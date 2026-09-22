// ADR-0143. No model calls, payload logging, SDK or client-controlled destination.
const uuid7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const rejectionReasons = new Set(['invalid_json', 'invalid_envelope',
  'missing_identity_fields', 'invalid_capture_id', 'invalid_captured_at',
  'invalid_source', 'missing_payload']);

function reply(status, body) {
  return Response.json(body, { status, headers: { 'cache-control': 'no-store' } });
}

async function authenticated(request, expected) {
  if (typeof expected !== 'string' || !expected.trim()) return false;
  const auth = request.headers.get('authorization') ?? '';
  if (!/^Bearer /i.test(auth)) return false;
  const supplied = auth.slice(7);
  if (!supplied.trim()) return false;
  const encoder = new TextEncoder();
  const [a, b] = await Promise.all([expected, supplied].map(async token =>
    new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(token)))));
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

export async function handle(request, env, send = fetch) {
  if (request.method !== 'POST') return reply(405, { error: 'method_not_allowed' });
  if (!await authenticated(request, env.CAPTURE_TOKEN)) {
    return reply(401, { error: 'unauthorized' });
  }
  try {
    // Fixed service origin only: no alternate ports, credentials, paths or redirects.
    const origin = new URL(env.SUPABASE_URL);
    if (origin.protocol !== 'https:' || !/^[a-z0-9]+\.supabase\.co$/.test(origin.hostname)
        || origin.port || origin.username || origin.password || origin.pathname !== '/'
        || origin.search || origin.hash || typeof env.SUPABASE_CAPTURE_JWT !== 'string'
        || typeof env.SUPABASE_ANON_KEY !== 'string' || !env.SUPABASE_ANON_KEY.trim()) {
      throw new Error('configuration');
    }
    // Reject accidental service-role configuration. PostgREST verifies the signature;
    // the dedicated role has only ingress EXECUTE, never private-read capability.
    const role = token => JSON.parse(atob(token.split('.')[1]
      .replace(/-/g, '+').replace(/_/g, '/'))).role;
    if (role(env.SUPABASE_CAPTURE_JWT) !== 'capture_ingest'
        || role(env.SUPABASE_ANON_KEY) !== 'anon') throw new Error('credential_scope');
    const raw = await request.text();
    const response = await send(new URL('/rest/v1/rpc/receive_capture', origin), {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(8000),
      headers: {
        'content-type': 'application/json',
        apikey: env.SUPABASE_ANON_KEY,
        authorization: `Bearer ${env.SUPABASE_CAPTURE_JWT}`,
        prefer: 'tx=commit',
      },
      body: JSON.stringify({ p_raw_body: raw }),
    });
    // Requires PostgREST commit-allow-override configuration. Never mistake a
    // rollback-mode RPC response for a durable acknowledgement (REQ-CAP-011).
    const applied = (response.headers.get('preference-applied') ?? '')
      .split(',').map(value => value.trim());
    if (!response.ok || !applied.includes('tx=commit') || applied.includes('tx=rollback')) {
      throw new Error('storage_unproven');
    }
    const receipt = await response.json();
    if (receipt?.status === 'rejected' && rejectionReasons.has(receipt.error)) {
      return reply(400, { error: receipt.error });
    }
    if (!uuid7.test(receipt?.capture_id ?? '')) throw new Error('invalid_receipt');
    // Confirm the reply belongs to this request, not an unrelated/malformed RPC result.
    const client = JSON.parse(raw);
    if (typeof client?.capture_id !== 'string'
        || receipt.capture_id.toLowerCase() !== client.capture_id.toLowerCase()) {
      throw new Error('mismatched_receipt');
    }
    if (receipt.status === 'duplicate') {
      return reply(200, { status: 'duplicate', capture_id: receipt.capture_id });
    }
    if (receipt.status !== 'created') throw new Error('invalid_receipt');
    return reply(202, { capture_id: receipt.capture_id });
  } catch {
    // Lost responses and timeouts may have committed. Same-ID retry safely resolves them.
    return reply(503, { error: 'capture_storage_unavailable' });
  }
}

// Cloudflare's third argument is ExecutionContext, never the fetch transport.
export default { fetch(request, env) { return handle(request, env); } };
