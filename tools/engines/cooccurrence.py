"""B17 §D.1/D.2 — the link object and its evidence tiers (REQ-FIN-160..180).

Pure: no database, no clock, no model.

WHAT THIS PREVENTS. Spend can be correlated against sleep, mood, workouts, location, substances
and productivity. That is hundreds of implicit tests, and REQ-FIN-176 states the consequence
plainly: SOMETHING WILL ALWAYS LOOK SIGNIFICANT. A system that computes a correlation whenever
two series are available will therefore produce a steady supply of striking, false findings, and
each one will arrive with a real number attached.

So a co-occurrence may only be computed for a hypothesis Joe registered FIRST, the foreign key is
NOT NULL, and an unregistered pairing aborts and is logged rather than quietly skipped -- the log
is how a fishing expedition becomes visible instead of just unsuccessful.

THE TIER LADDER, AND WHY ITS TOP RUNG IS WELDED SHUT.

  T0 OBSERVED     one dated fact, n=1, no pattern claimed, no interpretation attached
  T1 DESCRIPTIVE  a count over a stated window, n >= 10, day-of-week reported
  T2 CO-OCCURRENT a rate difference across a pre-registered condition, n >= 20 in the SMALLER
                  arm, day-of-week controlled
  T3 CAUSAL       reserved, and permanently unreachable by this subsystem

T3 exists in the vocabulary so that the ladder is honest about having a rung above T2, and it is
unreachable because observational spend data cannot support a causal claim no matter how large n
becomes. `assign_tier` has no code path that returns it and a test asserts as much.

WHY DAY-OF-WEEK IS CONTROLLED, NOT REPORTED (REQ-FIN-177). Friday is both the high-work day and
the social day. Almost every apparent finding in this domain is day-of-week wearing a costume,
and controlling for it is what separates "he drinks when he is stressed" from "both happen on
Fridays".

WHY CASH IS EXCLUDED FROM EVERY DENOMINATOR (REQ-FIN-179). Cash is not random missingness. It is
concentrated on exactly the behaviour being examined -- a bar round, a split tab -- so leaving it
in the denominator silently deflates every rate involving the thing most likely to be paid for in
cash.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

TIERS = ("T0_OBSERVED", "T1_DESCRIPTIVE", "T2_COOCCURRENT", "T3_CAUSAL")
T1_MIN_N = 10                      # REQ-FIN-172
T2_MIN_SMALLER_ARM = 20            # REQ-FIN-173
ALCOHOL_WINDOW_HOURS = 3           # REQ-FIN-161/164
LINKED_CATEGORIES = frozenset({"bar", "restaurant"})


class UnregisteredHypothesis(Exception):
    """REQ-FIN-176. The computation aborts; it does not degrade to a lower tier."""


@dataclass(frozen=True)
class Cooccurrence:
    hypothesis_id: str             # REQ-FIN-175, NOT NULL by construction
    atom_ids: tuple
    subject_day: dt.date
    tier: str
    n: int
    smaller_arm_n: int | None = None
    day_of_week_controlled: bool = False
    date_only: bool = False        # REQ-FIN-163
    excluded_cash_n: int = 0       # REQ-FIN-179
    note: str = ""

    def __post_init__(self):
        if not self.hypothesis_id:
            raise UnregisteredHypothesis(
                "REQ-FIN-175: a co-occurrence carries a non-null hypothesis foreign key")
        if self.tier not in TIERS:
            raise ValueError(f"REQ-FIN-170: {self.tier!r} is not one of {TIERS}")
        if self.tier == "T3_CAUSAL":
            raise ValueError("REQ-FIN-174: T3 is permanently unreachable by this subsystem; "
                             "observational spend data cannot support a causal claim at any n")


def assign_tier(*, n, smaller_arm_n=None, day_of_week_controlled=False):
    """REQ-FIN-170/172/173/174. Exactly one tier, and never T3.

    Returns (tier, displayable, reason). A finding that fails its tier's floor is NOT silently
    demoted to the tier below: T1 and T2 answer different questions, and presenting an
    underpowered rate difference as a count would answer a question nobody asked.
    """
    if n <= 1:
        return "T0_OBSERVED", True, "a single dated fact; no pattern is claimed"
    if smaller_arm_n is not None:
        if not day_of_week_controlled:
            return ("T2_COOCCURRENT", False,
                    "REQ-FIN-177: day-of-week is not controlled, and Friday is both the "
                    "high-work day and the social day")
        if smaller_arm_n < T2_MIN_SMALLER_ARM:
            return ("T2_COOCCURRENT", False,
                    f"REQ-FIN-173: the smaller arm holds {smaller_arm_n}, below {T2_MIN_SMALLER_ARM}")
        return "T2_COOCCURRENT", True, ""
    if n < T1_MIN_N:
        return "T1_DESCRIPTIVE", False, f"REQ-FIN-172: n={n} is below {T1_MIN_N}"
    return "T1_DESCRIPTIVE", True, ""


def render(co, claim):
    """REQ-FIN-171/178/179. The sentence, or a refusal.

    Every displayed co-occurrence states its n IN THE SAME SENTENCE as its claim. A claim whose n
    sits in a tooltip is a claim most readers will meet without its n.
    """
    tier, ok, reason = assign_tier(n=co.n, smaller_arm_n=co.smaller_arm_n,
                                   day_of_week_controlled=co.day_of_week_controlled)
    if not ok:
        return {"display": False, "reason": reason}
    if tier == "T0_OBSERVED":
        # REQ-FIN-171. A dated statement of what happened, with nothing attached. One evening is
        # an anecdote, and an interpretation on top of n=1 is the whole of the harm this ladder
        # exists to prevent.
        return {"display": True, "tier": tier,
                "text": f"On {co.subject_day.isoformat()}: {claim}.",
                "interpretation": None}
    parts = [f"{claim} (n={co.n}"]
    if co.smaller_arm_n is not None:
        parts.append(f", smaller arm n={co.smaller_arm_n}")
    parts.append(")")
    text = "".join(parts) + "."
    if co.excluded_cash_n:
        # REQ-FIN-179. Stated, not merely done. An excluded denominator nobody is told about is
        # a rate that cannot be checked.
        text += (f" Excludes {co.excluded_cash_n} cash or ATM transaction(s): cash is a "
                 f"systematic blind spot concentrated on this behaviour, not random missingness.")
    if co.date_only:
        text += " Date-only import: no time of day, so no within-day claim is made."
    return {"display": True, "tier": tier, "text": text}


def compute(*, hypothesis_id, registered_hypotheses, atom_ids, subject_day, n,
            smaller_arm_n=None, day_of_week_controlled=False, date_only=False,
            excluded_cash_n=0, attempted_pairing=None, log=None):
    """REQ-FIN-175/176. Registered first, or aborted and logged.

    The abort is deliberate rather than a skip. A pairing that is silently not computed leaves no
    trace, so a job quietly fishing across every lens looks identical to a job doing nothing. The
    log is what makes the fishing visible.
    """
    if hypothesis_id not in set(registered_hypotheses):
        if log is not None:
            log.append({"event": "unregistered_pairing_aborted",
                        "pairing": attempted_pairing or hypothesis_id,
                        "reason": ("REQ-FIN-176: correlating spend against sleep, mood, workouts, "
                                   "location, substances and productivity is hundreds of implicit "
                                   "tests and something will always look significant")})
        raise UnregisteredHypothesis(
            f"REQ-FIN-176: no registered hypothesis for {attempted_pairing or hypothesis_id!r}")
    tier, _, _ = assign_tier(n=n, smaller_arm_n=smaller_arm_n,
                             day_of_week_controlled=day_of_week_controlled)
    return Cooccurrence(hypothesis_id=hypothesis_id, atom_ids=tuple(atom_ids),
                        subject_day=subject_day, tier=tier, n=n, smaller_arm_n=smaller_arm_n,
                        day_of_week_controlled=day_of_week_controlled, date_only=date_only,
                        excluded_cash_n=excluded_cash_n)


# ---------------------------------------------------------------- D.1 building the links

def link_transaction(txn, *, consume_atoms=(), mood_atoms=(), place_atoms=(),
                     window_hours=ALCOHOL_WINDOW_HOURS):
    """REQ-FIN-161/162/163. What co-occurs with a bar or restaurant charge.

    Joined on `occurred_at`, NEVER on `posted_at` (REQ-FIN-162): settlement is commonly the
    following day, and joining on it would attribute a Thursday night to Friday -- silently
    moving every late-week evening into the weekend and manufacturing the weekend pattern the
    analysis was looking for.
    """
    if (txn.get("category") or "").lower() not in LINKED_CATEGORIES:
        return None
    occurred = txn.get("occurred_at")
    if occurred is None:
        return None
    date_only = bool(txn.get("date_only")) or getattr(occurred, "hour", None) is None
    day = txn.get("subject_day") or (occurred.date() if hasattr(occurred, "date") else occurred)

    if date_only:
        # REQ-FIN-163. A CSV import with no time of day cannot support a +/-3h window. The link
        # is kept as a same-day fact and BARRED from within-day and hour-of-day analysis, rather
        # than dropped -- the charge did happen.
        near = ()
    else:
        window = dt.timedelta(hours=window_hours)
        near = tuple(a for a in consume_atoms
                     if a.get("props", {}).get("class") == "alcohol"
                     and abs(a["occurred_at"] - occurred) <= window)
    return {
        "subject_day": day,
        "date_only": date_only,
        "alcohol_atoms": near,
        "mood_atoms": tuple(a for a in mood_atoms if a.get("subject_day") == day),
        "place_atoms": tuple(a for a in place_atoms
                             if not date_only and a.get("starts_at") is not None
                             and a["starts_at"] <= occurred <= a.get("ends_at", occurred)),
        "implied_unlogged": (not near) and not date_only,     # REQ-FIN-165
        "eligible_for_within_day": not date_only,
    }


def missingness(links):
    """REQ-FIN-165. Implied-but-unlogged, counted whether or not Joe ever answers a prompt.

    This is the quantity the analysis layer needs and the prompt does not produce. If the count
    only existed when he replied, then the days he ignored the prompt -- the busiest ones, the
    ones most likely to involve a bar -- would look like days with no drinking.
    """
    total = sum(1 for l in links if l)
    implied = sum(1 for l in links if l and l["implied_unlogged"])
    date_only = sum(1 for l in links if l and l["date_only"])
    return {
        "occasions": total,
        "implied_unlogged": implied,
        "logged": total - implied - date_only,
        "date_only": date_only,
        "unlogged_fraction": round(implied / total, 3) if total else None,
        "note": ("Counted from transactions, independently of whether any prompt was answered. "
                 "A count that only existed when Joe replied would make the days he ignored the "
                 "prompt look like days with no drinking."),
    }


def prompt_once(link, already_prompted_days):
    """REQ-FIN-164. One dismissible prompt per occasion, offered once, never repeated."""
    if not link or not link["implied_unlogged"]:
        return None
    if link["subject_day"] in set(already_prompted_days):
        return None
    return {"day": link["subject_day"], "dismissible": True, "repeat": False,
            "text": "There was a bar or restaurant charge here with no drinks logged. Add them?"}


def alcohol_context(links, *, amounts=(), inbound_transfers=()):
    """REQ-FIN-166/180. Occasions are primary; the amount is secondary and netted.

    Visit count is robust to price variance and to splitting; an amount is not. A $120 tab that
    three people split is one occasion and $40 of Joe's money, and reporting the $120 as the
    alcohol metric would make a normal evening look like a heavy one.
    """
    gross = sum(float(a) for a in amounts)
    inbound = sum(float(t) for t in inbound_transfers)          # REQ-FIN-180 / REQ-FIN-050
    m = missingness(links)
    return {
        "primary_metric": "occasions",
        "occasions": m["occasions"],
        "logged": m["logged"],
        "implied_unlogged": m["implied_unlogged"],
        "secondary_amount_net": round(gross - inbound, 2),
        "netted_inbound": round(inbound, 2),
        "note": ("Occasions are the primary measure. Visit count is robust to price variance and "
                 "to splitting; an amount is not, and a split tab would read as a heavy evening."),
    }
