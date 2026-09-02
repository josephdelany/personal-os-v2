#!/usr/bin/env python3
"""E5 — next-day forecasts with adaptive conformal bands (ADR-0038; port of the
old conformal.py's Gibbs-Candès online-alpha design, stateless re-derivation).

Per headline metric: point = trailing-28d median; band half-width = the (1-a)
quantile of trailing-60d absolute residuals, with alpha walked forward over the
history (a += gamma*(target_miss - miss)) so coverage self-corrects — the walk
is recomputed deterministically from history each night (no hidden state).
Every forecast writes: analysis.forecasts row + a core.predictions row claiming
p=0.90 the value lands in-band (resolution makes the claim scoreable: Brier +
empirical coverage — the Trust tab's raw material). Resolution updates ONLY the
outcome fields of matured rows (REQ-INF-306's write; no re-forecasting)."""
import datetime as dt

CODE_VERSION = "forecast-v2"
METRICS = ("sleep_asleep_min", "hrv_sdnn", "rhr", "steps", "screen_active_hours")
TARGET = 0.90
GAMMA = 0.02


def _median(xs):
    s = sorted(xs); n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def _quantile(xs, q):
    s = sorted(xs)
    if not s:
        return None
    i = min(len(s) - 1, max(0, int(q * len(s))))
    return s[i]


def forecast_metric(days, vals, target_day):
    """Walk the conformal alpha over history; return (lo, point, hi) for target."""
    resid, alpha = [], 1 - TARGET
    fc = {}
    for i, d in enumerate(days):
        hist = vals[max(0, i - 28):i]
        if len(hist) >= 10:
            pt = _median(hist)
            w = _quantile([abs(r) for r in resid[-60:]], min(0.99, 1 - alpha)) if len(resid) >= 20 else None
            fc[d] = (pt, w)
            miss = 1.0 if (w is not None and abs(vals[i] - pt) > w) else 0.0
            if w is not None:
                alpha = min(0.5, max(0.005, alpha + GAMMA * ((1 - TARGET) - miss)))
            resid.append(vals[i] - pt)
        else:
            resid.append(0.0)
    hist = vals[-28:]
    if len(hist) < 10 or len(resid) < 20:
        return None
    pt = _median(hist)
    w = _quantile([abs(r) for r in resid[-60:]], min(0.99, 1 - alpha))
    return (pt - w, pt, pt + w)


def run(cur, target_day=None, write_predictions=True):
    target_day = target_day or (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=1))
    made = 0
    for metric in METRICS:
        cur.execute("""select day, value from analysis.panel
                        where metric=%s and day < %s order by day""", (metric, target_day))
        rows = cur.fetchall()
        if len(rows) < 40:
            continue
        days = [r[0] for r in rows]; vals = [float(r[1]) for r in rows]
        f = forecast_metric(days, vals, target_day)
        if not f:
            continue
        lo, pt, hi = (round(x, 2) for x in f)
        if metric in ("sleep_asleep_min", "hrv_sdnn", "rhr", "steps", "screen_active_hours"):
            lo = max(0.0, lo)    # N3: physical floor; also keeps coverage claims honest
        cur.execute("""insert into analysis.forecasts (day_target, metric, lo, point, hi, code_version)
                       values (%s,%s,%s,%s,%s,%s)
                       on conflict (day_target, metric) do update
                       set lo=excluded.lo, point=excluded.point, hi=excluded.hi,
                           code_version=excluded.code_version""",
                    (target_day, metric, lo, pt, hi, CODE_VERSION))
        if not write_predictions:
            made += 1
            continue
        # N4: claim_text built in SQL from the forecasts row itself — the resolver
        # reconstructs it with the identical SQL concat, so formatting can't drift
        cur.execute("""insert into core.predictions
                       (claim_text, resolution_rule, resolves_at, evidence_tier,
                        p_forecast, model_version)
                       select f.metric || ' on ' || f.day_target || ' within [' || f.lo || ', ' || f.hi || ']',
                              'panel value in stored band', %s, 'DESCRIPTIVE', %s, %s
                         from analysis.forecasts f
                        where f.day_target = %s and f.metric = %s
                          and not exists (select 1 from core.predictions p2
                                           where p2.claim_text = f.metric || ' on ' || f.day_target ||
                                                 ' within [' || f.lo || ', ' || f.hi || ']')""",
                    (dt.datetime.combine(target_day, dt.time(23, 59), dt.timezone.utc),
                     TARGET, CODE_VERSION, target_day, metric))
        made += 1
    return made


def resolve(cur):
    """Score matured forecasts against the panel (writes outcome fields only)."""
    cur.execute("""
        select p.prediction_id, f.metric, f.day_target, f.lo, f.hi, p.p_forecast,
               pan.value
          from core.predictions p
          join analysis.forecasts f
            on p.claim_text = f.metric || ' on ' || f.day_target ||
               ' within [' || f.lo || ', ' || f.hi || ']'
          left join analysis.panel pan on pan.metric = f.metric and pan.day = f.day_target
         where p.outcome_bool is null and p.resolves_at < clock_timestamp()""")
    n_res = n_unres = 0
    for pid, metric, day, lo, hi, p_fc, actual in cur.fetchall():
        if actual is None:
            n_unres += 1
            continue
        hit = float(lo) <= float(actual) <= float(hi)
        brier = (float(p_fc) - (1.0 if hit else 0.0)) ** 2
        cur.execute("""update core.predictions
                       set outcome_bool=%s, resolved_at=now(), brier=%s
                       where prediction_id=%s""", (hit, brier, pid))
        n_res += 1
    return n_res, n_unres
