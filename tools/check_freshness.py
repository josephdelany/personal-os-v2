#!/usr/bin/env python3
"""Is data still arriving? (REQ-NFR-005..012, Gate 4)

    PYTHONPATH=. python3 tools/check_freshness.py
    PYTHONPATH=. python3 tools/check_freshness.py --json

**The failure this exists to catch.** On 2026-07-28 device-side capture stopped.
`public.intraday`, the browser-history feed and the location feed went silent within two days
of each other and stayed silent for 43 days. Every scheduled job kept running and kept writing
`status = 'ok'` rows to `ops.runs` the entire time, because the jobs were alive and only their
inputs were dead. `tools/status.py` answers "did the job run?"; nothing answered "did anything
arrive?". That is the gap, and 43 unrecoverable days of sleep, HRV and vitals is what it cost.

**What it checks.** Every metric in `core.metric_registry` carrying a `max_staleness_days`
(REQ-NFR-005 — the limit is stored configuration, never a number written into this file). For
each, the most recent `subject_day` on which an observation exists, taken as the later of
`core.atoms_current` and `analysis.panel` (REQ-NFR-012 — the most recent OBSERVATION, never a
job's completion time, because a job that succeeds over an empty input proves nothing).

**Three states, and only one of them fails (REQ-NFR-006/007).**

* `stale` — this metric HAS reported and has now gone quiet past its limit. This is the
  2026-07-28 signature, and it is the only state that exits non-zero.
* `misconfigured` — nothing under this key, but a **similar** key does carry a series. The
  metric is registered for monitoring and is not being monitored. It fails, because that is a
  real and actionable defect. The candidate is a **suggestion, never an alias** (REQ-NFR-014):
  deciding two differently named series are the same measurement is a ruling, not a string
  match, and a monitoring tool has no business making it.
* `never_seen` — no observation under this metric key, and nothing that resembles it. Unbuilt
  scope, so it is counted and reported but does not fail the run — failing on it would make the
  check permanently red and therefore permanently ignored. **This list can still hide a naming
  mismatch**: the detector finds only resemblances a string comparison can find, and it will
  not connect `resting_hr` to `rhr`. See OQ-51.
* `fresh` — reported inside its limit.

**It never prints a value** (REQ-NFR-011). Only the metric key, the last observed day and the
elapsed day count. An operational alert must not become an egress path (RULE-29).
"""
import argparse
import datetime as dt
import json
import re
import sys

from lib import db
from tools.importers.common import current_subject_day, redact

CODE_VERSION = "check-freshness-v1"
JOB_NAME = "check_freshness"


def registered_limits(cur, schema="core"):
    """metric_key -> max_staleness_days, for every metric that declares one (REQ-NFR-005),
    plus the count of registered metrics that declare none (REQ-NFR-010)."""
    cur.execute(f"select metric_key, max_staleness_days from {schema}.metric_registry")
    rows = cur.fetchall()
    limits = {k: int(v) for k, v in rows if v is not None}
    unmonitored = sorted(k for k, v in rows if v is None)
    return limits, unmonitored


def observed_series(cur, schema="core", analysis="analysis"):
    """Every metric name that actually carries observations, in either store.

    Used to tell a registry key that nothing writes under from one whose source truly does not
    exist. Names only — no values leave this function (REQ-NFR-011).
    """
    names = set()
    cur.execute(f"select distinct metric_key from {schema}.atoms_current where metric_key is not null")
    names.update(r[0] for r in cur.fetchall())
    if _panel_exists(cur, analysis):
        cur.execute(f"select distinct metric from {analysis}.panel")
        names.update(r[0] for r in cur.fetchall())
    return names


def similar_key(metric, candidates):
    """A key that looks like it might be the same series under another name, or None.

    REQ-NFR-013/014: this **suggests**, it never aliases. Deciding that two differently named
    series are the same measurement is a claim about data and belongs in an ADR after Joe has
    ruled, not in a monitoring tool that noticed a string resemblance. What it buys is that a
    metric silently escaping monitoring becomes a failing, named, actionable report instead of
    being filed under "never reported" and passing.

    Unit suffixes are stripped before comparison because that is the shape the drift actually
    takes here — the registry says `hrv_sdnn_ms` and the panel says `hrv_sdnn`.
    """
    import difflib
    suffixes = ("_ms", "_bpm", "_pct", "_min", "_lb", "_kcal", "_c", "_f", "_usd", "_km",
                "_m_s", "_cm", "_db", "_ml_kg_min")

    def stem(name):
        for suf in suffixes:
            if name.endswith(suf):
                return name[: -len(suf)]
        return name

    target = stem(metric)
    by_stem = {}
    for c in candidates:
        by_stem.setdefault(stem(c), c)
    if target in by_stem:
        return by_stem[target]
    close = difflib.get_close_matches(target, list(by_stem), n=1, cutoff=0.85)
    return by_stem[close[0]] if close else None


def _panel_exists(cur, analysis="analysis"):
    """Is the panel present? A missing panel is a schema-shape fact, not an outage."""
    cur.execute("select to_regclass(%s) is not null", (f"{analysis}.panel",))
    return bool(cur.fetchone()[0])


def last_observed(cur, keys, schema="core", analysis="analysis"):
    """metric_key -> (last subject_day, which store it came from).

    Both stores are consulted and the LATER day wins. `core.atoms` is the spine's observation
    store; `analysis.panel` is where the old stack's live feeds still land. Checking only one
    would report a metric as quiet while it is arriving through the other.
    """
    seen = {}
    if not keys:
        return seen
    ks = list(keys)
    cur.execute(f"""select metric_key, max(subject_day) from {schema}.atoms_current
                     where metric_key = any(%s) group by 1""", (ks,))
    for k, d in cur.fetchall():
        if d is not None:
            seen[k] = (d, "atoms")
    if not _panel_exists(cur, analysis):
        return seen
    cur.execute(f"""select metric, max(day) from {analysis}.panel
                     where metric = any(%s) group by 1""", (ks,))
    for k, d in cur.fetchall():
        if d is None:
            continue
        prior = seen.get(k)
        if prior is None or d > prior[0]:
            seen[k] = (d, "panel")
    return seen


def check(cur, schema="core", analysis="analysis"):
    """Returns (report, ok). Caller owns the transaction.

    The schema names are parameters, not literals, so a test can run this against throwaway
    names rather than creating schemas actually called `core` and `analysis` — which RULE-01's
    disposable-schema carve-out forbids (OQ-52). Production passes nothing and gets the
    production names. Both are validated as plain identifiers before interpolation, because an
    identifier cannot be a bind parameter.
    """
    for name in (schema, analysis):
        if not re.match(r"^[a-z_][a-z0-9_]*$", name):
            raise ValueError(f"not a plain schema identifier: {name!r}")
    # The clock is the SUBJECT day, not the database server's calendar date.
    #
    # `current_date` on Supabase is UTC. A stored `subject_day` turns at 04:00 ET (RULE-03,
    # ADR-0019). Those are different quantities and mixing them produces a seasonal off-by-one:
    # the workflow's 08:10 UTC cron is 04:10 ET in summer (just after the boundary) and 03:10
    # ET in winter (just before it), so the two agree from March to November and differ by a
    # day the rest of the year. Using the subject day on both sides removes the seam rather
    # than moving it. `now()` is read from the database so the clock still comes from one place.
    #
    # The direction matters and an earlier comment here had it backwards: with the UTC date as
    # the clock, winter elapsed counts would be one too HIGH (a metric looks staler than it is
    # and reports early); with the subject day as the clock and a fixed-UTC cron, the check
    # simply runs slightly before the new subject day opens in winter, which delays detection
    # by at most one run and never fabricates staleness. Reporting late is the safer error.
    cur.execute("select now()")
    today = current_subject_day(cur.fetchone()[0])

    limits, unmonitored = registered_limits(cur, schema)
    seen = last_observed(cur, set(limits), schema, analysis)
    all_series = observed_series(cur, schema, analysis)

    fresh, stale, never, misconfigured = [], [], [], []
    for key in sorted(limits):
        limit = limits[key]
        got = seen.get(key)
        if got is None:
            # REQ-NFR-013: nothing under this key, but a similar key HAS a series. That is a
            # naming mismatch, not absent scope — the metric is registered for monitoring and
            # is not being monitored. It fails, because it is a real defect and it is
            # actionable, unlike genuinely unbuilt scope.
            candidate = similar_key(key, all_series - set(limits))
            if candidate:
                misconfigured.append({"metric": key, "limit_days": limit,
                                      "candidate_key": candidate})
            else:
                never.append({"metric": key, "limit_days": limit})
            continue
        day, src = got
        elapsed = (today - day).days
        row = {"metric": key, "last_day": day.isoformat(), "elapsed_days": elapsed,
               "limit_days": limit, "source": src}
        (stale if elapsed > limit else fresh).append(row)

    report = {
        "as_of": today.isoformat(),
        "code_version": CODE_VERSION,
        "counts": {"fresh": len(fresh), "stale": len(stale),
                   "misconfigured": len(misconfigured),
                   "never_seen": len(never), "unmonitored": len(unmonitored)},
        "stale": sorted(stale, key=lambda r: -r["elapsed_days"]),
        "fresh": fresh,
        "misconfigured": misconfigured,
        "never_seen": never,
        "unmonitored": unmonitored,
    }
    # REQ-NFR-007: a metric that has gone quiet fails the run.
    # REQ-NFR-013: so does one that is not being monitored because of a naming mismatch — the
    # metric is registered, a series exists, and the check is blind to it. That is a defect.
    # REQ-NFR-006/010: never_seen and unmonitored are reported, counted, and do NOT fail —
    # they are unbuilt scope rather than a feed that stopped, and a check that is always red
    # is a check nobody reads.
    return report, (len(stale) == 0 and len(misconfigured) == 0)


def log_run(cur, report, ok, ops="ops"):
    """REQ-NFR-008: one runs row per execution, carrying the counts. Counts only — no metric
    value ever reaches this row (REQ-NFR-011)."""
    cur.execute(f"""insert into {ops}.runs (job_name, finished_at, status, rows_written, detail)
                    values (%s, now(), %s, %s, %s)""",
                (JOB_NAME, "ok" if ok else "error", report["counts"]["fresh"],
                 json.dumps({"counts": report["counts"], "code_version": CODE_VERSION,
                             "stale_metrics": [r["metric"] for r in report["stale"]],
                             "misconfigured_metrics": [r["metric"] for r in report["misconfigured"]]})))


def render(report):
    c = report["counts"]
    out = [f"freshness as of {report['as_of']}  "
           f"fresh={c['fresh']} stale={c['stale']} misconfigured={c['misconfigured']} "
           f"never_seen={c['never_seen']} unmonitored={c['unmonitored']}"]
    if report["stale"]:
        out.append("")
        out.append("STALE — reported before, quiet now:")
        for r in report["stale"]:
            out.append(f"  {r['metric']:32} last {r['last_day']}  "
                       f"{r['elapsed_days']}d elapsed (limit {r['limit_days']}d, via {r['source']})")
    if report["misconfigured"]:
        out.append("")
        out.append("MISCONFIGURED — registered for monitoring, but nothing writes under this "
                   "key while a similar series exists. NOT monitored:")
        for r in report["misconfigured"]:
            out.append(f"  {r['metric']:32} nothing observed; a series exists under "
                       f"{r['candidate_key']!r} (limit {r['limit_days']}d)")
        out.append("  -> these are SUGGESTIONS, not aliases. Whether two differently named")
        out.append("     series are the same measurement is a ruling, not a string match.")
    if report["never_seen"]:
        out.append("")
        out.append("NEVER SEEN — registered with a limit, no observation under this key ever:")
        for r in report["never_seen"]:
            out.append(f"  {r['metric']:32} (limit {r['limit_days']}d)")
        out.append("  -> this list can still hide a naming mismatch. The detector above only")
        out.append("     finds resemblances a string comparison can find; it will not connect")
        out.append("     'resting_hr' to 'rhr'. A metric here may be unbuilt scope OR may be")
        out.append("     unmonitored under another name — see OQ-51.")
    if report["unmonitored"]:
        out.append("")
        out.append(f"UNMONITORED — registered with no staleness limit: "
                   f"{', '.join(report['unmonitored'])}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable report on stdout")
    ap.add_argument("--core", default="core")
    ap.add_argument("--analysis", default="analysis")
    ap.add_argument("--no-log", action="store_true", help="skip the ops.runs row")
    a = ap.parse_args(argv)

    # REQ-NFR-009: an unreachable database exits non-zero and reports nothing as fresh.
    try:
        conn = db.connect()
    except Exception as e:
        print(f"{JOB_NAME}: DATABASE UNREACHABLE: {type(e).__name__}: {redact(e)}",
              file=sys.stderr)
        return 2

    try:
        cur = conn.cursor()
        report, ok = check(cur, a.core, a.analysis)
        if not a.no_log:
            log_run(cur, report, ok)
            conn.commit()
        else:
            conn.rollback()
    except Exception as e:
        conn.rollback()
        # REQ-NFR-011: the checker reports metric keys and day counts, never content. Its
        # own failure path is not an exception to that — a Postgres error can carry a DETAIL
        # line echoing an `analysis.panel` or `core.atoms` row.
        print(f"{JOB_NAME}: FAILED: {type(e).__name__}: {redact(e)}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    print(json.dumps(report, indent=2) if a.json else render(report))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
