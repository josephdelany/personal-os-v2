#!/usr/bin/env python3
"""The evidence report: what ran, what passed, and what anything but a test ever calls.

WHY THIS EXISTS. `tools/audit_requirements.py` used to report "685 of 685 requirements
proven" by globbing requirement IDs out of test function NAMES in the source tree. It never
started pytest and never opened a result file, so a green test, a skipped test, a failing
test and a test that was never collected all produced the same word. That number was quoted
as a completion claim. ADR-0136 records the defect; `tools/audit_requirements.py` was rewritten
to read JUnit results and now owns the question "did it run and pass?".

Fixing that leaves a second, quieter over-claim standing, and this tool exists for it.

**A requirement can have a named test that genuinely passes against a module that nothing in
the running system ever calls.** `tools/engines/` holds 55 modules. Eight are reachable from a
script a scheduled workflow starts; five more only from a hand-run script. The remaining
forty-two are imported by `tests/` and by nothing else — libraries with no caller. Their tests
pass. Passing proves the module's arithmetic; it does not prove that any job, surface or
endpoint invokes it, and "proven" was being read as though it did.

So this report prints as SEPARATE COLUMNS the two facts that one word used to blur:

    status        did a named test RUN and PASS?     delegated to tools/audit_requirements.py
    reachability  is what that test imports reachable from a production entry point?
                  scheduled / cli / tests-only / none, from the import graph

and it adds the one state the ladder does not model: **vacuous** — the requirement's only
passing named test asserts nothing. A name is not an assertion.

The two columns are never combined into a single percentage. A single percentage is the one
form of evidence nobody re-derives, which is how the original claim survived two reviews.

WHAT THIS TOOL WILL NOT DO.

*It will not run without results.* No result file means every status is unknown and this exits
non-zero. Degrading to a name count is the defect it exists to correct.

*It will not call reachability "wired", "integrated" or "deployed".* An import edge is a static
fact about source text. It says nothing about whether the job ran, whether a row landed, or
whether Joe ever saw the number. Those are levels 4-6 of the ladder, they come only from a
declared reference, and this tool does not populate them.

*It will not be hand-edited.* `--check` regenerates the document and exits 1 when the file on
disk differs, so a figure cannot be improved with a text editor.

    PYTHONPATH=. python3 tools/evidence_report.py --report /tmp/junit.xml
    PYTHONPATH=. python3 tools/evidence_report.py --report live.xml --report local.xml
    PYTHONPATH=. python3 tools/evidence_report.py --report /tmp/junit.xml --check

The result file is an ordinary `pytest --junitxml=` report; `tools/update_features.py` already
writes one. No second format is defined here. Two files may be given because CI runs the suite
twice — live database, and disposable PostgreSQL 17 (ADR-0082) — and each job skips the other's
tests by design; `tools/audit_requirements.py` merges them, failures unioned and passes
requiring a named run.
"""
from __future__ import annotations

import argparse
import ast
import collections
import datetime as dt
import pathlib
import re
import sys

from tools import audit_requirements as audit_tool

ROOT = pathlib.Path(__file__).resolve().parents[1]

REACH = ("scheduled", "cli", "tests-only", "none")
REACH_RANK = {r: i for i, r in enumerate(REACH)}

# The order statuses are printed in, worst-known first after `passed`.
STATUSES = ("passed", "vacuous", "failed", "error", "skipped", "not_run", "no_results",
            "no_tests")


# ------------------------------------------------------------------ is the test empty?

def _trivial_assert(node):
    """`assert True`, `assert 1 == 1` — a statement that checks nothing about the system."""
    test = node.test
    if isinstance(test, ast.Constant):
        return True
    if isinstance(test, ast.Compare):
        return isinstance(test.left, ast.Constant) \
            and all(isinstance(c, ast.Constant) for c in test.comparators)
    return False


# `pytest.raises(...)`, `pytest.warns(...)`, `pytest.approx(...)`, unittest's `assertX(...)`.
ASSERTING = ("raises", "warns", "fail", "approx", "deprecated_call", "xfail")


def _callee_names(fn):
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def substantive(fn, helpers=None, depth=0):
    """Does this test body actually check something?

    A test named for a requirement that asserts nothing is a name, not evidence. But this
    check must not manufacture vacuity either, which would be the same defect pointing the
    other way. Several tests here delegate the assertion to a helper — `refuses(cur, ...)` in
    test_ontology_constraints, `check_imports(...)` in test_generator_gate — so calls into
    named helpers are followed, and INSIDE a helper a conditional `raise` counts as the check,
    because for `check_imports` that raise IS the check. In a test body a bare `raise` does not
    count, which is what the `depth` guard distinguishes.

    Measured on this suite: a body-only rule flags 10 of 1340 test functions as assertion-free
    and all 10 are false positives of exactly that kind.
    """
    for node in ast.walk(fn):
        if isinstance(node, ast.Assert) and not _trivial_assert(node):
            return True
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else \
                (func.id if isinstance(func, ast.Name) else "")
            if name in ASSERTING or name.startswith("assert"):
                return True
    if depth and any(isinstance(n, ast.Raise) for n in ast.walk(fn)):
        return True
    if helpers and depth < 3:
        for name in _callee_names(fn):
            helper = helpers.get(name)
            if helper is not None and helper is not fn and substantive(helper, helpers, depth + 1):
                return True
    return False


def helper_functions(root=ROOT):
    """Module-level functions in tests/, lib/ and tools/, by bare name, for the walk above."""
    out, root = {}, pathlib.Path(root)
    paths = [p for p in list((root / "tests").rglob("*.py")) + list((root / "lib").rglob("*.py"))
             + list((root / "tools").rglob("*.py")) if "__pycache__" not in str(p)]
    for path in sorted(paths):
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.setdefault(node.name, node)
    return out


def test_bodies(root=ROOT):
    """({`tests.test_x::test_y`: is it substantive}, {same key: its test module}).

    Test functions are found with `tools.audit_requirements.collected_test_names`' own rule —
    parsed, module- and class-level `test_*` — so this tool and the audit agree on what a test
    is. A regex would count a `def test_...` line inside a docstring or a fixture string.
    """
    root = pathlib.Path(root)
    is_real, owner = {}, {}
    helpers = helper_functions(root)
    tests = root / "tests"
    for path in sorted(tests.rglob("test_*.py")) if tests.is_dir() else ():
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except SyntaxError as e:
            print(f"  !! unparseable test file {path}: {e}", file=sys.stderr)
            continue
        module = ".".join(path.relative_to(root).with_suffix("").parts)
        nodes = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name.startswith("test_"):
                nodes[node.name] = node
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                            and item.name.startswith("test_"):
                        nodes[item.name] = item
        for name, fn in nodes.items():
            key = f"{module}::{name}"
            is_real[key], owner[key] = substantive(fn, helpers), module
    return is_real, owner


# ------------------------------------------------------------------ who calls what

def import_graph(root=ROOT):
    """({module: path}, {module: {imported module}}, {modules with a __main__ block}).

    `from tools.engines import panel` records an edge to `tools.engines.panel`, not only to
    `tools.engines`. Missing that form is how a naive graph concludes that
    `tools/run_analysis.py` imports no engine at all — it imports three that way.
    """
    root = pathlib.Path(root)
    files = [p for p in list(root.glob("tools/**/*.py")) + list(root.glob("lib/**/*.py"))
             + list(root.glob("ops/**/*.py")) + list(root.glob("tests/**/*.py"))
             if "__pycache__" not in str(p)]

    def name_of(path):
        parts = list(path.relative_to(root).with_suffix("").parts)
        return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)

    by_module = {name_of(p): p for p in files}
    edges, mains = collections.defaultdict(set), set()
    for path in files:
        source = path.read_text(errors="ignore")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        module = name_of(path)
        if re.search(r'^if __name__ == ["\']__main__["\']', source, re.M):
            mains.add(module)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in by_module:
                        edges[module].add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                if node.module in by_module:
                    edges[module].add(node.module)
                for alias in node.names:
                    if f"{node.module}.{alias.name}" in by_module:
                        edges[module].add(f"{node.module}.{alias.name}")
    return by_module, dict(edges), mains


def entry_points(root=ROOT, by_module=None):
    """Modules the automation actually starts: every `tools/x.py`, `ops/x.py` or `lib/x.py`
    named in a workflow file or in RUN_TONIGHT.sh.

    NOT "has a `__main__` block". A script nothing schedules is not a production entry point,
    and conflating the two makes almost everything look reachable — which is the flattering
    answer, and the reason the distinction is drawn here rather than assumed.
    """
    root = pathlib.Path(root)
    text = "".join(p.read_text(errors="ignore")
                   for p in sorted(root.glob(".github/workflows/*.yml")))
    runner = root / "RUN_TONIGHT.sh"
    if runner.exists():
        text += runner.read_text(errors="ignore")
    found = {".".join(pathlib.Path(s).with_suffix("").parts)
             for s in re.findall(r"((?:tools|ops|lib)/[A-Za-z0-9_/]+\.py)", text)}
    return {m for m in found if by_module is None or m in by_module}


def _closure(seeds, edges):
    seen, stack = set(seeds), list(seeds)
    while stack:
        for target in edges.get(stack.pop(), ()):
            if target not in seen:
                seen.add(target)
                stack.append(target)
    return seen


def module_reach(root=ROOT):
    """({module: reachability}, edges, sorted entry points) for every non-test module.

    scheduled   transitively imported by a script a workflow or RUN_TONIGHT.sh starts
    cli         transitively imported only by a hand-runnable script (a `__main__` block)
    tests-only  nothing outside `tests/` reaches it — a library with no caller

    An entry point is itself `scheduled`. The three values are ordered, and a module reachable
    both ways is reported at its best.
    """
    by_module, edges, mains = import_graph(root)
    seeds = entry_points(root, by_module)
    scheduled = _closure(seeds, edges)
    cli = _closure({m for m in mains if not m.startswith("tests.")} - seeds, edges)
    labels = {m: ("scheduled" if m in scheduled else "cli" if m in cli else "tests-only")
              for m in by_module if not m.startswith("tests.")}
    return labels, edges, sorted(seeds)


def test_reach(module, edges, labels):
    """(best reachability, the modules at that level) for what a TEST MODULE imports.

    Transitive: a test importing an engine that imports a scheduled module is reported at the
    best level anything it reaches carries. `none` means the test imports no first-party module
    at all — it exercises a document, a migration file, or pure Python, and reachability is not
    a meaningful question about it. `none` is reported, never silently counted as a failure.
    """
    seen, production = set(), []
    stack = [d for d in edges.get(module, ()) if not d.startswith("tests.")]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        if current in labels:
            production.append(current)
        stack.extend(d for d in edges.get(current, ())
                     if not d.startswith("tests.") and d not in seen)
    if not production:
        return "none", []
    best = min((labels[m] for m in production), key=lambda r: REACH_RANK[r])
    return best, sorted(m for m in production if labels[m] == best)


# ------------------------------------------------------------------ the join

def build(root=ROOT, reports=()):
    """Everything the document needs, as data. One pass, no writes.

    Status comes from `tools.audit_requirements.audit`, which owns the result-file reading, so
    there is exactly one implementation of "did it pass" in the repository. This function adds
    the two facts that audit deliberately does not model: whether the passing test asserts
    anything, and whether anything outside `tests/` calls what it imports.
    """
    root = pathlib.Path(root)
    if not reports:
        raise audit_tool.NoResults("no result file supplied; run pytest with --junitxml first")
    data = audit_tool.audit(root=root, junit=list(reports))
    if data["junit"] is None:
        raise audit_tool.NoResults(data["junit_note"])

    is_real, owner = test_bodies(root)
    labels, edges, seeds = module_reach(root)

    rows = {}
    for rid, record in data["records"].items():
        if not record["declared"]:
            continue                      # orphans are the audit's business, reported below
        keys = record["mapped_tests"]
        status = record["test_state"]
        passing = [k for k in keys if record["per_test"].get(k, {}).get("outcome") == "passed"]
        if status == "passed" and not any(is_real.get(k, False) for k in passing):
            # Every named test passed and not one of them asserts anything. The ladder cannot
            # see this: to it a green testcase is a green testcase.
            status = "vacuous"
        best, via = "none", []
        for key in (passing or keys):
            reach, modules = test_reach(owner.get(key, ""), edges, labels)
            if REACH_RANK[reach] < REACH_RANK[best]:
                best, via = reach, modules
        rows[rid] = {"family": record["family"], "status": status, "level": record["level"],
                     "reach": best, "via": via, "tests": keys,
                     "per_test": record["per_test"],
                     "empty_tests": sorted(k for k in passing if not is_real.get(k, False))}
    return {"rows": rows, "labels": labels, "entry_points": seeds, "audit": data}


# ------------------------------------------------------------------ the document

def render(result):
    """The whole report as markdown. Deterministic apart from the generated-at line."""
    rows, data = result["rows"], result["audit"]
    total = len(rows)
    by_status = collections.Counter(r["status"] for r in rows.values())
    passed = by_status.get("passed", 0)
    name_count = sum(1 for r in rows.values() if r["tests"])
    revision = data["revision"]
    out = []
    w = out.append

    w("# Evidence report")
    w("")
    w(f"Generated by `tools/evidence_report.py` at "
      f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} against "
      f"`{revision.get('short')}` on `{revision.get('branch')}`"
      + (" (**working tree dirty** — this report is about source that is not in a commit)"
         if revision.get("dirty") else "") + ".")
    w("")
    w("**Generated, never hand-edited.** `tools/evidence_report.py --check` regenerates this "
      "document and exits 1 if the file on disk differs.")
    w("")
    w("## The honest figure")
    w("")
    w(f"**{passed} of {total} requirements ({100 * passed / total:.1f}%) have a named test "
      f"that ran and passed** in the result files below.")
    w("")
    w(f"The superseded `tools/audit_requirements.py` reported **{name_count} of {total} "
      f"({100 * name_count / total:.1f}%) proven**. It counted requirement IDs appearing in "
      f"test FUNCTION NAMES in the source tree: it started no test run and opened no result "
      f"file, so a green test, a skipped test, a failing test and a test that was never "
      f"collected all counted identically. The gap between the two figures is "
      f"**{name_count - passed} requirements** whose entire evidence was a filename. "
      f"ADR-0136 records the defect.")
    w("")
    w("**Neither figure is a completion figure.** A passing named test is evidence about the "
      "assertions in that test. It is not evidence that the test's subject is the "
      "requirement's whole sentence, and it is not evidence that anything outside `tests/` "
      "ever calls the code — that is the second column, and it is reported separately below "
      "and never folded in.")
    w("")
    w("## Result files read")
    w("")
    for meta in data["junit"] or ():
        w(f"- `{meta['label']}` — {meta['n_testcases']} testcases, "
          + ", ".join(f"{v} {k}" for k, v in sorted(meta["counts"].items()))
          + (f", run {meta['timestamp']}" if meta.get("timestamp") else ""))
    w("")
    w("Merged by `tools.audit_requirements.merge_runs`: a failure in ANY run makes a test "
      "failed; a pass requires a run that produced one.")
    w("")
    w("## Column one — did a named test run and pass?")
    w("")
    w("| prefix | declared | passed | vacuous | failed | error | skipped | not run | no test |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    per_prefix = collections.defaultdict(collections.Counter)
    for rid, row in rows.items():
        per_prefix[rid.rsplit("-", 1)[0]][row["status"]] += 1
    order = ("passed", "vacuous", "failed", "error", "skipped", "not_run", "no_tests")
    for prefix in sorted(per_prefix):
        counts = per_prefix[prefix]
        w(f"| {prefix} | {sum(counts.values())} | "
          + " | ".join(str(counts.get(k, 0)) for k in order) + " |")
    w(f"| **TOTAL** | **{total}** | "
      + " | ".join(f"**{by_status.get(k, 0)}**" for k in order) + " |")
    w("")
    w("`not run` — a test carrying the ID exists in the source but no supplied result file "
      "contains it; it was never collected. `skipped` — at least one named test skipped, and a "
      "skip is not a pass. `vacuous` — every passing named test asserts nothing.")
    w("")
    empty = sorted(k for row in rows.values() for k in row["empty_tests"])
    if empty:
        w("Passing tests that assert nothing:")
        w("")
        for key in sorted(set(empty)):
            w(f"- `{key}`")
        w("")
    else:
        w("No passing named test in this suite is assertion-free.")
        w("")
    w("## Column two — does anything but a test call it?")
    w("")
    w("`scheduled` — the test imports something transitively reachable from a script a "
      "workflow or `RUN_TONIGHT.sh` starts. `cli` — reachable only from a hand-run script. "
      "`tests-only` — nothing outside `tests/` imports it. `none` — the test imports no "
      "first-party module (it exercises a document, a migration, or pure Python).")
    w("")
    w("This is a static fact about imports. It is **not** a claim that the job ran, that a row "
      "landed, or that anyone saw the number.")
    w("")
    w("| reachability | requirements | share |")
    w("|---|---:|---:|")
    reach_counts = collections.Counter(r["reach"] for r in rows.values())
    for reach in REACH:
        n = reach_counts.get(reach, 0)
        w(f"| {reach} | {n} | {100 * n / total:.1f}% |")
    w("")
    w("### Passing and reachable are not the same requirement set")
    w("")
    w("| | scheduled | cli | tests-only | none |")
    w("|---|---:|---:|---:|---:|")
    for status in STATUSES:
        line = [str(sum(1 for r in rows.values() if r["status"] == status and r["reach"] == k))
                for k in REACH]
        if any(x != "0" for x in line):
            w(f"| {status} | " + " | ".join(line) + " |")
    w("")
    engines = {m: r for m, r in result["labels"].items() if m.startswith("tools.engines.")}
    engine_counts = collections.Counter(engines.values())
    w(f"### `tools/engines/` — {len(engines)} modules")
    w("")
    w(", ".join(f"**{engine_counts.get(r, 0)} {r}**" for r in REACH if engine_counts.get(r))
      + ".")
    w("")
    w("| engine module | reachability |")
    w("|---|---|")
    for module in sorted(engines):
        w(f"| `{module.split('.')[-1]}` | {engines[module]} |")
    w("")
    w(f"Entry points found ({len(result['entry_points'])}): "
      + ", ".join(f"`{m}`" for m in result["entry_points"]) + ".")
    w("")
    w("## Every requirement")
    w("")
    w("| requirement | family | status | ladder | reachability | evidence |")
    w("|---|---|---|---|---|---|")
    for rid in sorted(rows):
        row = rows[rid]
        shown = [k for k in row["tests"]
                 if row["per_test"].get(k, {}).get("outcome") == row["status"]] or row["tests"]
        evidence = "; ".join(
            f"`{k}` ({row['per_test'].get(k, {}).get('outcome', 'not_run')})" for k in shown[:2])
        if len(shown) > 2:
            evidence += f" +{len(shown) - 2} more"
        w(f"| {rid} | {row['family']} | {row['status']} | {row['level']} | {row['reach']} | "
          f"{evidence or '—'} |")
    w("")
    orphans = sorted(r for r, rec in data["records"].items() if not rec["declared"])
    if orphans:
        w("## Orphans")
        w("")
        w("Requirement IDs named by a test but declared in no spec — a typo in a test name, or "
          "a requirement someone deleted. Either way the test's subject is uncheckable:")
        w("")
        for rid in orphans:
            w(f"- {rid}")
        w("")
    w("## What this report does not establish")
    w("")
    w("- That a passing test covers its requirement's whole sentence. Read the named tests.")
    w("- That a `scheduled` module is correctly wired, or that its job succeeded. Reachability "
      "is an import edge.")
    w("- Integration, deployment or observation on real data. Those are levels 4-6 of "
      "`tools/audit_requirements.py`'s ladder, they come only from a declared reference, and "
      "at this revision they are zero for every requirement.")
    w("")
    return "\n".join(out) + "\n"


def _comparable(text):
    """The generated-at line is the only non-deterministic part; --check ignores it."""
    return "\n".join(line for line in text.splitlines()
                     if not line.startswith("Generated by `tools/evidence_report.py`"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate docs/EVIDENCE_REPORT.md from real "
                                             "pytest results plus the import graph.")
    ap.add_argument("--report", action="append", default=[], metavar="XML",
                    help="a pytest --junitxml report; repeat for several runs")
    ap.add_argument("--out", default="docs/EVIDENCE_REPORT.md")
    ap.add_argument("--check", action="store_true",
                    help="regenerate and exit 1 if the file on disk differs")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)

    root = pathlib.Path(a.root).resolve()
    try:
        result = build(root, a.report)
    except audit_tool.NoResults as e:
        print(f"REFUSED: {e}\n"
              "  This tool reports what RAN. With no result file every status is unknown, and\n"
              "  counting test names instead is the defect it exists to correct (ADR-0136).\n"
              "  Produce one with:  PYTHONPATH=. python3 -m pytest tests/ "
              "--junitxml=/tmp/junit.xml", file=sys.stderr)
        return 2

    document = render(result)
    out = root / a.out
    if a.check:
        if not out.exists():
            print(f"{a.out} does not exist; generate it first", file=sys.stderr)
            return 1
        if _comparable(out.read_text()) != _comparable(document):
            print(f"{a.out} differs from the generated report: it was hand-edited, or the "
                  f"evidence moved. Regenerate it.", file=sys.stderr)
            return 1
        print(f"{a.out} matches the evidence")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document)
    rows = result["rows"]
    passed = sum(1 for r in rows.values() if r["status"] == "passed")
    reach = collections.Counter(r["reach"] for r in rows.values())
    print(f"wrote {a.out}")
    print(f"  {passed} of {len(rows)} requirements have a named test that ran and passed")
    print("  reachability: " + ", ".join(f"{reach.get(k, 0)} {k}" for k in REACH))
    return 0


if __name__ == "__main__":
    sys.exit(main())
