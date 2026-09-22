import test from 'node:test';
import assert from 'node:assert/strict';
import worker, { handle } from '../workers/capture-ingest/index.mjs';

const cid = '0195dc0b-3470-7000-8000-000000000001';
const body = JSON.stringify({ capture_id: cid, captured_at: '2026-09-22T12:00:00Z',
  source: 'shortcut_text', payload: { text: 'fixture only' } });
const env = { CAPTURE_TOKEN: 'test-token', SUPABASE_URL: 'https://fixture.supabase.co',
  SUPABASE_ANON_KEY: `fixture.${btoa(JSON.stringify({ role: 'anon' }))}.fixture`,
  SUPABASE_CAPTURE_JWT: `fixture.${btoa(JSON.stringify({ role: 'capture_ingest' }))}.fixture` };
const req = (raw = body, token = env.CAPTURE_TOKEN) => new Request('https://capture.invalid', {
  method: 'POST', headers: { authorization: `Bearer ${token}`, prefer: 'tx=rollback' }, body: raw });
const receipt = (status = 'created', headers = { 'preference-applied': 'tx=commit' }) =>
  Response.json({ status, capture_id: cid }, { headers });

test('REQ_CAP_011 platform entrypoint accepts ExecutionContext and invokes real transport adapter', async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; return receipt(); };
  try {
    const response = await worker.fetch(req(), env, { waitUntil() { assert.fail('no enrichment'); } });
    assert.equal(response.status, 202);
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});

test('REQ_CAP_008 authentication precedes body access and storage', async () => {
  for (const [expected, supplied] of [[undefined, undefined], ['', ''], [' ', ' '],
    ['test-token', 'wrong'], ['test-token', ''], [false, 'false']]) {
    const request = req(body, supplied);
    request.text = () => { throw new Error('BODY READ'); };
    let called = false;
    const response = await handle(request, { ...env, CAPTURE_TOKEN: expected }, () => {
      called = true; throw new Error('STORE CALLED'); });
    assert.equal(response.status, 401);
    assert.equal(called, false);
    assert.equal(request.bodyUsed, false);
  }
});

test('REQ_CAP_009_011 POST waits for commit receipt and keeps secrets server-side', async () => {
  let complete, sent = false;
  const pending = handle(req(), env, async (url, options) => {
    assert.equal(String(url), 'https://fixture.supabase.co/rest/v1/rpc/receive_capture');
    assert.equal(options.redirect, 'error');
    assert.equal(options.headers.prefer, 'tx=commit');
    assert.equal(options.headers.authorization, `Bearer ${env.SUPABASE_CAPTURE_JWT}`);
    assert.equal(options.headers.apikey, env.SUPABASE_ANON_KEY);
    assert.deepEqual(JSON.parse(options.body), { p_raw_body: body });
    sent = true;
    return new Promise(resolve => { complete = resolve; });
  });
  let finished = false;
  pending.then(() => { finished = true; });
  while (!sent) await new Promise(resolve => setTimeout(resolve, 1));
  assert.equal(finished, false);
  complete(receipt());
  const response = await pending;
  assert.equal(response.status, 202);
  assert.deepEqual(await response.json(), { capture_id: cid });
});

test('REQ_CAP_016_017 duplicate returns 200 using one storage call and no enrichment', async () => {
  let calls = 0;
  const response = await handle(req(), env, async () => { calls++; return receipt('duplicate'); });
  assert.equal(calls, 1);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: 'duplicate', capture_id: cid });
});

test('REQ_CAP_007 missing identity raw body reaches persistence before 400', async () => {
  const raw = '{ "payload" : "fixture only" }';
  const response = await handle(req(raw), env, async (_, options) => {
    assert.equal(JSON.parse(options.body).p_raw_body, raw);
    return Response.json({ status: 'rejected', error: 'missing_identity_fields' },
      { headers: { 'preference-applied': 'tx=commit' } });
  });
  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { error: 'missing_identity_fields' });
});

test('REQ_CAP_011 storage error rollback absent receipt and mismatched receipt never acknowledge', async () => {
  for (const send of [async () => { throw new Error('private body and secret'); },
    async () => new Response('private database error', { status: 500 }),
    async () => receipt('created', {}),
    async () => receipt('created', { 'preference-applied': 'tx=rollback' }),
    async () => receipt('unknown'),
    async () => Response.json({ status: 'created', capture_id: cid.replace(/1$/, '2') },
      { headers: { 'preference-applied': 'tx=commit' } }),
    async () => Response.json(null, { headers: { 'preference-applied': 'tx=commit' } }),
  ]) {
    const response = await handle(req(), env, send);
    assert.equal(response.status, 503);
    assert.deepEqual(await response.json(), { error: 'capture_storage_unavailable' });
  }
});

test('REQ_CAP_009 fixed origin configuration cannot leak capture or server credential', async () => {
  for (const url of ['http://fixture.supabase.co', 'https://evil.invalid',
    'https://fixture.supabase.co.evil.invalid', 'https://fixture.supabase.co:444',
    'https://secret@fixture.supabase.co', 'https://fixture.supabase.co/path']) {
    let sent = false;
    const response = await handle(req(), { ...env, SUPABASE_URL: url }, async () => { sent = true; });
    assert.equal(response.status, 503);
    assert.equal(sent, false);
  }
  assert.equal(typeof worker.fetch, 'function');
});

test('REQ_CAP_009 broad service credential is rejected before body or network', async () => {
  const request = req();
  const broad = `fixture.${btoa(JSON.stringify({ role: 'service_role' }))}.fixture`;
  let called = false;
  const response = await handle(request, { ...env, SUPABASE_CAPTURE_JWT: broad }, async () => {
    called = true;
  });
  assert.equal(response.status, 503);
  assert.equal(called, false);
  assert.equal(request.bodyUsed, false);
  const anonRequest = req();
  const result = await handle(anonRequest, { ...env, SUPABASE_ANON_KEY: broad }, async () => {
    assert.fail('broad apikey must not reach transport');
  });
  assert.equal(result.status, 503);
  assert.equal(anonRequest.bodyUsed, false);
});
