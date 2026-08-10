"""
Reusable validation helpers for building your own components.

These are the same building blocks
:mod:`flowline_scada.domain.components` uses internally for things like
"a pipe's length must be positive" — exposed here so you can use them if
you're defining your own component types with :mod:`attrs`, rather than
re-implementing the same checks.

Example:

```python
import attrs
from flowline_scada.domain.validators import positive_quantity

@attrs.define
class MyComponent:
    length: "pint.Quantity" = attrs.field(validator=positive_quantity("[length]"))
```
"""

import typing

import attrs
import pint


def quantity_with_dimensionality(
    dimensionality: str,
) -> typing.Callable[[object, "attrs.Attribute[pint.Quantity]", "pint.Quantity"], None]:
    """Build a validator requiring a value to be a
    :class:`pint.Quantity` with a specific dimensionality — the value's
    *kind* of unit, not the exact unit. ``"psi"`` and ``"Pa"`` are both
    ``"[pressure]"``, for instance, so either passes.

    :param dimensionality: a pint dimensionality string, e.g.
        ``"[length]"``, ``"[pressure]"``, ``"[length] ** 3 / [time]"``
        for a volumetric flow rate.
    :return: a validator function usable as ``attrs.field(validator=...)``.

    Example:

    ```python
    validator = quantity_with_dimensionality("[pressure]")
    # accepts Quantity(100, "psi") or Quantity(689476, "Pa")
    # rejects Quantity(10, "ft") — wrong kind of unit entirely
    ```
    """

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
    """Build a validator requiring a value to be a
    :class:`pint.Quantity` with the given dimensionality *and* strictly
    greater than zero — the right choice for something like a pipe
    length or diameter, where zero or negative isn't physically
    meaningful.

    :param dimensionality: a pint dimensionality string, e.g. ``"[length]"``.
    :return: a validator function usable as ``attrs.field(validator=...)``.
    """

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
    """Build a validator requiring a value to be a
    :class:`pint.Quantity` with the given dimensionality and zero or
    greater — the right choice for something like pipe roughness, where
    zero (a perfectly smooth pipe) is a valid, if idealized, value but a
    negative one never makes sense.

    :param dimensionality: a pint dimensionality string, e.g. ``"[length]"``.
    :return: a validator function usable as ``attrs.field(validator=...)``.
    """

    dimensionality_check = quantity_with_dimensionality(dimensionality)

    def _validator(
        instance: object, attribute: "attrs.Attribute[pint.Quantity]", value: "pint.Quantity"
    ) -> None:
        dimensionality_check(instance, attribute, value)
        if value.magnitude < 0:
            raise ValueError(f"{attribute.name} must be non-negative, got {value!r}")

    return _validator


def unit_fraction(instance: object, attribute: "attrs.Attribute[float]", value: float) -> None:
    """Validator requiring a plain ``float`` to fall within ``[0, 1]`` —
    the right choice for something like a leak's fractional position
    along a pipe (0 = inlet, 1 = outlet), used directly as a validator
    rather than a factory since it doesn't need any configuration.

    :param instance: the object being constructed (supplied automatically by attrs).
    :param attribute: the field being validated (supplied automatically by attrs).
    :param value: the value being validated.
    :raises ValueError: if ``value`` is outside ``[0, 1]``.
    """
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{attribute.name} must be between 0 and 1 inclusive, got {value!r}")
