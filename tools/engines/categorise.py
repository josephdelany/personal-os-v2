#!/usr/bin/env python3
"""B14.3 — merchant category rules, discovered from Joe's own prior categorisation.

REQ-FIN-051, REQ-FIN-070..074, RULE-01, RULE-06, RULE-12, RULE-10.

WHERE THE CATEGORIES COME FROM. `public.transactions.category` holds Joe's existing
classification of 1,002 charges. This does not invent a taxonomy; it reads the one already in
his data and attaches it to the merchant ENTITY, so a category survives a descriptor changing.

TWO VOCABULARIES ARE MIXED IN THERE, and conflating them would be the ADR-0089 mistake again:

    snake_case   bank_fee, transfer_person, dining, groceries, coffee, gas_convenience, ...
    Title Case   Food & Drink, Travel, Fees & Adjustments, Personal, Groceries

`groceries` (82 charges) and `Groceries` (9) differ only in case and are the same concept, so
folding case is deterministic and safe. `Food & Drink` against `dining` + `coffee` +
`bar_alcohol_smoke` is NOT a synonym — it is a coarser grain, and merging them changes what a
"dining" total means without anyone choosing that. So case is folded; vocabularies are NOT
mapped onto each other, and the split is reported for Joe to rule on (OQ-59).

A MERCHANT GETS A CATEGORY ONLY WHEN ITS OWN CHARGES AGREE. The rule is a two-thirds majority
of that merchant's categorised charges. A merchant whose charges disagree gets none and is
reported: a modal category from a 50/50 split is a coin flip presented as a fact (RULE-06).

REQ-FIN-051 is enforced positively, not by absence: ATM, transfer and fee descriptors are
classified as non-merchants and never reach a category rollup, and this tool refuses to write a
category rule for one even if the legacy data carried one.

    PYTHONPATH=. python3 tools/engines/categorise.py --core core            # dry run
    PYTHONPATH=. python3 tools/engines/categorise.py --core core --commit
"""
import argparse
import collections
import json
import sys

from lib import db
from tools.engines.merchants import classify_non_merchant, normalize
from tools.engines.resolve_merchants import build, read_descriptors

MAJORITY = 2 / 3


def fold(category: str) -> str:
    """Case only. `groceries` and `Groceries` are one concept; `Food & Drink` and `dining`
    are two, and this function is deliberately incapable of merging those."""
    return (category or "").strip().lower()


def vocabularies(categories):
    """Which naming convention each category follows, so a mixed set is visible not silent."""
    snake = {c for c in categories if c and c == c.lower() and " " not in c}
    other = {c for c in categories if c and c not in snake}
    return sorted(snake), sorted(other)


def assign(counts):
    """A merchant's category, or None when its own charges do not agree.

    Pure, so the rule is exercised without a database. A two-thirds majority of that
    merchant's CATEGORISED charges; uncategorised ones neither vote nor block.
    """
    known = {c: n for c, n in counts.items() if c != "__uncategorised__"}
    if not known:
        return None
    total = sum(known.values())
    top, top_n = max(known.items(), key=lambda kv: (kv[1], kv[0]))
    if top_n / total >= MAJORITY:
        return top, round(top_n / total, 3), total
    # RULE-06: a modal category from a split is a coin flip presented as a fact.
    return None


def plan(cur):
    cur.execute("""SELECT merchant, category, count(*) FROM public.transactions
                    WHERE merchant IS NOT NULL AND btrim(merchant) <> ''
                    GROUP BY 1, 2""")
    rows = cur.fetchall()
    descriptors = read_descriptors(cur)
    location, _, resolutions, _ = build(descriptors)

    per_merchant = collections.defaultdict(collections.Counter)
    raw_categories = set()
    for descriptor, category, n in rows:
        res = resolutions.get(descriptor, (None, None, None))[1]
        if res is None or res.merchant_source == "not_a_merchant":
            continue
        if res.needs_review or not res.canonical:
            continue
        if category:
            raw_categories.add(category)
            per_merchant[res.canonical][fold(category)] += n
        else:
            per_merchant[res.canonical]["__uncategorised__"] += n

    assigned, disagreed, uncategorised = {}, {}, []
    for merchant, counts in per_merchant.items():
        verdict = assign(counts)
        known = {c: n for c, n in counts.items() if c != "__uncategorised__"}
        if not known:
            uncategorised.append(merchant)
        elif verdict:
            assigned[merchant] = verdict
        else:
            disagreed[merchant] = dict(known)
    return assigned, disagreed, uncategorised, raw_categories


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", default="core")
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args()
    conn = db.connect()
    cur = conn.cursor()
    try:
        assigned, disagreed, uncategorised, raw = plan(cur)
        snake, other = vocabularies(raw)
        print(json.dumps(dict(merchants_with_a_category=len(assigned),
                              merchants_whose_charges_disagree=len(disagreed),
                              merchants_with_no_categorised_charge=len(uncategorised),
                              distinct_categories=len(raw)), indent=2, sort_keys=True))
        print(f"\nTWO VOCABULARIES, not merged (OQ-59):")
        print(f"  snake_case ({len(snake)}): {', '.join(snake)}")
        print(f"  other      ({len(other)}): {', '.join(other)}")
        if disagreed:
            print(f"\n{len(disagreed)} merchant(s) whose own charges disagree — no rule written:")
            for m, counts in sorted(disagreed.items())[:6]:
                print(f"  {m}: {counts}")

        if not a.commit:
            print("\nDRY RUN — nothing written.")
            return 0
        cur.execute("DELETE FROM config.category_rules WHERE provenance = 'discovered'")
        for merchant, (category, share, n) in sorted(assigned.items()):
            if classify_non_merchant(merchant):
                continue        # REQ-FIN-051, enforced positively
            cur.execute("""INSERT INTO config.category_rules
                           (merchant_canonical, category, provenance)
                           VALUES (%s,%s,'discovered')
                           ON CONFLICT (merchant_canonical) DO NOTHING""", (merchant, category))
        conn.commit()
        print(f"\nCOMMITTED {len(assigned)} category rules")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
