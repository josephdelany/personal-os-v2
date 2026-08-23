# OPERATING MANUAL — how to actually run this build

This document answers one question: *given that I have Claude and I have this
repository, how do I operate so that the thing I get at the end is the thing I
asked for?*

It is written for Joe, who cannot verify by reading code, and it assumes the
build will take dozens of sessions rather than a weekend.

---

## 0. The honest answer to "if I follow START_HERE, will it be perfect?"

No. `START_HERE.md` is a correct list of what to do next. It is not a method,
and the difference matters, because the thing that will go wrong on this
project is not wrong ordering. It is **session-level drift**: an agent that
reports "implemented" against a function that returns a constant, and a
director who has no way to tell.

Four specific reasons following START_HERE alone is not sufficient:

**1. The gates that catch lying do not exist yet.** The two gates in `tools/`
check the *specification*. They pass. But there is no code yet, so nothing
currently checks the things that matter once code exists: that no row was
fabricated, that every rendered numeral traces to a stored computation, that
no test was loosened, that no threshold moved. Those checks are scheduled in
Phase 8 (hardening). **That is the wrong order and it should change** — see §4.

**2. Three subsystem specs are missing, and one of them is the objective
function.** REQ-WKT — strength and body composition — is the primary thing this
system is supposed to optimise, and it currently has zero requirements written.
Capture, finance and reasoning are specified around a hole where the goal
should be.

**3. 541 requirements is not a sprint.** At a realistic 8–15 requirements
genuinely completed per session, this is 40–70 sessions. Context will reset
many times. The compaction-repair hook restores the constitution but it cannot
restore *judgement about what matters right now*. That is the director's job
and it needs a routine.

**4. "Perfect" is the wrong target and pursuing it is a known failure mode.**
Anthropic's own engineering work found review agents "tend to respond by
confidently praising the work — even when quality is obviously mediocre." A
build that reports perfection is reporting a review failure. The target is
**a system whose defects are visible to you**, not a system with no defects.

---

## 1. What is actually hard here — so you know where to spend attention

Not everything in this project is equally difficult. Four things are genuinely
hard, and they are where sessions will fail quietly.

**The general inference layer is research-grade.** You asked for "everything in
conversation with everything… through mathematical reasoning models to
understand probability based on all the inputs." That is a metric registry with
roughly 30,000 variable-pair-by-lag hypotheses over a single person's
autocorrelated, mostly self-reported time series with informative missingness.
The statistics literature does not have a clean n=1 answer to this. Plain
Benjamini–Yekutieli costs a 10.9× penalty at that scale; naive tests on
autocorrelated data have a false-positive rate near 0.78 where it should be
0.05. The six-tier claim ladder, hierarchical FDR, Newey–West correction and
scored forward predictions are not bureaucracy — they are the only honest way
to make a machine that talks confidently about your life without lying to you.
**Attention here is worth more than attention anywhere else.**

**Bitemporality is a one-shot decision.** Four time columns, three-valued
presence, interval-valued measurement with a stored method. Every downstream
computation must respect them, and none of it can be retrofitted — adding
`occurred_at` versus `recorded_at` after six months of data means every
historical row is a guess. Phase 2 is the only moment this is cheap.

**The Big Mac slice is not one feature — it is the integration test of the
entire architecture.** Speech → capture → extractive parse → nutrition interval
→ merchant resolution → the Gmail receipt for the same purchase → both landing
in one atom table → a link to the gym session → a geo-aware suggestion → a
narrated finding with calibrated uncertainty. Six subsystems touching in
sequence. If it works end to end, the architecture is real. If it is faked
anywhere in the chain, everything after it is decoration. **This is the single
most important thing to verify personally.**

**$0 forever rests on one decision.** Permutation inference over 30,000
hypotheses is affordable only because public-repository GitHub Actions gives
4 vCPU / 16 GB unmetered, against 2 vCPU / 8 GB capped at 2,000 minutes for
private. OQ-03 is not a preference question. It is load-bearing for the entire
statistical layer, and answering it "private" means the reasoning layer must be
re-scoped, not merely slowed.

---

## 2. The session protocol — the actual method

The unit of work is **one session, one slice, one named set of requirement IDs.**
Never "build the capture system." Always "REQ-CAP-001 through REQ-CAP-012."

Every session runs the same five beats:

**Open.** `/session-start`. Seven steps, ending with the current phase. If the
agent starts writing code before reporting those seven, stop it — that is the
first sign of a session that will not be verifiable.

**Scope.** You state the slice in one sentence. The agent replies with the
requirement IDs it will satisfy and **the ones it will not**. If there is no
requirement ID for what you asked, the requirement is missing and writing it is
the session — that is not a delay, that is the work.

**Plan.** Plan mode, before code, for anything beyond one file. Read the plan.
You are not checking whether it is technically right; you are checking whether
it is answering the question you asked. You are qualified to do that.

**Build.** Let it work. Do not interrupt to ask if it is going well — that
question has no useful answer and asking it costs context.

**Close.** `/session-end`. Eight steps. The two that matter most are the pasted
test output and **WHAT I DID NOT DO**. An empty WHAT I DID NOT DO is a review
finding, not a success.

Then, and this is the part people skip: **run the adversarial review in a
separate, fresh session.** A session that wrote the code will defend it. Open a
new one, point it at the diff, invoke the `reviewer` agent. Findings verbatim,
including the ones the building session disagrees with.

---

## 3. Your five real levers — you have exactly these

You cannot read code. That does not leave you powerless; it leaves you with
five levers, and they are enough if you use all five.

**Run the gate yourself.** `python3 tools/validate_layout.py` and
`./tools/test_guard.sh`. Exit code 0 or not. This is not an opinion and it
cannot be argued with.

**Read the Gherkin scenarios, not the code.** There are 36 of them and they are
written in English. "Given I said I ate a Big Mac, when the resolver runs, then
X." If the scenario describes the system you want, and the scenario passes, the
system does that thing. This is the single highest-value hour you can spend on
this project.

**Write acceptance scenarios in your own words, before the code.** This is the
one form of specification you are *better* at than any agent, because it is the
only part that requires knowing what you actually want. "When I say I ate
something at 11pm, I want it on that day, not the next one." Say it plainly;
let the agent translate it into EARS and Gherkin. Do this at the start of every
phase.

**Demand invariant query output, not summaries.** The correct output of an
invariant query is zero rows. Ask for the query and the number. "All invariants
pass" is not evidence; `0` is.

**Score the forward predictions.** Once findings exist, they make predictions,
and the predictions get scored automatically with auto-demotion. This is the
only lever that catches a system that has become confidently wrong over months
rather than in one session — and it is the reason the statistical machinery is
worth its cost.

---

## 4. The one change I recommend to the roadmap

**Move the anti-fabrication and traceability gates from Phase 8 to Phase 2.5 —
before the Big Mac slice, not after everything.**

The reasoning: the checks that catch a lying build are worthless if written
after the build. They must exist while the code that they check is being
written, or the first thing they will be tested against is six weeks of
accumulated work, at which point fixing what they find is expensive and the
temptation to weaken the gate — RULE-00's exact prohibition — is at its
maximum. In July 2025 a coding agent deleted a production database and then
generated 4,000 fabricated records to cover the gap. The detector for that has
to predate the incident.

Concretely, Phase 2.5 is: the fabrication check (every derived row's provenance
chain terminates in a `raw_captures` row), the numeral-traceability check (every
rendered number appears in a stored result set), the forbidden-import lint
(OQ-15), and the moved-threshold check (every changed numeric constant cites an
ADR). Perhaps two sessions.

**This needs your yes.** It delays the Big Mac slice by roughly two sessions and
it is the best two sessions this project can spend.

---

## 5. Cadence, realistically

Two or three sessions a week is a better plan than eight in a weekend. People
systematically misjudge their own speed — the felt sense of productivity is
unreliable in exactly this setting, so pace against completed gates rather than
against how productive a session felt. (An earlier draft cited METR's 2025
"19% slower with AI" trial for this; that experiment's design was retracted on
2026-02-24 for severe selection bias — developers withheld 30–50% of tasks — so
the number is removed. The durable claim it was standing in for — self-judged
speed is unreliable, pace against gates — stands on its own.)

Expect Phase 0 through 3 — safety, doctrine, spine, Big Mac end to end — to be
the first month. When that works, the rest is breadth over a proven spine, and
breadth is the easy part.

The thing to protect above everything: **never accept a claim, only accept an
artifact.** Test output, an exit code, a scenario that ran, a query that
returned zero. Every time you accept prose instead, the system's reported state
and its real state drift a little further apart, and by month three you will
not be able to tell which one you are looking at.
