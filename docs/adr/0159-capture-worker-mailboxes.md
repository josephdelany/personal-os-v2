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

All mailbox writer locks are nonblocking: overlapping ticks refuse and retain
work for a later invocation. Readers can inspect the last atomic publication.
Outbound polling locks its own state directory, persists its role-bound cursor
before dispatch and processes at most ten requests. A crash advances the scan but
retains the request for a later wrap. SQL reservation identity prevents replay.
Private polling uses the existing fixed-cutoff SQL queue, one capture per tick,
and independent regular/nightly cursors under one state lock. Regular passes do
not authorize new retries. A retry sweep completes once per UTC operational day;
this is scheduling state, not a measurement-day definition. Before capture work,
the private cursor advances durably and marks the sweep incomplete. On its final
page the daily gate is also saved before work. A confirmed return restores the
prior failure state or records the new failure. Forced termination therefore cannot
monopolize the first queue item or falsely certify the final nightly page. A crash
between cursor publication and capture work may defer that item until the next
regular wrap/nightly sweep; the interrupted sweep remains explicitly incomplete.
Raw evidence and SQL attempts are retained. Immutable identities make revisits safe.

Private polling also checks one request-file entry per tick using an independent
retirement cursor, including after nightly completion and when the active capture
queue is empty. Saved attempt/outcome and payload hash must match; commit precedes
retirement. This recovers files left behind by a filesystem failure after terminal
SQL progression. Unconsumed requests remain; cleanup failures are incomplete and
do not block active capture progression. No raw row, atom, media or SQL result is
deleted by this maintenance. Each outbound poll checks one control projection
using its own durable cursor and removes it only when its UUID request is absent
from the still-existing private request directory. A present request, including a
symlink, retains the control; missing channel or malformed metadata refuses. This
removes transport copies, not source evidence or authoritative SQL response rows.

Publication limits are1024 files and1GiB per directory,72MiB per file, and64MiB
free-filesystem reserve. Byte accounting includes temporary files and the additional
replacement body before atomic rename. The byte cap permits at most14 maximum-size
request files. These are conservative backlog safety defaults, not measurement
definitions or promised deployment capacity. Identical immutable publication needs
no allocation and remains idempotent at capacity. Exhaustion refuses new writes;
existing files and SQL remain, with no eviction or paid storage fallback. Other
filesystem writers can race the free-space check, so write errors remain failures.
Before publication, the exclusive directory writer may remove one abandoned
`.tmp-UUID` regular file owned by the directory owner. No cooperating writer can
be live under that same lock. Only that temporary name is removed; an already
published hard link remains. This recovers interrupted publication space without
deleting queued requests. A real SIGKILL publication test exercises recovery.
Operators must restore free space if the reserve prevents cursor publication;
automatic cleanup is not claimed to work on a full disk. Raw/media and authoritative
SQL retention remain separate policies.

Deployment must provide bounded service invocations, continuous regular polling,
nightly sweep invocation through all pages, protected directories, separate OS
identities, and secret injection. Mac sleep/offline time is not solved by a cursor.
Queue/result cleanup and publication caps need deployed capacity monitoring and
recovery verification before release.
Local same-user tests do not prove deployed permissions, independent SQL commit
survival, simultaneous process behavior or a real voice/provider path. No production
deployment or new production-write authorization is implied by this decision.

## Local service packet continuation after b2078cd

The private service runs one fixed poll child under a120-second deadline, kills
and reaps its process group on timeout, and reports unconfirmed rather than
claiming SQL rollback. Only private DB/Storage configuration reaches the child.
The role entry point reads one owner-only regular secret JSON, refuses inherited
credentials, then execs the fixed role worker with an explicit environment. No
secret is placed in command arguments, generated plists or diagnostic output.

Four uninstalled launchd daemon definitions cover private regular/nightly, model
and reference ticks. They require three distinct unprivileged account names,
absolute reviewed paths and independently protected secret files. Each ticks at
60 seconds; nightly skips before06:00 UTC, then the saved cursor completes its
once-per-UTC-day sweep. This puts the first eligible tick at01:00/02:00 New York,
without defining measurement days. Host/DB clock agreement is a deployment check.
RunAtLoad=false does not make installation harmless: interval activation still
enables subsequent writes/provider calls and requires applicable authorization.

No paid service or new dependency is added. Daemons require the host to be running;
they do not guarantee a wake from sleep. Dedicated channel groups must contain only
their writer/reader identities, never reuse broad private-data groups. Local plist
syntax and command tests are not deployed account/ACL/secret or schedule evidence.
