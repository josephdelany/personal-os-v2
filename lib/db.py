"""Supabase Postgres connection — the one place ETL reaches the database.

TLS is verified against Supabase's pinned root CA (lib/certs/supabase-prod-ca-2021.crt),
with hostname checking on. CERT_NONE (encrypt-without-verify) was considered for the
Phase-0 archive and rejected: this is the permanent connection path for every ETL job
from Phase 2 onward, and an unverified posture set "just for the archive" would have
become the ETL default by inertia. See PROGRESS 2026-08-23.

The credential comes only from the SUPABASE_DB_URL environment variable. It is never
hardcoded here, never logged, never echoed. This module reads it and hands back a live
connection; it does not print it.

This is a minimal connection helper (TLS + credential parsing), NOT the Phase-2 spine:
no pooling, no ret/backoff, no ops.egress_log wiring. Those arrive with the spine.
"""
import os
import ssl
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
    p = urlparse(url)
    return pg8000.dbapi.connect(
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        host=p.hostname,
        port=p.port or 5432,
        database=(p.path or "/postgres").lstrip("/") or "postgres",
        ssl_context=_ssl_context(),
    )
