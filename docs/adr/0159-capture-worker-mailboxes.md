# ADR-0159 — Durable capture handoff between isolated workers

Status: local implementation and targeted tests; integration, activation and
physical observation remain open. Continues ADR-0020/0158 and M3-B16 gates2/4.

Private preparation, model dispatch and reference dispatch must run under separate
OS identities with independently supplied secrets. A scheduler must never collect
the three roles' credentials. Each role is independently invocable; local files
carry only the prepared request or bound control metadata between them. Committed
SQL remains the authority for provider responses, processing history and atoms.

Each mailbox is pre-provisioned with one owner writer, an intended reader group,
and no world access or group write. The implementation refuses unsafe final paths,
symlinks, special files and noncanonical content. Requests are immutable UUID files
published with a flushed temporary file and create-if-absent hard link. Identical
publication is idempotent; reuse with different bytes refuses. Result projections
are atomically replaced and include the complete prepared request's SHA256.
Directories and ancestors are operator-provisioned; runtime does not broaden access.
No additional package, network destination or recurring charge is introduced.

Private preparation commits before publication. Private retirement requires a
matching saved attempt payload and outcome, followed by a confirmed commit before
unlinking the transient request. Commit ambiguity leaves files intact. Lost file
publication can be reconstructed through the saved attempt. Lost result stdout
recovers from SQL. Budget-refusal metadata uses the existing append-only failure
owner; saved SQL receipts outrank that metadata. Unknown control cannot invent a
provider success. Historical response bodies remain private SQL data.

The reference supervisor shares the tested process-lifetime implementation with
the model supervisor. Only a newly committed reservation acknowledges ownership.
After the owned child stops, migration0088's reference-only wrapper invokes the
existing reconciliation owner, preserving results and uncertainty/cooldown rules.
Supervisor/host loss without ownership proof remains unresolved; timeout alone
does not authorize redispatch of an issued reservation.

Outbound polling locks its own state directory, persists its role-bound cursor
before dispatch and processes at most ten requests. A crash advances the scan but
retains the request for a later wrap. SQL reservation identity prevents replay.
Private polling uses the existing fixed-cutoff SQL queue, one capture per tick,
and independent regular/nightly cursors under one state lock. Regular passes do
not authorize new retries. A retry sweep completes once per UTC operational day;
this is scheduling state, not a measurement-day definition. Failed entries advance
the cursor and preserve an incomplete sweep status. A crash before saving a private
cursor may revisit work; immutable attempt/result identities provide idempotency.

Deployment must provide bounded service invocations, continuous regular polling,
nightly sweep invocation through all pages, protected directories, separate OS
identities, and secret injection. Mac sleep/offline time is not solved by a cursor.
Queue/result retention and disk capacity need operational limits before release.
Local same-user tests do not prove deployed permissions, independent SQL commit
survival, simultaneous process behavior or a real voice/provider path. No production
deployment or new production-write authorization is implied by this decision.
