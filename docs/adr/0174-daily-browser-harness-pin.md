# ADR-0174 — Re-pin the Ask harness and pin the daily-page harness

Date: 2026-09-26. Status: accepted; locally verified; independent review accepted 2026-09-27.
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
registered before pages exist. Only fixed own-app paths (the daily harness ignores any query
string, needed for `?demo=1`; the Ask harness matches exact URLs) and the one stub dependency
URL are fulfilled, and every other request aborts and is asserted. Both run the refusal cases for
fetch, navigation and a popup's first request against reserved invalid hosts. No financial
institution, personal data or credential is involved. Any edit, path swap, copy or symlink
loses recognition. Credential, payment and raw-mutation checks still scan both files. There
is still no runtime switch.

## Verification

- `test_finance_never.py`: 32 pass. The recognition and no-exemption cases now run for both
  harnesses, plus a new case: the daily harness's bytes at the Ask harness's path are refused.
- Both harnesses pass in real Chrome, including the refusal cases.

## Independent review (2026-09-27)

A read-only reviewer accepted the change at ba9d9e6 and found no blocking defect. It checked
that both pins equal the files' SHA-256 and that the Ask harness differs from its ADR-0163
reviewed bytes by the page path only. It checked the daily harness against every ADR-0163
property; it is stricter in one respect, asserting that no unexpected request was made.
Scratch probes refused a swapped path, a case variant, a nested path, CRLF bytes, and a
symlinked `tests/` pointing inside the root. It also confirmed that no test was loosened
relative to 85d3364.

Retained limitations:
- **Query strings.** Fixture paths in the daily harness match regardless of query string.
  The text above now says so. Offline routing still prevents any network access.
- **Symlinks outside the root.** A `tests/` directory symlinked outside the repository root
  is never walked by `tools/layout_sources.py`, so its files go unscanned rather than
  approved. This predates this ADR and is unchanged by it.
- **No Chrome run by the reviewer.** The reviewer did not run either harness in Chrome.
  The author ran both, and both passed, including the refusal cases.
