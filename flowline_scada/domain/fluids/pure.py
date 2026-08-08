"""
Pure and pseudo-pure fluid properties, backed by CoolProp.

`PureFluid` wraps a single named fluid CoolProp recognizes (e.g.
"Methane", "Water", "n-Decane") and exposes property lookups as
pint-quantified methods. This is the fast path for anything that's a
single component or can be reasonably treated as one (a sales-gas stream
modeled as methane, for instance) — for real multi-component mixture
flash (a live gas-oil-water stream with a defined composition), see
`fluids.mixture` instead.

Deliberately uncached: this module is direct and correct, not optimized.
Quantized caching for hot-path repeated lookups during iterative solving
is a solver-layer concern (`solver/fluid_cache.py`, arrives with Phase 2)
— see the v1 review for why an uncached call here and a cache keyed on
unrounded floats both defeat the purpose; this module intentionally does
neither, and leaves it to the layer that actually knows the access
pattern.
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
    """A single-component (or well-defined pseudo-pure) fluid."""

    name: str = attrs.field(validator=_validate_fluid_name)
    """CoolProp fluid name, e.g. 'Methane', 'Water', 'n-Decane'."""

    @property
    def molecular_weight(self) -> "pint.Quantity[float]":
        """Molar mass, independent of pressure/temperature."""
        return Quantity(PropsSI("M", self.name), "kg/mol")

    def density(
        self, pressure: "pint.Quantity[float]", temperature: "pint.Quantity[float]"
    ) -> "pint.Quantity[float]":
        value = self._props_si("D", pressure, temperature)
        return Quantity(value, "kg/m^3")

    def viscosity(
        self, pressure: "pint.Quantity[float]", temperature: "pint.Quantity[float]"
    ) -> "pint.Quantity[float]":
        value = self._props_si("V", pressure, temperature)
        return Quantity(value, "Pa*s")

    def compressibility_factor(
        self, pressure: "pint.Quantity[float]", temperature: "pint.Quantity[float]"
    ) -> float:
        """Dimensionless Z-factor, PV = ZnRT. 1.0 for an ideal gas."""
        return self._props_si("Z", pressure, temperature)

    def phase(
        self, pressure: "pint.Quantity[float]", temperature: "pint.Quantity[float]"
    ) -> FluidPhase:
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
        """dT/dP at constant enthalpy. Positive for most gases below their
        inversion temperature (the typical pipeline case) — an expanding
        gas cools; negative above the inversion temperature."""
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
