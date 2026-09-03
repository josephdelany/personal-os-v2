# THE SURFACE — the definitive front-end plan

*2026-09-02, written after reading every requirement in `specs/` that constrains
what may appear on a screen. Supersedes `THE_ROUTE.md` and `THE_CRITIQUE.md`,
both of which were written without that reading and are wrong in consequence.*

---

## 0. What the research changed

There are **96 written requirements that bind the surface** — REQ-NAR (29),
REQ-TIER (43 of which ~20 are render rules), REQ-FIN §E (19), REQ-NUT §E (7),
REQ-CAP §F (13), plus twelve constitution rules with tier LINT or TEST. I had
designed against the *data* and not against these. The consequences are large
enough that the prototype currently on the artifact is **non-compliant in eight
specific ways**, and three whole surfaces required by the specs do not exist in
any plan I have written.

This document is the corrected version. Every design rule below cites the
requirement that produces it, so the front end can be audited the way the
backend is.

---

## 1. Eight ways the current prototype is non-compliant

| # | Violation | Rule | Fix |
|---|---|---|---|
| 1 | **The front end computes displayed numbers** — 14-night sleep debt, deep/REM minutes from percentages, nights-below-band count, "8 of 14 sources", theme counts, efficiency × 100 | **RULE-14**, **REQ-NAR-033** (LINT + TEST: *"no arithmetic beyond formatting in client code"*) | every one moves into the envelope as a stored computation; the client formats only |
| 2 | `n` rendered without `n_eff` on stream pages and ledgers | **REQ-INF-023** (*"SHALL NOT render `n` alone"*) | every sample size renders as `n / n_eff` |
| 3 | The two-bar comparison under an exploratory claim | **REQ-NAR-035** (*"SHALL NOT render a chart for a claim whose tier is CANDIDATE"*) — ruling R1 amended ADR-0032 and REQ-TIER-050 but **not this** | amend REQ-NAR-035 in the same ADR, or the comparison is illegal |
| 4 | Plan showed HAC **confidence** intervals on confirmed findings | **REQ-TIER-025** (*"SHALL NOT render a frequentist confidence interval on any user-facing surface"*) | display the Bayesian credible interval + probability of direction (B19); HAC stays internal to the gate |
| 5 | Nutrition figures planned as point values | **REQ-NUT-044** (exact format `~<point> kcal (<low>–<high>)`), **REQ-NUT-045** (visual weight set by `estimate_method`, never by magnitude) | interval-first rendering, and a typographic scale keyed to resolution method |
| 6 | Money ledgers show a single period | **REQ-FIN-217** (*"every retrospective amount … paired with the same figure for the preceding period"*) | every money row carries prior-period beside it |
| 7 | No feedback control on any insight | **REQ-FIN-221** (*"Every insight surfaced SHALL carry a 'not useful' control, and activating it SHALL suppress that entire insight class permanently"*) | a dismiss affordance on every insight, and a suppression store |
| 8 | ATM rows, split tabs and stale accounts rendered unlabelled | **REQ-FIN-224**, **REQ-FIN-225** (*'destination unknown'*, *'net of $N reimbursed'*, coverage warning at 35 days on **every aggregate view**) | limitation labels inline, not in a footnote |

---

## 2. Three required surfaces that appear in no plan I have written

1. **The specification curve.** REQ-INF-037: *"SHALL present the specification
   curve as the default output format for any promoted-or-higher finding."* Not
   an optional extra — the **default** rendering of a promoted claim is the
   distribution of effect across all 108 specifications, with the shifted-null
   fraction beside it (REQ-INF-034). This is the single most important analysis
   component in the product and I had it as a line of small print.

2. **The changes log.** REQ-FIN-223: the periodic review *"SHALL include a
   running record of changes Joe has already made and their recorded effect."*
   A first-class object — what you changed, when, and what happened after —
   which is also the only honest way to answer "is this thing working."

3. **The refusal ledger.** REQ-NAR-013 and REQ-FIN-219 write `render_violations`
   and `copy_violation` rows every time the system refuses to render something
   untraceable or moralising. Those rows are currently invisible. Surfacing them
   in Trust — *"the file refused to render 3 strings this week"* — is the
   strongest trust signal the product can possibly emit, and it costs one table
   read.

---

## 3. The abstract model

Under the 26 screens there are only **eleven object types**, and the whole
interface is a browser over them and their relations.

| Object | Count today | Canonical card | Canonical page | Relation to Day |
|---|---|---|---|---|
| **Day** | 2,382 | date + coverage dots | the Record | *is* the join |
| **Stream** | 223 | label · distribution · n/n_eff · coverage | stream page | one value per day |
| **Domain** | 14 | name · hero · coverage · replaces | domain page (idiom) | a curated set of streams |
| **Entity** | thousands | name · count · last seen | entity page | appears on days |
| **Capture** | growing | source · time · trust | provenance sheet | belongs to a day |
| **Atom** | ~100k | value · method · interval | provenance sheet | belongs to a day |
| **Claim** | 22 | tier · headline · evidence | pattern page | spans a window of days |
| **Prediction** | 4 | claim · resolves · score | inside its claim | resolves on a day |
| **Recommendation** | 0 | tier · instruction · effect · would-change | inside Today | issued on a day |
| **Question** | 0 | text · tier · numerals | Ask | scoped to days |
| **Correction** | 0 | before · after · when | changes log | recorded on a day |

Two design consequences fall straight out:

- **Every object type needs exactly one card component and one page**, and every
  card must be able to appear inside any other object's page. A claim card
  appears on Patterns, on a stream page, on a domain page and inside Ask. Build
  eleven cards, not forty layouts.
- **Every object relates to Day.** So the Day view is not "a screen" — it is the
  universal cross-section, and it must be reachable from every card in one tap.

**The verbs are ten:** look · log · correct · name · watch · compare · ask ·
pin · dismiss · export. Anything the interface offers that is not one of these
is scope creep.

---

## 4. The claim state machine — the spine of the analysis surface

Every analysis screen is a view onto one machine. Drawing it once, correctly,
replaces four screens.

```
                    scan (weekly, shuffled-null calibrated)
                              │
                        ┌─ CANDIDATE ─┐            22 today
        (you press Watch)│             │(never auto-advances)
                         ▼
                  WATCHING / INSUFFICIENT          0 today
                         │  look 1 · first night with ≥30 paired days
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      PROMOTED      still watching   REFUTED         0 · 0 · 0
          │  look 2 at day 120 + confirmation gate
          │  (spec curve, tree-FDR, DAG adjustment,
          │   HAC errors, E-value, 2 negative controls, DoWhy)
          ▼
  CONFIRMED_OBSERVATIONAL ──monthly re-check fails──▶ back to PROMOTED
          │
          └── only a randomised trial reaches EXPERIMENTAL
```

**Render rules attached to this machine, all already written:**

- CANDIDATE appears **only** on the exploratory surface; every other finding
  surface returns the refusal string (**REQ-TIER-035**, **REQ-INF-402/403**).
- No chart on a CANDIDATE claim (**REQ-NAR-035**).
- PROMOTED and above renders the **specification curve by default**
  (**REQ-INF-037**) with the shifted-null fraction (**REQ-INF-034**).
- PROMOTED or above **without a prediction row does not render at all**
  (**REQ-INF-302**).
- CONFIRMED renders its adjustment set, E-value at the point estimate, and
  negative-control results in the same payload (**REQ-TIER-023**), as a
  **credible** interval with probability of direction — never a confidence
  interval (**REQ-TIER-025**, **REQ-INF-526**).
- CONFIRMED whose adjustment-set coverage drops below 0.60 renders as
  INSUFFICIENT (**REQ-TIER-045**).
- Any demotion is surfaced in the next brief, naming the previous claim and the
  reason (**REQ-TIER-043**, **REQ-INF-324**).
- INSUFFICIENT is displayable and must carry either a named data requirement or
  a proposed trial, or the render is rejected (**RULE-18**, **REQ-TIER-030/034**).
- Every claim payload carries `finding_id, tier, n, n_eff, coverage,
  code_version` (**REQ-TIER-005**), and `n` never appears without `n_eff`
  (**REQ-INF-023**).

---

## 5. The design system, derived from the requirements

Not taste. Each rule below is the visual consequence of a written requirement.

### 5.1 Numbers
- Every displayed number is a stored computation; the client formats only. **RULE-14**
- Every numeral carries its unit. **REQ-NAR-014**
- Rounding only through the metric's registered rounding rule. **REQ-NAR-015**
- Interval bounds never round inward. **REQ-NUT-049**
- Sample sizes always as `n / n_eff`. **REQ-INF-023**
- Numbers never animate — an animated number is a sequence of false values.
- Tabular figures everywhere; a stale value renders as missing, never carried
  forward. **REQ-INF-109**

### 5.2 Intervals are a typographic primitive
- Estimates render as intervals, not points. **RULE-08**
- Energy and macros in the exact form `~412 kcal (380–450)`. **REQ-NUT-044**
- **Visual weight is set by `estimate_method`, never by magnitude**
  (**REQ-NUT-045**): `weighed` renders at full weight, `labelled` slightly
  lighter, `portion_table` lighter still, `photo_estimate` lightest. You can see
  how well a number is known before you read it.
- If an interval is wider than the difference being discussed, say so in plain
  words. **REQ-NUT-047**

### 5.3 Charts
- A chart never appears above its verdict text. **REQ-NAR-034**
- No chart on a CANDIDATE claim. **REQ-NAR-035**
- No pie, donut, or part-to-whole visual of spending. **REQ-FIN-215**
- Concentration of spend is a ranked list with absolute amounts and counts,
  never a share of total. **REQ-FIN-216**
- Specification curve is the default rendering of a promoted claim. **REQ-INF-037**
- No unpruned cross-lens map; edges ranked by |effect| × confidence. **REQ-INF-563**
- Sparse windows draw points with visible gaps, never a line through absence.
  **RULE-06**

### 5.4 Language
- Six tiers, closed vocabulary per tier, linted. **RULE-16**, **REQ-NAR-020/021/022**
- Banned wordlist enforced on every string: excessive, wasteful, necessary,
  unnecessary, too much, splurge, guilty, overspent, bad, should have.
  **REQ-NAR-023**, **REQ-FIN-218**
- No streak, compliance score, composite wellness score, celebratory animation,
  or live counter. **RULE-24**, **REQ-NAR-025**, **REQ-CAP-095**
- Never `granger`; the statistic is `predictive_lead` in every string.
  **REQ-TIER-022**
- Every surface renders fully with the language layer off. **RULE-15**, **REQ-NAR-030/031**
- Alcohol surfaces speak in occasions and context, never volume and cost.
  **REQ-FIN-227**
- A coping behaviour is never characterised as a malfunction. **REQ-FIN-228**

### 5.5 Coverage and honesty
- Rolling 7-day capture coverage as a percentage; never a streak. **REQ-CAP-094**
- Adherence bar is 2 eating occasions per day, not 100 % of meals. **REQ-CAP-096**
- Two logged meals reports 50 %, never an imputed third. **REQ-CAP-099**
- Any account without a successful import for 35 days puts a coverage warning on
  **every aggregate view**, and no total is presented as complete. **REQ-FIN-225**
- Every figure affected by cash, splitting or missing coverage is labelled with
  the specific limitation **in the same view**. **REQ-FIN-224**
- Persistent indicator of unsynced captures; deferred captures shown with their
  reason. **REQ-CAP-024**, **REQ-CAP-044**
- An unresolved food item is not a failure state. **REQ-NUT-027**

### 5.6 Cadence — the surface must not nag
- One prompt per subject per day maximum; scheduled, never random; a dismissed
  prompt never repeats. **RULE-27**, **REQ-CAP-087**
- No battery exceeds 26 items. **RULE-27**
- Finance: at most one scheduled review per 7 days, at most 4 notifications per
  month, and **no figure that updates more than once per 24 hours**.
  **REQ-FIN-211/213/226**
- Every insight carries a *not useful* control that permanently suppresses its
  class. **REQ-FIN-221**

### 5.7 The finance surface is deliberately not a daily surface
The spec's own non-goal: *"A daily dashboard. The surface Joe opens should be
worth opening, which means it should not be there most days."* The evidence is
two field studies where precise frequent feedback increased spending by $32–40.

**Consequence for the design:** money does not appear on the daily Glance. It
appears in the weekly review and on its own page when you go there. This is the
one place where the product deliberately withholds something you could show.

---

## 6. The corrected surface map — three modes, 26 screens

Modes are the usage architecture; screens hang off them.

### Mode 1 · GLANCE — phone, 15–40 s, time-of-day aware
| Screen | Contents | Requirements it satisfies |
|---|---|---|
| **1. Today** | the sentence, large · the instruction if one exists · your pinboard · notices (demotions, refutations, guardian) · collection gap when coverage is low · 7-day capture coverage % | REQ-TIER-043, REQ-INF-324, REQ-CAP-094, RULE-27 |
| **2. Notices** | dated demotions, refutations, design alerts, blindspots | REQ-TIER-043, REQ-CAP-097 |

**No money on this screen** (§5.7). Before 11:00 it shows last night; midday the
day so far; after 20:00 the check-in prompt and what is unlogged.

### Mode 2 · CAPTURE — phone, under 5 s, one thumb
| Screen | Contents | Requirements |
|---|---|---|
| **3. Capture home** | generated from the gap: stale sources with dropzones · what is waiting on a habit · unsynced and deferred indicators | REQ-FIN-225, REQ-CAP-024, REQ-CAP-044 |
| **4. Quick log** | night · morning · food · drink · workout set · weight; ≤26 items per battery; nothing defaulted | RULE-27, RULE-06 |
| **5. Log another day** | date picker; bitemporal — records when it happened and when you said so | RULE-03 |
| **6. Unresolved** | unnamed foods, unnamed places, unlinked charges; resolving teaches permanently | RULE-10, REQ-NUT-027 |
| **7. Corrections** | what is wrong / what is right → a superseding row | RULE-10, RULE-02 |

### Mode 3 · SESSION — desktop, unlimited
| # | Screen | Idiom |
|---|---|---|
| 8 | **Domain index** | five pillars, 14 rows |
| 9–20 | **Domain pages ×12** | native idiom each (sleep, recovery, vitals, body, workouts, activity, food, drink, attention, content, mood, money) |
| 21 | **Stream index** | 223 rows, filter, coverage-first sort |
| 22 | **Stream page** | universal: shape · n/n_eff · history · rhythm · in-conversation |
| 23 | **Entity page** | merchant · category · site · channel · exercise · place · food |
| 24 | **The Record — day** | timeline · logged · coverage ribbon · links · every domain's value that day |
| 25 | **The Record — search + calendar** | month histogram, year heatmap of 2,382 days |
| 26 | **Patterns** | the state machine: journey · themes · claim cards · spec curves · watching clocks · confirmed evidence · chains · trials |
| 27 | **Compare** | metric × condition → two-group split, DESCRIPTIVE |
| 28 | **Recommendations** | instruction · tier · effect · would-change · prediction · demoted |
| 29 | **Ask** | question → traced answer, every numeral a computation id |
| 30 | **Weekly review** | the one scheduled surface: money, changes log, coverage, findings changed |
| 31 | **Changes log** | what you changed, when, what happened after |
| 32 | **Trust** | coverage · calibration · heartbeats · **refusal ledger** · requirement ledger |
| 33 | **Places** | day track · register · place page (no map, ever) |

Thirty-three routes, but only **three things to learn**: a card, a page, and the
Day. Settings is a sheet. Provenance is a sheet. Compare is a sheet from any
metric.

---

## 7. Component library — 41 components, each with its rule

| Family | Components | Governing requirements |
|---|---|---|
| **Shell** (6) | Sidebar · TabBar · CollapsingHeader · CommandPalette · SheetHost · Toast | — |
| **Object cards** (11) | DayCard · StreamCard · DomainCard · EntityCard · CaptureCard · AtomRow · ClaimCard · PredictionCard · RecommendationCard · QuestionCard · CorrectionRow | one per object type (§3) |
| **Primitives** (9) | Sentence · TierBadge · CoverageBadge · TraceNumber · IntervalValue · SampleSize (`n/n_eff`) · LimitationLabel · DismissControl · RefusalCard | REQ-NAR-014, REQ-INF-023, REQ-FIN-221/224, RULE-18 |
| **Charts** (11) | TrendBand · Sparkline (sparse/dense) · NightsHistogram · CompositionBar · IntervalBars · DayTrack24 · SessionStrip · MonthHistogram · YearHeatmap · LedgerRow · WeekBars | REQ-NAR-034/035, REQ-FIN-215/216, RULE-06 |
| **Analysis** (4) | **SpecificationCurve** · JourneyBand · ContextStack · ComparisonPair | REQ-INF-034/037, REQ-TIER-025 |

**SpecificationCurve** is the component to get right: 108 specifications ordered
by effect, the registered specification marked, the shifted-null share drawn
beneath, `n/n_eff` and `q` beside it. It is the default face of every promoted
claim and nothing else in the product communicates robustness as directly.

---

## 8. New backend gaps this research exposes

Beyond the six in `THE_ROUTE.md`, reading the requirements adds **nine**. All
additive; fold into B8/B9/B10.

| Gap | Required by | Shape |
|---|---|---|
| Server-side computation of every number the client currently derives | RULE-14 | `get_domain` gains `debt`, `nights_below_band`, stage minutes, coverage counts as stored values |
| `n_eff` on every envelope that carries `n` | REQ-INF-023 | additive field everywhere |
| Specification-curve payload | REQ-INF-037 | `spec_curve:{n_specs, share_sig, null_share, points:[{spec_id, effect, p, same_sign}]}` |
| Bayesian effect fields on confirmed claims | REQ-TIER-025, REQ-INF-526 | `credible:[lo,hi]`, `p_direction`, `p_practical`, `rope` |
| Prior-period figure on every money aggregate | REQ-FIN-217 | `prior:{amount, n, period}` |
| Limitation labels | REQ-FIN-224 | `limitations:[{kind:'destination_unknown'|'net_of_reimbursed'|'coverage', text}]` |
| Insight suppression store + control | REQ-FIN-221 | `suppress_insight_class(p_class)`, and every insight carries `class` |
| Changes log | REQ-FIN-223 | `get_changes()` — what changed, when, recorded effect |
| Refusal ledger read | REQ-NAR-013, REQ-FIN-219 | `get_trust.refusals:{render_violations_7d, copy_violations_7d, recent:[…]}` |

---

## 9. Build order — 12 rounds, acceptance by requirement ID

| R | Contents | Acceptance |
|---|---|---|
| **1** | Shell, routing, all 33 routes, primitives, performance contract (envelope cache keyed on `as_of`, virtualised lists, min/max downsampling) | no `from(`; **zero arithmetic operators in the render layer** (RULE-14 lint); every route renders an honest state |
| **2** | Object cards ×11 + chart library with sparse/dense modes | REQ-NAR-034 (chart below verdict) passes on every card; sparse mode proven on 23-point series |
| **3** | **Capture, complete** — gap cards, dropzones, six forms, retro-log, unresolved, corrections, unsynced/deferred indicators | REQ-CAP-024/044/094/096/099, RULE-27 (≤26 items, one prompt/day) |
| **4** | **Glance** — Today, pinboard, time-of-day, notices; no money present | REQ-TIER-043, §5.7 |
| **5** | Domain index + universal domain page + stream index + stream page | REQ-INF-023 everywhere; REQ-INF-109 (stale = missing) |
| **6** | ContextStack + global time cursor + global scope + Compare sheet | descriptive only; cursor shared across every chart on screen |
| **7** | The Record: day, search, year heatmap, provenance sheet | every number opens its chain (RULE-14, INV-3) |
| **8** | **Patterns** — journey, themes, claim cards, **specification curve**, watching, confirmed, chains, trials | REQ-INF-037 default rendering; REQ-INF-302 (no prediction → no render); REQ-TIER-025 (no confidence intervals); REQ-NAR-035 |
| **9** | **Sleep · Attention · Content** in native idiom | RULE-24 (no streaks anywhere) |
| **10** | **Money + weekly review + changes log** | REQ-FIN-210/211/212/215/216/217/221/224/225 all provable |
| **11** | **Food · Drink · Body · Workouts · Places** | REQ-NUT-044/045/047/048/049; REQ-LOC-002 (grep: no map, no coordinate) |
| **12** | Recommendations · Ask · Trust incl. refusal ledger · polish · full copy audit | REQ-NAR-023 banned wordlist returns zero; REQ-TIER-049 (no recommendation without tier + interval) |

Rounds 1–7 need only what is live today plus B8. Rounds 8–12 each wait on their
backend.

---

## 10. What I need from you

1. **REQ-NAR-035 amendment.** Ruling R1 amended ADR-0032 and REQ-TIER-050 to
   permit the descriptive two-bar under an exploratory claim, but REQ-NAR-035
   independently forbids *any* chart on a CANDIDATE claim. Either it is amended
   in the same ADR with the same five constraints, or the comparison comes out.
   **I recommend amending it**, with the constraint made explicit that the mark
   renders the *group medians* (descriptive) and never the *claim*.
2. **Money off the Glance.** The finance spec's own non-goal forbids a daily
   money surface, on measured evidence. Confirm you want that honoured — it
   means no spend figure on Today, ever.
3. **The pinboard.** Confirm it exists: any metric, claim, place or entity
   pinned to Today, drag-ordered. It is the single-user advantage and nothing
   else replaces it.
4. **The name.**
