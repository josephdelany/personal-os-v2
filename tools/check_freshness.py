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

**Two blind spots this also closes (ADR-0140). Both are cases where every count above is
literally true and the honest answer is still "capture is broken".**

* `source_quiet` — a metric is FRESH, and one of the CAPTURE SOURCES that used to supply it
  has stopped. This is not hypothetical: the bank CSV export died on 2026-05-13 and
  `chase_email` took over, so `transaction_amount_usd` is fresh on roughly a third of the
  transactions and a seventh of the value. Metric-scoped freshness cannot see it, because
  freshness asks "did anything arrive" and this asks "did the same thing keep arriving".
  Reported and counted; it does NOT fail the run — which of two sources to believe is a
  measurement ruling (RULE-12), and a check that is permanently red is a check nobody reads.
  `tools/check_source_continuity.py` is where a rate change across such a handover is
  quantified; this is the detector that says where to look.

  **The source here is the ingress channel** (`core.raw_captures.source`, a closed enum), not
  the device. The Watch-versus-iPhone split that made `steps` double-count is NOT visible to
  this check: for a file import both devices arrive under `file_import`, and the instrument
  survives only inside `core.atoms.evidence_span` as free text taken from the export's
  `sourceName`. That field is deliberately not parsed here. It is a user-renamable string
  ("Joe's iPhone") in a column that also carries merchant descriptors and page titles, and
  REQ-NFR-011 says an operational alert never becomes an egress path. Device-level attribution
  is a real gap and it belongs somewhere that can name instruments from stored configuration.
* the **local import schedule's own silence**. `ops/capture_schedule.py` runs on Joe's Mac
  under launchd, and this check runs on a GitHub runner, so a laptop that has been shut for a
  week is invisible here — every metric it would have refreshed simply ages, and the reason is
  not in the report. The job's expected cadence is read from the schedule declaration in
  `ops/capture_schedule.py` rather than written here, for the same reason staleness limits are
  read from the registry. It follows the `stale`/`never_seen` rule exactly: a schedule that has
  NEVER reported is `not_installed` and does not fail (it is not installed yet — see the
  activation steps in that module), while one that reported and then stopped is `job_stale`
  and does.

**It never prints a value** (REQ-NFR-011). Only the metric key, the last observed day and the
elapsed day count. An operational alert must not become an egress path (RULE-29).
"""
import argparse
import datetime as dt
import json
import re
import sys

from lib import db
from ops import capture_schedule
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


def contributing_sources(cur, keys, schema="core"):
    """(metric_key, ingress channel) -> the last subject_day that channel supplied.

    The channel is `core.raw_captures.source`, which is an enum: every value it can take is
    named in migration 0004 and none of them is personal data. That is the reason this reads
    the capture row rather than the atom's `evidence_span`, which carries the device name and
    much else besides (see the module docstring).

    ADR-0140. The join is `atoms -> raw_captures`, which is INV-1 read in the direction it was
    built for: every derived row traces to the capture it came from, so "which channel is still
    reporting" is answerable from stored rows rather than from a naming convention.

    The set of channels a metric depends on is DERIVED FROM EVIDENCE — a channel that has ever
    written an atom under this key — and is never a list maintained by hand. A hand-maintained
    list of expected sources is the same object as the prose inventory that `0053` replaced,
    and it goes stale in the same way: it would never have contained a source nobody
    remembered, and it would have gone on asserting one long after it died.

    Names and days only; no value leaves this function (REQ-NFR-011).
    """
    if not keys:
        return {}
    cur.execute(
        f"""select a.metric_key, rc.source::text, max(a.subject_day)
              from {schema}.atoms_current a
              join {schema}.raw_captures rc on rc.capture_id = a.raw_capture_id
             where a.metric_key = any(%s) and a.subject_day is not null
             group by 1, 2""", (list(keys),))
    out = {}
    for key, src, day in cur.fetchall():
        if day is not None:
            out.setdefault(key, {})[src] = day
    return out


def _relation_exists(cur, qualified):
    cur.execute("select to_regclass(%s) is not null", (qualified,))
    return bool(cur.fetchone()[0])


def declared_import_cadence_days(plist=None):
    """The maximum days between two firings of the local import, read from its own schedule.

    Not a number written here. `ops/capture_schedule.py` is the file that declares when the
    import runs, so it is the file this is read from; a constant here would be a second
    statement of the cadence, free to disagree with the first.
    """
    spec = (plist or capture_schedule.launchd_plist()).get("StartCalendarInterval") or {}
    if "Weekday" in spec:
        return 7
    if "Day" in spec:
        return 31
    if "Hour" in spec:
        return 1                      # a daily calendar interval
    return 1


def import_schedule_liveness(cur, today, ops="ops", cadence_days=None):
    """Has the LOCAL import schedule reported inside its own cadence? (ADR-0140)

    Three states, mirroring the metric rule exactly:

    * `not_installed` — no row under either job name, ever. The launchd agent has not been
      bootstrapped (ADR-0094 keeps activation a separate, human act). This does NOT fail: a
      schedule that was never installed is unbuilt scope, not a feed that stopped, and failing
      on it would leave this workflow red from the day it shipped until the day Joe installs
      the agent, which is how a red check becomes an ignored one.
    * `stale` — it reported and has now gone quiet past its cadence plus one day of margin.
      That is the laptop shut for a week, the agent unloaded, the plist wrong. It FAILS, and it
      is the only thing in this report that can explain why a dozen metrics aged at once.
    * `fresh` — it reported inside the window.

    Both job names count. `import_drop` writes the row when its transaction commits and
    `capture_schedule` writes one when it does not, so the pair is "the schedule fired",
    whatever the outcome was — including the outcomes that mean nothing arrived. A firing is
    not evidence of capture and is not read as any; that is what every other line of this file
    is for.
    """
    if not _relation_exists(cur, f"{ops}.runs"):
        return {"state": "unknown", "reason": f"{ops}.runs does not exist"}
    cadence = declared_import_cadence_days() if cadence_days is None else cadence_days
    limit = cadence + 1               # one cadence, plus a day of margin for a late laptop
    cur.execute(
        f"""select max(finished_at) from {ops}.runs
             where job_name in (%s, %s)""",
        (capture_schedule.JOB_NAME, capture_schedule.IMPORTER_JOB_NAME))
    last = cur.fetchone()[0]
    if last is None:
        return {"state": "not_installed", "limit_days": limit,
                "note": "the local import schedule has never written a runs row. It is not "
                        "installed; see ops/capture_schedule.py --emit-launchd."}
    last_day = current_subject_day(last)
    elapsed = (today - last_day).days
    return {"state": "stale" if elapsed > limit else "fresh",
            "last_day": last_day.isoformat(), "elapsed_days": elapsed, "limit_days": limit}


def check(cur, schema="core", analysis="analysis", ops="ops"):
    """Returns (report, ok). Caller owns the transaction.

    The schema names are parameters, not literals, so a test can run this against throwaway
    names rather than creating schemas actually called `core` and `analysis` — which RULE-01's
    disposable-schema carve-out forbids (OQ-52). Production passes nothing and gets the
    production names. Both are validated as plain identifiers before interpolation, because an
    identifier cannot be a bind parameter.
    """
    for name in (schema, analysis, ops):
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

    # ADR-0140. A fresh metric can be fresh on one instrument while another has died under it.
    # Only fresh metrics are examined: a stale metric already fails and already names its last
    # day, and enumerating the sources of something that is failing anyway is noise.
    by_source = contributing_sources(cur, {r["metric"] for r in fresh}, schema)
    source_quiet = []
    for row in fresh:
        limit = row["limit_days"]
        for src, day in sorted(by_source.get(row["metric"], {}).items()):
            elapsed = (today - day).days
            if elapsed > limit:
                source_quiet.append({"metric": row["metric"], "capture_source": src,
                                     "last_day": day.isoformat(), "elapsed_days": elapsed,
                                     "limit_days": limit,
                                     "metric_last_day": row["last_day"]})
    source_quiet.sort(key=lambda r: -r["elapsed_days"])

    schedule = import_schedule_liveness(cur, today, ops)

    report = {
        "as_of": today.isoformat(),
        "code_version": CODE_VERSION,
        "counts": {"fresh": len(fresh), "stale": len(stale),
                   "misconfigured": len(misconfigured),
                   "never_seen": len(never), "unmonitored": len(unmonitored),
                   "source_quiet": len(source_quiet)},
        "stale": sorted(stale, key=lambda r: -r["elapsed_days"]),
        "fresh": fresh,
        "misconfigured": misconfigured,
        "never_seen": never,
        "unmonitored": unmonitored,
        "source_quiet": source_quiet,
        "import_schedule": schedule,
    }
    # REQ-NFR-007: a metric that has gone quiet fails the run.
    # REQ-NFR-013: so does one that is not being monitored because of a naming mismatch — the
    # metric is registered, a series exists, and the check is blind to it. That is a defect.
    # REQ-NFR-006/010: never_seen and unmonitored are reported, counted, and do NOT fail —
    # they are unbuilt scope rather than a feed that stopped, and a check that is always red
    # is a check nobody reads.
    # ADR-0140: `source_quiet` does not fail either, for a different reason — which of two
    # instruments to believe is Joe's ruling (RULE-12, OQ-55), not this tool's. A local import
    # schedule that reported and then STOPPED does fail; one that was never installed does not.
    return report, (len(stale) == 0 and len(misconfigured) == 0
                    and schedule.get("state") != "stale")


def log_run(cur, report, ok, ops="ops"):
    """REQ-NFR-008: one runs row per execution, carrying the counts. Counts only — no metric
    value ever reaches this row (REQ-NFR-011)."""
    cur.execute(f"""insert into {ops}.runs (job_name, finished_at, status, rows_written, detail)
                    values (%s, now(), %s, %s, %s)""",
                (JOB_NAME, "ok" if ok else "error", report["counts"]["fresh"],
                 json.dumps({"counts": report["counts"], "code_version": CODE_VERSION,
                             "stale_metrics": [r["metric"] for r in report["stale"]],
                             "misconfigured_metrics": [r["metric"] for r in report["misconfigured"]],
                             # ADR-0140. Metric key and capture-source name only: both are
                             # schema vocabulary, neither is an observation (REQ-NFR-011).
                             "quiet_sources": sorted({r["capture_source"]
                                                      for r in report["source_quiet"]}),
                             "import_schedule": report["import_schedule"].get("state")})))


def render(report):
    c = report["counts"]
    out = [f"freshness as of {report['as_of']}  "
           f"fresh={c['fresh']} stale={c['stale']} misconfigured={c['misconfigured']} "
           f"never_seen={c['never_seen']} unmonitored={c['unmonitored']} "
           f"source_quiet={c.get('source_quiet', 0)}"]
    sched = report.get("import_schedule") or {}
    if sched.get("state") == "stale":
        out.append("")
        out.append(f"LOCAL IMPORT SCHEDULE STALE — last reported {sched['last_day']}, "
                   f"{sched['elapsed_days']}d ago (limit {sched['limit_days']}d). The drop "
                   f"folder is on the Mac and nothing on a runner can import it. Every "
                   f"metric it feeds is ageing for this reason.")
    elif sched.get("state") == "not_installed":
        out.append("")
        out.append("LOCAL IMPORT SCHEDULE NOT INSTALLED — no run has ever reported. This does "
                   "not fail the check; it means file import is a manual act today.")
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
    if report.get("source_quiet"):
        out.append("")
        out.append("SOURCE QUIET — the metric is FRESH and one of the ingress channels that "
                   "used to supply it has stopped:")
        for r in report["source_quiet"]:
            out.append(f"  {r['metric']:24} via {r['capture_source']:16} last {r['last_day']}  "
                       f"{r['elapsed_days']}d elapsed, while the metric itself has "
                       f"{r['metric_last_day']}")
        out.append("  -> this does NOT fail the run. Which source to believe is a measurement")
        out.append("     ruling, not a monitoring decision. What it tells you is that a trend")
        out.append("     crossing this boundary is comparing two capture paths;")
        out.append("     tools/check_source_continuity.py quantifies the rate change.")
        out.append("     Device-level loss (Watch vs iPhone) is NOT covered — see the module")
        out.append("     docstring for why evidence_span is not parsed here.")
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
    ap.add_argument("--ops", default="ops",
                    help="ops schema for the runs row and the schedule-liveness read")
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
        report, ok = check(cur, a.core, a.analysis, a.ops)
        if not a.no_log:
            log_run(cur, report, ok, a.ops)
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
