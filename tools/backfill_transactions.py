#!/usr/bin/env python3
"""Backfill public.transactions -> core.atoms so `spend` has anything to read.

REQ-FIN-001 (a transaction is an atom of kind 'transaction'), REQ-FIN-040/041, RULE-01,
RULE-04, INV-1, INV-2, ADR-0025 (reconciled, not equal), ADR-0059 (the atom shape).

WHY THIS EXISTS. `core.atoms` holds ZERO transaction atoms. `public.ask`'s `spend` operation
reads transaction atoms, so it currently cannot answer a spend question at any tier — not
because the data is missing, but because 1,052 real transactions live only in the legacy
`public.transactions` table and nothing has ever moved them across. That is M2's last unmet
operation and it is a plumbing gap, not a design one.

IT REUSES THE IMPORTER'S SHAPE, IT DOES NOT INVENT ONE. The AtomSpec below is byte-identical
in structure to what `tools/importers/bank.py` emits — same kind, same metric_key, same unit,
same state_class, same evidence_span grammar — and it is written by `import_drop.insert_atoms`,
the same writer. Two producers of one measure with two shapes is RULE-12's failure mode: a
query that works on file-imported spend and silently misses backfilled spend.

LINEAGE (INV-1). Every atom traces to a raw_capture. Legacy rows have no capture of their own,
so one capture row per (source) batch is created with `source='legacy_archive'`, carrying the
row count and the query that produced it. That is honest: the capture is the BACKFILL, and it
says so, rather than pretending each legacy row arrived through a device.

KNOWLEDGE TIME (RULE-04). `recorded_at` is when the backfill ran, not when the purchase
happened. The subject day comes from the transaction's own timestamp. A replay of a question
asked before this backfill therefore does not see these atoms, which is correct: the system
did not know them then.

    PYTHONPATH=. python3 tools/backfill_transactions.py --core core            # dry run
    PYTHONPATH=. python3 tools/backfill_transactions.py --core core --commit
"""
import argparse
import collections
import datetime as dt
import json
import sys
import uuid
from zoneinfo import ZoneInfo

from lib import db
from tools.import_drop import insert_atoms
from tools.importers.common import AtomSpec, quantise, utc_key

CODE_VERSION = "backfill-transactions-v1"
ET = ZoneInfo("America/New_York")


def specs(cur):
    """One AtomSpec per legacy transaction, in bank.py's shape."""
    cur.execute("""SELECT id, ts, amount, currency, merchant, category, source
                     FROM public.transactions
                    WHERE amount IS NOT NULL AND ts IS NOT NULL
                    ORDER BY ts""")
    out, counters = [], collections.Counter()
    for _id, ts, amount, currency, merchant, category, source in cur.fetchall():
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        # RULE-04: a purchase dated in the future is not a purchase we observed.
        if ts.astimezone(ET).date() > dt.datetime.now(ET).date():
            counters["future_dated"] += 1
            continue
        cur_code = (currency or "USD").upper()
        if cur_code != "USD":
            # `transaction_amount_usd` says USD in its name. Converting would invent a rate
            # (RULE-09) and storing a EUR amount under a USD key would be a lie by column.
            counters[f"not_usd:{cur_code}"] += 1
            continue
        out.append(AtomSpec(
            kind="transaction",
            metric_key="transaction_amount_usd",
            occurred_at=ts,
            value=float(amount),
            unit="usd",
            state_class="total",
            estimate_method="measured",
            time_precision="exact",
            # REQ-FIN-047 + INV-1. `legacy_id` is not decoration. Five groups of legacy rows
            # are identical on (timestamp, amount, descriptor) because their timestamps are
            # DATE-ONLY — midnight ET, no clock time — so the dedupe key cannot tell two real
            # purchases from one double-ingest. Two MTA tickets in a day is ordinary; three
            # identical reversals is suspicious. Deciding either way silently is the failure:
            # skipping loses real spend, merging invents certainty. Carrying the legacy row id
            # makes every atom distinct and traceable, so all nine rows survive, a re-run still
            # dedupes exactly, and the ambiguity is REPORTED for review rather than resolved by
            # a coin flip (REQ-FIN-047: do not merge, raise it).
            evidence_span=(f"legacy:{source or 'unknown'};legacy_id={_id}"
                           f";merchant={(merchant or '').strip()}"
                           f";descriptor={(merchant or '').strip()}"
                           + (f";category={category}" if category else "")),
        ))
        counters["mapped"] += 1
    return out, counters


def existing_keys(cur, schema):
    """ADR-0025 / INV-2: re-running must add nothing. Same dedupe key as import_drop."""
    cur.execute(f"""SELECT kind, metric_key, occurred_at, lower(valid_interval),
                           upper(valid_interval), value_point, evidence_span
                      FROM {schema}.atoms WHERE kind = 'transaction'""")
    return {(k, mk, utc_key(o), utc_key(lo), utc_key(hi), quantise(v), ev)
            for k, mk, o, lo, hi, v, ev in cur.fetchall()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", default="core")
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args()

    conn = db.connect()
    cur = conn.cursor()
    try:
        batch, counters = specs(cur)
        seen = existing_keys(cur, a.core)
        fresh, duplicates = [], 0
        for s in batch:
            key = s.dedupe_key
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            fresh.append(s)

        # REQ-FIN-047: report the groups a date-only timestamp cannot disambiguate.
        cur.execute("""SELECT count(*) FROM (
              SELECT ts, amount, merchant FROM public.transactions
               WHERE amount IS NOT NULL AND ts IS NOT NULL
               GROUP BY 1,2,3 HAVING count(*) > 1) d""")
        ambiguous = cur.fetchone()[0]

        days = {s.subject_day for s in fresh}
        report = dict(legacy_rows_considered=sum(counters.values()),
                      atoms_to_write=len(fresh), duplicates_skipped=duplicates,
                      subject_days=len(days),
                      period=[min(days).isoformat(), max(days).isoformat()] if days else None,
                      counters=dict(counters),
                      ambiguous_dedupe_groups=ambiguous)
        print(json.dumps(report, indent=2, sort_keys=True))
        if ambiguous:
            print(f"\nREQ-FIN-047: {ambiguous} group(s) of legacy rows are identical on "
                  f"(timestamp, amount, descriptor) because the timestamp carries no clock "
                  f"time. All rows are written and traceable by legacy_id; NONE is merged and "
                  f"none is dropped. Whether each is a repeat purchase or a double ingest is "
                  f"Joe's to say.")

        if not a.commit:
            conn.rollback()
            print("\nDRY RUN — nothing written.")
            return 0

        capture_id = uuid.uuid4()
        cur.execute(f"""INSERT INTO {a.core}.raw_captures
            (capture_id, source, captured_at, payload, trust_level)
            VALUES (%s, 'legacy_archive', now(), %s, 'trusted')""",
            (capture_id, json.dumps({
                "kind": "backfill",
                "of": "public.transactions",
                "rows": len(fresh),
                "code_version": CODE_VERSION,
                # The capture IS the backfill and says so, rather than pretending each legacy
                # row arrived through a device (INV-1, ADR-0025).
                "query": "SELECT id, ts, amount, currency, merchant, category, source "
                         "FROM public.transactions WHERE amount IS NOT NULL AND ts IS NOT NULL",
            })))
        written = 0
        for i in range(0, len(fresh), 500):
            written += insert_atoms(cur, a.core, capture_id, fresh[i:i + 500], CODE_VERSION)
        conn.commit()
        print(f"\nCOMMITTED {written} transaction atoms under capture {capture_id}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
