# Personal OS: A Self-Science Platform That Cannot Lie to Its User
### Joseph Delany · September 2026

---

## Abstract

Personal OS is a single-user "quantified-everything" system: it captures the
streams a life emits — sleep, heart, movement, attention, media, money, food,
mood, weather, work — holds them immutably, computes over them deterministically,
and talks back. Where commercial trackers (Whoop, Oura) cover one domain, this
system holds **34 input streams across 12 life domains, 350 daily metric series,
and seven years of history (2019–2026)**, live in production at $0 recurring
cost. Its central contribution is not breadth but **structural honesty**: a
six-tier evidence ladder enforced in the database schema, exploratory findings
that must wear their uncertainty, pre-registration as a database constraint
(confirmation can only use data collected *after* a hypothesis is registered —
enforced by triggers, not discipline), forecasts that score themselves publicly,
and a self-auditing "Trust" surface. The design is a direct response to a
measured failure: the author's previous system produced 1,413 "validated
insights" whose strongest results were tautologies — the same quantity
correlated with itself under two names. This system publishes its own
false-positive rate on every scan.

---

## 1 · The problem: personal analytics that lie

Consumer self-tracking produces numbers; it rarely produces *knowledge*, and
when it manufactures knowledge it routinely manufactures falsehood. The
predecessor system built for this project (2 years of data collection, 126
analysis scripts) illustrated every failure mode at once: its top "validated"
findings (r ≈ 0.81, FDR-controlled, out-of-sample "held") included *deep sleep
percentage predicts deep sleep minutes* and *browsing session count predicts
active screen hours* — statistically bulletproof restatements of identity. Of
1,413 validated insights, **zero** touched the user's stated objective
(strength and body composition). The statistics were fine; the epistemology was
broken. The rebuild's thesis: **honesty must be structural — enforced by
schemas, triggers, grants, and published calibration — because good intentions
demonstrably were not enough.**

## 2 · Architecture

**Capture (immutable).** An append-only spine: `raw_captures` (every capture,
UPDATE/DELETE revoked at the grant level AND rejected by triggers) → deterministic
extraction → `atoms` (bitemporal facts: when it happened vs when the system
learned it; three-valued presence — *observed / observed-absent / unknown* — so
"logged no drink" never collapses into "didn't log"). Ingress is a write-only
RPC: the phone's credential can append a capture and can read nothing.

**Inputs.** iOS Shortcuts (check-ins, food, workout sets — built
programmatically and signed via Apple's toolchain), Mac collectors (browsing,
YouTube, screen time), nightly physiology processing, Gmail-receipt
transactions, calendar, weather, plus a loaded seven-year legacy daily series.
19 streams live; the rest staged with parsers.

**The panel.** One row per (day, metric): 111,626 rows, 350 metrics, 2,801+
distinct days. Genuine NULLs — absence is never filled (the no-imputation rule
is constitutional).

**Engines (all deterministic, all heartbeated, all $0 on free-tier compute):**
- *Timeline*: any day since 2019 reconstructed minute-by-minute (a probe
  reconstructed 2025-03-04: 41 timestamped moments).
- *Baselines/State*: per-metric robust baselines (median/MAD, EWMA-detrended,
  dual 7/28-day scales), personal p10–p90 bands, out-of-band streak lengths
  with personal records, and a 2-of-N autonomic concurrence check reported with
  its own historical base rate (a pattern match, never a diagnosis).
- *Contrast scan*: for every cross-domain (driver, outcome, lag) pair —
  deseasonalized (calendar-month demedian), detrended (EWMA), weekday-demedianed
  both sides; within-person quartile contrast; tie-corrected Mann-Whitney;
  **hierarchical (tree) FDR** — Simes-selected domain-pair families, BH within
  selected families, family id + size persisted per result; a minimum-effect
  floor; bidirectional lag-0 associations collapsed to one pattern; and
  **construct-family guards that make the predecessor's tautology class
  structurally untestable**. The null check runs **five replicate shuffled
  twins** and publishes the null discovery count's median and 95th percentile
  beside every observed count.
- *Forecasts*: next-day bands via adaptive conformal inference; every forecast
  writes a prediction row that later resolves and scores (Brier + coverage).
- *Brief compositor*: a deterministic 7-slot morning page (state, connection,
  week-vs-you, watching, forecast) that renders with no language model at all.

**The ladder.** DESCRIPTIVE → CANDIDATE → PROMOTED → CONFIRMED → EXPERIMENTAL,
plus INSUFFICIENT as a first-class, *returnable* answer. Vocabulary is
tier-gated: an exploratory association may say "may" and must say "unverified";
"causes" is unutterable below the experimental tier. The scan's output enters
as CANDIDATE only, renders only on a text-only EXPLORATORY surface (no charts —
a plot invites over-belief a sentence does not), and that surface was proven
before the scan was allowed to ship (an acceptance probe asserts: only
CANDIDATE rows render, every row carries the label, zero confirmed-tier verbs
in any payload, and no other surface can reach them).

**The loop — how a pattern earns the strong sentence.** The user taps *Watch
this* on a pattern. A NEW registration row is inserted with
`preregistered_at = now()`; a database CHECK forbids confirmation data older
than registration, and a trigger freezes every registration column against
UPDATE (verified: the probe's tampering attempt bounces). The hypothesis then
waits for ≥30 *future* days and is confirmed or refuted on data that did not
exist when it was registered. Confirmed findings emit forward predictions;
sufficient prediction failures demote automatically, with no override
interface. The system cannot be argued with — only out-predicted.

## 3 · Evaluation (real runs on real data)

**Scan calibration (published on-surface every run).** Stride-sampled proof
run under the final (v2) methodology: **31 significant observed vs a
shuffled-null median of 12 (p95 below observed) across 909 tested pair-lags,
five null replicates** — the null distribution is displayed beside every result
set, making residual false-discovery risk a number the user reads, not a
footnote. (Development iterations tell the honest story: the naive first run's
"discoveries" were tautologies and shared seasonality — the shuffled null BEAT
the observed set 54 : 35 — and the pipeline refused to ship itself until
construct-family guards and deseasonalization collapsed the null. An
adversarial review then forced three further upgrades before submission: flat
BH → hierarchical tree-FDR, an effective-sample-size formula that could
inflate, and a single-draw null → a replicate null distribution.)

**Sample discovered patterns (exploratory, q-values shown in-app):** heavy
information-consumption days run ~1,300 fewer steps the same day (q≈0.0000,
n≈670, both directions surfaced and labeled as one bidirectional association);
entertainment-video days precede +1.55 purchases two days later (q=0.002);
hotter days precede ~$67 higher spend two days later (q=0.009).

**Forecast scorecard.** Backtest on a fully-covered day: 4/4 metrics inside
their conformal bands (mean Brier 0.01); claimed 90% coverage vs achieved
coverage is a permanent public statistic on the Trust tab, recomputed nightly.

**Structural proofs (every unit, before every deploy).** Each engine shipped
only after a rolled-back proof on live data — including hand-checked values
against the source CSV, an attempted UPDATE on a frozen registration (rejected),
a no-JWT read attempt (rejected: reads are owner-locked to one identity), and a
time-traveling prediction (rejected by the schema's own CHECK).

## 4 · What the finished surface does

Six tabs on a deployed, authenticated web app
(https://josephdelany.github.io/personal-os-v2/): **Today** (the 7-slot brief) ·
**Timeline** (any day since 2019, to the minute) · **Patterns** (the EXPLORATORY
surface with Watch buttons and per-run honesty line) · **Trust** (the system
grading itself) · **Insights** (a 1,338-fact descriptive battery over 223
streams) · **Day** (raw capture view). Capture rides four phone shortcuts and
five unattended collector lanes; everything continues without any AI service —
the language model was needed to *build* the system, not to run it.

## 5 · Limitations, stated the way the system states them

Exploratory patterns are screened associations, not findings — the ladder's
upper rungs (confirmed/experimental) are reachable only through the
registration clock and, later, randomized micro-trials whose machinery is
specified (632 requirements, 39 architecture decision records) but not yet
built. The Mann-Whitney p-values do not model serial correlation beyond
detrending; effective-n is computed and displayed as the honest sample size.
Several device-side streams died for five weeks (a macOS permissions change) —
the gap is visible in the data and on the Trust tab, because a gap rendered as
a gap is the design. Subjective streams (mood, food) are only as dense as the
user's taps; the system never fills what he does not log.

## 6 · Why this matters

Every consumer health product answers "what should the user be told?" This
project answers a harder question: **"what is the system entitled to say?"** —
and encodes the answer in schemas, triggers, tier vocabularies, published null
rates, and self-scoring forecasts, so that the entitlement is checked by the
machine rather than promised by the developer. The result is a personal
analytics platform whose every sentence carries its evidence, whose mistakes
demote themselves, and whose owner can audit any number down to the immutable
capture it came from — a Whoop for everything, built on the premise that the
first thing a self-knowledge system owes its user is the truth about how little
it knows.

---

### Appendix A — demo script (5 minutes)
1. **Today**: read the brief — state, a rotating exploratory connection, the
   week's money vs baseline, watch-clocks, tomorrow's bands + track record.
2. **Timeline**: pick 2025-03-04 — watch a random Tuesday reconstruct.
3. **Patterns**: read the honesty line (93 vs 50 shuffled of 9,072); tap
   **Watch this** on a pattern; show the frozen registration row and the
   day-0/30 clock.
4. **Trust**: the scorecard, the calibration ledger, the blindspots list.
5. Close with the constitution: the append-only proof (an UPDATE bouncing off
   `atoms`), and the predecessor's 1,413 tautologies as the control group.

### Appendix B — artifact inventory
632 requirements across 7 specs · 39 ADRs · 32 forward-only migrations (every
one dry-run against a disposable schema before live apply) · 12 engines/tools ·
5 rolled-back proof harnesses · 38-check CI gate on every push · 4 scheduled
unattended jobs · 1 deployed surface · 0 dollars.
