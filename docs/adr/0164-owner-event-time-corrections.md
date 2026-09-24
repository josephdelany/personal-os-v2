# ADR-0164 — Owner correction of a resolved event time

Date: 2026-09-24. Status: accepted; locally implemented and verified, not deployed.
Requirements: CAP014/066, RULE02/03/05/06/10/12. Extends ADR0161.

Add `retime` to the existing private owner command. Require an explicit ISO-8601
timestamp with numeric offset or Z and an explicit existing time-precision value.
Reject timezone-free dates, natural language and extra nutrient/source fields.
Normalize the instant to UTC for request identity and replay. The original capture,
transcript and extraction remain immutable. This does not change dateparser's
automatic temporal-expression policy or settle OQ53's reserved measurement axes.

The existing `tools.importers.common.subject_day` remains the sole calculation
owner for personal-day assignment. Store its result in the correction ledger and
bind the new item version to that day, instant and precision. Explicit owner input
has time provenance `extracted` from that request, with reason `owner_correction`;
nutrient provenance and quantity provenance remain unchanged. The new timestamp's
precision is supplied rather than guessed from formatting.

Time-only correction copies the prior resolution and current nutrient atoms;
it must not re-fetch a food, recompute an interval, change component shape or revive
a removed item. Database checks preserve all non-time atom values/provenance and
require predecessor links. Retraction is not a time correction. Current totals move
to the new personal day, while knowledge-cutoff reads retain the old placement.
Fixing defaulted time may make a record eligible for statistics; it cannot promote
a defaulted quantity. Later quantity/reference corrections retain the corrected time.

Use the existing capture lock, owner capability, stale-version refusal, atomic
savepoint and immutable result replay. The ledger binds the complete request;
changed timestamps or precision under a reused request ID refuse. No new provider,
dependency, recurring cost or production action. Fixture rows remain rollback-only.

Acceptance: current capture/day/as-of readers; cross-day and personal-boundary
cases; exact numeric/component preservation; defaulted time and quantity separation;
repeat time/quantity/removal operations; stale/conflicting replay, invalid input,
unauthorized role, database mismatch rejection and partial-write rollback. Full
integration and independent review remain required. CAP014 name and unresolved-field
corrections and full backend M0–M6 release are not closed by this unit.


Independent review (2026-09-24): found that Python normalizes malformed offset
minutes such as +01:99. The input grammar now limits offset hours to00–23 and
minutes to00–59 before parsing; positive and negative malformed-offset regressions
pass. Final review found no further scoped blocker, covering stored-value copying,
historical reads, day boundary, mixed operations, request identity and rollback.
The SQL item-day check binds to the ledger; the existing subject_day calculation
in the trusted owner engine remains responsible for calculating that ledger value.
This is not a second database implementation of the day policy.
Targeted SQL93passed; request/CLI41passed; migration chain89files935statements;
layout43passed. Full integration:1074SQLpassed/1production-only skip483.03s; sanctioned feature
writer1441passed901skipped214.57s. Four scoped spine invariants pass; generic
RULE04 remains pending. Merged43 unverified skips (41production,2NumPyro), feature
ledger14/15 unchanged. Evidence .local/evidence/capture-retime/; tested source
hashes unchanged. These results close this unit, not full CAP014 or M0–M6.
