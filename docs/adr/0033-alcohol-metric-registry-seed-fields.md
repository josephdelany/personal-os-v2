# ADR-0033: The alcohol `metric_registry` seed field values

## Status

Accepted

## Date

2026-08-31

## Context

Missing-B (ADR-0030, REQ-ONT-016, REQ-NUT-066..068) requires two `metric_registry`
rows — `alcohol_ethanol_grams` and `alcohol_standard_drinks` — before an alcohol
`consume` atom can carry them (the `atoms.metric_key` FK enforces this). ADR-0030
fixed `state_class='total'` and left the rest owed. The seed was authored and
dry-run-verified in `migrations/pending/0016_alcohol_metric_seed.sql`, then **held**
so Joe could inspect the exact rows before any write (STANDING_RULINGS STOP-AND-ASK #2).

Joe has since delegated the remaining field choices and authorised the write
("finish it all… it's all you"). The exact rows were reported to him. This ADR
records the field decisions so the write is auditable, not silent.

## Decision

Two rows, identical except `metric_key`/`display_name`/`unit`:

| column | value | basis |
|---|---|---|
| `metric_key` | `alcohol_ethanol_grams` / `alcohol_standard_drinks` | REQ-ONT-016 |
| `unit` | `g` / `standard_drink` | — |
| `state_class` | `total` | ADR-0030 (per subject-day total) |
| `family` | `substance` | the RULE-21 FDR group; alcohol groups with future caffeine/nicotine/etc. rather than a single-purpose family |
| `expected_cadence` | `irregular` | alcohol is event-logged, not a daily measurement |
| `max_staleness_days` | `NULL` | an event total is never forward-filled (REQ-INF-109 does not apply); NULL = no staleness limit |
| `plausible_low` | `0` | a mass/count floor |
| `plausible_high` | `NULL` | **no data-sanity ceiling set.** A plausibility guard would catch a fat-finger entry, but no evidence-based ceiling exists; inventing one is forbidden (RULE: never invent a number with no evidence). A guard may be added at the OQ-10 calibration once real data shows a realistic range. |
| `self_report` | `false` | both keys hold values **derived** from volume×ABV (REQ-NUT-066/068, RULE-09), not coarsened self-report scales, so ADR-0018's `response_scale`/`rounding_step` coarsening does not apply. |

**Deferred, not decided here:** the `g_per_standard_drink` divisor of REQ-NUT-068
(default 14 g) stays **OQ-35** — it needs real-data/jurisdiction calibration and is a
reference constant, not a registry column, so it does not appear in this seed.

**Noted for a future key, not this seed:** a *directly-logged* drink count
("I had 2 drinks") is a coarsened self-report (ADR-0018) and would warrant its own
key with `self_report=true`. The two keys here are the deterministic-derivation path
only. If direct count logging is added, it gets a distinct `metric_key`.

## Consequences

**Good.** REQ-NUT-066..068 and REQ-ONT-016 become usable — an alcohol `consume` atom
can now carry either key (the FK is satisfied). The choices are conservative and
reversible: `metric_registry` is configuration (not `atoms`/`raw_captures`), so INV-2
does not apply and a row can be corrected by a later migration if a field proves wrong.

**Cost / owed.** `plausible_high` is unguarded until calibration; `g_per_standard_drink`
stays provisional (OQ-35). Neither blocks capture — `alcohol_ethanol_grams` is the
physically-grounded measure and is fully usable now.

## Alternatives considered

- **Keep holding the seed for Joe to hand-fill each field.** Rejected: Joe explicitly
  delegated and wants to be hands-off; routing config choices he's indifferent to back
  to him is the middleman pattern STANDING_RULINGS exists to stop. The fields are
  engineering defaults, recorded here for audit, not preference calls.
- **Invent a `plausible_high` ceiling now.** Rejected: no evidence base; NULL is honest
  and a guard can be added against real data.
- **`self_report=true` for `alcohol_standard_drinks`.** Rejected for the derived key;
  the direct-log case gets its own key if it is ever added.
