#!/usr/bin/env python3
"""Is Joe using what he keeps paying for? (REQ-FIN-110..116, REQ-REC-009; R4; ADR-0140)

    PYTHONPATH=. python3 tools/service_usage.py                  # report, writes nothing
    PYTHONPATH=. python3 tools/service_usage.py --commit         # store the usage EVENTS
    PYTHONPATH=. python3 tools/service_usage.py --as-of 2026-09-11

THE GAP THIS CLOSES. `tools/engines/recurrence.py` builds subscription streams and
`tools/engines/usage_status.py` turns evidence into a REQ-FIN-110 tier. Both were complete,
tested, and called by nothing outside `tests/`. Nothing read a recurring charge and asked whether
the thing was used, which is the question the whole of B17 §C.1 exists to answer.

THE SENTENCE THIS TOOL IS BUILT AROUND. **An outage is not proof of nonuse.** The Watch stopped
in five stages ending 2026-08-21; the bank CSV export died 2026-05-13. The largest silences in
this system are its own instruments failing, so "no gym visit recorded since May" is, on this
data, far more likely to be a statement about a logger than about Joe. Three tiers, and the
difference between the last two is the entire feature:

    used      something recorded a use, recently enough to say so
    unused    the source KEPT RECORDING afterwards and registered no further use
    unknown   nothing was watching -- or nothing established whether anything was

WHAT IT REFUSES TO DO.

  * It never says 'unused' without naming the window in which something was watching and saw
    nothing. `usage_status.from_evidence` will not return that tier without `source_last_seen`.
  * It never writes a row asserting nonuse. Only a positive usage event is stored
    (`config.reconstruction_methods` gives `service_usage` the single output `occurred`).
    Nonuse is the absence of a class of events over a window, not an event.
  * It never uses the words REQ-FIN-112 bans. Every string it emits goes through
    `usage_status.guard_words`, on write rather than on display, because a stored word leaks
    into an export later.
  * It computes no necessity, score or percentage. Whether a purchase was worth making is not a
    fact this system can observe (REQ-FIN-110's own rejected alternatives).
"""
import argparse
import collections
import datetime as dt
import sys

from lib import db
from tools.engines import recurrence, usage_status
from tools.engines.reconstruct import Evidence, evaluate, to_row
from tools.reconstruct_run import load_method, write

# REQ-FIN-111. The tier moves only on an explicit evidence row, and these are the atom kinds
# that constitute one. A transaction at a merchant with a physical location is included because
# REQ-FIN-123 makes it a location fix: a card present at a gym is stronger evidence of being at
# the gym than most things this system could infer, and it costs no capture at all.
USAGE_KINDS = ("place_visit", "media_play", "web_visit")

# How long after the last recorded use the status stops reading as 'used'. Stored here rather
# than guessed per call; it is not a measurement definition about Joe, it is the reporting
# window this tool uses, and it is stated so a reader can disagree with it.
UNUSED_AFTER_DAYS = 60


def streams(cur, *, core="core", as_of, min_charges=recurrence.EARLY_OCCURRENCES):
    """Recurring charge streams, built by the engine from transaction atoms.

    Reads `core.atoms` rather than `public.transactions`: the atom lane is the one every other
    measure uses, and a tool that reads the legacy table would silently miss anything imported
    after the backfill (the defect `tools/backfill_transactions.py` documents).
    """
    cur.execute(f"""
        SELECT a.occurred_at::date AS day,
               a.value_point       AS amount,
               a.evidence_span     AS span
          FROM {core}.atoms a
         WHERE a.kind = 'transaction'
           AND a.metric_key = 'transaction_amount_usd'
           AND a.value_point < 0
           AND a.occurred_at::date <= %s
         ORDER BY a.occurred_at
    """, (as_of,))
    charges = []
    for day, amount, span in cur.fetchall():
        merchant = _field(span, "merchant") or _field(span, "descriptor")
        if not merchant:
            continue
        charges.append({"merchant": merchant, "account": _field(span, "legacy") or "default",
                        "day": day, "amount": abs(float(amount))})
    return recurrence.detect(charges, as_of=as_of)


def _field(span, key):
    """One `k=v` field out of an `evidence_span`. The span is the single representation of a
    transaction's descriptor; parsing it here beats adding a column that can drift from it."""
    for part in (span or "").split(";"):
        name, _, value = part.partition("=")
        if name.strip() == key:
            return value.strip() or None
    return None


def usage_rows(cur, merchant, *, core="core", as_of):
    """Explicit usage evidence for one merchant (REQ-FIN-111)."""
    cur.execute(f"""
        SELECT a.subject_day, a.kind, a.recorded_at
          FROM {core}.atoms a
         WHERE a.kind = ANY(%s)
           AND a.evidence_span ILIKE %s
           AND a.subject_day <= %s
         ORDER BY a.subject_day
    """, (list(USAGE_KINDS), f"%{merchant}%", as_of))
    return [{"day": d, "kind": k, "recorded_at": r} for d, k, r in cur.fetchall()]


def source_last_seen(cur, *, core="core", as_of):
    """The last subject day on which the usage SOURCE recorded anything at all.

    **NOT about any particular merchant, and that is the point.** The question is whether the
    instrument was alive, so the answer must come from the instrument's whole output. Asking
    "when did this source last see THIS gym" would return the same date as the last visit and
    make every outage look like continued watching — the tautology this whole feature exists to
    avoid.

    `None` means the source has never recorded anything, which is the current state of this
    database: no `place_visit`, `media_play` or `web_visit` atom has ever been written. Every
    service is therefore 'unknown', and that is the correct answer rather than a failure.
    """
    cur.execute(f"""SELECT max(a.subject_day) FROM {core}.atoms a
                     WHERE a.kind = ANY(%s) AND a.subject_day <= %s""",
                (list(USAGE_KINDS), as_of))
    return cur.fetchone()[0]


def assess(cur, *, core="core", as_of, unused_after_days=UNUSED_AFTER_DAYS):
    """(stream, status, rows) per recurring service. Computes; writes nothing."""
    watching = source_last_seen(cur, core=core, as_of=as_of)
    out = []
    for stream in streams(cur, core=core, as_of=as_of):
        rows = usage_rows(cur, stream.merchant, core=core, as_of=as_of)
        status = usage_status.from_evidence(
            stream.merchant, rows, as_of=as_of, unused_after_days=unused_after_days,
            source_last_seen=watching)
        out.append((stream, status, rows))
    return out, watching


def evidence_for(stream, status, rows, *, watching, as_of):
    """Citations for one service's usage conclusion.

    **THE TWO REQUIRED CITATIONS ARE DERIVED FROM THE TIER, SO THE OUTAGE RULE LIVES IN EXACTLY
    ONE PLACE.** `usage_status.from_evidence` already decides whether anything was watching;
    restating that decision here as a second date comparison would be two rules that can drift,
    and the first version of this function got the second one wrong — it demanded that the source
    outlive the last use even when that use was two days ago, so a currently-active gym came back
    `unknown`.

        tier 'used'     -> the service was used recently: BOTH citations
        tier 'unused'   -> something was watching and saw nothing: the WINDOW only.
                           No `usage_evidence`, so the method cannot conclude a use occurred,
                           and the engine returns unknown. The 'unused' TIER is reported by
                           this tool; it is never stored as an event.
        tier 'unknown'  -> nothing was watching, or continuity was never established: NEITHER.
                           The engine's REQ-REC-009 path names both missing inputs.

    A dead source is therefore structurally incapable of producing a conclusion: it cannot make
    `usage_status` return anything but 'unknown', and 'unknown' emits no required citation.
    """
    last = max((r["day"] for r in rows), default=None)
    recorded = max((r["recorded_at"] for r in rows), default=None) or dt.datetime.combine(
        as_of, dt.time(0), dt.timezone.utc)
    ev = [Evidence(ref=f"stream:{stream.merchant}:{stream.account}",
                   kind="recurring_charge_stream", stance="supports",
                   origin_group=f"bank:{stream.account}", recorded_at=recorded)]
    if status.tier in ("used", "unused") and watching is not None:
        ev.append(Evidence(ref=f"window:{(last or as_of).isoformat()}..{watching.isoformat()}",
                           kind="usage_observation_window", stance="supports",
                           origin_group=f"usage_capture:{watching.isoformat()}",
                           recorded_at=recorded))
    if status.tier == "used" and last is not None:
        ev.append(Evidence(ref=f"usage:{stream.merchant}:{last.isoformat()}",
                           kind="usage_evidence", stance="supports",
                           # A visit is a different capture path from the bank feed, so it is a
                           # genuinely independent origin.
                           origin_group=f"usage_capture:{last.isoformat()}",
                           recorded_at=recorded))
    return tuple(ev)


def rows_for(cur, method, *, core="core", as_of, unused_after_days=UNUSED_AFTER_DAYS,
             coverage=None):
    """Rows to store: only services with an established, observed USE."""
    assessed, watching = assess(cur, core=core, as_of=as_of,
                                unused_after_days=unused_after_days)
    out = []
    unknown = coverage if coverage is not None else []
    for stream, status, rows in assessed:
        ev = evidence_for(stream, status, rows, watching=watching, as_of=as_of)
        recorded = max((e.recorded_at for e in ev), default=None)
        r = evaluate(method, ev, as_of=recorded)
        if r.presence == "unknown":
            # Not a conclusion, so not a row. `inferred_events` stores conclusions, and a
            # service nobody observed is the default state of every service nobody examined.
            unknown.append((stream.merchant, status.tier, r.missing_evidence))
            continue
        day = max(x["day"] for x in rows)
        start = dt.datetime.combine(day, dt.time(0), dt.timezone.utc)
        out.append((day, r, ev, to_row(
            r, method, event_time_from=start, event_time_to=start + dt.timedelta(days=1),
            subject_day=day, knowledge_time=recorded)))
    return out, assessed, watching


def render(assessed, watching, coverage, *, as_of):
    tiers = collections.Counter(s.tier for _, s, _ in assessed)
    print(f"Recurring services at {as_of}: {len(assessed)}")
    if watching is None:
        print("  The usage source has NEVER recorded anything — no place_visit, media_play or")
        print("  web_visit atom exists. Every service below is 'unknown' for that reason, which")
        print("  is a true statement about the record and not a failure of this tool.")
    else:
        print(f"  Usage source last recorded anything on {watching} "
              f"({(as_of - watching).days} days ago).")
    for tier in usage_status.TIERS:
        print(f"    {tier:<8} {tiers.get(tier, 0)}")
    print()
    for stream, status, _ in sorted(assessed, key=lambda t: t[0].merchant):
        # REQ-FIN-113: never a bare label. The evidence is printed with the tier, always.
        print(f"  {status.tier:<8} {stream.merchant}")
        print(f"           every {stream.period_days}d, {stream.lifecycle}, "
              f"{stream.occurrences} charges, {stream.amount_behaviour}")
        print(f"           {status.evidence}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--core", default="core")
    ap.add_argument("--config", default="config")
    ap.add_argument("--as-of")
    ap.add_argument("--unused-after-days", type=int, default=UNUSED_AFTER_DAYS)
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args(argv)
    as_of = dt.date.fromisoformat(a.as_of) if a.as_of else dt.date.today()

    conn = db.connect()
    cur = conn.cursor()
    try:
        method = load_method(cur, "service_usage", core=a.core, config=a.config)
        coverage: list = []
        rows, assessed, watching = rows_for(
            cur, method, core=a.core, as_of=as_of,
            unused_after_days=a.unused_after_days, coverage=coverage)
        render(assessed, watching, coverage, as_of=as_of)
        if coverage:
            print(f"\n  {len(coverage)} service(s) with no stored usage event — reported, not "
                  f"written. An unknown is not a conclusion.")
            for merchant, tier, missing in coverage[:10]:
                print(f"    {merchant}: {tier}; missing {list(missing)}")
        if not a.commit:
            print("\nDRY RUN — nothing written. Re-run with --commit.")
            return 0
        stored = write(cur, rows, core=a.core)
        conn.commit()
        print(f"\nCOMMITTED {stored} usage event(s) with their evidence.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
