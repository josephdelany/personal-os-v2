# Lovable front end — the paste-ready build package

**When to use this:** after ~2 weeks of captures are flowing (the alert I'll give
you). Everything below is ready now so that "time for the front end" is one paste
into Lovable, zero thinking. The backend contract is frozen; fields get added,
never renamed.

**Before pasting:** migration 0021 (`get_day`) must be applied, and Supabase Auth
needs one user (you) — Dashboard → Authentication → Add user (your email). The old
dashboard already used magic-link auth; this is the same pattern.

---

## The prompt (paste into Lovable)

Build a single-page personal daily log — React, on my existing Supabase backend.
Do NOT create tables. Connect:

- Project URL: `https://cykviouklidnbsbgdgdo.supabase.co`
- Use the **anon publishable key** I provide in Lovable's Supabase integration.
- **Supabase Auth, email magic-link.** Every read is the RPC below, which is
  EXECUTE-granted to `authenticated` only — an unauthenticated call returns a
  permission error, and that is correct behaviour, not a bug to fix. No service
  key in the client, ever.

### The one read

`supabase.rpc('get_day', { p_day: '2026-09-01' })` (or `p_day` omitted for today)
returns:

```json
{
  "day": "2026-09-01",
  "checkin": {
    "checkin_morning_energy":  { "point": 5.0, "low": 4.5, "high": 5.5, "atom_id": "…" },
    "checkin_night_day_rating":{ "point": 7.0, "low": 6.5, "high": 7.5, "atom_id": "…" }
  },
  "food":  [ { "label": "big mac", "at": "…", "precision": "hour", "atom_id": "…" } ],
  "notes": [ { "text": "…", "at": "…", "atom_id": "…" } ],
  "coverage": { "captures": 3, "atoms": 9, "unextracted": 0 },
  "last_extract_run": { "at": "…", "status": "ok" }
}
```

Any key may be absent (no data that day) — render the absence honestly ("not
logged"), never a zero, never a placeholder value.

### The screen

One day view with a date picker (default today):
1. **Check-in scores** — morning row and night row of labelled chips
   ("Energy 5 (4.5–5.5)"). Show the interval; the point alone overstates
   precision. Metric label = the key minus `checkin_<type>_`, title-cased.
2. **Food** — a plain list of labels with times. No calories are in the data;
   show none. If the list is empty: "no food logged".
3. **Notes** — the note text, verbatim.
4. **Footer** — "`captures` captured · `atoms` facts · last processed
   `last_extract_run.at`" and, if `unextracted > 0`, "`unextracted` awaiting
   processing".

### Hard rules (these are the product, not styling preferences)

- **Never invent, estimate, or round a number.** Render only numerals present in
  the envelope. If a value is missing, say "not logged" — never 0, never a guess.
- **No streaks, no scores-of-scores, no badges, no celebratory animation, no
  compliance %.** A displayed number is an intervention; keep it plain.
- **No judgment language** — never "good/bad day", "too much", "unhealthy",
  "necessary". Label numbers with what they are, not verdicts.
- **Intervals are first-class** — a self-report is shown with its range.
- Motion: 150 ms ease-out, opacity/transform only. Nothing celebratory.
- Typography: tabular numerals for all numbers.
- This is a single-user private app; there is no sharing, no social, no export
  button in v1.

---

## What v2 adds (do not build yet)

Trends (e1RM, weight) come from `derived_measures` (Phase 5) via further RPCs of
the same envelope pattern. Recommendations, findings, and anything with an
evidence tier waits for the tier-labelling surface (RULE-17 sequencing). The
EXPLORATORY surface, when it comes, is text/labels only — no charts (ADR-0032).
