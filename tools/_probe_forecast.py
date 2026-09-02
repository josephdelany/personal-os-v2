"""U8 rolled-back proof: forecasts + resolution + today/trust envelopes.
Backtests by issuing a forecast for a PAST day with known actual, resolving it,
then reading get_today/get_trust. Rolled back — nothing persisted."""
import datetime as dt
import glob
import json
import sys
from lib import db
from tools import run_migration
from tools.engines import forecast

conn = db.connect(); cur = conn.cursor()
try:
    sql = open(glob.glob("migrations/0032_*.sql")[0]).read() \
        .replace("__CORE__", "core").replace("__OPS__", "ops")
    for st in run_migration.split_statements(sql):
        cur.execute(st)
    # issue for tomorrow (live path)
    n = forecast.run(cur)
    cur.execute("select metric, lo, point, hi from analysis.forecasts order by metric")
    fcs = cur.fetchall()
    print(f"(1) forecasts issued for tomorrow: {n}")
    for m, lo, pt, hi in fcs:
        print(f"    {m}: {lo} .. {pt} .. {hi}")
    # backtest: forecast a past day (bands only), then a REQ-INF-303-legal
    # prediction that matures seconds later and resolves against the known actual
    cur.execute("""select day from analysis.panel
                    where metric in ('sleep_asleep_min','hrv_sdnn','rhr','steps')
                    group by day having count(distinct metric) = 4
                    order by day desc limit 1""")
    past = cur.fetchone()[0]
    forecast.run(cur, target_day=past, write_predictions=False)
    cur.execute("""insert into core.predictions
                   (claim_text, resolution_rule, resolves_at, evidence_tier,
                    p_forecast, model_version)
                   select f.metric || ' on ' || f.day_target || ' within [' || f.lo || ', ' || f.hi || ']',
                          'panel value in band', now() + interval '1 second',
                          'DESCRIPTIVE', 0.90, 'forecast-v1'
                     from analysis.forecasts f where f.day_target = %s""", (past,))
    cur.execute("select pg_sleep(1.5)")
    n_res, n_unres = forecast.resolve(cur)
    cur.execute("""select claim_text, outcome_bool, brier from core.predictions
                    where outcome_bool is not null limit 5""")
    print(f"(2) backtest {past}: resolved {n_res} (unresolvable {n_unres})")
    for r in cur.fetchall():
        print(f"    {r[0][:60]}… -> inside={r[1]} brier={round(float(r[2]),3)}")
    cur.execute("""select set_config('request.jwt.claims',
                   '{"email":"joseph.delany21@gmail.com"}', true)""")
    cur.execute("select public.get_today()")
    t = cur.fetchone()[0]; t = t if isinstance(t, dict) else json.loads(t)
    print(f"(3) get_today keys: {sorted(t.keys())}")
    print(f"    connection: {str((t.get('connection') or {}).get('sentence'))[:100]}")
    cur.execute("select public.get_trust()")
    tr = cur.fetchone()[0]; tr = tr if isinstance(tr, dict) else json.loads(tr)
    print(f"(4) trust: forecasts={tr.get('forecasts')} · hypotheses={tr.get('hypotheses')}")
    good = n >= 3 and n_res >= 3 and "state" in t and tr.get("forecasts") is not None
    print("PROBE:", "ALL PASS" if good else "FAIL")
    sys.exit(0 if good else 1)
finally:
    conn.rollback(); conn.close(); print("rolled back — nothing persisted")
