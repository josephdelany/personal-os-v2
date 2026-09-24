# ADR-0170 — V0 day and imported health read contract

Date:2026-09-24. Status: accepted; local integration verified, activation pending.
Scope: daily V0 backend (ADR0165); RULE02/05/06/10/12/29, ASK021, WKT003/018.

## Observed gap

The existing get_day/get_timeline responses do not compose the new V0 entry
ledgers or consistently supply units and event/received timestamps. Some date
bounds depend on the database session timezone. The legacy timeline also mixes
legacy public records with atoms. Reusing those responses wholesale would not
meet the approved Today/History contract.

## Proposed integration

Add one owner-authenticated V0 day read that composes get_v0_checkins,
get_v0_meals and get_v0_workouts, retaining their current entry and predecessor
IDs, saved states and domain-specific missing/pending semantics.

Provide imported health/activity in distinct sections:

- Latest actual measurements: native metric key and registered unit, atom and raw
  capture identity, observed event time, atom recorded time and capture received
  time. Keep a latest observation distinct from a daily aggregate.
- Daily activity: reuse analysis.f_atom_panel and its configured aggregation and
  device precedence. Return selected device, method/version and source counts.
  Never independently sum all Watch and phone atoms. Use the atom-backed lane;
  do not quietly substitute legacy UTC-day data through f_daily_panel.
- Recorded workout sessions: current workout_session_min atoms with active
  duration and valid_interval separately. A session is not an individual set,
  and elapsed interval length is not the active duration.

Do not choose hero aliases, rename measurements, guess source identity or settle
OQ48/51/53. Preserve the existing subject-day convention and explicit timestamps.
Actual event/received times must be visible even when a late import is recent.
Domain status may be reused only where its definition matches; last subject day
is not a receipt timestamp. Missing observations stay empty/null, never zero.
Advanced inference, health interpretation and coaching remain outside this unit.

## Acceptance required

Owner/anonymous/nonowner, current V0 IDs and corrections, missing day, selected
device overlap, distinct event/received timestamps on late import, DST and04:00
boundaries independent of database timezone, current/superseded atoms, native
units and provenance, session active duration versus interval length. Exercise
actual public RPCs against disposable schemas; provide a caller/runbook and
activation procedure. Real-data freshness remains separately unverified until
actual account/source inspection succeeds.

A read-only reviewer confirmed the reusable owners and gaps. This design does
not claim the complete V0 day contract: spending/visits and real-account acceptance
remain explicit handoff obligations in EXECUTION_PLAN.

0094 implements the owner RPC. Initial tests found transaction-start knowledge
excluded fresh rows stamped with clock_timestamp under ADR0149; corrected to
statement_timestamp. Reviewer also found global panel results could mix another
importer or incompatible units. The read now withholds those selected-device
results with a reason, without changing the aggregation owner's arithmetic.
Unselected device data cannot poison the selected result. Missing registered
aggregation is explicit; activation must verify actual available metrics have
appropriate existing configuration. No runtime configuration mutation occurs.

Expanded15targeted SQL cases cover these fixes, current IDs, late receipts,
corrections, DST boundaries/04:00 selection, units and owner bounds. Independent
review accepted the final scoped fixes. Full integration and real-account
activation remain separate; no V0 completion claim.

Final local integration:1177SQLpassed1production-skip377.83s; feature writer1451
passed1004skipped165.97s; chain93migrations974statements; layout43pass. Four spine
invariants pass; generic RULE04 pending. Merged43unverified skips (41production,
2NumPyro); ledger14/15 unchanged. Final hashes/evidence .local/evidence/v0-day/.
No production or real-account proof. Actual aggregation configuration remains an
activation check, and spending/visits remain explicit V0 obligations.
