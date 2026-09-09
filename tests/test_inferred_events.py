"""B14R step 3: reconstructed events (REQ-REC-005..012).

An atom is what a source recorded. An inferred event is what the system CONCLUDED. The
failure mode of this whole feature is a conclusion that reads like an observation six months
later, so these tests are almost entirely about what the schema refuses.
"""
import os
import re

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.run_migration import split_statements

METHOD = ("meal_from_charge", 1)


def rebind(sql):
    return re.sub(r"\bconfig\.", "config_pytest.", sql.replace("__CORE__", "rec_core_pytest"))


@pytest.fixture
def rec(sql_connection):
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds schemas from migration DDL; disposable local server only")
    cur = sql_connection.cursor()
    for schema in ("rec_core_pytest", "config_pytest"):
        cur.execute(f"CREATE SCHEMA {schema}")
    for role in ("anon", "authenticated"):
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE ROLE {role}")
    for filename in ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
                     "0051_file_import.sql", "0054_inferred_events.sql"):
        for statement in split_statements((ROOT / "migrations" / filename).read_text()):
            cur.execute(rebind(statement))
    cur.execute("""INSERT INTO config_pytest.reconstruction_methods
        (method_key, method_version, event_family, required_evidence, permissible_outputs,
         temporal_specification, note)
        VALUES ('meal_from_charge', 1, 'meal', ARRAY['transaction'], ARRAY['occurred'],
                'interval', 'a card charge at a food merchant')""")
    return cur


def event(cur, **kw):
    base = dict(event_family="meal", method_key=METHOD[0], method_version=METHOD[1],
                event_time_from="2026-07-01T18:00:00Z", event_time_to="2026-07-01T19:00:00Z",
                subject_day="2026-07-01", tier="EXPLORATORY", presence="occurred",
                no_alternative_generator=True, author="engine")
    base.update(kw)
    cols = ", ".join(base)
    cur.execute(f"INSERT INTO rec_core_pytest.inferred_events ({cols}) "
                f"VALUES ({', '.join(['%s'] * len(base))}) RETURNING event_id",
                tuple(base.values()))
    return cur.fetchone()[0]


def refuses(cur, constraint, **kw):
    cur.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        event(cur, **kw)
    assert constraint in str(e.value), str(e.value)
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_REC_010_a_probability_without_its_calibration_is_refused(rec):
    """The central constraint. A number here with no stored calibration is a made-up
    confidence wearing a percent sign, and every consumer downstream would read it as
    measured. An uncalibrated ranking is allowed — it just may not call itself a chance."""
    refuses(rec, "probability_requires_calibration", probability=0.82)
    event(rec, rule_score=0.82)                                    # a ranking: fine
    event(rec, probability=0.82, calibration_ref="cal-2026-09")    # earned: fine


def test_REQ_REC_007_an_empty_alternative_set_must_be_stated_not_left_blank(rec):
    """Silence about alternatives is indistinguishable from having considered none."""
    refuses(rec, "alternatives_are_disclosed", no_alternative_generator=False)
    event(rec, no_alternative_generator=False,
          alternatives='[{"explanation": "someone else used the card"}]')


def test_REQ_REC_009_an_unknown_event_cannot_carry_a_confidence(rec):
    """RULE-07's three-valued presence. If coverage cannot establish that it did not happen,
    the answer is unknown — and unknown with a 0.7 attached is not unknown."""
    refuses(rec, "unknown_carries_no_score", presence="unknown", rule_score=0.7)
    event(rec, presence="unknown")


def test_RULE_04_an_event_cannot_be_concluded_before_it_happened(rec):
    refuses(rec, "knowledge_follows_the_event", knowledge_time="2020-01-01T00:00:00Z")


def test_REQ_REC_006_a_method_outside_the_registry_cannot_run(rec):
    """RULE-11/RULE-13: the model proposes; it never invents the rule or mints the number."""
    rec.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        event(rec, method_key="whatever_the_model_thought_of")
    assert "foreign key" in str(e.value).lower() or "violates" in str(e.value).lower()
    rec.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_REC_011_the_engine_may_not_supersede_a_human_correction(rec):
    """Without this the next scheduled run reverts every correction Joe ever made, and the
    revision history would present it as an improvement."""
    joe = event(rec, author="human", note="I did not eat there")
    rec.execute("SAVEPOINT s")
    with pytest.raises(Exception) as e:
        event(rec, supersedes=joe, author="engine")
    assert "REQ-REC-011" in str(e.value)
    rec.execute("ROLLBACK TO SAVEPOINT s")
    event(rec, supersedes=joe, author="human")          # Joe may revise himself


def test_REQ_REC_011_an_earlier_interpretation_survives_its_correction(rec):
    first = event(rec, note="first reading")
    second = event(rec, supersedes=first, author="human", note="corrected")
    rec.execute("SELECT count(*) FROM rec_core_pytest.inferred_events")
    assert rec.fetchone()[0] == 2, "the earlier interpretation must remain readable"
    rec.execute("SELECT event_id FROM rec_core_pytest.v_current_events")
    assert [r[0] for r in rec.fetchall()] == [second], "only the head is current"


def test_RULE_02_an_inferred_event_is_append_only(rec):
    e = event(rec)
    for verb in (f"UPDATE rec_core_pytest.inferred_events SET note='x' WHERE event_id='{e}'",
                 f"DELETE FROM rec_core_pytest.inferred_events WHERE event_id='{e}'"):
        rec.execute("SAVEPOINT s")
        with pytest.raises(Exception) as exc:
            rec.execute(verb)
        assert "RULE-02" in str(exc.value)
        rec.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_REC_008_two_copies_of_one_receipt_are_one_piece_of_evidence(rec):
    """The R5 case in INTENT_COVERAGE. A receipt copied into two sources alongside its bank
    charge is TWO origins, not three, and a reconstruction that counts three has talked
    itself into confidence it did not earn."""
    e = event(rec)
    for ref, origin in (("gmail:receipt-1", "receipt-1"),      # the receipt
                        ("drive:receipt-1-copy", "receipt-1"),  # the same receipt, copied
                        ("bank:txn-99", "bank-txn-99")):        # genuinely independent
        rec.execute("""INSERT INTO rec_core_pytest.event_evidence
            (event_id, external_ref, stance, origin_group, recorded_at)
            VALUES (%s, %s, 'supports', %s, '2026-07-02T00:00:00Z')""", (e, ref, origin))
    rec.execute("SELECT supporting_rows, independent_support "
                f"FROM rec_core_pytest.v_event_independence WHERE event_id = '{e}'")
    rows, independent = rec.fetchone()
    assert (rows, independent) == (3, 2), "duplicate copies were counted as independent"


def test_REQ_REC_007_contradicting_evidence_is_retained_not_discarded(rec):
    """R3: one source contradicts attendance. Keeping only what fits is how a reconstruction
    becomes a story."""
    e = event(rec)
    rec.execute("""INSERT INTO rec_core_pytest.event_evidence
        (event_id, external_ref, stance, origin_group, recorded_at)
        VALUES (%s,'calendar:declined','contradicts','calendar','2026-07-02T00:00:00Z')""", (e,))
    rec.execute("SELECT independent_contradiction FROM rec_core_pytest.v_event_independence "
                f"WHERE event_id = '{e}'")
    assert rec.fetchone()[0] == 1


def test_REQ_REC_005_an_inferred_event_has_no_measured_value_column(rec):
    """INV-5. The table cannot store a measurement, so a conclusion can never be read back
    as one — the separation is structural, not a convention someone has to remember."""
    rec.execute("""SELECT column_name FROM information_schema.columns
                    WHERE table_schema='rec_core_pytest' AND table_name='inferred_events'""")
    cols = {r[0] for r in rec.fetchall()}
    assert not (cols & {"value_point", "value_low", "value_high", "unit", "estimate_method"})
    assert {"event_time_from", "event_time_to", "knowledge_time"} <= cols


# ---- REQ-REC-014: the registered lineage interface (migration 0055) ----

def _install_reader(cur):
    """0055's function, with its schemas rebound. It is SECURITY DEFINER with an empty
    search_path, so every reference inside it must already be schema-qualified."""
    cur.execute("""CREATE SCHEMA IF NOT EXISTS auth_pytest""")
    cur.execute("""CREATE OR REPLACE FUNCTION auth_pytest.jwt() RETURNS jsonb
                   LANGUAGE sql STABLE AS $$
                   SELECT nullif(current_setting('request.jwt.claims', true), '')::jsonb $$""")
    for statement in split_statements((ROOT / "migrations" / "0055_get_reconstruction.sql").read_text()):
        cur.execute(re.sub(r"\bauth\.", "auth_pytest.",
                           re.sub(r"\bpublic\.", "public_pytest.", rebind(statement))))
    cur.execute("SELECT set_config('request.jwt.claims', %s, true)",
                ('{"email":"joseph.delany21@gmail.com"}',))


@pytest.fixture
def reader(rec):
    rec.execute("CREATE SCHEMA public_pytest")
    _install_reader(rec)
    return rec


def read(cur, event_id):
    cur.execute("SELECT public_pytest.get_reconstruction(%s)", (event_id,))
    return cur.fetchone()[0]


def test_REQ_REC_014_the_owner_check_is_the_same_one_the_rest_of_the_system_uses(reader):
    reader.execute("SELECT set_config('request.jwt.claims', %s, true)",
                   ('{"email":"someone.else@example.com"}',))
    reader.execute("SAVEPOINT s")
    with pytest.raises(Exception, match="owner only"):
        read(reader, event(reader))
    reader.execute("ROLLBACK TO SAVEPOINT s")


def test_REQ_REC_010_the_interface_labels_an_uncalibrated_score_as_unquantified(reader):
    """A bare rule_score handed to a caller is a number that will eventually be rendered
    with a percent sign. The kind travels with the number."""
    r = read(reader, event(reader, rule_score=0.5))
    assert r["uncertainty"]["kind"] == "unquantified"
    assert r["uncertainty"]["rule_score"] == 0.5
    assert "not a probability" in r["uncertainty"]["note"]
    assert "probability" not in r["uncertainty"]


def test_REQ_REC_010_a_calibrated_probability_travels_with_its_calibration(reader):
    r = read(reader, event(reader, probability=0.8, calibration_ref="cal-2026-09"))
    assert r["uncertainty"] == {"kind": "calibrated_probability", "probability": 0.8,
                                "calibration_ref": "cal-2026-09"}


def test_REQ_REC_008_the_interface_reports_rows_and_origins_separately(reader):
    """Two copies of one receipt are two rows and ONE origin. A caller that sees only a count
    cannot tell the difference, which is how duplicate evidence becomes corroboration."""
    e = event(reader)
    for ref, origin in (("gmail:r1", "receipt-1"), ("drive:r1-copy", "receipt-1"),
                        ("bank:t99", "bank-t99")):
        reader.execute("""INSERT INTO rec_core_pytest.event_evidence
            (event_id, external_ref, stance, origin_group, recorded_at)
            VALUES (%s,%s,'supports',%s,'2026-07-02T00:00:00Z')""", (e, ref, origin))
    r = read(reader, e)
    assert r["support"] == {"rows": 3, "independent_origins": 2}
    assert len(r["evidence"]) == 3


def test_REQ_REC_007_contradicting_evidence_arrives_without_being_asked_for(reader):
    """A caller that has to opt in to the contradicting half will render a one-sided story."""
    e = event(reader)
    reader.execute("""INSERT INTO rec_core_pytest.event_evidence
        (event_id, external_ref, stance, origin_group, recorded_at)
        VALUES (%s,'calendar:declined','contradicts','calendar','2026-07-02T00:00:00Z')""", (e,))
    r = read(reader, e)
    assert r["contradiction"]["independent_origins"] == 1
    assert any(x["stance"] == "contradicts" for x in r["evidence"])


def test_REQ_REC_011_a_superseded_event_says_so_and_names_its_replacement(reader):
    """A cached event_id would otherwise keep answering after Joe corrected it."""
    first = event(reader)
    second = event(reader, supersedes=first, author="human", note="corrected")
    old, new = read(reader, first), read(reader, second)
    assert old["is_current"] is False and old["superseded_by"] == str(second)
    assert new["is_current"] is True and new["superseded_by"] is None
    # REQ-REC-012: the chain is readable oldest first, and the human revision is visibly human.
    assert [h["author"] for h in new["revision_history"]] == ["engine", "human"]


def test_REQ_REC_014_a_missing_event_is_a_stated_absence_not_an_error(reader):
    """RULE-18: not found is an answer."""
    r = read(reader, "00000000-0000-0000-0000-000000000000")
    assert r == {"event_id": "00000000-0000-0000-0000-000000000000", "found": False}


def test_REQ_REC_014_the_answer_is_deterministic_and_names_itself_so(reader):
    """RULE-15: nothing here requires a model, and the caller can verify that claim."""
    r = read(reader, event(reader))
    assert r["deterministic"] is True
    assert r["no_alternative_generator"] is True and r["alternatives"] == []
