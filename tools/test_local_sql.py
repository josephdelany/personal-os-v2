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
         "tests/test_freshness.py", "tests/test_egress.py", "tests/test_ask_planner.py", "tests/test_nutrition.py")


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
        subprocess.run([*control, "-l", str(root / "server.log"), "-o",
                        f"-k {sockets} -p 55432 -c listen_addresses=''", "start"], check=True)
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
