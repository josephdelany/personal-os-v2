"""File-drop importers (B13, ADR-0057).

Each importer is a pure parser: it takes a path and yields `AtomSpec` records. It never
opens a database connection and never writes. `tools/import_drop.py` owns the transaction,
the raw_captures row and the dedupe. That split is what lets the parsers be tested against
generated fixtures with no database at all (RULE-01: fixtures are synthetic, never Joe's
data, and never touch a real table).
"""
