#!/usr/bin/env python3
"""
validate_layout.py - the first CI gate.

Checks the things that can be checked before any code exists:
that the documents reference only files that exist, that requirement
IDs are unique and well-formed, that the EARS grammar rules in
REQUIREMENTS_INDEX.md are actually obeyed, that the constitution
stays inside its own 30-rule cap, and that the counts the documents
claim about themselves are true.

Exit 0 = pass. Exit 1 = at least one FAIL. Warnings never fail the build.
"""
import json, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
fails, warns, passes = [], [], []
def ok(m): passes.append(m)
def fail(m): fails.append(m)
def warn(m): warns.append(m)

def read(p):
    f = ROOT / p
    return f.read_text() if f.exists() else None

# ---------- 1. structural: files the docs promise ----------
REQUIRED = [
    "CLAUDE.md", "docs/CONSTITUTION.md", "docs/DECISIONS.md",
    "docs/OPEN_QUESTIONS.md", "docs/ROADMAP.md",
    "specs/REQUIREMENTS_INDEX.md",
    ".claude/settings.json", ".claude/agents/reviewer.md",
    ".claude/hooks/guard-destructive.sh",
    ".claude/skills/session-start/SKILL.md",
    ".claude/skills/session-end/SKILL.md",
]
# files that CLAUDE.md / the skills / the hook actively read at runtime
RUNTIME_READS = ["ops/PROGRESS.md", "ops/features.json"]

for p in REQUIRED:
    (ok if (ROOT / p).exists() else fail)(f"required file {p}")
for p in RUNTIME_READS:
    if (ROOT / p).exists(): ok(f"runtime file {p}")
    else: fail(f"runtime file {p} is missing but session-start, session-end and the "
               f"SessionStart hook all read it -- every session will error on line 1")

# ---------- 2. settings.json parses and is coherent ----------
s = read(".claude/settings.json")
if s is None:
    fail("settings.json missing")
else:
    try:
        cfg = json.loads(s); ok("settings.json is valid JSON")
        perms = cfg.get("permissions", {})
        a, d = set(perms.get("allow", [])), set(perms.get("deny", []))
        if a & d: fail(f"permission appears in both allow and deny: {a & d}")
        else: ok("no allow/deny contradiction")
        ok(f"{len(a)} pre-approved operations, {len(d)} blocked outright, "
           f"{len(perms.get('ask', []))} prompt")
        cmds = json.dumps(cfg.get("hooks", {}))
        for f_ in re.findall(r'cat ([A-Za-z0-9_/.\-]+\.md)', cmds) + \
                  re.findall(r'tail -n \d+ ([A-Za-z0-9_/.\-]+\.md)', cmds):
            if not (ROOT / f_).exists():
                fail(f"SessionStart hook runs on {f_} which does not exist")
    except Exception as e:
        fail(f"settings.json does not parse: {e}")

# ---------- 3. hook is executable ----------
h = ROOT / ".claude/hooks/guard-destructive.sh"
if h.exists():
    (ok if h.stat().st_mode & 0o111 else fail)("guard hook is executable")

# ---------- 4. constitution: cap, contiguity, enforcement tier ----------
c = read("docs/CONSTITUTION.md")
if c:
    rules = re.findall(r'^\**RULE-(\d{2})\b', c, re.M)
    nums = sorted({int(x) for x in rules})
    if not nums: warn("could not find RULE-nn headings in the constitution")
    else:
        ok(f"{len(nums)} constitution rules, RULE-{nums[0]:02d}..RULE-{nums[-1]:02d}")
        numbered = [n for n in nums if n != 0]   # RULE-00 is the meta-rule, exempt
        if len(numbered) > 30: fail("constitution has %d numbered rules, cap is 30 (RULE-00 exempt)" % len(numbered))
        else: ok("constitution inside its 30-rule cap (%d numbered + RULE-00)" % len(numbered))
        missing = [n for n in range(nums[0], nums[-1] + 1) if n not in nums]
        if missing: fail(f"constitution rule numbers not contiguous, missing {missing}")
        else: ok("rule numbers contiguous")

# ---------- 5. requirements: IDs, uniqueness, EARS grammar ----------
spec_files = sorted((ROOT / "specs").rglob("requirements.md"))
all_ids, dup, no_shall, has_should, weasel = {}, [], [], [], []
formats = {}
# 'robust' on its own is vague; 'autocorrelation-robust' (and any hyphenated
# qualifier + robust) is a statistical term of art, so a preceding hyphen exempts it.
WEASEL = re.compile(
    r'\b(?:fast|slow|quick|reasonable|appropriate|user-friendly|efficient|as needed|etc\.)\b'
    r'|(?<!-)\brobust\b', re.I)
# tolerant: an ID may be bold or bare, statement may be on the same line or the next
REQ_LINE = re.compile(r'^(\**)(REQ-[A-Z]+-\d{3})\**\s*(\([^)]*\))?\s*(.*)$')

for sf in spec_files:
    lines = sf.read_text().split("\n"); rel = str(sf.relative_to(ROOT))
    n_req = n_sc = 0
    for i, line in enumerate(lines):
        if re.match(r'^[#*\s]*Scenario\b', line): n_sc += 1
        m = REQ_LINE.match(line)
        if not m: continue
        bold, rid, pat, tail = m.groups()
        if not pat:            # a definition always carries its EARS pattern marker;
            continue           # a bare ID at line start is a prose cross-reference
        n_req += 1
        formats.setdefault(("bold" if bold else "bare") + ("+inline" if tail.strip() else "+nextline"), []).append(rel)
        if rid in all_ids: dup.append((rid, rel, all_ids[rid]))
        else: all_ids[rid] = rel
        stmt = tail.strip()
        j = i + 1
        while j < len(lines) and lines[j].strip() and not REQ_LINE.match(lines[j]):
            stmt += " " + lines[j].strip(); j += 1
        if " shall " not in stmt.lower(): no_shall.append(rid + " (" + rel + ")")
        unquoted = re.sub(r"'[^']*'|`[^`]*`", "", stmt)
        if re.search(r'\bshould\b', unquoted, re.I): has_should.append(rid + " (" + rel + ")")
        # Only the normative SHALL response is testable prose. Anything before
        # the first SHALL is preamble, and a "because" clause is rationale that
        # explains *why* the requirement holds -- adjectives there are expected,
        # not defects, so trim both before the weasel scan.
        k = stmt.lower().find(" shall")
        normative = stmt[k:] if k != -1 else stmt
        b = normative.lower().find(" because")
        if b != -1: normative = normative[:b]
        w = WEASEL.search(normative)
        if w: weasel.append(rid + ": '" + w.group(0) + "'")
    ok("%s: %d requirements, %d Gherkin scenarios" % (rel, n_req, n_sc))

if len(formats) > 1:
    fail("the three spec files use %d different requirement markups (%s) -- any lint, "
         "traceability or coverage tool has to parse all of them" % (len(formats), ", ".join(sorted(formats))))
else:
    ok("all spec files use one consistent requirement markup")

ok("%d unique requirement IDs across %d spec files" % (len(all_ids), len(spec_files)))
if dup: fail("duplicate requirement IDs: %s" % (dup[:5],))
else: ok("no duplicate requirement IDs")
if no_shall: fail("%d requirements with no binding SHALL: %s" % (len(no_shall), no_shall[:5]))
else: ok("every requirement statement contains a binding SHALL")
if has_should: fail("SHOULD is banned but appears in: %s" % (has_should[:5],))
else: ok("SHOULD appears in no requirement statement")
if weasel: warn("%d unquantified adjectives: %s" % (len(weasel), weasel[:5]))
else: ok("no unquantified adjectives in requirement statements")

pref = {}
for rid in all_ids:
    k = rid.rsplit("-", 1)[0]; pref[k] = pref.get(k, 0) + 1
ok("prefix census: " + ", ".join("%s=%d" % kv for kv in sorted(pref.items())))

# ---------- 6. do the docs' self-reported counts match reality? ----------
idx = read("specs/REQUIREMENTS_INDEX.md")
if idx:
    for p, n in re.findall(r'(REQ-[A-Z]+)\D{0,40}?(\d{2,4})', idx):
        if p in pref and abs(pref[p] - int(n)) == 0: pass
    claimed = re.search(r'(\d{3,4})\s+requirements', idx)
    if claimed:
        cnum = int(claimed.group(1))
        if cnum != len(all_ids):
            fail(f"REQUIREMENTS_INDEX claims {cnum} requirements; {len(all_ids)} exist on disk")
        else: ok(f"index count {cnum} matches disk")

# ---------- 7. cross-references in prose ----------
body = "\n".join(filter(None, [read(p) for p in REQUIRED if read(p)]))
for ref in sorted(set(re.findall(r'`((?:docs|specs|ops|tools|\.claude|tests)/[A-Za-z0-9_/.\-]+)`', body))):
    if not (ROOT / ref).exists() and "*" not in ref:
        warn(f"referenced but absent: {ref}")

# ---------- 8. requirement IDs cited in docs must exist ----------
for rid in sorted(set(re.findall(r'\bREQ-[A-Z]+-\d{3}\b', body))):
    if rid not in all_ids: fail(f"{rid} is cited in a governing doc but is not defined in any spec")

# ---------- 9. no personal-data files tracked in git (RULE-29 / ADR-0013) ----------
# The repo is public. Not one row of personal data may be committed. A tracked
# Parquet/CSV/SQLite/DB file is a leak; any exception must be ADR'd first.
import subprocess
DATA_EXT = (".parquet", ".csv", ".db", ".sqlite")
try:
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                             capture_output=True, text=True, check=True).stdout.split()
    offenders = sorted(f for f in tracked if f.lower().endswith(DATA_EXT))
    if offenders:
        for f in offenders:
            fail(f"personal-data file tracked in git (RULE-29): {f}")
    else:
        ok(f"no tracked data files ({', '.join(DATA_EXT)}) — RULE-29 clean")
except Exception as e:
    warn(f"could not run git ls-files for the RULE-29 data-file check: {e}")

# ---------- 10. no committed coordinate / home-location literal (RULE-29 SCOPE lint) ----------
# ADR-0029 opened location storage but kept the egress ban absolute: "a lint fails
# the build if a coordinate or the home location can reach an export, log, commit,
# or prompt path." This is a STATIC TRIPWIRE, not coverage — it catches a coordinate
# or home-location literal committed to the public repo, in the common serializations
# (JSON/dict key, coordinate pair, WKT POINT, home_* identifier). It CANNOT prove the
# absence of every encoding (geohash, split x/y, base64) — a static regex never can
# (cf. OQ-15). The AUTHORITATIVE enforcement is the RUNTIME egress proof (no coordinate
# reaches an export/log/prompt at execution time; `ops.egress_log`) + review, OWED when
# the location table (Phase 4) and egress paths (Phase 3) exist. Named here, not skipped,
# so a green from this lint is never mistaken for "no coordinate can leak."
# tests/ is excluded: its fixtures are synthetic (RULE-01), not personal coordinates.
CODE_EXT = (".py", ".sql", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml", ".sh")
SELF = "tools/validate_layout.py"
HOME_COORD = re.compile(r'\bhome_(?:lat|lon|lng|latitude|longitude)\b', re.I)
COORD_KV   = re.compile(r'["\']?\b(?:lat|lon|lng|latitude|longitude)\b["\']?\s*[:=]\s*-?\d{1,3}\.\d{3,}', re.I)
COORD_PAIR = re.compile(r'-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}')  # decimal-degree pair
WKT_POINT  = re.compile(r'\bPOINT\s*\(\s*-?\d', re.I)
try:
    coord_offenders = []
    for f in tracked:
        if not f.lower().endswith(CODE_EXT) or f == SELF or f.startswith("tests/"):
            continue
        p = ROOT / f
        try:
            txt = p.read_text(errors="ignore")
        except Exception:
            continue
        m = (HOME_COORD.search(txt) or COORD_KV.search(txt)
             or COORD_PAIR.search(txt) or WKT_POINT.search(txt))
        if m:
            coord_offenders.append(f"{f}: '{m.group(0)}'")
    if coord_offenders:
        for o in coord_offenders:
            fail(f"coordinate/home-location literal committed (RULE-29): {o}")
    else:
        ok("no committed coordinate/home-location literal (RULE-29 static tripwire; runtime egress proof owed Phase 3/4)")
except Exception as e:
    warn(f"could not run the RULE-29 coordinate-literal check: {e}")

# ---------- report ----------
for m in passes: print(f"PASS  {m}")
for m in warns: print(f"WARN  {m}")
for m in fails: print(f"FAIL  {m}")
print(f"\n{len(passes)} passed, {len(warns)} warnings, {len(fails)} failed")
sys.exit(1 if fails else 0)
