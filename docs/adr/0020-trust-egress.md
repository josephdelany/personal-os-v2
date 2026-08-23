# ADR-0020: Trust level at ingest, and the read/egress process separation

## Status

Accepted (RULE-29 clarification; no new numbered rule — the 30-cap holds)

## Date

2026-08-23

## Context

The **lethal trifecta** (Simon Willison, 2025-06-16, verified verbatim): private
data + untrusted content + external communication. Remove any one leg and the
prompt-injection exploit breaks. Untrusted content — email bodies, web text, PDF
text, merchant strings, and any model extraction over them — must reach a model as
quoted *data*, never as instruction.

**Citation note.** The NSA CSI "MCP: Security Design Considerations…"
(U/OO/6030316-26, May 2026) is **snippet-confirmed, primary unreachable** — the
media.defense.gov PDF returned 403 to the verifier; identifier/title/agency/date
corroborated from the URL and a secondary summary, not the primary document. **The
decision stands on the verified lethal-trifecta reasoning (Willison) plus OWASP
LLM01 (prompt injection) and LLM06 (excessive agency), not on the NSA document.**
The specific rules below ("never a generic `execute_sql`," "no session both reads
private data and egresses") are our sound least-privilege inferences, presented as
our derived architecture, **not** quoted verbatim from any of those sources.

## Decision

- **`trust_level ∈ {trusted, untrusted}` on `core.atoms` and `core.raw_captures`,
  set at ingest.** Anything authored by a third party — email body, web/PDF text,
  merchant string, or a model extraction over untrusted input — is `untrusted`.
- **Process separation (ratified):** a session/process that can read personal rows
  **must not** also hold an egress capability, and vice-versa. This breaks one leg
  of the trifecta structurally, not by prompt. It is the row-level + process-level
  complement to RULE-29's egress *logging* and to OQ-15's forbidden-import lint.
- **No generic `execute_sql` reaches a model** — only parameterised,
  schema-validated, read-only RPCs.

This is a **RULE-29 clarification + this ADR**, not a new numbered rule; the 30-rule
cap holds.

## Consequences

**Good.** The strongest single addition on the Phase-2 list: even a successful
injection into untrusted content cannot both read private rows and exfiltrate,
because no process holds both capabilities. `trust_level` is set once at ingest and
is cheap now, expensive to retrofit.

**Bad.** The read/egress separation is an *architecture* commitment that Phase-3+
code must honour; nothing in this migration enforces it yet (the column is the only
concrete artifact this phase). The enforcement (process boundaries, the RPC
allowlist, the forbidden-import lint of OQ-15) is owed as those surfaces are built.

## Alternatives considered

- **Trust as a computed property at read time.** Rejected: provenance of trust is
  a fact about ingest, not recomputable later; store it at the source.
- **Rely on prompt instructions ("treat the following as data").** Rejected: that
  is precisely the boundary prompt injection crosses; the defence must be
  structural.
