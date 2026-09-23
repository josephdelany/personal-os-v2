"""Pint-backed physical quantities; no volume-to-mass or portion assumptions."""

import math
import re
from decimal import Decimal
from functools import lru_cache
from lib.quantity_literals import matches_number, number_phrase

# Fixed token mapping prevents Pint's expression parser from interpreting model
# text as an arithmetic expression or choosing a regional household definition.
MASS_INPUT_UNITS = {
    'g':'gram', 'gram':'gram', 'grams':'gram',
    'mg':'milligram', 'milligram':'milligram', 'milligrams':'milligram',
    'kg':'kilogram', 'kilogram':'kilogram', 'kilograms':'kilogram',
    'oz':'ounce', 'ounce':'ounce', 'ounces':'ounce',
    'lb':'pound', 'lbs':'pound', 'pound':'pound', 'pounds':'pound',
}
VOLUME_INPUT_UNITS = {
    'ml':'milliliter', 'milliliter':'milliliter', 'milliliters':'milliliter',
    'millilitre':'milliliter', 'millilitres':'milliliter',
    'cl':'centiliter', 'dl':'deciliter', 'l':'liter',
    'liter':'liter', 'liters':'liter', 'litre':'liter', 'litres':'liter',
}


def normalize_unit(unit):
    """Fold spelled-out words, never SI prefix symbols (Mg is not mg)."""
    token = unit.strip()
    if token in ('L','mL','cL','dL'):
        return token.lower()
    if len(token) > 3:
        return token.lower()
    return token


@lru_cache(maxsize=1)
def _registry():
    from pint import UnitRegistry
    return UnitRegistry()


def _finite_positive(value):
    if not isinstance(value, (int, float, Decimal)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value > 0
    except (ValueError, OverflowError):
        return False


def literal_pair(value, unit, evidence):
    """Bind an exact decimal amount and approved unit token in one whole span.

    Caller still verifies the span against the original transcript. No unit alias
    may stand in for a different literal token supplied by the model.
    """
    if not (_finite_positive(value) and isinstance(unit, str) and isinstance(evidence, str)):
        return False
    token = normalize_unit(unit)
    if token not in MASS_INPUT_UNITS and token not in VOLUME_INPUT_UNITS:
        return False
    match = re.fullmatch(r'\s*(.+?)\s*([a-z]+)\s*', evidence, re.I)
    return bool(match and normalize_unit(match[2]) == token
                and matches_number(value,number_phrase(match[1])))


def convert_quantity(value, unit):
    """REQ-NUT-019: convert a bounded scalar, retaining its physical dimension."""
    if not _finite_positive(value) or not isinstance(unit, str):
        raise ValueError('invalid quantity')
    token = normalize_unit(unit)
    if token in MASS_INPUT_UNITS:
        canonical, target = MASS_INPUT_UNITS[token], 'g'
    elif token in VOLUME_INPUT_UNITS:
        canonical, target = VOLUME_INPUT_UNITS[token], 'ml'
    else:
        raise ValueError('unsupported quantity unit')
    result = _registry().Quantity(float(value), canonical).to(target).magnitude
    if not math.isfinite(result) or result <= 0:
        raise ValueError('invalid converted quantity')
    return {'value': result, 'unit': target, 'provenance': 'extracted'}
