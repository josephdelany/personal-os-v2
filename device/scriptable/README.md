# Voice recording transport — installation and acceptance draft

Joe approved Scriptable as the free transport helper (ADR-0153). No installation,
server activation or device acceptance is claimed. The scripts are ordinary text;
no secret is embedded. Shortcuts still owns microphone use.

## Install after the capture endpoint is activated

1. Install Scriptable from its official App Store listing. No tip/purchase is needed.
2. Copy `PersonalOSQueue.js`, `PersonalOSCapture.js` and `PersonalOSSetup.js` into
   Scriptable as scripts with those names (without the `.js` extension). The queue uses
   `FileManager.local()` documents, never iCloud storage or temporary storage.
3. Run `PersonalOSSetup` manually on the device. It stores one local Keychain
   configuration containing the endpoint and token; the token input is masked.
   Setup sends no request. The endpoint must
   be the reviewed `https://<worker>.<account>.workers.dev/capture` URL. The token is
   the device bearer token, never a Supabase key. Do not paste either into chat or
   source control. No configured endpoint means the helper retains the queue.

## Voice Shortcut actions

1. Current Date → retain the original capture time as an ISO8601 string with timezone.
2. Record Audio → audio only; no PWA recording.
3. Save File → a persistent **On My iPhone** folder before calling any transport.
   Use a unique filename, no overwrite. Retain this source even after sending;
   media deletion/retention is not decided by this implementation.
4. Get Details of Media → duration in seconds from the recorded file. Do not estimate
   it from file size. This implementation expects the native audio/mp4 recording.
5. Dictionary → `captured_at` (original ISO time), `kind` (`food`, `note`, or
   `workout`), `duration_s` (positive number from step4).
6. Scriptable **Run Script** → `PersonalOSCapture`; Parameter = dictionary;
   Files = the saved recording. Do not pass the recording as a text/base64 field.
   Scriptable documents Files input and warns that large files may require Run in
   App; the intended in-Shortcut path needs a real maximum-size acceptance run.
7. A success notification is allowed only for output status `acknowledged`.
   `queued` and `unconfirmed` are not success. Do not add an error dialog for
   network failure. Never delete the source file based on a transport exception.

## Replay automation

An hourly Shortcut calls the same script with Parameter dictionary `replay: true`
and no Files. Configure its time-based personal automation on the device and verify
that it runs while locked. It iterates pending JSONL files in UUIDv7 order, catches
individual failures, and removes only matching raw-acknowledged queue entries.
An acknowledged manifest and its media remain locally retained. There is no shared
queue-file rewrite that can drop a concurrently captured recording.

## Required physical acceptance

Record once offline: original file, manifest, media copy and pending line must exist;
no error dialog. Restore connectivity: the same ID/bytes must arrive once, with a
committed raw receipt. Repeat with response loss, upload-only/wrong-ID replies,
a trickling response past ten seconds, device lock and interrupted execution.
Check that the helper returns to Shortcuts within the required deadline; Node's
race test proves queue safety, not iOS cancellation or extension lifetime. Scriptable's
native timeout is an idle timeout, so the separate timer is essential.

Record a real food capture and inspect immutable transcript, verified extraction,
atoms and provenance once the runtime is connected. This installation draft does
not close that end-to-end gate, replace the signed Shortcut deliverable, or claim
an installed hourly automation.
