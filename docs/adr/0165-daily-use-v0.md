# ADR-0165 — Daily-use V0 before complete backend

Date: 2026-09-24. Status: accepted delivery scope, explicitly requested by Joe.

Joe wants a useful limited program while development continues. Complete the
current correction change, then focus exclusively on Today, Add and History and
the daily flows/release bar in EXECUTION_PLAN. This supersedes the latest
complete-backend-first sequencing; it does not discard the full project backlog.

Make phone usability, visual hierarchy and calm aesthetics part of V0. Show saved
state separately from processing and distinguish missing, stale and pending data
from zero or verified results. Provide simple capture, supported financial import,
existing health/activity and visits, check-ins and day history with corrections.
Defer inference, recommendations, correlations, elaborate dashboards and perfect
automation. Keep privacy, access control, immutable evidence and idempotent writes.

Joe explicitly approved morning sleep quality/energy and evening mood/energy,
each on a1–10 scale, with optional notes. These are subjective reports; no
clinical interpretation or composite score is authorized. Delivery scope is not permission to invent them, bypass capture
rules, deploy or mutate production. Prepare reviewable changes before requesting
any still-required authorization. Verify one complete day on Joe's real account;
local passing tests or attractive fixture screens cannot establish that outcome.

New 1–10 check-ins require distinct versioned measurement definitions; historical
0–10 observations must not be relabeled or silently combined with them.

Failure mode: a reduced release could become a misleading demo or another sprawling
backend project. EXECUTION_PLAN therefore owns a fixed daily-use acceptance bar;
NEXT_SESSION records one active unit and evidence. Do not treat complete-backend
requirements as V0 blockers unless this daily path depends on them. Do not call
V0 completion completion of the full project.
