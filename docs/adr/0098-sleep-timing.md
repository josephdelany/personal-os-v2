# ADR-0098 — Three facts about one night, and why a nap is not part of it

Status: accepted (`tools/engines/sleep.py`; no migration, no production write)
Date: 2026-09-09
Requirements: REQ-SLP (authored against this build), RULE-06, RULE-07, RULE-08, RULE-12.

## Three facts that are not the same fact

- **Duration** — how long Joe was asleep: the union of the asleep segments. Awake-in-bed
  excluded. Already in the panel as `interval_union_minutes` (ADR-0089).
- **Window** — onset to final wake. It *contains* the awake periods, so it is always ≥
  duration and is not a duration under another name.
- **Midpoint** — the centre of the window. It says *when* Joe slept, not how much, and it is
  the input to regularity.

A 6-hour duration inside a 9-hour window is a different night from 6 hours inside 6. Any
measure reporting one number for both erases that, which is the OQ-48 family of error in a new
place.

## The defect the real data found

A subject day can hold a night **and a nap**. The first version treated every segment in a day
as one period, and **2026-07-14 held two blocks 352 minutes apart** — producing a 938-minute
"window" containing 586 minutes of sleep, with a midpoint at 13:14 local.

That single night pushed the regularity spread across 23 nights from plausible to **208.5
minutes**. Splitting sessions on the importer's existing three-hour gap took it to **87.2**.
The nap is now disclosed as `other_sessions` rather than folded into the night.

The constant is **imported from `tools/importers/apple_health.py`**, not restated (RULE-12).
If the engine and the importer could disagree about where a night ends, one night could be two
facts, and a test asserts they are the same object.

## The midpoint is local, and anchored on noon

Computed in UTC, a March daylight-saving change would shift every midpoint by an hour and read
as Joe's sleep shifting. Anchoring on noon keeps 23:50 and 00:10 twenty minutes apart rather
than twenty-three hours — without it, a spread over a midnight-crossing sleeper is arithmetic
on a bimodal distribution and means nothing.

## Honest limit, not resolved

"Main session" is the longest by time asleep. On 2026-07-14 the two blocks were 331 and 254
minutes, and picking the longer may well have picked the *morning* sleep rather than the night.
There is no principled way to choose "the night" from two comparable blocks without asserting
when Joe sleeps, which is a measurement definition and his. The count and duration of other
sessions are returned so the ambiguity is visible rather than resolved by fiat.

## Coverage

Regularity refuses below seven nights: fewer than that and "usual bedtime" is not a meaningful
phrase (RULE-06). A missing night is absent from the statistic, never imputed as the median —
counting it as usual would make an irregular sleeper look regular in exactly the weeks the data
is worst (RULE-07). Every figure is a spread and carries no target (RULE-08).

## Not done

`REQ-SLP` is not yet authored as a spec file; these measures are built against the intent
recorded in the B21 brief, and the IDs are owed. REQ-BOD and REQ-CTX have no data at all —
`weight_lb` holds zero rows — so their measures are not built and would be untestable if they
were.
