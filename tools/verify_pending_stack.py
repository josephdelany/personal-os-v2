#!/usr/bin/env python3
"""Apply every pending change in ONE transaction, exercise the stack, roll back.

WHY THIS EXISTS. Each pending unit is verified alone: 0056 against the panel, 0057 against the
resolver, 0059 against spend, the backfill against the legacy table. None of that proves they
COMPOSE. The regression in 0061 was exactly a composition failure — two halves of one migration
landing in different schemas — and it was invisible until the whole chain ran together.

This is the integration boundary the execution plan asks for, run on the actual candidate
revision against the actual database, and it writes nothing: one transaction, always rolled
back. It is what Joe would be authorising, executed and then undone.

    PYTHONPATH=. python3 tools/verify_pending_stack.py
"""
import json
import pathlib
import sys
import uuid

from lib import db
from tools.run_migration import split_statements

# Reconciled against production on 2026-09-10 by inspecting the objects each migration
# creates, because there is no ledger table. The frontier was NOT where the checkpoint said:
# 0055 is also unapplied, so `public.get_reconstruction` — the evidence-inspection API — does
# not exist in production either. `analysis.f_daily_panel` has one argument (not 0056's two),
# `public.ask` has one and two (not 0058's three), and `public.search_record` has two (not
# 0065's three). core.inferred_events exists with 19 columns and no `inferred_inputs`.
PENDING = ("0055_get_reconstruction.sql", "0056_atom_panel.sql",
           "0057_entities_and_merchants.sql", "0058_ask_two_clocks.sql",
           "0059_spend_by_merchant.sql", "0060_domain_status.sql",
           "0061_strength_measures.sql", "0062_chains_and_roles.sql",
           "0063_micro_trials.sql", "0064_watch_wear_method.sql",
           "0065_search_reconstructions.sql", "0066_inferred_inputs.sql",
           "0067_sleep_gap_method.sql", "0068_derivation_refusal.sql")
OWNER = '{"email":"joseph.delany21@gmail.com"}'


def apply(cur, filename):
    sql = pathlib.Path("migrations", filename).read_text() \
        .replace("__CORE__", "core").replace("__OPS__", "ops")
    for statement in split_statements(sql):
        cur.execute(statement)


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  — ' + detail if detail else ''}")
    return bool(ok)


def main() -> int:
    conn = db.connect()
    cur = conn.cursor()
    failures = []
    try:
        print("=== applying the pending migrations in one transaction ===")
        for filename in PENDING:
            apply(cur, filename)
            print(f"  ok  {filename}")

        print("\n=== the transaction backfill ===")
        from tools.backfill_transactions import specs, CODE_VERSION
        from tools.import_drop import insert_atoms
        batch, _ = specs(cur)
        capture = uuid.uuid4()
        cur.execute("""INSERT INTO core.raw_captures
            (capture_id, source, captured_at, payload, trust_level)
            VALUES (%s,'legacy_archive', now(), %s,'trusted')""",
            (capture, json.dumps({"kind": "backfill", "rows": len(batch)})))
        for i in range(0, len(batch), 500):
            insert_atoms(cur, "core", capture, batch[i:i + 500], CODE_VERSION)
        # The invariant is "none dropped, none merged", not the number 1052. That constant was
        # measured once and the source has since grown to 1,053 — a real transaction, not a
        # defect — so the frozen number would fail forever for being out of date while a
        # genuine drop of 300 rows on a 1,352-row source would pass unnoticed. Comparing
        # against the live source count tests the actual rule; the floor catches a source that
        # has silently emptied, which comparing a number to itself would not.
        cur.execute("SELECT count(*) FROM public.transactions")
        source_rows = cur.fetchone()[0]
        failures.append(not check("every legacy transaction became exactly one atom",
                                  len(batch) == source_rows and source_rows > 1000,
                                  f"{len(batch)} atoms from {source_rows} legacy rows"))

        print("\n=== entities, links and categories ===")
        from tools.engines.link_merchants import plan, CODE_VERSION as LINK_V
        entities, links, counters, _ = plan(cur, "core")
        ids = {}
        for canonical, res in sorted(entities.items()):
            eid = uuid.uuid4(); ids[canonical] = eid
            cur.execute("""INSERT INTO core.entities
                (id, entity_type, canonical_name, provenance, confidence, code_version)
                VALUES (%s,'merchant',%s,%s,%s,%s)""",
                (eid, canonical,
                 "extracted" if res.merchant_source.startswith("pattern") else "inferred",
                 res.confidence, LINK_V))
        for atom_id, canonical, source, confidence in links:
            cur.execute("""INSERT INTO core.links
                (subject_atom, predicate, object_entity, provenance, confidence, code_version)
                VALUES (%s,'paid_to',%s,%s,%s,%s)""",
                (atom_id, ids[canonical],
                 "extracted" if source.startswith("pattern") else "inferred", confidence, LINK_V))
        failures.append(not check("merchant entities created", len(ids) > 50, f"{len(ids)}"))
        failures.append(not check("paid_to links created", len(links) > 500, f"{len(links)}"))

        print("\n=== invariants, with everything applied ===")
        cur.execute("""SELECT count(*) FROM core.atoms a
                        LEFT JOIN core.raw_captures r ON r.capture_id = a.raw_capture_id
                       WHERE r.capture_id IS NULL""")
        failures.append(not check("INV-1: no orphan atoms", cur.fetchone()[0] == 0))
        cur.execute("SELECT count(*) FROM core.atoms WHERE subject_day > current_date")
        failures.append(not check("RULE-04: no future-dated atoms", cur.fetchone()[0] == 0))

        print("\n=== the stack answering real questions ===")
        cur.execute("SELECT set_config('request.jwt.claims', %s, true)", (OWNER,))
        cases = [
            ("how is my steps last 30 days", "DESCRIPTIVE", None),
            ("how much did i spend at hannaford last 500 days", "DESCRIPTIVE", "resolved_merchant"),
            ("how is my hrv last 45 days", "INSUFFICIENT", None),
            ("how is my toenail length", None, None),
            ("does my alcohol affect my hrv tomorrow", None, None),
        ]
        for question, want_tier, want_method in cases:
            cur.execute("SELECT public.ask(%s, %s)", (question, "2026-09-09"))
            r = cur.fetchone()[0]
            got_tier = r.get("tier")
            method = (r.get("result") or {}).get("match_method")
            ok = got_tier == want_tier and (want_method is None or method == want_method)
            failures.append(not check(f"{question!r}", ok,
                                      f"tier={got_tier} method={method}"))

        print("\n=== reconstruction, against real production evidence ===")
        # The point of doing this HERE rather than in a unit test: this is the first time the
        # engine meets the actual atom history rather than a fixture built to suit it. Both
        # defects that reached the runner's output were of exactly that kind.
        from tools.reconstruct_run import load_method, rows_for, write as write_rec
        cur.execute("SELECT count(*) FROM config.reconstruction_methods WHERE retired_at IS NULL")
        failures.append(not check("both methods are registered (RULE-13)",
                                  cur.fetchone()[0] == 2))
        method = load_method(cur, "watch_non_wear", core="core", config="config")
        rows = rows_for(cur, method, core="core")
        written = write_rec(cur, rows, core="core")
        failures.append(not check("non-wear episodes reconstructed from real atoms",
                                  written > 0, f"{written} episodes"))
        cur.execute("""SELECT tier, count(*) FROM core.inferred_events
                        WHERE method_key = 'watch_non_wear' GROUP BY 1""")
        tiers = dict(cur.fetchall())
        # REQ-REC-008. One HealthKit export read twice is ONE origin. Any EXPLORATORY row here
        # is the corroboration-inflation defect returning.
        failures.append(not check("every episode is DESCRIPTIVE, none inflated to EXPLORATORY",
                                  set(tiers) == {"DESCRIPTIVE"}, json.dumps(tiers)))
        cur.execute("""SELECT count(*) FROM core.inferred_events
                        WHERE method_key = 'watch_non_wear' AND probability IS NOT NULL""")
        failures.append(not check("REQ-REC-010: no stored probability without a calibration",
                                  cur.fetchone()[0] == 0))

        cur.execute("SELECT public.search_record('watch non wear', 50, now())")
        hits = [h for h in cur.fetchone()[0]["hits"] if h["src"] == "inferred_events"]
        failures.append(not check("reconstructions are findable through the search path",
                                  len(hits) > 0, f"{len(hits)} hits"))
        # INV-5. A reconstruction must never render as a measurement.
        failures.append(not check("INV-5: every hit is labelled inferred",
                                  all(h.get("provenance") == "inferred" for h in hits)))
        # Inspect a stored CONCLUSION, named explicitly rather than whichever row the search
        # happened to rank first — the earlier version took hits[0] and reported "1 citation",
        # which was true of a row that should never have been stored at all.
        cur.execute("""SELECT event_id FROM core.inferred_events
                        WHERE method_key = 'watch_non_wear' AND presence = 'occurred'
                        ORDER BY subject_day LIMIT 1""")
        conclusion = cur.fetchone()
        if conclusion:
            cur.execute("SELECT public.get_reconstruction(%s)", (conclusion[0],))
            detail = cur.fetchone()[0]
            failures.append(not check("REQ-REC-012: its citations are inspectable",
                                      len(detail.get("evidence") or []) == 2,
                                      f"{len(detail.get('evidence') or [])} citations"))

        print("\n=== the R7 refusal ===")
        cur.execute("SELECT public.derivation_support('screen_hours')")
        refusal = cur.fetchone()[0]
        failures.append(not check("an uncatalogued derivation is refused, with no substitute",
                                  refusal["supported"] is False and refusal["substitute"] is None,
                                  refusal.get("reason", "")))

        print("\n=== domain readiness and the panel ===")
        cur.execute("SELECT resolution, count(*) FROM analysis.f_domain_status('2026-09-09') GROUP BY 1")
        by_state = dict(cur.fetchall())
        failures.append(not check("every domain has a readiness state",
                                  sum(by_state.values()) == 14, json.dumps(by_state)))
        cur.execute("SELECT count(*) FROM config.v_time_specification_violations")
        violations = cur.fetchone()[0]
        failures.append(not check("OQ-54 detector still reports the interval gap",
                                  violations == 5, f"{violations} measures"))

        bad = sum(1 for f in failures if f)
        print(f"\n{'STACK VERIFIED' if not bad else f'{bad} CHECK(S) FAILED'} — "
              f"{len(failures) - bad} of {len(failures)} passed")
        return 1 if bad else 0
    finally:
        conn.rollback()
        conn.close()
        print("ROLLED BACK — nothing was written.")


if __name__ == "__main__":
    sys.exit(main())
