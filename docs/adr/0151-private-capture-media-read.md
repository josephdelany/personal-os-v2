# ADR-0151 — Hash-bound private capture media reads

Status: locally verified foundation; upload and runtime activation open.
Date: 2026-09-22. REQ-CAP-006/009/011/012/034; ADR0020/0148/0150.

Private preparation reads media from the same authoritative Supabase store as the
capture, through lib/db.py. It holds only private read capabilities, not Cloudflare
credentials. The isolated model process now also refuses SUPABASE_STORAGE_READ_JWT,
so adding Storage access does not silently give the provider process private reads.
No new service, dependency or paid capability is introduced.

The new prepare-media CLI stage reads the immutable capture's media_path and
media_sha256. The path must be capture UUID plus one filename; it cannot select a
URL, bucket, different capture, query, traversal or local file. The fixed private
captures bucket is read from the configured HTTPS *.supabase.co origin using an
explicit Storage read JWT and anon API key. Response redirects are refused before
credentials can follow them. Reads have a30-second socket-operation timeout and50MiB in-memory bound.
The dedicated POSIX main-thread CLI additionally arms a45-second SIGALRM timer
around configuration, connection, body acquisition and digest verification. It refuses
an already armed timer and restores the previous handler on every exit. This interrupts
a slow-drip blocking Python read; it is not a hard process kill for every possible
native-library stall. A supervising runtime still needs process-level timeout/recovery.
These are operational refusal limits, not permission to drop a capture or delete media.

Returned bytes must match the immutable SHA256. Only then are they encoded into the
fixed transcription payload and bound to the saved attempt by its existing digest.
The private caller commits before exporting that request to the separate dispatcher.
The hash protects against unnoticed Storage replacement; it does not prove device
provenance or make Storage objects immutable by itself.

[Supabase's private download contract](https://supabase.com/docs/guides/storage/management/download-objects)
and [bucket access rules](https://supabase.com/docs/guides/storage/buckets/fundamentals)
were checked September22. The authenticated-object endpoint keeps downloads subject
to Storage authorization. The [Cloudflare transcription guide](https://developers.cloudflare.com/workers-ai/guides/tutorials/build-a-workers-ai-whisper-with-chunking/)
documents base64 audio input. Actual credentials, live Storage policies and provider
acceptance remain deployment evidence, not consequences of these local tests.

## Required remaining work

Upload issuance, append-only upload receipt/hash creation, Storage bucket policies,
Shortcut payload generation and media retention remain unimplemented. Capture payloads
without the required binding refuse explicitly; recovery for existing unbound media
must be resolved through trusted append-only evidence, never raw-row updates. Do not
claim media recovery complete just because new strict requests can be prepared.

The prepared-payload helper remains an internal stage primitive; the actual media
runner must use prepare-media. Extraction/atoms and separated nightly orchestration
remain required, as do interruption recovery and observed real voice/photo paths.
No production or external media request has run. Pure transport tests substitute the
opener; SQL tests substitute download and roll back all fixture data.

## Local verification

16 transport tests passed0.18s;17 disposable SQL preparation/consumption cases passed
8.86s;43 layout checks passed. Independent review accepted path/hash/redirect and
credential boundaries, and identified the socket-vs-total-deadline distinction above.
The follow-up deadline regression interrupts an actual5-second blocking fixture read
after30ms and checks handler restoration; a second regression preserves an already
armed timer.18 pure tests now pass0.23s. Independent review accepted this POSIX
implementation with the native-stall distinction above. Full integration passed:1111 noDB/721 skipped (189.42s),888 SQL/1 skipped
(249.52s),43 layout checks.79-migration/719-statement chain evidence is reused from
936f5cd: no migration changed, verified by Git. No live access.
