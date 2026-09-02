#!/usr/bin/env python3
"""E11 — the watch resolver (ADR-0048; docs/build/B7_resolve_watches.md).

`register_watch` (migration 0031) inserts a pre-registered `watch:` row at
status INSUFFICIENT and starts the clock. Nothing re-tested it afterwards, so
the six-tier ladder stopped at WATCHING forever. This job implements the frozen
`resolution_rule` sentence on every open watch — "median delta same sign with
q<0.10 on >=30 post-registration days" — exactly as written, per row, and never
reinterprets it:

  * only panel days strictly after `confirmation_data_from` are read
    (REQ-INF-107 / REQ-INF-104); the weekday demedian is computed on that
    window alone, so no pre-registration value can leak in;
  * fewer than MIN_POST_DAYS paired days: still on the clock, nothing written;
  * the quartile contrast is the scan's own `_contrast` (imported, not copied:
    RULE-11/12 one owner) with a side floor of MIN_SIDE for the short window;
  * TWO LOOKS ONLY (Joe's ruling 2026-09-02 on OQ-44(d); ADR-0048 §12): look 1 on
    the first night a watch has >= MIN_POST_DAYS paired days, look 2 once it has
    >= EXPIRE_DAYS paired days. Every look writes one ledger row, so a look is
    never repeated — re-testing every night was optional stopping (measured
    0.58-0.86 false resolution on nulls by day 120);
  * at each look: Kish effective sample size n_eff = post_days*(1-rho)/(1+rho)
    from the outcome's lag-1 rho (deflate only), stored, and gated at N_EFF_MIN
    (REQ-TIER-017's floor) -> `insufficient_low_n_eff` if below;
  * q is Benjamini-Hochberg across the watches looked at in this run (`scan._bh`);
  * q < Q_CONFIRM and observed sign == registered direction -> PROMOTED,
    opposite sign -> REFUTED; otherwise look 1 records `insufficient_sign_unstable`
    (the sign is not established at this look) and waits for look 2; look 2 with
    no decision, or a window that never fills within EXPIRE_DAYS calendar days ->
    INSUFFICIENT with reason `expired_no_decision_120d`, final.

Why PROMOTED and not CONFIRMED_OBSERVATIONAL (ADR-0048 amendment, reviewer #5):
REQ-TIER-013 assigns CONFIRMED_OBSERVATIONAL only with a DAG adjustment set, HAC
errors, an E-value, negative controls and refutation tests — none of which exist.
A pre-registered contrast that survived on post-registration data is exactly
what PROMOTED means; assigning the causal tier without its gate would violate
RULE-00. A later build climbs PROMOTED -> CONFIRMED with the real machinery.

Every status change writes ONE row to core.hypothesis_resolutions (append-only;
REQ-TIER-043), and the register UPDATE touches `status` only (REQ-INF-103 — the
0012 freeze trigger rejects anything else). A PROMOTED row also inserts a
forward prediction in the same transaction (REQ-INF-301): the same sign on the
next FORWARD_DAYS days, resolving then, p_forecast = 1 - Q_CONFIRM (a stated
constant, not a calibrated probability — OQ-44). Nothing scores it yet (OQ-44),
so RULE-20's demotion path is NOT satisfied by this file.

Deterministic, stdlib only, no model. Schema names are parameters so the tests
run the identical code against disposable twins (RULE-01 exception, ADR-0022).
"""
import datetime as dt
import hashlib
import json

from tools.engines import scan
from tools.engines.scan import (_load_panel, _dow_demedian, _contrast,   # noqa: F401 — imported, not copied
                                _mann_whitney_p, _lag1_rho, _median, _bh)

CODE_VERSION = "resolve-v1"
MIN_POST_DAYS = 30        # from the frozen rule text (">=30 post-registration days")
MIN_SIDE = 7              # quartile side floor on a 30-day window (ADR-0048; inert at n>=30 — reviewer #11 — kept as the stated floor)
Q_CONFIRM = 0.10          # from the frozen rule text ("q<0.10")
EXPIRE_DAYS = 120         # ADR-0048: look 2 at 120 paired days; no decision then -> INSUFFICIENT, expired
N_EFF_MIN = 20            # REQ-TIER-017's n_eff floor (a placeholder, OQ-10); gated at every look
LOOK_REASONS = ("insufficient_low_n_eff", "insufficient_sign_unstable")   # a look that decided nothing
FORWARD_DAYS = 30         # the forward prediction's window (REQ-INF-301)
OPEN_STATUSES = ("INSUFFICIENT",)   # PROMOTED is final for resolve-v1 (its forward prediction is the next test)

REASONS = ("promoted_same_sign_q_lt_0_10", "refuted_opposite_sign_q_lt_0_10",
           "insufficient_window_too_short", "insufficient_low_n_eff",
           "insufficient_sign_unstable", "expired_no_decision_120d")


def _post_window(dv, data_from, today):
    """Only days strictly after confirmation_data_from and not after today."""
    return {d: v for d, v in dv.items() if data_from < d <= today}


def _snapshot_hash(drv_raw, out_raw):
    """REQ-INF-307: identify the exact feature state that decided this — a hash of the
    post-window (day, value) pairs on both sides, in day order."""
    h = hashlib.sha256()
    for series in (drv_raw, out_raw):
        for d in sorted(series):
            h.update(f"{d.isoformat()}={series[d]!r};".encode())
        h.update(b"|")
    return h.hexdigest()


def _write_resolution(cur, core, h, status_to, reason, post_days, c, q, obs_dir,
                      look=None, n_eff=None, rho=None):
    cur.execute(f"UPDATE {core}.hypothesis_register SET status = %s WHERE hypothesis_id = %s",
                (status_to, h["hypothesis_id"]))
    cur.execute(f"""INSERT INTO {core}.hypothesis_resolutions
        (hypothesis_id, status_from, status_to, reason, post_days, n_hi, n_lo,
         delta, p_raw, q_fdr, family_m, registered_direction, observed_direction, code_version,
         look, n_eff, rho_outcome)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (h["hypothesis_id"], h["status"], status_to, reason, post_days,
         c[0] if c else None, c[1] if c else None,
         c[4] if c else None, c[5] if c else None, q, h.get("family_m"),
         h["direction"], obs_dir, CODE_VERSION, look, n_eff, rho))


def _write_forward_prediction(cur, core, h, q, snapshot_hash):
    """REQ-INF-301: a PROMOTED assignment inserts a forward prediction in the same
    transaction. claim = the registered sign on the NEXT window; resolution_rule = that
    same sign predicate (no q-gate: the claim and its rule are one predicate);
    p_forecast = 1 - Q_CONFIRM, a stated constant (ADR-0048 / OQ-44), never 1-q."""
    claim = (f"{h['exposure_metric']} -> {h['outcome_metric']} (lag {h['lag_days']}d): "
             f"median delta {h['direction']} on the next {FORWARD_DAYS} post-promotion days")
    rule = (f"quartile_contrast_mannwhitney median delta sign == {h['direction']} "
            f"on the {FORWARD_DAYS} panel days after resolved_at")
    cur.execute(f"""INSERT INTO {core}.predictions
        (hypothesis_id, claim_text, resolution_rule, resolves_at, evidence_tier,
         model_version, p_forecast, feature_snapshot_hash)
        VALUES (%s, %s, %s, clock_timestamp() + make_interval(days => %s), 'PROMOTED',
                %s, %s, %s)""",
        (h["hypothesis_id"], claim, rule, FORWARD_DAYS,
         CODE_VERSION, round(1.0 - Q_CONFIRM, 4), snapshot_hash))


def _kish_n_eff(post_days, rho):
    """Kish effective sample size; rho deflates only (scan's M2: a negative rho never inflates)."""
    r = max(0.0, rho)
    return round(post_days * (1 - r) / (1 + r), 1)


def run(cur, today=None, *, core="core", panel_schema="analysis"):
    """Evaluate every open watch at its due look. Returns run counts for the ops.runs heartbeat."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    cur.execute(f"""SELECT h.hypothesis_id, h.exposure_metric, h.outcome_metric, h.lag_days, h.direction,
                          h.confirmation_data_from, h.resolution_rule, h.status,
                          (SELECT count(*) FROM {core}.hypothesis_resolutions r
                            WHERE r.hypothesis_id = h.hypothesis_id AND r.reason = ANY(%s)) AS looks_done
                     FROM {core}.hypothesis_register h
                    WHERE h.hypothesis_id LIKE %s AND h.status = ANY(%s)
                      AND NOT EXISTS (SELECT 1 FROM {core}.hypothesis_resolutions r
                                       WHERE r.hypothesis_id = h.hypothesis_id
                                         AND r.reason = 'expired_no_decision_120d')
                    ORDER BY h.preregistered_at""",
                (list(LOOK_REASONS), "watch:%", list(OPEN_STATUSES)))
    # an expired watch keeps status INSUFFICIENT (the CHECK has no 'EXPIRED'); its expiry ledger
    # row is what closes it, here and in get_findings. looks_done counts the ledger rows that
    # recorded a look with no decision: 0 -> look 1 is due at MIN_POST_DAYS, 1 -> look 2 at
    # EXPIRE_DAYS, 2 cannot happen (look 2 always writes a final row).
    cols = ("hypothesis_id", "exposure_metric", "outcome_metric", "lag_days", "direction",
            "confirmation_data_from", "resolution_rule", "status", "looks_done")
    watches = [dict(zip(cols, r)) for r in cur.fetchall()]
    stats = {"looked": 0, "promoted": 0, "refuted": 0, "expired": 0,
             "undecided": 0, "waiting": 0, "on_clock": 0}
    if not watches:
        return stats
    panel = _load_panel(cur, schema=panel_schema)
    batch = []      # (h, c, post_days, snapshot_hash, look, n_eff, rho)
    for h in watches:
        data_from = h["confirmation_data_from"].date()
        calendar_days = (today - data_from).days
        drv_raw = _post_window(panel.get(h["exposure_metric"], {}), data_from, today)
        out_raw = _post_window(panel.get(h["outcome_metric"], {}), data_from, today)
        lag = dt.timedelta(days=h["lag_days"])
        post_days = sum(1 for d in drv_raw if (d + lag) in out_raw)
        look = h["looks_done"] + 1
        due = MIN_POST_DAYS if look == 1 else EXPIRE_DAYS
        if post_days < due:
            if look == 1 and calendar_days >= EXPIRE_DAYS:
                # the window never filled (metric gone, device silent): expire by the calendar,
                # otherwise it would be WATCHING forever (reviewer #10)
                _write_resolution(cur, core, h, "INSUFFICIENT", "expired_no_decision_120d",
                                  post_days, None, None, None, look=look)
                stats["expired"] += 1
            elif look == 1:
                stats["on_clock"] += 1      # REQ-INF-107: window_too_short, rule not evaluated
            else:
                stats["waiting"] += 1       # looked once, undecided; look 2 is due at EXPIRE_DAYS
            continue
        stats["looked"] += 1
        final = look >= 2 or post_days >= EXPIRE_DAYS      # look 2, or a first look already past day 120
        drv = _dow_demedian(drv_raw)
        out = _dow_demedian(out_raw)
        c = _contrast(drv, out, h["lag_days"], min_side=MIN_SIDE)
        rho = c[6] if c else None
        n_eff = _kish_n_eff(post_days, rho) if c else None
        if c is None or min(c[0], c[1]) < MIN_SIDE or n_eff < N_EFF_MIN:
            reason = "expired_no_decision_120d" if final else "insufficient_low_n_eff"
            _write_resolution(cur, core, h, "INSUFFICIENT", reason, post_days, c, None, None,
                              look=look, n_eff=n_eff, rho=rho)
            stats["expired" if final else "undecided"] += 1
            continue
        batch.append((h, c, post_days, _snapshot_hash(drv_raw, out_raw), look, n_eff, rho, final))
    if batch:
        qs = _bh([c[5] for _, c, _, _, _, _, _, _ in batch])
        for (h, c, post_days, snap, look, n_eff, rho, final), q in zip(batch, qs):
            h["family_m"] = len(batch)          # REQ-INF-106: the BH family size, persisted
            obs_dir = "positive" if c[4] > 0 else "negative"
            if q < Q_CONFIRM and obs_dir == h["direction"]:
                _write_resolution(cur, core, h, "PROMOTED", "promoted_same_sign_q_lt_0_10",
                                  post_days, c, q, obs_dir, look=look, n_eff=n_eff, rho=rho)
                _write_forward_prediction(cur, core, h, q, snap)
                stats["promoted"] += 1
            elif q < Q_CONFIRM and obs_dir != h["direction"]:
                _write_resolution(cur, core, h, "REFUTED", "refuted_opposite_sign_q_lt_0_10",
                                  post_days, c, q, obs_dir, look=look, n_eff=n_eff, rho=rho)
                stats["refuted"] += 1
            elif final:
                _write_resolution(cur, core, h, "INSUFFICIENT", "expired_no_decision_120d",
                                  post_days, c, q, obs_dir, look=look, n_eff=n_eff, rho=rho)
                stats["expired"] += 1
            else:
                _write_resolution(cur, core, h, "INSUFFICIENT", "insufficient_sign_unstable",
                                  post_days, c, q, obs_dir, look=look, n_eff=n_eff, rho=rho)
                stats["undecided"] += 1
    return stats
