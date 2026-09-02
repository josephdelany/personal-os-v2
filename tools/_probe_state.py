"""T3 rolled-back proof: timeline + state RPCs over the real corpus.
One transaction: 0026/0027/0029/0030 + legacy load + panel + baselines, then
get_timeline on a real 2025 day and get_state on a data-rich day; owner-lock
verified both ways (JWT email set in-tx to pass, absent to fail)."""
import glob
import json
import sys
from lib import db
from tools import run_migration
from tools.engines import panel, baselines

conn = db.connect(); cur = conn.cursor()
try:
    for pref in ("0026", "0027", "0029", "0030"):
        sql = open(glob.glob(f"migrations/{pref}_*.sql")[0]).read() \
            .replace("__CORE__", "core").replace("__OPS__", "ops")
        for st in run_migration.split_statements(sql):
            cur.execute(st)
    import csv
    from pathlib import Path
    CSV = Path.home() / "Documents/Claude/Projects/Personal Survilance/05_archive/daily_series.csv"
    COLS = ["hrv","rhr","resp","kcal","exmin","steps","asleep","inbed","deep","rem","core","awake","onset","wake_min"]
    DB = ["hrv","rhr","resp","kcal","exmin","steps","asleep","inbed","deep","rem","core_min","awake","onset","wake_min"]
    buf = []
    for r in csv.DictReader(open(CSV)):
        d = r["d"].strip(); vals = [float(r[c]) if r.get(c, "").strip() != "" else None for c in COLS]
        if d and any(v is not None for v in vals):
            buf.append([d] + vals)
    for i in range(0, len(buf), 500):
        ch = buf[i:i+500]; ph = ",".join(["(" + ",".join(["%s"]*15) + ")"] * len(ch))
        cur.execute(f"insert into analysis.legacy_daily (day,{','.join(DB)}) values " + ph,
                    [x for row in ch for x in row])
    panel.build(cur)
    baselines.compute(cur)

    # owner-lock: absent JWT must refuse
    denied = False
    cur.execute("SAVEPOINT p")
    try:
        cur.execute("select public.get_state('2026-07-27'::date)")
    except Exception as e:
        denied = "owner only" in str(e)
        cur.execute("ROLLBACK TO SAVEPOINT p")
    print(f"(1) no-JWT call refused: {denied}")

    # act as the owner for the rest of the transaction
    cur.execute("""select set_config('request.jwt.claims',
                   '{"email":"joseph.delany21@gmail.com"}', true)""")

    cur.execute("select public.get_timeline('2025-03-04'::date)")
    tl = cur.fetchone()[0]; tl = tl if isinstance(tl, dict) else json.loads(tl)
    print(f"(2) timeline 2025-03-04: {tl.get('n')} entries; first 3:")
    for e in (tl.get("entries") or [])[:3]:
        print(f"      {e['at']} [{e['kind']}] {e['text'][:70]}")

    cur.execute("select public.get_state('2026-07-27'::date)")
    st_ = cur.fetchone()[0]; st_ = st_ if isinstance(st_, dict) else json.loads(st_)
    dev = st_.get("deviations") or []
    print(f"(3) state 2026-07-27: {len(dev)} deviations; top:",
          {k: dev[0][k] for k in ("metric", "z", "value")} if dev else None)
    print(f"    streaks: {len(st_.get('streaks') or [])} · guardian: {bool(st_.get('guardian'))}"
          f" · week_money rows: {len(st_.get('week_money') or [])}")

    good = denied and (tl.get("n") or 0) > 5 and len(dev) >= 3
    print("PROBE:", "ALL PASS" if good else "FAIL")
    sys.exit(0 if good else 1)
finally:
    conn.rollback(); conn.close(); print("rolled back — nothing persisted")
