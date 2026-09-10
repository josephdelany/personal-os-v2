# ADR-0099 — The tier vocabulary linter, and the two false positives that would have silenced it

Status: accepted (`tools/engines/narration.py`; no migration, no production write)
Date: 2026-09-09
Requirements: REQ-NAR-020..023, REQ-TIER-020, RULE-19, RULE-23.

## What it enforces

A tier is a claim about how much is known, and **vocabulary is how a tier leaks**. "Steps were
typically a four-figure daily step count" and "steps increase HRV" can rest on identical evidence; only the second
asserts something that evidence cannot carry. The tiers are enforced in the data all the way
down, and then one verb undoes it.

`lint(claim, tier, vocabulary)` returns the terms in a claim that are reserved for a tier
**above** the one assigned. `config.tier_vocabulary` is a set of per-tier allow-lists, so the
linter ranks the tiers and asks whether anything from a higher rank appears. A term from a
*lower* tier is fine — a confirmed finding may still say "was", and reserving downward would
forbid plain language at exactly the tiers that have earned it.

## Two false positives, either of which would have made it useless

**The month of May.** "may" is EXPLORATORY vocabulary. A DESCRIPTIVE answer reading "over
1 May to 30 May" contains it twice, and a case-insensitive match discards a *correct* answer
and writes a violation row about it. A linter that silences true statements is worse than none,
because the failure is invisible and reads as reticence. Terms that are also ordinary proper
nouns are matched in **lower case only**.

**The preposition "on".** Run against the live templates, the linter flagged exactly one breach:
the INSUFFICIENT copy "There is not enough data **on** {display}", because "on" appears in
DESCRIPTIVE's list as scaffolding for "highest on Tuesday". REQ-NAR-021 reserves "a **verb or
qualifier**", and a preposition is neither. A tiny structural list is excluded, and it is
deliberately only prepositions — "per" stays a reservation, because a rate word carries a claim.

With both handled, the live templates produce **zero breaches** and zero moralising terms.

## The finding underneath

`config.tier_vocabulary` has **no row for INSUFFICIENT**. Five tiers carry vocabulary and the
bottom one carries none, so under the reservation reading every term in the table is above it.
The live refusal templates pass today only because they happen to use structural words — luck,
not design. Recorded as OQ-62 with a recommendation, because whether refusals should be
governed as tightly as claims is a decision, not an implementation detail.

## Pure, and reading the table

No database and no hardcoded vocabulary: REQ-TIER-020 requires the linter to read
`tier_vocabulary` rather than a list in code, so the table is passed in. An unknown tier raises
rather than defaulting to the bottom — defaulting would silently permit every term.

## Not done

Wiring the linter into the render path so REQ-NAR-021's "discard the string, emit the
deterministic template, write a `render_violations` row" happens at runtime. That is a call
site, and today nothing generates a non-template claim string: no model narrates yet. The
build-time half (REQ-NAR-022) is what has something to check.
