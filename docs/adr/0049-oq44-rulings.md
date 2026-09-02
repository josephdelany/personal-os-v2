# ADR-0049: OQ-44 rulings (Joe, 2026-09-02, via advisor) — the ladder made self-consistent before B9

## Status
Accepted. Built by B8 (`docs/build/B8_consistency_and_rulings.md`), migration 0045, session 20.

## Date
2026-09-02

## The rulings (verbatim from B8; each closes an OQ-44 letter)

- **(a) Who scores the forward prediction.** The resolver's second look (day 120) scores it:
  `outcome_bool` = same sign with p < 0.10 on the post-promotion window; `brier` =
  (p_forecast − outcome)². B9 wires it; B8 records the ruling.
- **(b) `p_forecast`.** 0.90 was arbitrary. Ruling: `p_forecast = 0.5`, stated in `claim_text` as
  "uninformative until the calibration ledger holds ≥ 20 scored resolutions"; once it does,
  `p_forecast` = the empirical replication rate from `core.hypothesis_resolutions` (REQ-INF-3xx
  count-and-proportion trigger). Until then, every Brier is 0.25 by construction and the surface
  must say so.
- **(c) Reason vocabulary.** Add `insufficiency_reason TEXT` to `core.hypothesis_resolutions`
  with the REQ-TIER-018 closed set; map: `insufficient_window_too_short → window_too_short`,
  `insufficient_low_n_eff → low_n_eff`, `insufficient_sign_unstable → sign_unstable`,
  `expired_no_decision_120d → window_too_short`, new `insufficient_low_coverage →
  low_coverage`. The ledger keeps both columns.
- **(e) PROMOTED, not CONFIRMED, from the resolver.** Confirmed. CONFIRMED_OBSERVATIONAL is
  granted only by B9's gate.
- **(f) Surfaces agree.** `get_today.watching` and `get_trust.hypotheses.watching` read the same
  predicate as `get_findings.watching`: `hypothesis_id LIKE 'watch:%' AND status IN
  ('INSUFFICIENT','PROMOTED') AND NOT EXISTS (resolution row with status_to IN ('REFUTED') OR
  reason = 'expired_no_decision_120d')`. Put the predicate in one SQL function
  `public._watching_rows()` and have all three call it (RULE-12). The clock shown is **paired
  post-registration days** (`post_days`, computed by the same helper the resolver uses, exposed
  via a small `analysis.watch_progress` table the resolver writes nightly: `hypothesis_id,
  post_days, coverage, n_eff, next_look, computed_at`) — never calendar days. Text: "day
  {post_days} of 30 · next look {next_look}".
- **(g) Tests in CI.** New workflow `tests.yml`: nightly 09:00 UTC and on push to `main`, runs
  `python3 tools/update_features.py` (which runs the full suite) with `SUPABASE_DB_URL` from the
  secret, fails the job on any test failure, and commits `ops/features.json` if it changed (bot
  commit, same pattern as keepalive's heartbeat commit). Plus the RULE-22 grep the constitution
  describes — read the constitution's wording and implement exactly that grep as a `gates.yml`
  step.
- **(h) Which n the floor of 20 governs.** Kish `n_eff` on the **paired-day** count (RULE-21),
  with the existing per-side minimum of 7 retained as a separate gate. Both gates stored in
  `watch_progress`.
- **(i) False-resolution rate.** Ruling: tighten the **rule template for new registrations**
  (zero watches exist; nothing is retroactive). New `resolution_rule` text written by
  `register_watch`: "Look 1 at the first night with ≥30 paired post-registration days: promote if
  same sign as registered and p<0.05 with n_eff≥20; refute if opposite sign and p<0.10. Look 2 at
  day 120: keep PROMOTED only if same sign and p<0.10, else demote to INSUFFICIENT(sign_unstable);
  refute if opposite sign and p<0.10." The resolver reads the rule text's thresholds from a parsed
  `rule_version` field (add `rule_version TEXT` to `core.hypothesis_register` via ALTER — the
  freeze trigger does not list it; `'v1'` for rows registered before this migration, `'v2'`
  after) and applies v1 semantics to v1 rows forever.
- **(j) Coverage clause.** `coverage = post_days / calendar_days_since(confirmation_data_from +
  lag)`; `< 0.60 → INSUFFICIENT(low_coverage)` at either look, ledgered. `rho` stays on the paired
  series; record in ADR-0049 that it is biased low under sparse coverage and that the coverage
  gate is the mitigation.
- **(k) Token.** Joe rotates it (one `supabase secrets set` + re-type on the phone). Not a build
  item.

## How B8 read the rulings where the text left a gap (recorded, not silently chosen)
1. **v2 look 2 on a PROMOTED row tests the post-promotion window only** — the paired days after
   the look-1 `look_day` (a new ledger column: the panel day a look was taken at; `resolved_at`
   is wall clock). That is what (a) scores, so it is what (i)'s "keep PROMOTED only if …" reads
   over. Look 2 is therefore due when the row has ≥120 paired days **and** the post-promotion
   window holds ≥30 — a promotion at a late first look is not re-looked the same night on an
   empty window (found by the idempotence test).
2. **An INSUFFICIENT v2 row at look 2** (look 1 undecided) gets the look-1 criterion on the full
   post-registration window; otherwise it expires. The v2 text does not say; this is the
   conservative reading.
3. **A PROMOTED v2 row is never calendar-expired.** It waits for its post-promotion window; if
   the data stops after promotion it stays PROMOTED-under-watch. Named in WHAT I DID NOT DO.
4. **v1 rows**: PROMOTED is final (ADR-0048 §12 semantics unchanged). No v1 row exists live.
5. **Gates are ledgered as looks** (coverage, n_eff, per-side) with the vocabulary reason; a
   degenerate contrast is still not a look (ADR-0048 §13).
6. **`next_look` is a projection** (one paired day per calendar day) and every surface labels it
   "~". `insufficiency_reason: window_too_short` on an on-the-clock watch is surfaced by
   `_watching_rows` (no ledger row is written for the on-the-clock state).
7. **The forward prediction resolves 90 days out** (120 − 30), when look 2 is due; B9 scores it.
8. **`ρ` is biased low under sparse coverage** (second review, finding 9); the coverage gate (j)
   is the mitigation and is applied before the n_eff gate.

## Consequences
- One predicate, three surfaces, one clock: `get_today`, `get_trust`, `get_findings` cannot
  disagree on `watching` by construction (RULE-12); the TODAY line reads "day N of 30 · next
  look ~D" from the resolver's own table (RULE-14 / INV-3).
- The whole suite runs on every push and nightly (`tests.yml`), and the ledger moves only by a
  bot commit from a named passing test; RULE-22's grep exists in `gates.yml`.
- New registrations resolve under the v2 template; the executed null replay of the v1 template
  (~0.20 false resolution) stands in ADR-0048 as the reason.

## Not built
Scoring of the forward prediction (B9); the calibrated `p_forecast` path is coded but
unreachable until 20 scored resolutions exist; PROMOTED → CONFIRMED (B9); a PROMOTED row whose
data stops is not expired.
