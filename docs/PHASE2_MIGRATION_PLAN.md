# PHASE 2 — MIGRATION PLAN AND SCHEMA DECISIONS

**Status: PROPOSAL. No SQL executed. No migration written.**
Session of 2026-08-23 (Phase 2, session 1 of several). Plan-and-ADRs only, by
Joe's instruction. Nine schema-shaping decisions are settled here *on paper*
before any migration touches the database, because each one rewrites every
historical row if it is wrong.

Every technical claim below was verified against primary sources before being
accepted (Joe's Phase-1 citations were wrong three times in seven). Verdicts:
**VERIFIED / PARTLY / WRONG / UNVERIFIABLE**, with the source. Where I disagree
with the proposal, it is marked **▶ DISAGREE**. Where there is a consequence Joe
was not told, it is marked **▶ UNPRICED**.

Two live-database facts, gathered this session, are load-bearing and are stated
once here:

- **Supabase is PostgreSQL 17.6.** Live DB size **197 MB** of the 500 MB free
  ceiling (top tables: `intraday` 94 MB, `signals` 46 MB, `events` 34 MB).
- **`pg_available_extensions` on the live instance:** `pg_duckdb`, `pg_ducklake`,
  `duckdb`, `timescaledb`, `temporal_tables`, `periods` are **all absent**.
  Only `btree_gist 1.7` and `pg_partman 5.3.1` are installable. This single
  query settles decisions #5 and #7 on facts, not inference.

---

## SCORECARD — how each of the nine claims held up

| # | Topic | Claim verdict | My disposition |
|---|---|---|---|
| 1 | E-values as FDR currency | **PARTLY** — one sub-claim WRONG, one citation is *cautionary* | Adopt, with corrected justification |
| 2 | Forecasts as distributions | **VERIFIED** — with a binary-vs-continuous nuance | Adopt as an *extension*, not a replacement |
| 3 | Non-response is a row | **VERIFIED** (JMIR cite snippet-confirmed only) — mainstream | Adopt (separate table, different axis from RULE-07) |
| 4 | Scale/rounding metadata | **PARTLY** — paper real but is a GMM-estimation paper | Adopt (metadata is a sound extrapolation) |
| 5 | Valid time as a range type | **PARTLY** — PG facts right, PG18/19 attribution risk | **▶ DISAGREE with blanket application; needs Joe's ruling** |
| 6 | Trust level at ingest | **VERIFIED** (NSA cite snippet-confirmed only; trifecta verified verbatim) | Adopt (strongest single addition) |
| 7 | Analytical store = Parquet on R2 | **VERIFIED** (confirmed on live instance) | Adopt; **▶ one architectural seam is Joe's ruling** |
| 8 | Capture schema consequences | **PARTLY** — two facts WRONG | Adopt the intent; correct the two facts |
| 9 | Hypothesis register (RULE-19) | **VERIFIED** — already fully specified | No new work; already designed |

**Four corrections you should see first (Phase-1 lesson):**
1. **#1(d) is WRONG.** "A p-value cannot be converted to an e-value after the
   fact" is false. A p-to-e *calibrator* exists (e.g. `e = κ·pᵏ⁻¹`). The real
   cost is *power loss*, not impossibility. The decision to store native e-values
   still stands — precisely *because* calibration is lossy — but the reason must
   be stated correctly.
2. **#1(e) — arXiv:2502.08539 is a *cautionary* paper, not a cheerleader.**
   "Anytime-valid FDR control with the stopped e-BH procedure" (Wang,
   Dandapanthula, Ramdas; *Statistics & Probability Letters*) shows stopped e-BH
   *can fail* FDR control unless an extra no-unobserved-confounding assumption
   (its Assumption 3.1) holds. Cite it as "conditions under which stopped e-BH is
   valid," never as "e-BH just works." Citing it the wrong way would repeat the
   Phase-1 error exactly.
3. **#8(a) — Apple's on-device model context window is 4,096 tokens, not ~8k.**
   (Apple TN3193.) Off by 2×. The "one record per model call" constraint is
   *tighter* than you were told, not looser.
4. **#8(b) — the workout dedup key `(source + start + duration)` is partly
   wrong.** The whole point of the duplicate is that it comes from a *different
   source* (Apple Watch vs GymKit machine) for the *same* activity. Putting
   `source` in the identity fails to collapse exactly the duplicate you care
   about. Apple keys on *time overlap + source priority*. Use `(start-window,
   duration-window)` as identity, `source` as a tiebreaker.

---

## DECISION 1 — E-VALUES AS THE FDR CURRENCY

**Claim.** Findings must store an e-value (or sufficient statistics to compute
one) on every test row, because continuous monitoring invalidates a
Benjamini-Hochberg p-value guarantee; e-values are immune to optional stopping,
compose by multiplication, hold under arbitrary dependence; a p-value cannot be
converted post-hoc. Keep hierarchical FDR; make e-values the currency.

**Verification.**
- Optional-stopping immunity (anytime-valid), multiplication, e-BH under
  arbitrary dependence: **VERIFIED** (Wang, *e-values review*; Wang–Ramdas 2022).
- Arbitrary-dependence robustness is **conditional**: it holds only for *valid*
  e-values (nonnegative, 𝔼≤1 under the null). Not a free lunch on any input.
- "Cannot convert a p-value post-hoc": **WRONG** — calibrators exist; cost is
  power. (ERCIM/ResearchGate on p-to-e calibration.)
- `arXiv:2502.08539`: **real, but cautionary** (see correction #2 above).
- `online-fdr` (PyPI, **BSD-3**, Oliver Hennhoefer): **VERIFIED**; implements
  LOND/LORD/SAFFRON/ADDIS and **e-LOND + e-BH** in current source — but it is
  **beta, single-maintainer, ~0.0.x**. Pin the version; verify e-LOND is in the
  installed wheel (it was absent from the 0.0.3 PyPI snapshot).

**▶ UNPRICED — the cost of e-values is lower power when you *don't* peek.** This
is the universally-acknowledged price of anytime-valid inference. Your
justification ("I will look constantly; every peek invalidates BH") is exactly
the condition under which the trade is worth it — so the decision is right *for
your usage*, but it is a real trade, not a strict upgrade. If a given analysis is
run once and never re-peeked, a p-value would be more powerful there.

**Recommendation: ADOPT.** On every test/finding row store the **e-value** and
the **sufficient statistics** to recompute it (test type, statistic, n, n_eff,
ρ, maxlags — several already required by REQ-INF-020..024). Keep the tree-FDR
structure (RULE-21); e-BH replaces BH-on-p-values as the rejection rule. Store a
p-value too where one exists, for interpretability, but the *gate* is the
e-value. This **amends RULE-21 *and* REQ-INF-106** — the latter is a binding SHALL
("apply Benjamini–Hochberg across the set of registered hypotheses… and persist
that family size", `specs/04-reasoning/requirements.md:325-326`), so switching the
rejection rule to e-BH is a *requirement* change, not only a rule change. Fills
reserved **ADR-0007** (multiplicity control). Joe's nod needed because it changes
a stated method **and** a binding requirement.

**Schema.** `findings`: add `e_value NUMERIC`, `e_value_method TEXT`,
`e_process_params JSONB` (the sufficient statistics), keep `n_eff`, `rho`,
`maxlags`. **Correction (reviewer, this session):** e-values are *not* greenfield —
REQ-INF-112 (`:343-344`) already gates the CONFIRMED→micro-trial step on a stored
E-value below 1.5. The actual gap is narrower and precise: today the E-value is a
*single-hypothesis gate at one tier*, while **BH-on-p-values (REQ-INF-106) is the
family-wide rejection rule**. The change is to make a *stored e-value the
family-wide FDR currency (e-BH)* on every test row, not to introduce e-values from
nothing. (An earlier draft miscited REQ-INF-114 here; that requirement is about the
observations store never UPDATE-ing, unrelated to e-values.)

---

## DECISION 2 — FORECASTS AS DISTRIBUTIONS, NOT POINTS

**Claim.** Every stored prediction carries a predictive distribution (quantiles
or samples) plus issue time, horizon, resolution time. CRPS and log score cannot
be computed from a point forecast (`scoringrules` 0.11.0).

**Verification.**
- CRPS/log score need a distribution: **VERIFIED**, with nuance — **CRPS of a
  point mass = MAE** (graceful degradation), but **log score is undefined /
  infinite for a point** (no graceful case). Asymmetry matters for a unified
  scoring column.
- `scoringrules` **0.11.0**: **VERIFIED**; **Apache-2.0** (not BSD/MIT); backends
  NumPy/JAX/PyTorch (heavy optional deps beyond NumPy — relevant to $0/dep-caution).

**▶ UNPRICED — the current `predictions` table is *binary*, not continuous.**
The spec's `predictions` table (REQ-INF-300..330) stores `p_forecast` (a scalar
probability), `outcome_bool`, `brier`, `log_score`. Brier and log score are
*correct* for a **binary** forecast — you do not need CRPS there. CRPS is for
**continuous** outcomes (e.g. "tomorrow's weight," "next week's mean sleep").
So this is not "the table is wrong"; it is "the table only covers binary
outcomes, and continuous forecasts need a second shape." Do not throw away the
binary path.

**Recommendation: ADOPT as an extension.** Support two forecast shapes:
- **Binary** — keep `p_forecast`, `brier`, `log_score` (already specified).
- **Continuous** — add a `forecast_distribution JSONB` (quantile grid *or*
  sample vector + a `dist_family` tag), `issued_at`, `horizon`, `resolves_at`,
  and score columns `crps`, `log_score_cont`. Store the distribution, not a mean.

This extends **RULE-20**; recommend a short ADR (proposed **ADR-0021**). Defer
the *scoring compute* to Phase 6, but lock the *column shape* now (cheap now,
migration-over-history later).

---

## DECISION 3 — NON-RESPONSE IS A ROW

**Claim.** When a scheduled prompt fires and I don't answer, that writes a row. A
missing row and a recorded refusal are different facts; one cannot be
reconstructed from the other. Needed for joint missingness modelling (JMIR
mHealth 2025, 10.2196/65350).

**Verification.**
- DOI **10.2196/65350**: **SNIPPET-CONFIRMED, PRIMARY UNREACHABLE** — the JMIR
  page returned 403 to the verifier; the title/DOI/argument were confirmed only
  via the search-index snippet and the accepted-preprint record, not the primary
  article, and the author byline could not be retrieved. Title as found:
  "Within- and Between-Individual Compliance in Mobile Health: Joint Modeling
  Approach to Nonrandom Missingness…" (JMIR mHealth 2025). It fits a joint model
  of substance + missingness because missingness is non-random; this *requires*
  per-prompt issue/answer records. **Decision 3 does not depend on this citation
  being exact — it stands on its own reasoning** (you cannot classify a
  missingness mechanism without recording which prompts were issued). The label is
  downgraded; the decision is not.
- "Silent gap ≠ recorded non-response," matters for MCAR/MAR/MNAR: **VERIFIED,
  mainstream.** You cannot classify a missingness mechanism without the
  denominator (which prompts were issued).

**▶ UNPRICED — this is a *different axis* from RULE-07, and there is a fourth
category you weren't told about.** RULE-07's three-valued presence
(`observed / observed_absent / unknown`) is about the *value* of a fact. Prompt
non-response is about the *lifecycle of a question*. They are orthogonal and must
not be merged into one column. The literature distinguishes at least:
`delivered_unseen` (phone off/asleep) · `seen_declined` · `partial` ·
**`never_scheduled`** (planned missingness — MCAR by construction). Collapsing
`never_scheduled` into `declined` would *bias the missingness model*. Model the
prompt lifecycle explicitly.

**Recommendation: ADOPT** — a dedicated `prompt_dispatch` (or `ops.prompts`)
table: one row per prompt *issued*, with `scheduled_for`, `delivered_at`,
`responded_at NULL`, and `response_state ∈ {answered, seen_declined,
delivered_unseen, partial, expired}`. `never_scheduled` is the *absence* of a row
for a slot the schedule defines, so it is derivable and needs no row. Proposed
**ADR-0017**. Schema is cheap; lock it now, wire it when prompts exist (Phase 3+).

---

## DECISION 4 — SCALE AND ROUNDING METADATA PER VARIABLE

**Claim.** `metric_registry` stores response scale, number of points, rounding
step per variable, because self-reports are coarsened interval data, not points
(Psychometrika, arXiv:2501.10726).

**Verification.**
- `arXiv:2501.10726`: **VERIFIED it exists and is Psychometrika (2025)** — but it
  is **"Estimation of Linear Models from Coarsened Observations: A Method of
  Moments Approach"** (van Praag, Hop, Greene), a **GMM estimation** paper. It
  argues ordinal responses are coarsened observations of a latent continuum and
  that the *number of categories* demonstrably changes the analysis.
- **The "store scale metadata as schema" idea is your reasonable extrapolation,
  not a claim in the paper.** Don't attribute it to the paper. The coarsened-
  latent framing itself is **mainstream/orthodox**, not fringe.

**Recommendation: ADOPT.** `metric_registry` already carries `scale_type` and
`legal_transforms` (ADR-0002, REQ-INF preamble) but does not enumerate them. Add
per-variable: `response_scale` (e.g. `[0,10]`), `n_scale_points` (e.g. 11),
`rounding_step` (e.g. 1), and keep `self_report BOOL`. A self-report value then
carries its coarsening, so downstream code can treat it as interval-censored, not
a point. Folds into the metric_registry design (part of ADR-0002's registry or a
small **ADR-0018**). Mine to specify; no ruling needed.

---

## DECISION 5 — VALID TIME AS A RANGE TYPE  ▶ NEEDS JOE'S RULING

**Claim.** Model `occurred_at` as `tstzrange` with a GiST index, not two scalars.
PG19 adds native temporal PKs and FOR PORTION OF (GA ~Sept 2026), system
versioning is NOT in PG19, Supabase is PG17 — so roll our own transaction-time
regardless. Range choice costs nothing now and makes a future migration
mechanical. Consider Graphiti naming (valid_at/invalid_at, created_at/expired_at).

**Verification.**
- `tstzrange` + GiST + exclusion constraint for non-overlap: **VERIFIED**
  idiomatic Postgres; **`btree_gist` is installable on the live instance** (needed
  to combine a scalar equality with a range `&&` in one exclusion constraint).
- **PG18 vs PG19 — attribution correction:** temporal **PRIMARY KEY / UNIQUE
  (`WITHOUT OVERLAPS`)** and temporal **FK (`PERIOD`)** shipped in **PG18** (GA
  2025-09-25). PG19's temporal add is **`UPDATE/DELETE … FOR PORTION OF`**. **PG19
  is in beta (Beta 3, 2026-08-13), NOT GA**; GA is late-Sept/Oct 2026 and can
  slip. Do not attribute temporal PKs to PG19.
- System versioning not in PG19: **VERIFIED TRUE** (PG19 docs say emulate via
  triggers/extensions). Roll-our-own transaction time: correct.
- Supabase PG18/19 preview: none on mainline (only OrioleDB alpha, production-
  discouraged). `temporal_tables`/`periods` **absent on the live instance**
  (confirmed). So DIY is not a preference — it's the only option.

**▶ DISAGREE with the blanket form. Here is the precise proposal instead.**
`occurred_at` for a *point event* (a meal, a card swipe) is genuinely an instant;
ADR-0002 *already* encodes imprecision via `time_precision ∈ {exact, minute,
hour, day, unknown}`. Turning every `occurred_at` into `[t,t]` adds machinery and
buys nothing for point events, and it *duplicates* `time_precision`. Ranges earn
their keep in exactly two places:
1. **Durational facts** — a 45-min workout, an 8-hr sleep, a screen session — have
   a genuine *start and end*. Neither `occurred_at`+`time_precision` nor a single
   instant captures both. **This is the real gap.** Add a **`valid_interval
   tstzrange`** for durational atoms (NULL for point events).
2. **Belief validity over time (bitemporal valid-time)** — "home address was X
   from date A to date B." That is `valid_at / invalid_at`, distinct from
   *occurrence*. Most atoms don't need it; entities/states do.

For transaction time, ADR-0002 already has `recorded_at` + `supersedes`. Add
**`expired_at`** (when this row was superseded, NULL = currently-believed) so
"what did we believe on date D" is a single indexed range predicate rather than a
`supersedes`-chain walk. This is the mechanical-migration win, and it is cheap now.

**▶ UNPRICED and this is why it's your ruling — the 04:00 boundary breaks on a
range.** RULE-03 generates `subject_day` from `occurred_at` on a 04:00 local
boundary. A *durational* fact can **straddle 04:00** (a workout 03:30–04:30; sleep
always does). "Which subject_day does a range belong to?" has no free answer:
by-start, by-end, by-majority-overlap, or split-into-two are all defensible and
they change every daily aggregate. This **interacts directly with OQ-06** (still
open: is the boundary 04:00 at all?) and it is non-retrofittable. **I will not
decide this alone.**

**Recommendation (for your ruling):** adopt ranges *only* for durational/valid-
time facts (proposal above), keep instant+`time_precision` for point events, add
`expired_at` for transaction time. Then rule the straddle policy (I lean
**by-start**, matching how `occurred_at` already anchors a point event, with the
full `valid_interval` retained so overlap analyses are exact). Becomes an
amendment to ADR-0002 (proposed **ADR-0019**) once you rule.

---

## DECISION 6 — TRUST LEVEL AT INGEST

**Claim.** Every atom carries a trust level at ingest. Untrusted content (email
bodies, web text, PDFs, merchant strings) renders to the model as quoted *data*,
never instruction. Read-only, parameterised, schema-validated tools only — never
a generic `execute_sql`. No session that reads personal data also holds an egress
tool. (NSA MCP guidance U/OO/6030316-26, May 2026; lethal-trifecta framing.)

**Verification.**
- **Lethal trifecta** (Simon Willison, 2025-06-16): **VERIFIED verbatim** —
  private data + untrusted content + external communication; remove any one leg
  and the exploit breaks.
- **NSA CSI U/OO/6030316-26** "MCP: Security Design Considerations…" (May 2026):
  **SNIPPET-CONFIRMED, PRIMARY UNREACHABLE** — the media.defense.gov PDF returned
  403 to the verifier; the identifier, title, agency and date were corroborated
  from the URL string and a secondary summary, not read from the primary document.
  Reported recommendations: egress filtering/DLP, URL/method pinning, scanning tool
  results for indirect injection, sandboxing, signed/expiring messages, audit
  logging. (Companion: CISA-led "Careful Adoption of Agentic AI," 2026-05-01.)
  **Decision 6 does not depend on this citation being exact — it stands on the
  lethal-trifecta reasoning (Willison, VERIFIED verbatim) and OWASP LLM01/LLM06.**
  The label is downgraded; the decision is not.
- OWASP LLM Top-10 2025 **LLM01 (prompt injection)** and **LLM06 (excessive
  agency)**: **VERIFIED** support for quoted-data and no-generic-execute_sql.
- **▶ Mild overstatement:** the exact rules ("never `execute_sql`," "no session
  both reads private data and egresses") are *sound engineering inferences* from
  least-privilege + the trifecta — they are **not stated verbatim** in NSA/CISA/
  OWASP. Present them as our derived architecture, not as quoted guidance.

**Recommendation: ADOPT — this is the strongest single addition on the list.**
- `atoms` and `raw_captures`: add **`trust_level ∈ {trusted, untrusted}`** set at
  ingest. Anything authored by a third party (email body, web/PDF text, merchant
  string, model extraction over untrusted input) is `untrusted`.
- **Architecture rule (ratify):** a session/process that can read personal rows
  **must not** also hold an egress capability, and vice-versa — breaking one leg
  of the trifecta structurally, not by prompt. This is the row-level +
  process-level complement to RULE-29's egress *logging* and to OQ-15's
  forbidden-import lint. Touches RULE-29's territory; **30-rule cap holds** — this
  is a RULE-29 clarification + an ADR, not a new numbered rule.
- No generic `execute_sql` reaches a model; only parameterised, schema-validated,
  read-only RPCs.

Proposed **ADR-0020**. The `trust_level` column is non-retrofittable-cheap now,
expensive later — lock it into the atom this phase.

---

## DECISION 7 — ANALYTICAL STORE = PARQUET ON R2  ▶ ONE SEAM IS JOE'S RULING

**Claim.** Supabase Free is 500 MB (already ~222 MB); TimescaleDB deprecated on
Supabase; R2 Free is 10 GB, zero egress; DuckDB 1.5.5 / DuckLake 1.0 /
pg_ducklake 1.0 make Parquet-with-a-catalog a $0 pattern — but pg_duckdb/
pg_ducklake **cannot** be installed on hosted Supabase, so DuckDB lives in the
Actions runner. Postgres holds operational state; Parquet on R2 is the analytical
system of record.

**Verification.**
- Supabase Free **500 MB → read-only** at the limit; **7-day inactivity → project
  pause**: **VERIFIED**. Live is **197 MB measured this session** (your ~222 MB
  was an earlier estimate, not a second measurement; the 197 MB is the
  point-in-time query result and is the figure to use). ~40% of the ceiling is
  gone before the new schema exists — the premise is sound.
- TimescaleDB **deprecated on PG17 Supabase**: **VERIFIED** (and absent on the
  live instance).
- R2 Free **10 GB, zero egress, 1M Class-A + 10M Class-B ops/mo**: **VERIFIED**.
- DuckDB **1.5.5** current (DuckDB **2.0 in preview**, fall 2026); DuckLake and
  pg_ducklake **at/past 1.0**: **VERIFIED** (versions have short shelf life).
- **pg_duckdb/pg_ducklake absent on hosted Supabase: CONFIRMED on the live
  instance** (`pg_available_extensions` query). Note the *general* premise
  "managed can't run pg_duckdb" is false (Azure supports it) — but **Supabase
  specifically does not**, which is all that matters here.

**▶ UNPRICED #1 — the $0 guarantee's real leak is R2 Class-A operations.** Class-A
(writes/lists) is capped at **1M/month free**, then $4.50/M. A chatty writer —
many tiny Parquet files, frequent multipart parts, heavy `LIST` — is the single
most plausible way this quietly leaves $0. **Mitigation is a design rule now:**
batch and compact Parquet writes; no per-row PUTs; avoid `LIST`-heavy scans.

**▶ UNPRICED #2 — the system-of-record seam, and it is your ruling.** Calling
Parquet-on-R2 "the analytical system of record" while Postgres holds `atoms`
creates a **two-store consistency problem that INV-1 and RULE-12 must span**:
- If `atoms` live in Postgres and are *exported* to Parquet, the Parquet is a
  *derived copy* — fine, but then a finding computed by DuckDB **in the Actions
  runner** must write back to Postgres *with provenance and `code_version`*
  (RULE-12: compute once, one owner), and must still trace to a `raw_captures`
  row (INV-1) *across the store boundary*. That trace crossing two systems is the
  new failure surface.
- **Which store owns `atoms`?** If Postgres owns them and R2 is a read-optimised
  mirror, the mirror can go stale (RULE-04 point-in-time correctness must be
  computed on the *authoritative* store or on a snapshot with a known
  `recorded_at` cut). If R2 owns them, then the immutability/grant enforcement
  (RULE-02, ADR-0010 triggers) has no Postgres teeth on the authoritative copy.

**Recommendation:** Postgres remains the **authoritative** store for `atoms`,
`raw_captures`, `findings`, `ops.*` (that is where immutability, grants, and
point-in-time queries have teeth). R2/Parquet is the **analytical mirror +
scratch space** for the heavy statistical passes that would blow the 500 MB
ceiling or need columnar scans — computed in the runner via DuckDB, results
written *back* to Postgres with full provenance. That keeps one owner per number
and one trace to raw. **But confirm this is the seam you want** before I write it
into an ADR (proposed **ADR-0016** or a dedicated analytical-store ADR) — the
alternative (R2 authoritative, Postgres as a thin operational cache) is
defensible too and changes Phase 2's entire migration target.

---

## DECISION 8 — CAPTURE SCHEMA CONSEQUENCES

**Claim.** One record per model call (Apple on-device ~8k context); store raw
text alongside every extraction so we can re-extract when models improve; a
`capture_source` enum from day one including `notification_parse`; and a workout
dedup key `(source + start + duration)` because GymKit will duplicate Watch
workouts.

**Verification.**
- One-record-per-call + raw-text-alongside-extraction: already the spec (REQ-CAP-
  006/011/012, immutable `raw_captures.payload` with transcript retained). **Good,
  no change.** The re-extraction-when-models-improve path is exactly the
  `supersedes` mechanism.
- **Apple context "~8k": WRONG — it is 4,096 tokens** (Apple TN3193). The chunking
  constraint is *tighter*; a long untrusted email/PDF routed through the on-device
  model will silently truncate. **This compounds Decision 6:** long untrusted
  inputs both truncate *and* are the injection surface.
- **Dedup key `(source + start + duration)`: PARTLY WRONG** (correction #4). Cross-
  source duplicates (Watch vs GymKit machine) share the *activity*, not the
  *source*. Use identity `(start-window, duration-window)`; `source` is a
  priority tiebreaker, mirroring Apple's own overlap+priority resolution.
- `capture_source` enum incl. `notification_parse`: reasonable; the current enum
  is `{shortcut_voice, shortcut_photo, shortcut_text}`.

**Recommendation: ADOPT the intent, with the two corrections.** Extend the
`capture_source` enum from day one: add `notification_parse`, and reserve values
for the net-new feeds (`healthkit_workout`, `email_receipt`, `location`, …).
Workout dedup: identity on `(subject≈start-window, duration-window)` + source
priority. Fix any "8k" figure to **4,096**. Folds into reserved **ADR-0008**
(capture transport). Mine to specify.

**▶ UNPRICED — OQ-18 collides with the workout schema.** There is **no workout
history anywhere** (live `public.workouts` = 0 rows; July backup CSV empty), yet
strength is the stated objective function (Phase 6). Designing the workout dedup
key is right, but it is designing the plumbing for a feed **that does not yet
capture anything.** Whether workout capture exists at all is OQ-18, still open,
and it gates whether Phase 5/6 are measurable. Flagging, not deciding.

---

## DECISION 9 — HYPOTHESIS REGISTER (RULE-19)

**Claim.** RULE-19's amendment: the exploratory pass over two years runs once and
outputs a register of pre-registered hypotheses with adjustment sets, lags,
windows fixed. Design the registry table now.

**Verification / status.** The **table** is already fully specified.
`hypothesis_register` (REQ-INF-100 / 102 / 103, `:307-317`) carries `hypothesis_id,
exposure_metric, outcome_metric, lag_days, direction, transformation,
adjustment_set, test_statistic, preregistered_at, confirmation_data_from,
resolution_rule, status`, with a CHECK (`confirmation_data_from >=
preregistered_at`) and an UPDATE-rejecting trigger. RULE-19 amendment recorded in
ADR-0015. **Caveat (reviewer, this session):** the register *table* needs no new
work, but *how its rows are evaluated* changes under Decision 1 — REQ-INF-106's
BH becomes e-BH — so "no new work" is true of the schema, not of the evaluation
path. (Earlier draft over-cited the range as REQ-INF-100..114; 108-114 are
point-in-time/staleness/no-impute/snapshot requirements, unrelated to the register
columns.)

**Recommendation: NO NEW WORK.** The design is done. One belt-and-braces note for
Phase 2: stamp the exploratory-pass hypotheses with a provenance marker so the
CHECK constraint provably prevents confirming them on the same pre-existing data
they were mined from. No new ADR.

---

## WHAT I WOULD BUILD FIRST, AND WHAT I WOULD DEFER

**Build first — the spine, in this order (all non-retrofittable, everything hangs
off them):**
1. **`atoms`** — with the corrected temporal model (instant + `time_precision`
   for points; `valid_interval tstzrange` for durational; `expired_at` for
   transaction time), three-valued `presence`, `trust_level`, interval value +
   `estimate_method`, `state_class`, full provenance. **Blocked on two rulings:
   OQ-06 (04:00) and Decision 5 (range + straddle policy).**
2. **`raw_captures`** — with the extended `capture_source` enum and `trust_level`;
   immutability enforced by the ADR-0010 mutation-rejecting trigger (not just
   absent grants), with the connecting DB role decided explicitly.
3. **`metric_registry`** — with scale/rounding metadata (Decision 4).
4. **`ops.runs`, `ops.egress_log`, `ops.job_registry`** — and the two keepalives
   that close Gate 0.

**Lock the shape now, wire the compute later (cheap now, migration-over-history
later):**
- `findings.e_value` + sufficient-stats columns (Decision 1) — compute in Phase 6.
- `predictions.forecast_distribution` + CRPS columns (Decision 2) — compute Phase 6.
- `prompt_dispatch` non-response table (Decision 3) — wire when prompts exist (Phase 3+).
- `hypothesis_register` (Decision 9) — table + constraints now; the exploratory
  pass runs in Phase 6.

**Defer (not this phase):**
- **Analytical store on R2/DuckDB (Decision 7)** — needs the seam ruling; it does
  *not* block the operational spine, and premature R2 wiring adds a consistency
  surface before there is anything to analyse. Build after the spine exists and
  the 500 MB ceiling is actually in sight.
- Any scoring/FDR *computation* — Phases 5/6.

**Genuine rulings I need from you (I will not decide these alone):**
- **A · OQ-06** — is the subject-day boundary 04:00? Blocks `atoms`.
- **B · Decision 5** — adopt ranges only for durational/valid-time facts (my
  recommendation) vs blanket `tstzrange` vs scalars-only; and the 04:00-straddle
  policy (I lean by-start). Non-retrofittable.
- **C · Decision 7** — is Postgres authoritative and R2 the analytical mirror (my
  recommendation), or R2 authoritative? Changes Phase 2's migration target.
- **D · Decision 1** — accept the power cost of e-values as the price of
  anytime-valid peeking (I recommend yes, given how you use the system)?
- **E · Decision 6** — ratify "no session both reads personal data and holds an
  egress tool" as a structural rule (RULE-29 clarification + ADR, cap holds)?

## WHAT I DID NOT DO

- **Did not write any migration SQL or execute anything** — by instruction; this
  is the plan only.
- **Did not write the nine ADRs as standalone files.** They are recorded here as
  *proposed* decision-records. **Corrected numbering (reviewer, this session):**
  ADR-0007 e-values/multiplicity · ADR-0008 capture transport + dedup · **ADR-0016
  analytical store (R2)** · ADR-0017 non-response/`prompt_dispatch` · ADR-0018
  metric-registry scale/rounding metadata · ADR-0019 temporal amendment to
  ADR-0002 · ADR-0020 trust/egress · **ADR-0021 distributional forecasts** (0021
  splits the forecasts ADR out of the analytical-store one — an earlier draft
  double-booked 0016 for both). These numbers are now **reserved in DECISIONS.md**
  this session (previously the plan said "reserved" while DECISIONS.md did not
  hold them — corrected). Promoting them to standalone files is the next session's
  work — deliberately deferred because five of the nine carry
  decisions that are **Joe's to rule** (A–E above), and writing an ADR that
  pre-decides his ruling is exactly the "just decide" failure CLAUDE.md rule 5 and
  the advisor stance forbid. The repo's own convention (ADR-0015 recorded Gate-1
  rulings *after* Joe ruled) is followed here.
- **Did not independently re-run the external experiments** (e-BH proofs, JMIR
  joint model, Apple TN3193) — verified the *citations and claims* against primary
  sources; did not reproduce the science.
- **Did not paste every primary-source URL into this plan.** The full source URLs
  for all nine verifications live in this session's three verification reports (in
  the transcript), not inline here — so a reader of this file alone cannot click
  through to check each one. Also: the version/licence facts (`scoringrules`
  0.11.0 / Apache-2.0, `online-fdr` BSD-3 / beta, DuckDB 1.5.5) have a **short
  shelf life** and must be re-verified against PyPI/releases at the moment a
  dependency ADR (RULE-28) is written, not trusted from this snapshot.
- **Did not resolve OQ-06 or OQ-18** — surfaced their collision with Decisions 5
  and 8; both remain Joe's.
- **Did not verify the `online-fdr` / `scoringrules` free-tier/licence fit against
  RULE-28** beyond noting licences (BSD-3 / Apache-2.0) and that both are pip/$0
  with no service limit — a full dependency ADR is owed before either is added.
- **Did not price the two-store migration** (Postgres↔R2) in rows or ops/month —
  that costing is owed with the Decision-7 ruling.

---

## DIRECTOR RULINGS — 2026-08-23 (settled; ADRs written next session)

Joe ruled on all five open questions and accepted all four corrections. These are
the settled inputs for next session's migrations and ADRs. ADR numbers as reserved
in the plan above.

**Corrections — all four ACCEPTED.**
1. p-value→e-value conversion **is** possible via a calibrator (`e = k·p^(k−1)`);
   the cost is **power loss, not impossibility**. The ADR (ADR-0007) must state the
   reason correctly: **we store native e-values because calibration is lossy**, not
   because conversion is impossible.
2. `arXiv:2502.08539` is **cautionary**; cite it only as *"conditions under which
   stopped e-BH is valid."*
3. Apple on-device context is **4,096 tokens**.
4. Workout dedup identity is **(start-window, duration-window)** with **source as
   tiebreaker**, never source-first.

**A · OQ-06 — RESOLVED.** Subject-day boundary is **04:00 local**. Assignment
**by start instant**, with **sleep attributed to the day it ENDS** (wake date;
sleep-research convention and how Joe speaks of it). `subject_day` is **stored
explicitly with a `rule_version`** so the rule is versioned and a future change is
visible, not silent. → amends RULE-03 / ADR-0002.

**B · Decision 5 — RULED as recommended.** Instant + `time_precision` for point
events; `valid_interval tstzrange` **only** for genuinely durational atoms
(workout, sleep, screen session); `expired_at` added for transaction time.
Straddle policy: **by-start, EXCEPT sleep attributed to the wake day** (per A —
Joe added the sleep carve-out that the body recommendation, which said plain
by-start, did not contain). → ADR-0019 (amends ADR-0002, incl. `subject_day`
changing from a *generated* column to an application-computed *stored* column with
`rule_version`, since a generated expression cannot encode "by-start except sleep
by end").

**C · Decision 7 — RULED as recommended.** **Postgres authoritative**; R2/Parquet
is the analytical mirror + scratch, results written back with provenance
(preserves INV-1 and RULE-12 within one enforceable store). **New consequence
opened as OQ-20**: Postgres Free is 500 MB, `atoms` are append-only (RULE-02, so
no delete escape hatch) — the fill-behaviour options memo is owed **before** the
wall. → ADR-0016 (analytical store) must reference OQ-20.

**D · Decision 1 — ACCEPTED as a trade, not an upgrade.** Joe peeks constantly, so
anytime-validity is worth real power to him. ADR-0007 records it explicitly as a
**power-for-anytime-validity trade**.

**E · Decision 6 — RATIFIED** as a **RULE-29 clarification + ADR-0020**, no new
numbered rule (30-cap holds): a session that reads personal rows must not also
hold an egress capability, and vice-versa; `trust_level` on `atoms`/`raw_captures`;
no generic `execute_sql` reaches a model.

**OQ-18 — Joe's directive.** Manual interim workout capture starts **this week**
to start the clock; the real feed is Phase 3/4 net-new work. Interim
recommendation recorded in `ops/PROGRESS.md` this session.
