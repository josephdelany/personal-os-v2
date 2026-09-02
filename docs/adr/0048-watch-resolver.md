# ADR-0048: The watch resolver — a frozen rule, evaluated on post-registration days only, resolving to PROMOTED / REFUTED with an append-only ledger

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
5. **`EXPIRE_DAYS = 120`**: a watch with no decision after 120 post-registration days —
   paired days, or calendar days since `confirmation_data_from` when the window never fills
   (a metric that left the panel; reviewer #10) — becomes `INSUFFICIENT` with reason
   `expired_no_decision_120d`. Without it a watch that is
   never significant is WATCHING forever. The status CHECK has no `EXPIRED` value, so the
   ledger row is what closes it: the resolver skips watches that carry an expiry row
   (found by the test — otherwise it re-expired nightly), and `get_findings` moves them from
   `watching` to `insufficient` with the reason.
6. **q is Benjamini-Hochberg across the watches evaluated in one run**, not the scan's
   two-level tree FDR: the batch is a handful of human-chosen watches, not a sweep. The
   family size is persisted per row as `family_m` (REQ-INF-106; reviewer #6) — with one
   watch in the batch, q is the raw p and the row says so.
7. **`core.hypothesis_resolutions`** (migration 0042) records every status change: from,
   to, a closed-set reason, `post_days`, the contrast that decided it, both directions,
   `code_version`. Append-only via the 0012 statement-level trigger (owner included),
   RLS on, app roles revoked. `get_findings` gains `history` (last 50, tier + trace) —
   additive, nothing renamed (REQ-TIER-043).
8. **The register UPDATE sets `status` only**; the 0012 freeze trigger rejects anything else
   (REQ-INF-103). Tested both ways.
9. **Amendment (same day, reviewer #5): the resolver assigns `PROMOTED`, not
   `CONFIRMED_OBSERVATIONAL`.** REQ-TIER-013 grants the causal tier only with a DAG-derived
   adjustment set, Newey–West HAC errors, an E-value at the point and the interval limit,
   negative controls and refutation tests — none of which exist — and REQ-TIER-021/032 let
   that tier unlock causal vocabulary downstream. Assigning it from one quartile contrast
   would be a weakened gate (RULE-00). A pre-registered contrast that survived on
   post-registration data is exactly what `PROMOTED` means, so that is what a watch becomes;
   the ledger reason is `promoted_same_sign_q_lt_0_10`; `PROMOTED` is final for resolve-v1
   (not re-tested), and `get_findings` keeps it under `watching` with `status: PROMOTED` —
   `confirmed` stays empty until the confirmation pipeline exists. B7 as written said
   CONFIRMED_OBSERVATIONAL; Joe may overrule (OQ-44).
10. **B7's predictions insert was changed to fit the live schema and REQ-INF-301.** As
   written (`resolves_at = now()`, `outcome_bool` set, no `p_forecast`) it violates two
   CHECKs on `core.predictions` (`resolves_at > created_at`; exactly one of `p_forecast` /
   `forecast_distribution`) and is a record, not a forward prediction. Instead, **a CONFIRMED
   assignment inserts one forward prediction in the same transaction** (REQ-INF-301 names
   PROMOTED / CONFIRMED / EXPERIMENTAL; REFUTED and expired rows get the ledger row only):
   claim = the registered sign on the next 30 days, `resolution_rule` = that same sign
   predicate (reviewer #7: the frozen q-gated text was a harder predicate than the claim),
   `resolves_at` = now + 30 days, `evidence_tier` = `PROMOTED`, `model_version` =
   `resolve-v1`, **`p_forecast` = 1 − Q_CONFIRM = 0.90** — a stated constant, not a calibrated
   probability (the reviewer is right that an FDR bound is a property of the rejection set,
   not of this claim's replication; kept because REQ-INF-301 requires a row and no
   calibrated number exists — OQ-44b), never `1 − q`. `feature_snapshot_hash` is a SHA-256 of
   the post-window (day, value) pairs that decided it (REQ-INF-307). It appears in
   `predictions_pending` until a later build scores it (OQ-44a); **RULE-20 is therefore not
   satisfied by this build** — a prediction is emitted, none is scored, nothing demotes.
11. **Nothing computes an E-value or a negative control.** A CONFIRMED row is observational;
    `get_findings` keeps those keys absent and the UI says so (ADR-0047).

## Known statistical defect, not fixed here (reviewer #1/#2 — Joe's ruling needed, OQ-44a)
Evaluating the rule **every night** from day 30 is optional stopping. The reviewer replayed the
resolver's own functions on null series: P(resolve | one look at day 30) ≈ 0.14 iid / 0.20 at
ρ=0.5; P(resolve on some night, days 30–120) ≈ 0.58 iid / 0.74 at ρ=0.5 / 0.86 at ρ=0.7 —
about half of those in the registered direction. The weekday demedian on a 30-day window
(4–5 points per weekday) and the absence of any n_eff / HAC adjustment add to it. Nothing
matures before ~2 October even if applied today, so the ruling can precede the first
resolution. Recommended: one look at the first night with ≥30 paired days, and one last look at
day 120, with `n_eff` (Kish, from the ρ `_contrast` already returns) stored and gated. The
frozen sentence "on >=30 post-registration days" does not say which reading was intended.

## Consequences
- The ladder can climb one rung: a 30-day watch becomes PROMOTED or REFUTED the morning after it
  matures, by a deterministic rule Joe registered before the data existed; CONFIRMED waits for
  the confirmation machinery.
- The resolver runs as its own workflow job, so a failure (0042 not applied) cannot block the
  Monday scan (reviewer #3).
- Every demotion or resolution is a named ledger row with its reason (REQ-TIER-043) and is
  never edited.
- The ledger's reason vocabulary is B7's closed set, not REQ-TIER-018's `insufficiency_reason`
  set; the mapping is open (OQ-44).
- No rolling re-confirmation: a CONFIRMED row stays CONFIRMED until a later build re-tests it
  or scores its forward prediction (RULE-20's demotion path is not wired yet — OQ-44).

## Not built
Scoring of `resolve-v1` predictions; re-confirmation; E-value / negative control; the
PROMOTED → CONFIRMED_OBSERVATIONAL step; `insufficient_sign_unstable` /
`insufficient_low_n_eff` ledger rows (never written; `low_n_eff` is a misnomer — no n_eff is
computed); `get_today.watching` / `get_trust.hypotheses.watching` still ignore resolution and
expiry (reviewer #8); the displayed "day N of 30" is calendar days while the gate is paired
days after `confirmation_data_from` plus lag (reviewer #9); `MIN_SIDE = 7` is inert at 30
pairs (quartile sides are ≥ 8 by construction; reviewer #11) and kept only as the stated
floor; REQ-INF-104's `ingested_at` clause and REQ-INF-108's point-in-time panel cannot be
honoured because `analysis.panel` has no `recorded_at` (reviewer #12); no `run_id` on the
ledger row (REQ-TIER-042).
