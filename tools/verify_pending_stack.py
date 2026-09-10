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

PENDING = ("0056_atom_panel.sql", "0057_entities_and_merchants.sql",
           "0058_ask_two_clocks.sql", "0059_spend_by_merchant.sql",
           "0060_domain_status.sql", "0061_strength_measures.sql")
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
        failures.append(not check("1,052 legacy transactions became atoms", len(batch) == 1052,
                                  f"{len(batch)} atoms"))

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
