"""Tests for flowline_scada.domain.fluids.water."""

import pytest

from flowline_scada.domain.errors import PropertyEvaluationError
from flowline_scada.domain.fluids.water import Brine
from flowline_scada.domain.units import Quantity


class TestConstruction:
    def test_default_salinity_is_zero(self) -> None:
        brine = Brine()
        assert brine.salinity == 0.0

    def test_explicit_salinity(self) -> None:
        brine = Brine(salinity=0.08)
        assert brine.salinity == 0.08

    def test_negative_salinity_raises(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            Brine(salinity=-0.01)

    def test_salinity_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            Brine(salinity=1.01)


class TestDensity:
    def test_freshwater_density_matches_pure_water(self) -> None:
        # 0% salinity via MITSW should closely match plain pure-water
        # density (~999 kg/m^3 at 60F) — verified directly against
        # CoolProp before writing this module.
        fresh = Brine(salinity=0.0)
        density = fresh.density(Quantity(1, "atm"), Quantity(60, "degF"))
        assert density.to("kg/m^3").magnitude == pytest.approx(999.0, rel=0.01)

    def test_seawater_salinity_density_matches_known_reference(self) -> None:
        # Real seawater (~3.5% salinity) is ~1025 kg/m^3 — a widely known
        # reference value, and a good sanity check that the salinity
        # parameter is actually doing something physically correct.
        seawater = Brine(salinity=0.035)
        density = seawater.density(Quantity(1, "atm"), Quantity(60, "degF"))
        assert density.to("kg/m^3").magnitude == pytest.approx(1025.9, rel=0.01)

    def test_higher_salinity_gives_higher_density(self) -> None:
        pressure = Quantity(1.0, "atm")
        temperature = Quantity(60.0, "degF")
        low_salinity_density = Brine(salinity=0.02).density(pressure, temperature)
        high_salinity_density = Brine(salinity=0.10).density(pressure, temperature)
        assert high_salinity_density > low_salinity_density


class TestViscosity:
    def test_freshwater_viscosity_matches_pure_water(self) -> None:
        fresh = Brine(salinity=0.0)
        viscosity = fresh.viscosity(Quantity(1, "atm"), Quantity(60, "degF"))
        assert viscosity.to("cP").magnitude == pytest.approx(1.12, rel=0.05)


class TestErrorHandling:
    def test_out_of_range_conditions_raise_property_evaluation_error(self) -> None:
        brine = Brine(salinity=0.035)
        with pytest.raises(PropertyEvaluationError):
            brine.density(Quantity(-10, "psi"), Quantity(60, "degF"))

    def test_error_message_includes_salinity(self) -> None:
        brine = Brine(salinity=0.035)
        with pytest.raises(PropertyEvaluationError, match="0.035")
            brine.density(Quantity(-10, "psi"), Quantity(60, "degF"))
