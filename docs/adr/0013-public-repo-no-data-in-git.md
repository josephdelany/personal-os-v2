# ADR-0013: The repository is public; no personal data ever enters git

## Status

Accepted. Resolves OQ-03 (public vs private) and OQ-02 (repository name). Extends
the enforcement of RULE-29; does not add a new numbered rule (the constitution is
at its 30-rule cap, and a public repo is already a third party under RULE-29).

## Date

2026-08-23

## Context

OQ-03 asked whether the repository is public or private. The trade recorded there:
a **public** repo gets unmetered GitHub Actions on 4 vCPU / 16 GB runners, which
is what makes the statistical layer (specification-curve and permutation
inference) affordable at all; a **private** repo caps at 2,000 minutes/month on
2 vCPU / 8 GB. The cost of going public is that a committed secret is a real
breach and all pipeline logic is visible.

The blocker on deciding public was OQ-01 (an unrotated exposed credential).
OQ-01 is now resolved (the exposed value is dead; the live credential lives only
in gitignored `.claude/settings.local.json`). With rotation done, the compute
argument wins.

## Decision

1. **The repository is PUBLIC.** Accepted for the unmetered Actions capacity the
   statistical layer depends on (ADR-0001's compute budget).

2. **Repository name: `personal-os`.** Nothing cute, nothing identifying.

3. **No personal data ever enters git — not one row.** A public git repository
   is a third party; committing personal data to it is an egress to a
   non-allowlisted destination, already forbidden in principle by RULE-29. This
   ADR makes it explicit and enforced:
   - Every data path — Parquet, exports, fixtures, caches — is **gitignored by
     default**. `_legacy_snapshot/` stays gitignored permanently.
   - A tracked `.parquet`, `.csv`, `.db`, or `.sqlite` file **fails CI**
     (`tools/validate_layout.py` section 9, LINT tier). Demonstrated to fire:
     tracking a dummy `.csv` produced `FAIL … (RULE-29)` and exit 1; the clean
     tree passes.
   - Any exception (e.g. a fixture that must be tracked) requires an ADR
     **before** the file is tracked.
   - RULE-29's text is amended to state this. No new numbered rule is added — the
     30-rule cap holds.

## Consequences

- **Before the first push to the public remote**, the dead credential string in
  git history (commit `990bc97`, the skeleton commit) becomes publicly visible.
  It is dead (rotated), so this is embarrassment, not breach. Scrubbing it
  (history rewrite / fresh initial commit) is optional and is a decision owed at
  first-push time, flagged in OQ-01. This ADR does not perform it.
- CI must run on the public repo; the data-file check runs in
  `tools/validate_layout.py`, which is already the first gate.
- Fixtures (RULE-01, `tests/fixtures/`) are not auto-exempt: a tracked data-file
  fixture trips the check and needs an ADR. `tests/fixtures/` is empty today, so
  there is no conflict yet.
- Creating the GitHub repo and the first push are **not** done in this session
  (Joe: "commit, and stop"). They are the first outward-facing actions and will
  be taken deliberately, after the history-scrub decision above.

## Alternatives considered

- **Private repo.** Rejected: the metered Actions minutes and smaller runners
  make permutation inference and specification curves unaffordable, which is the
  whole reason the compute budget in ADR-0001 assumed public.
- **A new numbered constitution rule (RULE-31).** Rejected: the constitution is
  capped at 30 and a public repo is already a third party under RULE-29;
  strengthening RULE-29 plus a CI check achieves the same enforcement without
  breaching the cap.
