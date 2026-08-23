# ADR-0017: Non-response is a row — the prompt_dispatch table

## Status

Accepted

## Date

2026-08-23

## Context

When a scheduled prompt fires and Joe does not answer, that is a fact. A silent
gap ("no row") and a recorded non-response ("issued, not answered") are different,
and one cannot be reconstructed from the other. You cannot classify a missingness
mechanism (MCAR / MAR / MNAR) without the **denominator** — which prompts were
issued (Decision 3; mainstream, verified).

Two things this is **not**:

- It is **not** RULE-07 presence. RULE-07's `observed / observed_absent / unknown`
  is about the *value* of a fact. Prompt response is about the *lifecycle of a
  question*. Orthogonal axes; never one column.
- It is **not** two-valued. The literature distinguishes at least `delivered_unseen`
  (phone off/asleep), `seen_declined`, `partial`, and **`never_scheduled`**
  (planned missingness, MCAR by construction). Collapsing `never_scheduled` into
  `declined` would bias the missingness model.

**Citation note.** The supporting JMIR paper (DOI 10.2196/65350, "Within- and
Between-Individual Compliance in Mobile Health…") is **snippet-confirmed, primary
unreachable** — the JMIR page returned 403 to the verifier; title/DOI/argument
confirmed only via the search index and the accepted-preprint record. **The
decision stands on its own reasoning** (you cannot classify a missingness
mechanism without recording which prompts were issued), not on this citation.

## Decision

A dedicated `core.prompt_dispatch` table: one row per prompt **issued**, with
`subject`, `scheduled_for`, `delivered_at`, `responded_at`, and `response_state ∈
{pending, answered, seen_declined, delivered_unseen, partial, expired}`.
`never_scheduled` is the **absence** of a row for a slot the schedule defines — it
is derivable and needs no row. `subject` supports RULE-27's "one prompt per subject
per day" limit. Shape locked this phase; wired when prompts exist (Phase 3+).

## Consequences

**Good.** Joint missingness modelling becomes possible: the issued/answered
denominator is recorded, so a compliance model can separate "did not see" from
"declined." RULE-27's rate limit has the data it needs.

**Bad.** Every scheduled prompt now writes a row whether answered or not — expected
and desired, but it is write volume against the 500 MB ceiling (OQ-20), to be
watched.

## Alternatives considered

- **A `responded BOOLEAN` on an existing check-in row.** Rejected: cannot
  represent delivered-unseen vs declined, and has no row at all for an unanswered
  prompt — exactly the denominator that is needed.
- **Folding response state into RULE-07 presence.** Rejected: different axis;
  merging biases both.
