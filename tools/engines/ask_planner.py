"""The language layer: free text in, a REGISTERED PLAN out (B11.2, REQ-ASK-007/008/012; ADR-0064).

The deterministic grammar in `public.ask` answers the questions it recognises and always
works (RULE-15). This module exists for the ones it does not recognise, and its job is
deliberately small: **choose among options that already exist**. It never executes anything,
never sees a number, and never narrates.

What the model may choose
-------------------------
An operation from `config.operations`, a metric from `core.metric_registry`, a condition
metric, and a range **the question itself stated**. Nothing else.

What it may not choose, and why
-------------------------------
RULE-13: "Lag structures, window definitions, aggregation choices, and adjustment sets are
fixed data, never model output at query time." So a question that states no range does not get
one from the model — it gets `config`'s default. The distinction is between *extraction* ("the
user said last 90 days") and *selection* ("the user said recently, I'll use 90 days"); the
first is reading, the second is choosing a window definition, and HEARTS (ICML 2026) found
code execution fixes arithmetic but not temporal reasoning, with models falling back on
heuristics as temporal complexity rises. That is the failure this rule anticipates.

RULE-11 / REQ-ASK-012: the model performs no arithmetic and contributes no numeral. The plan
it returns is executed by the deterministic path, and narration stays on the template path —
so the only numbers that can reach an answer are ones the executor computed and stored.

REQ-ASK-004/031: an operation outside the registry is refused with the stored string and the
nearest registered options, and **no code from the model is ever executed**. The plan is data
that is validated field by field; it is not a program.
"""
import json
import re

CODE_VERSION = "ask-planner-v1"
MAX_ITERATIONS = 5                     # REQ-ASK-008
MODEL_ID = "@cf/meta/llama-3.1-8b-instruct"
# A planning call is small. The figure is an estimate and is recorded as one: the ledger is
# what will let it be replaced by an observed number (ADR-0063).
ESTIMATED_NEURONS_PER_PLAN = 15.0


class PlanRefused(Exception):
    """The plan cannot be mapped onto the registry. Carries the disclosure REQ-ASK-031 wants."""

    def __init__(self, reason, nearest=None):
        self.reason, self.nearest = reason, nearest or []
        super().__init__(reason)


def registry_options(cur, schema="core", config="config"):
    """The closed sets the plan is validated against, read from the database.

    Read rather than hardcoded: the registry is the authority for what exists, and a list
    copied into this file would be a second one that drifts.
    """
    cur.execute(f"select op, arity, tier_ceiling from {config}.operations order by op")
    operations = {r[0]: {"arity": r[1], "tier_ceiling": r[2]} for r in cur.fetchall()}
    cur.execute(f"select metric_key, display_name from {schema}.metric_registry order by metric_key")
    metrics = {r[0]: r[1] for r in cur.fetchall()}
    return operations, metrics


def plan_schema(operations, metrics):
    """The JSON schema the model must answer in — built from the registry, not written here."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["op"],
        "properties": {
            "op": {"type": "string", "enum": sorted(operations)},
            "metric": {"type": "string", "enum": sorted(metrics)},
            "condition_metric": {"type": "string", "enum": sorted(metrics)},
            "condition": {"type": "string"},
            # A range is echoed back only when the question stated one. There is no enum of
            # window lengths here on purpose: offering the model a menu of windows would be
            # inviting it to choose one (RULE-13).
            "range_phrase": {"type": "string"},
            "entity": {"type": "string"},
        },
    }


# Range phrases the deterministic parser already understands. The planner may only echo a
# phrase the QUESTION contains — matched against the question text, not generated.
_RANGE_PATTERNS = (
    r"today", r"yesterday", r"this (?:week|month|year)", r"last (?:week|month|year)",
    r"last \d+ days?", r"since [a-z]+(?: \d{4})?", r"in \d{4}",
)


def stated_range(question):
    """The range phrase the QUESTION contains, or None.

    RULE-13's line: extracting a window the user stated is reading; supplying one they did not
    is choosing a window definition. A question with no range gets the executor's registered
    default, never the model's preference.
    """
    low = question.lower()
    for pattern in _RANGE_PATTERNS:
        m = re.search(pattern, low)
        if m:
            return m.group(0)
    return None


def validate(plan, question, operations, metrics):
    """Validate the model's plan against the registry. Returns a clean plan or raises.

    Every field is checked against a closed set read from the database. Nothing is coerced,
    nothing is guessed, and a field the model invented is a refusal rather than a silently
    dropped key — an invented field means the model answered a different question.
    """
    if not isinstance(plan, dict):
        raise PlanRefused("plan_not_an_object")

    unknown = set(plan) - {"op", "metric", "condition_metric", "condition", "range_phrase", "entity"}
    if unknown:
        raise PlanRefused(f"plan_has_unknown_fields:{','.join(sorted(unknown))}")

    op = plan.get("op")
    if op not in operations:
        # REQ-ASK-004/031: outside the registry, refused with the nearest registered options.
        import difflib
        nearest = difflib.get_close_matches(str(op or ""), sorted(operations), n=3, cutoff=0.0)
        raise PlanRefused("operation_not_registered", nearest)

    clean = {"op": op}
    for field in ("metric", "condition_metric"):
        value = plan.get(field)
        if value is not None:
            if value not in metrics:
                import difflib
                nearest = difflib.get_close_matches(str(value), sorted(metrics), n=3, cutoff=0.0)
                raise PlanRefused(f"{field}_not_registered", nearest)
            clean[field] = value

    # RULE-13. A range the question did not state is not the model's to supply.
    stated = stated_range(question)
    proposed = plan.get("range_phrase")
    if proposed is not None:
        if stated is None or proposed.lower().strip() not in question.lower():
            raise PlanRefused("range_not_stated_in_question")
        clean["range_phrase"] = proposed.lower().strip()
    elif stated is not None:
        clean["range_phrase"] = stated

    for field in ("condition", "entity"):
        if plan.get(field) is not None:
            clean[field] = str(plan[field])[:200]
    return clean


def to_question(plan, metrics):
    """Render a validated plan back into the canonical phrasing the deterministic executor
    already parses.

    The plan is never executed as code and never becomes SQL. It selects among questions the
    executor can already answer, so the model's whole influence is which registered question
    gets asked — which is what keeps RULE-11 and REQ-ASK-012 true by construction rather than
    by inspection.
    """
    op, display = plan["op"], metrics.get(plan.get("metric", ""), "")
    rng = f" {plan['range_phrase']}" if "range_phrase" in plan else ""
    if op == "describe":
        return f"how is my {display}{rng}"
    if op == "trend":
        return f"has my {display} changed{rng}"
    if op == "rhythm":
        return f"which weekday is my {display}{rng}"
    if op == "last":
        return f"when did i last log my {display}"
    if op == "count_days":
        return f"how many days my {display} {plan.get('condition', 'above the usual range')}{rng}"
    if op == "compare":
        cond = metrics.get(plan.get("condition_metric", ""), "")
        return (f"my {display} on days when my {cond} "
                f"{plan.get('condition', 'is above the usual range')}{rng}")
    if op in ("effect", "contrast"):
        other = metrics.get(plan.get("condition_metric", ""), "")
        return f"does my {display} affect my {other}{rng}"
    if op == "spend":
        return f"how much did i spend at {plan.get('entity', '')}{rng}"
    if op == "entity":
        return plan.get("entity", "")
    return plan.get("entity") or display


def build_prompt(question, operations, metrics):
    """The prompt. It carries the registry and the question, and nothing else.

    No coordinate, no mood value, no other lens's data — the same restriction REQ-FIN-092
    places on the categorizer's prompt, for the same reason.
    """
    return {
        "messages": [
            {"role": "system", "content":
                "Map the question to ONE registered operation and its metrics. "
                "Reply with JSON matching the schema and nothing else. "
                "Do not compute anything. Do not invent a metric or an operation. "
                "Only include range_phrase if the question itself states a time range."},
            {"role": "user", "content": json.dumps({
                "question": question,
                "operations": {k: v["arity"] for k, v in operations.items()},
                "metrics": metrics,
            })},
        ],
        "response_format": {"type": "json_schema",
                            "json_schema": plan_schema(operations, metrics)},
    }


def plan_question(cur, question, *, schema="core", ops="ops", config="config",
                  transport=None, max_iterations=MAX_ITERATIONS):
    """Ask the model for a plan, validate it, and return (plan, canonical_question, attempts).

    Raises PlanRefused when no attempt produces a registered plan within the iteration cap
    (REQ-ASK-008), and lets `BudgetExceeded` propagate so the caller degrades deterministically
    (RULE-15). The caller owns the transaction.
    """
    from lib import egress
    operations, metrics = registry_options(cur, schema, config)
    prompt = build_prompt(question, operations, metrics)
    last = None

    for attempt in range(1, max_iterations + 1):
        raw = egress.call(cur, model_id=MODEL_ID, call_kind="plan", payload=prompt,
                          estimated_neurons=ESTIMATED_NEURONS_PER_PLAN,
                          purpose="ask_plan", schema=schema, ops=ops, _transport=transport)
        try:
            candidate = _extract_plan(raw)
            clean = validate(candidate, question, operations, metrics)
            return clean, to_question(clean, metrics), attempt
        except PlanRefused as e:
            last = e
            # The next attempt is told what was wrong. It is still bounded by the cap, and the
            # cap is a refusal rather than a best guess (REQ-ASK-008).
            prompt = dict(prompt)
            prompt["messages"] = prompt["messages"] + [
                {"role": "user", "content": f"That plan was rejected: {e.reason}. "
                                            "Reply with a plan using only the listed values."}]
    raise PlanRefused(f"iteration_cap_reached:{last.reason if last else 'no_plan'}",
                      last.nearest if last else [])


def _extract_plan(raw):
    """The plan out of a Workers AI response envelope, without trusting its shape."""
    if isinstance(raw, dict):
        inner = raw.get("result", raw)
        if isinstance(inner, dict):
            body = inner.get("response", inner)
            if isinstance(body, str):
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    raise PlanRefused("plan_not_json")
            return body
    raise PlanRefused("plan_not_json")
