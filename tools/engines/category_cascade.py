"""B17 §B.3/B.4 — the categorisation cascade and the correction loop (REQ-FIN-080..106).

Pure orchestration: no database, no clock, no network, no model. Every layer is a callable the
caller supplies, so the ORDER, the confidence ceilings and the refusals are testable without
embeddings, without an LLM, and without a single network call.

WHY THE ORDER IS THE REQUIREMENT. Six layers, each running only if every preceding one abstained:

  1. hash      — this exact descriptor, already confirmed by Joe. Certain.
  2. merchant  — the merchant's default category. Nearly certain.
  3. mcc       — the acquirer's code. A weak prior, capped at 0.60, NEVER ground truth.
  4. knn       — Joe's own corrected history, nearest five.
  5. llm       — a guess, admitted only above 0.80 confidence.
  6. ask       — Joe.

Run in any other order this is a different system. The LLM is cheap and fluent and will answer
every question put to it, so a cascade that reaches for it early produces a fully-categorised
ledger that is 60% right — REQ-FIN-089's own figure for zero-shot accuracy. REQ-FIN-091 therefore
forbids the LLM as the first move, absolutely, and this module cannot express that ordering.

WHY MCC IS CAPPED AT 0.60 AND NEVER TRUSTED (REQ-FIN-083). The same business codes differently
across cards and departments. MCC 5812 (Eating Places) versus 5813 (Drinking Places) is set by
the ACQUIRER -- and that is exactly the distinction every alcohol figure in this system depends
on. A code chosen by a payment processor for its own reasons cannot be allowed to decide whether
a charge was dinner or drinking.

WHY THE EMBEDDING STORE REFUSES LLM LABELS (REQ-FIN-086). The kNN layer learns from Joe's
corrections. Admitting an LLM label would let the model's 60%-accurate guesses become the
neighbours that justify the next guess, and the error would compound while looking like learning.

WHY BELOW 100 EXAMPLES NOTHING AUTO-APPLIES (REQ-FIN-087). The ~95% accuracy figure for
embeddings-plus-classifier is reported at roughly 100 labelled examples. Below that the number is
not claimed, and borrowing it would be citing a result the study did not produce.
"""
from __future__ import annotations

from dataclasses import dataclass, field

LAYERS = ("hash", "merchant", "mcc", "knn", "llm")      # REQ-FIN-080, in order. `user` is not a layer.
CATEGORY_SOURCES = frozenset(LAYERS) | {"user", "user_propagated"}   # REQ-FIN-081
MCC_MAX_CONFIDENCE = 0.60            # REQ-FIN-083
KNN_K = 5                            # REQ-FIN-085
KNN_MIN_EXAMPLES = 100               # REQ-FIN-087
LLM_MIN_CONFIDENCE = 0.80            # REQ-FIN-089
MAX_TAXONOMY_LEAVES = 25             # REQ-FIN-093
LAYER_CORRECTION_LIMIT = 0.20        # REQ-FIN-105
LAYER_WINDOW = 50                    # REQ-FIN-105
REVIEW_PAGE = 20                     # REQ-FIN-106

# REQ-FIN-092. What the LLM prompt may contain, exhaustively. An allowlist rather than a
# banlist: a banlist has to anticipate every future field, and the one it misses is the one that
# leaks. Anything not named here is not sent.
PROMPT_ALLOWED_KEYS = frozenset({"normalized_descriptor", "amount", "mcc", "taxonomy"})


@dataclass(frozen=True)
class Categorisation:
    category: str
    category_source: str
    confidence: float
    layer_trace: tuple = ()

    def __post_init__(self):
        if self.category_source not in CATEGORY_SOURCES:
            raise ValueError(f"REQ-FIN-081: unknown category_source {self.category_source!r}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence {self.confidence} is not a probability")


@dataclass(frozen=True)
class NeedsReview:
    """REQ-FIN-090. Uncategorised, queued, and NOT displayed as a guess anywhere.

    `category` is deliberately absent from this class rather than present-and-null. A field that
    holds the rejected guess is a field a renderer will eventually read "just to show something",
    and REQ-FIN-090 forbids displaying it at all. The only way to be sure is not to carry it.
    """
    descriptor: str
    reason: str
    amount: float | None = None
    layer_trace: tuple = ()


def validate_taxonomy(taxonomy):
    """REQ-FIN-093. At most 25 leaves.

    Not an arbitrary tidiness limit: Field Study 5 (n=251) found that fragmenting spend into many
    sub-categories INCREASED total spending, through mental-accounting justification. The
    taxonomy size is a behavioural intervention, so it is enforced rather than recommended.
    """
    leaves = list(taxonomy)
    if len(leaves) > MAX_TAXONOMY_LEAVES:
        raise ValueError(
            f"REQ-FIN-093: {len(leaves)} categories exceeds the {MAX_TAXONOMY_LEAVES}-leaf limit; "
            f"sub-category fragmentation increased total spending in Field Study 5 (n=251)")
    return tuple(leaves)


def knn_vote(neighbours, *, k=KNN_K, n_examples=0):
    """REQ-FIN-085/087. Plurality of the nearest k, confidence = the winning vote fraction.

    Returns (category, confidence, auto_ok). `auto_ok` is False below 100 confirmed examples --
    the layer still votes, and its vote still goes to review rather than to the ledger.
    """
    top = list(neighbours)[:k]
    if not top:
        return None, 0.0, False
    counts = {}
    for c in top:
        counts[c] = counts.get(c, 0) + 1
    # Ties break on the neighbour order, which is cosine distance: the closest wins. Breaking on
    # the category name instead would make the answer depend on the alphabet.
    best = max(counts, key=lambda c: (counts[c], -top.index(c)))
    return best, counts[best] / len(top), n_examples >= KNN_MIN_EXAMPLES


def build_llm_prompt(*, normalized_descriptor, amount, taxonomy, mcc=None):
    """REQ-FIN-088/092. The complete taxonomy, a confidence request, and nothing else.

    Built here rather than assembled by the caller so REQ-FIN-092's allowlist is applied at the
    one place a prompt can be constructed. A caller that wants to add a field has to change this
    function, which is a visible edit, rather than pass an extra key nobody notices.
    """
    payload = {"normalized_descriptor": normalized_descriptor, "amount": amount,
               "taxonomy": validate_taxonomy(taxonomy)}
    if mcc is not None:
        payload["mcc"] = mcc                     # REQ-FIN-084: absent is normal, not an error
    leaked = set(payload) - PROMPT_ALLOWED_KEYS
    if leaked:
        raise ValueError(f"REQ-FIN-092: {sorted(leaked)} may not enter a categorisation prompt")
    payload["instruction"] = ("Return one category from the taxonomy and a confidence between 0 "
                              "and 1.")
    return payload


def categorise(descriptor, *, layers, taxonomy, amount=None, mcc=None, knn_examples=0,
               disabled_layers=()):
    """The cascade. Returns a `Categorisation` or a `NeedsReview`.

    `layers` maps a layer name to a callable. A layer ABSTAINS by returning None; anything else
    is its answer. A layer absent from the mapping abstains -- which is how REQ-FIN-084 is
    satisfied for MCC without a special case, since MCC is absent from CSV exports, alert emails
    and OFX alike.

    `disabled_layers` comes from REQ-FIN-105: a layer whose correction rate has exceeded 20% is
    still CONSULTED, but its answer is routed to review rather than auto-applied. Silencing it
    entirely would lose the signal that it has started working again.
    """
    validate_taxonomy(taxonomy)
    trace = []

    for name in LAYERS:
        fn = layers.get(name)
        if fn is None:
            trace.append({"layer": name, "outcome": "not_configured"})
            continue

        if name == "llm":
            # REQ-FIN-091. Not merely "the LLM is last in the list" -- an explicit check, because
            # the list could be reordered by a future edit and this is the one ordering whose
            # violation produces a confident, fluent, 60%-accurate ledger.
            if not any(t["outcome"] in ("abstained", "below_threshold", "routed_to_review")
                       for t in trace):
                raise ValueError("REQ-FIN-091: the LLM layer may never be the first move")
            prompt = build_llm_prompt(normalized_descriptor=descriptor, amount=amount,
                                      taxonomy=taxonomy, mcc=mcc)
            result = fn(prompt)
        elif name == "knn":
            result = fn(descriptor)
        else:
            result = fn(descriptor, mcc) if name == "mcc" else fn(descriptor)

        if result is None:
            trace.append({"layer": name, "outcome": "abstained"})
            continue

        category, confidence = result if isinstance(result, tuple) else (result, 1.0)

        if name == "hash":
            # REQ-FIN-082. A descriptor Joe has already confirmed is certain, and no later layer
            # runs. Recomputing it would let a model disagree with him about a question he has
            # already answered.
            confidence = 1.0
        elif name == "mcc":
            # REQ-FIN-083. Capped, never ground truth. The cap is applied here rather than
            # trusted to the layer, because the layer is supplied by the caller.
            confidence = min(float(confidence), MCC_MAX_CONFIDENCE)
        elif name == "knn":
            category, confidence, auto_ok = knn_vote(category if isinstance(category, list)
                                                     else [category], k=KNN_K,
                                                     n_examples=knn_examples)
            if not auto_ok:
                trace.append({"layer": name, "outcome": "routed_to_review",
                              "reason": f"only {knn_examples} confirmed examples; the ~95% "
                                        f"accuracy figure is reported at ~{KNN_MIN_EXAMPLES}"})
                continue
        elif name == "llm":
            if float(confidence) < LLM_MIN_CONFIDENCE:
                # REQ-FIN-090. Uncategorised, queued, and the guess is not carried forward.
                trace.append({"layer": name, "outcome": "below_threshold",
                              "confidence": round(float(confidence), 3)})
                return NeedsReview(descriptor, "llm_confidence_below_threshold", amount,
                                   tuple(trace))

        if name in disabled_layers:
            # REQ-FIN-105. The layer answered and is under suspension: its answer goes to review.
            trace.append({"layer": name, "outcome": "routed_to_review",
                          "reason": "layer suspended for exceeding its correction rate"})
            continue

        trace.append({"layer": name, "outcome": "assigned", "category": category})
        return Categorisation(category, name, float(confidence), tuple(trace))

    return NeedsReview(descriptor, "no_layer_assigned", amount, tuple(trace))   # REQ-FIN-080 (6)


# ---------------------------------------------------------------- B.4 the correction loop

def apply_correction(existing, corrected_category, *, descriptor_hash, sharing_hash=()):
    """REQ-FIN-100/101/102/103. Joe corrects, and three memories and every sibling follow.

    Returns the writes to make, all in ONE transaction. Returning them rather than performing
    them keeps this module pure, and makes REQ-FIN-102's "in the same transaction" a property a
    caller can be tested against.
    """
    if existing.get("category_source") == "user":
        # REQ-FIN-101. "No automated layer, no model retrain, no reprocessing job, and no schema
        # migration SHALL change such a value." Only Joe supersedes Joe.
        if existing.get("corrected_by") != "joe":
            raise ValueError("REQ-FIN-101: a user-set category may never be overwritten by an "
                             "automated layer")

    writes = [{"table": "transactions", "id": existing.get("id"),
               "category": corrected_category, "category_source": "user",
               "confidence": 1.0, "corrected_at": "now"}]          # REQ-FIN-100
    # REQ-FIN-102, all three memories.
    writes.append({"table": "descriptor_hash_memory", "hash": descriptor_hash,
                   "category": corrected_category, "confirmed_by": "joe"})
    writes.append({"table": "merchant_default_category", "merchant": existing.get("merchant"),
                   "category": corrected_category})
    writes.append({"table": "category_embeddings", "descriptor": existing.get("descriptor"),
                   "category": corrected_category, "label_origin": "joe"})   # REQ-FIN-086
    # REQ-FIN-103. Every uncorrected sibling gets it, marked so the propagation is visible and
    # distinguishable from a direct correction.
    for sibling in sharing_hash:
        if sibling.get("category_source") == "user":
            continue                       # his own earlier decision on that row stands
        writes.append({"table": "transactions", "id": sibling.get("id"),
                       "category": corrected_category,
                       "category_source": "user_propagated", "confidence": 1.0})
    return {"writes": tuple(writes), "atomic": True}


def embeddings_admission(row):
    """REQ-FIN-086. Only Joe's confirmations and corrections enter the embedding store.

    Admitting an LLM label would let 60%-accurate guesses become the neighbours that justify the
    next guess. The error would compound while looking like learning.
    """
    if row.get("label_origin") not in ("joe", "user", "user_propagated"):
        return False, (f"REQ-FIN-086: label_origin {row.get('label_origin')!r} is not a Joe "
                       f"confirmation; an LLM label would become the neighbour that justifies "
                       f"the next LLM label")
    return True, ""


def layer_accuracy(events):
    """REQ-FIN-104. Per-layer correction rate, so the FAILING layer is identifiable.

    `events` is a sequence of {layer, corrected: bool}, newest last. Without this, a categoriser
    that has quietly become wrong presents as a categoriser that is fine, because the aggregate
    hides which layer moved.
    """
    out = {}
    for layer in LAYERS:
        recent = [e for e in events if e.get("layer") == layer][-LAYER_WINDOW:]
        if not recent:
            out[layer] = {"n": 0, "corrected": 0, "rate": None, "auto_apply": True}
            continue
        corrected = sum(1 for e in recent if e.get("corrected"))
        rate = corrected / len(recent)
        out[layer] = {"n": len(recent), "corrected": corrected, "rate": round(rate, 3),
                      # REQ-FIN-105. Suspension needs a full window: judging a layer on three
                      # samples would suspend it for noise, and a layer suspended for noise is a
                      # capability lost for no reason.
                      "auto_apply": not (len(recent) >= LAYER_WINDOW
                                         and rate > LAYER_CORRECTION_LIMIT)}
    return out


def suspended_layers(events):
    """REQ-FIN-105. Which layers must route to review instead of auto-applying."""
    return tuple(l for l, s in layer_accuracy(events).items() if not s["auto_apply"])


def review_page(items, *, page=REVIEW_PAGE):
    """REQ-FIN-106. At most 20, largest amount first, so a session is bounded in time.

    Ordering by amount rather than by date puts the decisions that matter most at the top, and
    the cap means a backlog of 400 items is still a twenty-minute job rather than a reason never
    to open the queue at all.
    """
    return tuple(sorted(items, key=lambda i: -abs(float(i.get("amount") or 0)))[:page])
