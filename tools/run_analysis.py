#!/usr/bin/env python3
"""Nightly analysis refresh (ADR-0038): panel -> baselines, heartbeated.
Loads the static legacy series only if the table is empty. Safe to re-run.

    PYTHONPATH=. python3 tools/run_analysis.py
"""
import json
import sys

from lib import db
from tools.engines import panel, baselines, forecast


def main() -> int:
    conn = db.connect(); cur = conn.cursor()
    try:
        cur.execute("select count(*) from analysis.legacy_daily")
        if cur.fetchone()[0] == 0:
            print("legacy_daily empty — run tools/parsers/legacy_daily.py first "
                  "(static seven-year series).")
        n_p = panel.build(cur)
        panel.log_run(cur, n_p)
        n_b = baselines.compute(cur)
        baselines.log_run(cur, n_b)
        n_res, n_unres = forecast.resolve(cur)
        n_fc = forecast.run(cur)
        cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                       values ('forecast_nightly', now(), 'ok', %s, %s)""",
                    (n_fc, json.dumps({"resolved": n_res, "unresolvable_pending": n_unres,
                                       "code_version": forecast.CODE_VERSION})))
        cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                       values ('analysis_refresh', now(), 'ok', %s, '{}')""", (n_p + n_b,))
        conn.commit()
        print(f"analysis refresh: panel {n_p}, baselines {n_b}, "
              f"forecasts {n_fc}, resolved {n_res}")
        return 0
    except Exception as e:
        conn.rollback()
        try:
            cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                           values ('analysis_refresh', now(), 'error', 0, %s)""",
                        (json.dumps({"error": str(e)[:400]}),))
            conn.commit()
        except Exception:
            conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
