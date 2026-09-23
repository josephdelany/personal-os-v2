# ADR-0156 — Append reference refreshes without replacing earlier evidence

Status: implemented and tested locally, not deployed. REQ-NUT-008; INV-1/3; RULE-10.

Branded/Open Food Facts rows older than365 days must be fetched again. Updating a
foods_cache row would change the evidence behind earlier food_id references.
Migration0086 instead admits versions distinguished by fetched_at. The existing
nutrition owner serializes publication by food identity and appends a refresh only
when the newest version is expired and the received timestamp is newer. Ordinary
insert callers retain their no-replacement behavior. Private receipt consumption
uses the database receipt clock for freshness, not the source worker clock.

Current lookup excludes expired Branded/OFF rows, picks the newest matching version
within existing source/correction precedence, and follows an alias's food identity
across versions. Old rows/IDs and alias evidence stay intact. Foundation and Joe
entries do not expire. A failed refresh stays missing/pending; it cannot silently
fall back to stale nutrients. Automatic source order and supervisor remain separate
required parts of the same capture path, not deferrals.

No dependency, service, recurring charge or external call is introduced. Version
retention increases storage; release still requires the existing storage-budget and
operational checks. This decision authorizes no production mutation/deployment.

Scoped validation:143 targeted nutrition/reference tests passed28.46s after the
reviewed READ COMMITTED guard repair. Actual SQL tests reject RR/Serializable
before publication. Concurrent-process proof and full integration remain pending.

Automatic name-search preparation now uses saved outcomes in Foundation→Branded→OFF
order after fresh-cache lookup. A reserved/unconsumed attempt requests reconciliation;
a deferred source remains retryable and cannot become a final no-match. All three
recorded misses allow the resolver to persist no_source_match with review eligibility.
Brand/restaurant evidence and barcode support remain open; this name-only sequence
is not the full REQ-NUT-001/013 contract.

The unresolved-items row is the current review projection. When its tried/reason
changes, a security-definer trigger appends the prior JSON and knowledge timestamp
to immutable unresolved_item_history, then stamps the new projection with database
time. This preserves the operational hold when a later terminal no-match becomes
reviewable. Capture and atom rows are never updated. History is service-readable;
the service can update only the projection's tried field, not forge history rows.

Final local integration at ec2cda2 plus0086 sources:972 SQL passes/1 production-only
skip340.26s;1182 noDB passes/805 skips180.64s;85 migrations865 statements;layout43.
Final scoped review accepted snapshot and persisted-review repairs. Brand/barcode,
complete runtime/process/device and full backend release gates remain open.
