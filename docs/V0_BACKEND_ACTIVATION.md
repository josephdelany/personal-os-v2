# V0 backend activation and acceptance

Prepared at local implementation commit d3d4eaa. Status: NOT activated or accepted.
The catalog preflight was executed on a disposable PostgreSQL17 server against
both an empty catalog (0/12 required functions) and the fully migrated schema
(12/12); both passed and the server stopped. This proves the inventory query runs,
not that production matches or all permissions are correct.

This is the current V0 handoff checklist; older CAPTURE_ACTIVATION observations
are dated evidence, not a current production inventory. No deployment is authorized
by this document. Credentials stay in the normal private environment configuration.

## Establish the target before requesting deployment

1. Restore the known-failing database credential through normal secret configuration.
   Do not paste it into chat or rerun unchanged credentials after SQLSTATE28P01.
2. Run `ops/preflight/v0_backend.sql` privately with psql, using its normal connection
   configuration. The script is read-only, reports catalog metadata only, and calls
   no V0 read RPC (some persist their results). Preserve the result privately.
3. Compare installed function definitions and schema to the reviewed migrations;
   existence alone is insufficient. The fingerprint is a comparison aid, not proof
   of migration version or permission correctness. Missing functions are explicit.
4. Inventory deployed edge revisions, the private captures bucket and actual Storage
   policies, scheduled extract revision, and health aggregation registry. Confirm
   owner authentication configuration through its normal admin interface. Never
   expose tokens, personal source rows or coordinates in a deployment report.
5. Produce an exact ordered migration list from that inventory. The existing
   run_migration.py executes supplied files; it has no applied-migration ledger.
   Do not blindly replay the chain or assume0091–0096 are the only missing files.
   The clean-chain test includes legacy prerequisites and is not a production
   recovery or migration-state probe.

## Concrete activation actions to review after inventory

- Apply the missing reviewed dependencies through0096 to the intended existing
  database, with backup/recovery readiness and verification at each boundary.
- Apply supabase/capture_storage_policies.sql before
  supabase/v0_meal_photo_policies.sql; verify captures remains private.
- Activate the matching capture upload/completion transport and approved Shortcut
  helper; verify location-ingest token configuration and its service-only RPC path.
- Publish the reviewed extract workflow only after refresh_v0_visits exists.
  Observe an actual scheduled execution, not just a workflow file or manual run.
- Import the actual supported credit export with one retained account UUID using
  tools.import_v0_card. Archived files are not automatically admitted. Check the
  actual health source/configuration before importing or changing aggregation.

The permission request must identify target, exact files/revisions, ordered actions,
source import and expected verification. This packet still needs live inventory
before it is a deployable request. Do not substitute a blanket deployment approval.

## Backend acceptance evidence, using real owner data

| Contract | Required observed result |
|---|---|
| Owner access | Owner session calls the API; anonymous and nonowner calls refuse; no service key in client |
| Check-ins | Real morning/evening1–10 values save/read; identical retry returns same entry; correction appends and stale correction refuses |
| Meals | Real text and completed private photo save/read; owner downloads image; save remains distinct from pending nutrition |
| Workouts | Real set preserves stated mode/load/unit/reps/RPE; save, same-request retry and correction read back |
| Health | Imported native units, event and received timestamps; actual aggregation and device precedence inspected; missing stays missing |
| Spending | Actual credit CSV receipt, exact retry, source-row reconciliation, explicit ambiguous overlap and owner review; no payments-as-income claim |
| Visits | Phone upload, same-batch resend, offline recovery, hourly refresh and coordinate-free owner read; human labels survive |
| Day/history | Current and prior day compose all available domains; corrected entry appears; empty domains stay visibly missing |

Use genuinely supplied observations only, never invented production smoke entries.
Keep complete requests and IDs privately for retries. A timeout is unconfirmed,
not saved or failed: retry the identical request. If a save succeeded but readback
failed, preserve its receipt and retry the read. Stale corrections require a fresh
read and explicit new correction. Do not delete immutable evidence as cleanup.

Record deployed revision, operation, event/received time, retained receipt identifier,
and observed outcome privately. Record only redacted pass/fail evidence in Git.
Local tests prove contracts under fixtures, not this real-account acceptance.
Frontend work follows this backend handoff; the phone UI and complete-day release
checklist remain separate and are not claimed complete here.

## Executable caller and remaining integration

At d3d4eaa the existing app has sign-in and generic RPC handling but no get_v0 or
save_v0 calls. Runtime documentation contains examples, not a runnable V0 client.
The new app/v0_client.mjs adapter now provides retained request identity,
explicit unconfirmed errors, save receipts independent of readback, and current
entry correction support; see V0_OWNER_CALLER.md. Eight local behavior cases pass
and independent review accepted the recovery fixes. Exercise it against the
authenticated endpoint after activation; injected transports are not HTTP/account
proof. Consumer draft persistence and the three screens remain frontend work.
