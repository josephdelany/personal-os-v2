#!/usr/bin/env python3
"""Legacy-archive -> atoms backfill: RECONCILIATION + registry + atom generation.

ADR-0025 (reconciliation), ADR-0026 (A' lineage + gait), ADR-0027 (registry +
per-stream modeling). This supersedes the disposition math in `backfill_map.py`
by reading the ACTUAL archive (not the manifests), which revealed the map was
wrong: `intraday` and the `health__*` tables are the same Apple-Health export
(value-level confirmed), so they must be union-deduped, and `locations` cannot
be a scalar atom (RULE-29). See ADR-0026/0027.

Modes:
    python3 tools/backfill_run.py --report      # compute + print reconciliation,
                                                # registry rows, sample atoms. NO DB.
    (the rolled-back DB dry-run that INSERTs into a copy is added once migration
     0015 — the `legacy_archive` enum value — is committed; ADD VALUE cannot be
     used in the same transaction it is created, so it must land first.)

--report writes NOTHING and touches no database (RULE-01). It exists so the
Gate-2 reconciliation and the atom transforms are auditable before any
irreversible append (INV-2).
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import pathlib
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNAP = ROOT / "_legacy_snapshot"
UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")
RULE_VERSION = "legacy-v1-2026-08-23"

# ---- metric_registry rows (ADR-0027 / ADR-0018). plausible_low/high NULL (RULE-06). ----
# (metric_key, display_name, family, unit, state_class, self_report, response_scale, n_pts, round)
REGISTRY = [
    ("heart_rate",            "Heart rate",              "cardio",   "count/min", "measurement", False, None, None, None),
    ("resting_heart_rate",    "Resting heart rate",      "cardio",   "count/min", "measurement", False, None, None, None),
    ("walking_heart_rate",    "Walking heart rate",      "cardio",   "count/min", "measurement", False, None, None, None),
    ("respiratory_rate",      "Respiratory rate",        "respiratory", "count/min", "measurement", False, None, None, None),
    ("spo2",                  "Blood oxygen (SpO2)",     "respiratory", "%",       "measurement", False, None, None, None),
    ("wrist_temperature",     "Wrist temperature",       "thermoregulation", "degF", "measurement", False, None, None, None),
    ("vo2max",                "VO2 max",                 "cardio",   "mL/min·kg", "measurement", False, None, None, None),
    ("hrv",                   "Heart-rate variability",  "cardio",   "ms",        "measurement", False, None, None, None),
    ("walking_speed",         "Walking speed",           "gait",     "mi/hr",     "measurement", False, None, None, None),
    ("walking_step_length",   "Walking step length",     "gait",     "in",        "measurement", False, None, None, None),
    ("walking_double_support_pct", "Double-support time","gait",     "%",         "measurement", False, None, None, None),
    ("walking_asymmetry_pct", "Walking asymmetry",       "gait",     "%",         "measurement", False, None, None, None),
    ("walking_steadiness_pct","Walking steadiness",      "gait",     "%",         "measurement", False, None, None, None),
    ("body_weight",           "Body weight",             "body",     "lbs",       "measurement", False, None, None, None),
    ("body_fat_pct",          "Body fat",                "body",     "%",         "measurement", False, None, None, None),
    ("fat_mass",              "Fat mass",                "body",     "lbs",       "measurement", False, None, None, None),
    ("lean_mass",             "Lean mass",               "body",     "lbs",       "measurement", False, None, None, None),
    ("muscle_mass",           "Muscle mass",             "body",     "lbs",       "measurement", False, None, None, None),
    ("hydration",             "Hydration mass",          "body",     "lbs",       "measurement", False, None, None, None),
    ("bone_mass",             "Bone mass",               "body",     "lbs",       "measurement", False, None, None, None),
    ("txn_amount",            "Transaction amount",      "money",    "USD",       "measurement", False, None, None, None),
    # sleep — one metric_key per stage (ADR-0027, Joe's ruling); durational, no scalar value
    ("sleep_inbed",           "Sleep: in bed",           "sleep",    None,        "measurement", False, None, None, None),
    ("sleep_core",            "Sleep: core",             "sleep",    None,        "measurement", False, None, None, None),
    ("sleep_deep",            "Sleep: deep",             "sleep",    None,        "measurement", False, None, None, None),
    ("sleep_rem",             "Sleep: REM",              "sleep",    None,        "measurement", False, None, None, None),
    ("sleep_awake",           "Sleep: awake",            "sleep",    None,        "measurement", False, None, None, None),
    ("sleep_asleep_unspecified", "Sleep: asleep (unspecified)", "sleep", None,    "measurement", False, None, None, None),
    # self-reports (ADR-0018 coarsening: integer 1..5 scale observed in checkins)
    ("energy",                "Energy (self-report)",    "self_report", None,     "measurement", True, "[1,5]", 5, 1),
    ("restored",              "Restedness (self-report)","self_report", None,     "measurement", True, "[1,5]", 5, 1),
    ("drive",                 "Drive (self-report)",     "self_report", None,     "measurement", True, "[1,5]", 5, 1),
]
STAGE2METRIC = {
    "HKCategoryValueSleepAnalysisInBed": "sleep_inbed",
    "HKCategoryValueSleepAnalysisAsleepCore": "sleep_core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "sleep_deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "sleep_rem",
    "HKCategoryValueSleepAnalysisAwake": "sleep_awake",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "sleep_asleep_unspecified",
}
BODY_COLS = [("weight_lbs", "body_weight", "lbs"), ("fat_pct", "body_fat_pct", "%"),
             ("fat_mass_lbs", "fat_mass", "lbs"), ("lean_mass_lbs", "lean_mass", "lbs"),
             ("muscle_mass_lbs", "muscle_mass", "lbs"), ("hydration_lbs", "hydration", "lbs"),
             ("bone_mass_lbs", "bone_mass", "lbs")]

# series/table -> (metric_key, kind). sleep handled separately.
VITAL = {"heart_rate", "resting_heart_rate", "walking_heart_rate", "respiratory_rate",
         "spo2", "wrist_temperature", "vo2max"}
def kind_of(metric):
    if metric == "hrv":
        return "heart_rate_variability"
    if metric in VITAL:
        return "vital_sample"
    return "activity_sample"  # gait

SERIES2METRIC = {
    "hr": "heart_rate", "rhr": "resting_heart_rate", "walking_hr": "walking_heart_rate",
    "resp_rate": "respiratory_rate", "spo2": "spo2", "wrist_temp": "wrist_temperature",
    "vo2max": "vo2max", "hrv_window": "hrv", "walking_speed": "walking_speed",
    "walking_step_length": "walking_step_length",
    "walking_double_support": "walking_double_support_pct",
    "walking_asymmetry": "walking_asymmetry_pct", "walking_steadiness": "walking_steadiness_pct",
}
HEALTHTBL2METRIC = {
    "health__hr_samples": "heart_rate", "health__rhr": "resting_heart_rate",
    "health__walking_hr": "walking_heart_rate", "health__resp_rate": "respiratory_rate",
    "health__spo2": "spo2", "health__wrist_temp": "wrist_temperature",
    "health__vo2max": "vo2max", "health__hrv_windows": "hrv",
    "health__walking_speed": "walking_speed", "health__walking_step_length": "walking_step_length",
    "health__walking_double_support": "walking_double_support_pct",
    "health__walking_asymmetry": "walking_asymmetry_pct",
    "health__walking_steadiness": "walking_steadiness_pct",
}


def P(rel):
    return pq.read_table(SNAP / rel)


def epoch_of_str(s):
    """health__ ts like '2023-09-19 07:06:43 -0400' -> utc epoch int."""
    return int(dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z").timestamp())


def subject_day(occurred_utc_epoch, is_sleep_end=None):
    """ADR-0019: 04:00 local (ET) boundary, by start; sleep by wake day handled by
    passing the END epoch as occurred. Returns a date."""
    local = dt.datetime.fromtimestamp(occurred_utc_epoch, ET)
    d = local.date()
    if local.hour < 4:
        d = d - dt.timedelta(days=1)
    return d


def load_manifests():
    m = {}
    for f in ("supabase_manifest.json", "manifest.json"):
        for rec in json.loads((SNAP / f).read_text()):
            m[rec["entity"]] = rec
    return m


def health_dedup():
    """Union intraday(non-sleep health series) + 14 health__ tables. Returns
    (distinct_keys:set, rows_in:int, per_source_first:dict metric->{key:src})."""
    keys = set()
    src_of = {}
    rows_in = 0
    # intraday
    it = P("supabase/intraday.parquet").select(["series", "ts", "value"]).to_pylist()
    for r in it:
        s = r["series"]
        if s == "sleep_stage":
            continue  # sleep handled separately
        metric = SERIES2METRIC[s]
        rows_in += 1
        k = (metric, int(r["ts"].timestamp()), None if r["value"] is None else round(float(r["value"]), 4))
        if k not in keys:
            keys.add(k); src_of[k] = "intraday"
    # health__ tables
    for tbl, metric in HEALTHTBL2METRIC.items():
        if tbl == "health__hrv_windows":
            # durational: key on window START + the SDNN value (matches intraday hrv_window ts/value)
            pairs = [(r["start_ts"], r["sdnn_apple_ms"])
                     for r in P(f"parquet/{tbl}.parquet").select(["start_ts", "sdnn_apple_ms"]).to_pylist()]
        else:
            pairs = [(r["ts"], r["value"])
                     for r in P(f"parquet/{tbl}.parquet").select(["ts", "value"]).to_pylist()]
        for ts, value in pairs:
            rows_in += 1
            k = (metric, epoch_of_str(ts), None if value is None else round(float(value), 4))
            if k not in keys:
                keys.add(k); src_of[k] = tbl
            elif src_of[k] == "intraday":
                src_of[k] = "intraday+" + tbl  # both exports carry it
    return keys, rows_in, src_of


def web_dedup(kind_name, events_kind, pos_rel, pos_ts_col, pos_tz):
    """Union events.<kind> + pos table. pos_tz in {'UTC','ET'}. Returns (distinct, rows_in, src_of)."""
    ev = P("supabase/events.parquet").to_pylist()
    keys = set(); src_of = {}; rows_in = 0
    for r in ev:
        if r["kind"] != events_kind:
            continue
        rows_in += 1
        p = json.loads(r["payload"]); url = p.get("url")
        k = (url, int(r["ts"].timestamp()))
        if k not in keys:
            keys.add(k); src_of[k] = "events"
    pos = P(pos_rel).select(["url", pos_ts_col]).to_pylist()
    for r in pos:
        rows_in += 1
        s = r[pos_ts_col]
        if pos_tz == "UTC":
            e = int(dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp())
        else:
            e = int(dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET).timestamp())
        k = (r["url"], e)
        if k not in keys:
            keys.add(k); src_of[k] = pos_rel.split("/")[-1]
        elif src_of[k] == "events":
            src_of[k] = "events+pos"
    return keys, rows_in, src_of


import uuid
_NS = uuid.UUID("1e6ac70e-0000-4000-8000-000000000001")  # fixed namespace for deterministic legacy capture ids
CODE_VERSION = "backfill-0026-0027"


def cap_id(table):
    return str(uuid.uuid5(_NS, f"legacy_archive:{table}"))


def epoch_dt(ep):
    return dt.datetime.fromtimestamp(ep, UTC)


def build_atoms():
    """Return (registry_rows, capture_rows, atom_rows) fully materialised (ADR-0026/0027).
    atom_rows are tuples in ATOM_COLS order; valid_interval is a text range or None."""
    man = load_manifests()
    contributing = set()
    atoms = []

    def add(table, **f):
        contributing.add(table)
        f.setdefault("raw_capture_id", cap_id(table))
        f.setdefault("metric_key", None); f.setdefault("occurred_at", None)
        f.setdefault("time_precision", "exact"); f.setdefault("valid_interval", None)
        f.setdefault("value_low", None); f.setdefault("value_point", None); f.setdefault("value_high", None)
        f.setdefault("estimate_method", None); f.setdefault("unit", None); f.setdefault("state_class", None)
        f.setdefault("value_type", None); f.setdefault("provenance", "extracted")
        atoms.append(f)

    # --- health samples (union-deduped) ---
    h_keys, _, h_src = health_dedup()
    for (metric, ep, val) in h_keys:
        src = h_src[(metric, ep, val)]
        primary = "intraday" if src.startswith("intraday") else src
        add(primary, kind=kind_of(metric), metric_key=metric, occurred_at=epoch_dt(ep),
            subject_day=subject_day(ep), presence="observed",
            value_low=val, value_point=val, value_high=val, estimate_method="measured",
            unit=REG_UNIT[metric], state_class="measurement", trust_level="trusted",
            evidence_span=f"{primary}#({metric},{ep},{val})|src={src}")

    # --- sleep (durational; metric_key per stage; subject_day by WAKE=end) ---
    for r in P("parquet/health__sleep_intervals.parquet").to_pylist():
        s = int(dt.datetime.strptime(r["start_ts"], "%Y-%m-%d %H:%M:%S %z").timestamp())
        e = int(dt.datetime.strptime(r["end_ts"], "%Y-%m-%d %H:%M:%S %z").timestamp())
        add("health__sleep_intervals", kind="sleep", metric_key=STAGE2METRIC[r["stage"]],
            valid_interval=f"[{epoch_dt(s).isoformat()},{epoch_dt(e).isoformat()}]",
            time_precision="exact", subject_day=subject_day(e), presence="observed",
            trust_level="trusted", evidence_span=f"health__sleep_intervals#({s},{e},{r['stage']})|src=health__sleep_intervals")

    # --- web_visit / media_play (deduped) ---
    for (kind_name, ev_kind, pos_rel, pos_col, tz, trust) in [
        ("web_visit", "chrome_visit", "parquet/pos__chrome_history.parquet", "visited_at", "UTC", "untrusted"),
        ("media_play", "youtube_watch", "parquet/pos__youtube_history.parquet", "watched_at", "ET", "untrusted")]:
        keys, _, src = web_dedup(kind_name, ev_kind, pos_rel, pos_col, tz)
        tbl = "events" if kind_name == "web_visit" else "events"
        for (url, ep) in keys:
            s = src[(url, ep)]
            primary = "events" if s.startswith("events") else pos_rel.split("/")[-1].replace(".parquet", "")
            add(primary, kind=kind_name, occurred_at=epoch_dt(ep), subject_day=subject_day(ep),
                presence="observed", trust_level=trust,
                evidence_span=f"{primary}#({url},{ep})|src={s}")

    # --- calendar_event ---
    ev = P("supabase/events.parquet").to_pylist()
    cal_seen = set()
    for r in ev:
        if r["kind"] != "calendar":
            continue
        p = json.loads(r["payload"]); key = (str(p.get("id") or p.get("summary")), str(p.get("start") or p.get("start_dt")))
        cal_seen.add(key)
        ep = int(r["ts"].timestamp())
        add("events", kind="calendar_event", occurred_at=epoch_dt(ep), time_precision="minute",
            subject_day=subject_day(ep), presence="observed", trust_level="trusted",
            evidence_span=f"events#{key}|src=events")
    for r in P("parquet/pos__calendar_events.parquet").to_pylist():
        key = (str(r["id"]), str(r["start_dt"]))
        if key in cal_seen:
            continue
        # date-only start -> day precision, occurred at 12:00 local as a placeholder instant
        d = dt.datetime.strptime(r["start_dt"][:10], "%Y-%m-%d").replace(hour=12, tzinfo=ET)
        add("pos__calendar_events", kind="calendar_event", occurred_at=d.astimezone(UTC),
            time_precision="day", subject_day=subject_day(int(d.timestamp())), presence="observed",
            trust_level="trusted", evidence_span=f"pos__calendar_events#{key}|src=pos__calendar_events")

    # --- transaction ---
    for r in P("supabase/transactions.parquet").to_pylist():
        ep = int(r["ts"].timestamp()); amt = float(r["amount"])
        add("transactions", kind="transaction", occurred_at=epoch_dt(ep), subject_day=subject_day(ep),
            presence="observed", value_low=amt, value_point=amt, value_high=amt, estimate_method="measured",
            unit=r["currency"], state_class="measurement", trust_level="untrusted",
            evidence_span=f"transactions#{r['id']}|src=transactions")

    # --- body_measurement (wide -> one atom per non-null metric cell) ---
    for r in P("parquet/pos__body_composition.parquet").to_pylist():
        d = dt.datetime.strptime(r["date"][:10], "%Y-%m-%d").replace(hour=12, tzinfo=ET)
        for col, metric, unit in BODY_COLS:
            if r[col] is None:
                continue
            v = float(r[col])
            add("pos__body_composition", kind="body_measurement", metric_key=metric,
                occurred_at=d.astimezone(UTC), time_precision="day", subject_day=subject_day(int(d.timestamp())),
                presence="observed", value_low=v, value_point=v, value_high=v, estimate_method="measured",
                unit=unit, state_class="measurement", trust_level="trusted",
                evidence_span=f"pos__body_composition#{r['date']}:{metric}|src=pos__body_composition")

    # --- self_report (checkins; 1..5 coarsened interval [r-0.5, r+0.5], ADR-0018) ---
    for r in P("supabase/checkins.parquet").to_pylist():
        ep = int(r["ts"].timestamp())
        for metric in ("energy", "restored", "drive"):
            if r[metric] is None:
                continue
            v = float(r[metric])
            add("checkins", kind="self_report", metric_key=metric, occurred_at=epoch_dt(ep),
                subject_day=subject_day(ep), presence="observed",
                value_low=v - 0.5, value_point=v, value_high=v + 0.5, estimate_method="self_report",
                state_class="measurement", trust_level="trusted",
                evidence_span=f"checkins#{r['id']}:{metric}|src=checkins")

    # captures: one per contributing table-load (A', ADR-0026)
    captures = []
    for tbl in sorted(contributing):
        m = man[tbl]
        payload = json.dumps({"table": tbl, "sha256": m["sha256"], "rows_source": m["rows_source"],
                              "source": m["source"], "snapshot": "2026-08-23 legacy archive"})
        captures.append((cap_id(tbl), BACKFILL_TS, "legacy_archive", "trusted", payload))
    return list(REGISTRY), captures, atoms


REG_UNIT = {r[0]: r[3] for r in REGISTRY}
BACKFILL_TS = dt.datetime(2026, 8, 23, 12, 0, tzinfo=UTC)  # archive ingest reference (not a device capture)
ATOM_COLS = ["raw_capture_id", "kind", "metric_key", "occurred_at", "time_precision", "valid_interval",
             "subject_day", "presence", "value_low", "value_point", "value_high", "estimate_method",
             "unit", "state_class", "value_type", "trust_level", "provenance", "evidence_span"]


def dry_run(core, ops="ops_dryrun"):
    from lib import db
    from tools import check_invariants, run_migration
    print(f"building atoms from the archive ...")
    reg, caps, atoms = build_atoms()
    print(f"generated: {len(reg)} registry, {len(caps)} captures, {len(atoms):,} atoms")
    conn = db.connect(); cur = conn.cursor()
    try:
        # build the copy schema IN THIS TXN. The capture_source enum is created here
        # (migration 0004) and legacy_archive added (0015) in the same transaction, so
        # Postgres permits USING it in this same txn (enum-created-this-txn exception).
        nf, ns = run_migration.apply(cur, core, ops)
        print(f"applied {nf} migrations ({ns} statements) to {core}/{ops} (in-txn)")
        for row in reg:
            cur.execute(
                f"insert into {core}.metric_registry (metric_key,display_name,family,unit,state_class,"
                f"self_report,response_scale,n_scale_points,rounding_step) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8]))
        for c in caps:
            cur.execute(f"insert into {core}.raw_captures (capture_id,captured_at,source,trust_level,payload) "
                        f"values (%s,%s,%s,%s,%s)", c)
        cols = ",".join(ATOM_COLS + ["code_version", "subject_day_rule_version"])
        row_ph = "(%s,%s,%s,%s,%s,%s::tstzrange,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        B = 2000
        for i in range(0, len(atoms), B):
            chunk = atoms[i:i + B]
            sql = f"insert into {core}.atoms ({cols}) values " + ",".join([row_ph] * len(chunk))
            params = []
            for a in chunk:
                params += [a["raw_capture_id"], a["kind"], a["metric_key"], a["occurred_at"], a["time_precision"],
                           a["valid_interval"], a["subject_day"], a["presence"], a["value_low"], a["value_point"],
                           a["value_high"], a["estimate_method"], a["unit"], a["state_class"], a["value_type"],
                           a["trust_level"], a["provenance"], a["evidence_span"], CODE_VERSION, RULE_VERSION]
            cur.execute(sql, params)
        # verify
        cur.execute(f"select count(*) from {core}.atoms"); n = cur.fetchone()[0]
        cur.execute(f"select kind,count(*) from {core}.atoms group by kind order by 2 desc")
        by_kind = cur.fetchall()
        cur.execute(f"select count(*) from {core}.metric_registry"); nreg = cur.fetchone()[0]
        cur.execute(f"select count(*) from {core}.raw_captures"); ncap = cur.fetchone()[0]
        print(f"\nDB DRY-RUN (rolled back) on {core}: {nreg} registry, {ncap} captures, {n:,} atoms inserted")
        print("atoms by kind:")
        for k, c in by_kind:
            print(f"  {k:24} {c:>10,}")
        # storage footprint of the populated copy (data + indexes + toast), before rollback
        print("--- storage footprint (measured on the populated copy) ---")
        total = 0
        for t in ("atoms", "raw_captures", "metric_registry"):
            cur.execute(f"select pg_total_relation_size('{core}.{t}')")
            sz = cur.fetchone()[0]; total += sz
            print(f"  {core}.{t:16} {sz/1024/1024:8.2f} MB")
        print(f"  {'TOTAL new':18} {total/1024/1024:8.2f} MB  (this is the commit delta)")
        print("--- invariants (in-transaction) ---")
        ok = check_invariants.run_checks(cur, core)
        print("--- invariants:", "ALL PASS" if ok else "FAIL", "---")
    finally:
        conn.rollback(); conn.close()
        print("ROLLED BACK — nothing persisted (INV-2 respected; core untouched)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--dry-run", dest="dryrun", metavar="SCHEMA",
                    help="insert registry+captures+atoms into SCHEMA, verify, ROLLBACK")
    args = ap.parse_args()
    if args.dryrun:
        dry_run(args.dryrun)
        return

    man = load_manifests()

    # ---- deduped streams ----
    h_keys, h_rows, h_src = health_dedup()
    w_keys, w_rows, _ = web_dedup("web_visit", "chrome_visit", "parquet/pos__chrome_history.parquet", "visited_at", "UTC")
    m_keys, m_rows, _ = web_dedup("media_play", "youtube_watch", "parquet/pos__youtube_history.parquet", "watched_at", "ET")
    # calendar: (id, start)
    ev = P("supabase/events.parquet").to_pylist()
    cal_keys = set(); cal_rows = 0
    for r in ev:
        if r["kind"] == "calendar":
            cal_rows += 1
            p = json.loads(r["payload"]); cal_keys.add((str(p.get("id") or p.get("summary")), str(p.get("start") or p.get("start_dt"))))
    for r in P("parquet/pos__calendar_events.parquet").select(["id", "start_dt"]).to_pylist():
        cal_rows += 1
        cal_keys.add((str(r["id"]), str(r["start_dt"])))

    # sleep: sleep_intervals is canonical (durational); intraday.sleep_stage is dup
    sleep_atoms = man["health__sleep_intervals"]["rows_source"]
    sleep_intraday_dup = sum(1 for r in P("supabase/intraday.parquet").select(["series"]).to_pylist() if r["series"] == "sleep_stage")

    # simple tables
    txn_atoms = int(man["transactions"]["rows_source"])
    dh = P("parquet/pos__daily_health.parquet")   # WHOLE table is DERIVED (Joe: daily rollups, INV-5)
    bc = P("parquet/pos__body_composition.parquet")
    body_atoms = sum(bc.num_rows - bc.column(c).null_count for c, _, _ in BODY_COLS)
    ck = P("supabase/checkins.parquet")
    checkin_atoms = sum(ck.num_rows - ck.column(c).null_count for c in ("energy", "restored", "drive"))

    # events non-web/media/calendar kinds -> excluded (derived/operational)
    ev_kind = collections.Counter(r["kind"] for r in ev)
    ev_atom_kinds = {"youtube_watch", "chrome_visit", "calendar"}
    ev_excluded = sum(n for k, n in ev_kind.items() if k not in ev_atom_kinds)

    # ---- reconciliation ----
    # Two DISTINCT totals (ADR-0025 reconciles ROWS; atoms can fan out/in):
    #   rows_mapped  = archived ROWS that produce >=1 atom (1:1 for deduped streams;
    #                  the whole row count for the wide fan tables). Reconciles to 810,933.
    #   atoms_out    = ATOMS written (deduped streams 1:1; wide tables fan: body 10 rows
    #                  -> 52 atoms, daily_health 2,370 rows -> 1,480 env atoms). Informational.
    rows_mapped = (len(h_keys) + len(w_keys) + len(m_keys) + len(cal_keys)
                   + int(sleep_atoms) + txn_atoms + bc.num_rows + ck.num_rows)
    atoms_out = (len(h_keys) + len(w_keys) + len(m_keys) + len(cal_keys)
                 + int(sleep_atoms) + txn_atoms + body_atoms + checkin_atoms)
    dup_internal = ((h_rows - len(h_keys)) + (w_rows - len(w_keys)) + (m_rows - len(m_keys))
                    + (cal_rows - len(cal_keys)) + sleep_intraday_dup)

    # excluded-with-reason (from backfill_map buckets, minus what we re-bucketed)
    OVERLAP = 72108          # csv__* + pos__spend_transactions (cross-snapshot dups)
    DERIVED = 111113 + dh.num_rows  # 17 old-stack output tables + pos__daily_health (all rollups, INV-5)
    ENTITY = 2237
    REGISTRY_ROWS = 402
    OPERATIONAL = 15
    EMPTY = 0
    DEFERRED_locations = int(man["locations"]["rows_source"])   # RULE-29 + schema-fit -> Phase 4

    grand = 810933
    accounted = (rows_mapped + dup_internal + ev_excluded + OVERLAP + DERIVED
                 + ENTITY + REGISTRY_ROWS + OPERATIONAL + EMPTY + DEFERRED_locations)

    print("=" * 72)
    print("BACKFILL RECONCILIATION (ADR-0025/0026/0027) — computed from the archive")
    print("Reconciles ROWS (every archived row accounted); atoms-written is separate")
    print("because wide tables fan out and deduped streams fan in.")
    print("=" * 72)
    print(f"{'disposition':<26}{'rows':>12}   note")
    rows = [
        ("MAPPED -> atoms",         rows_mapped, "archived rows producing >=1 atom"),
        ("  health samples",        len(h_keys), f"union intraday+health__ (in={h_rows})"),
        ("  web_visit",             len(w_keys), f"union events+pos chrome (in={w_rows})"),
        ("  media_play",            len(m_keys), f"union events+pos youtube (in={m_rows})"),
        ("  calendar_event",        len(cal_keys), f"union events+pos calendar (in={cal_rows})"),
        ("  sleep",                 int(sleep_atoms), "health__sleep_intervals (durational)"),
        ("  transaction",           txn_atoms,   "supabase.transactions (canonical)"),
        ("  body_composition rows", bc.num_rows, f"wide: {bc.num_rows} rows -> {body_atoms} body_measurement atoms"),
        ("  checkins rows",         ck.num_rows, f"{ck.num_rows} rows -> {checkin_atoms} self_report atoms"),
        ("DUP_INTERNAL (excluded)", dup_internal, "same fact in 2 exports — rider 1, named not silent"),
        ("events non-obs (excl)",   ev_excluded, "data_quarantine/alerts/etc -> derived/operational"),
        ("OVERLAP (excl)",          OVERLAP,     "csv__* + pos__spend_transactions cross-snapshot dups"),
        ("DERIVED (excl)",          DERIVED,     "17 old-stack outputs + pos__daily_health (rollups, INV-5)"),
        ("ENTITY (excl)",           ENTITY,      "-> core.entities (Phase 4)"),
        ("REGISTRY (excl)",         REGISTRY_ROWS, "-> metric_registry / category ref"),
        ("OPERATIONAL (excl)",      OPERATIONAL, "ingest status / probe queue"),
        ("DEFERRED: locations",     DEFERRED_locations, "RULE-29 + no coord cols -> Phase 4 (OQ)"),
    ]
    for name, n, note in rows:
        print(f"{name:<26}{n:>12,}   {note}")
    print("-" * 72)
    print(f"{'accounted rows':<26}{accounted:>12,}   archive grand total = {grand:,}")
    print(f"{'RECONCILES':<26}{str(accounted == grand):>12}   (Δ = {grand - accounted:,})")
    print(f"{'ATOMS written (fan-adj)':<26}{atoms_out:>12,}   (MAPPED rows {rows_mapped:,} "
          f"-> {atoms_out:,} atoms after wide-table fan)")

    print("\n" + "=" * 72)
    print(f"metric_registry rows to insert: {len(REGISTRY)} (plausible_low/high NULL, RULE-06)")
    print("=" * 72)
    print(f"{'metric_key':<26}{'family':<14}{'unit':<10}{'self_report'}")
    for row in REGISTRY:
        print(f"{row[0]:<26}{row[2]:<14}{str(row[3]):<10}{row[5]}")

    print("\n" + "=" * 72)
    print("SAMPLE ATOMS (first of each stream; evidence_span carries source — rider 2)")
    print("=" * 72)
    # a couple of concrete health atoms
    shown = 0
    for k in list(h_keys)[:3]:
        metric, ep, val = k
        sd = subject_day(ep)
        print(f"  kind={kind_of(metric):<22} metric_key={metric:<20} occurred_at={dt.datetime.fromtimestamp(ep, UTC).isoformat()} "
              f"value={val} subject_day={sd} presence=observed estimate_method=measured trust=trusted "
              f"provenance=extracted evidence_span='{h_src[k]}#<rowkey>|src={h_src[k]}'")
        shown += 1


if __name__ == "__main__":
    main()
