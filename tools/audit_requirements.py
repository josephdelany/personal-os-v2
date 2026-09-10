#!/usr/bin/env python3
"""The requirement evidence ladder: what is actually known about each requirement, by level.

This replaces a report that counted a requirement as PROVEN when a test function whose name
contained its ID existed **in a source file**. It never ran the test. A requirement whose only
test is `pytest.skip`ped, whose test was never collected, or whose test fails, was reported as
proven identically to one with a green run behind it — and the summary line rendered the total
as a percentage. A percentage is the one output nobody re-derives, so an absence of evidence
became a number that looked like progress.

WHAT CHANGED. Evidence is a LADDER of six levels, and each is reported separately because they
fail separately and they are not substitutes for one another:

    1 DECLARED     the ID exists in specs/*/requirements.md
    2 MAPPED       at least one test FUNCTION NAME carries the ID
    3 TESTS_PASSED every mapped test was collected AND passed in a named result file
    4 INTEGRATED   an explicit integration-evidence reference exists
    5 DEPLOYED     an explicit deployment-evidence reference exists
    6 OBSERVED     an explicit observation-on-real-data reference exists

The ladder is MONOTONIC: level N is reported only if every level below it holds. That is not
bureaucracy. "Deployed" while the tests are skipped is the exact sentence this tool exists to
make unwriteable.

THE FOUR THINGS THIS REFUSES TO DO.

**A missing result file is not a pass.** With no JUnit report, every requirement sits at level 2
and the header says so. The old tool's answer to "were the tests run?" was to not ask.

**Skipped, errored, uncollected and failed are each not-passed, and worst-case wins.** A
requirement with three mapped tests where one passes and two skip is NOT at level 3. The single
passing test is still shown, with its two skipped siblings beside it, because that is the fact a
reader needs. `REQ-INF-520` is the live case: of its three named tests, the two that execute
NUTS skip wherever NumPyro is absent, and the one that passes asserts on `inspect.getsource`.

**Level 3 is called TESTS_PASSED and never PROVEN or COMPLETE.** A passing mapped test is
evidence about the assertions in that test, not about the requirement's full sentence. A
requirement declaring a five-step cascade is not covered by a test of one branch of step two.
`--requirement` prints the mapped tests by name so the reader can judge that themselves; the
tool does not pretend to.

**Levels 4-6 come only from a declared reference, never from inference.** No import graph, no
"a module mentions it", no "the tests pass so it must be wired". Those are the inferences that
produced the claims under review. With no evidence file the honest answer is UNKNOWN, which is
what is printed — UNKNOWN is a state, not a gap to be filled by a guess.

    PYTHONPATH=. python3 tools/audit_requirements.py --junit /tmp/junit.xml
    PYTHONPATH=. python3 tools/audit_requirements.py --prefix REQ-REC --junit /tmp/junit.xml
    PYTHONPATH=. python3 tools/audit_requirements.py --requirement REQ-INF-520 --junit /tmp/junit.xml

The result file is produced by a normal pytest run with `--junitxml`; `tools/update_features.py`
already writes one to /tmp/features_junit.xml, and this tool reads that format rather than
defining a second one.
"""
from __future__ import annotations

import argparse
import ast
import collections
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Exactly three digits, and not four: REQ-NFR-0012 must not prefix-match REQ-NFR-001.
ID = re.compile(r"\bREQ-[A-Z]{3,4}-\d{3}(?!\d)")
# A test name carries the ID with underscores, and may carry several:
# `test_REQ_ASK_021_022_011_...` names three requirements, not one.
IN_NAME = re.compile(r"REQ_([A-Z]{3,4})_((?:\d{3})(?:_\d{3})*)(?!\d)")
# Test functions are found by PARSING, not by matching text. A regex over source — even one
# anchored to the start of a line — counts `def test_REQ_XYZ_001_...` written inside a
# docstring or a fixture string, because such a line really does start with `def`. This file's
# own tests embed fixture modules as triple-quoted strings, and an earlier regex version of
# this function duly reported their invented IDs as real mapped tests and then as orphans. A
# tool that miscounts its own test suite cannot be trusted to count anything else.
#
# The walk mirrors pytest's collection: module-level `test_*` functions and `test_*` methods of
# a class, and nothing nested inside another function (pytest does not collect those either).

# Level names. Deliberately not "proven" and not "complete".
LEVELS = ("DECLARED", "MAPPED", "TESTS_PASSED", "INTEGRATED", "DEPLOYED", "OBSERVED")

# Worst case wins. A requirement is only TESTS_PASSED when every mapped test passed, so the
# roll-up takes the WORST outcome among them rather than the best or the commonest.
OUTCOME_RANK = {"failed": 0, "error": 1, "not_run": 2, "skipped": 3, "passed": 4}
# JUnit children that mean a testcase did not pass. Same set `tools/update_features.py` uses;
# `rerun`/`flaky*` are retried attempts, and a test that needed one did not cleanly pass.
NOT_PASSED_TAGS = {"failure": "failed", "error": "error", "skipped": "skipped",
                   "rerun": "failed", "flakyFailure": "failed", "flakyError": "error"}

EVIDENCE_KINDS = ("integration", "deployment", "observation")
# Which ladder level each declared evidence kind can unlock.
KIND_LEVEL = {"integration": "INTEGRATED", "deployment": "DEPLOYED", "observation": "OBSERVED"}


# ---------------------------------------------------------------- level 1: declared

def declared_requirements(root=ROOT):
    """{requirement id: spec directory}. The specs are the only source of what exists.

    A requirement absent here but named by a test is an ORPHAN — either a typo in a test name
    or a requirement someone deleted — and it is reported rather than silently dropped, because
    a test that names nothing real is a test whose subject nobody can check.
    """
    out = {}
    specs = pathlib.Path(root) / "specs"
    for path in sorted(specs.rglob("requirements.md")) if specs.is_dir() else ():
        family = path.relative_to(specs).parts[0]
        for match in ID.finditer(path.read_text(errors="ignore")):
            out.setdefault(match.group(0), family)
    return out


# ---------------------------------------------------------------- level 2: mapped

def _test_key(path, root, name):
    """`tests.test_x::test_y` — the same shape JUnit's classname::name produces, so the join
    between source and results is an equality and not a fuzzy match."""
    rel = pathlib.Path(path).resolve().relative_to(pathlib.Path(root).resolve())
    return f"{'.'.join(rel.with_suffix('').parts)}::{name}"


def collected_test_names(source):
    """Every name pytest would collect from this module: `test_*` at module or class level.

    Raises SyntaxError for an unparseable file, which the caller surfaces — a test file that
    does not parse contributes no coverage, and reporting it as "no tests" would hide the fact
    that the file is broken.
    """
    names = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and item.name.startswith("test_"):
                    names.append(item.name)
    return names


def mapped_tests(root=ROOT, unparseable=None):
    """{requirement id: {test key, ...}} from test FUNCTION NAMES only.

    A requirement ID in a docstring, a comment, an assertion message or an ADR is a claim about
    coverage. The project's own rule is that a test name carries the IDs it covers, and that is
    the only thing read here.
    """
    out = collections.defaultdict(set)
    tests = pathlib.Path(root) / "tests"
    for path in sorted(tests.rglob("test_*.py")) if tests.is_dir() else ():
        try:
            names = collected_test_names(path.read_text(errors="ignore"))
        except SyntaxError as e:
            if unparseable is not None:
                unparseable.append(f"{path}: {e}")
            continue
        for name in names:
            for match in IN_NAME.finditer(name):
                for number in match.group(2).split("_"):
                    out[f"REQ-{match.group(1)}-{number}"].add(_test_key(path, root, name))
    return dict(out)


# ---------------------------------------------------------------- level 3: results

class NoResults(Exception):
    """No parseable result file. Level 3 is unknown for everything, and that is reported."""


def parse_junit(path):
    """{test key: outcome} plus the run's own metadata. Outcomes: passed/failed/error/skipped.

    Parametrised cases arrive as `test_x[case]`; the parameter is stripped so every case joins
    to the one source function, and a single skipped case therefore prevents the whole
    requirement reaching level 3. That is the intended direction: a parametrisation that skips
    half its cases has not tested half its cases.
    """
    path = pathlib.Path(path)
    if not path.exists():
        raise NoResults(f"no result file at {path}")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise NoResults(f"result file at {path} is not parseable XML ({e})") from e

    outcomes, counts = {}, collections.Counter()
    for case in root.iter("testcase"):
        classname = case.get("classname") or ""
        name = (case.get("name") or "").split("[", 1)[0]
        key = f"{classname}::{name}"
        outcome, why = "passed", None
        for tag, mapped in NOT_PASSED_TAGS.items():
            found = case.find(tag)
            if found is not None:
                outcome, why = mapped, (found.get("message") or "")[:160]
                break
        counts[outcome] += 1
        # Worst outcome wins across parametrised cases of the same function: a parametrisation
        # that skips half its cases has not tested half its cases.
        if key not in outcomes or OUTCOME_RANK[outcome] < outcomes[key][0]:
            outcomes[key] = (OUTCOME_RANK[outcome], outcome, why)
    outcomes = {k: {"outcome": v[1], "why": v[2]} for k, v in outcomes.items()}

    suite = next(root.iter("testsuite"), root)
    meta = {"junit_path": str(path),
            "timestamp": suite.get("timestamp"), "hostname": suite.get("hostname"),
            "suite_name": suite.get("name"), "suite_time_s": suite.get("time"),
            "counts": dict(counts), "n_testcases": sum(counts.values())}
    if not outcomes:
        raise NoResults(f"result file at {path} contains no testcase element")
    return outcomes, meta


def merge_runs(per_run):
    """{test key: {outcome, why, runs}} across several result files.

    Two result files are needed here, not one, and the reason is structural rather than
    convenient: this repository's CI runs the suite twice — once against the live database and
    once against a disposable PostgreSQL server — and each job SKIPS the other's tests by
    design. 45 of the skips in a local run read `SUPABASE_DB_URL not set`. So a requirement
    whose only test lives in the disposable-server job is skipped in the job that writes the
    ledger, and reading one file alone would report it as untested. That is an UNDER-count, and
    an under-count is not the safe direction — it is the same defect pointing the other way,
    and it teaches a reader to ignore the report.

    The merge rule, stated because it is the one place a pass can be manufactured:

      * a FAILURE or ERROR in ANY run makes the test failed. A test that fails somewhere is
        failing, whatever it did elsewhere.
      * otherwise a PASS in ANY run makes it passed, and the run that produced it is named. A
        skip in a job where the test does not apply, beside a pass in the job where it does, is
        a test that passed.
      * otherwise skipped, and otherwise not_run.

    The asymmetry is deliberate: failures are unioned, passes require a named source.
    """
    merged = {}
    for label, outcomes in per_run:
        for key, rec in outcomes.items():
            slot = merged.setdefault(key, {"outcome": None, "why": None, "runs": {}})
            slot["runs"][label] = rec["outcome"]
            current, incoming = slot["outcome"], rec["outcome"]
            if current is None:
                slot["outcome"], slot["why"] = incoming, rec["why"]
                continue
            # A failure anywhere wins outright; otherwise the BEST outcome wins.
            if OUTCOME_RANK[incoming] <= OUTCOME_RANK["error"]:
                slot["outcome"], slot["why"] = incoming, rec["why"]
            elif OUTCOME_RANK[current] > OUTCOME_RANK["error"] \
                    and OUTCOME_RANK[incoming] > OUTCOME_RANK[current]:
                slot["outcome"], slot["why"] = incoming, rec["why"]
    return merged


def roll_up(keys, outcomes):
    """The requirement's test state: the WORST outcome across its mapped tests.

    A mapped test absent from the results is `not_run` — it was never collected, which is a
    different fact from skipping and a very different fact from passing. Both are ranked below
    `passed`, so neither can carry a requirement to level 3.
    """
    if not keys:
        return "no_tests", {}
    per_test = {}
    for k in sorted(keys):
        rec = outcomes.get(k)
        per_test[k] = {"outcome": "not_run", "why": "not present in any supplied result file"} \
            if rec is None else {"outcome": rec["outcome"], "why": rec.get("why"),
                                 "runs": rec.get("runs", {})}
    worst = min((v["outcome"] for v in per_test.values()), key=lambda o: OUTCOME_RANK[o])
    return worst, per_test


# ---------------------------------------------------------------- levels 4-6: declared only

def load_evidence(path):
    """Explicit integration / deployment / observation references, or {} when none are declared.

    The schema is one object per requirement:

        {"REQ-NUT-001": {"integration": {"ref": "tools/resolve_nutrition.py::main",
                                         "verified_at": "2026-09-10",
                                         "how": "job run against a disposable spine, 12 atoms"}}}

    `ref` and `how` are both required, because a reference with no statement of what was
    verified is a citation to nothing. NOTHING here is derived: this file is written by whoever
    performed the verification, and its absence means UNKNOWN rather than false. There is no
    code path in this tool that populates it.
    """
    path = pathlib.Path(path)
    if not path.exists():
        return {}, f"no evidence file at {path}; levels 4-6 are UNKNOWN for every requirement"
    doc = json.loads(path.read_text())
    if not isinstance(doc, dict):
        raise ValueError(f"{path} must hold an object keyed by requirement id")
    cleaned, rejected = {}, []
    for rid, kinds in doc.items():
        if not isinstance(kinds, dict):
            rejected.append(f"{rid}: not an object")
            continue
        keep = {}
        for kind, ref in kinds.items():
            if kind not in EVIDENCE_KINDS:
                rejected.append(f"{rid}.{kind}: not one of {EVIDENCE_KINDS}")
                continue
            if not isinstance(ref, dict) or not ref.get("ref") or not ref.get("how"):
                # Refused rather than accepted-with-a-warning. An evidence entry that does not
                # say what was verified would still print as INTEGRATED, which is the whole
                # failure mode being corrected.
                rejected.append(f"{rid}.{kind}: needs both 'ref' and 'how'")
                continue
            keep[kind] = ref
        if keep:
            cleaned[rid] = keep
    note = f"{len(cleaned)} requirement(s) carry declared evidence in {path}"
    if rejected:
        note += f"; {len(rejected)} entry/entries refused: " + "; ".join(sorted(rejected)[:5])
    return cleaned, note


# ---------------------------------------------------------------- the join

def ladder_level(*, is_declared, keys, test_state, evidence):
    """The highest level that holds, plus why it stops there. Monotonic by construction.

    Written as a fall-through rather than a max() over independent predicates: a declared
    deployment reference for a requirement whose tests are skipped must NOT report DEPLOYED,
    and a max() would.
    """
    if not is_declared:
        return "ORPHAN", "named by a test but declared in no spec"
    if not keys:
        return "DECLARED", "no test function name carries this ID"
    if test_state != "passed":
        reason = {"skipped": "every mapped test was skipped or one of them was",
                  "not_run": "a mapped test was not collected in this run",
                  "failed": "a mapped test failed", "error": "a mapped test errored",
                  "no_results": "no result file was supplied, so the tests' outcome is unknown"}
        return "MAPPED", reason.get(test_state, f"mapped tests rolled up to {test_state!r}")
    for kind in EVIDENCE_KINDS:
        if kind not in (evidence or {}):
            return (LEVELS[LEVELS.index(KIND_LEVEL[kind]) - 1],
                    f"no declared {kind} evidence")
    return "OBSERVED", "declared evidence at every level"


def audit(root=ROOT, junit=None, evidence_path=None):
    """Everything the report needs, as data. One pass, no side effects, no writes."""
    root = pathlib.Path(root)
    spec_ids = declared_requirements(root)
    unparseable = []
    mapped = mapped_tests(root, unparseable)

    paths = [] if junit is None else ([junit] if isinstance(junit, (str, pathlib.Path))
                                      else list(junit))
    per_run, junit_meta, notes = [], [], []
    for path in paths:
        try:
            outcomes, meta = parse_junit(path)
        except NoResults as e:
            notes.append(str(e))
            continue
        label = pathlib.Path(path).name
        per_run.append((label, outcomes))
        junit_meta.append({"label": label, **meta})
        notes.append(f"{label}: {meta['n_testcases']} testcases, "
                     + ", ".join(f"{v} {k}" for k, v in sorted(meta["counts"].items())))
    outcomes = merge_runs(per_run)
    junit_note = "; ".join(notes) if notes else "no result file supplied"
    if not per_run:
        junit_meta = None

    evidence, evidence_note = load_evidence(
        evidence_path if evidence_path is not None else root / "ops" / "requirement_evidence.json")

    records = {}
    for rid in sorted(set(spec_ids) | set(mapped)):
        keys = mapped.get(rid, set())
        if not per_run:
            # No results at all. Not "passed", not "skipped" — unknown, and named as such.
            state, per_test = ("no_results", {k: {"outcome": "unknown", "why": None}
                                              for k in sorted(keys)}) if keys \
                else ("no_tests", {})
        else:
            state, per_test = roll_up(keys, outcomes)
        level, why = ladder_level(is_declared=rid in spec_ids, keys=keys, test_state=state,
                                  evidence=evidence.get(rid))
        records[rid] = {
            "requirement": rid, "family": spec_ids.get(rid), "declared": rid in spec_ids,
            "mapped_tests": sorted(keys), "test_state": state, "per_test": per_test,
            "evidence": evidence.get(rid, {}), "level": level, "level_reason": why,
        }
    return {"root": str(root), "revision": revision(root), "generated_at": _now(),
            "junit": junit_meta, "junit_note": junit_note, "evidence_note": evidence_note,
            "unparseable_test_files": unparseable,
            "environment": environment(), "records": records}


# ---------------------------------------------------------------- provenance of the audit itself

def revision(root=ROOT):
    """The revision audited, and whether the tree was dirty when it was audited.

    An evidence report with no revision is an evidence report about nothing: the tests that
    passed, passed against some particular source, and "dirty" means that source is not
    reconstructible from the commit alone.
    """
    def git(*args):
        try:
            done = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True,
                                  timeout=15)
            return done.stdout.strip() if done.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None
    head = git("rev-parse", "HEAD")
    return {"head": head, "short": (head or "")[:7] or None,
            "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(git("status", "--porcelain"))}


def environment():
    """The interpreter the AUDIT ran under, and whether the optional analysis stack imports.

    Recorded because a skip is a fact about an environment and not about a requirement:
    REQ-INF-520's executing tests skip wherever NumPyro is absent, and a report that omits which
    interpreter produced it cannot be read at all. These flags describe THIS process; they are
    not evidence about the run that produced the result file, which carries its own hostname
    and timestamp, and they never move a ladder level.
    """
    optional = {}
    for module in ("numpy", "scipy", "statsmodels", "networkx", "jax", "numpyro", "pg8000",
                   "yaml", "ofxtools"):
        try:
            __import__(module)
            optional[module] = True
        except Exception:                    # noqa: BLE001 — any import failure is absence
            optional[module] = False
    return {"python": sys.version.split()[0], "platform": sys.platform,
            "importable": optional}


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- rendering

def _header(result, out):
    rev, env = result["revision"], result["environment"]
    dirty = " (DIRTY WORKING TREE — these results are not reconstructible from the commit)" \
        if rev["dirty"] else ""
    out(f"  revision   {rev['short']} on {rev['branch']}{dirty}")
    out(f"  audited at {result['generated_at']} under python {env['python']} / {env['platform']}")
    out(f"  results    {result['junit_note']}")
    if result["junit"]:
        for j in result["junit"]:
            out(f"             {j['label']} run at {j['timestamp']} on {j['hostname']}")
    else:
        out("             LEVEL 3 IS UNKNOWN FOR EVERY REQUIREMENT — no outcome was read.")
    out(f"  evidence   {result['evidence_note']}")
    if result["unparseable_test_files"]:
        out(f"  BROKEN     {len(result['unparseable_test_files'])} test file(s) do not parse and "
            f"contribute no coverage: {result['unparseable_test_files'][0]}")
    absent = sorted(k for k, v in env["importable"].items() if not v)
    if absent:
        out(f"  NOTE       not importable in the auditing interpreter: {', '.join(absent)}. A test "
            f"needing one of these skips here.")


def render_summary(result, out=print):
    """Counts per level, by family. Never a single percentage: the whole defect being corrected
    was a percentage that averaged six different questions into one number."""
    _header(result, out)
    by_family = collections.defaultdict(collections.Counter)
    for rec in result["records"].values():
        by_family[rec["family"] or "(orphan)"][rec["level"]] += 1
    width = max([len("family")] + [len(f) for f in by_family]) + 2
    out("")
    out("  " + "family".ljust(width) + "".join(l.rjust(14) for l in LEVELS) + "ORPHAN".rjust(9))
    for family in sorted(by_family):
        row = by_family[family]
        out("  " + family.ljust(width)
            + "".join(str(sum(row[l] for l in LEVELS[i:])).rjust(14)
                      for i in range(len(LEVELS)))
            + str(row["ORPHAN"]).rjust(9))
    total = collections.Counter()
    for row in by_family.values():
        total.update(row)
    out("  " + "TOTAL".ljust(width)
        + "".join(str(sum(total[l] for l in LEVELS[i:])).rjust(14) for i in range(len(LEVELS)))
        + str(total["ORPHAN"]).rjust(9))
    out("")
    out("  Each column is CUMULATIVE: a requirement counted under TESTS_PASSED is also counted")
    out("  under DECLARED and MAPPED. Levels are monotonic, so a column can never exceed the one")
    out("  to its left.")
    out("")
    out(f"  TESTS_PASSED means every test naming the requirement was collected and passed in the")
    out(f"  named result file. It does NOT mean the requirement's full sentence is covered, and it")
    out(f"  is not a substitute for INTEGRATED. Use --requirement to see the assertions relied on.")
    return 0


def render_prefix(result, prefix, out=print):
    rows = [r for rid, r in sorted(result["records"].items()) if rid.startswith(prefix)]
    if not rows:
        out(f"  no requirement matches {prefix!r}")
        return 1
    _header(result, out)
    out("")
    out(f"  {'requirement':<16}{'level':<14}{'tests':>6}  state / why it stops there")
    for rec in rows:
        out(f"  {rec['requirement']:<16}{rec['level']:<14}{len(rec['mapped_tests']):>6}  "
            f"{rec['test_state']} — {rec['level_reason']}")
    return 0


def render_open(result, prefix, out=print):
    """What has not reached TESTS_PASSED in one family, and why each one stops."""
    rows = [r for rid, r in sorted(result["records"].items())
            if rid.startswith(prefix) and r["level"] in ("DECLARED", "MAPPED", "ORPHAN")]
    _header(result, out)
    out("")
    out(f"  {len(rows)} {prefix} requirement(s) have not reached TESTS_PASSED:")
    for rec in rows:
        out(f"    {rec['requirement']:<16}{rec['test_state']:<12} {rec['level_reason']}")
    if not rows:
        out("    (none — every one has a mapped test that passed in the supplied results)")
    out("")
    out("  Reaching TESTS_PASSED is not the same as being covered, integrated or deployed.")
    return 0


def render_requirement(result, rid, out=print):
    rec = result["records"].get(rid)
    if rec is None:
        out(f"  {rid} is declared in no spec and named by no test")
        return 1
    _header(result, out)
    out("")
    out(f"  {rid}   family {rec['family']}   LEVEL: {rec['level']}")
    out(f"  stops there because: {rec['level_reason']}")
    out("")
    out(f"  1 DECLARED      {'yes' if rec['declared'] else 'NO — orphan'}")
    out(f"  2 MAPPED        {len(rec['mapped_tests'])} test(s) name this requirement")
    for key, detail in sorted(rec["per_test"].items()):
        out(f"                    [{detail['outcome']:>8}]  {key}")
        if detail.get("runs") and len(detail["runs"]) > 1:
            out("                                per run: "
                + ", ".join(f"{r}={o}" for r, o in sorted(detail["runs"].items())))
        if detail.get("why"):
            out(f"                                why: {detail['why']}")
    if not rec["mapped_tests"]:
        out("                    (none)")
    out(f"  3 TESTS_PASSED  {'yes' if rec['test_state'] == 'passed' else 'NO — ' + rec['test_state']}")
    for kind in EVIDENCE_KINDS:
        ref = rec["evidence"].get(kind)
        label = KIND_LEVEL[kind]
        if ref:
            out(f"  {LEVELS.index(label) + 1} {label:<13} {ref['ref']}")
            out(f"                    how: {ref['how']}   verified_at: {ref.get('verified_at', '?')}")
        else:
            out(f"  {LEVELS.index(label) + 1} {label:<13} UNKNOWN — no declared {kind} evidence. "
                f"Not inferred from the tests.")
    return 0


def render_markdown(result, out=print):
    """The report body. Same numbers as the summary, in a form a document can carry."""
    rev = result["revision"]
    out(f"Generated {result['generated_at']} against `{rev['short']}` on `{rev['branch']}`"
        f"{' with a DIRTY working tree' if rev['dirty'] else ''}.")
    out("")
    out(f"- Results read: {result['junit_note']}")
    out(f"- Evidence file: {result['evidence_note']}")
    out(f"- Auditing interpreter: python {result['environment']['python']} "
        f"({result['environment']['platform']})")
    absent = sorted(k for k, v in result["environment"]["importable"].items() if not v)
    out(f"- Not importable here: {', '.join(absent) if absent else 'nothing'}")
    out("")
    out("| family | declared | mapped | tests passed | integrated | deployed | observed | orphan |")
    out("|---|---:|---:|---:|---:|---:|---:|---:|")
    by_family = collections.defaultdict(collections.Counter)
    for rec in result["records"].values():
        by_family[rec["family"] or "(orphan)"][rec["level"]] += 1
    total = collections.Counter()
    for family in sorted(by_family):
        row = by_family[family]
        total.update(row)
        cells = " | ".join(str(sum(row[l] for l in LEVELS[i:])) for i in range(len(LEVELS)))
        out(f"| {family} | {cells} | {row['ORPHAN']} |")
    cells = " | ".join(str(sum(total[l] for l in LEVELS[i:])) for i in range(len(LEVELS)))
    out(f"| **TOTAL** | {cells} | {total['ORPHAN']} |")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(ROOT), help="repository root to audit")
    ap.add_argument("--junit", action="append", default=None, metavar="PATH",
                    help="a pytest --junitxml report; repeat for each CI job, because this "
                         "repository's jobs skip each other's tests by design. Without any, "
                         "level 3 is UNKNOWN for every requirement and the report says so "
                         "rather than assuming a pass.")
    ap.add_argument("--evidence", default=None,
                    help="explicit integration/deployment/observation references "
                         "(default: ops/requirement_evidence.json)")
    ap.add_argument("--prefix", help="per-requirement rows for one family, e.g. REQ-REC")
    # `--open REQ-FIN` is documented in docs/NEXT_SESSION.md. Kept working rather than removed,
    # but it now lists what has not reached TESTS_PASSED — which is what the reader wanted and
    # what the old flag could not tell them, because it never read a result file.
    ap.add_argument("--open", dest="open_prefix", metavar="PREFIX",
                    help="requirements in PREFIX that have NOT reached TESTS_PASSED")
    ap.add_argument("--requirement", help="the full evidence card for one requirement")
    ap.add_argument("--json", action="store_true", help="machine-readable, for a report build")
    ap.add_argument("--markdown", action="store_true", help="the report table")
    a = ap.parse_args(argv)

    result = audit(root=a.root, junit=a.junit, evidence_path=a.evidence)
    if a.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if a.markdown:
        return render_markdown(result)
    if a.requirement:
        return render_requirement(result, a.requirement)
    if a.open_prefix:
        return render_open(result, a.open_prefix)
    if a.prefix:
        return render_prefix(result, a.prefix)
    return render_summary(result)


if __name__ == "__main__":
    sys.exit(main())
