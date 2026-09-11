"""A skipped test is not a passing test.

An independent audit found that the NumPyro tests could skip while the workflow that was
supposed to prove them never installed their dependencies — so the requirement they cover was
counted as satisfied by a test that had never run anywhere. That is the failure mode this file
closes: in CI, a test that steps aside because a LIBRARY IS MISSING is a failure, because the
whole job of CI is to be the environment where nothing is missing.

Skips that are about DATA are left alone. "No transactions today" is a true statement about the
world and a test that asserts nothing about an empty table is correct to stand down; installing
a package cannot fix it. The two cases are distinguished by an explicit marker rather than by
guessing at prose, so a new skip has to declare which kind it is.
"""
import os
import sys
import time

import pytest

# A skip reason starting with this marker asserts: "this environment lacks a dependency". CI
# sets PERSONAL_OS_REQUIRE_DEPS=1 and such a skip becomes a failure there.
MISSING_DEPENDENCY = "MISSING DEPENDENCY:"


def dependency_skip(package, detail=""):
    """Skip because `package` is not importable — and fail instead when CI says it must be."""
    reason = f"{MISSING_DEPENDENCY} {package}" + (f" ({detail})" if detail else "")
    if os.environ.get("PERSONAL_OS_REQUIRE_DEPS") == "1":
        pytest.fail(f"{reason} — required in this environment, so a skip here would hide an "
                    f"unproven requirement (install it in .github/workflows/tests.yml)")
    pytest.skip(reason)


@pytest.hookimpl(trylast=True)
def pytest_report_header(config):
    if os.environ.get("PERSONAL_OS_REQUIRE_DEPS") == "1":
        return "PERSONAL_OS_REQUIRE_DEPS=1: a missing-dependency skip fails instead of skipping"
    return None


def pytest_terminal_summary(terminalreporter):
    """Print the dependency skips at the end, so they are visible even where they are allowed.

    A skip buried in a field of dots is a skip nobody reads. Locally these are legitimate — the
    default interpreter here is 3.14 — but they must still be nameable at a glance.
    """
    skipped = [r for r in terminalreporter.stats.get("skipped", [])
               if MISSING_DEPENDENCY in str(getattr(r, "longrepr", ""))]
    if not skipped:
        return
    terminalreporter.write_sep("-", "tests skipped for a missing dependency")
    for r in skipped:
        reason = str(r.longrepr[2]) if isinstance(r.longrepr, tuple) else str(r.longrepr)
        terminalreporter.write_line(f"  {r.nodeid}\n      {reason.strip()}")


@pytest.fixture(scope="session", autouse=True)
def _record_run_environment(record_testsuite_property):
    """Stamp the RUN's environment into the JUnit report itself.

    tools/evidence_manifest.py otherwise had to describe the run by inspecting its own process,
    which is a different process with a different environment: it reported `require_deps=False`
    and `tz=EST` for a suite that had actually run with PERSONAL_OS_REQUIRE_DEPS=1 against a
    server pinned to UTC. Recording it here puts the fact in the artifact that outlives the run,
    which is the only place it stays true.

    Never the database URL or host — the mode name and a boolean only.
    """
    socket = os.environ.get("PERSONAL_OS_TEST_SOCKET")
    live = bool(os.environ.get("SUPABASE_DB_URL"))
    record_testsuite_property(
        "personal_os_database_mode",
        "disposable" if socket else ("live" if live else "none"))
    record_testsuite_property("personal_os_require_deps",
                              str(os.environ.get("PERSONAL_OS_REQUIRE_DEPS") == "1"))
    record_testsuite_property("personal_os_production_checks",
                              str(os.environ.get("PERSONAL_OS_PRODUCTION_CHECKS") == "1"))
    record_testsuite_property("personal_os_tz", time.tzname[0])
    record_testsuite_property("personal_os_python", sys.version.split()[0])
