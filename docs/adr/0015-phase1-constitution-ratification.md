# ADR-0015: Phase-1 constitution ratification (Gate 1)

## Status

Accepted. This is the Gate-1 record: Joe reviewed all 31 rules
(RULE-00..RULE-30) and ruled on each. All 31 are **kept**. Two carry amendments
(RULE-19, RULE-30). The three doctrine-reversing rules (RULE-18, RULE-23,
RULE-30) were affirmed explicitly, as ROADMAP Gate 1 requires.

## Date

2026-08-23

## Context

ROADMAP Phase 1 is Joe reading the constitution and ruling on every rule, because
every later extraction decision depends on it. The review ran in batches; for
each rule Joe received its plain-English meaning, its cost to him, and a
recommendation. RULE-13/14 had just been changed by ADR-0014 (temporal-spec rule
added; old render rule merged); RULE-11/17/29 had just been corrected/strengthened
(ADR-0014, ADR-0013). Joe ruled on the current text of each.

## Decision

**All 31 rules kept.** Enforcement tiers and the 30-rule cap are unchanged.

**Reversals affirmed explicitly (Gate-1 requirement):**
- **RULE-18** (`INSUFFICIENT` is returnable/displayable — reverses the old
  silence doctrine): affirmed. "Silence to a question I actually asked is a
  hidden null, and a hidden null is a lie by omission." No text change.
- **RULE-23** (a money surface exists but never moralises — reverses "not a
  budget app"): affirmed. The no-moralising guard "is not a politeness
  convention — it is the mechanism": the evidence that precise spend feedback
  raises spending $32–40 is *why* the guard exists. No text change; the guard
  must never soften (no "excessive"/"wasteful"/"you should have").
- **RULE-30** (Shortcuts own media capture; `getUserMedia` fails the build):
  affirmed and amended (below).

**Amendment 1 — RULE-19.** The pre-registration cost (nothing in the pre-existing
~two years can ever become a *confirmed* finding from that same data) is turned
into an advantage rather than merely tolerated: the exploratory pass over the old
data runs **once, early**, emitting a written register of pre-registered
hypotheses with adjustment sets, lags, and windows fixed and stamped before any
new data accumulates. The waiting clock starts day one, and the old data does the
job it is good for — generating hypotheses, never confirming them.

**Amendment 2 — RULE-30.** Records the revisit trigger (if WebKit 215884 is fixed
in iOS 19+, the rule is re-opened, not silently kept) and strengthens the
rationale beyond "bug workaround": Apple's on-device Foundation Model is reachable
from Shortcuts with structured output and no developer account, and on-device
SpeechAnalyzer beats Whisper (14.0% WER at 70× realtime). Shortcuts-owned capture
is free, private, offline, and better — advantages that survive the bug fix, so a
future session must weigh them rather than reverse the rule reflexively.

## Consequences

- Gate 1 passes: every rule has an enforcement tier and an owner, and the three
  reversals are explicitly accepted.
- RULE-19's one-time exploratory pass becomes a concrete Phase-6 deliverable (the
  hypothesis register authored before results are seen — it aligns with ROADMAP
  Phase 6's "hypothesis library re-authored before any results are seen").
- RULE-30 carries a live revisit trigger tied to an external event (iOS 19 /
  WebKit 215884); a future session that sees the bug fixed must re-open, not
  auto-keep.
- No rule was added or removed here, so the 30-cap is untouched.
