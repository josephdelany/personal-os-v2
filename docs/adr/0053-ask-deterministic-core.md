# ADR-0053 — Ask deterministic core (in progress)

Date: 2026-09-08. Implements B11.1 incrementally; not a release approval.

The executor and grammar/templates live in PostgreSQL. Python must call that
owner rather than compute a second version of an answer. Migration 0049 is still
a draft and has not been applied to production. B11.2 remains unimplemented.

The existing legacy `ask(text)` is preserved. The new overload requires both
`text` and `date`, avoiding ambiguous one-argument calls. A supplied NULL date
uses the existing subject-day convention. Retirement/default arguments wait for
the old-stack cutover.

Calendar windows are inclusive at both ends. “Last N days” includes exactly N
days ending at `as_of`; the default is 90 days. “This week” means the ISO week
starting Monday through `as_of`; “last week” is the preceding complete ISO week.
Months and years use calendar boundaries, including leap days. “Since June”
uses the most recent June on or before `as_of`; an explicit year is honored.
Future, malformed or out-of-calendar ranges return a capability refusal rather
than silently selecting a different period. This convention is a calendar
parser choice, not a change to statistical gates.

Metric identity comes only from `core.metric_registry` (REQ-ASK-003).
Domain/display aliases may improve matching but cannot authorize an unregistered
panel column. Suggestions are distinct metrics and display the registry's
canonical name/unit. Existing panel-to-registry naming gaps must be reconciled
explicitly; do not silently widen the registry to make a question answerable.

Formatting uses domain-metric rounding, selecting a hero rule first and then
domain key for deterministic ties, otherwise the registry's positive rounding
step. If neither exists, preserve the computed value. No new two-decimal default.

For the tested descriptive paths, results include their narration metadata,
explicit observation keys and per-numeral computation references. The owner-locked
`get_computation(uuid)` reads the stored plan/result/keys without granting direct
table access. A broken stored template with an untraceable numeral is logged and
its prose refused; this is not the model-narration fallback still owed by B11.2.

## Verification boundaries and remaining work

`python3 tools/test_local_sql.py` executes real PostgreSQL 17 SQL, including the
whole draft Ask migration against focused prerequisite DDL from earlier
migrations, within rolled-back test schemas. It does not install or validate the
entire legacy dependency chain. See ADR-0082 for the test environment.

B11 remains incomplete: the two-metric operations, money/search/entity contracts,
all partial/absent disclosure wording, complete medical-data attachments, immutable
point-in-time replay, execution/write privilege separation, and the language
planner/budget/egress path still require work and acceptance evidence. In
particular `f_daily_panel` currently imposes a subject-day cutoff only, not the
bitemporal cutoff required by REQ-INF-108 or the replay guarantee of REQ-ASK-030.
No passing calendar test proves either of those requirements.
