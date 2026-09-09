-- 0049_ask_core.sql — B11.1: Ask, the deterministic core (REQ-ASK-001..012, 020..032; ADR-0053).
-- DRAFT: B11 is not complete and this migration is not ready for live apply.
-- See docs/adr/0053-ask-deterministic-core.md for remaining work and test scope.
-- A question in, a traced and tiered answer out, with no model anywhere on the path (RULE-15).
--
-- NAME COLLISION, stated rather than worked around: `public.ask(text)` already exists — it belongs to the
-- PREVIOUS build, which is still live and still serving the old PWA (OQ-17). B11 names this RPC `ask`. A
-- two-argument overload with a DEFAULT would make every single-argument call ambiguous and break that app,
-- so this one takes both arguments as REQUIRED: `ask(text, date)` never collides with `ask(text)`.
-- B22 retires the old stack; the default comes back then.
--
-- ONE OWNER (RULE-11/12): the executor exists once, here, in plpgsql. `tools/engines/ask.py` is a thin
-- client that calls it — not a second implementation. B11 asks for "the same logic" in Python; two
-- implementations of one executor is precisely the drift RULE-12 exists to prevent (ADR-0053).

-- ---------------------------------------------------------------- the closed operation registry (REQ-ASK-002/004)
CREATE TABLE IF NOT EXISTS config.operations (
    op           TEXT PRIMARY KEY,
    arity        TEXT NOT NULL,
    description  TEXT NOT NULL,
    tier_ceiling TEXT NOT NULL
);
REVOKE ALL ON config.operations FROM anon, authenticated;
INSERT INTO config.operations (op, arity, description, tier_ceiling) VALUES
 ('insufficient','none','the form an answer takes when coverage floors it below every tier','INSUFFICIENT'),
 ('describe','metric','median, p10-p90, min/max, n, coverage over the range','DESCRIPTIVE'),
 ('trend','metric','first-half vs second-half medians and the 28-day rolling median at range end','DESCRIPTIVE'),
 ('rhythm','metric','weekday medians; highest/lowest weekday','DESCRIPTIVE'),
 ('last','metric','latest value and day, plus days since','DESCRIPTIVE'),
 ('count_days','metric,condition','days where metric satisfies condition over a denominator','DESCRIPTIVE'),
 ('compare','metric,condition','metric on days satisfying condition vs the rest: medians, n each, delta','DESCRIPTIVE'),
 ('contrast','metric,metric','the registered quartile contrast at lag 0; EXPLORATORY unless a finding exists','EXPLORATORY'),
 ('effect','metric,metric','the stored finding for driver->outcome at PROMOTED+; else a refusal','PROMOTED'),
 ('search','text','search_record','DESCRIPTIVE'),
 ('entity','entity','get_entity','DESCRIPTIVE'),
 ('spend','entity','money: total, n, typical week, top merchants over the range','DESCRIPTIVE')
ON CONFLICT (op) DO NOTHING;

-- ---------------------------------------------------------------- the grammar and the templates, in one place
CREATE TABLE IF NOT EXISTS config.ask_grammar (
    priority INTEGER PRIMARY KEY,
    pattern  TEXT NOT NULL,            -- POSIX regex over the lowercased question
    op       TEXT NOT NULL REFERENCES config.operations(op),
    note     TEXT
);
REVOKE ALL ON config.ask_grammar FROM anon, authenticated;
INSERT INTO config.ask_grammar (priority, pattern, op, note) VALUES
 (10, '(how much|how many dollars).*(spend|spent)', 'spend', 'money first: "how much did I spend on X"'),
 (20, '(when did i last|last time i|when was the last)', 'last', NULL),
 (30, 'how many days', 'count_days', NULL),
 (40, '(which day|what day|which weekday|what weekday|day of the week)', 'rhythm', NULL),
 (50, '(going up|going down|improving|getting worse|trending|trend|over time|changed)', 'trend', NULL),
 (60, '(affect|affects|drive|drives|cause|causes|impact|impacts|related to|relate to|do .* affect)', 'effect', NULL),
 (70, '( on days | when i | on the days | when my )', 'compare', NULL),
 (80, '(how (is|are|was|were)|what(''s| is| are) my|show me my|my )', 'describe', NULL)
ON CONFLICT (priority) DO NOTHING;

CREATE TABLE IF NOT EXISTS config.ask_templates (
    op       TEXT NOT NULL REFERENCES config.operations(op),
    tier     TEXT NOT NULL,
    template TEXT NOT NULL,
    PRIMARY KEY (op, tier)
);
REVOKE ALL ON config.ask_templates FROM anon, authenticated;
INSERT INTO config.ask_templates (op, tier, template) VALUES
 ('describe','DESCRIPTIVE','Your {display} was typically {median} {unit} over {range} ({n} of {days} days with data). Your usual range was {p10} to {p90}.'),
 ('trend','DESCRIPTIVE','Your {display} ran {second} {unit} in the second half of {range} against {first} {unit} in the first ({n} of {days} days with data). {rolling_28_clause}'),
 ('rhythm','DESCRIPTIVE','Your {display} was highest on {hi_day} ({hi} {unit}) and lowest on {lo_day} ({lo} {unit}) over {range}.'),
 ('last','DESCRIPTIVE','The last {display} on record is {value} {unit} on {day}, {since} days ago.'),
 -- "{k} of {n}" alone reads as "of the window", and n is the OBSERVED day count: "5 of 10
 -- days over the last 30 days" hid twenty missing days. `describe` states both; this now does
 -- too (RULE-06: coverage is reported alongside every aggregate).
 ('count_days','DESCRIPTIVE','{k} of the {n} days with data over {range} ({n} of {days} days observed).'),
 ('compare','DESCRIPTIVE','Your {display} was typically {a} {unit} on the {n_a} days when {condition}, against {b} {unit} on the other {n_b} days over {range}.'),
 -- NOT "over {range}": the stored contrast covers the scan's own window, not the window the
 -- question asked about, and `analysis.contrasts` does not record that window. The sentence
 -- states what the number actually rests on.
 ('contrast','EXPLORATORY','On your highest-{driver} days, {outcome} ran {delta} {unit} {direction} than on your lowest, across {n_hi} high and {n_lo} low days measured by {window}. This may reflect a pattern; it is exploratory and unverified.'),
 -- PROMOTED does NOT get dose-response phrasing. "per {driver} step" states a rate of
 -- change, and `config.tier_vocabulary` reserves "per" for CONFIRMED_OBSERVATIONAL — the
 -- seeded template and the seeded vocabulary contradicted each other, and RULE-16 says the
 -- language may not run ahead of the tier. A PROMOTED finding survived the specification
 -- curve and hierarchical FDR on post-registration data; it is explicitly "not yet a causal
 -- claim" (0048's own wording), so the sentence states a difference between high and low
 -- days, which is what was actually measured.
 ('effect','PROMOTED','{outcome} appears to differ by {delta} {unit} between your highest and lowest {driver} days. Provisional: registered and watched, not confirmed.'),
 ('effect','CONFIRMED_OBSERVATIONAL','{outcome} runs {delta} {unit} {direction} per {driver} step, adjusted for {adjustment}.'),
 ('search','DESCRIPTIVE','{n} records mention that over {range}.'),
 ('entity','DESCRIPTIVE','{summary}'),
 -- The form an answer takes when coverage floors it below every tier's language. It states
 -- the numbers and what is missing, in vocabulary that claims nothing (RULE-16, RULE-18).
 ('insufficient','INSUFFICIENT','Over {range} there were {n} of {days} days with data for {display} — below what this answer would need. The observations are stored and traceable; the claim is not made.'),
 ('spend','DESCRIPTIVE','Charges matching "{matched_on}" over {range} total {total_out} {currency} across {n_out} charges, about {per_week} {currency} a week. This is {caveat}.')
ON CONFLICT (op, tier) DO NOTHING;

-- ---------------------------------------------------------------- the per-tier vocabulary (REQ-TIER-020 / REQ-NAR-020)
CREATE TABLE IF NOT EXISTS config.tier_vocabulary (tier TEXT NOT NULL, term TEXT NOT NULL, PRIMARY KEY (tier, term));
REVOKE ALL ON config.tier_vocabulary FROM anon, authenticated;
INSERT INTO config.tier_vocabulary (tier, term) VALUES
 ('DESCRIPTIVE','ran'), ('DESCRIPTIVE','was'), ('DESCRIPTIVE','were'), ('DESCRIPTIVE','median'),
 ('DESCRIPTIVE','typically'), ('DESCRIPTIVE','on'), ('DESCRIPTIVE','highest'), ('DESCRIPTIVE','lowest'),
 ('EXPLORATORY','may'), ('EXPLORATORY','might'), ('EXPLORATORY','exploratory'), ('EXPLORATORY','unverified'),
 ('EXPLORATORY','candidate'), ('EXPLORATORY','a generator flagged'),
 ('PROMOTED','appears'), ('PROMOTED','provisional'), ('PROMOTED','consistent with'), ('PROMOTED','watched'),
 ('CONFIRMED_OBSERVATIONAL','runs'), ('CONFIRMED_OBSERVATIONAL','increases'), ('CONFIRMED_OBSERVATIONAL','decreases'),
 ('CONFIRMED_OBSERVATIONAL','per'), ('CONFIRMED_OBSERVATIONAL','adjusted for'),
 ('EXPERIMENTAL','caused'), ('EXPERIMENTAL','causes')
ON CONFLICT DO NOTHING;

-- the stored strings, verbatim (REQ-ASK-003/023/031, REQ-ASK-028). config.strings already exists (0047).
INSERT INTO config.strings (key, value, note) VALUES
 ('refusal_untracked','I do not track that.','REQ-ASK-003'),
 ('refusal_insufficient','We do not have enough to answer this.','REQ-ASK-023 / RULE-18'),
 ('refusal_unmappable','I cannot compute that.','REQ-ASK-031, verbatim from the spec')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------- the question and computation ledger
CREATE TABLE IF NOT EXISTS __CORE__.questions (
    question_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asked_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    text        TEXT NOT NULL,
    planner     TEXT NOT NULL CHECK (planner IN ('deterministic','workers_ai')),
    plan        JSONB,
    iterations  INTEGER NOT NULL DEFAULT 1,
    answer      JSONB,
    refusal     TEXT,
    tier        TEXT
);
REVOKE ALL ON __CORE__.questions FROM anon, authenticated;
ALTER TABLE __CORE__.questions ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS __CORE__.computations (
    computation_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id         UUID NOT NULL REFERENCES __CORE__.questions(question_id),
    plan                JSONB NOT NULL,
    as_of               DATE NOT NULL,
    result              JSONB NOT NULL,      -- every numeral the answer may use lives here (REQ-ASK-009)
    observation_keys    JSONB NOT NULL,      -- the rows behind the result (REQ-ASK-011)
    coverage            JSONB NOT NULL,
    tier                TEXT NOT NULL,
    insufficiency_reason TEXT,
    executed_at         TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    code_version        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS computations_question_idx ON __CORE__.computations (question_id);
REVOKE ALL ON __CORE__.computations FROM anon, authenticated;
ALTER TABLE __CORE__.computations ENABLE ROW LEVEL SECURITY;

-- the render-refusal sink already exists (0047); Ask needs to name the question that failed
ALTER TABLE analysis.render_violations ADD COLUMN IF NOT EXISTS question_id UUID;

-- ---------------------------------------------------------------- the point-in-time panel (REQ-INF-108)
-- The spec names `f_daily_panel(as_of)`; this is it. `analysis.panel` carries no ingestion timestamp, so
-- the cutoff it can honour is the SUBJECT-DAY one only. Stated here so nothing downstream mistakes it for
-- the bitemporal function REQ-INF-108 ultimately wants (that needs a recorded_at on the panel — OQ-45).
CREATE OR REPLACE FUNCTION analysis.f_daily_panel(p_as_of date)
RETURNS TABLE (day date, metric text, value numeric)
LANGUAGE sql STABLE
AS $fn$
    SELECT day, metric, value FROM analysis.panel WHERE day <= p_as_of
$fn$;
COMMENT ON FUNCTION analysis.f_daily_panel(date) IS
  'REQ-INF-108 as far as the panel allows: a subject-day cutoff, NOT a bitemporal one. analysis.panel has no '
  'recorded_at, so a value revised after as_of is still returned. OQ-45.';

-- ---------------------------------------------------------------- metric resolution (REQ-ASK-003)
CREATE OR REPLACE FUNCTION public._ask_resolve_metric(p_text text, p_exclude text DEFAULT NULL)
RETURNS TABLE (metric text, display text, unit text, sim real)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    WITH cand AS (
        SELECT mr.metric_key AS metric, mr.display_name AS display, mr.unit FROM __CORE__.metric_registry mr
        UNION
        SELECT dm.metric, dm.display_name, dm.unit FROM config.domain_metrics dm
          JOIN __CORE__.metric_registry mr ON mr.metric_key = dm.metric
        UNION
        SELECT d.hero_metric, d.display_name, mr.unit FROM config.domains d
          JOIN __CORE__.metric_registry mr ON mr.metric_key = d.hero_metric
    ), scored AS (
        SELECT c.metric, c.display, c.unit,
               greatest(extensions.similarity(lower(c.display), lower(p_text)),
                        extensions.similarity(lower(replace(replace(c.metric,'_',' '),'.',' ')), lower(p_text))) AS sim
          FROM cand c
         WHERE p_exclude IS NULL OR c.metric <> p_exclude
    )
    SELECT s.metric, mr.display_name, mr.unit, max(s.sim)
      FROM scored s JOIN __CORE__.metric_registry mr ON mr.metric_key = s.metric
     GROUP BY s.metric, mr.display_name, mr.unit ORDER BY max(s.sim) DESC, s.metric LIMIT 3
$fn$;
REVOKE ALL ON FUNCTION public._ask_resolve_metric(text, text) FROM PUBLIC, anon, authenticated;

-- Formatting is registered; a missing rounding rule preserves the computed
-- numeric value instead of inventing a decimal precision (REQ-NAR-015).
CREATE OR REPLACE FUNCTION public._ask_round(p_value numeric, p_metric text)
RETURNS numeric LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT CASE WHEN dm.rounding IS NOT NULL THEN round(p_value, dm.rounding)
                WHEN mr.rounding_step > 0 THEN round(p_value / mr.rounding_step) * mr.rounding_step
                ELSE p_value END
      FROM __CORE__.metric_registry mr
      LEFT JOIN LATERAL (SELECT d.rounding FROM config.domain_metrics d WHERE d.metric = mr.metric_key
                         ORDER BY CASE d.role WHEN 'hero' THEN 0 ELSE 1 END, d.domain_key LIMIT 1) dm ON true
     WHERE mr.metric_key = p_metric
$fn$;
REVOKE ALL ON FUNCTION public._ask_round(numeric, text) FROM PUBLIC, anon, authenticated;

-- Preserve the template slot for each occurrence: the same numeral can mean
-- a metric value in one slot and a day count in another (REQ-ASK-009).
CREATE OR REPLACE FUNCTION public._ask_numerals(p_template text, p_result jsonb, p_id uuid)
RETURNS jsonb LANGUAGE sql IMMUTABLE SET search_path = ''
AS $fn$
    WITH pieces AS (
        SELECT part[1] AS part, ordinality AS piece_order
          FROM regexp_matches(p_template, '(\{[a-z_0-9]+\}|[^{}]+)', 'g') WITH ORDINALITY AS p(part, ordinality)
    ), slots AS (
        SELECT *, CASE WHEN left(part,1) = '{' THEN
            CASE part WHEN '{range}' THEN 'range_label'
                      ELSE substring(part FROM 2 FOR length(part)-2) END END AS key
          FROM pieces
    ), rendered AS (
        SELECT *, CASE WHEN key IS NULL THEN part ELSE coalesce(p_result->>key, '') END AS value,
            -- Day counts are days, whatever the metric's unit is. The list was written for
            -- the descriptive ops and never extended, so a contrast's n_hi/n_lo — plain day
            -- counts — were labelled with the driver's unit and shipped in the numerals
            -- payload that RULE-14's numeral-template rendering depends on.
            CASE WHEN key IN ('n','days','k','n_a','n_b','since','n_hi','n_lo',
                              'n_first','n_second','n_out','n_in','rolling_28_n',
                              'n_condition_unknown','n_condition_missing','lag_days',
                              'rolling_28_window_days','weeks') THEN 'days'
                 WHEN key IN ('computed_on','window','first_day','last_day','day',
                              'rolling_28_from','rolling_28_to') THEN 'date'
                 WHEN key IN ('total','total_out','total_in','per_week','threshold')
                      THEN coalesce(p_result->>'currency', p_result->>'unit')
                 WHEN key = 'range_label' THEN CASE WHEN p_result->>'range_label' ~ 'days' THEN 'days' ELSE 'year' END
                 WHEN key = 'day' THEN 'date'
                 ELSE p_result->>'unit' END AS unit
          FROM slots
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object('value', n.num[1], 'unit', r.unit,
              'computation_id', p_id, 'result_keys', CASE WHEN r.key IS NOT NULL THEN jsonb_build_array(r.key)
                  ELSE (SELECT jsonb_agg(kv.key ORDER BY kv.key) FROM jsonb_each_text(p_result) kv
                    WHERE EXISTS (SELECT 1 FROM regexp_matches(kv.value,
                        '([-+]?[0-9]+(?:\.[0-9]+)?)', 'g') AS stored(num) WHERE stored.num[1] = n.num[1])) END)
              ORDER BY r.piece_order, n.ordinality), '[]'::jsonb)
      FROM rendered r, LATERAL regexp_matches(r.value, '([-+]?[0-9]+(?:\.[0-9]+)?)', 'g')
           WITH ORDINALITY AS n(num, ordinality)
$fn$;
REVOKE ALL ON FUNCTION public._ask_numerals(text, jsonb, uuid) FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------- range parsing
CREATE OR REPLACE FUNCTION public._ask_range(p_q text, p_as_of date)
RETURNS TABLE (d_from date, d_to date, label text)
LANGUAGE plpgsql IMMUTABLE SET search_path = ''
AS $fn$
DECLARE
    q text := lower(coalesce(p_q, ''));
    n numeric;
    yr int;
    month_no int;
    matched text[];
BEGIN
    IF p_as_of IS NULL OR NOT isfinite(p_as_of) THEN
        RAISE EXCEPTION 'A finite as_of date is required' USING ERRCODE = '22023';
    END IF;
    d_to := p_as_of;
    IF q ~ '\mtoday\M' THEN d_from := p_as_of; label := 'today';
    ELSIF q ~ '\myesterday\M' THEN
        d_from := p_as_of - 1; d_to := d_from; label := 'yesterday';
    ELSIF q ~ '\mthis week\M' THEN
        d_from := p_as_of - (extract(isodow FROM p_as_of)::int - 1);
        label := 'this week';
    ELSIF q ~ '\mlast week\M' THEN
        d_to := p_as_of - extract(isodow FROM p_as_of)::int;
        d_from := d_to - 6; label := 'last week';
    ELSIF q ~ '\mthis month\M' THEN
        d_from := make_date(extract(year FROM p_as_of)::int, extract(month FROM p_as_of)::int, 1);
        label := 'this month';
    ELSIF q ~ '\mlast month\M' THEN
        d_to := make_date(extract(year FROM p_as_of)::int, extract(month FROM p_as_of)::int, 1) - 1;
        d_from := make_date(extract(year FROM d_to)::int, extract(month FROM d_to)::int, 1);
        label := 'last month';
    ELSIF q ~ '\mthis year\M' THEN
        d_from := make_date(extract(year FROM p_as_of)::int, 1, 1); label := 'this year';
    ELSIF q ~ '\mlast [+-]?[0-9]+([.][0-9]+)? days?\M' THEN
        matched := regexp_match(q, '\mlast ([+-]?[0-9]+([.][0-9]+)?) days?\M');
        n := matched[1]::numeric;
        IF n < 1 OR n <> trunc(n) OR n > 2147483647 THEN
            RAISE EXCEPTION 'Day count must be a positive integer in the supported date range'
                USING ERRCODE = '22023';
        END IF;
        d_from := p_as_of - (n::int - 1); label := 'the last ' || n::int || ' days';
    ELSIF q ~ '\msince\M' THEN
        matched := regexp_match(q,
            '\msince (january|february|march|april|may|june|july|august|september|october|november|december)( ([0-9]{4}))?\M[?.!]?\s*$');
        IF matched IS NULL THEN
            RAISE EXCEPTION 'Use since followed by a month name and optional year'
                USING ERRCODE = '22023';
        END IF;
        month_no := array_position(ARRAY['january','february','march','april','may','june',
                                        'july','august','september','october','november','december'], matched[1]);
        yr := coalesce(matched[3]::int, extract(year FROM p_as_of)::int);
        IF matched[3] IS NULL AND month_no > extract(month FROM p_as_of)::int THEN yr := yr - 1; END IF;
        d_from := make_date(yr, month_no, 1);
        label := 'since ' || initcap(matched[1]) || ' ' || yr;
    ELSIF q ~ '\min [0-9]{4}\M' THEN
        yr := (regexp_match(q, '\min ([0-9]{4})\M'))[1]::int;
        d_from := make_date(yr, 1, 1); d_to := least(p_as_of, make_date(yr, 12, 31));
        label := yr::text;
    ELSIF q ~ '\min [0-9]' THEN
        RAISE EXCEPTION 'Use a four-digit calendar year' USING ERRCODE = '22023';
    ELSE
        d_from := p_as_of - 89; label := 'the last 90 days';
    END IF;
    IF d_from > d_to THEN
        RAISE EXCEPTION 'Date range begins after as_of' USING ERRCODE = '22023';
    END IF;
    RETURN NEXT;
EXCEPTION WHEN datetime_field_overflow OR numeric_value_out_of_range THEN
    RAISE EXCEPTION 'Date range is outside the supported calendar' USING ERRCODE = '22023';
END $fn$;
REVOKE ALL ON FUNCTION public._ask_range(text, date) FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------- the executor (REQ-ASK-005..012, 020..032)

-- ---------------------------------------------------------------- the condition parser, in one place
-- `count_days` and `compare` both ask "days where this metric satisfies a condition". Parsing
-- that phrase twice is how the two operations drift into disagreeing about what "above the
-- usual range" means, so it is parsed once here and both read the result.
--   direction  'above' | 'below'          (NULL when the phrase is not a condition at all)
--   threshold  a number, or NULL for the band form
--   label      the text the answer template renders
--   band_form  true when the comparison is against the personal band rather than a number
-- A user's subject is data, not a pattern. "spend on %" matched every charge and reported the
-- lot as that merchant's, carrying a caveat that said it may have UNDER-counted. Not injection
-- — the value is parameterised — just a wrong money number with a confident sentence.
CREATE OR REPLACE FUNCTION public._ask_like_escape(p text)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path = '' AS $fn$
    SELECT replace(replace(replace(p, '\\', '\\\\'), '%', '\\%'), '_', '\\_')
$fn$;
REVOKE ALL ON FUNCTION public._ask_like_escape(text) FROM public;

CREATE OR REPLACE FUNCTION public._ask_condition(p_q text)
RETURNS TABLE (direction text, threshold numeric, label text, band_form boolean)
LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $fn$
DECLARE txt text; m text[]; dir text;
BEGIN
    txt := regexp_replace(p_q,
        '\s+(today|yesterday|this (week|month|year)|last [0-9]+ days?|last (week|month)|since .+|in [0-9]{4})[?]?$','');
    txt := trim(txt, ' ?');
    -- More than one comparator means more than one clause, and nothing ties the direction to
    -- the threshold: "above 5000 and below 7" took `above` from the first and `7` from the
    -- last, then answered "above 7" — 20 of 20 days where the truth was 10, at DESCRIPTIVE
    -- tier with no refusal. A condition that cannot be read as ONE comparison is refused.
    IF (SELECT count(*) FROM regexp_matches(txt, '\m(above|below|over|under)\M', 'g')) > 1 THEN
        RETURN QUERY SELECT NULL::text, NULL::numeric, NULL::text, NULL::boolean;
        RETURN;
    END IF;
    dir := (regexp_match(txt, '\m(above|below|over|under)\M'))[1];
    IF dir IS NULL THEN
        RETURN QUERY SELECT NULL::text, NULL::numeric, NULL::text, NULL::boolean;
        RETURN;
    END IF;
    IF dir IN ('over') THEN dir := 'above'; ELSIF dir IN ('under') THEN dir := 'below'; END IF;
    -- A number must be the WHOLE remaining token, so "over 1,000" does not parse as 1 and
    -- "50.5.7" is rejected rather than read as 50.5.
    m := regexp_match(txt, '\m(above|below|over|under)\s+([-+]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)$');
    IF m IS NOT NULL THEN
        RETURN QUERY SELECT dir, replace(m[2], ',', '')::numeric,
                            dir || ' ' || replace(m[2], ',', ''), false;
        RETURN;
    END IF;
    IF txt ~ '\m(above|below|over|under)( (the )?(usual |normal )?(range|band))?$' THEN
        RETURN QUERY SELECT dir, NULL::numeric, dir || ' the usual range', true;
        RETURN;
    END IF;
    -- A comparison phrase that is neither a clean number nor the band form is unsupported.
    -- Falling through to the band form here would silently answer a different question.
    RETURN QUERY SELECT NULL::text, NULL::numeric, NULL::text, NULL::boolean;
END $fn$;
REVOKE ALL ON FUNCTION public._ask_condition(text) FROM public;


-- ---------------------------------------------------------------- tier ordering, in one place
-- RULE-16's ladder as a number, so "is this language above its tier?" is answerable in SQL.
-- INSUFFICIENT sits at the bottom: it is not a rung of the ladder, it is the statement that
-- the ladder cannot be climbed with the evidence available.
CREATE OR REPLACE FUNCTION public._ask_tier_rank(p_tier text)
RETURNS int LANGUAGE sql IMMUTABLE SET search_path = '' AS $fn$
    SELECT CASE p_tier
             WHEN 'INSUFFICIENT'             THEN 0
             WHEN 'DESCRIPTIVE'              THEN 1
             WHEN 'EXPLORATORY'              THEN 2
             WHEN 'CANDIDATE'                THEN 2
             WHEN 'PROMOTED'                 THEN 3
             WHEN 'CONFIRMED_OBSERVATIONAL'  THEN 4
             WHEN 'EXPERIMENTAL'             THEN 5
             ELSE 0 END
$fn$;
REVOKE ALL ON FUNCTION public._ask_tier_rank(text) FROM public;

CREATE OR REPLACE FUNCTION public.ask(p_question text, p_as_of date)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $fn$
<<ask_state>>
DECLARE
    q text; as_of date; qid uuid; cid uuid; op text; r record; rng record;
    m1 record; m2 record; nearest jsonb; res jsonb; cov jsonb; keys jsonb;
    tier text; templ text; answer text; refusal text; med numeric; n_days int; n_have int;
    coverage_min numeric; low_metric text; raise_action text; out jsonb; ins_reason text;
    words text[]; cond_txt text; hit text; term text; metric_text text; entity_text text;
    condition_match text[]; condition_value numeric; condition_direction text; condition_input text;
    cond_band boolean; compare_lag int; cond_metric record; n_outcome_days int;
    n_null_unit int; n_cond_days int; r3 jsonb;
    reverse_finding record; reverse_contrast record; r2 jsonb;
    numeral_valid boolean := true;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    q := lower(trim(coalesce(p_question, '')));
    as_of := coalesce(p_as_of, (now() AT TIME ZONE 'America/New_York' - interval '4 hours')::date - 1);
    INSERT INTO __CORE__.questions (text, planner) VALUES (coalesce(p_question, ''), 'deterministic') RETURNING question_id INTO qid;
    -- RECORD variables have no shape until assigned, even when their fields
    -- would logically be NULL. Every branch may safely inspect these now.
    SELECT NULL::text AS metric, NULL::text AS display, NULL::text AS unit, NULL::real AS sim INTO m1;
    SELECT NULL::text AS metric, NULL::text AS display, NULL::text AS unit, NULL::real AS sim INTO m2;
    SELECT NULL::text AS metric, NULL::text AS display, NULL::text AS unit, NULL::real AS sim INTO cond_metric;
    SELECT NULL::text AS hypothesis_id, NULL::text AS status_to,
           NULL::text AS exposure_metric, NULL::text AS outcome_metric INTO reverse_finding;
    SELECT NULL::text AS driver, NULL::text AS outcome, NULL::date AS run_date INTO reverse_contrast;
    compare_lag := 0;

    -- RULE-26 / REQ-ASK-028: a medical question is answered with the stored referral string, data attached
    SELECT mv.term INTO hit FROM config.medical_vocabulary mv
     WHERE q ~ ('\y' || mv.term || '\y') LIMIT 1;
    IF hit IS NOT NULL THEN
        SELECT value INTO refusal FROM config.strings WHERE key = 'medical_referral';
        UPDATE __CORE__.questions SET refusal = ask_state.refusal, tier = NULL WHERE question_id = qid;
        RETURN jsonb_build_object('question_id', qid, 'refusal', refusal, 'reason', 'medical',
                                  'matched_term', hit, 'tier', NULL);
    END IF;

    BEGIN
        SELECT * INTO rng FROM public._ask_range(q, as_of);
    EXCEPTION WHEN invalid_parameter_value THEN
        SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_unmappable';
        UPDATE __CORE__.questions SET refusal = ask_state.refusal WHERE question_id = qid;
        RETURN jsonb_build_object('question_id', qid, 'refusal', refusal,
            'reason', 'invalid_date_range', 'nearest', jsonb_build_array('my steps last 90 days'));
    END;

    -- op selection from the stored grammar (REQ-ASK-004: nothing outside config.operations can run)
    SELECT g.op INTO op FROM config.ask_grammar g WHERE q ~ g.pattern ORDER BY g.priority LIMIT 1;
    IF op IS NULL THEN op := 'search'; END IF;

    -- metric resolution (REQ-ASK-003)
    IF op IN ('describe','trend','rhythm','last','count_days','compare','effect','contrast') THEN
        -- Match the metric phrase, not grammar/date words that dilute trigram
        -- similarity. The grammar still selects the operation independently.
        metric_text := regexp_replace(q,
            '\s+(today|yesterday|this (week|month|year)|last [0-9]+ days?|last (week|month)|since .+|in [0-9]{4})[?]?$','');
        metric_text := regexp_replace(metric_text,
            '^(how (is|are|was|were) my |what(''s| is| are) my |show me my |my )','');
        IF op = 'trend' THEN
            metric_text := regexp_replace(metric_text, '^(is|has) my ', '');
            metric_text := regexp_replace(metric_text,
                '\s+(going up|going down|improving|getting worse|trending|trend|changed|over time)$', '');
        ELSIF op = 'rhythm' THEN
            metric_text := regexp_replace(metric_text,
                '^(which weekdays?|what weekdays?|which days?|what days?|day of the week) (my )?', '');
        ELSIF op = 'last' THEN
            metric_text := regexp_replace(metric_text,
                '^(when did i last|last time i|when was the last) (log |record |have )?(my )?', '');
        END IF;
        IF op = 'count_days' THEN
            metric_text := regexp_replace(metric_text, '^how many days (was |were |is |are )?(my )?', '');
            metric_text := regexp_replace(metric_text, '\s+(above|below|over|under)\M.*$', '');
        ELSIF op = 'compare' THEN
            -- `compare` is CROSS-METRIC: "my sleep on days when I drink" is sleep (the
            -- outcome) split by drinking (the condition metric). Splitting the outcome by its
            -- OWN value answers a different, nearly meaningless question while looking exactly
            -- as authoritative. The phrase is cut at the connective: before it names the
            -- outcome, after it names the condition metric and its comparison.
            condition_input := (regexp_match(metric_text,
                '\s+(?:on|after)\s+(?:the\s+)?days?\s+(?:when\s+|with\s+|that\s+)?(.*)$'))[1];
            IF condition_input IS NULL THEN
                condition_input := (regexp_match(metric_text, '\s+when\s+(.*)$'))[1];
            END IF;
            -- "after days" compares the outcome on the day FOLLOWING a qualifying day.
            compare_lag := CASE WHEN metric_text ~ '\safter\s+(the\s+)?days?\M' THEN 1 ELSE 0 END;
            metric_text := regexp_replace(metric_text, '\s+(on|after|when)\s+.*$', '');
            metric_text := regexp_replace(metric_text, '^(my )', '');

        ELSIF op IN ('effect','contrast') THEN
            -- "does my steps affect my hrv" -> m1 is the phrase BEFORE the verb; the second
            -- metric is resolved from what is left after m1's display is removed.
            metric_text := regexp_replace(metric_text,
                '^(does|do|is|are|did)\s+(my\s+)?', '');
            metric_text := regexp_replace(metric_text,
                '\s+(affect|affects|drive|drives|cause|causes|impact|impacts|relate to|related to)\M.*$', '');
        END IF;
        metric_text := trim(metric_text, ' ?');
        SELECT * INTO m1 FROM public._ask_resolve_metric(metric_text) LIMIT 1;
        IF m1.sim IS NULL OR m1.sim < 0.35 THEN
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_untracked';
            SELECT jsonb_agg(jsonb_build_object('metric', x.metric, 'display', x.display))
              INTO nearest FROM public._ask_resolve_metric(metric_text) x;
            UPDATE __CORE__.questions SET refusal = ask_state.refusal WHERE question_id = qid;
            RETURN jsonb_build_object('question_id', qid, 'refusal', refusal, 'nearest', nearest, 'tier', NULL);
        END IF;
    END IF;

    -- coverage first (REQ-ASK-021/022/023)
    n_days := (rng.d_to - rng.d_from) + 1;
    IF m1.metric IS NOT NULL THEN
        SELECT count(*) INTO n_have FROM analysis.f_daily_panel(as_of) p
         WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to;
        coverage_min := n_have::numeric / greatest(n_days,1);
        cov := jsonb_build_object(m1.metric, coverage_min);
        IF n_have = 0 THEN                                    -- REQ-ASK-023: the absent form, verbatim
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_insufficient';
            SELECT d.capture_action INTO raise_action FROM config.domain_metrics dm
              JOIN config.domains d ON d.domain_key = dm.domain_key WHERE dm.metric = m1.metric LIMIT 1;
            UPDATE __CORE__.questions SET refusal = ask_state.refusal, tier = 'INSUFFICIENT' WHERE question_id = qid;
            RETURN jsonb_strip_nulls(jsonb_build_object(
                'question_id', qid, 'tier', 'INSUFFICIENT', 'insufficiency_reason', 'metric_absent',
                'refusal', refusal, 'metric', m1.metric, 'display', m1.display,
                'range', jsonb_build_array(rng.d_from, rng.d_to), 'would_raise_it', raise_action));
        END IF;
    END IF;

    -- execute (REQ-ASK-005): one op, in SQL, from the point-in-time panel
    IF op = 'describe' THEN
        SELECT jsonb_build_object(
                 'median', public._ask_round(percentile_cont(0.5) WITHIN GROUP (ORDER BY p.value)::numeric, m1.metric),
                 'p10', public._ask_round(percentile_cont(0.1) WITHIN GROUP (ORDER BY p.value)::numeric, m1.metric),
                 'p90', public._ask_round(percentile_cont(0.9) WITHIN GROUP (ORDER BY p.value)::numeric, m1.metric),
                 'min', public._ask_round(min(p.value), m1.metric), 'max', public._ask_round(max(p.value), m1.metric),
                 'n', count(*), 'days', n_days)
          INTO res FROM analysis.f_daily_panel(as_of) p
         WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to;
    ELSIF op = 'trend' THEN
        SELECT jsonb_build_object(
                 'first', public._ask_round(percentile_cont(0.5) WITHIN GROUP (ORDER BY p.value) FILTER
                     (WHERE p.day < rng.d_from + (n_days/2))::numeric, m1.metric),
                 'second', public._ask_round(percentile_cont(0.5) WITHIN GROUP (ORDER BY p.value) FILTER
                     (WHERE p.day >= rng.d_from + (n_days/2))::numeric, m1.metric),
                 'n_first', count(*) FILTER (WHERE p.day < rng.d_from + (n_days/2)),
                 'n_second', count(*) FILTER (WHERE p.day >= rng.d_from + (n_days/2)),
                 'n', count(*), 'days', n_days)
          INTO res FROM analysis.f_daily_panel(as_of) p
         WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to;
        IF res->>'first' IS NULL OR res->>'second' IS NULL THEN
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_insufficient';
            UPDATE __CORE__.questions SET refusal = ask_state.refusal, tier = 'INSUFFICIENT'
             WHERE question_id = qid;
            RETURN jsonb_build_object('question_id', qid, 'tier', 'INSUFFICIENT',
                'refusal', refusal, 'metric', m1.metric, 'display', m1.display,
                'insufficiency_reason', 'low_coverage', 'missing_input', 'comparison_half',
                'range', jsonb_build_array(rng.d_from, rng.d_to),
                'would_raise_it', 'Record observations in both halves of the requested period before comparing them.');
        END IF;
        -- The 28-day rolling median AT RANGE END (B11's registered trend contract). Two halves
        -- answer "did it move across this period"; the rolling figure answers "where is it
        -- now", which is a different question and the one a reader actually acts on. It is
        -- computed over the 28 days ENDING at the range end — which may reach back BEFORE the
        -- requested range, so its own window and day count are reported rather than implied.
        -- A window with too few observed days reports NULL rather than a median of three days
        -- dressed up as a 28-day figure (RULE-06: a gap, never a plausible value).
        SELECT jsonb_build_object(
                 'rolling_28', CASE WHEN count(*) >= 14
                     THEN public._ask_round(percentile_cont(0.5) WITHIN GROUP (ORDER BY p.value)::numeric,
                                            m1.metric) END,
                 'rolling_28_n', count(*),
                 'rolling_28_from', (rng.d_to - 27),
                 'rolling_28_to', rng.d_to,
                 'rolling_28_min_days', 14,
                 -- The window length is a RESULT field, not a literal in the sentence: every
                 -- numeral the answer emits must trace to a stored value (REQ-NAR-012), and a
                 -- date written into the template tokenises into 2026 / 09 / 08, none of which
                 -- is a stored value. The exact dates stay in the computation for the trace.
                 'rolling_28_window_days', 28,
                 -- An assembled fragment, not a computed one: every number inside it is
                 -- already a stored field above, and the clause only chooses which of them to
                 -- say. It exists because the template mechanism has no conditional, and the
                 -- alternative — leaving an empty slot when the window is too thin — renders
                 -- "the median was  ms", which reads as a missing value rather than as the
                 -- explicit statement that there were not enough days (RULE-18).
                 'rolling_28_clause', CASE WHEN count(*) >= 14
                     THEN 'Over the most recent 28 days the median was '
                          || public._ask_round(percentile_cont(0.5) WITHIN GROUP (ORDER BY p.value)::numeric,
                                               m1.metric)::text
                          || ' ' || coalesce(m1.unit,'') || ', from ' || count(*)::text
                          || ' days with data.'
                     ELSE 'The most recent 28 days hold only ' || count(*)::text
                          || ' days with data, too few for a 28-day median.' END)
          INTO r2 FROM analysis.f_daily_panel(as_of) p
         WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_to - 27 AND rng.d_to;
        res := res || r2;
    ELSIF op = 'rhythm' THEN
        SELECT jsonb_build_object('hi_day', hi.dow, 'hi', hi.med, 'lo_day', lo.dow, 'lo', lo.med,
                                  'n', (SELECT count(*) FROM analysis.f_daily_panel(as_of) p
                                         WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to))
          INTO res
          FROM (SELECT to_char(p.day,'FMDay') AS dow,
                       public._ask_round(percentile_cont(0.5) WITHIN GROUP (ORDER BY p.value)::numeric, m1.metric) AS med
                  FROM analysis.f_daily_panel(as_of) p
                 WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to
                 GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 1) hi,
               (SELECT to_char(p.day,'FMDay') AS dow,
                       public._ask_round(percentile_cont(0.5) WITHIN GROUP (ORDER BY p.value)::numeric, m1.metric) AS med
                  FROM analysis.f_daily_panel(as_of) p
                 WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to
                 GROUP BY 1 ORDER BY 2 ASC, 1 LIMIT 1) lo;
    ELSIF op = 'last' THEN
        SELECT jsonb_build_object('value', public._ask_round(p.value, m1.metric), 'day', p.day, 'since', as_of - p.day)
          INTO res FROM analysis.f_daily_panel(as_of) p
         WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to
         ORDER BY p.day DESC LIMIT 1;
    ELSIF op = 'count_days' THEN
        SELECT c.direction, c.threshold, c.label, c.band_form
          INTO condition_direction, condition_value, cond_txt, cond_band
          FROM public._ask_condition(q) c;
        IF condition_direction IS NULL THEN
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_unmappable';
            UPDATE __CORE__.questions SET refusal = ask_state.refusal WHERE question_id = qid;
            RETURN jsonb_build_object('question_id', qid, 'refusal', refusal,
                'nearest', jsonb_build_array('how many days my ' || m1.display || ' above the usual range'));
        END IF;
        IF NOT cond_band THEN
            SELECT jsonb_build_object('k', count(*) FILTER (WHERE
                        CASE WHEN condition_direction = 'above' THEN p.value > condition_value
                             ELSE p.value < condition_value END),
                     'n', count(*), 'condition', cond_txt, 'threshold', condition_value)
              INTO res FROM analysis.f_daily_panel(as_of) p
             WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to;
        ELSE
            SELECT jsonb_build_object('k', count(*) FILTER (WHERE
                        CASE WHEN condition_direction = 'above' THEN p.value > b.band_hi
                             ELSE p.value < b.band_lo END),
                     'n', count(*), 'condition', cond_txt)
              INTO res FROM analysis.f_daily_panel(as_of) p
              JOIN analysis.baselines b ON b.metric = p.metric AND b.day = p.day
             WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to
               AND CASE WHEN condition_direction = 'above' THEN b.band_hi IS NOT NULL
                        ELSE b.band_lo IS NOT NULL END;
            -- A value without its comparison band cannot count as a tested day.
            coverage_min := (res->>'n')::numeric / n_days;
            cov := jsonb_build_object(m1.metric, coverage_min);
            IF (res->>'n')::int = 0 THEN
                SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_insufficient';
                UPDATE __CORE__.questions SET refusal = ask_state.refusal, tier = 'INSUFFICIENT'
                 WHERE question_id = qid;
                RETURN jsonb_build_object('question_id', qid, 'tier', 'INSUFFICIENT',
                    'refusal', refusal, 'metric', m1.metric, 'display', m1.display,
                    'insufficiency_reason', 'low_coverage', 'missing_input', 'comparison_band',
                    'range', jsonb_build_array(rng.d_from, rng.d_to),
                    'would_raise_it', 'Compute the personal comparison band from prior observations before comparing these days.');
            END IF;
        END IF;

    -- ------------------------------------------------------------------ compare (metric, condition)
    -- B11's registered arity for `compare` is metric+condition: the metric on days satisfying a
    -- condition against the metric on the days that do not. The draft routed it into the
    -- effect/contrast branch, which resolves a SECOND METRIC and looks for a finding — a
    -- different question with a different answer shape, so `compare` could never return what
    -- `config.operations` says it returns.
    ELSIF op = 'compare' THEN
        -- CROSS-METRIC. `m1` is the outcome; `cond_metric` is the metric the condition is
        -- about. "my sleep on days when I drink" splits sleep by drinking, not sleep by sleep.
        IF condition_input IS NULL OR trim(condition_input) = '' THEN
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_unmappable';
            UPDATE __CORE__.questions SET refusal = ask_state.refusal WHERE question_id = qid;
            RETURN jsonb_build_object('question_id', qid, 'refusal', refusal,
                'reason', 'no_condition_metric',
                'nearest', jsonb_build_array('my ' || m1.display || ' on days when my steps are above the usual range'));
        END IF;
        SELECT c.direction, c.threshold, c.label, c.band_form
          INTO condition_direction, condition_value, cond_txt, cond_band
          FROM public._ask_condition(condition_input) c;
        -- A BARE condition names the metric and no comparison, and B11's grammar reads that
        -- as "that metric above its usual range". A condition that contains a comparison this
        -- parser could not read is a different thing entirely and is refused — falling
        -- through to the band form would silently answer a question nobody asked, which is
        -- exactly what `_ask_condition`'s own comment says must not happen. `count_days`
        -- refuses here; the shared parser exists so the two cannot disagree about one phrase.
        IF condition_direction IS NULL THEN
            IF condition_input ~ '\m(above|below|over|under|more than|less than|at least|at most)\M' THEN
                SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_unmappable';
                UPDATE __CORE__.questions SET refusal = ask_state.refusal WHERE question_id = qid;
                RETURN jsonb_build_object('question_id', qid, 'refusal', refusal,
                    'reason', 'condition_not_readable',
                    'nearest', jsonb_build_array('my ' || m1.display || ' on days when my steps are above 5000'));
            END IF;
            condition_direction := 'above'; cond_band := true; cond_txt := 'above the usual range';
        END IF;
        -- `p_exclude` = the outcome. Splitting a metric by its own value answers a different,
        -- nearly meaningless question while looking exactly as authoritative — the whole
        -- reason `compare` was rewritten — and permitting it here left that door open.
        SELECT * INTO cond_metric FROM public._ask_resolve_metric(
            trim(regexp_replace(condition_input,
                 '\s*(is|are|was|were)?\s*(above|below|over|under)\M.*$', ''), ' ?'),
            m1.metric) LIMIT 1;
        IF cond_metric.metric IS NULL OR cond_metric.sim < 0.35 THEN
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_untracked';
            SELECT jsonb_agg(jsonb_build_object('metric', x.metric, 'display', x.display))
              INTO nearest FROM public._ask_resolve_metric(condition_input) x;
            UPDATE __CORE__.questions SET refusal = ask_state.refusal WHERE question_id = qid;
            RETURN jsonb_build_object('question_id', qid, 'refusal', refusal,
                'reason', 'condition_metric_untracked', 'nearest', nearest);
        END IF;
        cond_txt := cond_metric.display || ' ' || cond_txt;

        -- The groups form from days on which the CONDITION metric was observed. A day whose
        -- condition value is unknown belongs to NEITHER group: putting it on the "did not
        -- qualify" side reads an absence as a negative observation, which is the collapse
        -- RULE-07 exists to prevent. Unknown days are counted and reported instead.
        WITH cond AS (
            SELECT p.day,
                   CASE WHEN cond_band THEN
                             CASE WHEN condition_direction = 'above' THEN p.value > b.band_hi
                                  ELSE p.value < b.band_lo END
                        ELSE CASE WHEN condition_direction = 'above' THEN p.value > condition_value
                                  ELSE p.value < condition_value END
                   END AS sat
              FROM analysis.f_daily_panel(as_of) p
              LEFT JOIN analysis.baselines b ON b.metric = p.metric AND b.day = p.day
             WHERE p.metric = cond_metric.metric
               AND p.day BETWEEN rng.d_from - compare_lag AND rng.d_to - compare_lag
        ), outcome AS (
            SELECT p.day, p.value FROM analysis.f_daily_panel(as_of) p
             WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to
        ), joined AS (
            -- `compare_lag` aligns the outcome to the day AFTER a qualifying day when the
            -- question said "after days"; 0 when it said "on days".
            SELECT o.value, c.sat FROM outcome o JOIN cond c ON c.day = o.day - compare_lag
        )
        SELECT jsonb_build_object(
                 'a', public._ask_round(percentile_cont(0.5) WITHIN GROUP (
                          ORDER BY j.value) FILTER (WHERE j.sat IS TRUE)::numeric, m1.metric),
                 'b', public._ask_round(percentile_cont(0.5) WITHIN GROUP (
                          ORDER BY j.value) FILTER (WHERE j.sat IS FALSE)::numeric, m1.metric),
                 'n_a', count(*) FILTER (WHERE j.sat IS TRUE),
                 'n_b', count(*) FILTER (WHERE j.sat IS FALSE),
                 'n_condition_unknown', count(*) FILTER (WHERE j.sat IS NULL),
                 'condition', cond_txt, 'condition_metric', cond_metric.metric,
                 'lag_days', compare_lag, 'threshold', condition_value)
          INTO res FROM joined j;

        SELECT count(*) INTO n_outcome_days FROM analysis.f_daily_panel(as_of) p
         WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to;
        -- Outcome days the condition could not be evaluated on: no condition row at all, or a
        -- row with no comparison band. They are in neither group, and the count says how many
        -- so the reader can see how much of the range the comparison actually rests on.
        res := res || jsonb_build_object('n_condition_missing',
                 n_outcome_days - ((res->>'n_a')::int + (res->>'n_b')::int));
        -- REQ-ASK-021: BOTH metrics' coverage is reported, not only the outcome's. The tier
        -- floor uses the lower of the two, because the weaker input bounds the answer.
        -- Each metric's OWN coverage over the range. The earlier version stored the
        -- intersection under both keys, so a condition metric observed on every day read as
        -- 0.6 — two different meanings of the word "coverage" in one column, and the wrong
        -- one feeding the tier gate.
        SELECT count(*) INTO n_cond_days FROM analysis.f_daily_panel(as_of) p
         WHERE p.metric = cond_metric.metric
           AND p.day BETWEEN rng.d_from - compare_lag AND rng.d_to - compare_lag;
        cov := jsonb_build_object(
                 m1.metric, n_outcome_days::numeric / greatest(n_days,1),
                 cond_metric.metric, n_cond_days::numeric / greatest(n_days,1));
        coverage_min := least(
            n_outcome_days::numeric / greatest(n_days,1),
            ((res->>'n_a')::numeric + (res->>'n_b')::numeric) / greatest(n_days,1));

        IF coalesce((res->>'n_a')::int, 0) = 0 OR coalesce((res->>'n_b')::int, 0) = 0 THEN
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_insufficient';
            UPDATE __CORE__.questions SET refusal = ask_state.refusal, tier = 'INSUFFICIENT'
             WHERE question_id = qid;
            RETURN jsonb_strip_nulls(jsonb_build_object('question_id', qid, 'tier', 'INSUFFICIENT',
                'refusal', refusal, 'metric', m1.metric, 'display', m1.display,
                'condition_metric', cond_metric.metric,
                'insufficiency_reason', 'low_coverage', 'missing_input', 'comparison_half',
                'condition', cond_txt,
                'n_a', (res->>'n_a')::int, 'n_b', (res->>'n_b')::int,
                'n_condition_unknown', (res->>'n_condition_unknown')::int,
                'range', jsonb_build_array(rng.d_from, rng.d_to),
                'would_raise_it', 'Both sides need days on which the condition metric was observed.'));
        END IF;
        res := res || jsonb_build_object('display', m1.display, 'unit', coalesce(m1.unit, ''));
    ELSIF op IN ('effect','contrast') THEN
        SELECT * INTO m2 FROM public._ask_resolve_metric(regexp_replace(q, m1.display, '', 'g'), m1.metric) LIMIT 1;
        -- REQ-ASK-021/022: BOTH metrics' coverage, and the gate on the MINIMUM. Reporting the
        -- driver's only meant the outcome — the metric the delta is actually about — was
        -- neither disclosed nor gated, so the 0.60 floor was applied to one side of a
        -- two-metric operation and not the other.
        IF m2.metric IS NOT NULL THEN
            SELECT count(*) INTO n_outcome_days FROM analysis.f_daily_panel(as_of) p
             WHERE p.metric = m2.metric AND p.day BETWEEN rng.d_from AND rng.d_to;
            cov := coalesce(cov, '{}'::jsonb)
                   || jsonb_build_object(m2.metric, n_outcome_days::numeric / greatest(n_days,1));
            coverage_min := least(coalesce(coverage_min, 1),
                                  n_outcome_days::numeric / greatest(n_days,1));
        END IF;
        IF m2.metric IS NULL THEN
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_unmappable';
            UPDATE __CORE__.questions SET refusal = ask_state.refusal WHERE question_id = qid;
            RETURN jsonb_build_object('question_id', qid, 'refusal', refusal,
                'reason', 'second_metric_unresolved',
                'nearest', jsonb_build_array('does ' || m1.display || ' affect my sleep'));
        END IF;
        -- `delta` and `adjustment_set` come from the tables that actually carry them: the
        -- effect size from the resolution that set the current status, the adjustment set from
        -- the frozen pre-registration. The draft read `r2.beta` and `r2.adjustment_set`, and
        -- neither column exists on `hypothesis_resolutions` — this branch had never been
        -- executed by a test, so the error waited for the first real question instead.
        -- REQ-ASK-030 / RULE-19: the finding is read AS OF the question's date.
        --   * the hypothesis must have been registered on or before as_of, and
        --   * its status is the one its latest resolution ON OR BEFORE as_of set — never
        --     `hypothesis_register.status`, a mutable column reflecting what is true NOW.
        -- Without this a promotion or a correction recorded next month silently rewrites the
        -- answer to a question asked today, and "what did the system say on D" stops being
        -- answerable. A day cutoff on panel rows alone is not replay.
        --
        -- Direction is EXACT. A registered finding that X predicts Y does not answer "does Y
        -- affect X": exposure and outcome are not interchangeable, and serving the reverse
        -- asserts a relationship the pre-registration never tested (RULE-19).
        SELECT h.hypothesis_id, res2.status_to AS status, res2.delta, h.adjustment_set,
               h.lag_days
          INTO r FROM __CORE__.hypothesis_register h
          JOIN LATERAL (SELECT rr.status_to, rr.delta FROM __CORE__.hypothesis_resolutions rr
                         WHERE rr.hypothesis_id = h.hypothesis_id
                           -- The SUBJECT day (ADR-0019: 04:00 ET), not `::date`, which uses
                           -- whatever timezone the session happens to have. A resolution at
                           -- 23:30 UTC answered PROMOTED from America/New_York and
                           -- INSUFFICIENT from Asia/Tokyo — same question, same as_of, same
                           -- data. CI runs UTC, the fixture ran ET, and every fixture wrote
                           -- 12:00 UTC, which never crosses a boundary in either.
                           AND ((rr.resolved_at AT TIME ZONE 'America/New_York')
                                - interval '4 hours')::date <= as_of
                         ORDER BY rr.resolved_at DESC, rr.resolution_id LIMIT 1) res2 ON true
         WHERE ((h.preregistered_at AT TIME ZONE 'America/New_York')
                - interval '4 hours')::date <= as_of
           AND res2.status_to IN ('PROMOTED','CONFIRMED_OBSERVATIONAL')
           AND h.exposure_metric = m1.metric AND h.outcome_metric = m2.metric
         -- A deterministic tiebreak. Two PROMOTED hypotheses for one exposure->outcome is a
         -- state the schema permits, and without this the answer depended on physical row
         -- order and would change after a VACUUM FULL — REQ-ASK-030 reproducibility gone for
         -- a reason nothing in the record would show.
         ORDER BY CASE res2.status_to WHEN 'CONFIRMED_OBSERVATIONAL' THEN 0 ELSE 1 END,
                  h.preregistered_at, h.hypothesis_id LIMIT 1;

        IF r.hypothesis_id IS NULL THEN
            SELECT h.hypothesis_id, res2.status_to, h.exposure_metric, h.outcome_metric
              INTO reverse_finding FROM __CORE__.hypothesis_register h
              JOIN LATERAL (SELECT rr.status_to FROM __CORE__.hypothesis_resolutions rr
                             WHERE rr.hypothesis_id = h.hypothesis_id
                               AND ((rr.resolved_at AT TIME ZONE 'America/New_York')
                                    - interval '4 hours')::date <= as_of
                             ORDER BY rr.resolved_at DESC, rr.resolution_id LIMIT 1) res2 ON true
             WHERE ((h.preregistered_at AT TIME ZONE 'America/New_York')
                    - interval '4 hours')::date <= as_of
               AND res2.status_to IN ('PROMOTED','CONFIRMED_OBSERVATIONAL')
               AND h.exposure_metric = m2.metric AND h.outcome_metric = m1.metric
             ORDER BY h.preregistered_at, h.hypothesis_id LIMIT 1;
        END IF;

        -- A finding exists only for the REVERSE pair. It is named as a different finding and
        -- never served as the answer to the question that was asked.
        IF r.hypothesis_id IS NULL AND reverse_finding.hypothesis_id IS NOT NULL THEN
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_insufficient';
            UPDATE __CORE__.questions SET refusal = ask_state.refusal, tier = 'INSUFFICIENT'
             WHERE question_id = qid;
            RETURN jsonb_build_object('question_id', qid, 'tier', 'INSUFFICIENT',
                'refusal', refusal, 'insufficiency_reason', 'no_finding_in_this_direction',
                'asked', m1.display || ' -> ' || m2.display,
                'available_instead', m2.display || ' -> ' || m1.display,
                'available_tier', reverse_finding.status_to,
                'note', 'A finding is registered in the other direction. Exposure and outcome are not interchangeable, so it does not answer this question.',
                'would_raise_it', 'Register and watch the hypothesis in the direction asked.');
        END IF;

        IF r.hypothesis_id IS NOT NULL AND r.delta IS NULL THEN
            -- `hypothesis_resolutions.delta` is nullable. A blank where the number belongs
            -- passes the numeral verifier — a MISSING numeral is not an untraceable one — and
            -- renders "appears to differ by  ms", which reads as a value rather than as its
            -- absence. The identical hole was fixed in `contrast`; this branch had it too.
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_insufficient';
            UPDATE __CORE__.questions SET refusal = ask_state.refusal, tier = 'INSUFFICIENT'
             WHERE question_id = qid;
            RETURN jsonb_build_object('question_id', qid, 'tier', 'INSUFFICIENT',
                'refusal', refusal, 'insufficiency_reason', 'finding_without_an_effect_size',
                'hypothesis_id', r.hypothesis_id,
                'would_raise_it', 'The registered finding carries no effect size, so there is no number to state.');
        END IF;
        IF r.hypothesis_id IS NOT NULL THEN
            op := 'effect';
            res := jsonb_build_object('driver', m1.display, 'outcome', m2.display,
                                      'delta', abs(round(r.delta, 3)),
                                      'unit', coalesce(m2.unit, ''),
                                      'direction', CASE WHEN r.delta > 0 THEN 'higher' ELSE 'lower' END,
                                      'adjustment', coalesce(
                                          (SELECT string_agg(x, ', ') FROM jsonb_array_elements_text(r.adjustment_set) x),
                                          'day of week'),
                                      'hypothesis_id', r.hypothesis_id, 'status', r.status);
            tier := r.status;
        ELSE
            -- REQ-ASK-032: no registered finding, so no causal claim. The exploratory quartile
            -- contrast is all there is, and it is READ from `analysis.contrasts` rather than
            -- recomputed here. RULE-12: that measure has exactly one owner — the weekly scan
            -- engine, which computes it with the Mann-Whitney p, the BH q and the weekday
            -- partialling this function cannot reproduce. A second implementation in plpgsql
            -- would be a second definition of the same number, differing silently.
            op := 'contrast';
            SELECT c.driver, c.outcome, c.lag_days, c.n_hi, c.n_lo, c.med_hi, c.med_lo,
                   c.delta, c.q_fdr, c.run_date, c.code_version
              INTO r
              FROM analysis.contrasts c
             -- EXACT orientation. The quartile contrast splits days by the DRIVER and reads
             -- the OUTCOME, so the two are not interchangeable and the reverse row answers a
             -- different question. `run_date <= as_of` keeps a scan run that happened after
             -- the question's date out of its answer (REQ-ASK-030 / RULE-04).
             WHERE c.driver = m1.metric AND c.outcome = m2.metric
               AND c.run_date <= as_of
             ORDER BY c.run_date DESC, abs(c.lag_days), c.q_fdr, c.contrast_id
             LIMIT 1;
            IF r.driver IS NULL THEN
                SELECT c.driver, c.outcome, c.run_date INTO reverse_contrast
                  FROM analysis.contrasts c
                 WHERE c.driver = m2.metric AND c.outcome = m1.metric AND c.run_date <= as_of
                 ORDER BY c.run_date DESC LIMIT 1;
                -- Nothing has been computed for this pair. That is a documented gap, not a
                -- zero: the draft returned delta NULL into a template that reads "ran {delta}
                -- lower", which renders a sentence stating a difference nobody measured.
                SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_insufficient';
                UPDATE __CORE__.questions SET refusal = ask_state.refusal, tier = 'INSUFFICIENT'
                 WHERE question_id = qid;
                RETURN jsonb_strip_nulls(jsonb_build_object('question_id', qid, 'tier', 'INSUFFICIENT',
                    'refusal', refusal, 'insufficiency_reason', 'no_contrast_computed',
                    'driver', m1.display, 'outcome', m2.display,
                    'reverse_direction_available', CASE WHEN reverse_contrast.driver IS NOT NULL
                        THEN m2.display || ' -> ' || m1.display END,
                    'reverse_note', CASE WHEN reverse_contrast.driver IS NOT NULL THEN
                        'A contrast exists in the other direction only. It answers a different question and is not shown as this one.' END,
                    'range', jsonb_build_array(rng.d_from, rng.d_to),
                    'would_raise_it', 'The weekly scan computes this contrast; it has not yet run in this direction.'));
            END IF;
            -- The stored contrast covers the SCAN's window, which `analysis.contrasts` does
            -- not record and which is not the question's range. The answer therefore states
            -- what the number actually rests on — the observed high and low day counts and
            -- the run that produced it — and never restates the asked-for range. Labelling a
            -- multi-year sweep "over the last 10 days" is a false statement about evidence.
            res := jsonb_build_object(
                     'driver', m1.display, 'outcome', m2.display,
                     'delta', abs(r.delta), 'unit', coalesce(m2.unit, ''),
                     'direction', CASE WHEN r.delta > 0 THEN 'higher' ELSE 'lower' END,
                     'n_hi', r.n_hi, 'n_lo', r.n_lo, 'lag_days', r.lag_days,
                     'q_fdr', r.q_fdr, 'computed_on', r.run_date,
                     'window', 'the scan run of ' || r.run_date::text,
                     'owner', 'analysis.contrasts', 'owner_code_version', r.code_version);
        END IF;

    ELSIF op = 'spend' THEN
        -- WHAT THIS MEASURES, precisely: the sum of `transaction` atoms whose STATEMENT
        -- DESCRIPTOR contains the requested text. That is a well-defined measurement. It is
        -- NOT "spend at merchant X", and the difference is not pedantry — a McDonald's charge
        -- that settles as "SQ *MCD 8005551212 CA" is a real charge this will not find, so the
        -- total is a floor, not a total.
        --
        -- Merchant and category resolution is REQ-FIN-070..093: a pattern table, a fuzzy
        -- cascade, kNN over Joe's own corrections, a confidence-gated model, and a review
        -- queue. It belongs to B14/B17 and none of it exists. Implementing a substring match
        -- here and calling it merchant resolution would create a second owner of a measure
        -- B14 owns (RULE-12) and would make the weaker number indistinguishable from the
        -- real one. So the answer says what it matched on, and ADR-0062 records the rest as
        -- held rather than silently unmet.
        -- The subject must be NAMED. A bare "how much did i spend" has no subject, and a
        -- blind regexp_replace leaves the whole question as the search text — which then
        -- matches no descriptor and reports an absent answer, hiding a question the executor
        -- simply could not read as an unlucky lack of data.
        entity_text := trim(coalesce((regexp_match(q, '(?:spend|spent)\s+(?:on|at)\s+(.+)$'))[1], ''), ' ?');
        entity_text := trim(regexp_replace(entity_text,
            '\s+(today|yesterday|this (week|month|year)|last [0-9]+ days?|last (week|month)|since .+|in [0-9]{4})[?]?$', ''), ' ?');
        IF entity_text = '' THEN
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_unmappable';
            UPDATE __CORE__.questions SET refusal = ask_state.refusal WHERE question_id = qid;
            RETURN jsonb_build_object('question_id', qid, 'refusal', refusal,
                'reason', 'no_spend_subject',
                'nearest', jsonb_build_array('how much did i spend at a merchant this month'));
        END IF;

        -- Currency is checked, not assumed. Summing across units produces a number with no
        -- meaning, and `transaction_amount_usd` is the only unit B13's importer writes today,
        -- so a second unit means an importer changed and this query is no longer valid.
        -- count(DISTINCT) IGNORES NULLs and core.atoms.unit is nullable, so two unit-less
        -- atoms counted as zero currencies and `coalesce(term,'usd')` then INVENTED one — a
        -- total labelled usd with no row saying so. A missing unit is not agreement.
        SELECT count(DISTINCT a.unit), min(a.unit), count(*) FILTER (WHERE a.unit IS NULL)
          INTO n_outcome_days, term, n_null_unit
          FROM __CORE__.atoms_current a
         WHERE a.kind = 'transaction'
           AND a.subject_day BETWEEN rng.d_from AND rng.d_to AND a.subject_day <= as_of
           AND a.evidence_span ILIKE '%' || public._ask_like_escape(entity_text) || '%';
        IF n_outcome_days > 1 OR n_null_unit > 0 THEN
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_insufficient';
            UPDATE __CORE__.questions SET refusal = ask_state.refusal, tier = 'INSUFFICIENT'
             WHERE question_id = qid;
            RETURN jsonb_build_object('question_id', qid, 'tier', 'INSUFFICIENT',
                'refusal', refusal,
                'insufficiency_reason', CASE WHEN n_null_unit > 0 THEN 'unit_missing'
                                             ELSE 'mixed_currency' END,
                'matched_on', entity_text, 'currencies', n_outcome_days,
                'charges_without_a_unit', n_null_unit,
                'would_raise_it', CASE WHEN n_null_unit > 0
                    THEN 'Some matching charges carry no currency, so no total can be labelled honestly.'
                    ELSE 'These charges are in more than one currency; a single total would not mean anything until conversion is defined.' END);
        END IF;

        -- Outflows and inflows are counted separately, never netted here. REQ-FIN-050 nets
        -- inbound P2P transfers against bar and restaurant spend, but only through LINKED
        -- `transfers` rows — netting an arbitrary refund into a total silently changes what
        -- the number means and cannot be undone by a reader.
        SELECT jsonb_build_object(
                 'matched_on', entity_text,
                 'match_method', 'statement_descriptor_contains',
                 'currency', term,
                 'total_out', abs(round(coalesce(sum(a.value_point) FILTER (WHERE a.value_point < 0), 0), 2)),
                 'n_out', count(*) FILTER (WHERE a.value_point < 0),
                 'total_in', round(coalesce(sum(a.value_point) FILTER (WHERE a.value_point > 0), 0), 2),
                 'n_in', count(*) FILTER (WHERE a.value_point > 0),
                 'first_day', min(a.subject_day) FILTER (WHERE a.value_point < 0),
                 'last_day', max(a.subject_day) FILTER (WHERE a.value_point < 0),
                 'weeks', greatest(round((n_days::numeric / 7), 2), 0.01),
                 'per_week', abs(round(coalesce(sum(a.value_point) FILTER (WHERE a.value_point < 0), 0)
                                       / greatest(n_days::numeric / 7, 0.01), 2)))
          INTO res
          FROM __CORE__.atoms_current a
         WHERE a.kind = 'transaction'
           AND a.subject_day BETWEEN rng.d_from AND rng.d_to AND a.subject_day <= as_of
           AND a.evidence_span ILIKE '%' || public._ask_like_escape(entity_text) || '%';

        IF coalesce((res->>'n_out')::int, 0) = 0 THEN
            SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_insufficient';
            UPDATE __CORE__.questions SET refusal = ask_state.refusal, tier = 'INSUFFICIENT'
             WHERE question_id = qid;
            RETURN jsonb_strip_nulls(jsonb_build_object('question_id', qid, 'tier', 'INSUFFICIENT',
                'refusal', refusal, 'insufficiency_reason', 'metric_absent',
                'matched_on', entity_text, 'match_method', 'statement_descriptor_contains',
                'n_in', (res->>'n_in')::int,
                'range', jsonb_build_array(rng.d_from, rng.d_to),
                'would_raise_it', 'No charge in this range carries that text in its statement descriptor. Merchant resolution is not built (B14), so a charge recorded under a different descriptor would not be found.'));
        END IF;

        res := res || jsonb_build_object(
                 'total', (res->>'total_out')::numeric, 'n', (res->>'n_out')::int,
                 'entity', entity_text,
                 -- Carried into the answer text, so the limitation travels with the number
                 -- rather than living only in an ADR nobody reads at the moment of reading it.
                 'caveat', 'matched on the statement descriptor; merchant resolution is not built, so charges recorded under another descriptor are not included');
    ELSE
        -- `entity` before `search`: a question naming something the record knows as an entity
        -- — a merchant, a category, a site, a channel, an exercise — is answered by that
        -- entity's own summary, not by a text search that happens to mention it. The
        -- operation was registered in `config.operations` from the start and was unreachable:
        -- no grammar pattern routed to it and `get_entity` was never called, so a registered
        -- operation existed that nothing could ever run (REQ-ASK-004's registry is meant to
        -- be exhaustive in both directions).
        -- The ORIGINAL question text, not the lowercased `q`: `get_entity` matches a merchant
        -- key exactly, so "Blue Bottle Coffee" and "blue bottle coffee" are different keys and
        -- lowercasing makes every entity unresolvable. Grammar matching stays case-insensitive;
        -- only the key does not.
        entity_text := trim(regexp_replace(p_question, '(?i)^(what|who|tell me) (is|about) ', ''), ' ?');
        entity_text := trim(regexp_replace(entity_text,
            '(?i)\s+(today|yesterday|this (week|month|year)|last [0-9]+ days?|last (week|month)|since .+|in [0-9]{4})[?]?$', ''), ' ?');
        FOREACH term IN ARRAY ARRAY['merchant','category','site','channel','exercise'] LOOP
            SELECT public.get_entity(term, entity_text) INTO r2;
            -- `get_entity` reports an unknown key as `{n: 0, note: "Nothing recorded ..."}`
            -- with NO `refusal` field, so testing for a refusal alone treats every unknown
            -- name as a successful entity answer — including one that is plainly a search.
            -- The emptiness test is `n`.
            IF r2 IS NOT NULL AND r2->>'refusal' IS NULL
               AND coalesce((r2->>'n')::int, 0) > 0 THEN
                op := 'entity';
                -- `get_entity` computes its OWN cutoff (yesterday) and discards the caller's
                -- date, so a question asked as of 2020 was answered from 2026 data while the
                -- computation row stamped 2020. The entity's real as-of is carried so the two
                -- are visible rather than silently contradictory; making get_entity honour the
                -- caller's date is B14's, and is named in the checkpoint.
                res := jsonb_build_object('entity_type', term, 'entity_key', entity_text,
                                          'entity_as_of', r2->>'as_of',
                                          'as_of_requested', as_of,
                                          'as_of_matches_request', (r2->>'as_of')::date = as_of,
                                          'n', (r2->>'n')::int,
                                          'summary', coalesce(r2->>'summary',
                                              entity_text || ': ' || (r2->>'n') || ' records'),
                                          'entity', r2);
                EXIT;
            END IF;
        END LOOP;

        IF op <> 'entity' THEN
            op := 'search';
            -- The full `search_record` payload is carried, not a count wrapper. The count
            -- alone cannot be traced back to anything: REQ-ASK-009 requires every rendered
            -- numeral to reach a stored result, and an answer that says "12 records mention
            -- that" with no record identities behind it is unverifiable by construction.
            -- The RANGE PHRASE is not a search term. Passing the whole question meant
            -- "kubernetes networking last 90 days" was matched literally against titles, so
            -- adding a range to a question that worked made it return nothing — the range
            -- narrowed the words instead of the window.
            SELECT public.search_record(
                     trim(regexp_replace(
                       regexp_replace(p_question, '[?]', '', 'g'),
                       '(?i)\s+(today|yesterday|this (week|month|year)|last [0-9]+ days?|last (week|month)|since .+|in [0-9]{4})$',
                       '')), 200) INTO r2;
            -- `search_record` carries NO date predicate, so its hits span the whole record.
            -- The sentence names the requested range, so the count has to mean that range —
            -- otherwise "3 records mention that over the last 90 days" is false, and one of
            -- the three can be dated after the question's own as_of. Filtered here, on the
            -- subject day each hit already carries.
            SELECT coalesce(jsonb_agg(h ORDER BY h->>'day' DESC), '[]'::jsonb)
              INTO r3 FROM jsonb_array_elements(coalesce(r2->'hits','[]'::jsonb)) h
             WHERE (h->>'day')::date BETWEEN rng.d_from AND rng.d_to
               AND (h->>'day')::date <= as_of;
            res := jsonb_build_object(
                     'n', jsonb_array_length(r3),
                     'q', r2->>'q',
                     'hits', r3,
                     'n_all_time', coalesce((r2->>'n')::int, 0),
                     'by_month', coalesce(r2->'by_month', '[]'::jsonb));
            IF coalesce((res->>'n')::int, 0) = 0 THEN
                SELECT value INTO refusal FROM config.strings WHERE key = 'refusal_insufficient';
                UPDATE __CORE__.questions SET refusal = ask_state.refusal, tier = 'INSUFFICIENT'
                 WHERE question_id = qid;
                RETURN jsonb_build_object('question_id', qid, 'tier', 'INSUFFICIENT',
                    'refusal', refusal, 'insufficiency_reason', 'metric_absent',
                    'q', r2->>'q', 'n', 0,
                    'would_raise_it', 'Nothing in the record matches those words over this range.');
            END IF;
        END IF;

    END IF;

    -- tier (REQ-ASK-020): the op ceiling, floored by coverage (REQ-TIER-017)
    IF tier IS NULL THEN SELECT o.tier_ceiling INTO tier FROM config.operations o WHERE o.op = ask_state.op; END IF;
    IF coverage_min IS NOT NULL AND coverage_min < 0.60 THEN
        tier := 'INSUFFICIENT'; ins_reason := 'low_coverage';
        SELECT d.capture_action INTO raise_action FROM config.domain_metrics dm
          JOIN config.domains d ON d.domain_key = dm.domain_key WHERE dm.metric = m1.metric LIMIT 1;
        IF op = 'count_days' AND coalesce(cond_band, false) THEN
            raise_action := 'Compute the missing personal comparison bands from prior observations to increase the number of comparable days.';
        END IF;
    END IF;

    -- Narration metadata is part of the persisted result too: range labels and
    -- units can themselves contain numerals. Nothing gets an ambient exemption.
    -- The unit belongs to the value the number IS. For a two-metric operation the delta is in
    -- the OUTCOME's unit, and overwriting it with the driver's rendered "HRV ran 7.5 steps
    -- lower" — and persisted it that way, so the trace confirmed the wrong unit instead of
    -- correcting it (RULE-05: no number is rendered without its lane).
    res := res || jsonb_build_object('display', m1.display,
                                     'unit', CASE WHEN op IN ('effect','contrast')
                                                  THEN coalesce(res->>'unit', m2.unit, '')
                                                  ELSE coalesce(m1.unit, res->>'unit') END,
                                     'range_label', rng.label, 'days', n_days);
    SELECT coalesce(jsonb_agg(jsonb_build_object('table','analysis.panel', 'day', p.day, 'metric', p.metric)
                             ORDER BY p.day, p.metric), '[]'::jsonb)
      INTO keys FROM analysis.f_daily_panel(as_of) p
     WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to;
    IF op IN ('count_days','compare') AND coalesce(cond_band, false) THEN
        -- The band was evaluated on the metric the CONDITION is about — which for `compare`
        -- is the condition metric, not the outcome. Tracing m1's baselines produced an empty
        -- set whenever the outcome had none, and `jsonb_agg` over nothing is NULL, which the
        -- NOT NULL on observation_keys turned into a crash: the answer was computed correctly
        -- and then thrown away with a 500. `coalesce` to an empty array as everywhere else,
        -- and trace the metric the comparison actually rested on.
        SELECT coalesce(jsonb_agg(jsonb_build_object('table', rows.table_name, 'day', rows.day,
                                                     'metric', rows.metric)
                         ORDER BY rows.day, rows.table_name), '[]'::jsonb)
          INTO keys FROM (
            SELECT p.day, p.metric, source.table_name
              FROM analysis.f_daily_panel(as_of) p
              JOIN analysis.baselines b ON b.metric = p.metric AND b.day = p.day
              CROSS JOIN (VALUES ('analysis.panel'), ('analysis.baselines')) source(table_name)
             WHERE p.metric = coalesce(cond_metric.metric, m1.metric)
               AND p.day BETWEEN rng.d_from - coalesce(compare_lag,0)
                             AND rng.d_to - coalesce(compare_lag,0)
               AND CASE WHEN condition_direction = 'above' THEN b.band_hi IS NOT NULL
                        ELSE b.band_lo IS NOT NULL END
          ) rows;
        -- For `compare` the OUTCOME's rows are part of the evidence too: the medians came
        -- from them. Tracing only the condition side would make the answer unauditable in
        -- exactly the direction the number points.
        IF op = 'compare' THEN
            SELECT keys || coalesce(jsonb_agg(jsonb_build_object(
                       'table','analysis.panel','day',p.day,'metric',p.metric)
                     ORDER BY p.day), '[]'::jsonb)
              INTO keys FROM analysis.f_daily_panel(as_of) p
             WHERE p.metric = m1.metric AND p.day BETWEEN rng.d_from AND rng.d_to;
        END IF;
    ELSIF op = 'compare' THEN
        -- Threshold form: the condition metric's rows decided the split and belong in the
        -- trace beside the outcome's.
        SELECT keys || coalesce(jsonb_agg(jsonb_build_object(
                   'table','analysis.panel','day',p.day,'metric',p.metric)
                 ORDER BY p.day), '[]'::jsonb)
          INTO keys FROM analysis.f_daily_panel(as_of) p
         WHERE p.metric = cond_metric.metric
           AND p.day BETWEEN rng.d_from - coalesce(compare_lag,0)
                         AND rng.d_to - coalesce(compare_lag,0);
    ELSIF op = 'last' THEN
        keys := jsonb_build_array(jsonb_build_object('table', 'analysis.panel',
            'day', res->>'day', 'metric', m1.metric));
    END IF;
    INSERT INTO __CORE__.computations (question_id, plan, as_of, result, observation_keys, coverage,
                                       tier, insufficiency_reason, code_version)
    VALUES (qid, jsonb_build_object('op', op, 'metric', m1.metric, 'metric2', m2.metric,
                                    'range', jsonb_build_array(rng.d_from, rng.d_to)),
            as_of, res, keys, coalesce(cov, '{}'::jsonb), tier, ins_reason, 'ask-v1')
    RETURNING computation_id INTO cid;          -- REQ-ASK-006: persisted BEFORE narration

    -- narrate from the stored template only (REQ-NAR-011); slots come from `res` and nothing else
    -- RULE-16: a template is never selected from a tier ABOVE the effective one. The old
    -- selection fell back to "any template for this op" when no exact tier matched, and the
    -- coverage floor (REQ-TIER-017) is exactly when that happens: an `effect` answer floored
    -- to INSUFFICIENT rendered the CONFIRMED_OBSERVATIONAL sentence — "runs {delta} per
    -- {driver} step, adjusted for {adjustment}" — a causal, dose-response claim on an answer
    -- the system had just declared it could not support. The highest template at or below the
    -- effective tier is chosen instead, so language can only ever fall, never rise.
    SELECT t.template INTO templ FROM config.ask_templates t
     WHERE t.op = ask_state.op
       AND public._ask_tier_rank(t.tier) <= public._ask_tier_rank(ask_state.tier)
     ORDER BY public._ask_tier_rank(t.tier) DESC LIMIT 1;
    IF templ IS NULL THEN
        -- No template at or below the effective tier. The previous fallback took the LOWEST
        -- template for the op, which is still above INSUFFICIENT — so an INSUFFICIENT answer
        -- rendered "appears ... provisional ... watched", every one a PROMOTED-tier term
        -- (config.tier_vocabulary). The bound was written and then defeated three lines later.
        --
        -- An INSUFFICIENT answer gets the INSUFFICIENT form: the numbers, labelled as not
        -- meeting the coverage the tier ladder requires. RULE-18 wants weak evidence disclosed
        -- as weak evidence, not silence — and not a confident sentence either.
        SELECT t.template INTO templ FROM config.ask_templates t
         WHERE t.op = 'insufficient' LIMIT 1;
    END IF;
    answer := templ;
    answer := replace(answer, '{display}', coalesce(m1.display, ''));
    -- `res.unit` first. It has already been set to the unit the VALUE is in — the outcome's
    -- for a two-metric operation — and preferring m1's here re-introduced the driver's unit
    -- into the sentence after the result had been corrected.
    answer := replace(answer, '{unit}', coalesce(res->>'unit', m1.unit, ''));
    answer := replace(answer, '{range}', rng.label);
    answer := replace(answer, '{condition}', coalesce(res->>'condition', ''));
    answer := replace(answer, '{driver}', coalesce(res->>'driver',''));
    answer := replace(answer, '{outcome}', coalesce(res->>'outcome',''));
    answer := replace(answer, '{direction}', coalesce(res->>'direction',''));
    answer := replace(answer, '{adjustment}', coalesce(res->>'adjustment',''));
    answer := replace(answer, '{entity}', coalesce(res->>'entity',''));
    answer := replace(answer, '{summary}', coalesce(res->>'summary',''));
    answer := replace(answer, '{days}', n_days::text);
    SELECT string_agg(x, '') INTO answer FROM (SELECT answer AS x) z;   -- no-op; keeps the plan simple
    -- fill every remaining {slot} from res, so a numeral can only come from the stored result
    SELECT string_agg(kv.key, ',') INTO cond_txt FROM jsonb_each_text(res) kv;
    FOR term IN SELECT kv.key FROM jsonb_each_text(res) kv LOOP
        answer := replace(answer, '{' || term || '}', coalesce(res->>term, ''));
    END LOOP;

    -- REQ-ASK-010 / REQ-NAR-012: every numeral must be a complete token in a
    -- persisted result field. The whole token is the capture group, not merely
    -- its decimal suffix. No special exemption for dates or the day count.
    IF EXISTS (
        SELECT 1 FROM regexp_matches(answer, '([-+]?[0-9]+(?:\.[0-9]+)?)', 'g') AS mm(num)
         WHERE NOT EXISTS (SELECT 1 FROM jsonb_each_text(res) kv,
                               LATERAL regexp_matches(kv.value, '([-+]?[0-9]+(?:\.[0-9]+)?)', 'g') AS stored(num)
                            WHERE stored.num[1] = mm.num[1])
    ) THEN
        INSERT INTO analysis.render_violations (surface, rule, detail, question_id)
        VALUES ('ask', 'REQ-ASK-010', jsonb_build_object('reason', 'untraceable_numeral',
                'answer', answer, 'result', res), qid);
        -- No model narrator is connected yet. A corrupt stored template has no
        -- trusted template fallback; keep the result accessible, refuse its text.
        answer := 'The answer did not pass numeral verification.';
        numeral_valid := false;
    END IF;

    out := jsonb_strip_nulls(jsonb_build_object(
        'question_id', qid, 'op', op, 'tier', tier, 'insufficiency_reason', ins_reason,
        'answer_text', answer, 'result', res,
        'numerals', CASE WHEN numeral_valid THEN public._ask_numerals(templ, res, cid) ELSE '[]'::jsonb END,
        'metric', m1.metric, 'display', m1.display,
        'range', jsonb_build_array(rng.d_from, rng.d_to), 'range_label', rng.label,
        'coverage', cov, 'would_raise_it', raise_action, 'as_of', as_of,
        'trace', jsonb_build_object('computation_id', cid, 'table', 'core.computations')));
    UPDATE __CORE__.questions SET plan = jsonb_build_object('op', op, 'metric', m1.metric),
           answer = out, tier = ask_state.tier WHERE question_id = qid;
    RETURN out;
END $fn$;
REVOKE ALL ON FUNCTION public.ask(text, date) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.ask(text, date) FROM anon;
GRANT EXECUTE ON FUNCTION public.ask(text, date) TO authenticated;

-- REQ-ASK-009/011: traces have an owner-locked read path; the client never needs
-- direct SELECT privileges on the question/computation tables.
CREATE OR REPLACE FUNCTION public.get_computation(p_computation_id uuid)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE result jsonb;
BEGIN
    IF coalesce((auth.jwt()->>'email'), '') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only';
    END IF;
    SELECT to_jsonb(c) INTO result FROM __CORE__.computations c
     WHERE c.computation_id = p_computation_id;
    RETURN result;
END $fn$;
REVOKE ALL ON FUNCTION public.get_computation(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_computation(uuid) TO authenticated;
