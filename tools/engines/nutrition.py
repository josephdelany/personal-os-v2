"""Food and drink resolution: a name and a quantity become interval-valued nutrients.

B12, REQ-NUT §D/§E, ADR-0056. Two rules shape everything here.

**RULE-09 — a model's output never becomes a gram, a calorie or a macro.** The model extracts
names, quantities and verbatim evidence spans. This module converts a name into numbers by
deterministic lookup against a reference source. There is no path by which a kcal figure the
model produced reaches an atom, and `resolve_item` never takes one as an argument.

**RULE-08 / RULE-06 — the width is the method, and a gap stays a gap.** Text-only LLM recall
carries 652 kcal MAE; frontier vision runs ~36% MAPE with systematic downward bias. A single
number is a lie about precision, so every resolved value is an interval whose width comes from
`config.nutrition_interval_widths` — a table, because RULE-00 forbids quietly editing a
threshold. An item nothing resolves gets NULL values and a row in `unresolved_items`
(REQ-NUT-040), never a plausible figure.

Cache first, always (§D.1): a lookup done once is not repeated. It costs a request, it can
fail, and the answer does not change.

**ADR-0137 — the cascade is the path, not a diagram of one.** Until this revision
`SOURCE_PRECEDENCE` was declared here and read nowhere, `tools/engines/nutrition_cascade.py`
had sixteen passing tests and no caller, and `resolve_item` did a single `foods_cache` lookup
and raised `Unresolved` on a miss. The declared order was documentation. It is now what runs:
`resolve_item` walks `nutrition_cascade.resolve` over four legs —

    joe             -> `CacheLeg`, the `foods_cache`/alias read (REQ-NUT-001 step 1, REQ-NUT-002)
    usda_branded    -> `UnconfiguredLeg`, blocked on an api.data.gov key
    usda_foundation -> `UnconfiguredLeg`, likewise
    off_product     -> `OffLeg`, `nutrition_off` behind `lib.egress` (REQ-NUT-010/011, RULE-29)

— and the two USDA legs raise `NotConfigured` rather than returning invented rows, so a missing
key is a recorded outcome and never a plausible number (RULE-06).
"""
import json
import os

from tools.engines import nutrition_cascade
from tools.engines import nutrition_off

CODE_VERSION = "nutrition-v2"

# The order sources are consulted. Joe's own corrections outrank everything, permanently
# (RULE-10, §D.4) — once he has said what a portion is, nothing re-guesses it.
#
# One definition, not two: the cascade owns the order (REQ-NUT-036) and this name is an alias
# for it. It used to be a second copy that nothing read, which is how it stayed a decoration.
SOURCE_PRECEDENCE = nutrition_cascade.SOURCE_PRECEDENCE

NUTRIENT_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "sodium_mg")

# REQ-NUT-005 / REQ-NUT-013 / REQ-NUT-014. The USDA FoodData Central legs are the only part of
# B12 §D.2/D.3 still outstanding, and they are outstanding for a reason that is not a coding
# one: Joe has no api.data.gov key. Saying so, once, in the place both legs report it from.
USDA_UNCONFIGURED = ("no api.data.gov key: the USDA FoodData Central client is unwritten and "
                     "its egress target is unrecorded under RULE-29 (ADR-0106 'What remains')")


class Unresolved(Exception):
    """Nothing could resolve this item. The caller writes an `unresolved_items` row.

    `reason` and `review_reason` come straight off the cascade and are NOT the same fact
    (REQ-NUT-015 / REQ-NUT-024). `no_source_match` means a source was asked and did not know
    the food — Joe can answer that, so `review_reason` is set. `no_source_available` means
    nothing could be asked at all; that is an operations problem and `review_reason` is None,
    because a review list of items nothing was ever going to resolve costs Joe real effort for
    no information. `brand` is kept verbatim so an unmatched restaurant item still says which
    restaurant (REQ-NUT-015).
    """

    def __init__(self, item_text, tried, *, reason="no_source_match",
                 review_reason="no_source_match", brand=None, status="unresolved"):
        self.item_text, self.tried = item_text, tried
        self.reason, self.review_reason = reason, review_reason
        self.brand, self.status = brand, status
        super().__init__(f"unresolved: {item_text!r} ({reason})")


def interval_widths(cur, config="config"):
    """method -> (rel_low, rel_high), read from the table rather than hardcoded."""
    cur.execute(f"select method, rel_low, rel_high from {config}.nutrition_interval_widths")
    return {m: (float(lo), float(hi)) for m, lo, hi in cur.fetchall()}


def constant(cur, key, config="config"):
    cur.execute(f"select value from {config}.strings where key = %s", (key,))
    row = cur.fetchone()
    if row is None:
        raise LookupError(f"{key} is not configured")
    return float(row[0])


def apply_width(point, method, widths):
    """A point becomes an interval. REQ-NUT-034 orders it; REQ-NUT-039 keeps it asymmetric.

    `photo_estimate` is 0.75x / 1.60x — wider ABOVE than below — because the documented bias is
    systematic UNDER-estimation. A symmetric interval would encode the wrong shape of error and
    would read as more careful than it is.
    """
    if point is None:
        return (None, None, None)                      # REQ-NUT-040: a gap stays a gap
    if method not in widths:
        raise LookupError(f"no registered interval width for method {method!r}")
    lo, hi = widths[method]
    return (round(point * lo, 4), round(point, 4), round(point * hi, 4))


def widest_method(methods, widths):
    """REQ-NUT-042: a meal resolved under several methods takes the WIDEST.

    The meal is only as well known as its least well known item, and taking the narrowest —
    or the commonest — would make a photo-estimated side dish disappear into a labelled main.
    """
    present = [m for m in methods if m in widths]
    if not present:
        return None
    return max(present, key=lambda m: widths[m][1] - widths[m][0])


# ---------------------------------------------------------------- lookup

def cached_row_answers_brand(source, row_brand, brand):
    """REQ-NUT-016 at the cache, where it is easiest to break.

    The substitution REQ-NUT-016 forbids does not only happen over the network. Once a generic
    `usda_foundation` row for "chicken burrito" is in `foods_cache`, an exact-name read serves
    it to "Chipotle chicken burrito" for ever, offline, with no request to notice. A restaurant
    portion is routinely double the generic and the number looks entirely ordinary, so:

      * a generic source may not answer a branded query at all (REQ-NUT-016);
      * a branded row that records a DIFFERENT brand is a different product (REQ-NUT-025 —
        the only question that may be asked about two names is whether they are the same);
      * a branded-source row with no brand recorded answers only if Joe entered it, because
        his row is keyed on the phrase he used and he is the one who ate it (RULE-10).
    """
    if source not in nutrition_cascade.BRANDED_SOURCES:
        return False
    if row_brand:
        return nutrition_off.normalise_name(row_brand) == nutrition_off.normalise_name(brand)
    return source == "joe"


def lookup_cached(cur, name, schema="core", brand=None):
    """The cache, in precedence order. Returns (row, method) or (None, None).

    Candidates are filtered in precedence order rather than taking the top row and testing it,
    so a rejected generic row does not hide a usable branded one beneath it.
    """
    cur.execute(
        f"""select canonical_name, source, nutrients_per_100g, serving_g, brand
              from {schema}.foods_cache
             where lower(canonical_name) = lower(%s)
             order by array_position(%s::text[], source)""",
        (name, list(SOURCE_PRECEDENCE)))
    for canonical, source, nutrients, serving_g, row_brand in cur.fetchall():
        if brand and not cached_row_answers_brand(source, row_brand, brand):
            continue
        nutrients = nutrients if isinstance(nutrients, dict) else json.loads(nutrients)
        return {"canonical_name": canonical, "source": source,
                "nutrients_per_100g": nutrients, "brand": row_brand,
                "serving_g": None if serving_g is None else float(serving_g)}, source
    return None, None


def portion_grams(cur, name, schema="core"):
    """Joe's own portion first, then any other. RULE-10: his correction outranks the source."""
    cur.execute(
        f"""select grams, source from {schema}.portions
             where lower(canonical_name) = lower(%s)
             order by case when source = 'joe' then 0 else 1 end, recorded_at desc
             limit 1""", (name,))
    row = cur.fetchone()
    return (float(row[0]), row[1]) if row else (None, None)


# ---------------------------------------------------------------- the cascade legs (ADR-0137)
#
# Each leg is a callable `(item_text, brand) -> result | None` and raises `SourceUnavailable`
# when it could not be asked, which is the contract `nutrition_cascade.resolve` walks. They are
# objects rather than closures for two honest reasons: `.calls` makes "the cache hit, so nothing
# went to the network" an assertion a test can make instead of a claim a comment makes, and
# `.notes` keeps what each source SAID next to the cascade's record of what was TRIED.

class CacheLeg:
    """Step 1 of REQ-NUT-001: `foods_cache` and its aliases. REQ-NUT-002 — no network request.

    Registered as the `joe` leg because it is consulted first and because Joe's own rows live
    in it, but the row's OWN source is what is reported back: a cached `off_product` row read
    from the cache is still an Open Food Facts figure, and relabelling it `joe` would make a
    crowd transcription indistinguishable from something Joe measured (RULE-10, INV-5).

    `counts_as_asked = False`: see `nutrition_cascade.resolve`. The cache cannot know a food
    nobody has ever looked up, so a cache miss is not evidence about the food.
    """

    counts_as_asked = False

    def __init__(self, cur, schema="core", notes=None):
        self.cur, self.schema = cur, schema
        self.notes = [] if notes is None else notes
        self.calls = 0

    def __call__(self, item_text, brand):
        self.calls += 1
        cached, source = lookup_cached(self.cur, item_text, self.schema, brand=brand)
        # The shape the pre-cascade `resolve_item` recorded, kept verbatim so an existing
        # reader of `tried` — and the test that pins it — still finds what it looks for.
        self.notes.append({"source": "foods_cache", "hit": cached is not None})
        if cached is None:
            return None
        out = {"cached": cached, "resolved_source": source, "from_cache": True,
               "estimate_method": source, "network_requests": 0}
        if source == "usda_branded":
            # REQ-NUT-014 does not stop applying because the row came back from the cache, and
            # it has to be ENFORCED here rather than merely applied. `nutrition_cascade.resolve`
            # raises when a `usda_branded` match arrives with no brand owner, but that check is
            # keyed on the LEG NAME, and this leg is registered as `joe` — so a cached branded
            # row walked straight past it. `foods_cache.brand` is nullable, so such a row is
            # storable, and the result was `estimate_method='labelled'` with `brand_owner=None`
            # — while `labelled` is one of `nutrition_display.TIGHT_METHODS`. That is exactly
            # what ADR-0106 forbids: a labelled figure that cannot be re-checked against the
            # product it came from, promoted into the tight class with no referent.
            if not cached["brand"]:
                raise ValueError(
                    "REQ-NUT-014: a usda_branded row must record its brand owner; "
                    f"{cached['canonical_name']!r} is cached with brand NULL. A `labelled` "
                    "claim with nothing to re-check it against is a defect in the row, not a "
                    "resolution (ADR-0106).")
            out["estimate_method"] = "labelled"
            out["brand_owner"] = cached["brand"]
        return out


class UnconfiguredLeg:
    """A cascade step that exists in code and cannot answer yet.

    REQ-NUT-005/013/014: the two USDA FoodData Central legs are blocked on Joe's api.data.gov
    key. Raising `NotConfigured` is the correct behaviour and not a placeholder — the cascade
    records `not_configured` with this detail and walks on, and the alternative (a leg that
    returns something) would put a number in an atom that no source ever published (RULE-06,
    RULE-01). `unavailable_reason` keeps `resolvable_sources` from claiming this leg could
    answer.
    """

    unavailable_reason = "not_configured"

    def __init__(self, source, detail):
        self.source, self.detail = source, detail
        self.calls = 0

    def __call__(self, item_text, brand):
        self.calls += 1
        raise nutrition_cascade.NotConfigured(self.source, self.detail)


class OffLeg:
    """Step 5 of REQ-NUT-001: Open Food Facts text search, behind `lib.egress`.

    Every request this leg makes goes through `nutrition_off`, which goes through
    `lib.egress.get_json`, which refuses a host outside `config.egress_allowlist` and screens
    the query parameters before anything leaves (RULE-29), and through the REQ-NUT-011 windows
    carried on `limits`. The transport is a parameter, so a test proves the etiquette without
    an IP address.

    The translation from Open Food Facts' four outcomes to the cascade's two is the whole point
    of this class, and it is not a formality:

      * `OffNotFound` / `OffAmbiguous` / `OffMalformed` -> `None`. Open Food Facts WAS asked and
        has no usable record for this food. That is evidence about the food, it reaches Joe's
        review list as `no_source_match`, and the specific reason is kept in `notes`.
      * `OffRateLimited` -> `RateLimited`, which puts the source in REQ-NUT-012's hour-long
        penalty box; `OffTransient` -> `SourceUnavailable`. Neither is a fact about the food,
        and recording an outage as "no such food" would turn a 503 into a permanent gap.
      * `ContactMissing` -> `NotConfigured`. REQ-NUT-010 requires a contact address; without
        one the request must not be issued at all.
      * `egress.PayloadRefused` is NOT caught. A RULE-29 refusal recorded as a food outcome is
        a privacy failure filed as a data one, and it must reach the operator as itself.
    """

    source = nutrition_off.SOURCE

    def __init__(self, cur, *, limits=None, env=None, schema="core", ops="ops",
                 config="config", transport=None, timeout=20, fetched_at=None, notes=None):
        self.cur, self.env, self.transport, self.timeout = cur, env, transport, timeout
        self.schema, self.ops, self.config = schema, ops, config
        self.limits = nutrition_off.Limits() if limits is None else limits
        self.fetched_at = fetched_at
        self.notes = [] if notes is None else notes
        self.calls = 0

    def __call__(self, item_text, brand):
        self.calls += 1
        try:
            row = nutrition_off.lookup_by_name(
                self.cur, item_text, brand=brand, limits=self.limits, env=self.env,
                schema=self.schema, ops=self.ops, config=self.config, timeout=self.timeout,
                fetched_at=self.fetched_at, _transport=self.transport)
        except nutrition_off.ContactMissing as e:
            raise nutrition_cascade.NotConfigured(self.source, f"REQ-NUT-010: {e}") from e
        except nutrition_off.OffRateLimited as e:
            raise nutrition_cascade.RateLimited(
                self.source, f"REQ-NUT-011 {e.reason} window, retry in {e.detail}s") from e
        except nutrition_off.OffTransient as e:
            raise nutrition_cascade.SourceUnavailable(
                self.source, e.reason, json.dumps(e.detail, default=str)) from e
        except nutrition_off.OffUnusable as e:
            self.notes.append(e.tried_entry())
            return None
        self.notes.append({"source": self.source, "hit": True, "source_id": row["source_id"]})
        return {"cache_row": row, "resolved_source": self.source, "from_cache": False,
                "estimate_method": self.source,
                "cached": {"canonical_name": row["canonical_name"], "source": row["source"],
                           "nutrients_per_100g": row["nutrients_per_100g"],
                           "serving_g": row["serving_g"], "brand": row["brand"]}}


def live_transport_permitted(env=None):
    """RULE-01 / ADR-0082: a run against a disposable local server is never a production run.

    `PERSONAL_OS_TEST_SOCKET` names a throwaway PostgreSQL instance built from migration DDL
    inside a transaction that rolls back. A resolver pointed at it must not issue a real Open
    Food Facts request — the request would be real whatever the database is, it would spend one
    of REQ-NUT-011's fifteen slots, and it would drop a live third-party payload into a fixture.
    So the live transport is withheld there and the leg reports `not_configured`, which the
    cascade already knows how to record. A test that wants the leg INJECTS a transport, which
    is visible in the call rather than dependent on an environment variable.
    """
    env = os.environ if env is None else env
    return not env.get("PERSONAL_OS_TEST_SOCKET")


LIVE_TRANSPORT_REFUSED = ("no transport was supplied and PERSONAL_OS_TEST_SOCKET names a "
                          "disposable server; a real Open Food Facts request is not issued "
                          "from a rolled-back fixture (RULE-01, ADR-0082)")


def build_sources(cur, *, schema="core", ops="ops", config="config", off=True,
                  off_transport=None, off_limits=None, off_env=None, off_timeout=20,
                  fetched_at=None, env=None):
    """The four legs, in the order `nutrition_cascade` will walk them.

    `off=False` is not a convenience switch: it is how a caller says Open Food Facts cannot be
    reached at all, which the cascade must be able to tell apart from "Open Food Facts did not
    know this food" (REQ-NUT-024).
    """
    sources = {
        "joe": CacheLeg(cur, schema),
        "usda_branded": UnconfiguredLeg("usda_branded", USDA_UNCONFIGURED),
        "usda_foundation": UnconfiguredLeg("usda_foundation", USDA_UNCONFIGURED),
    }
    if off and off_transport is None and not live_transport_permitted(env):
        sources["off_product"] = UnconfiguredLeg("off_product", LIVE_TRANSPORT_REFUSED)
    elif off:
        sources["off_product"] = OffLeg(cur, limits=off_limits, env=off_env, schema=schema,
                                        ops=ops, config=config, transport=off_transport,
                                        timeout=off_timeout, fetched_at=fetched_at)
    return sources


# ---------------------------------------------------------------- what a resolution writes

def remember_alias(cur, phrase, row, schema="core"):
    """REQ-NUT-004. The phrase AS UTTERED resolves from the cache next time.

    REQ-NUT-001 step 1 and REQ-NUT-004 name a `food_aliases` table. **Migration 0050 does not
    create one** and this worker does not own migrations, so the alias is written as a second
    `foods_cache` key on the SAME `(source, source_id)` as the record it aliases. That is not a
    second reading of the food: `raw` on the alias row carries `alias_of` and the phrase, the
    source payload stays on the canonical row it was derived from (INV-1), and the pair is
    liftable into a real `food_aliases` table by one mechanical migration over
    `raw ? 'alias_of'`. The cost of the bridge is that a re-fetch under REQ-NUT-008 must update
    both rows; that is the argument for the table, and it is recorded in ADR-0137.

    Nothing is written when the phrase already reads back through `lookup_cached` — which
    matches on `lower(canonical_name)`, so that, and not a normaliser, is the test used here.
    """
    canonical = row["canonical_name"]
    if str(phrase).strip().lower() == str(canonical).strip().lower():
        return None
    alias = dict(row)
    alias["canonical_name"] = str(phrase).strip()
    alias["raw"] = {"alias_of": canonical, "phrase_as_uttered": phrase,
                    "requirement": "REQ-NUT-004", "code_version": CODE_VERSION}
    # The insert is `nutrition_off`'s because the `foods_cache` append is written once, there,
    # with its ON CONFLICT DO NOTHING and its INV-1 note. It is not an Open-Food-Facts-specific
    # statement and this module does not restate it.
    return nutrition_off.insert_cache_row(cur, alias, schema=schema)


def resolve_item(cur, item_text, *, grams=None, servings=None, brand=None, sources=None,
                 cooldowns=None, learn_alias=True, schema="core", config="config", ops="ops",
                 **source_kw):
    """One food item -> {metric_key: (low, point, high)} plus the method that produced it.

    The walk is `nutrition_cascade.resolve` over `build_sources` (ADR-0137); `sources` is
    injectable so a test drives the real path with a transport it controls rather than a
    reimplementation of it.

    Raises `Unresolved` rather than returning zeros. A zero is a claim that the item had no
    calories; an absence is the truth (RULE-06).
    """
    widths = interval_widths(cur, config)
    if sources is None:
        sources = build_sources(cur, schema=schema, ops=ops, config=config, **source_kw)
    elif source_kw:
        raise TypeError(f"sources was supplied; {sorted(source_kw)} would be ignored")

    # One record of what each source SAID, in the order they were called. The cascade's own
    # `tried` records the WALK — which legs were skipped, rate limited or unconfigured — and the
    # two are complementary: neither alone says both what happened and why.
    notes = []
    for leg in sources.values():
        if hasattr(leg, "notes"):
            leg.notes = notes

    outcome = nutrition_cascade.resolve(item_text, sources, brand=brand, cooldowns=cooldowns)
    if isinstance(outcome, nutrition_cascade.Unresolved):
        # REQ-NUT-015 / REQ-NUT-024: the item text and the restaurant token survive verbatim,
        # and WHY nothing answered decides whether Joe is asked about it at all.
        raise Unresolved(item_text, list(outcome.tried) + notes, reason=outcome.reason,
                         review_reason=outcome.review_reason, brand=outcome.brand,
                         status=outcome.status)

    tried = list(outcome["tried"]) + notes
    cached, source = outcome["cached"], outcome["resolved_source"]

    # REQ-NUT-003 / REQ-NUT-004. A food resolved from a network source becomes a `foods_cache`
    # row and an alias, before anything else can fail: the composition IS resolved at this
    # point even if the quantity turns out not to be, and re-asking Open Food Facts tomorrow
    # for an answer already in hand spends a request REQ-NUT-011 rations.
    food_id = alias_id = None
    if not outcome.get("from_cache") and outcome.get("cache_row") is not None:
        food_id = nutrition_off.insert_cache_row(cur, outcome["cache_row"], schema=schema)
        if learn_alias:
            alias_id = remember_alias(cur, item_text, outcome["cache_row"], schema=schema)

    # How many grams? A stated weight beats a serving count beats a portion-table entry, and
    # each step down widens the interval because each is a weaker claim about quantity.
    method = source
    if grams is None:
        if servings is not None and cached["serving_g"]:
            grams = float(servings) * cached["serving_g"]
        else:
            grams, portion_source = portion_grams(cur, item_text, schema)
            tried.append({"source": "portions", "hit": grams is not None})
            if grams is None:
                # Knowing the composition is not knowing the quantity, and this refusal is not
                # about the sources at all — so it carries its own reason, not theirs.
                raise Unresolved(item_text, tried, reason="no_quantity",
                                 review_reason="no_quantity", brand=brand)
            method = "joe" if portion_source == "joe" else "portion_table"
    else:
        # A weighed quantity removes portion error but not composition error, so it takes the
        # `weighed` width rather than collapsing to a point (ADR-0005, REQ-NUT-035).
        method = "weighed" if source != "joe" else "joe"

    factor = float(grams) / 100.0
    out = {}
    for key in NUTRIENT_KEYS:
        per100 = cached["nutrients_per_100g"].get(key)
        if per100 is None:
            continue                                   # absent nutrient stays absent
        out[key] = apply_width(float(per100) * factor, method, widths)
    if not out:
        raise Unresolved(item_text, tried, reason="no_usable_nutrient",
                         review_reason="no_usable_nutrient", brand=brand)
    return {"method": method, "grams": round(float(grams), 2), "source": source,
            # `method` is the width that was APPLIED; `estimate_method` is what the source
            # CLAIMED. A weighed portion of an Open Food Facts product is `weighed` by width
            # and `off_product` by provenance, and collapsing the two would lose one of them.
            "estimate_method": outcome.get("estimate_method"),
            "leg": outcome["source"], "from_cache": bool(outcome.get("from_cache")),
            "nutrition_status": outcome.get("nutrition_status", "resolved"),
            "brand": cached.get("brand"), "food_id": food_id, "alias_id": alias_id,
            "canonical_name": cached["canonical_name"], "tried": tuple(tried),
            "nutrients": out}


# ---------------------------------------------------------------- drink -> ethanol (§D.6)

def resolve_drink(cur, *, volume_ml, abv_percent, abv_from_label,
                  volume_is_estimated=False, schema="core", config="config"):
    """ABV and volume -> ethanol grams and standard drinks, deterministically (REQ-NUT-066/067/068).

    `ethanol_grams = volume_ml x (abv/100) x 0.789`. The model supplies the drink's NAME and
    VOLUME and never an ethanol gram or a standard-drink count (RULE-09, REQ-CAP-109); this
    function does not accept one.

    `provenance` is the honest part. An ABV read from the drink's own label is `extracted`; an
    ABV supplied by a reference table for an unlabelled drink is `defaulted`, because an assumed
    ABV is a modelled input and not a measurement (RULE-06, REQ-NUT-066).

    REQ-NUT-067: where the volume is estimated or the ABV is defaulted, the interval must be
    NON-DEGENERATE — an assumed input may never masquerade as a measured point. Only a labelled
    volume against a label ABV may narrow toward one.
    """
    widths = interval_widths(cur, config)
    density = constant(cur, "ethanol_density_g_per_ml", config)
    g_per_drink = constant(cur, "g_per_standard_drink", config)

    if volume_ml is None or abv_percent is None:
        raise Unresolved("drink", [{"source": "abv_reference", "hit": False}])

    point = float(volume_ml) * (float(abv_percent) / 100.0) * density
    provenance = "extracted" if abv_from_label else "defaulted"

    # A labelled volume against a label ABV is the only case that may narrow. Everything else
    # carries the portion-table width, so an assumption is visible as width.
    if abv_from_label and not volume_is_estimated:
        method = "labelled"
    else:
        method = "portion_table"

    lo, pt, hi = apply_width(point, method, widths)
    drinks = tuple(None if v is None else round(v / g_per_drink, 4) for v in (lo, pt, hi))
    return {
        "method": method,
        "provenance": provenance,
        "ethanol_density_g_per_ml": density,
        "g_per_standard_drink": g_per_drink,
        "alcohol_ethanol_grams": (lo, pt, hi),
        "alcohol_standard_drinks": drinks,
    }


# ---------------------------------------------------------------- persistence (§D.5, INV-1)
#
# `resolve_item` returns numbers; until they are stored, nothing downstream can read them. The
# panel, `atoms_current` and every `ask` operation read `core.atoms`, so an interval that never
# becomes an atom is a calculation nobody can retrieve — which is how the cascade came to have
# sixteen passing tests and no caller.

# One nutrient interval per atom, keyed to the item's own capture. `metric_key` is a foreign key
# into `metric_registry`, which migration 0050 seeds with exactly these seven.
SUBJECT_DAY_RULE_VERSION = "v1-2026-08-23"          # matches tools/importers/common.py
UNRESOLVED_METHOD = "unresolved"                    # REQ-NUT-040's estimate_method


def _registry_units(cur, keys, schema="core"):
    """metric_key -> (unit, state_class), from the registry rather than from a literal here.

    The unit a nutrient is stored in is registry configuration (migration 0050 sets `kcal`,
    `g`, `mg`). Writing `'g'` into this module would be a second, silent definition of a
    quantity the registry already owns, and the two would drift.
    """
    cur.execute(f"""select metric_key, unit, state_class from {schema}.metric_registry
                     where metric_key = any(%s)""", (list(keys),))
    return {k: (u, s) for k, u, s in cur.fetchall()}


def _already_stored(cur, raw_capture_id, metric_key, subject_day, evidence_span, schema="core"):
    """Has this item's nutrient already been written and not superseded?

    Resolution is re-run: a nightly pass sweeps the same days, and REQ-NUT-008 re-fetches a
    stale Open Food Facts row. Without this, every re-run doubles the day's kcal — and a doubled
    total is not obviously wrong on inspection, which is what makes it dangerous. Keyed on the
    capture rather than the day, so two genuinely separate coffees on one day both survive.
    """
    cur.execute(f"""select 1 from {schema}.atoms a
                     where a.raw_capture_id = %s and a.metric_key = %s
                       and a.subject_day = %s and a.evidence_span = %s
                       and not exists (select 1 from {schema}.atoms b where b.supersedes = a.id)
                     limit 1""",
                (raw_capture_id, metric_key, subject_day, evidence_span))
    return cur.fetchone() is not None


def persist_resolution(cur, resolved, *, raw_capture_id, occurred_at, subject_day,
                       evidence_span, schema="core", trust_level="trusted",
                       code_version=CODE_VERSION):
    """A resolved item's intervals -> one `consume` atom per nutrient. Returns the keys written.

    **Why `inferred` and never `extracted`.** The capture contains a phrase, not a calorie. Every
    number here came from a reference source and a portion rule, so the value is inferred and
    RULE-05 requires it to say so — an `extracted` nutrient would claim the figure was observed
    in the capture, and `INV-5` exists to keep those two apart. `estimate_method` carries the
    finer claim (`labelled`, `off_product`, `portion_table`, …) and `value_low/point/high` carry
    the interval whole: a point would be a lie about precision (RULE-08).

    INV-1 holds by construction — every atom points at the capture the item was uttered in.
    """
    units = _registry_units(cur, resolved["nutrients"], schema)
    written = []
    for key, (low, point, high) in sorted(resolved["nutrients"].items()):
        if key not in units:
            # An unregistered metric is a schema question, not something to invent a unit for.
            raise LookupError(f"{key!r} is not in {schema}.metric_registry")
        if _already_stored(cur, raw_capture_id, key, subject_day, evidence_span, schema):
            continue
        unit, state_class = units[key]
        cur.execute(
            f"""insert into {schema}.atoms
                  (raw_capture_id, kind, metric_key, occurred_at, time_precision,
                   subject_day, subject_day_rule_version, presence,
                   value_low, value_point, value_high, estimate_method, unit, state_class,
                   trust_level, provenance, evidence_span, code_version)
                values (%s, 'consume', %s, %s, 'hour', %s, %s, 'observed',
                        %s, %s, %s, %s, %s, %s, %s, 'inferred', %s, %s)""",
            (raw_capture_id, key, occurred_at, subject_day, SUBJECT_DAY_RULE_VERSION,
             low, point, high, resolved["estimate_method"], unit, state_class,
             trust_level, evidence_span, code_version))
        written.append(key)
    return written


def record_unresolved(cur, unresolved, *, raw_capture_id, subject_day, schema="core"):
    """An item nothing resolved -> one `unresolved_items` row (REQ-NUT-024, REQ-NUT-040).

    Returns the `item_id`, or None when the item is already open — a nightly re-run must not
    grow Joe's review list by one row per night for the same sandwich.

    **An operations failure is not put on the review list.** When `review_reason` is None the
    cascade is saying nothing could be ASKED — no key, everything rate limited — and the item
    is recorded with that reason so the history is complete, but `tried` says plainly that no
    source was consulted. REQ-NUT-027: unresolved is a normal outcome, never an error state.
    """
    cur.execute(f"""select item_id from {schema}.unresolved_items
                     where item_text = %s and subject_day = %s and resolved_at is null
                       and raw_capture_id is not distinct from %s
                     limit 1""", (unresolved.item_text, subject_day, raw_capture_id))
    existing = cur.fetchone()
    if existing:
        return None
    tried = json.dumps({"reason": unresolved.reason, "review_reason": unresolved.review_reason,
                        "brand": unresolved.brand, "tried": list(unresolved.tried)},
                       default=str)
    cur.execute(
        f"""insert into {schema}.unresolved_items
              (raw_capture_id, item_text, subject_day, tried)
            values (%s, %s, %s, %s::jsonb) returning item_id""",
        (raw_capture_id, unresolved.item_text, subject_day, tried))
    return cur.fetchone()[0]
