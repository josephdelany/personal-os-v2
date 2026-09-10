# Backend completion — reconciled against Git, 2026-09-09

Reconciled at `cd30ec8` by inspecting code, tests and the live database, not by reading the
plan's own claims. Status words are kept apart deliberately:

- **implemented** — code exists in the repository
- **tested** — a named test containing the requirement ID passes
- **deployed** — applied to the production database
- **observed** — verified working against real data in production

Passing tests, deployed tables and correct refusals do not establish completion. A capability
is complete only when it is *observed*.

## Requirement coverage, measured 2026-09-10

`tools/audit_requirements.py`. A requirement counts as PROVEN only when a test whose NAME
carries its ID passes — the project's own rule, and deliberately the only thing accepted. Not a
mention in an ADR, not an implementation that looks right, not a docstring citing the ID.

```
  prefix         declared  proven  claimed  unproven
  REQ-ACT              12       2        7        10
  REQ-ASK              25      21        0         4
  REQ-CAP             101       7        2        94
  REQ-FIN             173      19        2       154
  REQ-INF             140       9        4       131
  REQ-LOC              18      12        0         6
  REQ-NAR              29       7        0        22
  REQ-NFR              14      14        0         0
  REQ-NUT              60      23        3        37
  REQ-ONT              17       3        0        14
  REQ-REC              16      13        0         3
  REQ-SLP              15      11        0         4
  REQ-TIER             43      18        2        25
  REQ-WKT              22       9        1        13
  TOTAL               685     168       21       517

  168 of 685 requirements (25%) are proven by a test carrying their ID.
```

**168 of 685 (25%).** That number is low and it is the honest one. A ledger reporting 90%
because it counted every ID appearing anywhere would convert an absence of evidence into a
percentage, and nobody re-checks a percentage.

Read by prefix it says where the work is: REQ-NFR is complete (14/14), REQ-ASK nearly so
(21/25), and REQ-CAP (7/101), REQ-FIN (19/173) and REQ-INF (9/140) are barely begun. Those
three are 414 of the 517 unproven requirements. M6's "no unexplained open requirement" is a
long way off, and this is the list to explain.

## Milestone status

| Milestone | Implemented | Tested | Deployed | Observed |
|---|---|---|---|---|
| M0 integration baseline | yes | yes | n/a | **yes** |
| M1 recover collection | yes | yes | yes | **partial** |
| M2 deterministic Ask | partial | yes | yes | **partial** |
| M3 shared services + capture | partial | partial | yes (0050/0052) | **no** |
| M4 domain processing | partial | partial | partial (0054) | **no** |
| M5 remaining analysis | no | no | no | no |
| M6 backend release | no | no | no | no |
| M7 frontend | out of scope now | — | — | — |

## Unmet acceptance criteria, with dependency and next executable action

### M1 — recover collection
| Criterion | State | Dependency | Next action |
|---|---|---|---|
| 0051 applied with permission | **observed** | — | — |
| actual export reconciled | **observed** | — | OQ-56 closed: 252 records, all accounted |
| overlapping import idempotent | **observed** | — | 33,355 dedupe keys preloaded on re-run |
| withheld feed detected | **observed** | — | freshness: 9 fresh / 17 stale / 11 never seen |
| **new device observation arrives unattended** | **not met** | Joe: the Watch (OQ-55) | Joe checks the Watch; then a fresh export shows rows after 2026-08-21 |
| **deployed schedule verified** | **not met** | none | Add a scheduled `import_drop` / freshness workflow and show `ops.runs` rows for it |

### M2 — deterministic Ask
| Criterion | State | Dependency | Next action |
|---|---|---|---|
| required questions and adversarial cases pass | **tested**; observed for `describe` | — | 4 review rounds closed; 323 local tests |
| executor permission separation proven | **observed** | — | owner-only, `SECURITY DEFINER`, revoked from anon |
| **all registered operations meet full contracts** | **not met** | B14 entity resolution | `spend` has no merchant/category semantics (ADR-0062). Implement B14 entity resolution, then the `spend` merchant branch |
| **historical replay/provenance proven** | **partial** | migration 0056 authorization | The atom lane is bitemporal as of 0056; `analysis.panel` still has no `recorded_at` (OQ-45). Next: apply 0056, then decide whether the legacy panel gains `recorded_at` or is retired |
| **the panel serves imported atoms** | **implemented + tested, not deployed** | **0056 authorization** | Apply 0056 |

### M3 — shared services and capture
| Criterion | State | Dependency | Next action |
|---|---|---|---|
| one egress/budget contract | **deployed** (0052) | — | observed once a real call is made |
| validated planner and fallback | **tested** | — | — |
| **real planned question** | **not met** | a live Workers AI call | Run `tools/ask.py` on a question the grammar misses, with the neuron budget live |
| **real voice/photo path** | **not met** | B16 shortcuts + Joe installing them | Generate the shortcuts, Joe installs, one real capture lands |
| **reference-backed nutrition intervals** | **not met** | B12 source parser; `USDA_API_KEY` absent | Write the Open Food Facts parser (needs no key) against `config.egress_allowlist`; USDA stays blocked on the key |

### M4 — complete domain processing
| Criterion | State | Dependency | Next action |
|---|---|---|---|
| **entity/correction precedence** | **not implemented** | — | B14: entity resolution + correction precedence |
| **reconstruction-local R1-R8/R10/R12** | **5 of 12 at engine level** | B14 (R1), B18 (R2), B17 (R4) | Register the first reconstruction method; `config.reconstruction_methods` is empty so the engine can conclude nothing |
| **linked meal-charge-place** | **not implemented** | B14 | after entity resolution |
| **period/compare contracts** | **not implemented** | B15 (no code exists) | B15 |
| **finance reconciliation** | **not implemented** | B17 (no code beyond importers) | B17 |
| **per-set workout progression** | **capture path built, no data** | Joe logs sets | `tools/extract_workouts.py` is written and tested; the Watch has 25 sessions in 4 years and none contain sets |

### M5 / M6 — not started
B19, B20, B21 (analysis), B22, B23 (release) have briefs and no code. M6 additionally requires
the REQ-REC audit, deployed API and schedule evidence, a runbook, and no unexplained open
requirement.

## The critical path

Everything else is a branch off this line:

1. **Apply 0056** — needs Joe. Without it Ask cannot see 33,355 imported atoms, and M2's data
   half stays unmet.
2. **B14 entity resolution** — the widest dependency in the plan. It blocks `spend`'s merchant
   and category contract (M2), entity/correction precedence and meal-charge-place (M4), and
   reconstruction case R1.
3. **B14R method registration** — the reconstruction engine and schema are built and the
   registry is empty, so nothing can be concluded. Depends on B14 for the first real method.
4. **B15 period/compare, B17 finance, B18 workout derivation** — parallel after B14.
5. **B19/B20/B21** — analysis, which consumes reconstructed events (R9/R11).
6. **B22/B23** — release: audit, schedules, runbook, cutover.

## Safely independent, no shared files

- **B12 Open Food Facts parser** — `tools/engines/nutrition.py` + a new parser file. Needs no
  key, no migration, and touches nothing on the critical path.
- **A scheduled freshness/import workflow** — `.github/workflows/`, closes an M1 criterion.
- **B15 period/compare** — new files; depends on the panel, not on B14.
- **`_legacy_prerequisites.sql` → real DDL** (OQ-58) — only if Joe chooses that recovery story.

## Decisions only Joe can make

| # | Decision | What it unblocks | Recommendation |
|---|---|---|---|
| 1 | Apply migration 0056 | M2's data half; every metric question | Apply — chain verified clean, 323 tests, verified against production in a rolled-back transaction |
| 2 | The Watch (OQ-55) | 17 stale metrics | Check worn/paired/permissions/storage |
| 3 | The 20 Health types (OQ-57) | what the next import takes | Take `TimeInDaylight` + `EnvironmentalAudioExposure`; skip the rest |
| 4 | Log strength sets | the primary objective | Install the Log Workout shortcut |
| 5 | Recovery story (OQ-58) | disaster recovery | (b) restore-from-backup is cheaper and honest |

## Can the full scope fit in four days?

**No, and the bottleneck is not implementation speed.** M4 alone contains B14, B15, B17, B18
and B14R's method registration; M5 contains three unbuilt analysis units; M6 requires a
release audit across every requirement. That is weeks of work at the standard this codebase
holds — every unit here has carried adversarial review, requirement-ID tests and an ADR.

Two constraints dominate and neither is code:

1. **Capture cannot be compressed.** The Watch has been dark since 2026-08-21 and has never
   recorded a single strength set. No amount of implementation creates that data; it accrues
   only after the device is fixed and the shortcut is installed. M1's "new device observation
   arrives unattended" and M4's "per-set workout progression" are gated on elapsed time.
2. **Production writes need authorization each time**, which serialises deployment against
   Joe's availability rather than against work completed.

What can credibly fit in four days: apply 0056 and observe M2's data half; B14 entity
resolution with `spend`'s merchant contract; the first registered reconstruction method; the
Open Food Facts parser; a scheduled capture workflow. That closes M1 except the device, most
of M2, and the front of M4. M5 and M6 do not fit and saying otherwise would be the
completion-claim failure this project is built to prevent.
