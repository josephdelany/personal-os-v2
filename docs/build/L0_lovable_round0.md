# L0 — Lovable Round 0: kill, rewire, seven-section shell

**Preconditions:** B1 live (`get_domains`). Everything else L0 reads is already live.
**Where:** lovable.dev → project **My Life Compass** (`e410d482-dd93-4c0f-a79b-6db0a2e0fe9b`).
**How:** paste everything below the line as ONE message. Do not split it. Do not add
"also make it look nice". If Lovable asks a question, answer only that question.
**Joe's decisions baked in (change the bracketed words before pasting if you disagree):**
name = **[The File]**; bottom bar = Assessment · Record · Sources · Findings · Desk,
Movements and Reliability under "More"; dark by default.

---

ROUND 0 — REBUILD THE SHELL. Keep the design system, replace everything else.

KEEP exactly: `src/styles.css` oklch dark-teal tokens, tabular-nums, 150–300 ms ease-out
motion with `prefers-reduced-motion` honoured, the PWA manifest and service worker,
magic-link auth (`signInWithOtp`). Rename the app to "[The File]" in manifest, title, header.

DELETE every page, component, hook and query that reads any of: `day_timeline`, `signals`,
`insights`, `events`, `transactions`, `checkins`, any `public.*` table directly, any RPC not
listed below, and the entire old Today "Proven" feed and Intelligence loops. Delete the
old tabs (Today/Timeline/Domains/Trends/Intelligence/Ask/Log). No dead code remains.

DATA RULES (non-negotiable, these are the product):
- Every screen is exactly one `supabase.rpc(...)` call from this list. The client never
  computes: no sums, averages, deltas, percentages, ranks, sorting by value, or "trend"
  arrows. Render what the envelope sends, in the order it sends it.
- A number the envelope did not send is never shown. A missing key means the module is
  absent — render its empty-state text, never `0`, never `—`, never a placeholder chart.
- Every numeric value is rendered with its `unit` field beside it.
- Every value that comes with a `trace` object is tappable: tapping opens a small sheet
  that prints the `trace` object's fields as key: value lines (this is the provenance
  view; no styling beyond monospace).
- The only confidence words that may appear anywhere are the values of a `tier` field:
  DESCRIPTIVE · EXPLORATORY · WATCHING · CONFIRMED · REFUTED · INSUFFICIENT — rendered
  as a small outlined badge. Never "proven", "strong", "likely", stars, or percentages of
  confidence.
- Coverage badge component `<Coverage status last_day stale_days/>`: `fresh` → teal dot;
  `stale` → amber dot + "stale · {stale_days}d"; `not_logged` → grey + "not logged since
  {last_day}"; `never_captured` → grey outline + "never captured". Text exactly as given.
- Never render: rings, streak flames, celebrations, scores-of-scores, "good/bad day", any
  chart for an item whose tier is EXPLORATORY, WATCHING, REFUTED or INSUFFICIENT.
- `owner only` / permission errors mean "sign in" — show the magic-link form, never an error toast.
- A `refusal` key in any envelope renders the string verbatim in a plain card plus, if
  present, `nearest` as tappable chips. Nothing else on that screen.

NAVIGATION. Desktop ≥ 900 px: left rail with seven items; content is a bento of the
current section. Phone: bottom bar with five: Assessment · Record · Sources · Findings ·
Desk, plus "More" opening Movements and Reliability. Routes:
`/assessment` (default) `/record` `/record/:day` `/movements` `/sources` `/sources/:domain`
`/findings` `/reliability` `/desk`.

SECTIONS in this round (each opens with the one sentence the envelope provides, then evidence):

1) ASSESSMENT — `supabase.rpc('get_today')`. Envelope:
`{for_day, based_on, state:{day, deviations:[{metric,value,z,band:[lo,hi]}], streaks:[{metric,run_days,direction,historical_max_run}], guardian:{signals_firing,threshold,fires_historically}, week_money:[{name,grain,this_week,typical_week,delta}]}, connection:{label,sentence,q,n}, watching:[{hypothesis,registered,day,of,status}], forecast:[{metric,lo,point,hi}], forecast_track_record:{resolved,inside_band,claimed_coverage,achieved_coverage}}`
Opening sentence: if `state.deviations` is absent or empty → "In your normal bands."
else → the first deviation as "{metric} {value} — z {z} against your band {lo}–{hi}."
(These are the only two templates; use the metric name prettified, raw name in tooltip.)
Guardian → amber banner only when present, text exactly: "{signals_firing} of
{threshold} autonomic signals firing; historically fired on {fires_historically} days.
A pattern match, not a diagnosis." Deviations → rows with a range bar (band) and a value
marker. Streaks → rows "{run_days} days {direction} · longest ever {historical_max_run}".
Week money → delta chips "{name} {delta:+$} vs typical". Connection → one text card with
badge EXPLORATORY and the `sentence` verbatim, "q {q} · n {n}" in small print, no chart.
Watching → progress rows "day {day} of {of} · verdict pending". Forecast → range bars
`lo–hi` with `point` marker, and under them one line: "Claimed {claimed_coverage},
achieved {achieved_coverage} on {resolved} resolved." Empty forecast → no forecast block.

2) THE RECORD — two panels on one day. Top: `supabase.rpc('get_timeline', {p_day})`,
envelope `{day, sleep_text?, n, entries:[{at,kind,text,src,row_id}]}`. Date picker
2019-09-03 → today, ‹ › day arrows, "random day". Header sentence: "{n} records" plus
`sleep_text` verbatim when present. Vertical time axis; an icon per `kind` (web video
calendar money checkin consume note workout self_report). Row tap → sheet showing `src`
and `row_id`. Empty: "Nothing recorded." Bottom panel "Logged": `supabase.rpc('get_day',
{p_day})`, envelope `{day, checkin?:{<metric_key>:{point,low,high,atom_id}}, food?:[{label,at,precision,atom_id}], notes?:[{text,at,atom_id}], coverage:{captures,atoms,unextracted}, last_extract_run?:{at,status}}`.
Check-ins render as intervals "Energy 5 (4.5–5.5)" (never the point alone); food and
notes as rows; `coverage` as a footer line "{captures} captures · {atoms} atoms ·
{unextracted} unextracted" with the unextracted count amber when > 0; absent keys →
"not logged". Every `atom_id` is the trace. Search box present but disabled, tooltip
"arrives with round 4".

3) MOVEMENTS — no RPC yet. Full-screen empty state, text exactly: "Never captured.
Install the location logger to start the movement record." Nothing else.

4) SOURCES — `supabase.rpc('get_domains')`. Envelope
`{as_of, pillars:[...], domains:[{domain,pillar,display_name,replaces,sort_order, hero?:{metric,unit,value,day,trace}, coverage:{status,last_day?,stale_days?,first_day?,days_with_data?,density}, capture_action}]}`.
Five pillar groups in the order of `pillars`, headed body · movement · fuel · mind ·
life. Under each, its domains in envelope order as rows: `display_name`, `replaces` in
small type, right side `hero.value hero.unit` (tap → trace sheet) or, when `hero` is
absent, "never captured → {capture_action}" in muted text; then `<Coverage/>` and a
density word (years · months · weeks · none). Row tap → `/sources/:domain`, which in this
round shows only the same row's data plus text "Full source page arrives with round 1."

5) FINDINGS — `supabase.rpc('get_patterns')` and `supabase.rpc('register_watch', {p_hypothesis_id})`.
Envelope `{tier:'EXPLORATORY', disclaimer, calibration:{run_date,pairs_tested,observed_significant,shuffled_null_significant,null_p95?}, keystone:[{driver,outcome_families,patterns}], patterns:[{hypothesis_id,label,driver,outcome,lag_days,seeded,sentence,n_hi,n_lo,n_eff:[hi,lo],q,watched,watch_progress?:{registered_at,days_elapsed,days_needed,status}}]}`.
First line, verbatim template: "{observed_significant} significant of {pairs_tested}
tested vs {shuffled_null_significant} on shuffled data — read accordingly." Then
`disclaimer` verbatim. Then cards: badge EXPLORATORY, `sentence` verbatim, small print
"lag {lag_days}d · n {n_hi}+{n_lo} · n_eff {n_eff[0]}/{n_eff[1]} · q {q}", a Watch button
→ `register_watch` → refetch; when `watched`, replace the button with "day
{days_elapsed} of {days_needed} · {status}". Keystone → a compact table. TEXT AND
LABELS ONLY on this screen; zero charts, zero bars. Empty: "No patterns above the null
yet."

6) RELIABILITY — `supabase.rpc('get_trust')`. Envelope
`{scan_calibration:[{run,tested,observed_sig,shuffled_null_sig,null_p95}], forecasts:{resolved,inside_band,achieved_coverage,claimed_coverage,mean_brier,pending}, hypotheses:{candidates,watching,confirmed,refuted}, job_heartbeats:[{job,last,status}], coverage_blindspots:[{metric,last_day}]}`.
Opening sentence: "Claimed {claimed_coverage}, achieved {achieved_coverage}." Then four
plain tables in that order. Heartbeat rows show `last` as a relative time and `status`
verbatim. Blindspots: "{metric} — last {last_day}".

7) THE DESK — three panels.
Ask: a text box, disabled, with the text "Ask arrives when the question engine is
built." (There is no ask RPC yet; do not wire anything, do not fake an answer.)
Capture: a text box that calls `supabase.rpc('ingest_capture', {p_capture_id: crypto.randomUUID(), p_captured_at: new Date().toISOString(), p_source:'pwa_text', p_payload:{kind:'note', text}})`
and shows "Recorded." with the returned id. No other capture forms this round.
Facts: `supabase.rpc('get_insights_guarded')`, envelope `{tier:'DESCRIPTIVE', disclaimer, stream_count, fact_count, rhythms:[{metric,weekday,median,is_highest}], lists:{top_sites,top_channels,top_merchants,top_categories}, auto:[{source,metric,n,median,p10,p90,min,max,last30_median}]}`.
Header "{fact_count} facts across {stream_count} streams." then `disclaimer`, the four
top-lists as ranked text, and `auto` as a searchable table grouped by `source`
(median · p10–p90 · min–max · last30 · n); a null `last30_median` renders "not logged".
Settings: sign out; theme toggle (dark default); a "Data" line that prints `as_of` from
the last `get_domains` call.

EMPTY-STATE COMPONENT `<Empty what since action/>`: "{what}: {since ? 'not logged since '+since : 'never captured'}. {action}." Used everywhere an envelope key is absent.

ACCEPTANCE (Lovable must self-check before finishing): (a) `grep` the codebase for
`from('` — zero results; (b) every `rpc('` name is one of: get_today get_timeline get_day
get_domains get_patterns register_watch get_trust get_insights_guarded ingest_capture;
(c) no arithmetic on envelope values anywhere; (d) the word "Proven" appears nowhere;
(e) lighthouse mobile layout has no horizontal scroll at 360 px.
