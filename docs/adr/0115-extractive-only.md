# ADR-0115 — The extractive-only contract: the model may point, not add

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-CAP-050..066, 108, 109 (§C.1, §C.2, §C.3)
**Adds one dependency:** `dateparser`, named by REQ-CAP-064.

## The contract

**The model may point at the transcript. It may not add to it.**

That needs enforcing rather than prompting, because a model asked for the calories in *"a bagel
and cream cheese"* will answer — fluently, plausibly, and wrongly in a way nobody can see. Three
guards, deliberately failing differently:

1. **REQ-CAP-052 keeps the words out of the schema**, so the model is never invited to produce
   them. Checked on field *descriptions* as well as names: the invitation is in the description
   as much as in the name.
2. **REQ-CAP-053 asserts `transcript[start:start+len(evidence)] == evidence`.** This is the
   load-bearing check, and its virtue is that it is a **string comparison, not a judgement**. A
   model that invents an item invents its evidence span too, and the invented span will not be at
   that offset.
3. **REQ-CAP-056 strips any calorie or macronutrient number at the adapter boundary**, before a
   row exists — and explicitly *not* at reduced confidence. **A stored number with low confidence
   is still a stored number, and confidence decays out of a reader's memory faster than the
   digits do.**

On a span mismatch the **value is discarded**, not flagged (REQ-CAP-054). A span that does not
match means the model pointed at text that is not there, and nothing it said about that field
survives.

## The label that would have quietly broken the guard

REQ-CAP-065: when `dateparser` cannot resolve a temporal span, the event time falls back to
`captured_at` and the provenance is **`defaulted`** — not `inferred`.

That distinction is the whole guard. **REQ-CAP-062 excludes `defaulted` from statistics and does
not exclude `inferred`**, so labelling the fallback `inferred` would let a substituted timestamp
into a trend as though it had been measured. The requirement's own text records a reviewer
catching exactly that in an earlier draft. It is an easy mistake to repeat and the label here is
chosen deliberately.

**The fallback is a common path, not an exotic one.** Measured on 2026-09-10: `dateparser`
returns `None` for both *"this morning"* and *"last Tuesday"* — two of the most natural things to
say into a voice capture. A test pins that, so if the library improves the test will say so.

## `dateparser`, installed before it was adopted

0.3 MB, pure Python, BSD, no service, no account, no runtime network call. Four small pure-Python
transitive dependencies.

Installed and exercised locally **before** this ADR was written, which is the amendment ADR-0103
earned: *a dependency ADR written from package metadata is a plan to add a dependency, not
evidence that it can be added.* Added to `analysis.yml`'s `resolve` job, pinned.

## The rest

**The profile set is closed and an unknown subject routes to `note`** (REQ-CAP-108), rather than
raising. An un-profiled extraction is the failure the requirement names, and a capture about
something nobody anticipated should still be **kept**.

**Quarantine after two retries, never a partial write** (REQ-CAP-055). A response that failed
validation three times is one nobody understands, and writing the half that parsed would put
unvalidated values in the same table as validated ones with nothing to tell them apart.

**The render treatment is returned as data** (REQ-CAP-061), so a surface cannot render an
inferred value identically to a measured one *by omission*.

**`statistical_inclusion` offers both branches** REQ-CAP-062 allows — exclude, or include with a
stated count. What it does not offer is including them silently.

## Verification

21 tests, no network and no model call: the model's response is passed in, and what comes back is
what may be written. Requirements proven 350 → 367 (54%); REQ-CAP unproven 83 → 66.

Not claimed: no extraction service is wired. This is the contract that will bind one.
