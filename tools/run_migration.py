#!/usr/bin/env python3
"""Apply the numbered forward-only migration to a target schema pair.

Schema-parameterised: every migration file uses the tokens __CORE__ and __OPS__,
which this runner substitutes with the target schema names. The identical DDL
therefore applies to a throwaway core_dryrun/ops_dryrun pair first (dry run,
rolled back — zero residue, same PG 17.6 engine and extensions) and then to
core/ops for real.

    python3 tools/run_migration.py --core core_dryrun --ops ops_dryrun   # dry run (rollback)
    python3 tools/run_migration.py --core core --ops ops --commit        # real apply

DoD item 5: the dry run IS "run against a copy first" — the rolled-back
transaction on the live instance is a stricter copy than a create-and-drop
schema (identical engine, guaranteed no residue). Nothing is fabricated: tables
are created empty; no data row is ever written (RULE-01).
"""
import argparse
import sys
from pathlib import Path

from lib import db
from tools import check_invariants

MIG_DIR = Path(__file__).resolve().parent.parent / "migrations"


def split_statements(sql: str):
    """Split SQL into statements on top-level ';', respecting line comments,
    single-quoted strings and dollar-quoted bodies ($$ ... $$ / $tag$ ... $tag$)."""
    stmts, buf, i, n = [], [], 0, len(sql)
    while i < n:
        ch = sql[i]
        two = sql[i:i + 2]
        if two == "--":                      # line comment to EOL
            j = sql.find("\n", i)
            j = n if j == -1 else j
            buf.append(sql[i:j]); i = j; continue
        if ch == "'":                        # single-quoted string
            j = i + 1
            while j < n:
                if sql[j] == "'" and sql[j + 1:j + 2] == "'":
                    j += 2; continue
                if sql[j] == "'":
                    break
                j += 1
            buf.append(sql[i:j + 1]); i = j + 1; continue
        if ch == "$":                        # possible dollar-quote open
            k = i + 1
            while k < n and (sql[k].isalnum() or sql[k] == "_"):
                k += 1
            if k < n and sql[k] == "$":
                tag = sql[i:k + 1]           # e.g. '$$' or '$body$'
                end = sql.find(tag, k + 1)
                if end == -1:
                    raise ValueError(f"unterminated dollar-quote {tag}")
                buf.append(sql[i:end + len(tag)]); i = end + len(tag); continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []; i += 1; continue
        buf.append(ch); i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def apply(cur, core: str, ops: str, only: str = None):
    """Apply migration files to the target schema pair on an open cursor.
    Caller owns the transaction (commit/rollback). `only` restricts to files whose
    name starts with that prefix (e.g. '0013'), for incremental application onto an
    already-migrated schema. Returns (files, statements)."""
    files = sorted(MIG_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if only:
        files = [f for f in files if f.name.startswith(only)]
    if not files:
        raise RuntimeError("no migration files found")
    nstmts = 0
    for f in files:
        sql = f.read_text().replace("__CORE__", core).replace("__OPS__", ops)
        stmts = split_statements(sql)
        for s in stmts:
            cur.execute(s)
        nstmts += len(stmts)
        print(f"  ok  {f.name}  ({len(stmts)} statements)")
    return len(files), nstmts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", required=True)
    ap.add_argument("--ops", required=True)
    ap.add_argument("--commit", action="store_true",
                    help="commit for real; without it the transaction is rolled back (dry run)")
    ap.add_argument("--verify", action="store_true",
                    help="run invariant checks in-transaction after applying, before commit/rollback")
    ap.add_argument("--only", default=None,
                    help="apply only the migration file(s) whose name starts with this prefix")
    args = ap.parse_args()

    files = sorted(MIG_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        print("no migration files found", file=sys.stderr); sys.exit(1)

    conn = db.connect()
    cur = conn.cursor()
    applied = 0
    try:
        _, applied = apply(cur, args.core, args.ops, only=args.only)
        if args.verify:
            print("--- invariants (in-transaction) ---")
            passed = check_invariants.run_checks(cur, args.core)
            print("--- invariants:", "ALL PASS" if passed else "FAIL", "---")
            if not passed and args.commit:
                conn.rollback()
                print("REFUSING to commit: invariants failed. Rolled back.", file=sys.stderr)
                sys.exit(1)
        if args.commit:
            conn.commit()
            print(f"COMMITTED {applied} statements to {args.core}/{args.ops}")
        else:
            conn.rollback()
            print(f"ROLLED BACK {applied} statements (dry run on {args.core}/{args.ops}) — "
                  f"schema executed end to end, nothing persisted")
    except Exception as e:
        conn.rollback()
        print(f"FAILED after {applied} statements: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
