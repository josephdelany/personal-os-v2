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

**OQ-30 — What evidence-tier floor governs a REQ-ACT recommendation, and how does a
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

---

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

**OQ-15 — Shell-level egress blocking is bypassable and cannot be fixed at the
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
