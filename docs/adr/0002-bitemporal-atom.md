# ADR-0002: The atom — bitemporal, three-valued, interval-capable

## Status

Accepted

## Date

2026-08-06

## Context

Everything the system knows is stored as an *atom*: one row, one observation,
one moment. Sections — Workout, Nutrition, Sleep, Body, Mind, Context, Money —
are **predicates over atoms evaluated at read time**, never containers. A beer
at a bar is a nutrition atom, a context atom, a sleep confounder and a spend
event simultaneously, because it is one row that four predicates all match.
This resolves the problem that originally motivated the project — *"it's gonna
be impossible having mutually exclusive sections but idk how to do it"* — and
it is the single best idea in the previous specification. It survives unchanged.

What does not survive is the previous `atoms` DDL, for three reasons, each of
which is a root-level schema change and each of which is far more expensive to
add later than now:

**Bitemporality is not retrofittable.** If a row records only when something
happened and not when the system learned it, then the question "what did we
believe on 3 March" becomes unanswerable forever after. Every backtest, every
"was that prediction any good", every honest account of a revised measurement
depends on it. This is the single most expensive thing to add late.

**Two lanes are not enough axes.** The previous model had
`lane ∈ {hard, inferred}`, which conflates three genuinely independent
questions: how the value was obtained, whether the thing was present at all,
and how precise the value is. A logged absence and an unlogged day both became
zero. An estimated 550 kcal and a weighed 550 kcal became the same number.

**A point estimate is a false precision claim.** Nutrition resolution carries
652 kcal MAE from text recall and roughly 36% MAPE from vision with systematic
downward bias. Storing "550" asserts something the resolution method cannot
support.

Two ideas are borrowed rather than invented. Home Assistant encodes
`state_class ∈ {measurement, total, total_increasing}` in the schema, which
answers "may this be summed?" structurally — and lets the database refuse an
illegal aggregation, including one written by a language model. Exist.io's
value types distinguish "time from midnight" from "time from midday", which is
the clean fix for the bug where bedtime crossing midnight destroys an average.

## Decision

`atoms` is append-only and carries the following, beyond identity and payload:

**Time — four columns, not one.**
`occurred_at` (when it happened), `recorded_at` (when the system learned it,
system-set, never client-set), `time_precision` (`exact` / `minute` / `hour` /
`day` / `unknown`), and `subject_day` (generated, on a **04:00 local
boundary**, so that a 2 a.m. meal belongs to the night before rather than to
the next morning). Corrections are new rows carrying `supersedes`; nothing is
ever edited.

**Presence — three-valued.**
`presence ∈ {observed, observed_absent, unknown}`. "I logged that I did not
drink" and "I did not log" are different facts and never collapse.

**Value — an interval, with its method.**
`value_low`, `value_point`, `value_high` (asymmetric permitted),
`estimate_method`, and `unit`. A measured quantity sets all three equal and
`estimate_method = 'measured'`. Interval width is a function of the method, and
the method is stored so the width can be re-derived when the method improves.

**Aggregation legality — in the schema.**
`state_class ∈ {measurement, total, total_increasing}` and `value_type`
(including `time_from_midnight` and `time_from_midday`). The read API refuses
an aggregation that the `state_class` forbids, rather than trusting the caller
to know better.

**Provenance — mandatory, not optional.**
`source` (constrained to a registered set), `provenance`
(`extracted` / `inferred` / `defaulted`), `evidence_span` (verbatim source
text where the value came from a transcript), `confidence`, `code_version`,
`confirmed_at`, `corrected_at`.

**Kind — a closed taxonomy, plus a registry.**
The 20-member `kind` enum stays closed. What it lacked was a `metric_registry`
table describing each measure: its family for FDR grouping, its expected
cadence, its staleness limit, its unit, its `state_class`, and its plausible
range. The registry is what makes a *general* inference layer possible rather
than a hardcoded list of hypotheses — the statistics iterate over the registry,
not over hand-written pairs.

## Consequences

**Good.** "What did we believe on date D" is answerable, permanently. Point-in-
time correctness becomes one CI query (INV-4 / RULE-04) rather than a hope. An
aggregation that would be nonsense is refused by the database, including one a
model wrote. Interval arithmetic propagates honestly into every downstream
figure. Adding a new measure means adding a registry row, not writing a module.

**Bad.** Rows are wider and writes are more expensive; at N=1 volumes this does
not matter. Every read path must reason about intervals, which is real work and
makes some queries ugly. Three-valued presence means every aggregate must state
which of the three it counts, which is friction — and is exactly the friction
that prevents the zero-versus-null bug that ruins single-subject analysis.

**Migration.** The 14 legacy tables and the existing feature store are archived
to Parquet **before** any backfill runs, then backfilled into `atoms` with
`recorded_at` set to the archive timestamp and `provenance = 'inferred'` where
original provenance is unrecoverable. Roughly two years of browsing, media,
health, location and spend history is irreplaceable and must not be lost to
this migration; the archive job runs first, and its output is verified by row
count before a single row is written to the new schema.
