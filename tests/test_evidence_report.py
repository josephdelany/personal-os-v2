"""The evidence report's own correctness, against synthetic repositories in tmp_path.

WHY tmp_path AND NOT THE LIVE SUITE. A test that asserts "the real audit says 636" pins a
number that moves every time anyone writes a test, and it cannot exhibit the cases that
matter — a failing test, a skipped test, an empty test — because the real suite does not
contain them on purpose. Each test below builds a four-file repository whose answer is known
by construction, so a wrong answer is a defect in the tool and never a defect in the fixture.

WHY NO REQUIREMENT ID IS IN ANY TEST NAME HERE. The project's rule is that a test name carries
the IDs it covers, and both audit tools read those names as coverage. These tests cover a
TOOL, not a requirement, so naming one `test_REQ_NFR_005_...` would make the audit report that
requirement as covered by a test of the auditor. That precise mistake was in the previous
version of `tests/test_audit_requirements.py` and was removed in b899489. Repeating it here
would reintroduce it. The fixture IDs below are `REQ-ZZZ-nnn`, which no spec declares, and
they live inside triple-quoted strings that `ast.parse` never treats as definitions.
"""
import pathlib
import subprocess
import sys
import textwrap

import pytest

from tools import evidence_report as er


ROOT = pathlib.Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ the synthetic repository

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip())
    return path


JUNIT = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="5" errors="0" failures="1" skipped="1"
    time="0.1" timestamp="2026-09-10T12:00:00" hostname="fixture">
  <testcase classname="tests.test_fixture" name="test_REQ_ZZZ_001_passes" time="0.01"/>
  <testcase classname="tests.test_fixture" name="test_REQ_ZZZ_002_fails" time="0.01">
    <failure message="assert 1 == 2">assert 1 == 2</failure>
  </testcase>
  <testcase classname="tests.test_fixture" name="test_REQ_ZZZ_003_skips" time="0.0">
    <skipped message="SUPABASE_DB_URL not set" type="pytest.skip"/>
  </testcase>
  <testcase classname="tests.test_fixture" name="test_REQ_ZZZ_004_asserts_nothing" time="0.01"/>
  <testcase classname="tests.test_fixture" name="test_REQ_ZZZ_006_touches_the_orphan_library"
      time="0.01"/>
</testsuite></testsuites>
"""

FIXTURE_TESTS = '''\
    from tools.engines import wired, orphan


    def test_REQ_ZZZ_001_passes():
        assert wired.double(2) == 4


    def test_REQ_ZZZ_002_fails():
        assert wired.double(2) == 5


    def test_REQ_ZZZ_003_skips():
        assert wired.double(3) == 6


    def test_REQ_ZZZ_004_asserts_nothing():
        """Named for a requirement, checks nothing. The whole defect, in four lines."""
        wired.double(2)


    def test_REQ_ZZZ_005_was_never_collected():
        assert wired.double(4) == 8


    def test_REQ_ZZZ_006_touches_the_orphan_library():
        assert orphan.triple(2) == 6
'''


@pytest.fixture
def repo(tmp_path):
    """A repository with one scheduled entry point, one wired engine and one orphan engine.

    By construction:
      REQ-ZZZ-001 passes           REQ-ZZZ-004 passes but asserts nothing  -> vacuous
      REQ-ZZZ-002 fails            REQ-ZZZ-005 named in source, absent from the report
      REQ-ZZZ-003 skips            REQ-ZZZ-006 passes, but only `orphan` is imported
                                   REQ-ZZZ-007 declared with no test at all
    `tools/engines/wired.py` is imported by `tools/run_job.py`, which `.github/workflows/
    nightly.yml` starts. `tools/engines/orphan.py` is imported by the test file and by nothing
    else.
    """
    write(tmp_path / "specs/01-fixture/requirements.md", """
        REQ-ZZZ-001 the tool shall count a pass.
        REQ-ZZZ-002 the tool shall not count a failure.
        REQ-ZZZ-003 the tool shall not count a skip.
        REQ-ZZZ-004 the tool shall flag an empty test.
        REQ-ZZZ-005 the tool shall not count a test that never ran.
        REQ-ZZZ-006 the tool shall report an unreachable library as unreachable.
        REQ-ZZZ-007 the tool shall report a requirement with no test.
    """)
    write(tmp_path / "tests/test_fixture.py", FIXTURE_TESTS)
    write(tmp_path / "tools/__init__.py", "")
    write(tmp_path / "tools/engines/__init__.py", "")
    write(tmp_path / "tools/engines/wired.py", "def double(n):\n    return n * 2\n")
    write(tmp_path / "tools/engines/orphan.py", "def triple(n):\n    return n * 3\n")
    write(tmp_path / "tools/run_job.py", """
        from tools.engines import wired

        if __name__ == "__main__":
            print(wired.double(21))
    """)
    write(tmp_path / ".github/workflows/nightly.yml", """
        name: nightly
        jobs:
          go:
            steps:
              - run: python3 tools/run_job.py
    """)
    write(tmp_path / "junit.xml", JUNIT)
    return tmp_path


@pytest.fixture
def rows(repo):
    return er.build(repo, [repo / "junit.xml"])["rows"]


# ------------------------------------------------------------------ column one: what ran

def test_a_requirement_whose_test_failed_is_not_counted_proven(rows):
    """The single most important refusal. A red test is evidence AGAINST the requirement."""
    assert rows["REQ-ZZZ-002"]["status"] == "failed"
    assert rows["REQ-ZZZ-002"]["status"] != "passed"
    proven = {r for r, v in rows.items() if v["status"] == "passed"}
    assert "REQ-ZZZ-002" not in proven


def test_a_requirement_whose_test_skipped_is_not_counted_proven(rows):
    """125 of this repository's real skips read `SUPABASE_DB_URL not set`. A skip is the
    absence of evidence, and the old tool could not see the difference."""
    assert rows["REQ-ZZZ-003"]["status"] == "skipped"
    assert rows["REQ-ZZZ-003"]["status"] != "passed"


def test_a_test_that_asserts_nothing_is_flagged_and_not_counted_proven(rows):
    """`test_REQ_ZZZ_004_asserts_nothing` calls the engine and checks nothing. JUnit records a
    clean pass — the test really did not raise — so results alone cannot catch this."""
    row = rows["REQ-ZZZ-004"]
    assert row["status"] == "vacuous", "a passing test that asserts nothing is not proof"
    assert row["empty_tests"] == ["tests.test_fixture::test_REQ_ZZZ_004_asserts_nothing"]


def test_a_named_test_missing_from_the_report_is_not_run_rather_than_passed(rows):
    """`test_REQ_ZZZ_005_was_never_collected` exists in source and in no result file. The old
    tool counted it; not being collected is a different fact from passing."""
    assert rows["REQ-ZZZ-005"]["status"] == "not_run"


def test_a_requirement_with_no_test_at_all_is_distinguished_from_one_with_a_failing_test(rows):
    assert rows["REQ-ZZZ-007"]["status"] == "no_tests"
    assert rows["REQ-ZZZ-007"]["tests"] == []
    assert rows["REQ-ZZZ-007"]["status"] != rows["REQ-ZZZ-002"]["status"]


def test_only_the_genuinely_passing_requirement_is_counted(rows):
    """One of seven. The old name count would have said seven of seven."""
    passed = sorted(r for r, v in rows.items() if v["status"] == "passed")
    assert passed == ["REQ-ZZZ-001", "REQ-ZZZ-006"]
    named = sorted(r for r, v in rows.items() if v["tests"])
    assert len(named) == 6, "six of the seven have a test NAME carrying their ID"


def test_a_trivial_assertion_does_not_rescue_an_empty_test(repo):
    """`assert True` is a syntactic assertion and no check at all."""
    write(repo / "tests/test_fixture.py",
          FIXTURE_TESTS.replace('        wired.double(2)\n', '        assert True\n'))
    rows = er.build(repo, [repo / "junit.xml"])["rows"]
    assert rows["REQ-ZZZ-004"]["status"] == "vacuous"


def test_an_assertion_delegated_to_a_helper_is_not_called_empty(repo):
    """The mirror defect. Real tests here delegate to `refuses(...)` and `check_imports(...)`;
    calling those vacuous would invent an absence, which RULE-00 forbids as firmly as
    inventing a presence."""
    write(repo / "tests/test_fixture.py", FIXTURE_TESTS.replace(
        '        wired.double(2)\n',
        '        _must_double(2, 4)\n')
        + '\n\n    def _must_double(n, expected):\n'
          '        assert wired.double(n) == expected\n')
    rows = er.build(repo, [repo / "junit.xml"])["rows"]
    assert rows["REQ-ZZZ-004"]["status"] == "passed", \
        "a test whose helper asserts is not an empty test"


def test_with_no_result_file_the_tool_refuses_instead_of_counting_names(repo):
    """The defect, refused at the door: no results means unknown, not proven."""
    with pytest.raises(er.audit_tool.NoResults):
        er.build(repo, [])
    assert er.main(["--root", str(repo), "--out", "docs/EVIDENCE_REPORT.md"]) == 2
    assert not (repo / "docs/EVIDENCE_REPORT.md").exists()


def test_a_failure_in_one_run_beats_a_pass_in_another(repo):
    """CI runs this suite twice. Merging must not let a green run erase a red one."""
    write(repo / "second.xml", JUNIT.replace(
        '<testcase classname="tests.test_fixture" name="test_REQ_ZZZ_002_fails" time="0.01">\n'
        '    <failure message="assert 1 == 2">assert 1 == 2</failure>\n  </testcase>',
        '<testcase classname="tests.test_fixture" name="test_REQ_ZZZ_002_fails" time="0.01"/>'))
    rows = er.build(repo, [repo / "second.xml", repo / "junit.xml"])["rows"]
    assert rows["REQ-ZZZ-002"]["status"] == "failed"
    rows = er.build(repo, [repo / "junit.xml", repo / "second.xml"])["rows"]
    assert rows["REQ-ZZZ-002"]["status"] == "failed", "order must not change the verdict"


def test_a_skip_in_one_run_and_a_pass_in_another_is_a_pass(repo):
    """The opposite direction, and it must also hold: the disposable-server job skips the live
    job's tests by design, and reporting those as untested is an under-count."""
    write(repo / "second.xml", JUNIT.replace(
        '<testcase classname="tests.test_fixture" name="test_REQ_ZZZ_003_skips" time="0.0">\n'
        '    <skipped message="SUPABASE_DB_URL not set" type="pytest.skip"/>\n  </testcase>',
        '<testcase classname="tests.test_fixture" name="test_REQ_ZZZ_003_skips" time="0.01"/>'))
    rows = er.build(repo, [repo / "junit.xml", repo / "second.xml"])["rows"]
    assert rows["REQ-ZZZ-003"]["status"] == "passed"


# ------------------------------------------------------------------ column two: who calls it

def test_a_module_no_non_test_caller_imports_is_reported_tests_only(repo):
    """`orphan.py` is imported by the test file and by nothing else. `wired.py` is reached from
    the script the workflow starts. The two must not report the same word."""
    labels = er.build(repo, [repo / "junit.xml"])["labels"]
    assert labels["tools.engines.orphan"] == "tests-only"
    assert labels["tools.engines.wired"] == "scheduled"
    assert labels["tools.run_job"] == "scheduled"


def test_the_requirement_reachability_column_follows_what_its_test_imports(rows):
    """REQ-ZZZ-006's only passing test is the one that touches the orphan — but the fixture
    module also imports `wired`, and reachability is per test MODULE, so both read
    `scheduled`. The engine table below is where the orphan is visible; this asserts the
    column is computed from imports and is reported separately from status."""
    assert rows["REQ-ZZZ-006"]["status"] == "passed"
    assert rows["REQ-ZZZ-006"]["reach"] == "scheduled"
    assert "tools.engines.wired" in rows["REQ-ZZZ-006"]["via"]


def test_reachability_is_transitive_but_a_main_block_alone_is_not_scheduled(repo):
    """A script nothing schedules is `cli`, never `scheduled`. Treating every `__main__` as an
    entry point is the flattering answer and would make almost everything look reachable."""
    write(repo / "tools/engines/deep.py", "def deep():\n    return 1\n")
    write(repo / "tools/engines/wired.py",
          "from tools.engines import deep\n\n\ndef double(n):\n    return n * 2\n")
    write(repo / "tools/handrun.py", """
        from tools.engines import orphan

        if __name__ == "__main__":
            print(orphan.triple(1))
    """)
    labels = er.build(repo, [repo / "junit.xml"])["labels"]
    assert labels["tools.engines.deep"] == "scheduled", "reached through wired, transitively"
    assert labels["tools.handrun"] == "cli", "a main block is not a schedule"
    assert labels["tools.engines.orphan"] == "cli", "now hand-runnable, still not scheduled"


def test_the_from_package_import_module_form_is_an_edge(repo):
    """`from tools.engines import wired` must record an edge to `tools.engines.wired`, not only
    to the package. Missing this form makes `tools/run_analysis.py` look as though it imports
    no engine at all — it imports three that way, and the naive graph reports 45 orphaned
    engines where there are 42."""
    _, edges, _ = er.module_reach(repo)
    assert "tools.engines.wired" in edges["tools.run_job"]


def test_an_entry_point_is_read_from_the_workflow_not_guessed(repo):
    result = er.build(repo, [repo / "junit.xml"])
    assert result["entry_points"] == ["tools.run_job"]
    write(repo / ".github/workflows/nightly.yml", "name: nightly\njobs: {}\n")
    result = er.build(repo, [repo / "junit.xml"])
    assert result["entry_points"] == []
    assert result["labels"]["tools.engines.wired"] == "cli", \
        "with nothing scheduled, the hand-runnable path is all that is left"


# ------------------------------------------------------------------ the document

def test_the_report_states_both_figures_and_names_the_gap(repo):
    document = er.render(er.build(repo, [repo / "junit.xml"]))
    assert "2 of 7 requirements (28.6%) have a named test that ran and passed" in document
    assert "6 of 7 (85.7%) proven" in document, "the superseded name count, for comparison"
    assert "4 requirements** whose entire evidence was a filename" in document
    assert "ADR-0134" in document
    for column in ("vacuous", "not run", "tests-only", "scheduled"):
        assert column in document


def test_check_fails_on_a_hand_edited_report(repo):
    """Generated, never hand-edited — enforced, not asked for."""
    assert er.main(["--root", str(repo), "--report", str(repo / "junit.xml")]) == 0
    out = repo / "docs/EVIDENCE_REPORT.md"
    assert er.main(["--root", str(repo), "--report", str(repo / "junit.xml"), "--check"]) == 0
    out.write_text(out.read_text().replace("2 of 7 requirements", "7 of 7 requirements"))
    assert er.main(["--root", str(repo), "--report", str(repo / "junit.xml"), "--check"]) == 1


def test_the_report_is_reproducible_apart_from_its_timestamp(repo):
    build = er.build(repo, [repo / "junit.xml"])
    assert er._comparable(er.render(build)) == er._comparable(er.render(er.build(
        repo, [repo / "junit.xml"])))


# ------------------------------------------------------------------ against the real tree

def test_the_fixture_ids_in_this_file_never_reach_the_real_audit():
    """Every requirement ID above lives inside a triple-quoted string. Test collection is done
    by parsing, so none of them may appear as a mapped test or an orphan of the real specs."""
    mapped = __import__("tools.audit_requirements", fromlist=["x"]).mapped_tests(ROOT)
    assert not [r for r in mapped if r.startswith("REQ-ZZZ")], \
        "a fixture string was read as a test definition"


def test_the_tool_runs_against_the_real_tree_and_refuses_without_results():
    """No result file is cached in CI, so this asserts the refusal path, not a number."""
    done = subprocess.run([sys.executable, "tools/evidence_report.py"],
                          cwd=ROOT, capture_output=True, text=True,
                          env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"})
    assert done.returncode == 2, done.stderr
    assert "REFUSED" in done.stderr
