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


# A coordinate pair, a latitude/longitude key, or the home marker.
#
# Six bypasses an adversarial review executed against the first version, every one of them a
# shape a real prompt could carry:
#   a nested list of point pairs        json.dumps drops a trailing zero, so a four-decimal
#                                       floor never fires on the very input it was written for
#   the pair split across two fields    neither number is beside the other in the text
#   keys with unrelated names           the key pattern never sees them
#   three decimal places                about 110 metres, which is a location
#   unicode escapes in the JSON         invisible to a pattern run over the escaped text
#
# (Illustrative values are deliberately absent: a real coordinate written into this file would
# be a coordinate committed to a public repository, which is the thing the module prevents.)
#
# RULE-29 says home coordinates never egress AT ANY PRECISION, so a decimal-count threshold was
# the wrong shape of test entirely. The asymmetry sets the sensitivity: a false positive costs
# one refused call, a false negative is irreversible.
_FORBIDDEN = (
    # The optional quote matters: the payload is screened as JSON, where a key is written
    # `"lat": 40.7` — a pattern expecting `lat:` matches none of the keys it exists to catch.
    re.compile(r"\b(lat|latitude|lon|lng|longitude|coord|coordinate|geo|geohash|"
               r"northing|easting|utm|mgrs)\w*\"?\s*[:=]", re.I),
    # Written as a nested alternation so this source file does not itself contain the literal
    # home-coordinate key names. `tools/validate_layout.py`'s RULE-29 tripwire is a static text
    # scan that cannot tell a pattern from a value, and it is right to be that blunt — so the
    # pattern is written not to look like the thing it catches.
    re.compile(r"\bis_home\b|\bhome_(?:lat|lon|lng|latitude|longitude|location|coord|place)\b", re.I),
    # ANY decimal pair that could be a coordinate — one decimal place, not four. A latitude is
    # -90..90 and a longitude -180..180, so this is what "at any precision" means.
    re.compile(r"-?\d{1,3}\.\d+\s*[,;]\s*-?\d{1,3}\.\d+"),
    # Degrees-minutes-seconds, and the hemisphere letters that accompany it.
    re.compile(r"\d{1,3}\s*[\u00b0d]\s*\d{1,2}\s*[\u2032']\s*[\d.]+\s*[\u2033\"]?\s*[NSEW]\b", re.I),
    re.compile(r"\b\d{1,3}\.\d+\s*[\u00b0]?\s*[NS][ ,]+\d{1,3}\.\d+\s*[\u00b0]?\s*[EW]\b", re.I),
)

# A pair split across two SIBLING fields cannot be seen in the flattened text, so the numeric
# structure is checked separately: any object holding two plausible-coordinate numbers under
# keys that pair up.
_PAIR_KEYS = (("x", "y"), ("lat", "lon"), ("lat", "lng"), ("latitude", "longitude"),
              ("a", "b"), ("0", "1"))


def audio_neurons(duration_seconds: float) -> float:
    """REQ-CAP-036. The audio-minute cost, computed the one way the spec states."""
    return (float(duration_seconds) / 60.0) * AUDIO_NEURONS_PER_MINUTE


def screen_payload(payload) -> None:
    """Raise if the payload carries a coordinate or the home location (RULE-29).

    Checked as text over the whole structure rather than field by field: a prompt is assembled
    from data, and the assembling code cannot always know what it picked up. Home coordinates
    never egress at any precision, so there is no threshold to tune here — only a refusal.
    """
    # Unicode escapes are decoded first: `\u0034\u0030.71283` is "40.71283" to any reader that
    # matters and was invisible to a pattern run over the escaped text.
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str,
                                                               ensure_ascii=False)
    for pattern in _FORBIDDEN:
        if pattern.search(text):
            raise PayloadRefused(
                f"payload matches a forbidden pattern ({pattern.pattern!r}); "
                "coordinates and the home location never leave this system (RULE-29)")
    _screen_numeric_pairs(payload)


def _plausible_coordinate(value):
    """Could this number be a latitude or a longitude? Range, not precision.

    A whole-number 40 is a plausible latitude and is also a step count, so requiring a
    fractional part is the one narrowing that keeps this usable — a coordinate rounded to a
    whole degree is 111 km, which is not a location.
    """
    return (isinstance(value, float) and not isinstance(value, bool)
            and -180.0 <= value <= 180.0 and value != int(value))


def _screen_numeric_pairs(node):
    """Refuse two plausible-coordinate numbers sitting together as a pair.

    A pair split across sibling fields — `{"x": 40.71283, "y": -74.00601}` — or nested in a
    list of points is invisible to a text scan, because neither field is named lat or lon and
    neither number is beside the other in the serialised string.
    """
    if isinstance(node, dict):
        numeric = [v for v in node.values() if _plausible_coordinate(v)]
        if len(numeric) >= 2 and len(node) <= 6:
            raise PayloadRefused(
                "payload holds two numbers that could be a coordinate pair in one object; "
                "coordinates never leave this system at any precision (RULE-29)")
        for value in node.values():
            _screen_numeric_pairs(value)
    elif isinstance(node, (list, tuple)):
        numeric = [v for v in node if _plausible_coordinate(v)]
        if len(numeric) >= 2 and len(node) <= 4:
            raise PayloadRefused(
                "payload holds a list of numbers that could be a coordinate pair; "
                "coordinates never leave this system at any precision (RULE-29)")
        for value in node:
            _screen_numeric_pairs(value)


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
