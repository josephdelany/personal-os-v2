# DECISIONS — ADR index

One line per decision. Read the full ADR before changing anything it covers.
ADRs are immutable: a superseded decision is marked superseded and kept, never
edited and never deleted, because the reason it was made is the thing worth
preserving.

| ID | Status | Date | Decision |
|---|---|---|---|
| ADR-0001 | Accepted | 2026-08-06 | Compute placement — three tiers, one owner per number, model plans and narrates but never computes |
| ADR-0002 | Accepted | 2026-08-06 | The atom — bitemporal, three-valued presence, interval-valued, `state_class` in the schema |
| ADR-0005 | Stub | 2026-08-15 | Nutrition resolution — **stub**: records only the `weighed` interval width (±10%, equal to `labelled`, provisional; distinct method kept for calibration). Cache-first lookup, portion table, and remaining widths still to be authored before Phase 3 |

## Awaiting authorship

These are decisions already implied by the requirements and not yet written up.
Each must exist before the code it governs is written.

| ID | Decision to record |
|---|---|
| ADR-0003 | Evidence ladder — six tiers, permitted vocabulary per tier, promotion and demotion rules |
| ADR-0004 | Entity resolution — blocking keys, match thresholds, the review queue, the human-adjudication invariant |
| ADR-0006 | Transaction ingestion — CSV/QFX plus Gmail parsing, `occurred_at` vs `posted_at`, dedupe key |
| ADR-0007 | Multiplicity control — the family tree, hierarchical FDR, HAC standard errors, `n_eff` |
| ADR-0008 | Capture transport — the Shortcuts-to-endpoint contract, idempotency, offline queue |
| ADR-0009 | Design tokens and honesty grammar — carried forward from the archived UI system |
| ADR-0010 | RULE-02 enforcement hardening — atoms/`raw_captures` mutation-rejecting trigger, the owner/`service_role` bypass, and which DB role each job connects as. (Number confirmed 2026-08-15: Joe's Session-1 ruling said "ADR-0003", which is already reserved above for the Evidence ladder; ADR-0010 is the corrected free number.) |

**Note — ADR-0005 is a stub, not unwritten.** Its `weighed`-width decision is
written and accepted (see the top table and `docs/adr/0005-nutrition-resolution.md`).
Its remaining scope is still owed before Phase 3 and is deliberately kept out of
the table above so no row's status is self-contradictory: cache-first USDA
lookup, the personal portion table, the other method widths, and the count→grams
rule for branded items (REQ-NUT-050/051).
