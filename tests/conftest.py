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
