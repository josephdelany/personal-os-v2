# ADR-0155 — Isolated, durable reference dispatch

Status: implemented and tested locally; private handoff/runtime open, not deployed.
Date: 2026-09-23. REQ-NUT-003–012; RULE-09/28/29; ADR-0020/0154.

The voice-to-atoms path needs reference data when its private cache misses. The
private stage must not acquire source API capabilities. A dedicated reference
process receives only a bounded, persisted lookup request, uses the existing USDA
and Open Food Facts adapters, and returns a receipt-bound result for private cache
consumption. It authenticates directly as reference_egress, never SET ROLE from a
private reader. Private credentials in its environment cause refusal.

Reuse migration0072's rate events/cooldowns. A serialized database reservation
charges one request to USDA's shared meter or the corresponding OFF meter before
sending. Reservation and audit must commit before any network call. Unknown commit
outcomes refuse sending; a used request identity is never dispatched twice. USDA
429 cooldown survives process exit. The dispatcher holds a session advisory lock
through reservation, HTTP and settlement, so a queued dispatcher observes the
previous429 before obtaining a permit. Quota counting includes the60-second permit
lifetime in addition to the provider window; delayed sends cannot age out early. Separate immutable results bind request and
response digests; private consumption must check that receipt before publishing a
cache row. Reservations are conservative charged attempts, not proof of delivery.

No new dependency, service or recurring charge. Existing source accounts and free
limits remain binding; limits defer instead of spending. GET transport accepts only
HTTPS endpoints, refuses all redirects, and bounds response bytes to2MiB (single
capped search page/product). The socket timeout is not a whole-process deadline;
the separated supervisor still must impose and reap an overall deadline.

Local tests use injected transports and rollback-only disposable SQL. They cannot
prove commit survival or simultaneous independent database sessions. The complete
runtime gate remains open until private preparation/consumption, source dispatch,
process scheduling and applicable observed acceptance are connected and exercised.


The existing adapter writes a per-HTTP detail log inside the settlement transaction;
the separately committed reference reservation log is the durable pre-send audit.
These are two audit stages of one reserved request, not two charged network calls.
A crash may leave a reservation with no receipt; it must not be replayed with the
same ID. Recovery needs an explicit new attempt, still charged to the persisted meter.
The2MiB transport bound and redirect repair also apply to existing source callers.


## Interrupted attempts

The global session lock also supplies the boundary for discovering interrupted
predecessors. After acquiring it, a new dispatcher can observe reservations without
a result that no active dispatcher still owns. Reservation maintenance appends an
immutable `uncertain` outcome with NULL response hash/status. It does not manufacture
a response or a provider429. For USDA it starts a conservative60-minute cooldown
at discovery time, covering an unrecorded rate-limit response immediately before
the predecessor lost its session. The next fresh request may proceed after expiry.

A denied permit can perform this maintenance, so its transaction must commit before
returning refusal. Unknown commit acknowledgement emits no network request. Late
settlement cannot rewrite an uncertain outcome. Independent-process crash and
connection-loss evidence remains required; rollback SQL and commit-order probes
prove only their scoped state transitions and ordering.


Final local integration:939 SQL passes/1 production-only skip,1181 noDB passes/772
skips,83 migrations/829 statements and43 layout checks. Final scoped review accepted
the timing/interruption repairs. Evidence and remaining gates are in PROGRESS and
COMPLETION_AUDIT; this is not a complete capture-runtime or deployment claim.

## Private handoff (implementation continuation)

Private preparation binds the saved extraction, item index, selected source and
processing predecessor to an immutable exact lookup payload/hash before export.
The source runner receives no capture identity or transcript. A private consumer
requires both the prepared request hash and isolated response receipt, rechecks the
exact match and reparses the source payload through its existing adapter, then writes
cache, verbatim alias and immutable consumption outcome in one savepoint. It never
accepts model nutrient values. Stale extraction records an unapplied outcome without
cache publication. Completed same-ID deliveries reuse the saved outcome.

This handoff initially accepts an explicit source stage; it does not pretend to
finish automatic source ordering, barcode/brand extraction or TTL refresh. Those
remain consuming runtime requirements in the same voice path. No new dependency,
service, authorization or recurring cost is introduced.

Draft0085 recovery continuation: service-only `reconcile_reference_call` acquires
the existing dispatcher lock and records a lone abandoned request as uncertain,
including the existing USDA cooldown policy. No extra request is required for orphan
discovery. Existing settled receipts are preserved and unknown reservations refuse.
The source-only `settle_reference_response` RPC now stores the exact bounded response
text atomically with its digest receipt. Only the private service role can read this
immutable handoff; the source role cannot retrieve historical bodies or use the old
hash-only settlement RPC. Recovery reuses the saved canonical bytes and the same
receipt binding, source parser and cache transaction as direct consumption. Lost
stdout therefore needs no redispatch. Actual CLI integration exercises preparation,
source dispatch, discarded output, recovery and atom resolution under the respective
session identities; rollback-only commit probes establish ordering, not durability
or separate-process isolation.

Integration layout found an earlier direct urllib import in the source transport
test. The test now patches `lib.egress`'s existing urllib dependency. The same real
redirect handler/size checks run without sockets; the network-import gate is unchanged.

0085 local integration:958 SQL passes/1 production-only skip;1182 noDB passes/791
skips;84 migrations850 statements;layout43. Actual CLI handoff reaches saved atoms
after lost stdout. Automatic order, refresh and runtime/process/device gates remain
open; this is not backend release or deployment evidence.
