#!/usr/bin/env python3
"""E11 — the watch resolver (ADR-0048, ADR-0049; docs/build/B7, B8).

`register_watch` inserts a pre-registered `watch:` row at status INSUFFICIENT and
starts the clock. This job is the only thing that moves it, and it moves it by the
row's own frozen `resolution_rule`, read through `rule_version` (ADR-0049 (i)):

  v1 (rows registered before migration 0045): "median delta same sign with q<0.10 on
     >=30 post-registration days" — q is BH across this run's batch; PROMOTED is final.
  v2 (rows registered by the 0045 `register_watch`): look 1 promotes on same sign,
     p<0.05, n_eff>=20; refutes on opposite sign, p<0.10; else sign_unstable, wait.
     Look 2 (120 paired days): a PROMOTED row is KEPT on same sign, p<0.10 over the
     post-promotion window (the days after its look-1 `look_day`), else demoted to
     INSUFFICIENT(sign_unstable); refuted on opposite sign, p<0.10; an INSUFFICIENT row
     at look 2 gets the look-1 criterion on the full post-registration window, else expires.

Common to both (REQ-TIER-017/018, RULE-21, ADR-0048 §12/§13, ADR-0049 (h) (j)):
  * only panel days strictly after `confirmation_data_from` are read (REQ-INF-107/104);
    the weekday demedian is computed on that window alone;
  * TWO LOOKS ONLY — look 1 on the first night with >= MIN_POST_DAYS paired days, look 2
    at >= EXPIRE_DAYS; every look writes one ledger row (`look`, `look_day`), so a look
    is never repeated. A degenerate contrast (exposure without spread) is not a look;
  * gates at every look, each ledgered with REQ-TIER-018's vocabulary in
    `insufficiency_reason`: coverage = post_days / calendar days since
    (confirmation_data_from + lag) < COVERAGE_MIN -> low_coverage; Kish
    n_eff = post_days*(1-rho)/(1+rho) on the PAIRED-DAY count (ruling (h)) < N_EFF_MIN ->
    low_n_eff; per-side minimum MIN_SIDE retained as a separate gate -> low_n_eff;
  * no look reached within EXPIRE_DAYS calendar days -> expired_no_decision_120d, final;
  * `analysis.watch_progress` is written every night for every open watch (the clock the
    surfaces render — paired days, never calendar days; `next_look` is a PROJECTION at one
    paired day per calendar day);
  * a PROMOTED assignment inserts one forward prediction (REQ-INF-301) with
    p_forecast = 0.5 until >= CALIBRATION_MIN scored resolutions exist, then the empirical
    replication rate (ruling (b)); B9 scores it at look 2 (ruling (a)).

Statistics are the scan's own helpers, imported (RULE-11/12). Deterministic, stdlib only.
Schema names are parameters so the tests run the identical code against disposable twins.
"""
import datetime as dt
import hashlib

from tools.engines import scan
from tools.engines.scan import (_load_panel, _dow_demedian, _contrast,   # noqa: F401 — imported, not copied
                                _mann_whitney_p, _lag1_rho, _median, _bh)

CODE_VERSION = "resolve-v2"
MIN_POST_DAYS = 30        # look 1: from the rule text
EXPIRE_DAYS = 120         # look 2 / expiry: from the rule text (ADR-0048)
MIN_SIDE = 7              # per-side floor, retained as a separate gate (ADR-0049 h)
N_EFF_MIN = 20            # REQ-TIER-017 floor, on the paired-day Kish n_eff (ADR-0049 h)
COVERAGE_MIN = 0.60       # REQ-TIER-017 coverage floor (ADR-0049 j)
Q_CONFIRM_V1 = 0.10       # v1 rule text
P_PROMOTE_V2 = 0.05       # v2 rule text, look 1 promote
P_DECIDE_V2 = 0.10        # v2 rule text, refute / look-2 keep
FORWARD_DAYS = 30         # the forward prediction's window (REQ-INF-301)
CALIBRATION_MIN = 20      # ruling (b): p_forecast is 0.5 until this many scored resolutions exist
LOOK_REASONS = ("insufficient_low_n_eff", "insufficient_sign_unstable", "insufficient_low_coverage",
                "kept_promoted_same_sign_p_lt_0_10")   # ledger rows that record a look without ending the watch

VOCAB = {   # resolver reason -> REQ-TIER-018 insufficiency_reason (ADR-0049 c)
    "insufficient_window_too_short": "window_too_short",
    "insufficient_low_n_eff": "low_n_eff",
    "insufficient_sign_unstable": "sign_unstable",
    "insufficient_low_coverage": "low_coverage",
    "expired_no_decision_120d": "window_too_short",
    "demoted_sign_unstable": "sign_unstable",
}
REASONS = ("promoted_same_sign_q_lt_0_10", "refuted_opposite_sign_q_lt_0_10",
           "promoted_same_sign_p_lt_0_05", "refuted_opposite_sign_p_lt_0_10",
           "kept_promoted_same_sign_p_lt_0_10", "demoted_sign_unstable",
           "insufficient_window_too_short", "insufficient_low_n_eff", "insufficient_sign_unstable",
           "insufficient_low_coverage", "expired_no_decision_120d")


def _post_window(dv, data_from, today):
    """Only days strictly after confirmation_data_from and not after today."""
    return {d: v for d, v in dv.items() if data_from < d <= today}


def _snapshot_hash(drv_raw, out_raw):
    h = hashlib.sha256()
    for series in (drv_raw, out_raw):
        for d in sorted(series):
            h.update(f"{d.isoformat()}={series[d]!r};".encode())
        h.update(b"|")
    return h.hexdigest()


def _kish_n_eff(post_days, rho):
    r = max(0.0, rho)
    return round(post_days * (1 - r) / (1 + r), 1)


def _outcome_rho(drv, out, lag):
    off = dt.timedelta(days=lag)
    ys = [out[d + off] for d in sorted(drv) if (d + off) in out]
    return _lag1_rho(ys) if ys else 0.0


def _paired_days(drv, out, lag):
    off = dt.timedelta(days=lag)
    return sum(1 for d in drv if (d + off) in out)


def _write_ledger(cur, core, h, status_to, reason, post_days, c, q, obs_dir, *,
                  look, n_eff, rho, coverage, look_day):
    if status_to != h["status"]:
        cur.execute(f"UPDATE {core}.hypothesis_register SET status = %s WHERE hypothesis_id = %s",
                    (status_to, h["hypothesis_id"]))
    cur.execute(f"""INSERT INTO {core}.hypothesis_resolutions
        (hypothesis_id, status_from, status_to, reason, insufficiency_reason, post_days, n_hi, n_lo,
         delta, p_raw, q_fdr, family_m, registered_direction, observed_direction, code_version,
         look, n_eff, rho_outcome, coverage, look_day)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (h["hypothesis_id"], h["status"], status_to, reason,
         VOCAB.get(reason) if status_to == "INSUFFICIENT" else None,
         post_days, c[0] if c else None, c[1] if c else None,
         c[4] if c else None, c[5] if c else None, q, h.get("family_m"),
         h["direction"], obs_dir, CODE_VERSION, look, n_eff, rho, coverage, look_day))
    h["status"] = status_to


def _p_forecast(cur, core):
    """Ruling (b): 0.5 until CALIBRATION_MIN scored resolve-* predictions exist, then the empirical
    replication rate. Returns (p, calibrated: bool)."""
    cur.execute(f"""SELECT count(*), avg(outcome_bool::int) FROM {core}.predictions
                     WHERE model_version LIKE 'resolve-%%' AND outcome_bool IS NOT NULL""")
    n, rate = cur.fetchone()
    if n >= CALIBRATION_MIN and rate is not None:
        return round(float(rate), 4), True
    return 0.5, False


def _write_forward_prediction(cur, core, h, q, snapshot_hash):
    p, calibrated = _p_forecast(cur, core)
    claim = (f"{h['exposure_metric']} -> {h['outcome_metric']} (lag {h['lag_days']}d): "
             f"median delta {h['direction']} on the next {FORWARD_DAYS} post-promotion days"
             + ("" if calibrated else
                f" [p_forecast 0.5: uninformative until the calibration ledger holds >= {CALIBRATION_MIN} scored resolutions]"))
    rule = (f"quartile_contrast_mannwhitney median delta sign == {h['direction']} and p < {P_DECIDE_V2} "
            f"on the post-promotion panel days at look 2")
    cur.execute(f"""INSERT INTO {core}.predictions
        (hypothesis_id, claim_text, resolution_rule, resolves_at, evidence_tier,
         model_version, p_forecast, feature_snapshot_hash)
        VALUES (%s, %s, %s, clock_timestamp() + make_interval(days => %s), 'PROMOTED',
                %s, %s, %s)""",
        (h["hypothesis_id"], claim, rule, EXPIRE_DAYS - MIN_POST_DAYS, CODE_VERSION, p, snapshot_hash))


def _write_progress(cur, schema, h, post_days, calendar_days, coverage, n_eff, c, next_look, look_done):
    cur.execute(f"""INSERT INTO {schema}.watch_progress
        (hypothesis_id, post_days, calendar_days, coverage, n_eff, n_hi, n_lo, next_look, look_done,
         code_version, computed_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, clock_timestamp())
        ON CONFLICT (hypothesis_id) DO UPDATE SET
            post_days = EXCLUDED.post_days, calendar_days = EXCLUDED.calendar_days,
            coverage = EXCLUDED.coverage, n_eff = EXCLUDED.n_eff, n_hi = EXCLUDED.n_hi,
            n_lo = EXCLUDED.n_lo, next_look = EXCLUDED.next_look, look_done = EXCLUDED.look_done,
            code_version = EXCLUDED.code_version, computed_at = EXCLUDED.computed_at""",
        (h["hypothesis_id"], post_days, calendar_days, coverage, n_eff,
         c[0] if c else None, c[1] if c else None, next_look, look_done, CODE_VERSION))


def _decide_v1(h, c, q, obs_dir, look, final):
    """v1 frozen text: q<0.10 same sign -> PROMOTED; opposite -> REFUTED; else wait / expire."""
    if q < Q_CONFIRM_V1 and obs_dir == h["direction"]:
        return "PROMOTED", "promoted_same_sign_q_lt_0_10"
    if q < Q_CONFIRM_V1:
        return "REFUTED", "refuted_opposite_sign_q_lt_0_10"
    return ("INSUFFICIENT", "expired_no_decision_120d") if final else ("INSUFFICIENT", "insufficient_sign_unstable")


def _decide_v2(h, c, p, obs_dir, look, final):
    """v2 text: look 1 promote p<0.05 same sign / refute p<0.10 opposite; look 2 keep PROMOTED on
    same sign p<0.10 else demote; refute p<0.10 opposite. An INSUFFICIENT row at look 2 gets the
    look-1 criterion, else expires (ADR-0049 reading)."""
    same = obs_dir == h["direction"]
    if h["status"] == "PROMOTED":
        if same and p < P_DECIDE_V2:
            return "PROMOTED", "kept_promoted_same_sign_p_lt_0_10"
        if (not same) and p < P_DECIDE_V2:
            return "REFUTED", "refuted_opposite_sign_p_lt_0_10"
        return "INSUFFICIENT", "demoted_sign_unstable"
    if same and p < P_PROMOTE_V2:
        return "PROMOTED", "promoted_same_sign_p_lt_0_05"
    if (not same) and p < P_DECIDE_V2:
        return "REFUTED", "refuted_opposite_sign_p_lt_0_10"
    return ("INSUFFICIENT", "expired_no_decision_120d") if final else ("INSUFFICIENT", "insufficient_sign_unstable")


def run(cur, today=None, *, core="core", panel_schema="analysis"):
    """Evaluate every open watch at its due look; write the clock for all. Returns run counts."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    cur.execute(f"""SELECT h.hypothesis_id, h.exposure_metric, h.outcome_metric, h.lag_days, h.direction,
                          h.confirmation_data_from, h.resolution_rule, h.status, h.rule_version,
                          coalesce((SELECT max(r.look) FROM {core}.hypothesis_resolutions r
                                     WHERE r.hypothesis_id = h.hypothesis_id), 0) AS looks_done,
                          (SELECT r.look_day FROM {core}.hypothesis_resolutions r
                            WHERE r.hypothesis_id = h.hypothesis_id AND r.status_to = 'PROMOTED'
                            ORDER BY r.resolved_at DESC LIMIT 1) AS promoted_on
                     FROM {core}.hypothesis_register h
                    WHERE h.hypothesis_id LIKE %s AND h.status IN ('INSUFFICIENT','PROMOTED')
                      AND NOT EXISTS (SELECT 1 FROM {core}.hypothesis_resolutions r
                                       WHERE r.hypothesis_id = h.hypothesis_id
                                         AND (r.status_to = 'REFUTED' OR r.reason = 'expired_no_decision_120d'))
                    ORDER BY h.preregistered_at""", ("watch:%",))
    cols = ("hypothesis_id", "exposure_metric", "outcome_metric", "lag_days", "direction",
            "confirmation_data_from", "resolution_rule", "status", "rule_version", "looks_done", "promoted_on")
    watches = [dict(zip(cols, r)) for r in cur.fetchall()]
    stats = {"open": len(watches), "looked": 0, "promoted": 0, "kept": 0, "demoted": 0, "refuted": 0,
             "expired": 0, "undecided": 0, "waiting": 0, "on_clock": 0, "not_evaluable": 0, "final_v1": 0}
    if not watches:
        return stats
    panel = _load_panel(cur, schema=panel_schema)
    batch = []      # (h, c, post_days, snapshot, look, n_eff, rho, coverage, final)
    for h in watches:
        data_from = h["confirmation_data_from"].date()
        lag_d = h["lag_days"]
        calendar_days = max(0, (today - data_from).days - lag_d)
        drv_raw = _post_window(panel.get(h["exposure_metric"], {}), data_from, today)
        out_raw = _post_window(panel.get(h["outcome_metric"], {}), data_from, today)
        drv = _dow_demedian(drv_raw) if drv_raw else {}
        out = _dow_demedian(out_raw) if out_raw else {}
        post_days = _paired_days(drv, out, lag_d)
        coverage = round(post_days / calendar_days, 3) if calendar_days else None
        rho = _outcome_rho(drv, out, lag_d) if post_days else 0.0
        n_eff = _kish_n_eff(post_days, rho)
        look = h["looks_done"] + 1
        due = MIN_POST_DAYS if look == 1 else EXPIRE_DAYS
        v1_final = h["rule_version"] == "v1" and h["status"] == "PROMOTED"   # v1: PROMOTED is final
        # v2 look 2 on a PROMOTED row tests the POST-PROMOTION window (ruling (a)), so it is due only once
        # that window itself holds MIN_POST_DAYS paired days — a promotion at a late first look must not be
        # re-looked the same night on an empty window
        promo_window = h["status"] == "PROMOTED" and h["rule_version"] == "v2" and h["promoted_on"] is not None
        post_promo = _paired_days({d: v for d, v in drv.items() if d > h["promoted_on"]}, out, lag_d) if promo_window else None
        if promo_window:
            due = max(EXPIRE_DAYS, post_days - post_promo + MIN_POST_DAYS)
        next_look = None if (look > 2 or v1_final) else (today + dt.timedelta(days=max(0, due - post_days)))
        c_all = _contrast(drv, out, lag_d, min_side=MIN_SIDE) if post_days >= MIN_POST_DAYS else None
        _write_progress(cur, panel_schema, h, post_days, calendar_days, coverage, n_eff, c_all,
                        next_look, h["looks_done"])
        if v1_final or look > 2:
            stats["final_v1" if v1_final else "waiting"] += 1
            continue
        if post_days < due:
            if promo_window:
                stats["waiting"] += 1       # a PROMOTED row waits for its post-promotion window; never calendar-expired
            elif calendar_days >= EXPIRE_DAYS:
                _write_ledger(cur, core, h, "INSUFFICIENT", "expired_no_decision_120d", post_days, None,
                              None, None, look=look, n_eff=n_eff, rho=rho, coverage=coverage, look_day=today)
                stats["expired"] += 1
            elif look == 1:
                stats["on_clock"] += 1      # REQ-INF-107 window_too_short: surfaced by _watching_rows, not ledgered
            else:
                stats["waiting"] += 1
            continue
        # the window this look tests: v2 look 2 on a PROMOTED row = the post-promotion days only (ruling (a))
        if h["rule_version"] == "v2" and h["status"] == "PROMOTED" and h["promoted_on"]:
            drv_t = {d: v for d, v in drv.items() if d > h["promoted_on"]}
            out_t = out
        else:
            drv_t, out_t = drv, out
        c = _contrast(drv_t, out_t, lag_d, min_side=MIN_SIDE)
        if c is None:
            if calendar_days >= EXPIRE_DAYS:
                _write_ledger(cur, core, h, "INSUFFICIENT", "expired_no_decision_120d", post_days, None,
                              None, None, look=look, n_eff=n_eff, rho=rho, coverage=coverage, look_day=today)
                stats["expired"] += 1
            else:
                stats["not_evaluable"] += 1     # not a test: no look spent
            continue
        stats["looked"] += 1
        final = look >= 2 or post_days >= EXPIRE_DAYS
        gate = None
        if coverage is not None and coverage < COVERAGE_MIN:
            gate = "insufficient_low_coverage"
        elif n_eff < N_EFF_MIN or min(c[0], c[1]) < MIN_SIDE:
            gate = "insufficient_low_n_eff"
        if gate:
            if final and h["status"] != "PROMOTED":
                gate = "expired_no_decision_120d"
            elif final:
                gate = "demoted_sign_unstable" if gate == "insufficient_sign_unstable" else gate
            _write_ledger(cur, core, h, "INSUFFICIENT", gate, post_days, c, None, None,
                          look=look, n_eff=n_eff, rho=rho, coverage=coverage, look_day=today)
            stats["expired" if gate == "expired_no_decision_120d" else ("demoted" if h["status"] == "INSUFFICIENT" and final else "undecided")] += 1
            continue
        batch.append((h, c, post_days, _snapshot_hash(drv_raw, out_raw), look, n_eff, rho, coverage, final))
    if batch:
        qs = _bh([c[5] for _, c, *_ in batch])
        for (h, c, post_days, snap, look, n_eff, rho, coverage, final), q in zip(batch, qs):
            h["family_m"] = len(batch)
            obs_dir = "positive" if c[4] > 0 else "negative"
            before = h["status"]
            if h["rule_version"] == "v1":
                status_to, reason = _decide_v1(h, c, q, obs_dir, look, final)
            else:
                status_to, reason = _decide_v2(h, c, c[5], obs_dir, look, final)
            _write_ledger(cur, core, h, status_to, reason, post_days, c, q, obs_dir,
                          look=look, n_eff=n_eff, rho=rho, coverage=coverage, look_day=today)
            if reason.startswith("promoted"):
                _write_forward_prediction(cur, core, h, q, snap); stats["promoted"] += 1
            elif reason.startswith("kept"):
                stats["kept"] += 1
            elif reason.startswith("demoted"):
                stats["demoted"] += 1
            elif reason.startswith("refuted"):
                stats["refuted"] += 1
            elif reason.startswith("expired"):
                stats["expired"] += 1
            else:
                stats["undecided"] += 1
    return stats
