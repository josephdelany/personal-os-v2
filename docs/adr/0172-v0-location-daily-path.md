# ADR-0172 — V0 location collection and daily readback

Date:2026-09-24. Status: accepted and locally verified; not activated.
Scope: ADR0165 V0 visits/day; CAP017, LOC001/002/004/006/009/012/013/015/018,
RULE02/03/05/06/10/12/14/29. No new geofence or mobility definitions.

The existing Overland batch RPC generates a new capture UUID on every retry.
The unused direct Shortcut fallback also accepts anonymous writes. These fail
the V0 retry and access-control bar. The existing movements read additionally
uses session-timezone day boundaries and includes mobility analysis beyond V0.

Keep the approved Overland transport (ADR0046), restricted coordinate storage,
existing provisional visit thresholds and in-database derivation. Fix retry
identity, provide owner-only labels/times/coverage/freshness, then compose visits
and imported card activity with the current V0 daily response. Do not add a new
tracking app, behavioral interpretation, location export, model call or cost.

## Collection boundary

Only the token-authenticated Overland edge receiver needs batch ingestion.
Revoke app-role execution of the unused direct location writer; retain the
service-role batch capability. This supersedes ADR0044 item4's anonymous fallback
permission. Repository callers were inspected: no built Shortcut/UI caller uses
that fallback. No constitutional permission or evidence rule is weakened.

Persist retry evidence only inside the restricted store, never raw coordinates
or their content digests in an owner read, public capture payload or log. Exact
replays and overlapping/reordered batches must retain one fix per source record.
Keep original point data; exclude transport-only batch count from record identity.
Never treat a device identifier as a unique measurement identifier. Invalid input
must not acknowledge unpersisted evidence or partially commit a batch.

Primary protocol reference inspected2026-09-24:
https://github.com/aaronpk/Overland-iOS/blob/master/README.md
Its API section defines queued GeoJSON points, optional current/trip envelopes,
device identity, locations_in_payload as a batch count, and result=ok as the
acknowledgement that removes records from the phone queue. That acknowledgement
must follow durable receipt. Device setup/real transport verification remain open.

## Read and refresh boundary

Use explicit 04:00 America/New_York bounds with independent next-day construction
across DST. Show event time separately from received time; missing data is unknown,
not zero visits or assumed presence at the last known location. A saved fix is
distinct from a derived visit. Preserve provisional labels and registered-place
matching; no nearest-place guess or interpretation. A late offline batch must have
a refresh path for its actual dates, not just the scheduler's most recent days.

The implementation must retain traceable visit inputs, current human assignments,
coordinate-free outputs and calculation provenance. The daily response reuses the
existing check-in/meal/workout/health and card activity owners instead of duplicating
their computations. Canonical finance and advanced mobility remain later work.

Acceptance: reproduce batch replay and anonymous-write gaps; prove exact/overlap
retries, invalid/conflicting input rollback, role boundaries, original evidence
privacy, day/DST/freshness behavior, missing/no-visit distinction, late refresh,
human assignment survival and daily composition in disposable schemas. Verify the
transport response path and document activation separately from local tests.

## Implemented contract and review

0096 retains the first accepted full source feature and canonical identity record
in immutable restricted receipts. Only locations_in_payload is removed for identity;
later retries with a different transport count reuse that first evidence rather
than editing it. No receipt hash crosses the restricted boundary. Batch responses
include stable capture IDs and inserted/duplicate counts; the existing edge still
returns the Overland result acknowledgement only after the RPC succeeds. Record
identity begins with this migration: no claim of deduplicating old pre-receipt
transport history is made. Strict timestamps refuse silent clock normalization,
and motion elements must be strings. Failed batches roll back all their new rows.

Visits-v2 remains the existing derivation owner with unchanged provisional
thresholds. It records contributing capture IDs and a stored first-to-last observed
span, excludes negative accuracy, orders timestamp ties by capture ID, and extends
refresh context to whole affected stays. A refresh cut can no longer create a
second overlapping copy of a stay begun on a prior subject day. No departure time
is invented beyond the last actual observation. When rebuilding would merge
conflicting human place assignments, the transaction refuses and preserves the
prior visits; an explicit owner correction can resolve the conflict before retry.

refresh_v0_visits bootstraps existing restricted fixes once, then refreshes the
recent interval and any older dates introduced by newly received batches. This is
derived-data rebuilding, not import of legacy public locations or archived data.
The existing hourly extract job calls this wrapper. Receipts and refresh share a
lock and require READ COMMITTED, so a refresh watermark cannot skip a concurrent
new batch. Current server clocks stamp receipt/fix/derivation metadata.

get_v0_visits shows whole visits overlapping the selected04:00ET window, preserving
their original source_subject_day. This is a view selection, not reassignment of
facts or resolution of OQ53. Span values describe the whole observed visit, not a
daily total or continuous-presence claim. No coordinates or content hashes leave
the function. Missing, awaiting_derivation, no_detected_visits and available states
remain distinct; presence stays unknown when no explicit absence was recorded.
Each exact read response is stored privately with its trace and method metadata.

get_v0_day now composes these reads and per-account card activity with the original
health/check-in/meal/workout owner, moved into core as a private helper. Card dates
remain source transaction calendar dates; no intraday financial time is inferred.
The read RPC uses POST because the returned computations are persisted. This is
current-knowledge history, not historical point-in-time reconstruction.

Focused location/day/legacy regression73passed1production-only skip10.07s. Review
caught historical bootstrap and timestamp normalization; both fixed and tested.
Human-conflict refusal and server-clock ordering also passed. Full SQL: 1242 passed, 1 production-only skip (415.41s). Sanctioned feature
writer: 1473 passed, 1069 skipped; feature ledger remains14/15. Migration chain:
95 migrations/1037 statements; layout43 passed. Four scoped spine invariants pass;
generic RULE04 remains pending. Merged43 unverified skips remain (41 production,
2 NumPyro). Independent review accepted the repaired behavior. Evidence and tested
source hashes: .local/evidence/v0-location/. No production/device activation,
independent committed-concurrency proof or completed V0 claim.
