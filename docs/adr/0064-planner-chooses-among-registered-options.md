# ADR-0064: The planner chooses among registered options; it never selects a specification

## Status
Accepted. Builds `tools/engines/ask_planner.py` and `tools/ask.py` (B11.2, REQ-ASK-004/007/
008/012/031). Depends on ADR-0063's shared egress and budget.

## Date
2026-09-09

## The line this draws

RULE-13's INTEGRITY core: *"Lag structures, window definitions, aggregation choices, and
adjustment sets are fixed data, never model output at query time."* B11.2 asks for a language
layer that turns free text into a query plan. Those are only compatible if the plan is a
**selection among things that already exist**, never a specification the model composes.

So the planner may choose: an operation from `config.operations`, metrics from
`core.metric_registry`, and a range **the question itself contains**. It may not choose a
window. A question that states no range gets the executor's registered default, not the
model's preference.

The distinction is between *extraction* — "the user said last 90 days" — and *selection* —
"the user said recently, so I will use 90 days". The first is reading. The second is choosing
a window definition, and it is invisible in the answer. HEARTS (ICML 2026, arXiv:2603.06638)
found code execution fixes arithmetic but **not** temporal reasoning, with models falling back
on heuristics as temporal complexity rises; that is precisely the failure RULE-13 anticipates,
and "recently" is exactly the input that triggers it.

## How the boundary is kept

- **The plan is validated field by field against closed sets read from the database.** A field
  the model invented is a refusal, not a silently dropped key — an invented field means it
  answered a different question, and `{"multiply_by": 2}` dropped quietly is arithmetic absent
  from the record of what was asked.
- **A validated plan is rendered back into a canonical question the deterministic executor
  already parses.** Nothing from the model becomes SQL or is executed (REQ-ASK-031). The
  model's entire influence is *which registered question gets asked*, which keeps RULE-11 and
  REQ-ASK-012 true by construction rather than by inspection.
- **Narration stays on the template path.** The only numerals that can reach an answer are ones
  the executor computed and stored.
- **The prompt carries the question and the registry, and nothing else** — the same restriction
  REQ-FIN-092 places on the categorizer's prompt, for the same reason.

## The fallback order, which is the point

1. The deterministic executor answers the question as asked. Most questions end here and cost
   nothing.
2. Only a question the **grammar** missed reaches the planner. A refusal for an untracked
   metric or thin coverage is a TRUE answer about the record — handing it to a model would turn
   an honest refusal into a different question that happens to have data, which is the most
   useful-looking way to be wrong.
3. Over budget, unreachable, or no registered plan within REQ-ASK-008's cap of five: the
   original deterministic refusal stands, annotated with why the planner did not help.

**The planner path is never worse than not having a planner** (RULE-15). Every answer records
which path produced it; a reader who cannot tell whether a model was involved cannot judge it.

## What is not done

- **No call has been made.** Every test injects an explicit `transport` — a parameter, not a
  monkeypatch, so what is substituted is visible in the signature. Nothing proves Workers AI
  accepts this request shape, no credential has been exercised, and no worker is deployed.
- **The neuron cost per plan is an estimate** (ADR-0063), uncalibrated until a real call.
- **Iteration re-prompting is untested against a real model.** The loop is bounded and its
  refusal is proven; whether telling a model why its plan was rejected actually improves the
  next one is unknown and is not claimed.
