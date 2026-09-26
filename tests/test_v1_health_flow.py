"""ADR-0173 Data In: a real Apple Health export reaches the daily page's Health card.

The day tests insert health atoms by hand in the importer's shape. This drives the actual
drop-folder importer on a synthetic export (labeled fixture values, no personal data) into
the disposable twin, then reads the actual owner day RPC, so a drift between the importer's
writes and the day read's filters fails here instead of leaving the card silently empty.
"""
import json
import zipfile

import pytest

from tests._location_fixture import CORE, apply_chain, as_owner
from tests._sql_fixture import connect, requires_disposable
from tools import import_drop

pytestmark = requires_disposable

DAY = '2026-03-07'
EXPORT = '''<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
 <Record type="HKQuantityTypeIdentifierRestingHeartRate" sourceName="Fixture Watch" unit="count/min"
  creationDate="2026-03-07 09:00:00 -0500" startDate="2026-03-07 08:00:00 -0500" endDate="2026-03-07 08:00:00 -0500" value="58"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Fixture Watch" unit="count"
  creationDate="2026-03-07 11:00:00 -0500" startDate="2026-03-07 10:00:00 -0500" endDate="2026-03-07 10:10:00 -0500" value="1200"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Fixture Watch" unit="count"
  creationDate="2026-03-07 16:00:00 -0500" startDate="2026-03-07 15:00:00 -0500" endDate="2026-03-07 15:20:00 -0500" value="800"/>
</HealthData>
'''


@pytest.fixture(scope='module')
def imported(tmp_path_factory):
    path = tmp_path_factory.mktemp('drop') / 'export.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('apple_health_export/export.xml', EXPORT)
    conn = connect()
    try:
        cur = conn.cursor()
        apply_chain(cur)
        assert import_drop.classify(path) == 'apple_health'
        ranges = import_drop.registry_ranges(cur, CORE)
        version = import_drop.code_version_for('apple_health')
        result = import_drop.import_file(cur, CORE, path, 'apple_health', None, None, version, ranges)
        again = import_drop.import_file(cur, CORE, path, 'apple_health', None, None, version, ranges)
        cur.execute('SET LOCAL ROLE authenticated')
        as_owner(cur)
        cur.execute('SELECT public.get_v0_day(%s)', (DAY,))
        day = cur.fetchone()[0]
        yield result, (json.loads(day) if isinstance(day, str) else day), again
    finally:
        conn.rollback()
        conn.close()


def test_ADR_0173_importer_writes_the_fixture_export(imported):
    result, _, _ = imported
    assert result['status'] == 'imported', result
    assert result['atoms_written'] >= 3, result


def test_ADR_0173_RULE_03_imported_measurement_reaches_the_day_read(imported):
    _, day, _ = imported
    health = day['health']
    latest = {m['metric']: m for m in health['latest_measurements']}
    assert latest, json.dumps(health, indent=1)[:2000]
    hr = latest.get('resting_hr')
    assert hr is not None, sorted(latest)
    assert float(hr['value']) == 58 and hr['device'] == 'Watch' and hr['unit'] == 'bpm'
    assert hr['received_at'] is not None and hr['occurred_at'] is not None
    assert health['freshness']['last_received_at'] is not None


def test_ADR_0173_RULE_06_steps_are_aggregated_or_explicitly_unavailable_never_silent(imported):
    _, day, _ = imported
    health = day['health']
    daily = {a['metric']: a for a in health['daily_aggregates']}
    unavailable = {u['metric']: u['reason'] for u in health['aggregation_unavailable']}
    steps = [k for k in {**daily, **unavailable} if 'step' in k]
    print('STEPS_STATE', {k: ('aggregated', daily[k]['value']) if k in daily else ('unavailable', unavailable[k]) for k in steps})
    assert steps, json.dumps(health, indent=1)[:2000]
    for key in steps:
        if key in daily:
            assert float(daily[key]['value']) == 2000
        else:
            assert unavailable[key] in ('no_registered_daily_aggregate',
                                        'selected_contributors_have_incompatible_source_or_unit')


def test_ADR_0173_reimporting_the_same_file_writes_nothing(imported):
    _, _, again = imported
    assert again['status'] == 'skipped_duplicate_file', again
