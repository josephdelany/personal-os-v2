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
TESTS = ("tests/test_v1_health_flow.py", "tests/test_v1_activation_check.py", "tests/test_v0_location.py", "tests/test_v0_card_store.py", "tests/test_v0_day.py", "tests/test_v0_workouts.py", "tests/test_v0_meals.py", "tests/test_v0_checkins.py", "tests/test_capture_runtime.py", "tests/test_capture_model_recovery.py", "tests/test_capture_reference.py", "tests/test_reference_dispatch_sql.py", "tests/test_capture_media_receipts.py", "tests/test_capture_transcription.py", "tests/test_ask_jobs.py", "tests/test_model_reservations.py", "tests/test_capture_processing.py", "tests/test_capture_ingress_sql.py", "tests/test_ask_ranges.py", "tests/test_ask.py", "tests/test_ask_operations.py", "tests/test_status_sql.py",
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
         # Spine: applies the chain to a throwaway schema pair. Also OQ-78 casualties.
         "tests/test_spine_invariants.py",
         "tests/test_spine_insert_paths.py",
         # REQ-NFR-008 was guarded for the disposable server but listed in no job, so it
         # could not run anywhere: a requirement unprovable by construction.
         "tests/test_capture_schedule.py",
         "tests/test_keepalive.py",
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
         # 30 of its 59 tests CREATE SCHEMA and build 0050 in disposable schemas, so this is
         # the only job that may run them. Unregistered they skipped in every environment and
         # counted as nothing -- the "counted but never executed" failure again, this time
         # caught by the worker who wrote them rather than by an audit.
         "tests/test_nutrition_usda.py",
         # B12 §E.3/§G.1. The read side: `nutrition_display` had no caller, and these enter
         # through `tools/nutrition_day.py:main()` against stored atoms. Registered in the same
         # commit that adds them — an unregistered socket-gated file skips everywhere and
         # counts as nothing, which is how the previous one nearly shipped.
         "tests/test_nutrition_day.py",
         "tests/test_ontology_constraints.py",
         # INTENT_COVERAGE R2: the recorded training history. The importer discarded every
         # `<Workout>` element, so these had nowhere to run before 0070.
         "tests/test_workout_session_r2.py",
         # INTENT_COVERAGE R4: an outage is not proof of nonuse. Enters through
         # tools/service_usage.py, which is the first caller recurrence.py and
         # usage_status.py have ever had.
         "tests/test_service_usage_r4.py",
         # REQ-REC-015's second half (ADR-0141). Its pure decision tests run anywhere; the
         # queries that feed them -- which reconstruction is still open, what has already been
         # asked -- only run against a real schema, and a test that runs in no job is the
         # "counted but never executed" failure the evidence audit found in the ledger.
         "tests/test_clarification_prompts.py")


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


def pytest(socket, tests, junitxml=None):
    env = os.environ.copy()
    env.pop("SUPABASE_DB_URL", None)
    env["PERSONAL_OS_TEST_SOCKET"] = str(socket)
    # This job installs its own dependency set, so a library missing HERE is a hole in the
    # evidence exactly as it is in the `pytest` job -- not a tolerable local condition. Skips
    # about absent DATA are untouched; no package installs a row. Caller may override.
    env.setdefault("PERSONAL_OS_REQUIRE_DEPS", "1")
    cmd = [sys.executable, "-m", "pytest", *tests, "-q", "--tb=short"]
    if junitxml:
        # Without this the disposable suite produced NO machine-readable result, so the
        # two-report merge tools/evidence_report.py is built around could only ever be assembled
        # by hand on a developer machine. Half the evidence had no artifact.
        cmd.append(f"--junitxml={junitxml}")
    return subprocess.run(cmd, cwd=ROOT, env=env).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, help="reuse an already-running disposable test socket")
    parser.add_argument("--tests", nargs="+", choices=TESTS, default=TESTS)
    parser.add_argument("--junitxml", default=None,
                        help="write a pytest JUnit report here (feeds tools/evidence_report.py)")
    args = parser.parse_args()
    if args.socket:
        return pytest(args.socket, args.tests, args.junitxml)
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
        return pytest(sockets / ".s.PGSQL.55432", args.tests, args.junitxml)
    finally:
        stopped = subprocess.run([*control, "-m", "fast", "stop"])
        if stopped.returncode:
            # Retain the directory if shutdown is unproven. Never delete a live
            # server's data, including after an interrupted start/test run.
            raise RuntimeError(f"Test server shutdown unproven; directory retained: {root}")
        shutil.rmtree(root)


if __name__ == "__main__":
    sys.exit(main())
