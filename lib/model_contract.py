"""One byte representation binds prepared model payloads to budget reservations."""
import json


def request_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


AUDIO_NEURONS_PER_MINUTE = 46.63


def audio_neurons(duration_seconds):
    """REQ-CAP-036 owner: unrounded binary-float estimate for JSON transport.

    Persist Decimal(str(returned_value)) so the prepared request and reservation
    compare exactly; do not independently round a consumer's daily contribution.
    """
    return float(duration_seconds) / 60.0 * AUDIO_NEURONS_PER_MINUTE
