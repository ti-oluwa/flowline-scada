"""Tests for flowline_scada.domain.components."""

import typing

import attrs
import pytest

from flowline_scada.domain.components import (
    ArtificialLiftType,
    Boundary,
    Choke,
    ChokeType,
    Compressor,
    ControlLoop,
    HeatExchanger,
    Instrument,
    Junction,
    Manifold,
    MeasuredVariable,
    Pipe,
    PipeLeak,
    Pump,
    Regulator,
    RegulatorType,
    Separator,
    SeparatorType,
    Tank,
    TankType,
    Valve,
    ValveType,
    Well,
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


class TestPump:
    def test_construction(self) -> None:
        pump = Pump(
            name="PUMP-1",
            rated_flow_rate=Quantity(500, "ft^3/s"),
            rated_pressure_boost=Quantity(200, "psi"),
        )
        assert pump.efficiency == 0.75

    def test_zero_rated_flow_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            Pump(
                name="PUMP-1",
                rated_flow_rate=Quantity(0, "ft^3/s"),
                rated_pressure_boost=Quantity(200, "psi"),
            )

    def test_zero_rated_pressure_boost_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            Pump(
                name="PUMP-1",
                rated_flow_rate=Quantity(500, "ft^3/s"),
                rated_pressure_boost=Quantity(0, "psi"),
            )

    def test_efficiency_of_zero_raises(self) -> None:
        with pytest.raises(ValueError, match=r"\(0, 1\]"):
            Pump(
                name="PUMP-1",
                rated_flow_rate=Quantity(500, "ft^3/s"),
                rated_pressure_boost=Quantity(200, "psi"),
                efficiency=0.0,
            )

    def test_efficiency_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match=r"\(0, 1\]"):
            Pump(
                name="PUMP-1",
                rated_flow_rate=Quantity(500, "ft^3/s"),
                rated_pressure_boost=Quantity(200, "psi"),
                efficiency=1.5,
            )

    def test_satisfies_edge_protocol(self) -> None:
        pump = Pump(
            name="PUMP-1",
            rated_flow_rate=Quantity(500, "ft^3/s"),
            rated_pressure_boost=Quantity(200, "psi"),
        )
        assert isinstance(pump, Edge)


class TestRegulator:
    def test_construction_defaults_to_pressure_reducing(self) -> None:
        regulator = Regulator(name="PRV-1", setpoint_pressure=Quantity(500, "psi"))
        assert regulator.regulator_type == RegulatorType.PRESSURE_REDUCING

    def test_back_pressure_type(self) -> None:
        regulator = Regulator(
            name="BPR-1",
            setpoint_pressure=Quantity(500, "psi"),
            regulator_type=RegulatorType.BACK_PRESSURE,
        )
        assert regulator.regulator_type == RegulatorType.BACK_PRESSURE

    def test_zero_setpoint_pressure_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            Regulator(name="PRV-1", setpoint_pressure=Quantity(0, "psi"))

    def test_satisfies_edge_protocol(self) -> None:
        assert isinstance(Regulator(name="PRV-1", setpoint_pressure=Quantity(500, "psi")), Edge)


class TestManifold:
    def test_construction_without_capacity(self) -> None:
        manifold = Manifold(name="MAN-1")
        assert manifold.design_capacity is None

    def test_construction_with_capacity(self) -> None:
        manifold = Manifold(name="MAN-1", design_capacity=Quantity(10000, "ft^3/s"))
        assert manifold.design_capacity == Quantity(10000, "ft^3/s")

    def test_zero_capacity_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            Manifold(name="MAN-1", design_capacity=Quantity(0, "ft^3/s"))

    def test_wrong_capacity_dimensionality_raises(self) -> None:
        with pytest.raises(ValueError, match="dimensionality"):
            Manifold(name="MAN-1", design_capacity=Quantity(100, "psi"))

    def test_is_frozen(self) -> None:
        manifold = Manifold(name="MAN-1")
        with pytest.raises(attrs.exceptions.FrozenInstanceError):
            manifold.name = "MAN-2"  # type: ignore[misc]

    def test_satisfies_node_protocol(self) -> None:
        assert isinstance(Manifold(name="MAN-1"), Node)


class TestSeparator:
    def test_construction_defaults_to_three_phase(self) -> None:
        separator = Separator(
            name="SEP-1",
            operating_pressure=Quantity(300, "psi"),
            operating_temperature=Quantity(100, "degF"),
        )
        assert separator.separator_type == SeparatorType.THREE_PHASE

    def test_two_phase_type(self) -> None:
        separator = Separator(
            name="SEP-1",
            operating_pressure=Quantity(300, "psi"),
            operating_temperature=Quantity(100, "degF"),
            separator_type=SeparatorType.TWO_PHASE,
        )
        assert separator.separator_type == SeparatorType.TWO_PHASE

    def test_zero_operating_pressure_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            Separator(
                name="SEP-1",
                operating_pressure=Quantity(0, "psi"),
                operating_temperature=Quantity(100, "degF"),
            )

    def test_wrong_temperature_dimensionality_raises(self) -> None:
        with pytest.raises(ValueError, match="dimensionality"):
            Separator(
                name="SEP-1",
                operating_pressure=Quantity(300, "psi"),
                operating_temperature=Quantity(100, "psi"),
            )

    def test_satisfies_node_protocol(self) -> None:
        separator = Separator(
            name="SEP-1",
            operating_pressure=Quantity(300, "psi"),
            operating_temperature=Quantity(100, "degF"),
        )
        assert isinstance(separator, Node)


class TestWell:
    def test_pressure_only_construction(self) -> None:
        well = Well(name="WELL-1", pressure=Quantity(1200, "psi"))
        assert well.is_pressure_boundary
        assert well.artificial_lift == ArtificialLiftType.NATURAL_FLOW
        assert well.api_number is None

    def test_flow_rate_only_construction(self) -> None:
        well = Well(name="WELL-1", flow_rate=Quantity(3500, "bbl/day"))
        assert well.is_flow_boundary

    def test_both_specified_raises(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            Well(name="WELL-1", pressure=Quantity(1200, "psi"), flow_rate=Quantity(3500, "bbl/day"))

    def test_neither_specified_raises(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            Well(name="WELL-1")

    def test_wrong_dimensionality_for_pressure_raises(self) -> None:
        with pytest.raises(ValueError, match="dimensionality"):
            Well(name="WELL-1", pressure=Quantity(10, "ft"))

    def test_api_number_and_lift_type_are_stored(self) -> None:
        well = Well(
            name="WELL-1",
            pressure=Quantity(1200, "psi"),
            api_number="42-123-45678",
            artificial_lift=ArtificialLiftType.GAS_LIFT,
        )
        assert well.api_number == "42-123-45678"
        assert well.artificial_lift == ArtificialLiftType.GAS_LIFT

    def test_set_flow_rate_switches_from_pressure_control(self) -> None:
        well = Well(name="WELL-1", pressure=Quantity(1200, "psi"))
        well.set_flow_rate(Quantity(3500, "bbl/day"))
        assert well.is_flow_boundary
        assert not well.is_pressure_boundary
        assert well.pressure is None

    def test_set_pressure_switches_from_flow_control(self) -> None:
        well = Well(name="WELL-1", flow_rate=Quantity(3500, "bbl/day"))
        well.set_pressure(Quantity(1200, "psi"))
        assert well.is_pressure_boundary
        assert well.flow_rate is None

    def test_satisfies_node_protocol(self) -> None:
        assert isinstance(Well(name="WELL-1", pressure=Quantity(1200, "psi")), Node)


class TestTank:
    def test_construction_with_defaults(self) -> None:
        tank = Tank(name="TK-201", capacity=Quantity(500, "bbl"))
        assert tank.operating_pressure == Quantity(14.7, "psi")
        assert tank.tank_type == TankType.STORAGE

    def test_knockout_type(self) -> None:
        tank = Tank(name="KO-1", capacity=Quantity(50, "bbl"), tank_type=TankType.KNOCKOUT)
        assert tank.tank_type == TankType.KNOCKOUT

    def test_zero_capacity_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            Tank(name="TK-201", capacity=Quantity(0, "bbl"))

    def test_zero_operating_pressure_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            Tank(
                name="TK-201", capacity=Quantity(500, "bbl"), operating_pressure=Quantity(0, "psi")
            )

    def test_satisfies_node_protocol(self) -> None:
        assert isinstance(Tank(name="TK-201", capacity=Quantity(500, "bbl")), Node)


class TestCompressor:
    def test_construction_with_defaults(self) -> None:
        compressor = Compressor(name="COMP-1", rated_flow_rate=Quantity(5, "MMscf/day"))
        assert compressor.compression_ratio == 2.0
        assert compressor.polytropic_efficiency == 0.75

    def test_zero_rated_flow_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            Compressor(name="COMP-1", rated_flow_rate=Quantity(0, "MMscf/day"))

    def test_compression_ratio_of_one_raises(self) -> None:
        with pytest.raises(ValueError, match="greater than 1.0"):
            Compressor(
                name="COMP-1", rated_flow_rate=Quantity(5, "MMscf/day"), compression_ratio=1.0
            )

    def test_compression_ratio_below_one_raises(self) -> None:
        with pytest.raises(ValueError, match="greater than 1.0"):
            Compressor(
                name="COMP-1", rated_flow_rate=Quantity(5, "MMscf/day"), compression_ratio=0.5
            )

    def test_polytropic_efficiency_of_zero_raises(self) -> None:
        with pytest.raises(ValueError, match=r"\(0, 1\]"):
            Compressor(
                name="COMP-1",
                rated_flow_rate=Quantity(5, "MMscf/day"),
                polytropic_efficiency=0.0,
            )

    def test_satisfies_edge_protocol(self) -> None:
        compressor = Compressor(name="COMP-1", rated_flow_rate=Quantity(5, "MMscf/day"))
        assert isinstance(compressor, Edge)


class TestHeatExchanger:
    def test_outlet_temperature_only_construction(self) -> None:
        heater = HeatExchanger(name="E-101", outlet_temperature=Quantity(100, "degF"))
        assert heater.is_temperature_controlled
        assert not heater.is_duty_controlled
        assert heater.duty is None

    def test_duty_only_construction(self) -> None:
        cooler = HeatExchanger(name="E-102", duty=Quantity(-2, "MMBtu/hr"))
        assert cooler.is_duty_controlled
        assert not cooler.is_temperature_controlled
        assert cooler.outlet_temperature is None

    def test_both_specified_raises(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            HeatExchanger(
                name="E-101", outlet_temperature=Quantity(100, "degF"), duty=Quantity(2, "MMBtu/hr")
            )

    def test_neither_specified_raises(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            HeatExchanger(name="E-101")

    def test_wrong_dimensionality_for_outlet_temperature_raises(self) -> None:
        with pytest.raises(ValueError, match="dimensionality"):
            HeatExchanger(name="E-101", outlet_temperature=Quantity(100, "psi"))

    def test_wrong_dimensionality_for_duty_raises(self) -> None:
        with pytest.raises(ValueError, match="dimensionality"):
            HeatExchanger(name="E-101", duty=Quantity(100, "psi"))

    def test_set_duty_switches_from_temperature_controlled(self) -> None:
        heater = HeatExchanger(name="E-101", outlet_temperature=Quantity(100, "degF"))
        heater.set_duty(Quantity(2, "MMBtu/hr"))
        assert heater.is_duty_controlled
        assert heater.outlet_temperature is None

    def test_set_outlet_temperature_switches_from_duty_controlled(self) -> None:
        heater = HeatExchanger(name="E-101", duty=Quantity(2, "MMBtu/hr"))
        heater.set_outlet_temperature(Quantity(100, "degF"))
        assert heater.is_temperature_controlled
        assert heater.duty is None

    def test_satisfies_edge_protocol(self) -> None:
        assert isinstance(
            HeatExchanger(name="E-101", outlet_temperature=Quantity(100, "degF")), Edge
        )


class TestChoke:
    def test_construction_with_defaults(self) -> None:
        choke = Choke(name="CHK-1", bean_size=Quantity(0.5, "inch"))
        assert choke.choke_type == ChokeType.ADJUSTABLE

    def test_positive_choke_type(self) -> None:
        choke = Choke(name="CHK-1", bean_size=Quantity(0.25, "inch"), choke_type=ChokeType.POSITIVE)
        assert choke.choke_type == ChokeType.POSITIVE

    def test_zero_bean_size_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            Choke(name="CHK-1", bean_size=Quantity(0, "inch"))

    def test_satisfies_edge_protocol(self) -> None:
        assert isinstance(Choke(name="CHK-1", bean_size=Quantity(0.5, "inch")), Edge)


class TestInstrument:
    def test_construction(self) -> None:
        instrument = Instrument(name="PT-101", measured_variable=MeasuredVariable.PRESSURE)
        assert instrument.low_alarm is None
        assert instrument.high_alarm is None

    def test_is_in_alarm_below_low_alarm(self) -> None:
        instrument = Instrument(
            name="PT-101",
            measured_variable=MeasuredVariable.PRESSURE,
            low_alarm=Quantity(50, "psi"),
        )
        assert instrument.is_in_alarm(Quantity(40, "psi"))
        assert not instrument.is_in_alarm(Quantity(100, "psi"))

    def test_is_in_alarm_above_high_alarm(self) -> None:
        instrument = Instrument(
            name="PT-101",
            measured_variable=MeasuredVariable.PRESSURE,
            high_alarm=Quantity(1200, "psi"),
        )
        assert instrument.is_in_alarm(Quantity(1250, "psi"))
        assert not instrument.is_in_alarm(Quantity(800, "psi"))

    def test_is_in_alarm_within_bounds(self) -> None:
        instrument = Instrument(
            name="PT-101",
            measured_variable=MeasuredVariable.PRESSURE,
            low_alarm=Quantity(50, "psi"),
            high_alarm=Quantity(1200, "psi"),
        )
        assert not instrument.is_in_alarm(Quantity(800, "psi"))

    def test_no_alarms_configured_never_alarms(self) -> None:
        instrument = Instrument(name="PT-101", measured_variable=MeasuredVariable.PRESSURE)
        assert not instrument.is_in_alarm(Quantity(999999, "psi"))


class TestControlLoop:
    def test_construction(self) -> None:
        sensor = Instrument(name="PT-101", measured_variable=MeasuredVariable.PRESSURE)
        loop = ControlLoop(
            name="PIC-101",
            sensor=sensor,
            setpoint=Quantity(800, "psi"),
            final_control_element_name="PCV-101",
        )
        assert loop.sensor is sensor
        assert loop.setpoint == Quantity(800, "psi")
        assert loop.final_control_element_name == "PCV-101"
