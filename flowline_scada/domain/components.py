"""
Concrete node and edge types that plug into `domain.network.PipelineNetwork`.

State only — no correlation logic (how much a valve's position affects
pressure drop, how a pipe's roughness feeds into a friction factor) lives
here. That's Phase 2's `correlations`/`solver` layers, deliberately kept
separate so this module stays pure data plus the invariants that make it
physically sane, testable without a solver, and usable from either the
steady-state or transient engine unchanged.

Node types: `Junction`, `Boundary`.
Edge types: `Pipe` (with `PipeLeak`s), `Valve`.

Pump, Regulator, Manifold, and Separator are the next slice — not built
in this pass.
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


@attrs.define(frozen=True, slots=True)
class Junction:
    """A plain connection point with no behavior of its own — where two
    or more pipes meet without any special equipment (a manifold, a
    separator) at that point."""

    name: str


@attrs.define(slots=True)
class Boundary:
    """A node with an externally-imposed condition: a well feeding the
    network at a known flowing pressure or a known rate, a delivery point
    taking product off at a fixed rate, and so on.

    Exactly one of pressure or flow rate is ever set at a time — that's
    not a validation nicety, it's the actual physical/numerical
    requirement: a hydraulic network solver needs precisely one boundary
    condition per boundary node (fix the other and the solver determines
    it), never both and never neither. `set_pressure`/`set_flow_rate` are
    the way to change which kind of boundary this is, specifically so
    switching from one to the other is a single atomic action rather than
    two independent field writes that could leave both (or neither) set
    in between.
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
        return self._pressure

    @property
    def flow_rate(self) -> "pint.Quantity | None":
        return self._flow_rate

    @property
    def is_pressure_boundary(self) -> bool:
        return self._pressure is not None

    @property
    def is_flow_boundary(self) -> bool:
        return self._flow_rate is not None

    def set_pressure(self, pressure: "pint.Quantity") -> None:
        """Make this a fixed-pressure boundary — a well with a known
        flowing tubing pressure, or a fixed-pressure delivery point."""
        _check_pressure_quantity(pressure)
        self._pressure = pressure
        self._flow_rate = None

    def set_flow_rate(self, flow_rate: "pint.Quantity") -> None:
        """Make this a fixed-flow-rate boundary — a well on rate control,
        or a contracted delivery volume."""
        _check_flow_rate_quantity(flow_rate)
        self._flow_rate = flow_rate
        self._pressure = None


def _check_pressure_quantity(value: "pint.Quantity") -> None:
    if not value.check("[pressure]"):
        raise ValueError(f"pressure must have dimensionality '[pressure]', got {value!r}")


def _check_flow_rate_quantity(value: "pint.Quantity") -> None:
    if not value.check("[length] ** 3 / [time]"):
        raise ValueError(f"flow_rate must have dimensionality volume/time, got {value!r}")


@attrs.define(slots=True)
class PipeLeak:
    """A leak at a fixed location along a pipe's length."""

    name: str
    location: float = attrs.field(validator=unit_fraction)
    """Fractional position along the pipe, 0 = inlet, 1 = outlet."""

    diameter: "pint.Quantity" = attrs.field(validator=positive_quantity("[length]"))
    """Effective leak orifice diameter."""

    active: bool = attrs.field(default=True)

    discharge_coefficient: float = attrs.field(default=0.61)
    """Orifice discharge coefficient. 0.61 is the standard value for a
    sharp-edged circular orifice at high Reynolds number — the common
    default absent a reason to use something more specific."""

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
    always stores the name-keyed dict form. Using an attrs converter for
    this rather than post-init normalization means the field's declared
    type can just be the stored form (`dict[str, PipeLeak]`) while
    `__init__` still accepts the broader input — that's what a converter
    is for, and mypy's attrs plugin understands the distinction natively."""
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
    """A length of pipe between two network nodes — the primary edge type."""

    name: str
    length: "pint.Quantity" = attrs.field(validator=positive_quantity("[length]"))
    internal_diameter: "pint.Quantity" = attrs.field(validator=positive_quantity("[length]"))

    roughness: "pint.Quantity" = attrs.field(
        factory=lambda: Quantity(0.0, "m"), validator=non_negative_quantity("[length]")
    )
    """Absolute pipe-wall roughness. Defaults to 0 (a perfectly smooth
    pipe) only because that's a valid degenerate case, not because it's a
    realistic default for an actual steel pipe — see the v1 review's
    finding on how an unset roughness silently zeroes out the friction
    factor's roughness term. Callers modeling a real pipe should set this
    explicitly (typical commercial steel: ~0.045 mm / 0.0018 in)."""

    elevation_change: "pint.Quantity" = attrs.field(
        factory=lambda: Quantity(0.0, "m"),
        validator=quantity_with_dimensionality("[length]"),
    )
    """Outlet elevation minus inlet elevation — negative for a pipe
    running downhill. No sign constraint, unlike length/diameter."""

    _leaks: "dict[str, PipeLeak]" = attrs.field(
        factory=dict, alias="leaks", repr=False, converter=_normalize_leaks
    )

    @property
    def leaks(self) -> "tuple[PipeLeak, ...]":
        return tuple(self._leaks.values())

    def add_leak(self, leak: PipeLeak) -> None:
        if leak.name in self._leaks:
            raise DuplicateLeakError(f"Pipe {self.name!r} already has a leak named {leak.name!r}.")
        self._leaks[leak.name] = leak

    def remove_leak(self, name: str) -> None:
        try:
            del self._leaks[name]
        except KeyError:
            raise UnknownLeakError(f"Pipe {self.name!r} has no leak named {name!r}.") from None

    def get_leak(self, name: str) -> PipeLeak:
        try:
            return self._leaks[name]
        except KeyError:
            raise UnknownLeakError(f"Pipe {self.name!r} has no leak named {name!r}.") from None


class ValveType(enum.StrEnum):
    """Governs P&ID symbol selection (Phase 3) — not solving behavior."""

    GATE = "gate"
    GLOBE = "globe"
    BALL = "ball"
    CHECK = "check"
    CONTROL = "control"


@attrs.define(slots=True)
class Valve:
    """A valve along the network — its own edge type rather than an
    attribute bolted onto `Pipe`'s start/end, so a run of pipe-valve-pipe
    (or several valves in series) is just more edges and junction nodes,
    not a shape `Pipe` has to specially accommodate."""

    name: str
    valve_type: ValveType = attrs.field(default=ValveType.GATE)

    position: float = attrs.field(default=1.0, validator=unit_fraction)
    """0 = fully closed, 1 = fully open. A plain gate/ball/globe valve is
    only ever meaningfully at 0 or 1; a control valve can sit anywhere in
    between — modeled as one continuous field rather than a discrete open/
    closed enum plus a separate "how far open" field for control valves,
    since every valve type is a special case of "some position in [0, 1]\"."""

    @property
    def is_open(self) -> bool:
        return self.position > 0.0

    @property
    def is_closed(self) -> bool:
        return self.position == 0.0

    @property
    def is_fully_open(self) -> bool:
        return self.position == 1.0

    def open(self) -> None:
        self.position = 1.0

    def close(self) -> None:
        self.position = 0.0
