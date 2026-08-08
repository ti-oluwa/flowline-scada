"""
Units and unit-system definitions.

Built on `pint` for dimensional quantities. `UnitSystem` is a small,
generic mapping from a physical-quantity name (e.g. "pressure") to its
preferred unit for a given display context (Imperial, SI, oil-field), with
a display string and an optional default value. Carried over from the v1
NiceGUI app's src/units.py, cleaned up and fully typed.
"""

import typing
from collections import defaultdict

import attrs
import pint
from pint import UnitRegistry

__all__ = [
    "IMPERIAL",
    "OIL_FIELD",
    "SI",
    "Quantity",
    "QuantityUnit",
    "Unit",
    "UnitSystem",
    "ureg",
]

ureg: UnitRegistry[float] = UnitRegistry()
ureg.define("scf = 0.0283168 * meter**3 = SCF")  # 1 scf ~= 0.0283168 m^3
ureg.define("Mscf = 1000 * scf = MSCf")  # 1 Mscf = 1000 scf
ureg.define("MMscf = 1000 * Mscf = MMSCF")  # 1 MMscf = 1,000,000 scf
ureg.define("MMMscf = 1000 * MMscf = MMMSCF")  # 1 MMMscf = 1,000,000,000 scf

# `ureg.Quantity`/`ureg.Unit` are registry-bound constructors — the ones
# actually used everywhere at runtime, since only quantities built through
# *this* registry know about scf/Mscf/MMscf/MMMscf. They're dynamically
# generated per-registry, though, so mypy can't resolve them as static
# types. `pint.Quantity`/`pint.Unit` (imported as `pint` above) are the
# statically-typeable base classes pint ships specifically for annotation
# purposes — registry-bound instances are real subclasses of these at
# runtime, so annotating with `pint.Unit`/`pint.Quantity` while
# constructing with `Unit(...)`/`Quantity(...)` is correct both ways.
Quantity = ureg.Quantity
Unit = ureg.Unit


def _to_unit(value: "str | pint.Unit") -> pint.Unit:
    """Named wrapper around the registry-bound `Unit` constructor.

    attrs' mypy plugin needs a converter it can statically resolve as a
    named function, type, or lambda — `attrs.field(converter=Unit)` alone
    doesn't qualify, since `Unit` is a dynamically-generated per-registry
    class reached through an attribute access (`ureg.Unit`), not something
    mypy can pin down as a class reference at that point. This wrapper is
    just a plain function around the same constructor.
    """
    return Unit(value)


@attrs.define(frozen=True, slots=True)
class QuantityUnit:
    """Unit for a specific physical quantity."""

    unit: pint.Unit = attrs.field(converter=_to_unit)
    """Pint-supported unit, e.g. 'psi', 'degF', 'm^3/s'."""

    display: str | None = attrs.field(default=None)
    """Optional display string for UI, e.g. '°F'."""

    default: float | None = attrs.field(default=None)
    """Default value for the quantity in the specified unit, if applicable."""

    def __str__(self) -> str:
        return self.display or str(self.unit)


QuantityUnitT = typing.TypeVar("QuantityUnitT", bound=QuantityUnit)


class UnitSystem(defaultdict[str, QuantityUnitT]):
    """
    A unit system mapping quantity names to their `QuantityUnit` definitions.

    Subclasses `defaultdict` so unrecognized quantity names fall back to a
    dimensionless default instead of raising `KeyError`, which keeps UI code
    that looks up units by name simple even for quantities a given system
    hasn't defined.

    Example:

    ```python
    imperial: UnitSystem[QuantityUnit] = UnitSystem("imperial")
    imperial["pressure"] = QuantityUnit(unit="psi", default=14.7)

    pressure_unit = imperial["pressure"].unit  # psi
    default_pressure = imperial["pressure"].default  # 14.7
    ```
    """

    def __init__(
        self,
        name: str,
        __map: typing.Mapping[str, QuantityUnitT] | None = None,
        /,
        *,
        default_factory: typing.Callable[[], QuantityUnitT] | None = None,
        **kwargs: QuantityUnitT,
    ) -> None:
        """Initialize a named `UnitSystem` with an optional starting mapping."""
        self.name = name
        if default_factory is None:

            def _default_factory() -> QuantityUnitT:
                return typing.cast(QuantityUnitT, QuantityUnit(unit="dimensionless", default=None))

            default_factory = _default_factory

        merged: dict[str, QuantityUnitT] = dict(__map or {}, **kwargs)
        super().__init__(default_factory, merged)

    def __missing__(self, key: str) -> QuantityUnitT:
        """Return the default `QuantityUnit` for a name this system hasn't defined."""
        assert self.default_factory is not None
        return self.default_factory()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.name})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, units={dict(self)!r})"


IMPERIAL: UnitSystem[QuantityUnit] = UnitSystem(
    "imperial",
    {
        "length": QuantityUnit(unit="ft", display="ft"),
        "diameter": QuantityUnit(unit="inch", display="in"),
        "pressure": QuantityUnit(unit="psi", display="psi"),
        "temperature": QuantityUnit(unit="degF", display="°F", default=60.0),
        "flow_rate": QuantityUnit(unit="ft^3/s", display="ft³/s"),
        "mass_flow_rate": QuantityUnit(unit="lb/s", display="lb/s"),
        "flow_volume": QuantityUnit(unit="scf", display="scf"),
        "molecular_weight": QuantityUnit(unit="g/mol", display="g/mol", default=16.04),
        "roughness": QuantityUnit(unit="meter", display="m"),
        "elevation": QuantityUnit(unit="ft", display="ft", default=0.0),
        "area": QuantityUnit(unit="inch^2", display="in²"),
        "velocity": QuantityUnit(unit="ft/s", display="ft/s"),
        "density": QuantityUnit(unit="lb/ft^3", display="lb/ft³"),
        "viscosity": QuantityUnit(unit="cP", display="cP"),
    },
)

SI: UnitSystem[QuantityUnit] = UnitSystem(
    "si",
    {
        "length": QuantityUnit(unit="m", display="m"),
        "diameter": QuantityUnit(unit="mm", display="mm"),
        "pressure": QuantityUnit(unit="Pa", display="Pa"),
        "temperature": QuantityUnit(unit="degC", display="°C", default=15.6),
        "flow_rate": QuantityUnit(unit="m^3/s", display="m³/s"),
        "mass_flow_rate": QuantityUnit(unit="kg/s", display="kg/s"),
        "flow_volume": QuantityUnit(unit="m^3", display="m³"),
        "molecular_weight": QuantityUnit(unit="g/mol", display="g/mol", default=16.04),
        "roughness": QuantityUnit(unit="mm", display="mm"),
        "elevation": QuantityUnit(unit="m", display="m", default=0.0),
        "area": QuantityUnit(unit="mm^2", display="mm²"),
        "velocity": QuantityUnit(unit="m/s", display="m/s"),
        "density": QuantityUnit(unit="kg/m^3", display="kg/m³"),
        "viscosity": QuantityUnit(unit="Pa*s", display="Pa⋅s"),
    },
)

OIL_FIELD: UnitSystem[QuantityUnit] = UnitSystem(
    "oil_field",
    {
        "length": QuantityUnit(unit="ft", display="ft"),
        "diameter": QuantityUnit(unit="inch", display="in"),
        "pressure": QuantityUnit(unit="psi", display="psi"),
        "temperature": QuantityUnit(unit="degR", display="°R", default=520.0),
        "flow_rate": QuantityUnit(unit="MMscf/day", display="MMscf/day"),
        "mass_flow_rate": QuantityUnit(unit="kg/s", display="kg/s"),
        "flow_volume": QuantityUnit(unit="scf", display="scf"),
        "molecular_weight": QuantityUnit(unit="g/mol", display="g/mol", default=16.04),
        "roughness": QuantityUnit(unit="meter", display="m"),
        "elevation": QuantityUnit(unit="ft", display="ft", default=0.0),
        "area": QuantityUnit(unit="inch^2", display="in²"),
        "velocity": QuantityUnit(unit="ft/s", display="ft/s"),
        "density": QuantityUnit(unit="lb/ft^3", display="lb/ft³"),
        "viscosity": QuantityUnit(unit="cP", display="cP"),
    },
)
