# 02 — CAPTURE & NUTRITION RESOLUTION — REQUIREMENTS (EARS)

**Status:** COMPLETE — 154 requirements, 12 acceptance scenarios. Ready for review by Joe.
**Blocking:** the UNRESOLVED QUESTIONS in each section are decisions for Joe — Claude Code must ASK,
not decide. What is still undecided, and what it blocks, is tracked canonically in
`docs/OPEN_QUESTIONS.md`; this header does not restate it. (E-Q1 was resolved 2026-08-15 — see OQ-05.)
**Scope:** the "Big Mac vertical slice". Joe says or photographs *"I ate a Big Mac from McDonald's"*
and the system stores honest, interval-valued nutrition with full provenance.
**Grammar:** EARS (Mavin & Wilkinson). Five patterns only. SHALL is binding. SHOULD is not used
anywhere in this document.
**ID scheme:** `REQ-CAP-nnn` (capture ingress, transcription, extraction, prompting),
`REQ-NUT-nnn` (food resolution, interval nutrition).

---

## 0. SYSTEM ACTORS

Named systems used in the SHALL statements below. Each name refers to exactly one deployable thing,
so that every requirement has one owner.

| Name in requirements | What it is |
|---|---|
| **the capture Shortcut** | An iOS Shortcuts automation on Joe's iPhone. Owns all media capture (camera, microphone). |
| **the ingest endpoint** | A Cloudflare Worker. The only public write surface. Bearer-token authenticated. |
| **the transcription service** | The ingest endpoint's call path to Cloudflare Workers AI `@cf/openai/whisper-large-v3-turbo`. |
| **the extraction service** | The ingest endpoint's call path to a Workers AI text/vision LLM under JSON Schema `response_format`. |
| **the resolution job** | The nightly Python job in GitHub Actions. Owns time resolution, food lookup, interval computation. |
| **the nutrition resolver** | The component of the resolution job that maps a food name + quantity to nutrients. |
| **the PWA** | The installed home-screen web app. Reads everything; writes long-form text only. |
| **the review list** | The batched low-confidence queue shown inside the evening reflection screen. |

**Governing split, from which most of Section A follows:** iOS Shortcuts captures; the PWA displays
and writes long-form text. This is forced by a still-unfixed WebKit limitation — in standalone (home-screen) PWA
mode, `getUserMedia` permission grants are **not persisted**, so every reload and every reopen
re-prompts "allow for this website". Joe has stated that confirmation taps and permission prompts are
design failures, not acceptable costs. Native Shortcuts permissions are granted permanently.

---

## A. CAPTURE INGRESS

### A.1 Ownership of media capture

**REQ-CAP-001** (Ubiquitous) The PWA SHALL NOT call `navigator.mediaDevices.getUserMedia` in any
code path.

**REQ-CAP-002** (Ubiquitous) The PWA SHALL NOT call `webkitSpeechRecognition` or the WebSpeech API
in any code path.

**REQ-CAP-003** (Ubiquitous) The capture Shortcut SHALL be the origin of every audio and every image
byte that reaches `raw_captures`.

**REQ-CAP-004** (Optional feature) WHERE a still image must be acquired from inside the PWA, the PWA
SHALL acquire it using `<input type="file" accept="image/*" capture="environment">` and SHALL NOT
acquire it by any other mechanism.

**REQ-CAP-005** (Ubiquitous) The PWA SHALL accept written input only into the morning check-in
fields and the evening reflection field, and SHALL write every other row as a read-only rendering of
data captured elsewhere.

### A.2 The Shortcuts → endpoint contract

**REQ-CAP-006** (Ubiquitous) The capture Shortcut SHALL include in every request body the fields
`capture_id` (UUIDv7 generated on device), `captured_at` (ISO-8601 with timezone offset, read from
the device clock at the moment of capture), `source` (one of `shortcut_voice`, `shortcut_photo`,
`shortcut_text`, `pwa_text`), and `payload` (the text, and/or a reference to the uploaded media
part).

**REQ-CAP-007** (Unwanted behaviour) IF a request to the ingest endpoint is missing `capture_id` or
`captured_at`, THEN the ingest endpoint SHALL return HTTP 400, SHALL write a row to
`ingest_rejections` with the raw body and reason `missing_identity_fields`, and SHALL NOT create a
`raw_captures` row.

**REQ-CAP-008** (Unwanted behaviour) IF a request to the ingest endpoint carries an absent or
non-matching bearer token, THEN the ingest endpoint SHALL return HTTP 401 and SHALL NOT read the
request body.

**REQ-CAP-009** (Ubiquitous) The capture Shortcut SHALL NOT contain the Supabase `service_role` key.

**REQ-CAP-010** (Ubiquitous) The capture Shortcut SHALL resize every image to a longest edge of 1024
pixels before upload.

**REQ-CAP-011** (Event-driven) WHEN the ingest endpoint receives an authenticated, well-formed
request, the ingest endpoint SHALL insert a `raw_captures` row **before** issuing any Workers AI
call, and SHALL return HTTP 202 with the `capture_id` once that insert commits.

**REQ-CAP-110** (Optional feature) WHERE a capture carries `source = 'location'` (the
`capture_source` enum member reserved by ADR-0008, migration 0004), the ingest endpoint SHALL write
the coordinate payload to `raw_captures` and SHALL route it to the restricted coordinate store whose
access is separated from any egress-capable session (RULE-29, ADR-0020), and no coordinate and no
home location SHALL reach any export, log line, commit, or model prompt. (Ratified 2026-08-24;
requirements-audit Missing-D — the worksheet's `shortcut_location` was corrected to the actual
reserved enum member `location` by the C-5 reviewer. Pairs with REQ-CAP-106: the PWA never requests
a location permission; the coordinate path arrives via the Shortcut.)

**REQ-CAP-111** (Event-driven) WHEN a capture states that a loggable behaviour did **not** occur
(e.g. "I did not drink today"), the extraction service SHALL record it as an `observed_absent`
presence for that subject, distinct from `unknown` (RULE-07), and SHALL NOT collapse a logged absence
into the same zero as an un-logged day. (Ratified 2026-08-24; requirements-audit Missing-D. This is
the capture origin the three-valued presence state previously lacked.)

### A.3 Immutability of `raw_captures`

**REQ-CAP-012** (Ubiquitous) The `raw_captures` table SHALL be append-only: the database SHALL deny
`UPDATE` and `DELETE` on `raw_captures.payload`, `raw_captures.captured_at`, `raw_captures.source`
and `raw_captures.capture_id` to every role used by the ingest endpoint, the resolution job and the
PWA.

**REQ-CAP-013** (Ubiquitous) The system SHALL retain every transcript text in `raw_captures`
indefinitely, and SHALL treat every extracted, resolved and derived row as a recomputable view over
it.

**REQ-CAP-014** (Event-driven) WHEN Joe corrects an extracted or resolved value, the system SHALL
write a new row that supersedes the prior row and SHALL NOT modify the `raw_captures` row it derives
from.

**REQ-CAP-015** (Ubiquitous) The system SHALL record `model_id` and `prompt_version` on every row
produced by the extraction service.

### A.4 Idempotency and dedupe

**REQ-CAP-016** (Event-driven) WHEN the ingest endpoint inserts into `raw_captures`, the ingest
endpoint SHALL use `ON CONFLICT (capture_id) DO NOTHING`.

**REQ-CAP-017** (Event-driven) WHEN an insert is suppressed by the `capture_id` conflict clause, the
ingest endpoint SHALL return HTTP 200 with body `{"status":"duplicate","capture_id":<id>}` and SHALL
NOT enqueue a second enrichment job for that `capture_id`.

**REQ-CAP-018** (Ubiquitous) The ingest endpoint SHALL derive `capture_id` from the client payload
only, and SHALL NOT generate a `capture_id` server-side.

### A.5 Offline

**REQ-CAP-019** (Unwanted behaviour) IF the capture Shortcut's `Get Contents of URL` action returns
a network error or does not complete within 10 seconds, THEN the capture Shortcut SHALL append the
full payload as one JSON line to a local queue file in the Files app and SHALL exit without
displaying an error dialog.

**REQ-CAP-020** (Event-driven) WHEN the hourly replay automation runs, the replay Shortcut SHALL
POST each queued line to the ingest endpoint in file order and SHALL remove a line from the queue
file only after receiving HTTP 202 or HTTP 200 for that line.

**REQ-CAP-021** (Ubiquitous) The system SHALL treat `captured_at` as the event time for every
capture and SHALL treat `received_at` (set server-side) as metadata only.

**REQ-CAP-022** (Ubiquitous) No query, rollup or chart in the system SHALL bucket a capture by
`received_at`.

**REQ-CAP-023** (Ubiquitous) The PWA SHALL persist the evening reflection draft to IndexedDB on a
1-second debounce after each keystroke, SHALL POST the partial draft every 30 seconds, and SHALL
retain the local copy until the server acknowledges the POST.

**REQ-CAP-024** (State-driven) WHILE the PWA holds one or more unsynced local writes, the PWA SHALL
display a persistent indicator stating the exact count of unsynced entries.

### A.6 Downstream service failure

**REQ-CAP-025** (Unwanted behaviour) IF the transcription service or the extraction service returns
any non-2xx status, THEN the ingest endpoint SHALL set `raw_captures.processing_status =
'pending_enrichment'`, SHALL write the provider error code to `raw_captures.last_error`, and SHALL
still return HTTP 202 to the capture Shortcut.

**REQ-CAP-026** (State-driven) WHILE a `raw_captures` row has `processing_status =
'pending_enrichment'`, the resolution job SHALL re-attempt enrichment on each nightly run.

**REQ-CAP-027** (Unwanted behaviour) IF a `raw_captures` row has been in `processing_status =
'pending_enrichment'` for more than 72 hours, THEN the resolution job SHALL add it to the review
list with reason `enrichment_stalled`.

**REQ-CAP-028** (Ubiquitous) The system SHALL implement transcription behind a single provider
function whose implementation is selected by one environment variable, so that the provider can be
changed without editing call sites.

**REQ-CAP-029** (Unwanted behaviour) IF the nightly resolution job has not completed successfully
within the last 48 hours, THEN the system SHALL send one Web Push notification stating the hours
elapsed since the last successful run.

### A.NON-GOALS

- Building a native iOS app. `SFSpeechRecognizer` with `requiresOnDeviceRecognition` is the only way
  to *guarantee* on-device speech, and it needs an Apple Developer account at $99/yr, which violates
  the $0-recurring constraint.
- Background Sync / Periodic Background Sync in the PWA. Safari supports neither; the pattern does not
  exist on this platform and no amount of service-worker code creates it.
- CRDTs or conflict resolution. One user, one phone, append-only log. `ON CONFLICT DO NOTHING` is the
  whole of conflict handling.
- Guaranteeing zero taps forever. iOS 18.2 was reported to re-introduce confirmation prompts on
  automations previously set to Run Immediately. The design must survive a missed automation, not
  assume one cannot happen.

### A.ALTERNATIVES CONSIDERED

- **PWA `getUserMedia` with a strict no-reload SPA.** Rejected. It reduces the re-prompt rate but does
  not eliminate it; the underlying WebKit defect (non-persistent media grants for home-screen PWAs —
  no authoritative ticket cited, as the previously-named 215884 was a misattribution and is resolved) is
  treated as unfixed. Joe's constraint is *zero* prompts, not *fewer*.
- **Removing `apple-mobile-web-app-capable`** so the app runs in Safari chrome, which does fix
  permission persistence. Rejected: it forfeits Web Push and the ITP 7-day storage exemption. Bad
  trade.
- **Direct Supabase PostgREST insert from the Shortcut with the `anon` key + RLS.** Viable, one fewer
  moving part. Rejected as primary because it puts schema knowledge inside a Shortcut (schema changes
  then require editing shortcuts on the phone) and gives the phone direct DB access. The Worker keeps
  one revocable secret with zero database privileges on the device.
- **Server-generated capture IDs.** Rejected: makes offline replay non-idempotent, which is precisely
  the failure the local queue file exists to prevent.

### A.UNRESOLVED QUESTIONS

- **A-Q1.** What is the retention period for the audio blob and the meal photo after successful
  extraction? Research says delete the audio and keep only text as the honest privacy mitigation, and
  notes 1GB Supabase storage ≈ 6,600 downscaled photos ≈ 4.5 years, but gives no chosen number. Joe
  must state a retention period in days for audio and in months for photos.
- **A-Q2.** Which iOS build is on Joe's phone, and does "Notify When Run" appear as a toggle on it?
  Zero-tap operation cannot be promised until this is verified on the actual device.
- **A-Q3.** Is the personal day boundary 04:00, as the research suggests, or a different hour? This
  determines which day a 02:00 voice note is filed under and cannot be decided without Joe.
- **A-Q4.** Does Joe want the camera-roll backstop (an automation that uploads photos from a "Meals"
  album for meals he forgot to log), given it uploads images he did not explicitly log?

---

## B. TRANSCRIPTION AND THE NEURON BUDGET

Cloudflare Workers AI gives 10,000 neurons/day free to every account.
`@cf/openai/whisper-large-v3-turbo` costs **46.63 neurons per audio-minute** — about 214 audio-minutes
per day. Joe's realistic volume is 5–15 min/day. The budget is not the binding constraint; the
*hard-fail behaviour* is the design-relevant fact: on the free plan, exceeding the daily cap makes
further operations **fail with an error**. Cloudflare does not silently bill. That property is a
feature and is exploited below as the cost guarantee, not worked around.

### B.1 Model and parameters

**REQ-CAP-030** (Ubiquitous) The transcription service SHALL call model ID
`@cf/openai/whisper-large-v3-turbo` and SHALL NOT call `@cf/openai/whisper-tiny-en`.

**REQ-CAP-031** (Ubiquitous) The transcription service SHALL send `language: "en"` on every request.

**REQ-CAP-032** (Ubiquitous) The transcription service SHALL send `vad_filter: true` on every
request.

**REQ-CAP-033** (Ubiquitous) The transcription service SHALL send `condition_on_previous_text:
false` on every request.

**REQ-CAP-034** (Ubiquitous) The transcription service SHALL store the returned transcript text and
the returned segment timing data on the `raw_captures` row.

### B.2 The daily neuron budget

**REQ-CAP-035** (Ubiquitous) The system SHALL maintain a `neuron_ledger` table with one row per
Workers AI call recording `capture_id`, `model_id`, `call_kind`, `estimated_neurons` and
`called_at`.

**REQ-CAP-036** (Ubiquitous) The system SHALL compute audio-minute cost as `duration_seconds / 60 ×
46.63` neurons and SHALL write that value to `neuron_ledger.estimated_neurons` for every
transcription call.

**REQ-CAP-037** (Event-driven) WHEN the ingest endpoint is about to issue any Workers AI call, the
ingest endpoint SHALL sum `estimated_neurons` over the current UTC day and SHALL proceed only if
that sum plus the estimated cost of the pending call is less than or equal to 9,000.

**REQ-CAP-038** (State-driven) WHILE the current UTC day's summed `estimated_neurons` is greater
than 9,000, the ingest endpoint SHALL set `processing_status = 'deferred_budget'` on each newly
received capture and SHALL NOT issue a Workers AI call for it.

**REQ-CAP-039** (Ubiquitous) The system SHALL reserve the 1,000-neuron margin between the 9,000 soft
ceiling and the 10,000 hard cap exclusively for re-processing `deferred_budget` captures, and SHALL
NOT spend it on newly arrived captures.

**REQ-CAP-040** (Event-driven) WHEN a new UTC day begins, the resolution job SHALL process
`deferred_budget` captures in ascending `captured_at` order before processing any capture received
that day.

### B.3 Refusal, not silent loss

**REQ-CAP-041** (Unwanted behaviour) IF Workers AI returns an error indicating the daily neuron
allowance is exhausted, THEN the ingest endpoint SHALL set `processing_status = 'deferred_budget'`,
SHALL write `last_error = 'neuron_cap'`, and SHALL NOT delete, truncate or overwrite the audio or
text payload.

**REQ-CAP-042** (Ubiquitous) The system SHALL NOT enable Workers AI paid usage, SHALL NOT attach a
payment method to the Workers AI account, and SHALL treat the hard-fail at 10,000 neurons/day as the
enforcement mechanism for the $0-recurring constraint.

**REQ-CAP-043** (Ubiquitous) The system SHALL NOT drop, discard or mark-as-complete any capture
whose transcription did not succeed.

**REQ-CAP-044** (State-driven) WHILE one or more captures are in `processing_status =
'deferred_budget'`, the PWA SHALL display the exact count of deferred captures and the reason
`waiting for tomorrow's AI budget`.

**REQ-CAP-045** (Unwanted behaviour) IF the transcription service returns an empty transcript for a
capture whose audio duration is greater than 2 seconds, THEN the system SHALL set `processing_status
= 'pending_enrichment'`, SHALL write `last_error = 'empty_transcript'`, and SHALL add the capture to
the review list.

**REQ-CAP-046** (Optional feature) WHERE the capture Shortcut used the native `Dictate Text` action
rather than `Record Audio`, the ingest endpoint SHALL store the supplied text as the transcript,
SHALL set `transcript_source = 'ios_dictation'`, and SHALL NOT issue a transcription call.

### B.NON-GOALS

- Running whisper.cpp or faster-whisper inside GitHub Actions as the normal path. A 20–60 second cold
  start plus a 1.5GB weight download per note is slow, and at 10–20 notes/day it exceeds the 2,000
  free Actions minutes/month outright. It stays available only as a disaster-recovery re-transcription
  path if Cloudflare changes its free tier.
- Deepgram and AssemblyAI. Both run on finite signup credits ($200 one-time for Deepgram), which is a
  time bomb rather than a free tier under a "$0 recurring forever" constraint.
- Chasing the last 1.8 points of WER. Whisper large-v3 is 7.44% average WER on the Open ASR
  Leaderboard vs 5.63% for the best model available; the downstream extraction is robust to a wrong
  word and the transcript is retained for audit anyway.

### B.ALTERNATIVES CONSIDERED

- **Groq's free Whisper tier.** Genuinely free and indefinitely renewing, and materially faster.
  Recorded as the documented *fallback* provider behind REQ-CAP-028, not the primary: its terms have
  changed repeatedly, it adds a second vendor and a second privacy surface, and it is outside the
  chosen stack.
- **`whisper-tiny-en` to conserve neurons.** Rejected explicitly. Tiny runs roughly 3–5× the WER of
  large on hard audio, and the neuron budget is not the binding constraint — the system uses ~28% of
  the daily allocation with self-consistency passes included. Paying accuracy for headroom we do not
  need is a bad trade.
- **iOS `Dictate Text` as the sole path.** Free, instant, and no audio leaves the phone. Kept as a
  first-class variant (REQ-CAP-046) rather than the only path, because Apple does not expose a
  force-on-device toggle to Shortcuts and dictation is materially worse on brand names, numbers and
  noisy environments — which is exactly the food-logging case.

### B.UNRESOLVED QUESTIONS

- **B-Q1.** Is 9,000 the right soft ceiling, or should the reserve for deferred work be larger? The
  research gives the 10,000 hard cap and a ~2,760/day worked estimate but no chosen reserve figure.
- **B-Q2.** Should the default meal-capture path be Variant A (`Dictate Text`, private, lower
  accuracy) or Variant B (`Record Audio` → Whisper, accurate, audio leaves the device)? The research
  recommends building both and defaults to A; this is a privacy-versus-accuracy call only Joe can
  make.
- **B-Q3.** Does Joe want a notification when captures are deferred to the next day's budget, or only
  the passive PWA indicator of REQ-CAP-044?

---

---

## C. EXTRACTION — NAMES AND QUANTITIES ONLY

The governing number: an un-fine-tuned LLM asked to estimate energy from a text-only dietary recall
has a **mean absolute error of 652 kcal**, with Lin's concordance below 0.46. That is roughly a third
of a day's intake, per recall. Fine-tuning fixes it (MAE 171–191 kcal, CCC > 0.89) and fine-tuning is
not available at $0. The design consequence is absolute and structural: **the model never sees the
word "calorie".** It reads names and stated quantities; deterministic Python does the arithmetic.

### C.1 The extractive-only contract

**REQ-CAP-050** (Ubiquitous) The extraction service SHALL request output under a JSON Schema via the
Workers AI `response_format` parameter on every call.

**REQ-CAP-051** (Ubiquitous) The extraction service's **food-item extraction profile** output schema
SHALL contain, per food item, exactly the fields `name`, `evidence`, `evidence_start`, `quantity`,
`quantity_unit`, `quantity_evidence`, and `quantity_evidence_start`. (This is the food profile of the
per-subject dispatch in REQ-CAP-108; the extractive-only contract of REQ-CAP-052/053/056 binds every
profile, not only this one.)

**REQ-CAP-052** (Ubiquitous) The extraction service's output schema SHALL NOT contain any field
whose name or description refers to calories, kilocalories, energy, grams of macronutrient, protein,
carbohydrate, fat, or fibre.

**REQ-CAP-053** (Event-driven) WHEN the extraction service returns an item, the resolution job SHALL
assert `transcript[evidence_start : evidence_start + len(evidence)] == evidence`.

**REQ-CAP-054** (Unwanted behaviour) IF the span assertion of REQ-CAP-053 fails for a field, THEN
the resolution job SHALL discard that field's value, SHALL write `provenance = 'inferred'` with
`value = NULL` for it, and SHALL record reason `span_mismatch`.

**REQ-CAP-055** (Unwanted behaviour) IF the extraction service returns a response that fails
Pydantic validation against the schema, THEN the resolution job SHALL retry the call at most twice
and, if all attempts fail, SHALL set `processing_status = 'extraction_quarantined'` and add the
capture to the review list.

**REQ-CAP-056** (Unwanted behaviour) IF any numeric value denominated in calories, kilocalories, or
grams of a macronutrient appears anywhere in an extraction service response, THEN the resolution job
SHALL discard that value at the adapter boundary before any row is written, and SHALL NOT store it
at reduced confidence.

**REQ-CAP-108** (Event-driven) WHEN the extraction service processes a capture, it SHALL select
exactly one extraction profile by the capture's detected subject from the closed set `food`,
`workout`, `drink`, `activity`, `mood`, `note`, and SHALL apply that profile's own closed field
schema (the food profile is REQ-CAP-051); IF no profile matches the detected subject, THEN it SHALL
route the capture to the `note` profile rather than emit an un-profiled extraction. (Ratified
2026-08-24, ADR-0030 context; requirements-audit C-5/Missing-D. This replaces the former single
food-only extraction path that foreclosed capture of workouts, drinks and activities — wants 6/7/9.
The profile set extends only by a requirement edit, never silently — new subjects are a spec change.)

**REQ-CAP-109** (Ubiquitous) The extractive-only contract SHALL bind every extraction profile: for
every profile the span assertion of REQ-CAP-053 and the discard-on-mismatch of REQ-CAP-054 SHALL
hold, and every profile's output schema SHALL contain **only** extraction fields — a `name`, verbatim
`evidence` spans, and a model-stated `quantity` with its `quantity_unit` — and SHALL NOT contain any
field that holds a resolved or derived measure: no gram, calorie, macronutrient, standard-drink count,
ethanol gram, or dollar (RULE-09). Every such measure is produced downstream by deterministic lookup
(REQ-NUT for food; the ADR-0030 ABV→ethanol path for drink), never emitted by the model. REQ-CAP-052
and REQ-CAP-056 remain the food-profile enforcement of this rule; this requirement extends the same
boundary to every non-food profile.

### C.2 Three-way provenance

**REQ-CAP-057** (Ubiquitous) Every extracted field written by the system SHALL carry a `provenance`
column whose value is exactly one of `extracted`, `inferred`, or `defaulted`.

**REQ-CAP-058** (Event-driven) WHEN a field's `evidence` span is present and passes REQ-CAP-053, the
resolution job SHALL set that field's `provenance` to `extracted`.

**REQ-CAP-059** (Event-driven) WHEN a field's value is produced by the model with a null `evidence`
span, the resolution job SHALL set that field's `provenance` to `inferred`.

**REQ-CAP-060** (Event-driven) WHEN a field's value is supplied by a system default table rather
than by the model, the resolution job SHALL set that field's `provenance` to `defaulted`.

**REQ-CAP-061** (Ubiquitous) Every view in the PWA that renders a field SHALL render `inferred` and
`defaulted` fields with a visual treatment distinct from `extracted` fields.

**REQ-CAP-062** (Ubiquitous) Any statistical claim, correlation or trend computed by the system
SHALL exclude fields whose `provenance` is `defaulted`, or SHALL state the count of `defaulted`
fields included alongside the claim.

### C.3 Time resolution

**REQ-CAP-063** (Ubiquitous) The extraction service SHALL emit the verbatim span of any temporal
expression and SHALL NOT emit a timestamp, date, or time-of-day value.

**REQ-CAP-064** (Event-driven) WHEN a temporal expression span is present, the resolution job SHALL
resolve it with `dateparser` using `RELATIVE_BASE` set to the capture's `captured_at` and
`PREFER_DATES_FROM: 'past'`.

**REQ-CAP-065** (Unwanted behaviour) IF `dateparser` fails to resolve a temporal expression span,
THEN the resolution job SHALL set the event time to `captured_at`, SHALL set that field's
`provenance` to `defaulted`, and SHALL set its `time_precision` to `unknown`, so the fallback is never
read downstream as a measured instant. (Reworded 2026-08-24, requirements-audit C-11 / RULE-06: a
`dateparser`-failure fallback to `captured_at` is a *system default* (REQ-CAP-060), so `defaulted` is
the correct provenance — and it is exactly the value REQ-CAP-062 already excludes from statistics (or
requires a stated count for). The C-11 fix is the added `time_precision='unknown'`, which flags the
substituted instant as imprecise so no consumer reads it as measured; the C-11 reviewer corrected an
earlier draft that mislabelled it `inferred`, which REQ-CAP-062 does *not* filter — that would have
weakened the guard, not strengthened it.)

**REQ-CAP-066** (Ubiquitous) The resolution job SHALL attribute a capture whose resolved event time
falls before the configured personal day boundary to the preceding calendar day.

**REQ-CAP-067** (Optional feature) WHERE a capture's `source` is `pwa_text` and it originates from
the evening reflection field, the extraction service SHALL emit a time-of-day bucket from the set
{`morning`, `midday`, `afternoon`, `evening`, `night`} per item and SHALL NOT emit a clock time.

### C.4 Vision extraction

**REQ-CAP-068** (Ubiquitous) The extraction service SHALL request from the vision model only food
item names, per-item confidence, a `portion_cue` string, and a count.

**REQ-CAP-069** (Event-driven) WHEN dictated text and vision output disagree on a food item's
identity or quantity, the resolution job SHALL take the dictated value and SHALL record the
discarded vision value in `extraction_conflicts`.

**REQ-CAP-070** (Optional feature) WHERE the selected vision model does not accept
`response_format`, the extraction service SHALL call the vision model for a prose description and
SHALL pass that description to a text model under JSON Schema to obtain structure.

**REQ-CAP-071** (Ubiquitous) The system SHALL pin every Workers AI model ID in configuration and
SHALL fail the nightly run with a non-zero exit code if a configured model ID is no longer present
in the catalog.

**REQ-CAP-072** (Optional feature) WHERE a capture contains one or more food items, the extraction
service SHALL run extraction twice at temperature 0.7 and SHALL mark any field whose value differs
between the two runs with `consistency_flag = false`.

### C.NON-GOALS

- Asking the LLM for a confidence score. Self-reported LLM confidence is poorly calibrated and close
  to useless; evidence-span presence is the confidence signal (REQ-CAP-057 through REQ-CAP-060).
- Exotic JSON Schema. Framework schema coverage falls apart on nested `oneOf`, regex patterns and
  `$ref` chains; the schema stays flat.
- SUTime, HeidelTime or Duckling for time resolution. SUTime has the best measured accuracy (F1 0.92
  on TempEval-2 vs HeidelTime's 0.86) but requires a JVM, which is awkward in Workers and heavy in
  Actions; Duckling needs a Haskell service, contradicting "$0 and no servers".
- Confirming anything at capture time. Capture is fire-and-forget; every uncertainty waits for the
  evening review list.

### C.ALTERNATIVES CONSIDERED

- **True constrained decoding (Outlines, XGrammar, GBNF).** Structural validity becomes a mathematical
  guarantee rather than a probability, and the literature reports it *improving* task performance by
  up to 4% while speeding generation ~50%. Unavailable on hosted Workers AI, which offers JSON Mode
  only and explicitly states it "can't guarantee that the model responds according to the requested
  JSON Schema" — hence the mandatory Pydantic validate-and-retry of REQ-CAP-055.
- **Letting the LLM produce grams for vague phrases** ("a handful", "a big bowl"). Rejected: neither
  quantulum3 nor Pint handles food vernacular, and the dominant variance in portion size is *between
  people*, not between meals — so a personal portion table beats any model estimate within about a
  month.
- **A closed food taxonomy enumerated into the vision prompt** (from the prior nutrition spec).
  Constraining a VLM to a closed taxonomy moved one model's worst subtask from 20.3% to 64%. Deferred
  rather than rejected — it is a strong idea, but it requires a seeded 150–300 item list that does not
  exist yet, and it is recorded as D-Q4.

### C.UNRESOLVED QUESTIONS

- **C-Q1.** Does Joe want self-consistency double-passes (REQ-CAP-072) on all food captures, or only
  on captures with no dictated text? It costs 2–3× neurons on those calls; the budget allows it, but
  it is his call whether the extra confidence is worth it.
- **C-Q2.** What visual treatment distinguishes `extracted` from `inferred` from `defaulted`
  (REQ-CAP-061)? This is a design decision with real consequences for whether the distinction is
  actually noticed, and it belongs to Joe, not to the agent.
- **C-Q3.** Should a `consistency_flag = false` field automatically enter the review list, or only be
  marked?

---

---

## D. FOOD RESOLUTION

**Design constraint stated by Joe, and binding on everything below:** the system does **not** mirror
the world's food databases and does **not** scrape every restaurant menu. It looks things up when
needed and caches what he actually eats. This is not a compromise forced by the free tier — it is
strictly better: smaller, faster, current, and legally clean. People eat a startlingly small number of
distinct foods; most individuals' diets are dominated by ~100–200 recurring items, so the cache
plateaus at a few hundred rows and the expected steady-state hit rate exceeds 90% after about six
weeks.

USDA FoodData Central is free, **CC0 1.0 public domain** (so caching carries no legal obligation), and
rate-limited at **1,000 requests/hour per IP** against a realistic load of 10–20 lookups/day.

### D.1 Cache-first resolution order

**REQ-NUT-001** (Ubiquitous) The nutrition resolver SHALL attempt resolution of a food name in
exactly this order and SHALL stop at the first success: (1) `food_aliases` exact match, (2) barcode
lookup against Open Food Facts if a barcode is present, (3) USDA FDC search restricted to
FNDDS/Survey and Foundation data types, (4) USDA FDC search restricted to the Branded data type, (5)
Open Food Facts text search, (6) unresolved.

**REQ-NUT-002** (Event-driven) WHEN a `food_aliases` exact match is found, the nutrition resolver
SHALL read nutrients from `foods_cache` and SHALL NOT issue any network request.

**REQ-NUT-003** (Event-driven) WHEN a food is resolved from any network source, the nutrition
resolver SHALL insert a `foods_cache` row containing `canonical_name`, `source`, `source_id`,
`per_100g_nutrients` and `fetched_at`.

**REQ-NUT-004** (Event-driven) WHEN a food is resolved from any network source, the nutrition
resolver SHALL insert a `food_aliases` row mapping the spoken phrase as uttered to the resolved
`canonical_name`.

**REQ-NUT-005** (Ubiquitous) The nutrition resolver SHALL store the USDA `fdcId` on every row
resolved from USDA FDC, so that the provenance of the number is auditable to a specific database
record.

**REQ-NUT-006** (Ubiquitous) The system SHALL NOT download, import or mirror the full USDA FoodData
Central database or the full Open Food Facts database.

**REQ-NUT-007** (Ubiquitous) The system SHALL NOT scrape, crawl or bulk-import restaurant menu data
from any source.

**REQ-NUT-008** (Ubiquitous) The nutrition resolver SHALL treat `foods_cache` entries sourced from
Foundation Foods and SR Legacy as non-expiring, and SHALL re-fetch entries sourced from Branded or
Open Food Facts when `fetched_at` is more than 365 days old.

### D.2 Rate limits and source etiquette

**REQ-NUT-009** (State-driven) WHILE the count of USDA FDC requests issued in the trailing 60
minutes is greater than or equal to 900, the nutrition resolver SHALL defer further USDA requests to
the next nightly run.

**REQ-NUT-010** (Ubiquitous) The nutrition resolver SHALL send a `User-Agent` header in the format
`PersonalOS/<version> (<contact email>)` on every Open Food Facts request.

**REQ-NUT-011** (Ubiquitous) The nutrition resolver SHALL issue no more than 10 Open Food Facts
search requests per minute and no more than 15 Open Food Facts product-read requests per minute.

**REQ-NUT-012** (Unwanted behaviour) IF USDA FDC returns HTTP 429, THEN the nutrition resolver SHALL
stop issuing USDA requests for 60 minutes, SHALL leave the affected items unresolved, and SHALL NOT
substitute a different food's nutrients.

### D.3 Branded and restaurant items

**REQ-NUT-013** (Event-driven) WHEN an extracted food item carries a brand or restaurant token in
its `evidence` span, the nutrition resolver SHALL include that token in the USDA Branded search
query.

**REQ-NUT-014** (Event-driven) WHEN a USDA Branded match is found, the nutrition resolver SHALL set
`estimate_method = 'labelled'` and SHALL record the matched brand owner string.

**REQ-NUT-015** (Unwanted behaviour) IF a restaurant item has no match in any configured source,
THEN the nutrition resolver SHALL set `nutrition_status = 'unresolved'`, SHALL retain the item name
and the restaurant token verbatim, and SHALL add the item to the review list with reason
`no_source_match`.

**REQ-NUT-016** (Ubiquitous) The nutrition resolver SHALL NOT substitute a generic food's nutrients
for a named restaurant item.

**REQ-NUT-017** (Event-driven) WHEN Joe supplies nutrients for an unresolved item through the review
list, the nutrition resolver SHALL write a `foods_cache` row with `source = 'joe'`, SHALL write the
corresponding `food_aliases` row, and SHALL set `nutrition_status = 'resolved'` on the item.

### D.4 Quantity resolution and the personal portion table

**REQ-NUT-018** (Ubiquitous) The system SHALL maintain a `portion_aliases` table keyed on
`(food_class, phrase)` with a `grams` value and a `n_corrections` counter.

**REQ-NUT-019** (Event-driven) WHEN an extracted quantity is expressed in a mass or volume unit, the
nutrition resolver SHALL convert it with Pint and SHALL set the quantity's `provenance` to
`extracted`.

**REQ-NUT-020** (Event-driven) WHEN an extracted quantity is a vernacular phrase, the nutrition
resolver SHALL look the phrase up in `portion_aliases` and SHALL set the quantity's `provenance` to
`defaulted`.

**REQ-NUT-021** (Unwanted behaviour) IF no quantity is stated and no `portion_aliases` entry exists
for the food class, THEN the nutrition resolver SHALL apply the source's own listed serving size,
SHALL set `provenance = 'defaulted'`, and SHALL add the item to the review list with reason
`portion_defaulted`.

**REQ-NUT-022** (Event-driven) WHEN Joe corrects a portion through the review list, the nutrition
resolver SHALL update the matching `portion_aliases` row's `grams` value, SHALL increment
`n_corrections`, and SHALL NOT alter the original capture.

**REQ-NUT-023** (Ubiquitous) The extraction service SHALL NOT emit a gram value for a vernacular
portion phrase.

### D.4a Counts of branded menu items

A counted menu item — *"a Big Mac"*, *"two McMuffins"* — states its quantity as a bare count, not a
mass, a volume, or a vernacular portion phrase, so none of REQ-NUT-019 through REQ-NUT-021 converts
it to grams. The count resolves through the branded label's own per-serving definition, and the case
where that definition is absent is stated so the count is never silently guessed into grams. A
*partial* count — "half a Big Mac", or a vague "most of" — is handled by REQ-NUT-052 and REQ-NUT-053
so that a stated fraction and a vague quantifier are treated differently, not both guessed.

**REQ-NUT-050** (Event-driven) WHEN an extracted quantity is a unitless count of a food resolved from
the USDA Branded data type, the nutrition resolver SHALL multiply the Branded record's per-serving
gram weight by the count to obtain the item's mass, SHALL store the Branded serving definition — its
household-measure string and its per-serving gram weight — on the resolved row, and SHALL set
`estimate_method = 'labelled'` so that the interval width of REQ-NUT-036 governs.

**REQ-NUT-051** (Unwanted behaviour) IF an extracted quantity is a unitless count (whole or
fractional) of a restaurant or branded menu item and no USDA Branded record carrying a per-serving
gram weight is available for it, THEN the nutrition resolver SHALL leave the count unconverted, SHALL
set `nutrition_status = 'unresolved'` for the item, SHALL retain the item name, the brand or
restaurant token, and the count verbatim, and SHALL add the item to the review list with reason
`no_branded_serving`.

**REQ-NUT-052** (Event-driven) WHEN an extracted quantity is a fractional or partial count of a food
resolved from the USDA Branded data type and the Branded record carries a per-serving gram weight — a
stated fraction such as `half` or `0.5`, or the fractional part of a mixed count such as `2.5` — the
nutrition resolver SHALL resolve the whole-number part, if any, under REQ-NUT-050, SHALL multiply the
Branded per-serving values by the fractional part, SHALL store the Branded serving definition and
brand-owner string on the row exactly as REQ-NUT-050 and REQ-NUT-014 require so the label origin
stays auditable by `fdcId`, SHALL set the quantity's `provenance` to `defaulted`, and SHALL set
`estimate_method = 'portion_table'` on the fractional part so that the wider interval of REQ-NUT-037
governs it, because a stated fraction of a serving is an estimated portion, not a measured one.

**REQ-NUT-053** (Unwanted behaviour) IF an extracted quantity of a branded or counted menu item is a
vague or non-numeric quantifier that maps to no explicit fraction — such as `most of` or `a few
bites` — THEN the nutrition resolver SHALL NOT assign it a fraction, SHALL set `nutrition_status =
'unresolved'` for the item, SHALL retain the quantifier phrase verbatim, and SHALL add the item to
the review list with reason `vague_fraction`; the system carries no vague-quantifier-to-fraction
mapping, because inventing one (`most of` = 0.75) would impute a quantity the system never measured,
which RULE-06 forbids.

### D.5 The never-guess rule

**REQ-NUT-024** (Unwanted behaviour) IF a food name resolves against no configured source, THEN the
nutrition resolver SHALL write the item with `nutrition_status = 'unresolved'` and NULL in every
nutrient column.

**REQ-NUT-025** (Ubiquitous) The nutrition resolver SHALL NOT write a nutrient value derived from a
fuzzy, partial, or best-effort-similar food match.

**REQ-NUT-026** (State-driven) WHILE an item has `nutrition_status = 'unresolved'`, every daily
total that includes that item's meal SHALL state the count of unresolved items contributing to it.

**REQ-NUT-027** (Ubiquitous) The system SHALL treat `unresolved` as a normal, non-error outcome and
SHALL NOT display it as a failure state to Joe.

### D.6 Drink resolution — the ABV→ethanol path (alcohol, Missing-B)

*The drink analogue of the food path. The model extracts a drink name and a volume and never an ethanol
gram or a standard-drink count (REQ-CAP-109); a deterministic reference converts them to ethanol grams and
standard drinks (ADR-0030, RULE-09). Ethanol is stored on the `consume` atom's native interval (migration
0005: `value_low`/`value_point`/`value_high` + `estimate_method` + `provenance`), width and provenance
driven by how the inputs were resolved (RULE-06, RULE-08). The abstinence-day side of Missing-B — "I did
not drink" as an `observed_absent` presence — is handled at capture by REQ-CAP-111 (Missing-D); its alcohol
grain rides the capture subject / `metric_key` of the absence, and it is not re-authored here.*

**REQ-NUT-066** (Event-driven) WHEN an extracted `consume` item is an alcoholic drink carrying a name and a
volume, the nutrition resolver SHALL obtain the drink's alcohol-by-volume from a configured reference source
(a static ABV reference or the drink's own label) and SHALL compute ethanol mass deterministically as
`ethanol_grams = volume_ml × (abv_percent / 100) × 0.789`, where 0.789 g/mL is the density of ethanol
(ADR-0030), and SHALL NOT accept an ethanol-gram or standard-drink value emitted by the model (RULE-09,
REQ-CAP-109). WHERE the ABV is read from the drink's own label the resolver SHALL set the atom
`provenance = 'extracted'`; WHERE it is supplied by the reference source for an unlabelled drink the
resolver SHALL set `provenance = 'defaulted'`, because an assumed ABV is a modelled input and not a
measurement (RULE-06).

**REQ-NUT-067** (Ubiquitous) The nutrition resolver SHALL store the resolved `alcohol_ethanol_grams` as an
interval on the `consume` atom's native value columns (`value_low`, `value_point`, `value_high`) carrying an
`estimate_method` — REQ-NUT-032 mandates the `estimate_method` column; the interval width comes from the
resolution method (RULE-08). WHERE the volume is estimated or the ABV is `defaulted` (REQ-NUT-066), the
resolver SHALL make the interval non-degenerate (`value_low < value_high`) so an assumed input can never
masquerade as a measured point (RULE-06); only a labelled volume resolved against a label ABV may narrow
toward a point. Like the keys it is written under (REQ-NUT-068), this store is possible only once the
Missing-B `metric_registry` seed lands, which the `atoms.metric_key` foreign key enforces.

**REQ-NUT-068** (Event-driven) WHEN `alcohol_ethanol_grams` is resolved, the nutrition resolver SHALL derive
`alcohol_standard_drinks = ethanol_grams / g_per_standard_drink` deterministically and SHALL propagate the
interval, where `g_per_standard_drink` is a named provisional placeholder — 14 g (the US NIAAA standard
drink) pending OQ-35, flagged provisional and not silently fixed, held as a reference value revisable to
another jurisdiction's definition (WHO 10 g, UK 8 g) without a code change; and SHALL carry both
`alcohol_ethanol_grams` and `alcohol_standard_drinks` under the `metric_registry` keys REQ-ONT-016 names,
which the `atoms.metric_key` foreign key makes writable only once the Missing-B seed lands.

### D.NON-GOALS

- Mirroring USDA or Open Food Facts locally. The full OFF dump is multi-GB against a 500MB Supabase
  free-tier database, and the on-demand + cache design is smaller, faster and more current regardless
  of storage.
- Making Open Food Facts the canonical store. Its database is ODbL with share-alike obligations
  attaching to redistribution; USDA's CC0 is the clean choice for a canonical cache.
- Covering every food that exists. The cache covers what Joe eats; a taxonomy that tries to cover all
  food covers none of his.
- Barcode scanning from the PWA in this slice. It needs `getUserMedia`, which REQ-CAP-001 forbids;
  if barcodes are wanted, they arrive through a Shortcut.

### D.ALTERNATIVES CONSIDERED

- **Nutritionix / Edamam / other commercial food APIs.** Not evaluated in the research and not free in
  perpetuity; USDA FDC at 1,000 req/hr against a 10–20 lookup/day load is enormous headroom, so no
  case was made for adding a vendor.
- **Pre-seeding the cache with a curated 150–300 item taxonomy** before any real logging. Attractive —
  it removes the cold-start miss rate and enables the closed-taxonomy vision constraint — but it
  requires Joe's input on what he actually eats. Recorded as D-Q4.
- **Letting a near-miss match through at low confidence.** Rejected. A wrong number carrying a
  confidence score still ends up in a chart eventually; a number that never enters the system cannot.

### D.UNRESOLVED QUESTIONS

- **D-Q1.** McDonald's items specifically: a "Big Mac" may match USDA's Branded data type, may match
  an FNDDS survey composite, or may match neither. Which does Joe want preferred when both exist —
  the brand's own label data, or USDA's independently analysed survey composite? The research does not
  decide this and the two can differ materially.
- **D-Q2.** Seed values for `portion_aliases`. The research names the mechanism and gives one
  illustrative figure ("a bowl of cereal" starting at a generic 40g) but no table. Joe must supply
  starting grams for his own common phrases, or accept that everything starts `defaulted` and
  converges over weeks.
- **D-Q3.** How many nutrients are tracked? Energy and the four macros are implied throughout, but
  micronutrients are never enumerated. Do not guess a list.
- **D-Q4.** Does Joe want the closed vision taxonomy (Section C alternatives), and if so will he sit
  for the 150–300 item seeding session?
- **D-Q5.** Should a resolved-then-corrected food overwrite the `foods_cache` row, or create a second
  row scoped to Joe? Affects whether a correction to "his" Big Mac changes the canonical record.

---

---

## E. INTERVAL-VALUED NUTRITION

The evidence that forces this section:

| Method | Published error |
|---|---|
| LLM text-only recall, no fine-tuning | **MAE 652 kcal**, Lin's CCC < 0.46 |
| Frontier vision (GPT-4o, Claude 3.5 Sonnet) on meal photos | **~36% MAPE** on energy; **all models systematically underestimate**, bias slopes −0.23 to −0.50 |
| Workers AI vision models (smaller and weaker) | assume **40–60% MAPE** |
| 2D image portion estimation, review | 15–25% median portion error |
| Depth/LiDAR-augmented portion estimation | 8–12% — unavailable, no free path from LiDAR to a web pipeline |
| Photo-based logging vs written diary (Keenoa RCT) | app 1,693 kcal vs diary 2,006 kcal — **15.6% systematic under-capture** |

Two independent underestimation biases stack in the same direction. A point estimate is therefore not
merely imprecise, it is **directionally misleading**. The interval is not a caveat attached to the
finding; the interval *is* the finding.

### E.1 Storage shape

**REQ-NUT-030** (Ubiquitous) The system SHALL store energy as three columns — `kcal_low`,
`kcal_point`, `kcal_high` — and SHALL NOT provide any column holding energy as a single unqualified
number.

**REQ-NUT-031** (Ubiquitous) The system SHALL store each tracked macronutrient as a `_low`,
`_point`, `_high` triple.

**REQ-NUT-032** (Ubiquitous) Every row carrying a nutrient interval SHALL carry an `estimate_method`
column whose value is exactly one of `weighed`, `labelled`, `portion_table`, `photo_estimate`,
`unresolved`.

**REQ-NUT-033** (Ubiquitous) The system SHALL permit `kcal_low`, `kcal_point` and `kcal_high` to
differ such that `kcal_point − kcal_low` is not equal to `kcal_high − kcal_point`.

**REQ-NUT-034** (Ubiquitous) The system SHALL enforce the database constraint `kcal_low <=
kcal_point <= kcal_high` on every row.

### E.2 Interval width is a function of resolution method

**REQ-NUT-035** (Event-driven) WHEN `estimate_method = 'weighed'`, the nutrition resolver SHALL set
`kcal_low = 0.90 × kcal_point` and `kcal_high = 1.10 × kcal_point` — provisionally equal to the
`labelled` width (REQ-NUT-036) per ADR-0005, because weighing removes portion error but not
composition error, and the composition uncertainty of a weighed generic food is not yet calibrated
and may prove wider than a label's legal tolerance rather than tighter.

**REQ-NUT-036** (Event-driven) WHEN `estimate_method = 'labelled'`, the nutrition resolver SHALL set
`kcal_low = 0.90 × kcal_point` and `kcal_high = 1.10 × kcal_point`.

**REQ-NUT-037** (Event-driven) WHEN `estimate_method = 'portion_table'`, the nutrition resolver
SHALL set `kcal_low = 0.80 × kcal_point` and `kcal_high = 1.20 × kcal_point`.

**REQ-NUT-038** (Event-driven) WHEN `estimate_method = 'photo_estimate'`, the nutrition resolver
SHALL set `kcal_low = 0.75 × kcal_point` and `kcal_high = 1.60 × kcal_point`.

**REQ-NUT-039** (Ubiquitous) The nutrition resolver SHALL apply the asymmetric multipliers of
REQ-NUT-038 in that direction — wider above the point than below — because the documented
photo-estimation bias is systematic underestimation.

**REQ-NUT-040** (Event-driven) WHEN `estimate_method = 'unresolved'`, the nutrition resolver SHALL
write NULL to `kcal_low`, `kcal_point` and `kcal_high`.

**REQ-NUT-041** (Ubiquitous) The nutrition resolver SHALL NOT narrow an interval on the basis of the
vision model's reported per-item confidence.

**REQ-NUT-042** (Event-driven) WHEN a meal's items resolve under more than one `estimate_method`,
the nutrition resolver SHALL set the meal-level `estimate_method` to the widest-interval method
present among its items.

### E.3 Propagation and display

**REQ-NUT-043** (Event-driven) WHEN computing a daily total, the resolution job SHALL sum `kcal_low`
across items to produce the total's low bound and SHALL sum `kcal_high` across items to produce the
total's high bound, and SHALL NOT compute the bounds from the summed point estimates.

**REQ-NUT-044** (Ubiquitous) Every PWA view that displays an energy or macro figure SHALL display
the interval alongside the point value in the form `~<point> kcal (<low>–<high>)`.

**REQ-NUT-045** (Ubiquitous) The PWA SHALL render nutrient values with a visual weight determined by
`estimate_method` and SHALL NOT vary that visual treatment by the magnitude of the value.

**REQ-NUT-046** (Ubiquitous) Any correlation or trend analysis over nutrition data SHALL either
weight observations by inverse interval width or restrict to rows where `estimate_method IN
('weighed','labelled','portion_table')`, and SHALL state which of the two it did.

**REQ-NUT-047** (Unwanted behaviour) IF a daily total's interval width exceeds the deficit or
surplus being reported against it, THEN the system SHALL state in plain words that the day's logging
cannot resolve that difference.

**REQ-NUT-048** (Ubiquitous) The system SHALL NOT display a red/green, over/under, or pass/fail
judgment framing on any nutrient value.

**REQ-NUT-049** (Ubiquitous) The system SHALL NOT round an interval bound in a direction that
narrows the interval.

### E.NON-GOALS

- Correcting the systematic underestimation bias away with a multiplier. The bias is *stable*, and a
  stable bias does not corrupt within-person trends; documenting it in the schema is worth more than
  inventing a correction factor. The prior spec's rule holds: the instrument does not need to be
  accurate, it needs to be the same instrument at both ends.
- LiDAR or depth-augmented portion estimation. It genuinely works (8–12% portion error vs ~20% for 2D)
  and Joe's phone may have the hardware, but there is no free path from LiDAR depth to a web pipeline
  without a native app.
- Buying a better vision model. The ~36% MAPE figure is from frontier models; this is a limitation of
  single-2D-photo information content, not of the free tier. Prompt engineering does not fix it
  (p > 0.05) and multi-angle capture does not fix it (p = 0.182).
- Adaptive TDEE / the Kalman filter. It is the right next lens and its rules survive from the prior
  spec — never label it "your metabolism", never correct it toward a formula, `skip` on fluid steps,
  `inflate` on recomposition windows — but it consumes this section's output and is out of scope here.

### E.ALTERNATIVES CONSIDERED

- **Symmetric ±40% intervals for photo estimates.** Simpler, and rejected: the documented bias is
  directional (slopes −0.23 to −0.50), so a symmetric interval would place the true value outside the
  band more often on the high side. Asymmetry is the whole point.
- **A single `confidence` float instead of `estimate_method` + interval.** Rejected: a scalar
  confidence collapses "how the number was obtained" into "how much we like it", and the first is what
  downstream filtering actually needs.
- **Hiding the interval and showing one clean number.** Named in the research as the single most
  likely way this system quietly fails ("uncertainty laundering"). Also actively protective to avoid:
  precision theatre around ±40% numbers is among the design patterns implicated in disordered eating
  behaviour in app-based self-monitoring.
- **Storing variance rather than bounds.** Cleaner statistically, but Joe cannot read a variance and
  he is the person who has to verify this system. Bounds are legible.

### E.UNRESOLVED QUESTIONS

- **E-Q1 — RESOLVED 2026-08-15 (ADR-0005, OQ-05).** The `weighed` interval was a ±5% placeholder not
  found in the research (which gives ±10% for `labelled`, ±20% for `portion_table`, 0.75×/1.6× for
  `photo_estimate`, and lists `weighed` without a width). Joe's ruling: set it to ±10%, equal to
  `labelled` (REQ-NUT-035), and keep it provisional pending a calibration against a known-label food.
  Rationale: weighing removes portion error but not composition error, so a weighed generic food's
  true width may prove *wider* than a label's legal tolerance, not tighter. `weighed` and `labelled`
  stay distinct `estimate_method` values even while their widths are equal, so calibration can
  separate them later without a migration.
- **E-Q2.** Should the interval narrow as `portion_aliases.n_corrections` grows for a given phrase?
  It is intuitively right — a phrase corrected fifteen times is better known than one corrected once —
  but no evidence in the research supports any particular narrowing function, so none is specified.
- **E-Q3.** Which macronutrients are in scope for interval storage (REQ-NUT-031)? See D-Q3.
- **E-Q4.** What should REQ-NUT-047 actually say to Joe, in his words? The requirement mandates the
  statement; the wording is his.

---

---

## F. CAPTURE BUDGET AND PROMPTING

Joe's stated budget, verbatim: *"should be 3 [minutes] in the morning; pictures and quick details
about each meal; should have easy voice note update systems for feelings and emotions and food, snacks
and plans and activities and all that; and I should have the night check-in which is like 7-10 minutes
if I write."*

The literature says he arrived at a good design by instinct. The numbers that constrain the build:

- Scheduled morning assessment: **81% compliance** at week 0, decaying 2%/week. Random
  signal-contingent prompts: **52%**, a 29-point gap before any decay.
- Batteries of **more than 26 items drop to 63% compliance** vs 78.6–84% for ≤26 items. Prompt
  *length* matters far more than prompt *frequency*.
- **Tailored** prompts timed from the individual's own observed eating times: **+1.78 images/day,
  p ≤ .001**. Generic fixed-time prompts: +0.83/day, **p = .23, not significant**.
- Streaks and gamification are mixed-to-negative; they work through loss aversion, which is actively
  harmful once broken.
- The practical adherence marker is **two eating occasions per day logged**, not every meal.

### F.1 Budget enforcement

**REQ-CAP-080** (Ubiquitous) The morning check-in screen SHALL present no more than 5 input items in
total.

**REQ-CAP-081** (Ubiquitous) The morning check-in screen SHALL present no more than 3 rating scales.

**REQ-CAP-082** (Ubiquitous) No single capture screen or prompt in the system SHALL present more
than 26 items.

**REQ-CAP-083** (Ubiquitous) The meal capture Shortcut SHALL complete from trigger to POST in no
more than 4 user actions: trigger, shutter, speak, done.

**REQ-CAP-084** (Ubiquitous) The evening reflection screen SHALL present the day's already-captured
meals, workouts, locations, mood points and sleep for review before presenting any field requiring
recall.

**REQ-CAP-085** (Ubiquitous) The review list SHALL present no more than 5 items per evening, ordered
by descending interval width.

**REQ-CAP-086** (Event-driven) WHEN Joe leaves the evening reflection screen without acting on the
review list, the system SHALL retain every affected row unchanged with its existing provenance and
interval, and SHALL NOT re-prompt about those items.

### F.2 Prompting

**REQ-CAP-087** (Ubiquitous) The system SHALL NOT send a prompt at a randomly chosen time.

**REQ-CAP-088** (Ubiquitous) The system SHALL send no more than 3 scheduled prompts per day.

**REQ-CAP-089** (Event-driven) WHEN at least 14 days of meal captures exist, the resolution job
SHALL compute the median `captured_at` time-of-day for each of Joe's distinct eating occasions and
SHALL write them to `prompt_schedule`.

**REQ-CAP-090** (State-driven) WHILE a `prompt_schedule` row exists, the system SHALL send that
prompt 15 minutes before the computed median eating time.

**REQ-CAP-091** (Event-driven) WHEN a calendar month elapses, the resolution job SHALL recompute
`prompt_schedule` from the trailing data.

**REQ-CAP-092** (Ubiquitous) The system SHALL deliver every prompt via Web Push and SHALL NOT
deliver prompts by SMS or email.

**REQ-CAP-093** (Unwanted behaviour) IF a scheduled prompt's corresponding capture has already been
received for that day, THEN the system SHALL suppress that prompt.

### F.3 Compliance instrumentation, without gamification

**REQ-CAP-094** (Ubiquitous) The system SHALL compute and display rolling 7-day capture coverage as
a percentage.

**REQ-CAP-095** (Ubiquitous) The system SHALL NOT display a streak count, a consecutive-day counter,
a badge, a chain, or any message referring to a broken run.

**REQ-CAP-096** (Ubiquitous) The system SHALL define the dietary self-monitoring adherence bar as 2
eating occasions logged per day and SHALL NOT set the bar at 100% of meals.

**REQ-CAP-097** (Event-driven) WHEN rolling 7-day morning check-in coverage declines by more than 2
percentage points per week for 3 consecutive weeks, the system SHALL write a row to `design_alerts`
with reason `compliance_decline_exceeds_baseline`.

**REQ-CAP-098** (Ubiquitous) The system SHALL NOT respond to declining coverage by increasing prompt
frequency.

**REQ-CAP-099** (Ubiquitous) The system SHALL NOT impute a missing meal, and a day with two logged
meals SHALL report `coverage_pct = 50%` rather than an estimated third and fourth meal.

### F.NON-GOALS

- Streaks, badges, chains, and any competitive or social layer. For a private single-user system there
  is no social mechanism to make gamification work, and the downside — abandoning the whole system
  after one missed day — is severe.
- Nagging. When compliance drops, the correct response is to shorten the task, not to add reminders;
  standard fixed-time prompts were not statistically significant and *all* participants in the
  tailored-prompting study found intrusive notifications aversive.
- Asking Joe anything the phone can answer by itself. The active capture budget is spent only on
  feelings, intent, meaning, and food.
- Aggressive calorie targets and precision theatre. Both are among the patterns implicated in
  disordered eating behaviour in app-based self-monitoring, and both are incompatible with Section E.

### F.ALTERNATIVES CONSIDERED

- **More scheduled prompts.** The two meta-analyses disagree: the broad one (496 samples, 677,536
  participants, mean compliance 79.19%) found number of assessments per day had **no** significant
  effect; the health-behaviour one found 1–3 prompts/day → 87% vs ≥6 → 79.4%. The defensible synthesis
  is that there is no upside above ~3 and there is downside risk, hence REQ-CAP-088.
- **Financial or token incentives.** Statistically significant in the literature (82.21% vs 76.20%,
  p = .014) but only ~6 points, and structurally meaningless in a self-built personal system.
- **Generic fixed-time meal reminders** at 7:15 / 11:15 / 17:15. Explicitly rejected on evidence:
  +0.83 images/day at p = .23. The tailored variant at p ≤ .001 is what REQ-CAP-089 through
  REQ-CAP-091 implement.
- **Confirming captures at capture time to improve data quality.** Rejected; the resolution is
  asynchronous batched review inside a session Joe has already budgeted 7–10 minutes for, where the
  attention is free. This is the single most important UX decision in the capture layer.

### F.UNRESOLVED QUESTIONS

- **F-Q1.** What counts toward "rolling 7-day coverage" (REQ-CAP-094) — morning check-in, 2+ meals,
  evening reflection, or a weighted blend? The research supports the 2-meals marker for diet
  specifically but does not define a composite coverage metric.
- **F-Q2.** Does Joe want the `design_alerts` row of REQ-CAP-097 surfaced to him, or held for the
  agent to act on? It is a signal that *the design is failing*, not that Joe is.
- **F-Q3.** How many distinct eating occasions should `prompt_schedule` model — 3, 4, or learned from
  the data? The tailored-prompting study sent one prompt 15 min before the earliest eating episode;
  extending it to every meal is an extrapolation.
- **F-Q4.** Is 5 the right cap on nightly review-list items (REQ-CAP-085)? The research says "3 things
  I wasn't sure about today" illustratively; 5 is chosen as a ceiling, not derived.

---

---

## G. NEVER-RULES FOR THIS SUBSYSTEM

These restate, as binding requirements, the invariants that the rest of the document depends on. They
are listed separately because they are the ones most likely to be eroded by a well-meaning
optimisation six months from now. Several are inherited verbatim in force from the prior nutrition
spec.

### G.1 Numbers

**REQ-NUT-060** (Ubiquitous) No calorie, gram, or macronutrient figure stored by the system SHALL
originate from a language model or a vision model.

**REQ-NUT-061** (Unwanted behaviour) IF a model response contains a numeric nutrient quantity, THEN
the resolution job SHALL discard it at the adapter boundary and SHALL NOT store it with a confidence
score.

**REQ-NUT-062** (Ubiquitous) The system SHALL NOT render an unresolved food as a number.

**REQ-NUT-063** (Ubiquitous) The system SHALL NOT present a nutrient interval as a point estimate
anywhere in the interface, including in summaries, notifications and exports.

**REQ-NUT-064** (Ubiquitous) The system SHALL NOT describe a low logged intake of any nutrient as a
deficiency.

**REQ-NUT-065** (Ubiquitous) The system SHALL NOT render an inferred item identically to a confirmed
one.

### G.2 Capture

**REQ-CAP-100** (Ubiquitous) Capture SHALL NOT block on a network call, a database lookup, a search
result, or a required field.

**REQ-CAP-101** (Unwanted behaviour) IF the resolution service, the transcription service, the
extraction service and the database are all unavailable, THEN the capture Shortcut SHALL still
complete and SHALL still persist the payload to the local queue file.

**REQ-CAP-102** (Ubiquitous) The system SHALL NOT ask Joe to confirm anything at capture time.

**REQ-CAP-103** (Ubiquitous) The system SHALL NOT lose an input to a failed enrichment.

**REQ-CAP-104** (Ubiquitous) The system SHALL NOT treat the server's receive time as the event time.

**REQ-CAP-105** (Ubiquitous) The system SHALL NOT modify or delete a `raw_captures` row as part of
any correction, reprocessing, or schema migration.

**REQ-CAP-106** (Ubiquitous) The system SHALL NOT request a camera, microphone, or geolocation
permission from the PWA.

**REQ-CAP-107** (Ubiquitous) The system SHALL NOT nag, and missing logs SHALL surface as coverage
rather than as guilt.

### G.NON-GOALS

- Making these rules configurable. A never-rule behind a feature flag is not a never-rule. If one of
  these must change, it changes here, in the requirements, with an ID and a reason.
- Enforcing them by convention. Where a database constraint can enforce a rule (REQ-NUT-034,
  REQ-CAP-012, REQ-CAP-016), the constraint is the enforcement and the code comment is not.

### G.ALTERNATIVES CONSIDERED

- **Storing model-produced numbers at low confidence rather than discarding them** (REQ-NUT-061). This
  is the intuitive, tolerant design and it is wrong: a wrong number carrying a confidence score still
  ends up in a chart eventually, whereas a number that never enters the system cannot.
- **Allowing capture to block briefly on a fast lookup** to improve the immediate feedback. Rejected —
  it converts every network hiccup into a lost meal, and the meal anchor is the atom that must never
  fail.

### G.UNRESOLVED QUESTIONS

- **G-Q1.** Is there any circumstance in which Joe wants a single number with no interval — for
  example an export to a third-party app that cannot accept one? REQ-NUT-063 currently forbids it
  everywhere including exports.
- **G-Q2.** Should REQ-CAP-102 admit one exception: a same-second undo affordance on a mis-triggered
  capture? An undo is not a confirmation, but it is a tap.

---

---

## H. GHERKIN ACCEPTANCE SCENARIOS

These are what Joe verifies against. He cannot read code; he can read these and check the screen.
Every scenario names the requirement IDs it exercises.

---

### Scenario 1 — The Big Mac, spoken, happy path
*Covers: REQ-CAP-003, REQ-CAP-006, REQ-CAP-011, REQ-CAP-030, REQ-CAP-051, REQ-CAP-053, REQ-CAP-058,
REQ-NUT-001, REQ-NUT-013, REQ-NUT-014, REQ-NUT-036, REQ-NUT-044*

```gherkin
Given the food cache contains no entry for "big mac"
  And the daily neuron ledger for today totals 400 neurons
When Joe double-taps the back of his phone and says "I ate a Big Mac from McDonald's"
Then a raw_captures row exists with source 'shortcut_voice' and the audio duration recorded
  And the transcript "I ate a Big Mac from McDonald's" is stored on that row
  And an extracted item exists with name "Big Mac", evidence "a Big Mac", quantity 1
  And that item's provenance is 'extracted'
  And no field named calories, kcal, protein, carbs or fat appears in the extraction output
  And the item resolves against USDA FoodData Central Branded with a recorded fdcId
  And estimate_method is 'labelled'
  And the meal displays as "~<point> kcal (<point×0.90>–<point×1.10>)"
```

---

### Scenario 2 — The Big Mac, photographed, no spoken words
*Covers: REQ-CAP-010, REQ-CAP-068, REQ-NUT-038, REQ-NUT-039, REQ-NUT-021, REQ-CAP-060*

```gherkin
Given Joe taps the NFC tag on the fridge and photographs a Big Mac without speaking
When the photo is processed
Then the uploaded image has a longest edge of 1024 pixels
  And the vision model output contains only item names, confidences, portion cues and counts
  And no quantity in grams appears anywhere in the vision model output
  And the item's quantity provenance is 'defaulted'
  And estimate_method is 'photo_estimate'
  And kcal_low equals 0.75 × kcal_point
  And kcal_high equals 1.60 × kcal_point
  And the interval is visibly wider above the point value than below it
  And the item appears in tonight's review list with reason 'portion_defaulted'
```

---

### Scenario 3 — Homemade meal with no branded match
*Covers: REQ-NUT-001, REQ-NUT-015, REQ-NUT-024, REQ-NUT-025, REQ-NUT-026, REQ-NUT-027, REQ-NUT-040,
REQ-NUT-062*

```gherkin
Given Joe says "I had my mum's chicken curry, a big bowl"
  And no configured source returns a match for "mum's chicken curry"
When the nightly resolution job runs
Then the item is stored with name "mum's chicken curry" exactly as extracted
  And nutrition_status is 'unresolved'
  And kcal_low, kcal_point and kcal_high are all NULL
  And no nutrients from a generic "chicken curry" row have been substituted
  And the day's total states "1 unresolved item"
  And the item is not displayed to Joe as an error or a failure
  And the item appears in tonight's review list with reason 'no_source_match'
```

---

### Scenario 4 — Joe resolves the unresolved item, and the system learns
*Covers: REQ-NUT-017, REQ-NUT-018, REQ-NUT-022, REQ-CAP-014, REQ-CAP-105*

```gherkin
Given "mum's chicken curry" is unresolved from Scenario 3
When Joe names it in the evening review list and gives a portion of 400 g
Then a foods_cache row exists with source 'joe'
  And a food_aliases row maps "mum's chicken curry" to that cache entry
  And a portion_aliases row records the phrase "a big bowl" against 400 g
  And nutrition_status becomes 'resolved'
  And the original raw_captures row is byte-for-byte unchanged
When Joe says "mum's chicken curry, a big bowl" again three weeks later
Then it resolves from cache with zero network requests
```

---

### Scenario 5 — Voice note at 2am
*Covers: REQ-CAP-063, REQ-CAP-064, REQ-CAP-066, REQ-CAP-021, REQ-CAP-022*

```gherkin
Given the personal day boundary is configured at 04:00
When Joe records a voice note at 02:14 on Tuesday saying "just had some crisps"
Then captured_at is 02:14 on Tuesday
  And the extraction output contains no timestamp, only the text spans
  And dateparser resolves the event time with RELATIVE_BASE = 02:14 Tuesday
  And the item is attributed to Monday's food log
  And no rollup buckets this capture by its server receive time
```

---

### Scenario 6 — Capture arrives while offline
*Covers: REQ-CAP-019, REQ-CAP-020, REQ-CAP-016, REQ-CAP-017, REQ-CAP-021, REQ-CAP-101*

```gherkin
Given Joe's phone has no network connection
When he taps the fridge NFC tag, photographs his lunch and says "chicken and rice"
Then the Shortcut completes without showing an error dialog
  And one JSON line containing capture_id and captured_at is appended to the local queue file
When the network returns and the hourly replay automation runs
Then the queued line is POSTed and a raw_captures row is created
  And the meal is filed at its original captured_at, not at the replay time
  And the queue line is removed only after HTTP 202 is received
When the same line is accidentally replayed a second time
Then the endpoint returns {"status":"duplicate"} and no second meal appears
```

---

### Scenario 7 — The neuron budget is exhausted
*Covers: REQ-CAP-037, REQ-CAP-038, REQ-CAP-039, REQ-CAP-041, REQ-CAP-042, REQ-CAP-043, REQ-CAP-044,
REQ-CAP-040*

```gherkin
Given today's neuron ledger totals 9,150 neurons
When Joe records a voice note about his dinner
Then a raw_captures row is created containing the full audio payload
  And no Workers AI call is issued
  And processing_status is 'deferred_budget'
  And the PWA shows "1 capture waiting for tomorrow's AI budget"
  And no charge is incurred and no payment method is attached to the account
When the next UTC day begins and the resolution job runs
Then the deferred capture is transcribed before any capture received that day
  And the dinner appears in the log at its original captured_at
```

---

### Scenario 8 — The transcription service is down
*Covers: REQ-CAP-025, REQ-CAP-026, REQ-CAP-027, REQ-CAP-103, REQ-CAP-011*

```gherkin
Given Cloudflare Workers AI is returning HTTP 503
When Joe records a voice note
Then the ingest endpoint returns HTTP 202 to the phone
  And a raw_captures row exists with the audio retained
  And processing_status is 'pending_enrichment' with last_error recorded
  And the nightly job re-attempts enrichment
When 72 hours pass with the service still down
Then the capture appears in the review list with reason 'enrichment_stalled'
  And the capture has not been dropped, truncated or marked complete
```

---

### Scenario 9 — The model invents a food that was never said
*Covers: REQ-CAP-053, REQ-CAP-054, REQ-CAP-056, REQ-NUT-060, REQ-NUT-061*

```gherkin
Given the transcript is exactly "I ate a Big Mac from McDonald's"
When the extraction model returns an additional item "large fries" with evidence "and fries"
Then the span assertion transcript[start:start+len(evidence)] == evidence fails
  And "large fries" is not written as a meal item
  And reason 'span_mismatch' is recorded
When the same response also contains the field "calories": 563
Then that value is discarded at the adapter boundary
  And it is not stored anywhere at reduced confidence
```

---

### Scenario 10 — The PWA never asks for permission
*Covers: REQ-CAP-001, REQ-CAP-002, REQ-CAP-004, REQ-CAP-106*

```gherkin
Given the PWA is installed to the Home Screen
When Joe opens it, reloads it, closes it and reopens it ten times over a week
Then no "allow for this website" prompt for camera, microphone or location ever appears
  And no code path in the shipped bundle references getUserMedia or webkitSpeechRecognition
When a photo must be attached from inside the PWA
Then it is acquired via <input type="file" accept="image/*" capture="environment">
  And still no permission prompt appears
```

---

### Scenario 11 — A day of four photo-logged meals
*Covers: REQ-NUT-043, REQ-NUT-047, REQ-NUT-046, REQ-NUT-063, REQ-NUT-048*

```gherkin
Given Joe logged four meals today, all by photo with no spoken portions
When the daily total is displayed
Then the total's low bound is the sum of the four kcal_low values
  And the total's high bound is the sum of the four kcal_high values
  And the total is NOT displayed as a single number
  And because the interval width exceeds a 500 kcal deficit, the screen says in plain words
      that today's logging cannot resolve that difference
  And no red/green or over/under judgment framing appears
```

---

### Scenario 12 — Prompting, streaks, and a missed day
*Covers: REQ-CAP-087, REQ-CAP-088, REQ-CAP-089, REQ-CAP-090, REQ-CAP-092, REQ-CAP-093, REQ-CAP-094,
REQ-CAP-095, REQ-CAP-099, REQ-CAP-107*

```gherkin
Given 14 days of meal captures exist with a median lunch time of 13:10
When the prompt schedule is computed
Then a prompt is scheduled for 12:55, delivered by Web Push and not by SMS
  And no more than 3 scheduled prompts exist for the day
  And no prompt is ever scheduled at a random time
When Joe logs lunch at 12:30 before the prompt fires
Then that prompt is suppressed
When Joe logs nothing at all the following day
Then rolling 7-day coverage drops by roughly 14 points and continues to display
  And no streak, chain, badge or "you broke your run" message appears anywhere
  And the missed day shows coverage 0%, with no imputed meals
  And the system does not increase prompt frequency in response
```

---

*End of requirements. Unresolved questions A-Q1…G-Q2 feed `docs/OPEN_QUESTIONS.md`. They are
decisions for Joe, not for the agent.*
