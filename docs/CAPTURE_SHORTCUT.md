# Capture Shortcut — iOS setup (your ~10 minutes)

The database is live and waiting. This Shortcut is the one piece that has to live on
your phone. It sends a text note straight into `raw_captures` through the write-only
`ingest_capture` function (ADR-0034) — nothing else can be touched with it.

## First: two values from your Supabase dashboard

Open your project → **Settings → API**. You'll see, together on one page:

- **Project URL** — looks like `https://abcdefghijklmnop.supabase.co`
- **`anon` `public` key** — a long string beginning `eyJ...`

That anon key is a *write-only* credential here (it can only append a capture), so it's
safe to keep in the Shortcut on your phone. It never comes to me and never goes in the
repo.

## Build the Shortcut (Shortcuts app → + → new shortcut, name it "Log")

Add these actions in order:

1. **Dictate Text** *(for voice)* or **Ask for Input → Text** *(for typing)*.
   → this becomes the variable **Dictated Text** / **Provided Input**. Call it **Note**.

2. **Format Date**
   - Date: **Current Date**
   - Format: **ISO 8601** (make sure "Include Time" is on).
   → variable **Formatted Date**.

3. **Get Contents of URL**
   - **URL:** `https://<YOUR-PROJECT-REF>.supabase.co/rest/v1/rpc/ingest_capture`
     (paste your Project URL and add `/rest/v1/rpc/ingest_capture`)
   - **Method:** `POST`
   - **Headers** (tap "Add new header" three times):
     - `apikey` → *(your anon key)*
     - `Authorization` → `Bearer ` *(space, then your anon key)*
     - `Content-Type` → `application/json`
   - **Request Body:** choose **JSON**, then add these fields:
     - `p_source` → **Text** → `shortcut_text`
     - `p_captured_at` → **Text** → insert the **Formatted Date** variable
     - `p_payload` → **Dictionary** → one entry: key `text` → value = the **Note** variable

4. *(optional)* **Show Notification** → `Logged ✓`

That's it. Tap the Shortcut, speak or type a sentence, done. Add it to your Home Screen
or the Share Sheet so it's one tap. On iOS you can also say *"Hey Siri, Log"*.

## The exact payload it sends (for reference)

```json
POST https://<ref>.supabase.co/rest/v1/rpc/ingest_capture
apikey: <anon key>
Authorization: Bearer <anon key>
Content-Type: application/json

{
  "p_source": "shortcut_text",
  "p_captured_at": "2026-08-31T18:40:00Z",
  "p_payload": { "text": "ate a big mac, felt tired after" }
}
```

The function refuses any `p_source` other than `shortcut_voice|shortcut_photo|shortcut_text|pwa_text`,
requires a payload, stamps `trust_level='trusted'` and `recorded_at` server-side, and
returns the new capture's id. A voice version is identical with `p_source` = `shortcut_voice`.

## Prove it worked

Tap it once with any throwaway sentence. That first real capture is the end-to-end
proof (I can't fabricate one — RULE-01). Then tell me, and I'll verify the row landed in
`raw_captures` and read it back to you. From there, every tap is captured, unattended,
forever — no subscription required.

## What's next (I build, once captures are flowing)

- The `raw_captures → atoms` transform (extraction), which can run any time later against
  the immutable captures — even after the subscription ends.
- A one-tap workout logger and a nightly note, same pattern, different `p_payload`.
