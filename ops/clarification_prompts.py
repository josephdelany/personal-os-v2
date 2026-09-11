#!/usr/bin/env python3
"""What would settle it, asked at most once (REQ-REC-015, RULE-27, ADR-0140).

    PYTHONPATH=. python3 ops/clarification_prompts.py                    # plan only, no writes
    PYTHONPATH=. python3 ops/clarification_prompts.py --json
    PYTHONPATH=. python3 ops/clarification_prompts.py --at 09:00 --commit

**The gap this closes.** REQ-REC-015 has two halves. The first — "return the missing evidence
that would distinguish the alternatives, or state that none was identified" — is built:
`tools/engines/reconstruct.py` computes it, migration 0069 stores it in
`core.inferred_events.discriminating_evidence`, and `public.get_reconstruction` returns it. The
second half is the clause at the end: *"with any user prompt subject to existing cadence and
dismissal rules"*. Nothing connected the first half to a prompt, and `core.prompt_dispatch`
(migration 0009, `SHAPE LOCKED`, "wired when prompts exist") had no writer of any kind. This is
that writer, and it is the ONLY one: a second prompt mechanism would be a second place for
RULE-27 to be true, which is the same as it not being true.

**What it does NOT do, stated plainly.** It SCHEDULES. It does not deliver. `delivered_at` is
left NULL because there is no delivery channel — REQ-CAP-092 names Web Push and Web Push is not
built. A row here means "this question is due to be asked", never "Joe was asked". Those are
different facts and the table has two columns precisely so they cannot be merged.

**The rules it applies, and where each comes from.**

* RULE-27, dismissal: a subject Joe has ever declined is **never asked again**. Not after a
  cooldown, not in a different wording. The rule says never repeat a dismissed prompt, and a
  cooldown is a repeat with a delay.
* RULE-27, cadence: one prompt per subject per day, maximum.
* Duplicate suppression: a subject with an open (`pending`, `delivered_unseen`, `partial`)
  dispatch is not asked again while that dispatch is open. Asking twice about one unanswered
  question is the same failure as asking twice about an answered one, and is likelier.
* An `answered` subject is not re-asked: the question is settled.
* A daily ceiling, reusing `MAX_SCHEDULED_PROMPTS_PER_DAY` from
  `tools/engines/vision_and_prompts.py` rather than declaring a second number. There is one
  prompt budget, not one per feature — B16's meal prompts and these draw on the same attention.

**The subject key is the QUESTION, not the row.** `clarify:<event_family>:<subject_day>`. A
reconstruction that is superseded by a better one (REQ-REC-011 makes revision append-only) is a
new `event_id` for the same open question, and keying on `event_id` would let a re-run ask Joe
about Tuesday's meal again every time the engine changed its mind — which is precisely the nag
RULE-27 forbids, arriving through a technicality.

**`--at` is Joe's, and this command will not guess it.** REQ-CAP-087 forbids a randomly chosen
time and RULE-27 records that scheduled morning prompts achieve 81% compliance against 52% for
random pings, so the time matters and it is a preference, not a derivation. Without `--at` the
command plans and prints and writes nothing. Recommendation: `--at 09:00`.
"""
import argparse
import datetime as dt
import json
import sys

from lib import db
from tools.engines.vision_and_prompts import (MAX_SCHEDULED_PROMPTS_PER_DAY, check_channel,
                                              check_prompt_timing)
from tools.importers.common import redact

CODE_VERSION = "clarification-prompts-v1"
JOB_NAME = "clarification_prompts"

# RULE-27's dismissal rule, as the set of states that close a subject forever / for now.
DISMISSED = ("seen_declined",)
SETTLED = ("answered",)
OPEN = ("pending", "delivered_unseen", "partial")
# 'expired' is none of the above: the question was asked, went unseen past its window, and may
# be asked again on a later day — but not today, which the per-day rule already covers.


# --------------------------------------------------------------------------- reading

def open_questions(cur, core="core"):
    """Current reconstructions that have alternatives AND something that would settle them.

    `no_discriminating_evidence` rows are excluded deliberately: 0069 makes "nothing identified
    would settle this" an explicit, stored answer, and there is no question to ask Joe when the
    system has already concluded that no observation distinguishes the alternatives. Asking
    anyway would be asking him to do the engine's work.

    Superseded rows are excluded: a reconstruction that has been revised is not the current
    interpretation, and the current one carries its own discriminating evidence.
    """
    cur.execute(
        f"""select e.event_id, e.event_family, e.subject_day, e.discriminating_evidence,
                   jsonb_array_length(e.alternatives), e.knowledge_time
              from {core}.inferred_events e
             where not exists (select 1 from {core}.inferred_events s
                                where s.supersedes = e.event_id)
               and jsonb_array_length(e.alternatives) > 0
               and not e.no_discriminating_evidence
               and cardinality(e.discriminating_evidence) > 0
               and e.presence <> 'did_not_occur'
             order by e.subject_day, e.event_family""")
    return [{"event_id": str(r[0]), "event_family": r[1], "subject_day": r[2],
             "discriminating_evidence": list(r[3] or ()), "alternatives": int(r[4]),
             "knowledge_time": r[5]}
            for r in cur.fetchall()]


def dispatch_history(cur, core="core", subjects=()):
    """subject -> {states seen, the most recent state, the last day it was scheduled}.

    Every row for the subject is read, not just the latest: `seen_declined` is permanent
    (RULE-27), so a subject declined once and later re-created by some other path must stay
    declined. Reading only the newest row would let a dismissal be overwritten by a retry.
    """
    history = {}
    if not subjects:
        return history
    # The local DATE is computed in SQL, in the one zone every subject-day rule already uses
    # (ADR-0019). Converting a timestamptz to a date in Python would use whichever zone the
    # machine running this happens to be in, so "was this asked today" would mean something
    # different on a GitHub runner than on the Mac.
    cur.execute(
        f"""select subject, response_state,
                   (scheduled_for at time zone 'America/New_York')::date
              from {core}.prompt_dispatch
             where subject = any(%s)
             order by scheduled_for""", (list(subjects),))
    for subject, state, scheduled_day in cur.fetchall():
        h = history.setdefault(subject, {"states": set(), "last_state": None,
                                         "last_scheduled_day": None})
        h["states"].add(state)
        h["last_state"] = state
        h["last_scheduled_day"] = scheduled_day
    return history


def issued_on(cur, day, core="core"):
    """How many prompts are already scheduled for `day`, across every subject."""
    cur.execute(
        f"""select count(*) from {core}.prompt_dispatch
             where (scheduled_for at time zone 'America/New_York')::date = %s""", (day,))
    return int(cur.fetchone()[0])


# --------------------------------------------------------------------------- deciding

def subject_for(question):
    """The stable key for the QUESTION. See the module docstring for why not the event_id."""
    return f"clarify:{question['event_family']}:{question['subject_day'].isoformat()}"


def decide(questions, history, today, issued_today=0,
           max_per_day=MAX_SCHEDULED_PROMPTS_PER_DAY):
    """(to_schedule, suppressed). Pure: no database, no clock, no side effects.

    Ordering when the budget bites is oldest subject day first. The oldest unresolved question
    is the one whose answer is decaying fastest — Joe's memory of an ordinary Tuesday is the
    perishable evidence here, and a question asked six weeks late is a question asked of a
    person who no longer knows. Ranking by score instead would put the engine's confidence
    ahead of the only input that expires.
    """
    to_schedule, suppressed = [], []
    budget = max(0, max_per_day - issued_today)
    seen_this_run = set()

    for q in sorted(questions, key=lambda q: (q["subject_day"], q["event_family"])):
        subject = subject_for(q)
        row = dict(q, subject=subject)
        h = history.get(subject) or {}
        states = h.get("states") or set()
        last_day = h.get("last_scheduled_day")

        if states & set(DISMISSED):
            suppressed.append(dict(row, reason="dismissed",
                                   note="RULE-27: a dismissed prompt is never repeated"))
        elif states & set(SETTLED):
            suppressed.append(dict(row, reason="answered",
                                   note="the question has been answered"))
        elif h.get("last_state") in OPEN:
            suppressed.append(dict(row, reason="already_open",
                                   note=f"an unanswered prompt for this subject is "
                                        f"{h['last_state']}"))
        elif last_day == today or subject in seen_this_run:
            suppressed.append(dict(row, reason="already_today",
                                   note="RULE-27: one prompt per subject per day"))
        elif budget <= 0:
            suppressed.append(dict(row, reason="daily_budget",
                                   note=f"the day's prompt budget of {max_per_day} is spent; "
                                        f"this question keeps its place for tomorrow"))
        else:
            to_schedule.append(row)
            seen_this_run.add(subject)
            budget -= 1

    return to_schedule, suppressed


# --------------------------------------------------------------------------- writing

def next_occurrence(cur, at):
    """The next time-of-day `at` that is in the future, as a timestamptz.

    Computed in the database so the prompt's clock is the same clock as every stored row's,
    and in `America/New_York` because that is the zone every subject-day rule in this system
    already uses (ADR-0019). Never in the past: a prompt scheduled behind the current instant
    is one the dispatcher would treat as already missed.
    """
    cur.execute(
        """select case
             when ((current_date + %s::time) at time zone 'America/New_York') > now()
             then  ((current_date + %s::time) at time zone 'America/New_York')
             else  ((current_date + 1 + %s::time) at time zone 'America/New_York') end""",
        (at, at, at))
    return cur.fetchone()[0]


def schedule_prompts(cur, rows, scheduled_for, core="core"):
    """Insert one `pending` dispatch per decided question. `delivered_at` stays NULL."""
    written = []
    for row in rows:
        cur.execute(
            f"""insert into {core}.prompt_dispatch (subject, scheduled_for, response_state)
                values (%s, %s, 'pending') returning dispatch_id""",
            (row["subject"], scheduled_for))
        written.append(str(cur.fetchone()[0]))
    return written


def log_run(cur, planned, suppressed, committed, ops="ops"):
    """One runs row, counts only. A prompt subject carries an event family and a date, which
    are schema vocabulary and a calendar day — no evidence text and no reconstruction content
    reaches this row."""
    cur.execute(
        f"""insert into {ops}.runs (job_name, finished_at, status, rows_written, detail)
            values (%s, now(), 'ok', %s, %s)""",
        (JOB_NAME, len(planned) if committed else 0,
         json.dumps({"code_version": CODE_VERSION, "committed": bool(committed),
                     "planned": len(planned), "suppressed": len(suppressed),
                     "suppressed_by_reason": _by_reason(suppressed),
                     "delivered": 0,
                     "note": "scheduled only; there is no delivery channel (REQ-CAP-092)"})))


def _by_reason(suppressed):
    out = {}
    for row in suppressed:
        out[row["reason"]] = out.get(row["reason"], 0) + 1
    return out


# --------------------------------------------------------------------------- cli

def render(planned, suppressed, scheduled_for, committed):
    out = [f"clarification prompts: {len(planned)} to schedule, {len(suppressed)} suppressed "
           f"({'COMMITTED' if committed else 'PLAN ONLY — nothing was written'})"]
    if scheduled_for:
        out.append(f"  scheduled_for: {scheduled_for}")
    for row in planned:
        out.append(f"  ASK  {row['subject']}  "
                   f"{row['alternatives']} alternatives, "
                   f"{len(row['discriminating_evidence'])} discriminating observation(s)")
    if suppressed:
        out.append("")
        out.append("SUPPRESSED:")
        for row in suppressed:
            out.append(f"  {row['reason']:14} {row['subject']}  — {row['note']}")
    out.append("")
    out.append("  A row here means the question is DUE to be asked. It does not mean Joe was")
    out.append("  asked: delivered_at stays NULL because no delivery channel exists yet")
    out.append("  (REQ-CAP-092 names Web Push). The two are separate columns for that reason.")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--at", help="local time of day to schedule for, HH:MM. Joe's decision; "
                                 "required for --commit. Recommended: 09:00")
    ap.add_argument("--commit", action="store_true",
                    help="write the dispatch rows. Without it nothing is written.")
    ap.add_argument("--json", action="store_true", help="machine-readable plan on stdout")
    ap.add_argument("--core", default="core")
    ap.add_argument("--ops", default="ops")
    ap.add_argument("--max-per-day", type=int, default=MAX_SCHEDULED_PROMPTS_PER_DAY)
    a = ap.parse_args(argv)

    if a.commit and not a.at:
        print("clarification_prompts: --commit needs --at HH:MM. The time a prompt arrives is "
              "Joe's decision, not this command's: REQ-CAP-087 forbids a randomly chosen time "
              "and RULE-27 records that a scheduled morning prompt is acted on far more often "
              "than an unscheduled one. Recommended: --at 09:00.", file=sys.stderr)
        return 2
    if a.at:
        try:
            dt.time.fromisoformat(a.at)
        except ValueError:
            print(f"clarification_prompts: --at must be HH:MM, got {a.at!r}", file=sys.stderr)
            return 2
        # REQ-CAP-087/092, asserted against the same policy the meal prompts obey rather than
        # restated here: the time is chosen, not jittered, and the channel is not SMS or email.
        check_prompt_timing({"random": False})
        check_channel("web_push")

    try:
        conn = db.connect()
    except Exception as e:
        print(f"{JOB_NAME}: DATABASE UNREACHABLE: {type(e).__name__}", file=sys.stderr)
        return 2

    try:
        cur = conn.cursor()
        cur.execute("select (now() at time zone 'America/New_York')::date")
        today = cur.fetchone()[0]
        questions = open_questions(cur, a.core)
        history = dispatch_history(cur, a.core, [subject_for(q) for q in questions])
        planned, suppressed = decide(questions, history, today, issued_on(cur, today, a.core),
                                     a.max_per_day)
        scheduled_for = next_occurrence(cur, a.at) if (a.at and planned) else None
        if a.commit and planned:
            schedule_prompts(cur, planned, scheduled_for, a.core)
        log_run(cur, planned, suppressed, a.commit, a.ops)
        if a.commit:
            conn.commit()
        else:
            conn.rollback()
    except Exception as e:
        conn.rollback()
        print(f"{JOB_NAME}: FAILED: {type(e).__name__}: {redact(e)}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    if a.json:
        print(json.dumps({"code_version": CODE_VERSION, "committed": bool(a.commit),
                          "scheduled_for": str(scheduled_for) if scheduled_for else None,
                          "planned": [{k: str(v) for k, v in r.items()} for r in planned],
                          "suppressed_by_reason": _by_reason(suppressed)}, indent=2))
    else:
        print(render(planned, suppressed, scheduled_for, a.commit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
