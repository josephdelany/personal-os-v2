// Daily V1 surface: Today, Add and History over the V0 owner RPCs.
// Renders only stored values (no client arithmetic); missing stays "not logged".
import {createV0Client} from './v0_client.mjs';

export const esc = value => String(value ?? '').replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// RFC 9562 UUIDv7: 48-bit Unix milliseconds, version 7, variant 10, random tail.
export function uuidv7(now = Date.now(), random = n => crypto.getRandomValues(new Uint8Array(n))) {
  const b = random(16);
  let ms = BigInt(now);
  for (let i = 5; i >= 0; i--) { b[i] = Number(ms & 0xffn); ms >>= 8n; }
  b[6] = (b[6] & 0x0f) | 0x70;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
}

// Local wall time with explicit offset, as the save RPCs require.
export function offsetTimestamp(date = new Date()) {
  const p = n => String(Math.trunc(Math.abs(n))).padStart(2, '0');
  const off = -date.getTimezoneOffset();
  return `${date.getFullYear()}-${p(date.getMonth()+1)}-${p(date.getDate())}T${p(date.getHours())}:` +
    `${p(date.getMinutes())}:${p(date.getSeconds())}${off >= 0 ? '+' : '-'}${p(off/60)}:${p(off%60)}`;
}

// Request builders mirror the exact CAPTURE_RUNTIME contracts. Validation here only
// gives earlier feedback; the server remains the authority.
export function checkinRequest({period, ratings, note = '', supersedes = null, occurredAt, id = uuidv7()}) {
  const keys = {morning: ['sleep_quality','energy'], evening: ['mood','energy']}[period];
  if (!keys) throw new Error('Choose morning or evening.');
  const chosen = {};
  for (const k of keys) {
    const v = ratings?.[k];
    if (!Number.isInteger(v) || v < 1 || v > 10) throw new Error(`Choose a ${label(k)} rating from 1 to 10.`);
    chosen[k] = v;
  }
  return {entry_id: id, supersedes, occurred_at: occurredAt ?? offsetTimestamp(), period, ratings: chosen, note};
}

export function mealRequest({text, supersedes = null, occurredAt, photoCaptureId = null, id = uuidv7()}) {
  if (!String(text ?? '').trim() && !photoCaptureId) throw new Error('Describe what you ate.');
  return {entry_id: id, supersedes, occurred_at: occurredAt ?? offsetTimestamp(), text: String(text ?? ''),
    photo_capture_id: photoCaptureId};
}

export function workoutRequest({exercise, mode, load, unit, reps, rpe = null, note = '', supersedes = null,
  occurredAt, id = uuidv7()}) {
  if (!String(exercise ?? '').trim()) throw new Error('Name the exercise.');
  if (!['external_load','bodyweight','assisted'].includes(mode)) throw new Error('Choose a movement mode.');
  if (!Number.isInteger(reps) || reps < 1) throw new Error('Reps must be a whole number above zero.');
  const weighted = mode !== 'bodyweight';
  if (weighted && !(Number.isFinite(load) && load > 0 && ['lb','kg'].includes(unit)))
    throw new Error(mode === 'assisted' ? 'Enter the assistance amount and unit.' : 'Enter the load and unit.');
  if (rpe !== null && !(Number.isFinite(rpe) && rpe >= 0 && rpe <= 10 && Number.isInteger(rpe * 2)))
    throw new Error('RPE is 0–10 in half steps, or leave it blank.');
  return {entry_id: id, supersedes, occurred_at: occurredAt ?? offsetTimestamp(), exercise: String(exercise).trim(),
    movement_mode: mode, load: weighted ? load : null, load_unit: weighted ? unit : null, reps, rpe, note};
}

// Each V0 write carries its own retained identity (card reviews use decision_id).
export const requestId = request => request?.entry_id ?? request?.decision_id;

export function cardReviewRequest({rowId, action, targetId = null, supersedes = null, id = uuidv7()}) {
  if (!rowId) throw new Error('Missing card row.');
  if (action === 'link' && !targetId) throw new Error('Choose the matching charge.');
  if (!['distinct','link'].includes(action)) throw new Error('Unknown review action.');
  return {decision_id: id, row_id: rowId, action, target_id: action === 'link' ? targetId : null, supersedes};
}

// Unconfirmed saves survive reloads so a retry reuses the identical request.
export function createPendingStore(storage) {
  const KEY = 'personal-os.pending.v1';
  const readAll = () => { try { return JSON.parse(storage?.getItem(KEY) || '[]'); } catch { return []; } };
  const writeAll = list => { try { storage?.setItem(KEY, JSON.stringify(list)); } catch { /* memory only */ } };
  let memory = readAll();
  return {
    list: () => memory.map(p => structuredClone(p)),
    put(kind, request) {
      memory = memory.filter(p => requestId(p.request) !== requestId(request)).concat([{kind, request}]);
      writeAll(memory);
    },
    remove(id) { memory = memory.filter(p => requestId(p.request) !== id); writeAll(memory); }
  };
}

const LABELS = {sleep_quality: 'sleep quality', energy: 'energy', mood: 'mood'};
const label = key => LABELS[key] ?? String(key).replace(/_/g, ' ');
const time = ts => typeof ts === 'string' && ts.length >= 16 ? esc(ts.slice(11, 16)) : '';
const missing = text => `<p class="missing">${esc(text)}</p>`;

function editButton(kind, entry) {
  return `<button type="button" class="link" data-edit="${esc(kind)}" data-entry="${esc(entry.entry_id)}">Correct</button>`;
}

export function renderCheckins(section) {
  const entries = section?.entries ?? [];
  if (!entries.length) return missing('No check-in logged.');
  return '<ul class="entries">' + entries.map(e => {
    const r = Object.entries(e.ratings ?? {}).map(([k, v]) =>
      `<span class="pill">${esc(label(k))} <strong>${esc(v)}</strong><span class="scale">/10</span></span>`).join(' ');
    return `<li><div class="row"><span class="when">${time(e.occurred_at)} · ${esc(e.period)}</span>${editButton('checkin', e)}</div>` +
      `<div>${r}</div>${e.note ? `<p class="note">${esc(e.note)}</p>` : ''}</li>`;
  }).join('') + '</ul>';
}

const NUTRITION = {pending: 'Nutrition not processed', results_available: 'Nutrition results available',
  removed: 'Nutrition items removed'};

export function renderMeals(section) {
  const entries = section?.entries ?? [];
  if (!entries.length) return missing('No meals logged.');
  return '<ul class="entries">' + entries.map(e =>
    `<li><div class="row"><span class="when">${time(e.occurred_at)}</span>${editButton('meal', e)}</div>` +
    `<p>${esc(e.text) || '<span class="muted">Photo only</span>'}</p>` +
    (e.photo ? '<p class="muted">Photo attached</p>' : '') +
    `<p class="muted small">${esc(NUTRITION[e.nutrition?.status] ?? 'Nutrition status unavailable')}</p></li>`
  ).join('') + '</ul>';
}

export function renderWorkouts(section) {
  const entries = section?.entries ?? [];
  if (!entries.length) return missing('No sets logged.');
  return '<ul class="entries">' + entries.map(e => {
    const load = e.movement_mode === 'bodyweight' ? 'bodyweight'
      : `${esc(e.load)} ${esc(e.load_unit)}${e.movement_mode === 'assisted' ? ' assistance' : ''}`;
    return `<li><div class="row"><span class="when">${time(e.occurred_at)}</span>${editButton('workout', e)}</div>` +
      `<p><strong>${esc(e.exercise)}</strong> · ${load} × ${esc(e.reps)}${e.rpe != null ? ` · RPE ${esc(e.rpe)}` : ''}</p>` +
      (e.note ? `<p class="note">${esc(e.note)}</p>` : '') + '</li>';
  }).join('') + '</ul>';
}

export function renderHealth(health) {
  const daily = health?.daily_aggregates ?? [];
  const sessions = health?.recorded_workout_sessions ?? [];
  let h = daily.length
    ? '<ul class="stats">' + daily.map(a =>
        `<li><span class="stat-label">${esc(a.label ?? a.metric)}</span><span class="stat">${esc(a.value)} <span class="unit">${esc(a.unit)}</span></span>` +
        `<span class="muted small">${esc(a.device ?? '')}</span></li>`).join('') + '</ul>'
    : missing('No health data for this day.');
  if (sessions.length) h += `<p class="muted small">${esc(sessions.length)} recorded workout session(s) from Apple Health.</p>`;
  const last = health?.freshness?.last_received_at;
  h += `<p class="muted small">${last ? `Last health import received ${esc(String(last).slice(0, 16).replace('T', ' '))}.` : 'No Apple Health import received yet.'}</p>`;
  return h;
}

export function renderSpending(spending) {
  const rows = (spending?.accounts ?? []).flatMap(a => a?.entries ?? []);
  if (!rows.length) return missing('No card activity imported for this day.');
  const byId = new Map(rows.map(r => [r.row_id, r]));
  const name = id => { const r = byId.get(id); return r ? `${esc(r.description)} ${esc(r.amount)}` : 'a charge from another day'; };
  return '<ul class="entries">' + rows.map(r => {
    let extra = '';
    if (r.status === 'needs_review') {
      extra = '<p class="small">This may duplicate another import. Is it a separate charge?</p><div class="review">' +
        `<button type="button" data-review="distinct" data-row="${esc(r.row_id)}" data-supersedes="${esc(r.decision_id ?? '')}">Separate charge</button>` +
        (r.candidate_ids ?? []).map(c => `<button type="button" data-review="link" data-row="${esc(r.row_id)}" data-target="${esc(c)}" data-supersedes="${esc(r.decision_id ?? '')}">Same as ${name(c)}</button>`).join('') +
        '</div>';
    } else if (r.status === 'linked') {
      extra = `<p class="muted small">Counted as the same charge as ${name(r.linked_to)}. ` +
        `<button type="button" class="link" data-review="distinct" data-row="${esc(r.row_id)}" data-supersedes="${esc(r.decision_id ?? '')}">Keep as separate</button></p>`;
    } else if (r.status && r.status !== 'distinct') {
      extra = `<p class="muted small">${esc(String(r.status).replace(/_/g, ' '))}</p>`;
    }
    return `<li><div class="row"><span>${esc(r.description)}</span><span class="stat">${esc(r.amount)} <span class="unit">${esc(r.currency)}</span></span></div>${extra}</li>`;
  }).join('') + '</ul>';
}

export function renderVisits(visits) {
  const entries = visits?.entries ?? [];
  if (!entries.length) {
    const why = {awaiting_derivation: 'Location received; visits not processed yet.',
      no_detected_visits: 'Location received; no stays detected.'}[visits?.processing_status];
    return missing(why ?? 'No location data for this day.');
  }
  return '<ul class="entries">' + entries.map(v =>
    `<li><div class="row"><span>${esc(v.label)}</span><span class="when">${time(v.first_observed_at)}–${time(v.last_observed_at)}</span></div></li>`
  ).join('') + '</ul>';
}

export function renderDay(day) {
  if (!day || typeof day !== 'object' || Array.isArray(day)) throw new Error('Invalid day');
  const card = (title, body) => `<section class="card"><h3>${esc(title)}</h3>${body}</section>`;
  return `<p class="day-label">${esc(day.day)}</p>` +
    card('Check-ins', renderCheckins(day.checkins)) +
    card('Meals', renderMeals(day.meals)) +
    card('Workouts', renderWorkouts(day.workouts)) +
    card('Health', renderHealth(day.health)) +
    card('Spending', renderSpending(day.spending)) +
    card('Places', renderVisits(day.visits));
}

// Browser glue. `dom` is document; `rpc` is the signed-in Supabase rpc.
export function mountDaily({dom, rpc, storage}) {
  const $ = id => dom.getElementById(id);
  const v0 = createV0Client({rpc});
  const pending = createPendingStore(storage);
  const operations = new Map();
  let lastDay = null, viewToken = 0, editing = null;

  async function showDay(target, dayValue) {
    const token = ++viewToken;
    target.innerHTML = '<p class="muted" role="status">Loading…</p>';
    const result = await v0.read('day', {p_day: dayValue || null});
    if (token !== viewToken) return;
    if (result.status !== 'available') {
      target.innerHTML = '<p role="alert">Couldn\'t load this day. That doesn\'t mean it\'s empty.</p><button type="button" id="retry-day">Try again</button>';
      $('retry-day').onclick = () => showDay(target, dayValue);
      return;
    }
    lastDay = result.data;
    target.innerHTML = renderDay(result.data);
    target.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => startCorrection(b.dataset.edit, b.dataset.entry));
    target.querySelectorAll('[data-review]').forEach(b => b.onclick = () => {
      target.querySelectorAll(`[data-row="${b.dataset.row}"]`).forEach(x => { x.disabled = true; });
      send('card_review', cardReviewRequest({rowId: b.dataset.row, action: b.dataset.review,
        targetId: b.dataset.target || null, supersedes: b.dataset.supersedes || null}));
    });
  }

  function renderPending() {
    const list = pending.list();
    const box = $('pending');
    box.hidden = !list.length;
    box.innerHTML = list.length ? `<p><strong>${list.length} unconfirmed save(s).</strong> These may or may not have reached the server. Retrying is safe.</p>` +
      list.map(p => `<div class="row"><span>${esc(p.kind)} · ${esc(p.kind === 'card_review' ? 'charge review' : p.request.occurred_at?.slice(11, 16))}</span>` +
        `<span><button type="button" data-retry="${esc(requestId(p.request))}">Retry</button> ` +
        `<button type="button" class="link" data-discard="${esc(requestId(p.request))}">Discard</button></span></div>`).join('') : '';
    box.querySelectorAll('[data-retry]').forEach(b => b.onclick = () => {
      const p = list.find(x => requestId(x.request) === b.dataset.retry);
      if (p) send(p.kind, p.request);
    });
    box.querySelectorAll('[data-discard]').forEach(b => b.onclick = () => { pending.remove(b.dataset.discard); renderPending(); });
  }

  async function send(kind, request) {
    const status = $('add-status');
    pending.put(kind, request);             // Persist before sending (V0_OWNER_CALLER).
    const id = requestId(request);
    let op = operations.get(id);
    if (!op) { op = v0.prepare(kind, request); operations.set(id, op); }
    status.textContent = 'Saving…';
    const outcome = await op.send();
    if (outcome.status === 'saved') {
      pending.remove(id); operations.delete(id);
      status.textContent = 'Saved.';
      resetForms();
      if (!$('panel-today').hidden) showDay($('today-view'), null);
      else if (!$('panel-history').hidden && $('history-date').value) showDay($('history-view'), $('history-date').value);
    } else if (outcome.status === 'rejected') {
      pending.remove(id); operations.delete(id);
      status.textContent = outcome.recovery === 'sign_in' ? 'Not saved: sign in again.'
        : 'Not saved: the server refused it. If you were correcting an entry, reload Today and try again.';
    } else {
      status.textContent = 'Not confirmed. Your entry is kept below. Retry when you\'re back online.';
    }
    renderPending();
  }

  function setRating(group, value) {
    group.dataset.value = String(value);
    group.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.v) === value)));
  }
  function readRating(group) { const v = Number(group.dataset.value); return Number.isInteger(v) && v > 0 ? v : undefined; }

  function periodChanged() {
    const period = $('ci-period').value;
    $('ci-sleep-row').hidden = period !== 'morning';
    $('ci-mood-row').hidden = period !== 'evening';
  }

  function resetForms() {
    editing = null;
    $('editing').hidden = true;
    dom.querySelectorAll('form.entry').forEach(f => f.reset());
    dom.querySelectorAll('.rating').forEach(g => { delete g.dataset.value; g.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false')); });
    $('ci-period').value = new Date().getHours() < 15 ? 'morning' : 'evening';
    periodChanged(); modeChanged();
  }

  function modeChanged() { $('wo-load-row').hidden = $('wo-mode').value === 'bodyweight'; }

  function startCorrection(kind, entryId) {
    const section = {checkin: 'checkins', meal: 'meals', workout: 'workouts'}[kind];
    const entry = lastDay?.[section]?.entries?.find(e => e.entry_id === entryId);
    if (!entry) return;
    resetForms();
    editing = {kind, entryId, occurredAt: entry.occurred_at};
    $('editing').hidden = false;
    $('editing-text').textContent = `Correcting a ${kind} from ${String(entry.occurred_at).slice(0, 16).replace('T', ' ')}. The original stays in history.`;
    if (kind === 'checkin') {
      $('ci-period').value = entry.period; periodChanged();
      for (const [k, v] of Object.entries(entry.ratings ?? {})) { const g = dom.querySelector(`.rating[data-key="${k}"]`); if (g) setRating(g, v); }
      $('ci-note').value = entry.note ?? '';
    } else if (kind === 'meal') {
      $('meal-text').value = entry.text ?? '';
    } else {
      $('wo-exercise').value = entry.exercise ?? ''; $('wo-mode').value = entry.movement_mode; modeChanged();
      $('wo-load').value = entry.load ?? ''; $('wo-unit').value = entry.load_unit ?? 'lb';
      $('wo-reps').value = entry.reps ?? ''; $('wo-rpe').value = entry.rpe ?? ''; $('wo-note').value = entry.note ?? '';
    }
    openTab('add', kind);
  }

  function submit(kind, build) {
    try {
      const base = editing?.kind === kind ? {supersedes: editing.entryId, occurredAt: editing.occurredAt} : {};
      send(kind, build(base));
    } catch (error) { $('add-status').textContent = error.message; }
  }

  function openTab(name, addKind) {
    $('add-status').textContent = '';
    for (const t of ['today','add','history','ask']) {
      $(`panel-${t}`).hidden = t !== name;
      $(`tab-${t}`).setAttribute('aria-current', String(t === name));
    }
    if (addKind) dom.querySelectorAll('[data-add]').forEach(b => {
      const on = b.dataset.add === addKind;
      b.setAttribute('aria-pressed', String(on));
      $(`form-${b.dataset.add}`).hidden = !on;
    });
    if (name === 'today') showDay($('today-view'), null);
    if (name === 'history' && $('history-date').value) showDay($('history-view'), $('history-date').value);
  }

  // Wiring
  for (const t of ['today','add','history','ask']) $(`tab-${t}`).onclick = () => openTab(t);
  dom.querySelectorAll('[data-add]').forEach(b => b.onclick = () => openTab('add', b.dataset.add));
  dom.querySelectorAll('.rating').forEach(g => {
    g.innerHTML = Array.from({length: 10}, (_, i) => `<button type="button" data-v="${i+1}" aria-pressed="false">${i+1}</button>`).join('');
    g.querySelectorAll('button').forEach(b => b.onclick = () => setRating(g, Number(b.dataset.v)));
  });
  $('ci-period').onchange = periodChanged;
  $('wo-mode').onchange = modeChanged;
  $('cancel-edit').onclick = resetForms;
  $('form-checkin').onsubmit = e => { e.preventDefault(); submit('checkin', base => {
    const period = $('ci-period').value;
    const ratings = {energy: readRating(dom.querySelector('.rating[data-key="energy"]'))};
    if (period === 'morning') ratings.sleep_quality = readRating(dom.querySelector('.rating[data-key="sleep_quality"]'));
    else ratings.mood = readRating(dom.querySelector('.rating[data-key="mood"]'));
    return checkinRequest({period, ratings, note: $('ci-note').value, ...base});
  }); };
  $('form-meal').onsubmit = e => { e.preventDefault(); submit('meal', base => mealRequest({text: $('meal-text').value, ...base})); };
  $('form-workout').onsubmit = e => { e.preventDefault(); submit('workout', base => {
    const num = id => $(id).value.trim() === '' ? null : Number($(id).value);
    return workoutRequest({exercise: $('wo-exercise').value, mode: $('wo-mode').value, load: num('wo-load'),
      unit: $('wo-unit').value, reps: num('wo-reps'), rpe: num('wo-rpe'), note: $('wo-note').value, ...base});
  }); };
  $('history-date').onchange = () => showDay($('history-view'), $('history-date').value);

  resetForms();
  renderPending();
  return {openTab, showDay};
}
