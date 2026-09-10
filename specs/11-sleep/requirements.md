# 11 — Sleep and recovery

Status: specified 2026-09-09. §A implemented (`tools/engines/sleep.py`, ADR-0098); §B and §C OPEN.
Scope: what one night IS, how nights compare, and what may be said about recovery.
Complements REQ-INF cross-lens statistics; does not replace them.
Decision: ADR-0098. Measurement definitions Joe has not ruled remain OQ-48 and OQ-60.

## A. What one night is

**REQ-SLP-001** (Ubiquitous) The system SHALL represent a night as three distinct measures — sleep DURATION (time asleep), sleep WINDOW (onset to final wake, containing any awake period), and sleep MIDPOINT (the centre of the window) — and SHALL NOT report one of them under the name of another.

**REQ-SLP-002** (Ubiquitous) Sleep duration SHALL be the measure of the UNION of the asleep intervals, so that two overlapping segments are counted once, and SHALL exclude time recorded as awake.

**REQ-SLP-003** (Ubiquitous) The system SHALL determine the boundary between one sleep session and the next from a single stored gap constant shared with the capture path, and SHALL NOT define that boundary independently in any consumer (RULE-12).

**REQ-SLP-004** (Event-driven) WHEN a subject day contains more than one sleep session, the system SHALL report the main session's measures and SHALL disclose the count and duration of the other sessions separately, and SHALL NOT merge them into the main session's window.

**REQ-SLP-005** (Unwanted behaviour) IF two sessions in one subject day are of comparable duration, THEN the system SHALL NOT assert which is "the night" beyond its stated main-session rule, because choosing between them asserts when Joe sleeps, which is a measurement definition reserved to him.

**REQ-SLP-006** (Ubiquitous) Sleep efficiency SHALL be duration over window, and SHALL be reported as undefined — never as 1.0 — where the window is zero.

**REQ-SLP-007** (Ubiquitous) The sleep midpoint SHALL be computed in a fixed local timezone and expressed relative to a noon anchor, so that a daylight-saving transition does not shift it and so that times either side of midnight are adjacent rather than a day apart.

### NON-GOALS
A sleep score, a sleep debt against an unstated target, a stage-quality judgement, or any
single number standing for "how well Joe slept".
### ALTERNATIVES CONSIDERED
Reporting duration alone was rejected: a 6-hour duration inside a 9-hour window is a different
night from 6 inside 6, and the difference is the part a person can act on. Computing the
midpoint in UTC was rejected: a clock change would move every midpoint by an hour and read as
Joe's sleep shifting.
### UNRESOLVED QUESTIONS
OQ-48 governs which stored metric means "how long did I sleep"; `sleep_inbed_min` remains a
fourth concept and is never used as a duration. OQ-60 governs the `sleep` domain's hero metric.

## B. Comparing nights

**REQ-SLP-010** (Ubiquitous) Sleep regularity SHALL be reported as the SPREAD of sleep midpoints over a window, SHALL carry the count of nights actually used, and SHALL NOT be accompanied by a target or a threshold until one is calibrated to Joe.

**REQ-SLP-011** (Unwanted behaviour) IF fewer nights carry sleep timing than the stated minimum, THEN the system SHALL return an insufficiency naming the shortfall and SHALL NOT compute a regularity figure.

**REQ-SLP-012** (Ubiquitous) A night with no recorded sleep SHALL be treated as unknown and SHALL be absent from every aggregate, and SHALL NOT be imputed as a typical night, because imputing it would make an irregular sleeper appear regular in exactly the weeks the record is worst.

**REQ-SLP-013** (Ubiquitous) Every sleep aggregate SHALL report its coverage — nights with data against nights in the window — alongside the figure.

### NON-GOALS
Ranking Joe's weeks; streaks; any presentation that makes a missing night look like a bad one.
### ALTERNATIVES CONSIDERED
A mean midpoint with no spread was rejected: it states a precision a small sample does not have
and hides the variation the measure exists to describe.
### UNRESOLVED QUESTIONS
The minimum-nights floor is a stated judgement, not a calibrated one; it is provisional in the
same sense as OQ-36's ACWR windows.

## C. Recovery, and what may be said about it

**REQ-SLP-020** (Ubiquitous) The system SHALL treat HRV, resting heart rate, respiratory rate and wrist temperature as SEPARATE measures with their own coverage, and SHALL NOT combine them into a composite recovery score (RULE-24).

**REQ-SLP-021** (Event-driven) WHEN a recovery measure's capture has lapsed, the system SHALL report the lapse with the date of the last observation rather than presenting the most recent stale value as current (REQ-NFR-005..014).

**REQ-SLP-022** (Unwanted behaviour) IF a sleep or recovery figure would be rendered as advice about a medical condition, THEN the system SHALL return the stored referral string instead (RULE-26).

**REQ-SLP-023** (Ubiquitous) A statement relating sleep to any other measure SHALL carry the evidence tier and coverage the reasoning layer assigns it, and SHALL NOT use causal vocabulary without a confirmed finding (REQ-ASK-032, RULE-19).

### NON-GOALS
A readiness number; a recommendation to sleep more; any inference from a single night.
### ALTERNATIVES CONSIDERED
A composite recovery index was rejected under RULE-24 and because its inputs have wildly
different coverage — HRV stops on 2026-08-21 while steps continue — so the composite would
silently become a proxy for whichever input still has data.
### UNRESOLVED QUESTIONS
Whether `hrv_sdnn` and `rhr` (the domain hero metrics) are the same measures as the registered
`hrv_sdnn_ms` and `resting_hr` is OQ-60 and is not decided here.

## Traceability

| Requirement | Built by | Tested by |
|---|---|---|
| REQ-SLP-001, 002, 004, 006 | `tools/engines/sleep.py` | `tests/test_sleep.py` |
| REQ-SLP-003 | shared `SLEEP_SESSION_GAP` | `test_RULE_12_the_session_gap_is_the_importers_own_constant` |
| REQ-SLP-005 | disclosed, not resolved | `test_REQ_SLP_004_a_nap_is_disclosed...` (the count it discloses) |
| REQ-SLP-007 | `midpoint_minutes` | the daylight-saving and midnight tests |
| REQ-SLP-010, 011, 012 | `regularity` | `tests/test_sleep.py` |
| REQ-SLP-013 | `nights_used` | `test_RULE_07_a_missing_night_...` |
| REQ-SLP-020..023 | OPEN | — |
