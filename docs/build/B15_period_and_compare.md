# B15 — `get_period(week)` and `get_compare(metric, condition)` (migration 0053)

**What this is.** THE_FILE's v2 items: the weekly report (ASSESSMENT › weekly) and
Compare (FINDINGS › Compare). Both are DESCRIPTIVE, both are one envelope, both reuse
B11's registered operations so there is one owner of every statistic. One session.

**Requirement IDs satisfied:** REQ-TIER-010 (DESCRIPTIVE tier for these computations),
REQ-ASK-005/006 (every period/compare result is a `computations` row — reuse B11's
executor so `get_period` and `get_compare` are thin wrappers), REQ-NAR-014/015,
REQ-INF-505. **ADR:** ADR-0062.

## `public.get_period(p_week date DEFAULT NULL)` — the ISO week containing `p_week` (default: last complete week)
Envelope:
```
{week_start, week_end, tier:'DESCRIPTIVE',
 sentence,                                   -- closed template: "Week of {week_start}: {k} of {n} tracked sources in band; {m} above, {j} below."
 sources:[{domain, display_name, metric, unit, week_median, prior_week_median, delta, band:[lo,hi], position, days_with_data, trace}],
 money:{total, typical_week, delta, top_categories:[{name, amount, typical, delta}], top_merchants:[...]} ,
 movement?:{away_min, distinct_places, top_places:[{label, dwell_min}]},
 findings_changed:[{hypothesis_id, from, to, reason, at}],        -- from core.hypothesis_resolutions in the week
 recommendations:{issued, followed?:null, scored:[{claim, outcome_bool, brier}]},
 coverage_gaps:[{domain, status, capture_action}],
 computation_ids:[...]}
```
`position` uses the personal band from `analysis.baselines` on the week's last day.
`followed` is null and stays null until a follow-through capture exists (say so in the
ADR; never infer "followed" from the outcome).

## `public.get_compare(p_metric text, p_condition text, p_window text DEFAULT '1y')`
`p_condition` grammar (closed; the same as B11's `count_days` condition):
`above_band:<metric>` | `below_band:<metric>` | `gt:<metric>:<x>` | `lt:<metric>:<x>` |
`weekday:<1-7>` | `place:<label>` | `entity:<type>:<key>` | `after:<metric>:above_band:<lag>`.
Envelope:
```
{metric, unit, condition, window, tier:'DESCRIPTIVE',
 sentence,   -- "On the {n_a} days when {condition text}, {metric} ran {median_a} {unit}; on the other {n_b}, {median_b} {unit} (difference {delta} {unit})."
 a:{n, median, p10, p90}, b:{n, median, p10, p90}, delta,
 natural_frequency:{k, n, text},   -- REQ-ASK-027: "{k} of {n} condition days were above your band"
 note:"Descriptive comparison. Not a finding; see Findings for tested patterns.",
 existing_finding?:{hypothesis_id, tier},   -- if the pair is registered, point to it (REQ-ASK-032)
 computation_id}
```
Never a p-value here; if the user wants inference, the `existing_finding` pointer is the
route (and `register_watch` from FINDINGS).

## Tests
```
test_ADR_0062_get_period_defaults_to_last_complete_iso_week
test_ADR_0062_get_period_every_number_has_trace_or_computation_id
test_ADR_0062_get_compare_condition_grammar_rejects_unknown_with_refusal
test_ADR_0062_get_compare_never_returns_a_p_value
test_REQ_ASK_027_compare_natural_frequency_text
test_REQ_ASK_032_compare_points_to_registered_finding_when_one_exists
test_REQ_INF_505_period_omits_money_when_no_transactions_in_week
```

## Done when
Migration; three owner calls pasted (last week; compare sleep vs alcohol above band;
compare hrv vs place:gym); tests; ADR-0062; L4 amended (I will) to bind the weekly card;
PROGRESS + WHAT I DID NOT DO.
