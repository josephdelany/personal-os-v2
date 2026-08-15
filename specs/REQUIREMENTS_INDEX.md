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

## Current coverage — 543 requirements, 36 scenarios

| Prefix | Count | Subsystem | File |
|---|---|---|---|
| `REQ-CAP` | 97 | Capture — Shortcuts ingress, transcription, extraction, prompting | `specs/02-capture-nutrition/requirements.md` |
| `REQ-NUT` | 55 | Nutrition resolution — USDA lookup, portions, intervals | `specs/02-capture-nutrition/requirements.md` |
| `REQ-FIN` | 165 | Finance — ingestion, merchant resolution, usage inference, restraint | `specs/03-finance/requirements.md` |
| `REQ-INF` | 137 | Inference — multiplicity, pre-registration, trials, predictions, cross-lens | `specs/04-reasoning/requirements.md` |
| `REQ-TIER` | 39 | The six-tier evidence ladder | `specs/04-reasoning/requirements.md` |
| `REQ-NAR` | 27 | Narration — numeral templates, vocabulary linting, degradation | `specs/04-reasoning/requirements.md` |
| `REQ-ASK` | 23 | Open-ended question answering — the PHIA loop | `specs/04-reasoning/requirements.md` |

**Gherkin acceptance scenarios: 12 per file, 36 total.** These are the artifact
Joe verifies against, because they are readable without reading code and they
either pass or fail visibly.

## Not yet written

| Prefix | Subsystem | Blocked by |
|---|---|---|
| `REQ-ONT` | Ontology, atoms, entity resolution, the metric registry | ADR-0002 accepted; requirements not yet extracted |
| `REQ-WKT` | Workout — e1RM, sets, RPE, volume, ACWR | The objective function. **This is the largest remaining gap** — the previous hypothesis library had zero coverage of e1RM, sets, RPE, lean mass or calories, which is to say zero coverage of the system's stated purpose |
| `REQ-BOD` | Body composition — Kalman weight and TDEE, lean mass | ADR-0005 |
| `REQ-SLP` | Sleep and recovery | — |
| `REQ-CTX` | Context — location, media, alcohol, screen time | Extraction from archived `08` |
| `REQ-NFR` | Non-functional — cost, privacy, performance, reliability | Partly in `CONSTITUTION.md` §V; needs numeric form |
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
