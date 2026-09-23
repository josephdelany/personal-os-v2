# ADR-0153 — Local Scriptable transport for Shortcut-owned capture

Status: approved by Joe 2026-09-22; implementation/device verification in progress.
Requirements: REQ-CAP-003/006/008/009/018–021; RULE-28/29/30.

Joe approved the free Scriptable helper while Shortcuts continues to record audio.
Scriptable handles local persistence, UUIDv7 identity, catchable HTTP failure and
replay to the existing /capture endpoint. It never records media, calls a model,
reads Supabase directly or holds a service credential.

Cost before dependency introduction: the official App Store listing is free;
optional in-app purchases are tips, never required or invoked. This is local code,
not a paid hosted tier, subscription or metered service. Projected use is one local
save per capture and one request per queued retry; local capacity is bounded by
available device storage. A storage failure refuses sending and retains the source
recording. No paid overage or automatic purchase is possible in this helper.
https://apps.apple.com/us/app/scriptable/id1405459188

Use FileManager.local, not iCloud: recordings and queue metadata stay on device.
Use an explicitly configured HTTPS Cloudflare capture endpoint and local Keychain
token. Redirects are refused. No telemetry, log of payloads, model call or new
personal-data destination is added. Shortcuts must first retain the source file.

Scriptable documents request timeoutInterval as an IDLE timeout, not a total
deadline. Therefore use a separate ten-second timer around dispatch and ignore late
acknowledgements; the pending entry survives and same-ID replay reconciles it.
Returning promptly to Shortcuts despite a pending native request is a DEVICE gate,
not something Node tests can prove. No claim of cancellation or hard process kill.
https://docs.scriptable.app/request/
https://docs.scriptable.app/args/
https://docs.scriptable.app/filemanager/

Store each capture as a separate immutable one-line JSON queue file plus its media;
this avoids concurrent read/modify/write of a shared queue losing a newer capture.
Replay pending files in their sorted capture-ID order and each file's line order.
A matching 202 or duplicate200 writes an acknowledgement marker before removing the
pending file. Retain the original manifest and media; acknowledgement is not a
media-retention/deletion policy. Uncertain writes/receipts remain recoverable.

This implementation decision does not close the full device requirements. Signed
Shortcuts, physical offline/locked-device runs, timing, file sharing, available
storage and hourly automation must be exercised before activation is accepted.
