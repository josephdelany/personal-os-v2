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
