"""B12 §D.2/D.3 — the source cascade (REQ-NUT-012..016, REQ-NUT-024, REQ-NUT-036).

Pure orchestration, so every source is a stub and the ordering, refusals and brand rules are
tested without an API key, a socket, or Joe's USDA registration. Almost every test is about the
cascade declining to answer.
"""
import pytest

from tools.engines.nutrition_cascade import (BRANDED_SOURCES, Cooldowns, NotConfigured,
                                             RATE_LIMIT_COOLDOWN_S, RateLimited,
                                             SOURCE_PRECEDENCE, SourceUnavailable, Unresolved,
                                             resolvable_sources, resolve)


def knows(kcal, **extra):
    def fn(item_text, brand):
        return dict(kcal=kcal, canonical_name=item_text, **extra)
    return fn


def knows_nothing(item_text, brand):
    return None


def test_REQ_NUT_036_the_precedence_is_joe_then_branded_then_foundation_then_off():
    """Not ranked by convenience — ranked by how directly each source knows THIS food. Joe
    measured it; the manufacturer labelled this exact product; a lab analysed the generic food;
    a crowd typed in a label."""
    assert SOURCE_PRECEDENCE == ("joe", "usda_branded", "usda_foundation", "off_product")


def test_REQ_NUT_036_the_first_source_that_knows_the_food_wins():
    sources = {"joe": knows(101), "usda_branded": knows(202, brand_owner="X"),
               "usda_foundation": knows(303), "off_product": knows(404)}
    assert resolve("oats", sources)["kcal"] == 101
    del sources["joe"]
    assert resolve("oats", sources)["kcal"] == 202
    del sources["usda_branded"]
    assert resolve("oats", sources)["kcal"] == 303


def test_REQ_NUT_036_a_source_that_does_not_know_the_food_falls_through():
    """Returning None means "I do not know this food" and the cascade continues; it is not the
    same as the source being unable to answer."""
    r = resolve("oats", {"joe": knows_nothing, "usda_foundation": knows(303)})
    assert r["kcal"] == 303 and r["source"] == "usda_foundation"
    assert [t["outcome"] for t in r["tried"]][:1] == ["no_match"]


def test_REQ_NUT_016_a_branded_item_never_falls_back_to_a_generic_source():
    """The rule that matters most. "Chipotle chicken burrito" resolving to USDA's generic
    "burrito, chicken" is not a small error — a restaurant portion is routinely double the
    generic, and the number would look entirely ordinary on the plate."""
    sources = {"usda_branded": knows_nothing, "usda_foundation": knows(300),
               "off_product": knows_nothing}
    r = resolve("chicken burrito", sources, brand="Chipotle")
    assert isinstance(r, Unresolved), f"a generic source answered a branded item: {r}"
    outcomes = {t["source"]: t["outcome"] for t in r.tried}
    assert outcomes["usda_foundation"] == "skipped_generic_source_for_branded_item"
    assert "usda_foundation" not in BRANDED_SOURCES


def test_REQ_NUT_016_the_same_generic_source_answers_when_there_is_no_brand():
    """The exclusion is about the BRAND on the item, not about the source being untrusted."""
    sources = {"usda_foundation": knows(300)}
    assert resolve("chicken burrito", sources)["kcal"] == 300


def test_REQ_NUT_015_an_unmatched_restaurant_item_keeps_its_token_and_reaches_the_review_list():
    """An unresolved item is a question Joe can answer. A plausible wrong number is not."""
    r = resolve("chicken burrito", {"usda_branded": knows_nothing, "off_product": knows_nothing},
                brand="Chipotle")
    assert isinstance(r, Unresolved)
    assert r.status == "unresolved"
    assert r.reason == "no_source_match"
    assert r.review_reason == "no_source_match"
    assert r.item_text == "chicken burrito" and r.brand == "Chipotle", "both kept verbatim"


def test_REQ_NUT_024_could_not_find_it_and_could_not_look_are_different_refusals():
    """If no source was configured, every item is unresolved for a reason that has nothing to do
    with the food. Reporting that as `no_source_match` would hand Joe a review list of items
    nothing was ever going to resolve — an operations failure disguised as a data gap."""
    asked = resolve("oats", {"joe": knows_nothing})
    assert asked.reason == "no_source_match" and asked.review_reason == "no_source_match"

    could_not_look = resolve("oats", {})
    assert could_not_look.reason == "no_source_available"
    assert could_not_look.review_reason is None, "not Joe's to review"


def test_REQ_NUT_012_a_429_stops_that_source_for_sixty_minutes():
    """A rate limit is the provider saying stop. Retrying around it gets the key banned, and the
    failure mode of a banned key is every future item unresolved — so the polite failure is also
    the cheap one."""
    calls = []

    def limited(item_text, brand):
        calls.append(item_text)
        raise RateLimited("usda_branded", "HTTP 429")

    cd, sources = Cooldowns(), {"usda_branded": limited, "off_product": knows(404)}
    first = resolve("oats", sources, brand="B", cooldowns=cd, now=1000.0)
    assert first["source"] == "off_product", "the cascade continues past the limited source"
    assert cd.active("usda_branded", now=1000.0)
    assert cd.remaining("usda_branded", now=1000.0) == RATE_LIMIT_COOLDOWN_S

    resolve("rice", sources, brand="B", cooldowns=cd, now=2000.0)
    assert calls == ["oats"], "the limited source must not be called again during the cooldown"

    resolve("rice", sources, brand="B", cooldowns=cd, now=1000.0 + RATE_LIMIT_COOLDOWN_S + 1)
    assert calls == ["oats", "rice"], "and must be tried again once the hour is up"


def test_REQ_NUT_012_a_rate_limited_source_never_substitutes_a_different_food():
    """The requirement's own words: leave the item unresolved, do not substitute."""
    def limited(item_text, brand):
        raise RateLimited("usda_branded")

    r = resolve("chicken burrito", {"usda_branded": limited}, brand="Chipotle")
    assert isinstance(r, Unresolved)
    assert r.reason == "no_source_available", "nothing was successfully asked"


def test_REQ_NUT_014_a_branded_match_is_labelled_and_records_whose_label_it_was():
    """Without the brand owner a labelled figure cannot be re-checked against the product it came
    from, and `labelled` becomes a claim about precision with no referent."""
    r = resolve("burrito", {"usda_branded": knows(650, brand_owner="Chipotle Mexican Grill")},
                brand="Chipotle")
    assert r["estimate_method"] == "labelled"
    assert r["brand_owner"] == "Chipotle Mexican Grill"


def test_REQ_NUT_014_a_branded_match_without_a_brand_owner_is_a_defect_not_a_result():
    with pytest.raises(ValueError, match="REQ-NUT-014"):
        resolve("burrito", {"usda_branded": knows(650)}, brand="Chipotle")


def test_REQ_NUT_014_only_the_branded_source_claims_labelled():
    """A lab analysis of a generic food is not a label, and calling it one would let a
    `labelled` filter downstream return figures no manufacturer ever published."""
    r = resolve("oats", {"usda_foundation": knows(389)})
    assert r.get("estimate_method") != "labelled"


def test_REQ_NUT_012_an_unconfigured_source_is_recorded_and_skipped_without_error():
    """A missing USDA key must not crash the run or poison the other sources."""
    r = resolve("oats", {"off_product": knows(404)})
    outcomes = {t["source"]: t["outcome"] for t in r["tried"]}
    assert outcomes["joe"] == "not_configured"
    assert outcomes["usda_branded"] == "not_configured"
    assert r["source"] == "off_product"


def test_REQ_NUT_012_a_source_raising_unavailable_is_skipped_not_treated_as_a_miss():
    def broken(item_text, brand):
        raise SourceUnavailable("usda_foundation", "connection_reset", "socket hung up")

    r = resolve("oats", {"usda_foundation": broken})
    assert isinstance(r, Unresolved)
    assert r.reason == "no_source_available", "a broken source is not evidence about the food"
    # Looked up by source, not by position: the cascade keeps walking after a broken source,
    # so the last entry is whatever came after it, not the failure being tested.
    entry = next(t for t in r.tried if t["source"] == "usda_foundation")
    assert entry["outcome"] == "connection_reset"
    assert entry["detail"] == "socket hung up"


def test_REQ_NUT_036_every_attempt_is_recorded_on_the_answer_as_well_as_the_refusal():
    """A resolved item must still say what was tried, or "Joe's own figure" and "the fourth
    source we asked" become indistinguishable after the fact."""
    r = resolve("oats", {"joe": knows_nothing, "usda_foundation": knows(389)})
    assert [(t["source"], t["outcome"]) for t in r["tried"]] == [
        ("joe", "no_match"),
        ("usda_branded", "not_configured"),
        ("usda_foundation", "match")], r["tried"]


def test_resolvable_sources_explains_a_refusal_without_reordering_it():
    cd = Cooldowns()
    cd.trip("usda_branded", now=0.0)
    sources = {"joe": knows_nothing, "usda_branded": knows_nothing, "off_product": knows_nothing}
    assert resolvable_sources(sources, cd, now=10.0) == ("joe", "off_product")
    assert resolvable_sources(sources, cd, now=10.0, brand="X") == ("joe", "off_product")
    assert resolvable_sources({}, cd, now=10.0) == ()
