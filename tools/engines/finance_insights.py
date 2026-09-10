"""B17 §C.4 / §D.3 — what the system may say, and when (REQ-FIN-150..158, 190..198, 200).

Pure: no database, no clock, no model.

WHY AN INSIGHT IS TIMED TO THE RENEWAL AND NOT TO ITS DISCOVERY (REQ-FIN-151). Payment
depreciation erodes the salience of a sunk cost: a subscription bought in March feels free by
June, which is exactly why unused ones survive. Telling Joe in June that he has not opened it
since March lands on a cost he no longer feels. Telling him ON the day it charges again restores
the salience, and that is the moment a cancellation actually happens.

So `schedule_unused_insight` returns the NEXT EXPECTED CHARGE DATE, never today, even though
today is when the evidence became available. The delay is the intervention.

THE 197/198 TENSION, RESOLVED EXPLICITLY. REQ-FIN-197 says NEVER estimate alcohol volume, units
or standard drinks from a transaction amount. REQ-FIN-198 permits a bar tab as a PRIOR on drink
count at confidence <= 0.30 with provenance 'inferred'. These are not in conflict, and the
difference is the whole of it:

  * An ESTIMATE is presented as a drink count. It answers "how much did I drink" with a number
    derived from a price. Forbidden, always -- $60 at a bar is a round for other people as often
    as it is four drinks for Joe.
  * A PRIOR is a disclosed, weak, clearly-labelled input to something else, which is DISCARDED
    the moment a real `consume` atom exists for that episode.

`drink_prior` therefore refuses to produce anything unless the caller asks for a prior
explicitly, caps confidence at 0.30, stamps provenance, and returns None outright when a real
observation exists. There is no function here that returns a drink count.

WHY A DISMISSED INSIGHT CLASS NEVER COMES BACK UNDER A NEW NAME (REQ-FIN-158). Re-raising the
same idea with different wording is the behaviour that teaches a person to stop reading. The
suppression is by CLASS, and `rephrase_would_evade` exists so a future author cannot reintroduce
a suppressed class by renaming it.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

UNUSED_DAYS = 60                       # REQ-FIN-150
ZOMBIE_DAYS = 90                       # REQ-FIN-155
RENEWAL_REVIEWS_PER_YEAR = 2           # REQ-FIN-152
BULK_RESPONSE_SURFACE = "synthetic_renewal_review"   # REQ-FIN-153
MAX_ITEMS_ELSEWHERE = 10               # REQ-FIN-153
DRINK_PRIOR_MAX_CONFIDENCE = 0.30      # REQ-FIN-198
LATE_BAR_HOUR = 21                     # REQ-FIN-194

# REQ-FIN-193. The connectives the requirement names, verbatim, plus the conjugations a writer
# actually reaches for.
CAUSAL_CONNECTIVES = ("because", "causes", "caused", "leads to", "led to", "due to",
                      "makes you", "made you", "results in", "resulted in")


@dataclass(frozen=True)
class Insight:
    kind: str
    insight_class: str
    deliver_on: dt.date
    text: str
    evidence_tier: str
    what_would_raise_it: str
    dismissible: bool = True
    not_useful_control: bool = True
    answerable: bool = True
    recommends_action: bool = False
    evidence: dict = field(default_factory=dict)

    def __post_init__(self):
        # REQ-FIN-157 / RULE-25. A recommendation without its tier and its escape hatch is an
        # assertion wearing a suggestion's clothes.
        if self.recommends_action and not (self.evidence_tier and self.what_would_raise_it):
            raise ValueError("REQ-FIN-157: an insight that recommends an action must name its "
                             "evidence tier and what would raise it")
        if not (self.dismissible and self.not_useful_control):
            raise ValueError("REQ-FIN-157: every insight is dismissible and markable not useful")


def schedule_unused_insight(stream, *, usage_days_absent, next_charge_date, today):
    """REQ-FIN-150/151/157. Scheduled for the renewal, never for today.

    Returns None below the 60-day threshold. `next_charge_date` is required rather than derived
    here, because deriving it would duplicate the period arithmetic that `recurrence.py` owns and
    the two copies would drift.
    """
    if usage_days_absent < UNUSED_DAYS:
        return None
    if next_charge_date <= today:
        # A renewal already past is not a moment of restored salience; wait for the next one.
        return None
    return Insight(
        kind="unused_subscription",
        insight_class="unused_subscription",
        deliver_on=next_charge_date,          # REQ-FIN-151, not `today`
        evidence_tier="T1_DESCRIPTIVE",
        what_would_raise_it=("A usage signal — an app open, a login, a receipt — would make this "
                             "a measurement rather than an absence of evidence."),
        recommends_action=True,
        text=(f"{stream} charges again on {next_charge_date.isoformat()}. No usage has been "
              f"recorded for {usage_days_absent} days. Keep it or cancel it?"),
        evidence={"usage_days_absent": usage_days_absent, "next_charge": next_charge_date})


def renewal_review_dates(year):
    """REQ-FIN-152. Exactly twice per calendar year, on fixed dates.

    Fixed rather than "every six months from the first one", because a rolling schedule drifts
    and a review that arrives on a different date each year is a review nobody expects.
    """
    return (dt.date(year, 1, 15), dt.date(year, 7, 15))


def renewal_review(streams, *, last_usage, on):
    """REQ-FIN-152/153. Every active stream, its usage evidence, and an explicit keep-or-cancel.

    This is the ONLY surface allowed to ask for more than ten responses at once (REQ-FIN-153).
    Everywhere else a long list is a wall, and a wall gets closed.
    """
    items = [{"stream": s, "last_usage": last_usage.get(s),
              "response_required": "keep_or_cancel"}
             for s in streams]
    return {"surface": BULK_RESPONSE_SURFACE, "on": on, "items": tuple(items),
            "bulk_response_allowed": True,
            "note": ("The only surface that may require a response on more than "
                     f"{MAX_ITEMS_ELSEWHERE} items at once.")}


def check_bulk_response(surface_name, n_items):
    """REQ-FIN-153, enforced rather than trusted."""
    if n_items > MAX_ITEMS_ELSEWHERE and surface_name != BULK_RESPONSE_SURFACE:
        return (f"REQ-FIN-153: {surface_name!r} asks for {n_items} responses; only "
                f"{BULK_RESPONSE_SURFACE} may exceed {MAX_ITEMS_ELSEWHERE}",)
    return ()


def duplicate_services(streams):
    """REQ-FIN-154. Two or more active streams in one service class, with the combined amount.

    The combined amount is the point. Three music subscriptions at $11 each read as three small
    charges and one $33 monthly decision, and only the second framing is actionable.
    """
    by_class: dict = {}
    for s in streams:
        if s.get("lifecycle") != "active":
            continue
        by_class.setdefault(s.get("service_class"), []).append(s)
    out = []
    for service_class, members in sorted(by_class.items(), key=lambda kv: (kv[0] or "")):
        if service_class and len(members) >= 2:
            out.append({
                "service_class": service_class,
                "merchants": tuple(sorted(m["merchant"] for m in members)),
                "combined_monthly": round(sum(float(m.get("monthly_amount", 0))
                                              for m in members), 2),
                "n": len(members)})
    return tuple(out)


def zombie_streams(streams, *, signals):
    """REQ-FIN-155. Active, but no login / app use / email for 90 days — naming WHICH signal.

    Naming the absent signal is required because "we think you do not use this" is unfalsifiable
    and irritating, while "no login since 12 June" is a claim Joe can immediately confirm or
    correct.
    """
    out = []
    for s in streams:
        if s.get("lifecycle") != "active":
            continue
        absent = tuple(sorted(name for name, days in (signals.get(s["merchant"]) or {}).items()
                              if days is not None and days >= ZOMBIE_DAYS))
        if absent and len(absent) == len(signals.get(s["merchant"], {})):
            out.append({"merchant": s["merchant"], "absent_signals": absent,
                        "days": max(signals[s["merchant"]][a] for a in absent),
                        "text": (f"{s['merchant']} is still charging. No "
                                 f"{', '.join(absent)} for "
                                 f"{max(signals[s['merchant']][a] for a in absent)} days.")})
    return tuple(out)


def record_cancellation(*, stream, monthly_amount, insight_id, prior_total=0.0):
    """REQ-FIN-156. The cancellation, the amount, the originating insight, and a running total.

    The running total is the only place this system keeps score, and it keeps score of the
    system's own usefulness rather than of Joe's behaviour.
    """
    return {"stream": stream, "monthly_amount": round(float(monthly_amount), 2),
            "insight_id": insight_id,
            "running_total_monthly": round(float(prior_total) + float(monthly_amount), 2)}


def suppress_class(insight_class, suppressed):
    """REQ-FIN-158. Permanent, by class."""
    return insight_class in set(suppressed)


def rephrase_would_evade(insight_class, suppressed, *, aliases=None):
    """REQ-FIN-158's second clause: "SHALL NOT re-raise it under a different wording."

    Re-raising the same idea with new words is the behaviour that teaches a person to stop
    reading. A class rename is the easy way to do that by accident, so known aliases are checked
    too and a rename must be declared rather than silently introduced.
    """
    aliases = aliases or {}
    canonical = aliases.get(insight_class, insight_class)
    return canonical in {aliases.get(s, s) for s in suppressed}


# ---------------------------------------------------------------- §D.3

def check_copy(text, *, where=""):
    """REQ-FIN-191/192/193. Block publication and cite the rule.

    REQ-FIN-192 (trait, mood and mental-health inference) is delegated to
    `finance_never.check_text`, which already owns that vocabulary. Two copies of that list would
    drift, and the drift would be invisible until one surface shipped a word the other blocked.
    """
    from tools.engines.finance_never import check_text as never_check
    out = []
    low = (text or "").lower()
    for c in CAUSAL_CONNECTIVES:
        if re.search(rf"(?<![a-z]){re.escape(c)}(?![a-z])", low):
            out.append({"rule": "REQ-FIN-191", "token": c, "where": where,
                        "row": "copy_violation"})
    for v in never_check(text, where=where):
        if v.requirement in ("REQ-FIN-248", "REQ-FIN-247"):
            out.append({"rule": "REQ-FIN-192" if v.requirement == "REQ-FIN-248"
                        else "REQ-FIN-191", "token": v.detail, "where": where,
                        "row": "copy_violation"})
    return {"publish": not out, "violations": tuple(out)}


def annotation_prompt(txn, *, already_scheduled_days=()):
    """REQ-FIN-194/195. One prompt, the following morning, answerable in two taps.

    The morning rather than the moment: asking at 23:30 interrupts the evening it is asking
    about, and the answer would be worse for it.
    """
    occurred = txn.get("occurred_at")
    if (txn.get("category") or "").lower() != "bar" or occurred is None:
        return None
    if getattr(occurred, "hour", None) is None or occurred.hour < LATE_BAR_HOUR:
        return None
    day = (occurred + dt.timedelta(days=1)).date()
    if day in set(already_scheduled_days):
        return None
    return {"deliver_on": day, "taps": 2, "dismissible_without_answer": True,
            "questions": ("Who were you with?", "How is the morning?"),
            "stores_as": "annotations"}


def supersede_with_annotation(inferred, annotation):
    """REQ-FIN-196. Joe's annotation outranks any inference, always.

    Returns the value that stands. The inferred row is not deleted — it is superseded — so a
    later question about what the system believed before he answered still has an answer.
    """
    if annotation is None:
        return {"value": inferred.get("value"), "provenance": inferred.get("provenance",
                                                                          "inferred"),
                "superseded_by": None}
    return {"value": annotation.get("value"), "provenance": "joe",
            "confidence": 1.0, "superseded_by": annotation.get("id"),
            "supersedes": inferred.get("id")}


def drink_prior(*, tab_amount, episode_has_consume_atom, requested_as_prior=False):
    """REQ-FIN-197/198. There is no function here that returns a drink COUNT.

    REQ-FIN-197 forbids estimating volume, units or standard drinks from an amount. REQ-FIN-198
    permits the tab as a weak, disclosed PRIOR. The distinction is not cosmetic:

      * an estimate answers "how much did I drink" with a number derived from a price;
      * a prior is a labelled input to something else, capped at 0.30 confidence, and discarded
        the moment a real observation exists.

    So this returns None unless the caller asks for a prior explicitly, and None again the moment
    a `consume` atom exists for the episode. `$60 at a bar` is a round for other people as often
    as it is four drinks for Joe.
    """
    if not requested_as_prior:
        return None
    if episode_has_consume_atom:
        # REQ-FIN-198: "SHALL discard it the moment an actual consume atom exists".
        return None
    return {"kind": "weak_prior_only", "basis": "bar_tab_amount",
            "tab_amount": round(float(tab_amount), 2),
            "provenance": "inferred", "confidence": DRINK_PRIOR_MAX_CONFIDENCE,
            "drink_count": None,
            "disclosure": ("A bar tab is a weak prior, not a drink count. It is disclosed as "
                           "inferred at confidence 0.30 and is discarded as soon as a logged "
                           "drink exists for this episode.")}


def frame_against_goals(pattern, goals, *, tier, what_would_raise_it, gap=None):
    """REQ-FIN-200 / RULE-25. Fit with Joe's own stated goals, never restraint.

    The gap MAY be named — naming it is often the useful part — but only with its tier, its
    uncertainty and what would raise it, and never as an established fact. Framing around
    restraint instead would make the system an authority on how Joe should live, which is a role
    nothing in a transaction log qualifies it for.
    """
    out = {"pattern": pattern, "goals": tuple(goals), "evidence_tier": tier,
           "what_would_raise_it": what_would_raise_it, "asserted_as_fact": False,
           "framing": "fit_with_stated_goals"}
    if gap:
        out["gap"] = gap
        out["gap_qualifier"] = (f"At {tier}. {what_would_raise_it}")
    return out
