# B17 — Finance as a full system (migrations 0055–0057)

**What this is.** `specs/03-finance/requirements.md` §A.2 (Gmail alert and receipt
parsing), §C (necessity inference and the recurrence engine), §D.2–D.3 (link evidence
tiers; recommend with disclosed uncertainty — reuses B10), §E (presentation restraint),
§G (income, balances, budgets, forecast, reconciliation). §A.1/A.4 arrived with B13,
§B with B14. Three sessions: B17.1 recurrence + necessity, B17.2 Gmail, B17.3 the
full-system layers + `get_domain('money')` upgraded. ADR-0031 stands: net worth and
investments out of scope; no live counters; $0.

**Requirement IDs satisfied:** every REQ-FIN ID in the sections named (quote the full
list per session; §H traceability table updated). **ADRs:** ADR-0065 (recurrence engine
as built), ADR-0066 (Gmail via Apps Script — see below), ADR-0067 (balances and
reconciliation from ingested data only).

## B17.1 — Recurrence and necessity (migration 0055)
- `analysis.recurring_streams (stream_id, merchant_entity_id, category, cadence_days,
  mad_days, median_amount, mad_amount, n, first_at, last_at, status
  ('early_detection'|'active'|'lapsed'|'ended'), necessity_tier, changepoints jsonb,
  code_version, computed_at)` — rebuilt nightly by `tools/engines/recurrence.py` using
  **median interval and MAD** (REQ-FIN-133; never mean/sd), `early_detection` at 2
  occurrences (REQ-FIN-131), status thresholds per REQ-FIN-137, exclusions per
  REQ-FIN-139 (groceries, fuel, coffee, bars route to frequency analysis, not
  subscriptions), changepoint detection on the amount series per REQ-FIN-135 (PELT via
  `ruptures` is free; or the binary-segmentation the scan already has — one owner),
  dormant-while-active detection per REQ-FIN-155 (90 days without related app/site/email
  activity → a `brief_notes` notice, never an action).
- Necessity (§C.1–C.2): a **tier**, not a fact — `necessity_tier` ∈ the closed set the
  spec defines, inferred only from the signals §C.2 lists as inferable, defaulting to
  `unknown`, overridable by Joe via `public.set_necessity(p_stream_id, p_tier)` (a
  superseding row, RULE-10). The interventions of §C.4 are recommendations through B10
  (kind `standing_order` with the finance conditions), never automatic.
- Tests: `test_REQ_FIN_133_median_mad_not_mean_sd`, `test_REQ_FIN_131_early_detection_at_two`,
  `test_REQ_FIN_137_status_transitions`, `test_REQ_FIN_139_exclusions_route_to_frequency`,
  `test_REQ_FIN_135_changepoint_creates_note_with_before_after`, `test_REQ_FIN_155_dormant_active_notice`,
  `test_REQ_FIN_C1_necessity_is_a_tier_defaulting_unknown`.

## B17.2 — Gmail alerts and receipts (migration 0056; ADR-0066)
$0 and hands-off: a **Google Apps Script** bound to Joe's Gmail (free, runs on Google's
side on a time trigger every 15 min) that searches the labels/queries §A.2 names
(bank alerts, receipts), extracts the fields §A.2 lists with the regexes the spec
gives (add Joe's actual bank's alert format from a DISCOVER: Joe forwards one alert
to himself and pastes the *shape* — never amounts — into the session), and POSTs to
`ingest_capture` with `p_source='email_receipt'` (enum already reserved; grant EXECUTE for
that source on the same write-only path; `trust_level='untrusted'` per ADR-0020 — the
email body is third-party content and reaches any model only quoted). The extractor
gains an `email_receipt` branch → `transaction` atoms with `posted_at`/`occurred_at`
(§A.4), deduped against bank-import atoms by (amount, merchant-normalised, ±3 days) —
the receipt enriches (line items → `consume` atoms via B12 when food), it never
double-counts. Apps Script source lives in `tools/gmail/Code.gs` in the repo; Joe
installs it once (script.new → paste → set trigger); the anon key it needs is already
public by design (ADR-0034).
- Tests: `test_REQ_FIN_A2_receipt_regex_fixtures`, `test_REQ_FIN_A4_receipt_dedupes_against_bank_import`,
  `test_ADR_0020_email_receipt_is_untrusted_and_quoted`, `test_ADR_0066_line_items_become_consume_atoms_via_B12`.

## B17.3 — Income, balances, budgets, forecast, reconciliation (migration 0057; ADR-0067)
- Income (§G.1): direction-marked `transaction` atoms; P2P netting per REQ-FIN-049/260;
  income streams through the recurrence engine (REQ-FIN-261).
- Balances (§G.2): `analysis.account_positions (account, as_of, balance_lo, balance_mid,
  balance_hi, coverage, code_version)` derived nightly from ingested transactions plus
  any Joe-entered anchor balance (`public.set_balance_anchor(p_account, p_as_of,
  p_balance)` — the one human input; without an anchor the position is a *change since
  first import*, labelled as such per REQ-FIN-263). Never a live counter (REQ-FIN-210).
- Budgets (§G.3): `config.budgets (category, monthly_target)` **Joe-set only** (the
  ADR must record the ruling: no suggested budgets — RULE-23); presented retrospectively
  or as a range (REQ-FIN-214).
- Forecast (§G.4): committed + expected outflows for the next 30/60/90 days from active
  streams, as a range ≥ 20 % wide (REQ-FIN-265/212).
- Reconciliation (§G.5): per-period reconciliation flags in `analysis.reconciliation
  (period, account, ingested_sum, anchor_delta, gap, flagged)`; flagged periods surface in
  RELIABILITY and in `get_domain('money')` coverage.
- `get_domain('money')` gains modules: `recurring:[{merchant, cadence_days, median_amount,
  status, necessity_tier, next_expected}]`, `income:[...]`, `position:{as_of, lo, mid, hi,
  coverage, note}`, `budget:[{category, target, actual_range, month}]`, `forecast_outflows:
  {d30:[lo,hi], d60:[lo,hi], d90:[lo,hi]}`, `reconciliation:{flagged_periods}` — all
  additive. `get_period.money` gains `recurring_due` and `position`.
- Presentation restraint (§E) is enforced by tests over the envelopes: no field named
  `remaining`, `spent_so_far`, `on_track`; no point forecast; every balance carries `as_of`
  and `coverage`.
- Tests: `test_REQ_FIN_262_263_balance_is_as_of_and_labelled`, `test_REQ_FIN_210_no_live_counter_field_in_any_envelope`,
  `test_REQ_FIN_265_forecast_is_a_range_at_least_20pct_wide`, `test_REQ_FIN_264_budget_only_retrospective_or_range`,
  `test_REQ_FIN_266_unreconciled_period_is_flagged_and_surfaced`, `test_REQ_FIN_049_p2p_reimbursement_is_not_income`,
  plus the 12 finance Gherkin scenarios in §G as named tests (`test_FIN_SCENARIO_<n>_<slug>`).

## Done when (per session)
Migrations; nightly job wiring; the Apps Script installed by Joe and one real receipt
landed (counts only); envelopes pasted for `get_domain('money')`; all named tests; the
§H traceability table updated; ADR-0065/0066/0067; PROGRESS + WHAT I DID NOT DO
(net worth out of scope; cash spending unreconcilable; Joe's bank formats limited to
those discovered).
