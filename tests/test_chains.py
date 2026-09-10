"""B19 §G.4 — chains across lenses (REQ-INF-560..565, REQ-TIER-046).

Pure arithmetic and graph traversal, so it is exercised exhaustively here. Every test is about
a refusal, an attenuation or a tier floor: a chain is the easiest place in this system to
manufacture a confident falsehood, because each hop multiplies the reader's willingness to
believe while the evidence multiplies downward.
"""
import pytest

from tools.engines.chains import (Chain, Edge, TIER_ORDER, attenuate, build, paths,
                                  weakest_tier)

EV = dict(n=120, n_eff=41.2, interval=[0.11, 0.49], estimator="hac_ols",
          reverse_check={"nc_exposure_p": 0.61, "passed": True}, family="sleep->vitals")


def edge(a, b, effect=0.3, tier="PROMOTED", confidence=0.8, hid=None):
    return Edge(hypothesis_id=hid or f"{a}->{b}", exposure=a, outcome=b, tier=tier,
                effect=effect, confidence=confidence, evidence=dict(EV))


def test_REQ_INF_560_two_edges_of_point_three_compose_to_about_point_zero_nine():
    """The requirement's own worked example. Reporting 0.3 at the end of a two-hop chain would
    carry the first edge's strength all the way through; 91% of the variance is gone."""
    assert attenuate([0.3, 0.3]) == pytest.approx(0.09)
    chains = build([edge("sleep", "energy"), edge("energy", "spend")])
    assert len(chains) == 1
    assert chains[0].attenuated_effect == pytest.approx(0.09)


def test_REQ_INF_560_two_negative_edges_compose_to_a_positive_reach():
    """The single most counter-intuitive thing a chain reports, and the one a reader is most
    likely to get backwards if the sign is not computed: less sleep raising stress, and stress
    lowering spending, means less sleep RAISES spending."""
    chains = build([edge("sleep", "stress", effect=-0.4),
                    edge("stress", "spend", effect=-0.5)])
    assert chains[0].attenuated_effect == pytest.approx(0.2)


def test_REQ_INF_561_a_cycle_terminates_traversal_and_no_node_repeats():
    """Without this, A->B->A composes an effect with itself and reports the square of a
    correlation as a discovery, and a cyclic graph enumerates forever."""
    cyclic = [edge("a", "b"), edge("b", "c"), edge("c", "a")]
    for p in paths(cyclic):
        nodes = [p[0].exposure] + [e.outcome for e in p]
        assert len(nodes) == len(set(nodes)), f"a node repeats in {nodes}"
    assert all(len(p) <= 3 for p in paths(cyclic))


def test_REQ_TIER_046_the_chain_takes_the_tier_of_its_weakest_edge():
    """A chain is a conjunction: it holds only if every edge holds. Taking the strongest edge's
    tier would let one well-evidenced link launder two guesses."""
    chains = build([edge("sleep", "energy", tier="CONFIRMED_OBSERVATIONAL"),
                    edge("energy", "spend", tier="CANDIDATE")])
    assert chains[0].chain_tier == "CANDIDATE"
    assert weakest_tier(["EXPERIMENTAL", "DESCRIPTIVE", "PROMOTED"]) == "DESCRIPTIVE"


def test_REQ_INF_562_an_assembled_chain_states_what_would_firm_it_up():
    """Assembly from sub-threshold edges is PERMITTED, and only with this sentence attached. It
    must name the edge that is actually binding, not offer a generic 'collect more data'."""
    chains = build([edge("sleep", "energy", tier="CONFIRMED_OBSERVATIONAL"),
                    edge("energy", "spend", tier="CANDIDATE")])
    sentence = chains[0].what_would_firm_it_up
    assert "energy -> spend" in sentence, sentence
    assert "sleep -> energy" not in sentence, "the strong edge is not the constraint"


def test_REQ_INF_562_the_firming_sentence_names_the_confirmation_gate_for_a_promoted_chain():
    chains = build([edge("sleep", "energy", tier="PROMOTED"),
                    edge("energy", "spend", tier="CONFIRMED_OBSERVATIONAL")])
    assert "confirmation gate" in chains[0].what_would_firm_it_up


def test_REQ_INF_563_the_map_is_pruned_to_the_top_twenty_by_effect_times_confidence():
    """An unpruned cross-lens map is a wall of lines that means nothing. The ranking is
    absolute effect multiplied by confidence, so a large effect nobody trusts does not outrank
    a moderate one that is well evidenced."""
    edges = []
    for i in range(30):
        edges.append(edge(f"x{i}", f"y{i}", effect=0.9, confidence=0.01 * (i + 1)))
        edges.append(edge(f"y{i}", f"z{i}", effect=0.9, confidence=0.01 * (i + 1)))
    chains = build(edges)
    assert len(chains) == 20, "REQ-INF-563: pruned"
    scores = [c.rank_score for c in chains]
    assert scores == sorted(scores, reverse=True), "and ranked, strongest first"
    assert chains[0].rank_score > chains[-1].rank_score


def test_REQ_INF_563_a_large_effect_nobody_trusts_does_not_outrank_a_trusted_moderate_one():
    edges = [edge("a", "b", effect=0.9, confidence=0.05), edge("b", "c", effect=0.9, confidence=0.05),
             edge("p", "q", effect=0.4, confidence=0.95), edge("q", "r", effect=0.4, confidence=0.95)]
    chains = build(edges)
    assert chains[0].path[0] == "p", [(c.path, c.rank_score) for c in chains]


def test_REQ_INF_564_an_edge_without_a_complete_evidence_record_cannot_be_constructed():
    """Refusing at construction is the only place that cannot be forgotten by a caller
    assembling an envelope later. All six fields are required by name."""
    for field in Edge.REQUIRED_EVIDENCE:
        incomplete = {k: v for k, v in EV.items() if k != field}
        with pytest.raises(ValueError, match="REQ-INF-564"):
            Edge(hypothesis_id="h", exposure="a", outcome="b", tier="PROMOTED",
                 effect=0.3, confidence=0.8, evidence=incomplete)


def test_REQ_INF_564_every_rendered_edge_resolves_to_its_evidence():
    chains = build([edge("sleep", "energy"), edge("energy", "spend")])
    for e in chains[0].edges:
        for field in Edge.REQUIRED_EVIDENCE:
            assert e.evidence.get(field) is not None, f"{e.hypothesis_id} lost {field}"


def test_REQ_INF_565_a_chain_starting_at_a_context_metric_is_not_actionable():
    """Discovering that a chain STARTS at something Joe cannot change -- the weather, the day
    of the week, a resting heart rate -- does not make it a lever. An association is not a
    licence to reclassify."""
    roles = {"sleep_minutes": "lever", "weather_temp": "context"}
    chains = build([edge("weather_temp", "energy"), edge("energy", "spend")], roles=roles)
    assert chains[0].actionable is False
    chains = build([edge("sleep_minutes", "energy"), edge("energy", "spend")], roles=roles)
    assert chains[0].actionable is True


def test_REQ_INF_565_an_unregistered_metric_defaults_to_context_not_lever():
    """The safe default for "may Joe act on this?" is no. A metric absent from the registry is
    one nobody has classified, and treating silence as permission is how a context metric
    becomes a recommendation."""
    chains = build([edge("mystery", "energy"), edge("energy", "spend")], roles={})
    assert chains[0].actionable is False


def test_RULE_16_an_unknown_tier_is_refused_rather_than_ordered_arbitrarily():
    with pytest.raises(ValueError, match="unknown tier"):
        Edge(hypothesis_id="h", exposure="a", outcome="b", tier="STRONG",
             effect=0.3, confidence=0.8, evidence=dict(EV))


def test_RULE_21_a_confidence_outside_zero_to_one_is_refused():
    with pytest.raises(ValueError, match="not a probability"):
        Edge(hypothesis_id="h", exposure="a", outcome="b", tier="PROMOTED",
             effect=0.3, confidence=1.4, evidence=dict(EV))


def test_REQ_INF_563_a_single_edge_is_not_reported_as_a_chain():
    """A one-edge "chain" is the hypothesis itself, already surfaced by get_findings. Repeating
    it here would double-count one piece of evidence in the reader's mind."""
    assert build([edge("a", "b")]) == []


def test_REQ_INF_563_the_order_is_stable_across_identical_runs():
    """Ties broken by the path itself. Otherwise "the top 20" reshuffles between runs and a
    reader sees movement that is not there."""
    edges = [edge("a", "b"), edge("b", "c"), edge("p", "q"), edge("q", "r")]
    assert [c.path for c in build(edges)] == [c.path for c in build(list(reversed(edges)))]


def test_REQ_INF_560_a_three_hop_chain_attenuates_further_than_a_two_hop_one():
    chains = build([edge("a", "b"), edge("b", "c"), edge("c", "d")])
    by_hops = {c.hops: c.attenuated_effect for c in chains}
    assert by_hops[3] == pytest.approx(0.027)
    assert abs(by_hops[3]) < abs(by_hops[2]) < 0.3
