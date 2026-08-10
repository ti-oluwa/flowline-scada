"""
Pipeline network topology: connect nodes and edges into a real graph.

Use this when your pipeline isn't just one straight run of pipe — a
manifold feeding two downstream lines, a looped gathering system with
redundant paths, anything with real branching or loops. If you only ever
need a simple series of pipes, this still works fine; it just means your
network happens to have every node with at most two connections.

Example — a simple branching gathering system, two wells feeding one
manifold, one outlet downstream:

```python
from flowline_scada.domain.network import PipelineNetwork
from flowline_scada.domain.components import Boundary, Manifold, Pipe
from flowline_scada.domain.units import Quantity

network = PipelineNetwork(name="gathering-system")
network.add_node(Boundary(name="well_1", pressure=Quantity(900, "psi")))
network.add_node(Boundary(name="well_2", pressure=Quantity(850, "psi")))
network.add_node(Manifold(name="manifold_1"))
network.add_node(Boundary(name="outlet", flow_rate=Quantity(1000, "ft^3/s")))

network.add_edge(
    Pipe(name="fl_1", length=Quantity(2000, "ft"), internal_diameter=Quantity(6, "inch")),
    from_node="well_1", to_node="manifold_1",
)
network.add_edge(
    Pipe(name="fl_2", length=Quantity(1800, "ft"), internal_diameter=Quantity(6, "inch")),
    from_node="well_2", to_node="manifold_1",
)
network.add_edge(
    Pipe(name="trunk", length=Quantity(5000, "ft"), internal_diameter=Quantity(10, "inch")),
    from_node="manifold_1", to_node="outlet",
)

network.validate()  # raises if anything isn't connected up correctly
print(network.circuit_rank)  # 0 — this is a branching network, but not a looped one
```
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
    """What any node type needs to provide to be usable in a
    :class:`PipelineNetwork` — just a name. You don't need to inherit
    from this; any object with a ``name`` works, including everything in
    :mod:`flowline_scada.domain.components` (:class:`~flowline_scada.domain.components.Junction`,
    :class:`~flowline_scada.domain.components.Boundary`, etc.) and any
    custom node type you define yourself.
    """

    @property
    def name(self) -> str: ...


@typing.runtime_checkable
class Edge(typing.Protocol):
    """What any edge type needs to provide to be usable in a
    :class:`PipelineNetwork` — just a name, same idea as :class:`Node`.
    Everything in :mod:`flowline_scada.domain.components` that connects
    two nodes (:class:`~flowline_scada.domain.components.Pipe`,
    :class:`~flowline_scada.domain.components.Valve`, etc.) satisfies
    this automatically.
    """

    @property
    def name(self) -> str: ...


NodeT = typing.TypeVar("NodeT", bound=Node)
EdgeT = typing.TypeVar("EdgeT", bound=Edge)


class PipelineNetwork(typing.Generic[NodeT, EdgeT]):
    """A pipeline network: nodes connected by edges, as an actual graph
    rather than a fixed list.

    Every edge is added with a direction (``from_node`` to ``to_node``),
    but that's just a sign-convention reference for whichever way the
    flow ends up solved, not a rule about which way flow is allowed to
    go — a real pipe carries flow whichever way the pressures actually
    drive it. Two nodes can also be connected by more than one edge (a
    looped or redundant pipe run) — that's supported directly, not
    something you need to work around.

    :param name: a label for this network, used in error messages and ``repr()``.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._nodes: dict[str, NodeT] = {}
        self._edges: dict[str, EdgeT] = {}
        self._edge_keys: dict[str, tuple[str, str, int]] = {}

    def add_node(self, node: NodeT) -> None:
        """Add a node to the network.

        :param node: any object with a unique ``name`` — see :class:`Node`.
        :raises ~flowline_scada.domain.errors.DuplicateNodeError: if a
            node with this name is already in the network.
        """
        if node.name in self._nodes:
            raise DuplicateNodeError(
                f"Network {self.name!r} already has a node named {node.name!r}."
            )
        self._nodes[node.name] = node
        self._graph.add_node(node.name)

    def add_edge(self, edge: EdgeT, from_node: str, to_node: str) -> None:
        """Connect two existing nodes with an edge.

        :param edge: any object with a unique ``name`` — see :class:`Edge`.
        :param from_node: name of an existing node — the edge's reference
            "start" (see the class docstring for what this direction
            actually means).
        :param to_node: name of an existing node — the edge's reference "end".
        :raises ~flowline_scada.domain.errors.DuplicateEdgeError: if an
            edge with this name already exists.
        :raises ~flowline_scada.domain.errors.UnknownNodeError: if
            ``from_node`` or ``to_node`` isn't in the network yet — add
            both nodes first with :meth:`add_node`.

        Example:

        ```python
        network.add_node(Junction(name="A"))
        network.add_node(Junction(name="B"))
        network.add_edge(Pipe(name="P1", ...), from_node="A", to_node="B")
        ```
        """
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
        """Every node currently in the network, in the order they were added."""
        return tuple(self._nodes.values())

    @property
    def edges(self) -> tuple[EdgeT, ...]:
        """Every edge currently in the network, in the order they were added."""
        return tuple(self._edges.values())

    def get_node(self, name: str) -> NodeT:
        """Look up a node by name.

        :param name: the node's name.
        :return: the node.
        :raises ~flowline_scada.domain.errors.UnknownNodeError: if no
            node with that name exists.
        """
        try:
            return self._nodes[name]
        except KeyError:
            raise UnknownNodeError(f"Network {self.name!r} has no node named {name!r}.") from None

    def get_edge(self, name: str) -> EdgeT:
        """Look up an edge by name.

        :param name: the edge's name.
        :return: the edge.
        :raises ~flowline_scada.domain.errors.UnknownEdgeError: if no
            edge with that name exists.
        """
        try:
            return self._edges[name]
        except KeyError:
            raise UnknownEdgeError(f"Network {self.name!r} has no edge named {name!r}.") from None

    def edge_endpoints(self, edge_name: str) -> tuple[str, str]:
        """Look up which nodes an edge connects.

        :param edge_name: the edge's name.
        :return: a ``(from_node, to_node)`` tuple, in the edge's reference direction.
        :raises ~flowline_scada.domain.errors.UnknownEdgeError: if no
            edge with that name exists.
        """
        if edge_name not in self._edge_keys:
            raise UnknownEdgeError(f"Network {self.name!r} has no edge named {edge_name!r}.")
        from_node, to_node, _key = self._edge_keys[edge_name]
        return from_node, to_node

    def incident_edges(self, node_name: str) -> tuple[EdgeT, ...]:
        """Find every edge touching a node.

        :param node_name: the node's name.
        :return: every edge connected to this node, in either reference direction.
        :raises ~flowline_scada.domain.errors.UnknownNodeError: if no
            node with that name exists.
        """
        if node_name not in self._nodes:
            raise UnknownNodeError(f"Network {self.name!r} has no node named {node_name!r}.")
        names = [
            name
            for name, (u, v, _key) in self._edge_keys.items()
            if u == node_name or v == node_name
        ]
        return tuple(self._edges[name] for name in names)

    def neighbors(self, node_name: str) -> tuple[str, ...]:
        """Find every node directly connected to a given node.

        :param node_name: the node's name.
        :return: the names of every directly-connected node, in either
            reference direction.
        :raises ~flowline_scada.domain.errors.UnknownNodeError: if no
            node with that name exists.
        """
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
        """Check whether every node can reach every other node, ignoring
        which way each edge's reference direction points.

        :return: ``True`` if the whole network is one connected group of
            nodes, ``False`` if any node is unreachable from the rest.
        """
        if not self._nodes:
            return True
        return bool(nx.is_weakly_connected(self._graph))

    @property
    def circuit_rank(self) -> int:
        """How many independent loops the network's topology contains.

        This is 0 for anything tree-shaped — including the simplest case,
        a single series string of pipes — and 1 or more for a network
        with a redundant path between two points, whether that's a pair
        of parallel pipes or a longer loop through several nodes.

        If you're building a loop-flow solver later, this is the number
        of independent loop-correction equations it needs to set up —
        not just a "does this have a loop" nicety.
        """
        if not self._nodes:
            return 0
        return (
            self._graph.number_of_edges()
            - self._graph.number_of_nodes()
            + nx.number_weakly_connected_components(self._graph)
        )

    def validate(self) -> None:
        """Check that the network is in a solvable shape: at least one
        node, and every node reachable from every other.

        :raises ~flowline_scada.domain.errors.DisconnectedNetworkError:
            if the network is empty, or if it has more than one
            disconnected group of nodes.
        """
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
