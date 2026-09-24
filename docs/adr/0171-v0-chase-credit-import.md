# ADR-0171 — V0 actual Chase credit export support

Date:2026-09-24. Status: accepted, locally verified; not activated.
Scope: V0 spending (ADR0165), FIN010/014/015/040/042 and deduplication/reconciliation.

## Evidence motivating the work

The reorganized private collection includes a Chase credit export and two checking
exports. File hashes match the index. None matches the currently shipped mappings.
The credit header is Transaction Date, Post Date, Description, Category, Type,
Amount, Memo. A temporary local mapping parses all rows, preserves each signed
amount and the signed total, and produces stable keys on repeat parsing. However,
one pair of full-identical source rows collapses to one dedupe key. The generic
parser also drops Type/Category/Memo. A mapping alone would silently lose source
multiplicity and leave payments/fees/cash advances indistinguishable from purchases.
Private evidence: .local/evidence/v0-bank-preflight/; no database writes occurred.

## Required outcome

Support the verified credit header explicitly, preserving stated transaction and
posting dates, signed amounts, source type/category/description and source identity.
Retain source-row multiplicity without treating a repeated import as new spending.
A pair of identical source rows does not prove two independent purchases; preserve
and disclose the source records rather than silently deleting or assigning identity.
Prove exact-file retry and overlapping exports against stored rows, not parser keys
alone. Preserve source trace and reconcile source/accepted/duplicate/rejected counts
and values. Do not weaken existing institution parsing or redefine old evidence.

Expose recent records through an owner-only read with explicit date/amount/unit,
source classification and event/received timestamps. Separate source-labelled
purchases from payments, fees and cash advances; do not label every debit spending
or every credit income. Source category is not the canonical category vocabulary.
OQ59/61 remain unresolved. No bank connection or credential-based automation.

## Currency evidence and limit

The observed credit export uses the ledger sign convention (sales negative,
payments positive). Chase's public US card agreement states that foreign-currency
transactions are converted to US dollars before the transaction amount is sent
to Chase, and payments are in US dollars:
https://www.chase.com/content/feed/public/creditcards/cma/Chase/COL00058.pdf
(USING YOUR CARD / Foreign Transaction Fee and Exchange Rate, page6;
PAYING US BACK, page8 in the PDF viewer). This supports the proposed US Chase card
USD mapping; it does not authorize a generic currency assumption for other files
or institutions. Use the exact source header and documented account/export scope.

Checking exports have only Posting Date and a different header; this proposal
makes no claim that their occurrence date or transfer semantics are settled.
Keep unsupported formats explicit until their own evidence supports a mapping.

Implementation and independent review must resolve the duplicate identity design
before an actual import. Acceptance requires real-file read-only reconciliation,
rollback-only SQL import/retry/overlap behavior, permission checks and signed
readback. No real-account activation or completed finance contract is claimed.

Independent read-only review recommends a versioned account-scoped file/row ledger,
keeping generic bank imports unchanged. File hash/row ordinal preserve raw identity
but must not become canonical transaction identity across overlapping files. Match
occurrences only where account and export coverage support it; otherwise preserve
ambiguous overlap for explicit review. Preserve full source multiplicity even when
normalization is unresolved. Do not fabricate a universal reliable deduper from
CSV fields that contain no stable transaction identifier.

## V0 staging boundary (reviewed)

Use dedicated source-observation and owner-adjudication tables. These are not the
raw_transactions/canonical transaction tables governed by FIN043–048. Do not call
the pending-to-posted merge routine, create tip deltas or claim canonical finance
completion. Exact bytes/equivalent full source multiset identify import replay;
partial-file identity remains a separate explicit owner review. Persist link and
distinct decisions append-only. Reads are imported card activity; incomplete
subtotals disclose unresolved source observations. This is the approved limited
V0 scope, not an amendment to FIN044 or a renamed canonical transaction engine.
Independent review accepted this distinction; full-project reconciliation remains
unfinished and must not inherit staging decisions as proven canonical identities.

## Parser checkpoint

config/institutions/v0/chase_credit.yaml is isolated from generic importer globbing.
tools/importers/v0_card.py preserves original bytes, source fields and row ordinal;
exact file SHA and full-row multiset SHA retain duplicate multiplicity. Account
identity is an explicit UUID, never guessed from filename. Decimal amounts retain
USD precision, both supplied dates survive even when equal, missing posted date
stays null. Strict header/UTF8/amount/date validation and byte/row/field bounds fail
with recoverable messages that do not disclose transaction contents.

20pure parser tests passed0.69s. Read-only actual-export reconciliation preserves every
row, field, amount and signed total; duplicate pair stays present. Private evidence
.local/evidence/v0-card/actual-parser-reconciliation.json. No database import,
persistence activation or V0 finance completion is claimed by that parser evidence.

## Storage and owner interface

0095 adds immutable private file/row/decision/read ledgers. The trusted Python
writer parses original bytes itself and runs in a caller-owned READ COMMITTED
transaction, serialized with review decisions. Autocommit and stronger snapshot
isolation refuse. Exact account+byte replay returns the original receipt; equivalent
full-row multisets under the same mapping preserve another source file and map
each occurrence to its original row without adding activity. Source files retain
their bytes in raw captures, with import-received capture time; transaction and
posting dates remain date precision. No event timestamp is invented.

Potential partial overlaps (identical source record, or same currency/type/amount
on the same date; up to three days apart with matching merchant text) need owner
review. This is a candidate rule, not proof of identity or comprehensive matching
of arbitrarily changed exports. Identical rows within a file are preserved too.
Unknown source types remain visible. No source Type or Category becomes canonical
income, transfer or category meaning. The writer does not use the canonical merge
engine. Unsupported files fail validation before database writes; the existing
generic quarantine workflow is unchanged and FIN015 is not newly completed.

review_v0_card_row appends an idempotent link/distinct decision with an explicit
predecessor. Distinct preserves the source row's rejected candidate relationships;
new imports cannot reverse that choice. An explicit later owner correction can
supersede it. Links require a currently distinct same-account target; incoming
links must be resolved before their target can itself link, preventing chains.
Equivalent-file aliases must be reviewed through their original observations.

get_v0_card_activity returns an inclusive, at-most-366-day date range, current owner
decisions, original fields, IDs and received timestamps. Its source-type/currency
subtotals include only distinct observations, disclose unresolved IDs, and store
the exact response and contributing IDs with code_version=v0_card_activity_v1.
Missing activity returns no subtotals, never fabricated zero spending. This read
is current-knowledge history, not an as-known-then reconstruction. Source subtotals
are imported card activity, not reconciled spending or income.

tools/import_v0_card.py defaults to local validation. --apply uses the private
configured ETL connection, commits before reporting saved, and returns unconfirmed
on an uncertain commit acknowledgement so the identical file/account can retry.
The CLI does not log source contents or database exceptions. No browser upload or
public import RPC is introduced. No recurring service or dependency is added.

Verification: fullSQL1206passed1production-only skip492.70s; feature writer
1473passed1033skipped202.57s, ledger14/15 unchanged. A subsequent metadata-only
fix added explicit observed lane/imported_statement provenance/sum method/version
to each subtotal, without changing arithmetic, filtering or access. Final targeted
29passed1.18s verifies that delta; independent review accepted it. Full-suite
artifacts identify the pre-metadata source hashes, and final hashes identify the
narrow reviewed delta. Final chain94migrations1004statements; layout43pass.
Four scoped spine invariant cases passed; generic RULE04 remains pending.
Merged43 checks remain unverified (41production,2NumPyro). No broad completion
claim follows from requirement-name reports. Private evidence .local/evidence/v0-card/.
Runbook: docs/V0_CARD_IMPORT.md. Activation, actual-account import, day composition
and independent committed-concurrency/crash proof remain unverified.
