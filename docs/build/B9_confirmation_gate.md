# B9 — The confirmation gate: PROMOTED → CONFIRMED_OBSERVATIONAL, to spec (migration 0046)

**What this is.** The rung the ladder was promised on. REQ-TIER-012 and REQ-TIER-013
say exactly what PROMOTED and CONFIRMED_OBSERVATIONAL require; nothing built so far
meets either in full, which is why session 19 correctly refused to stamp CONFIRMED.
This build implements both requirements as written, at $0, with free libraries
(`statsmodels`, `dowhy`, `networkx`), on GitHub Actions, nightly. Two sessions
(B9.1 promotion to spec; B9.2 the confirmation gate).

**Requirement IDs satisfied:** REQ-TIER-012, REQ-TIER-013, REQ-TIER-014, REQ-TIER-023,
REQ-TIER-024, REQ-TIER-028, REQ-TIER-040, REQ-TIER-041, REQ-TIER-042, REQ-TIER-043,
REQ-TIER-044, RULE-20 (forward prediction scored), RULE-21 (n_eff), RULE-11/12.
**ADRs to write:** ADR-0050 (B9.1, "the specification curve and the promotion gate"),
ADR-0051 (B9.2, "the registered DAG and the confirmation gate").

## Step 0 — DISCOVER
```sql
SELECT hypothesis_id, status, rule_version FROM core.hypothesis_register WHERE status IN ('PROMOTED','CONFIRMED_OBSERVATIONAL');
SELECT metric, count(*) FROM analysis.panel WHERE day >= current_date - 365 GROUP BY 1 ORDER BY 2 DESC LIMIT 60;
```
`pip install statsmodels dowhy networkx` in the Actions job (add to the workflow's deps
step; pin versions). Confirm `import dowhy` works on the runner before writing code.

---

## B9.1 — Promotion to spec (REQ-TIER-012)

The resolver's look 1 (B8 v2 rule) currently promotes on one contrast. REQ-TIER-012
requires three things at promotion; add them to the look-1 path in `resolve.py` (v2
rows only; v1 semantics untouched):

1. **Hierarchical FDR at every level of its branch.** The family is `(driver family →
   outcome family)` as the scan already computes (`family_id`, `family_m` in
   `analysis.contrasts`). At look 1, BH-adjust the look-1 p across all watches evaluated
   that night *within the same family_id* (level 1) and across families (level 2, the
   tree-FDR the scan uses — import its function). Promote only if rejected at both.
2. **Specification curve ≥ 50 specifications.** `tools/engines/speccurve.py`:
   the grid is `transformation ∈ {raw, dow_demedian, detrend+dow_demedian}` ×
   `split ∈ {quartile, tertile, median}` × `trim ∈ {none, 1%, 5%}` ×
   `window ∈ {all post days, last 60 post days}` × `test ∈ {mann_whitney, welch_t}`
   = 108 specifications, all on post-registration data only. Record each spec's p and
   sign in `analysis.spec_curves (hypothesis_id, look, spec_id, transformation, split,
   trim, window, test, n, delta, p, same_sign, code_version, computed_at)`. The
   statistic reported: `share_sig` = share of specs with p<0.05 and registered sign.
3. **Circular-shift null.** Shift the outcome series by a random offset ≥ 30 days
   (the scan's `_shift`), recompute `share_sig` over the same 108 specs, repeat 20
   times; `null_median_share`. Promote only if `share_sig > null_median_share`.

Store on `analysis.watch_progress`: `share_sig`, `null_median_share`, `fdr_level1_q`,
`fdr_level2_q`. The ledger row for a promotion carries all four (add columns to
`core.hypothesis_resolutions`: `share_sig NUMERIC, null_share NUMERIC, q_l1 NUMERIC,
q_l2 NUMERIC`). If any of the three fails at look 1 → stay INSUFFICIENT with reason
`sign_unstable` (spec curve) or `low_n_eff` (FDR), ledgered.

`get_findings.watching[]` and `.promoted[]` (new list: PROMOTED rows) gain
`spec_curve:{n_specs, share_sig, null_median_share}` and `fdr:{q_l1, q_l2}`.
L3 renders them as text: "{share_sig×100}% of {n_specs} specifications agree (null
median {null_median_share×100}%)".

**REQ-TIER-028 counter-frame** at promotion: compute and store on the ledger row
`counter_frame_n` = number of post-registration days where the outcome was in its
bottom quartile *and* the exposure was in its bottom quartile (outcome-negative days
without the exposure). Every PROMOTED/CONFIRMED payload carries it; L3 renders
"{counter_frame_n} bad-outcome days happened without the exposure."

---

## B9.2 — The confirmation gate (REQ-TIER-013 / 014 / 023)

### The registered DAG (ADR-0051) — `config.dag_edges`
REQ-TIER-013 needs a "minimal sufficient adjustment set computed from the DAG". There is
no DAG yet. Register one, in config, editable only by migration, seeded from what the
ontology already asserts. Nodes are panel metrics or the two exogenous clocks.
```sql
CREATE TABLE IF NOT EXISTS config.dag_edges (
    src TEXT NOT NULL, dst TEXT NOT NULL, basis TEXT NOT NULL,   -- 'exogenous_clock' | 'physiology' | 'behaviour' | 'joe'
    PRIMARY KEY (src, dst));
INSERT INTO config.dag_edges VALUES
 ('day_of_week','*','exogenous_clock'), ('season','*','exogenous_clock'),
 ('alcohol_standard_drinks','sleep_asleep_min','physiology'), ('alcohol_standard_drinks','hrv_sdnn','physiology'),
 ('alcohol_standard_drinks','rhr','physiology'), ('alcohol_standard_drinks','sleep_efficiency','physiology'),
 ('sleep_asleep_min','hrv_sdnn','physiology'), ('sleep_asleep_min','rhr','physiology'),
 ('sleep_asleep_min','checkin_morning_energy','physiology'), ('sleep_asleep_min','checkin_morning_mood','physiology'),
 ('sleep_asleep_min','checkin_night_mood','physiology'), ('sleep_asleep_min','checkin_night_energy','physiology'),
 ('steps','sleep_asleep_min','behaviour'), ('exercise_min','sleep_asleep_min','behaviour'),
 ('exercise_min','hrv_sdnn','physiology'), ('strength_volume','hrv_sdnn','physiology'),
 ('screen_active_hours','sleep_asleep_min','behaviour'), ('screen_binge_min','sleep_onset_min','behaviour'),
 ('screen_active_hours','checkin_night_mood','behaviour'),
 ('spend.monetary_7d','checkin_night_stress','behaviour'),
 ('wrist_temp_f','hrv_sdnn','physiology'), ('resp_night','hrv_sdnn','physiology')
ON CONFLICT DO NOTHING;
```
`'*'` means "every metric" (the exogenous clocks are parents of everything). Any edge
not in this table does not exist for the purposes of adjustment. This DAG is **Joe's
to extend** by migration; the ADR must say the seed is a floor, not a claim about the
world, and list every edge with its basis. The DAG must be acyclic — `networkx` check
in a test.

### The gate — `tools/engines/confirm.py`, nightly after the resolver
For every `PROMOTED` row (v2) with ≥ 60 paired post-promotion days and coverage ≥ 0.60:

1. **Adjustment set.** Build the DAG with `networkx`; compute the minimal sufficient
   backdoor set for (exposure → outcome) with `dowhy.CausalModel(...).identify_effect()`
   (backdoor criterion). If no set identifies the effect → INSUFFICIENT(`no_adjustment_set`).
   Always include `day_of_week` (one-hot) and `season` (sin/cos of day-of-year).
2. **Estimate with Newey–West HAC.** OLS of outcome(t+lag) on exposure(t) + adjustment
   set, post-registration data only, `statsmodels` `cov_type='HAC'`,
   `maxlags = floor(4·(n/100)^(2/9))` (the standard rule). Effect in **absolute outcome
   units** (REQ-TIER-024), with the 95 % interval.
3. **E-value.** Convert the standardized effect (β / SD of outcome) to an approximate
   risk ratio via `RR ≈ exp(0.91·d)` (Chinn 2000; state it as an approximation in the
   payload), then `E = RR + sqrt(RR·(RR−1))` at the point estimate **and at the interval
   limit nearest the null** (REQ-TIER-013). Store both.
4. **Negative controls (REQ-TIER-014).**
   (a) *Negative-control outcome*: the panel metric with no directed path from the
   exposure in the DAG and the highest coverage in the window; rerun step 2 with it as
   outcome; pass iff its p ≥ 0.20.
   (b) *Negative-control exposure*: the exposure shifted **forward** by `lag + 7` days
   (future exposure predicting past outcome); pass iff p ≥ 0.20.
   Either failure → REFUTED, ledgered with the check name, and a DESCRIPTIVE statement
   queued for the next brief (`analysis.brief_notes` — a small table `get_today` reads
   as `notices[]`: `{kind:'refutation', text, hypothesis_id, at}`).
5. **DoWhy refutation tests.** `placebo_treatment_refuter`, `random_common_cause`,
   `data_subset_refuter` (subset 0.8, 20 simulations). Pass iff the placebo effect's
   p ≥ 0.20 and the other two estimates stay within the HAC interval. Any failure → REFUTED.
6. **Decision.** All of 1–5 pass and the HAC interval excludes 0 with the registered
   sign → `CONFIRMED_OBSERVATIONAL`. Ledger row carries: `adjustment_set`, `beta`,
   `ci_lo`, `ci_hi`, `hac_maxlags`, `e_value_point`, `e_value_limit`, `nc_outcome_metric`,
   `nc_outcome_p`, `nc_exposure_p`, `refuter_results` (jsonb), `counter_frame_n`. Add
   these columns to `core.hypothesis_resolutions` (all nullable).
7. **Re-confirmation.** Every CONFIRMED row is re-run monthly on a rolling window; a
   failure demotes to PROMOTED (REQ-TIER-041/042/043) with a ledger row and a brief notice.
8. **Forward prediction scoring (RULE-20, OQ-44a).** At look 2 and at every monthly
   re-run, score the pending `core.predictions` row for the hypothesis: `outcome_bool`,
   `brier`, `resolved_at`.

### Envelope additions (all additive)
`get_findings.confirmed[]` gains `effect:{beta, unit, ci:[lo,hi], hac_maxlags}`,
`e_value:{point, limit}`, `negative_controls:{outcome_metric, outcome_p, exposure_p}`,
`refuters:{placebo_p, random_common_cause_ok, subset_ok}`, `adjustment_set:[...]`,
`counter_frame_n`, `next_recheck`. L3's "not yet computed" line is replaced by these.
`get_today` gains `notices[]` (demotions/refutations since the last brief, REQ-TIER-043).

### Tests `tests/test_confirmation_gate.py` (synthetic series; seeded RNG; rolled back)
```
test_ADR_0051_dag_is_acyclic
test_REQ_TIER_013_adjustment_set_is_minimal_backdoor_for_seed_edges
test_REQ_TIER_013_hac_maxlags_follows_rule
test_REQ_TIER_013_e_value_at_point_and_limit_for_known_beta
test_REQ_TIER_014_negative_control_outcome_failure_refutes_and_writes_notice
test_REQ_TIER_014_future_exposure_control_failure_refutes
test_REQ_TIER_014_dowhy_placebo_failure_refutes
test_REQ_TIER_040_confirm_requires_promoted_first
test_REQ_TIER_041_042_monthly_recheck_failure_demotes_with_ledger_row
test_RULE_20_forward_prediction_is_scored_at_look_2
test_REQ_TIER_012_spec_curve_has_108_specs_and_null_share
test_REQ_TIER_028_counter_frame_stored_on_promotion
test_ADR_0050_confirmation_on_pure_noise_synthetic_is_below_5_percent   (200 seeded null runs on synthetic ρ=0.5 series; assert rate < 0.05)
```
The last test is the honesty proof for this build; it must be in CI.

## Done when
Both migrations; `confirm.py` and `speccurve.py` in the nightly workflow after
`run_resolve.py`; the null-rate test passes with its measured rate pasted; ADR-0050/0051
with the full DAG listed; DECISIONS rows; `update_features.py`; PROGRESS + WHAT I DID
NOT DO (must state: the RR conversion is an approximation; the DAG is a seed; no
micro-trials / EXPERIMENTAL tier).
