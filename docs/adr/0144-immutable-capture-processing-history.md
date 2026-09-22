# ADR-0144 — Append-only capture processing history

Status: accepted by Joe, 2026-09-22 (OQ-83).
Requirements: REQ-CAP-025..027. Integrity: RULE-02, INV-1/2.

Joe explicitly approved replacing mutable raw-capture processing fields with
append-only processing events and a current-status view. The former requirement
wording contradicted the mutation-denying trigger in migration 0012 and ADR-0035.

Amend REQ-CAP-025..027 accordingly. Each processing outcome links to its immutable
capture, carries a server-recorded time and exposes status/provider error through
the projection. Repeated provider failures do not restart the pending clock.
Capture acknowledgement remains independent of enrichment success. Nightly retry
and review after more than 72 hours remain obligations. No raw-capture UPDATE,
backdating, invented transcript, or test-fixture exception is authorized.

Next implementation must prove persisted failure/success history, current-state
selection, retry selection, stable pending-age calculation, duplicate attempts,
and raw-record immutability through disposable SQL and the actual runner. The
projection must not infer completion for historical `received` rows merely from
the absence of an error. Preserve existing ingestion-time terminal states.

This decision adds no service or recurring dependency. Migration/runner design and
verification remain work; production writes and deployment retain their separate
authorization requirements. B16's historical raw-row UPDATE recipe is superseded
by this decision, not an instruction to weaken 0012.
