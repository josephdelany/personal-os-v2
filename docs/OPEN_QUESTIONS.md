# OPEN QUESTIONS

Things that are **not decided**. Claude Code must **ask**, not assume, on
anything in this file. Answering one of these produces either an ADR or an edit
to a requirements file, and the entry is then moved to RESOLVED with a date and
a pointer.

This file is the pressure valve that keeps `CLAUDE.md` and `CONSTITUTION.md`
short. Anything unresolved belongs here rather than accumulating as hedged
prose somewhere else.

Format: **ID · question · why it is open · what depends on it · what would
settle it.**

---

## Architecture and operations

**OQ-01 — Is the Supabase credential rotated?**
Why open: `***REMOVED-DEAD-CREDENTIAL***` was exposed in the previous build folder and has not
been rotated. Joe's ruling: *"its internal. its just finish the project and ill
close everything."* Recorded once, not raised again.
Depends on it: nothing technically; it is a standing exposure.
Settles it: Joe rotating it, or explicitly closing this as accepted risk.

**OQ-02 — What is the repository name and where does it live?**
Depends on it: every CI check, every keepalive, the Actions budget.

**OQ-03 — Public or private repository?**
Why open: public gives unmetered Actions with 4 vCPU / 16 GB, which is what
makes permutation inference affordable; it also makes all pipeline logic
public and means a committed secret is a real breach rather than an
embarrassment. Private caps at 2,000 minutes/month on 2 vCPU / 8 GB.
Depends on it: ADR-0001's compute budget; whether specification-curve and
permutation methods are affordable at all.
Settles it: Joe's comfort with publishing code that contains no data.

**OQ-04 — Which surfaces may run while the language model is unavailable, and
what do they show?**
RULE-15 requires graceful degradation everywhere; the actual fallback copy is
unwritten.

## Capture and nutrition

*Full text at `specs/02-capture-nutrition/requirements.md` §§A–G
"UNRESOLVED QUESTIONS" — 7 questions, A-Q1 through G-Q1.*

The two that block work:

**OQ-05 — What is the interval width for `weighed` food?**
Why open: the research gives defensible widths for `labelled` (±10%),
`portion_table` (±20%) and `photo_estimate` (0.75× / 1.6×, asymmetric) and
**no width at all for `weighed`**. ±5% is currently written into REQ-NUT-035
and is invented.
Depends on it: `weighed` is the narrowest interval in the system, so it alone
determines whether a daily energy total is ever tight enough to resolve a
deficit. Every claim about energy balance rests on this number.
Settles it: Joe deciding, or a small calibration exercise against a known food.

**OQ-06 — Is the subject-day boundary 04:00?**
Depends on it: the generated `subject_day` column in ADR-0002, and therefore
every daily aggregate ever computed. Changing it later rewrites history.

## Finance

*Full text at `specs/03-finance/requirements.md` §§A–F.*

**OQ-07 — "Necessary" was narrowed to "used / unused / unknown". Is that
acceptable?**
Why open: Joe asked the system to "see what is necessary and not based on other
data of usage." Necessity is three separable questions and only one — was it
used — is measurable. The requirements now emit `used` / `unused` / `unknown`,
default everything to `unknown`, cap inferred confidence by purchase type (gym
membership 0.90 down to clothing 0.00), and ban the words "necessary" and
"unnecessary" from the schema, the interface and every export.
Why the narrowing: personality-from-spend achieves AUROC 0.55–0.59 — near
chance. A system that cannot infer traits from spend certainly cannot infer
values.
Settles it: Joe accepting the narrowing, or naming what he would accept instead.
**This is the single largest gap between what Joe asked for and what is
specified, and he should be told so plainly rather than discovering it later.**

**OQ-08 — Is the pie-chart prohibition still in force?**
The only clause of the old money doctrine Joe did not explicitly address. It is
currently carried forward, with ranked lists answering "where do I spend the
most" instead.

**OQ-09 — SimpleFIN at $15/yr.**
Recorded as the one considered rule-break, in ALTERNATIVES CONSIDERED only. No
code path requires it and the adapter interface (REQ-FIN-030) makes a future
reversal free. Left open because Joe's $0 rule was stated twice and is treated
as hard until he says otherwise.

## Reasoning and statistics

*Full text at `specs/04-reasoning/requirements.md` §§A–I.*

**OQ-10 — Twelve numeric thresholds are placeholders, not decisions.**
Coverage floor (0.60), `n_eff` floor (20), minimum specifications in a curve
(50), E-value floor (1.5), demotion triggers (3 failures at 0.50; 5 at 0.60),
and six others. None appear in the research. Each is written into its
requirement as a named placeholder and listed locally.
Settles it: a calibration session once six months of real data exists — these
should be set against Joe's actual data density, not guessed now. Until then
they are explicitly provisional and every finding they gate says so.

**OQ-11 — `INSUFFICIENT` has two disclosure modes. Both?**
Partial ("here is what we have, here is what it would take") and absent ("we do
not have enough to answer this"). This is the choice that overturns the old
silence doctrine, and roughly a third of the reasoning requirements are shaped
by it. Joe's instruction reads as endorsing both. Confirm before building.

## Interface

**OQ-12 — Type scale and corner radii.**
The old `11_UI_SYSTEM.md` fixes a palette, a font stack, tabular numerals, a
4 px grid, ≥44 pt targets, and the motion rules — 150 ms, ease-out, opacity and
transform only, nothing celebratory. It does **not** fix a type scale or corner
radii. Those are the actual design gaps, and they are smaller than "no design
system".

**OQ-13 — Which apps' feel would Joe steal?**
Asked before, never answered. Interfaces come last (Phase 7), so this is not
blocking, but the answer is worth capturing whenever it arrives.

---

## RESOLVED

*(empty — entries move here with a date and a pointer to the ADR or requirement
that settled them)*

---

**OQ-14 — May `derived_measures` rows be deleted?**

*Question.* The guard hook blocks DELETE and UPDATE on `raw_captures`, `atoms`,
`entities`, `links` and `findings`. It does not block them on
`derived_measures`. Behavioural test `tools/test_guard.sh` confirms
`delete from derived_measures` is currently allowed.

*Why open.* Two defensible positions. Deleting a derived measure is recoverable
by recomputation, so it is not in the same class as deleting a capture — that
argues for allowing it. But a recompute that silently produces different numbers
than the ones already narrated to Joe is exactly the failure INV-3 exists to
prevent, and a delete makes that undetectable — that argues for append-with-
supersedes there too.

*Depends on it.* The atoms/derived boundary in ADR-0002, and whether
`derived_measures` needs a `supersedes` column at schema time (retrofitting one
later is a migration over every historical row).

*Would settle it.* A ruling from Joe, written into RULE-02 either way, plus the
matching line in `tools/test_guard.sh` flipped to the expected behaviour.

---

**OQ-15 — Shell-level egress blocking is bypassable and cannot be fixed at the
shell level.**

*Question.* RULE-29 requires every outbound request to go through the
egress-logged client. The guard hook enforces this by blocking `curl`, `wget`
and `nc`. Behavioural test confirms `python3 -c "import requests;
requests.get(...)"` passes straight through.

*Why open.* This is not a hole that a better regex closes — any language runtime
can open a socket, and a guard that blocks the obvious spellings while missing
the rest gives false assurance, which is worse than no guard. The real
enforcement is a forbidden-import lint (`requests`, `httpx`, `urllib`,
`aiohttp`, `socket` outside `lib/egress.py`) run in CI, plus a review check.

*Depends on it.* Whether RULE-29 can honestly claim tier SQL/LINT or must be
downgraded to REVIEW until the lint exists.

*Would settle it.* Writing the forbidden-import lint and adding it to
`tools/validate_layout.py`, then restating RULE-29's enforcement tier.
