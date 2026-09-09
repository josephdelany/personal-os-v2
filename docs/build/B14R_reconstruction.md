# B14R — Evidence reconstruction and historical use

Required sub-build of M4, before M5 consumes reconstructed events. Complements B14;
not a new service, unrestricted chatbot or replacement for the existing statistics.
Requirements: REQ-REC-001..016. Acceptance: docs/INTENT_COVERAGE.md R1-R12.

## Implementation sequence

1. Inventory project manifests, export members/types and live source metadata read-only.
   Emit counts/date coverage/dispositions and consumers; mark merely mentioned assets
   unverified. Keep personal details out of Git. Reconcile overlap before production load.
2. Catalogue derivations with input fields, units, methods, time/coverage rules and owners.
   Integrate existing B18/B21 formulas; do not create competing metric definitions.
3. Inspect existing entities/links, captures, correction and computation schemas. Write
   the additive schema/permissions ADR before migration. Reserve migration numbers from
   actual Git, not this brief. Preserve inferred versus measured storage and knowledge time.
4. Implement a versioned event-method registry and deterministic evaluator with evidence
   lineage, common-origin groups, contradiction and alternatives, and explicit unknowns.
   Candidate proposals may be model-assisted only through existing validated/budgeted
   services; models never select execution windows or mint unsupported numeric values.
5. Expose stored reconstructions through registered Ask and Record responses. Reuse
   owner authentication, numeral verification and historical-cutoff contracts. Add source
   dependence/uncertainty contracts to B19 consumers and clarification hooks to B16.
6. Implement reconstruction-local R1-R8/R10/R12 acceptance cases with requirement-ID
   test names. Expose the uncertainty/lineage contract for M5, which implements and
   closes R9/R11 against B19. All R1-R12 are required at M6; M4 does not depend on M5. Verify one
   end-to-end real source case where available; report genuinely unavailable inputs as
   blocked rather than manufacturing records. Run full checks at integration, then deploy
   only under applicable authorization. Update the evidence ledger and checkpoint.

## Ready/done distinction

A table and a linking rule do not complete this unit. It closes only with acceptance
coverage across multiple event families, historical corrections, dependent evidence,
missingness, model fallback and a published uncertainty/lineage contract. Actual
downstream propagation is verified by R9/R11 in M5, not an M4 closure prerequisite. A calibrated probability
is not required to emit an uncertain reconstruction; an unsupported probability is forbidden.
No protected metric definition or numerical confidence threshold is decided by this brief.

Historical derivations must preserve RULE-04. Event-time range and knowledge cutoff
are distinct; before writing any late-import derivation, the schema/method ADR must
show how the stored analysis window and input recorded_at satisfy the invariant.
If current storage cannot represent this, keep that operation open rather than
backdating evidence or interpreting away the invariant. Unquantified uncertainty
uses permitted insufficient/ambiguity templates, not unsupported “likely/probably”
wording in violation of REQ-TIER-026.
