"""B17 §D.3 — the habit-rhythm engine (REQ-FIN-199).

Pure: no database, no clock, no model.

WHY A CIRCULAR HISTOGRAM AND CHI-SQUARE IS THE DEFAULT. The question "is there a rhythm here" on
day-of-week and hour-of-day data is a question about whether counts depart from uniform. A
chi-square against uniform answers exactly that, needs no period search, and has a null
distribution nobody has to defend. It is boring, and boring is the correct default for a method
that will run against every merchant class Joe has.

WHY LOMB-SCARGLE IS FENCED (REQ-FIN-199). A periodogram will ALWAYS return a peak. On a short,
irregular series the highest peak is noise, and it arrives looking exactly like a discovery --
a period, a power, a plot. So it runs only where the series contains enough cycles for a
false-alarm probability to mean something, and any peak that does not clear the FAP is not
reported at all. Not reported at a lower tier: not reported.

WHY THE HOUR-OF-DAY TEST REFUSES DATE-ONLY ROWS. A CSV import with no clock has no hour, and
scoring it as midnight would put a spike at 00:00 in every histogram and then find it
significant. REQ-FIN-163 already bars those rows from within-day analysis; this module refuses
them rather than trusting the caller to have filtered.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from scipy import stats as _sp

MIN_COUNT_FOR_CHISQUARE = 20      # below this the asymptotic null is not trustworthy
MIN_CYCLES_FOR_PERIODOGRAM = 10   # REQ-FIN-199: "enough cycles for a FAP to be computed"
FAP_THRESHOLD = 0.05


@dataclass(frozen=True)
class NoRhythm:
    """RULE-06. Why no rhythm was reported, which is different from 'there is none'."""
    reason: str
    detail: str
    n: int = 0


def day_of_week_rhythm(days, *, min_count=MIN_COUNT_FOR_CHISQUARE):
    """Chi-square of the seven day-of-week counts against uniform."""
    counts = [0] * 7
    for d in days:
        counts[d.weekday()] += 1
    n = sum(counts)
    if n < min_count:
        return NoRhythm("too_few_observations",
                        f"{n} observations; below {min_count} the chi-square null is asymptotic "
                        f"and its p-value would be a number without a distribution behind it", n)
    expected = n / 7.0
    stat = sum((c - expected) ** 2 / expected for c in counts)
    p = float(_sp.chi2.sf(stat, df=6))
    peak = max(range(7), key=lambda i: counts[i])
    return {"method": "chi_square_vs_uniform", "counts": tuple(counts), "n": n,
            "statistic": round(stat, 4), "p_value": round(p, 6), "df": 6,
            "peak_weekday": peak, "peak_count": counts[peak],
            "uniform_rejected": p < 0.05,
            # The effect size, because a large n makes a trivial departure significant and the
            # p-value alone would then read as a finding.
            "cramers_v": round(math.sqrt(stat / (n * 6)), 4)}


def hour_of_day_rhythm(times, *, bins=24, min_count=MIN_COUNT_FOR_CHISQUARE):
    """Circular histogram over the hour of day, chi-square against uniform.

    Rows with no clock are REFUSED rather than scored as midnight: a date-only import would put
    a spike at 00:00 in every histogram and the test would then find it significant.
    """
    usable = [t for t in times if getattr(t, "hour", None) is not None]
    if len(usable) < len(list(times)):
        dropped = len(list(times)) - len(usable)
    else:
        dropped = 0
    counts = [0] * bins
    for t in usable:
        counts[t.hour % bins] += 1
    n = sum(counts)
    if n < min_count:
        return NoRhythm("too_few_observations",
                        f"{n} timed observations ({dropped} had no clock and were refused "
                        f"rather than scored as midnight)", n)
    expected = n / bins
    stat = sum((c - expected) ** 2 / expected for c in counts)
    p = float(_sp.chi2.sf(stat, df=bins - 1))
    peak = max(range(bins), key=lambda i: counts[i])
    return {"method": "circular_histogram_chi_square", "bins": bins, "counts": tuple(counts),
            "n": n, "date_only_refused": dropped, "statistic": round(stat, 4),
            "p_value": round(p, 6), "df": bins - 1, "peak_hour": peak,
            "uniform_rejected": p < 0.05,
            "cramers_v": round(math.sqrt(stat / (n * (bins - 1))), 4)}


def lomb_scargle(times_days, values, *, span_days, min_period=2.0, max_period=None,
                 fap_threshold=FAP_THRESHOLD):
    """REQ-FIN-199. Only where the series has enough cycles, and only above the FAP.

    A periodogram always returns a peak. On a short irregular series the highest peak is noise,
    and it arrives looking exactly like a discovery: a period, a power, a plot. So the gate comes
    first and the peak is computed second.
    """
    max_period = max_period or span_days / MIN_CYCLES_FOR_PERIODOGRAM
    if max_period < min_period:
        return NoRhythm(
            "too_few_cycles",
            f"a {span_days:.0f}-day span holds fewer than {MIN_CYCLES_FOR_PERIODOGRAM} cycles of "
            f"any period above {min_period:.0f} days, so a false-alarm probability cannot be "
            f"computed and the highest peak would be noise wearing a period's clothes",
            len(values))
    n = len(values)
    if n < 2 * MIN_CYCLES_FOR_PERIODOGRAM:
        return NoRhythm("too_few_observations",
                        f"{n} observations is too few for a periodogram to have a usable null",
                        n)
    import numpy as np
    t = np.asarray(times_days, dtype=float)
    y = np.asarray(values, dtype=float)
    y = y - y.mean()
    periods = np.linspace(min_period, max_period, 512)
    freqs = 2 * np.pi / periods
    # `scipy.signal`, imported explicitly. An earlier version reached for `_sp.signal` where
    # `_sp` is `scipy.stats` -- which has no `.signal` -- so the `hasattr` guard silently fell
    # through to the hand-rolled fallback on every call. It gave plausible numbers, which is why
    # it survived: a wrong branch that returns nonsense announces itself, and one that returns
    # something reasonable does not.
    from scipy.signal import lombscargle as _ls
    power = _ls(t, y, freqs, normalize=True)
    i = int(np.argmax(power))
    peak_power, peak_period = float(power[i]), float(periods[i])
    # The standard false-alarm probability for a NORMALIZED Lomb-Scargle power p in [0,1]:
    # a single frequency exceeds p with probability (1-p)^((N-3)/2), and the highest of M
    # effectively independent frequencies exceeds it with 1 - (1 - that)^M.
    #
    # The first version used exp(-p(N-3)/2), which is the formula for a DIFFERENTLY normalized
    # periodogram. With N=400 that exponent is enormous for any p, so it returned a false-alarm
    # probability of exactly 0.000 for pure Gaussian noise -- the gate this function exists to
    # be was wide open, and it reported a 19.5-day "period" in random numbers.
    m_eff = max(1.0, span_days / min_period)
    single = (1.0 - peak_power) ** ((n - 3) / 2.0)
    fap = float(1.0 - (1.0 - single) ** m_eff)
    if fap > fap_threshold:
        # Not reported at a lower tier. NOT REPORTED.
        return NoRhythm("peak_does_not_clear_false_alarm_probability",
                        f"the strongest peak (period {peak_period:.1f} d) has a false-alarm "
                        f"probability of {fap:.3f}, above {fap_threshold}; a periodogram always "
                        f"returns a peak and this one is indistinguishable from noise", n)
    return {"method": "lomb_scargle", "peak_period_days": round(peak_period, 2),
            "power": round(peak_power, 4), "false_alarm_probability": round(fap, 5),
            "n": n, "span_days": span_days}


def analyse(days, times=None, *, values=None, span_days=None):
    """The default method first; the periodogram only if it is licensed."""
    out = {"day_of_week": day_of_week_rhythm(days)}
    if times is not None:
        out["hour_of_day"] = hour_of_day_rhythm(times)
    if values is not None and span_days:
        out["periodogram"] = lomb_scargle([(d - min(days)).days for d in days], values,
                                          span_days=span_days)
    return out
