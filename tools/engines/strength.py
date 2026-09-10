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

import copy
import datetime as dt
from dataclasses import dataclass, field

# REQ-WKT-008/012: the formulas and the windows are DATA, named and versioned, never a choice
# made at query time (RULE-13). `valid_reps` is each formula's own fitted range; the effective
# range in force is PARAMETERS["strength_e1rm_lb"]["valid_reps"], which the catalogue can set.
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

# RULE-13, made TRUE rather than asserted. Migration 0061's header says a method's numbers are
# "DATA beside it rather than constants in Python", and that "the windows and the formula set
# can be changed without a code change". That was false: nothing read
# config.derivation_catalogue.parameters, and the only test on it asserted that the migration
# TEXT contained the same literals this module holds -- proving the two copies agreed, not that
# either was derived from the other. Changing the table changed no computed figure.
#
# The module stays PURE -- no database, no clock -- because that is what makes the arithmetic
# exhaustively testable. So the catalogue rows are pushed IN by whatever holds a connection,
# rather than pulled from here. The constants above are the fallback when nothing has been
# loaded, not a second source of truth.
# Seeded FROM the formula table rather than restating its numbers, so there is one source and
# not two that a future edit could drift apart. Every registered formula currently shares the
# same fitted range; if one ever does not, this raises rather than quietly widening the range
# and licensing an extrapolation the narrower formula was never fitted for.
_RANGES = {spec["valid_reps"] for spec in FORMULAS.values()}
if len(_RANGES) != 1:
    raise ValueError(f"registered formulas no longer share one fitted range ({_RANGES}); "
                     f"e1rm must filter per formula again before this parameter is meaningful")

PARAMETERS = {
    "strength_e1rm_lb": dict(formulas=tuple(sorted(FORMULAS)), valid_reps=next(iter(_RANGES))),
    "strength_acwr": dict(acute_days=ACWR_ACUTE_DAYS, chronic_days=ACWR_CHRONIC_DAYS,
                          windows_calibrated=ACWR_WINDOWS_ARE_CALIBRATED),
}


def apply_catalogue_parameters(by_measure):
    """Load RULE-13 parameters from config.derivation_catalogue rows.

    `by_measure` maps a measure name to its `parameters` object. Unknown measures and unknown
    keys are IGNORED rather than silently accepted: a typo in the table must not become a
    parameter this module thinks it is honouring. An unknown FORMULA name raises, because
    naming a formula that does not exist is a request for a number this module cannot compute,
    and quietly dropping it would narrow the interval -- reporting MORE precision from a
    configuration error (REQ-WKT-009).
    """
    # Validated into a CANDIDATE first, then committed in one step. Mutating PARAMETERS as it
    # went meant a row that failed validation halfway left the module running on a mixture of
    # the old configuration and the new one -- and the exception would name the bad value while
    # saying nothing about the good ones already applied behind it.
    candidate = copy.deepcopy(PARAMETERS)
    for measure, params in (by_measure or {}).items():
        target = candidate.get(measure)
        if target is None or not isinstance(params, dict):
            continue
        for key, value in params.items():
            if key not in target:
                continue
            if key == "formulas":
                names = tuple(sorted(value))
                unknown = [n for n in names if n not in FORMULAS]
                if unknown:
                    raise ValueError(
                        f"config.derivation_catalogue names formula(s) this module cannot "
                        f"compute: {', '.join(unknown)}; known are {', '.join(sorted(FORMULAS))}")
                if not names:
                    raise ValueError("at least one e1RM formula must be registered; an empty "
                                     "set would make every e1RM an unexplained omission")
                target[key] = names
            elif key == "valid_reps":
                lo, hi = int(value[0]), int(value[1])
                if lo < 1 or hi < lo:
                    raise ValueError(f"valid_reps {value} is not an ascending range at or above 1")
                target[key] = (lo, hi)
            elif key in ("acute_days", "chronic_days"):
                target[key] = int(value)
            elif key == "windows_calibrated":
                target[key] = bool(value)
    if candidate["strength_acwr"]["chronic_days"] <= candidate["strength_acwr"]["acute_days"]:
        raise ValueError("the chronic window must be longer than the acute one")
    PARAMETERS.clear()
    PARAMETERS.update(candidate)
    return PARAMETERS


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
    registered = PARAMETERS["strength_e1rm_lb"]["formulas"]
    lo, hi = PARAMETERS["strength_e1rm_lb"]["valid_reps"]
    usable = [name for name in registered if lo <= reps <= hi]
    if not usable:
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


def acwr(daily_volume, as_of, acute_days=None, chronic_days=None):
    """REQ-WKT-012/018. Acute over chronic workload, or an Omission.

    `daily_volume` maps a date to that day's volume. A day ABSENT from the mapping is unknown,
    not zero — a skipped session is not zero volume (REQ-WKT-018) and an unlogged day is not a
    rest day (REQ-WKT-019). Coverage is returned so the caller can refuse a thin ratio rather
    than dividing two guesses.
    """
    # Resolved at CALL time, not at import time. A default argument evaluated at import binds
    # the constant forever, so a catalogue load after import would change nothing -- which is
    # precisely the defect this is fixing.
    if acute_days is None:
        acute_days = PARAMETERS["strength_acwr"]["acute_days"]
    if chronic_days is None:
        chronic_days = PARAMETERS["strength_acwr"]["chronic_days"]
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
        windows_calibrated=PARAMETERS["strength_acwr"]["windows_calibrated"],
        # The caveat states the windows it ACTUALLY used. It named 7 and 28 unconditionally
        # while the windows were configurable, so a recalibrated pair would have been described
        # by a sentence about the old one -- an untrue disclosure attached to a true number.
        caveat=(f"the {acute_days} and {chronic_days} day windows are provisional placeholders, "
                f"not calibrated to Joe; this ratio orders sessions against each other and "
                f"carries no threshold")
               if not PARAMETERS["strength_acwr"]["windows_calibrated"] else
               (f"the {acute_days} and {chronic_days} day windows are calibrated; this ratio "
                f"orders sessions against each other and carries no threshold"))
