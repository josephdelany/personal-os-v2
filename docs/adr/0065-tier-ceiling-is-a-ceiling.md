# ADR-0065: `config.operations.tier_ceiling` is a ceiling, and is enforced as one

## Status
Accepted. Settles the ambiguity an adversarial review flagged as needing "an ADR sentence".
Changes `migrations/0049_ask_core.sql` only.

## Date
2026-09-09

## The ambiguity

`config.operations.tier_ceiling` was consulted only when the tier was still NULL:

```sql
IF tier IS NULL THEN SELECT o.tier_ceiling INTO tier FROM config.operations o ...
```

So it behaved as a **default**, not a ceiling. `effect`'s registered value is `PROMOTED`, but an
answer backed by a `CONFIRMED_OBSERVATIONAL` resolution set `tier` earlier and sailed past it,
rendering full causal dose-response language — *"HRV runs 3.200 ms lower per Steps step,
adjusted for day_of_week"* — on an operation the registry caps below that.

The review would not call it a defect without a ruling, correctly: the column might have meant
"the minimum tier a finding must reach for this operation to answer" (B11's build order reads
`'the stored finding for driver→outcome if one exists at PROMOTED+'`), in which case the name
and the comment were wrong instead.

## Decision

**It is a ceiling. It is enforced.** An answer's tier is capped at its operation's registered
value, and the finding's own tier is disclosed alongside rather than discarded.

The reasoning is about *whose warrant* the tier expresses. The confirmation gate (B9,
REQ-TIER-013 — registered DAG, minimal backdoor set, HAC errors, E-values, negative controls,
refutation tests) is what earns `CONFIRMED_OBSERVATIONAL`, and it earns it **for the finding**.
`effect` is a query operation that *reads* that finding and renders a sentence. Letting the
sentence inherit the finding's tier lets a SELECT statement speak with the authority of a
procedure it did not run.

That distinction is exactly RULE-16's: *"Each tier has a permitted vocabulary … A claim
rendered in language above its tier fails the build."* The claim here is the answer, not the
row it read.

Nothing is hidden. The stored result carries `tier_before_ceiling`, `tier_ceiling` and the
finding's `status`, so an auditor sees both the finding's strength and the fact that the
operation was not warranted to speak it. Raising `effect`'s ceiling is then a deliberate,
visible change to one row of `config.operations` — which is what a registry is for — rather
than something an individual answer does to itself.

## Consequences

- A `CONFIRMED_OBSERVATIONAL` finding answered through `effect` renders at `PROMOTED` and
  therefore in hedged language. That is a real loss of expressiveness, and it is the intended
  trade: the surface that *should* speak in confirmed language is the findings surface (B6's
  `get_findings`), which reads the register directly and whose tier is the finding's.
- If Joe wants `effect` to speak at CONFIRMED, the change is one UPDATE to
  `config.operations` plus a template at that tier — a decision with a diff, not a silent
  inheritance.
- The other operations are unaffected: their registered ceilings already matched the tier they
  computed, which is why this went unnoticed.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Enforce it as a ceiling (adopted)** | The name is right, the tier expresses the operation's warrant, and the finding's strength is still disclosed. |
| Rename it `tier_floor` and keep the inheritance | Rejected. It would let a query executor render CONFIRMED causal language without the confirmation gate having run for *this* claim, which is the failure RULE-16 exists to prevent. |
| Leave it ambiguous and document the behaviour | Rejected outright. The review's point was that a column named "ceiling" which is not one will be read as one by the next person, and the cost of that misreading is a causal claim. |
