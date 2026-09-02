#!/usr/bin/env python3
"""E11 — the watch resolver (ADR-0048; docs/build/B7_resolve_watches.md).

`register_watch` (migration 0031) inserts a pre-registered `watch:` row at
status INSUFFICIENT and starts the clock. Nothing re-tested it afterwards, so
the six-tier ladder stopped at WATCHING forever. This job implements the frozen
`resolution_rule` sentence on every watch — "median delta same sign with q<0.10
on >=30 post-registration days" — exactly as written, per row, and never
reinterprets it:

  * only panel days strictly after `confirmation_data_from` are read
    (REQ-INF-107 / REQ-INF-104); the weekday demedian is computed on that
    window alone, so no pre-registration value can leak in;
  * fewer than MIN_POST_DAYS paired days: still on the clock, nothing written;
  * the quartile contrast is the scan's own `_contrast` (imported, not copied:
    RULE-11/12 one owner) with a side floor of MIN_SIDE for the short window;
  * q is Benjamini-Hochberg across the watches evaluated in this run (`scan._bh`);
  * q < Q_CONFIRM and observed sign == registered direction -> CONFIRMED_OBSERVATIONAL,
    opposite sign -> REFUTED; no decision after EXPIRE_DAYS post days -> INSUFFICIENT
    with reason `expired_no_decision_120d`; otherwise still watching, nothing written.

Every status change writes ONE row to core.hypothesis_resolutions (append-only;
REQ-TIER-043), and the register UPDATE touches `status` only (REQ-INF-103 — the
0012 freeze trigger rejects anything else). A CONFIRMED row also inserts a
forward prediction in the same transaction (REQ-INF-301 / RULE-20): the same
rule on the next MIN_POST_DAYS days, resolving 30 days out, p_forecast = the
rule's own FDR bound (1 - Q_CONFIRM). Nothing here computes an E-value or a
negative control; a CONFIRMED row is observational and get_findings says so.

Deterministic, stdlib only, no model. Schema names are parameters so the tests
run the identical code against disposable twins (RULE-01 exception, ADR-0022).
"""
import datetime as dt
import json

from tools.engines import scan
from tools.engines.scan import (_load_panel, _dow_demedian, _contrast,   # noqa: F401 — imported, not copied
                                _mann_whitney_p, _lag1_rho, _median, _bh)

CODE_VERSION = "resolve-v1"
MIN_POST_DAYS = 30        # from the frozen rule text (">=30 post-registration days")
MIN_SIDE = 7              # quartile side minimum on a 30-day window (ADR-0048; scan's 30 is for 7-year sweeps)
Q_CONFIRM = 0.10          # from the frozen rule text ("q<0.10")
EXPIRE_DAYS = 120         # ADR-0048: no decision after 120 post days -> INSUFFICIENT, expired
FORWARD_DAYS = 30         # the forward prediction's window (RULE-20; same length as the rule's)

REASONS = ("confirmed_same_sign_q_lt_0_10", "refuted_opposite_sign_q_lt_0_10",
           "insufficient_window_too_short", "insufficient_low_n_eff",
           "insufficient_sign_unstable", "expired_no_decision_120d")


def _post_window(dv, data_from, today):
    """Only days strictly after confirmation_data_from and not after today."""
    return {d: v for d, v in dv.items() if data_from < d <= today}


def _write_resolution(cur, core, h, status_to, reason, post_days, c, q, obs_dir):
    cur.execute(f"UPDATE {core}.hypothesis_register SET status = %s WHERE hypothesis_id = %s",
                (status_to, h["hypothesis_id"]))
    cur.execute(f"""INSERT INTO {core}.hypothesis_resolutions
        (hypothesis_id, status_from, status_to, reason, post_days, n_hi, n_lo,
         delta, p_raw, q_fdr, registered_direction, observed_direction, code_version)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (h["hypothesis_id"], h["status"], status_to, reason, post_days,
         c[0] if c else None, c[1] if c else None,
         c[4] if c else None, c[5] if c else None, q,
         h["direction"], obs_dir, CODE_VERSION))


def _write_forward_prediction(cur, core, h, q):
    """REQ-INF-301: a CONFIRMED assignment inserts a forward prediction in the same
    transaction. claim = the registered sentence applied to the NEXT window;
    resolution_rule = the frozen rule text (this resolver evaluates it);
    p_forecast = 1 - Q_CONFIRM, the bound the rule licenses (ADR-0048), never 1-q."""
    claim = (f"{h['exposure_metric']} -> {h['outcome_metric']} (lag {h['lag_days']}d): "
             f"median delta {h['direction']} on the next {FORWARD_DAYS} post-confirmation days")
    cur.execute(f"""INSERT INTO {core}.predictions
        (hypothesis_id, claim_text, resolution_rule, resolves_at, evidence_tier,
         model_version, p_forecast, feature_snapshot_hash)
        VALUES (%s, %s, %s, now() + make_interval(days => %s), 'CONFIRMED_OBSERVATIONAL',
                %s, %s, %s)""",
        (h["hypothesis_id"], claim, h["resolution_rule"], FORWARD_DAYS,
         CODE_VERSION, round(1.0 - Q_CONFIRM, 4), json.dumps({"q_fdr_at_confirmation": q})))


def run(cur, today=None, *, core="core", panel_schema="analysis"):
    """Evaluate every open watch. Returns run counts for the ops.runs heartbeat."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    cur.execute(f"""SELECT hypothesis_id, exposure_metric, outcome_metric, lag_days, direction,
                          confirmation_data_from, resolution_rule, status
                     FROM {core}.hypothesis_register
                    WHERE hypothesis_id LIKE %s AND status IN ('INSUFFICIENT','PROMOTED')
                      AND NOT EXISTS (SELECT 1 FROM {core}.hypothesis_resolutions r
                                       WHERE r.hypothesis_id = hypothesis_register.hypothesis_id
                                         AND r.reason = 'expired_no_decision_120d')
                    ORDER BY preregistered_at""", ("watch:%",))
    # an expired watch keeps status INSUFFICIENT (the CHECK has no 'EXPIRED'); its expiry ledger
    # row is what closes it, here and in get_findings — otherwise it would expire again nightly
    cols = ("hypothesis_id", "exposure_metric", "outcome_metric", "lag_days", "direction",
            "confirmation_data_from", "resolution_rule", "status")
    watches = [dict(zip(cols, r)) for r in cur.fetchall()]
    stats = {"evaluated": 0, "confirmed": 0, "refuted": 0, "expired": 0,
             "still_watching": 0, "on_clock": 0}
    if not watches:
        return stats
    panel = _load_panel(cur, schema=panel_schema)
    batch = []      # (h, c, post_days)
    for h in watches:
        data_from = h["confirmation_data_from"].date()
        drv_raw = _post_window(panel.get(h["exposure_metric"], {}), data_from, today)
        out_raw = _post_window(panel.get(h["outcome_metric"], {}), data_from, today)
        if not drv_raw or not out_raw:
            stats["on_clock"] += 1
            continue
        drv = _dow_demedian(drv_raw)
        out = _dow_demedian(out_raw)
        lag = dt.timedelta(days=h["lag_days"])
        post_days = sum(1 for d in drv if (d + lag) in out)
        if post_days < MIN_POST_DAYS:
            stats["on_clock"] += 1          # REQ-INF-107: window_too_short, rule not evaluated
            continue
        stats["evaluated"] += 1
        c = _contrast(drv, out, h["lag_days"], min_side=MIN_SIDE)
        if c is None or min(c[0], c[1]) < MIN_SIDE:
            if post_days >= EXPIRE_DAYS:
                _write_resolution(cur, core, h, "INSUFFICIENT", "expired_no_decision_120d",
                                  post_days, c, None, None)
                stats["expired"] += 1
            else:
                stats["still_watching"] += 1     # insufficient_low_n_eff so far; keep watching
            continue
        batch.append((h, c, post_days))
    if batch:
        qs = _bh([c[5] for _, c, _ in batch])
        for (h, c, post_days), q in zip(batch, qs):
            obs_dir = "positive" if c[4] > 0 else "negative"
            if q < Q_CONFIRM and obs_dir == h["direction"]:
                _write_resolution(cur, core, h, "CONFIRMED_OBSERVATIONAL",
                                  "confirmed_same_sign_q_lt_0_10", post_days, c, q, obs_dir)
                _write_forward_prediction(cur, core, h, q)
                stats["confirmed"] += 1
            elif q < Q_CONFIRM and obs_dir != h["direction"]:
                _write_resolution(cur, core, h, "REFUTED", "refuted_opposite_sign_q_lt_0_10",
                                  post_days, c, q, obs_dir)
                stats["refuted"] += 1
            elif post_days >= EXPIRE_DAYS:
                _write_resolution(cur, core, h, "INSUFFICIENT", "expired_no_decision_120d",
                                  post_days, c, q, obs_dir)
                stats["expired"] += 1
            else:
                stats["still_watching"] += 1
    return stats
