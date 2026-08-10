"""
Multi-component mixture thermodynamics, backed by `thermo
<https://thermo.readthedocs.io>`_'s Peng-Robinson cubic-EOS flash.

Use this for a real multi-component stream — a live gas-oil-water stream
with a defined composition — where you need to know the actual
phase-equilibrium split: how much of it is vapor vs. liquid, and what
each phase is made of. For a single component (or something you're
comfortable approximating as one), see
:mod:`flowline_scada.domain.fluids.pure` instead — it's faster and
doesn't need a full flash calculation.

Example:

```python
from flowline_scada.domain.fluids.mixture import MixtureComposition, MixtureFluid
from flowline_scada.domain.units import Quantity

composition = MixtureComposition(
    components=("methane", "decane", "water"),
    mole_fractions=(0.5, 0.3, 0.2),
)
mixture = MixtureFluid(composition)

result = mixture.flash(Quantity(150, "psi"), Quantity(80, "degF"))
print(result.vapor_fraction, result.is_two_phase)
```
"""

import math
import typing

import attrs
import pint
from thermo import PRMIX, CEOSGas, CEOSLiquid, ChemicalConstantsPackage, FlashVL

from flowline_scada.domain.errors import InvalidFluidError, PropertyEvaluationError


def _to_str_tuple(value: typing.Iterable[str]) -> "tuple[str, ...]":
    return tuple(value)


def _to_float_tuple(value: typing.Iterable[float]) -> "tuple[float, ...]":
    return tuple(value)


@attrs.define(frozen=True, slots=True)
class MixtureComposition:
    """A mixture's components and their mole fractions.

    :param components: chemical names/IDs `thermo` recognizes, e.g.
        ``("methane", "decane", "water")``.
    :param mole_fractions: mole fraction of each component, in the same
        order as ``components``. Must be non-negative and sum to 1.0
        (within floating-point tolerance).
    :raises ValueError: if ``mole_fractions`` isn't the same length as
        ``components``, contains a negative value, or doesn't sum to 1.0.

    Example:

    ```python
    composition = MixtureComposition(
        components=("methane", "decane", "water"),
        mole_fractions=(0.5, 0.3, 0.2),
    )
    len(composition)  # 3
    ```
    """

    components: "tuple[str, ...]" = attrs.field(converter=_to_str_tuple)
    mole_fractions: "tuple[float, ...]" = attrs.field(converter=_to_float_tuple)

    @mole_fractions.validator
    def _check_mole_fractions(
        self, attribute: "attrs.Attribute[tuple[float, ...]]", value: "tuple[float, ...]"
    ) -> None:
        if len(value) != len(self.components):
            raise ValueError(
                f"mole_fractions has {len(value)} entries but components has "
                f"{len(self.components)} — they must be the same length."
            )
        if any(fraction < 0 for fraction in value):
            raise ValueError(f"mole fractions must be non-negative, got {value!r}")
        total = math.fsum(value)
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(f"mole fractions must sum to 1.0, got {total!r} ({value!r})")

    def __len__(self) -> int:
        """The number of components in this mixture."""
        return len(self.components)


@attrs.define(frozen=True, slots=True)
class FlashResult:
    """The result of a vapor-liquid equilibrium flash at fixed pressure
    and temperature — see :meth:`MixtureFluid.flash`.

    :param vapor_fraction: the mole fraction of the overall stream that's
        vapor. 0 = entirely liquid, 1 = entirely vapor, anything in
        between is two-phase.
    :param gas_composition: the composition within the vapor phase
        specifically, or ``None`` if there's no vapor phase present.
    :param liquid_composition: the composition within the liquid phase
        specifically, or ``None`` if there's no liquid phase present.
    """

    vapor_fraction: float
    gas_composition: "MixtureComposition | None"
    liquid_composition: "MixtureComposition | None"

    @property
    def is_single_phase_vapor(self) -> bool:
        """``True`` if the whole stream is vapor."""
        return self.vapor_fraction >= 1.0

    @property
    def is_single_phase_liquid(self) -> bool:
        """``True`` if the whole stream is liquid."""
        return self.vapor_fraction <= 0.0

    @property
    def is_two_phase(self) -> bool:
        """``True`` if the stream has split into both vapor and liquid."""
        return 0.0 < self.vapor_fraction < 1.0


class MixtureFluid:
    """A multi-component fluid mixture, flashed via Peng-Robinson EOS.

    Building the underlying flash machinery (pulling chemical constants,
    setting up the gas/liquid phase objects) is real work — this class
    does it once when you construct it and reuses it for every
    :meth:`flash` call, rather than rebuilding it per lookup.

    :param composition: the mixture's components and mole fractions.
    :raises ~flowline_scada.domain.errors.InvalidFluidError: if any
        component name in ``composition`` isn't a chemical `thermo` recognizes.

    Example:

    ```python
    mixture = MixtureFluid(MixtureComposition(
        components=("methane", "decane"), mole_fractions=(0.7, 0.3),
    ))
    ```
    """

    def __init__(self, composition: MixtureComposition) -> None:
        self.composition = composition
        try:
            constants, properties = ChemicalConstantsPackage.from_IDs(list(composition.components))
        except ValueError as exc:
            raise InvalidFluidError(
                f"One or more of {composition.components!r} is not a chemical "
                f"thermo recognizes: {exc}"
            ) from exc

        self._constants = constants
        self._properties = properties
        eos_kwargs = {
            "Tcs": constants.Tcs,
            "Pcs": constants.Pcs,
            "omegas": constants.omegas,
        }
        zs = list(composition.mole_fractions)
        # Reference (T, P) here is just to construct the phase objects —
        # every actual flash() call below passes its own (T, P, zs) and
        # is independent of whatever was used at construction.
        gas = CEOSGas(
            PRMIX,
            T=298.15,
            P=101325.0,
            zs=zs,
            eos_kwargs=eos_kwargs,
            HeatCapacityGases=properties.HeatCapacityGases,
        )
        liquid = CEOSLiquid(
            PRMIX,
            T=298.15,
            P=101325.0,
            zs=zs,
            eos_kwargs=eos_kwargs,
            HeatCapacityGases=properties.HeatCapacityGases,
        )
        self._flasher = FlashVL(constants, properties, liquid=liquid, gas=gas)

    def flash(
        self, pressure: "pint.Quantity[float]", temperature: "pint.Quantity[float]"
    ) -> FlashResult:
        """Run a vapor-liquid equilibrium flash at the given conditions.

        :param pressure: the pressure to flash at.
        :param temperature: the temperature to flash at.
        :return: the flash result — vapor fraction and each phase's composition.
        :raises ~flowline_scada.domain.errors.PropertyEvaluationError: if
            the flash fails to converge or the conditions are unphysical.
        """
        try:
            result = self._flasher.flash(
                T=temperature.to("K").magnitude,
                P=pressure.to("Pa").magnitude,
                zs=list(self.composition.mole_fractions),
            )
        except ValueError as exc:
            raise PropertyEvaluationError(
                f"Flash failed for {self.composition.components!r} at "
                f"{pressure!r}, {temperature!r}: {exc}"
            ) from exc

        vapor_fraction = float(result.VF)
        gas_composition = (
            MixtureComposition(components=self.composition.components, mole_fractions=result.gas.zs)
            if result.gas is not None
            else None
        )
        liquid_composition = (
            MixtureComposition(
                components=self.composition.components, mole_fractions=result.liquid0.zs
            )
            if result.liquid0 is not None
            else None
        )
        return FlashResult(
            vapor_fraction=vapor_fraction,
            gas_composition=gas_composition,
            liquid_composition=liquid_composition,
        )
