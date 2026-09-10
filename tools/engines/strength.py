"""B18 — the workout derived measures (REQ-WKT-008..013, REQ-WKT-018/019).

RULE-09 and RULE-11: the model narrates, it never computes. This module is where every
strength number comes from, and it is pure — no database, no clock, no model — so the
arithmetic can be exercised exhaustively and cheaply.

WHY e1RM IS AN INTERVAL AND NOT A NUMBER (REQ-WKT-009). An e1RM from a submaximal set is
RESOLVED, not measured: nobody lifted it. Published formulas disagree — at 225 lb x 5, Epley
gives 262.5 and Brzycki 253.1 — and reporting either alone states a precision the method does
not have. The interval is the SPREAD ACROSS THE REGISTERED FORMULAS, an honest statement of
how much the choice of method matters, rather than an invented percentage band.

WHY A SET OUTSIDE THE VALIDATED RANGE PRODUCES NOTHING (REQ-WKT-010). Both formulas are fitted
on roughly 1-10 repetitions. A 20-rep set extrapolates far outside that, and the number would
look exactly like a good one. The omission is returned with its reason, so a missing e1RM is a
recorded fact rather than a silent absence (RULE-06).

WHY VOLUME REFUSES A PARTIAL SET. Load x reps needs both. A set with reps and no load — a
bodyweight movement the shortcut cannot mark (REQ-WKT-004) — contributes no volume and is
counted as excluded, because treating its load as zero would make a hard session look light.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

# REQ-WKT-008/012: the formulas and the windows are DATA, named and versioned, never a choice
# made at query time (RULE-13). `valid_reps` is each formula's own fitted range.
FORMULAS = {
    "epley":   dict(fn=lambda w, r: w * (1 + r / 30.0), valid_reps=(1, 10),
                    cite="Epley 1985"),
    "brzycki": dict(fn=lambda w, r: w * 36.0 / (37.0 - r), valid_reps=(1, 10),
                    cite="Brzycki 1993"),
}
METHOD_VERSION = "strength-v1"

# REQ-WKT-012: provisional placeholders (OQ-36). Every figure derived from them says so.
ACWR_ACUTE_DAYS, ACWR_CHRONIC_DAYS = 7, 28
ACWR_WINDOWS_ARE_CALIBRATED = False


@dataclass(frozen=True)
class Omission:
    """RULE-06. Why a measure was NOT computed, so the gap is a fact and not a silence."""
    reason: str
    detail: str = ""


@dataclass
class E1RM:
    low: float
    high: float
    estimate_method: str
    formulas: tuple[str, ...]

    @property
    def point(self) -> float:
        """The midpoint, for ordering only. It is never the answer on its own (RULE-08)."""
        return round((self.low + self.high) / 2.0, 2)


@dataclass
class Volume:
    total: float
    sets_counted: int
    sets_excluded: int = 0
    excluded_reasons: tuple[str, ...] = field(default_factory=tuple)
    method_version: str = METHOD_VERSION


def e1rm(load, reps):
    """REQ-WKT-008/009/010. An interval across the registered formulas, or an Omission."""
    if load is None or reps is None:
        return Omission("incomplete_set", "e1RM needs both a load and a repetition count")
    if load <= 0:
        # A bodyweight or assisted movement (REQ-WKT-004). Its e1RM is not zero; it is
        # undefined by this method, and zero would sort as the weakest set ever performed.
        return Omission("no_external_load", "load is not positive; the movement is bodyweight "
                                            "or assisted and this formula does not apply")
    usable = [name for name, spec in FORMULAS.items()
              if spec["valid_reps"][0] <= reps <= spec["valid_reps"][1]]
    if not usable:
        lo = min(s["valid_reps"][0] for s in FORMULAS.values())
        hi = max(s["valid_reps"][1] for s in FORMULAS.values())
        return Omission("reps_outside_validated_range",
                        f"{reps} repetitions is outside every registered formula's fitted "
                        f"range ({lo}-{hi}); extrapolating would produce a number that looks "
                        f"exactly like a good one")
    values = sorted(FORMULAS[name]["fn"](float(load), float(reps)) for name in usable)
    return E1RM(low=round(values[0], 2), high=round(values[-1], 2),
                estimate_method=f"formula_spread:{'+'.join(sorted(usable))}@{METHOD_VERSION}",
                formulas=tuple(sorted(usable)))


def volume(sets):
    """REQ-WKT-011. Sum of load x reps over sets, with what it could not count."""
    total, counted, excluded, reasons = 0.0, 0, 0, []
    for load, reps in sets:
        if load is None or reps is None or load <= 0 or reps <= 0:
            excluded += 1
            reasons.append("incomplete_or_bodyweight_set")
            continue
        total += float(load) * float(reps)
        counted += 1
    return Volume(total=round(total, 2), sets_counted=counted, sets_excluded=excluded,
                  excluded_reasons=tuple(sorted(set(reasons))))


def acwr(daily_volume, as_of, acute_days=ACWR_ACUTE_DAYS, chronic_days=ACWR_CHRONIC_DAYS):
    """REQ-WKT-012/018. Acute over chronic workload, or an Omission.

    `daily_volume` maps a date to that day's volume. A day ABSENT from the mapping is unknown,
    not zero — a skipped session is not zero volume (REQ-WKT-018) and an unlogged day is not a
    rest day (REQ-WKT-019). Coverage is returned so the caller can refuse a thin ratio rather
    than dividing two guesses.
    """
    if chronic_days <= acute_days:
        raise ValueError("the chronic window must be longer than the acute one")

    def window(days):
        first = as_of - dt.timedelta(days=days - 1)
        seen = {d: v for d, v in daily_volume.items() if first <= d <= as_of}
        return sum(seen.values()), len(seen)

    acute_sum, acute_n = window(acute_days)
    chronic_sum, chronic_n = window(chronic_days)
    if chronic_n == 0:
        return Omission("no_chronic_data", "no logged training day in the chronic window")
    # RATES, not totals: the windows are different lengths, and dividing a 7-day total by a
    # 28-day total would report a quarter of the truth. Absent days divide out of both.
    acute_rate = acute_sum / acute_n if acute_n else 0.0
    chronic_rate = chronic_sum / chronic_n
    if chronic_rate == 0:
        return Omission("zero_chronic_workload", "every logged chronic day carried no volume")
    return dict(
        ratio=round(acute_rate / chronic_rate, 3),
        acute_days_with_data=acute_n, chronic_days_with_data=chronic_n,
        acute_window=acute_days, chronic_window=chronic_days,
        method_version=METHOD_VERSION,
        # REQ-WKT-012: the windows are provisional placeholders (OQ-36) and every figure
        # derived from them must say so until they are calibrated.
        windows_calibrated=ACWR_WINDOWS_ARE_CALIBRATED,
        caveat=("the 7 and 28 day windows are provisional placeholders, not calibrated to Joe; "
                "this ratio orders sessions against each other and carries no threshold"))
