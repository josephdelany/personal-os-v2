# ADR-0140 — An outage is not proof of nonuse

**Status:** accepted
**Date:** 2026-09-11
**Requirements:** REQ-FIN-110..116, REQ-REC-004/005/009; INTENT_COVERAGE R4
**Migrations:** 0073 (the `service_usage` method)

## The defect

`tools/engines/usage_status.from_evidence` decided the REQ-FIN-110 tier like this:

```python
tier = "used" if days < unused_after_days else "unused"
```

`days` is the age of the newest usage evidence. There is no other input. So stale evidence became
`unused`, unconditionally, and the two entirely different reasons evidence goes stale were read
identically:

| what happened | what the engine said | what is true |
|---|---|---|
| the source kept capturing and recorded no visit | `unused` | supported |
| the source stopped capturing | `unused` | **nothing was watching** |

**This is not a hypothetical failure mode in this system; it is the common case.** The Watch
stopped in five stages ending 2026-08-21. The bank CSV export died 2026-05-13. The largest
silences on record here are its own instruments failing. An engine that reads those as `unused`
accuses Joe of not going to the gym on the strength of a broken logger — which is exactly what
REQ-FIN-112's banned vocabulary exists to prevent, and what REQ-REC-009 states directly: absence
of a record is absence of capture.

The module was correct about everything else. It refuses a boolean, refuses a score, defaults to
`unknown`, bans five words on write rather than on display, and returns `unknown` for an empty
evidence list — its own docstring says *"a gym membership with no `place_visit` rows is not an
unused gym membership"*. It got the empty case right and the **stale** case wrong, which is the
harder one and the one that actually fires.

It also had **no caller outside `tests/`**, which is how the defect survived: every test asserted
the behaviour the code had.

## The rule

`from_evidence` takes `source_last_seen` — the last subject day on which the evidence **source**
produced anything at all. Not about this merchant; about anything. That distinction is the whole
mechanism: asking "when did this source last see THIS gym" returns the date of the last visit and
makes every outage look like continued watching. `tools/check_freshness.py` already measures
exactly this per metric.

```
no rows                              -> unknown   (unchanged)
recent evidence                      -> used      (unchanged)
stale, source silent since           -> unknown   the gap is the source's
stale, source kept recording         -> unused    something watched and saw nothing
stale, continuity not established    -> unknown   the caller cannot support the claim
```

### `source_last_seen=None` yields `unknown`, and that default is the point

The permissive default *was* the bug. A caller who never considered continuity silently got the
accusatory answer. An `unused` now has to be asked for by a caller able to say what was watching,
which is the only kind of caller entitled to one.

This changed one existing passing test. `test_REQ_FIN_113_a_status_names_the_evidence_that_produced_it`
asserted `unused` from a 71-day-old visit with nothing said about the source. Its assertion is
unchanged; it now has to state that the source kept recording afterwards. **That is the test
getting stronger, not weaker** (INV-6 / RULE-00): it previously passed without stating a
precondition the conclusion depends on.

## The method, and why an outage cannot become a conclusion

`service_usage` (0073) declares `usage_observation_window` as **required evidence**.
`tools/service_usage.py` emits that citation only when the tier is `used` or `unused` — that is,
only when `usage_status` established that something was watching. A dead source cannot make
`usage_status` return anything but `unknown`, and `unknown` emits no required citation, so the
engine's existing REQ-REC-009 path returns `unknown` and names the missing input.

**There is no branch anywhere from a dead sensor to a conclusion.** The refusal is structural: it
follows from a citation the dead sensor cannot produce, not from a check someone remembered to
write. This is the same shape as `evaluate()` having no `did_not_occur` return path at all.

A first version of the citation logic **got this wrong in the opposite direction**, and it is
worth recording because the error is instructive: it required the source to outlive the last
recorded use, which is right for a stale visit and wrong for a current one. A gym visited two
days ago came back `unknown`, because nothing had been recorded *after* the visit. The fix was to
stop restating the rule — the tier already encodes it, and two copies of a rule are two rules that
drift.

## `unused` is reported and never stored

`permissible_outputs` is `{occurred}` alone. "Joe did not use his gym membership" is not an event;
it is the absence of a class of events over a window, and `core.inferred_events` is the wrong
shape for it. Storing one row per un-used service per window repeats `watch_non_wear`'s mistake,
where 404 `unknown` days made the table 92% rows asserting nothing and buried the real episodes.

The three-tier status REQ-FIN-110 requires is computed and displayed by `tools/service_usage.py`,
with its evidence, every time (REQ-FIN-113 — never a bare label).

## What this connects

`recurrence.py` and `usage_status.py` were both complete, tested and callerless — two of the 28
required runtime capabilities with no caller measured at `48745d9`. `tools/service_usage.py` is
the first caller either has ever had. They were connected because R4 needed them, not to move a
reachability statistic.

## What it says today, and why that is correct

**No `place_visit`, `media_play` or `web_visit` atom has ever been written to this database.**
`source_last_seen` is therefore `None` and every recurring service is `unknown`. That is a true
statement about the record, not a failure of the tool, and it is printed as a sentence rather
than left to be inferred from a column of identical values.

Transaction atoms also do not exist in production yet — `public.transactions` holds 1,053 rows
and the backfill (`tools/backfill_transactions.py`) is part of the unapplied stack — so the tool
currently finds no streams there either. Both facts are about deployment, not about this unit.
