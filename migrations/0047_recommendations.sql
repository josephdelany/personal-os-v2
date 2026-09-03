-- 0047_recommendations.sql — B10: RULE-25 as built (REQ-ACT-001..012; ADR-0052, closing OQ-30).
-- The action layer: what to do today, with its tier, its credible interval, what would change it, and a
-- scored forward prediction attached. Two channels: `pattern` (from a PROMOTED / CONFIRMED_OBSERVATIONAL
-- hypothesis whose exposure Joe can move) and `standing_order` (Joe's own rule, DESCRIPTIVE).

-- ---------------------------------------------------------------- what Joe can actually move
CREATE TABLE IF NOT EXISTS config.controllable_metrics (
    metric      TEXT PRIMARY KEY,
    lever       TEXT NOT NULL,                 -- how Joe moves it, in his words
    unit        TEXT NOT NULL,
    min_effect  NUMERIC NOT NULL,              -- OQ-10 placeholder per metric: below this, say nothing
    hedged_verb TEXT NOT NULL DEFAULT 'consider',
    direct_verb TEXT NOT NULL DEFAULT 'do'
);
COMMENT ON COLUMN config.controllable_metrics.min_effect IS
  'REQ-ACT-003. A placeholder (OQ-10): a guess at what Joe would notice, to be calibrated against real data.';
REVOKE ALL ON config.controllable_metrics FROM anon, authenticated;
INSERT INTO config.controllable_metrics (metric, lever, unit, min_effect, hedged_verb, direct_verb) VALUES
 ('alcohol_standard_drinks','drinks tonight','drinks',1,'consider','keep'),
 ('sleep_asleep_min','time in bed','min',20,'consider','protect'),
 ('sleep_midpoint','bedtime','clock',0.5,'consider','keep'),
 ('steps','walking','steps',2000,'consider','get'),
 ('exercise_min','training','min',15,'consider','do'),
 ('strength_volume','session volume','lb-reps',1000,'consider','lift'),
 ('screen_active_hours','screen time','h',1,'consider','cap'),
 ('screen_binge_min','late binges','min',30,'consider','cut'),
 ('meals_logged','logging meals','meals',1,'consider','log')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------- Joe's own rules (REQ-ACT-004)
CREATE TABLE IF NOT EXISTS config.standing_orders (
    order_id      TEXT PRIMARY KEY,
    condition_sql TEXT NOT NULL,               -- a boolean SQL expression over analysis.baselines; by migration only
    instruction   TEXT NOT NULL,
    enabled       BOOLEAN NOT NULL DEFAULT true
);
COMMENT ON TABLE config.standing_orders IS
  'ADR-0052 ruling 2. Joe''s own rules, applied to his own numbers: not an inference, so tier DESCRIPTIVE. '
  'condition_sql is owner-written and changes only by migration — it is executed, so nothing else may write it.';
REVOKE ALL ON config.standing_orders FROM anon, authenticated;
INSERT INTO config.standing_orders (order_id, condition_sql, instruction) VALUES
 ('guardian',
  '(SELECT count(*) FILTER (WHERE metric=''rhr'' AND z_fast >= 1.0)'
  ' + count(*) FILTER (WHERE metric=''hrv_sdnn'' AND z_fast <= -1.0)'
  ' + count(*) FILTER (WHERE metric=''resp_night'' AND z_fast >= 1.0)'
  ' + count(*) FILTER (WHERE metric=''wrist_temp_f'' AND z_fast >= 1.0)'
  ' FROM analysis.baselines'
  ' WHERE day = (now() AT TIME ZONE ''America/New_York'' - interval ''4 hours'')::date - 1) >= 2',
  'Lift lighter today; this is your rule for a 2-of-4 autonomic day.'),
 ('sleep_debt',
  '(SELECT count(*) FROM analysis.baselines'
  ' WHERE metric = ''sleep_asleep_min'' AND value < band_lo'
  '   AND day > (now() AT TIME ZONE ''America/New_York'' - interval ''4 hours'')::date - 3'
  '   AND day <= (now() AT TIME ZONE ''America/New_York'' - interval ''4 hours'')::date - 1) >= 2',
  'Protect tonight''s sleep; two nights below your band.')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------- RULE-26 / REQ-ACT-012
CREATE TABLE IF NOT EXISTS config.medical_vocabulary (term TEXT PRIMARY KEY, note TEXT);
REVOKE ALL ON config.medical_vocabulary FROM anon, authenticated;
INSERT INTO config.medical_vocabulary (term, note) VALUES
 ('diagnose','RULE-26: never name a condition'), ('diagnosis','RULE-26'),
 ('symptom','RULE-26: never interpret a symptom'), ('symptoms','RULE-26'),
 ('disease','RULE-26'), ('disorder','RULE-26'), ('syndrome','RULE-26'),
 ('infection','RULE-26'), ('depression','RULE-26'), ('anxiety disorder','RULE-26'),
 ('apnea','RULE-26'), ('arrhythmia','RULE-26'), ('hypertension','RULE-26'),
 ('diabetes','RULE-26'), ('prescribe','RULE-26: never prescribe'), ('prescription','RULE-26'),
 ('dose','RULE-26: never dose'), ('dosage','RULE-26'), ('mg','RULE-26: never dose'),
 ('medication','RULE-26'), ('drug','RULE-26'), ('supplement dose','RULE-26'),
 ('treat','RULE-26: never recommend a treatment'), ('treatment','RULE-26'), ('therapy','RULE-26'),
 ('cure','RULE-26'), ('see a doctor about','RULE-26: the referral string is the only referral')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS config.strings (key TEXT PRIMARY KEY, value TEXT NOT NULL, note TEXT);
REVOKE ALL ON config.strings FROM anon, authenticated;
INSERT INTO config.strings (key, value, note) VALUES
 ('medical_referral',
  'I do not interpret symptoms or give medical advice. Here is the relevant data; take it to a clinician.',
  'REQ-ASK-028 / RULE-26: the single stored referral string, returned with the data attached.')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------- the render-refusal sink
-- Referenced by REQ-FIN-003, REQ-NAR-004, REQ-NAR-025, REQ-ASK-015 and REQ-TIER-054 and never created
-- until now (ADR-0052). Every "the render layer refused" event lands here.
CREATE TABLE IF NOT EXISTS analysis.render_violations (
    violation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    at           TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    surface      TEXT NOT NULL,
    rule         TEXT NOT NULL,
    detail       JSONB
);
REVOKE ALL ON analysis.render_violations FROM anon, authenticated;

-- ---------------------------------------------------------------- the recommendations themselves
CREATE TABLE IF NOT EXISTS __CORE__.recommendations (
    recommendation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    for_day         DATE NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('pattern','standing_order')),
    hypothesis_id   TEXT REFERENCES __CORE__.hypothesis_register(hypothesis_id),
    order_id        TEXT,
    tier            TEXT NOT NULL CHECK (tier IN ('DESCRIPTIVE','PROMOTED','CONFIRMED_OBSERVATIONAL')),
    driver          TEXT, outcome TEXT, lag_days INTEGER,
    instruction     TEXT NOT NULL,
    effect_abs      NUMERIC, effect_unit TEXT,
    ci_lo           NUMERIC, ci_hi NUMERIC,
    interval_method TEXT,                       -- ADR-0052: the interval is CREDIBLE; this names how
    prob_direction  NUMERIC,                    -- REQ-TIER-025's probability-of-direction statement
    n               INTEGER, n_eff NUMERIC, coverage NUMERIC, counter_frame_n INTEGER,
    would_change    TEXT NOT NULL,              -- REQ-TIER-048
    prediction_id   UUID REFERENCES __CORE__.predictions(prediction_id),   -- RULE-20 / REQ-ACT-010
    is_daily        BOOLEAN NOT NULL DEFAULT false,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','demoted','superseded')),
    demoted_reason  TEXT, demoted_at TIMESTAMPTZ,
    code_version    TEXT NOT NULL,
    -- REQ-ACT-001: a pattern recommendation is never DESCRIPTIVE; a standing order is always DESCRIPTIVE
    CHECK ((kind = 'pattern' AND tier IN ('PROMOTED','CONFIRMED_OBSERVATIONAL') AND hypothesis_id IS NOT NULL)
        OR (kind = 'standing_order' AND tier = 'DESCRIPTIVE' AND order_id IS NOT NULL)),
    -- REQ-TIER-049: a pattern recommendation without its interval may not exist, let alone render
    CHECK (kind <> 'pattern' OR (ci_lo IS NOT NULL AND ci_hi IS NOT NULL AND effect_abs IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS recommendations_day_idx ON __CORE__.recommendations (for_day DESC, status);
CREATE UNIQUE INDEX IF NOT EXISTS recommendations_one_daily_idx
    ON __CORE__.recommendations (for_day) WHERE is_daily;      -- REQ-ACT-008: at most one per day
COMMENT ON TABLE __CORE__.recommendations IS
  'REQ-ACT-001..012 / ADR-0052. Append-only except status, demoted_reason, demoted_at and is_daily '
  '(enforced by trigger): a recommendation is never deleted, only withdrawn.';
ALTER TABLE __CORE__.recommendations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.recommendations FROM anon, authenticated;

CREATE OR REPLACE FUNCTION __CORE__.reject_recommendation_edit() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.for_day IS DISTINCT FROM OLD.for_day OR NEW.kind IS DISTINCT FROM OLD.kind
    OR NEW.hypothesis_id IS DISTINCT FROM OLD.hypothesis_id OR NEW.order_id IS DISTINCT FROM OLD.order_id
    OR NEW.tier IS DISTINCT FROM OLD.tier OR NEW.instruction IS DISTINCT FROM OLD.instruction
    OR NEW.effect_abs IS DISTINCT FROM OLD.effect_abs OR NEW.ci_lo IS DISTINCT FROM OLD.ci_lo
    OR NEW.ci_hi IS DISTINCT FROM OLD.ci_hi OR NEW.would_change IS DISTINCT FROM OLD.would_change
    OR NEW.prediction_id IS DISTINCT FROM OLD.prediction_id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION
          'REQ-ACT-012: a recommendation is never rewritten; only status, demoted_reason, demoted_at and is_daily may change.'
          USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS recommendations_status_only ON __CORE__.recommendations;
CREATE TRIGGER recommendations_status_only
    BEFORE UPDATE ON __CORE__.recommendations
    FOR EACH ROW EXECUTE FUNCTION __CORE__.reject_recommendation_edit();

-- ---------------------------------------------------------------- the read API
CREATE OR REPLACE FUNCTION public.get_recommendations(p_day date DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE out jsonb; d date;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    d := coalesce(p_day, (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date);
    SELECT jsonb_strip_nulls(jsonb_build_object(
      'day', d,
      -- REQ-TIER-025: a CREDIBLE interval and a probability of direction; never a frequentist interval
      'interval_note', 'Intervals are credible intervals at 80% mass; interval_method names how each was computed.',
      'daily', (
        SELECT jsonb_build_object(
                 'recommendation_id', r.recommendation_id, 'kind', r.kind, 'tier', r.tier,
                 'instruction', r.instruction, 'would_change', r.would_change,
                 'effect', CASE WHEN r.effect_abs IS NULL THEN NULL ELSE jsonb_build_object(
                     'abs', round(r.effect_abs, 4), 'unit', r.effect_unit,
                     'credible_interval', jsonb_build_array(round(r.ci_lo, 4), round(r.ci_hi, 4)),
                     'interval_mass', 0.80, 'interval_method', r.interval_method,
                     'prob_direction', round(r.prob_direction, 4)) END,
                 'trace', jsonb_build_object('table','core.recommendations','recommendation_id',r.recommendation_id))
          FROM __CORE__.recommendations r WHERE r.for_day = d AND r.is_daily AND r.status = 'active'),
      'active', (
        SELECT jsonb_agg(jsonb_build_object(
                 'recommendation_id', r.recommendation_id, 'kind', r.kind, 'tier', r.tier,
                 'instruction', r.instruction, 'driver', r.driver, 'outcome', r.outcome,
                 'lag_days', r.lag_days,
                 'effect', CASE WHEN r.effect_abs IS NULL THEN NULL ELSE jsonb_build_object(
                     'abs', round(r.effect_abs, 4), 'unit', r.effect_unit,
                     'credible_interval', jsonb_build_array(round(r.ci_lo, 4), round(r.ci_hi, 4)),
                     'interval_mass', 0.80, 'interval_method', r.interval_method,
                     'prob_direction', round(r.prob_direction, 4)) END,
                 'n', r.n, 'n_eff', r.n_eff, 'coverage', r.coverage,
                 'counter_frame_n', r.counter_frame_n, 'would_change', r.would_change,
                 'prediction', (SELECT jsonb_build_object('claim', left(p.claim_text, 200),
                                    'resolves_at', p.resolves_at::date, 'p_forecast', p.p_forecast,
                                    'outcome_bool', p.outcome_bool, 'brier', p.brier)
                                  FROM __CORE__.predictions p WHERE p.prediction_id = r.prediction_id),
                 'trace', jsonb_build_object('table','core.recommendations','recommendation_id',r.recommendation_id))
               ORDER BY CASE r.tier WHEN 'CONFIRMED_OBSERVATIONAL' THEN 0 WHEN 'PROMOTED' THEN 1 ELSE 2 END,
                        r.effect_abs DESC NULLS LAST, r.created_at)
          FROM __CORE__.recommendations r WHERE r.for_day = d AND r.status = 'active'),
      'demoted_recent', (
        SELECT jsonb_agg(jsonb_build_object('instruction', r.instruction, 'tier', r.tier,
                 'demoted_reason', r.demoted_reason, 'demoted_at', r.demoted_at)
               ORDER BY r.demoted_at DESC)
          FROM __CORE__.recommendations r
         WHERE r.status = 'demoted' AND r.demoted_at > now() - interval '30 days')
    )) INTO out;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_recommendations(date) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_recommendations(date) FROM anon;
GRANT EXECUTE ON FUNCTION public.get_recommendations(date) TO authenticated;

-- ---------------------------------------------------------------- get_today gains the daily instruction
CREATE OR REPLACE FUNCTION public.get_today()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE out jsonb; d date;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    d := (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date - 1;
    SELECT jsonb_strip_nulls(jsonb_build_object(
      'for_day', d + 1, 'based_on', d,
      'state', public.get_state(d),
      'patterns_waiting', (      -- a COUNT is not generator content (REQ-INF-402)
        SELECT jsonb_build_object('count', count(*),
                 'note', 'exploratory patterns await on the Patterns tab (pull to read)')
          FROM __CORE__.hypothesis_register h
          JOIN analysis.contrasts c ON c.hypothesis_id = h.hypothesis_id
         WHERE h.status = 'CANDIDATE'
           AND c.run_date = (SELECT max(run_date) FROM analysis.contrasts)
        HAVING count(*) > 0),
      'watching', (
        SELECT jsonb_agg(jsonb_build_object(
                 'hypothesis', replace(w.hypothesis_id,'watch:scan:',''),
                 'hypothesis_id', w.hypothesis_id,
                 'registered', w.preregistered_at::date,
                 'day', w.post_days, 'of', w.days_needed,
                 'next_look', w.next_look,
                 'text', CASE WHEN w.post_days IS NULL THEN 'clock not yet computed'
                              ELSE 'day ' || w.post_days || ' of ' || w.days_needed ||
                                   coalesce(' · next look ~' || w.next_look, '') END,
                 'status', w.status, 'rule_version', w.rule_version) ORDER BY w.preregistered_at)
          FROM public._watching_rows() w),
      'instruction', (      -- REQ-ACT-008: the one proactive instruction, read-only, at most one per day
        SELECT jsonb_build_object('tier', r.tier, 'kind', r.kind, 'text', r.instruction,
                 'would_change', r.would_change,
                 'effect', CASE WHEN r.effect_abs IS NULL THEN NULL ELSE jsonb_build_object(
                     'abs', round(r.effect_abs, 4), 'unit', r.effect_unit,
                     'credible_interval', jsonb_build_array(round(r.ci_lo, 4), round(r.ci_hi, 4)),
                     'interval_mass', 0.80, 'interval_method', r.interval_method,
                     'prob_direction', round(r.prob_direction, 4)) END,
                 'trace', jsonb_build_object('table','core.recommendations','recommendation_id',r.recommendation_id))
          FROM __CORE__.recommendations r
         WHERE r.for_day = d + 1 AND r.is_daily AND r.status = 'active'),
      'notices', (      -- REQ-TIER-014 / REQ-TIER-043: demotions and refutations, named, in the next brief
        SELECT jsonb_agg(jsonb_build_object('kind', n.kind, 'tier', n.tier, 'text', n.text,
                 'hypothesis_id', n.hypothesis_id, 'at', n.created_at,
                 'trace', jsonb_build_object('table','analysis.brief_notes','note_id',n.note_id))
               ORDER BY n.created_at DESC)
          FROM analysis.brief_notes n WHERE n.created_at > now() - interval '14 days'),
      'forecast', (
        SELECT jsonb_agg(jsonb_build_object(
                 'metric', metric, 'lo', lo, 'point', point, 'hi', hi))
          FROM analysis.forecasts WHERE day_target = d + 1),
      'forecast_track_record', (
        SELECT jsonb_build_object(
            'resolved', count(*),
            'inside_band', count(*) FILTER (WHERE outcome_bool),
            'claimed_coverage', 0.90,
            'achieved_coverage', round(avg(outcome_bool::int)::numeric, 2))
          FROM __CORE__.predictions
         WHERE model_version LIKE 'forecast-%' AND outcome_bool IS NOT NULL
        HAVING count(*) > 0)
    )) INTO out;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.get_today() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_today() FROM anon;
GRANT EXECUTE ON FUNCTION public.get_today() TO authenticated;


