"""
Modular piping components for SVG-based pipeline visualization.

This module provides a clean, component-based approach to building pipeline visualizations
with proper connection interfaces and decoupled SVG generation.
"""

import typing
import copy
import attrs
import math
from pint.facets.plain import PlainQuantity

from src.units import Quantity
from src.types import PipeDirection

__all__ = [
    "ConnectionPoint",
    "SVGComponent",
    "PipeComponent",
    "LeakInfo",
    "HorizontalPipe",
    "VerticalPipe",
    "ValveComponent",
    "StraightConnector",
    "Pipeline",
    "build_valve",
    "build_horizontal_pipe",
    "build_vertical_pipe",
    "build_straight_connector",
    "build_elbow_connector",
]


@attrs.define(slots=True)
class ConnectionPoint:
    """Connection point information for joining components."""

    x: float
    """X coordinate of the connection point in SVG units."""
    y: float
    """Y coordinate of the connection point in SVG units."""
    direction: PipeDirection
    """Direction of flow at this connection point."""
    diameter: float
    """Diameter of the pipe at this connection point in pixels."""
    flow_rate: PlainQuantity[float] = attrs.field(
        factory=lambda: Quantity(0.0, "ft^3/s")
    )
    """Flow rate through this connection point."""


@attrs.define(slots=True)
class SVGComponent:
    """Container for SVG content and connection information."""

    main_svg: str
    """Complete standalone SVG with outer tags and all definitions."""
    inner_content: str
    """SVG content without outer <svg> tag for embedding in larger compositions."""
    width: float
    """Width of the SVG component in pixels."""
    height: float
    """Height of the SVG component in pixels."""
    inlet: ConnectionPoint
    """Inlet connection point for this component."""
    outlet: ConnectionPoint
    """Outlet connection point for this component."""
    viewbox: str
    """SVG viewBox attribute string defining the coordinate system."""


@attrs.define(slots=True)
class LeakInfo:
    """Visual representation of a pipe leak for SVG rendering."""

    location: float
    """Position along pipe length as fraction (0.0 to 1.0)."""
    severity: str
    """Qualitative severity: 'pinhole', 'small', 'moderate', 'large', 'critical'."""

    def get_visual_size(self, pipe_diameter_pixels: float) -> float:
        """Calculate visual size of leak indicator based on severity and pipe size."""
        # Base size as fraction of pipe diameter
        size_map = {
            "pinhole": 0.15,
            "small": 0.25,
            "moderate": 0.4,
            "large": 0.6,
            "critical": 0.8,
        }
        base_fraction = size_map.get(self.severity, 0.3)
        return max(3, pipe_diameter_pixels * base_fraction)

    def get_leak_color(self) -> str:
        """Get color based on leak severity."""
        color_map = {
            "pinhole": "#fbbf24",  # Yellow
            "small": "#f59e0b",  # Orange
            "moderate": "#dc2626",  # Red
            "large": "#991b1b",  # Dark red
            "critical": "#7f1d1d",  # Very dark red
        }
        return color_map.get(self.severity, "#dc2626")

    def get_spray_count(self) -> int:
        """Get number of spray particles based on severity."""
        severity_spray_map = {
            "pinhole": 4,
            "small": 6,
            "moderate": 8,
            "large": 12,
            "critical": 16,
        }
        return severity_spray_map.get(self.severity, 6)


@typing.runtime_checkable
class PipeComponent(typing.Protocol):
    """Protocol for pipe components with SVG representation and connection interface."""

    scale_factor: typing.Optional[float]

    def get_svg_component(self) -> SVGComponent:
        """Get the SVG component representation."""
        ...

    def connect(self, other: "PipeComponent") -> "Pipeline":
        """Connect this component to another component."""
        ...


def calculate_flow_intensity(
    flow_rate: PlainQuantity[float],
    max_flow_rate: PlainQuantity[float] = Quantity(10.0, "ft^3/s"),
) -> float:
    """
    Calculate flow intensity normalized to 0-1 range.

    Converts absolute flow rate to a normalized intensity value for
    visual representation (colors, animation speed, etc.).

    :param flow_rate: Current flow rate in volumetric units.
    :param max_flow_rate: Maximum expected flow rate for normalization.
    :return: Normalized intensity between 0.0 and 1.0.
    """
    flow_magnitude = flow_rate.to("ft^3/s").magnitude
    max_flow_magnitude = max_flow_rate.to("ft^3/s").magnitude
    return min(flow_magnitude / max_flow_magnitude, 1.0)


def get_flow_color(intensity: float) -> str:
    """
    Get color based on flow intensity.

    Maps flow intensity to appropriate colors for visual representation:
    - Gray: No flow (intensity ≤ 0)
    - Blue: Low flow (intensity < 0.2)
    - Green: Normal flow (intensity < 0.5)
    - Orange: High flow (intensity < 0.8)
    - Red: Very high flow (intensity ≥ 0.8)

    :param intensity: Normalized flow intensity (0.0 to 1.0).
    :return: Hex color code for the given intensity.
    """
    if intensity <= 0:
        return "#9ca3af"  # Gray for no flow
    elif intensity < 0.2:
        return "#3b82f6"  # Blue for low flow
    elif intensity < 0.5:
        return "#10b981"  # Green for normal flow
    elif intensity < 0.8:
        return "#f59e0b"  # Orange for high flow
    return "#ef4444"  # Red for very high flow


def physical_to_display_unit(
    physical: PlainQuantity[float],
    scale_factor: float = 1.0,
    min_display_unit: typing.Optional[float] = None,
    max_display_unit: typing.Optional[float] = None,
) -> float:
    """
    Convert physical quantity to display pixels.

    Converts real-world measurements to SVG pixel units with optional
    bounds clamping for reasonable visual representation.

    :param physical: Physical measurement with units (e.g., mm, inches, meters).
    :param scale_factor: Scaling factor for conversion to pixels.
    :param min_display_unit: Minimum pixel value (clamps small values).
    :param max_display_unit: Maximum pixel value (clamps large values).
    :return: Display value in pixels.
    """
    # Convert to mm first, then apply scale
    display_value = physical.to("mm").magnitude * scale_factor
    if min_display_unit is not None:
        display_value = max(display_value, min_display_unit)
    if max_display_unit is not None:
        display_value = min(display_value, max_display_unit)
    return display_value


@attrs.define(slots=True)
class HorizontalPipe(PipeComponent):
    """Horizontal pipe component."""

    direction: PipeDirection
    """Flow direction: must be EAST or WEST."""
    internal_diameter: PlainQuantity[float]
    """Internal diameter of the pipe (e.g., mm, inches)."""
    length: PlainQuantity[float]
    """Physical length of the pipe (e.g., m, ft)."""
    flow_rate: PlainQuantity[float] = attrs.field(
        factory=lambda: Quantity(0.0, "ft^3/s")
    )
    """Current flow rate through the pipe."""
    max_flow_rate: PlainQuantity[float] = attrs.field(
        factory=lambda: Quantity(10.0, "ft^3/s")
    )
    """Maximum expected flow rate for intensity scaling."""
    scale_factor: typing.Optional[float] = 1.0
    """Scaling factor for converting physical dimensions to display pixels."""
    canvas_width: float = 400.0
    """Width of the SVG canvas for this pipe."""
    canvas_height: float = 100.0
    """Height of the SVG canvas for this pipe."""
    leaks: typing.List[LeakInfo] = attrs.field(factory=list)
    """List of leaks in this pipe."""

    def __attrs_post_init__(self):
        """Validate direction after initialization."""
        if self.direction not in [PipeDirection.EAST, PipeDirection.WEST]:
            raise ValueError(
                f"HorizontalPipe direction must be EAST or WEST, got {self.direction}"
            )

    def get_svg_component(self) -> SVGComponent:
        """
        Generate SVG component for horizontal pipe.

        Creates a complete SVG representation including:
        - Pipe body with flow-based coloring
        - Inlet and outlet flanges
        - Connection points for joining with other components
        - Flow direction indicators and animations
        - Flow particles based on current flow rate

        :return: Complete SVG representation with connection information.
        """
        # Calculate pipe dimensions
        pipe_diameter_pixels = physical_to_display_unit(
            self.internal_diameter,
            self.scale_factor or 1.0,
            min_display_unit=8,
            max_display_unit=60,
        )

        pipe_length_pixels = physical_to_display_unit(
            self.length,
            self.scale_factor or 1.0,
            min_display_unit=200,
            max_display_unit=320,
        )

        # Calculate positioning
        pipe_y = (self.canvas_height - pipe_diameter_pixels) / 2
        pipe_x_start = (self.canvas_width - pipe_length_pixels) / 2
        pipe_x_end = pipe_x_start + pipe_length_pixels

        # Flow calculations
        intensity = calculate_flow_intensity(self.flow_rate, self.max_flow_rate)
        color = get_flow_color(intensity)

        # Flow direction setup
        if self.direction == PipeDirection.EAST:
            flow_start_x, flow_end_x = pipe_x_start + 20, pipe_x_end - 20
            arrow = "▶"
            inlet_x, outlet_x = pipe_x_start, pipe_x_end
        else:  # WEST
            flow_start_x, flow_end_x = pipe_x_end - 20, pipe_x_start + 20
            arrow = "◀"
            inlet_x, outlet_x = pipe_x_end, pipe_x_start

        center_y = self.canvas_height / 2

        # Generate flow particles
        particles = ""
        if intensity > 0:
            particle_count = max(3, int(intensity * 8))
            animation_duration = max(0.8, 3.0 - intensity * 2.0)

            for i in range(particle_count):
                delay = i * (animation_duration / particle_count)
                particles += f'''
                <circle r="2" fill="{color}" opacity="0">
                    <animate attributeName="cx" 
                             values="{flow_start_x};{flow_end_x}" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                    <animate attributeName="cy" 
                             values="{center_y};{center_y}" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                    <animate attributeName="opacity" 
                             values="0;0.8;0.8;0" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                </circle>
                '''

        # Generate flow direction indicators
        direction_indicators = ""
        if intensity > 0:
            arrow_count = 4
            for i in range(arrow_count):
                x_pos = (
                    pipe_x_start
                    + 40
                    + (i * (pipe_length_pixels - 80) / (arrow_count - 1))
                )
                direction_indicators += f'''
                <text x="{x_pos}" y="{center_y - pipe_diameter_pixels / 2 - 8}" 
                      text-anchor="middle" font-size="12" fill="{color}" opacity="0.7">
                    <animate attributeName="opacity" 
                             values="0.3;1;0.3" 
                             dur="2s" 
                             repeatCount="indefinite" 
                             begin="{i * 0.3}s"/>
                    {arrow}
                </text>
                '''

        # Flange dimensions
        flange_width = 8
        flange_height = pipe_diameter_pixels + 8

        # Generate leak visualization
        leak_visuals = ""
        for leak in self.leaks:
            # Calculate leak position along pipe
            if self.direction == PipeDirection.EAST:
                leak_x = pipe_x_start + (leak.location * pipe_length_pixels)
            else:
                leak_x = pipe_x_start + ((1 - leak.location) * pipe_length_pixels)
            leak_size = leak.get_visual_size(pipe_diameter_pixels)
            leak_color = leak.get_leak_color()

            # Create leak indicator (crack/hole)
            leak_visuals += f'''
            <!-- LeakInfo indicator at {leak.location:.1%} -->
            <g class="leak-indicator" data-severity="{leak.severity}">
                <!-- Main leak hole -->
                <ellipse cx="{leak_x}" cy="{center_y}" 
                         rx="{leak_size / 2}" ry="{leak_size / 3}" 
                         fill="{leak_color}" stroke="#000000" stroke-width="1" 
                         opacity="0.8">
                    <animate attributeName="opacity" 
                             values="0.6;1;0.6" 
                             dur="1.5s" 
                             repeatCount="indefinite"/>
                </ellipse>
                
                <!-- LeakInfo spray particles -->
                <g class="leak-spray">
            '''

            # Generate spray particles for active leaks
            spray_count = leak.get_spray_count()
            for i in range(spray_count):
                # Spray particles emanating from leak
                angle = -45 + (
                    i * 90 / max(1, spray_count - 1)
                )  # Spray downward and sideways
                spray_distance = leak_size * (1.5 + i * 0.3)
                spray_x = leak_x + spray_distance * math.cos(math.radians(angle)) * 0.3
                spray_y = (
                    center_y + spray_distance * math.sin(math.radians(angle)) * 0.3
                )

                leak_visuals += f'''
                <circle cx="{spray_x}" cy="{spray_y}" r="1" 
                        fill="{leak_color}" opacity="0.4">
                    <animate attributeName="opacity" 
                                values="0;0.7;0" 
                                dur="{1 + i * 0.2}s" 
                                repeatCount="indefinite" 
                                begin="{i * 0.1}s"/>
                    <animateTransform attributeName="transform" 
                                        type="translate" 
                                        values="0,0; 0,{spray_distance / 3}" 
                                        dur="{1 + i * 0.2}s" 
                                        repeatCount="indefinite" 
                                        begin="{i * 0.1}s"/>
                </circle>
                '''

            leak_visuals += """
                </g>
                
                <!-- LeakInfo severity indicator -->
                <text x="{}" y="{}" text-anchor="middle" 
                      font-size="8" fill="{}" font-weight="bold" opacity="0.8">
                    {}
                </text>
            </g>
            """.format(
                leak_x,
                center_y - pipe_diameter_pixels / 2 - 10,
                leak_color,
                leak.severity[0].upper(),  # First letter of severity
            )

        # Generate unique ID for this component
        unique_id = id(self)

        # Generate inner SVG content (without outer svg tags)
        inner_content = f'''
            <!-- Pipe body -->
            <rect x="{pipe_x_start}" y="{pipe_y}" 
                  width="{pipe_length_pixels}" height="{pipe_diameter_pixels}" 
                  fill="url(#pipeGrad_{unique_id})" stroke="{color}" stroke-width="2" rx="4"/>
            
            <!-- Inlet flange -->
            <rect x="{inlet_x - flange_width // 2}" y="{pipe_y - 4}" 
                  width="{flange_width}" height="{flange_height}" 
                  fill="#6b7280" rx="2"/>
            
            <!-- Outlet flange -->
            <rect x="{outlet_x - flange_width // 2}" y="{pipe_y - 4}" 
                  width="{flange_width}" height="{flange_height}" 
                  fill="#6b7280" rx="2"/>
            
            <!-- Connection points -->
            <circle cx="{inlet_x}" cy="{center_y}" r="3" 
                    fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            <circle cx="{outlet_x}" cy="{center_y}" r="3" 
                    fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            
            <!-- Flow direction indicators -->
            {direction_indicators}
            
            <!-- Flow particles -->
            {particles}
            
            <!-- LeakInfo visualizations -->
            {leak_visuals}
        '''

        # Generate complete SVG with unique gradient ID
        viewbox = f"0 0 {self.canvas_width} {self.canvas_height}"
        main_svg = f'''
        <svg viewBox="{viewbox}" class="mx-auto" style="width: 100%; height: auto; max-width: 100%;">
            <defs>
                <linearGradient id="pipeGrad_{unique_id}" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" style="stop-color:{color};stop-opacity:0.3" />
                    <stop offset="50%" style="stop-color:{color};stop-opacity:0.6" />
                    <stop offset="100%" style="stop-color:{color};stop-opacity:0.3" />
                </linearGradient>
            </defs>
            {inner_content}
        </svg>
        '''

        # Create connection points
        inlet = ConnectionPoint(
            x=inlet_x,
            y=center_y,
            direction=self.direction,
            diameter=pipe_diameter_pixels,
            flow_rate=self.flow_rate,
        )
        outlet = ConnectionPoint(
            x=outlet_x,
            y=center_y,
            direction=self.direction,
            diameter=pipe_diameter_pixels,
            flow_rate=self.flow_rate,
        )
        return SVGComponent(
            main_svg=main_svg,
            inner_content=inner_content,
            width=self.canvas_width,
            height=self.canvas_height,
            inlet=inlet,
            outlet=outlet,
            viewbox=viewbox,
        )

    def connect(self, other: PipeComponent) -> "Pipeline":
        """Connect this pipe to another component."""
        return Pipeline([self, other])


@attrs.define(slots=True)
class VerticalPipe(PipeComponent):
    """Vertical pipe component."""

    direction: PipeDirection
    """Flow direction: must be NORTH or SOUTH."""
    internal_diameter: PlainQuantity[float]
    """Internal diameter of the pipe (e.g., mm, inches)."""
    length: PlainQuantity[float]
    """Physical length of the pipe (e.g., m, ft)."""
    flow_rate: PlainQuantity[float] = attrs.field(
        factory=lambda: Quantity(0.0, "ft^3/s")
    )
    """Current flow rate through the pipe."""
    max_flow_rate: PlainQuantity[float] = attrs.field(
        factory=lambda: Quantity(10.0, "ft^3/s")
    )
    """Maximum expected flow rate for intensity scaling."""
    scale_factor: typing.Optional[float] = 1.0
    """Scaling factor for converting physical dimensions to display pixels."""
    canvas_width: float = 100.0
    """Width of the SVG canvas for this pipe."""
    canvas_height: float = 400.0
    """Height of the SVG canvas for this pipe."""
    leaks: typing.List[LeakInfo] = attrs.field(factory=list)
    """List of leaks on this pipe."""

    def __attrs_post_init__(self):
        """
        Validate direction after initialization.

        :raises ValueError: If direction is not NORTH or SOUTH.
        """
        if self.direction not in [PipeDirection.NORTH, PipeDirection.SOUTH]:
            raise ValueError(
                f"VerticalPipe direction must be NORTH or SOUTH, got {self.direction}"
            )

    def get_svg_component(self) -> SVGComponent:
        """
        Generate SVG component for vertical pipe.

        Creates a complete SVG representation including:
        - Pipe body with flow-based coloring
        - Inlet and outlet flanges positioned for vertical orientation
        - Connection points for joining with other components
        - Flow direction indicators and animations
        - Flow particles following vertical flow direction

        :return: Complete SVG representation with connection information.
        """
        # Calculate pipe dimensions
        pipe_diameter_pixels = physical_to_display_unit(
            self.internal_diameter,
            self.scale_factor or 1.0,
            min_display_unit=8,
            max_display_unit=60,
        )

        pipe_length_pixels = physical_to_display_unit(
            self.length,
            self.scale_factor or 1.0,
            min_display_unit=200,
            max_display_unit=320,
        )

        # Calculate positioning
        pipe_x = (self.canvas_width - pipe_diameter_pixels) / 2
        pipe_y_start = (self.canvas_height - pipe_length_pixels) / 2
        pipe_y_end = pipe_y_start + pipe_length_pixels

        # Flow calculations
        intensity = calculate_flow_intensity(self.flow_rate, self.max_flow_rate)
        color = get_flow_color(intensity)

        # Flow direction setup
        if self.direction == PipeDirection.SOUTH:
            flow_start_y, flow_end_y = pipe_y_start + 20, pipe_y_end - 20
            arrow = "▼"
            inlet_y, outlet_y = pipe_y_start, pipe_y_end
        else:  # NORTH
            flow_start_y, flow_end_y = pipe_y_end - 20, pipe_y_start + 20
            arrow = "▲"
            inlet_y, outlet_y = pipe_y_end, pipe_y_start

        center_x = self.canvas_width / 2

        # Generate flow particles
        particles = ""
        if intensity > 0:
            particle_count = max(3, int(intensity * 8))
            animation_duration = max(0.8, 3.0 - intensity * 2.0)

            for i in range(particle_count):
                delay = i * (animation_duration / particle_count)
                particles += f'''
                <circle r="2" fill="{color}" opacity="0">
                    <animate attributeName="cx" 
                             values="{center_x};{center_x}" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                    <animate attributeName="cy" 
                             values="{flow_start_y};{flow_end_y}" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                    <animate attributeName="opacity" 
                             values="0;0.8;0.8;0" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                </circle>
                '''

        # Generate flow direction indicators
        direction_indicators = ""
        if intensity > 0:
            arrow_count = 4
            for i in range(arrow_count):
                y_pos = (
                    pipe_y_start
                    + 40
                    + (i * (pipe_length_pixels - 80) / (arrow_count - 1))
                )
                direction_indicators += f'''
                <text x="{center_x + pipe_diameter_pixels / 2 + 12}" y="{y_pos}" 
                      text-anchor="middle" font-size="12" fill="{color}" opacity="0.7">
                    <animate attributeName="opacity" 
                             values="0.3;1;0.3" 
                             dur="2s" 
                             repeatCount="indefinite" 
                             begin="{i * 0.3}s"/>
                    {arrow}
                </text>
                '''

        # Flange dimensions
        flange_width = pipe_diameter_pixels + 8
        flange_height = 8

        # Generate leak visualization
        leak_visuals = ""
        for leak in self.leaks:
            # Calculate leak position along pipe (vertical)
            if self.direction == PipeDirection.SOUTH:
                leak_y = pipe_y_start + (leak.location * pipe_length_pixels)
            else:
                leak_y = pipe_y_start + ((1 - leak.location) * pipe_length_pixels)
            leak_size = leak.get_visual_size(pipe_diameter_pixels)
            leak_color = leak.get_leak_color()

            # Create leak indicator (crack/hole)
            leak_visuals += f'''
            <!-- LeakInfo indicator at {leak.location:.1%} -->
            <g class="leak-indicator" data-severity="{leak.severity}">
                <!-- Main leak hole -->
                <ellipse cx="{center_x}" cy="{leak_y}" 
                         rx="{leak_size / 3}" ry="{leak_size / 2}" 
                         fill="{leak_color}" stroke="#000000" stroke-width="1" 
                         opacity="0.8">
                    <animate attributeName="opacity" 
                             values="0.6;1;0.6" 
                             dur="1.5s" 
                             repeatCount="indefinite"/>
                </ellipse>
                
                <!-- LeakInfo spray particles -->
                <g class="leak-spray">
            '''

            # Generate spray particles for active leaks
            spray_count = leak.get_spray_count()
            for i in range(spray_count):
                # Spray particles emanating from leak (horizontal spray from vertical pipe)
                angle = -135 + (i * 90 / max(1, spray_count - 1))  # Spray sideways
                spray_distance = leak_size * (1.5 + i * 0.3)
                spray_x = (
                    center_x + spray_distance * math.cos(math.radians(angle)) * 0.5
                )
                spray_y = leak_y + spray_distance * math.sin(math.radians(angle)) * 0.3

                leak_visuals += f'''
                <circle cx="{spray_x}" cy="{spray_y}" r="1" 
                        fill="{leak_color}" opacity="0.4">
                    <animate attributeName="opacity" 
                                values="0;0.7;0" 
                                dur="{1 + i * 0.2}s" 
                                repeatCount="indefinite" 
                                begin="{i * 0.1}s"/>
                    <animateTransform attributeName="transform" 
                                        type="translate" 
                                        values="0,0; {spray_distance / 3},0" 
                                        dur="{1 + i * 0.2}s" 
                                        repeatCount="indefinite" 
                                        begin="{i * 0.1}s"/>
                </circle>
                '''

            leak_visuals += """
                </g>
                
                <!-- LeakInfo severity indicator -->
                <text x="{}" y="{}" text-anchor="middle" 
                      font-size="8" fill="{}" font-weight="bold" opacity="0.8">
                    {}
                </text>
            </g>
            """.format(
                center_x + pipe_diameter_pixels / 2 + 15,
                leak_y,
                leak_color,
                leak.severity[0].upper(),  # First letter of severity
            )

        # Generate unique ID for this component
        unique_id = id(self)

        # Generate inner SVG content
        inner_content = f'''
            <!-- Pipe body -->
            <rect x="{pipe_x}" y="{pipe_y_start}" 
                  width="{pipe_diameter_pixels}" height="{pipe_length_pixels}" 
                  fill="url(#pipeGradV_{unique_id})" stroke="{color}" stroke-width="2" rx="4"/>
            
            <!-- Inlet flange -->
            <rect x="{pipe_x - 4}" y="{inlet_y - flange_height // 2}" 
                  width="{flange_width}" height="{flange_height}" 
                  fill="#6b7280" rx="2"/>
            
            <!-- Outlet flange -->
            <rect x="{pipe_x - 4}" y="{outlet_y - flange_height // 2}" 
                  width="{flange_width}" height="{flange_height}" 
                  fill="#6b7280" rx="2"/>
            
            <!-- Connection points -->
            <circle cx="{center_x}" cy="{inlet_y}" r="3" 
                    fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            <circle cx="{center_x}" cy="{outlet_y}" r="3" 
                    fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            
            <!-- Flow direction indicators -->
            {direction_indicators}
            
            <!-- Flow particles -->
            {particles}
            
            <!-- LeakInfo visualizations -->
            {leak_visuals}
        '''

        # Generate complete SVG
        viewbox = f"0 0 {self.canvas_width} {self.canvas_height}"
        main_svg = f'''
        <svg viewBox="{viewbox}" class="mx-auto" style="width: 100%; max-width: 100%; height: 100%;">
            <defs>
                <linearGradient id="pipeGradV_{unique_id}" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" style="stop-color:{color};stop-opacity:0.3" />
                    <stop offset="50%" style="stop-color:{color};stop-opacity:0.6" />
                    <stop offset="100%" style="stop-color:{color};stop-opacity:0.3" />
                </linearGradient>
            </defs>
            {inner_content}
        </svg>
        '''

        # Create connection points
        inlet = ConnectionPoint(
            x=center_x,
            y=inlet_y,
            direction=self.direction,
            diameter=pipe_diameter_pixels,
            flow_rate=self.flow_rate,
        )
        outlet = ConnectionPoint(
            x=center_x,
            y=outlet_y,
            direction=self.direction,
            diameter=pipe_diameter_pixels,
            flow_rate=self.flow_rate,
        )
        return SVGComponent(
            main_svg=main_svg,
            inner_content=inner_content,
            width=self.canvas_width,
            height=self.canvas_height,
            inlet=inlet,
            outlet=outlet,
            viewbox=viewbox,
        )

    def connect(self, other: PipeComponent) -> "Pipeline":
        """Connect this pipe to another component."""
        return Pipeline([self, other])


@attrs.define(slots=True)
class ValveComponent(PipeComponent):
    """Valve component for flow control visualization."""

    direction: PipeDirection
    """Flow direction through the valve."""
    internal_diameter: PlainQuantity[float]
    """Internal diameter of the pipe the valve is attached to."""
    state: typing.Literal["open", "close"] = "open"
    """Valve state: "open" or "closed"."""
    flow_rate: PlainQuantity[float] = attrs.field(
        factory=lambda: Quantity(0.0, "ft^3/s")
    )
    """Current flow rate through the valve (0 if closed)."""
    scale_factor: typing.Optional[float] = 0.1
    """Scaling factor for converting physical dimensions to display pixels."""
    canvas_width: float = 80.0
    """Width of the SVG canvas for this valve."""
    canvas_height: float = 80.0
    """Height of the SVG canvas for this valve."""

    def get_svg_component(self) -> SVGComponent:
        """
        Generate SVG component for valve.

        Creates a complete SVG representation including:
        - Valve body with state-based coloring (green=open, red=closed)
        - Valve handle positioned appropriately
        - Connection points for joining with pipes
        - State indicator text
        - Proper orientation based on flow direction

        :return: Complete SVG representation with connection information.
        """
        # Valve color based on state
        valve_color = "#10b981" if self.state == "open" else "#ef4444"

        # Calculate valve dimensions based on pipe diameter
        diameter_pixels = physical_to_display_unit(
            self.internal_diameter,
            self.scale_factor or 0.1,
            min_display_unit=8,
            max_display_unit=60,
        )

        valve_width = diameter_pixels * 2.5  # Valve is wider than pipe
        valve_height = diameter_pixels * 3  # Valve body height

        is_vertical = self.direction in [PipeDirection.NORTH, PipeDirection.SOUTH]
        if is_vertical:
            # Vertical valve
            center_x = self.canvas_width / 2
            center_y = self.canvas_height / 2

            inlet_y = 0
            outlet_y = self.canvas_height

            inner_content = f'''
                <g transform="translate({center_x}, {center_y})">
                    <!-- Valve body -->
                    <rect x="{-valve_width / 2}" y="{-valve_height / 2}" 
                          width="{valve_width}" height="{valve_height}" 
                          fill="{valve_color}" stroke="#1e293b" stroke-width="2" rx="4"/>
                    <!-- Valve handle -->
                    <line x1="0" y1="{-valve_height / 2}" x2="0" y2="{-valve_height / 2 - 20}" 
                          stroke="#1e293b" stroke-width="4" stroke-linecap="round"/>
                    <circle cx="0" cy="{-valve_height / 2 - 20}" r="6" fill="#1e293b"/>
                    <!-- State indicator -->
                    <text x="0" y="5" text-anchor="middle" font-size="10" 
                          fill="white" font-weight="bold">{self.state[0].upper()}</text>
                </g>
                <!-- Connection points -->
                <circle cx="{center_x}" cy="{inlet_y}" r="3" 
                        fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
                <circle cx="{center_x}" cy="{outlet_y}" r="3" 
                        fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            '''

            inlet = ConnectionPoint(
                x=center_x,
                y=inlet_y,
                direction=self.direction,
                diameter=diameter_pixels,
                flow_rate=self.flow_rate,
            )
            outlet = ConnectionPoint(
                x=center_x,
                y=outlet_y,
                direction=self.direction,
                diameter=diameter_pixels,
                flow_rate=self.flow_rate,
            )
        else:
            # Horizontal valve
            center_x = self.canvas_width / 2
            center_y = self.canvas_height / 2

            inlet_x = 0
            outlet_x = self.canvas_width

            inner_content = f'''
                <g transform="translate({center_x}, {center_y})">
                    <!-- Valve body -->
                    <rect x="{-valve_height / 2}" y="{-valve_width / 2}" 
                          width="{valve_height}" height="{valve_width}" 
                          fill="{valve_color}" stroke="#1e293b" stroke-width="2" rx="4"/>
                    <!-- Valve handle -->
                    <line x1="{-valve_height / 2}" y1="0" x2="{-valve_height / 2 - 20}" y2="0" 
                          stroke="#1e293b" stroke-width="4" stroke-linecap="round"/>
                    <circle cx="{-valve_height / 2 - 20}" cy="0" r="6" fill="#1e293b"/>
                    <!-- State indicator -->
                    <text x="0" y="5" text-anchor="middle" font-size="10" 
                          fill="white" font-weight="bold">{self.state[0].upper()}</text>
                </g>
                <!-- Connection points -->
                <circle cx="{inlet_x}" cy="{center_y}" r="3" 
                        fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
                <circle cx="{outlet_x}" cy="{center_y}" r="3" 
                        fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            '''

            inlet = ConnectionPoint(
                x=inlet_x,
                y=center_y,
                direction=self.direction,
                diameter=diameter_pixels,
                flow_rate=self.flow_rate,
            )
            outlet = ConnectionPoint(
                x=outlet_x,
                y=center_y,
                direction=self.direction,
                diameter=diameter_pixels,
                flow_rate=self.flow_rate,
            )

        # Generate complete SVG
        viewbox = f"0 0 {self.canvas_width} {self.canvas_height}"
        main_svg = f'''
        <svg viewBox="{viewbox}" class="mx-auto" style="width: 100%; height: auto; max-width: 100%;">
            {inner_content}
        </svg>
        '''
        return SVGComponent(
            main_svg=main_svg,
            inner_content=inner_content,
            width=self.canvas_width,
            height=self.canvas_height,
            inlet=inlet,
            outlet=outlet,
            viewbox=viewbox,
        )

    def connect(self, other: PipeComponent) -> "Pipeline":
        """Connect this valve to another component."""
        return Pipeline([self, other])


@attrs.define(slots=True)
class StraightConnector(PipeComponent):
    """Straight connector between pipes of same direction."""

    pipe1: PipeComponent
    """First pipe component (upstream)."""
    pipe2: PipeComponent
    """Second pipe component (downstream)."""
    length: PlainQuantity[float] = attrs.field(factory=lambda: Quantity(50, "mm"))
    """Physical length of the connector."""
    scale_factor: typing.Optional[float] = None
    """Scaling factor for converting physical dimensions to display pixels. If None, average of connected pipes is used."""

    def __attrs_post_init__(self):
        """
        Validate that pipes have same direction.

        :raises ValueError: If the connected pipes have different flow directions.
        """
        svg1 = self.pipe1.get_svg_component()
        svg2 = self.pipe2.get_svg_component()

        if svg1.outlet.direction != svg2.inlet.direction:
            raise ValueError("StraightConnector requires pipes with same direction")

    def get_svg_component(self) -> SVGComponent:
        """
        Generate SVG for straight connector.

        Creates a connector that transitions between pipes of the same direction
        but potentially different diameters. Handles:
        - Tapered transitions for diameter changes (reducers/expanders)
        - Flow direction-aware particle animation
        - Proper connection point positioning
        - Both horizontal and vertical orientations

        :return: SVG representation of the straight connector.
        """
        svg1 = self.pipe1.get_svg_component()
        svg2 = self.pipe2.get_svg_component()

        direction = svg1.outlet.direction
        diameter1 = svg1.outlet.diameter
        diameter2 = svg2.inlet.diameter
        flow_rate = svg1.outlet.flow_rate
        max_flow_rate = getattr(self.pipe1, "max_flow_rate", Quantity(10.0, "ft^3/s"))
        if self.scale_factor is None:
            scale_factor = (
                (self.pipe1.scale_factor or 1.0) + (self.pipe2.scale_factor or 1.0)
            ) / 2
        else:
            scale_factor = self.scale_factor

        # Generate unique ID for this component
        unique_id = id(self)

        # Calculate connector dimensions
        length_pixels = physical_to_display_unit(
            self.length,
            scale_factor,
            min_display_unit=30,
            max_display_unit=100,
        )

        intensity = calculate_flow_intensity(flow_rate, max_flow_rate)
        color = get_flow_color(intensity)

        if direction in [PipeDirection.EAST, PipeDirection.WEST]:
            # Horizontal connector
            width = length_pixels + 10
            height = 80
            center_y = height / 2

            if direction == PipeDirection.EAST:
                inlet_x, outlet_x = 0, width
                start_x, end_x = 5, width - 5
            else:  # WEST
                inlet_x, outlet_x = width, 0
                start_x, end_x = width - 5, 5

            # Create tapered connector path
            y1 = center_y - diameter1 / 2
            y2 = center_y - diameter2 / 2

            if abs(diameter1 - diameter2) < 2:
                # Straight connector
                connector_path = f'''
                <rect x="5" y="{min(y1, y2)}" width="{length_pixels}" 
                      height="{max(diameter1, diameter2)}" 
                      fill="url(#connectorGrad_{unique_id})" stroke="{color}" stroke-width="2" rx="3"/>
                '''
            else:
                # Tapered connector
                if direction == PipeDirection.EAST:
                    points = f"5,{y1} {5 + length_pixels},{y2} {5 + length_pixels},{y2 + diameter2} 5,{y1 + diameter1}"
                else:  # WEST
                    points = f"{5 + length_pixels},{y1} 5,{y2} 5,{y2 + diameter2} {5 + length_pixels},{y1 + diameter1}"

                connector_path = f'''
                <polygon points="{points}" 
                         fill="url(#connectorGrad_{unique_id})" stroke="{color}" stroke-width="2"/>
                '''

            # Flow particles
            particles = ""
            if intensity > 0:
                particle_count = max(2, int(intensity * 5))
                animation_duration = max(0.8, 2.5 - intensity * 1.5)

                for i in range(particle_count):
                    delay = i * (animation_duration / particle_count)
                    particles += f'''
                    <circle r="1.5" fill="{color}" opacity="0">
                        <animate attributeName="cx" 
                                 values="{start_x};{end_x}" 
                                 dur="{animation_duration}s" 
                                 repeatCount="indefinite" 
                                 begin="{delay}s"/>
                        <animate attributeName="cy" 
                                 values="{center_y};{center_y}" 
                                 dur="{animation_duration}s" 
                                 repeatCount="indefinite" 
                                 begin="{delay}s"/>
                        <animate attributeName="opacity" 
                                 values="0;0.8;0.8;0" 
                                 dur="{animation_duration}s" 
                                 repeatCount="indefinite" 
                                 begin="{delay}s"/>
                    </circle>
                    '''

            inlet = ConnectionPoint(inlet_x, center_y, direction, diameter1, flow_rate)
            outlet = ConnectionPoint(
                outlet_x, center_y, direction, diameter2, flow_rate
            )

        else:
            # Vertical connector
            width = 80
            height = length_pixels + 10
            center_x = width / 2

            if direction == PipeDirection.SOUTH:
                inlet_y, outlet_y = 0, height
                start_y, end_y = 5, height - 5
            else:  # NORTH
                inlet_y, outlet_y = height, 0
                start_y, end_y = height - 5, 5

            # Create tapered connector path
            x1 = center_x - diameter1 / 2
            x2 = center_x - diameter2 / 2

            if abs(diameter1 - diameter2) < 2:
                # Straight connector
                connector_path = f'''
                <rect x="{min(x1, x2)}" y="5" width="{max(diameter1, diameter2)}" 
                      height="{length_pixels}" 
                      fill="url(#connectorGrad_{unique_id})" stroke="{color}" stroke-width="2" rx="3"/>
                '''
            else:
                # Tapered connector
                if direction == PipeDirection.SOUTH:
                    points = f"{x1},5 {x2},{5 + length_pixels} {x2 + diameter2},{5 + length_pixels} {x1 + diameter1},5"
                else:  # NORTH
                    points = f"{x1},{5 + length_pixels} {x2},5 {x2 + diameter2},5 {x1 + diameter1},{5 + length_pixels}"

                connector_path = f'''
                <polygon points="{points}" 
                         fill="url(#connectorGrad_{unique_id})" stroke="{color}" stroke-width="2"/>
                '''

            # Flow particles
            particles = ""
            if intensity > 0:
                particle_count = max(2, int(intensity * 5))
                animation_duration = max(0.8, 2.5 - intensity * 1.5)

                for i in range(particle_count):
                    delay = i * (animation_duration / particle_count)
                    particles += f'''
                    <circle r="1.5" fill="{color}" opacity="0">
                        <animate attributeName="cx" 
                                 values="{center_x};{center_x}" 
                                 dur="{animation_duration}s" 
                                 repeatCount="indefinite" 
                                 begin="{delay}s"/>
                        <animate attributeName="cy" 
                                 values="{start_y};{end_y}" 
                                 dur="{animation_duration}s" 
                                 repeatCount="indefinite" 
                                 begin="{delay}s"/>
                        <animate attributeName="opacity" 
                                 values="0;0.8;0.8;0" 
                                 dur="{animation_duration}s" 
                                 repeatCount="indefinite" 
                                 begin="{delay}s"/>
                    </circle>
                    '''

            inlet = ConnectionPoint(center_x, inlet_y, direction, diameter1, flow_rate)
            outlet = ConnectionPoint(
                center_x, outlet_y, direction, diameter2, flow_rate
            )

        # Generate inner content
        inner_content = f'''
            {connector_path}
            <!-- Connection points -->
            <circle cx="{inlet.x}" cy="{inlet.y}" r="2" 
                    fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            <circle cx="{outlet.x}" cy="{outlet.y}" r="2" 
                    fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            {particles}
        '''

        # Generate complete SVG
        viewbox = f"0 0 {width} {height}"
        main_svg = f'''
        <svg viewBox="{viewbox}" class="mx-auto" style="width: 100%; height: auto; max-width: 100%;">
            <defs>
                <linearGradient id="connectorGrad_{unique_id}" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style="stop-color:{color};stop-opacity:0.3" />
                    <stop offset="50%" style="stop-color:{color};stop-opacity:0.6" />
                    <stop offset="100%" style="stop-color:{color};stop-opacity:0.3" />
                </linearGradient>
            </defs>
            {inner_content}
        </svg>
        '''

        return SVGComponent(
            main_svg=main_svg,
            inner_content=inner_content,
            width=width,
            height=height,
            inlet=inlet,
            outlet=outlet,
            viewbox=viewbox,
        )

    def connect(self, other: PipeComponent) -> "Pipeline":
        """Connect this connector to another component."""
        return Pipeline([self, other])


@attrs.define(slots=True)
class ElbowConnector(PipeComponent):
    """Elbow connector for direction changes."""

    pipe1: PipeComponent
    """First pipe component (upstream)."""
    pipe2: PipeComponent
    """Second pipe component (downstream)."""
    arm_length: PlainQuantity[float] = attrs.field(factory=lambda: Quantity(30, "mm"))
    """Length of each arm of the elbow connector."""
    scale_factor: typing.Optional[float] = None
    """Scaling factor for converting physical dimensions to display pixels. If None, average of connected pipes is used."""

    def __attrs_post_init__(self):
        """
        Validate that pipes have different directions.

        :raises ValueError: If the connected pipes have the same flow direction.
        """
        svg1 = self.pipe1.get_svg_component()
        svg2 = self.pipe2.get_svg_component()

        if svg1.outlet.direction == svg2.inlet.direction:
            raise ValueError("ElbowConnector requires pipes with different directions")

    def get_svg_component(self) -> SVGComponent:
        """
        Generate SVG for elbow connector.

        Creates a 90-degree elbow connector for changing flow directions.
        Features include:
        - Dynamic orientation based on inlet/outlet directions
        - Smooth curved flow particle paths
        - Proper connection point positioning for all direction combinations
        - Flow-based coloring and animation

        Supports all valid direction combinations:
        - EAST ↔ NORTH/SOUTH
        - WEST ↔ NORTH/SOUTH
        - NORTH/SOUTH ↔ EAST/WEST

        :return: SVG representation of the elbow connector.
        """
        svg1 = self.pipe1.get_svg_component()
        svg2 = self.pipe2.get_svg_component()

        inlet_dir = svg1.outlet.direction
        outlet_dir = svg2.inlet.direction
        diameter1 = svg1.outlet.diameter
        diameter2 = svg2.inlet.diameter
        flow_rate = svg1.outlet.flow_rate
        max_flow_rate = getattr(self.pipe1, "max_flow_rate", Quantity(10.0, "ft^3/s"))

        if self.scale_factor is None:
            scale_factor = (
                (self.pipe1.scale_factor or 1.0) + (self.pipe2.scale_factor or 1.0)
            ) / 2
        else:
            scale_factor = self.scale_factor

        # Calculate arm length in pixels
        arm_pixels = physical_to_display_unit(
            self.arm_length,
            scale_factor,
            min_display_unit=20,
            max_display_unit=60,
        )

        # Generate unique ID for this component
        unique_id = id(self)

        # Use average diameter for consistent appearance
        avg_diameter = (diameter1 + diameter2) / 2

        intensity = calculate_flow_intensity(flow_rate, max_flow_rate)
        color = get_flow_color(intensity)

        # Calculate elbow size based on arm length to ensure proper alignment
        margin = 10  # Margin around the elbow
        width = height = 2 * arm_pixels + margin * 2
        center_x = center_y = arm_pixels + margin

        # Determine elbow orientation and positions
        orientation_map = {
            (PipeDirection.EAST, PipeDirection.NORTH): ("west", "north"),
            (PipeDirection.EAST, PipeDirection.SOUTH): ("west", "south"),
            (PipeDirection.WEST, PipeDirection.NORTH): ("east", "north"),
            (PipeDirection.WEST, PipeDirection.SOUTH): ("east", "south"),
            (PipeDirection.SOUTH, PipeDirection.EAST): ("north", "east"),
            (PipeDirection.SOUTH, PipeDirection.WEST): ("north", "west"),
            (PipeDirection.NORTH, PipeDirection.EAST): ("south", "east"),
            (PipeDirection.NORTH, PipeDirection.WEST): ("south", "west"),
        }

        inlet_face, outlet_face = orientation_map.get(
            (inlet_dir, outlet_dir), ("west", "north")
        )

        # Calculate positions - these should be at the exact edge of the elbow for proper alignment
        if inlet_face == "west":
            inlet_x, inlet_y = margin, center_y  # Left edge
        elif inlet_face == "east":
            inlet_x, inlet_y = width - margin, center_y  # Right edge
        elif inlet_face == "north":
            inlet_x, inlet_y = center_x, margin  # Top edge
        else:  # south
            inlet_x, inlet_y = center_x, height - margin  # Bottom edge

        if outlet_face == "west":
            outlet_x, outlet_y = margin, center_y  # Left edge
        elif outlet_face == "east":
            outlet_x, outlet_y = width - margin, center_y  # Right edge
        elif outlet_face == "north":
            outlet_x, outlet_y = center_x, margin  # Top edge
        else:  # south
            outlet_x, outlet_y = center_x, height - margin  # Bottom edge

        # Create elbow geometry that extends exactly to the connection points
        if inlet_face in ["west", "east"] and outlet_face in ["north", "south"]:
            # Horizontal to vertical
            # Horizontal arm extends from inlet to center
            if inlet_face == "west":
                h_start_x = inlet_x
                h_width = center_x - inlet_x + avg_diameter / 2
            else:  # east
                h_start_x = center_x - avg_diameter / 2
                h_width = inlet_x - center_x + avg_diameter / 2

            h_rect = f'''<rect x="{h_start_x}" y="{center_y - avg_diameter / 2}" 
                              width="{h_width}" height="{avg_diameter}" 
                              fill="url(#elbowGrad_{unique_id})" stroke="{color}" stroke-width="2" rx="3"/>'''

            # Vertical arm extends from outlet to center
            if outlet_face == "north":
                v_start_y = outlet_y
                v_height = center_y - outlet_y + avg_diameter / 2
            else:  # south
                v_start_y = center_y - avg_diameter / 2
                v_height = outlet_y - center_y + avg_diameter / 2

            v_rect = f'''<rect x="{center_x - avg_diameter / 2}" y="{v_start_y}" 
                              width="{avg_diameter}" height="{v_height}" 
                              fill="url(#elbowGrad_{unique_id})" stroke="{color}" stroke-width="2" rx="3"/>'''
        else:
            # Vertical to horizontal
            # Vertical arm extends from inlet to center
            if inlet_face == "north":
                v_start_y = inlet_y
                v_height = center_y - inlet_y + avg_diameter / 2
            else:  # south
                v_start_y = center_y - avg_diameter / 2
                v_height = inlet_y - center_y + avg_diameter / 2

            v_rect = f'''<rect x="{center_x - avg_diameter / 2}" y="{v_start_y}" 
                              width="{avg_diameter}" height="{v_height}" 
                              fill="url(#elbowGrad_{unique_id})" stroke="{color}" stroke-width="2" rx="3"/>'''

            # Horizontal arm extends from outlet to center
            if outlet_face == "west":
                h_start_x = outlet_x
                h_width = center_x - outlet_x + avg_diameter / 2
            else:  # east
                h_start_x = center_x - avg_diameter / 2
                h_width = outlet_x - center_x + avg_diameter / 2

            h_rect = f'''<rect x="{h_start_x}" y="{center_y - avg_diameter / 2}" 
                              width="{h_width}" height="{avg_diameter}" 
                              fill="url(#elbowGrad_{unique_id})" stroke="{color}" stroke-width="2" rx="3"/>'''

        # Flow particles following curved path
        particles = ""
        if intensity > 0:
            particle_count = max(3, int(intensity * 6))
            animation_duration = max(1.0, 3.0 - intensity * 2.0)

            for i in range(particle_count):
                delay = i * (animation_duration / particle_count)

                # Create curved path from inlet to outlet
                particles += f'''
                <circle r="1.5" fill="{color}" opacity="0">
                    <animateMotion dur="{animation_duration}s" repeatCount="indefinite" begin="{delay}s">
                        <path d="M {inlet_x},{inlet_y} Q {center_x},{center_y} {outlet_x},{outlet_y}"/>
                    </animateMotion>
                    <animate attributeName="opacity" 
                             values="0;0.8;0.8;0" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                </circle>
                '''

        # Add center junction sized to properly connect the arms
        junction_radius = avg_diameter / 2 + 2
        center_junction = f'''<circle cx="{center_x}" cy="{center_y}" r="{junction_radius}" 
                                    fill="{color}" fill-opacity="0.9" stroke="{color}" stroke-width="3"/>'''

        # Generate inner content
        inner_content = f'''
            {h_rect}
            {v_rect}
            {center_junction}
            <!-- Connection points -->
            <circle cx="{inlet_x}" cy="{inlet_y}" r="2" 
                    fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            <circle cx="{outlet_x}" cy="{outlet_y}" r="2" 
                    fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            {particles}
        '''

        # Generate complete SVG
        viewbox = f"0 0 {width} {height}"
        main_svg = f'''
        <svg viewBox="{viewbox}" class="mx-auto" style="width: 100%; height: auto; max-width: 100%;">
            <defs>
                <linearGradient id="elbowGrad_{unique_id}" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style="stop-color:{color};stop-opacity:0.3" />
                    <stop offset="50%" style="stop-color:{color};stop-opacity:0.6" />
                    <stop offset="100%" style="stop-color:{color};stop-opacity:0.3" />
                </linearGradient>
            </defs>
            {inner_content}
        </svg>
        '''

        # Create connection points
        inlet = ConnectionPoint(inlet_x, inlet_y, inlet_dir, diameter1, flow_rate)
        outlet = ConnectionPoint(outlet_x, outlet_y, outlet_dir, diameter2, flow_rate)
        return SVGComponent(
            main_svg=main_svg,
            inner_content=inner_content,
            width=width,
            height=height,
            inlet=inlet,
            outlet=outlet,
            viewbox=viewbox,
        )

    def connect(self, other: PipeComponent) -> "Pipeline":
        """Connect this connector to another component."""
        return Pipeline([self, other])


@attrs.define
class Pipeline(PipeComponent):
    """Pipeline composed of multiple connected components."""

    components: typing.List[PipeComponent] = attrs.field(factory=list)
    """List of pipe components that make up this pipeline."""
    scale_factor: typing.Optional[float] = None
    """Scaling factor for converting physical dimensions to display pixels. If set, overrides individual component scale factors."""

    def get_svg_component(self) -> SVGComponent:
        """
        Generate combined SVG for entire pipeline.

        Combines all component SVGs into a single cohesive visualization:
        - Automatically positions components for proper connection alignment
        - Merges SVG definitions to avoid conflicts
        - Calculates overall bounding box with padding
        - Maintains connection point relationships
        - Preserves individual component animations and styling

        :return: Combined SVG representing the complete pipeline.
        """
        if not self.components:
            # Empty pipeline
            return SVGComponent(
                main_svg='<svg width="200" height="100" viewBox="0 0 200 100"><text x="100" y="50" text-anchor="middle">Empty Pipeline</text></svg>',
                inner_content='<text x="100" y="50" text-anchor="middle">Empty Pipeline</text>',
                width=200,
                height=100,
                inlet=ConnectionPoint(0, 50, PipeDirection.EAST, 0),
                outlet=ConnectionPoint(200, 50, PipeDirection.EAST, 0),
                viewbox="0 0 200 100",
            )

        if self.scale_factor is not None:
            components = []
            for comp in self.components:
                comp = copy.copy(comp)
                comp.scale_factor = self.scale_factor
                components.append(comp)
        else:
            components = self.components

        # Get SVG components for all elements
        svg_components = [comp.get_svg_component() for comp in components]

        # Calculate layout and positioning
        current_x = 0
        current_y = 0
        positioned_components = []

        for i, svg_comp in enumerate(svg_components):
            if i == 0:
                # First component at origin
                pos_x, pos_y = 0, 0
            else:
                # Position relative to previous component's outlet
                prev_svg = positioned_components[-1]
                prev_outlet = prev_svg["svg"].outlet
                current_inlet = svg_comp.inlet

                # Calculate offset to align connection points
                pos_x = prev_svg["x"] + prev_outlet.x - current_inlet.x
                pos_y = prev_svg["y"] + prev_outlet.y - current_inlet.y

            positioned_components.append({"svg": svg_comp, "x": pos_x, "y": pos_y})

            current_x = max(current_x, pos_x + svg_comp.width)
            current_y = max(current_y, pos_y + svg_comp.height)

        # Calculate total bounding box
        min_x = min_y = 0
        max_x = max_y = 0

        for comp in positioned_components:
            min_x = min(min_x, comp["x"])
            min_y = min(min_y, comp["y"])
            max_x = max(max_x, comp["x"] + comp["svg"].width)
            max_y = max(max_y, comp["y"] + comp["svg"].height)

        # Add padding
        padding = 20
        total_width = max_x - min_x + 2 * padding
        total_height = max_y - min_y + 2 * padding
        offset_x = padding - min_x
        offset_y = padding - min_y

        # Combine all inner content
        combined_content = ""
        all_defs = set()

        for comp in positioned_components:
            svg_comp = comp["svg"]
            x_pos = comp["x"] + offset_x
            y_pos = comp["y"] + offset_y

            # Extract defs from main SVG
            import re

            defs_match = re.search(r"<defs>(.*?)</defs>", svg_comp.main_svg, re.DOTALL)
            if defs_match:
                all_defs.add(defs_match.group(1))

            # Add positioned content
            combined_content += f"""
            <g transform="translate({x_pos}, {y_pos})">
                {svg_comp.inner_content}
            </g>
            """

        # Create final SVG
        viewbox = f"0 0 {total_width} {total_height}"
        main_svg = f'''
        <svg width="100%" height="auto" viewBox="{viewbox}" class="mx-auto">
            <defs>
                {"".join(all_defs)}
            </defs>
            {combined_content}
        </svg>
        '''

        # Calculate pipeline inlet/outlet
        first_comp = positioned_components[0]
        last_comp = positioned_components[-1]

        pipeline_inlet = ConnectionPoint(
            x=first_comp["x"] + first_comp["svg"].inlet.x + offset_x,
            y=first_comp["y"] + first_comp["svg"].inlet.y + offset_y,
            direction=first_comp["svg"].inlet.direction,
            diameter=first_comp["svg"].inlet.diameter,
            flow_rate=first_comp["svg"].inlet.flow_rate,
        )

        pipeline_outlet = ConnectionPoint(
            x=last_comp["x"] + last_comp["svg"].outlet.x + offset_x,
            y=last_comp["y"] + last_comp["svg"].outlet.y + offset_y,
            direction=last_comp["svg"].outlet.direction,
            diameter=last_comp["svg"].outlet.diameter,
            flow_rate=last_comp["svg"].outlet.flow_rate,
        )

        return SVGComponent(
            main_svg=main_svg,
            inner_content=combined_content,
            width=total_width,
            height=total_height,
            inlet=pipeline_inlet,
            outlet=pipeline_outlet,
            viewbox=viewbox,
        )

    def connect(self, other: PipeComponent) -> "Pipeline":
        """Connect this pipeline to another component."""
        return Pipeline(self.components + [other])


def build_horizontal_pipe(
    direction: PipeDirection,
    internal_diameter: PlainQuantity[float],
    length: PlainQuantity[float],
    flow_rate: typing.Optional[PlainQuantity[float]] = None,
    max_flow_rate: typing.Optional[PlainQuantity[float]] = None,
    scale_factor: float = 1.0,
    canvas_width: float = 400.0,
    canvas_height: float = 100.0,
    leaks: typing.Optional[typing.List[LeakInfo]] = None,
) -> HorizontalPipe:
    """
    Build a horizontal pipe component.

    Convenience function for creating horizontal pipes with proper defaults.

    :param direction: Flow direction (EAST or WEST).
    :param internal_diameter: Internal diameter of the pipe.
    :param length: Physical length of the pipe.
    :param flow_rate: Current flow rate. Defaults to 0.0 ft³/s.
    :param max_flow_rate: Maximum flow rate for intensity scaling. Defaults to 10.0 ft³/s.
    :param scale_factor: Scaling factor for physical to display conversion.
    :param canvas_width: Width of the SVG canvas.
    :param canvas_height: Height of the SVG canvas.
    :param leaks: Optional list of leaks in the pipe.
    :return: Configured horizontal pipe component.
    :raises ValueError: If direction is not EAST or WEST.
    """
    if flow_rate is None:
        flow_rate = Quantity(0.0, "ft^3/s")
    if max_flow_rate is None:
        max_flow_rate = Quantity(10.0, "ft^3/s")

    return HorizontalPipe(
        direction=direction,
        internal_diameter=internal_diameter,
        length=length,
        flow_rate=flow_rate,
        max_flow_rate=max_flow_rate,
        scale_factor=scale_factor,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        leaks=leaks or [],
    )


def build_vertical_pipe(
    direction: PipeDirection,
    internal_diameter: PlainQuantity[float],
    length: PlainQuantity[float],
    flow_rate: typing.Optional[PlainQuantity[float]] = None,
    max_flow_rate: typing.Optional[PlainQuantity[float]] = None,
    scale_factor: float = 1.0,
    canvas_width: float = 100.0,
    canvas_height: float = 400.0,
    leaks: typing.Optional[typing.List[LeakInfo]] = None,
) -> VerticalPipe:
    """
    Build a vertical pipe component.

    Convenience function for creating vertical pipes with proper defaults.

    :param direction: Flow direction (NORTH or SOUTH).
    :param internal_diameter: Internal diameter of the pipe.
    :param length: Physical length of the pipe.
    :param flow_rate: Current flow rate. Defaults to 0.0 ft³/s.
    :param max_flow_rate: Maximum flow rate for intensity scaling. Defaults to 10.0 ft³/s.
    :param scale_factor: Scaling factor for physical to display conversion.
    :param canvas_width: Width of the SVG canvas.
    :param canvas_height: Height of the SVG canvas.
    :param leaks: Optional list of leaks in the pipe.
    :return: Configured vertical pipe component.
    :raises ValueError: If direction is not NORTH or SOUTH.
    """
    if flow_rate is None:
        flow_rate = Quantity(0.0, "ft^3/s")
    if max_flow_rate is None:
        max_flow_rate = Quantity(10.0, "ft^3/s")

    return VerticalPipe(
        direction=direction,
        internal_diameter=internal_diameter,
        length=length,
        flow_rate=flow_rate,
        max_flow_rate=max_flow_rate,
        scale_factor=scale_factor,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        leaks=leaks or [],
    )


def build_straight_connector(
    pipe1: PipeComponent,
    pipe2: PipeComponent,
    length: typing.Optional[PlainQuantity[float]] = None,
) -> StraightConnector:
    """
    Build a straight connector between two pipes.

    Creates a straight connector for pipes flowing in the same direction.
    Automatically handles diameter transitions and flow direction.

    :param pipe1: First pipe component (upstream).
    :param pipe2: Second pipe component (downstream).
    :param length: Physical length of connector. Defaults to 50 mm.
    :return: Configured straight connector.
    :raises ValueError: If pipes have different flow directions.
    """
    if length is None:
        length = Quantity(50, "mm")

    return StraightConnector(pipe1=pipe1, pipe2=pipe2, length=length)


def build_elbow_connector(
    pipe1: PipeComponent,
    pipe2: PipeComponent,
    arm_length: typing.Optional[PlainQuantity[float]] = None,
) -> ElbowConnector:
    """
    Build an elbow connector between two pipes.

    Creates a 90-degree elbow connector for pipes with different flow directions.
    Automatically determines the correct orientation based on pipe directions.

    :param pipe1: First pipe component (upstream).
    :param pipe2: Second pipe component (downstream).
    :param arm_length: Length of each elbow arm. Defaults to 30 mm.
    :return: Configured elbow connector.
    :raises ValueError: If pipes have the same flow direction.
    """
    if arm_length is None:
        arm_length = Quantity(30, "mm")

    return ElbowConnector(pipe1=pipe1, pipe2=pipe2, arm_length=arm_length)


def build_valve(
    direction: PipeDirection,
    internal_diameter: PlainQuantity[float],
    state: str = "open",
    flow_rate: typing.Optional[PlainQuantity[float]] = None,
    scale_factor: float = 0.1,
    canvas_width: float = 80.0,
    canvas_height: float = 80.0,
) -> ValveComponent:
    """
    Build a valve component for the pipeline.

    Convenience function for creating valves with proper defaults.

    :param direction: Flow direction (affects valve orientation)
    :param internal_diameter: Diameter of pipe valve is attached to
    :param state: Valve state ("open" or "closed")
    :param flow_rate: Current flow rate. Defaults to 0.0 ft³/s.
    :param scale_factor: Display scale factor
    :param canvas_width: Canvas width in pixels
    :param canvas_height: Canvas height in pixels
    :return: Configured valve component
    """
    if flow_rate is None:
        flow_rate = Quantity(0.0, "ft^3/s")

    return ValveComponent(
        direction=direction,
        internal_diameter=internal_diameter,
        state=state,
        flow_rate=flow_rate,
        scale_factor=scale_factor,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
    )
