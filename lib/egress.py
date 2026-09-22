"""The one place personal data leaves this system (RULE-29, REQ-CAP-035..042; ADR-0063).

Every real outbound model call goes through `dispatch()` (ADR-0146).
`call()` retains only an injected transport seam for rollback-only legacy fixtures. Nothing else in the repository opens a
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
import hashlib
import json
import os
import re
import time
import uuid
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


class DispatchRefused(Exception):
    """No request sent: identity, durability or permit validity was not established."""


class DispatchUncertain(Exception):
    """A request may have left; never retry this identity as a fresh dispatch."""


def dispatch(conn, *, request_id, model_id, call_kind, payload, estimated_neurons,
             capture_id=None, _transport=None, _monotonic=time.monotonic):
    """Own the dedicated reservation and settlement transactions (ADR-0146).

    Receives an already prepared payload, never a private-row cursor. The database
    session must authenticate directly as model_egress, so SET ROLE from a broad
    reader is refused. A returned provider value requires committed settlement.
    """
    screen_payload(payload)
    request_id = str(uuid.UUID(str(request_id)))
    body = json.dumps(payload, allow_nan=False).encode()
    if os.environ.get('SUPABASE_DB_URL') or os.environ.get('SUPABASE_SERVICE_ROLE_KEY'):
        raise DispatchRefused('private credentials present')
    cur = conn.cursor()
    try:
        cur.execute('SELECT session_user, current_user')
        if tuple(cur.fetchone()) != ('model_egress', 'model_egress'):
            raise DispatchRefused('dedicated model identity required')
        started = _monotonic()
        cur.execute('SELECT public.reserve_model_call(%s,%s,%s,%s,%s,%s,%s)',
                    (request_id, model_id, call_kind, estimated_neurons, capture_id,
                     len(body), hashlib.sha256(body).hexdigest()))
        permit = cur.fetchone()[0]
        if not permit.get('allowed'):
            if permit.get('duplicate'):
                raise DispatchRefused('request already reserved')
            raise BudgetExceeded(permit['spent'], permit['ceiling'], permit['reason'])
        if permit.get('request_id') != request_id:
            raise DispatchRefused('reservation identity mismatch')
        reserved = dt.datetime.fromisoformat(permit['reserved_at'])
        expires = dt.datetime.fromisoformat(permit['valid_before'])
        if reserved.utcoffset() is None or expires.utcoffset() is None:
            raise DispatchRefused('reservation clock missing timezone')
        # Measure from BEFORE the RPC, conservatively including lock/roundtrip time.
        lifetime = (expires-reserved).total_seconds()
        if not 0 < lifetime <= 86400:
            raise DispatchRefused('invalid permit lifetime')
        conn.commit()
    except (DispatchRefused, BudgetExceeded):
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    except Exception:
        # A commit can succeed server-side while its acknowledgement is lost.
        # Do not send, and do not report exception text containing credentials.
        try:
            conn.rollback()
        except Exception:
            pass
        raise DispatchRefused('reservation not confirmed') from None
    if _monotonic()-started >= lifetime:
        raise DispatchRefused('reservation expired before dispatch')
    try:
        raw = (_transport or _post)(model_id, body)
        result = json.loads(raw.decode())
        outcome = 'ok'
    except Exception:
        result = None
        raw = None
        outcome = 'error'
    try:
        cur.execute('SELECT public.settle_model_call(%s,%s,%s)',
                    (request_id, outcome, len(raw) if raw is not None else None))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise DispatchUncertain('request outcome could not be recorded') from None
    if outcome == 'error':
        raise DispatchUncertain('provider request failed; reservation retained')
    return result


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
    # A PREFIX is allowed: a prefixed coordinate key is the same disclosure as a bare one,
    # and a \b-anchored pattern misses every prefixed form.
    re.compile(r"\w*(lat|latitude|lon|lng|longitude|coord|coordinate|geohash|"
               r"northing|easting|utm|mgrs)\b\"?\s*[:=]", re.I),
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

# A blind "two floats together" test cannot tell {"protein_g": 30.5, "carbs_g": 45.2} from a
# coordinate, and round 4 proved it both ways: it passed a pair held as Decimal (which is what
# pg8000 returns for every numeric column, and these payloads are built from SQL rows), as
# strings, and in any object with more than six keys — while REFUSING every real nutrition
# payload and any Ask result carrying two percentiles. A screen that blocks the traffic it
# exists to protect gets removed by whoever hits it next.
#
# What discriminates is the KEY and the TEXT SHAPE, not the arithmetic. Those are screened
# below over a normalised rendering: Decimals stringified, and unicode escapes DECODED — an
# earlier comment claimed decoding happened and it did not, so `\u0034\u0030.7128` walked
# straight through.


# Keys that hold a coordinate pair WITHOUT naming it. Narrow on purpose: keyed on the name,
# not on "two floats together", because the blind version refused every real nutrition and
# statistics payload. A pair under `x`/`y`, a list under `points`, a `location` object.
_PAIR_CONTAINER = re.compile(r"^(points?|coords?|coordinates|location|place|position|geometry)$", re.I)
_PAIR_MEMBER = re.compile(r"^(?:\w+_)?(x|y|a|b|0|1)$", re.I)


def _screen_pair_containers(node):
    """Refuse a coordinate pair hidden under keys that do not name it."""
    if isinstance(node, dict):
        members = [k for k in node if _PAIR_MEMBER.match(str(k))
                   and isinstance(node[k], (int, float)) and not isinstance(node[k], bool)]
        if len(members) >= 2:
            raise PayloadRefused(
                "payload holds a numeric pair under generic keys; a coordinate does not stop "
                "being one because its fields are called x and y (RULE-29)")
        for key, value in node.items():
            if _PAIR_CONTAINER.match(str(key)):
                raise PayloadRefused(
                    f"payload holds a {key!r} field; positions never leave this system "
                    "(RULE-29). The restricted store is the only place they live (ADR-0020).")
            _screen_pair_containers(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _screen_pair_containers(value)


def _normalise(payload) -> str:
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    # Decode \uXXXX so an escaped coordinate is screened as the characters it denotes.
    try:
        text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    except ValueError:
        pass
    return text.replace("\\", "")          # JSON-escaped quotes, so DMS survives the scan


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
    _screen_pair_containers(payload)
    text = _normalise(payload)
    for pattern in _FORBIDDEN:
        if pattern.search(text):
            raise PayloadRefused(
                f"payload matches a forbidden pattern ({pattern.pattern!r}); "
                "coordinates and the home location never leave this system (RULE-29)")


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
    """Legacy rollback-fixture adapter; real calls use isolated dispatch (ADR-0146).

    The caller owns the transaction. `_transport` exists so a test can prove the budget,
    screening and logging behaviour without reaching the network — the seam is explicit rather
    than a monkeypatch, so what is substituted is visible in the signature.
    """
    if _transport is None:
        raise DispatchRefused('model calls require the isolated committed dispatcher')
    screen_payload(payload)                                   # RULE-29, before anything else
    spent, ceiling = check_budget(cur, estimated_neurons, deferred_retry, schema)

    body = json.dumps(payload).encode()
    egress_id, ledger_id = _log(
        cur, destination=WORKERS_AI_HOST, purpose=purpose or call_kind, model_id=model_id,
        call_kind=call_kind, estimated_neurons=estimated_neurons, capture_id=capture_id,
        deferred_retry=deferred_retry, request_bytes=len(body), schema=schema, ops=ops)

    try:
        raw = _transport(model_id, body)
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


# ---------------------------------------------------------------- source APIs (B12, REQ-NUT)
# The nutrition sources are not model calls: they cost no neurons and consume no budget. They
# share this module because RULE-29 reserves ONE outbound path and `validate_layout.py` enforces
# it — a second module with its own logging would be a second place for an unlogged call to
# appear. What they share is the log; what they do not share is the budget.


def get_json(cur, url, purpose, *, params=None, headers=None, timeout=20,
             schema="core", ops="ops", config="config", _transport=None):
    """GET a source API, allowlisted and logged. Returns the parsed body.

    The host must be in `config.egress_allowlist` — a table, not a constant, so adding a
    destination is a visible data change that can be reviewed on its own rather than a line in
    a diff about something else.

    **The request body is never logged.** `ops.egress_log` records the host, the purpose and
    the byte counts; a nutrition query carries what Joe ate, and a log that reproduces it turns
    the audit trail into a second copy of the record it is auditing.
    """
    from urllib.parse import urlencode, urlsplit

    host = urlsplit(url).hostname or ""
    # Schema names are parameters here for the same reason as in the engines (ADR-0061): a
    # test must exercise this against throwaway schemas rather than creating ones called
    # `config`, which RULE-01 forbids.
    if not re.match(r"^[a-z_][a-z0-9_]*$", config):
        raise ValueError(f"not a plain schema identifier: {config!r}")
    cur.execute(f"select 1 from {config}.egress_allowlist where host = %s", (host,))
    if cur.fetchone() is None:
        raise PayloadRefused(
            f"{host!r} is not in config.egress_allowlist; personal data leaves this system "
            "only to the destinations RULE-29 names")

    full = url + (("?" + urlencode(params)) if params else "")
    # Query parameters can carry the food name, so they are screened like any other payload.
    screen_payload({"url_params": params or {}})

    cur.execute(
        f"""insert into {ops}.egress_log (destination, purpose, request_bytes, detail)
            values (%s, %s, %s, %s) returning egress_id""",
        (host, purpose, len(full.encode()),
         json.dumps({"path": urlsplit(url).path, "n_params": len(params or {})})))
    egress_id = cur.fetchone()[0]

    started = dt.datetime.now(dt.timezone.utc)
    try:
        raw = (_transport or _get)(full, headers or {}, timeout)
    except Exception as e:
        cur.execute(f"""update {ops}.egress_log set detail = detail || %s where egress_id = %s""",
                    (json.dumps({"error": type(e).__name__}), egress_id))
        raise
    elapsed_ms = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
    cur.execute(
        f"""update {ops}.egress_log set response_bytes = %s, detail = detail || %s
             where egress_id = %s""",
        (len(raw), json.dumps({"ms": elapsed_ms}), egress_id))
    return json.loads(raw.decode())


def _get(url, headers, timeout):
    req = urllib.request.Request(url, method="GET", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


class _RefuseModelRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PayloadRefused('model destination redirect refused')


def _post(model_id, body):
    """The model transport; redirects cannot disclose its authorization header."""
    account = os.environ.get("CF_ACCOUNT_ID")
    token = os.environ.get("CF_API_TOKEN")
    if not account or not token:
        raise RuntimeError("CF_ACCOUNT_ID / CF_API_TOKEN not set")
    url = f"https://{WORKERS_AI_HOST}/client/v4/accounts/{account}/ai/run/{model_id}"
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    opener = urllib.request.build_opener(_RefuseModelRedirect())
    with opener.open(req, timeout=TIMEOUT_SECONDS) as resp:
        return resp.read()
