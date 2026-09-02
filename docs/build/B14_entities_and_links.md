# B14 — Entities and links: merchants resolved, meals ↔ charges ↔ places joined (migration 0052)

**What this is.** Phase 4 as promised by ADR-0004: `core.entities` stops being
shape-only. Finance §B (descriptor normalisation, the merchant and category cascades,
Joe's correction outranks everything) and §D.1 (the link object), plus REQ-ONT §B
(entity types), plus the Big Mac path's last joint: the meal, the charge and the place
become one linked event. One session.

**Requirement IDs satisfied:** REQ-FIN §B.1–B.4 IDs, REQ-FIN §D.1 IDs, REQ-ONT §B and §D
IDs (quote them), RULE-10, INV-2. **ADRs:** ADR-0060 (resolution cascade as built),
ADR-0061 (link predicates and the time windows).

## Migration `migrations/0052_entities.sql`
- `ALTER TABLE __CORE__.entities ADD CONSTRAINT entities_type_check CHECK (entity_type IN (<the closed list from REQ-ONT §B, verbatim>))` — applied as NOT VALID then VALIDATE after backfill.
- `config.merchant_rules (pattern TEXT, canonical TEXT, category TEXT, provenance TEXT)` — seed from the descriptor rules in §B.1/B.2 plus a DISCOVER over
  `SELECT merchant, count(*) FROM public.transactions GROUP BY 1 ORDER BY 2 DESC LIMIT 100` (paste the counts, never amounts) so the top 100 descriptors resolve on day one.
- `config.category_rules (merchant_canonical TEXT, category TEXT, necessity_default TEXT)` — the categorisation cascade §B.3.
- `core.entity_aliases (alias TEXT, entity_id UUID, provenance, confidence, recorded_at, supersedes)` — append-only.

## Resolution job — `tools/engines/resolve_entities.py`, hourly after extraction
Cascade exactly as §B.2: (1) Joe's corrections (`corrected_by_human` rows) → (2) exact
alias → (3) `config.merchant_rules` regex → (4) normalised descriptor (§B.1: strip
store numbers, city codes, card suffixes, `SQ *`, `TST*`, `AMZN Mktp`) → (5) trigram ≥
0.6 to an existing canonical → (6) new entity with `provenance='inferred'`,
`confidence` from the step that matched. Every atom of kind `transaction` gets a
`core.links` row `(subject_atom, predicate='paid_to', object_entity)`. Same cascade for
`site` (domain), `channel`, `exercise` (workout atoms: normalise "bench", "bench press",
"BP" → one exercise entity — seed from REQ-WKT's exercise vocabulary), `food`
(canonical food names from `foods_cache`), `place` (from `restricted.places` labels —
the entity carries the label only, never a coordinate).

## Links (ADR-0061) — `tools/engines/link.py`, same job
Deterministic, windowed, provenance `inferred`, never overwriting a human link:
- `transaction` at merchant M within [visit.arrive−15min, visit.depart+15min] of a visit
  at place P → `(transaction) at (place)`; and if M's category is food/drink →
  `(place) is_merchant (M)` once.
- `consume` atom within ±45 min of a food/drink `transaction` → `(consume) paid_by
  (transaction)`, confidence 0.7 (0.9 if the merchant's canonical name appears in the
  food evidence span).
- `workout` set atoms within a visit at a place of kind `gym` → `(workout) at (place)`.
- `consume` with ethanol > 0 within a visit at kind `bar` → `(consume) at (place)`.
Joe's corrections from THE DESK: `public.correct_link(p_link_id, p_action:'confirm'|'reject'|'retarget', p_target)` → a superseding link row with `corrected_by_human=true` (RULE-10).

## Envelope additions
`get_timeline` entries gain `links:[{predicate, label}]` (e.g. "paid_to McDonald's",
"at Planet Fitness"); `get_entity` gains `links_n` and `linked:[…top 10]`; `get_place`'s
`money_here` now reads links instead of the time-window join (one owner, RULE-11).

## Tests
```
test_REQ_FIN_B1_descriptor_normalisation_fixture_of_40
test_REQ_FIN_B2_cascade_order_and_confidence_per_step
test_REQ_FIN_B4_human_correction_outranks_every_later_automated_match
test_REQ_ONT_B_entity_type_check_rejects_unknown_type
test_ADR_0061_big_mac_path_links_meal_charge_and_place_end_to_end   (synthetic atoms in a rolled-back txn)
test_ADR_0061_links_never_overwrite_a_human_link
test_INV_2_entities_and_links_are_append_only
```

## Done when
Migration; job in the hourly workflow; DISCOVER counts pasted; resolution rate on the
live transactions table pasted as "{k} of {n} descriptors resolved, {m} new entities";
tests; ADR-0060/0061; PROGRESS + WHAT I DID NOT DO (no ML matching; places only from
registered labels).
