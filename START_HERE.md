# START HERE — what to do in the terminal, right now

Two gates already exist and both pass. Run them first; they are how you check
work you cannot read.

    python3 tools/validate_layout.py     # 30 checks on the specification itself
    ./tools/test_guard.sh                # 25 real commands fed to the safety hook

Both print every check by name and exit non-zero on failure. If either ever
prints FAIL, that is the answer to "is this going well" — not what any session
tells you in prose.

## Then, in order

1. **Answer the three blocking questions.** OQ-03 (public or private repo),
   OQ-05 (uncertainty width for weighed food), OQ-07 ("necessary" narrowed to
   used / unused / unknown). Nothing downstream is safe to build until these
   are settled, and OQ-07 is the largest gap between what you asked for and
   what is written down.

2. **Say yes or no to the three doctrine reversals** — RULE-18, RULE-23,
   RULE-30 in `docs/CONSTITUTION.md`. They overturn positions the old spec held.

3. **Phase 0, and only Phase 0** (`docs/ROADMAP.md`): archive the old 19 files
   to `archive/`, verified by row count, nothing deleted; both keepalives live.

4. **Then the three missing specs** — REQ-ONT, REQ-WKT, REQ-BOD. REQ-WKT is
   the objective function you named as primary and it currently has zero
   requirements written.

## Read this before session two

`docs/OPERATING_MANUAL.md` — the session protocol, your five real levers for
verifying work you cannot read, what is genuinely hard in this project, and one
recommended change to the roadmap that needs your ruling.

## What the gates do not check

They check the specification, not the system — there is no schema, no code and
no data yet, so nothing here proves anything works end to end. The first thing
that will is Phase 3, the Big Mac slice.
