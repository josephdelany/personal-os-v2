"""The demonstration ADR-0011 required before it is discharged: the sanctioned ledger
writer flips an entry ONLY on a genuinely passing test that names the requirement ID,
and never touches anything else (CONSTITUTION Definition of Done item 4; INV-6).

No REQ ID exists for this mechanism (specs/06-nfr defines REQ-NFR-001..004 only —
checked 2026-09-02, session 17, B0), so these tests carry the ADR ID, the convention
already used by test_ADR_0002_* / test_ADR_0021_*.

Everything here runs against a hand-written JUnit fixture and a COPY of the ledger in
a temp dir. The real ops/features.json is never opened for writing by these tests.
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import update_features as uf  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "junit_update_features.xml"


def _ledger(tmp_path, entries, comment="never reworded — test"):
    p = tmp_path / "features.json"
    doc = {"_comment": comment, "features": entries}
    p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return p


def _entry(fid, req, status="failing", proving=None, extra=None):
    e = {"id": fid, "description": f"desc {fid}", "requirement": req,
         "status": status, "proving_test": proving}
    if extra:
        e.update(extra)
    return e


def test_ADR_0011_only_genuinely_passing_testcases_count():
    passed, counts = uf.parse_junit(FIXTURE)
    names = [full for full, _ in passed]
    # the two real passes, the 4-digit one, and the unnamed one are the only bare testcases
    assert names == [
        "tests.test_a::test_REQ_AAA_001_genuine_pass",
        "tests.test_a::test_REQ_AAA_001_second_pass_same_req",
        "tests.test_a::test_REQ_GGG_0017_four_digit_id",
        "tests.test_a::test_no_requirement_named",
    ]
    # failure / error / skipped / xfail-as-skipped / rerun are all excluded from evidence
    assert counts == {"total": 9, "passed": 4, "failed": 2, "errors": 1, "skipped": 2}


def test_ADR_0011_flips_only_the_named_requirement_and_records_first_test(tmp_path):
    ledger = _ledger(tmp_path, [
        _entry("F-001", "REQ-AAA-001"),          # named by a genuine pass -> flips
        _entry("F-002", "REQ-BBB-002"),          # named only by a failing test -> stays
        _entry("F-003", "REQ-CCC-003"),          # setup error -> stays
        _entry("F-004", "REQ-DDD-004"),          # skipped -> stays
        _entry("F-005", "REQ-EEE-005"),          # xfail that failed -> stays
        _entry("F-006", "REQ-FFF-006"),          # rerun attempt -> stays
        _entry("F-007", "REQ-GGG-001"),          # 4-digit REQ_GGG_0017 must NOT prefix-match
        _entry("F-008", "REQ-ZZZ-999"),          # no test at all -> stays
    ])
    doc, counts, regressions = uf.apply(FIXTURE, ledger)
    by_id = {e["id"]: e for e in doc["features"]}
    assert by_id["F-001"]["status"] == "passing"
    assert by_id["F-001"]["proving_test"] == "tests.test_a::test_REQ_AAA_001_genuine_pass"
    for fid in ("F-002", "F-003", "F-004", "F-005", "F-006", "F-007", "F-008"):
        assert by_id[fid]["status"] == "failing", fid
        assert by_id[fid]["proving_test"] is None, fid
    assert regressions == []
    # written back to disk, not just returned
    on_disk = json.loads(ledger.read_text(encoding="utf-8"))
    assert on_disk == doc


def test_ADR_0011_never_moves_passing_to_failing_and_prints_regression(tmp_path, capsys):
    ledger = _ledger(tmp_path, [
        _entry("F-010", "REQ-BBB-002", status="passing", proving="tests.old::test_REQ_BBB_002_was_green"),
    ])
    doc, _, regressions = uf.apply(FIXTURE, ledger)
    e = doc["features"][0]
    assert e["status"] == "passing"                                   # untouched (INV-6)
    assert e["proving_test"] == "tests.old::test_REQ_BBB_002_was_green"
    assert regressions == ["F-010"]
    assert "REGRESSION F-010 (REQ-BBB-002)" in capsys.readouterr().out


def test_ADR_0011_changes_nothing_but_status_and_proving_test(tmp_path):
    entries = [
        _entry("F-001", "REQ-AAA-001", extra={"note": "an extra key must survive"}),
        _entry("F-002", "REQ-BBB-002"),
    ]
    ledger = _ledger(tmp_path, entries)
    before = json.loads(ledger.read_text(encoding="utf-8"))
    uf.apply(FIXTURE, ledger)
    raw_after = ledger.read_text(encoding="utf-8")
    after = json.loads(raw_after)
    # top-level key order and the _comment are intact; entry count and ids intact
    assert list(after.keys()) == list(before.keys()) == ["_comment", "features"]
    assert after["_comment"] == before["_comment"]
    assert [e["id"] for e in after["features"]] == [e["id"] for e in before["features"]]
    # every field other than status/proving_test is byte-identical, and key order per entry holds
    for b, a in zip(before["features"], after["features"]):
        assert list(a.keys()) == list(b.keys())
        for k in b:
            if k not in ("status", "proving_test"):
                assert a[k] == b[k], k
    # indent=2, trailing newline, and the file's escaping convention preserved (— stays escaped)
    assert raw_after.endswith("}\n")
    assert raw_after.startswith('{\n  "_comment"')
    assert "\\u2014" in raw_after


def test_ADR_0011_truncated_report_leaves_ledger_untouched(tmp_path):
    bad = tmp_path / "junit.xml"
    bad.write_text('<?xml version="1.0"?><testsuites><testsuite><testcase name="x"', encoding="utf-8")
    ledger = _ledger(tmp_path, [_entry("F-001", "REQ-AAA-001")])
    before = ledger.read_bytes()
    import xml.etree.ElementTree as ET
    with pytest.raises(ET.ParseError):
        uf.apply(bad, ledger)
    assert ledger.read_bytes() == before
    assert not (tmp_path / "features.json.tmp").exists()   # parse fails before any temp is written


def test_ADR_0011_whole_suite_command_is_fixed_and_strict():
    # B0: never -x, never -k; the whole tests/ tree, JUnit to the fixed path; xfail strict
    assert uf.PYTEST_CMD[:5] == ["python3", "-m", "pytest", "tests/", "-q"]
    assert "-x" not in uf.PYTEST_CMD and "-k" not in uf.PYTEST_CMD
    assert "xfail_strict=true" in uf.PYTEST_CMD
    assert uf.PYTEST_CMD[-1] == "--junitxml=/tmp/features_junit.xml"
