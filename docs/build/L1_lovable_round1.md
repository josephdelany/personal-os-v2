# L1 — Lovable Round 1: the SOURCES page on `get_domain`

**Preconditions:** L0 done and accepted; B2 live (`get_domain`). Paste as ONE message.
**Scope discipline:** this round builds `/sources/:domain` and nothing else. If Lovable
touches another route, say "revert everything outside /sources/:domain".

---

ROUND 1 — THE SOURCE PAGE. One component, `<SourcePage/>`, driven entirely by
`supabase.rpc('get_domain', {p_domain, p_window})`. It replaces Whoop, Apple Health,
Mint, Screen Time and every other single-purpose app with one skeleton. Build it once;
every domain from `get_domains` routes to it. Do not special-case any domain.

ENVELOPE (fields absent = module absent = render nothing for that module, no placeholder):
```
{domain, pillar, display_name, replaces, as_of, window,
 coverage:{status, last_day?, stale_days?, first_day?, days_with_data?, days_in_window?, density},
 sentence,
 hero?:{metric, display_name, unit, value, day, band?:[lo,hi], z?, run_len?, position?, trace},
 why?:[{metric, display_name, unit, value, day, band?, z?, delta_vs_28d_median?, trace}],
 history?:{metric, unit, window, n, points:[{day, value, lo?, hi?}], trace},
 rhythm?:{window, unit, weekday:[{dow, median, n}], sentence?, trace},
 notables?:[{kind, day, text, trace}],
 driven_by?:[{hypothesis_id, tier, driver, outcome, lag_days, sentence, n, n_eff:[hi,lo], q, controlled_for?, watched, trace}],
 drives?:[...same...],
 forecast?:{metric, unit, day_target, lo, point, hi, claimed_coverage, trace, track_record?:{resolved, inside_band, achieved_coverage}},
 entities?:[{type, key, n, amount?, last}],
 capture:{action, shortcut?, correct_via},
 refusal?, nearest?}
```
If `refusal` is present render it verbatim with `nearest` as chips linking to
`/sources/{key}`, and nothing else.

WINDOW CONTROL: a segmented control 7d · 30d · 90d · 1y · all → `p_window`. Default
90d. Changing it refetches; only `history` and `entities` and `coverage.days_in_window`
change with it (the server decides; re-render everything from the new envelope).

PAGE ORDER, top to bottom — nine modules, each a card, each with a small left-aligned
label in caps. A card is omitted entirely when its key is absent.

0) HEADER: `display_name` large; `replaces` small muted ("replaces Whoop"); `<Coverage/>`
   from `coverage` (same component as L0); `density` word. Then `sentence` in the
   sentence style (it is the verdict; nothing above it but the name).

1) HERO: `value` `unit` huge, tabular. Beneath: a horizontal band bar from `band[0]` to
   `band[1]` with the value marker; if `position` is 'above'/'below' colour the marker
   amber; if `band` absent, show the value alone with "no personal band yet". Small print
   "{day}" and, when `run_len` ≥ 2, "{run_len} days {position}". Tap value → trace sheet.

2) WHY: one row per item: `display_name`, `value unit`, a mini band bar when `band` present,
   `delta_vs_28d_median` as "{±delta} vs 28d" in small print (sign from the server value,
   never computed). Tap → trace sheet.

3) HISTORY: a line of `points[].value` over `points[].day` with the band drawn as a
   shaded ribbon between `lo` and `hi` where present. Missing days are GAPS — never
   interpolate across a day that has no point. Y axis labelled with `unit`. Tap a point →
   navigate to `/record/{day}`. Under the chart: "{n} days in {window}".

4) RHYTHM: `sentence` first when present. Then seven bars from `weekday[]` in `dow`
   order 1–7 labelled Mon…Sun, heights from `median`, `n` under each. Unit on the axis.
   (This is DESCRIPTIVE data; a chart is allowed.)

5) NOTABLES: a plain dated list: `text` verbatim, `day` right-aligned. No icons, no
   colour, no badges. Tap → trace sheet.

6) DRIVES / DRIVEN BY: two lists titled "What drives this" (`driven_by`) and "What this
   drives" (`drives`). Each item: `tier` badge, `sentence` verbatim, small print "lag
   {lag_days}d · n {n} · n_eff {n_eff[0]}/{n_eff[1]} · q {q}{controlled_for ? ' · controlled
   for '+controlled_for : ''}", a Watch button → `register_watch({p_hypothesis_id})` → refetch;
   when `watched`, show "watching" instead. TEXT AND LABELS ONLY. No chart, no bar, no
   sparkline in these lists, ever. Empty list (key present but `[]`) → "No patterns
   above the null yet for this source." Key absent → omit the card.

7) FORECAST: range bar `lo`–`hi` with `point` marker, "for {day_target}", and beside it
   in the same card: "claimed {claimed_coverage} · achieved {track_record.achieved_coverage}
   on {track_record.resolved}" when `track_record` present, else "no track record yet".

8) ENTITIES: ranked rows: `key`, then `n` and `amount` (with `$` when present), `last`
   date. Tap → `/entity/{type}/{key}` (route exists but shows "arrives with round 2" —
   do not wire `get_entity` in this round).

9) CAPTURE: `action` as a sentence; when `shortcut` present, a button labelled "Open
   {shortcut}" that deep-links `shortcuts://run-shortcut?name={shortcut}`; a "Correct a
   value" text box that calls `ingest_capture` with `p_payload:{kind:'correction',
   domain, text}` and `p_source:'pwa_text'` and shows "Recorded."

TRACE SHEET: unchanged from L0 — key: value lines of the `trace` object, monospace.

STATES: while loading, show the header with `display_name` only (no skeleton charts).
On `owner only` → sign-in form. On any other error → "The file could not be read:
{error.message}" in a plain card. Never an empty chart.

ACCEPTANCE: (a) `/sources/sleep`, `/sources/money`, `/sources/attention` render with
different module sets and no console errors; (b) `/sources/places` shows header +
sentence + capture only; (c) `/sources/nonsense` shows the refusal and the chips;
(d) switching 90d → all changes the history point count and nothing is computed
client-side; (e) grep confirms no arithmetic on envelope values and no chart component
is ever passed `driven_by` or `drives` data.
