"""U5 rolled-back proof: the contrast scan on the LIVE panel (stride-sampled
discovery + all seeds), CANDIDATE registration, calibration ledger — one
transaction, rolled back, nothing persisted."""
import datetime as dt
import sys
from lib import db
from tools.engines import scan

conn = db.connect(); cur = conn.cursor()
try:
    stats = scan.run(cur, dt.date(2026, 9, 2), stride=8)
    print(f"(1) scan: {stats}")
    cur.execute("""select driver, outcome, lag_days, seeded, round(delta::numeric,2),
                          n_hi, n_lo, round(q_fdr::numeric,4)
                     from analysis.contrasts order by q_fdr limit 10""")
    print("(2) top contrasts:")
    for r in cur.fetchall():
        print(f"    {r[0]} -> {r[1]} (lag {r[2]}{', seeded' if r[3] else ''}): "
              f"delta {r[4]}, n {r[5]}/{r[6]}, q={r[7]}")
    cur.execute("select count(*) from core.hypothesis_register where status='CANDIDATE'")
    ncand = cur.fetchone()[0]
    cur.execute("select observed_sig, null_sig, n_pairs_tested from analysis.scan_calibration")
    cal = cur.fetchone()
    print(f"(3) CANDIDATE rows: {ncand} · calibration: observed {cal[0]} vs null {cal[1]} of {cal[2]}")
    # freeze trigger: a CANDIDATE row's prereg columns must reject UPDATE
    cur.execute("select hypothesis_id from core.hypothesis_register where status='CANDIDATE' limit 1")
    hid = cur.fetchone()[0]
    frozen = False
    cur.execute("SAVEPOINT f")
    try:
        cur.execute("update core.hypothesis_register set lag_days = 99 where hypothesis_id=%s", (hid,))
    except Exception as e:
        frozen = "frozen" in str(e).lower() or "REQ-INF-103" in str(e)
        cur.execute("ROLLBACK TO SAVEPOINT f")
    print(f"(4) freeze trigger rejects prereg-column UPDATE: {frozen}")
    good = stats["kept"] >= 10 and ncand >= 10 and frozen and cal[1] <= max(3, cal[0] // 5)
    print("PROBE:", "ALL PASS" if good else "FAIL")
    sys.exit(0 if good else 1)
finally:
    conn.rollback(); conn.close(); print("rolled back — nothing persisted")
