# V0 card import and review

Local implementation; activation and real-account acceptance are still pending.
This path supports the actual **Chase US credit-card activity CSV** header:
Transaction Date, Post Date, Description, Category, Type, Amount, Memo.
Checking exports and automatic bank connections are outside this path.

## Validate and save

Keep the original export in private local storage. Choose one UUID for this card
and reuse it for every export of the same account. It is an internal account
identity, not the card number. Using a new UUID intentionally creates a separate
account; the importer cannot infer that two account identities are the same card.

From the repository root, validation is local and makes no database connection:

```bash
PYTHONPATH=. python3 -m tools.import_v0_card --file "$CARD_EXPORT_PATH" --account "$CARD_ACCOUNT_ID"
```

`validated_not_saved` confirms parsing only. The response reports the mapping and
source-row count. Malformed/unsupported files give an error without dropping rows
or exposing transaction contents. Validation does not create a quarantine receipt.

After reviewed activation, the private ETL environment supplies SUPABASE_DB_URL
through normal secret configuration. It needs the existing privileged import role;
anon, authenticated, capture_ingest and service_role cannot directly access this
new source ledger. Do not give this connection to the frontend.

```bash
PYTHONPATH=. python3 -m tools.import_v0_card --file "$CARD_EXPORT_PATH" --account "$CARD_ACCOUNT_ID" --apply
```

`saved` is printed only after commit. Retain its file_id/account_id receipt.
`unconfirmed` means retry the identical bytes with the same account ID: the commit
may already have succeeded. An exact retry returns the original receipt. A complete
reordered export is preserved as another source file with equivalent-row references,
without additional activity. Overlapping partial exports can require owner review.

## Owner API contract

Call through the normal signed-in Supabase client with the owner's JWT. Neither
the anonymous project key alone nor another user's JWT grants access. The frontend
caller and its sign-in experience belong to the next delivery phase.

`get_v0_card_activity(p_account uuid, p_start date, p_end date)` accepts an inclusive
range of at most 366 calendar dates. Dates are the source's transaction dates,
not invented swipe times or the check-in 04:00 day boundary. It returns:

- Original activity fields, transaction/posting dates, native signed USD amounts,
  source Type/Category, received times, and raw capture/source-row references.
- `distinct`, `needs_review`, or `linked` status with current decision ID and
  candidate IDs. Equivalent-file aliases do not appear as extra activity.
- Stored source-type/currency subtotals with exact included IDs. Unresolved rows
  are listed and excluded. Payments are not income; debits are not all purchases.
- `missing`, `incomplete`, or `imported_observations_only` coverage. No imported
  rows means an empty subtotal list, not zero spending. Exports cannot prove that
  all activity for the requested dates was collected.

`review_v0_card_row(p_request jsonb)` accepts exactly these keys:

```json
{
  "decision_id": "a new UUID retained for retries",
  "row_id": "source observation UUID from activity read",
  "action": "distinct",
  "target_id": null,
  "supersedes": null
}
```

The strings above describe values to substitute, not an executable fixture or
valid UUID request. Use `link` and a target_id to identify the same activity as an
existing **distinct** observation in the same account. Use `distinct` to retain it
as separate activity. On a correction, supersedes is the current decision_id.
Keep the complete request unchanged for retry; a changed request needs a new ID.
A stale predecessor requires reloading the row before deciding again.

Links cannot form chains. Resolve incoming links before changing their target into
a link. A correction appends history; it never edits CSV evidence. Reimports do not
override owner decisions. Reads show current decisions for past transaction dates,
not what was known on that historical day.

## Activation and remaining acceptance

Apply the reviewed migration chain through 0095 to the intended backend only after
production-write authorization. Keep the original CSV and account identity private.
Use an actual export for authorized import/readback, retry, source reconciliation,
owner/nonowner access and a reversible append-only review correction. Verify missing
dates, received freshness, Type separation, unresolved exclusions and saved receipts.
Connect the resulting activity to the V0 day response before backend handoff.

Local disposable tests are not production evidence. Independent commit/crash tests
remain limited by the repository's rollback-only fixture policy. Canonical finance
reconciliation, category/transfer definitions and automated bank connections remain
later project work; this source staging path does not claim those contracts complete.
