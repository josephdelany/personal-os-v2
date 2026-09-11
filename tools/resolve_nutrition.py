#!/usr/bin/env python3
"""Resolve one food item through the real source cascade (ADR-0106, ADR-0137).

    PYTHONPATH=. python3 tools/resolve_nutrition.py "hazelnut spread" --servings 1
    PYTHONPATH=. python3 tools/resolve_nutrition.py "chicken burrito" --brand Chipotle
    PYTHONPATH=. python3 tools/resolve_nutrition.py "porridge" --grams 320 --commit

This is the runnable proof that the cascade is on the execution path rather than beside it: it
builds the four legs with `nutrition.build_sources` and calls `nutrition.resolve_item`, which is
the same call the nightly resolver makes. It adds no resolution logic of its own.

**It rolls back unless `--commit` is given.** A resolution WRITES — REQ-NUT-003 inserts a
`foods_cache` row and REQ-NUT-004 its alias — and a production write needs explicit
authorisation, so the default run shows what would be written and then discards it. `--commit`
is the operator saying yes.

Nothing here takes a nutrient value on the command line (RULE-09): the arguments are a name, a
brand token and a quantity, and the numbers come from a source.
"""
import argparse
import json
import sys

from lib import db
from tools.engines import nutrition, nutrition_cascade


def render(result):
    lines = [f"resolved  {result['canonical_name']!r}"
             f"  source={result['source']}  leg={result['leg']}"
             f"  estimate_method={result['estimate_method']}",
             f"          width method={result['method']}  grams={result['grams']}"
             f"  from_cache={result['from_cache']}"]
    for key, (lo, pt, hi) in sorted(result["nutrients"].items()):
        lines.append(f"          {key:<10} {lo:>10} .. {pt:>10} .. {hi:>10}")
    if result["food_id"]:
        lines.append(f"          REQ-NUT-003 foods_cache row {result['food_id']}")
    if result["alias_id"]:
        lines.append(f"          REQ-NUT-004 alias row       {result['alias_id']}")
    return "\n".join(lines)


def render_refusal(e):
    """A refusal is an outcome, not an error (REQ-NUT-027), and WHY it refused is the point."""
    lines = [f"unresolved  {e.item_text!r}"
             + (f"  brand={e.brand!r}" if e.brand else "")
             + f"  reason={e.reason}  review_reason={e.review_reason}"]
    if e.review_reason is None:
        lines.append("            nothing could be asked; this is an operations problem and "
                     "does not belong on Joe's review list (REQ-NUT-024)")
    for entry in e.tried:
        lines.append(f"            {json.dumps(entry, default=str)}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("item_text", help="the food name as uttered")
    ap.add_argument("--brand", default=None,
                    help="the brand or restaurant token; a branded item never falls back to a "
                         "generic source (REQ-NUT-016)")
    quantity = ap.add_mutually_exclusive_group()
    quantity.add_argument("--grams", type=float, default=None)
    quantity.add_argument("--servings", type=float, default=None)
    ap.add_argument("--no-off", action="store_true",
                    help="do not register the Open Food Facts leg at all")
    ap.add_argument("--no-usda", action="store_true",
                    help="do not register either USDA FoodData Central leg at all")
    ap.add_argument("--commit", action="store_true",
                    help="keep the REQ-NUT-003/004 rows; without it the run rolls back")
    args = ap.parse_args()

    conn = db.connect()
    cur = conn.cursor()
    try:
        sources = nutrition.build_sources(cur, off=not args.no_off, usda=not args.no_usda)
        usable = nutrition_cascade.resolvable_sources(sources)
        print("legs      " + ", ".join(
            f"{name}{'' if name in usable else ' (unavailable)'}"
            for name in nutrition_cascade.SOURCE_PRECEDENCE if name in sources))
        # A leg that cannot answer says WHY, once, before any item is attempted. Without this
        # an operator reads "unavailable" and cannot tell a missing api.data.gov key from a
        # run that is pointed at a disposable server (RULE-01) — and only one of those is
        # something they can fix.
        for name in nutrition_cascade.SOURCE_PRECEDENCE:
            leg = sources.get(name)
            if leg is not None and name not in usable and getattr(leg, "detail", None):
                print(f"          {name}: {leg.detail}")
        try:
            result = nutrition.resolve_item(cur, args.item_text, grams=args.grams,
                                            servings=args.servings, brand=args.brand,
                                            sources=sources)
        except nutrition.Unresolved as e:
            print(render_refusal(e))
            conn.rollback()
            return 0                        # REQ-NUT-027: unresolved is a normal outcome
        print(render(result))
        if args.commit:
            conn.commit()
            print("committed")
        else:
            conn.rollback()
            print("rolled back — pass --commit to keep the REQ-NUT-003/004 rows")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
