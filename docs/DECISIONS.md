# DECISIONS — ADR index

One line per decision. Read the full ADR before changing anything it covers.
ADRs are immutable: a superseded decision is marked superseded and kept, never
edited and never deleted, because the reason it was made is the thing worth
preserving.

| ID | Status | Date | Decision |
|---|---|---|---|
| ADR-0001 | Accepted | 2026-08-06 | Compute placement — three tiers, one owner per number, model plans and narrates but never computes |
| ADR-0002 | Accepted | 2026-08-06 | The atom — bitemporal, three-valued presence, interval-valued, `state_class` in the schema |
| ADR-0004 | Accepted | 2026-08-23 | Entity/link **table shape only** — bitemporal, provenance, `corrected_by_human` (RULE-10); `entity_type` open TEXT pending the ontology spec (OQ-16); in `core` schema (never touches old `public.entities`). Resolution algorithm (blocking keys, thresholds, review queue) deferred to Phase 4 |
| ADR-0005 | Stub | 2026-08-15 | Nutrition resolution — **stub**: records only the `weighed` interval width (±10%, equal to `labelled`, provisional; distinct method kept for calibration). Cache-first lookup, portion table, and remaining widths still to be authored before Phase 3 |
| ADR-0007 | Accepted | 2026-08-23 | Multiplicity — store native **e-values** (`e_value`, `e_value_method`, `e_process_params`, `family_size`) as the family-wide FDR currency; **e-BH replaces BH-on-p** (amends RULE-21 + REQ-INF-106). A **power-for-anytime-validity trade** (Joe peeks constantly), not a strict upgrade. Corrections: p→e conversion *is* possible but lossy; arXiv:2502.08539 is cautionary. Compute is Phase 6; `online-fdr` needs a RULE-28 dep-ADR |
| ADR-0008 | Accepted | 2026-08-23 | Capture **schema** — extended `capture_source` enum (spec's 4 + `notification_parse` + reserved `healthkit_workout`/`email_receipt`/`location`); workout dedup identity `(start-window, duration-window)` + source **tiebreaker** (not source-first); Apple on-device context **4,096** tokens. Transport contract deferred to Phase 3. OQ-18 collision flagged (no workout data exists yet) |
| ADR-0010 | Accepted | 2026-08-23 | RULE-02 enforcement — append-only by **grant REVOKE** (app roles) **and trigger** (catches even the owner, whose implicit grant is unrevocable). The literal RULE-02 CI query counts the owner self-grant so can never return 0; the CI check is **scoped to app roles** per REQ-CAP-012 — a correction, not a weakening (RULE-00), **flagged for Joe's ratification + a constitution-text update**. Behavioural proof needs no fabricated row (permission denied on empty table) |
| ADR-0011 | Accepted | 2026-08-23 | `features.json` write-lock — agent denied Edit/Write on the ledger at the permission level so it cannot mark its own work passing (verified: an Edit on the file is rejected by the permission engine). The sanctioned writer that flips an entry only on proven pytest output is deferred to Phase 3, authored with the first proving test |
| ADR-0012 | Accepted | 2026-08-23 | ETL database TLS posture — all DB access via `lib/db.py`, TLS verified against the pinned `Supabase Root 2021 CA` (`lib/certs/`, proven to anchor the live chain), `CERT_REQUIRED` + hostname check, only `VERIFY_X509_STRICT` cleared (Supabase *intermediate/leaf* omit `keyUsage`; the root carries it). CERT_NONE considered and rejected. Credential from env only. Pinned root expires 2031-04-26 |
| ADR-0013 | Accepted | 2026-08-23 | Repository is **public** (unmetered Actions for the statistical layer) named `personal-os`; resolves OQ-03/OQ-02. No personal data ever tracked in git — every data path gitignored by default, a tracked `.parquet`/`.csv`/`.db`/`.sqlite` fails CI (RULE-29 strengthened, no new rule; cap held). Dead credential scrubbed from all history 2026-08-23 via git filter-repo, verified absent from every object (see ADR-0013 addendum; all commit hashes changed as a result) |
| ADR-0014 | Accepted | 2026-08-23 | Phase-1 research corrections — RULE-11 PHIA numbers refined to 22%→74%→84% (Gemini 1.0 Ultra main results, unreplicated; conclusion unchanged); RULE-17 causal-discovery distrust strengthened with CausalDynamics (PCMCI+ **at chance** on simple systems, AUROC ~0.52); **new RULE-13** "the model never selects the temporal specification" (HEARTS, ICML 2026), retiring the former RULE-13 into RULE-14 to hold the 30-cap. *Citations re-verified 2026-08-23, see addendum.* |
| ADR-0015 | Accepted | 2026-08-23 | Phase-1 constitution ratification (Gate 1) — all 31 rules reviewed and **kept**; reversals RULE-18/23/30 affirmed explicitly; RULE-19 amended (one-time early exploratory pre-registration pass, waiting clock starts day one); RULE-30 amended (revisit trigger if iOS/WebKit ships persistent PWA media grants; rationale strengthened — on-device Foundation Model + SpeechTranscriber (wins on *accuracy*) make Shortcuts capture free/private/offline/better). *WebKit 215884 citation removed as a misattribution 2026-08-23.* |
| ADR-0016 | Accepted | 2026-08-23 | Analytical store — **Postgres authoritative** (`atoms`/`raw_captures`/`findings`/`ops.*`); Parquet-on-R2 the analytical mirror + scratch, DuckDB in the Actions runner (hosted Supabase cannot run pg_duckdb/pg_ducklake); results written back with provenance (INV-1/RULE-12 stay in one enforceable store). **No R2 code this phase.** R2 Class-A ops are the real $0 leak → batch/compact writes. References **OQ-20** (500 MB fill; append-only means no delete escape hatch) |
| ADR-0017 | Accepted | 2026-08-23 | Non-response is a row — `core.prompt_dispatch`, one row per prompt **issued**; `response_state ∈ {pending, answered, seen_declined, delivered_unseen, partial, expired}`; `never_scheduled` = absence of a row. Distinct axis from RULE-07 presence. JMIR e65350 **snippet-confirmed, primary unreachable**; decision stands on its own reasoning. Wired Phase 3+ |
| ADR-0018 | Accepted | 2026-08-23 | Metric-registry scale/rounding metadata — `self_report`, `response_scale`, `n_scale_points`, `rounding_step` per variable, so self-reports are stored as coarsened interval data (arXiv:2501.10726, a GMM paper; schema-as-metadata is our extrapolation, not the paper's claim) |
| ADR-0019 | Accepted | 2026-08-23 | Temporal amendment to ADR-0002 — instant + `time_precision` for points, `valid_interval tstzrange` for durational atoms; `subject_day` moves from *generated* to application-computed **stored** with `rule_version` (04:00 local, by start instant, **sleep by wake day**). Amends RULE-03. Resolves OQ-06. **Implementation correction, ratified by Joe 2026-08-23: transaction time is `recorded_at` (system-set at INSERT via trigger) + currency DERIVED from `supersedes` (`atoms_current` view), NOT a stored `expired_at` — a stored expiry needs an UPDATE that INV-2 forbids; the invariant wins.** |
| ADR-0020 | Accepted | 2026-08-23 | Trust/egress — `trust_level ∈ {trusted, untrusted}` on `atoms`/`raw_captures` at ingest; a session that reads personal rows holds no egress capability (and vice-versa); no generic `execute_sql` reaches a model. RULE-29 clarification, no new numbered rule (30-cap holds). NSA CSI **snippet-confirmed, primary unreachable**; decision rests on the verified lethal-trifecta + OWASP LLM01/LLM06 |
| ADR-0021 | Accepted | 2026-08-23 | Distributional forecasts — continuous predictions store `forecast_distribution` (quantiles/samples) + `dist_family`/`issued_at`/`horizon`/`crps`/`log_score_cont`; binary path (`p_forecast`/`brier`/`log_score`) kept (log score is infinite for a point mass, so no unified column). Extends RULE-20. Split from ADR-0016. Scoring compute is Phase 6 |

## Awaiting authorship

These are decisions already implied by the requirements and not yet written up.
Each must exist before the code it governs is written.

| ID | Decision to record |
|---|---|
| ADR-0003 | Evidence ladder — six tiers, permitted vocabulary per tier, promotion and demotion rules |
| ADR-0006 | Transaction ingestion — CSV/QFX plus Gmail parsing, `occurred_at` vs `posted_at`, dedupe key |
| ADR-0009 | Design tokens and honesty grammar — ⚠️ "carried forward from the archived UI system" premise is **void** (that archive was lost, OQ-19); must be **re-derived**, and this row re-scoped, at Phase 7 |

*Authored 2026-08-23 (Phase-2 session 2), moved to the accepted table above:
ADR-0004, 0007, 0008, 0010, 0016, 0017, 0018, 0019, 0020, 0021. ADR-0004 and
ADR-0008 were authored **partially** — ADR-0004 is the entity/link table shape
only (resolution algorithm still Phase 4); ADR-0008 is the capture schema only
(transport contract still Phase 3) — so each retains owed scope named in its file.*

**Note — ADR-0005 is a stub, not unwritten.** Its `weighed`-width decision is
written and accepted (see the top table and `docs/adr/0005-nutrition-resolution.md`).
Its remaining scope is still owed before Phase 3 and is deliberately kept out of
the table above so no row's status is self-contradictory: cache-first USDA
lookup, the personal portion table, the other method widths, and the count→grams
rule for branded items (REQ-NUT-050/051).
