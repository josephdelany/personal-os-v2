# ADR-0001: Compute placement — three tiers, one owner per number

## Status

Accepted

## Date

2026-08-06

## Context

Personal OS computes derived numbers — daily energy balance, a Kalman-filtered
weight and TDEE trend, a Widmark alcohol curve, within–between effect
estimates, correlation surfaces with FDR control — and renders them across a
PWA, notifications, and a question-answering surface.

Three execution environments are available, and all three are free:

1. **Postgres** on the Supabase free tier — always on, transactional, cheap for
   set operations, incapable of anything requiring SciPy.
2. **Python in GitHub Actions** — 2,000 minutes/month on a private repository
   with 2 vCPU / 8 GB, or *unmetered* on a public repository with 4 vCPU /
   16 GB, 6-hour job cap. The unmetered public tier is what makes permutation
   inference and specification curves affordable at all.
3. **Cloudflare Workers AI** — inference only. 10,000 neurons/day.
   `whisper-large-v3-turbo` costs 46.63 neurons per audio-minute, giving ~214
   audio-minutes/day. Projected full-system steady state is ~2,760 neurons/day,
   about 28% of the allowance. Critically, **Cloudflare hard-fails at the limit
   rather than billing**, which converts a cost risk into an availability
   event — the correct trade under a $0 constraint.

The previous specification stated the placement rule in exactly one sentence,
at line 34 of a handoff file that sat outside the numbered specification and
outside its own precedence chain. The predictable result: the within–between
estimator and the deload detector had rendering surfaces and no owner
anywhere at all, and the Kalman filter, the Lomb–Scargle periodogram, the
Widmark fit and the reliability calculation had surfaces but no named job. The
most load-bearing architectural rule in the project was also its least
governed.

Separately, an empirical finding settles the role of the language model. In
PHIA (Google, *Nature Communications*), a model reasoning over personal health
data in context answered numeric questions with **22%** accuracy; the same
model writing code that was then executed deterministically reached **84%**.
The gap is not a prompting problem. It is the difference between a system that
computes and a system that hallucinates plausibly.

## Decision

**Every computed number has exactly one owner, in exactly one tier, stamped
with the `code_version` that produced it. Nothing recomputes a value it does
not own.**

Placement rules, in order of precedence:

1. **If it can be expressed as SQL over stored rows, it lives in Postgres.**
   Aggregation, windowing, lens predicates, coverage counts, the read API,
   ASOF joins against bitemporal history.
2. **If it needs SciPy, statsmodels, NumPyro, dynamax, or more than a few
   seconds, it lives in a scheduled GitHub Actions job**, and it writes its
   result back into Postgres as rows. The job name is recorded in
   `ops.job_registry` next to the measure it owns.
3. **If it is inference over unstructured input — transcription, extraction,
   embedding, narration — it lives in Workers AI**, and its output is names,
   spans, and labels. Never quantities. Never claims.
4. **The PWA renders. It does not compute.** No arithmetic beyond formatting
   in client code.
5. **The language model plans and narrates. It never computes.** For an
   open-ended question, the model emits a query plan; the plan is executed
   deterministically; the model narrates only what the returned rows contain.

Enforcement, so that this ADR does not repeat the fate of line 34:

- `ops.job_registry` maps every derived measure to its owning tier and job. A
  CI check fails if a measure is read by any surface and has no registry row.
- A lint rule bans arithmetic operators outside a formatting allowlist in the
  render layer.
- A lint rule bans numeric literals in model output schemas for nutrition,
  finance, and statistics — the model may return a name and a span, not a
  value.
- Every job writes a row to `ops.runs` on start and finish, with row counts.
  Staleness alerts fire off that table. *Four feeds died silently in the
  previous system — health for ~26 days, location ~22, spend ~28, and browsing
  since 19 June — and nothing noticed.*

Two operational hazards are covered here because they are placement facts:
**Supabase pauses a free project after 7 days of inactivity, and GitHub
disables scheduled workflows after 60 days of repository inactivity.** Both get
keepalive jobs in Phase 0. Either one silently ends the project otherwise.

## Consequences

**Good.** Numbers agree across surfaces by construction. Every number is
reproducible from its `code_version` and its input rows. The 22%-accuracy
failure mode is architecturally impossible rather than discouraged. The
unmetered public-repository tier makes permutation-based inference affordable,
which is what allows honest multiplicity control at N=1 sample sizes.

**Bad.** A public repository means the code is public, so no secret may ever be
committed and no personal data may ever enter the repository — enforced by a
pre-commit hook, not by care. Batch scheduling means results are stale by up to
the job interval, so every derived measure carries `computed_at` and every
surface shows it. Adding a derived measure now requires a registry entry, a
job, and a migration — friction that is the point.

**Deferred.** Whether the repository is public or private is not settled here;
it is in `OPEN_QUESTIONS.md` as OQ-03, because it trades compute budget against
code exposure and the answer depends on how much of the pipeline logic Joe is
comfortable publishing. *(OQ-03 later RESOLVED public — ADR-0013.)*

## Correction 2026-08-23 — PHIA numbers refined (decision unchanged)

The Context above quotes PHIA as **22% in-context vs 84% executed**, which
overstates what deterministic execution alone buys. The published breakdown
(PHIA, *Nature Communications*, 12 Jan 2026) is three-way: **22%** no-tools
in-context, **74%** one-shot generated-and-executed code, **84%** the full
ReAct agentic loop. Executing code at all buys the large gap (22→74); the loop
adds the last ~10 points (74→84). Caveats: Gemini 1.0 Ultra for all main results
(a GPT-4 chain-of-thought comparison at 53.6% is also reported), not yet
independently replicated. **The decision in this ADR is unchanged** — it
depends only on "executed ≫ in-head," which the corrected numbers support at
least as strongly. See ADR-0014 for the matching constitution correction
(RULE-11).
