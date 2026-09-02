#!/usr/bin/env python3
"""
update_features.py — the sanctioned writer of ops/features.json (ADR-0011; DoD item 4;
built under docs/build/B0_update_features.md).

The agent is denied Edit/Write on the ledger at the tool-permission level so it cannot
mark its own work passing. This script is the sanctioned path: it runs the WHOLE
pytest suite, parses the JUnit XML, and flips an entry failing -> passing only when a
test whose classname::name carries the entry's requirement ID genuinely passed.
(The deny is tool-level, as ADR-0011 states — it is a control on the agent's
habits, not a filesystem lock. Nothing else in this repo may write the ledger.)

What it never does (INV-6 / RULE-00):
  - never runs a subset (-x, -k) — the whole suite, always; xfail is strict so an
    unexpected pass is a FAILURE, never evidence;
  - never deletes an entry, never rewords a description, never adds a key;
  - never moves passing -> failing. A requirement that was passing and now has no
    passing test is printed as `REGRESSION F-0xx` and left for a human.

Exit 0 when pytest ran (whatever the tests did). Exit 2 when pytest itself failed
to start or produce a parseable report (interpreter missing, usage/internal error,
interrupted, truncated XML).

Run:  python3 tools/update_features.py [--strict]
  --strict: exit 1 when any test failed or errored (CI, ADR-0049 (g)); the ledger
            is still written first, exactly as without the flag.
"""
import datetime as _dt
import json
import os
import pathlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
FEATURES = ROOT / "ops" / "features.json"
JUNIT = pathlib.Path("/tmp/features_junit.xml")   # path fixed by B0
# B0's command, plus strict xfail: a non-strict xfail that unexpectedly passes is
# emitted in JUnit as a bare <testcase/> indistinguishable from a real pass
# (reviewer M6). Strict turns it into a <failure>, which is what it is.
PYTEST_CMD = ["python3", "-m", "pytest", "tests/", "-q", "-o", "xfail_strict=true",
              f"--junitxml={JUNIT}"]

# exactly three digits: REQ-NFR-0012 must not prefix-match REQ-NFR-001 (reviewer m3)
REQ_RE = re.compile(r"REQ-[A-Z]+-[0-9]{3}(?![0-9])")
# test names use underscores: REQ_NFR_001 -> REQ-NFR-001
UNDERSCORE_REQ_RE = re.compile(r"REQ_([A-Z]+)_([0-9]{3})(?![0-9])")
# a testcase carrying any of these children did not genuinely pass
NOT_PASSED = ("failure", "error", "skipped", "rerun", "flakyFailure", "flakyError")


def run_pytest():
    """Run the whole suite. Return True if pytest itself ran and left a report."""
    try:
        if JUNIT.exists():
            JUNIT.unlink()                      # never parse a stale report
        proc = subprocess.run(PYTEST_CMD, cwd=ROOT)
    except (FileNotFoundError, PermissionError, KeyboardInterrupt) as e:
        print(f"pytest failed to start: {type(e).__name__}: {e}", file=sys.stderr)
        return False
    # pytest exit codes: 0 all passed, 1 tests failed, 5 none collected — all "ran".
    # 2 interrupted, 3 internal error, 4 usage error, <0 killed by signal — did not.
    if proc.returncode in (2, 3, 4) or proc.returncode < 0 or not JUNIT.exists():
        print(f"pytest failed to start or produce a report (exit {proc.returncode}, "
              f"junit present={JUNIT.exists()})", file=sys.stderr)
        return False
    return True


def parse_junit(junit_path):
    """Return (passed, counts). `passed` is a list of (classname::name, {REQ ids}) for every
    testcase with no failure/error/skipped/rerun child, in document order. `counts` is the
    suite-level tally so the summary can show what was skipped (DoD item 2)."""
    root = ET.parse(junit_path).getroot()
    passed, counts = [], {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for tc in root.iter("testcase"):
        counts["total"] += 1
        if tc.find("failure") is not None:
            counts["failed"] += 1
        elif tc.find("error") is not None:
            counts["errors"] += 1
        elif tc.find("skipped") is not None:
            counts["skipped"] += 1
        elif any(tc.find(tag) is not None for tag in NOT_PASSED):
            counts["failed"] += 1                # rerun attempts are failed attempts
        else:
            counts["passed"] += 1
            full = f"{tc.get('classname', '')}::{tc.get('name', '')}"
            normalised = UNDERSCORE_REQ_RE.sub(r"REQ-\1-\2", full)
            passed.append((full, set(REQ_RE.findall(normalised))))
    return passed, counts


def apply(junit_path, features_path):
    """Flip entries on the evidence in junit_path; write features_path back byte-faithfully
    except for status/proving_test. Returns (doc, counts, regressions)."""
    passed, counts = parse_junit(junit_path)

    # requirement -> first passing test that names it (document order)
    first_test_for = {}
    for full, reqs in passed:
        for r in reqs:
            first_test_for.setdefault(r, full)

    raw = features_path.read_text(encoding="utf-8")
    doc = json.loads(raw)                     # dict preserves key order
    features = doc["features"]
    regressions = []

    for entry in features:
        req = entry.get("requirement")
        if req in first_test_for:
            entry["status"] = "passing"
            entry["proving_test"] = first_test_for[req]
        elif entry.get("status") == "passing":
            # a regression: was passing, now has no passing test. Left for a human (INV-6).
            regressions.append(entry.get("id"))
            print(f"REGRESSION {entry.get('id')} ({req}): previously passing, "
                  f"no passing test names it now")

    # preserve the file's own escaping convention so a description never changes byte-wise
    ascii_only = raw.isascii()
    out = json.dumps(doc, indent=2, ensure_ascii=ascii_only) + "\n"
    tmp = features_path.with_suffix(".json.tmp")
    tmp.write_text(out, encoding="utf-8")
    os.replace(tmp, features_path)             # atomic: never a truncated ledger
    return doc, counts, regressions


def _commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip() or "?"
    except OSError:
        return "?"


def main():
    if not run_pytest():
        return 2
    try:
        doc, counts, _ = apply(JUNIT, FEATURES)
    except ET.ParseError as e:
        print(f"pytest report is not parseable ({e}); ledger untouched", file=sys.stderr)
        return 2

    features = doc["features"]
    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    print(f"pytest: {counts['passed']} passed, {counts['failed']} failed, "
          f"{counts['errors']} errors, {counts['skipped']} skipped of {counts['total']} "
          f"collected — commit {_commit()} at {stamp}")
    widths = (6, 12, 8)
    print(f"{'id':<{widths[0]}} | {'requirement':<{widths[1]}} | {'status':<{widths[2]}} | proving_test")
    print(f"{'-'*widths[0]}-+-{'-'*widths[1]}-+-{'-'*widths[2]}-+-{'-'*40}")
    for e in features:
        print(f"{str(e.get('id')):<{widths[0]}} | {str(e.get('requirement')):<{widths[1]}} | "
              f"{str(e.get('status')):<{widths[2]}} | {e.get('proving_test')}")
    n_pass = sum(1 for e in features if e.get("status") == "passing")
    print(f"{n_pass} passing / {len(features)} total")
    if "--strict" in sys.argv and (counts["failed"] or counts["errors"]):
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted; ledger untouched", file=sys.stderr)
        sys.exit(2)
