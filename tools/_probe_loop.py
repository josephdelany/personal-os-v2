"""U5 rolled-back proof: Patterns surface (RULE-17/REQ-TIER-050..053) + Watch loop.
One transaction: 0031 applied, scan (stride=16) populates CANDIDATEs, then:
(1) get_patterns renders ONLY CANDIDATE-derived rows, every one labeled
    EXPLORATORY, calibration published;
(2) NO confirmed-tier verb in any rendered string (REQ-TIER-052 lint);
(3) other surfaces cannot reach CANDIDATE content (get_state/get_day never
    query hypothesis_register — asserted structurally);
(4) register_watch inserts a frozen registration; its prereg columns reject
    UPDATE; watching shows progress.
Rolled back — nothing persisted."""
import datetime as dt
import glob
import json
import re
import sys
from lib import db
from tools import run_migration
from tools.engines import scan

BANNED = re.compile(r"\b(precedes|predicts|predictive lead|causes|caused|proves|"
                    r"confirmed|established|robust)\b", re.I)

conn = db.connect(); cur = conn.cursor()
try:
    import glob as _g
    from tools import run_migration as _rm
    _sql = open(_g.glob("migrations/0033_*.sql")[0]).read().replace("__CORE__","core").replace("__OPS__","ops")
    for _st in _rm.split_statements(_sql):
        cur.execute(_st)
    sql = open(glob.glob("migrations/0031_*.sql")[0]).read() \
        .replace("__CORE__", "core").replace("__OPS__", "ops")
    for st in run_migration.split_statements(sql):
        cur.execute(st)
    stats = scan.run(cur, dt.date(2026, 9, 2), stride=16)
    print(f"(0) scan: {stats}")
    cur.execute("""select set_config('request.jwt.claims',
                   '{"email":"joseph.delany21@gmail.com"}', true)""")
    cur.execute("select public.get_patterns()")
    env = cur.fetchone()[0]; env = env if isinstance(env, dict) else json.loads(env)
    pats = env.get("patterns") or []
    all_labeled = all(p.get("label") == "EXPLORATORY" for p in pats)
    cal = env.get("calibration") or {}
    print(f"(1) patterns: {len(pats)}, all EXPLORATORY-labeled: {all_labeled}; "
          f"calibration published: {bool(cal.get('pairs_tested'))}")
    print("    sample:", (pats[0]["sentence"][:120] + "…") if pats else None)
    text = json.dumps(env)
    banned_hit = BANNED.search(text)
    print(f"(2) confirmed-tier verbs in payload: {banned_hit.group(0) if banned_hit else 'none'}")
    # (3) structural: the other read surfaces never touch hypothesis_register
    other = ""
    for f in ("0024_owner_lock.sql", "0029_timeline_api.sql", "0030_state_api.sql"):
        other += open(f"migrations/{f}").read()
    leak = "hypothesis_register" in other
    print(f"(3) day/state/insights surfaces reference hypothesis_register: {leak} (must be False)")
    # (4) the Watch loop
    hid = pats[0]["hypothesis_id"]
    cur.execute("select public.register_watch(%s)", (hid,))
    w = cur.fetchone()[0]; w = w if isinstance(w, dict) else json.loads(w)
    print(f"(4) watch registered: {w.get('watching')}")
    frozen = False
    cur.execute("SAVEPOINT f")
    try:
        cur.execute("update core.hypothesis_register set lag_days=99 where hypothesis_id=%s",
                    (w["watching"],))
    except Exception as e:
        frozen = True
        cur.execute("ROLLBACK TO SAVEPOINT f")
    cur.execute("select public.get_patterns()")
    env2 = cur.fetchone()[0]; env2 = env2 if isinstance(env2, dict) else json.loads(env2)
    p0 = next(p for p in env2["patterns"] if p["hypothesis_id"] == hid)
    print(f"    frozen: {frozen}; watched flag: {p0.get('watched')}; "
          f"progress: {p0.get('watch_progress')}")
    good = (len(pats) >= 5 and all_labeled and not banned_hit and not leak
            and frozen and p0.get("watched") is True)
    print("PROBE:", "ALL PASS" if good else "FAIL")
    sys.exit(0 if good else 1)
finally:
    conn.rollback(); conn.close(); print("rolled back — nothing persisted")
