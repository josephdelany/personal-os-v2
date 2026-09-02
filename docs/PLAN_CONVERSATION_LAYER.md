# PERSONAL OS — THE SELF-SCIENCE PLATFORM
## The complete master plan, thought from every angle. Four books: the Product, the Machine, the Science, the Execution.

---

# BOOK I — THE PRODUCT (designed from your life inward, not the data outward)

## I.1 The Question Atlas — the 30 questions a person asks about themselves
Every surface exists to answer a human question. The atlas maps each to its
engine, so nothing is built without a question it answers:

**Present-tense:** How am I today? (Today/E2+E9) · Why do I feel off? (E2 flags +
E8 probe) · Am I getting sick? (guardian 2-of-N + published base rate) · What
should I do differently *today*? (KEYSTONE + WATCHING) ·
**Past-tense:** What happened on [any day]? (Timeline E1) · What did last week/
month look like? (Week/Month zoom) · When did X start? (regime chapters E6) ·
Have I ever…? / When was the last time…? (records + serendipity feed) · What was
different about my best weeks? (recipe mining) ·
**Money:** Where does it go? (tops/categories) · What changed this week? (Δ
engine) · What's this month projecting to? (E5 band) · What do I not notice?
($8,983 bank fees class) ·
**Body/mind:** What actually moves my sleep/HRV/mood? (Patterns E3/E4 → Loop) ·
What does drinking really cost me? (event studies + confirmed effects) · Am I
overtraining? (ACWR-proxy + streaks) · Is my strength going up? (e1RM trend) ·
**Self-knowledge:** What are my rhythms? (weekday/hour fingerprints) · What kind
of person does my data say I am? (trait layer, months-arc, CI-carried) · What
runs my life without my noticing? (KEYSTONE leaderboard) ·
**Trust:** Why should I believe you? (Trust tab: scorecard, coverage, every
number's row-id) · What don't you know? (gaps rendered as gaps, INSUFFICIENT
answers) · What were you wrong about? (demotions shown, prediction misses
published).

## I.2 A day in the life (seven moments, what the system does in each)
**07:10 wake** — alarm-off automation stamps true wake; Today is already
composed: STATE/CONNECTION/WEEK/KEYSTONE/WATCHING/QUESTION/FORECAST (the §II.9
mock). One probe max. **08:30 breakfast** — Log Food, 10 seconds, or nothing
(absence is honest). **12:00 work** — collectors watch screen/commits silently;
nothing pings you (RULE-27). **17:30 gym** — Log Workout per set; arrival dwell
(Phase-4) will log itself. **19:00 dinner out** — the transaction lands at its
minute via Gmail; tomorrow's WEEK slot knows. **23:20 slip** — late-night screen
minutes accrue; no scolding, ever — it just becomes tomorrow's CONNECTION if the
pattern is real. **23:55 night check-in v2** — 5 scores + note + food catch-all;
sleep architecture arrives by itself overnight. **Total demanded of you: under
two minutes. Everything else is ambient.**

## I.3 Time as a zoomable interface (six levels, one data spine)
**Minute** (E1 Timeline) → **Day** (Day tab) → **Week** (deviations vs you) →
**Month** (chapter: regimes, records, top patterns that month) → **Year** (the
Annual Report of You: v1 = auto-compiled markdown — totals, records, chapters,
confirmed findings, best/worst weeks, the year's KEYSTONE) → **Life** (era view:
regime chapters end-to-end over the 7-year panel + "on this day" across years).
One RPC family (`get_zoom(level, anchor)`), one renderer, six altitudes.

## I.4 The Life Ledger (the system as autobiography)
Deterministic narrative artifacts, template-rendered, archived immutably:
**Weekly Review** (Sun: what happened, what deviated, what advanced in the loop,
next week's watchlist) · **Monthly Chapter** (readable prose-of-record from the
same slots + records + regime shifts) · **Annual Report** (the book of your
year). All exportable (REQ-NAR-037), all LLM-optional (RULE-15: templates render
alone; Workers-AI polish is a garnish within the free 10k neurons/day, never a
dependency, every call egress-logged).

## I.5 The serendipity feed (honest surprise, the anti-plateau)
Rotating, novelty-guarded: **on this day** (1/2/5 years ago, from the Timeline) ·
**first-evers & last-times** ("first logged lift since May 13", "longest gap in
bar spending this year") · **rarities** ("today's 31,015 steps: #1 all-time") ·
**quiet milestones** ("1,000th logged capture"). Zero judgment, pure memory —
the feature that makes opening the app feel like meeting yourself.

## I.6 Voice (talk to it)
A "Ask my OS" Siri shortcut → E7 Ask endpoint → spoken/displayed answer with its
n. Ten-second build once Ask v1 lands; the closed operation registry makes voice
SAFE (no free-form compute reachable).

## I.7 The Trust tab (the system's own report card, first-class)
Forecast coverage vs claimed (87% inside band) · prediction Brier trend ·
confirmations vs refutations count · demotions log (public) · per-domain
coverage/staleness · every scan's null-calibration numbers (I.12) · "what I
cannot see" (dead streams, gaps). **Trust is a product surface, not a vibe.**

## I.8 Anti-abandonment engineering (the red-team of engagement, no gamification)
Failure modes designed against: *novelty decay* → serendipity + weekly freshness
guarantee (no repeated CONNECTION within N days — novelty guard ported) ·
*capture fatigue* → ambient-first bias (12 of 19 live streams need zero taps),
probe cap 1/day, absence never punished · *insight plateau* → the loop keeps
raising stakes (exploratory→confirmed→recommendation), KEYSTONE re-ranks weekly,
new streams (Spotify/search/place) stage in over weeks · *trust erosion* → Trust
tab + demotions shown > hidden · *single-point death* → keepalives, heartbeats,
staleness alerts on every job, HANDOFF doc, everything re-derivable from
immutable captures.

---

# BOOK II — THE MACHINE (the complete engineering core)

## II.1 Asset ledger (all mined, all assigned)
OLD workspace: `baselines.py` (median/MAD, EWMA-detrend, dual-z 7/28d,
changepoint-aware) → E2 · `changepoint.py` (PELT rbf pen4 min14d + BOCPD h=1/120)
→ E2/E6 · `event_study.py` (DoW-reweighted contrasts, bootstrap, permutation) →
E4 · `conformal.py` (adaptive conformal, online α) + `forecast.py` → E5 ·
`validity.py` (degeneracy n<30/modal>90%, staleness budgets) → universal gate ·
guardian+`guardian_leadtime.py` (2-of-N + backtested lead-time/precision) →
E2+I.7 · `brief_morning.py` 4-slot + novelty guard → E9 · `select_probes.py` +
`checkin_probes` (13 trigger-keyed questions, recovered verbatim) → E8 ·
**`HYPOTHESIS_LIBRARY.md`: 130+ hypotheses, 12 themes, 5 validated anchors, 14
phenotypes, top-20 narratives** → E3 seeds + months trait layer ·
`insights_catalog` (1,191 rows) → the 10-family typology + KEYSTONE design ·
`daily_series.csv` **2,382 days 2019→2026** → panel depth · `merchant_map.json`
(~1k) + `yt_channel_map` + `content_taxonomy` (661) → naming layers ·
`first_analysis_report.md` measured priors (REM↔HRV +.645, sleep↔HRV +.606,
sleep↔RHR −.503, deep↔HRV +.547, HRV↔RHR −.449) → seed cross-check ·
`03_data_in`: **Spotify 50k plays · Google Search history · Chrome History.json ·
bank CSVs** → parsers · `health_raw` parquets (gait 51k, HR 49k, sleep 20k) →
granular surfacing · 34 archived briefs → E9 voice · Edge Function sources →
bridge fidelity · `METHODOLOGY.md`/`DIGITAL_TWIN_SPEC.md`/`INSIGHT_ENGINE.md` →
months-arc specs.
NEW system (live): immutable spine + 23 metrics · ingress RPC + bridge + hourly
extractor · owner-locked get_day/get_insights (1,338 facts) · deployed app ·
hypothesis_register (freeze trigger + clock CHECK) · predictions table ·
findings/tier_history/links/prompt_dispatch · 632-REQ spec · 37 ADRs · 38-check
gate · proof harness · reviewer discipline · keepalives · revived collectors ·
phone fleet (3 shortcuts imported).

## II.2 Input matrix — 34 streams
🟢 flowing: ActivityWatch/Chrome/YouTube (revived) · Gmail-receipts→txns · Gmail
contacts · calendar · weather · extractor+bridge lanes. 🟡 lagging: watch
activity, Withings. 🔵 awaiting taps: morning/night-v2 check-ins, Log Food, Log
Workout, health-harvest automation. 📦 on disk: Spotify, search history, Takeout
Chrome, bank CSVs, daily_series 2019→, health_raw granular. 🔴 revival: sleep/
HRV/vitals (drop or harvest), probes (E8), air quality, locations (Phase-4).
⚪ future: wake/focus/charge/CarPlay automations (30-sec setups), CGM/H10/env
sensors behind RULE-28 ADRs.

## II.3 Panel dictionary (~90 daily variables)
sleep(16): asleep, inbed, efficiency, deep/deep%, rem/rem%, core, onset, waso,
midpoint, awakenings, span, debt-7d, SRI, jetlag · heart(8): sdnn rmssd pnn50
rhr_night resp_night wrist_temp hr_min hr_max · body/move(10): steps kcal exmin
weight gait-speed step-length asymmetry steadiness walking-hr trimp · train(5):
sets volume e1rm/lift per-ex-volume days-since · mind(11): checkin scores ·
food(6): meals late-meal alcohol-items ethanol-g caffeine-proxy water · money(8):
total count dining groceries retail late-night novel-merchant variance-7d ·
attention(8): active-hours sessions binge-min max-binge late-screen switches
chrome-ev yt-ev · media(6): yt-videos yt-late spotify-min spotify-late
artist-novelty top-channel-share · search(3) · work(4) · social(3) · place(4,P4)
· environment(5). All registry-known, validity-gated, NULL-honest (REQ-INF-505).

## II.4 The insight catalog — ten families × five classes
Families (from the old registry's proven typology, produced honestly): link
(1,066 in old) · trend · state · record · rhythm · trait · recipe · mediation ·
latent · **KEYSTONE** ("reduce binge-length — it appears in 5 of your strongest
patterns": cross-pattern driver ranking, free from E3's table). Classes:
[D]escriptive [Δ]eviation [P]attern [F]orecast [C]onfirmed. Full domain-by-domain
sentence catalog as previously enumerated (sleep/heart/training/food/money/
attention/media/mind/work/search/place/env — ~150 named example sentences,
hundreds live at scale: 5 classes × 90 vars + 12k scanned pair-lags FDR-gated +
30 seeds + KEYSTONE, compounding weekly).

## II.5 The named seed manifest (~30, day-one)
sleep⇄HRV(+.61 prior) · REM⇄HRV(+.645) · sleep⇄RHR(−.503) · deep⇄HRV(+.547) ·
HRV⇄RHR(−.449) · resp⇄RHR(+.393) · YouTube-binge→bar-spend(0-7d, validated) ·
SRI→discretionary-spend(+3d, validated) · heavy-spend⇄sleep(bidir, validated) ·
circadian-frag→gait(+7d, validated) · alcohol-evening→HRV(−37% measured)/RHR/
deep% · late-screen→onset/efficiency · late-meal→efficiency/wrist-temp ·
hard-session→RHR(≈4d) · meetings→commits · low-mood→retail · spend-variance→
stress-proxies · daylight→mood/timing · caffeine-proxy→deep% · weekend-jetlag→
Monday-state · steps→sleep · music-late→onset (once parsed) · search-bursts→
sleep/mood (once parsed) — plus the discovery sweep behind them.

## II.6 The twelve engines
E1 TIMELINE minute-merge RPC (2,500 reconstructable days) · E2 BASELINE/STATE
(ports: dual-z, bands, streak run-lengths vs history, changepoint resets, 2-of-N
guardian w/ base rate) · E3 CONTRAST SCAN (seeded+discovery, within-person
quartile contrasts, weekday-partialled, lags{0,1,2,7}, Mann-Whitney,
n_eff=n(1−ρ)/(1+ρ), BH-FDR, n≥30/side, top-K/domain → CANDIDATE rows,
mined_from_preexisting=true) · E4 EVENT-STUDY (bar-evenings/late-screen/workout
days vs DoW-matched, permutation p) · E5 FORECAST+CONFORMAL (per headline
metric; each forecast a predictions row; nightly resolver → Brier+coverage) ·
E6 REGIME CHAPTERS · E7 ASK v1 (closed ops {median,sum,trend,compare_windows,
top_k,on_days_when}; numerals row-bound) · E8 PROBE ENGINE (13-question bank,
E2-triggered, 1/day, answers→atoms) · E9 BRIEF COMPOSITOR (7 slots,
novelty-guarded, template-first) · E10 KEYSTONE AGGREGATOR · E11 CONFIRMATION
JOB (weekly, post-registration data only — DB-enforced clock; auto-promote
language / auto-demote on misses) · E12 DISCOVERY+ (months-arc: PCMCI+ ≤20-var
blocks, spec curves, negative controls, mediation, HMM, trials, twin).

## II.7 The loop (worked twice)
Cascade: scan → "+$31 bar-spend after top-quartile late-YouTube (n=180/177,
q=.004, exploratory)" → [Watch] → frozen registration (trigger-enforced) →
future-days-only clock → confirmed ⇒ language upgrade + forward predictions ⇒
misses ≥50% @n≥3 auto-demote, shown. Guardian: 2-of-N fires → WATCH slot + E8
asks → answer becomes evidence → backtest publishes YOUR lead-time & precision.

## II.8 Surfaces
Today (the mock) · Timeline · Patterns (RULE-17-proven EXPLORATORY surface,
text-only, [Watch] buttons, clocks) · Ask · Trust (I.7) · Insights (live 1,338) ·
Day · Week/Month/Year/Life zooms (I.3) · Ledger archive (I.4) · voice (I.6).
All owner-locked; every numeral → row-id.

## II.9 Ops schedule (all $0, all heartbeated)
live: keepalives(daily) · extract(hourly) · collectors(6h) · physiology(nightly)
· gates(push). NEW: analysis-nightly (panel→validity→baselines→state→forecasts→
resolver→brief) · analysis-weekly (scan→keystone→confirmations→weekly review) ·
probe-queue (with state) · ledger-monthly/annual.

---

# BOOK III — THE SCIENCE (honesty as measured results — the submission's spine)

## III.1 The evaluation harness (benchmark the system on its own claims)
**(a) Null calibration:** every scan runs a shuffled-panel twin (circular-shift
preserving autocorrelation); report observed-vs-null discovery counts — the
false-positive rate is PUBLISHED per run (old system's fatal flaw, made into a
headline feature). **(b) Negative-control injection:** synthetic no-relationship
pairs seeded into the scan family; any survivor halts promotion and flags the
pipeline (design from REQ-INF-506..508, v0 form). **(c) Guardian backtest:** on
7-year history — lead-time distribution + precision/false-alarm of the 2-of-N
signature (guardian_leadtime.py port). **(d) Forecast coverage:** claimed 90% vs
achieved, rolling. **(e) Split-half stability:** every reported contrast
re-checked on independent halves; instability shown. **The submission's
evaluation section = these five tables from real runs. Nobody grades "trust me";
they grade measurements.**

## III.2 The self-experiment engine (v0, honest, consent-first)
For watched-but-unconfirmable hypotheses: propose a randomized week-plan
("screen-cutoff 23:00 on randomized days, 3 weeks; ~power at your effect
size"), one-tap accept/decline (never re-asked <7d, RULE-27; boundary-respecting
REQ-INF-216-217 spirit), assignment seeded+stored, adherence via E8 probe
(`experiment_comply` — the question already exists in the recovered bank),
analysis at n_blocks with ITT + HAC. **v0 = propose/assign/track only;
EXPERIMENTAL-tier language stays locked until the full REQ-INF-200..219
machinery lands (months-arc). The fastest honest road from correlation to
causation, in your own life.**

## III.3 The 12-month science arc (from their own deepest specs, constitution-gated)
M2-3 mediation paths + negative-control battery + PCMCI+ blocks (E12 opens) ·
M3-5 micro-trials full machinery + recipe-mining of top-decile weeks · M5-8
latent-state HMM ("what state am I in", REQ-INF-540..547) + trait table with CIs
(chronotype, substance-sensitivity, recovery-resilience — the 14 phenotypes) ·
M8-12 digital-twin stages 0→1 (observational what-ifs → graph interventions:
"cut late screen 30m ⇒ sleep +22–41m expected") + autonomous weekly analyst +
Lovable rich UI. Same gates at every rung.

## III.4 The autonomous analyst (the system as employee, Claude-free)
Job description: nightly — refresh, compose Today, resolve forecasts, queue
probes; weekly — scan, keystone, confirmations, Weekly Review, Trust refresh;
monthly — Chapter, staleness audit; always — heartbeat every run, render every
failure loudly. Stack: deterministic engines + templates (LLM-zero core); prose
polish optionally via Workers AI inside the free tier (egress-logged, RULE-15
degradable). **After your subscription ends, the analyst keeps working. That is
the design.**

---

# BOOK IV — EXECUTION

## IV.1 The 48 hours
**TONIGHT** T1 migrations 0026-28 (analysis schema · CANDIDATE widening ·
legacy_daily 2019→ load) → T2 panel+validity+baselines ports + probe
(hand-check vs measured priors) → T3 E1+E2 RPCs + probe → T4 Today(v1)+Timeline
tabs deployed. **DAY-2 AM** U5 E3 seeded+discovery → Patterns + RULE-17 proof +
Watch RPC → U6 E4 → U7 E10 keystone + null-calibration table (III.1a). **DAY-2
PM** U8 E5+resolver+Trust v1 → U9 E9 full Today + E8 probe queue → U10 E7 Ask ✂
→ U11 reviewer sweep → SUBMISSION.md (Book-III results inside) → final deploy.
✂ under pressure: Ask → E8 → parsers (week-1); the spine T1-U8 is non-negotiable.
**WEEKS 1-4:** Spotify/search/bank parsers · confirmations mature · scorecard
fills · automations · experiment-v0 first proposal. **M2-12:** Book III arc.

## IV.2 Deliverables tree
migrations/0026-0031 (analysis schema · candidate-status · legacy_daily ·
timeline · state · patterns/watch/ask APIs) · tools/engines/{panel,validity,
baselines,changepoint,state,scan,event_study,forecast,keystone,brief,confirm,
probe_queue}.py · tools/parsers/{legacy_daily,spotify,search_history,bank_csv}.py
· tools/eval/{null_calibration,guardian_backtest,coverage_report}.py ·
tools/_probe_{panel,state,scan,loop}.py · .github/workflows/analysis.yml ·
app/index.html (Today·Timeline·Patterns·Ask·Trust tabs + zooms v1) ·
docs/adr/0038-0042 · docs/SUBMISSION.md · updated HANDOFF/LOVABLE docs ·
PROGRESS per unit.

## IV.3 Verification & demo script
Per-unit rolled-back probes with pasted output → live: a 2025 day reconstructs ·
real dollars in WEEK slot · ≥20 patterns with n/q · frozen registration verified
in DB · forecast resolves into Trust · null-table published · gates 38/0/0 ·
invariants ALL PASS. **Demo:** Today (read yourself) → Timeline (a random 2025
Tuesday) → Patterns → Watch (show the frozen row + clock) → Trust (the system
grading itself) → the constitution close: "this system cannot lie to me — and
here are the 1,413 lies the old one told, as the control group."

## IV.4 Honest boundaries & anti-scope
Hedged language until earned — the thesis, not a gap · "down to the minute" =
every day the collectors covered; gaps render AS gaps and are themselves data ·
your taps remain the one unbuildable input; history carries the demo regardless ·
no Phase-6 machinery faked early; no photo pipeline yet; no content-level text
mining ever (counts only); no Lovable build now (contract updated); no spend,
anywhere, at any stage.
