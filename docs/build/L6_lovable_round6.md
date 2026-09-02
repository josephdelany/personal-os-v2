# L6 — Lovable Round 6: THE DESK

**Preconditions:** L5 accepted. No new backend needed: every form here posts to the
existing `ingest_capture` with a payload shape the hourly extractor already understands
(`tools/extract_checkins.py`). Paste as ONE message.

---

ROUND 6 — THE DESK. Where Joe acts. Every form is one `supabase.rpc('ingest_capture',
{p_capture_id: crypto.randomUUID(), p_captured_at: new Date().toISOString(),
p_source: 'pwa_text', p_payload})` and then shows "Recorded {HH:MM}." with the id in
small print. Forms never compute, never validate beyond "is a number in range" (ranges
below), never default a value the user did not enter — an empty field is omitted from
the payload, not sent as 0.

Panels (tabs on phone, bento on desktop): Capture · Correct · Watch · Facts · Settings.

1) CAPTURE — five forms, each a card:
- **Night check-in** → `{kind:'checkin', type:'night', mood, stress, mental_sharpness, energy, day_rating, note?}`;
  five 0–10 integer steppers (no defaults, no pre-selected value), one optional note.
- **Morning check-in** → `{kind:'checkin', type:'morning', restored, energy, mood, mental_clarity, drive, sleep_feel, note?}`.
- **Food / drink** → `{kind:'food', text}` — one free-text line ("big mac, coke"); a
  hint under it: "Comma-separate items. Say the drink and the size."
- **Workout set** → `{kind:'workout', exercise, weight_lb, reps, rpe?}` — exercise text,
  weight number (0–1500), reps integer (0–200), RPE number 0–10 in 0.5 steps; a
  "+ another set" button that keeps `exercise` and clears the rest; each set is its own
  capture.
- **Body** → `{kind:'health', metric:'weight_lb', value}` — one number.
- Under all five: "Or use the Shortcuts on your phone — they land in the same place."
  with deep links `shortcuts://run-shortcut?name=Night%20check-in`, `Log%20Food`,
  `Log%20Workout`.

2) CORRECT — a text form: "What is wrong, and what is right?" → `{kind:'note',
correction:true, text}` with the hint "Corrections are recorded as notes with
provenance; they never edit the original." Below it, the last 20 notes from
`get_day` for today (call `get_day` with no argument), each with its `atom_id` as the
trace.

3) WATCH — reads `get_findings` (L3) and shows only the `watching` list with the clocks,
plus a line "Start a watch from any exploratory card in Findings." (No custom
hypothesis form yet — there is no RPC for it; do not fake one.)

4) FACTS — moved here from L0 unchanged (`get_insights_guarded`).

5) SETTINGS — sign out; theme (dark default); "Data as of {as_of}" from `get_domains`;
a "Shortcuts" list with the three deep links; a "Privacy" paragraph, verbatim: "This app
reads only through owner-locked functions. It never receives a coordinate. Nothing here
is shared with anyone."

Remove the disabled Ask box from THE DESK entirely (it will return when a question
engine exists). Keep Ask out of the nav.

ACCEPTANCE: (a) each form posts exactly the payload shape above (log the payload to the
console in dev and check the keys); (b) an untouched stepper sends no key; (c) every
form shows "Recorded {time}." on success and the raw error message on failure;
(d) no `from('` anywhere; `rpc('ingest_capture'` is the only write.
