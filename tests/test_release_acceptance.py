"""Acceptance checks that start the real entry points and fail if the wiring is removed.

WHY THIS FILE EXISTS. The evidence audit's third finding was that 30 of 33 engine modules had
no non-test caller: their tests passed, and passing proved the arithmetic, not that anything in
the running system ever called them. `tools/evidence_report.py` reports that as a reachability
column, but reporting a number is not the same as defending it. Nothing failed when a module
fell out of the reachable set — the number simply moved, and a number that only moves is a
number nobody notices.

These checks fail instead.

They are deliberately NOT a re-implementation of the reachability report. That tool answers
"what fraction is reachable?" across everything. This file answers "are these specific
capabilities still wired?" for the engines that a scheduled job is supposed to start, and it
answers it by starting the actual scripts.

WHAT "INVOKE" MEANS HERE, AND WHAT IT DOES NOT PROVE. Each entry point is run as a subprocess
with no database reachable. That exercises the real `if __name__ == "__main__"` path and loads
the script's entire import closure, so a renamed engine, a deleted import or a syntax error is
a failure here. It stops at the database boundary, which is the point: this is a statement
about INTEGRATION, not about deployment or observation. A passing check here says the nightly
job would reach the engine. It does not say the job ran, that a row landed, or that Joe ever
saw the number — those are levels 5 and 6 of the ladder and no test in this repository
establishes them.

No database, no network, no credential: the subprocesses are given an environment with
SUPABASE_DB_URL removed.
"""
import os
import pathlib
import subprocess
import sys

import pytest

from tools import evidence_report as er

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The engines a scheduled workflow is supposed to start, pinned by name. This list is the
# assertion: if wiring is removed, the engine drops out of the scheduled closure and the check
# fails rather than quietly lowering a percentage. Adding an engine here is a claim that some
# workflow starts something that imports it, and the test immediately checks that claim.
REQUIRED_SCHEDULED_ENGINES = (
    "tools.engines.baselines",
    "tools.engines.confirm",
    "tools.engines.forecast",
    "tools.engines.panel",
    "tools.engines.recommend",
    "tools.engines.reconstruct",
    "tools.engines.resolve",
    "tools.engines.scan",
    "tools.engines.speccurve",
)

# Scripts a workflow or RUN_TONIGHT.sh actually starts, each the front door of one capability.
REQUIRED_ENTRY_POINTS = (
    "tools/run_analysis.py",
    "tools/run_confirm.py",
    "tools/run_recommend.py",
    "tools/run_resolve.py",
    "tools/run_scan.py",
    "tools/reconstruct_run.py",
    "tools/check_freshness.py",
)

# A failure mode that means the wiring is broken, as opposed to the database simply being
# absent. These are the words that appear when an import closure does not load.
BROKEN_WIRING = ("ModuleNotFoundError", "ImportError", "SyntaxError", "NameError",
                 "AttributeError", "IndentationError")

# Reaching this text means the script got all the way to the database and stopped there, which
# is exactly as far as an acceptance check without a database can go.
DATABASE_BOUNDARY = ("SUPABASE_DB_URL", "no database", "could not connect", "connection")


def _no_database_env():
    env = os.environ.copy()
    env.pop("SUPABASE_DB_URL", None)          # never let an acceptance check touch production
    env.pop("PERSONAL_OS_TEST_SOCKET", None)
    env["PYTHONPATH"] = str(ROOT)
    return env


@pytest.fixture(scope="module")
def reach():
    labels, edges, seeds = er.module_reach(ROOT)
    return labels, edges, set(seeds)


@pytest.mark.parametrize("engine", REQUIRED_SCHEDULED_ENGINES)
def test_ADR_0136_required_engine_is_reachable_from_a_scheduled_entry_point(engine, reach):
    """The engine is in the import closure of a script some workflow starts.

    Fails if the workflow step is deleted, if the runner stops importing the engine, or if the
    engine is renamed without updating its caller — the three ways integration disappears
    without anything else going red.
    """
    labels, _edges, _seeds = reach
    assert engine in labels, (
        f"{engine} is not a module this repository contains any more. If it was renamed, "
        f"update REQUIRED_SCHEDULED_ENGINES; if it was deleted, the capability went with it."
    )
    assert labels[engine] == "scheduled", (
        f"{engine} is '{labels[engine]}', not 'scheduled'. Nothing a workflow starts imports "
        f"it any more, so whatever its own tests prove, no job runs it. This is the gap between "
        f"'tested' and 'works' the evidence audit found, and it is now a failure."
    )


@pytest.mark.parametrize("script", REQUIRED_ENTRY_POINTS)
def test_ADR_0136_entry_point_exists_and_is_named_by_the_automation(script, reach):
    """The file is on disk AND some workflow or RUN_TONIGHT.sh names it.

    A script that exists but nothing schedules is not an entry point — that distinction is the
    whole reason `evidence_report.entry_points` does not accept a `__main__` block as evidence.
    """
    _labels, _edges, seeds = reach
    assert (ROOT / script).exists(), f"{script} does not exist"
    module = ".".join(pathlib.Path(script).with_suffix("").parts)
    assert module in seeds, (
        f"{script} exists but no workflow and no RUN_TONIGHT.sh line names it. It is a script "
        f"someone can run by hand, which is not the same as a capability the system has."
    )


@pytest.mark.parametrize("script", REQUIRED_ENTRY_POINTS)
def test_ADR_0136_entry_point_starts_and_loads_its_whole_import_closure(script):
    """Actually run it, with no database, and require that it fail only at the database.

    This is the check that would not survive the integration being removed: the subprocess
    executes the real `__main__` path, so every module the script imports must load. A broken
    import is indistinguishable from a missing capability at runtime, and both fail here.

    Two acceptable outcomes: the script parses `--help` and exits, or it reaches `db.connect()`
    and reports that SUPABASE_DB_URL is unset. `tools/run_analysis.py` takes the second path —
    it ignores argv entirely — and that is recorded rather than corrected, because this file
    does not own the runtime scripts.
    """
    done = subprocess.run([sys.executable, script, "--help"], cwd=str(ROOT),
                          env=_no_database_env(), capture_output=True, text=True, timeout=180)
    combined = done.stdout + done.stderr
    broken = [marker for marker in BROKEN_WIRING if marker in combined]
    assert not broken, (
        f"{script} failed to load its import closure ({', '.join(broken)}). The script is "
        f"scheduled, so this is a capability that cannot run at all:\n{combined[-1500:]}"
    )
    reached_database = any(marker in combined for marker in DATABASE_BOUNDARY)
    parsed_arguments = "usage:" in combined
    assert reached_database or parsed_arguments, (
        f"{script} neither parsed arguments nor reached the database. It exited "
        f"{done.returncode} with output that shows it got nowhere in particular:\n"
        f"{combined[-1500:]}"
    )


def test_ADR_0136_the_reachability_report_and_these_checks_do_not_disagree(reach):
    """Every engine pinned above is reported 'scheduled' by the tool that publishes the number.

    Two sources for one fact is how "685 of 685" survived two reviews. If this file and
    `evidence_report.py` ever disagree, the disagreement should be the failure, not a footnote
    in whichever document is read second.
    """
    labels, _edges, _seeds = reach
    disagreements = [e for e in REQUIRED_SCHEDULED_ENGINES if labels.get(e) != "scheduled"]
    assert not disagreements, (
        "these are pinned as scheduled here but not reported so by tools/evidence_report.py: "
        + ", ".join(disagreements)
    )


def test_ADR_0136_acceptance_checks_never_reach_production():
    """The environment these checks hand their subprocesses has no database in it.

    Asserted rather than assumed: OQ-80 records that SUPABASE_DB_URL is exported into the shell
    every agent session inherits, so "the tests do not have it" is a statement that needs
    checking on the machine where it is claimed.
    """
    env = _no_database_env()
    assert "SUPABASE_DB_URL" not in env
    assert "PERSONAL_OS_TEST_SOCKET" not in env
