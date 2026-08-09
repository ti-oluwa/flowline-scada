"""Tests for flowline_scada.domain.components."""

import typing

import attrs
import pytest

from flowline_scada.domain.components import (
    Boundary,
    Junction,
    Pipe,
    PipeLeak,
    Valve,
    ValveType,
)
from flowline_scada.domain.errors import DuplicateLeakError, UnknownLeakError
from flowline_scada.domain.network import Edge, Node, PipelineNetwork
from flowline_scada.domain.units import Quantity


class TestJunction:
    def test_construction(self) -> None:
        junction = Junction(name="J1")
        assert junction.name == "J1"

    def test_is_frozen(self) -> None:
        junction = Junction(name="J1")
        with pytest.raises(attrs.exceptions.FrozenInstanceError):
            junction.name = "J2"  # type: ignore[misc]

    def test_satisfies_node_protocol(self) -> None:
        assert isinstance(Junction(name="J1"), Node)


class TestBoundary:
    def test_pressure_only_construction(self) -> None:
        boundary = Boundary(name="well_1", pressure=Quantity(800, "psi"))
        assert boundary.is_pressure_boundary
        assert not boundary.is_flow_boundary
        assert boundary.pressure == Quantity(800, "psi")
        assert boundary.flow_rate is None

    def test_flow_rate_only_construction(self) -> None:
        boundary = Boundary(name="well_1", flow_rate=Quantity(500, "ft^3/s"))
        assert boundary.is_flow_boundary
        assert not boundary.is_pressure_boundary
        assert boundary.flow_rate == Quantity(500, "ft^3/s")
        assert boundary.pressure is None

    def test_both_specified_raises(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            Boundary(name="bad", pressure=Quantity(800, "psi"), flow_rate=Quantity(500, "ft^3/s"))

    def test_neither_specified_raises(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            Boundary(name="bad")

    def test_wrong_dimensionality_for_pressure_raises(self) -> None:
        with pytest.raises(ValueError, match="dimensionality"):
            Boundary(name="bad", pressure=Quantity(10, "ft"))

    def test_wrong_dimensionality_for_flow_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="dimensionality"):
            Boundary(name="bad", flow_rate=Quantity(10, "psi"))

    def test_set_pressure_switches_from_flow_boundary(self) -> None:
        boundary = Boundary(name="well_1", flow_rate=Quantity(500, "ft^3/s"))
        boundary.set_pressure(Quantity(800, "psi"))
        assert boundary.is_pressure_boundary
        assert not boundary.is_flow_boundary
        assert boundary.flow_rate is None

    def test_set_flow_rate_switches_from_pressure_boundary(self) -> None:
        boundary = Boundary(name="well_1", pressure=Quantity(800, "psi"))
        boundary.set_flow_rate(Quantity(500, "ft^3/s"))
        assert boundary.is_flow_boundary
        assert not boundary.is_pressure_boundary
        assert boundary.pressure is None

    def test_set_pressure_with_wrong_dimensionality_leaves_state_unchanged(self) -> None:
        boundary = Boundary(name="well_1", pressure=Quantity(800, "psi"))
        with pytest.raises(ValueError, match="dimensionality"):
            boundary.set_pressure(Quantity(10, "ft"))
        # The failed call must not have partially mutated state — still
        # the original pressure boundary, not switched to an invalid one.
        assert boundary.pressure == Quantity(800, "psi")
        assert boundary.is_pressure_boundary

    def test_satisfies_node_protocol(self) -> None:
        assert isinstance(Boundary(name="well_1", pressure=Quantity(800, "psi")), Node)


class TestPipeLeak:
    def test_construction(self) -> None:
        leak = PipeLeak(name="L1", location=0.5, diameter=Quantity(0.5, "inch"))
        assert leak.name == "L1"
        assert leak.location == 0.5
        assert leak.active is True
        assert leak.discharge_coefficient == 0.61

    def test_location_at_lower_bound_is_valid(self) -> None:
        PipeLeak(name="L1", location=0.0, diameter=Quantity(0.5, "inch"))

    def test_location_at_upper_bound_is_valid(self) -> None:
        PipeLeak(name="L1", location=1.0, diameter=Quantity(0.5, "inch"))

    def test_location_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            PipeLeak(name="L1", location=-0.1, diameter=Quantity(0.5, "inch"))

    def test_location_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            PipeLeak(name="L1", location=1.1, diameter=Quantity(0.5, "inch"))

    def test_zero_diameter_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            PipeLeak(name="L1", location=0.5, diameter=Quantity(0, "inch"))

    def test_wrong_diameter_dimensionality_raises(self) -> None:
        with pytest.raises(ValueError, match="dimensionality"):
            PipeLeak(name="L1", location=0.5, diameter=Quantity(1, "psi"))

    def test_discharge_coefficient_of_one_is_valid(self) -> None:
        PipeLeak(name="L1", location=0.5, diameter=Quantity(0.5, "inch"), discharge_coefficient=1.0)

    def test_discharge_coefficient_of_zero_raises(self) -> None:
        with pytest.raises(ValueError, match=r"\(0, 1\]"):
            PipeLeak(
                name="L1", location=0.5, diameter=Quantity(0.5, "inch"), discharge_coefficient=0.0
            )

    def test_discharge_coefficient_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match=r"\(0, 1\]"):
            PipeLeak(
                name="L1", location=0.5, diameter=Quantity(0.5, "inch"), discharge_coefficient=1.5
            )

    def test_location_revalidates_on_mutation(self) -> None:
        leak = PipeLeak(name="L1", location=0.5, diameter=Quantity(0.5, "inch"))
        with pytest.raises(ValueError, match="between 0 and 1"):
            leak.location = 1.5
        assert leak.location == 0.5  # unchanged after the rejected mutation

    def test_active_can_be_toggled(self) -> None:
        leak = PipeLeak(name="L1", location=0.5, diameter=Quantity(0.5, "inch"), active=True)
        leak.active = False
        assert leak.active is False


class TestPipe:
    def test_construction_with_required_fields_only(self) -> None:
        pipe = Pipe(name="P1", length=Quantity(1000, "ft"), internal_diameter=Quantity(6, "inch"))
        assert pipe.name == "P1"
        assert pipe.roughness == Quantity(0.0, "m")
        assert pipe.elevation_change == Quantity(0.0, "m")
        assert pipe.leaks == ()

    def test_zero_length_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            Pipe(name="P1", length=Quantity(0, "ft"), internal_diameter=Quantity(6, "inch"))

    def test_zero_diameter_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            Pipe(name="P1", length=Quantity(1000, "ft"), internal_diameter=Quantity(0, "inch"))

    def test_negative_roughness_raises(self) -> None:
        with pytest.raises(ValueError, match="must be non-negative"):
            Pipe(
                name="P1",
                length=Quantity(1000, "ft"),
                internal_diameter=Quantity(6, "inch"),
                roughness=Quantity(-0.001, "m"),
            )

    def test_negative_elevation_change_is_valid(self) -> None:
        # A downhill run — negative elevation change is physically normal,
        # unlike length/diameter/roughness which must be non-negative.
        pipe = Pipe(
            name="P1",
            length=Quantity(1000, "ft"),
            internal_diameter=Quantity(6, "inch"),
            elevation_change=Quantity(-50, "ft"),
        )
        assert pipe.elevation_change == Quantity(-50, "ft")

    def test_construction_with_leaks_list(self) -> None:
        leak_1 = PipeLeak(name="L1", location=0.3, diameter=Quantity(0.5, "inch"))
        leak_2 = PipeLeak(name="L2", location=0.7, diameter=Quantity(0.3, "inch"))
        pipe = Pipe(
            name="P1",
            length=Quantity(1000, "ft"),
            internal_diameter=Quantity(6, "inch"),
            leaks=[leak_1, leak_2],
        )
        assert {leak.name for leak in pipe.leaks} == {"L1", "L2"}

    def test_duplicate_leak_names_at_construction_raises(self) -> None:
        leak_1 = PipeLeak(name="L1", location=0.3, diameter=Quantity(0.5, "inch"))
        leak_2 = PipeLeak(name="L1", location=0.7, diameter=Quantity(0.3, "inch"))
        with pytest.raises(DuplicateLeakError):
            Pipe(
                name="P1",
                length=Quantity(1000, "ft"),
                internal_diameter=Quantity(6, "inch"),
                leaks=[leak_1, leak_2],
            )

    def test_add_leak(self) -> None:
        pipe = Pipe(name="P1", length=Quantity(1000, "ft"), internal_diameter=Quantity(6, "inch"))
        leak = PipeLeak(name="L1", location=0.5, diameter=Quantity(0.5, "inch"))
        pipe.add_leak(leak)
        assert pipe.get_leak("L1") is leak

    def test_add_duplicate_leak_raises(self) -> None:
        pipe = Pipe(name="P1", length=Quantity(1000, "ft"), internal_diameter=Quantity(6, "inch"))
        pipe.add_leak(PipeLeak(name="L1", location=0.5, diameter=Quantity(0.5, "inch")))
        with pytest.raises(DuplicateLeakError):
            pipe.add_leak(PipeLeak(name="L1", location=0.2, diameter=Quantity(0.3, "inch")))

    def test_remove_leak(self) -> None:
        pipe = Pipe(name="P1", length=Quantity(1000, "ft"), internal_diameter=Quantity(6, "inch"))
        pipe.add_leak(PipeLeak(name="L1", location=0.5, diameter=Quantity(0.5, "inch")))
        pipe.remove_leak("L1")
        assert pipe.leaks == ()

    def test_remove_unknown_leak_raises(self) -> None:
        pipe = Pipe(name="P1", length=Quantity(1000, "ft"), internal_diameter=Quantity(6, "inch"))
        with pytest.raises(UnknownLeakError):
            pipe.remove_leak("nonexistent")

    def test_get_unknown_leak_raises(self) -> None:
        pipe = Pipe(name="P1", length=Quantity(1000, "ft"), internal_diameter=Quantity(6, "inch"))
        with pytest.raises(UnknownLeakError):
            pipe.get_leak("nonexistent")

    def test_mutation_revalidates(self) -> None:
        pipe = Pipe(name="P1", length=Quantity(1000, "ft"), internal_diameter=Quantity(6, "inch"))
        with pytest.raises(ValueError, match="must be positive"):
            pipe.length = Quantity(-5, "ft")
        assert pipe.length == Quantity(1000, "ft")

    def test_satisfies_edge_protocol(self) -> None:
        pipe = Pipe(name="P1", length=Quantity(1000, "ft"), internal_diameter=Quantity(6, "inch"))
        assert isinstance(pipe, Edge)


class TestValveType:
    def test_members_behave_as_strings(self) -> None:
        assert ValveType.GATE == "gate"
        assert ValveType.CONTROL == "control"

    def test_has_expected_members(self) -> None:
        assert {member.value for member in ValveType} == {
            "gate",
            "globe",
            "ball",
            "check",
            "control",
        }


class TestValve:
    def test_defaults(self) -> None:
        valve = Valve(name="V1")
        assert valve.valve_type == ValveType.GATE
        assert valve.position == 1.0
        assert valve.is_fully_open
        assert valve.is_open
        assert not valve.is_closed

    def test_position_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            Valve(name="V1", position=-0.1)

    def test_position_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            Valve(name="V1", position=1.1)

    def test_partially_open_state(self) -> None:
        valve = Valve(name="V1", position=0.5)
        assert valve.is_open
        assert not valve.is_closed
        assert not valve.is_fully_open

    def test_close_sets_position_to_zero(self) -> None:
        valve = Valve(name="V1")
        valve.close()
        assert valve.position == 0.0
        assert valve.is_closed
        assert not valve.is_open

    def test_open_sets_position_to_one(self) -> None:
        valve = Valve(name="V1", position=0.0)
        valve.open()
        assert valve.position == 1.0
        assert valve.is_fully_open

    def test_control_valve_type(self) -> None:
        valve = Valve(name="PCV-101", valve_type=ValveType.CONTROL, position=0.35)
        assert valve.valve_type == ValveType.CONTROL
        assert 0.0 < valve.position < 1.0

    def test_satisfies_edge_protocol(self) -> None:
        assert isinstance(Valve(name="V1"), Edge)


class TestNetworkIntegration:
    """A pipe-valve-pipe run through an intermediate junction — proving
    the "valve is its own edge type, not a field on Pipe" design decision
    actually composes the way the module docstring claims it does."""

    def test_pipe_valve_pipe_series_via_junction(self) -> None:
        network: PipelineNetwork[Junction, typing.Any] = PipelineNetwork(name="test")
        network.add_node(Junction(name="upstream"))
        network.add_node(Junction(name="valve_inlet"))
        network.add_node(Junction(name="valve_outlet"))
        network.add_node(Junction(name="downstream"))

        pipe_1 = Pipe(name="P1", length=Quantity(500, "ft"), internal_diameter=Quantity(6, "inch"))
        valve = Valve(name="V1", valve_type=ValveType.GATE)
        pipe_2 = Pipe(name="P2", length=Quantity(500, "ft"), internal_diameter=Quantity(6, "inch"))

        network.add_edge(pipe_1, from_node="upstream", to_node="valve_inlet")
        network.add_edge(valve, from_node="valve_inlet", to_node="valve_outlet")
        network.add_edge(pipe_2, from_node="valve_outlet", to_node="downstream")

        network.validate()  # should not raise — fully connected
        assert network.circuit_rank == 0
        assert [edge.name for edge in network.incident_edges("valve_inlet")] == ["P1", "V1"]

    def test_boundary_nodes_with_a_pipe_between_them(self) -> None:
        network: PipelineNetwork[typing.Any, Pipe] = PipelineNetwork(name="test")
        network.add_node(Boundary(name="well_1", pressure=Quantity(900, "psi")))
        network.add_node(Boundary(name="delivery", flow_rate=Quantity(200, "ft^3/s")))
        network.add_edge(
            Pipe(
                name="flowline", length=Quantity(5000, "ft"), internal_diameter=Quantity(8, "inch")
            ),
            from_node="well_1",
            to_node="delivery",
        )
        network.validate()
        assert network.circuit_rank == 0
