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

**OQ-06 — Is the subject-day boundary 04:00?**
Depends on it: the generated `subject_day` column in ADR-0002, and therefore
every daily aggregate ever computed. Changing it later rewrites history.

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
