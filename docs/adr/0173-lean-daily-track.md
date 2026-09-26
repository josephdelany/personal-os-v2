# ADR-0173 — Lean daily track: use it before building more

Date: 2026-09-25. Status: accepted at Joe's request ("fix the project … if we cannot
[finish the full build], focus on a more basic v1 system for me to use").

## Context

After 40 days: 316 commits, 685 requirements, ~170 ADRs, ~35k lines of tests, a
2,175-line checkpoint, and nothing used on a real day. The honest completion audit
(BACKEND_COMPLETION, 2026-09-10) counted 179/685 implemented; deployed-and-observed
is effectively zero. The full build is months from done, and inference cannot
produce findings until months of real data exist. Collection has not started.

## Decision

1. **The active product is the daily V1**: `app/index.html` (Today, Add, History, Ask)
   over the existing V0 owner RPCs (migrations 0091–0096). The 685-requirement backlog
   is paused, not deleted, and does not block V1.
2. **Activation comes before any new feature.** The next work is: Joe restores the
   database credential, V0 migrations are applied under the existing activation
   packet (V0_BACKEND_ACTIVATION), the page is published, and Joe uses it.
3. **No new backend features until Joe has used V1 on 7 real days.** Then the next
   feature is whatever he actually missed, not the next item in the plan.
4. **Process for this track** (applies the existing Definition of Done; no gate removed):
   - Frontend-only changes: targeted Node tests plus the offline browser smoke tests.
     The full SQL suite and ledger writer run only when a migration or RPC changes
     (the DoD's "backend integration"), and before any production apply.
   - A new ADR is written only for data meaning, measurement, privacy or permission
     changes. UI and routine fixes are recorded in the commit message.
   - NEXT_SESSION is overwritten, not appended, and stays under ~60 lines. History
     lives in Git and `docs/history/`.
   - The reviewer subagent runs before production changes, not after every unit.
5. **Unchanged:** INV-1…6, RULE-00, privacy/egress (RULE-29), permission requirements
   for production writes, and the rule that missing data is never shown as zero.

## Consequences

Work becomes visible to Joe in days instead of months. The risk is that the lean
cadence lets a backend regression through between full runs; the mitigation is that
any migration/RPC change still triggers the full suite, and nothing reaches
production without it. If V1 turns out to be unused after activation, that is a
finding about the product, not a reason to resume the full backlog by default.
