# ADR-0090 — Descriptor normalisation and the merchant resolution cascade

Status: accepted (migration 0057 prepared, NOT applied)
Date: 2026-09-09
Requirements: REQ-ONT-005/006, REQ-FIN-060..062, REQ-FIN-070..074, RULE-06, RULE-10, INV-2.

## Why this is the critical path

B14 is the widest dependency in the plan. It blocks `spend`'s merchant and category contract
(M2's last unmet operation), entity/correction precedence and meal-charge-place (M4), and
reconstruction case R1. This ADR covers B14.1 — normalisation and merchant resolution. Links
(ADR-0061's predicates and windows) are B14.2.

## The spec overrides the brief in two places

1. **The threshold.** The B14 brief proposes trigram similarity ≥ 0.6. REQ-FIN-072 names
   `difflib.SequenceMatcher` and **0.80**, and the requirement wins. The difference is not
   cosmetic: trigram similarity on short strings scores a substring near 1.0 — the same
   artefact that sent "sleep" to "Asleep (unspecified)" in ADR-0089 — which is precisely
   wrong for merchant names, where one is frequently a prefix of another.
2. **The migration number.** The brief says `0052_entities.sql`; 0052 is the neuron ledger and
   is live. Reserved from Git as 0057.

## No personal data in the repository

The brief proposes seeding the pattern table from Joe's top 100 descriptors. A merchant
descriptor is an observation about Joe — where he was, what he bought — and this repository is
public. The migration is shape and rules only; patterns and the city vocabulary are discovered
at run time into the database, the same treatment the source inventory's counts get (ADR-0088).

## The cascade, and why its order is not negotiable

Human correction → exact pattern → regex by descending specificity → fuzzy ≥ 0.80 →
provisional. Each step is strictly more speculative than the one before, and **no step runs
once an earlier one has answered**. That property is what makes the stored `merchant_source`
meaningful rather than decorative: without it a fuzzy guess can overrule an exact rule and
nothing in the row would show it.

Two consequences are enforced in the schema rather than trusted to the resolver:

- **`provisional_has_no_confidence`.** REQ-FIN-073's provisional merchant carries no number,
  because a number there is read downstream as evidence and there is none.
- **The RULE-10 precedence trigger.** The resolver may revise itself; it may not supersede
  Joe. Without it the next hourly run reverts every correction he ever made and the ledger
  presents that as an improvement.

REQ-FIN-073 also forbids writing the provisional descriptor into `merchant_patterns`. That is
the subtle one: doing so would make the next identical descriptor resolve as `pattern_exact`
at confidence 1.0 — a guess laundered into a fact, with no record that it ever was one.

## The city problem, solved by discovery rather than by a guess

REQ-FIN-060 requires stripping "trailing city and two-letter state codes". The state is a
regex. The city is not: "OAKLAND" is one token and "NEW YORK" is two, and a gazetteer is a
dependency this project will not take for one field.

So the city vocabulary is **learned from Joe's own descriptors**: a token that appears as the
last word after **four or more distinct merchant prefixes** is a location; one that follows a
single merchant is part of its name. "HOUSTON" follows a fuel station, a supermarket and a
pharmacy; "GARAGE" follows only Joe's Garage. The threshold is a count of distinct prefixes —
not a similarity, not a model judgement — so the result is reproducible and inspectable, and
`config.location_tokens` refuses a row with fewer than four.

Thin input learns nothing rather than producing a confident-looking guess, and a descriptor
that is *only* a city is never stripped to empty: that would turn an unresolvable descriptor
into a merchant named "" (RULE-06).

## REQ-ONT-005 answers OQ-16, at least for entities

OQ-16 records the entity-type taxonomy as lost with the ontology spec. It is not lost:
REQ-ONT-005 gives the closed six — `merchant`, `place`, `food`, `person`, `media_channel`,
`website`. The constraint is added `NOT VALID` because `core.entities` is append-only, so a
pre-existing out-of-taxonomy row cannot be edited into compliance and must not block the
constraint protecting every future row. Validating it is a separate, reversible decision once
the existing rows are known clean.

## Not done here

Category resolution beyond the table shape, the link engine (B14.2), and applying 0057.
