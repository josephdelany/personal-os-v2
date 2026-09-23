# ADR-0157 — Carry verified supplier context into reference resolution

Status: implemented and locally tested for supported explicit clauses; no deployment. REQ-NUT-013/016/025;
REQ-CAP-051/053; RULE-09/10/29.

The exact seven-field food model schema remains unchanged. A shared private owner
reads the immutable transcript used by a saved extraction and its verified name
span. Supported explicit `food from supplier` clauses yield a food query, verbatim
supplier and offset. Reference preparation and private resolution use this same
context; a branded query cannot use Foundation or a generic cache entry. The
resolution JSON stores the context and parser version alongside source provenance.
Only the food query and supplier token leave for the approved reference source.

No fuzzy brand classification or language-model nutrient computation is introduced.
Detected shared or ambiguous supplier clauses refuse instead of dropping the
qualifier. Version 2 also retains possessive supplier qualifiers inside verified
evidence but outside the extracted food name. Personal ownership, negation,
conflicting suffixes, narrowed unverified spans and shared possessive context refuse.
Possessives inside the full food name are not reclassified. General brand prefixes,
full-name disambiguation, more complex clauses and barcode support remain open;
this parser does not claim general brand recognition. Conservative clause checks
can refuse otherwise valid multi-item sentences.
A literal origin phrase can be broader than a commercial supplier; exact source
brand matching is still required and an unmatched phrase stays unresolved.

Current cache matching uses exact source brand-name/brand-owner tokens from retained
raw source metadata while continuing to record the actual brand owner. Multiple
highest-priority product identities refuse instead of selecting an arbitrary row.
Within source precedence, an exact alias chooses its identity; Joe's corrections
remain first. Versions of one identity select the newest fresh version.

When the verified extracted name contains the supplier clause, the request uses
its food query, and publication retains both that query alias and the original
spoken name. Preparation must use the same normalized query on the next poll to
avoid refetching a successfully cached food.

No dependency, service, recurring charge, production permission or new model output
field is added. After the reviewed full-name cache-hit repair,12 pure and152 targeted
SQL tests passed. Full noDB1194 passed/809 skipped146.63s; staged layout43 passed.
Full SQL976 passed/1 production-only skip365.32s, including invariant checks;
generic RULE04 remains pending. Ledger14/15 unchanged. No migration change.
Independent scoped review accepted the query/alias repair; archive
`.local/evidence/capture-brand/` records base d70923a and tested source hashes.
This does not close general supplier recognition, M3 or M6.

Version2 integration after5ea1cd8:22 pure and38 reference SQL tests pass after
review repair of narrowed personal-ownership evidence. Full noDB1295 passed834
skipped174.24s; full SQL1001 passed1 production-only skip339.62s; layout43.
Ledger14/15 unchanged/F006 existing diagnostic; genericRULE04 pending. No migration.
Source hashes and JUnit/logs archived .local/evidence/capture-possessive/. Review
accepted the scoped repair with conservative multi-item refusals noted.
