"""Tests for flowline_scada.domain.fluids.pure."""

import pytest

from flowline_scada.domain.errors import InvalidFluidError, PropertyEvaluationError
from flowline_scada.domain.fluids.pure import PureFluid
from flowline_scada.domain.units import Quantity


@pytest.fixture
def methane() -> PureFluid:
    return PureFluid(name="Methane")


@pytest.fixture
def water() -> PureFluid:
    return PureFluid(name="Water")


class TestConstruction:
    def test_valid_fluid_name_succeeds(self) -> None:
        fluid = PureFluid(name="Methane")
        assert fluid.name == "Methane"

    def test_unrecognized_fluid_name_raises_invalid_fluid_error(self) -> None:
        with pytest.raises(InvalidFluidError):
            PureFluid(name="NotARealFluid")

    def test_is_frozen(self, methane: PureFluid) -> None:
        with pytest.raises(Exception):  # noqa: B017 — attrs raises FrozenInstanceError
            methane.name = "Water"  # type: ignore[misc]


class TestMolecularWeight:
    def test_methane_molecular_weight(self, methane: PureFluid) -> None:
        # CODATA/NIST value for methane is 16.043 g/mol.
        assert methane.molecular_weight.to("g/mol").magnitude == pytest.approx(16.04, abs=0.01)

    def test_water_molecular_weight(self, water: PureFluid) -> None:
        assert water.molecular_weight.to("g/mol").magnitude == pytest.approx(18.015, abs=0.01)

    def test_molecular_weight_is_independent_of_state(self, methane: PureFluid) -> None:
        # No pressure/temperature args at all — this should be a fixed
        # property of the fluid, not a function of state.
        assert methane.molecular_weight == methane.molecular_weight


class TestDensity:
    def test_water_density_at_standard_conditions(self, water: PureFluid) -> None:
        # Water is ~999 kg/m^3 (~62.4 lb/ft^3) near 60F/1atm — the
        # standard oilfield reference condition.
        density = water.density(Quantity(1, "atm"), Quantity(60, "degF"))
        assert density.to("kg/m^3").magnitude == pytest.approx(999.0, rel=1e-3)

    def test_water_density_in_imperial_units(self, water: PureFluid) -> None:
        density = water.density(Quantity(1, "atm"), Quantity(60, "degF"))
        assert density.to("lb/ft^3").magnitude == pytest.approx(62.37, rel=1e-3)

    def test_gas_density_increases_with_pressure(self, methane: PureFluid) -> None:
        temperature = Quantity(60.0, "degF")
        low_pressure_density = methane.density(Quantity(100, "psi"), temperature)
        high_pressure_density = methane.density(Quantity(1000, "psi"), temperature)
        assert high_pressure_density > low_pressure_density

    def test_liquid_density_decreases_with_temperature(self, water: PureFluid) -> None:
        pressure = Quantity(1.0, "atm")
        cool_density = water.density(pressure, Quantity(40, "degF"))
        warm_density = water.density(pressure, Quantity(150, "degF"))
        assert warm_density < cool_density


class TestViscosity:
    def test_water_viscosity_at_standard_conditions(self, water: PureFluid) -> None:
        # ~1.12 cP at 60F is the standard reference value.
        viscosity = water.viscosity(Quantity(1, "atm"), Quantity(60, "degF"))
        assert viscosity.to("cP").magnitude == pytest.approx(1.12, rel=0.02)

    def test_liquid_viscosity_decreases_with_temperature(self, water: PureFluid) -> None:
        pressure = Quantity(1.0, "atm")
        cool_viscosity = water.viscosity(pressure, Quantity(40, "degF"))
        warm_viscosity = water.viscosity(pressure, Quantity(150, "degF"))
        assert warm_viscosity < cool_viscosity


class TestCompressibilityFactor:
    def test_ideal_gas_limit_at_low_pressure(self, methane: PureFluid) -> None:
        # Z -> 1 as P -> 0 for any real gas (the ideal-gas limit).
        z = methane.compressibility_factor(Quantity(1, "psi"), Quantity(60, "degF"))
        assert z == pytest.approx(1.0, abs=0.01)

    def test_deviates_from_ideal_at_elevated_pressure(self, methane: PureFluid) -> None:
        # At typical pipeline pressures methane's Z drops measurably below 1.
        z = methane.compressibility_factor(Quantity(1000, "psi"), Quantity(60, "degF"))
        assert 0.80 < z < 0.99


class TestPhase:
    def test_water_at_standard_conditions_is_liquid(self, water: PureFluid) -> None:
        assert water.phase(Quantity(1, "atm"), Quantity(60, "degF")) == "liquid"

    def test_methane_at_low_pressure_and_ambient_temperature_is_supercritical_gas(
        self, methane: PureFluid
    ) -> None:
        # Methane's critical temperature is ~-117°F — any ambient/process
        # temperature relevant to a surface pipeline is above that, so
        # CoolProp classifies it as "supercritical_gas" rather than plain
        # "gas" (a subcritical-only classification) regardless of
        # pressure. This is the physically correct, expected case for
        # essentially all real gas-gathering conditions, not an edge case.
        assert methane.phase(Quantity(14.7, "psi"), Quantity(60, "degF")) == "supercritical_gas"

    def test_methane_below_its_critical_temperature_is_plain_gas(self, methane: PureFluid) -> None:
        # Below methane's ~-117°F critical temperature, low-pressure vapor
        # is classified as subcritical "gas" — this is the case that
        # actually distinguishes "gas" from "supercritical_gas".
        assert methane.phase(Quantity(14.7, "psi"), Quantity(-150, "degF")) == "gas"

    def test_water_above_boiling_at_atmospheric_pressure_is_gas(self, water: PureFluid) -> None:
        assert water.phase(Quantity(1, "atm"), Quantity(250, "degF")) == "gas"


class TestJouleThomsonCoefficient:
    def test_methane_jt_coefficient_is_positive_at_pipeline_conditions(
        self, methane: PureFluid
    ) -> None:
        # Below its inversion temperature (the case for essentially every
        # real pipeline scenario), a real gas cools on throttling — a
        # positive JT coefficient. This is the physical basis for the
        # cooling effect a solver needs to model across a choke or a large
        # pressure drop.
        jt = methane.joule_thomson_coefficient(Quantity(1000, "psi"), Quantity(60, "degF"))
        assert jt.magnitude > 0


class TestErrorHandling:
    def test_negative_pressure_raises_property_evaluation_error(self, water: PureFluid) -> None:
        with pytest.raises(PropertyEvaluationError):
            water.density(Quantity(-10, "psi"), Quantity(60, "degF"))

    def test_phase_lookup_with_invalid_state_raises_property_evaluation_error(
        self, water: PureFluid
    ) -> None:
        with pytest.raises(PropertyEvaluationError):
            water.phase(Quantity(-10, "psi"), Quantity(60, "degF"))

    def test_error_message_names_the_fluid_and_state(self, water: PureFluid) -> None:
        with pytest.raises(PropertyEvaluationError, match="Water"):
            water.density(Quantity(-10, "psi"), Quantity(60, "degF"))
