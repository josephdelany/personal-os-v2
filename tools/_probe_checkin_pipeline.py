"""End-to-end rolled-back proof of the check-in pipeline (ADR-0035).
One transaction: apply migrations 0001..0020 to disposable schemas (0020's one-time
mirror reads the REAL public.checkins rows into core_dryrun.raw_captures — real data,
disposable destination), run the deterministic extraction, verify the atoms + all
invariants, then ROLL BACK. Nothing persists (RULE-01)."""
import sys
from lib import db
from tools import run_migration, check_invariants
from tools.extract_checkins import extract

conn = db.connect(); cur = conn.cursor()
try:
    run_migration.apply(cur, "core_dryrun", "ops_dryrun")
    cur.execute("select count(*) from core_dryrun.raw_captures where payload->>'kind'='checkin'")
    n_caps = cur.fetchone()[0]
    print(f"(1) real check-ins mirrored into disposable captures: {n_caps}")

    made, n, skipped = extract(cur, "core_dryrun")
    print(f"(2) extraction: {made} atoms from {n} captures ({skipped} skipped)")

    cur.execute("""select a.metric_key, a.value_low, a.value_point, a.value_high,
                          a.estimate_method, a.subject_day, a.presence
                     from core_dryrun.atoms a where a.kind='self_report' order by a.occurred_at, a.metric_key""")
    for r in cur.fetchall():
        print(f"    {r[0]:32} [{r[1]}..{r[2]}..{r[3]}] {r[4]:12} day={r[5]} {r[6]}")
    cur.execute("select count(*) from core_dryrun.atoms where kind='note'")
    print(f"    note atoms: {cur.fetchone()[0]}")

    made2, n2, _ = extract(cur, "core_dryrun")
    print(f"(3) idempotency re-run: {made2} new atoms from {n2} captures (must be 0/0)")

    # food path: a fixture capture into the DISPOSABLE schema only (RULE-01 bounded
    # exception: rolled back, never committed, never read as data)
    cur.execute("""insert into core_dryrun.raw_captures
                     (capture_id, captured_at, source, trust_level, payload)
                   values (gen_random_uuid(), now(), 'shortcut_text', 'trusted',
                           '{"kind":"food","text":"big mac, large coke"}'::jsonb)""")
    made3, _, _ = extract(cur, "core_dryrun")
    cur.execute("""select evidence_span, kind, presence, time_precision
                     from core_dryrun.atoms where kind='consume' order by evidence_span""")
    food_atoms = cur.fetchall()
    for r in food_atoms:
        print(f"    consume: {r[0]!r} {r[2]} precision={r[3]}")
    print(f"(3b) food capture -> {made3} consume atoms (must be 2, no values invented)")

    # workout + health fixtures (disposable schema, rolled back)
    cur.execute("""insert into core_dryrun.raw_captures
                     (capture_id, captured_at, source, trust_level, payload)
                   values (gen_random_uuid(), now(), 'shortcut_text', 'trusted',
                           '{"kind":"workout","exercise":"bench press","weight_lb":"185","reps":"8","rpe":"7.5"}'::jsonb),
                          (gen_random_uuid(), now(), 'shortcut_text', 'trusted',
                           '{"kind":"health","samples":[{"metric":"steps","value":9432},{"metric":"resting_hr","value":58},{"metric":"nonsense","value":1}]}'::jsonb)""")
    made4, _, _ = extract(cur, "core_dryrun")
    cur.execute("""select kind, metric_key, value_point, estimate_method, evidence_span
                     from core_dryrun.atoms where kind in ('workout','activity_sample','vital_sample')
                    order by metric_key""")
    for r in cur.fetchall(): print(f"    {r[0]:16} {r[1]:18} {r[2]} ({r[3]}) '{r[4]}'")
    print(f"(3c) workout+health -> {made4} atoms (must be 5: 3 set attrs + 2 samples; 'nonsense' skipped)")
    cur.execute("select count(*) from core_dryrun.atoms where kind='consume' and value_point is not null")
    no_invented = cur.fetchone()[0] == 0

    print("(4) invariants in-transaction:")
    ok = check_invariants.run_checks(cur, "core_dryrun")
    good = n_caps >= 3 and made > 0 and made2 == 0 and made3 == 2 and made4 == 5 and no_invented and ok
    print("PROBE:", "ALL PASS" if good else "FAIL")
    sys.exit(0 if good else 1)
finally:
    conn.rollback(); conn.close()
    print("rolled back — nothing persisted")
