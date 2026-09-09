# Checkpoint — 2026-09-09

Reconciled against Git at `1304b90` + this commit. Revision under test: HEAD.

## LIVE (deployed and observed in production)

- Migration **0051** applied. `core.raw_captures` carries a `file_import` source; the
  registry holds 43 metrics, 37 monitored.
- **33,355 atoms imported** from `export.zip` (2026-07-01 .. 2026-09-09), 25 metric keys,
  one capture row. `check_invariants.py --core core`: ALL PASS, orphan atoms 0. Idempotence
  proven against production — a re-run preloaded 33,355 dedupe keys and skipped every one.
- `check_freshness.py` against real data: **9 fresh, 17 stale, 11 never seen, 6 unmonitored**.

## INTEGRATION BOUNDARY — run at HEAD

- Full production pytest suite: **219 passed, 218 skipped, exit 0** (26 min). The skips are
  the disposable-server SQL tests, which skip against production by design (ADR-0082).
- Disposable-server SQL suite: **299 passed** under `America/New_York` and `UTC`.
- `tests/test_reconstruct.py`: 12 passed. `validate_layout.py`: 42/42.
- `check_invariants.py --core core`: ALL PASS.

## IMPLEMENTED AND LOCALLY TESTED (not deployed)

- **0049 Ask core** — all round-4 findings closed. REQ-ASK-031 refuses an uncomputable
  question shape instead of substituting a nearby one.
- **0050** nutrition, **0052** neuron ledger, **0053** source inventory + derivation
  catalogue, **0054** inferred events, **0055** `get_reconstruction` — written, locally
  verified, **not applied**. Six migrations are now queued behind one authorization.
- `tools/engines/reconstruct.py` — the deterministic evaluator. Three refusals enforced by
  signature: no probability parameter, no path from missing evidence to `did_not_occur`, and
  evidence after the cutoff is dropped.
- `tools/build_inventory.py` (113 rows) and `tools/build_catalogue.py` (25 measures) run
  clean against production read-only; neither has been committed to a table.

## ACTIVE UNIT

**B14R step 5b** — wire a `reconstruct` operation into `public.ask`. Held deliberately: the
operation row and the `ask()` branch must land together, because a row in
`config.operations` with no implementation is a registered operation that cannot run, which
is worse than an absent one (RULE-11). `ask()` lives in 0049 and is ~1400 lines through four
review rounds; amending it belongs in the same change as applying it.

*Proves it complete:* "what happened on <day>" returns a stored reconstruction with its
evidence, both independence counts, its alternatives and its revision history, and refuses
with REQ-ASK-031 when no registered method covers the question.

## BLOCKED — needs Joe

| # | Question | What it holds up |
|---|---|---|
| OQ-54 | Device precedence: Watch or iPhone, when both observed a metric? | Every summed daily total for `steps`, distance, flights, active energy, exercise minutes |
| OQ-55 | Why did the Watch stop syncing (worn / paired / permissions / storage)? | 17 stale metrics — most of the physiological signal |
| OQ-56 | 228 unexplained missing records; and 20 Apple Health types (11,106 records in window) have no scope ruling | Inventory accuracy for M1/M4 closure |
| — | Apply migrations 0049, 0050, 0052, 0053 | M2/M3 deployment |
| OQ-48 | Which sleep metric means "how long did I sleep" | Any sleep answer |

## NEXT ACTION

Write the B14R step-3 ADR, then migration 0054 for `core.inferred_events`. Independent of
every hold above.

## Do not repeat

- The panel does not read the imported atoms. Wiring it is gated on OQ-54.
- `sleep_asleep_min`, `sleep_core/deep/rem/awake_min`, `sleep_inbed_min` and `sleep_minutes`
  are five different concepts. They are not summed or mapped onto each other.
- "Capture stopped" is wrong. The Watch stopped; the phone did not.
