"""
The building blocks you connect together into a
:class:`~flowline_scada.domain.network.PipelineNetwork`.

These are state only — a :class:`Valve`'s ``position`` or a :class:`Pipe`'s
``length``, not how much that valve position actually affects pressure
drop. The physics that turns this state into pressure/flow numbers is a
separate layer (arriving in a later phase) — that split is deliberate, so
these classes stay simple, easy to test on their own, and usable from
either a steady-state or a transient solver unchanged.

**Node types** (things you connect edges *between* — pass to
:meth:`~flowline_scada.domain.network.PipelineNetwork.add_node`):
:class:`Junction`, :class:`Boundary`, :class:`Well`, :class:`Manifold`,
:class:`Separator`, :class:`Tank`.

**Edge types** (things that connect two nodes — pass to
:meth:`~flowline_scada.domain.network.PipelineNetwork.add_edge`):
:class:`Pipe` (which can carry :class:`PipeLeak`\\ s), :class:`Valve`,
:class:`Pump`, :class:`Compressor`, :class:`Regulator`,
:class:`HeatExchanger`, :class:`Choke`.

**Instrumentation** (attached to the network for monitoring/control,
rather than being nodes or edges themselves): :class:`Instrument`,
:class:`ControlLoop`.

Example — see
:mod:`flowline_scada.domain.network` for a fuller worked example of
connecting several of these into an actual network.

```python
from flowline_scada.domain.components import Pipe
from flowline_scada.domain.units import Quantity

pipe = Pipe(
    name="FL-101",
    length=Quantity(2000, "ft"),
    internal_diameter=Quantity(6, "inch"),
    roughness=Quantity(0.0018, "inch"),  # typical commercial steel
)
```
"""

import enum
import typing

import attrs
import pint

from flowline_scada.domain.errors import DuplicateLeakError, UnknownLeakError
from flowline_scada.domain.units import Quantity
from flowline_scada.domain.validators import (
    non_negative_quantity,
    positive_quantity,
    quantity_with_dimensionality,
    unit_fraction,
)

# --------------------------------------------------------------------------
# Shared validation helpers for the mutually-exclusive-condition pattern
# used by Boundary, Well, and HeatExchanger.
# --------------------------------------------------------------------------


def _check_pressure_quantity(value: "pint.Quantity") -> None:
    if not value.check("[pressure]"):
        raise ValueError(f"pressure must have dimensionality '[pressure]', got {value!r}")


def _check_flow_rate_quantity(value: "pint.Quantity") -> None:
    if not value.check("[length] ** 3 / [time]"):
        raise ValueError(f"flow_rate must have dimensionality volume/time, got {value!r}")


def _check_temperature_quantity(value: "pint.Quantity") -> None:
    if not value.check("[temperature]"):
        raise ValueError(
            f"outlet_temperature must have dimensionality '[temperature]', got {value!r}"
        )


def _check_duty_quantity(value: "pint.Quantity") -> None:
    if not value.check("[mass] * [length] ** 2 / [time] ** 3"):
        raise ValueError(f"duty must have dimensionality of power (energy/time), got {value!r}")


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------


@attrs.define(frozen=True, slots=True)
class Junction:
    """A plain connection point with no behavior of its own — where two
    or more pipes meet without any special equipment (a manifold, a
    separator) at that point.

    :param name: a unique name for this junction within its network.

    Example:

    ```python
    network.add_node(Junction(name="J1"))
    ```
    """

    name: str


@attrs.define(slots=True)
class Boundary:
    """A node with an externally-imposed condition — a well feeding the
    network at a known pressure or rate, a delivery point taking product
    off at a fixed rate, and so on.

    Exactly one of ``pressure``/``flow_rate`` is set at a time — a
    hydraulic network solver needs precisely one boundary condition per
    boundary node (fixing the other lets the solver work it out), never
    both, never neither. Use :meth:`set_pressure`/:meth:`set_flow_rate`
    to switch which kind of boundary this is later, so the switch happens
    as one atomic step rather than leaving both (or neither) set in
    between two separate field writes.

    :param name: a unique name for this boundary within its network.
    :param pressure: the fixed pressure at this boundary, if it's a
        pressure boundary. Leave unset if using ``flow_rate`` instead.
    :param flow_rate: the fixed flow rate at this boundary, if it's a
        flow boundary. Leave unset if using ``pressure`` instead.
    :raises ValueError: if both or neither of ``pressure``/``flow_rate``
        are given, or if either has the wrong kind of unit.

    Example:

    ```python
    from flowline_scada.domain.components import Boundary
    from flowline_scada.domain.units import Quantity

    inlet = Boundary(name="well_1", pressure=Quantity(900, "psi"))
    outlet = Boundary(name="sales_point", flow_rate=Quantity(1000, "ft^3/s"))

    # Switch a boundary from pressure- to rate-controlled later:
    inlet.set_flow_rate(Quantity(500, "ft^3/s"))
    ```
    """

    name: str
    _pressure: "pint.Quantity | None" = attrs.field(default=None, alias="pressure")
    _flow_rate: "pint.Quantity | None" = attrs.field(default=None, alias="flow_rate")

    def __attrs_post_init__(self) -> None:
        self._validate_exactly_one_condition()
        if self._pressure is not None:
            _check_pressure_quantity(self._pressure)
        if self._flow_rate is not None:
            _check_flow_rate_quantity(self._flow_rate)

    def _validate_exactly_one_condition(self) -> None:
        specified = sum(x is not None for x in (self._pressure, self._flow_rate))
        if specified != 1:
            raise ValueError(
                f"Boundary {self.name!r} must have exactly one of pressure or "
                f"flow_rate specified at a time, got {specified}."
            )

    @property
    def pressure(self) -> "pint.Quantity | None":
        """The fixed pressure at this boundary, or ``None`` if it's a flow boundary."""
        return self._pressure

    @property
    def flow_rate(self) -> "pint.Quantity | None":
        """The fixed flow rate at this boundary, or ``None`` if it's a pressure boundary."""
        return self._flow_rate

    @property
    def is_pressure_boundary(self) -> bool:
        """``True`` if this boundary currently fixes pressure."""
        return self._pressure is not None

    @property
    def is_flow_boundary(self) -> bool:
        """``True`` if this boundary currently fixes flow rate."""
        return self._flow_rate is not None

    def set_pressure(self, pressure: "pint.Quantity") -> None:
        """Switch this boundary to fix pressure instead of flow rate.

        :param pressure: the pressure to hold this boundary at.
        :raises ValueError: if ``pressure`` isn't pressure-dimensioned.
        """
        _check_pressure_quantity(pressure)
        self._pressure = pressure
        self._flow_rate = None

    def set_flow_rate(self, flow_rate: "pint.Quantity") -> None:
        """Switch this boundary to fix flow rate instead of pressure.

        :param flow_rate: the flow rate to hold this boundary at.
        :raises ValueError: if ``flow_rate`` isn't volume/time-dimensioned.
        """
        _check_flow_rate_quantity(flow_rate)
        self._flow_rate = flow_rate
        self._pressure = None


class ArtificialLiftType(enum.StrEnum):
    """Which artificial lift method a :class:`Well` uses, if any — purely
    descriptive metadata (for reporting and P&ID symbol selection), not
    something that changes how the well's boundary condition is solved.

    :cvar NATURAL_FLOW: the well flows on reservoir energy alone.
    :cvar GAS_LIFT: gas is injected into the tubing to lighten the fluid column.
    :cvar ESP: electric submersible pump.
    :cvar ROD_PUMP: sucker-rod (beam) pump.
    :cvar PCP: progressive cavity pump.
    """

    NATURAL_FLOW = "natural_flow"
    GAS_LIFT = "gas_lift"
    ESP = "esp"
    ROD_PUMP = "rod_pump"
    PCP = "pcp"


@attrs.define(slots=True)
class Well:
    """A well feeding the network (or, for an injector, taking flow from
    it) at a known pressure or rate.

    This follows the same "exactly one boundary condition, switchable via
    explicit methods" pattern as :class:`Boundary` — see there for why —
    with well-specific identity and lift-method metadata added. Kept as
    its own class rather than a :class:`Boundary` subclass, to keep both
    simple and independent.

    :param name: a unique tag for this well, e.g. ``"WELL-014"``.
    :param pressure: the well's flowing pressure, if it's on pressure
        control. Leave unset if it's on rate control instead.
    :param flow_rate: the well's flow rate, if it's on rate control.
        Leave unset if it's on pressure control instead.
    :param api_number: the well's API number (US) or equivalent
        regulatory identifier — reference only, not used in any calculation.
    :param artificial_lift: which lift method the well uses. Defaults to
        :attr:`ArtificialLiftType.NATURAL_FLOW`.
    :raises ValueError: if both or neither of ``pressure``/``flow_rate``
        are given, or if either has the wrong kind of unit.

    Example:

    ```python
    from flowline_scada.domain.components import Well, ArtificialLiftType
    from flowline_scada.domain.units import Quantity

    well = Well(
        name="WELL-014",
        pressure=Quantity(1200, "psi"),
        api_number="42-123-45678",
        artificial_lift=ArtificialLiftType.GAS_LIFT,
    )

    well.set_flow_rate(Quantity(3500, "bbl/day"))  # switch onto rate control
    ```
    """

    name: str
    _pressure: "pint.Quantity | None" = attrs.field(default=None, alias="pressure")
    _flow_rate: "pint.Quantity | None" = attrs.field(default=None, alias="flow_rate")
    api_number: "str | None" = attrs.field(default=None)
    artificial_lift: ArtificialLiftType = attrs.field(default=ArtificialLiftType.NATURAL_FLOW)

    def __attrs_post_init__(self) -> None:
        self._validate_exactly_one_condition()
        if self._pressure is not None:
            _check_pressure_quantity(self._pressure)
        if self._flow_rate is not None:
            _check_flow_rate_quantity(self._flow_rate)

    def _validate_exactly_one_condition(self) -> None:
        specified = sum(x is not None for x in (self._pressure, self._flow_rate))
        if specified != 1:
            raise ValueError(
                f"Well {self.name!r} must have exactly one of pressure or "
                f"flow_rate specified at a time, got {specified}."
            )

    @property
    def pressure(self) -> "pint.Quantity | None":
        """The well's flowing pressure, or ``None`` if it's on rate control."""
        return self._pressure

    @property
    def flow_rate(self) -> "pint.Quantity | None":
        """The well's flow rate, or ``None`` if it's on pressure control."""
        return self._flow_rate

    @property
    def is_pressure_boundary(self) -> bool:
        """``True`` if this well is currently on pressure control."""
        return self._pressure is not None

    @property
    def is_flow_boundary(self) -> bool:
        """``True`` if this well is currently on rate control."""
        return self._flow_rate is not None

    def set_pressure(self, pressure: "pint.Quantity") -> None:
        """Switch this well onto pressure control.

        :param pressure: the flowing pressure to hold the well at.
        :raises ValueError: if ``pressure`` isn't pressure-dimensioned.
        """
        _check_pressure_quantity(pressure)
        self._pressure = pressure
        self._flow_rate = None

    def set_flow_rate(self, flow_rate: "pint.Quantity") -> None:
        """Switch this well onto rate control.

        :param flow_rate: the flow rate to hold the well at.
        :raises ValueError: if ``flow_rate`` isn't volume/time-dimensioned.
        """
        _check_flow_rate_quantity(flow_rate)
        self._flow_rate = flow_rate
        self._pressure = None


@attrs.define(frozen=True, slots=True)
class Manifold:
    """A multi-pipe gathering point.

    Physically the same kind of node as :class:`Junction` — the network's
    edges already capture "how many pipes meet here" — but kept as its
    own type so P&ID symbol selection and manifold-specific metadata (a
    design capacity, a tag number) have a real place to live rather than
    overloading what a plain :class:`Junction` means.

    :param name: a unique tag for this manifold, e.g. ``"MAN-1"``.
    :param design_capacity: the manifold's rated throughput, if you want
        to record one. Leave unset if not tracking this.
    :raises ValueError: if ``design_capacity`` is given but isn't
        positive or isn't volume/time-dimensioned.

    Example:

    ```python
    manifold = Manifold(name="MAN-1", design_capacity=Quantity(10000, "ft^3/s"))
    ```
    """

    name: str
    design_capacity: "pint.Quantity | None" = attrs.field(default=None)

    @design_capacity.validator
    def _check_design_capacity(
        self, attribute: "attrs.Attribute[pint.Quantity | None]", value: "pint.Quantity | None"
    ) -> None:
        if value is None:
            return
        if not value.check("[length] ** 3 / [time]"):
            raise ValueError(f"design_capacity must have dimensionality volume/time, got {value!r}")
        if value.magnitude <= 0:
            raise ValueError(f"design_capacity must be positive, got {value!r}")


class SeparatorType(enum.StrEnum):
    """What phases a :class:`Separator` splits its inlet stream into.

    :cvar TWO_PHASE: splits gas from total liquid (oil and water not separated).
    :cvar THREE_PHASE: splits gas, oil, and water into three distinct outlet streams.
    """

    TWO_PHASE = "two_phase"
    THREE_PHASE = "three_phase"


@attrs.define(slots=True)
class Separator:
    """A separator vessel splitting an inlet stream into outlet phases.

    This models the vessel's operating conditions only — the actual
    phase-split behavior (how much gas/oil/water leaves each outlet,
    which needs a real flash calculation against the inlet composition)
    needs the solver layer to exist to drive it, and isn't computed by
    this class itself.

    :param name: a unique tag for this separator, e.g. ``"SEP-1"``.
    :param operating_pressure: the pressure the vessel is held at.
    :param operating_temperature: the temperature the vessel is held at.
    :param separator_type: whether this splits two or three phases.
        Defaults to :attr:`SeparatorType.THREE_PHASE`.

    Example:

    ```python
    separator = Separator(
        name="SEP-1",
        operating_pressure=Quantity(300, "psi"),
        operating_temperature=Quantity(100, "degF"),
    )
    ```
    """

    name: str
    operating_pressure: "pint.Quantity" = attrs.field(validator=positive_quantity("[pressure]"))
    operating_temperature: "pint.Quantity" = attrs.field(
        validator=quantity_with_dimensionality("[temperature]")
    )
    separator_type: SeparatorType = attrs.field(default=SeparatorType.THREE_PHASE)


class TankType(enum.StrEnum):
    """What a :class:`Tank` is used for — purely descriptive, for P&ID
    symbol selection and reporting.

    :cvar STORAGE: general-purpose storage (crude, produced water, etc).
    :cvar SURGE: a surge/buffer tank smoothing out short-term flow variation.
    :cvar KNOCKOUT: a knockout drum/pot removing free liquid from a gas stream.
    """

    STORAGE = "storage"
    SURGE = "surge"
    KNOCKOUT = "knockout"


@attrs.define(slots=True)
class Tank:
    """A storage or surge vessel.

    :param name: a unique tag for this tank, e.g. ``"TK-201"``.
    :param capacity: the tank's total working volume.
    :param operating_pressure: the pressure the vessel is held at.
        Defaults to atmospheric (14.7 psi), the common case for an
        atmospheric stock tank.
    :param tank_type: what the tank is used for. Defaults to
        :attr:`TankType.STORAGE`.

    Example:

    ```python
    tank = Tank(name="TK-201", capacity=Quantity(500, "bbl"))
    ```
    """

    name: str
    capacity: "pint.Quantity" = attrs.field(validator=positive_quantity("[length] ** 3"))
    operating_pressure: "pint.Quantity" = attrs.field(
        factory=lambda: Quantity(14.7, "psi"), validator=positive_quantity("[pressure]")
    )
    tank_type: TankType = attrs.field(default=TankType.STORAGE)


# --------------------------------------------------------------------------
# Edges
# --------------------------------------------------------------------------


@attrs.define(slots=True)
class PipeLeak:
    """A leak at a fixed location along a :class:`Pipe`'s length.

    :param name: a unique name for this leak within its pipe.
    :param location: where along the pipe the leak is, as a fraction from
        0 (inlet) to 1 (outlet).
    :param diameter: the leak's effective orifice diameter.
    :param active: whether the leak is currently open. Defaults to ``True``
        — set ``False`` to model a leak that's been temporarily
        shut in without removing it from the pipe.
    :param discharge_coefficient: the orifice discharge coefficient.
        Defaults to 0.61, the standard value for a sharp-edged circular
        orifice at high Reynolds number — use a different value if you
        have a more specific figure for this leak's geometry.
    :raises ValueError: if ``location`` is outside ``[0, 1]``, ``diameter``
        isn't a positive length, or ``discharge_coefficient`` is outside
        ``(0, 1]``.

    Example:

    ```python
    leak = PipeLeak(name="L1", location=0.5, diameter=Quantity(0.5, "inch"))
    pipe.add_leak(leak)
    ```
    """

    name: str
    location: float = attrs.field(validator=unit_fraction)
    diameter: "pint.Quantity" = attrs.field(validator=positive_quantity("[length]"))
    active: bool = attrs.field(default=True)
    discharge_coefficient: float = attrs.field(default=0.61)

    @discharge_coefficient.validator
    def _check_discharge_coefficient(
        self, attribute: "attrs.Attribute[float]", value: float
    ) -> None:
        if not (0.0 < value <= 1.0):
            raise ValueError(
                f"discharge_coefficient must be in (0, 1], got {value!r}. Real "
                "orifice discharge coefficients for a leak are essentially "
                "always in this range; a value outside it is almost always a "
                "units or entry mistake rather than a real leak geometry."
            )


def _normalize_leaks(
    leaks: "dict[str, PipeLeak] | typing.Iterable[PipeLeak]",
) -> "dict[str, PipeLeak]":
    """Converter for `Pipe.leaks`: accepts either a ready-made dict or any
    iterable of `PipeLeak` (the convenient `leaks=[leak_1, leak_2]` form),
    always stores the name-keyed dict form."""
    if isinstance(leaks, dict):
        return dict(leaks)
    result: dict[str, PipeLeak] = {}
    for leak in leaks:
        if leak.name in result:
            raise DuplicateLeakError(f"Duplicate leak name {leak.name!r} in leaks list.")
        result[leak.name] = leak
    return result


@attrs.define(slots=True)
class Pipe:
    """A length of pipe between two network nodes — the primary edge type.

    :param name: a unique name for this pipe within its network.
    :param length: the pipe's length.
    :param internal_diameter: the pipe's internal diameter.
    :param roughness: the pipe wall's absolute roughness. Defaults to 0
        (a perfectly smooth pipe), which is a valid limiting case but not
        a realistic default for an actual steel pipe — set this
        explicitly for a real pipe (typical commercial steel is about
        0.045 mm / 0.0018 in) or friction-factor calculations that depend
        on it later will silently treat the pipe as smoother than it is.
    :param elevation_change: outlet elevation minus inlet elevation.
        Negative for a pipe running downhill — unlike ``length``/
        ``internal_diameter``/``roughness``, there's no sign constraint
        here, since downhill runs are completely normal.
    :param leaks: any :class:`PipeLeak`\\ s already on this pipe, as
        either a list or a dict keyed by leak name. You can also add them
        one at a time after construction with :meth:`add_leak`.
    :raises ValueError: if ``length``/``internal_diameter`` aren't
        positive lengths, or ``roughness`` is negative.
    :raises ~flowline_scada.domain.errors.DuplicateLeakError: if
        ``leaks`` contains two leaks with the same name.

    Example:

    ```python
    pipe = Pipe(
        name="FL-101",
        length=Quantity(2000, "ft"),
        internal_diameter=Quantity(6, "inch"),
        roughness=Quantity(0.0018, "inch"),
    )
    pipe.add_leak(PipeLeak(name="L1", location=0.5, diameter=Quantity(0.25, "inch")))
    ```
    """

    name: str
    length: "pint.Quantity" = attrs.field(validator=positive_quantity("[length]"))
    internal_diameter: "pint.Quantity" = attrs.field(validator=positive_quantity("[length]"))
    roughness: "pint.Quantity" = attrs.field(
        factory=lambda: Quantity(0.0, "m"), validator=non_negative_quantity("[length]")
    )
    elevation_change: "pint.Quantity" = attrs.field(
        factory=lambda: Quantity(0.0, "m"),
        validator=quantity_with_dimensionality("[length]"),
    )
    _leaks: "dict[str, PipeLeak]" = attrs.field(
        factory=dict, alias="leaks", repr=False, converter=_normalize_leaks
    )

    @property
    def leaks(self) -> "tuple[PipeLeak, ...]":
        """Every leak currently on this pipe."""
        return tuple(self._leaks.values())

    def add_leak(self, leak: PipeLeak) -> None:
        """Add a leak to this pipe.

        :param leak: the leak to add.
        :raises ~flowline_scada.domain.errors.DuplicateLeakError: if a
            leak with this name is already on the pipe.
        """
        if leak.name in self._leaks:
            raise DuplicateLeakError(f"Pipe {self.name!r} already has a leak named {leak.name!r}.")
        self._leaks[leak.name] = leak

    def remove_leak(self, name: str) -> None:
        """Remove a leak from this pipe.

        :param name: the name of the leak to remove.
        :raises ~flowline_scada.domain.errors.UnknownLeakError: if no
            leak with that name is on the pipe.
        """
        try:
            del self._leaks[name]
        except KeyError:
            raise UnknownLeakError(f"Pipe {self.name!r} has no leak named {name!r}.") from None

    def get_leak(self, name: str) -> PipeLeak:
        """Look up a leak on this pipe by name.

        :param name: the leak's name.
        :return: the leak.
        :raises ~flowline_scada.domain.errors.UnknownLeakError: if no
            leak with that name is on the pipe.
        """
        try:
            return self._leaks[name]
        except KeyError:
            raise UnknownLeakError(f"Pipe {self.name!r} has no leak named {name!r}.") from None


class ValveType(enum.StrEnum):
    """A valve's mechanical type — governs P&ID symbol selection, not
    solving behavior.

    :cvar GATE: a gate valve — on/off, not intended for throttling.
    :cvar GLOBE: a globe valve — can throttle, more resistance than a gate.
    :cvar BALL: a ball valve — on/off, quarter-turn operation.
    :cvar CHECK: a check valve — one-way flow only.
    :cvar CONTROL: a control valve — designed to modulate continuously.
    """

    GATE = "gate"
    GLOBE = "globe"
    BALL = "ball"
    CHECK = "check"
    CONTROL = "control"


@attrs.define(slots=True)
class Valve:
    """A valve along the network.

    Modeled as its own edge type rather than an attribute bolted onto
    :class:`Pipe`'s start/end, so a run of pipe-valve-pipe (or several
    valves in series) is just more edges and junction nodes — see the
    example below.

    :param name: a unique name for this valve within its network.
    :param valve_type: the valve's mechanical type. Defaults to
        :attr:`ValveType.GATE`.
    :param position: how open the valve is, from 0 (fully closed) to 1
        (fully open). Defaults to 1. A plain gate/ball/globe valve is
        only ever meaningfully at 0 or 1; a control valve can sit
        anywhere in between — both are the same one continuous field
        here, since every valve type is a special case of "some position
        in [0, 1]".
    :raises ValueError: if ``position`` is outside ``[0, 1]``.

    Example — a pipe-valve-pipe run through intermediate junctions:

    ```python
    network.add_node(Junction(name="upstream"))
    network.add_node(Junction(name="valve_inlet"))
    network.add_node(Junction(name="valve_outlet"))
    network.add_node(Junction(name="downstream"))

    network.add_edge(Pipe(name="P1", ...), from_node="upstream", to_node="valve_inlet")
    network.add_edge(Valve(name="V1"), from_node="valve_inlet", to_node="valve_outlet")
    network.add_edge(Pipe(name="P2", ...), from_node="valve_outlet", to_node="downstream")

    network.get_edge("V1").close()  # shut the valve
    ```
    """

    name: str
    valve_type: ValveType = attrs.field(default=ValveType.GATE)
    position: float = attrs.field(default=1.0, validator=unit_fraction)

    @property
    def is_open(self) -> bool:
        """``True`` if the valve is open at all (``position > 0``)."""
        return self.position > 0.0

    @property
    def is_closed(self) -> bool:
        """``True`` if the valve is fully closed (``position == 0``)."""
        return self.position == 0.0

    @property
    def is_fully_open(self) -> bool:
        """``True`` if the valve is fully open (``position == 1``)."""
        return self.position == 1.0

    def open(self) -> None:
        """Fully open the valve (sets ``position`` to 1.0)."""
        self.position = 1.0

    def close(self) -> None:
        """Fully close the valve (sets ``position`` to 0.0)."""
        self.position = 0.0


@attrs.define(slots=True)
class Pump:
    """A pump adding energy to the flow — its own edge type, same
    reasoning as :class:`Valve`.

    Modeled at its rated design point for now (a single flow rate /
    pressure boost / efficiency) rather than a full multi-point
    performance curve — how a real pump's boost varies away from its
    rated flow is solver-layer behavior for later, not state this class
    needs to carry yet.

    :param name: a unique name for this pump within its network.
    :param rated_flow_rate: the flow rate at the pump's best-efficiency
        design point.
    :param rated_pressure_boost: the pressure rise across the pump at its
        rated flow rate.
    :param efficiency: the fraction of shaft power converted to
        hydraulic work at the rated point. Defaults to 0.75, a reasonable
        mid-range value for a centrifugal pump absent a real datasheet
        figure — use the real number if you have it.
    :raises ValueError: if ``rated_flow_rate``/``rated_pressure_boost``
        aren't positive, or ``efficiency`` is outside ``(0, 1]``.

    Example:

    ```python
    pump = Pump(
        name="PUMP-1",
        rated_flow_rate=Quantity(500, "ft^3/s"),
        rated_pressure_boost=Quantity(200, "psi"),
    )
    ```
    """

    name: str
    rated_flow_rate: "pint.Quantity" = attrs.field(
        validator=positive_quantity("[length] ** 3 / [time]")
    )
    rated_pressure_boost: "pint.Quantity" = attrs.field(validator=positive_quantity("[pressure]"))
    efficiency: float = attrs.field(default=0.75)

    @efficiency.validator
    def _check_efficiency(self, attribute: "attrs.Attribute[float]", value: float) -> None:
        if not (0.0 < value <= 1.0):
            raise ValueError(f"efficiency must be in (0, 1], got {value!r}")


@attrs.define(slots=True)
class Compressor:
    """A gas compressor adding pressure to the flow via mechanical work —
    its own edge type, same reasoning as :class:`Pump`.

    Rated by compression ratio rather than a flat pressure boost (unlike
    :class:`Pump`), because that's how a real compressor is actually
    specified and how its performance scales: a centrifugal or
    reciprocating compressor holds roughly the discharge/suction
    pressure *ratio* close to constant across a range of suction
    pressures, not a fixed pressure difference the way a liquid pump does.

    :param name: a unique name for this compressor within its network.
    :param rated_flow_rate: the flow rate at the compressor's design point.
    :param compression_ratio: discharge pressure divided by suction
        pressure at the rated point. Must be greater than 1 (a
        compressor raises pressure — a ratio of 1 would do nothing).
        Defaults to 2.0.
    :param polytropic_efficiency: the fraction of ideal polytropic work
        actually delivered at the rated point. Defaults to 0.75, a
        reasonable mid-range value absent a real datasheet figure.
    :raises ValueError: if ``rated_flow_rate`` isn't positive,
        ``compression_ratio`` isn't greater than 1, or
        ``polytropic_efficiency`` is outside ``(0, 1]``.

    Example:

    ```python
    compressor = Compressor(
        name="COMP-1",
        rated_flow_rate=Quantity(5, "MMscf/day"),
        compression_ratio=2.5,
    )
    ```
    """

    name: str
    rated_flow_rate: "pint.Quantity" = attrs.field(
        validator=positive_quantity("[length] ** 3 / [time]")
    )
    compression_ratio: float = attrs.field(default=2.0)
    polytropic_efficiency: float = attrs.field(default=0.75)

    @compression_ratio.validator
    def _check_compression_ratio(self, attribute: "attrs.Attribute[float]", value: float) -> None:
        if value <= 1.0:
            raise ValueError(
                "compression_ratio must be greater than 1.0 (a compressor "
                f"increases pressure), got {value!r}"
            )

    @polytropic_efficiency.validator
    def _check_polytropic_efficiency(
        self, attribute: "attrs.Attribute[float]", value: float
    ) -> None:
        if not (0.0 < value <= 1.0):
            raise ValueError(f"polytropic_efficiency must be in (0, 1], got {value!r}")


class RegulatorType(enum.StrEnum):
    """Which side of itself a :class:`Regulator` holds at its setpoint.

    :cvar BACK_PRESSURE: maintains a fixed *upstream* pressure, relieving
        downstream as needed — throttles more as upstream pressure rises.
    :cvar PRESSURE_REDUCING: maintains a fixed *downstream* pressure
        regardless of upstream pressure — the common "PRV" case.
    """

    BACK_PRESSURE = "back_pressure"
    PRESSURE_REDUCING = "pressure_reducing"


@attrs.define(slots=True)
class Regulator:
    """A pressure regulator holding one side of itself at a setpoint —
    its own edge type, same reasoning as :class:`Valve` and :class:`Pump`.

    :param name: a unique name for this regulator within its network.
    :param setpoint_pressure: the pressure this regulator tries to hold.
    :param regulator_type: which side of the regulator the setpoint
        applies to. Defaults to :attr:`RegulatorType.PRESSURE_REDUCING`.
    :raises ValueError: if ``setpoint_pressure`` isn't positive.

    Example:

    ```python
    prv = Regulator(name="PRV-1", setpoint_pressure=Quantity(500, "psi"))
    ```
    """

    name: str
    setpoint_pressure: "pint.Quantity" = attrs.field(validator=positive_quantity("[pressure]"))
    regulator_type: RegulatorType = attrs.field(default=RegulatorType.PRESSURE_REDUCING)


@attrs.define(slots=True)
class HeatExchanger:
    """A heater or cooler in the flow path — a fired heater preventing
    hydrate formation, a cooler ahead of compression, and so on.

    Exactly one of ``outlet_temperature``/``duty`` is set at a time, same
    reasoning as :class:`Boundary`'s pressure/flow_rate: fixing the
    outlet temperature and fixing the heat duty are two different, and
    incompatible, ways to specify the same piece of equipment.

    :param name: a unique name for this exchanger within its network.
    :param outlet_temperature: hold the outlet at this fixed temperature.
        Leave unset if using ``duty`` instead.
    :param duty: apply this fixed heat duty (positive = heating, negative
        = cooling). Leave unset if using ``outlet_temperature`` instead.
    :raises ValueError: if both or neither of
        ``outlet_temperature``/``duty`` are given, or if either has the
        wrong kind of unit.

    Example:

    ```python
    heater = HeatExchanger(name="E-101", outlet_temperature=Quantity(100, "degF"))
    heater.set_duty(Quantity(2, "MMBtu/hr"))  # switch to duty-controlled later
    ```
    """

    name: str
    _outlet_temperature: "pint.Quantity | None" = attrs.field(
        default=None, alias="outlet_temperature"
    )
    _duty: "pint.Quantity | None" = attrs.field(default=None, alias="duty")

    def __attrs_post_init__(self) -> None:
        self._validate_exactly_one_condition()
        if self._outlet_temperature is not None:
            _check_temperature_quantity(self._outlet_temperature)
        if self._duty is not None:
            _check_duty_quantity(self._duty)

    def _validate_exactly_one_condition(self) -> None:
        specified = sum(x is not None for x in (self._outlet_temperature, self._duty))
        if specified != 1:
            raise ValueError(
                f"HeatExchanger {self.name!r} must have exactly one of "
                f"outlet_temperature or duty specified at a time, got {specified}."
            )

    @property
    def outlet_temperature(self) -> "pint.Quantity | None":
        """The fixed outlet temperature, or ``None`` if this is duty-controlled."""
        return self._outlet_temperature

    @property
    def duty(self) -> "pint.Quantity | None":
        """The fixed heat duty, or ``None`` if this is temperature-controlled."""
        return self._duty

    @property
    def is_temperature_controlled(self) -> bool:
        """``True`` if this exchanger holds a fixed outlet temperature."""
        return self._outlet_temperature is not None

    @property
    def is_duty_controlled(self) -> bool:
        """``True`` if this exchanger applies a fixed heat duty."""
        return self._duty is not None

    def set_outlet_temperature(self, outlet_temperature: "pint.Quantity") -> None:
        """Switch to holding a fixed outlet temperature.

        :param outlet_temperature: the temperature to hold the outlet at.
        :raises ValueError: if ``outlet_temperature`` isn't
            temperature-dimensioned.
        """
        _check_temperature_quantity(outlet_temperature)
        self._outlet_temperature = outlet_temperature
        self._duty = None

    def set_duty(self, duty: "pint.Quantity") -> None:
        """Switch to applying a fixed heat duty.

        :param duty: the heat duty to apply (positive = heating, negative = cooling).
        :raises ValueError: if ``duty`` isn't power-dimensioned.
        """
        _check_duty_quantity(duty)
        self._duty = duty
        self._outlet_temperature = None


class ChokeType(enum.StrEnum):
    """Whether a :class:`Choke`'s restriction is fixed or field-adjustable.

    :cvar POSITIVE: a fixed-size bean, physically replaced (not adjusted) to change flow.
    :cvar ADJUSTABLE: a variable-orifice choke, adjustable without replacement.
    """

    POSITIVE = "positive"
    ADJUSTABLE = "adjustable"


@attrs.define(slots=True)
class Choke:
    """A wellhead or surface choke restricting flow through a fixed or
    adjustable orifice (a "bean", in oilfield terms).

    Modeled as its own edge type rather than a :class:`Valve`, even
    though both restrict flow: chokes are characterized and reported
    differently in production engineering (bean size, often in 64ths of
    an inch, is the standard way to describe one) and are usually solved
    with critical/subcritical-flow correlations distinct from a generic
    valve's — keeping the two as separate types from the start avoids
    overloading what :class:`Valve` means later.

    :param name: a unique name for this choke within its network.
    :param bean_size: the orifice diameter.
    :param choke_type: whether this is a fixed or adjustable choke.
        Defaults to :attr:`ChokeType.ADJUSTABLE`.
    :raises ValueError: if ``bean_size`` isn't a positive length.

    Example:

    ```python
    # a 32/64" (0.5 in) adjustable choke
    choke = Choke(name="CHK-1", bean_size=Quantity(0.5, "inch"))
    ```
    """

    name: str
    bean_size: "pint.Quantity" = attrs.field(validator=positive_quantity("[length]"))
    choke_type: ChokeType = attrs.field(default=ChokeType.ADJUSTABLE)


# --------------------------------------------------------------------------
# Instrumentation
# --------------------------------------------------------------------------


class MeasuredVariable(enum.StrEnum):
    """What physical quantity an :class:`Instrument` measures — the first
    letter of an ISA-5.1 instrument tag (the ``P`` in ``PT-101``).

    :cvar PRESSURE: ISA-5.1 letter ``P``.
    :cvar TEMPERATURE: ISA-5.1 letter ``T``.
    :cvar FLOW_RATE: ISA-5.1 letter ``F``.
    :cvar LEVEL: ISA-5.1 letter ``L``.
    """

    PRESSURE = "pressure"
    TEMPERATURE = "temperature"
    FLOW_RATE = "flow_rate"
    LEVEL = "level"


@attrs.define(slots=True)
class Instrument:
    """A measurement point — a pressure transmitter on a pipe, a level
    indicator on a separator, and so on.

    This models the instrument itself: its tag, what it measures, and its
    alarm limits. It doesn't reach into a network to find its own live
    reading — see :class:`ControlLoop` for tying an instrument to the
    piece of equipment it monitors or controls.

    :param name: the instrument's ISA-5.1-style tag, e.g. ``"PT-101"``
        (pressure transmitter, loop 101).
    :param measured_variable: which physical quantity this instrument reads.
    :param low_alarm: the threshold below which the reading is flagged.
        Leave unset if there's no low alarm.
    :param high_alarm: the threshold above which the reading is flagged.
        Leave unset if there's no high alarm.

    Example:

    ```python
    from flowline_scada.domain.components import Instrument, MeasuredVariable
    from flowline_scada.domain.units import Quantity

    pt_101 = Instrument(
        name="PT-101",
        measured_variable=MeasuredVariable.PRESSURE,
        low_alarm=Quantity(50, "psi"),
        high_alarm=Quantity(1200, "psi"),
    )
    pt_101.is_in_alarm(Quantity(1250, "psi"))  # True
    ```
    """

    name: str
    measured_variable: MeasuredVariable
    low_alarm: "pint.Quantity | None" = attrs.field(default=None)
    high_alarm: "pint.Quantity | None" = attrs.field(default=None)

    def is_in_alarm(self, value: "pint.Quantity") -> bool:
        """Check whether a reading would trip this instrument's alarm.

        :param value: the reading to check against the configured limits.
        :return: ``True`` if ``value`` is at or beyond either configured
            limit, ``False`` otherwise (including when no limits are set at all).
        """
        if self.low_alarm is not None and value <= self.low_alarm:
            return True
        if self.high_alarm is not None and value >= self.high_alarm:
            return True
        return False


@attrs.define(slots=True)
class ControlLoop:
    """A control loop: a sensor feeding a controller that drives a final
    control element toward a setpoint — a ``PIC`` (pressure indicating
    controller) modulating a control :class:`Valve` to hold a setpoint
    pressure, for instance.

    This is what makes an :class:`Instrument` more than decoration on a
    diagram: a loop with a setpoint is something a solver can actually
    act on.

    :param name: the loop's tag, e.g. ``"PIC-101"``.
    :param sensor: the :class:`Instrument` providing the process value.
    :param setpoint: the value this loop tries to hold the process at.
    :param final_control_element_name: the name of the :class:`Valve`,
        :class:`Pump`, :class:`Compressor`, or :class:`Regulator` this
        loop drives — stored as a plain name (rather than a direct
        reference) so a ``ControlLoop`` doesn't need to know about the
        network it will eventually be used within.

    Example:

    ```python
    loop = ControlLoop(
        name="PIC-101",
        sensor=pt_101,
        setpoint=Quantity(800, "psi"),
        final_control_element_name="PCV-101",
    )
    ```
    """

    name: str
    sensor: Instrument
    setpoint: "pint.Quantity"
    final_control_element_name: str
