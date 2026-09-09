"""The one place personal data leaves this system (RULE-29, REQ-CAP-035..042; ADR-0063).

Every outbound model call goes through `call()`. Nothing else in the repository opens a
socket to a model provider, and `tools/validate_layout.py` enforces that: a network-capable
import outside this module and `lib/db.py` fails the build.

Three things happen on every call, in this order, and the order is the point:

1. **The budget is checked against the shared ledger.** Three consumers will call Workers AI
   — Ask's planner (B11.2), nutrition resolution (B12) and media transcription (B16) — and
   each would naturally count its own usage. Three counters against one 10,000-neuron daily
   allowance means none of them knows the real total. `core.neuron_budget()` is one gate over
   one sum.
2. **A ledger row and an `ops.egress_log` row are written BEFORE the request is issued.**
   Writing them afterwards means a call that hangs, crashes the process, or returns an error
   leaves no trace — and those are exactly the calls worth having a trace of. RULE-29 requires
   a log row for every outbound call, not for every *successful* one.
3. **The payload is screened for anything that must never leave.** A coordinate or the home
   location reaching a prompt is the failure RULE-29 exists to prevent, and a prompt is
   assembled from data by code that cannot always know what it picked up.

Over budget is a **refusal**, never a smaller call and never a retry: RULE-28 disqualifies a
service that bills on overage, and REQ-CAP-042 makes Workers AI's own hard fail at 10,000
neurons/day the enforcement mechanism for $0-recurring. Degrading to the deterministic path is
the caller's job (RULE-15 — nothing may require the model to be available).
"""
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request

# Cloudflare Workers AI, the only model destination this system is permitted (RULE-29).
WORKERS_AI_HOST = "api.cloudflare.com"
AUDIO_NEURONS_PER_MINUTE = 46.63          # REQ-CAP-036
SOFT_CEILING = 9000                        # REQ-CAP-037
HARD_CAP = 10000                           # REQ-CAP-039 / REQ-CAP-042
TIMEOUT_SECONDS = 60


class BudgetExceeded(Exception):
    """The daily neuron budget would be exceeded. The caller degrades deterministically."""

    def __init__(self, spent, ceiling, reason):
        self.spent, self.ceiling, self.reason = spent, ceiling, reason
        super().__init__(f"{reason}: {spent} of {ceiling} neurons spent today")


class PayloadRefused(Exception):
    """The payload carries something that must never leave this system (RULE-29)."""


# A coordinate pair, a latitude/longitude key, or the home marker. Deliberately broad: a false
# positive costs one refused call, a false negative is an irreversible disclosure.
_FORBIDDEN = (
    # The optional quote matters: the payload is screened as JSON, where a key is written
    # `"lat": 40.7` — a pattern expecting `lat:` matches none of the keys it exists to catch.
    re.compile(r"\b(lat|latitude|lon|lng|longitude)\b\"?\s*[:=]", re.I),
    re.compile(r"\bis_home\b|\bhome_lat\b|\bhome_lon\b|\bhome_location\b", re.I),
    re.compile(r"-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}"),   # a bare coordinate pair
)


def audio_neurons(duration_seconds: float) -> float:
    """REQ-CAP-036. The audio-minute cost, computed the one way the spec states."""
    return (float(duration_seconds) / 60.0) * AUDIO_NEURONS_PER_MINUTE


def screen_payload(payload) -> None:
    """Raise if the payload carries a coordinate or the home location (RULE-29).

    Checked as text over the whole structure rather than field by field: a prompt is assembled
    from data, and the assembling code cannot always know what it picked up. Home coordinates
    never egress at any precision, so there is no threshold to tune here — only a refusal.
    """
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    for pattern in _FORBIDDEN:
        if pattern.search(text):
            raise PayloadRefused(
                f"payload matches a forbidden pattern ({pattern.pattern!r}); "
                "coordinates and the home location never leave this system (RULE-29)")


def check_budget(cur, estimated_neurons, deferred_retry=False, schema="core"):
    """The shared gate. Returns (spent_today, ceiling); raises BudgetExceeded."""
    cur.execute(f"select * from {schema}.neuron_budget(%s, %s)",
                (estimated_neurons, deferred_retry))
    spent, ceiling, allowed, reason = cur.fetchone()
    if not allowed:
        raise BudgetExceeded(float(spent), float(ceiling), reason)
    return float(spent), float(ceiling)


def _log(cur, *, destination, purpose, model_id, call_kind, estimated_neurons,
         capture_id, deferred_retry, request_bytes, schema="core", ops="ops"):
    """Write the egress row and the ledger row BEFORE the request. Returns their ids."""
    cur.execute(
        f"""insert into {ops}.egress_log (destination, purpose, request_bytes, detail)
            values (%s, %s, %s, %s) returning egress_id""",
        (destination, purpose, request_bytes,
         json.dumps({"model_id": model_id, "call_kind": call_kind,
                     "estimated_neurons": float(estimated_neurons)})))
    egress_id = cur.fetchone()[0]
    cur.execute(
        f"""insert into {schema}.neuron_ledger
              (capture_id, model_id, call_kind, estimated_neurons, is_deferred_retry,
               outcome, egress_id)
            values (%s, %s, %s, %s, %s, 'issued', %s) returning ledger_id""",
        (capture_id, model_id, call_kind, estimated_neurons, deferred_retry, egress_id))
    return egress_id, cur.fetchone()[0]


def _settle(cur, ledger_id, egress_id, outcome, response_bytes=None, detail=None,
            schema="core", ops="ops"):
    """Record what the call actually did. An errored call still spent its neurons."""
    cur.execute(f"update {schema}.neuron_ledger set outcome = %s, detail = %s where ledger_id = %s",
                (outcome, json.dumps(detail) if detail else None, ledger_id))
    if response_bytes is not None:
        cur.execute(f"update {ops}.egress_log set response_bytes = %s where egress_id = %s",
                    (response_bytes, egress_id))


def call(cur, *, model_id, call_kind, payload, estimated_neurons,
         capture_id=None, deferred_retry=False, purpose=None,
         schema="core", ops="ops", _transport=None):
    """Issue one Workers AI call, budgeted, screened and logged. Returns the parsed response.

    The caller owns the transaction. `_transport` exists so a test can prove the budget,
    screening and logging behaviour without reaching the network — the seam is explicit rather
    than a monkeypatch, so what is substituted is visible in the signature.
    """
    screen_payload(payload)                                   # RULE-29, before anything else
    spent, ceiling = check_budget(cur, estimated_neurons, deferred_retry, schema)

    body = json.dumps(payload).encode()
    egress_id, ledger_id = _log(
        cur, destination=WORKERS_AI_HOST, purpose=purpose or call_kind, model_id=model_id,
        call_kind=call_kind, estimated_neurons=estimated_neurons, capture_id=capture_id,
        deferred_retry=deferred_retry, request_bytes=len(body), schema=schema, ops=ops)

    try:
        raw = (_transport or _post)(model_id, body)
    except Exception as e:
        # No retry. A retry doubles the spend against a budget whose whole purpose is to make
        # the ceiling reachable exactly once, and REQ-CAP-043 says a failed call must not lose
        # its capture — the caller defers it, it does not try again here.
        _settle(cur, ledger_id, egress_id, "error",
                detail={"error": type(e).__name__}, schema=schema, ops=ops)
        raise

    _settle(cur, ledger_id, egress_id, "ok", response_bytes=len(raw),
            schema=schema, ops=ops)
    return json.loads(raw.decode())


def _post(model_id, body):
    """The only outbound request in this repository."""
    account = os.environ.get("CF_ACCOUNT_ID")
    token = os.environ.get("CF_API_TOKEN")
    if not account or not token:
        raise RuntimeError("CF_ACCOUNT_ID / CF_API_TOKEN not set")
    url = f"https://{WORKERS_AI_HOST}/client/v4/accounts/{account}/ai/run/{model_id}"
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return resp.read()
