#!/usr/bin/env python3
"""CI invariant checks for the Phase-2 spine. Named with the rule IDs they cover.

Runs either standalone against a committed schema:
    python3 tools/check_invariants.py --core core
or in-transaction from run_migration.py --verify (on the rolled-back dry-run copy).

RULE-01 SAFETY: no check ever inserts a row. Append-only enforcement is proven by
attempting an UPDATE/DELETE as a non-owner app role (service_role), which Postgres
rejects at the table-privilege check *before* any row is processed — so it works on
an empty table and fabricates nothing. Each probe is wrapped in a SAVEPOINT so the
expected error does not abort the surrounding transaction.
"""
import argparse
import sys

from lib import db

APP_ROLES = ("anon", "authenticated", "service_role")


def _probe_denied(cur, sql):
    """Run sql expecting a privilege error; return (denied, message). Savepoint-guarded."""
    cur.execute("SAVEPOINT p")
    try:
        cur.execute(sql)
        cur.execute("ROLLBACK TO SAVEPOINT p")
        return False, "NO ERROR (mutation was allowed)"
    except Exception as e:
        cur.execute("ROLLBACK TO SAVEPOINT p")
        return True, f"{type(e).__name__}: {str(e).splitlines()[0][:120]}"


def run_checks(cur, core: str):
    ok = True

    # ---- RULE-02 (grant level): no app role holds UPDATE/DELETE on the append-only
    # tables. Owner's implicit self-grant is excluded per ADR-0010 (not revocable;
    # the trigger is its backstop; Joe ratified the app-role scoping 2026-08-23).
    # NOTE (review m4): the constitution's RULE-02 query is schema-agnostic (it would
    # flag a stray public.atoms too); this adds `table_schema = %s` so the same
    # check can run against a throwaway dry-run schema. For the live check
    # (core), the two are equivalent because only `core` holds tables named
    # atoms/raw_captures.
    cur.execute(
        """select grantee, privilege_type
             from information_schema.role_table_grants
            where table_schema = %s and table_name in ('atoms','raw_captures')
              and privilege_type in ('UPDATE','DELETE')
              and grantee = any(%s)""",
        (core, list(APP_ROLES)),
    )
    bad = cur.fetchall()
    print(f"[RULE-02 grants] app-role UPDATE/DELETE grants on atoms/raw_captures: "
          f"{len(bad)} (must be 0)")
    for g in bad:
        print(f"    !! {g[0]} has {g[1]}")
    ok = ok and len(bad) == 0

    # ---- RULE-02 GRANT path: a non-owner app role (service_role) is refused at the
    # table-privilege check ("permission denied for table ...") — before any row is
    # touched, so this needs no fabricated row (RULE-01).
    for tbl, col in (("atoms", "code_version"), ("raw_captures", "last_error")):
        cur.execute("SAVEPOINT r")
        cur.execute("SET ROLE service_role")
        du, mu = _probe_denied(cur, f"UPDATE {core}.{tbl} SET {col}='x'")
        dd, md = _probe_denied(cur, f"DELETE FROM {core}.{tbl}")
        cur.execute("ROLLBACK TO SAVEPOINT r")   # also resets ROLE
        grant_ok = du and "permission denied" in mu and dd and "permission denied" in md
        print(f"[RULE-02 grant] service_role on {core}.{tbl}: UPDATE {mu}; DELETE {md} "
              f"-> {'OK' if grant_ok else 'FAIL'}")
        ok = ok and grant_ok

    # ---- RULE-02 TRIGGER path: the OWNER (whose grant cannot be revoked) is refused
    # by the statement-level append-only trigger, which fires even on an empty table.
    # This is the only mechanism that stops the Phase-2 ETL identity (postgres), and
    # it is proven behaviourally here without any fabricated row.
    for tbl, col in (("atoms", "code_version"), ("raw_captures", "last_error")):
        du, mu = _probe_denied(cur, f"UPDATE {core}.{tbl} SET {col}='x'")
        dd, md = _probe_denied(cur, f"DELETE FROM {core}.{tbl}")
        trig_ok = du and "RULE-02" in mu and dd and "RULE-02" in md
        print(f"[RULE-02 trigger] owner on {core}.{tbl}: UPDATE {mu}; DELETE {md} "
              f"-> {'OK' if trig_ok else 'FAIL'}")
        ok = ok and trig_ok

    # ---- append-only triggers present (ADR-0010)
    cur.execute(
        """select c.relname, t.tgname
             from pg_trigger t join pg_class c on c.oid=t.tgrelid
             join pg_namespace n on n.oid=c.relnamespace
            where n.nspname=%s and not t.tgisinternal order by 1,2""",
        (core,),
    )
    trigs = {(r[0], r[1]) for r in cur.fetchall()}
    for want in [("atoms", "atoms_append_only"),
                 ("raw_captures", "raw_captures_append_only"),
                 ("hypothesis_register", "hypothesis_register_freeze")]:
        present = want in trigs
        print(f"[ADR-0010 trigger] {want[1]} on {want[0]}: {'present' if present else 'MISSING'}")
        ok = ok and present

    # ---- RULE-04 (point-in-time): references derived_measures, a Phase-5 table.
    cur.execute("select to_regclass(%s)", (f"{core}.derived_measures",))
    dm = cur.fetchone()[0]
    if dm is None:
        print("[RULE-04] PENDING — derived_measures does not exist yet (Phase 5); "
              "point-in-time query cannot run. Not a failure this phase.")
    else:
        cur.execute(
            f"""select count(*) from {core}.derived_measures d
                 join {core}.atoms a on a.id = any(d.source_atom_ids)
                where a.recorded_at > d.window_end""")
        n = cur.fetchone()[0]
        print(f"[RULE-04] rows recorded after window close: {n} (must be 0)")
        ok = ok and n == 0

    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", required=True)
    args = ap.parse_args()
    conn = db.connect()
    cur = conn.cursor()
    try:
        ok = run_checks(cur, args.core)
    finally:
        conn.rollback()
        conn.close()
    print("\nINVARIANTS:", "ALL PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
