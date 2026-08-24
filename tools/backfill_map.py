#!/usr/bin/env python3
"""Legacy-archive -> atoms backfill MAP and reconciliation (Phase 2, Gate 2).

PLAN AND AUDIT ONLY. This script reads nothing but the two archive manifests and
prints the disposition of every archived table. It writes no atom, touches no
database, and executes no backfill. It exists so the Gate-2 reconciliation is
re-runnable and auditable rather than asserted once in prose (ADR-0025).

Gate 2 says "backfilled row count matches the Parquet archive." Taken as equality
that is impossible without violating the constitution: ~23% of archived rows are the
OLD STACK's derived outputs (making them atoms fabricates raw_captures lineage they
never had — INV-1; stores inferred values as observed — INV-5, RULE-01), cross-archive
duplicates (double-counting the same facts), reference data (-> entities/registry), or
empty tables. So "match" means RECONCILIATION: every archived row is either mapped to
an atom OR explicitly excluded with a recorded reason, and the per-table sums are exact.
This script proves the sums are exact (they total 810,933).

    python3 tools/backfill_map.py          # summary + reconciliation check
    python3 tools/backfill_map.py --md     # full per-table markdown table

Requires the archive manifests under _legacy_snapshot/ (gitignored; present locally).
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SUP = ROOT / "_legacy_snapshot" / "supabase_manifest.json"
LOC = ROOT / "_legacy_snapshot" / "manifest.json"

# disposition: entity -> (bucket, target_or_reason)
# buckets, in reconciliation order:
#   ATOM        maps to exactly one atoms.kind, no judgement
#   ATOM_J      is an atom but needs a schema split or a kind boundary call
#   OVERLAP     the same facts as another archive snapshot (exclude the duplicate)
#   ENTITY      reference -> core.entities (Phase 4), not an atom
#   REGISTRY    reference -> metric_registry / category reference, not an atom
#   DERIVED     old-stack INFERENCE/output; no raw_captures lineage (INV-1/INV-5)
#   OPERATIONAL ingest status / prompt queue; not an observation
#   EMPTY       0 rows — nothing to backfill regardless of class
D = {
    # ---- Supabase (public) ----
    "locations":              ("ATOM", "location_fix"),
    "checkins":               ("ATOM_J", "self_report (+ spec-cited mood) — split by metric"),
    "intraday":               ("ATOM_J", "activity_sample (11 cols, multi-metric split; some vital_sample)"),
    "events":                 ("ATOM_J", "mixed raw event stream — per-type split needed"),
    "transactions":           ("ATOM_J", "transaction — canonical of 3 tx snapshots"),
    "content_taxonomy":       ("ENTITY", "media_channel"),
    "merchant_taxonomy":      ("ENTITY", "merchant"),
    "place_book":             ("ENTITY", "place"),
    "entities":               ("ENTITY", "old entity table -> Phase-4 resolution"),
    "entity_occurrences":     ("ENTITY", "entity<->event links -> Phase-4"),
    "category_map":           ("REGISTRY", "finance category reference"),
    "metric_catalog":         ("REGISTRY", "-> metric_registry"),
    "signals":                ("DERIVED", "old-stack computed signals"),
    "insights":               ("DERIVED", "old-stack output"),
    "insights_catalog":       ("DERIVED", "old-stack output"),
    "validated_insights":     ("DERIVED", "old-stack output"),
    "hypotheses":             ("DERIVED", "old-stack output (Phase-6 re-authored fresh)"),
    "inferred_events":        ("DERIVED", "old-stack INFERRED (INV-5)"),
    "coach_recommendations":  ("DERIVED", "old-stack output"),
    "forecast_log":           ("DERIVED", "old-stack output"),
    "graph_structures":       ("DERIVED", "old-stack output"),
    "day_narratives":         ("DERIVED", "old-stack narrative output"),
    "briefs":                 ("DERIVED", "old-stack output"),
    "confrontations":         ("DERIVED", "old-stack output"),
    "experiments":            ("DERIVED", "old-stack experiment defs"),
    "goals":                  ("DERIVED", "old-stack goals"),
    "ask_threads":            ("DERIVED", "old-stack chat"),
    "checkin_probes":         ("OPERATIONAL", "prompt dispatch -> not atoms"),
    "ingest_status":          ("OPERATIONAL", "pipeline status"),
    "checkin_probe_queue":    ("EMPTY", "0 rows"),
    "context_facts":          ("EMPTY", "context_fact kind, 0 rows"),
    "experiment_assignments": ("EMPTY", "0 rows"),
    "reconcile_queue":        ("EMPTY", "0 rows"),
    "workouts":               ("EMPTY", "0 rows (OQ-18: strength unmeasured)"),
    # ---- Local: personal_os.db ----
    "pos__body_composition":  ("ATOM", "body_measurement"),
    "pos__calendar_events":   ("ATOM", "calendar_event"),
    "pos__chrome_history":    ("ATOM", "web_visit (+website entity)"),
    "pos__youtube_history":   ("ATOM", "media_play (+media_channel entity)"),
    "pos__daily_health":      ("ATOM_J", "env_db/headphone_db cols -> environment_sample; rollups are derived"),
    "pos__spend_transactions":("OVERLAP", "transaction dup of supabase.transactions"),
    "pos__anomalies":         ("DERIVED", "old-stack output"),
    "pos__baselines":         ("DERIVED", "computed baselines"),
    "pos__mood_log":          ("EMPTY", "mood, 0 rows"),
    # ---- Local: health_raw.sqlite ----
    "health__hr_samples":     ("ATOM", "vital_sample"),
    "health__hrv_windows":    ("ATOM", "heart_rate_variability"),
    "health__resp_rate":      ("ATOM", "vital_sample"),
    "health__rhr":            ("ATOM", "vital_sample"),
    "health__spo2":           ("ATOM", "vital_sample"),
    "health__wrist_temp":     ("ATOM", "vital_sample"),
    "health__walking_hr":     ("ATOM", "vital_sample"),
    "health__sleep_intervals":("ATOM", "sleep"),
    "health__vo2max":         ("ATOM_J", "vital_sample vs derived measure"),
    "health__walking_asymmetry":     ("ATOM_J", "gait -> vital_sample or activity_sample"),
    "health__walking_double_support":("ATOM_J", "gait"),
    "health__walking_speed":         ("ATOM_J", "gait"),
    "health__walking_steadiness":    ("ATOM_J", "gait"),
    "health__walking_step_length":   ("ATOM_J", "gait"),
    # ---- Local: backup_2026-07-17/csv ----
    # Uniform rule: a csv-backup / pos__ table that duplicates a canonical Supabase table
    # is OVERLAP (excluded as a duplicate), classified by WHAT IT DUPLICATES, not by the
    # canonical's own nature — so csv__insights/csv__ingest_status are OVERLAP, not
    # DERIVED/OPERATIONAL (reviewer m3).
    "csv__events":            ("OVERLAP", "older snapshot of supabase.events"),
    "csv__transactions":      ("OVERLAP", "dup of supabase.transactions"),
    "csv__signals":           ("OVERLAP", "dup of supabase.signals (derived)"),
    "csv__insights":          ("OVERLAP", "dup of supabase.insights (derived)"),
    "csv__ingest_status":     ("OVERLAP", "dup of supabase.ingest_status (operational)"),
    "csv__workouts":          ("EMPTY", "empty file / parse error"),
}

ORDER = ["ATOM", "ATOM_J", "OVERLAP", "ENTITY", "REGISTRY", "DERIVED", "OPERATIONAL", "EMPTY"]
ATOM_BUCKETS = {"ATOM", "ATOM_J"}


def rows(rec):
    return rec.get("rows_source") or 0


def load():
    if not SUP.exists() or not LOC.exists():
        sys.exit("archive manifests not found under _legacy_snapshot/ (gitignored; run where the archive lives)")
    recs = []
    for rec in json.loads(SUP.read_text()):
        recs.append(("supabase", rec["entity"], rows(rec)))
    for rec in json.loads(LOC.read_text()):
        src = rec["source"].split("/")[0]
        recs.append((src, rec["entity"], rows(rec)))
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", action="store_true", help="print the full per-table markdown table")
    args = ap.parse_args()
    recs = load()

    unknown = [e for _, e, _ in recs if e not in D]
    if unknown:
        sys.exit(f"disposition missing for: {unknown} — update tools/backfill_map.py")

    buckets = {b: [0, 0] for b in ORDER}
    total = 0
    for _, e, n in recs:
        b, _t = D[e]
        buckets[b][0] += 1
        buckets[b][1] += n
        total += n

    if args.md:
        print("| source | table | rows | bucket | target / reason |")
        print("|---|---|--:|---|---|")
        rank = {b: i for i, b in enumerate(ORDER)}
        for src, e, n in sorted(recs, key=lambda r: (rank[D[r[1]][0]], -r[2])):
            b, t = D[e]
            print(f"| {src} | `{e}` | {n:,} | {b} | {t} |")
        print()

    print(f"tables: {len(recs)}   grand total rows: {total:,}")
    print(f"{'bucket':<12}{'tables':>7}{'rows':>12}")
    gt = gr = 0
    for b in ORDER:
        t, r = buckets[b]
        gt += t
        gr += r
        print(f"{b:<12}{t:>7}{r:>12,}")
    print(f"{'--sum--':<12}{gt:>7}{gr:>12,}")

    atom_rows = sum(buckets[b][1] for b in ATOM_BUCKETS)
    print()
    print(f"UPPER BOUND on atom-eligible rows (ATOM + ATOM_J): {atom_rows:,}")
    print("  (an upper bound only: `intraday` fans OUT to many atoms per row, while")
    print("   `events` sub-types and `pos__daily_health` rollups drop OUT — the true")
    print("   atom count is knowable only after the per-metric split is written)")
    print(f"explicitly excluded, with a recorded reason:      {gr - atom_rows:,}")

    assert gr == total, "reconciliation failure: buckets do not sum to the archive total"
    assert gt == len(recs)
    print("\nRECONCILIATION OK — every archived table is accounted for.")


if __name__ == "__main__":
    main()
