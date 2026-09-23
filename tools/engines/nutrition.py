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
import datetime as dt
import json
import os
import re
import math

from tools.engines import nutrition_cascade
from tools.engines import nutrition_off
from tools.engines import nutrition_usda

CODE_VERSION = "nutrition-v2"

# The order sources are consulted. Joe's own corrections outrank everything, permanently
# (RULE-10, §D.4) — once he has said what a portion is, nothing re-guesses it.
#
# One definition, not two: the cascade owns the order (REQ-NUT-036) and this name is an alias
# for it. It used to be a second copy that nothing read, which is how it stayed a decoration.
SOURCE_PRECEDENCE = nutrition_cascade.SOURCE_PRECEDENCE

NUTRIENT_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "sodium_mg")

# REQ-NUT-005 / REQ-NUT-013 / REQ-NUT-014. The USDA FoodData Central client is now WRITTEN
# (`nutrition_usda`) and its egress target has been recorded since migration 0050 put
# `api.nal.usda.gov` in `config.egress_allowlist` — so ADR-0106's second blocker was already
# resolved when it was written (ADR-0139). What remains is a credential, which is a RUNTIME
# fact rather than a constant: `build_sources` asks `nutrition_usda` at the moment it builds
# the legs, and there is deliberately no module-level "USDA is unconfigured" string here any
# more. One did exist, and by the end of this change nothing read it — a constant nobody reads
# is the smallest version of the problem this project keeps finding at module scale.
#
# RULE-01 / ADR-0082, as for Open Food Facts below: a resolver pointed at a disposable server
# must not spend one of REQ-NUT-009's 900 real slots or drop a live third-party payload into a
# fixture. A test that wants the leg INJECTS a transport, which is visible in the call.
USDA_TRANSPORT_REFUSED = ("no transport was supplied and PERSONAL_OS_TEST_SOCKET names a "
                          "disposable server; a real USDA FoodData Central request is not "
                          "issued from a rolled-back fixture (RULE-01, ADR-0082)")


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

    Two ways in, and REQ-NUT-001 names both: step (1) is a `food_aliases` exact match on the
    phrase as spoken, and a direct `canonical_name` match is the case where what Joe said IS
    the food's name. Either way REQ-NUT-002 holds — nutrients come from `foods_cache` and no
    network request is issued.

    **They are unioned and then ranked, not tried in sequence, and that ordering is RULE-10.**
    An alias points at exactly one `food_id`. If the alias were consulted FIRST and returned
    its row, an alias learned from Open Food Facts would outrank a correction Joe made later
    for the same food — the resolver would answer with the crowd figure and never look at
    Joe's. Collecting both sets and sorting the union by `SOURCE_PRECEDENCE` keeps `joe` ahead
    of every source however the row was reached, which is the whole point of the ordering.

    Candidates are filtered in precedence order rather than taking the top row and testing it,
    so a rejected generic row does not hide a usable branded one beneath it.
    """
    cur.execute(
        f"""select c.canonical_name, c.source, c.nutrients_per_100g, c.serving_g, c.brand,
                   c.food_id,c.source_id,c.raw
              from {schema}.foods_cache c
             where (lower(c.canonical_name) = lower(%s)
                or exists (select 1 from {schema}.food_aliases a
                    join {schema}.foods_cache original on original.food_id=a.food_id
                    where lower(a.alias)=lower(%s)
                      and original.canonical_name=c.canonical_name
                      and original.source=c.source
                      and original.source_id is not distinct from c.source_id))
               and (c.source not in ('usda_branded','off_product')
                    or c.fetched_at >= clock_timestamp()-interval '365 days')
             order by array_position(%s::text[], c.source),c.fetched_at desc,c.food_id""",
        (name, name, list(SOURCE_PRECEDENCE)))
    for canonical, source, nutrients, serving_g, row_brand, food_id, source_id, raw in cur.fetchall():
        if brand and not cached_row_answers_brand(source, row_brand, brand):
            continue
        nutrients = nutrients if isinstance(nutrients, dict) else json.loads(nutrients)
        return {"canonical_name": canonical, "source": source,
                "nutrients_per_100g": nutrients, "brand": row_brand,
                "food_id":str(food_id),"source_id":source_id,"raw":raw,
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


class UsdaLeg:
    """Steps 3 and 4 of REQ-NUT-001: USDA FoodData Central, behind `lib.egress`.

    One class serves both datasets because the difference between them is a `dataType` filter
    and a TTL, not a protocol. `source` is `usda_branded` or `usda_foundation` and is the name
    the cascade registers it under, so `nutrition_cascade`'s REQ-NUT-014 brand-owner check and
    REQ-NUT-016 branded-source rule key on the right thing without a special case here.

    **Both legs share one `Quota`.** api.data.gov meters the KEY, and one key serves both
    datasets, so REQ-NUT-009's 900-per-hour ceiling and REQ-NUT-012's 429 cooldown are counted
    once across the pair. Giving each leg its own would permit 1,800 requests an hour and would
    let a 429 on Branded be followed immediately by a Foundation request against the same
    throttled key — which is how a key gets banned, and the failure mode of a banned key is
    every future item unresolved.

    The translation from FoodData Central's outcomes to the cascade's two mirrors `OffLeg`:

      * `UsdaNotFound` / `UsdaAmbiguous` / `UsdaMalformed` -> `None`. USDA WAS asked and has no
        usable record for this food. That is evidence about the food, it reaches Joe's review
        list as `no_source_match`, and the specific reason is kept in `notes`.
      * `UsdaRateLimited` -> `RateLimited`, which puts the source in REQ-NUT-012's hour-long
        penalty box; `UsdaTransient` -> `SourceUnavailable`. Neither is a fact about the food,
        and recording an outage as "no such food" would turn a 503 into a permanent gap.
      * `ApiKeyMissing` -> `NotConfigured`. In practice `build_sources` has already substituted
        an `UnconfiguredLeg` when there is no key, so this is the path for a key that
        disappears mid-run; it is handled rather than left to become a crash in a nightly job.
      * `egress.PayloadRefused` is NOT caught, exactly as in `OffLeg`.
    """

    def __init__(self, source, cur, *, quota=None, env=None, schema="core", ops="ops",
                 config="config", transport=None, timeout=20, fetched_at=None, notes=None):
        if source not in nutrition_usda.SOURCES:
            raise ValueError(f"not a USDA cascade source: {source!r}")
        self.source, self.cur, self.env = source, cur, env
        self.transport, self.timeout = transport, timeout
        self.schema, self.ops, self.config = schema, ops, config
        self.quota = nutrition_usda.Quota() if quota is None else quota
        self.fetched_at = fetched_at
        self.notes = [] if notes is None else notes
        self.calls = 0

    def __call__(self, item_text, brand):
        self.calls += 1
        try:
            row = nutrition_usda.lookup_by_name(
                self.cur, item_text, self.source, brand=brand, quota=self.quota, env=self.env,
                schema=self.schema, ops=self.ops, config=self.config, timeout=self.timeout,
                fetched_at=self.fetched_at, _transport=self.transport)
        except nutrition_usda.ApiKeyMissing as e:
            raise nutrition_cascade.NotConfigured(self.source, str(e)) from e
        except nutrition_usda.UsdaRateLimited as e:
            kind = "REQ-NUT-012 provider 429" if e.provider else "REQ-NUT-009 hourly quota"
            raise nutrition_cascade.RateLimited(
                self.source, f"{kind}, retry in {round(e.retry_after)}s") from e
        except nutrition_usda.UsdaTransient as e:
            raise nutrition_cascade.SourceUnavailable(
                self.source, e.reason, json.dumps(e.detail, default=str)) from e
        except nutrition_usda.UsdaUnusable as e:
            self.notes.append(e.tried_entry())
            return None
        self.notes.append({"source": self.source, "hit": True, "source_id": row["source_id"]})
        out = {"cache_row": row, "resolved_source": self.source, "from_cache": False,
               "estimate_method": self.source,
               "cached": {"canonical_name": row["canonical_name"], "source": row["source"],
                          "nutrients_per_100g": row["nutrients_per_100g"],
                          "serving_g": row["serving_g"], "brand": row["brand"],
                          "source_id":row.get('source_id'),"raw":row.get('raw')}}
        if self.source == nutrition_usda.BRANDED:
            # REQ-NUT-014. `nutrition_cascade.resolve` REQUIRES this key on a `usda_branded`
            # match and raises without it; `nutrition_usda.parse_food` has already refused a
            # branded record with no brand owner, so this cannot be None by the time it is read.
            out["brand_owner"] = row["brand"]
        return out


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
                           "serving_g": row["serving_g"], "brand": row["brand"],
                           "source_id":row.get('source_id'),"raw":row.get('raw')}}


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


def usda_available(env=None):
    """Is there an api.data.gov key? Returns the reason it is unusable, or None.

    Separated from `build_sources` so the reason a USDA leg is absent can be asked for — by
    `tools/resolve_nutrition.py`, and by a test — without constructing the whole cascade.
    """
    try:
        nutrition_usda.api_key(env)
    except nutrition_usda.ApiKeyMissing as e:
        return str(e)
    return None


def build_sources(cur, *, schema="core", ops="ops", config="config", off=True,
                  off_transport=None, off_limits=None, off_env=None, off_timeout=20,
                  usda=True, usda_transport=None, usda_quota=None, usda_env=None,
                  usda_timeout=20, fetched_at=None, env=None):
    """The four legs, in the order `nutrition_cascade` will walk them.

    `off=False` and `usda=False` are not convenience switches: they are how a caller says a
    source cannot be reached at all, which the cascade must be able to tell apart from "that
    source did not know this food" (REQ-NUT-024).

    A leg is real only when it could actually answer. Three things can put a USDA leg back to
    `UnconfiguredLeg`, and they are different facts that must not collapse into one message:
    the caller disabled it, there is no api.data.gov key, or the run is pointed at a disposable
    server with no injected transport (RULE-01).

    `usda_env` carries the CREDENTIAL and `env` the RUN CONTEXT, exactly as `off_env` and `env`
    already divide for Open Food Facts. They are not interchangeable and neither defaults to
    the other: a caller passing `env={}` is saying "no test socket is set", not "this system
    has no api.data.gov key", and letting one stand in for the other would silently disable a
    configured leg. Both fall back to `os.environ` on their own when None.
    """
    sources = {"joe": CacheLeg(cur, schema)}

    # REQ-NUT-009/012 are metered per KEY, so ONE quota object is shared by both USDA legs.
    usda_quota = nutrition_usda.Quota() if usda_quota is None else usda_quota
    usda_reason = None
    if not usda:
        usda_reason = "the caller declared USDA FoodData Central unreachable for this run"
    elif (missing := usda_available(usda_env)):
        usda_reason = missing
    elif usda_transport is None and not live_transport_permitted(env):
        usda_reason = USDA_TRANSPORT_REFUSED
    for name in nutrition_usda.SOURCES:
        sources[name] = (UnconfiguredLeg(name, usda_reason) if usda_reason else
                         UsdaLeg(name, cur, quota=usda_quota, env=usda_env, schema=schema,
                                 ops=ops, config=config, transport=usda_transport,
                                 timeout=usda_timeout, fetched_at=fetched_at))
    if off and off_transport is None and not live_transport_permitted(env):
        sources["off_product"] = UnconfiguredLeg("off_product", LIVE_TRANSPORT_REFUSED)
    elif off:
        sources["off_product"] = OffLeg(cur, limits=off_limits, env=off_env, schema=schema,
                                        ops=ops, config=config, transport=off_transport,
                                        timeout=off_timeout, fetched_at=fetched_at)
    return sources


# ---------------------------------------------------------------- what a resolution writes

def cached_food_id(cur, row, schema="core"):
    """The `food_id` of an existing `foods_cache` row, or None.

    `nutrition_off.insert_cache_row` returns None when `ON CONFLICT DO NOTHING` fired, which is
    the ordinary case for a food already in the cache. The alias still needs something to point
    at, so the id is read back on that path rather than the alias being skipped — otherwise a
    phrase would only ever be learned the very first time a food was seen.
    """
    cur.execute(f"""select food_id from {schema}.foods_cache
                     where canonical_name = %s and source = %s
                       and source_id is not distinct from %s
                     order by fetched_at desc,food_id limit 1""",
                (row["canonical_name"], row["source"], row.get("source_id")))
    found = cur.fetchone()
    return found[0] if found else None


def remember_alias(cur, phrase, row, *, food_id=None, schema="core"):
    """REQ-NUT-004. The phrase AS UTTERED resolves from the cache next time.

    Writes `core.food_aliases` (migration 0071). Until that table existed the alias was written
    as a SECOND `foods_cache` row carrying `raw->>'alias_of'` — a bridge that worked and was
    tested, and whose cost was that REQ-NUT-008's 365-day re-fetch would have had to update two
    rows or let them disagree. One fact stored twice, one copy refreshed. The bridge is gone.

    **Both columns are written and they are not the same string.** `alias` is folded for
    matching; `verbatim` is what Joe actually said, which is what REQ-NUT-004 means by "as
    uttered" and what a folded key destroys. A correction is only recognisable as a correction
    of something if the something survives.

    An alias IS written when the phrase already equals the canonical name. The old bridge
    skipped that case because a second `foods_cache` row would have been pure duplication;
    a `food_aliases` row is not, REQ-NUT-004 does not exempt it, and step (1) of REQ-NUT-001
    should not depend on which of two spellings a food happened to be resolved under.
    """
    if food_id is None:
        food_id = cached_food_id(cur, row, schema)
    if food_id is None:
        # Nothing to point at. Silent rather than raising: the caller has already stored the
        # nutrients, and an alias is a convenience for the next lookup, not part of the answer.
        return None
    verbatim = str(phrase)
    alias = verbatim.strip().lower()
    if not alias:
        return None
    cur.execute(
        f"""insert into {schema}.food_aliases (alias, verbatim, food_id, source)
            values (%s, %s, %s, %s)
            on conflict (alias, food_id) do nothing
            returning alias_id""",
        (alias, verbatim, food_id, row["source"]))
    found = cur.fetchone()
    return found[0] if found else None


def _counted_servings(item_text, count, source, cached):
    """Use the label's household count, never equate an item with a serving."""
    raw = cached.get('raw') or {}
    household = (raw.get('usda_food') or {}).get('householdServingFullText')
    if source != 'usda_branded' or not cached.get('serving_g') or not isinstance(household,str):
        raise Unresolved(item_text,[],reason='no_branded_serving',review_reason='no_branded_serving',brand=cached.get('brand'))
    match = re.fullmatch(r'\s*(one|\d+(?:\.\d+)?)\s+([a-z][a-z -]*?)'
                         r'(?:\s*\((\d+(?:\.\d+)?\s*(?:g|grams?|oz|ounces?))\))?\s*',household,re.I)
    if match is None:
        raise Unresolved(item_text,[],reason='no_branded_serving',review_reason='no_branded_serving',brand=cached.get('brand'))
    per_serving = 1.0 if match[1].lower()=='one' else float(match[1])
    unit_words = set(re.findall(r'[a-z]+',match[2].lower()))
    # A cup, gram or slice fraction is not proof of one complete menu item.
    forbidden = {'g','gram','grams','kg','ml','cup','cups','tbsp','tsp','oz','ounce','ounces','pound','pounds','slice','slices',
                 'or','to','about','half','quarter','third','two','three','four','five','six','seven','eight','nine','ten'}
    counted = {'item','items','piece','pieces','bar','bars','burger','burgers','sandwich','sandwiches',
               'cookie','cookies','cracker','crackers','egg','eggs'}
    if per_serving<=0 or unit_words & forbidden or not unit_words & counted:
        raise Unresolved(item_text,[],reason='no_branded_serving',review_reason='no_branded_serving',brand=cached.get('brand'))
    if per_serving != 1:
        # Multiple pieces are usable only when their stated noun also names
        # the requested food; do not turn a multi-piece package into one item.
        food_words = {word.rstrip('s') for word in re.findall(r'[a-z]+',item_text.lower())}
        label_words = {word.rstrip('s') for word in unit_words & counted} - {'item','piece','packet'}
        if not food_words & label_words:
            raise Unresolved(item_text,[],reason='no_branded_serving',review_reason='no_branded_serving',brand=cached.get('brand'))
    return float(count)/per_serving


def resolve_item(cur, item_text, *, grams=None, servings=None, item_count=None, brand=None, sources=None,
                 cooldowns=None, learn_alias=True, schema="core", config="config", ops="ops",
                 **source_kw):
    """One food item -> {metric_key: (low, point, high)} plus the method that produced it.

    The walk is `nutrition_cascade.resolve` over `build_sources` (ADR-0137); `sources` is
    injectable so a test drives the real path with a transport it controls rather than a
    reimplementation of it.

    Raises `Unresolved` rather than returning zeros. A zero is a claim that the item had no
    calories; an absence is the truth (RULE-06).
    """
    if sum(value is not None for value in (grams,servings,item_count))>1:
        raise ValueError('one quantity representation required')
    for value in (grams,servings,item_count):
        if value is not None and (isinstance(value,bool) or not math.isfinite(float(value)) or float(value)<=0):
            raise ValueError('positive finite quantity required')
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
    if item_count is not None:
        servings = _counted_servings(item_text,item_count,source,cached)

    # REQ-NUT-003 / REQ-NUT-004. A food resolved from a network source becomes a `foods_cache`
    # row and an alias, before anything else can fail: the composition IS resolved at this
    # point even if the quantity turns out not to be, and re-asking Open Food Facts tomorrow
    # for an answer already in hand spends a request REQ-NUT-011 rations.
    food_id, alias_id = cached.get('food_id'), None
    if not outcome.get("from_cache") and outcome.get("cache_row") is not None:
        food_id = nutrition_off.insert_cache_row(cur, outcome["cache_row"], schema=schema, refresh=True)
        if food_id is None:
            food_id = cached_food_id(cur,outcome['cache_row'],schema=schema)
        if learn_alias:
            alias_id = remember_alias(cur, item_text, outcome["cache_row"],
                                      food_id=food_id, schema=schema)

    # How many grams? A stated weight beats a serving count beats a portion-table entry, and
    # each step down widens the interval because each is a weaker claim about quantity.
    #
    # Recorded BEFORE `grams` is reassigned below: REQ-NUT-032 distinguishes a weight Joe
    # stated from one this system derived, and after the next few lines the variable cannot
    # tell them apart.
    grams_stated = grams is not None
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
    components = []
    stated_count = item_count if item_count is not None else servings
    if source=='usda_branded' and not grams_stated and stated_count is not None and float(stated_count)%1:
        whole = math.floor(float(stated_count))
        fraction = float(stated_count)-whole
        unit_grams = float(grams)/float(stated_count)
        for label,part,width,provenance in (('whole',whole,'labelled','extracted'),
                                            ('fraction',fraction,'portion_table','defaulted')):
            if part:
                nutrients={key:apply_width(float(value)*part*unit_grams/100,width,widths)
                           for key,value in cached['nutrients_per_100g'].items()
                           if key in NUTRIENT_KEYS and value is not None}
                components.append({'component':label,'count':part,'grams':part*unit_grams,
                                   'stored_method':width,'method':width,'quantity_provenance':provenance,
                                   'nutrients':nutrients})
    for key in NUTRIENT_KEYS:
        per100 = cached["nutrients_per_100g"].get(key)
        if per100 is None:
            continue                                   # absent nutrient stays absent
        out[key] = (tuple(round(sum(part['nutrients'][key][i] for part in components),4) for i in range(3))
                    if components else apply_width(float(per100) * factor, method, widths))
    if not out:
        raise Unresolved(item_text, tried, reason="no_usable_nutrient",
                         review_reason="no_usable_nutrient", brand=brand)
    source_raw = cached.get('raw') or {}
    usda_food = source_raw.get('usda_food') or {}
    return {"method": method, "grams": round(float(grams), 2), "source": source,
            "components":components,
            "quantity_provenance":"defaulted" if components else ("extracted" if grams_stated or stated_count is not None else "defaulted"),
            "source_id":cached.get('source_id'),
            "serving_definition":{'grams':cached.get('serving_g'),
                                  'household_measure':usda_food.get('householdServingFullText'),
                                  'brand_owner':usda_food.get('brandOwner') or cached.get('brand')},
            # `method` is the width that was APPLIED; `estimate_method` is what the source
            # CLAIMED. A weighed portion of an Open Food Facts product is `weighed` by width
            # and `off_product` by provenance, and collapsing the two would lose one of them.
            "estimate_method": outcome.get("estimate_method"),
            # REQ-NUT-032's value, which is a THIRD fact and not either of the two above: the
            # width applied, the source's claim, and the method the requirement enumerates.
            "stored_method": 'portion_table' if components else stored_estimate_method(
                source_claim=outcome.get("estimate_method"), grams_stated=grams_stated,
                resolved_source=source),
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

# REQ-NUT-032. The stored `estimate_method` of a row carrying a nutrient interval is EXACTLY
# one of these five. Not a convention — the requirement enumerates them.
#
# THIS IS NOT WHAT WAS BEING STORED, and the gap is why `nutrition_display` could not be wired.
# `persist_resolution` wrote `resolved["estimate_method"]`, which is the SOURCE's claim —
# `usda_foundation`, `off_product` — so a Foundation-resolved row carried a value outside this
# set. `nutrition_display.TIGHT_METHODS` and `METHOD_WEIGHT` speak this vocabulary, so they
# matched nothing that had actually been stored: REQ-NUT-045's visual weight fell through to
# "light" for everything and REQ-NUT-046's restrict mode returned an empty set for every day.
# A display layer whose vocabulary does not intersect the stored data cannot be connected, and
# that — not the absence of a caller — was the real reason it had none.
REQ_NUT_032_METHODS = frozenset(
    {"weighed", "labelled", "portion_table", "photo_estimate", UNRESOLVED_METHOD})


def stored_estimate_method(*, source_claim, grams_stated, resolved_source=None):
    """The REQ-NUT-032 value for a resolution. Provenance is NOT this column.

    The source is not lost by this. It stays on the `foods_cache` row the resolution came from
    and in the resolution's own `source`/`estimate_method` fields; what changes is only which of
    the two facts occupies a column the requirement reserves for the method.

    **1. A manufacturer's label is `labelled`, and this outranks a stated mass.** Not obvious,
    and the integration owner initially ruled the other way before a USDA acceptance test
    caught it. The column governs the INTERVAL WIDTH — REQ-NUT-035/036/037 are each "WHEN
    `estimate_method` = X, SHALL set the width" — so it names whichever error source dominates
    what is left. Weighing removes PORTION error; it does nothing about COMPOSITION error. So:

        weighed GENERIC food   portion error ~0, composition uncertain      -> `weighed`
        weighed BRANDED food   portion error ~0, composition = label        -> `labelled`

    REQ-NUT-035's own rationale says "a weighed GENERIC food", and warns its width may prove
    *wider* than a label's legal tolerance rather than tighter. Calling a weighed branded bar
    `weighed` would apply the uncalibrated generic-composition assumption to a product whose
    composition is legally bounded.

    **2. A whole serving count against a USDA Branded per-serving gram weight is `labelled`.**
    REQ-NUT-050 says so outright: multiply the Branded record's per-serving gram weight by the
    count, store the serving definition, and set `estimate_method = 'labelled'` so REQ-NUT-036's
    width governs. The label defines what a serving is, so "2 servings" of a labelled product is
    a label claim, not an estimated portion.

    This also removes an inconsistency that was already live: `resolve_from_cache` sets
    `estimate_method = 'labelled'` for a cached `usda_branded` row, while the fresh Branded leg
    sets it to `'usda_branded'`. The same food therefore stored `labelled` from cache and
    `portion_table` on a fresh resolution — the width a reader sees depending on whether someone
    had asked for that food before.

    **3. Everything else that got its quantity from a portion is `portion_table`** — Joe's own
    `portions` row, a Foundation or Open Food Facts declared serving.

    **Open Food Facts is deliberately NOT extended to `labelled`, and that is a decision.**
    REQ-NUT-050 names the USDA Branded data type and nothing else. OFF is a crowd-sourced
    transcription of labels rather than the label, and `labelled` is one of
    `nutrition_display.TIGHT_METHODS`: promoting it would put a figure nobody can re-check
    against the product into the tight class, which is what ADR-0106 forbids and what
    `resolve_from_cache`'s REQ-NUT-014 guard exists to stop. Widening the requirement to cover a
    source it does not name would be this function inventing a rule (RULE-09).

    REQ-NUT-052 fractional Branded counts are split by resolve_item into labelled
    whole and portion_table fractional components, each with its own width.
    Capture persistence requires per-item/component identity for that split;
    callers without it refuse instead of collapsing the fractional uncertainty.
    """
    if source_claim == "labelled" or resolved_source == "usda_branded":
        return "labelled"                       # REQ-NUT-014 / REQ-NUT-050; see branches 1 & 2
    return "weighed" if grams_stated else "portion_table"


def _registry_units(cur, keys, schema="core"):
    """metric_key -> (unit, state_class), from the registry rather than from a literal here.

    The unit a nutrient is stored in is registry configuration (migration 0050 sets `kcal`,
    `g`, `mg`). Writing `'g'` into this module would be a second, silent definition of a
    quantity the registry already owns, and the two would drift.
    """
    cur.execute(f"""select metric_key, unit, state_class from {schema}.metric_registry
                     where metric_key = any(%s)""", (list(keys),))
    return {k: (u, s) for k, u, s in cur.fetchall()}


def _already_stored(cur, raw_capture_id, metric_key, subject_day, evidence_span, schema="core", capture_item_id=None, capture_component='total'):
    """Has this item's nutrient already been written and not superseded?

    Resolution is re-run: a nightly pass sweeps the same days, and REQ-NUT-008 re-fetches a
    stale Open Food Facts row. Without this, every re-run doubles the day's kcal — and a doubled
    total is not obviously wrong on inspection, which is what makes it dangerous. Keyed on the
    capture rather than the day, so two genuinely separate coffees on one day both survive.
    """
    if capture_item_id is not None:
        cur.execute(f'''SELECT 1 FROM {schema}.atoms a
            WHERE a.capture_item_id=%s AND a.raw_capture_id=%s AND a.metric_key=%s AND a.capture_component=%s
              AND NOT EXISTS (SELECT 1 FROM {schema}.atoms b WHERE b.supersedes=a.id) LIMIT 1''',
            (capture_item_id,raw_capture_id,metric_key,capture_component))
        return cur.fetchone() is not None
    cur.execute(f"""select 1 from {schema}.atoms a
                     where a.raw_capture_id = %s and a.metric_key = %s
                       and a.subject_day = %s and a.evidence_span = %s
                       and not exists (select 1 from {schema}.atoms b where b.supersedes = a.id)
                     limit 1""",
                (raw_capture_id, metric_key, subject_day, evidence_span))
    return cur.fetchone() is not None


def persist_resolution(cur, resolved, *, raw_capture_id, occurred_at, subject_day,
                       evidence_span, schema="core", trust_level="trusted",
                       code_version=CODE_VERSION, time_precision="hour", capture_item_id=None,
                       capture_component='total'):
    """A resolved item's intervals -> one `consume` atom per nutrient. Returns the keys written.

    **Why `inferred` and never `extracted`.** The capture contains a phrase, not a calorie. Every
    number here came from a reference source and a portion rule, so the value is inferred and
    RULE-05 requires it to say so — an `extracted` nutrient would claim the figure was observed
    in the capture, and `INV-5` exists to keep those two apart. `estimate_method` carries the
    finer claim (`labelled`, `off_product`, `portion_table`, …) and `value_low/point/high` carry
    the interval whole: a point would be a lie about precision (RULE-08).

    INV-1 holds by construction — every atom points at the capture the item was uttered in.
    """
    if resolved.get('components'):
        if capture_item_id is None:
            raise ValueError('fractional resolution requires persistent item identity')
        written=[]
        for component in resolved['components']:
            written.extend(persist_resolution(cur,{**resolved,**component,'components':[]},
                raw_capture_id=raw_capture_id,occurred_at=occurred_at,subject_day=subject_day,
                evidence_span=evidence_span,schema=schema,trust_level=trust_level,code_version=code_version,
                time_precision=time_precision,capture_item_id=capture_item_id,
                capture_component=component['component']))
        return written
    units = _registry_units(cur, resolved["nutrients"], schema)
    if time_precision not in ('exact','minute','hour','day','unknown'):
        raise ValueError('invalid nutrient event time precision')
    # REQ-NUT-032, ENFORCED rather than assumed. Until this line the column held the source's
    # claim (`usda_foundation`, `off_product`) for every non-branded resolution — outside the
    # five values the requirement enumerates, and outside the vocabulary `nutrition_display`
    # reads, which is why nothing could be wired to it. Raising here rather than writing an
    # unexpected value keeps the next such drift from being discovered a second time by a
    # display layer that quietly matches nothing.
    method = resolved.get("stored_method") or stored_estimate_method(
        source_claim=resolved.get("estimate_method"), grams_stated=False)
    if method not in REQ_NUT_032_METHODS:
        raise ValueError(
            f"REQ-NUT-032: estimate_method must be one of {sorted(REQ_NUT_032_METHODS)}; "
            f"refusing to store {method!r}")
    written = []
    for key, (low, point, high) in sorted(resolved["nutrients"].items()):
        if key not in units:
            # An unregistered metric is a schema question, not something to invent a unit for.
            raise LookupError(f"{key!r} is not in {schema}.metric_registry")
        if _already_stored(cur, raw_capture_id, key, subject_day, evidence_span, schema, capture_item_id, capture_component):
            continue
        unit, state_class = units[key]
        item_column = ', capture_item_id, capture_component' if capture_item_id is not None else ''
        item_value = ', %s, %s' if capture_item_id is not None else ''
        cur.execute(
            f"""insert into {schema}.atoms
                  (raw_capture_id, kind, metric_key, occurred_at, time_precision,
                   subject_day, subject_day_rule_version, presence,
                   value_low, value_point, value_high, estimate_method, unit, state_class,
                   trust_level, provenance, evidence_span, code_version{item_column})
                values (%s, 'consume', %s, %s, %s, %s, %s, 'observed',
                        %s, %s, %s, %s, %s, %s, %s, 'inferred', %s, %s{item_value})""",
            (raw_capture_id, key, occurred_at, time_precision, subject_day, SUBJECT_DAY_RULE_VERSION,
             low, point, high, method, unit, state_class,
             trust_level, evidence_span, code_version) + ((capture_item_id,capture_component) if capture_item_id is not None else ()))
        written.append(key)
    return written


def record_unresolved(cur, unresolved, *, raw_capture_id, subject_day, schema="core",
                      extraction_request_id=None, item_index=None):
    """An item nothing resolved -> one `unresolved_items` row (REQ-NUT-024, REQ-NUT-040).

    Returns the `item_id`, or None when the item is already open — a nightly re-run must not
    grow Joe's review list by one row per night for the same sandwich.

    **An operations failure is not put on the review list.** When `review_reason` is None the
    cascade is saying nothing could be ASKED — no key, everything rate limited — and the item
    is recorded with that reason so the history is complete, but `tried` says plainly that no
    source was consulted. REQ-NUT-027: unresolved is a normal outcome, never an error state.
    """
    if (extraction_request_id is None) != (item_index is None):
        raise ValueError('complete extracted-item identity required')
    identity = ' AND extraction_request_id=%s AND capture_item_index=%s' if extraction_request_id is not None else ''
    identity_args = (extraction_request_id,item_index) if extraction_request_id is not None else ()
    cur.execute(f"""select item_id,tried from {schema}.unresolved_items
                     where item_text = %s and subject_day = %s and resolved_at is null
                       and raw_capture_id is not distinct from %s
                       {identity}
                     limit 1""", (unresolved.item_text, subject_day, raw_capture_id)+identity_args)
    existing = cur.fetchone()
    tried = json.dumps({"reason": unresolved.reason, "review_reason": unresolved.review_reason,
                        "brand": unresolved.brand, "tried": list(unresolved.tried)},
                       default=str)
    if existing:
        if existing[1]!=json.loads(tried):
            cur.execute(f'UPDATE {schema}.unresolved_items SET tried=%s::jsonb WHERE item_id=%s',
                        (tried,existing[0]))
        return None
    columns = ',extraction_request_id,capture_item_index' if identity_args else ''
    placeholders = ',%s,%s' if identity_args else ''
    cur.execute(
        f"""insert into {schema}.unresolved_items
              (raw_capture_id, item_text, subject_day, tried{columns})
            values (%s, %s, %s, %s::jsonb{placeholders}) returning item_id""",
        (raw_capture_id, unresolved.item_text, subject_day, tried)+identity_args)
    return cur.fetchone()[0]


def close_capture_unresolved(cur, *, capture_id, extraction_request_id, item_index, schema='core'):
    """A later reference resolves this exact item, not every equal food phrase."""
    cur.execute(f'''UPDATE {schema}.unresolved_items SET resolved_at=clock_timestamp(),resolved_by='later_source'
        WHERE raw_capture_id=%s AND extraction_request_id=%s AND capture_item_index=%s AND resolved_at IS NULL''',
        (capture_id,extraction_request_id,item_index))

# ---------------------------------------------------------------- the review list closes (§D.3)

class CorrectionRefused(Exception):
    """Joe's answer could not be accepted as given. Never silently adjusted (RULE-01)."""


def accept_correction(cur, item_id, nutrients_per_100g, *, supplied_by,
                      canonical_name=None, serving_g=None, brand=None, schema="core"):
    """REQ-NUT-017. Joe answers a review-list item, and the answer becomes a `joe` cache row.

    Until this existed, `unresolved_items` was WRITE-ONLY. `record_unresolved` filled it every
    night and nothing could ever empty it: there was no path from Joe's answer back into
    `foods_cache`, so the same sandwich was re-asked, re-refused and re-listed indefinitely.
    RULE-10 says a human correction permanently outranks a guess, and `lookup_cached` already
    orders by `SOURCE_PRECEDENCE` with `joe` first — but nothing wrote the row that ordering
    exists to prefer.

    Three writes, which REQ-NUT-017 names together because any one alone leaves the loop open:

      1. a `foods_cache` row with `source = 'joe'` — the answer itself;
      2. its alias, via `remember_alias`, so the phrase AS UTTERED resolves next time rather
         than only the canonical name Joe happened to type (REQ-NUT-004);
      3. `resolved_at` / `resolved_by = 'joe'` on the item, so it leaves the review list.

    **THIS IS THE ONE PLACE A NUTRIENT VALUE ENTERS FROM OUTSIDE A SOURCE, AND IT IS A HUMAN
    PATH ONLY.** RULE-09 keeps models from computing or supplying figures, and the requirement
    that a human may do so is not a loophole in it. `supplied_by` is mandatory, must be `joe`,
    and is stored on the row: a call site that cannot name a person cannot use this function,
    and a value whose origin is unrecorded is exactly the `inferred`-as-`measured` confusion
    INV-5 exists to prevent. `resolve_item` never calls this; `tools/resolve_nutrition.py`
    never calls it; no model-facing path reaches it.

    Idempotent. Answering an item that is already resolved returns None and writes nothing,
    because a review list that re-opens on a second submission is a review list that grows.
    """
    if supplied_by != "joe":
        # The column's CHECK already restricts `resolved_by`; refusing here means the refusal
        # names the rule rather than surfacing as a constraint violation three writes later.
        raise CorrectionRefused(
            f"REQ-NUT-017 / RULE-09: a nutrient value may be supplied by Joe and by nobody "
            f"else; supplied_by={supplied_by!r}")

    cur.execute(f"""select item_text, resolved_at from {schema}.unresolved_items
                     where item_id = %s""", (item_id,))
    found = cur.fetchone()
    if found is None:
        raise CorrectionRefused(f"no unresolved item {item_id!r} to answer")
    item_text, resolved_at = found
    if resolved_at is not None:
        return None                       # already answered; answering twice changes nothing

    cleaned = _screen_supplied_nutrients(nutrients_per_100g)
    name = str(canonical_name or item_text).strip()
    if not name:
        raise CorrectionRefused("a correction needs a name to key `foods_cache` on")
    if serving_g is not None and float(serving_g) <= 0:
        raise CorrectionRefused(f"serving_g must be positive, got {serving_g!r}")

    row = {"canonical_name": name, "source": "joe",
           # `foods_cache` is UNIQUE on (canonical_name, source, source_id). Keying Joe's row
           # on the NAME rather than on `item_id` means one `joe` row per food, so answering
           # the same food on two different nights updates nothing and duplicates nothing —
           # rather than two rows whose ordering `lookup_cached` would have to break a tie on.
           "source_id": name.lower(),
           "brand": brand, "nutrients_per_100g": cleaned, "serving_g": serving_g,
           "fetched_at": dt.datetime.now(dt.timezone.utc),
           "raw": {"supplied_by": supplied_by, "requirement": "REQ-NUT-017",
                   "answered_item_id": str(item_id), "item_text_as_uttered": item_text,
                   "code_version": CODE_VERSION}}
    food_id = nutrition_off.insert_cache_row(cur, row, schema=schema)
    alias_id = remember_alias(cur, item_text, row, food_id=food_id, schema=schema)

    cur.execute(f"""update {schema}.unresolved_items
                       set resolved_at = now(), resolved_by = 'joe'
                     where item_id = %s and resolved_at is null""", (item_id,))
    return {"food_id": food_id, "alias_id": alias_id, "canonical_name": name,
            "nutrients_per_100g": cleaned, "item_text": item_text}


def _screen_supplied_nutrients(nutrients):
    """A supplied nutrient map, or `CorrectionRefused`. Nothing is coerced or clamped.

    Joe is authoritative about what he ate; he is not exempt from arithmetic. A typed `3000`
    where `300` was meant is the ordinary failure here, and it would enter the cache as a
    `joe` row — the one source nothing else outranks — and stay wrong until he noticed. So the
    same physical ceilings every source payload is screened against apply, and a value past
    them is REFUSED rather than dropped: a source record with one unreadable field is still
    worth keeping, but a person's answer with a rejected field is a question to re-ask.
    """
    if not isinstance(nutrients, dict) or not nutrients:
        raise CorrectionRefused("a correction must supply at least one nutrient")
    unknown = sorted(set(nutrients) - set(NUTRIENT_KEYS))
    if unknown:
        raise CorrectionRefused(
            f"not nutrients this system stores: {unknown}; expected some of "
            f"{list(NUTRIENT_KEYS)}")
    cleaned = {}
    for key, value in nutrients.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise CorrectionRefused(f"{key}={value!r} is not a number") from None
        if number != number or number in (float("inf"), float("-inf")):
            raise CorrectionRefused(f"{key}={value!r} is not a finite number")
        if number < 0:
            raise CorrectionRefused(f"{key}={number} is negative")
        ceiling = nutrition_off.CEILING_PER_100G.get(key)
        if ceiling is not None and number > ceiling:
            raise CorrectionRefused(
                f"{key}={number} per 100 g exceeds the physical ceiling {ceiling}; 100 g of "
                f"anything cannot contain that. Check the units and the per-100 g basis.")
        cleaned[key] = number
    return cleaned
