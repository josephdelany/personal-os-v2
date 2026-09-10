-- 0063_micro_trials.sql — randomized micro-trials (REQ-INF-200..217; ADR-0104).
-- The arithmetic is in tools/engines/trials.py; this is where a trial is PRE-REGISTERED, and
-- pre-registration is only meaningful if the database refuses to let it change afterwards.
--
-- WHY THIS TABLE IS STRICTER THAN THE OTHERS. A randomized trial outranks every observational
-- finding on RULE-16's ladder, and it is the only thing in this system that asks Joe to change
-- his behaviour for six weeks. Both of those make it the most attractive thing to fudge: move
-- the outcome after seeing the data and an EXPERIMENTAL claim appears out of a null result.
-- REQ-INF-213 forbids exactly that, and a rule enforced only in the engine is enforced only
-- for the one caller that goes through the engine.

CREATE TABLE IF NOT EXISTS analysis.trials (
    trial_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exposure                TEXT NOT NULL REFERENCES __CORE__.metric_registry(metric_key),
    outcome                 TEXT NOT NULL REFERENCES __CORE__.metric_registry(metric_key),
    block_length_days       INTEGER NOT NULL CHECK (block_length_days > 0),
    n_blocks_planned        INTEGER NOT NULL CHECK (n_blocks_planned >= 2),
    washout_days            INTEGER NOT NULL DEFAULT 0 CHECK (washout_days >= 0),
    washout_justification   TEXT NOT NULL,
    randomization_seed      TEXT NOT NULL,
    blinded                 BOOLEAN NOT NULL,
    blinding_note           TEXT,
    primary_outcome_metric  TEXT NOT NULL REFERENCES __CORE__.metric_registry(metric_key),
    analysis_method         TEXT NOT NULL,
    mde_sd                  NUMERIC NOT NULL CHECK (mde_sd > 0),
    assumed_rho             NUMERIC NOT NULL DEFAULT 0,
    computed_power          NUMERIC NOT NULL,
    preregistered_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at              TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    declined_at             TIMESTAMPTZ,

    -- REQ-INF-203. A block no longer than the washout means each block begins before the
    -- previous exposure wore off: the arms bleed together and the contrast is diluted toward
    -- zero. That is a bias TOWARD the null, so it reads as a clean negative result rather
    -- than as a broken design, which is the worst way for a design fault to present.
    CONSTRAINT block_must_outlast_the_washout CHECK (block_length_days > washout_days),
    -- REQ-INF-206. Below six weeks of blocks the result cannot reach EXPERIMENTAL, so the
    -- trial would spend Joe's compliance to buy a tier the observational path already gives.
    CONSTRAINT at_least_six_weeks_of_blocks
        CHECK (block_length_days * n_blocks_planned >= 42),
    -- REQ-INF-208. An underpowered trial is worse than no trial: it costs six weeks and then
    -- returns a null meaning "we could not have seen it" that READS as "it does not work".
    CONSTRAINT power_at_or_above_the_floor CHECK (computed_power >= 0.80),
    -- REQ-INF-205. If it is not blinded, the impossibility must be stated — the note is not
    -- optional decoration, it is the disclosure that travels with the result.
    CONSTRAINT unblinded_states_why CHECK (blinded OR blinding_note IS NOT NULL)
);

COMMENT ON TABLE analysis.trials IS
  'REQ-INF-200/201. The complete pre-registration, written BEFORE the first block is assigned. '
  'A randomized result outranks every observational finding, so this row is the thing most '
  'worth fudging: moving the outcome after seeing the data turns a null into an EXPERIMENTAL '
  'claim. The trigger below makes that impossible rather than merely forbidden.';

-- REQ-INF-202. Append-only by construction: one row per block, drawn once.
CREATE TABLE IF NOT EXISTS analysis.trial_assignments (
    trial_id      UUID NOT NULL REFERENCES analysis.trials(trial_id),
    block_index   INTEGER NOT NULL CHECK (block_index >= 0),
    arm           TEXT NOT NULL CHECK (arm IN ('A', 'B')),
    starts_on     DATE NOT NULL,
    ends_on       DATE NOT NULL,
    assigned_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trial_id, block_index),
    CONSTRAINT block_ends_after_it_starts CHECK (ends_on >= starts_on)
);

COMMENT ON TABLE analysis.trial_assignments IS
  'REQ-INF-202. Drawn from a seeded PRNG at block start and never regenerated. An assignment '
  'that changes when you look at it again is not a randomisation, it is a rewrite of history.';

-- REQ-INF-209. A day Joe did the opposite of his assignment is DATA, not dirt.
CREATE TABLE IF NOT EXISTS analysis.trial_deviations (
    deviation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id       UUID NOT NULL REFERENCES analysis.trials(trial_id),
    block_index    INTEGER NOT NULL,
    day            DATE NOT NULL,
    assigned_arm   TEXT NOT NULL CHECK (assigned_arm IN ('A', 'B')),
    observed_value NUMERIC,
    observed_note  TEXT,
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (trial_id, day),
    FOREIGN KEY (trial_id, block_index)
        REFERENCES analysis.trial_assignments(trial_id, block_index)
);

COMMENT ON TABLE analysis.trial_deviations IS
  'REQ-INF-209/210. The day is RETAINED in the dataset and flagged, never dropped. Dropping it '
  'silently converts an intention-to-treat estimate into a per-protocol one — the substitution '
  'that makes adherence look like efficacy, because the days Joe complied are the days he felt '
  'able to, and those differ from the rest in ways the exposure did not cause.';

-- REQ-INF-213 / REQ-INF-201. The pre-registration columns freeze at the first assignment.
--
-- Deliberately NOT "freeze on insert": a proposed trial Joe has not accepted yet may still be
-- adjusted, and forbidding that would push the editing into a delete-and-recreate cycle that
-- loses the proposal history. The line is the FIRST ASSIGNMENT, because that is the moment
-- randomisation begins and after which any change is retrospective.
CREATE OR REPLACE FUNCTION analysis.trials_freeze_prereg() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE frozen text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM analysis.trial_assignments a WHERE a.trial_id = OLD.trial_id)
    THEN
        RETURN NEW;                      -- not started; still a proposal
    END IF;
    frozen := CASE
        WHEN NEW.exposure               IS DISTINCT FROM OLD.exposure               THEN 'exposure'
        WHEN NEW.outcome                IS DISTINCT FROM OLD.outcome                THEN 'outcome'
        WHEN NEW.primary_outcome_metric IS DISTINCT FROM OLD.primary_outcome_metric THEN 'primary_outcome_metric'
        WHEN NEW.analysis_method        IS DISTINCT FROM OLD.analysis_method        THEN 'analysis_method'
        WHEN NEW.block_length_days      IS DISTINCT FROM OLD.block_length_days      THEN 'block_length_days'
        WHEN NEW.n_blocks_planned       IS DISTINCT FROM OLD.n_blocks_planned       THEN 'n_blocks_planned'
        WHEN NEW.mde_sd                 IS DISTINCT FROM OLD.mde_sd                 THEN 'mde_sd'
        WHEN NEW.randomization_seed     IS DISTINCT FROM OLD.randomization_seed     THEN 'randomization_seed'
        WHEN NEW.preregistered_at       IS DISTINCT FROM OLD.preregistered_at       THEN 'preregistered_at'
        ELSE NULL END;
    IF frozen IS NOT NULL THEN
        RAISE EXCEPTION 'REQ-INF-213: % is frozen once the first block is assigned; a trial '
                        'whose outcome or method can move after randomisation begins is not '
                        'pre-registered', frozen
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $fn$;

DROP TRIGGER IF EXISTS trials_freeze_prereg ON analysis.trials;
CREATE TRIGGER trials_freeze_prereg BEFORE UPDATE ON analysis.trials
    FOR EACH ROW EXECUTE FUNCTION analysis.trials_freeze_prereg();

-- REQ-INF-216. Enforced here as well as in the engine: randomising something Joe only observes
-- would assign an arm nobody can comply with, and `role` already carries the distinction.
CREATE OR REPLACE FUNCTION analysis.trials_exposure_is_a_lever() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE r text;
BEGIN
    SELECT role INTO r FROM __CORE__.metric_registry WHERE metric_key = NEW.exposure;
    IF r IS DISTINCT FROM 'lever' THEN
        RAISE EXCEPTION 'REQ-INF-216: % is marked % in the metric registry; a trial randomises '
                        'something Joe DECIDES', NEW.exposure, coalesce(r, 'unregistered')
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $fn$;

DROP TRIGGER IF EXISTS trials_exposure_is_a_lever ON analysis.trials;
CREATE TRIGGER trials_exposure_is_a_lever BEFORE INSERT OR UPDATE ON analysis.trials
    FOR EACH ROW EXECUTE FUNCTION analysis.trials_exposure_is_a_lever();

REVOKE ALL ON analysis.trials, analysis.trial_assignments, analysis.trial_deviations
    FROM anon, authenticated;
