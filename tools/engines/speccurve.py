#!/usr/bin/env python3
"""B9.1 — the specification curve and its circular-shift null (REQ-TIER-012; ADR-0050).

REQ-TIER-012 promotes only a hypothesis that "has a specification curve computed over at least 50
defensible specifications, and has a circular-shift null showing its significant-specification share
exceeds the null median". The grid is 3 transformations x 3 splits x 3 trims x 2 windows x 2 tests =
**108 specifications**, every one of them computed on post-registration days only.

A specification is "defensible" here in the narrow sense the requirement needs: each axis is a choice
a careful analyst could have made in advance and none of them is chosen after seeing the result — the
grid is fixed in this file, not selected per hypothesis (RULE-13: the model never picks the temporal
or analytic specification).

`share_sig` = the share of the 108 specifications with p < 0.05 AND the registered sign.
The null repeats the identical 108 on a circularly shifted outcome series (the scan's own `_shift`,
which is deterministic per name, so a null run is reproducible rather than random) and takes the
median share over NULL_REPS repetitions.

Deterministic. Statistics reused from the scan (RULE-11/12) except Welch's t, which scipy provides.
"""
import datetime as dt
import hashlib

from scipy import stats as _sp

from tools.engines.scan import _detrend, _dow_demedian, _mann_whitney_p, _median

CODE_VERSION = "speccurve-v1"
TRANSFORMATIONS = ("raw", "dow_demedian", "detrend_dow_demedian")
SPLITS = ("quartile", "tertile", "median")
TRIMS = ("none", "1pct", "5pct")
WINDOWS = ("all_post", "last_60")
TESTS = ("mann_whitney", "welch_t")
N_SPECS = len(TRANSFORMATIONS) * len(SPLITS) * len(TRIMS) * len(WINDOWS) * len(TESTS)   # 108
MIN_SPECS = 50            # REQ-TIER-012's floor
MIN_SIDE = 5              # a specification with fewer than this per side is not computable
NULL_REPS = 20
P_SIG = 0.05


def _transform(dv, kind):
    if kind == "raw":
        return dict(dv)
    if kind == "dow_demedian":
        return _dow_demedian(dv)
    return _dow_demedian(_detrend(dv))


def _pairs(drv, out, lag):
    off = dt.timedelta(days=lag)
    return [(d, x, out[d + off]) for d, x in sorted(drv.items()) if (d + off) in out]


def _windowed(pairs, window):
    if window == "all_post" or len(pairs) <= 60:
        return pairs
    return pairs[-60:]


def _trimmed(pairs, trim):
    if trim == "none" or not pairs:
        return pairs
    frac = 0.01 if trim == "1pct" else 0.05
    k = int(len(pairs) * frac)
    if k == 0:
        return pairs
    by_y = sorted(pairs, key=lambda t: t[2])
    keep = set(id(t) for t in by_y[k:len(by_y) - k])
    return [t for t in pairs if id(t) in keep]


def _split(pairs, how):
    xs = sorted(x for _, x, _ in pairs)
    if not xs:
        return [], []
    if how == "quartile":
        lo_c, hi_c = xs[len(xs) // 4], xs[(3 * len(xs)) // 4]
    elif how == "tertile":
        lo_c, hi_c = xs[len(xs) // 3], xs[(2 * len(xs)) // 3]
    else:
        m = _median(xs)
        lo_c = hi_c = m
    if lo_c == hi_c and how != "median":
        return [], []
    hi = [y for _, x, y in pairs if x >= hi_c]
    lo = [y for _, x, y in pairs if x <= lo_c] if how != "median" else [y for _, x, y in pairs if x < hi_c]
    return hi, lo


def _p(hi, lo, test):
    if test == "mann_whitney":
        return _mann_whitney_p(hi, lo)
    res = _sp.ttest_ind(hi, lo, equal_var=False)
    p = float(res.pvalue)
    return 1.0 if p != p else max(1e-12, p)          # NaN (zero variance) -> no evidence


def specs():
    """The fixed grid, in a fixed order, so spec_id is stable across runs."""
    i = 0
    for t in TRANSFORMATIONS:
        for s in SPLITS:
            for tr in TRIMS:
                for w in WINDOWS:
                    for te in TESTS:
                        yield i, t, s, tr, w, te
                        i += 1


def curve(drv_raw, out_raw, lag, direction):
    """Run the 108 specifications. Returns (rows, share_sig) where rows are dicts ready to store."""
    cache = {}
    rows, sig = [], 0
    for spec_id, t, s, tr, w, te in specs():
        if t not in cache:
            cache[t] = (_transform(drv_raw, t), _transform(out_raw, t))
        drv, out = cache[t]
        pairs = _trimmed(_windowed(_pairs(drv, out, lag), w), tr)
        hi, lo = _split(pairs, s)
        if len(hi) < MIN_SIDE or len(lo) < MIN_SIDE:
            rows.append(dict(spec_id=spec_id, transformation=t, split=s, trim=tr, window=w, test=te,
                             n=len(pairs), delta=None, p=None, same_sign=None))
            continue
        delta = _median(hi) - _median(lo)
        p = _p(hi, lo, te)
        same = (delta > 0) == (direction == "positive")
        if p < P_SIG and same:
            sig += 1
        rows.append(dict(spec_id=spec_id, transformation=t, split=s, trim=tr, window=w, test=te,
                         n=len(pairs), delta=delta, p=p, same_sign=same))
    return rows, round(sig / N_SPECS, 4)


MIN_SHIFT = 30            # REQ-TIER-012 / B9: "a random offset >= 30 days"


def circular_shift(dv, name, min_shift=MIN_SHIFT):
    """A genuine circular shift of at least `min_shift` days, deterministic per name.

    This does NOT reuse `scan._shift`, which B9 names, because that function computes its offset as
    60 + hash % 241 with no reference to the series length: on a series shorter than the offset,
    `vals[-k:] + vals[:-k]` is the identity and the "null" is the observed data. The scan runs on
    seven-year series where k <= 300 always shifts; a post-registration window is 30-180 days, where
    it silently does not. Measured before the fix: a synthetic pair with a real effect scored
    share_sig = 1.000 and null_median_share = 1.000. Fixed here rather than in the scan so scan
    behaviour is unchanged (ADR-0050). Returns None when the series is too short to shift."""
    days = sorted(dv)
    n = len(days)
    span = n - 2 * min_shift
    if span <= 0:
        return None
    k = min_shift + int(hashlib.sha256(name.encode()).hexdigest(), 16) % span
    vals = [dv[d] for d in days]
    return dict(zip(days, vals[-k:] + vals[:-k]))


def null_share(drv_raw, out_raw, lag, direction, key, reps=NULL_REPS):
    """The circular-shift null: the identical grid on a shifted outcome, `reps` times, median share.
    Returns None when the window is too short for a real shift — the caller must treat that as a
    failure to demonstrate the REQ-TIER-012 condition, never as a pass."""
    shares = []
    for r in range(reps):
        shifted = circular_shift(out_raw, f"{key}|specnull|rep{r}")
        if shifted is None:
            return None
        _, s = curve(drv_raw, shifted, lag, direction)
        shares.append(s)
    shares.sort()
    return shares[len(shares) // 2]


def store(cur, schema, hypothesis_id, look, rows):
    """One multi-row INSERT: 108 separate round trips to Supabase dominated the nightly job and the
    test suite (21 minutes for one test module before this)."""
    cur.execute(f"DELETE FROM {schema}.spec_curves WHERE hypothesis_id = %s AND look = %s",
                (hypothesis_id, look))
    if not rows:
        return
    params = []
    for r in rows:
        params += [hypothesis_id, look, r["spec_id"], r["transformation"], r["split"], r["trim"],
                   r["window"], r["test"], r["n"], r["delta"], r["p"], r["same_sign"], CODE_VERSION]
    cur.execute(f"""INSERT INTO {schema}.spec_curves
        (hypothesis_id, look, spec_id, transformation, split, trim, window_spec, test, n, delta, p,
         same_sign, code_version) VALUES """
        + ",".join(["(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"] * len(rows)), params)


def counter_frame_n(drv_raw, out_raw, lag):
    """REQ-TIER-028: outcome-negative days on which the exposure was absent — here, days in the
    outcome's bottom quartile whose paired exposure was in the exposure's bottom quartile."""
    pairs = _pairs(drv_raw, out_raw, lag)
    if len(pairs) < 8:
        return 0
    xs = sorted(x for _, x, _ in pairs)
    ys = sorted(y for _, _, y in pairs)
    x_lo, y_lo = xs[len(xs) // 4], ys[len(ys) // 4]
    return sum(1 for _, x, y in pairs if y <= y_lo and x <= x_lo)
