# FRONT-END PLAN — the whole thing, built once, under the constitution

**Status:** decided plan (2026-09-02). Supersedes `FRONTEND_DESIGN_BRIEF.md`'s
"your canvas" framing. Source of the design: Joe's own `FRONT_END_SPEC.md`
(2026-07-29, old workspace) — "show everything, 10x deeper" — reconciled with
the ratified constitution and the live backend.

---

## 0. What Joe already decided (July 29) — recalled, not reinvented

> "I want literally everything I could possibly want to know. The app tracks it
> all, so it needs to properly show it."

**Every domain is a full mini-app.** Not a feed of cards — a *program*. The "8
apps combined" is literal: each domain tab is the best-in-class app for that
domain, rebuilt on your data, and every one of them is wired into every other.

| Domain (the "app" it replaces) | Pillar | Data density today |
|---|---|---|
| Sleep *(Oura)* | BODY | RICH — 1,340 nights to 2023 |
| Recovery / HRV *(WHOOP)* | BODY | RICH — 1,407 days |
| Circadian rhythm | BODY | RICH |
| Vitals / temp | BODY | RICH-small — 291 days |
| Body composition *(Withings)* | BODY | THIN, stale |
| Cardio load / training load | BODY | MODERATE, stale |
| Illness guardian | BODY | derived |
| Activity / steps *(Apple Health)* | MOVEMENT | RICH — to 2019, deepest series |
| Gait / mobility | MOVEMENT | RICH — 7,082 days |
| Workouts *(Strong / Hevy)* | MOVEMENT | **EMPTY — objective function** |
| Food / nutrition *(MyFitnessPal)* | FUEL | EMPTY — capture-gated |
| Hydration · Supplements · Substances *(alcohol)* | FUEL | EMPTY / THIN |
| Attention / focus *(RescueTime)* | MIND | RICH — 8,831 days |
| Mood / energy / stress *(Daylio)* | MIND | THIN — check-ins |
| Finance / spend *(Mint / YNAB)* | LIFE | RICH — 1,032 tx |
| Content diet *(YouTube / browsing)* | LIFE | RICH — 28,102 rows |
| Places / travel *(Google Timeline)* | LIFE | THIN — from 2026-07 |
| Email · Calendar · Code · Weather · Social | LIFE | MODERATE / THIN / driver-only |

**The Universal Domain Module.** Every one of those tabs is built from the
*same nine-module skeleton*, top to bottom. Learn it once; every domain has
identical depth. Thin domains degrade to a capture nudge, never a fake chart.

1. **Hero verdict** — how am I on this right now, vs *my* normal. One honest
   sentence, one number, the personal band.
2. **Contributors** — *why* it's that. Named sub-factors, which ones drag.
3. **History** — the trend, 7d → all-time, with the personal rolling band.
4. **Weekly / seasonal pattern** — which weekday, which hour, which season.
5. **Within-domain notables** — anomalies, changepoints, records.
6. **What drives this ↑ / what this drives ↓** — the cross-domain layer. The
   10x feature. Two ranked lists per domain: inputs and outputs.
7. **Forecast** — where it's heading, with a band and its track record.
8. **Entity drill-down** — which merchant, which place, which exercise.
9. **Capture / correct** — log or fix, inline.

**On top: the Intelligence layer** — Patterns, Compare ("X on Y-days"),
Discoveries, Experiments, the driver→outcome map. **Then Today, Timeline, Me.**

This is the god's-eye: every stream captured, every domain a full program,
every program talking to every other, one brain on top.

---

## 1. What the constitution changed about it — module by module

The July spec was written before the rebuild. Nine of its elements survive
unchanged. Five are altered by rules you ratified. Nothing here is a new
restriction — it's your own later decisions applied to your own earlier design.

| Element | July spec | Now | Rule |
|---|---|---|---|
| Hero verdict | number + 3-state colour + band + sentence | **same, minus any ring/gauge** | RULE-24 |
| Contributors | bars, red = drag | same | — |
| History chart | line + personal band | same — descriptive charts are fine in domain tabs | RULE-14 |
| Weekly / seasonal | bars | same | — |
| Notables | anomalies, PR badges, **streak chips** | anomalies + records as plain facts; **no streak chips, no badges, no flames** | RULE-24 |
| Module 6 cards | "Proven" + confidence stars + scatter/backtest expander | **EXPLORATORY badge, tier word not stars, verbatim hedged sentence, n / n_eff / q — text and labels only, no expander charts** | RULE-17, ADR-0032 |
| Confidence chip | proven / likely / suggestive / guess | **the six-tier vocabulary only**; nothing else may appear on a number | RULE-16 |
| Forecast | value + band | same, **and the track record must show beside it** | RULE-20 |
| Driver→outcome map | rendered graph | **list form until RULE-17's revisit trigger** (exploratory content is text-only) | ADR-0032 |
| Recovery ring / composite scores | hero gauges | **gone** — personal bands and honest state instead | RULE-24 |
| Sankey, pixel mosaic, multi-lane graph | allowed | allowed — descriptive | — |
| Capture / correct | ✓ ✗ ✎ | same; a correction is a human override with provenance (OQ-32) | RULE-10 |

**The single biggest change is what feeds Module 6.** The July spec ran on
1,398 "validated insights" — 666 of them "proven." The rebuild proved those
were mostly tautologies and noise. The new engine, run honestly, keeps **19
patterns** from 123 tested against a null median of 87. So every domain's
"what drives this" list will be *short*, and many will be empty for months.
The design has to be beautiful when empty, because it will be.

---

## 2. Why you don't like the current app — precisely

It is the July IA with the depth removed and the dishonesty left in.

- **It has the tabs and not the modules.** Domains is a flat list of numbers
  with no drill-down; tap Sleep and you don't get the nine-module Sleep app.
- **Today is a feed of "Proven" cards** from the old engine — the exact
  lie-machine — including two that contradict each other on the same screen.
- **The Intelligence loops are sentence templates filled with noise** ("light
  sleep % nudges discretionary spending, which loops back through
  discretionary spending" — the lever and the mediator are the same variable).
- **Nothing is traceable.** No atom ids, no tiers, no n_eff, no null.
- **No Trust surface** exists at all.

What's *good* and should be kept: the Domains page's staleness labels and
"Nothing captured yet"; the Timeline's day picker and "Nothing logged for this
day"; the dark-teal token system; the bottom-tab + desktop-bento shell; the PWA
manifest; the Ask box (rewired).

---

## 3. The credit-efficient build — this is how finite Lovable survives

Three principles, and they are the whole strategy.

**A. Build the Universal Domain Module ONCE. Domains are configuration, not
code.** One round builds the nine-module component. One round adds a
`domains.config` file that instantiates it for every domain. Adding a domain
later is a config line, not a Lovable round. This is where most of the credits
are saved.

**B. Lovable never computes. Every module reads exactly one envelope field.**
Where the backend doesn't supply what a module needs, the gap is closed by
Claude Code — free — *before* the Lovable round, never during it. A Lovable
round that discovers a data gap is a wasted round.

**C. One round = one screen family, frozen contract, screenshot-verified.**
No round starts until its envelope is live and returning real data. No
"fix" rounds spent on backend bugs.

---

## 4. Backend gaps — Claude Code, free, before any Lovable round

The live backend has six RPCs: `get_today`, `get_timeline`, `get_patterns`,
`get_trust`, `get_insights_guarded`, `get_day` (+ `register_watch`). The
nine-module skeleton needs more. **These are built first, at $0.**

| Gap | What it returns | Feeds |
|---|---|---|
| **`get_domain(domain)`** — the big one | hero (latest, band, z, sentence) · contributors · history series · weekday/hour signature · notables · patterns_in / patterns_out (EXPLORATORY, from the tree-FDR scan) · forecast + track record · entities · staleness | Modules 1–8 for every domain |
| `domains.config` | pillars → domains → metric keys → density → "replaces app X" | the Domains index + module instantiation |
| `get_compare(metric, condition)` | with/without distributions, delta, CI, n | Intelligence → Compare |
| `get_period(week)` | plan-vs-actual, most/least, new patterns that crossed, records | Daily → weekly report |
| `get_entity(id)` | per-merchant / place / exercise detail | Module 8 |

`get_domain` is roughly 80% of the front end's data needs in one envelope,
and it's the thing the current app never had — which is why tapping a domain
goes nowhere.

---

## 5. The rounds

| Round | Builds | Verify by |
|---|---|---|
| **R0 — Kill and rewire** | Remove every read of old tables and RPCs. Delete the "Proven" feed, the loops, the council, readiness. Keep the shell, tokens, tabs, PWA, auth. Empty states everywhere. | No old data anywhere; every screen renders honestly empty |
| **R1 — The Universal Domain Module** | The nine-module component, config-driven, against `get_domain`. Instantiated for **three RICH domains only**: Sleep, Finance, Attention. | Three domain tabs at full depth, real data, every numeral traceable |
| **R2 — Every domain** | `domains.config` → all ~20 domains. Domains index grouped by pillar with density and staleness. Thin/empty domains show the capture nudge. | Every domain reachable; empty ones honest |
| **R3 — Intelligence** | Patterns (text-only, EXPLORATORY-badged, calibration line verbatim, Watch buttons) · Compare · Trust (claimed vs achieved, refutations, blindspots, heartbeats) | The 19 patterns render; Trust shows the null |
| **R4 — Today + Timeline + Period** | Today as state-not-claims: verdict, bands, what's stale, what's uncaptured, patterns as a count. Timeline with the ribbon. Weekly report. | Today is quiet and true |
| **R5 — Me** | Ask (rewired to the conversation layer), capture settings, goals, profile | Ask answers from atoms with ids |
| **R6 — Polish** | Density, motion, dark mode, reduced-motion, tabular numerals | Screenshots vs the laws |

Six rounds, plus one or two for fixes. R0 first because it's the destructive
step and cheapest while nothing depends on it.

---

## 6. Decisions only Joe can make

1. **Final domain list** — the table in §0 is the July list; confirm or cut.
2. **The first three domains for R1** — Sleep, Finance, Attention are the
   richest. Swap if you'd rather see a different one first.
3. **Compare in v1 or v2?** It's the "wrist temp on leg day" surface and it
   needs a conditions registry that doesn't exist yet.
4. **Tab names.** Today · Domains · Intelligence · Timeline · Me, or your own.
5. **The empty-state voice.** Most of FUEL and Workouts will read "not logged"
   for weeks. Do you want that plain, or with the one-line capture nudge?

---

## 7. What this does not fix

The front end can only show what's captured. Workouts — your objective
function — has zero rows. FUEL is empty. Most BODY metrics are 30–270 days
stale. The most beautiful Sleep app in the world reads "stale · 35d ago" until
the export refreshes. Capture is still the clock that's running.
