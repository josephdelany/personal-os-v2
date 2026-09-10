"""The evidence ladder's own correctness — and specifically that it cannot be talked upward.

The report this replaces called a requirement PROVEN because a test function with its ID in
the name existed in a source file. It never ran the test, so a skipped test, an uncollected
test and a failing test all produced the same word as a green run, and the summary rendered
the total as a percentage.

Every test below is a lock on one way that could happen again. Four of them are the direct
answer to "could this tool ever report a pass it does not have": a skip, a failure, a test
that was never collected, and no result file at all. Two more are the answer to "could a
passing test ever manufacture integration or deployment", which is the claim the tool is being
built to stop.

Fixtures are synthetic trees under `tmp_path` (RULE-01): a spec file, a test file and a JUnit
document written for the case at hand. Nothing reads the real repository except the three
clearly-marked smoke tests at the end, which read it and assert nothing about its contents
being good — only that the tool's answers about it are internally consistent.
"""
import json
import pathlib
import textwrap

import pytest

from tools import audit_requirements as ar

# The smoke tests read the repository this file lives in. Derived from the test file's own
# location rather than from the tool's, so they keep reading the real tree wherever the tool
# is imported from.
REAL_ROOT = pathlib.Path(__file__).resolve().parents[1]
# These three assert against the repository, so they are guarded on its presence rather than
# written to pass vacuously somewhere else. The guard is on a marker file, not on a try/except:
# a smoke test that quietly passes when it found nothing to look at is worse than absent.
in_repo = pytest.mark.skipif(
    not (REAL_ROOT / "tests" / "test_bayes_model.py").exists(),
    reason="the repository smoke tests need the real tests/ tree")


# ---------------------------------------------------------------- fixtures

def make_repo(tmp_path, *, spec_ids=("REQ-XYZ-001",), test_source=None):
    """A minimal repository: one spec declaring `spec_ids`, one test file."""
    spec = tmp_path / "specs" / "99-fixture"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "requirements.md").write_text(
        "\n".join(f"**{rid}** (Ubiquitous) The fixture SHALL exist." for rid in spec_ids))
    tests = tmp_path / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test_fixture.py").write_text(textwrap.dedent(test_source or """
        def test_REQ_XYZ_001_the_fixture_exists():
            assert True
        """))
    return tmp_path


def junit(tmp_path, cases, *, name="fixture", timestamp="2026-09-10T00:00:00",
          hostname="fixture-host"):
    """A JUnit document. `cases` is [(classname, name, outcome_tag_or_None), ...]."""
    body = []
    for classname, case, tag in cases:
        if tag is None:
            body.append(f'<testcase classname="{classname}" name="{case}" time="0.01"/>')
        else:
            body.append(f'<testcase classname="{classname}" name="{case}" time="0.01">'
                        f'<{tag} message="fixture">detail</{tag}></testcase>')
    path = tmp_path / "junit.xml"
    path.write_text(f'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite '
                    f'name="{name}" timestamp="{timestamp}" hostname="{hostname}" '
                    f'tests="{len(cases)}" time="1.0">' + "".join(body) +
                    "</testsuite></testsuites>")
    return path


def level_of(tmp_path, cases, *, evidence=None, spec_ids=("REQ-XYZ-001",), test_source=None,
             rid="REQ-XYZ-001", with_results=True):
    root = make_repo(tmp_path, spec_ids=spec_ids, test_source=test_source)
    ev_path = tmp_path / "evidence.json"
    if evidence is not None:
        ev_path.write_text(json.dumps(evidence))
    result = ar.audit(root=root,
                      junit=junit(tmp_path, cases) if with_results else None,
                      evidence_path=ev_path)
    return result["records"][rid], result


ALL_EVIDENCE = {"REQ-XYZ-001": {
    "integration": {"ref": "tools/job.py::main", "how": "ran the job on a disposable spine"},
    "deployment": {"ref": "migrations/9999.sql applied", "how": "psql \\dt shows the table"},
    "observation": {"ref": "ops/runs 2026-09-10", "how": "12 real rows written"}}}


# ================================================================ the four not-passed states

def test_a_skipped_mapped_test_never_reaches_TESTS_PASSED(tmp_path):
    """The live case is REQ-INF-520, whose two executing tests skip wherever NumPyro is absent.

    A skip is a statement about the environment the suite ran in. Reading it as a pass is how
    a requirement whose code has never once executed comes to be reported as covered.
    """
    rec, _ = level_of(tmp_path, [("tests.test_fixture",
                                  "test_REQ_XYZ_001_the_fixture_exists", "skipped")])
    assert rec["test_state"] == "skipped"
    assert rec["level"] == "MAPPED"
    assert rec["level"] != "TESTS_PASSED"
    assert rec["per_test"]["tests.test_fixture::test_REQ_XYZ_001_the_fixture_exists"]["outcome"] \
        == "skipped"


def test_a_failed_or_errored_mapped_test_never_reaches_TESTS_PASSED(tmp_path):
    for tag, expected in (("failure", "failed"), ("error", "error")):
        rec, _ = level_of(tmp_path, [("tests.test_fixture",
                                      "test_REQ_XYZ_001_the_fixture_exists", tag)])
        assert rec["test_state"] == expected
        assert rec["level"] == "MAPPED", f"{tag} must not reach level 3"


def test_a_mapped_test_that_was_never_COLLECTED_never_reaches_TESTS_PASSED(tmp_path):
    """Absent from the results is a third thing, distinct from skipped and from passed.

    This is the quietest of the four: a test deselected by a marker, lost to a collection
    error, or renamed in source and stale in the report leaves no row at all. Treating "no
    news" as good news is how a whole file's worth of coverage disappears without a trace.
    """
    rec, _ = level_of(tmp_path, [("tests.test_other", "test_something_unrelated", None)])
    assert rec["test_state"] == "not_run"
    assert rec["level"] == "MAPPED"
    detail = rec["per_test"]["tests.test_fixture::test_REQ_XYZ_001_the_fixture_exists"]
    assert detail["outcome"] == "not_run"
    assert "not present in any supplied result file" in detail["why"]


def test_with_NO_result_file_level_3_is_unknown_and_never_passed(tmp_path):
    """The old report's actual behaviour: it read source names and printed a percentage without
    ever asking whether anything ran. With no results the answer is `no_results`, which ranks
    below passed, so nothing climbs the ladder."""
    rec, result = level_of(tmp_path, [], with_results=False)
    assert rec["test_state"] == "no_results"
    assert rec["level"] == "MAPPED"
    assert result["junit"] is None
    assert "no result file" in result["junit_note"]
    # And even with every level of declared evidence, it still cannot pass a test it never ran.
    rec2, _ = level_of(tmp_path, [], evidence=ALL_EVIDENCE, with_results=False)
    assert rec2["level"] == "MAPPED"


def test_the_worst_outcome_wins_across_several_mapped_tests(tmp_path):
    """REQ-INF-520 again: one passing test beside two skipped ones is not a pass. Taking the
    best outcome, or the commonest, would report exactly that requirement as covered."""
    source = """
        def test_REQ_XYZ_001_first():
            assert True

        def test_REQ_XYZ_001_second():
            assert True

        def test_REQ_XYZ_001_third():
            assert True
        """
    rec, _ = level_of(tmp_path, [
        ("tests.test_fixture", "test_REQ_XYZ_001_first", None),
        ("tests.test_fixture", "test_REQ_XYZ_001_second", "skipped"),
        ("tests.test_fixture", "test_REQ_XYZ_001_third", "skipped"),
    ], test_source=source)
    assert len(rec["mapped_tests"]) == 3
    assert rec["test_state"] == "skipped"
    assert rec["level"] == "MAPPED"
    assert sorted(v["outcome"] for v in rec["per_test"].values()) == \
        ["passed", "skipped", "skipped"]


def test_one_skipped_parametrised_case_prevents_TESTS_PASSED(tmp_path):
    """Parametrised cases collapse onto their source function. Half the cases skipping is half
    the cases untested, and the roll-up must show that rather than average it away."""
    rec, _ = level_of(tmp_path, [
        ("tests.test_fixture", "test_REQ_XYZ_001_the_fixture_exists[a]", None),
        ("tests.test_fixture", "test_REQ_XYZ_001_the_fixture_exists[b]", "skipped"),
    ])
    assert rec["test_state"] == "skipped"
    assert rec["level"] == "MAPPED"


def test_a_rerun_attempt_is_not_a_pass(tmp_path):
    """A test that needed a retry did not cleanly pass. Same set of non-passing tags
    `tools/update_features.py` already refuses, so the two tools cannot disagree."""
    rec, _ = level_of(tmp_path, [("tests.test_fixture",
                                  "test_REQ_XYZ_001_the_fixture_exists", "rerun")])
    assert rec["test_state"] == "failed"
    assert rec["level"] == "MAPPED"


def test_a_pass_in_one_CI_JOB_and_a_skip_in_the_other_is_a_pass(tmp_path):
    """This repository runs the suite twice — against the live database, and against a
    disposable PostgreSQL server — and each job SKIPS the other's tests by design; 45 of the
    skips in a local run read `SUPABASE_DB_URL not set`. Reading one file alone reports those
    requirements as untested, which is an under-count, and an under-count is not the safe
    direction: it is the same defect pointing the other way, and it teaches a reader to ignore
    the report."""
    root = make_repo(tmp_path)
    live = tmp_path / "live.xml"
    live.write_text(junit(tmp_path, [
        ("tests.test_fixture", "test_REQ_XYZ_001_the_fixture_exists", None)]).read_text())
    local = tmp_path / "local.xml"
    local.write_text(junit(tmp_path, [
        ("tests.test_fixture", "test_REQ_XYZ_001_the_fixture_exists", "skipped")]).read_text())

    rec = ar.audit(root=root, junit=[live, local],
                   evidence_path=tmp_path / "none.json")["records"]["REQ-XYZ-001"]
    assert rec["test_state"] == "passed"
    assert rec["level"] == "TESTS_PASSED"
    detail = rec["per_test"]["tests.test_fixture::test_REQ_XYZ_001_the_fixture_exists"]
    assert detail["runs"] == {"live.xml": "passed", "local.xml": "skipped"}, detail


def test_a_FAILURE_in_any_run_beats_a_pass_in_another(tmp_path):
    """The asymmetry that keeps the merge honest: failures are unioned across runs, passes are
    not. A test that fails in one job and passes in another is a failing test — most likely a
    real environment-dependent defect, which is exactly what must not be averaged away."""
    root = make_repo(tmp_path)
    good = tmp_path / "good.xml"
    good.write_text(junit(tmp_path, [
        ("tests.test_fixture", "test_REQ_XYZ_001_the_fixture_exists", None)]).read_text())
    bad = tmp_path / "bad.xml"
    bad.write_text(junit(tmp_path, [
        ("tests.test_fixture", "test_REQ_XYZ_001_the_fixture_exists", "failure")]).read_text())

    for order in ([good, bad], [bad, good]):
        rec = ar.audit(root=root, junit=order,
                       evidence_path=tmp_path / "none.json")["records"]["REQ-XYZ-001"]
        assert rec["test_state"] == "failed", order
        assert rec["level"] == "MAPPED"


def test_skipped_in_every_supplied_run_is_still_skipped(tmp_path):
    """Merging must not turn two skips into a pass. Two jobs that both skipped a test have
    between them tested nothing."""
    root = make_repo(tmp_path)
    a, b = tmp_path / "a.xml", tmp_path / "b.xml"
    for path in (a, b):
        path.write_text(junit(tmp_path, [
            ("tests.test_fixture", "test_REQ_XYZ_001_the_fixture_exists", "skipped")]).read_text())
    rec = ar.audit(root=root, junit=[a, b],
                   evidence_path=tmp_path / "none.json")["records"]["REQ-XYZ-001"]
    assert rec["test_state"] == "skipped"
    assert rec["level"] == "MAPPED"


def test_the_reason_a_test_skipped_is_carried_into_the_report(tmp_path):
    """"Skipped" alone is unactionable. "Skipped because NumPyro is not importable" tells the
    reader whether the gap is an environment to fix or a requirement to implement."""
    root = make_repo(tmp_path)
    path = tmp_path / "j.xml"
    path.write_text(
        '<testsuites><testsuite name="s" tests="1"><testcase '
        'classname="tests.test_fixture" name="test_REQ_XYZ_001_the_fixture_exists">'
        '<skipped message="NumPyro not importable in this interpreter"/></testcase>'
        '</testsuite></testsuites>')
    rec = ar.audit(root=root, junit=path,
                   evidence_path=tmp_path / "none.json")["records"]["REQ-XYZ-001"]
    assert "NumPyro not importable" in \
        rec["per_test"]["tests.test_fixture::test_REQ_XYZ_001_the_fixture_exists"]["why"]


# ================================================================ passing tests fabricate nothing

def test_all_mapped_tests_passing_does_NOT_produce_integration_evidence(tmp_path):
    """The central claim. Green tests are evidence about the assertions in those tests, and
    nothing whatever about whether an application calls the code.

    The concrete case: `inferred_input` and `acceptance_report` in
    `tools/engines/surface_contract.py` have passing named tests for REQ-REC-013 and
    REQ-REC-016 and no caller anywhere outside those tests.
    """
    rec, _ = level_of(tmp_path, [("tests.test_fixture",
                                  "test_REQ_XYZ_001_the_fixture_exists", None)])
    assert rec["test_state"] == "passed"
    assert rec["level"] == "TESTS_PASSED", "a green mapped test reaches level 3 and stops"
    assert rec["level"] != "INTEGRATED"
    assert rec["evidence"] == {}
    assert rec["level_reason"] == "no declared integration evidence"


def test_the_ladder_is_monotonic_so_deployment_evidence_cannot_skip_a_rung(tmp_path):
    """A declared deployment reference for a requirement whose tests skip must NOT report
    DEPLOYED. Computing each level as an independent predicate and taking the maximum would
    report exactly that, and it is the most flattering possible reading of the evidence."""
    only_deploy = {"REQ-XYZ-001": {
        "deployment": {"ref": "migrations/9999.sql", "how": "applied by hand"},
        "observation": {"ref": "ops/runs", "how": "seen once"}}}
    rec, _ = level_of(tmp_path, [("tests.test_fixture",
                                  "test_REQ_XYZ_001_the_fixture_exists", "skipped")],
                      evidence=only_deploy)
    assert rec["level"] == "MAPPED"

    # Passing tests, and deployment declared, but integration NOT declared: it stops at 3.
    rec2, _ = level_of(tmp_path, [("tests.test_fixture",
                                   "test_REQ_XYZ_001_the_fixture_exists", None)],
                       evidence=only_deploy)
    assert rec2["level"] == "TESTS_PASSED"
    assert rec2["evidence"]["deployment"]["ref"] == "migrations/9999.sql"


def test_the_full_ladder_is_reachable_only_with_every_level_declared(tmp_path):
    """The tool is not unfalsifiable in the other direction either: real declared evidence at
    every level does reach OBSERVED, so a reader can tell "nobody wrote it down" apart from
    "the tool refuses to ever say yes"."""
    rec, _ = level_of(tmp_path, [("tests.test_fixture",
                                  "test_REQ_XYZ_001_the_fixture_exists", None)],
                      evidence=ALL_EVIDENCE)
    assert rec["level"] == "OBSERVED"
    assert rec["evidence"]["observation"]["how"] == "12 real rows written"


def test_an_evidence_entry_that_does_not_say_what_was_verified_is_refused(tmp_path):
    """A reference with no statement of what was checked is a citation to nothing, and it would
    otherwise print as INTEGRATED — the exact failure being corrected, re-entering through the
    file that was meant to fix it."""
    bad = {"REQ-XYZ-001": {"integration": {"ref": "tools/job.py"}},          # no `how`
           "REQ-XYZ-002": {"integration": {"how": "ran it"}},               # no `ref`
           "REQ-XYZ-003": {"integration": "yes"},                           # not an object
           "REQ-XYZ-004": {"vibes": {"ref": "x", "how": "y"}}}              # unknown kind
    path = tmp_path / "ev.json"
    path.write_text(json.dumps(bad))
    evidence, note = ar.load_evidence(path)
    assert evidence == {}
    assert "refused" in note

    rec, _ = level_of(tmp_path, [("tests.test_fixture",
                                 "test_REQ_XYZ_001_the_fixture_exists", None)], evidence=bad)
    assert rec["level"] == "TESTS_PASSED"


def test_an_absent_evidence_file_means_UNKNOWN_and_not_false(tmp_path):
    """"Nobody has verified integration" and "integration was verified and failed" are
    different facts. The tool reports the first and never silently renders it as the second."""
    evidence, note = ar.load_evidence(tmp_path / "does_not_exist.json")
    assert evidence == {}
    assert "no evidence file" in note and "UNKNOWN" in note


def test_no_code_path_in_the_tool_writes_or_derives_evidence():
    """Levels 4-6 exist only if a human wrote them down, so the tool must have no way to write
    one. The absence of a write has no call to make, so it is asserted against the source.

    Checked by PARSING for calls rather than by searching for substrings. The first version of
    this test searched for the text `open(` and failed on the function `render_open(` — the
    same text-versus-structure error this whole tool exists to correct, committed inside the
    test meant to guard it. Parsing distinguishes a call from a name that contains one.
    """
    import ast
    import inspect

    banned = {"write_text", "write_bytes", "writelines", "mkdir", "unlink", "replace",
              "dump", "open", "remove", "rmtree"}
    allowed_dump = {"dumps"}                       # rendering to stdout is not writing
    calls = []
    for node in ast.walk(ast.parse(inspect.getsource(ar))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in banned and name not in allowed_dump:
            calls.append(name)
    assert calls == [], f"the audit tool must only READ; it calls {sorted(set(calls))}"

    # And the only thing that can raise a level above 3 is a key lookup in the loaded file.
    assert "evidence.get(rid" in inspect.getsource(ar)


# ================================================================ mapping precision

def test_only_a_test_FUNCTION_DEFINITION_counts_not_a_name_quoted_in_a_string(tmp_path):
    """This file embeds whole fixture modules as triple-quoted strings, whose lines really do
    start with `def`. A regex over source — even one anchored to the start of a line — counts
    those, and an earlier version of this tool did: it reported these invented IDs as mapped
    and then as orphans of the real specs. Parsing is what makes the distinction real.

    A nested definition is not collected either, because pytest does not collect one.
    """
    source = '''
        NAMES = ["def test_REQ_XYZ_002_quoted_only(x):"]

        def helper_REQ_XYZ_003_not_a_test():
            pass

        def test_REQ_XYZ_001_real():
            assert "def test_REQ_XYZ_004_in_an_assertion(x):"

            def test_REQ_XYZ_005_nested_is_never_collected():
                pass
        '''
    root = make_repo(tmp_path, spec_ids=("REQ-XYZ-001", "REQ-XYZ-002", "REQ-XYZ-003",
                                         "REQ-XYZ-004", "REQ-XYZ-005"), test_source=source)
    mapped = ar.mapped_tests(root)
    assert set(mapped) == {"REQ-XYZ-001"}
    assert "REQ-XYZ-002" not in mapped, "a name inside a string list is not a definition"
    assert "REQ-XYZ-003" not in mapped, "only a test_ function counts"
    assert "REQ-XYZ-004" not in mapped, "a name inside an assertion is not a definition"
    assert "REQ-XYZ-005" not in mapped, "a nested def is not collected by pytest either"


def test_one_test_name_can_map_several_requirements(tmp_path):
    """`test_REQ_ASK_021_022_011_...` covers three. Counting only the first is an UNDER-count —
    the mirror of the over-count, and just as misleading, because it hides real coverage."""
    source = """
        def test_REQ_XYZ_001_002_003_covers_three():
            assert True
        """
    root = make_repo(tmp_path, spec_ids=("REQ-XYZ-001", "REQ-XYZ-002", "REQ-XYZ-003"),
                     test_source=source)
    mapped = ar.mapped_tests(root)
    assert set(mapped) == {"REQ-XYZ-001", "REQ-XYZ-002", "REQ-XYZ-003"}
    assert all(len(v) == 1 for v in mapped.values())


def test_an_id_is_exactly_three_digits_and_stands_alone():
    assert ar.ID.findall("REQ-ASK-031 and REQ-FIN-070") == ["REQ-ASK-031", "REQ-FIN-070"]
    assert ar.ID.findall("REQ-ASK-31") == [], "a two-digit tail is not an ID"
    assert ar.ID.findall("XREQ-ASK-031") == [], "an ID must stand alone"
    assert ar.ID.findall("REQ-NFR-0012") == [], "four digits must not match REQ-NFR-001"
    assert [m.groups() for m in ar.IN_NAME.finditer("test_REQ_NFR_0012_x")] == []


def test_a_test_naming_a_requirement_no_spec_declares_is_an_ORPHAN(tmp_path):
    """A test whose subject does not exist is a test nobody can check. Silently dropping it
    loses both the typo and the deleted requirement."""
    source = """
        def test_REQ_XYZ_404_names_nothing_real():
            assert True
        """
    root = make_repo(tmp_path, spec_ids=("REQ-XYZ-001",), test_source=source)
    result = ar.audit(root=root, junit=None, evidence_path=tmp_path / "none.json")
    assert result["records"]["REQ-XYZ-404"]["level"] == "ORPHAN"
    assert result["records"]["REQ-XYZ-404"]["declared"] is False
    # And the declared-but-untested one is still reported at its own level.
    assert result["records"]["REQ-XYZ-001"]["level"] == "DECLARED"
    assert "no test function name carries this ID" in result["records"]["REQ-XYZ-001"]["level_reason"]


def test_a_declared_requirement_with_no_mapped_test_stops_at_DECLARED(tmp_path):
    rec, _ = level_of(tmp_path, [], spec_ids=("REQ-XYZ-001",),
                      test_source="def test_unrelated():\n    assert True\n")
    assert rec["mapped_tests"] == []
    assert rec["test_state"] == "no_tests"
    assert rec["level"] == "DECLARED"


# ================================================================ provenance of the audit itself

def test_the_report_records_the_revision_and_the_environment_it_was_produced_in(tmp_path):
    """A skip is a fact about an environment, so a report that omits the environment cannot be
    read. And results that passed, passed against a particular source: without the revision the
    report is about nothing."""
    root = make_repo(tmp_path)
    result = ar.audit(root=root, junit=junit(tmp_path, [
        ("tests.test_fixture", "test_REQ_XYZ_001_the_fixture_exists", None)]),
        evidence_path=tmp_path / "none.json")
    assert set(result["revision"]) == {"head", "short", "branch", "dirty"}
    assert result["environment"]["python"]
    assert "numpyro" in result["environment"]["importable"]
    assert result["junit"][0]["hostname"] == "fixture-host"
    assert result["junit"][0]["timestamp"] == "2026-09-10T00:00:00"
    assert result["junit"][0]["label"] == "junit.xml"
    assert result["generated_at"].endswith("+00:00")


def test_an_unparseable_or_empty_result_file_is_NO_RESULTS_and_not_a_pass(tmp_path):
    """A truncated report is the one most likely to be read optimistically, because it looks
    like a report."""
    truncated = tmp_path / "bad.xml"
    truncated.write_text("<testsuites><testsuite name='x'><testcase ")
    with pytest.raises(ar.NoResults):
        ar.parse_junit(truncated)

    empty = tmp_path / "empty.xml"
    empty.write_text("<testsuites><testsuite name='x' tests='0'/></testsuites>")
    with pytest.raises(ar.NoResults):
        ar.parse_junit(empty)

    root = make_repo(tmp_path)
    result = ar.audit(root=root, junit=truncated, evidence_path=tmp_path / "none.json")
    assert result["records"]["REQ-XYZ-001"]["level"] == "MAPPED"
    assert "not parseable" in result["junit_note"]


def test_a_test_file_that_does_not_parse_is_reported_and_not_silently_zero(tmp_path):
    """A broken test file contributes no coverage. Reporting it as "no tests" hides the reason,
    and the reason is that the file cannot be collected at all."""
    root = make_repo(tmp_path)
    (root / "tests" / "test_broken.py").write_text("def test_REQ_XYZ_001_x(:\n  pass\n")
    unparseable = []
    ar.mapped_tests(root, unparseable)
    assert len(unparseable) == 1 and "test_broken.py" in unparseable[0]
    result = ar.audit(root=root, junit=None, evidence_path=tmp_path / "none.json")
    assert result["unparseable_test_files"]


def test_the_word_PROVEN_appears_nowhere_in_the_levels():
    """Level 3 is TESTS_PASSED. "Proven" and "complete" are claims about a requirement's whole
    sentence, which a test of one branch of one step does not support."""
    assert "TESTS_PASSED" in ar.LEVELS
    assert not any(l in ar.LEVELS for l in ("PROVEN", "COMPLETE", "COVERED", "DONE"))


def test_a_single_percentage_is_not_the_summary_output(tmp_path, capsys):
    """The defect was a percentage that averaged six different questions into one number, and a
    percentage is the one output nobody re-derives."""
    root = make_repo(tmp_path)
    result = ar.audit(root=root, junit=junit(tmp_path, [
        ("tests.test_fixture", "test_REQ_XYZ_001_the_fixture_exists", "skipped")]),
        evidence_path=tmp_path / "none.json")
    ar.render_summary(result)
    printed = capsys.readouterr().out
    assert "%" not in printed
    for level in ar.LEVELS:
        assert level[:11] in printed
    assert "CUMULATIVE" in printed


# ================================================================ the real repository

def test_the_documented_open_flag_still_works_and_now_reads_a_result_file(tmp_path, capsys):
    """`--open REQ-FIN` is documented in docs/NEXT_SESSION.md. It is kept working rather than
    removed, but it now answers the question the reader was actually asking: what has NOT
    reached TESTS_PASSED, which the old flag could not tell them because it read no results."""
    root = make_repo(tmp_path, spec_ids=("REQ-XYZ-001", "REQ-XYZ-002"))
    result = ar.audit(root=root, junit=junit(tmp_path, [
        ("tests.test_fixture", "test_REQ_XYZ_001_the_fixture_exists", "skipped")]),
        evidence_path=tmp_path / "none.json")
    assert ar.render_open(result, "REQ-XYZ") == 0
    printed = capsys.readouterr().out
    assert "REQ-XYZ-001" in printed and "skipped" in printed
    assert "REQ-XYZ-002" in printed, "declared with no mapped test is also not TESTS_PASSED"
    assert "not the same as being covered, integrated or deployed" in printed


@in_repo
def test_smoke_the_real_specs_declare_hundreds_of_requirements():
    """Reads the repository and asserts only what must be true of any state of it."""
    spec_ids = ar.declared_requirements(REAL_ROOT)
    assert len(spec_ids) > 600
    assert all(ar.ID.fullmatch(r) for r in spec_ids)


@in_repo
def test_smoke_the_numpyro_requirement_has_several_mapped_tests_not_one_verdict():
    """The disputed NumPyro case, read from the real tree. Three tests name REQ-INF-520; two
    call NUTS and skip where NumPyro is absent, and the third asserts on `inspect.getsource`.
    Whatever this environment does, the tool must show them individually rather than collapse
    them — this asserts the SHAPE of the answer, not a particular outcome."""
    mapped = ar.mapped_tests(REAL_ROOT)
    keys = mapped.get("REQ" "-INF-520", set())
    assert len(keys) >= 3, keys
    assert all(k.startswith("tests.") and "::" in k for k in keys)
    # And this file must not have mapped ITSELF onto that requirement by naming it.
    assert not any("test_audit_requirements" in k for k in keys)


@in_repo
def test_smoke_the_audit_never_reports_a_level_above_TESTS_PASSED_without_an_evidence_file():
    """The repository has no `ops/requirement_evidence.json`. So no requirement in it may be
    reported as INTEGRATED, DEPLOYED or OBSERVED — by anything the tool can do on its own."""
    result = ar.audit(root=REAL_ROOT, junit=None)
    levels = {r["level"] for r in result["records"].values()}
    assert not (levels & {"INTEGRATED", "DEPLOYED", "OBSERVED"}), levels
    assert "no evidence file" in result["evidence_note"]
