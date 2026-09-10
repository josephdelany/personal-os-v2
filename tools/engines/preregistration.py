"""B9 §C/§G.1 — pre-registration as a database constraint, and the registry that drives it
(REQ-INF-100..114, 500..508).

Pure: no database, no clock, no model. The constraints these functions mirror live in migrations
0010 and 0012; this is the Python side and the reasoning that goes with it.

WHY PRE-REGISTRATION IS A CONSTRAINT AND NOT A CONVENTION. The difference between a discovery and
a story is entirely a matter of WHEN the claim was written down. Every part of the analysis --
the lag, the direction, the transformation, the adjustment set, the test statistic -- can be
chosen after seeing the data, and each choice is defensible on its own. Choosing all of them
after the fact is how a null result becomes a finding without anybody lying.

So the register stores those choices with `preregistered_at`, and `confirmation_data_from` is set
to now() at registration. After that the arithmetic does the work: the confirmation job can only
read observations from AFTER the moment the claim was fixed.

WHY `ingested_at` MATTERS AS MUCH AS `subject_day` (REQ-INF-104/105). A row about last Tuesday
that arrived today is not post-registration data -- it is old data that showed up late, and a
backfill can deliver thousands of them. Filtering on `subject_day` alone would let a single
import silently supply the entire confirmation window. Both clocks, or neither.

WHY A REFUTATION IS SURFACED RATHER THAN DELETED (REQ-INF-111). A register that quietly drops its
failures reports a success rate of 100% and means nothing. The refutations are the only evidence
that the confirmation gate does anything at all.

WHY MISSING IS NEVER IMPUTED (REQ-INF-110). An imputed value is indistinguishable from a measured
one once it is in the matrix, and the imputation model's assumptions become the finding's
assumptions without appearing anywhere in its provenance.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

# REQ-INF-100. What a registration must fix before any confirming data exists.
REGISTER_FIELDS = ("hypothesis_id", "exposure_metric", "outcome_metric", "lag_days",
                   "direction", "transformation", "adjustment_set", "test_statistic",
                   "preregistered_at", "confirmation_data_from", "resolution_rule", "status")

# REQ-INF-504. Exactly three, and no other reach into storage.
INFERENCE_INTERFACES = ("f_daily_panel", "v_metric_tree", "v_coverage")

E_VALUE_FLOOR = 1.5           # REQ-INF-112


class PreregistrationViolation(Exception):
    """Mirrors a CHECK constraint or a trigger: the write does not happen."""


class ConfirmationAborted(Exception):
    """REQ-INF-105. Aborted and logged, never downgraded to a weaker claim."""


def register(**kw):
    """REQ-INF-100/101/102. Every choice fixed, and the two clocks set together."""
    missing = [f for f in REGISTER_FIELDS if f not in kw]
    if missing:
        raise PreregistrationViolation(
            f"REQ-INF-100: a registration fixes {missing} too; a claim whose lag, direction, "
            f"transformation, adjustment set or test statistic is still open can be chosen after "
            f"the data is seen, and each such choice is defensible on its own")
    if kw["confirmation_data_from"] < kw["preregistered_at"]:
        # REQ-INF-102, as a CHECK. Confirming data that predates the registration is the data the
        # hypothesis was mined from.
        raise PreregistrationViolation(
            "REQ-INF-102: confirmation_data_from >= preregistered_at")
    return dict(kw)


def promote_to_registered(hypothesis, *, now):
    """REQ-INF-101. Both clocks are `now()` at promotion, not a window chosen afterwards."""
    return register(**{**hypothesis, "status": "PROMOTED",
                       "preregistered_at": now, "confirmation_data_from": now})


def confirmation_rows(rows, *, confirmation_data_from):
    """REQ-INF-104/105. Both clocks, or the confirmation aborts.

    A row about last Tuesday that arrived today is not post-registration data — it is old data
    that showed up late, and a backfill can deliver thousands of them at once. Filtering on
    `subject_day` alone would let a single import silently supply the entire confirmation window.
    """
    leaked = [r for r in rows if r["ingested_at"] < confirmation_data_from]
    if leaked:
        raise ConfirmationAborted(
            f"REQ-INF-105: {len(leaked)} row(s) with ingested_at before "
            f"{confirmation_data_from}; the confirmation is aborted, no tier above PROMOTED is "
            f"assigned, and a pipeline_violations row is written")
    return tuple(r for r in rows
                 if r["subject_day"] >= confirmation_data_from.date()
                 and r["ingested_at"] >= confirmation_data_from)


def confirmation_family(hypotheses, *, run_id):
    """REQ-INF-106. BH across the hypotheses evaluated in THIS run, family size persisted.

    Persisted because the family a q-value was computed in is not recoverable afterwards: two
    runs of different sizes produce different q-values from identical p-values, and without the
    stored size nobody can tell which one they are looking at.
    """
    return {"run_id": run_id, "family_size": len(hypotheses),
            "hypothesis_ids": tuple(h["hypothesis_id"] for h in hypotheses),
            "method": "benjamini_hochberg", "persisted": True}


def no_imputation(series):
    """REQ-INF-110. Missing stays missing, and is modelled where the analysis needs it.

    An imputed value is indistinguishable from a measured one once it is in the matrix, and the
    imputation model's assumptions become the finding's assumptions without appearing anywhere
    in its provenance.
    """
    return {"values": tuple(series),
            "n_missing": sum(1 for v in series if v is None),
            "imputed": False,
            "missingness_modelled_explicitly": True}


def refute(hypothesis, *, reason):
    """REQ-INF-111. REFUTED, and surfaced rather than deleted.

    A register that quietly drops its failures reports a success rate of 100% and means nothing.
    The refutations are the only evidence that the confirmation gate does anything at all.
    """
    return {**hypothesis, "status": "REFUTED", "reason": reason,
            "surfaced_to_joe": True, "deleted": False}


def confirmation_ceiling(*, e_value_at_limit, has_minimal_adjustment_set):
    """REQ-INF-112. Below an E-value of 1.5, or with no minimal sufficient adjustment set,
    the hypothesis stays at PROMOTED.

    The E-value at the interval limit nearest the null is the honest question: how strong would
    an unmeasured confounder have to be to explain this away? Below 1.5, the answer is "not very",
    and no amount of process makes that a confirmed observational finding.
    """
    if e_value_at_limit is None or e_value_at_limit < E_VALUE_FLOOR:
        return {"max_tier": "PROMOTED",
                "reason": (f"E-value at the limit nearest the null is "
                           f"{e_value_at_limit if e_value_at_limit is not None else 'unknown'}, "
                           f"below {E_VALUE_FLOOR}: a modest unmeasured confounder would explain "
                           f"this away")}
    if not has_minimal_adjustment_set:
        return {"max_tier": "PROMOTED",
                "reason": ("no minimal sufficient adjustment set exists for this DAG, so what "
                           "was adjusted for is not what the DAG says must be")}
    return {"max_tier": "CONFIRMED_OBSERVATIONAL"}


def feature_snapshot_hash(matrix_spec):
    """REQ-INF-113. Sufficient to RECONSTRUCT the exact feature matrix, not merely to label it.

    A hash over a description that omits a filter is a hash that certifies the wrong matrix, so
    this hashes the whole canonicalised specification.
    """
    blob = json.dumps(matrix_spec, sort_keys=True, default=str)
    return hashlib.blake2b(blob.encode(), digest_size=16).hexdigest()


def revise_observation(existing, new_value, *, source_rev=None):
    """REQ-INF-114. Never an UPDATE: a new row, incremented rev, flipped `is_current`.

    The old row is what makes "what did the system believe last Tuesday" answerable at all.
    """
    return ({**existing, "is_current": False},
            {**existing, "value": new_value, "is_current": True,
             "source_rev": (source_rev if source_rev is not None
                            else existing.get("source_rev", 0) + 1)})


# ---------------------------------------------------------------- §G.1 the registry drives it

def hypotheses_from_registry(registry, tree):
    """REQ-INF-500. Derived entirely from the registry and the tree; no hardcoded pairs.

    Named `hypotheses_from_registry` rather than `testable_hypotheses` because pytest collects
    any imported callable whose name begins with `test`, and the collision produced a confusing
    "fixture 'registry' not found" error in an unrelated file. A name that breaks the test runner
    wherever it is imported is worth changing once.

    A hardcoded list is a list that stops matching the data the first time a metric is added, and
    the mismatch is silent — the search simply never looks at the new metric.
    """
    return tuple((src, tgt) for src, tgt in tree
                 if src in registry and tgt in registry)


def include_new_metric(registry, metric_key, *, active_since):
    """REQ-INF-501. A metric with `active_since` joins the NEXT scheduled search automatically."""
    return {**registry, metric_key: {"active_since": active_since,
                                     "joins": ("search", "regime_model", "coverage_report"),
                                     "at": "next_scheduled_run"}}


def ingest_guard(metric_key, registry):
    """REQ-INF-502. An observation whose metric has no registry row is refused.

    Not stored-and-flagged: refused. A metric with no registry row has no unit, no state class,
    no plausible range and no staleness rule, so nothing downstream can decide what to do with
    its values — and the row would sit there looking like data.
    """
    if metric_key not in registry:
        raise PreregistrationViolation(
            f"REQ-INF-502: {metric_key!r} has no row in metric_registry; an observation with no "
            f"unit, state class, plausible range or staleness rule is not data")
    return True


def legal_specifications(metric, registry, requested_transforms):
    """REQ-INF-503. Only the transformations that metric's registry row lists.

    The legal set is a property of the metric — a log transform is meaningful for a count and
    meaningless for a signed z-score — so it is declared once beside the metric rather than
    chosen per analysis.
    """
    legal = set(registry.get(metric, {}).get("legal_transforms") or ())
    illegal = [t for t in requested_transforms if t not in legal]
    if illegal:
        raise PreregistrationViolation(
            f"REQ-INF-503: {illegal} are not in {metric}'s legal_transforms {sorted(legal)}")
    return tuple(requested_transforms)


def check_interface(name):
    """REQ-INF-504. Exactly three interfaces, and no other reach into storage.

    An inference component that reads a table directly is one that can see a column the panel
    deliberately does not expose — a raw row, an un-superseded value, a coordinate.
    """
    if name not in INFERENCE_INTERFACES:
        raise PreregistrationViolation(
            f"REQ-INF-504: the inference layer reaches storage through exactly "
            f"{list(INFERENCE_INTERFACES)}; {name!r} is not one of them")
    return True


def negative_control_battery(registry, *, effects, threshold):
    """REQ-INF-506/507. Run automatically on EVERY promotion attempt, and a hit suppresses
    the whole pipeline's output.

    Not just the offending finding: the WHOLE RUN. A negative control that fires means the
    pipeline is finding effects where there cannot be any, and there is no reason to believe the
    other findings from that same run are different in kind.
    """
    controls = [m for m, r in registry.items() if r.get("is_negative_control")]
    fired = tuple(sorted(m for m in controls
                         if effects.get(m) is not None and abs(effects[m]) >= threshold))
    if fired:
        return {"passed": False, "fired": fired, "suppress_entire_run": True,
                "reason": (f"negative control(s) {list(fired)} show an effect at the same "
                           f"threshold as the real outcome; the pipeline is finding effects "
                           f"where there cannot be any, so the whole run is suppressed")}
    return {"passed": True, "controls_run": tuple(sorted(controls)), "suppress_entire_run": False}


def future_exposure_check(*, p_future, threshold=0.05):
    """REQ-INF-508. Shift the exposure to a FUTURE day and see whether the effect survives.

    If tomorrow's caffeine predicts today's sleep, the association is not caffeine acting on
    sleep — it is something slower moving both, or a shared trend nobody removed. A surviving
    effect here is an ARTIFACT DETECTOR: it says the pipeline would have found this pattern
    whatever the direction of time.
    """
    if p_future is None:
        return {"ran": False,
                "reason": "the future-shifted exposure could not be evaluated on this window"}
    survived = p_future < threshold
    return {"ran": True, "p_future": p_future, "artifact_detected": survived,
            "verdict": ("the effect survives with the exposure shifted into the FUTURE, so it is "
                        "an artifact of something moving both series, not of the exposure"
                        if survived else
                        "the effect does not survive a future-shifted exposure, as it should not")}
