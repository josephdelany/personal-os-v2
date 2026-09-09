# 06 — NON-FUNCTIONAL (RELIABILITY) — REQUIREMENTS (EARS)

**Status:** PARTIAL — 4 requirements, 0 acceptance scenarios (proven by named tests
and a workflow-file check, ADR-0024, not by Gherkin).
**Scope:** the reliability keepalives that stop the two calendar-clock failures that
would silently end the project — the Supabase Free **7-day inactivity pause** and the
GitHub Actions **60-day scheduled-workflow disable** — and the `ops.runs` evidence that
proves a keepalive fired. This is the `REQ-NFR` half of OQ-16 (previously a dangling
prefix cited by F-014/F-015).
**Blocking:** nothing, since 2026-08-31 — the repository is pushed (OQ-02), the
`SUPABASE_DB_URL` Actions secret is set, and unattended scheduled firings are verified in
`ops.runs` (Gate 0 CLOSED). REQ-NFR-001/002 are proven as mechanism (named tests) and as
a scheduled event (`trigger=schedule` rows). See N-Q1 below.
**Grammar:** EARS (Mavin & Wilkinson). SHALL is binding. SHOULD is not used.
**ID scheme:** `REQ-NFR-nnn` (non-functional — reliability here; cost and privacy NFRs
already live in `CONSTITUTION.md` §V and RULE-28/RULE-29, and performance budgets are
not yet written).

---

## 0. SYSTEM ACTORS

| Name in requirements | What it is |
|---|---|
| **the Supabase keepalive** | the `--job supabase` path of `ops/keepalive.py`, scheduled by `.github/workflows/keepalive.yml`. |
| **the GitHub Actions keepalive** | the `--job github` path of `ops/keepalive.py` plus the heartbeat-commit step of the same workflow. |
| **a keepalive job** | either keepalive above, at the moment it executes. |
| **the runs table** | `ops.runs` (migration `0011`), the heartbeat every job writes to. |

**Governing idea (ADR-0024):** the keepalive's proof-of-life is a genuine operational
row in `ops.runs` recording that a job *did run at time T*. That is a true operational
fact, not fabricated data (RULE-01) — it writes **zero** data rows.

---

## A. SURVIVING THE TWO CLOCKS

**REQ-NFR-001** (Ubiquitous) The Supabase keepalive SHALL run on a schedule whose
maximum period between runs is 3 days, so that an authenticated database write always
reaches the project inside its 7-day inactivity window and the project is never paused.

**REQ-NFR-002** (Ubiquitous) The GitHub Actions keepalive SHALL check repository
staleness at least once every 3 days and SHALL make a repository commit whenever the
most recent commit is older than 50 days, so that the repository is never more than 53
days without a commit and its scheduled workflows are never disabled at GitHub's 60-day
inactivity limit.

## B. EVIDENCE THAT A KEEPALIVE FIRED

**REQ-NFR-003** (Event-driven) WHEN a keepalive job runs, the keepalive SHALL write
exactly one row to the runs table carrying its `job_name`, `started_at`, `finished_at`,
and a terminal `status`, so that whether a keepalive fired on schedule is answerable
from stored data rather than from assertion.

**REQ-NFR-004** (Unwanted behaviour) IF a keepalive job fails, THEN the keepalive SHALL
record its runs-table row with `status` set to `error` when the database is reachable,
SHALL exit with a non-zero status in every failure case, and SHALL NOT report success,
so that a keepalive failure is visible rather than silent — as a stored row when it can
be, and as a failed run when the database itself is unreachable.

## C. FEED FRESHNESS — KNOWING A SOURCE HAS GONE QUIET

**Why this section exists.** On 2026-07-28 device-side capture stopped. `public.intraday`,
`chrome_visit`/`youtube_watch` and the location feed all went silent within two days of each
other and stayed silent for 43 days. Throughout, every scheduled job kept running and kept
writing `status = 'ok'` rows, because the jobs were alive and only their *inputs* were dead.
Section B proves a job fired. It cannot prove anything arrived. That distinction is the whole
of this section, and 43 days of unrecoverable sleep, HRV and vitals is what it cost.

**REQ-NFR-005** (Ubiquitous) The freshness checker SHALL derive each registered metric's
staleness limit from its `max_staleness_days` value in the metric registry, so that the
limit is stored configuration rather than a threshold written into code.

**REQ-NFR-006** (Ubiquitous) The freshness checker SHALL classify every registered metric
carrying a staleness limit as `fresh`, `stale` or `never_seen` by comparing the most recent
subject day on which an observation of that metric exists against the check clock, so that a
source that has gone quiet is distinguished from one that has never reported.

**REQ-NFR-007** (Unwanted behaviour) IF a registered metric's most recent observation is
older than its staleness limit, THEN the freshness checker SHALL report that metric as
`stale` carrying its last observed day and its elapsed days, and SHALL exit with a non-zero
status, so that a quiet source fails a scheduled run rather than passing it.

**REQ-NFR-008** (Ubiquitous) The freshness checker SHALL write exactly one row to the runs
table per execution carrying the counts of fresh, stale and never-seen metrics, so that the
freshness history is answerable from stored data rather than from a log that scrolls away.

**REQ-NFR-009** (Unwanted behaviour) IF the freshness checker cannot reach the database,
THEN it SHALL exit with a non-zero status and SHALL NOT report any metric as fresh, so that
an unreachable database is never reported as a healthy one.

**REQ-NFR-010** (Ubiquitous) The freshness checker SHALL treat a metric whose registry row
carries no staleness limit as unmonitored and SHALL report the count of unmonitored metrics,
so that a metric silently escaping monitoring is visible rather than absent.

**REQ-NFR-011** (Unwanted behaviour) IF the freshness checker would report a metric's
observed value, a coordinate, or any payload content, THEN it SHALL instead report only the
metric key, the last observed day and the elapsed day count, so that an operational alert
never becomes an egress path for personal data (RULE-29).

**REQ-NFR-012** (Ubiquitous) The freshness checker SHALL compare against the most recent
`subject_day` carrying an observation rather than against a job's completion time, so that a
job which runs successfully over an empty input is never counted as evidence of freshness.

**REQ-NFR-013** (Unwanted behaviour) IF a registered metric has no observation under its own
key while an observation series exists under a similar key, THEN the freshness checker SHALL
report that metric as `misconfigured` naming the candidate key, and SHALL exit with a non-zero
status, so that a metric which is not being monitored because of a naming mismatch is
distinguished from one whose source has never existed.

**REQ-NFR-014** (Ubiquitous) The freshness checker SHALL NOT treat a similar key as an alias
for a registered metric, so that a decision about whether two differently named series are the
same measurement is never made by a monitoring tool.

---

## NON-GOALS

- **Cost and privacy NFRs.** The $0-recurring rule and the egress posture are already
  binding in `CONSTITUTION.md` §V (RULE-28, RULE-29); they are not restated here.
- ~~**Feed staleness alerting.**~~ **No longer a non-goal — amended 2026-09-09, ADR-0060.**
  It was deferred to Phase 4 as "a different mechanism from keeping the platform itself
  alive", which was correct about the mechanism and wrong about the sequencing: the
  2026-07-28 capture failure went undetected for 43 days precisely because platform
  liveness was the only thing being watched. Detecting that a *data source* has gone quiet
  is now §C above (REQ-NFR-005..012). Gate 4 still owns the *demonstration* — a
  deliberately withheld feed raising an alert inside its limit.
- **Performance and latency budgets.** Not yet written; this file is reliability only.

## ALTERNATIVES CONSIDERED

- **Supabase-side `pg_cron` keepalive as the primary.** Rejected as primary: the
  scheduler that keeps the project alive would live *inside* the project it is keeping
  alive — circular, and it dies with the thing it is meant to save. An external
  heartbeat (GitHub Actions) has no such dependency. Kept available as belt-and-braces
  (ADR-0024).
- **A third-party keepalive Action.** Rejected: it grants a marketplace action a
  write-scoped token on a public, security-conscious repo; the commit-when-stale logic
  is a few lines of inline shell with no added supply-chain surface.
- **A daily heartbeat commit.** Rejected: ~365 commits/year of churn on `main`;
  commit-only-when-older-than-50-days achieves the same 60-day protection with
  near-zero churn.

## UNRESOLVED QUESTIONS

- **N-Q1 — CLOSED 2026-09-02.** Its two conditions (repository pushed, OQ-02;
  `SUPABASE_DB_URL` Actions secret set) were both met by 24 Aug, and the first
  unattended scheduled firings were verified against `ops.runs` on 2026-08-31 (Gate 0
  CLOSED; PROGRESS session 14 addendum). REQ-NFR-001/002 are therefore proven both as
  *mechanism* (the named tests) and as an *on-schedule event* (`trigger=schedule` rows).
  F-014/F-015 no longer need to stay `failing`; the ledger runner (`tools/update_features.py`,
  ADR-0011) flips them on the named tests. The ledger's `proving_test` names the mechanism
  test; the on-schedule evidence lives in `ops.runs`, not in a test.
