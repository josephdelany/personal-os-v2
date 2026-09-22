# ADR-0149 — System recorded time is insertion time, not transaction start

Status: local integrity repair reviewed and integration-tested; deployment held. Date: 2026-09-22.
Rules03/04, ADR0002; prerequisite found through delayed Ask response acceptance.

A rollback-only full-chain regression prepared a question at a server knowledge
cutoff, then inserted another observation before consuming the model response.
The response's maximum became9100 rather than100 even though the new atom was
inserted after the cutoff. Diagnosis: migration0012's force_recorded_at trigger
replaced all supplied timestamps with now(), which is transaction start, so it
backdated the later insert to before the question. This also affects a real writer
whose transaction began before a question and inserts after it.

Migration0079 forces clock_timestamp() at each raw/atom insert instead. Callers
still cannot backdate, and no existing raw or atom row is updated. This preserves
ADR0002's system-learned-time contract and RULE03/04; it changes no measurement or
temporal default. The receipt test's transaction-start equality is replaced by
server-clock bounds around the actual insert; the delayed-response test continues
to require the later atom be excluded. No threshold is relaxed.

Limit: insertion time is not commit visibility time. A different transaction that
inserts before a question but commits afterward still needs snapshot/commit-order
analysis and real two-process evidence (OQ82); this change does not prove that case
or close generic RULE04. Historical rows stamped with transaction start are not
rewritten or claimed repaired. Full review and integration remain required.


Independent read-only review confirms preservation of server forcing and append-only
invariants. Focused combined SQL54 passed (18.11s), including late-insert exclusion.
Reviewer flagged existing current-time APIs defaulting known_at to now(); check or
repair those wrappers before full integration because transaction-start cutoffs can
hide inserts stamped later in that same transaction. No global completion claim.


The related current-read issue is repaired in the same forward migration. The
existing installed Ask, daily-panel, provenance, domain-status and search owners
replace transaction-start now() with statement_timestamp() for current defaults.
An explicit p_known_at remains unchanged. The migration names each exact signature,
requires it and its prior clock expression to exist, and reuses pg_get_functiondef
so no parallel copy of Ask can drift. CREATE OR REPLACE preserves existing grants.
Current wrappers now use one stable query clock, while INSERT uses actual row time.

The targeted path checks current Ask/panel/domain/provenance include a later row
while the stored earlier job excludes it; search's reported current cutoff is
bracketed by a server clock. This does not establish historical filtering for every
legacy measured search lane: _search_measured uses atoms_current and legacy tables
without p_known_at; that separate existing replay gap remains for M2/M6 audit.

Final integration:54 focused SQL passed (17.58s),871 full SQL passed/1 skipped,
78 migrations/689 statements from empty,43 layout checks. Current-read assertions
and frozen-question exclusion both pass. Independent review found no new blocker.
The historical and commit-visibility limits above remain open.
