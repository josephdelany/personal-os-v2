# ADR-0166 — V0 structured check-in backend

Date:2026-09-24. Status: accepted, locally verified; not activated.
Joe’s latest order is V0 backend, then frontend, then the remaining project.
Requirements:CAP014/016/017, RULE01/02/03/06/10/29; V0 daily release contract.

Provide owner-authenticated save/read RPCs for the approved morning sleep-quality
and energy, evening mood and energy, all integer1–10 with optional notes. Store
versioned v0_checkin_v1 captures, separate from legacy0–10 extractor inputs. These
are subjective answers, not clinical interpretation or derived computations.
No inferred scale conversion, synthetic data, analytics or model call is needed.

Client UUIDv7 identifies a complete request. Exact retry returns its saved receipt;
changed contents under that ID refuse. A correction names the current predecessor,
appends a new capture/version and never updates evidence. One successor per version,
serialized saves, stale-target refusal. History returns current entries for the
existing04:00 America/New_York day; both event/received time and prior entry ID are
retained. Read missing days as an empty list. No implicit merging with old scores.

Raw ingress and the version ledger commit together through the RPC transaction.
Only the owner JWT may execute successfully; anon and nonowner users cannot save
or read entries. Direct app access to private ledger is revoked. Structured values
are immediately usable; successful save is independent of nutrition/model processing.

Acceptance: real SQL owner/nonowner permissions, exact/conflicting retry, bad and
missing fields/scales/types, midnight/day boundary, correction/current/history,
append-only mutation refusal and atomic rollback. Disposable rollback-only fixtures.
No production or frontend change is authorized by this ADR. Final review and full
integration required. Other V0 flows remain separate acceptance obligations.


Verification: targeted30pass1.12s; full SQL1105pass1production-only skip436.84s;
feature writer1441pass932skip176.09s; chain90files946statements; layout43pass.
Four scoped spine invariants pass; generic RULE04 remains pending. Merged43 checks
unverified (41production,2NumPyro); ledger14/15 unchanged. Evidence and exact
source hashes at .local/evidence/v0-checkins/. Independent review caught PostgreSQL
clock normalization; strict hours/minutes/seconds validation and rejection cases
fixed it, re-review accepted. Concurrent independent-commit retry and real-account
acceptance are not proven under rollback-only fixtures. These remain limitations,
not passed checks. Other V0 flows and production activation remain open.
