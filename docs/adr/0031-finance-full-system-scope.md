# ADR-0031: Finance is a full system (income, balances, budgets, forecasting) — with net worth carved out and no live spend counter

## Status

Accepted

## Date

2026-08-24

## Context

The requirements audit (`docs/REQUIREMENTS_AUDIT.md`, C-3 / Missing-C) found the
finance spec (`specs/03-finance/requirements.md`) is titled "FINANCE / **SPEND**
SUBSYSTEM" and, of the eight components of a full personal-finance system, covers
only **transactions, recurring, and categories**. Income, account balances/cash
position, budgets/targets, forward forecasting, and net worth are absent or
explicitly forbidden — a majority-foreclosure of **want 8 (finance as a full
system)**, recorded nowhere as a deliberate trade. Each ban was individually
defensible on the over-spend restraint evidence (precise, always-on spending
feedback increased spending by $32–40; Pocheptsova/Ghosh/Huang), but collectively
they narrowed the subsystem to a spend tracker.

Verified verbatim against the spec:
- `REQ-FIN-210` — "SHALL NOT display a running count of money spent or remaining in
  the current period."
- `REQ-FIN-212` — "SHALL NOT express any forward-looking amount as a single number"
  (range-only).
- `REQ-FIN-214` — "SHALL NOT define, store or display a budget target **for any
  individual category**" (the ban is *category-scoped*).
- `§A NON-GOALS` — real-time balance display, investment/portfolio tracking, and
  net worth explicitly out.
- `REQ-FIN-041` is a defined requirement that *reads* a "reconciliation and balance
  layer" (`SHALL read posted_at and SHALL NOT read occurred_at`), but that layer's
  broader behaviour — what it reconciles, what balance it surfaces — is specified in
  **no** requirement. A forward/under-specified reference, not a missing ID.

Joe ruled want 8 at consequence level on 2026-08-24.

## Decision

**Finance is a full system, with one carve-out and one surviving constraint.**

**IN (to be specified as new requirement-sets, Missing-C):**
- income / earnings ingestion (today the only inbound handling nets P2P receipts
  against bar tabs — never income);
- account balances and cash position;
- budgets / targets;
- range-based forward forecasting (buildable from existing recurrence detection);
- the `REQ-FIN-041` reconciliation-and-balance layer, now to be actually specified.

**OUT for now:** net worth, investments, portfolio. This is **not** a restraint
decision — it is simply not what was asked, and it is addable later without
re-architecting. (`§A NON-GOALS` keeps net worth/investments out; balances move IN.)

**CONSTRAINT that survives, and does not reverse:** **no live running counter of
money spent or remaining.** The $32–40 over-spend evidence is specifically about
precise, always-on feedback, and a live budget countdown is exactly that. Budgets
and forecasts are **retrospective or range-based, never a live number ticking
down.** Concretely:
- `REQ-FIN-210` is **KEPT** as the no-live-counter constraint.
- `REQ-FIN-212` is **KEPT** as the range-only constraint on forward amounts.
- `REQ-FIN-214` is **REVERSED** — budgets/targets come IN. **Scope note:** the ban
  was *per-category*; this reversal brings budgets in more broadly, so the
  category-vs-all scope of the new budget requirement is a knowing decision, not an
  omission (flagged in the audit worksheet).

## Consequences

**Good.** Want 8 is delivered as asked instead of silently narrowed to a spend
tracker. The restraint evidence is honoured where it actually applies (no live
always-on counter) without deleting income, balances, budgets, and forecasting to
get there. The `REQ-FIN-041` under-specified layer gets a real spec.

**Cost / owed (named, not hidden).** This ADR is the rationale and scope; it writes
no requirements. Track 1.2 owes: the Missing-C requirement-sets (income, balances,
budgets/targets, range-forecast, reconciliation layer); the `REQ-FIN-214` reversal;
keeping `REQ-FIN-210`/`212` as the surviving constraints; and a reconciliation of
the new budget/forecast surfaces against the RULE-23 (inform-never-moralise) and
RULE-24 (no gamification / no live intervention counter) restraint rules — the new
budget surface must not become the scolding tally RULE-23 forbids. **Nothing here
touches a schema** (finance ingest tables are Phase-3 net-new); this ADR stops at
the requirement-authoring layer, before any migration.

**Tension to hold:** a budget-vs-actual surface is one wording slip from a
compliance score (RULE-24) or a necessity verdict (RULE-23). The requirement text
must keep it retrospective/range-based and judgment-free.

## Alternatives considered

- **Keep it a spend subsystem (status quo).** Rejected by Joe: it forecloses a
  stated want and records the trade nowhere; the restraint evidence constrains
  *how loudly* the surface speaks, not whether income/balances/budgets exist.
- **Full system including net worth/investments now.** Rejected for now: not asked,
  and portfolio tracking is a genuinely separate subsystem (the `§A` "wrong
  subsystem" note stands). Addable later without rework.
- **Reverse REQ-FIN-210 too (allow a live remaining-balance counter).** Rejected:
  that is precisely the precise-always-on-feedback the $32–40 evidence indicts. The
  live-counter ban is the one restraint constraint that survives the want-8 opening.
