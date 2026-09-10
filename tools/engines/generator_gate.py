"""B19 §F.1/§F.2 — generators generate, and the killed methods stay killed
(REQ-INF-400..413, 420..431).

Pure: no database, no network, no model. Every check takes its inputs.

WHY A GENERATOR IS ONLY EVER A GENERATOR (REQ-INF-400/401). PCMCI+, LPCMCI, VAR-LiNGAM,
DirectLiNGAM and regularized VAR all produce directed edges, and a directed edge LOOKS like a
finding. It is not one: it is a hypothesis with an arrow drawn on it. So every generator output
goes to `hypothesis_register` at CANDIDATE, and no code path turns one into a `findings` row --
because a `findings` row is what every surface in this system reads.

WHY A CANDIDATE ON A FINDING SURFACE IS A LOGGED VIOLATION (REQ-INF-403). "No finding available."
is the honest answer, and the log entry is what makes a leak visible rather than merely absent.
The EXPLORATORY surface is a different question and renders the same row happily -- the row is
not the problem, the surface is.

WHY THE COVERAGE FLOORS ARE HARD (REQ-INF-405/406). Below 200 well-covered days a generator will
still return edges; they will just be wrong, and they will arrive with a p-value. The floor is
not about statistical power in the abstract -- it is about a method that CANNOT REFUSE, so
something outside it has to.

WHY THE KILLED METHODS ARE KILLED (§F.2). Every one of them is published, cited and available,
and each fails specifically at n=1 on personal time series:

  * NOTEARS / DYNOTEARS and any scale-non-invariant continuous-optimization DAG learner --
    varsortability exceeds 0.94 on standard benchmarks, so the recovered graph is largely an
    artifact of the variables' UNITS. Change minutes to hours and the arrows move.
  * Convergent cross mapping and pyEDM/rEDM/skccm -- built for long deterministic dynamical
    systems, not for 2,400 noisy days of a person's life.
  * Model-X knockoffs -- requires the covariate distribution to be known.
  * GIMME-style stepwise modification-index search at n=1 -- a search over model modifications
    with no correction is a machine for producing significant paths.
  * GES / FGES -- score-based search whose output at this sample size is unstable to reordering.

REQ-INF-429 and 430 make those BUILD failures rather than review comments, because a method that
is merely discouraged gets used by whoever is in a hurry.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

GENERATORS = ("pcmci+", "lpcmci", "var-lingam", "directlingam", "regularized_var",
              "graphical_var")
MAX_BLOCK_VARIABLES = 20             # REQ-INF-404
GENERATOR_MIN_DAYS = 200             # REQ-INF-405
NONPARAMETRIC_MIN_DAYS = 500         # REQ-INF-406
NONPARAMETRIC_TESTS = ("cmiknn", "cmisymb")
DEFAULT_CI_TEST = "parcorr"          # REQ-INF-407
GPDC_MAX_VARIABLES = 3               # REQ-INF-407
TRANSFER_ENTROPY_MAX_VARIABLES = 3   # REQ-INF-425

# REQ-INF-429. Packages whose presence fails the build.
FORBIDDEN_PACKAGES = ("causalnex", "pyedm", "skccm", "redm")
# REQ-INF-430. Symbol names, case-insensitive.
FORBIDDEN_SYMBOLS = ("notears", "dynotears", "knockoff", "ccm")
# §F.2, by name, so a refusal cites the method rather than describing it.
KILLED_METHODS = {
    "notears": "REQ-INF-420",
    "dynotears": "REQ-INF-421",
    "dsem": "REQ-INF-423",
    "convergent_cross_mapping": "REQ-INF-424",
    "model_x_knockoffs": "REQ-INF-426",
    "gimme": "REQ-INF-427",
    "ges": "REQ-INF-428",
    "fges": "REQ-INF-428",
}

REFUSAL_STRING = "No finding available."      # REQ-INF-403


class GeneratorRefused(Exception):
    """A precondition that fails is a run that does not happen, not a run with a caveat."""


class KilledMethod(Exception):
    """§F.2. Named, with its requirement, so the refusal cites rather than describes."""


@dataclass(frozen=True)
class CandidateDestination:
    table: str = "hypothesis_register"
    status: str = "CANDIDATE"
    findings_row: bool = False


def register_output(edge, *, transformation, null_calibration):
    """REQ-INF-401/409/410. Every generator output, and what must travel with it.

    A directed edge LOOKS like a finding. It is a hypothesis with an arrow drawn on it, so it
    goes to the register at CANDIDATE and never becomes a `findings` row -- which is what every
    surface in this system reads.
    """
    if not transformation:
        raise GeneratorRefused(
            "REQ-INF-409: every series is detrended and deseasonalized before a generator run, "
            "and the transformation applied is recorded on the candidate")
    for k in ("discovery_count", "null_median", "null_p95"):
        if (null_calibration or {}).get(k) is None:
            raise GeneratorRefused(
                f"REQ-INF-410: a generator run is calibrated against a circular-shift null; "
                f"{k} is missing, so the discovery count has nothing to be compared against")
    return {**CandidateDestination().__dict__, "edge": edge,
            "transformation": transformation, "null_calibration": dict(null_calibration)}


def render_finding_surface(row):
    """REQ-INF-402/403. A CANDIDATE on a finding surface is a refusal AND a logged violation.

    The log entry is what makes a leak visible rather than merely absent: a surface that quietly
    shows nothing looks identical to a surface with nothing to show.
    """
    if row.get("status") == "CANDIDATE":
        return {"text": REFUSAL_STRING, "rendered": False,
                "rows": ({"table": "render_violations", "reason": "candidate_leak",
                          "hypothesis_id": row.get("hypothesis_id")},)}
    return {"row": row, "rendered": True, "rows": ()}


def render_exploratory_surface(row, *, surface_proven):
    """REQ-INF-402/413 with REQ-TIER-051. The same row, a different surface, no violation.

    The row is not the problem; the surface is. But the EXPLORATORY surface must exist and be
    proven first -- exploratory output is never pushed at Joe, and a generator shipped before its
    label surface has nowhere labelled to put its output.
    """
    if not surface_proven:
        return {"rendered": False,
                "reason": ("REQ-TIER-051: the EXPLORATORY surface is not built and proven; the "
                           "label surface precedes the generation that feeds it")}
    if row.get("status") != "CANDIDATE":
        # REQ-TIER-053. It sources CANDIDATE rows and renders no row of any other status.
        return {"rendered": False,
                "reason": "the EXPLORATORY surface renders CANDIDATE rows and nothing else"}
    return {"rendered": True, "label": "EXPLORATORY", "row": row, "pushed": False}


def prompt_payload(rows):
    """REQ-INF-402. A candidate never enters a language-layer prompt as established fact.

    This is the quietest of the three leaks and the worst: a model handed a candidate edge will
    write a sentence about it in the same voice it uses for a confirmed one.
    """
    leaked = [r for r in rows if r.get("status") == "CANDIDATE"]
    if leaked:
        raise GeneratorRefused(
            f"REQ-INF-402: {len(leaked)} CANDIDATE row(s) in a language-layer prompt; a model "
            f"handed a candidate edge writes about it in the same voice it uses for a confirmed "
            f"finding")
    return tuple(rows)


def check_run(*, variables, well_covered_days, ci_test=DEFAULT_CI_TEST, method="pcmci+",
              on_demand=False, surface_proven=True):
    """REQ-INF-404..407, 412. Every precondition, applied identically to scheduled and on-demand.

    REQ-INF-412 is explicit that an on-demand run applies "every precondition and floor of the
    method it invokes exactly as the scheduled run of that method would". So there is ONE
    function and `on_demand` changes nothing about the floors -- it only adds the RULE-17 gate.
    """
    problems = []
    if method.lower() in KILLED_METHODS:
        raise KilledMethod(f"{KILLED_METHODS[method.lower()]}: {method} is not available")
    if len(variables) > MAX_BLOCK_VARIABLES:
        problems.append(f"REQ-INF-404: {len(variables)} variables; a generator runs on domain "
                        f"blocks of at most {MAX_BLOCK_VARIABLES}, never the full metric space "
                        f"in one pass")
    if well_covered_days < GENERATOR_MIN_DAYS:
        problems.append(f"REQ-INF-405: {well_covered_days} well-covered days is below "
                        f"{GENERATOR_MIN_DAYS}; below this a generator still returns edges, they "
                        f"are just wrong, and they arrive with a p-value")
    if ci_test.lower() in NONPARAMETRIC_TESTS and well_covered_days < NONPARAMETRIC_MIN_DAYS:
        problems.append(f"REQ-INF-406: {ci_test} needs {NONPARAMETRIC_MIN_DAYS} well-covered "
                        f"days; there are {well_covered_days}")
    if ci_test.lower() == "gpdc" and len(variables) > GPDC_MAX_VARIABLES:
        problems.append(f"REQ-INF-407: GPDC is reserved for a confirmatory subset of at most "
                        f"{GPDC_MAX_VARIABLES} variables; this run has {len(variables)}")
    if on_demand and not surface_proven:
        problems.append("REQ-INF-412 / REQ-TIER-051: an on-demand run is exploration and does "
                        "not run before the EXPLORATORY surface is built and proven")
    if problems:
        raise GeneratorRefused("; ".join(problems))
    return {"allowed": True, "ci_test": ci_test, "n_variables": len(variables),
            "on_demand": on_demand}


def corroboration_only(candidate):
    """REQ-INF-408/411. A VAR-family edge corroborates; it never promotes on its own.

    The idiographic-network literature is the reason and it is worth carrying: across 43 studies
    the median series length was 99, 8.8% tested normality, 11.6% evaluated stability and 7% were
    preregistered. A single edge from a regularized VAR fit is a hypothesis.
    """
    src = (candidate.get("source_method") or "").lower()
    if src in ("var-lingam", "regularized_var", "graphical_var"):
        if not candidate.get("pcmci_also_produced"):
            return {"may_promote": False,
                    "reason": ("REQ-INF-408: a VAR-family edge is corroboration only and may not "
                               "promote a candidate that PCMCI+ did not also produce")}
    return {"may_promote": True}


def on_demand_outcome(run):
    """REQ-INF-413. Exploration only: no findings row, no promotion, no confirmation job.

    The waiting clock is untouched, and the reason is structural rather than procedural: the
    confirmation job reads only observations at or after `confirmation_data_from`, which is set
    to now() at registration. An on-demand run over pre-existing data cannot confirm anything
    whatever fires it.
    """
    return {"destination": CandidateDestination().__dict__,
            "findings_row": False, "may_promote": False, "triggers_confirmation": False,
            "note": ("The confirmation job reads only observations at or after "
                     "confirmation_data_from, set to now() at registration, so a run over "
                     "pre-existing data cannot confirm a hypothesis whatever fires it.")}


# ---------------------------------------------------------------- §F.2 the killed methods

def check_method(name):
    """§F.2. Refused by name, citing the requirement."""
    key = str(name).lower().replace(" ", "_").replace("-", "_")
    if key in KILLED_METHODS:
        raise KilledMethod(f"{KILLED_METHODS[key]}: {name} is not available in this system")
    return True


def check_transfer_entropy(n_variables):
    """REQ-INF-425. At most three variables."""
    if n_variables > TRANSFER_ENTROPY_MAX_VARIABLES:
        raise KilledMethod(f"REQ-INF-425: multivariate transfer entropy on {n_variables} "
                           f"variables; the limit is {TRANSFER_ENTROPY_MAX_VARIABLES}")
    return True


def check_dag_learner(*, continuous_optimization, scale_invariant):
    """REQ-INF-422. Scale non-invariance is the disqualifier, not the family.

    Varsortability exceeds 0.94 on standard benchmarks, so the recovered graph is largely an
    artifact of the variables' UNITS: change minutes to hours and the arrows move. A learner that
    IS scale-invariant is not caught by this rule, which is why the check asks about the property
    rather than about a name.
    """
    if continuous_optimization and not scale_invariant:
        raise KilledMethod(
            "REQ-INF-422: a continuous-optimization DAG learner whose objective is scale "
            "non-invariant; varsortability exceeds 0.94 on standard benchmarks and the recovered "
            "graph is largely an artifact of the variables' units")
    return True


def check_dependencies(packages):
    """REQ-INF-429. A BUILD failure, not a review comment.

    A method that is merely discouraged gets used by whoever is in a hurry.
    """
    found = tuple(sorted(p for p in packages
                         if str(p).lower().replace("-", "").replace("_", "")
                         in FORBIDDEN_PACKAGES))
    if found:
        raise KilledMethod(f"REQ-INF-429: the dependency set resolves {list(found)}; the build "
                           f"fails rather than warning")
    return True


def check_imports(source, *, where=""):
    """REQ-INF-430. Any imported symbol matching the four names, case-insensitively."""
    hits = []
    for m in re.finditer(r"^\s*(?:from|import)\s+([\w\.]+)(?:\s+import\s+([\w\s,\*]+))?",
                         source or "", re.M):
        blob = " ".join(x for x in m.groups() if x).lower()
        for sym in FORBIDDEN_SYMBOLS:
            if sym in blob:
                hits.append(sym)
    if hits:
        raise KilledMethod(f"REQ-INF-430: {sorted(set(hits))} imported in {where or 'a module'}; "
                           f"the build fails")
    return True


def check_search_scope(*, all_pairs, registry_constrained, hierarchical_fdr):
    """REQ-INF-431. An unrestricted all-pairs search needs both guards or it does not run.

    Without the registry's direction constraints every pair is tested in both directions, and
    without the hierarchical FDR tree the family size is the square of the metric count. Together
    those turn a scan into a machine for producing significant results.
    """
    if all_pairs and not (registry_constrained and hierarchical_fdr):
        missing = [n for n, v in (("metric_registry direction constraints", registry_constrained),
                                  ("the hierarchical FDR tree", hierarchical_fdr)) if not v]
        raise GeneratorRefused(
            f"REQ-INF-431: an all-pairs search across the full metric space without "
            f"{' and '.join(missing)}")
    return True
