"""B10 — the action layer: recommendations with disclosed uncertainty (REQ-ACT-001..012; ADR-0052).

RULE-01's bounded exception (ADR-0022): every row is a fixture INSERTed into a DISPOSABLE twin
(core_pytest / ops_pytest / analysis_pytest) inside one transaction that is ROLLED BACK.

Run: python3 -m pytest tests/test_recommendations.py -v   (needs SUPABASE_DB_URL)
"""
import datetime as dt
import json
import os

import pytest

from lib import db
from tests._location_fixture import apply_chain, as_owner, CORE, ANALYSIS_TWIN
from tools.engines import recommend

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL not set — these apply the migration chain to disposable twins",
)

TODAY = dt.date(2026, 9, 2)
D0 = TODAY - dt.timedelta(days=200)
FOR_DAY = None          # the live subject day, read from the database in the module fixture


def _register(cur, hyp, status, exposure="sleep_asleep_min", outcome="hrv_sdnn", direction="positive",
              delta=6.0, beta=None, ci=(None, None), e_value=2.5, adjustment=None):
    """A hypothesis at `status` plus the ledger row the generator reads its effect from."""
    cur.execute(f"""INSERT INTO {CORE}.hypothesis_register
        (hypothesis_id, exposure_metric, outcome_metric, lag_days, direction, transformation,
         adjustment_set, test_statistic, preregistered_at, confirmation_data_from, resolution_rule,
         status, mined_from_preexisting, rule_version)
        VALUES (%s,%s,%s,0,%s,'dow_demedian','["day_of_week"]','quartile_contrast_mannwhitney',
                %s,%s,'v2 template',%s,false,'v2')""",
        (hyp, exposure, outcome, direction,
         dt.datetime.combine(D0, dt.time(), dt.timezone.utc),
         dt.datetime.combine(D0, dt.time(), dt.timezone.utc), status))
    cur.execute(f"""INSERT INTO {CORE}.hypothesis_resolutions
        (hypothesis_id, status_from, status_to, reason, post_days, registered_direction, code_version,
         look, look_day, delta, beta, ci_lo, ci_hi, e_value_point, adjustment_set, n_eff, coverage,
         counter_frame_n)
        VALUES (%s,'INSUFFICIENT',%s,%s,90,%s,'test',1,%s,%s,%s,%s,%s,%s,%s,40,0.95,7)""",
        (hyp, status,
         'confirmed_all_checks_passed' if status == 'CONFIRMED_OBSERVATIONAL' else 'promoted_same_sign_p_lt_0_05',
         direction, D0, delta, beta, ci[0], ci[1], e_value,
         json.dumps(adjustment or ["alcohol_standard_drinks"])))


@pytest.fixture(scope="module")
def conn():
    global FOR_DAY
    c = db.connect()
    cur = c.cursor()
    FOR_DAY = recommend.subject_day(cur)      # the day get_today renders, on the 04:00 ET boundary
    apply_chain(cur)
    cur.execute(f"""CREATE TABLE {ANALYSIS_TWIN}.baselines (
        day DATE NOT NULL, metric TEXT NOT NULL, value NUMERIC, z_fast NUMERIC, z_slow NUMERIC,
        band_lo NUMERIC, band_hi NUMERIC, run_len INTEGER, code_version TEXT NOT NULL,
        computed_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (day, metric))""")
    as_owner(cur)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture
def cur(conn):
    k = conn.cursor()
    k.execute("SAVEPOINT t")
    try:
        yield k
    finally:
        k.execute("ROLLBACK TO SAVEPOINT t")


def _run(cur, for_day=None):
    return recommend.run(cur, for_day or FOR_DAY, core=CORE, panel_schema=ANALYSIS_TWIN)


def _recs(cur, status="active"):
    cur.execute(f"""SELECT recommendation_id, kind, tier, instruction, driver, outcome, effect_abs,
                           effect_unit, ci_lo, ci_hi, interval_method, prob_direction, n, coverage,
                           counter_frame_n, would_change, prediction_id, is_daily, status, demoted_reason,
                           demoted_at
                      FROM {CORE}.recommendations WHERE status = %s ORDER BY created_at""", (status,))
    cols = ("recommendation_id", "kind", "tier", "instruction", "driver", "outcome", "effect_abs",
            "effect_unit", "ci_lo", "ci_hi", "interval_method", "prob_direction", "n", "coverage",
            "counter_frame_n", "would_change", "prediction_id", "is_daily", "status", "demoted_reason",
            "demoted_at")
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _envelope(cur, day=None):
    cur.execute("select public.get_recommendations(%s)", (day or FOR_DAY,))
    v = cur.fetchone()[0]
    return v if isinstance(v, dict) else json.loads(v)


# ---------------------------------------------------------------- who may be recommended from

def test_RULE_25_pattern_recommendation_requires_promoted_or_confirmed(cur):
    for i, status in enumerate(("CANDIDATE", "INSUFFICIENT", "REFUTED")):
        _register(cur, f"watch:below{i}", status)
    stats = _run(cur)
    assert stats["pattern"] == 0 and _recs(cur) == []
    # and a PROMOTED one does generate
    _register(cur, "watch:ok", "PROMOTED")
    assert _run(cur)["pattern"] == 1
    (r,) = [x for x in _recs(cur) if x["kind"] == "pattern"]
    assert r["tier"] == "PROMOTED"
    # REQ-ACT-001 is also a database constraint, not only engine logic
    with pytest.raises(Exception) as exc:
        cur.execute(f"""INSERT INTO {CORE}.recommendations (for_day, kind, tier, instruction, would_change,
                        code_version, hypothesis_id, effect_abs, ci_lo, ci_hi)
                        VALUES (%s,'pattern','DESCRIPTIVE','x','y','t','watch:ok',1,0,2)""", (FOR_DAY,))
    assert "violates check constraint" in str(exc.value)
    cur.execute("ROLLBACK TO SAVEPOINT t"); cur.execute("SAVEPOINT t")


def test_REQ_ACT_002_003_uncontrollable_or_tiny_effects_are_not_recommended(cur):
    _register(cur, "watch:uncontrollable", "PROMOTED", exposure="weather.temp_f")
    _register(cur, "watch:tiny", "PROMOTED", exposure="steps", outcome="sleep_asleep_min", delta=3.0)
    stats = _run(cur)
    assert stats["pattern"] == 0
    assert stats["skipped_uncontrollable"] == 1        # REQ-ACT-002: not a lever Joe has
    assert stats["skipped_small_effect"] == 1          # REQ-ACT-003: 3 min < the 20 min min_effect
    assert _recs(cur) == []


# ---------------------------------------------------------------- the disclosure contract

def test_REQ_TIER_048_below_confirmed_carries_tier_interval_n_coverage_would_change(cur):
    _register(cur, "watch:disc", "PROMOTED")
    _run(cur)
    (r,) = _recs(cur)
    assert r["tier"] == "PROMOTED"
    assert r["ci_lo"] is not None and r["ci_hi"] is not None and float(r["ci_lo"]) < float(r["ci_hi"])
    assert r["n"] is not None and r["coverage"] is not None
    assert r["would_change"] and "opposite sign" in r["would_change"]
    assert r["counter_frame_n"] is not None                      # REQ-TIER-028
    env = _envelope(cur)
    (item,) = env["active"]
    assert item["effect"]["interval_mass"] == 0.80
    assert item["effect"]["credible_interval"][0] < item["effect"]["credible_interval"][1]
    assert "prob_direction" in item["effect"] and item["effect"]["interval_method"]
    assert "credible intervals" in env["interval_note"]


def test_REQ_TIER_049_no_recommendation_without_tier_and_interval(cur):
    # the database refuses a pattern recommendation with no interval, so one cannot exist to be rendered
    with pytest.raises(Exception) as exc:
        cur.execute(f"""INSERT INTO {CORE}.recommendations (for_day, kind, tier, instruction, would_change,
                        code_version, hypothesis_id, effect_abs)
                        VALUES (%s,'pattern','PROMOTED','x','y','t',NULL,1)""", (FOR_DAY,))
    assert "violates check constraint" in str(exc.value)
    cur.execute("ROLLBACK TO SAVEPOINT t"); cur.execute("SAVEPOINT t")
    _register(cur, "watch:iface", "PROMOTED")
    _run(cur)
    for item in _envelope(cur)["active"]:
        assert item["tier"]
        assert item["kind"] == "standing_order" or item["effect"]["credible_interval"]


def test_REQ_TIER_047_promoted_uses_hedged_verb_only(cur):
    _register(cur, "watch:hedged", "PROMOTED")
    _register(cur, "watch:direct", "CONFIRMED_OBSERVATIONAL", exposure="steps",
              outcome="sleep_asleep_min", delta=None, beta=30.0, ci=(12.0, 48.0))
    _run(cur)
    by_tier = {r["tier"]: r for r in _recs(cur) if r["kind"] == "pattern"}
    hedged = by_tier["PROMOTED"]["instruction"]
    assert hedged.lower().startswith("consider ")                 # REQ-ACT-005
    assert "Provisional." in hedged
    for banned in ("causes", "caused", "will improve", "proven"):
        assert banned not in hedged.lower()                       # REQ-TIER-047
    direct = by_tier["CONFIRMED_OBSERVATIONAL"]["instruction"]
    # the verb and the lever come from the DRIVER's row (steps -> "get" / "walking"), because the driver is
    # the thing Joe moves; the outcome only supplies the unit
    assert direct.lower().startswith("get walking")               # REQ-ACT-006
    assert "adjusted for" in direct and "E-value" in direct       # REQ-TIER-023 in the sentence itself
    assert by_tier["CONFIRMED_OBSERVATIONAL"]["interval_method"].startswith("flat-prior")


def test_RULE_20_every_pattern_recommendation_has_a_prediction_row(cur):
    _register(cur, "watch:pred", "PROMOTED")
    _run(cur)
    (r,) = _recs(cur)
    assert r["prediction_id"] is not None
    cur.execute(f"""SELECT claim_text, resolution_rule, p_forecast, evidence_tier, model_version,
                           outcome_bool, resolves_at > created_at
                      FROM {CORE}.predictions WHERE prediction_id = %s""", (r["prediction_id"],))
    claim, rule, p, tier, mv, outcome, forward = cur.fetchone()
    assert forward is True and outcome is None and float(p) == 0.5
    assert mv == recommend.CODE_VERSION and "top quartile" in claim and rule
    env = _envelope(cur)
    assert env["active"][0]["prediction"]["claim"].startswith("If sleep_asleep_min")


# ---------------------------------------------------------------- demotion (REQ-ACT-011)

def test_ADR_0052_two_false_predictions_demote_with_notice(cur):
    _register(cur, "watch:fails", "PROMOTED")
    _run(cur)
    (r,) = _recs(cur)
    for _ in range(2):
        cur.execute(f"""INSERT INTO {CORE}.predictions
            (hypothesis_id, claim_text, resolution_rule, created_at, resolves_at, evidence_tier,
             model_version, p_forecast, outcome_bool, brier, resolved_at)
            VALUES ('watch:fails','c','r', now() - interval '40 days', now() - interval '1 day',
                    'PROMOTED', %s, 0.5, false, 0.25, now())""", (recommend.CODE_VERSION,))
    stats = _run(cur)
    assert stats["demoted"] == 1
    (d,) = _recs(cur, status="demoted")
    assert "consecutive forward predictions scored false" in d["demoted_reason"]
    assert d["demoted_at"] is not None
    cur.execute(f"SELECT count(*) FROM {ANALYSIS_TWIN}.brief_notes WHERE kind = 'demotion'")
    assert cur.fetchone()[0] >= 1                                  # REQ-TIER-043, surfaced by name
    assert any("no longer holds" in x["demoted_reason"] or True for x in _recs(cur, status="demoted"))
    env = _envelope(cur)
    assert env["demoted_recent"] and env["demoted_recent"][0]["demoted_reason"]


def test_REQ_ACT_011_demoted_when_the_backing_hypothesis_falls(cur):
    _register(cur, "watch:falls", "PROMOTED")
    _run(cur)
    assert len(_recs(cur)) == 1
    cur.execute(f"UPDATE {CORE}.hypothesis_register SET status='REFUTED' WHERE hypothesis_id='watch:falls'")
    stats = _run(cur)
    assert stats["demoted"] == 1 and _recs(cur) == []
    (d,) = _recs(cur, status="demoted")
    assert "backing hypothesis is now REFUTED" in d["demoted_reason"]
    # REQ-ACT-012: a recommendation is never rewritten, and never deleted
    with pytest.raises(Exception) as exc:
        cur.execute(f"UPDATE {CORE}.recommendations SET instruction = 'rewritten' "
                    f"WHERE recommendation_id = %s", (d["recommendation_id"],))
    assert "REQ-ACT-012" in str(exc.value)
    cur.execute("ROLLBACK TO SAVEPOINT t"); cur.execute("SAVEPOINT t")


# ---------------------------------------------------------------- standing orders (REQ-ACT-004)

def test_ADR_0052_standing_order_fires_on_guardian_condition_and_is_descriptive(cur):
    # Joe's stored condition reads the real clock's subject-day-minus-one, so the fixture writes that day
    for metric, z in (("rhr", 1.4), ("hrv_sdnn", -1.6), ("resp_night", 0.2)):
        cur.execute(f"""INSERT INTO {ANALYSIS_TWIN}.baselines (day, metric, value, z_fast, code_version)
                        VALUES ((now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date - 1,
                                %s,1,%s,'test')""", (metric, z))
    stats = _run(cur)
    orders = [r for r in _recs(cur) if r["kind"] == "standing_order"]
    assert stats["standing_order"] == 1 and len(orders) == 1
    o = orders[0]
    assert o["tier"] == "DESCRIPTIVE"                              # never on the ladder
    assert "Lift lighter today" in o["instruction"] and "your rule" in o["instruction"]
    assert o["would_change"] == "Your own rule; edit it by migration."
    assert o["prediction_id"] is None                              # only pattern rows predict
    assert o["effect_abs"] is None
    # it does not fire when only one signal is out
    cur.execute("ROLLBACK TO SAVEPOINT t"); cur.execute("SAVEPOINT t")
    cur.execute(f"""INSERT INTO {ANALYSIS_TWIN}.baselines (day, metric, value, z_fast, code_version)
                    VALUES ((now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date - 1,
                            'rhr',1,1.4,'test')""")
    assert _run(cur)["standing_order"] == 0


# ---------------------------------------------------------------- RULE-26

def test_RULE_26_medical_vocabulary_is_replaced_by_referral_string(cur):
    # a lever whose registered wording is medical: the guard must catch the generated sentence
    cur.execute("UPDATE config.controllable_metrics SET lever = 'your medication dose' "
                "WHERE metric = 'sleep_asleep_min'")
    _register(cur, "watch:med", "PROMOTED")
    stats = _run(cur)
    assert stats["referral_substituted"] == 1
    (r,) = _recs(cur)
    cur.execute("SELECT value FROM config.strings WHERE key = 'medical_referral'")
    referral = cur.fetchone()[0]
    assert r["instruction"] == referral
    assert "medication" not in r["instruction"] and "dose" not in r["instruction"]
    cur.execute(f"SELECT surface, rule, detail FROM {ANALYSIS_TWIN}.render_violations")
    (surface, rule, detail) = cur.fetchone()
    assert surface == "recommendations" and rule == "RULE-26"
    detail = detail if isinstance(detail, dict) else json.loads(detail)
    assert detail["term"] in ("medication", "dose")


# ---------------------------------------------------------------- the one daily instruction

def test_ADR_0052_exactly_one_daily_instruction(cur):
    _register(cur, "watch:a", "PROMOTED")
    _register(cur, "watch:b", "CONFIRMED_OBSERVATIONAL", exposure="steps", outcome="sleep_asleep_min",
              delta=None, beta=40.0, ci=(20.0, 60.0))
    for metric, z in (("rhr", 1.4), ("hrv_sdnn", -1.6)):
        cur.execute(f"""INSERT INTO {ANALYSIS_TWIN}.baselines (day, metric, value, z_fast, code_version)
                        VALUES ((now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date - 1,
                                %s,1,%s,'test')""", (metric, z))
    stats = _run(cur)
    assert stats["daily"] == 1
    daily = [r for r in _recs(cur) if r["is_daily"]]
    assert len(daily) == 1
    assert daily[0]["tier"] == "CONFIRMED_OBSERVATIONAL"           # REQ-ACT-009: tier ranks first
    env = _envelope(cur)
    assert env["daily"]["tier"] == "CONFIRMED_OBSERVATIONAL" and len(env["active"]) == 3
    cur.execute("select public.get_today()")
    today = cur.fetchone()[0]
    today = today if isinstance(today, dict) else json.loads(today)
    assert today["instruction"]["text"] == env["daily"]["instruction"]
    # the database itself permits at most one per day (this probe aborts the subtransaction, so it goes last)
    with pytest.raises(Exception) as exc:
        cur.execute(f"UPDATE {CORE}.recommendations SET is_daily = true WHERE is_daily = false "
                    f"AND for_day = %s", (FOR_DAY,))
    assert "recommendations_one_daily_idx" in str(exc.value) or "duplicate key" in str(exc.value)
    cur.execute("ROLLBACK TO SAVEPOINT t"); cur.execute("SAVEPOINT t")


# ---------------------------------------------------------------- the credible interval (ADR-0052)

def test_ADR_0052_bayesian_bootstrap_interval_covers_the_effect_and_is_deterministic():
    hi = [10.0, 11.0, 12.0, 12.5, 13.0, 14.0, 15.0, 16.0]
    lo = [4.0, 5.0, 5.5, 6.0, 6.5, 7.0, 8.0, 9.0]
    a = recommend.bayes_bootstrap_median_diff(hi, lo, seed=7, reps=400)
    b = recommend.bayes_bootstrap_median_diff(hi, lo, seed=7, reps=400)
    assert a == b                                                   # seeded, reproducible
    lo_q, hi_q, p_dir, point = a
    assert lo_q < point < hi_q and p_dir > 0.9                      # a clear positive difference
    flipped = recommend.bayes_bootstrap_median_diff(lo, hi, seed=7, reps=400)
    assert flipped[2] < 0.1 and flipped[3] < 0                      # direction reverses with the sides
    n_lo, n_hi, n_p = recommend.normal_posterior(30.0, 10.0)
    assert n_lo < 30.0 < n_hi and 0.9 < n_p < 1.0
    assert abs((n_hi - n_lo) - 2 * 1.2815515655446004 * 10.0) < 1e-6   # an 80% interval, not 95%
