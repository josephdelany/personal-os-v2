# ROADMAP — eight phases and their gates

The ordering principle: **the irreversible decisions come first, the vertical
slice comes before breadth, and the interface comes last.** The previous plan
had eleven rounds and reached 0 of 9 on round zero; this one is ordered so that
something usable exists in weeks rather than at month three, because month
three was already identified as the risk point — enough data to tempt
conclusions, not enough to support them — and nothing was ever done about it.

A phase does not end because the work feels done. It ends when its gate passes,
with output shown. **RULE-00: never weaken a gate to make it pass.**

---

## Phase 0 — Safety. Today, before anything else.

Archive **all live tables and all local legacy sources, count verified at
archive time** (not a fixed number — the original "14 legacy tables" was an
estimate written before anyone counted; the live DB held 34 `public` DATA
tables at first archive, 2026-08-23, plus 29 local-source entities already in
`_legacy_snapshot/manifest.json`). A number nobody checked is how a gate passes
while missing data. Archive to Parquet and verify by row count, **before** any
backfill touches anything. Roughly two years of browsing, media, health,
location and spend history is irreplaceable.
The 19 previous specification files **no longer exist** — they were lost with a
cloud workspace and were never on this machine. There is no document folder to
archive and none will be invented: **the legacy archive is the verified Parquet
snapshot, not a document folder.** Stand up `ops.runs`. Add the Supabase 7-day
keepalive and the GitHub Actions 60-day keepalive — either one silently ends the
project. Decide OQ-01 (credential), OQ-02 (repo name) and OQ-03 (public/private)
— **all RESOLVED 2026-08-23**, see DECISIONS (ADR-0013 for the repo decisions).

**Gate 0:** Parquet archives exist and row counts match source — this *is* the
legacy archive (the previous spec-document folder was lost and is deliberately
not recreated; criterion voided 2026-08-23). Both keepalives have run once on
schedule and left a row in `ops.runs`.

## Phase 1 — Constitution and doctrine. One session.

Already drafted: `docs/CONSTITUTION.md`. This phase is Joe reading it line by
line and ruling on each of the 30 rules, because every later extraction
decision depends on it and because it is the document where the reframe is
settled.

**Gate 1:** Every rule has an enforcement tier and an owner. Joe has explicitly
accepted or amended RULE-18, RULE-23 and RULE-30 — the three that reverse
previous doctrine.

## Phase 2 — The spine, in code.

Migrations for `atoms`, `entities`, `links`, `metric_registry`, `sources`,
`raw_captures`, `findings`, `ops.runs`, `ops.job_registry`, `ops.egress_log`.
RLS everywhere. UPDATE and DELETE revoked at the grant level. Every CI
invariant query written and running **except RULE-04 point-in-time correctness,
which is DEFERRED to Phase 5** — its query joins `derived_measures`, which does
not exist until then, so it cannot run this phase and is not silently counted as
passed (OQ-22; `tools/check_invariants.py` prints it PENDING with that reason).
`ops/features.json` created with every planned feature pre-marked failing. Legacy
Parquet backfilled into `atoms`.

**Gate 2:** All runnable invariant queries return zero rows (**RULE-04 explicitly
deferred to Phase 5, named not silent — OQ-22**). An attempted UPDATE on `atoms`
fails with a permission error, shown. The legacy backfill **reconciles** against
the Parquet archive — every archived row is mapped to an atom or excluded with a
recorded reason, exact per source table (reconciliation, not row-count equality;
ADR-0025).

## Phase 3 — One vertical slice, end to end: the Big Mac path.

Joe's own example, chosen deliberately because it is the largest gap and
because it forces every new mechanism at once. Voice or photo capture via
Shortcuts → `raw_captures` → extractive-only parse with evidence spans → food
resolution with interval-valued nutrition → merchant resolution → the
McDonald's transaction ingested from a Gmail receipt → both landing in the same
atom table → one `DESCRIPTIVE` finding rendered through the numeral-template
path.

No inference. No ladder. No experiment. If this slice works, the architecture
is proven. If it does not, better to know in month one than in month six.

**Gate 3:** Joe says "I ate a Big Mac from McDonald's" into a Shortcut and,
without touching anything else, the meal and the charge appear as linked atoms
with intervals, provenance, and a rendered figure that traces to a stored
computation. Twelve Gherkin scenarios from
`specs/02-capture-nutrition/requirements.md` pass, by name.

**Old-stack freeze (OQ-17).** The previous cron stack keeps running until this
phase proves a replacement. It is frozen/switched off **only** after the new
capture path **ingests one real day end to end** — capture → `raw_captures` →
atoms → rendered figure — with nothing hand-fed. Until that test passes, nothing
in the old stack is disabled. Phase 2 does not touch the old tables.

## Phase 4 — Breadth of ingest, then entity resolution.

Restore the four dead feeds — media dead since 19 June, health ~26 days stale,
location ~22, spend ~28 — **with staleness alerting on `ops.runs`, so the next
silent death is loud.** Then `resolve_entity` in full.

**Gate 4:** Every registered source has run inside its staleness limit, and a
deliberately withheld feed raises an alert within its limit, demonstrated.

## Phase 5 — Derived measures.

Kalman weight and TDEE with interval intake and the 7.1 kcal/g alcohol fix —
note that "7.1 kcal" appears nowhere in the entire previous specification.
Widmark. The within–between estimator with HAC errors, lag profiles,
permutation nulls, weakly-informative priors and specification curves. Every
one has a registry row and a named job before it has a surface.

**Gate 5:** No derived measure is readable by any surface without an
`ops.job_registry` row. Two independent implementations of the within–between
estimator agree to stated tolerance on the same input. **RULE-04 activates here
(deferred from Gate 2, OQ-22):** now that `derived_measures` exists, the RULE-04
point-in-time query runs in CI and returns zero rows, shown — the single query
that proves bitemporality works rather than merely existing in the schema.

## Phase 6 — Statistics and the ladder.

The family catalogue and two-stage FDR. The curated DAG with adjustment sets
and negative controls. The `hypothesis_register` with its pre-registration
constraint. The `predictions` table with scoring and automatic demotion. The
six-tier ladder including `INSUFFICIENT` and coverage-based refusal. The
hypothesis library is re-authored here, aimed at the objective function —
strength and body composition — **before any results are seen.** The previous
library had 93 hypotheses and not one touched e1RM, sets, RPE, lean mass or
calories, which is to say it had near-zero coverage of the system's own stated
purpose.

**Gate 6:** A finding whose forward prediction fails is demoted with no human
action, demonstrated. A `CANDIDATE` from PCMCI+ cannot be reached by any read
path, demonstrated by attempting it. The vocabulary linter rejects a
deliberately over-claimed sentence.

## Phase 7 — Interfaces, last.

The 42 archived screens **no longer exist** — they were lost with the cloud
workspace, along with the spec-document folder (see Phase 0). Interfaces are
built fresh here and judged against RPCs that return real rows. Consequence to
resolve before this phase: the archived UI system that the honesty grammar,
design tokens and motion rules were to be "carried forward" from (ADR-0009,
OQ-12) was in the same lost archive, so those must be **re-derived, not
recovered**.

**Gate 7:** No screen renders a number that does not trace to a stored
computation. No arithmetic operator outside the formatting allowlist exists in
client code.

## Phase 8 — Hardening, and the forever rhythm.

The independent-re-derivation practice that caught twenty defects becomes a
scheduled job rather than a heroic effort. Prediction scores get reviewed.
`OPEN_QUESTIONS.md` gets worked down. The line budget on `CLAUDE.md` and the
30-item cap on the constitution are enforced in CI, because without them this
audit gets written again in eighteen months.
