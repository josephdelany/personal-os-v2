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
#   shape 'noise'    : outcome unrelated to exposure (p ~ 0.62 single-look) -> looked at, undecided
#   shape 'absent'   : no panel rows at all                                 -> window never fills
#   shape 'auto'     : outcome is a ramp (lag-1 rho -> 1)                   -> n_eff below the floor
#   shape 'late'     : noise for 45 days, then tracks exposure               -> undecided at look 1, decided at look 2
WATCHES = [
    ("watch:t.conf",   "t.x_conf",   "t.y_conf",   "positive", 45,  200, "same"),
    ("watch:t.ref",    "t.x_ref",    "t.y_ref",    "positive", 45,  200, "opposite"),
    ("watch:t.short",  "t.x_short",  "t.y_short",  "positive", 20,  200, "same"),
    ("watch:t.expire", "t.x_expire", "t.y_expire", "positive", 130, 0,   "flat"),
    ("watch:t.clock",  "t.x_clock",  "t.y_clock",  "positive", 60,  0,   "flat"),
    ("watch:t.noise",  "t.x_noise",  "t.y_noise",  "positive", 45,  0,   "noise"),
    ("watch:t.absent", "t.x_absent", "t.y_absent", "positive", 130, 0,   "absent"),
    ("watch:t.auto",   "t.x_auto",   "t.y_auto",   "positive", 45,  0,   "auto"),
    ("watch:t.late",   "t.x_late",   "t.y_late",   "positive", 130, 0,   "late"),
]
# v2 rows (rule_version 'v2', the 0045 register_watch template; ADR-0049 (i)):
#   'late2'  : tracks exposure for 45 days (promoted at look 1), then noise -> demoted at look 2
#   'sparse' : data on even days only over 61 calendar days -> coverage < 0.60 at look 1
WATCHES_V2 = [
    ("watch:v2.conf",   "v2.x_conf",   "v2.y_conf",   "positive", 45,  0, "same"),
    ("watch:v2.noise",  "v2.x_noise",  "v2.y_noise",  "positive", 45,  0, "noise"),
    ("watch:v2.auto",   "v2.x_auto",   "v2.y_auto",   "positive", 45,  0, "auto"),
    ("watch:v2.late2",  "v2.x_late2",  "v2.y_late2",  "positive", 130, 0, "late2"),
    ("watch:v2.sparse", "v2.x_sparse", "v2.y_sparse", "positive", 60,  0, "sparse"),
]
LATE_D0 = TODAY - dt.timedelta(days=131)
V2_RULE = ("Look 1 at the first night with >=30 paired post-registration days: promote if same sign as registered "
           "and p<0.05 with n_eff>=20; refute if opposite sign and p<0.10. Look 2 at day 120: keep PROMOTED only if "
           "same sign and p<0.10, else demote to INSUFFICIENT(sign_unstable); refute if opposite sign and p<0.10.")


def _series(i, shape):
    x = float((i * 7) % 45)
    if shape == "flat":
        return 1.0, float(i % 10)
    if shape == "noise" or (shape == "late" and i <= 45) or (shape == "late2" and i > 45):
        return x, float((i * 13) % 17)
    if shape == "auto":
        return x, float(i)
    y = x + float((i * 3) % 5) if shape in ("same", "late", "late2", "sparse") else 100.0 - x
    return x, y


def _seed(cur):
    for wid, xm, ym, direction, n_post, n_pre, shape, rv in \
            [w + ("v1",) for w in WATCHES] + [w + ("v2",) for w in WATCHES_V2]:
        d0 = TODAY - dt.timedelta(days=n_post + 1)
        assert shape not in ("late", "late2") or d0 == LATE_D0
        cur.execute(f"""INSERT INTO {CORE}.hypothesis_register
            (hypothesis_id, exposure_metric, outcome_metric, lag_days, direction, transformation,
             adjustment_set, test_statistic, preregistered_at, confirmation_data_from,
             resolution_rule, status, mined_from_preexisting, rule_version)
            VALUES (%s,%s,%s,0,%s,'dow_demedian','["day_of_week"]','quartile_contrast_mannwhitney',
                    %s,%s,%s,'INSUFFICIENT',false,%s)""",
            (wid, xm, ym, direction,
             dt.datetime.combine(d0, dt.time(0, 0), dt.timezone.utc),
             dt.datetime.combine(d0, dt.time(0, 0), dt.timezone.utc), RULE if rv == "v1" else V2_RULE, rv))
        if shape == "absent":
            continue                            # a watch whose metrics never reach the panel
        rows = []
        for i in range(1, n_post + 1):
            if shape == "sparse" and i % 2:
                continue                        # every other day missing -> coverage ~0.49
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


def _run(cur, today=TODAY):
    return resolve.run(cur, today, core=CORE, panel_schema=ANALYSIS_TWIN)


def _status(cur, wid):
    cur.execute(f"SELECT status FROM {CORE}.hypothesis_register WHERE hypothesis_id=%s", (wid,))
    return cur.fetchone()[0]


def _ledger(cur, wid=None):
    q = (f"SELECT hypothesis_id, status_from, status_to, reason, post_days, n_hi, n_lo, delta, "
         f"p_raw, q_fdr, family_m, registered_direction, observed_direction, code_version, "
         f"look, n_eff, rho_outcome, insufficiency_reason, coverage, look_day FROM {CORE}.hypothesis_resolutions")
    if wid:
        cur.execute(q + " WHERE hypothesis_id=%s", (wid,))
    else:
        cur.execute(q)
    cols = ("hypothesis_id", "status_from", "status_to", "reason", "post_days", "n_hi", "n_lo",
            "delta", "p_raw", "q_fdr", "family_m", "registered_direction", "observed_direction", "code_version",
            "look", "n_eff", "rho_outcome", "insufficiency_reason", "coverage", "look_day")
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
    assert resolve.Q_CONFIRM_V1 == 0.10 and resolve.MIN_POST_DAYS == 30   # the v1 frozen rule's numbers
    assert resolve.P_PROMOTE_V2 == 0.05 and resolve.P_DECIDE_V2 == 0.10 and resolve.COVERAGE_MIN == 0.60
    assert resolve.N_EFF_MIN == 20 and resolve.EXPIRE_DAYS == 120           # REQ-TIER-017 floor; look 2


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
    # looked: conf, ref, noise, auto, late (>=30 paired days AND a contrast possible);
    # expire/clock are flat exposures: no contrast, no look spent (reviewer #4)
    # v1: conf + late (first look past 120) promote; v2: conf promotes, late2 promotes at its first look (past 120,
    # so final: kept? no — an INSUFFICIENT row at a final first look gets the look-1 criterion: it promotes)
    assert stats["promoted"] == 4 and stats["not_evaluable"] == 1                    # clock: flat exposure
    assert stats["looked"] == 10          # v1: conf ref noise auto late · v2: conf noise auto late2 sparse
    assert _status(cur, "watch:t.conf") == "PROMOTED"
    cur.execute(f"SELECT count(*) FROM {CORE}.hypothesis_register WHERE status='CONFIRMED_OBSERVATIONAL'")
    assert cur.fetchone()[0] == 0
    (row,) = _ledger(cur, "watch:t.conf")
    assert row["status_from"] == "INSUFFICIENT" and row["status_to"] == "PROMOTED"
    assert row["reason"] == "promoted_same_sign_q_lt_0_10"
    assert float(row["q_fdr"]) < 0.10 and float(row["delta"]) > 0
    # BH was applied across the batch (REQ-INF-106): q is corrected, not the raw p
    assert row["family_m"] == 7                                   # v1 conf ref noise late + v2 conf noise late2; auto/sparse gated before BH
    assert float(row["p_raw"]) < float(row["q_fdr"]) <= 7 * float(row["p_raw"])
    assert row["look_day"] == TODAY and row["coverage"] is not None and float(row["coverage"]) >= 0.6
    assert row["look"] == 1 and float(row["n_eff"]) >= resolve.N_EFF_MIN      # stored and gated (RULE-21)
    assert row["registered_direction"] == row["observed_direction"] == "positive"
    assert min(row["n_hi"], row["n_lo"]) >= resolve.MIN_SIDE
    assert row["code_version"] == resolve.CODE_VERSION
    # REQ-INF-301 / RULE-20: a forward prediction in the same transaction
    cur.execute(f"""SELECT evidence_tier, model_version, p_forecast, outcome_bool, resolves_at > created_at,
                           resolution_rule, claim_text, forecast_distribution, feature_snapshot_hash
                      FROM {CORE}.predictions WHERE hypothesis_id='watch:t.conf'""")
    (p,) = cur.fetchall()
    assert p[0] == "PROMOTED" and p[1] == resolve.CODE_VERSION
    assert float(p[2]) == 0.5 and p[3] is None and p[4] is True           # ruling (b): uninformative until calibrated
    assert "uninformative until the calibration ledger holds >= 20" in p[6]
    assert "positive" in p[5] and "t.x_conf -> t.y_conf" in p[6] and p[7] is None
    assert re.fullmatch(r"[0-9a-f]{64}", p[8])                     # REQ-INF-307: a real snapshot hash
    # surfaced: get_findings (twin) keeps it under watching (status PROMOTED), in history with the
    # claim named, and the prediction as pending; `confirmed` stays absent — nothing is confirmed
    env = _findings(cur)
    assert "confirmed" not in env
    w = {x["hypothesis_id"]: x for x in env["watching"]}
    # ruling (f): the watching predicate is status IN (INSUFFICIENT, PROMOTED) minus refuted/expired, so a
    # PROMOTED row stays under watch (v2: until its look 2); it is ALSO in the promoted list
    assert w["watch:t.conf"]["status"] == "PROMOTED" and w["watch:t.conf"]["post_days"] == 45
    pr = {x["hypothesis_id"]: x for x in env["promoted"]}
    assert pr["watch:t.conf"]["tier"] == "PROMOTED" and "not a causal claim" in pr["watch:t.conf"]["note"]
    assert env["counts"]["watching"] == len(env["watching"])
    hist = [h for h in env["history"] if h["hypothesis_id"] == "watch:t.conf"]
    assert len(hist) == 1 and hist[0]["tier"] == "PROMOTED"
    assert hist[0]["exposure"] == "t.x_conf" and hist[0]["outcome"] == "t.y_conf" and hist[0]["direction"] == "positive"
    assert hist[0]["trace"]["table"] == "core.hypothesis_resolutions" and hist[0]["reason"] == row["reason"]
    assert "watch:t.conf" in {p["hypothesis_id"] for p in env["predictions_pending"]}
    # the noise watch was looked at and NOT resolved: one look row, still open, still on the page
    (nz,) = _ledger(cur, "watch:t.noise")
    assert nz["reason"] == "insufficient_sign_unstable" and nz["look"] == 1 and nz["status_to"] == "INSUFFICIENT"
    assert _status(cur, "watch:t.noise") == "INSUFFICIENT" and w["watch:t.noise"]["looks_done"] == 1
    assert w["watch:t.noise"]["days_needed"] == 120 and w["watch:t.noise"]["last_look_reason"] == nz["reason"]
    assert w["watch:t.short"]["looks_done"] == 0 and w["watch:t.short"]["days_needed"] == 30
    assert w["watch:t.short"]["insufficiency_reason"] == "window_too_short"       # REQ-INF-107
    # history: every row that reports post_days reports n_eff (RULE-21), and says whether status changed
    for hrow in env["history"]:
        assert "n_eff" in hrow and "status_changed" in hrow, hrow


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
    assert stats["expired"] == 2 and stats["undecided"] == 5      # expire + absent; v1 noise auto · v2 noise auto sparse
    assert _status(cur, "watch:t.expire") == "INSUFFICIENT"
    (row,) = _ledger(cur, "watch:t.expire")
    assert row["reason"] == "expired_no_decision_120d" and row["post_days"] >= resolve.EXPIRE_DAYS
    assert row["n_hi"] is None and row["q_fdr"] is None       # no contrast was possible: absent, not 0
    assert row["n_eff"] is not None                            # but n_eff is (RULE-21)
    # 60 flat days: no contrast possible -> not a look, nothing written, re-checked nightly (reviewer #4)
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
    assert len(ledger) == len(changed) + stats["expired"] + stats["undecided"] + stats["kept"]   # looks are recorded too
    assert len(ledger) == len(set(by_id))                          # one row per watch in a single run
    assert {r["reason"] for r in ledger} <= set(resolve.REASONS)
    # every change is surfaced by name — the claim (exposure, outcome, direction) and its reason (REQ-TIER-043)
    env = _findings(cur)
    assert {h["hypothesis_id"] for h in env["history"]} == set(by_id)
    for h in env["history"]:
        assert h["exposure"] and h["outcome"] and h["direction"] and h["reason"] and "tier" in h
    # idempotent: a second run the same night changes nothing and writes nothing (a look is never repeated)
    stats2 = _run(cur)
    assert stats2["looked"] == stats2["promoted"] == stats2["refuted"] == stats2["expired"] == stats2["undecided"] == 0
    # REQ-TIER-018: every INSUFFICIENT ledger row carries a vocabulary reason
    for r in ledger:
        if r["status_to"] == "INSUFFICIENT":
            assert r["insufficiency_reason"] in ("low_coverage", "low_n_eff", "informative_missingness",
                                                 "no_adjustment_set", "sign_unstable", "metric_absent", "window_too_short"), r
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


def test_OQ_44d_a_look_is_never_repeated_two_looks_only(cur):
    # night 1: the noise watch gets its first look and is undecided
    s1 = _run(cur)
    assert s1["undecided"] >= 1
    (r1,) = _ledger(cur, "watch:t.noise")
    assert r1["reason"] == "insufficient_sign_unstable" and r1["look"] == 1
    # the same night again, and every night for the next 60 days: no second look before 120 paired days
    for offset in (0, 1, 30, 60):
        s = _run(cur, TODAY + dt.timedelta(days=offset))
        assert s["looked"] == 0 and s["waiting"] >= 1, offset
        assert len(_ledger(cur, "watch:t.noise")) == 1
    assert _status(cur, "watch:t.noise") == "INSUFFICIENT"
    env = _findings(cur)
    assert {w["hypothesis_id"]: w["looks_done"] for w in env["watching"]}["watch:t.noise"] == 1


def test_OQ_44d_second_look_at_120_paired_days_decides_or_expires(cur):
    # look 1 at day 45: the first 45 days are noise -> undecided
    s1 = _run(cur, LATE_D0 + dt.timedelta(days=45))
    (r1,) = _ledger(cur, "watch:t.late")
    assert r1["look"] == 1 and r1["reason"] == "insufficient_sign_unstable" and r1["post_days"] == 45
    # nights in between: waiting, nothing written
    s_mid = _run(cur, LATE_D0 + dt.timedelta(days=100))
    assert len(_ledger(cur, "watch:t.late")) == 1
    # look 2 at 130 paired days: the rule is met on the full post window -> PROMOTED, final
    s2 = _run(cur, TODAY)
    rows = sorted(_ledger(cur, "watch:t.late"), key=lambda r: r["look"])
    assert [r["look"] for r in rows] == [1, 2]
    assert rows[1]["reason"] == "promoted_same_sign_q_lt_0_10" and rows[1]["post_days"] == 130
    assert _status(cur, "watch:t.late") == "PROMOTED"
    # a watch whose data stops AFTER look 1 expires by the calendar too (reviewer #5): the noise watch has
    # one look and only 45 panel days; 200 days later it must not still be 'waiting'
    s3 = _run(cur, TODAY + dt.timedelta(days=200))
    rows = sorted(_ledger(cur, "watch:t.noise"), key=lambda r: r["look"])
    assert [r["reason"] for r in rows] == ["insufficient_sign_unstable", "expired_no_decision_120d"]
    assert rows[1]["look"] == 2 and rows[1]["n_eff"] is not None
    env = _findings(cur)
    assert "watch:t.noise" not in {w["hypothesis_id"] for w in env.get("watching", [])}
    # and a watch undecided at look 2 itself expires there: replay t.noise's second look on its own data
    # (45 paired days never reach 120, so that branch is the calendar one above; the in-look final
    #  branch is covered by t.late's first look past day 120 in the promote test)


def test_REQ_TIER_017_low_n_eff_is_stored_and_gated_to_insufficient(cur):
    _run(cur)
    (row,) = _ledger(cur, "watch:t.auto")
    assert row["reason"] == "insufficient_low_n_eff" and row["look"] == 1
    assert row["n_eff"] is not None and float(row["n_eff"]) < resolve.N_EFF_MIN
    assert float(row["rho_outcome"]) > 0.5 and row["post_days"] == 45
    assert _status(cur, "watch:t.auto") == "INSUFFICIENT"
    env = _findings(cur)
    (h,) = [x for x in env["history"] if x["hypothesis_id"] == "watch:t.auto"]
    assert h["look"] == 1 and "n_eff" in h and h["post_days"] == 45        # RULE-21: n never without n_eff


# ---------------------------------------------------------------- B8 / ADR-0049 ----------------------------------

def test_ADR_0049_v1_rows_keep_v1_semantics(cur):
    _run(cur)
    cur.execute(f"SELECT rule_version FROM {CORE}.hypothesis_register WHERE hypothesis_id='watch:t.conf'")
    assert cur.fetchone()[0] == "v1"
    (row,) = _ledger(cur, "watch:t.conf")
    assert row["reason"] == "promoted_same_sign_q_lt_0_10"          # the v1 sentence, q-gated, not p<0.05
    # a v1 PROMOTED row is final: replayed a year on it is neither re-looked nor expired
    s = _run(cur, TODAY + dt.timedelta(days=365))
    assert len(_ledger(cur, "watch:t.conf")) == 1 and _status(cur, "watch:t.conf") == "PROMOTED"
    assert s["final_v1"] >= 1


def test_ADR_0049_v2_look1_requires_p_lt_0_05_and_n_eff_20(cur):
    _run(cur)
    (c,) = _ledger(cur, "watch:v2.conf")
    assert c["reason"] == "promoted_same_sign_p_lt_0_05" and float(c["p_raw"]) < 0.05 and float(c["n_eff"]) >= 20
    assert _status(cur, "watch:v2.conf") == "PROMOTED"
    (n,) = _ledger(cur, "watch:v2.noise")                            # p ~ 0.6: not promoted, waits
    assert n["reason"] == "insufficient_sign_unstable" and n["insufficiency_reason"] == "sign_unstable"
    (a,) = _ledger(cur, "watch:v2.auto")                             # n_eff < 20: gated before any decision
    assert a["reason"] == "insufficient_low_n_eff" and a["insufficiency_reason"] == "low_n_eff" and float(a["n_eff"]) < 20
    cur.execute(f"SELECT resolution_rule FROM {CORE}.hypothesis_register WHERE hypothesis_id='watch:v2.conf'")
    assert "p<0.05 with n_eff>=20" in cur.fetchone()[0]


def test_ADR_0049_v2_look2_demotes_sign_unstable(cur):
    # look 1 at day 45: the first 45 days track the exposure -> PROMOTED, look_day recorded
    _run(cur, LATE_D0 + dt.timedelta(days=45))
    (r1,) = _ledger(cur, "watch:v2.late2")
    assert r1["reason"] == "promoted_same_sign_p_lt_0_05" and r1["look"] == 1
    assert r1["look_day"] == LATE_D0 + dt.timedelta(days=45)
    # look 2 at 130 paired days: the post-promotion window is noise -> demoted, INSUFFICIENT(sign_unstable)
    s2 = _run(cur, TODAY)
    rows = sorted(_ledger(cur, "watch:v2.late2"), key=lambda r: r["look"])
    assert [r["look"] for r in rows] == [1, 2]
    assert rows[1]["reason"] == "demoted_sign_unstable" and rows[1]["insufficiency_reason"] == "sign_unstable"
    assert rows[1]["status_from"] == "PROMOTED" and rows[1]["status_to"] == "INSUFFICIENT"
    assert _status(cur, "watch:v2.late2") == "INSUFFICIENT" and s2["demoted"] >= 1
    # the demotion is surfaced by name (REQ-TIER-043) and the row has left the promoted list
    env = _findings(cur)
    assert "watch:v2.late2" not in {p["hypothesis_id"] for p in env.get("promoted", [])}
    assert any(h["hypothesis_id"] == "watch:v2.late2" and h["reason"] == "demoted_sign_unstable" for h in env["history"])


def test_REQ_TIER_017_low_coverage_is_insufficient_with_reason(cur):
    _run(cur)
    (r,) = _ledger(cur, "watch:v2.sparse")
    assert r["reason"] == "insufficient_low_coverage" and r["insufficiency_reason"] == "low_coverage"
    assert float(r["coverage"]) < 0.60 and r["post_days"] >= 30
    assert _status(cur, "watch:v2.sparse") == "INSUFFICIENT"
    env = _findings(cur)
    w = {x["hypothesis_id"]: x for x in env["watching"]}
    assert float(w["watch:v2.sparse"]["coverage"]) < 0.60 and w["watch:v2.sparse"]["last_look_reason"] == "insufficient_low_coverage"


def test_RULE_12_three_surfaces_report_identical_watching_sets(cur):
    _run(cur)
    env = _findings(cur)
    findings_ids = {w["hypothesis_id"] for w in env["watching"]}
    cur.execute("select public.get_today()")
    today = cur.fetchone()[0]; today = today if isinstance(today, dict) else json.loads(today)
    today_ids = {w["hypothesis_id"] for w in today["watching"]}
    cur.execute("select public.get_trust()")
    trust = cur.fetchone()[0]; trust = trust if isinstance(trust, dict) else json.loads(trust)
    assert findings_ids == today_ids and len(findings_ids) == env["counts"]["watching"] == trust["hypotheses"]["watching"]
    # refuted and expired rows are in none of them; PROMOTED-under-watch rows are in all of them
    assert "watch:t.ref" not in findings_ids and "watch:t.expire" not in findings_ids
    assert "watch:v2.conf" in findings_ids
    # the clock is paired days from the resolver's own table, never calendar days
    t = {w["hypothesis_id"]: w for w in today["watching"]}
    assert t["watch:t.short"]["day"] == 20 and t["watch:t.short"]["of"] == 30 and "next look" in t["watch:t.short"]["text"]
    cur.execute(f"SELECT post_days, coverage, n_eff FROM {ANALYSIS_TWIN}.watch_progress WHERE hypothesis_id='watch:t.short'")
    assert cur.fetchone()[0] == 20


def test_REQ_TIER_018_every_insufficient_ledger_row_has_vocabulary_reason(cur):
    _run(cur, LATE_D0 + dt.timedelta(days=45)); _run(cur); _run(cur, TODAY + dt.timedelta(days=200))
    rows = _ledger(cur)
    assert rows
    for r in rows:
        if r["status_to"] == "INSUFFICIENT":
            assert r["insufficiency_reason"] in ("low_coverage", "low_n_eff", "informative_missingness",
                                                 "no_adjustment_set", "sign_unstable", "metric_absent", "window_too_short"), r
        else:
            assert r["insufficiency_reason"] is None, r
    assert {r["insufficiency_reason"] for r in rows if r["status_to"] == "INSUFFICIENT"} >= {"low_coverage", "low_n_eff", "sign_unstable", "window_too_short"}
