# ADR-0046: Background location capture via Overland → Supabase Edge Function; the MOVEMENTS read API

## Status
Accepted — Joe's ruling 2026-09-02: **Overland** (the DECISION B5 put to him).

## Date
2026-09-02

## Decision
**Capture.** Overland (free, open-source iOS app; background "significant location changes"
mode, ~1–3 % battery/day) POSTs batches to a Supabase Edge Function,
`supabase/functions/location-ingest/index.ts`. The function accepts POST only, reads the
access token from `Authorization: Bearer <token>` — **the header only**; Overland's README
(fetched 2026-09-02) says the token "will be sent in the HTTP Authorization header preceded
by the text Bearer", and a `?token=` query form would put the secret in request logs, so it
is not accepted — compares it to `LOCATION_TOKEN` in constant time, forwards the body
unchanged to `public.ingest_location_batch` with the service-role client (the RPC's only
grantee, ADR-0044), and replies `{"result":"ok"}`; Overland treats anything else as
undelivered and retries. **It never logs the request body, a coordinate, or a database
error message** — only a status word and an error code (REQ-LOC-002; a test asserts it).
The body shape the RPC parses — `{"locations":[GeoJSON Feature …]}`, geometry coordinates
`[longitude, latitude]`, properties `timestamp`, `horizontal_accuracy`, `speed`,
`battery_level`, `motion[]` — is the README's, verified against the same fetch.

The iOS-Shortcut automation path (`ingest_location` is `anon`-executable for it) is the
**fallback and is not built**: Overland was chosen, and a "Register this place" Shortcut
needs an authenticated session on the phone, which THE DESK provides on desktop instead.

**Read API** (migration 0040). `get_movements(p_day)` returns a day's coverage (fix count,
first/last fix clock, longest gap, `none | partial | fresh`), `last_known` (today only),
the visit list (label or `unknown place`, kind, `is_home`, arrive/depart clock, dwell
minutes, fix count, trace), `unknown_visits`, and `mobility` (distinct places, home/away
minutes, first leave, last return, trips, radius of gyration rounded to 0.1 km and never
paired with a centre). `get_place(p_place_id)` is the place page; `get_places()` the
label-only register. **Every figure carries `tier: DESCRIPTIVE` and `provisional: true`**
(REQ-LOC-013/017); everything renders from SQL with no model (REQ-LOC-018). No output
contains a coordinate key or a number with four or more decimals (REQ-LOC-002; tested by
walking every envelope). `get_entity('place', key)` now delegates to `get_place`; a key
that is not a uuid is refused with a note rather than a cast error.

## Decisions taken inside B5.3's envelope (recorded)
1. `get_places` is plpgsql with the RAISE pattern (B5's sql sketch returned NULL to a
   non-owner).
2. `get_entity(place)` wraps the uuid cast in an exception block (REQ-ASK-003 refusal, not
   an error). B4's test was updated to the post-B5 contract, not weakened.
3. Header-only token (above).
4. `unknown_visits` is emitted as `0` on a day with visits and none unknown, and on a day
   with no visits — a count, not a measurement; B5's envelope specified it.

## Deploy (Joe; needs `supabase login` in a browser)
```
supabase functions deploy location-ingest --project-ref cykviouklidnbsbgdgdo --no-verify-jwt
supabase secrets set LOCATION_TOKEN=<openssl rand -hex 24>
```
Overland settings: endpoint `https://cykviouklidnbsbgdgdo.functions.supabase.co/location-ingest`,
the same token as Access Token, tracking "Significant location changes", send interval 5 min,
batching on. The token is typed into the phone and the secret — never into chat or git.

## Not built / unmeasured
Shortcut fallback; "Register this place" Shortcut (use THE DESK); battery impact; no end-to-end
fix from Joe's phone in this session (needs the deploy above); inferred places; transit metrics.
