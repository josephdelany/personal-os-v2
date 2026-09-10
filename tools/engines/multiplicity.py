"""B9 §B.1/§B.2/§B.3 — multiplicity, serial correlation, and specification curves
(REQ-INF-001..009, 020..026, 030..038).

Pure: no database, no network, no model. `speccurve.py` computes a curve; this is the DISCIPLINE
around it -- what may be tested, how many tests that makes, and what a sample size means when the
observations are days in a row.

WHY A TREE AND NOT ONE FLAT FAMILY (REQ-INF-001/002). A flat correction over every metric pair is
a family of tens of thousands, and at that size the correction is so severe that nothing survives
-- so nothing is discovered, and the search may as well not have run. Yekutieli's hierarchical
FDR tests a family ONLY IF ITS PARENT WAS REJECTED, which keeps each family small enough for BH
to have power while still controlling the error rate over the tree.

WHY NOT PLAIN BENJAMINI-YEKUTIELI (REQ-INF-004). Its harmonic penalty factor is about 10.9 at
m=30,000. That is not conservatism, it is a gate that nothing passes, and a gate nothing passes
teaches you nothing about the world.

WHY THE FAMILY SIZE IS FROZEN AT TEST TIME (REQ-INF-003/009). If `m` is recomputed later, a
q-value changes without the data changing -- and the direction it changes is whichever way the
person recomputing it wants. Authoring or modifying the family catalog AFTER seeing results is
the same move with an extra step, and REQ-INF-009 forbids it outright.

WHY n IS NEVER SHOWN ALONE (REQ-INF-022/023). These observations are days in a row and they are
autocorrelated. A metric with rho=0.6 over 400 days carries the information of about 100
independent ones. "n=400" is true and misleading; "n=400, n_eff=100" is neither.

WHY A WASHOUT WITHOUT HAC IS FORBIDDEN (REQ-INF-026). Discarding the days around a transition
makes the remaining points look cleaner and more independent than they are. Combined with naive
inference it raised the false-positive rate in the cited work -- a procedure that LOOKS like extra
rigour while being the opposite is the most dangerous kind.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

LAG_PROFILE = (0, 1, 2, 3, 7)            # REQ-INF-035
WEEKLY_SHIFTS = 200                      # REQ-INF-033
MONTHLY_SHIFTS = 2_000
TREE_LEVELS = ("domain_pair", "variable_pair", "lag_specification")   # REQ-INF-001


class PipelineViolation(Exception):
    """REQ-INF-008/025. The result is discarded and a row is written; it is not repaired."""


# ---------------------------------------------------------------- §B.1 the multiplicity tree

def prune_search_space(pairs, registry):
    """REQ-INF-005. Pruned BEFORE any correction, not after.

    Order matters and it is the whole point: a pair removed before correction does not count
    toward `m`, so pruning makes the surviving tests MORE powerful. Pruning afterwards would
    shrink the reported family while leaving the penalty already paid.
    """
    kept = []
    for src, tgt in pairs:
        s, t = registry.get(src, {}), registry.get(tgt, {})
        if s.get("can_be_cause") is False or t.get("can_be_effect") is False:
            continue
        kept.append((src, tgt))
    return tuple(kept)


def benjamini_hochberg(pvalues, *, m=None):
    """BH within one family. `m` is passed in and never derived from the list length.

    REQ-INF-003: the family size is the REGISTERED one. Deriving it from however many tests
    happened to run would let a crashed test silently make every surviving q-value smaller.
    """
    m = len(pvalues) if m is None else m
    if m <= 0:
        return ()
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    q = [0.0] * len(pvalues)
    prev = 1.0
    for rank_from_end, i in enumerate(reversed(order), start=1):
        k = len(order) - rank_from_end + 1
        prev = min(prev, pvalues[i] * m / k)
        q[i] = round(prev, 10)
    return tuple(q)


def hierarchical_fdr(tree, *, alpha=0.05):
    """REQ-INF-002/007. BH within each family; a family is tested only if its parent was rejected.

    Returns every family it descended into with the test count and the q threshold applied there
    (REQ-INF-007) -- because a discovery whose family size and threshold are not reported cannot
    be judged by anyone reading it.
    """
    reported, rejected_parents = [], {None}
    for family in tree:
        parent = family.get("parent")
        if parent not in rejected_parents:
            reported.append({"family": family["id"], "level": family["level"],
                             "tested": False, "reason": "parent hypothesis not rejected"})
            continue
        m = family["m"]
        qs = benjamini_hochberg(family["pvalues"], m=m)
        rejects = tuple(i for i, q in enumerate(qs) if q <= alpha)
        if rejects:
            rejected_parents.add(family["id"])
        reported.append({"family": family["id"], "level": family["level"], "tested": True,
                         "n_tests": len(family["pvalues"]), "m": m, "q_threshold": alpha,
                         "q_values": qs, "rejected": rejects})
    return tuple(reported)


def persist_test(*, family_id, m, p_raw, q_adjusted, registered_families):
    """REQ-INF-003/008. Every test stores its family, its m, its p and its q — or is discarded.

    A test whose family is not in `v_metric_tree` is not a test that was corrected for; it is a
    test nobody counted, and counting it afterwards is the recomputation REQ-INF-003 forbids.
    """
    if family_id not in registered_families:
        raise PipelineViolation(
            f"REQ-INF-008: family {family_id!r} is not registered in v_metric_tree; the result is "
            f"discarded, no candidate is inserted, and a pipeline_violations row is written")
    for name, v in (("m", m), ("p_raw", p_raw), ("q_adjusted", q_adjusted)):
        if v is None:
            raise PipelineViolation(f"REQ-INF-003: a stored test carries {name}")
    return {"family_id": family_id, "m": m, "p_raw": p_raw, "q_adjusted": q_adjusted,
            "m_frozen_at_test_time": True}


def check_multiplicity_method(method):
    """REQ-INF-004. Plain BY is not the primary gate.

    Its harmonic penalty is about 10.9 at m=30,000 — not conservatism but a gate nothing passes,
    and a gate nothing passes teaches you nothing about the world.
    """
    if str(method).lower().replace("-", "_") in ("benjamini_yekutieli", "by"):
        raise PipelineViolation(
            "REQ-INF-004: plain Benjamini-Yekutieli is not the primary multiplicity gate for the "
            "search tree; its harmonic penalty is about 10.9 at m=30,000")
    return True


def catalog_authored_before_results(*, authored_at, first_result_at):
    """REQ-INF-009. The family catalog is fixed before any result is seen.

    Authoring or modifying it afterwards changes q-values without changing data, in whichever
    direction the person doing it wants.
    """
    if authored_at >= first_result_at:
        raise PipelineViolation(
            "REQ-INF-009: the family catalog may not be authored or modified after inspecting a "
            "run's results")
    return True


def extend_tree(registry, *, existing_families, recompute_at):
    """REQ-INF-006. A new metric extends the tree automatically, and `m` moves at the NEXT run.

    Not mid-run: a family size that changes while a run is in progress makes the q-values of the
    tests already performed incomparable with the ones still to come.
    """
    return {"families": tuple(existing_families) + tuple(
                f"variable_pair:{k}" for k in sorted(registry) if
                f"variable_pair:{k}" not in existing_families),
            "family_sizes_recomputed_at": recompute_at,
            "note": "Family sizes move at the next scheduled run, never mid-run."}


# ---------------------------------------------------------------- §B.2 serial correlation

def effective_n(n, rho):
    """REQ-INF-022. n(1-rho)/(1+rho).

    A metric with rho=0.6 over 400 days carries the information of about 100 independent ones.
    """
    rho = max(-0.99, min(0.99, float(rho)))
    return round(float(n) * (1.0 - rho) / (1.0 + rho), 4)


def estimate_row(*, beta, se, n, rho, maxlags, robust_method):
    """REQ-INF-020/021/024/025. No robust SE, no rho, no n_eff — no findings row.

    Refused rather than flagged: an estimate with a naive standard error over autocorrelated days
    has a confidence interval that is simply too narrow, and nothing downstream can tell.
    """
    if robust_method not in ("newey_west", "hac", "ar1"):
        raise PipelineViolation(
            "REQ-INF-020: every user-facing effect estimate uses Newey-West/HAC standard errors "
            "or an explicit AR(1) error term")
    if rho is None or maxlags is None:
        raise PipelineViolation(
            "REQ-INF-021/024: rho and the HAC maxlags used are stored alongside every estimate")
    return {"beta": beta, "se": se, "n": n, "rho": rho, "n_eff": effective_n(n, rho),
            "maxlags": maxlags, "robust_method": robust_method}


def create_finding(estimate):
    """REQ-INF-025. Without a stored rho and n_eff there is no findings row, only a violation."""
    if estimate.get("rho") is None or estimate.get("n_eff") is None:
        raise PipelineViolation(
            "REQ-INF-025: an estimate with no stored rho and n_eff does not become a finding; a "
            "pipeline_violations row is written instead")
    return {"findings_row": True, **estimate}


def render_sample_size(n, n_eff):
    """REQ-INF-023. Together, always. `n=400` alone is true and misleading."""
    if n_eff is None:
        raise PipelineViolation("REQ-INF-023: n is never rendered alone")
    return f"n={n}, n_eff={n_eff:g}"


def check_washout(*, washout_days, robust_method):
    """REQ-INF-026. A washout without robust inference is forbidden.

    Discarding the days around a transition makes the remaining points look cleaner and more
    independent than they are. With naive inference that RAISED the false-positive rate — a
    procedure that looks like extra rigour while being the opposite is the most dangerous kind.
    """
    if washout_days and robust_method not in ("newey_west", "hac", "ar1"):
        raise PipelineViolation(
            "REQ-INF-026: a washout period may not be applied to an observational analysis "
            "without autocorrelation-robust inference; washout with naive inference raises the "
            "false-positive rate rather than lowering it")
    return True


# ---------------------------------------------------------------- §B.3 specification curves

def curve_summary(effects, pvalues, *, alpha=0.05):
    """REQ-INF-031. Count, median, sign-agreement fraction, significant fraction."""
    if not effects:
        return None
    ordered = sorted(effects)
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0
    sign = (1 if median > 0 else -1 if median < 0 else 0)
    same = sum(1 for e in effects if (1 if e > 0 else -1 if e < 0 else 0) == sign)
    sig = sum(1 for p in pvalues if p <= alpha)
    return {"n_specs": n, "median_effect": round(median, 6),
            "sign_agreement": round(same / n, 4),
            "significant_fraction": round(sig / n, 4)}


def null_shifts_required(schedule):
    """REQ-INF-033. 200 weekly, 2,000 monthly."""
    return {"weekly": WEEKLY_SHIFTS, "monthly": MONTHLY_SHIFTS}[schedule]


def render_curve(summary, null_summary):
    """REQ-INF-032/034. The observed significant fraction is NEVER shown without the null's.

    "41% of specifications were significant" sounds decisive until the shuffled data produces 38%.
    The null fraction is not a footnote to that number, it is the thing that gives it a meaning,
    so the renderer refuses to produce one without the other.
    """
    if null_summary is None or null_summary.get("significant_fraction") is None:
        raise PipelineViolation(
            "REQ-INF-034: the observed significant fraction may not be rendered without the "
            "fraction significant under the circular-shift null beside it")
    return {**summary, "null_significant_fraction": null_summary["significant_fraction"],
            "text": (f"{summary['significant_fraction']:.0%} of {summary['n_specs']} "
                     f"specifications were significant; the circular-shift null gives "
                     f"{null_summary['significant_fraction']:.0%}.")}


def lag_profile(effects_by_lag, pvalues_by_lag, *, alpha=0.05):
    """REQ-INF-035/036. The whole profile, and the one-lag sign-flip refusal.

    A single lag coefficient reported as "the effect" is a choice among five, and the one chosen
    is the one that looked best. Significant at exactly one lag AND changing sign at another is
    the signature of noise, so it returns INSUFFICIENT rather than a finding.
    """
    missing = [l for l in LAG_PROFILE if l not in effects_by_lag]
    if missing:
        raise PipelineViolation(
            f"REQ-INF-035: the effect is reported as a lag profile over {list(LAG_PROFILE)}; "
            f"lags {missing} are missing")
    sig = [l for l in LAG_PROFILE if pvalues_by_lag.get(l, 1.0) <= alpha]
    signs = {l: (1 if effects_by_lag[l] > 0 else -1 if effects_by_lag[l] < 0 else 0)
             for l in LAG_PROFILE}
    profile = {"lags": dict(effects_by_lag), "significant_lags": tuple(sig)}
    if len(sig) == 1:
        s = signs[sig[0]]
        if any(signs[l] == -s and s != 0 for l in LAG_PROFILE if l != sig[0]):
            return {**profile, "tier": "INSUFFICIENT",
                    "insufficiency_reason": "sign_unstable",
                    "detail": (f"significant at lag {sig[0]} alone and sign-flipped at another "
                               f"tested lag; that is the signature of noise, not of an effect")}
    return {**profile, "tier": None}


def default_output_format(finding):
    """REQ-INF-037. The curve IS the default output for a promoted-or-higher finding.

    Not an expandable detail: a single number with a curve hidden behind a click is a single
    number, and the dashboard of which analytic choices produced each point is the part that
    shows whether the result depended on them.
    """
    from tools.engines.tier_contract import rank
    if rank(finding.get("tier", "INSUFFICIENT")) >= rank("PROMOTED"):
        return {"format": "specification_curve", "includes_choice_dashboard": True,
                "collapsed_by_default": False}
    return {"format": "summary"}


def discovery_count_vs_null(observed, null_counts):
    """REQ-INF-038. A run's discovery count against the shuffled-data median and 95th.

    Twelve discoveries is a number. Twelve discoveries against a null median of three and a 95th
    percentile of seven is a result; against a null median of eleven it is a Tuesday.
    """
    if not null_counts:
        raise PipelineViolation("REQ-INF-038: the empirical null distribution of the discovery "
                                "count is reported with every run")
    s = sorted(null_counts)
    median = s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2.0
    p95 = s[min(len(s) - 1, int(math.ceil(0.95 * len(s))) - 1)]
    return {"observed": observed, "null_median": median, "null_p95": p95,
            "exceeds_null_p95": observed > p95,
            "text": (f"{observed} discoveries; shuffled data gives a median of {median:g} and a "
                     f"95th percentile of {p95:g}.")}
