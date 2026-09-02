# L3 — Lovable Round 3: FINDINGS and RELIABILITY, complete

**Preconditions:** L2 accepted; B6 live (`get_findings`). If B6 is not live, paste
only part A and the RELIABILITY block; add the lifecycle lists later in a short round.
Paste as ONE message.

---

ROUND 3 — FINDINGS AND RELIABILITY.

A) `/findings` becomes four stacked lists on one page with a sticky sub-nav:
Exploratory · Watching · Confirmed · Refuted. Data: `get_patterns` (exploratory, as
built in L0) and `supabase.rpc('get_findings')`. Envelope:
```
{as_of,
 watching?:[{hypothesis_id, tier:'WATCHING', source, exposure, outcome, lag_days, direction, registered_at, data_from, days_elapsed, days_needed, resolution_rule, status, trace}],
 confirmed?:[{hypothesis_id, tier:'CONFIRMED', exposure, outcome, lag_days, direction, adjustment_set, registered_at, trace}],
 refuted?:[{hypothesis_id, tier:'REFUTED', exposure, outcome, lag_days, registered_at, trace}],
 insufficient?:[{hypothesis_id, tier:'INSUFFICIENT', exposure, outcome, lag_days, registered_at, trace}],
 counts:{candidates, watching, confirmed, refuted},
 predictions_pending?:[{claim, tier, resolves_at, hypothesis_id, trace}]}
```
- Page opening sentence, template: "{counts.confirmed} confirmed · {counts.watching}
  watching · {counts.candidates} exploratory · {counts.refuted} refuted."
- EXPLORATORY: unchanged from L0 (calibration line first, text cards, Watch button).
- WATCHING: one row per item: badge WATCHING, "{exposure} → {outcome}, lag {lag_days}d,
  {direction}", a progress bar `days_elapsed / days_needed` with the text "day
  {days_elapsed} of {days_needed} · verdict pending · data from {data_from}", and
  `resolution_rule` in a details disclosure. Text + one progress bar; no charts.
- CONFIRMED: badge CONFIRMED, "{exposure} → {outcome}, lag {lag_days}d, {direction}",
  "controlled for: {adjustment_set as comma list}", and the line "E-value and negative
  control: not yet computed." verbatim (they are absent in the envelope). Empty list →
  "Nothing confirmed yet. Confirmation needs a watched test to run its course."
- REFUTED: badge REFUTED, same one-line description, `registered_at`. Empty →
  "Nothing refuted yet."
- INSUFFICIENT (collapsed by default): badge INSUFFICIENT, one line each.
- PREDICTIONS PENDING (bottom): rows "{claim} · resolves {resolves_at}" with badge from
  `tier`.
- Every row's trace sheet from `trace`. Keystone table stays in the Exploratory section.

B) `/reliability` becomes the full audit page from `get_trust` (already wired in L0),
laid out as six cards in this order, each with its own one-line opener:
1. FORECASTS — opener "Claimed {claimed_coverage}, achieved {achieved_coverage} on
   {resolved} resolved · {pending} pending · mean Brier {mean_brier}." Then two bars
   side by side (claimed vs achieved) — this is DESCRIPTIVE and may be charted.
2. SCAN LEDGER — a table of `scan_calibration` rows: run · tested · observed ·
   shuffled-null · null p95. Opener: the latest row as "{observed_sig} observed vs
   {shuffled_null_sig} on shuffled data (p95 {null_p95}) in the {run} run."
3. LIFECYCLE — the four `hypotheses` counts as large numerals with labels; each links
   to the matching `/findings` list.
4. WHAT THE FILE CANNOT SEE — `coverage_blindspots` as an amber list "{metric} — last
   {last_day}". Empty → "No blind spots among the core metrics." Prettify metric names,
   raw in tooltip.
5. HEARTBEATS — `job_heartbeats` rows: job · relative `last` · `status` verbatim; a
   status other than "ok" renders amber. Opener: "{count of ok} of {count} jobs
   reported ok on their last run." (count of rows — allowed).
6. CORRECTIONS — text only for now: "Corrections you make in THE DESK appear here in a
   later round." (no RPC yet; do not fake).
Misses must be exactly as visible as hits: never hide a bad number.

ACCEPTANCE: (a) all four findings lists render from the envelope with correct empty
states; (b) no CANDIDATE row appears anywhere except the Exploratory list; (c) the only
chart-like elements on `/findings` are the WATCHING progress bars; (d) `/reliability`
shows six cards in order; (e) no client arithmetic beyond counting envelope rows.
