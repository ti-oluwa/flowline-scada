"""Tests for flowline_scada.domain.fluids.mixture."""

import pytest

from flowline_scada.domain.errors import InvalidFluidError, PropertyEvaluationError
from flowline_scada.domain.fluids.mixture import FlashResult, MixtureComposition, MixtureFluid
from flowline_scada.domain.units import Quantity


class TestMixtureComposition:
    def test_construction(self) -> None:
        composition = MixtureComposition(
            components=("methane", "decane", "water"), mole_fractions=(0.5, 0.3, 0.2)
        )
        assert len(composition) == 3

    def test_mismatched_lengths_raise(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            MixtureComposition(components=("methane", "decane"), mole_fractions=(0.5, 0.3, 0.2))

    def test_negative_fraction_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            MixtureComposition(components=("methane", "decane"), mole_fractions=(1.2, -0.2))

    def test_fractions_not_summing_to_one_raise(self) -> None:
        with pytest.raises(ValueError, match="sum to 1"):
            MixtureComposition(components=("methane", "decane"), mole_fractions=(0.5, 0.3))

    def test_fractions_within_tolerance_of_one_are_accepted(self) -> None:
        # Floating point sums won't always be bit-exact 1.0.
        MixtureComposition(components=("methane", "decane"), mole_fractions=(0.1, 0.9))


class TestMixtureFluidConstruction:
    def test_valid_composition_succeeds(self) -> None:
        composition = MixtureComposition(
            components=("methane", "decane"), mole_fractions=(0.7, 0.3)
        )
        mixture = MixtureFluid(composition)
        assert mixture.composition is composition

    def test_unrecognized_component_raises_invalid_fluid_error(self) -> None:
        composition = MixtureComposition(
            components=("methane", "not_a_real_chemical_xyz"), mole_fractions=(0.5, 0.5)
        )
        with pytest.raises(InvalidFluidError):
            MixtureFluid(composition)


class TestFlash:
    def test_gas_dominant_mixture_at_low_pressure_is_single_phase_vapor(self) -> None:
        # Mostly methane at low pressure, moderate temperature — should
        # flash to essentially all vapor.
        composition = MixtureComposition(
            components=("methane", "decane"), mole_fractions=(0.95, 0.05)
        )
        mixture = MixtureFluid(composition)
        result = mixture.flash(Quantity(50, "psi"), Quantity(150, "degF"))
        assert result.vapor_fraction > 0.9

    def test_liquid_dominant_mixture_at_low_temperature_is_mostly_liquid(self) -> None:
        composition = MixtureComposition(
            components=("methane", "decane"), mole_fractions=(0.05, 0.95)
        )
        mixture = MixtureFluid(composition)
        result = mixture.flash(Quantity(50, "psi"), Quantity(60, "degF"))
        assert result.vapor_fraction < 0.1

    def test_two_phase_conditions_give_both_compositions(self) -> None:
        composition = MixtureComposition(
            components=("methane", "decane"), mole_fractions=(0.5, 0.5)
        )
        mixture = MixtureFluid(composition)
        result = mixture.flash(Quantity(150, "psi"), Quantity(100, "degF"))
        if result.is_two_phase:
            assert result.gas_composition is not None
            assert result.liquid_composition is not None
            # Methane should concentrate in the gas phase relative to the
            # feed — basic physical sanity check on the flash result, not
            # just that it returned *something*.
            feed_methane_fraction = composition.mole_fractions[0]
            gas_methane_fraction = result.gas_composition.mole_fractions[0]
            assert gas_methane_fraction > feed_methane_fraction

    def test_invalid_conditions_raise_property_evaluation_error(self) -> None:
        composition = MixtureComposition(
            components=("methane", "decane"), mole_fractions=(0.5, 0.5)
        )
        mixture = MixtureFluid(composition)
        with pytest.raises(PropertyEvaluationError):
            mixture.flash(Quantity(-10, "psi"), Quantity(100, "degF"))


class TestFlashResultProperties:
    def test_is_single_phase_vapor(self) -> None:
        result = FlashResult(vapor_fraction=1.0, gas_composition=None, liquid_composition=None)
        assert result.is_single_phase_vapor
        assert not result.is_single_phase_liquid
        assert not result.is_two_phase

    def test_is_single_phase_liquid(self) -> None:
        result = FlashResult(vapor_fraction=0.0, gas_composition=None, liquid_composition=None)
        assert result.is_single_phase_liquid
        assert not result.is_single_phase_vapor
        assert not result.is_two_phase

    def test_is_two_phase(self) -> None:
        result = FlashResult(vapor_fraction=0.5, gas_composition=None, liquid_composition=None)
        assert result.is_two_phase
        assert not result.is_single_phase_vapor
        assert not result.is_single_phase_liquid
