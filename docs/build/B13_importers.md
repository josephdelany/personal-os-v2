# B13 — Importers: the seven-year streams become captures in the new stack (migration 0051)

**What this is.** Apple Health, the bank, and Chrome/YouTube history still flow through
the *old* repo into `public.signals` / `public.events` / `public.transactions`. If that
stack stops, the file goes stale. This build rebuilds each importer as a capture path
into `core.raw_captures` → atoms → panel, so the old stack can be retired (B23). Two
sessions. Also satisfies finance §A.1 (the CSV/QFX floor) and §A.4 (dedupe, two
timestamps).

**Requirement IDs satisfied:** REQ-FIN §A.1 and §A.4 IDs (quote them), REQ-CAP-006
(UUIDv7 on device is not applicable to file imports — record the file hash as the
idempotency key instead: ADR), REQ-INF-505, INV-1/2/4, REQ-LOC-005 (Takeout location
history is **not** imported here — B5's restricted path only; ADR the exclusion).
**ADRs:** ADR-0057 (drop-folder import model, file-hash idempotency), ADR-0058
(Apple Health XML → sample atoms mapping), ADR-0059 (bank CSV/QFX schema detection).

## The model (ADR-0057)
A drop folder on Joe's Mac: `~/PersonalOS_Drop/` (it already exists). Joe drops
`export.zip` (Apple Health), `*.csv`/`*.qfx` (bank), `Takeout*.zip` (Google). A local
command `python3 tools/import_drop.py` (run by Joe, or by a launchd job every night —
generate the plist) reads each file, writes **one `raw_captures` row per source file**
(`source='shortcut_text'` is wrong here — add `'file_import'` to the `capture_source`
enum by migration; payload = `{kind:'import', importer, file_sha256, n_records,
period:[from,to]}`; the file itself is never stored in the DB — it stays on the Mac),
then writes atoms in batches with `raw_capture_id` = that row (INV-1). A file whose
sha256 already exists is skipped (idempotent). Nothing is deleted from the drop folder;
processed files are moved to `~/PersonalOS_Drop/_done/`.

## Importers
1. **Apple Health** (`tools/importers/apple_health.py`, streaming XML parse — the export
   is hundreds of MB; use `xml.etree.iterparse`, never load it whole). Record types →
   atoms (kind, metric_key, unit, state_class, precision) exactly as `extract_checkins.py`'s
   `HK` table already maps for the seven health kinds, extended to: HRV SDNN, resting HR,
   respiratory rate, wrist temperature, SpO2, VO2max, steps, active energy, exercise
   minutes, sleep stages (asleep/inbed/deep/rem/core/awake as interval atoms with
   `valid_interval`, subject day by **wake day** per ADR-0019), body mass, walking
   metrics. Each record's `sourceName` becomes `estimate_method`-adjacent provenance in
   `evidence_span`. Dedupe against existing atoms on (metric_key, occurred_at or
   valid_interval, value) so a re-export is a no-op.
2. **Bank CSV/QFX** (`tools/importers/bank.py`): schema detection by header signature
   (§A.1's named formats — read them; add Joe's actual bank's format from a DISCOVER
   step where Joe drops one real file); two timestamps (posted vs transaction, §A.4);
   dedupe rule exactly as §A.4 states; writes `transaction` atoms (ADR-0027's kind) with
   amount, merchant descriptor raw, account, and a `core.entities` merchant row is **not**
   created here (B14 does resolution).
3. **Google Takeout** (`tools/importers/takeout.py`): Chrome `BrowserHistory.json` and
   YouTube `watch-history.json` → `web_visit` / `media_play` atoms with title, domain,
   channel in `evidence_span`/attributes; the panel's attention metrics
   (`screen_*`, `yt_events`, `chrome_events`) are re-derived in `panel.py` from atoms
   when present, falling back to `public.signals` (precedence: atoms > signals, and
   record the change in ADR-0058 because it flips `panel.py`'s stated order for these
   metrics only).

## Panel
`panel.py` gains atom-derived sources for every metric the three importers feed, with
the precedence documented; `src` tags `atoms:apple_health`, `atoms:bank`, `atoms:takeout`.

## Tests
```
test_ADR_0057_same_file_twice_writes_one_capture_and_no_duplicate_atoms
test_INV_1_every_imported_atom_references_the_file_capture
test_ADR_0058_sleep_intervals_assign_subject_day_by_wake_day
test_ADR_0058_iterparse_handles_a_300mb_fixture_within_memory_limit   (synthetic XML generated in the test, 300 MB, peak RSS < 500 MB)
test_REQ_FIN_A4_dedupe_two_timestamp_rule
test_ADR_0059_bank_schema_detection_on_three_fixture_headers
test_REQ_LOC_005_takeout_location_history_is_never_read
test_ADR_0058_panel_prefers_atoms_over_signals_for_attention_metrics
```
Fixtures are synthetic (generated), never Joe's data.

## Joe actions (list them at session end)
Export Apple Health (Health app → profile → Export All Health Data) → AirDrop
`export.zip` into `~/PersonalOS_Drop/`; download the bank CSV; request Google Takeout
(Chrome + YouTube only). Then `python3 tools/import_drop.py` once by hand; thereafter
the launchd job.

## Done when
Migration; three importers with tests; `import_drop.py` run against Joe's real files
with **counts only** pasted (never contents); panel `src` distribution before/after
pasted; ADR-0057/0058/0059; PROGRESS + WHAT I DID NOT DO (Gmail receipts are B17;
old stack still running until B23).
