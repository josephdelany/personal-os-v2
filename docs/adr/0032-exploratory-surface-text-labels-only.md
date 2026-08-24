# ADR-0032: The EXPLORATORY surface is text and labels only — no charts

## Status

Accepted

## Date

2026-08-24

## Context

RULE-17's SCOPE shell (ADR-0029) reversed the former "exploratory output never
reaches a screen": automated structure-discovery output (`CANDIDATE` tier —
PCMCI+, VAR-LiNGAM, regularized VAR) MAY now be displayed, carrying an explicit
`EXPLORATORY` label, on a tier-labelling surface that is built and proven before
any continuous exploration ships. Track-1.2 unit C-2 narrowed the prohibitions
(REQ-INF-402/403, REQ-TIER-035, the tier table, reasoning Scenario 4) to permit
that surface, leaving forward references to "the EXPLORATORY-labelled surface"
that Missing-F now defines.

The C-2 reviewer surfaced an open question: **is the EXPLORATORY surface
text/label-only, or may it render charts?** REQ-NAR-035 already forbids a chart
for a `CANDIDATE`-tier claim, so the two would need to agree.

The integrity risk RULE-17's core guards against is that exploratory output scored
**at chance** on the easy case (CausalDynamics, PCMCI+ AUROC ~0.52) yet is the most
seductive thing to over-believe. The display-format decision is where that risk is
won or lost.

## Decision

**The EXPLORATORY surface renders text and labels only. No charts.** The normative
enumeration and the positive whitelist (the surface emits only text and label render
components) live in REQ-TIER-050 — chart, plot, scatter, trend line, edge or network
diagram, heat map, or any other graphical encoding of a `CANDIDATE` relation may not
appear on it. This ADR is that requirement's rationale; REQ-TIER-050 is its canonical
statement.

**Rationale (Joe's ruling, on the record):** the entire risk RULE-17 guards is Joe
over-believing exploratory output that scored at chance. A chart is the most
persuasive format available — it makes a noise correlation look like a finding in a
way a sentence never does. Text forces the tier and the uncertainty to be read; a
scatter plot lets the reader skip them. So the surface that exists specifically to
display the *weakest* tier is the one place a chart does the most damage.
REQ-NAR-035 (no chart for a `CANDIDATE` claim) therefore stays coherent and
unchanged; this ADR extends the same logic from a single claim to the whole surface.

**Revisit trigger, recorded not silent:** once RULE-20's forward-prediction scoring
has an actual track record on exploratory items — i.e. once there is evidence about
how often these candidates survive — charts on the EXPLORATORY surface may be
reconsidered *with that evidence*. Not before.

## Consequences

**Good.** The weakest-evidence surface cannot borrow the credibility of a chart.
The tier and uncertainty are unskippable because they are the content, not a caption.
REQ-NAR-035 and the new Missing-F requirements agree by construction rather than by
coincidence. The revisit trigger ties any future loosening to RULE-20 evidence, so
the restraint is falsifiable, not dogma.

**Cost (named, not hidden).** A genuine exploratory pattern that a chart would make
legible (e.g. a lagged relationship across many variables) is harder to grasp as
text. That is the intended trade: legibility is exactly the persuasion this surface
must not have until the evidence earns it. If exploration later proves to surface
things worth seeing graphically, the revisit trigger reopens the question.

## Alternatives considered

- **Charts behind the EXPLORATORY label.** Rejected — this is the "friendlier name"
  laundering RULE-17's core and ADR-0029 already warn against; a labelled chart is
  still a chart, and the label is the part the eye skips.
- **No EXPLORATORY surface at all (keep the pre-reversal ban).** Rejected by ADR-0029
  — silence about a sub-threshold pattern is indistinguishable from never having
  looked, which is its own dishonesty (the RULE-18 logic). The surface exists; its
  format is what this ADR bounds.
- **Charts now, gated on a prominent uncertainty caption.** Rejected — the RCT-style
  evidence that a displayed number is itself an intervention (RULE-24) argues the
  caption is exactly what gets skipped. Text is the caption made unskippable.
