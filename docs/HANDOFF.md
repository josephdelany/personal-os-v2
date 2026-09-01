# HAND-OFF — what runs, what's next, how to pick this up cold

Written 2026-09-01 so that **Joe alone, or a fresh session with no memory, can operate
and continue this system** — especially after the Claude subscription ends. Claude is
needed to *build*, not to *run*: the finished system is Supabase + GitHub Actions + iOS
Shortcuts + Apple's on-device models, $0 forever, no Anthropic dependency at runtime.

**Check current state any time:** `PYTHONPATH=. python3 tools/status.py` — keepalive
health, capture counts, what's waiting. Read-only, safe to run.

---

## 1. What runs unattended right now (no one has to do anything)

- **Two keepalives** fire daily on GitHub Actions cron (`.github/workflows/keepalive.yml`,
  `17 6 * * *`) and write `ops.runs` rows. They stop Supabase pausing (7-day) and GitHub
  disabling the schedule (60-day). **Gate 0 is closed** — verified in `ops.runs`
  (`keepalive_supabase` + `keepalive_github`, `trigger=schedule`, `ok`). This is the only
  thing that *must* keep running for the database to survive; it does, on its own.
- **CI gates** run on every push (`.github/workflows/gates.yml` → `tools/validate_layout.py`):
  spec/index consistency, no fabricated data files, no committed coordinate, the
  forbidden-import lint (RULE-29 egress boundary). 38 checks, all green.

## 2. What's LIVE but empty (built, applied, waiting for input)

- **Capture ingress** — `public.ingest_capture(...)` on the live database (ADR-0034,
  migrations 0017/0018). A phone Shortcut POSTs a note → `core.raw_captures`. Write-only:
  the `anon` key can append a capture and nothing else. **`raw_captures` is 0 rows —
  nothing is fabricated.**
- **The spine** — `core.atoms/entities/links/findings/metric_registry/raw_captures`,
  all invariants enforced (append-only, bitemporal, INV-1 FK). Empty by design (Gate 2).
- **Alcohol metric keys** seeded (`alcohol_ethanol_grams`, `alcohol_standard_drinks`;
  ADR-0033, migration 0016).

## 3. THE ONE THING BETWEEN HERE AND REAL DATA

Build the capture Shortcut on the phone (`docs/CAPTURE_SHORTCUT.md`, ~10 min) and tap it.
That is the only remaining step to the first real row, and it can't be delegated or faked
(RULE-01). **The data clock is the binding constraint** — every day without capture is
data gone forever (`ops/WORK_QUEUE.md`). Crude manual logging (a lifting app, meal photos,
a nightly note) is just as valid and imports later; the Shortcut just automates it.

## 4. What to build next, in order (and what each needs)

1. **Extraction: `raw_captures → atoms`.** Reads `processing_status='received'` captures,
   extracts names/quantities with a model (RULE-09 — extract only, never compute a number),
   deterministic lookup converts to values, writes atoms. **Needs the Cloudflare Workers AI
   credential** (account id + API token) — not currently on this machine. Deferrable: raw
   captures are immutable, so extraction can run any time later, even post-subscription.
2. **Passive feeds** (Gmail receipts, Apple Health, browsing, YouTube). Each is a scheduled
   GitHub Action writing `ops.runs` + `raw_captures`. **Needs per-source server-side OAuth
   credentials** stored as GitHub Actions secrets. These run unattended once set up.
3. **A richer surface.** `tools/status.py` is the honest v0. A read page comes in Phase 7.

## 5. What breaks first (failure modes, ranked)

1. **Nothing captures** — the live risk. Not a bug; the Shortcut isn't built / logging
   hasn't started. Fix: §3. `tools/status.py` shows `total captures: 0`.
2. **Keepalive stops** — if GitHub disables the cron (60-day inactivity) or the Actions
   secret `SUPABASE_DB_URL` is removed, the database can pause. Check: `status.py` LIVENESS
   shows `STALE`. Fix: re-run the workflow (`gh workflow run keepalive.yml`) and confirm
   the secret exists (`gh secret list`).
3. **anon key leaked** — worst case is capture-spam (append-only rows, no read, no other
   table). Mitigate: rotate the anon key in Supabase; a shared capture token or rate limit
   can be added to `ingest_capture` (ADR-0034 residual).
4. **Storage ceiling** — Supabase free is 500 MB (~200 MB used by the *old* stack). Not
   near it. OQ-20 tracks the eviction design; not urgent.

## 6. Credentials — what's held, what's needed, and by whom

| credential | where | status |
|---|---|---|
| `SUPABASE_DB_URL` | `.claude/settings.local.json` (local) + GitHub Actions secret | **set** — DB access + keepalive work |
| GitHub auth (`gh`) | keychain, logged in as `josephdelany` | **set** — push, secrets, workflows |
| Supabase **anon key** | *Joe's phone (the Shortcut)* | **Joe pastes from dashboard**, never shared with the agent |
| Cloudflare Workers AI token | not present | **needed for extraction** (step 4.1) — Joe adds to `settings.local.json` when ready |
| per-source OAuth (Gmail, Health…) | not present | **needed for passive feeds** (step 4.2) |

## 7. The map (where things are)

- **Migrations** `migrations/0001..0018` — the schema, applied to live `core`. Apply a new
  one: `PYTHONPATH=. python3 tools/run_migration.py --core core --ops ops --only NNNN --commit`
  (dry-run first by omitting `--commit`). A live data write needs Joe's explicit yes
  (STANDING_RULINGS STOP-AND-ASK #2; the auto-mode classifier enforces it).
- **Specs** `specs/*/requirements.md` (632 requirements) + `specs/REQUIREMENTS_INDEX.md`.
- **Decisions** `docs/DECISIONS.md` (ADR index) + `docs/adr/`. **Open questions**
  `docs/OPEN_QUESTIONS.md`. **What's wrong/next** `docs/REMEDIATION_PLAN.md`.
- **Rules of engagement** `CLAUDE.md`, `docs/CONSTITUTION.md`, `docs/STANDING_RULINGS.md`
  (untracked — Joe's durable authorisations), `ops/WORK_QUEUE.md` (untracked — the goal).
- **Progress log** `ops/PROGRESS.md` (newest last). **Session start/end** skills in
  `.claude/skills/`.

## 8. If you are a fresh session picking this up

1. Read `CLAUDE.md`, `docs/CONSTITUTION.md`, `docs/STANDING_RULINGS.md`, `ops/WORK_QUEUE.md`.
2. Run `tools/status.py` and `PYTHONPATH=. python3 tools/check_invariants.py --core core`.
3. **Verify live state before reciting docs** — this project's docs have gone stale (Gate 0
   was reported blocked for a week after it closed). Check the database, not the prose.
4. The goal is capture running, not the roadmap. Build toward §3/§4. Don't fabricate data
   to make anything look done (RULE-01) — the empty state is the honest state until Joe
   captures.
