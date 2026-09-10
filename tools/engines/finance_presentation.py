"""B17 §E — presentation restraint (REQ-FIN-210..228).

Pure: no database, no clock, no model. A surface is offered; violations come back.

THE EVIDENCE THIS ENCODES. Pocheptsova Ghosh & Huang measured what precise, frequent budget
feedback does: overspending of about $40 (n=283, p=.002) and $32 (n=363). A RANGE instead of an
exact figure attenuated it (n=198). Splitting a budget into sub-categories INCREASED total
spending (n=251).

The mechanism is worth stating because it is counter-intuitive: certainty removes the safety
margin. When you do not know exactly how much is left, you keep a buffer. A precise app tells you
exactly how much room you have, and you spend into it.

So the restraint here is not modesty or minimalism. **A running "you have $312 left" counter is
the single identified feature in this whole system with measured evidence of causing harm.** It
is banned outright, and this module exists so that it cannot be reintroduced by a well-meaning
surface later.

WHY THE BANNED WORDS ARE THE SMALL PART. REQ-FIN-218's ten words are the easiest rule to keep and
the least of it. The structural rules -- no running total, no figure that updates more than daily,
no forward point estimate, no pie chart, no share-of-total -- are where a surface actually goes
wrong, because each of them looks like good product design.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from tools.engines.narration import MORALISING

# REQ-FIN-218, which is REQ-NAR-023's list plus three. Extended from the reasoning layer's
# constant rather than restated, because two copies of a banned-word list drift and the drift is
# invisible until a banned word ships on one surface and not the other -- which is exactly what
# the requirement's own 2026-08-24 note records happening with `necessary`.
FINANCE_ONLY = ("overspent", "bad", "should have")
BANNED_WORDS = tuple(MORALISING) + FINANCE_ONLY

# REQ-FIN-220. An observation is numbers, counts and timestamps. A quantity adjective is a
# verdict wearing a measurement's clothes: "a lot" is not a quantity, it is an opinion about one.
QUANTITY_ADJECTIVES = ("a lot", "lots", "plenty", "loads", "heavy", "hefty", "steep", "huge",
                       "massive", "tiny", "minimal", "modest", "significant", "substantial",
                       "considerable", "high spending", "low spending")

MIN_RANGE_WIDTH_FRACTION = 0.20      # REQ-FIN-212
MAX_REVIEWS_PER_7_DAYS = 1           # REQ-FIN-213
MAX_NOTIFICATIONS_PER_MONTH = 4      # REQ-FIN-226
STALE_IMPORT_DAYS = 35               # REQ-FIN-225
MIN_UPDATE_INTERVAL_HOURS = 24       # REQ-FIN-211

FORBIDDEN_CHARTS = ("pie", "donut", "doughnut", "treemap", "sunburst", "stacked_percent")


@dataclass(frozen=True)
class Violation:
    requirement: str
    detail: str
    where: str = ""

    def __str__(self):
        return f"{self.requirement}: {self.detail}" + (f" [{self.where}]" if self.where else "")


def _words(text):
    return (text or "").lower()


def banned_words(text):
    """REQ-FIN-218. Whole-word matching, so 'badly' and 'badge' do not trip 'bad'."""
    low = _words(text)
    return tuple(w for w in BANNED_WORDS
                 if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low))


def quantity_adjectives(text):
    """REQ-FIN-220."""
    low = _words(text)
    return tuple(a for a in QUANTITY_ADJECTIVES
                 if re.search(rf"(?<![a-z]){re.escape(a)}(?![a-z])", low))


def check_copy(text, *, surface=""):
    """REQ-FIN-218/219/220/228. Returns violations; the caller blocks publication."""
    out = []
    for w in banned_words(text):
        out.append(Violation("REQ-FIN-218", f"moralising token {w!r}", surface))
    for a in quantity_adjectives(text):
        out.append(Violation("REQ-FIN-220", f"quantity adjective {a!r} instead of a number", surface))
    return tuple(out)


def copy_violation_rows(text, *, surface="", question_id=None):
    """REQ-FIN-219. Publication is BLOCKED and a row is written citing the offending token.

    Blocking rather than redacting is deliberate: silently deleting the word would ship a
    sentence nobody wrote, and the sentence would still be built on the judgement the word
    expressed. The copy has to be rewritten, not laundered.
    """
    v = check_copy(text, surface=surface)
    return {
        "publish": not v,
        "violations": v,
        "rows": tuple({"rule": x.requirement, "token": x.detail, "surface": surface,
                       "question_id": question_id} for x in v),
    }


def check_forward_amount(amount):
    """REQ-FIN-212. A forward-looking amount is a RANGE at least 20% of its midpoint wide.

    A point estimate of a future amount is the most tempting single number in the whole system
    and the one the evidence most directly implicates: it is the "you will spend $312" that
    removes the buffer. The width floor exists so that a range cannot be made technically
    compliant and practically precise -- $311-$313 is a point estimate with a hyphen in it.
    """
    if not isinstance(amount, (list, tuple)) or len(amount) != 2:
        return (Violation("REQ-FIN-212",
                          f"forward-looking amount {amount!r} is a single number; a point "
                          f"estimate of a future amount removes the safety margin"),)
    lo, hi = float(amount[0]), float(amount[1])
    if hi < lo:
        return (Violation("REQ-FIN-212", f"range {amount!r} is inverted"),)
    mid = (lo + hi) / 2.0
    if mid == 0:
        return ()
    width = (hi - lo) / abs(mid)
    if width < MIN_RANGE_WIDTH_FRACTION:
        return (Violation("REQ-FIN-212",
                          f"range width {width:.1%} of midpoint is below the "
                          f"{MIN_RANGE_WIDTH_FRACTION:.0%} floor; a range this tight is a point "
                          f"estimate with a hyphen in it"),)
    return ()


def check_surface(surface):
    """The whole of §E against one surface description. Returns every violation found.

    `surface` is a dict describing what would be rendered — not the rendered HTML. Checking the
    DESCRIPTION means a violation is caught while it is still a field in an envelope, which is
    where it can be fixed, rather than after it has become pixels.
    """
    out = []
    name = surface.get("name", "")

    # REQ-FIN-210. The measured harm. Not a style preference.
    if surface.get("running_total") or surface.get("remaining_in_period") is not None:
        out.append(Violation("REQ-FIN-210",
                             "a running spent/remaining counter for the current period — the "
                             "one feature here with measured evidence of causing harm "
                             "($32-40 overspend, n=283 and n=363)", name))

    # REQ-FIN-211. Frequency is half the mechanism; a daily-updating figure is still a live one.
    hours = surface.get("update_interval_hours")
    if hours is not None and hours < MIN_UPDATE_INTERVAL_HOURS:
        out.append(Violation("REQ-FIN-211",
                             f"updates every {hours}h; nothing may update more than once per "
                             f"{MIN_UPDATE_INTERVAL_HOURS}h", name))

    for label, amount in (surface.get("forward_amounts") or {}).items():
        for v in check_forward_amount(amount):
            out.append(Violation(v.requirement, f"{label}: {v.detail}", name))

    # REQ-FIN-215/216. A pie chart IS a share-of-total; banning the words and allowing the shape
    # would be theatre.
    chart = (surface.get("chart") or "").lower()
    if any(c in chart for c in FORBIDDEN_CHARTS):
        out.append(Violation("REQ-FIN-215", f"part-to-whole visual {chart!r}", name))
    if surface.get("concentration_as_share_of_total"):
        out.append(Violation("REQ-FIN-216",
                             "concentration presented as a share of a total rather than as a "
                             "ranked list with absolute amounts and counts", name))

    # REQ-FIN-217. A figure with nothing to compare it to invites the reader to supply the
    # comparison, and the one they supply is usually a judgement.
    if surface.get("retrospective_amount") is not None and \
            surface.get("preceding_period_amount") is None:
        out.append(Violation("REQ-FIN-217",
                             "a retrospective amount with no preceding-period figure beside it",
                             name))

    # REQ-FIN-221. Without it, an unwanted insight can only be endured.
    if surface.get("is_insight") and not surface.get("not_useful_control"):
        out.append(Violation("REQ-FIN-221", "an insight with no 'not useful' control", name))

    # REQ-FIN-224/225. A total that omits a dead account is not a total.
    for account, days in (surface.get("account_import_age_days") or {}).items():
        if days > STALE_IMPORT_DAYS and not surface.get("coverage_warning"):
            out.append(Violation("REQ-FIN-225",
                                 f"{account} has had no import for {days} days and no coverage "
                                 f"warning names it; no total here may be presented as complete",
                                 name))
    for limitation in ("has_atm_withdrawals", "has_split_tabs"):
        if surface.get(limitation) and not surface.get("limitation_labels"):
            out.append(Violation("REQ-FIN-224",
                                 f"{limitation} present with no limitation label in the same "
                                 f"view", name))

    for field in ("title", "body", "caption", "summary"):
        out.extend(check_copy(surface.get(field), surface=f"{name}.{field}"))
    return tuple(out)


def check_cadence(review_days, notification_days, *, month_days=30):
    """REQ-FIN-213/226. How often the system is allowed to speak at all.

    The cheap architecture is the behaviourally correct one: monthly CSV imports naturally
    produce retrospective, low-frequency review. These limits stop a future surface from
    undoing that by accident.
    """
    out = []
    days = sorted(review_days)
    for i in range(1, len(days)):
        gap = (days[i] - days[i - 1]).days
        if gap < 7:
            out.append(Violation("REQ-FIN-213",
                                 f"two scheduled reviews {gap} days apart ({days[i-1]} and "
                                 f"{days[i]}); at most {MAX_REVIEWS_PER_7_DAYS} per 7 days"))
    if len(notification_days) > MAX_NOTIFICATIONS_PER_MONTH:
        out.append(Violation("REQ-FIN-226",
                             f"{len(notification_days)} notifications in the month; the limit is "
                             f"{MAX_NOTIFICATIONS_PER_MONTH} excluding the twice-yearly renewal "
                             f"review"))
    return tuple(out)


def check_alcohol_surface(surface):
    """REQ-FIN-227/228. Occasions and context, never volume and cost.

    A surface that totals drinks or spend is a surface that invites a verdict, and REQ-FIN-228
    records the finding that matters here: making purchase decisions restores a sense of personal
    control and measurably reduces residual sadness. Copy describing a coping behaviour as a
    malfunction is contradicted by the published result, not merely unkind.
    """
    out = []
    for banned in ("total_volume_ml", "total_units", "total_spend"):
        if surface.get(banned) is not None:
            out.append(Violation("REQ-FIN-227",
                                 f"{banned} presented; alcohol surfaces speak in occasions and "
                                 f"context, not volume and cost", surface.get("name", "")))
    text = " ".join(str(surface.get(f) or "") for f in ("title", "body", "caption", "summary"))
    for token in ("problem", "malfunction", "unhealthy coping", "bad habit", "relapse",
                  "failure", "slip"):
        if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", text.lower()):
            out.append(Violation("REQ-FIN-228",
                                 f"characterises a coping behaviour as a malfunction ({token!r}); "
                                 f"the published finding is that purchase decisions restore a "
                                 f"sense of control and reduce residual sadness",
                                 surface.get("name", "")))
    return tuple(out)
