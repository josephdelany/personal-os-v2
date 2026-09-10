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
    # `internal_transfer` since the internal/external split: the kind became more precise,
    # the obligation (a transfer is not a merchant) did not.
    assert classify_non_merchant("Online Transfer from CHK transaction#:") == "internal_transfer"
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
    assert classify_non_merchant(raw) == "internal_transfer"
    assert classify_non_merchant(normalize(raw).normalized) == "internal_transfer", (
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


# ---------------------------------------------------------------- B14.3: category rules

def test_RULE_06_a_merchant_whose_charges_disagree_gets_no_category():
    """A modal category from a 50/50 split is a coin flip presented as a fact. Two thirds of
    that merchant's own categorised charges, or nothing."""
    from tools.engines.categorise import assign
    assert assign({"groceries": 8, "dining": 2})[0] == "groceries"
    assert assign({"groceries": 5, "dining": 5}) is None
    assert assign({"groceries": 6, "dining": 4}) is None, "60% is not a majority here"
    assert assign({}) is None
    assert assign({"__uncategorised__": 9}) is None


def test_RULE_06_uncategorised_charges_neither_vote_nor_block():
    """A merchant with one categorised charge and forty blanks is still categorised by the one
    piece of evidence there is — the blanks are absence, not disagreement (RULE-07)."""
    from tools.engines.categorise import assign
    got = assign({"coffee": 1, "__uncategorised__": 40})
    assert got is not None and got[0] == "coffee"


def test_RULE_12_case_is_folded_but_vocabularies_are_never_merged():
    """`groceries` and `Groceries` are one concept under two spellings, so folding case is
    deterministic and safe. `Food & Drink` against `dining` is a COARSER GRAIN, not a synonym,
    and merging them would change what a dining total means without anyone choosing that.
    This function is deliberately incapable of the second."""
    from tools.engines.categorise import fold, vocabularies
    assert fold("Groceries") == fold("groceries") == "groceries"
    assert fold("Food & Drink") != fold("dining")

    snake, other = vocabularies(["groceries", "dining", "Food & Drink", "Groceries", "Travel"])
    assert snake == ["dining", "groceries"]
    assert other == ["Food & Drink", "Groceries", "Travel"], (
        "a mixed vocabulary must be visible, not silently normalised away")


def test_REQ_FIN_051_a_non_merchant_never_acquires_a_category():
    """Enforced positively, not by the absence of an edge. REQ-FIN-051 excludes ATM amounts
    from every category rollup, and the legacy data does carry an `atm_cash` category."""
    from tools.engines.merchants import classify_non_merchant
    assert classify_non_merchant("NON-CHASE ATM WITHDRAW MAIN") == "atm"
    assert classify_non_merchant("Hannaford") is None


# ---------------------------------------------------------------- internal vs external money

def test_REQ_FIN_049_moving_money_between_your_own_accounts_is_not_income():
    """Measured on the real data: of the inbound total inbound, the great majority — 94.3% — is an internal
    transfer. Counting it as income overstates by seventeen times, and netting it against
    outflow makes total spend look like $279 against a true the gross outflow. Both would be
    arithmetically perfect and entirely false."""
    from tools.engines.merchants import classify_non_merchant
    for descriptor in ("Online Transfer from CHK transaction#:",
                       "Online Transfer to SAV transaction#:",
                       "AUTOMATIC PAYMENT - THANK YOU"):
        assert classify_non_merchant(descriptor) == "internal_transfer", descriptor


def test_REQ_FIN_049_a_person_to_person_receipt_is_distinguished_from_an_internal_one():
    """REQ-FIN-049 nets a shared bill against a P2P receipt. Netting an INTERNAL transfer
    against one would cancel a restaurant bill with Joe's own savings."""
    from tools.engines.merchants import classify_non_merchant
    for descriptor in ("VENMO CASHOUT", "CASH APP*JOHN", "PAYPAL *SOMEONE", "ZELLE PAYMENT"):
        assert classify_non_merchant(descriptor) == "p2p", descriptor


def test_REQ_FIN_049_the_internal_rule_is_tested_before_the_generic_transfer_rule():
    """"Online Transfer from CHK" matches both patterns and only the first is true. Order in
    NON_MERCHANT is load-bearing, so a reordering must fail here rather than silently
    reclassify the great majority."""
    from tools.engines.merchants import NON_MERCHANT, classify_non_merchant
    kinds = [kind for kind, _ in NON_MERCHANT]
    assert kinds.index("internal_transfer") < kinds.index("transfer")
    assert classify_non_merchant("Online Transfer from CHK") == "internal_transfer"


def test_REQ_FIN_051_a_real_merchant_is_still_a_merchant():
    """A classifier that swallows ordinary spending is worse than none."""
    from tools.engines.merchants import classify_non_merchant
    for descriptor in ("HANNAFORD #8229", "UBER EATS", "BLUE BOTTLE COFFEE"):
        assert classify_non_merchant(descriptor) is None, descriptor


def test_RULE_10_a_second_resolution_must_supersede_the_first(ent):
    """Review finding 6. The resolver inserted every row with supersedes NULL, so the
    precedence trigger returned at its first line every time and never fired — and
    `v_current_aliases`, which means "nothing supersedes me", returned Joe's correction AND the
    machine's guess side by side. A consumer reading `SELECT canonical WHERE alias = ?` got
    whichever the planner returned first."""
    first = _alias(ent, alias="SQ *HANN", canonical="Hannaford")
    ent.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        _alias(ent, alias="SQ *HANN", canonical="Hann Inc", resolved_by="fuzzy", confidence=0.83)
    assert "already has a current resolution" in str(e.value)
    ent.execute("ROLLBACK TO SAVEPOINT s")
    _alias(ent, alias="SQ *HANN", canonical="Hann Inc", resolved_by="fuzzy",
           confidence=0.83, supersedes=first)
    ent.execute(f"SELECT canonical FROM {_S}.v_current_aliases WHERE alias = 'SQ *HANN'")
    assert [r[0] for r in ent.fetchall()] == ["Hann Inc"], "exactly one current resolution"


def test_RULE_10_a_fork_off_an_already_superseded_row_is_refused(ent):
    """The other route to two heads: superseding a row that is already superseded. The trigger
    only inspected the superseded row's provenance, so a fork slipped past the human check."""
    first = _alias(ent, alias="SQ *HANN", canonical="Hannaford")
    _alias(ent, alias="SQ *HANN", canonical="Corrected", resolved_by="human", supersedes=first)
    ent.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        _alias(ent, alias="SQ *HANN", canonical="Guess", resolved_by="fuzzy",
               confidence=0.9, supersedes=first)
    assert "already superseded" in str(e.value)
    ent.execute("ROLLBACK TO SAVEPOINT s")


def test_RULE_10_a_fuzzy_match_can_never_claim_certainty(ent):
    """Review finding 7. The constraint ended `OR resolved_by = 'fuzzy'`, admitting precisely
    what its own comment forbade — ('fuzzy', 1.0) inserted cleanly — and with `provisional`
    already forced to NULL confidence by the constraint above it, NO pair could violate it at
    all. A constraint that cannot fail is decoration, and this decoration read as a guarantee:
    "fuzzy at 1.00" and "Joe said so" would have been indistinguishable downstream."""
    ent.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        _alias(ent, resolved_by="fuzzy", confidence=1.0)
    assert "only_a_rule_or_a_human_is_certain" in str(e.value)
    ent.execute("ROLLBACK TO SAVEPOINT s")
    _alias(ent, resolved_by="fuzzy", confidence=0.99)
    _alias(ent, alias="OTHER", resolved_by="human", confidence=1.0)


def test_RULE_01_a_location_token_stores_its_measured_evidence_not_the_floor():
    """Review finding 8. The writer stored the literal 4 — the constraint's own floor — for
    every token, so one backed by forty distinct prefixes and one backed by exactly four were
    recorded identically. The column asserts measured evidence and held a constant."""
    from tools.engines.merchants import location_token_evidence
    sample = ["SHELL OIL 111 HOUSTON TX", "KROGER 222 HOUSTON TX", "CVS 333 HOUSTON TX",
              "TARGET 444 HOUSTON TX", "JOES GARAGE HOUSTON TX",
              "BLUE BOTTLE COFFEE OAKLAND CA"]
    evidence = location_token_evidence(sample)
    assert evidence["HOUSTON"] == 5, "the real count, which is not the floor"
    assert "OAKLAND" not in evidence


def _run(cur, descriptors):
    """Run the real cascade and the real writer against the fixture schema."""
    from tools.engines.merchants import location_token_evidence
    from tools.engines.resolve_merchants import build, write_resolutions
    location, patterns, resolutions, _ = build(descriptors)
    return write_resolutions(cur, patterns, location, resolutions,
                             location_token_evidence([d for d, _ in descriptors]),
                             core=_S, config="config_pytest")


def test_REQ_FIN_051_a_non_merchant_is_stored_rather_than_killing_the_whole_run(ent):
    """Third review, finding 1. The worst of the three rounds, and the one both earlier rounds
    edited this very loop without seeing.

    REQ-FIN-051 classifies ATM withdrawals, transfers and fees as not-a-merchant, with
    `canonical` None and `needs_review` False — so they fell straight through to the INSERT,
    where `canonical` was NOT NULL and `resolved_by` had no such member. The commit is after
    the loop and there was no exception handling, so ONE ATM descriptor rolled back every
    pattern, every location token and every alias in the run. It needed no human correction to
    trigger, only Joe's ordinary bank data: the tool's own output calls out ATM/transfer/fee
    descriptors as a routine line.

    The previous tests for this loop read the source file and grepped it for string literals,
    which is why a crash on real input passed them."""
    written = _run(ent, [("ONLINE TRANSFER FROM CHK 1234", 6),
                         ("ATM WITHDRAWAL 555 MAIN ST", 3),
                         ("STARBUCKS 111 PORTLAND ME", 9),
                         ("STARBUCKS 222 PORTLAND ME", 7)])
    assert written["not_a_merchant"] == 2, written
    ent.execute(f"SELECT alias, canonical, non_merchant_kind, resolved_by, confidence "
                f"FROM {_S}.entity_aliases WHERE resolved_by = 'not_a_merchant' ORDER BY alias")
    rows = ent.fetchall()
    assert len(rows) == 2, rows
    for alias, canonical, kind, source, confidence in rows:
        assert canonical is None, "a non-merchant has no merchant name"
        assert kind, f"but it must say WHY there is no merchant: {alias}"
        assert confidence is None, "a rule match reports no confidence"


def test_REQ_FIN_051_the_classification_reads_the_raw_descriptor_not_the_normalised_one(ent):
    """Third review, finding 11. `resolve()` documents that REQ-FIN-051 runs on the RAW string
    because normalisation strips the evidence — and the one production caller omitted `raw=`.
    `punctuation` turns E-PAYMENT into E PAYMENT, which the \bE-?PAYMENT\b rule no longer
    matches, so that descriptor escaped classification and was resolved as a merchant called
    "E Payment". The test that existed to protect this called `resolve` directly, passing the
    argument the caller did not."""
    _run(ent, [("E-PAYMENT THANK YOU 0001", 4), ("E-PAYMENT THANK YOU 0002", 4)])
    ent.execute(f"SELECT resolved_by, non_merchant_kind FROM {_S}.entity_aliases")
    rows = ent.fetchall()
    assert rows and all(r[0] == "not_a_merchant" for r in rows), rows


def test_RULE_10_the_resolver_skips_a_human_corrected_alias_instead_of_dying(ent):
    """Second review, finding 1, now proven by running rather than by reading.

    The repair set `supersedes` unconditionally, and the resolver can only ever emit an
    automated `resolved_by`. So the first time Joe corrected an alias the trigger raised, the
    run died with no exception handling and no commit, and EVERY pattern and token was lost —
    identically on every subsequent run, forever, because a human head is permanent."""
    descriptors = [("STARBUCKS 111 PORTLAND ME", 9), ("STARBUCKS 222 PORTLAND ME", 7)]
    _run(ent, descriptors)
    # Joe's correction is recorded the way RULE-02 requires: a new row SUPERSEDING the head,
    # not an UPDATE. The append-only trigger refuses the update, which is the point.
    ent.execute(f"SELECT alias_id, alias FROM {_S}.entity_aliases LIMIT 1")
    head_id, alias = ent.fetchone()
    ent.execute(f"INSERT INTO {_S}.entity_aliases (alias, canonical, resolved_by, confidence, "
                f"supersedes) VALUES (%s,'Joe Said So','human',1.0,%s)", (alias, head_id))
    ent.execute(f"SELECT count(*) FROM {_S}.entity_aliases")
    before = ent.fetchone()[0]

    written = _run(ent, descriptors)          # must not raise

    assert written["skipped_human_correction"] == 1, written
    ent.execute(f"SELECT canonical FROM {_S}.v_current_aliases WHERE alias = %s", (alias,))
    assert ent.fetchone()[0] == "Joe Said So", "RULE-10: the correction is permanent"
    ent.execute(f"SELECT count(*) FROM {_S}.entity_aliases")
    assert ent.fetchone()[0] == before, "and nothing was appended over it"


def test_RULE_10_a_human_answered_alias_is_not_raised_for_review_again(ent):
    """Third review, finding 7. The review-queue insert ran BEFORE the human-head check, so an
    alias Joe had already answered could be queued again the moment the automated cascade
    degraded — a discovered pattern dropping below MIN_DISTINCT_RAW was enough. His answer sat
    in `entity_aliases` while the queue asked him for it a second time."""
    strong = [("KROGER 111 HOUSTON TX", 9), ("KROGER 222 HOUSTON TX", 8),
              ("KROGER 333 HOUSTON TX", 7)]
    _run(ent, strong)
    ent.execute(f"SELECT alias_id, alias FROM {_S}.entity_aliases")
    for head_id, alias in ent.fetchall():
        ent.execute(f"INSERT INTO {_S}.entity_aliases (alias, canonical, resolved_by, "
                    f"confidence, supersedes) VALUES (%s,'Kroger','human',1.0,%s)",
                    (alias, head_id))
    ent.execute(f"DELETE FROM {_S}.merchant_review_queue")

    _run(ent, [("KROGER 111 HOUSTON TX", 1)])   # one descriptor: no pattern survives discovery

    ent.execute(f"SELECT count(*) FROM {_S}.merchant_review_queue")
    assert ent.fetchone()[0] == 0, "Joe already answered this alias; it must not be re-asked"


def test_RULE_10_the_resolver_does_not_rewrite_an_unchanged_resolution(ent):
    """Second review, finding 9. Every run appended one superseding row per alias to an
    append-only table that can never be pruned — roughly 12k rows a day at this scale — and
    made "when did this resolution last change?" unanswerable from the ledger."""
    descriptors = [("STARBUCKS 111 PORTLAND ME", 9), ("STARBUCKS 222 PORTLAND ME", 7)]
    first = _run(ent, descriptors)
    ent.execute(f"SELECT count(*) FROM {_S}.entity_aliases")
    after_first = ent.fetchone()[0]
    assert first["unchanged"] == 0, "nothing can be unchanged on an empty table"

    second = _run(ent, descriptors)

    assert second["unchanged"] >= 1 and second["written"] == 0, second
    ent.execute(f"SELECT count(*) FROM {_S}.entity_aliases")
    assert ent.fetchone()[0] == after_first, "a second identical run appends nothing"


def test_REQ_FIN_061_collapsed_raw_descriptors_are_recorded_not_dropped(ent):
    """Third review, finding 6. `resolutions` is keyed by RAW descriptor and N raws collapse
    onto one alias, so the loop wrote the same alias N times: the first inserted, and every
    later one found the row it had just written and was counted `unchanged` — on a table that
    started EMPTY, which is what exposed it. The raws that lost the race vanished, chosen by
    dictionary order, while REQ-FIN-061 asks for "the original, verbatim"."""
    written = _run(ent, [("HANNAFORD 8229 WATERVILLE ME", 12),
                         ("HANNAFORD 8230 WATERVILLE ME", 3),
                         ("HANNAFORD 8231 WATERVILLE ME", 1)])
    assert written["unchanged"] == 0, "nothing is unchanged on a first run"
    assert written["raw_descriptors_collapsed"] == 2, written
    ent.execute(f"SELECT raw_descriptor, also_seen FROM {_S}.entity_aliases")
    raw, also = ent.fetchone()
    assert raw == "HANNAFORD 8229 WATERVILLE ME", "the most-transacted original is kept"
    assert sorted(also) == ["HANNAFORD 8230 WATERVILLE ME",
                            "HANNAFORD 8231 WATERVILLE ME"], "and the others are not lost"


def test_REQ_FIN_074_a_confirmed_pattern_changes_the_next_run_s_resolution(ent):
    """Third review, finding 4. `build()` constructed its pattern list PURELY from discovered
    normalised forms and never read `config.merchant_patterns`, while `review_merchants.py`
    wrote Joe's confirmation only to that table. His answer went into a table the resolver did
    not query, so REQ-FIN-074's "confirmation is what promotes a provisional merchant into a
    pattern" changed no subsequent resolution — the review sheet with 157 descriptors needing
    names terminated in a write nobody read."""
    from tools.engines.resolve_merchants import build, read_stored_patterns
    descriptors = [("HANNAFORD 8229 WATERVILLE ME", 12), ("HANNAFORD 8230 WATERVILLE ME", 8)]
    _run(ent, descriptors)
    ent.execute(f"SELECT canonical FROM {_S}.v_current_aliases")
    machine = ent.fetchone()[0]

    # Exactly the statement review_merchants.py runs: Joe's confirmation UPGRADES the
    # discovered row in place rather than adding a second one.
    ent.execute("""INSERT INTO config_pytest.merchant_patterns
                   (pattern, canonical, is_regex, specificity, provenance)
                   VALUES ('HANNAFORD WATERVILLE', 'Hannaford', false, 0, 'human')
                   ON CONFLICT (pattern, is_regex)
                   DO UPDATE SET canonical = EXCLUDED.canonical, provenance = 'human'""")
    _, _, resolutions, stats = build(descriptors, read_stored_patterns(ent, "config_pytest"))

    assert stats["patterns_stored"] == 1, stats
    canonicals = {r.canonical for _, r, _ in resolutions.values()}
    assert canonicals == {"Hannaford"}, (
        f"Joe's confirmed name must win over the machine's {machine!r}: {canonicals}")


def test_RULE_10_a_human_alias_in_the_ledger_reaches_cascade_step_one(ent):
    """Third review, finding 4. `resolve()`'s `human_alias` parameter — cascade step 1, "the
    answer, and it outranks every rule permanently" — had exactly ONE caller in the repository
    and it was a test. No production path passed it, so RULE-10's alias guarantee was enforced
    by a trigger on a table nothing consulted."""
    from tools.engines.resolve_merchants import build, read_human_aliases
    descriptors = [("KROGER 111 HOUSTON TX", 9), ("KROGER 222 HOUSTON TX", 8),
                   ("KROGER 333 HOUSTON TX", 7)]
    _run(ent, descriptors)
    ent.execute(f"SELECT alias_id, alias FROM {_S}.entity_aliases")
    for head_id, alias in ent.fetchall():
        ent.execute(f"INSERT INTO {_S}.entity_aliases (alias, canonical, resolved_by, "
                    f"confidence, supersedes) VALUES (%s,'Kroger Co','human',1.0,%s)",
                    (alias, head_id))

    _, _, resolutions, stats = build(descriptors, (), read_human_aliases(ent, _S))

    assert stats["human_aliases_applied"] == len(descriptors), stats
    for _, r, _ in resolutions.values():
        assert (r.canonical, r.merchant_source) == ("Kroger Co", "human"), r
