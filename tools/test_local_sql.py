#!/usr/bin/env python3
"""Run focused SQL tests in a temporary local PostgreSQL 17 server (ADR-0082).

    python3 tools/test_local_sql.py

Requires PostgreSQL binaries installed locally. No production credentials are
used by the selected tests. TCP is disabled, every fixture rolls back, and the
server is stopped before its temporary directory is removed.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
TESTS = ("tests/test_ask_ranges.py", "tests/test_ask.py", "tests/test_ask_operations.py", "tests/test_status_sql.py",
         "tests/test_status.py", "tests/test_import_drop.py",
         "tests/test_panel_attention.py",
         "tests/test_freshness.py", "tests/test_egress.py", "tests/test_ask_planner.py", "tests/test_nutrition.py",
         "tests/test_source_inventory.py",
         "tests/test_inferred_events.py",
         "tests/test_extract_workouts.py",
         "tests/test_atom_panel.py",
         "tests/test_merchants.py",
         # Added when RULE-13's parameter preservation stopped being a source-text grep and
         # became a test that runs the rebuild against a real config.derivation_catalogue.
         "tests/test_strength.py",
         # OQ-78: the location/confirmation family builds the twins by applying the whole
         # migration chain. It was gated on SUPABASE_DB_URL, so CI's `pytest` job ran that
         # chain against production and timed out (57014). It belongs here.
         "tests/test_confirmation_gate.py",
         "tests/test_movements_api.py",
         "tests/test_resolve_watches.py",
         "tests/test_derive_visits.py",
         "tests/test_restricted_location.py",
         "tests/test_recommendations.py",
         "tests/test_chains_sql.py",
         "tests/test_trials_sql.py",
         # The reconstruction path end to end: schema, engine and read API were each
         # tested and nothing ran them together.
         "tests/test_reconstruction_e2e.py",
         # INTENT_COVERAGE R7: the refusal path for an uncatalogued derivation.
         "tests/test_derivation_refusal.py",
         # B12. The nutrition cascade became the execution path; without these three lines
         # none of that evidence runs anywhere — test_nutrition_off.py's SQL half had never
         # run in CI at all, which is the same "counted but never executed" failure the
         # evidence audit found in the requirement ledger.
         "tests/test_nutrition_off.py",
         "tests/test_nutrition_integration.py",
         "tests/test_nutrition_persistence.py",
         "tests/test_ontology_constraints.py")


def pg_bin():
    located = shutil.which("initdb")
    candidates = ([str(Path(located).parent)] if located else []) + [
        "/opt/homebrew/opt/postgresql@17/bin", "/usr/local/opt/postgresql@17/bin"]
    for base in candidates:
        binary = Path(base) / "initdb"
        if binary.exists():
            version = subprocess.run([str(binary), "--version"], check=True,
                                     capture_output=True, text=True).stdout
            if re.search(r"\(PostgreSQL\) 17[. ]", version):
                return Path(base)
    raise RuntimeError("PostgreSQL 17 binaries are required; install them before running this command.")


def pytest(socket, tests):
    env = os.environ.copy()
    env.pop("SUPABASE_DB_URL", None)
    env["PERSONAL_OS_TEST_SOCKET"] = str(socket)
    return subprocess.run([sys.executable, "-m", "pytest", *tests, "-q", "--tb=short"],
                          cwd=ROOT, env=env).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, help="reuse an already-running disposable test socket")
    parser.add_argument("--tests", nargs="+", choices=TESTS, default=TESTS)
    args = parser.parse_args()
    if args.socket:
        return pytest(args.socket, args.tests)
    binaries = pg_bin()
    root = Path(tempfile.mkdtemp(prefix="personal-os-sql-", dir="/tmp"))
    data, sockets = root / "data", root / "socket"
    sockets.mkdir(mode=0o700)
    subprocess.run([str(binaries / "initdb"), "-D", str(data), "--auth-local=trust",
                    "--auth-host=reject", "--encoding=UTF8", "--no-locale"], check=True,
                   stdout=subprocess.DEVNULL)
    control = [str(binaries / "pg_ctl"), "-D", str(data)]
    try:
        # timezone=UTC because Supabase runs UTC and this server otherwise inherits the
        # developer's zone. Without it, tests that count days across a timestamptz->date cast
        # give different answers in EDT than in CI: `test_resolve_watches` reported 46 paired
        # days locally and 45 in UTC. A suite whose result depends on where the laptop is
        # cannot be evidence for anything, and CI runners are UTC, so it hid there.
        subprocess.run([*control, "-l", str(root / "server.log"), "-o",
                        f"-k {sockets} -p 55432 -c listen_addresses='' -c timezone=UTC",
                        "start"], check=True)
        return pytest(sockets / ".s.PGSQL.55432", args.tests)
    finally:
        stopped = subprocess.run([*control, "-m", "fast", "stop"])
        if stopped.returncode:
            # Retain the directory if shutdown is unproven. Never delete a live
            # server's data, including after an interrupted start/test run.
            raise RuntimeError(f"Test server shutdown unproven; directory retained: {root}")
        shutil.rmtree(root)


if __name__ == "__main__":
    sys.exit(main())
