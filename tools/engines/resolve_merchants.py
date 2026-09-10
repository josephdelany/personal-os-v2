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


def read_stored_patterns(cur, config="config"):
    """REQ-FIN-074. The patterns Joe has confirmed, plus any curated ones.

    `build()` used to construct its pattern list PURELY from discovered normalised forms and
    never read this table, so `review_merchants.py` wrote Joe's confirmation to a table nothing
    queried and his answer changed no subsequent resolution. The whole review loop -- the sheet
    with 157 descriptors needing names -- terminated in a write nobody read.
    """
    cur.execute(f"""SELECT pattern, canonical, is_regex, specificity, provenance
                      FROM {config}.merchant_patterns
                     WHERE provenance <> 'discovered'
                     ORDER BY provenance = 'human' DESC, specificity DESC, pattern""")
    return [Pattern(pattern=r[0], canonical=r[1], is_regex=r[2]) for r in cur.fetchall()]


def read_human_aliases(cur, core="core"):
    """RULE-10. The alias ledger's current human answers, keyed by normalised alias.

    Cascade step 1 -- "the answer, and it outranks every rule permanently" -- had exactly one
    caller in the tree, and it was a test. No production path passed it, so the guarantee was
    enforced by a trigger on a table nothing consulted.
    """
    cur.execute(f"""SELECT alias, canonical FROM {core}.v_current_aliases
                     WHERE resolved_by = 'human' AND canonical IS NOT NULL""")
    return {a: c for a, c in cur.fetchall()}


def build(descriptors, stored_patterns=(), human_aliases=None):
    """Returns (location_tokens, patterns, resolutions, stats)."""
    raws = [d for d, _ in descriptors]
    location = discover_location_tokens(raws)

    normalised = {raw: normalize(raw, location) for raw in raws}
    by_form = collections.defaultdict(set)
    for raw, n in normalised.items():
        if n.normalized:
            by_form[n.normalized].add(raw)

    txn_by_raw = dict(descriptors)
    discovered = [Pattern(pattern=form, canonical=form.title(), is_regex=False)
                  for form, raw_strings in sorted(by_form.items())
                  if len(raw_strings) >= MIN_DISTINCT_RAW
                  or sum(txn_by_raw.get(r, 0) for r in raw_strings) >= MIN_TRANSACTIONS]
    # Stored patterns FIRST. The cascade returns at the first exact match, so a human-confirmed
    # canonical must be reachable before the title-cased guess derived from the same normalised
    # form -- otherwise Joe's "Hannaford" loses to the machine's "Hannaford Waterville".
    stored = list(stored_patterns)
    stored_keys = {(p.pattern.strip().upper(), p.is_regex) for p in stored}
    patterns = stored + [p for p in discovered
                         if (p.pattern.strip().upper(), p.is_regex) not in stored_keys]

    human_aliases = human_aliases or {}
    known = [p.canonical for p in patterns]
    resolutions, by_source = {}, collections.Counter()
    for raw, count in descriptors:
        # `raw=` is not optional here. REQ-FIN-051's classification runs on the RAW string
        # BEFORE normalisation strips the evidence it needs (merchants.py:212). Omitting it
        # made the cascade classify the NORMALISED form -- `punctuation` turns "E-PAYMENT"
        # into "E PAYMENT", which the \bE-?PAYMENT\b rule no longer matches, so that
        # descriptor escaped internal_transfer classification and was resolved as a merchant.
        # tests/test_merchants.py exists to protect exactly this and could not see it, because
        # it called `resolve` directly with the argument this caller was not passing.
        r = resolve(normalised[raw].normalized, patterns, known, raw=raw,
                    human_alias=human_aliases.get(normalised[raw].normalized))
        resolutions[raw] = (normalised[raw], r, count)
        by_source[r.merchant_source] += 1

    stats = dict(
        raw_descriptors=len(raws),
        normalised_forms=len(by_form),
        collapsed=len(raws) - len(by_form),
        location_tokens=len(location),
        patterns_discovered=len(discovered),
        patterns_stored=len(stored),
        human_aliases_applied=sum(
            1 for _, (n, r, _) in resolutions.items() if r.merchant_source == "human"),
        by_source=dict(by_source),
    )
    return location, patterns, resolutions, stats


def write_resolutions(cur, patterns, location, resolutions, evidence,
                      core="core", config="config"):
    """Persist one resolver run. Returns a Counter of what it did.

    Extracted from `main()` so it can be tested against a real schema. The three tests that
    covered this loop read THIS FILE as text and grepped it for string literals -- they passed
    whatever the code did at runtime, and the defect that killed the whole run on any ATM
    descriptor sat underneath two of them for a full review round.
    """
    written = collections.Counter()
    # `config` is a parameter for the same reason `core` is: a test cannot rebind a schema name
    # baked into a string. Hardcoding it here is what forced the three tests over this loop to
    # read the file as TEXT instead of running it, and a crash on ordinary bank input then sat
    # underneath two of them for a full review round. OQ-64 tracks the same question for the
    # migrations, where `config.*` is deliberately NOT schema-parameterised.
    cur.execute(f"DELETE FROM {config}.location_tokens")
    # The measured count, not the constraint's floor: a token following forty merchants and
    # one following exactly four are different evidence and were stored identically.
    for token in sorted(location):
        cur.execute(f"""INSERT INTO {config}.location_tokens (token, distinct_prefixes)
                        VALUES (%s, %s) ON CONFLICT (token) DO NOTHING""",
                    (token, evidence.get(token, 4)))
    cur.execute(f"DELETE FROM {config}.merchant_patterns WHERE provenance = 'discovered'")
    for p in patterns:
        cur.execute(f"""INSERT INTO {config}.merchant_patterns
                       (pattern, canonical, is_regex, specificity, provenance)
                       VALUES (%s,%s,false,0,'discovered')
                       ON CONFLICT (pattern, is_regex) DO NOTHING""",
                    (p.pattern, p.canonical))
    # Keyed by NORMALISED alias, not by raw descriptor. N raw strings collapse onto one
    # alias -- that is this module's whole purpose -- so iterating `resolutions` writes the
    # same alias N times. The first inserted; every later one found the row it had just
    # written, matched it, and was counted `unchanged`, on a table that started EMPTY. The
    # counter could not be read as an idempotence signal, and the raw descriptors that lost
    # the race were dropped without a word.
    by_alias: dict[str, tuple] = {}
    for raw, (n, r, count) in resolutions.items():
        key = n.normalized or raw
        prior = by_alias.get(key)
        # REQ-FIN-061 wants "the original, verbatim". When several raws share an alias there
        # is no single original, so the one with the most transactions is recorded and the
        # rest are kept as `also_seen` rather than silently discarded.
        if prior is None:
            by_alias[key] = (n, r, count, [raw], raw)
        else:
            pn, pr, pcount, seen, pbest = prior
            seen.append(raw)
            by_alias[key] = ((n, r, count, seen, raw) if count > pcount
                             else (pn, pr, pcount, seen, pbest))
    collapsed = sum(len(v[3]) - 1 for v in by_alias.values())
    if collapsed:
        written["raw_descriptors_collapsed"] = collapsed

    for alias_key, (n, r, count, also_seen, raw) in by_alias.items():
        # RULE-10. The head is read FIRST, before the review branch. It used to be read
        # after, so an alias Joe had already answered could be raised again the moment the
        # automated cascade degraded -- a discovered pattern dropping below MIN_DISTINCT_RAW
        # was enough. Joe's answer sat in `entity_aliases` while the queue asked him for it
        # a second time. A permanent correction that gets re-asked is not permanent.
        cur.execute(f"""SELECT alias_id, resolved_by, canonical,
                               non_merchant_kind, confidence
                          FROM {core}.entity_aliases a
                         WHERE a.alias = %s
                           AND NOT EXISTS (SELECT 1 FROM {core}.entity_aliases b
                                            WHERE b.supersedes = a.alias_id)""",
                    (alias_key,))
        head = cur.fetchone()
        if head and head[1] == "human":
            # Joe's correction stands and this run leaves it alone -- it neither supersedes
            # it nor re-queues it.
            #
            # The previous version set `supersedes` unconditionally, so the trigger raised
            # on the first human-corrected alias — and with no exception handling the whole
            # run was lost, every pattern and every token, identically on every subsequent
            # run, forever, because a human head is permanent. "The resolver may revise
            # itself but may not supersede Joe" became "the resolver dies the first time Joe
            # corrects anything".
            written["skipped_human_correction"] += 1
            continue
        if r.needs_review:
            cur.execute(f"""INSERT INTO {core}.merchant_review_queue
                            (alias, raw_descriptor, n_transactions, considered)
                            VALUES (%s,%s,%s,%s)
                            ON CONFLICT (alias) DO NOTHING""",
                        (alias_key, raw, count,
                         json.dumps([[m, round(sc, 4)] for m, sc in r.considered])))
            written["queued_for_review"] += 1
            continue
        # Idempotence. Without this an hourly run appended one superseding row per alias per
        # run to an append-only table — ~12k rows a day at this scale — and "when did this
        # resolution last change?" became unanswerable from the ledger.
        #
        # The comparison must pin EVERYTHING the insert would write, not a convenient
        # subset. `confidence` happens to be a deterministic function of (alias, canonical,
        # cascade step) under today's cascade, so comparing canonical and step pins it by
        # coincidence — the day confidence starts depending on evidence count, a silent
        # comparison stops noticing. It is compared explicitly instead.
        if head is not None:
            same = (head[2] == r.canonical and head[1] == r.merchant_source
                    and head[3] == r.non_merchant_kind
                    and (head[4] is None) == (r.confidence is None)
                    and (r.confidence is None
                         or abs(float(head[4]) - float(r.confidence)) < 1e-9))
            if same:
                written["unchanged"] += 1
                continue
        cur.execute(f"""INSERT INTO {core}.entity_aliases
            (alias, raw_descriptor, also_seen, canonical, non_merchant_kind, resolved_by,
             confidence, normalization_rules, supersedes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (alias_key, raw, sorted(x for x in also_seen if x != raw),
             r.canonical, r.non_merchant_kind, r.merchant_source,
             r.confidence, list(n.rules_fired), head[0] if head else None))
        written["not_a_merchant" if r.merchant_source == "not_a_merchant"
                else "written"] += 1

    return written


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
        location, patterns, resolutions, stats = build(
            descriptors, read_stored_patterns(cur), read_human_aliases(cur, a.core))
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

        written = write_resolutions(cur, patterns, location, resolutions,
                                    location_token_evidence([d for d, _ in descriptors]),
                                    core=a.core)
        conn.commit()
        print(f"\nCOMMITTED {len(patterns)} patterns, {len(location)} location tokens, "
              f"{written['written'] + written['not_a_merchant']} aliases, "
              f"{written['queued_for_review']} review rows")
        if written:
            print("  " + ", ".join(f"{k}={v}" for k, v in sorted(written.items())))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
