#!/usr/bin/env python3
"""E2 baselines — port of the old system's proven math (04_scripts/baselines.py)
under the new constitution: per (metric, day) — EWMA-detrended (halflife 14d)
modified z-scores at two timescales (7d fast / 28d slow) using median/MAD
(robust: one outlier can't poison a baseline), trailing-90d p10/p90 personal
band, and run-length of consecutive out-of-band days. Deterministic, stamped.
(The PELT changepoint reset lands with E6; the EWMA detrend already absorbs
slow drift, which is the reset's main job — documented limit, not hidden.)
"""
import json
from collections import defaultdict

CODE_VERSION = "baselines-v1"
HALFLIFE = 14.0
ALPHA = 1 - 0.5 ** (1.0 / HALFLIFE)
K = 0.6745  # modified z constant


def _mad_z(window, x):
    if len(window) < 5:
        return None
    s = sorted(window)
    m = s[len(s) // 2]
    dev = sorted(abs(v - m) for v in window)
    mad = dev[len(dev) // 2]
    if mad < 1e-6:
        return 0.0
    z = K * (x - m) / mad
    # winsorize: zero-inflated streams (precip, binge_runs, topic fractions)
    # legitimately produce huge modified-z on any nonzero day; ±10 preserves
    # ranking while keeping the scale readable (documented, standard practice)
    return max(-10.0, min(10.0, z))


def compute(cur):
    """Rebuild analysis.baselines from analysis.panel. Returns rows written."""
    cur.execute("delete from analysis.baselines")
    cur.execute("""select metric, day, value from analysis.panel
                   order by metric, day""")
    series = defaultdict(list)
    for metric, day, value in cur.fetchall():
        series[metric].append((day, float(value)))
    n_rows = 0
    for metric, pts in series.items():
        if len(pts) < 30:                      # validity: degenerate (old gate)
            continue
        vals = [v for _, v in pts]
        uniq = set(vals)
        if len(uniq) < 10:
            continue                           # flag/near-constant stream: z is meaningless
        modal = max(vals.count(x) for x in uniq) / len(vals) if len(uniq) < 50 else 0
        if modal >= 0.9:
            continue                           # essentially constant stream
        ewma = None
        resid_hist, raw_hist = [], []
        rows = []
        for day, v in pts:
            ewma = v if ewma is None else (ALPHA * v + (1 - ALPHA) * ewma)
            resid = v - ewma
            zf = _mad_z(resid_hist[-7:], resid)
            zs = _mad_z(resid_hist[-28:], resid)
            band = sorted(raw_hist[-90:])
            lo = band[max(0, int(0.1 * len(band)) - 1)] if len(band) >= 10 else None
            hi = band[min(len(band) - 1, int(0.9 * len(band)))] if len(band) >= 10 else None
            out = 0
            if lo is not None and v < lo:
                out = -1
            elif hi is not None and v > hi:
                out = 1
            prev_run = rows[-1][7] if rows else 0
            run = (prev_run + out) if (out != 0 and (prev_run == 0 or (prev_run > 0) == (out > 0))) else out
            rows.append((day, metric, v, zf, zs, lo, hi, run))
            resid_hist.append(resid)
            raw_hist.append(v)
        buf = [(day, met, v, zf, zs, lo, hi, run, CODE_VERSION)
               for day, met, v, zf, zs, lo, hi, run in rows]
        for i in range(0, len(buf), 500):
            chunk = buf[i:i+500]
            ph = ",".join(["(%s,%s,%s,%s,%s,%s,%s,%s,%s)"] * len(chunk))
            cur.execute("insert into analysis.baselines (day, metric, value, z_fast,"
                        " z_slow, band_lo, band_hi, run_len, code_version) values " + ph,
                        [x for row in chunk for x in row])
        n_rows += len(buf)
    return n_rows


def log_run(cur, n):
    cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                   values ('baselines_build', now(), 'ok', %s, %s)""",
                (n, json.dumps({"code_version": CODE_VERSION})))
