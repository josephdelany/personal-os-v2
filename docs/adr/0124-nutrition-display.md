# ADR-0124 — A calorie count is the most confidently wrong number this system can produce

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-NUT-018..027, 041..053, 062..065
**Implements:** B12 §D.4, §D.4a, §E.3, §G.1. Thirty requirements. REQ-NUT now stands at 51 of 60.

## The premise

A calorie figure is assembled from **a food someone identified from a sentence, a portion nobody
weighed, and a database entry for something similar** — and then rendered as *"1,847 kcal"*, which
reads like a measurement.

So the interval *is* the value, and a point is never shown alone. This is not hedging: **the
honest width of the estimate is the most informative thing about it.**

## The four rules that carry the section

**Bounds sum separately** (REQ-NUT-043). The day's low is the sum of the lows. Summing the points
and putting a band around them would understate the width, because **the errors here are
systematic — portion sizes drift the same direction all day — not independent, so they do not
cancel.**

**Rounding may never narrow** (REQ-NUT-049). 1,847.4–2,103.6 → 1,847–2,104 is fine. → 1,850–2,100
removes 7 kcal of honest uncertainty for tidiness, and every such rounding along the chain removes
a little more. The low floors and the high ceils.

**Vision confidence may never narrow an interval** (REQ-NUT-041). The model's per-item confidence
is about **identification** — how sure it is that this is a bagel. The interval is about
**quantity**. A confident identification says nothing about how big the bagel was, and letting it
narrow the interval **converts one kind of certainty into another it has no bearing on.**

**Visual weight follows the method, never the magnitude** (REQ-NUT-045). Weighting by magnitude
makes a big number look more certain than a small one, **when the opposite is usually true.**

## When the interval is wider than the question

REQ-NUT-047. A day logged by voice routinely has a 500 kcal width. Reporting a 300 kcal deficit
against it is **reporting a difference the data cannot see — and the number would be believed.**
So the system says, in plain words, that this day's logging cannot resolve that difference.

## Vagueness gets no fraction

REQ-NUT-053. *"Most of a burrito"* is not 0.75 of one. Assigning a fraction would **invent a
number and carry it through a whole day's total — the figure Joe actually reads.** An *explicit*
fraction ("half") does resolve: the rule is about vagueness, not about fractions.

Likewise REQ-NUT-051: with no per-serving gram weight from the Branded record, the count stays
**unconverted**. There is nothing to multiply it by, and inventing a serving weight would put a
guess in the same column as a label.

## The two words this section refuses

**"Deficiency"** (REQ-NUT-064) is a clinical term with a clinical meaning, and **a low logged
intake is a fact about the logging at least as often as about the eating.**

**"Over budget" / red / pass-fail** (REQ-NUT-048) — the judgment framings. An unresolved item is
likewise **a normal outcome, never a failure state** (REQ-NUT-027): shown as a failure it reads as
something Joe did wrong; shown as a normal outcome it reads as a question he can answer, which is
what it is.

## Verification

20 tests. Requirements proven 509 → 532 (78%); REQ-NUT unproven 30 → 9.
