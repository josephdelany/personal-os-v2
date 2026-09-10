"""B17 §A.1..A.3 — email ingest and the source-adapter interface (REQ-FIN-017, 020..034).

Pure: no database, no network, no clock. Emails come in as parsed dicts; what comes back is the
rows to write and the reasons for anything refused.

WHY THE ALERT'S TIME-OF-DAY WINS FOREVER (REQ-FIN-022). The alert email arrives at the moment of
the swipe and carries the clock. The CSV arrives days later carrying only a date. So the alert is
the ONLY source that ever knows a purchase happened at 22:40 — and a later observation of the
same purchase must not overwrite it, because "more recent" and "more accurate" are different
things and only one of them is true here.

WHY A TEMPLATE IS TRIED BEFORE ANY MODEL (REQ-FIN-024). A per-sender regex either matches or does
not, and when it does the result is exact. A model asked to parse the same email will always
return something, and what it returns is plausible whether or not it is right. Deterministic
first is not an optimisation; it is the difference between a parse that can fail loudly and one
that cannot fail at all.

WHY A TEMPLATE THAT STOPS MATCHING IS A NOTIFICATION (REQ-FIN-025). A sender previously parsed
successfully whose template no longer matches means the bank changed its email format. That is
silent data loss with a clear cause and a cheap fix, and nothing else in the system will notice
it — the transactions simply stop appearing.

WHY THE PRE-AUTH FLAG EXISTS (REQ-FIN-028). A $50 bar pre-authorisation commonly settles at $67
after tip. An alert-derived amount treated as final understates exactly the category where the
gap is largest, and understates it in the direction that flatters.

WHY NO CODE DOWNSTREAM MAY NAME A PROVIDER (REQ-FIN-030/032/033). Every Tier 3 adapter is
optional, free-tier, and liable to be reclassified out from under this system at any time. If a
provider name reaches past `raw_transactions`, its disappearance becomes a code change rather
than a config change — and the subsystem has to keep working with every adapter disabled.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

POLL_INTERVAL_MINUTES = 15                # REQ-FIN-020
STALE_IMPORT_DAYS = 35                    # REQ-FIN-017
PARSE_FAILURE_NOTIFY_DAYS = 7             # REQ-FIN-025
NEURON_DAILY_ALLOWANCE = 10_000           # REQ-FIN-027
TIER1, TIER2, TIER3 = "csv_import", "email_alert", "api_adapter"


class IngestViolation(Exception):
    pass


@dataclass(frozen=True)
class RawTxn:
    """REQ-FIN-030. The single shape every source returns.

    No provider field: the shape is what downstream reads, and a provider name in it would leak
    past `raw_transactions` the moment somebody wanted to special-case one.
    """
    account: str
    occurred_at: dt.datetime
    amount: float
    descriptor: str
    pending: bool = False
    provenance: str = "extracted"
    confidence: float | None = None
    source_tier: str = TIER2


def poll_schedule():
    """REQ-FIN-020. Every 15 minutes, on Actions cron, for messages not already stored.

    Fifteen minutes rather than continuously: the alert email is the only timely source, and a
    quarter-hour of latency on a purchase Joe already knows he made costs nothing.
    """
    return {"cron": "*/15 * * * *", "interval_minutes": POLL_INTERVAL_MINUTES,
            "selector": "messages in the ingest mailbox absent from raw_documents"}


def alert_to_raw_txn(alert, *, message_ts):
    """REQ-FIN-021/022/028. `pending=true`, the body's timestamp, and the pre-auth flag.

    The body's timestamp when it has one, the message timestamp otherwise — and the distinction
    is recorded, because a message timestamp is when the mail arrived rather than when the card
    was presented.
    """
    body_ts = alert.get("body_timestamp")
    return RawTxn(
        account=alert["account"], occurred_at=body_ts or message_ts,
        amount=float(alert["amount"]), descriptor=alert["descriptor"],
        pending=True, source_tier=TIER2), {
        "occurred_at_source": "alert_body" if body_ts else "message_timestamp",
        # REQ-FIN-028. A $50 bar pre-auth commonly settles at $67 after tip: treating an
        # alert-derived amount as final understates exactly the category where the gap is
        # largest, and understates it in the flattering direction.
        "pre_authorisation_estimate": True,
        "superseded_by_posted": False}


def occurred_at_precedence(existing, incoming):
    """REQ-FIN-022. An alert's time-of-day is authoritative and is never overwritten.

    The alert arrives at the moment of the swipe and carries the clock; the CSV arrives days
    later carrying only a date. So the alert is the ONLY source that ever knows a purchase
    happened at 22:40, and "more recent" and "more accurate" are different things here.
    """
    if existing.get("source_tier") == TIER2 and existing.get("occurred_at") is not None:
        if incoming.get("occurred_at") != existing["occurred_at"]:
            return {"occurred_at": existing["occurred_at"], "overwritten": False,
                    "reason": ("REQ-FIN-022: the alert carried the time of day and a later CSV "
                               "or API observation carries only a date; more recent is not more "
                               "accurate here")}
    return {"occurred_at": incoming.get("occurred_at"), "overwritten": True}


def order_confirmation_items(email, *, transaction_id):
    """REQ-FIN-023. One `transaction_items` row per line item, linked by foreign key.

    Line items are the only place this system ever learns WHAT was bought rather than where. A
    single total from a merchant is a category guess; a line saying "espresso, 2, 3.50" is not.
    """
    rows = []
    for line in email.get("line_items") or ():
        for f in ("description", "quantity", "unit_amount"):
            if line.get(f) is None:
                raise IngestViolation(
                    f"REQ-FIN-023: a transaction_items row carries {f}; a line without it is a "
                    f"total wearing an itemisation's clothes")
        rows.append({"table": "transaction_items", "transaction_id": transaction_id,
                     "description": line["description"], "quantity": line["quantity"],
                     "unit_amount": line["unit_amount"]})
    return tuple(rows)


def parse(email, *, templates, model=None, neurons_used_today=0, model_enabled=False):
    """REQ-FIN-024/025/026/027. Template first, model only on failure, never a billable endpoint.

    A per-sender regex either matches or does not, and when it does the result is exact. A model
    asked to parse the same email will ALWAYS return something, and what it returns is plausible
    whether or not it is right. Deterministic first is the difference between a parse that can
    fail loudly and one that cannot fail at all.
    """
    sender = email.get("sender")
    tpl = templates.get(sender)
    if tpl is not None:
        parsed = tpl["match"](email)
        if parsed is not None:
            return {"parsed": parsed, "path": "template", "provenance": "extracted",
                    "confidence": None}
        if tpl.get("previously_succeeded"):
            # REQ-FIN-025. The bank changed its email format. That is silent data loss with a
            # clear cause and a cheap fix, and nothing else in the system will notice it — the
            # transactions simply stop appearing.
            return {"parsed": None, "path": "template_failed",
                    "rows": ({"table": "parse_failures", "sender": sender,
                              "message_id": email.get("message_id"),
                              "template_version": tpl.get("version")},),
                    "notify": {"sender": sender, "once_per_days": PARSE_FAILURE_NOTIFY_DAYS,
                               "text": (f"{sender} emails stopped matching their template. "
                                        f"Transactions from this sender are not being "
                                        f"recorded.")}}
    if not model_enabled or model is None:
        return {"parsed": None, "path": "no_parser", "rows": ()}
    if neurons_used_today >= NEURON_DAILY_ALLOWANCE:
        # REQ-FIN-027. Deferred to the next UTC reset, and NEVER a billable endpoint. RULE-28
        # again: the free allowance is the cost control, not an inconvenience around it.
        return {"parsed": None, "path": "deferred",
                "retry_after": "next 00:00 UTC reset", "billable_fallback": False,
                "reason": (f"the {NEURON_DAILY_ALLOWANCE}-neuron free allowance is exhausted; "
                           f"no billable inference endpoint is used")}
    out = model(email)
    # REQ-FIN-026. Marked inferred with the model's own confidence — never as an extraction,
    # because a model-parsed amount and a regex-parsed one are different kinds of number.
    return {"parsed": out["fields"], "path": "model", "provenance": "inferred",
            "confidence": out["confidence"]}


def stale_import_reminder(account, *, days_since_import, already_reminded):
    """REQ-FIN-017. Exactly one reminder per account, and no second until an import succeeds.

    One, because a repeating reminder about a manual export is a reminder Joe learns to dismiss —
    and the export is the thing that stopped, so the reminder has to still mean something when it
    finally matters.
    """
    if days_since_import <= STALE_IMPORT_DAYS:
        return None
    if already_reminded:
        return None
    return {"account": account, "days": days_since_import,
            "text": (f"{account} has had no successful import for {days_since_import} days."),
            "repeat": False}


# ---------------------------------------------------------------- §A.3 the adapter interface

def fetch_transactions(account, since, *, adapters, enabled=()):
    """REQ-FIN-030. One interface, and no provider name reaches past `raw_transactions`.

    Every Tier 3 adapter is optional, free-tier, and liable to be reclassified out from under
    this system at any time. A provider name downstream turns its disappearance into a code
    change rather than a config change.
    """
    out = []
    for name in enabled:
        fn = adapters.get(name)
        if fn is None:
            continue
        for txn in fn(account, since):
            if not isinstance(txn, RawTxn):
                raise IngestViolation(
                    "REQ-FIN-030: every source returns RawTxn; a provider-shaped object leaks a "
                    "provider name past raw_transactions")
            out.append(txn)
    return tuple(out)


def check_downstream_provider_reference(source_text):
    """REQ-FIN-030. No code downstream of `raw_transactions` names a provider."""
    import re as _re
    providers = ("teller", "plaid", "yodlee", "finicity", "mx.com")
    hits = tuple(p for p in providers
                 if _re.search(rf"(?<![a-z]){_re.escape(p)}(?![a-z])", (source_text or "").lower()))
    if hits:
        raise IngestViolation(
            f"REQ-FIN-030: {list(hits)} named downstream of raw_transactions; a provider name "
            f"there turns an adapter's disappearance into a code change")
    return True


def adapter_credentials(*, uses_mtls_from_secret, stores_login, drives_browser):
    """REQ-FIN-031/034. mTLS from a secret; never a login, never a browser.

    The distinction matters: an mTLS client certificate authenticates THIS SYSTEM to the
    provider. A bank login authenticates JOE to his bank, and storing one puts this repository in
    a different category of thing entirely.
    """
    if stores_login or drives_browser:
        raise IngestViolation(
            "REQ-FIN-034: the ingest layer stores no bank login credentials and drives no "
            "headless browser; an mTLS certificate authenticates this system to a provider, "
            "while a login authenticates Joe to his bank")
    if not uses_mtls_from_secret:
        raise IngestViolation(
            "REQ-FIN-031: the adapter authenticates with mTLS client certificates read from a "
            "GitHub Actions secret")
    return {"auth": "mtls_client_certificate", "environment": "teller_development",
            "cost": 0, "enrollment_cap": 100}


def on_adapter_error(kind, *, already_notified, downstream):
    """REQ-FIN-032/033. Disable, notify once, and continue Tier 1 and Tier 2 undegraded.

    "No degradation of any downstream function" is the load-bearing half. An adapter that fails
    open — leaving categorisation or recurrence detection broken — turns an optional convenience
    into a single point of failure for the whole subsystem.
    """
    if kind not in ("authentication", "quota", "tier_reclassification"):
        return {"disable": False}
    degraded = tuple(sorted(f for f, ok in downstream.items() if not ok))
    if degraded:
        raise IngestViolation(
            f"REQ-FIN-033: {list(degraded)} degraded with the adapter disabled; the finance "
            f"subsystem remains fully functional with every Tier 3 adapter off")
    return {"disable": True, "notify": not already_notified, "notify_once": True,
            "tier1_continues": True, "tier2_continues": True,
            "reason": f"adapter returned a {kind} error"}
