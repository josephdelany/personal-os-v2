import test from 'node:test';
import assert from 'node:assert/strict';
import { handle } from '../workers/capture-media/index.mjs';
const cid = '0195dc0b-3470-7000-8000-000000000001';
const jwt = role => `fixture.${btoa(JSON.stringify({ role }))}.fixture`;
const env = { CAPTURE_TOKEN: 'fixture', SUPABASE_URL: 'https://fixture.supabase.co',
  SUPABASE_MEDIA_UPLOAD_JWT: jwt('capture_media_upload'), SUPABASE_ANON_KEY: jwt('anon') };
const request = () => new Request('https://capture.invalid', { method: 'POST',
  headers: { authorization: 'Bearer fixture', 'x-capture-id': cid,
    'x-media-kind': 'voice', 'content-type': 'audio/mp4' }, body: 'fixture bytes' });
const commit = value => Response.json(value, { headers: { 'preference-applied': 'tx=commit' } });
function transport(mode, calls) {
  let receipt;
  return async (url, options) => {
    calls.push(url.pathname);
    assert.equal(options.redirect, 'error');
    assert.equal(options.headers.authorization, `Bearer ${env.SUPABASE_MEDIA_UPLOAD_JWT}`);
    if (url.pathname.endsWith('begin_capture_media_upload')) {
      const args = JSON.parse(options.body);
      const bytes = new TextEncoder().encode('fixture bytes');
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
        .map(x => x.toString(16).padStart(2, '0')).join('');
      assert.equal(args.p_sha256, hash);
      assert.equal(args.p_size, bytes.length);
      receipt = { capture_id: cid, media_path: `${cid}/audio`, media_sha256: hash,
        size_bytes: bytes.length, status: mode === 'duplicate' ? 'available' : 'awaiting_upload' };
      if (mode === 'rollback') return Response.json(receipt);
      if (mode === 'wrong_hash') return commit({ ...receipt, media_sha256: '0'.repeat(64) });
      return commit(receipt);
    }
    if (url.pathname.includes('/storage/')) {
      assert.equal(options.headers['x-upsert'], 'false');
      assert.equal(new TextDecoder().decode(options.body), 'fixture bytes');
      if (mode === 'conflict') return Response.json({}, { status: 409 });
      return Response.json({ Key: mode === 'wrong_path' ? 'other' : `captures/${cid}/audio` });
    }
    assert.ok(url.pathname.endsWith('complete_capture_media_upload'));
    if (mode === 'lost_completion') throw new Error('secret must not leak');
    return commit({ ...receipt, status: 'available' });
  };
}
test('REQ_CAP_006_009_012 upload hashes actual bytes and commits ordered receipts', async () => {
  const calls = [];
  const result = await handle(request(), env, transport('ok', calls));
  assert.equal(result.status, 201);
  assert.equal((await result.json()).status, 'available');
  assert.equal(calls.length, 3);
});
test('REQ_CAP_016 confirmed retry does not replace media', async () => {
  const calls = [];
  assert.equal((await handle(request(), env, transport('duplicate', calls))).status, 200);
  assert.equal(calls.length, 1);
});
for (const [mode, count] of [['rollback', 1], ['wrong_hash', 1], ['conflict', 2],
  ['wrong_path', 2], ['lost_completion', 3]]) {
  test(`REQ_CAP_012_016 unconfirmed ${mode} never acknowledges media`, async () => {
    const calls = [];
    const result = await handle(request(), env, transport(mode, calls));
    assert.equal(result.status, 503);
    assert.equal(calls.length, count);
    assert.ok(!(await result.text()).includes('secret'));
  });
}
test('REQ_CAP_008 unauthorized upload never reads body or sends', async () => {
  const req = request();
  req.headers.set('authorization', 'Bearer wrong');
  assert.equal((await handle(req, env, () => assert.fail('sent'))).status, 401);
  assert.equal(req.bodyUsed, false);
});
test('REQ_CAP_009 service role configuration fails before reading media', async () => {
  const req = request();
  assert.equal((await handle(req, { ...env, SUPABASE_MEDIA_UPLOAD_JWT: jwt('service_role') },
    () => assert.fail('sent'))).status, 503);
  assert.equal(req.bodyUsed, false);
});
test('REQ_CAP_006 truncated declared body cannot upload', async () => {
  const req = request(); req.headers.set('content-length', '100');
  assert.equal((await handle(req, env, () => assert.fail('sent'))).status, 400);
});

test('REQ_CAP_011_016 combined device route acknowledges raw receipt after upload', async () => {
  const { default: worker } = await import('../workers/capture-media/index.mjs');
  const req = request();
  req.headers.set('x-capture-metadata', JSON.stringify({ captured_at: '2026-09-22T12:00:00Z',
    kind: 'food', duration_s: 3.5 }));
  const combined = new Request('https://capture.invalid/capture', req);
  const calls = [];
  const upload = transport('ok', calls);
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    if (!url.pathname.endsWith('receive_capture')) return upload(url, options);
    calls.push(url.pathname);
    assert.equal(options.headers.authorization, `Bearer ${jwt('capture_ingest')}`);
    const raw = JSON.parse(JSON.parse(options.body).p_raw_body);
    assert.equal(raw.capture_id, cid);
    assert.equal(raw.source, 'shortcut_voice');
    assert.equal(raw.payload.duration_s, 3.5);
    assert.equal(raw.payload.media_path, `${cid}/audio`);
    assert.match(raw.payload.media_sha256, /^[0-9a-f]{64}$/);
    return commit({ capture_id: cid, status: 'created' });
  };
  try {
    const result = await worker.fetch(combined, { ...env, SUPABASE_CAPTURE_JWT: jwt('capture_ingest') }, {});
    assert.equal(result.status, 202);
    assert.deepEqual(await result.json(), { capture_id: cid });
    assert.equal(calls.length, 4);
  } finally { globalThis.fetch = original; }
});

test('REQ_CAP_011_016 combined retry requires a committed raw receipt', async () => {
  const { capture } = await import('../workers/capture-media/index.mjs');
  for (const durable of [false, true]) {
    const req = request();
    req.headers.set('x-capture-metadata', JSON.stringify({ captured_at: '2026-09-22T12:00:00Z',
      kind: 'food', duration_s: 3.5 }));
    const calls = [];
    const upload = transport('duplicate', calls);
    const result = await capture(req, { ...env, SUPABASE_CAPTURE_JWT: jwt('capture_ingest') },
      async (url, options) => {
        if (!url.pathname.endsWith('receive_capture')) return upload(url, options);
        calls.push(url.pathname);
        const receipt = { capture_id: cid, status: 'duplicate' };
        return durable ? commit(receipt) : Response.json(receipt);
      });
    assert.equal(result.status, durable ? 200 : 503);
    assert.equal(calls.length, 2);
  }
});

test('REQ_CAP_006_008 combined invalid metadata never reads or uploads media', async () => {
  const { capture } = await import('../workers/capture-media/index.mjs');
  const req = request();
  assert.equal((await capture(req, env, () => assert.fail('sent'))).status, 400);
  assert.equal(req.bodyUsed, false);
});


test('REQ_CAP_006_030 zero-duration voice refuses before upload', async () => {
  const { capture } = await import('../workers/capture-media/index.mjs');
  const req = request();
  req.headers.set('x-capture-metadata', JSON.stringify({ captured_at: '2026-09-22T12:00:00Z',
    kind: 'food', duration_s: 0 }));
  assert.equal((await capture(req, env, () => assert.fail('sent'))).status, 400);
  assert.equal(req.bodyUsed, false);
});

test('REQ_CAP_006 stalled body cancellation cannot upload a truncated prefix', async () => {
  const original = globalThis.setTimeout;
  globalThis.setTimeout = (fn, delay, ...args) => original(fn, delay === 30000 ? 5 : delay, ...args);
  const base = request();
  const stream = new ReadableStream({ start(controller) {
    controller.enqueue(new TextEncoder().encode('prefix'));
    // Deliberately never close: a cancelled read must not become a complete upload.
  } });
  const req = new Request(base.url, { method: 'POST', headers: base.headers, body: stream, duplex: 'half' });
  try {
    assert.equal((await handle(req, env, () => assert.fail('sent'))).status, 400);
  } finally { globalThis.setTimeout = original; }
});

test('REQ_CAP_011_020 unknown device routes cannot return an upload-only acknowledgement', async () => {
  const { default: worker } = await import('../workers/capture-media/index.mjs');
  const original = globalThis.fetch;
  globalThis.fetch = () => assert.fail('sent');
  try {
    for (const path of ['/capture/', '/captures', '/', '/upload/']) {
      const req = new Request(`https://capture.invalid${path}`, request());
      assert.equal((await worker.fetch(req, env, {})).status, 404);
      assert.equal(req.bodyUsed, false);
    }
  } finally { globalThis.fetch = original; }
});
