# ADR-0158 — Durable model response handoff for capture recovery

Status: implemented and locally integrated for receipt recovery, owned model-worker
timeout and private progression; scheduler/deployment gates remain open.

M3 gate2/4 cannot recover a successful transcription/extraction when model stdout
is lost: the ledger records only a digest and duplicate dispatch is forbidden.
Migration0087 stores the bounded canonical response text atomically with settlement.
The existing model role can publish through one narrow RPC but cannot read historical
bodies; its previous hash-only settlement permission is revoked. Private service
consumers retain original receipt/schema/evidence validation before applying results.
A correlated provider error settles its HTTP status in that same transaction.

The response limit is2MiB, enforced at transport read, dispatch canonicalization and
SQL publication. No new dependency or recurring charge. This adds bounded storage
per model call, not a total retention/storage policy; that remains a release gate.
Bodies can contain private/untrusted provider output and never enter logs or public
evidence. Immutable storage is readable only by the private service and owner.

The private reconcile-model command resumes successful saved transcription/extraction
or records the settled error. Missing reservations mean awaiting dispatch; issued
reservations mean awaiting result, never presumed worker death. Historical digest-only
success is explicitly response_unavailable and cannot be silently redispatched.

Owned stopped-call reconciliation requires dispatcher ownership and termination
proof. The bounded model worker now supplies that proof for its own child. The runtime must use separately
credentialed private/model/reference workers and a credential-free scheduler. A parent
that reads all secrets and filters child environments violates ADR0020. Scheduling,
independent-process durability and real-device/provider verification remain open.

Evidence:87 targeted SQL passed66.95s and17 dispatcher tests passed0.20s.
Independent scoped review found no blocker in atomic body/digest/status publication
or private recovery. The old standalone HTTP-status RPC is also revoked from the
model role, so new status metadata must be published through atomic settlement.
Final integration evidence below supersedes that initial targeted checkpoint.


## Bounded model worker and private progression

`tools/model_worker.py` runs only the fixed model dispatcher in a fresh process
group, with model-only credentials passed through an explicit allowlist. It refuses
private/reference credentials and disposable-test environments before spawning.
The child writes a correlated acknowledgement on an inherited private pipe only
after a NEW reservation commit is confirmed, before HTTP. Duplicate/refused or
uncertain reservation commits never acknowledge ownership.

The supervisor discards provider stdout. At90 seconds it kills its child process
group before reaping; it does not wait on inherited pipe EOF after a timeout.
Only after termination and a matching acknowledgement does it invoke the narrow
model-role reconcile RPC. The RPC preserves any successful settlement or changes
its owned issued call to error without refunding the charge. SQL settlement has a
separate10-second main-thread alarm. An unconfirmed settlement remains unconfirmed.
No elapsed-time observation alone can authorize replay of a reservation.

This does not solve supervisor SIGKILL/host loss before durable completion, independent
process/DB crash durability, or OS secret-file isolation. Deployment must provision
separate worker identities and independently inject secrets. The credential-free
scheduler never loads all credentials and then filters them for children.

`capture_transcription advance CAPTURE_ID [--retry]` is the private progression
entrypoint. It reuses prepared work at the current nullable processing head,
consumes saved model/source receipts, returns the next bounded dispatch action,
and ultimately invokes the existing resolution owner. Missing/issued receipts wait.
Preparing a new retry requires --retry; consuming an already prepared result does
not. A same-UTC-day budget deferral stays held, and extraction quarantine remains
review_required even with --retry. Caller commit precedes action export.

The integration path now has a private state machine and a bounded model worker.
The separate reference worker supervisor, durable scheduler handoff, installed
schedule and real-device/provider proof remain open in the same M3 unit.


Final local evidence at b46846f plus recorded source hashes: runtime SQL30 passed
24.80s; recovery SQL89 passed88.34s; process/dispatch37 passed2.39s; full SQL992
passed/1 production-only skip311.68s; full noDB1214 passed/825 skipped149.70s;
chain86 migrations877 statements; staged layout43. Ledger14/15 unchanged; existing
F006 noDB diagnostic and generic RULE04 pending status remain. All handles terminal
and disposable servers stopped. Archive `.local/evidence/capture-runtime/`.

Review and tests repaired disposable-marker stripping, NULL-head duplicate work,
quarantine routing, and retry gating that had blocked consumption of already saved
results. Independent scoped review accepted the repairs. No production or physical
capture evidence is inferred from these checks.
