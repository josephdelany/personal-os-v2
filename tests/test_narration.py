"""B20 — the tier vocabulary linter (REQ-NAR-020..023, REQ-TIER-020; RULE-19, RULE-23).

A tier is a claim about how much is known, and vocabulary is how a tier leaks. "steps were
typically 2,206" and "steps increase HRV" can sit on the same evidence; only the second asserts
something the evidence cannot carry.
"""
import pytest

from tools.engines.narration import (MORALISING, STRUCTURAL_TERMS, TIER_ORDER, check_templates,
                                     lint, moralising, rank)

V = {
    "DESCRIPTIVE": ["was", "were", "typically", "median", "highest", "on"],
    "EXPLORATORY": ["may", "might", "candidate", "unverified"],
    "PROMOTED": ["appears", "consistent with", "watched"],
    "CONFIRMED_OBSERVATIONAL": ["increases", "decreases", "adjusted for", "per"],
    "EXPERIMENTAL": ["causes", "caused"],
}


def test_REQ_NAR_020_a_claim_using_only_its_own_tiers_words_passes():
    assert lint("Your steps was typically 2206.", "DESCRIPTIVE", V) == ()


def test_REQ_NAR_021_a_term_from_a_higher_tier_is_a_violation():
    """The whole point: the tiers are enforced in the data all the way down, and then one verb
    undoes it."""
    (v,) = lint("Sleep causes higher HRV.", "EXPLORATORY", V)
    assert (v.term, v.term_tier, v.claim_tier) == ("causes", "EXPERIMENTAL", "EXPLORATORY")
    assert v.rule == "vocabulary_above_tier"


def test_REQ_NAR_021_the_same_term_at_its_own_tier_is_permitted():
    assert lint("Sleep causes higher HRV.", "EXPERIMENTAL", V) == ()


def test_REQ_NAR_021_a_term_from_a_LOWER_tier_is_not_a_violation():
    """A confirmed finding may still say "was". Reserving downward would forbid plain language
    at exactly the tiers that have earned the right to be plain."""
    assert lint("HRV was higher and sleep increases it.", "EXPERIMENTAL", V) == ()


def test_REQ_NAR_021_the_month_of_may_does_not_discard_a_correct_answer():
    """"may" is EXPLORATORY vocabulary and also a month. A case-insensitive match would discard
    a true DESCRIPTIVE answer and write a violation row about it — a linter that silences true
    statements is worse than none, because the failure is invisible and reads as reticence."""
    assert lint("Your steps was typically 2206 over 1 May to 30 May.", "DESCRIPTIVE", V) == ()
    (v,) = lint("Your steps may be higher.", "DESCRIPTIVE", V)
    assert v.term == "may", "the modal must still be caught in lower case"


def test_REQ_NAR_021_a_word_is_matched_whole_and_not_as_a_fragment():
    """"increases" is CONFIRMED_OBSERVATIONAL. "increased" and "decreased" in a descriptive
    sentence must not trip it, and neither must a substring inside a longer word."""
    assert lint("The percentage was highest on Tuesday.", "DESCRIPTIVE", V) == ()
    assert lint("Caused-by analysis is unavailable.", "DESCRIPTIVE", V), (
        "a real occurrence of a reserved word must still be caught")


def test_REQ_NAR_021_a_multi_word_term_is_matched_as_a_phrase():
    (v,) = lint("Sleep, adjusted for weekday, was higher.", "DESCRIPTIVE", V)
    assert v.term == "adjusted for"


def test_REQ_NAR_021_a_structural_preposition_is_not_a_reservation():
    """REQ-NAR-021 reserves "a verb or qualifier". The live INSUFFICIENT copy — "There is not
    enough data ON {display}" — was flagged for a preposition, which would have failed the
    build on correct text."""
    assert "on" in STRUCTURAL_TERMS
    assert lint("There is not enough data on Steps to make this claim.",
                "INSUFFICIENT", V) == ()
    assert "per" not in STRUCTURAL_TERMS, (
        "a rate word can carry a claim and must stay a reservation")


def test_REQ_TIER_020_the_ladder_is_ordered_lowest_first():
    assert rank("INSUFFICIENT") < rank("DESCRIPTIVE") < rank("EXPLORATORY")
    assert rank("EXPLORATORY") < rank("PROMOTED") < rank("CONFIRMED_OBSERVATIONAL")
    assert rank("CONFIRMED_OBSERVATIONAL") < rank("EXPERIMENTAL")
    assert TIER_ORDER[0] == "INSUFFICIENT" and TIER_ORDER[-1] == "EXPERIMENTAL"


def test_REQ_TIER_020_an_unknown_tier_is_refused_rather_than_treated_as_the_lowest():
    """Defaulting an unrecognised tier to the bottom would silently permit every term."""
    with pytest.raises(ValueError, match="unknown tier"):
        lint("anything", "VERY_SURE", V)


def test_REQ_NAR_023_the_moralising_wordlist_is_the_one_the_requirement_names():
    """A spending or screen-time figure is not a character judgement (RULE-23)."""
    for term in ("excessive", "wasteful", "necessary", "unnecessary", "too much",
                 "splurge", "guilty"):
        assert term in MORALISING, term
    assert moralising("That was an excessive splurge.") == ("excessive", "splurge")
    assert moralising("Your spend was 1262.14 usd.") == ()


def test_REQ_NAR_023_unnecessary_does_not_hide_inside_a_longer_word():
    assert moralising("The necessary paperwork") == ("necessary",)
    assert moralising("unnecessarily") == (), "a fragment is not the banned term"


def test_REQ_NAR_022_a_template_is_linted_against_the_tier_it_is_declared_for():
    """A template is a promise about every answer it will ever produce, so the breach is found
    at build time rather than on the day it is read."""
    clean = check_templates([("DESCRIPTIVE", "Your {display} was typically {median}.")], V)
    assert clean == ()
    bad = check_templates([("DESCRIPTIVE", "Your {display} causes {other}.")], V)
    assert len(bad) == 1 and bad[0][2].term == "causes"


# ---------------------------------------------------------------- REQ-NAR-025 / RULE-24

def test_REQ_NAR_025_a_streak_is_never_rendered():
    """A streak makes a missing day a failure. Joe's capture has stopped twice this year
    through no act of his — the Watch on 2026-08-21 and the bank export on 2026-05-13 — and a
    streak would have scored both as lapses of his."""
    from tools.engines.narration import forbidden_surface
    assert forbidden_surface("7 day streak!") == ("streak",)
    assert forbidden_surface("4 days in a row") == ("streak",)
    assert forbidden_surface("12 consecutive days logged") == ("streak",)


def test_REQ_NAR_025_a_compliance_or_composite_score_is_never_rendered():
    """A compliance score measures obedience to a plan rather than what happened. A composite
    averages incomparable measures into one number whose movement cannot be attributed to
    anything — and whose inputs here have wildly different coverage, so it would silently
    become a proxy for whichever input still has data."""
    from tools.engines.narration import forbidden_surface
    assert forbidden_surface("your compliance was 82%") == ("compliance_score",)
    assert forbidden_surface("your wellness score is 82") == ("composite_score",)
    assert forbidden_surface("readiness score: 61") == ("composite_score",)


def test_REQ_NAR_025_a_celebration_is_never_rendered():
    """A celebration attaches an emotional reward to a number, which is what makes a metric
    worth gaming."""
    from tools.engines.narration import forbidden_surface
    assert forbidden_surface("Congratulations! 🎉") == ("celebration",)
    assert forbidden_surface("Nice work, keep it up") == ("celebration",)


def test_REQ_NAR_025_a_plain_descriptive_sentence_is_not_flagged():
    """A detector that fires on ordinary copy is noise, and noise is ignored precisely when it
    matters."""
    from tools.engines.narration import forbidden_surface
    for ok in ("Your Steps was typically 2206 count over the last 30 days.",
               "Charges matching \"Hannaford\" total 1262.14 usd across 30 charges.",
               "There is not enough data on HRV to make this claim."):
        assert forbidden_surface(ok) == (), ok


def test_REQ_NAR_025_no_live_template_or_string_renders_a_banned_surface():
    """The build-time half. A template is a promise about every answer it will ever produce."""
    from tools.engines.narration import forbidden_surface
    import pathlib
    sql = pathlib.Path(__file__).resolve().parents[1].joinpath(
        "migrations/0049_ask_core.sql").read_text()
    templates = [line for line in sql.splitlines()
                 if "'DESCRIPTIVE','" in line or "'INSUFFICIENT','" in line]
    assert templates, "the template seed must be present for this to mean anything"
    for line in templates:
        assert forbidden_surface(line) == (), line[:100]
