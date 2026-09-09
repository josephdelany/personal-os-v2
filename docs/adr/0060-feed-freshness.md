# ADR-0060: Freshness is a property of the data, not of the job

## Status
Accepted. Authors REQ-NFR-005..012 (`specs/06-nfr/requirements.md` §C) and amends that
file's "feed staleness alerting" non-goal. Builds `tools/check_freshness.py` and the
`freshness` workflow. Partially discharges Gate 4; the withheld-feed demonstration is still
owed. Related: ADR-0057 (the recovery path for the outage this describes), OQ-50.

## Date
2026-09-09

## Context

`ops.runs` answers "did the job run?". Nothing answered "did anything arrive?".

Between 2026-07-28 and 2026-09-09 those two questions had different answers for 43 days:

| Question | Answer during the outage |
|---|---|
| Did `panel_build` run? | Yes, daily, `status='ok'` |
| Did `derive_visits` run? | Yes, daily, `status='ok'` |
| Did both keepalives fire? | Yes, daily, `status='ok'` |
| Did any heart-rate, HRV, sleep-stage, browser or location data arrive? | **No. Not one row.** |

Every job succeeded over an empty input, and succeeding over an empty input is
indistinguishable from succeeding, from the outside. `tools/status.py` was improved in an
earlier session to stop reporting failed and running jobs as healthy — a real fix to a real
problem, and one that would not have caught this, because none of these jobs failed.

The NFR spec had already anticipated the mechanism and deferred it: "Detecting that a *data
source* has gone quiet is Phase 4 (Gate 4), a different mechanism from keeping the platform
itself alive." That was right about the mechanism and wrong about the sequencing. The
platform was kept alive impeccably while the thing it exists to hold stopped being collected.

## Decision

1. **The staleness limit is stored configuration, never a number in code** (REQ-NFR-005).
   `core.metric_registry.max_staleness_days` already existed and was unused. The checker
   reads it. A threshold in code is a threshold that gets edited to make a check pass, which
   RULE-00 exists to forbid; a threshold in the registry is data, and changing it is a
   visible change to data.

2. **Freshness is measured from the most recent `subject_day` carrying an observation, never
   from a job's completion time** (REQ-NFR-012), and the clock it is compared against is the
   **current subject day**, not the database server's `current_date`. This is the whole point.

   The clock detail is not pedantry. `current_date` on Supabase is UTC; a stored `subject_day`
   turns at 04:00 ET. The workflow's 08:10 UTC cron is 04:10 ET in summer (just after the
   boundary) and 03:10 ET in winter (just before it), so a UTC clock and an ET subject day
   agree from March to November and differ by a day the rest of the year. Using the subject day
   on both sides removes the seam rather than moving it.

   *A correction to this ADR's own first version:* it claimed the seasonal error would make
   winter counts one too HIGH and turn metrics red. The direction is the other way — with a
   fixed-UTC cron the check simply runs shortly before the new subject day opens in winter, so
   detection is delayed by at most one run and staleness is never fabricated. Reporting late is
   the safer of the two errors, but the claim was wrong and is corrected rather than deleted. `test_REQ_NFR_012_a_
   successful_job_over_an_empty_input_is_not_freshness` reproduces the outage directly: it
   fills `ops.runs` with successful runs finishing today and asserts the check still fails.

3. **Both stores are consulted, and the later day wins.** `core.atoms` is the spine's
   observation store; `analysis.panel` is where the old stack's still-live feeds land.
   Checking only one would report a live feed as quiet during the very migration period when
   both are half-populated.

4. **Three states, and only one of them fails** (REQ-NFR-006/007/010):
   - `stale` — reported before, quiet now. **The only state that exits non-zero.** This is
     the 2026-07-28 signature.
   - `misconfigured` — nothing under this key, but a **similar** key does carry a series. The
     metric is registered for monitoring and is not being monitored. **Fails**, because it is a
     real and actionable defect rather than absent scope. The candidate is a suggestion and
     never an alias (REQ-NFR-014): deciding two differently named series are the same
     measurement is a ruling, and a monitoring tool has no business making it by string match.
   - `never_seen` — no observation under this key and nothing resembling it. Unbuilt scope.
     Counted and reported; does not fail.
   - `unmonitored` — registered with no limit. Counted and reported, so a metric escaping
     monitoring is visible rather than absent.

   The split matters more than it looks. Collapsing `never_seen` into `stale` would leave
   the check permanently red — today it would report 13 never-seen metrics — and **a check
   that is always red is a check nobody reads.** That is the same failure as no check at all,
   arrived at by a different route.

5. **The report never carries an observed value** (REQ-NFR-011): metric key, last day,
   elapsed days. An operational alert must not become an egress path (RULE-29). The test uses
   a value that would be unmistakable if it leaked, and asserts it appears neither in the
   report nor in the `ops.runs` detail.

6. **Its own workflow, on its own schedule, ahead of `analysis`.** A freshness check that runs
   as a step inside the pipeline it audits shares that pipeline's fate: if `analysis` fails
   early the check never runs, and that silence looks exactly like health. GitHub's own
   failed-run notification is the alert channel — no third party, no recurring cost.

## What it says today

The first run against the live database, before any repair:

```
freshness as of 2026-09-09  fresh=0 stale=4 never_seen=13 unmonitored=6

STALE — reported before, quiet now:
  steps                            last 2026-07-17  54d elapsed (limit 3d, via panel)
  checkin_morning_drive            last 2026-07-22  49d elapsed (limit 2d, via atoms)
  checkin_morning_energy           last 2026-07-22  49d elapsed (limit 2d, via atoms)
  checkin_morning_restored         last 2026-07-22  49d elapsed (limit 2d, via atoms)
```

**Zero metrics fresh.** Had this existed on 2026-07-31 it would have gone red on the fourth
day, and the 43-day gap would have been a three-day one.

## Consequences, including the uncomfortable one

- A quiet feed now fails a daily scheduled run instead of passing it silently.
- **Registered metrics that have never been observed under their registry names are the
  system's largest monitoring gap.** Several are naming mismatches rather than missing data:
  the registry says `hrv_sdnn_ms` and `resting_hr`, the panel carries `hrv_sdnn` and `rhr`.
  Review showed the first version filed all of them under the non-failing `never_seen` state,
  which meant **the checker was blind to precisely the feeds its own rationale names** — 133
  rows of HRV that stopped on 2026-07-28 were reported as never having reported, and the run
  passed on that count. The `misconfigured` state exists to fix that, and it fails.

  Its reach is limited and the limit is stated in the tool's own output: the detector finds
  only resemblances a string comparison can find. It connects `hrv_sdnn_ms` to `hrv_sdnn`; it
  does **not** connect `resting_hr` to `rhr`, and no threshold would without inventing false
  pairs. A metric in `never_seen` may therefore still be unmonitored under another name.
  **Reconciling registry names to panel names is unfinished work** (OQ-51).
- `analysis.panel` is consulted only when it exists. Hardcoding it meant a fresh installation
  raised, `main()` returned 2, and the workflow reported an unreachable-database-class failure
  for what is a schema-shape difference.
- Gate 4 is **not** closed by this. Its criterion is that "a deliberately withheld feed raises
  an alert within its limit, demonstrated". The mechanism exists and its unit tests pass; the
  live demonstration has not been run.
- The check tells Joe a feed died. It does not restart it. Restarting device-side capture is
  OQ-50 and needs Joe's phone.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Registry-driven metric freshness (adopted)** | The limit is data, the check is code, and the two are separable. |
| Extend `tools/status.py` | Rejected. Its question is job liveness and that is a different question; merging them produces one number that means two things and hides whichever is healthier. |
| Alert on `public.signals` per source | Attractive — it is closer to "a feed died" than metric-level is — but every threshold would have to be invented, since no source-level registry with limits exists. Deferred rather than guessed. |
| An alias table mapping registry names to panel names | Rejected for now. Asserting two series are the same measurement is a claim about data, and it should be made deliberately with an ADR, not inside a monitoring tool to make its output tidier. |
| A third-party uptime/alerting service | Rejected on RULE-28 and RULE-29: a recurring cost, and it would need to be told what is missing. |
