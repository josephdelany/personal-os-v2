# REQUIREMENTS INDEX

Every requirement in this project has a stable ID. IDs are how work is
assigned, how tests are named, and how drift becomes detectable. A commit that
implements something must quote the IDs it satisfies; a test must carry the ID
in its name.

All requirements are written in **EARS** — Easy Approach to Requirements
Syntax, from Rolls-Royce, adopted by AWS in Kiro. Five patterns:

| Pattern | Template |
|---|---|
| Ubiquitous | `The <system> SHALL <response>` |
| Event-driven | `WHEN <trigger>, the <system> SHALL <response>` |
| State-driven | `WHILE <precondition>, the <system> SHALL <response>` |
| Unwanted behaviour | `IF <trigger>, THEN the <system> SHALL <response>` |
| Optional feature | `WHERE <feature is included>, the <system> SHALL <response>` |

`SHALL` is binding. `SHOULD` does not appear anywhere in this project — if it
is optional, it is not a requirement. One requirement per statement. Every
response is observable. Numbers, never adjectives.

---

## Current coverage — 587 requirements, 36 scenarios

| Prefix | Count | Subsystem | File |
|---|---|---|---|
| `REQ-ONT` | 17 | Ontology — the closed `atoms.kind` and `entities.entity_type` taxonomies, atom controlled vocabularies | `specs/05-ontology/requirements.md` |
| `REQ-NFR` | 4 | Non-functional (reliability) — the Supabase 7-day and GitHub Actions 60-day keepalives and their `ops.runs` evidence | `specs/06-nfr/requirements.md` |
| `REQ-CAP` | 101 | Capture — Shortcuts ingress, transcription, extraction, prompting; per-subject extraction profiles (REQ-CAP-108/109), location capture path (REQ-CAP-110), three-valued-presence capture (REQ-CAP-111) | `specs/02-capture-nutrition/requirements.md` |
| `REQ-NUT` | 57 | Nutrition resolution — USDA lookup, portions, intervals | `specs/02-capture-nutrition/requirements.md` |
| `REQ-FIN` | 173 | Finance — ingestion, merchant resolution, usage inference, restraint | `specs/03-finance/requirements.md` |
| `REQ-INF` | 140 | Inference — multiplicity, pre-registration, trials, predictions, cross-lens; on-demand exploration (REQ-INF-412/413, Missing-G) | `specs/04-reasoning/requirements.md` |
| `REQ-TIER` | 43 | The six-tier evidence ladder; the EXPLORATORY surface (REQ-TIER-050..053, Missing-F/ADR-0032) | `specs/04-reasoning/requirements.md` |
| `REQ-NAR` | 29 | Narration — numeral templates, vocabulary linting, degradation | `specs/04-reasoning/requirements.md` |
| `REQ-ASK` | 23 | Open-ended question answering — the PHIA loop | `specs/04-reasoning/requirements.md` |

**Gherkin acceptance scenarios: 12 per file, 36 total.** These are the artifact
Joe verifies against, because they are readable without reading code and they
either pass or fail visibly.

## Not yet written

| Prefix | Subsystem | Blocked by |
|---|---|---|
| `REQ-WKT` | Workout — e1RM, sets, RPE, volume, ACWR | The objective function. **This is the largest remaining gap** — the previous hypothesis library had zero coverage of e1RM, sets, RPE, lean mass or calories, which is to say zero coverage of the system's stated purpose |
| `REQ-BOD` | Body composition — Kalman weight and TDEE, lean mass | ADR-0005 |
| `REQ-SLP` | Sleep and recovery | — |
| `REQ-CTX` | Context — location, media, alcohol, screen time | Extraction from archived `08` (location storage unblocked by ADR-0029 / the reworded RULE-29) |
| `REQ-ACT` | Action — the *generation* machinery for recommendations: when to recommend (proactive vs on-demand), cadence, the scored-prediction/auto-demotion loop applied to recommendations, the action vocabulary, an optional "what to do today" digest | **Authoring opened (ADR-0029).** Must **reconcile with, not duplicate, REQ-TIER-047/048/049**, which already specify the recommendation *disclosure contract* (session-end reviewer, ADR-0029 addendum). Scope in ADR-0029 §D4 / `docs/CONSTITUTION_RESTRUCTURE_PROPOSAL.md` §4. Blocked on OQ-30 (residual tier floor + REQ-FIN-190/198 reconciliation) and the tier-labelling surface (RULE-17). No requirement numbered until OQ-30 is ruled |
| `REQ-UI` | Interface | Phase 7, deliberately last |

## Rules for adding requirements

Every requirements file ends each section with three mandatory subsections:
**NON-GOALS**, **ALTERNATIVES CONSIDERED**, **UNRESOLVED QUESTIONS**. The third
feeds `docs/OPEN_QUESTIONS.md` and is the mechanism by which an agent is
required to ask rather than quietly decide.

A requirement never encodes a technology choice. "SHALL store in a Postgres
JSONB column" welds a design decision into a requirement and makes the design
unrevisitable. Requirements say *what must be true*; ADRs say *how*.

IDs are never reused and never renumbered. A retired requirement is marked
`WITHDRAWN` with a date and stays in the file.
