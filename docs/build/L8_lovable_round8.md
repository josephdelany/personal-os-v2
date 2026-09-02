# L8 — Lovable Round 8: Ask, Recommendations, Trials, the weekly report, and the new modules

**Preconditions:** L7 accepted (or L6 if L7 skipped); B8–B23 live. Paste as ONE message.
This round binds every envelope field the later backend builds added. Each item names
its RPC; if an RPC is absent (the backend session was skipped), Lovable must render the
honest empty state, never a mock.

---

ROUND 8 — THE INSIGHT LAYER SURFACES.

1) THE DESK › ASK — `supabase.rpc('ask', {p_question, p_as_of?})`. Envelope
`{question_id, tier, answer_text, numerals:[{value, unit, computation_id}], plan, coverage:{<metric>:x},
insufficiency_reason?, refusal?, nearest?, trace:{computation_ids}}`.
Enable the Ask box. Render `answer_text` verbatim; every numeral inside it is a tap
target → trace sheet showing its `computation_id`, the `plan`, and `coverage`. `tier`
badge on the answer. `refusal` → verbatim + `nearest` chips (tap → re-ask with the
chip). INSUFFICIENT → the partial form: answer plus an amber line "{insufficiency_reason}
— {what would raise it}" (from the envelope, never invented). Keep a scrollable history
of the session's questions (client memory only). Never send a question automatically.

2) ASSESSMENT › the one instruction — `get_today.instruction` (from B10). A single
card at the top, under the opening sentence: `tier` badge, `instruction` verbatim,
small print "effect {effect.abs} {effect.unit} ({ci[0]}–{ci[1]}) · n {n} · coverage
{coverage} · {counter_frame_n} bad days without it", `would_change` as a footnote,
and the prediction line "predicts: {prediction.claim} · resolves {resolves_at}". If
absent → no card (never "no recommendation today" as a card; silence is the honest state).
Also `get_today.notices[]` (demotions/refutations) → amber rows above the state block:
"{kind}: {text}". And `get_today.regime` → one line "Current state: {profile as
'metric mean unit' list} · {days_in_state} days (typical {typical_run.median})" — no
state names, no colours.

3) THE DESK › RECOMMENDATIONS — `supabase.rpc('get_recommendations')` → the `active`
list as cards (same anatomy as 2), `demoted_recent` below in muted style with
`demoted_reason`. Standing orders show badge DESCRIPTIVE and "your standing order".

4) FINDINGS additions — `get_findings` gained: `promoted[]` (render like `watching`
with the spec-curve line "{share_sig×100}% of {n_specs} specs agree (null median
{null_median_share×100}%)" and the counter-frame line); `confirmed[]` fields `effect`,
`e_value`, `negative_controls`, `refuters`, `adjustment_set`, `next_recheck` (replace the
"not yet computed" line with: "adjusted for {adjustment_set}; E-value {e_value.point}
(limit {e_value.limit}); negative controls {outcome_metric} p {outcome_p}, future-exposure
p {exposure_p}; re-check {next_recheck}"); `history[]` (the resolution ledger as a
plain dated list); `chains[]` (each as a text path "A → B → C · {chain_tier} ·
attenuated {attenuated_effect}" with each edge tappable to its evidence record);
`trials[]` (cards: exposure → outcome, blocks {blocks_done}/{blocks_planned}, deviation
rate, power, `result` when present; "Propose a trial" button → a form calling
`propose_trial` and rendering its power line or refusal verbatim).
The Bayesian display for CONFIRMED rows: "{p_direction×100}% probability the effect is
{direction}; {p_practical×100}% beyond ±{rope} {unit}" — numeral first, EFSA term after,
exactly as the envelope's `bayes_text` field provides it (do not compose it).

5) ASSESSMENT › WEEKLY — `supabase.rpc('get_period')` on a "This week / Last week"
toggle: the `sentence`, the `sources[]` table (median, prior, delta, position badge),
`money` (total vs typical, top categories/merchants as delta chips, `position` line with
its `as_of` and `coverage` — never a live counter), `movement`, `findings_changed`,
`recommendations.scored`, `coverage_gaps`. Every number tappable to its trace or
computation id.

6) FINDINGS › COMPARE — `supabase.rpc('get_compare', {p_metric, p_condition, p_window})`:
a form with a metric picker (from `get_domains` metrics) and a condition builder
limited to the closed grammar (above band / below band / gt / lt / weekday / place /
entity / after…lag); render the `sentence`, the two summaries, `natural_frequency.text`,
`note` verbatim, and `existing_finding` as a link when present. No chart with a p-value
(there is none).

7) SOURCES › new modules (all from `get_domain`, additive): `money` → `recurring`,
`income`, `position`, `budget`, `forecast_outflows` (ranges only), `reconciliation`;
`workouts` → `exercises` (best e1RM as an interval, the e1RM trend line with band),
`load` (ACWR with window and coverage), `presence` (three numbers); `body` → smoothed
weight with interval, TDEE only when present; `sleep` → debt, regularity; `food` →
the daily nutrient intervals (kcal lo–hi as a range bar, never a point); `weather`
domain appears in the index automatically.

8) THE DESK additions — "Unresolved items" (`get_day.unresolved[]` from B12) with a
resolve form (`resolve_item` RPC); "Name this link" corrections (`correct_link`);
"Explore families" (`request_scan`); "Set balance anchor" (`set_balance_anchor`) and
"Budgets" (a Joe-set table, retrospective view only); deferred/failed capture counts
(REQ-CAP-044) with the exact reason strings.

9) RELIABILITY additions — `get_trust.requirements` as the file's own honesty number:
"{proven} proven · {deferred} deferred · {open} open of {total}" with the by-prefix
table; `calibration` reliability table; `capture_compliance`; reconciliation flags.

ACCEPTANCE: (a) every field above binds to an existing RPC or renders its empty state;
(b) grep: no client arithmetic, no `from('`, no p-value string anywhere, no map
libraries; (c) the Ask box never auto-submits; (d) numerals in `answer_text` are
tappable and resolve to computation ids.
