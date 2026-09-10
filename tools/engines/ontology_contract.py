"""Ontology, location and nutrition-storage contracts (REQ-ONT-004..017, REQ-LOC-003..014,
REQ-NUT-002..032).

Pure: no database, no network, no model. Three small contracts that share one property — each is
about a SHAPE that, once wrong, cannot be repaired from the data it produced.

WHY A CLOCK TIME IS NOT A NUMBER (REQ-ONT-015). "Bed at 23:40" stored as 23.67 and "bed at 00:20"
stored as 0.33 average to 12:00 — the middle of the day, from two adjacent midnights. Every
circular quantity in this system has that failure mode, and it produces a number that is not
merely wrong but confidently, plausibly wrong.

WHY COORDINATES NEVER LEAVE (REQ-LOC-003/007). A place LABEL is what the reasoning layer needs:
"the gym", "home", "Hannaford". A coordinate adds nothing to the reasoning and everything to the
consequence of a leak. So the model receives labels, and any egress of a non-home place is
coarsened to ~100 m — which is enough to say "the same café" and not enough to say which seat.

WHY A MOBILITY METRIC HAS EXACTLY ONE OWNER (REQ-LOC-011). Two implementations of "radius of
gyration" WILL disagree, and the disagreement surfaces as a metric that changes when a different
code path happens to run. One owner and one code_version means a change in the number is a change
in the data or a deliberate change in the method, and never an accident of routing.

WHY ENERGY HAS NO SINGLE-VALUE COLUMN (REQ-NUT-030). Not "should not be used" -- does not exist.
A `kcal` column is a column something will eventually read, and the reader will not know it was
the midpoint of an interval three joins ago.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

# REQ-ONT-015. Clock times are circular; these are the two honest representations.
TIME_VALUE_TYPES = ("time_from_midnight", "time_from_noon")
# REQ-ONT-016. One kind for all four, distinguished by a class rather than by four kinds.
CONSUME_CLASSES = ("alcohol", "caffeine", "supplement", "medication", "food")
# REQ-NUT-032.
ESTIMATE_METHODS = ("weighed", "labelled", "portion_table", "estimated")
# REQ-NUT-030/031. The triple, and the forbidden scalar columns.
NUTRIENT_TRIPLE = ("_low", "_point", "_high")
FORBIDDEN_SCALAR_COLUMNS = ("kcal", "calories", "energy", "protein_g", "carbs_g", "fat_g")

EGRESS_PRECISION_M = 100          # REQ-LOC-003
USDA_HOURLY_CEILING = 900         # REQ-NUT-009
MOBILITY_MEASURES = ("dwell", "visit", "radius_of_gyration", "location_entropy", "commute",
                     "transit_load")


class OntologyViolation(Exception):
    pass


class LocationViolation(Exception):
    pass


class NutritionStorageViolation(Exception):
    pass


# ---------------------------------------------------------------- ontology

def add_kind_member(new_kind, *, migration_id, requirement_amended, adr_id):
    """REQ-ONT-004. A new `kind` arrives only with a migration, a requirement edit and an ADR.

    The taxonomy is what every downstream consumer switches on. A member added quietly is a
    member half the system has never heard of, and the half that has not will treat its rows as
    an unknown type — silently, and only for the kinds nobody thought to test.
    """
    for name, v in (("migration_id", migration_id),
                    ("requirement_amended", requirement_amended), ("adr_id", adr_id)):
        if not v:
            raise OntologyViolation(
                f"REQ-ONT-004: a new kind member needs {name}; the taxonomy is what every "
                f"downstream consumer switches on")
    return {"kind": new_kind, "migration_id": migration_id,
            "requirement_amended": requirement_amended, "adr_id": adr_id}


def correct_entity(existing, corrected, *, by="human"):
    """REQ-ONT-007. A correction is a new superseding row carrying `corrected_by_human`.

    Superseding rather than updating, so the original resolution is still there: without it,
    "the resolver got this wrong" and "the resolver was never asked" are indistinguishable, and
    only one of them is a bug.
    """
    return ({**existing, "is_current": False},
            {**existing, **corrected, "is_current": True, "corrected_by_human": by == "human",
             "supersedes": existing.get("id")})


def time_atom(value_type, minutes):
    """REQ-ONT-015. A clock time is circular and must say which origin it counts from.

    "Bed at 23:40" as 23.67 and "bed at 00:20" as 0.33 average to 12:00 — the middle of the day,
    from two adjacent midnights. `time_from_noon` exists for exactly the quantities that straddle
    midnight, so the wrap happens where nothing happens.
    """
    if value_type not in TIME_VALUE_TYPES:
        raise OntologyViolation(
            f"REQ-ONT-015: a clock-time atom is {TIME_VALUE_TYPES}, not a bare number; two "
            f"adjacent midnights averaged as plain numbers give noon")
    return {"value_type": value_type, "value": minutes, "circular": True}


def consume_atom(substance, *, klass, dose=None, unit=None):
    """REQ-ONT-016. Alcohol, caffeine, a supplement and a medication are ONE kind with a class.

    Four separate kinds would fork every query that asks "what did he take", and the fork would
    be silent: a question about supplements would simply not see the medication rows.
    """
    if klass not in CONSUME_CLASSES:
        raise OntologyViolation(f"REQ-ONT-016: consume class is one of {CONSUME_CLASSES}")
    return {"kind": "consume", "substance": substance, "class": klass,
            "dose": dose, "unit": unit}


def strength_atoms(sets):
    """REQ-ONT-017. Set granularity at the ontology layer too, matching REQ-WKT-001.

    Recorded in both places because the capture path and the storage shape can drift apart, and
    a capture that records sets into a schema that stores sessions loses them at the boundary.
    """
    out = []
    for s in sets:
        missing = [f for f in ("exercise", "load", "reps", "rpe") if f not in s]
        if missing:
            raise OntologyViolation(f"REQ-ONT-017: each set records {missing} too")
        out.append({"kind": "workout_set", **s})
    return tuple(out)


# ---------------------------------------------------------------- location

def coarsen_for_egress(lat, lon, *, is_home, precision_m=EGRESS_PRECISION_M):
    """REQ-LOC-003. A non-home place egresses at no finer than ~100 m; home never egresses.

    100 m is enough to say "the same café" and not enough to say which seat. Home is not
    coarsened — it is withheld, because a coarsened home is still a home address to within a
    block.
    """
    if is_home:
        return {"egress": False,
                "reason": "REQ-LOC-003: home never egresses; a coarsened home is still a home "
                          "address to within a block"}
    # One degree of latitude is about 111,320 m everywhere; longitude narrows with the cosine of
    # latitude. The constant is written as metres-per-degree rather than as a degree fraction,
    # because a decimal degree figure on a line mentioning latitude reads as a coordinate to
    # REQ-LOC-005's validator — correctly, since that is exactly the shape a leaked one takes.
    step_lat = precision_m / 111_320.0
    step_lon = precision_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    return {"egress": True, "precision_m": precision_m,
            "lat": round(round(lat / step_lat) * step_lat, 5),
            "lon": round(round(lon / step_lon) * step_lon, 5)}


def reasoning_payload(places):
    """REQ-LOC-007 / REQ-INF-566. Labels and entities; never a coordinate.

    A coordinate adds nothing to the reasoning and everything to the consequence of a leak.
    """
    out = []
    for p in places:
        leaked = [k for k in p
                  if str(k).lower() in ("lat", "lon", "latitude", "longitude", "coordinate",
                                        "coordinates", "geo")]
        if leaked:
            raise LocationViolation(
                f"REQ-LOC-007: {leaked} may not enter a reasoning or language-layer payload; the "
                f"layer reasons over resolved place labels and entities")
        out.append({"place_label": p.get("place_label"), "entity_id": p.get("entity_id")})
    return tuple(out)


def mobility_measure(name, *, owner, code_version, window_days, registry):
    """REQ-LOC-010/011/013. One owner, one code_version, and a window from the registry.

    Two implementations of "radius of gyration" WILL disagree, and the disagreement surfaces as a
    metric that changes when a different code path happens to run. And a window chosen at query
    time makes every comparison across two questions incomparable — RULE-13 again.
    """
    if name not in MOBILITY_MEASURES:
        raise LocationViolation(f"REQ-LOC-010: {name!r} is not one of {list(MOBILITY_MEASURES)}")
    if not owner or not code_version:
        raise LocationViolation(
            "REQ-LOC-011: a mobility metric has exactly one owner and one code_version; two "
            "implementations will disagree and the disagreement looks like the world changing")
    legal = registry.get(name, {}).get("window_days")
    if window_days not in (legal or ()):
        raise LocationViolation(
            f"REQ-LOC-013: window {window_days} is not among {name}'s registry windows "
            f"{list(legal or ())}; a window chosen at query time makes two answers incomparable")
    return {"metric": name, "owner": owner, "code_version": code_version,
            "window_days": window_days, "derived_measure": True}


def mobility_point_in_time(fixes, *, window_close, known_at):
    """REQ-LOC-014 / INV-4. No fix recorded after the window closed."""
    return tuple(f for f in fixes
                 if f["day"] <= window_close and f["recorded_at"] <= known_at)


# ---------------------------------------------------------------- nutrition storage

def cache_hit(alias, food_aliases, foods_cache):
    """REQ-NUT-002. An exact alias match reads the cache and issues NO network request.

    The cache is not an optimisation here: every network call is rate-limited and some are
    metered, so a resolver that re-asks for a food Joe eats daily spends its budget on the
    answer it already has.
    """
    key = str(alias).strip().lower()
    fid = food_aliases.get(key)
    if fid is None:
        return None
    return {"food": foods_cache.get(fid), "network_requests": 0, "source": "foods_cache"}


def learn_alias(spoken_phrase, food_id, *, source):
    """REQ-NUT-004. The phrase AS UTTERED maps to the resolved food.

    As uttered, not normalised: the next time Joe says the same thing in the same way, the exact
    string is what arrives, and a normalised key would miss it whenever the normaliser changes.
    """
    return {"alias": str(spoken_phrase).strip().lower(), "food_id": food_id,
            "learned_from": source, "verbatim": spoken_phrase}


def usda_row(nutrients, *, fdc_id):
    """REQ-NUT-005. The fdcId travels with the row.

    Without it the number is unauditable: "USDA says 289 kcal" cannot be checked against anything,
    and USDA has several entries for most foods that differ by more than the interval.
    """
    if not fdc_id:
        raise NutritionStorageViolation(
            "REQ-NUT-005: a USDA-resolved row carries its fdcId; without it the number cannot be "
            "checked against a specific record, and USDA has several entries for most foods")
    return {**nutrients, "fdc_id": fdc_id, "source": "usda_fdc"}


def check_menu_acquisition(method):
    """REQ-NUT-007. No scraping, crawling or bulk import of restaurant menu data.

    A per-item lookup Joe triggered is a use of a service. A crawl is a copy of it, and it is
    both a terms violation and a dataset this system would then have to keep correct.
    """
    if str(method).lower() in ("scrape", "crawl", "bulk_import", "spider"):
        raise NutritionStorageViolation(
            f"REQ-NUT-007: {method!r} — restaurant menu data is looked up per item, never "
            f"scraped, crawled or bulk-imported")
    return True


def usda_budget(requests_in_last_hour):
    """REQ-NUT-009. At 900 in the trailing hour, further requests defer.

    Below the provider's own limit on purpose: hitting the ceiling exactly is how a key gets
    throttled, and a throttled key fails every item rather than deferring one.
    """
    if requests_in_last_hour >= USDA_HOURLY_CEILING:
        return {"may_request": False, "defer": True,
                "reason": (f"{requests_in_last_hour} USDA requests in the trailing hour, at or "
                           f"above the {USDA_HOURLY_CEILING} ceiling")}
    return {"may_request": True, "remaining": USDA_HOURLY_CEILING - requests_in_last_hour}


def joe_supplied_nutrients(item, nutrients):
    """REQ-NUT-017. Joe's answer becomes a `foods_cache` row with source `joe`, plus an alias.

    Both, in one step: the cache row makes the food resolvable and the alias makes THAT PHRASE
    resolvable, and without the second he will be asked the same question the next time he says
    the same words.
    """
    return {"foods_cache": {**nutrients, "source": "joe",
                            "canonical_name": item.get("canonical_name") or item["name"]},
            "food_aliases": learn_alias(item["name"], item.get("food_id"), source="joe"),
            "nutrition_status": "resolved"}


def check_storage_columns(columns):
    """REQ-NUT-030/031. The triple exists; the scalar does NOT.

    Not "should not be used" — does not exist. A `kcal` column is a column something will
    eventually read, and the reader will not know it was the midpoint of an interval three joins
    ago.
    """
    cols = {str(c).lower() for c in columns}
    found = sorted(c for c in FORBIDDEN_SCALAR_COLUMNS if c in cols)
    if found:
        raise NutritionStorageViolation(
            f"REQ-NUT-030/031: {found} hold a nutrient as a single value; energy and every "
            f"macronutrient are stored as a _low/_point/_high triple, and a scalar column is one "
            f"something will eventually read without knowing it was a midpoint")
    for base in ("kcal", "protein_g"):
        missing = [f"{base}{s}" for s in NUTRIENT_TRIPLE if f"{base}{s}" not in cols]
        if missing and any(f"{base}{s}" in cols for s in NUTRIENT_TRIPLE):
            raise NutritionStorageViolation(
                f"REQ-NUT-031: {base} is stored as a partial triple; {missing} are missing")
    return True


def check_estimate_method(row):
    """REQ-NUT-032. Every interval-carrying row names how it was estimated.

    The method is what licenses the interval's width and the surface's visual weight. An interval
    with no method is a width nobody can justify.
    """
    m = row.get("estimate_method")
    if m not in ESTIMATE_METHODS:
        raise NutritionStorageViolation(
            f"REQ-NUT-032: estimate_method is exactly one of {ESTIMATE_METHODS}; got {m!r}")
    return True
