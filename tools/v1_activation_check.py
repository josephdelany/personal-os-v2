#!/usr/bin/env python3
"""Which numbered migrations does the target database appear to be missing? (ADR-0173)

    python3 -m tools.v1_activation_check            # production, read-only catalog queries
    python3 -m tools.v1_activation_check --json

run_migration.py has no applied-migration ledger, so this infers state from the catalog.
It replays the chain's CREATE / DROP / RENAME / SET SCHEMA statements to learn which schemas,
tables, views and functions should exist at the end, attributes each surviving object to the
last migration that created or moved it, and asks the catalog which exist. Nothing else is
read: no rows, no personal data. The transaction is READ ONLY and rolled back.

Presence is not correctness. A present object may carry an older definition, and migrations
whose effects are grants/alters only are "unverifiable" here. The plan it prints is a
proposal for review under V0_BACKEND_ACTIVATION, never an authorization to apply.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from tools.run_migration import MIG_DIR, split_statements

IDENT = r'(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)'
QNAME = rf'({IDENT})(?:\s*\.\s*({IDENT}))?'
_COMMENT = re.compile(r"--[^\n]*")

_PATTERNS = [
    ("create", "schema", re.compile(rf"^CREATE\s+SCHEMA\s+(?:IF\s+NOT\s+EXISTS\s+)?({IDENT})", re.I)),
    ("create", "table", re.compile(rf"^CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{QNAME}", re.I)),
    ("create", "view", re.compile(rf"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?{QNAME}", re.I)),
    ("create", "function", re.compile(rf"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+{QNAME}\s*\(", re.I)),
    ("drop", "schema", re.compile(rf"^DROP\s+SCHEMA\s+(?:IF\s+EXISTS\s+)?({IDENT})", re.I)),
    ("drop", "table", re.compile(rf"^DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?{QNAME}", re.I)),
    ("drop", "view", re.compile(rf"^DROP\s+(?:MATERIALIZED\s+)?VIEW\s+(?:IF\s+EXISTS\s+)?{QNAME}", re.I)),
    ("drop", "function", re.compile(rf"^DROP\s+(?:FUNCTION|PROCEDURE)\s+(?:IF\s+EXISTS\s+)?{QNAME}", re.I)),
]
_ALTER = re.compile(rf"^ALTER\s+(TABLE|VIEW|MATERIALIZED\s+VIEW|FUNCTION|PROCEDURE)\s+(?:IF\s+EXISTS\s+)?{QNAME}"
                    rf"(?:\s*\([^)]*\))?\s+(RENAME\s+TO|SET\s+SCHEMA)\s+({IDENT})", re.I)
_KIND = {"table": "table", "view": "view", "materialized view": "view", "function": "function",
         "procedure": "function"}


def _unquote(name):
    return name[1:-1] if name.startswith('"') else name.lower()


def _qualified(first, second, default_schema="public"):
    return (_unquote(first), _unquote(second)) if second else (default_schema, _unquote(first))


def default_rewrite(sql):
    return sql.replace("__CORE__", "core").replace("__OPS__", "ops")


def expected_objects(files, rewrite=default_rewrite):
    """{(kind, schema, name): migration filename} for objects that survive the whole chain."""
    state = {}
    for path in files:
        for statement in split_statements(rewrite(path.read_text())):
            text = _COMMENT.sub("", statement).strip()
            match = _ALTER.match(text)
            if match:
                kind = _KIND[" ".join(match.group(1).lower().split())]
                schema, name = _qualified(match.group(2), match.group(3))
                target = _unquote(match.group(5))
                state.pop((kind, schema, name), None)
                moved = (kind, target, name) if "SCHEMA" in match.group(4).upper() else (kind, schema, target)
                state[moved] = path.name
                continue
            for action, kind, pattern in _PATTERNS:
                match = pattern.match(text)
                if not match:
                    continue
                key = ("schema", _unquote(match.group(1)), "") if kind == "schema" \
                    else (kind, *_qualified(match.group(1), match.group(2)))
                if action == "create":
                    state[key] = path.name
                elif kind == "schema":
                    state = {k: v for k, v in state.items() if k[1] != key[1]}
                else:
                    state.pop(key, None)
                break
    return state


def present(cur, objects):
    """Catalog lookup only. Returns the subset of object keys that exist."""
    found = set()
    for key in objects:
        kind, schema, name = key
        if kind == "schema":
            cur.execute("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=%s)", (schema,))
        elif kind == "function":
            cur.execute("""SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                           WHERE n.nspname=%s AND p.proname=%s)""", (schema, name))
        else:
            cur.execute("""SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                           WHERE n.nspname=%s AND c.relname=%s AND c.relkind IN ('r','p','v','m'))""", (schema, name))
        if cur.fetchone()[0]:
            found.add(key)
    return found


def plan(files, objects, found):
    """Per-migration status and the proposed ordered apply list."""
    rows = []
    for path in files:
        mine = [k for k, owner in objects.items() if owner == path.name]
        have = sum(1 for k in mine if k in found)
        status = ("unverifiable" if not mine else "present" if have == len(mine)
                  else "missing" if have == 0 else "partial")
        rows.append({"migration": path.name, "status": status, "objects": len(mine), "found": have,
                     "absent": sorted(".".join(p for p in k[1:] if p) + f" ({k[0]})" for k in mine if k not in found)})
    first = next((i for i, r in enumerate(rows) if r["status"] in ("missing", "partial")), None)
    proposed = [] if first is None else [r["migration"] for r in rows[first:]]
    later_present = [] if first is None else [r["migration"] for r in rows[first + 1:] if r["status"] == "present"]
    partial = [r["migration"] for r in rows if r["status"] == "partial"]
    return {"migrations": rows, "proposed_apply": proposed,
            "needs_manual_review": {"partial": partial, "present_after_first_gap": later_present}}


def run(cur, files=None, rewrite=default_rewrite):
    files = files or sorted(MIG_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    objects = expected_objects(files, rewrite)
    return plan(files, objects, present(cur, objects))


def report(result):
    lines = []
    counts = {}
    for row in result["migrations"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        if row["status"] != "present":
            lines.append(f"  {row['status']:<12} {row['migration']}  ({row['found']}/{row['objects']} objects)")
            lines.extend(f"      absent: {a}" for a in row["absent"][:8])
    head = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    out = [f"Migrations: {head}"] + lines
    if result["proposed_apply"]:
        out.append("\nProposed apply order (review first; dry run each with run_migration.py before --commit):")
        out += [f"  {m}" for m in result["proposed_apply"]]
    else:
        out.append("\nNo missing or partial migrations detected by object presence.")
    review = result["needs_manual_review"]
    if review["partial"] or review["present_after_first_gap"]:
        out.append(f"\nMANUAL REVIEW: partial={review['partial']} present_after_gap={review['present_after_first_gap']}")
    out.append("Presence is not definition correctness; run ops/preflight/v0_backend.sql for fingerprints and grants.")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    from lib import db
    conn = db.connect()
    try:
        cur = conn.cursor()
        cur.execute("SET TRANSACTION READ ONLY")
        result = run(cur)
    finally:
        conn.rollback()
        conn.close()
    print(json.dumps(result, indent=2) if args.json else report(result))
    return 1 if result["needs_manual_review"]["partial"] else 0


if __name__ == "__main__":
    sys.exit(main())
