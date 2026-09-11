# ADR-0138 — The USDA FoodData Central client, and one meter for one key

**Status:** accepted
**Date:** 2026-09-11
**Requirements:** REQ-NUT-005, 006, 007, 008, 009, 012, 013, 014, 016, 017, 019, 024, 025,
030, 031, 032, 034
**Completes:** ADR-0106's "What remains" and ADR-0137's two `UnconfiguredLeg` placeholders.
**Amends:** ADR-0106 — one of its two stated blockers was already resolved. See *Correction*.

## Context

ADR-0137 put the cascade on the execution path and left two of its four legs as
`UnconfiguredLeg` — a class whose entire behaviour is to raise `NotConfigured`. `usda_branded`
and `usda_foundation` have been the first and second *reference* sources in
`SOURCE_PRECEDENCE` since ADR-0106, which means that until now the cascade's own ordering
argument — a manufacturer's label outranks a crowd transcription — described a preference the
system could not act on. Every branded item that Open Food Facts did not know was unresolved,
and the reason was never about the food.

The requirement ledger did not show this. All seven USDA requirements were *named* by passing
tests before this session:

| requirement | what its test asserted, before | against what |
|---|---|---|
| REQ-NUT-005 (store the `fdcId`) | a row with no `fdc_id` is refused | `ontology_contract.usda_row` |
| REQ-NUT-009 (900/hour, then defer) | `usda_budget(900)["defer"] is True` | `ontology_contract.usda_budget` |
| REQ-NUT-012 (429 stops the source) | cooldown arithmetic with stub sources | `nutrition_cascade` |
| REQ-NUT-013 (brand token in the query) | a brand token settles an ambiguity | `nutrition_off` |
| REQ-NUT-014 (`labelled` + brand owner) | the cascade raises without a brand owner | `nutrition_cascade` |

Not one of them was false, and not one of them was about a USDA client, because there was no
USDA client. `ontology_contract` is a contract module — it exists to be asserted against, and
NEXT_SESSION already names that category. The gap it leaves is the one this ADR closes: a rule
stated in a contract module and a rule enforced in the code that issues requests are two
different artefacts, and only the second one rations anything.

## Correction to ADR-0106

ADR-0106's "What remains" gave two blockers: no api.data.gov key, and *"under RULE-29 that
egress target also needs recording before first use."*

**The second was already satisfied when it was written.** Migration 0050 creates
`config.egress_allowlist` and inserts `api.nal.usda.gov` in the same statement, with the note
"USDA FoodData Central; free API key, no personal data in the request". RULE-29's recording
requirement has been met for as long as the table has existed.

This matters beyond tidiness: the sentence made the client look blocked on a governance step
that had already happened, and a blocker nobody re-checks is indistinguishable from a real one.
Only the credential is outstanding.

## Decisions

### 1. A separate module, sharing what is genuinely shared

`tools/engines/nutrition_usda.py`, not a branch inside `nutrition_off`. Open Food Facts is
crowd-sourced, keyless, rationed per minute, and reports a flat `nutriments` dict keyed by
name; FoodData Central is authoritative, keyed, rationed per hour, and reports a *list* of
records keyed by numeric nutrient id, in two different shapes depending on the endpoint. A
shared parser would be a function whose every branch asks which source it is reading.

What the two genuinely share is imported rather than copied: the physical per-100 g ceilings
(`nutrition_off.CEILING_PER_100G`, promoted from a private name) and `insert_cache_row`. Those
are facts about matter and about one `ON CONFLICT` clause respectively, and two copies of
either could drift apart without any test noticing.

### 2. One meter for one key — the decision with the most consequence

REQ-NUT-009 says *"the count of USDA FDC requests"* and REQ-NUT-012 says *"stop issuing USDA
requests"*. Neither says "Branded requests". api.data.gov meters the **key**, and one key
serves both datasets, so the quota and the 429 cooldown are held in a single `Quota` object
shared by both legs.

The alternative — a limiter per leg, which is what `nutrition_off`'s per-endpoint `Limits`
looks like and would have been the easy symmetry — permits **1,800 requests an hour against a
key metered at 1,000**, and lets a 429 on Branded be followed immediately by a Foundation
request against the same throttled key. The failure mode of a banned key is every future item
unresolved, so the polite behaviour is also the cheap one.

A consequence worth stating plainly: when the shared quota is exhausted or tripped, **both**
USDA legs report `rate_limited` and the cascade walks on to Open Food Facts. The item's
`tried` record distinguishes our own ceiling (`REQ-NUT-009 hourly quota`) from the provider's
refusal (`REQ-NUT-012 provider 429`), because only one of those means the key is at risk.

### 3. The relevance ranking is discarded; an exact match is required

FDC's `/foods/search` returns something for almost any query, ordered by a score this system
cannot audit or reproduce. Taking `foods[0]` would let the same query resolve to a different
food on a different day, with no signal that anything had changed.

So `select_exact_match` requires the description — and, for a branded query, the brand — to
equal the query after normalisation. No exact match is `UsdaNotFound`; several *distinct*
`fdcId`s are `UsdaAmbiguous`, which is REQ-NUT-025's case and Joe's to settle. The same
`fdcId` returned twice is one food listed twice, not an ambiguity.

### 4. REQ-NUT-008's TTL is keyed on the dataset, not on our bucket

Branded expires at 365 days because a manufacturer can reformulate a product without renaming
it. Foundation and SR Legacy never expire because a laboratory analysis of a generic food is
not superseded by time. `needs_refetch` therefore consults FDC's own `dataType` when it is
available and falls back to the cascade source name only when it is not — SR Legacy sits in
our `usda_foundation` bucket and must not inherit Branded's TTL by association.

### 5. Failures do not collapse

Five outcomes stay distinct all the way to `unresolved_items`, because they lead to different
actions and only some of them are about the food at all:

| outcome | reason | reaches Joe's review list? |
|---|---|---|
| no api.data.gov key | `no_source_available` | **no** — an operations problem |
| our quota exhausted / provider 429 | `no_source_available` | **no** — retry, not a question |
| asked, nothing matched | `no_source_match` | yes |
| asked, several matched | `no_source_match`, with `ambiguous_exact_match` in `tried` | yes |
| asked, record unreadable | `no_source_match`, with `no_readable_nutrient` | yes |

A missing key reported as `no_source_match` would hand Joe a review list of foods to answer a
question about an environment variable.

### 6. Nothing is coerced, clamped or inferred

A nutrient in an unrecognised unit is **dropped with its reason**, not assumed to be in the
expected one — sodium stated in grams and read as milligrams is a thousand-fold error that
looks like an ordinary number. A value past a physical ceiling is dropped, never clamped
(RULE-01: a clamped value is a fabricated one). A serving stated in millilitres yields **no**
serving mass, because the density is not published and water is a guess. Energy converted from
kJ records that it was converted. `labelNutrients`, FDC's per-serving block, is never read.

## What this does not establish

**No request has been issued to api.data.gov.** Every behaviour above is exercised through an
injected transport against payloads the tests construct. The client is *implemented* and
*tested*; it is not *deployed* and not *observed*, and those four statuses stay apart.

The live check needs `USDA_FDC_API_KEY` (or `PERSONAL_OS_USDA_API_KEY`) from
<https://api.data.gov/signup/> — free, and no personal data is required to register. Until then
`build_sources` substitutes `UnconfiguredLeg` carrying that instruction, which is the same
outcome as before this ADR for a smaller and more accurate reason.

One further guard is deliberate: even **with** a key, no live request is issued when
`PERSONAL_OS_TEST_SOCKET` names a disposable server and no transport was injected (RULE-01,
ADR-0082). A request is real whatever the database is, it would spend one of the 900 slots, and
it would drop a live third-party payload into a rolled-back fixture.

### 7. REQ-NUT-017 — the review list stops being write-only

Found while auditing what the USDA legs left uncovered, and fixed here because it is the same
loop: `record_unresolved` filled `core.unresolved_items` every night and **nothing could ever
resolve a row**. There was no path from Joe's answer back into `foods_cache`, so the same item
was re-asked, re-refused and re-listed indefinitely. RULE-10 says a human correction
permanently outranks a guess, and `lookup_cached` already orders by `SOURCE_PRECEDENCE` with
`joe` first — but nothing wrote the row that ordering exists to prefer.

`nutrition.accept_correction` performs REQ-NUT-017's three writes together: the `joe`
`foods_cache` row, its alias (REQ-NUT-004), and `resolved_at` / `resolved_by = 'joe'` on the
item. No migration was needed; `unresolved_items` has carried `resolved_by CHECK (... IN
('joe','later_source'))` since 0050.

Two guards, because this is **the one place a nutrient value enters from outside a source**:

- `supplied_by` is mandatory and must be `joe`. RULE-09 keeps models from supplying figures,
  and REQ-NUT-017's permission is for a person; a call site that cannot name one cannot use
  the function. Nothing on a model-facing path calls it.
- A supplied value past a physical ceiling is **refused whole**, not dropped field-by-field as
  a source payload is. A typed `3000` where `300` was meant would enter as a `joe` row — the
  one source nothing outranks — and stay wrong until Joe noticed. A source record with one
  unreadable field is still worth keeping; a person's answer with a rejected field is a
  question that can simply be re-asked, and the item stays open so it will be.

### 8. What was checked and is NOT a defect

`analysis.legacy_daily.kcal` (migration 0026) is a scalar energy column and looks like a
REQ-NUT-030 violation. It is not: it sits beside `hrv`, `rhr`, `steps` and the sleep columns
in an Apple Health daily series, so it is energy **expenditure** measured by a device, not a
food-derived intake estimate. REQ-NUT-030 governs the storage of nutrition estimates, whose
uncertainty is asymmetric and whose point value is directionally misleading. Recorded here
because the next person to grep for a scalar `kcal` will find it too.

## Consequences

- The two reference legs of `SOURCE_PRECEDENCE` can answer for the first time, so ADR-0106's
  ordering argument now governs behaviour rather than describing an intention.
- REQ-NUT-005/009 gain an implementation behind contracts that previously had none;
  `tests/test_nutrition_usda.py` binds `REQUESTS_PER_HOUR` to
  `ontology_contract.USDA_HOURLY_CEILING` so the rule and its enforcement cannot diverge.
- `nutrition_off.CEILING_PER_100G` and `MACRO_SUM_CEILING` are now public. Nothing else moved.
- `tools/nutrition_acceptance.py` runs the seven acceptance cases end to end against a
  disposable server and prints what happened, so the claim can be checked by running one thing.
- **No REQ-NUT requirement is now evidenced only by `ontology_contract`.** Before this change
  five were (005, 007, 009, 017, 030/031/032 in part); every one now has at least one test
  against code that runs on the execution path. That is a smaller claim than "proven" and a
  larger one than the ledger previously supported.
- **Still open, and not this worker's to change:** REQ-NUT-004's `food_aliases` table does not
  exist in migration 0050, so an alias is written as a second `foods_cache` row keyed on the
  same `(source, source_id)`. It works and it is liftable by one mechanical migration over
  `raw ? 'alias_of'`, but a re-fetch under REQ-NUT-008 must update both rows. Migrations
  belong to the main session; the proposal is in the session record.
