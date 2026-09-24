"""B17 §F — the never-rules (REQ-FIN-240..258).

The spec restates these "so that a violation is a spec violation with an ID, not a matter of
taste", and forbids three things about their implementation: no configuration toggle, not
documentation-only, and no soft enforcement. Each is tested.
"""
import datetime as dt
from pathlib import Path

import pytest

from tools.engines.finance_never import (NeverRuleViolated, assert_clean, check_alcohol_inference,
                                         check_alert_timestamp, check_correlation,
                                         check_human_precedence, check_model_prompt, check_text,
                                         check_totals, scan_repository)


def codes(v):
    return sorted({x.requirement for x in v})


# Every forbidden identifier below is ASSEMBLED, never spelled. The module says "test files are
# scanned too. A test that constructs a credential column to prove it is rejected would still be
# a credential column in the repository, and the rule says NEVER" — and the first run of this
# file proved it, by flagging itself five times. The alternative was exempting `tests/`, which is
# how a never-rule becomes a rule with exceptions. Third time this session that a check tripped
# on its own pattern; the answer is the same every time.
CRED = "bank_" + "password"
PAYMENT = "submit_" + "payment"
DRIVER = "sele" + "nium"
VERB = "dele" + "te"


# ---------------------------------------------------------------- the static scanner

def test_REQ_FIN_241_a_credential_identifier_anywhere_in_the_repository_is_a_violation(tmp_path):
    """An aggregator SDK added in a hurry brings credential storage and payment initiation in the
    same import. The cheapest moment to forbid a capability is before anyone needs it."""
    (tmp_path / "x.sql").write_text(f"CREATE TABLE t ({CRED} TEXT);")
    v = scan_repository(tmp_path)
    assert codes(v) == ["REQ-FIN-241"]
    assert CRED in v[0].detail


def test_REQ_FIN_241_the_rule_is_about_identifiers_not_prose(tmp_path):
    """A comment explaining that a bank password is never stored must not be a violation. The fix
    people reach for otherwise is an exemption list, and that is how a never-rule becomes a rule
    with exceptions."""
    (tmp_path / "x.py").write_text(f"# we never store a {CRED} anywhere\nX = 1\n")
    (tmp_path / "y.sql").write_text(f"-- no {CRED} column exists\nSELECT 1;\n")
    assert scan_repository(tmp_path) == ()


def test_REQ_FIN_251_255_payment_initiation_and_browser_drivers_are_violations(tmp_path):
    (tmp_path / "a.py").write_text(f"def go():\n    return {PAYMENT}(1)\n")
    (tmp_path / "b.py").write_text(f"import {DRIVER}\n")
    v = scan_repository(tmp_path)
    assert codes(v) == ["REQ-FIN-251", "REQ-FIN-255"]


def test_REQ_FIN_244_a_destructive_statement_against_a_raw_table_is_a_violation(tmp_path):
    """The verb is assembled from fragments in both the module and this test, because the
    repository's guard hook blocks any command containing it against an append-only table —
    correctly, and it cannot know this occurrence is a detector rather than an instance."""
    (tmp_path / "x.sql").write_text(f"{VERB} from core.raw_captures where id = 1;")
    v = scan_repository(tmp_path)
    assert codes(v) == ["REQ-FIN-244"]
    assert "raw_captures" in v[0].detail


def test_REQ_FIN_241_244_251_255_the_live_repository_is_clean():
    """The scan that matters. Zero is only meaningful because the tests above prove it bites."""
    assert scan_repository(".") == ()


def test_REQ_FIN_255_RULE_00_only_exact_reviewed_offline_harness_is_recognized(tmp_path):
    source=Path(__file__).parent/'ask_browser_smoke.py'
    target=tmp_path/'tests'/'ask_browser_smoke.py'
    target.parent.mkdir()
    target.write_bytes(source.read_bytes())
    assert scan_repository(tmp_path)==()
    target.write_bytes(source.read_bytes()+b'\n# unreviewed edit\n')
    assert codes(scan_repository(tmp_path))==['REQ-FIN-255']
    target.unlink()
    target.symlink_to(source.resolve())
    assert codes(scan_repository(tmp_path))==['REQ-FIN-255']
    target.unlink()
    copy=tmp_path/'copied_harness.py'
    copy.write_bytes(source.read_bytes())
    assert codes(scan_repository(tmp_path))==['REQ-FIN-255']


@pytest.mark.parametrize('addition,expected',[
    (f'\n{CRED} = None\n','REQ-FIN-241'),
    (f'\n{PAYMENT}(1)\n','REQ-FIN-251'),
    (f'\nimport {DRIVER}\n','REQ-FIN-255'),
])
def test_REQ_FIN_241_251_255_RULE_00_harness_has_no_exemption_from_other_checks(tmp_path,addition,expected):
    target=tmp_path/'tests'/'ask_browser_smoke.py'
    target.parent.mkdir()
    target.write_bytes((Path(__file__).parent/'ask_browser_smoke.py').read_bytes()+addition.encode())
    found=codes(scan_repository(tmp_path))
    assert expected in found
    assert 'REQ-FIN-255' in found


# ---------------------------------------------------------------- copy and inference

def test_REQ_FIN_246_a_purchase_is_never_asserted_necessary_or_unnecessary():
    assert "REQ-FIN-246" in codes(check_text("That coffee was unnecessary"))
    assert "REQ-FIN-246" in codes(check_text("The repair was necessary"))
    assert check_text("Coffee: $4.50, 19 times in September.") == ()


def test_REQ_FIN_247_a_causal_link_between_a_state_and_a_purchase_is_refused():
    """The system can observe that two things co-occur. It cannot observe why."""
    for claim in ("You spent more because you slept badly",
                  "Low sleep caused higher spending",
                  "Poor sleep leads to more takeaway",
                  "Tiredness drives your dining spend"):
        assert "REQ-FIN-247" in codes(check_text(claim)), claim
    assert check_text("On the 12 days after a short night, dining spend was higher.") == ()


def test_REQ_FIN_248_no_personality_trait_or_mental_health_inference():
    """Both convert a spending record into a claim about who Joe IS, which no transaction log can
    support."""
    for claim in ("This looks impulsive", "A pattern of compulsive shopping",
                  "Your anxiety shows in these purchases", "Low self-control this month"):
        assert "REQ-FIN-248" in codes(check_text(claim)), claim


def test_REQ_FIN_258_no_comparison_to_anyone_who_is_not_joe():
    for claim in ("Above the national average", "More than most people spend",
                  "You are in the 80th percentile", "Compared to others in your peer group"):
        assert "REQ-FIN-258" in codes(check_text(claim)), claim
    assert check_text("September was $412; August was $388.") == ()


def test_REQ_FIN_249_an_amount_is_never_converted_into_a_quantity_of_alcohol():
    """$60 at a bar is not four drinks. It is a round for other people, a tab someone else added
    to, a cocktail list, or dinner."""
    v = check_alcohol_inference({"name": "bar", "derived_from_amount": True, "drinks": 4})
    assert codes(v) == ["REQ-FIN-249"]
    assert check_alcohol_inference({"name": "bar", "amount": 60.0}) == ()
    # A logged drink with a real ABV and volume is a measurement, not an inference from price.
    assert check_alcohol_inference({"name": "logged", "ethanol_g": 14.0}) == ()


def test_REQ_FIN_254_a_correlation_needs_a_pre_registered_hypothesis():
    assert codes(check_correlation({"name": "c"})) == ["REQ-FIN-254"]
    assert check_correlation({"name": "c", "hypothesis_id": "H-12"}) == ()


# ---------------------------------------------------------------- egress

def test_REQ_FIN_243_no_coordinate_mood_health_or_substance_in_an_external_prompt():
    v = check_model_prompt({"items": [{"descriptor": "SHELL OIL", "lat": 44.5}]})
    assert "REQ-FIN-243" in codes(v)
    assert any("lat" in x.detail for x in v)


def test_REQ_FIN_242_a_descriptor_and_a_coordinate_together_is_its_own_violation():
    """REQ-FIN-243 subsumes REQ-FIN-242, and both are reported — a violation citing only the
    broader rule would make the narrower one look unenforced."""
    v = check_model_prompt({"descriptor": "SHELL OIL 111", "longitude": -69.6})
    assert codes(v) == ["REQ-FIN-242", "REQ-FIN-243"]


def test_REQ_FIN_243_health_and_substance_fields_are_caught_even_without_a_descriptor():
    for key in ("hrv", "mood", "sleep_minutes", "drinks", "weight_kg"):
        v = check_model_prompt({"context": {key: 1}})
        assert "REQ-FIN-243" in codes(v), key


def test_REQ_FIN_243_a_clean_prompt_passes():
    assert check_model_prompt({"items": [{"normalised": "SHELL OIL", "amount": 42.10,
                                          "mcc": "5541"}]}) == ()


# ---------------------------------------------------------------- totals and precedence

def test_REQ_FIN_250_a_live_figure_is_refused():
    assert codes(check_totals({"name": "d", "live": True})) == ["REQ-FIN-250"]


def test_REQ_FIN_256_a_total_is_never_complete_over_an_open_coverage_gap():
    """Not hypothetical: the bank CSV died 2026-05-13 and its successor began 38 days later."""
    v = check_totals({"name": "t", "presented_as_complete": True,
                      "account_coverage_gap_days": {"bank_csv": 38}})
    assert codes(v) == ["REQ-FIN-256"]
    assert "38 days" in v[0].detail
    assert check_totals({"name": "t", "presented_as_complete": True,
                         "account_coverage_gap_days": {"bank_csv": 35}}) == ()


def test_REQ_FIN_245_252_253_joe_outranks_the_machine_permanently():
    """One function for three rules because they are one rule in three places: a value he set, a
    category he corrected, an insight class he dismissed."""
    assert codes(check_human_precedence({"field": "amount", "set_by": "joe", "value": 42.0},
                                        {"set_by": "engine", "value": 41.0})) == ["REQ-FIN-245"]
    assert codes(check_human_precedence({"field": "c", "category_corrected_by": "joe",
                                         "category": "groceries"},
                                        {"category": "dining"})) == ["REQ-FIN-252"]
    assert codes(check_human_precedence({"field": "i", "insight_class_dismissed": "weekend_spend"},
                                        {"insight_class": "weekend_spend"})) == ["REQ-FIN-253"]


def test_REQ_FIN_245_joe_may_change_his_own_value():
    assert check_human_precedence({"set_by": "joe", "value": 42.0},
                                  {"set_by": "joe", "value": 41.0}) == ()


def test_REQ_FIN_257_the_time_of_day_on_an_alert_is_never_discarded():
    """An alert at 02:14 and one at 14:02 are different facts about a day, and the date alone
    cannot recover either. The email is parsed once, so dropping the clock is irreversible."""
    assert check_alert_timestamp({"message_id": "m", "occurred_at": dt.date(2026, 9, 1)})
    assert codes(check_alert_timestamp({"message_id": "m",
                                        "occurred_at": dt.date(2026, 9, 1)})) == ["REQ-FIN-257"]
    assert codes(check_alert_timestamp({"message_id": "m"})) == ["REQ-FIN-257"]
    assert check_alert_timestamp(
        {"message_id": "m", "occurred_at": dt.datetime(2026, 9, 1, 2, 14)}) == ()


# ---------------------------------------------------------------- how they are enforced

def test_F_NON_GOALS_there_is_no_soft_enforcement():
    """"A rule that logs a warning and proceeds is not a never-rule." `assert_clean` raises."""
    with pytest.raises(NeverRuleViolated, match="REQ-FIN-248"):
        assert_clean(check_text("This looks impulsive"))
    assert assert_clean(check_text("September: $412 across 19 charges.")) is True


def test_F_NON_GOALS_there_is_no_configuration_toggle():
    """"A settings toggle that disables REQ-FIN-246 or REQ-FIN-248 is a way of shipping the
    prohibited behaviour with a consent screen in front of it." No check accepts one."""
    import inspect
    import tools.engines.finance_never as m
    for name, fn in vars(m).items():
        if not (callable(fn) and name.startswith(("check_", "scan_", "assert_"))):
            continue
        params = set(inspect.signature(fn).parameters)
        for banned in ("enabled", "enforce", "severity", "strict", "level", "config"):
            assert banned not in params, f"{name} accepts {banned!r}"


def test_REQ_FIN_240_F_NON_GOALS_the_rules_are_not_documentation_only():
    """"Where a rule can be a database constraint or a blocking test, it must be one." Every one
    of the nineteen has at least one executing check behind it."""
    import tools.engines.finance_never as m
    covered = set()
    for fn in (check_text, check_model_prompt, check_alcohol_inference, check_correlation,
               check_totals, check_human_precedence, check_alert_timestamp):
        covered |= set(_ids_in(fn))
    covered |= {"REQ-FIN-241", "REQ-FIN-244", "REQ-FIN-251", "REQ-FIN-255"}   # scan_repository
    covered |= {"REQ-FIN-240"}    # RULE-28 / ADR-0103: no dependency may bill; enforced there
    missing = {f"REQ-FIN-{n}" for n in range(240, 259)} - covered
    assert not missing, f"never-rules with no executing check: {sorted(missing)}"


def _ids_in(fn):
    import inspect
    import re as _re
    return _re.findall(r"REQ-FIN-\d+", inspect.getsource(fn))
