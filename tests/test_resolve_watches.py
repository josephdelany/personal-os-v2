"""The watch resolver (B7, migration 0042, ADR-0048): tools/engines/resolve.py.

RULE-01's bounded exception (ADR-0022): every row here is a fixture INSERTed into a DISPOSABLE
twin (core_pytest / ops_pytest / analysis_pytest) inside one transaction that is ROLLED BACK.
No real table is touched; no row survives. The series are deterministic integer sequences, not
random and not real data. Names carry the REQ/ADR IDs (DoD 1/3).

Run: python3 -m pytest tests/test_resolve_watches.py -v   (needs SUPABASE_DB_URL)
"""
import datetime as dt
import inspect
import json
import os
import re

import pytest

from lib import db
from tests._location_fixture import apply_chain, as_owner, CORE, ANALYSIS_TWIN
from tools.engines import resolve, scan

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL not set — these apply the migration chain to disposable twins",
)

TODAY = dt.date(2026, 9, 2)
RULE = "median delta same sign with q<0.10 on >=30 post-registration days"
OPEN = ("INSUFFICIENT", "PROMOTED")
FROZEN = ("exposure_metric", "outcome_metric", "lag_days", "direction", "transformation",
          "adjustment_set", "test_statistic", "preregistered_at", "confirmation_data_from",
          "resolution_rule")

# (watch id, exposure, outcome, registered direction, post days, pre days, shape)
#   shape 'same'     : outcome tracks exposure  (post window)  -> confirms a 'positive' registration
#   shape 'opposite' : outcome = 100 - exposure (post window)  -> refutes  a 'positive' registration
#   shape 'flat'     : exposure constant                        -> no contrast possible (q1 == q3)
# Pre-registration days ALWAYS carry the opposite pattern, strongly and in bulk, so that a resolver
# which read them would flip the sign (REQ-INF-107 is proven by the confirm case surviving them).
#   shape 'noise'    : outcome unrelated to exposure (p ~ 0.62 single-look) -> evaluated, not resolved
#   shape 'absent'   : no panel rows at all                                 -> window never fills
WATCHES = [
    ("watch:t.conf",   "t.x_conf",   "t.y_conf",   "positive", 45,  200, "same"),
    ("watch:t.ref",    "t.x_ref",    "t.y_ref",    "positive", 45,  200, "opposite"),
    ("watch:t.short",  "t.x_short",  "t.y_short",  "positive", 20,  200, "same"),
    ("watch:t.expire", "t.x_expire", "t.y_expire", "positive", 130, 0,   "flat"),
    ("watch:t.clock",  "t.x_clock",  "t.y_clock",  "positive", 60,  0,   "flat"),
    ("watch:t.noise",  "t.x_noise",  "t.y_noise",  "positive", 45,  0,   "noise"),
    ("watch:t.absent", "t.x_absent", "t.y_absent", "positive", 130, 0,   "absent"),
]


def _series(i, shape):
    x = float((i * 7) % 45)
    if shape == "flat":
        return 1.0, float(i % 10)
    if shape == "noise":
        return x, float((i * 13) % 17)
    y = x + float((i * 3) % 5) if shape == "same" else 100.0 - x
    return x, y


def _seed(cur):
    for wid, xm, ym, direction, n_post, n_pre, shape in WATCHES:
        d0 = TODAY - dt.timedelta(days=n_post + 1)
        cur.execute(f"""INSERT INTO {CORE}.hypothesis_register
            (hypothesis_id, exposure_metric, outcome_metric, lag_days, direction, transformation,
             adjustment_set, test_statistic, preregistered_at, confirmation_data_from,
             resolution_rule, status, mined_from_preexisting)
            VALUES (%s,%s,%s,0,%s,'dow_demedian','["day_of_week"]','quartile_contrast_mannwhitney',
                    %s,%s,%s,'INSUFFICIENT',false)""",
            (wid, xm, ym, direction,
             dt.datetime.combine(d0, dt.time(0, 0), dt.timezone.utc),
             dt.datetime.combine(d0, dt.time(0, 0), dt.timezone.utc), RULE))
        if shape == "absent":
            continue                            # a watch whose metrics never reach the panel
        rows = []
        for i in range(1, n_post + 1):
            x, y = _series(i, shape)
            rows += [(d0 + dt.timedelta(days=i), xm, x), (d0 + dt.timedelta(days=i), ym, y)]
        # the registration day itself (j = 0) and the days before it carry the OPPOSITE pattern, in
        # bulk: `day > confirmation_data_from` must exclude day 0 too (reviewer mutant M1)
        for j in range(0, n_pre + 1) if n_pre else ():
            x, y = _series(j + 1, "opposite" if shape == "same" else "same")
            rows += [(d0 - dt.timedelta(days=j), xm, x), (d0 - dt.timedelta(days=j), ym, y)]
        cur.execute(f"INSERT INTO {ANALYSIS_TWIN}.panel (day, metric, value, src, code_version) VALUES "
                    + ",".join(["(%s,%s,%s,'fixture','test')"] * len(rows)),
                    [x for r in rows for x in r])


@pytest.fixture(scope="module")
def conn():
    c = db.connect()
    cur = c.cursor()
    apply_chain(cur)
    cur.execute(f"""CREATE TABLE {ANALYSIS_TWIN}.panel (
        day DATE NOT NULL, metric TEXT NOT NULL, value NUMERIC NOT NULL,
        src TEXT NOT NULL, code_version TEXT NOT NULL, PRIMARY KEY (day, metric))""")
    as_owner(cur)
    _seed(cur)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture
def cur(conn):
    k = conn.cursor()
    k.execute("SAVEPOINT t")
    try:
        yield k
    finally:
        k.execute("ROLLBACK TO SAVEPOINT t")


def _run(cur):
    return resolve.run(cur, TODAY, core=CORE, panel_schema=ANALYSIS_TWIN)


def _status(cur, wid):
    cur.execute(f"SELECT status FROM {CORE}.hypothesis_register WHERE hypothesis_id=%s", (wid,))
    return cur.fetchone()[0]


def _ledger(cur, wid=None):
    q = (f"SELECT hypothesis_id, status_from, status_to, reason, post_days, n_hi, n_lo, delta, "
         f"p_raw, q_fdr, family_m, registered_direction, observed_direction, code_version "
         f"FROM {CORE}.hypothesis_resolutions")
    if wid:
        cur.execute(q + " WHERE hypothesis_id=%s", (wid,))
    else:
        cur.execute(q)
    cols = ("hypothesis_id", "status_from", "status_to", "reason", "post_days", "n_hi", "n_lo",
            "delta", "p_raw", "q_fdr", "family_m", "registered_direction", "observed_direction", "code_version")
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _findings(cur):
    cur.execute("select public.get_findings()")
    v = cur.fetchone()[0]
    return v if isinstance(v, dict) else json.loads(v)


def test_RULE_11_resolver_imports_contrast_from_scan_not_a_copy():
    assert resolve._contrast is scan._contrast
    assert resolve._bh is scan._bh
    assert resolve._mann_whitney_p is scan._mann_whitney_p
    assert resolve._dow_demedian is scan._dow_demedian
    assert resolve._load_panel is scan._load_panel
    assert resolve._median is scan._median and resolve._lag1_rho is scan._lag1_rho
    src = inspect.getsource(resolve)
    for name in ("_contrast", "_bh", "_mann_whitney_p", "_dow_demedian", "_load_panel", "_median"):
        assert not re.search(rf"^def {name}\(", src, re.M), f"{name} re-implemented in resolve.py"
    assert resolve.Q_CONFIRM == 0.10 and resolve.MIN_POST_DAYS == 30      # the frozen rule's numbers


def test_ADR_0048_watch_under_30_post_days_is_left_alone(cur):
    stats = _run(cur)
    assert stats["on_clock"] >= 1
    assert _status(cur, "watch:t.short") == "INSUFFICIENT"
    assert _ledger(cur, "watch:t.short") == []


def test_REQ_INF_107_resolver_ignores_days_before_confirmation_data_from(cur):
    # 200 pre-registration days carry the OPPOSITE sign in bulk; only the 45 post days agree with
    # the registration. Reading pre-registration data would refute; the rule confirms.
    _run(cur)
    assert _status(cur, "watch:t.conf") == "PROMOTED"
    (row,) = _ledger(cur, "watch:t.conf")
    assert row["post_days"] == 45                    # not 246 (200 pre days + day 0 + 45)
    assert row["observed_direction"] == "positive"
    cur.execute(f"SELECT count(*) FROM {ANALYSIS_TWIN}.panel WHERE metric='t.x_conf' AND day = "
                f"(SELECT confirmation_data_from::date FROM {CORE}.hypothesis_register WHERE hypothesis_id='watch:t.conf')")
    assert cur.fetchone()[0] == 1                    # day 0 exists in the panel and was excluded
    # and the direct check: the resolver's own window helper drops every pre-registration day
    cur.execute(f"SELECT confirmation_data_from FROM {CORE}.hypothesis_register WHERE hypothesis_id='watch:t.conf'")
    d0 = cur.fetchone()[0].date()
    panel = scan._load_panel(cur, schema=ANALYSIS_TWIN)
    win = resolve._post_window(panel["t.x_conf"], d0, TODAY)
    assert len(win) == 45 and min(win) > d0 and max(win) <= TODAY


def test_REQ_INF_103_resolver_changes_only_status(cur):
    cur.execute(f"SELECT hypothesis_id, {', '.join(FROZEN)} FROM {CORE}.hypothesis_register "
                f"WHERE hypothesis_id LIKE 'watch:%%' ORDER BY 1")
    before = cur.fetchall()
    stats = _run(cur)
    assert stats["promoted"] + stats["refuted"] + stats["expired"] >= 3   # changes did happen
    cur.execute(f"SELECT hypothesis_id, {', '.join(FROZEN)} FROM {CORE}.hypothesis_register "
                f"WHERE hypothesis_id LIKE 'watch:%%' ORDER BY 1")
    assert cur.fetchall() == before
    # the only UPDATE the resolver issues sets status and nothing else
    updates = re.findall(r"UPDATE\s+\{core\}\.hypothesis_register\s+SET\s+(.*?)\s+WHERE",
                         inspect.getsource(resolve), re.S)
    assert updates and all(u.strip() == "status = %s" for u in updates), updates
    # and the 0012 freeze trigger is what enforces it on the twin too
    with pytest.raises(Exception) as exc:
        cur.execute(f"UPDATE {CORE}.hypothesis_register SET lag_days = lag_days + 1 "
                    f"WHERE hypothesis_id='watch:t.conf'")
    assert "REQ-INF-103" in str(exc.value)
    cur.execute("ROLLBACK TO SAVEPOINT t")   # the raise aborted the subtransaction; restore for teardown
    cur.execute("SAVEPOINT t")


def test_ADR_0048_same_sign_q_below_0_10_promotes_and_writes_ledger_and_prediction(cur):
    # PROMOTED, not CONFIRMED_OBSERVATIONAL: REQ-TIER-013's gate (DAG adjustment set, HAC, E-value,
    # negative controls) is not built, so the causal tier is never assigned here (ADR-0048 amendment)
    stats = _run(cur)
    assert stats["promoted"] >= 1 and stats["evaluated"] == 5      # conf, ref, noise, expire, clock (>=30 paired days)
    assert _status(cur, "watch:t.conf") == "PROMOTED"
    cur.execute(f"SELECT count(*) FROM {CORE}.hypothesis_register WHERE status='CONFIRMED_OBSERVATIONAL'")
    assert cur.fetchone()[0] == 0
    (row,) = _ledger(cur, "watch:t.conf")
    assert row["status_from"] == "INSUFFICIENT" and row["status_to"] == "PROMOTED"
    assert row["reason"] == "promoted_same_sign_q_lt_0_10"
    assert float(row["q_fdr"]) < 0.10 and float(row["delta"]) > 0
    # BH was applied across the batch of three (REQ-INF-106): q is corrected, not the raw p
    assert row["family_m"] == 3
    assert float(row["p_raw"]) < float(row["q_fdr"]) <= 3 * float(row["p_raw"])
    assert row["registered_direction"] == row["observed_direction"] == "positive"
    assert min(row["n_hi"], row["n_lo"]) >= resolve.MIN_SIDE
    assert row["code_version"] == resolve.CODE_VERSION
    # REQ-INF-301 / RULE-20: a forward prediction in the same transaction
    cur.execute(f"""SELECT evidence_tier, model_version, p_forecast, outcome_bool, resolves_at > created_at,
                           resolution_rule, claim_text, forecast_distribution, feature_snapshot_hash
                      FROM {CORE}.predictions WHERE hypothesis_id='watch:t.conf'""")
    (p,) = cur.fetchall()
    assert p[0] == "PROMOTED" and p[1] == resolve.CODE_VERSION
    assert float(p[2]) == round(1.0 - resolve.Q_CONFIRM, 4) and p[3] is None and p[4] is True
    assert "positive" in p[5] and "t.x_conf -> t.y_conf" in p[6] and p[7] is None
    assert re.fullmatch(r"[0-9a-f]{64}", p[8])                     # REQ-INF-307: a real snapshot hash
    # surfaced: get_findings (twin) keeps it under watching (status PROMOTED), in history with the
    # claim named, and the prediction as pending; `confirmed` stays absent — nothing is confirmed
    env = _findings(cur)
    assert "confirmed" not in env
    w = {x["hypothesis_id"]: x for x in env["watching"]}
    assert w["watch:t.conf"]["status"] == "PROMOTED"
    hist = [h for h in env["history"] if h["hypothesis_id"] == "watch:t.conf"]
    assert len(hist) == 1 and hist[0]["tier"] == "PROMOTED"
    assert hist[0]["exposure"] == "t.x_conf" and hist[0]["outcome"] == "t.y_conf" and hist[0]["direction"] == "positive"
    assert hist[0]["trace"]["table"] == "core.hypothesis_resolutions" and hist[0]["reason"] == row["reason"]
    assert "watch:t.conf" in {p["hypothesis_id"] for p in env["predictions_pending"]}
    # the noise watch was evaluated and NOT resolved: no row, still open, still on the page
    assert _ledger(cur, "watch:t.noise") == [] and _status(cur, "watch:t.noise") == "INSUFFICIENT"
    assert "watch:t.noise" in w


def test_ADR_0048_opposite_sign_q_below_0_10_refutes(cur):
    stats = _run(cur)
    assert stats["refuted"] >= 1
    assert _status(cur, "watch:t.ref") == "REFUTED"
    (row,) = _ledger(cur, "watch:t.ref")
    assert row["reason"] == "refuted_opposite_sign_q_lt_0_10"
    assert float(row["q_fdr"]) < 0.10 and float(row["delta"]) < 0
    assert row["registered_direction"] == "positive" and row["observed_direction"] == "negative"
    cur.execute(f"SELECT count(*) FROM {CORE}.predictions WHERE hypothesis_id='watch:t.ref'")
    assert cur.fetchone()[0] == 0                       # REQ-INF-301 names PROMOTED/CONFIRMED/EXPERIMENTAL only
    env = _findings(cur)
    assert "watch:t.ref" in {r["hypothesis_id"] for r in env["refuted"]}
    assert "watch:t.ref" not in {w["hypothesis_id"] for w in env.get("watching", [])}


def test_ADR_0048_no_decision_after_120_days_expires_to_insufficient_with_reason(cur):
    stats = _run(cur)
    assert stats["expired"] == 2 and stats["still_watching"] == 2      # expire + absent; clock + noise
    assert _status(cur, "watch:t.expire") == "INSUFFICIENT"
    (row,) = _ledger(cur, "watch:t.expire")
    assert row["reason"] == "expired_no_decision_120d" and row["post_days"] >= resolve.EXPIRE_DAYS
    assert row["n_hi"] is None and row["q_fdr"] is None       # no contrast was possible: absent, not 0
    # 60 flat days: no decision yet, under 120 -> still on the clock, nothing written
    assert _status(cur, "watch:t.clock") == "INSUFFICIENT" and _ledger(cur, "watch:t.clock") == []
    env = _findings(cur)
    watching = {w["hypothesis_id"] for w in env.get("watching", [])}
    assert "watch:t.expire" not in watching and "watch:t.clock" in watching and "watch:t.short" in watching
    ins = {i["hypothesis_id"]: i for i in env["insufficient"]}
    assert ins["watch:t.expire"]["reason"] == "expired_no_decision_120d"
    assert env["counts"]["watching"] == len(env["watching"])


def test_REQ_TIER_043_every_status_change_has_a_ledger_row(cur):
    cur.execute(f"SELECT hypothesis_id, status FROM {CORE}.hypothesis_register WHERE hypothesis_id LIKE 'watch:%%'")
    before = dict(cur.fetchall())
    stats = _run(cur)
    cur.execute(f"SELECT hypothesis_id, status FROM {CORE}.hypothesis_register WHERE hypothesis_id LIKE 'watch:%%'")
    after = dict(cur.fetchall())
    ledger = _ledger(cur)
    by_id = {r["hypothesis_id"]: r for r in ledger}
    changed = {k for k in before if before[k] != after[k]}
    for wid in changed:
        assert wid in by_id and by_id[wid]["status_from"] == before[wid] and by_id[wid]["status_to"] == after[wid]
    assert len(ledger) == len(changed) + stats["expired"]        # expiry keeps INSUFFICIENT but is still recorded
    assert len(ledger) == len(set(by_id))                          # one row per change
    assert {r["reason"] for r in ledger} <= set(resolve.REASONS)
    # every change is surfaced by name — the claim (exposure, outcome, direction) and its reason (REQ-TIER-043)
    env = _findings(cur)
    assert {h["hypothesis_id"] for h in env["history"]} == set(by_id)
    for h in env["history"]:
        assert h["exposure"] and h["outcome"] and h["direction"] and h["reason"] and "tier" in h
    # idempotent: a second run changes nothing and writes nothing (a PROMOTED row is final for v1)
    stats2 = _run(cur)
    assert stats2["promoted"] == stats2["refuted"] == stats2["expired"] == 0
    assert len(_ledger(cur)) == len(ledger)
    # the ledger is append-only even for the owner (0012 trigger attached in 0042)
    with pytest.raises(Exception) as exc:
        cur.execute(f"DELETE FROM {CORE}.hypothesis_resolutions")
    assert "append-only" in str(exc.value)
    cur.execute("ROLLBACK TO SAVEPOINT t")
    cur.execute("SAVEPOINT t")


def test_ADR_0048_watch_whose_metrics_never_reach_the_panel_expires_by_the_calendar(cur):
    _run(cur)
    assert _status(cur, "watch:t.absent") == "INSUFFICIENT"
    (row,) = _ledger(cur, "watch:t.absent")
    assert row["reason"] == "expired_no_decision_120d" and row["post_days"] == 0
    assert row["n_hi"] is None and row["delta"] is None and row["q_fdr"] is None
    env = _findings(cur)
    assert "watch:t.absent" not in {w["hypothesis_id"] for w in env.get("watching", [])}
    assert {i["hypothesis_id"]: i["reason"] for i in env["insufficient"]}["watch:t.absent"] == "expired_no_decision_120d"
