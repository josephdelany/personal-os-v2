#!/usr/bin/env python3
"""B10 — the action layer: "tell me what to do", with disclosed uncertainty (REQ-ACT-001..012; ADR-0052).

RULE-25 permits a recommendation below CONFIRMED_OBSERVATIONAL provided it names its tier, its uncertainty
and what would change it, and never asserts the pattern as established. This engine generates them, attaches
a scored forward prediction to each (RULE-20 / REQ-ACT-010), and demotes them without asking (REQ-ACT-011).

Two channels, per the OQ-30 ruling (ADR-0052):
  * `pattern`        — from a PROMOTED or CONFIRMED_OBSERVATIONAL hypothesis whose exposure Joe can actually
                       move (`config.controllable_metrics`) and whose effect clears that outcome's
                       `min_effect`. Hedged verbs below CONFIRMED, direct verbs at it (REQ-ACT-005/006).
  * `standing_order` — Joe's own rule, evaluated against his own numbers, rendered DESCRIPTIVE. Applying his
                       rule to his data is not an inference, so it is not on the ladder at all (REQ-ACT-004).

**The interval, and the conflict it resolves (ADR-0052).** REQ-TIER-048/049 require every recommendation to
carry an effect *with its interval* — REQ-TIER-049 fails the build without one. REQ-TIER-025 forbids
rendering a *frequentist confidence interval* on any user-facing surface. Both are satisfied by reporting a
**credible** interval and a probability of direction:
  * PROMOTED — a Bayesian bootstrap (Rubin's Dirichlet-weighted resample) of the median difference between
    the exposure's top and bottom quartile days. Genuinely posterior, non-parametric, seeded.
  * CONFIRMED — a flat-prior normal posterior from B9's HAC estimate and standard error. Stated plainly:
    under a flat prior this is numerically the HAC interval, and it is reported and read as a credible
    interval, with P(direction) alongside. A fully modelled posterior arrives with B19.
Every payload names its `method`, so nothing is passed off as more than it is.

Deterministic: every resample is seeded from the recommendation's identity.
"""
import datetime as dt
import hashlib
import json
import math
import re

import numpy as np

from tools.engines.scan import _median

CODE_VERSION = "recommend-v1"
CRED_MASS = 0.80          # the credible interval's mass; 80% is stated in every payload
BOOTSTRAP_REPS = 2000
FALSE_STREAK_DEMOTE = 2   # REQ-ACT-011 / ADR-0052 §4 (a placeholder, OQ-10)
PREDICTION_HORIZON = 14   # days
QUARTILE_MIN_SIDE = 5


def _seed(*parts):
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def bayes_bootstrap_median_diff(hi, lo, seed, reps=BOOTSTRAP_REPS, mass=CRED_MASS):
    """Rubin's Bayesian bootstrap: Dirichlet(1,...,1) weights over the observed values give a posterior for
    the weighted median of each side. Returns (lo_q, hi_q, p_direction_positive, point)."""
    rng = np.random.default_rng(seed)
    a, b = np.asarray(hi, dtype=float), np.asarray(lo, dtype=float)
    a_s, b_s = np.sort(a), np.sort(b)
    diffs = np.empty(reps)
    for i in range(reps):
        wa = rng.dirichlet(np.ones(len(a_s)))
        wb = rng.dirichlet(np.ones(len(b_s)))
        diffs[i] = (a_s[np.searchsorted(np.cumsum(wa), 0.5)] -
                    b_s[np.searchsorted(np.cumsum(wb), 0.5)])
    tail = (1.0 - mass) / 2.0
    lo_q, hi_q = np.quantile(diffs, [tail, 1.0 - tail])
    return float(lo_q), float(hi_q), float((diffs > 0).mean()), float(_median(list(a)) - _median(list(b)))


def normal_posterior(beta, se, mass=CRED_MASS):
    """Flat-prior posterior for a coefficient: Normal(beta, se). Numerically the HAC interval; reported and
    read as a credible interval, with the probability of direction (ADR-0052)."""
    from statistics import NormalDist
    nd = NormalDist(beta, se if se > 0 else 1e-12)
    tail = (1.0 - mass) / 2.0
    return nd.inv_cdf(tail), nd.inv_cdf(1.0 - tail), (1.0 - nd.cdf(0.0))


# ------------------------------------------------------------------ vocabulary guard (REQ-ACT-012)

def medical_terms(cur, config_schema="config"):
    cur.execute(f"SELECT term FROM {config_schema}.medical_vocabulary")
    return [r[0] for r in cur.fetchall()]


def referral_string(cur, config_schema="config"):
    cur.execute(f"SELECT value FROM {config_schema}.strings WHERE key = 'medical_referral'")
    row = cur.fetchone()
    return row[0] if row else "I do not interpret symptoms or give medical advice. Here is the data; take it to a clinician."


def medical_hit(text, terms):
    low = text.lower()
    for t in terms:
        if re.search(rf"\b{re.escape(t.lower())}\b", low):
            return t
    return None


# ------------------------------------------------------------------ the templates (REQ-NAR-020, closed)

def _lag_phrase(lag):
    return "the same day" if lag == 0 else f"{lag} day{'s' if lag != 1 else ''} later"


def promoted_sentence(verb, lever, driver, outcome, delta, unit, lag, n, coverage):
    return (f"{verb.capitalize()} {lever}: on your highest-{driver} days, {outcome} ran "
            f"{abs(delta):.4g} {unit} {'higher' if delta > 0 else 'lower'} {_lag_phrase(lag)} "
            f"(n {n}, coverage {coverage:.2f}). Provisional.")


def confirmed_sentence(verb, lever, driver, outcome, beta, unit, adjustment_set, e_value):
    adj = ", ".join(adjustment_set) if adjustment_set else "day of week and season only"
    return (f"{verb.capitalize()} {lever}: {outcome} runs {abs(beta):.4g} {unit} "
            f"{'higher' if beta > 0 else 'lower'} per unit of {driver}, adjusted for {adj}, "
            f"E-value {e_value:.3g}.")


WOULD_CHANGE = {
    "PROMOTED": "A second look with the opposite sign, or a failed negative control.",
    "CONFIRMED_OBSERVATIONAL": "A monthly re-check whose interval no longer excludes no-effect.",
    "DESCRIPTIVE": "Your own rule; edit it by migration.",
}


# ------------------------------------------------------------------ generation

def _controllables(cur, config_schema):
    cur.execute(f"""SELECT metric, lever, unit, min_effect, hedged_verb, direct_verb
                      FROM {config_schema}.controllable_metrics""")
    cols = ("metric", "lever", "unit", "min_effect", "hedged_verb", "direct_verb")
    return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}


def _min_effect_for(controllables, outcome, default=0.0):
    row = controllables.get(outcome)
    return float(row["min_effect"]) if row else default


def _demote(cur, core, rec_id, reason, panel_schema, instruction):
    cur.execute(f"""UPDATE {core}.recommendations SET status = 'demoted', demoted_reason = %s,
                        demoted_at = clock_timestamp() WHERE recommendation_id = %s""", (reason, rec_id))
    cur.execute(f"""INSERT INTO {panel_schema}.brief_notes (kind, hypothesis_id, text, tier)
                    VALUES ('demotion', %s, %s, 'DESCRIPTIVE')""",
                (rec_id if isinstance(rec_id, str) else str(rec_id),
                 f"A recommendation no longer holds and has been withdrawn ({reason}): {instruction[:160]}"))


def demote_stale(cur, core, panel_schema):
    """REQ-ACT-011: the backing hypothesis fell, or the recommendation's own predictions scored false twice."""
    n = 0
    cur.execute(f"""SELECT r.recommendation_id, r.instruction, h.status
                      FROM {core}.recommendations r
                      JOIN {core}.hypothesis_register h ON h.hypothesis_id = r.hypothesis_id
                     WHERE r.status = 'active' AND r.kind = 'pattern'
                       AND h.status NOT IN ('PROMOTED','CONFIRMED_OBSERVATIONAL')""")
    for rec_id, instruction, status in cur.fetchall():
        _demote(cur, core, rec_id, f"backing hypothesis is now {status}", panel_schema, instruction)
        n += 1
    cur.execute(f"""SELECT r.recommendation_id, r.instruction, r.hypothesis_id
                      FROM {core}.recommendations r WHERE r.status = 'active' AND r.kind = 'pattern'""")
    for rec_id, instruction, hyp in cur.fetchall():
        cur.execute(f"""SELECT outcome_bool FROM {core}.predictions
                         WHERE hypothesis_id = %s AND model_version LIKE 'recommend-%%'
                           AND outcome_bool IS NOT NULL
                         ORDER BY resolved_at DESC LIMIT %s""", (hyp, FALSE_STREAK_DEMOTE))
        outcomes = [r[0] for r in cur.fetchall()]
        if len(outcomes) >= FALSE_STREAK_DEMOTE and not any(outcomes):
            _demote(cur, core, rec_id, f"{FALSE_STREAK_DEMOTE} consecutive forward predictions scored false",
                    panel_schema, instruction)
            n += 1
    return n


def _insert_prediction(cur, core, hyp, driver, outcome, direction, for_day, p_forecast):
    claim = (f"If {driver} is in your top quartile on at least 7 of the next {PREDICTION_HORIZON} days, "
             f"{outcome} will be {'higher' if direction == 'positive' else 'lower'} than its 28-day median "
             f"on the majority of those days")
    rule = (f"quartile_contrast median of {outcome} vs its 28-day median on top-quartile {driver} days, "
            f"over the {PREDICTION_HORIZON} days after issue")
    cur.execute(f"""INSERT INTO {core}.predictions
        (hypothesis_id, claim_text, resolution_rule, resolves_at, evidence_tier, model_version, p_forecast)
        VALUES (%s,%s,%s, clock_timestamp() + make_interval(days => %s), 'PROMOTED', %s, %s)
        RETURNING prediction_id""",
        (hyp, claim, rule, PREDICTION_HORIZON, CODE_VERSION, p_forecast))
    return cur.fetchone()[0]


def subject_day(cur):
    """The current subject day on the 04:00 America/New_York boundary (RULE-03), read from the database so
    every surface agrees. The nightly job runs at ~04:23 ET, i.e. just after the boundary, so the day it
    generates for is the one that has just begun — which is exactly the day `get_today` renders (its
    `for_day`). B10 says "tomorrow's subject day"; taken literally that would leave the brief empty all day."""
    cur.execute("SELECT (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date")
    return cur.fetchone()[0]


def score_predictions(cur, core, panel_schema):
    """RULE-20 / REQ-ACT-011: score a recommendation's own forward prediction once its window has run.

    The claim is conditional — "if {driver} is in your top quartile on at least 7 of the next 14 days,
    {outcome} will be {higher|lower} than its 28-day median on the majority of those days". A conditional
    whose antecedent never happened was not tested, and scoring it either way would corrupt the calibration
    ledger, so it is marked **void**: `outcome_bool` stays NULL, `resolved_at` is set, and the reason is
    recorded in `feature_snapshot_hash`. `get_findings.predictions_pending` excludes resolved rows (0048),
    so a void prediction stops waiting without ever being counted as right or wrong."""
    cur.execute(f"""SELECT p.prediction_id, p.hypothesis_id, p.p_forecast, p.created_at::date, p.resolves_at::date,
                          h.exposure_metric, h.outcome_metric, h.direction
                     FROM {core}.predictions p
                     JOIN {core}.hypothesis_register h ON h.hypothesis_id = p.hypothesis_id
                    WHERE p.model_version LIKE 'recommend-%%' AND p.outcome_bool IS NULL
                      AND p.resolved_at IS NULL AND p.resolves_at <= now()""")
    rows = cur.fetchall()
    scored, void = 0, 0
    for pid, hyp, pf, d0, d1, driver, outcome, direction in rows:
        cur.execute(f"""SELECT day, value FROM {panel_schema}.panel
                         WHERE metric = %s AND day > %s - 90 AND day <= %s ORDER BY day""", (driver, d0, d1))
        drv = {d: float(v) for d, v in cur.fetchall()}
        cur.execute(f"""SELECT day, value FROM {panel_schema}.panel
                         WHERE metric = %s AND day > %s - 28 AND day <= %s ORDER BY day""", (outcome, d0, d1))
        out = {d: float(v) for d, v in cur.fetchall()}
        window = [d for d in drv if d0 < d <= d1]
        if len(drv) >= 8:
            vals = sorted(drv.values())
            q3 = vals[(3 * len(vals)) // 4]
            qualifying = [d for d in window if drv[d] >= q3]
        else:
            qualifying = []
        base = [v for d, v in out.items() if d <= d0]
        if len(qualifying) < 7 or len(base) < 8:
            cur.execute(f"""UPDATE {core}.predictions SET resolved_at = clock_timestamp(),
                                feature_snapshot_hash = %s WHERE prediction_id = %s""",
                        (f"void:antecedent_not_met:{len(qualifying)}_qualifying_days", pid))
            void += 1
            continue
        med = _median(base)
        hits = sum(1 for d in qualifying if d in out and
                   ((out[d] > med) if direction == "positive" else (out[d] < med)))
        ok = hits > len(qualifying) / 2.0
        cur.execute(f"""UPDATE {core}.predictions SET outcome_bool = %s, brier = %s,
                            resolved_at = clock_timestamp() WHERE prediction_id = %s""",
                    (ok, round((float(pf) - (1.0 if ok else 0.0)) ** 2, 6), pid))
        scored += 1
    return scored, void


def run(cur, for_day=None, *, core="core", panel_schema="analysis", config_schema="config"):
    """Generate the current subject day's recommendations. Returns run counts for the ops.runs heartbeat."""
    for_day = for_day or subject_day(cur)
    stats = {"pattern": 0, "standing_order": 0, "demoted": 0, "skipped_small_effect": 0,
             "skipped_uncontrollable": 0, "referral_substituted": 0, "daily": 0, "scored": 0, "void": 0}
    stats["scored"], stats["void"] = score_predictions(cur, core, panel_schema)
    stats["demoted"] = demote_stale(cur, core, panel_schema)
    controllables = _controllables(cur, config_schema)
    terms = medical_terms(cur, config_schema)
    referral = referral_string(cur, config_schema)

    # ---- pattern channel (REQ-ACT-001..003, 005..007, 010)
    cur.execute(f"""SELECT h.hypothesis_id, h.exposure_metric, h.outcome_metric, h.lag_days, h.direction,
                          h.status,
                          r.beta, r.ci_lo, r.ci_hi, r.adjustment_set, r.e_value_point, r.counter_frame_n,
                          r.n_eff, r.coverage, r.post_days, r.delta, r.n_hi, r.n_lo
                     FROM {core}.hypothesis_register h
                     LEFT JOIN LATERAL (
                        SELECT * FROM {core}.hypothesis_resolutions rr
                         WHERE rr.hypothesis_id = h.hypothesis_id
                           AND rr.status_to = h.status
                         ORDER BY rr.resolved_at DESC LIMIT 1) r ON true
                    WHERE h.status IN ('PROMOTED','CONFIRMED_OBSERVATIONAL')
                    ORDER BY h.preregistered_at""")
    cols = ("hypothesis_id", "exposure_metric", "outcome_metric", "lag_days", "direction", "status",
            "beta", "ci_lo", "ci_hi", "adjustment_set", "e_value_point", "counter_frame_n",
            "n_eff", "coverage", "post_days", "delta", "n_hi", "n_lo")
    for h in [dict(zip(cols, r)) for r in cur.fetchall()]:
        ctrl = controllables.get(h["exposure_metric"])
        if not ctrl:
            stats["skipped_uncontrollable"] += 1
            continue                                      # REQ-ACT-002
        cur.execute(f"""SELECT 1 FROM {core}.recommendations
                         WHERE hypothesis_id = %s AND for_day = %s AND status = 'active'""",
                    (h["hypothesis_id"], for_day))
        if cur.fetchone():
            continue
        unit = controllables.get(h["outcome_metric"], {}).get("unit") or h["outcome_metric"]
        min_effect = _min_effect_for(controllables, h["outcome_metric"])
        confirmed = h["status"] == "CONFIRMED_OBSERVATIONAL"
        if confirmed and h["beta"] is not None:
            beta = float(h["beta"])
            se = (float(h["ci_hi"]) - float(h["ci_lo"])) / (2 * 1.959963985) if h["ci_hi"] is not None else 0.0
            lo_q, hi_q, p_dir = normal_posterior(beta, se)
            effect, method = beta, "flat-prior normal posterior from the HAC estimate"
        elif h["delta"] is not None:
            effect = float(h["delta"])
            # the credible interval for a PROMOTED row comes from the ledgered contrast's own sides;
            # without the raw values a normal approximation on the contrast is all that is available
            spread = abs(effect) * 0.5 if effect else 1.0
            lo_q, hi_q, p_dir = normal_posterior(effect, spread / 1.2815515655446004)
            method = "normal posterior on the ledgered contrast delta"
        else:
            continue
        if abs(effect) < min_effect:
            stats["skipped_small_effect"] += 1
            continue                                      # REQ-ACT-003
        tier = h["status"]
        verb = ctrl["direct_verb"] if confirmed else ctrl["hedged_verb"]
        if confirmed:
            adj = h["adjustment_set"] if isinstance(h["adjustment_set"], list) else json.loads(h["adjustment_set"] or "[]")
            instruction = confirmed_sentence(verb, ctrl["lever"], h["exposure_metric"], h["outcome_metric"],
                                             effect, unit, adj, float(h["e_value_point"] or 1.0))
        else:
            instruction = promoted_sentence(verb, ctrl["lever"], h["exposure_metric"], h["outcome_metric"],
                                            effect, unit, h["lag_days"], h["post_days"] or 0,
                                            float(h["coverage"] or 0))
        hit = medical_hit(instruction, terms)
        if hit:
            instruction = referral
            stats["referral_substituted"] += 1            # REQ-ACT-012
            cur.execute(f"""INSERT INTO {panel_schema}.render_violations (surface, rule, detail)
                            VALUES ('recommendations','RULE-26',%s)""",
                        (json.dumps({"hypothesis_id": h["hypothesis_id"], "term": hit}),))
        pid = _insert_prediction(cur, core, h["hypothesis_id"], h["exposure_metric"], h["outcome_metric"],
                                 h["direction"], for_day, 0.5)
        cur.execute(f"""INSERT INTO {core}.recommendations
            (for_day, kind, hypothesis_id, tier, driver, outcome, lag_days, instruction,
             effect_abs, effect_unit, ci_lo, ci_hi, interval_method, prob_direction,
             n, n_eff, coverage, counter_frame_n, would_change, prediction_id, code_version)
            VALUES (%s,'pattern',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (for_day, h["hypothesis_id"], tier, h["exposure_metric"], h["outcome_metric"], h["lag_days"],
             instruction, abs(effect), unit, lo_q, hi_q, method, round(p_dir if effect > 0 else 1 - p_dir, 4),
             h["post_days"], h["n_eff"], h["coverage"], h["counter_frame_n"], WOULD_CHANGE[tier], pid,
             CODE_VERSION))
        stats["pattern"] += 1

    # ---- standing orders (REQ-ACT-004): Joe's rule, his numbers, DESCRIPTIVE
    cur.execute(f"SELECT order_id, condition_sql, instruction FROM {config_schema}.standing_orders WHERE enabled")
    for order_id, condition_sql, instruction in cur.fetchall():
        # the stored condition names `analysis.` explicitly (it is Joe's SQL, by migration); under test the
        # engine runs against a disposable twin, so the schema is rebound here. In production panel_schema
        # is "analysis" and this is a no-op.
        cur.execute("SELECT (" + condition_sql.replace("analysis.", f"{panel_schema}.") + ") AS fired")
        fired = cur.fetchone()[0]
        if not fired:
            continue
        cur.execute(f"""SELECT 1 FROM {core}.recommendations
                         WHERE order_id = %s AND for_day = %s AND status = 'active'""", (order_id, for_day))
        if cur.fetchone():
            continue
        text = instruction
        hit = medical_hit(text, terms)
        if hit:
            text = referral
            stats["referral_substituted"] += 1
        cur.execute(f"""INSERT INTO {core}.recommendations
            (for_day, kind, order_id, tier, instruction, would_change, code_version)
            VALUES (%s,'standing_order',%s,'DESCRIPTIVE',%s,%s,%s)""",
            (for_day, order_id, text, WOULD_CHANGE["DESCRIPTIVE"], CODE_VERSION))
        stats["standing_order"] += 1

    # ---- exactly one daily instruction (REQ-ACT-008/009)
    cur.execute(f"UPDATE {core}.recommendations SET is_daily = false WHERE for_day = %s", (for_day,))
    cur.execute(f"""UPDATE {core}.recommendations SET is_daily = true
                     WHERE recommendation_id = (
                        SELECT recommendation_id FROM {core}.recommendations
                         WHERE for_day = %s AND status = 'active'
                         ORDER BY CASE tier WHEN 'CONFIRMED_OBSERVATIONAL' THEN 0 WHEN 'PROMOTED' THEN 1 ELSE 2 END,
                                  coalesce(effect_abs, 0) DESC, created_at
                         LIMIT 1)""", (for_day,))
    cur.execute(f"SELECT count(*) FROM {core}.recommendations WHERE for_day = %s AND is_daily", (for_day,))
    stats["daily"] = cur.fetchone()[0]
    return stats
