#!/usr/bin/env python3
"""The unified daily panel (ADR-0038): analysis.panel from three sources.

Precedence per (day, canonical-metric): signals > legacy_daily > atoms — fresher
provenance wins; legacy extends history back to 2019. Everything else in signals
passes through under its native "source.metric" name so no stream is lost.
Genuine NULL-honesty: absent means absent (REQ-INF-505); nothing filled.
Rebuild is full DELETE+reload (analysis is rebuildable by design).
"""
import json

CODE_VERSION = "panel-v1"

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


def build(cur):
    """Rebuild analysis.panel. Caller owns the transaction. Returns row count."""
    cur.execute("delete from analysis.panel")
    # 1) signals — canonical headliners
    for canon, (src, met) in SIG_CANON.items():
        cur.execute("""
            insert into analysis.panel (day, metric, value, src, code_version)
            select ts::date, %s, avg(value), %s, %s
              from public.signals
             where source=%s and metric=%s and value is not null
             group by 1
            on conflict (day, metric) do nothing""",
            (canon, f"signals:{src}", CODE_VERSION, src, met))
    # 2) signals — full passthrough for every remaining stream (no loss)
    cur.execute("""
        insert into analysis.panel (day, metric, value, src, code_version)
        select ts::date, source || '.' || metric, avg(value),
               'signals:' || source, %s
          from public.signals
         where value is not null
         group by 1, source, metric
        on conflict (day, metric) do nothing""", (CODE_VERSION,))
    # 3) legacy_daily — extend canonical history where signals is absent
    for col, canon in LEGACY_CANON.items():
        db_col = "core_min" if col == "core" else col
        cur.execute(f"""
            insert into analysis.panel (day, metric, value, src, code_version)
            select day, %s, {db_col}, 'legacy_daily', %s
              from analysis.legacy_daily
             where {db_col} is not null
            on conflict (day, metric) do nothing""", (canon, CODE_VERSION))
    # 4) atoms — check-in scores + daily consume/workout aggregates
    cur.execute("""
        insert into analysis.panel (day, metric, value, src, code_version)
        select a.subject_day, a.metric_key, avg(a.value_point), 'atoms', %s
          from core.atoms_current a
         where a.metric_key like 'checkin_%%' and a.value_point is not null
         group by 1, a.metric_key
        on conflict (day, metric) do nothing""", (CODE_VERSION,))
    cur.execute("""
        insert into analysis.panel (day, metric, value, src, code_version)
        select a.subject_day, 'meals_logged', count(*), 'atoms', %s
          from core.atoms_current a where a.kind='consume'
         group by 1
        on conflict (day, metric) do nothing""", (CODE_VERSION,))
    cur.execute("""
        insert into analysis.panel (day, metric, value, src, code_version)
        select a.subject_day, 'strength_volume',
               sum(case when a.metric_key='strength_load_lb' then a.value_point else 0 end)
               * greatest(1, avg(case when a.metric_key='strength_reps' then a.value_point end)),
               'atoms', %s
          from core.atoms_current a where a.kind='workout'
         group by 1
        on conflict (day, metric) do nothing""", (CODE_VERSION,))
    cur.execute("select count(*) from analysis.panel")
    return cur.fetchone()[0]


def log_run(cur, n):
    cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                   values ('panel_build', now(), 'ok', %s, %s)""",
                (n, json.dumps({"code_version": CODE_VERSION})))
