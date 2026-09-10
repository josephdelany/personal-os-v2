# ADR-0089 — The analysis layer reads core.atoms: two lanes, two clocks, one owner per measure

Status: accepted (migration 0056 prepared, NOT applied — needs authorization)
Date: 2026-09-09
Requirements: REQ-INF-108, REQ-ASK-021, RULE-06, RULE-08, RULE-10, RULE-12, RULE-13.
Implements Joe's rulings of 2026-09-09 on device precedence and sleep duration.

## Two lanes, never blended

`analysis.panel` holds 111,891 legacy rows across 350 metrics whose definitions are unverified
(OQ-51). Seven metric names exist in both lanes. The overlap was **measured before the design
was written**:

| metric | legacy avg | atoms avg | verdict |
|---|---|---|---|
| `steps` | 2,239 | 3,047 | different populations |
| `sleep_deep_min` | 1.3 | 78.2 | legacy is in **hours** despite the `_min` suffix |
| `sleep_rem_min` | 1.6 | 102.0 | legacy is in **hours** despite the `_min` suffix |
| `sleep_asleep_min` | 411.2 | 122.4 | legacy means **total** sleep; the atom means the **unstaged** part |
| `checkin_morning_energy` | 5.0 | 5.0 | identical |

Two of those are wrong by a factor of sixty, silently, under a name that asserts the unit. So
a metric has one owning lane: where atoms own it, the legacy rows are excluded — not blended,
and not used to backfill days the atoms miss. A series whose definition changes mid-window is
worse than a short series. Coverage before the atom lane begins is absent and disclosed
(`analysis.v_atom_lane_coverage`), never imputed (RULE-06).

## Two clocks, two parameters

`p_as_of` is the subject-day cutoff — which days count. `p_known_at` is the knowledge-time
cutoff — what the system had learned when the question was asked.

This migration originally passed `as_of` to both. Because Ask defaults `as_of` to **yesterday**
(today is incomplete), all 33,355 atoms imported **today** were invisible to every question.
The answer was bitemporally correct and completely useless, which is how you know the two
cutoffs are different questions. `f_daily_panel(date)` now means "days up to as_of, using
everything known now"; `f_daily_panel(date, timestamptz)` is true replay. This is the half of
OQ-45 the atom lane can close — `core.atoms` has a real `recorded_at`, which `analysis.panel`
does not.

Superseded atoms are excluded as of the knowledge time, so a human correction wins today while
a replay of an earlier question still returns what was current then (RULE-10, INV-2).

## The specification is data, not a branch

`config.panel_aggregation` holds the per-metric daily method and device precedence;
`config.panel_composition` holds sleep's definition. Both are seeded from
`core.metric_registry.state_class` so the method cannot disagree with the metric's own
declaration. Joe can change a measurement definition without a code change, and an answer can
cite the method and version that produced it (RULE-13).

- **Totals sum; readings take the median.** The median is what `describe` already renders, so
  the panel and the sentence cannot mean different things, and it is robust to the outliers a
  wrist sensor produces.
- **Devices: Watch preferred, never summed.** Measured, not assumed — on days both reported,
  the Watch alone was 1.01× a one-device day, the iPhone alone 0.97×, their sum 1.98×. The
  precedence is applied per *day*, so the phone-only days after 2026-08-21 survive.
- **Sleep is `interval_union_minutes`**, not a sum: overlapping segments are counted once. The
  stored data happens not to overlap (0 overlapping pairs, checked), but "happens not to" is
  not a guarantee and a duplicated segment from a future import must not inflate a night.

## The guard against picking the wrong metric is at naming, not storage

"how is my sleep" resolved to `sleep_asleep_min` at similarity **1.0** and would have answered
from the 3-day unstaged fragment instead of sleep duration — "sleep" is a substring of "Asleep
(unspecified)". Two wrong fixes were tried before the right one:

1. Withholding components from the panel. It stopped the double-count nobody performs and cost
   a real capability: "how much deep sleep did I get" resolved correctly and had nothing to
   answer from.
2. Demoting any component whose whole also matched. That sent "deep sleep" to Sleep duration.

The rule that works: a component is demoted only when the phrase carries **no word that
distinguishes it from the whole**. "deep" is in "Deep sleep" and not in "Sleep duration", so
the asker means the part. Bare "sleep" is inside both names, so it means the whole. Components
remain served and answerable in their own right (RULE-12 applied to naming).

## Not decided here

The legacy lane is still subject-day-only; OQ-45 closes fully when the legacy panel gains a
`recorded_at` or is retired. `sleep_inbed_min` remains a separate concept and is never used as
sleep duration.
