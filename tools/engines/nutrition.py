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
"""
import json

CODE_VERSION = "nutrition-v1"

# The order sources are consulted. Joe's own corrections outrank everything, permanently
# (RULE-10, §D.4) — once he has said what a portion is, nothing re-guesses it.
SOURCE_PRECEDENCE = ("joe", "usda_branded", "usda_foundation", "off_product")

NUTRIENT_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "sodium_mg")


class Unresolved(Exception):
    """Nothing could resolve this item. The caller writes an `unresolved_items` row."""

    def __init__(self, item_text, tried):
        self.item_text, self.tried = item_text, tried
        super().__init__(f"unresolved: {item_text!r}")


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

def lookup_cached(cur, name, schema="core"):
    """The cache, in precedence order. Returns (row, method) or (None, None)."""
    cur.execute(
        f"""select canonical_name, source, nutrients_per_100g, serving_g, brand
              from {schema}.foods_cache
             where lower(canonical_name) = lower(%s)
             order by array_position(%s::text[], source)
             limit 1""",
        (name, list(SOURCE_PRECEDENCE)))
    row = cur.fetchone()
    if row is None:
        return None, None
    canonical, source, nutrients, serving_g, brand = row
    nutrients = nutrients if isinstance(nutrients, dict) else json.loads(nutrients)
    return {"canonical_name": canonical, "source": source, "nutrients_per_100g": nutrients,
            "serving_g": None if serving_g is None else float(serving_g), "brand": brand}, source


def portion_grams(cur, name, schema="core"):
    """Joe's own portion first, then any other. RULE-10: his correction outranks the source."""
    cur.execute(
        f"""select grams, source from {schema}.portions
             where lower(canonical_name) = lower(%s)
             order by case when source = 'joe' then 0 else 1 end, recorded_at desc
             limit 1""", (name,))
    row = cur.fetchone()
    return (float(row[0]), row[1]) if row else (None, None)


def resolve_item(cur, item_text, *, grams=None, servings=None, schema="core", config="config"):
    """One food item -> {metric_key: (low, point, high)} plus the method that produced it.

    Raises `Unresolved` rather than returning zeros. A zero is a claim that the item had no
    calories; an absence is the truth (RULE-06).
    """
    widths = interval_widths(cur, config)
    tried = []

    cached, source = lookup_cached(cur, item_text, schema)
    tried.append({"source": "foods_cache", "hit": cached is not None})
    if cached is None:
        raise Unresolved(item_text, tried)

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
                raise Unresolved(item_text, tried)
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
        raise Unresolved(item_text, tried)
    return {"method": method, "grams": round(float(grams), 2), "source": source,
            "canonical_name": cached["canonical_name"], "nutrients": out}


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
