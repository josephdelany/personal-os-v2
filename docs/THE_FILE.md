# THE FILE — the design, section by section

*Developed from `WHAT_THIS_IS.md` (confirmed by Joe, 2026-09-02). This is the
document the Lovable rounds are cut from. Each section below is one screen
family, one envelope, one round.*

> A case file on you, kept by an agency that works only for you, that cannot
> lie, and that knows you better than you know yourself.

---

## Part I — The language of the file (cross-cutting, built once)

Everything on every screen obeys these. They are the product's identity.

**The opening sentence.** Every screen, every section, every card leads with
one honest sentence before anything visual. Calm when unremarkable: "In your
normal bands." Direct when not: "Resting heart rate 8 above your band for the
third day." The sentence is computed server-side and rendered verbatim. Charts
are evidence beneath it, never the headline.

**The confidence vocabulary.** Six words, and nothing else may appear on a
claim: DESCRIPTIVE · EXPLORATORY · WATCHING · CONFIRMED · REFUTED ·
INSUFFICIENT. No stars, no "proven," no "strong," no percentages of
confidence. The word is a badge on the card; its meaning is one tap away.

**The coverage vocabulary.** Every source and every metric carries one of:
`fresh` · `stale · Nd` · `not logged` · `never captured`. Stale is a colour
and a number, never hidden. "Not logged" is a value, never zero.

**Provenance.** Every number is tappable. Tap → the atom ids behind it → the
capture they came from → the source. No dead ends. If a number can't trace,
it doesn't render.

**The empty-state doctrine.** Empty is normal and the file says so plainly:
what's missing, since when, and the *one* action that fills it — a Shortcut,
an export, a reconnect. Never a placeholder chart, never a sample, never a
zero.

**The refusal string.** When the file can't answer — out of registry, not
enough data, can't compute — it says exactly that, verbatim from a stored
string, and names the nearest thing it *can* answer.

**What never appears.** Rings. Streak flames. Badges. Celebrations. Scores of
scores. "Good day / bad day." "Too much." "You should have." Charts for
anything exploratory. Numbers the envelope didn't send.

**The look.** Dark by default. Dense. Tabular numerals everywhere. One
typeface. Motion 150–300 ms ease-out, honours reduced-motion. Desktop: a left
rail of seven sections and a bento of the current one. Phone: bottom bar with
Assessment · Record · Sources · Findings · Desk, and Movements + Reliability
under a fifth "more." A reading room, not a scoreboard.

---

## Part II — The seven sections

### 1 · ASSESSMENT — today

*What the analyst would tell you if you walked in this morning.*

**Opens with** the day's sentence: state vs your bands, plus the collection
gap in the same breath — *"In your normal bands. Two sources stale, nothing
logged since Tuesday."*

**Then, in order:**

- **State.** Each metric that's outside its personal band today, as a range
  bar with the band shaded and your value marked. Nothing inside its band is
  listed — silence is the signal that things are normal.
- **The instruction.** One recommendation, at most. Its tier, its uncertainty,
  what would raise it, and the prediction it's making about tomorrow. If there
  isn't one worth making, the block says "No instruction today" — not a
  generic tip.
- **Forecast.** Tonight and tomorrow for the metrics that have one: point,
  band, and *beside it* the track record — "claimed 80% coverage, achieved 74%
  over 31 forecasts." A forecast never renders without its record.
- **Guardian.** Only when firing. Amber. The verbatim text ends with "A
  pattern match, not a diagnosis."
- **Collection.** What's stale, what's never captured, what fills it. This
  block is *on* Assessment because the gap *is* part of the assessment.
- **Findings waiting.** A count and a link. Never pattern content here — that
  is a hard rule (RULE-17): exploratory findings are pulled, never pushed.
- **Money this week.** Delta chips vs a typical week, retrospective only. No
  running counter, no budget bar.

**Reads:** `get_today` + the coverage block of `get_trust`.
**Empty:** "Nothing to assess. Last capture: N days ago. → Log something."

### 2 · THE RECORD — every day since 2019

*The raw file. Everything that was captured, in the order it happened.*

- **Day view.** Date picker back to 2019, keyboard arrows, "random day." A
  vertical time axis. A colour ribbon along it — sleep → wake → work → meals →
  evening — from the stages and blocks the file actually has. Every entry:
  time, kind icon (web / video / money / calendar / check-in / consume / note /
  workout / place / self-report), one-line text, source, atom id on hover.
  Sleep as a subheader at the top of the day.
- **Search.** Across every entry, every year: "McDonald's," "gym," "bar,"
  "flight." Results are entries with their day; tap → that day.
- **The ledger.** A second view: raw captures as they arrived — what was
  captured, when, what it extracted into, what's still pending, what was
  corrected and by whom. This is the audit trail of the file itself.
- **Counts.** Every day header: N logged · N confirmed · N proposed.

**Reads:** `get_timeline(day)`, `get_day`, plus a search RPC (gap).
**Empty day:** "Nothing recorded." — and if it's *today*, the log button.

### 3 · MOVEMENTS — where you were

*The location tracer. Its own section because it cross-references everything.*

- **Opens with** last known place and how long you've been there — a place
  *label*, never a coordinate: "Home, since 22:14."
- **Today's movements.** Places in order with arrival, departure, dwell. A
  list, not a map, by default; a descriptive map is allowed as evidence below
  it (RULE-29: places at ~100 m, home never plotted).
- **The places register.** Every named place: visits, dwell distribution,
  arrival/departure histograms, first and last seen. Sorted by time spent.
  Tap a place → its page: the visits, and what else the file knows happened on
  those days (spend at that merchant, drinks logged, next-day state) —
  labelled EXPLORATORY where it's an association, DESCRIPTIVE where it's just
  co-occurrence.
- **Ground truth.** Gym attendance from presence, not self-report. Bar dwell
  from presence, not memory. These two lines are why this section exists —
  the objective function and the least honest self-report both get an
  independent witness.
- **Mobility.** Radius of gyration, location entropy, home-stay fraction,
  novelty (new places per week), commute and transit load — as trends with
  personal bands. These are derived measures; they wear DESCRIPTIVE.
- **Trips.** Multi-day away-from-home spans, auto-detected, listed.

**Reads:** `get_movements(day)`, `get_place(id)` — **both gaps**; REQ-LOC
exists, the RPCs don't.
**Empty:** "Location capture not yet active. → Install the Shortcut." Then,
once active: "N days of movement. Nothing before 2026-07."

### 4 · SOURCES — the collection disciplines

*Every domain, at full depth, from one skeleton.*

**The index.** Five pillars — Body · Movement · Fuel · Mind · Life. Under each,
its sources as rows: name, the app it replaces in small type, latest value,
coverage badge, density (years / months / weeks / none). Ordered richest
first within each pillar. Tap → the source page.

**The source page — the nine modules, developed.**

1. **Hero.** Latest value, personal band shaded, where you sit in it, the
   sentence. Coverage badge in the corner. If stale: the sentence says so
   first.
2. **Why.** The sub-factors that make up the hero, each with its own delta
   vs baseline, drags marked. (Sleep: stages, onset, wake-after-onset,
   midpoint. Finance: categories, merchants, frequency. Attention: sessions,
   binge runs, late-night share.)
3. **History.** The series, 7d / 30d / 90d / 1y / all, with the rolling
   personal band. Tap a point → that day in THE RECORD. Changepoints marked.
4. **Rhythm.** Weekday bars, hour-of-day bars, season — each vs your own
   average. "Highest on Thursdays" as a sentence above the bars.
5. **Notables.** Anomalies (2-of-N), changepoints, records — as plain dated
   facts. "Longest night since March: 8h41m on the 12th." No badges.
6. **What drives this / what this drives.** Two lists. Each item: the verbatim
   hedged sentence, EXPLORATORY (or WATCHING / CONFIRMED / REFUTED), lag,
   n / n_eff / q, "controlled for" chip, a Watch button. Text and labels only.
   Sorted by tier, then q. **This list is short and the design must be
   beautiful when it has one item or none** — "No patterns above the null yet
   for this source."
7. **Forecast.** Where it's heading, band, track record beside it. Only for
   sources that have one.
8. **Entities.** The things inside this source: merchants, places, exercises,
   sites, channels. Ranked; tap → entity page.
9. **Capture / correct.** Log something to this source right here. Correct a
   value — a human override, recorded with provenance, never an edit.

**Per-source character** (the skeleton is shared; the content isn't):
- *Sleep* — hypnogram in History; stages in Why; the midpoint clock in Rhythm.
- *Recovery / HRV* — overnight HRV, autonomic balance; the illness guardian's
  evidence line in Notables.
- *Vitals* — wrist temperature as the quiet substrate; the guardian's home.
- *Workouts* — **the objective function.** e1RM per lift, volume per session,
  per-exercise trends, acute:chronic load. Per-set atoms. Empty today; the
  empty state names the lifting logger and the export.
- *Food / Drink* — meals as captures with intervals and their method;
  ethanol grams and standard drinks; abstinence days as `observed_absent`,
  visibly distinct from unlogged.
- *Attention* — screen sessions, binge runs, late-night share, the content
  diet beneath it.
- *Money* — categories, merchants, recurring, income, balances (retrospective),
  the reconciliation layer. Necessity as used / unused / unknown. Never a
  live counter.
- *Content* — sites and channels, novelty vs repeat, the health-search spikes.
- *Places* — a pointer into MOVEMENTS.
- *Email · Calendar · Code · Weather* — thinner; History + Rhythm + Entities.

**Reads:** `get_domain(source)` — **the single largest gap** — one envelope
carrying all nine modules; `domains.config` for the index.
**Empty source:** the pillar row stays, greyed, with "never captured → [the
one action]."

### 5 · FINDINGS — what the analysis has established

*The brain's output, at the tier it earned.*

- **Opens with** the calibration line, verbatim, always: *"19 significant of
  123 tested vs 87 median (102 p95) on shuffled data — read accordingly."*
  If the file can't say this, it can't show findings.
- **Exploratory.** Text cards. EXPLORATORY badge. The sentence. Driver →
  outcome, lag. n / n_eff / q small. "Controlled for." Watch. Sorted by tier,
  then q. Filter by source pair. No charts, ever, on this screen.
- **Watching.** Hypotheses you've registered: the pre-registration (direction,
  lag, window, adjustment set — frozen), day N of 30, what would confirm,
  what would refute. A verdict is pending until the clock runs out.
- **Confirmed.** With its pre-registration shown beside it, and the data
  boundary: "registered 2026-09-14; confirmed on data after that date only."
- **Refuted.** Kept. Same weight, same layout. A file that hides its misses
  isn't a file.
- **Keystones.** The drivers that show up across the most outcomes — a compact
  ranked list, not a graph.
- **Compare — "X on Y-days."** Pick a metric, pick a condition (lifted /
  drank / rained / high-spend / poor-sleep) → with vs without distributions,
  delta, interval, n. The wrist-temp-on-leg-day surface. *v2 unless ruled
  otherwise* — needs a conditions registry.

**Reads:** `get_patterns`, `register_watch`; `get_compare` (gap, v2).
**Empty:** the calibration line still shows; below it, "Nothing above the
null this run."

### 6 · RELIABILITY — how much to trust the file

*The section that makes every other section believable.*

- **Forecast record.** Claimed coverage vs achieved, side by side. Brier.
  Resolved / pending counts. Per metric.
- **Scan ledger.** Every run: date, pairs tested, observed significant, null
  median, null p95, kept. A table. The honesty of the whole engine in six
  columns.
- **Lifecycle.** Candidates · watching · confirmed · refuted — counts, with the
  refuted list one tap away.
- **Coverage.** Every source: last day seen, days in the last 30, gap. The
  **blindspots** list — "What I cannot currently see" — as a plain amber list.
- **Heartbeats.** Every job: last run, status, trigger (schedule vs manual).
  The keepalives. A red row is a red row.
- **Corrections.** Every human override, with what it replaced.

**Reads:** `get_trust`.
**Empty:** never — this section always has content, because absence of runs
is itself a finding here.

### 7 · THE DESK — where you act

*The only section where you write, not read.*

- **Ask.** Free text. The answer with its atom ids and tier. When it can't:
  the refusal string, and the nearest thing it can compute. Recent questions.
- **Capture.** The quick-log entries mirroring the Shortcuts: food, drink,
  workout set, mood, note. Photo. Voice. Each becomes a capture with a
  server-generated id and shows up in THE RECORD within the hour.
- **Correct.** Find an entry, override it. The original stays; the override is
  a new row with your name on it.
- **Register a hypothesis.** The pre-registration form — driver, outcome,
  direction, lag, window, adjustment set — frozen on submit, then it appears
  under FINDINGS › Watching.
- **Settings.** Sources and their Shortcut recipes; the objective; the
  subject-day boundary; export.

**Reads / writes:** the conversation layer, `ingest_capture`,
`register_watch`, the correction path (OQ-32).

---

## Part III — Backend gaps, consolidated (Claude Code, free, before Lovable)

| RPC / artefact | Section | Status |
|---|---|---|
| `get_domain(source)` — all nine modules in one envelope | SOURCES | **gap — largest** |
| `domains.config` — pillars → sources → metrics → density → replaces | SOURCES index | gap |
| `get_movements(day)` · `get_place(id)` | MOVEMENTS | gap (REQ-LOC written) |
| `search_record(q)` | THE RECORD | gap |
| `get_entity(id)` | SOURCES › 8 | gap |
| `get_compare(metric, condition)` | FINDINGS › Compare | gap, v2 |
| `get_period(week)` | ASSESSMENT › weekly | gap, v2 |
| `get_today` · `get_timeline` · `get_day` · `get_patterns` · `get_trust` · `get_insights_guarded` · `register_watch` · `ingest_capture` · conversation layer | — | **live** |

Build order: `domains.config` → `get_domain` → `get_movements` → `search_record`
→ `get_entity`. Everything else is v2.

---

## Part IV — The rounds, cut from the sections

| Round | Section(s) | Precondition |
|---|---|---|
| **R0** | Kill and rewire. Remove every old read. Seven-section shell, rail + bottom bar. Auth. Empty states everywhere. Part I language as the component library. | none |
| **R1** | SOURCES — the nine-module page against `get_domain`, for Sleep, Money, Attention | `get_domain` live |
| **R2** | SOURCES — the index; every source from `domains.config` | config live |
| **R3** | FINDINGS + RELIABILITY | live RPCs |
| **R4** | ASSESSMENT + THE RECORD | search RPC |
| **R5** | MOVEMENTS | `get_movements` live |
| **R6** | THE DESK | conversation layer |
| **R7** | Polish — density, dark, motion, numerals | — |

Seven rounds. R0 first, always. R1 before R2 so the skeleton is proven on
three rich sources before it's multiplied by twenty.

---

## Part V — What Joe still decides

1. **Phone bottom bar:** Assessment · Record · Sources · Findings · Desk, with
   Movements and Reliability under "more" — or a different five?
2. **Compare and the weekly report:** v2 (my recommendation) or v1?
3. **The first three sources for R1:** Sleep, Money, Attention?
4. **Dark by default:** confirmed?
5. **The name.** "My Life Compass" is the old app. This is a file. Does it
   have a name?
