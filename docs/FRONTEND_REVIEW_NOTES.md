# Frontend review notes — 2026-09-09

Saved at Joe's request for later frontend planning. Review observations and
proposals only: this does not replace the execution plan, ratify a redesign,
change constitutional rules, or authorize a Lovable rebuild. Backend work continues
in the active build session. No live Lovable application or exported source was inspected.

## Material reviewed

- [Frontend plan](FRONTEND_PLAN.md)
- [Design brief](FRONTEND_DESIGN_BRIEF.md)
- [The File](THE_FILE.md)
- [Lovable starter](LOVABLE_FRONTEND.md) and [resume prompt](LOVABLE_RESUME.md)
- [L0](build/L0_lovable_round0.md) and [L8](build/L8_lovable_round8.md)
- [Current product intent](INTENT_COVERAGE.md)

## Preserve

Deep domain views with history, comparisons, related evidence and corrections;
an interconnected personal record; coherent phone/desktop design; readable
numbers; visible uncertainty, missingness and provenance. Reusable components
are useful, but domain-specific interactions should not be forced into identical
screens merely to save generation rounds.

## Findings to resolve before using the old prompts

1. LOVABLE_FRONTEND claims the backend is done and frozen. Revalidate every API
   against the actual implementation and deployment; do not repeat that claim.
2. The documents prescribe different names, navigation and screen sets. Establish
   one maintained frontend specification and clearly supersede old paste prompts.
3. L8 combines Ask, recommendations, trials, weekly reports, comparison and several
   domain modules in one late round. Split into testable user journeys; make the
   central intelligence interaction shape the design earlier.
4. Raw IDs and key/value trace sheets are developer diagnostics. Provide readable
   source evidence, explanation and revision history, with technical IDs underneath.
5. L0 treats absent/empty deviations as 'In your normal bands.' Distinguish
   verified normality from missing, stale, failed or uncomputed assessment.
6. Permission errors are treated universally as sign-in requests. Distinguish
   signed-out, unauthorized-owner and service/configuration failures.
7. 'Exactly one API call per screen' contradicts specified multi-call screens.
   Preserve server-owned calculations and authorized APIs; revisit the call-count
   restriction as a proposed design change, not a new rule applied silently.
8. Missing APIs can satisfy some round acceptance through empty states. Explicitly
   distinguish unavailable functionality from a working feature with no records.
   An empty state cannot close an unimplemented capability.
9. Old tier vocabulary must be reconciled with current RULE-16 and accepted display
   contracts. Lifecycle labels and evidence tiers must not be conflated.
10. Historical counts, claimed coverage and fixed date limits in prompts are not
    current product facts. Bind to verified response fields and actual coverage.

## Proposed first complete journey

Ask a question -> inspect its explanation -> inspect supporting and contradicting
evidence and alternatives -> correct an interpretation -> see its revision.

Include event time versus knowledge time, unknowns, source dependence, and what
additional evidence would distinguish explanations (REQ-REC-005..015). Preserve
current privacy, tier, chart and correction rules; any changes require the existing
decision process. Do not promise that a compelling finding exists in the data.

## Next frontend planning session

Consolidate the specification; confirm navigation and visual references with Joe;
map user journeys to current API contracts and acceptance evidence; then implement
one polished working journey before extending the domain views. Include responsive
layouts, keyboard/accessibility behavior, loading/errors, auth, and real integration
tests. Decide Lovable versus direct repository implementation after inspecting the
existing frontend source and integration options. No tool choice was made here.

## Verification limits

This is a document review, not an implementation audit or a backend status ledger.
No frontend code, production data, existing instructions or active checkpoint changed.
No requirement was marked complete and no architectural decision was ratified.
