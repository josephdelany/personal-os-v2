# ADR-0154 — Persisted extraction requests bound to saved transcription

Status: locally implemented and integration-tested; deployment and complete runtime remain open.
Date: 2026-09-23. REQ-CAP-050–060; RULE-02/09/28/29; ADR-0020/0148.

Private preparation reads the current saved voice transcript and immutable capture.
It persists the exact request payload and SHA256, transcript attempt identity,
processing predecessor, model ID, profile/schema version and cost estimate before
export. The existing isolated dispatcher owns the shared reservation and provider
call. Private consumption must later bind its response to that persisted request
and settled response digest before writing any extracted field/atom. Raw evidence
and attempts remain append-only. This draft does not mark transcription enriched.

Pydantic2 is the local schema validator required by REQ-CAP-055. It is open-source,
requires no hosted account or paid tier, has no metered usage, and fails locally on
invalid types/extra fields. Bound each model response before validation. No Logfire
or other telemetry service is enabled. Installed local version2.12.5; declare the
same major-version dependency in CI before relying on it. Projected use: one schema
validation per bounded extraction attempt, up to three attempts per transcript.
No new vendor or recurring service is introduced.

The food-item schema has exactly REQ-CAP-051's seven fields. JSON-schema output is
requested on every call; local strict validation is authoritative, not the provider's
schema promise. Quantity/offsets cannot be booleans; non-finite numbers refuse.
The outer response can include an exact temporal evidence span for deterministic
resolution under REQ-CAP-063–066. Nutrition values must be removed/refused before
persistence; no model nutrient quantity is accepted as an atom.

The model remains @cf/meta/llama-3.1-8b-instruct. The published pricing table currently
lists25608 input and75147 output neurons per million tokens. Preparation estimates
using serialized request bytes as an input-token upper estimate plus1024 template
margin and the explicit2048 output-token cap. This is a conservative planning
estimate, not observed usage or a vendor tokenizer proof; calibrate before activation.
The shared9000 soft/10000 hard budget and Free-plan hard refusal remain authoritative.
Example projection: a6000-byte request reserves333.771648 neurons; ten requests reserve
3337.71648 before transcription and other consumers. Three attempts can triple that
allocation; the ledger refuses/defer rather than bill or silently switch models.

Sources: https://developers.cloudflare.com/workers-ai/platform/pricing/
https://docs.pydantic.dev/latest/concepts/strict_mode/
https://docs.pydantic.dev/latest/concepts/json_schema/

The draft now implements private `consume-extraction`: match the settled model
receipt's full identity and request/response hashes, then validate locally before
any result row. Persist an immutable outcome plus separate fields carrying value,
provenance, reason and verified evidence. No provider response or validation input
is retained in diagnostics. Malformed/duplicate-key/oversized JSON and prohibited
nutrient quantities refuse; invalid spans persist NULL/inferred/span_mismatch.
A real quantity span cannot support a different numeric value. Complex quantity
phrases currently refuse rather than guess and still need the deterministic
quantity owner for complete coverage.

A capture lock and expected processing predecessor guard current application.
Stale outcomes retain their digest but write no fields. One savepoint covers the
processing event, outcome, fields and quarantine review. Three applied invalid
responses per transcript exhaust validation retries; the third enters
extraction_quarantined and queues review unless permanently dismissed. Successful
validation enters extracted, not enriched. Readback exposes stored fields and the
work queue selects resolve. No nutrition atoms or deterministic time resolution
are claimed by this stage. Dispatch-failure recovery now preserves validation retries; the separated runtime
supervisor remains to be connected before the end-to-end gate can close.

Independent review repaired hidden quarantine review selection, current-transcript
binding, split/prose nutrient quantities and partial count tokens. Numeric nutrient
labels require evidenced product/count support, otherwise refuse. This conservative
adapter still refuses some benign food language; deterministic quantity/reference
resolution must close that functional gap before full capture coverage is claimed.


## Deterministic resolution and integrity

The private resolve CLI consumes saved verified fields and invokes the existing
nutrition owner with cached references only. It cannot enable USDA/OFF network
fallback. A separate reference_egress role has allowlist/log access and no private
schema access; the process transport that uses this role remains to be connected.
This role definition and injected-transport tests alone do not prove process isolation.

Immutable resolved items bind extraction identity and item index to reference source,
serving evidence, time provenance and deterministic resolution. Atoms carry item and
whole/fraction component identity; retries cannot merge repeated equal food phrases
or duplicate an item's original components. Corrections still require supersession.
A newer extraction cannot silently replace previously persisted capture atoms.

Counts require a supported reference household mapping; unsupported units remain
pending. Fractional USDA Branded counts split labelled whole and portion-table
fractional components through the same computation owner. Triggers stamp event-time
and quantity provenance from the resolved item. Analysis excludes defaulted values,
time and quantity; nutrition-day discloses omitted components and never turns an
empty total into zero. Exact-item unresolved closure, atom persistence, processing
event and resolution outcome share one savepoint. Failure rolls back that boundary.

Local integration:929 SQL passes/1 production-only skip;1149 noDB passes/762 guarded
or dependency skips;82 migrations/815 statements; layout43. See PROGRESS for evidence
and scoped review. Full quantity language, isolated reference runtime, supervisor,
live provider/storage and device acceptance remain open under the same M3 unit.
