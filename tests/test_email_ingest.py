"""B17 §A.1..A.3 — email ingest and the source-adapter interface (REQ-FIN-017, 020..034)."""
import datetime as dt

import pytest

from tools.engines.email_ingest import (IngestViolation, NEURON_DAILY_ALLOWANCE,
                                        PARSE_FAILURE_NOTIFY_DAYS, POLL_INTERVAL_MINUTES,
                                        RawTxn, STALE_IMPORT_DAYS, TIER2,
                                        adapter_credentials, alert_to_raw_txn,
                                        check_downstream_provider_reference,
                                        fetch_transactions, occurred_at_precedence,
                                        on_adapter_error, order_confirmation_items, parse,
                                        poll_schedule, stale_import_reminder)

SWIPE = dt.datetime(2026, 9, 3, 22, 40)
ARRIVED = dt.datetime(2026, 9, 3, 22, 42)


def test_REQ_FIN_020_the_job_polls_every_fifteen_minutes_for_unseen_messages():
    """A quarter-hour of latency on a purchase Joe already knows he made costs nothing, and the
    alert email is the only timely source there is."""
    s = poll_schedule()
    assert s["interval_minutes"] == POLL_INTERVAL_MINUTES == 15
    assert s["cron"] == "*/15 * * * *"
    assert "absent from raw_documents" in s["selector"]


def test_REQ_FIN_021_028_an_alert_is_pending_and_flagged_as_a_pre_authorisation():
    """A $50 bar pre-auth commonly settles at $67 after tip. An alert-derived amount treated as
    final understates exactly the category where the gap is largest — in the flattering
    direction."""
    txn, meta = alert_to_raw_txn(
        {"account": "visa", "amount": 50.0, "descriptor": "JOES BAR",
         "body_timestamp": SWIPE}, message_ts=ARRIVED)
    assert txn.pending is True and txn.occurred_at == SWIPE
    assert meta["pre_authorisation_estimate"] is True
    assert meta["occurred_at_source"] == "alert_body"


def test_REQ_FIN_021_with_no_body_timestamp_the_message_time_is_used_and_recorded_as_such():
    """A message timestamp is when the mail arrived rather than when the card was presented, so
    the distinction is recorded rather than blurred."""
    txn, meta = alert_to_raw_txn(
        {"account": "visa", "amount": 50.0, "descriptor": "X"}, message_ts=ARRIVED)
    assert txn.occurred_at == ARRIVED
    assert meta["occurred_at_source"] == "message_timestamp"


def test_REQ_FIN_022_a_later_csv_never_overwrites_the_alert_s_time_of_day():
    """The alert arrives at the moment of the swipe and carries the clock; the CSV arrives days
    later carrying only a date. "More recent" and "more accurate" are different things here."""
    existing = {"source_tier": TIER2, "occurred_at": SWIPE}
    out = occurred_at_precedence(existing, {"occurred_at": dt.datetime(2026, 9, 4, 0, 0)})
    assert out["occurred_at"] == SWIPE and out["overwritten"] is False
    assert "not more accurate" in out["reason"]


def test_REQ_FIN_022_a_csv_first_observation_is_updated_normally():
    """The precedence is about the ALERT's clock, not about refusing all updates."""
    existing = {"source_tier": "csv_import", "occurred_at": dt.datetime(2026, 9, 4)}
    out = occurred_at_precedence(existing, {"occurred_at": SWIPE})
    assert out["overwritten"] is True and out["occurred_at"] == SWIPE


def test_REQ_FIN_023_one_transaction_items_row_per_line_linked_by_foreign_key():
    """Line items are the only place this system learns WHAT was bought rather than where. A
    single total from a merchant is a category guess; "espresso, 2, 3.50" is not."""
    rows = order_confirmation_items(
        {"line_items": [{"description": "espresso", "quantity": 2, "unit_amount": 3.50},
                        {"description": "bagel", "quantity": 1, "unit_amount": 4.25}]},
        transaction_id="t1")
    assert len(rows) == 2 and all(r["transaction_id"] == "t1" for r in rows)
    assert rows[0]["description"] == "espresso"
    with pytest.raises(IngestViolation, match="REQ-FIN-023"):
        order_confirmation_items({"line_items": [{"description": "x", "quantity": 1}]},
                                 transaction_id="t1")


def test_REQ_FIN_024_a_deterministic_template_runs_before_any_model():
    """A regex either matches or does not, and when it does the result is exact. A model asked to
    parse the same email will ALWAYS return something, and what it returns is plausible whether
    or not it is right."""
    calls = []
    templates = {"bank@x": {"match": lambda e: {"amount": 41.0}, "version": "v1"}}
    out = parse({"sender": "bank@x"}, templates=templates,
                model=lambda e: calls.append("model") or {"fields": {}, "confidence": 0.9},
                model_enabled=True)
    assert out["path"] == "template" and out["provenance"] == "extracted"
    assert calls == [], "the model was never invoked"


def test_REQ_FIN_025_a_template_that_stops_matching_writes_a_failure_and_notifies_once():
    """A sender previously parsed successfully whose template no longer matches means the bank
    changed its email format — silent data loss with a clear cause, and nothing else in the
    system will notice: the transactions simply stop appearing."""
    templates = {"bank@x": {"match": lambda e: None, "version": "v2",
                            "previously_succeeded": True}}
    out = parse({"sender": "bank@x", "message_id": "m1"}, templates=templates)
    assert out["path"] == "template_failed"
    assert out["rows"][0]["table"] == "parse_failures"
    assert out["rows"][0]["template_version"] == "v2"
    assert out["notify"]["once_per_days"] == PARSE_FAILURE_NOTIFY_DAYS == 7
    assert "not being" in out["notify"]["text"]


def test_REQ_FIN_026_the_model_runs_only_after_a_template_failed_and_marks_the_row_inferred():
    """A model-parsed amount and a regex-parsed one are different kinds of number."""
    templates = {"bank@x": {"match": lambda e: None, "version": "v1"}}
    out = parse({"sender": "bank@x"}, templates=templates,
                model=lambda e: {"fields": {"amount": 41.0}, "confidence": 0.82},
                model_enabled=True)
    assert out["path"] == "model" and out["provenance"] == "inferred"
    assert out["confidence"] == 0.82


def test_REQ_FIN_026_with_the_fallback_disabled_nothing_is_parsed_rather_than_guessed():
    out = parse({"sender": "unknown@x"}, templates={}, model_enabled=False)
    assert out["parsed"] is None and out["path"] == "no_parser"


def test_REQ_FIN_027_an_exhausted_allowance_defers_and_NEVER_falls_back_to_a_billable_endpoint():
    """RULE-28 again: the free allowance is the cost control, not an inconvenience around it."""
    templates = {"bank@x": {"match": lambda e: None, "version": "v1"}}
    out = parse({"sender": "bank@x"}, templates=templates, model=lambda e: {},
                model_enabled=True, neurons_used_today=NEURON_DAILY_ALLOWANCE)
    assert out["path"] == "deferred" and out["billable_fallback"] is False
    assert "next 00:00 UTC reset" in out["retry_after"]


def test_REQ_FIN_017_one_reminder_per_account_and_none_until_an_import_succeeds():
    """A repeating reminder about a manual export is one Joe learns to dismiss — and the export
    is the thing that stopped, so the reminder has to still mean something when it matters."""
    assert stale_import_reminder("bank_csv", days_since_import=STALE_IMPORT_DAYS,
                                 already_reminded=False) is None
    out = stale_import_reminder("bank_csv", days_since_import=120, already_reminded=False)
    assert out["repeat"] is False and "120 days" in out["text"]
    assert stale_import_reminder("bank_csv", days_since_import=120,
                                 already_reminded=True) is None


def test_REQ_FIN_030_every_source_returns_one_shape():
    """A provider-shaped object leaks a provider name past raw_transactions the moment somebody
    wants to special-case one."""
    def good(account, since):
        return [RawTxn(account=account, occurred_at=SWIPE, amount=1.0, descriptor="X")]

    assert len(fetch_transactions("visa", SWIPE, adapters={"a": good}, enabled=("a",))) == 1
    with pytest.raises(IngestViolation, match="REQ-FIN-030"):
        fetch_transactions("visa", SWIPE,
                           adapters={"a": lambda ac, s: [{"amount": 1.0}]}, enabled=("a",))


def test_REQ_FIN_030_no_provider_name_appears_downstream():
    assert check_downstream_provider_reference("SELECT * FROM raw_transactions")
    for p in ("teller", "Plaid", "yodlee"):
        with pytest.raises(IngestViolation, match="REQ-FIN-030"):
            check_downstream_provider_reference(f"if source == '{p}':")


def test_REQ_FIN_031_034_mtls_authenticates_the_SYSTEM_never_a_bank_login():
    """An mTLS client certificate authenticates THIS SYSTEM to the provider. A bank login
    authenticates JOE to his bank, and storing one puts this repository in a different category
    of thing entirely."""
    out = adapter_credentials(uses_mtls_from_secret=True, stores_login=False,
                              drives_browser=False)
    assert out["auth"] == "mtls_client_certificate" and out["cost"] == 0
    for kw in ({"stores_login": True}, {"drives_browser": True}):
        args = {"uses_mtls_from_secret": True, "stores_login": False, "drives_browser": False}
        args.update(kw)
        with pytest.raises(IngestViolation, match="REQ-FIN-034"):
            adapter_credentials(**args)
    with pytest.raises(IngestViolation, match="REQ-FIN-031"):
        adapter_credentials(uses_mtls_from_secret=False, stores_login=False,
                            drives_browser=False)


def test_REQ_FIN_032_033_an_adapter_error_disables_it_and_degrades_nothing():
    """"No degradation of any downstream function" is the load-bearing half: an adapter that
    fails open turns an optional convenience into a single point of failure for the subsystem."""
    healthy = {"ingest": True, "categorisation": True, "recurrence": True,
               "usage_inference": True, "review": True}
    out = on_adapter_error("quota", already_notified=False, downstream=healthy)
    assert out["disable"] is True and out["notify"] is True and out["notify_once"] is True
    assert out["tier1_continues"] is True and out["tier2_continues"] is True
    assert on_adapter_error("quota", already_notified=True,
                            downstream=healthy)["notify"] is False
    with pytest.raises(IngestViolation, match="REQ-FIN-033"):
        on_adapter_error("authentication", already_notified=False,
                         downstream={**healthy, "recurrence": False})
