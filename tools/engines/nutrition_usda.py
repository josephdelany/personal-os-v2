"""B12 §D.2/D.3 — the USDA FoodData Central source adapter (REQ-NUT-005..009, 012..014).

The two USDA legs of `nutrition_cascade.SOURCE_PRECEDENCE` — `usda_branded` and
`usda_foundation` — were the last part of B12 still unwritten. ADR-0106's "What remains" said
so, and gave two reasons: no api.data.gov key, and an unrecorded egress target. **The second
reason is stale.** Migration 0050 already inserts `api.nal.usda.gov` into
`config.egress_allowlist`, so RULE-29's recording requirement was met when the table was
created. Only the key is outstanding, and a missing key is a runtime configuration fact, not a
reason to leave the client unwritten: without it every leg raises `NotConfigured` exactly as
before, and with it the same code path answers. The transport is a parameter, so every
behaviour below is provable without Joe's registration.

WHY THIS IS A SEPARATE MODULE FROM `nutrition_off`. The two sources agree on almost nothing.
Open Food Facts is crowd-sourced, keyless, rationed per minute, and reports nutrients in a flat
`nutriments` dict keyed by name. FoodData Central is authoritative, keyed, rationed per HOUR,
and reports nutrients as a LIST of records keyed by a numeric nutrient id whose shape differs
between the search and detail endpoints. Sharing a parser between them would mean a function
whose every branch asks which source it is looking at. What they genuinely share — the physical
ceilings a per-100 g figure cannot exceed, and the `foods_cache` insert — is imported from
`nutrition_off` rather than copied, so neither can drift.

THE THREE RATION RULES, WHICH ARE NOT THE SAME RULE.

  * REQ-NUT-009 is a QUOTA: 900 requests in the trailing 60 minutes and the resolver defers to
    the next nightly run. It is ours to count, and it is counted across BOTH legs, because
    api.data.gov meters the key and one key serves both datasets. Two windows of 900 would
    permit 1,800.
  * REQ-NUT-012 is a REFUSAL: the provider answered 429. It stops USDA requests for 60 minutes
    — again across both legs, for the same reason — and the items stay unresolved rather than
    borrowing another food's numbers.
  * REQ-NUT-008 is a TTL on the stored row, and it differs BY DATASET: a Foundation or SR
    Legacy analysis does not expire, because a laboratory measurement of a generic food is not
    superseded by the passage of time. A Branded label does expire at 365 days, because a
    manufacturer can reformulate a product without renaming it.

Conflating any two of these would be wrong in a way that looks fine: a quota deferral reported
as a 429 would put the source in a penalty box it was never sent to, and a Branded row treated
as non-expiring would serve a discontinued recipe forever.

WHY A SEARCH IS NOT A MATCH (REQ-NUT-024, REQ-NUT-025). FoodData Central's `/foods/search` is a
relevance ranker: it returns something for almost any query, ordered by a score this system has
no access to and no way to audit. Taking `foods[0]` would resolve "chicken burrito" to whatever
happened to rank first that day. So the ranking is DISCARDED and `select_exact_match` requires
the description — and, for a branded query, the brand — to equal the query after
normalisation. No exact match is `UsdaNotFound`; several distinct ones are `UsdaAmbiguous`, a
question for Joe rather than a tie-break for the resolver.

REQ-NUT-006 / REQ-NUT-007. Nothing here downloads, mirrors or crawls. `PAGE_SIZE` is capped and
there is no pagination: one search returns one page, and a food that is not on it is not found.
The bulk-download endpoints are deliberately absent from this module.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import time
from collections import deque

from lib import egress
from lib.mass_units import MASS_UNITS_TO_G
from tools.engines import nutrition_off


CODE_VERSION = "nutrition-usda-v1"

BRANDED = "usda_branded"
FOUNDATION = "usda_foundation"
SOURCES = (BRANDED, FOUNDATION)

HOST = "api.nal.usda.gov"                        # in config.egress_allowlist (migration 0050)
SEARCH_URL = f"https://{HOST}/fdc/v1/foods/search"
FOOD_URL = f"https://{HOST}/fdc/v1/food/{{fdc_id}}"

# The `dataType` filter each leg sends. Foundation asks for SR Legacy too: both are laboratory
# analyses of generic foods, both are non-expiring under REQ-NUT-008, and SR Legacy is where
# most ordinary ingredients still live now that Foundation is being rebuilt food by food.
DATA_TYPES = {BRANDED: ("Branded",), FOUNDATION: ("Foundation", "SR Legacy")}

# REQ-NUT-009. The api.data.gov default for a signed-up key is 1,000 requests per hour; the
# requirement stops at 900 so the last hundred remain for anything else on the same key.
REQUESTS_PER_HOUR = 900
QUOTA_WINDOW_S = 60 * 60
# REQ-NUT-012. A 429 stops USDA for an hour. Same duration as the quota window by coincidence
# of policy, not by derivation, so it is its own constant.
RATE_LIMIT_COOLDOWN_S = 60 * 60

# REQ-NUT-006: one page, capped. Raising this does not find more foods, it downloads more of
# the database, which is the thing the requirement forbids.
PAGE_SIZE = 25

# REQ-NUT-008. Branded expires; Foundation and SR Legacy do not.
BRANDED_TTL_DAYS = 365

API_KEY_ENV = ("USDA_FDC_API_KEY", "PERSONAL_OS_USDA_API_KEY")

# The message the two legs report when the key is absent. It names api.data.gov because that is
# where Joe registers, and `tests/test_nutrition_integration.py` asserts on that token: a
# refusal whose text does not say what to do about it is a refusal nobody acts on.
NO_API_KEY = ("no api.data.gov key: set one of " + " / ".join(API_KEY_ENV) +
              " (register at https://api.data.gov/signup/ — free, no personal data required)")

KJ_PER_KCAL = 4.184                              # definition, not a measurement

# FoodData Central nutrient ids. The tuple is an ORDER OF PREFERENCE, not a set: the first id
# present wins. `kcal` prefers the declared 1008 over the Atwater-derived 2047/2048 because a
# declared energy is a measurement and an Atwater figure is a computation from other figures
# already in this row — preferring the latter would double-count their error.
NUTRIENT_IDS = {
    "kcal":      (1008, 2047, 2048),
    "protein_g": (1003,),
    "carbs_g":   (1005, 1050),       # by difference, then by summation
    "fat_g":     (1004,),
    "fiber_g":   (1079, 2033),       # total dietary, then AOAC 2011.25
    "sugar_g":   (2000, 1063),       # total including NLEA, then total NLEA
    "sodium_mg": (1093,),
}
ENERGY_KJ_ID = 1062                  # converted to kcal only when no kcal id is present

# The one unit each key is STORED in. FDC states a unit per nutrient and it is not always this
# one, so it is checked rather than assumed: a sodium figure in grams read as milligrams is a
# thousand-fold error that looks like an ordinary number.
STORED_UNIT = {
    "kcal": "kcal", "protein_g": "g", "carbs_g": "g", "fat_g": "g",
    "fiber_g": "g", "sugar_g": "g", "sodium_mg": "mg",
}
# Unit conversions FDC actually emits. Anything outside this table is DROPPED with its reason
# rather than coerced, because a unit nobody anticipated is a parsing failure, not a scale.
_UNIT_SCALE = {
    ("g", "mg"): 1000.0, ("mg", "g"): 0.001, ("µg", "mg"): 0.001, ("ug", "mg"): 0.001,
    ("mcg", "mg"): 0.001, ("kj", "kcal"): 1.0 / KJ_PER_KCAL,
}

_WORD_RE = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------- outcomes
#
# Deliberately parallel to `nutrition_off`'s hierarchy, because `nutrition.UsdaLeg` translates
# both into the same two cascade outcomes and a reader comparing the two modules should find
# the same shape. They are separate classes rather than a shared base because an `except
# OffUnusable` that silently swallowed a USDA failure would be a real bug and the type system
# is the cheapest place to prevent it.

class UsdaUnusable(Exception):
    """Base: FoodData Central produced no usable record. Carries the `tried` entry verbatim."""

    def __init__(self, source, reason, detail=None):
        self.source, self.reason, self.detail = source, reason, detail
        super().__init__(f"{type(self).__name__}: {source}: {reason}")

    def tried_entry(self):
        entry = {"source": self.source, "hit": False, "reason": self.reason}
        if self.detail is not None:
            entry["detail"] = self.detail
        return entry


class UsdaNotFound(UsdaUnusable):
    """No food in this dataset matched the query exactly. A gap, and a settled one."""


class UsdaAmbiguous(UsdaUnusable):
    """Several distinct foods matched exactly. Joe picks; the system does not (REQ-NUT-025)."""


class UsdaMalformed(UsdaUnusable):
    """The record exists and its nutrition cannot be read without inventing something."""


class UsdaTransient(UsdaUnusable):
    """The request did not complete. Defer it; this is not a statement about the food."""


class UsdaRateLimited(UsdaTransient):
    """REQ-NUT-012 (the provider said 429) or REQ-NUT-009 (our own quota). Both defer.

    `provider` separates them, because they are different facts about the world and only one of
    them is a complaint from api.data.gov. Both stop USDA for an hour, so the cascade treats
    them alike; the `tried` record does not.
    """

    def __init__(self, source, kind, retry_after, *, provider):
        self.retry_after, self.provider = retry_after, provider
        super().__init__(source, f"rate_limited_{kind}",
                         {"retry_after_s": round(float(retry_after), 3), "provider": provider})


class ApiKeyMissing(Exception):
    """REQ-NUT-005/013/014 cannot be satisfied, so no request is issued.

    Not a `UsdaUnusable`: this is a misconfiguration of *this* system, not an outcome of a
    lookup, and writing it into `unresolved_items` would put a food on Joe's review list to
    answer a question about an environment variable. The key lives in the environment because
    a public Git repository is a third party (RULE-29) and a key in a source file is a
    credential committed to it.
    """


def api_key(env=None):
    """The api.data.gov key, or `ApiKeyMissing`. Never logged, never returned in an error."""
    env = os.environ if env is None else env
    key = next((env[k].strip() for k in API_KEY_ENV if env.get(k, "").strip()), None)
    if not key:
        raise ApiKeyMissing(NO_API_KEY)
    return key


# ---------------------------------------------------------------- the ration (REQ-NUT-009/012)

class Quota:
    """One api.data.gov key's hour, shared by both USDA legs.

    REQ-NUT-009's window and REQ-NUT-012's cooldown live together because they gate the same
    thing and a caller that held one without the other would satisfy half a requirement. Both
    REFUSE rather than sleep: the caller is a nightly batch with other items to resolve, and a
    held thread converts a rationing rule into a latency bug.

    The clock is a parameter throughout, so the boundary at exactly 900 and the minute a
    cooldown expires are assertions a test makes rather than waits it endures.
    """

    def __init__(self, max_requests=REQUESTS_PER_HOUR, window_seconds=QUOTA_WINDOW_S,
                 cooldown_seconds=RATE_LIMIT_COOLDOWN_S):
        self.max_requests = int(max_requests)
        self.window = float(window_seconds)
        self.cooldown_seconds = float(cooldown_seconds)
        self._stamps = deque()
        self._blocked_until = None

    # -- REQ-NUT-012 ------------------------------------------------------
    def trip(self, now=None):
        """api.data.gov answered 429. No USDA request for an hour, on either leg."""
        now = time.monotonic() if now is None else float(now)
        self._blocked_until = now + self.cooldown_seconds

    def blocked_for(self, now=None):
        """Seconds remaining in the 429 cooldown, or 0.0."""
        if self._blocked_until is None:
            return 0.0
        now = time.monotonic() if now is None else float(now)
        return max(0.0, self._blocked_until - now)

    # -- REQ-NUT-009 ------------------------------------------------------
    def acquire(self, source, now=None):
        """Record one request, or raise `UsdaRateLimited`.

        The 429 cooldown is checked BEFORE the quota window. A source in its penalty box must
        not spend a quota slot to discover that, and the reason Joe is given should be the
        provider's refusal rather than our own arithmetic.
        """
        now = time.monotonic() if now is None else float(now)
        blocked = self.blocked_for(now)
        if blocked > 0:
            raise UsdaRateLimited(source, "provider", blocked, provider=True)
        while self._stamps and now - self._stamps[0] >= self.window:
            self._stamps.popleft()
        if len(self._stamps) >= self.max_requests:
            # REQ-NUT-009: defer to the next nightly run. The retry-after is when the oldest
            # request leaves the window, which is the earliest moment a slot actually exists.
            #
            # A quota of ZERO has no oldest request, and reading `_stamps[0]` raised
            # `IndexError` — which escapes `UsdaLeg`'s `except UsdaTransient` and takes the
            # whole nightly batch down instead of deferring one item. A ceiling of zero is a
            # legitimate way to say "do not call USDA at all", so the empty window reports the
            # full window rather than crashing.
            retry_after = self.window - (now - self._stamps[0]) if self._stamps else self.window
            raise UsdaRateLimited(source, "quota", retry_after, provider=False)
        self._stamps.append(now)

    def __len__(self):
        return len(self._stamps)


# ---------------------------------------------------------------- matching

def normalise_name(text):
    """Lowercase, punctuation-free, single-spaced. The comparison key, never stored."""
    return _WORD_RE.sub(" ", str(text or "").lower()).strip()


def _descriptions(food):
    """Every string this food could reasonably be called."""
    return [food.get("description"), food.get("lowercaseDescription"),
            food.get("additionalDescriptions")]


def _brand_tokens(food):
    """Every string that could be this food's brand. `brandOwner` is the legal manufacturer and
    `brandName` the marketing name; they differ often enough that matching only one loses
    products ("Frito-Lay" owns "Doritos")."""
    return [food[key] for key in ("brandOwner", "brandName")
            if isinstance(food.get(key), str) and food[key].strip()]


def select_exact_match(query, foods, source, *, brand=None):
    """The one food whose description — and brand, when given — equals the query.

    Raises `UsdaNotFound` when nothing matches exactly and `UsdaAmbiguous` when several
    distinct `fdcId`s do. FDC's relevance order is deliberately not consulted: see the module
    docstring. Sorting by `fdcId` before the ambiguity check makes the outcome identical across
    runs regardless of the order the API returned.
    """
    want = normalise_name(query)
    want_brand = normalise_name(brand) if brand else None
    if not want:
        raise UsdaNotFound(source, "empty_query")
    hits = []
    for food in foods or []:
        if not isinstance(food, dict):
            continue
        if not any(normalise_name(d) == want for d in _descriptions(food) if d):
            continue
        if want_brand is not None and not any(
                normalise_name(b) == want_brand for b in _brand_tokens(food) if b):
            continue
        hits.append(food)
    if not hits:
        raise UsdaNotFound(source, "no_exact_name_match", {"candidates": len(foods or [])})
    hits.sort(key=lambda f: str(f.get("fdcId") or ""))
    distinct = {str(f.get("fdcId") or "") for f in hits}
    if len(distinct) > 1:
        raise UsdaAmbiguous(source, "ambiguous_exact_match",
                            {"fdc_ids": sorted(distinct)[:5], "n": len(distinct)})
    return hits[0]


# ---------------------------------------------------------------- parsing

def _number(value):
    """A float, or None. A blank string and a non-numeric string are None, not zero."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def _nutrient_records(food):
    """`foodNutrients` normalised to `(id, amount, unit)`, across BOTH FDC shapes.

    The search endpoint returns a flat record — `{"nutrientId": 1008, "value": 539,
    "unitName": "KCAL"}` — and the detail endpoint a nested one — `{"nutrient": {"id": 1008,
    "unitName": "kcal"}, "amount": 539}`. The same food read through the two endpoints must
    parse identically; handling only the shape this module happens to request would make the
    parser silently endpoint-specific.
    """
    out = []
    for record in food.get("foodNutrients") or []:
        if not isinstance(record, dict):
            continue
        nested = record.get("nutrient") if isinstance(record.get("nutrient"), dict) else {}
        nutrient_id = record.get("nutrientId", nested.get("id"))
        amount = record.get("value", record.get("amount", nested.get("amount")))
        unit = record.get("unitName", nested.get("unitName"))
        try:
            nutrient_id = int(nutrient_id)
        except (TypeError, ValueError):
            continue
        out.append((nutrient_id, _number(amount), str(unit or "").strip()))
    return out


def _convert(value, from_unit, to_unit):
    """`value` in `to_unit`, or None when the pair is not one FDC is known to emit."""
    have, want = str(from_unit or "").strip().lower(), to_unit.lower()
    if not have:
        return None
    if have == want:
        return value
    scale = _UNIT_SCALE.get((have, want))
    return None if scale is None else value * scale


def parse_food(food, source):
    """An FDC payload -> per-100 g nutrients in this system's units, or `UsdaMalformed`.

    Takes the payload and the dataset name, and nothing else. There is no argument here
    through which a caller — or a model behind one — could supply a nutrient value (RULE-09,
    REQ-NUT-060/061).

    Branded and Foundation records both state nutrients per 100 g, so there is no basis
    conversion to do and none is invented. A Branded record additionally carries a serving
    size, which is stored for REQ-NUT-019's serving arithmetic but never used to rescale the
    nutrients: `labelNutrients` (the per-serving block) is deliberately not read, because
    mixing a per-serving figure into a per-100 g row is the error that makes everything
    downstream wrong by the size of a serving.
    """
    if not isinstance(food, dict) or not food:
        raise UsdaMalformed(source, "empty_food")

    fdc_id = food.get("fdcId")
    if fdc_id in (None, ""):
        # REQ-NUT-005: without the fdcId the number is unauditable, so the row is not written.
        raise UsdaMalformed(source, "no_fdc_id")
    fdc_id = str(fdc_id)

    name = next((str(d).strip() for d in _descriptions(food) if str(d or "").strip()), None)
    if not name:
        raise UsdaMalformed(source, "no_description")      # nothing to key `foods_cache` on

    records = _nutrient_records(food)
    if not records:
        raise UsdaMalformed(source, "no_food_nutrients")
    by_id = {}
    for nutrient_id, amount, unit in records:
        by_id.setdefault(nutrient_id, (amount, unit))

    nutrients, provenance, dropped = {}, {}, []
    for key, ids in NUTRIENT_IDS.items():
        for nutrient_id in ids:
            if nutrient_id not in by_id:
                continue
            amount, unit = by_id[nutrient_id]
            if amount is None:
                dropped.append({"key": key, "id": nutrient_id, "why": "not_a_number"})
                continue
            converted = _convert(amount, unit, STORED_UNIT[key])
            if converted is None:
                # An unrecognised unit is a parsing failure. Assuming it was the expected one
                # would turn "we could not read this" into a number nobody published.
                dropped.append({"key": key, "id": nutrient_id, "why": "unexpected_unit",
                                "unit": unit})
                continue
            nutrients[key] = converted
            provenance[key] = {"fdc_nutrient_id": nutrient_id, "unit": unit}
            break

    # Energy in kJ only. Converted, and the conversion is recorded, because a kcal figure
    # derived from kJ is not the label's own kcal and a later reader must be able to tell.
    if "kcal" not in nutrients and ENERGY_KJ_ID in by_id:
        amount, unit = by_id[ENERGY_KJ_ID]
        converted = _convert(amount, unit or "kj", "kcal")
        if converted is not None:
            nutrients["kcal"] = converted
            provenance["kcal"] = {"fdc_nutrient_id": ENERGY_KJ_ID, "unit": unit,
                                  "converted_from_kj": True}

    # The same physical ceilings `nutrition_off` screens on, imported rather than copied. A
    # value past them is a transcription error in the source record; it is DROPPED with its
    # reason, never clamped, because a clamped value is a fabricated one (RULE-01).
    for key, value in sorted(nutrients.items()):
        ceiling = nutrition_off.CEILING_PER_100G.get(key)
        why = None
        if value < 0:
            why = {"key": key, "value": value, "why": "negative"}
        elif ceiling is not None and value > ceiling:
            why = {"key": key, "value": value, "why": "above_physical_ceiling",
                   "ceiling": ceiling}
        if why is not None:
            dropped.append(why)
            nutrients.pop(key)
            provenance.pop(key, None)

    macro_sum = sum(nutrients.get(k, 0.0) for k in ("protein_g", "carbs_g", "fat_g", "fiber_g"))
    if macro_sum > nutrition_off.MACRO_SUM_CEILING:
        raise UsdaMalformed(source, "macros_exceed_100g",
                            {"sum": round(macro_sum, 2)})
    if not nutrients:
        raise UsdaMalformed(source, "no_readable_nutrient",
                            {"dropped": dropped[:5]})

    brand = next((str(b).strip() for b in _brand_tokens(food) if str(b or "").strip()), None)
    if source == BRANDED and not brand:
        # REQ-NUT-014. `labelled` is a claim that a manufacturer published this number. Without
        # the brand owner there is nothing to re-check it against, and `nutrition_cascade`
        # raises on such a match anyway — refusing here turns that crash into an outcome.
        raise UsdaMalformed(source, "branded_without_brand_owner", {"fdc_id": fdc_id})
    if source == FOUNDATION:
        # A Foundation or SR Legacy food is generic by definition. Carrying a brand would let
        # REQ-NUT-016's branded-source check be satisfied by a generic row.
        brand = None

    serving_g, serving_note = _serving_mass(food)

    return {
        "canonical_name": name,
        "source": source,
        "source_id": fdc_id,                    # REQ-NUT-005
        "brand": brand,
        "nutrients_per_100g": {k: round(v, 4) for k, v in sorted(nutrients.items())},
        "serving_g": serving_g,
        "data_type": str(food.get("dataType") or "").strip() or None,
        "nutrient_provenance": provenance,
        "dropped": dropped,
        "notes": [serving_note] if serving_note else [],
    }


def _serving_mass(food):
    """`servingSize` in grams, or `(None, reason)`. Volumes are not masses and are not guessed.

    A Branded record states `servingSize` with `servingSizeUnit`. When that unit is a volume
    the mass depends on the product's density, which FDC does not publish — so the serving is
    left unknown and says why, rather than being converted at the density of water. A drink
    resolved at 1 g/ml would be wrong by whatever its sugar contributes.
    """
    value = _number(food.get("servingSize"))
    unit = str(food.get("servingSizeUnit") or "").strip().lower()
    if value is None or value <= 0:
        return None, None
    if unit in ("g", "gram", "grams", "mg", "kg", "oz"):
        return round(value * MASS_UNITS_TO_G[unit], 4), None
    if unit in ("ml", "l", "cl", "dl"):
        return None, f"serving_stated_in_volume_{unit}"
    return None, f"serving_unit_unrecognised_{unit or 'blank'}" if unit else None


# ---------------------------------------------------------------- the cache row (REQ-NUT-003)

def cache_row(food, source, parsed=None, *, fetched_at=None):
    """The `core.foods_cache` row this source produces, in migration 0050's columns.

    `raw` keeps the payload so a changed reading can be re-derived without spending another
    request (ADR-0066 decision 2), and keeps the dataset name alongside it so REQ-NUT-008's
    differing TTLs can be applied to a row read back from the cache.
    """
    parsed = parse_food(food, source) if parsed is None else parsed
    return {
        "canonical_name": parsed["canonical_name"],
        "source": parsed["source"],
        "source_id": parsed["source_id"],
        "brand": parsed["brand"],
        "nutrients_per_100g": parsed["nutrients_per_100g"],
        "serving_g": parsed["serving_g"],
        "fetched_at": fetched_at or dt.datetime.now(dt.timezone.utc),
        "raw": {"usda_food": food, "parse": {
            "code_version": CODE_VERSION, "data_type": parsed["data_type"],
            "nutrient_provenance": parsed["nutrient_provenance"],
            "dropped": parsed["dropped"], "notes": parsed["notes"]}},
    }


def needs_refetch(source, fetched_at, now=None, data_type=None):
    """REQ-NUT-008. Branded expires at 365 days; Foundation and SR Legacy never do.

    `data_type` is consulted when given because the dataset is the thing the requirement names,
    and a row's `source` is this system's bucket rather than FDC's label.
    """
    if data_type:
        expiring = str(data_type).strip().lower() == "branded"
    else:
        expiring = source == BRANDED
    if not expiring:
        return False
    if fetched_at is None:
        return True
    now = now or dt.datetime.now(dt.timezone.utc)
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=dt.timezone.utc)
    return (now - fetched_at) > dt.timedelta(days=BRANDED_TTL_DAYS)


# The `foods_cache` insert is source-independent and already written; importing it keeps one
# ON CONFLICT clause in the repository rather than two that must be kept in step (INV-1).
insert_cache_row = nutrition_off.insert_cache_row


# ---------------------------------------------------------------- the network path

def _is_429(exc):
    """Did this transport failure carry HTTP 429? REQ-NUT-012 turns on this and nothing else.

    `urllib.error.HTTPError` exposes `.code`; other transports (and the injected ones tests
    use) may expose `.status`. Both are checked, and a failure that carries neither is a
    transient, not a rate limit — guessing 429 from a message would put the source in an
    hour-long penalty box on the strength of a string.
    """
    for attribute in ("code", "status"):
        try:
            if int(getattr(exc, attribute)) == 429:
                return True
        except (AttributeError, TypeError, ValueError):
            continue
    return False


def _get(cur, url, purpose, params, source, *, quota, now, env, timeout, schema, ops, config,
         _transport):
    """Every request this module makes goes through `lib.egress.get_json` and none other.

    The order of the three steps is deliberate and mirrors `nutrition_off._get`. The key is
    read FIRST, so a missing key costs no quota; the REQ-NUT-009 slot is taken SECOND, so a
    slot is spent only when a request is actually about to be issued; the request goes LAST.

    THE API KEY IS A QUERY PARAMETER AND THAT IS FDC'S DESIGN, NOT A CHOICE MADE HERE.
    `lib.egress.get_json` records the parameter COUNT and the path in `ops.egress_log`, never
    the values, so the key does not reach the log. It does not reach an exception either:
    `UsdaTransient` carries the exception's type name and nothing from the URL.

    `PayloadRefused` is re-raised untouched — it is either the allowlist refusing a host or the
    RULE-29 screen refusing a payload, and a privacy refusal recorded as "USDA was flaky" is a
    privacy failure filed as a network one.
    """
    params = dict(params)
    params["api_key"] = api_key(env)
    quota.acquire(source, now)
    try:
        return egress.get_json(cur, url, purpose, params=params, headers={
            "Accept": "application/json"}, timeout=timeout, schema=schema, ops=ops,
            config=config, _transport=_transport)
    except egress.PayloadRefused:
        raise
    except UsdaUnusable:
        raise
    except Exception as e:
        if _is_429(e):
            # REQ-NUT-012. Stop USDA — both legs — for 60 minutes.
            quota.trip(now)
            raise UsdaRateLimited(source, "provider", quota.cooldown_seconds,
                                  provider=True) from e
        raise UsdaTransient(source, "request_failed", {"error": type(e).__name__}) from e


def search_foods(cur, query, source, *, quota, brand=None, now=None, env=None, timeout=20,
                 schema="core", ops="ops", config="config", _transport=None):
    """One page of FDC search results for one dataset. Returns the candidate list, unfiltered.

    REQ-NUT-013: the brand or restaurant token is appended to the query string for a Branded
    search, because FDC indexes the brand into the same free-text field as the description and
    a query without it ranks the whole category. It is NOT sent for a Foundation search, where
    a brand token can only make a generic food harder to find.

    The filtering is `select_exact_match`, kept separate so the matching rule can be tested
    exhaustively against fixed candidate lists with no transport at all.
    """
    text = str(query or "").strip()
    if not text:
        raise UsdaNotFound(source, "empty_query")
    if source == BRANDED and brand:
        text = f"{str(brand).strip()} {text}"
    body = _get(cur, SEARCH_URL, f"nutrition:{source}_search",
                {"query": text, "dataType": ",".join(DATA_TYPES[source]),
                 "pageSize": PAGE_SIZE, "pageNumber": 1, "requireAllWords": "true"},
                source, quota=quota, now=now, env=env, timeout=timeout, schema=schema,
                ops=ops, config=config, _transport=_transport)
    if not isinstance(body, dict) or not isinstance(body.get("foods"), list):
        raise UsdaMalformed(source, "search_response_without_foods")
    return body["foods"]


def fetch_food(cur, fdc_id, source, *, quota, now=None, env=None, timeout=20, schema="core",
               ops="ops", config="config", _transport=None):
    """REQ-NUT-005 — one food by its `fdcId`. Returns the raw payload.

    Used to re-read a row whose Branded TTL has expired (REQ-NUT-008) without spending a search
    slot on a food whose identity is already known.
    """
    identifier = str(fdc_id or "").strip()
    if not identifier.isdigit():
        raise UsdaNotFound(source, "not_an_fdc_id", {"given": identifier[:16]})
    body = _get(cur, FOOD_URL.format(fdc_id=identifier), f"nutrition:{source}_read",
                {"format": "abridged"}, source, quota=quota, now=now, env=env, timeout=timeout,
                schema=schema, ops=ops, config=config, _transport=_transport)
    if not isinstance(body, dict) or not body:
        raise UsdaMalformed(source, "response_not_an_object")
    if body.get("fdcId") in (None, ""):
        raise UsdaNotFound(source, "fdc_id_not_found", {"fdc_id": identifier})
    return body


def lookup_by_name(cur, query, source, *, brand=None, **kw):
    """Name (+ optional brand token) -> a `foods_cache` row ready to insert, or a refusal."""
    fetched_at = kw.pop("fetched_at", None)
    foods = search_foods(cur, query, source, brand=brand, **kw)
    match = select_exact_match(query, foods, source, brand=brand)
    return cache_row(match, source, fetched_at=fetched_at)


def lookup_by_fdc_id(cur, fdc_id, source, **kw):
    """`fdcId` -> a `foods_cache` row ready to insert. The caller owns the cascade order."""
    fetched_at = kw.pop("fetched_at", None)
    return cache_row(fetch_food(cur, fdc_id, source, **kw), source, fetched_at=fetched_at)
