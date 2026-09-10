# ADR-0095 — A domain says why it has nothing, not just that it has nothing

Status: accepted (migration 0060 prepared, NOT applied; depends on 0056)
Date: 2026-09-09
Requirements: REQ-ASK-021, REQ-TIER-018, RULE-06, RULE-07, RULE-12, RULE-18.

## Why this came before the weekly report

Every per-domain surface iterates `config.domains.hero_metric`. Checked against the registry
and both lanes, **eight of the fourteen name a measure `core.metric_registry` does not
contain**, and four of those have rows anyway.

A weekly report built today would print "no data" for recovery and vitals while **1,333
observations sit in `core.atoms`** as `hrv_sdnn_ms` and `resting_hr`, because the domains ask
for `hrv_sdnn` and `rhr`. That is not a display bug; it is a false statement about Joe's life,
produced by a surface that could not tell two different absences apart.

## The distinction

`analysis.f_domain_status` returns one of five states rather than a value and a blank:

| state | meaning | against real data |
|---|---|---|
| `resolved` | registered, has observations | 2 (activity, sleep) |
| `unregistered_but_has_data` | **rows exist under a name the registry does not know** | 4 (recovery, vitals, content, money) |
| `unregistered_and_unbuilt` | no registry entry and no rows anywhere | 4 (attention, food, places, workouts) |
| `registered_no_observations` | defined, never captured | 3 (body, drink, mood) |
| `no_hero_metric` | the domain names none | 1 (calendar) |

Those five point at four different fixes: confirm a rename, build a measure, fix capture, or
choose a hero metric. Collapsing them into "no data" sends someone hunting for data that was
never captured, or worse, leaves a rename invisible.

## It resolves by exact name, deliberately

A string-similarity search proposes **`sleep_awake_min` for `away_min`** — time *awake in bed*
offered as time *away from home*. The tooling cannot tell a rename from a coincidence, and a
wrong map here is invisible and permanent: the surface would look correct while attributing one
measure to another. CLAUDE.md reserves data definitions for Joe, so this function reports the
gap and never closes it. A test asserts that a similarly-named metric's rows are **not**
borrowed.

## Band position is three-valued

A missing baseline band yields NULL, not `in_band`. Defaulting to inside would make an
unmonitored metric look reassuring, which is the same failure in a smaller place (RULE-07).

## What this does not decide

The eight mappings are OQ-60 and remain Joe's. This makes the gap queryable so the answer can
be applied to data rather than to prose, and so B15's weekly report can be built against a
truthful foundation whichever way the mappings go.
