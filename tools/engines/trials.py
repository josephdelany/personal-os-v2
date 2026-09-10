"""B19 §D — randomized micro-trials (REQ-INF-200..217).

Pure: no database, no clock, no model. Every function takes its inputs and returns a decision.

WHY A TRIAL AT ALL. Everything else in this system is observational: it watches what Joe already
does and tries to strip out confounding after the fact. A randomized block trial is the one
design where the assignment is not caused by anything about Joe's day, which is why
EXPERIMENTAL sits above CONFIRMED_OBSERVATIONAL on the ladder. It is also the only part of the
system that ASKS JOE TO DO SOMETHING, so the bar for starting one is deliberately high.

WHY POWER IS COMPUTED BEFORE THE TRIAL AND REFUSED BELOW 0.80 (REQ-INF-207/208). An
underpowered trial is worse than no trial: it costs six weeks of Joe's compliance and then
returns a null that means "we could not have seen it" while reading as "it does not work". The
refusal states the duration that WOULD work and the larger effect the requested duration COULD
detect, because "no" without either is not a decision Joe can act on.

WHY BLOCK ORDER IS RANDOMIZED RATHER THAN ALTERNATED (REQ-INF-203). ABABAB is perfectly
confounded with any weekly or fortnightly rhythm -- and Joe's life has several. A seeded
permutation is not.

WHY DEVIATIONS ARE KEPT (REQ-INF-209/210/211). A day where Joe did the opposite of the
assignment is data, not dirt. Dropping it silently turns an intention-to-treat estimate into a
per-protocol one, which is exactly the substitution that makes adherence look like efficacy. So
deviating days stay in, flagged; ITT over ASSIGNED arms is primary; per-protocol is secondary
and labelled; and above 20% deviation the trial cannot reach EXPERIMENTAL at all.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

from scipy import stats as _sp

MIN_POWER = 0.80            # REQ-INF-208
MIN_WEEKS_FOR_EXPERIMENTAL = 6      # REQ-INF-206
MAX_DEVIATION_RATE = 0.20           # REQ-INF-211/214
DECLINE_COOLDOWN_DAYS = 7           # REQ-INF-217
ALPHA = 0.05


@dataclass(frozen=True)
class Refusal:
    """RULE-06. Why a trial was NOT started, in terms Joe can act on."""
    reason: str
    detail: str
    required_blocks: int | None = None
    detectable_effect: float | None = None


def seed_for(trial_id: str) -> int:
    """Deterministic from the trial id (REQ-INF-202).

    `hash()` is salted per process in Python 3, so a rerun would produce a DIFFERENT assignment
    sequence for the same trial -- and an assignment that changes when you look at it again is
    not a randomisation, it is a rewrite of history. BLAKE2b is stable across processes and
    releases.
    """
    return int.from_bytes(hashlib.blake2b(trial_id.encode(), digest_size=8).digest(), "big")


def effective_n(n_blocks: int, rho: float) -> float:
    """REQ-INF-215 / RULE-21. Block means are still autocorrelated; n is not n_eff.

    Blocks are contiguous, so adjacent block means share a boundary and a slow-moving trend.
    Treating 12 blocks as 12 independent observations overstates precision, which inflates power
    at the planning stage and confidence at the analysis stage -- the same error twice, in the
    direction that makes a trial look better than it is.
    """
    rho = max(-0.99, min(0.99, float(rho)))
    return n_blocks * (1.0 - rho) / (1.0 + rho)


def power(n_blocks: int, mde_sd: float, rho: float = 0.0, alpha: float = ALPHA) -> float:
    """Two-sided power for a balanced two-arm comparison of block means (REQ-INF-207).

    `mde_sd` is the minimum detectable effect in standard deviations of the BLOCK MEAN. The
    normal approximation is used deliberately: at the block counts a personal trial can reach
    (10-30) the t-correction moves power by a couple of points, and presenting a power figure
    to three decimals would imply a precision the assumption of a known SD does not have.
    """
    if n_blocks < 2 or mde_sd <= 0:
        return 0.0
    n_eff = effective_n(n_blocks, rho)
    if n_eff < 2:
        return 0.0
    # Balanced arms: half the effective blocks per arm.
    se = math.sqrt(4.0 / n_eff)
    z = _sp.norm.ppf(1 - alpha / 2)
    lam = abs(mde_sd) / se
    return float(_sp.norm.cdf(lam - z) + _sp.norm.cdf(-lam - z))


def blocks_required(mde_sd: float, rho: float = 0.0, alpha: float = ALPHA,
                    target: float = MIN_POWER, cap: int = 400) -> int | None:
    """The smallest block count reaching `target` power, or None if `cap` does not."""
    for n in range(2, cap + 1):
        if power(n, mde_sd, rho, alpha) >= target:
            return n
    return None


def detectable_effect(n_blocks: int, rho: float = 0.0, alpha: float = ALPHA,
                      target: float = MIN_POWER) -> float | None:
    """The smallest effect this many blocks could detect at `target` power (REQ-INF-208).

    A refusal that only says "not enough power" leaves Joe with nothing. This is the honest
    counter-offer: at the duration you asked for, here is what could actually be seen.
    """
    lo, hi = 1e-4, 10.0
    if power(n_blocks, hi, rho, alpha) < target:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        if power(n_blocks, mid, rho, alpha) >= target:
            hi = mid
        else:
            lo = mid
    return round(hi, 3)


def propose(exposure, outcome, block_days, n_blocks, mde_sd, *, rho=0.0,
            washout_days=0, role=None, declined_days_ago=None):
    """REQ-INF-203/206/207/208/216/217. Returns a plan dict or a Refusal.

    Every gate here refuses BEFORE the trial exists, because REQ-INF-201 requires the complete
    row to be written before the first assignment and REQ-INF-213 forbids changing the primary
    outcome or analysis method afterwards. A trial that has to be edited after it starts is a
    trial that was not thought through, and the register cannot express the edit.
    """
    # REQ-INF-216. Randomising something Joe cannot choose is not a trial; it is waiting. The
    # default is `context` for the same reason as in chains.py -- silence is not permission.
    if role != "lever":
        return Refusal("exposure_is_not_a_lever",
                       f"{exposure} is marked {role or 'context'} in the metric registry. A "
                       f"trial randomises something Joe DECIDES; randomising something he only "
                       f"observes would assign an arm nobody can comply with.")
    if declined_days_ago is not None and declined_days_ago < DECLINE_COOLDOWN_DAYS:
        # REQ-INF-217. Proposed, not imposed. Re-asking inside a week is nagging, and a system
        # that nags gets ignored wholesale rather than declined per trial.
        return Refusal("declined_recently",
                       f"Joe declined this trial {declined_days_ago} day(s) ago; it will not be "
                       f"re-proposed for {DECLINE_COOLDOWN_DAYS} days.")
    # REQ-INF-203. A block shorter than the washout means the next block starts before the last
    # exposure has worn off, so the arms bleed into each other and the contrast is diluted
    # toward zero -- a bias TOWARD the null, which reads as a clean negative result.
    if block_days <= washout_days:
        return Refusal("block_shorter_than_washout",
                       f"a {block_days}-day block does not exceed the declared {washout_days}-day "
                       f"washout, so each block would begin before the previous exposure ended")
    weeks = (block_days * n_blocks) / 7.0
    if weeks < MIN_WEEKS_FOR_EXPERIMENTAL:
        # REQ-INF-206. Below six weeks the result cannot reach EXPERIMENTAL, so running it
        # buys a tier the observational path already offers at no cost to Joe.
        return Refusal("below_minimum_duration",
                       f"{weeks:.1f} weeks of blocks cannot reach EXPERIMENTAL; "
                       f"{MIN_WEEKS_FOR_EXPERIMENTAL} weeks is the floor",
                       required_blocks=math.ceil(MIN_WEEKS_FOR_EXPERIMENTAL * 7 / block_days))
    achieved = power(n_blocks, mde_sd, rho)
    if achieved < MIN_POWER:
        # REQ-INF-208. The refusal carries BOTH counter-offers: the duration that would work,
        # and the effect the requested duration could see.
        return Refusal("underpowered",
                       f"power is {achieved:.2f} against an effect of {mde_sd} SD over "
                       f"{n_blocks} blocks (n_eff {effective_n(n_blocks, rho):.1f} after "
                       f"autocorrelation); {MIN_POWER:.2f} is the floor",
                       required_blocks=blocks_required(mde_sd, rho),
                       detectable_effect=detectable_effect(n_blocks, rho))
    return dict(exposure=exposure, outcome=outcome, block_length_days=block_days,
                n_blocks_planned=n_blocks, washout_days=washout_days,
                mde_sd=mde_sd, rho=rho, power=round(achieved, 3),
                weeks=round(weeks, 1), primary_outcome_metric=outcome,
                analysis_method="itt_block_means_hac")


def assign_blocks(trial_id: str, n_blocks: int) -> list[str]:
    """REQ-INF-202/203. A seeded PERMUTATION of balanced arms, not an alternation.

    ABABAB is perfectly confounded with any weekly or fortnightly rhythm, and Joe's life has
    several -- pay dates, weekends, a training split. The permutation is balanced first so the
    arms cannot drift apart by chance at small block counts, then shuffled.
    """
    if n_blocks < 2:
        raise ValueError("a trial needs at least two blocks to have two arms")
    arms = ["A"] * (n_blocks // 2) + ["B"] * (n_blocks - n_blocks // 2)
    random.Random(seed_for(trial_id)).shuffle(arms)
    return arms


def deviation_rate(assigned_days: int, deviating_days: int) -> float:
    if assigned_days <= 0:
        return 0.0
    return deviating_days / assigned_days


def result_tier(n_blocks_planned, n_blocks_completed, assigned_days, deviating_days,
                analysis_ran: bool, blinded: bool):
    """REQ-INF-211/214/205. The tier, and the sentence that must travel with it.

    EXPERIMENTAL requires ALL THREE: every planned block completed, deviation at or below 20%,
    and the pre-specified analysis actually run. Any one missing gives INSUFFICIENT -- not a
    downgrade to CONFIRMED_OBSERVATIONAL, because a half-finished randomisation is not an
    observational study, it is a randomisation that failed.
    """
    rate = deviation_rate(assigned_days, deviating_days)
    reasons = []
    if n_blocks_completed < n_blocks_planned:
        reasons.append(f"{n_blocks_completed} of {n_blocks_planned} planned blocks completed")
    if rate > MAX_DEVIATION_RATE:
        reasons.append(f"{rate:.0%} of assigned days deviated (the limit is "
                       f"{MAX_DEVIATION_RATE:.0%})")
    if not analysis_ran:
        reasons.append("the pre-specified analysis did not run")
    tier = "INSUFFICIENT" if reasons else "EXPERIMENTAL"
    # REQ-INF-205. Not a footnote: an unblinded behavioural trial can move its own outcome
    # through expectation alone, and the reader must be told at the point of reading.
    note = ("" if blinded else
            "Joe knew which arm each block was in; this exposure admits no indistinguishable "
            "placebo, so expectation could contribute to the effect. ")
    return dict(tier=tier, deviation_rate=round(rate, 3), blinded=blinded,
                reasons=tuple(reasons),
                note=note + ("" if tier == "EXPERIMENTAL" else "Reported at INSUFFICIENT: "
                             + "; ".join(reasons) + "."))


def analyse(blocks, per_protocol=False):
    """REQ-INF-210/215. ITT over ASSIGNED arms is primary; per-protocol is secondary.

    `blocks` is a sequence of (assigned_arm, block_mean, deviated). ITT keeps every block under
    the arm it was ASSIGNED, deviations included. Dropping them is the substitution that makes
    adherence look like efficacy: the days Joe complied are the days he felt able to, and those
    differ from the rest in ways the exposure did not cause.
    """
    used = [b for b in blocks if not (per_protocol and b[2])]
    a = [m for arm, m, _ in used if arm == "A"]
    b = [m for arm, m, _ in used if arm == "B"]
    if len(a) < 2 or len(b) < 2:
        return Refusal("too_few_blocks_per_arm",
                       f"{len(a)} A-blocks and {len(b)} B-blocks; a contrast needs two of each")
    diff = sum(b) / len(b) - sum(a) / len(a)
    pooled = (_sp.tstd(a) ** 2 * (len(a) - 1) + _sp.tstd(b) ** 2 * (len(b) - 1))
    pooled = math.sqrt(pooled / (len(a) + len(b) - 2)) if len(a) + len(b) > 2 else 0.0
    return dict(analysis="per_protocol" if per_protocol else "itt",
                n_blocks=len(used), delta=round(diff, 4),
                delta_sd=round(diff / pooled, 4) if pooled else None,
                blocks_a=len(a), blocks_b=len(b),
                deviating_blocks=sum(1 for _, _, d in blocks if d),
                label=("SECONDARY, per-protocol: deviating blocks removed. Adherence is not "
                       "random, so this is not an unbiased estimate of the exposure's effect."
                       if per_protocol else
                       "PRIMARY, intention-to-treat over assigned arms."))


# ---------------------------------------------------------------- blinding and deviation

def blinding(exposure, *, admits_indistinguishable_placebo):
    """REQ-INF-204/205. Blind where a placebo is physically indistinguishable; say so where not.

    Most of Joe's exposures are behavioural and cannot be blinded — he knows whether he had
    caffeine. A supplement in an identical capsule can be. The distinction is physical, not a
    matter of effort, so the function asks about the exposure rather than about intent.

    Where blinding IS possible it is not optional: an unblinded supplement trial measures the
    supplement plus Joe's expectation of it, and the expectation is the larger of the two often
    enough to matter.
    """
    if admits_indistinguishable_placebo:
        return {"blinded": True, "until": "trial_completes",
                "note": ("This exposure admits an indistinguishable placebo, so the assignment is "
                         "hidden until the trial completes. An unblinded version would measure "
                         "the exposure plus the expectation of it.")}
    return {"blinded": False,
            "impossibility": (f"{exposure} cannot be blinded: there is no physically "
                              f"indistinguishable placebo for it, and Joe necessarily knows "
                              f"which arm he is in.")}


def on_deviation_threshold(trial, *, deviation_rate, already_notified, block_days):
    """REQ-INF-212. Notify ONCE, offer a shorter block, and never repeat.

    A shorter block is the right offer rather than "try harder": a 20% deviation rate usually
    means the block length does not fit Joe's life, and the fix is the design rather than the
    discipline. Repeating the notification would make a design problem feel like a personal one.
    """
    if deviation_rate <= MAX_DEVIATION_RATE or already_notified:
        return None
    return {"notify": True, "once": True,
            "offer": {"action": "restart_with_shorter_block",
                      "current_block_days": block_days,
                      "proposed_block_days": max(1, block_days // 2)},
            "text": (f"{deviation_rate:.0%} of assigned days have deviated. A "
                     f"{max(1, block_days // 2)}-day block may fit better than the current "
                     f"{block_days}. Restart with the shorter block?"),
            "repeat": False}
