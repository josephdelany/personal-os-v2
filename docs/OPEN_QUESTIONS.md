# OPEN QUESTIONS

Things that are **not decided**. Claude Code must **ask**, not assume, on
anything in this file. Answering one of these produces either an ADR or an edit
to a requirements file, and the entry is then moved to RESOLVED with a date and
a pointer.

This file is the pressure valve that keeps `CLAUDE.md` and `CONSTITUTION.md`
short. Anything unresolved belongs here rather than accumulating as hedged
prose somewhere else.

Format: **ID · question · why it is open · what depends on it · what would
settle it.**

---

## Architecture and operations

**OQ-01 — RESOLVED 2026-08-23. See RESOLVED section below.**

**OQ-02 — RESOLVED 2026-08-23. See RESOLVED section below.** (name: `personal-os`)

**OQ-03 — RESOLVED 2026-08-23. See RESOLVED section below.** (public; ADR-0013)

**OQ-04 — Which surfaces may run while the language model is unavailable, and
what do they show?**
RULE-15 requires graceful degradation everywhere; the actual fallback copy is
unwritten.

## Capture and nutrition

*Full text at `specs/02-capture-nutrition/requirements.md` §§A–G
"UNRESOLVED QUESTIONS" — 7 questions, A-Q1 through G-Q1.*

What still blocks work (OQ-05 resolved 2026-08-15 — see RESOLVED). This file is
the canonical *index* of what blocks work and its status; the full text of each
question lives in its spec's UNRESOLVED QUESTIONS section, and spec headers point
here rather than restating blocker status of their own.

**OQ-06 — RESOLVED 2026-08-23. See RESOLVED section below.** (04:00 local;
assignment by start instant; sleep attributed to the wake day; `subject_day`
stored explicitly with a `rule_version` so a future change is visible, not silent.)

**D-Q1 (spec §D) — Big Mac: prefer USDA Branded label data or the FNDDS survey
composite?** *Blocks Section D food resolution.* One-line status only; full text
in the spec's D.UNRESOLVED QUESTIONS. Open because REQ-NUT-001 stops at the first
match, so whether a Big Mac even reaches the Branded step depends on whether a
survey composite matches it first — which is the preference nobody has set.
Depends on it: which nutrient numbers the Phase-3 slice resolves against, and so
the `estimate_method` and interval it reports. Settles it: Joe choosing
label-first or survey-first for branded menu items.

## Finance

*Full text at `specs/03-finance/requirements.md` §§A–F.*

**OQ-07 — "Necessary" was narrowed to "used / unused / unknown". Is that
acceptable?**
Why open: Joe asked the system to "see what is necessary and not based on other
data of usage." Necessity is three separable questions and only one — was it
used — is measurable. The requirements now emit `used` / `unused` / `unknown`,
default everything to `unknown`, cap inferred confidence by purchase type (gym
membership 0.90 down to clothing 0.00), and ban the words "necessary" and
"unnecessary" from the schema, the interface and every export.
Why the narrowing: personality-from-spend achieves AUROC 0.55–0.59 — near
chance. A system that cannot infer traits from spend certainly cannot infer
values.
Settles it: Joe accepting the narrowing, or naming what he would accept instead.
**This is the single largest gap between what Joe asked for and what is
specified, and he should be told so plainly rather than discovering it later.**

**OQ-08 — Is the pie-chart prohibition still in force?**
The only clause of the old money doctrine Joe did not explicitly address. It is
currently carried forward, with ranked lists answering "where do I spend the
most" instead.

**OQ-09 — SimpleFIN at $15/yr.**
Recorded as the one considered rule-break, in ALTERNATIVES CONSIDERED only. No
code path requires it and the adapter interface (REQ-FIN-030) makes a future
reversal free. Left open because Joe's $0 rule was stated twice and is treated
as hard until he says otherwise.

## Reasoning and statistics

*Full text at `specs/04-reasoning/requirements.md` §§A–I.*

**OQ-10 — Twelve numeric thresholds are placeholders, not decisions.**
Coverage floor (0.60), `n_eff` floor (20), minimum specifications in a curve
(50), E-value floor (1.5), demotion triggers (3 failures at 0.50; 5 at 0.60),
and six others. None appear in the research. Each is written into its
requirement as a named placeholder and listed locally.
Settles it: a calibration session once six months of real data exists — these
should be set against Joe's actual data density, not guessed now. Until then
they are explicitly provisional and every finding they gate says so.

*Rationale-clause adjectives (appended 2026-08-15).* Two requirements use a
vague adjective inside a *because*-clause — rationale wording, not a threshold
the system gates on. The adjective linter in `tools/validate_layout.py` no
longer flags either (it now scans only the normative SHALL response and skips
`because` clauses). Kept here so the wording is on record as provisional, not
because either is an open decision:

- **REQ-FIN-166 · "robust"** — "visit count is robust to price variance and to
  splitting". Rationale for preferring visit count over dollar amount as the
  alcohol-context metric. To make it a number one would measure the variance of
  visit-count vs dollar-amount under price changes and bill-splitting — but
  there is no gate here to set a threshold on.
- **REQ-INF-521 · "slow"** — "make CI installation slow or fragile", the
  rationale for banning Stan/CmdStanPy/Turing.jl/PyMC. To make it a number one
  would pick a CI install/compile wall-clock budget and measure each toolchain
  against it — again a justification, not a gate.

**OQ-11 — `INSUFFICIENT` has two disclosure modes. Both?**
Partial ("here is what we have, here is what it would take") and absent ("we do
not have enough to answer this"). This is the choice that overturns the old
silence doctrine, and roughly a third of the reasoning requirements are shaped
by it. Joe's instruction reads as endorsing both. Confirm before building.

## Interface

**OQ-12 — Type scale and corner radii.**
The old `11_UI_SYSTEM.md` fixes a palette, a font stack, tabular numerals, a
4 px grid, ≥44 pt targets, and the motion rules — 150 ms, ease-out, opacity and
transform only, nothing celebratory. It does **not** fix a type scale or corner
radii. Those are the actual design gaps, and they are smaller than "no design
system".

**OQ-13 — Which apps' feel would Joe steal?**
Asked before, never answered. Interfaces come last (Phase 7), so this is not
blocking, but the answer is worth capturing whenever it arrives.

**OQ-19 — The archived UI system was lost; ADR-0009's "carry forward" premise is void.**
Why open: the 42 archived screens, the old `11_UI_SYSTEM.md` (palette, font stack,
tabular numerals, 4 px grid, ≥44 pt targets, motion rules), the honesty grammar
and design tokens were all in the cloud workspace that was lost (same loss as the
19 spec files, see ROADMAP Phase 0). ADR-0009 (awaiting authorship) was to
"carry forward" the design tokens and honesty grammar *from that archive* — there
is nothing to carry forward. Surfaced 2026-08-23 while cleaning stale `archive/`
references (ADR none; ruling scoped to Gate 0).
Depends on it: Phase 7 (interfaces) and ADR-0009. What survives is only what is
written into the live constitution (RULE-14, RULE-24 motion/anti-gamification
constraints) and OQ-12's partial notes; the type scale, corner radii, palette,
and honesty-grammar vocabulary must be **re-derived, not recovered**.
Settles it: Joe deciding, at Phase 7, whether to re-derive the design system from
scratch or adopt a new reference; and re-scoping ADR-0009 accordingly.

---

## Spine (Phase 2)

**OQ-21 — RESOLVED 2026-08-23 (ADR-0022).** Ruling (Joe): a behavioural test MAY
create a disposable schema (never `core`, never `public`), INSERT fixture rows,
assert, and roll back the whole transaction — nothing commits, no row is read as
data. This is option (a) of the settle list, written as a **clarification** to
RULE-01 (not a weakening; nothing persists) in `docs/CONSTITUTION.md` and
`CLAUDE.md`. The INSERT-path constraints (value/presence/lane CHECKs,
`force_recorded_at` override, predictions XOR, prereg-freeze happy path) are now
proven behaviourally in `tests/test_spine_insert_paths.py`, including the
legitimate `observed_absent` row and the valid-interval-only nutrition estimate.
Pointer: ADR-0022. Original question retained below.

**OQ-21 (original) — How is an INSERT-path constraint tested behaviourally under
RULE-01's absolute no-fabrication?**
Why open: the Phase-2 spine's INSERT-path guarantees — the `force_recorded_at`
trigger overriding a client-supplied `recorded_at`, the atoms value/presence/lane
CHECKs, the `predictions` binary/continuous XOR, the `hypothesis_register` freeze
trigger's *legitimate* status-only-UPDATE path — can only be proven by executing an
INSERT and observing acceptance/rejection. RULE-01 forbids "placeholder, synthetic,
sample, or example rows in any table, in any environment, for any reason including
testing," and says fixtures "never touch a real table." So these are currently
verified **structurally only** (constraint/trigger definitions present via
catalog), never behaviourally. The append-only *rejection* path is proven (no row
needed — privilege/trigger fires on an empty table); the *acceptance and coercion*
paths are not. Depends on it: whether the shape-lock work is actually trustworthy
or merely present. Settles it: Joe ruling one of — (a) a narrow RULE-01 clarification
that a rolled-back INSERT into a throwaway schema, never committed and never read as
data, is a permitted constraint probe; (b) fixture tables in `tests/fixtures/` that
mirror the shape and carry the same constraints (duplication risk — the fixture can
drift from the real DDL); or (c) accept structural-only verification for INSERT-path
and document it as a standing limitation. Raised by the session-end reviewer,
2026-08-23.

**OQ-22 — RESOLVED 2026-08-23 (Phase-2 session 4 ruling).** Ruling (Joe): **option (a)**.
Gate 2 is satisfied for Phase 2 with **RULE-04 explicitly DEFERRED to Phase 5, named on
the gate, not passed silently** — its query joins `derived_measures`, which does not exist
until Phase 5, so it cannot run this phase. No minimal shell is pulled forward (option (b)
rejected). Done: ROADMAP Phase 2 body + Gate 2 amended to state the deferral, and
**RULE-04's activation is added to Gate 5** so it cannot be forgotten (Gate 5 now requires
the deferred RULE-04 query to run against `derived_measures` and return zero rows).
`tools/check_invariants.py` already prints RULE-04 PENDING with this reason. Original
question retained below.

**OQ-22 (original) — Gate 2 requires RULE-04 "written and running," but RULE-04's query needs
`derived_measures`, which is Phase 5.**
Why open: ROADMAP Gate 2 says "Every CI invariant query written and running,
including RULE-04 point-in-time correctness," and RULE-04 is Tier SQL. But RULE-04's
query joins `derived_measures` (a Phase-5 derived-compute table) to `atoms`, and the
spine scope Joe set this session explicitly excludes derived compute. So RULE-04 is
*written* (in `tools/check_invariants.py`) but prints PENDING and cannot run — the
single query that "proves bitemporality actually works rather than merely existing
in the schema" is not exercised at all this phase. Depends on it: whether Gate 2 can
be declared passed with RULE-04 pending, or whether the gate wording is wrong.
Settles it: Joe ruling either (a) Gate 2 is satisfied for Phase 2 with RULE-04
explicitly deferred to whenever `derived_measures` lands (Phase 5), the deferral
recorded on the gate; or (b) a minimal `derived_measures` shell is pulled forward so
RULE-04 can run against empty tables now. Raised by the session-end reviewer,
2026-08-23.

**OQ-23 — RESOLVED 2026-08-23 (ADR-0023, migration 0014, REQ-ONT).** Ruling (Joe):
write the REQ-ONT requirements now with the taxonomy **derived** from the 34
archived tables + cited specs, and add the enforcing CHECK over the empty tables in
the same session. Done: `specs/05-ontology/requirements.md` (REQ-ONT-001..014),
migration `0014_ontology_checks.sql` closes `atoms.kind` to 19 members and
`entities.entity_type` to 6 via CHECK (not native ENUM — the set grows; CHECK is a
cheap forward migration). `kind` is coarse; the specific measure stays in
`metric_key` (registry). The seven guesses are recorded in ADR-0023. Original
question retained below.

**OQ-23 (original) — The closed taxonomies for `atoms.kind` and `entities.entity_type`
are unwritten, so both ship as open TEXT.**
Why open: ADR-0002 specifies a closed 20-member `kind` enum; ADR-0004's `entity_type`
similarly wants a closed set. Both taxonomies lived in the lost ontology spec (OQ-16)
and were **not re-invented** this session (that would be fabricating a spec). So both
columns are `NOT NULL TEXT` with no CHECK — a typo or an out-of-taxonomy value is
accepted. The append-only tables mean adding the CHECK later is a forward migration
that must pass over historical rows. Depends on it: whether extraction (Phase 3) can
begin writing `kind`/`entity_type` values before the taxonomy is fixed (risking
inconsistent values that a later CHECK would reject). Settles it: Joe authoring or
ruling the `kind` and `entity_type` taxonomies (part of the unwritten ontology spec,
OQ-16), after which a forward migration adds the CHECK/enum. Raised 2026-08-23.

**OQ-24 — RESOLVED 2026-08-23.** Ruling (Joe): the guard self-edit was authorised
explicitly this session (the auto-mode classifier had correctly refused it last
session). Done: `.claude/hooks/guard-destructive.sh:13` regex is now
`(public\.|core\.)?`, and `tools/test_guard.sh` blocks `UPDATE core.atoms` and
`delete from core.raw_captures` (26/0). **Known residual, honestly bounded (per the
OQ-15 stance that a shell regex cannot be exhaustive):** the regex still misses
`UPDATE ONLY core.atoms` and quoted-identifier forms (`"core"."atoms"`); the
DB-level `reject_mutation()` trigger catches all of these, so enforcement is intact
and this is dev-time defence-in-depth only. Not chasing regex completeness would
give false assurance (OQ-15). Original question retained below.

**OQ-24 (original) — The guard hook's append-only regex matches `public.` but not
`core.` schema-qualified table names.**
Why open: `.claude/hooks/guard-destructive.sh` blocks `UPDATE/DELETE … (public\.)?
(atoms|raw_captures|entities|links|findings)`, but the new spine lives in `core`, so
`UPDATE core.atoms …` is **not** blocked by the dev-time guard. The DB-level
append-only trigger still catches it (so enforcement is intact), but the guard —
which exists to stop the mistake before it reaches the DB — has a gap. Claude Code is
blocked from editing its own guard config (auto-mode classifier denied the edit this
session), so this must be applied by Joe. Depends on it: dev-time defence-in-depth
only; DB enforcement is unaffected. Settles it: Joe adding `core\.` to the regex on
line 13 of the guard hook (`(public\.|core\.)?`) and adding a `core.atoms` case to
`tools/test_guard.sh`. Raised 2026-08-23.

**OQ-25 — Bitemporal column names diverge between the spine and the Phase-6
reasoning requirements.**
Why open: REQ-INF-104/105 reference an observations store filtered on `ingested_at`,
and REQ-INF-114 requires `source_rev` + a flipped `is_current`. The spine instead
uses `recorded_at` + `supersedes` with currency derived via `*_current` views. These
are plausibly the same concepts under different names, but nothing maps
`ingested_at → recorded_at` or explains the absence of `source_rev`/`is_current`, and
REQ-INF-114's "flip is_current" is a *different* mechanism (an in-place UPDATE, which
INV-2 would forbid) from derive-from-supersedes. Depends on it: whether the Phase-6
confirmation job (REQ-INF-104/105) can be implemented against the spine as built, or
whether a reconciliation ADR is needed first. Settles it: an ADR mapping the
reasoning-spec bitemporal vocabulary onto the spine's, written before Phase 6.
Raised by the session-end reviewer, 2026-08-23.

**OQ-26 — RESOLVED 2026-08-24 (Track 1.2, C-8).** The finance-spec column drift is
reconciled: REQ-FIN-001 (`lane`→`estimate_method`+`state_class`, `atoms.local_date`→
`subject_day`, `source` dropped as redundant with the `NOT NULL raw_capture_id`
lineage), REQ-FIN-026/198 (`lane='inferred'`→`provenance='inferred'`), REQ-FIN-114
(inferred case → `provenance='inferred'`; the *human-override* case spun out to OQ-32).
Verified against migration 0005 by the C-8 reviewer; `validate_layout` green. One
residual it surfaced — the authoritative-human-override representation — is **OQ-32**,
not this drift. Original question retained below.
Why open: REQ-FIN-001 (specs/03-finance/requirements.md:31) says a transaction atom
carries `lane` and is queryable on `atoms.local_date`, but the built spine renamed
these — the value's lane is `estimate_method` (+ `state_class`) and the day axis is
`subject_day` (ADR-0019). This is the same spec/spine drift as OQ-25 but in the
finance spec, and it predates this session (surfaced while deriving REQ-ONT). Depends
on it: whether Phase-3 finance ingest can be written against the spine as built, or
whether REQ-FIN needs a column-name reconciliation first. Settles it: an edit to the
affected REQ-FIN statements (or a mapping ADR) aligning `lane`→`estimate_method` and
`local_date`→`subject_day` before finance ingest is built. Raised 2026-08-23.

**OQ-32 — How does the spine represent an authoritative *direct human override* of a
usage status, distinct from a value extracted from a capture?**
Why open: C-8 reconciled REQ-FIN-114's `lane='inferred'`/`lane='hard'` to the spine
vocabulary. The inferred case maps cleanly to `provenance='inferred'`. But the spine's
`provenance` enum {`extracted`,`inferred`,`defaulted`} (migration 0005) has no value
that distinguishes a **Joe-directly-set authoritative override** (old `lane='hard'`)
from an ordinary content-extraction — and `confidence=1.0` alone is a weak
discriminator (a template parser could also assign 1.0). RULE-10 ("a human correction
outranks every automated layer, permanently") needs this distinction to be durable, not
a confidence coincidence. Depends on it: whether REQ-FIN-114/115's human-override
guarantee is enforceable against the schema, and whether Phase-3 usage-status rows need
a dedicated marker. Settles it: Joe ruling one of — (a) override = `provenance='extracted'`
+ `confidence=1.0` + supersedes-lineage, with a test proving no automated process can
re-guess it (RULE-10); (b) a dedicated `source='human_override'` / `set_by_human` marker
(a Phase-3 schema decision); or (c) the correction is always a *superseding* row and
authority is read from the supersedes graph, never from a column. Raised by the C-8
session reviewer, 2026-08-24.

**OQ-27 — Three `atoms.kind`/`entity_type` boundary calls are guesses, not rulings.**
Why open: ADR-0023 and REQ-ONT (`specs/05-ontology/requirements.md` §UNRESOLVED,
O-Q1/2/3) record three membership boundaries decided by derivation, not by Joe:
`mood` vs `self_report`; `media_play` vs `screen_session` and the `heart_rate_variability`
split from `vital_sample`; and whether `entity_type` needs `brand`/`product` as a 7th
type. The taxonomy is enforced (migration 0014), so a change is now a forward migration,
not a free edit. Depends on it: whether Phase-3 extraction emits kinds that match Joe's
mental model. Settles it: Joe ruling each boundary once real extraction exercises it, or
accepting the derived defaults. Not blocking. Raised 2026-08-23.

**→ Remediation:** `docs/REMEDIATION_PLAN.md` **Track 1** (requirements audit +
correction) — the `atoms.kind`/`entity_type` boundary guesses are revisited there.
*Note (session 11): the plan text does not name OQ-27 explicitly; the mapping to
Track 1 was Claude's and **Joe confirmed it 2026-08-24** — the `atoms.kind` /
`entity_type` boundary is a requirements-layer question, so Track 1 is its home.*

**OQ-28 — RESOLVED 2026-08-23 (Phase-2 session 4).** Consent granted (Joe). Corrected on
the live DB: the two pre-fix `ops.runs` smoke rows are marked `trigger=manual_smoke` with a
note (they stay `now()`-stamped — labelled, not re-run, so they are never mistaken for a
scheduled firing); `ops.job_registry.keepalive_github` moved to the daily design
(`schedule='17 6 * * *'`, `max_staleness_hours=1200`, daily-design description). Both
registry rows now read `'17 6 * * *'`. This was an UPDATE against committed operational
rows (`ops.*`, not `atoms`/`raw_captures`, so INV-2 does not apply); only `<safety>` gated
it, and Joe authorised it explicitly. Original question retained below.

**OQ-28 (original) — Three committed operational rows are pre-fix and describe the abandoned
monthly keepalive; correcting them needs a Joe-consented UPDATE.**
Why open: session-4 committed two `ops.runs` smoke rows and one `ops.job_registry` row
(`keepalive_github`) with the *pre-fix* design — the `ops.runs` rows are `now()`-stamped
(`started_at == finished_at`, no `trigger` key), and the registry row still says
`schedule = '0 6 1 * *'` (monthly), `max_staleness_hours = 1440` (60 days), from the design
reviewer-finding B1 removed. The code, tests, workflow, spec, ADR-0024 and DECISIONS.md all
now describe the correct **daily** design, so these three rows are the only place the wrong
design still lives — and they are operationally misleading (a reader querying `ops.runs`
cannot tell a smoke row from a scheduled firing; the registry advertises a schedule the
workflow does not run). Fixing them is an UPDATE against committed rows, which CLAUDE.md
`<safety>` requires Joe to authorise first — the auto-mode classifier correctly blocked it
this session. Depends on it: whether Gate-0 evidence and the job registry read truthfully
before the first scheduled firing. Settles it: Joe authorising the UPDATE (mark the two
`ops.runs` rows `trigger=manual_smoke`/pre-fix; set `keepalive_github` schedule
`'17 6 * * *'`, staleness `1200`, daily-design description), or ruling the rows be left as
a documented pre-fix artifact. `ops.runs`/`ops.job_registry` are operational tables (not
`atoms`/`raw_captures`), so INV-2 does not forbid the UPDATE; only the safety rule gates it.
Raised by the session-end reviewer, 2026-08-23.

**OQ-29 — When does the legacy Parquet backfill actually load into `core.atoms`?**
Ruling (Joe, 2026-08-23, ADR-0028): **option (c)** — legacy history is
Parquet-authoritative and **nothing is loaded into Postgres now**. `core.atoms`
stays 0; Gate 2 is satisfied by the proven, DB-verified reconciliation (Δ=0), not by
rows-in-Postgres. The loader (`tools/backfill_run.py`, DB-verified this session:
309,826 atoms into a rolled-back copy, all constraints/invariants pass) stands by.
**What is still open:** which specific load, and when. **The condition, stated
plainly:** the loader runs when a **named Phase-5/6 analysis actually needs a
specific legacy stream in Postgres** — not speculatively, not wholesale. At that
time: (1) the old cron stack must be **frozen and its ~174 MB (`public.intraday`
94 + `signals` 46 + `events` 34) reclaimed** (OQ-17), so the same history is not
double-stored; (2) the load is **sized against the 500 MB ceiling as it stands
then** (OQ-20) and scoped to the stream(s) the analysis names; (3) anything not
explicitly loaded stays Parquet-authoritative; (4) **two loader defects the
session-end reviewer found must be fixed first** (ADR-0028 addendum): sleep
`subject_day` is computed per stage-segment, splitting a night that straddles 04:00
across two days — the "by wake day" rule needs per-night sessionization, not
per-segment; and `evidence_span` names dedup-secondary `health__*` tables that have
no A′ capture row — either capture every contributing source or stop naming
capture-less ones. Also owed: the dead `txn_amount` registry row and the
hardcoded excluded-bucket constants in `backfill_run.py`. Depends on it: whether Phase-5/6
`derived_measures`/hypotheses read history from `core.atoms` or from
DuckDB-over-Parquet (ADR-0016). Settles it: the first Phase-5/6 analysis that names
a legacy stream, at which point the load target + size are decided against the
then-current ceiling. Raised 2026-08-23 (ADR-0028).

**→ Remediation:** `docs/REMEDIATION_PLAN.md` **Track 3.2/3.3** — the legacy-load
trigger/sizing (3.2) and the three loader defects owed before any load (3.3:
per-night `subject_day` sessionisation, `evidence_span` capture-row gap, dead
`txn_amount` row + hardcoded bucket constants).
**Two more loader defects, found by the ADR-0035 reviewer (2026-09-01), owed before
any load:** (a) `backfill_run.py` seeds the check-in metrics (`energy`/`restored`/
`drive`) on a **1–5 scale — wrong**: the deployed `ingest-checkin` Edge Function
validates `0 <= v <= 10` (source read directly) and the shortcut prompts read
"(0-10)"; the loader's registry tuples and unclamped coarsening must be corrected to
0–10 before it ever runs. (b) The loader must **exclude the `checkins` stream
entirely** — the live mirror (migration 0020 / ADR-0035) now owns check-in ingest
under `checkin_<type>_<field>` keys, and a second load under bare `energy`-style
keys would double-count the same real measurements in any family aggregate.

**OQ-30 — RESOLVED 2026-09-02 (ADR-0052; migrations 0047-0048; session 20, B10).** Joe's ruling, via the advisor, is recorded verbatim in ADR-0052 and numbered as REQ-ACT-001..012 in `specs/09-action/requirements.md`: (1) tier-gated language, option (c), with a floor of PROMOTED for anything pattern-based; (2) Joe's own standing orders are a separate DESCRIPTIVE channel, because applying his rule to his numbers is not an inference; (3) the proactive channel is one read-only instruction per subject day on ASSESSMENT and is not a push, so it does not consume RULE-27's daily prompt; (4) demotion when the backing finding falls or two consecutive forward predictions score false (a placeholder, OQ-10); (5) a daily digest of one, with the full list on demand. **Still open and carried into `specs/09-action` A-Q3:** the REQ-FIN-190/198 reconciliation, so no finance surface recommends until B17 settles it. Original text kept below.

*Was:* **OQ-30 — What evidence-tier floor governs a REQ-ACT recommendation, and how does a
proactive recommendation fit RULE-27's cadence?**
Ruling context (Joe, 2026-08-23, ADR-0029): RULE-25 was reworded so the system MAY
recommend below `CONFIRMED_OBSERVATIONAL` with disclosed uncertainty, and REQ-ACT
authoring is opened (REQUIREMENTS_INDEX "Not yet written"). The audit confirmed **no**
existing requirement authorises prescription — REQ-ASK is descriptive, REQ-NAR is
narration restraint. **What is still undecided before REQ-ACT can be numbered:**
(1) the **evidence-tier floor** — three options in `CONSTITUTION_RESTRUCTURE_PROPOSAL.md`
§4.2: (a) recommend from `DESCRIPTIVE` with mandatory uncertainty (maximally useful,
maximally risky); (b) from `PROMOTED` upward only (safer, quieter); (c) tier-gated
*language* — hedged verbs below `CONFIRMED`, direct verbs at/above it (the drafted
recommendation, mapping the REQ-NAR-020 per-tier vocabulary linter onto actions);
(2) whether a **proactive** recommendation counts against RULE-27's single daily
prompt or is a separate channel; (3) the **demotion thresholds** for a recommendation
whose scored forward prediction (RULE-20) fails — these join OQ-10's placeholder-threshold
set, to be set against real data, not guessed; (4) whether Joe wants a daily
"what to do today" digest surface or only on-demand (REQ-ASK-style).
**Reconciliation the session-end reviewer surfaced (must be done before REQ-ACT is
numbered):** the recommendation *disclosure contract* already exists — REQ-TIER-047
forbids a recommendation phrased as a causal-effect claim below `CONFIRMED_OBSERVATIONAL`;
REQ-TIER-048 permits a decision-under-uncertainty recommendation below CONFIRMED provided
it carries tier, effect size + interval, `n`, `coverage`, and what-would-change-it;
REQ-TIER-049 fails the build if one renders without its tier + interval. So the tier floor
(1) is **partially pre-answered** (below CONFIRMED, with disclosure), and REQ-ACT covers
only the *generation* machinery those requirements do not — when/how-often/what-happens-when-wrong/
the action vocabulary. Separately, new RULE-25 ("MAY recommend") is in tension with
**unamended REQ-FIN-190 / REQ-FIN-198**, which still require a co-occurrence be phrased as
a question, never a conclusion; those two need reconciling (edit to align with RULE-25, or
an ADR) before finance surfaces recommend.
Depends on it: whether REQ-ACT requirements can be written, and how aggressively the
system is allowed to prescribe. Also gated on the tier-labelling surface (RULE-17
binding sequencing) being built and proven first. Settles it: Joe ruling the residual tier
floor (what REQ-TIER-047/048 leave open) and the cadence question (2), and the
REQ-FIN-190/198 reconciliation; (3)/(4) can follow. Raised 2026-08-23 (ADR-0029);
extended by the session-end reviewer 2026-08-23.

---

## Data integrity

**OQ-16 — `ops/features.json` cites requirement IDs that exist in no spec, and
the layout gate does not catch it.**
Why open: features F-006, F-014 and F-015 cite ids under the `REQ-ONT` and
`REQ-NFR` prefixes (the ontology and non-functional specs). Those prefixes appear
in no spec file (the prefix census is REQ-ASK/CAP/FIN/INF/NAR/NUT/TIER). The
subsystem specs are known-unwritten (PROGRESS 2026-08-08), so the ids are forward
references to specs that do not yet exist. `validate_layout.py` cross-checks
requirement ids cited in *governing docs* against the specs, but does **not**
cross-check `features.json`, so this passes silently. (This entry deliberately
names only the prefixes, not the full ids, because writing a full undefined id
into this governing doc would itself fail the section-8 cross-reference check —
which is exactly the asymmetry in question.) Surfaced by the reviewer,
2026-08-23; predates this session.
Depends on it: whether a feature can name a requirement before that requirement
is written, and whether the ledger↔spec link should be gated. Settles it: Joe
ruling either (a) forward references are fine until the spec is authored, and the
gate stays as-is, or (b) the gate must fail when `features.json` names an id no
spec defines — in which case those three features need their specs written or
their ids corrected. No entry may be edited to describe what was built (features.json
`_comment`), so option (b) means writing the specs, not renaming the features.
**Partial progress 2026-08-23 (REQ-ONT half):** `REQ-ONT-001` now exists
(`specs/05-ontology/requirements.md`, ADR-0023), so F-006's citation is no longer
dangling. **Further progress 2026-08-23 (REQ-NFR half, session 4):** `specs/06-nfr/requirements.md`
now defines `REQ-NFR-001..004` (ADR-0024), so F-014's `REQ-NFR-001` and F-015's
`REQ-NFR-002` citations are **no longer dangling** — every prefix cited by
`features.json` now resolves to a spec. **Still open (the actual gate question):**
should `validate_layout.py` be extended to cross-check `features.json` requirement ids
against the specs, so a future dangling citation fails the build rather than passing
silently? That is still Joe's to rule. `features.json` is write-locked to the agent
(ADR-0011); F-006/F-014/F-015 are not flipped here (they need their proving tests /
scheduled firings, not just a resolvable citation).
**Progress 2026-09-02 (session 17, B0):** `tools/update_features.py` now exists — the
ADR-0011 sanctioned writer. It flips an entry on a *requirement-ID match* between the
entry and a passing test name, which surfaces a second, narrower defect in the ledger:
**F-006's description ("Bitemporal atoms table, append-only") does not describe the
requirement it cites.** `REQ-ONT-001` is the closed `atoms.kind` taxonomy (19 members),
and the test that proves it (`test_REQ_ONT_001_kind_taxonomy_enforced`) proves the
taxonomy, not append-only-ness. Append-only is proven by `test_RULE_02_*`, which names
a RULE, not a REQ, so no ledger entry can cite it. The runner will flip F-006 on the
letter of the ledger's own rule (named test containing the requirement ID); whether
that is the intended meaning is Joe's to rule. Options: (a) accept — the entry's
`requirement` field is the contract, the description is prose; (b) add a REQ ID for
append-only in `specs/05-ontology` and rename the RULE-02 tests to carry it, then let a
future ledger entry cite it. No entry was edited (the `_comment` forbids it).
The reviewer (session 17) added three more ledger-matching facts Joe should know, all
inherited from B0's rule "a named test containing the requirement ID", none a script bug:
(i) **F-001 and F-013 both cite `REQ-CAP-003`**, so the first passing test naming it
flips both — the Big Mac end-to-end slice (F-013) would be marked green by a single
Shortcut-write unit test. (ii) The match is over `classname::name`, so a token in a test
*file name* counts, and a negative test (`test_documents_that_REQ_X_is_NOT_covered`)
counts. (iii) Lowercase `req_x_001` never matches — silently. Settling (i) means either a
second REQ ID for the slice or accepting that F-013's contract is REQ-CAP-003 as written;
(ii)/(iii) are conventions to hold in review, not code to add. **Also a ruling owed:**
should `validate_layout.py` refuse when two ledger entries share a `requirement`?


**OQ-17 — The previous build is still live and writing to the database v2 is
rebuilding. Coexist, migrate, or tear down?**
Why open: the live DB has 8 active `pg_cron` jobs (health_staleness_check,
brief_readiness_tick, day-narrative-tick, enumerate_insights,
generate_betterment_plan, refresh_metric_catalog, run_coaches, log_forecast), all
succeeding as of 2026-08-23, writing tables v2 will own (events, signals,
insights, metric_catalog, …). Discovered this session while checking for an
existing keepalive. Nothing in any doc says whether v2 runs alongside the old
system, migrates off it, or tears it down first. Two direct consequences already
realised: (a) the Phase-0 Parquet archive is a point-in-time snapshot of a
*mutating* source, already stale for the busy tables; (b) Phase 2's "spine, in
code" partially already exists as this old stack.
Depends on it: whether Phase-2 migrations target an empty schema or must
coexist with live writers; whether the archive must be re-taken at a quiesced
moment; the meaning of "backfill" in Gate 2.
Settles it: Joe deciding the disposition of the old cron stack (freeze / migrate
/ drop) and whether the archive needs a quiesced re-run.
**Ruling (Joe, 2026-08-23).** The old cron stack keeps running — it is still the
only working system and still collecting wanted data. The Parquet archive is
accepted as explicitly point-in-time; no quiesced re-run is required. Phase 2
creates *new* tables and does not touch the old ones, so the moving target is not
a blocker for the spine. **Freeze is deferred to Phase 3, conditional on the new
capture path demonstrably replacing the old one — specific acceptance test: the
new path ingests one real day end to end before anything is switched off.** Until
that test passes, nothing in the old stack is disabled. (Recorded in ROADMAP
Phase 3.)

**→ Remediation:** `docs/REMEDIATION_PLAN.md` **Track 3.2** (storage ceiling) —
retiring the old stack at Phase 3 reclaims ~174 MB; step not yet executed.

**OQ-18 — There is no workout/strength history anywhere, yet strength is the
system's stated objective function.**
Why open: `public.workouts` is 0 rows live, and the July backup CSV was empty —
so no workout data exists in either source. ROADMAP Phase 6 names strength and
body composition as the objective function, and the previous hypothesis library
was faulted for near-zero coverage of e1RM/sets/RPE/lean mass. If workouts are
never captured, the whole objective is unmeasurable.
Depends on it: whether a capture path for workouts must exist before Phase 5/6
derived measures and hypotheses are meaningful.
Settles it: Joe confirming whether strength is being logged at all (and where),
or accepting that workout capture is net-new work the roadmap must schedule.
**Ruling direction (Joe, 2026-08-23).** Accepted as net-new work the roadmap must
schedule: **manual, ugly, interim workout capture starts THIS WEEK** to start the
clock (every week without it is a week Phase 6 cannot have), to be replaced by a
real ingest path in Phase 3/4. The interim capture recommendation is recorded in
`ops/PROGRESS.md` (this session) and the Phase-4 feed remains owed. Still open:
which specific interim tool Joe adopts, and the Phase-4 workout-feed design.

**OQ-20 — Postgres Free is 500 MB; what happens when it fills, given atoms are
append-only?**
Why open: Decision 7 (`docs/PHASE2_MIGRATION_PLAN.md`) makes **Postgres the
authoritative store** and R2/Parquet the analytical mirror. Supabase Free caps the
database at **500 MB and flips it read-only at the limit** (verified this session;
live DB is ~197–222 MB before the new schema exists — already ~40% gone). RULE-02
makes `atoms` and `raw_captures` **append-only**, so "delete old rows" is not an
available remedy — the usual escape hatch is closed by our own constitution.
Depends on it: whether the spine needs a cold-storage/eviction design (move
sealed, superseded, or old-`recorded_at` rows to R2 Parquet and keep only a
pointer in Postgres) from day one, or whether N=1 volumes stay under 500 MB for
years and this is a Phase-8 concern. The busy legacy tables (`intraday` 94 MB,
`signals` 46 MB, `events` 34 MB) show the old stack alone would blow the ceiling —
but those are the *old* system's tables, not the new spine's.
Settles it: a written options memo (evict-to-R2 vs archive-and-truncate-legacy vs
accept-and-monitor with a storage alert on `ops.runs`) with the row/byte
projection for the new schema, ruled by Joe **before** the wall, not at it.
Raised by Joe's Decision-7 ruling, 2026-08-23.

**OQ-31 — The requirements audit (session 12) is ranked but not ratified; two rulings owe ADRs.**
Why open: `docs/REQUIREMENTS_AUDIT.md` holds ~17 conflicts over ~30 REQ IDs + 8 missing
requirement-sets from the item-3 audit. Nothing is applied — Track 1.2 (correction) is gated on
Joe reading the worksheet and marking each item ACCEPT/REJECT/DEFER. Two items were ruled early
because they alone have a hardening deadline: **RULED-1** (ontology — alcohol=`consume`+metric_key,
mobility=`derived_measures`; spine-verified, no migration; reserved **ADR-0030**) and **RULED-2**
(finance = full system with net-worth/investments carved out, no live spend counter; reserved
**ADR-0031**). Those two ADRs are OWED and unauthored. One sub-item is newly open and unresolved by
either ruling: **strength-*set* granularity** — is a strength set (exercise/weight/reps/RPE) one
`workout` atom per set or one per session? The objective function (want 7) rides on it, and it is a
requirements-layer question REQ-ONT is silent on (no O-Q, unlike the mood/media/brand boundaries).
Depends on it: whether Phase-3 extraction and Phase-5/6 derived measures for e1RM/volume read a
consistent set-level shape. Settles it: Joe ratifying the worksheet (→ Track 1.2 corrections +
ADR-0030/0031 authored), and ruling the set-granularity boundary. Raised 2026-08-24 (session 12).

**OQ-33 — What atom-shape stores one strength set's four attributes (exercise, load, reps, RPE)?**
Why open: ADR-0030 ruled strength granularity is **per set** (not per session), and REQ-ONT-017
fixes that granularity. But an `atoms` row carries a *single* `value_point` (migration 0005), so one
set's four attributes cannot live in one atom's value. Two representations fit the built model without
a new `kind`: (a) **one `workout` atom per attribute** (`metric_key` ∈ {`strength_load_kg`,
`strength_reps`, `strength_rpe`}, the exercise as a linked entity), all sharing a set key /
`occurred_at`; or (b) a **single `workout` atom per set with a structured `value_type`** (a composite),
which strains the single-`value_point` shape and the `atoms_value_has_lane` interval model. ADR-0030's
prose "one atom per set carrying exercise, load, reps, RPE" reads as (b) but is not directly
expressible; (a) is expressible today. Depends on it: how Phase-3/4 workout capture (REQ-WKT) writes
sets, and whether e1RM/volume derive from per-attribute atoms or a composite. Settles it: Joe ruling
(a) per-attribute atoms sharing a set key, or (b) a composite value_type (with the schema change that
implies), when REQ-WKT is authored. Not blocking the granularity ruling. Raised by the Missing-A
authoring, 2026-08-24.

**OQ-34 — What fires the confirmation job? Its trigger (schedule vs event) is unspecified.**
Why open: the confirmation pipeline is fully specified on *what it reads* — REQ-INF-104 evaluates a
registered hypothesis using only observations whose `subject_day` and `ingested_at` are at or after
`confirmation_data_from` — but no requirement states *what fires* it: a nightly/weekly schedule, an event
(a hypothesis's window elapsing, new data landing), or an on-demand call. Missing-G (REQ-INF-412/413) added
an on-demand *exploration* trigger and explicitly excluded the confirmation job from it, which sharpened
the gap: exploration now has a named trigger and confirmation does not. **Integrity is not at risk either
way** — REQ-INF-104's data filter holds regardless of what fires the job, so a confirmation can never read
pre-registration data no matter the trigger; this is why it is an open question, not a defect. But an
unstated trigger is the kind of silence that becomes an assumption at Phase 6, when the confirmation job is
actually built, and it interacts with REQ-INF-107 (a registered-but-immature hypothesis at
`window_too_short` — re-checked on a cadence, or on window-elapse?). Depends on it: how Phase 6 schedules
and re-checks confirmation. Settles it: Joe (at or before Phase 6) ruling the confirmation-job trigger —
scheduled, event-driven on window-elapse, on-demand, or a combination — recorded as a REQ-INF requirement
or an ADR. Raised 2026-08-27 (session 14), flagged by the Missing-G reviewer.

**OQ-35 — Which standard-drink definition (grams of ethanol per standard drink) does the system use?**
Why open: REQ-NUT-068 derives `alcohol_standard_drinks = ethanol_grams / g_per_standard_drink`, but the
divisor is a jurisdiction convention, not physics: US NIAAA = 14 g, WHO = 10 g, UK = 8 g. The same logged
pint of 5% beer (≈568 mL → ≈22.4 g ethanol) reads as 1.6, 2.24, or 2.8 standard drinks depending on the
choice — a ~1.75× spread that propagates into every alcohol metric, trend, and finding. REQ-NUT-068 carries
**14 g (US NIAAA) as a named provisional placeholder**, flagged not silently fixed, the OQ-10 placeholder
posture. Depends on it: every standard-drink number the system stores or renders. Not blocking:
`alcohol_ethanol_grams` — the physically-grounded measure — is fully computable without this choice; only
the derived standard-drink count needs it. Settles it: Joe picking the jurisdiction definition (US 14 g is
the recommended default given the US context of the rest of the system — USDA food, dollar amounts),
recorded by fixing `g_per_standard_drink` and moving this to RESOLVED. Raised 2026-08-27 (session 14),
Missing-B authoring.

**OQ-36 — Which e1RM formula, and which ACWR window lengths and smoothing, does the workout layer use?**
Why open: REQ-WKT-008 computes e1RM from load and reps by a single named formula, and REQ-WKT-012 computes
the acute:chronic workload ratio over fixed window lengths — but the specific choices are not physics, they
are modelling conventions that diverge on real data: Epley, Brzycki, and Lombardi disagree most at high rep
counts; ACWR admits 7:28 coupled vs uncoupled and rolling-average vs EWMA variants. Both are written into
their requirements as **provisional placeholders** and every figure they gate says so, the OQ-10 posture —
they should be set against Joe's actual training data density, not guessed before it exists. Depends on it:
every e1RM and ACWR number the system stores or renders, and any strength finding that rides on them.
Settles it: a calibration once real training data exists — Joe (or the data) choosing the e1RM formula and
the ACWR window/smoothing, recorded in the metric registry and moved to RESOLVED. Not blocking authoring;
blocking only the numbers. Raised 2026-08-31 (session 14), REQ-WKT authoring.

**OQ-37 — The location placeholders: home-geofence definition, mobility-metric windows, and place taxonomy.**
Why open: REQ-LOC-008 designates a home place but the radius and dwell threshold that decide what counts as
"home" are not set; REQ-LOC-013 computes mobility metrics (radius of gyration, location entropy, commute,
transit load) over window lengths that are provisional; and the place-taxonomy granularity is not fixed.
These are the location analogue of OQ-36's workout placeholders and OQ-10's threshold set — modelling
choices that should be set against Joe's real location data, not guessed before it exists, and every figure
they gate says so until then. The home-geofence one is privacy-load-bearing: it decides which coordinates
fall under the absolute home egress ban (REQ-LOC-002), so it must be set conservatively (a larger home
radius errs safe). Depends on it: every mobility number, and the boundary of the home egress ban. Settles
it: a calibration once real location data exists — Joe setting the home geofence, the mobility windows, and
the place taxonomy, recorded in the metric registry / a location ADR and moved to RESOLVED. Not blocking
authoring; blocking the numbers and the location table (Phase 4). Raised 2026-08-31 (session 14), REQ-LOC
authoring.

**OQ-38 — Does a night check-in get a "by the day it rates" subject-day exception, like sleep's by-wake-day?**
Why open: ADR-0019 assigns `subject_day` by start instant (04:00 ET boundary), with one ratified exception
(sleep → wake day). A night check-in submitted after midnight before 04:00 lands on the prior day — correct,
that is the day it rates. But a night check-in submitted the NEXT MORNING (a real case exists: 2026-07-23
08:37 ET) lands by-start on the submission day while rating the previous one, and it diverges from the
phone's own `checkin_date` field. The extraction (ADR-0035) follows ratified ADR-0019 as-is and carries the
phone's `checkin_date` in the immutable capture payload, so a future ruling can re-derive under a new
`rule_version` with zero data loss. Depends on it: which day a night rating counts toward in any daily
aggregate or lagged analysis. Settles it: Joe ruling whether `night_*` metrics take a rated-day exception
(like sleep) or stay by-start; then a `rule_version` bump and re-derivation. Raised by the ADR-0035
reviewer (M4), 2026-09-01.

**OQ-39 — The free-text food path cannot classify alcohol/caffeine, so REQ-ONT-016's consume+metric_key
shape is unmet for drinks logged as text.**
Why open: `_food_atoms` (ADR-0035 increment) stores a self-logged item as a bare `consume` atom — verbatim
label, no nutrient value (REQ-NUT-024 never-guess), and **no `metric_key`**. REQ-ONT-016 requires an
alcoholic or caffeinated drink to carry a registry key (`alcohol_standard_drinks` etc., seeded in 0016) —
but assigning one requires *classifying* the free text ("two beers" → alcohol), and a keyword guess here
would be exactly the fragile shortcut the extraction contract forbids; classification with evidence spans is
the Phase-3 resolver's job (REQ-CAP-109, REQ-NUT-066..068's ABV path). The capture is immutable, so every
drink logged meanwhile re-derives losslessly into keyed atoms once the resolver exists — nothing is lost,
but until then an alcohol atom from this path is indistinguishable from food and no ethanol/standard-drink
number exists. Depends on it: want-9 alcohol instrumentation coverage for text-logged drinks; any interim
alcohol query. Settles it: the Phase-3 extraction/resolution slice landing (re-derive `consume` atoms with
keys from the same captures), or Joe ruling an interim explicit-marker convention (e.g. logging drinks via
a dedicated prompt) if he wants alcohol keyed sooner. Raised by the ADR-0035 increment reviewer (M1),
2026-09-01.

---

**OQ-40 — Coverage-vocabulary thresholds (`fresh ≤ 1 day`, `stale ≤ 30 days`) are provisional.**
Why open: `config.coverage_thresholds` (migration 0034, ADR-0040) seeds `fresh_max_days=1`
and `stale_max_days=30` so `get_domains()` can render `fresh / stale / not_logged /
never_captured`. Neither number has evidence behind it (STOP-AND-ASK #8: never invent a
threshold silently). A weekly Apple Health export makes every body domain "stale" six
days in seven; a nightly check-in makes "stale" mean something different.
Depends on it: every coverage badge on the SOURCES index and on `get_domain` (B2).
Settles it: Joe setting the two numbers against the real capture cadence once a month
of unattended capture exists — possibly per-domain (a column on `config.domains`)
rather than global. Until then the values are read from the table, never hardcoded,
and the envelope says nothing about how they were chosen. Opened 2026-09-02, session 17.

**OQ-41 — Tier-specific sentence templates for `_domain_claims` when the first non-CANDIDATE row exists.**
Why open: `public._domain_claims` (migration 0035, ADR-0041) renders every claim with the 0031
sentence template, which ends "This may reflect a pattern; it is exploratory and unverified."
That is correct for EXPLORATORY and wrong for WATCHING / CONFIRMED / REFUTED / INSUFFICIENT.
Today every `hypothesis_register` row is CANDIDATE (34/34), so the wrong text is unreachable.
Depends on it: REQ-TIER-020 tier vocabulary on the SOURCES page the moment a Watch matures.
Settles it: five templates, one per tier, written into `_domain_claims` by migration and
linted by the tier-vocabulary check — before the first PROMOTED row lands, not after.
Opened 2026-09-02, session 17 (B2).

**OQ-42 — Why was `analysis.forecasts` absent from the live database?**
Why open: migration 0032 (applied 2026-09-01) declares `analysis.forecasts`; `get_today()` and
the nightly `analysis_refresh` read it; on 2026-09-02 both failed live with `42P01 relation
"analysis.forecasts" does not exist` (two `error` rows in `ops.runs`). Nothing in the repo
drops it; `tools/run_analysis.py` and the engines only INSERT. Migration 0035 re-declared it
(IF NOT EXISTS, verbatim) and both paths work again, but the cause is unestablished — a
partial 0032 apply, a manual drop, or an `analysis` schema rebuild outside the repo.
Depends on it: whether any other 0032/0033 object is also missing (checked: `get_today`,
`get_trust`, `analysis.scan_calibration` present). Settles it: Joe recalling whether the
`analysis` schema was rebuilt by hand; otherwise a one-off `information_schema` diff of every
migration-declared object against live, added to `check_invariants.py` as a standing check.
Opened 2026-09-02, session 17 (B2).

**OQ-43 — Are the 282 legacy `public.locations` rows (2026-07-16 .. 2026-07-29) wanted in the restricted store?**
Why open: the previous build's `public.locations` (lat, lon, accuracy, altitude, velocity, course,
battery, trigger, meta) holds 282 fixes from thirteen days in July 2026. Migration 0038 (ADR-0044)
created the restricted store with a `source` value `legacy` reserved for them but deliberately did
not migrate them: a backfill is a data write (STOP-AND-ASK #2), the rows would need a synthetic
`raw_captures` lineage row each (INV-1) with `trust_level` decided (REQ-LOC-004), and thirteen days
adds nothing to a derivation that will have months of Overland fixes.
Depends on it: whether MOVEMENTS ever shows July 2026; whether `public.locations` can be dropped from
the previous build's schema (ADR-0017 territory) once B5 is live.
Settles it: Joe ruling migrate (agent writes a one-off `--only` migration with a `legacy` source and
a redacted capture row per fix, dry-run first) or discard (the table stays where it is, untouched, until
the previous build is retired). Opened 2026-09-02, session 17 (B5.1).

**OQ-44 — RESOLVED 2026-09-02 (ADR-0049; migration 0045; session 20, B8).** Every letter ruled by Joe via the advisor and recorded verbatim in ADR-0049: (a) the second look scores the forward prediction (wired by B9); (b) p_forecast 0.5 until 20 scored resolutions, then the empirical rate; (c) REQ-TIER-018 vocabulary column on the ledger; (d) two looks (earlier); (e) PROMOTED not CONFIRMED; (f) one `_watching_rows()` predicate and a paired-day clock; (g) tests in CI + the RULE-22 grep; (h) paired-day n_eff with the per-side 7 kept; (i) v2 rule template for new registrations; (j) coverage < 0.60 gates; (k) Joe rotates the token. Original text kept below for the record.

*Was:* **OQ-44 — Who scores a `resolve-v1` forward prediction, and what do its `p_forecast` and the ledger's reason vocabulary mean?**
Why open: ADR-0048 makes a CONFIRMED watch insert one forward prediction (the same rule on the next
30 days, `p_forecast` = 0.90, the FDR bound the frozen rule licenses). Nothing scores it: the
forecast resolver (`tools/engines/forecast.py`) matches only `forecast-%` rows, and B7 explicitly
left rolling re-confirmation unbuilt, so RULE-20's automatic demotion path stops at "pending". Three
sub-questions: (a) which job re-runs the contrast on the next window and writes `outcome_bool` /
`brier`; (b) whether 0.90 is the right stated probability or whether the calibration ledger should
supply one once ≥20 resolutions exist (REQ-INF-3xx's count-and-proportion triggers); (c) the ledger's
closed reason set (`confirmed_same_sign_q_lt_0_10` … `expired_no_decision_120d`) is not REQ-TIER-018's
`insufficiency_reason` set (`window_too_short`, `low_n_eff`, `sign_unstable`, …) — one must map to the
other before a vocabulary linter (REQ-TIER-020) reads it. Also provisional and unratified: `MIN_SIDE`
7 per quartile side on a 30-day window; `EXPIRE_DAYS` 120.
Depends on it: whether a CONFIRMED row can ever be demoted without a human (RULE-20; Gate 6);
whether the FINDINGS page can show a Brier record for confirmations.
Settles it: Joe ruling on (b) and the two constants; a B8 build order for (a) and (c). Opened
2026-09-02, session 18 (B7).
*Extended the same day after the adversarial review (findings verbatim in PROGRESS session 18):*
**(d) — RESOLVED 2026-09-02 (Joe: "YES, the reviewer's recommendation"; ADR-0048 §12, migration 0043, session 19). Was:** nightly evaluation from day 30 is optional stopping. Replaying the
resolver's own functions on null series: P(resolve at one look, day 30) ≈ 0.14 iid / 0.20 at ρ=0.5;
P(resolve on some night, days 30–120) ≈ 0.58 iid / 0.74 at ρ=0.5 / 0.86 at ρ=0.7, roughly half in
the registered direction. Recommended reading of the frozen sentence: one look on the first night
with ≥30 paired days and one last look at day 120, with Kish `n_eff` from the ρ `_contrast` already
returns stored and gated (RULE-21). Nothing can mature before ~2 Oct 2026, so this can be ruled
before the first resolution. *Now two looks (first night ≥30 paired days; once more at 120), Kish `n_eff` stored and
gated at 20.* **(e)** B7 said CONFIRMED_OBSERVATIONAL; the build assigns PROMOTED
because REQ-TIER-013's gate is unbuilt (ADR-0048 §9) — confirm or overrule. **(f)** `get_today.watching`
and `get_trust.hypotheses.watching` (0033) ignore resolution and expiry, so after the first
resolution TODAY will say "day 31 of 30" for a row FINDINGS lists as PROMOTED, and the two
`watching` counts diverge (RULE-12); the displayed clock is calendar days while the gate is paired
days after `confirmation_data_from` plus lag. Fix belongs with B8. **(g)** No workflow runs pytest;
every TEST-tier rule is enforced only by hand (pre-existing; surfaced by the review).
*Second review, 2026-09-02 (session 19; findings verbatim in PROGRESS):* **(h)** which `n` does
REQ-TIER-017's floor of 20 govern — the paired-day count (the resolver: ~30 at look 1, ~120 at look 2)
or the per-side count the scan deflates (~8 and ~30)? Per-side at 20 would block look 2 whenever ρ > 0.2,
i.e. nearly always; paired-day at 20 lets an 8-vs-8 contrast through. **(i)** the executed false-resolution
rate of the two-look policy on nulls is ≈ 0.20 at every ρ (family of one → q = p; n_eff gates but never
deflates p). Options: accept it (half lands PROMOTED and then faces the forward prediction); tighten the
rule text for new registrations to q < 0.05 (existing rows are frozen); or deflate p by n_eff (a
Newey–West-flavoured correction, RULE-21). **(j)** `rho` is the paired-index autocorrelation, biased low
under sparse coverage (50 % coverage inflates n_eff ~64 %); REQ-TIER-017's coverage clause (< 0.60 →
INSUFFICIENT) is not implemented — `post_days` has no denominator. **(k)** the Overland bearer token was
printed once into the session transcript at Joe's instruction ("print the token once"), against
CLAUDE.md's "never echoed into a log"; the disagreement is recorded, not hidden — rotating it after
Overland is configured is one `supabase secrets set` and re-typing it on the phone.

## RESOLVED

**OQ-01 — RESOLVED 2026-08-23.** *Is the Supabase credential rotated?*
Finding: the previously-exposed password is DEAD — it fails pooler auth with
`28P01` (tenant found, password rejected), so it had already been rotated
despite the original "not rotated" premise. A working credential was supplied
this session and lives only in `.claude/settings.local.json` under `env`
(gitignored; `lib/db.py` reads it from there). The *live* credential is written
into no committed doc; the dead prior value is deliberately not reproduced here
either. Ruling (Joe, 2026-08-23): **treat the live credential as burned — it
entered the chat transcript in the course of being set, so the transcript now
carries a live secret — and rotate it again once the project is done and
everything is closed.** That final rotation is the standing action; until then
the transcript exposure is accepted risk. No further raising of this question.
Note (2026-08-23): the *dead* prior value was present in git history (the
skeleton commit) but has been **scrubbed from all history** via `git filter-repo`
and verified absent from every git object (see ADR-0013 addendum). The rewrite
changed all commit hashes.

**OQ-02 — RESOLVED 2026-08-23.** *Repository name and where it lives?*
Ruling (Joe): name is **`personal-os`** — nothing cute, nothing identifying.
Where it lives (the GitHub account/org) and the first push are not done yet;
creation is a deliberate outward action for a later session. Pointer: ADR-0013.
**Load-bearing update 2026-08-23 (session 4):** the reliability keepalives (ADR-0024,
REQ-NFR-001/002) are built and proven locally but **cannot fire on schedule until this
push happens** and `SUPABASE_DB_URL` is set as an Actions secret. Gate 0's calendar
clocks (7-day Supabase, 60-day GitHub) therefore **start at the push, not before** — so
this outward action is now the single thing gating Gate 0 closure. Joe does the push
(ruled this session: agent builds + proves locally, Joe pushes).
**Closure verified 2026-08-31:** the push happened, the `SUPABASE_DB_URL` secret is set
(24 Aug), and both keepalives now fire on their daily schedule writing `ops.runs` rows
(`keepalive_supabase` + `keepalive_github`, `trigger=schedule`, status `ok`, every day
26–31 Aug). **Gate 0 is closed** — this blocker is fully cleared.

**OQ-03 — RESOLVED 2026-08-23.** *Public or private repository?*
Ruling (Joe, now that OQ-01 rotation is done): **PUBLIC.** Load-bearing —
public-repo Actions runners are unmetered on 4 vCPU / 16 GB, and the statistical
layer (permutation / specification-curve inference) is only affordable because of
that. Enforced consequence: no personal data ever enters git; every data path is
gitignored by default and a tracked `.parquet`/`.csv`/`.db`/`.sqlite` fails CI.
Pointer: ADR-0013 + RULE-29 (strengthened). The dead credential in history was
scrubbed 2026-08-23 (git filter-repo, verified absent from every object), so the
first public push carries no known secret.

**OQ-05 — RESOLVED 2026-08-15.** *What is the interval width for `weighed` food?*
Ruling: ±10%, equal to `labelled`, marked provisional in REQ-NUT-035 pending a
calibration against a known-label food. Weighing removes portion error but not
composition error, so a weighed generic food's true width may prove *wider*
than a label's legal tolerance, not tighter — the old ±5% placeholder wrongly
made `weighed` the tightest method in the system. `weighed` and `labelled` stay
distinct `estimate_method` values despite equal widths, so calibration can
separate them later without a migration. Pointer: ADR-0005 (stub) + REQ-NUT-035.

**OQ-06 — RESOLVED 2026-08-23.** *Is the subject-day boundary 04:00?*
Ruling (Joe, 2026-08-23): **yes, 04:00 local.** Assignment of a fact to its
`subject_day` is **by start instant**, with one documented exception: **sleep
intervals are attributed to the day they END (the wake date)** — both the
sleep-research convention and how Joe actually refers to it ("last night's sleep"
belongs to this morning). `subject_day` is **stored explicitly** (not only a
generated expression) and carries a **`rule_version`**, so the assignment rule is
itself versioned and a future change to it is visible in the data rather than a
silent rewrite. This settles the straddle problem raised by Decision 5 of
`docs/PHASE2_MIGRATION_PLAN.md`: a durational atom crossing 04:00 lands by its
start, except sleep, which lands by its end. **This amends ADR-0002's mechanism,
not just its parameter:** ADR-0002 defines `subject_day` as a *generated* column
on a 04:00 boundary, but a generated expression cannot encode "by start except
sleep by end" (it needs the atom's type and its interval end), so `subject_day`
becomes an application-computed *stored* column carrying `rule_version`. **Known
transient inconsistency, flagged not hidden:** until the amending ADR (ADR-0019)
and its migration land next session, `RULE-03`, `ADR-0002`, and this resolution
describe `subject_day` differently (generated vs stored). RULE-00 is not in play —
nothing is weakened; a director-ruled amendment is being recorded before the code,
which is the correct order. Pointer: `docs/PHASE2_MIGRATION_PLAN.md` Decisions 5 + A;
ADR-0019 reserved in DECISIONS.md.

---

**OQ-14 — May `derived_measures` rows be deleted?**

*Question.* The guard hook blocks DELETE and UPDATE on `raw_captures`, `atoms`,
`entities`, `links` and `findings`. It does not block them on
`derived_measures`. Behavioural test `tools/test_guard.sh` confirms
`delete from derived_measures` is currently allowed.

*Why open.* Two defensible positions. Deleting a derived measure is recoverable
by recomputation, so it is not in the same class as deleting a capture — that
argues for allowing it. But a recompute that silently produces different numbers
than the ones already narrated to Joe is exactly the failure INV-3 exists to
prevent, and a delete makes that undetectable — that argues for append-with-
supersedes there too.

*Depends on it.* The atoms/derived boundary in ADR-0002, and whether
`derived_measures` needs a `supersedes` column at schema time (retrofitting one
later is a migration over every historical row).

*Would settle it.* A ruling from Joe, written into RULE-02 either way, plus the
matching line in `tools/test_guard.sh` flipped to the expected behaviour.

---

**OQ-15 — RESOLVED 2026-08-31 (session 14).** The forbidden-import lint now exists
in `tools/validate_layout.py` (section 11): it fails the build on `requests`,
`httpx`, `aiohttp`, `socket`, `pycurl`, `urllib.request`, or `urllib.error`
imported in any tracked `.py` outside the sanctioned egress modules (`lib/egress.py`,
owed; `lib/db.py`, the RULE-29-allowed Supabase connection). It is precise —
`urllib.parse` (a pure URL-string utility, used by `lib/db.py`) is deliberately NOT
caught — and it was proven non-vacuous against positive and negative cases
(`import requests`/`urllib.request`/`socket` match; `urllib.parse`/`ssl`/`psycopg`/a
comment do not). **RULE-29's tier LINT is now honest** rather than aspirational.
The residual — a runtime can import dynamically or hand-roll a socket by other
names — is the same static-regex bound as RULE-29's coordinate tripwire (a lint
cannot prove absence of every encoding); review remains the backstop, and the
authoritative enforcement is still the runtime egress proof (`ops.egress_log`)
owed when egress paths exist (Phase 3). Original question retained below.

**OQ-15 (original) — Shell-level egress blocking is bypassable and cannot be fixed at the
shell level.**

*Question.* RULE-29 requires every outbound request to go through the
egress-logged client. The guard hook enforces this by blocking `curl`, `wget`
and `nc`. Behavioural test confirms `python3 -c "import requests;
requests.get(...)"` passes straight through.

*Why open.* This is not a hole that a better regex closes — any language runtime
can open a socket, and a guard that blocks the obvious spellings while missing
the rest gives false assurance, which is worse than no guard. The real
enforcement is a forbidden-import lint (`requests`, `httpx`, `urllib`,
`aiohttp`, `socket` outside `lib/egress.py`) run in CI, plus a review check.

*Depends on it.* Whether RULE-29 can honestly claim tier SQL/LINT or must be
downgraded to REVIEW until the lint exists.

*Would settle it.* Writing the forbidden-import lint and adding it to
`tools/validate_layout.py`, then restating RULE-29's enforcement tier.

**→ Remediation:** `docs/REMEDIATION_PLAN.md` **Track 4** (Phase 2.5 gates) — the
forbidden-import lint closes this OQ and lets RULE-29 claim tier LINT.


## 2026-09-08 operational verification blockers

**OQ-46 — Restore the local database credential.** The database is reachable but
rejects the current environment credential with SQLSTATE `28P01`. Live status,
invariants, migration dry runs and behavioral tests depend on this. Settled by
updating the credential through local secret configuration and a successful
read-only connection; never paste the secret into chat. OQ-45 is reserved by the
existing Ask draft for point-in-time panel correctness.

**OQ-47 — Resolve the scheduled-branch drift.** The GitHub API currently reports
`v2-day1` as the default branch while completed B8–B10 code is on local `main`.
Whether that default is intentional remains unknown. Unattended operation depends
on comparing current remote heads/workflows, aligning the scheduled branch with
the intended implementation, and observing scheduled job success. No repository
setting was changed in this turn.


**OQ-45 — Point-in-time panel and reproducible Ask.** Formalizing the question
reserved by draft migration 0049: `analysis.panel` is rebuilt and lacks the
original observation recorded-at history needed to answer what was known on an
earlier date. A subject-day filter alone cannot meet REQ-INF-108/REQ-ASK-030.
Depends: replay, inference cutoffs, and honest historical answers. Settled by a
versioned/provenance-preserving read path and tests that mutate later knowledge
while proving earlier answers remain identical. No bitemporal completion claim
is made for the current draft.


## 2026-09-09 — B13 capture recovery

**OQ-46 — RESOLVED 2026-09-09.** The credential authenticates. A single connection
returned `current_user = postgres`; `tools/check_invariants.py --core core` reported
**ALL PASS**; the full suite ran **217 passed, exit 0** against the live database.
The prior 104 errors were entirely this credential.

**OQ-48 — What are the four `screen_*` metrics' real definitions?**
`screen_active_hours`, `screen_binge_min`, `screen_max_binge` and `screen_sessions`
are session-level statistics computed by the old stack, whose code is not in this
repository. Their thresholds — the inactivity gap that ends a session, the length
that makes a session a binge — are therefore unknown. B13 deliberately does **not**
re-derive them from `web_visit` / `media_play` atoms, because inventing thresholds
would produce a series that steps silently at the changeover while keeping the
historical name (ADR-0058 §4). They continue to come from `public.signals` and go
visibly stale after 2026-09-02.
*Settled by* either recovering the old definitions, or ruling new ones and storing
them under new metric names so the two series are never confused. **Do not decide
this alone** — the choice is whether continuity or correctness wins, and that is
Joe's call.

**OQ-49 — Which institutions does Joe actually bank with, and do the four shipped
header signatures match his real exports?** `config/institutions/` ships mappings
for Apple Card, Venmo, PayPal and Cash App because REQ-FIN-016 names them. The
headers were written from public export documentation, **not from Joe's files**, and
no real statement has been imported. Joe's actual bank has no mapping at all. This
mirrors the unresolved question already recorded in `specs/03-finance/requirements.md`.
*Settled by* dropping one real export from each institution; a file that matches no
mapping quarantines and prints its observed header, which is exactly the input needed
to write the correct mapping (ADR-0059 §6).

**OQ-50 — Why did device-side capture stop on 2026-07-28, and what prevents a
recurrence?** `public.intraday`, `chrome_visit`/`youtube_watch` and OwnTracks all
stopped within two days of each other and never resumed, while `ops.runs` stayed
green throughout because the *jobs* were alive and only their *inputs* were dead.
The proximate cause is not established: the old stack's ingest code is not in this
repository. `health_auto_export` resumed at some later point but now delivers only
daily aggregates (steps, flights, walking metrics) — not the intraday samples that
`apple_sleep` / `apple_hrv` / `apple_circadian` / `apple_vitals` are derived from.
*Settled by* (a) identifying what the Health Auto Export configuration used to send
and restoring it, (b) re-establishing the OwnTracks and browser-history paths, and
(c) **freshness alerting on data rather than on jobs** — the gap this ADR's context
section exists to describe went undetected for 43 days precisely because job liveness
was the only thing being watched. (c) is Gate 4 work and is the durable fix.

**OQ-51 — The panel's canonical metric map is stale relative to what the feeds now emit.**
Found 2026-09-09 by `tools/check_freshness.py`, which reported canonical `steps` as 54 days
stale. Auditing `panel.SIG_CANON` against `public.signals` shows the map is out of step with
the sources in two distinct ways, both of which make a canonical metric silently blind:

1. **`steps` is wired to `health_history.steps`, dead since 2026-06-23, while
   `apple_watch.steps` is arriving daily (last 2026-09-08).** The live data exists; it lands
   in the panel only under the passthrough name `apple_watch.steps` and never as canonical
   `steps`. Every analysis reading canonical `steps` has been blind since June while the
   measurement sat beside it under another name.

2. **`screen_active_hours` is wired to `attention.active_hours`, which has never existed in
   `public.signals`.** The canonical metric has **zero rows in the panel, ever**. The nearest
   real metric is `attention.screen_active_min` — a different name *and a different unit*.
   Alongside it, `screen_evening_min` and `screen_late_min` appear with only 3 rows each,
   last 2026-09-02, under names `SIG_CANON` does not know.

The pattern behind both: the old stack's attention/health pipeline was at some point rewritten
to emit different metric names, and `panel.py`'s canonical map was never updated to match.

*Why this was not fixed on the spot.* Both repairs are claims about data, not code. Rewiring
`steps` asserts that a Watch-derived daily count and a backfilled historical count are the
same measurement — plausible, but two pipelines can differ systematically (Watch+iPhone
de-duplication versus iPhone alone), and a level shift introduced into a metric that feeds
baselines, the specification curve and the confirmation gate is precisely the invisible
"plausible wrong number" the constitution exists to prevent. Rewiring `screen_active_hours`
additionally requires a unit conversion (minutes → hours), and a guessed conversion is worse
than a missing metric. ADR-0060 states the principle this defers to: asserting that two
differently named series are the same measurement is a deliberate decision with an ADR, never
a tidy-up inside a tool.

*Settled by* Joe ruling, per metric, whether the live series is the same measurement as the
dead one; then either a precedence list in `SIG_CANON` (live source first, historical
fallback) with the level shift measured and reported over the overlap period, or new canonical
names so the two series are never silently concatenated. **Do not decide this alone.**

**OQ-52 — RESOLVED 2026-09-09, by removing the need rather than by amending the rule.**
`tools/engines/panel.py` and `tools/check_freshness.py` now take their schema names as
parameters (validated as plain identifiers, since an identifier cannot be a bind parameter),
exactly as the migrations already do with `__CORE__`/`__OPS__`. Production passes nothing and
gets the production names, so no deployed behaviour changed. Every test schema is now a
throwaway name — `core_fresh_pytest`, `analysis_panel_pytest` and so on — and **no test creates
a schema called `core`, `analysis` or `public` anywhere**. The `assert_disposable_server`
compensating control was deleted along with the problem it compensated for. RULE-01 is
unchanged and untouched, which was the point: the question was whether to widen a constitutional
rule, and the answer was that the rule was right and the code was wrong. Original text below.

**OQ-52 (original) — Does RULE-01's disposable-schema carve-out extend to a disposable *server*?**
Raised by the adversarial review of session 21. RULE-01 permits a behavioural test to build a
**disposable schema** and says "never `core`, never `public`". Three test files
(`tests/test_freshness.py`, `tests/test_panel_attention.py`, and `tests/_import_fixture.py`'s
consumers) create schemas named exactly `core`, `ops`, `analysis` and a table in `public`,
because the engines under test — `panel.build`, `check_freshness` — name those schemas
literally and cannot be pointed elsewhere without parameterising them.

The argument for allowing it is that these run only on a temporary PostgreSQL instance created
and destroyed by `tools/test_local_sql.py`, which is a *stronger* isolation posture than a
rolled-back transaction against the real database: no production catalog is touched at all.
The argument against is that the carve-out was widened **by a docstring**, and under CLAUDE.md's
amendment bar an INTEGRITY-section change requires a written ADR plus an adversarial review
whose job is to break it. That did not happen, and a rule that can be widened by a comment is
not a rule.

*Compensating control added meanwhile:* the `assert_disposable_server` helper in
`tests/_import_fixture.py` refuses
to build the spine unless the server's `data_directory` is under a temp root, so the guarantee
rests on the server's own reported state rather than on an environment variable happening to
point somewhere sensible.

*Settled by* either (a) an ADR amending RULE-01 to "a disposable schema, or any schema on a
disposable server", ratified by consequence with an adversarial review, or (b) parameterising
`panel.py` and `check_freshness.py` on their schema names as the migrations already are, which
removes the need entirely. **(b) is the cleaner answer and does not touch the constitution.**
Do not decide this alone.

**OQ-53 — The panel's two source families disagree about what a day is.**
`analysis.panel` rows from `public.signals` are grouped by `ts::date` — the server's UTC
calendar date. Rows from `core.atoms` are grouped by `subject_day`, which turns at 04:00 ET
(ADR-0019, RULE-03). A visit at 22:00 ET is one day under one rule and the previous day under
the other. B13 avoided the immediate consequence by making atom-derived attention counts fill
only days signals never covered (ADR-0058 §4), so no value is overwritten — but the seam
remains: a series that crosses the changeover has a one-day boundary shift at the join.
*Settled by* deciding whether the panel's day axis is the subject day everywhere (and if so,
rebuilding the signals passes to use it) or the UTC date everywhere. This affects every metric,
not only the two attention counts, so it is larger than it looks.

**OQ-54 — Accumulating quantities were imported as instants, so cross-device
double-counting cannot currently be ruled out.**

Apple exports steps, distance, flights climbed, active energy and exercise minutes as
interval records. `tools/importers/apple_health.py` stores `occurred_at = start` and
leaves `valid_interval` NULL for all of them; sleep is stored correctly as an interval.
14,640 atoms from the 2026-09-09 import are affected.

Two devices reported these metrics concurrently until 2026-08-21 — for `steps`, 2,130
Watch rows and 1,901 iPhone rows. If their intervals overlap, a daily sum counts the
same walking twice. With `valid_interval` NULL that question cannot be asked in SQL:
an overlap query returns 0 for want of an operand. Magnitudes look plausible
(2,616–3,938 steps/day when both devices contributed), and Apple's export appears to
split a day between devices, but plausibility is not proof and this must not be cited
as one.

*Why it is open:* the repair is mechanical — every end timestamp survives in
`evidence_span` — but it is a re-derivation that appends superseding rows, and whether
to run it now or fold it into the next import is a sequencing call. There is also a
prior question: **when two devices both observed a metric, which one owns it?**
RULE-12 requires one owner per measure and this data has two. Watch-over-iPhone is the
conventional answer for gait and energy, but it is a measurement definition, not a
tidying decision, so it is Joe's.

*What depends on it:* every summed daily total for `steps`,
`walking_running_distance_km`, `flights_climbed`, `active_energy_kcal` and
`exercise_minutes`; therefore `describe`, `trend` and `compare` over any of them; and
the panel wiring for these atoms. Until it is settled no such total may be published.

*What would settle it:* a ruling on device precedence, then a corrected re-derivation
populating `valid_interval` with `supersedes` set (never an UPDATE — INV-2), then the
overlap query re-run with an actual operand and its result recorded.

*Related:* OQ-48 (which sleep metric means "how long did I sleep"), OQ-51 (canonical
names vs. what the feeds emit), ADR-0085.

**OQ-55 — The Apple Watch stopped syncing health data in stages, ending 2026-08-21;
the cause is unknown and nothing detects a recurrence at the source.**

Dated from real rows by `check_freshness.py` after the 2026-09-09 import: check-ins
stopped 07-22, `sleep_asleep_min` 07-28, `wrist_temperature_c` 08-08, respiratory rate
and the four sleep stages 08-14, and the whole remaining Watch set — heart rate, HRV,
resting HR, SpO2, active energy, exercise minutes — on 08-21. Every metric still fresh
is iPhone-sourced. This supersedes the earlier reading of OQ-50, which treated
2026-07-28 as a single stop.

*Why it is open:* the pattern says the Watch, not the phone and not the pipeline, but
it does not say whether this is a pairing fault, a storage-full condition, a watchOS
update, a disabled permission, or the Watch not being worn. Those have different fixes
and only Joe can look.

*What depends on it:* 17 stale metrics, which is most of the physiological signal —
every HRV, heart-rate and sleep question is answering from data that stops on 08-21.
Also any trend spanning that date: September steps average a much lower figure against July's
a much higher one purely because the Watch's contribution vanished, and a `trend` answer would
report that as a decline in activity.

*What would settle it:* Joe checks the Watch — worn, paired, Health permissions on,
storage free — and reports what he finds; then a fresh export shows whether rows
resume after 08-21. Until then the freshness report is the detector and it now works.

**OQ-56 — 252 Apple Health records inside the recovery window are in the export but not in
`core.atoms`, and only 24 of them are accounted for.**

`tools/build_inventory.py --core core` reconciles what the source holds inside the window
against what landed. Sixteen of 17 imported metrics are short:

    heart_rate_bpm  -131   active_energy_kcal -26   steps -19   distance -19
    headphone_db     -19   respiratory_rate   -16   hrv   -13   spo2   -4
    flights -2   exercise_minutes -2   resting_hr -1

The importer's own counters explain 24: 18 headphone readings out of range and 6 in-file
duplicates. The remaining ~228 are unexplained.

The likely cause is a difference in what "inside the window" means. The seed counts by the
export's start-date *text*; the importer assigns a subject day on the 04:00 ET boundary
(ADR-0019), so a record starting at 01:00 on 2026-07-01 belongs to 2026-06-30 and is
correctly outside a `--since 2026-07-01` import. That would produce exactly this shape — a
small deficit concentrated in high-frequency metrics. **It has not been proven.** Extending
the window one day added 2,755 atoms, far more than 228, so that test did not isolate the
boundary effect and must not be cited as if it did.

*Why it is open:* a 1.3% shortfall that is understood is fine; the same shortfall
unexplained means the import path may be dropping records for a reason nobody has named,
and REQ-REC-001 requires the inventory to be accurate about what was taken.

*What depends on it:* whether `config.source_inventory` can be trusted as the completion
evidence for M1 and M4, and whether any future import's counters can be read at a glance.

*What would settle it:* a per-record diff for one metric on one day — parse the export for
`heart_rate` on 2026-07-01, compute each record's subject day, and compare that set against
the stored atoms. If the missing records are exactly those before 04:00 ET, this closes as
correct behaviour and the inventory should report the window in subject-day terms instead.

*Related:* ADR-0019 (the 04:00 boundary), ADR-0025 (reconciled, not equal), ADR-0085.

**OQ-56 — RESOLVED 2026-09-09. Every one of the 252 records is accounted for; nothing was
lost.**

The question was whether a 1.3% shortfall between the export and `core.atoms` meant the
import path was silently dropping records. It does not. A per-record scan of the real export,
computing each record's subject day with the importer's own `subject_day()` and comparing
against the stored atoms, reconciles it exactly:

| cause | records |
|---|---|
| the 04:00 ET subject-day boundary (ADR-0019) | 228 |
| `headphone_audio_exposure_db` readings outside the plausible range | 18 |
| duplicates within the file | 6 |
| **unexplained** | **0** |

For `heart_rate_bpm` alone: 9,789 records have a start date on or after 2026-07-01, 9,658
have a *subject day* on or after it, and 9,658 atoms are stored. The 131-record gap is the
131 records that started between midnight and 04:00 on 2026-07-01 and therefore belong to
2026-06-30 — correctly outside a `--since 2026-07-01` import. Fifteen of the seventeen
metrics match their subject-day count exactly; the two that do not are `steps` (-3) and
`walking_running_distance_km` (-3), which together are the six in-file duplicates the
importer reported, and `headphone_audio_exposure_db` (-18), which is its reported
out-of-range count.

The earlier guess in this entry was right about the mechanism and wrong to be stated without
proof; the widened-window test cited then did not isolate it. This does.

*Consequence:* the shortfall is a difference of BASIS, not a loss, and `config.source_inventory`
now says which basis each number uses — `record_count` and `count_in_window` by start date,
`atoms_stored` by subject day. An unexplained delta in a future import is therefore a real
finding rather than an expected mystery.

*Still open, separately:* the 20 Apple Health types with no scope ruling (11,106 records
inside the window) are Joe's decision and are tracked under OQ-57.

**OQ-57 — Twenty Apple Health record types are captured by the phone but no ruling exists on
whether Joe wants them.**

Split out of OQ-56, whose reconciliation question is now closed. `config.source_inventory`
owns these to "Joe (scope ruling)" rather than to a build unit, because assigning an undecided
measurement to B18 would convert a question Joe has never been asked into committed work.

Inside the recovery window: `PhysicalEffort` 8,577, `TimeInDaylight` 1,104,
`EnvironmentalAudioExposure` 1,043, `StairAscentSpeed` 160, `StairDescentSpeed` 121,
`AudioExposureEvent` 46, `EnvironmentalSoundReduction` 39, `SixMinuteWalkTestDistance` 7,
`AtrialFibrillationBurden` 4, `EstimatedWorkoutEffortScore` 3,
`HeadphoneAudioExposureEvent` 2, and nine types with no records in the window.

*Recommendation:* take `TimeInDaylight` and `EnvironmentalAudioExposure` — both are genuine
environmental exposures with no other source in the system, and daylight is a plausible input
to sleep and mood questions. Decline `PhysicalEffort` and `EstimatedWorkoutEffortScore`
despite their volume: both are Apple-computed composites, so under RULE-05 they are resolved
rather than measured, and under RULE-12 they would compete with `active_energy_kcal` and
`exercise_minutes` for the same measure. `AtrialFibrillationBurden` is medical and RULE-26
forbids this system interpreting it.

*What depends on it:* whether these records are imported on the next drop. Nothing else is
blocked — they are additive.

*What would settle it:* Joe's yes/no per type. `BasalEnergyBurned` is NOT in this list; it is
an implementation gap owned by B18, because total expenditure needs it alongside active energy.

**OQ-58 — The repository cannot rebuild the database from empty, and nobody knew.**

`tools/verify_migration_chain.py` applies every migration in order to a disposable server.
It stops at `0020_checkin_mirror.sql`, which reads `public.checkins` — a table no migration
file creates. Thirty-four `public.*` tables are in that position: the old stack made them, the
chain depends on them, the repository does not define them.

The chain is clean once their shapes are supplied (54 migrations, 469 statements), so this is
not a defect in any migration. It is a gap in the recovery story: if the Supabase project were
lost, the repository could not rebuild the schema.

*Why it is open:* there are two legitimate answers and they cost differently. Either (a) the
legacy tables get real DDL under a migration number with their own ADR, making the repository
self-sufficient and the chain a genuine recovery path; or (b) the recovery story is
"restore the Supabase backup", the chain is explicitly not a rebuild path, and
`_legacy_prerequisites.sql` stays a test fixture. (b) is cheaper and honest; (a) is what "$0
recurring, forever" implies if the free tier ever ends and the data has to move.

*What depends on it:* the disaster-recovery answer, and whether a fresh contributor or a fresh
environment can stand the system up at all.

*What would settle it:* Joe choosing (a) or (b). If (a), the DDL already exists in generated
form and needs review, a migration number and an ADR — perhaps an hour.

*Related:* ADR-0088, ADR-0025 (the legacy backfill is reconciled, not equal).

**OQ-54 — MEASURED 2026-09-09. The devices do not hand off. They both count the whole day,
and every summed total across 2026-07-01..2026-08-21 is currently about twice the truth.**

Earlier I looked at seven days, saw plausible magnitudes, and said in conversation that Apple
splits the day between devices without overlap. That was wrong, and it was wrong in the
dangerous direction. Seven days is not a sample; the recorded entry hedged but the spoken
claim did not.

The test that settles it does not need `valid_interval` at all. Compare each device's own
daily total on days when BOTH reported against the total on days when only one did:

| | steps/day |
|---|---|
| Watch alone, on days both reported | 2,843 (**1.01×**) |
| iPhone alone, on days both reported | 2,724 (**0.97×**) |
| their sum, on those days | 5,567 (**1.98×**) |
| total on one-device days | 2,806 (1.00×) |

If the devices handed off, each alone would be well below 1.0× and their sum about 1.0×. Each
is at 1.0× and the sum is at 2.0×: **both devices independently record the whole day.** The
"Watch is worn on active days" confounder predicts the opposite pattern and is ruled out.

*Consequences, stated plainly:*
- Any `steps`, `walking_running_distance_km`, `flights_climbed`, `active_energy_kcal` or
  `exercise_minutes` total covering 2026-07-01 to 2026-08-21 is roughly **doubled**.
- After 2026-08-21 the Watch stopped, so those days are single-device and correct.
- A trend spanning 08-21 therefore shows a ~50% collapse in activity that is entirely
  instrumentation. This is the concrete form of the risk ADR-0085 named.
- Nothing is corrupted: both devices' rows are real observations, correctly stored and
  correctly attributed. The defect would be in any consumer that SUMS them, and no consumer
  does yet — the panel does not read these atoms. The hold announced in ADR-0085 was right.

*Recommendation (Joe's ruling, not mine to take):* one device owns each measure per subject
day, Watch preferred, iPhone used only when the Watch has no record that day. Watch-preferred
because it is worn continuously while the phone is only carried, and on these days the two
agree to within 4%, so the choice costs almost nothing and the rule is simple enough to state
in an answer. The alternative — merge by interval — needs `valid_interval`, which the import
did not populate, and would be a re-derivation for a 4% difference.

*What remains for the ruling:* Watch-preferred vs iPhone-preferred vs interval-merge. The
"never sum across devices" part is no longer a question; the data has answered it.

**OQ-59 — Two category vocabularies are mixed in the transaction history, and merging them is
a measurement decision.**

`public.transactions.category` carries 18 distinct values across 1,002 charges in two clearly
different naming conventions:

- **snake_case (13):** `bank_fee`, `bar_alcohol_smoke`, `coffee`, `dining`, `entertainment`,
  `gas_convenience`, `groceries`, `health_pharmacy`, `other`, `retail_shopping`,
  `subscription`, `transfer_person`, `transport`
- **Title Case (5):** `Fees & Adjustments`, `Food & Drink`, `Groceries`, `Personal`, `Travel`

`tools/engines/categorise.py` folds CASE only — `groceries` (82 charges) and `Groceries` (9)
are one concept under two spellings, and that is deterministic. It does **not** map across the
vocabularies, and it is deliberately incapable of doing so.

*Why it is open:* `Food & Drink` is not a synonym for `dining`. It is a coarser grain that
appears to span `dining`, `coffee` and `bar_alcohol_smoke`. Folding it into any one of them
changes what that category's total means, silently, in the direction of looking more complete.
The same applies to `Fees & Adjustments` against `bank_fee`, and `Personal` against nothing
obvious. This is a taxonomy decision about Joe's own spending and it is his.

*What depends on it:* every category-level spend answer. With the vocabularies separate,
"how much on dining" excludes the 31 `Food & Drink` charges and would understate; merged
wrongly, it overstates. Neither is acceptable without a ruling.

*Recommendation:* treat the Title Case set as the OLDER, coarser import and map it forward —
`Food & Drink` → the finer categories cannot be recovered, so those 31 charges are better
marked `uncategorised_coarse` than forced into `dining`. That preserves the honest gap.
`Groceries` → `groceries` is already handled by case folding. `Fees & Adjustments` →
`bank_fee` looks safe. `Travel` and `Personal` have no snake_case counterpart and can stand
as their own categories.

*What would settle it:* Joe confirming that mapping, or supplying his own. 88 of 93 merchants
already carry a discovered category; only the cross-vocabulary question is open.

*Related:* ADR-0093 (spend by merchant), ADR-0089 (two lanes never blended), OQ-51.

**OQ-60 — Eight of the fourteen domain hero metrics name measures that are not in the registry,
and two of them are the same measure the atom lane already holds under a different name.**

`config.domains.hero_metric` is what any per-domain surface iterates — the weekly report, the
status page, coverage. Checked against `core.metric_registry` and both data lanes:

| domain | hero_metric | in registry | panel rows | last panel day | atom rows |
|---|---|---|---|---|---|
| activity | `steps` | yes | 2,380 | — | 4,031 |
| sleep | `sleep_asleep_min` | yes | 86 | — | 16 |
| recovery | `hrv_sdnn` | **no** | 133 | 2026-07-28 | 0 |
| vitals | `rhr` | **no** | 119 | 2026-07-28 | 0 |
| content | `yt_events` | **no** | 1,364 | 2026-07-28 | 0 |
| money | `spend.monetary_7d` | **no** | 797 | 2026-07-27 | 0 |
| attention | `screen_active_hours` | **no** | 0 | — | 0 |
| places | `away_min` | **no** | 0 | — | 0 |
| food | `meals_logged` | **no** | 0 | — | 0 |
| workouts | `strength_volume` | **no** | 0 | — | 0 |
| body | `weight_lb` | yes | 0 | — | 0 |
| drink | `alcohol_standard_drinks` | yes | 0 | — | 0 |
| mood | `checkin_night_mood` | yes | 0 | — | 0 |
| calendar | *(none)* | — | — | — | — |

**Two are the same measure split across two names and two lanes.** `hrv_sdnn` has 133 panel
rows ending 2026-07-28; `hrv_sdnn_ms` is registered and holds **1,303 atoms**. `rhr` has 119
panel rows; `resting_hr` is registered and holds 30 atoms. Any domain surface iterating
`hero_metric` reports "no recent data" for recovery and vitals while 1,333 observations sit in
`core.atoms` under the other spelling.

*Why it is open, and why I did not just fix it:* this is a measurement-definition decision and
CLAUDE.md reserves it — "never infer data definitions from similar names". The danger is not
hypothetical. A string-similarity search proposes **`sleep_awake_min` for `away_min`**: time
*awake in bed* offered as time *away from home*. Accepting that would attribute one to the
other invisibly and permanently. The two safe-looking pairs may be safe; the tooling that
found them cannot tell the difference, so a person must.

*Recommendation, pair by pair:*
- `hrv_sdnn` → `hrv_sdnn_ms` — almost certainly the same measure; the suffix is a unit. **Confirm.**
- `rhr` → `resting_hr` — same, an abbreviation. **Confirm.**
- `away_min` → `sleep_awake_min` — **reject.** Different concepts entirely.
- `spend.monetary_7d` — a 7-day rolling total, i.e. a *derived* measure, not a raw one. It
  should point at `transaction_amount_usd` with a window, not be a registry key.
- `yt_events`, `screen_active_hours`, `meals_logged`, `strength_volume` — unbuilt scope, not
  naming errors. They stay unmapped until B18/B21 build them, and the domain should say so.

*What depends on it:* every per-domain surface. The weekly report (B15) cannot honestly
iterate domains until each hero metric either resolves or is explicitly marked unbuilt.

*What would settle it:* Joe confirming or rejecting each pair above. Four are recommendations
about naming; four are scope statements needing only a yes.

*Related:* OQ-51 (canonical names vs what the feeds emit), ADR-0089 (two lanes never blended).

**OQ-61 — 94% of "inbound" money is Joe moving his own money, and nothing downstream knew.**

Measured across all 1,052 legacy transactions:

| kind | share of inbound | share of outbound |
|---|---|---|
| **internal transfer** | **~94%** | small |
| merchant | small | **~73%** |
| ATM | negligible | ~11% |
| person-to-person | negligible | ~8% |
| fee | negligible | negligible |

(Shares rather than amounts: this repository is public, and a table of Joe's yearly totals by
category is exactly the personal data RULE-29 keeps out of it. The amounts are in the database.)

`Online Transfer from CHK` alone is 56 rows and most of it. Of the inbound total total inbound, **only
a small fraction is external money**.

Two figures that would be arithmetically perfect and entirely false:

- **Income.** Reading inbound as income overstates it by roughly **seventeen times**.
- **Net spend.** the inbound total in against the gross outflow out nets to **$279**, against true merchant
  spending of **the merchant-spend figure**.

`spend` is not affected: it reports `total_out` and `total_in` separately and has never netted
them, which this data has now validated rather than assumed. `tools/engines/merchants.py` now
classifies `internal_transfer` distinctly from `p2p` and from a generic `transfer`, and the
resolver counts them among the non-merchants, so no internal movement can acquire a merchant
edge or a category.

*Why it is open:* the classification is by descriptor pattern and is therefore a heuristic
about Joe's own accounts. `AUTOMATIC PAYMENT - THANK YOU` is a credit-card payment — internal
if the card is his, external if he is paying someone else's. Only Joe knows which accounts are
his, and the constitution does not let that be inferred.

*What depends on it:* any income, savings-rate, net-worth or net-spend measure. None exists
yet, and none should be built until this is settled, because each would be wrong by an order
of magnitude in the direction that flatters.

*Recommendation:* confirm that `Online Transfer to/from CHK|SAV` and `AUTOMATIC PAYMENT` are
all movements between Joe's own accounts. If so, the current classification stands and
external inbound is a small fraction over the whole record. If any is a third party, name it.

*What would settle it:* one confirmation. Related: REQ-FIN-049/050, ADR-0096, OQ-59.

**OQ-62 — `config.tier_vocabulary` has no row for INSUFFICIENT, so no INSUFFICIENT copy has a
permitted vocabulary.**

Found by building the REQ-NAR-020 linter and running it against the live table. Five tiers
carry vocabulary — DESCRIPTIVE, EXPLORATORY, PROMOTED, CONFIRMED_OBSERVATIONAL, EXPERIMENTAL —
and INSUFFICIENT carries none.

Under REQ-NAR-021's reading (a term reserved for a higher tier is a violation), INSUFFICIENT
sits at the bottom of the ladder, so *every* term in the table is above it. The live
INSUFFICIENT templates pass today only because they happen to use structural words and words
in no tier's list. That is luck, not design: one edit adding "typically" to a refusal would be
caught, and one adding an unlisted claim word would not.

REQ-TIER-018 makes INSUFFICIENT an answer rather than a silence, and REQ-TIER-030/031/033
mandate its render forms — a data-requirement sentence and a trial sentence. So it is a tier
with required wording and no vocabulary governing that wording.

*Why it is open:* two defensible answers with different consequences.
(a) INSUFFICIENT gets its own row — the words a refusal is allowed to use ("not enough", "would
raise it", "stored and traceable"). The linter then governs refusals as tightly as claims.
(b) INSUFFICIENT is exempt because a refusal makes no claim, and the linter skips it. Cheaper,
and it leaves refusal copy ungoverned — which is where a hedge could quietly become a hint.

*What depends on it:* whether REQ-NAR-022's build-time check can be turned on for the
INSUFFICIENT templates at all. Today it runs and passes vacuously.

*Recommendation:* (a). A refusal is the surface most likely to be softened into an implication
over time, precisely because it feels unsatisfying to write. Governing its words costs one
table row.

*What would settle it:* Joe choosing (a) or (b). If (a), the permitted terms are a short list
he can dictate. Related: REQ-TIER-018/020, REQ-NAR-020..022, ADR-0099.

**OQ-63 — The forecaster issued 32 predictions for metrics whose capture had already stopped,
and every one of them is unresolvable.**

`core.predictions` holds 32 rows created 2026-09-02, resolving 2026-09-03 to 2026-09-10, across
four metrics. Resolved read-only against the panel:

| metric | predictions | panel data ends |
|---|---|---|
| `hrv_sdnn` | 8 | 2026-07-28 |
| `rhr` | 8 | 2026-07-28 |
| `sleep_asleep_min` | 8 | 2026-07-28 |
| `steps` | 8 | 2026-07-17 |

**All 32 are unresolvable — `no_observation`.** The forecaster predicted four metrics for days
it had no way to observe, three of them dark since July.

*Why this is dangerous rather than merely useless.* Each carries `p_forecast = 0.9`. A resolver
that treated "no observation" as "the forecast was wrong" would score every one at Brier 0.81,
produce a catastrophic calibration record, and — under REQ-INF-3xx's auto-demotion — demote
findings on the strength of it. An instrument failure would become a forecasting failure, and
the demotions would look earned. `tools/engines/calibration.py` refuses all 32 and refuses the
summary; that is the correct behaviour and it is also a warning.

*The gap:* nothing stops a forecast being issued for a metric whose capture is stale.
`check_freshness.py` knows `hrv_sdnn_ms` and `resting_hr` are stale. The forecaster does not
consult it. A prediction about a dark instrument is not a forecast; it is a guess with a
timestamp.

*Recommendation:* the forecast job should refuse to issue a prediction for a metric whose last
observation is older than its `max_staleness_days`, and record the refusal. That is a new
requirement in REQ-INF §E, not a code change to an existing one, so it needs Joe's assent
before being written.

*A second-order note:* once migration 0056 is applied, `steps` becomes resolvable — the atom
lane runs to 2026-09-09 — so 8 of the 32 would resolve. The other 24 stay unresolvable until
the Watch is fixed (OQ-55).

*What depends on it:* every calibration figure, and therefore auto-demotion. Related:
REQ-INF-300..309, REQ-NFR-005..014, ADR-0100.

**OQ-64 — `config.*` is not schema-parameterised while `__CORE__` is, so a shared config table
holding a foreign key into core cannot be correct in both worlds.**

Migrations rewrite `__CORE__` and `__OPS__` to a target schema pair, which lets the spine test
apply the whole chain to a throwaway schema inside a rolled-back transaction (ADR-0022).
`config.*` is written literally and is therefore **shared** between that test and production.

That was harmless while config tables only held their own data. `config.derivation_catalogue`
(0053, mine) broke it by carrying `measure REFERENCES __CORE__.metric_registry(metric_key)`.
Applied to production the constraint targets `core.metric_registry`; applied to a pytest schema
pair the table already exists, so `CREATE TABLE IF NOT EXISTS` is a no-op and the constraint
still points at the real core. A migration that inserts into both then writes the registry row
to the pytest registry and the catalogue row to the shared table — **73 errors in the
production suite**, and pytest-only measures leaking into a shared table.

0061 is guarded (it inserts only when the parameterised core *is* the real core) and the suites
pass, but the guard treats a symptom.

*Why it is open:* three answers with different costs.
(a) Parameterise `config.*` as `__CONFIG__` throughout — correct, and it touches every
migration that mentions config, which is most of them since 0034.
(b) Drop the foreign key from `config.derivation_catalogue` and enforce the relationship in a
check tool — cheap, and loses a real integrity guarantee.
(c) Leave it, and require every future migration inserting into a config table with a core
foreign key to carry the same guard — cheapest now, and it is a rule nobody will remember in
six months.

*What depends on it:* every future config table that references core. `config.panel_aggregation`
and `config.panel_composition` (0056) already do, and only avoid the problem because nothing
inserts into them from a parameterised context yet.

*Recommendation:* (a). It is the only one that makes the test and production the same shape,
and the alternative is a rule that has to be remembered every time. It is mechanical, and the
migration chain verifier would catch a mistake immediately.

*What would settle it:* Joe choosing. Related: ADR-0022, ADR-0082, ADR-0097.

**OQ-65 — A production trigger enforces a rule no requirement states, and cites a requirement
that says something else.**

`migrations/0047_recommendations.sql` (applied) raises:

> `REQ-ACT-012: a recommendation is never rewritten; only status, demoted_reason, demoted_at
> and is_daily may change.`

REQ-ACT-012 is the **medical-vocabulary rule**: *"IF a generated instruction contains any term
from the stored medical vocabulary, THEN the action layer SHALL replace the instruction with
the stored referral string."* It says nothing about rewriting. REQ-ACT-011, the neighbouring
demotion requirement, does not either. **No REQ-ACT requirement carries the append-only
constraint the trigger enforces.**

Found by the requirement audit: REQ-ACT-012 showed as *mentioned* in a test file without a
named test, and following that mention led to a test asserting the trigger's message rather
than the requirement's content.

*The constraint itself is right.* A recommendation that can be rewritten is a recommendation
whose history cannot be trusted, which is INV-2 and RULE-02 applied to a new table. It is the
citation that is wrong, and a wrong citation is worse than none: a reader who follows it finds
a requirement about medicine and concludes the constraint is unrelated to what it protects.

*Why it is open:* two fixes, and the choice is Joe's because one adds a requirement.
(a) Re-cite the trigger to **INV-2 / RULE-02**, which already exist and already say this. A
migration changing an error string, no behaviour change.
(b) Author a REQ-ACT requirement for recommendation immutability and cite that. More precise,
and it grows the requirement set by one.

*What depends on it:* nothing functional — the constraint works. It matters for the audit: a
requirement can appear covered because a test asserts a message that names it, while the
requirement's actual content is untested. REQ-ACT-012's real content *is* now tested
(`test_REQ_ACT_012_medical_vocabulary_is_replaced_by_referral_string`), which is how the
discrepancy became visible.

*Recommendation:* (a). The rule is constitutional, not domain-specific, and INV-2 already says
it for every append-only table in the system.

**OQ-66 — One rung of the evidence ladder has two names, and two live tables disagree about
which.**

`core.findings.tier` (migration 0007, applied) permits:
`DESCRIPTIVE, CANDIDATE, PROMOTED, CONFIRMED_OBSERVATIONAL, EXPERIMENTAL, INSUFFICIENT`.

`config.tier_vocabulary` (migration 0049, applied) carries rows for:
`DESCRIPTIVE, EXPLORATORY, PROMOTED, CONFIRMED_OBSERVATIONAL, EXPERIMENTAL` — **no CANDIDATE**,
and no INSUFFICIENT (that second gap is OQ-62).

REQ-TIER-001 names the tier set with `CANDIDATE`. REQ-NAR-013 defines "the **EXPLORATORY
surface**" as where a `CANDIDATE` finding may be shown. So the two words are not a rename: one
is a tier, the other is the surface that displays it — and the vocabulary table, which the
linter reads, is keyed by the surface name while findings are stored under the tier name.

*Why it matters.* REQ-NAR-020 requires the linter to lint **every** generated claim against the
vocabulary for its tier. A claim carrying `tier = 'CANDIDATE'` has no row to lint against. The
first version of `tools/engines/narration.py` raised `unknown tier 'CANDIDATE'` on exactly that
input — and raising is not a safe failure for a linter whose job is to run on everything.
CANDIDATE is now aliased to EXPLORATORY so both rank alike, which is correct but is a
workaround for a naming split that should not exist.

*Why it is open:* two answers, and one of them touches applied migrations.
(a) Add a `CANDIDATE` row to `config.tier_vocabulary` duplicating EXPLORATORY's terms. Cheapest,
and leaves two names for one rung — the condition that produced this.
(b) Choose one name. `CANDIDATE` is what REQ-TIER-001 and `core.findings` use, so renaming the
vocabulary row is the smaller change; but `EXPLORATORY` is what RULE-17 and the surface
requirements say, and `config.operations` already stores it as a default tier.

*What depends on it:* the narration linter, `analysis.f_domain_status`'s band language, and any
future surface that reads a tier's permitted words. Nothing is currently broken — the alias
holds — but a third consumer written against one name will meet rows carrying the other.

*Recommendation:* (b), choosing `CANDIDATE`, because the tier is what gets stored on a row and
the surface can be named anything. It is a data change to one table plus the alias's removal.

*What would settle it:* Joe choosing a name. Related: REQ-TIER-001, REQ-NAR-013, RULE-17, OQ-62.

**OQ-67 — Personal figures are already published in this repository's public git history.**

`josephdelany/personal-os-v2` is public. Between 2026-09-09 and 2026-09-10 I committed Joe's
real spend totals at named merchants, his daily step figures, his sleep minutes and a
category-level breakdown of his year's money into migration comments, four ADRs and the
checkpoint — violating CONSTITUTION.md's "not one row of personal data is ever committed or
tracked."

The working tree is redacted. **The history is not**, and history is what a public repository
publishes. The values should be assumed already fetched and indexed.

*Why it is open:* removing them requires rewriting published history (`git filter-repo` or an
interactive rebase across ~30 commits) followed by a **force push to a shared remote** — a
destructive operation that CLAUDE.md reserves for explicit authorization, and one that breaks
every existing clone and any fork.

*The options:*
(a) Rewrite and force-push. Removes the values from the repository. Does not remove them from
any clone, fork, or cache that already has them, and GitHub retains unreachable objects for a
period.
(b) Make the repository private. Stops further publication immediately, is not destructive, and
is reversible. Does not remove what is already public.
(c) Leave it. The figures are a few merchant totals and step counts — real personal data, and
not credentials.

*Recommendation:* (b) then (a), in that order. Making it private costs nothing and stops the
bleeding; the rewrite can then happen without time pressure. Doing (a) first on a public repo
races against whoever is watching it.

*What would settle it:* Joe's decision. A force push will not happen without it.

*Related:* RULE-29, CONSTITUTION.md "Cost and privacy", and the finding that produced this —
migration 0057's header refuses to commit merchant patterns on the same ground.

**OQ-68 — `sleep_minutes` has two sources with different lanes, and one name.**

`tools/extract_checkins.py` writes `sleep_minutes` atoms from Joe's self-reported check-in
("how long did you sleep?"). `config.panel_composition` also derives `sleep_minutes` from the
Watch's staged sleep intervals. Same metric key, two sources, two RULE-05 lanes: one a
coarsened self-report, the other a device interval union.

Found by an adversarial review of migration 0056: both arms of `f_daily_panel` emitted the
metric, so one day produced two rows. Coverage counted two, could exceed 1.0, and passed the
0.60 INSUFFICIENT floor on a doubled denominator — twelve real nights in thirty read as 0.80
instead of 0.40. The median mixed the two lanes in one distribution, which is INV-5.

0056 now serves a composed metric from the composed lane only, so the double-count is gone.
**The self-reported atoms are then not served at all**, and that is a real loss rather than a
fix: Joe's own answer about his sleep becomes invisible while the Watch's derivation is shown.

*Why it is open:* the two are not interchangeable and merging them is a measurement decision.
A self-report and a device derivation disagree systematically, they have different coverage —
the check-in stopped 2026-07-22, the Watch 2026-08-14 — and averaging them produces a number
that tracks whichever source is still reporting.

*The options:* (a) two metric keys, `sleep_minutes_self_report` and `sleep_minutes_device`,
with the composed one derived and the self-report answerable in its own right; (b) the device
lane wins where it exists and the self-report fills gaps, disclosed per day; (c) the
self-report is not a sleep duration at all and should be a different metric entirely.

*Recommendation:* (a). Two names for two lanes is what INV-5 asks for everywhere else in this
system, and it makes "what did I say" and "what did the Watch derive" both answerable — which
is more useful than either alone, and lets their disagreement be a finding.

*What depends on it:* any sleep answer once check-in capture resumes. Nothing today: zero
`sleep_minutes` atoms exist. It would have fired silently the first time Joe logged one.

*Related:* OQ-48, INV-5, RULE-05, ADR-0089.

**OQ-69 — "how is my sleep quality" resolves to the 3-day unstaged fragment, and the obvious
fix makes it worse.**

`_ask_resolve_metric('sleep quality')` returns `sleep_asleep_min` at similarity 0.429 —
16 atoms over 3 days — rather than `sleep_minutes`. The part-vs-whole demotion does not fire
because it requires the WHOLE to clear the same 0.35 floor, and "Sleep duration" scores 0.261
against that phrase.

I lowered the demotion floor to 0.20 and a review measured the result: the winner becomes
`sleep_minutes` at 0.273, which then **fails the 0.35 answerability gate** two statements later
in `ask`. The question stopped being answered at all — only the metric named in the refusal
changed. Worse, `config.domains` contributes a second display name ('Sleep' for
`sleep_asleep_min`), and at 0.20 that pair activates: **"asleep" — a similarity 1.000 match —
resolved to `sleep_awake_min`, "Awake during sleep"**, for a question about being asleep.

Reverted to 0.35. A demotion floor *below* the answerability floor can demote a part in favour
of a whole the next check rejects.

*Why it is open:* trigram similarity is the wrong instrument for this and no threshold fixes it.
"quality" is a word about no metric in the registry, and the phrase's similarity to every
candidate is low; the winner is then decided by string accident. My justification numbers for
the 0.20 change did not reproduce (0.32/0.43 claimed, 0.261/0.138 measured), which is the
RULE-00 signature — a gate constant moved on numbers nobody checked.

*The options:* (a) an explicit synonym table mapping phrases Joe actually uses to metrics —
data, inspectable, and it makes "sleep quality" a decision rather than an accident; (b) require
the whole to beat the part by a MARGIN rather than clear an absolute floor; (c) refuse when no
candidate clears a confident threshold and offer the nearest, which is honest and answers
fewer questions.

*Recommendation:* (a). Every other resolution problem in this system was solved by putting the
decision in a table; this is the same shape.

*What depends on it:* any question phrased with a word the registry does not contain.

**OQ-70 — the finance capture gap is real and currently undisclosed in the answer.**

ADR-0096 established that `bank_csv` stopped on 2026-05-13 and `chase_email` began 2026-06-20,
with 38 days covered by neither. A spend total spanning that window is arithmetically correct
and materially incomplete.

I added `covered_days`/`covered_weeks` to the answer to disclose it, and a review measured them:
the value was days÷7 over *all* transactions in the range, so it was not weeks, was not filtered
to the merchant asked, and carried no knowledge bound. Its source key also missed the format
`tools/backfill_run.py` writes, collapsing those atoms into one 'unknown' source whose span
covers the whole history — so it would have reported full coverage across the very hole it
existed to reveal.

Withdrawn. **A disclosure that is wrong is worse than none, because it is read as reassurance.**

*Still open:* the gap needs disclosing. `source_discontinuity` catches a window spanning two
sources, and each source's own span is in the result, but neither says "this window contains
days no source covered."

*What would settle it:* a definition of capture coverage that does not derive from where
charges happen to be — most likely a table recording when each source was active, written when
a source is configured rather than inferred from its output.

**OQ-71 — `analysis.baselines` has no usable knowledge time, so a band cannot be replayed.**

`f_domain_status` takes `p_known_at`. I bounded the baseline lookup on `computed_at <=
p_known_at` so a replay would not be handed a band built after the question. A review showed
`tools/engines/baselines.py` DELETEs the entire table and reinserts on every nightly run — so
`computed_at` is the last *rebuild* time, not the band's knowledge time. After one run, a replay
pinned to any earlier moment matches no baseline at all: every band NULL for every domain, while
`resolution` still reads 'resolved' and nothing distinguishes "outside a band" from "no band"
from "band suppressed by a clock". INV-4 satisfied; RULE-06 broken.

Reverted, and a test now pins the reversal so nobody reapplies it.

*Why it is open:* this is OQ-45's shape in a second place. A lane rebuilt in place cannot answer
"what did you believe then", and the fix is either an append-only baseline history or an
explicit statement that band position is always as-of-now and never replayed.

*Recommendation:* the explicit statement, until something needs the history. A band is a
descriptive aid, not a claim being replayed, and an append-only baseline table for 104,391 rows
a night is a large cost for a capability nothing has asked for.

**OQ-72 — `entity_aliases.canonical` is nullable, and one reader must now handle it.**

REQ-FIN-051 non-merchant resolutions (ATM, internal transfer, fee) are real answers with no
merchant name, so 0057 makes `canonical` NULL exactly there and pairs it with a required
`non_merchant_kind`. Before this, the writer emitted those rows and the schema rejected them,
and because the commit is after the loop, ONE ATM descriptor rolled back an entire resolver run.

*Why it is open:* the nullability is settled, but `v_current_aliases` now returns rows whose
`canonical` is NULL, and any future consumer that renders an alias must decide whether a
non-merchant appears in merchant lists at all. Today the only consumers are the resolver's own
head lookup and `read_human_aliases`, which filters `canonical IS NOT NULL`.

*What depends on it:* B14's spend-by-merchant surfaces, once they read the ledger rather than
recomputing from the cascade.

*What would settle it:* Joe saying whether "ATM withdrawal" should appear as a line in a
spend breakdown, or be excluded from merchant reporting entirely and counted separately.

**OQ-73 — the resolver picks one raw descriptor of several as "the original".**

REQ-FIN-061 asks for "the original, verbatim". Several raw descriptors normalise onto one alias
by design, so there is no single original. The writer now records the most-transacted one in
`raw_descriptor` and the rest in `also_seen`, replacing a version that dropped them silently in
dictionary order.

*Why it is open:* most-transacted is a defensible tie-break, not a ruling. Most-recent would
also be defensible and would track a merchant's current descriptor format.

*What depends on it:* nothing blocking; both are recorded, so a later ruling can re-derive.

*What would settle it:* Joe saying which he would rather see quoted back when asked where a
charge came from.


**OQ-74 — REQ-INF-540 names `dynamax`, and `dynamax` cannot responsibly be used.**

The requirement says the regime HMM SHALL be fitted "using `dynamax`". Attempting the install
found two blockers that package metadata does not show: `dynamax` depends on **`tfp-nightly`**, a
nightly build with no pinnable version whose contents change daily, and it requires `jaxlib`,
which **ships no macOS x86_64 wheel** — so it cannot run on this development machine at all.

The behaviour every other §G.3 requirement specifies is implemented and tested against synthetic
series with known regimes (ADR-0105): state means recovered within 0.15 h, run-length median
recovered as exactly the true 50-day switching period, K=2 selected by the pre-registered
held-out criterion. Only the named implementation differs.

*Why it is open:* a requirement naming a specific library is a requirement, and substituting for
it is a scope decision, not an implementation detail. I should not ratify my own deviation.

*Options:* (a) amend REQ-INF-540 to specify the MODEL rather than the library — "a Gaussian HMM
with 2-4 latent states", which is what the requirement is actually about; (b) keep `dynamax` as
the requirement and accept that regimes cannot be developed or tested locally, only in CI; (c)
drop regimes.

*Recommendation:* (a). Every other requirement in §G.3 constrains behaviour rather than tooling,
and this is the only one that names a package — most likely because the brief was written with a
library in mind rather than because the library is the requirement. A nightly dependency also
cannot satisfy RULE-28's failure-at-the-limit clause, so (b) conflicts with an existing rule.

*What depends on it:* nothing is blocked; the code exists and passes. This is about whether the
requirement or the implementation is corrected.

**OQ-75 — the Bayesian effect layer needs a machine this one is not.**

§G.2 (REQ-INF-520..527) specifies NUTS with named priors, partial pooling over day-of-week and
season, and a latent missingness indicator. NumPyro is the right tool and `jaxlib` has no macOS
x86_64 wheel, so it cannot be run on this machine. CI (`ubuntu-latest`) would run it.

*Why it is open:* building it anyway would mean writing a sampler that is never executed once
where it is written, whose tests only ever run on a nightly CI job. That is unverified code
behind a green badge earned somewhere else, and this project's whole discipline is that a claim
is worth what its runnable evidence is worth.

*Options:* (a) implement it and accept CI-only verification, with every iteration costing a push
and a wait; (b) hand-roll a Gibbs sampler in numpy — tractable for this model, since a Normal
likelihood with Normal priors and half-normal scales has conjugate conditionals, and it would run
and be tested locally; (c) defer §G.2 until it can be developed on hardware that supports jax.

*Recommendation:* (b) if the layer is wanted soon, (c) if it is not urgent. Not (a). The model
REQ-INF-520 specifies is a hierarchical linear model, which is exactly the case where a Gibbs
sampler is straightforward and exactly checkable — recovery of a known beta within its HDI is the
same test either way.

*What depends on it:* B19 is otherwise complete. §G.2 is its last unstarted piece.

**OQ-76 — `get_state` ships a `streaks` array, and the frontend brief forbids streaks on the same page.**

REQ-CAP-095: "The system SHALL NOT display a streak count, a consecutive-day counter, a badge, a
chain, or any message referring to a broken run."

`docs/LOVABLE_FRONTEND.md` line 16 says *"No streaks, no badges, no rings, no confetti, no
gamification of any kind, ever."* Line 31 of the same document ships:

```
"streaks":[{"metric":"rhr","run_days":3,"direction":"above","historical_max_run":8}]
```

Migration 0030 (`get_state`, **live in production**) is where that comes from.

*The substance is defensible; the framing is not.* A run of consecutive days a metric sits
outside its personal band is a real statistical observation, and it is not a compliance counter —
nobody earns it and nothing is lost by breaking it. `narration.py` already records the distinction
in a comment: a capture streak "makes a missing day a failure. Joe's capture has stopped twice
this year through no act of his; a streak would have scored both as lapses."

But the field is called `streaks`, carries `run_days` and `historical_max_run`, and a frontend
reading that contract will render "3 day streak — best ever 8". At that point the distinction
lives only in a migration comment, and REQ-CAP-095 is violated by a screen nobody intended.

*Why it is open:* renaming a field in a live API is a contract change, and deciding whether
metric-deviation runs count as "streaks" under REQ-CAP-095 is a product judgement about what Joe
will read, not a technical one.

*Options:* (a) rename to `deviation_runs` with `days_outside_band` / `longest_previous_run`, and
keep the data — the observation is genuinely useful and only the vocabulary is dangerous;
(b) scope REQ-CAP-095 explicitly to capture-adherence surfaces and leave the field, accepting
that a renderer may still gamify it; (c) drop the field.

*Recommendation:* (a). The information is worth having and the word is the entire problem. A
rename also makes the frontend brief self-consistent, which it currently is not.

*What depends on it:* the frontend, when it is built. Nothing backend is blocked. `lint_envelope`
in `tools/engines/compliance.py` will fail this envelope the moment it is wired to a surface,
which is the intended behaviour and is why this must be settled before the frontend, not after.
