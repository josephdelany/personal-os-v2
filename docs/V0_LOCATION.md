# V0 visits: collection, processing and recovery

Local backend implementation; production and phone acceptance remain pending.
Use the already-approved Overland path. Coordinates stay in the restricted store;
the owner interface receives labels, observation times, coverage and trace IDs.

## Prepared activation

Apply the reviewed migration chain through0096 only after production authorization.
The selected edge receiver is `supabase/functions/location-ingest/index.ts`.
Check its deployed revision and token configuration before relying on it. Keep the
token in normal secret configuration and the phone's Access Token field; do not
put it in a URL, chat, source file or log. The unused anonymous direct SQL location
writer is disabled by0096. The service-role batch RPC remains the edge's path.

In Overland, use the configured location-ingest endpoint, the matching access token,
All Data logging and a batch size at most1000. Keep the default explicit JSON
acknowledgement behavior; a failed response must leave the queue available for
retry. Optional current/trip envelope fields are outside this V0 point-ingestion
path. Select the approved background tracking settings and verify actual delivery
on the phone; local SQL tests cannot prove permissions, battery use or transport.

The first visit refresh rebuilds existing restricted fixes so older history also
gets traceable source IDs. Later refreshes include newly received older batches
as well as recent data. This does not import archived or legacy public location
history. The prepared hourly extract workflow calls `public.refresh_v0_visits()`
through the private SQL runner and records the existing derive_visits job status.
Publish/activate that workflow only after its SQL dependency is installed.

## Owner response

Use the signed-in owner's normal Supabase RPC client, with POST:

- `get_v0_visits(p_day)` returns the selected04:00 America/New_York window, including
  correct DST boundaries, and whole visits overlapping it. Each visit keeps its
  original source_subject_day, first/last observation times, stored observed span,
  source capture IDs, method/version, derived time and received time.
- `get_v0_day(p_day)` composes visits, per-account imported card activity, health,
  check-ins, meals and workouts. Card dates are the source's calendar dates; they
  do not pretend to have swipe timestamps or04:00 subject-day precision.

The observed span is the interval between the first and last contributing fixes.
It is not proof of uninterrupted presence or an inferred actual departure time.
Place labels are human assignments, provisional matches to registered places,
or unknown. No nearest-place guess or behavioral interpretation is added.

Processing states:

| State | Meaning |
|---|---|
| missing | No fixes or derived visits in this window; presence is unknown |
| awaiting_derivation | Evidence is saved but the visit refresh is not current |
| no_detected_visits | Refresh ran; available samples did not establish a qualifying visit |
| available | Current derived visits are available, with provisional method and coverage |

Received time and observation time are separate. A newly uploaded old batch is
not a recent observation. Fix counts include received samples; low-quality samples
can be excluded from visit derivation. No detected visit is not proof of absence.

## Retry and correction recovery

An exact record replay, a reordered batch, or a changed batch-count property reuses
its saved capture ID. Different source evidence stays distinct. The first source
feature remains immutable; retrying does not edit it. A malformed point rolls back
the whole batch, so the phone must retain it for correction/retry. Pre0096 imports
did not retain these receipts; historical transport deduplication is not claimed.

If a late sample would merge visits with conflicting human labels, refresh refuses
and retains both prior assignments. The derive_visits job reports failure and
the owner read remains awaiting_derivation. Review those assignments and use the
existing owner-only `assign_place` correction, then retry refresh. The backend
never chooses which human label to discard.

## Remaining real-account proof

Verify a real phone upload, successful receipt, safe resend, received timestamp,
hourly visit refresh, current day/history read and owner-only access. Check a
recoverable offline upload and an existing human label through refresh. Confirm
that no coordinate appears in a response or log. Record deployed revisions and
these observed results separately from local test results. These checks are still
open; frontend construction follows the V0 backend handoff.
