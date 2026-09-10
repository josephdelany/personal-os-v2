#!/usr/bin/env python3
"""B14.1 job — discover the merchant vocabulary from Joe's own descriptors and resolve them.

REQ-FIN-060..062, REQ-FIN-070..074, RULE-06, RULE-10, INV-2.

WHAT IT READS. `public.transactions.merchant` holds the RAW bank descriptor, not a resolved
merchant: "WAL-MART #2013 WATERVILLE ME" and "WAL-MART #2013" are the same shop under two
strings. Nothing has ever collapsed them.

WHY DISCOVERY RUNS BEFORE RESOLUTION. The pattern table starts empty, so a first pass with no
patterns would send every descriptor down the fuzzy branch and then to `provisional` —
hundreds of review rows, which is a worse answer than none. Instead:

  1. normalise every descriptor (REQ-FIN-060),
  2. learn the city vocabulary from the normalised forms (a token following four or more
     distinct merchant prefixes is a location, not a name),
  3. re-normalise with that vocabulary,
  4. a normalised form seen on two or more SEPARATE descriptor strings is evidence that the
     normalisation found a real merchant, so it becomes a `discovered` exact pattern,
  5. resolve every descriptor through the full cascade against those patterns.

Step 4 is the load-bearing one and its threshold is deliberately about DISTINCT RAW STRINGS,
not transaction count: fifty charges at one shop under one descriptor prove the shop is
frequent, not that the normalisation collapsed anything. Two different raw strings landing on
one normalised form is the actual evidence.

RULE-01: nothing here invents a merchant. Every canonical name is a normalised form of a
string that appears in Joe's data, and a descriptor that resolves to nothing goes to the
review queue rather than acquiring a plausible name.

    PYTHONPATH=. python3 tools/engines/resolve_merchants.py --core core            # dry run
    PYTHONPATH=. python3 tools/engines/resolve_merchants.py --core core --commit
"""
import argparse
import collections
import json
import sys

from lib import db
from tools.engines.merchants import (Pattern, discover_location_tokens,
                                     location_token_evidence, normalize, resolve)

# Step 4's evidence, in two forms. An earlier version required two DISTINCT RAW STRINGS on one
# normalised form, reasoning that collapse is what proves the normalisation found a merchant.
# That was backwards for the commonest case: "UBER EATS" appears under exactly one string and
# 25 transactions, and sending it to review because it never needed collapsing is absurd — a
# stable descriptor Joe transacts at repeatedly is STRONGER evidence of a real merchant, not
# weaker. Either kind of repetition counts; a descriptor seen exactly once still waits, because
# once could be a typo, a one-off, or a merchant Joe will never see again.
MIN_DISTINCT_RAW = 2          # two raw strings collapsing onto one normalised form
MIN_TRANSACTIONS = 2          # or one string he transacted at more than once


def read_descriptors(cur):
    cur.execute("""SELECT merchant, count(*) FROM public.transactions
                    WHERE merchant IS NOT NULL AND btrim(merchant) <> ''
                    GROUP BY 1 ORDER BY 2 DESC""")
    return cur.fetchall()


def build(descriptors):
    """Returns (location_tokens, patterns, resolutions, stats)."""
    raws = [d for d, _ in descriptors]
    location = discover_location_tokens(raws)

    normalised = {raw: normalize(raw, location) for raw in raws}
    by_form = collections.defaultdict(set)
    for raw, n in normalised.items():
        if n.normalized:
            by_form[n.normalized].add(raw)

    txn_by_raw = dict(descriptors)
    patterns = [Pattern(pattern=form, canonical=form.title(), is_regex=False)
                for form, raw_strings in sorted(by_form.items())
                if len(raw_strings) >= MIN_DISTINCT_RAW
                or sum(txn_by_raw.get(r, 0) for r in raw_strings) >= MIN_TRANSACTIONS]

    known = [p.canonical for p in patterns]
    resolutions, by_source = {}, collections.Counter()
    for raw, count in descriptors:
        r = resolve(normalised[raw].normalized, patterns, known)
        resolutions[raw] = (normalised[raw], r, count)
        by_source[r.merchant_source] += 1

    stats = dict(
        raw_descriptors=len(raws),
        normalised_forms=len(by_form),
        collapsed=len(raws) - len(by_form),
        location_tokens=len(location),
        patterns_discovered=len(patterns),
        by_source=dict(by_source),
    )
    return location, patterns, resolutions, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", default="core")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--show", type=int, default=0, help="print N collapse examples")
    a = ap.parse_args()

    conn = db.connect()
    cur = conn.cursor()
    try:
        descriptors = read_descriptors(cur)
        location, patterns, resolutions, stats = build(descriptors)
        print(json.dumps(stats, sort_keys=True, indent=2))

        if a.show:
            groups = collections.defaultdict(list)
            for raw, (n, r, count) in resolutions.items():
                groups[r.canonical].append(raw)
            merged = sorted(((c, v) for c, v in groups.items() if len(v) > 1),
                            key=lambda t: -len(t[1]))[:a.show]
            print(f"\n{len(merged)} canonical merchants collapse more than one raw string:")
            for canonical, raws in merged:
                print(f"  {canonical!r} <- {len(raws)} strings")

        # Distinct strings is the review BURDEN; transactions is the spend COVERAGE. They
        # differ a lot, because a long tail of one-off merchants is many strings and little
        # money, and reporting only the first makes a usable resolver look broken.
        review = [raw for raw, (_, r, _) in resolutions.items() if r.needs_review]
        total_txn = sum(c for _, c in descriptors)
        review_txn = sum(resolutions[raw][2] for raw in review)
        nonmerch_txn = sum(c for raw, (_, r, c) in resolutions.items()
                           if r.merchant_source == "not_a_merchant")
        resolved_txn = total_txn - review_txn - nonmerch_txn
        print(f"\nreview burden : {len(review)} of {len(descriptors)} distinct descriptors "
              f"({100 * len(review) / max(len(descriptors), 1):.0f}%)")
        print(f"spend coverage: {resolved_txn} of {total_txn} transactions resolved "
              f"({100 * resolved_txn / max(total_txn, 1):.0f}%); {nonmerch_txn} are "
              f"ATM/transfer/fee (REQ-FIN-051, not merchants); {review_txn} await Joe")
        print("REQ-FIN-073: every one of those waits; none becomes a fact")

        if not a.commit:
            print("\nDRY RUN — nothing written.")
            return 0

        cur.execute("DELETE FROM config.location_tokens")
        # The measured count, not the constraint's floor: a token following forty merchants and
        # one following exactly four are different evidence and were stored identically.
        evidence = location_token_evidence([d for d, _ in descriptors])
        for token in sorted(location):
            cur.execute("""INSERT INTO config.location_tokens (token, distinct_prefixes)
                           VALUES (%s, %s) ON CONFLICT (token) DO NOTHING""",
                        (token, evidence.get(token, 4)))
        written = collections.Counter()
        cur.execute("DELETE FROM config.merchant_patterns WHERE provenance = 'discovered'")
        for p in patterns:
            cur.execute("""INSERT INTO config.merchant_patterns
                           (pattern, canonical, is_regex, specificity, provenance)
                           VALUES (%s,%s,false,0,'discovered')
                           ON CONFLICT (pattern, is_regex) DO NOTHING""",
                        (p.pattern, p.canonical))
        for raw, (n, r, count) in resolutions.items():
            if r.needs_review:
                cur.execute(f"""INSERT INTO {a.core}.merchant_review_queue
                                (alias, raw_descriptor, n_transactions, considered)
                                VALUES (%s,%s,%s,%s)
                                ON CONFLICT (alias) DO NOTHING""",
                            (n.normalized or raw, raw, count,
                             json.dumps([[m, round(s, 4)] for m, s in r.considered])))
                continue
            # RULE-10. A re-run supersedes the CURRENT HEAD for this alias rather than adding
            # a second current row. The trigger in 0057 now refuses both alternatives — a bare
            # insert over an existing head, and a fork off an already-superseded row.
            cur.execute(f"""SELECT alias_id, resolved_by, canonical
                              FROM {a.core}.entity_aliases a
                             WHERE a.alias = %s
                               AND NOT EXISTS (SELECT 1 FROM {a.core}.entity_aliases b
                                                WHERE b.supersedes = a.alias_id)""",
                        (n.normalized,))
            head = cur.fetchone()
            if head and head[1] == "human":
                # RULE-10. Joe's correction stands and this run leaves it alone.
                #
                # The previous version set `supersedes` unconditionally, so the trigger raised
                # on the first human-corrected alias — and with no exception handling the whole
                # run was lost, every pattern and every token, identically on every subsequent
                # run, forever, because a human head is permanent. "The resolver may revise
                # itself but may not supersede Joe" became "the resolver dies the first time Joe
                # corrects anything".
                written["skipped_human_correction"] += 1
                continue
            if head and head[2] == r.canonical and head[1] == r.merchant_source:
                # Idempotence. Without this an hourly run appended one superseding row per
                # alias per run to an append-only table — ~12k rows a day at this scale — and
                # "when did this resolution last change?" became unanswerable from the ledger.
                written["unchanged"] += 1
                continue
            cur.execute(f"""INSERT INTO {a.core}.entity_aliases
                (alias, raw_descriptor, canonical, resolved_by, confidence,
                 normalization_rules, supersedes)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (n.normalized, raw, r.canonical, r.merchant_source, r.confidence,
                 list(n.rules_fired), head[0] if head else None))
        conn.commit()
        print(f"\nCOMMITTED {len(patterns)} patterns, {len(location)} location tokens, "
              f"{len(resolutions) - len(review)} aliases, {len(review)} review rows")
        if written:
            print("  " + ", ".join(f"{k}={v}" for k, v in sorted(written.items())))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
