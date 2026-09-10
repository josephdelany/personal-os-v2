"""B17 §B.3/B.4 — the categorisation cascade and correction loop (REQ-FIN-080..106).

Pure orchestration, so every layer is a stub: the order, the confidence ceilings and the refusals
are tested with no embeddings, no LLM and no network call.
"""
import pytest

from tools.engines.category_cascade import (Categorisation, KNN_MIN_EXAMPLES, LAYERS,
                                            LAYER_WINDOW, LLM_MIN_CONFIDENCE,
                                            MAX_TAXONOMY_LEAVES, MCC_MAX_CONFIDENCE, NeedsReview,
                                            apply_correction, build_llm_prompt, categorise,
                                            embeddings_admission, knn_vote, layer_accuracy,
                                            review_page, suspended_layers, validate_taxonomy)

TAXONOMY = ("groceries", "dining", "fuel", "transport", "utilities")


def says(category, confidence=1.0):
    def fn(*args, **kwargs):
        return (category, confidence)
    return fn


def abstains(*args, **kwargs):
    return None


def test_REQ_FIN_080_the_layers_run_in_order_and_only_after_every_earlier_one_abstained():
    assert LAYERS == ("hash", "merchant", "mcc", "knn", "llm")
    calls = []

    def watch(name, result):
        def fn(*a, **k):
            calls.append(name)
            return result
        return fn

    r = categorise("SHELL OIL", taxonomy=TAXONOMY, layers={
        "hash": watch("hash", None), "merchant": watch("merchant", None),
        "mcc": watch("mcc", ("fuel", 0.9)), "knn": watch("knn", ("dining", 1.0)),
    }, mcc="5541")
    assert calls == ["hash", "merchant", "mcc"], "knn must not run after mcc answered"
    assert r.category == "fuel"


def test_REQ_FIN_082_a_hash_hit_is_certain_and_stops_the_cascade():
    """A descriptor Joe has already confirmed is answered. Recomputing it would let a model
    disagree with him about a question he has already settled."""
    r = categorise("SHELL OIL", taxonomy=TAXONOMY,
                   layers={"hash": says("fuel", 0.4), "merchant": says("dining")})
    assert (r.category, r.category_source, r.confidence) == ("fuel", "hash", 1.0)
    assert [t["layer"] for t in r.layer_trace] == ["hash"]


def test_REQ_FIN_081_every_categorisation_carries_a_known_source_and_a_confidence():
    r = categorise("X", taxonomy=TAXONOMY, layers={"merchant": says("dining", 0.9)})
    assert r.category_source == "merchant" and r.confidence == 0.9
    with pytest.raises(ValueError, match="REQ-FIN-081"):
        Categorisation("dining", "vibes", 1.0)


def test_REQ_FIN_083_mcc_is_capped_at_zero_point_six_whatever_the_layer_claims():
    """The same business codes differently across cards and departments, and 5812 (Eating Places)
    versus 5813 (Drinking Places) is set by the ACQUIRER — the exact distinction every alcohol
    figure depends on."""
    r = categorise("X", taxonomy=TAXONOMY, layers={"mcc": says("dining", 0.99)}, mcc="5812")
    assert r.confidence == MCC_MAX_CONFIDENCE == 0.60
    assert r.category_source == "mcc"


def test_REQ_FIN_084_the_cascade_works_with_no_mcc_at_all():
    """MCC is absent from CSV exports, from alert emails and from OFX — that is the normal case,
    not an error."""
    r = categorise("X", taxonomy=TAXONOMY,
                   layers={"hash": abstains, "merchant": says("dining", 0.9)}, mcc=None)
    assert r.category == "dining"
    assert any(t["layer"] == "mcc" and t["outcome"] == "not_configured" for t in r.layer_trace) \
        or all(t["layer"] != "mcc" for t in r.layer_trace)


def test_REQ_FIN_085_knn_takes_the_plurality_of_five_and_reports_the_vote_fraction():
    cat, conf, auto = knn_vote(["dining", "dining", "dining", "groceries", "fuel"],
                               n_examples=200)
    assert (cat, conf, auto) == ("dining", 0.6, True)
    cat, conf, _ = knn_vote(["dining"] * 5, n_examples=200)
    assert conf == 1.0


def test_REQ_FIN_085_a_knn_tie_breaks_on_distance_not_on_the_alphabet():
    """Breaking on the category name would make the answer depend on spelling."""
    cat, _, _ = knn_vote(["zebra_cat", "apple_cat"], k=2, n_examples=200)
    assert cat == "zebra_cat", "the nearer neighbour wins"


def test_REQ_FIN_087_below_100_confirmed_examples_knn_goes_to_review_not_to_the_ledger():
    """The ~95% accuracy figure is reported at roughly 100 labelled examples. Below that the
    number is not claimed, and borrowing it would cite a result the study did not produce."""
    r = categorise("X", taxonomy=TAXONOMY, layers={"knn": says(["dining"] * 5)},
                   knn_examples=KNN_MIN_EXAMPLES - 1)
    assert isinstance(r, NeedsReview)
    routed = [t for t in r.layer_trace if t["layer"] == "knn"][0]
    assert routed["outcome"] == "routed_to_review"
    assert "99 confirmed examples" in routed["reason"]

    ok = categorise("X", taxonomy=TAXONOMY, layers={"knn": says(["dining"] * 5)},
                    knn_examples=KNN_MIN_EXAMPLES)
    assert isinstance(ok, Categorisation) and ok.category_source == "knn"


def test_REQ_FIN_089_an_llm_answer_is_auto_applied_only_at_or_above_0_80():
    """Mirrors the published finding: >0.8-confidence predictions were 90.4% accurate while the
    same model's overall zero-shot accuracy was 60.4%."""
    r = categorise("X", taxonomy=TAXONOMY,
                   layers={"hash": abstains, "llm": says("dining", 0.81)})
    assert isinstance(r, Categorisation) and r.category_source == "llm"
    assert LLM_MIN_CONFIDENCE == 0.80


def test_REQ_FIN_090_a_low_confidence_llm_answer_leaves_no_guess_anywhere():
    """A field holding the rejected guess is a field a renderer eventually reads "just to show
    something". The only way to be sure is not to carry it."""
    r = categorise("X", taxonomy=TAXONOMY, amount=42.0,
                   layers={"hash": abstains, "llm": says("dining", 0.79)})
    assert isinstance(r, NeedsReview)
    assert r.reason == "llm_confidence_below_threshold"
    assert not hasattr(r, "category"), "the rejected guess must not be carried"
    assert "dining" not in str(r), r


def test_REQ_FIN_091_the_llm_may_never_be_the_first_move():
    """The one ordering whose violation produces a confident, fluent, 60%-accurate ledger. An
    explicit check, not merely last place in a list, because a list can be reordered."""
    with pytest.raises(ValueError, match="REQ-FIN-091"):
        categorise("X", taxonomy=TAXONOMY, layers={"llm": says("dining", 0.95)})


def test_REQ_FIN_092_the_prompt_carries_four_fields_and_no_other_lens():
    p = build_llm_prompt(normalized_descriptor="SHELL OIL", amount=42.1, taxonomy=TAXONOMY,
                         mcc="5541")
    assert set(p) == {"normalized_descriptor", "amount", "mcc", "taxonomy", "instruction"}
    assert "confidence" in p["instruction"]
    blob = str(p).lower()
    for leak in ("lat", "lon", "mood", "hrv", "sleep"):
        assert leak not in blob, leak


def test_REQ_FIN_092_the_prompt_is_built_in_one_place_so_the_allowlist_cannot_be_bypassed():
    """An allowlist rather than a banlist: a banlist has to anticipate every future field, and
    the one it misses is the one that leaks."""
    import inspect
    from tools.engines import category_cascade as m
    src = inspect.getsource(m.build_llm_prompt)
    assert "PROMPT_ALLOWED_KEYS" in src
    assert "REQ-FIN-092" in src


def test_REQ_FIN_093_a_taxonomy_over_25_leaves_is_refused():
    """Not tidiness: Field Study 5 (n=251) found sub-category fragmentation INCREASED total
    spending. The taxonomy size is a behavioural intervention."""
    assert len(validate_taxonomy(TAXONOMY)) == 5
    with pytest.raises(ValueError, match="REQ-FIN-093"):
        validate_taxonomy([f"c{i}" for i in range(MAX_TAXONOMY_LEAVES + 1)])
    assert validate_taxonomy([f"c{i}" for i in range(MAX_TAXONOMY_LEAVES)])


def test_REQ_FIN_080_when_every_layer_abstains_the_sixth_step_is_asking_joe():
    r = categorise("MYSTERY", taxonomy=TAXONOMY, amount=12.0,
                   layers={"hash": abstains, "merchant": abstains})
    assert isinstance(r, NeedsReview) and r.reason == "no_layer_assigned"


# ---------------------------------------------------------------- B.4 the correction loop

def test_REQ_FIN_100_102_a_correction_writes_all_three_memories_in_one_transaction():
    out = apply_correction({"id": 1, "merchant": "Shell", "descriptor": "SHELL OIL 111"},
                           "fuel", descriptor_hash="h1")
    assert out["atomic"] is True
    tables = {w["table"] for w in out["writes"]}
    assert tables == {"transactions", "descriptor_hash_memory", "merchant_default_category",
                      "category_embeddings"}
    txn = [w for w in out["writes"] if w["table"] == "transactions"][0]
    assert (txn["category_source"], txn["confidence"]) == ("user", 1.0)
    assert txn["corrected_at"] is not None


def test_REQ_FIN_101_an_automated_layer_may_never_overwrite_a_user_category():
    """"No automated layer, no model retrain, no reprocessing job, and no schema migration.\""""
    with pytest.raises(ValueError, match="REQ-FIN-101"):
        apply_correction({"id": 1, "category_source": "user", "corrected_by": "engine"},
                         "dining", descriptor_hash="h1")


def test_REQ_FIN_103_siblings_sharing_the_hash_are_propagated_and_marked_as_such():
    out = apply_correction({"id": 1, "merchant": "Shell", "descriptor": "SHELL OIL"}, "fuel",
                           descriptor_hash="h1",
                           sharing_hash=[{"id": 2}, {"id": 3, "category_source": "user"}])
    propagated = [w for w in out["writes"]
                  if w["table"] == "transactions" and w.get("category_source") == "user_propagated"]
    assert [w["id"] for w in propagated] == [2], "row 3 was Joe's own earlier decision"


def test_REQ_FIN_086_the_embedding_store_refuses_an_llm_label():
    """Admitting one would let 60%-accurate guesses become the neighbours that justify the next
    guess: the error compounds while looking like learning."""
    ok, _ = embeddings_admission({"label_origin": "joe"})
    assert ok
    bad, why = embeddings_admission({"label_origin": "llm"})
    assert not bad and "REQ-FIN-086" in why


def test_REQ_FIN_104_the_failing_layer_is_identifiable_not_just_the_aggregate():
    """Without per-layer tallies, a categoriser that has quietly become wrong presents as one
    that is fine, because the aggregate hides which layer moved."""
    events = [{"layer": "mcc", "corrected": True} for _ in range(30)] + \
             [{"layer": "hash", "corrected": False} for _ in range(30)]
    acc = layer_accuracy(events)
    assert acc["mcc"]["rate"] == 1.0 and acc["hash"]["rate"] == 0.0
    assert acc["knn"]["n"] == 0 and acc["knn"]["rate"] is None


def test_REQ_FIN_105_a_layer_over_20_percent_across_50_stops_auto_applying():
    events = [{"layer": "llm", "corrected": i < 15} for i in range(LAYER_WINDOW)]
    assert layer_accuracy(events)["llm"]["rate"] == 0.3
    assert suspended_layers(events) == ("llm",)


def test_REQ_FIN_105_a_short_window_does_not_suspend_a_layer_for_noise():
    """A layer suspended on three samples is a capability lost for no reason."""
    events = [{"layer": "llm", "corrected": True} for _ in range(3)]
    assert suspended_layers(events) == ()


def test_REQ_FIN_105_a_suspended_layer_is_still_consulted_and_routed_to_review():
    """Silencing it entirely would lose the signal that it has started working again."""
    r = categorise("X", taxonomy=TAXONOMY, layers={"merchant": says("dining", 0.9)},
                   disabled_layers=("merchant",))
    assert isinstance(r, NeedsReview)
    routed = [t for t in r.layer_trace if t["layer"] == "merchant"][0]
    assert routed["outcome"] == "routed_to_review"
    assert "suspended" in routed["reason"]


def test_REQ_FIN_106_a_review_session_is_bounded_and_ordered_by_amount():
    """A backlog of 400 is still a twenty-minute job rather than a reason never to open the
    queue at all."""
    items = [{"id": i, "amount": i} for i in range(40)]
    page = review_page(items)
    assert len(page) == 20
    assert [i["amount"] for i in page] == list(range(39, 19, -1))
    assert review_page([{"id": 1, "amount": -500}, {"id": 2, "amount": 20}])[0]["id"] == 1


def test_REQ_FIN_088_the_llm_layer_receives_the_complete_taxonomy_and_asks_for_confidence():
    """The complete taxonomy, because a model given a partial list will invent a category that
    fits the item rather than choosing badly from the list it was shown — and an invented
    category is one no downstream rollup knows about."""
    p = build_llm_prompt(normalized_descriptor="SHELL OIL", amount=42.1, taxonomy=TAXONOMY)
    assert tuple(p["taxonomy"]) == TAXONOMY
    assert "confidence" in p["instruction"]
