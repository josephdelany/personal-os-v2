#!/usr/bin/env python3
"""B14.2 — merchant entities and `paid_to` links (REQ-ONT-005, REQ-FIN-070..074, RULE-10,
RULE-12, INV-1, INV-2; ADR-0092).

WHAT THIS IS NOT. The B14 brief's link rules join transactions to VISITS at PLACES and meals
to charges. `core.entities` holds 0 rows, and there are no visit, consume or workout atoms —
so those rules would link nothing to nothing. Building them now would satisfy the brief's
checklist and deliver no capability, which is the failure INTENT_COVERAGE names by name: "a
table and a linking rule do not complete this unit."

WHAT IT IS. The half with real data on both ends: 1,052 transaction atoms and ~108 canonical
merchants resolved from Joe's own descriptors. Each transaction gets one edge
`(transaction atom) -[paid_to]-> (merchant entity)`, which is what lets `spend` answer about a
MERCHANT rather than about a substring of a statement descriptor (ADR-0062's held contract).

THE CONFIDENCE ON THE EDGE IS THE CASCADE'S, NOT A NEW NUMBER. A link inherits the confidence
of the resolution that produced it — 1.0 from an exact pattern, the difflib ratio from a fuzzy
match, and nothing at all from a provisional one, which produces NO link. Inventing an edge
confidence would create a second opinion about the same fact (RULE-12) and the weaker number
would be indistinguishable from the stronger one downstream.

A provisional resolution produces no entity and no link. It waits in the review queue
(REQ-FIN-073). An unlinked transaction is a visible gap; a linked guess is an invisible error.

    PYTHONPATH=. python3 tools/engines/link_merchants.py --core core            # dry run
    PYTHONPATH=. python3 tools/engines/link_merchants.py --core core --commit
"""
import argparse
import collections
import json
import re
import sys
import uuid

from lib import db
from tools.engines.merchants import normalize
from tools.engines.resolve_merchants import build, read_descriptors

CODE_VERSION = "link-merchants-v1"


def decide(res):
    """Whether a resolution earns an edge, and why not when it does not.

    Pure, so the rule can be exercised without a database. Returns (link?, reason).
    """
    if res is None:
        return False, "descriptor_not_in_resolution"
    if res.merchant_source == "not_a_merchant":
        # REQ-FIN-051. An ATM withdrawal has no merchant to point at; its destination is
        # unknown by definition, and an edge to a merchant would assert one.
        return False, f"not_a_merchant:{res.non_merchant_kind}"
    if res.needs_review or not res.canonical:
        # REQ-FIN-073. An unlinked transaction is a visible gap; a linked guess is an
        # invisible error, and the second is much harder to notice six months later.
        return False, "awaiting_review"
    return True, "linked"


def transaction_atoms(cur, schema):
    """Every current transaction atom with the descriptor its evidence span carries."""
    cur.execute(f"""SELECT a.id, a.evidence_span FROM {schema}.atoms a
                     WHERE a.kind = 'transaction'
                       AND NOT EXISTS (SELECT 1 FROM {schema}.atoms s WHERE s.supersedes = a.id)""")
    rows = []
    for atom_id, span in cur.fetchall():
        m = re.search(r"descriptor=([^;]*)", span or "")
        rows.append((atom_id, (m.group(1) if m else "").strip()))
    return rows


def plan(cur, schema):
    descriptors = read_descriptors(cur)
    location, patterns, resolutions, stats = build(descriptors)
    by_norm = {normalize(raw, location).normalized: res
               for raw, (_, res, _) in resolutions.items()}

    atoms = transaction_atoms(cur, schema)
    entities, links, counters = {}, [], collections.Counter()
    for atom_id, descriptor in atoms:
        res = by_norm.get(normalize(descriptor, location).normalized)
        ok, reason = decide(res)
        counters[reason] += 1
        if not ok:
            continue
        entities.setdefault(res.canonical, res)
        links.append((atom_id, res.canonical, res.merchant_source, res.confidence))
    return entities, links, counters, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", default="core")
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args()

    conn = db.connect()
    cur = conn.cursor()
    try:
        entities, links, counters, stats = plan(cur, a.core)
        print(json.dumps(dict(merchant_entities=len(entities), links=len(links),
                              counters=dict(counters)), indent=2, sort_keys=True))
        if not links:
            print("\nNo transaction atoms to link. Run tools/backfill_transactions.py first.")
        if not a.commit:
            conn.rollback()
            print("\nDRY RUN — nothing written.")
            return 0

        ids = {}
        for canonical, res in sorted(entities.items()):
            cur.execute(f"""SELECT id FROM {a.core}.entities
                             WHERE entity_type='merchant' AND canonical_name=%s LIMIT 1""",
                        (canonical,))
            row = cur.fetchone()
            if row:
                ids[canonical] = row[0]
                continue
            eid = uuid.uuid4()
            cur.execute(f"""INSERT INTO {a.core}.entities
                (id, entity_type, canonical_name, provenance, confidence, code_version)
                VALUES (%s,'merchant',%s,%s,%s,%s)""",
                (eid, canonical,
                 # RULE-05 vocabulary: a pattern match is EXTRACTED from a rule Joe's data
                 # supports; a fuzzy match is INFERRED. They are not the same claim.
                 "extracted" if res.merchant_source.startswith("pattern") else "inferred",
                 res.confidence, CODE_VERSION))
            ids[canonical] = eid

        written = 0
        for atom_id, canonical, source, confidence in links:
            # RULE-10 / INV-2: never replace a human edge, and never duplicate one.
            cur.execute(f"""SELECT 1 FROM {a.core}.links
                             WHERE subject_atom=%s AND predicate='paid_to'
                               AND NOT EXISTS (SELECT 1 FROM {a.core}.links s
                                                WHERE s.supersedes = {a.core}.links.id)""",
                        (atom_id,))
            if cur.fetchone():
                continue
            cur.execute(f"""INSERT INTO {a.core}.links
                (subject_atom, predicate, object_entity, provenance, confidence, code_version)
                VALUES (%s,'paid_to',%s,%s,%s,%s)""",
                (atom_id, ids[canonical],
                 "extracted" if source.startswith("pattern") else "inferred",
                 confidence, CODE_VERSION))
            written += 1
        conn.commit()
        print(f"\nCOMMITTED {len(ids)} merchant entities and {written} paid_to links")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
