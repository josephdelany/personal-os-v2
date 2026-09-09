#!/usr/bin/env python3
"""B14R step 1: populate config.source_inventory from actual scans (REQ-REC-001..003).

The point of this tool is that it CANNOT be talked into a comfortable answer.

`parser_supported` is read out of `tools/importers/apple_health.py` at run time, never
taken from the seed file. The seed carries its own `parser_supported` flag, written by a
different process on a different day; when the two disagree the tool exits 1 and names the
types, because a disagreement means either the inventory or the importer is lying about
what this system can read, and both are worth stopping for.

`atoms_stored` and `observed_freshness` come from the live database, so the inventory
reconciles what a source CONTAINS against what actually landed. ADR-0025's rule holds:
reconciled, not equal — an import legitimately drops out-of-range and duplicate records,
and the delta is a number to explain, not a failure.

The seed (`_legacy_snapshot/…json`) is gitignored and stays that way: a record count is an
observation about Joe, so counts live in the database and in this process, never in Git.

Usage:
    PYTHONPATH=. python3 tools/build_inventory.py --core core            # dry run
    PYTHONPATH=. python3 tools/build_inventory.py --core core --commit
"""
import argparse
import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEED = ROOT / "_legacy_snapshot" / "data_capability_inventory_2026-09-09.json"

# The recovery window opened here (ADR-0057). `count_in_window` is relative to it.
WINDOW_FROM = dt.date(2026, 7, 1)

# REQ-REC-003. Every unparsed Apple Health type gets a disposition and an owner from THIS
# table or it gets the honest default below. Nothing is classified by guesswork about what
# a type name probably means.
#
# The distinction that matters: an implementation gap has a build unit as its owner; a
# question about whether Joe wants a measurement at all is a scope ruling and belongs to
# Joe. Assigning the second kind to a build unit would quietly convert an unasked question
# into a committed piece of work.
UNPARSED = {
    "HKQuantityTypeIdentifierBasalEnergyBurned": (
        "pending_implementation", "B18",
        "resting energy; needed with active energy for any total-expenditure measure"),
    "HKWorkoutTypeIdentifier": (
        "pending_implementation", "B18",
        "workout sessions; the importer defers these deliberately, see ADR-0059"),
    "HKQuantityTypeIdentifierDistanceCycling": (
        "pending_implementation", "B18",
        "cycling distance; a workout modality B18 already covers for walking and running"),
    "HKQuantityTypeIdentifierWalkingHeartRateAverage": (
        "pending_implementation", "B18",
        "an Apple-computed average, not a raw reading; needs a RULE-05 lane decision"),
    "HKQuantityTypeIdentifierAppleStandTime": (
        "excluded", "Joe",
        "a ring-closing metric derived from movement already captured; adds no independent "
        "observation and would compete with exercise_minutes under RULE-12"),
    "HKCategoryTypeIdentifierAppleStandHour": (
        "excluded", "Joe",
        "the hourly form of stand time; same RULE-12 objection as AppleStandTime"),
}

# REQ-REC-002. Named in historical design documents, never located. NULL counts are
# enforced by the table, which is the whole reason those documents cannot be cited as
# evidence of availability.
CONCEPT_REASON = ("named only in a historical design document; no artifact or live access "
                  "has been checked, so no count may be reported (REQ-REC-002)")

ARCHIVE_DISPOSITION = {
    "DERIVED":     ("historical_derived", "B14R",
                    "an old stack's OUTPUT, not a source record; may not be re-imported as "
                    "observation without re-deriving from its own inputs (INV-1)"),
    "EMPTY":       ("unavailable", "B14R",
                    "the archived table exists but holds no rows; nothing to import"),
    "OVERLAP":     ("duplicate", "B14R",
                    "the same originating records as another archived entity; counting both "
                    "would double-count (REQ-REC-008)"),
    "REGISTRY":    ("historical_derived", "B14R",
                    "a lookup/registry table from the old stack, superseded by config.*"),
    "OPERATIONAL": ("historical_derived", "B14R",
                    "old-stack operational bookkeeping, not an observation about Joe"),
    "ATOM":        ("pending_implementation", "B14R",
                    "raw observations from the old stack; the backfill is planned and its "
                    "row count is reconciled, not equal (ADR-0025)"),
    "ATOM_J":      ("pending_implementation", "B14R",
                    "raw observations stored as JSON columns; needs a field-level mapping "
                    "before import, per its disposition_reason"),
    "ENTITY":      ("pending_implementation", "B14",
                    "entities and links from the old stack; B14 owns entity resolution"),
}


def parser_support():
    """What the importer can ACTUALLY read, from the importer itself."""
    from tools.importers import apple_health as ah
    supported = set(ah.HK)
    supported.add(ah.SLEEP_TYPE)
    return supported, {k: v[0] if isinstance(v, (list, tuple)) else v for k, v in ah.HK.items()}


def rows_from_seed(seed, supported, metric_of, live):
    rows, disagreements, unassigned = [], [], []
    scan = "apple_health export scan 2026-09-09; start-date text bounds, not subject days"

    for rtype, info in seed["health_record_types"].items():
        is_supported = rtype in supported
        if bool(info.get("parser_supported")) != is_supported:
            disagreements.append((rtype, info.get("parser_supported"), is_supported))
        metric = metric_of.get(rtype)
        if is_supported and metric:
            disp, owner, reason = ("used", "B13",
                                   "mapped by tools/importers/apple_health.py and landing in "
                                   "core.atoms as " + metric)
        elif rtype in UNPARSED:
            disp, owner, reason = UNPARSED[rtype]
        elif is_supported:
            disp, owner, reason = ("pending_implementation", "B13",
                                   "the importer maps this type but no metric_registry key "
                                   "was resolved for it")
        else:
            # The honest default. Not an implementation gap and not an exclusion: nobody has
            # decided whether this measurement is wanted, and inventing that decision here is
            # exactly the failure this table exists to prevent.
            disp, owner, reason = ("pending_implementation", "Joe (scope ruling)",
                                   "no parser reads this type and no ruling exists on whether "
                                   "it is wanted; a scope decision, not an implementation gap")
            unassigned.append((rtype, info.get("since_2026_07_01", 0)))
        stored, fresh = live.get(metric, (None, None))
        rows.append(dict(
            source_family="apple_health", record_type=rtype,
            availability="verified_present", disposition=disp,
            disposition_reason=reason, owner=owner,
            parser_supported=is_supported, metric_key=metric if disp == "used" else None,
            record_count=info.get("count"),
            event_date_from=info.get("from"), event_date_to=info.get("to"),
            count_in_window=info.get("since_2026_07_01"),
            atoms_stored=stored, observed_freshness=fresh,
            import_status=("imported" if stored else "not imported"),
            duplicate_of=None, analytical_consumers=[], scan_method=scan))

    for a in seed["archives"]:
        disp, owner, reason = ARCHIVE_DISPOSITION.get(
            a["classification"],
            ("pending_implementation", "B14R", "classification not recognised by this tool"))
        detail = (a.get("disposition_reason") or "").strip()
        rows.append(dict(
            source_family="legacy_archive:" + a["source"], record_type=a["entity"],
            availability="verified_present", disposition=disp,
            disposition_reason=(reason + (" — " + detail if detail else "")), owner=owner,
            parser_supported=False, metric_key=None,
            record_count=a.get("rows"), event_date_from=None, event_date_to=None,
            count_in_window=None, atoms_stored=None, observed_freshness=None,
            import_status=a.get("new_core_import_status", "not verified"),
            duplicate_of=(a["entity"] if disp == "duplicate" else None),
            analytical_consumers=[],
            scan_method="archive manifest metadata only; event-date coverage requires a "
                        "parquet scan that has not been run"))

    for name in seed["concept_only_unverified"]:
        rows.append(dict(
            source_family="concept_only", record_type=name,
            availability="unverified_mentioned", disposition="pending_implementation",
            disposition_reason=CONCEPT_REASON, owner="B14R",
            parser_supported=False, metric_key=None,
            record_count=None, event_date_from=None, event_date_to=None,
            count_in_window=None, atoms_stored=None, observed_freshness=None,
            import_status="not located", duplicate_of=None, analytical_consumers=[],
            scan_method="none — this asset has not been located"))
    return rows, disagreements, unassigned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", required=True)
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args()
    if not SEED.exists():
        sys.exit(f"seed not found: {SEED}")
    seed = json.loads(SEED.read_text())

    supported, metric_of = parser_support()

    from lib.db import connect
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"""SELECT metric_key, count(*), max(subject_day)
                      FROM {a.core}.atoms WHERE metric_key IS NOT NULL GROUP BY 1""")
    live = {m: (n, d) for m, n, d in cur.fetchall()}

    rows, disagreements, unassigned = rows_from_seed(seed, supported, metric_of, live)

    if disagreements:
        print("PARSER SUPPORT DISAGREES WITH THE CODE — the inventory or the importer is wrong:")
        for rtype, claimed, actual in disagreements:
            print(f"  {rtype}: seed says {claimed}, tools/importers/apple_health.py says {actual}")
        sys.exit(1)

    counts = {}
    for r in rows:
        counts[r["disposition"]] = counts.get(r["disposition"], 0) + 1
    print(f"{len(rows)} inventory rows: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if unassigned:
        print(f"\n{len(unassigned)} Apple Health types have no scope ruling "
              f"({sum(n for _, n in unassigned)} records inside the recovery window):")
        for rtype, n in sorted(unassigned, key=lambda x: -x[1])[:12]:
            print(f"  {n:>6}  {rtype}")

    print("\nreconciliation — what the source holds inside the window vs what landed:")
    for r in rows:
        if r["disposition"] == "used" and r["count_in_window"]:
            stored = r["atoms_stored"] or 0
            d = stored - r["count_in_window"]
            flag = "" if d == 0 else f"   delta {d:+d}"
            print(f"  {r['metric_key']:<30} source {r['count_in_window']:>6}  stored {stored:>6}{flag}")

    if not a.commit:
        print("\nDRY RUN — nothing written. Re-run with --commit.")
        return
    cur.execute("DELETE FROM config.source_inventory")
    for r in rows:
        cur.execute("""INSERT INTO config.source_inventory
            (source_family, record_type, availability, disposition, disposition_reason, owner,
             parser_supported, metric_key, record_count, event_date_from, event_date_to,
             count_in_window, atoms_stored, observed_freshness, import_status, duplicate_of,
             analytical_consumers, scan_method)
            VALUES (%s,%s,%s::config.source_availability,%s::config.source_disposition,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (r["source_family"], r["record_type"], r["availability"], r["disposition"],
             r["disposition_reason"], r["owner"], r["parser_supported"], r["metric_key"],
             r["record_count"], r["event_date_from"], r["event_date_to"], r["count_in_window"],
             r["atoms_stored"], r["observed_freshness"], r["import_status"], r["duplicate_of"],
             r["analytical_consumers"], r["scan_method"]))
    conn.commit()
    print(f"\nCOMMITTED {len(rows)} rows to config.source_inventory")


if __name__ == "__main__":
    main()
