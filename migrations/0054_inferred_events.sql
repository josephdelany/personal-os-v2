-- 0054_inferred_events.sql — B14R step 3-4: reconstructed events (REQ-REC-005..012).
--
-- WHAT THIS IS FOR. An atom is something a sensor or a source recorded. A reconstructed
-- event is something the system CONCLUDED happened — "he ate at that restaurant", "that
-- was a lifting session" — from evidence that never states it directly. The two must not
-- share a table, a lane, or a vocabulary, because the entire failure mode of this feature
-- is a conclusion that reads like an observation six months later (INV-5, RULE-05).
--
-- The constraints below are the unit. A reconstruction engine that stores its output in a
-- permissive table is a system that will eventually assert a plausible story with the same
-- typography as a measured fact.

-- REQ-REC-006. Methods are REGISTERED, versioned, and declare what they need before they
-- run. A model may propose a candidate; it never invents the rule, selects the window, or
-- mints a number (RULE-11, RULE-13).
CREATE TABLE IF NOT EXISTS config.reconstruction_methods (
    method_key        TEXT NOT NULL,
    method_version    INTEGER NOT NULL,
    event_family      TEXT NOT NULL,        -- 'meal', 'training_session', 'outing', ...
    required_evidence TEXT[] NOT NULL,      -- evidence kinds without which it may not run
    permissible_outputs TEXT[] NOT NULL,    -- what it is allowed to conclude
    temporal_specification TEXT NOT NULL
        CHECK (temporal_specification IN ('instant','interval','subject_day')),
    retired_at        TIMESTAMPTZ,
    note              TEXT NOT NULL,
    PRIMARY KEY (method_key, method_version),
    CONSTRAINT method_declares_its_inputs  CHECK (cardinality(required_evidence) > 0),
    CONSTRAINT method_declares_its_outputs CHECK (cardinality(permissible_outputs) > 0)
);
REVOKE ALL ON config.reconstruction_methods FROM anon, authenticated;

-- REQ-REC-005. The inferred event itself.
CREATE TABLE IF NOT EXISTS __CORE__.inferred_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_family    TEXT NOT NULL,
    method_key      TEXT NOT NULL,
    method_version  INTEGER NOT NULL,

    -- Event time and knowledge time are DIFFERENT CLOCKS and conflating them is how a
    -- replayed answer silently improves. `event_time_*` bounds when it happened;
    -- `knowledge_time` is when this system could first have concluded it (RULE-04, INV-4).
    event_time_from TIMESTAMPTZ NOT NULL,
    event_time_to   TIMESTAMPTZ NOT NULL,
    subject_day     DATE NOT NULL,
    knowledge_time  TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- RULE-16 / REQ-TIER-016. The same tier vocabulary as everything else; a reconstruction
    -- does not get a private confidence language.
    tier            TEXT NOT NULL,

    -- REQ-REC-009. Three-valued, like RULE-07. 'unknown' is the answer when coverage cannot
    -- establish that the event did NOT happen. Absence of a record is never absence of the
    -- event.
    presence        TEXT NOT NULL CHECK (presence IN ('occurred','did_not_occur','unknown')),

    -- REQ-REC-010. THE CENTRAL CONSTRAINT OF THIS FILE. A rule score and a probability are
    -- different objects. A number here without a stored calibration is a made-up confidence
    -- wearing a percent sign, and it would propagate into every consumer as if measured.
    rule_score      NUMERIC,                -- uncalibrated ranking; never rendered as a chance
    probability     NUMERIC CHECK (probability IS NULL OR (probability >= 0 AND probability <= 1)),
    calibration_ref TEXT,                   -- the stored calibration that earned the number

    -- REQ-REC-007. An empty alternative set is a STATEMENT, not a blank. Either alternatives
    -- were considered, or the row says on its face that no generator applied.
    alternatives            JSONB NOT NULL DEFAULT '[]'::jsonb,
    no_alternative_generator BOOLEAN NOT NULL DEFAULT false,
    unresolved_ambiguity    TEXT,

    -- REQ-REC-011. Append-only revision. A later interpretation supersedes an earlier one;
    -- the earlier one and the evidence available at its cutoff stay readable.
    supersedes      UUID REFERENCES __CORE__.inferred_events(event_id),
    author          TEXT NOT NULL CHECK (author IN ('engine','human')),
    note            TEXT,

    FOREIGN KEY (method_key, method_version)
        REFERENCES config.reconstruction_methods(method_key, method_version),

    CONSTRAINT event_time_is_ordered CHECK (event_time_from <= event_time_to),

    -- RULE-04. Nothing is concluded before its own evidence could exist.
    CONSTRAINT knowledge_follows_the_event CHECK (knowledge_time >= event_time_from),

    -- REQ-REC-010, enforced: a probability requires the calibration that produced it.
    CONSTRAINT probability_requires_calibration
        CHECK (probability IS NULL OR calibration_ref IS NOT NULL),

    -- ...and a rule score may never be quietly read as one.
    CONSTRAINT score_is_not_a_probability
        CHECK (rule_score IS NULL OR probability IS NULL OR calibration_ref IS NOT NULL),

    -- REQ-REC-007: silence about alternatives is not permitted.
    CONSTRAINT alternatives_are_disclosed
        CHECK (jsonb_array_length(alternatives) > 0 OR no_alternative_generator),

    -- REQ-REC-009: an unknown event cannot carry a confidence in having happened.
    CONSTRAINT unknown_carries_no_score
        CHECK (presence <> 'unknown' OR (rule_score IS NULL AND probability IS NULL))
);
REVOKE ALL ON __CORE__.inferred_events FROM anon, authenticated;

-- REQ-REC-007/008. The evidence, with its ORIGIN GROUP. Two rows copied from one receipt
-- are one piece of evidence; counting them twice is how a reconstruction talks itself into
-- confidence. `origin_group` is what makes independence countable instead of assumed.
CREATE TABLE IF NOT EXISTS __CORE__.event_evidence (
    event_id     UUID NOT NULL REFERENCES __CORE__.inferred_events(event_id) ON DELETE RESTRICT,
    atom_id      UUID REFERENCES __CORE__.atoms(id),
    external_ref TEXT,
    stance       TEXT NOT NULL CHECK (stance IN ('supports','contradicts')),
    origin_group TEXT NOT NULL,
    recorded_at  TIMESTAMPTZ NOT NULL,
    note         TEXT,
    -- One reference per (event, origin). A PRIMARY KEY cannot be an expression, so the
    -- reference is materialised: an atom-backed and a text-backed citation are the same
    -- kind of thing and must collide the same way.
    evidence_ref TEXT GENERATED ALWAYS AS (coalesce(atom_id::text, external_ref)) STORED,
    PRIMARY KEY (event_id, origin_group, evidence_ref),
    CONSTRAINT evidence_points_at_something
        CHECK (atom_id IS NOT NULL OR external_ref IS NOT NULL)
);
REVOKE ALL ON __CORE__.event_evidence FROM anon, authenticated;

-- REQ-REC-008 made queryable: independent support is DISTINCT origin groups, not row count.
CREATE OR REPLACE VIEW __CORE__.v_event_independence AS
SELECT e.event_id,
       count(*) FILTER (WHERE ev.stance = 'supports')                       AS supporting_rows,
       count(DISTINCT ev.origin_group) FILTER (WHERE ev.stance = 'supports') AS independent_support,
       count(*) FILTER (WHERE ev.stance = 'contradicts')                     AS contradicting_rows,
       count(DISTINCT ev.origin_group) FILTER (WHERE ev.stance = 'contradicts') AS independent_contradiction
  FROM __CORE__.inferred_events e
  LEFT JOIN __CORE__.event_evidence ev USING (event_id)
 GROUP BY e.event_id;
REVOKE ALL ON __CORE__.v_event_independence FROM anon, authenticated;

-- RULE-02 / INV-2: append-only, like every other record of what happened.
CREATE OR REPLACE FUNCTION __CORE__.inferred_events_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'RULE-02: % on inferred_events is forbidden; supersede the row instead',
        TG_OP USING ERRCODE = '42501';
END $$;
DROP TRIGGER IF EXISTS inferred_events_append_only ON __CORE__.inferred_events;
CREATE TRIGGER inferred_events_append_only BEFORE UPDATE OR DELETE
    ON __CORE__.inferred_events FOR EACH ROW EXECUTE FUNCTION __CORE__.inferred_events_append_only();

-- REQ-REC-011. Human corrections retain precedence: the engine may revise itself, but it may
-- not overwrite Joe. Without this the next scheduled run silently reverts every correction
-- he ever made, and the revision history would show it as an improvement.
CREATE OR REPLACE FUNCTION __CORE__.check_supersede_precedence() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE prior_author text;
BEGIN
    IF NEW.supersedes IS NULL THEN RETURN NEW; END IF;
    SELECT author INTO prior_author FROM __CORE__.inferred_events WHERE event_id = NEW.supersedes;
    IF prior_author = 'human' AND NEW.author <> 'human' THEN
        RAISE EXCEPTION
            'REQ-REC-011: the engine may not supersede a human interpretation (event %)',
            NEW.supersedes USING ERRCODE = '42501';
    END IF;
    -- RULE-04: a revision knows more, so it cannot be dated before what it replaces.
    IF NEW.knowledge_time < (SELECT knowledge_time FROM __CORE__.inferred_events
                              WHERE event_id = NEW.supersedes) THEN
        RAISE EXCEPTION 'RULE-04: a superseding interpretation cannot predate the one it replaces'
            USING ERRCODE = '22007';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS inferred_events_supersede_precedence ON __CORE__.inferred_events;
CREATE TRIGGER inferred_events_supersede_precedence BEFORE INSERT
    ON __CORE__.inferred_events FOR EACH ROW EXECUTE FUNCTION __CORE__.check_supersede_precedence();

-- REQ-REC-004/013. The current interpretation of each event: the head of every supersede
-- chain. Consumers read this, never the raw table, so a corrected event stops being read.
CREATE OR REPLACE VIEW __CORE__.v_current_events AS
SELECT e.* FROM __CORE__.inferred_events e
 WHERE NOT EXISTS (SELECT 1 FROM __CORE__.inferred_events s WHERE s.supersedes = e.event_id);
REVOKE ALL ON __CORE__.v_current_events FROM anon, authenticated;
