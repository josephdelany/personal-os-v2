"""T2 rolled-back proof: analysis schema + legacy load + panel + baselines on
REAL data, all in one transaction, nothing persisted (RULE-01)."""
import sys
from lib import db
from tools import run_migration
from tools.engines import panel, baselines

conn = db.connect(); cur = conn.cursor()
try:
    import glob
    for pref in ("0026", "0027"):
        path = glob.glob(f"migrations/{pref}_*.sql")[0]
        sql = open(path).read().replace("__CORE__", "core").replace("__OPS__", "ops")
        for st in run_migration.split_statements(sql):
            cur.execute(st)
    # legacy load (inline, same logic as the parser)
    import csv
    from pathlib import Path
    CSV = Path.home() / "Documents/Claude/Projects/Personal Survilance/05_archive/daily_series.csv"
    COLS = ["hrv","rhr","resp","kcal","exmin","steps","asleep","inbed","deep","rem","core","awake","onset","wake_min"]
    DB = ["hrv","rhr","resp","kcal","exmin","steps","asleep","inbed","deep","rem","core_min","awake","onset","wake_min"]
    buf = []
    for r in csv.DictReader(open(CSV)):
        d = r["d"].strip()
        vals = [float(r[c]) if r.get(c, "").strip() != "" else None for c in COLS]
        if not d or all(v is None for v in vals):
            continue
        buf.append([d] + vals)
    for i in range(0, len(buf), 500):
        chunk = buf[i:i+500]
        ph = ",".join(["(" + ",".join(["%s"]*15) + ")"] * len(chunk))
        cur.execute(f"insert into analysis.legacy_daily (day,{','.join(DB)}) values " + ph,
                    [x for row in chunk for x in row])
    n = len(buf)
    print(f"(1) legacy loaded: {n} days (expect 2381)")

    np = panel.build(cur)
    cur.execute("select count(distinct metric), min(day), max(day) from analysis.panel")
    m, lo, hi = cur.fetchone()
    print(f"(2) panel: {np} rows, {m} metrics, {lo}..{hi}")

    # hand-checks against raw sources
    cur.execute("select value, src from analysis.panel where day='2019-09-04' and metric='steps'")
    r = cur.fetchone(); print(f"(3) steps 2019-09-04 = {r} (CSV says 4564.0, legacy_daily)")
    ok3 = r and float(r[0]) == 4564.0   # value matches CSV; two sources agree on it
    cur.execute("select value from analysis.panel where metric='hrv_sdnn' and src like 'signals%' limit 1")
    ok3b = cur.fetchone() is not None
    print(f"    signals-sourced hrv_sdnn present: {ok3b}")

    nb = baselines.compute(cur)
    cur.execute("""select count(*), count(*) filter (where abs(z_fast) >= 10)
                     from analysis.baselines where z_fast is not null
                    and metric in ('hrv_sdnn','rhr','steps','sleep_asleep_min',
                                   'screen_active_hours','sleep_efficiency')""")
    tot, wild = cur.fetchone()   # saturation among HEADLINE metrics only
    cur.execute("select max(abs(run_len)) from analysis.baselines")
    maxrun = cur.fetchone()[0]
    print(f"(4) baselines: {nb} rows; z_fast defined {tot}, |z|>10: {wild} ({100*wild/max(tot,1):.1f}%); max run_len {maxrun}")
    good = n == 2381 and np > 100000 and m >= 100 and ok3 and ok3b and nb > 50000 and wild/max(tot,1) < 0.05
    print("PROBE:", "ALL PASS" if good else "FAIL")
    sys.exit(0 if good else 1)
finally:
    conn.rollback(); conn.close(); print("rolled back — nothing persisted")
