"""B14.1 — descriptor normalisation and the merchant resolution cascade.

REQ-FIN-060..062, REQ-FIN-070..074, RULE-06, RULE-10.

No personal data: every descriptor below is invented in the shape a card statement produces,
which is what RULE-01 permits — these are not rows in any table and describe nobody.
"""
import pytest

from tools.engines.merchants import (FUZZY_FLOOR, Pattern, classify_non_merchant, confirm,
                                     discover_location_tokens, normalize, resolve)

PATTERNS = [
    Pattern("BLUE BOTTLE COFFEE", "Blue Bottle"),
    Pattern(r"^SHELL\b", "Shell", is_regex=True, specificity=10),
    Pattern(r"^SH", "Generic Shop", is_regex=True, specificity=1),
]
KNOWN = ["Blue Bottle", "Shell", "Sweetgreen", "Generic Shop"]


def test_REQ_FIN_060_the_normalizer_strips_facilitators_digits_and_the_state(): 
    n = normalize("SQ *BLUE BOTTLE COFFEE 123 OAKLAND CA")
    assert n.normalized == "BLUE BOTTLE COFFEE OAKLAND"
    assert "facilitator_sq" in n.rules_fired and "trailing_state" in n.rules_fired


def test_REQ_FIN_061_the_raw_descriptor_is_preserved_verbatim():
    raw = "TST* Sweetgreen #0421 New York NY"
    n = normalize(raw)
    assert n.raw == raw, "the original must survive normalisation unchanged"
    assert n.normalized != raw


def test_REQ_FIN_062_the_rules_that_fired_are_recorded_in_order():
    """"We normalised it somehow" is not provenance. Which rules fired, in order, is."""
    n = normalize("SQ *SHOP #42 555-123-4567 AUSTIN TX")
    assert n.rules_fired[0] == "facilitator_sq", n.rules_fired
    assert "store_number" in n.rules_fired and "phone_number" in n.rules_fired
    assert list(n.rules_fired) == sorted(set(n.rules_fired), key=list(n.rules_fired).index)


def test_REQ_FIN_070_an_exact_pattern_wins_at_confidence_one_and_stops_the_cascade():
    r = resolve("BLUE BOTTLE COFFEE", PATTERNS, KNOWN)
    assert (r.canonical, r.merchant_source, r.confidence) == ("Blue Bottle", "pattern_exact", 1.0)
    assert r.considered == (), "a later step ran after an exact match"


def test_REQ_FIN_071_regex_patterns_are_evaluated_in_descending_specificity():
    """Both `^SHELL` and `^SH` match "SHELL OIL". The specific one must win, or a broad
    catch-all rule silently swallows every merchant that happens to share two letters."""
    r = resolve("SHELL OIL", PATTERNS, KNOWN)
    assert (r.canonical, r.merchant_source) == ("Shell", "pattern_regex")


def test_REQ_FIN_072_fuzzy_assigns_only_at_or_above_the_floor_and_the_ratio_is_the_confidence():
    """A one-character typo clears the floor; the stored confidence is the actual ratio, not
    a rounded-up 1.0, so a near-match never looks like a certainty."""
    r = resolve("SWEETGREN", PATTERNS, KNOWN)          # one letter missing
    assert r.merchant_source == "fuzzy" and r.canonical == "Sweetgreen"
    assert FUZZY_FLOOR <= r.confidence < 1.0, r.confidence

    # An exact string match against a known name is still reached by comparison, not by a
    # pattern, and it says so: source `fuzzy`, ratio 1.0. Both facts are true and both matter.
    exact = resolve("SWEETGREEN", PATTERNS, KNOWN)
    assert (exact.merchant_source, exact.confidence) == ("fuzzy", 1.0)

    # Just below the floor must NOT assign, or the threshold is decorative.
    below = resolve("SWXXTGRXX", PATTERNS, KNOWN)
    assert below.merchant_source == "provisional"


def test_REQ_FIN_073_below_the_floor_it_is_provisional_and_never_becomes_a_pattern():
    """The dangerous version writes the guess into merchant_patterns, so the NEXT identical
    descriptor resolves as pattern_exact at confidence 1.0 — a guess laundered into a fact
    with no record that it ever was one."""
    r = resolve("ZZQQ UNKNOWN THING", PATTERNS, KNOWN)
    assert r.merchant_source == "provisional"
    assert r.needs_review is True and r.unconfirmed is True
    assert r.confidence is None, "a provisional merchant has no confidence to report"
    assert not any(p.pattern == "ZZQQ UNKNOWN THING" for p in PATTERNS), \
        "the provisional descriptor must not have been written into the pattern set"


def test_REQ_FIN_073_the_alternatives_it_rejected_are_disclosed():
    """RULE-18: what it nearly matched is part of an honest refusal."""
    r = resolve("SWEETGRXX", PATTERNS, KNOWN)
    assert r.considered, "it rejected candidates without saying which"
    assert all(score < FUZZY_FLOOR for _, score in r.considered)


def test_RULE_10_a_human_correction_outranks_every_automated_step():
    """Permanently, and without consulting anything below it. An exact pattern says
    Blue Bottle; Joe says otherwise; Joe wins."""
    r = resolve("BLUE BOTTLE COFFEE", PATTERNS, KNOWN, human_alias="The Roastery")
    assert (r.canonical, r.merchant_source, r.confidence) == ("The Roastery", "human", 1.0)


def test_REQ_FIN_074_confirmation_is_what_promotes_a_provisional_into_a_pattern():
    p = confirm("zzqq unknown thing", "Corner Store")
    assert (p.pattern, p.canonical, p.is_regex) == ("ZZQQ UNKNOWN THING", "Corner Store", False)
    with pytest.raises(ValueError, match="REQ-FIN-074"):
        confirm("something", "")


def test_RULE_06_an_empty_descriptor_is_a_gap_not_a_merchant_named_nothing():
    for empty in ("", "   ", None):
        r = resolve(normalize(empty).normalized, PATTERNS, KNOWN)
        assert r.canonical is None and r.needs_review is True


def test_REQ_FIN_060_the_city_vocabulary_is_discovered_not_guessed():
    """A token following MANY different merchants is a city; one following a single merchant
    is part of its name. That is why this is learned from the data rather than hard-coded:
    a gazetteer is a dependency, and a guess silently merges two merchants."""
    sample = ["SHELL OIL 111 HOUSTON TX", "KROGER 222 HOUSTON TX", "CVS 333 HOUSTON TX",
              "TARGET 444 HOUSTON TX", "JOES GARAGE HOUSTON TX",
              "BLUE BOTTLE COFFEE OAKLAND CA"]
    loc = discover_location_tokens(sample)
    assert "HOUSTON" in loc, "a token after four distinct merchants is a city"
    assert "OAKLAND" not in loc, "a token after one merchant is not yet evidence"
    assert "GARAGE" not in loc
    assert normalize("JOES GARAGE HOUSTON TX", loc).normalized == "JOES GARAGE"
    assert normalize("BLUE BOTTLE COFFEE OAKLAND CA", loc).normalized == \
        "BLUE BOTTLE COFFEE OAKLAND", "an unlearned token must not be stripped"


def test_REQ_FIN_060_thin_input_learns_nothing_rather_than_guessing():
    assert discover_location_tokens(["SHELL OIL HOUSTON TX"]) == frozenset()


def test_RULE_06_a_descriptor_that_is_only_a_city_is_not_stripped_to_nothing():
    loc = frozenset({"HOUSTON"})
    assert normalize("HOUSTON TX", loc).normalized == "HOUSTON", \
        "stripping to empty would turn an unresolvable descriptor into a merchant called ''"


def test_REQ_FIN_060_one_supermarket_under_many_descriptors_becomes_one_merchant():
    """The real failure this fixes. Chase embeds the purchase DATE and a truncated "Purchase"
    in the descriptor, and the store code is not always digits. One pass over the rules left
    a single supermarket as THREE merchants — "Hannaford", "Hannaford Waterville Me 10 14"
    and "Hannaford El" — because stripping the date exposes the state, stripping the state
    exposes the city, and each needed the previous one to have run first."""
    loc = frozenset({"WATERVILLE"})
    forms = {normalize(d, loc).normalized for d in (
        "HANNAFORD #8229 WATERVILLE ME /17",
        "HANNAFORD #8229 WATERVILLE ME 10/14 Purc",
        "HANNAFORD # EL WATERVILLE ME 01/23 Purch",
        "HANNAFORD #8238 WATERVILLE ME 04/04 Purc")}
    assert forms == {"HANNAFORD"}, forms


def test_REQ_FIN_060_the_rules_are_applied_to_a_fixed_point_not_once():
    """A single pass is order-dependent and silently wrong. This asserts the property, not a
    particular string: normalising an already-normalised value must change nothing."""
    once = normalize("HANNAFORD #8229 WATERVILLE ME 10/14 Purc", frozenset({"WATERVILLE"}))
    twice = normalize(once.normalized, frozenset({"WATERVILLE"}))
    assert twice.normalized == once.normalized


def test_REQ_FIN_051_an_atm_withdrawal_is_not_a_merchant():
    """Its destination is unknown by definition — the cash went somewhere the bank cannot see.
    Naming it puts it in category rollups REQ-FIN-051 explicitly excludes it from, and
    "Non Chase Atm Withdraw Main" is not a shop."""
    assert classify_non_merchant("NON-CHASE ATM WITHDRAW MAIN ST") == "atm"
    assert classify_non_merchant("Online Transfer from CHK transaction#:") == "transfer"
    assert classify_non_merchant("NON-CHASE ATM FEE-WITH") in ("atm", "fee")
    assert classify_non_merchant("HANNAFORD #8229") is None

    r = resolve("NON CHASE ATM WITHDRAW MAIN", [], ["Hannaford"],
                raw="NON-CHASE ATM WITHDRAW MAIN ST")
    assert r.merchant_source == "not_a_merchant" and r.non_merchant_kind == "atm"
    assert r.canonical is None, "a non-purchase must not acquire a merchant name"
    assert r.needs_review is False, (
        "its disposition is known; queueing it would bury the descriptors that need Joe")


def test_REQ_FIN_051_the_classification_is_offered_the_raw_descriptor():
    """The check runs on the ORIGINAL when one is supplied, so a future normalisation rule
    cannot silently reclassify a transfer as a merchant by stripping the token that identifies
    it. Today's rules happen to preserve that token — asserted below so the day they stop is
    a visible change — but the resolver does not depend on their continuing to."""
    raw = "Online Transfer from CHK transaction#: 12345"
    assert classify_non_merchant(raw) == "transfer"
    assert classify_non_merchant(normalize(raw).normalized) == "transfer", (
        "today's rules preserve the marker; if this ever fails, normalisation changed and the "
        "raw-descriptor path below is what keeps the classification correct")

    # The property that matters: `raw` wins when given. A normalised form that looks like an
    # ordinary merchant is still classified from the original.
    assert resolve("SOME SHOP", [], ["Some Shop"], raw=raw).merchant_source == "not_a_merchant"
    assert resolve("SOME SHOP", [], ["Some Shop"]).merchant_source != "not_a_merchant"


# ---------------------------------------------------------------- schema (migration 0057)

import os as _os
import re as _re

from tests._sql_fixture import ROOT, sql_connection          # noqa: E402
from tools.run_migration import split_statements             # noqa: E402

_S = "ent_core_pytest"


@pytest.fixture
def ent(sql_connection):
    if not _os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds schemas from migration DDL; disposable local server only")
    c = sql_connection.cursor()
    for schema in (_S, "config_pytest"):
        c.execute(f"CREATE SCHEMA {schema}")
    for role in ("anon", "authenticated"):
        c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if c.fetchone() is None:
            c.execute(f"CREATE ROLE {role}")
    for filename, keep in (("0003_entities.sql", None),
                           # 0014 also constrains atoms, which this fixture does not build.
                           ("0014_ontology_checks.sql", "__CORE__.entities"),
                           ("0057_entities_and_merchants.sql", None)):
        for statement in split_statements((ROOT / "migrations" / filename).read_text()):
            if keep and keep not in statement:
                continue
            c.execute(_re.sub(r"\bconfig\.", "config_pytest.", statement.replace("__CORE__", _S)))
    return c


def _alias(c, **kw):
    base = dict(alias="SOME MERCHANT", canonical="Some Merchant",
                resolved_by="pattern_exact", confidence=1.0)
    base.update(kw)
    cols = ", ".join(base)
    c.execute(f"INSERT INTO {_S}.entity_aliases ({cols}) "
              f"VALUES ({', '.join(['%s'] * len(base))}) RETURNING alias_id", tuple(base.values()))
    return c.fetchone()[0]


def test_REQ_ONT_005_the_taxonomy_is_enforced_once_by_its_original_constraint(ent):
    """0014_ontology_checks.sql has enforced this closed six since Phase 2. 0057 adds nothing:
    an earlier draft duplicated it under a second name, which broke
    test_REQ_ONT_002_entity_type_taxonomy_enforced — a test that asserts the constraint BY
    NAME. Two constraints saying the same thing is not belt and braces; it is two places to
    change and one of them will be forgotten."""
    ent.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        ent.execute(f"""INSERT INTO {_S}.entities (entity_type, canonical_name, provenance)
                        VALUES ('spaceship','X','human')""")
    assert "entities_type_taxonomy" in str(e.value), str(e.value)
    ent.execute("ROLLBACK TO SAVEPOINT s")
    ent.execute("""SELECT count(*) FROM pg_constraint c
                    WHERE c.conrelid = %s::regclass AND c.contype = 'c'
                      AND pg_get_constraintdef(c.oid) LIKE '%%entity_type%%'""", (f"{_S}.entities",))
    assert ent.fetchone()[0] == 1, "the taxonomy must be enforced in exactly one place"
    for good in ("merchant", "place", "food", "person", "media_channel", "website"):
        ent.execute(f"""INSERT INTO {_S}.entities (entity_type, canonical_name, provenance)
                        VALUES (%s,'X','human')""", (good,))


def test_RULE_10_an_automated_resolution_may_not_supersede_a_human_correction(ent):
    """Without this the next hourly run reverts every correction Joe made, and the ledger
    presents that as an improvement."""
    joe = _alias(ent, resolved_by="human", canonical="The Roastery")
    ent.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        _alias(ent, resolved_by="fuzzy", confidence=0.9, supersedes=joe)
    assert "RULE-10" in str(e.value)
    ent.execute("ROLLBACK TO SAVEPOINT s")
    _alias(ent, resolved_by="human", canonical="Corrected Again", supersedes=joe)


def test_INV_2_an_alias_is_appended_never_edited(ent):
    a = _alias(ent)
    for verb in (f"UPDATE {_S}.entity_aliases SET canonical='X' WHERE alias_id='{a}'",
                 f"DELETE FROM {_S}.entity_aliases WHERE alias_id='{a}'"):
        ent.execute("SAVEPOINT s")
        with pytest.raises(Exception) as e:
            ent.execute(verb)
        assert "INV-2" in str(e.value) or "RULE-02" in str(e.value)
        ent.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_FIN_073_a_provisional_resolution_carries_no_confidence(ent):
    """A number here reads downstream as evidence, and there is none."""
    ent.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        _alias(ent, resolved_by="provisional", confidence=0.5, unconfirmed=True)
    assert "provisional_has_no_confidence" in str(e.value)
    ent.execute("ROLLBACK TO SAVEPOINT s")
    _alias(ent, resolved_by="provisional", confidence=None, unconfirmed=True)


def test_REQ_FIN_071_a_regex_pattern_must_declare_its_specificity(ent):
    """Two regexes can match one descriptor; without an explicit order the winner is whatever
    the planner returned first, which is not a decision anyone made."""
    ent.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        ent.execute("""INSERT INTO config_pytest.merchant_patterns
                       (pattern, canonical, is_regex, specificity, provenance)
                       VALUES ('^SH','Generic',true,0,'seed')""")
    assert "specificity" in str(e.value)
    ent.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_FIN_060_a_location_token_cannot_be_recorded_without_evidence(ent):
    ent.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        ent.execute("""INSERT INTO config_pytest.location_tokens (token, distinct_prefixes)
                       VALUES ('HOUSTON', 1)""")
    assert "a_location_token_needs_evidence" in str(e.value)
    ent.execute("ROLLBACK TO SAVEPOINT s")
    ent.execute("""INSERT INTO config_pytest.location_tokens (token, distinct_prefixes)
                   VALUES ('HOUSTON', 4)""")


def test_RULE_10_the_current_view_returns_only_the_head_of_the_chain(ent):
    first = _alias(ent, canonical="Guessed")
    second = _alias(ent, resolved_by="human", canonical="Corrected", supersedes=first)
    ent.execute(f"SELECT alias_id, canonical FROM {_S}.v_current_aliases")
    rows = list(ent.fetchall())
    assert rows == [[second, "Corrected"]], rows
    ent.execute(f"SELECT count(*) FROM {_S}.entity_aliases")
    assert ent.fetchone()[0] == 2, "the earlier resolution must remain readable"


# ---------------------------------------------------------------- B14.2: entities and links

def test_REQ_FIN_073_a_provisional_resolution_earns_no_edge():
    """An unlinked transaction is a visible gap; a linked guess is an invisible error, and the
    second is far harder to notice six months later."""
    from tools.engines.link_merchants import decide
    provisional = resolve("ZZQQ UNKNOWN", PATTERNS, KNOWN)
    assert provisional.needs_review
    assert decide(provisional) == (False, "awaiting_review")


def test_REQ_FIN_051_a_non_purchase_earns_no_edge():
    """An ATM withdrawal's destination is unknown by definition; an edge to a merchant would
    assert one that does not exist."""
    from tools.engines.link_merchants import decide
    atm = resolve("NON CHASE ATM WITHDRAW", [], KNOWN, raw="NON-CHASE ATM WITHDRAW MAIN")
    assert decide(atm) == (False, "not_a_merchant:atm")


def test_RULE_12_the_edge_inherits_the_cascade_confidence_and_invents_none():
    """A second opinion about the same fact is how a weak number becomes indistinguishable
    from a strong one downstream. An exact pattern is certain; a fuzzy match carries its ratio."""
    from tools.engines.link_merchants import decide
    exact = resolve("BLUE BOTTLE COFFEE", PATTERNS, KNOWN)
    fuzzy = resolve("SWEETGREN", PATTERNS, KNOWN)
    assert decide(exact) == (True, "linked") and exact.confidence == 1.0
    assert decide(fuzzy) == (True, "linked")
    assert FUZZY_FLOOR <= fuzzy.confidence < 1.0, "a fuzzy edge must not claim certainty"


def test_REQ_ONT_005_a_merchant_entity_is_extracted_from_a_rule_but_inferred_from_a_guess():
    """RULE-05 vocabulary. A pattern match is extracted from a rule Joe's data supports; a
    fuzzy match is inferred. Storing both as 'extracted' would erase the distinction the
    provenance column exists to keep."""
    exact = resolve("BLUE BOTTLE COFFEE", PATTERNS, KNOWN)
    fuzzy = resolve("SWEETGREN", PATTERNS, KNOWN)
    assert exact.merchant_source.startswith("pattern")
    assert not fuzzy.merchant_source.startswith("pattern")
