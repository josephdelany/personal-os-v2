# ADR-0132 — Every code-only requirement is proven; eight remain and all are one decision

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-CAP-032, 067..072, 087..092, 110, 111; REQ-INF-030, 204, 212, 218, 219
**Result:** **677 of 685 requirements proven (99%). Thirteen of fourteen prefixes complete.**
The remaining eight are REQ-INF-520..527 — all of them OQ-75.

## Vision asks for four things

REQ-CAP-068: names, a per-item confidence, a `portion_cue` string, a count. **Not grams, not
calories, not a serving size.** A vision model asked "how many grams" will answer, and **the
answer is a guess about a photograph's scale dressed as a measurement** — which REQ-NUT-041
already forbids from narrowing anything.

**Dictation beats vision on disagreement** (REQ-CAP-069), and the discarded value is kept. The
photo shows what was on the plate; the sentence says what Joe ate. **Those differ constantly and
predictably** — a shared dish, a plate he did not finish, something eaten before the photo. The
dictated value is a statement by the person who ate it; the vision value is a guess about a
picture of it.

**Extraction runs twice at 0.7** (REQ-CAP-072). A field that differs between two runs is one the
model was not sure about — **information its own confidence score does not reliably carry.**

**A model ID missing from the catalogue fails the run** (REQ-CAP-071), non-zero, rather than
falling back. **A model that has left the catalogue is a silent change in what the system
extracts, and a fallback makes that invisible exactly when it starts mattering.**

## Prompts are never random

REQ-CAP-087/090. **A prompt at a random time interrupts whatever is happening. A prompt fifteen
minutes before Joe's own median eating time arrives while he is deciding what to eat** — and that
difference is the difference between a notification he acts on and one he turns off.

The schedule uses the **median**, because one 02:00 kebab should not move the dinner prompt by
half an hour, and a mean would.

REQ-CAP-092 forbids SMS and email: **both are channels Joe reads for other reasons, and a capture
prompt arriving among them competes with things that matter more and loses.**

## Blinding is physical, not a matter of effort

REQ-INF-204. Most of Joe's exposures are behavioural — he knows whether he had caffeine. A
supplement in an identical capsule can be blinded, and **where it can be, it is not optional: an
unblinded supplement trial measures the supplement plus his expectation of it, and the expectation
is the larger of the two often enough to matter.**

REQ-INF-212 offers a **shorter block** rather than "try harder". A 20% deviation rate usually
means the block length does not fit Joe's life — **the fix is the design, not the discipline** —
and repeating the notification would make a design problem feel like a personal one.

## Interrupted time series, and its ceiling

REQ-INF-218 applies to a discrete one-off change on a **known** date. Without one, **the method
degenerates into searching for the best changepoint — which will always find one.**

The control series is **printed and vetoable**, because an ITS estimate is only as good as its
control and **choosing it is a judgement about Joe's life the system cannot make**: steps is a
reasonable control for sleep unless the thing that changed was his commute.

REQ-INF-219 caps it at CONFIRMED_OBSERVATIONAL. n=1, no randomisation, one intervention date —
**and a clean discontinuity is exactly when somebody would want to call it an experiment.**

## Where this leaves the backend

Every requirement that could be proven without Joe now is. The eight that remain are a single
decision:

> **REQ-INF-520: "The reasoning layer SHALL use NumPyro as its sole probabilistic programming
> language."**

`jaxlib` ships no macOS x86_64 wheel, so the Bayesian layer cannot be developed or tested on this
machine (ADR-0103 as amended). OQ-75 puts three options to Joe and recommends a hand-rolled Gibbs
sampler if the layer is wanted soon — the model REQ-INF-520..527 specifies is a hierarchical
linear model, which is exactly the case where that is straightforward and exactly checkable.

**That is the whole of the remaining requirement work.** Everything else outstanding is
deployment (one authorization), or a ruling, or a credential.
