# B8 — Consistency & rulings: OQ-44 closed, surfaces agree, tests run in CI (migration 0045)

**What this is.** Session 19's WHAT I DID NOT DO and OQ-44 (e)–(k), turned into rulings
and one short build. Nothing new is invented here; the ladder is made self-consistent
before B9 builds its top rung. Half a session.

**Requirement IDs satisfied:** RULE-12 (one number, one owner — the two `watching`
counts must agree), REQ-TIER-017 (both clauses: coverage and n_eff), REQ-TIER-018
(machine-readable `insufficiency_reason`), RULE-20 (a forward prediction is scored),
RULE-22 (CI enforcement of TEST-tier rules), REQ-INF-103 (frozen columns untouched:
the new rule text applies only to rows registered after this migration).
**ADR to write:** ADR-0049 — "OQ-44 rulings (Joe, 2026-09-02, via advisor)".

## The rulings (record verbatim in ADR-0049; close each OQ-44 letter)

- **(a) Who scores the forward prediction.** The resolver's second look (day 120)
  scores it: `outcome_bool` = same sign with p < 0.10 on the post-promotion window;
  `brier` = (p_forecast − outcome)². B9 wires it; B8 records the ruling.
- **(b) `p_forecast`.** 0.90 was arbitrary. Ruling: `p_forecast = 0.5`, stated in
  `claim_text` as "uninformative until the calibration ledger holds ≥ 20 scored
  resolutions"; once it does, `p_forecast` = the empirical replication rate from
  `core.hypothesis_resolutions` (REQ-INF-3xx count-and-proportion trigger). Until then,
  every Brier is 0.25 by construction and the surface must say so.
- **(c) Reason vocabulary.** Add `insufficiency_reason TEXT` to
  `core.hypothesis_resolutions` with the REQ-TIER-018 closed set; map:
  `insufficient_window_too_short → window_too_short`, `insufficient_low_n_eff → low_n_eff`,
  `insufficient_sign_unstable → sign_unstable`, `expired_no_decision_120d → window_too_short`,
  new `insufficient_low_coverage → low_coverage`. The ledger keeps both columns.
- **(e) PROMOTED, not CONFIRMED, from the resolver.** Confirmed. CONFIRMED_OBSERVATIONAL
  is granted only by B9's gate.
- **(f) Surfaces agree.** `get_today.watching` and `get_trust.hypotheses.watching` read
  the same predicate as `get_findings.watching`: `hypothesis_id LIKE 'watch:%' AND status
  IN ('INSUFFICIENT','PROMOTED') AND NOT EXISTS (resolution row with status_to IN
  ('REFUTED') OR reason = 'expired_no_decision_120d')`. Put the predicate in one SQL
  function `public._watching_rows()` and have all three call it (RULE-12). The clock
  shown is **paired post-registration days** (`post_days`, computed by the same helper the
  resolver uses, exposed via a small `analysis.watch_progress` table the resolver writes
  nightly: `hypothesis_id, post_days, coverage, n_eff, next_look, computed_at`) — never
  calendar days. Text: "day {post_days} of 30 · next look {next_look}".
- **(g) Tests in CI.** New workflow `tests.yml`: nightly 09:00 UTC and on push to
  `main`, runs `python3 tools/update_features.py` (which runs the full suite) with
  `SUPABASE_DB_URL` from the secret, fails the job on any test failure, and commits
  `ops/features.json` if it changed (bot commit, same pattern as keepalive's heartbeat
  commit). Plus the RULE-22 grep the constitution describes — read the constitution's
  wording and implement exactly that grep as a `gates.yml` step.
- **(h) Which n the floor of 20 governs.** Kish `n_eff` on the **paired-day** count
  (RULE-21), with the existing per-side minimum of 7 retained as a separate gate. Both
  gates stored in `watch_progress`.
- **(i) False-resolution rate.** Ruling: tighten the **rule template for new
  registrations** (zero watches exist; nothing is retroactive). New `resolution_rule`
  text written by `register_watch`: "Look 1 at the first night with ≥30 paired
  post-registration days: promote if same sign as registered and p<0.05 with n_eff≥20;
  refute if opposite sign and p<0.10. Look 2 at day 120: keep PROMOTED only if same sign
  and p<0.10, else demote to INSUFFICIENT(sign_unstable); refute if opposite sign and
  p<0.10." The resolver reads the rule text's thresholds from a parsed `rule_version`
  field (add `rule_version TEXT` to `core.hypothesis_register` via ALTER — the freeze
  trigger does not list it; `'v1'` for rows registered before this migration, `'v2'`
  after) and applies v1 semantics to v1 rows forever.
- **(j) Coverage clause.** `coverage = post_days / calendar_days_since(confirmation_data_from + lag)`;
  `< 0.60 → INSUFFICIENT(low_coverage)` at either look, ledgered. `rho` stays on the
  paired series; record in ADR-0049 that it is biased low under sparse coverage and that
  the coverage gate is the mitigation.
- **(k) Token.** Joe rotates it (one `supabase secrets set` + re-type on the phone). Not
  a build item.

## Migration `migrations/0045_consistency.sql`
- `ALTER TABLE core.hypothesis_register ADD COLUMN IF NOT EXISTS rule_version TEXT NOT NULL DEFAULT 'v1';`
  (use `__CORE__`); `CREATE OR REPLACE FUNCTION public.register_watch` with the v2 rule
  text and `rule_version='v2'` — keep every other line identical to 0031.
- `ALTER TABLE __CORE__.hypothesis_resolutions ADD COLUMN IF NOT EXISTS insufficiency_reason TEXT CHECK (insufficiency_reason IN ('low_coverage','low_n_eff','informative_missingness','no_adjustment_set','sign_unstable','metric_absent','window_too_short'));`
- `CREATE TABLE IF NOT EXISTS analysis.watch_progress (hypothesis_id TEXT PRIMARY KEY, post_days INT, calendar_days INT, coverage NUMERIC, n_eff NUMERIC, n_hi INT, n_lo INT, next_look DATE, look_done INT, code_version TEXT, computed_at TIMESTAMPTZ DEFAULT now());`
- `public._watching_rows()` (SECURITY DEFINER, no client EXECUTE) and `CREATE OR REPLACE` of
  `get_today`, `get_trust`, `get_findings` to use it — additive envelope changes only:
  `watching[].post_days`, `watching[].coverage`, `watching[].n_eff`, `watching[].next_look`.

## `tools/engines/resolve.py` changes
Implement (h), (i), (j) and write `analysis.watch_progress` every night for every open
watch (even when no look is due — the surfaces need the clock). Rule thresholds by
`rule_version`. Tests added: `test_ADR_0049_v1_rows_keep_v1_semantics`,
`test_ADR_0049_v2_look1_requires_p_lt_0_05_and_n_eff_20`,
`test_ADR_0049_v2_look2_demotes_sign_unstable`, `test_REQ_TIER_017_low_coverage_is_insufficient_with_reason`,
`test_RULE_12_three_surfaces_report_identical_watching_sets`,
`test_REQ_TIER_018_every_insufficient_ledger_row_has_vocabulary_reason`.

## Done when
Migration dry-run + apply; `tests.yml` exists and its first run on GitHub is green (paste
the run URL and the summary line); `gates.yml` has the RULE-22 step; the three surfaces
return the same `watching` list (paste all three); ADR-0049; OQ-44 letters closed;
`update_features.py`; PROGRESS + WHAT I DID NOT DO.
