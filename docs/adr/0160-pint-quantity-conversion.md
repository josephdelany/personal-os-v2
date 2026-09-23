# ADR-0160 — Pint owns physical quantity conversion

Date: 2026-09-23. Status: implemented, reviewed and integrated locally; deployment unverified.

REQ-NUT-019 explicitly requires Pint. The verified literal adapter at cf404e6
connects existing fixed mass factors but does not satisfy that dependency contract.
Use Pint 0.26.1 through one shared quantity owner, retaining exact extraction
evidence and the existing nutrition interval/atom owner. Supported unit aliases
are mapped explicitly; never evaluate arbitrary transcript expressions as units.
Physical conversion does not infer food density or a vernacular portion size.
Volumes remain volumes unless an independently authorized source supplies the
needed relationship. Preserve source-specific serving parsing and method policy.

## Cost, limits and privacy before introducing the dependency

Pint is a BSD-licensed local Python library, not a hosted service. Pin 0.26.1,
compatible with the repository's Python 3.12 CI and local Python 3.14. Install
through pip in development and the actual executing CI/runtime environments;
record transitive dependency versions in verification evidence. Runtime calls
use local unit definitions only, with no outbound request or personal disclosure.

Recurring cost is $0. There is no account, quota, paid tier, billing credential or
automatic overage. Expected use is one bounded scalar conversion per extracted
quantity or source serving, sharing one registry per process. Existing extraction
and worker limits bound input and execution. Unsupported dimensions/units and
nonfinite values return an explicit unresolved outcome; absent dependency fails
installation/readiness rather than silently switching calculation libraries.
Memory/CPU exhaustion is a worker failure under existing retry/deadline rules,
never a trigger to purchase capacity. No new service or vendor egress permission.

## Acceptance and limits

Verify aliases, compact literal spans, amount/unit binding, refusal of volume-to-
mass without density, persisted provenance and count/serving compatibility through
the saved capture consumer. Cover OFF/USDA callers and actual workflow dependencies.
Run required integration gates. No migration or deployment is authorized here;
real device/provider acceptance and other backend requirements remain open.

Sources: [Pint package and license](https://pypi.org/project/Pint/),
[official quantity tutorial](https://pint.readthedocs.io/en/latest/getting/tutorial.html).


Local verification: pure133passed40guardedSQLskips1.31s and layout43; fullnoDB1360
passed873skipped216.21s. Independent reviewer accepted amount/unit binding, symbol
case, overflow and density refusal. Initial fullSQL failed only because the local
virtual environment lay inside repository egress-scanner scope. It was moved to
/tmp/personal-os-pint-venv-cf404e6, preserving the scanner; final SQL rerun is pending.
Dependencies: Pint0.26.1, flexcache0.3, flexparser0.4, platformdirs4.9.4,
typing-extensions4.15.0. Saved compact decimal captures and unit aliases are covered;
word-valued amounts remain the next capture quantity acceptance case. No deployment.


Pint final integration: fullnoDB1360passed873skipped216.21s, terminal24127;
finalSQL1046passed1production-onlyskip379.92s, terminal29354/server stopped.
Stagedlayout43passes, terminal3756. Source hashes match; logs/JUnit/dependency
versions/skip reasons archived .local/evidence/capture-pint, original environmental
failure retained separately. Ledger14/15 unchanged; pre-existing F006 diagnostic.
SQLskip is live visits_public shape; noDB skips are SQL/live guards and two existing
NumPyro cases. Four spine invariants pass; genericRULE04 remains pending.
Independent review accepted conversion/overflow/case/density boundaries. No migration.
This closes local Pint conversion of verified literal decimal quantities and the
runtime dependency declaration, not word-valued amounts, density-dependent food
mass, actual deployment/device/provider observation, M3 or M6.
