"""Tests for flowline_scada.domain.validators."""

import attrs
import pytest

from flowline_scada.domain.units import Quantity
from flowline_scada.domain.validators import (
    non_negative_quantity,
    positive_quantity,
    quantity_with_dimensionality,
    unit_fraction,
)


@attrs.define
class _Dummy:
    """A tiny attrs class used to exercise each validator through attrs'
    real construction/mutation path, not by calling the validator
    functions directly — that's what actually proves they're wired up
    correctly as attrs validators, not just correct as plain functions."""

    length: "object" = attrs.field(validator=positive_quantity("[length]"))
    roughness: "object" = attrs.field(validator=non_negative_quantity("[length]"))
    pressure: "object" = attrs.field(validator=quantity_with_dimensionality("[pressure]"))
    fraction: float = attrs.field(validator=unit_fraction)


def _make(**overrides: object) -> _Dummy:
    defaults: dict[str, object] = {
        "length": Quantity(10, "ft"),
        "roughness": Quantity(0, "m"),
        "pressure": Quantity(100, "psi"),
        "fraction": 0.5,
    }
    defaults.update(overrides)
    return _Dummy(**defaults)  # type: ignore[arg-type]


class TestPositiveQuantity:
    def test_accepts_positive_value(self) -> None:
        _make(length=Quantity(1, "ft"))  # should not raise

    def test_rejects_zero(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            _make(length=Quantity(0, "ft"))

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            _make(length=Quantity(-1, "ft"))

    def test_rejects_wrong_dimensionality(self) -> None:
        with pytest.raises(ValueError, match="dimensionality"):
            _make(length=Quantity(1, "psi"))

    def test_revalidates_on_mutation(self) -> None:
        dummy = _make()
        with pytest.raises(ValueError, match="must be positive"):
            dummy.length = Quantity(-1, "ft")


class TestNonNegativeQuantity:
    def test_accepts_zero(self) -> None:
        _make(roughness=Quantity(0, "m"))  # should not raise

    def test_accepts_positive_value(self) -> None:
        _make(roughness=Quantity(0.001, "m"))  # should not raise

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="must be non-negative"):
            _make(roughness=Quantity(-0.001, "m"))

    def test_rejects_wrong_dimensionality(self) -> None:
        with pytest.raises(ValueError, match="dimensionality"):
            _make(roughness=Quantity(1, "psi"))


class TestQuantityWithDimensionality:
    def test_accepts_matching_dimensionality(self) -> None:
        _make(pressure=Quantity(14.7, "psi"))  # should not raise

    def test_accepts_matching_dimensionality_different_unit(self) -> None:
        _make(pressure=Quantity(101325, "Pa"))  # same dimensionality, different unit

    def test_rejects_mismatched_dimensionality(self) -> None:
        with pytest.raises(ValueError, match="dimensionality"):
            _make(pressure=Quantity(10, "ft"))

    def test_negative_value_is_allowed(self) -> None:
        # Dimensionality-only check — no sign constraint. A gauge
        # pressure can legitimately be negative (vacuum).
        _make(pressure=Quantity(-1, "psi"))  # should not raise


class TestUnitFraction:
    def test_accepts_zero(self) -> None:
        _make(fraction=0.0)  # should not raise

    def test_accepts_one(self) -> None:
        _make(fraction=1.0)  # should not raise

    def test_accepts_mid_range_value(self) -> None:
        _make(fraction=0.42)  # should not raise

    def test_rejects_below_zero(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            _make(fraction=-0.01)

    def test_rejects_above_one(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            _make(fraction=1.01)
