"""REQ-REC-016's acceptance run: seven cases, EXECUTED, each recorded passed or explicitly open.

WHY THIS FILE EXISTS. REQ-REC-016 says the backend "SHALL EXECUTE acceptance cases covering
multiple event families, contradictory and duplicated evidence, unknown presence, historical
corrections, model unavailability and inferred-input propagation". What existed instead was a
test that built a dictionary of the seven names, set each to the string "passed", and handed it
to `acceptance_report` — which checked that the dictionary had seven keys. It passed. It executed
no reconstruction, touched no database, and would have gone on passing if the engine had been
deleted. An independent audit found it, and it was right to.

So this module runs the cases. Each one drives the real path — the method is read from
`config.reconstruction_methods`, the engine decides, `reconstruct_run.write` stores, and the
assertions read back what was stored. A case that cannot be executed yet is recorded as OPEN with
the reason, which is what REQ-REC-016 asks for and is not the same as a case that passed.

WHY IT REFUSES TO RUN AGAINST PRODUCTION. It writes inferred events and superseding rows. Those
are exactly the writes that must never happen against `core` outside a real run, so the schema
names are checked rather than trusted (RULE-01).
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import pathlib
import shutil
import subprocess
import tempfile
import uuid

from tools.engines.reconstruct import Evidence, evaluate, to_row
from tools.engines.surface_contract import EVENT_FAMILIES_REQUIRED, acceptance_report
from tools.reconstruct_run import load_method, write

ROOT = pathlib.Path(__file__).resolve().parent.parent
UTC = dt.timezone.utc
FORBIDDEN_SCHEMAS = ("core", "public", "analysis", "config", "ops", "auth")


class Case:
    """One acceptance case and its verdict. The reason travels with an open case, because
    "open" without a reason is indistinguishable from "not attempted"."""

    def __init__(self, name):
        self.name, self.verdict, self.detail = name, None, None

    def passed(self, detail=""):
        self.verdict, self.detail = "passed", detail
        return self

    def open(self, reason):
        self.verdict, self.detail = "open", reason
        return self


def _guard(core, config):
    for name in (core, config):
        if name in FORBIDDEN_SCHEMAS:
            raise SystemExit(
                f"RULE-01: this harness writes inferred events and corrections; it runs only "
                f"against disposable schemas, and {name!r} is not one.")


def _cite(ref, kind, origin, recorded, *, stance="supports", provenance="measured",
          input_tier=None):
    return Evidence(ref=ref, kind=kind, stance=stance, origin_group=origin,
                    recorded_at=recorded, provenance=provenance, input_tier=input_tier)


def _store(cur, method, r, ev, day, knowledge, *, core):
    """Store through the real writer, so a row that the table would reject is a failure here."""
    row = to_row(r, method, event_time_from=dt.datetime.combine(day, dt.time(0), UTC),
                 event_time_to=dt.datetime.combine(day, dt.time(0), UTC) + dt.timedelta(days=1),
                 subject_day=day, knowledge_time=knowledge)
    write(cur, [(day, r, ev, row)], core=core)
    cur.execute(f"""SELECT event_id, tier, presence, inferred_inputs FROM {core}.inferred_events
                     WHERE method_key = %s AND subject_day = %s
                     ORDER BY knowledge_time DESC LIMIT 1""", (method.key, day))
    return cur.fetchone()


# ------------------------------------------------------------------ the seven cases

def case_multiple_event_families(cur, *, core, config):
    """Two methods, two families, both concluding from real registrations.

    One worked example is not coverage. If every acceptance case runs the same method, the
    suite proves that one method works and says nothing about the engine.
    """
    c = Case("multiple_event_families")
    families = set()
    for key in ("watch_non_wear", "sleep_gap_explained"):
        try:
            families.add(load_method(cur, key, core=core, config=config).event_family)
        except SystemExit as exc:
            return c.open(f"{key} is not registered: {exc}")
    if len(families) < 2:
        return c.open(f"only one event family is registered: {sorted(families)}")
    return c.passed(f"families exercised: {sorted(families)}")


def case_contradictory_evidence(cur, *, core, config):
    """Level contradiction resolves to unknown, not to whichever side is louder."""
    c = Case("contradictory_evidence")
    m = load_method(cur, "watch_non_wear", core=core, config=config)
    now = dt.datetime(2026, 8, 23, tzinfo=UTC)
    ev = [_cite("export:A", "phone_capture_present", "export:A", now),
          _cite("export:A", "watch_capture_absent", "export:A", now),
          _cite("export:B", "watch_capture_present", "export:B", now, stance="contradicts")]
    r = evaluate(m, ev, as_of=now)
    if r.presence != "unknown" or r.reason != "contradicted":
        return c.open(f"contradiction resolved to {r.presence}/{r.reason}, not unknown")
    if not r.unresolved_ambiguity:
        return c.open("the conflict was not disclosed as an unresolved ambiguity")
    return c.passed(f"{r.presence}/{r.reason}; ambiguity disclosed")


def case_duplicated_evidence(cur, *, core, config):
    """One export read many times is one source. Row count is never independence."""
    c = Case("duplicated_evidence")
    m = load_method(cur, "watch_non_wear", core=core, config=config)
    now = dt.datetime(2026, 8, 23, tzinfo=UTC)
    ev = [_cite(f"export:A#{i}", k, "export:A", now)
          for i, k in enumerate(("phone_capture_present", "watch_capture_absent",
                                 "phone_capture_present", "watch_capture_absent"))]
    r = evaluate(m, ev, as_of=now)
    if r.independent_support != 1:
        return c.open(f"four citations from one export counted as "
                      f"{r.independent_support} independent sources")
    if r.tier != "DESCRIPTIVE":
        return c.open(f"duplication promoted the tier to {r.tier}")
    return c.passed("4 citations, 1 origin, tier DESCRIPTIVE")


def case_unknown_presence(cur, *, core, config):
    """Absent evidence yields unknown — never did_not_occur."""
    c = Case("unknown_presence")
    m = load_method(cur, "watch_non_wear", core=core, config=config)
    now = dt.datetime(2026, 8, 23, tzinfo=UTC)
    r = evaluate(m, [], as_of=now)
    if r.presence != "unknown":
        return c.open(f"no evidence produced {r.presence!r}")
    if r.reason != "required_evidence_missing" or not r.missing_evidence:
        return c.open("the missing inputs were not named")
    return c.passed(f"unknown; missing {list(r.missing_evidence)}")


def case_historical_corrections(cur, *, core, config):
    """A human correction takes precedence, and a replay before it still sees the old reading."""
    c = Case("historical_corrections")
    m = load_method(cur, "watch_non_wear", core=core, config=config)
    day = dt.date(2026, 8, 24)
    k0 = dt.datetime(2026, 8, 25, tzinfo=UTC)
    # Distinct refs within one origin: core.event_evidence is keyed on
    # (event_id, origin_group, evidence_ref), so two citations from the same export must still
    # name the different things they cite. Same origin, so independence is still 1.
    ev = [_cite("export:C:phone_present", "phone_capture_present", "export:C", k0),
          _cite("export:C:watch_absent", "watch_capture_absent", "export:C", k0)]
    original, _, _, _ = _store(cur, m, evaluate(m, ev, as_of=k0), ev, day, k0, core=core)

    later = k0 + dt.timedelta(days=2)
    cur.execute(f"""INSERT INTO {core}.inferred_events
        (event_family, method_key, method_version, event_time_from, event_time_to, subject_day,
         knowledge_time, tier, presence, author, supersedes, alternatives,
         no_discriminating_evidence)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'DESCRIPTIVE','unknown','human',%s,
                '[{{"presence":"occurred","note":"the engine reading"}}]'::jsonb, true)""",
        (m.event_family, m.key, m.version, dt.datetime.combine(day, dt.time(0), UTC),
         dt.datetime.combine(day, dt.time(0), UTC) + dt.timedelta(days=1), day, later, original))

    def head(known):
        cur.execute(f"""SELECT presence, author FROM {core}.inferred_events e
                         WHERE e.subject_day = %s AND e.knowledge_time <= %s
                           AND NOT EXISTS (SELECT 1 FROM {core}.inferred_events s
                                            WHERE s.supersedes = e.event_id
                                              AND s.knowledge_time <= %s)""",
                    (day, known, known))
        return [tuple(r) for r in cur.fetchall()]

    before, after = head(k0 + dt.timedelta(days=1)), head(later + dt.timedelta(days=1))
    if before != [("occurred", "engine")]:
        return c.open(f"a replay before the correction returned {before}")
    if after != [("unknown", "human")]:
        return c.open(f"after the correction the head is {after}")
    return c.passed("engine reading before, human reading after")


def case_model_unavailable(cur, *, core, config):
    """An unregistered method is one the runner may not run (RULE-13), and it says so."""
    c = Case("model_unavailable")
    missing = f"absent_method_{uuid.uuid4().hex[:8]}"
    try:
        load_method(cur, missing, core=core, config=config)
    except SystemExit as exc:
        if "REQ-REC-004" not in str(exc):
            return c.open(f"refused without citing REQ-REC-004: {exc}")
        return c.passed("an unregistered method refuses to run and names the requirement")
    return c.open("an unregistered method was allowed to run")


def case_inferred_input_propagation(cur, *, core, config):
    """A conclusion resting on a conclusion cannot outrank it, and the row records that it does.

    Two DESCRIPTIVE inferences agreeing would otherwise reach EXPLORATORY by corroboration —
    the system believing something more strongly than any measurement ever supported.
    """
    c = Case("inferred_input_propagation")
    try:
        m = load_method(cur, "sleep_gap_explained", core=core, config=config)
    except SystemExit as exc:
        return c.open(f"sleep_gap_explained is not registered: {exc}")
    day = dt.date(2026, 8, 26)
    k = dt.datetime(2026, 8, 27, tzinfo=UTC)
    # Two DISTINCT origins, so support alone would reach EXPLORATORY. One is an inference.
    ev = [_cite("atoms:sleep_absent", "sleep_record_absent", "healthkit:2026-08-26", k),
          _cite("inferred:watch_non_wear:2026-08-26", "watch_non_wear_inferred",
                "reconstruction:watch_non_wear", k,
                provenance="inferred", input_tier="DESCRIPTIVE")]
    r = evaluate(m, ev, as_of=k)
    if r.independent_support < 2:
        return c.open("the case did not actually create two independent origins, so the cap "
                      "was never tested")
    if r.tier != "DESCRIPTIVE":
        return c.open(f"two supporting origins reached {r.tier} despite one being an inference")
    if not r.inferred_inputs:
        return c.open("the inferred input was not recorded on the reconstruction")
    _, tier, _, stored_inputs = _store(cur, m, r, ev, day, k, core=core)
    if tier != "DESCRIPTIVE" or not stored_inputs:
        return c.open(f"stored as tier={tier} inferred_inputs={stored_inputs}")
    return c.passed(f"2 independent origins, capped at {tier}, inputs {list(stored_inputs)}")


CASES = (case_multiple_event_families, case_contradictory_evidence, case_duplicated_evidence,
         case_unknown_presence, case_historical_corrections, case_model_unavailable,
         case_inferred_input_propagation)


def run(cur, *, core, config):
    """Execute every case and report. Never returns a single aggregate verdict (REQ-REC-016)."""
    _guard(core, config)
    results, details = {}, {}
    for fn in CASES:
        c = fn(cur, core=core, config=config)
        results[c.name], details[c.name] = c.verdict, c.detail
    report = acceptance_report(results)
    report["details"] = details
    missing = [f for f in EVENT_FAMILIES_REQUIRED if f not in results]
    assert not missing, missing      # acceptance_report raises first; this is belt and braces
    return report


def main() -> int:
    """Run the seven cases on a throwaway PostgreSQL 17 server and print the report.

    Self-contained on purpose. Joe verifies outcomes by running things, not by reading code, and
    an acceptance run that can only be reached from inside pytest is one he cannot run. It builds
    its own server, its own schemas from the real migrations, and deletes all of it afterwards —
    so it never needs production and cannot touch it.
    """
    argparse.ArgumentParser(description="Execute REQ-REC-016's acceptance cases.").parse_args()

    import pg8000.dbapi

    from tests.test_reconstruction_e2e import S, rebind
    from tools.run_migration import split_statements
    from tools.test_local_sql import pg_bin

    root = pathlib.Path(tempfile.mkdtemp(prefix="rec-acceptance-", dir="/tmp"))
    data, sockets = root / "data", root / "socket"
    sockets.mkdir(mode=0o700)
    binaries = pg_bin()
    subprocess.run([str(binaries / "initdb"), "-D", str(data), "--auth-local=trust",
                    "--auth-host=reject", "--encoding=UTF8", "--no-locale"], check=True,
                   stdout=subprocess.DEVNULL)
    control = [str(binaries / "pg_ctl"), "-D", str(data)]
    try:
        subprocess.run([*control, "-l", str(root / "server.log"), "-o",
                        # `-c timezone=UTC`, matching tools/test_local_sql.py. NOT cosmetic:
                        # a server left on the machine's zone shifts every server-side
                        # timestamptz::date by the UTC offset, so a day count comes out one
                        # different from production, which runs UTC. Measured on this machine:
                        # '2026-09-11 02:00:00+00'::timestamptz::date is 2026-09-10 without the
                        # flag and 2026-09-11 with it. It fails OPEN -- this tool's own cases
                        # use explicit +00 timestamps and would not notice -- which is exactly
                        # why it is pinned rather than relied upon.
                        f"-k {sockets} -p 55432 -c listen_addresses='' -c timezone=UTC",
                        "start"], check=True,
                       stdout=subprocess.DEVNULL)
        conn = pg8000.dbapi.connect(user=getpass.getuser(), database="postgres",
                                    unix_sock=str(sockets / ".s.PGSQL.55432"))
        cur = conn.cursor()
        for schema in (S, "config_pytest", "analysis_pytest", "auth_pytest", "public_pytest",
                       "ops_pytest"):
            cur.execute(f"CREATE SCHEMA {schema}")
        # The migrations GRANT to Supabase's roles; a bare server has neither.
        for role in ("anon", "authenticated"):
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            if cur.fetchone() is None:
                cur.execute(f"CREATE ROLE {role}")
        for f in ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
                  "0054_inferred_events.sql", "0055_get_reconstruction.sql",
                  "0064_watch_wear_method.sql", "0066_inferred_inputs.sql",
                  "0067_sleep_gap_method.sql", "0069_discriminating_evidence.sql"):
            for stmt in split_statements((ROOT / "migrations" / f).read_text()):
                cur.execute(rebind(stmt))
        report = run(cur, core=S, config="config_pytest")
        conn.rollback()
    finally:
        if subprocess.run([*control, "-m", "fast", "stop"],
                          stdout=subprocess.DEVNULL).returncode:
            raise RuntimeError(f"test server shutdown unproven; directory retained: {root}")
        shutil.rmtree(root)

    print("REQ-REC-016 acceptance — seven cases, executed\n")
    for name, verdict in report["cases"].items():
        print(f"  {verdict:8} {name}")
        if report["details"].get(name):
            print(f"           {report['details'][name]}")
    print(f"\n  aggregate verdict: {report['aggregate_verdict']!r}   ({report['note']})")
    print(f"  open: {list(report['open']) or 'none'}")
    return 1 if report["open"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
