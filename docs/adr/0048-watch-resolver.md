# ADR-0048: The watch resolver — a frozen rule, evaluated nightly on post-registration days only, with an append-only ledger

## Status
Accepted (code and tests merged; the live apply of migration 0042 was held by the auto-mode
classifier on 2026-09-02 — see PROGRESS session 18 for the two commands that finish it)

## Date
2026-09-02

## Context
`register_watch` (migration 0031, ADR-0038) inserts a pre-registered `watch:` row at
`INSUFFICIENT` and starts a 30-day clock. Nothing ever re-tested it: the ladder stopped at
WATCHING forever and the system could not establish anything. 0031 promised "E11 (weekly)
later resolves it". This is E11, built under `docs/build/B7_resolve_watches.md`.

## Decision
`tools/engines/resolve.py` (`resolve-v1`), run nightly by `tools/run_resolve.py` from
`.github/workflows/analysis.yml` after the panel refresh and before the Monday scan
(a watch crossing 30 days resolves the next morning, not the next Monday).

1. **The frozen `resolution_rule` sentence is implemented literally and never reinterpreted
   per row**: "median delta same sign with q<0.10 on >=30 post-registration days".
   `MIN_POST_DAYS = 30` and `Q_CONFIRM = 0.10` come from that text (RULE-13: registry data,
   not a model choice).
2. **Only days strictly after `confirmation_data_from` and not after today are read**
   (REQ-INF-107 / REQ-INF-104); the weekday demedian is computed on that window alone, so a
   pre-registration value cannot leak in through the baseline. Proven by a test whose 200
   pre-registration days carry the opposite sign in bulk.
3. **One owner for the statistics (RULE-11/12).** The resolver imports the scan's
   `_contrast`, `_mann_whitney_p`, `_dow_demedian`, `_load_panel`, `_median`, `_lag1_rho`
   and BH from `tools/engines/scan.py`; nothing is copied. Two additive changes to the scan:
   `_contrast(..., min_side=None)` and `_load_panel(cur, schema="analysis")` (defaults
   unchanged), and the nested `bh()` hoisted to module-level `_bh` (identical code). A test
   asserts function identity.
4. **`MIN_SIDE = 7`** per quartile side on the short window. The scan's 30 is a floor for
   7-year sweeps; on a 30-day window a quartile holds ~8 days, so 30 would never resolve.
   Provisional; REQ-TIER-017's `n_eff` floor of 20 is itself a placeholder (spec §A).
5. **`EXPIRE_DAYS = 120`**: a watch with no decision after 120 post-registration days
   becomes `INSUFFICIENT` with reason `expired_no_decision_120d`. Without it a watch that is
   never significant is WATCHING forever. The status CHECK has no `EXPIRED` value, so the
   ledger row is what closes it: the resolver skips watches that carry an expiry row
   (found by the test — otherwise it re-expired nightly), and `get_findings` moves them from
   `watching` to `insufficient` with the reason.
6. **q is Benjamini-Hochberg across the watches evaluated in one run**, not the scan's
   two-level tree FDR: the batch is a handful of human-chosen watches, not a sweep.
7. **`core.hypothesis_resolutions`** (migration 0042) records every status change: from,
   to, a closed-set reason, `post_days`, the contrast that decided it, both directions,
   `code_version`. Append-only via the 0012 statement-level trigger (owner included),
   RLS on, app roles revoked. `get_findings` gains `history` (last 50, tier + trace) —
   additive, nothing renamed (REQ-TIER-043).
8. **The register UPDATE sets `status` only**; the 0012 freeze trigger rejects anything else
   (REQ-INF-103). Tested both ways.
9. **B7's predictions insert was changed to fit the live schema and REQ-INF-301.** As
   written (`resolves_at = now()`, `outcome_bool` set, no `p_forecast`) it violates two
   CHECKs on `core.predictions` (`resolves_at > created_at`; exactly one of `p_forecast` /
   `forecast_distribution`) and is a record, not a forward prediction. Instead, **a CONFIRMED
   assignment inserts one forward prediction in the same transaction** (REQ-INF-301 names
   PROMOTED / CONFIRMED / EXPERIMENTAL; REFUTED and expired rows get the ledger row only):
   claim = the registered sentence on the next 30 days, `resolution_rule` = the frozen text,
   `resolves_at` = now + 30 days, `evidence_tier` = `CONFIRMED_OBSERVATIONAL`,
   `model_version` = `resolve-v1`, **`p_forecast` = 1 − Q_CONFIRM = 0.90** — the bound the
   rule itself licenses, never `1 − q` (which would overstate and make one failure's log
   score unbounded). `feature_snapshot_hash` carries the confirming q. It appears in
   `predictions_pending` until a later build scores it (OQ-44).
10. **Nothing computes an E-value or a negative control.** A CONFIRMED row is observational;
    `get_findings` keeps those keys absent and the UI says so (ADR-0047).

## Consequences
- The ladder can climb: a 30-day watch becomes CONFIRMED_OBSERVATIONAL or REFUTED the morning
  after it matures, by a deterministic rule Joe registered before the data existed.
- Every demotion or resolution is a named ledger row with its reason (REQ-TIER-043) and is
  never edited.
- The ledger's reason vocabulary is B7's closed set, not REQ-TIER-018's `insufficiency_reason`
  set; the mapping is open (OQ-44).
- No rolling re-confirmation: a CONFIRMED row stays CONFIRMED until a later build re-tests it
  or scores its forward prediction (RULE-20's demotion path is not wired yet — OQ-44).

## Not built
Scoring of `resolve-v1` predictions; re-confirmation; E-value / negative control;
`insufficient_sign_unstable` / `insufficient_low_n_eff` ledger rows (the resolver keeps
watching in those states rather than recording them); PROMOTED as an intermediate status.
