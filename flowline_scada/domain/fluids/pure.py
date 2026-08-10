"""
Properties of a single fluid component, backed by `CoolProp <http://www.coolprop.org>`_.

Use :class:`PureFluid` for anything that's a single chemical component,
or that you're comfortable approximating as one (a sales-gas stream
modeled as methane, for instance). For a real multi-component mixture
where you need to know the actual phase split (a live gas-oil-water
stream with a defined composition), see
:mod:`flowline_scada.domain.fluids.mixture` instead.

Example:

```python
from flowline_scada.domain.fluids.pure import PureFluid
from flowline_scada.domain.units import Quantity

methane = PureFluid(name="Methane")
density = methane.density(Quantity(800, "psi"), Quantity(60, "degF"))
print(density.to("lb/ft^3"))
```
"""

import typing

import attrs
import pint
from CoolProp.CoolProp import PhaseSI, PropsSI

from flowline_scada.domain.errors import InvalidFluidError, PropertyEvaluationError
from flowline_scada.domain.units import Quantity

FluidPhase = typing.Literal[
    "critical_point",
    "gas",
    "liquid",
    "not_imposed",
    "supercritical",
    "supercritical_gas",
    "supercritical_liquid",
    "twophase",
    "unknown",
]
"""The phase labels :meth:`PureFluid.phase` can return."""


def _validate_fluid_name(
    instance: "PureFluid", attribute: "attrs.Attribute[str]", value: str
) -> None:
    try:
        PropsSI("M", value)
    except ValueError as exc:
        raise InvalidFluidError(
            f"{value!r} is not a fluid CoolProp recognizes. See "
            "http://www.coolprop.org/fluid_properties/PurePseudoPure.html "
            "for the list of supported fluid names."
        ) from exc


@attrs.define(frozen=True, slots=True)
class PureFluid:
    """A single-component (or well-defined pseudo-pure) fluid.

    Every property lookup takes the pressure and temperature to evaluate
    at — nothing is cached here, since how much caching makes sense (and
    with what key) depends on the access pattern of whatever's calling
    this repeatedly, which this class doesn't know about.

    :param name: a CoolProp fluid name, e.g. ``"Methane"``, ``"Water"``,
        ``"n-Decane"`` — see the `CoolProp fluid list
        <http://www.coolprop.org/fluid_properties/PurePseudoPure.html>`_
        for everything supported.
    :raises ~flowline_scada.domain.errors.InvalidFluidError: if ``name``
        isn't a fluid CoolProp recognizes.

    Example:

    ```python
    water = PureFluid(name="Water")
    ```
    """

    name: str = attrs.field(validator=_validate_fluid_name)

    @property
    def molecular_weight(self) -> "pint.Quantity[float]":
        """This fluid's molar mass. Doesn't depend on pressure or
        temperature, unlike every other property on this class."""
        return Quantity(PropsSI("M", self.name), "kg/mol")

    def density(
        self, pressure: "pint.Quantity[float]", temperature: "pint.Quantity[float]"
    ) -> "pint.Quantity[float]":
        """This fluid's density at the given conditions.

        :param pressure: the pressure to evaluate at.
        :param temperature: the temperature to evaluate at.
        :return: the density.
        :raises ~flowline_scada.domain.errors.PropertyEvaluationError: if
            the property can't be evaluated at these conditions.
        """
        value = self._props_si("D", pressure, temperature)
        return Quantity(value, "kg/m^3")

    def viscosity(
        self, pressure: "pint.Quantity[float]", temperature: "pint.Quantity[float]"
    ) -> "pint.Quantity[float]":
        """This fluid's dynamic viscosity at the given conditions.

        :param pressure: the pressure to evaluate at.
        :param temperature: the temperature to evaluate at.
        :return: the dynamic viscosity.
        :raises ~flowline_scada.domain.errors.PropertyEvaluationError: if
            the property can't be evaluated at these conditions.
        """
        value = self._props_si("V", pressure, temperature)
        return Quantity(value, "Pa*s")

    def compressibility_factor(
        self, pressure: "pint.Quantity[float]", temperature: "pint.Quantity[float]"
    ) -> float:
        """This fluid's compressibility factor (Z, where PV = ZnRT) at
        the given conditions — a dimensionless number, 1.0 for an ideal
        gas and generally less than 1.0 for a real gas at typical
        pipeline pressures.

        :param pressure: the pressure to evaluate at.
        :param temperature: the temperature to evaluate at.
        :return: the compressibility factor.
        :raises ~flowline_scada.domain.errors.PropertyEvaluationError: if
            the property can't be evaluated at these conditions.
        """
        return self._props_si("Z", pressure, temperature)

    def phase(
        self, pressure: "pint.Quantity[float]", temperature: "pint.Quantity[float]"
    ) -> FluidPhase:
        """Which phase this fluid is in at the given conditions.

        :param pressure: the pressure to evaluate at.
        :param temperature: the temperature to evaluate at.
        :return: one of the :data:`FluidPhase` labels, e.g. ``"liquid"``,
            ``"gas"``, ``"supercritical_gas"``.
        :raises ~flowline_scada.domain.errors.PropertyEvaluationError: if
            the phase can't be determined at these conditions.

        Note that a fluid held above its critical temperature is always
        ``"supercritical"``/``"supercritical_gas"``, never plain
        ``"gas"``, regardless of pressure — methane's critical
        temperature is about -117°F, for instance, so methane at any
        normal ambient or process temperature is always supercritical.
        """
        # Unlike PropsSI, PhaseSI does not raise for an unsolvable state —
        # verified empirically across NaN, zero, and out-of-range inputs,
        # it always returns a string like "unknown: solver_rho_Tp was
        # unable to find a solution for T=..." embedding the failure
        # instead of raising. So there's no ValueError to catch here (a
        # try/except ValueError around this call would be dead,
        # untestable code pretending to handle something that can't
        # happen) — the actual error contract is the sentinel string
        # checked below.
        result = PhaseSI(
            "P",
            pressure.to("Pa").magnitude,
            "T",
            temperature.to("K").magnitude,
            self.name,
        )
        if result not in typing.get_args(FluidPhase):
            raise PropertyEvaluationError(
                f"Could not determine phase for {self.name!r} at "
                f"{pressure!r}, {temperature!r}: {result}"
            )
        return typing.cast(FluidPhase, result)

    def joule_thomson_coefficient(
        self, pressure: "pint.Quantity[float]", temperature: "pint.Quantity[float]"
    ) -> "pint.Quantity[float]":
        """This fluid's Joule-Thomson coefficient (dT/dP at constant
        enthalpy) at the given conditions — how much its temperature
        changes as it expands through a restriction with no heat
        exchanged.

        :param pressure: the pressure to evaluate at.
        :param temperature: the temperature to evaluate at.
        :return: the Joule-Thomson coefficient.
        :raises ~flowline_scada.domain.errors.PropertyEvaluationError: if
            the property can't be evaluated at these conditions.

        Positive for most gases below their inversion temperature — the
        typical pipeline case, where an expanding gas cools rather than
        heats. Negative above the inversion temperature.
        """
        value = self._props_si("d(T)/d(P)|H", pressure, temperature)
        return Quantity(value, "K/Pa")

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
                    "P",
                    pressure.to("Pa").magnitude,
                    "T",
                    temperature.to("K").magnitude,
                    self.name,
                ),
            )
        except ValueError as exc:
            raise PropertyEvaluationError(
                f"Could not evaluate {output_key!r} for {self.name!r} at "
                f"{pressure!r}, {temperature!r}: {exc}"
            ) from exc
