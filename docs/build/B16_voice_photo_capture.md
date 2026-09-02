# B16 — Voice and photo capture: transcription, extractive extraction, the neuron budget (migration 0054)

**What this is.** `specs/02-capture-nutrition/requirements.md` §A.2 (the Shortcuts →
endpoint contract for audio/photo), §A.5/A.6 (offline, downstream failure), §B
(transcription on Cloudflare Workers AI with the daily neuron budget), §C (extraction:
names and quantities only, three-way provenance, time resolution, vision), §F (capture
budget, prompting, compliance instrumentation without gamification). Today only typed
text reaches the file. After this, Joe says "I ate a Big Mac" or photographs the meal.
Two sessions. $0: Cloudflare Workers AI free tier (10,000 neurons/day), Supabase Storage
free tier (1 GB) for the media.

**Requirement IDs satisfied:** REQ-CAP-001..111 in §A, §B, §C, §F (quote every ID at
session start; the ones already satisfied by the text path — the endpoint, idempotency,
immutability — are re-verified, not rebuilt). **ADRs:** ADR-0063 (media path: Storage
bucket + Edge Function `capture-media` + Workers AI), ADR-0064 (extraction is extractive
via JSON-schema-constrained Workers AI with a regex verifier; Scenario 9 is the proof).

## Architecture (do not redesign)
1. **Shortcuts** "Log Voice" / "Log Photo" (generators in `tools/`): record/take →
   upload the file to Supabase Storage bucket `captures` (private; upload via a
   short-lived signed URL obtained from Edge Function `capture-media` step 1) →
   call `ingest_capture` with `p_source='shortcut_voice'|'shortcut_photo'` and payload
   `{kind:'food'|'note'|'workout', media_path, duration_s?, checkin_date}` **first**
   (REQ-CAP-011: the row exists before any AI call), UUIDv7 from the device.
2. **Edge Function `capture-media`** (Deno, free): triggered by a DB webhook on
   `raw_captures` insert where `payload->>'media_path'` is set. Checks the neuron ledger
   (REQ-CAP-035..042: 9,000 soft ceiling, 10,000 hard cap, `deferred_budget` status,
   oldest-first reprocessing), calls Workers AI `@cf/openai/whisper-large-v3-turbo`
   (REQ-CAP-030; never whisper-tiny) for audio, or the vision model named in REQ-CAP-070
   for photos, writes `transcript` + `model_id` + `prompt_version` on the capture row
   (the only columns the trigger permits to change — verify against 0012's guard and
   ADR it), inserts the `core.neuron_ledger` row with `estimated_neurons` per REQ-CAP-036's
   formula, sets `processing_status`.
3. **Extraction** (the existing hourly `extract_checkins.py` gains a branch): for
   captures with a transcript and `kind='food'|'workout'`, call Workers AI
   `@cf/meta/llama-3.1-8b-instruct` with `response_format: json_schema` (REQ-CAP-050)
   for **names and quantities only** (§C.1 contract; schema: `items:[{label, quantity?,
   unit?, evidence_span}]`), then the **verifier**: every `label` and `quantity` must
   appear verbatim (case-insensitive) in the transcript, else the item is dropped and a
   `render_violations(reason='invented_item')` row is written (Scenario 9). Three-way
   provenance §C.2: `provenance='extracted'` + `evidence_span` for verified items,
   `'defaulted'` for spec-defaulted quantities, never `'inferred'` from this path. Time
   resolution §C.3 from spoken time words ("at 2", "this morning") with
   `time_precision` set accordingly, else capture time with `'minute'`.
4. **Offline / failure** (§A.5/A.6): the Shortcut keeps the file locally and retries
   with the same UUID (idempotent); the Edge Function on Workers AI failure sets
   `processing_status='failed'` + `last_error`, and the hourly job retries up to 3×;
   the PWA (L6) shows deferred/failed counts (REQ-CAP-044).
5. **Prompting** (§F.2): one daily prompt, RULE-27 — an iOS Shortcut automation at a
   Joe-chosen time that shows the count of days without a night check-in and opens the
   check-in; no streaks, no flames (§F.3, RULE-24). Compliance instrumentation = the
   coverage badges already on SOURCES plus `analysis.capture_compliance (day, kind, n)`
   for RELIABILITY.

## Migration `migrations/0054_media_capture.sql`
`core.neuron_ledger (id, at, capture_id, model_id, call_kind, estimated_neurons, actual_neurons?, run_id)`;
`processing_status` CHECK gains `'deferred_budget'`; `capture_source` enum already has
the media values; a `config.models (purpose, model_id, prompt_version)` table so the
model ids live in one place; `analysis.capture_compliance`. Storage bucket policy:
no public access; uploads only via signed URL; the service role reads.

## Tests — Gherkin scenarios as tests (§H)
```
test_SCENARIO_1_big_mac_spoken_happy_path          (fixture transcript; extraction → verifier → atoms → B12 resolution)
test_SCENARIO_2_big_mac_photographed_no_words      (vision description fixture)
test_SCENARIO_5_voice_note_at_2am_time_resolution_and_subject_day
test_SCENARIO_6_offline_capture_same_uuid_is_idempotent
test_SCENARIO_7_neuron_budget_exhausted_defers_oldest_first
test_SCENARIO_8_transcription_down_marks_failed_never_loses_capture
test_SCENARIO_9_invented_food_is_dropped_and_logged          (the honesty proof; must be in CI)
test_SCENARIO_10_pwa_never_calls_getUserMedia               (grep the Lovable export / app source)
test_SCENARIO_12_prompting_has_no_streaks_and_one_daily_prompt
test_REQ_CAP_030_whisper_large_v3_turbo_only
test_REQ_CAP_036_neuron_estimate_formula
```
Workers AI calls are mocked in tests (recorded fixtures); one `@pytest.mark.live` smoke
runs when `CF_API_TOKEN` is set.

## Joe actions
Create a free Cloudflare account; create an API token with Workers AI read; give it to
CC via `settings.local.json` env and the GitHub/Supabase secrets — never in chat.
Install the two Shortcuts (signed, generated); set the daily prompt automation time.

## Done when
Migration; bucket + Edge Function deployed; both Shortcuts generated and installed;
one real voice capture and one real photo capture land as atoms (counts and the
verified item labels pasted — the labels are Joe's food, fine to paste); Scenario 9 test
green in CI; `neuron_ledger` shows the two calls with estimates; ADR-0063/0064;
PROGRESS + WHAT I DID NOT DO.
