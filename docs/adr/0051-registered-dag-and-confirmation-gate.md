# ADR-0051: The registered DAG and the confirmation gate (REQ-TIER-013 / 014 / 023 / 024 / 040-044)

## Status
Accepted. Built by B9.2 (`docs/build/B9_confirmation_gate.md`), migration 0046, session 20.

## Date
2026-09-02

## Context
Session 19 refused to stamp `CONFIRMED_OBSERVATIONAL` because none of REQ-TIER-013's conditions existed
(ADR-0048 §9). This is the build that makes the tier reachable, and reachable only on its own terms.

## Decision

### 1. The registered DAG lives in `config.dag_edges` (migration 0046)
Nodes are panel metrics plus the two exogenous clocks. `basis` records why each edge is asserted:
`exogenous_clock`, `physiology`, `behaviour`, `joe`. **An edge that is not in this table does not exist
for the purposes of adjustment.** The 22-edge seed is a **floor, not a claim about the world**: it
asserts only relationships the ontology already assumes (alcohol depresses sleep and HRV; sleep drives
next-morning check-ins; screen time displaces sleep; the two clocks are parents of everything). Joe
extends it by migration, and every added edge carries its basis. The table is acyclic by test
(`test_ADR_0051_dag_is_acyclic`). A `'*'` destination means "parent of every metric": the two clocks are
therefore held out of the graph search and **forced into every regression** instead, which is equivalent
and keeps the search over panel metrics.

### 2. The adjustment set is a minimal backdoor set, computed, never chosen
`confirm.minimal_backdoor` removes the exposure's outgoing edges and searches subsets of
`ancestors(exposure) | ancestors(outcome)`, smallest first, for the first that d-separates exposure from
outcome in that graph (the backdoor criterion), rejecting any set containing a descendant of the
exposure. **If the exposure or the outcome is not a node in the registered DAG, the result is `None`, not
the empty set** — we cannot claim "a minimal sufficient adjustment set computed from the DAG" for a pair
the DAG has never heard of. That ledgers `insufficient_no_adjustment_set` (vocabulary
`no_adjustment_set`). This reading is deliberate: the alternative lets every unregistered pair through
with no adjustment at all, which is the over-claim REQ-TIER-013 exists to prevent.

### 3. The estimate: Newey-West HAC, absolute units
OLS of outcome(t+lag) on exposure(t) + the adjustment set + 6 weekday dummies + season (sin/cos of
day-of-year), post-registration days only, `cov_type='HAC'` with
`maxlags = floor(4*(n/100)^(2/9))` — the standard rule, asserted by test. The effect is reported in
**absolute outcome units per one unit of exposure** (REQ-TIER-024; never a percentage change).

### 4. E-values at the point estimate and at the limit nearest the null
`d = beta * sd(exposure) / sd(outcome)`; `RR = exp(0.91*d)` (Chinn 2000); `E = RR + sqrt(RR*(RR-1))`,
computed on RR or 1/RR, whichever is >= 1. The limit E-value uses the interval bound nearest zero, and is
exactly 1 when the interval spans the null. **The RR conversion is an approximation, not a measured risk
ratio, and every payload says so in words.**

### 5. Negative controls (REQ-TIER-014)
(a) *Outcome*: the highest-coverage panel metric with no directed path from the exposure; passes iff
p >= 0.20. (b) *Exposure*: the exposure taken `lag + 7` days **after** its outcome — future exposure
predicting past outcome; passes iff p >= 0.20. Either failure sets `REFUTED`, writes the ledger row
naming the failed check, and writes a `DESCRIPTIVE` row to `analysis.brief_notes`, which `get_today`
renders as `notices[]` — the "statement to Joe naming the hypothesis and the check that failed".

### 6. Deviation from B9: the refutation tests are implemented here, not via DoWhy
B9 specifies `dowhy`'s `placebo_treatment_refuter`, `random_common_cause` and `data_subset_refuter`.
**DoWhy does not install on this machine**: every release requires Python < 3.14 (0.14 requires
`>=3.9,<3.14`) and the only interpreter available to Joe is 3.14.3. It would install on the GitHub runner
(3.12), which means the check would exist only where Joe cannot run it — and "if the only proof a thing
works is that you say so, it is not proven" (CLAUDE.md). The three refuters are therefore implemented in
`confirm.refuters`, deterministically and seeded from the hypothesis id, over the same HAC estimator
(one owner, RULE-11/12):
- **placebo treatment** — the exposure column replaced by a seeded permutation of itself; the effect must
  vanish (p >= 0.20);
- **random common cause** — a seeded standard-normal covariate added; the exposure's beta must stay inside
  the original HAC 95% interval;
- **data subset** — leave-one-contiguous-block-out (5 blocks); at least 80% of those refits must land
  inside the full-sample HAC interval. **Deliberately not DoWhy's random subsets.** A random 80% subset
  is nested in the full sample, so its estimate is correlated with the full estimate and lands inside a
  1.96-SE interval essentially always: measured, a clean effect, an estimate carried by four leverage
  points, and pure noise all scored share-inside 1.00 under both the mean rule and the share rule. A
  check that cannot fail is not protection. Contiguous blocks are the right resampling unit for a time
  series — the same reason the errors are HAC — and they catch the failure that matters here, an effect
  present in only part of the window.
This is a substitution of implementation, not of meaning, and it is recorded rather than silent. It also
removes a heavy dependency from a $0 nightly job (RULE-28). B9's test name
`test_REQ_TIER_014_dowhy_placebo_failure_refutes` is renamed
`test_REQ_TIER_014_refutation_test_failure_refutes` (with a separate test that the placebo does not flag a
real effect), because a test named for DoWhy that does not use DoWhy would be a false name.

### 7. Conflict with REQ-TIER-025, resolved in the spec's favour
B9's envelope specifies `effect:{beta, unit, ci:[lo,hi], hac_maxlags}`. REQ-TIER-025 says the reasoning
layer "SHALL NOT render a frequentist confidence interval on any user-facing surface". `get_findings` is
a user-facing surface. The interval is therefore **stored** on the ledger row (`ci_lo`, `ci_hi` — needed
for the E-value at the limit, and reachable through the trace for audit) and **not rendered**: the
envelope carries `prob_direction` instead, the direct probability-of-direction statement REQ-TIER-025
asks for. A genuine Bayesian credible interval arrives with B19's NumPyro layer; until then the payload
states a probability of direction and no interval. Recorded, not silently substituted.

### 8. The ladder is enforced in the database
`reject_tier_skip` (a BEFORE UPDATE trigger on `hypothesis_register`) rejects any promotion that skips a
step (REQ-TIER-040) — `INSUFFICIENT -> CONFIRMED_OBSERVATIONAL` raises. Any downward move, and `REFUTED`
from anywhere, is permitted in one step (REQ-TIER-041). No path anywhere asks for human approval
(REQ-TIER-044). Every ledger row carries `run_id`, the `ops.runs` id of the job that wrote it
(REQ-TIER-042), stamped by `tools/run_confirm.py` before the gate runs.

### 9. Re-confirmation is monthly
A `CONFIRMED_OBSERVATIONAL` row carries `next_recheck = confirmed_at + 30 days`. On that day the whole
gate re-runs on the rolling window; failure demotes to `PROMOTED` with `demoted_recheck_failed` and a
brief notice. Confirmation is a lease, not a deed.

### 10. Forward predictions are scored (RULE-20, OQ-44 (a))
`confirm.score_predictions` scores any pending `resolve-*` prediction whose `resolves_at` has passed:
`outcome_bool` = the registered sign holds with p < 0.10 on the post-promotion window;
`brier = (p_forecast - outcome)^2`. With ADR-0049's `p_forecast = 0.5` every Brier is 0.25 by
construction until the calibration ledger holds 20 scored resolutions — the surface says so.

### 11. What the negative controls cost
The future-exposure control passes only when its p is at least 0.20, so on a pair with no relationship
it wrongly refutes about one time in five. That is a power cost, not a correctness fault — it removes
claims, never adds them — but it is worth stating: a genuine finding has roughly a 20% chance of being
refuted by chance on this check alone at each evaluation. B9 sets the bar; it is not tuned here.

## Consequences
- `CONFIRMED_OBSERVATIONAL` is reachable, and only through: a registered DAG edge, a minimal backdoor
  set, HAC errors, two E-values, two negative controls, three refutation tests, and an interval excluding
  the null with the registered sign. On pure noise the whole conjunction fires 3.0% of the time.
- A confirmed claim renders with its adjustment set, its E-value and its negative-control result in the
  same payload (REQ-TIER-023), in absolute units (REQ-TIER-024), with the counter-frame (REQ-TIER-028).
- Nothing can be confirmed that the DAG does not know. Extending the DAG is Joe's, by migration.

## Not built
Bayesian credible intervals (B19); micro-trials and the `EXPERIMENTAL` tier (REQ-TIER-015);
REQ-TIER-045's coverage-triggered re-rendering of a confirmed finding; the counter-frame uses the
exposure's bottom quartile as "absent", which is a proxy — a true absence needs the three-valued presence
of RULE-07, which the panel does not carry.
