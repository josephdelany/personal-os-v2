# Resume "My Life Compass" — the rewiring round (paste into your EXISTING Lovable project)

**Where:** lovable.dev → your project **My Life Compass** (`e410d482-dd93-4c0f-a79b-6db0a2e0fe9b`).
Credits blocked it on 2026-07-26; they've refreshed. Paste everything below the line as one
message. This keeps every visual decision you already made and swaps the guts.

---

REWIRING ROUND — keep the design, replace the data layer.

Keep exactly as-is: the dark-teal oklch design system and src/styles.css tokens, phone-first
bottom tab bar + desktop bento, PWA manifest/service worker, tabular-nums, 200-300ms ease-out
motion, THE RULE (verdict before charts — every screen leads with one honest sentence, then
evidence). Do NOT restyle. This round only changes where data comes from and what screens exist.

The backend moved to a new, stricter system in the same Supabase project. Remove ALL reads of
the old tables/RPCs (day_timeline, signals, insights, events, anything touching public tables
directly). The new contract is six owner-locked RPCs — every screen is exactly one call, no
client-side computation ever, "owner only"/permission errors mean sign-in (magic-link auth,
signInWithOtp), never a bug.

New tab set (bottom bar): **Today · Timeline · Patterns · Trust · Insights · Log**

1) TODAY — supabase.rpc('get_today'). Envelope:
{"for_day","based_on","state":{"deviations":[{"metric","value","z","band":[lo,hi]}],
"streaks":[{"metric","run_days","direction","historical_max_run"}],
"guardian":{"signals_firing","threshold","fires_historically"},
"week_money":[{"name","grain","this_week","typical_week","delta"}]},
"patterns_waiting":{"count","note"},"watching":[{"hypothesis","registered","day","of","status"}],
"forecast":[{"metric","lo","point","hi"}],
"forecast_track_record":{"resolved","inside_band","claimed_coverage","achieved_coverage"}}
Verdict sentence first (calm when unremarkable: "In your normal bands."). Guardian = amber
banner only when present, verbatim wording ending "A pattern match, not a diagnosis."
Deviations as metric rows with the personal band as a range bar + value position. Week-money
as delta chips. Watching as day-N/30 progress bars ("verdict pending"). Forecast as range
bars with the track-record line in small print. patterns_waiting renders ONLY as a count that
links to Patterns — never pattern content here (hard rule).

2) TIMELINE — supabase.rpc('get_timeline',{p_day}). {"day","sleep_text","n","entries":
[{"at","kind","text","src","row_id"}]}. Date picker (2019→today), vertical time axis, icons by
kind (web/video/money/calendar/checkin/consume/note/workout/self_report), sleep_text as
subheader, "random day" shuffle. Empty day: "nothing recorded".

3) PATTERNS — supabase.rpc('get_patterns') + supabase.rpc('register_watch',{p_hypothesis_id}).
{"tier":"EXPLORATORY","disclaimer","calibration":{"run_date","pairs_tested",
"observed_significant","shuffled_null_significant","null_p95"},"keystone":[{"driver",
"outcome_families","patterns"}],"patterns":[{"hypothesis_id","label","driver","outcome",
"lag_days","seeded","sentence","n_hi","n_lo","n_eff":[..],"q","watched","watch_progress"}]}
HARD RULES (the product itself): text/labels ONLY on this screen — zero charts. Every card
wears a visible EXPLORATORY badge. Sentence verbatim; n/n_eff/q in small print. Calibration
line at top verbatim: "X significant of N tested vs M median (P p95) on shuffled data — read
accordingly." Watch button → register_watch → refetch; watched cards show the day/30 clock.
Keystone = compact leaderboard. Prettify metric names for display (strip prefixes,
title-case), raw name in tooltip.

4) TRUST — supabase.rpc('get_trust'). {"scan_calibration":[...],"forecasts":{"resolved",
"inside_band","achieved_coverage","claimed_coverage","mean_brier","pending"},
"hypotheses":{"candidates","watching","confirmed","refuted"},"job_heartbeats":[{"job","last",
"status"}],"coverage_blindspots":[{"metric","last_day"}]}
An audit page: claimed-vs-achieved coverage side by side, the scan honesty ledger as a table,
lifecycle counts, heartbeat dots, and "What I cannot currently see" as a plain amber list.
Misses exactly as visible as hits.

5) INSIGHTS — supabase.rpc('get_insights_guarded'). {"tier":"DESCRIPTIVE","disclaimer",
"stream_count","fact_count","rhythms":[{"metric","weekday","median","is_highest"}],
"lists":{"top_sites","top_channels","top_merchants","top_categories"},"auto":[{"source",
"metric","n","median","p10","p90","min","max","last30_median"}]}
Header: "1,338 facts across 223 streams, computed live." Rhythm headline cards; ranked
top-lists; the auto battery as a searchable table grouped by source (median · p10–p90 ·
min–max · 30d · n). Null last30 renders "—", never 0. Descriptive charts allowed here — each
BELOW its verdict sentence.

6) LOG — supabase.rpc('get_day',{p_day}). Check-in scores AS INTERVALS ("Energy 5 (4.5–5.5)"),
food, notes, workout sets, coverage footer; unextracted count amber; absence = "not logged".

Honesty rules to bake into components (unchanged from Project Knowledge, now enforced):
render only envelope numerals (no client math, no invented values; missing → "not logged"/"—");
self-reports always show intervals; no judgment words ever (good/bad/too much/wasteful);
exploratory content only on Patterns; no charts for exploratory items anywhere; errors are
honest states, not empty fakes.

Summarize the diff when done. No paid integrations, no DB writes from the app, no new backend.
