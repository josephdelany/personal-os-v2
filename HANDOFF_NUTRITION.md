# Worker 2 handoff — nutrition (B12), at `c523393`

For Session 1 (main), per `WORKER_BRIEF.md` → *Handoff*. Joe relays.

Branch `work/nutrition-finish`, from `48745d9` (clean). Nothing pushed, nothing merged, no
migration created, no file outside this worker's ownership modified.

---

## 1. What works end to end, through which command, at which revision

**Revision `c523393`.** Four statuses kept apart: implemented / tested / **deployed** /
**observed**. Everything below is *implemented and tested*. **Nothing is deployed or observed.**

| capability | command | status |
|---|---|---|
| The seven acceptance cases | `python3 tools/nutrition_acceptance.py` | **7 of 7**, runnable, disposable server |
| One food through the real cascade | `PYTHONPATH=. python3 tools/resolve_nutrition.py "x" --brand Y` | implemented; **unrun** — needs `SUPABASE_DB_URL` |
| USDA Branded + Foundation legs | via `nutrition.build_sources` | implemented; **no live request ever issued** |
| Joe answers a review item | `nutrition.accept_correction(...)` | implemented + tested; no CLI yet |

### Evidence at `c523393`

- **222 passed, 11 skipped** — every nutrition-touching test file, disposable PostgreSQL 17.
  All 11 skips are `tests/test_spine_insert_paths.py`, which needs the live database rather
  than the disposable socket. **No nutrition test skipped in that run**, which is the claim
  that matters: a skip is not a pass.
- **149 passed** deterministic (no database).
- `tools/validate_layout.py` — **43 / 43**, 1 pre-existing WARN (`.claude/settings.local.json`).
- `tools/nutrition_acceptance.py` — **7 of 7**.

**These are worker-branch results and are not proof of the integrated branch.** They must be
re-run after merge; see §2, without which they cannot be.

---

## 2. THE REGISTRATION GAP — the one thing that must not be missed

`tests/test_nutrition_usda.py` has **59 tests: 29 pure, 30 gated on `PERSONAL_OS_TEST_SOCKET`.**

The gate is correct and deliberate: those 30 run `CREATE SCHEMA` and build migration 0050 in
disposable schemas, so they must never point at production — that is the same hazard as the
`tests/test_status_sql.py` incident this checkpoint recorded as closed.

The consequence is that the **only** job that can run them is `local-sql`, which runs
`tools/test_local_sql.py`, whose `TESTS` tuple does not list the file. **Unregistered, those 30
tests skip everywhere and count as nothing** — the exact "counted but never executed" failure
the evidence audit found in the requirement ledger.

`tools/test_local_sql.py` is a workflow. `WORKER_BRIEF.md` puts workflows outside this worker's
ownership, so it has deliberately not been edited. **Exact change required**, after line 46:

```python
         "tests/test_nutrition_persistence.py",
         "tests/test_nutrition_usda.py",          # ← add this line
```

Whoever owns the harness should reconcile this against the capture worker's changes to the same
tuple before applying it; it is one line in a list several workers are appending to at once.

**Acceptance for integration:** after merge, `python3 tools/test_local_sql.py` must report the
30 as *passed*, not skipped. A green run that silently skipped them proves nothing.

---

## 3. Migrations needed — exact DDL, numbers REQUESTED not picked

Highest number on this branch is `0069`; 0055–0069 are unapplied. **Main allocates. These are
written with `__CORE__` / `__OPS__` placeholders to match 0050's convention.**

### 3a. `food_aliases` — REQ-NUT-002 / REQ-NUT-004

Currently an alias is written as a **second `foods_cache` row** keyed on the same
`(source, source_id)`, carrying `raw->>'alias_of'`. It works and is tested, but a REQ-NUT-008
re-fetch must update both rows, which is a defect waiting to happen.

```sql
CREATE TABLE IF NOT EXISTS __CORE__.food_aliases (
    alias_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alias      TEXT NOT NULL,                       -- lowercased; the matching key
    verbatim   TEXT NOT NULL,                       -- the phrase AS UTTERED, unnormalised
    food_id    UUID NOT NULL REFERENCES __CORE__.foods_cache(food_id) ON DELETE CASCADE,
    source     TEXT NOT NULL
               CHECK (source IN ('usda_branded','usda_foundation','off_product','joe')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (alias, food_id)
);
CREATE INDEX IF NOT EXISTS food_aliases_alias_idx ON __CORE__.food_aliases (alias);
```

Mechanical backfill from the existing bridge rows:

```sql
INSERT INTO __CORE__.food_aliases (alias, verbatim, food_id, source)
SELECT lower(a.canonical_name),
       COALESCE(a.raw->>'phrase_as_uttered', a.canonical_name),
       c.food_id, a.source
  FROM __CORE__.foods_cache a
  JOIN __CORE__.foods_cache c
    ON c.canonical_name = a.raw->>'alias_of'
   AND c.source = a.source
   AND c.source_id IS NOT DISTINCT FROM a.source_id
 WHERE a.raw ? 'alias_of'
ON CONFLICT DO NOTHING;
```

**Deliberately not included: a `DELETE` of the bridge rows.** Removing them changes what
`lookup_cached` returns and is a destructive change to a populated table. That is main's call,
and it should be a separate, reviewable statement. Until it happens the two representations
coexist harmlessly — the bridge row is still a valid cache row.

Once the table exists, `nutrition.remember_alias` is a small rewrite this worker owns and will
make on request.

### 3b. `portion_aliases` — REQ-NUT-018

Named by the requirement, present in no migration. `core.portions` (in 0050) is a different
thing: it keys on `canonical_name`, not on `(food_class, phrase)`, and has no correction count.

```sql
CREATE TABLE IF NOT EXISTS __CORE__.portion_aliases (
    food_class    TEXT NOT NULL,
    phrase        TEXT NOT NULL,
    grams         NUMERIC NOT NULL CHECK (grams > 0),
    n_corrections INTEGER NOT NULL DEFAULT 0 CHECK (n_corrections >= 0),
    source        TEXT NOT NULL DEFAULT 'joe' CHECK (source IN ('joe','portion_table')),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (food_class, phrase)
);
```

### 3c. `ops.rate_limits` — REQ-NUT-011, and now REQ-NUT-009 / REQ-NUT-012 too

**This gap grew during this session and the brief did not anticipate that.** It previously
affected only Open Food Facts. The new USDA `Quota` has the same limitation: it is a
**per-process** object, so two concurrent runs each believe they hold the whole ration.

For Open Food Facts that risks impoliteness. **For USDA it risks the key**, because REQ-NUT-012
is a provider 429 and the cooldown is currently forgotten when the process exits — a second run
started inside the hour will issue requests the provider has already refused.

A sliding window needs timestamps, not a counter, so this is two tables rather than one:

```sql
CREATE TABLE IF NOT EXISTS __OPS__.rate_limit_events (
    event_id  BIGSERIAL PRIMARY KEY,
    meter     TEXT NOT NULL,      -- the thing metered, NOT the leg:
                                  -- 'usda' (one api.data.gov key serves both datasets),
                                  -- 'off_search', 'off_product'
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rate_limit_events_meter_idx
    ON __OPS__.rate_limit_events (meter, issued_at DESC);

CREATE TABLE IF NOT EXISTS __OPS__.rate_limit_cooldowns (
    meter         TEXT PRIMARY KEY,
    blocked_until TIMESTAMPTZ NOT NULL,
    reason        TEXT NOT NULL,   -- 'provider_429' | 'quota_exhausted'
    set_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`meter = 'usda'` for both USDA legs is the same decision ADR-0138 §2 argues for, made durable:
one key, one meter. `rate_limit_events` needs a pruning step (anything older than the longest
window is dead); that is a scheduled job and a decision for main, not a default this worker
should pick.

---

## 4. What remains open

### 4a. `nutrition_display.py` still has no caller — `WORKER_BRIEF.md` priority 1, NOT done

Stated plainly because it was the brief's **first** objective. The Session 3 instruction this
worker received scoped the session to the USDA path and the B12 requirements in its ownership,
and that is what was delivered. `tools/engines/nutrition_display.py` is still referenced only
from a comment in `nutrition.py` and from its own tests — B12 §D.4 / §E.3 / §G.1 (vernacular
portions, interval rounding, daily totals, the deficit statement) therefore remain tested but
unreachable. **This is the largest remaining B12 gap and it is unstarted.**

### 4b. Live USDA verification — pending, blocked on a credential only

No request has been issued to api.data.gov. Every behaviour is exercised through an injected
transport. Needs `USDA_FDC_API_KEY` (or `PERSONAL_OS_USDA_API_KEY`) from
<https://api.data.gov/signup/> — free, no personal data required to register.

ADR-0106's *second* stated blocker is **withdrawn**: `api.nal.usda.gov` has been in
`config.egress_allowlist` since migration 0050 created the table, so RULE-29's recording
requirement was already met. Only the credential is outstanding. See ADR-0138 → *Correction*.

### 4c. `accept_correction` has no CLI

REQ-NUT-017 is implemented and tested but reachable only from Python. A small
`tools/answer_nutrition.py` would make it operable; this worker owns it and has not written it,
to avoid starting new work before ownership is reassigned.

---

## 5. Two defects fixed in passing, and one hazard found

- `Quota(max_requests=0)` raised `IndexError` out of an empty deque instead of deferring —
  would have killed a nightly batch rather than deferring one item. Found by a test.
- `egress_rows` in `tests/test_nutrition_integration.py` ordered by `egress_id`, a
  `gen_random_uuid()` primary key. A random shuffle, invisible only because no test there had
  ever logged two calls. Both `occurred_at` (transaction start, identical within a fixture) and
  `egress_id` are non-ordering; the helper now sorts.
- **OQ-80 hazard, reported not fixed:** `SUPABASE_DB_URL` is inherited by every agent shell, so
  a bare `python3 -m pytest -q` in a worktree runs the live-database suite **against
  production**. Observed here: the run sat at 0.3% CPU on pooler latency for ~25 minutes before
  being stopped, having reported nothing. The deterministic suite must be run as
  `env -u SUPABASE_DB_URL python3 -m pytest -q`. This is a property of the environment, not of
  any branch, and it makes "the full suite passed" ambiguous about which suite ran.

## 6. Checked, and NOT a defect

`analysis.legacy_daily.kcal` (migration 0026) is a scalar energy column and greps like a
REQ-NUT-030 violation. It is not: it sits beside `hrv`, `rhr`, `steps` and the sleep columns in
an Apple Health daily series, so it is device-measured **expenditure**, not a food-derived
intake estimate. REQ-NUT-030 governs nutrition storage. Recorded because the next person to
grep for a scalar `kcal` will find it too.

## 7. Coverage claim, stated at its real strength

Before this session, **all 60** REQ-NUT were already *named* by passing tests, so the count did
not move and is not the headline. What moved: **five requirements were evidenced only by
`tools/engines/ontology_contract.py`** — a contract module asserting what a rule should be —
and now **none are**. REQ-NUT-005, 007, 009, 017 and (in part) 030/031/032 each have at least
one test against code on the execution path.

That is a smaller claim than "proven" and a larger one than the ledger previously supported.
Per the checkpoint's standard, a requirement is proven when a named test containing its ID
**ran and passed in a recorded run** and its **body demonstrates the requirement** — which for
the 30 gated tests is true only once §2 is applied.
