"""B13 — the drop-folder importers (ADR-0057, ADR-0058, ADR-0059).

Every fixture in this file is generated. None of it is Joe's data, and nothing is committed:
the database tests build a disposable schema inside a transaction that always rolls back
(RULE-01's bounded exception, ADR-0022).
"""
import datetime as dt
import json
import os
import resource
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

from tests._import_fixture import build_spine
from tests._sql_fixture import sql_connection  # noqa: F401  (pytest fixture)
from tools import import_drop
from tools.importers import apple_health, bank, takeout
from tools.importers.common import AtomSpec, file_sha256, subject_day

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- generators

def health_xml(records):
    """A minimal but structurally real Apple Health export."""
    body = "\n".join(records)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
 <ExportDate value="2026-09-09 12:00:00 -0400"/>
{body}
</HealthData>
"""


def quantity(rtype, unit, value, start, end=None):
    end = end or start
    return (f' <Record type="{rtype}" sourceName="Apple Watch" unit="{unit}" '
            f'creationDate="{start}" startDate="{start}" endDate="{end}" value="{value}"/>')


def sleep_record(stage, start, end):
    return (f' <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" '
            f'creationDate="{start}" startDate="{start}" endDate="{end}" value="{stage}"/>')


# --------------------------------------------------------------------------- pure parsers

def test_ADR_0058_sleep_intervals_assign_subject_day_by_wake_day(tmp_path):
    """A night that starts on the 8th and ends on the 9th is the 9th's sleep.

    This is the whole reason sleep gets its own subject-day rule. Under the ordinary
    ADR-0019 rule (04:00 boundary applied to the *start*), a 23:40 bedtime lands on the 8th
    and the night is filed against the day before the morning it belongs to — which silently
    misaligns every sleep-versus-next-day analysis by one day.
    """
    p = tmp_path / "export.xml"
    p.write_text(health_xml([
        sleep_record("HKCategoryValueSleepAnalysisAsleepCore",
                     "2026-09-08 23:40:00 -0400", "2026-09-09 01:40:00 -0400"),
        sleep_record("HKCategoryValueSleepAnalysisAsleepDeep",
                     "2026-09-09 01:40:00 -0400", "2026-09-09 03:10:00 -0400"),
        sleep_record("HKCategoryValueSleepAnalysisAsleepREM",
                     "2026-09-09 03:10:00 -0400", "2026-09-09 07:10:00 -0400"),
    ]))
    with open(p, "rb") as fp:
        specs = list(apple_health.parse(fp))

    assert len(specs) == 3
    assert {s.metric_key for s in specs} == {"sleep_core_min", "sleep_deep_min", "sleep_rem_min"}
    # Every segment files against the WAKE day, including the ones that both start and end
    # before 04:00 — the anchor is that segment's wake instant, consistently applied.
    assert [s.subject_day for s in specs] == [dt.date(2026, 9, 9)] * 3
    assert [round(s.value) for s in specs] == [120, 90, 240]
    assert all(s.interval_start is not None and s.interval_end is not None for s in specs)
    # Contrast: the ordinary rule applied to the START instant would have filed the first
    # segment on the 8th. That one-day difference is the bug this rule prevents.
    assert subject_day(specs[0].interval_start) == dt.date(2026, 9, 8)


def test_ADR_0058_apple_health_converts_units_and_never_guesses_an_unknown_one(tmp_path):
    """A unit the type has no conversion for is dropped and counted, never assumed."""
    p = tmp_path / "export.xml"
    p.write_text(health_xml([
        quantity("HKQuantityTypeIdentifierBodyMass", "kg", "80", "2026-09-08 08:00:00 -0400"),
        quantity("HKQuantityTypeIdentifierOxygenSaturation", "%", "0.97", "2026-09-08 09:00:00 -0400"),
        quantity("HKQuantityTypeIdentifierWalkingSpeed", "km/hr", "3.6", "2026-09-08 10:00:00 -0400"),
        quantity("HKQuantityTypeIdentifierAppleSleepingWristTemperature", "degF", "95.0",
                 "2026-09-08 03:00:00 -0400"),
        # A body mass in stones: no conversion registered, so it must be dropped, never read
        # as 12.5 pounds.
        quantity("HKQuantityTypeIdentifierBodyMass", "st", "12.5", "2026-09-08 11:00:00 -0400"),
    ]))
    c = apple_health.Counters()
    with open(p, "rb") as fp:
        specs = {s.metric_key: s for s in apple_health.parse(fp, counters=c)}

    assert round(specs["weight_lb"].value, 2) == 176.37          # 80 kg
    assert round(specs["spo2_pct"].value, 1) == 97.0             # 0.97 fraction -> percent
    assert round(specs["walking_speed_m_s"].value, 3) == 1.0     # 3.6 km/h
    assert round(specs["wrist_temperature_c"].value, 2) == 35.0  # 95 degF
    assert any(k.startswith("unconvertible_unit:") and k.endswith(":st") for k in c)
    assert sum(v for k, v in c.items() if k.startswith("unconvertible_unit:")) == 1


def test_ADR_0058_iterparse_handles_a_300mb_fixture_within_memory_limit(tmp_path):
    """Peak RSS must not scale with the file.

    The real export is hundreds of megabytes. `ElementTree.parse` on 300 MB costs several
    gigabytes, which is the difference between an import that runs on Joe's Mac and one that
    is killed. The parse runs in a subprocess so the measured high-water mark belongs to this
    parse and not to some earlier test.
    """
    big = tmp_path / "export.xml"
    target = 300 * 1024 * 1024
    rec = quantity("HKQuantityTypeIdentifierHeartRate", "count/min", "72",
                   "2026-09-08 10:00:00 -0400") + "\n"
    with open(big, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<HealthData locale="en_US">\n')
        written, block = 0, rec * 1000
        while written < target:
            f.write(block)
            written += len(block)
        f.write("</HealthData>\n")
    assert big.stat().st_size >= target

    # The child reports its OWN peak. Reading RUSAGE_CHILDREN in the parent was wrong: it is a
    # monotonic maximum over every reaped child and is never reset, so `after - before` is a
    # lower bound that collapses to zero once any earlier subprocess in the suite has peaked
    # higher — and another test in this suite runs a subprocess before this one.
    child = textwrap.dedent(f"""
        import resource, sys
        sys.path.insert(0, {str(ROOT)!r})
        from tools.importers import apple_health
        n = 0
        with open({str(big)!r}, 'rb') as fp:
            for _ in apple_health.parse(fp):
                n += 1
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        scale = 1024 * 1024 if sys.platform == 'darwin' else 1024   # bytes vs kilobytes
        print(n, peak / scale)
    """)
    out = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True,
                         timeout=1800)
    assert out.returncode == 0, out.stderr[-2000:]
    n_records, peak_mb = out.stdout.split()
    peak_mb = float(peak_mb)
    assert int(n_records) > 1_000_000, "fixture should hold over a million records"
    assert peak_mb < 500, f"peak RSS {peak_mb:.0f} MB exceeds the 500 MB bound"
    assert peak_mb > 5, "a near-zero peak means the measurement, not the parser, is wrong"


def test_REQ_FIN_014_REQ_FIN_016_ADR_0059_bank_schema_detection_on_three_fixture_headers(tmp_path):
    """Three institutions, three headers, three mappings — resolved from the repository's
    mapping files (REQ-FIN-014), never inferred from the data."""
    apple = tmp_path / "apple.csv"
    apple.write_text(
        "Transaction Date,Clearing Date,Description,Merchant,Category,Type,Amount (USD)\n"
        "09/03/2026,09/05/2026,COFFEE BAR,Coffee Bar,Food,Purchase,12.34\n")
    venmo = tmp_path / "venmo.csv"
    venmo.write_text(
        "Account Statement - (@joe)\n"
        "Account Activity\n"
        ",ID,Datetime,Type,Status,Note,From,To,Amount (total)\n"
        ",1,2026-09-03T18:00:00,Payment,Complete,dinner,Joe,Sam,- $20.00\n")
    cash = tmp_path / "cash.csv"
    cash.write_text(
        "Transaction ID,Date,Transaction Type,Currency,Amount,Fee,Net Amount,Status,"
        "Notes,Name of sender/receiver,Account\n"
        "T1,2026-09-03 12:00:00,Payment,USD,-8.50,0,-8.50,COMPLETE,lunch,Deli,Cash\n")

    got = {}
    for f in (apple, venmo, cash):
        specs = list(bank.parse(f))
        assert len(specs) == 1, f.name
        got[f.stem] = specs[0]

    # Every institution lands in the ledger convention: money out is negative. Apple Card
    # writes a purchase as POSITIVE 12.34, so this assertion is the one that catches an
    # inverted sign — the failure that would silently negate every spend number.
    assert float(got["apple"].value) == -12.34
    assert float(got["venmo"].value) == -20.00
    assert float(got["cash"].value) == -8.50
    assert all(s.metric_key == "transaction_amount_usd" for s in got.values())
    assert all(s.kind == "transaction" for s in got.values())
    # Venmo's real header is not row 0; it is found, not assumed.
    assert got["venmo"].subject_day == dt.date(2026, 9, 3)


def test_REQ_FIN_015_a_file_matching_no_mapping_is_quarantined_and_parses_nothing(tmp_path, monkeypatch):
    """The header is preserved where Joe can read it, and NOT printed.

    Writing the observed header to stdout was the obvious design and is wrong: a CSV's first
    row is not always a header — Venmo's export opens with `Account Statement - (@joe)` — so it
    can be data, and this command promises counts and never contents (RULE-29). It goes to a
    local file on Joe's own machine instead, which is not egress, and the message carries only
    the path and the column count.
    """
    monkeypatch.setenv("PERSONAL_OS_DROP", str(tmp_path / "drop"))
    f = tmp_path / "mystery.csv"
    f.write_text("Col A,Col B,Col C\n1,2,3\n")
    with pytest.raises(bank.QuarantineError) as e:
        list(bank.parse(f))
    msg = str(e.value)
    assert "no_institution_mapping" in msg
    assert "3 columns" in msg
    assert "Col A" not in msg, "the message must not echo the row; it may be data, not a header"

    note = tmp_path / "drop" / "_quarantine" / "mystery.csv.header.txt"
    assert note.exists(), "the header must be preserved somewhere Joe can act on it"
    body = note.read_text()
    assert "Col A" in body and "config/institutions" in body
    # Only header-shaped rows are reproduced. The data row must not appear.
    assert "1,2,3" not in body and "'1'" not in body


def test_REQ_FIN_040_REQ_FIN_042_two_distinct_timestamps_never_one_copied(tmp_path):
    """REQ-FIN-040/042: two distinct timestamps, and never the same value written to both.

    A statement carrying a settlement date distinct from the swipe date keeps both. A
    statement whose two dates are identical carries one fact, so the settlement date is left
    absent rather than filled with a copy of the swipe — a copied `posted_at` is an invented
    observation, and a later posted row could never correct it.
    """
    distinct = tmp_path / "a.csv"
    distinct.write_text(
        "Transaction Date,Clearing Date,Description,Merchant,Category,Type,Amount (USD)\n"
        "09/03/2026,09/05/2026,BAR TAB,Bar,Food,Purchase,50.00\n")
    same = tmp_path / "b.csv"
    same.write_text(
        "Transaction Date,Clearing Date,Description,Merchant,Category,Type,Amount (USD)\n"
        "09/03/2026,09/03/2026,BAR TAB,Bar,Food,Purchase,50.00\n")

    a = list(bank.parse(distinct))[0]
    b = list(bank.parse(same))[0]
    assert "posted=2026-09-05" in a.evidence_span
    assert "posted=" not in b.evidence_span, "identical dates must not be recorded twice"
    assert a.occurred_at.date() == b.occurred_at.date() == dt.date(2026, 9, 3)

    # The dedupe key is what makes a re-imported overlapping statement a no-op: same amount,
    # same instant, same kind is the same fact. A different amount is not.
    again = list(bank.parse(distinct))[0]
    assert again.dedupe_key == a.dedupe_key
    assert b.dedupe_key != AtomSpec(kind="transaction", metric_key="transaction_amount_usd",
                                    occurred_at=b.occurred_at, value=-51.0).dedupe_key


def test_REQ_LOC_005_takeout_location_history_is_never_read(tmp_path):
    """A coordinate must never arrive through this importer.

    Refusal is asserted, not absence. The archive below *contains* location members; the
    importer must decline to open them by name and emit no atom from them, while still
    importing the Chrome member sitting beside them.
    """
    z = tmp_path / "takeout-20260909.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Takeout/Chrome/BrowserHistory.json", json.dumps({"Browser History": [
            {"title": "Example", "url": "https://example.com/a",
             "time_usec": int(dt.datetime(2026, 9, 8, 15, tzinfo=dt.timezone.utc).timestamp() * 1e6)},
        ]}))
        zf.writestr("Takeout/Location History (Timeline)/Records.json",
                    json.dumps({"locations": []}))
        zf.writestr("Takeout/Location History (Timeline)/Semantic Location History/2026/2026_SEPTEMBER.json",
                    json.dumps({"timelineObjects": []}))

    c = apple_health.Counters()
    specs = list(takeout.parse(z, counters=c))

    assert [s.kind for s in specs] == ["web_visit"]
    assert c.get("location_member_refused_REQ_LOC_005") == 2
    blob = " ".join(s.evidence_span or "" for s in specs)
    assert "Records.json" not in blob and "Location History" not in blob
    for name in ("Takeout/Location History (Timeline)/Records.json",
                 "Takeout/Location History (Timeline)/Semantic Location History/2026/2026_SEPTEMBER.json"):
        assert takeout.is_forbidden_member(name)
    assert not takeout.is_forbidden_member("Takeout/Chrome/BrowserHistory.json")


def test_ADR_0058_takeout_streams_youtube_and_chrome_without_loading_the_array(tmp_path):
    """The incremental reader must return every record of a multi-chunk array."""
    n = 5000
    base = dt.datetime(2026, 9, 8, 12, tzinfo=dt.timezone.utc)
    z = tmp_path / "takeout.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Takeout/Chrome/BrowserHistory.json", json.dumps({"Browser History": [
            {"title": f"Page {i} " + "x" * 200, "url": f"https://example.com/{i}",
             "time_usec": int((base + dt.timedelta(seconds=i)).timestamp() * 1e6)}
            for i in range(n)]}))
        zf.writestr("Takeout/YouTube and YouTube Music/history/watch-history.json", json.dumps([
            {"header": "YouTube", "title": f"Watched {i}",
             "subtitles": [{"name": "Some Channel"}],
             "time": (base + dt.timedelta(seconds=i)).isoformat().replace("+00:00", "Z")}
            for i in range(n)]))

    specs = list(takeout.parse(z))
    assert sum(1 for s in specs if s.kind == "web_visit") == n
    assert sum(1 for s in specs if s.kind == "media_play") == n
    assert all(s.metric_key is None and s.value is None for s in specs)
    assert any("domain=example.com" in (s.evidence_span or "") for s in specs)
    assert any("channel=Some Channel" in (s.evidence_span or "") for s in specs)


def test_migration_0051_adds_the_file_import_label():
    """The disposable test schema folds 'file_import' into its enum, because a label added by
    ALTER TYPE cannot be used in the same transaction. This checks the two never diverge."""
    sql = (ROOT / "migrations" / "0051_file_import.sql").read_text()
    assert "ADD VALUE IF NOT EXISTS 'file_import'" in sql


# --------------------------------------------------------------------------- database
#
# These run against the **disposable local server** only (`tools/test_local_sql.py`). They
# build the spine by executing eight real migrations, which is hundreds of statements per
# test; over a network connection to the production instance that is minutes of round trips
# per test and would push the nightly suite past its 60-minute CI budget. On the temporary
# local instance it is under a second, and it touches no production schema at all — a
# strictly better isolation posture than a rolled-back transaction against the real database.
# `.github/workflows/tests.yml` runs them in their own job with PostgreSQL 17 installed.

_needs_local_server = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds a spine from eight migrations; disposable local server only "
           "(run via tools/test_local_sql.py)")


def _drop(tmp_path, files):
    d = tmp_path / "drop"
    d.mkdir()
    for name, content in files.items():
        (d / name).write_text(content)
    return d


@_needs_local_server
def test_REQ_CAP_006_REQ_FIN_011_REQ_FIN_012_ADR_0057_same_file_twice_writes_one_capture_and_no_duplicate_atoms(sql_connection, tmp_path):
    """Idempotency is the property that makes a re-export safe.

    Joe will re-export Apple Health every time a feed breaks, and every export overlaps every
    earlier one. Without this, the second export doubles the first's atoms and every mean in
    the system moves. The file hash catches an identical file; the per-atom dedupe key catches
    an overlapping but non-identical one.
    """
    cur = sql_connection.cursor()
    core, ops = build_spine(cur)

    xml = health_xml([
        quantity("HKQuantityTypeIdentifierStepCount", "count", "500", "2026-09-08 10:00:00 -0400"),
        quantity("HKQuantityTypeIdentifierStepCount", "count", "700", "2026-09-08 11:00:00 -0400"),
        quantity("HKQuantityTypeIdentifierHeartRate", "count/min", "62", "2026-09-08 10:30:00 -0400"),
    ])
    d = _drop(tmp_path, {"export.xml": xml})
    f = d / "export.xml"

    r1 = import_drop.import_file(cur, core, f, "apple_health", None, None, "test-v1",
                                       import_drop.registry_ranges(cur, core))
    assert r1["status"] == "imported"
    assert r1["atoms_written"] == 3

    # (a) The identical file again: skipped whole, on the hash, before any parsing.
    r2 = import_drop.import_file(cur, core, f, "apple_health", None, None, "test-v1",
                                       import_drop.registry_ranges(cur, core))
    assert r2["status"] == "skipped_duplicate_file"
    assert r2["atoms_written"] == 0
    assert r2["capture_id"] == r1["capture_id"]

    # (b) A DIFFERENT file (different hash) that overlaps: the two already-stored samples are
    # recognised, and only the genuinely new one is written.
    overlap = health_xml([
        quantity("HKQuantityTypeIdentifierStepCount", "count", "500", "2026-09-08 10:00:00 -0400"),
        quantity("HKQuantityTypeIdentifierHeartRate", "count/min", "62", "2026-09-08 10:30:00 -0400"),
        quantity("HKQuantityTypeIdentifierStepCount", "count", "900", "2026-09-09 10:00:00 -0400"),
    ])
    f2 = d / "export2.xml"
    f2.write_text(overlap)
    r3 = import_drop.import_file(cur, core, f2, "apple_health", None, None, "test-v1",
                                    import_drop.registry_ranges(cur, core))
    assert r3["status"] == "imported"
    assert r3["duplicates_skipped"] == 2
    assert r3["atoms_written"] == 1

    cur.execute(f"select count(*) from {core}.atoms")
    assert cur.fetchone()[0] == 4
    cur.execute(f"select count(*) from {core}.raw_captures")
    assert cur.fetchone()[0] == 2          # one per distinct file, not per import attempt
    sql_connection.rollback()


@_needs_local_server
def test_INV_1_every_imported_atom_references_the_file_capture(sql_connection, tmp_path):
    """INV-1: every derived row traces to a raw_captures row.

    The foreign key makes an orphan impossible, so what is checked here is the stronger thing
    that could really go wrong: every atom points at *its own* file's capture, that capture is
    a `file_import` carrying that file's SHA-256, and the payload's record count matches the
    rows the file actually produced.
    """
    cur = sql_connection.cursor()
    core, ops = build_spine(cur)

    xml = health_xml([
        quantity("HKQuantityTypeIdentifierStepCount", "count", "100", "2026-09-08 10:00:00 -0400"),
        sleep_record("HKCategoryValueSleepAnalysisAsleepDeep",
                     "2026-09-08 23:40:00 -0400", "2026-09-09 01:40:00 -0400"),
    ])
    csvtext = ("Transaction Date,Clearing Date,Description,Merchant,Category,Type,Amount (USD)\n"
               "09/03/2026,09/05/2026,BAR TAB,Bar,Food,Purchase,50.00\n")
    d = _drop(tmp_path, {"export.xml": xml, "apple.csv": csvtext})

    r_h = import_drop.import_file(cur, core, d / "export.xml", "apple_health", None, None, "t",
                                  import_drop.registry_ranges(cur, core))
    r_b = import_drop.import_file(cur, core, d / "apple.csv", "bank", None, None, "t",
                                  import_drop.registry_ranges(cur, core))
    assert r_h["atoms_written"] == 2 and r_b["atoms_written"] == 1

    cur.execute(f"""select a.raw_capture_id, rc.source::text, rc.payload->>'file_sha256',
                           rc.payload->>'importer', (rc.payload->>'records_parsed')::int
                      from {core}.atoms a join {core}.raw_captures rc
                        on rc.capture_id = a.raw_capture_id""")
    rows = cur.fetchall()
    assert len(rows) == 3
    assert {r[1] for r in rows} == {"file_import"}

    by_capture = {}
    for cap, _, sha, importer, n in rows:
        by_capture.setdefault(str(cap), []).append((sha, importer, n))
    assert len(by_capture) == 2, "atoms from two files must not share one capture"
    assert by_capture[r_h["capture_id"]][0][0] == file_sha256(d / "export.xml")
    assert by_capture[r_b["capture_id"]][0][0] == file_sha256(d / "apple.csv")
    for cap_id, entries in by_capture.items():
        # `records_parsed` counts what the file yielded BEFORE dedupe and range rejection.
        # On a first import of a clean file those are equal; the name says which it is, because
        # the earlier name `n_records` read as "atoms written" and would not be on a re-import.
        assert all(n == len(entries) for _, _, n in entries), "records_parsed must match"

    cur.execute(f"""select count(*) from {core}.atoms a
                     where not exists (select 1 from {core}.raw_captures rc
                                        where rc.capture_id = a.raw_capture_id)""")
    assert cur.fetchone()[0] == 0
    sql_connection.rollback()


@_needs_local_server
def test_ADR_0057_a_window_bounds_the_import_and_the_capture_records_it(sql_connection, tmp_path):
    """`--since` is how the 43-day gap is recovered without re-importing seven years."""
    cur = sql_connection.cursor()
    core, ops = build_spine(cur)
    xml = health_xml([
        quantity("HKQuantityTypeIdentifierStepCount", "count", "1", "2024-01-01 10:00:00 -0400"),
        quantity("HKQuantityTypeIdentifierStepCount", "count", "2", "2026-07-28 10:00:00 -0400"),
        quantity("HKQuantityTypeIdentifierStepCount", "count", "3", "2026-09-08 10:00:00 -0400"),
    ])
    f = _drop(tmp_path, {"export.xml": xml}) / "export.xml"
    r = import_drop.import_file(cur, core, f, "apple_health",
                                dt.date(2026, 7, 28), dt.date(2026, 9, 8), "t",
                                import_drop.registry_ranges(cur, core))
    assert r["atoms_written"] == 2
    assert r["period"] == ["2026-07-28", "2026-09-08"]
    cur.execute(f"select min(subject_day), max(subject_day) from {core}.atoms")
    assert cur.fetchone() == [dt.date(2026, 7, 28), dt.date(2026, 9, 8)]
    sql_connection.rollback()


@_needs_local_server
def test_RULE_02_the_importer_never_updates_or_deletes(sql_connection, tmp_path):
    """RULE-02: raw_captures and atoms are append-only, and the importer's re-run path is
    additive only.

    This is now **behavioural**. Two earlier versions were a grep over `import_drop.py`'s
    source text, run against a schema whose spine omitted migration 0012 — so the tables under
    test had no append-only enforcement at all and the database work was decoration. The spine
    now installs 0012's trigger, so the assertions below are about what the database does.
    """
    cur = sql_connection.cursor()
    core, ops = build_spine(cur)
    xml = health_xml([quantity("HKQuantityTypeIdentifierStepCount", "count", "1",
                               "2026-09-08 10:00:00 -0400")])
    f = _drop(tmp_path, {"export.xml": xml}) / "export.xml"
    import_drop.import_file(cur, core, f, "apple_health", None, None, "t",
                            import_drop.registry_ranges(cur, core))

    # The append-only trigger is present and it actually refuses, for both tables and both
    # verbs. A savepoint per probe so one refusal does not poison the rest.
    # A column that really exists on each table, so the probe reaches the trigger instead of
    # failing on syntax first — a malformed UPDATE being rejected would prove nothing.
    for table, column in (("atoms", "code_version"), ("raw_captures", "processing_status")):
        for verb, sql in (("update", f"update {core}.{table} set {column} = 'enriched'"),
                          ("delete", f"delete from {core}.{table}")):
            cur.execute("SAVEPOINT probe")
            try:
                cur.execute(sql)
                raise AssertionError(f"RULE-02: {verb} on {table} was NOT refused")
            except AssertionError:
                raise
            except Exception as e:
                assert "forbidden" in str(e).lower() or "append-only" in str(e).lower(), str(e)
            finally:
                cur.execute("ROLLBACK TO SAVEPOINT probe")

    # And the row the importer wrote is still there, untouched, after all of that.
    cur.execute(f"select count(*) from {core}.atoms")
    assert cur.fetchone()[0] == 1

    # Belt and braces: the importer's own source issues no mutating statement against either
    # table, in the interpolated form the file actually uses.
    src = (ROOT / "tools" / "import_drop.py").read_text().lower()
    verbs = ("upd" + "ate", "del" + "ete from")
    tables = ("{schema}.atoms", "{schema}.raw_captures", f"{core}.atoms",
              f"{core}.raw_captures", "core.atoms", "core.raw_captures")
    for verb in verbs:
        for table in tables:
            assert f"{verb} {table}" not in src, f"RULE-02: {verb} {table} in import_drop.py"
    sql_connection.rollback()


def test_ADR_0058_a_nap_is_its_own_session_and_does_not_join_the_following_night(tmp_path):
    """Session grouping must divide sleep by the gap between segments, not by the clock.

    An afternoon nap and that night's sleep are separate facts about separate parts of the
    day. If they were grouped into one session, the nap would inherit the night's wake day
    and be filed as sleep for the following morning — a nap on the 8th silently becoming
    sleep for the 9th.
    """
    p = tmp_path / "export.xml"
    p.write_text(health_xml([
        # Nap: 15:00-15:40 on the 8th. Wake instant is on the 8th.
        sleep_record("HKCategoryValueSleepAnalysisAsleepCore",
                     "2026-09-08 15:00:00 -0400", "2026-09-08 15:40:00 -0400"),
        # Night: 23:40 on the 8th -> 07:10 on the 9th, in two segments.
        sleep_record("HKCategoryValueSleepAnalysisAsleepCore",
                     "2026-09-08 23:40:00 -0400", "2026-09-09 03:00:00 -0400"),
        sleep_record("HKCategoryValueSleepAnalysisAsleepREM",
                     "2026-09-09 03:00:00 -0400", "2026-09-09 07:10:00 -0400"),
    ]))
    with open(p, "rb") as fp:
        specs = list(apple_health.parse(fp))

    assert [s.subject_day for s in specs] == [
        dt.date(2026, 9, 8),    # the nap keeps its own day
        dt.date(2026, 9, 9),    # both night segments take the wake day
        dt.date(2026, 9, 9),
    ]
    # Two segments separated by less than the session gap are one night even across midnight.
    night = [s for s in specs if s.subject_day == dt.date(2026, 9, 9)]
    assert len(night) == 2
    assert round(sum(s.value for s in night)) == 450


def test_ADR_0058_out_of_range_values_are_dropped_and_never_clamped(tmp_path):
    """RULE-01/RULE-06: an impossible reading is a gap, not the nearest legal value.

    This asserts the choke point `import_drop.bounded`, which every importer's output passes
    through. Two earlier versions of this test were weaker than their name: the first called
    a predicate the importer never invoked, and the second passed a hand-written bounds dict
    to a parser argument that defaulted to None everywhere else in the suite.
    """
    from tools.importers.apple_health import Counters
    from tools.import_drop import bounded

    ranges = {"heart_rate_bpm": (25.0, 230.0), "spo2_pct": (70.0, 100.0),
              "weight_lb": (50.0, 800.0), "sleep_deep_min": (0.0, 1440.0)}
    now = dt.datetime(2026, 9, 8, 14, tzinfo=dt.timezone.utc)
    specs = [
        AtomSpec(kind="vital_sample", metric_key="heart_rate_bpm", occurred_at=now, value=62,
                 unit="bpm", state_class="measurement", estimate_method="measured"),
        AtomSpec(kind="vital_sample", metric_key="heart_rate_bpm", occurred_at=now, value=9999,
                 unit="bpm", state_class="measurement", estimate_method="measured"),
        AtomSpec(kind="vital_sample", metric_key="heart_rate_bpm", occurred_at=now, value=0,
                 unit="bpm", state_class="measurement", estimate_method="measured"),
        AtomSpec(kind="vital_sample", metric_key="spo2_pct", occurred_at=now, value=0.5,
                 unit="pct", state_class="measurement", estimate_method="measured"),
        AtomSpec(kind="sleep", metric_key="sleep_deep_min", interval_start=now,
                 interval_end=now + dt.timedelta(days=22), value=31680, unit="min",
                 state_class="total", estimate_method="measured"),
        # An event atom has no value and no metric: it must pass through untouched.
        AtomSpec(kind="web_visit", metric_key=None, occurred_at=now),
        # A metric with no registry bounds is not rejected for lacking them.
        AtomSpec(kind="activity_sample", metric_key="unbounded_metric", occurred_at=now,
                 value=1e9, unit="count", state_class="total", estimate_method="measured"),
    ]
    c = Counters()
    kept = list(bounded(specs, ranges, c))

    assert [(k.metric_key, k.value) for k in kept] == [
        ("heart_rate_bpm", 62), (None, None), ("unbounded_metric", 1e9)]
    assert c.get("out_of_range:heart_rate_bpm") == 2
    assert c.get("out_of_range:spo2_pct") == 1
    assert c.get("out_of_range:sleep_deep_min") == 1
    for k in kept:
        assert k.value not in (25.0, 230.0, 70.0, 100.0, 0.0, 1440.0), "clamping is fabrication"


def test_REQ_FIN_010_two_distinct_same_day_same_amount_transactions_are_both_kept(tmp_path):
    """Two $20 payments on one day, to different people, are two facts.

    This is ordinary data — two identical fares, two identical coffees, a $20 payment to each
    of two friends — and the first version of the dedupe key collapsed them: it keyed on
    (kind, metric_key, instant, value) with merchant and descriptor excluded, and `_localise`
    overwrote Venmo's real timestamp with noon, erasing the only remaining discriminator. The
    second payment was silently dropped and counted as a duplicate.
    """
    f = tmp_path / "venmo.csv"
    f.write_text(
        "Account Statement - (@joe)\n"
        ",ID,Datetime,Type,Status,Note,From,To,Amount (total)\n"
        ",1,2026-09-03T18:00:00,Payment,Complete,coffee,Joe,Sam,- $20.00\n"
        ",2,2026-09-03T21:30:00,Payment,Complete,dinner,Joe,Alex,- $20.00\n")
    specs = list(bank.parse(f))
    assert len(specs) == 2
    assert len({s.dedupe_key for s in specs}) == 2, "distinct transactions must not collide"
    # The real clock time is preserved, not replaced with a noon anchor.
    assert [s.occurred_at.hour for s in specs] == [18, 21]
    assert [s.time_precision for s in specs] == ["minute", "minute"]

    # Even at the SAME instant, a different counterparty is a different fact.
    g = tmp_path / "venmo2.csv"
    g.write_text(
        ",ID,Datetime,Type,Status,Note,From,To,Amount (total)\n"
        ",1,2026-09-03T18:00:00,Payment,Complete,split,Joe,Sam,- $20.00\n"
        ",2,2026-09-03T18:00:00,Payment,Complete,split,Joe,Alex,- $20.00\n")
    two = list(bank.parse(g))
    assert len({s.dedupe_key for s in two}) == 2

    # A date-only source still gets the noon anchor and says so.
    apple = tmp_path / "apple.csv"
    apple.write_text(
        "Transaction Date,Clearing Date,Description,Merchant,Category,Type,Amount (USD)\n"
        "09/03/2026,09/05/2026,COFFEE,Coffee Bar,Food,Purchase,12.34\n")
    a = list(bank.parse(apple))[0]
    assert a.time_precision == "day" and a.occurred_at.hour == 12


def test_ADR_0059_parenthesised_amounts_and_ambiguous_formats(tmp_path):
    """Sign and separator handling, which is where money goes silently wrong."""
    from tools.importers.bank import parse_amount
    # Parentheses negate within the STATEMENT's convention, and only then is amount_sign
    # applied. On Apple Card (positive_is_outflow) a charge is written positive, so a
    # bracketed value is a REFUND — money in — which is +12.34 in the ledger convention.
    # A previous "fix" here returned -12.34, storing refunds as charges, and this assertion
    # stated that wrong value under a comment describing the right one.
    assert parse_amount("(12.34)", "positive_is_outflow") == 12.34     # refund: money IN
    assert parse_amount("12.34", "positive_is_outflow") == -12.34      # charge: money OUT
    assert parse_amount("-12.34", "positive_is_outflow") == 12.34
    assert parse_amount("(12.34)", "negative_is_outflow") == -12.34
    assert parse_amount("1234.56-", "negative_is_outflow") == -1234.56
    assert parse_amount("$1,234,567.89", "negative_is_outflow") == 1234567.89
    # Ambiguous separators are refused, never guessed. Reading "1.234,56" as US turns a
    # €1,234.56 charge into $1.23.
    for ambiguous in ("1.234,56", "1 234,56", "1,56", "50.5.7"):
        assert parse_amount(ambiguous, "negative_is_outflow") is None, ambiguous
    # Anything that is not a number is refused rather than having its letters deleted.
    for junk in ("$100.00 CR", "100.00 DR", "(12.34", "12.34)", "--12.34", "1e3"):
        assert parse_amount(junk, "positive_is_outflow") is None, junk


def test_ADR_0059_an_ambiguous_institution_match_is_quarantined_not_guessed(tmp_path):
    """Two mappings matching equally must refuse, because they can disagree about the sign."""
    mdir = tmp_path / "mappings"
    mdir.mkdir()
    for name, sign in (("aaa_bank", "negative_is_outflow"), ("zzz_bank", "positive_is_outflow")):
        (mdir / f"{name}.yaml").write_text(
            f"institution: {name}\ncolumns:\n  occurred_at: Date\n  amount: Amount\n"
            f"date_formats: ['%Y-%m-%d']\namount_sign: {sign}\n")
    f = tmp_path / "x.csv"
    f.write_text("Date,Amount\n2026-09-03,10.00\n")
    with pytest.raises(bank.QuarantineError) as e:
        list(bank.parse(f, mapping_dir=mdir))
    assert "ambiguous_institution_mapping" in str(e.value)
    assert "aaa_bank" in str(e.value) and "zzz_bank" in str(e.value)


def test_REQ_LOC_005_a_malformed_takeout_member_fails_loudly_and_is_not_half_imported(tmp_path):
    """A malformed record must raise, not silently truncate the import.

    The first version treated every decode failure as "incomplete at the buffer edge", read to
    EOF and returned what it had. One bad record part-way through a history file therefore
    discarded every record after it with no error — and because idempotency keyed on the file
    hash, the archive could never be re-imported to recover them.
    """
    import io
    from tools.importers.takeout import MalformedJSON, iter_json_objects

    good = json.dumps({"Browser History": [{"t": i} for i in range(500)]})
    bad = good.replace('{"t": 2}', '{"t": ,2}', 1)
    with pytest.raises(MalformedJSON):
        list(iter_json_objects(io.BytesIO(bad.encode())))

    # A truncated download must also raise rather than report a short but plausible import.
    with pytest.raises(MalformedJSON):
        list(iter_json_objects(io.BytesIO(good[:len(good) // 2].encode())))

    # A top-level shape this reader cannot stream is an error, not an empty result.
    with pytest.raises(MalformedJSON):
        list(iter_json_objects(io.BytesIO(b'{"a": 1}')))

    # A "[" inside a string value must not be mistaken for the array.
    tricky = json.dumps({"note": "see [here]", "Browser History": [{"t": 1}, {"t": 2}]})
    assert len(list(iter_json_objects(io.BytesIO(tricky.encode())))) == 2
    # An genuinely empty array is not an error.
    assert list(iter_json_objects(io.BytesIO(json.dumps({"Browser History": []}).encode()))) == []


def test_ADR_0058_multibyte_titles_survive_every_read_boundary(tmp_path):
    """Stored evidence must be what the source said.

    Decoding each raw chunk independently splits multibyte characters across read boundaries
    and `errors='replace'` writes U+FFFD into a title that is then stored verbatim in
    `core.atoms.evidence_span`, indistinguishable from the real text.
    """
    import io
    from tools.importers.takeout import iter_json_objects
    recs = [{"title": f"café 😀 {i} — naïve", "t": i} for i in range(60)]
    payload = json.dumps({"Browser History": recs}).encode()
    for chunk in (7, 13, 64, 1024, 1 << 20):
        got = list(iter_json_objects(io.BytesIO(payload), chunk=chunk))
        assert len(got) == 60, chunk
        assert not any("�" in g["title"] for g in got), f"corruption at chunk={chunk}"
        assert got[0]["title"] == "café 😀 0 — naïve"


@_needs_local_server
def test_INV_1_takeout_event_atoms_are_written_with_no_metric_and_no_value(sql_connection, tmp_path):
    """The Takeout path writes a structurally different atom, and had no database test.

    A `web_visit` / `media_play` atom carries `metric_key = NULL` and no value at all — it
    records that something happened, and inventing a duration for a page visit would be a
    fabricated quantity. That INSERT exercises different constraints from every other importer
    (`atoms_value_has_lane`, `atoms_unknown_has_no_value`, the metric_key foreign key), and no
    test drove it through `insert_atoms` until this one.
    """
    cur = sql_connection.cursor()
    core, ops = build_spine(cur)

    base = dt.datetime(2026, 9, 8, 15, tzinfo=dt.timezone.utc)
    z = tmp_path / "takeout-x.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Takeout/Chrome/BrowserHistory.json", json.dumps({"Browser History": [
            {"title": "Example page", "url": "https://example.com/a",
             "time_usec": int(base.timestamp() * 1e6)},
            {"title": "Another", "url": "https://other.test/b",
             "time_usec": int((base + dt.timedelta(minutes=5)).timestamp() * 1e6)},
        ]}))
        zf.writestr("Takeout/YouTube and YouTube Music/history/watch-history.json", json.dumps([
            {"header": "YouTube", "title": "Watched something",
             "subtitles": [{"name": "A Channel"}],
             "time": base.isoformat().replace("+00:00", "Z")},
        ]))
        zf.writestr("Takeout/Location History (Timeline)/Records.json", json.dumps({"locations": []}))

    r = import_drop.import_file(cur, core, z, "takeout", None, None, "t",
                                import_drop.registry_ranges(cur, core))
    assert r["status"] == "imported"
    assert r["atoms_written"] == 3

    cur.execute(f"""select kind, metric_key, value_point, value_low, value_high,
                           estimate_method, state_class, presence::text
                      from {core}.atoms order by kind""")
    rows = cur.fetchall()
    assert len(rows) == 3
    for kind, mk, vp, vl, vh, em, sc, presence in rows:
        assert kind in ("web_visit", "media_play")
        assert mk is None and vp is None and vl is None and vh is None
        assert em is None and sc is None
        assert presence == "observed"

    # No location member contributed anything (REQ-LOC-005).
    cur.execute(f"select count(*) from {core}.atoms where kind = 'location_fix'")
    assert cur.fetchone()[0] == 0
    cur.execute(f"select evidence_span from {core}.atoms")
    for (ev,) in cur.fetchall():
        assert "Location History" not in (ev or "")

    # Re-importing the identical archive writes nothing new.
    again = import_drop.import_file(cur, core, z, "takeout", None, None, "t",
                                    import_drop.registry_ranges(cur, core))
    assert again["status"] == "skipped_duplicate_file"
    cur.execute(f"select count(*) from {core}.atoms")
    assert cur.fetchone()[0] == 3
    sql_connection.rollback()


@_needs_local_server
def test_ADR_0057_a_widened_window_can_reimport_the_same_export(sql_connection, tmp_path):
    """Importing a bounded window must not burn the export.

    The documented primary use is `--since 2026-07-28` against a seven-year Apple Health
    export to recover the gap. Keying idempotency on the file hash alone meant that afterwards
    the rest of that export could never be read — the only remedy being to delete a
    `raw_captures` row, which RULE-02 forbids. The window is part of what was imported, so it
    is part of the import's identity.
    """
    cur = sql_connection.cursor()
    core, ops = build_spine(cur)
    xml = health_xml([
        quantity("HKQuantityTypeIdentifierStepCount", "count", "1", "2024-01-01 10:00:00 -0400"),
        quantity("HKQuantityTypeIdentifierStepCount", "count", "2", "2026-07-28 10:00:00 -0400"),
        quantity("HKQuantityTypeIdentifierStepCount", "count", "3", "2026-09-08 10:00:00 -0400"),
    ])
    f = _drop(tmp_path, {"export.xml": xml}) / "export.xml"

    ranges = import_drop.registry_ranges(cur, core)
    narrow = import_drop.import_file(cur, core, f, "apple_health",
                                     dt.date(2026, 7, 28), None, "t", ranges)
    assert narrow["atoms_written"] == 2

    # Same file, same window -> still a no-op.
    assert import_drop.import_file(cur, core, f, "apple_health", dt.date(2026, 7, 28), None,
                                   "t", ranges)["status"] == "skipped_duplicate_file"

    # Same file, WIDER window -> the rest is importable, and the overlap is not doubled.
    wide = import_drop.import_file(cur, core, f, "apple_health", None, None, "t", ranges)
    assert wide["status"] == "imported"
    assert wide["duplicates_skipped"] == 2
    assert wide["atoms_written"] == 1
    cur.execute(f"select count(*) from {core}.atoms")
    assert cur.fetchone()[0] == 3
    sql_connection.rollback()


@_needs_local_server
def test_ADR_0057_one_failing_file_does_not_abort_the_run(sql_connection, tmp_path):
    """A per-file failure must be reported, not crash the command.

    Without a SAVEPOINT per file, one Postgres error leaves the transaction in a failed state,
    every later statement raises 25P02, and the command dies with a traceback — losing the
    per-file report and every file that had already succeeded.
    """
    cur = sql_connection.cursor()
    core, ops = build_spine(cur)
    xml = health_xml([quantity("HKQuantityTypeIdentifierStepCount", "count", "5",
                               "2026-09-08 10:00:00 -0400")])
    f = _drop(tmp_path, {"export.xml": xml}) / "export.xml"

    cur.execute("SAVEPOINT sp_bad")
    try:
        # A metric with no registry row violates the foreign key: a real per-file failure.
        import_drop.insert_atoms(cur, core, __import__("uuid").uuid4(), [
            AtomSpec(kind="activity_sample", metric_key="not_registered_anywhere",
                     occurred_at=dt.datetime(2026, 9, 8, 12, tzinfo=dt.timezone.utc),
                     value=1, unit="count", state_class="total", estimate_method="measured")
        ], "t")
        raise AssertionError("expected a foreign-key violation")
    except AssertionError:
        raise
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT sp_bad")

    # The transaction is usable again, and a good file still imports.
    ok = import_drop.import_file(cur, core, f, "apple_health", None, None, "t",
                                 import_drop.registry_ranges(cur, core))
    assert ok["status"] == "imported" and ok["atoms_written"] == 1

    # And the ops.runs write that follows the per-file loop succeeds.
    cur.execute(f"""insert into {ops}.runs (job_name, finished_at, status, rows_written, detail)
                    values ('import_drop', now(), 'error', 0, '{{}}'::jsonb)""")
    cur.execute(f"select count(*) from {ops}.runs where job_name='import_drop'")
    assert cur.fetchone()[0] == 1
    sql_connection.rollback()


def test_REQ_FIN_013_REQ_FIN_010_ofx_is_parsed_by_ofxtools_with_two_timestamps(tmp_path):
    """REQ-FIN-010/013: OFX/QFX/QBO are accepted, and parsed by `ofxtools`.

    This path had no test at all until now, because the dependency was justified in ADR-0059
    but not installed — so the code had never once been executed. It also had a REQ-FIN-042
    violation that only running it would show: the first version wrote `DTPOSTED` (settlement)
    into `occurred_at`, which is the field the behavioural layer reads.
    """
    pytest.importorskip("ofxtools", reason="REQ-FIN-013 requires ofxtools; see ADR-0059 §5")

    qfx = tmp_path / "statement.qfx"
    qfx.write_text(
        "OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\n"
        "ENCODING:USASCII\r\nCHARSET:1252\r\nCOMPRESSION:NONE\r\nOLDFILEUID:NONE\r\n"
        "NEWFILEUID:NONE\r\n\r\n"
        "<OFX><SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS>"
        "<DTSERVER>20260909120000<LANGUAGE>ENG</SONRS></SIGNONMSGSRSV1>"
        "<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>"
        "<STMTRS><CURDEF>USD<BANKACCTFROM><BANKID>123456789<ACCTID>000111222333"
        "<ACCTTYPE>CHECKING</BANKACCTFROM><BANKTRANLIST>"
        "<DTSTART>20260901<DTEND>20260909"
        # A transaction whose swipe (DTUSER) and settlement (DTPOSTED) genuinely differ.
        "<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260905120000<DTUSER>20260903183000"
        "<TRNAMT>-42.50<FITID>A1<NAME>COFFEE BAR<MEMO>card purchase</STMTTRN>"
        # A transaction carrying only a settlement date.
        "<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260907120000"
        "<TRNAMT>-13.25<FITID>A2<NAME>DELI<MEMO>card purchase</STMTTRN>"
        "</BANKTRANLIST><LEDGERBAL><BALAMT>100.00<DTASOF>20260909120000</LEDGERBAL>"
        "</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>\r\n")

    specs = sorted(bank.parse(qfx), key=lambda s: s.value)
    assert len(specs) == 2
    assert all(s.kind == "transaction" and s.metric_key == "transaction_amount_usd" for s in specs)
    assert [float(s.value) for s in specs] == [-42.50, -13.25]

    swipe = specs[0]
    # REQ-FIN-040/042: the SWIPE is occurred_at. Writing settlement here is what the first
    # version did, and it puts the wrong date in the field behavioural analysis reads.
    assert swipe.occurred_at.date() == dt.date(2026, 9, 3)
    assert swipe.occurred_at.hour == 18
    assert "posted=2026-09-05" in swipe.evidence_span
    assert swipe.time_precision == "minute"

    settle_only = specs[1]
    # Only one date was available, so it is recorded once and never copied into both.
    assert settle_only.occurred_at.date() == dt.date(2026, 9, 7)
    assert "posted=" not in settle_only.evidence_span
    assert settle_only.time_precision == "day"

    # The account number never leaves in full — only the last four.
    assert "000111222333" not in (swipe.evidence_span or "")
    assert "account=2333" in swipe.evidence_span


@_needs_local_server
def test_RULE_01_registry_bounds_are_loaded_and_applied_to_every_importer(sql_connection, tmp_path):
    """The wiring itself, which was the untested half of the range-rejection fix.

    The first fix put the check inside the Apple Health parser with the bounds argument
    defaulted to None, so every caller in the suite silently ran with rejection OFF and a
    9999 bpm heart rate was still stored as a `measured` atom. It also never applied to sleep
    segments or to transactions. This drives `import_file` exactly as the CLI does — bounds
    loaded from `core.metric_registry` — and asserts all three importers are covered.
    """
    cur = sql_connection.cursor()
    core, ops = build_spine(cur)
    ranges = import_drop.registry_ranges(cur, core)
    # The bounds are the migration's, not the test's.
    assert ranges["heart_rate_bpm"] == (25.0, 230.0)
    assert ranges["sleep_deep_min"] == (0.0, 1440.0)

    xml = health_xml([
        quantity("HKQuantityTypeIdentifierHeartRate", "count/min", "62", "2026-09-08 10:00:00 -0400"),
        quantity("HKQuantityTypeIdentifierHeartRate", "count/min", "9999", "2026-09-08 10:01:00 -0400"),
        quantity("HKQuantityTypeIdentifierHeartRate", "count/min", "0", "2026-09-08 10:02:00 -0400"),
        # A 22-day "deep sleep" segment: sleep bypassed the check entirely before.
        sleep_record("HKCategoryValueSleepAnalysisAsleepDeep",
                     "2026-08-17 23:00:00 -0400", "2026-09-08 23:00:00 -0400"),
        sleep_record("HKCategoryValueSleepAnalysisAsleepREM",
                     "2026-09-08 23:10:00 -0400", "2026-09-09 01:10:00 -0400"),
    ])
    f = _drop(tmp_path, {"export.xml": xml}) / "export.xml"
    r = import_drop.import_file(cur, core, f, "apple_health", None, None, "t", ranges)

    cur.execute(f"select metric_key, value_point from {core}.atoms order by metric_key")
    stored = cur.fetchall()
    assert [k for k, _ in stored] == ["heart_rate_bpm", "sleep_rem_min"]
    assert float(stored[0][1]) == 62.0
    assert float(stored[1][1]) == 120.0
    assert r["counters"].get("out_of_range:heart_rate_bpm") == 2
    assert r["counters"].get("out_of_range:sleep_deep_min") == 1
    # Nothing was clamped to a bound.
    for _, v in stored:
        assert float(v) not in (25.0, 230.0, 0.0, 1440.0)

    # Transactions are covered too: transaction_amount_usd has a registry range.
    csvtext = ("Transaction Date,Clearing Date,Description,Merchant,Category,Type,Amount (USD)\n"
               "09/03/2026,09/05/2026,SANE,Bar,Food,Purchase,50.00\n"
               "09/03/2026,09/05/2026,ABSURD,Bar,Food,Purchase,99999999.00\n")
    g = tmp_path / "apple.csv"
    g.write_text(csvtext)
    rb = import_drop.import_file(cur, core, g, "bank", None, None, "t", ranges)
    assert rb["atoms_written"] == 1
    assert rb["counters"].get("out_of_range:transaction_amount_usd") == 1
    sql_connection.rollback()


@_needs_local_server
def test_ADR_0057_the_dedupe_key_does_not_depend_on_the_session_timezone(sql_connection, tmp_path):
    """The key must be a property of the instant, not of who is looking at it.

    Python renders an Apple timestamp with the offset the file carried (`-04:00`); pg8000
    renders the same `timestamptz` in the database session's `TimeZone`, which is UTC on
    Supabase and on every CI runner. Comparing those two strings never matches, so nothing is
    ever recognised as a duplicate and every overlapping re-export writes its samples again —
    reporting `duplicates_skipped: 0` as though that were good news. The original tests passed
    only because this machine's session happened to share a zone with the fixture data.
    """
    cur = sql_connection.cursor()
    core, ops = build_spine(cur)
    ranges = import_drop.registry_ranges(cur, core)
    xml = health_xml([
        quantity("HKQuantityTypeIdentifierStepCount", "count", "500", "2026-09-08 10:00:00 -0400"),
        quantity("HKQuantityTypeIdentifierStepCount", "count", "700", "2026-09-08 11:00:00 -0400"),
    ])
    d = _drop(tmp_path, {"export.xml": xml})
    first = d / "export.xml"
    import_drop.import_file(cur, core, first, "apple_health", None, None, "t", ranges)

    # A second, differently-named file with overlapping content, read back under a session
    # timezone that is NOT the one the fixture was written in.
    for zone in ("UTC", "Asia/Tokyo", "America/Los_Angeles", "America/New_York"):
        cur.execute(f"set timezone = '{zone}'")
        second = d / f"export_{zone.replace('/', '_')}.xml"
        # Distinct bytes so the file hash cannot short-circuit; the per-atom key is what is
        # under test here, not the file-level one.
        second.write_text(xml.replace("<HealthData", f"<!-- {zone} --><HealthData"))
        r = import_drop.import_file(cur, core, second, "apple_health", None, None, "t", ranges)
        assert r["duplicates_skipped"] == 2, f"session timezone {zone} broke the dedupe key"
        assert r["atoms_written"] == 0, f"session timezone {zone} doubled the data"

    cur.execute("set timezone = 'UTC'")
    cur.execute(f"select count(*) from {core}.atoms")
    assert cur.fetchone()[0] == 2
    sql_connection.rollback()


def test_RULE_29_the_quarantine_note_never_writes_statement_rows(tmp_path, monkeypatch):
    """A quarantine must not spill the file it refused to parse.

    The first version wrote the first five rows verbatim — real transactions, merchants and
    amounts — to a file, and did so on a dry run, contradicting this tool's promise that
    without `--commit` nothing is written. Only header-shaped rows are reproduced now.
    """
    monkeypatch.setenv("PERSONAL_OS_DROP", str(tmp_path / "drop"))
    f = tmp_path / "venmo_like.csv"
    f.write_text(
        "Account Statement - (@joe)\n"
        "Mystery A,Mystery B,Mystery C\n"
        "2026-09-03,Sam Wilson,- $420.00\n"
        "2026-09-04,Alex Chen,- $69.00\n")
    with pytest.raises(bank.QuarantineError):
        list(bank.parse(f))

    note = tmp_path / "drop" / "_quarantine" / "venmo_like.csv.header.txt"
    body = note.read_text()
    assert "Mystery A" in body, "the header candidate must be preserved"
    for leaked in ("Sam Wilson", "Alex Chen", "420.00", "69.00", "@joe"):
        assert leaked not in body, f"{leaked!r} leaked into the quarantine note"


def test_RULE_29_the_quarantine_note_is_never_written_inside_the_repository(tmp_path, monkeypatch):
    """If the drop folder ever pointed into the working tree, a file of statement rows would
    be committable — and `validate_layout.py` only fails on .parquet/.csv/.db/.sqlite."""
    monkeypatch.setenv("PERSONAL_OS_DROP", str(ROOT / "some_drop_dir"))
    f = tmp_path / "x.csv"
    f.write_text("Alpha,Beta\n1,2\n")
    with pytest.raises(bank.QuarantineError) as e:
        list(bank.parse(f))
    assert "inside the repository" in str(e.value)
    assert not (ROOT / "some_drop_dir").exists(), "nothing may be created inside the repo"
