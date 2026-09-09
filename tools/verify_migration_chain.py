#!/usr/bin/env python3
"""Apply EVERY migration, in order, to a disposable PostgreSQL 17 server (ADR-0082).

WHY. Six migrations are written and unapplied — 0049, 0050, 0052, 0053, 0054, 0055 — and
applying them is a production write Joe authorises one at a time. The risk he is being asked
to accept is not "does this SQL parse"; it is "does this SQL parse AFTER the five before it,
against the objects they created". A file that is individually valid can still fail on the
real database because a dependency landed in a different order, and finding that out mid-apply
is the worst place to find it.

This runs the whole chain from an empty database and reports the first file that fails and the
statement that failed. It touches nothing real: the server is created, used and destroyed, TCP
is disabled, and no SUPABASE_DB_URL is read.

It is NOT a claim that production will accept them. Production carries 0001-0051 already
applied plus real rows, and this starts empty. What it proves is that the ORDER is coherent
and every object a later migration references is created by an earlier one — which is the
failure this sequence can actually have.

    python3 tools/verify_migration_chain.py
    python3 tools/verify_migration_chain.py --from 0052    # the unapplied tail only
"""
import argparse
import getpass
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pg8000.dbapi

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.run_migration import split_statements          # noqa: E402
from tools.test_local_sql import pg_bin                    # noqa: E402

CORE, OPS = "core", "ops"


def prepare(cur):
    """The prerequisites a hosted Supabase gives you and an empty server does not."""
    for role in ("anon", "authenticated", "service_role"):
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE ROLE {role}")
    for schema in ("extensions", "auth", "analysis", "config", CORE, OPS):
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions")
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions")
    # THE LEGACY PREREQUISITES. 34 `public.*` tables predate the migration chain: the old
    # stack created them and no migration file does, so the chain is NOT self-contained and
    # "apply every migration to a fresh database" is not currently a recovery path. That is a
    # finding (ADR-0088), not a workaround. The DDL is generated from the live catalog by
    # --refresh-legacy — column names and types only, no rows — so a column drift fails HERE
    # rather than inside a function under test.
    legacy = ROOT / "migrations" / "_legacy_prerequisites.sql"
    if legacy.exists():
        for statement in split_statements(legacy.read_text()):
            cur.execute(statement)

    # Supabase's JWT helper. A stand-in, declared as one: the migrations only need it to
    # exist with the right signature so their owner checks compile.
    cur.execute("""CREATE OR REPLACE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE
                   AS $$ SELECT nullif(current_setting('request.jwt.claims', true), '')::jsonb $$""")


def run(conn, first):
    cur = conn.cursor()
    cur.execute("SET search_path TO public, extensions")
    prepare(cur)
    conn.commit()

    files = sorted(ROOT.joinpath("migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if first:
        files = [f for f in files if f.name[:4] >= first]
    ok, failed = [], None
    for f in files:
        sql = f.read_text().replace("__CORE__", CORE).replace("__OPS__", OPS)
        statements = split_statements(sql)
        try:
            for s in statements:
                cur.execute(s)
            conn.commit()
            ok.append((f.name, len(statements)))
            print(f"  ok    {f.name:<40} {len(statements):>4} statements")
        except Exception as exc:
            conn.rollback()
            failed = (f.name, str(exc)[:400])
            print(f"  FAIL  {f.name}")
            print(f"        {failed[1]}")
            break
    return ok, failed


def refresh_legacy():
    """Regenerate the legacy DDL from the live catalog. Reads pg_catalog only — column names
    and types — so nothing personal leaves the database and nothing is written to it."""
    from lib.db import connect
    cur = connect().cursor()
    cur.execute("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1""")
    out = ["-- GENERATED from the live catalog by tools/verify_migration_chain.py --refresh-legacy.",
           "-- Column names and types only. No rows are read and none are written; a column name is",
           "-- not an observation. These tables predate the migration chain and no migration file",
           "-- creates them, so a rebuild from empty is impossible without them (ADR-0088).", ""]
    for (table,) in cur.fetchall():
        cur.execute("""SELECT column_name, data_type, is_nullable, column_default
                         FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = %s
                        ORDER BY ordinal_position""", (table,))
        lines = []
        for name, typ, nullable, default in cur.fetchall():
            typ = {"USER-DEFINED": "text", "ARRAY": "text[]"}.get(typ, typ)
            suffix = ""
            if default and "nextval" in str(default):
                typ, suffix = "bigint", " GENERATED BY DEFAULT AS IDENTITY"
            elif default and "gen_random_uuid" in str(default):
                suffix = " DEFAULT gen_random_uuid()"
            elif default and ("now()" in str(default) or "CURRENT_TIMESTAMP" in str(default)):
                suffix = " DEFAULT now()"
            lines.append(f'    "{name}" {typ}{suffix}{"" if nullable == "YES" else " NOT NULL"}')
        if lines:
            out.append(f"CREATE TABLE IF NOT EXISTS public.{table} (\n" + ",\n".join(lines) + "\n);")
    path = ROOT / "migrations" / "_legacy_prerequisites.sql"
    path.write_text("\n".join(out) + "\n")
    print(f"wrote {path}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="first", default=None,
                    help="start at this 4-digit prefix (e.g. 0052)")
    ap.add_argument("--refresh-legacy", action="store_true",
                    help="regenerate migrations/_legacy_prerequisites.sql from the live "
                         "catalog (column names and types only; no rows are read)")
    a = ap.parse_args()
    if a.refresh_legacy:
        return refresh_legacy()

    binaries = pg_bin()
    root = pathlib.Path(tempfile.mkdtemp(prefix="personal-os-chain-", dir="/tmp"))
    data, sockets = root / "data", root / "socket"
    sockets.mkdir(mode=0o700)
    subprocess.run([str(binaries / "initdb"), "-D", str(data), "--auth-local=trust",
                    "--auth-host=reject", "--encoding=UTF8", "--no-locale"],
                   check=True, stdout=subprocess.DEVNULL)
    control = [str(binaries / "pg_ctl"), "-D", str(data)]
    subprocess.run([*control, "-l", str(root / "server.log"), "-o",
                    f"-k {sockets} -p 55433 -c listen_addresses=''", "start"], check=True)
    try:
        conn = pg8000.dbapi.connect(user=getpass.getuser(), database="postgres",
                                    unix_sock=str(sockets / ".s.PGSQL.55433"), timeout=20)
        ok, failed = run(conn, a.first)
        conn.close()
    finally:
        stopped = subprocess.run([*control, "-m", "fast", "stop"])
        if stopped.returncode:
            raise RuntimeError(f"shutdown unproven; directory retained: {root}")
        shutil.rmtree(root)

    print()
    if failed:
        print(f"CHAIN BROKEN at {failed[0]} after {len(ok)} clean file(s).")
        return 1
    print(f"CHAIN CLEAN: {len(ok)} migrations, "
          f"{sum(n for _, n in ok)} statements, applied in order from empty.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
