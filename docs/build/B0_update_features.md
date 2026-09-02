# B0 — `tools/update_features.py`: make `ops/features.json` tell the truth

**Why first.** `ops/features.json` has 15 entries, all `failing`, `proving_test: null`,
while capture, extraction, the read API and the conversation layer are live. The file
is write-locked for Claude Code (`.claude/settings.json` deny list) by design: only a
test runner may move an entry. That runner was never built. Definition-of-Done item 4
has therefore been unfulfillable since session 4. This session builds the runner.

**Requirement IDs satisfied:** the REQ-NFR entry in `specs/06-nfr/requirements.md` that
says a proven-count may only be incremented by the test runner — open the file, quote
the ID and its text in the session before starting. If no such ID exists, say so and
cite CONSTITUTION "Definition of Done" item 4 instead.

## What to build

`tools/update_features.py`:

1. Runs `python3 -m pytest tests/ -q --junitxml=/tmp/features_junit.xml` (never
   `-x`, never `-k`; the whole suite, always).
2. Parses the JUnit XML. For every `<testcase>` with no `<failure>`/`<error>`/`<skipped>`
   child, extracts every `REQ-[A-Z]+-[0-9]{3}` token from `classname + "::" + name`,
   after normalising `REQ_X_001` → `REQ-X-001` (test names use underscores).
3. Loads `ops/features.json`. For every entry whose `requirement` is in the passed set,
   sets `status: "passing"` and `proving_test` to the `classname::name` of the first
   passing test that names it. **Never** changes an entry in any other way: never
   deletes, never rewords `description`, never moves passing → failing (a regression is
   printed to stdout as `REGRESSION F-0xx` and left for a human; INV-6).
4. Writes the file back with `indent=2`, keys in original order, trailing newline.
5. Prints a table `id | requirement | status | proving_test`, then `N passing / M total`.
6. Exit 0 when it ran; exit 2 if pytest itself failed to start.

The script is the **only** writer. Add to `.claude/settings.json` `permissions.allow`:
`"Bash(python3 tools/update_features.py)"` (exact string, no wildcard). Do not remove
the `Edit`/`Write` denies on `ops/features.json`.

## Also in this session

List every REQ token currently present in test names:
`grep -rhoE "def test_[A-Za-z0-9_]+" tests/ | grep -oE "REQ_[A-Z]+_[0-9]{3}" | sort -u`.
Report in PROGRESS which of the 15 entries now pass and which have **no test at all**
(those stay failing — that is the honest state). Do not rename a test to make it match
an entry.

## Done when

- `python3 tools/update_features.py` output pasted.
- `git diff ops/features.json` pasted (may legitimately be empty if no test names a
  listed requirement — then the PROGRESS entry must say exactly that).
- `python3 tools/validate_layout.py` → 0 failed.
- PROGRESS entry + WHAT I DID NOT DO.
