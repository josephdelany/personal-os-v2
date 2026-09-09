#!/usr/bin/env python3
"""The unified daily panel (ADR-0038): analysis.panel from three sources.

Precedence per (day, canonical-metric): signals > legacy_daily > atoms — fresher
provenance wins; legacy extends history back to 2019. Everything else in signals
passes through under its native "source.metric" name so no stream is lost.
Genuine NULL-honesty: absent means absent (REQ-INF-505); nothing filled.
Rebuild is full DELETE+reload (analysis is rebuildable by design).

**B13 (ADR-0058) adds atom-derived `chrome_events` and `yt_events`, as a FILL, not an
override.** The `attention` stream in `public.signals` stopped on 2026-07-28; once Takeout
history is imported as `web_visit` / `media_play` atoms, those atoms are the only source for
every day after that. They are inserted for days signals does not already cover, and they
never replace a signals value.

The build order asked for atoms to *win* these two metrics. Review showed that is unsafe and
it was not done, for two reasons that only appear when the two sources overlap:

* **The two sources use different day boundaries.** Atoms carry `subject_day` (04:00 ET,
  ADR-0019); the signals passes below group by `ts::date`, the server's UTC calendar date. A
  visit at 22:00 ET is one day under signals and the previous day under atoms. Overwriting
  would move every late-evening visit one day earlier across the overlap — a silent step in
  the middle of a series, which is the failure ADR-0058 refuses to accept for the `screen_*`
  metrics and must equally refuse here.
* **Chrome expires local history at roughly 90 days**, so a Takeout archive covers about a
  quarter. Letting it win would replace complete historical values with partial ones.

Filling only where signals is absent gets the live data in without rewriting history. The
join still carries the day-boundary difference, which is recorded rather than hidden (OQ-52).

**Why only those two.** The four `screen_*` metrics (`screen_active_hours`,
`screen_binge_min`, `screen_max_binge`, `screen_sessions`) are session-level statistics whose
definitions — the inactivity gap that ends a session, the length that makes a session a
binge — live in the old stack's code, which is not in this repository. Re-deriving them here
with invented thresholds would produce a series that silently steps at the changeover and
would not mean what the historical values mean. They therefore continue to come from signals
alone and go stale visibly, which is the honest failure (OQ-48). An event count has no such
ambiguity: it is the number of events in the subject day, and it means the same thing in
both stacks.
"""
import json
import re

# v2: attention event counts may now come from atoms (ADR-0058). `build()` opens with a full
# `delete from analysis.panel` and reloads, so after the first v2 run no v1 row survives — an
# earlier comment here claimed the bump kept v1 rows identifiable, which is not true of a
# rebuild-from-scratch engine. What the bump is actually for: every stored row states which
# code produced it (RULE-12), so a row read out of the table can be attributed to a known
# definition, and a version that never changed would make two different definitions
# indistinguishable in that column.
CODE_VERSION = "panel-v2"

# canonical name -> the atom kind whose per-day count defines it. Inserted AFTER the signals
# passes, so these FILL days signals never covered and never overwrite one it did.
ATOM_EVENT_COUNTS = {
    "chrome_events": "web_visit",
    "yt_events": "media_play",
}

# canonical name -> (signals source, signals metric)
SIG_CANON = {
    "sleep_asleep_min":  ("apple_sleep", "asleep_min"),
    "sleep_inbed_min":   ("apple_sleep", "inbed_min"),
    "sleep_efficiency":  ("apple_sleep", "efficiency"),
    "sleep_deep_pct":    ("apple_sleep", "deep_pct"),
    "sleep_rem_pct":     ("apple_sleep", "rem_pct"),
    "sleep_onset_min":   ("apple_sleep", "onset_latency_min"),
    "sleep_waso_min":    ("apple_sleep", "waso_min"),
    "sleep_midpoint":    ("apple_sleep", "midpoint_clock"),
    "hrv_sdnn":          ("apple_hrv", "sdnn"),
    "hrv_rmssd":         ("apple_hrv", "rmssd"),
    "rhr":               ("apple_vitals", "rhr_night"),
    "resp_night":        ("apple_vitals", "resp_night"),
    "wrist_temp_f":      ("apple_vitals", "wrist_temp_f"),
    "steps":             ("health_history", "steps"),
    "screen_active_hours": ("attention", "active_hours"),
    "screen_binge_min":  ("attention", "binge_minutes"),
    "screen_max_binge":  ("attention", "max_binge_len"),
    "screen_sessions":   ("attention", "session_count"),
    "yt_events":         ("attention", "yt_events"),
    "chrome_events":     ("attention", "chrome_events"),
}
# legacy_daily column -> canonical (fills where signals lacks the day)
LEGACY_CANON = {
    "hrv": "hrv_sdnn", "rhr": "rhr", "resp": "resp_night",
    "kcal": "active_kcal", "exmin": "exercise_min", "steps": "steps",
    "asleep": "sleep_asleep_min", "inbed": "sleep_inbed_min",
    "deep": "sleep_deep_min", "rem": "sleep_rem_min",
    "onset": "sleep_onset_min", "wake_min": "sleep_waso_min",
}


# The four schemas this engine reads and writes. They are parameters, not literals, so a test
# can run the real `build()` against throwaway schema names instead of having to create schemas
# actually called `core`, `analysis` and `public` — which is what RULE-01's disposable-schema
# carve-out forbids (OQ-52). Production passes nothing and gets the production names, so this
# changes no deployed behaviour; the migrations already work this way with __CORE__/__OPS__.
SCHEMAS = {"core": "core", "analysis": "analysis", "public": "public",
           "config": "config", "ops": "ops"}
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def resolve_schemas(overrides=None):
    """Merge caller overrides over the production defaults, rejecting anything that is not a
    plain identifier. These names are interpolated into SQL — a bind parameter cannot carry an
    identifier — so the allowlist pattern is the guard."""
    out = dict(SCHEMAS)
    for k, v in (overrides or {}).items():
        if k not in SCHEMAS:
            raise ValueError(f"unknown schema role {k!r}")
        if not _IDENT.match(v):
            raise ValueError(f"not a plain schema identifier: {v!r}")
        out[k] = v
    return out


def build(cur, schemas=None):
    """Rebuild the daily panel. Caller owns the transaction. Returns row count."""
    S = resolve_schemas(schemas)
    CORE, ANALYSIS, PUBLIC, CONFIG = S["core"], S["analysis"], S["public"], S["config"]
    cur.execute(f"delete from {ANALYSIS}.panel")
    # 1) signals — canonical headliners
    for canon, (src, met) in SIG_CANON.items():
        cur.execute(f"""
            insert into {ANALYSIS}.panel (day, metric, value, src, code_version)
            select ts::date, %s, avg(value), %s, %s
              from {PUBLIC}.signals
             where source=%s and metric=%s and value is not null
             group by 1
            on conflict (day, metric) do nothing""",
            (canon, f"signals:{src}", CODE_VERSION, src, met))
    # 2) signals — full passthrough for every remaining stream (no loss)
    cur.execute(f"""
        insert into {ANALYSIS}.panel (day, metric, value, src, code_version)
        select ts::date, source || '.' || metric, avg(value),
               'signals:' || source, %s
          from {PUBLIC}.signals
         where value is not null
         group by 1, source, metric
        on conflict (day, metric) do nothing""", (CODE_VERSION,))
    # 3) legacy_daily — extend canonical history where signals is absent
    for col, canon in LEGACY_CANON.items():
        db_col = "core_min" if col == "core" else col
        cur.execute(f"""
            insert into {ANALYSIS}.panel (day, metric, value, src, code_version)
            select day, %s, {db_col}, 'legacy_daily', %s
              from {ANALYSIS}.legacy_daily
             where {db_col} is not null
            on conflict (day, metric) do nothing""", (canon, CODE_VERSION))
    # 4) atoms — check-in scores + daily consume/workout aggregates
    cur.execute(f"""
        insert into {ANALYSIS}.panel (day, metric, value, src, code_version)
        select a.subject_day, a.metric_key, avg(a.value_point), 'atoms', %s
          from {CORE}.atoms_current a
         where a.metric_key like 'checkin_%%' and a.value_point is not null
         group by 1, a.metric_key
        on conflict (day, metric) do nothing""", (CODE_VERSION,))
    cur.execute(f"""
        insert into {ANALYSIS}.panel (day, metric, value, src, code_version)
        select a.subject_day, 'meals_logged', count(*), 'atoms', %s
          from {CORE}.atoms_current a where a.kind='consume'
         group by 1
        on conflict (day, metric) do nothing""", (CODE_VERSION,))
    cur.execute(f"""
        insert into {ANALYSIS}.panel (day, metric, value, src, code_version)
        select a.subject_day, 'strength_volume',
               sum(case when a.metric_key='strength_load_lb' then a.value_point else 0 end)
               * greatest(1, avg(case when a.metric_key='strength_reps' then a.value_point end)),
               'atoms', %s
          from {CORE}.atoms_current a where a.kind='workout'
         group by 1
        on conflict (day, metric) do nothing""", (CODE_VERSION,))
    # 4b) atoms — attention EVENT COUNTS, FILLING days signals does not cover (ADR-0058).
    #     Placed after the signals passes on purpose: precedence here is insertion order plus
    #     `on conflict do nothing`, so being later means signals keeps any day it already has
    #     and these only reach days it never covered. See the module docstring for why an
    #     override would be wrong (different day boundary, partial Takeout history).
    for canon, kind in ATOM_EVENT_COUNTS.items():
        cur.execute(f"""
            insert into {ANALYSIS}.panel (day, metric, value, src, code_version)
            select a.subject_day, %s, count(*), 'atoms:takeout', %s
              from {CORE}.atoms_current a
             where a.kind = %s
             group by 1
            on conflict (day, metric) do nothing""", (canon, CODE_VERSION, kind))
    # 5) mobility — from {ANALYSIS}.visits_public ONLY (labels/minutes; never a coordinate — REQ-LOC-012).
    #    A day with no visit gets no row: absent means absent (REQ-LOC-015, REQ-INF-505).
    cur.execute(f"""
        insert into {ANALYSIS}.panel (day, metric, value, src, code_version)
        select subject_day, 'away_min', sum(dwell_min) filter (where not coalesce(is_home, false)), 'visits', %s
          from {ANALYSIS}.visits_public group by 1
        having sum(dwell_min) filter (where not coalesce(is_home, false)) is not null
        on conflict (day, metric) do nothing""", (CODE_VERSION,))
    cur.execute(f"""
        insert into {ANALYSIS}.panel (day, metric, value, src, code_version)
        select subject_day, 'home_min', sum(dwell_min) filter (where is_home), 'visits', %s
          from {ANALYSIS}.visits_public group by 1
        having sum(dwell_min) filter (where is_home) is not null
        on conflict (day, metric) do nothing""", (CODE_VERSION,))
    cur.execute(f"""
        insert into {ANALYSIS}.panel (day, metric, value, src, code_version)
        select subject_day, 'places_distinct', count(distinct place_id), 'visits', %s
          from {ANALYSIS}.visits_public group by 1
        on conflict (day, metric) do nothing""", (CODE_VERSION,))
    # the places domain's config rows register themselves the first night the panel has away_min (ADR-0045)
    cur.execute(f"select {CONFIG}.ensure_places_metrics()")
    cur.execute(f"select count(*) from {ANALYSIS}.panel")
    return cur.fetchone()[0]


def log_run(cur, n):
    cur.execute(f"""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                   values ('panel_build', now(), 'ok', %s, %s)""",
                (n, json.dumps({"code_version": CODE_VERSION})))
