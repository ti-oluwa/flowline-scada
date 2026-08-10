"""
Physical units, built on `pint <https://pint.readthedocs.io>`_.

Every quantity in this package (a pipe's length, a fluid's pressure, a
flow rate) is a :class:`pint.Quantity` built through :data:`Quantity`
below — not a plain float — so unit mistakes (mixing psi and Pa, feet and
meters) are caught immediately rather than silently producing a wrong
answer.

Example:

```python
from flowline_scada.domain.units import Quantity

length = Quantity(1000, "ft")
length_in_meters = length.to("m")
print(length_in_meters)  # 304.8 meter
```

This module also registers a handful of oilfield-standard units pint
doesn't define natively — gas volumes (``scf``, ``Mscf``, ``MMscf``,
``MMMscf``) and heat duty (``MMBtu``) — usable anywhere any other pint
unit is, once this module has been imported.

:class:`UnitSystem` is a separate, optional convenience on top of this:
a named collection of "preferred unit for each kind of quantity",
for a UI that wants to show pressures in psi vs. Pa depending on which
system the user picked. Three are built in — :data:`IMPERIAL`,
:data:`SI`, :data:`OIL_FIELD` — covering the common quantity names used
throughout this package (``"pressure"``, ``"temperature"``,
``"flow_rate"``, etc).
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

# pint's UnitRegistry doesn't expose a statically-inferable type for its
# own constructor, so mypy can't infer one here without help.
ureg = UnitRegistry()  # type: ignore[var-annotated]
"""The single :class:`pint.UnitRegistry` this whole package builds
quantities through. You generally don't need to touch this directly —
use :data:`Quantity` to build values and :data:`Unit` to build bare
units instead."""

ureg.define("scf = 0.0283168 * meter**3 = SCF")  # 1 scf ~= 0.0283168 m^3
ureg.define("Mscf = 1000 * scf = MSCf")  # 1 Mscf = 1000 scf
ureg.define("MMscf = 1000 * Mscf = MMSCF")  # 1 MMscf = 1,000,000 scf
ureg.define("MMMscf = 1000 * MMscf = MMMSCF")  # 1 MMMscf = 1,000,000,000 scf
ureg.define("MMBtu = 1e6 * Btu = MMBTU")  # 1 MMBtu = 1,000,000 Btu — standard US heat-duty unit

Quantity = ureg.Quantity
"""Build a physical quantity: ``Quantity(value, unit_string)``. Also
recognizes the oilfield gas-volume units this module adds on top of
pint's own (``scf``, ``Mscf``, ``MMscf``, ``MMMscf``), in addition to
everything pint supports natively (``psi``, ``degF``, ``ft^3/s``, ...).

Example:

```python
pressure = Quantity(800, "psi")
gas_volume = Quantity(5, "MMscf")
```
"""

Unit = ureg.Unit
"""Build a bare unit (no value attached) — mostly useful for comparisons
and conversions, e.g. ``some_quantity.to(Unit("Pa"))``."""


@attrs.define(frozen=True, slots=True)
class QuantityUnit:
    """A single "preferred unit" entry within a :class:`UnitSystem` — the
    unit itself, how to display it, and an optional default value.

    :param unit: the unit, as anything :data:`Unit` accepts — e.g.
        ``"psi"``, ``"degF"``, ``"m^3/s"``.
    :param display: how to show this unit in a UI, if different from its
        plain string form — e.g. ``"°F"`` instead of ``"degF"``. Falls
        back to ``str(unit)`` if not given.
    :param default: a default value for this quantity, in this unit, if
        one makes sense (e.g. 60.0 for a default ambient temperature in
        °F). Leave unset if there's no sensible default.

    Example:

    ```python
    pressure_unit = QuantityUnit(unit="psi", display="psi", default=14.7)
    print(str(pressure_unit))  # "psi"
    ```
    """

    unit: pint.Unit = attrs.field(converter=Unit)  # type: ignore[misc]

    display: str | None = attrs.field(default=None)

    default: float | None = attrs.field(default=None)

    def __str__(self) -> str:
        return self.display or str(self.unit)


QuantityUnitT = typing.TypeVar("QuantityUnitT", bound=QuantityUnit)


class UnitSystem(defaultdict[str, QuantityUnitT]):
    """
    A named set of preferred units — one :class:`QuantityUnit` per kind
    of physical quantity (``"pressure"``, ``"temperature"``, and so on).

    Looking up a quantity name this system hasn't defined doesn't raise
    :class:`KeyError` — it returns a dimensionless default instead, so UI
    code that looks up units by name doesn't need to special-case
    quantities a particular system left undefined.

    :param name: a label for this unit system, e.g. ``"imperial"``.
    :param __map: an optional starting mapping of quantity name to
        :class:`QuantityUnit` (positional-only — pass it as the second
        positional argument, or just use keyword arguments instead, as
        in the example below).
    :param default_factory: what to return for a quantity name this
        system doesn't define. Defaults to a dimensionless
        :class:`QuantityUnit` with no default value.
    :param kwargs: additional ``quantity_name=QuantityUnit(...)`` entries,
        merged with ``__map``.

    Example:

    ```python
    imperial: UnitSystem[QuantityUnit] = UnitSystem(
        "imperial", pressure=QuantityUnit(unit="psi", default=14.7)
    )

    pressure_unit = imperial["pressure"].unit       # psi
    default_pressure = imperial["pressure"].default  # 14.7
    imperial["nonexistent_quantity"]                 # dimensionless default, not KeyError
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
        self.name = name
        if default_factory is None:

            def _default_factory() -> QuantityUnitT:
                return typing.cast(QuantityUnitT, QuantityUnit(unit="dimensionless", default=None))

            default_factory = _default_factory

        merged: dict[str, QuantityUnitT] = dict(__map or {}, **kwargs)
        super().__init__(default_factory, merged)

    def __missing__(self, key: str) -> QuantityUnitT:
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
