# Capture media HTTP contract

Local implementation; not deployed or verified on a device. This Worker has only
write capabilities. It never runs a model or reads private database records.

Configure `CAPTURE_TOKEN`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and
`SUPABASE_MEDIA_UPLOAD_JWT` (role `capture_media_upload`) through Worker secrets.
The combined `/capture` route also requires `SUPABASE_CAPTURE_JWT` (role
`capture_ingest`). Neither role is a service role. The device holds only the
capture bearer token. Never include credentials in generated source or logs.

## Device request

POST binary recording bytes to `/capture`, with these headers:

- `Authorization: Bearer <device capture token>`
- `X-Capture-ID`: the device-generated UUIDv7, retained across retries
- `X-Media-Kind`: `voice` (or `photo`)
- `Content-Type`: actual `audio/*` MIME type (`image/jpeg` or `image/png` for photo)
- `X-Capture-Metadata`: compact JSON with original `captured_at` including timezone,
  `kind` (`food`, `note`, `workout`), `duration_s` for voice, optional `checkin_date`

Persist the recording, identity and metadata locally before attempting the request.
Retry exactly those bytes and metadata with the same identity. Do not substitute a
new recording under an old ID. The server computes the hash from actual bytes.
Photo resizing to 1024 pixels is the device's responsibility and is not proved here.

The handler commits the expected media identity, uploads without replacement,
commits a verified upload receipt, then calls the existing ingestion handler with
`capture_id`, original timestamp, `shortcut_voice`/`shortcut_photo`, and payload
containing kind, duration, optional check-in date, media path and SHA256.

Only HTTP 202 with the matching capture ID, or HTTP 200 with status `duplicate`
and matching ID, confirms raw ingestion. An upload-only success is insufficient.
The explicit `/upload` route supports upload alone and returns 201/200 with a media
receipt; it does not acknowledge a raw capture. All other paths return 404. No result claims enrichment.

A timeout, lost response, 503 or malformed receipt leaves the local entry pending.
A 400 also does not authorize dropping the recording; retain it for correction.
If Storage accepted bytes but its completion response was lost, a private worker
must run hash reconciliation before the same-ID retry can proceed. Never overwrite
an existing object to force a retry through. REQ-CAP-019/020's ten-second silent
queueing and ordered replay still require the actual Shortcut implementation;
this server may complete after the device has timed out.

## Activation gates

Apply draft0081 and the separately approved Storage policies to a private bounded
bucket; provision scoped roles and PostgREST commit override; verify actual Storage
permissions, maximum-size memory/CPU and end-to-end timeout behavior. Generate,
sign/install and exercise the recording/replay Shortcut. Complete the separated
transcription/extraction runtime. These are pending, not implied by HTTP tests.

Local contract test:
`node --test tests/capture_media_http.test.mjs tests/capture_http.test.mjs`
