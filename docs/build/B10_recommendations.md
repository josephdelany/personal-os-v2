# B10 — Recommendations: "tell me what to do," with disclosed uncertainty (migration 0047)

**What this is.** RULE-25 as built. THE_FILE §1 promised ASSESSMENT "one instruction
with tier + prediction attached." Nothing generates it. This build adds the
recommendations table, the generator, the scored forward prediction per
recommendation, auto-demotion, and `get_recommendations()`. One session.

**Requirement IDs satisfied:** RULE-25, RULE-20, RULE-26 (referral string default),
REQ-TIER-047/048/049 (disclosure contract), REQ-TIER-024 (absolute units), REQ-TIER-028
(counter-frame), REQ-NAR-020 (closed vocabulary per tier), the REQ-INF "Missing-E"
trigger (line ~541 of `specs/04-reasoning/requirements.md`: tier-gated, delta-gated,
carries its own scored prediction). **ADR to write:** ADR-0052 — the OQ-30 ruling (below)
and REQ-ACT numbered as REQ-ACT-001..012 in a new `specs/09-action/requirements.md`.

## The OQ-30 ruling (Joe's standing want: "tell me what to do"; recorded as his ruling via advisor, 2026-09-02)
1. **Tier floor: option (c), tier-gated language, with a floor of PROMOTED for
   pattern-based recommendations.** Below CONFIRMED the verbs are hedged and the full
   REQ-TIER-048 disclosure set is attached; at CONFIRMED the verbs are direct. Nothing
   pattern-based is recommended from DESCRIPTIVE or EXPLORATORY.
2. **State-based standing orders are a separate, DESCRIPTIVE channel.** Joe registers
   his own rules in `config.standing_orders` (condition over today's z-scores/bands →
   instruction text). Applying his own rule to his own numbers is not an inference; it
   renders with tier DESCRIPTIVE, the numbers, and "your standing order". Seed two:
   guardian (≥2 autonomic signals firing → "Lift lighter today; this is your rule for a
   2-of-4 autonomic day.") and sleep debt (`sleep_asleep_min` below band two nights →
   "Protect tonight's sleep; two nights below your band.").
3. **Proactive channel = ASSESSMENT's one instruction, read-only, at most one per
   day**, separate from RULE-27's daily prompt (it is a surface, not a push).
4. **Demotion:** a recommendation is demoted when its finding demotes (REQ-TIER-041) or
   when its own forward prediction scores false twice consecutively (placeholder; OQ-10).
5. **Digest:** yes — the one instruction daily on ASSESSMENT; the full list on demand in
   THE DESK.

## Migration `migrations/0047_recommendations.sql`
```sql
CREATE TABLE IF NOT EXISTS config.controllable_metrics (
    metric TEXT PRIMARY KEY, lever TEXT NOT NULL,        -- how Joe moves it, in his words
    unit TEXT NOT NULL, min_effect NUMERIC NOT NULL,     -- OQ-10 placeholder per metric
    hedged_verb TEXT NOT NULL DEFAULT 'consider', direct_verb TEXT NOT NULL DEFAULT 'do');
INSERT INTO config.controllable_metrics VALUES
 ('alcohol_standard_drinks','drinks tonight','drinks',1,'consider','keep'),
 ('sleep_asleep_min','time in bed','min',20,'consider','protect'),
 ('sleep_midpoint','bedtime','clock',0.5,'consider','keep'),
 ('steps','walking','steps',2000,'consider','get'),
 ('exercise_min','training','min',15,'consider','do'),
 ('strength_volume','session volume','lb·reps',1000,'consider','lift'),
 ('screen_active_hours','screen time','h',1,'consider','cap'),
 ('screen_binge_min','late binges','min',30,'consider','cut'),
 ('meals_logged','logging meals','meals',1,'consider','log')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS config.standing_orders (
    order_id TEXT PRIMARY KEY, condition_sql TEXT NOT NULL,   -- boolean SQL over analysis.baselines for day d; owner-written by migration only
    instruction TEXT NOT NULL, enabled BOOLEAN NOT NULL DEFAULT true);
-- seed the two orders from the ruling (write the boolean SQL against analysis.baselines exactly as get_state's guardian block does)

CREATE TABLE IF NOT EXISTS __CORE__.recommendations (
    recommendation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    for_day DATE NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('pattern','standing_order')),
    hypothesis_id TEXT REFERENCES __CORE__.hypothesis_register(hypothesis_id),   -- pattern kind
    order_id TEXT,                                                              -- standing_order kind
    tier TEXT NOT NULL,                       -- DESCRIPTIVE | PROMOTED | CONFIRMED_OBSERVATIONAL
    driver TEXT, outcome TEXT, lag_days INT,
    instruction TEXT NOT NULL,                -- the sentence, from the closed templates below
    effect_abs NUMERIC, effect_unit TEXT, ci_lo NUMERIC, ci_hi NUMERIC,
    n INT, n_eff NUMERIC, coverage NUMERIC, counter_frame_n INT,
    would_change TEXT NOT NULL,               -- REQ-TIER-048: what evidence would change the answer
    prediction_id UUID REFERENCES __CORE__.predictions(prediction_id),         -- RULE-20
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','demoted','superseded')),
    demoted_reason TEXT, demoted_at TIMESTAMPTZ,
    code_version TEXT NOT NULL
);
-- append-only except status/demoted_* (a status-only trigger like hypothesis_register's freeze)
```

## Generator — `tools/engines/recommend.py`, nightly after `confirm.py`
For day d (tomorrow's subject day):
- **Pattern recommendations.** For each `PROMOTED` / `CONFIRMED_OBSERVATIONAL` hypothesis
  whose driver ∈ `config.controllable_metrics` and whose |effect| (B9's HAC β for
  CONFIRMED; the contrast delta for PROMOTED) ≥ `min_effect` of the *outcome* if listed
  else any: build one recommendation. Instruction from the closed templates (REQ-NAR-020):
  - PROMOTED: "{Consider} {lever}: on your highest-{driver} days, {outcome} ran
    {|delta|} {unit} {higher|lower} {lag phrase} (n {n}, coverage {coverage}). Provisional."
  - CONFIRMED: "{Direct_verb} {lever}: {outcome} runs {|beta|} {unit} ({ci_lo}–{ci_hi})
    {higher|lower} per {driver} step, adjusted for {adjustment_set}, E-value {e_value_point}."
  `would_change` = "A second look with the opposite sign, or a failed negative control."
  (PROMOTED) / "A monthly re-check outside the interval." (CONFIRMED).
  Insert a `core.predictions` row: claim "If {driver} is in your top quartile on ≥7 of
  the next 14 days, {outcome} will be {higher|lower} than its 28-day median on the
  majority of those days", `resolves_at` = d+14, `p_forecast` = 0.5 until calibrated
  (B8 ruling b); the forecast resolver (`forecast.resolve`) gains a branch for
  `model_version LIKE 'recommend-%'` that scores it.
- **Standing orders.** Evaluate each enabled `condition_sql` for d−1; if true, insert a
  `standing_order` recommendation, tier DESCRIPTIVE, with the numbers that fired it in
  `instruction` and `would_change` = "Your own rule; edit it by migration."
- **Ranking for the one daily instruction** (ASSESSMENT): CONFIRMED before PROMOTED
  before standing orders; within tier, largest |effect|/min_effect. Exactly one gets
  `is_daily = true` (add the column).
- **Demotion.** If the hypothesis was demoted/refuted since, or two consecutive
  predictions scored false → `status='demoted'`, `demoted_reason`, and a brief notice
  (B9's `analysis.brief_notes`). Never delete.
- **RULE-26 guard.** A regex lint over every generated instruction for the medical
  vocabulary list in REQ-ASK-028 (read it; use its list); a hit replaces the instruction
  with the stored referral string and logs a `render_violations` row.

## RPC `public.get_recommendations(p_day date DEFAULT NULL)`
Envelope: `{day, daily?:{...one recommendation...}, active:[{recommendation_id, kind,
tier, instruction, driver, outcome, lag_days, effect:{abs, unit, ci:[lo,hi]}, n, n_eff,
coverage, counter_frame_n, would_change, prediction:{claim, resolves_at, p_forecast,
outcome_bool?, brier?}, trace}], demoted_recent:[{instruction, tier, demoted_reason,
demoted_at}]}`. `get_today` gains `instruction: <the daily one>` (additive).
REQ-TIER-049 is enforced by a test that every item carries `tier` and `effect.ci` (or
kind = standing_order with tier DESCRIPTIVE).

## Tests `tests/test_recommendations.py`
```
test_RULE_25_pattern_recommendation_requires_promoted_or_confirmed
test_REQ_TIER_048_below_confirmed_carries_tier_interval_n_coverage_would_change
test_REQ_TIER_049_no_recommendation_without_tier_and_interval
test_REQ_TIER_047_promoted_uses_hedged_verb_only
test_RULE_20_every_pattern_recommendation_has_a_prediction_row
test_ADR_0052_two_false_predictions_demote_with_notice
test_ADR_0052_standing_order_fires_on_guardian_condition_and_is_descriptive
test_RULE_26_medical_vocabulary_is_replaced_by_referral_string
test_ADR_0052_exactly_one_daily_instruction
```

## Done when
Migration; generator in the nightly workflow; `get_recommendations()` and `get_today.instruction`
pasted (expected today: only standing orders can fire — say so); `specs/09-action/requirements.md`
with REQ-ACT-001..012 numbered from the ruling; ADR-0052; OQ-30 closed; tests; PROGRESS +
WHAT I DID NOT DO (min_effect placeholders; no cadence beyond daily; no push channel).
