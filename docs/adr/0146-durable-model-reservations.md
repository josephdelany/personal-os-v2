# ADR-0146 — Serialized model reservations and a restricted logging capability

Status: local implementation in progress; deployment held. Date: 2026-09-22.
Requirements: REQ-CAP-035..039, RULE-29; extends ADR-0063 and ADR-0020.

The current egress helper logs through its caller's cursor. That is not durable
before dispatch: a later rollback can remove both the shared spend and audit row.
A check and separate insert also permit competing consumers to admit calls against
the same remaining budget. Existing tests inspect uncommitted rows; they do not
prove the documented failure-survival contract.

Migration0077 introduces a single reservation RPC under one transaction lock shared
by all model consumers. READ COMMITTED is required. The UTC clock is sampled after
lock acquisition, so a transaction begun yesterday cannot spend yesterday's budget.
Finite positive estimates are mandatory. Issued and failed calls consume the same
shared neuron ledger; refusals create no claimed outbound call. The 1,000-neuron
margin requires a currently deferred capture with an unresolved deferral from an
earlier UTC day, rather than a caller-supplied privilege flag.

Request UUID and payload digest bind idempotency to a specific request. A duplicate
reservation never permits a second dispatch, even if no result is known. This
conservatively consumes budget when a process dies after reservation but before
sending. The log says reserved until settled; reservation is not proof of delivery.
Settlement cannot change an already observed outcome. No request body is stored in
this audit metadata.

The model_egress role has only the narrow reservation/settlement RPCs, without
private-table reads or owner APIs. It is created with LOGIN but PASSWORD NULL and no memberships;
credential provisioning and live effective ACL audit remain deployment work.
The private reader and result writer must run separately from provider credentials.
No new service or dependency is introduced ($0 recurring).

## Runtime implementation and remaining caller work

`lib.egress.dispatch` owns the dedicated connection transactions. It checks both
session_user and current_user are model_egress (a broad reader using SET ROLE is
refused), commits reservation before sending, and commits settlement separately.
Failed or ambiguous reservation commits cause no send. Duplicate permits refuse
without another request. Expiry is checked using monotonic elapsed time from before
the reservation RPC, conservatively including lock and network wait.

`tools/model_egress.py` accepts a prepared request on stdin and returns a result on
stdout for a private consumer, never a CI log/artifact. It uses only MODEL_EGRESS_DB_URL
and refuses inherited broad database credentials. Runtime secret provisioning and
actual separated orchestration remain unimplemented. The old cursor-based call
refuses real dispatch; its injected fixture transport remains for rollback tests.
Ask therefore retains deterministic fallback until its separated caller is wired.
All consumers must use the same reservation owner before release. SQL fixtures
remain rollback-only; they cannot prove durable commits or competing transactions
(OQ-82). Actual enrichment results must be persisted atomically with effective
processing status by a separate consumer.

REQ-CAP-034 still says to put returned transcript/timings on a raw row. Joe's
approval explicitly covered REQ-CAP-025..027; do not silently extend it to changing
that contract. Prepare an append-only result proposal before wiring transcription.

## Review constraints

Independent review identified UTC rollover between reservation and dispatch. An
allowed receipt now includes server reserved_at and valid_before (next UTC midnight).
The transport must refuse an expired permit and obtain a fresh request identity and
reservation for the new day before dispatch; a commit alone cannot satisfy this.
Network transit and vendor accounting time still require the provider's hard limit;
no local timestamp proves the vendor charged the same day. Runtime deadline handling is implemented and tested for exact expiry. Review also identified that a plan call could attach a deferred
capture ID to spend the margin. Plan calls are now always limited to 9,000; the
future preparer must bind actual capture payload/provenance and call kind.


Independent review also reproduced default HTTP redirect handling forwarding a
fixture Authorization header to a different host. The model transport now installs
a redirect-refusing handler. A real HTTP302 handler-path test fails before the
redirected opener can run; another test checks _post installs it. The existing
static inventory now counts one source urlopen and one model opener.open, retaining
the same two-transport gate. Source API redirect handling remains separate work.

Fifteen dispatcher/CLI tests establish ordering and failure behavior using a connection
probe; 53 disposable SQL/planner regressions passed before the redirect fix. The
full no-DB suite passed 1073 tests/690 skipped, followed by three additional CLI
checks in the 15-test targeted run. Neither
is post-commit durability proof. Final read-only review found no further material
issue in the model path after redirect repair; full integration passed: 857 SQL/1 skipped; 1073 no-DB/690 skipped, followed
by three added CLI checks in the15-case targeted suite; chain76/659; layout43/43.
