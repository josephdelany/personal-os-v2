"""B19 §G.4 — chains across lenses (REQ-INF-560..565, REQ-TIER-046).

Pure: no database, no clock, no model. The caller supplies edges and receives chains.

WHAT A CHAIN IS. A single hypothesis says "exposure moves outcome". A chain says "A moves B,
and B moves C, so A may reach C". That is a genuinely useful thing to surface across lenses --
sleep reaching spending through energy, say -- and it is also the easiest place in this system
to manufacture a confident falsehood, because every step multiplies the reader's willingness to
believe while the evidence multiplies DOWNWARD.

WHY ATTENUATION IS MULTIPLICATIVE (REQ-INF-560). Two edges of r=0.3 compose to about 0.09, not
0.6 and not 0.3. Ninety-one percent of the variance is gone after two hops. Stating the chain
without stating that number invites the reader to carry the strength of the first edge all the
way to the end. So `attenuated_effect` is computed and displayed, always, and it is the only
magnitude a chain is allowed to report.

WHY THE TIER IS THE WEAKEST EDGE (REQ-TIER-046, REQ-INF-562). A chain is a conjunction: it is
true only if every edge holds. A CONFIRMED edge joined to a CANDIDATE edge is a CANDIDATE
claim. Taking the strongest edge's tier, or an average, would let one well-evidenced link
launder two guesses -- which is exactly how a plausible story outruns its evidence.

WHY EVERY CHAIN CARRIES `what_would_firm_it_up` (REQ-INF-562). Assembly from sub-threshold
edges is PERMITTED, and it is permitted only with that sentence attached. A chain the reader
cannot act on and cannot improve is speculation presented as analysis.

WHY A CONTEXT METRIC IS NEVER A LEVER (REQ-INF-565). `metric_registry.role` distinguishes what
Joe can change from what merely covaries. Discovering that a chain STARTS at a context metric --
the weather, a resting heart rate, the day of the week -- does not make it actionable, and an
association is not a licence to reclassify. The role is declared in the registry and this
module reads it; nothing here writes it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# RULE-16's ladder, weakest first. A chain takes the minimum.
TIER_ORDER = ("INSUFFICIENT", "DESCRIPTIVE", "CANDIDATE", "PROMOTED",
              "CONFIRMED_OBSERVATIONAL", "EXPERIMENTAL")
MAX_PATH_EDGES = 3          # REQ-INF-560's worked example is two; three is the brief's cap
KEEP_TOP = 20               # REQ-INF-563


@dataclass(frozen=True)
class Edge:
    """One hypothesis, as a directed edge with its evidence record.

    `effect` MUST be on a common standardized scale across every edge, because REQ-INF-560
    multiplies them. Multiplying a beta in minutes-per-hour by a beta in dollars-per-step
    produces a number with no meaning and no unit, and it would still print. `evidence` is
    required to carry REQ-INF-564's six fields; a missing one raises rather than rendering an
    edge that cannot be traced.
    """
    hypothesis_id: str
    exposure: str
    outcome: str
    tier: str
    effect: float                       # standardized; sign carries direction
    confidence: float                   # 0..1
    evidence: dict = field(default_factory=dict)

    REQUIRED_EVIDENCE = ("n", "n_eff", "interval", "estimator", "reverse_check", "family")

    def __post_init__(self):
        if self.tier not in TIER_ORDER:
            raise ValueError(f"{self.hypothesis_id}: unknown tier {self.tier!r}")
        missing = [k for k in self.REQUIRED_EVIDENCE if k not in self.evidence]
        if missing:
            # REQ-INF-564. An edge that cannot resolve to a stored evidence record must not be
            # rendered, and refusing at construction is the only place that cannot be forgotten
            # later by a caller assembling an envelope.
            raise ValueError(f"{self.hypothesis_id}: evidence record is missing "
                             f"{', '.join(missing)} (REQ-INF-564)")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"{self.hypothesis_id}: confidence {self.confidence} is not a "
                             f"probability")


@dataclass(frozen=True)
class Chain:
    path: tuple[str, ...]
    edges: tuple[Edge, ...]
    tiers: tuple[str, ...]
    chain_tier: str
    attenuated_effect: float
    rank_score: float
    actionable: bool
    what_would_firm_it_up: str

    @property
    def hops(self) -> int:
        return len(self.edges)


def weakest_tier(tiers) -> str:
    """REQ-TIER-046. The chain is a conjunction; it is only as good as its worst link."""
    return min(tiers, key=TIER_ORDER.index)


def attenuate(effects) -> float:
    """REQ-INF-560. Multiplicative, so 0.3 and 0.3 compose to 0.09 rather than 0.6.

    The sign is the product of the signs: two negative edges compose to a POSITIVE reach, which
    is correct and is the single most counter-intuitive thing a chain reports. Less sleep
    raising stress, and stress lowering spending, means less sleep RAISES spending.
    """
    out = 1.0
    for e in effects:
        out *= float(e)
    return out


def _firming_sentence(edges) -> str:
    """REQ-INF-562. What would move this chain up a tier, named concretely.

    The binding constraint is the weakest edge, not the chain as a whole, so the sentence names
    that edge. A generic "collect more data" is not a next action.
    """
    worst = min(edges, key=lambda e: TIER_ORDER.index(e.tier))
    if worst.tier in ("INSUFFICIENT", "DESCRIPTIVE", "CANDIDATE"):
        return (f"The chain is held at {worst.tier} by {worst.exposure} -> {worst.outcome}. "
                f"Registering that pair as a hypothesis and letting it accrue post-registration "
                f"days would let it promote, which would raise the whole chain.")
    if worst.tier == "PROMOTED":
        return (f"The chain is held at PROMOTED by {worst.exposure} -> {worst.outcome}. "
                f"It needs the confirmation gate: a registered adjustment set, negative controls "
                f"and refutation tests on data recorded after registration.")
    return (f"Every edge is at {worst.tier} or better. Only a randomized trial on "
            f"{worst.exposure} would raise it further.")


def paths(edges, max_edges: int = MAX_PATH_EDGES):
    """Every simple directed path of 1..max_edges edges (REQ-INF-561).

    "Simple" is the whole requirement: traversal terminates on any cycle and a node appears at
    most once per path. Without it, A->B->A composes an effect with itself and reports the
    square of a correlation as a discovery, and a cyclic graph enumerates forever.
    """
    by_source: dict[str, list[Edge]] = {}
    for e in edges:
        by_source.setdefault(e.exposure, []).append(e)

    found = []

    def walk(node, visited, acc):
        if acc:
            found.append(tuple(acc))
        if len(acc) == max_edges:
            return
        for edge in by_source.get(node, ()):
            if edge.outcome in visited:
                continue                      # REQ-INF-561: the cycle stops here
            walk(edge.outcome, visited | {edge.outcome}, acc + [edge])

    for start in sorted(by_source):
        walk(start, {start}, [])
    return found


def build(edges, roles=None, keep_top: int = KEEP_TOP, min_hops: int = 2):
    """Assemble, rank and prune. Returns at most `keep_top` chains, strongest first.

    `roles` maps a metric to 'lever' or 'context'. REQ-INF-565: a chain whose head is a context
    metric is still REPORTED -- it is a real association and hiding it would be its own
    distortion -- but it is marked `actionable=False`, and nothing downstream may treat its head
    as something to change. An unknown metric is treated as context, because the safe default
    for "may Joe act on this?" is no.

    `min_hops` defaults to 2 because a one-edge "chain" is just the hypothesis, already surfaced
    by `get_findings`; repeating it here would double-count one piece of evidence in a reader's
    mind.
    """
    roles = roles or {}
    chains = []
    for edge_path in paths(edges):
        if len(edge_path) < min_hops:
            continue
        nodes = (edge_path[0].exposure,) + tuple(e.outcome for e in edge_path)
        tiers = tuple(e.tier for e in edge_path)
        att = attenuate(e.effect for e in edge_path)
        # REQ-INF-563: rank by |effect| x confidence. The confidence of a conjunction is bounded
        # by its weakest link, so the MINIMUM is used rather than a product -- a product would
        # punish a long chain twice, once through attenuation and again through confidence, and
        # the ordering would then be driven by length rather than by strength.
        score = abs(att) * min(e.confidence for e in edge_path)
        chains.append(Chain(
            path=nodes, edges=tuple(edge_path), tiers=tiers,
            chain_tier=weakest_tier(tiers), attenuated_effect=round(att, 6),
            rank_score=round(score, 6),
            actionable=roles.get(nodes[0]) == "lever",
            what_would_firm_it_up=_firming_sentence(edge_path)))
    # Ties broken by the path itself so a rerun on unchanged data returns the same order --
    # otherwise "the top 20" silently reshuffles and a reader sees movement that is not there.
    chains.sort(key=lambda c: (-c.rank_score, c.path))
    return chains[:keep_top]
