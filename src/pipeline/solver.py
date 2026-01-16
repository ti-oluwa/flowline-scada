"""
Pipeline Flow Solver
"""

import logging
import typing

import attrs
from cachetools import LRUCache
import numpy as np
from scipy.optimize import brentq
from pint.facets.plain import PlainQuantity

from src.flow import compute_pipe_pressure_drop
from src.pipeline.core import Pipe, PipeLeak, Pipeline
from src.types import FlowType
from src.units import Quantity

logger = logging.getLogger(__name__)  # type: ignore[attr-defined]


@attrs.define(slots=True, frozen=True)
class PipeSegment:
    """Represents a pipe segment between two points (potentially leak locations)"""

    start_position: float = attrs.field()
    """Fractional position along pipe (0 to 1)"""
    end_position: float = attrs.field()
    """Fractional position along pipe (0 to 1)"""
    length: PlainQuantity[float] = attrs.field()
    """Actual physical length of segment"""
    has_leak_at_end: bool = attrs.field()
    """Whether there's a leak at the end of this segment"""
    leak: typing.Optional[PipeLeak] = attrs.field(default=None)
    """The leak object if has_leak_at_end is True"""


@attrs.define(slots=True)
class FlowState:
    """Represents flow state at a point in the pipeline"""

    pressure: PlainQuantity[float] = attrs.field()
    """Pressure at this point"""
    temperature: PlainQuantity[float] = attrs.field()
    """Temperature at this point"""
    mass_flow_rate: PlainQuantity[float] = attrs.field()
    """Mass flow rate at this point"""
    position: float = attrs.field()
    """Fractional position along pipe (0 to 1)"""


@attrs.define(slots=True, frozen=True)
class CachedFluidProperties:
    """Cached fluid properties at a given state"""

    density: PlainQuantity[float] = attrs.field()
    """Fluid density"""
    viscosity: PlainQuantity[float] = attrs.field()
    """Dynamic viscosity"""
    compressibility_factor: float = attrs.field()
    """Compressibility factor (Z)"""
    specific_gravity: float = attrs.field()
    """Specific gravity relative to reference fluid"""
    temperature: PlainQuantity[float] = attrs.field()
    """Temperature at which properties are calculated"""


class FlowSolver:
    """
    Optimized pipeline flow solver using segment-based approach for leak modeling.

    This solver:
    1. Divides pipes with leaks into segments for proper physics modeling
    2. Caches expensive fluid property calculations
    3. Respects each pipe's individual flow equation
    4. Maintains proper pressure tracking across pipeline

    Cache clearing is required when:
    - Pipeline configuration changes (pipes added/removed)
    - Leak configuration changes (leaks added/removed/moved)
    - Pipe properties change (diameter, length, roughness, etc.)
    - Fluid properties change fundamentally (different fluid)

    Cache does NOT need clearing for:
    - Pressure changes (that's what we're solving for)
    - Temperature changes (handled by cache keys)
    - Flow rate changes (computed values, not cached)
    """

    def __init__(self, pipeline: Pipeline, cache_size: int = 128):
        """
        Initialize the flow solver.

        :param pipeline: Pipeline object to solve
        :param cache_size: Maximum number of cached entries for each cache type
        """
        self.pipeline = pipeline
        self.cache_size = cache_size
        self._fluid_property_cache: LRUCache = LRUCache(maxsize=cache_size)
        self._segment_cache: LRUCache = LRUCache(maxsize=cache_size)
        self._pipe_fluid_cache: LRUCache = LRUCache(maxsize=cache_size)

    def clear_cache(self):
        """
        Clear all solver caches.

        This should be called when:
        - Pipeline structure changes (add/remove pipes)
        - Leak configuration changes
        - Pipe physical properties change
        - Fluid type changes
        """
        self._fluid_property_cache.clear()
        self._segment_cache.clear()
        self._pipe_fluid_cache.clear()

    def get_fluid_properties(
        self, pressure: PlainQuantity[float], temperature: PlainQuantity[float]
    ) -> typing.Optional[CachedFluidProperties]:
        """
        Get cached fluid properties for given conditions.

        :param pressure: Pressure at which to get properties
        :param temperature: Temperature at which to get properties
        :return: CachedFluidProperties if available, None otherwise
        """
        fluid = self.pipeline.fluid
        if fluid is None:
            return None

        # Create cache key with reasonable precision (to Pa and 0.1K)
        pressure_pa = round(pressure.to("Pa").magnitude, 0)
        temp_k = round(temperature.to("K").magnitude, 1)
        cache_key = (fluid.name, pressure_pa, temp_k)

        if cache_key in self._fluid_property_cache:
            return self._fluid_property_cache[cache_key]

        # Cache miss. Compute and store
        try:
            fluid_at_state = fluid.for_pressure_temperature(
                pressure=pressure, temperature=temperature
            )
            cached_props = CachedFluidProperties(
                density=fluid_at_state.density,
                viscosity=fluid_at_state.viscosity,
                compressibility_factor=fluid_at_state.compressibility_factor,
                specific_gravity=fluid_at_state.specific_gravity,
                temperature=temperature,
            )
            self._fluid_property_cache[cache_key] = cached_props
            return cached_props

        except Exception as exc:
            logger.error(f"Failed to compute fluid properties: {exc}", exc_info=True)
            return None

    def segment_pipe_with_leaks(self, pipe: Pipe) -> typing.List[PipeSegment]:
        """
        Divide pipe into segments based on leak locations.

        Each segment between leaks can be treated as having constant mass flow rate,
        which is critical for proper physics modeling.

        :param pipe: Pipe object to segment
        :return: List of PipeSegment objects
        """
        # Check cache first - use pipe id and leak count as key
        leak_count = len(pipe._leaks) if pipe._leaks else 0
        cache_key = (id(pipe), leak_count)

        if cache_key in self._segment_cache:
            return self._segment_cache[cache_key]

        segments = []

        if not pipe._leaks or pipe._ignore_leaks:
            # Single segment for entire pipe
            segments = [
                PipeSegment(
                    start_position=0.0,
                    end_position=1.0,
                    length=pipe.length,
                    has_leak_at_end=False,
                    leak=None,
                )
            ]
        else:
            # Sort active leaks by position
            sorted_leaks = sorted(
                [(leak.location, leak) for leak in pipe._leaks if leak.active],
                key=lambda x: x[0],
            )

            if not sorted_leaks:
                # No active leaks - single segment
                segments = [
                    PipeSegment(
                        start_position=0.0,
                        end_position=1.0,
                        length=pipe.length,
                        has_leak_at_end=False,
                        leak=None,
                    )
                ]
            else:
                current_pos = 0.0
                pipe_length = pipe.length

                for leak_pos, leak in sorted_leaks:
                    # Create segment before leak (if there's distance)
                    if leak_pos > current_pos:
                        segment_length = (
                            leak_pos - current_pos
                        ) * pipe_length.magnitude
                        segments.append(
                            PipeSegment(
                                start_position=current_pos,
                                end_position=leak_pos,
                                length=Quantity(segment_length, pipe_length.units),
                                has_leak_at_end=True,
                                leak=leak,
                            )
                        )
                    current_pos = leak_pos

                # Final segment after last leak
                if current_pos < 1.0:
                    segment_length = (1.0 - current_pos) * pipe_length.magnitude
                    segments.append(
                        PipeSegment(
                            start_position=current_pos,
                            end_position=1.0,
                            length=Quantity(segment_length, pipe_length.units),
                            has_leak_at_end=False,
                            leak=None,
                        )
                    )

        # Cache the result
        self._segment_cache[cache_key] = segments
        return segments

    def compute_segment_pressure_drop(
        self, segment: PipeSegment, pipe: Pipe, inlet_state: FlowState
    ) -> typing.Tuple[PlainQuantity[float], PlainQuantity[float]]:
        """
        Compute pressure drop and outlet mass flow rate for a pipe segment.

        This respects the pipe's designated flow equation and properly handles
        segment-specific calculations.

        :param segment: PipeSegment to analyze
        :param pipe: Parent Pipe object
        :param inlet_state: Flow state at segment inlet
        :return: Tuple of (outlet_pressure, outlet_mass_flow_rate)
        """
        if pipe.fluid is None:
            logger.error(f"Pipe {pipe.name!r} has no fluid defined")
            return Quantity(0.0, "Pa"), Quantity(0.0, "kg/s")

        if inlet_state.mass_flow_rate.magnitude <= 0:
            # No flow - no pressure drop
            return inlet_state.pressure, Quantity(0.0, "kg/s")

        # Get cached fluid properties at inlet conditions
        fluid_props = self.get_fluid_properties(
            inlet_state.pressure, inlet_state.temperature
        )

        if fluid_props is None:
            logger.error(f"Could not get fluid properties for pipe {pipe.name!r}")
            return Quantity(0.0, "Pa"), Quantity(0.0, "kg/s")

        # Calculate volumetric flow rate from mass flow rate
        volumetric_flow = inlet_state.mass_flow_rate / fluid_props.density

        # Get pipe's designated flow equation
        flow_equation = pipe.flow_equation
        if flow_equation is None:
            logger.error(f"Pipe {pipe.name!r} has no flow equation determined")
            return Quantity(0.0, "Pa"), Quantity(0.0, "kg/s")

        # Compute pressure drop using the pipe's designated flow equation
        # Note: We scale the pipe properties to segment length
        try:
            # Create a "virtual" segment pressure by assuming the pressure drop
            # is proportional to segment length
            segment_fraction = segment.length.magnitude / pipe.length.magnitude

            # For this segment, assume downstream pressure is inlet minus some drop
            # We'll iterate if needed, but first approximation:
            # Calculate pressure drop for this segment using the proper equation
            segment_pressure_drop = compute_pipe_pressure_drop(
                upstream_pressure=inlet_state.pressure,
                flow_rate=volumetric_flow,
                length=segment.length,
                internal_diameter=pipe.internal_diameter,
                relative_roughness=pipe.relative_roughness,
                efficiency=pipe.efficiency,
                elevation_difference=pipe.elevation_difference * segment_fraction,
                specific_gravity=fluid_props.specific_gravity,
                temperature=inlet_state.temperature,
                compressibility_factor=fluid_props.compressibility_factor,
                density=fluid_props.density,
                viscosity=fluid_props.viscosity,
                flow_equation=flow_equation,
            )

            outlet_pressure = inlet_state.pressure - segment_pressure_drop
            outlet_pressure = Quantity(
                max(0.0, outlet_pressure.magnitude), outlet_pressure.units
            )

        except Exception as exc:
            logger.error(
                f"Pressure drop calculation failed for {pipe.name!r}: {exc}",
                exc_info=True,
            )
            return Quantity(0.0, "Pa"), Quantity(0.0, "kg/s")

        outlet_mass_flow = inlet_state.mass_flow_rate

        # Handle leak at segment end if present
        # CRITICAL: We compute the leak rate HERE using the outlet pressure
        # To avoid circular dependency we must not call `pipe.leak_rate` here
        if segment.has_leak_at_end and segment.leak and segment.leak.active:
            try:
                leak_rate_volumetric = segment.leak.compute_rate(
                    pipe_pressure=outlet_pressure,
                    ambient_pressure=pipe.ambient_pressure,
                    fluid_density=fluid_props.density,
                )

                leak_mass_rate = leak_rate_volumetric * fluid_props.density
                outlet_mass_flow = inlet_state.mass_flow_rate - leak_mass_rate

                # Ensure non-negative flow
                if outlet_mass_flow.magnitude < 0:
                    logger.warning(
                        f"Leak at position {segment.leak.location} in pipe {pipe.name!r} "
                        f"exceeds available flow. Setting outlet flow to zero."
                    )
                    outlet_mass_flow = Quantity(0.0, "kg/s")

            except Exception as exc:
                logger.error(
                    f"Leak calculation failed for {pipe.name!r}: {exc}", exc_info=True
                )
                # Continue without leak effect if calculation fails

        return outlet_pressure, outlet_mass_flow

    def compute_connector_pressure_drop(
        self,
        current_pipe: Pipe,
        next_pipe: Pipe,
        inlet_state: FlowState,
    ) -> PlainQuantity[float]:
        """
        Compute pressure drop across connector between two pipes.

        Handles both straight and elbow connectors, and tapered transitions.

        :param current_pipe: Upstream pipe
        :param next_pipe: Downstream pipe
        :param inlet_state: Flow state at connector inlet
        :return: Pressure drop across connector
        """
        from src.flow import compute_tapered_pipe_pressure_drop

        if inlet_state.mass_flow_rate.magnitude <= 0:
            return Quantity(0.0, "Pa")

        # Get fluid properties at connector inlet
        fluid_props = self.get_fluid_properties(
            inlet_state.pressure, inlet_state.temperature
        )

        if fluid_props is None:
            logger.error("Could not get fluid properties for connector")
            return Quantity(0.0, "Pa")

        # Calculate volumetric flow rate
        volumetric_flow = inlet_state.mass_flow_rate / fluid_props.density

        # Check if this is an elbow connection (direction change)
        is_elbow = current_pipe.direction != next_pipe.direction

        # Connector length - double for elbow connectors
        connector_length = self.pipeline.connector_length
        if is_elbow:
            connector_length = 2 * connector_length

        # Check diameter difference for tapered vs straight connector
        relative_diameter_diff = (
            abs(
                current_pipe.internal_diameter.to("m").magnitude
                - next_pipe.internal_diameter.to("m").magnitude
            )
            / current_pipe.internal_diameter.to("m").magnitude
        )

        if relative_diameter_diff < 0.02:
            # Straight connector (same diameter within 2%)
            # Use Darcy-Weisbach with average pipe properties

            avg_efficiency = (current_pipe.efficiency + next_pipe.efficiency) / 2
            connector_efficiency = avg_efficiency * 0.95 if is_elbow else avg_efficiency

            # Calculate elevation change proportionally
            if current_pipe.length.magnitude != 0:
                elevation_change_per_length = (
                    current_pipe.elevation_difference.to("m").magnitude
                    / current_pipe.length.to("m").magnitude
                )
            else:
                elevation_change_per_length = 0.0

            connector_elevation_diff = Quantity(
                elevation_change_per_length * connector_length.to("m").magnitude, "m"
            )

            # Use the current pipe's flow equation for connector
            flow_equation = current_pipe.flow_equation
            if flow_equation is None:
                from src.types import FlowEquation

                flow_equation = FlowEquation.DARCY_WEISBACH

            try:
                connector_pressure_drop = compute_pipe_pressure_drop(
                    upstream_pressure=inlet_state.pressure,
                    flow_rate=volumetric_flow,
                    length=connector_length,
                    internal_diameter=current_pipe.internal_diameter,
                    relative_roughness=0.0001,  # Assume smooth connector
                    efficiency=connector_efficiency,
                    elevation_difference=connector_elevation_diff,
                    specific_gravity=fluid_props.specific_gravity,
                    temperature=inlet_state.temperature,
                    compressibility_factor=fluid_props.compressibility_factor,
                    density=fluid_props.density,
                    viscosity=fluid_props.viscosity,
                    flow_equation=flow_equation,
                )
            except Exception as exc:
                logger.error(
                    f"Connector pressure drop calculation failed: {exc}", exc_info=True
                )
                connector_pressure_drop = Quantity(0.0, "Pa")

        else:
            # Tapered connector (significant diameter difference)
            try:
                connector_pressure_drop = compute_tapered_pipe_pressure_drop(
                    flow_rate=volumetric_flow,
                    pipe_inlet_diameter=current_pipe.internal_diameter,
                    pipe_outlet_diameter=next_pipe.internal_diameter,
                    pipe_length=connector_length,
                    fluid_density=fluid_props.density,
                    fluid_dynamic_viscosity=fluid_props.viscosity,
                    pipe_relative_roughness=0.000001,  # Very smooth connector
                    gradual_angle_threshold_deg=15.0,
                )
            except Exception as exc:
                logger.error(
                    f"Tapered connector pressure drop calculation failed: {exc}",
                    exc_info=True,
                )
                connector_pressure_drop = Quantity(0.0, "Pa")

        return connector_pressure_drop

    def solve_pipe_flow(
        self, pipe: Pipe, inlet_state: FlowState, set_values: bool = False
    ) -> FlowState:
        """
        Solve flow through a single pipe considering all segments.

        This maintains proper pressure tracking and respects each segment's physics.

        Valve logic:
        - Start valve closed: No flow enters pipe, returns zero flow state
        - End valve closed: Flow occurs in pipe but doesn't exit (outlet mass flow = 0)

        :param pipe: Pipe object to solve
        :param inlet_state: Flow state at pipe inlet
        :param set_values: Whether to set calculated values on the pipe object
        :return: Flow state at pipe outlet
        """
        # Check for closed START valve - no flow enters pipe at all
        if pipe._start_valve is not None and pipe._start_valve.is_closed():
            zero_state = FlowState(
                pressure=Quantity(0.0, "Pa"),
                temperature=inlet_state.temperature,
                mass_flow_rate=Quantity(0.0, "kg/s"),
                position=1.0,
            )
            if set_values:
                pipe.set_upstream_pressure(Quantity(0.0, "Pa"), check=False, sync=False)
                pipe.set_downstream_pressure(
                    Quantity(0.0, "Pa"), check=False, sync=False
                )
                pipe.set_flow_rate(Quantity(0.0, "ft^3/s"))
            return zero_state

        # Check if inlet flow is already zero (from upstream blockage)
        if inlet_state.mass_flow_rate.magnitude <= 0:
            zero_state = FlowState(
                pressure=Quantity(0.0, "Pa"),
                temperature=inlet_state.temperature,
                mass_flow_rate=Quantity(0.0, "kg/s"),
                position=1.0,
            )
            if set_values:
                pipe.set_upstream_pressure(Quantity(0.0, "Pa"), check=False, sync=False)
                pipe.set_downstream_pressure(
                    Quantity(0.0, "Pa"), check=False, sync=False
                )
                pipe.set_flow_rate(Quantity(0.0, "ft^3/s"))
            return zero_state

        # Flow CAN enter the pipe - solve normally
        segments = self.segment_pipe_with_leaks(pipe)
        current_state = inlet_state

        # Set pipe inlet conditions if requested
        if set_values:
            pipe.set_upstream_pressure(inlet_state.pressure, check=False, sync=False)
            pipe.set_upstream_temperature(inlet_state.temperature, sync=False)

        for segment in segments:
            outlet_pressure, outlet_mass_flow = self.compute_segment_pressure_drop(
                segment, pipe, current_state
            )

            # Update temperature for compressible flow (Joule-Thomson effect)
            outlet_temp = current_state.temperature
            if (
                pipe.fluid
                and pipe.fluid.phase == "gas"
                and pipe.flow_type == FlowType.COMPRESSIBLE
            ):
                try:
                    jt_coeff = pipe.fluid.get_joule_thomson_coefficient(
                        pressure=current_state.pressure,
                        temperature=current_state.temperature,
                    )
                    pressure_drop = current_state.pressure - outlet_pressure
                    outlet_temp = current_state.temperature.to("degF") + (
                        jt_coeff.to("degF/Pa") * pressure_drop.to("Pa")
                    )
                except Exception as exc:
                    logger.debug(f"JT coefficient calculation failed: {exc}")
                    outlet_temp = current_state.temperature

            current_state = FlowState(
                pressure=outlet_pressure,
                temperature=outlet_temp,
                mass_flow_rate=outlet_mass_flow,
                position=segment.end_position,
            )

            # Stop if pressure or flow drops to zero
            if outlet_pressure.magnitude <= 0 or outlet_mass_flow.magnitude <= 0:
                break

        # Set pipe outlet conditions and flow rate if requested
        if set_values:
            pipe.set_downstream_pressure(
                current_state.pressure, check=False, sync=False
            )

            # Convert mass flow to volumetric flow for pipe
            # Use INLET mass flow (what flows THROUGH the pipe), not outlet mass flow
            # This ensures correct display when end valve is closed (flow happens inside pipe)
            if pipe.fluid and inlet_state.mass_flow_rate.magnitude > 0:
                fluid_props = self.get_fluid_properties(
                    inlet_state.pressure, inlet_state.temperature
                )
                if fluid_props:
                    volumetric_flow = inlet_state.mass_flow_rate / fluid_props.density
                    pipe.set_flow_rate(volumetric_flow.to("ft^3/s"))
                else:
                    pipe.set_flow_rate(Quantity(0.0, "ft^3/s"))
            else:
                pipe.set_flow_rate(Quantity(0.0, "ft^3/s"))

        # Check for closed END valve - flow occurred IN pipe but doesn't EXIT
        if pipe._end_valve is not None and pipe._end_valve.is_closed():
            # Flow happened inside the pipe (flow_rate is set above)
            # But no mass flow exits to next pipe
            return FlowState(
                pressure=current_state.pressure,  # Pressure builds up at end
                temperature=current_state.temperature,
                mass_flow_rate=Quantity(0.0, "kg/s"),  # ZERO mass exits
                position=1.0,
            )
        return current_state

    def estimate_initial_mass_flow(self) -> PlainQuantity[float]:
        """
        Estimate initial mass flow rate for solver initialization.

        Uses Hagen-Poiseuille approximation for quick estimate.

        :return: Estimated mass flow rate
        """
        if not self.pipeline._pipes or self.pipeline.fluid is None:
            return Quantity(0.0, "kg/s")

        # Use equivalent single-pipe approximation
        total_length = sum(p.length.to("m").magnitude for p in self.pipeline._pipes)
        avg_diameter = np.mean(
            [p.internal_diameter.to("m").magnitude for p in self.pipeline._pipes]
        )

        # Pressure difference
        delta_p = self.pipeline.upstream_pressure - self.pipeline.downstream_pressure

        if delta_p.magnitude <= 0:
            return Quantity(0.0, "kg/s")

        # Get fluid properties at inlet conditions
        upstream_temperature = self.pipeline.upstream_temperature
        inlet_temperature = (
            upstream_temperature
            if upstream_temperature is not None
            else self.pipeline.fluid.temperature
        )
        fluid_props = self.get_fluid_properties(
            self.pipeline.upstream_pressure, inlet_temperature
        )
        if fluid_props is None:
            return Quantity(1.0, "kg/s")  # Fallback

        # Hagen-Poiseuille for initial guess
        q_approx = (np.pi * avg_diameter**4 * delta_p.to("Pa").magnitude) / (
            128 * fluid_props.viscosity.to("Pa*s").magnitude * total_length
        )
        mass_flow_approx = q_approx * fluid_props.density.to("kg/m^3").magnitude
        return Quantity(max(0.001, mass_flow_approx), "kg/s")

    def solve_pipeline(
        self, tolerance: float = 100.0, max_iterations: int = 30
    ) -> bool:
        """
        Solve the pipeline for flow distribution and pressures.

        Uses Brent's method for robust root finding with intelligent bracketing.

        :param tolerance: Pressure tolerance in Pa for convergence
        :param max_iterations: Maximum number of solver iterations
        :return: True if converged successfully, False otherwise
        """
        if not self.pipeline._pipes:
            logger.warning(f"Pipeline {self.pipeline.name!r} has no pipes")
            return False

        if self.pipeline.fluid is None:
            logger.warning(f"Pipeline {self.pipeline.name!r} has no fluid defined")
            return False

        # Check for valid pressures
        if self.pipeline.upstream_pressure.magnitude <= 0:
            logger.warning(
                f"Pipeline {self.pipeline.name!r} has non-positive upstream pressure"
            )
            for pipe in self.pipeline._pipes:
                pipe.set_flow_rate(Quantity(0.0, "ft^3/s"))
            return False

        if self.pipeline.downstream_pressure.magnitude <= 0:
            logger.warning(
                f"Pipeline {self.pipeline.name!r} has non-positive downstream pressure"
            )
            for pipe in self.pipeline._pipes:
                pipe.set_flow_rate(Quantity(0.0, "ft^3/s"))
            return False

        # Prepare inlet conditions used by solver
        inlet_pressure = self.pipeline.upstream_pressure
        upstream_temperature = self.pipeline.upstream_temperature
        inlet_temperature = (
            upstream_temperature
            if upstream_temperature is not None
            else self.pipeline.fluid.temperature
        )

        # Check for closed start valves in the pipeline
        # Find the first pipe with a closed start valve (if any)
        blocked_pipe_index = None
        for i, pipe in enumerate(self.pipeline._pipes):
            if pipe._start_valve is not None and pipe._start_valve.is_closed():
                blocked_pipe_index = i
                break

        # If first pipe is blocked, no flow anywhere
        if blocked_pipe_index == 0:
            logger.info(
                f"Pipeline {self.pipeline.name!r}: First pipe has closed start valve - setting all pipes to zero flow"
            )
            for pipe in self.pipeline._pipes:
                pipe.set_upstream_pressure(Quantity(0.0, "Pa"), check=False, sync=False)
                pipe.set_downstream_pressure(
                    Quantity(0.0, "Pa"), check=False, sync=False
                )
                pipe.set_flow_rate(Quantity(0.0, "ft^3/s"))
            return True

        # If a middle/later pipe is blocked, solve upstream section and zero downstream section
        if blocked_pipe_index is not None:
            logger.info(
                f"Pipeline {self.pipeline.name!r}: Pipe {blocked_pipe_index} "
                f"'{self.pipeline._pipes[blocked_pipe_index].name}' has closed start valve - "
                f"solving {blocked_pipe_index} upstream pipes, zeroing {len(self.pipeline._pipes) - blocked_pipe_index} downstream pipes"
            )

            # Zero out blocked pipe and all downstream pipes
            for j in range(blocked_pipe_index, len(self.pipeline._pipes)):
                blocked_pipe = self.pipeline._pipes[j]
                blocked_pipe.set_upstream_pressure(
                    Quantity(0.0, "Pa"), check=False, sync=False
                )
                blocked_pipe.set_downstream_pressure(
                    Quantity(0.0, "Pa"), check=False, sync=False
                )
                blocked_pipe.set_flow_rate(Quantity(0.0, "ft^3/s"))

            # Solve only the upstream pipes (0 to blocked_pipe_index - 1)
            # Use atmospheric pressure as the "downstream" pressure for the last upstream pipe
            upstream_pipes = self.pipeline._pipes[:blocked_pipe_index]
            target_outlet_p = (
                Quantity(14.7, "psi").to("Pa").magnitude
            )  # Atmospheric pressure

            def upstream_objective(mass_flow_rate_kg_s: float) -> float:
                """Objective function for upstream section only."""
                if mass_flow_rate_kg_s <= 0:
                    return inlet_pressure.to("Pa").magnitude - target_outlet_p

                current_state = FlowState(
                    pressure=inlet_pressure,
                    temperature=inlet_temperature,
                    mass_flow_rate=Quantity(mass_flow_rate_kg_s, "kg/s"),
                    position=0.0,
                )

                for i, pipe in enumerate(upstream_pipes):
                    current_state = self.solve_pipe_flow(
                        pipe, current_state, set_values=False
                    )

                    if current_state.mass_flow_rate.magnitude <= 0:
                        return (
                            current_state.pressure.to("Pa").magnitude - target_outlet_p
                        )

                    if current_state.pressure.magnitude <= 0:
                        return -target_outlet_p

                    # Add connector if not last upstream pipe
                    if i < len(upstream_pipes) - 1:
                        next_pipe = upstream_pipes[i + 1]
                        connector_drop = self.compute_connector_pressure_drop(
                            pipe, next_pipe, current_state
                        )
                        new_pressure = current_state.pressure - connector_drop
                        new_pressure = Quantity(
                            max(0.0, new_pressure.magnitude), new_pressure.units
                        )
                        current_state = FlowState(
                            pressure=new_pressure,
                            temperature=current_state.temperature,
                            mass_flow_rate=current_state.mass_flow_rate,
                            position=0.0,
                        )

                return current_state.pressure.to("Pa").magnitude - target_outlet_p

            # Solve for upstream section
            initial_guess = self.estimate_initial_mass_flow()
            lower_bound = 0.001
            upper_bound = max(initial_guess.magnitude * 10, 10.0)

            bracket_found = False
            for attempt in range(6):
                try:
                    f_lower = upstream_objective(lower_bound)
                    f_upper = upstream_objective(upper_bound)

                    if f_lower * f_upper < 0:
                        bracket_found = True
                        break

                    if f_lower > 0 and f_upper > 0:
                        lower_bound = upper_bound
                        upper_bound *= 5
                    elif f_lower < 0 and f_upper < 0:
                        upper_bound = lower_bound
                        lower_bound = max(0.001, lower_bound / 5)
                    else:
                        if abs(f_lower) < 10:
                            lower_bound *= 0.9
                        if abs(f_upper) < 10:
                            upper_bound *= 1.1
                except Exception:
                    break

            if not bracket_found:
                logger.warning(
                    f"Could not establish bracket for upstream section of {self.pipeline.name!r}"
                )
                return False

            try:
                solution = brentq(
                    upstream_objective,
                    lower_bound,
                    upper_bound,
                    xtol=tolerance / inlet_pressure.to("Pa").magnitude,
                    maxiter=max_iterations,
                )

                # Apply solution to upstream pipes
                current_state = FlowState(
                    pressure=inlet_pressure,
                    temperature=inlet_temperature,
                    mass_flow_rate=Quantity(solution, "kg/s"),
                    position=0.0,
                )

                for i, pipe in enumerate(upstream_pipes):
                    current_state = self.solve_pipe_flow(
                        pipe, current_state, set_values=True
                    )

                    if i < len(upstream_pipes) - 1:
                        next_pipe = upstream_pipes[i + 1]
                        connector_drop = self.compute_connector_pressure_drop(
                            pipe, next_pipe, current_state
                        )
                        new_pressure = current_state.pressure - connector_drop
                        new_pressure = Quantity(
                            max(0.0, new_pressure.magnitude), new_pressure.units
                        )
                        current_state = FlowState(
                            pressure=new_pressure,
                            temperature=current_state.temperature,
                            mass_flow_rate=current_state.mass_flow_rate,
                            position=0.0,
                        )

                logger.info(
                    f"Pipeline {self.pipeline.name!r} upstream section converged: "
                    f"mass_flow={solution:.6f} kg/s"
                )
                return True
            except Exception as exc:
                logger.error(
                    f"Solver failed for upstream section: {exc}", exc_info=True
                )
                return False

        # No blocked pipes - solve normally
        target_outlet_p = self.pipeline.downstream_pressure.to("Pa").magnitude
        inlet_pressure = self.pipeline.upstream_pressure
        upstream_temperature = self.pipeline.upstream_temperature
        inlet_temperature = (
            upstream_temperature
            if upstream_temperature is not None
            else self.pipeline.fluid.temperature
        )

        def objective(mass_flow_rate_kg_s: float) -> float:
            """
            Objective function: error between calculated and target outlet pressure.

            :param mass_flow_rate_kg_s: Trial mass flow rate in kg/s
            :return: Pressure error in Pa (positive if too high, negative if too low)
            """
            if mass_flow_rate_kg_s <= 0:
                return inlet_pressure.to("Pa").magnitude - target_outlet_p

            current_state = FlowState(
                pressure=inlet_pressure,
                temperature=inlet_temperature,
                mass_flow_rate=Quantity(mass_flow_rate_kg_s, "kg/s"),
                position=0.0,
            )

            # Solve through all pipes AND connectors
            num_pipes = len(self.pipeline._pipes)
            for i, pipe in enumerate(self.pipeline._pipes):
                # Solve flow through this pipe
                # The pipe itself will handle its start valve (blocks entry)
                # and end valve (blocks exit but allows internal flow)
                current_state = self.solve_pipe_flow(
                    pipe, current_state, set_values=False
                )

                # If current_state has zero mass flow, all downstream pipes get zero
                if current_state.mass_flow_rate.magnitude <= 0:
                    # This means either:
                    # 1. Start valve of this pipe was closed, OR
                    # 2. End valve of previous pipe was closed, OR
                    # 3. End valve of this pipe was closed
                    # In all cases, no flow continues downstream
                    return current_state.pressure.to("Pa").magnitude - target_outlet_p

                if current_state.pressure.magnitude <= 0:
                    return -target_outlet_p

                # Add connector pressure drop if not the last pipe
                if i < num_pipes - 1:
                    next_pipe = self.pipeline._pipes[i + 1]

                    # Calculate connector pressure drop
                    connector_pressure_drop = self.compute_connector_pressure_drop(
                        pipe, next_pipe, current_state
                    )

                    # Update state after connector
                    new_pressure = current_state.pressure - connector_pressure_drop
                    new_pressure = Quantity(
                        max(0.0, new_pressure.magnitude), new_pressure.units
                    )

                    # Update temperature through connector (JT effect for gases)
                    new_temp = current_state.temperature
                    if (
                        pipe.fluid
                        and pipe.fluid.phase == "gas"
                        and pipe.flow_type == FlowType.COMPRESSIBLE
                    ):
                        try:
                            jt_coeff = pipe.fluid.get_joule_thomson_coefficient(
                                pressure=current_state.pressure,
                                temperature=current_state.temperature,
                            )
                            new_temp = current_state.temperature.to("degF") + (
                                jt_coeff.to("degF/Pa")
                                * connector_pressure_drop.to("Pa")
                            )
                        except Exception as exc:
                            logger.debug(
                                f"JT coefficient calculation failed: {exc}",
                                exc_info=True,
                            )

                    new_temp = typing.cast(PlainQuantity[float], new_temp)
                    current_state = FlowState(
                        pressure=new_pressure,
                        temperature=new_temp,
                        mass_flow_rate=current_state.mass_flow_rate,  # Carries through
                        position=0.0,  # Reset position for next pipe
                    )
                    if new_pressure.magnitude <= 0:
                        return -target_outlet_p

            return current_state.pressure.to("Pa").magnitude - target_outlet_p

        # Get intelligent initial guess
        initial_guess = self.estimate_initial_mass_flow()

        # Establish bracketing interval
        lower_bound = 0.001
        upper_bound = max(initial_guess.magnitude * 10, 10.0)

        # Find bracket with opposite signs
        bracket_found = False
        for attempt in range(6):
            try:
                f_lower = objective(lower_bound)
                f_upper = objective(upper_bound)

                if f_lower * f_upper < 0:  # Sign change found ( -ve * +ve = -ve )
                    bracket_found = True
                    break

                if f_lower > 0 and f_upper > 0:
                    lower_bound = upper_bound
                    upper_bound *= 5
                elif f_lower < 0 and f_upper < 0:
                    upper_bound = lower_bound
                    lower_bound = max(0.001, lower_bound / 5)
                else:
                    if abs(f_lower) < 10:
                        lower_bound *= 0.9
                    if abs(f_upper) < 10:
                        upper_bound *= 1.1

            except Exception as exc:
                logger.error(f"Error during bracket search: {exc}")
                break

        if not bracket_found:
            logger.warning(
                f"Could not establish bracket for pipeline {self.pipeline.name!r}. "
                f"Tried range [{lower_bound:.6f}, {upper_bound:.6f}] kg/s"
            )
            return False

        try:
            # Solve using Brent's method
            solution = brentq(
                objective,
                lower_bound,
                upper_bound,
                xtol=tolerance / inlet_pressure.to("Pa").magnitude,
                maxiter=max_iterations,
            )

            # Apply solution to all pipes (final pass with set_values=True)
            current_state = FlowState(
                pressure=inlet_pressure,
                temperature=inlet_temperature,
                mass_flow_rate=Quantity(solution, "kg/s"),
                position=0.0,
            )

            num_pipes = len(self.pipeline._pipes)
            for i, pipe in enumerate(self.pipeline._pipes):
                # Solve this pipe with set_values=True
                current_state = self.solve_pipe_flow(
                    pipe, current_state, set_values=True
                )

                # If no flow exits this pipe, all downstream pipes get zero
                if current_state.mass_flow_rate.magnitude <= 0:
                    logger.info(
                        f"Pipeline {self.pipeline.name!r}: Pipe {i} '{pipe.name}' has zero outlet flow - "
                        f"setting {num_pipes - i - 1} downstream pipes to zero"
                    )
                    # Set all remaining downstream pipes to zero
                    for j in range(i + 1, num_pipes):
                        downstream_pipe = self.pipeline._pipes[j]
                        downstream_pipe.set_upstream_pressure(
                            Quantity(0.0, "Pa"), check=False, sync=False
                        )
                        downstream_pipe.set_downstream_pressure(
                            Quantity(0.0, "Pa"), check=False, sync=False
                        )
                        downstream_pipe.set_flow_rate(Quantity(0.0, "ft^3/s"))
                        logger.debug(
                            f"  Set pipe {j} '{downstream_pipe.name}' to zero flow"
                        )
                    break

                # Apply connector effects if not last pipe
                if i < num_pipes - 1:
                    next_pipe = self.pipeline._pipes[i + 1]
                    connector_pressure_drop = self.compute_connector_pressure_drop(
                        pipe, next_pipe, current_state
                    )

                    new_pressure = current_state.pressure - connector_pressure_drop
                    new_pressure = Quantity(
                        max(0.0, new_pressure.magnitude), new_pressure.units
                    )

                    new_temp = current_state.temperature
                    if (
                        pipe.fluid
                        and pipe.fluid.phase == "gas"
                        and pipe.flow_type == FlowType.COMPRESSIBLE
                    ):
                        try:
                            jt_coeff = pipe.fluid.get_joule_thomson_coefficient(
                                pressure=current_state.pressure,
                                temperature=current_state.temperature,
                            )
                            new_temp = current_state.temperature.to("degF") + (
                                jt_coeff.to("degF/Pa")
                                * connector_pressure_drop.to("Pa")
                            )
                        except Exception as exc:
                            logger.debug(
                                f"JT coefficient calculation failed: {exc}",
                                exc_info=True,
                            )
                    new_temp = typing.cast(PlainQuantity[float], new_temp)
                    current_state = FlowState(
                        pressure=new_pressure,
                        temperature=new_temp,
                        mass_flow_rate=current_state.mass_flow_rate,
                        position=0.0,
                    )

            logger.info(
                f"Pipeline {self.pipeline.name!r} converged: "
                f"mass_flow={solution:.6f} kg/s, "
                f"outlet_pressure={current_state.pressure.to('psi'):.4f}"
            )
            return True

        except ValueError as exc:
            logger.error(
                f"Solver failed for pipeline {self.pipeline.name!r}: {exc}",
                exc_info=True,
            )
            return False
        except Exception as exc:
            logger.error(
                f"Unexpected error in solver for pipeline {self.pipeline.name!r}: {exc}",
                exc_info=True,
            )
            return False

    def estimate_pressure_at_location(
        self, pipe: Pipe, location: float
    ) -> PlainQuantity[float]:
        """
        Estimate pressure at a specific fractional location along a pipe.

        This properly accounts for:
        - Segment-based pressure drops
        - Leak effects on local pressure
        - Non-linear pressure profiles

        :param pipe: Pipe object to analyze
        :param location: Fractional position along pipe (0.0 to 1.0)
        :return: Estimated pressure at the specified location
        :raises ValueError: If location is outside valid range
        """
        if not (0.0 <= location <= 1.0):
            raise ValueError(f"Location must be between 0.0 and 1.0, got {location}")

        # Handle boundary cases
        if location == 0.0:
            return pipe.upstream_pressure
        if location == 1.0:
            return pipe.downstream_pressure

        # Check if pipe has been solved (has flow rate set)
        if pipe._flow_rate.magnitude == 0:
            logger.debug(
                f"Attempting to estimate pressure before pipe {pipe.name!r} has been solved. "
                f"Call `pipeline.sync()` first. Using linear interpolation as fallback."
            )
            # No flow - assume linear pressure gradient
            pressure_drop = pipe.upstream_pressure - pipe.downstream_pressure
            return pipe.upstream_pressure - (location * pressure_drop)

        # Get segments for this pipe
        segments = self.segment_pipe_with_leaks(pipe)

        # Find which segment contains the target location
        inlet_pressureressure = pipe.upstream_pressure
        fluid = pipe.fluid
        if fluid is None:
            logger.error(f"Pipe {pipe.name!r} has no fluid defined")
            return Quantity(0.0, "Pa")

        upstream_temperature = pipe.upstream_temperature
        inlet_temperature = (
            upstream_temperature
            if upstream_temperature is not None
            else (fluid.temperature or Quantity(298.15, "K"))
        )
        mass_flow = pipe._flow_rate.to("ft^3/s") * fluid.density.to("lb/ft^3")

        current_state = FlowState(
            pressure=inlet_pressureressure,
            temperature=inlet_temperature,
            mass_flow_rate=mass_flow,
            position=0.0,
        )

        for segment in segments:
            # Check if target location is in this segment
            if location <= segment.end_position:
                # Target is in this segment
                if location == segment.start_position:
                    return current_state.pressure

                # Interpolate within segment
                segment_fraction = (location - segment.start_position) / (
                    segment.end_position - segment.start_position
                )

                # Calculate outlet state for this segment
                outlet_pressure, outlet_mass_flow = self.compute_segment_pressure_drop(
                    segment, pipe, current_state
                )

                # Linear interpolation within segment
                # (This is accurate for constant flow rate segments)
                pressure_drop_in_segment = current_state.pressure - outlet_pressure
                interpolated_pressure = current_state.pressure - (
                    segment_fraction * pressure_drop_in_segment
                )

                return Quantity(
                    max(0.0, interpolated_pressure.magnitude),
                    interpolated_pressure.units,
                )

            # Target is beyond this segment - compute full segment and continue
            outlet_pressure, outlet_mass_flow = self.compute_segment_pressure_drop(
                segment, pipe, current_state
            )
            # Update state for next segment
            outlet_temp = current_state.temperature
            if (
                pipe.fluid
                and pipe.fluid.phase == "gas"
                and pipe.flow_type == FlowType.COMPRESSIBLE
            ):
                try:
                    jt_coeff = pipe.fluid.get_joule_thomson_coefficient(
                        pressure=current_state.pressure,
                        temperature=current_state.temperature,
                    )
                    pressure_drop = current_state.pressure - outlet_pressure
                    outlet_temp = current_state.temperature.to("degF") + (
                        jt_coeff.to("degF/Pa") * pressure_drop.to("Pa")
                    )
                except Exception as exc:
                    logger.debug(
                        f"JT coefficient calculation failed: {exc}", exc_info=True
                    )
                    pass  # Keep temperature constant if JT calculation fails

            current_state = FlowState(
                pressure=outlet_pressure,
                temperature=outlet_temp,
                mass_flow_rate=outlet_mass_flow,
                position=segment.end_position,
            )

        # If we get here, return the final state pressure
        return current_state.pressure
