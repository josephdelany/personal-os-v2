# ADR-0059: Bank statement import — mappings from the repository, the sign convention, and the two timestamps

## Status
Accepted. Built by B13, migration 0051. Opens OQ-49.

## Date
2026-09-09

## 1. Column meaning comes from a file in the repository, never from the data

REQ-FIN-014 forbids inferring column semantics heuristically at runtime. Every CSV is read
through a per-institution mapping in `config/institutions/*.yaml`. REQ-FIN-016 names Apple
Card, Venmo, PayPal and Cash App as first-class, and all four are present.

**Matching rule:** a mapping matches a file when every source column it names is present in
that file's header. Matching on *required columns* rather than on the full header verbatim
means an institution adding a column does not silently orphan its mapping, while the meaning
of each column still comes only from the mapping file. Where more than one mapping matches,
the one naming the most columns wins; a genuine tie is a quarantine, not a coin flip.

The header is **found**, not assumed to be row 0 — Venmo's export puts preamble rows above it.

**REQ-FIN-015: a file matching no mapping is quarantined and parsed not at all.** The
quarantine message carries the observed header, because that is precisely what is needed to
write the mapping that would have matched. Guessing at an unknown bank's columns is the
failure this requirement exists to prevent: a mis-identified amount column produces a
plausible number, and a plausible wrong number is invisible.

## 2. The sign convention, which is the thing most likely to go silently wrong

Statements disagree about sign. Most banks write a purchase as `-12.34` (ledger convention).
**Apple Card writes a purchase as `+12.34`** and a payment as negative (statement convention).
A mapping declares which it uses via `amount_sign`, and atoms are always stored in the ledger
convention: **money out is negative**.

This is called out because an inverted sign is the failure with no symptom. Nothing errors;
every spend number in the system is simply negated, and every conclusion drawn from it is
backwards. `test_ADR_0059_bank_schema_detection_on_three_fixture_headers` asserts the signed
value for three institutions with two different conventions, and it is that assertion — not
the header detection — that is the point of the test.

## 3. Two timestamps, and never one value written to both

REQ-FIN-040 requires `occurred_at` (the swipe, what behavioural analysis reads) and
`posted_at` (settlement, what reconciliation reads) as distinct facts. REQ-FIN-042 forbids
writing the same value to both when a distinct one was available.

A statement carrying a settlement date distinct from the transaction date keeps both. **A
statement whose two dates are identical carries one fact, so settlement is left absent rather
than filled with a copy of the swipe.** A copied `posted_at` is an invented observation, and
worse, a later genuinely-posted row could never correct it — the fabrication would look like
data that already agreed.

A statement date carrying **no** clock time is anchored at **noon local**, with
`time_precision = 'day'` recording that the clock time is not real. A source that *does* carry
a time keeps it, at `time_precision = 'minute'`. Venmo and Cash App both export real
timestamps, and the first version overwrote them all with noon — which erased the only thing
separating two same-day, same-amount payments and made them collide in the dedupe key. Midnight was rejected: it
sits one hour from the 04:00 subject-day boundary in one direction and twenty in the other, so
a midnight anchor makes the subject day sensitive to a DST shift. Noon is unambiguous.

## 3b. Amount parsing refuses ambiguity rather than guessing

The first version stripped every character except digits, dot and sign, then called `float()`.
Three failures followed from that, all silent:

- `1.234,56` (European) became `1.23456` — a €1,234.56 charge stored as $1.23.
- `1 234,56` became `123456.0`.
- `(12.34)` under `positive_is_outflow` was negated **twice**: the parenthesis rule forced it
  negative and the sign convention then flipped it again, so a parenthesised Apple Card refund
  was stored as money *out*. §2 names sign inversion as "the failure with no symptom"; this
  path produced it.

Now the decision is made from the raw separator layout before anything is stripped: US grouping
is normalised, a comma-decimal amount is **refused** (none of the shipped mappings declare one,
so its presence means the mapping is wrong), a trailing minus is honoured, and parentheses
state the sign outright rather than composing with the mapping's convention. A refused amount
is a documented gap (RULE-06); a guessed one is a plausible wrong number.

## 4. What this build does NOT do about dedupe

REQ-FIN-043..048 describe a canonical-transaction engine: the same purchase arrives up to
three times (alert → API pending → CSV posted) and is matched on account, amount within 25%,
date within 3 days and normalised merchant, with a review queue for ambiguity and a permanent
`not_same` adjudication. **None of that is built here.** It is B17's, and building half of it
would produce merges nobody can audit.

What is built is narrower and stated plainly: the same *file* imported twice is a no-op
(ADR-0057), and an identical (amount, instant, kind) row already stored is not written again.
That is enough for the Tier-1 CSV floor and no more.

## 5. `ofxtools` as a conditional dependency (RULE-28)

REQ-FIN-013 requires OFX/QFX/QBO to be parsed by `ofxtools`, never by its Direct-Connect
fetch client. The importer does not fall back to a hand-rolled SGML reader — a silently-different parser for
a financial file is how amounts go quietly wrong. Where the dependency is absent, an OFX-family
file raises a quarantine naming it rather than being parsed by something else.

The OFX path reads **`DTUSER` as the swipe and `DTPOSTED` as settlement**. The first version
wrote `DTPOSTED` into `occurred_at` — the settlement date in the field the behavioural layer
reads, which is exactly what REQ-FIN-042 forbids — and produced no `posted_at` at all. This
path remains **untested**: `ofxtools` is not installed, so it has never been executed. That is
stated rather than implied.

### PyYAML — required, and added

REQ-FIN-014 requires the mappings to be YAML files in the repository, so PyYAML is a hard
dependency of the CSV path rather than an optional one. RULE-28 justification: **MIT-licensed,
pure Python, installed from PyPI, no account, no API, no network use at runtime — $0 recurring
with no overage surface.** The behaviour at any "limit" is that `pip install` fails, which is a
build error and not a bill. It is added to the `tests` workflow's install line in the same
change that depends on it, so CI cannot pass in an environment the code would fail in.

### ofxtools — justified, and installed

RULE-28 justification, stated before it is added: **MIT-licensed, pure Python, installed from
PyPI, no account, no API, no network use at runtime, and therefore $0 recurring with no
overage surface.** The failure at any "limit" is that `pip install` fails, which is a build
error, not a bill. CSV, Apple Health and Takeout require nothing beyond what is installed.

## 6. The unverified part, recorded rather than glossed (OQ-49)

**The four header signatures were written from public export documentation, not from Joe's own
files.** No real statement from any of these institutions has been imported. Until one has,
each mapping is a hypothesis. This is a deliberate consequence of the spec's own unresolved
question — "which institutions does Joe actually bank with?" is listed as unanswered in
`specs/03-finance/requirements.md` — and it is why the quarantine path prints the observed
header instead of failing silently: the first real file that does not match will say exactly
what the mapping should have been.

Joe's actual bank has **no mapping at all**, because the institution is not known. That is a
gap, not an oversight, and it is the first thing a real dropped file will close.
