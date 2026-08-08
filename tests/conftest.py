"""Shared pytest fixtures for the test suite."""

import typing

import pytest

from flowline_scada.domain.units import (
    IMPERIAL,
    OIL_FIELD,
    SI,
    QuantityUnit,
    UnitSystem,
)


@pytest.fixture(params=[IMPERIAL, SI, OIL_FIELD], ids=["imperial", "si", "oil_field"])
def unit_system(request: pytest.FixtureRequest) -> UnitSystem[QuantityUnit]:
    """Each built-in UnitSystem in turn, so shared-shape tests run against all three."""
    return typing.cast(UnitSystem[QuantityUnit], request.param)


@pytest.fixture
def empty_unit_system() -> UnitSystem[QuantityUnit]:
    """A UnitSystem with no quantities defined, for exercising the missing-key fallback."""
    return UnitSystem("empty")
