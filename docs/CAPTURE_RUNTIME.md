# Capture runtime — implementation and activation checklist

Current local foundation: receipt-backed private progression at5356c09 plus the
0088/ADR0159 worker-mailbox integration draft. Earlier stage notes below document
the individual interfaces; NEXT_SESSION records current evidence and remaining gates.
This is a runbook under construction, not an activated capture service.
Production authentication is held per NEXT_SESSION; do not retry the unchanged secret.

## Connected worker invocation packet — not installed

Provision three OS identities: private, model and reference. The service manager
must independently inject each role's allowed environment; a shell that loads all
three secret sets and then filters them is forbidden. Use a fixed reviewed checkout
and Python environment. No credential is written into these commands or a job plist.

Provision separate directories beneath an operator-selected protected root:

| Directory | Owner/writer | Reader group |
|---|---|---|
| model-outbox | private | model |
| model-results | model | private |
| reference-outbox | private | reference |
| reference-results | reference | private |
| private-state | private | private only |
| model-state | model | model only |
| reference-state | reference | reference only |

Mailboxes require owner write, intended reader access, no group write and no world
access; state directories are0700. Protect all ancestor paths. Verify access using
the actual identities, including denial of other roles' secrets and private data.
The writer must belong to each channel's reader group: publication explicitly sets
that group and refuses if it cannot do so. Same-user local tests do not prove the
deployed permission boundary; do not treat this draft as an activated packet.

Run each command only within its independently provisioned role environment. The
paths below are deployment path templates, not claims that directories exist:

```sh
python3 -m tools.capture_private_worker --state-directory /capture/private-state --model-outbox /capture/model-outbox --model-results /capture/model-results --reference-outbox /capture/reference-outbox
python3 -m tools.capture_dispatch_mailbox model /capture/model-outbox /capture/model-results --state-directory /capture/model-state
python3 -m tools.capture_dispatch_mailbox reference /capture/reference-outbox /capture/reference-results --state-directory /capture/reference-state
```

Each private invocation handles one queue item; schedule repeated regular ticks.
Each outbound invocation defaults to one request, with --limit bounded at10.
For the nightly lane, invoke the private command with --retry repeatedly until
sweep_complete is true. Its separate cursor holds the insertion cutoff across ticks
and prevents another completed retry sweep during the same UTC operational day.
Regular ticks continue without --retry and consume already dispatched results.
Nonzero exit/incomplete must remain a failure in job monitoring; an empty/finished
scan is not evidence of a provider result or observation freshness.

Before activation, supply bounded service invocations, a nightly trigger that
continues all pages, actual OS identities/secret injection, disk-capacity handling,
and deployed revision/migration verification. Private DB connection/lock stalls and
supervisor/host loss still need operational handling. Do not install a job whose
timeout silently discards an issued reservation or whose success hides incomplete
captures. Physical voice/photo, independent commit-survival and observed schedule
acceptance remain separate release gates.

## Process capabilities

| Process | Required capability | Must not inherit |
|---|---|---|
| Private preparation/consumption | Direct private DB login; fixed Supabase Storage origin and anon API key; Storage read JWT restricted to private captures | CF_API_TOKEN, MODEL_EGRESS_DB_URL |
| Model dispatcher | Direct model_egress DB login; Cloudflare account/token | SUPABASE_DB_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STORAGE_READ_JWT |
| Future supervisor | Validated stage messages and scheduling state | A combined private/model credential environment |

The supervisor must not solve process separation by holding every secret itself.
Provision separately scoped workers and validate effective role/Storage permissions
before activation. Environment guards are tested local refusal mechanisms, not proof
of an OS sandbox or deployed permission boundary. No generic SQL reaches the model.

## Stages already implemented

`workers/capture-media` exposes `/capture` for a binary recording and immutable
device metadata. It hashes bytes, records expected identity, uploads without
replacement, records completion, and invokes the existing raw ingress handler.
Only a committed raw receipt produces202 or duplicate200. `/upload` is explicitly
media-only; other paths return404. [The Worker contract](../workers/capture-media/README.md)
specifies headers, retries and acknowledgement matching. No route is deployed.

An ambiguous Storage success is recoverable through
`tools.capture_transcription reconcile-media CAPTURE_ID`: private acquisition
verifies the saved expected hash/size and appends a completion receipt. Retry the
same device request afterwards. This command does not overwrite or delete media.
The device must retain its original file and metadata until raw acknowledgement;
a local Scriptable queue/replay implementation now exists under `device/scriptable/`
(ADR0153, approved by Joe), but signed Shortcuts and physical silence/deadline
acceptance remain open.

`tools.capture_transcription prepare-media REQUEST_ID CAPTURE_ID` reads the immutable
voice capture reference and digest, downloads only its private captures object and
builds the fixed transcription payload. It commits the attempt before emitting JSON.
The capture path is UUID/filename. Missing hash refuses; never modify a raw row to add it.
The internal `prepare` primitive accepts already prepared JSON and is not the media
source-authentication boundary; the media runner must use `prepare-media`.

`tools.model_egress` consumes one prepared JSON request on stdin in its isolated
process. It commits the shared reservation before sending, then commits a response
receipt or bounded HTTP failure metadata. Do not publish stdout/stderr as CI artifacts:
success data is private; error output exposes only controlled codes/status.

`tools.capture_transcription consume` accepts the correlated response, verifies its
settled receipt and stores the immutable transcript/status together. `fail` records
budget/provider failures, including matched HTTP status. `readback CAPTURE_ID` returns
current processing state and usable transcript. A transcribed capture still needs
extraction; it is not enriched or a stored atom merely because the transcript exists.

`queue` returns items and a next_cursor. Continue every page, even when older items
fail. Preserve the cursor only after its page's outcomes are handled. A new run begins
without a cursor; retries must not loop forever over page1. Pagination does not claim
work or solve concurrent workers; durable run/attempt supervision remains to be built.

## Deadlines and recovery

Private media retrieval rejects redirects, limits reads to50MiB and checks SHA256.
The socket timeout is30s; a dedicated POSIX main-thread45s signal timer also surrounds
the acquisition and hash check. Pre-existing signal timers cause a fail-closed refusal.
The original handler is restored. Non-POSIX/non-main-thread callers refuse.

This is not a hard process-kill guarantee for every native-library stall. The future
supervisor must terminate/reap stalled stage processes under an overall deadline,
retain a stable request identity, and reconcile uncertain commits before deciding the
next action. Never treat a lost acknowledgement as proof that a write rolled back.

## Required before activation

- Activate and verify the implemented authenticated upload/receipt route and
  private bucket policy artifact with replacement refusal. Provision scoped credentials via
  normal secrets configuration; no secret belongs in chat, source or a Shortcut.
- Generate/install the Shortcut media payload path, including upload reference/hash.
  Reconcile existing unbound media using trusted append-only evidence. Do not declare
  old captures unrecoverable just because strict preparation refuses missing hashes.
- Connect validated extraction to atomic atom persistence and nutrition resolution.
  Complete dictated-text and photo paths and their required scenarios.
- Implement the separate worker supervisor, durable per-run work tracking, timeout
  recovery and observed nightly schedule. Counts-only maintenance is not enrichment.
- Complete approved production migration/ACL checks, real voice/photo replay,
  post-commit readback, freshness/withheld-feed evidence and authorized cutover.

Media retention/deletion and reserved measurement decisions remain Joe's. No uploads,
provider calls, deletion, production migration or deployment were performed to create
this document or the associated local tests.


## Device source packet

Build the source-only installation bundle with
`python3 tools/package_capture_device.py --out .local/device/PersonalOSCapture.zip`.
It contains the queue, capture entrypoint, manual on-device setup and instructions,
plus a hash manifest. Setup stores endpoint/token together in local Keychain without
sending a request. This is not a signed Shortcut or evidence of installation.

The device queue is now exercised through the actual combined Worker in a local
contract test, with backend HTTP substituted. Pending removal follows raw202 or
matching duplicate200, not an upload receipt. The recording and manifest remain.
See `device/scriptable/README.md` for the physical timeout/lock/offline acceptance
packet. Missing device observations remain open while the private extraction and
runtime connection proceed. Production verification still requires the refreshed
normal DB secret; Joe was reminded at this activation boundary.


## Reference dispatch connection — local draft0084 / ADR0155

`PYTHONPATH=. python3 tools/reference_egress.py` reads one bounded JSON request on
stdin and returns `{request_id,result}` only after a committed digest receipt.
Request keys are exactly request_id,source,query,brand,barcode. Sources are
usda_foundation/usda_branded/off_search/off_product; product requests carry only a
barcode, name requests carry a query and optional brand. No arbitrary URL or nutrient
value is accepted. The private saved-request producer and cache consumer are still
required; manually assembling this envelope does not establish capture provenance.

The process requires REFERENCE_EGRESS_DB_URL authenticating directly as
reference_egress, plus USDA_FDC_API_KEY/PERSONAL_OS_USDA_API_KEY or the OFF contact
configuration for its source. It refuses private/model credentials, including
SUPABASE_DB_URL, service/Storage keys, MODEL_EGRESS_DB_URL and CF_API_TOKEN. Conversely
private capture stages refuse reference credentials. Migration0083 creates a NOLOGIN
role; no live login or secret has been provisioned by this implementation.

0084 reuses0072's rate events/cooldowns, charges a durable reservation, and stores an
immutable response-digest receipt. The reference reservation is the committed
pre-send audit; existing adapters add a per-HTTP detail audit at settlement. Quotas
include permit lifetime to account for delayed sends. A session lock serializes
reservation through settlement so a recorded429 gates the next dispatch. A process
crash releases the lock; an outstanding reservation remains charged and must not be
resent with the same identity. Source cache publication must verify both digests.

HTTPS, no redirects and2MiB responses are locally enforced. The socket timeout does
not replace the supervisor's total process deadline. Separate-session behavior,
uncertain commit recovery, TTL refresh, complete source-order fidelity and scheduling
remain acceptance work. Nothing here authorizes production provisioning or proves
an actual originating-API request or device capture.


Interrupted reference reservations are reconciled under that same session lock:
missing results become immutable uncertain outcomes with no fabricated hash/status.
USDA then waits a full hour from discovery, since the lost response may have been429.
A denied reservation commits that maintenance; late results cannot replace it.
This recovery policy is locally tested, but independent-process kill/connection-loss
acceptance has not yet been exercised. It is not an observed unattended recovery.
