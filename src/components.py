import copy
import enum
import typing
import math
import re
import logging
from attrs import evolve
from nicegui import ui
from enum import Enum

from nicegui.elements.html import Html
from nicegui.elements.row import Row
from pint.facets.plain import PlainQuantity

from src.units import Quantity, ureg
from src.properties import (
    FlowEquation,
    Fluid,
    PipeProperties,
    compute_fluid_density,
    determine_pipe_flow_equation,
    compute_reynolds_number,
    compute_pipe_flow_rate,
    compute_pipe_pressure_drop,
    compute_tapered_pipe_pressure_drop,
)

logger = logging.getLogger(__name__)


__all__ = [
    "PipeDirection",
    "PipelineConnectionError",
    "physical_to_display_unit",
    "calculate_flow_intensity",
    "get_flow_color",
    "check_directions_compatibility",
    "Meter",
    "FlowMeter",
    "PressureGauge",
    "TemperatureGauge",
    "Regulator",
    "Pipe",
    "Pipeline",
    "FlowStation",
    "build_straight_pipe_connector_svg",
    "build_elbow_pipe_connector_svg",
]


class Meter:
    """Base class for all meters."""

    def __init__(
        self,
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 100.0,
        units: str = "",
        label: str = "Meter",
        width: str = "200px",
        height: str = "200px",
        precision: int = 3,
        alarm_high: typing.Optional[float] = None,
        alarm_low: typing.Optional[float] = None,
        animation_speed: float = 5.0,
        animation_interval: float = 0.1,
        update_func: typing.Optional[
            typing.Callable[[], typing.Optional[float]]
        ] = None,
        update_interval: float = 1.0,
    ) -> None:
        """
        Initialize the meter.

        :param value: Initial value
        :param min_value: Minimum value for scaling
        :param max_value: Maximum value for scaling
        :param units: Units to display
        :param label: Label for the meter
        :param width: Width of the meter
        :param height: Height of the meter
        :param precision: Decimal precision for value display
        :param alarm_high: High alarm threshold
        :param alarm_low: Low alarm threshold
        :param animation_speed: Speed of value change animation
        :param animation_interval: Interval in seconds for animation updates
        :param update_func: Optional function to fetch updated value
        :param update_interval: Interval in seconds to call `update_func`
        """
        self.value = value
        self.min = min_value
        self.max = max_value
        self.units = units
        self.label = label
        self.width = width
        self.height = height
        self.precision = precision
        self.alarm_high = alarm_high
        self.alarm_low = alarm_low
        self._target_value = value
        self.animation_speed = animation_speed
        self.animation_interval = animation_interval
        self.update_func = update_func
        self.update_interval = update_interval

        self.label_element = None
        self.value_element = None
        self.status_element = None
        self.container = None
        self.visible = False
        self._animation_timer = None
        self._update_timer = None

    def show(
        self,
        width: typing.Optional[str] = None,
        height: typing.Optional[str] = None,
        label: typing.Optional[str] = None,
        show_label: bool = True,
    ) -> ui.card:
        """
        Display the meter as a UI component.

        :param width: Width of the meter (overrides default if provided)
        :param height: Height of the meter (overrides default if provided)
        :param label: Label for the meter (overrides default if provided)
        :param show_label: Whether to display the label
        :return: UI card element containing the meter visualization
        """
        display_width = width or self.width
        display_height = height or self.height
        display_label = label or self.label

        # Create the UI container with enhanced styling and responsive scaling
        self.container = (
            ui.card()
            .classes("p-2 text-center flex flex-col items-center overflow-auto")
            .style(
                f"""
                width: {display_width}; 
                height: {display_height}; 
                min-width: {display_width}; 
                min-height: {display_height}; 
                background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
                border: 2px solid #e2e8f0;
                border-radius: 16px;
                box-shadow: 
                    0 10px 25px -5px rgba(0, 0, 0, 0.1),
                    0 8px 10px -6px rgba(0, 0, 0, 0.1),
                    inset 0 1px 0 rgba(255, 255, 255, 0.6);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                scrollbar-width: none;
                -ms-overflow-style: none;
                display: flex;
                flex-direction: column;
                justify-content: space-evenly;
                gap: 0.25rem;
                """
            )
        )

        # Add hover effects for Meter
        def on_mouseenter():
            if self.container:
                self.container.style(
                    add="""
                    transform: translateY(-2px);
                    box-shadow: 
                        0 20px 40px -10px rgba(0, 0, 0, 0.15),
                        0 15px 20px -10px rgba(0, 0, 0, 0.1),
                        inset 0 1px 0 rgba(255, 255, 255, 0.6);
                """
                )

        def on_mouseleave():
            if self.container:
                self.container.style(
                    add="""
                    transform: translateY(0px);
                    box-shadow: 
                        0 10px 25px -5px rgba(0, 0, 0, 0.1),
                        0 8px 10px -6px rgba(0, 0, 0, 0.1),
                        inset 0 1px 0 rgba(255, 255, 255, 0.6);
                """
                )

        self.container.on("mouseenter", on_mouseenter)
        self.container.on("mouseleave", on_mouseleave)

        with self.container:
            if show_label:
                self.label = display_label
            self.display()
            self.update_viz()

        # Initialize timers and mark as visible
        self._initialize_timers()
        self.set_visibility(True)

        return self.container

    def _initialize_timers(self):
        """Initialize animation and update timers."""
        if self._animation_timer is None:
            self._animation_timer = ui.timer(
                self.animation_interval,
                self._animate_value,
                once=False,
                immediate=True,
                active=False,
            )

        if self._update_timer is None and self.update_func is not None:
            self._update_timer = ui.timer(
                self.update_interval,
                self._update_value,
                once=False,
                immediate=True,
                active=False,
            )

    def display(self):
        """Override in subclasses to create specific meter displays"""
        self.label_element = (
            ui.label(self.label)
            .classes("font-bold mb-1 text-center w-full text-slate-700")
            .style("""
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            letter-spacing: -0.025em;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
            font-size: clamp(0.5rem, 2.5vw, 1rem);
            line-height: 1.1;
        """)
        )

        self.value_element = (
            ui.label()
            .classes("font-mono text-center w-full flex-shrink-0 text-slate-800")
            .style("""
            font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
            font-weight: 600;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
            padding: 4px 8px;
            background: rgba(248, 250, 252, 0.8);
            border-radius: 6px;
            border: 1px solid rgba(226, 232, 240, 0.6);
            font-size: clamp(0.75rem, 3vw, 1.25rem);
            line-height: 1.1;
            word-break: break-all;
            overflow-wrap: break-word;
        """)
        )

    def update_viz(self):
        """Update the visual display"""
        if self.value_element is None:
            return

        value_text = f"{self.value:.{self.precision}f}"
        if self.units:
            value_text += f" {self.units}"
        self.value_element.text = value_text

    def get_status_color(self) -> str:
        """Get color based on value with gradient from blue to green to red"""
        # Calculate percentage of value within range
        percentage = (
            (self.value - self.min) / (self.max - self.min)
            if self.max > self.min
            else 0
        )
        percentage = max(0, min(1, percentage))  # Clamp between 0 and 1

        # Create gradient: blue (0-40%) -> green (40-80%) -> red (80-100%)
        if percentage <= 0.4:  # Blue to green range (0-40%)
            # Interpolate from blue to green
            ratio = percentage / 0.4
            r = int(59 + (16 - 59) * ratio)  # 59 -> 16 (3b -> 10)
            g = int(130 + (185 - 130) * ratio)  # 130 -> 185 (82 -> b9)
            b = int(246 + (129 - 246) * ratio)  # 246 -> 129 (f6 -> 81)
        elif percentage <= 0.8:  # Green to yellow range (40-80%)
            # Interpolate from green to yellow/orange
            ratio = (percentage - 0.4) / 0.4
            r = int(16 + (245 - 16) * ratio)  # 16 -> 245 (10 -> f5)
            g = int(185 + (158 - 185) * ratio)  # 185 -> 158 (b9 -> 9e)
            b = int(129 + (11 - 129) * ratio)  # 129 -> 11 (81 -> 0b)
        else:  # Yellow to red range (80-100%)
            # Interpolate from yellow to red
            ratio = (percentage - 0.8) / 0.2
            r = int(245 + (239 - 245) * ratio)  # 245 -> 239 (f5 -> ef)
            g = int(158 + (68 - 158) * ratio)  # 158 -> 68 (9e -> 44)
            b = int(11 + (68 - 11) * ratio)  # 11 -> 68 (0b -> 44)

        # Handle alarm conditions - override gradient if alarms are set
        if self.alarm_high and self.value >= self.alarm_high:
            return "#ef4444"  # red alarm
        elif self.alarm_low and self.value <= self.alarm_low:
            return "#f59e0b"  # yellow alarm

        return f"#{r:02x}{g:02x}{b:02x}"

    def _animate_value(self) -> None:
        """Animate value changes smoothly (paused when not visible)"""
        # Skip animation if not visible to save resources
        if not self.visible:
            return

        if abs(self.value - self._target_value) < 0.1:
            self.value = self._target_value
            return

        # Calculate animation step with better responsiveness
        diff = self._target_value - self.value
        # Base step on both animation speed and difference magnitude
        base_step = self.animation_speed * 0.15
        magnitude_factor = min(abs(diff) * 0.1, 2.0)  # Scale with difference size
        step = min(abs(diff), base_step * (1 + magnitude_factor))

        if diff < 0:
            step = -step

        self.value += step
        self.update_viz()

    def _update_value(self) -> None:
        """
        Update value from external function if provided.

        To be called periodically by timer.
        """
        if self.update_func is not None:
            try:
                new_value = self.update_func()
                if new_value is not None:
                    self.set_value(new_value)
            except Exception as exc:
                logger.error(f"Error in update function: {exc}", exc_info=True)

    def set_value(self, value: float, immediate: bool = False):
        """
        Set target value with animation.

        :param value: New target value
        :param immediate: If True, set value immediately without animation
        :return: self for method chaining
        """
        if immediate:
            self.value = max(self.min, min(self.max, value))
            self._target_value = self.value
            self.update_viz()
            return self

        self._target_value = max(self.min, min(self.max, value))
        return self

    def set_visibility(self, visible: bool):
        """
        Set visibility state to optimize performance.

        :param visible: Whether the meter should be visible and actively updating
        :return: self for method chaining
        """
        self.visible = visible
        if visible:
            # Resume updates when becoming visible
            self.update_viz()

        if self.visible:
            if self._animation_timer and not self._animation_timer.active:
                self._animation_timer.activate()
            if self._update_timer and not self._update_timer.active:
                self._update_timer.activate()
        else:
            if self._animation_timer and self._animation_timer.active:
                self._animation_timer.deactivate()
            if self._update_timer and self._update_timer.active:
                self._update_timer.deactivate()
        return self


class FlowMeter(Meter):
    """
    Flow meter with visual flow indication.
    Shows animated flow direction and rate.
    """

    def __init__(
        self,
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 100.0,
        units: str = "ft³/sec",
        label: str = "Flow Meter",
        flow_direction: typing.Literal["east", "west", "north", "south"] = "east",
        width: str = "200px",
        height: str = "220px",
        alarm_high: typing.Optional[float] = None,
        alarm_low: typing.Optional[float] = None,
        animation_speed: float = 5.0,
        animation_interval: float = 0.1,
        update_func: typing.Optional[
            typing.Callable[[], typing.Optional[float]]
        ] = None,
        update_interval: float = 1.0,
    ) -> None:
        self.flow_direction = flow_direction
        self.flow_viz = None  # Placeholder for flow visualization element
        super().__init__(
            value=value,
            min_value=min_value,
            max_value=max_value,
            units=units,
            label=label,
            width=width,
            height=height,
            alarm_high=alarm_high,
            alarm_low=alarm_low,
            animation_speed=animation_speed,
            animation_interval=animation_interval,
            update_func=update_func,
            update_interval=update_interval,
        )

    def display(self) -> None:
        """Create flow meter specific display"""
        super().display()

        if self.label_element is not None:
            self.label_element.style(
                "display: flex; align-items: center; justify-content: center; gap: 8px;"
            )

        # Create a sophisticated flow visualization container with responsive scaling
        self.flow_viz = (
            ui.html()
            .classes("flex-1 flex items-center justify-center overflow-hidden")
            .style("""
                max-height: min(80px, 40%);
                min-height: 40px;
                padding: 8px;
                background: linear-gradient(135deg, rgba(59, 130, 246, 0.05) 0%, rgba(16, 185, 129, 0.05) 100%);
                border-radius: 8px;
                border: 1px solid rgba(59, 130, 246, 0.1);
                backdrop-filter: blur(10px);
                width: 100%;
                height: auto;
            """)
        )

    def update_viz(self):
        """Update display including flow visualization"""
        super().update_viz()
        if self.flow_viz is None:
            return

        # Calculate flow intensity based on value
        intensity = (
            (self.value - self.min) / (self.max - self.min)
            if self.max > self.min
            else 0
        )
        self.flow_viz.content = self.get_svg(intensity)

    def get_svg(self, intensity: float = 0.5) -> str:
        """
        Generate animated flow visualization with SVG pipe and flowing particles.

        :param intensity: Flow intensity from 0.0 to 1.0
        :return: SVG string for flow visualization
        """
        if intensity <= 0:
            return """
            <svg width="100%" height="100%" viewBox="0 0 140 80" class="mx-auto" style="max-width: 140px; max-height: 80px;">
                <defs>
                    <linearGradient id="noPipeGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                        <stop offset="0%" style="stop-color:#f1f5f9;stop-opacity:1" />
                        <stop offset="50%" style="stop-color:#e2e8f0;stop-opacity:1" />
                        <stop offset="100%" style="stop-color:#cbd5e1;stop-opacity:1" />
                    </linearGradient>
                </defs>
                <!-- Pipe outline with enhanced styling -->
                <rect x="15" y="25" width="110" height="30" fill="url(#noPipeGrad)" 
                      stroke="#94a3b8" stroke-width="2" rx="15"/>
                <!-- Inner pipe shadow -->
                <rect x="17" y="27" width="106" height="26" fill="none" 
                      stroke="#cbd5e1" stroke-width="1" rx="13"/>
                <!-- No flow indicator -->
                <rect x="50" y="35" width="40" height="10" fill="white" stroke="#94a3b8" rx="5"/>
                <text x="70" y="42" text-anchor="middle" font-size="7" fill="#64748b" font-weight="500">No Flow</text>
            </svg>
            """

        # Calculate flow speed and particle count based on intensity
        # More particles at higher flow rates for better visual representation
        # At 0% flow: 2 particles (minimal)
        # At 50% flow: 6 particles (moderate)
        # At 100% flow: 12 particles (many, dense flow)
        particle_count = max(2, int(intensity * 12))
        # More responsive animation duration that changes dramatically with flow rate
        # At 0% flow: 6 seconds (very slow)
        # At 50% flow: 2 seconds (moderate)
        # At 100% flow: 0.3 seconds (very fast)
        animation_duration = max(0.5, 3 - (intensity * 2.7))  # Range: 0.5s to 3s

        # Get flow direction and setup coordinates
        if self.flow_direction == "west":
            # Flow from east to west
            start_x, end_x = 105, 15
            arrow = "◀"
        elif self.flow_direction == "north":
            # Vertical flow north (show as particles moving north through horizontal pipe)
            start_x, end_x = 15, 105
            arrow = "▲"
        elif self.flow_direction == "south":
            # Vertical flow south (show as particles moving south through horizontal pipe)
            start_x, end_x = 105, 15
            arrow = "▼"
        else:  # east (default)
            # Flow from west to east
            start_x, end_x = 15, 105
            arrow = "▶"

        # Create flowing particles with staggered timing
        particles = ""
        for i in range(particle_count):
            # Stagger the start times so particles follow each other
            delay = i * (animation_duration / particle_count)

            particles += f'''
            <circle r="3" fill="#3b82f6" opacity="0">
                <animate attributeName="cx" 
                         values="{start_x};{end_x}" 
                         dur="{animation_duration}s" 
                         repeatCount="indefinite" 
                         begin="{delay}s"/>
                <animate attributeName="cy" 
                         values="30;30" 
                         dur="{animation_duration}s" 
                         repeatCount="indefinite" 
                         begin="{delay}s"/>
                <!-- Fade in as particle enters pipe, fade out as it exits -->
                <animate attributeName="opacity" 
                         values="0;0.9;0.9;0" 
                         dur="{animation_duration}s" 
                         repeatCount="indefinite" 
                         begin="{delay}s"/>
            </circle>
            '''

        # Use status color for pipe (matches alarm conditions)
        pipe_color = self.get_status_color()

        # Add flow direction arrows along the pipe
        direction_indicators = ""
        for i in range(3):
            x_pos = 30 + (i * 30)
            if self.flow_direction == "left":
                x_pos = 90 - (i * 30)

            direction_indicators += f'''
            <text x="{x_pos}" y="15" text-anchor="middle" font-size="10" fill="{pipe_color}" opacity="0.7">
                <animate attributeName="opacity" 
                         values="0.3;1;0.3" 
                         dur="1s" 
                         repeatCount="indefinite" 
                         begin="{i * 0.3}s"/>
                {arrow}
            </text>
            '''

        return f'''
        <svg width="100%" height="100%" viewBox="0 0 140 80" class="mx-auto" style="max-width: 140px; max-height: 80px;">
            <!-- Enhanced pipe styling with gradients -->
            <defs>
                <linearGradient id="pipeGrad_{id(self)}" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" style="stop-color:{pipe_color};stop-opacity:0.3" />
                    <stop offset="30%" style="stop-color:{pipe_color};stop-opacity:0.6" />
                    <stop offset="70%" style="stop-color:{pipe_color};stop-opacity:0.8" />
                    <stop offset="100%" style="stop-color:{pipe_color};stop-opacity:0.4" />
                </linearGradient>
                <filter id="glow_{id(self)}">
                    <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
                    <feMerge> 
                        <feMergeNode in="coloredBlur"/>
                        <feMergeNode in="SourceGraphic"/>
                    </feMerge>
                </filter>
            </defs>
            
            <!-- Main pipe body with enhanced styling -->
            <rect x="15" y="25" width="110" height="30" fill="url(#pipeGrad_{id(self)})" 
                  stroke="{pipe_color}" stroke-width="3" rx="15" filter="url(#glow_{id(self)})"/>
            
            <!-- Inner pipe detail -->
            <rect x="18" y="28" width="104" height="24" fill="none" 
                  stroke="rgba(255,255,255,0.3)" stroke-width="1" rx="12"/>
            
            <!-- Flow direction indicators with better positioning -->
            {direction_indicators}
            
            <!-- Enhanced flowing particles -->
            {particles}
            
            <!-- Modern flow rate indicator -->
            <rect x="45" y="60" width="50" height="16" fill="rgba(255,255,255,0.95)" 
                  stroke="{pipe_color}" stroke-width="2" rx="8"/>
            <text x="70" y="70" text-anchor="middle" font-size="9" fill="{pipe_color}" 
                  font-weight="600" font-family="monospace">
                {intensity * 100:.0f}% Flow
            </text>
        </svg>
        '''


class PressureGauge(Meter):
    """
    Pressure gauge with circular gauge visualization.
    """

    def __init__(
        self,
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 100.0,
        units: str = "PSI",
        label: str = "Pressure",
        width: str = "200px",
        height: str = "180px",
        alarm_high: typing.Optional[float] = None,
        alarm_low: typing.Optional[float] = None,
        animation_speed: float = 5.0,
        animation_interval: float = 0.1,
        update_func: typing.Optional[
            typing.Callable[[], typing.Optional[float]]
        ] = None,
        update_interval: float = 1.0,
    ) -> None:
        self.gauge_element = None  # Placeholder for gauge element
        super().__init__(
            value=value,
            min_value=min_value,
            max_value=max_value,
            units=units,
            label=label,
            width=width,
            height=height,
            alarm_high=alarm_high,
            alarm_low=alarm_low,
            animation_speed=animation_speed,
            animation_interval=animation_interval,
            update_func=update_func,
            update_interval=update_interval,
        )

    def display(self):
        """Create pressure gauge specific display"""
        super().display()

        if self.label_element is not None:
            self.label_element.style(
                "display: flex; align-items: center; justify-content: center; gap: 8px;"
            )

        # Add enhanced circular gauge container with responsive sizing
        self.gauge_element = (
            ui.html()
            .classes("flex-1 flex items-center justify-center overflow-hidden")
            .style("""
                max-height: min(100px, 50%);
                min-height: 60px;
                padding: 8px;
                background: radial-gradient(circle at center, rgba(59, 130, 246, 0.05) 0%, transparent 70%);
                border-radius: 50%;
                border: 2px solid rgba(59, 130, 246, 0.1);
                width: 100%;
                height: auto;
                aspect-ratio: 1;
            """)
        )

    def update_viz(self):
        """Update display including gauge"""
        super().update_viz()
        if self.gauge_element is None:
            return
        self.gauge_element.content = self.get_svg()

    def get_svg(self) -> str:
        """
        Generate visualization SVG for pressure gauge.

        :return: SVG string for gauge visualization
        """
        percentage = (
            (self.value - self.min) / (self.max - self.min)
            if self.max > self.min
            else 0
        )
        angle = percentage * 180  # Half circle gauge
        color = self.get_status_color()

        # Create enhanced SVG gauge with modern styling
        gauge_svg = f'''
        <svg width="100%" height="100%" viewBox="0 0 120 80" class="mx-auto" style="max-width: 120px; max-height: 80px;">
            <defs>
                <linearGradient id="gaugeGrad_{id(self)}" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style="stop-color:{color};stop-opacity:0.8" />
                    <stop offset="100%" style="stop-color:{color};stop-opacity:1" />
                </linearGradient>
                <filter id="shadow_{id(self)}">
                    <feDropShadow dx="2" dy="2" stdDeviation="3" flood-color="rgba(0,0,0,0.3)"/>
                </filter>
                <filter id="glow_{id(self)}">
                    <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
                    <feMerge> 
                        <feMergeNode in="coloredBlur"/>
                        <feMergeNode in="SourceGraphic"/>
                    </feMerge>
                </filter>
            </defs>
            
            <!-- Outer gauge ring -->
            <circle cx="60" cy="50" r="35" fill="none" stroke="#e2e8f0" stroke-width="8"/>
            
            <!-- Background arc with subtle gradient -->
            <path d="M 25 50 A 35 35 0 0 1 95 50" stroke="#f1f5f9" stroke-width="12" 
                  fill="none" stroke-linecap="round"/>
            
            <!-- Value arc with enhanced styling -->
            <path d="M 25 50 A 35 35 0 0 1 {60 + 35 * math.cos(math.radians(180 - angle))} {50 - 35 * math.sin(math.radians(180 - angle))}" 
                  stroke="url(#gaugeGrad_{id(self)})" stroke-width="10" fill="none" 
                  stroke-linecap="round" filter="url(#glow_{id(self)})"/>
            
            <!-- Gauge ticks -->
            <g stroke="#94a3b8" stroke-width="2">
                <line x1="25" y1="50" x2="30" y2="50"/>
                <line x1="35" y1="25" x2="38" y2="28"/>
                <line x1="60" y1="15" x2="60" y2="20"/>
                <line x1="85" y1="25" x2="82" y2="28"/>
                <line x1="95" y1="50" x2="90" y2="50"/>
            </g>
            
            <!-- Enhanced needle with better styling -->
            <line x1="60" y1="50" x2="{60 + 30 * math.cos(math.radians(180 - angle))}" 
                  y2="{50 - 30 * math.sin(math.radians(180 - angle))}" 
                  stroke="#1e293b" stroke-width="3" stroke-linecap="round" filter="url(#shadow_{id(self)})"/>
            
            <!-- Center hub with gradient -->
            <circle cx="60" cy="50" r="6" fill="url(#gaugeGrad_{id(self)})" 
                    stroke="#1e293b" stroke-width="2" filter="url(#shadow_{id(self)})"/>
            <circle cx="60" cy="50" r="3" fill="rgba(255,255,255,0.8)"/>
            
            <!-- Value display -->
            <rect x="40" y="65" width="40" height="12" fill="rgba(255,255,255,0.95)" 
                  stroke="{color}" stroke-width="1" rx="6"/>
            <text x="60" y="73" text-anchor="middle" font-size="8" fill="{color}" 
                  font-weight="600" font-family="monospace">
                {self.value:.1f} {self.units}
            </text>
        </svg>
        '''
        return gauge_svg


class TemperatureGauge(Meter):
    """
    Temperature gauge with thermometer visualization.
    """

    def __init__(
        self,
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 100.0,
        units: str = "°C",
        label: str = "Temperature",
        width: str = "160px",
        height: str = "240px",
        alarm_high: typing.Optional[float] = None,
        alarm_low: typing.Optional[float] = None,
        animation_speed: float = 5.0,
        animation_interval: float = 0.1,
        update_func: typing.Optional[
            typing.Callable[[], typing.Optional[float]]
        ] = None,
        update_interval: float = 1.0,
    ):
        self.thermo_element = None
        super().__init__(
            value=value,
            min_value=min_value,
            max_value=max_value,
            units=units,
            label=label,
            width=width,
            height=height,
            alarm_high=alarm_high,
            alarm_low=alarm_low,
            animation_speed=animation_speed,
            animation_interval=animation_interval,
            update_func=update_func,
            update_interval=update_interval,
        )

    def display(self):
        """Create temperature gauge specific display"""
        super().display()

        if self.label_element is not None:
            self.label_element.style(
                "display: flex; align-items: center; justify-content: center; gap: 8px;"
            )

        # Add enhanced thermometer visualization container with responsive sizing
        self.thermo_element = (
            ui.html()
            .classes("flex-1 flex items-center justify-center overflow-hidden")
            .style("""
                max-height: min(100px, 60%);
                min-height: 60px;
                padding: 8px;
                background: linear-gradient(180deg, rgba(239, 68, 68, 0.05) 0%, rgba(59, 130, 246, 0.05) 100%);
                border-radius: 8px;
                border: 2px solid rgba(148, 163, 184, 0.2);
                width: 100%;
                height: auto;
            """)
        )

    def update_viz(self):
        """Update display including thermometer"""
        super().update_viz()
        if self.thermo_element is None:
            return
        self.thermo_element.content = self.get_svg()

    def get_svg(self) -> str:
        """
        Generate visualization SVG for temperature thermometer.

        :return: SVG string for thermometer visualization
        """
        # Calculate percentage
        percentage = (
            (self.value - self.min) / (self.max - self.min)
            if self.max > self.min
            else 0
        )
        color = self.get_status_color()

        # Create enhanced thermometer SVG with modern styling
        thermo_svg = f'''
        <svg width="100%" height="100%" viewBox="0 0 60 100" class="mx-auto" style="max-width: 60px; max-height: 100px;">
            <defs>
                <linearGradient id="thermoGrad_{id(self)}" x1="0%" y1="100%" x2="0%" y2="0%">
                    <stop offset="0%" style="stop-color:{color};stop-opacity:1" />
                    <stop offset="50%" style="stop-color:{color};stop-opacity:0.8" />
                    <stop offset="100%" style="stop-color:{color};stop-opacity:0.6" />
                </linearGradient>
                <linearGradient id="tubeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" style="stop-color:#f8fafc;stop-opacity:1" />
                    <stop offset="50%" style="stop-color:#ffffff;stop-opacity:1" />
                    <stop offset="100%" style="stop-color:#f1f5f9;stop-opacity:1" />
                </linearGradient>
                <filter id="shadow_{id(self)}">
                    <feDropShadow dx="1" dy="2" stdDeviation="2" flood-color="rgba(0,0,0,0.2)"/>
                </filter>
            </defs>
            
            <!-- Thermometer outer tube with enhanced styling -->
            <rect x="22" y="15" width="16" height="60" fill="url(#tubeGrad)" 
                  stroke="#cbd5e1" stroke-width="2" rx="8" filter="url(#shadow_{id(self)})"/>
            
            <!-- Inner tube (hollow part) -->
            <rect x="24" y="17" width="12" height="56" fill="#f8fafc" 
                  stroke="#e2e8f0" stroke-width="1" rx="6"/>
            
            <!-- Mercury/fluid with gradient -->
            <rect x="24" y="{73 - 56 * percentage}" width="12" height="{56 * percentage}" 
                  fill="url(#thermoGrad_{id(self)})" rx="6"/>
            
            <!-- Enhanced bulb with gradient -->
            <circle cx="30" cy="80" r="12" fill="url(#thermoGrad_{id(self)})" 
                    stroke="#64748b" stroke-width="2" filter="url(#shadow_{id(self)})"/>
            <circle cx="30" cy="80" r="8" fill="{color}" opacity="0.9"/>
            <circle cx="30" cy="80" r="4" fill="rgba(255,255,255,0.3)"/>
            
            <!-- Scale marks with better styling -->
            <g stroke="#64748b" stroke-width="1.5" opacity="0.8">
                <line x1="12" y1="20" x2="20" y2="20"/>
                <line x1="15" y1="30" x2="20" y2="30"/>
                <line x1="12" y1="40" x2="20" y2="40"/>
                <line x1="15" y1="50" x2="20" y2="50"/>
                <line x1="12" y1="60" x2="20" y2="60"/>
                <line x1="15" y1="70" x2="20" y2="70"/>
            </g>
            
            <!-- Scale labels -->
            <g font-size="6" fill="#64748b" font-family="monospace" font-weight="500">
                <text x="10" y="22" text-anchor="end">{self.max:.0f}</text>
                <text x="10" y="42" text-anchor="end">{(self.max + self.min) / 2:.0f}</text>
                <text x="10" y="62" text-anchor="end">{self.min:.0f}</text>
            </g>
            
            <!-- Value display -->
            <rect x="42" y="45" width="16" height="10" fill="rgba(255,255,255,0.95)" 
                  stroke="{color}" stroke-width="1" rx="5"/>
            <text x="50" y="51" text-anchor="middle" font-size="6" fill="{color}" 
                  font-weight="600" font-family="monospace">
                {self.value:.1f}°
            </text>
        </svg>
        '''
        return thermo_svg


class Regulator:
    """
    Regulator component for setting and controlling values.

    This is the opposite of a Meter - instead of displaying values, it allows users
    to set them using both a slider and a number input with enhanced styling.
    """

    def __init__(
        self,
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 100.0,
        step: float = 0.1,
        units: str = "",
        label: str = "Regulator",
        width: str = "280px",
        height: str = "220px",
        setter_func: typing.Optional[typing.Callable[[float], None]] = None,
        alarm_high: typing.Optional[float] = None,
        alarm_low: typing.Optional[float] = None,
        precision: int = 3,
    ) -> None:
        """
        Initialize the regulator.

        :param value: Initial value
        :param min_value: Minimum allowed value
        :param max_value: Maximum allowed value
        :param step: Step size for the slider
        :param units: Units to display
        :param label: Label for the regulator
        :param width: Width of the regulator
        :param height: Height of the regulator
        :param setter_func: Function to call when value changes
        :param alarm_high: High alarm threshold for color coding
        :param alarm_low: Low alarm threshold for color coding
        :param precision: Number of decimal places to display
        """
        self.value = value
        self.min = min_value
        self.max = max_value
        self.step = step
        self.units = units
        self.label = label
        self.width = width
        self.height = height
        self.setter_func = setter_func
        self.alarm_high = alarm_high
        self.alarm_low = alarm_low
        self.precision = precision

        # UI elements
        self.container = None
        self.label_element = None
        self.slider_element = None
        self.input_element = None
        self.status_indicator = None

    def show(
        self,
        width: typing.Optional[str] = None,
        height: typing.Optional[str] = None,
        label: typing.Optional[str] = None,
        show_label: bool = True,
    ) -> ui.card:
        """
        Display the regulator as a UI component.

        :param width: Width of the regulator (overrides default if provided)
        :param height: Height of the regulator (overrides default if provided)
        :param label: Label for the regulator (overrides default if provided)
        :param show_label: Whether to display the label
        :return: UI card element containing the regulator
        """
        display_width = width or self.width
        display_height = height or self.height
        display_label = label or self.label

        # Create the UI container
        self.container = (
            ui.card()
            .classes("p-2 text-center flex flex-col items-center overflow-auto")
            .style(
                f"""
                width: {display_width}; 
                height: {display_height}; 
                background: linear-gradient(145deg, #f8fafc 0%, #ffffff 100%);
                border: 2px solid #e2e8f0;
                border-radius: 16px;
                box-shadow: 
                    0 10px 25px -5px rgba(0, 0, 0, 0.1),
                    0 8px 10px -6px rgba(0, 0, 0, 0.1),
                    inset 0 1px 0 rgba(255, 255, 255, 0.6);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                scrollbar-width: none;
                -ms-overflow-style: none;
                display: flex;
                flex-direction: column;
                justify-content: space-evenly;
                gap: 0.25rem;
                """
            )
        )

        # Add hover effects for Regulator
        def on_mouseenter():
            if self.container:
                self.container.style(
                    add="""
                    transform: translateY(-2px);
                    box-shadow: 
                        0 20px 40px -10px rgba(0, 0, 0, 0.15),
                        0 15px 20px -10px rgba(0, 0, 0, 0.1),
                        inset 0 1px 0 rgba(255, 255, 255, 0.6);
                """
                )

        def on_mouseleave():
            if self.container:
                self.container.style(
                    add="""
                    transform: translateY(0px);
                    box-shadow: 
                        0 10px 25px -5px rgba(0, 0, 0, 0.1),
                        0 8px 10px -6px rgba(0, 0, 0, 0.1),
                        inset 0 1px 0 rgba(255, 255, 255, 0.6);
                """
                )

        self.container.on("mouseenter", on_mouseenter)
        self.container.on("mouseleave", on_mouseleave)

        with self.container:
            if show_label:
                self.label = display_label
            self.display()

        return self.container

    def display(self):
        """Create the regulator display with slider and input controls."""
        # Label with status indicator
        if self.label:
            with ui.row().classes("items-center justify-center w-full mb-1"):
                self.label_element = (
                    ui.label(self.label)
                    .classes("font-bold text-center text-slate-700")
                    .style("""
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                    letter-spacing: -0.025em;
                    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
                    font-size: clamp(0.5rem, 2.5vw, 1rem);
                    line-height: 1.1;
                """)
                )

                # Status indicator (colored dot)
                self.status_indicator = ui.html(
                    f'<div class="w-2 h-2 rounded-full ml-1" style="background-color: {self.get_status_color()};"></div>'
                )

        value = max(self.min, min(self.max, self.value))
        # Current value display with enhanced styling
        value_text = f"{value:.{self.precision}f}"
        if self.units:
            value_text += f" {self.units}"

        current_value_display = (
            ui.label(value_text)
            .classes("font-mono text-center w-full mb-1 text-slate-800")
            .style(f"""
            font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
            font-weight: 600;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
            padding: 4px 8px;
            background: rgba(248, 250, 252, 0.8);
            border-radius: 6px;
            border: 1px solid rgba(226, 232, 240, 0.6);
            color: {self.get_status_color()};
            font-size: clamp(0.75rem, 3vw, 1.125rem);
            line-height: 1.1;
            word-break: break-all;
            overflow-wrap: break-word;
        """)
        )

        # Slider with enhanced styling
        self.slider_element = (
            ui.slider(min=self.min, max=self.max, value=value, step=self.step)
            .props("label-always color=primary")
            .classes("w-full mb-1")
            .style("""
                margin: 4px 0;
            """)
        )

        # Number input with enhanced styling
        format_str = f"%.{self.precision}f"
        suffix = f" {self.units}" if self.units else ""

        self.input_element = (
            ui.number(
                label="Set Value",
                value=value,
                min=self.min,
                max=self.max,
                step=self.step,
                format=format_str,
                suffix=suffix,
            )
            .classes("w-full")
            .style("""
                font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
            """)
        )

        # Range display with responsive sizing
        ui.label(
            f"Range: {self.min:.{self.precision}f} - {self.max:.{self.precision}f} {self.units}"
        ).classes("text-gray-500 mt-1").style("""
            font-size: clamp(0.5rem, 1.5vw, 0.625rem);
            line-height: 1.1;
        """)

        # Bind events for synchronization
        def update_value(new_value):
            """Update all components when value changes."""
            if new_value is None:
                return

            # Clamp value to valid range
            new_value = max(self.min, min(self.max, float(new_value)))
            self.value = new_value

            # Update all UI elements
            if self.slider_element:
                self.slider_element.value = new_value
            if self.input_element:
                self.input_element.value = new_value

            # Update value display
            value_text = f"{new_value:.{self.precision}f}"
            if self.units:
                value_text += f" {self.units}"
            current_value_display.text = value_text

            # Update status color
            new_color = self.get_status_color()
            current_value_display.style(f"""
                font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
                font-weight: 600;
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
                padding: 8px 12px;
                background: rgba(248, 250, 252, 0.8);
                border-radius: 8px;
                border: 1px solid rgba(226, 232, 240, 0.6);
                color: {new_color};
            """)

            if self.status_indicator:
                self.status_indicator.content = f'<div class="w-2 h-2 rounded-full ml-1" style="background-color: {new_color};"></div>'

            # Call setter function if provided
            if self.setter_func:
                try:
                    self.setter_func(new_value)
                except Exception as e:
                    logger.error(
                        f"Error in regulator setter function: {e}", exc_info=True
                    )

        # Connect events
        self.slider_element.on("update:model-value", lambda e: update_value(e.args))
        self.input_element.on("update:model-value", lambda e: update_value(e.args))

    def get_status_color(self) -> str:
        """Get color based on value and alarm thresholds."""
        # Check alarm conditions first
        if self.alarm_high and self.value >= self.alarm_high:
            return "#ef4444"  # Red for high alarm
        elif self.alarm_low and self.value <= self.alarm_low:
            return "#f59e0b"  # Orange for low alarm

        # Calculate percentage for gradient
        if self.max > self.min:
            percentage = (self.value - self.min) / (self.max - self.min)
        else:
            percentage = 0
        percentage = max(0, min(1, percentage))

        # Create gradient: blue (0-40%) -> green (40-80%) -> orange (80-100%)
        if percentage <= 0.4:
            # Blue to green
            ratio = percentage / 0.4
            r = int(59 + (16 - 59) * ratio)  # 59 -> 16
            g = int(130 + (185 - 130) * ratio)  # 130 -> 185
            b = int(246 + (129 - 246) * ratio)  # 246 -> 129
        elif percentage <= 0.8:
            # Green to orange
            ratio = (percentage - 0.4) / 0.4
            r = int(16 + (245 - 16) * ratio)  # 16 -> 245
            g = int(185 + (158 - 185) * ratio)  # 185 -> 158
            b = int(129 + (11 - 129) * ratio)  # 129 -> 11
        else:
            # Orange to red-orange
            ratio = (percentage - 0.8) / 0.2
            r = int(245 + (239 - 245) * ratio)  # 245 -> 239
            g = int(158 + (98 - 158) * ratio)  # 158 -> 98
            b = int(11 + (11 - 11) * ratio)  # 11 -> 11

        return f"#{r:02x}{g:02x}{b:02x}"

    def set_value(self, value: float):
        """
        Programmatically set the regulator value.

        :param value: New value to set
        """
        value = max(self.min, min(self.max, float(value)))
        self.value = value

        # Update UI elements if they exist
        if self.slider_element:
            self.slider_element.value = value
        if self.input_element:
            self.input_element.value = value

    def get_value(self) -> float:
        """Get the current regulator value."""
        return self.value


class PipeDirection(str, Enum):
    """Enumeration for pipe flow directions."""

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


class PipelineConnectionError(Exception):
    """Exception raised when pipes in a pipeline are not properly connected."""

    pass


def physical_to_display_unit(
    physical: PlainQuantity[float],
    scale_factor: float = 0.1,
    min_display_unit: typing.Optional[float] = None,
    max_display_unit: typing.Optional[float] = None,
) -> float:
    """
    Convert a physical quantity to a display unit based on the scale factor.

    :param physical: The physical quantity to convert
    :param scale_factor: The scale factor for conversion (default: 0.1) (pixels per millimeter)
    :param min_display_unit: Minimum display unit value (default: None)
    :param max_display_unit: Maximum display unit value (default: 100.0)
    :return: The converted display unit value
    """
    display_value = physical.to("mm").magnitude * scale_factor
    if min_display_unit is not None:
        display_value = max(display_value, min_display_unit)
    if max_display_unit is not None:
        display_value = min(display_value, max_display_unit)
    return display_value


def calculate_flow_intensity(
    flow_rate: PlainQuantity[float],
    max_flow_rate: PlainQuantity[float] = Quantity(10.0, "ft^3/s"),
) -> float:
    """
    Calculate flow intensity normalized to 0-1 range.

    :param flow_rate: Flow rate as Quantity
    :param max_flow_rate: Maximum expected flow rate for normalization as Quantity
    :return: Intensity value between 0.0 and 1.0
    """
    flow_magnitude = flow_rate.to("ft^3/s").magnitude
    max_flow_magnitude = max_flow_rate.to("ft^3/s").magnitude
    return min(flow_magnitude / max_flow_magnitude, 1.0)


def get_flow_color(intensity: float) -> str:
    """
    Get color based on flow intensity.

    :param intensity: Flow intensity from 0.0 to 1.0
    :return: Hex color string for the flow visualization
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


def check_directions_compatibility(*directions: PipeDirection) -> bool:
    """
    Check if two pipe directions are compatible for connection.

    Pipes with opposing flow directions cannot be connected:
    - North flow cannot connect to South flow
    - East flow cannot connect to West flow

    :param directions: Sequence of `PipeDirection` to check
    :return: True if directions are compatible, False if opposing
    """
    # Define opposing direction pairs
    opposing_pairs = [
        (PipeDirection.NORTH, PipeDirection.SOUTH),
        (PipeDirection.SOUTH, PipeDirection.NORTH),
        (PipeDirection.EAST, PipeDirection.WEST),
        (PipeDirection.WEST, PipeDirection.EAST),
    ]

    if len(directions) == 1:
        return True

    def check_unique(dir1: PipeDirection, dir2: PipeDirection) -> bool:
        return (dir1 == dir2) or (dir1, dir2) not in opposing_pairs

    for i in range(len(directions)):
        for j in range(i + 1, len(directions)):
            if not check_unique(directions[i], directions[j]):
                return False
    return True


class Pipe:
    """Pipe component for flow system visualization."""

    def __init__(
        self,
        properties: PipeProperties,
        fluid: typing.Optional[Fluid] = None,
        direction: typing.Union[PipeDirection, str] = PipeDirection.EAST,
        name: typing.Optional[str] = None,
        scale_factor: float = 0.1,
        max_flow_rate: PlainQuantity[float] = Quantity(10.0, "ft^3/s"),
    ) -> None:
        """
        Initialize a Pipe component.

        :param properties: PipeProperties instance with physical characteristics
        :param direction: PipeDirection enum indicating flow direction
        :param name: Optional name for the pipe
        :param scale_factor: Display scale factor for converting physical units to pixels (pixels per millimeter).
            Example: A scale_factor of 0.1 means 1 pixel represents 10 mm (1 cm).
        :param max_flow_rate: Maximum expected flow rate for intensity normalization
        """
        self.name = name or f"Pipe-{id(self)}"
        self.direction = PipeDirection(direction)
        if self.direction == PipeDirection.NORTH:
            self._properties = evolve(
                properties, elevation_difference=properties.length
            )
        elif self.direction == PipeDirection.SOUTH:
            self._properties = evolve(
                properties, elevation_difference=-properties.length
            )
        else:
            self._properties = evolve(
                properties, elevation_difference=0.0 * properties.length.units
            )
        self._fluid = evolve(fluid) if fluid else None
        self.scale_factor = scale_factor
        self.flow_rate = Quantity(0.0, "ft^3/s")
        self.max_flow_rate = max_flow_rate
        self.pipe_viz = None  # Placeholder for pipe visualization element
        self.update_flow_rate()

    @property
    def properties(self) -> PipeProperties:
        """Pipe properties."""
        return self._properties

    def set_properties(self, new_properties: PipeProperties, update: bool = True):
        """
        Update pipe properties and optionally recalculate flow rate.

        :param new_properties: New PipeProperties instance to set
        :param update: Whether to update flow rate after changing properties
        :return: self or updated Pipe instance
        """
        self._properties = evolve(new_properties)
        if update:
            return self.update_flow_rate()
        return self

    @property
    def fluid(self) -> typing.Optional[Fluid]:
        """Get fluid properties."""
        return self._fluid

    def set_fluid(self, new_fluid: Fluid, update: bool = True):
        """
        Update pipe fluid and optionally recalculate flow rate.

        :param new_fluid: New Fluid instance to set
        :param update: Whether to update flow rate after changing fluid
        :return: self or updated Pipe instance
        """
        self._fluid = evolve(new_fluid)
        if update:
            return self.update_flow_rate()
        return self

    def set_fluid_temperature(
        self, temperature: PlainQuantity[float], update: bool = True
    ):
        """
        Update pipe fluid temperature and optionally recalculate flow rate.

        :param temperature: New temperature to set
        :param update: Whether to update flow rate after changing temperature
        :return: self or updated Pipe instance
        """
        if self.fluid is not None:
            self._fluid = evolve(self.fluid, temperature=temperature)
        if update:
            return self.update_flow_rate()
        return self

    @property
    def flow_equation(self) -> typing.Optional[FlowEquation]:
        """Appropriate pipe flow equation based on pipe and fluid properties."""
        if self.fluid is None:
            return None
        return determine_pipe_flow_equation(
            pressure_drop=self.properties.pressure_drop,
            upstream_pressure=self.properties.upstream_pressure,
            internal_diameter=self.properties.internal_diameter,
            length=self.properties.length,
            fluid_phase=self.fluid.phase,
            fluid_specific_gravity=self.fluid.specific_gravity,
        )

    @property
    def mass_rate(self) -> PlainQuantity[float]:
        """Mass flow rate in pipe in (lb/s) based on current flow rate and fluid density."""
        if self.fluid is None:
            return Quantity(0.0, "lb/s")
        density = self.fluid.density.to("lb/ft^3").magnitude
        volumetric_rate = self.flow_rate.to("ft^3/s").magnitude
        return Quantity(density * volumetric_rate, "lb/s")

    @property
    def flow_velocity(self) -> PlainQuantity[float]:
        """Flow velocity of the fluid in the pipe in (ft/s) based on current flow rate and pipe cross-sectional area."""
        area = self.properties.cross_sectional_area.to("ft^2").magnitude
        if area <= 0:
            return Quantity(0.0, "ft/s")
        volumetric_rate = self.flow_rate.to("ft^3/s").magnitude
        return Quantity(volumetric_rate / area, "ft/s")

    def show(
        self,
        width: str = "400px",
        height: str = "200px",
        label: typing.Optional[str] = None,
        show_label: bool = True,
    ) -> Html:
        """
        Render the pipe visualization as an HTML element.

        :param label: Optional label for the pipe section
        :param width: Width of the SVG container
        :param height: Height of the SVG container
        :param show_label: Whether to display the label above the pipe
        :return: Html element containing the SVG representation of the pipe
        """
        container = (
            ui.html()
            .classes("flex flex-col items-center justify-center")
            .style(f"width: {width}; height: {height};")
        )

        with container:
            if show_label and label:
                ui.label(label).classes("text-lg font-semibold mb-2 text-center")

            # Create the SVG visualization
            self.pipe_viz = ui.html(self.get_svg()).classes("w-full h-full")
        return container

    def update_viz(self):
        """
        Update the pipe visualization with current properties and flow rate.

        This method regenerates the SVG content based on the current state.
        """
        if self.pipe_viz is not None:
            self.pipe_viz.content = self.get_svg()
        return self

    def get_svg(self) -> str:
        """
        Generate the SVG content for the pipe based on its direction.

        :return: SVG string representing the pipe visualization
        """
        if self.direction in [PipeDirection.NORTH, PipeDirection.SOUTH]:
            return self.build_vertical_pipe_svg()
        return self.build_horizontal_pipe_svg()

    def build_horizontal_pipe_svg(self) -> str:
        """
        Create horizontal pipe SVG with flow animation.

        :return: SVG string for horizontal pipe visualization
        """
        # Determine flow direction
        if self.direction == PipeDirection.WEST:
            start_x, end_x = 350, 50
            arrow = "◀"
        else:  # EAST (default)
            start_x, end_x = 50, 350
            arrow = "▶"

        # Convert physical diameter to display units with reasonable bounds
        pipe_diameter_in_pixels = physical_to_display_unit(
            self.properties.internal_diameter,
            self.scale_factor,
            min_display_unit=10,
            max_display_unit=80,
        )
        pipe_y = 50 - pipe_diameter_in_pixels / 2

        # Calculate intensity and color from flow rate
        intensity = calculate_flow_intensity(self.flow_rate, self.max_flow_rate)
        color = get_flow_color(intensity)

        # Create flow particles if there's flow
        particles = ""
        if intensity > 0:
            particle_count = max(3, int(intensity * 10))
            animation_duration = max(0.8, 3.0 - intensity * 2.0)

            for i in range(particle_count):
                delay = i * (animation_duration / particle_count)
                particles += f'''
                <circle r="3" fill="{color}" opacity="0">
                    <animate attributeName="cx" 
                             values="{start_x};{end_x}" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                    <animate attributeName="cy" 
                             values="50;50" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                    <animate attributeName="opacity" 
                             values="0;0.9;0.9;0" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                </circle>
                '''

        # Flow direction indicators
        direction_indicators = ""
        if intensity > 0:
            for i in range(5):
                x_pos = 80 + (i * 50)
                if self.direction == PipeDirection.WEST:
                    x_pos = 320 - (i * 50)

                direction_indicators += f'''
                <text x="{x_pos}" y="30" text-anchor="middle" font-size="14" fill="{color}" opacity="0.7">
                    <animate attributeName="opacity" 
                             values="0.3;1;0.3" 
                             dur="2s" 
                             repeatCount="indefinite" 
                             begin="{i * 0.4}s"/>
                    {arrow}
                </text>
                '''

        return f'''
        <svg width="100%" height="100" viewBox="0 0 400 100" class="mx-auto">
            <defs>
                <linearGradient id="pipeGrad_{id(self)}" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" style="stop-color:{color};stop-opacity:0.3" />
                    <stop offset="50%" style="stop-color:{color};stop-opacity:0.6" />
                    <stop offset="100%" style="stop-color:{color};stop-opacity:0.3" />
                </linearGradient>
            </defs>
            
            <!-- Pipe body -->
            <rect x="45" y="{pipe_y}" width="310" height="{pipe_diameter_in_pixels}" 
                  fill="url(#pipeGrad_{id(self)})" stroke="{color}" stroke-width="2" rx="4"/>
            
            <!-- Pipe flanges/connections -->
            <rect x="40" y="{pipe_y - 3}" width="10" height="{pipe_diameter_in_pixels + 6}" fill="#6b7280" rx="2"/>
            <rect x="350" y="{pipe_y - 3}" width="10" height="{pipe_diameter_in_pixels + 6}" fill="#6b7280" rx="2"/>
            
            <!-- Connection points -->
            <circle cx="45" cy="50" r="4" fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            <circle cx="355" cy="50" r="4" fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            
            <!-- Flow direction indicators -->
            {direction_indicators}
            
            <!-- Flow particles -->
            {particles}
        </svg>
        '''

    def build_vertical_pipe_svg(self) -> str:
        """
        Create vertical pipe SVG with flow animation.

        :return: SVG string for vertical pipe visualization
        """
        # Determine flow direction
        if self.direction == PipeDirection.NORTH:
            start_y, end_y = 80, 20
        else:  # SOUTH (default)
            start_y, end_y = 20, 80

        # Calculate pipe thickness with reasonable bounds
        pipe_diameter_in_pixels = physical_to_display_unit(
            self.properties.internal_diameter,
            self.scale_factor,
            min_display_unit=10,
            max_display_unit=80,
        )
        pipe_x = 200 - pipe_diameter_in_pixels / 2

        # Calculate intensity and color from flow rate
        intensity = calculate_flow_intensity(self.flow_rate, self.max_flow_rate)
        color = get_flow_color(intensity)

        # Create flow particles
        particles = ""
        if intensity > 0:
            particle_count = max(3, int(intensity * 8))
            animation_duration = max(0.8, 3.0 - intensity * 2.0)

            for i in range(particle_count):
                delay = i * (animation_duration / particle_count)
                particles += f'''
                <circle r="3" fill="{color}" opacity="0">
                    <animate attributeName="cx" 
                             values="200;200" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                    <animate attributeName="cy" 
                             values="{start_y};{end_y}" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                    <animate attributeName="opacity" 
                             values="0;0.9;0.9;0" 
                             dur="{animation_duration}s" 
                             repeatCount="indefinite" 
                             begin="{delay}s"/>
                </circle>
                '''

        # Flow direction indicators
        direction_indicators = ""
        if intensity > 0:
            # Add 3 directional arrows along the pipe
            for i in range(3):
                y_pos = 25 + i * 20  # Position arrows vertically along the pipe
                # Choose arrow based on flow direction
                arrow = "▲" if self.direction == PipeDirection.NORTH else "▼"
                direction_indicators += f'''
                <text x="220" y="{y_pos}" text-anchor="middle" font-size="10" fill="{color}" opacity="0.7">
                    <animate attributeName="opacity" values="0.3;1;0.3" dur="1.5s" repeatCount="indefinite" begin="{i * 0.3}s"/>
                    {arrow}
                </text>
                '''

        return f'''
        <svg width="100%" height="100" viewBox="0 0 400 100" class="mx-auto">
            <defs>
                <linearGradient id="pipeGradV_{id(self)}" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" style="stop-color:{color};stop-opacity:0.3" />
                    <stop offset="50%" style="stop-color:{color};stop-opacity:0.6" />
                    <stop offset="100%" style="stop-color:{color};stop-opacity:0.3" />
                </linearGradient>
            </defs>
            
            <!-- Pipe body -->
            <rect x="{pipe_x}" y="15" width="{pipe_diameter_in_pixels}" height="70" 
                  fill="url(#pipeGradV_{id(self)})" stroke="{color}" stroke-width="2" rx="4"/>
            
            <!-- Pipe flanges/connections -->
            <rect x="{pipe_x - 3}" y="10" width="{pipe_diameter_in_pixels + 6}" height="10" fill="#6b7280" rx="2"/>
            <rect x="{pipe_x - 3}" y="80" width="{pipe_diameter_in_pixels + 6}" height="10" fill="#6b7280" rx="2"/>
            
            <!-- Connection points -->
            <circle cx="200" cy="15" r="4" fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            <circle cx="200" cy="85" r="4" fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
            
            <!-- Flow direction indicators -->
            {direction_indicators}
            
            <!-- Flow particles -->
            {particles}
        </svg>
        '''

    def set_flow_rate(self, flow_rate: typing.Union[PlainQuantity[float], float]):
        """
        Set the flow rate and update calculations.

        :param flow_rate: Flow rate as Quantity or float (assumed ft^3/s if float)
        :return: self for method chaining
        """
        if isinstance(flow_rate, Quantity):
            flow_rate_q = flow_rate.to("ft^3/s")
        else:
            flow_rate_q = Quantity(flow_rate, "ft^3/s")

        flow_rate_q = Quantity(max(0, flow_rate_q.magnitude), flow_rate_q.units).to(
            "ft^3/s"
        )
        if flow_rate_q.magnitude > 0 and self.fluid is None:
            raise ValueError(
                "Cannot set a positive flow rate without defining fluid properties. Flow cannot occur in an empty pipe."
            )
        self.flow_rate = flow_rate_q
        return self

    def update_flow_rate(self):
        """Update flow rate based on current properties and fluid."""
        flow_equation = self.flow_equation
        fluid = self.fluid
        if flow_equation is None or fluid is None:
            return self.set_flow_rate(0.0)

        # Compute Reynolds number
        reynolds_number = compute_reynolds_number(
            current_flow_rate=self.flow_rate,
            pipe_internal_diameter=self.properties.internal_diameter,
            fluid_density=fluid.density,
            fluid_dynamic_viscosity=fluid.viscosity,
        )
        # Calculate flow rate using the appropriate equation
        flow_rate = compute_pipe_flow_rate(
            properties=self.properties,
            fluid=fluid,
            reynolds_number=reynolds_number or 2000,  # Default to laminar if undefined
            flow_equation=flow_equation,
        )
        return self.set_flow_rate(flow_rate)

    def set_upstream_pressure(
        self,
        pressure: typing.Union[PlainQuantity[float], float],
        check: bool = True,
        update: bool = True,
    ):
        """
        Set upstream pressure and update flow rate.

        :param pressure: Upstream pressure as Quantity or float (assumed psi if float)
        :param check: Whether to check pressure constraints (default is True)
        :param update: Whether to update flow rate after setting pressure (default is True)
        :return: self for method chaining
        """
        if isinstance(pressure, Quantity):
            if pressure.magnitude < 0:
                raise ValueError("Upstream pressure cannot be negative.")
            pressure_q = pressure.to("psi")
        else:
            if pressure < 0:
                raise ValueError("Upstream pressure cannot be negative.")
            pressure_q = Quantity(pressure, "psi")

        if check and (self.properties.downstream_pressure > pressure_q):
            raise ValueError(
                "Upstream pressure cannot be less than downstream pressure. Flow cannot occur against the pressure gradient."
            )
        self.properties.upstream_pressure = pressure_q
        if update:
            return self.update_flow_rate()
        return self

    def set_downstream_pressure(
        self,
        pressure: typing.Union[PlainQuantity[float], float],
        check: bool = True,
        update: bool = True,
    ):
        """
        Set downstream pressure and update flow rate.

        :param pressure: Downstream pressure as Quantity or float (assumed psi if float)
        :param check: Whether to check pressure constraints (default is True)
        :param update: Whether to update flow rate after setting pressure (default is True)
        :return: self for method chaining
        """
        if isinstance(pressure, Quantity):
            if pressure.magnitude < 0:
                raise ValueError("Downstream pressure cannot be negative.")
            pressure_q = pressure.to("psi")
        else:
            if pressure < 0:
                raise ValueError("Downstream pressure cannot be negative.")
            pressure_q = Quantity(pressure, "psi")

        if check and (self.properties.upstream_pressure < pressure_q):
            raise ValueError(
                "Downstream pressure cannot exceed upstream pressure. Flow cannot occur against the pressure gradient."
            )
        self.properties.downstream_pressure = pressure_q
        if update:
            return self.update_flow_rate()
        return self

    def get_pipeline_type(self) -> typing.Type["Pipeline"]:
        """
        Get the pipeline type for this pipe.

        :return: Pipeline class type
        """
        return Pipeline

    def connect(
        self,
        other: "Pipe",
        pipeline_type: typing.Optional[typing.Type["Pipeline"]] = None,
        **kwargs: typing.Any,
    ):
        """
        Connect this pipe to another pipe.

        :param other: Another Pipe instance to connect to
        :param pipeline_type: Optional Pipeline subclass to use for the connection
        :param kwargs: Additional keyword arguments to pass to the pipeline constructor
        :return: Pipeline containing both pipes
        :raises TypeError: If other is not a Pipe instance
        :raises PipelineConnectionError: If pipes cannot be connected
        """
        if not isinstance(other, Pipe):
            raise TypeError("Can only connect to another Pipe instance")

        # Validate flow direction compatibility
        if not check_directions_compatibility(self.direction, other.direction):
            raise PipelineConnectionError(
                f"Cannot connect pipes with opposing flow directions: "
                f"{self.direction.value} to {other.direction.value}. "
                f"Pipes flowing in opposite directions cannot be connected."
            )

        pipeline_cls = pipeline_type or self.get_pipeline_type()
        kwargs.setdefault("scale_factor", self.scale_factor)
        kwargs.setdefault("max_flow_rate", self.max_flow_rate)
        return pipeline_cls([self, other], **kwargs)

    def __and__(self, other: "Pipe"):
        """
        Overload the pipe connection operator.

        :param other: Another Pipe instance to connect using & operator
        :return: Pipeline containing both connected pipes
        """
        return self.connect(other)

    __add__ = __and__


def build_straight_pipe_connector_svg(
    pipe1: Pipe,
    pipe2: Pipe,
    connector_length: PlainQuantity[float],
    flow_rate: typing.Union[PlainQuantity[float], float, None] = None,
) -> str:
    """
    Build a straight connector SVG between two pipes with diameter transition.

    :param pipe1: First pipe (upstream)
    :param pipe2: Second pipe (downstream)
    :param connector_length: Length of connector in physical units (e.g., mm, cm)
    :param flow_rate: Optional flow rate for animation
    :return: SVG string for the straight connector
    """
    # Scale diameters for display (use average scale factor)
    scale_factor = (pipe1.scale_factor + pipe2.scale_factor) / 2
    diameter1_in_pixels = physical_to_display_unit(
        pipe1.properties.internal_diameter, scale_factor, max_display_unit=200
    )
    diameter2_in_pixels = physical_to_display_unit(
        pipe2.properties.internal_diameter, scale_factor, max_display_unit=200
    )
    length = physical_to_display_unit(
        connector_length, scale_factor, min_display_unit=40, max_display_unit=300
    )

    # Calculate flow properties
    flow_rate = pipe1.flow_rate if flow_rate is None else flow_rate
    if not isinstance(flow_rate, Quantity):
        flow_rate = Quantity(flow_rate, "ft^3/s")

    intensity = calculate_flow_intensity(flow_rate, pipe1.max_flow_rate)
    color = get_flow_color(intensity)

    # Connector dimensions
    y1 = 50 - diameter1_in_pixels / 2
    y2 = 50 - diameter2_in_pixels / 2

    # Create transition path
    if abs(diameter1_in_pixels - diameter2_in_pixels) < 2:
        # Minimal diameter change - straight connector
        connector_path = f'''
        <rect x="5" y="{min(y1, y2)}" width="{length}" height="{max(diameter1_in_pixels, diameter2_in_pixels)}" 
              fill="url(#connectorGrad)" stroke="{color}" stroke-width="2" rx="4"/>
        '''
    else:
        # Significant diameter change - tapered connector
        if diameter1_in_pixels > diameter2_in_pixels:
            # Contracting (reducer)
            connector_path = f'''
            <polygon points="5,{y1} {5 + length},{y2} {5 + length},{y2 + diameter2_in_pixels} 5,{y1 + diameter1_in_pixels}" 
                     fill="url(#connectorGrad)" stroke="{color}" stroke-width="2"/>
            '''
        else:
            # Expanding (expander)
            connector_path = f'''
            <polygon points="5,{y1} {5 + length},{y2} {5 + length},{y2 + diameter2_in_pixels} 5,{y1 + diameter1_in_pixels}" 
                     fill="url(#connectorGrad)" stroke="{color}" stroke-width="2"/>
            '''

    # Flow particles through connector
    particles = ""
    if intensity > 0:
        particle_count = max(2, int(intensity * 6))
        animation_duration = max(0.8, 3.0 - intensity * 2.0)

        for i in range(particle_count):
            delay = i * (animation_duration / particle_count)

            # Particles follow the centerline, adjusting for diameter changes
            start_y = 50
            end_y = 50

            particles += f'''
            <circle r="2" fill="{color}" opacity="0">
                <animate attributeName="cx" 
                         values="5;{5 + length}" 
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

    return f'''
    <svg width="{5 + length + 5}" height="100" viewBox="0 0 {5 + length + 5} 100" class="mx-auto">
        <defs>
            <linearGradient id="connectorGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" style="stop-color:{color};stop-opacity:0.3" />
                <stop offset="50%" style="stop-color:{color};stop-opacity:0.6" />
                <stop offset="100%" style="stop-color:{color};stop-opacity:0.3" />
            </linearGradient>
        </defs>
        
        <!-- Connector body with diameter transition -->
        {connector_path}
        
        <!-- Connection flanges -->
        <rect x="0" y="{y1 - 2}" width="5" height="{diameter1_in_pixels + 4}" fill="#6b7280" rx="2"/>
        <rect x="{5 + length}" y="{y2 - 2}" width="5" height="{diameter2_in_pixels + 4}" fill="#6b7280" rx="2"/>
        
        <!-- Connection points -->
        <circle cx="0" cy="50" r="3" fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
        <circle cx="{5 + length + 5}" cy="50" r="3" fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
        
        <!-- Flow particles -->
        {particles}
    </svg>
    '''


def build_elbow_pipe_connector_svg(
    pipe1: Pipe,
    pipe2: Pipe,
    connector_length: typing.Optional[PlainQuantity[float]] = None,
    flow_rate: typing.Union[PlainQuantity[float], float, None] = None,
) -> str:
    """
    Build an elbow connector SVG between two pipes with dynamic orientation.
    The elbow orientation is determined by the flow directions of the connected pipes.

    :param pipe1: First pipe (upstream)
    :param pipe2: Second pipe (downstream)
    :param connector_length: Physical length of connector arms (e.g., mm, cm). If None, uses default.
    :param flow_rate: Optional flow rate for animation
    :return: SVG string for the elbow connector
    """
    # Scale diameters for display (use average scale factor)
    scale_factor = (pipe1.scale_factor + pipe2.scale_factor) / 2
    diameter1_in_pixels = physical_to_display_unit(
        pipe1.properties.internal_diameter,
        scale_factor,
        max_display_unit=200,
    )
    diameter2_in_pixels = physical_to_display_unit(
        pipe2.properties.internal_diameter,
        scale_factor,
        max_display_unit=200,
    )

    flow_rate = pipe1.flow_rate if flow_rate is None else flow_rate
    if not isinstance(flow_rate, Quantity):
        flow_rate = Quantity(flow_rate, "ft^3/s")

    intensity = calculate_flow_intensity(flow_rate, pipe1.max_flow_rate)
    color = get_flow_color(intensity)

    # Determine elbow orientation based on pipe directions
    dir1 = pipe1.direction
    dir2 = pipe2.direction

    # Map directions to elbow orientations
    # The elbow inlet faces opposite to pipe1's direction
    # The elbow outlet faces the same as pipe2's direction
    orientation_map = {
        (PipeDirection.EAST, PipeDirection.NORTH): (
            "west",
            "north",
        ),  # west inlet, north outlet
        (PipeDirection.EAST, PipeDirection.SOUTH): (
            "west",
            "south",
        ),  # west inlet, south outlet
        (PipeDirection.WEST, PipeDirection.NORTH): (
            "east",
            "north",
        ),  # east inlet, north outlet
        (PipeDirection.WEST, PipeDirection.SOUTH): (
            "east",
            "south",
        ),  # east inlet, south outlet
        (PipeDirection.SOUTH, PipeDirection.EAST): (
            "north",
            "east",
        ),  # north inlet, east outlet
        (PipeDirection.SOUTH, PipeDirection.WEST): (
            "north",
            "west",
        ),  # north inlet, west outlet
        (PipeDirection.NORTH, PipeDirection.EAST): (
            "south",
            "east",
        ),  # south inlet, east outlet
        (PipeDirection.NORTH, PipeDirection.WEST): (
            "south",
            "west",
        ),  # south inlet, west outlet
    }

    if (dir1, dir2) not in orientation_map:
        # Fallback to default orientation if combination not found
        inlet_face, outlet_face = "west", "north"
    else:
        inlet_face, outlet_face = orientation_map[(dir1, dir2)]

    # Use average thickness for consistent appearance
    avg_thickness = (diameter1_in_pixels + diameter2_in_pixels) / 2

    # Calculate arm length from connector length or use default
    # Each arm should use the connector_length independently
    if connector_length is not None:
        # Convert physical connector length to display units for each arm
        arm_length = physical_to_display_unit(
            connector_length, scale_factor, min_display_unit=40, max_display_unit=50
        )
    else:
        # Default arm length for compact design
        arm_length = 25

    if inlet_face == "west" and outlet_face == "north":
        # West inlet (left), North outlet (top)
        # Connection points at the edges of the elbow arms
        inlet_x, inlet_y = 50 - arm_length, 50
        outlet_x, outlet_y = 50, 50 - arm_length
        h_rect = f'<rect x="{inlet_x}" y="{50 - avg_thickness / 2}" width="{arm_length + avg_thickness / 2}" height="{avg_thickness}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        v_rect = f'<rect x="{50 - avg_thickness / 2}" y="{outlet_y}" width="{avg_thickness}" height="{arm_length + avg_thickness / 2}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        particle_path = (
            f"M {inlet_x + 5} 50 L {50 - 5} 50 Q 50 50 50 {50 - 5} L 50 {outlet_y + 5}"
        )

    elif inlet_face == "west" and outlet_face == "south":
        # West inlet (left), South outlet (bottom)
        inlet_x, inlet_y = 50 - arm_length, 50
        outlet_x, outlet_y = 50, 50 + arm_length
        h_rect = f'<rect x="{inlet_x}" y="{50 - avg_thickness / 2}" width="{arm_length + avg_thickness / 2}" height="{avg_thickness}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        v_rect = f'<rect x="{50 - avg_thickness / 2}" y="{50 - avg_thickness / 2}" width="{avg_thickness}" height="{arm_length + avg_thickness / 2}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        particle_path = (
            f"M {inlet_x + 5} 50 L {50 - 5} 50 Q 50 50 50 {50 + 5} L 50 {outlet_y - 5}"
        )

    elif inlet_face == "east" and outlet_face == "north":
        # East inlet (right), North outlet (top)
        inlet_x, inlet_y = 50 + arm_length, 50
        outlet_x, outlet_y = 50, 50 - arm_length
        h_rect = f'<rect x="{50 - avg_thickness / 2}" y="{50 - avg_thickness / 2}" width="{arm_length + avg_thickness / 2}" height="{avg_thickness}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        v_rect = f'<rect x="{50 - avg_thickness / 2}" y="{outlet_y}" width="{avg_thickness}" height="{arm_length + avg_thickness / 2}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        particle_path = (
            f"M {inlet_x - 5} 50 L {50 + 5} 50 Q 50 50 50 {50 - 5} L 50 {outlet_y + 5}"
        )

    elif inlet_face == "east" and outlet_face == "south":
        # East inlet (right), South outlet (bottom)
        inlet_x, inlet_y = 50 + arm_length, 50
        outlet_x, outlet_y = 50, 50 + arm_length
        h_rect = f'<rect x="{50 - avg_thickness / 2}" y="{50 - avg_thickness / 2}" width="{arm_length + avg_thickness / 2}" height="{avg_thickness}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        v_rect = f'<rect x="{50 - avg_thickness / 2}" y="{50 - avg_thickness / 2}" width="{avg_thickness}" height="{arm_length + avg_thickness / 2}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        particle_path = (
            f"M {inlet_x - 5} 50 L {50 + 5} 50 Q 50 50 50 {50 + 5} L 50 {outlet_y - 5}"
        )

    elif inlet_face == "north" and outlet_face == "east":
        # North inlet (top), East outlet (right)
        inlet_x, inlet_y = 50, 50 - arm_length
        outlet_x, outlet_y = 50 + arm_length, 50
        v_rect = f'<rect x="{50 - avg_thickness / 2}" y="{inlet_y}" width="{avg_thickness}" height="{arm_length + avg_thickness / 2}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        h_rect = f'<rect x="{50 - avg_thickness / 2}" y="{50 - avg_thickness / 2}" width="{arm_length + avg_thickness / 2}" height="{avg_thickness}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        particle_path = (
            f"M 50 {inlet_y + 5} L 50 {50 - 5} Q 50 50 {50 + 5} 50 L {outlet_x - 5} 50"
        )

    elif inlet_face == "north" and outlet_face == "west":
        # North inlet (top), West outlet (left)
        inlet_x, inlet_y = 50, 50 - arm_length
        outlet_x, outlet_y = 50 - arm_length, 50
        v_rect = f'<rect x="{50 - avg_thickness / 2}" y="{inlet_y}" width="{avg_thickness}" height="{arm_length + avg_thickness / 2}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        h_rect = f'<rect x="{outlet_x}" y="{50 - avg_thickness / 2}" width="{arm_length + avg_thickness / 2}" height="{avg_thickness}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        particle_path = (
            f"M 50 {inlet_y + 5} L 50 {50 - 5} Q 50 50 {50 - 5} 50 L {outlet_x + 5} 50"
        )

    elif inlet_face == "south" and outlet_face == "east":
        # South inlet (bottom), East outlet (right)
        inlet_x, inlet_y = 50, 50 + arm_length
        outlet_x, outlet_y = 50 + arm_length, 50
        v_rect = f'<rect x="{50 - avg_thickness / 2}" y="{50 - avg_thickness / 2}" width="{avg_thickness}" height="{arm_length + avg_thickness / 2}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        h_rect = f'<rect x="{50 - avg_thickness / 2}" y="{50 - avg_thickness / 2}" width="{arm_length + avg_thickness / 2}" height="{avg_thickness}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        particle_path = (
            f"M 50 {inlet_y - 5} L 50 {50 + 5} Q 50 50 {50 + 5} 50 L {outlet_x - 5} 50"
        )

    else:  # inlet_face == "south" and outlet_face == "west"
        # South inlet (bottom), West outlet (left)
        inlet_x, inlet_y = 50, 50 + arm_length
        outlet_x, outlet_y = 50 - arm_length, 50
        v_rect = f'<rect x="{50 - avg_thickness / 2}" y="{50 - avg_thickness / 2}" width="{avg_thickness}" height="{arm_length + avg_thickness / 2}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        h_rect = f'<rect x="{outlet_x}" y="{50 - avg_thickness / 2}" width="{arm_length + avg_thickness / 2}" height="{avg_thickness}" fill="url(#elbowGrad_{id(pipe1)})" stroke="{color}" stroke-width="2" rx="3"/>'
        particle_path = (
            f"M 50 {inlet_y - 5} L 50 {50 + 5} Q 50 50 {50 - 5} 50 L {outlet_x + 5} 50"
        )

    # Create the elbow geometry with overlapping sections (no corner needed)
    elbow_geometry = f"""
        <!-- Horizontal section -->
        {h_rect}
        <!-- Vertical section (overlaps horizontal) -->
        {v_rect}
    """

    # Flow particles following the elbow curved path
    particles = ""
    if intensity > 0:
        particle_count = max(3, int(intensity * 8))
        animation_duration = max(1.0, 4.0 - intensity * 3.0)
        particle_color = color

        for i in range(particle_count):
            delay = i * (animation_duration / particle_count)

            particles += f'''
            <circle r="2" fill="{particle_color}" opacity="0">
                <animateMotion dur="{animation_duration}s" repeatCount="indefinite" begin="{delay}s">
                    <path d="{particle_path}"/>
                </animateMotion>
                <animate attributeName="opacity" 
                         values="0;0.8;0.8;0" 
                         dur="{animation_duration}s" 
                         repeatCount="indefinite" 
                         begin="{delay}s"/>
            </circle>
            '''

    return f'''
    <svg width="80" height="80" viewBox="0 0 80 80" class="mx-auto">
        <defs>
            <linearGradient id="elbowGrad_{
        id(pipe1)
    }" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:{color};stop-opacity:0.3" />
                <stop offset="50%" style="stop-color:{color};stop-opacity:0.6" />
                <stop offset="100%" style="stop-color:{color};stop-opacity:0.3" />
            </linearGradient>
        </defs>
        
        <!-- Elbow body with dynamic orientation -->
        {elbow_geometry}
        
        <!-- Connection flanges positioned to overlap with pipe flanges -->
        <!-- Inlet flange - extends outward from connection point toward the connecting pipe -->
        {
        f'<rect x="{inlet_x}" y="{inlet_y - diameter1_in_pixels / 2 - 2}" width="5" height="{diameter1_in_pixels + 4}" fill="#6b7280" rx="2"/>'
        if inlet_face == "east"
        else f'<rect x="{inlet_x - 5}" y="{inlet_y - diameter1_in_pixels / 2 - 2}" width="5" height="{diameter1_in_pixels + 4}" fill="#6b7280" rx="2"/>'
        if inlet_face == "west"
        else f'<rect x="{inlet_x - diameter1_in_pixels / 2 - 2}" y="{inlet_y}" width="{diameter1_in_pixels + 4}" height="5" fill="#6b7280" rx="2"/>'
        if inlet_face == "south"
        else f'<rect x="{inlet_x - diameter1_in_pixels / 2 - 2}" y="{inlet_y - 5}" width="{diameter1_in_pixels + 4}" height="5" fill="#6b7280" rx="2"/>'
    }
        <!-- Outlet flange - extends outward from connection point toward the connecting pipe -->
        {
        f'<rect x="{outlet_x}" y="{outlet_y - diameter2_in_pixels / 2 - 2}" width="5" height="{diameter2_in_pixels + 4}" fill="#6b7280" rx="2"/>'
        if outlet_face == "east"
        else f'<rect x="{outlet_x - 5}" y="{outlet_y - diameter2_in_pixels / 2 - 2}" width="5" height="{diameter2_in_pixels + 4}" fill="#6b7280" rx="2"/>'
        if outlet_face == "west"
        else f'<rect x="{outlet_x - diameter2_in_pixels / 2 - 2}" y="{outlet_y}" width="{diameter2_in_pixels + 4}" height="5" fill="#6b7280" rx="2"/>'
        if outlet_face == "south"
        else f'<rect x="{outlet_x - diameter2_in_pixels / 2 - 2}" y="{outlet_y - 5}" width="{diameter2_in_pixels + 4}" height="5" fill="#6b7280" rx="2"/>'
    }
        
        <!-- Connection points -->
        <circle cx="{inlet_x}" cy="{
        inlet_y
    }" r="3" fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
        <circle cx="{outlet_x}" cy="{
        outlet_y
    }" r="3" fill="#dc2626" stroke="#ffffff" stroke-width="1"/>
        
        <!-- Flow particles -->
        {particles}
    </svg>
    '''


class FlowType(str, enum.Enum):
    """Enumeration of flow types for pipes."""

    COMPRESSIBLE = "compressible"
    """Compressible flow (e.g., gases). With the flow type, the volumetric rate in pipes will vary with pressure and temperature."""
    INCOMPRESSIBLE = "incompressible"
    """Incompressible flow (e.g., liquids). The volumetric rate in pipes remains constant regardless of pressure changes."""


class Pipeline:
    """
    Pipeline component that manages a sequence of connected Pipe components.

    Validates proper connections between pipes and aggregates their properties
    to provide comprehensive pipeline characteristics and visualization.
    """

    def __init__(
        self,
        pipes: typing.Sequence[Pipe],
        fluid: typing.Optional[Fluid] = None,
        name: typing.Optional[str] = None,
        scale_factor: float = 0.1,
        max_flow_rate: PlainQuantity[float] = Quantity(10.0, "ft^3/s"),
        flow_type: FlowType = FlowType.COMPRESSIBLE,
        connector_length: PlainQuantity[float] = Quantity(0.1, "m"),
    ) -> None:
        """
        Initialize a Pipeline component.

        :param pipes: Sequence of Pipe instances to include in the pipeline
        :param fluid: Optional Fluid instance representing the fluid in the pipeline
        :param name: Optional name for the pipeline
        :param scale_factor: Scaling factor for pipe visualization (applied to all pipes)
        :param max_flow_rate: Maximum expected flow rate for intensity normalization
        :param flow_type: Flow type for the pipeline (compressible or incompressible)
        :param connector_length: Physical length of connectors between pipes (e.g., mm, cm)
        """
        self.name = name or f"Pipeline-{id(self)}"
        self._pipes: typing.List[Pipe] = []
        self.scale_factor = scale_factor
        self.max_flow_rate = max_flow_rate
        self.pipeline_viz = None
        self.flow_type = flow_type
        self.connector_length = connector_length
        self._fluid = fluid
        for pipe in pipes:
            self.add_pipe(pipe, update=False)
        self.update_properties()

    @property
    def fluid(self) -> typing.Optional[Fluid]:
        """Get the fluid in the pipeline."""
        return self._fluid

    def set_fluid(self, value: Fluid):
        """Set the fluid in the pipeline and update all pipes."""
        self._fluid = value
        for pipe in self._pipes:
            pipe.set_fluid(value)
        return self.update_properties()

    @property
    def upstream_pressure(self) -> PlainQuantity[float]:
        """The upstream pressure of the pipeline (from the first pipe)."""
        if self._pipes:
            return self._pipes[0].properties.upstream_pressure
        return Quantity(0, "psi")

    @property
    def downstream_pressure(self) -> PlainQuantity[float]:
        """The downstream pressure (psi) of the pipeline (from the last pipe)."""
        if self._pipes:
            return self._pipes[-1].properties.downstream_pressure
        return Quantity(0, "psi")

    @property
    def inlet_flow_rate(self) -> PlainQuantity[float]:
        """The inlet/upstream flow rate (ft^3/s) of the pipeline (from the first pipe)."""
        if self._pipes:
            return self._pipes[0].flow_rate
        return Quantity(0, "ft^3/s")

    @property
    def outlet_flow_rate(self) -> PlainQuantity[float]:
        """The outlet/downstream flow rate of the pipeline (ft^3/s) (from the last pipe)."""
        if self._pipes:
            return self._pipes[-1].flow_rate
        return Quantity(0, "ft^3/s")

    def show(
        self,
        width: str = "100%",
        height: str = "auto",
        label: typing.Optional[str] = None,
        show_label: bool = True,
    ) -> Row:
        """
        Display the pipeline as a UI component.

        :param label: Title label for the pipeline visualization
        :param width: Width of the container (CSS units)
        :param height: Height of the container (CSS units)
        :param show_label: Whether to display the label above the pipeline
        :return: Html component containing the pipeline visualization
        """
        container = (
            ui.row()
            .classes(
                "w-full h-auto p-4 bg-white border border-gray-200 rounded-lg shadow-sm flex flex-col items-center"
            )
            .style(
                f"width: {width}; height: {height}; min-height: 300px; overflow: auto;"
            )
        )

        with container:
            label = label or self.name
            if show_label:
                ui.label(label).classes("text-2xl font-bold text-gray-800")

            # Get the SVG content and check if it's valid
            svg_content = self.get_svg()
            self.pipeline_viz = (
                ui.html(svg_content)
                .classes("w-full")
                .style(
                    "min-height: 200px; border: 1px solid #ccc; background: #f9f9f9;"
                )
            )
        return container

    def update_viz(self):
        """
        Update the SVG visualization of the pipeline.
        This method should be called whenever pipe properties or flow rates change.
        """
        if self.pipeline_viz is not None:
            self.pipeline_viz.content = self.get_svg()
        return self

    def get_svg(self) -> str:
        """
        Generate a unified SVG showing all pipes connected together based on their actual flow directions.

        :return: SVG string representing the entire pipeline with proper connections
        """
        if not self._pipes:
            return """
            <svg viewBox="0 0 400 100" class="mx-auto">
                <text x="200" y="50" text-anchor="middle" font-size="14" fill="#6b7280">
                    Empty Pipeline
                </text>
            </svg>
            """

        def extract_svg_dimensions(svg_content: str) -> tuple[float, float]:
            """Extract width and height from SVG content."""
            # Try to extract from viewBox first
            viewbox_match = re.search(
                r'viewBox="[\d\s.-]+ [\d\s.-]+ ([\d\s.-]+) ([\d\s.-]+)"', svg_content
            )
            if viewbox_match:
                return float(viewbox_match.group(1)), float(viewbox_match.group(2))

            # Fallback to width/height attributes
            width_match = re.search(r'width="([\d.]+)"', svg_content)
            height_match = re.search(r'height="([\d.]+)"', svg_content)
            if width_match and height_match:
                return float(width_match.group(1)), float(height_match.group(1))

            # Default fallback
            return 400.0, 100.0

        def get_pipe_flange_positions(pipe: Pipe) -> dict:
            """Get flange positions for a pipe based on its direction and actual dimensions."""
            svg_content = pipe.get_svg()
            width, height = extract_svg_dimensions(svg_content)

            if pipe.direction == PipeDirection.EAST:
                return {
                    "inlet": {"x": 45, "y": height / 2},  # Left flange
                    "outlet": {"x": width - 45, "y": height / 2},  # Right flange
                    "width": width,
                    "height": height,
                }
            elif pipe.direction == PipeDirection.WEST:
                return {
                    "inlet": {"x": width - 45, "y": height / 2},  # Right flange (inlet)
                    "outlet": {"x": 45, "y": height / 2},  # Left flange (outlet)
                    "width": width,
                    "height": height,
                }
            elif pipe.direction == PipeDirection.SOUTH:
                return {
                    "inlet": {"x": width / 2, "y": 15},  # Top flange
                    "outlet": {"x": width / 2, "y": height - 15},  # Bottom flange
                    "width": width,
                    "height": height,
                }
            # NORTH
            return {
                "inlet": {
                    "x": width / 2,
                    "y": height - 15,
                },  # Bottom flange (inlet)
                "outlet": {"x": width / 2, "y": 15},  # Top flange (outlet)
                "width": width,
                "height": height,
            }

        def calculate_straight_flange_overlap_offset() -> float:
            """
            Calculate the proper offset for straight connector flange overlap.

            Based on testing, 20 pixels provides the optimal flange overlap for
            straight connectors where pipe flanges sit properly on top of connector flanges.

            :return: Offset in pixels for proper straight connector flange overlap
            """
            return 20  # Empirically determined optimal offset for straight connectors

        def calculate_elbow_flange_overlap_offset() -> float:
            """
            Calculate the proper offset for elbow connector flange overlap.

            Based on testing, 25 pixels provides the optimal flange overlap for
            elbow connectors where pipe flanges sit properly on top of connector flanges.

            :return: Offset in pixels for proper elbow connector flange overlap
            """
            return 25  # Empirically determined optimal offset for elbow connectors

        def get_connector_dimensions_and_flanges(
            pipe1: Pipe, pipe2: Pipe, is_elbow: bool
        ) -> dict:
            """Get connector dimensions and flange positions."""
            if is_elbow:
                # Elbow connector - fixed 80x80 viewBox
                arm_length = physical_to_display_unit(
                    self.connector_length,
                    (pipe1.scale_factor + pipe2.scale_factor) / 2,
                    min_display_unit=15,
                    max_display_unit=50,
                )

                # Map pipe directions to elbow inlet/outlet positions
                dir1, dir2 = pipe1.direction, pipe2.direction
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
                    (dir1, dir2), ("west", "north")
                )

                # Calculate inlet and outlet positions based on faces
                if inlet_face == "west":
                    inlet_pos = {"x": 50 - arm_length, "y": 50}
                elif inlet_face == "east":
                    inlet_pos = {"x": 50 + arm_length, "y": 50}
                elif inlet_face == "north":
                    inlet_pos = {"x": 50, "y": 50 - arm_length}
                else:  # south
                    inlet_pos = {"x": 50, "y": 50 + arm_length}

                if outlet_face == "west":
                    outlet_pos = {"x": 50 - arm_length, "y": 50}
                elif outlet_face == "east":
                    outlet_pos = {"x": 50 + arm_length, "y": 50}
                elif outlet_face == "north":
                    outlet_pos = {"x": 50, "y": 50 - arm_length}
                else:  # south
                    outlet_pos = {"x": 50, "y": 50 + arm_length}

                return {
                    "inlet": inlet_pos,
                    "outlet": outlet_pos,
                    "width": 80,
                    "height": 80,
                }
            else:
                # Straight connector - dynamic length based on connector_length
                scale_factor = (pipe1.scale_factor + pipe2.scale_factor) / 2
                length = physical_to_display_unit(
                    self.connector_length,
                    scale_factor,
                    min_display_unit=20,
                    max_display_unit=300,
                )

                return {
                    "inlet": {"x": 0, "y": 50},  # Left side
                    "outlet": {
                        "x": length + 10,
                        "y": 50,
                    },  # Right side (length + flanges)
                    "width": length + 10,
                    "height": 100,
                }

        # Dynamic dimensions will be calculated per pipe/connector
        # No fixed constants needed - use actual SVG dimensions

        # Track all elements to be rendered - separate layers for proper z-ordering
        connector_elements = []  # Connectors rendered first (underneath)
        pipe_elements = []  # Pipes rendered second (on top)
        gradient_defs = []  # Collect all gradient definitions

        # Current position tracker - where the next pipe should connect
        current_connection_x = 0
        current_connection_y = 0

        # Bounding box tracking for dynamic viewBox
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        pipe_count = len(self._pipes)

        for i, pipe in enumerate(self._pipes):
            # Get pipe SVG content (ensure it reflects current flow rate)
            pipe_svg_content = pipe.get_svg()
            pipe_info = get_pipe_flange_positions(pipe)

            # Extract both defs and content separately
            defs_match = re.search(r"<defs>(.*?)</defs>", pipe_svg_content, re.DOTALL)
            if defs_match:
                gradient_defs.append(defs_match.group(1))

            # Extract the main content (everything except the outer svg tag and defs)
            content_match = re.search(
                r"<svg[^>]*>.*?<defs>.*?</defs>(.*?)</svg>", pipe_svg_content, re.DOTALL
            )
            if not content_match:
                # Fallback if no defs found
                content_match = re.search(
                    r"<svg[^>]*>(.*)</svg>", pipe_svg_content, re.DOTALL
                )

            inner_svg_content = (
                content_match.group(1) if content_match else pipe_svg_content
            )

            # Position pipe for proper flange overlap - minimal offset for pipe positioning
            # Pipes should be positioned to just touch connectors, with connectors handling the overlap offset
            pipe_positioning_offset = 5  # Minimal offset just for edge alignment

            if pipe.direction == PipeDirection.EAST:
                # For east-flowing pipes, move right slightly so left flange edge aligns with connector
                pipe_x = (
                    current_connection_x
                    - pipe_info["inlet"]["x"]
                    + pipe_positioning_offset
                )
            elif pipe.direction == PipeDirection.WEST:
                # For west-flowing pipes, move left slightly so right flange edge aligns with connector
                pipe_x = (
                    current_connection_x
                    - pipe_info["inlet"]["x"]
                    - pipe_positioning_offset
                )
            else:
                # For vertical pipes, use standard center positioning
                pipe_x = current_connection_x - pipe_info["inlet"]["x"]

            pipe_y = current_connection_y - pipe_info["inlet"]["y"]
            next_connection_x = pipe_x + pipe_info["outlet"]["x"]
            next_connection_y = pipe_y + pipe_info["outlet"]["y"]

            # Add pipe element with unique transform group
            pipe_elements.append(f"""
            <!-- Pipe {i + 1}: {pipe.name} ({pipe.direction.value}) -->
            <g transform="translate({pipe_x}, {pipe_y})">
                {inner_svg_content}
            </g>
            """)

            # Update bounding box
            min_x = min(min_x, pipe_x)
            min_y = min(min_y, pipe_y)
            max_x = max(max_x, pipe_x + pipe_info["width"])
            max_y = max(max_y, pipe_y + pipe_info["height"])

            # Add connector to next pipe (if not the last pipe)
            if i < (pipe_count - 1):
                next_pipe = self._pipes[i + 1]

                # Check if we need an elbow connector (direction change)
                is_elbow = pipe.direction != next_pipe.direction

                # Get connector dimensions and flange positions
                connector_info = get_connector_dimensions_and_flanges(
                    pipe, next_pipe, is_elbow
                )

                if is_elbow:
                    # Generate elbow connector with pipeline flow rate
                    connector_svg = build_elbow_pipe_connector_svg(
                        pipe,
                        next_pipe,
                        flow_rate=pipe.flow_rate,
                        connector_length=self.connector_length,
                    )
                else:
                    # Generate straight connector with pipeline flow rate
                    connector_svg = build_straight_pipe_connector_svg(
                        pipe,
                        next_pipe,
                        flow_rate=pipe.flow_rate,
                        connector_length=self.connector_length,
                    )

                # Extract connector defs and content
                defs_match = re.search(r"<defs>(.*?)</defs>", connector_svg, re.DOTALL)
                if defs_match:
                    gradient_defs.append(defs_match.group(1))

                content_match = re.search(
                    r"<svg[^>]*>.*?<defs>.*?</defs>(.*?)</svg>",
                    connector_svg,
                    re.DOTALL,
                )
                if not content_match:
                    content_match = re.search(
                        r"<svg[^>]*>(.*)</svg>", connector_svg, re.DOTALL
                    )

                connector_content = (
                    content_match.group(1) if content_match else connector_svg
                )

                # Position connector so its inlet flange overlaps with current pipe's outlet flange
                # Move connectors back by negative X offset for proper alignment
                connector_back_offset = 15  # Move connectors back by 15 pixels

                if is_elbow:
                    # Elbow positioning with backward offset
                    if pipe.direction == PipeDirection.EAST:
                        connector_x = (
                            next_connection_x
                            - connector_info["inlet"]["x"]
                            - connector_back_offset
                        )
                        connector_y = next_connection_y - connector_info["inlet"]["y"]
                    elif pipe.direction == PipeDirection.WEST:
                        connector_x = (
                            next_connection_x
                            - connector_info["inlet"]["x"]
                            + connector_back_offset
                        )
                        connector_y = next_connection_y - connector_info["inlet"]["y"]
                    elif pipe.direction == PipeDirection.SOUTH:
                        connector_x = next_connection_x - connector_info["inlet"]["x"]
                        connector_y = (
                            next_connection_y
                            - connector_info["inlet"]["y"]
                            - connector_back_offset
                        )
                    else:  # PipeDirection.NORTH
                        connector_x = next_connection_x - connector_info["inlet"]["x"]
                        connector_y = (
                            next_connection_y
                            - connector_info["inlet"]["y"]
                            + connector_back_offset
                        )
                else:
                    # Straight connector positioning with backward offset
                    if pipe.direction == PipeDirection.EAST:
                        connector_x = (
                            next_connection_x
                            - connector_info["inlet"]["x"]
                            - connector_back_offset
                        )
                        connector_y = next_connection_y - connector_info["inlet"]["y"]
                    elif pipe.direction == PipeDirection.WEST:
                        connector_x = (
                            next_connection_x
                            - connector_info["inlet"]["x"]
                            + connector_back_offset
                        )
                        connector_y = next_connection_y - connector_info["inlet"]["y"]
                    else:
                        # For vertical pipes, apply Y offset instead of X
                        connector_x = next_connection_x - connector_info["inlet"]["x"]
                        if pipe.direction == PipeDirection.SOUTH:
                            connector_y = (
                                next_connection_y
                                - connector_info["inlet"]["y"]
                                - connector_back_offset
                            )
                        else:  # PipeDirection.NORTH
                            connector_y = (
                                next_connection_y
                                - connector_info["inlet"]["y"]
                                + connector_back_offset
                            )

                connector_elements.append(f"""
                <!-- {"Elbow" if is_elbow else "Straight"} Connector {i + 1} to {i + 2} -->
                <g transform="translate({connector_x}, {connector_y})">
                    {connector_content}
                </g>
                """)

                # Update bounding box for connector
                min_x = min(min_x, connector_x)
                min_y = min(min_y, connector_y)
                max_x = max(max_x, connector_x + connector_info["width"])
                max_y = max(max_y, connector_y + connector_info["height"])

                # Update connection point for next pipe to connector's outlet position
                current_connection_x = connector_x + connector_info["outlet"]["x"]
                current_connection_y = connector_y + connector_info["outlet"]["y"]

        # Calculate final viewBox with padding
        if min_x == float("inf"):  # No elements
            viewbox = "0 0 400 100"
        else:
            padding = 50
            viewbox_width = max_x - min_x + (2 * padding)
            viewbox_height = max_y - min_y + (2 * padding)
            viewbox_x = min_x - padding
            viewbox_y = min_y - padding
            viewbox = f"{viewbox_x} {viewbox_y} {viewbox_width} {viewbox_height}"

        # Combine all elements in proper z-order (connectors first, then pipes)
        # This ensures pipe flanges appear on top of connector flanges for proper overlap
        svg_content = f'''
        <svg viewBox="{viewbox}" class="mx-auto">
            <defs>
                {"".join(gradient_defs)}
            </defs>
            <!-- Connectors layer (underneath) -->
            {"".join(connector_elements)}
            <!-- Pipes layer (on top for flanges to overlap) -->
            {"".join(pipe_elements)}
        </svg>
        '''
        return svg_content

    def is_connected(self, pipe1_idx: int, pipe2_idx: int) -> bool:
        """
        Check if two consecutive pipes are properly connected.

        :param pipe1_idx: Index of the first pipe
        :param pipe2_idx: Index of the second pipe
        :return: True if pipes are connected, False otherwise
        """
        if pipe1_idx < 0 or pipe2_idx >= len(self._pipes):
            return False

        pipe1 = self._pipes[pipe1_idx]
        pipe2 = self._pipes[pipe2_idx]

        # Check direction compatibility (only check for direction compatibility now)
        direction_compatible = check_directions_compatibility(
            pipe1.direction, pipe2.direction
        )
        return direction_compatible

    def set_upstream_pressure(
        self, pressure: typing.Union[PlainQuantity[float], float], check: bool = True
    ):
        """
        Set the upstream pressure for the entire pipeline (applied to the first pipe).

        :param pressure: Upstream pressure to set
        :param check: Whether to validate the pressure change (default is True)
        :return: self for method chaining
        """
        if self._pipes:
            self._pipes[0].set_upstream_pressure(pressure, check=check, update=True)
        return self.update_properties()

    def set_upstream_temperature(
        self, temperature: typing.Union[PlainQuantity[float], float]
    ):
        """Set the upstream fluid temperature for the pipeline (applied to the first pipe)."""
        if isinstance(temperature, Quantity):
            temperature_q = temperature.to("degF")
        else:
            temperature_q = Quantity(temperature, "degF")

        if self._pipes:
            self._fluid = evolve(self._fluid, temperature=temperature_q)
            self._pipes[0].set_fluid_temperature(temperature_q, update=False)
        return self.update_properties()

    def add_pipe(self, pipe: Pipe, index: int = -1, update: bool = True):
        """
        Add a new pipe to the end of the pipeline.

        :param pipe: Pipe instance to add to the pipeline
        :param index: Optional index to insert the pipe at (default is -1 for appending)
        :param update: Whether to update properties after adding (default is True)
        :return: self for method chaining
        :raises `PipelineConnectionError`: If the new pipe cannot be connected
        """
        if self._pipes:
            # Validate flow direction compatibility
            last_pipe = self._pipes[-1]
            if not check_directions_compatibility(last_pipe.direction, pipe.direction):
                raise PipelineConnectionError(
                    f"Cannot add pipe with opposing flow direction: "
                    f"{last_pipe.direction.value} to {pipe.direction.value}. "
                    f"Pipes flowing in opposite directions cannot be connected."
                )

        copied_pipe = copy.deepcopy(pipe)
        # Apply the pipeline's scale factor and max flow rate to the pipe
        copied_pipe.scale_factor = self.scale_factor
        copied_pipe.max_flow_rate = self.max_flow_rate
        if self.fluid is not None:
            copied_pipe.set_fluid(self.fluid)

        if index < 0:
            index = len(self._pipes) + index + 1  # Convert negative index to positive

        self._pipes.insert(index, copied_pipe)
        if update:
            self.update_properties()
        return self

    def remove_pipe(self, index: int = -1, update: bool = True):
        """
        Remove a pipe from the pipeline at the specified index.

        :param index: Index of the pipe to remove
        :param update: Whether to update properties after removal (default is True)
        :return: self for method chaining
        :raises PipelineConnectionError: If removing the pipe breaks pipeline continuity
        """
        if index < 0:
            index = len(self._pipes) + index  # Convert negative index to positive

        if 0 <= index < len(self._pipes):
            self._pipes.pop(index)

            # Validate remaining connections
            if len(self._pipes) > 1:
                for i in range(len(self._pipes) - 1):
                    current_pipe = self._pipes[i]
                    next_pipe = self._pipes[i + 1]

                    if not check_directions_compatibility(
                        current_pipe.direction, next_pipe.direction
                    ):
                        raise PipelineConnectionError(
                            f"Removing pipe creates incompatible flow directions between segments {i} "
                            f"({current_pipe.direction.value}) and {i + 1} ({next_pipe.direction.value})"
                        )

        if update:
            self.update_properties()
        return self

    def update_properties(self, start_index: int = 0, end_index: int = -1):
        """
        Update properties for all pipes in the pipeline.

        :param start_index: Starting index of pipes to update (default is 0)
        :param end_index: Ending index of pipes to update (default is -1 for last pipe)
        :return: self for method chaining
        """
        if self.fluid is None:
            return self

        pipe_count = len(self._pipes)
        if start_index < 0:
            start_index = pipe_count + start_index

        if end_index < 0:
            end_index = pipe_count + end_index

        # Process pipes sequentially from start_index to end_index
        # Each pipe connects only to its immediate next neighbor
        for i in range(start_index, min(end_index, pipe_count - 1)):
            current_pipe = self._pipes[i]
            next_pipe = self._pipes[i + 1]
            print("Current Pipe:", current_pipe.name)
            print("Next Pipe:", next_pipe.name)

            # # Ensure current pipe flow rate is updated first
            # current_pipe.update_flow_rate()

            relative_diameter_difference = (
                abs(
                    current_pipe.properties.internal_diameter.magnitude
                    - next_pipe.properties.internal_diameter.magnitude
                )
                / current_pipe.properties.internal_diameter.magnitude
            )
            # If diameters are within 5%, treat as same diameter (no pressure drop across connector)
            if relative_diameter_difference < 0.05:
                # No pressure drop across connector if diameters are the same
                # So mass and volumetric flow rates remain constant
                # and the next pipe's pressures can be directly set
                next_pipe_fluid = next_pipe.fluid
                if next_pipe_fluid is None:
                    raise ValueError(
                        "Next pipe must have fluid properties defined to update flow rates."
                    )
                # Set next pipe's upstream pressure to current pipe's downstream pressure
                next_pipe_upstream_pressure = (
                    current_pipe.properties.downstream_pressure
                )
                next_pipe.set_upstream_pressure(
                    pressure=next_pipe_upstream_pressure,
                    check=False,
                    update=False,
                )
                # Compute the pressure drop across the length of the next pipe with the flow rate of the current pipe
                # entering the next pipe
                next_pipe_flow_equation = next_pipe.flow_equation
                if next_pipe_flow_equation is None:
                    raise ValueError(
                        "Next pipe must have a flow equation defined to update flow rates."
                    )
                pressure_drop = compute_pipe_pressure_drop(
                    properties=next_pipe.properties,
                    flow_rate=current_pipe.flow_rate,
                    fluid=next_pipe_fluid,
                    flow_equation=next_pipe_flow_equation,
                )
                next_pipe_downstream_pressure = (
                    next_pipe.properties.upstream_pressure.to("psi").magnitude
                    - pressure_drop.magnitude
                ) * ureg.psi
                next_pipe.set_downstream_pressure(
                    pressure=next_pipe_downstream_pressure,
                    check=False,
                    update=False,
                )
                # Next pipe flow rate is same as current pipe flow rate
                next_pipe.set_flow_rate(flow_rate=current_pipe.flow_rate)
                continue

            current_pipe_fluid = current_pipe.fluid
            next_pipe_fluid = next_pipe.fluid
            if current_pipe_fluid is None or next_pipe_fluid is None:
                raise ValueError(
                    "Both pipes must have fluid properties defined to update flow rates."
                )

            mass_rate = current_pipe.mass_rate.to("lb/s")
            is_elbow_connected = current_pipe.direction != next_pipe.direction
            # For elbow connectors, there are two arms each of length, `connector_length`
            connector_length = (
                2 * self.connector_length
                if is_elbow_connected
                else self.connector_length
            )

            # Calculate the pressure drop across the connector due to diameter change
            connector_pressure_drop = compute_tapered_pipe_pressure_drop(
                flow_rate=current_pipe.flow_rate,
                pipe_inlet_diameter=current_pipe.properties.internal_diameter,
                pipe_outlet_diameter=next_pipe.properties.internal_diameter,
                pipe_length=connector_length,
                fluid_density=current_pipe_fluid.density,
                fluid_dynamic_viscosity=current_pipe_fluid.viscosity,
                pipe_relative_roughness=0.0001,  # Assume very smooth connector
            )

            print("Connector Pressure Drop:", connector_pressure_drop.to("kilopascal"))
            connector_upstream_pressure = current_pipe.properties.downstream_pressure
            print(
                "Connector Upstream Pressure:",
                connector_upstream_pressure.to("kilopascal"),
            )
            connector_downstream_pressure = Quantity(
                connector_upstream_pressure.to("psi").magnitude
                - connector_pressure_drop.magnitude,
                "psi",
            )
            print(
                "Connector Downstream Pressure:",
                connector_downstream_pressure.to("kilopascal"),
            )

            is_compressible_flow = (
                self.flow_type == FlowType.COMPRESSIBLE
                or current_pipe_fluid.compressibility_factor > 0.0
            )
            # mass rate and volumetric rate is constant for short connector,
            # for both compressible and incompressible flow. However, for compressible flow,
            # fluid density changes
            if is_compressible_flow:
                estimated_fluid_density_in_next_pipe = compute_fluid_density(
                    pressure=connector_downstream_pressure,
                    temperature=current_pipe_fluid.temperature,
                    molecular_weight=current_pipe_fluid.molecular_weight,
                    compressibility_factor=current_pipe_fluid.compressibility_factor,
                ).to("lb/ft^3")
            else:
                estimated_fluid_density_in_next_pipe = current_pipe_fluid.density.to(
                    "lb/ft^3"
                )

            # Since mass rate is constant, across the pipeline, the estimated volumetric rate in the next pipe will be
            estimated_volumetric_rate_in_next_pipe = (
                mass_rate / estimated_fluid_density_in_next_pipe
            )
            next_pipe_upstream_pressure = connector_downstream_pressure
            next_pipe_downstream_pressure = Quantity(
                0.0, "psi"
            )  # We don't know this yet

            tolerance = 1e-6
            for _ in range(100):
                # Compute the pressure drop across the length of the next pipe with the outlet volumetric flow rate
                pressure_drop_in_next_pipe = compute_pipe_pressure_drop(
                    properties=next_pipe.properties,
                    flow_rate=estimated_volumetric_rate_in_next_pipe,
                    fluid=next_pipe_fluid,
                    flow_equation=FlowEquation.WEYMOUTH,  # start with weymouth
                )
                next_pipe_flow_equation = determine_pipe_flow_equation(
                    pressure_drop=pressure_drop_in_next_pipe,
                    upstream_pressure=next_pipe_upstream_pressure,
                    internal_diameter=next_pipe.properties.internal_diameter,
                    length=next_pipe.properties.length,
                    fluid_phase=next_pipe_fluid.phase,
                    fluid_specific_gravity=next_pipe.fluid.specific_gravity,  # type: ignore
                )
                print("Flow Equation:", next_pipe_flow_equation.value)

                next_pipe_downstream_pressure = Quantity(
                    next_pipe_upstream_pressure.magnitude
                    - pressure_drop_in_next_pipe.magnitude,
                    "psi",
                )

                if is_compressible_flow:
                    # use average-pressure for density evaluation
                    average_pressure = (
                        next_pipe_upstream_pressure.magnitude
                        + next_pipe_downstream_pressure.magnitude
                    ) / 2
                    average_pressure = Quantity(average_pressure, "psi")
                    new_density_estimate = compute_fluid_density(
                        pressure=average_pressure,
                        temperature=current_pipe_fluid.temperature,
                        molecular_weight=current_pipe_fluid.molecular_weight,
                        compressibility_factor=current_pipe_fluid.compressibility_factor,
                    ).to("lb/ft^3")
                else:
                    new_density_estimate = estimated_fluid_density_in_next_pipe

                new_volumetric_flow_rate_estimate = (
                    mass_rate / new_density_estimate
                ).to("ft^3/s")

                # Convergence check
                relative_error = abs(
                    (
                        new_volumetric_flow_rate_estimate
                        - estimated_volumetric_rate_in_next_pipe
                    ).magnitude
                ) / max(estimated_volumetric_rate_in_next_pipe.magnitude, 1e-12)

                if relative_error < tolerance:
                    estimated_fluid_density_in_next_pipe = new_density_estimate
                    estimated_volumetric_rate_in_next_pipe = (
                        new_volumetric_flow_rate_estimate
                    )
                    break

                # Relaxation update
                estimated_fluid_density_in_next_pipe = (
                    estimated_fluid_density_in_next_pipe.magnitude
                    + new_density_estimate.magnitude
                ) / 2
                estimated_fluid_density_in_next_pipe = Quantity(
                    estimated_fluid_density_in_next_pipe, "lb/ft^3"
                )
                estimated_volumetric_rate_in_next_pipe = (
                    estimated_volumetric_rate_in_next_pipe.magnitude
                    + new_volumetric_flow_rate_estimate.magnitude
                ) / 2
                estimated_volumetric_rate_in_next_pipe = Quantity(
                    estimated_volumetric_rate_in_next_pipe, "ft^3/s"
                )
                # Update next pipe fluid density for next iteration
                next_pipe.fluid.density = estimated_fluid_density_in_next_pipe  # type: ignore
            else:
                raise RuntimeError(
                    "Failed to converge compressible update for next pipe"
                )

            print(
                "Current Pipe Volumetric Rate:",
                current_pipe.flow_rate.to("ft^3/s"),
            )
            print(
                "Next Pipe Volumetric Rate:",
                estimated_volumetric_rate_in_next_pipe.to("ft^3/s"),
            )
            print(
                "Current Pipe Fluid Density:",
                current_pipe_fluid.density.to("lb/ft^3"),
            )
            print(
                "Next Pipe Fluid Density:",
                estimated_fluid_density_in_next_pipe.to("lb/ft^3"),
            )
            print(
                "Next Pipe Upstream Pressure:",
                next_pipe_upstream_pressure.to("kilopascal"),
            )
            print(
                "Next Pipe Downstream Pressure:",
                next_pipe_downstream_pressure.to("kilopascal"),
            )
            next_pipe.fluid.density = estimated_fluid_density_in_next_pipe  # type: ignore
            next_pipe.set_upstream_pressure(
                pressure=next_pipe_upstream_pressure,
                check=False,
                update=False,
            )
            next_pipe.set_downstream_pressure(
                pressure=next_pipe_downstream_pressure,
                check=False,
                update=False,
            )
            # Update the next pipe's flow rate after pressure changes
            next_pipe.set_flow_rate(estimated_volumetric_rate_in_next_pipe)
            print()

        return self

    def validate_connections(self) -> typing.List[str]:
        """
        Validate all pipe connections and return any error messages.

        :return: List of error messages for disconnected pipes (empty if all valid)
        """
        errors = []
        for i in range(len(self._pipes) - 1):
            current_pipe = self._pipes[i]
            next_pipe = self._pipes[i + 1]

            # Validate flow direction compatibility
            if not check_directions_compatibility(
                current_pipe.direction, next_pipe.direction
            ):
                errors.append(
                    f"Incompatible flow directions between pipe {i} ({current_pipe.direction.value}) "
                    f"and pipe {i + 1} ({next_pipe.direction.value}). "
                    f"Opposing flow directions cannot be connected."
                )
        return errors

    def connect(self, other: typing.Union[Pipe, "Pipeline"]):
        """
        Connect this pipeline to another pipe or pipeline.

        :param other: Pipe or Pipeline instance to connect
        :return: self for method chaining
        :raises TypeError: If other is not a Pipe or Pipeline instance
        """
        if isinstance(other, Pipe):
            # Connect single pipe
            return type(self)(self._pipes + [other])

        elif isinstance(other, Pipeline):
            # Connect another pipeline
            return type(self)(self._pipes + other._pipes)
        raise TypeError("Can only connect to Pipe or Pipeline instances")

    def __and__(self, other: typing.Union[Pipe, "Pipeline"]):
        """
        Overload the pipe connection operator.

        :param other: Pipe or Pipeline instance to connect using & operator
        :return: Connected Pipeline instance
        """
        return self.connect(other)

    __add__ = __and__


class FlowStation:
    """A collection of meters and regulators to monitor and control a fluid flow system."""

    def __init__(
        self,
        meters: typing.Optional[typing.Sequence[Meter]] = None,
        regulators: typing.Optional[typing.Sequence[Regulator]] = None,
        name: str = "Flow Station",
        width: str = "100%",
        height: str = "auto",
    ):
        """
        Initialize a FlowStation instance.

        :param pipeline: Pipeline instance to monitor
        :param name: Name of the flow station (default is "Flow Station")
        :param width: Width of the flow station display (default is "100%")
        :param height: Height of the flow station display (default is "200px")
        """
        self.name = name
        self.width = width
        self.height = height
        self._meters: typing.List[Meter] = list(meters) if meters else []
        self._regulators: typing.List[Regulator] = (
            list(regulators) if regulators else []
        )

    @property
    def meters(self) -> typing.List[Meter]:
        """Get the list of meters in the flow station."""
        return self._meters

    @property
    def regulators(self) -> typing.List[Regulator]:
        """Get the list of regulators in the flow station."""
        return self._regulators

    def show(
        self,
        width: str = "100%",
        height: str = "auto",
        show_meters_first: bool = True,
        section_titles: typing.Optional[typing.Tuple[str, str]] = None,
        meters_per_row: int = 3,
        regulators_per_row: int = 3,
        label: typing.Optional[str] = None,
        show_label: bool = True,
        show_empty_section: bool = False,
    ) -> ui.card:
        """
        Display the flow station as a UI component with responsive grid layout.

        :param width: Width of the container (CSS units)
        :param height: Height of the container (CSS units)
        :param show_meters_first: Whether to show meters before regulators (default is True)
        :param meters_per_row: Number of meters per row (auto-calculated if None)
        :param regulators_per_row: Number of regulators per row (auto-calculated if None)
        :param label: Title label for the flow station (uses self.name if None)
        :param show_label: Whether to display the label above the flow station
        :param section_titles: Optional tuple to customize section titles (meters, regulators)
        :param show_empty_section: Whether to show sections even if empty (default is False)
        :return: ui.card component containing the flow station visualization
        """
        container = (
            ui.card()
            .classes(
                "w-full h-auto p-4 bg-gradient-to-br from-blue-50 to-indigo-100 "
                "border border-blue-200 rounded-xl shadow-lg"
            )
            .style(
                f"width: {width}; height: {height}; min-height: 200px; "
                f"overflow-y: auto; overflow-x: hidden;"
            )
        )

        with container:
            # Header section
            if show_label:
                display_label = label or self.name
                ui.label(display_label).classes(
                    "text-xl font-bold text-blue-900 mb-4 text-center w-full"
                ).style(
                    "font-size: clamp(1rem, 3vw, 1.5rem); "
                    "margin-bottom: clamp(0.5rem, 2vw, 1rem);"
                )

            # Main content container with vertical layout
            content_container = (
                ui.column()
                .classes("w-full gap-4 flex-1")
                .style("gap: clamp(0.75rem, 2vw, 1.5rem);")
            )

            with content_container:
                # Determine display order
                sections = []
                if show_meters_first:
                    meters_section_title = (
                        section_titles[0] if section_titles else "Meters"
                    )
                    regulators_section_title = (
                        section_titles[1] if section_titles else "Regulators"
                    )
                    sections = [
                        ("meters", meters_section_title, self._meters, meters_per_row),
                        (
                            "regulators",
                            regulators_section_title,
                            self._regulators,
                            regulators_per_row,
                        ),
                    ]
                else:
                    regulators_section_title = (
                        section_titles[0] if section_titles else "Regulators"
                    )
                    meters_section_title = (
                        section_titles[1] if section_titles else "Meters"
                    )
                    sections = [
                        (
                            "regulators",
                            regulators_section_title,
                            self._regulators,
                            regulators_per_row,
                        ),
                        ("meters", meters_section_title, self._meters, meters_per_row),
                    ]

                # Render each section
                for section_type, section_title, items, items_per_row in sections:
                    if not items and not show_empty_section:
                        continue
                    self._render_section(
                        section_type=section_type,
                        section_title=section_title,
                        items=items,
                        items_per_row=items_per_row,
                    )

        return container

    def _render_section(
        self,
        section_type: str,
        section_title: str,
        items: typing.List[typing.Union[Meter, Regulator]],
        items_per_row: int,
    ):
        """
        Render a section (meters or regulators) with responsive grid layout.

        :param section_type: Type of section ("meters" or "regulators")
        :param section_title: Display title for the section
        :param items: List of items to display
        :param items_per_row: Number of items per row (auto-calculated if None)
        """
        # Section container
        section_container = (
            ui.column()
            .classes("w-full bg-white rounded-lg border border-gray-200 shadow-sm")
            .style("padding: clamp(0.75rem, 2vw, 1.5rem);")
        )

        with section_container:
            # Section header with count
            header_container = (
                ui.row()
                .classes("w-full items-center justify-between mb-3")
                .style("margin-bottom: clamp(0.5rem, 1.5vw, 0.75rem);")
            )

            with header_container:
                ui.label(section_title).classes(
                    "text-lg font-semibold text-gray-800"
                ).style("font-size: clamp(0.875rem, 2.5vw, 1.125rem);")

                # Count badge
                count_color = (
                    "bg-blue-100 text-blue-800"
                    if section_type == "meters"
                    else "bg-green-100 text-green-800"
                )
                ui.badge(str(len(items))).classes(
                    f"{count_color} px-2 py-1 rounded-full text-xs font-medium"
                ).style("font-size: clamp(0.625rem, 1.5vw, 0.75rem);")

            # Content area
            if not items:
                self._render_empty_grid(section_type)
            else:
                self._render_items_grid(items, items_per_row, section_type)

    def _render_empty_grid(self, section_type: str):
        """
        Render empty state when no items are available.

        :param section_type: Type of section ("meters" or "regulators")
        """
        icon = "📊" if section_type == "meters" else "🎛️"
        message = f"No {section_type} configured"

        empty_container = (
            ui.column()
            .classes("w-full items-center justify-center py-8 text-gray-500")
            .style("padding: clamp(2rem, 4vw, 3rem) clamp(1rem, 2vw, 1.5rem);")
        )

        with empty_container:
            ui.label(icon).classes("text-4xl mb-2").style(
                "font-size: clamp(2rem, 4vw, 2.5rem); "
                "margin-bottom: clamp(0.5rem, 1vw, 0.75rem);"
            )
            ui.label(message).classes("text-center font-medium").style(
                "font-size: clamp(0.75rem, 2vw, 0.875rem);"
            )

    def _render_items_grid(
        self,
        items: typing.List[typing.Union[Meter, Regulator]],
        items_per_row: int,
        section_type: str,
    ):
        """
        Render items in a responsive grid layout.

        :param items: List of items to display
        :param items_per_row: Number of items per row (auto-calculated if None)
        :param section_type: Type of section for styling
        """
        # Create responsive grid container
        grid_classes = self._get_grid_classes(items_per_row)
        grid_container = (
            ui.column()
            .classes("w-full gap-3")
            .style("gap: clamp(0.5rem, 1.5vw, 0.75rem);")
        )

        with grid_container:
            # Split items into rows
            for i in range(0, len(items), items_per_row):
                row_items = items[i : i + items_per_row]

                # Create row container
                row_container = (
                    ui.row()
                    .classes(f"{grid_classes} gap-3 w-full")
                    .style("gap: clamp(0.5rem, 1.5vw, 0.75rem);")
                )

                with row_container:
                    for item in row_items:
                        # Create responsive item wrapper
                        item_wrapper = (
                            ui.column()
                            .classes(
                                "flex-row justify-center align-center flex-1 min-w-0"  # min-w-0 allows flex items to shrink
                            )
                            .style(
                                "min-width: clamp(200px, 25vw, 300px); max-width: 100%;"
                            )
                        )

                        with item_wrapper:
                            # Show the item (both Meter and Regulator have show() method)
                            item_display = item.show()
                            item_display.style(
                                "max-width: 100%;"  # Ensure it fills the wrapper
                            )

    def _get_grid_classes(self, items_per_row: int) -> str:
        """
        Get appropriate CSS classes for grid layout based on items per row.

        :param items_per_row: Number of items per row
        :return: CSS classes string
        """
        # Use flexbox with responsive behavior
        if items_per_row == 1:
            return "flex-col"
        elif items_per_row == 2:
            return "flex-row flex-wrap justify-center"
        elif items_per_row == 3:
            return "flex-row flex-wrap justify-center"
        # 4 or more
        return "flex-row flex-wrap justify-center"
