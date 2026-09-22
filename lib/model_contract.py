"""One byte representation binds prepared model payloads to budget reservations."""
import json


def request_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
