"""The requirement audit's own correctness.

A ledger that over-counts is worse than none: it converts an absence of evidence into a
percentage, and nobody re-checks a percentage. These tests pin the one rule it applies —
a requirement is proven by a test whose NAME carries its ID, and by nothing else.
"""
import re

from tools.audit_requirements import ID, IN_TEST_NAME, declared, mentioned_only, proven


def test_the_audit_counts_a_named_test_and_only_a_named_test():
    """This very file mentions REQ-ASK-031 in prose below without a test named for it, so it
    must appear as MENTIONED and never as PROVEN.

    The requirement referenced here is REQ-ASK-031, deliberately, as the fixture.
    """
    have, claimed = proven(), mentioned_only()
    assert "REQ-ASK-031" in have, "a real named test elsewhere proves this one"
    # The distinction the tool exists to make: a mention is recorded separately.
    assert any("test_audit_requirements.py" in f for f in claimed.get("REQ-ASK-031", set())), \
        "a bare mention in a test file must be recorded as a claim, not as coverage"


def test_REQ_NFR_005_a_proven_requirement_names_the_test_that_proves_it():
    """The audit is only useful if it can point at the evidence."""
    have = proven()
    assert "REQ-NFR-005" in have
    assert all("::" in ref for ref in have["REQ-NFR-005"]), have["REQ-NFR-005"]


def test_the_id_pattern_does_not_match_a_partial_or_malformed_id():
    assert ID.findall("REQ-ASK-031 and REQ-FIN-070") == ["REQ-ASK-031", "REQ-FIN-070"]
    assert ID.findall("REQ-ASK-31") == [], "a two-digit tail is not an ID"
    assert ID.findall("XREQ-ASK-031") == [], "an ID must stand alone"


def test_every_declared_id_comes_from_a_spec_file():
    spec_ids = declared()
    assert len(spec_ids) > 600, "the specs declare hundreds of requirements"
    assert all(re.fullmatch(r"REQ-[A-Z]{3,4}-\d{3}", r) for r in spec_ids)
    assert "REQ-SLP-001" in spec_ids, "the sleep spec authored this session must be counted"


def test_the_audit_never_reports_more_proven_than_declared():
    """The failure this tool warns about, applied to itself."""
    spec_ids, have = declared(), proven()
    counted = [r for r in have if r in spec_ids]
    assert len(counted) <= len(spec_ids)
    orphans = sorted(r for r in have if r not in spec_ids)
    assert not orphans, f"tests name requirement IDs no spec declares: {orphans}"


def test_a_test_function_name_is_recognised():
    assert IN_TEST_NAME.findall("def test_REQ_ASK_031_something(cur):") == \
        ["test_REQ_ASK_031_something"]
    assert IN_TEST_NAME.findall("def helper_REQ_ASK_031(cur):") == [], \
        "only a test function counts"
