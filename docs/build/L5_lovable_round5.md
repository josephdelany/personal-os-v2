# L5 — Lovable Round 5: MOVEMENTS

**Preconditions:** L4 accepted; B5 live (`get_movements`, `get_place`, `get_places`,
`assign_place`) and at least one day of real fixes. Paste as ONE message.

---

ROUND 5 — MOVEMENTS. Labels, minutes and aggregates only. **The app never receives,
stores, displays or requests a coordinate. No map component, no map tiles, no
geolocation API call, ever.** (This is the privacy boundary; it is not negotiable.)

1) `/movements` (default day = today) — `supabase.rpc('get_movements', {p_day})`. Envelope:
```
{day, tier:'DESCRIPTIVE', provisional:true,
 coverage:{fixes, first_fix_at?, last_fix_at?, longest_gap_min?, status:'none'|'partial'|'fresh'},
 last_known?:{label, kind, at, minutes_ago},
 visits?:[{visit_id, label, kind, is_home, place_id?, arrive, depart, dwell_min, n_fixes, trace}],
 unknown_visits, 
 mobility?:{distinct_places, home_min?, away_min?, first_leave?, last_return?, trips, radius_of_gyration_km?, window}}
```
- Date picker and ‹ › arrows as in THE RECORD.
- Opening sentence, templates: `coverage.status='none'` → "Nothing captured on {day}."
  (and nothing else on the page but the capture hint "The location logger sends fixes
  automatically; if this persists, open Overland and check it is running.");
  otherwise, for today: "Last known: {last_known.label}, {last_known.minutes_ago} min
  ago." ; for a past day: "{visits.length} places, {mobility.away_min} min away from
  home." (count of rows + envelope value; no arithmetic).
- COVERAGE line under the sentence: "{fixes} fixes · {first_fix_at}–{last_fix_at} ·
  longest gap {longest_gap_min} min" with status colour (partial = amber). Text
  "provisional thresholds" in small print when `provisional` is true.
- DAY STRIP: a horizontal 24-hour bar (04:00 → 04:00) with a block per visit from
  `arrive`–`depart`, labelled with `label`; home visits in a muted tone; unknown visits
  hatched. Gaps between visits are empty — never fill them.
- VISITS list: rows "{arrive}–{depart} · {label} · {dwell_min} min"; unknown visits
  show label "unknown place" and a "Name it" button → a small sheet with a text field
  and a kind picker (home gym bar work restaurant shop friend family transit other) →
  `supabase.rpc('assign_place', {p_visit_id, p_label, p_kind})` → refetch. Tap a named
  visit → `/movements/place/{place_id}`.
- MOBILITY card: `distinct_places` · `home_min` · `away_min` · `trips` ·
  `radius_of_gyration_km` (label "radius of gyration") · `first_leave` · `last_return`,
  as labelled numerals; absent keys omitted. Badge DESCRIPTIVE.
- `unknown_visits` > 0 → an amber line "{unknown_visits} unnamed places today."

2) `/movements/places` — `supabase.rpc('get_places')`. Envelope `{places:[{place_id,
label, kind, is_home, visits_n, last_visit}]}`. A plain register: rows sorted as sent
(home first); tap → place page. Empty → "No places registered yet. Name an unknown
visit to create one."

3) `/movements/place/:place_id` — `supabase.rpc('get_place', {p_place_id})`. Envelope:
```
{place_id, label, kind, is_home, tier:'DESCRIPTIVE', visits_n, first_visit, last_visit,
 dwell_total_min, dwell_median_min, by_weekday:[{dow,n}], by_arrival_hour:[{hour,n}],
 recent:[{day, arrive, depart, dwell_min, visit_id}], money_here?:[{merchant, n, amount}], trace}
```
- Opener template: "{visits_n} visits since {first_visit}; typically {dwell_median_min}
  min." BY WEEKDAY and BY ARRIVAL HOUR as bars (DESCRIPTIVE). RECENT rows tap →
  `/movements?day={day}`. MONEY HERE rows "{merchant} · {n} · ${amount}" (ground truth
  for gym/bar/restaurant visits). Trace sheet on the header.

4) Nav: `/movements` gets a sub-nav Day · Places.

ACCEPTANCE: (a) `grep` the codebase for `lat`, `lng`, `lon`, `geolocation`, `leaflet`,
`mapbox`, `google.maps` → zero results; (b) a day with no fixes shows only the
"Nothing captured" state; (c) naming an unknown visit creates a place and the row
updates after refetch; (d) the day strip never draws anything between visits.
