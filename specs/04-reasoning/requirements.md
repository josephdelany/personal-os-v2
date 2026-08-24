# 04 — REASONING LAYER: REQUIREMENTS (EARS)

**Spec:** `specs/04-reasoning/requirements.md` · **Subject:** Personal OS, single user (Joe), n=1
**Grammar:** EARS (Mavin & Wilkinson). Five patterns only. `SHALL` is binding. `SHOULD` does not appear in this document.
**Sources:** `RESEARCH/C_REASONING_LAYER.md` (§1–§7), `RESEARCH/B_COMPARABLE_SYSTEMS.md` §1.2 (PHIA), `RESEARCH/G_REPURPOSE_AUDIT.md` §2–§3, `PERSONAL_OS_BUILD/09_PROGRAM.md` §1/§11/§12, `PERSONAL_OS_BUILD/10_STORY_LAYER.md` §10/§11, `RESEARCH/F_HOW_TO_SPEC.md` §2.1.

**ID scheme:** `REQ-INF-nnn` inference/statistics · `REQ-TIER-nnn` evidence ladder · `REQ-NAR-nnn` narration/language · `REQ-ASK-nnn` open-ended question answering.
IDs are stable and never reused. Every implementation commit cites the IDs it satisfies.

---

## 0. PREAMBLE — THE PHIA FINDING AND WHAT IT SETTLES

Google's PHIA (*Nature Communications*, published 12 Jan 2026 — "Transforming wearable data into personal health insights using large language model agents") evaluated an **objective benchmark of 4,000 personal-health questions** requiring numerical reasoning over one person's wearable data (a separate open-ended set was also studied; 4,000 is the objective benchmark, not the total):

| System | Accuracy |
|---|---|
| Text-only numerical reasoning — the LLM does the arithmetic in its head | **22%** |
| Custom GPT-4 chain-of-thought | 53.6% |
| One-shot code generation, no loop | 74% |
| **PHIA — ReAct loop, LLM writes code, deterministic sandbox executes it** | **84%** |

Same weights. The swing decomposes and should not be quoted as one lump: executing code at all takes 22%→74% (the large gap — this is what "the LLM never computes" buys), and the ReAct loop then adds 74%→84% (~10 further points). Caveats: Gemini 1.0 Ultra for all main results (the paper also reports a GPT-4 chain-of-thought comparison, the 53.6% row above), and the result has not been independently replicated. The architectural conclusion below is robust to both — it does not depend on the exact 84, only on "executed ≫ in-head."

**This settles the architecture of the entire reasoning layer, and every requirement below is downstream of it:**

> **All math is deterministic, auditable, and executed. The LLM plans the computation and narrates the result. The LLM never computes.**

Three independent lines of evidence converge on this rule: PHIA's benchmark (`B` §1.2), `C_REASONING_LAYER` §4.6's "the LLM never touches raw data and never computes a number," and the old spec's own `09 §11` rule 2 ("never let the language layer promote a rung, invent a number, or generate a claim"), which `G` §3.1 marks **KEEP AS IS** and instructs to "treat as settled." This document does not re-litigate it.

**Doctrinal position of this document.** `G` §2.8 finds the old restraint doctrine ~80% intact. Two things change and only two: (1) the *behaviour when the evidence standard is not met* — silence becomes calibrated disclosure; (2) the *scope of subject matter*. Every statistical prohibition, every privacy prohibition, every anti-gamification prohibition, and every LLM-narrates-only rule is carried forward unchanged.

**Definitions used throughout.**
- `n_eff` — effective sample size after serial-correlation correction, `n_eff ≈ n(1−ρ)/(1+ρ)` for an AR(1) process (`C` §1.2).
- `coverage` — fraction of days in the analysis window on which the metric has a non-null, non-stale observation (`C` §6.5, `v_coverage`).
- `tier` — one of the six values in §A, computed by the statistics job, stored on the finding row, immutable downstream.
- `metric_registry` — the table defining domain, unit, scale type, legal transforms, `can_be_cause`, `can_be_effect`, `is_negative_control`, `self_report`, `max_staleness_days` for every metric (`C` §6.2).
- **Refusal string** — a stored, versioned, non-LLM-generated string returned in place of a claim. Refusal strings are enumerated in §H and §I and are testable byte-for-byte.

## A. THE CLAIM LADDER (REQ-TIER)

Six tiers. Every emitted sentence sits on exactly one, the tier is computed by the statistics job, stored, and carried to the pixel (`09` §1, `C` §7).

| Tier | Produced by | Shown to Joe? | Permitted vocabulary |
|---|---|---|---|
| `DESCRIPTIVE` | Layer 2 (description, regime HMM) | Yes | "is", "was", "has been", "typically lasts", "on N of the last M days" |
| `CANDIDATE` | Layer 3 (PCMCI+, VAR-LiNGAM, regularized VAR) | **EXPLORATORY-labelled surface only**, once built+proven (RULE-17); never on a finding surface | the `EXPLORATORY` label vocabulary only — never confirmed-tier terms |
| `PROMOTED` | Layer 4 (hierarchical FDR + spec curve + shift null) | Yes | "robust across N specifications", "precedes", "predictive lead" |
| `CONFIRMED_OBSERVATIONAL` | Layer 5 (backdoor adjustment, HAC, E-value, refuters) | Yes | "associated with, adjusting for {set}", "E-value N" |
| `EXPERIMENTAL` | Layer 6 (randomized micro-trial, ITS) | Yes | "caused", full stop |
| `INSUFFICIENT` | Layer 1 or Layer 4 | **Yes — returnable and displayable** | "we cannot give a probability for this", "based on what we have", "not enough to say" |

**The doctrinal change.** `09 §1` rule 6 said *"anything that fails to reach rung 2 is not shown at all."* `G` §2.1 **OVERTURNS** it. Joe's words: *"tell me that we dont have enough evidence but based on what we have, its this. and if its not close to having enough, just tell me that you dont have it."* Silence is epistemically worse than disclosure: a hidden sub-threshold pattern is indistinguishable from a pattern that was never looked for, so Joe cannot tell whether the system is being careful or is broken. `INSUFFICIENT` is therefore a first-class return value, not an error state, and it has two sub-modes — **partial** ("based on what we have, it's this") and **absent** ("we don't have it").

### A.1 Tier assignment and immutability

**REQ-TIER-001 (Ubiquitous)**
The reasoning layer SHALL assign exactly one tier from {`DESCRIPTIVE`, `CANDIDATE`, `PROMOTED`, `CONFIRMED_OBSERVATIONAL`, `EXPERIMENTAL`, `INSUFFICIENT`} to every row in `findings`, and SHALL reject any insert where `tier` is null or outside that set.

**REQ-TIER-002 (Ubiquitous)**
The reasoning layer SHALL compute `tier` in the deterministic statistics job and SHALL store it on the `findings` row together with `code_version`, `n`, `n_eff`, and `coverage`.

**REQ-TIER-003 (Ubiquitous)**
The narration layer SHALL NOT write to the `tier` column of any `findings` row.

**REQ-TIER-004 (Unwanted behaviour)**
IF a rendered surface emits a claim whose displayed tier differs from the `tier` stored on its source `findings` row, THEN the render pipeline SHALL discard the rendered output, emit the non-LLM template rendering instead, and write a row to `render_violations` with the finding ID, the expected tier, and the observed tier.

**REQ-TIER-005 (Ubiquitous)**
The reasoning layer SHALL carry `finding_id`, `tier`, `n`, `n_eff`, `coverage`, and `code_version` in the payload of every claim delivered to any surface.

### A.2 Evidence required per tier

**REQ-TIER-010 (Event-driven)**
WHEN a computation produces only counts, sums, means, trends, regime-state assignments, or seasonal decompositions with no cross-metric effect estimate, the reasoning layer SHALL assign tier `DESCRIPTIVE`.

**REQ-TIER-011 (Event-driven)**
WHEN a hypothesis-generation method emits a candidate edge, the reasoning layer SHALL insert it into `hypothesis_register` with status `CANDIDATE` and SHALL NOT create a `findings` row for it.

**REQ-TIER-012 (Event-driven)**
WHEN a `CANDIDATE` hypothesis passes hierarchical-FDR rejection at every level of its branch, has a specification curve computed over at least 50 defensible specifications, and has a circular-shift null showing its significant-specification share exceeds the null median, the reasoning layer SHALL promote it to `PROMOTED` and SHALL freeze a pre-registration record per REQ-INF-101.

**REQ-TIER-013 (Event-driven)**
WHEN a `PROMOTED` hypothesis is estimated on post-registration data only, with a minimal sufficient adjustment set computed from the DAG, Newey–West HAC standard errors, a computed E-value at both the point estimate and the interval limit nearest the null, all negative-control checks passed, and all DoWhy refutation tests passed, the reasoning layer SHALL assign tier `CONFIRMED_OBSERVATIONAL`.

**REQ-TIER-014 (Unwanted behaviour)**
IF any negative-control check fails or any refutation test fails for a `PROMOTED` hypothesis, THEN the reasoning layer SHALL set its status to `REFUTED`, SHALL NOT assign `CONFIRMED_OBSERVATIONAL`, and SHALL emit a `DESCRIPTIVE`-tier statement to Joe naming the hypothesis and the check that failed.

**REQ-TIER-015 (Event-driven)**
WHEN a randomized micro-trial completes with its pre-specified minimum number of blocks and its pre-specified primary outcome analysis, the reasoning layer SHALL assign tier `EXPERIMENTAL` to the resulting finding.

**REQ-TIER-016 (Ubiquitous)**
The reasoning layer SHALL assign tier `EXPERIMENTAL` only to findings whose exposure was assigned by the system's randomizer, and SHALL NOT assign `EXPERIMENTAL` to any finding derived from observational data.

**REQ-TIER-017 (Event-driven)**
WHEN coverage for any metric in a requested analysis is below 0.60 over the analysis window, or `n_eff` is below 20, the reasoning layer SHALL assign tier `INSUFFICIENT`.

**REQ-TIER-018 (Ubiquitous)**
The reasoning layer SHALL record on every `INSUFFICIENT` finding a machine-readable `insufficiency_reason` from the closed set {`low_coverage`, `low_n_eff`, `informative_missingness`, `no_adjustment_set`, `sign_unstable`, `metric_absent`, `window_too_short`}.

### A.3 Language permitted per tier

**REQ-TIER-020 (Ubiquitous)**
The reasoning layer SHALL maintain a `tier_vocabulary` table mapping each tier to a closed list of permitted verbs and qualifiers, and the vocabulary linter (REQ-NAR-020) SHALL read that table rather than a hardcoded list.

**REQ-TIER-021 (Ubiquitous)**
The reasoning layer SHALL permit the word "caused" and its inflections only on claims at tier `EXPERIMENTAL`.

**REQ-TIER-022 (Ubiquitous)**
The reasoning layer SHALL name any lead-lag statistic `predictive_lead` in every table, column, API field, and rendered string, and SHALL NOT use the identifier `granger_cause` anywhere in the codebase.

**REQ-TIER-023 (Ubiquitous)**
The reasoning layer SHALL render every `CONFIRMED_OBSERVATIONAL` claim with its adjustment set, its E-value at the point estimate, and its negative-control result attached in the same payload.

**REQ-TIER-024 (Ubiquitous)**
The reasoning layer SHALL express effect sizes in absolute units with the unit named, and SHALL NOT express an effect size as a percentage change of the outcome.

**REQ-TIER-025 (Ubiquitous)**
The reasoning layer SHALL report Bayesian credible intervals and direct probability-of-direction statements, and SHALL NOT render a frequentist confidence interval on any user-facing surface.

**REQ-TIER-026 (Ubiquitous)**
The reasoning layer SHALL pair every verbal probability term with the numeric probability, numeral first, using the EFSA approximate probability scale (almost certain 99–100%, extremely likely 95–99%, very likely 90–95%, likely 66–90%, about as likely as not 33–66%, unlikely 10–33%, very unlikely 5–10%, extremely unlikely 1–5%, almost impossible 0–1%).

**REQ-TIER-027 (Ubiquitous)**
The reasoning layer SHALL include "unable to give any probability: range 0–100%" as a legal value of the verbal probability field, and SHALL treat it as a normal return value rather than an error.

**REQ-TIER-028 (Ubiquitous)**
The reasoning layer SHALL state the counter-frame alongside every `PROMOTED` or higher claim — the count of outcome-negative days on which the exposure was absent — in the same payload as the claim.

### A.4 INSUFFICIENT is returnable

**REQ-TIER-030 (Event-driven)**
WHEN a question resolves to tier `INSUFFICIENT` with `insufficiency_reason` in {`low_coverage`, `low_n_eff`, `sign_unstable`}, the reasoning layer SHALL return the partial disclosure form: the point estimate, the interval, `n`, `n_eff`, `coverage`, the tier label `INSUFFICIENT`, and the sentence "This is not enough evidence to be confident. Based on what we have, it is this."

**REQ-TIER-031 (Event-driven)**
WHEN a question resolves to tier `INSUFFICIENT` with `insufficiency_reason` in {`metric_absent`, `window_too_short`, `informative_missingness`, `no_adjustment_set`}, the reasoning layer SHALL return the absent disclosure form: the refusal string "We do not have enough to answer this.", the named missing or compromised input, and the specific condition that would make it answerable.

**REQ-TIER-032 (Ubiquitous)**
The reasoning layer SHALL NOT suppress, hide, or omit a computed result on the grounds that its tier is `INSUFFICIENT`.

**REQ-TIER-033 (Ubiquitous)**
The reasoning layer SHALL terminate every `INSUFFICIENT` response with either a named quantity of additional data required, or a concrete proposed randomized micro-trial specification that would answer the question.

**REQ-TIER-034 (Unwanted behaviour)**
IF an `INSUFFICIENT` response is rendered without either a named data requirement or a proposed trial, THEN the render pipeline SHALL reject the response and SHALL return the absent disclosure form instead.

**REQ-TIER-035 (State-driven)**
WHILE a finding has status `CANDIDATE`, the reasoning layer SHALL exclude it from every finding surface, every reading-intended export, every notification payload, and every LLM prompt that would present it as established, and SHALL render it only on the `EXPLORATORY`-labelled surface (RULE-17), never in confirmed-tier vocabulary. (Reworded 2026-08-24; requirements-audit C-2, ADR-0029 RULE-17 SCOPE-shell reversal.)

### A.5 Demotion and movement between tiers

**REQ-TIER-040 (Ubiquitous)**
The reasoning layer SHALL permit tier promotion only in the order `CANDIDATE` → `PROMOTED` → `CONFIRMED_OBSERVATIONAL` → `EXPERIMENTAL`, and SHALL reject any promotion that skips a step.

**REQ-TIER-041 (Ubiquitous)**
The reasoning layer SHALL permit demotion from any tier to any lower tier or to `REFUTED` in a single step.

**REQ-TIER-042 (Event-driven)**
WHEN a finding is demoted, the reasoning layer SHALL write a row to `tier_history` recording the finding ID, previous tier, new tier, timestamp, the machine-readable demotion reason, and the ID of the job that performed it.

**REQ-TIER-043 (Event-driven)**
WHEN a finding is demoted, the reasoning layer SHALL surface the demotion to Joe within the next brief, naming the previous claim and the reason it no longer holds.

**REQ-TIER-044 (Ubiquitous)**
The reasoning layer SHALL NOT require human approval for a demotion.

**REQ-TIER-045 (State-driven)**
WHILE coverage for any metric in a `CONFIRMED_OBSERVATIONAL` finding's adjustment set is below 0.60 in the trailing 90 days, the reasoning layer SHALL render that finding at tier `INSUFFICIENT` with `insufficiency_reason='low_coverage'`.

**REQ-TIER-046 (Ubiquitous)**
The reasoning layer SHALL label an assembled multi-edge explanation at the tier of its weakest constituent edge, and SHALL apply and display cumulative attenuation across the chain.

**REQ-TIER-047 (Ubiquitous)**
The reasoning layer SHALL NOT emit a recommendation phrased as a causal-effect claim below tier `CONFIRMED_OBSERVATIONAL`.

**REQ-TIER-048 (Optional feature)**
WHERE a recommendation is emitted below tier `CONFIRMED_OBSERVATIONAL` as a decision-under-uncertainty, the reasoning layer SHALL attach the tier label, the effect size with interval, `n` and `coverage`, and an explicit statement of what evidence would change the answer.

**REQ-TIER-049 (Unwanted behaviour)**
IF a recommendation is rendered without its tier label and its interval, THEN the build SHALL fail the acceptance suite and the surface SHALL NOT ship.

### A.6 The EXPLORATORY surface (RULE-17, Missing-F)

*The RULE-17 SCOPE shell (ADR-0029) permits `CANDIDATE`/exploratory structure-discovery output to be displayed, carrying an explicit `EXPLORATORY` label, on a surface built and proven before any continuous exploration ships. These requirements define that surface — its row source, its format, its build-before-exploration gate, and its vocabulary. The integrity core is unchanged — such output is never promoted to a finding and never rendered in confirmed-tier vocabulary (REQ-INF-401, REQ-INF-402).*

**REQ-TIER-050 (Ubiquitous)**
The EXPLORATORY surface SHALL render a `CANDIDATE`-status row only as text and labels carrying an explicit `EXPLORATORY` tag, SHALL emit only text and label render components, and SHALL NOT render it as a chart, plot, scatter, trend line, edge or network diagram, heat map, or any other graphical encoding (ADR-0032, reinforcing REQ-NAR-035).

**REQ-TIER-051 (State-driven)**
WHILE the EXPLORATORY surface has not passed the acceptance suite that proves it renders `CANDIDATE` output under its `EXPLORATORY` label (RULE-17's "built and proven" gate, enforced as in REQ-TIER-049), the reasoning layer SHALL NOT ship any continuous exploration — the label surface precedes the generation that feeds it.

**REQ-TIER-052 (Ubiquitous)**
The EXPLORATORY surface SHALL draw its copy only from the `EXPLORATORY` row of `tier_vocabulary` (illustrative members: "a generator flagged", "candidate", "exploratory, not a finding", "may", "might", "unverified"; the closure of every per-tier vocabulary row is the open question in §A.UNRESOLVED), and the per-tier vocabulary linter of REQ-NAR-020 SHALL fail the build if any confirmed-tier verb (for example "precedes", "predicts", "predictive lead", "causes") appears on it.

**REQ-TIER-053 (Ubiquitous)**
The EXPLORATORY surface SHALL source its rows from `hypothesis_register` entries whose `status = 'CANDIDATE'` and SHALL render no row of any other status; this is the one surface on which a `CANDIDATE` row is displayable (REQ-INF-402), and the routing of generator/continuous-exploration output to it is by this source binding, not by any push.

### A.NON-GOALS
- Not a goal: mapping this ladder onto GRADE's High/Moderate/Low/Very Low labels for display. GRADE's five downgrade and three upgrade domains are used as *inputs* to tier computation; the GRADE label itself is never shown.
- Not a goal: a numeric confidence score per finding. Tier plus interval plus coverage is the contract; a single scalar invites exactly the composite-score failure mode the old spec bans.
- Not a goal: user-adjustable tier thresholds. Thresholds are versioned in code, not in settings.
- Not a goal: preserving the old four-rung numbering. Rungs 1–4 map onto `DESCRIPTIVE`/`PROMOTED`/`CONFIRMED_OBSERVATIONAL`/recommendation-gate; `CANDIDATE` and `INSUFFICIENT` are genuinely new (`G` §3.10).

### A.ALTERNATIVES CONSIDERED
- **Keep `09 §1` rule 6 (hide everything below rung 2).** Rejected by `G` §2.1 as the most direct conflict in the corpus, and because it contradicts `09 §11` rule 8 ("never hide an inconclusive result") within the same document. Overturning rule 6 resolves the contradiction in favour of rule 8.
- **Four tiers, folding `CANDIDATE` into an internal status flag.** Rejected: making `CANDIDATE` a tier rather than a flag means its display property is enforced by the same mechanism that enforces every other tier property, and is testable with one test rather than N. (Post-ADR-0029/C-2: the property is now "never shown *on a finding surface*, shown only on the EXPLORATORY-labelled surface once built+proven per RULE-17" — the tier mechanism enforces the narrowed property just as it enforced the former absolute.)
- **Ban hedged phrasing outright (`10 §10`).** Rejected per `G` §2.5: calibrated disclosure is *made of* hedged phrasing. Replaced by the per-tier closed vocabulary plus a linter (REQ-TIER-020, REQ-NAR-020), converting a judgment call into a mechanical check.
- **Show frequentist CIs.** Rejected on `C` §5.1: Hoekstra et al. found 442 students, 34 master's students and 120 researchers endorsed on average 3.51 / 3.24 / 3.45 false statements out of six about a 95% CI; only 2–3% got all six right.

### A.UNRESOLVED QUESTIONS
- The coverage threshold 0.60 and `n_eff` floor 20 in REQ-TIER-017 are not derived from any number in the research files. They are placeholders pending a calibration study on Joe's own data.
- The minimum specification count of 50 in REQ-TIER-012 is chosen by analogy to the 180- and 240-specification examples in `C` §3.2 and §5.5; the research does not state a minimum.
- Whether `DESCRIPTIVE` findings should also carry forward predictions (§E) or be exempt. Exempting them is cheaper; including them gives a much larger calibration sample.
- How `EXPERIMENTAL` findings decay. A randomized result from 2026 may not describe Joe in 2029. No half-life is specified in the research.

## B. MULTIPLICITY CONTROL (REQ-INF-0xx)

With p=80 daily metrics and lags {0,1,2,3,7}, pairwise directed tests number 80x79x5 = 31,600. Add moderators and legal transforms and the specification space crosses 10^6. At alpha=0.05 with no correction, a system testing 10^6 nulls hands Joe roughly 50,000 false discoveries, and an LLM then writes physiologically-flavoured narratives about them (`C` §3.1). This section is the machinery that prevents that.

### B.1 Hierarchical / tree FDR

**REQ-INF-001 (Ubiquitous)**
The reasoning layer SHALL construct the multiplicity tree with three levels — domain-pair, then variable-pair, then lag/specification — and SHALL derive every node of that tree from `metric_registry` via the view `v_metric_tree`.

**REQ-INF-002 (Ubiquitous)**
The reasoning layer SHALL apply Benjamini–Hochberg within each family of the tree, and SHALL test a family only if its parent hypothesis was rejected (Yekutieli 2008 hierarchical FDR).

**REQ-INF-003 (Ubiquitous)**
The reasoning layer SHALL persist, for every test performed, the family identifier, the family size `m`, the raw p-value, and the adjusted q-value, and SHALL NOT recompute family size at render time.

**REQ-INF-004 (Ubiquitous)**
The reasoning layer SHALL NOT use plain Benjamini–Yekutieli as the primary multiplicity gate for the search tree, because the harmonic penalty factor is approximately 10.9 at m=30,000, which makes it useless as a discovery engine at this scale.

**REQ-INF-005 (Ubiquitous)**
The reasoning layer SHALL prune from the search space, before any multiplicity correction is applied, every ordered pair whose source metric has `can_be_cause = false` or whose target metric has `can_be_effect = false`.

**REQ-INF-006 (Event-driven)**
WHEN a new metric is added to `metric_registry`, the reasoning layer SHALL extend the search tree from the registry automatically and SHALL recompute family sizes at the next scheduled search run without a code change.

**REQ-INF-007 (Ubiquitous)**
The reasoning layer SHALL report, with every branch of the tree it descends into, the number of tests performed at each level and the q threshold applied at that level.

**REQ-INF-008 (Unwanted behaviour)**
IF a test is executed whose family is not registered in `v_metric_tree`, THEN the reasoning layer SHALL discard the result, SHALL NOT insert any candidate, and SHALL write a row to `pipeline_violations` with reason `unregistered_family`.

**REQ-INF-009 (Ubiquitous)**
The reasoning layer SHALL NOT author or modify the family catalog after inspecting the results of a run.

### B.2 Serial correlation — mandatory, not optional

**REQ-INF-020 (Ubiquitous)**
The reasoning layer SHALL compute every effect estimate with Newey–West / HAC autocorrelation-robust standard errors or an explicit AR(1) error term, and SHALL NOT compute any user-facing effect estimate under i.i.d. error assumptions.

**REQ-INF-021 (Ubiquitous)**
The reasoning layer SHALL compute and store `rho`, the estimated lag-1 autocorrelation of the residual series, alongside every effect estimate.

**REQ-INF-022 (Ubiquitous)**
The reasoning layer SHALL compute `n_eff = n(1−rho)/(1+rho)` for every effect estimate, SHALL store it on the finding row, and SHALL render `n_eff` rather than `n` as the headline sample size on every surface.

**REQ-INF-023 (Ubiquitous)**
The reasoning layer SHALL render `n` and `n_eff` together whenever a sample size is shown, and SHALL NOT render `n` alone.

**REQ-INF-024 (Ubiquitous)**
The reasoning layer SHALL record the HAC `maxlags` value used for each estimate on the finding row.

**REQ-INF-025 (Unwanted behaviour)**
IF an estimate is produced without a stored `rho` and `n_eff`, THEN the reasoning layer SHALL refuse to create a `findings` row for it and SHALL write a row to `pipeline_violations` with reason `missing_serial_correlation_handling`.

**REQ-INF-026 (Ubiquitous)**
The reasoning layer SHALL NOT apply a washout period to an observational analysis without also applying autocorrelation-robust inference, because washout with naive inference raised the false-positive rate to 0.30+ at AR(1)≈0.70 and 0.40–0.50 at AR(1)≈0.75–0.80 in the HDSR simulations.

### B.3 Specification curves and circular-shift nulls

**REQ-INF-030 (Event-driven)**
WHEN a candidate hypothesis is evaluated for promotion, the reasoning layer SHALL enumerate the full cross-product of defensible specifications from `metric_registry.legal_transforms`, the declared exclusion rules, and the declared control sets, and SHALL estimate every enumerated specification.

**REQ-INF-031 (Ubiquitous)**
The reasoning layer SHALL store, for every specification curve, the specification count, the median effect, the fraction of specifications sharing the sign of the median, and the fraction significant in that direction.

**REQ-INF-032 (Ubiquitous)**
The reasoning layer SHALL calibrate every specification curve against a circular-shift null in which the exposure series is circularly rotated by a random offset, preserving each series' own autocorrelation while destroying cross-series alignment.

**REQ-INF-033 (Ubiquitous)**
The reasoning layer SHALL run at least 200 circular shifts on the weekly schedule and at least 2,000 on the monthly schedule.

**REQ-INF-034 (Ubiquitous)**
The reasoning layer SHALL store and render, with every specification-curve result, the fraction of specifications significant under the shifted null, and SHALL NOT render the observed significant fraction without the null fraction beside it.

**REQ-INF-035 (Ubiquitous)**
The reasoning layer SHALL report the effect of every hypothesis as a lag profile over lags {0,1,2,3,7}, and SHALL NOT report a single lag coefficient as "the effect".

**REQ-INF-036 (Event-driven)**
WHEN a candidate's effect is significant at exactly one lag out of the five tested and changes sign at another tested lag, the reasoning layer SHALL assign `INSUFFICIENT` with `insufficiency_reason='sign_unstable'` and SHALL NOT promote it.

**REQ-INF-037 (Ubiquitous)**
The reasoning layer SHALL present the specification curve as the default output format for any promoted-or-higher finding, including the dashboard of which analytic choices produced each point.

**REQ-INF-038 (Ubiquitous)**
The reasoning layer SHALL report the empirical null distribution of the *number of discoveries* per pipeline run, so that a run's discovery count can be stated against the shuffled-data median and 95th percentile.

### B.NON-GOALS
- Not a goal: family-wise error control (Bonferroni/Holm) anywhere in the search tree. FDR is the correct target for a discovery engine.
- Not a goal: exhaustive all-pairs search over the full 80-metric space in one run. Discovery runs on domain blocks of at most 20 variables (§F).
- Not a goal: reporting a corrected p-value to Joe. q-values and family sizes are stored for audit; the user-facing quantity is the specification curve plus the shifted-null comparison.
- Not a goal: Model-X knockoffs. See §F.

### B.ALTERNATIVES CONSIDERED
- **Plain Benjamini–Yekutieli across the flat 31,600-test space.** Correct under arbitrary dependence, and rejected: the R documentation itself notes BY is more conservative than Bonferroni for small p, and the ~10.9x penalty at m=30,000 kills every real effect Joe has.
- **Plain Benjamini–Hochberg flat.** Rejected: BH controls FDR under independence or PRDS, and these tests are massively and not always positively dependent.
- **Model-X knockoffs for exact finite-sample FDR control.** Rejected: knockoffs require a known joint distribution of the covariates, which is unobtainable for 80 heterogeneous, zero-inflated, autocorrelated life variables; non-exchangeability degrades FDR control.
- **Parametric p-values only, no permutation nulls.** Rejected: on autocorrelated daily data the analytic null the FDR sits on is itself wrong; circular-shift nulls require no distributional assumption and implicitly correct for every forking path the code actually takes.

### B.UNRESOLVED QUESTIONS
- The exact block structure of the domain level. `C` §3.3 estimates ~15 domains giving ~105 domain-pair tests; the actual domain list for Joe's registry is not yet fixed.
- Which block-level omnibus statistic to use at the domain level — canonical correlation, distance correlation, or a permutation test on the max absolute partial correlation within the block. `C` §3.3 lists all three without ranking them.
- The HAC `maxlags` selection rule. `C` §1.2 names the statsmodels parameter but not a selection procedure.
- Whether the stationary bootstrap is preferable to circular shift for series with strong weekly seasonality. Not addressed in the research.

## C. PRE-REGISTRATION AS A DATABASE CONSTRAINT (REQ-INF-1xx)

`C` §3.5 calls this "the highest-leverage 200 lines of code in the entire project." The idea: a longitudinal single-subject system gets out-of-sample confirmation for free, because **a hypothesis generated today can be confirmed on data that has not been collected yet.** That is a genuine out-of-sample test with no multiplicity problem, because the confirmation test is pre-specified by construction. The requirement is that this be a *schema invariant*, not a discipline.

**REQ-INF-100 (Ubiquitous)**
The reasoning layer SHALL maintain a `hypothesis_register` table containing at minimum: `hypothesis_id`, `exposure_metric`, `outcome_metric`, `lag_days`, `direction`, `transformation`, `adjustment_set`, `test_statistic`, `preregistered_at`, `confirmation_data_from`, `resolution_rule`, `status`.

**REQ-INF-101 (Event-driven)**
WHEN a hypothesis is promoted to `PROMOTED`, the reasoning layer SHALL write a `hypothesis_register` row with `preregistered_at = now()` and `confirmation_data_from = now()`, and SHALL populate every field in REQ-INF-100 in the same transaction.

**REQ-INF-102 (Ubiquitous)**
The `hypothesis_register` table SHALL enforce `confirmation_data_from >= preregistered_at` as a CHECK constraint.

**REQ-INF-103 (Ubiquitous)**
The `hypothesis_register` table SHALL reject any UPDATE to `exposure_metric`, `outcome_metric`, `lag_days`, `direction`, `transformation`, `adjustment_set`, `test_statistic`, `preregistered_at`, `confirmation_data_from`, or `resolution_rule` after insert, enforced by a database trigger rather than by application code.

**REQ-INF-104 (Ubiquitous)**
The confirmation job SHALL evaluate a registered hypothesis using only observations whose `subject_day >= confirmation_data_from` and whose `ingested_at >= confirmation_data_from`.

**REQ-INF-105 (Unwanted behaviour)**
IF a confirmation query returns any row whose `ingested_at < confirmation_data_from`, THEN the reasoning layer SHALL abort the confirmation, SHALL NOT assign any tier above `PROMOTED`, and SHALL write a row to `pipeline_violations` with reason `pre_registration_leak`.

**REQ-INF-106 (Ubiquitous)**
The reasoning layer SHALL apply Benjamini–Hochberg across the set of registered hypotheses evaluated in a given confirmation run, and SHALL persist that family size.

**REQ-INF-107 (State-driven)**
WHILE a registered hypothesis has fewer than 30 post-registration observation days on both its exposure and its outcome, the reasoning layer SHALL report it at tier `INSUFFICIENT` with `insufficiency_reason='window_too_short'` and SHALL NOT evaluate its resolution rule.

**REQ-INF-108 (Ubiquitous)**
The reasoning layer SHALL compute every feature consumed by a confirmation test through the point-in-time-correct function `f_daily_panel(as_of)`, honouring the bitemporal cutoff and per-metric `max_staleness_days`.

**REQ-INF-109 (Ubiquitous)**
The reasoning layer SHALL NOT forward-fill a metric value past its `max_staleness_days`, and SHALL represent a stale value as missing.

**REQ-INF-110 (Ubiquitous)**
The reasoning layer SHALL NOT impute any missing observation, and SHALL model missingness explicitly where the analysis requires it.

**REQ-INF-111 (Event-driven)**
WHEN a hypothesis fails its pre-specified confirmation test on post-registration data, the reasoning layer SHALL set its status to `REFUTED` and SHALL surface the refutation to Joe rather than dropping it silently.

**REQ-INF-112 (Event-driven)**
WHEN a hypothesis survives observational confirmation but its E-value at the interval limit nearest the null is below 1.5, or no minimal sufficient adjustment set exists for its DAG, the reasoning layer SHALL emit a proposed randomized micro-trial specification for that hypothesis.

**REQ-INF-113 (Ubiquitous)**
The reasoning layer SHALL store a `feature_snapshot_hash` on every confirmation result sufficient to reconstruct the exact feature matrix used.

**REQ-INF-114 (Ubiquitous)**
The observations store SHALL never UPDATE a recorded value, and SHALL record every revision as a new row with an incremented `source_rev` and a flipped `is_current`.

### C.NON-GOALS
- Not a goal: registering hypotheses with an external service (OSF, AsPredicted). The register is local and its enforcement is the DB constraint.
- Not a goal: random train/test splitting. Splits are by time only; random splits leak because adjacent days are correlated.
- Not a goal: allowing Joe to amend a registered hypothesis. Amendment is a new registration with a new `preregistered_at`.
- Not a goal: pre-registering `DESCRIPTIVE` computations. Descriptions make no inferential claim.

### C.ALTERNATIVES CONSIDERED
- **Pre-registration as a documented norm enforced in review.** Rejected: the whole point of `C` §3.5 is that a norm is not an invariant. The idiographic-network literature shows what norms achieve — of 43 fully idiographic studies, 7% preregistered, 11.6% evaluated network stability.
- **Application-level immutability instead of a DB trigger.** Rejected: the agent building this system also writes the application code. The constraint must sit where the agent cannot casually route around it.
- **Holding out a random 30% of history as the confirmation set.** Rejected on leakage grounds (`C` §3.5) and because it forfeits the free out-of-sample property that calendar time provides.
- **Confirming on all data including the discovery window, with a multiplicity penalty instead.** Rejected: no penalty is calibratable against an unbounded and undocumented forking path.

### C.UNRESOLVED QUESTIONS
- The 30-post-registration-day floor in REQ-INF-107 is not derived from the research; it is a placeholder.
- The E-value floor of 1.5 in REQ-INF-112 is not in the research files. `C` §2.5 gives the formula and worked examples (2.1, 1.4) but states no threshold.
- Whether a `REFUTED` hypothesis may ever be re-registered, and after what interval. Silence in the research.
- How to handle a registered hypothesis whose exposure metric is later redefined in `metric_registry`. The register pins a `metric_key`, not a definition version.

## D. RANDOMIZED MICRO-TRIALS (REQ-INF-2xx)

`C` §0 ranks this **BUILD FIRST — highest value in the system**, and `C` §7 names skipping it the highest-probability failure mode of the whole project: without randomized blocks the system spends years producing confidently-hedged correlations. Randomization is the only thing at n=1 that actually defeats confounding, and it needs no data history. The reporting template is CENT 2015 (CONSORT Extension for N-of-1 Trials).

**REQ-INF-200 (Ubiquitous)**
The reasoning layer SHALL maintain a `trials` table recording, per trial: `trial_id`, `exposure`, `outcome`, `block_length_days`, `n_blocks_planned`, `washout_days`, `washout_justification`, `randomization_seed`, `blinded`, `primary_outcome_metric`, `analysis_method`, `preregistered_at`.

**REQ-INF-201 (Ubiquitous)**
The reasoning layer SHALL write the complete `trials` row, including `analysis_method` and `primary_outcome_metric`, before the first block is assigned.

**REQ-INF-202 (Event-driven)**
WHEN a trial block begins, the reasoning layer SHALL draw the block's arm assignment from a seeded pseudorandom generator, SHALL store the assignment with its timestamp in `trial_assignments`, and SHALL NOT allow the assignment to be regenerated.

**REQ-INF-203 (Ubiquitous)**
The reasoning layer SHALL randomize block order rather than alternating arms, and SHALL make block length exceed the declared washout length.

**REQ-INF-204 (Optional feature)**
WHERE the exposure admits a physically indistinguishable placebo, the reasoning layer SHALL blind the assignment from Joe until the trial completes, and SHALL record `blinded = true`.

**REQ-INF-205 (Ubiquitous)**
The reasoning layer SHALL record `blinded = false` and SHALL state the impossibility of blinding in the trial's rendered result whenever blinding was not implemented.

**REQ-INF-206 (Ubiquitous)**
The reasoning layer SHALL require a minimum trial duration of 6 weeks of blocks for any trial whose result may reach tier `EXPERIMENTAL`.

**REQ-INF-207 (Event-driven)**
WHEN a trial is proposed, the reasoning layer SHALL compute and display its power against the pre-specified minimum detectable effect before the trial may be started.

**REQ-INF-208 (Unwanted behaviour)**
IF a proposed trial's power against its minimum detectable effect is below 0.80 at the requested duration, THEN the reasoning layer SHALL refuse to start it, SHALL state the duration that would be required, and SHALL offer the larger-effect alternative it could detect at the requested duration.

**REQ-INF-209 (Event-driven)**
WHEN Joe records an exposure that contradicts the current block's assignment, the reasoning layer SHALL write a row to `trial_deviations` with the day, the assigned arm, the observed exposure, and SHALL retain the day in the dataset flagged as a deviation.

**REQ-INF-210 (Ubiquitous)**
The reasoning layer SHALL analyse every trial by intention-to-treat over assigned arms as the primary analysis, and SHALL report the per-protocol analysis only as a labelled secondary result.

**REQ-INF-211 (State-driven)**
WHILE the proportion of deviating days in a running trial exceeds 0.20, the reasoning layer SHALL report the trial at tier `INSUFFICIENT` and SHALL NOT assign tier `EXPERIMENTAL` to its result.

**REQ-INF-212 (Event-driven)**
WHEN a trial's deviation proportion exceeds 0.20, the reasoning layer SHALL notify Joe once, SHALL offer to restart the trial with a shorter block length, and SHALL NOT repeat the notification.

**REQ-INF-213 (Ubiquitous)**
The reasoning layer SHALL NOT modify a trial's `primary_outcome_metric` or `analysis_method` after the first assignment is drawn.

**REQ-INF-214 (Event-driven)**
WHEN a trial completes, the reasoning layer SHALL emit a result at tier `EXPERIMENTAL` if and only if `n_blocks_planned` blocks completed, the deviation proportion is at or below 0.20, and the pre-specified analysis ran; otherwise it SHALL emit `INSUFFICIENT`.

**REQ-INF-215 (Ubiquitous)**
The reasoning layer SHALL carry out trial analysis with the same autocorrelation-robust inference required by REQ-INF-020, and SHALL report `n_eff` for the trial.

**REQ-INF-216 (Ubiquitous)**
The reasoning layer SHALL randomize only within the declared randomisation boundary recorded in `metric_registry`, and SHALL NOT randomize an exposure not marked `tier='lever'`.

**REQ-INF-217 (Ubiquitous)**
The reasoning layer SHALL propose a trial rather than impose one, SHALL accept a one-tap decline, and SHALL NOT re-propose a declined trial for 7 days.

**REQ-INF-218 (Optional feature)**
WHERE a discrete one-off change occurred on a known date and no randomization is possible, the reasoning layer SHALL use an interrupted-time-series / structural-time-series analysis, SHALL print the control series it selected, and SHALL allow Joe to veto any control series.

**REQ-INF-219 (Ubiquitous)**
The reasoning layer SHALL assign interrupted-time-series results a tier no higher than `CONFIRMED_OBSERVATIONAL`.

### D.NON-GOALS
- Not a goal: aggregated / series-of-N-of-1 designs. There is no second subject to borrow strength from.
- Not a goal: medical or supplement trials that require dosing advice. `09 §11` "never diagnose, never prescribe medically" is KEEP AS IS.
- Not a goal: automatic trial start. Every trial requires Joe's explicit consent per REQ-INF-217.
- Not a goal: gamified adherence. Streaks and adherence scores are banned; `07 §11.11` calls this data integrity, not UX preference.

### D.ALTERNATIVES CONSIDERED
- **Alternating ABAB rather than randomized block order.** Rejected: alternation is confounded with weekly and biweekly periodicity in Joe's data, and the old spec's acceptance test 15 already required randomized order.
- **Dropping deviation days from the analysis.** Rejected: deviation is almost certainly informative (Joe breaks assignment on the days the assignment is hardest), so dropping them is exactly the informative-missingness failure `C` §2.4 flags as the likeliest source of a confident false conclusion.
- **Washout periods as standard practice.** Narrowed: the HDSR simulations show washout *with naive inference* is the worst configuration, pushing false positives to 0.30+ at AR(1)≈0.70. Washout is permitted only with HAC inference (REQ-INF-026).
- **`tfp-causalimpact` for the ITS path.** Rejected: the TensorFlow dependency is ~600 MB and would dominate the CI budget. `statsmodels.tsa.statespace.UnobservedComponents` recovers most of the value.

### D.UNRESOLVED QUESTIONS
- The 0.20 deviation threshold in REQ-INF-211 is not in the research files.
- The power floor of 0.80 in REQ-INF-208 is conventional, not sourced from the research.
- Washout length justification is required by CENT but the research gives no rule for computing it from Joe's data; carryover assessment is likewise unspecified.
- Which exposures are genuinely blindable for a single user without a collaborator. The research states blinding is "usually impossible for you" without enumerating exceptions.
- The 6-week minimum in REQ-INF-206 comes from `C` §0's "~6 weeks per question"; whether that is per-block or total is not stated.

## E. SCORED FORWARD PREDICTIONS AND AUTO-DEMOTION (REQ-INF-3xx)

This is the anti-sycophancy machinery and it is the structural defence against a system that tells Joe what he wants to hear. `C` §5.2: *"Retrospective narratives can never be scored and therefore can never be trusted. Force the system to also emit forward predictions it will be graded on. This is the single most important integrity mechanism in the entire design, because it makes self-deception expensive."*

A scoring rule is **proper** if reporting one's true belief maximizes expected score. The governing paradigm is "maximize the sharpness of the predictive distribution subject to calibration." Good Judgment Project results show prediction skill is real, measurable and improvable, and that it replicates across years rather than regressing (standardized Brier −0.34 / −0.14 / 0.04; AUC 96% / 84% / 75%; calibration error 0.01 / 0.03 / 0.04).

**REQ-INF-300 (Ubiquitous)**
The reasoning layer SHALL maintain a `predictions` table containing at minimum: `prediction_id`, `created_at`, `hypothesis_id`, `claim_text`, `resolution_rule`, `resolves_at`, `p_forecast`, `evidence_tier`, `model_version`, `feature_snapshot_hash`, `resolved_at`, `outcome_bool`, `brier`, `log_score`.

**REQ-INF-301 (Event-driven)**
WHEN a finding is assigned tier `PROMOTED`, `CONFIRMED_OBSERVATIONAL`, or `EXPERIMENTAL`, the reasoning layer SHALL insert at least one row into `predictions` in the same transaction.

**REQ-INF-302 (Unwanted behaviour)**
IF a finding at tier `PROMOTED` or above has no row in `predictions`, THEN the reasoning layer SHALL refuse to render that finding on any surface and SHALL return the refusal string "This finding has no forward prediction attached and cannot be shown."

**REQ-INF-303 (Ubiquitous)**
The `predictions` table SHALL enforce `resolves_at > created_at` as a CHECK constraint.

**REQ-INF-304 (Ubiquitous)**
The reasoning layer SHALL express every `resolution_rule` as a machine-evaluable predicate over stored metrics with no free text, such that resolution requires no human judgement.

**REQ-INF-305 (Unwanted behaviour)**
IF a `resolution_rule` cannot be parsed and evaluated by the resolution job, THEN the reasoning layer SHALL reject the prediction at insert time and SHALL NOT promote the associated finding.

**REQ-INF-306 (Ubiquitous)**
The reasoning layer SHALL resolve every prediction whose `resolves_at` has passed on the nightly schedule, SHALL compute the Brier score and the logarithmic score, and SHALL write both to the prediction row.

**REQ-INF-307 (Ubiquitous)**
The reasoning layer SHALL resolve a prediction against the feature state reconstructible from `feature_snapshot_hash` plus post-`resolves_at` observations, and SHALL NOT resolve against a value revised after `resolves_at`.

**REQ-INF-308 (Ubiquitous)**
The reasoning layer SHALL maintain a reliability diagram of forecast probability against observed frequency, stratified by evidence tier and by domain.

**REQ-INF-309 (Ubiquitous)**
The reasoning layer SHALL report the Murphy decomposition of the Brier score into reliability, resolution, and uncertainty, and SHALL NOT report the Brier score alone.

### E.1 Auto-demotion — no human in the loop

**REQ-INF-320 (Event-driven)**
WHEN 3 or more predictions attached to a single finding have resolved and the proportion resolving false is 0.50 or greater, the reasoning layer SHALL demote that finding by one tier automatically.

**REQ-INF-321 (Event-driven)**
WHEN 5 or more predictions attached to a single finding have resolved and the proportion resolving false is 0.60 or greater, the reasoning layer SHALL set that finding's status to `REFUTED` automatically.

**REQ-INF-322 (Ubiquitous)**
The reasoning layer SHALL execute demotion under REQ-INF-320 and REQ-INF-321 without human confirmation, and SHALL NOT provide any interface that suppresses, defers, or overrides an automatic demotion.

**REQ-INF-323 (Event-driven)**
WHEN a finding is auto-demoted, the reasoning layer SHALL write a `tier_history` row with reason `failed_forward_predictions`, the resolved prediction IDs, and the observed failure proportion.

**REQ-INF-324 (Event-driven)**
WHEN a finding is auto-demoted, the reasoning layer SHALL surface the demotion in the next brief, naming the original claim, the number of failed predictions, and the new tier.

**REQ-INF-325 (State-driven)**
WHILE a probability bucket in the reliability diagram shows observed frequency below its nominal probability by more than 0.15 over at least 20 resolved predictions, the reasoning layer SHALL widen the rendered intervals for new findings in that bucket and SHALL state on the surface that it is doing so and why.

**REQ-INF-326 (State-driven)**
WHILE a probability bucket is miscalibrated as defined in REQ-INF-325, the reasoning layer SHALL downgrade the EFSA verbal term attached to claims in that bucket to the band matching the observed frequency rather than the nominal one.

**REQ-INF-327 (Ubiquitous)**
The reasoning layer SHALL make the full prediction track record — every prediction, its forecast probability, its outcome, and its scores — available to Joe on demand and in export.

**REQ-INF-328 (Ubiquitous)**
The reasoning layer SHALL NOT delete a resolved prediction, and SHALL NOT recompute a stored score under a later model version.

**REQ-INF-329 (Ubiquitous)**
The reasoning layer SHALL count a prediction whose `resolves_at` has passed but whose resolution inputs are missing as `unresolvable`, SHALL exclude it from scoring, and SHALL report the unresolvable rate alongside the reliability diagram.

**REQ-INF-330 (Unwanted behaviour)**
IF the unresolvable rate exceeds 0.25 over the trailing 90 days, THEN the reasoning layer SHALL report its own calibration at tier `INSUFFICIENT` and SHALL state that its track record cannot currently be assessed.

### E.NON-GOALS
- Not a goal: scoring retrospective narratives. They are unfalsifiable by construction and are therefore never scored, never counted toward calibration, and never used as evidence of system quality.
- Not a goal: a user-facing "accuracy percentage". The reliability diagram plus the Murphy decomposition is the contract; a single scalar hides the reliability/resolution distinction that matters.
- Not a goal: rewarding the system for confident correct calls. Only proper scoring rules are used.
- Not a goal: letting Joe mark a prediction correct. Resolution is mechanical (REQ-INF-304).

### E.ALTERNATIVES CONSIDERED
- **Log score alone.** Rejected as the sole rule: it is unbounded, and one confident wrong call at p=0.01 dominates the record. Both Brier and log score are stored; Brier drives demotion.
- **Human review before demotion.** Rejected: the entire purpose of this section is to remove the human from the loop, because the human is the source of the sycophancy pressure being defended against.
- **Demote only on statistically significant miscalibration.** Rejected as a false-precision trap at these sample sizes; fixed count-and-proportion triggers are auditable and testable.
- **Emit forward predictions only for `EXPERIMENTAL` findings.** Rejected: `PROMOTED` findings are the ones most likely to be noise and therefore the ones most in need of scoring.

### E.UNRESOLVED QUESTIONS
- The thresholds in REQ-INF-320 (3 predictions, 0.50), REQ-INF-321 (5, 0.60), REQ-INF-325 (0.15 over 20), and REQ-INF-330 (0.25) are not present in the research files. They are placeholders requiring simulation before build.
- The Ferro & Fricker small-sample bias correction to the Brier decomposition is flagged as relevant in `C` §5.2 but no correction formula or trigger point is specified here.
- How many predictions per finding to emit, and at what horizon. `C` §5.5's example uses a single prediction with a ~4-month horizon.
- Whether calibration should be pooled across domains when a single domain has too few resolutions.

## F. GENERATOR-ONLY METHODS AND KILLED METHODS (REQ-INF-4xx)

`C` §7 names "believing Layer 3" one of the three ways this project fails: PCMCI+ edges look like discoveries, and rendering one to Joe puts the ~50,000-false-discoveries-per-10^6-specifications arithmetic directly into his beliefs about his own life. Discovery output is a to-do list, not a finding.

### F.1 Generator-only

**REQ-INF-400 (Ubiquitous)**
The reasoning layer SHALL treat PCMCI+, LPCMCI, VAR-LiNGAM, DirectLiNGAM, and regularized/graphical VAR as hypothesis generators only.

**REQ-INF-401 (Ubiquitous)**
The reasoning layer SHALL write every output of a generator method into `hypothesis_register` with status `CANDIDATE` and SHALL NOT create a `findings` row directly from a generator output.

**REQ-INF-402 (Ubiquitous)**
The reasoning layer SHALL NOT include a generator method's output in any finding surface, any confirmed-tier rendering, any notification payload, any reading-intended export that presents it as a finding, or any prompt sent to the language layer as established fact; it MAY appear only on the dedicated pulled `EXPLORATORY`-labelled surface, and only once that surface is built and proven (RULE-17 binding sequencing — the label surface precedes any continuous exploration; exploratory output is never pushed at Joe). (Reworded 2026-08-24; requirements-audit C-2, ADR-0029 RULE-17 SCOPE-shell reversal. The former blanket "any user-facing surface" ban is narrowed to finding surfaces; the integrity core — never a finding, never confirmed vocabulary, never into an LLM prompt as fact — is unchanged, REQ-INF-401.)

**REQ-INF-403 (Unwanted behaviour)**
IF a render request for a finding surface resolves to a row whose `status = 'CANDIDATE'`, THEN the surface SHALL return the refusal string "No finding available." and SHALL write a row to `render_violations` with reason `candidate_leak`; a request for the `EXPLORATORY`-labelled surface is not a violation and SHALL render the row under its `EXPLORATORY` label (RULE-17).

**REQ-INF-404 (Ubiquitous)**
The reasoning layer SHALL run generator methods on domain blocks of at most 20 variables at a time, and SHALL NOT run a generator over the full metric space in one pass.

**REQ-INF-405 (State-driven)**
WHILE the well-covered observation count is below 200 days, the reasoning layer SHALL NOT run any generator method.

**REQ-INF-406 (State-driven)**
WHILE the well-covered observation count is below 500 days, the reasoning layer SHALL NOT run a nonparametric conditional-independence test (CMIknn, CMIsymb) in any generator.

**REQ-INF-407 (Ubiquitous)**
The reasoning layer SHALL use ParCorr as the default conditional-independence test for routine generator runs and SHALL reserve GPDC for a confirmatory subset of at most 3 variables.

**REQ-INF-408 (Ubiquitous)**
The reasoning layer SHALL treat a VAR-LiNGAM edge as corroboration only, and SHALL NOT promote any candidate to `PROMOTED` on the strength of a VAR-LiNGAM edge that PCMCI+ did not also produce.

**REQ-INF-409 (Ubiquitous)**
The reasoning layer SHALL detrend and deseasonalize every series before a generator run, and SHALL record on each candidate the transformation applied.

**REQ-INF-410 (Ubiquitous)**
The reasoning layer SHALL calibrate every generator run against a circular-shift null and SHALL store the discovery count of the real run and the null median and 95th percentile.

**REQ-INF-411 (Ubiquitous)**
The reasoning layer SHALL treat a single edge from a regularized or graphical VAR fit as a hypothesis and never as a finding, in accordance with the documented reliability problem in the idiographic-network literature (43 studies, median T=99, 8.8% tested normality, 11.6% evaluated stability, 7% preregistered).

### F.2 Killed methods — forbidden

*Note (C-14, 2026-08-24): this enumerated ban list is the **current** RULE-22 method list, which
RULE-22 makes revisable-with-evidence via an ADR (the CI grep enforces whatever the current list is).
An ADR that revises RULE-22 — adding or removing a method on new evidence — amends the requirements in
this section and their dependency/import checks in the same change, so a future revision updates these
rather than orphaning them as build-failing contradictions. The GIMME and GES/FGES bans below are
stricter than RULE-22's named set by deliberate choice, recorded here.*

**REQ-INF-420 (Ubiquitous)**
The reasoning layer SHALL NOT use NOTEARS.

**REQ-INF-421 (Ubiquitous)**
The reasoning layer SHALL NOT use DYNOTEARS.

**REQ-INF-422 (Ubiquitous)**
The reasoning layer SHALL NOT use any continuous-optimization DAG learner whose objective is scale non-invariant, because varsortability exceeds 0.94 on standard benchmarks and the recovered graph is largely an artifact of the variables' units.

**REQ-INF-423 (Ubiquitous)**
The reasoning layer SHALL NOT use DSEM.

**REQ-INF-424 (Ubiquitous)**
The reasoning layer SHALL NOT use convergent cross mapping.

**REQ-INF-425 (Ubiquitous)**
The reasoning layer SHALL NOT use multivariate transfer entropy on more than 3 variables.

**REQ-INF-426 (Ubiquitous)**
The reasoning layer SHALL NOT use Model-X knockoffs.

**REQ-INF-427 (Ubiquitous)**
The reasoning layer SHALL NOT use GIMME-style stepwise modification-index search as a discovery engine at n=1.

**REQ-INF-428 (Ubiquitous)**
The reasoning layer SHALL NOT use GES or FGES.

**REQ-INF-429 (Ubiquitous)**
The build SHALL fail if the dependency set resolves `causalnex`, `pyEDM`, `skccm`, or `rEDM`.

**REQ-INF-430 (Ubiquitous)**
The build SHALL fail if any module imports a symbol whose name matches `notears`, `dynotears`, `knockoff`, or `ccm` case-insensitively.

**REQ-INF-431 (Ubiquitous)**
The reasoning layer SHALL NOT perform an unrestricted all-pairs search across the full metric space without the `metric_registry` direction constraints and the hierarchical FDR tree.

### F.NON-GOALS
- Not a goal: reproducing published causal-discovery benchmarks. Benchmark performance on simulated DAGs is precisely what varsortability shows to be misleading.
- Not a goal: a "discovery feed" that launders `CANDIDATE` output into finding-like copy with a friendlier name. (The RULE-17 `EXPLORATORY`-labelled surface is the *sanctioned* alternative — it displays the same output but under a structural EXPLORATORY label and vocabulary, never as a finding; post-ADR-0029/C-2. What stays banned is the decorative feed that reads like a findings screen.)
- Not a goal: automated DAG learning replacing the hand-written domain DAG. Discovery proposes; the written DAG identifies.
- Not a goal: a graph database. ~80 nodes and a wide daily panel; the dominant query is a pivot, not a 3-hop traversal.

### F.ALTERNATIVES CONSIDERED
- **Show PCMCI+ edges behind an "exploratory" label.** Originally rejected (the old Patterns screen did exactly this; `C` §7 names it failure mode 3 — a label does not undo the false-positive arithmetic once the sentence has been read). **Reversed by ADR-0029 (RULE-17 SCOPE shell), 2026-08-24:** exploratory output MAY now be displayed carrying an explicit `EXPLORATORY` label, but only on a tier-labelling surface that is built and proven BEFORE any continuous exploration ships (binding sequencing, Joe's ruling). The integrity core the original rejection protected is unchanged — never promoted to a finding, never confirmed-tier vocabulary, never into an LLM prompt as established fact (REQ-INF-401/402). The reversal answers the old objection by making the label structural (a distinct surface + vocabulary), not decorative copy on a findings screen.
- **DYNOTEARS as the primary discovery engine.** Rejected — the strongest negative recommendation in the research. Joe's variables span steps (10^4), HRV ms (10^1), dollars (10^2), drinks (10^0), sleep hours (10^0); a method whose output changes with unit choice returns a confident, arbitrary graph of his life.
- **LPCMCI as primary instead of PCMCI+.** Kept available and not made primary: LPCMCI drops causal sufficiency, which is the honest choice given Joe unambiguously has hidden confounders, but its output is correspondingly weaker (mostly "confounded or one causes the other").
- **Granger causality as a headline feature.** Narrowed to `predictive_lead` (REQ-TIER-022). All seven of its assumptions are violated in this data.

### F.UNRESOLVED QUESTIONS
- `tigramite` is GPL-3.0. If the engine repo is made public for unmetered CI, the licence interaction with the rest of the stack (MIT/Apache/BSD) is unexamined in the research.
- The exact composition of the ≤20-variable domain blocks is not specified.
- Whether LPCMCI's PAG output can be represented in `causal_edges` without loss. The schema in `C` §6.4 assumes directed edges.
- What alpha to use in PCMCI+'s liberal stage-1 condition selection. `C` §2.1 says "liberal" without a value.

## G. CROSS-LENS INTEGRATION (REQ-INF-5xx)

Joe's words: *"think of a program that connects every single app and integrates at the highest level... having high level systems that put everything in conversation with everything through these high level systems and they go through mathematical reasoning models to understand probability based on all the inputs."*

The honest reading: the mathematics that makes "everything in conversation with everything" trustworthy is mostly **multiplicity control and calibration**, not causal discovery. The requirement is a *general* probabilistic inference layer parameterised by `metric_registry`, not a fixed list of hardcoded hypotheses — so that adding a tracker in 2029 automatically extends the search space and automatically pays the correct multiplicity price.

### G.1 The registry drives everything

**REQ-INF-500 (Ubiquitous)**
The reasoning layer SHALL derive the set of testable hypotheses entirely from `metric_registry` and `v_metric_tree`, and SHALL NOT contain a hardcoded list of variable pairs anywhere in the codebase.

**REQ-INF-501 (Event-driven)**
WHEN a metric row is inserted into `metric_registry` with `active_since` set, the reasoning layer SHALL include that metric in the next scheduled search, regime model, and coverage report without any code change.

**REQ-INF-502 (Ubiquitous)**
The reasoning layer SHALL refuse to ingest an observation whose `metric_key` has no row in `metric_registry`.

**REQ-INF-503 (Ubiquitous)**
The reasoning layer SHALL apply only the transformations listed in that metric's `legal_transforms` when constructing specifications for it.

**REQ-INF-504 (Ubiquitous)**
The reasoning layer SHALL expose exactly three interfaces to the inference layer — `f_daily_panel(as_of)`, `v_metric_tree`, and `v_coverage` — and SHALL NOT permit an inference job to query the observations table directly.

**REQ-INF-505 (Ubiquitous)**
The reasoning layer SHALL produce `f_daily_panel(as_of)` with genuine NULLs for missing values, never zero-filled and never forward-filled beyond `max_staleness_days`.

**REQ-INF-506 (Ubiquitous)**
The reasoning layer SHALL run the negative-control battery automatically on every promotion attempt, using every metric flagged `is_negative_control` in `metric_registry`.

**REQ-INF-507 (Event-driven)**
WHEN a negative-control outcome shows an effect from an exposure at the same threshold as the real outcome, the reasoning layer SHALL suppress every finding from that pipeline run and SHALL report the suppression and its cause.

**REQ-INF-508 (Ubiquitous)**
The reasoning layer SHALL run a negative-control exposure check by shifting the exposure to a future day relative to the outcome, and SHALL treat any effect surviving that check as an artifact detector.

### G.2 The probabilistic inference layer

**REQ-INF-520 (Ubiquitous)**
The reasoning layer SHALL use NumPyro as its sole probabilistic programming language.

**REQ-INF-521 (Ubiquitous)**
The reasoning layer SHALL NOT depend on Stan, CmdStanPy, Turing.jl, or PyMC, because the CmdStan C++ compile step, Julia precompilation, and the PyTensor toolchain respectively make CI installation slow or fragile.

**REQ-INF-522 (Ubiquitous)**
The reasoning layer SHALL standardize every predictor and every outcome before fitting a Bayesian model.

**REQ-INF-523 (Ubiquitous)**
The reasoning layer SHALL place a `Normal(0, 0.3)` prior on every standardized regression coefficient unless the hypothesis register records a different prior pre-registered before data inspection.

**REQ-INF-524 (Ubiquitous)**
The reasoning layer SHALL place half-normal(0,1) or half-t(4,0,1) priors on hierarchical scale parameters and SHALL NOT use an inverse-gamma prior on a scale parameter.

**REQ-INF-525 (Ubiquitous)**
The reasoning layer SHALL partially pool only across within-person groupings — day-of-week, month or season, life-phase or context, and repeated instances of the same exposure type — and SHALL NOT construct a between-person level.

**REQ-INF-526 (Ubiquitous)**
The reasoning layer SHALL report posterior probability of direction and posterior probability of practical significance against a declared ROPE, and SHALL NOT report a p-value on any user-facing surface.

**REQ-INF-527 (Ubiquitous)**
The reasoning layer SHALL model missingness as a latent quantity within the model where the analysis depends on it, and SHALL NOT impute and discard the missingness indicator.

### G.3 Regime detection — the general answer to "what is going on"

**REQ-INF-540 (Ubiquitous)**
The reasoning layer SHALL fit a Hidden Markov Model with between 2 and 4 latent states over the daily feature vector using `dynamax`.

**REQ-INF-541 (State-driven)**
WHILE the well-covered observation count is below 300 days, the reasoning layer SHALL NOT fit the regime HMM and SHALL report regime questions at tier `INSUFFICIENT` with `insufficiency_reason='window_too_short'`.

**REQ-INF-542 (Ubiquitous)**
The reasoning layer SHALL assign every regime-model output tier `DESCRIPTIVE`.

**REQ-INF-543 (Ubiquitous)**
The reasoning layer SHALL characterise each latent state by the mean and dispersion of each contributing metric within that state, and SHALL render the state using those metric values rather than an invented state name.

**REQ-INF-544 (Ubiquitous)**
The reasoning layer SHALL NOT attach any causal language to a regime-model output.

**REQ-INF-545 (Ubiquitous)**
The reasoning layer SHALL report the historical run-length distribution of the current state alongside the current state.

**REQ-INF-546 (Ubiquitous)**
The reasoning layer SHALL fit a local-level plus seasonal `UnobservedComponents` state-space model per key outcome and SHALL report the latent level rather than a rolling average as the current baseline.

**REQ-INF-547 (Ubiquitous)**
The reasoning layer SHALL select the number of HMM states by a pre-registered criterion recorded before fitting, and SHALL NOT select the state count by inspecting which count produces the most interpretable states.

### G.4 Chains across lenses

**REQ-INF-560 (Ubiquitous)**
The reasoning layer SHALL compute cumulative attenuation across a multi-edge chain multiplicatively, such that two edges of r=0.3 compose to approximately 0.09.

**REQ-INF-561 (Ubiquitous)**
The reasoning layer SHALL terminate chain traversal on any cycle and SHALL include each node at most once per path.

**REQ-INF-562 (Ubiquitous)**
The reasoning layer SHALL permit assembly of an explanation from sub-threshold edges only when the assembled explanation carries the tier of its weakest edge, displays the cumulative attenuated magnitude, and states what would firm it up.

**REQ-INF-563 (Ubiquitous)**
The reasoning layer SHALL NOT render an unpruned cross-lens map, and SHALL rank the retained edges by absolute effect multiplied by confidence.

**REQ-INF-564 (Ubiquitous)**
The reasoning layer SHALL resolve every rendered edge to a stored evidence record containing `n`, `n_eff`, the interval, the estimator, the reverse-direction check result, and the family identifier.

**REQ-INF-565 (Ubiquitous)**
The reasoning layer SHALL NOT auto-promote a metric marked `context` in `metric_registry` to `lever` status on the basis of a discovered association.

**REQ-INF-566 (Ubiquitous)**
The reasoning layer SHALL reason over resolved place labels and entities, and SHALL NOT include a numeric coordinate in any payload sent to the language layer, any export, or any log line.

### G.NON-GOALS
- Not a goal: a single unified model of Joe's whole life. `C` §7's architecture is seven layers with hard claim limits, and the value comes from the limits.
- Not a goal: GPU or paid compute. At ~1,400 rows x 80 columns, statistical power is the binding constraint, not compute.
- Not a goal: a knowledge graph store. `causal_edges` in Postgres plus `networkx` in memory is the knowledge graph.
- Not a goal: adopting a health ontology wholesale. Field naming is borrowed from Open mHealth, FHIR `Observation` (`effective` vs `issued`), and LOINC for clinical metrics; SNOMED CT is excluded on cost.
- Not a goal: continuous-time SEM. `ctsem` is R+Stan; the lag-profile requirement (REQ-INF-035) captures most of the insight.

### G.ALTERNATIVES CONSIDERED
- **PyMC for its nicer API.** Rejected: the fast path requires the nutpie/numpyro/blackjax backends anyway, and PyTensor plus a C compiler makes CI installs slower and more fragile.
- **A hardcoded hypothesis library.** The old `HYPOTHESIS_LIBRARY_V2.md` is 93 hypotheses. Rejected as the primary mechanism: a fixed list cannot answer "everything in conversation with everything," and it does not automatically pay a multiplicity price when extended. Retained only as seeded prior edges in `causal_edges` with `edge_type='asserted_prior'`.
- **GIMME as the integration engine.** Right shape, wrong statistical footing: its recovery properties come from the group stage, which does not exist at n=1.
- **Aggregated hierarchical modelling across "similar people."** Unavailable. There is no second subject.

### G.UNRESOLVED QUESTIONS
- The domain list for `metric_registry.domain` is not fixed. `C` §6.2 suggests sleep|substance|spend|affect|work|env|media|body|place; the finance overturn may add more.
- The ROPE width per metric is undefined. Practical significance is metric-specific and no values exist in the research.
- The pre-registered criterion for HMM state count (REQ-INF-547) is unspecified — BIC, held-out likelihood, or a fixed 3 are all defensible and none is recommended in the research.
- Whether `dynamax` HMM fits are stable enough at 300 days to avoid re-labelling states between nightly runs. State-label switching is not discussed in the research.

## H. OPEN-ENDED QUESTION ANSWERING (REQ-ASK)

Joe wants to ask anything about his life and get an answer. PHIA is the published architecture for exactly this: a ReAct loop where the model writes code, a sandbox executes it, the model reads the output and continues. 22%→74%→84% (see preamble §0 for the decomposition and caveats). This section specifies that loop with the LLM's arithmetic privileges removed entirely.

### H.1 The loop

**REQ-ASK-001 (Event-driven)**
WHEN Joe submits a free-text question, the language layer SHALL emit a structured query plan and SHALL NOT emit an answer in the same step.

**REQ-ASK-002 (Ubiquitous)**
The query plan SHALL consist only of: named metrics drawn from `metric_registry`, a date range, a set of named operations drawn from a closed operation registry, and optional grouping keys.

**REQ-ASK-003 (Ubiquitous)**
The reasoning layer SHALL reject any query plan referencing a `metric_key` absent from `metric_registry` and SHALL return the refusal string "I do not track that." with the list of the nearest tracked metrics.

**REQ-ASK-004 (Ubiquitous)**
The reasoning layer SHALL reject any query plan referencing an operation absent from the operation registry, and SHALL NOT execute arbitrary code emitted by the language layer.

**REQ-ASK-005 (Ubiquitous)**
The reasoning layer SHALL execute every query plan deterministically against Postgres through `f_daily_panel(as_of)` and the registered operations, in a sandbox with no network access and no write access.

**REQ-ASK-006 (Ubiquitous)**
The reasoning layer SHALL persist every executed query plan, its parameters, its result set, its execution timestamp, and its `code_version` in a `computations` table before any narration occurs.

**REQ-ASK-007 (Event-driven)**
WHEN a query plan executes successfully, the reasoning layer SHALL return the result set to the language layer as the sole input for narration, and SHALL NOT include raw observation rows in that payload.

**REQ-ASK-008 (Ubiquitous)**
The reasoning layer SHALL permit the language layer at most 5 plan-execute-observe iterations per question and SHALL return the best available answer or a refusal at the limit.

**REQ-ASK-009 (Ubiquitous)**
The reasoning layer SHALL attach a `computation_id` to every numeral in the answer payload, resolving to a row in `computations`.

**REQ-ASK-010 (Unwanted behaviour)**
IF any numeral in a generated answer has no `computation_id`, THEN the answer SHALL be discarded, the non-LLM template rendering SHALL be returned instead, and a row SHALL be written to `render_violations` with reason `untraceable_numeral`.

**REQ-ASK-011 (Ubiquitous)**
The reasoning layer SHALL make every numeral in every answer click-through auditable to the computation, the query plan, and the underlying observation IDs.

**REQ-ASK-012 (Ubiquitous)**
The language layer SHALL NOT perform arithmetic, and the answer pipeline SHALL NOT accept a numeral that does not appear verbatim in the result set or in a registered rounding of a result-set value.

### H.2 Tier and coverage on answers

**REQ-ASK-020 (Ubiquitous)**
The reasoning layer SHALL assign a tier to every answer, computed as the minimum tier across every finding and computation the answer draws on.

**REQ-ASK-021 (Ubiquitous)**
The reasoning layer SHALL compute and attach the coverage of every metric used in an answer, over the answer's date range.

**REQ-ASK-022 (Event-driven)**
WHEN the minimum coverage across the metrics required by a question is below 0.60, the reasoning layer SHALL return tier `INSUFFICIENT`, SHALL name the metric with the lowest coverage and its coverage value, and SHALL state what would raise it.

**REQ-ASK-023 (Event-driven)**
WHEN a question requires a metric that has no rows at all in the requested range, the reasoning layer SHALL return the refusal string "We do not have enough to answer this." naming the absent metric.

**REQ-ASK-024 (Event-driven)**
WHEN a question requires a causal claim and no minimal sufficient adjustment set exists in the DAG for the requested effect, the reasoning layer SHALL return tier `INSUFFICIENT` with `insufficiency_reason='no_adjustment_set'`, SHALL state that the question cannot be answered from observation, and SHALL propose the randomized micro-trial that would answer it.

**REQ-ASK-025 (Ubiquitous)**
The reasoning layer SHALL answer a descriptive question at tier `DESCRIPTIVE` without invoking the inference pipeline, so that lookups, totals and arithmetic over logged data remain available from day one.

**REQ-ASK-026 (State-driven)**
WHILE `missingness_informative_flag` is true for any metric in an answer, the reasoning layer SHALL state that fact in the answer and SHALL cap the answer's tier at `INSUFFICIENT`.

**REQ-ASK-027 (Ubiquitous)**
The reasoning layer SHALL express counts as natural frequencies over a stated denominator, and SHALL NOT express a headline result as a conditional probability without the natural-frequency form beside it.

**REQ-ASK-028 (Ubiquitous)**
The reasoning layer SHALL NOT name a medical condition, interpret a symptom, or recommend a medical action in any answer, and SHALL instead return the single stored referral string with the relevant data attached.

**REQ-ASK-029 (Ubiquitous)**
The reasoning layer SHALL answer questions about performance and subjective state from logged behaviour, and SHALL treat that as in scope and distinct from REQ-ASK-028.

**REQ-ASK-030 (Ubiquitous)**
The reasoning layer SHALL make every answer reproducible: re-executing a stored query plan at the same `as_of` SHALL return an identical result set.

### H.NON-GOALS
- Not a goal: free-form SQL or Python from the language layer. The closed operation registry is the security and correctness boundary.
- Not a goal: answering questions from the model's general world knowledge about Joe's life. General knowledge may be used for framing; every claim about Joe comes from a computation.
- Not a goal: conversational memory that accumulates unverified assertions across turns. Each answer stands on its stored computations.
- Not a goal: latency targets. Correctness and traceability take precedence.

### H.ALTERNATIVES CONSIDERED
- **Give the LLM a general pandas sandbox, as PHIA does.** Partially rejected. PHIA's 84% comes from executing code deterministically, which is retained; but PHIA's own expert error taxonomy lists pandas operation errors and misinterpretation of data as major categories, and its sibling PH-LLM confabulated and misattributed user data. A closed operation registry removes the code-error class entirely at the cost of expressiveness.
- **Let the LLM answer directly for "simple" questions like an average.** Rejected explicitly: 22% accuracy, no exceptions, including "just a quick average."
- **Retrieval-augmented generation over a text summary of the data.** Rejected: it reintroduces in-head arithmetic over retrieved numerals, which is the 22% path.
- **Refuse all questions below the coverage threshold.** Rejected per `G` §2.1: refusal without disclosure is the silence doctrine Joe overturned. Partial disclosure is required (REQ-TIER-030).

### H.UNRESOLVED QUESTIONS
- The contents of the closed operation registry are not enumerated. It must be large enough to answer real questions and small enough to audit.
- The iteration cap of 5 in REQ-ASK-008 is not sourced from the research; PHIA does not publish a loop bound.
- Whether the language layer may propose a *new* metric-pair hypothesis in response to a question, and whether such a proposal enters `hypothesis_register` as a `CANDIDATE` subject to the same pre-registration constraint.
- How to handle a question spanning a metric definition change recorded in `metric_registry`.

## I. NARRATION RESTRAINT (REQ-NAR)

`09 §11` rule 2 — *"never let the language layer promote a rung, invent a number, or generate a claim"* — is marked **KEEP AS IS** by `G` §2.1, and `G` §3.1 notes it is the rule that makes the reframed goal *possible* rather than blocking it. The research goes further than the old spec in one respect and this document adopts it: numeral-templating with **refuse-to-render on mismatch**, so number fidelity is structural rather than sampled by a test.

### I.1 The language layer's permitted surface

**REQ-NAR-001 (Ubiquitous)**
The language layer SHALL receive only a structured result object and SHALL NOT receive raw observation rows, atom rows, photo references, or coordinates.

**REQ-NAR-002 (Ubiquitous)**
The language layer SHALL NOT write to any table other than an append-only `narration_log`.

**REQ-NAR-003 (Ubiquitous)**
The language layer SHALL NOT change the tier of any claim it renders.

**REQ-NAR-004 (Ubiquitous)**
The language layer SHALL NOT introduce a claim, a relation, or an entity that is not present in its input result object.

**REQ-NAR-005 (Ubiquitous)**
The language layer SHALL NOT place two events in a causal or contributory relation unless that relation is present as an edge in the input result object.

**REQ-NAR-006 (Ubiquitous)**
The language layer SHALL NOT compute a number.

### I.2 Numeral-template rendering

**REQ-NAR-010 (Ubiquitous)**
The reasoning layer SHALL define every narration template with explicitly declared numeric slots, each bound to a named field of the result object.

**REQ-NAR-011 (Event-driven)**
WHEN a template is rendered, the render pipeline SHALL inject slot values from the result object and SHALL NOT accept a numeral supplied by the language layer.

**REQ-NAR-012 (Ubiquitous)**
The render pipeline SHALL scan every generated string for numerals and SHALL verify that each numeral matches a value present in the result object or a registered rounding of one.

**REQ-NAR-013 (Unwanted behaviour)**
IF a numeral in a generated string does not match a value in the result object, THEN the render pipeline SHALL discard the generated string, SHALL emit the deterministic template rendering instead, and SHALL write a row to `render_violations` with the finding ID, the offending numeral, and the result-object field set.

**REQ-NAR-014 (Ubiquitous)**
The render pipeline SHALL preserve the unit attached to every numeral and SHALL NOT render a numeral without its unit.

**REQ-NAR-015 (Ubiquitous)**
The render pipeline SHALL round only through registered rounding rules recorded per metric, and SHALL NOT permit ad-hoc rounding in a template.

### I.3 The per-tier vocabulary linter

**REQ-NAR-020 (Ubiquitous)**
The render pipeline SHALL lint every generated claim string against the closed vocabulary for its tier in `tier_vocabulary`.

**REQ-NAR-021 (Unwanted behaviour)**
IF a generated claim string contains a verb or qualifier not permitted at its tier, THEN the render pipeline SHALL discard the string, SHALL emit the deterministic template rendering, and SHALL write a row to `render_violations` with reason `vocabulary_above_tier`.

**REQ-NAR-022 (Ubiquitous)**
The render pipeline SHALL fail the build if any template in the repository contains a term above the tier that template is declared for.

**REQ-NAR-023 (Ubiquitous)**
The render pipeline SHALL lint every copy string against the banned moralising wordlist — at minimum {excessive, wasteful, necessary, unnecessary, too much, splurge, guilty} — and SHALL fail the build on a match. (C-10: added the standalone token `necessary`, which RULE-23 names by hand alongside `unnecessary`; the concept-level "spending/screen-time score" ban RULE-23 also names is enforced structurally by RULE-24 / REQ-NAR-025, not this wordlist.)

**REQ-NAR-024 (Ubiquitous)**
The language layer SHALL NOT render a rating, a total, or a behaviour back to Joe with a moralising judgment attached — a term on the REQ-NAR-023 banned wordlist; a decision-under-uncertainty recommendation carrying its tier and interval per REQ-TIER-048 is permitted (RULE-25).

**REQ-NAR-025 (Ubiquitous)**
The reasoning layer SHALL NOT display a streak, a compliance score, a composite wellness score, or a celebratory animation on any surface.

**REQ-NAR-026 (Ubiquitous)**
The reasoning layer SHALL NOT re-propose a declined suggestion for 7 days and SHALL NOT mention a skipped day.

### I.4 Degradation without the LLM

**REQ-NAR-030 (Ubiquitous)**
Every surface SHALL render fully with the language layer disabled.

**REQ-NAR-031 (State-driven)**
WHILE the language layer is unavailable, the render pipeline SHALL emit the deterministic template rendering for every claim and SHALL NOT return an error to any surface.

**REQ-NAR-032 (Ubiquitous)**
The reasoning layer SHALL NOT make any function, brief, answer, or alert conditional on the availability of the language layer.

**REQ-NAR-033 (Ubiquitous)**
The reasoning layer SHALL compute every displayed number in the deterministic layer, and the front end SHALL NOT compute a displayed number.

**REQ-NAR-034 (Ubiquitous)**
The render pipeline SHALL render a chart only below its verdict text, never above it.

**REQ-NAR-035 (Ubiquitous)**
The render pipeline SHALL NOT render a chart for a claim whose tier is `CANDIDATE`.

**REQ-NAR-036 (Ubiquitous)**
The reasoning layer SHALL include the TRUST section — coverage, missingness flags, and the current calibration state — in every weekly summary.

**REQ-NAR-037 (Ubiquitous)**
The reasoning layer SHALL make export complete, free, and synchronous, including atoms, links, findings, computations, predictions, and `tier_history`.

### I.NON-GOALS
- Not a goal: a natural, chatty voice as an end in itself. Fluency is the failure mode the architecture exists to prevent.
- Not a goal: LLM-generated summaries of the whole dataset. Narration operates on one result object at a time.
- Not a goal: fine-tuning a domain model. PH-LLM was *outperformed by the un-fine-tuned base model* on the training-load section, attributed to lower-quality training data.
- Not a goal: hiding the deterministic rendering. It is the fallback and it must be presentable.

### I.ALTERNATIVES CONSIDERED
- **Enforce the contract in the prompt.** Rejected explicitly by `C` §7: "Enforce the contract in code, not in the prompt."
- **Sample-based number-fidelity testing (`09 §12` test 3, 50 briefs).** Kept as a test, but rejected as the mechanism. `G` §3.1 instructs adopting the structural version — refuse-to-render on mismatch — and keeping the test.
- **Ban hedged phrasing outright.** Rejected; see §A.ALTERNATIVES.
- **Let the LLM select which finding to surface.** Rejected: selection is a claim about importance, and importance ranking is computed from `|effect| x confidence` and `achievable_delta`.

### I.UNRESOLVED QUESTIONS
- Whether the numeral scanner should also catch numbers written as words ("twenty-one minutes"). Not addressed in the research and a real bypass.
- The full contents of `tier_vocabulary` per tier. The research gives exemplars, not closed lists.
- Whether `render_violations` should trigger an alert to Joe or only a build-time report.
- How to lint a claim string in which the LLM has correctly paraphrased a permitted verb into an impermissible synonym. A wordlist linter is not a semantic check.

## J. GHERKIN ACCEPTANCE SCENARIOS

EARS says what the system must do. Gherkin says what a passing build looks like. Each scenario is executable against a seeded fixture database and cites the requirements it exercises.

### Scenario 1 — "Why am I underperforming in the gym?" with 3 weeks of data (INSUFFICIENT, partial disclosure)
*Cites: REQ-TIER-017, REQ-TIER-030, REQ-TIER-033, REQ-ASK-020, REQ-ASK-022, REQ-INF-022*
```gherkin
Given the fixture database contains 21 days of observations
  And workout.top_set_e1rm has coverage 0.90 over those 21 days
  And sleep.duration_min has coverage 0.86 over those 21 days
  And no hypothesis in hypothesis_register has status PROMOTED
When Joe asks "why am I underperforming in the gym?"
Then the returned answer has tier "INSUFFICIENT"
  And insufficiency_reason is "low_n_eff"
  And the answer contains the sentence "This is not enough evidence to be confident. Based on what we have, it is this."
  And the answer states n, n_eff and coverage for every metric it names
  And the answer terminates with either a named data requirement or a proposed randomized micro-trial
  And no sentence in the answer contains the word "caused"
```

### Scenario 2 — the same question with 6 months of data (PROMOTED path)
*Cites: REQ-TIER-012, REQ-INF-030, REQ-INF-032, REQ-INF-034, REQ-INF-035, REQ-TIER-028, REQ-INF-301*
```gherkin
Given the fixture database contains 183 days of observations
  And every metric in the SLEEP and WORKOUT domains has coverage above 0.85
  And the domain-pair test SLEEP x WORKOUT was rejected at q=0.10
  And the variable-pair test sleep.duration_min x workout.top_set_e1rm was rejected within that family
  And a specification curve of 240 specifications has been computed for that pair
  And the circular-shift null over 200 shifts gives a significant-specification share of 0.04
When the promotion job runs
Then the hypothesis is assigned tier "PROMOTED"
  And a hypothesis_register row exists with preregistered_at set and confirmation_data_from equal to it
  And at least one predictions row exists referencing that hypothesis
  And the rendered claim reports the effect as a lag profile over lags 0,1,2,3,7
  And the rendered claim reports the observed significant fraction and the shuffled-null fraction together
  And the rendered claim reports n_eff and not n alone
  And the rendered claim includes the counter-frame day count
  And the rendered claim does not contain the word "caused"
```

### Scenario 3 — a finding whose forward predictions fail must auto-demote
*Cites: REQ-INF-320, REQ-INF-322, REQ-INF-323, REQ-INF-324, REQ-TIER-042, REQ-TIER-044*
```gherkin
Given a finding F1 has tier "CONFIRMED_OBSERVATIONAL"
  And F1 has 4 predictions whose resolves_at has passed
  And 3 of those 4 predictions resolved with outcome_bool false
When the nightly prediction resolution job runs
Then F1 is demoted to tier "PROMOTED" without any human confirmation
  And a tier_history row exists with reason "failed_forward_predictions"
  And that row lists the 4 resolved prediction IDs and the failure proportion 0.75
  And the next brief names the original claim, the count of failed predictions, and the new tier
  And no API endpoint exists that can reverse the demotion
```

### Scenario 4 — a PCMCI+ output is EXPLORATORY-only, never a finding
*Cites: REQ-INF-400, REQ-INF-401, REQ-INF-402, REQ-INF-403, REQ-TIER-035, REQ-TIER-011, RULE-17*
```gherkin
Given the monthly discovery job has run PCMCI+ over a 14-variable SUBSTANCE x WORK block
  And PCMCI+ emitted an edge substance.thc_sessions -> work.deep_work_min at lag 1
When the edge is written to the database
Then it appears in hypothesis_register with status "CANDIDATE"
  And no findings row was created for it
  And the field storing the relation is named predictive_lead
When any surface requests renderable findings
Then that edge is absent from the response
  And it is absent from every notification payload
  And it is absent from every prompt that would present it as established fact
  And it is absent from the human-readable findings export
When a render is requested for that row by ID on a finding surface
Then the surface returns "No finding available."
  And a render_violations row exists with reason "candidate_leak"
When the EXPLORATORY-labelled surface renders that row (once built and proven per RULE-17)
Then the edge appears carrying an explicit EXPLORATORY label, never in confirmed-tier vocabulary
  And no render_violations row is written for that render
```

### Scenario 5 — the LLM states a number absent from the result set
*Cites: REQ-NAR-011, REQ-NAR-012, REQ-NAR-013, REQ-ASK-010, REQ-NAR-006*
```gherkin
Given a result object containing effect_point = -21.4 minutes, ci80_low = -34.2, ci80_high = -8.9, n = 463, n_eff = 155
When the language layer returns the string "about 25 fewer minutes of deep work across 463 days"
Then the render pipeline detects that 25 is not a value in the result object nor a registered rounding of one
  And the generated string is discarded
  And the deterministic template rendering is returned instead
  And a render_violations row exists with the offending numeral 25 and reason "untraceable_numeral"
  And the string shown to Joe contains -21.4 with the unit "minutes"
```

### Scenario 6 — the LLM uses vocabulary above the claim's tier
*Cites: REQ-NAR-020, REQ-NAR-021, REQ-TIER-021, REQ-TIER-003*
```gherkin
Given a findings row with tier "PROMOTED"
When the language layer returns "your short sleep caused the drop in your lifts"
Then the vocabulary linter rejects the string because "caused" is permitted only at tier EXPERIMENTAL
  And the generated string is discarded
  And the deterministic template rendering is returned instead
  And a render_violations row exists with reason "vocabulary_above_tier"
  And the tier column of the findings row is unchanged
```

### Scenario 7 — a question whose coverage is below threshold
*Cites: REQ-ASK-021, REQ-ASK-022, REQ-TIER-031, REQ-TIER-034*
```gherkin
Given Joe asks "does weed affect my next-day energy?"
  And substance.thc_sessions has 34 logged sessions in the window
  And mind.energy_rating has coverage 0.44 over the days those sessions occurred
When the question is executed
Then the returned answer has tier "INSUFFICIENT"
  And insufficiency_reason is "low_coverage"
  And the answer names mind.energy_rating and its coverage value 0.44
  And the answer states what would raise the coverage
  And the answer proposes a randomized micro-trial specification
  And the answer is not suppressed or replaced by silence
```

### Scenario 8 — informative missingness caps the answer
*Cites: REQ-ASK-026, REQ-INF-110, REQ-INF-109, REQ-TIER-017*
```gherkin
Given sleep.efficiency_pct has missingness predicted by substance.alcohol_grams at p < 0.01
  And the data-quality job has set missingness_informative_flag true for sleep.efficiency_pct
When Joe asks "how does drinking change my sleep?"
Then the answer tier is capped at "INSUFFICIENT"
  And the answer states that the wearable is missing more often on drinking nights
  And no missing sleep value was imputed
  And no stale value was forward-filled past max_staleness_days
```

### Scenario 9 — pre-registration leak is refused at the schema
*Cites: REQ-INF-102, REQ-INF-103, REQ-INF-104, REQ-INF-105*
```gherkin
Given a hypothesis H1 registered at 2026-06-01 with confirmation_data_from 2026-06-01
When a job attempts to UPDATE H1.lag_days from 1 to 2
Then the database rejects the UPDATE by trigger
When the confirmation job runs a query returning an observation with ingested_at 2026-05-20
Then the confirmation is aborted
  And H1 is not assigned any tier above PROMOTED
  And a pipeline_violations row exists with reason "pre_registration_leak"
```

### Scenario 10 — Joe breaks a trial assignment
*Cites: REQ-INF-209, REQ-INF-210, REQ-INF-211, REQ-INF-212, REQ-INF-214*
```gherkin
Given a randomized micro-trial T1 on "caffeine after 14:00" with 6 weeks of blocks
  And 9 of 42 trial days record an exposure contradicting the assigned arm
When the trial analysis runs
Then trial_deviations contains 9 rows each naming the day, the assigned arm and the observed exposure
  And the deviation proportion 0.214 exceeds 0.20
  And the result is reported at tier "INSUFFICIENT", not "EXPERIMENTAL"
  And Joe is notified once with an offer to restart with a shorter block length
  And the notification is not repeated on the following day
  And the primary analysis reported is intention-to-treat over assigned arms
```

### Scenario 11 — a killed method cannot enter the build
*Cites: REQ-INF-420, REQ-INF-421, REQ-INF-429, REQ-INF-430, REQ-INF-424, REQ-INF-426*
```gherkin
Given a pull request adds "causalnex" to the dependency set
When CI runs the dependency audit
Then the build fails naming REQ-INF-429
Given a pull request adds "from notears.linear import notears_linear"
When CI runs the forbidden-import check
Then the build fails naming REQ-INF-430
  And the failure message states scale non-invariance and varsortability above 0.94 as the reason
```

### Scenario 12 — the language layer is unavailable
*Cites: REQ-NAR-030, REQ-NAR-031, REQ-NAR-032, REQ-NAR-033, REQ-ASK-025*
```gherkin
Given the language layer is disabled entirely
When Joe opens every surface and requests the morning brief
Then every surface renders with the deterministic template rendering
  And the brief generates
  And no RPC returns an error
  And every displayed number was computed in the deterministic layer
When Joe asks a descriptive question about last month's totals
Then the question is answered at tier "DESCRIPTIVE" without the language layer
```

---

## K. REQUIREMENT INDEX

| Prefix | Range | Section | Count |
|---|---|---|---|
| `REQ-TIER` | 001–049 | A — the claim ladder | 39 |
| `REQ-INF` | 001–038 | B — multiplicity control | 25 |
| `REQ-INF` | 100–114 | C — pre-registration as a DB constraint | 15 |
| `REQ-INF` | 200–219 | D — randomized micro-trials | 20 |
| `REQ-INF` | 300–330 | E — scored predictions and auto-demotion | 21 |
| `REQ-INF` | 400–431 | F — generator-only and killed methods | 24 |
| `REQ-INF` | 500–566 | G — cross-lens integration | 32 |
| `REQ-ASK` | 001–030 | H — open-ended question answering | 23 |
| `REQ-NAR` | 001–037 | I — narration restraint | 27 |

**Totals:** `REQ-INF` 137 · `REQ-TIER` 39 · `REQ-NAR` 27 · `REQ-ASK` 23 · **226 requirements**, 12 acceptance scenarios.

### The single rule this file exists to enforce

All math is deterministic, auditable, and executed. The LLM plans the computation and narrates the result. **The LLM never computes.** 22%→74%→84%, same model (see preamble §0 for the decomposition and caveats).

### The second rule, which is the first rule's mirror

Silence is not rigour. When the evidence is short, the system says so, says what it has, and says what would fix it — and when it does not have it at all, it says that. `INSUFFICIENT` is an answer.

---

*End of `specs/04-reasoning/requirements.md`.*
