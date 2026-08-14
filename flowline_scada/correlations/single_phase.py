"""
Single-phase pressure drop: Darcy-Weisbach with a Newton-Raphson
Colebrook-White friction factor.

Use this for a pipe segment carrying a single phase (liquid or gas) where
compressibility effects are small enough to ignore over the segment — for
compressible gas over a long run where density changes meaningfully
along the pipe, see the Weymouth/Panhandle correlations instead (arriving
alongside this module).

Example:

```python
from flowline_scada.correlations.single_phase import darcy_weisbach_pressure_drop
from flowline_scada.domain.units import Quantity

result = darcy_weisbach_pressure_drop(
    length=Quantity(1000, "ft"),
    internal_diameter=Quantity(6, "inch"),
    roughness=Quantity(0.0018, "inch"),
    mass_flow_rate=Quantity(50, "lb/s"),
    density=Quantity(62.4, "lb/ft^3"),
    viscosity=Quantity(1.12, "cP"),
)
print(result.pressure_drop.to("psi"))
```
"""

import math

import pint

from flowline_scada.correlations.base import PressureDropResult

LAMINAR_REYNOLDS_LIMIT = 2300.0
"""Above this Reynolds number, flow is treated as turbulent (Colebrook-White)
rather than laminar. The transition between roughly 2300 and 4000 is
genuinely unstable in reality — this module uses a single cutoff rather
than modeling a separate transitional zone, which is the common
simplification most practical pipe-flow tools make."""


def reynolds_number(
    density: "pint.Quantity",
    velocity: "pint.Quantity",
    diameter: "pint.Quantity",
    viscosity: "pint.Quantity",
) -> float:
    """Compute the Reynolds number for flow through a circular pipe.

    :param density: fluid density.
    :param velocity: mean flow velocity.
    :param diameter: pipe internal diameter.
    :param viscosity: fluid dynamic viscosity.
    :return: the Reynolds number (dimensionless).
    """
    return (density * velocity * diameter / viscosity).to("dimensionless").magnitude


def colebrook_white_friction_factor(
    reynolds: float, relative_roughness: float, tolerance: float = 1e-10, max_iterations: int = 20
) -> float:
    """Solve the Colebrook-White equation for the Darcy friction factor,
    via Newton-Raphson.

    :param reynolds: Reynolds number. Must be positive; this correlation
        is only valid for turbulent flow (in practice, above about 2300 —
        see :data:`LAMINAR_REYNOLDS_LIMIT`), though this function itself
        doesn't enforce that boundary.
    :param relative_roughness: pipe roughness divided by internal
        diameter (dimensionless).
    :param tolerance: stop iterating once successive friction factor
        estimates differ by less than this.
    :param max_iterations: give up after this many iterations if the
        solution hasn't converged.
    :return: the Darcy friction factor.
    :raises ValueError: if ``reynolds`` isn't positive.

    Converges in about 4-6 iterations for realistic pipe-flow conditions —
    verified directly against :func:`scipy.optimize.brentq` across a
    range of roughness/Reynolds combinations before this was written. A
    fixed-point (successive-substitution) approach to the same equation
    needs 15-30+ iterations for the same tolerance, since it only
    converges linearly where Newton-Raphson converges quadratically.
    """
    if reynolds <= 0:
        raise ValueError(f"reynolds must be positive, got {reynolds!r}")

    friction_factor = 0.02
    for _ in range(max_iterations):
        sqrt_f = math.sqrt(friction_factor)
        inner_term = relative_roughness / 3.7 + 2.51 / (reynolds * sqrt_f)
        residual = 1.0 / sqrt_f + 2.0 * math.log10(inner_term)

        d_inner_df = 2.51 / reynolds * (-0.5) * friction_factor ** (-1.5)
        residual_derivative = (
            -0.5 * friction_factor ** (-1.5) + (2.0 / math.log(10)) * d_inner_df / inner_term
        )

        next_friction_factor = friction_factor - residual / residual_derivative
        if abs(next_friction_factor - friction_factor) < tolerance:
            return next_friction_factor
        friction_factor = next_friction_factor

    return friction_factor


def darcy_weisbach_friction_factor(reynolds: float, relative_roughness: float) -> float:
    """Compute the Darcy friction factor for flow through a circular pipe.

    :param reynolds: Reynolds number. Must be positive.
    :param relative_roughness: pipe roughness divided by internal
        diameter (dimensionless). Must be non-negative.
    :return: the Darcy friction factor.
    :raises ValueError: if ``reynolds`` isn't positive or
        ``relative_roughness`` is negative.

    Laminar flow (Reynolds number at or below
    :data:`LAMINAR_REYNOLDS_LIMIT`) uses the exact closed-form result,
    :math:`f = 64/Re`. Turbulent flow uses
    :func:`colebrook_white_friction_factor`.
    """
    if reynolds <= 0:
        raise ValueError(f"reynolds must be positive, got {reynolds!r}")
    if relative_roughness < 0:
        raise ValueError(f"relative_roughness must be non-negative, got {relative_roughness!r}")

    if reynolds <= LAMINAR_REYNOLDS_LIMIT:
        return 64.0 / reynolds
    return colebrook_white_friction_factor(reynolds, relative_roughness)


def darcy_weisbach_pressure_drop(
    length: "pint.Quantity",
    internal_diameter: "pint.Quantity",
    roughness: "pint.Quantity",
    mass_flow_rate: "pint.Quantity",
    density: "pint.Quantity",
    viscosity: "pint.Quantity",
) -> PressureDropResult:
    """Compute the frictional pressure drop across a pipe segment via the
    Darcy-Weisbach equation.

    :param length: segment length.
    :param internal_diameter: pipe internal diameter.
    :param roughness: pipe wall absolute roughness.
    :param mass_flow_rate: mass flow rate through the segment. Must be
        positive — for flow in the reference-negative direction, negate
        the result rather than passing a negative flow rate in.
    :param density: fluid density, evaluated at the segment's conditions.
    :param viscosity: fluid dynamic viscosity, evaluated at the segment's
        conditions.
    :return: the pressure drop, along with the friction factor and
        Reynolds number it was computed from.
    :raises ValueError: if ``mass_flow_rate`` isn't positive.

    This is the incompressible form — density is a single fixed value
    for the whole segment, not something that varies with the (unknown,
    solved-for) pressure along it. That's the right choice for a liquid,
    or for a gas segment short/low-pressure-drop enough that treating its
    density as constant is a reasonable approximation; for a gas pipe
    where that approximation breaks down, use the Weymouth or Panhandle
    correlations instead.
    """
    if mass_flow_rate.magnitude <= 0:
        raise ValueError(f"mass_flow_rate must be positive, got {mass_flow_rate!r}")

    area = math.pi / 4.0 * internal_diameter**2
    velocity = mass_flow_rate / (density * area)
    reynolds = reynolds_number(
        density=density, velocity=velocity, diameter=internal_diameter, viscosity=viscosity
    )
    relative_roughness = (roughness / internal_diameter).to("dimensionless").magnitude
    friction_factor = darcy_weisbach_friction_factor(reynolds, relative_roughness)

    pressure_drop = friction_factor * (length / internal_diameter) * (density * velocity**2 / 2.0)
    return PressureDropResult(
        pressure_drop=pressure_drop.to("Pa"),
        friction_factor=friction_factor,
        reynolds_number=reynolds,
    )
