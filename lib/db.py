"""Supabase Postgres connection — the one place ETL reaches the database.

TLS is verified against Supabase's pinned root CA (lib/certs/supabase-prod-ca-2021.crt),
with hostname checking on. CERT_NONE (encrypt-without-verify) was considered for the
Phase-0 archive and rejected: this is the permanent connection path for every ETL job
from Phase 2 onward, and an unverified posture set "just for the archive" would have
become the ETL default by inertia. See PROGRESS 2026-08-23.

ETL uses SUPABASE_DB_URL; the isolated model process uses MODEL_EGRESS_DB_URL.
The credential is never
hardcoded here, never logged, never echoed. This module reads it and hands back a live
connection; it does not print it.

This is a minimal connection helper (TLS + credential parsing), NOT the Phase-2 spine:
no pooling, no ret/backoff, no ops.egress_log wiring. Those arrive with the spine.
"""
import os
import ssl
import signal
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse, unquote

import pg8000.dbapi

CA_FILE = Path(__file__).resolve().parent / "certs" / "supabase-prod-ca-2021.crt"


def _ssl_context():
    if not CA_FILE.exists():
        raise RuntimeError(f"pinned CA missing: {CA_FILE}")
    ctx = ssl.create_default_context(cafile=str(CA_FILE))
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    # Python's create_default_context() enables OpenSSL 3.x strict mode
    # (VERIFY_X509_STRICT), which rejects this chain because the Supabase
    # *intermediate* ("Supabase Intermediate 2021 CA") and leaf
    # ("*.pooler.supabase.com") omit an explicit keyUsage extension — strict mode
    # requires a CA in the path to carry keyUsage=keyCertSign. (The pinned root
    # itself DOES carry keyUsage; the intermediate is the one that trips strict
    # mode.) Standard (non-strict) verification — what `openssl s_client -CAfile`
    # and every other Postgres client apply — accepts it. We clear ONLY this flag.
    # Full chain verification against the pinned root and hostname checking both
    # remain on. This is not CERT_NONE.
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


def connect():
    """Return a live pg8000 DB-API connection with verified TLS."""
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL not set")
    return _connect_url(url)


def connect_model_egress():
    """Dedicated credential only; provider processes must not inherit private DB access."""
    if any(os.environ.get(key) for key in ('SUPABASE_DB_URL', 'SUPABASE_SERVICE_ROLE_KEY',
                                          'SUPABASE_STORAGE_READ_JWT')):
        raise RuntimeError('private database credentials present in model process')
    url = os.environ.get('MODEL_EGRESS_DB_URL')
    if not url:
        raise RuntimeError('MODEL_EGRESS_DB_URL not set')
    return _connect_url(url)


def connect_reference_egress():
    """Source-only credential; the dispatcher also verifies the actual login role."""
    if any(os.environ.get(key) for key in ('SUPABASE_DB_URL', 'SUPABASE_SERVICE_ROLE_KEY',
        'SUPABASE_STORAGE_READ_JWT', 'MODEL_EGRESS_DB_URL', 'CF_API_TOKEN')):
        raise RuntimeError('private or model credentials present in reference process')
    url = os.environ.get('REFERENCE_EGRESS_DB_URL')
    if not url:
        raise RuntimeError('REFERENCE_EGRESS_DB_URL not set')
    return _connect_url(url)


def _connect_url(url):
    p = urlparse(url)
    return pg8000.dbapi.connect(
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        host=p.hostname,
        port=p.port or 5432,
        database=(p.path or "/postgres").lstrip("/") or "postgres",
        ssl_context=_ssl_context(),
    )


class CaptureMediaUnavailable(Exception):
    """Sanitized private Storage failure; never includes a URL or credential."""


CAPTURE_MEDIA_DEADLINE_SECONDS = 45


@contextmanager
def _capture_media_deadline():
    """Interrupt even a slow-drip blocking read in the dedicated private CLI.

    POSIX main-thread only. Refuse an already armed timer rather than overwriting
    another operation's deadline. No timer or signal-handler state leaks afterward.
    """
    if (threading.current_thread() is not threading.main_thread()
        or not hasattr(signal,'setitimer')):
        raise CaptureMediaUnavailable('media deadline requires a POSIX main thread')
    if signal.getitimer(signal.ITIMER_REAL) != (0.0,0.0):
        raise CaptureMediaUnavailable('media deadline timer already in use')
    previous = signal.getsignal(signal.SIGALRM)
    def expired(signum,frame):
        raise CaptureMediaUnavailable('private media acquisition deadline exceeded')
    signal.signal(signal.SIGALRM,expired)
    try:
        signal.setitimer(signal.ITIMER_REAL,CAPTURE_MEDIA_DEADLINE_SECONDS)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)


def read_capture_media(capture_id, media_path, expected_sha256):
    """Apply a wall-clock deadline to configuration, connection, body and hash check."""
    with _capture_media_deadline():
        return _read_capture_media(capture_id,media_path,expected_sha256)


def _read_capture_media(capture_id, media_path, expected_sha256):
    """Read hash-bound bytes from the configured private Supabase captures bucket.

    This is a read of the authoritative private store, not a provider capability.
    A separate process still owns model egress. No redirect, arbitrary URL, public
    bucket, filesystem path, or unbounded response is accepted.
    """
    import hashlib
    import re
    import uuid
    import urllib.request
    import urllib.error

    cid = str(uuid.UUID(str(capture_id)))
    if (not isinstance(media_path,str)
        or not re.fullmatch(re.escape(cid)+r'/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',media_path)
        or not isinstance(expected_sha256,str)
        or not re.fullmatch('[a-f0-9]{64}',expected_sha256)):
        raise ValueError('invalid capture media binding')
    if os.environ.get('CF_API_TOKEN') or os.environ.get('MODEL_EGRESS_DB_URL'):
        raise CaptureMediaUnavailable('provider capability present')
    origin = os.environ.get('SUPABASE_URL','').rstrip('/')
    if not re.fullmatch(r'https://[a-z0-9-]+\.supabase\.co',origin):
        raise CaptureMediaUnavailable('private storage origin not configured')
    token = os.environ.get('SUPABASE_STORAGE_READ_JWT')
    api_key = os.environ.get('SUPABASE_ANON_KEY')
    if not token or not api_key:
        raise CaptureMediaUnavailable('private storage credential not configured')

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            raise CaptureMediaUnavailable('private storage redirect refused')

    maximum = 50 * 1024 * 1024
    request = urllib.request.Request(origin+'/storage/v1/object/authenticated/captures/'+media_path,
        method='GET',headers={'Authorization':'Bearer '+token,'apikey':api_key,
                              'Accept-Encoding':'identity'})
    try:
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request,timeout=30) as response:
            if response.status != 200:
                raise CaptureMediaUnavailable('private storage response refused')
            declared = response.headers.get('Content-Length')
            if declared is not None and (not declared.isdecimal() or int(declared)>maximum):
                raise CaptureMediaUnavailable('private media size refused')
            body = response.read(maximum+1)
    except CaptureMediaUnavailable:
        raise
    except Exception:
        raise CaptureMediaUnavailable('private storage download failed') from None
    if not body or len(body)>maximum:
        raise CaptureMediaUnavailable('private media size refused')
    if hashlib.sha256(body).hexdigest() != expected_sha256:
        raise CaptureMediaUnavailable('private media digest mismatch')
    return body
