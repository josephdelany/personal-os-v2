#!/usr/bin/env python3
"""B14R step 2: the derivation catalogue (REQ-REC-004).

What each derived measure is MADE OF. Without it a measure's definition lives in whichever
function last computed it, and two functions can disagree while both look authoritative
(RULE-12: one owner per measure).

Everything here is DERIVED, never asserted:

  * `unit` and the accumulate/read distinction come from core.metric_registry.state_class.
  * `input_fields` and `method_version` come from tools/importers/apple_health.py — the HK
    map and the module's code_version, so the catalogue moves when the importer moves.
  * `time_specification` follows from state_class: a total accumulates over a window and is
    a fact about an INTERVAL; a measurement is a reading and is a fact about an INSTANT.
    This is the claim OQ-54 turns out to violate, which is the point of writing it down.
  * `missingness_rule` is quoted from the constitution per class, not composed per metric.
  * `analytical_consumers` is a scan for the literal metric key across migrations and tools.
    An empty list is meaningful: nothing names this measure, so it reaches analysis only
    through generic registry-driven paths, and a rename would not be caught by any test.

Usage:
    PYTHONPATH=. python3 tools/build_catalogue.py --core core            # dry run
    PYTHONPATH=. python3 tools/build_catalogue.py --core core --commit
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCAN_DIRS = ("migrations", "tools", "lib")

# RULE-06 (never impute) and RULE-07 (three-valued presence), stated once per class rather
# than reworded per metric. A day with no record is UNKNOWN. It is never zero: the absence
# of a step record is not evidence of a day without steps, it is evidence of a day without
# a watch.
MISSINGNESS = {
    "total": "a subject day with no record is unknown, never zero (RULE-06, RULE-07); "
             "absence of a record is absence of capture, not absence of the activity",
    "total_increasing":
             "a subject day with no record is unknown, never zero (RULE-06, RULE-07); "
             "the running total is not differenced across a capture gap",
    "measurement":
             "a subject day with no reading is unknown (RULE-07) and is not carried forward "
             "past core.metric_registry.max_staleness_days (REQ-INF-109)",
}

# RULE-08. A total accumulates over a window; a reading happens at an instant.
TIME_SPEC = {"total": "interval", "total_increasing": "interval", "measurement": "instant"}


def consumers(metric_key):
    """Files that name this measure literally. Empty means only generic paths reach it."""
    found = set()
    for d in SCAN_DIRS:
        for path in (ROOT / d).rglob("*"):
            if path.suffix not in (".sql", ".py") or "__pycache__" in str(path):
                continue
            if path.name.startswith("build_catalogue"):
                continue
            try:
                if re.search(rf"\b{re.escape(metric_key)}\b", path.read_text()):
                    found.add(str(path.relative_to(ROOT)))
            except (UnicodeDecodeError, OSError):
                continue
    return sorted(found)


def rows(cur, core):
    from tools.importers import apple_health as ah
    hk_for = {v[0]: (k, v[1]) for k, v in ah.HK.items()}
    version = getattr(ah, "CODE_VERSION", None) or getattr(ah, "VERSION", None) or "apple_health/unversioned"

    cur.execute(f"""SELECT r.metric_key, r.unit, r.state_class,
                           min(a.subject_day), count(a.metric_key)
                      FROM {core}.metric_registry r
                      JOIN {core}.atoms a ON a.metric_key = r.metric_key
                     GROUP BY 1,2,3 ORDER BY 1""")
    out = []
    for metric, unit, state_class, earliest, n in cur.fetchall():
        hk, hk_unit = hk_for.get(metric, (None, None))
        if metric.startswith("sleep_"):
            hk, hk_unit = ah.SLEEP_TYPE, "min"
            spec, method = "interval", "sleep stage segment duration"
        elif hk:
            spec, method = TIME_SPEC[state_class], f"apple_health sample ({state_class})"
        else:
            # Not from the Health importer. Its inputs are unknown to this tool and it must
            # say so rather than guess a method it has not read.
            spec, method = TIME_SPEC[state_class], "not produced by a catalogued importer"
        out.append(dict(
            measure=metric,
            input_fields=[hk or "unknown", "value", "startDate", "endDate", "sourceName"]
                          if hk else ["unknown"],
            method=method, method_version=str(version), unit=unit or hk_unit or "",
            time_specification=spec, missingness_rule=MISSINGNESS[state_class],
            earliest_supported_event_date=earliest, analytical_consumers=consumers(metric),
            owner="B13" if hk else "unassigned — no catalogued producer", atoms=n))
    return out


def write_catalogue(cur, catalogue, config="config"):
    """Rebuild config.derivation_catalogue from `catalogue`. Returns the preserved measures.

    Extracted from `main()` so the preservation rule can be tested by RUNNING it. The test
    that pinned the previous version grepped this file for three string literals, and the
    code it described was a no-op for every row it was written to protect.
    """
    # The RULE-13 parameters (formula names, validated rep range, ACWR windows) are seeded by
    # migration 0061 and are NOT recomputed here. A blind DELETE-and-reinsert destroyed them.
    #
    # The first repair read them back and rewrote them AFTER the reinsert, which preserved
    # nothing: `rows()` is `metric_registry JOIN atoms`, so a measure with no atoms yet -- which
    # is all three that 0061 seeds, until B18's engine runs -- is not in `catalogue` at all. The
    # DELETE removed the row and the write-back loop never reached it. It was a no-op for 100%
    # of the rows it was written to protect, and the test that pinned it grepped this file for
    # three string literals, so it passed on that state.
    #
    # A row carrying `parameters` was written by a migration, not derived by this tool, and this
    # tool does not own it. So the DELETE now spares those rows, and a seeded measure that later
    # acquires atoms is UPDATED in place rather than deleted and reinserted -- its derived
    # columns refresh, its parameters survive.
    cur.execute(f"SELECT measure FROM {config}.derivation_catalogue WHERE parameters IS NOT NULL")
    seeded = [m for (m,) in cur.fetchall()]
    if seeded:
        cur.execute(f"DELETE FROM {config}.derivation_catalogue "
                f"WHERE NOT (measure = ANY(%s))",
                    (seeded,))
    else:
        cur.execute(f"DELETE FROM {config}.derivation_catalogue")
    for r in catalogue:
        cur.execute(f"""INSERT INTO {config}.derivation_catalogue
            (measure, input_fields, method, method_version, unit, time_specification,
             missingness_rule, earliest_supported_event_date, analytical_consumers, owner)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (measure) DO UPDATE SET
              input_fields = EXCLUDED.input_fields, method = EXCLUDED.method,
              method_version = EXCLUDED.method_version, unit = EXCLUDED.unit,
              time_specification = EXCLUDED.time_specification,
              missingness_rule = EXCLUDED.missingness_rule,
              earliest_supported_event_date = EXCLUDED.earliest_supported_event_date,
              analytical_consumers = EXCLUDED.analytical_consumers, owner = EXCLUDED.owner""",
            (r["measure"], r["input_fields"], r["method"], r["method_version"], r["unit"],
             r["time_specification"], r["missingness_rule"],
             r["earliest_supported_event_date"], r["analytical_consumers"], r["owner"]))
    if seeded:
        print(f"\n{len(seeded)} seeded row(s) preserved (they carry RULE-13 parameters this "
              f"tool does not own): " + ", ".join(sorted(seeded)))
    return seeded


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", required=True)
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args()

    from lib.db import connect
    conn = connect()
    cur = conn.cursor()
    catalogue = rows(cur, a.core)

    print(f"{len(catalogue)} measures catalogued\n")
    orphans, unknown = [], []
    for r in catalogue:
        if not r["analytical_consumers"]:
            orphans.append(r["measure"])
        if r["method"].startswith("not produced"):
            unknown.append(r["measure"])
        print(f"  {r['measure']:<30} {r['time_specification']:<9} {r['unit']:<8} "
              f"{r['atoms']:>6} atoms  consumers={len(r['analytical_consumers'])}")

    if unknown:
        print(f"\n{len(unknown)} measures have no catalogued producer "
              f"(their inputs are not known to this tool): " + ", ".join(unknown))
    if orphans:
        print(f"\n{len(orphans)} measures are named by no SQL or tool. They reach analysis "
              f"only through generic registry-driven paths, so a rename would break nothing "
              f"visibly:\n  " + ", ".join(orphans))

    if not a.commit:
        print("\nDRY RUN — nothing written. Re-run with --commit.")
        return
    write_catalogue(cur, catalogue)
    conn.commit()
    print(f"\nCOMMITTED {len(catalogue)} rows to config.derivation_catalogue")


if __name__ == "__main__":
    main()
