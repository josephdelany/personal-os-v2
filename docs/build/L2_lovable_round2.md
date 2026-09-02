# L2 — Lovable Round 2: every source from the index, and the entity page

**Preconditions:** L1 accepted; B4 live (`get_entity`). Paste as ONE message.
**Scope:** `/sources` index polish, `/entity/:type/:key`, and the tap-through from the
SOURCES page module 8. Nothing else.

---

ROUND 2 — THE INDEX AND THE ENTITY PAGE.

1) `/sources` — the index already reads `get_domains`. Finish it:
- Group by `pillar` in the order of `pillars`. Pillar header: the pillar word, then in
  muted text "{k} of {n} sources capturing" where k = count of domains in that pillar
  whose `coverage.status` is `fresh` or `stale` (this is a count of envelope rows, which
  is allowed; it is not arithmetic on values).
- Each row: `display_name` · `replaces` (muted) · right side `hero.value hero.unit`
  (tap → trace sheet) or "never captured" · `<Coverage/>` · density word. Rows sort in
  envelope order; never re-sort by value.
- Row tap → `/sources/:domain` (the L1 page).
- Header line above the pillars: "As of {as_of}."

2) `/entity/:type/:key` — `supabase.rpc('get_entity', {p_type, p_key})`. Envelope:
```
{type, key, as_of, n, first_seen, last_seen, days_since_last, n_90d,
 amount_total?, amount_90d?, unit,
 by_month:[{month, n, amount?}], by_weekday:[{dow, n}], by_hour:[{hour, n}],
 recent:[{day, at, text, src, row_id}], trace}
```
or `{type, key, as_of, n:0, note}` or `{refusal, nearest?, note?}`.
- Header: `key` large, `type` small caps. Opening sentence, from exactly these
  templates: `n:0` → `note` verbatim; otherwise "{n} times since {first_seen}; last
  {days_since_last} days ago." and, when `amount_total` present, append
  " {unit}{amount_total} in total."
- Cards in this order, each omitted when its key is absent: BY MONTH (bars from
  `by_month[].n`, and when `amount` present a second series; months in envelope order, no
  gap-filling of missing months — a missing month is a gap, not a zero); BY WEEKDAY
  (seven bars, `dow` 1–7 Mon…Sun, missing dow = no bar); BY HOUR (24 slots, missing hour
  = no bar); RECENT (rows `day at · text`, tap → `/record/{day}`); the trace sheet on
  the header value.
- `refusal` → render verbatim; if `note` present show it under it.
- Back link to the source it came from (keep `?from=/sources/{domain}` in the URL when
  navigating from module 8; fall back to `/sources`).

3) Wire SOURCES page module 8 (ENTITIES) rows to `/entity/{type}/{key}?from=/sources/{domain}`.
Encode `key` with `encodeURIComponent`; decode before calling the RPC.

ACCEPTANCE: (a) `/sources` shows five pillar groups with the "k of n" line and no
value-based re-sorting; (b) `/entity/merchant/{top merchant}` renders all cards;
(c) `/entity/site/{unknown}` shows the n:0 note only; (d) `/entity/nonsense/x` shows the
refusal; (e) no client arithmetic; charts only on `by_*` arrays (DESCRIPTIVE).
