# ADR-0035: Check-ins bridge into the spine; deterministic extraction; hourly schedule

## Status

Accepted (design + rolled-back proof). The two live applies (migrations 0019, 0020)
are **held for Joe's explicit yes** — the auto-mode classifier correctly enforces
STANDING_RULINGS STOP-AND-ASK #2/#3 on live writes; everything else here is inert
until they run.

## Date

2026-09-01

## Context

The phone's morning/night check-in shortcuts POST to the OLD system's Edge Function
(`ingest-checkin` → `public.checkins` + `signals` fan-out). The NEW trustworthy spine
was empty and nothing fed it. Editing the phone is Joe-only; redeploying the Edge
Function needs a Supabase access token the agent doesn't hold. But the agent DOES
hold the database — and the old and new systems share one database.

Discovered in the old workspace (`~/Documents/Claude/Projects/Personal Survilance`):
the full `ingest-checkin` source, which validates each scored field as an integer
0–10 before storing. So a `public.checkins` row is **already-structured, validated
capture data** — exactly what the spine's extraction stage otherwise exists to
produce.

## Decision

1. **Bridge at the database, not the device** (migration 0020). An AFTER
   INSERT/UPDATE trigger on `public.checkins` mirrors every check-in submission into
   `core.raw_captures` (`source='shortcut_text'`, `trust_level='trusted'`, full
   payload as JSONB). The phone keeps POSTing to the old function unchanged; the
   spine receives every capture from the same write. A re-submission (the old
   function upserts one row per day per type) fires a fresh capture row — an
   append-only correction, never an edit. A one-time guarded INSERT..SELECT mirrors
   the check-ins that already exist (real rows, real provenance; 3 at authoring).
   This is live-operational ingest, NOT the deferred Parquet legacy load (ADR-0028),
   which stays deferred.

2. **Check-in metric keys seeded with ADR-0018 coarsening** (migration 0019).
   Eleven `checkin_<type>_<field>` keys (`family='self_report'`,
   `state_class='measurement'`, `response_scale=[0,10]`, 11 points, rounding 1).
   Morning and night variants are distinct metrics — mood-at-wake and mood-at-night
   are different variables, and this preserves comparability with the legacy
   `${type}_${field}` signals convention.

3. **Extraction is deterministic — no model call** (`tools/extract_checkins.py`).
   The scores were validated integers at ingest, so the transform is pure: per
   present field one `self_report` atom with the ADR-0018 coarsened interval
   `[v−0.5, v+0.5]` clamped to [0,10], `estimate_method='self_report'` (never
   'measured'), subject_day per ADR-0019 (04:00 ET, by start); a non-empty note
   becomes a `note` atom carrying the verbatim text. RULE-11 is satisfied by
   construction; RULE-09 has no model output to police; cost is $0. **Idempotency is
   by atom existence** (a capture is done when atoms exist for its `capture_id`) —
   `raw_captures` is append-only and `processing_status` cannot be flipped, which
   the design treats as a feature: no state to corrupt.

4. **Unattended hourly schedule** (`.github/workflows/extract.yml`), same secret and
   pattern as the proven keepalive. Free on the public repo; a missed run self-heals.

## Review outcome (adversarial review 2026-09-01: 4 MAJOR + 5 MINOR; all resolved or ruled)

- **M1 (the scale).** The reviewer found `backfill_run.py` treats the same check-in
  fields as a **1–5** scale while this unit seeds **0–10** — and could not read the
  Edge Function to settle it. Settled with primary evidence: the deployed
  `ingest-checkin` source validates `Number.isInteger(v) && v >= 0 && v <= 10`, and
  the shortcut prompts read "Drive (0-10)" / "Restored (0-10)" on-device. **0–10 is
  correct; the backfill's 1–5 is the defect**, recorded on OQ-29's owed-loader-fixes
  list. This unit stands.
- **M2 (double-load with the deferred backfill).** Real. Resolution: the legacy
  loader must exclude the `checkins` stream when it ever runs — the mirror owns
  check-in ingest now. Recorded on OQ-29's owed list.
- **M3 (mirror could break live ingest).** Fixed: the trigger is now **fail-open**
  (EXCEPTION handler; a spine-side failure logs a WARNING and the check-in still
  saves). Detection path: the extract job's `ops.runs` heartbeat + a
  checkins-vs-captures count comparison.
- **M4 (night check-in subject-day vs the day it rates).** Not silently re-ruled:
  extraction follows ratified ADR-0019 by-start; the divergence is **OQ-38**, and
  the capture carries the phone's `checkin_date` so a future ruling re-derives
  losslessly under a new `rule_version`.
- **m1 (observability).** Fixed: every extract run writes an `ops.runs` row
  (`extract_checkins`, ok/error, rows_written).
- **m3 (unlinked corrections).** Fixed: extraction now populates `supersedes` — a
  re-submission's atoms supersede the prior current atom for the same
  metric_key+subject_day (notes likewise), so `atoms_current` resolves to one value.
- **m4 (backfill+trigger double capture).** Dissolved by the m3 fix: the second
  capture's atoms supersede the first's; currency is single-valued.
- **m2/m5 (empty-capture re-scan; any-atom-means-done).** Accepted as documented
  design limits: bounded cost; a code-version-aware re-extract would need a design
  of its own and is not silently attempted.
- **n1 (`if True:` scaffolding).** Removed in the v2 rewrite.

## Proof (rolled back, nothing persisted — RULE-01)

One transaction: migrations 0001–0020 into disposable schemas (0020's mirror read the
3 REAL `public.checkins` rows), extraction ran, output verified, invariants ALL PASS:
5 atoms (3 scored + 2 notes) with correct coarsened intervals and subject days; an
empty check-in produced 0 atoms (a gap, not a guess); idempotent re-run produced 0.

## Consequences

**Good.** The moment 0019+0020 apply, every future morning/night check-in feeds BOTH
systems from one tap — the old one keeps its continuity, the new one accumulates
trustworthy, provenance-complete atoms — with zero phone changes and zero new
credentials. Extraction runs hourly, unattended, forever, at $0.

**Cost / residual (named).**
- A check-in with no scores and no note re-scans every run (no atoms to mark it
  done). Bounded: one row per empty submission, trivial cost.
- The bridge mirrors `checkins` only. The old function also fans food items into
  `inferred_events` — the food path gets its own capture design (the food shortcut,
  next); the check-in `meta` (which includes any food array) IS carried in the
  mirrored payload, so nothing is lost meanwhile.
- The old system's `signals` fan-out continues unchanged; the two systems will hold
  overlapping self-report data with different vocabularies. Reconciliation is a
  Phase-5/6 question and is not silently decided here.

## Alternatives considered

- **Repoint the phone shortcuts at `ingest_capture` (ADR-0034).** Works, but needs
  Joe editing every shortcut, loses the old system's continuity (`signals`,
  `checkin_probes`), and adds device steps for zero data gain over the mirror.
- **Redeploy the Edge Function to dual-write.** Needs a Supabase access token the
  agent doesn't hold, and an edge redeploy for what one trigger does in-database.
- **An LLM extraction pass over check-ins.** Rejected outright: the fields are
  already validated integers; a model call would add cost, noise, and a RULE-09
  surface for literally structured data.
