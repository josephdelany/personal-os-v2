# ADR-0174 — Re-pin the Ask harness and pin the daily-page harness

Date: 2026-09-26. Status: accepted; locally verified. Independent review: **pending**.
Requirements: REQ-FIN-255, RULE-00. Extends ADR-0163; does not amend REQ-FIN-255.

## What happened

ADR-0173 moved the Ask page to `app/explore.html` and made `app/index.html` the daily page.
That required a one-line edit to `tests/ask_browser_smoke.py` (the page it loads), and a new
harness, `tests/daily_browser_smoke.py`, verifies the daily page. Both were committed and
pushed to main before the full no-database suite ran. That suite then failed
`test_finance_never.py` twice: the edited harness no longer matched its pinned SHA-256, and
the new harness was an unpinned browser-driver import. The gate worked as designed. The
failure is recorded here, not hidden.

## Decision

The scanner recognizes an exact set of (path, SHA-256) pairs instead of one pair:

- `tests/ask_browser_smoke.py`: the ADR-0163 harness with only its served page path changed
  from `app/index.html` to `app/explore.html`.
- `tests/daily_browser_smoke.py`: the daily-page harness.

Everything ADR-0163 requires still holds for both. Each has an ephemeral context with
`offline=True`, blocked service workers and no stored authentication. Context-wide routing is
registered before pages exist. Only fixed own-app fixture URLs and the one stub dependency URL
are fulfilled, and every other request aborts and is asserted. Both run the refusal cases for
fetch, navigation and a popup's first request against reserved invalid hosts. No financial
institution, personal data or credential is involved. Any edit, path swap, copy or symlink
loses recognition. Credential, payment and raw-mutation checks still scan both files. There
is still no runtime switch.

## Verification

- `test_finance_never.py`: 32 pass. The recognition and no-exemption cases now run for both
  harnesses, plus a new case: the daily harness's bytes at the Ask harness's path are refused.
- Both harnesses pass in real Chrome, including the refusal cases.

## Pending

ADR-0163 requires independent review before a pin changes. It has not happened yet.
Until it does, treat both pins as provisional. The next reviewer should compare the
two files against the properties above and either accept or revert this ADR.
