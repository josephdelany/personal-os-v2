# ADR-0057: The drop folder — exported files become captures, keyed by file hash

## Status
Accepted. Built by B13 (`docs/build/B13_importers.md`), migration 0051.
Opens OQ-48 (the four session-level `screen_*` metrics) and OQ-49 (unverified
institution header signatures).

## Date
2026-09-09

## Context — the failure this is a response to

On **2026-07-28** the device-side capture path stopped. Everything downstream of it went dark
on the same day and stayed dark:

| Stream | Last row |
|---|---|
| `public.intraday` — `hr`, `hrv_window`, `spo2`, `sleep_stage`, `resp_rate`, `walking_*` | 2026-07-28 |
| `public.events` — `chrome_visit`, `youtube_watch` | 2026-07-28 |
| `public.locations` (OwnTracks) | 2026-07-29 |
| `public.signals` — `apple_sleep`, `apple_hrv`, `apple_circadian`, `apple_vitals` | 2026-07-28 |

The four `apple_*` signal feeds are **derived** from `intraday`. They are not independently
broken; their input died and they stopped with it.

Meanwhile the server-side pulls — `weather`, `gmail`, `calendar`, the watchdog, both
keepalives — kept running and kept writing `ok` rows to `ops.runs`. **The system therefore
looked healthy for 43 days while capturing almost nothing.** That is the specific failure
mode this ADR exists to answer: liveness of the *jobs* was being monitored, freshness of the
*data* was not.

The recoverable part matters more than the diagnosis. Apple Health still holds those samples
on the phone, and Chrome/YouTube history is retrievable through Google Takeout. The gap is
not yet lost — but it is exactly the kind of loss the project's standing ruling ("data can
only be collected once, code can be written anytime") is meant to prevent, and there is no
second chance if the phone is wiped or a retention window rolls over.

## Decision

A **drop folder**, `~/PersonalOS_Drop/`. Joe exports a file into it; `tools/import_drop.py`
turns it into captures and atoms.

1. **One file, one capture.** Each dropped file becomes exactly one `core.raw_captures` row
   with `source = 'file_import'` (added to the `capture_source` enum by migration 0051). Its
   payload carries the file's SHA-256, name, byte count, record count and the period covered.
   Every atom from that file references that row, so INV-1 holds by construction.
2. **The file's SHA-256 *and the requested window* are the idempotency key.** REQ-CAP-006 asks for a UUIDv7 minted on the
   device. An exported file has no device identity to mint one from, so the content hash
   takes that role. A file whose hash is already present is skipped whole, before parsing —
   which is REQ-FIN-011/012's `raw_documents` rule expressed in the spine's vocabulary: the
   capture row **is** the document row, and a separate table for it would be a second place
   to keep the same fact.

   The window belongs in the key, and leaving it out was a real defect caught in review. The
   documented primary use is `--since 2026-07-28` against a seven-year export to recover the
   gap; that writes only the windowed atoms, and a hash-only key then means the rest of that
   export can never be read again — with no remedy except deleting a `raw_captures` row, which
   RULE-02 forbids. Re-running the same file with the same window is still a no-op, and a
   widened window is safe because the per-atom dedupe (3) stops anything already stored from
   being written twice.
3. **A second dedupe, per atom, inside the file.** Re-exports overlap. Every export of Apple
   Health contains every earlier export's samples, so the hash alone protects only against
   the *identical* file. An atom whose (kind, metric_key, instant, value, **evidence**) is
   already stored is not written again. Without this, the second export doubles the first's
   atoms and every mean in the system moves — silently, because nothing errors.

   **Evidence is in the key, and has to be.** Without it, two genuinely distinct transactions
   on the same day for the same amount — two identical fares, a $20 payment to each of two
   people — produce identical keys, and the second is silently discarded and counted as a
   duplicate. That is ordinary data, not an edge case. It was made worse by a second bug: the
   statement reader overwrote Venmo's and Cash App's real timestamps with a noon anchor meant
   for date-only sources, erasing the last thing that distinguished them. Both are fixed and
   both are pinned by `test_REQ_FIN_010_two_distinct_same_day_same_amount_transactions_are_both_kept`.
4. **The file never enters the database.** Only counts, timestamps and derived atoms. The
   export stays on the Mac and is moved to `_done/`, never deleted (RULE-29: nothing personal
   is committed anywhere, and the repository is public).
5. **Default is read-only.** Without `--commit` the transaction rolls back and only counts
   are printed. Counts, never contents: the command never prints a value, a merchant, a title
   or a URL.
6. **One SAVEPOINT per file.** Without it a single Postgres error leaves the transaction in a
   failed state, every later statement raises `25P02`, and the command dies with a traceback —
   losing the per-file report and every file that had already succeeded. That is not
   hypothetical: until migration 0051 is applied, `'file_import'` is not a valid capture source
   and the very first file fails, which is exactly when the report matters most.

7. **Errors are redacted before they are printed.** Postgres attaches
   `DETAIL: Failing row contains (…)` to a constraint violation, and for these tables that row
   carries `evidence_span` — merchant names, page titles, video titles. This command promises
   counts and never contents, and printing a raw driver error breaks that promise at exactly
   the moment something has gone wrong. For the same reason a CSV that matches no institution
   mapping writes its observed header to a local file under the drop folder and reports only
   the path and the column count: a CSV's first row is not always a header (Venmo's export
   opens with `Account Statement - (@joe)`), so it can be data.

8. **`--since` / `--until` bound the import by subject day.** This is how the 43-day gap is
   recovered without re-importing seven years, and it is also what bounds the dedupe key set
   held in memory. Without a window, every existing atom of the relevant kinds is loaded to
   dedupe against; the loaded count is printed rather than hidden, because that number is the
   memory cost.

## Why counting the file twice

`raw_captures` is append-only (RULE-02). Its payload has to be correct when it is written —
there is no later pass to correct `n_records`, and the atoms cannot be written before the
capture they reference exists. So the importer streams the file once to count and find the
period, writes the capture, then streams it again to write the atoms. The alternative was to
buffer every parsed record in memory, which for a 300 MB Apple Health export is exactly the
thing the streaming parser exists to avoid.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Drop folder + file hash (adopted)** | $0, no third party, works offline, and the hash makes a re-drop free. Costs Joe a manual export. |
| Watch the folder with a launchd job | Compatible with this and worth adding later; it does not change the model, only who runs the command. Not built yet — an unattended job that writes to production on a file appearing deserves its own decision. |
| Upload to Supabase Storage and parse server-side | Puts the raw health export in a third-party store for no gain; the parse has to happen somewhere, and locally it is free. |
| A separate `raw_documents` table per REQ-FIN-011 | Rejected as a second home for a fact `raw_captures` already holds. Recorded here so the divergence from the spec's literal wording is visible rather than accidental. |
| Re-point the old stack's importers at `core.*` | The old stack is what broke, and its code is not in this repository. B22 retires it; this does not extend it. |

## Consequences

- The 2026-07-28 gap becomes recoverable by an export Joe can make today.
- Every feed gains a manual path that works when its automatic path breaks — the system stops
  being one silent device failure away from losing months.
- It depends on Joe remembering to export. That is a real weakness and is not solved here:
  what is needed is **staleness alerting on the data, not the job** (Gate 4), since the whole
  point of this ADR's context section is that job liveness was green throughout. Recorded as
  the open work it is.
- `ofxtools` becomes a conditional dependency for OFX/QFX/QBO only (see ADR-0059). CSV, Apple
  Health and Takeout need nothing that is not already installed.
