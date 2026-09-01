# Night Check-in — the robust version (~10 minutes to rebuild)

Your current night check-in is one Dictate Text posted raw. The Edge Function it
already POSTs to accepts five 0–10 scores, a note, **and a food array** — the
robust version just asks for them. Keep the same URL and token; only the questions
and the JSON body change. (Once the check-in bridge is applied, every submission
also lands in the new system automatically — that part needs nothing from the phone.)

## Rebuild "Night Check-in" with these actions

Ask–set pairs, exactly like your morning one (Ask for **Number** → Set variable):

1. **Ask for Number** `Mood (0-10)` → **Set variable** `Mood`
2. **Ask for Number** `Stress (0-10)` → **Set variable** `Stress`
3. **Ask for Number** `Mental sharpness (0-10)` → **Set variable** `Sharpness`
4. **Ask for Number** `Energy (0-10)` → **Set variable** `Energy`
5. **Ask for Number** `Day rating (0-10)` → **Set variable** `DayRating`
6. **Ask for Input (Text)** `Anything to note about today?` → **Set variable** `Note`
   *(or keep your Dictate Text here — dictation is great for the note)*
7. **Ask for Input (Text)** `What did you eat/drink today? (comma-separated, blank if logged already)` → **Set variable** `Food`

8. **Get Contents of URL** — your existing one, URL and headers unchanged
   (`https://cykviouklidnbsbgdgdo.supabase.co/functions/v1/ingest-checkin`, same
   Bearer token). Change the **Request Body → JSON** to:
   - `type` → Text → `night`
   - `mood` → **Number** → `Mood`
   - `stress` → **Number** → `Stress`
   - `mental_sharpness` → **Number** → `Sharpness`
   - `energy` → **Number** → `Energy`
   - `day_rating` → **Number** → `DayRating`
   - `note` → Text → `Note`

   *(Field types matter: the scores must be **Number** fields — the function
   rejects non-integer scores into quarantine rather than storing garbage.)*

9. *(optional)* **Show Notification** → `Night check-in ✓`

**The food answer:** the function's food array wants structured items, which is
clumsy to build in Shortcuts. Simplest robust pattern: after action 7, add a second
**Get Contents of URL** that POSTs the food text to the NEW endpoint exactly like
the "Log Food" shortcut (`docs/FOOD_SHORTCUT.md`, body `kind`=`food`,
`text`=`Food` variable) — wrap it in an **If** (`Food` *has any value*) so a blank
answer skips it. One check-in, both systems fed, food included.

## Why not more questions

RULE-27: no battery over 26 items, one prompt per subject per day, and a check-in
that takes 90 seconds is one you'll still be doing in six months. Five scores + a
note + food is the full instrument the backend supports today; anything more
belongs in the app later.
