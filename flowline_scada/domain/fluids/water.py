"""
Brine/produced-water properties.

Oilfield produced water is a saline aqueous solution — its density and
viscosity depend on salinity in a way a plain freshwater lookup
(``PureFluid(name="Water")``) doesn't capture. Rather than hand-deriving
empirical brine correlations here, :class:`Brine` wraps CoolProp's own
``INCOMP::MITSW`` backend — the MIT seawater property library (Sharqawy,
Lienhard & Zubair, 2010), a real published, peer-reviewed correlation
CoolProp already ships and validates.

Valid for roughly 0-12% salinity by mass and 0-180°C — outside that
range CoolProp raises, surfaced here as
:class:`~flowline_scada.domain.errors.PropertyEvaluationError`, the same
error every other fluid class in this package uses, rather than silently
extrapolating past where the correlation is valid.

Example:

```python
from flowline_scada.domain.fluids.water import Brine
from flowline_scada.domain.units import Quantity

produced_water = Brine(salinity=0.08)  # 8% salinity, fairly saline formation water
density = produced_water.density(Quantity(500, "psi"), Quantity(150, "degF"))
```
"""

import typing

import attrs
import pint
from CoolProp.CoolProp import PropsSI

from flowline_scada.domain.errors import PropertyEvaluationError
from flowline_scada.domain.units import Quantity


@attrs.define(frozen=True, slots=True)
class Brine:
    """Produced or formation water at a given salinity.

    :param salinity: mass fraction of dissolved salt, from 0.0 to 1.0 —
        e.g. 0.035 for typical seawater salinity (about 3.5%). Defaults
        to 0.0 (fresh water); real oilfield produced water is very often
        well above seawater salinity, so set this explicitly for a
        realistic result.
    :raises ValueError: if ``salinity`` is outside ``[0, 1]``.

    Example:

    ```python
    seawater = Brine(salinity=0.035)
    ```
    """

    salinity: float = attrs.field(default=0.0)

    @salinity.validator
    def _check_salinity(self, attribute: "attrs.Attribute[float]", value: float) -> None:
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"salinity must be a mass fraction between 0 and 1, got {value!r}")

    @property
    def _fluid_string(self) -> str:
        return f"INCOMP::MITSW[{self.salinity}]"

    def density(
        self, pressure: "pint.Quantity[float]", temperature: "pint.Quantity[float]"
    ) -> "pint.Quantity[float]":
        """This brine's density at the given conditions.

        :param pressure: the pressure to evaluate at.
        :param temperature: the temperature to evaluate at.
        :return: the density.
        :raises ~flowline_scada.domain.errors.PropertyEvaluationError: if
            the conditions fall outside the correlation's valid range.
        """
        return Quantity(self._props_si("D", pressure, temperature), "kg/m^3")

    def viscosity(
        self, pressure: "pint.Quantity[float]", temperature: "pint.Quantity[float]"
    ) -> "pint.Quantity[float]":
        """This brine's dynamic viscosity at the given conditions.

        :param pressure: the pressure to evaluate at.
        :param temperature: the temperature to evaluate at.
        :return: the dynamic viscosity.
        :raises ~flowline_scada.domain.errors.PropertyEvaluationError: if
            the conditions fall outside the correlation's valid range.
        """
        return Quantity(self._props_si("V", pressure, temperature), "Pa*s")

    def _props_si(
        self,
        output_key: str,
        pressure: "pint.Quantity[float]",
        temperature: "pint.Quantity[float]",
    ) -> float:
        try:
            return typing.cast(
                float,
                PropsSI(
                    output_key,
                    "T",
                    temperature.to("K").magnitude,
                    "P",
                    pressure.to("Pa").magnitude,
                    self._fluid_string,
                ),
            )
        except ValueError as exc:
            raise PropertyEvaluationError(
                f"Could not evaluate {output_key!r} for brine at salinity "
                f"{self.salinity!r}, {pressure!r}, {temperature!r}: {exc}"
            ) from exc
