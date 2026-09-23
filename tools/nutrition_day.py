#!/usr/bin/env python3
"""What Joe ate on one day, read back as intervals (B12 §D.4/§E.3/§G.1).

    PYTHONPATH=. python3 tools/nutrition_day.py 2026-09-11
    PYTHONPATH=. python3 tools/nutrition_day.py 2026-09-11 --target 2200
    PYTHONPATH=. python3 tools/nutrition_day.py 2026-09-11 --analysis restrict
    PYTHONPATH=. python3 tools/nutrition_day.py 2026-09-11 --json

`tools/resolve_nutrition.py` is the WRITE side: a phrase goes in, a cascade runs, atoms come
out. This is the READ side, and until now there wasn't one. `tools/engines/nutrition_display.py`
holds every rule about how a nutrient figure may be shown — REQ-NUT-043's separate bound sums,
REQ-NUT-049's rounding that may never narrow, REQ-NUT-044/063's ban on a bare point,
REQ-NUT-047's plain-words refusal when the interval is wider than the difference — and **nothing
called it.** Sixteen tested rules with no caller is documentation, not behaviour: the same shape
of failure ADR-0137 was written about when `SOURCE_PRECEDENCE` was a constant nothing read.

So every display rule below comes from that module. This file computes no interval, sums no
bound, rounds nothing and writes no sentence about a deficit. It reads rows and asks the engine.

**THIS COMMAND ONLY READS.** Its statements are `SELECT`s against `atoms_current` and
`unresolved_items`; there is no INSERT, UPDATE or DELETE anywhere in it, and no transaction to
commit. Resolution is `tools/resolve_nutrition.py`'s job and stays there.

WHY THE TARGET IS AN ARGUMENT AND NEVER A DEFAULT. REQ-NUT-047 compares the day against a
target, and a calorie target is a specification about Joe that this system has not been given
and must not invent (RULE-09 — models narrate, they do not choose specifications). With no
`--target` the command prints the day and says plainly that it was not asked to compare it to
anything. It does not reach for a plausible 2,000.

WHY IT CHECKS ITS OWN OUTPUT. REQ-NUT-048/064 forbid judgment framing — no over/under, no
pass/fail, no "deficiency" — and the cheapest place for that to leak back in is a print
statement added later by someone who never read the requirement. `nutrition_display.check_framing`
runs over the rendered payload before anything reaches the terminal, and a violation is a
non-zero exit rather than a warning nobody sees.
"""
import argparse
import datetime as dt
import json
import sys

from lib import db
from tools.engines import nutrition_display as display

ENERGY = "kcal"


def read_day(cur, day, schema="core"):
    """The day's `consume` energy atoms and its open review items. Two SELECTs, nothing else.

    Energy specifically, because REQ-NUT-043's daily total and REQ-NUT-047's deficit statement
    are both about energy. The other nutrients are stored as their own atoms and are reported
    per item, not summed here — summing them would be inventing a rule the requirements do not
    state.
    """
    cur.execute(
        f"""select evidence_span, value_low, value_point, value_high, estimate_method, unit
              from {schema}.atoms_current a
             where kind = 'consume' and metric_key = %s and subject_day = %s
               and (to_jsonb(a)->>'event_time_provenance') IS DISTINCT FROM 'defaulted'
               and (to_jsonb(a)->>'quantity_provenance') IS DISTINCT FROM 'defaulted'
               and provenance<>'defaulted'
             order by occurred_at, evidence_span""",
        (ENERGY, day))
    items = []
    for span, low, point, high, method, unit in cur.fetchall():
        items.append({"name": span, "kcal_low": float(low), "kcal_point": float(point),
                      "kcal_high": float(high), "estimate_method": method, "unit": unit,
                      "nutrition_status": "resolved"})

    # REQ-NUT-026: a total that omits an unresolved item must say so, so they are read even
    # though they contribute no number. An item Joe has already answered is closed and is not
    # a gap in this day any more.
    cur.execute(
        f"""select item_text, tried ->> 'reason'
              from {schema}.unresolved_items
             where subject_day = %s and resolved_at is null
             order by seen_at, item_text""",
        (day,))
    unresolved = [{"name": text, "reason": reason} for text, reason in cur.fetchall()]
    cur.execute(f'''SELECT min(evidence_span),
        CASE WHEN bool_or(to_jsonb(a)->>'event_time_provenance'='defaulted')
             THEN 'defaulted_event_time_excluded' ELSE 'defaulted_quantity_excluded' END
        FROM {schema}.atoms_current a
        WHERE kind='consume' AND metric_key=%s AND subject_day=%s
          AND (to_jsonb(a)->>'event_time_provenance'='defaulted'
               OR to_jsonb(a)->>'quantity_provenance'='defaulted' OR provenance='defaulted')
        GROUP BY to_jsonb(a)->>'capture_item_id' ''',(ENERGY,day))
    unresolved.extend({'name':row[0],'reason':row[1]} for row in cur.fetchall())
    return items, unresolved


def build_report(items, unresolved, *, target=None, analysis_mode=None):
    """Rows in, a rendered day out. Every rule applied here belongs to `nutrition_display`."""
    # REQ-NUT-026. The unresolved items go INTO the list the total is computed from, carrying
    # no figures, so `daily_total` counts them and its note says how many are missing. Leaving
    # them out would produce a total that looks complete and silently is not.
    counted = items + [{"nutrition_status": display.UNRESOLVED, "name": u["name"]}
                       for u in unresolved]
    total = display.daily_total(counted)

    report = {
        "n_resolved": total["n_items"],
        "n_unresolved": total["unresolved_items"],
        "unresolved_note": total["unresolved_note"],
        # REQ-NUT-044/063: the day's figure is an interval, rendered by the engine.
        "total": display.render_value(total["kcal_point"], total["kcal_low"],
                                      total["kcal_high"], estimate_method="mixed",
                                      status=display.UNRESOLVED if not total['n_items'] else None),
        # REQ-NUT-042: a day whose items resolved under several methods is reported as the
        # widest claim any of them makes, never as the tightest.
        "methods": sorted({i["estimate_method"] for i in items if i["estimate_method"]}),
        "items": [dict(display.render_value(i["kcal_point"], i["kcal_low"], i["kcal_high"],
                                            estimate_method=i["estimate_method"]),
                       name=i["name"]) for i in items],
        # REQ-NUT-027/062: never a number, and never a failure state.
        "unresolved": [display.unresolved_is_not_an_error(u) for u in unresolved],
    }

    if target is not None:
        # REQ-NUT-047. Whether the difference is even visible at this width is the engine's
        # judgement, not this file's.
        report["deficit"] = display.deficit_statement(total, target)
    if analysis_mode:
        # REQ-NUT-046. What a trend analysis is allowed to use out of this day.
        report["analysis"] = {
            "mode": analysis_mode,
            "rows": [r if isinstance(r, dict) else r
                     for r in display.analysis_rows(items, mode=analysis_mode)]}
    return report


def render(report, day):
    lines = [f"{day}  —  {report['n_resolved']} resolved item(s)"
             + (f", {report['n_unresolved']} unresolved" if report["n_unresolved"] else "")]
    lines.append(f"  total   {report['total']['text']}"
                 + (f"   [{', '.join(report['methods'])}]" if report["methods"] else ""))
    for item in report["items"]:
        lines.append(f"    {item['text']:<28} {item['weight']:<7} {item['name'] or ''}")
    for item in report["unresolved"]:
        # REQ-NUT-062: the words, not a number, not a zero, not a dash.
        lines.append(f"    {item.get('label','not resolved'):<28} {'light':<7} {item['item'] or ''}")
    if report["unresolved_note"]:
        lines.append(f"  {report['unresolved_note']}")
    if "deficit" in report:
        lines.append(f"  {report['deficit']['text']}")
    else:
        lines.append("  no --target was given, so this day was not compared to one.")
    if "analysis" in report:
        rows = report["analysis"]["rows"]
        lines.append(f"  analysis ({report['analysis']['mode']}): {len(rows)} of "
                     f"{report['n_resolved']} item(s) usable")
    return "\n".join(lines)


def framing_violations(report):
    """REQ-NUT-048/064, checked against what is about to be printed rather than trusted."""
    payload = {"total": report["total"]["text"],
               "note": report["unresolved_note"],
               "items": " ".join(i["text"] for i in report["items"]),
               "unresolved": " ".join(i["text"] for i in report["unresolved"])}
    if "deficit" in report:
        payload["deficit"] = report["deficit"]["text"]
    return display.check_framing(payload)


def main(argv=None, connect=None) -> int:
    """`argv` and `connect` are parameters so a test drives THIS function — the one the
    operator runs, argument parsing, refusal and exit code included — against a disposable
    server, rather than a reimplementation of it beside it. ADR-0061 already makes schema
    names parameters for the same reason."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("day", help="the subject day, YYYY-MM-DD (ADR-0019's 04:00 boundary)")
    ap.add_argument("--target", type=float, default=None,
                    help="an energy target to compare the day against (REQ-NUT-047). There is "
                         "no default: a target is a specification about Joe, not one this "
                         "system may choose (RULE-09)")
    ap.add_argument("--analysis", choices=("restrict", "weight"), default=None,
                    help="what a trend analysis may use from this day (REQ-NUT-046)")
    ap.add_argument("--json", action="store_true", help="the report as JSON")
    ap.add_argument("--schema", default="core", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        day = dt.date.fromisoformat(args.day)
    except ValueError:
        print(f"not a date: {args.day!r}", file=sys.stderr)
        return 2

    conn = (connect or db.connect)()
    try:
        cur = conn.cursor()
        items, unresolved = read_day(cur, day, schema=args.schema)
        report = build_report(items, unresolved, target=args.target,
                              analysis_mode=args.analysis)
        violations = framing_violations(report)
        if violations:
            for v in violations:
                print(f"REFUSED: {v}", file=sys.stderr)
            return 1
        print(json.dumps(report, indent=2, default=str) if args.json
              else render(report, day))
        return 0
    finally:
        # Read-only by construction; the rollback is belt-and-braces for a driver that opened
        # a transaction to run the SELECTs.
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
