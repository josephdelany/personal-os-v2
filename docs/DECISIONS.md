# DECISIONS — ADR index

One line per decision. Read the full ADR before changing anything it covers.
ADRs are immutable: a superseded decision is marked superseded and kept, never
edited and never deleted, because the reason it was made is the thing worth
preserving.

| ID | Status | Date | Decision |
|---|---|---|---|
| ADR-0001 | Accepted | 2026-08-06 | Compute placement — three tiers, one owner per number, model plans and narrates but never computes |
| ADR-0002 | Accepted | 2026-08-06 | The atom — bitemporal, three-valued presence, interval-valued, `state_class` in the schema |

## Awaiting authorship

These are decisions already implied by the requirements and not yet written up.
Each must exist before the code it governs is written.

| ID | Decision to record |
|---|---|
| ADR-0003 | Evidence ladder — six tiers, permitted vocabulary per tier, promotion and demotion rules |
| ADR-0004 | Entity resolution — blocking keys, match thresholds, the review queue, the human-adjudication invariant |
| ADR-0005 | Nutrition resolution — cache-first USDA lookup, personal portion table, interval widths by method |
| ADR-0006 | Transaction ingestion — CSV/QFX plus Gmail parsing, `occurred_at` vs `posted_at`, dedupe key |
| ADR-0007 | Multiplicity control — the family tree, hierarchical FDR, HAC standard errors, `n_eff` |
| ADR-0008 | Capture transport — the Shortcuts-to-endpoint contract, idempotency, offline queue |
| ADR-0009 | Design tokens and honesty grammar — carried forward from the archived UI system |
