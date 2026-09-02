# Front-end design brief — for Joe's Cowork design session

Drop this file (plus the two referenced ones) into Cowork as context. Everything
here is either a hard constraint (the backend/constitution) or a decision already
made — the rest is yours to design freely.

## What you're designing
"My Life Compass" — the window onto the finished Personal OS backend. Six data
surfaces, each fed by exactly one API call returning one JSON envelope (all
contracts with example payloads: `docs/LOVABLE_RESUME.md`). One responsive web
app: designed on desktop, lived-in on phone (PWA).

## Decisions already made (don't re-litigate, build on them)
- The old "Proven" insight feed dies in round 1 (it renders the old system's
  untrustworthy claims). Nothing ships that shows it.
- Surfaces to cover (tab structure is YOURS to arrange): Today's brief · the
  minute Timeline (any day since 2019) · exploratory Patterns with Watch buttons ·
  the Trust/audit page · the 1,338-fact Insights battery · the capture Log.
- Auth: magic-link sign-in; "owner only" errors mean signed-out, never broken.

## Hard laws (the product's identity — design AROUND these, never against)
1. **Verdict before charts** (your own rule): every screen leads with one honest
   sentence; visuals are evidence below it, never the headline.
2. **Patterns surface = text and labels only.** No charts/plots for exploratory
   content anywhere, ever. Every pattern card wears its EXPLORATORY badge, its
   n / n_eff / q, and the verbatim hedged sentence.
3. **No gamification**: no streak flames, rings, scores-of-scores, badges,
   celebrations. Progress renders as plain numbers and bands.
4. **No judgment language**: numbers get labels, not verdicts (never "good/bad
   day", "too much", "wasteful").
5. **Render only what the envelope contains**: missing = "not logged"/"—",
   never zero, never invented; self-report scores always show their interval
   ("Energy 5 (4.5–5.5)"); every numeral traceable (row ids ride the payloads).
6. **Misses as visible as hits**: the Trust page shows refutations, missed
   forecasts, and blindspots at equal weight.
7. Tabular numerals for all numbers; motion subtle (150–300ms ease-out);
   respect reduced-motion.

## Free to design (your canvas)
Palette (evolve the dark-teal or replace it) · typography · tab count/arrangement
& navigation · card language · density vs air · how bands/ranges are drawn ·
iconography · the Timeline's visual metaphor · empty states' voice · desktop
bento vs single column · dark/light.

## Reference material
- `docs/LOVABLE_RESUME.md` — the six envelope contracts w/ real example JSON.
- Old workspace `01_architecture/FRONT_END_SPEC.md` — your "show everything,
  10x deeper" teardown of ~30 tracking apps (what to steal, which graveyards to
  avoid).
- Old workspace `01_architecture/APP_GLASS_BALL.md` — your original Glass Ball
  vision (the app IS this, minus the ring).

## When you're back
Bring: the look (screens/sketches/words — anything), your tab arrangement, and
anything you want changed in the envelopes. I turn it into numbered Lovable
rounds (I write, you paste, screenshot back). Round 0 (kill the Proven feed +
rewire data) is pre-written and waiting.
