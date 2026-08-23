# ADR-0007: Multiplicity control — e-values as the family-wide FDR currency (e-BH)

## Status

Accepted (amends RULE-21; amends REQ-INF-106). Fills the reserved ADR-0007
(multiplicity control).

## Date

2026-08-23

## Context

RULE-21 controls multiplicity with tree-structured FDR (domain → variable-pair →
lag) and mandates HAC standard errors and `n_eff`. REQ-INF-106 binds the rejection
rule to Benjamini–Hochberg over p-values. Two facts make BH-on-p the wrong
currency **for how Joe uses the system**:

- Joe **peeks constantly**. Every optional look at an accumulating result
  invalidates a fixed-sample BH p-value guarantee.
- **e-values are immune to optional stopping** (anytime-valid), compose by
  multiplication, and support e-BH under arbitrary dependence — *for valid
  e-values* (nonnegative, expectation ≤ 1 under the null). Verified: Wang &
  Ramdas, e-values review; Wang–Ramdas 2022.

Two corrections to the original justification (both accepted by Joe, 2026-08-23):

1. **A p-value *can* be converted to an e-value post-hoc**, via a calibrator
   (e.g. `e = κ·p^{κ−1}`). The claim that it cannot was **wrong**. The real cost
   is **power loss**, not impossibility. We store native e-values *because
   calibration is lossy*, not because conversion is impossible.
2. **arXiv:2502.08539** ("Anytime-valid FDR control with the stopped e-BH
   procedure," Wang, Dandapanthula, Ramdas) is a **cautionary** paper: stopped
   e-BH *can fail* FDR control unless an extra no-unobserved-confounding
   assumption (its Assumption 3.1) holds. Cite it only as "conditions under which
   stopped e-BH is valid," never as "e-BH just works."

e-values are **not greenfield here**: REQ-INF-112 already gates the CONFIRMED →
micro-trial step on a stored E-value below 1.5. That is a *single-hypothesis gate
at one tier*; the change is to make a stored e-value the *family-wide* rejection
currency on every test row.

## Decision

- On every test/finding row store the **e-value** and the **sufficient statistics
  to recompute it** (`e_value`, `e_value_method`, `e_process_params JSONB`), plus
  the existing `n_eff`, `rho`, `maxlags`, and a persisted `family_size`
  (REQ-INF-106). Store a `p_value` too where one exists, for interpretability
  only — the **gate is the e-value**.
- Keep the RULE-21 tree-FDR structure; **e-BH replaces BH-on-p as the rejection
  rule**. This amends RULE-21 **and** REQ-INF-106 (a binding SHALL), so it is a
  requirement change, not only a rule change.
- **This is a trade, not a strict upgrade.** e-values cost power when you *don't*
  peek. Joe accepts the trade explicitly: he peeks constantly, so anytime-validity
  is worth the power to him. An analysis run once and never re-peeked would be more
  powerful with a p-value — that case is not how this system is used.

Shape locked this phase (`core.findings`); the e-BH **compute** is Phase 6.

## Consequences

**Good.** Peeking no longer invalidates inference. Evidence composes across looks
by multiplication. The gate matches the usage pattern.

**Bad.** Lower power on never-re-peeked analyses. A dependency (`online-fdr`, PyPI,
BSD-3, single-maintainer ~0.0.x) is implied for e-LOND/e-BH — **a RULE-28
dependency ADR is owed before it is added**, pinning the version and verifying
e-LOND is in the installed wheel (absent from the 0.0.3 snapshot).

## Alternatives considered

- **Keep BH-on-p, add a peeking penalty.** Rejected: no penalty is calibratable
  against unbounded, undocumented optional stopping.
- **Store p-values, calibrate to e-values on demand.** Rejected: calibration is
  lossy; store the native e-value.
