# ADR-0008: Capture schema — capture_source enum and the workout dedup identity

## Status

Accepted for the **schema** (enum + dedup identity). The full capture **transport**
contract (Shortcuts-to-endpoint, idempotency, offline queue) is deferred to Phase 3.

## Date

2026-08-23

## Context

Decision 8 of the Phase-2 plan settled the capture schema consequences, with two
corrections accepted by Joe (2026-08-23):

- **One record per model call, raw text retained alongside every extraction** —
  already the spec (REQ-CAP-006/011/012, immutable `raw_captures.payload` with the
  transcript kept). No change. The "re-extract when models improve" path is the
  `supersedes` mechanism.
- **Correction: Apple's on-device model context is 4,096 tokens, not ~8k**
  (Apple TN3193) — off by 2×. The chunking constraint is *tighter*; a long
  untrusted email/PDF routed through the on-device model will silently truncate.
  This compounds ADR-0020: long untrusted inputs both truncate *and* are the
  injection surface.
- **Correction: the workout dedup key `(source + start + duration)` is wrong.** The
  duplicate exists precisely because it comes from a *different source* (Apple Watch
  vs a GymKit machine) for the *same* activity. Putting `source` in the identity
  fails to collapse the very duplicate it targets. Apple keys on time overlap +
  source priority.

## Decision

- **`core.capture_source` enum**, extended from day one: the spec's four
  (`shortcut_voice`, `shortcut_photo`, `shortcut_text`, `pwa_text`), plus
  `notification_parse`, plus reserved values for the net-new feeds
  (`healthkit_workout`, `email_receipt`, `location`). `raw_captures` is the single
  immutable landing for every feed, so every atom traces to it (INV-1).
- **Workout dedup identity is `(start-window, duration-window)`, with `source` as a
  priority *tiebreaker`**, never source-first — mirroring Apple's overlap+priority
  resolution. (Schema-relevant now; the dedup *logic* is Phase 4 ingest.)
- **Any "~8k" figure is corrected to 4,096 tokens** wherever on-device chunking is
  designed.

## Consequences

**Good.** The enum admits every planned feed without a later `ALTER TYPE` per feed;
the dedup identity will actually collapse cross-source workout duplicates.

**Bad / flagged.** The workout dedup key is plumbing for a feed **that captures
nothing yet** — `public.workouts` is 0 rows and the July backup CSV was empty
(OQ-18). Whether workout capture exists at all is OQ-18 (open), and it gates whether
Phase 5/6 are measurable. Designing the identity now is correct; it does not create
the data.

**Deferred.** The transport contract — the Shortcuts-to-endpoint request shape,
idempotency key handling, offline queue — is Phase 3 and is **not** in this ADR.

## Alternatives considered

- **`(source + start + duration)` identity.** Rejected (correction above): it fails
  to collapse the cross-source duplicate that is the whole point.
- **A free-text `source` column instead of an enum.** Rejected: the closed enum is
  what lets a CHECK and the ingest path reason about provenance structurally.
