// location-ingest — the Overland receiver (ADR-0046; REQ-LOC-002).
//
// Overland (github.com/aaronpk/Overland-iOS) POSTs {"locations":[GeoJSON Feature, …]} with the
// configured access token in `Authorization: Bearer <token>` and requires {"result":"ok"} back;
// any other reply makes it keep the batch and retry at the next interval.
//
// This function verifies the token with a constant-time compare, forwards the body UNCHANGED to
// public.ingest_location_batch with the service-role client (the only grantee of that RPC), and
// answers {"result":"ok"}. It NEVER logs the request body, a coordinate, or a database message
// (a CHECK-violation detail could quote a row) — only a status word and an error code.
//
// Deploy (Joe, once):  supabase functions deploy location-ingest --project-ref cykviouklidnbsbgdgdo --no-verify-jwt
//                      supabase secrets set LOCATION_TOKEN=<openssl rand -hex 24>   (typed into Overland; never into chat or git)
// SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are injected by the platform.
import { createClient } from "npm:@supabase/supabase-js@2";

const JSON_HEADERS = { "content-type": "application/json" };

function timingSafeEqual(a: string, b: string): boolean {
  const ea = new TextEncoder().encode(a);
  const eb = new TextEncoder().encode(b);
  if (ea.length !== eb.length) return false;
  let diff = 0;
  for (let i = 0; i < ea.length; i++) diff |= ea[i] ^ eb[i];
  return diff === 0;
}

Deno.serve(async (req: Request): Promise<Response> => {
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ result: "error" }), { status: 405, headers: JSON_HEADERS });
  }
  const expected = Deno.env.get("LOCATION_TOKEN") ?? "";
  const auth = req.headers.get("authorization") ?? "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (expected.length === 0 || !timingSafeEqual(supplied, expected)) {
    return new Response(JSON.stringify({ result: "error" }), { status: 401, headers: JSON_HEADERS });
  }
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ result: "error" }), { status: 400, headers: JSON_HEADERS });
  }
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } },
  );
  const { error } = await supabase.rpc("ingest_location_batch", { p_batch: body });
  if (error) {
    console.error("location-ingest: rpc failed", error.code ?? "unknown");   // code only — never the message or body
    return new Response(JSON.stringify({ result: "error" }), { status: 500, headers: JSON_HEADERS });
  }
  return new Response(JSON.stringify({ result: "ok" }), { status: 200, headers: JSON_HEADERS });
});
