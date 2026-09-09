# Per-institution CSV mappings (REQ-FIN-014)

One file per institution. REQ-FIN-014 forbids inferring column meaning heuristically at
runtime, so a CSV is only ever read through one of these files. REQ-FIN-015 says a file
matching none of them is quarantined with reason `no_institution_mapping` and produces no
transaction row — it is never parsed on a guess.

**Matching rule.** A mapping matches a file when every source column it names is present in
that file's header. Matching on required columns rather than on the full header verbatim
means an institution adding a column does not silently orphan the mapping, while the meaning
of each column still comes only from this file. Where more than one mapping matches, the one
naming the most columns wins; a genuine tie is a quarantine, not a coin flip.

**`amount_sign`** — the one field worth reading twice, because getting it backwards inverts
every spend number in the system without any error appearing:

- `negative_is_outflow` — the ledger convention. A purchase is `-12.34`. Most banks.
- `positive_is_outflow` — the statement convention. A purchase is `12.34` and a payment or
  refund is negative. Apple Card.

Atoms are always stored in the ledger convention: **money out is negative**.

**These headers are unverified.** They were written from public export documentation, not
from Joe's own files. Until a real export from an institution has been dropped and imported
once, treat its mapping as a hypothesis. A file that fails to match prints its header, which
is exactly what is needed to correct the mapping.
