"""The merchant review sheet (REQ-FIN-073/074, RULE-10, RULE-29).

197 descriptors resolve to nothing above the fuzzy floor. REQ-FIN-073 holds each as
provisional and none becomes a fact — correct, and a dead end until Joe can answer them.
These tests cover the two ways the sheet could do harm: leaking his descriptors into a public
repository, and inviting a wrong tick.
"""
import pathlib

import pytest

from tools.engines.merchants import FUZZY_FLOOR, normalize
from tools.review_merchants import PLAUSIBLE, outside_the_repo, read_answers

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_RULE_29_the_sheet_refuses_to_be_written_inside_the_repository():
    """A merchant descriptor is an observation about Joe — where he was, what he bought — and
    this repository is public. `git add` is one keystroke from a permanent mistake."""
    for inside in ("docs/review.tsv", "review.tsv", "tools/../x.tsv"):
        with pytest.raises(SystemExit, match="refusing to write personal data"):
            outside_the_repo(pathlib.Path(REPO / inside))
    assert outside_the_repo(pathlib.Path("/tmp/ok.tsv")).name == "ok.tsv"


def test_REQ_FIN_073_a_suggestion_is_only_offered_when_it_is_plausible():
    """difflib returns the least-bad match even when nothing is close. The first draft offered
    "Msg Concessions New" for "$1.50 FRESH PIZZA" and called all 197 lines a tick. Nonsense
    presented as a suggestion invites a wrong tick, and a wrong tick becomes a HUMAN pattern
    that outranks every rule permanently (RULE-10) — the most expensive error available here."""
    assert PLAUSIBLE < FUZZY_FLOOR, (
        "a suggestion the cascade would have accepted outright is not a suggestion")
    assert PLAUSIBLE >= 0.5, "too low a bar is the same failure in slower motion"


def test_REQ_FIN_060_a_price_in_the_descriptor_is_not_part_of_the_name():
    """"$1.50 FRESH PIZZA" normalised to "1 50 FRESH PIZZA": punctuation stripping turned the
    amount into two tokens that blocked nothing and matched nothing."""
    n = normalize("$1.50 FRESH PIZZA #2 NEW YORK NY")
    assert "1 50" not in n.normalized, n.normalized
    assert "FRESH PIZZA" in n.normalized
    assert "currency_amount" in n.rules_fired


def test_REQ_FIN_074_the_sheet_reads_back_every_answer_form(tmp_path):
    sheet = tmp_path / "answers.tsv"
    sheet.write_text(
        "# a comment\n"
        "answer\tdescriptor\tnormalised\tcharges\tsuggestion_1\tsuggestion_2\tsuggestion_3\n"
        "2\tSQ *SHOP 12\tSHOP\t3\tWrong One\tRight One\tThird\n"
        "Corner Store\tANOTHER\tANOTHER\t2\tX\tY\tZ\n"
        "skip\tWEIRD\tWEIRD\t1\tA\tB\tC\n"
        "\tUNDECIDED\tUNDECIDED\t1\tA\tB\tC\n")
    answers = read_answers(sheet)
    assert ("SQ *SHOP 12", "SHOP", "Right One") in answers, "the numbered pick was misread"
    assert ("ANOTHER", "ANOTHER", "Corner Store") in answers
    assert ("WEIRD", "WEIRD", None) in answers
    assert not any(d == "UNDECIDED" for d, _, _ in answers), (
        "a blank line must stay unresolved, not be decided by omission")


def test_RULE_06_a_numbered_pick_with_no_such_suggestion_is_refused(tmp_path):
    """Silently treating it as unanswered would lose a decision Joe believes he made."""
    sheet = tmp_path / "bad.tsv"
    sheet.write_text("answer\tdescriptor\tnormalised\tcharges\ts1\ts2\ts3\n"
                     "3\tSHOP\tSHOP\t1\tOnly One\t\t\n")
    with pytest.raises(SystemExit, match="picks suggestion 3"):
        read_answers(sheet)
