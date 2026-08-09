"""Reusable attrs validators for domain models.

Pulled out into their own module because the same handful of checks
(positive length, non-negative length, a value that's a fraction between
0 and 1) recur across every physical-component class in `components.py`
— writing them once here means a bug fix or a clearer error message only
needs to happen in one place.
"""

import typing

import attrs
import pint


def quantity_with_dimensionality(
    dimensionality: str,
) -> typing.Callable[[object, "attrs.Attribute[pint.Quantity]", "pint.Quantity"], None]:
    """Validator factory: the value must be a Quantity with the given
    pint dimensionality string, e.g. '[length]', '[pressure]'."""

    def _validator(
        instance: object, attribute: "attrs.Attribute[pint.Quantity]", value: "pint.Quantity"
    ) -> None:
        if not value.check(dimensionality):
            raise ValueError(
                f"{attribute.name} must have dimensionality {dimensionality!r}, "
                f"got {value.units!r} ({value!r})"
            )

    return _validator


def positive_quantity(
    dimensionality: str,
) -> typing.Callable[[object, "attrs.Attribute[pint.Quantity]", "pint.Quantity"], None]:
    """Validator factory: a Quantity with the given dimensionality that
    must be strictly greater than zero — a pipe length or diameter, for
    instance, since a zero or negative one isn't physically meaningful."""

    dimensionality_check = quantity_with_dimensionality(dimensionality)

    def _validator(
        instance: object, attribute: "attrs.Attribute[pint.Quantity]", value: "pint.Quantity"
    ) -> None:
        dimensionality_check(instance, attribute, value)
        if value.magnitude <= 0:
            raise ValueError(f"{attribute.name} must be positive, got {value!r}")

    return _validator


def non_negative_quantity(
    dimensionality: str,
) -> typing.Callable[[object, "attrs.Attribute[pint.Quantity]", "pint.Quantity"], None]:
    """Validator factory: a Quantity with the given dimensionality that
    must be zero or greater — pipe roughness, for instance, where zero
    (a perfectly smooth pipe) is a physically valid, if idealized, value."""

    dimensionality_check = quantity_with_dimensionality(dimensionality)

    def _validator(
        instance: object, attribute: "attrs.Attribute[pint.Quantity]", value: "pint.Quantity"
    ) -> None:
        dimensionality_check(instance, attribute, value)
        if value.magnitude < 0:
            raise ValueError(f"{attribute.name} must be non-negative, got {value!r}")

    return _validator


def unit_fraction(instance: object, attribute: "attrs.Attribute[float]", value: float) -> None:
    """A plain float that must fall within [0, 1] — a leak's location
    along a pipe's length (0 = inlet, 1 = outlet), for instance."""
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{attribute.name} must be between 0 and 1 inclusive, got {value!r}")
