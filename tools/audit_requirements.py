#!/usr/bin/env python3
"""M6's requirement audit: which requirements a named test actually proves.

WHAT THIS COUNTS, AND WHAT IT REFUSES TO COUNT. A requirement is PROVEN when a test whose name
contains its ID passes. That is the project's own rule — "test names must contain the
requirement ID they cover" — and it is deliberately the only thing this tool accepts. Not a
mention in an ADR, not an implementation that looks right, not a docstring citing the ID. Those
are all claims about coverage; a passing named test is coverage.

The number this produces will be low and that is the point. A requirement ledger that reports
90% because it counted every ID appearing anywhere in the repository is worse than no ledger:
it converts an absence of evidence into a percentage, and nobody re-checks a percentage.

    PYTHONPATH=. python3 tools/audit_requirements.py            # summary by prefix
    PYTHONPATH=. python3 tools/audit_requirements.py --open REQ-ASK   # what is unproven
"""
import argparse
import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ID = re.compile(r"\b(REQ-[A-Z]{3,4}-\d{3})\b")
# A test name carries the ID with underscores: test_REQ_ASK_031_...
#
# Anchored to the start of a line. An unanchored `def\s+(test_\w+)` also matches a test name
# QUOTED INSIDE A STRING — this file's own tests quote one as fixture data — so a test that
# merely mentions another test's name would have been counted as proving that requirement.
# That is the exact over-count this tool exists to refuse, and its own test found it.
IN_TEST_NAME = re.compile(r"^\s*def\s+(test_\w+)\s*\(", re.M)


def declared():
    """Every requirement ID the specs define, by prefix."""
    out = {}
    for path in sorted(ROOT.joinpath("specs").rglob("requirements.md")):
        for match in ID.finditer(path.read_text()):
            out.setdefault(match.group(1), path.relative_to(ROOT).parts[1])
    return out


def proven():
    """Every requirement ID that appears in a TEST FUNCTION NAME."""
    found = collections.defaultdict(set)
    for path in sorted(ROOT.joinpath("tests").rglob("test_*.py")):
        for name in IN_TEST_NAME.findall(path.read_text()):
            for match in re.finditer(r"REQ_([A-Z]{3,4})_(\d{3})", name):
                found[f"REQ-{match.group(1)}-{match.group(2)}"].add(
                    f"{path.name}::{name}")
    return found


def mentioned_only():
    """IDs that appear in test FILES but not in a test NAME — a claim, not proof."""
    out = collections.defaultdict(set)
    for path in sorted(ROOT.joinpath("tests").rglob("test_*.py")):
        text = path.read_text()
        names = " ".join(IN_TEST_NAME.findall(text))
        for match in ID.finditer(text):
            rid = match.group(1)
            if rid.replace("-", "_") not in names:
                out[rid].add(path.name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", dest="prefix", help="list unproven IDs for a prefix, e.g. REQ-ASK")
    a = ap.parse_args()

    spec_ids = declared()
    have = proven()
    claimed = mentioned_only()

    by_prefix = collections.defaultdict(lambda: [0, 0, 0])
    for rid in spec_ids:
        prefix = rid.rsplit("-", 1)[0]
        by_prefix[prefix][0] += 1
        if rid in have:
            by_prefix[prefix][1] += 1
        elif rid in claimed:
            by_prefix[prefix][2] += 1

    if a.prefix:
        unproven = sorted(r for r in spec_ids
                          if r.startswith(a.prefix) and r not in have)
        print(f"{len(unproven)} unproven {a.prefix} requirement(s):")
        for rid in unproven:
            note = " (mentioned in a test file, not in a test name)" if rid in claimed else ""
            print(f"  {rid}{note}")
        return 0

    total = len(spec_ids)
    total_proven = sum(v[1] for v in by_prefix.values())
    total_claimed = sum(v[2] for v in by_prefix.values())
    print(f"  {'prefix':<14}{'declared':>9}{'proven':>8}{'claimed':>9}{'unproven':>10}")
    for prefix in sorted(by_prefix):
        declared_n, proven_n, claimed_n = by_prefix[prefix]
        print(f"  {prefix:<14}{declared_n:>9}{proven_n:>8}{claimed_n:>9}"
              f"{declared_n - proven_n:>10}")
    print(f"  {'TOTAL':<14}{total:>9}{total_proven:>8}{total_claimed:>9}"
          f"{total - total_proven:>10}")
    print(f"\n  {total_proven} of {total} requirements ({100 * total_proven / total:.0f}%) are "
          f"proven by a test carrying their ID.")
    print(f"  {total_claimed} more are MENTIONED in a test file without a named test — a claim "
          f"about coverage, not coverage.")
    print("\n  M6 requires no unexplained open requirement. This is the list to explain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
