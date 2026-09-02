# Lovable build package — Personal OS front end (v2, current)

**How to use:** paste everything below the line into Lovable as your first prompt.
When it asks about Supabase, use Lovable's native Supabase integration with your
project (`cykviouklidnbsbgdgdo`) and your anon key from the dashboard. The whole
backend is done and frozen — six RPCs, owner-locked, every envelope stable
(fields get added, never renamed). Your job in Lovable is purely visual.

---

Build "Personal OS" — a personal life-analytics app for one user (me), React +
Tailwind, dark-first, on my EXISTING Supabase backend. Do not create tables. Do
not compute anything client-side. Every screen is one RPC call rendering one
JSON envelope. Design language: calm, editorial, generous whitespace, tabular
numerals for all numbers, subtle 150ms ease-out transitions only — think a
premium reading app (Whoop's polish, a newspaper's restraint). No streaks, no
badges, no rings, no confetti, no gamification of any kind, ever.

## Auth
Supabase Auth, email magic-link (signInWithOtp). Every RPC is server-locked to
my identity — an error string "owner only" or a permission error means "sign
in", not a bug. No service keys client-side.

## Screens (bottom tab bar or left rail): Today · Timeline · Patterns · Trust · Insights · Log

### 1 · TODAY — `supabase.rpc('get_today')`
Envelope:
```json
{ "for_day":"2026-09-03","based_on":"2026-09-02",
  "state":{ "deviations":[{"metric":"hrv_sdnn","value":41,"z":-1.8,"band":[44,71]}],
            "streaks":[{"metric":"rhr","run_days":3,"direction":"above","historical_max_run":8}],
            "guardian":{"signals_firing":2,"threshold":2,"fires_historically":9},
            "week_money":[{"name":"HUMDINGERS","grain":"merchant","this_week":94,"typical_week":24,"delta":70}]},
  "patterns_waiting":{"count":19,"note":"exploratory patterns await on the Patterns tab (pull to read)"},
  "watching":[{"hypothesis":"screen_binge_min|sleep_asleep_min|L1","registered":"2026-09-02","day":4,"of":30,"status":"INSUFFICIENT"}],
  "forecast":[{"metric":"sleep_asleep_min","lo":206,"point":370,"hi":535}],
  "forecast_track_record":{"resolved":12,"inside_band":11,"claimed_coverage":0.9,"achieved_coverage":0.92} }
```
Layout: a hero card for state (calm if no deviations: "in your normal bands");
guardian as an amber banner ONLY if present, verbatim: "N autonomic signals
outside band together — this combination has occurred X times in your history.
A pattern match, not a diagnosis." Deviations as quiet metric rows with the
personal band drawn as a subtle range bar and the value's position on it.
Week-money as delta chips (+$70 emphasized, merchant name, "vs $24 typical").
Watching as progress bars labeled "day 4 of 30 — verdict pending". Forecast as
range bars with the track-record line underneath in small print. The
patterns_waiting count is a single tappable line that navigates to Patterns —
never render pattern content here (hard rule).

### 2 · TIMELINE — `supabase.rpc('get_timeline',{p_day:'2025-03-04'})`
```json
{ "day":"2025-03-04","sleep_text":"slept 6h12m","n":41,
  "entries":[{"at":"00:50","kind":"video","text":"…","src":"youtube","row_id":"…"}] }
```
A date picker (support any date 2019→today) + a beautiful vertical time axis.
kind → icon: web 🌐 video ▶ money 💵 calendar 📅 checkin 📝 consume 🍽 note ✏️
workout 🏋 self_report 📝. Group tight clusters; money entries slightly
emphasized. Show sleep_text as the day's subheader. Empty day: "nothing
recorded" — never invent. A "random day" shuffle button is welcome.

### 3 · PATTERNS — `supabase.rpc('get_patterns')` + `supabase.rpc('register_watch',{p_hypothesis_id})`
```json
{ "tier":"EXPLORATORY","disclaimer":"…","calibration":{"run_date":"2026-09-02",
  "pairs_tested":7062,"observed_significant":123,"shuffled_null_significant":87,"null_p95":102},
  "keystone":[{"driver":"steps","outcome_families":2,"patterns":4}],
  "patterns":[{"hypothesis_id":"scan:…","label":"EXPLORATORY","driver":"…","outcome":"…",
    "lag_days":1,"seeded":false,"sentence":"On your highest-… days, … This may reflect a pattern; it is exploratory and unverified.",
    "n_hi":210,"n_lo":208,"n_eff":[180.5,178.2],"q":0.0021,"watched":false,
    "watch_progress":null}] }
```
HARD RULES (these ARE the product): text and labels only — NO charts, plots, or
graphs anywhere on this screen. Every card wears a visible EXPLORATORY badge.
Render the sentence verbatim; show n/n_eff/q in small print. The calibration
line renders at top, verbatim numbers: "123 significant of 7,062 tested vs 87
median (102 p95) on shuffled data — read accordingly." Watch button per card →
register_watch → re-fetch; watched cards show the day/30 clock. Keystone as a
compact leaderboard ("appears in 4 patterns across 2 life domains — exploratory").
Prettify metric names for display (strip prefixes, title-case: 
"screen_binge_min" → "Screen binges (min)") but keep the raw name in a tooltip.

### 4 · TRUST — `supabase.rpc('get_trust')`
```json
{ "scan_calibration":[{"run":"2026-09-02","tested":7062,"observed_sig":123,
   "shuffled_null_sig":87,"null_p95":102,"null_reps":5}],
  "forecasts":{"resolved":12,"inside_band":11,"achieved_coverage":0.92,
   "claimed_coverage":0.9,"mean_brier":0.03,"pending":5},
  "hypotheses":{"candidates":19,"watching":2,"confirmed":0,"refuted":0},
  "job_heartbeats":[{"job":"extract_checkins","last":"…","status":"ok"}],
  "coverage_blindspots":[{"metric":"hrv_sdnn","last_day":"2026-07-28"}] }
```
This is the system grading itself — design it like an audit page: claimed vs
achieved coverage side by side, the scan honesty ledger as a table, hypothesis
lifecycle counts, green/amber heartbeat dots, and "what I cannot currently see"
as a plain amber list. Refutations and misses must be exactly as visible as
successes.

### 5 · INSIGHTS — `supabase.rpc('get_insights_guarded')`
```json
{ "tier":"DESCRIPTIVE","disclaimer":"…","stream_count":223,"fact_count":1338,
  "rhythms":[{"metric":"sleep (min)","weekday":"Tuesday","median":404,"is_highest":true}],
  "lists":{"top_sites":[{"site":"google.com","visits":1454}],
           "top_channels":[{"channel":"Al Jazeera English","videos":242}],
           "top_merchants":[{"merchant":"…","txns":25,"total":747}],
           "top_categories":[{"category":"dining","txns":130,"total":2584}]},
  "auto":[{"source":"apple_sleep","metric":"efficiency","n":84,"median":0.96,
           "p10":0.89,"p90":0.99,"min":0.6,"max":1.0,"last30_median":null}] }
```
Header: "1,338 facts across 223 streams, computed live." Rhythms as headline
cards ("Your sleep peaks on Tuesdays — 6h44m median"). Top-lists as ranked
lists. The auto battery as a searchable/filterable table grouped by source:
median · typical range (p10–p90) · extremes · last-30d · n. Every number shows
its n. Missing last30 renders as "—", never 0.

### 6 · LOG (capture status) — `supabase.rpc('get_day',{p_day})`
The capture view: check-in scores AS INTERVALS ("Energy 5 (4.5–5.5)"), food
list, notes, workout sets, and the coverage footer ("3 captured · 9 facts ·
last processed …"; unextracted count in amber). Absence = "not logged".

## Non-negotiable honesty rules (bake into components, not habits)
1. Render ONLY numerals present in envelopes — never compute, never round
   beyond display, never invent. Missing key → "not logged"/"—", never 0.
2. Self-reports always show their interval, never a bare point.
3. No judgment language anywhere: never "good/bad", "too much", "unhealthy",
   "wasteful". Numbers get labels, not verdicts.
4. EXPLORATORY content lives ONLY on Patterns. The Today count-link is the
   maximum allowed elsewhere.
5. No charts on Patterns (text/labels only). Charts allowed on Insights/Log for
   DESCRIPTIVE data only, always below their text, never for exploratory items.
6. Errors render as honest states ("read unavailable — are you signed in?"),
   never as fake empty data.
7. Tabular numerals everywhere; motion 150ms ease-out opacity/transform only.

## v2 later (do not build now)
Zoom levels (week/month/year), the Ask box, serendipity feed, probe prompts —
the backend contracts will arrive as new RPCs in this same envelope style.
