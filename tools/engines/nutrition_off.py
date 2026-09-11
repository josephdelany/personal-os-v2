"""Open Food Facts: a barcode or a name becomes a `foods_cache` row, or it becomes nothing.

B12, REQ-NUT §D.1/§D.2/§D.5, ADR-0066. This is the source-specific half of steps 2 and 5 of
REQ-NUT-001 — barcode lookup and text search against Open Food Facts. It does not own the
resolution order, the interval widths or the atom write; `tools/engines/nutrition.py` owns
those and this module never restates them. What it owns is the one thing a source parser is
for: turning a third party's payload into per-100 g numbers whose units and basis are known,
or refusing.

**RULE-09 is a shape here, not a discipline.** Every public function in this module takes a
barcode, a name, a brand token or a source payload. Not one takes a kcal, a gram or a macro,
so there is no parameter through which a model-produced number could enter a `foods_cache`
row. A test asserts the absence rather than trusting the caller.

**REQ-NUT-025 forbids a fuzzy match, so there is no scorer.** Open Food Facts text search
returns whatever it likes for "protein bar"; `select_exact_match` accepts a candidate only on
normalised string equality of the product name, and — when the caller supplies one — of the
brand. Several distinct products matching exactly is *ambiguity*, which is an unresolved item
(REQ-NUT-024), not a tie to be broken. A best-effort-similar match is the failure REQ-NUT-016
names by hand: a generic food's nutrients standing in for a named branded one.

**Four outcomes, never collapsed into one.** Crowd-sourced data fails in distinguishable ways
and a caller that cannot tell them apart will do the wrong thing with three of them:

    OffNotFound     the product does not exist, or nothing matched exactly.
                    -> `unresolved_items`, and do not ask again tonight.
    OffAmbiguous    several distinct products matched exactly.
                    -> `unresolved_items`, and Joe picks. Never a coin toss.
    OffMalformed    the product exists and its nutrition is unusable — no nutriments, a
                    per-serving basis with no serving size, physically impossible values.
                    -> `unresolved_items`, and the reason is worth reading.
    OffTransient    the request did not complete (Open Food Facts returns 503 often enough
                    that this is a normal weekday). -> defer. This is NOT "no such food",
                    and marking it unresolved would turn an outage into a permanent gap.

**Units, stated because getting them wrong is silent.** Open Food Facts normalises its
`*_100g` fields: macronutrients in grams, `energy-kcal_100g` in kcal, and `sodium_100g` in
GRAMS — while `core.metric_registry` stores `sodium_mg` in milligrams. The x1000 is written
once, here, next to the sentence explaining it. Energy falls back to `energy-kj_100g` over the
defined 4.184 kJ/kcal, and sodium falls back to `salt_100g / 2.5`, the factor EU regulation
1169/2011 defines; both are recorded in `notes` so a derived figure is never mistaken for a
declared one (INV-5).

**Per-serving is not per-100 g.** `nutrition_data_per` may be `serving`, in which case the
`*_serving` fields are the declared ones. They are converted with the product's own serving
mass and NEVER stored as though they were per-100 g. Where the basis is `serving` and no
serving mass is known, the record is malformed — the alternative is a number that is wrong by
whatever the serving happens to weigh, which is the most convincing kind of wrong.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import unicodedata
from collections import deque

from lib import egress

CODE_VERSION = "nutrition-off-v1"

# The `foods_cache.source` and `config.nutrition_interval_widths.method` value for everything
# this module produces. Defined in migration 0050; restated here as a reference, never as a
# second definition — the width that goes with it is read from the table by nutrition.py.
SOURCE = "off_product"

HOST = "world.openfoodfacts.org"                 # must be in config.egress_allowlist (RULE-29)
PRODUCT_URL = f"https://{HOST}/api/v2/product/{{code}}.json"
# Full-text search is not available in the v2 server-side API; the legacy CGI endpoint is the
# documented text-search path and is rate-limited as one (REQ-NUT-011).
SEARCH_URL = f"https://{HOST}/cgi/search.pl"

# REQ-NUT-011, and the same numbers Open Food Facts publishes: 15 product reads/min/IP and
# 10 searches/min/IP.
PRODUCT_READS_PER_MINUTE = 15
SEARCHES_PER_MINUTE = 10

# REQ-NUT-008. Foundation and SR Legacy never expire; a crowd-edited product does.
CACHE_TTL_DAYS = 365

KJ_PER_KCAL = 4.184                              # definition, not a measurement
SALT_TO_SODIUM = 2.5                             # EU 1169/2011: salt = sodium x 2.5

APP_VERSION = "1.0"                              # the <version> of REQ-NUT-010's User-Agent
CONTACT_ENV = ("PERSONAL_OS_CONTACT_EMAIL", "OFF_CONTACT_EMAIL")

PRODUCT_FIELDS = (
    "code,product_name,product_name_en,brands,quantity,serving_size,serving_quantity,"
    "serving_quantity_unit,nutrition_data_per,nutrition_data_prepared_per,no_nutrition_data,"
    "nutriments,last_modified_t")

# What this system stores, and where Open Food Facts keeps it. The right-hand side is a tuple
# because a fallback is a different number with a different provenance, not a synonym.
_NUTRIENT_SOURCES = {
    "kcal":      ("energy-kcal",),
    "protein_g": ("proteins",),
    "carbs_g":   ("carbohydrates",),
    "fat_g":     ("fat",),
    "fiber_g":   ("fiber", "fibre"),
    "sugar_g":   ("sugars",),
    "sodium_mg": ("sodium",),
}

# Physical ceilings per 100 g, not quality preferences. 100 g of anything cannot contain more
# than 100 g of one macronutrient, and 100 g of pure fat is about 900 kcal. A value past these
# is a transcription error in a crowd-sourced record; it is DROPPED with its reason, never
# clamped to the ceiling, because a clamped value is a fabricated one (RULE-01).
_CEILING_PER_100G = {
    "kcal": 950.0,          # pure fat is ~900; ethanol-heavy products sit below this
    "protein_g": 100.0, "carbs_g": 100.0, "fat_g": 100.0,
    "fiber_g": 100.0, "sugar_g": 100.0,
    "sodium_mg": 40000.0,   # 100 g of table salt is ~39.3 g sodium
}
_MACRO_SUM_CEILING = 105.0   # protein + carbs + fat + fibre, with rounding headroom

# These two are physical facts about 100 g of matter, not Open Food Facts quirks, so
# `nutrition_usda` screens on the same numbers rather than a second copy that could drift apart
# from this one. Public aliases rather than a move, so nothing below this line has to change.
CEILING_PER_100G = _CEILING_PER_100G
MACRO_SUM_CEILING = _MACRO_SUM_CEILING

_MASS_UNITS_TO_G = {"g": 1.0, "gram": 1.0, "grams": 1.0, "mg": 0.001, "kg": 1000.0,
                    "oz": 28.349523125, "lb": 453.59237}
_VOLUME_UNITS_TO_ML = {"ml": 1.0, "cl": 10.0, "dl": 100.0, "l": 1000.0, "litre": 1000.0}

_SERVING_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*([a-zA-Z]+)")
_PARENTHESISED = re.compile(r"\(([^)]*)\)")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCHEMA_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


# ---------------------------------------------------------------- outcomes

class OffUnusable(Exception):
    """Base: Open Food Facts produced no usable record. Carries the `tried` entry verbatim."""

    def __init__(self, reason, detail=None):
        self.reason, self.detail = reason, detail
        super().__init__(f"{type(self).__name__}: {reason}")

    def tried_entry(self):
        """The shape `nutrition.Unresolved.tried` collects and `unresolved_items.tried` stores."""
        entry = {"source": SOURCE, "hit": False, "reason": self.reason}
        if self.detail is not None:
            entry["detail"] = self.detail
        return entry


class OffNotFound(OffUnusable):
    """No such product, or nothing matched exactly. A gap, and a settled one."""


class OffAmbiguous(OffUnusable):
    """Several distinct products matched exactly. Joe picks; the system does not (REQ-NUT-025)."""


class OffMalformed(OffUnusable):
    """The product exists and its nutrition cannot be read without inventing something."""


class OffTransient(OffUnusable):
    """The request did not complete. Defer it; this is not a statement about the food."""


class OffRateLimited(OffTransient):
    """REQ-NUT-011's ceiling reached. Carries `retry_after` seconds."""

    def __init__(self, kind, retry_after):
        self.retry_after = retry_after
        super().__init__(f"rate_limited_{kind}", {"retry_after_s": round(retry_after, 3)})


class ContactMissing(Exception):
    """REQ-NUT-010 cannot be satisfied, so no request is issued.

    Not an `OffUnusable`: this is a misconfiguration of *this* system, not an outcome of a
    lookup, and it must not be written into `unresolved_items` as though the food were the
    problem. The contact address lives in the environment because a public Git repository is
    a third party (RULE-29) and an address in a source file is personal data committed to it.
    """


# ---------------------------------------------------------------- etiquette (REQ-NUT-010/011)

def user_agent(env=None):
    """`PersonalOS/<version> (<contact email>)`, exactly as REQ-NUT-010 writes it."""
    env = os.environ if env is None else env
    email = next((env[k].strip() for k in CONTACT_ENV if env.get(k, "").strip()), None)
    if email is None:
        raise ContactMissing(
            "REQ-NUT-010 requires a contact address in the User-Agent of every Open Food "
            f"Facts request; set one of {' / '.join(CONTACT_ENV)}")
    if not _EMAIL_RE.match(email):
        raise ContactMissing(f"contact address is not an email address: {email[:3]}...")
    return f"PersonalOS/{APP_VERSION} ({email})"


class RateLimiter:
    """A sliding window that REFUSES rather than sleeps.

    REQ-NUT-011 is a ceiling per minute, and the two ceilings are different (10 searches, 15
    product reads), so they are two windows and not one shared counter. Refusing rather than
    blocking is the point: the caller is a nightly batch that has other items to resolve and a
    deferral is cheaper than a held thread — and a test can prove the boundary at the exact
    second without waiting for it, because the clock is a parameter.
    """

    def __init__(self, max_calls, window_seconds=60.0, kind="off"):
        self.max_calls, self.window, self.kind = int(max_calls), float(window_seconds), kind
        self._stamps = deque()

    def acquire(self, now=None):
        """Record one call at `now` (monotonic seconds), or raise `OffRateLimited`."""
        now = time.monotonic() if now is None else float(now)
        while self._stamps and now - self._stamps[0] >= self.window:
            self._stamps.popleft()
        if len(self._stamps) >= self.max_calls:
            raise OffRateLimited(self.kind, self.window - (now - self._stamps[0]))
        self._stamps.append(now)

    def __len__(self):
        return len(self._stamps)


class Limits:
    """The two REQ-NUT-011 windows, held together for one job run.

    Passing this is REQUIRED by `fetch_product` and `search_products` rather than optional.
    A default of "no limiter" makes the requirement something a caller opts into, and the
    caller that forgets is exactly the nightly batch resolving forty items in nine seconds —
    the case the ceiling exists for. Job-scoped rather than module-level, because module state
    would make two runs share a ceiling they do not share and would make test order matter.
    """

    def __init__(self):
        self.product = RateLimiter(PRODUCT_READS_PER_MINUTE, kind="product")
        self.search = RateLimiter(SEARCHES_PER_MINUTE, kind="search")


# ---------------------------------------------------------------- barcodes

def normalise_barcode(raw):
    """A GTIN-8/12/13/14 with a valid mod-10 check digit, or `OffNotFound`.

    Checked before the request rather than after it, because a mistyped barcode spends one of
    the fifteen reads REQ-NUT-011 allows in that minute to be told what arithmetic already
    knew. A 12-digit UPC-A is zero-padded to 13, which is how Open Food Facts keys it.
    """
    digits = re.sub(r"[\s\-]", "", str(raw or ""))
    if not digits.isdigit() or len(digits) not in (8, 12, 13, 14):
        raise OffNotFound("malformed_barcode", {"length": len(digits)})
    body, check = digits[:-1], int(digits[-1])
    # Mod 10: weights alternate 3 and 1 from the RIGHTMOST body digit, for every GTIN length.
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    if (10 - total % 10) % 10 != check:
        raise OffNotFound("barcode_check_digit_failed")
    return digits.zfill(13) if len(digits) == 12 else digits


# ---------------------------------------------------------------- names

def normalise_name(text):
    """Case, accents, punctuation and spacing folded. Nothing else.

    This is the whole of the matching logic, and it is deliberately not a similarity measure:
    REQ-NUT-025 forbids a fuzzy, partial or best-effort-similar match, so the only question
    this module may ask about two names is whether they are the same name.
    """
    folded = unicodedata.normalize("NFKD", str(text or ""))
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = re.sub(r"[^0-9a-zA-Z]+", " ", folded.lower())
    return " ".join(folded.split())


def _product_names(product):
    return [product.get("product_name"), product.get("product_name_en")]


def _brand_tokens(product):
    return [b.strip() for b in str(product.get("brands") or "").split(",") if b.strip()]


def select_exact_match(query, products, *, brand=None):
    """The one product whose name — and brand, when given — equals the query. Or nothing.

    Returns a single product dict. Raises `OffNotFound` when nothing matches exactly and
    `OffAmbiguous` when several distinct products do. "Several products called 'protein bar'"
    is not a tie-break problem; it is the case REQ-NUT-024 exists for, and picking the most
    popular one would be a guess wearing a lookup's clothes.
    """
    want, want_brand = normalise_name(query), normalise_name(brand) if brand else None
    hits = []
    for product in products or []:
        if not any(normalise_name(n) == want for n in _product_names(product) if n):
            continue
        if want_brand is not None and not any(
                normalise_name(b) == want_brand for b in _brand_tokens(product)):
            continue
        hits.append(product)
    if not hits:
        raise OffNotFound("no_exact_name_match", {"candidates": len(products or [])})
    # Deterministic across identical inputs regardless of the order the API returned them.
    hits.sort(key=lambda p: str(p.get("code") or ""))
    distinct = {str(p.get("code") or "") for p in hits}
    if len(distinct) > 1:
        raise OffAmbiguous("ambiguous_exact_match", {"codes": sorted(distinct)[:5],
                                                     "n": len(distinct)})
    return hits[0]


# ---------------------------------------------------------------- parsing

def _number(value):
    """A float, or None. A blank string and a non-numeric string are None, not zero."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def serving_mass(product):
    """(grams, millilitres, note). Either may be None; both may be.

    `serving_g` in `core.foods_cache` is grams. A serving declared in millilitres is NOT
    converted: that conversion is a density, the system has measured no densities, and
    assuming 1 g/ml would put an invented number in a column whose whole purpose is to be a
    measured one. The millilitres are returned separately so a caller can see them and a
    later ruling can use them.
    """
    quantity = _number(product.get("serving_quantity"))
    unit = str(product.get("serving_quantity_unit") or "").strip().lower()
    if quantity is not None and unit in _MASS_UNITS_TO_G:
        return quantity * _MASS_UNITS_TO_G[unit], None, None
    if quantity is not None and unit in _VOLUME_UNITS_TO_ML:
        return None, quantity * _VOLUME_UNITS_TO_ML[unit], "serving_declared_in_volume"

    # `serving_size` is free text. A label writes the household measure first and the metric
    # weight in parentheses — "1 oz (28 g)" — and the parenthesised figure is the declared one.
    # Reading left to right would take "1 oz" and silently substitute 28.35 g for the 28 g on
    # the label: 1.2% on every nutrient in the row, in the same direction every time.
    text = str(product.get("serving_size") or "")
    for candidate in (_PARENTHESISED.findall(text) + [text]):
        match = _SERVING_RE.search(candidate)
        if not match:
            continue
        amount, parsed_unit = _number(match.group(1)), match.group(2).lower()
        if amount is not None and parsed_unit in _MASS_UNITS_TO_G:
            return amount * _MASS_UNITS_TO_G[parsed_unit], None, "serving_parsed_from_text"
        if amount is not None and parsed_unit in _VOLUME_UNITS_TO_ML:
            return None, amount * _VOLUME_UNITS_TO_ML[parsed_unit], "serving_declared_in_volume"

    # `serving_quantity` with no unit at all: Open Food Facts writes grams there by
    # convention, but a convention is not a declaration, and a household measure ("1 bar")
    # parses to no unit either. Unknown, and said so.
    if quantity is not None and not unit:
        return None, None, "serving_quantity_without_unit"
    return None, None, None


def _read_basis(nutriments, key, suffix):
    """One nutrient off one basis. Returns (value, off_key) or (None, None)."""
    for off_key in _NUTRIENT_SOURCES[key]:
        value = _number(nutriments.get(f"{off_key}_{suffix}"))
        if value is not None:
            return value, off_key
    return None, None


def parse_product(product):
    """A source payload -> per-100 g nutrients in this system's units, or `OffMalformed`.

    Takes the payload and nothing else. There is no argument here through which a caller —
    or a model behind one — could supply a nutrient value (RULE-09, REQ-NUT-060/061).
    """
    if not isinstance(product, dict) or not product:
        raise OffMalformed("empty_product")
    if str(product.get("no_nutrition_data") or "").strip().lower() in ("on", "1", "true"):
        # The contributor stated there is no nutrition data. Believing them is the whole point.
        raise OffMalformed("no_nutrition_data_flag")

    name = next((str(n).strip() for n in _product_names(product) if str(n or "").strip()), None)
    if not name:
        raise OffMalformed("no_product_name")      # nothing to key `foods_cache` on

    nutriments = product.get("nutriments")
    if not isinstance(nutriments, dict) or not nutriments:
        raise OffMalformed("no_nutriments")

    grams, millilitres, serving_note = serving_mass(product)
    notes = [serving_note] if serving_note else []

    declared_basis = str(product.get("nutrition_data_per") or "").strip().lower()
    basis, scale = "100g", 1.0
    if declared_basis in ("serving", "serving_size"):
        # Open Food Facts usually computes the *_100g fields itself. When it has not, the
        # declared numbers are per serving and the only honest conversion needs the serving's
        # mass. Without one there is no conversion, only a guess about what a serving weighs.
        if any(_read_basis(nutriments, k, "100g")[0] is not None for k in _NUTRIENT_SOURCES):
            notes.append("declared_per_serving_read_per_100g")
        elif grams and grams > 0:
            basis, scale = "serving", 100.0 / float(grams)
            notes.append("converted_from_serving_using_declared_serving_mass")
        else:
            raise OffMalformed("serving_basis_without_serving_mass",
                               {"serving_size": product.get("serving_size")})

    suffix = "serving" if basis == "serving" else "100g"
    nutrients, provenance, dropped = {}, {}, {}

    for key in _NUTRIENT_SOURCES:
        value, off_key = _read_basis(nutriments, key, suffix)

        if key == "kcal" and value is None:
            kj, kj_key = None, None
            for candidate in ("energy-kj", "energy"):
                kj = _number(nutriments.get(f"{candidate}_{suffix}"))
                if kj is not None:
                    kj_key = candidate
                    break
            # `energy_*` is only kilojoules when the record says so; unit-less energy is not
            # assumed to be anything.
            if kj is not None and (kj_key == "energy-kj" or str(
                    nutriments.get("energy_unit") or "").strip().lower() == "kj"):
                value, off_key = kj / KJ_PER_KCAL, kj_key
                notes.append("kcal_derived_from_kj")

        if key == "sodium_mg":
            if value is not None:
                value, off_key = value * 1000.0, "sodium"    # OFF reports sodium in GRAMS
            else:
                salt = _number(nutriments.get(f"salt_{suffix}"))
                if salt is not None:
                    value, off_key = salt * 1000.0 / SALT_TO_SODIUM, "salt"
                    notes.append("sodium_derived_from_salt")

        if value is None:
            continue                                # absent stays absent (RULE-06)
        value *= scale
        if value < 0 or value > _CEILING_PER_100G[key]:
            # Dropped, never clamped: a value at the ceiling would be a number this system
            # made up, and it would look exactly like a declared one.
            dropped[key] = {"off_key": off_key, "value": round(value, 4),
                            "ceiling": _CEILING_PER_100G[key]}
            continue
        nutrients[key] = round(value, 4)
        provenance[key] = off_key

    if not nutrients:
        raise OffMalformed("no_usable_nutrient", {"dropped": dropped or None})

    macro_sum = sum(nutrients.get(k, 0.0) for k in ("protein_g", "carbs_g", "fat_g", "fiber_g"))
    if macro_sum > _MACRO_SUM_CEILING:
        raise OffMalformed("macro_sum_exceeds_100g", {"sum_g": round(macro_sum, 2)})

    parsed = {
        "canonical_name": name,
        "brand": (_brand_tokens(product) or [None])[0],
        "source_id": str(product.get("code") or "").strip() or None,
        "nutrients_per_100g": nutrients,
        "serving_g": None if grams is None else round(float(grams), 4),
        "serving_ml": None if millilitres is None else round(float(millilitres), 4),
        "basis": basis,
        "nutrient_provenance": provenance,
        "dropped": dropped,
        "notes": sorted(set(notes)),
    }
    parsed["energy_consistency"] = _energy_consistency(nutrients)
    return parsed


def _energy_consistency(nutrients):
    """Advisory only: declared kcal against Atwater 4/4/9. NEVER a stored nutrient.

    Crowd-sourced energy and crowd-sourced macros disagree often enough to be worth seeing,
    but the Atwater figure is a computed estimate and the label is a declaration, so this
    reports a ratio and changes nothing. Whether a ratio should reject a record is a threshold
    ruling, and RULE-00 puts thresholds in a table and an ADR, not in a parser.
    """
    kcal = nutrients.get("kcal")
    if kcal is None or kcal <= 0:
        return None
    if not any(k in nutrients for k in ("protein_g", "carbs_g", "fat_g")):
        return None
    atwater = (4.0 * nutrients.get("protein_g", 0.0) + 4.0 * nutrients.get("carbs_g", 0.0)
               + 9.0 * nutrients.get("fat_g", 0.0))
    return {"declared_kcal": kcal, "atwater_kcal": round(atwater, 2),
            "ratio": round(atwater / kcal, 4)}


# ---------------------------------------------------------------- the cache row (REQ-NUT-003)

def cache_row(product, parsed=None, *, fetched_at=None):
    """The `core.foods_cache` row this source produces. Columns exactly as migration 0050
    defines them; `raw` keeps the payload so a changed reading can be re-derived without
    spending another request (ADR-0066 decision 2)."""
    parsed = parse_product(product) if parsed is None else parsed
    return {
        "canonical_name": parsed["canonical_name"],
        "source": SOURCE,
        "source_id": parsed["source_id"],
        "brand": parsed["brand"],
        "nutrients_per_100g": parsed["nutrients_per_100g"],
        "serving_g": parsed["serving_g"],
        "fetched_at": fetched_at or dt.datetime.now(dt.timezone.utc),
        "raw": {"off_product": product, "parse": {
            "code_version": CODE_VERSION, "basis": parsed["basis"],
            "nutrient_provenance": parsed["nutrient_provenance"],
            "serving_ml": parsed["serving_ml"], "dropped": parsed["dropped"],
            "energy_consistency": parsed["energy_consistency"], "notes": parsed["notes"]}},
    }


def insert_cache_row(cur, row, schema="core"):
    """Append the row if it is new. Returns the `food_id`, or None when it was already there.

    `ON CONFLICT DO NOTHING` on 0050's `(canonical_name, source, source_id)` key: a second
    lookup of the same product must not rewrite the first one's `raw`, because that is the
    payload an earlier reading was derived from (INV-1).
    """
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"not a plain schema identifier: {schema!r}")
    cur.execute(
        f"""insert into {schema}.foods_cache
              (canonical_name, source, source_id, brand, nutrients_per_100g, serving_g,
               fetched_at, raw)
            values (%s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
            on conflict (canonical_name, source, source_id) do nothing
            returning food_id""",
        (row["canonical_name"], row["source"], row["source_id"], row["brand"],
         json.dumps(row["nutrients_per_100g"]), row["serving_g"], row["fetched_at"],
         json.dumps(row["raw"], default=str)))
    found = cur.fetchone()
    return found[0] if found else None


def needs_refetch(fetched_at, now=None):
    """REQ-NUT-008: an Open Food Facts row older than 365 days is re-fetched.

    Foundation and SR Legacy do not expire; a crowd-edited product does, because the record
    can change under a name that did not.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    if fetched_at is None:
        return True
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=dt.timezone.utc)
    return (now - fetched_at) > dt.timedelta(days=CACHE_TTL_DAYS)


# ---------------------------------------------------------------- the two network paths

def _get(cur, url, purpose, params, *, limiter, now, env, timeout, schema, ops, config,
         _transport):
    """Every request this module makes goes through `lib.egress.get_json` and none other.

    The order of the three lines below is deliberate. The User-Agent is built FIRST, so a
    missing contact address costs nothing; the REQ-NUT-011 window is taken SECOND, so a slot
    is spent only when a request is actually about to be issued; the request goes LAST. Taking
    the slot first would let a misconfiguration burn a minute's ceiling on requests that never
    left the process.

    `PayloadRefused` is re-raised untouched. It is either the allowlist refusing a host or the
    RULE-29 screen refusing a payload, and both must reach the operator as themselves — a
    RULE-29 refusal recorded as "Open Food Facts was flaky" is a privacy failure filed as a
    network one.
    """
    headers = {"User-Agent": user_agent(env), "Accept": "application/json"}
    limiter.acquire(now)
    try:
        return egress.get_json(cur, url, purpose, params=params, headers=headers,
                               timeout=timeout, schema=schema, ops=ops, config=config,
                               _transport=_transport)
    except egress.PayloadRefused:
        raise
    except OffUnusable:
        raise
    except Exception as e:
        raise OffTransient("request_failed", {"error": type(e).__name__}) from e


def fetch_product(cur, barcode, *, limits, now=None, env=None, timeout=20,
                  schema="core", ops="ops", config="config", _transport=None):
    """REQ-NUT-001 step 2 — barcode lookup. Returns the raw product payload.

    Raises `OffNotFound` when Open Food Facts has no such product. A 404-shaped answer is a
    fact about the product; a failed request is not, and they leave by different doors.
    """
    code = normalise_barcode(barcode)
    body = _get(cur, PRODUCT_URL.format(code=code), "nutrition:off_product_read",
                {"fields": PRODUCT_FIELDS}, limiter=limits.product, now=now, env=env,
                timeout=timeout, schema=schema, ops=ops, config=config, _transport=_transport)
    if not isinstance(body, dict):
        raise OffMalformed("response_not_an_object")
    if body.get("status") != 1 or not isinstance(body.get("product"), dict):
        raise OffNotFound("barcode_not_in_off",
                          {"status_verbose": body.get("status_verbose")})
    return body["product"]


def search_products(cur, query, *, limits, page_size=20, now=None, env=None, timeout=20,
                    schema="core", ops="ops", config="config", _transport=None):
    """REQ-NUT-001 step 5 — text search. Returns the candidate list, unfiltered.

    The filtering is `select_exact_match`, kept separate so the matching rule can be tested
    exhaustively against fixed candidate lists without a transport at all.
    """
    text = str(query or "").strip()
    if not text:
        raise OffNotFound("empty_query")
    body = _get(cur, SEARCH_URL, "nutrition:off_search",
                {"search_terms": text, "json": 1, "page_size": int(page_size),
                 "fields": PRODUCT_FIELDS},
                limiter=limits.search, now=now, env=env, timeout=timeout, schema=schema,
                ops=ops, config=config, _transport=_transport)
    if not isinstance(body, dict) or not isinstance(body.get("products"), list):
        raise OffMalformed("search_response_without_products")
    return body["products"]


def lookup_by_barcode(cur, barcode, **kw):
    """Barcode -> a `foods_cache` row ready to insert. The caller owns the cascade order."""
    fetched_at = kw.pop("fetched_at", None)
    return cache_row(fetch_product(cur, barcode, **kw), fetched_at=fetched_at)


def lookup_by_name(cur, query, *, brand=None, **kw):
    """Name (+ optional brand token) -> a `foods_cache` row ready to insert, or a refusal."""
    fetched_at = kw.pop("fetched_at", None)
    products = search_products(cur, query, **kw)
    return cache_row(select_exact_match(query, products, brand=brand), fetched_at=fetched_at)
