# ADR-0120 — Generators generate, and the killed methods stay killed

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-INF-400..413 (§F.1), REQ-INF-420..431 (§F.2)
**Implements:** B19's generator discipline. Twenty-six requirements.

## The distinction the whole section protects

PCMCI+, LPCMCI, VAR-LiNGAM, DirectLiNGAM and regularized VAR all produce directed edges, and **a
directed edge looks like a finding.** It is not one: it is a hypothesis with an arrow drawn on it.

So every generator output goes to `hypothesis_register` at `CANDIDATE`, and no code path turns
one into a `findings` row — because **a `findings` row is what every surface in this system
reads.**

There are three ways a candidate leaks, and each is closed separately:

1. **A finding surface** (REQ-INF-403) — returns *"No finding available."* **and writes a
   `render_violations` row.** The log entry is the point: a surface that quietly shows nothing
   looks identical to a surface with nothing to show.
2. **The EXPLORATORY surface** — not a leak. The same row renders happily under its label,
   because **the row is not the problem, the surface is.** It is never *pushed* at Joe.
3. **A language-layer prompt** (REQ-INF-402) — the quietest of the three and the worst. **A model
   handed a candidate edge writes about it in the same voice it uses for a confirmed finding.**

## Why the floors are hard, not advisory

Below 200 well-covered days a generator **still returns edges. They are just wrong, and they
arrive with a p-value.** The floor is not about statistical power in the abstract — it is about a
method that *cannot refuse*, so something outside it has to.

REQ-INF-412 is explicit that an on-demand run applies *"every precondition and floor of the method
it invokes exactly as the scheduled run of that method would"*. So there is **one** `check_run`
and `on_demand` changes nothing about the floors — it only adds the RULE-17 surface gate.

## Why the killed methods are killed

Every one is published, cited and available, and each fails specifically at n=1 on personal time
series:

| method | why |
|---|---|
| NOTEARS / DYNOTEARS, and any scale-non-invariant continuous DAG learner | **varsortability exceeds 0.94** on standard benchmarks — the recovered graph is largely an artifact of the variables' *units*. Change minutes to hours and the arrows move. |
| convergent cross mapping, pyEDM / rEDM / skccm | built for long deterministic dynamical systems, not 2,400 noisy days of a person's life |
| Model-X knockoffs | requires the covariate distribution to be known |
| GIMME-style stepwise modification-index search at n=1 | a search over model modifications with no correction is a machine for producing significant paths |
| GES / FGES | score-based search whose output at this sample size is unstable to reordering |

**REQ-INF-422 checks the property, not the name.** Scale non-invariance is the disqualifier, so a
continuous-optimization learner that *is* scale-invariant passes — the rule is about the defect,
not about a family.

**REQ-INF-429/430 are build failures, not review comments**, because a method that is merely
discouraged gets used by whoever is in a hurry. A test runs `check_imports` over every file in
`tools/` to enforce "anywhere in the codebase" literally.

## The VAR corroboration rule

REQ-INF-408/411: a VAR-family edge may not promote a candidate PCMCI+ did not also produce. The
justification is carried in the code because it is worth carrying — across **43 idiographic-network
studies the median series length was 99, 8.8% tested normality, 11.6% evaluated stability, and 7%
were preregistered.**

## Verification

25 tests. Requirements proven 429 → 450 (66%); REQ-INF unproven 100 → 81.

Not claimed: no generator is wired. `tigramite` and the LiNGAM packages are not dependencies, and
adding them would need the ADR-0103 treatment — installed and exercised before adoption.
