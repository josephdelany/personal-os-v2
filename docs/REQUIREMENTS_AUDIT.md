# REQUIREMENTS AUDIT — ratification worksheet

**Status: RATIFIED 2026-08-24 (Joe, shorthand). Track 1.2 in progress.** This is the
ranked output of the requirements audit (REMEDIATION_PLAN sequence item 3 / Track 1.1).
Correction (Track 1.2) is now authorised for the ACCEPTED items below.

**Ratification summary (Joe, 2026-08-24):**
- **ACCEPT:** C-1, C-2 (each as its own pass — knowingly reversing acceptance tests +
  a governing principle), C-3, C-5, C-6, C-7, C-8, C-9, C-10, C-11, C-14, and all eight
  missing-sets A–H.
- **DEFER:** C-12, C-13, C-15, C-16, C-17.
- **REJECT:** none.
- **NEW RULING — strength-set granularity is PER SET:** one `workout` atom per set,
  carrying exercise, load, reps, RPE. e1RM, volume progression, and per-exercise trends
  all need per-set; it is the objective function. (Resolves the Missing-A follow-up + OQ-31.)
- **Migration boundary:** Track 1.2 stops before anything needing a migration (e.g. seeding
  `metric_registry` rows, or a schema change) — those wait for Joe.

**Method.** Five adversarial auditors, one per domain (REQ-CAP / REQ-NUT+ONT+NFR
/ REQ-FIN / REQ-INF / REQ-TIER+NAR+ASK), each running two jobs: conflict against
the eleven stated wants, and a sweep against the ten reworded rules (RULE-06, 13,
17, 19, 22, 23, 24, 25, 26, 29). Every HIGH/MED finding below was then
**re-verified by Claude against the actual requirement text** before ranking —
the marker `[verified verbatim]` means the quoted clause was confirmed at source.
LOW/framing items (#12–17) were taken on the auditors' report and are flagged
"for your eye," not asserted as defects.

**The organizing finding.** Nine of the ten reworded rules were *reversals* of a
former prohibition. Almost every live defect is the same shape: a requirement
still encoding the prohibition its governing rule just reversed. RULE-25 vs
REQ-FIN-190/198 was not a one-off — it is a pattern across finance, inference,
and narration.

**Scale.** ~17 conflicts over ~30 requirement IDs, plus 8 missing requirement-sets.

**Bookkeeping.** No count drift. A raw grep counts 570 "REQ-INF" IDs, but the six
"extra" (`REQ-INF-0..5`) are regex false positives from section headers written in
`4xx`/`0xx` shorthand (e.g. "GENERATOR-ONLY METHODS (REQ-INF-4xx)" matches
`REQ-INF-4`). `tools/validate_layout.py` counts 564 real IDs, REQ-INF=137 —
matching the index exactly. Corrected after the session-end reviewer caught the
grep artifact being presented as drift.

---

## PART 0 — RULED NOW (the two items with a hardening deadline)

These two were ruled by Joe on 2026-08-24 *before* ratifying the rest, because
they are the only items whose cost hardens with time. They are DECIDED. ADRs are
owed as the durable record (reserved **ADR-0030**, **ADR-0031**) — not yet
authored; authoring waits with the rest of Track 1.2.

### RULED-1 · Ontology members (Missing-A) — DECIDED, no new `atoms.kind`, no migration
**Ruling (Joe).**
- **Alcohol** is represented as `kind='consume'` + a `metric_key` (`standard drinks`,
  `ethanol grams`). No new kind, no migration. Generalises to caffeine, supplements,
  and medication rather than special-casing drink.
- **Mobility scalars** (radius of gyration, location entropy, commute, transit load)
  are **derived measures**, not atoms — they belong in `derived_measures` with
  `metric_registry` entries, never a new `atoms.kind`.

**Spine confirmation (Claude, verified against migrations 0002/0005/0014):**
- ✅ `consume` is already a member of the `atoms_kind_taxonomy` CHECK (migration
  0014:20). `atoms.metric_key` already exists as a live FK to `metric_registry`
  (0005:36). **No constraint ties which `kind` may carry a `metric_key`**, so a
  `consume` atom can carry `metric_key='alcohol_standard_drinks'` freely. Seeding
  an alcohol metric is a `metric_registry` **data INSERT**, not a taxonomy
  migration — the 0014 CHECK is never touched. **No one-way door. Confirmed.**
  - Seeding note (data task, not a blocker): each alcohol metric needs a
    `state_class` (`total` per day for both standard-drinks and ethanol-grams),
    a `family` for the RULE-21 FDR tree, and plausible bounds.
- ✅ Mobility-as-derived is the correct design and **requires no `atoms.kind`
  change**, so 0014 stays frozen — the load-bearing part of the ruling holds.
  **Honest caveat:** `derived_measures` is not built yet — it is the Phase-5 table
  behind RULE-04 PENDING (OQ-22). So mobility metrics are *designed-in, not
  buildable now*, which is exactly right for a derived measure and reverses no
  decision. Raw location (`location_fix`, `place_visit`) are already `kind`
  members, so atom-level location capture is representable today; the derived
  layer lands in Phase 5.
- **Verdict: both parts safe to bank. No re-ruling needed.**

**Owed (Track 1.2, gated):** author ADR-0030; add a REQ-ONT requirement (or O-Q
resolution) stating alcohol/caffeine/supplement/medication ride `consume`+registry;
seed the alcohol `metric_registry` rows; note mobility metric_keys as Phase-5
`derived_measures`. Closes Missing-A and the alcohol half of RULED scope; touches
OQ-27 (the `atoms.kind` boundary is a requirements-layer question, Track 1).

### RULED-2 · Finance want-8 — DECIDED: full finance system, one carve-out
**Ruling (Joe).**
- **IN:** income/earnings ingestion; account balances and cash position;
  budgets/targets; range-based forward forecasting; the REQ-FIN-041
  reconciliation-and-balance layer (currently a dangling reference — now to be
  specified).
- **OUT for now:** net worth, investments, portfolio. *Not* a restraint decision —
  just not what was asked; addable later.
- **CONSTRAINT that survives (do not reverse):** **no live running counter of money
  spent or remaining.** The $32–40 over-spend evidence is about precise, always-on
  feedback, and a live budget countdown is exactly that. Budgets and forecasts are
  **retrospective or range-based, never a live number ticking down.** → REQ-FIN-210
  is KEPT as this constraint; REQ-FIN-214 (budget ban) is REVERSED; REQ-FIN-212
  (range-only forward amounts) is KEPT as the range constraint.

**Owed (Track 1.2, gated):** author ADR-0031; write the missing requirement-sets
in Missing-C (income, balances, budgets/targets, range-forecast, reconciliation
layer); reverse REQ-FIN-214; keep REQ-FIN-210/212 as the surviving constraints;
reconcile the new budget/forecast surfaces against the RULE-23/24 restraint rules.

---

## PART 1 — CONFLICTS, ranked by how much of a stated want each removes

### TIER 1 — HIGH: each removes a whole stated want

#### C-1 · RULE-25 "never conclude / phrase-as-a-question" family → removes **want 2 (prescription)**
The reviewer found two members; there are at least six plus the doctrinal root.
All `[verified verbatim]`.

| ID | Contradicts / forecloses | Intent survives rewrite? | Cost |
|---|---|---|---|
| **§0 line 27** — "the system's job is to notice and ask, **not to conclude**" | The governing principle of the whole finance subsystem *is* the reversed RULE-25; cascades to every row below | Yes — reword to "recommend with disclosed uncertainty; never assert as established" | Doc-principle edit; cascades |
| **REQ-FIN-157** — "Every unused-purchase insight SHALL **end in a question**" | The central subscription-cancellation surface — where prescription is most useful — forbidden from recommending | Yes — permit a tiered recommendation as an alternative to the question | Wording + Scenario 7 |
| **REQ-FIN-190** *(known)* — "observation followed by a question, **SHALL NOT be phrased as a conclusion**" | Direct RULE-25 contradiction | Yes | Wording + Scenarios 4/5/7 |
| **REQ-FIN-198** *(known)* — "present it **only as a question**" | Same, scoped to bar-tab prior | Yes | Wording |
| **REQ-FIN-200** — "show the pattern beside those goals **rather than naming the gap itself**" | Forbids stating the discrepancy — the prescriptive move | Yes | Wording |
| **REQ-FIN-222** — "**SHALL NOT name the gap itself**" | Same, as a UI never-rule | Yes — "MAY name the gap with tier + uncertainty; never assert as established" | Wording |
| **REQ-NAR-024** — "SHALL NOT render a … behaviour back to Joe with a **judgment** attached" | Over-broad: a linter will reject RULE-26's own example ("under-slept, lift lighter today"); forecloses narrating *any* recommendation | Yes — pin "judgment" to RULE-23's wordlist, not to recommendation | One clause |

**Do NOT sweep up** REQ-FIN-191/192/247/248 (bans on causal / trait / mood /
mental-health inference from spend) — those are *correct* and survive RULE-25. The
defect is that the six rows above conflate a banned causal/trait assertion with a
now-permitted tiered recommendation, and kill both.

- [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

#### C-2 · RULE-17 reversal, foreclosed *and argued against* → removes **want 1 (general inference)** + **want 3 (finding true things I didn't know)**
RULE-17's SCOPE shell now permits exploratory output displayed behind an
EXPLORATORY label. The spec encodes the opposite everywhere and — uniquely —
rejects the fix in its own ALTERNATIVES CONSIDERED.

| ID | Contradicts / forecloses | Survives rewrite? | Cost |
|---|---|---|---|
| **REQ-INF-402** `[verified verbatim]` — "SHALL NOT include a generator method's output in **any user-facing surface** …" | The exact "never reaches a screen" prohibition RULE-17 reversed | Yes — integrity core preserved by INF-401/403; narrow 402, permit the labelled surface | Low text; must cite RULE-17 binding sequencing |
| **§F ALTERNATIVES line 629** `[verified verbatim]` — "Show PCMCI+ edges behind an 'exploratory' label. **Rejected.** … A label does not undo the false-positive arithmetic once the sentence has been read" | The spec *reasoned against* the design ADR-0029 now mandates — an overturned position, not a stale omission | Yes — rewrite to record the reversal | Doc edit |
| **REQ-INF-403** `[verified verbatim]` — CANDIDATE render → `candidate_leak` violation | Can't distinguish "render as finding" (forbidden) from "render as labelled exploratory" (now allowed) | Yes — fire `candidate_leak` only on a finding surface | Render-violation semantics + Scenario 4 |
| **REQ-TIER-035** — CANDIDATE excluded from every surface | TIER-side echo; fixing INF-402 alone leaves foreclosure intact | Yes — same direction | Wording |
| **Scenario 4** — "must not reach the screen" | Bakes the reversed prohibition into the build | Yes — narrow the "absent from every surface" clause | Test rewrite |

**Binding sequence (RULE-17):** the tier-labelling surface must be built+proven
*before* continuous exploration ships. The rewrite must reference that gate, not
just open the door.

- [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

#### C-3 · Want-8 foreclosure → **want 8 (finance as a full system)** — **SUPERSEDED BY RULED-2**
The spec's title is "FINANCE / **SPEND** SUBSYSTEM"; only transactions, recurring,
and categories were covered. `[verified verbatim — with the REQ-FIN-214 clause
corrected below; the earlier quote dropped its "for any individual category" scope]`

| ID | Foreclosed | Disposition under RULED-2 |
|---|---|---|
| **REQ-FIN-210** — "SHALL NOT display a running count of money spent or remaining" | balances / cash position | **KEPT** as the surviving no-live-counter constraint |
| **REQ-FIN-214** — "SHALL NOT define, store or display a budget target **for any individual category**" | *per-category* budgets/targets specifically | **REVERSED** — budgets now IN (retrospective/range). NOTE: the ban is category-scoped; RULED-2 brings budgets in wholesale, so the reversal is *broader* than the clause it reverses — decide the category-vs-all scope knowingly |
| **REQ-FIN-212** — "SHALL NOT express any forward-looking amount as a single number" | usable forecasting | **KEPT** as the range constraint |
| **§A NON-GOALS** — balances, investment/portfolio, net worth out | net worth | net worth stays **OUT** for now; balances now IN |

Ruled — see RULED-2. Missing sets to write: Missing-C.

- [x] RULED (see RULED-2)

#### C-4 · Want-9 foreclosed at the ontology → **want 9 (alcohol fully instrumented)** — **RESOLVED BY RULED-1**
**REQ-ONT-001** `[verified verbatim: 19 members, zero alcohol/drink/ethanol token
anywhere in the ontology spec]`. No drink member, and no O-Q even flags it, though
O-Qs exist for lower-stakes calls. RULE-07's own worked example is alcohol.
Resolved: `consume` + `metric_key` (RULED-1). No migration.

- [x] RULED (see RULED-1)

#### C-5 · Capture hard-wired to food → removes part of **wants 6, 7, 9** — HIGHEST-LEVERAGE SINGLE FIX
**REQ-CAP-051** `[verified verbatim]` — "output schema SHALL contain, **per food
item, exactly the fields** …". The single extraction path every voice note flows
through is food-shaped; it cannot represent a workout set, a drink, or an activity
— though Joe's own quoted budget says the note carries "feelings and emotions and
food, snacks and plans and **activities**." REQ-CAP-084 already *consumes*
"workouts, locations, mood points" the schema can't produce — a dangling reference
confirming the hole.
- **Forecloses:** want 6 (capture everything), want 7 (workouts), want 9 (drinks).
- **Survives rewrite?** Yes — make CAP-051 the *food-item extraction profile*;
  dispatch to a profile by subject; keep the evidence-span / no-model-number
  contract (RULE-09) on every profile.
- **Cost:** wording + one architectural note. **One fix unblocks four wants** —
  Joe flagged this to sit near the top.

- [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

### TIER 2 — MED: removes a facet of a want, or a testability defect

#### C-6 · Mobility-metric carrier gap (want 10) — **RESOLVED BY RULED-1**
REQ-ONT-001 has raw location (`place_visit`/`location_fix`) but no `kind` for
derived mobility scalars. Resolved: they are `derived_measures`, not atoms — no
new kind (RULED-1).

- [x] RULED (see RULED-1)

#### C-7 · REQ-CAP-106 + no location capture path (want 10) — MED
**REQ-CAP-106** forbids the PWA requesting geolocation (fine under RULE-30), but
**no REQ-CAP opens the sanctioned Shortcut→coordinate path.** Location is stranded
in capture: a closed door with no open one. Additive fix — see Missing-D.
- Survives: yes; the prohibition is fine, the paired positive requirement is missing.
- Cost: additive (a new REQ-CAP; no migration to existing reqs).

- [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

#### C-8 · Spine drift — untestable against schema (OQ-26, extended) — MED-HIGH
`[verified against migration 0005: `lane` is only a constraint *name*; `local_date`
appears nowhere; spine uses `estimate_method`/`state_class` and `subject_day`]`
- **REQ-FIN-001** references `lane` and `atoms.local_date` (OQ-26 already logs this).
- **NEW:** **REQ-FIN-026, -114, -198** also reference `lane`; `lane='hard'` is not a
  spine enum value. Each is untestable against the real schema until reworded.
- Survives: yes — spec/spine drift, not a design conflict.
- Cost: a single sweep — `lane`→`estimate_method`/`provenance`,
  `atoms.local_date`→`subject_day`, reconcile `'hard'` against the enums; + any
  test asserting the old names.

- [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

#### C-9 · REQ-ASK narrowed below "any question" (want 5) — MED
**REQ-ASK-002/004** restrict the answerable space to {registered metric ×
registered operation × date range × grouping}. Correct as a boundary — but an
out-of-registry operation gets a **bare rejection with no disclosure** (the
silence RULE-18 overturned, applied to operations). No graceful "I can't compute
that yet; nearest is X" rung; no routing of a causal ASK question into the §C
confirmation pipeline.
- Survives: yes — keep the closed registry; add an INSUFFICIENT-style disclosure
  rung for out-of-registry shapes, and a causal-routing rung.
- Cost: medium (new REQ-ASK rungs). See Missing-H.

- [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

#### C-10 · REQ-NAR-023 under-enforces RULE-23 (want 4) — MED
**REQ-NAR-023** banned-wordlist is missing the standalone token **"necessary"** —
RULE-23 names "necessary"/"unnecessary" as literal banned labels, and the list has
"unnecessary" but not "necessary". (The reviewer corrected an earlier overstatement
here: "score" is banned by RULE-23 as a *concept* — "a spending or screen-time
score" — handled structurally by RULE-24/NAR, not a missing wordlist token; so the
real gap is the one token "necessary", not two.) "At minimum" saves the list from
being wrong, but omitting a token its parent rule names by hand is weak enforcement.
Guard against banning the neutral money vocabulary RULE-23 now permits.
- Survives: yes. Cost: trivial (add the "necessary" token).

- [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

#### C-11 · REQ-CAP-065 imputes event time (RULE-06) — LOW-MED
**REQ-CAP-065** — on `dateparser` failure, sets event time to `captured_at`, tagged
`provenance='defaulted'`, and REQ-CAP-062 lets `defaulted` into stats. A point
substitution read downstream as real — RULE-06 wants an uncertainty-carrying
interval, or at minimum lane `inferred` (not `defaulted`).
- Survives: yes. Cost: switch the tag (no migration) or store an interval (schema).

- [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

### TIER 3 — LOW / framing (for your eye; no want removed; taken on auditor report)

- **C-12 · REQ-FIN-215** pie-chart ban — spec confesses this is an unmandated
  carry-forward (already OQ-08).  - [x] DEFER 2026-08-24 (Joe)
- **C-13 · REQ-FIN-156/223** running cancellation total — near a RULE-24 streak/score;
  framed as self-efficacy, borderline.  - [x] DEFER 2026-08-24 (Joe)
- **C-14 · REQ-INF-424/427/428/429/430** hard-code the RULE-22 method ban (and add
  GES/FGES/GIMME, not in RULE-22). Fine today; a future ADR revising the list would
  orphan these as build-failing contradictions. Add a "current list, revisable via
  ADR" note.  - [x] ACCEPT 2026-08-24 (Joe)
- **C-15 · REQ-CAP-085** review-list ordered by "interval width" — a nutrition-only key
  undefined for non-food review reasons.  - [x] DEFER 2026-08-24 (Joe)
- **C-16 · REQ-INF (line 748)** "reason over resolved place labels … SHALL NOT include
  a numeric coordinate in any payload/export/log." Egress half matches reworded
  RULE-29 — but "place labels only" may foreclose *coordinate-derived mobility
  metrics* from reasoning. Verify intent (mobility scalars are derived, so probably
  fine, but confirm).  - [x] DEFER 2026-08-24 (Joe)
- **C-17 · Count drift** — 570 grepped vs 564 index (REQ-INF 143 vs 137). Bookkeeping.
  - [x] DEFER 2026-08-24 (Joe)

---

## PART 2 — MISSING requirement-sets the wants imply that nothing covers

Beyond the already-expected **REQ-ACT**, **REQ-CTX/LOC**, **REQ-WKT** (and
index-tracked REQ-BOD/REQ-SLP):

- **Missing-A · Ontology members** — **RESOLVED BY RULED-1.** Alcohol =
  `consume`+registry; mobility = `derived_measures`+registry; no new kind. Owed:
  the REQ-ONT requirement/O-Q resolution + registry seeding + ADR-0030. Also
  unspecified and still open: strength-*set* granularity (one atom per set vs per
  session) for the objective function — flag for a follow-up ruling.
  - [x] RULED (RULED-1); strength-set granularity: - [ ] note: ____

- **Missing-B · Alcohol instrumentation (want 9)** — beyond REQ-CTX: standard-drink
  counting, a **deterministic ABV→ethanol-grams conversion** (`volume × ABV ×
  0.789` — the textbook RULE-09-compliant lookup, currently unspecified while food's
  USDA path is fully specified), and abstinence-day `observed_absent` capture.
  - [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

- **Missing-C · Finance full-system sets (want 8)** — **SCOPED BY RULED-2.** Write:
  income/earnings ingestion (today the only inbound handling nets P2P receipts
  against bar tabs — never income); account balances / cash position; budgets/targets
  (retrospective/range, never a live counter); range-based forward forecasting
  (buildable from existing recurrence data); the **REQ-FIN-041 reconciliation-and-
  balance layer** it currently only names. Net worth / investments **OUT for now**.
  - [x] RULED (RULED-2)

- **Missing-D · Capture generalization (wants 6/7/9)** — a per-subject
  extraction-profile requirement (see C-5); a location capture path
  (`source='shortcut_location'`, see C-7); and a **negative-observation /
  three-valued-presence capture path** — nothing lets Joe capture "logged that I did
  not drink" (RULE-07 `observed_absent` has no capture origin).
  - [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

- **Missing-E · Recommendation machinery (want 2)** — a NAR-side
  recommendation-narration rung (template + numeral binding + linter, mirroring
  REQ-TIER-049's refuse-on-missing-tier) and a recommendation-vocabulary tier: the
  recommendation object exists (TIER-047/048/049) but **has no speech contract**.
  Plus an inference-side trigger ("finding strong enough + achievable delta large
  enough → emit a candidate prescription with a scored prediction"). REQ-ACT covers
  the action side; these two are distinct and also missing.
  - [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

- **Missing-F · EXPLORATORY display path (wants 1/3)** — a requirement defining the
  EXPLORATORY label/tier and its permitted vocabulary, routing continuous-exploration
  output to it, and encoding RULE-17's binding sequencing (surface built+proven
  *before* exploration ships). The six-tier ladder has CANDIDATE = "never shown" and
  no displayable-exploratory rung.
  - [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

- **Missing-G · Continuous / on-demand inference (want 1)** — RULE-19's SCOPE shell
  says exploration is "continuous … may run at any time," but every REQ-INF generator
  run is weekly/monthly batch. No requirement guarantees the on-demand property.
  - [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

- **Missing-H · Ask completeness (want 5)** — a rung for out-of-registry
  operation/question-shape → graceful INSUFFICIENT-style disclosure + nearest
  computable, and a routing rung from a causal ASK question into the confirmation
  pipeline (so a causal answer draws its tier from a `findings` row, not a fresh
  in-answer computation).
  - [x] ACCEPT  - [ ] REJECT  - [ ] DEFER — note: ratified 2026-08-24 (Joe)

---

## Suggested ratification order (Claude's recommendation)

1. **RULED-1 / RULED-2** — already decided; only the ADRs + Track-1.2 writes remain.
2. **C-5 / Missing-D** — one wording fix unblocks four wants; highest leverage.
3. **C-1 (RULE-25 family)** and **C-2 (RULE-17 reversal)** — largest by want-coverage;
   wording/test reversals with no deadline, safe to correct once ratified.
4. **C-8 (spine drift)** — makes several REQ-FIN testable again; mechanical.
5. Everything else at your pace.

*Nothing in this file has been applied. Track 1.2 begins only after you ratify.*
