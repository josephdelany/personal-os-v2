import test from 'node:test';
import assert from 'node:assert/strict';
import {uuidv7, offsetTimestamp, checkinRequest, mealRequest, workoutRequest,
  createPendingStore, renderDay, renderCheckins, renderSpending, renderVisits} from '../app/daily.mjs';

test('V0-CHECKIN RULE-02 UUIDv7 carries version, variant and millisecond order', () => {
  const zero = n => new Uint8Array(n);
  const a = uuidv7(1_700_000_000_000, zero), b = uuidv7(1_700_000_000_001, zero);
  assert.match(a, /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.ok(a < b);
  assert.equal(a.slice(0, 13).replace('-', ''), (1_700_000_000_000).toString(16).padStart(12, '0'));
});

test('V0-CHECKIN offset timestamps keep the local wall time and an explicit offset', () => {
  const ts = offsetTimestamp(new Date(2026, 8, 25, 7, 5, 9));
  assert.match(ts, /^2026-09-25T07:05:09[+-]\d{2}:\d{2}$/);
});

test('V0-CHECKIN ADR-0166 requests contain exactly the period keys and never prefill ratings', () => {
  const r = checkinRequest({period: 'morning', ratings: {sleep_quality: 7, energy: 6, mood: 9}, id: 'x', occurredAt: 't'});
  assert.deepEqual(r, {entry_id: 'x', supersedes: null, occurred_at: 't', period: 'morning',
    ratings: {sleep_quality: 7, energy: 6}, note: ''});
  assert.throws(() => checkinRequest({period: 'evening', ratings: {energy: 5}}), /mood/);
  assert.throws(() => checkinRequest({period: 'morning', ratings: {sleep_quality: 0, energy: 5}}), /1 to 10/);
  assert.throws(() => checkinRequest({period: 'morning', ratings: {sleep_quality: 5.5, energy: 5}}), /1 to 10/);
});

test('V0-MEAL ADR-0167 meal needs text or photo and carries corrections as supersedes', () => {
  assert.throws(() => mealRequest({text: '   '}), /Describe/);
  const r = mealRequest({text: 'eggs', supersedes: 'prev', id: 'new', occurredAt: 't'});
  assert.deepEqual(r, {entry_id: 'new', supersedes: 'prev', occurred_at: 't', text: 'eggs', photo_capture_id: null});
});

test('V0-WORKOUT ADR-0169 bodyweight has null load and assisted is not external load', () => {
  const bw = workoutRequest({exercise: 'Pull-up', mode: 'bodyweight', load: 25, unit: 'lb', reps: 8, id: 'x', occurredAt: 't'});
  assert.equal(bw.load, null); assert.equal(bw.load_unit, null);
  const as = workoutRequest({exercise: 'Dip', mode: 'assisted', load: 40, unit: 'kg', reps: 6, id: 'y', occurredAt: 't'});
  assert.equal(as.movement_mode, 'assisted'); assert.equal(as.load, 40);
  assert.throws(() => workoutRequest({exercise: 'Squat', mode: 'external_load', load: null, unit: 'lb', reps: 5}), /load/);
  assert.throws(() => workoutRequest({exercise: 'Squat', mode: 'external_load', load: 100, unit: 'lb', reps: 5, rpe: 7.3}), /RPE/);
  assert.throws(() => workoutRequest({exercise: 'Squat', mode: 'external_load', load: 100, unit: 'lb', reps: 0}), /Reps/);
});

test('V0-CALLER RULE-02 pending saves survive reload with the identical request', () => {
  const backing = new Map();
  const storage = {getItem: k => backing.get(k) ?? null, setItem: (k, v) => backing.set(k, v)};
  const request = {entry_id: 'id-1', text: 'eggs'};
  createPendingStore(storage).put('meal', request);
  const reloaded = createPendingStore(storage);
  assert.deepEqual(reloaded.list(), [{kind: 'meal', request}]);
  reloaded.remove('id-1');
  assert.deepEqual(createPendingStore(storage).list(), []);
  const broken = createPendingStore({getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }});
  broken.put('meal', request);
  assert.equal(broken.list().length, 1);
});

test('V0-DAY RULE-06 empty domains render as not logged, never zero', () => {
  const html = renderDay({day: '2026-09-25', checkins: {entries: []}, meals: {entries: []},
    workouts: {entries: []}, health: {daily_aggregates: []}, spending: {accounts: []}, visits: {processing_status: 'missing'}});
  for (const text of ['No check-in logged', 'No meals logged', 'No sets logged', 'No health data',
    'No card activity', 'No location data']) assert.ok(html.includes(text), text);
  assert.ok(!/>\s*0\s*</.test(html));
});

test('V0-DAY RULE-14 stored values render escaped without client arithmetic', () => {
  const html = renderCheckins({entries: [{entry_id: 'e', occurred_at: '2026-09-25T07:30:00-04:00',
    period: 'morning', ratings: {sleep_quality: 7, energy: 4}, note: '<b>tired</b>'}]});
  assert.ok(html.includes('sleep quality <strong>7</strong>'));
  assert.ok(html.includes('&lt;b&gt;tired'));
  assert.ok(html.includes('data-entry="e"'));
  const spend = renderSpending({accounts: [{entries: [{description: 'Cafe', amount: -4.5, currency: 'USD'},
    {description: 'Store', amount: -10, currency: 'USD', status: 'ambiguous_overlap'}]}]});
  assert.ok(spend.includes('-4.5') && spend.includes('-10'));
  assert.ok(!spend.includes('-14.5'));
  assert.ok(spend.includes('ambiguous overlap'));
});

test('V0-VISITS awaiting processing is distinguished from no data', () => {
  assert.ok(renderVisits({entries: [], processing_status: 'awaiting_derivation'}).includes('not processed yet'));
  assert.ok(renderVisits({entries: [{label: 'Gym', first_observed_at: '2026-09-25T18:00:00-04:00',
    last_observed_at: '2026-09-25T19:10:00-04:00'}]}).includes('18:00–19:10'));
});
