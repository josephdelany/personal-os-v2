# B7 — `tools/engines/resolve.py`: the job that lets a watch become CONFIRMED or REFUTED (migration 0042)

**Why this exists.** Today nothing resolves a watch. `register_watch` inserts a
pre-registered row (`status='INSUFFICIENT'`, clock starts), the app shows "day N of
30", and on day 31 nothing happens — no job re-runs the test on post-registration data.
The six-tier ladder therefore stops at WATCHING forever and the system never
*establishes* anything. This is the most important missing piece of the insight layer
and it is one session. `migrations/0031_patterns_watch_api.sql` line 15 promised it
("E11 (weekly) later resolves it"); this is E11.

**Requirement IDs satisfied:** REQ-INF-103 (only `status` changes; frozen columns
untouched — the trigger in 0012 enforces it), REQ-INF-107 (resolution only on data
recorded after `confirmation_data_from`), REQ-TIER-017/018 (INSUFFICIENT with a
machine-readable reason), REQ-TIER-043 (every demotion/resolution is recorded and
surfaced), RULE-11/12 (one owner, one `code_version`, deterministic), RULE-20 (a
resolution is a prediction that gets scored). **ADR to write:** ADR-0048.

## Step 0 — DISCOVER
```sql
SELECT hypothesis_id, status, preregistered_at::date, confirmation_data_from::date, resolution_rule
  FROM core.hypothesis_register WHERE hypothesis_id LIKE 'watch:%' ORDER BY preregistered_at;
SELECT count(*) FROM analysis.panel WHERE day > (SELECT min(confirmation_data_from)::date FROM core.hypothesis_register WHERE hypothesis_id LIKE 'watch:%');
```
The frozen `resolution_rule` text on every existing watch is:
"median delta same sign with q<0.10 on >=30 post-registration days". The resolver
implements exactly that sentence. It **may not** be reinterpreted per row.

## Step 1 — migration `migrations/0042_hypothesis_resolutions.sql`
An append-only ledger of every status change, so demotions are visible (REQ-TIER-043)
and `get_findings` can show history.
```sql
CREATE TABLE IF NOT EXISTS __CORE__.hypothesis_resolutions (
    resolution_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hypothesis_id   TEXT NOT NULL REFERENCES __CORE__.hypothesis_register(hypothesis_id),
    resolved_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    status_from     TEXT NOT NULL,
    status_to       TEXT NOT NULL,
    reason          TEXT NOT NULL,          -- closed set below
    post_days       INTEGER NOT NULL,       -- days with both metrics after confirmation_data_from
    n_hi            INTEGER, n_lo INTEGER,
    delta           NUMERIC, p_raw NUMERIC, q_fdr NUMERIC,
    registered_direction TEXT NOT NULL,
    observed_direction   TEXT,
    code_version    TEXT NOT NULL
);
-- append-only: attach the 0012 mutation-rejecting trigger pattern to this table too.
```
`reason` ∈ {`confirmed_same_sign_q_lt_0_10`, `refuted_opposite_sign_q_lt_0_10`,
`insufficient_window_too_short`, `insufficient_low_n_eff`, `insufficient_sign_unstable`,
`expired_no_decision_120d`}.

Also extend `get_findings` (B6): add `'history', (SELECT jsonb_agg(...) FROM core.hypothesis_resolutions ORDER BY resolved_at DESC LIMIT 50)` with fields
`{hypothesis_id, resolved_at, status_from, status_to, reason, post_days, delta, q_fdr, trace}` — additive, no renames.

## Step 2 — `tools/engines/resolve.py`
Deterministic; imports the exact same helpers from `tools/engines/scan.py`
(`_load_panel`, `_dow_demedian`, `_contrast`, `_mann_whitney_p`, `_lag1_rho`,
`_median`) — **do not copy them**; import, so one owner (RULE-11).

```
CODE_VERSION = "resolve-v1"
MIN_POST_DAYS = 30        # from the frozen rule text
MIN_SIDE = 7              # quartile side minimum on a 30-day window (ADR-0048; the scan's 30 is for 7-year sweeps)
Q_CONFIRM = 0.10          # from the frozen rule text
EXPIRE_DAYS = 120         # ADR-0048: a watch with no decision after 120 post days expires to INSUFFICIENT

def run(cur, today=None):
    for each h in hypothesis_register where hypothesis_id like 'watch:%' and status in ('INSUFFICIENT','PROMOTED'):
        panel = _load_panel(cur) restricted to day > h.confirmation_data_from::date and day <= today
        drv = dow-demedianed series for h.exposure_metric; out = same for h.outcome_metric
        post_days = count of days where drv has a value and out has a value at day+lag
        if post_days < MIN_POST_DAYS: record nothing (still on the clock); continue
        c = _contrast(drv, out, h.lag_days) with side minimum MIN_SIDE   (pass as a parameter; add an optional `min_side` kwarg to scan._contrast defaulting to scan.MIN_SIDE — additive, scan behaviour unchanged)
        if c is None or min(n_hi, n_lo) < MIN_SIDE: reason = insufficient_low_n_eff -> if post_days >= EXPIRE_DAYS: status INSUFFICIENT + ledger row expired_no_decision_120d; continue
        collect (h, c, post_days)
    BH-adjust p across the batch collected this run -> q per watch
    for each: observed_direction = 'positive' if delta > 0 else 'negative'
        if q < Q_CONFIRM and observed_direction == h.direction: status_to = 'CONFIRMED_OBSERVATIONAL', reason confirmed_same_sign_q_lt_0_10
        elif q < Q_CONFIRM and observed_direction != h.direction: status_to = 'REFUTED', reason refuted_opposite_sign_q_lt_0_10
        elif post_days >= EXPIRE_DAYS: status_to = 'INSUFFICIENT', reason expired_no_decision_120d
        else: continue   # still watching; no row written
        UPDATE core.hypothesis_register SET status = status_to WHERE hypothesis_id = h.id   (only status: the freeze trigger allows it)
        INSERT core.hypothesis_resolutions (...)
        INSERT core.predictions: a scored prediction row for RULE-20 — claim_text = the registered sentence, evidence_tier = status_to, outcome_bool = (status_to == 'CONFIRMED_OBSERVATIONAL'), model_version = CODE_VERSION, resolves_at = now()  (use the real column names from 0008)
    write ops.runs row job_name='resolve_watches' with counts {evaluated, confirmed, refuted, expired, still_watching}
```
A `CONFIRMED_OBSERVATIONAL` row is still observational: `get_findings`/L3 already print
"E-value and negative control: not yet computed." Do not compute them here (they are a
separate, later build); do not soften the label to hide that.

## Step 3 — schedule
Add to `.github/workflows/analysis.yml`, nightly, after the panel+baselines step and
before the Monday scan: `python3 tools/run_resolve.py` (a 10-line wrapper like
`run_scan.py`, heartbeated to `ops.runs`). Nightly, not weekly: a watch that crosses 30
days should resolve the next morning.

## Tests `tests/test_resolve_watches.py` (synthetic panel in a rolled-back transaction, throwaway schema)
```
test_REQ_INF_107_resolver_ignores_days_before_confirmation_data_from
test_REQ_INF_103_resolver_changes_only_status
test_ADR_0048_watch_under_30_post_days_is_left_alone
test_ADR_0048_same_sign_q_below_0_10_confirms_and_writes_ledger_and_prediction
test_ADR_0048_opposite_sign_q_below_0_10_refutes
test_ADR_0048_no_decision_after_120_days_expires_to_insufficient_with_reason
test_REQ_TIER_043_every_status_change_has_a_ledger_row
test_RULE_11_resolver_imports_contrast_from_scan_not_a_copy   (assert resolve._contrast is scan._contrast)
```

## Done when
Migration dry-run + apply; `python3 tools/run_resolve.py` output pasted (expected today:
every watch "still on the clock" or evaluated with its real numbers — paste them);
tests pass; workflow file diff pasted; ADR-0048 (with the two interpretations stated:
MIN_SIDE=7 on the 30-day window; 120-day expiry); DECISIONS row; `update_features.py`;
PROGRESS + WHAT I DID NOT DO (E-value/negative control; no re-confirmation on a rolling
basis — a CONFIRMED row stays CONFIRMED until a later build re-tests it).
