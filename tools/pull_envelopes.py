"""Dump every read-RPC envelope, as the owner, to ~/Downloads/personalos_envelopes/*.json
(outside the repo; never committed). Used to design the front end against real data."""
import json, os, sys, datetime as dt
sys.path.insert(0, os.getcwd())
cfg = {"SUPABASE_DB_URL": os.environ.get("SUPABASE_DB_URL")} if os.environ.get("SUPABASE_DB_URL") else json.load(open(".claude/settings.local.json"))["env"]
os.environ['SUPABASE_DB_URL'] = cfg['SUPABASE_DB_URL']
from lib import db
out_dir = os.path.expanduser("~/Downloads/personalos_envelopes"); os.makedirs(out_dir, exist_ok=True)
conn = db.connect(); cur = conn.cursor()
cur.execute("""select set_config('request.jwt.claims','{"email":"joseph.delany21@gmail.com"}',true)""")
calls = {
 'get_domains': "select public.get_domains()",
 'get_today': "select public.get_today()",
 'get_trust': "select public.get_trust()",
 'get_patterns': "select public.get_patterns()",
 'get_findings': "select public.get_findings()",
 'get_domain_sleep': "select public.get_domain('sleep','90d')",
 'get_domain_recovery': "select public.get_domain('recovery','90d')",
 'get_domain_money': "select public.get_domain('money','90d')",
 'get_domain_attention': "select public.get_domain('attention','1y')",
 'get_domain_activity': "select public.get_domain('activity','90d')",
 'get_domain_content': "select public.get_domain('content','90d')",
 'get_domain_places': "select public.get_domain('places','90d')",
 'get_domain_workouts': "select public.get_domain('workouts','90d')",
 'get_timeline_recent': "select public.get_timeline((select max(day) from analysis.panel where metric='sleep_asleep_min'))",
 'get_timeline_2025': "select public.get_timeline('2025-03-04'::date)",
 'get_day': "select public.get_day()",
 'get_movements': "select public.get_movements()",
 'get_places': "select public.get_places()",
 'search_record': "select public.search_record('mcdonald', 20)",
 'get_insights_guarded': "select public.get_insights_guarded()",
}
summary = {}
for name, sql in calls.items():
    try:
        cur.execute(sql); v = cur.fetchone()[0]
        v = v if isinstance(v, (dict, list)) else json.loads(v)
        json.dump(v, open(f'{out_dir}/{name}.json','w'), indent=1, default=str)
        summary[name] = f"ok ({len(json.dumps(v, default=str))} bytes; keys={list(v)[:8] if isinstance(v, dict) else 'list'})"
    except Exception as e:
        summary[name] = f"ERR {type(e).__name__}: {str(e)[:120]}"
        conn.rollback()
        cur.execute("""select set_config('request.jwt.claims','{"email":"joseph.delany21@gmail.com"}',true)""")
conn.rollback(); conn.close()
for k,v in summary.items(): print(f"{k:24} {v}")
