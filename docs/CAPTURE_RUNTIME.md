# Capture runtime — implementation and activation checklist

Current local foundation: receipt-backed private progression at5356c09 plus the
0088/ADR0159 worker-mailbox integration draft. Earlier stage notes below document
the individual interfaces; NEXT_SESSION records current evidence and remaining gates.
This is a runbook under construction, not an activated capture service.
Production authentication is held per NEXT_SESSION; do not retry the unchanged secret.

## V0 meal save/history — local implementation, not activated

Migration0092/ADR0167 adds owner-JWT `save_v0_meal(p_request)` and
`get_v0_meals(p_day)`. Save requires exactly `entry_id` (UUIDv7), `supersedes`
(null or current entry UUID), `occurred_at` (timestamp with offset), `text`
(string, maximum10000 characters) and `photo_capture_id` (null or existing UUID).
Nonblank text or a completed photo is required. Reuse the exact request/UUID after
uncertain delivery; changed contents refuse. Corrections append a new version;
stale predecessors require rereading before an owner makes another correction.

A photo must already exist as a Shortcut photo capture with matching upload and
completion receipt. Day readback provides bucket/path/content-type metadata for
that image. After approved activation of `capture_storage_policies.sql`, apply
`v0_meal_photo_policies.sql` transactionally. Download with the owner's authenticated
Storage client into a local object URL; do not make the bucket public or embed a
service credential. Only linked completed photos are readable; owner photo writes
remain denied. Local policy tests are not evidence of live Storage delivery.

Save receipts confirm evidence storage. Day reads show `save_status=saved` and a
separate nutrition object: `pending`, `results_available`, or `removed`. Available
results retain their stored provenance/intervals and are not automatically verified
measurements; a removed item is not a nutrient value. Missing results yield an empty
items list, never zero calories. Correcting a meal does not reuse predecessor
nutrition. Existing voice workers do not automatically process these V0 text/photo
entries; this interface does not claim processing has started. Saving/history and
photo review remain useful independently of enrichment.

Example caller after activation, using the app's existing authenticated Supabase
client (no service credential). Generate and retain a fresh UUIDv7 once for each
new entry; reuse the whole request on retry:

```javascript
const request = {
  entry_id: entryId, supersedes: null,
  occurred_at: new Date().toISOString(),
  text: mealText, photo_capture_id: null
};
const {data: receipt, error} = await supabase.rpc('save_v0_meal', {p_request: request});
if (error) throw error; // Keep request for a visible retry; do not display saved.
const {data: history, error: readError} = await supabase.rpc('get_v0_meals', {
  p_day: receipt.subject_day
});
// receipt.status === 'saved' is durable-save acknowledgement even if readError occurs.
// Nutrition readiness comes from history.entries, never from the save receipt.
```

For a correction, supply a fresh entry UUID and the current entry's UUID as
`supersedes`, with the full replacement text/photo/time. A stale-predecessor error
requires reloading the day and showing the current entry before correcting again.
This example is a caller contract, not evidence of deployed RPC availability.

## V0 structured check-ins — local implementation, not activated

Migration0091/ADR0166 adds owner-JWT-only `save_v0_checkin(p_request)` and
`get_v0_checkins(p_day)`. Provision/deploy the reviewed migration before connecting
a frontend; these names are not claimed live. Nonowner and anonymous access refuse.

Save accepts exactly `entry_id` (client UUIDv7), `supersedes` (null for a new entry,
current predecessor UUID for a correction), `occurred_at` (ISO timestamp with
offset), `period` (`morning`/`evening`), `ratings` and `note` (empty string allowed,
maximum4000 characters). Morning ratings require `sleep_quality` and `energy`;
evening requires `mood` and `energy`. Each must be an integer1–10. Nothing is
pre-filled or inferred. `v0_checkin_v1` is separate from legacy0–10 measurements.

Keep the same complete request and entry UUID until save is acknowledged. Retry
uncertain transport failures with that exact request; changed content under the
same UUID refuses. A stale correction must reload its predecessor before the owner
makes a fresh correction. The receipt returns `status=saved`, entry ID, received
time, personal day and definition version. This confirms a structured saved entry,
not a model result. Do not display success before the RPC transaction succeeds.

Day reads return `entries:[]` for a missing day, never invented zero ratings.
Entries include event/received timestamps, explicit scale/version, predecessor,
period, ratings and note. Current versions use the existing04:00 ET day boundary;
corrections preserve raw evidence. These APIs do not compute clinical meaning or
mix subjective scales. Meal/workout/photo paths are separate V0 obligations.

## Owner corrections — local implementation, not activated

ADR0161/0089 adds `python3 -m tools.capture_correct`. It reads one JSON
request from stdin and prints a private result only after the transaction commits.
Run it in the separately provisioned owner environment: `SUPABASE_DB_URL` must
identify a login with `capture_owner` capability. Do not give that capability to
the private service, model, reference or ingress identities. Actor text is not
authorization. No owner login has been provisioned by this local work.

| Field | Contract |
|---|---|
| `request_id` | New UUID for a new correction; keep the same UUID for an exact retry |
| `capture_id` | Existing immutable capture UUID |
| `expected_item_id` | Current resolved-item UUID returned by capture readback |
| `actor` | `joe` |
| `operation` | `replace`, `remove`, or `retime` (ADR0164/0090, locally verified) |
| `food_id` | Required only for replacement; exact saved reference-cache version UUID |
| `quantity` | Required only for replacement; one positive finite numeric `grams`, `servings` or `item_count` value |

Removal omits both source and quantity; zero does not mean removal. Serving counts
require the pinned reference's serving mass. Item counts use the existing nutrition
owner's household definition. Missing nutrient values are retired explicitly rather
than converted to zero. `retime` requires `occurred_at` as an ISO-8601 timestamp
with explicit offset and `time_precision` (`exact`, `minute`, `hour`, `day`, or
`unknown`), omitting source and quantity. It preserves stored nutrient values and
uses the existing personal-day boundary. Extraction-field editing remains unfinished.

Read the current item before preparing a correction. On a stale-target refusal,
read it again and make a new deliberate correction; do not automatically substitute
the latest item ID into an old request. If success delivery is uncertain, retry the
exact request and UUID. Changed contents under an existing UUID are refused.
The saved outcome identifies both predecessor and replacement item. Capture readback
and current nutrient totals select the replacement; as-of reads preserve the older
answer. Late model results remain unapplied history and can be retired normally.

Production use still requires reviewed migration/login activation and real-data
verification. Local rollback tests and mocked commit failures do not prove host-crash
durability. Keep request/result files private; never publish them in service logs.

## Connected worker invocation packet — not installed

Provision three OS identities: private, model and reference. The service manager
must independently inject each role's allowed environment; a shell that loads all
three secret sets and then filters them is forbidden. Use a fixed reviewed checkout
and Python environment. No credential is written into these commands or a job plist.

The worker interpreter must be Python 3.12 or newer and have
`ops/capture-requirements.txt` installed. Provision its environment before loading
any runtime secrets; use the exact interpreter path in the generated service packet:

```sh
python3 -m venv /capture/venv
/capture/venv/bin/python -m pip install -r ops/capture-requirements.txt
/capture/venv/bin/python -c "import pg8000, pydantic, dateparser, pint; from lib.mass_units import convert_quantity; assert convert_quantity(1, 'kg')['value'] == 1000"
```

These are deployment templates, not executed activation steps. ADR0160 pins Pint
for shared mass/volume conversion; no network request occurs during conversion.
The code checkout and environment must be readable but not writable by worker
identities. Local verification uses `/tmp/personal-os-pint-venv-cf404e6`, outside the
checkout so dependency source files do not enter repository egress scanning. This
is not a deployed environment; the system interpreter does not acquire its dependencies.

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

Reader-group entries describe the intended reader, not a permission to reuse a
role's primary group. Provision dedicated channel groups containing only that
channel's writer and reader. Do not add outbound identities to a general private
data group just to permit file-group assignment. State/log directories stay0700;
each role's secret JSON stays0600 and owned by that role.

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


### Private service deadline — local continuation after b2078cd

`python3 -m tools.capture_private_service` accepts the same polling directory flags
and optional --retry as capture_private_worker. It starts only that fixed child,
passes only private DB/Storage configuration, discards child output and enforces a
120-second wait followed by process-group kill/reap. Its output describes invocation
completion or an unconfirmed result; it never certifies capture completion or SQL
rollback. Missing/foreign/disposable context refuses. Child result inspection stays
in protected private SQL/worker tools; it is not public scheduler output.

Private polling saves the next cursor and an incomplete marker before capture
work. A real SIGKILL filesystem test verifies that a replacement process advances
to the next item. An interrupted final nightly page keeps the daily gate incomplete;
it does not replay earlier retry work that day. A crash before actual capture work
can defer that item until the next pass, with the failed sweep visible. This is
process/filesystem evidence, not independent SQL commit-survival or power-loss proof.
Do not install unattended scheduling until the remaining service invocation bounds
and deployment checks are covered. The wrapper does not solve its
own host loss, deployed OS isolation or provider reservation ownership recovery.


### Transport retention and publication capacity

Private polling checks one request independently of active capture status and
retires it only after matching saved SQL outcome/payload and confirmed commit.
Outbound polling checks one control projection and removes it only after the
private request disappears from the existing channel. Malformed/missing channel
configuration refuses; neither worker deletes raw captures, media or SQL history.

Publication refuses above1024 files or1GiB per directory or below64MiB free-space
reserve (including the new temporary body). Per-file limit remains72MiB. Identical
request publication remains idempotent without allocation. Failures stay visible;
there is no automatic evidence eviction or paid fallback. If disk headroom is too
low for cursor writes, restore space before recovery polling. Validate deployed
capacity monitoring and retention before activation.

### Generated service packet — not installed

`ops/capture_services.py` emits four launchd daemon definitions: private regular,
private nightly, model and reference. Require explicit absolute checkout/Python/
runtime paths and three distinct unprivileged account names. These are daemon
definitions using UserName, not per-user LaunchAgents; installation/provisioning
requires a separately reviewed privileged action. No installation was performed.
The current source packet is `.local/capture-services/`; its four plists pass
`plutil -lint`, which proves syntax only. Example account names in that packet are
unprovisioned targets, not evidence those accounts or permissions exist.

Each60-second tick executes `tools.capture_service_entry` for one role, which
reads only `<runtime-root>/secrets/<role>.json` (nightly uses private.json).
The file must be regular, owned by the executing identity and inaccessible to
group/world, with only that role's allowed environment keys. The launcher refuses
preloaded credentials rather than becoming a parent that holds all roles' secrets.
It replaces itself with a fixed worker using only selected configuration and
PYTHONPATH. Never put secret values in the plist, command line or logs.

Private ticks use the120-second supervisor. Model/reference ticks retain the
existing90-second child plus10-second settlement limits and nonblocking mailbox
locks; filesystem/host failures remain explicit operational limits. Nightly ticks
skip before06:00 UTC (01:00/02:00 New York), then resume their saved sweep each
minute. After the database daily gate closes, later ticks perform no new retry
sweep. This is a scheduling choice, not a measurement-day decision. Host/DB clock
agreement must be checked at deployment. Sleep/offline time can delay a run.

Provision protected readable checkout/Python dependencies, role-owned log
directories, channel groups/directories and secrets through normal configuration
before any install. Verify effective access and negative cross-role reads, apply
authorized migration/runtime revision, then install and observe actual schedule
and capture outcomes. A plist's RunAtLoad=false avoids an explicit load trigger,
but installing an interval service enables subsequent work and is itself activation.
