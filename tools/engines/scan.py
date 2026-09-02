#!/usr/bin/env python3
"""E3 — the contrast scan (ADR-0038): seeded manifest + discovery sweep.

For each (driver, outcome, lag): within-person quartile contrast — outcome
distribution on the driver's top-quartile days vs bottom-quartile days, outcome
weekday-demedianed first (the day-of-week confound partialled), Mann-Whitney
normal-approximation p, lag-1-autocorr n_eff, BH-FDR across the whole run
family. Survivors (q<0.05, capped top-K per domain-pair) become CANDIDATE rows
in core.hypothesis_register (mined_from_preexisting=true) with full statistics
in analysis.contrasts. A circular-shift null twin (driver shifted 60-300 days,
deterministic per pair) runs the identical pipeline; observed-vs-null discovery
counts land in analysis.scan_calibration — the published false-positive check.

Tautology guards: same-source pairs excluded; passthrough duplicates of
canonical metrics excluded; the old system's derived composite streams
('engine.*', 'derived.*', 'events_inferred.*') excluded entirely — deriving a
"pattern" between a composite and its own inputs was the old system's fatal
flaw. Everything deterministic; no model, no dependency beyond stdlib.
"""
import hashlib
import json
import math
from collections import defaultdict

from tools.engines.panel import SIG_CANON, LEGACY_CANON

CODE_VERSION = "scan-v2"
MIN_SIDE = 30          # min days per quartile side (REQ posture: n>=30)
Q_CUT = 0.05
TOP_K = 3              # per (driver domain, outcome domain)
LAGS = (0, 1, 2, 7)

# passthrough names that duplicate canonicals -> excluded
DUP_PASSTHROUGH = {f"{s}.{m}" for s, m in SIG_CANON.values()} | \
                  {f"health_history.{c}" for c in LEGACY_CANON}
BLOCK_PREFIX = ("engine.", "derived.", "events_inferred.", "event_study.",
                "goal.", "checkin.")   # composites / too-sparse

# CONSTRUCT FAMILIES — a pair within one family is the same underlying
# measurement seen twice (the old system's tautology disease); never scanned.
FAMILY_RULES = [
    (("sleep_", "apple_sleep.", "nightly."), "sleep"),
    (("hrv_", "apple_hrv.", "rhr", "resp_night", "wrist_temp", "apple_vitals.",
      "health_history.hr", "health_history.rhr", "health_history.hrv"), "heart"),
    (("steps", "apple_gait.", "health_history.", "apple_watch.", "activity.",
      "exercise_", "active_kcal", "strength_", "apple_load.", "apple_trimp.",
      "apple_overnight.", "apple_circadian.", "mobility."), "movement"),
    (("screen_", "attention.", "information.", "yt_", "chrome_", "media."), "attention"),
    (("spend.", "meals_logged"), "spend"),
    (("weather.", "airnow."), "weather"),
    (("gmail.", "social."), "social"),
    (("github.",), "work"),
    (("mood", "checkin_"), "mind"),
]
def _family(m):
    for prefixes, fam in FAMILY_RULES:
        if any(m.startswith(p) or m == p.rstrip(".") for p in prefixes):
            return fam
    return "other:" + m.split(".")[0]

SEEDS = [  # (driver, outcome, lag) — the library's anchors, in panel vocabulary
    ("sleep_asleep_min", "hrv_sdnn", 0), ("sleep_asleep_min", "rhr", 0),
    ("sleep_rem_pct", "hrv_sdnn", 0), ("sleep_deep_pct", "hrv_sdnn", 0),
    ("hrv_sdnn", "rhr", 0), ("resp_night", "rhr", 0),
    ("screen_binge_min", "spend.bar_frac_30d", 7), ("yt_events", "spend.bar_frac_30d", 7),
    ("sleep_asleep_min", "spend.discretionary_frac_30d", 3),
    ("spend.monetary_7d", "sleep_asleep_min", 0),
    ("screen_binge_min", "sleep_asleep_min", 1), ("screen_binge_min", "sleep_onset_min", 1),
    ("yt_events", "sleep_asleep_min", 1), ("chrome_events", "sleep_onset_min", 1),
    ("steps", "sleep_asleep_min", 0), ("steps", "hrv_sdnn", 1),
    ("weather.temp_f", "sleep_asleep_min", 0),
    ("weather.daylight_hours", "sleep_midpoint", 0),
    ("sleep_asleep_min", "screen_active_hours", 1),
    ("screen_active_hours", "hrv_sdnn", 1),
]


def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


def _mann_whitney_p(a, b):
    """Two-sided Mann-Whitney via normal approximation with tie correction."""
    n1, n2 = len(a), len(b)
    allv = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks, i = {}, 0
    r = [0.0] * len(allv)
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[k] = avg
        i = j + 1
    r1 = sum(rk for rk, (_, g) in zip(r, allv) if g == 0)
    u = r1 - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    # tie-corrected variance
    n = n1 + n2
    counts = defaultdict(int)
    for v, _ in allv:
        counts[v] += 1
    tie = sum(c ** 3 - c for c in counts.values())
    var = n1 * n2 / 12.0 * ((n + 1) - tie / (n * (n - 1)))
    if var <= 0:
        return 1.0
    z = (u - mu) / math.sqrt(var)
    return max(1e-12, 2.0 * (1.0 - _phi(abs(z))))


def _lag1_rho(vals):
    if len(vals) < 3:
        return 0.0
    m = sum(vals) / len(vals)
    num = sum((vals[i] - m) * (vals[i - 1] - m) for i in range(1, len(vals)))
    den = sum((v - m) ** 2 for v in vals)
    return max(-0.99, min(0.99, num / den)) if den else 0.0


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def _load_panel(cur, schema="analysis"):
    """schema is 'analysis' in production; a disposable twin under test (RULE-01 exception)."""
    cur.execute(f"select metric, day, value from {schema}.panel")
    series = defaultdict(dict)
    for metric, day, value in cur.fetchall():
        series[metric][day] = float(value)
    return series


def _eligible(series):
    out = {}
    for m, dv in series.items():
        if m in DUP_PASSTHROUGH or any(m.startswith(p) for p in BLOCK_PREFIX):
            continue
        if len(dv) < 4 * MIN_SIDE:                 # needs quartile sides of 30
            continue
        if len(set(dv.values())) < 10:             # flag-like
            continue
        out[m] = dv
    return out


def _domain(m):
    return m.split(".")[0].split("_")[0]


def _detrend(dv):
    """Deseasonalize + detrend (REQ-INF-409): subtract the calendar-month median
    (annual cycle, computed across years) then EWMA(14d) residualize (local
    trend). The contrast then asks 'unusually high for the season AND the
    period' — and the circular-shift null loses the annual alignment that was
    faking discoveries."""
    bymonth = defaultdict(list)
    for d, v in dv.items():
        bymonth[d.month].append(v)
    mmed = {m: _median(v) for m, v in bymonth.items()}
    alpha = 1 - 0.5 ** (1.0 / 14.0)
    out, ewma = {}, None
    for d in sorted(dv):
        v = dv[d] - mmed[d.month]
        ewma = v if ewma is None else (alpha * v + (1 - alpha) * ewma)
        out[d] = v - ewma
    return out


def _dow_demedian(dv):
    bydow = defaultdict(list)
    for d, v in dv.items():
        bydow[d.weekday()].append(v)
    med = {k: _median(v) for k, v in bydow.items()}
    return {d: v - med[d.weekday()] for d, v in dv.items()}


def _contrast(drv, out, lag, min_side=None):
    """Returns (n_hi, n_lo, med_hi, med_lo, delta, p, rho) or None.
    min_side defaults to MIN_SIDE (the 7-year sweep floor); the watch resolver
    (tools/engines/resolve.py, ADR-0048) passes its own floor for a 30-day
    post-registration window. Additive: scan behaviour is unchanged."""
    if min_side is None:
        min_side = MIN_SIDE
    pairs = []
    from datetime import timedelta
    off = timedelta(days=lag)
    for d, x in drv.items():
        y = out.get(d + off)
        if y is not None:
            pairs.append((d, x, y))
    if len(pairs) < 4 * min_side:
        return None
    xs = sorted(p[1] for p in pairs)
    q1, q3 = xs[len(xs) // 4], xs[(3 * len(xs)) // 4]
    if q1 == q3:
        return None
    hi = [y for _, x, y in pairs if x >= q3]
    lo = [y for _, x, y in pairs if x <= q1]
    if len(hi) < min_side or len(lo) < min_side:
        return None
    p = _mann_whitney_p(hi, lo)
    ys = [y for _, _, y in sorted(pairs)]
    return (len(hi), len(lo), _median(hi), _median(lo),
            _median(hi) - _median(lo), p, _lag1_rho(ys))


def _bh(ps):
    """Benjamini-Hochberg step-up q-values. One owner (RULE-11/12): the scan's
    tree FDR and the watch resolver (ADR-0048) both call this function."""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    q = [1.0] * m
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, ps[i] * m / rank)
        q[i] = prev
    return q


def _shift(dv, name):
    """Deterministic circular shift 60-300 days for the null twin."""
    days = sorted(dv)
    k = 60 + int(hashlib.sha256(name.encode()).hexdigest(), 16) % 241
    vals = [dv[d] for d in days]
    shifted = vals[-k:] + vals[:-k]
    return dict(zip(days, shifted))


def run(cur, run_date, stride=1):
    raw = _eligible(_load_panel(cur))
    series = {m: _dow_demedian(_detrend(dv)) for m, dv in raw.items()}
    demed = series   # both sides detrended + weekday-demedianed
    tests = []
    seen = set()
    for d, o, lag in SEEDS:
        if d in series and o in series:
            tests.append((d, o, lag, True))
            seen.add((d, o, lag))
    metrics = sorted(series)
    for d in metrics:
        for o in metrics:
            if d == o or _family(d) == _family(o):
                continue
            if _family(o) == "weather":
                continue    # REQ-INF-005: weather is cause-only; behavior cannot move it
            for lag in LAGS:
                if (d, o, lag) not in seen:
                    tests.append((d, o, lag, False))
    if stride > 1:      # probe mode: deterministic subsample of the discovery sweep
        tests = [t for i, t in enumerate(tests) if t[3] or i % stride == 0]
    results = []
    for d, o, lag, seeded in tests:
        r = _contrast(series[d], demed[o], lag)
        if r:
            results.append((d, o, lag, seeded) + r)
    NULL_REPS = 5
    null_runs = []
    for rep in range(NULL_REPS):
        rep_res = []
        for d, o, lag, seeded in tests:
            rn = _contrast(_shift(series[d], f"{d}|{o}|{lag}|rep{rep}"), demed[o], lag)
            if rn:
                rep_res.append((d, o, lag, seeded) + rn)
        null_runs.append(rep_res)

    bh = _bh   # module-level since ADR-0048 so the watch resolver imports it; identical code

    # M1 (RULE-21 / REQ-INF-001/002): hierarchical FDR — level 1 selects
    # domain-pair FAMILIES (Simes p per family, BH across families); level 2
    # applies BH within each selected family. Family id + size persist per row.
    def tree_fdr(res):
        fams = defaultdict(list)
        for i, r in enumerate(res):
            fams[(_family(r[0]), _family(r[1]))].append(i)
        simes = {}
        for f, idxs in fams.items():
            ps = sorted(res[i][9] for i in idxs)
            simes[f] = min(p * len(ps) / (k + 1) for k, p in enumerate(ps))
        fkeys = sorted(fams)
        fq = bh([simes[f] for f in fkeys])
        selected = {f for f, q in zip(fkeys, fq) if q < Q_CUT}
        qs = [1.0] * len(res)
        for f in selected:
            idxs = fams[f]
            sub_q = bh([res[i][9] for i in idxs])
            for i, q in zip(idxs, sub_q):
                qs[i] = q
        fam_of = {i: (_family(res[i][0]), _family(res[i][1])) for i in range(len(res))}
        fam_m = {f: len(v) for f, v in fams.items()}
        return qs, fam_of, fam_m
    qs, fam_of, fam_m = tree_fdr(results)
    null_ps_counts = []
    for rep_res in null_runs:
        if rep_res:
            rq, _, _ = tree_fdr(rep_res)
            null_ps_counts.append(sum(1 for q in rq if q < Q_CUT))
        else:
            null_ps_counts.append(0)
    observed_sig = sum(1 for q in qs if q < Q_CUT)
    # M6: replicate null runs -> a null DISTRIBUTION of discovery counts
    null_counts = sorted(null_ps_counts)
    null_sig = null_counts[len(null_counts) // 2] if null_counts else 0
    null_p95 = null_counts[min(len(null_counts) - 1, int(0.95 * len(null_counts)))] if null_counts else 0

    mad = {}
    for m, dv in series.items():
        vals = sorted(dv.values()); md = vals[len(vals)//2]
        dev = sorted(abs(v-md) for v in vals); mad[m] = dev[len(dev)//2] or 1e-9
    ranked = sorted(zip(results, qs), key=lambda t: t[1])
    kept, percell = [], defaultdict(int)
    seen_unordered = set()   # N2: one bidirectional lag-0 association is ONE pattern
    for (d, o, lag, seeded, n_hi, n_lo, mh, ml, delta, p, rho), q in ranked:
        if q >= Q_CUT:
            break
        if abs(delta) < 0.3 * mad.get(o, 0):
            continue    # statistically clean but practically trivial
        if lag == 0:
            key0 = tuple(sorted((d, o)))
            if key0 in seen_unordered:
                continue     # reverse direction of an already-kept lag-0 pair
            seen_unordered.add(key0)
        cell = (_family(d), _family(o))
        if percell[cell] >= TOP_K and not seeded:
            continue
        percell[cell] += 1
        kept.append((d, o, lag, seeded, n_hi, n_lo, mh, ml, delta, p, q, rho))

    cur.execute("delete from analysis.contrasts where run_date = %s", (run_date,))
    n_cand = 0
    for d, o, lag, seeded, n_hi, n_lo, mh, ml, delta, p, q, rho in kept:
        cid = f"{d}|{o}|L{lag}|{run_date}"
        hyp = f"scan:{d}|{o}|L{lag}"
        rho_d = max(0.0, rho)   # M2: Kish deflates only; negative rho never inflates n_eff
        n_eff = lambda n: round(n * (1 - rho_d) / (1 + rho_d), 1)
        fam = (_family(d), _family(o))
        cur.execute("""insert into analysis.contrasts
            (contrast_id, run_date, driver, outcome, lag_days, seeded, n_hi, n_lo,
             med_hi, med_lo, delta, p_raw, q_fdr, n_eff_hi, n_eff_lo, rho_outcome,
             hypothesis_id, code_version, family_id, family_m)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (cid, run_date, d, o, lag, seeded, n_hi, n_lo, mh, ml, delta, p, q,
             n_eff(n_hi), n_eff(n_lo), round(rho, 3), hyp, CODE_VERSION,
             fam[0] + "->" + fam[1], fam_m.get(fam, 0)))
        cur.execute("""insert into core.hypothesis_register
            (hypothesis_id, exposure_metric, outcome_metric, lag_days, direction,
             transformation, adjustment_set, test_statistic, preregistered_at,
             confirmation_data_from, resolution_rule, status, mined_from_preexisting)
            values (%s,%s,%s,%s,%s,%s,%s,%s, now(), now(), %s, 'CANDIDATE', true)
            on conflict (hypothesis_id) do nothing""",
            (hyp, d, o, lag, "positive" if delta > 0 else "negative",
             "dow_demedian", json.dumps(["day_of_week"]),
             "quartile_contrast_mannwhitney",
             "median delta same sign with q<0.10 on >=30 post-registration days"))
        n_cand += 1
    cur.execute("""insert into analysis.scan_calibration
        (run_date, n_pairs_tested, observed_sig, null_sig, null_p95, null_reps, code_version)
        values (%s,%s,%s,%s,%s,%s,%s)
        on conflict (run_date) do update
        set n_pairs_tested=excluded.n_pairs_tested, observed_sig=excluded.observed_sig,
            null_sig=excluded.null_sig, null_p95=excluded.null_p95,
            null_reps=excluded.null_reps, code_version=excluded.code_version""",
        (run_date, len(results), observed_sig, null_sig, null_p95, NULL_REPS, CODE_VERSION))
    return {"tested": len(results), "observed_sig": observed_sig,
            "null_median": null_sig, "null_p95": null_p95, "kept": n_cand}
