# PROGRESS

Newest last. One entry per session. Appended by `/session-end`, never edited.
Each entry: date · what was attempted · what works · what does not · requirement
IDs touched · commit hash.

---

## 2026-08-08 — repository created, layout validated before any code

**Attempted.** Stand up the v2 repository skeleton and prove the pieces fit
together before writing a line of implementation.

**Works.** `tools/validate_layout.py` runs clean-ish (see below). 541 EARS
requirements across three spec files parse, IDs are unique, every statement
carries a binding SHALL, SHOULD appears nowhere, the index count matches disk,
and the constitution's rule numbers are contiguous. `tools/test_guard.sh`
exercises the destructive-command hook against 25 real command strings: 23
behave as specified.

**Does not work.** Three subsystem specs remain unwritten (REQ-ONT, REQ-WKT,
REQ-BOD, REQ-SLP, REQ-CTX, REQ-NFR, REQ-UI). No schema, no code, no tests
beyond the two harnesses above. Two guard-hook findings open — see
OPEN_QUESTIONS OQ-14 and OQ-15.

**Requirement IDs touched.** None — no implementation this session.

**Commit.** (pending first commit)

---

## 2026-08-15 — Session 1: orientation, verification, and five director rulings

**Attempted.** Orientation and verification only. No implementation code, schema,
or migration — by instruction. Read CLAUDE.md, the full constitution (31 rules,
RULE-00..RULE-30), OPERATING_MANUAL, ROADMAP, OPEN_QUESTIONS, REQUIREMENTS_INDEX,
DECISIONS, and the 150 capture/nutrition requirements incl. all 12 Gherkin
scenarios. Ran both gates. Traced the Big Mac path end to end. Surfaced OQ-03,
OQ-05, OQ-07, the manual §4 recommendation, and one new correctness finding for
Joe to rule on.

**Works.** `tools/validate_layout.py` exit 0 (31 passed, 0 warnings, 0 failed).
`tools/test_guard.sh` exit 0 (25 passed, 0 failed). Both re-run at session end,
same result. Working tree clean at session start and after (only this PROGRESS
entry changed).

**Does not work / unchanged.** No code exists yet beyond the two harnesses. The
gates check the specification, not any implementation.

**Director rulings this session (to be executed, paired with their settling
artifact, in the owning phase — NOT applied this session):**
1. **OQ-03 → PUBLIC.** Precondition, not preference: nothing is pushed to a
   public remote until the Supabase credential (OQ-01) is rotated. Before Phase 0
   commits `archive/`, grep all 19 legacy files for the old credential string and
   for any Supabase key or connection URL; report findings before the commit.
   Settles when: repo ADR written + OQ-01 rotated + archive grep clean.
2. **OQ-05 → weighed interval widened to ±10% (= labelled), marked provisional
   in REQ-NUT-035.** Rationale accepted: weighing removes portion error, not
   composition error. Calibration exercise (weigh a known-label food, compare
   stored vs label) logged as the measured number that would replace the
   placeholder. Settles when: ADR-0005 + REQ-NUT-035 edit, then OQ-05 → RESOLVED.
3. **OQ-07 → ACCEPT the narrowing.** System measures use; Joe supplies value where
   he wants it. Words "necessary"/"unnecessary" stay banned in generated copy.
   Settles when: finance ADR, then OQ-07 → RESOLVED.
4. **Manual §4 → MOVE the fabrication + traceability gates to a new Phase 2.5,
   before the Big Mac slice.** Settles when: ROADMAP edit.
5. **RULE-02 finding ACCEPTED → first task of Phase 2.** Change enforcement from
   "absence of a grant" (which the table owner and Supabase `service_role`
   bypass) to "demonstrated inability to mutate": a BEFORE UPDATE OR DELETE
   trigger that RAISEs, plus a test that connects as the role the resolution job
   actually uses, attempts DELETE on `atoms`, and asserts failure. Constraints
   from Joe: (a) write an ADR covering the owner/service_role bypass, the
   trigger design, and which role each job connects as, BEFORE the code; (b)
   decide and record that role explicitly — "whichever role the client defaults
   to" is how the hole reopens. This strengthens a gate, so RULE-00 is not in
   play, but it changes a stated enforcement mechanism, hence the ADR.
   CORRECTION (reviewer, this session): Joe's ruling named "ADR-0003", but
   DECISIONS.md:19 already reserves ADR-0003 for the Evidence ladder. This work
   must use a fresh unreserved number — next free is ADR-0010. Also noted: the
   trigger remedy is not novel — the same "put the constraint where the agent
   cannot route around it" pattern is already accepted at
   specs/04-reasoning/requirements.md:317,360 (an UPDATE-rejecting trigger on
   hypothesis_register), and ROADMAP Gate 2 (line 49) already requires "an
   attempted UPDATE on atoms fails with a permission error, shown." Phase 2's
   task is therefore to HARDEN Gate 2, not invent a gate.

**Requirement IDs touched.** None — no implementation this session.

**Commit.** (pending)

---

## 2026-08-15 — Session 2: four director instructions executed as the record

**Attempted.** Execute Joe's four Session-2 instructions as committed record on
`main` (not proposals). Still no implementation code, schema, or migration —
this is spec and doctrine work only, which is in scope for this phase. Ran
session-start in full first: both gates green at start, no regression against
Session 1.

**Works.** `tools/validate_layout.py` exit 0 (31 passed, 0 warnings, 0 failed)
after every edit — 152 requirements in the capture/nutrition file, 543 total,
REQ-NUT census 55, index count matches disk, zero unquantified-adjective
warnings. `tools/test_guard.sh` exit 0 (25 passed). Adversarial reviewer run
before commit.

**What changed, by instruction:**

1. **ADR-0003 → ADR-0010 confirmed.** DECISIONS.md now reserves ADR-0010 for the
   RULE-02 enforcement-hardening work (the atoms/`raw_captures` mutation-
   rejecting trigger and the role decision), with a note recording that Joe's
   Session-1 "ADR-0003" collided with the reserved Evidence-ladder number and
   ADR-0010 is the corrected free number. No ADR body written — that is Phase 2.

2. **OQ-05 resolved; REQ-NUT-035 widened ±5% → ±10%.** The `weighed` interval is
   now equal to `labelled` and marked provisional, paired with stub ADR-0005.
   ADR-0005 records the reasoning: a labelled packaged food has known portion
   and composition-only uncertainty; a weighed generic food has known portion
   but composition uncertainty plausibly *wider* than a label's legal tolerance,
   so weighed may end up wider than labelled, not tighter. The binding
   structural rule: `weighed` and `labelled` stay distinct `estimate_method`
   values even while their widths are equal, so calibration can separate them
   later without a migration. Never collapse two methods because their current
   numbers match. RULE-00 not triggered — the ±5% was an invented placeholder,
   not a passing threshold; no test asserts it (F-005 stays `failing`), so
   nothing was weakened to make anything pass, and the change references ADR-0005
   as RULE-00 requires for any threshold move. OQ-05 moved to RESOLVED; spec
   E-Q1 marked resolved.

3. **Big Mac count→grams gap (Reviewer Finding 3) filled.** Added **REQ-NUT-050**
   (Event-driven: a unitless count of a USDA-Branded-resolved food multiplies the
   record's per-serving gram weight by the count, stores the serving definition,
   sets `estimate_method = 'labelled'`) and **REQ-NUT-051** (Unwanted behaviour:
   no Branded per-serving weight available → count left unconverted, item marked
   `unresolved`, name/token/count retained verbatim, review-list reason
   `no_branded_serving`). Index and self-reported counts updated; gate re-run,
   green. *Deviation from the instruction, flagged:* Joe said "a new REQ-NUT id"
   (singular); I wrote two, because EARS forbids two patterns in one statement
   and "state what happens when no Branded record exists" is a distinct testable
   behaviour that needs its own ID and test under this project's rules.

4. **Audit trail for commit 914de1f written (below), per RULE-00.**

**Audit trail for commit 914de1f — adjective-linter narrowing (RULE-00 record).**
Joe authorised this narrowing and the reasoning was his; it is recorded here
because loosening a LINT check is RULE-00 territory and the justification
otherwise lived only in a chat the repo cannot see.

- *What the linter now skips.* Two things, both in `tools/validate_layout.py`'s
  WEASEL check. (a) The word `robust` is exempt when immediately preceded by a
  hyphen, so a hyphenated qualifier + `robust` compound passes. (b) The scan no
  longer reads a requirement's preamble (anything before the first ` shall`) or
  its trailing `because`-clause rationale — it inspects only the normative SHALL
  response. This cleared 5 false positives (REQ-INF-020/026/215 were noise;
  REQ-FIN-166 and REQ-INF-521 are rationale-clause wording, now recorded under
  OQ-10).
- *Why `autocorrelation-robust` is a term of art.* It names a specific
  statistical property — an estimator or standard error whose validity does not
  depend on the absence of serial correlation (e.g. Newey–West HAC errors,
  RULE-21). It is a fixed technical compound with a precise meaning, not the
  vague quality adjective "robust" as in "a robust system". Flagging it as an
  unquantified adjective was a false positive.
- *The check still fires on a bare adjective in a SHALL response.* The narrowing
  removed false positives without disarming the check: `robust` (un-hyphenated)
  and `fast/slow/quick/reasonable/appropriate/user-friendly/efficient/as
  needed/etc.` are still flagged when they appear inside the normative SHALL
  text of a requirement. This was **demonstrated by execution**, not asserted:
  the exact regex + normative-trim logic was run on four synthetic inputs and
  behaved correctly — `"...SHALL be robust"` → fires on `robust`;
  `"...SHALL use autocorrelation-robust errors"` → clears; a `because`-clause
  adjective → clears; a preamble adjective → clears. The current gate run
  reports zero adjective warnings because no real defect exists in the specs,
  not because the check was disabled. (No permanent negative-case fixture exists
  in the repo — noted as owed under WHAT I DID NOT DO.)

**Requirement IDs touched.** REQ-NUT-035 (edited: interval width ±5% → ±10%,
provisional). REQ-NUT-050, REQ-NUT-051 (new). No test named for them yet — these
are specification rows; their proving tests arrive with the Phase 3 slice, and
`ops/features.json` F-005 (REQ-NUT-035) stays `failing` until one exists.

**WHAT I DID NOT DO.**
- Did **not** write the body of ADR-0005 beyond the `weighed`-width decision. It
  is a labelled stub; cache-first lookup, the portion table, and the other
  method widths are explicitly listed as unauthored and due before Phase 3.
- Did **not** write the body of ADR-0010, or any RULE-02 trigger code — Phase 2.
- Did **not** add a proving test for REQ-NUT-035/050/051, and did **not** move
  any `ops/features.json` entry to `passing`. No code exists to test yet.
- Did **not** argue REQ-NUT-050's choice of `estimate_method = 'labelled'` in an
  ADR; it is stated in the requirement and noted as owed in ADR-0005's gap list.
- Did **not** add a permanent negative-case fixture for the adjective linter. Its
  continued teeth were shown by a one-off execution (recorded above), not by a
  committed test that feeds a known-bad adjective and asserts the check fires. A
  linter with no negative fixture is a gate proven only by inspection — worth a
  small test in a later session.
- Did **not** execute the other Session-1 rulings (OQ-03 repo, OQ-07 finance,
  manual §4 ROADMAP move, RULE-02 hardening) — those belong to their owning
  phases and were not in Joe's four instructions.
- **Newly surfaced, not built (for Joe):** REQ-NUT-050 assumes a count maps to
  whole servings. A fractional or split branded item ("half a Big Mac") is not
  handled by 050 or 051 and is not specified anywhere. Flagging, not deciding.

**Commit.** 6f7c5eb

---

## 2026-08-15 — Session 2 follow-up: partial servings, and one home for undecided facts

**Attempted.** Three follow-up rulings from Joe after commit 6f7c5eb. Still spec
only, no code. Both gates green after every edit.

**What changed:**
1. **REQ-NUT-050/051 kept as two** — confirmed by Joe, no edit.
2. **Partial servings.** Added **REQ-NUT-052** (Event-driven: a fractional or
   partial count of a Branded-resolved food multiplies the per-serving values by
   the stated fraction and drops `estimate_method` to `portion_table`, so the
   wider ±20% interval of REQ-NUT-037 governs instead of the `labelled` ±10%,
   because a stated fraction of a serving is an estimated portion, not a measured
   one) and **REQ-NUT-053** (Unwanted behaviour: a vague or non-numeric
   quantifier — "most of", "a few bites" — is NOT mapped to an invented fraction;
   it goes `unresolved` + review with reason `vague_fraction`). My call on the
   choice Joe left open: vague quantifiers are unresolved/reviewable, not a
   documented mapping, because a "most of = 0.75" table is the same
   fabricated-portion guess REQ-NUT-023/025 forbid. Two IDs again, for the same
   EARS reason Joe endorsed for 050/051.
3. **Single-home tracking.** The capture/nutrition spec header no longer restates
   its own blockers; it points to `docs/OPEN_QUESTIONS.md` as canonical. The
   Section-D blocker (D-Q1, Branded vs FNDDS) is now carried in OPEN_QUESTIONS
   alongside OQ-06, so the blocking-status fact has exactly one home.

Counts: 152 → 154 in-file, 543 → 545 total, REQ-NUT 55 → 57; index matches disk.

**Adversarial review ran before commit and changed the requirements.** Findings
folded in: REQ-NUT-052 now preserves the Branded `fdcId`/serving definition and
brand-owner on the row (so a fractional row's composition provenance is not lost
to the `portion_table` width label), decomposes a mixed count like `2.5` into a
whole `labelled` part (via REQ-NUT-050) plus a fractional `portion_table` part,
and guards its trigger on a per-serving gram weight being present so it does not
overlap REQ-NUT-051's unresolved path. REQ-NUT-051 now says "(whole or
fractional)". REQ-NUT-053's rationale now cites RULE-06 (never impute) rather
than the loosely-fitting REQ-NUT-023/025. The OPEN_QUESTIONS "canonical" claim
was corrected from over-claiming ("the spec files point here rather than
restating their blockers") to the accurate scope: this file is the canonical
*index* of blocker status; full question text stays in each spec section, so
D-Q1 is a one-line index entry here, not a second full copy.

**Correction to an instruction (flagged, not silently followed).** Joe said "the
spec header should point at OQ-06 rather than restating it as D-Q1," treating
D-Q1 and OQ-06 as one fact. They are two different facts: D-Q1 is the
Branded-vs-FNDDS preference (Section D); OQ-06 is the 04:00 subject-day boundary.
Writing "OQ-06 blocks Section D" would have been false. So I applied the
principle rather than the literal edit: the spec header defers to OPEN_QUESTIONS,
and D-Q1's blocking status was given its own canonical home there. Net effect is
what Joe asked for — one fact, one home — without equating two unrelated facts.

**Requirement IDs touched.** REQ-NUT-052, REQ-NUT-053 (new). REQ-NUT-035/050/051
unchanged in this follow-up.

**WHAT I DID NOT DO.**
- Did **not** resolve D-Q1 itself (Branded vs FNDDS) — only gave its blocking
  status a canonical home. Still Joe's decision.
- Did **not** add a new `estimate_method` enum value for "a fraction of a label";
  I reused `portion_table` for its width rather than touching the RULE-08 /
  ADR-0002 method enum. If Joe wants fraction-of-label distinguishable from a
  true portion-table estimate later, that is a schema change, not a spec edit.
- Did **not** add proving tests or move any `ops/features.json` entry — no code.
- Did **not** add the missing adjective-linter negative fixture (still owed from
  the prior entry).
- Did **not** mint an `OQ-nn` number for D-Q1; it is referenced by its spec-local
  ID in the canonical blocker list. If every blocker should carry an OQ number,
  that is a small follow-up.

**Commit.** (this follow-up's commit on `main`)

---

## 2026-08-23 — Session 3: environmental hardening of `.claude/` (Reward-Hacking-Benchmark)

**Attempted.** Two config changes Joe directed from the Reward-Hacking-Benchmark
finding (environmental hardening — remove the capability, don't just instruct
against it — cuts exploitation ~87.7% with no loss of task success): (1) deny the
agent write access to the feature ledger `ops/features.json` so it cannot mark
its own work passing, and add a sanctioned pytest-parsing writer; (2) make the
adversarial reviewer no cheaper than the builder. Config/doctrine only, no
implementation code, schema, or migration — in scope for Phase 0. session-start
ran in full first: both gates green at start, no regression.

**Works (evidenced above).**
- `.claude/settings.json`: added `Edit(/ops/features.json)` and
  `Write(/ops/features.json)` to `permissions.deny`. **Verified empirically, not
  asserted:** an `Edit` attempt on `ops/features.json` was rejected by the
  permission engine ("File is in a directory that is denied by your permission
  settings") — stopped before execution. `features.json` is byte-unchanged. The
  leading-slash form resolves to the project root, confirmed by the block.
- `.claude/agents/reviewer.md`: added `model: opus` and `effort: high` to the
  frontmatter. `effort` confirmed a recognized subagent frontmatter key
  (low/medium/high/xhigh/max) against current docs, twice, after a reviewer
  disputed it.
- `docs/adr/0011-features-json-write-lock.md` written; indexed in `DECISIONS.md`.
- `validate_layout.py` 31 passed / 0 warnings / 0 failed. `test_guard.sh` 25
  passed / 0 failed. Both re-run after every edit.

**Does not work / deliberately not done.**
- `tools/update_features.py` (the sanctioned writer) was **not** built. Joe chose
  to defer it to Phase 3 (recommended): there is no pytest suite to parse, no CI
  step to run it, and no entry legitimately flips before the Big Mac slice, so
  building it now is an unexercised control that manufactures false assurance —
  the exact failure the hardening is against. Recorded in ADR-0011. The deny is
  safe alone: nothing should write the ledger during Phase 0–2, and the Edit/Write
  tool deny does not block the future script's own file writes.
- No `features.json` entry moved to `passing`; all 15 remain `failing`. Correct —
  no code exists to prove any of them.

**Reviewer change bundling corrected.** The reviewer-model change was first
recorded inside ADR-0011 (a ledger-lock ADR); on the reviewer's finding it was
removed from the ADR and recorded here instead, since it is unrelated to the
ledger and uncontested.

**Requirement IDs touched.** None — this is harness config and doctrine, and no
REQ governs `.claude/` settings. No test named, no ledger entry moved.

**WHAT I DID NOT DO.**
- Did **not** build `tools/update_features.py` — deferred to Phase 3 by Joe's
  ruling (ADR-0011). The single thing I was most tempted to build to look
  complete; building it now would have been control theater.
- Did **not** verify that `effort: high` changes reviewer *behaviour* — I verified
  only that it is a recognized key in the docs. Whether this installation's
  parser honours it at runtime I could not introspect; worst case it is inert
  (harmless), not harmful.
- Did **not** test the `Write(/ops/features.json)` deny directly (only `Edit`),
  to avoid risking an overwrite of the ledger. The block message is directory-
  scoped and both rules share syntax, so Write is covered by the same mechanism —
  but that specific rule is inferred, not independently exercised.
- Did **not** address the pre-existing `features.json` → spec mismatch the
  reviewer surfaced (F-006/F-014/F-015 cite `REQ-ONT`/`REQ-NFR`, prefixes absent
  from every spec). Logged as OQ-16. Out of scope for this session.
- Did **not** run `git push` — nothing leaves local (OQ-01 credential + OQ-03
  public/private still open; Joe asked only to commit).

**Commit.** (this session's commit on `main`)

---

## 2026-08-23 — Session 4: Phase 0 live half — DB reachable, live archive, ETL TLS posture

**Attempted.** The live half of Phase 0: give the tools a working DB credential,
reach the Supabase database over a *verified* connection, inventory every table
with exact row counts, and archive the data tables to Parquet with re-read
verification. Then settle the `csv__workouts` question, record the TLS decision as
an ADR, and execute four of Joe's rulings. This is the first session to touch the
live database.

**Works (evidence is command output shown in-session, not assertion).**
- **Credential.** Old exposed password is DEAD (`28P01`, tenant found / password
  rejected) — it had been rotated despite OQ-01's premise. A three-way probe
  (real tenant `28P01` vs bogus tenant `XX000 ENOTFOUND`) proved the tenant is
  found and the pooler host/region correct. Working credential now in the
  gitignored `.claude/settings.local.json` `env` block; a fresh tool shell reads
  it (length verified, value never printed).
- **Verified TLS, pinned CA.** `lib/certs/supabase-prod-ca-2021.crt` is the real
  self-signed `Supabase Root 2021 CA` (fetched from the official `supabase/cli`
  repo over public-CA TLS), **proven to anchor the live pooler chain**
  (`openssl s_client -CAfile … → Verify return code: 0 (ok)`). `lib/db.py` is the
  one sanctioned connection: `CERT_REQUIRED` + hostname check, only
  `VERIFY_X509_STRICT` cleared (the intermediate+leaf omit `keyUsage`; the root
  carries it — verified by cert inspection). **CERT_NONE was considered and
  rejected** — recorded in ADR-0012 and `lib/db.py`.
- **Inventory.** 74 base tables (34 `public` DATA, 40 Supabase-managed), exact
  counts shown.
- **Archive.** 34/34 public DATA tables → Parquet, **426,269 source rows =
  426,269 Parquet rows**, confirmed by an independent fresh re-read (0 mismatches;
  sha256/bytes recorded per table). SELECT/count only — INV-2 intact, nothing
  mutated. Manifest `_legacy_snapshot/supabase_manifest.json` in the existing
  manifest format.
- **`csv__workouts` settled.** Live `public.workouts` is 0 rows / 9 cols — the
  empty backup CSV reflected reality, not truncation. No workout history exists
  anywhere. Documented gap, not fabricated.
- **ADR-0012 written** (ETL TLS posture) and indexed. `pg8000` (pure-Python PG
  driver) installed — a $0 local dep with no service/limit, RULE-28 cost test N/A.
- Both gates green after every edit: `validate_layout.py` 31/0/0; `test_guard.sh`
  25 passed. Invariant queries run live: RULE-02 = 0 (vacuous, no spine tables);
  RULE-04 errors `42P01` (derived_measures absent — Phase 2 unbuilt).

**Rulings executed (Joe, this session).**
1. OQ-01 → **RESOLVED**: live credential treated as burned (it entered the chat
   transcript), rotate again at project close; standing action recorded.
2. ROADMAP Phase 0 amended: "14 legacy tables" (an uncounted estimate) → "all
   live tables and all local legacy sources, count verified at archive time."
3. Supabase-managed tables (auth/storage/**vault.secrets**/cron/…) **not**
   archived — infra, and secrets must never leave the platform.
4. Before any keepalive: reported existing cron. **8 active pg_cron jobs, all
   succeeding today** — the *previous build is still live and writing to this DB.*
   None is a keepalive, so a future one won't duplicate. Not built (needs
   `ops.runs`, Phase 2).

**Does not work / not done.**
- Gate 0 not closed: keepalives (Supabase 7-day + GH Actions 60-day) need
  wall-clock days and `ops.runs` (Phase 2); `archive/` read-only not verified;
  OQ-02/OQ-03 open. See WHAT I DID NOT DO.

**Adversarial review ran and changed the work.** Five findings; four fixed
(keyUsage rationale was backwards in 3 places; ADR "one path" overclaim; the
dead-credential literal left in a tracked doc + a self-contradicting claim;
missing PROGRESS entry — this). The two pre-existing unverified scratch scripts
(`_legacy_snapshot/live_snapshot.py`, `diag.py`, not authored this session) are
disclosed in ADR-0012 and **recommended for deletion, pending Joe** — not removed
because they were not created here.

**Requirement IDs touched.** None — no REQ governs Phase-0 archive/transport
infra. No test named, no `ops/features.json` entry moved (all 15 remain failing;
the ledger is also write-locked to the agent per ADR-0011).

**WHAT I DID NOT DO.**
- Did **not** commit or push — no commit instruction this session; `lib/`
  untracked, doc edits unstaged.
- Did **not** delete the two stale scratch scripts (`live_snapshot.py`,
  `diag.py`) — surfaced for Joe's decision; the single thing most tempting to
  quietly remove to make ADR-0012's "one path" true on disk.
- Did **not** archive the 40 Supabase-managed tables (by ruling); if cron config
  matters for the keepalive, only `cron.job` rows are to be captured.
- Did **not** preserve column *types* for the 5 empty tables (workouts etc.):
  `archive.py` writes a null-typed schema for a 0-row table, so a consumer can't
  recover the DDL from the Parquet alone (recoverable from the live DB).
- Did **not** stand up either keepalive or `ops.runs` — Phase 2.
- Did **not** re-archive after noting the source is live and mutating — the
  Parquet is a point-in-time snapshot; the busy tables (events/signals/intraday)
  have grown since.
- Did **not** add an automated gate for the TLS posture (ADR-0012 is REVIEW-tier).

**Commit.** (pending — not committed this session)
