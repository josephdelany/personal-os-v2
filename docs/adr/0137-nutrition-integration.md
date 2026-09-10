# ADR-0137 — The nutrition cascade becomes the execution path

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-NUT-001, 002, 003, 004, 005, 010, 011, 012, 014, 015, 016, 024, 025, 034, 036
**Supersedes nothing. Completes:** ADR-0106 (the cascade) and ADR-0066 (the Open Food Facts
parser), both of which were built, tested and **never called**.

## Context

Two modules existed with thorough unit tests and **zero non-test callers**:

| module | tests | callers |
|---|---|---|
| `tools/engines/nutrition_cascade.py` | 16 | none |
| `tools/engines/nutrition_off.py` | 42 | none |

Meanwhile `nutrition.resolve_item` — the function actually on the execution path — performed one
`foods_cache` lookup and raised `Unresolved` on a miss. `SOURCE_PRECEDENCE` was declared in that
file and read by nothing.

This is a specific and dangerous shape of failure, not an untidy one. Every gate the project has
was green: the requirements were implemented, the tests passed, the ADRs were accepted. What did
not exist was a path from an input to the code. **A green unit suite over an unreachable module
is indistinguishable, from every summary the project produces, from a working feature.** The
ordering ADR-0106 argued for at length — a branded item never falling back to a generic source —
protected nothing, because nothing consulted it.

## Decisions

### 1. `resolve_item` walks the cascade; the cache is its first leg

`resolve_item` now builds four legs and calls `nutrition_cascade.resolve`:

| leg | class | what it is |
|---|---|---|
| `joe` | `CacheLeg` | the `foods_cache`/alias read — REQ-NUT-001 step 1, REQ-NUT-002, no network |
| `usda_branded` | `UnconfiguredLeg` | raises `NotConfigured`; no api.data.gov key |
| `usda_foundation` | `UnconfiguredLeg` | likewise |
| `off_product` | `OffLeg` | `nutrition_off` behind `lib.egress` (RULE-29, REQ-NUT-010/011) |

`nutrition.SOURCE_PRECEDENCE` is now bound to `nutrition_cascade.SOURCE_PRECEDENCE` rather than
being a second copy of the tuple. A constant duplicated in two files is how the first one came to
be unread.

**The cache reports the row's own source, not `joe`.** The cascade labels a result with the leg
that produced it; a cached `off_product` row read back through the cache leg is still a
crowd-sourced figure, and relabelling it `joe` would make it indistinguishable from something Joe
measured (INV-5, RULE-10). `resolve_item` therefore returns both: `source` is the provenance and
`leg` is the cascade step.

### 2. REQ-NUT-016 is enforced at the cache as well as over the network

The substitution ADR-0106 exists to prevent does not only happen at a source. Once a generic
`usda_foundation` row for "chicken burrito" is in `foods_cache`, an exact-name read serves it to a
branded query for ever, **offline, with no request to notice**. So a branded query is answered from
the cache only by a row whose source knows brands, and only when the row's recorded brand is the
same brand (REQ-NUT-025 — the only question that may be asked about two names is whether they are
the same). A branded-source row with no brand recorded answers only if Joe entered it.

### 2b. REQ-NUT-014 is enforced at the cache leg, not only at the branded leg

Making the cache a cascade leg opens a hole that did not exist before, and it has to be closed
in the same change. `nutrition_cascade.resolve` refuses a `usda_branded` match with no brand
owner — but that check is keyed on the **leg name**, and the cache leg is registered as `joe`.
A branded row read back from `foods_cache` walks past it, and `foods_cache.brand` is nullable,
so such a row is storable. The result would be `estimate_method = 'labelled'` with
`brand_owner = None` — a labelled figure with nothing to re-check it against, promoted into
`nutrition_display`'s tight class. `CacheLeg` therefore raises on it: a defect in the row, not a
resolution.

### 3. The cache is not "asked" for the purposes of REQ-NUT-024

`nutrition_cascade.resolve` counts a source as *asked* only if it could have known the food. A leg
may now declare `counts_as_asked = False`, and `CacheLeg` does.

Without this the ADR-0106 distinction collapses in practice. The cache is consulted on every item
and always answers, so with no USDA key and Open Food Facts unreachable, **every** item would come
back `no_source_match` with a review reason — an operations failure disguised as a data gap, on a
review list, costing Joe real effort per item. The cache is a record of answers already obtained;
it cannot know a food nobody has ever looked up, and its miss is not evidence about the food.

Symmetrically, `resolvable_sources` now excludes a leg that declares `unavailable_reason`. Being
registered is not the same as being able to answer, and a function whose job is to explain a
refusal must not name a source guaranteed to refuse.

### 4. The USDA legs raise `NotConfigured`. They do not return data

Joe has no api.data.gov key and the FoodData Central client is unwritten; under RULE-29 that egress
target is also unrecorded. `UnconfiguredLeg` raises `NotConfigured` with that detail, the cascade
records `not_configured` and walks on. This is the correct behaviour today, it is testable today,
and it is not a stub: a leg that returned something would put a number in an atom that no source
ever published (RULE-06, RULE-01).

### 5. Open Food Facts' four outcomes map onto the cascade's two, and the mapping is the point

`OffLeg` translates, and the translation is load-bearing:

* `OffNotFound` / `OffAmbiguous` / `OffMalformed` → `None`. Open Food Facts **was asked** and has
  no usable record. That is evidence about the food; it reaches the review list as
  `no_source_match`, and the specific reason is kept alongside the walk.
* `OffRateLimited` → `RateLimited` (REQ-NUT-012's hour-long cooldown); `OffTransient` →
  `SourceUnavailable`. Neither is a fact about the food. Filing a 503 as "no such food" turns a
  minute's outage into a permanent gap.
* `ContactMissing` → `NotConfigured`. REQ-NUT-010 requires a contact address; without one the
  request must not be issued at all.
* `egress.PayloadRefused` is **not caught**. A RULE-29 refusal recorded as a food outcome is a
  privacy failure filed as a data one, and it would be retried tonight.

### 6. A run against a disposable server does not get a live transport

`PERSONAL_OS_TEST_SOCKET` names a throwaway PostgreSQL instance built from migration DDL and
rolled back. The database being disposable does not make an HTTP request disposable: it would be
real, it would spend one of REQ-NUT-011's fifteen product reads, and it would drop a live
third-party payload into a fixture. `build_sources` therefore withholds the live transport there
and registers the leg as `not_configured`, which the cascade already knows how to record. A test
that wants the leg **injects** a transport, which is visible in the call rather than dependent on
an environment variable.

### 7. `method` and `estimate_method` are two different claims

`method` is the interval width that was **applied**; `estimate_method` is what the source
**claimed**. A weighed portion of an Open Food Facts product is `weighed` by width and
`off_product` by provenance. Collapsing them would lose one. REQ-NUT-014 is unchanged: only a USDA
Branded match claims `labelled`, and it must name the brand owner.

## The one thing this ADR does not do cleanly: `food_aliases`

REQ-NUT-001 step 1, REQ-NUT-004 and REQ-NUT-017 all name a `food_aliases` table. **Migration 0050
does not create one**, and this worker does not own migrations.

Until it exists, REQ-NUT-004 is satisfied by writing the phrase as uttered as a **second
`foods_cache` key on the same `(source, source_id)`** as the record it aliases. The alias row
carries `raw.alias_of` and the phrase; the source payload stays on the canonical row it was
derived from, so every row still traces to one source record (INV-1), and the pair is liftable
into a real table by one mechanical migration over `raw ? 'alias_of'`.

**The cost is stated rather than hidden:** the alias row duplicates the nutrient values, so a
REQ-NUT-008 re-fetch at 365 days must update both rows or the alias goes stale under a name that
did not change. That is the argument for the table, and the table is owed. The DDL the integration
owner needs:

```sql
CREATE TABLE IF NOT EXISTS __CORE__.food_aliases (
    alias_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alias       TEXT NOT NULL,                                  -- the phrase AS UTTERED
    food_id     UUID NOT NULL REFERENCES __CORE__.foods_cache(food_id),
    learned_from TEXT NOT NULL CHECK (learned_from IN ('joe','usda_branded','usda_foundation','off_product')),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (alias, food_id)
);
CREATE INDEX IF NOT EXISTS food_aliases_alias_idx ON __CORE__.food_aliases (lower(alias));
```

When it lands, `nutrition.remember_alias` and the alias branch of `lookup_cached` are the only two
functions that change; `resolve_item`'s contract does not.

## Evidence

`tests/test_nutrition_integration.py` — ten tests, all entering through `resolve_item`, none
touching the network. They assert on which legs were called and how many times, on
`ops.egress_log`, and on `core.foods_cache` afterwards, against migration 0050 verbatim in
disposable schemas (ADR-0082). Three mutations were run to confirm the tests are load-bearing:
removing the alias write, removing the REQ-NUT-016 cache guard, and removing `counts_as_asked`
each fail exactly the tests that claim those behaviours (four tests across the three).

The 67 pre-existing nutrition tests pass unchanged. No test, threshold or gate was weakened
(RULE-00).

**Not yet run in CI.** `tools/test_local_sql.py`'s `TESTS` tuple selects which SQL tests the
disposable-server job executes, and that file belongs to the integration owner.
`tests/test_nutrition_integration.py` — and `tests/test_nutrition_off.py`, whose SQL half has the
same gap — need adding to it before this evidence is produced by anything but a local run.

## 8. A resolved interval is stored as an atom, or it is not retrievable

Added after review. `resolve_item` returned numbers and nothing wrote them down, so the chain
stopped one step short of being readable: the panel, `atoms_current` and every `ask` operation
read `core.atoms`, and an interval that never becomes an atom is a calculation nobody can
retrieve. That is the same defect this ADR was written to fix — a component with no caller —
displaced one stage downstream, so it is closed here rather than left for the nightly resolver.

`persist_resolution` writes **one `consume` atom per nutrient**, and three properties are not
negotiable in that write:

* **`provenance = 'inferred'`, never `'extracted'`.** The capture contains a phrase, not a
  calorie. Every number came from a reference source and a portion rule, so RULE-05 and INV-5
  require the value to say it was inferred; `extracted` would claim the figure was observed in
  the capture.
* **The interval survives whole.** `value_low/point/high`, never a point (RULE-08). The atom's
  `estimate_method` carries the source's claim, which is a different fact from the width that
  was applied — decision 7 above.
* **INV-1 by construction.** Every atom carries the `raw_capture_id` of the capture the phrase
  was uttered in; the metric's `unit` and `state_class` are read from `metric_registry` rather
  than written as literals here, so the registry stays the single definition of the quantity.

**The write is idempotent, and keyed on the capture rather than the day.** Resolution is re-run
— a nightly pass sweeps the same days, and REQ-NUT-008 re-fetches a stale Open Food Facts row.
Without a guard each pass would double the day's calories, and a doubled daily total is not
obviously wrong on inspection, which is exactly what makes it dangerous. Keying the guard on
`(raw_capture_id, metric_key, subject_day, evidence_span)` rather than on the day means two
genuinely separate coffees both count, which a `(day, item)` key would silently collapse.

`record_unresolved` writes the `unresolved_items` row REQ-NUT-024 requires and returns None when
the item is already open, so a nightly re-run does not grow Joe's review list by one row per
night for the same sandwich — a list that does that is a list he stops reading (REQ-NUT-027).

### The REQ-NUT-014 hole this review found

The cascade raises when a `usda_branded` match arrives with no brand owner. That check is keyed
on the **leg name**, and `CacheLeg` is registered as `joe` — so a cached branded row walked past
it. `foods_cache.brand` is nullable, so the row is storable, and the result was
`estimate_method='labelled'` with `brand_owner=None`, while `labelled` is one of
`nutrition_display.TIGHT_METHODS`. A labelled figure that cannot be re-checked against the
product it came from, promoted into the tight class with no referent, is precisely what ADR-0106
forbids. `CacheLeg` now raises. Sentence 113 above ("REQ-NUT-014 is unchanged") was true of the
network path and false of the cache path; this is the correction.

One pre-existing fixture — `test_REQ_NUT_012_resolution_reads_the_cache_and_scales_by_grams`,
which cached a "big mac" as `usda_branded` with a NULL brand — was an illegal row under that
rule and now records `McDonald's`. No assertion in that test changed, and no threshold was
relaxed (RULE-00): the guard being load-bearing enough to catch a fixture that had been sitting
there is the argument for it.

### What criterion 6 still needs, and who owns it

Stored results are now retrievable through `core.atoms_current`, proven by
`tests/test_nutrition_persistence.py`. The remaining hop is **`tools/engines/panel.py`**, which
derives only `meals_logged` — a count — from `consume` atoms and no nutrient totals, so a kcal
figure still does not reach `analysis.panel` or the `metric` ask operation. That file is the
integration owner's. Two things must be decided with it rather than around it: `panel.value` is
a single number while nutrition is interval-valued, so flattening to the point estimate needs a
ruling; and REQ-NUT-026 requires any daily total to state the count of unresolved items
contributing to it, which a plain `sum()` does not carry.
