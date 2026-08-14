"""Tests for flowline_scada.correlations.single_phase."""

import math

import pint
import pytest
from scipy.optimize import brentq

from flowline_scada.correlations.single_phase import (
    LAMINAR_REYNOLDS_LIMIT,
    colebrook_white_friction_factor,
    darcy_weisbach_friction_factor,
    darcy_weisbach_pressure_drop,
    reynolds_number,
)
from flowline_scada.domain.units import Quantity


def _colebrook_residual(
    friction_factor: float, relative_roughness: float, reynolds: float
) -> float:
    return 1.0 / math.sqrt(friction_factor) + 2.0 * math.log10(
        relative_roughness / 3.7 + 2.51 / (reynolds * math.sqrt(friction_factor))
    )


class TestReynoldsNumber:
    def test_known_value(self) -> None:
        re = reynolds_number(
            density=Quantity(1000, "kg/m^3"),
            velocity=Quantity(2, "m/s"),
            diameter=Quantity(0.1, "m"),
            viscosity=Quantity(0.001, "Pa*s"),
        )
        assert re == pytest.approx(200_000, rel=1e-6)

    def test_is_dimensionless(self) -> None:
        re = reynolds_number(
            density=Quantity(62.4, "lb/ft^3"),
            velocity=Quantity(4, "ft/s"),
            diameter=Quantity(0.5, "ft"),
            viscosity=Quantity(1.12, "cP"),
        )
        assert isinstance(re, float)
        assert re > 0


class TestColebrookWhiteFrictionFactor:
    @pytest.mark.parametrize(
        "relative_roughness,reynolds",
        [
            (0.0001, 1e5),
            (0.001, 5e4),
            (0.0005, 1e6),
            (0.0, 1e5),
            (0.01, 1e4),
            (0.00005, 2.5e5),
        ],
    )
    def test_matches_brentq_ground_truth(self, relative_roughness: float, reynolds: float) -> None:
        expected = brentq(_colebrook_residual, 1e-5, 1.0, args=(relative_roughness, reynolds))
        actual = colebrook_white_friction_factor(reynolds, relative_roughness)
        assert actual == pytest.approx(expected, rel=1e-6)

    def test_converges_within_a_handful_of_iterations(self) -> None:
        # The whole point of Newton-Raphson over fixed-point iteration —
        # verify it actually converges fast, not just that it converges.
        result_low_iter_cap = colebrook_white_friction_factor(1e5, 0.0001, max_iterations=6)
        result_high_iter_cap = colebrook_white_friction_factor(1e5, 0.0001, max_iterations=20)
        assert result_low_iter_cap == pytest.approx(result_high_iter_cap, rel=1e-6)

    def test_exhausting_max_iterations_returns_best_estimate_so_far(self) -> None:
        # An artificially tight iteration cap that can't reach `tolerance`
        # should still return a usable (if not fully converged) estimate
        # rather than raising — exercises the loop-exhaustion fallback.
        result = colebrook_white_friction_factor(1e5, 0.0001, max_iterations=1)
        expected = brentq(_colebrook_residual, 1e-5, 1.0, args=(0.0001, 1e5))
        # Not fully converged after a single iteration, but still in the
        # right ballpark rather than wildly wrong.
        assert result == pytest.approx(expected, rel=0.1)

    def test_zero_reynolds_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            colebrook_white_friction_factor(0, 0.0001)

    def test_negative_reynolds_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            colebrook_white_friction_factor(-100, 0.0001)


class TestDarcyWeisbachFrictionFactor:
    def test_laminar_regime_uses_exact_formula(self) -> None:
        reynolds = 1500.0
        assert darcy_weisbach_friction_factor(reynolds, 0.0001) == pytest.approx(64.0 / reynolds)

    def test_at_laminar_limit_uses_laminar_formula(self) -> None:
        assert darcy_weisbach_friction_factor(LAMINAR_REYNOLDS_LIMIT, 0.0001) == pytest.approx(
            64.0 / LAMINAR_REYNOLDS_LIMIT
        )

    def test_turbulent_regime_uses_colebrook_white(self) -> None:
        reynolds, relative_roughness = 1e5, 0.0001
        assert darcy_weisbach_friction_factor(reynolds, relative_roughness) == pytest.approx(
            colebrook_white_friction_factor(reynolds, relative_roughness)
        )

    def test_zero_reynolds_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            darcy_weisbach_friction_factor(0, 0.0001)

    def test_negative_relative_roughness_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            darcy_weisbach_friction_factor(1e5, -0.001)


class TestDarcyWeisbachPressureDrop:
    def test_pressure_drop_is_positive_for_positive_flow(self) -> None:
        result = darcy_weisbach_pressure_drop(
            length=Quantity(1000, "ft"),
            internal_diameter=Quantity(6, "inch"),
            roughness=Quantity(0.0018, "inch"),
            mass_flow_rate=Quantity(50, "lb/s"),
            density=Quantity(62.4, "lb/ft^3"),
            viscosity=Quantity(1.12, "cP"),
        )
        assert result.pressure_drop.magnitude > 0
        assert result.friction_factor > 0
        assert result.reynolds_number > 0

    def test_pressure_drop_scales_with_length(self) -> None:
        kwargs: dict[str, pint.Quantity[float]] = {
            "internal_diameter": Quantity(6, "inch"),
            "roughness": Quantity(0.0018, "inch"),
            "mass_flow_rate": Quantity(50, "lb/s"),
            "density": Quantity(62.4, "lb/ft^3"),
            "viscosity": Quantity(1.12, "cP"),
        }
        short = darcy_weisbach_pressure_drop(length=Quantity(500, "ft"), **kwargs)
        long = darcy_weisbach_pressure_drop(length=Quantity(1000, "ft"), **kwargs)
        # Darcy-Weisbach is linear in length (f, Re, velocity unaffected by length).
        assert long.pressure_drop.magnitude == pytest.approx(
            2 * short.pressure_drop.magnitude, rel=1e-9
        )

    def test_higher_flow_rate_gives_higher_pressure_drop(self) -> None:
        kwargs: dict[str, pint.Quantity[float]] = {
            "length": Quantity(1000, "ft"),
            "internal_diameter": Quantity(6, "inch"),
            "roughness": Quantity(0.0018, "inch"),
            "density": Quantity(62.4, "lb/ft^3"),
            "viscosity": Quantity(1.12, "cP"),
        }
        low_flow = darcy_weisbach_pressure_drop(mass_flow_rate=Quantity(20, "lb/s"), **kwargs)
        high_flow = darcy_weisbach_pressure_drop(mass_flow_rate=Quantity(80, "lb/s"), **kwargs)
        assert high_flow.pressure_drop > low_flow.pressure_drop

    def test_zero_mass_flow_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            darcy_weisbach_pressure_drop(
                length=Quantity(1000, "ft"),
                internal_diameter=Quantity(6, "inch"),
                roughness=Quantity(0.0018, "inch"),
                mass_flow_rate=Quantity(0, "lb/s"),
                density=Quantity(62.4, "lb/ft^3"),
                viscosity=Quantity(1.12, "cP"),
            )

    def test_negative_mass_flow_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            darcy_weisbach_pressure_drop(
                length=Quantity(1000, "ft"),
                internal_diameter=Quantity(6, "inch"),
                roughness=Quantity(0.0018, "inch"),
                mass_flow_rate=Quantity(-10, "lb/s"),
                density=Quantity(62.4, "lb/ft^3"),
                viscosity=Quantity(1.12, "cP"),
            )

    def test_result_units_convert_correctly(self) -> None:
        result = darcy_weisbach_pressure_drop(
            length=Quantity(1000, "ft"),
            internal_diameter=Quantity(6, "inch"),
            roughness=Quantity(0.0018, "inch"),
            mass_flow_rate=Quantity(50, "lb/s"),
            density=Quantity(62.4, "lb/ft^3"),
            viscosity=Quantity(1.12, "cP"),
        )
        # Same physical result regardless of which unit you view it in.
        assert result.pressure_drop.to("psi").magnitude == pytest.approx(
            result.pressure_drop.to("Pa").magnitude / 6894.757, rel=1e-4
        )
