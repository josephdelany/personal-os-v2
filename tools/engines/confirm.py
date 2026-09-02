#!/usr/bin/env python3
"""B9.2 — the confirmation gate: PROMOTED -> CONFIRMED_OBSERVATIONAL (REQ-TIER-013; ADR-0051).

REQ-TIER-013, in full: "WHEN a PROMOTED hypothesis is estimated on post-registration data only, with a
minimal sufficient adjustment set computed from the DAG, Newey-West HAC standard errors, a computed
E-value at both the point estimate and the interval limit nearest the null, all negative-control checks
passed, and all DoWhy refutation tests passed, the reasoning layer SHALL assign tier
CONFIRMED_OBSERVATIONAL." REQ-TIER-014: any negative-control or refutation failure -> REFUTED plus a
DESCRIPTIVE statement naming the hypothesis and the failed check.

Each clause, and where it lives here:
  * post-registration data only          `_paired`, which never reads a day <= confirmation_data_from
  * minimal sufficient adjustment set    `minimal_backdoor` over `config.dag_edges` (networkx d-separation
                                         on the graph with the exposure's outgoing edges removed — the
                                         backdoor criterion), plus the two exogenous clocks, always forced in
  * Newey-West HAC                       statsmodels OLS, cov_type='HAC', maxlags = floor(4*(n/100)^(2/9))
  * E-value at point AND limit           `e_values`, on the standardized effect via Chinn's approximation
  * negative controls                    an outcome with no directed path from the exposure, and the
                                         exposure shifted FORWARD (future exposure predicting past outcome)
  * refutation tests                     placebo treatment, random common cause, data subset — implemented
                                         here, deterministically, NOT via DoWhy: see ADR-0051 "Deviation".

Deterministic: every resampling refuter is seeded from the hypothesis id, so a rerun reproduces the run.
"""
import datetime as dt
import hashlib
import json
import math
import random

import networkx as nx
import numpy as np
import statsmodels.api as sm

from tools.engines.scan import _load_panel, _median
from tools.engines import speccurve

CODE_VERSION = "confirm-v1"
MIN_POST_PROMO_DAYS = 60      # B9: a PROMOTED row is testable after 60 paired post-promotion days
COVERAGE_MIN = 0.60           # REQ-TIER-017 / REQ-TIER-045
NC_PASS_P = 0.20              # a negative control passes when its p is at least this
REFUTER_PLACEBO_P = 0.20
SUBSET_BLOCKS = 5             # leave-one-contiguous-block-out refits (ADR-0051)
SUBSET_INSIDE_MIN = 0.80      # share of those refits that must land inside the full-sample HAC interval
RECHECK_DAYS = 30             # REQ-TIER-041/042: monthly re-confirmation
EXOGENOUS = ("day_of_week", "season")


# ------------------------------------------------------------------ the registered DAG

def load_dag(cur):
    """Build the DAG from config.dag_edges. '*' destinations are the exogenous clocks: they are parents
    of everything and are ALWAYS in the adjustment set, so they are held out of the graph search and
    forced into the regression instead — equivalent, and it keeps the search over panel metrics."""
    cur.execute("SELECT src, dst, basis FROM config.dag_edges")
    g = nx.DiGraph()
    exogenous = set()
    for src, dst, _basis in cur.fetchall():
        if dst == "*":
            exogenous.add(src)
            continue
        g.add_edge(src, dst)
    return g, exogenous


def minimal_backdoor(g, x, y):
    """The minimal sufficient adjustment set by the backdoor criterion, or None if the effect is not
    identified. Returns [] when no confounding path exists and both nodes are registered."""
    if x not in g or y not in g:
        return None          # the DAG does not know this pair: we cannot claim a set "computed from the DAG"
    if not nx.has_path(g, x, y):
        return None          # no directed path: there is no effect to identify
    back = g.copy()
    back.remove_edges_from(list(g.out_edges(x)))
    desc_x = nx.descendants(g, x) | {x}
    candidates = sorted((nx.ancestors(g, x) | nx.ancestors(g, y)) - desc_x - {y})
    from itertools import combinations
    for r in range(0, len(candidates) + 1):
        for z in combinations(candidates, r):
            zs = set(z)
            if zs & desc_x:
                continue                      # a descendant of the exposure may never be adjusted for
            if nx.is_d_separator(back, {x}, {y}, zs):
                return list(z)
    return None


def negative_control_outcome(g, x, y, panel, since, until, exclude=()):
    """REQ-TIER-014(a): a metric with NO directed path from the exposure, with the highest coverage in
    the window. Returns the metric name or None.

    `exclude` holds the adjustment set. A variable we condition on cannot also be the negative-control
    outcome: regressing it on itself is degenerate and yields p ~ 0, which would refute every hypothesis
    whose adjustment set happens to have the highest coverage. (Found by the B9 tests, which refuted a
    clean synthetic effect for exactly that reason.)"""
    span = max(1, (until - since).days)
    best, best_cov = None, 0.0
    reachable = nx.descendants(g, x) | {x} if x in g else {x}
    for m, dv in panel.items():
        if m == y or m in reachable or m in exclude or m.startswith(("engine.", "derived.", "events_inferred.")):
            continue
        n = sum(1 for d in dv if since < d <= until)
        cov = n / span
        if cov > best_cov:
            best, best_cov = m, cov
    return best if best_cov >= COVERAGE_MIN else None


# ------------------------------------------------------------------ the design and the estimate

def _season(d):
    frac = (d.timetuple().tm_yday - 1) / 365.25
    return math.sin(2 * math.pi * frac), math.cos(2 * math.pi * frac)


def _paired(panel, xm, ym, lag, adj, since, until, x_shift=0, replace_x=None):
    """Rows of (outcome_day, y, x, *adj, dow one-hot, season sin/cos), post-registration only.

    The outcome is read at day d+lag and the exposure at day d+x_shift, so the normal estimate uses
    x_shift=0 and the future-exposure negative control uses x_shift=lag+7 (an exposure AFTER its
    outcome). `replace_x` substitutes a prepared exposure series (the placebo refuter)."""
    xs = replace_x if replace_x is not None else panel.get(xm, {})
    ys = panel.get(ym, {})
    rows, days = [], []
    for d in sorted(xs):
        od = d + dt.timedelta(days=lag)
        xd = d + dt.timedelta(days=x_shift)
        if not (since < od <= until) or not (since < xd <= until):
            continue
        if od not in ys or xd not in xs:
            continue
        cov = []
        ok = True
        for m in adj:
            v = panel.get(m, {}).get(od)
            if v is None:
                ok = False
                break
            cov.append(v)
        if not ok:
            continue
        s1, s2 = _season(od)
        dow = [1.0 if od.weekday() == k else 0.0 for k in range(6)]      # 6 dummies, Sunday is the base
        rows.append([ys[od], xs[xd]] + cov + dow + [s1, s2])
        days.append(od)
    return np.array(rows, dtype=float), days


def hac_maxlags(n):
    """The standard Newey-West rule: floor(4*(n/100)^(2/9))."""
    return max(1, int(math.floor(4 * (n / 100.0) ** (2.0 / 9.0))))


def hac_ols(arr):
    """OLS with Newey-West HAC errors. arr column 0 is the outcome, column 1 the exposure."""
    y = arr[:, 0]
    x = sm.add_constant(arr[:, 1:], has_constant="add")
    n = len(y)
    L = hac_maxlags(n)
    res = sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": L, "use_correction": True})
    beta = float(res.params[1])
    se = float(res.bse[1])
    p = float(res.pvalues[1])
    ci = res.conf_int(alpha=0.05)
    return {"beta": beta, "se": se, "p": p, "ci_lo": float(ci[1][0]), "ci_hi": float(ci[1][1]),
            "n": n, "maxlags": L, "sd_x": float(np.std(arr[:, 1], ddof=1)),
            "sd_y": float(np.std(y, ddof=1))}


def e_values(beta, ci_lo, ci_hi, sd_x, sd_y):
    """E-value at the point estimate and at the interval limit nearest the null (REQ-TIER-013).

    The effect is standardized as d = beta * sd(exposure) / sd(outcome) — the outcome shift, in outcome
    SDs, for a one-SD change in exposure — then converted to an approximate risk ratio by Chinn (2000),
    RR = exp(0.91*d). That conversion is an APPROXIMATION and every payload says so. E = RR + sqrt(RR*(RR-1)),
    computed on RR or 1/RR, whichever is >= 1. An interval containing the null has E_limit = 1 by definition."""
    def _e(b):
        if sd_y == 0:
            return 1.0
        d = b * sd_x / sd_y
        rr = math.exp(0.91 * d)
        if rr < 1:
            rr = 1.0 / rr
        return rr + math.sqrt(rr * (rr - 1))
    point = _e(beta)
    if ci_lo <= 0 <= ci_hi:
        limit = 1.0
    else:
        limit = _e(ci_lo if abs(ci_lo) < abs(ci_hi) else ci_hi)
    return round(point, 4), round(limit, 4)


# ------------------------------------------------------------------ refutation tests (ADR-0051 deviation)

def _seed(hyp, tag):
    return int(hashlib.sha256(f"{hyp}|{tag}".encode()).hexdigest()[:12], 16)


def refuters(arr, hyp, fit):
    """The three refutation tests REQ-TIER-013 names, implemented here rather than through DoWhy
    (ADR-0051 "Deviation" — DoWhy does not install on the interpreter Joe can run).

      placebo_treatment  — replace the exposure column with a seeded permutation of itself; the effect
                           must vanish (p >= 0.20).
      random_common_cause— add a seeded standard-normal covariate; the exposure's beta must stay inside
                           the original HAC 95% interval.
      data_subset        — leave-one-block-out: the window is cut into SUBSET_BLOCKS contiguous blocks
                           and refit with each block held out; at least SUBSET_INSIDE_MIN of those
                           estimates must land inside the full-sample HAC interval.
                           **Deliberately not DoWhy's random subsets** (ADR-0051): a random 80% subset is
                           nested in the full sample, so its estimate is correlated with the full estimate
                           at about 0.9 and lands inside a 1.96-SE interval essentially always. Measured
                           before the change: a clean effect, an estimate carried by four leverage points,
                           and pure noise all scored share-inside 1.00 — the check could not fail, and a
                           check that cannot fail is not protection. Contiguous blocks are the right
                           resampling unit for a time series (the same reason the errors are HAC) and they
                           detect the failure that matters here: an effect present in only part of the
                           window.
    """
    out = {}
    rng = random.Random(_seed(hyp, "placebo"))
    a = arr.copy()
    col = list(a[:, 1])
    rng.shuffle(col)
    a[:, 1] = col
    out["placebo_p"] = round(hac_ols(a)["p"], 4)
    out["placebo_ok"] = out["placebo_p"] >= REFUTER_PLACEBO_P

    rng = np.random.default_rng(_seed(hyp, "common_cause"))
    a = np.column_stack([arr, rng.standard_normal(len(arr))])
    b = hac_ols(a)["beta"]
    out["random_common_cause_beta"] = round(b, 6)
    out["random_common_cause_ok"] = fit["ci_lo"] <= b <= fit["ci_hi"]

    n = len(arr)
    edges = [round(n * i / SUBSET_BLOCKS) for i in range(SUBSET_BLOCKS + 1)]
    betas = []
    for b in range(SUBSET_BLOCKS):
        keep = np.r_[0:edges[b], edges[b + 1]:n]
        if len(keep) < 20:
            continue
        try:
            betas.append(hac_ols(arr[keep])["beta"])
        except Exception:
            continue
    inside = [b for b in betas if fit["ci_lo"] <= b <= fit["ci_hi"]]
    out["subset_block_betas"] = [round(b, 6) for b in betas]
    out["subset_share_inside"] = round(len(inside) / len(betas), 3) if betas else None
    out["subset_ok"] = bool(betas) and len(inside) / len(betas) >= SUBSET_INSIDE_MIN
    out["all_passed"] = bool(out["placebo_ok"] and out["random_common_cause_ok"] and out["subset_ok"])
    return out


# ------------------------------------------------------------------ the gate

def checks(fit, direction, ref, nc_p, nc_fut_p):
    """The REQ-TIER-013 conjunction, in one place so the gate and its null-rate proof share it
    (RULE-11/12). Returns a dict of the individual verdicts and `confirm`."""
    same_sign = (fit["beta"] > 0) == (direction == "positive")
    excludes_null = (fit["ci_lo"] > 0) or (fit["ci_hi"] < 0)
    nc_ok = not ((nc_p is not None and nc_p < NC_PASS_P) or (nc_fut_p is not None and nc_fut_p < NC_PASS_P))
    return {"same_sign": same_sign, "excludes_null": excludes_null, "negative_controls_ok": nc_ok,
            "refuters_ok": bool(ref["all_passed"]),
            "confirm": bool(same_sign and excludes_null and nc_ok and ref["all_passed"])}


def _note(cur, schema, kind, hyp, text):
    cur.execute(f"INSERT INTO {schema}.brief_notes (kind, hypothesis_id, text, tier) VALUES (%s,%s,%s,'DESCRIPTIVE')",
                (kind, hyp, text))


def _ledger(cur, core, h, status_to, reason, run_id, **kw):
    if status_to != h["status"]:
        cur.execute(f"UPDATE {core}.hypothesis_register SET status = %s WHERE hypothesis_id = %s",
                    (status_to, h["hypothesis_id"]))
    cols = dict(hypothesis_id=h["hypothesis_id"], status_from=h["status"], status_to=status_to,
                reason=reason, registered_direction=h["direction"], code_version=CODE_VERSION,
                post_days=kw.pop("post_days", 0), run_id=run_id,
                insufficiency_reason=kw.pop("insufficiency_reason", None))
    cols.update(kw)
    keys = list(cols)
    cur.execute(f"INSERT INTO {core}.hypothesis_resolutions ({', '.join(keys)}) "
                f"VALUES ({', '.join(['%s'] * len(keys))})", [cols[k] for k in keys])
    h["status"] = status_to


def score_predictions(cur, core, panel, today):
    """RULE-20 / OQ-44(a): score a promoted hypothesis's forward prediction once its window has run.
    outcome_bool = same sign as registered with p < 0.10 on the post-promotion window; brier = (p - o)^2."""
    cur.execute(f"""SELECT p.prediction_id, p.hypothesis_id, p.p_forecast, h.exposure_metric, h.outcome_metric,
                          h.lag_days, h.direction,
                          (SELECT r.look_day FROM {core}.hypothesis_resolutions r
                            WHERE r.hypothesis_id = h.hypothesis_id AND r.status_to = 'PROMOTED'
                            ORDER BY r.resolved_at DESC LIMIT 1)
                     FROM {core}.predictions p
                     JOIN {core}.hypothesis_register h ON h.hypothesis_id = p.hypothesis_id
                    WHERE p.outcome_bool IS NULL AND p.model_version LIKE 'resolve-%%'
                      AND p.resolves_at <= now()""")
    scored = 0
    for pid, hyp, pf, xm, ym, lag, direction, promoted_on in cur.fetchall():
        if promoted_on is None:
            continue
        arr, _ = _paired(panel, xm, ym, lag, [], promoted_on, today)
        if len(arr) < 20:
            continue
        hi_lo = speccurve._split([(None, r[1], r[0]) for r in arr], "quartile")
        hi, lo = hi_lo
        if len(hi) < 5 or len(lo) < 5:
            continue
        delta = _median(hi) - _median(lo)
        p = speccurve._p(hi, lo, "mann_whitney")
        ok = ((delta > 0) == (direction == "positive")) and p < 0.10
        brier = round((float(pf) - (1.0 if ok else 0.0)) ** 2, 6)
        cur.execute(f"""UPDATE {core}.predictions SET outcome_bool = %s, brier = %s, resolved_at = clock_timestamp()
                         WHERE prediction_id = %s""", (ok, brier, pid))
        scored += 1
    return scored


def run(cur, today=None, *, core="core", panel_schema="analysis", run_id=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    panel = _load_panel(cur, schema=panel_schema)
    g, _exogenous = load_dag(cur)
    stats = {"considered": 0, "confirmed": 0, "refuted": 0, "insufficient": 0, "rechecked": 0,
             "demoted": 0, "scored": 0, "not_ready": 0}
    cur.execute(f"""SELECT h.hypothesis_id, h.exposure_metric, h.outcome_metric, h.lag_days, h.direction,
                          h.confirmation_data_from, h.status, h.rule_version,
                          (SELECT r.look_day FROM {core}.hypothesis_resolutions r
                            WHERE r.hypothesis_id = h.hypothesis_id AND r.status_to = 'PROMOTED'
                            ORDER BY r.resolved_at DESC LIMIT 1) AS promoted_on,
                          (SELECT r.next_recheck FROM {core}.hypothesis_resolutions r
                            WHERE r.hypothesis_id = h.hypothesis_id AND r.status_to = 'CONFIRMED_OBSERVATIONAL'
                            ORDER BY r.resolved_at DESC LIMIT 1) AS next_recheck
                     FROM {core}.hypothesis_register h
                    WHERE h.status IN ('PROMOTED','CONFIRMED_OBSERVATIONAL')
                    ORDER BY h.preregistered_at""")
    cols = ("hypothesis_id", "exposure_metric", "outcome_metric", "lag_days", "direction",
            "confirmation_data_from", "status", "rule_version", "promoted_on", "next_recheck")
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for h in rows:
        hyp = h["hypothesis_id"]
        is_recheck = h["status"] == "CONFIRMED_OBSERVATIONAL"
        if is_recheck and (h["next_recheck"] is None or h["next_recheck"] > today):
            continue
        since = h["promoted_on"] or h["confirmation_data_from"].date()
        stats["considered"] += 1
        span = max(1, (today - since).days)

        # 1. adjustment set
        adj = minimal_backdoor(g, h["exposure_metric"], h["outcome_metric"])
        if adj is None:
            _ledger(cur, core, h, "INSUFFICIENT" if not is_recheck else "PROMOTED",
                    "insufficient_no_adjustment_set" if not is_recheck else "demoted_recheck_failed",
                    run_id, insufficiency_reason="no_adjustment_set", post_days=0, look_day=today)
            _note(cur, panel_schema, "demotion" if is_recheck else "refutation", hyp,
                  f"{hyp}: no minimal sufficient adjustment set is identifiable from the registered DAG for "
                  f"{h['exposure_metric']} -> {h['outcome_metric']}; not confirmed.")
            stats["demoted" if is_recheck else "insufficient"] += 1
            continue

        arr, days = _paired(panel, h["exposure_metric"], h["outcome_metric"], h["lag_days"], adj, since, today)
        coverage = round(len(arr) / span, 3)
        if len(arr) < MIN_POST_PROMO_DAYS or coverage < COVERAGE_MIN:
            stats["not_ready"] += 1
            continue

        # 2. HAC estimate
        fit = hac_ols(arr)
        prob_dir = round(1.0 - fit["p"] / 2.0 if (fit["beta"] > 0) == (h["direction"] == "positive")
                         else fit["p"] / 2.0, 4)

        # 3. E-values
        ev_point, ev_limit = e_values(fit["beta"], fit["ci_lo"], fit["ci_hi"], fit["sd_x"], fit["sd_y"])

        # 4. negative controls
        nc_metric = negative_control_outcome(g, h["exposure_metric"], h["outcome_metric"], panel, since, today,
                                             exclude=set(adj))
        nc_p = None
        if nc_metric:
            nc_arr, _ = _paired(panel, h["exposure_metric"], nc_metric, h["lag_days"], adj, since, today)
            if len(nc_arr) >= 20:
                nc_p = round(hac_ols(nc_arr)["p"], 4)
        fut_arr, _ = _paired(panel, h["exposure_metric"], h["outcome_metric"], h["lag_days"], adj, since, today,
                             x_shift=h["lag_days"] + 7)
        nc_fut_p = round(hac_ols(fut_arr)["p"], 4) if len(fut_arr) >= 20 else None
        nc_fail = (nc_p is not None and nc_p < NC_PASS_P) or (nc_fut_p is not None and nc_fut_p < NC_PASS_P)

        # 5. refutation tests, then the single REQ-TIER-013 conjunction
        ref = refuters(arr, hyp, fit)
        verdict = checks(fit, h["direction"], ref, nc_p, nc_fut_p)
        nc_fail = not verdict["negative_controls_ok"]

        common = dict(post_days=len(arr), coverage=coverage, look_day=today, adjustment_set=json.dumps(adj),
                      beta=fit["beta"], outcome_unit=h["outcome_metric"], ci_lo=fit["ci_lo"], ci_hi=fit["ci_hi"],
                      hac_maxlags=fit["maxlags"], prob_direction=prob_dir, p_raw=fit["p"],
                      e_value_point=ev_point, e_value_limit=ev_limit, nc_outcome_metric=nc_metric,
                      nc_outcome_p=nc_p, nc_exposure_p=nc_fut_p, refuter_results=json.dumps(ref),
                      counter_frame_n=speccurve.counter_frame_n(panel.get(h["exposure_metric"], {}),
                                                                panel.get(h["outcome_metric"], {}), h["lag_days"]),
                      observed_direction="positive" if fit["beta"] > 0 else "negative")

        # 6. decision
        if not verdict["negative_controls_ok"] or not verdict["refuters_ok"]:
            failed = ("negative control: " + ("outcome" if (nc_p is not None and nc_p < NC_PASS_P) else "future exposure")
                      ) if nc_fail else ("refutation test: " + ", ".join(k for k in ("placebo_ok", "random_common_cause_ok", "subset_ok") if not ref[k]))
            reason = "refuted_negative_control_failed" if nc_fail else "refuted_refutation_test_failed"
            _ledger(cur, core, h, "REFUTED", reason, run_id, **common)
            _note(cur, panel_schema, "refutation", hyp,
                  f"{hyp} ({h['exposure_metric']} -> {h['outcome_metric']}, lag {h['lag_days']}d) failed its {failed}; "
                  f"it is refuted and no longer claimed.")
            stats["refuted"] += 1
            continue
        if not verdict["confirm"]:
            if is_recheck:
                _ledger(cur, core, h, "PROMOTED", "demoted_recheck_failed", run_id,
                        insufficiency_reason=None, **common)
                _note(cur, panel_schema, "demotion", hyp,
                      f"{hyp} no longer holds on its rolling window (the effect's interval now includes no effect); "
                      f"demoted from CONFIRMED_OBSERVATIONAL to PROMOTED.")
                stats["demoted"] += 1
            else:
                _ledger(cur, core, h, "INSUFFICIENT", "insufficient_sign_unstable", run_id,
                        insufficiency_reason="sign_unstable", **common)
                stats["insufficient"] += 1
            continue
        _ledger(cur, core, h, "CONFIRMED_OBSERVATIONAL", "confirmed_all_checks_passed", run_id,
                next_recheck=today + dt.timedelta(days=RECHECK_DAYS), **common)
        if is_recheck:
            stats["rechecked"] += 1
        else:
            _note(cur, panel_schema, "confirmation", hyp,
                  f"{hyp} passed every confirmation check on post-registration data and is now "
                  f"CONFIRMED_OBSERVATIONAL (observational, not experimental).")
            stats["confirmed"] += 1
    stats["scored"] = score_predictions(cur, core, panel, today)
    return stats
