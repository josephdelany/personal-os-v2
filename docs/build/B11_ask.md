# B11 — Ask: a question in, a traced and tiered answer out (migrations 0048–0049)

**What this is.** REQ-ASK-001..032 as built. The whole point of "knows me better than
I know myself" is that you can ask it. Two sessions: B11.1 the deterministic core
(operation registry, computations, executor, template answers — RULE-15 path, no model);
B11.2 the language layer on Cloudflare Workers AI (free tier, the same neuron budget
REQ-CAP-036..042 already specifies) that turns free text into a query plan, with the
deterministic parser as the fallback that always works.

**Requirement IDs satisfied:** REQ-ASK-001..012, 020..032; REQ-NAR-011..015, 020;
REQ-TIER-030/031/034 (partial/absent disclosure forms); RULE-15; RULE-26.
**ADRs:** ADR-0053 (operation registry + computations), ADR-0054 (language layer on
Workers AI; deterministic parser fallback).

## B11.1 — the deterministic core (migration 0048)

### Tables
```sql
CREATE TABLE IF NOT EXISTS config.operations (           -- REQ-ASK-002/004: the closed registry
    op TEXT PRIMARY KEY, arity TEXT NOT NULL,             -- 'metric' | 'metric,metric' | 'metric,condition' | 'text' | 'entity'
    description TEXT NOT NULL, tier_ceiling TEXT NOT NULL); -- DESCRIPTIVE for all but 'contrast' (EXPLORATORY) and 'effect' (from findings)
INSERT INTO config.operations VALUES
 ('describe','metric','median, p10–p90, min/max, n, coverage over the range','DESCRIPTIVE'),
 ('trend','metric','first-half vs second-half medians and the 28-day rolling median at range end','DESCRIPTIVE'),
 ('rhythm','metric','weekday medians; highest/lowest weekday','DESCRIPTIVE'),
 ('last','metric','latest value and day, plus days since','DESCRIPTIVE'),
 ('count_days','metric,condition','days where metric satisfies condition (above_band|below_band|gt:X|lt:X) over a denominator','DESCRIPTIVE'),
 ('compare','metric,condition','metric on days satisfying condition vs the rest: medians, n each, delta','DESCRIPTIVE'),
 ('contrast','metric,metric','the registered quartile contrast (scan._contrast) at lag 0..3; EXPLORATORY unless a finding exists','EXPLORATORY'),
 ('effect','metric,metric','the stored finding for driver→outcome if one exists at PROMOTED+; else refusal','PROMOTED'),
 ('search','text','search_record','DESCRIPTIVE'),
 ('entity','entity','get_entity','DESCRIPTIVE'),
 ('spend','entity','money: total, n, typical week, top merchants for a category/merchant over the range','DESCRIPTIVE')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS __CORE__.computations (      -- REQ-ASK-006/009/011/030
    computation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID NOT NULL, plan JSONB NOT NULL,       -- {metrics:[], range:{from,to}, ops:[{op,args}], group_by?}
    as_of DATE NOT NULL, result JSONB NOT NULL,           -- the result set; every numeral the answer may use lives here
    observation_keys JSONB NOT NULL,                      -- [{table, key}] the rows behind the result (panel (day,metric) keys etc.)
    coverage JSONB NOT NULL,                              -- {metric: coverage}
    tier TEXT NOT NULL, insufficiency_reason TEXT,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT now(), code_version TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS __CORE__.questions (
    question_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), asked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    text TEXT NOT NULL, planner TEXT NOT NULL CHECK (planner IN ('deterministic','workers_ai')),
    plan JSONB, iterations INT NOT NULL DEFAULT 1, answer JSONB, refusal TEXT, tier TEXT);
CREATE TABLE IF NOT EXISTS __CORE__.render_violations (  -- REQ-ASK-010, REQ-NAR-013
    violation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), at TIMESTAMPTZ DEFAULT now(),
    question_id UUID, reason TEXT NOT NULL, detail JSONB);
CREATE TABLE IF NOT EXISTS config.tier_vocabulary (      -- REQ-TIER-020 / REQ-NAR-020
    tier TEXT NOT NULL, term TEXT NOT NULL, PRIMARY KEY (tier, term));
-- seed from REQ-TIER-052's illustrative members for EXPLORATORY; DESCRIPTIVE: 'ran','was','median','typically','on';
-- PROMOTED: 'appears','provisional','consistent with'; CONFIRMED: 'increases','decreases','per','adjusted for'; every causal verb ONLY under CONFIRMED/EXPERIMENTAL.
CREATE TABLE IF NOT EXISTS config.strings (k TEXT PRIMARY KEY, v TEXT NOT NULL);  -- the stored refusal/referral strings, verbatim from the spec
INSERT INTO config.strings VALUES
 ('refusal_untracked','I do not track that.'), ('refusal_insufficient','We do not have enough to answer this.'),
 ('refusal_unmappable','<REQ-ASK-031 exact string — copy from the spec>'),
 ('referral_medical','<REQ-ASK-028 stored referral string — copy from the spec; if the spec has none, write one and ADR it>')
ON CONFLICT DO NOTHING;
```

### The executor — `tools/engines/ask.py` (also callable as an RPC via plpgsql wrapper)
`answer(question_text, as_of=None, planner='deterministic')`:
1. **Plan.** Deterministic parser (B11.1) or Workers AI (B11.2) → plan JSON. Metric
   names resolve by trigram similarity against `metric_registry.display_name` and the
   panel metric names (threshold 0.35); a miss → `refusal_untracked` + the 3 nearest
   (REQ-ASK-003). Ops outside `config.operations` → `refusal_unmappable` (REQ-ASK-004/031).
   Range defaults: "last 90 days"; words like "this year", "last month", "since June",
   "in 2024" parse deterministically.
2. **Coverage first** (REQ-ASK-021/022/023): for each metric over the range,
   `coverage = days_with_value / days_in_range`. Any metric with 0 rows → the absent
   form with `refusal_insufficient` naming it. Minimum coverage < 0.60 → tier
   INSUFFICIENT with the partial disclosure form (REQ-TIER-030): still compute, still
   show, label it, name the lowest-coverage metric and "what would raise it" (the
   `capture_action` from `config.domains`).
3. **Execute** each op in SQL (read-only role; `SET TRANSACTION READ ONLY`), from
   `analysis.panel` (the spec's `f_daily_panel(as_of)` is realised as
   `SELECT … FROM analysis.panel WHERE day <= as_of` — write that function so the name
   exists), recording the `observation_keys` used.
4. **Persist** the computation row **before** narration (REQ-ASK-006).
5. **Tier** = min over ops' tiers and any finding drawn on (REQ-ASK-020); `effect`
   reads `core.hypothesis_register` + resolutions (REQ-ASK-032) and never states a
   causal claim below CONFIRMED.
6. **Narrate** with templates (REQ-NAR-011): one template per op, slots filled only
   from `result`; numerals rounded only by `config.domain_metrics.rounding`
   (REQ-NAR-015); units attached (REQ-NAR-014); counts as natural frequencies "{k} of
   {n} days" (REQ-ASK-027).
7. **Verify** (REQ-NAR-012/013, REQ-ASK-010): scan the answer string for numerals;
   every one must appear in `result` (or a registered rounding); otherwise discard, write
   `render_violations(untraceable_numeral)`, return the template rendering.
8. **RULE-26 lint**: the medical vocabulary list → `referral_medical` with the data attached.
9. Return `{question_id, tier, answer_text, numerals:[{value, unit, computation_id}],
   plan, coverage, insufficiency_reason?, refusal?, nearest?, trace:{computation_ids}}`.

### The deterministic parser (RULE-15 path; always available)
A small grammar over lowercased text; each pattern maps to one op:
- "how (is|was) my X", "what('s| is) my X", "my X" → `describe`
- "(is|has) my X (going up|improving|getting worse|trending|changed)" → `trend`
- "which day(s)?|what weekday" + X → `rhythm`
- "when did i last|last time" + X or entity → `last` / `search`
- "how many days" + X + (above|below|over|under N) → `count_days`
- "X (on|after) days (when|with) Y" / "X when Y is high" → `compare` (condition = Y above_band)
- "does X affect|drive|cause|relate to Y", "X and Y" → `effect` if a finding exists else `contrast`
- "how much (did i|have i) spen(d|t) (on|at) E" → `spend`
- anything with a merchant/site/channel name known to `get_entity` → `entity`
- otherwise → `search` on the longest noun phrase; if < 2 chars → `refusal_unmappable`.
Ranges: "today|yesterday|this week|last week|this month|last month|this year|last N days|since <month> [year]|in <year>".

### RPC `public.ask(p_question text, p_as_of date DEFAULT NULL)` → calls the Python? No —
the RPC must be pure SQL for RULE-15. Implement the executor's SQL side as plpgsql
`public.ask(...)` for the deterministic path (the parser is small enough in plpgsql with
regex), and the Python module is the same logic for jobs/tests (RULE-11: one owner — put
the templates and the grammar in `config.ask_grammar (pattern, op, arg_slots)` and
`config.ask_templates (op, tier, template)` so both readers use one source).

### Tests `tests/test_ask.py`
```
test_REQ_ASK_003_untracked_metric_returns_refusal_and_nearest
test_REQ_ASK_004_unregistered_operation_is_refused_and_never_executed
test_REQ_ASK_006_computation_row_exists_before_answer
test_REQ_ASK_009_every_numeral_in_answer_has_computation_id
test_REQ_ASK_010_injected_untraceable_numeral_is_discarded_and_logged
test_REQ_ASK_022_low_coverage_answers_at_insufficient_naming_metric_and_raise_action
test_REQ_ASK_023_absent_metric_returns_absent_form_verbatim
test_REQ_ASK_025_descriptive_question_never_touches_inference
test_REQ_ASK_027_counts_are_natural_frequencies
test_REQ_ASK_028_medical_question_returns_referral_string_with_data
test_REQ_ASK_030_reexecuting_stored_plan_at_same_as_of_is_identical
test_REQ_ASK_032_causal_phrasing_only_from_confirmed_finding
test_REQ_NAR_020_answer_vocabulary_within_tier_list
test_ADR_0053_grammar_maps_twenty_canonical_questions_to_expected_ops   (a fixture of 20 questions Joe would ask, with expected op)
```

## B11.2 — the language layer on Workers AI (migration 0049; ADR-0054)
- A Cloudflare Worker `ask-planner` (free tier) that takes `{question, metrics:[display
  names], operations:[...], ranges:[...]}` and returns **only** a plan JSON via
  `@cf/meta/llama-3.1-8b-instruct` with `response_format: json_schema` (the schema is
  the plan). Neuron cost logged to `core.neuron_ledger` (REQ-CAP-035; create the table if
  B16 has not yet), budget shared with capture (REQ-CAP-037..041); over budget → the
  deterministic parser answers and the response says "planned without the language layer".
- Iterations ≤ 5 (REQ-ASK-008): the worker may ask for `describe` of a metric to
  disambiguate, then re-plan; each iteration is a `computations` row.
- The language layer **never** narrates numerals (REQ-ASK-012): narration stays the
  template path in B11.1; optionally the worker may rephrase the template output with
  numerals masked as `{n1}`…`{nk}` and re-inserted verbatim — implement this only if the
  masked-reinsert verifier (REQ-NAR-012) passes 100 % on a 50-case fixture; else leave it off.
- Egress goes through `lib/egress.py` (B12 creates it) with an `ops.egress_log` row.
- Tests: `test_ADR_0054_planner_output_is_schema_valid_or_falls_back`,
  `test_REQ_CAP_037_ask_respects_daily_neuron_budget`, `test_REQ_ASK_008_iteration_cap`,
  `test_REQ_ASK_012_language_layer_never_adds_a_numeral`.

## Done when
`ask('how is my sleep')`, `ask('does alcohol affect my hrv')`, `ask('how much did I spend at
McDonald's this year')`, `ask('when did I last go to the gym')`, `ask('what is my blood pressure')`
pasted with their envelopes (the last must refuse: untracked); all tests; the worker deployed
(`wrangler deploy`, free) and one real planned question pasted; ADR-0053/0054; PROGRESS +
WHAT I DID NOT DO.
