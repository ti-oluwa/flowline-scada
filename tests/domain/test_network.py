"""Tests for flowline_scada.domain.network.

Concrete Node/Edge stand-ins are used here rather than the real component
types from `domain.components` (Pipe, Valve, Junction, etc. — arriving
next in Phase 1) — this module tests graph *topology* mechanics in
isolation, which only needs something with a `.name`.
"""

import attrs
import pytest

from flowline_scada.domain.errors import (
    DisconnectedNetworkError,
    DuplicateEdgeError,
    DuplicateNodeError,
    UnknownEdgeError,
    UnknownNodeError,
)
from flowline_scada.domain.network import Edge, Node, PipelineNetwork


@attrs.define(frozen=True, slots=True)
class FakeNode:
    name: str


@attrs.define(frozen=True, slots=True)
class FakeEdge:
    name: str


@pytest.fixture
def network() -> PipelineNetwork[FakeNode, FakeEdge]:
    return PipelineNetwork("test-network")


@pytest.fixture
def two_node_network(
    network: PipelineNetwork[FakeNode, FakeEdge],
) -> PipelineNetwork[FakeNode, FakeEdge]:
    network.add_node(FakeNode(name="A"))
    network.add_node(FakeNode(name="B"))
    return network


class TestProtocolConformance:
    def test_fake_node_satisfies_node_protocol(self) -> None:
        assert isinstance(FakeNode(name="A"), Node)

    def test_fake_edge_satisfies_edge_protocol(self) -> None:
        assert isinstance(FakeEdge(name="p1"), Edge)


class TestAddNode:
    def test_adds_successfully(self, network: PipelineNetwork[FakeNode, FakeEdge]) -> None:
        network.add_node(FakeNode(name="A"))
        assert network.get_node("A").name == "A"
        assert len(network) == 1

    def test_nodes_property_reflects_added_nodes(
        self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        assert {node.name for node in two_node_network.nodes} == {"A", "B"}

    def test_duplicate_name_raises(self, network: PipelineNetwork[FakeNode, FakeEdge]) -> None:
        network.add_node(FakeNode(name="A"))
        with pytest.raises(DuplicateNodeError):
            network.add_node(FakeNode(name="A"))


class TestAddEdge:
    def test_adds_successfully(self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]) -> None:
        two_node_network.add_edge(FakeEdge(name="pipe1"), "A", "B")
        assert two_node_network.get_edge("pipe1").name == "pipe1"
        assert len(two_node_network.edges) == 1

    def test_duplicate_name_raises(
        self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        two_node_network.add_edge(FakeEdge(name="pipe1"), "A", "B")
        with pytest.raises(DuplicateEdgeError):
            two_node_network.add_edge(FakeEdge(name="pipe1"), "A", "B")

    def test_unknown_from_node_raises(
        self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        with pytest.raises(UnknownNodeError):
            two_node_network.add_edge(FakeEdge(name="pipe1"), "nonexistent", "B")

    def test_unknown_to_node_raises(
        self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        with pytest.raises(UnknownNodeError):
            two_node_network.add_edge(FakeEdge(name="pipe1"), "A", "nonexistent")

    def test_parallel_edges_between_same_two_nodes_are_allowed(
        self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        # A looped/redundant pipe run — two separate pipes connecting the
        # same two nodes. This is exactly what the v1 solver couldn't
        # represent at all.
        two_node_network.add_edge(FakeEdge(name="pipe1"), "A", "B")
        two_node_network.add_edge(FakeEdge(name="pipe2"), "A", "B")
        assert len(two_node_network.edges) == 2


class TestGetters:
    def test_get_node_raises_for_unknown_name(
        self, network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        with pytest.raises(UnknownNodeError):
            network.get_node("nonexistent")

    def test_get_edge_raises_for_unknown_name(
        self, network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        with pytest.raises(UnknownEdgeError):
            network.get_edge("nonexistent")


class TestEdgeEndpoints:
    def test_returns_endpoints_in_reference_direction(
        self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        two_node_network.add_edge(FakeEdge(name="pipe1"), "A", "B")
        assert two_node_network.edge_endpoints("pipe1") == ("A", "B")

    def test_raises_for_unknown_edge(self, network: PipelineNetwork[FakeNode, FakeEdge]) -> None:
        with pytest.raises(UnknownEdgeError):
            network.edge_endpoints("nonexistent")


class TestIncidentEdges:
    def test_finds_edges_in_both_reference_directions(
        self, network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        # B is the *to* node of pipe1 and the *from* node of pipe2 —
        # incident_edges should find both regardless of which role B
        # played in each edge's reference direction.
        network.add_node(FakeNode(name="A"))
        network.add_node(FakeNode(name="B"))
        network.add_node(FakeNode(name="C"))
        network.add_edge(FakeEdge(name="pipe1"), "A", "B")
        network.add_edge(FakeEdge(name="pipe2"), "B", "C")

        incident = {edge.name for edge in network.incident_edges("B")}
        assert incident == {"pipe1", "pipe2"}

    def test_raises_for_unknown_node(self, network: PipelineNetwork[FakeNode, FakeEdge]) -> None:
        with pytest.raises(UnknownNodeError):
            network.incident_edges("nonexistent")


class TestNeighbors:
    def test_finds_neighbors_in_both_reference_directions(
        self, network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        network.add_node(FakeNode(name="A"))
        network.add_node(FakeNode(name="B"))
        network.add_node(FakeNode(name="C"))
        network.add_edge(FakeEdge(name="pipe1"), "A", "B")
        network.add_edge(FakeEdge(name="pipe2"), "C", "B")  # B is the *to* node here

        assert set(network.neighbors("B")) == {"A", "C"}

    def test_raises_for_unknown_node(self, network: PipelineNetwork[FakeNode, FakeEdge]) -> None:
        with pytest.raises(UnknownNodeError):
            network.neighbors("nonexistent")


class TestConnectivity:
    def test_empty_network_is_vacuously_connected(
        self, network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        assert network.is_connected() is True

    def test_single_node_is_connected(self, network: PipelineNetwork[FakeNode, FakeEdge]) -> None:
        network.add_node(FakeNode(name="A"))
        assert network.is_connected() is True

    def test_connected_network_is_connected(
        self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        two_node_network.add_edge(FakeEdge(name="pipe1"), "A", "B")
        assert two_node_network.is_connected() is True

    def test_two_isolated_nodes_are_not_connected(
        self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        # A and B added but never joined by an edge.
        assert two_node_network.is_connected() is False

    def test_two_separate_components_are_not_connected(
        self, network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        network.add_node(FakeNode(name="A"))
        network.add_node(FakeNode(name="B"))
        network.add_node(FakeNode(name="C"))
        network.add_node(FakeNode(name="D"))
        network.add_edge(FakeEdge(name="pipe1"), "A", "B")
        network.add_edge(FakeEdge(name="pipe2"), "C", "D")
        # {A, B} and {C, D} are each internally connected but not to each other.
        assert network.is_connected() is False


class TestCircuitRank:
    """The direct proof that this model represents real network topology,
    not just a series string with extra steps — a v1-shaped network
    (series only) always has circuit_rank == 0, same as a tree. Anything
    with an actual loop — parallel pipes or a longer cycle — is exactly
    what pushes circuit_rank above 0, and this is the quantity a
    loop-flow network solver needs to know how many correction equations
    to set up."""

    def test_empty_network_has_zero_circuit_rank(
        self, network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        assert network.circuit_rank == 0

    def test_series_string_has_zero_circuit_rank(
        self, network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        # A -> B -> C -> D: exactly what the v1 solver could represent.
        for name in ("A", "B", "C", "D"):
            network.add_node(FakeNode(name=name))
        network.add_edge(FakeEdge(name="p1"), "A", "B")
        network.add_edge(FakeEdge(name="p2"), "B", "C")
        network.add_edge(FakeEdge(name="p3"), "C", "D")
        assert network.circuit_rank == 0

    def test_branched_network_has_zero_circuit_rank(
        self, network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        # A genuine branch — two wells feeding one manifold, manifold
        # feeding one outlet — is a tree (no redundant path between any
        # two points), so circuit_rank is still 0, but the topology
        # itself is something the v1 solver's plain list could never
        # represent at all: a node with more than two connections.
        for name in ("well_1", "well_2", "manifold", "outlet"):
            network.add_node(FakeNode(name=name))
        network.add_edge(FakeEdge(name="flowline_1"), "well_1", "manifold")
        network.add_edge(FakeEdge(name="flowline_2"), "well_2", "manifold")
        network.add_edge(FakeEdge(name="trunk_line"), "manifold", "outlet")

        assert network.circuit_rank == 0
        assert len(network.incident_edges("manifold")) == 3
        assert set(network.neighbors("manifold")) == {"well_1", "well_2", "outlet"}

    def test_parallel_pipes_give_circuit_rank_one(
        self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        two_node_network.add_edge(FakeEdge(name="pipe1"), "A", "B")
        two_node_network.add_edge(FakeEdge(name="pipe2"), "A", "B")
        assert two_node_network.circuit_rank == 1

    def test_three_node_cycle_gives_circuit_rank_one(
        self, network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        for name in ("A", "B", "C"):
            network.add_node(FakeNode(name=name))
        network.add_edge(FakeEdge(name="p1"), "A", "B")
        network.add_edge(FakeEdge(name="p2"), "B", "C")
        network.add_edge(FakeEdge(name="p3"), "C", "A")
        assert network.circuit_rank == 1

    def test_two_independent_loops_give_circuit_rank_two(
        self, network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        # A-B-C-A triangle, plus a second independent loop C-D-E-C
        # sharing only node C with the first.
        for name in ("A", "B", "C", "D", "E"):
            network.add_node(FakeNode(name=name))
        network.add_edge(FakeEdge(name="p1"), "A", "B")
        network.add_edge(FakeEdge(name="p2"), "B", "C")
        network.add_edge(FakeEdge(name="p3"), "C", "A")
        network.add_edge(FakeEdge(name="p4"), "C", "D")
        network.add_edge(FakeEdge(name="p5"), "D", "E")
        network.add_edge(FakeEdge(name="p6"), "E", "C")
        assert network.circuit_rank == 2


class TestValidate:
    def test_empty_network_raises(self, network: PipelineNetwork[FakeNode, FakeEdge]) -> None:
        with pytest.raises(DisconnectedNetworkError):
            network.validate()

    def test_disconnected_network_raises(
        self, network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        network.add_node(FakeNode(name="A"))
        network.add_node(FakeNode(name="B"))
        network.add_node(FakeNode(name="C"))
        network.add_node(FakeNode(name="D"))
        network.add_edge(FakeEdge(name="p1"), "A", "B")
        network.add_edge(FakeEdge(name="p2"), "C", "D")
        with pytest.raises(DisconnectedNetworkError, match=r"2 disconnected"):
            network.validate()

    def test_connected_network_does_not_raise(
        self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        two_node_network.add_edge(FakeEdge(name="pipe1"), "A", "B")
        two_node_network.validate()  # should not raise


class TestDunderMethods:
    def test_len_reflects_node_count(
        self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        assert len(two_node_network) == 2

    def test_repr_includes_name_and_counts(
        self, two_node_network: PipelineNetwork[FakeNode, FakeEdge]
    ) -> None:
        two_node_network.add_edge(FakeEdge(name="pipe1"), "A", "B")
        text = repr(two_node_network)
        assert "test-network" in text
        assert "nodes=2" in text
        assert "edges=1" in text
