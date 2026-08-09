"""
Pipeline network topology: nodes and edges as a real graph.

This directly addresses the single biggest structural limitation found in
the v1 review: the old solver only ever walked a linear list of pipes
(`solve_pipeline()`), which meant it could represent a series string and
nothing else — no branching manifold feeding two downstream lines, no
looped gathering system with redundant paths. `PipelineNetwork` here is a
real graph from the start; whether a given network happens to be a simple
series string or a multi-branch system with loops is just a property of
which nodes and edges got added, not a constraint baked into the data
structure.

The underlying graph is directed (`networkx.MultiDiGraph`), but that
direction is a *sign convention* for the eventually-solved flow rate, not
a physical constraint — a real pipe carries flow in whichever direction
the pressures actually drive it, which the solver (arriving in Phase 2)
determines. `add_edge(edge, from_node, to_node)` just fixes which
direction counts as positive for that edge's solved flow. Parallel edges
(more than one pipe between the same two nodes — a looped or redundant
run) are supported directly via the multigraph, not worked around.
"""

import typing

import networkx as nx

from flowline_scada.domain.errors import (
    DisconnectedNetworkError,
    DuplicateEdgeError,
    DuplicateNodeError,
    UnknownEdgeError,
    UnknownNodeError,
)


@typing.runtime_checkable
class Node(typing.Protocol):
    """Structural protocol any node type must satisfy. See
    `domain.components` for concrete node types (Junction, Boundary,
    Manifold, Separator) — this module only needs a name.

    `name` is declared as a read-only property, not a plain attribute:
    with a plain `name: str`, mypy treats it as a read-write protocol
    member, which every frozen attrs class in this codebase (immutable by
    design) would then fail to satisfy structurally, since a frozen
    attribute isn't settable. Declaring it as a property fixes that
    without weakening the protocol for anything that actually needs it.
    """

    @property
    def name(self) -> str: ...


@typing.runtime_checkable
class Edge(typing.Protocol):
    """Structural protocol any edge type must satisfy. See
    `domain.components` for concrete edge types (Pipe, Valve, Pump,
    Regulator) — this module only needs a name. See `Node` above for why
    this is a property rather than a plain attribute."""

    @property
    def name(self) -> str: ...


NodeT = typing.TypeVar("NodeT", bound=Node)
EdgeT = typing.TypeVar("EdgeT", bound=Edge)


class PipelineNetwork(typing.Generic[NodeT, EdgeT]):
    """A pipeline network: nodes connected by edges, as an actual graph."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._nodes: dict[str, NodeT] = {}
        self._edges: dict[str, EdgeT] = {}
        # (from_node, to_node, multigraph_key) per edge name, tracked
        # directly here rather than round-tripped through networkx's own
        # edge-data attribute lookups — this is all simple bookkeeping,
        # and keeping it in a plain dict means the handful of lookups
        # below (incident_edges, neighbors, edge_endpoints) don't depend
        # on getting networkx's data-attribute API exactly right.
        # networkx itself is doing real work elsewhere: connectivity and
        # circuit-rank (independent loop count) below are genuine
        # graph-theoretic questions worth a real library, not
        # hand-rolled bookkeeping.
        self._edge_keys: dict[str, tuple[str, str, int]] = {}

    def add_node(self, node: NodeT) -> None:
        if node.name in self._nodes:
            raise DuplicateNodeError(
                f"Network {self.name!r} already has a node named {node.name!r}."
            )
        self._nodes[node.name] = node
        self._graph.add_node(node.name)

    def add_edge(self, edge: EdgeT, from_node: str, to_node: str) -> None:
        """Connect `from_node` to `to_node` via `edge`. This direction is
        the sign-convention reference for the edge's eventual solved flow
        rate, not a constraint on which way flow can actually go."""
        if edge.name in self._edges:
            raise DuplicateEdgeError(
                f"Network {self.name!r} already has an edge named {edge.name!r}."
            )
        for node_name in (from_node, to_node):
            if node_name not in self._nodes:
                raise UnknownNodeError(
                    f"Cannot add edge {edge.name!r}: node {node_name!r} is not "
                    f"in network {self.name!r}. Add it with add_node() first."
                )
        key = self._graph.add_edge(from_node, to_node)
        self._edges[edge.name] = edge
        self._edge_keys[edge.name] = (from_node, to_node, key)

    @property
    def nodes(self) -> tuple[NodeT, ...]:
        return tuple(self._nodes.values())

    @property
    def edges(self) -> tuple[EdgeT, ...]:
        return tuple(self._edges.values())

    def get_node(self, name: str) -> NodeT:
        try:
            return self._nodes[name]
        except KeyError:
            raise UnknownNodeError(f"Network {self.name!r} has no node named {name!r}.") from None

    def get_edge(self, name: str) -> EdgeT:
        try:
            return self._edges[name]
        except KeyError:
            raise UnknownEdgeError(f"Network {self.name!r} has no edge named {name!r}.") from None

    def edge_endpoints(self, edge_name: str) -> tuple[str, str]:
        """(from_node, to_node) in the edge's reference direction."""
        if edge_name not in self._edge_keys:
            raise UnknownEdgeError(f"Network {self.name!r} has no edge named {edge_name!r}.")
        from_node, to_node, _key = self._edge_keys[edge_name]
        return from_node, to_node

    def incident_edges(self, node_name: str) -> tuple[EdgeT, ...]:
        """Every edge touching this node, in either reference direction."""
        if node_name not in self._nodes:
            raise UnknownNodeError(f"Network {self.name!r} has no node named {node_name!r}.")
        names = [
            name
            for name, (u, v, _key) in self._edge_keys.items()
            if u == node_name or v == node_name
        ]
        return tuple(self._edges[name] for name in names)

    def neighbors(self, node_name: str) -> tuple[str, ...]:
        """Every node directly connected to this one, in either reference
        direction — a pipe's reference direction doesn't limit which way
        it can be traversed when just asking "what's connected to what\"."""
        if node_name not in self._nodes:
            raise UnknownNodeError(f"Network {self.name!r} has no node named {node_name!r}.")
        result: set[str] = set()
        for u, v, _key in self._edge_keys.values():
            if u == node_name:
                result.add(v)
            elif v == node_name:
                result.add(u)
        return tuple(sorted(result))

    def is_connected(self) -> bool:
        """Whether every node can reach every other, ignoring edge
        direction (a real pipe network's connectivity doesn't care which
        way is "reference forward\")."""
        if not self._nodes:
            return True
        return bool(nx.is_weakly_connected(self._graph))

    @property
    def circuit_rank(self) -> int:
        """Number of independent loops in the topology — the cyclomatic
        number / circuit rank, |E| - |V| + (number of connected
        components). 0 for a tree (which includes the degenerate case of
        a plain series string, the only shape the v1 solver could
        represent); >=1 for anything with a redundant path between two
        points, whether that's a pair of parallel pipes or a longer cycle
        through several nodes. This is the same quantity a Hardy-Cross-style
        loop-flow solver needs to know how many loop-correction equations
        it has to solve — not just a connectivity nicety."""
        if not self._nodes:
            return 0
        return (
            self._graph.number_of_edges()
            - self._graph.number_of_nodes()
            + nx.number_weakly_connected_components(self._graph)
        )

    def validate(self) -> None:
        """Raise if the network isn't in a solvable shape: at least one
        node, and every node reachable from every other."""
        if not self._nodes:
            raise DisconnectedNetworkError(f"Network {self.name!r} has no nodes.")
        if not self.is_connected():
            components = [sorted(c) for c in nx.weakly_connected_components(self._graph)]
            raise DisconnectedNetworkError(
                f"Network {self.name!r} has {len(components)} disconnected "
                f"groups of nodes instead of one connected network: {components}"
            )

    def __len__(self) -> int:
        return len(self._nodes)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.name!r}, "
            f"nodes={len(self._nodes)}, edges={len(self._edges)})"
        )
