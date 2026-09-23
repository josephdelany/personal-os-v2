// Upload only. No private reads, model credentials, or raw-capture acknowledgement.
import { authenticated, handle as ingest } from '../capture-ingest/index.mjs';
const MAX_BYTES = 52428800;
const uuid7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const reply = (status, body) => Response.json(body, {
  status, headers: { 'cache-control': 'no-store' },
});

async function boundedBody(request) {
  if (!request.body) throw new Error('empty');
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  let expired = false;
  const timer = setTimeout(() => { expired = true; void reader.cancel().catch(() => {}); }, 30000);
  let complete = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) { complete = true; break; }
      size += value.byteLength;
      if (size > MAX_BYTES) throw new Error('size');
      chunks.push(value);
    }
    const declared = request.headers.get('content-length');
    if (expired || !size || (declared !== null && (!/^\d+$/.test(declared)
        || Number(declared) !== size))) throw new Error('size');
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    return bytes;
  } finally {
    clearTimeout(timer);
    if (!complete) await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export async function handle(request, env, send = fetch) {
  if (request.method !== 'POST') return reply(405, { error: 'method_not_allowed' });
  if (!await authenticated(request, env.CAPTURE_TOKEN)) return reply(401, { error: 'unauthorized' });
  const cid = (request.headers.get('x-capture-id') ?? '').toLowerCase();
  const kind = request.headers.get('x-media-kind');
  const mime = request.headers.get('content-type') ?? '';
  if (!uuid7.test(cid) || !((kind === 'voice' && /^audio\/[a-z0-9.+-]+$/.test(mime))
      || (kind === 'photo' && ['image/jpeg', 'image/png'].includes(mime)))) {
    return reply(400, { error: 'invalid_media_identity' });
  }
  try {
    const origin = new URL(env.SUPABASE_URL);
    const role = token => JSON.parse(atob(token.split('.')[1]
      .replace(/-/g, '+').replace(/_/g, '/'))).role;
    if (origin.protocol !== 'https:' || !/^[a-z0-9]+\.supabase\.co$/.test(origin.hostname)
        || origin.port || origin.username || origin.password || origin.pathname !== '/'
        || origin.search || origin.hash || role(env.SUPABASE_MEDIA_UPLOAD_JWT) !== 'capture_media_upload'
        || role(env.SUPABASE_ANON_KEY) !== 'anon') throw new Error('configuration');
    let bytes;
    try { bytes = await boundedBody(request); }
    catch { return reply(400, { error: 'invalid_media_body' }); }
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
      .map(x => x.toString(16).padStart(2, '0')).join('');
    const path = `${cid}/${kind === 'voice' ? 'audio' : 'photo'}`;
    const headers = { apikey: env.SUPABASE_ANON_KEY,
      authorization: `Bearer ${env.SUPABASE_MEDIA_UPLOAD_JWT}` };
    const rpc = async (name, args) => {
      const response = await send(new URL(`/rest/v1/rpc/${name}`, origin), {
        method: 'POST', redirect: 'error', signal: AbortSignal.timeout(8000),
        headers: { ...headers, 'content-type': 'application/json', prefer: 'tx=commit' },
        body: JSON.stringify(args),
      });
      const applied = (response.headers.get('preference-applied') ?? '').split(',').map(x => x.trim());
      if (!response.ok || !applied.includes('tx=commit') || applied.includes('tx=rollback')) {
        throw new Error('unproven_commit');
      }
      const result = await response.json();
      if (result.capture_id !== cid || result.media_path !== path || result.media_sha256 !== hash
          || result.size_bytes !== bytes.byteLength) throw new Error('mismatched_receipt');
      return result;
    };
    const manifest = await rpc('begin_capture_media_upload', { p_capture_id: cid,
      p_kind: kind, p_sha256: hash, p_size: bytes.byteLength, p_content_type: mime });
    if (manifest.status === 'available') return reply(200, manifest);
    if (manifest.status !== 'awaiting_upload') throw new Error('invalid_status');
    const uploaded = await send(new URL(`/storage/v1/object/captures/${path}`, origin), {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(45000),
      headers: { ...headers, 'content-type': mime, 'x-upsert': 'false' }, body: bytes,
    });
    if (!uploaded.ok || (await uploaded.json()).Key !== `captures/${path}`) {
      throw new Error('upload_unproven');
    }
    const receipt = await rpc('complete_capture_media_upload', { p_capture_id: cid, p_sha256: hash });
    if (receipt.status !== 'available') throw new Error('invalid_status');
    return reply(201, receipt);
  } catch {
    // Same-ID retry or private hash reconciliation resolves ambiguous uploads.
    return reply(503, { error: 'media_upload_unconfirmed', capture_id: cid });
  }
}
// The combined device route acknowledges the raw capture, not merely its blob.
export async function capture(request, env, send = fetch) {
  if (request.method !== 'POST') return reply(405, { error: 'method_not_allowed' });
  if (!await authenticated(request, env.CAPTURE_TOKEN)) return reply(401, { error: 'unauthorized' });
  let metadata;
  try {
    const encoded = request.headers.get('x-capture-metadata');
    if (!encoded || encoded.length > 8192) throw new Error('metadata');
    metadata = JSON.parse(encoded);
    if (!metadata || Array.isArray(metadata) || typeof metadata !== 'object'
        || Object.keys(metadata).some(key => !['captured_at', 'kind', 'duration_s', 'checkin_date'].includes(key))
        || !['food', 'note', 'workout'].includes(metadata.kind)
        || typeof metadata.captured_at !== 'string'
        || !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(metadata.captured_at)
        || !Number.isFinite(Date.parse(metadata.captured_at))
        || (metadata.duration_s !== undefined && (typeof metadata.duration_s !== 'number'
          || !Number.isFinite(metadata.duration_s) || metadata.duration_s < 0))
        || (request.headers.get('x-media-kind') === 'voice' && (metadata.duration_s === undefined || metadata.duration_s <= 0))
        || (metadata.checkin_date !== undefined && (typeof metadata.checkin_date !== 'string'
          || !/^\d{4}-\d{2}-\d{2}$/.test(metadata.checkin_date)))) throw new Error('metadata');
  } catch { return reply(400, { error: 'invalid_capture_metadata' }); }
  const uploaded = await handle(request, env, send);
  if (![200, 201].includes(uploaded.status)) return uploaded;
  const media = await uploaded.json();
  const { captured_at, ...payload } = metadata;
  const envelope = { capture_id: media.capture_id, captured_at,
    source: request.headers.get('x-media-kind') === 'voice' ? 'shortcut_voice' : 'shortcut_photo',
    payload: { ...payload, media_path: media.media_path, media_sha256: media.media_sha256 } };
  return ingest(new Request('https://capture.invalid', { method: 'POST',
    headers: { authorization: request.headers.get('authorization'), 'content-type': 'application/json' },
    body: JSON.stringify(envelope) }), env, send);
}
export default { fetch(request, env) {
  const path = new URL(request.url).pathname;
  if (path === '/capture') return capture(request, env);
  if (path === '/upload') return handle(request, env);
  return reply(404, { error: 'not_found' });
} };
