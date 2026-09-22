"""Persisted lifecycle owner (ADR-0144). No network/model calls or raw UPDATEs.

Caller owns transaction/commit. A receipt from record_outcome is not a claim that
the transaction committed. Expected event identity protects newer successful work
from a late failure; stale outcomes remain immutable history.
"""
import re

CODE_VERSION = 'capture-processing-v1'
JOB_NAME = 'capture_processing_maintenance'


def _schema(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z_][a-z0-9_]*', value):
        raise ValueError('invalid schema identifier')
    return value


def record_outcome(cur, *, capture_id, attempt_id, expected_event_id, status,
                   error=None, processor_version):
    cur.execute('SELECT public.record_capture_processing(%s,%s,%s,%s,%s,%s)',
                (capture_id, attempt_id, expected_event_id, status, error, processor_version))
    return cur.fetchone()[0]


def pending_work(cur, *, now, schema='core'):
    """REQ-CAP-026/027: budget deferral cannot erase an unresolved provider failure.

    Deferred-only captures are retryable but do not acquire a fictional provider
    failure age. The runner must apply the shared budget before making a call.
    """
    schema = _schema(schema)
    cur.execute(f'''SELECT capture_id, event_id, pending_since, last_error,
                          coalesce(%s::timestamptz - pending_since > interval '72 hours', false)
                            AS stalled, processing_status
                     FROM {schema}.capture_processing_current
                    WHERE processing_status IN ('pending_enrichment','deferred_budget')
                    ORDER BY coalesce(pending_since, captured_at), capture_id''', (now,))
    return [dict(zip(('capture_id', 'event_id', 'pending_since', 'last_error', 'stalled',
                      'processing_status'), row))
            for row in cur.fetchall()]


def maintain_reviews(cur, *, now):
    """REQ-CAP-027: actual persisted reviews and a counts-only heartbeat.

    Caller commits or rolls back. This is maintenance, not a model execution job;
    no capture is marked enriched here, and initial received work stays visible.
    """
    # One migration-bound RPC owns queue mutation, counts and heartbeat together.
    # A caller cannot redirect only the reads/logs and accidentally write elsewhere.
    cur.execute('SELECT public.maintain_capture_processing(%s)', (now,))
    return cur.fetchone()[0]
