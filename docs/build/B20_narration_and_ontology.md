# B20 — Narration restraint (REQ-NAR) and the closed ontology (REQ-ONT) (migration 0062)

**What this is.** Two spec files that are mostly *constraints* rather than features,
made enforceable: §I of the reasoning spec (the language layer's permitted surface,
numeral-template rendering, the per-tier vocabulary linter, degradation without the
LLM, rendering a recommendation) and `specs/05-ontology/requirements.md` (the closed
`atoms.kind` and `entity_type` taxonomies, controlled vocabularies, identity and trace).
One session.

**Requirement IDs satisfied:** REQ-NAR-001..029 (all), REQ-ONT-001..017 (all),
REQ-TIER-020/021/022/052, RULE-15, RULE-24. **ADRs:** ADR-0074 (the render pipeline
as the single exit for every sentence), ADR-0075 (ontology CHECKs frozen; the 0014
ontology checks completed).

## Narration — `lib/render.py`, the single exit
Every sentence any surface or job emits (`get_*` templates, `ask`, recommendations,
brief notices, `sentence` fields) passes through one function
`render(template_id, slots, tier, result) -> str`:
1. **Templates live in `config.templates (template_id, tier, text, slot_spec)`**
   (REQ-NAR-011); slots are filled only from `result`; a slot whose value is absent
   renders the template's declared absent form, never a placeholder.
2. **Numeral verification** (REQ-NAR-012/013): every numeral in the output must equal a
   `result` value or its registered rounding (`config.domain_metrics.rounding`,
   REQ-NAR-015); failure → discard, `render_violations`, fall back to the template's
   deterministic minimal form.
3. **Units** (REQ-NAR-014): every numeral is followed by its unit; a numeral without a
   unit in `result` cannot be rendered.
4. **Vocabulary linter** (REQ-NAR-020, REQ-TIER-020/052): the output is tokenised and
   checked against `config.tier_vocabulary` for its tier: causal verbs (`causes`,
   `increases`, `drives`, `leads to`, `because`) only at CONFIRMED/EXPERIMENTAL
   (REQ-TIER-021); `predictive_lead` never `granger` (REQ-TIER-022: also a repo grep in
   `validate_layout`); judgment words (RULE-24's list: good/bad/too much/should have/
   streak/score) never; a hit → violation row + fallback.
5. **Degradation** (§I.4): the language layer is optional; `render` never calls a model;
   the SQL RPCs keep their own template copies *generated from* `config.templates` by a
   build step (`tools/gen_sql_templates.py`) so there is one source (RULE-11).
6. **Recommendation rendering** (§I.5): the B10 templates move into `config.templates`
   with tier-gated verbs from `config.controllable_metrics`.
The SQL side gets `public._render(template_id, slots jsonb)` implementing 1–4 in plpgsql
for the RPCs that must work without Python (RULE-15). Both implementations are tested
against the same fixture of 60 (template, slots, expected) cases (RULE-11 parity test).

## Ontology — migration 0062
- `ALTER TABLE __CORE__.atoms ADD CONSTRAINT atoms_kind_check CHECK (kind IN (<the closed
  list from REQ-ONT §A, verbatim>))` NOT VALID → DISCOVER the live distinct kinds
  (`SELECT kind, count(*) FROM core.atoms GROUP BY 1`) → any kind outside the list is an
  ADR-0075 decision (map it or extend the list by ADR, never silently) → VALIDATE.
- Same for `entities.entity_type` (B14 added it; verify) and the controlled vocabularies
  of §C (`estimate_method`, `presence`, `provenance`, `unit` list, `value_type` list) as
  CHECKs or lookup tables in `config.vocab (domain, term)`.
- §D identity and trace: a test that every atom's `raw_capture_id` resolves and every
  derived_measures row's `n_inputs` > 0 with `window_from/to` set.

## Tests
```
test_REQ_NAR_011_slots_only_from_result
test_REQ_NAR_012_013_untraceable_numeral_falls_back_and_logs
test_REQ_NAR_014_numeral_never_without_unit
test_REQ_NAR_015_only_registered_rounding
test_REQ_NAR_020_vocabulary_lint_per_tier_fixture_of_60
test_REQ_TIER_021_causal_verbs_only_at_confirmed
test_REQ_TIER_022_granger_absent_from_repo
test_RULE_24_judgment_words_never_rendered
test_RULE_11_python_and_sql_render_agree_on_60_cases
test_REQ_ONT_A_atoms_kind_is_closed
test_REQ_ONT_B_entity_type_is_closed
test_REQ_ONT_C_controlled_vocabularies_enforced
test_REQ_ONT_D_every_atom_traces_to_a_capture
```

## Done when
`lib/render.py` + `public._render`; every existing `sentence` producer refactored to use
them (list them in PROGRESS with the diff); migration validated; tests; ADR-0074/0075;
PROGRESS + WHAT I DID NOT DO.
