# B19 — The rest of the inference spec: regimes, Bayesian layer, chains, calibration, trials, on-demand exploration (migrations 0059–0061)

**What this is.** `specs/04-reasoning/requirements.md` §D (randomized micro-trials,
REQ-INF-2xx), §E (scored predictions and calibration, REQ-INF-3xx — the parts B7–B10
did not cover), §F.1 (on-demand exploration, REQ-INF-412/413), §G.2 (the probabilistic
layer, REQ-INF-520..527), §G.3 (regime detection, REQ-INF-540..545), §G.4 (chains across
lenses, REQ-INF-560..565). Three sessions. All free: `numpyro`+`jax[cpu]`, `dynamax`,
`networkx`, on GitHub Actions.

**ADRs:** ADR-0069 (regime HMM as built), ADR-0070 (Bayesian effect layer: model spec,
priors, ROPE), ADR-0071 (chains and the cross-lens map), ADR-0072 (calibration ledger),
ADR-0073 (micro-trials: the randomizer and what may be blinded).

## B19.1 — Regimes (§G.3) and the Bayesian layer (§G.2), migration 0059
- **Regimes.** `tools/engines/regimes.py` nightly: feature vector = the canonical
  metrics with ≥ 300 well-covered days (REQ-INF-541; Joe has ~2,380 days of sleep/HRV/
  RHR/steps — enough), standardized; `dynamax` Gaussian HMM with K ∈ {2,3,4} chosen by
  held-out log-likelihood on the last 20 % of days; outputs `analysis.regimes (day,
  state, p_state, code_version)` and `analysis.regime_profiles (state, metric, mean,
  dispersion, n_days)` (REQ-INF-543 — the state is *described by its metrics*, never
  named "good"/"bad"), plus run-length distribution per state (REQ-INF-545). Tier
  DESCRIPTIVE, no causal language (542/544). Envelope: `get_today.regime:{state,
  p_state, days_in_state, typical_run:{median, p90}, profile:[{metric, mean, unit}]}`
  and `get_domain(*).hero.regime_state`.
- **Bayesian effect layer.** `tools/engines/bayes.py`: for every PROMOTED/CONFIRMED
  hypothesis (and on demand from `ask` op `effect`), a NumPyro model (REQ-INF-520/521):
  standardized outcome ~ Normal(α + β·exposure_std + Σ γ·adjustment + u[dow] + u[season],
  σ); priors Normal(0,0.3) on β and γ (523, unless the register pre-registered another),
  half-normal(0,1) on scales (524); partial pooling only over day-of-week and season
  (525); missingness indicator modelled as a latent (527: include `m_t ~ Bernoulli(π)` and
  a coefficient on it; report it). NUTS, 4 chains × 1000 draws, seed = hash of
  hypothesis_id. Outputs `analysis.effects (hypothesis_id, as_of, beta_mean, beta_sd,
  hdi_lo, hdi_hi, p_direction, p_practical, rope, r_hat, ess, code_version)`;
  **ROPE** = ±0.1 SD of the outcome (declare; OQ-10 placeholder). Surfaces report
  `p_direction` and `p_practical` — **never a p-value** (526) — as "{p×100}% probability
  the effect is {positive}; {q×100}% that it is practically meaningful (beyond ±{rope}
  {unit})" with the EFSA verbal term paired numeral-first (REQ-TIER-026). B9's HAC
  estimate remains the confirmation-gate statistic; the Bayesian layer is what the
  surfaces *show* for CONFIRMED rows (record this division in ADR-0070).
- Tests: `test_REQ_INF_541_hmm_refuses_below_300_days`, `test_REQ_INF_543_state_described_by_metrics_not_labels`,
  `test_REQ_INF_545_run_length_distribution_present`, `test_REQ_INF_520_523_524_priors_as_specified`,
  `test_REQ_INF_526_no_p_value_in_any_envelope_field`, `test_REQ_INF_527_missingness_is_latent`,
  `test_ADR_0070_synthetic_known_beta_recovered_within_hdi`.

## B19.2 — Chains (§G.4), calibration (§E), on-demand exploration (§F.1), migration 0060
- **Chains.** `tools/engines/chains.py`: graph of edges = every hypothesis at
  PROMOTED+ (plus CANDIDATE edges only for *assembly* under 562's rule), weight = the
  standardized effect; paths up to length 3, no cycles, each node once (561);
  cumulative attenuation multiplicative (560: 0.3×0.3≈0.09); tier of a chain = weakest
  edge (REQ-TIER-046); prune to top 20 by |effect|×confidence (563); every rendered
  edge resolves to its evidence record (564). Context metrics never auto-promote to
  levers (565: `metric_registry.role` column `'lever'|'context'`, seeded; the
  recommendation engine reads it — amend B10 accordingly). Output `analysis.chains` and
  `get_findings.chains:[{path:[metric…], tiers:[…], chain_tier, attenuated_effect,
  edges:[{hypothesis_id, effect, n, n_eff, interval, estimator, reverse_check, family}]}]`.
- **Calibration ledger (REQ-INF-3xx).** `analysis.calibration (as_of, bucket, n,
  observed_rate, expected_rate, ece)` from every scored prediction (forecasts,
  resolutions, recommendations); bucket miscalibration per REQ-INF-325 → EFSA term
  downgrade (326); unresolvable rate > 0.25 → the system reports its own calibration at
  INSUFFICIENT (330). `get_trust.calibration` gains the reliability table; B8's ruling
  (b) reads `p_forecast` from here once n ≥ 20.
- **On-demand exploration (412/413).** `public.request_scan(p_driver_family text
  DEFAULT NULL, p_outcome_family text DEFAULT NULL)` writes `ops.scan_requests`; the
  nightly job runs a scoped scan for pending requests with the same calibration (null
  twin) and writes CANDIDATE rows exactly as the scheduled scan (413), family-limited to
  ≤ 20 variables per block (404). THE DESK gets a "Explore this pair of families" action.
- Tests: `test_REQ_INF_560_561_attenuation_and_no_cycles`, `test_REQ_TIER_046_chain_tier_is_weakest_edge`,
  `test_REQ_INF_563_pruned_to_top_20`, `test_REQ_INF_565_context_metric_never_becomes_lever`,
  `test_REQ_INF_325_326_bucket_miscalibration_downgrades_term`, `test_REQ_INF_330_unresolvable_rate_reports_insufficient`,
  `test_REQ_INF_412_413_on_demand_scan_writes_candidates_with_null_twin`.

## B19.3 — Randomized micro-trials (§D), migration 0061
- Tables exactly as REQ-INF-200 lists (`trials`, `trial_assignments`, `trial_deviations`),
  all columns named in 200 present; the complete row written before the first block (201).
- `public.propose_trial(p_exposure, p_outcome, p_block_days, p_weeks, p_mde)` → power
  computed (207) from the outcome's observed SD and lag-1 ρ (block-level t-test power,
  `statsmodels`); refused below 0.80 with the required duration stated (208); minimum 6
  weeks for EXPERIMENTAL eligibility (206); blinding recorded honestly (204/205 — for
  behavioural exposures `blinded=false` with the stated impossibility).
- Nightly `tools/engines/trials.py`: seeded PRNG assignment at block start (202),
  randomized block order, block > washout (203); deviation detection from captured
  exposure vs assigned arm (209); ITT primary, per-protocol labelled secondary (210);
  deviation proportion > 0.20 → INSUFFICIENT + one notice offering a shorter block (211/212).
- Result → `hypothesis_register` status `EXPERIMENTAL` only from a trial (REQ-TIER-015/016),
  never from observational data.
- Envelope: `get_findings.trials:[{trial_id, exposure, outcome, status, block_days,
  blocks_done, blocks_planned, current_arm (only if not blinded), deviation_rate, power,
  result?:{itt_effect, hdi, per_protocol_effect, tier}}]`; THE DESK gets "Propose a trial".
- Tests: `test_REQ_INF_201_trial_row_complete_before_first_block`, `test_REQ_INF_202_203_seeded_randomized_blocks_exceed_washout`,
  `test_REQ_INF_207_208_power_gate`, `test_REQ_INF_209_deviation_row`, `test_REQ_INF_210_itt_primary_pp_secondary`,
  `test_REQ_INF_211_212_deviation_rate_insufficient_single_notice`, `test_REQ_TIER_016_experimental_only_from_trial`.

## Done when (per session)
Migrations; jobs wired nightly (regimes, bayes, chains, calibration, trials); the
regime output on Joe's real 2,300+ days pasted (state profiles by metric); one proposed
trial's power computation pasted; all named tests; ADR-0069..0073; the §H traceability
of `specs/04-reasoning` updated; PROGRESS + WHAT I DID NOT DO.
