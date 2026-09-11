"""B17 §C.1 — necessity is a tier, not a fact (REQ-FIN-110..116)."""
import datetime as dt

import pytest

from tools.engines.usage_status import (DEFAULT_TIER, FORBIDDEN_WORDS, ForbiddenJudgement, TIERS,
                                        UsageStatus, as_interval, automated_update, from_evidence, guard_words,
                                        guard_words, initial_status, override)

AS_OF = dt.date(2026, 9, 10)


def test_REQ_FIN_110_usage_status_is_three_tiers_never_a_boolean_or_a_score():
    """A boolean forces every purchase into used-or-not, and the overwhelming majority are
    neither. "68% used" is a number with no referent — there is nothing it is 68% of."""
    assert TIERS == ("used", "unused", "unknown")
    with pytest.raises(ValueError, match="REQ-FIN-110"):
        UsageStatus("gym", True, "e", "inferred", 0.5)
    with pytest.raises(ValueError, match="REQ-FIN-110"):
        UsageStatus("gym", "0.68", "e", "inferred", 0.5)


def test_REQ_FIN_111_everything_starts_unknown_and_says_why():
    s = initial_status("gym membership")
    assert s.tier == DEFAULT_TIER == "unknown"
    assert "No usage evidence" in s.evidence


def test_REQ_FIN_111_no_evidence_is_unknown_not_unused():
    """A gym membership with no place_visit rows is not an unused gym membership; it is one
    about which nothing is recorded, and those license entirely different sentences."""
    assert from_evidence("gym", [], as_of=AS_OF).tier == "unknown"


def test_REQ_FIN_113_a_status_names_the_evidence_that_produced_it():
    """"Unused" alone is an accusation. "Last gym place_visit 71 days ago" is a fact Joe can
    confirm, correct or explain.

    `source_last_seen` is now required to reach 'unused' at all (R4): the source kept recording
    for ten weeks after that last visit and registered none, which is what makes the silence a
    fact about Joe rather than about the logger. The assertion is unchanged; what changed is
    that the test has to say what was watching.
    """
    rows = [{"day": AS_OF - dt.timedelta(days=71), "kind": "place_visit"}]
    s = from_evidence("gym", rows, as_of=AS_OF, source_last_seen=AS_OF - dt.timedelta(days=1))
    assert s.tier == "unused"
    assert "last gym place_visit 71 days ago" in s.evidence
    assert "(2026-07-01)" in s.evidence


# --- INTENT_COVERAGE R4: an outage is not proof of nonuse -------------------------------

def test_REQ_REC_009_a_dead_source_is_unknown_not_unused():
    """THE R4 CASE. The gym visits stopped because the logger stopped, not because Joe did.

    Same evidence as the test above -- one visit, 71 days ago -- and the opposite answer,
    because the thing that would have recorded a visit went silent on the same day. The Watch
    stopped in five stages ending 2026-08-21 and the bank CSV export died 2026-05-13, so this
    is the ordinary case in this system rather than an edge one.
    """
    last_visit = AS_OF - dt.timedelta(days=71)
    s = from_evidence("gym", [{"day": last_visit, "kind": "place_visit"}],
                      as_of=AS_OF, source_last_seen=last_visit)
    assert s.tier == "unknown", "nothing was watching, so nothing was observed"
    assert s.tier != "unused"
    assert "the gap is the source's" in s.evidence
    # REQ-FIN-114: an inferred status carries confidence below 1.0, and this one knows nothing.
    assert s.confidence == 0.0 and s.provenance == "inferred"


def test_REQ_REC_009_an_unestablished_source_cannot_produce_an_accusation():
    """The permissive default was the bug. A caller who never considered continuity used to get
    'unused' silently; it now gets 'unknown' and is told why."""
    s = from_evidence("gym", [{"day": AS_OF - dt.timedelta(days=71), "kind": "place_visit"}],
                      as_of=AS_OF)
    assert s.tier == "unknown"
    assert "no continuity was established" in s.evidence


def test_REQ_FIN_111_a_watching_source_that_saw_nothing_does_support_unused():
    """The other half, so the fix is not just 'always unknown'. An outage-aware engine that can
    never conclude 'unused' has replaced one wrong answer with another."""
    last_visit = AS_OF - dt.timedelta(days=90)
    s = from_evidence("gym", [{"day": last_visit, "kind": "place_visit"}],
                      as_of=AS_OF, source_last_seen=AS_OF - dt.timedelta(days=2))
    assert s.tier == "unused"
    assert "kept recording for 88 days afterwards" in s.evidence


def test_REQ_FIN_112_the_outage_wording_carries_no_forbidden_judgement():
    """Every branch's evidence string passes the REQ-FIN-112 guard, including the new ones."""
    last_visit = AS_OF - dt.timedelta(days=71)
    for kwargs in ({}, {"source_last_seen": last_visit},
                   {"source_last_seen": AS_OF - dt.timedelta(days=2)}):
        s = from_evidence("gym", [{"day": last_visit, "kind": "place_visit"}],
                          as_of=AS_OF, **kwargs)
        assert guard_words(s.evidence) is True


def test_REQ_FIN_113_a_bare_label_is_refused():
    with pytest.raises(ValueError, match="REQ-FIN-113"):
        UsageStatus("gym", "unused", "", "inferred", 0.4)


def test_REQ_FIN_111_recent_evidence_is_used():
    rows = [{"day": AS_OF - dt.timedelta(days=3), "kind": "place_visit"}]
    assert from_evidence("gym", rows, as_of=AS_OF).tier == "used"


def test_REQ_FIN_114_confidence_falls_with_the_age_of_the_evidence():
    """A visit yesterday says more about today than one eleven weeks ago, and reporting both at
    the same confidence would flatten that."""
    fresh = from_evidence("gym", [{"day": AS_OF - dt.timedelta(days=2), "kind": "v"}],
                          as_of=AS_OF)
    stale = from_evidence("gym", [{"day": AS_OF - dt.timedelta(days=300), "kind": "v"}],
                          as_of=AS_OF)
    assert fresh.confidence > stale.confidence
    assert fresh.provenance == "inferred" and fresh.confidence < 1.0


def test_REQ_FIN_112_the_five_words_may_not_be_written_stored_displayed_or_exported():
    """Not softened, not gated behind a tier: banned. Each asserts a judgement about how Joe
    should live that no transaction record can support."""
    for w in FORBIDDEN_WORDS:
        with pytest.raises(ForbiddenJudgement, match="REQ-FIN-112"):
            guard_words(f"this looks {w}")
    assert guard_words("last gym place_visit 71 days ago")


def test_REQ_FIN_112_the_ban_is_enforced_on_the_status_object_itself():
    """Enforced on write rather than filtered on display: a stored word leaks into an export or
    a prompt later."""
    with pytest.raises(ForbiddenJudgement):
        UsageStatus("gym", "unused", "an unnecessary purchase", "inferred", 0.4)


def test_REQ_FIN_112_whole_word_matching_so_ordinary_copy_survives():
    assert guard_words("Necessarily approximate")
    assert guard_words("needing nothing")


def test_REQ_FIN_114_an_inferred_status_may_not_claim_certainty():
    """Certainty is reserved for Joe."""
    with pytest.raises(ValueError, match="REQ-FIN-114"):
        UsageStatus("gym", "unused", "e", "inferred", 1.0)


def test_REQ_FIN_114_the_human_override_representation_is_left_to_OQ_32():
    """REQ-FIN-114 says so in its own text: whether the override is extracted+supersedes or needs
    its own marker is "a modeling decision for Joe, not a spelling reconciliation". The code
    refuses any third provenance rather than inventing one."""
    with pytest.raises(ValueError, match="OQ-32"):
        UsageStatus("gym", "unused", "e", "extracted", 1.0)


def test_REQ_FIN_115_joe_s_override_is_permanent_and_supersedes_rather_than_replaces():
    inferred = from_evidence("gym", [{"day": AS_OF - dt.timedelta(days=71), "kind": "v"}],
                             as_of=AS_OF)
    o = override(inferred, "used", note="I go, I just do not tap in")
    assert o.tier == "used" and o.provenance == "joe" and o.confidence == 1.0
    assert o.supersedes == inferred.evidence, "what the system thought before still has an answer"
    with pytest.raises(ValueError, match="REQ-FIN-115"):
        automated_update(o, inferred)
    assert automated_update(inferred, o) is o, "an inferred status may still be updated"


def test_REQ_FIN_116_an_inferred_quantity_is_an_interval_never_a_point():
    """A point estimate of something nobody measured states a precision the method does not
    have, and a single number is what a reader remembers."""
    assert as_interval(3, 6) == {"low": 3, "high": 6, "kind": "inferred"}
    with pytest.raises(ValueError, match="REQ-FIN-116"):
        as_interval(4, 4)
    with pytest.raises(ValueError, match="REQ-FIN-116"):
        as_interval(6, 3)


def test_REQ_FIN_116_an_observed_quantity_is_a_point_because_it_was_measured():
    """The rule is about inference, not about formatting."""
    assert as_interval(4, 4, observed=True) == {"value": 4, "kind": "observed"}
