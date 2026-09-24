# ADR-0163 — Bound the browser guard to reviewed offline acceptance

Date: 2026-09-24. Status: accepted; locally verified and integration checks passed.
Requirements: REQ-FIN-255, RULE-00; correction integration prerequisite.

## Recorded gate correction

The full regression run failed on the existing own-app browser smoke test.
REQ-FIN-255 prohibits the finance subsystem driving browser sessions against a
financial institution. ADR-0109 deliberately implemented a broader prohibition
on every browser-driver import, including test imports. That guard rejects the
offline app acceptance required to verify owner sign-in and read interfaces.

This decision explicitly supersedes ADR-0109's blanket browser-capability ban
only for the reviewed `tests/ask_browser_smoke.py` file. It does not amend the
finance requirement or constitution. RULE-00 permits correcting a wrong gate
through a recorded decision with an argument; silently hiding the import,
moving the test outside the scan, or excluding test directories is not permitted.

## Enforced boundary

The scanner recognizes only that repository-relative path and its exact reviewed
SHA-256. A changed file, another path or symlink loses recognition. The exception
applies only to its browser-driver finding; credential, payment and raw-mutation
checks still scan the file. Every other browser-driver import remains a failure.
There is no runtime setting to disable the financial guard.

The harness creates an ephemeral browser context with `offline=True` and blocked
service workers, without persistent profile or stored authentication. Context-wide
routing is registered before pages exist. Only the fixed own-app fixture URLs and
one exact dependency URL are fulfilled from local bytes; all other requests abort.
Tests exercise refused fetches, navigation and the first popup request. These are
browser-context controls, not a claim of OS-level network isolation. The test uses
reserved invalid hostnames and no financial institution or personal data.

Any harness edit invalidates the hash and requires renewed review and behavioral
verification before updating the pin. This intentionally makes edits fail closed.
The hash is review evidence, not a sandbox for arbitrary future Python code.

## Verification and failure modes

Scanner acceptance covers the exact harness; adversarial cases cover copied paths,
symlinks, content mutation and other prohibited constructs. Existing never-rule
tests remain unchanged. Browser verification must pass its refusal cases and the
existing app journey. Independent review is required before integration.

The earlier failed suite remains recorded as failed. A later passing result is
separate evidence. No new dependency, production capability, external request,
financial automation or recurring cost is introduced by this correction.

Independent review accepted the scoped gate correction and retained the network
isolation and hash-renewal limitations. Actual Chrome run passed the refusal cases
and existing app journey; finance-never tests27passed1.56s. The prior noDB failure
is preserved in /tmp/capture-correction-unit-full.log; the subsequent sanctioned full writer
passed1427 tests with892 guarded/dependency skips; no test was relabelled. Reviewed harness SHA-256:
`139070901c1c8d593a618158deb21ec27238fb7b8474778346bbd384d34e1d41`.
