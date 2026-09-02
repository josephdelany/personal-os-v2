# docs/build — executable build orders for Claude Code

*Written 2026-09-02 from `docs/THE_FILE.md` Part III. One file = one Claude Code
session = one migration (or one tool). Nothing in here is a design discussion; every
file is a checklist with the exact SQL, the exact envelope, the exact test names, and
the exact commands whose output proves it done. Where the SQL depends on something only
the live database can tell you, the file says DISCOVER and gives the query.*

## How Joe uses this

Open a terminal in `~/PERSONAL_OS_V2`, start `claude`, and paste **one line**:

```
Read docs/build/README.md, then execute docs/build/B1_domains_config.md exactly as written. Do not redesign anything in it. Where it says DISCOVER, run the query and paste the output into ops/PROGRESS.md before continuing. Where it says DECISION, stop and ask me. Finish with the Definition of Done from docs/CONSTITUTION.md, including WHAT I DID NOT DO.
```

Next session, the same line with the next file. `/session-end` at the end of each.

## The order (do not reorder)

| # | File | Builds | Migration | Sessions |
|---|---|---|---|---|
| B0 | `B0_update_features.md` | `tools/update_features.py` — `ops/features.json` finally reflects reality | — | 0.5 |
| B1 | `B1_domains_config.md` | `config.domains` + `config.domain_metrics` + `get_domains()` — the SOURCES index | 0034 | 0.5 |
| B2 | `B2_get_domain.md` | `get_domain(p_domain, p_window)` — the nine-module envelope | 0035 | 1–2 |
| B3 | `B3_search_record.md` | `search_record(p_q, p_limit)` — full-text over the record | 0036 | 0.5 |
| B4 | `B4_get_entity.md` | `get_entity(p_type, p_key)` — merchants, categories, sites, channels, exercises | 0037 | 0.5 |
| B5 | `B5_movements.md` | restricted location store, ingress, in-DB place resolution, `get_movements` / `get_place` / `get_places` | 0038–0040 | 2–3 |
| B6 | `B6_get_findings.md` | `get_findings()` — the WATCHING / CONFIRMED / REFUTED / INSUFFICIENT lists | 0041 | 0.5 |
| L0 | `L0_lovable_round0.md` | Lovable Round 0: kill + rewire + seven-section shell | — | after B1 |
| L1 | `L1_lovable_round1.md` | Round 1: the SOURCES page on `get_domain` | — | after B2 |
| L2 | `L2_lovable_round2.md` | Round 2: the index finished + the entity page | — | after B4 |
| L3 | `L3_lovable_round3.md` | Round 3: FINDINGS lifecycle lists + RELIABILITY audit page | — | after B6 |
| L4 | `L4_lovable_round4.md` | Round 4: ASSESSMENT complete + RECORD search | — | after B3 |
| L5 | `L5_lovable_round5.md` | Round 5: MOVEMENTS (day, places, place page) | — | after B5 |
| L6 | `L6_lovable_round6.md` | Round 6: THE DESK capture/correct forms | — | after L5 |
| L7 | `L7_lovable_round7.md` | Round 7: polish; skippable if credits are short | — | last |
| — | `RUNBOOK_NO_CLAUDE.md` | How the system runs, and is kept running, with no model at all | — | read once |

**L0 can be pasted as soon as B1 is live.** Everything else it reads is already live
(`get_today` `get_timeline` `get_day` `get_patterns` `register_watch` `get_trust`
`get_insights_guarded` `ingest_capture`). Each later round names its precondition.
The Lovable rounds need no Claude at all — they can be pasted after the subscription
ends, one per credit window.

**Known gap not in this pack:** there is no *ask* RPC (REQ-ASK-*: a question in, a
tiered, traced answer out). THE DESK's Ask box stays disabled until it exists. It is a
larger build than anything here and goes after B6; it needs a model to design it, and
`RUNBOOK_NO_CLAUDE.md` §5 names it as the first thing to build when one is available again.

## Rules that apply to every file here

1. **Owner-lock pattern is copied, not reinvented.** Every read RPC begins with the exact
   preamble in `migrations/0032_forecast_today_trust.sql` (`LANGUAGE plpgsql STABLE
   SECURITY DEFINER SET search_path = ''`, the `auth.jwt()->>'email'` check,
   `jsonb_strip_nulls`) and ends with the `REVOKE/REVOKE/GRANT` lines. `anon` never
   gets EXECUTE on a read RPC.
2. **Schema tokens.** Inside a migration, core tables are `__CORE__.x` and ops tables
   `__OPS__.x` (the runner substitutes). `analysis.*`, `public.*`, `config.*`,
   `restricted.*` are written literally.
3. **Migration numbering** continues from `0033` (there is no `0028`; leave it).
4. **Dry run first, always:**
   `python3 tools/run_migration.py --core core_dryrun --ops ops_dryrun` then
   `python3 tools/run_migration.py --core core --ops ops --commit`.
5. **Tests** go in `tests/` and are named exactly as each file lists them (the REQ/ADR
   ID is in the name — DoD item 1/3). They connect with `lib.db.connect()`, run inside
   one transaction, set the owner JWT with
   `select set_config('request.jwt.claims','{"email":"joseph.delany21@gmail.com"}',true)`
   (see `tools/_probe_state.py` lines 46–48), and **roll back**. They read live data;
   they never leave a row behind.
6. **No coordinate literal, no home identifier, ever, in any file in git** (REQ-LOC-005).
7. **The envelope is the contract.** Fields are added, never renamed. A field that cannot
   be populated is **absent** (`jsonb_strip_nulls`), never `0`, `""`, or a sample (REQ-INF-505).
8. **Every numeral has a trace** (INV-3, REQ-ASK-009/011). No trace, no numeral.
9. **`search_path = ''` means every function call is schema-qualified** — including
   extension functions (`extensions.similarity`, `extensions.gin_trgm_ops`). Check with
   `SELECT extnamespace::regnamespace FROM pg_extension WHERE extname='pg_trgm'`.
10. **Do not touch `ops/features.json` by hand** (write-locked); B0 builds the only path
    that may move an entry, and every later session runs it.
11. Commit message: `B<N>: <what> (<REQ-IDs>)`, ending with the `Co-Authored-By` line
    this repo already uses.
12. If anything in a file is wrong against the live schema, **stop and say what**
    (push_back stance in CLAUDE.md). Do not silently substitute.
