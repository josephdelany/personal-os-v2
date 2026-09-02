# ADR-0048: The watch resolver — a frozen rule, evaluated on post-registration days only, resolving to PROMOTED / REFUTED with an append-only ledger

## Status
Accepted. Migration 0042 applied live 2026-09-02 (session 19); amended the same day with the two-look
ruling (§12, migration 0043).

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

12. **Two looks only (Joe's ruling, 2026-09-02, OQ-44(d): "YES, the reviewer's recommendation";
    migration 0043).** A watch is tested on the first night it has ≥ 30 paired post-registration
    days (look 1) and once more when it has ≥ 120 (look 2), never on the nights between. Every
    look writes a ledger row (`look` 1 or 2), so a look is never repeated and the ledger is the
    schedule. At each look the Kish effective sample size `n_eff = post_days·(1−ρ)/(1+ρ)` (ρ =
    the outcome's lag-1 autocorrelation from `_contrast`, deflating only) is stored with ρ and
    gated at `N_EFF_MIN = 20` — REQ-TIER-017's floor, itself a placeholder (OQ-10) — giving
    `insufficient_low_n_eff`. Look 1 with q ≥ 0.10 records `insufficient_sign_unstable` (the
    sign is not established at this look) and waits; look 2 with no decision, or a first look
    already past day 120, or a window that never fills within 120 calendar days, expires. With
    ~30 paired days and ρ ≈ 0.5 the gate blocks look 1 (n_eff ≈ 10), so on autocorrelated
    metrics the first real test is at day 120 with n_eff ≈ 40 — by design, not by accident.
    `get_findings.watching` reports `looks_done`; `history` reports `look` and `n_eff` (RULE-21).

## Statistical defect — ruled and fixed the same day (reviewer #1/#2 → §12)
Evaluating the rule **every night** from day 30 is optional stopping. The reviewer replayed the
resolver's own functions on null series: P(resolve | one look at day 30) ≈ 0.14 iid / 0.20 at
ρ=0.5; P(resolve on some night, days 30–120) ≈ 0.58 iid / 0.74 at ρ=0.5 / 0.86 at ρ=0.7 —
about half of those in the registered direction. The weekday demedian on a 30-day window
(4–5 points per weekday) and the absence of any n_eff / HAC adjustment add to it. Nothing
matures before ~2 October. Joe ruled the reviewer's recommendation: one look at the first night
with ≥30 paired days and one last look at day 120, with Kish `n_eff` stored and gated (§12).
**What two looks actually buy (second review, same day, executed replay on AR(1) nulls, 4000
trials per cell): P(false resolution over both looks) ≈ 0.19–0.21 at every ρ from 0 to 0.7** —
down from 0.58–0.86 under nightly re-testing, but not the 0.10 the frozen sentence implies,
because (a) with watches registered on different days the BH family is almost always one, so
q = p; (b) `n_eff` is gated but never deflates p; (c) the gate at ρ = 0.7 blocks look 1 and
passes look 2 (n_eff 21.2), moving the false positives rather than removing them. Which fix —
accept ~0.20 (half of it PROMOTED, then facing the forward prediction), tighten new
registrations' rule text to q < 0.05, or deflate p by n_eff — is Joe's ruling, OQ-44(i).

13. **Second-review fixes (same day, migration 0044).** A degenerate contrast (`_contrast`
    returns None: an exposure with no spread) is *not a test*: no p, no look consumed, nothing
    written; the watch is re-checked nightly until testable or the calendar expires it — the
    earlier code burned look 1 and wrote a false `insufficient_low_n_eff`. The calendar expiry
    (120 days without reaching the next look) now applies after look 1 as well, so a watch whose
    data stops after its first look expires instead of waiting forever. `n_eff` and ρ are computed
    from the paired outcome series whether or not a contrast exists, so no ledger row reports
    `post_days` without `n_eff` (RULE-21). `get_findings`: `looks_done` = max(`look`) from the
    ledger (one definition); a PROMOTED watch leaves `watching` (which is now status
    INSUFFICIENT only) and appears in a new `promoted` list carrying the note that it is not a
    causal claim; `days_needed` is the paired days to the *next* look (30, then 120); a watch on
    the clock carries `insufficiency_reason: window_too_short` (REQ-INF-107); `history` rows carry
    `status_changed`. **`n_eff` is on the paired-day count, not the per-side count the scan
    deflates** (the scan's `n_eff_hi` on 30 paired days is ~8; the resolver's is ~30): the same
    floor of 20 applied to quantities that differ by ~4×. Stated here, not silently; which `n`
    REQ-TIER-017's floor governs is OQ-44(h). Two test assertions loosened to `>=` in session 19's
    first commit were re-pinned to exact values.

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
