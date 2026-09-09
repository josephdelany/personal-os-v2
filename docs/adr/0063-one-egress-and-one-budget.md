# ADR-0063: One outbound path, one shared budget

## Status
Accepted. Builds `lib/egress.py` and migration 0052 (`core.neuron_ledger`,
`core.neuron_budget`). Satisfies REQ-CAP-035..042. Prerequisite pulled forward from B12/B16
for B11.2, per EXECUTION_PLAN M3.

## Date
2026-09-09

## Why one ledger

Three consumers will call Cloudflare Workers AI, and each was specified separately:

- Ask's language planner (B11.2, REQ-ASK-008)
- Nutrition resolution (B12, REQ-NUT §E)
- Media transcription and extraction (B16, REQ-CAP-030..034)

Each would naturally count its own usage. **Three counters against one shared 10,000-neuron
daily allowance means none of them knows the real total**, and the budget is enforced by
whichever consumer happens to run last — which is to say, not enforced. One ledger, one sum,
one gate, expressed as `core.neuron_budget()` in SQL so every consumer asks the same question
of the same numbers (RULE-12).

## Why the hard cap is the $0 mechanism

RULE-28 disqualifies a service that bills on overage rather than failing. Workers AI hard-fails
at 10,000 neurons/day and REQ-CAP-042 forbids attaching a payment method — so the enforcement
is **the vendor's refusal, not our restraint**. The ledger exists so the system stops at 9,000
rather than discovering the ceiling by hitting it.

The 1,000-neuron margin between the soft ceiling and the hard cap is reserved exclusively for
re-processing captures deferred on a previous day (REQ-CAP-039). Without that reservation a
busy day starves yesterday's backlog forever: new work always arrives first and always wins.

## Decisions

1. **The log row is written BEFORE the request, and survives failure.** RULE-29 requires a row
   for every outbound call, not for every *successful* one. Logging afterwards means a call
   that hangs, crashes the process, or errors leaves no trace — and those are precisely the
   calls worth having a trace of. The ledger row is written as `issued` and settled to `ok` or
   `error`; an errored call still spent its neurons, so writing the row only on success would
   make the budget under-count exactly when it matters most.

2. **The payload is screened before anything else happens.** A coordinate or the home location
   reaching a prompt is the failure RULE-29 exists to prevent, and a prompt is assembled from
   data by code that cannot always know what it picked up — so the screen runs over the whole
   payload as text rather than field by field. Home coordinates never egress at any precision,
   so there is no threshold to tune, only a refusal. A false positive costs one refused call; a
   false negative is an irreversible disclosure, and the asymmetry sets the sensitivity.

   *The detail that made the first version useless:* the payload is screened as JSON, where a
   key reads `"lat": 40.7`. A pattern expecting `lat:` matched **none** of the keys it existed
   to catch. Caught by the test, not by reading.

3. **Over budget is a refusal — never a smaller call, never a retry, never a wait.** Degrading
   to the deterministic path is the caller's job (RULE-15: nothing may require the model to be
   available). A retry doubles the spend against a budget whose whole purpose is to make the
   ceiling reachable exactly once, and REQ-CAP-043 already says a failed capture is not lost —
   the caller defers it.

4. **One outbound request in the repository.** `tools/validate_layout.py` already fails the
   build on a network-capable import outside `lib/egress.py` and `lib/db.py`; a test asserts
   there is exactly one `urlopen` and that no path names another provider or a paid tier.

## What this does not do

- **No call has been made.** Every test uses an explicit `_transport` seam — a parameter, not
  a monkeypatch, so what is substituted is visible in the signature. Nothing here proves
  Workers AI accepts the request shape, and no credential has been exercised.
- **Migration 0052 is not applied.** Dry-run verified in the full chain (416 statements,
  rolled back); the live apply needs the same permission as 0051.
- **`processing_status = 'deferred_budget'` handling (REQ-CAP-038/040/044) is not built.** The
  budget refuses; nothing yet defers a capture, orders the backlog by `captured_at`, or shows
  the count in the PWA. That is B16's ingest path and is held there rather than half-built here.
- **The neuron estimate is an estimate.** REQ-CAP-036's audio formula is exact and implemented;
  the cost of a *planning* call is supplied by the caller and is not yet calibrated against
  observed usage. Until a real call is made, the budget is bounded by an assumption, and the
  ledger is what will let that assumption be checked.
