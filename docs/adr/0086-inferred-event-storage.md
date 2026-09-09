# ADR-0086 — Reconstructed events are stored where a measurement cannot be

Status: accepted
Date: 2026-09-09
Requirements: REQ-REC-005..012. Acceptance: INTENT_COVERAGE R3, R5, R6, R12.
Migration: 0054 (written, locally verified, NOT applied).

## Context

An atom is what a source recorded. A reconstructed event is what the system *concluded* —
"he ate there", "that was a lifting session" — from evidence that never says so directly.

The failure mode of this entire feature is a conclusion that reads like an observation six
months later. Nobody decides to do that; it happens when the conclusion and the observation
share a table, a lane, or a confidence vocabulary, and the distinction survives only as a
convention someone has to remember.

## Decision

Three tables, and the constraints are the unit.

**`config.reconstruction_methods`** (REQ-REC-006). Methods are registered and versioned and
declare their required evidence, permissible outputs and temporal specification before they
run. `inferred_events` carries a composite foreign key into it, so a method the registry does
not contain cannot produce a row. A model may propose a candidate; it never invents the rule,
selects the window, or mints a number (RULE-11, RULE-13).

**`core.inferred_events`** (REQ-REC-005). It has **no `value_point`, `value_low`,
`value_high`, `unit` or `estimate_method`**. The separation from measurement is structural,
not conventional: the table is incapable of storing a measured value, so a conclusion can
never be read back as one (INV-5, RULE-05). It carries event-time bounds and knowledge time
as different clocks, because conflating them is how a replayed answer silently improves
(RULE-04, INV-4).

**`core.event_evidence`** (REQ-REC-007/008), carrying `stance` and `origin_group`.

### The constraints that matter

- **`probability_requires_calibration`** (REQ-REC-010) is the central one. A number in the
  `probability` column with no stored calibration is a made-up confidence wearing a percent
  sign, and every consumer downstream would read it as measured. An uncalibrated `rule_score`
  is allowed — it simply may not call itself a chance.
- **`alternatives_are_disclosed`** (REQ-REC-007). An empty alternative set is a statement, not
  a blank: either alternatives are listed, or `no_alternative_generator` says on the row's
  face that none applied. Silence is indistinguishable from having considered none.
- **`unknown_carries_no_score`** (REQ-REC-009). RULE-07's three-valued presence. If coverage
  cannot establish that an event did *not* happen, the answer is `unknown` — and unknown with
  a 0.7 attached is not unknown.
- **`origin_group`** (REQ-REC-008) makes independence countable instead of assumed. A receipt
  copied into two sources alongside its bank charge is two origins, not three;
  `v_event_independence` counts distinct origins, not rows. This is INTENT_COVERAGE R5, and
  the row-count version is how a reconstruction talks itself into confidence it never earned.
- **Human precedence** (REQ-REC-011), enforced by trigger: the engine may revise itself but
  may not supersede a human interpretation. Without it the next scheduled run reverts every
  correction Joe ever made, and the revision history presents that as an improvement.
- **Append-only** (RULE-02, INV-2), by trigger, like every other record of what happened. A
  correction appends and `v_current_events` reads the head of each chain, so the earlier
  interpretation and the evidence available at its cutoff stay readable (REQ-REC-012).

## What this does not decide

No reconstruction method is registered by this migration — the table is empty, and an empty
method registry means the engine can conclude nothing. Registering `meal_from_charge` is
B14R step 4 and it depends on B14's entity resolution, which is not built.

Nothing here calibrates anything, so in practice every early reconstruction will carry a
`rule_score` and a NULL `probability`. That is the intended behaviour, not a limitation to be
worked around later: REQ-REC-010 says an uncalibrated system reports uncertainty as
unquantified, and the constraint makes that the path of least resistance rather than a
discipline.

R9 and R11 — inferred events flowing into analysis — belong to M5 and are not addressed here.

## Alternative rejected

Storing reconstructions as atoms with `estimate_method='inferred'` and a `confidence` column.
It is less code and it is what the existing atoms table almost supports. It was rejected
because it puts the conclusion one column away from every measured value in the system, and
every query that forgets the filter reads a story as a fact. INV-5 exists for this.
