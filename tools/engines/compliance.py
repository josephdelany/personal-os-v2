"""B16 §F.3 — compliance instrumentation, without gamification (REQ-CAP-093..099).

Pure: no database, no clock, no model.

WHY THIS MODULE IS MOSTLY PROHIBITIONS. Every obvious way to measure adherence makes the system
worse. A streak counter turns one missed day into a reason to abandon the whole thing -- and the
spec's own non-goals say so: "the downside — abandoning the whole system after one missed day —
is severe". A 100% adherence bar guarantees daily failure. Imputing a missing meal makes the
record look complete while making it false. Responding to a decline with more prompts is the one
intervention the evidence says participants uniformly found aversive.

So the measurable things here are deliberately dull: a rolling percentage with no memory of
consecutive days, a bar set at two eating occasions rather than all of them, and an alert that
goes to the SYSTEM's design log rather than to Joe.

WHY COVERAGE HAS NO MEMORY OF CONSECUTIVE DAYS (REQ-CAP-095). A rolling 7-day percentage and a
streak count can be computed from the same data, and they say opposite things after one missed
day: the percentage goes from 100% to 86%, the streak goes from 40 to 0. The second number is a
cliff, and a cliff is what makes a person stop. `coverage()` cannot compute a run length --
`run_lengths` is deliberately absent from this module, unlike regimes.py where it is required.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

WINDOW_DAYS = 7                          # REQ-CAP-094
EATING_OCCASIONS_BAR = 2                 # REQ-CAP-096
DECLINE_PP_PER_WEEK = 2.0                # REQ-CAP-097
DECLINE_CONSECUTIVE_WEEKS = 3            # REQ-CAP-097
DESIGN_ALERT_REASON = "compliance_decline_exceeds_baseline"

# REQ-CAP-095. The vocabulary of gamification, which must not reach any surface.
# Matched as whole words so "chained" in a technical sentence and "badger" do not trip it, and
# so the linter's own failure mode is a MISS rather than a false positive that gets it disabled.
GAMIFIED = ("streak", "streaks", "badge", "badges", "chain", "chains", "combo",
            "consecutive days", "days in a row", "day run", "broke", "broken run",
            "keep it up", "don't break", "back on track", "perfect week", "trophy",
            "level up", "points", "leaderboard", "rank")

# `points` is a game currency AND a unit of measurement. "You have 400 points" must be caught;
# "declined by 2 percentage points" must not, because REQ-CAP-097 is written in exactly those
# words -- a linter that fires on the requirement it enforces gets switched off within a week,
# and a switched-off linter catches nothing. The exclusion is by PRECEDING CONTEXT, so the
# gamified use is still caught; it is precision, not an exemption (RULE-00).
CONTEXTUAL_EXCEPTIONS = {"points": (r"percentage\s+$", r"\bpp\s+$", r"basis\s+$")}


@dataclass(frozen=True)
class Alert:
    """REQ-CAP-097. A row for `design_alerts` — addressed to the SYSTEM, not to Joe.

    A declining check-in rate is evidence that the ASKING is wrong, not that Joe is failing.
    Sending it to him would be the nag REQ-CAP-098 forbids, arriving under another name.
    """
    reason: str
    weeks: tuple
    total_decline_pp: float
    audience: str = "design_log"


def day_is_covered(day_record, *, components=("morning_checkin", "eating_occasions")):
    """Did this day meet the bar? Returns (covered, detail).

    F-Q1 in the spec is open: exactly what counts toward rolling 7-day coverage. So the
    components are a PARAMETER with the conservative default, rather than a constant baked in
    where a later ruling could not reach it. What is NOT open is REQ-CAP-096's bar: two eating
    occasions, never all of them.
    """
    detail = {}
    ok = True
    for c in components:
        if c == "eating_occasions":
            n = int(day_record.get("eating_occasions", 0) or 0)
            met = n >= EATING_OCCASIONS_BAR
            detail[c] = {"n": n, "bar": EATING_OCCASIONS_BAR, "met": met}
        else:
            met = bool(day_record.get(c))
            detail[c] = {"met": met}
        ok = ok and met
    return ok, detail


def coverage(day_records, as_of, *, window=WINDOW_DAYS, components=None):
    """REQ-CAP-094/099. Rolling coverage as a percentage over a FIXED denominator.

    The denominator is the window length, not the number of days that happen to have a record.
    A day with no record is a day not covered -- dividing by "days we heard from" would report
    100% for a week containing one entry, which is the arithmetic version of imputing the rest.

    REQ-CAP-099: nothing is imputed. Two logged meals out of four is 50%, not "two logged and
    two estimated". The estimate would make the record look complete while making it false.
    """
    kw = {"components": components} if components else {}
    by_day = {r["day"]: r for r in day_records}
    days = [as_of - dt.timedelta(days=i) for i in range(window - 1, -1, -1)]
    covered, per_day = 0, []
    for d in days:
        rec = by_day.get(d)
        if rec is None:
            # A day with no record is a day NOT covered, and it is marked as absent rather than
            # as a zero -- "missing" and "logged nothing" are different facts (RULE-06).
            ok, detail = False, {"no_record": True}
        else:
            ok, detail = day_is_covered(rec, **kw)
        covered += 1 if ok else 0
        per_day.append({"day": d, "covered": ok, "detail": detail})
    pct = round(100.0 * covered / window, 1)
    return {
        "coverage_pct": pct,
        "days_covered": covered,
        "window_days": window,
        "as_of": as_of,
        "per_day": tuple(per_day),
        # REQ-CAP-095, stated in the payload so a renderer cannot reach for the other number.
        # Written without using any of the vocabulary it rejects -- which is the point: the
        # policy can be explained without the words, and a note that trips its own linter would
        # have been the first argument for adding an exemption.
        "note": ("Rolling coverage over a fixed 7-day window. This figure has no memory of "
                 "which days were adjacent: one missed day moves it by about 14 percentage "
                 "points, where a counter that resets to nothing would fall off a cliff, and "
                 "the cliff is what makes a person abandon a system entirely."),
        "imputed": False,                                 # REQ-CAP-099
    }


def weekly_decline(weekly_pcts, *, threshold_pp=DECLINE_PP_PER_WEEK,
                   consecutive=DECLINE_CONSECUTIVE_WEEKS):
    """REQ-CAP-097. An alert only when the decline is sustained, not on one bad week.

    `weekly_pcts` is oldest-first. Requiring three consecutive weeks each losing more than two
    points is deliberately hard to trip: an alert that fires on ordinary variation trains its
    reader to ignore it, and this one is the only signal that the asking has stopped working.
    """
    if len(weekly_pcts) < consecutive + 1:
        return None
    drops = [(weekly_pcts[i - 1] - weekly_pcts[i]) for i in range(1, len(weekly_pcts))]
    tail = drops[-consecutive:]
    if all(d > threshold_pp for d in tail):
        return Alert(reason=DESIGN_ALERT_REASON,
                     weeks=tuple(round(float(p), 1) for p in weekly_pcts[-(consecutive + 1):]),
                     total_decline_pp=round(sum(tail), 1))
    return None


def prompt_plan(scheduled, *, captured_today=(), coverage_pct=None, baseline_plan=None):
    """REQ-CAP-093/098. Which prompts to send. It can only ever SHRINK.

    Two rules, and the second is the one that takes discipline:

      * REQ-CAP-093 -- a prompt whose capture already arrived today is suppressed. Asking for
        something already given is the fastest way to teach someone to ignore the asking.
      * REQ-CAP-098 -- a falling coverage figure must NEVER add prompts. The instinct is exactly
        backwards: when compliance drops the correct response is to shorten the task, not to
        add reminders. This function has no code path that returns more prompts than it was
        given, whatever `coverage_pct` says, which is why the parameter is accepted and then
        used only in the explanation.
    """
    base = list(baseline_plan if baseline_plan is not None else scheduled)
    keep = [p for p in scheduled if p not in set(captured_today)]
    suppressed = [p for p in scheduled if p in set(captured_today)]
    assert len(keep) <= len(base), "REQ-CAP-098: the plan may never grow"
    return {
        "send": tuple(keep),
        "suppressed_already_captured": tuple(suppressed),
        "coverage_pct": coverage_pct,
        "frequency_change": "none",
        "note": ("Prompt frequency does not respond to coverage. When capture declines the "
                 "correct response is to shorten the task, not to add reminders."),
    }


def lint_surface(text):
    """REQ-CAP-095. Gamified language, found before it reaches a screen.

    Returns the matched terms. Whole-word matching on purpose: a false positive gets a linter
    switched off, and a switched-off linter catches nothing at all.
    """
    found = []
    low = (text or "").lower()
    for term in GAMIFIED:
        for m in re.finditer(rf"(?<![a-z]){re.escape(term)}(?![a-z])", low):
            before = low[:m.start()]
            if any(re.search(p, before) for p in CONTEXTUAL_EXCEPTIONS.get(term, ())):
                continue
            found.append(term)
            break
    return tuple(sorted(set(found)))


def check_surfaces(surfaces):
    """Lint many named strings at once. `surfaces` maps a name to its text."""
    return {name: hits for name, text in surfaces.items() if (hits := lint_surface(text))}


def lint_envelope(payload, path="$"):
    """REQ-CAP-095 applied to what actually reaches a screen: an API envelope.

    WHY NOT SOURCE CODE. Running this over `.py` and `.sql` produces a wall of false positives --
    `chain` (a migration chain, a supersession chain), `rank` (a window function, a tier order),
    `points` (a data point, "the number points at"), `broke` (a commit message). REQ-CAP-095 says
    SHALL NOT **display**; a comment is not a display. Linting source would have produced 200
    hits, and a linter with 200 false positives is a linter somebody deletes.

    The envelope is the right boundary because every surface in this system renders one. Both
    KEYS and string VALUES are checked: a key named `streaks` becomes a heading, and a heading
    is a display even when no sentence mentions it.
    """
    hits = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            if found := lint_surface(str(k)):
                hits.append({"path": f"{path}.{k}", "where": "key", "terms": found})
            hits.extend(lint_envelope(v, f"{path}.{k}"))
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            hits.extend(lint_envelope(v, f"{path}[{i}]"))
    elif isinstance(payload, str):
        if found := lint_surface(payload):
            hits.append({"path": path, "where": "value", "terms": found})
    return hits
