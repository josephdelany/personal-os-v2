#!/usr/bin/env python3
"""What ran, against which source, in which environment — recorded at the moment it ran.

WHY THIS EXISTS. `tools/audit_requirements.py` answers "did a named test run and pass?" and
`tools/evidence_report.py` adds "is what it imports reachable from an entry point?". Both read a
pytest JUnit report. Neither records anything about the RUN that produced that report, and
`audit_requirements.environment()` says so in its own docstring: its flags "describe THIS
process; they are not evidence about the run that produced the result file".

That left the evidence unreproducible in three specific ways, each of which had already bitten:

*The tree was not recorded.* The checkpoint's caveat "it started against a dirty tree" is the
only surviving trace of one live run. `dirty: true` is not enough — a tree is dirty in some
particular way, and without the file list the run cannot be reconstructed or dismissed.

*The database mode was not recorded.* The same test name means different things against the
disposable PostgreSQL 17 server and against production. OQ-78's 38 `57014` timeouts and the
green disposable run are both "test_derive_visits", and only the mode distinguishes them.

*The timezone was not recorded.* `test_resolve_watches` counted 46 paired days in EDT and 45 in
UTC. A result file carries a hostname and a timestamp; neither tells you that.

WHAT THIS TOOL WILL NOT DO.

*It will not report requirement coverage.* Two tools already do, and a third number that nobody
re-derives is how "685 of 685" survived two reviews. This records provenance; `evidence_report`
consumes the same JUnit file and owns the counting.

*It will not promote a run to a deployment.* The `stages` block states outright that a passing
suite establishes `tested` and says nothing about `deployed` or `observed`. Those come from a
declared reference, never from a green tick.

*It will not record a credential.* `SUPABASE_DB_URL` is reported as the boolean `present` and
the mode name. The value never enters the manifest, and neither does the host.

    PYTHONPATH=. python3 tools/evidence_manifest.py --report /tmp/junit.xml --suite deterministic
    PYTHONPATH=. python3 tools/evidence_manifest.py --report local.xml --suite local-sql \\
        --out ops/evidence/local-sql.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]

# A skip reason starting with this marker asserts "this environment lacks a dependency"
# (tests/conftest.py). Kept in sync deliberately rather than imported: this tool must run
# against a result file without importing the test package that produced it.
MISSING_DEPENDENCY = "MISSING DEPENDENCY:"


def _git(*args, root=ROOT):
    try:
        done = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True,
                              timeout=15)
        return done.stdout.strip() if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


# Artifacts this tool and tools/evidence_report.py write. Changes to these say nothing about
# whether the tested source is reconstructible from the commit.
GENERATED_EVIDENCE = ("ops/evidence/", "docs/EVIDENCE_REPORT.md")


def _is_generated(path):
    return any(path.startswith(prefix) for prefix in GENERATED_EVIDENCE)


def working_tree(root=ROOT):
    """The revision, and exactly how the tree departs from it.

    `dirty: true` alone is unactionable. A reader needs to know whether the difference was a
    stray notebook or the engine under test.
    """
    porcelain = _git("status", "--porcelain", root=root) or ""
    entries = [line for line in porcelain.splitlines() if line.strip()]
    # `_git` strips its output, which removes the leading space from the FIRST porcelain line
    # only, so a fixed e[3:] slice silently ate a character off exactly one path per run --
    # "docs/EVIDENCE_REPORT.md" arrived as "ocs/EVIDENCE_REPORT.md" and then matched no prefix.
    # Two-character status, then the path, tolerating either form.
    changed = [{"status": e[:2].strip(), "path": e[2:].lstrip()} for e in entries]
    # Writing this manifest dirties the tree for the next one, and the evidence report dirties
    # it for both. That is not the question anybody is asking: "was the SOURCE under test
    # modified?" must not be answered "yes, because the report about it was written". Generated
    # evidence is therefore counted separately rather than folded into `dirty`.
    generated = [c for c in changed if _is_generated(c["path"])]
    source = [c for c in changed if not _is_generated(c["path"])]
    head = _git("rev-parse", "HEAD", root=root)
    return {
        "head": head,
        "short": (head or "")[:7] or None,
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD", root=root),
        # `dirty` means the SOURCE departs from the commit -- the thing that makes a run
        # unreproducible. Uncommitted generated evidence does not.
        "dirty": bool(source),
        "changed_files": source,
        "generated_evidence_uncommitted": generated,
        "describe": _git("describe", "--always", "--dirty", root=root),
    }


def database_mode():
    """Which database the suite could reach. Never the URL, never the host.

    The same test name proves a different thing in each mode, so a result file without this is
    ambiguous about the one thing OQ-78 turned on.
    """
    socket = os.environ.get("PERSONAL_OS_TEST_SOCKET")
    live = bool(os.environ.get("SUPABASE_DB_URL"))
    if socket:
        mode = "disposable"          # local PostgreSQL 17, ADR-0082
    elif live:
        mode = "live"                # production; schema-building tests are guarded off it
    else:
        mode = "none"                # SQL-backed tests skip, and say so
    return {"mode": mode, "disposable_socket_present": bool(socket),
            "supabase_url_present": live}


def environment():
    """The interpreter, the platform, the clock, and the dependency gate."""
    versions = {}
    for module in ("numpy", "scipy", "statsmodels", "networkx", "jax", "numpyro", "pg8000",
                   "yaml", "ofxtools", "dateparser", "pytest"):
        try:
            versions[module] = getattr(__import__(module), "__version__", "present")
        except Exception:                    # noqa: BLE001 — any import failure is absence
            versions[module] = None
    return {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "machine": platform.machine(),
        # Recorded because test_resolve_watches gave a different answer in EDT than in UTC.
        "timezone": {"tz_env": os.environ.get("TZ"), "local": time.tzname[0]},
        "require_deps": os.environ.get("PERSONAL_OS_REQUIRE_DEPS") == "1",
        "production_checks_enabled": os.environ.get("PERSONAL_OS_PRODUCTION_CHECKS") == "1",
        "dependency_versions": versions,
    }


def _recorded_properties(suites):
    """The run's own environment, stamped into the report by tests/conftest.py.

    This is the authoritative record: it was written by the process that ran the tests. What
    `environment()` collects below describes whichever process builds the manifest, which may
    be a different interpreter, a different timezone and a different dependency gate.
    """
    props = {}
    for suite in suites:
        for node in suite.iter("property"):
            name = node.get("name") or ""
            if name.startswith("personal_os_"):
                props[name[len("personal_os_"):]] = node.get("value")
    return props


def read_junit(path):
    """Counts, durations, and every non-passing case — with skips split by what caused them."""
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    duration = 0.0
    failures, errors, dependency_skips, other_skips = [], [], [], []
    for suite in suites:
        for key in counts:
            counts[key] += int(suite.get(key, 0) or 0)
        duration += float(suite.get("time", 0) or 0)
        for case in suite.iter("testcase"):
            name = f"{case.get('classname', '')}::{case.get('name', '')}".lstrip(":")
            for child in case:
                if child.tag == "failure":
                    failures.append({"test": name, "message": (child.get("message") or "")[:300]})
                elif child.tag == "error":
                    errors.append({"test": name, "message": (child.get("message") or "")[:300]})
                elif child.tag == "skipped":
                    reason = child.get("message") or ""
                    entry = {"test": name, "reason": reason[:300]}
                    # A missing library is a hole in the evidence. Absent data is a true
                    # statement about the world — no package installs a row.
                    (dependency_skips if reason.startswith(MISSING_DEPENDENCY)
                     else other_skips).append(entry)
    counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    return {
        "counts": counts,
        "duration_seconds": round(duration, 2),
        "run_environment": _recorded_properties(suites),
        "failures": failures,
        "errors": errors,
        "skips": {
            "dependency": dependency_skips,
            "environment_or_data": other_skips,
            "dependency_count": len(dependency_skips),
            "environment_or_data_count": len(other_skips),
        },
    }


def build(reports, suite, root=ROOT):
    runs = []
    for path in reports:
        p = pathlib.Path(path)
        if not p.exists():
            raise SystemExit(f"no result file at {p}: run pytest with --junitxml first")
        runs.append({"report": p.name, "report_path": str(p), **read_junit(p)})
    total = {k: sum(r["counts"].get(k, 0) for r in runs)
             for k in ("tests", "passed", "failures", "errors", "skipped")}
    return {
        "schema": "personal-os/evidence-manifest/1",
        "suite": suite,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "working_tree": working_tree(root),
        # Named to say whose environment it is. The run's own is under runs[].run_environment.
        "manifest_process": {**database_mode(), **environment()},
        "runs": runs,
        "totals": total,
        # Task 5's separation, stated in the artifact rather than left to the reader. A green
        # suite is evidence for exactly one of these.
        "stages": {
            "tested": "established by this manifest, for the revision and mode recorded above",
            "behavioural_scope": "see tools/evidence_report.py — a passing name is not a "
                                 "demonstrated requirement",
            "runtime_integration": "see tools/evidence_report.py reachability — an import edge "
                                   "is a static fact about source text",
            "deployed": "NOT established here; requires a migration applied to production",
            "observed": "NOT established here; requires verification against real production data",
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Record how a test run was produced.")
    ap.add_argument("--report", action="append", default=[], metavar="XML", required=True,
                    help="a pytest --junitxml report; repeat for several runs")
    ap.add_argument("--suite", required=True,
                    help="which suite this is, e.g. deterministic | local-sql | live")
    ap.add_argument("--out", default=None,
                    help="write here (default: ops/evidence/<suite>.json)")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args(argv)

    manifest = build(args.report, args.suite, root=pathlib.Path(args.root))
    out = pathlib.Path(args.out) if args.out else ROOT / "ops" / "evidence" / f"{args.suite}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    t = manifest["totals"]
    tree = manifest["working_tree"]
    print(f"{out}: {t['passed']} passed, {t['failures']} failed, {t['errors']} errors, "
          f"{t['skipped']} skipped")
    print(f"  revision {tree['short']} ({tree['branch']})"
          f"{' DIRTY — ' + str(len(tree['changed_files'])) + ' source files' if tree['dirty'] else ' (source clean)'}")
    for run in manifest["runs"]:
        env = run["run_environment"]
        if env:
            print(f"  {run['report']}: database {env.get('database_mode', '?')}, "
                  f"require_deps={env.get('require_deps', '?')}, tz={env.get('tz', '?')}, "
                  f"python={env.get('python', '?')}")
        else:
            print(f"  {run['report']}: no recorded run environment — this report predates "
                  f"tests/conftest.py stamping it; the manifest describes only the tree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
