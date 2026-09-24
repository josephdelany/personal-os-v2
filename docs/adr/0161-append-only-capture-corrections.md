# ADR-0161 — Append-only owner correction of saved capture results

Date: 2026-09-23. Status: reference/quantity/removal path locally verified; full CAP014 and deployment open.

CAP014 and RULE02/03/10 require human corrections to supersede derived results,
preserve old evidence and survive later automatic work. Current capture resolution
returns the prior completed outcome after enrichment, and the existing nutrition
review writer changes cache/review rows without replacing saved capture atoms.

## Representation and authority

Add an immutable owner-correction request ledger and a version chain for
capture_resolved_items. A request records the complete validated payload, actor,
expected current item and server knowledge time. New versions retain the original
capture/extraction identity; they do not rewrite extraction or raw evidence.
Serialize by capture, require the expected current version, and constrain one
successor per predecessor. Reusing a request ID with different input refuses.

Corrections use a dedicated private owner capability, separate from the automated
service/model/reference roles. Recording supplied_by=joe is required metadata,
not sufficient authorization by itself. Only the owner capability may create the
correction request. No model or reference response becomes a correction request.
The private runtime may read completed corrections but cannot originate them.
Provisioning that owner capability is a deployment action, not performed here.

The existing nutrition owner computes replacement intervals against an explicitly
bound source-cache version and corrected quantity. Reference/quantity changes,
whole/fraction component changes and item removal are covered by this first path.
Correction metadata identifies the source version, quantity/time provenance,
calculation version and actor. Name/time editing remains a separately identified
CAP014 acceptance case, not presumed closed by quantity correction.

## Supersession and removal

Matching metric/component atoms use the existing supersedes relation. When an old
metric/component no longer exists, append an explicitly marked retraction atom
that supersedes it. A retraction is structural correction metadata, not a new
clinical/food kind, a measured zero or an observation of absence. Preserve the
predecessor's capture/item/metric/component identity; require a predecessor and
authorized correction reference, unknown presence and no numeric/text/value-range
payload. Do not relax ordinary atom constraints or immutable-row triggers.

Current views exclude retraction rows from results but INCLUDE them when deciding
whether an older row was superseded. As-of readers include only supersession rows
known at their cutoff. Current capture readback selects the latest item version;
it must not show obsolete item versions or retractions as nutrient observations.
Review every direct atom reader, not only atoms_current, including historical
analysis and domain-status coverage. A split whole/fraction result corrected to a
single total must retire both old components without double counting or fake
missing measurements. Complete item removal retains its correction/version history.

Request, item version, new/retraction atoms and processing/readback outcome are one
transaction. Mid-operation failure rolls everything back. Replays return the same
saved outcome; stale predecessors refuse; automatic retries cannot supersede an
owner result. No mutation or deletion of original captures, extraction, items or atoms.

A partially resolved capture can still have pending enrichment. New extraction
preparation refuses once resolved items exist. Already prepared transcription or
extraction outcomes are recorded with `applied=false` by the processing-event
guard, even if their expected processing head still matches. They cannot replace
the transcript/extraction underlying corrected items, but remain consumable for
mailbox retirement and exact replay. Resolution requests for the remaining items
continue normally. This closes a current-readback bypass that a nutrient-only
supersession guard cannot prevent.

## Acceptance and limitations

Prove current capture readback, nutrition totals and historical analysis before
and after quantity correction, component-shape change, omitted nutrient and item
removal. Cover repeated corrections, identical/conflicting retries, stale targets,
invalid inputs, role denial and rollback after partial work. Independently review
the implementation and run migration-chain/full-suite/invariant/layout gates.

All local SQL fixtures remain disposable and rollback-only. Actual independent
commit/crash durability is not claimed without OQ82's ungranted fixture exception.
No migration is applied to production here. No new external dependency, recurring
cost, egress destination, measurement definition or frontend work. Full CAP014,
M3 and M6 closure require their remaining acceptance and deployment evidence.

Read-only design review identified fork prevention, direct readers, retraction
shape, component transitions, human authority and provenance as mandatory checks.
This ADR preserves the existing integrity rules; it does not amend them or settle
the reserved atom-kind taxonomy or measurement decisions.

Local integration on dirty root21faf12: targeted84pass58.55s; fullSQL1065pass/1live
skip374.88s; noDB1427pass892skip159.51s; chain88/932; layout43; independent review
accepted final owner precedence and obsolete-result retirement. Generic RULE04,
name/time/unresolved-field corrections and production observations remain open.
The41 production-guarded and2 NumPyro checks remaining after merged reconciliation
are unverified, not passed. Evidence: .local/evidence/capture-corrections/final/.
