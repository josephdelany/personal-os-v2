"""The reconstruction path, end to end, through real entry points (REQ-REC-001..016; ADR-0134).

source evidence -> registered method -> stored inferred event -> Ask/Record response
-> evidence inspection -> correction -> historical replay

This is deliberately ONE test file that walks the whole chain rather than a set of unit tests of
the parts. Every part of this chain already had passing unit tests and NOTHING RAN: the schema was
deployed since 0054, `reconstruct.py` was tested since B14R with no caller, and
`config.reconstruction_methods` was empty. Unit tests of an unwired path prove the parts work in
isolation, which is exactly what was already true and exactly what was not enough.
"""
import datetime as dt
import json
import os
import re
import uuid

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.engines.surface_contract import EVENT_FAMILIES_REQUIRED
from tools.reconstruct_run import evidence_for, load_method, reconstruct_day, rows_for, write
from tools.run_migration import split_statements

S = "rec_core_pytest"


def rebind(sql):
    sql = sql.replace("__CORE__", S).replace("__OPS__", "ops_pytest")
    for schema in ("public", "analysis", "config", "auth"):
        sql = re.sub(rf"\b{schema}\.", f"{schema}_pytest.", sql)
        sql = re.sub(rf"\bSCHEMA {schema}\b", f"SCHEMA {schema}_pytest", sql)
    return sql


@pytest.fixture
def rec(sql_connection):
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds schemas from migration DDL; disposable local server only")
    c = sql_connection.cursor()
    for schema in (S, "analysis_pytest", "config_pytest", "auth_pytest", "public_pytest",
                   "ops_pytest"):
        c.execute(f"CREATE SCHEMA {schema}")
    c.execute("""CREATE FUNCTION auth_pytest.jwt() RETURNS jsonb LANGUAGE sql STABLE AS $$
        SELECT nullif(current_setting('request.jwt.claims', true), '')::jsonb $$""")
    for role in ("anon", "authenticated"):
        c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if c.fetchone() is None:
            c.execute(f"CREATE ROLE {role}")
    # The three legacy tables `search_record` reads. Created empty, to the shape the live
    # function expects: the point is to exercise the real function against the real column
    # names. They stay empty here — this file is about the inferred lane, and an empty
    # measured lane makes an inferred hit unambiguous.
    c.execute("""CREATE TABLE public_pytest.events (
        id BIGSERIAL PRIMARY KEY, user_id UUID, ts TIMESTAMPTZ NOT NULL, kind TEXT NOT NULL,
        payload JSONB, ingested_at TIMESTAMPTZ DEFAULT now())""")
    c.execute("""CREATE TABLE public_pytest.transactions (
        id BIGSERIAL PRIMARY KEY, user_id UUID, ts TIMESTAMPTZ NOT NULL, amount NUMERIC,
        currency TEXT, merchant TEXT, category TEXT, source TEXT, meta JSONB,
        ingested_at TIMESTAMPTZ DEFAULT now())""")
    c.execute("""CREATE TABLE public_pytest.checkins (
        id BIGSERIAL PRIMARY KEY, user_id UUID, ts TIMESTAMPTZ NOT NULL,
        checkin_date DATE, type TEXT, note TEXT, meta JSONB,
        ingested_at TIMESTAMPTZ DEFAULT now())""")
    # 0036 reaches for pg_trgm through the `extensions` schema, which is Supabase's home for
    # it. Locally the extension may already live elsewhere, so the fixture finds it rather than
    # assuming, and installs it only if it is genuinely absent.
    c.execute("SELECT extnamespace::regnamespace::text FROM pg_extension WHERE extname='pg_trgm'")
    found = c.fetchone()
    if found:
        ext = found[0]
    else:
        c.execute("CREATE SCHEMA extensions_pytest")
        c.execute("CREATE EXTENSION pg_trgm WITH SCHEMA extensions_pytest")
        ext = "extensions_pytest"

    for f in ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
              "0054_inferred_events.sql", "0055_get_reconstruction.sql",
              "0064_watch_wear_method.sql",
              # Inferred-input propagation and the second event family (REQ-REC-016).
              "0066_inferred_inputs.sql", "0067_sleep_gap_method.sql",
              # The read surface: 0036 is the measured-lane function 0065 extends.
              "0036_search_record.sql", "0065_search_reconstructions.sql"):
        for stmt in split_statements((ROOT / "migrations" / f).read_text()):
            c.execute(rebind(stmt).replace("extensions.", '"' + ext.replace('"', '""') + '".'))
    # REQ-INF-502 / atoms_metric_key_fkey: an atom whose metric has no registry row is refused,
    # which is the rule working. The fixture registers what it is about to write.
    c.execute(f"""INSERT INTO {S}.metric_registry
                  (metric_key, display_name, family, unit, state_class)
                  VALUES ('steps','Steps','activity','count','total')
                  ON CONFLICT DO NOTHING""")
    c.execute("SELECT set_config('request.jwt.claims', %s, true)",
              ('{"email":"joseph.delany21@gmail.com"}',))
    return c


def atom(c, *, day, device, metric="steps", recorded=None):
    cid, aid = uuid.uuid4(), uuid.uuid4()
    # `healthkit_workout` is the capture_source enum member 0004 reserves for HealthKit feeds;
    # `file_import` arrives later in 0051 and this fixture builds only what the reconstruction
    # path needs.
    c.execute(f"""INSERT INTO {S}.raw_captures (capture_id, source, captured_at, payload, trust_level)
                  VALUES (%s,'healthkit_workout',%s,'{{}}'::jsonb,'trusted')""",
              (cid, dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)))
    c.execute(f"""INSERT INTO {S}.atoms
        (id, raw_capture_id, kind, metric_key, occurred_at, subject_day, subject_day_rule_version,
         recorded_at, presence, value_low, value_point, value_high, estimate_method, unit,
         state_class, value_type, trust_level, provenance, evidence_span, code_version)
        VALUES (%s,%s,'measurement',%s,%s,%s,'v1',%s,'observed',1,1,1,'measured','count',
                'total','numeric','trusted','extracted',%s,'test')""",
        (aid, cid, metric, dt.datetime.combine(day, dt.time(12), dt.timezone.utc), day,
         # RULE-04 / knowledge_follows_the_event: `knowledge_time` on the reconstruction is the
         # evidence's `recorded_at`, so an atom recorded BEFORE the day it describes would make
         # the engine conclude something before its own evidence could exist. Real HealthKit
         # exports are read after the fact; the fixture matches that rather than relaxing it.
         recorded or dt.datetime.combine(day, dt.time(12), dt.timezone.utc) + dt.timedelta(days=1),
         f"apple_health:X;source=Joseph's Apple {device}"))
    return aid


def correct(c, *, day, supersedes, knowledge_time, presence="unknown", author="human",
            alternatives=None):
    """Insert a superseding interpretation.

    REQ-REC-007 binds a human correction exactly as it binds the engine: the row must disclose
    the reading it rejects. Joe saying "I was wearing it" without recording that the engine
    concluded otherwise would leave the revision history unable to show what changed and why,
    which is the whole point of keeping the superseded row.
    """
    alternatives = alternatives or [
        {"presence": "occurred", "note": "the engine's reading: the Watch contributed nothing"}]
    c.execute(f"""INSERT INTO {S}.inferred_events
        (event_family, method_key, method_version, event_time_from, event_time_to, subject_day,
         knowledge_time, tier, presence, author, supersedes, alternatives)
        VALUES ('device_state','watch_non_wear',1,%s,%s,%s,%s,'DESCRIPTIVE',%s,%s,%s,%s)
        RETURNING event_id""",
        (dt.datetime.combine(day, dt.time(0), dt.timezone.utc),
         dt.datetime.combine(day, dt.time(0), dt.timezone.utc) + dt.timedelta(days=1),
         day, knowledge_time, presence, author, supersedes, json.dumps(alternatives)))
    return c.fetchone()[0]


def test_REQ_REC_004_the_method_is_read_from_the_registry_and_an_unregistered_one_cannot_run(rec):
    """RULE-13. A method this tool does not find registered is one it may not run — the
    declaration is data, not a constant in Python, so retiring a method is a row change."""
    m = load_method(rec, "watch_non_wear", core=S, config="config_pytest")
    assert m.event_family == "device_state"
    assert set(m.required_evidence) == {"phone_capture_present", "watch_capture_absent"}
    assert m.permissible_outputs == ("occurred",)
    with pytest.raises(SystemExit, match="REQ-REC-004"):
        load_method(rec, "no_such_method", core=S, config="config_pytest")


def test_REQ_REC_006_a_method_may_not_output_what_it_did_not_declare(rec):
    """`permissible_outputs` is ARRAY['occurred'] for this method, so it has no vocabulary for
    concluding a non-wear episode did NOT happen — and `to_row` refuses before the table does."""
    from tools.engines.reconstruct import Reconstruction, to_row
    m = load_method(rec, "watch_non_wear", core=S, config="config_pytest")
    r = Reconstruction(presence="did_not_occur", tier="DESCRIPTIVE", reason="x")
    with pytest.raises(ValueError, match="REQ-REC-006"):
        to_row(r, m, event_time_from=dt.datetime.now(dt.timezone.utc),
               event_time_to=dt.datetime.now(dt.timezone.utc), subject_day=dt.date(2026, 8, 22),
               knowledge_time=dt.datetime.now(dt.timezone.utc))


def test_REQ_REC_009_a_day_with_no_capture_at_all_is_unknown_not_a_non_wear_episode(rec):
    """The single most tempting error in the feature. A day on which NOTHING captured says
    nothing about the Watch — capture as a whole was down — and there is deliberately no code
    path from missing evidence to a conclusion."""
    m = load_method(rec, "watch_non_wear", core=S, config="config_pytest")
    now = dt.datetime(2026, 8, 23, tzinfo=dt.timezone.utc)
    r, _ = reconstruct_day(m, dt.date(2026, 8, 22), watch=False, phone=False, last_recorded=now)
    assert r.presence == "unknown"
    assert r.reason == "required_evidence_missing"
    assert "phone_capture_present" in r.missing_evidence


def test_REQ_REC_008_one_export_read_twice_is_one_origin_not_two(rec):
    """The phone's presence and the Watch's absence are one HealthKit export read twice. Giving
    them separate origins made a single-source inference count as two corroborations and
    promoted every episode to EXPLORATORY — caught by reading the runner's own output against
    production, not by a unit test."""
    m = load_method(rec, "watch_non_wear", core=S, config="config_pytest")
    now = dt.datetime(2026, 8, 23, tzinfo=dt.timezone.utc)
    r, ev = reconstruct_day(m, dt.date(2026, 8, 22), watch=False, phone=True, last_recorded=now)
    assert len({e.origin_group for e in ev}) == 1
    assert r.independent_support == 1
    assert r.tier == "DESCRIPTIVE", "one origin is not two corroborations"


def test_REQ_REC_010_a_stored_reconstruction_carries_no_probability(rec):
    """A rule score and a probability are different objects. No calibration exists, so every
    reconstruction this system currently produces reports uncertainty as unquantified — a number
    here would be a made-up confidence wearing a percent sign."""
    atom(rec, day=dt.date(2026, 8, 22), device="iPhone")
    m = load_method(rec, "watch_non_wear", core=S, config="config_pytest")
    rows = rows_for(rec, m, core=S)
    assert rows, "the runner produced nothing from real atoms"
    _, r, _, row = rows[0]
    assert row["probability"] is None and row["calibration_ref"] is None
    assert row["rule_score"] is not None


def test_REQ_REC_005_012_the_full_chain_stores_the_event_and_every_citation(rec):
    """source evidence -> method -> stored event -> evidence inspection, through the real
    entry points."""
    day = dt.date(2026, 8, 22)
    atom(rec, day=day, device="iPhone")
    m = load_method(rec, "watch_non_wear", core=S, config="config_pytest")
    rows = rows_for(rec, m, core=S)
    n = write(rec, rows, core=S)
    assert n == 1

    rec.execute(f"SELECT event_id, presence, tier, method_key, subject_day FROM {S}.inferred_events")
    event_id, presence, tier, method_key, subject_day = rec.fetchone()
    assert (presence, tier, method_key, subject_day) == ("occurred", "DESCRIPTIVE",
                                                         "watch_non_wear", day)

    # REQ-REC-012. Every citation is stored, with its stance and origin.
    rec.execute(f"""SELECT stance, note, origin_group FROM {S}.event_evidence
                     WHERE event_id = %s ORDER BY note""", (event_id,))
    ev = rec.fetchall()
    assert [(st, k) for st, k, _ in ev] == [("supports", "phone_capture_present"),
                                          ("supports", "watch_capture_absent")]
    assert len({o for _, _, o in ev}) == 1

    # Evidence inspection through the real read API.
    rec.execute("SELECT public_pytest.get_reconstruction(%s)", (event_id,))
    got = rec.fetchone()[0]
    if isinstance(got, str):
        got = json.loads(got)
    assert got["found"] is not False
    assert got["presence"] == "occurred"
    assert len(got["evidence"]) == 2


def test_REQ_REC_011_a_human_correction_outranks_the_engine_and_the_engine_cannot_take_it_back(rec):
    """The engine may revise itself; it may not overwrite Joe. Without this the next scheduled
    run silently reverts every correction he ever made, and the revision history would show it
    as an improvement."""
    day = dt.date(2026, 8, 22)
    atom(rec, day=day, device="iPhone")
    m = load_method(rec, "watch_non_wear", core=S, config="config_pytest")
    write(rec, rows_for(rec, m, core=S), core=S)
    rec.execute(f"SELECT event_id, knowledge_time FROM {S}.inferred_events")
    original, k0 = rec.fetchone()

    # Joe corrects it: he was wearing it, the export was partial.
    later = k0 + dt.timedelta(days=1)
    correction = correct(rec, day=day, supersedes=original, knowledge_time=later)

    # The engine may not supersede it.
    # Otherwise well-formed: it discloses its alternatives and its knowledge postdates the
    # correction. The ONLY thing wrong with it is who wrote the row it wants to overwrite.
    rec.execute("SAVEPOINT s")
    with pytest.raises(Exception, match="REQ-REC-011"):
        correct(rec, day=day, supersedes=correction, knowledge_time=later + dt.timedelta(days=1),
                presence="occurred", author="engine")
    rec.execute("ROLLBACK TO SAVEPOINT s")

    # The current interpretation is Joe's.
    rec.execute(f"SELECT presence, author FROM {S}.v_current_events")
    assert [tuple(r) for r in rec.fetchall()] == [("unknown", "human")]


def test_RULE_02_an_inferred_event_is_never_updated_or_deleted(rec):
    day = dt.date(2026, 8, 22)
    atom(rec, day=day, device="iPhone")
    m = load_method(rec, "watch_non_wear", core=S, config="config_pytest")
    write(rec, rows_for(rec, m, core=S), core=S)
    for verb in (f"UPDATE {S}.inferred_events SET tier = 'EXPLORATORY'",
                 f"DELETE FROM {S}.inferred_events"):
        rec.execute("SAVEPOINT s")
        with pytest.raises(Exception, match="RULE-02"):
            rec.execute(verb)
        rec.execute("ROLLBACK TO SAVEPOINT s")


def test_INV_4_a_replay_sees_the_interpretation_that_was_current_THEN(rec):
    """Historical replay. The correction exists today; a replay pinned before it must return the
    engine's original conclusion, not the corrected one — otherwise every past answer silently
    improves and the record of having been wrong disappears."""
    day = dt.date(2026, 8, 22)
    atom(rec, day=day, device="iPhone")
    m = load_method(rec, "watch_non_wear", core=S, config="config_pytest")
    write(rec, rows_for(rec, m, core=S), core=S)
    rec.execute(f"SELECT event_id, knowledge_time FROM {S}.inferred_events")
    original, k0 = rec.fetchone()
    later = k0 + dt.timedelta(days=5)
    correct(rec, day=day, supersedes=original, knowledge_time=later)

    def head_as_of(known):
        rec.execute(f"""SELECT presence, author FROM {S}.inferred_events e
                         WHERE e.knowledge_time <= %s
                           AND NOT EXISTS (SELECT 1 FROM {S}.inferred_events s
                                            WHERE s.supersedes = e.event_id
                                              AND s.knowledge_time <= %s)""", (known, known))
        return [tuple(r) for r in rec.fetchall()]  # pg8000 hands back lists

    assert head_as_of(k0 + dt.timedelta(days=1)) == [("occurred", "engine")], "before the correction"
    assert head_as_of(later + dt.timedelta(days=1)) == [("unknown", "human")], "after it"


def test_REQ_REC_013_INV_5_a_reconstruction_is_never_presented_as_a_measurement(rec):
    """The stored row carries its method, its tier and its author, so a consumer reading it
    cannot mistake an inference for an observation. A purchase is not a consumption and a
    device's silence is not a fact about Joe — the row says which method concluded what, and
    that method's note says what it may not conclude."""
    day = dt.date(2026, 8, 22)
    atom(rec, day=day, device="iPhone")
    m = load_method(rec, "watch_non_wear", core=S, config="config_pytest")
    write(rec, rows_for(rec, m, core=S), core=S)
    rec.execute(f"""SELECT e.method_key, e.tier, e.author, e.probability, cm.note
                      FROM {S}.inferred_events e
                      JOIN config_pytest.reconstruction_methods cm
                        ON cm.method_key = e.method_key AND cm.method_version = e.method_version""")
    method_key, tier, author, probability, note = rec.fetchone()
    assert (method_key, tier, author) == ("watch_non_wear", "DESCRIPTIVE", "engine")
    assert probability is None
    assert "never evidence about Joe" in note
    assert "did not sleep, walk or train" in note


def test_REQ_REC_013_INV_5_a_search_hit_announces_itself_as_inferred_never_as_a_record(rec):
    """Ask/Record leg. A reconstruction that can only be fetched by an event id nobody knows is
    a stored row, not a capability — and one that surfaced looking like a measurement would be
    an inference laundered into the record, arriving through the search box."""
    day = dt.date(2026, 8, 22)
    atom(rec, day=day, device="iPhone")
    m = load_method(rec, "watch_non_wear", core=S, config="config_pytest")
    write(rec, rows_for(rec, m, core=S), core=S)

    rec.execute("SELECT public_pytest.search_record(%s, 50, now())", ("watch non wear",))
    out = rec.fetchone()[0]
    if isinstance(out, str):
        out = json.loads(out)
    hits = [h for h in out["hits"] if h["src"] == "inferred_events"]
    assert len(hits) == 1, f"the reconstruction did not surface: {out}"
    hit = hits[0]
    assert hit["kind"] == "inferred"
    assert hit["provenance"] == "inferred"
    assert hit["tier"] == "DESCRIPTIVE"
    # The VERSION travels with the method. Two versions of a method can disagree about the
    # same day, and a hit that named only "watch_non_wear" could not tell them apart.
    assert hit["method"] == "watch_non_wear v1"
    assert hit["presence"] == "occurred"
    # The rollup names the lane, so a caller cannot total inferred and measured into one count.
    assert out["by_provenance"]["inferred"] == 1


def test_INV_4_a_search_pinned_before_the_correction_still_answers_what_was_believed_then(rec):
    """The same query, two knowledge bounds, two different answers — and the earlier one is not
    silently improved by what Joe later told the system."""
    day = dt.date(2026, 8, 22)
    atom(rec, day=day, device="iPhone")
    m = load_method(rec, "watch_non_wear", core=S, config="config_pytest")
    write(rec, rows_for(rec, m, core=S), core=S)
    rec.execute(f"SELECT event_id, knowledge_time FROM {S}.inferred_events")
    original, k0 = rec.fetchone()
    later = k0 + dt.timedelta(days=5)
    correct(rec, day=day, supersedes=original, knowledge_time=later)

    def presences(known):
        rec.execute("SELECT public_pytest.search_record(%s, 50, %s)", ("watch non wear", known))
        out = rec.fetchone()[0]
        if isinstance(out, str):
            out = json.loads(out)
        return sorted(h["presence"] for h in out["hits"] if h["src"] == "inferred_events")

    assert presences(k0 + dt.timedelta(days=1)) == ["occurred"], "the engine's reading, then"
    assert presences(later + dt.timedelta(days=1)) == ["unknown"], "Joe's reading, now"


def test_REQ_REC_016_the_seven_acceptance_cases_are_EXECUTED_not_asserted(rec):
    """REQ-REC-016 says the backend SHALL EXECUTE acceptance cases across seven situations.

    The harness runs each one against this database — loading methods from the registry, letting
    the engine decide, storing through the real writer and reading back what was stored. A case
    it cannot execute is recorded open WITH ITS REASON, which the requirement permits and which
    is not the same as a case that passed.
    """
    from tools.reconstruction_acceptance import run
    report = run(rec, core=S, config="config_pytest")

    assert report["aggregate_verdict"] is None, "REQ-REC-016 forbids one verdict for seven cases"
    assert set(report["cases"]) == set(EVENT_FAMILIES_REQUIRED)
    # Every case carries a reason, so an open case is never confused with an unattempted one.
    for name, verdict in report["cases"].items():
        assert verdict in ("passed", "open"), (name, verdict)
        assert report["details"].get(name), f"{name} recorded {verdict} with no detail"
    assert report["open"] == (), f"open acceptance cases: {[ (n, report['details'][n]) for n in report['open'] ]}"


def test_REQ_REC_016_two_inferences_agreeing_do_not_promote_each_other(rec):
    """The propagation rule, stated as the failure it prevents.

    Without the cap: infer A at DESCRIPTIVE, infer B from two such inferences, and B reaches
    EXPLORATORY — the system believing something more strongly than any measurement ever
    supported, with every row in the chain individually defensible.
    """
    from tools.engines.reconstruct import Evidence, evaluate
    m = load_method(rec, "sleep_gap_explained", core=S, config="config_pytest")
    k = dt.datetime(2026, 8, 27, tzinfo=dt.timezone.utc)

    def cite(ref, kind, origin, **kw):
        return Evidence(ref=ref, kind=kind, stance="supports", origin_group=origin,
                        recorded_at=k, **kw)

    measured_twin = [cite("a", "sleep_record_absent", "origin:1"),
                     cite("b", "watch_non_wear_inferred", "origin:2")]
    assert evaluate(m, measured_twin, as_of=k).tier == "EXPLORATORY", (
        "two independent MEASURED origins are what EXPLORATORY is for")

    one_inferred = [cite("a", "sleep_record_absent", "origin:1"),
                    cite("b", "watch_non_wear_inferred", "origin:2",
                         provenance="inferred", input_tier="DESCRIPTIVE")]
    r = evaluate(m, one_inferred, as_of=k)
    assert r.independent_support == 2, "the origins really are independent"
    assert r.tier == "DESCRIPTIVE", "one inferred input caps it, however many origins agree"
    assert r.inferred_inputs == ("b",)


def test_REQ_REC_016_the_database_refuses_an_EXPLORATORY_row_that_rests_on_an_inference(rec):
    """The cap is not only in the writer. A rule that lives in one caller lasts until the
    second caller."""
    day = dt.date(2026, 8, 28)
    rec.execute("SAVEPOINT s")
    with pytest.raises(Exception, match="inferred_input_caps_the_tier"):
        rec.execute(f"""INSERT INTO {S}.inferred_events
            (event_family, method_key, method_version, event_time_from, event_time_to,
             subject_day, knowledge_time, tier, presence, author, no_alternative_generator,
             inferred_inputs)
            VALUES ('data_coverage','sleep_gap_explained',1,%s,%s,%s,%s,'EXPLORATORY','occurred',
                    'engine', true, ARRAY['inferred:something'])""",
            (dt.datetime.combine(day, dt.time(0), dt.timezone.utc),
             dt.datetime.combine(day, dt.time(0), dt.timezone.utc) + dt.timedelta(days=1),
             day, dt.datetime(2026, 8, 29, tzinfo=dt.timezone.utc)))
    rec.execute("ROLLBACK TO SAVEPOINT s")


def test_INV_5_an_inferred_citation_must_declare_the_tier_it_was_concluded_at(rec):
    """Otherwise a conclusion built on a guess cannot be held below the guess."""
    from tools.engines.reconstruct import Evidence
    with pytest.raises(ValueError, match="INV-5"):
        Evidence(ref="x", kind="k", stance="supports", origin_group="o",
                 recorded_at=dt.datetime.now(dt.timezone.utc), provenance="inferred")
    with pytest.raises(ValueError, match="only a conclusion has one"):
        Evidence(ref="x", kind="k", stance="supports", origin_group="o",
                 recorded_at=dt.datetime.now(dt.timezone.utc), input_tier="DESCRIPTIVE")
