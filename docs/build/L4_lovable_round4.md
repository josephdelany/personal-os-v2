# L4 — Lovable Round 4: ASSESSMENT complete, THE RECORD search

**Preconditions:** L3 accepted; B3 live (`search_record`). Paste as ONE message.

---

ROUND 4 — ASSESSMENT AND THE RECORD.

A) `/assessment` — keep everything from L0 and add:
- "Collection gap" card from `get_domains` (one extra call on this screen — allowed
  here because it is the daily brief): the domains whose `coverage.status` is
  `not_logged` or `never_captured`, as rows "{display_name} — {status text} → {capture_action}".
  Opener template: "{k} sources need attention." Zero → omit the card.
- "Findings waiting" card: the number `patterns_waiting.count` from `get_today` if
  present, else omit. Renders ONLY the count with a link to `/findings`; never a
  pattern's content on this screen (hard rule, unchanged).
- Layout on desktop: opening sentence full width; then a 2-column bento: left State
  (deviations, streaks, guardian), right Forecast + Watching; below, Week money and
  Collection gap side by side; Connection card last. Phone: the same order, stacked.
- The date line at the top: "For {for_day}, based on {based_on}."

B) `/record` — enable the search box. `supabase.rpc('search_record', {p_q, p_limit: 100})`
on submit (not on keystroke). Envelope:
```
{q, n, truncated, hits:[{day, at, kind, text, src, row_id}], by_month:[{month, n}], note?}
```
- Results view replaces the day view until cleared: opener template "{n} records for
  “{q}”{truncated ? ', showing the latest 100' : ''}." or `note` verbatim when present
  or "Nothing recorded for “{q}”." when n is 0.
- BY MONTH strip: a row of small bars in envelope order from `by_month[].n`, labelled
  with `month`; tap a bar → filter the hit list to that month (client-side filter of
  rows already in hand — allowed; no computation).
- Hit rows: `day at · icon(kind) · text`; tap → `/record/{day}` with the row
  highlighted by `row_id` (scroll to it if present in the timeline).
- Clear (×) returns to the day view.
- Keep the disabled-state tooltip removed.

C) `/record/:day` — add a "ribbon" above the timeline from `get_day.coverage`:
"{captures} captures · {atoms} atoms · {unextracted} unextracted" and, when
`last_extract_run` present, "last extraction {relative time} · {status}". Unchanged
otherwise.

ACCEPTANCE: (a) search for a merchant you know returns hits and the month strip;
(b) nonsense query shows the empty sentence; (c) tapping a hit lands on the right day
with the row highlighted; (d) `/assessment` collection-gap card lists only
not_logged/never_captured sources; (e) no pattern content on `/assessment`.
