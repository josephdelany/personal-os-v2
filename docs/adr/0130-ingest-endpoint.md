# ADR-0130 — Store first, enrich second

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-CAP-003..005, 007, 008, 010..018
**Implements:** B16 §A.1–§A.4, the ingest endpoint contract. Fourteen requirements.
REQ-CAP unproven 34 → 20.

## The ordering that is the contract

Authenticate → validate identity → **insert** → enrich.

REQ-CAP-011: the `raw_captures` row lands **before** any Workers AI call, and the 202 is returned
once *that insert* commits — not once the enrichment succeeds. Everything downstream is a
recomputable view over the raw capture; **the capture is not.** A capture lost while waiting for
a model is lost permanently, and **the model is the least reliable thing in the path.**

## The client owns the identity

REQ-CAP-018. The Shortcut generates `capture_id` before the first attempt, so **the same id
survives a timeout, a queue and an hourly replay.** Generating it server-side would give every
retry a new identity — and the offline queue **retries by design**, so it would duplicate every
capture it ever held.

`ON CONFLICT (capture_id) DO NOTHING`, then a 200 with `{"status":"duplicate"}`, closes the loop:
the Shortcut learns the capture is safe, removes the line from its queue, and **no second
enrichment job is enqueued for work already done.**

## Two refusals that read as small and are not

**A bad token means the body is never read** (REQ-CAP-008). Parsing an unauthenticated body is
doing work on behalf of whoever sent it — **and the body of a capture request is audio.**

**A rejected request keeps its raw body** (REQ-CAP-007). A rejected capture is still the only copy
of whatever it was, and **a rejection with no body cannot be replayed after the fix.**

## The PWA is a surface, not a second capture path

REQ-CAP-005 allows exactly two writable fields. The constraint is what keeps the PWA a *rendering*
of data captured elsewhere — and **a second capture path is a second set of rules to keep in step
with the first.**

REQ-CAP-004 permits only `<input type="file" accept="image/*" capture="environment">`. That hands
the OS camera the job and gives the PWA the result: **it never holds a stream and cannot be left
recording**, which `getUserMedia` can be when a page is backgrounded badly.

REQ-CAP-010 resizes **before** upload, because bytes that never leave the phone cost nothing on
the bad connection — and **a capture on a bad connection is the one most likely to time out into
the offline queue.**

## The correction never touches the capture

REQ-CAP-013/014. **The transcript is the evidence.** A correction supersedes the *derived* row and
leaves the capture untouched, so *"what did Joe actually say"* survives every later opinion about
what he meant.

REQ-CAP-015 records `model_id` **and** `prompt_version` on every extracted row: **a different
model and a reworded prompt produce the same kind of drift, and only these two fields tell them
apart.**

## Verification

14 tests. Requirements proven 611 → 625 (91%).

Not claimed: no endpoint exists. This is the contract one will be held to, and it is the same
shape as `capture_resilience.py`'s — that module covers what happens when the network fails, this
one what happens when the request arrives.
