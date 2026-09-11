# Worker 2 — finish nutrition (B12)

Worktree `/Users/default/PERSONAL_OS_V2_nutrition_finish`, branch `work/nutrition-finish`,
created from `48745d9` (clean). Integration owner: Session 1 (main). Read `AGENTS.md`,
`CLAUDE.md`, `docs/CONSTITUTION.md`, `docs/NEXT_SESSION.md` and `docs/build/B12*.md` first.

## You own these files. Nobody else edits them.

- `tools/engines/nutrition.py`, `nutrition_off.py`, `nutrition_cascade.py`, `nutrition_display.py`
- `tools/resolve_nutrition.py` and any new nutrition CLI
- `tests/test_nutrition*.py`

## You do NOT own

Migrations (main allocates every number — **ask, do not pick one**), `lib/egress.py`,
`lib/db.py`, workflows, `tools/engines/ontology_contract.py`, anything reconstruction.

## Where B12 actually stands

Built and tested: the OFF parser (four distinct failure outcomes), and the five-step cascade
(`nutrition_cascade.py`, 16 tests, ADR-0106) where each source is a callable the caller
supplies — so ordering, refusals and brand rules are tested with no API key and no socket.

**The honest gap:** `SOURCE_PRECEDENCE` had been declared as a constant and never used. Check
your work against that failure mode specifically — a declared ordering that nothing reads is
documentation, not behaviour.

## The objective, in priority order

1. **`tools/engines/nutrition_display.py` has no caller** (measured at `48745d9`: it is one of
   28 required runtime capabilities with nothing invoking it). It covers B12 §D.4/§E.3/§G.1 —
   quantity conversion, vernacular portions, interval rounding, daily totals, the deficit
   statement. Connect it through the nutrition CLI so a real question gets a real answer.
   Tests must enter through the **supported command** and assert stored or returned behaviour;
   a pure-helper test does not establish acceptance.
2. **`food_aliases` (REQ-NUT-002/004) and `portion_aliases` (REQ-NUT-018) exist in no migration**,
   so the alias write REQ-NUT-004 requires has nowhere to land. Specify the exact DDL you need
   and **request a migration number from main.** Do not create one.
3. `ops.rate_limits` does not exist, so REQ-NUT-011 across concurrent runs is unmet — `Limits`
   is per-process only. Same rule: specify, request the number.

## Blocked, and not your fault — do not work around it

- **The USDA legs need Joe's api.data.gov key.** The cascade is built; the HTTP clients are not
  runnable. Do not stub a key, do not fabricate a response, do not mark REQ-NUT-001 proven.
- A serving declared in millilitres leaves `serving_g` NULL. Millilitres to grams is a density
  and **this system has measured none.** Do not invent one; NULL is the correct answer.

## Constraints

- Personal data may leave only to Supabase, Cloudflare Workers AI and originating APIs
  (RULE-29). Every outbound model call is logged. Use `lib/egress.py`; do not bypass it.
- Fixtures follow RULE-01's disposable-schema, rollback-only exception. Never production,
  core or public tables. Use a disposable PostgreSQL (ADR-0082) — Worker 1 owns the full
  database-heavy run, so do not compete for it.
- Measured and inferred values stay separate (INV-5). Missing is not zero.
- Never weaken a test or threshold to make it pass (INV-6 / RULE-00).

## Handoff

What now works end to end, through which command, with what evidence and at which revision;
what remains open and why; every migration you need, as exact DDL. Joe relays it to main.
