# "Log Food" Shortcut — iOS setup (~5 minutes)

One tap → type or dictate what you ate/drank → it lands in the spine as an immutable
capture, and the hourly extractor turns each item into a `consume` atom. Text-first
(you approved deferring photos — they'll come with the app or a storage design; a
photo in the database would eat the 500 MB free tier).

Comma-separate multiple items — "big mac, large coke" becomes two items. The system
stores the **names** now; nutrition numbers come later from the Phase-3 USDA path
(never guessed — a logged meal today is a fact with a name, not invented calories).

**Two known limits, named (not hidden):** the split is on commas ONLY — write
"rice and beans, chicken" (one comma = two items), and avoid commas inside numbers
("1000 calorie shake", not "1,000"). And a drink logged here isn't yet classified as
alcohol/caffeine (that's the Phase-3 resolver; OQ-39) — the capture is immutable, so
it re-derives with full alcohol accounting later, nothing lost.

## Build it (Shortcuts app → + → name it "Log Food")

1. **Ask for Input** — Input Type **Text**, prompt: `What did you eat/drink?`
   *(or **Dictate Text** if you prefer voice)*

2. **Format Date** — Date: **Current Date**, format **ISO 8601** (time on).

3. **Get Contents of URL** — tap Show More:
   - **URL:** `https://cykviouklidnbsbgdgdo.supabase.co/rest/v1/rpc/ingest_capture`
   - **Method:** `POST`
   - **Headers** (same three as your other shortcuts):
     | Key | Value |
     |---|---|
     | `apikey` | *(your anon key)* |
     | `Authorization` | `Bearer ` *(space, then anon key)* |
     | `Content-Type` | `application/json` |
   - **Request Body → JSON**, three fields:
     - `p_source` → Text → `shortcut_text`
     - `p_captured_at` → Text → the **Formatted Date** variable
     - `p_payload` → **Dictionary** → two entries:
       - `kind` → Text → `food`
       - `text` → Text → the **Provided Input** (or Dictated Text) variable

4. *(optional)* **Show Notification** → `Logged ✓`

Add to Home Screen / say "Hey Siri, Log Food". This endpoint is **live right now** —
this shortcut works the moment you build it, independent of everything else.

## What happens to it

`raw_captures` (immutable, `kind='food'`) → hourly extractor → one `consume` atom
per item: the verbatim label as evidence, `presence='observed'`, hour-level time
precision, no invented numbers (`REQ-NUT-024` never-guess). When the nutrition
resolution path is built (Phase 3), these same captures re-derive into full
interval-valued nutrition without you re-logging anything.
