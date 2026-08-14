"""
Shared building blocks used by every flow correlation in this package.

A "correlation" here means a specific published formula or method for
relating flow rate to pressure drop for some flow regime — Darcy-Weisbach
for single-phase flow, Beggs & Brill for two-phase flow, and so on. Each
one lives in its own module under this package
(:mod:`flowline_scada.correlations.single_phase`, and multiphase
correlations arriving after it) and can be called directly; this module
holds the handful of types shared across all of them.
"""

import attrs
import pint


@attrs.define(frozen=True, slots=True)
class PressureDropResult:
    """The result of a pressure-drop calculation across one pipe segment."""

    pressure_drop: "pint.Quantity"
    """The pressure lost across the segment, always non-negative — the
    direction of flow (and therefore which end is upstream) is the
    caller's concern, not this result's."""

    friction_factor: float
    """The Darcy friction factor used to compute this result. Present
    even for correlations (like Weymouth or Panhandle) that don't use it
    directly in their own formula, computed for reference/comparison."""

    reynolds_number: float
    """The Reynolds number the flow was evaluated at."""
