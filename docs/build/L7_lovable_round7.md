# L7 — Lovable Round 7: polish — density, dark, motion, numerals

**Preconditions:** L6 accepted. This round changes no data flow. Paste as ONE message.
If credits are short, this round is the one to skip or split: parts A and B matter,
C and D are cosmetic.

---

ROUND 7 — POLISH. No new data, no new routes, no new RPC calls. Touch only presentation.

A) TYPOGRAPHY AND NUMERALS
- One typeface throughout; `font-variant-numeric: tabular-nums` on every numeral;
  numerals right-aligned in tables; units in a lighter weight directly after the value
  with a thin space.
- Opening sentences: one size larger than body, regular weight, max 70 characters per
  line, never bold, never coloured.
- Badges (tier, coverage): 11px caps, outlined, no fill; amber only for `stale`,
  `partial`, guardian, unknown-visit lines and non-ok heartbeats; teal only for `fresh`.

B) DENSITY
- Desktop bento: 12-column grid, 16px gutters, cards with 16px padding, no card taller
  than its content; lists show 10 rows then "show all".
- Phone: 12px side padding, cards edge-to-edge, sticky section header with the opening
  sentence collapsing to one line on scroll.
- Charts: 120px tall on phone, 180px on desktop, axis labels 11px, band ribbon at 12%
  opacity, no gridlines except a single baseline, no legends when a single series.

C) MOTION
- 150 ms ease-out for state changes, 250 ms for route changes, none for data refresh
  (values must not animate from 0 — they appear).
- `prefers-reduced-motion` → all durations 0.

D) DARK / LIGHT
- Dark is default. Verify every colour token has a light counterpart; check contrast
  ≥ 4.5:1 for body text in both. The trace sheet is monospace in both themes.

E) AUDIT (Lovable performs and reports, does not fix silently):
- List every string literal shown to the user that is not in an envelope and not in
  the templates of rounds L0–L6; remove any that judges ("good", "bad", "too much",
  "should", "great job", "streak", emoji).
- Confirm zero `from('`, zero client arithmetic on envelope values, zero coordinate or
  map references, zero chart bound to `drives`/`driven_by`/`patterns`.
- Report bundle size and Lighthouse mobile scores.

Done when the audit is reported and the four checks are zero.
