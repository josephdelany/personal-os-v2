#!/usr/bin/env python3
"""Ask a question. The deterministic path always answers; the model only ever helps (B11.2).

    PYTHONPATH=. python3 tools/ask.py "how is my sleep"
    PYTHONPATH=. python3 tools/ask.py --no-planner "how is my sleep"
    PYTHONPATH=. python3 tools/ask.py --as-of 2026-09-08 "does alcohol affect my hrv"

The order is the design (RULE-15: nothing may require the language model to be available):

1. Try the deterministic executor on the question as asked. If it answers, that is the answer
   and no model is involved — which is most questions, and costs nothing.
2. Only if it REFUSES as unmappable does the planner run, and its whole job is to pick a
   registered question the executor can already answer. The executor then answers that one.
3. If the planner refuses, is over budget, or the model is unreachable, the original
   deterministic refusal is returned. **It is never worse than not having a planner.**

Every answer records which path produced it. A reader who cannot tell whether a model was
involved cannot judge the answer, and "planned" is a fact about provenance, not a footnote.
"""
import argparse
import datetime as dt
import json
import sys

from lib import db


import re

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _envelope(cur, question, as_of, api="public"):
    # Schema names are parameters here for the same reason as in the engines (ADR-0061): a
    # test must be able to exercise this against throwaway schemas rather than creating ones
    # called `public` and `core`, which RULE-01 forbids. Validated, because an identifier
    # cannot be a bind parameter.
    if not _IDENT.match(api):
        raise ValueError(f"not a plain schema identifier: {api!r}")
    cur.execute(f"select {api}.ask(%s, %s)", (question, as_of))
    row = cur.fetchone()[0]
    return row if isinstance(row, dict) else json.loads(row)


def _grammar_missed(envelope):
    """Did the deterministic GRAMMAR fail to map this question? Only then is it the planner's.

    The distinction matters more than it looks. "I do not track that" is a TRUE answer about
    the record — it names the nearest tracked metrics — and handing it to a model would turn an
    honest refusal into a different question that happens to have data, which is the most
    useful-looking way to be wrong. Likewise a refusal for absent data or thin coverage: the
    question was understood and the record cannot answer it, and rephrasing changes the
    question rather than the answer.

    Two observable signatures mean the grammar itself missed:
      * the stored `refusal_unmappable` path — the executor said so directly, or named which
        part of the phrasing it could not read;
      * the search fallback ran and matched nothing, which is what happens when no grammar
        pattern claimed the question at all.
    """
    if not envelope.get("refusal"):
        return False

    # A refusal naming an untracked METRIC is a true answer about the record: it says what is
    # not tracked and lists what is. Rephrasing it would turn an honest refusal into a
    # different question that happens to have data.
    if envelope.get("reason") in ("condition_metric_untracked", "second_metric_unresolved"):
        return False
    if envelope.get("reason") is None and envelope.get("nearest") and "q" not in envelope:
        return False                      # the bare untracked-metric refusal

    # A refusal about the SHAPE of the question — an unreadable date range, a missing spend
    # subject, a condition the parser could not read — is exactly what a rephrase could fix.
    # The earlier ordering returned False on any envelope carrying `nearest`, and all four of
    # these emit `nearest` too, so this whole branch was unreachable and the planner never ran
    # for the cases it would most plausibly help.
    if envelope.get("reason") in ("no_condition_metric", "no_spend_subject",
                                  "invalid_date_range", "condition_not_readable"):
        return True

    # The search fallback found nothing: no grammar pattern claimed the question at all.
    return "q" in envelope and envelope.get("n") == 0


def answer(cur, question, as_of=None, use_planner=True, transport=None,
           api="public", schema="core", ops="ops", config="config"):
    """Returns (envelope, provenance). Provenance is one of:
    'deterministic', 'planned', 'deterministic_after_planner_refused'.
    """
    from tools.engines import ask_planner

    envelope = _envelope(cur, question, as_of, api)
    if not use_planner or not _grammar_missed(envelope):
        return envelope, "deterministic"

    try:
        plan, canonical, attempts = ask_planner.plan_question(
            cur, question, schema=schema, ops=ops, config=config, transport=transport)
    except Exception as e:
        # Budget exhausted, model unreachable, or no registered plan within the cap. The
        # deterministic refusal stands; it is a real answer, and this path must never be
        # worse than not having a planner at all.
        envelope = dict(envelope)
        envelope["planner"] = {"used": False, "reason": type(e).__name__,
                               "detail": str(e)[:200]}
        return envelope, "deterministic_after_planner_refused"

    planned = _envelope(cur, canonical, as_of, api)
    planned = dict(planned)
    planned["planner"] = {"used": True, "attempts": attempts, "plan": plan,
                          "asked_as": canonical, "original_question": question}
    return planned, "planned"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question")
    ap.add_argument("--as-of", help="answer as of this date (YYYY-MM-DD); default today")
    ap.add_argument("--no-planner", action="store_true",
                    help="deterministic only — the path that always works (RULE-15)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    # NOT `dt.date.today()`. That reads the machine's timezone and is a day ahead of the
    # executor's own default — `(now() ET - 4 hours)::date - 1` — so at 01:00 ET the CLI asked
    # about days that cannot yet hold data, and those empty days counted in the coverage
    # denominator and pushed answers toward the INSUFFICIENT floor. Passing NULL lets the RPC
    # use its own default, which is the one number both paths agree on.
    as_of = dt.date.fromisoformat(a.as_of) if a.as_of else None

    conn = db.connect()
    try:
        cur = conn.cursor()
        envelope, provenance = answer(cur, a.question, as_of, use_planner=not a.no_planner)
        conn.commit()
    finally:
        conn.close()

    if a.json:
        print(json.dumps({"provenance": provenance, **envelope}, indent=2, default=str))
        return 0
    print(envelope.get("answer_text") or envelope.get("refusal") or "(no answer)")
    print(f"  [{provenance}; tier={envelope.get('tier')}]")
    if envelope.get("would_raise_it"):
        print(f"  would raise it: {envelope['would_raise_it']}")
    return 0 if envelope.get("answer_text") else 1


if __name__ == "__main__":
    sys.exit(main())
