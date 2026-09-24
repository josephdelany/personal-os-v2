# ADR-0162 — Prioritize a usable program

Date: 2026-09-23. Status: accepted user goal; implementation in progress.

Joe replaced the complete-backend-first goal with bringing him to a usable program,
prioritizing usability and leaving complicated capture flows for later. This changes
delivery order: work on the existing browser app and its required backend now.
The earlier prohibition on frontend work before M6 no longer determines selection
for this goal. It does not authorize production writes, publishing or weaker integrity.

Build on app/index.html and its existing Supabase owner authentication. First connect
the existing deterministic Ask RPC, preserving stored answers, evidence, uncertainty
and missing-data refusals. No client computations, new model calls, dependency or fee.
Keep advanced voice/camera/correction work preserved and paused. Full backend M6
requirements remain open; they are not the stopping condition for this replacement goal.

Usable means an accessible app, successful owner sign-in, representative real-data
answers/reads and explicit unavailable states, with a tested deployment and usage
instructions. Local rendering tests alone cannot establish that. Prepare exact
deployment changes before requesting any necessary production authorization.

Read-only GitHub inspection found the default branch is v2-day1 while Pages triggers
only on main. Add v2-day1 to that workflow and verify the Ask interaction before upload.
The configured Pages URL is https://josephdelany.github.io/personal-os-v2/ . This is
configuration evidence, not proof that the changed app is deployed or owner auth works.

Current scope excludes enabling new exploratory analysis, advanced capture and
invented data. Existing production DB authentication hold remains unverified; do not
send Joe's credentials through chat or repeat an unchanged failing probe.
