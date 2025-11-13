from enum import Enum
import logging
import math
import typing
import functools

from nicegui import ui
from nicegui.elements.column import Column
from nicegui.elements.html import Html
from nicegui.elements.row import Row
from pint.facets.plain import PlainQuantity
from typing_extensions import Self

from src.flow import (
    Fluid,
    compute_pipe_flow_rate,
    compute_reynolds_number,
    determine_pipe_flow_equation,
)
from src.pipeline.ui import (
    LeakInfo,
    PipeComponent,
    PipeDirection,
    PipelineComponents,
    SVGComponent,
    build_elbow_connector_component,
    build_elbow_valve_component,
    build_horizontal_pipe_component,
    build_straight_connector_component,
    build_straight_valve_component,
    build_vertical_pipe_component,
)
from src.types import FlowEquation, FlowType, P, R
from src.units import Quantity, ureg

logger = logging.getLogger(__name__)


__all__ = [
    "PipeDirection",
    "PipelineConnectionError",
    "check_direction_compatibility",
    "Meter",
    "FlowMeter",
    "MassFlowMeter",
    "PressureGauge",
    "TemperatureGauge",
    "Regulator",
    "Valve",
    "ValveState",
    "PipeLeak",
    "Pipe",
    "Pipeline",
    "FlowStation",
]


def show_alert(
    message: str,
    severity: typing.Literal["info", "warning", "error", "loading"] = "info",
    duration: int = 3000,
):
    """Show an alert message using NiceGUI's notify system."""
    if severity == "error":
        type = "negative"  # Map to NiceGUI's severity levels
    elif severity == "loading":
        type = "ongoing"
    else:
        type = severity
    ui.notify(
        message,
        type=type,
        timeout=duration,
        close_button=True,
        position="top",
        multi_line=True,
    )


class Meter:
    """Base class for all meters."""

    def __init__(
        self,
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 100.0,
        theme_color: str = "blue",
        units: str = "",
        label: str = "Meter",
        width: str = "200px",
        height: str = "200px",
        precision: int = 3,
        alarm_high: typing.Optional[float] = None,
        alarm_low: typing.Optional[float] = None,
        animation_speed: float = 5.0,
        animation_interval: float = 0.05,
        update_func: typing.Optional[
            typing.Callable[[], typing.Optional[float]]
        ] = None,
        update_interval: float = 1.0,
        alert_errors: bool = True,
        help_text: typing.Optional[str] = None,
    ) -> None:
        """
        Initialize the meter.

        :param value: Initial value
        :param min_value: Minimum value for scaling
        :param max_value: Maximum value for scaling
        :param theme_color: Theme color for styling
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
        :param alert_errors: Whether to show alerts on for meter update errors.
        :param help_text: Optional help text for the meter
        """
        self.min = min_value
        self.max = max_value
        self.value = 0.0
        self.theme_color = theme_color
        self.units = units
        self.label = label
        self.width = width
        self.height = height
        self.precision = int(precision) if precision else 0
        self.alarm_high = alarm_high
        self.alarm_low = alarm_low
        self._target_value = value
        self.animation_speed = animation_speed
        self.animation_interval = animation_interval
        self.update_func = update_func
        self.update_interval = update_interval
        self.help_text = help_text

        self.label_element = None
        self.value_element = None
        self.status_element = None
        self.container = None
        self.visible = False
        self._animation_timer = None
        self._update_timer = None
        self.alert_errors = alert_errors
        self.set_value(value, immediate=True)  # Use setter to clamp initial value

    def show(
        self,
        width: typing.Optional[str] = None,
        height: typing.Optional[str] = None,
        label: typing.Optional[str] = None,
        show_label: bool = True,
        help_text: typing.Optional[str] = None,
    ) -> ui.card:
        """
        Display the meter as a UI component.

        :param width: Width of the meter (overrides default if provided)
        :param height: Height of the meter (overrides default if provided)
        :param label: Label for the meter (overrides default if provided)
        :param show_label: Whether to display the label
        :param help_text: Optional help text for the meter
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
                border: 2px dotted {self.theme_color};
                border-radius: 8px;
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
        self.container.tooltip(help_text or self.help_text or display_label)

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

    def _cancel_timers(self):
        """Cancel timers to free resources."""
        if self._animation_timer is not None:
            try:
                if self._animation_timer.active:
                    self._animation_timer.deactivate()
                self._animation_timer.cancel()
            except Exception:
                pass
            self._animation_timer = None

        if self._update_timer is not None:
            try:
                if self._update_timer.active:
                    self._update_timer.deactivate()
                self._update_timer.cancel()
            except Exception:
                pass
            self._update_timer = None

    def __del__(self):
        try:
            self._cancel_timers()
        except Exception:
            pass

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

    def update_viz(self) -> Self:
        """Update the visual display"""
        if self.value_element is None:
            return self

        value_text = f"{self.value:.{self.precision}f}"
        if self.units:
            value_text += f" {self.units}"
        self.value_element.text = value_text
        return self

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
        """Animate value with multi-level acceleration for large differences."""
        try:
            if not self.visible:
                return

            diff = self._target_value - self.value
            abs_diff = abs(diff)

            # Snap to target if very close
            if abs_diff < 0.01:
                self.value = self._target_value
                self.update_viz()
                return

            base_step = self.animation_speed * self.animation_interval
            base_step = min(base_step, 10)

            # Multi-level scaling
            if abs_diff > 1000:
                # Very large jump, snap instantly
                step = base_step * 20
            elif abs_diff > 200:
                # Large jump, fast animation
                step = base_step * 10
            elif abs_diff > 50:
                # Medium jump, moderate acceleration
                step = base_step * 5
            else:
                # Small jump, normal speed
                step = base_step

            # Prevent overshoot
            if step > abs_diff:
                step = abs_diff

            # Apply direction
            self.value += step if diff > 0 else -step
            self.update_viz()
        except RuntimeError as e:
            # Handle parent slot deletion
            if "parent slot" in str(e).lower():
                self._cancel_timers()
        except Exception:
            # Silently ignore other errors during cleanup
            pass

    def _update_value(self) -> None:
        """
        Update value from external function if provided.

        To be called periodically by timer.
        """
        try:
            if self.update_func is not None:
                new_value = self.update_func()
                if new_value is not None:
                    self.set_value(new_value, immediate=False)
        except RuntimeError as e:
            # Handle parent slot deletion
            if "parent slot" in str(e).lower():
                self._cancel_timers()
        except Exception as exc:
            if self.alert_errors:
                try:
                    show_alert(f"Error updating {self.label}: {exc}", severity="error")
                except Exception:
                    pass
            logger.error(f"Error in update function: {exc}", exc_info=True)

    def set_value(self, value: float, immediate: bool = False) -> Self:
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

    def set_visibility(self, visible: bool) -> Self:
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
    Flow meter with visual flow indication. Shows animated flow direction and rate.
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
        precision: int = 2,
        theme_color: str = "blue",
        help_text: typing.Optional[str] = None,
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
            precision=precision,
            theme_color=theme_color,
            help_text=help_text,
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
            ui.html(sanitize=False)
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

    def update_viz(self) -> Self:
        """Update display including flow visualization"""
        super().update_viz()
        if self.flow_viz is None:
            return self

        # Calculate flow intensity based on value
        intensity = (
            (self.value - self.min) / (self.max - self.min)
            if self.max > self.min
            else 0
        )
        self.flow_viz.content = self.get_svg(intensity)
        return self

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


class MassFlowMeter(FlowMeter):
    """
    Mass flow meter with visual flow indication. Shows animated flow direction and rate.
    """

    def __init__(
        self,
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 100.0,
        units: str = "kg/sec",
        label: str = "Mass Flow Meter",
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
        precision: int = 2,
        theme_color: str = "blue",
        help_text: typing.Optional[str] = None,
    ) -> None:
        super().__init__(
            value=value,
            min_value=min_value,
            max_value=max_value,
            units=units,
            label=label,
            flow_direction=flow_direction,
            width=width,
            height=height,
            alarm_high=alarm_high,
            alarm_low=alarm_low,
            animation_speed=animation_speed,
            animation_interval=animation_interval,
            update_func=update_func,
            update_interval=update_interval,
            precision=precision,
            theme_color=theme_color,
            help_text=help_text,
        )


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
        precision: int = 2,
        theme_color: str = "blue",
        help_text: typing.Optional[str] = None,
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
            precision=precision,
            theme_color=theme_color,
            help_text=help_text,
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
            ui.html(sanitize=False)
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

    def update_viz(self) -> Self:
        """Update display including gauge"""
        super().update_viz()
        if self.gauge_element is None:
            return self
        self.gauge_element.content = self.get_svg()
        return self

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
        precision: int = 1,
        theme_color: str = "blue",
        help_text: typing.Optional[str] = None,
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
            precision=precision,
            theme_color=theme_color,
            help_text=help_text,
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
            ui.html(sanitize=False)
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

    def update_viz(self) -> Self:
        """Update display including thermometer"""
        super().update_viz()
        if self.thermo_element is None:
            return self
        self.thermo_element.content = self.get_svg()
        return self

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
        alert_errors: bool = True,
        theme_color: str = "blue",
        help_text: typing.Optional[str] = None,
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
        :param alert_errors: Whether to show alerts on setter function errors
        :param theme_color: Theme color for styling
        :param help_text: Optional help text to display as a tooltip
        """
        self.value = 0.0
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
        self.theme_color = theme_color
        self.precision = int(precision) if precision else 0
        self.help_text = help_text

        # UI elements
        self.container = None
        self.label_element = None
        self.slider_element = None
        self.input_element = None
        self.status_indicator = None
        self.alert_errors = alert_errors
        self.set_value(value)  # Use setter to ensure value is within bounds

    def show(
        self,
        width: typing.Optional[str] = None,
        height: typing.Optional[str] = None,
        label: typing.Optional[str] = None,
        show_label: bool = True,
        help_text: typing.Optional[str] = None,
    ) -> ui.card:
        """
        Display the regulator as a UI component.

        :param width: Width of the regulator (overrides default if provided)
        :param height: Height of the regulator (overrides default if provided)
        :param label: Label for the regulator (overrides default if provided)
        :param show_label: Whether to display the label
        :param help_text: Optional help text to display as a tooltip
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
                border-radius: 8px;
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
        self.container.tooltip(help_text or self.help_text or display_label)

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
                    f'<div class="w-2 h-2 rounded-full ml-1" style="background-color: {self.get_status_color()};"></div>',
                    sanitize=False,
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
            .props(
                f"label-always color={self.theme_color} background={self.theme_color}"
            )
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
                    if self.alert_errors:
                        show_alert(
                            f"Error setting regulator value on target: {e}",
                            severity="error",
                        )
                    logger.error(
                        f"Error in regulator setter function: {e}", exc_info=True
                    )

        # Connect events
        self.slider_element.on(
            "update:model-value", lambda e: update_value(e.args), throttle=1.5
        )
        self.input_element.on(
            "update:model-value", lambda e: update_value(e.args), throttle=1.5
        )

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

    def set_value(self, value: float) -> Self:
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
        return self

    def get_value(self) -> float:
        """Get the current regulator value."""
        return self.value


class ValveState(str, Enum):
    """Valve state enumeration."""

    OPEN = "open"
    CLOSED = "closed"

    def __str__(self) -> str:
        return self.value


class Valve:
    """Simple valve component that can be positioned at pipe start or end."""

    def __init__(
        self,
        position: typing.Literal["start", "end"] = "start",
        state: ValveState = ValveState.OPEN,
        name: typing.Optional[str] = None,
    ):
        """
        Initialize a valve.

        :param position: Position of valve - "start" or "end" of pipe
        :param state: Initial valve state (OPEN or CLOSED)
        :param name: Optional name for the valve
        """
        if position not in ["start", "end"]:
            raise ValueError("Valve position must be 'start' or 'end'")

        self.position = position
        self._state = state
        self.name = name or f"Valve-{id(self)}"

    @property
    def state(self) -> ValveState:
        """Current valve state."""
        return self._state

    def is_open(self) -> bool:
        """Check if valve is open."""
        return self._state == ValveState.OPEN

    def is_closed(self) -> bool:
        """Check if valve is closed."""
        return self._state == ValveState.CLOSED

    def open(self) -> Self:
        """Open the valve."""
        self._state = ValveState.OPEN
        return self

    def close(self) -> Self:
        """Close the valve."""
        self._state = ValveState.CLOSED
        return self

    def toggle(self) -> Self:
        """Toggle valve state between open and closed."""
        if self.is_open():
            self.close()
        else:
            self.open()
        return self

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.name!r}, "
            f"position={self.position!r}, state={self._state.value!r})"
        )


class PipelineConnectionError(Exception):
    """Exception raised when pipes in a pipeline are not properly connected."""

    pass


def check_direction_compatibility(*directions: PipeDirection) -> bool:
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


class PipeLeak:
    """Represents a physical leak in a pipe section."""

    def __init__(
        self,
        location: float,
        diameter: PlainQuantity[float],
        discharge_coefficient: float = 0.6,
        active: bool = True,
        name: typing.Optional[str] = None,
    ):
        if diameter.magnitude <= 0:
            raise ValueError("LeakInfo diameter must be positive")
        if not (0.0 <= location <= 1.0):
            raise ValueError("Location fraction must be between 0.0 and 1.0")

        self.location = location
        self.diameter = diameter
        self.discharge_coefficient = discharge_coefficient
        self.active = active
        self.name = name

    @property
    def leak_area(self) -> PlainQuantity[float]:
        """Cross-sectional area of the leak opening."""
        return (math.pi * self.diameter.to("m") ** 2) / 4

    def compute_rate(
        self,
        pipe_pressure: PlainQuantity[float],
        ambient_pressure: PlainQuantity[float] = Quantity(14.7, "psi"),
        fluid_density: PlainQuantity[float] = Quantity(1000, "kg/m^3"),
    ) -> PlainQuantity[float]:
        """
        Calculate volumetric leak rate based on orifice flow equation.

        Uses the standard orifice flow equation:
        Q = Cd * A * sqrt(2 * ΔP / ρ)

        Where:
        - Q = volumetric flow rate
        - Cd = discharge coefficient
        - A = orifice area
        - ΔP = pressure difference across orifice
        - ρ = fluid density

        :param pipe_pressure: Internal pressure at leak location
        :param ambient_pressure: External pressure (usually atmospheric). This is the pressure outside/surrounding the pipe.
        :param fluid_density: Density of the leaking fluid
        :return: Volumetric leak rate
        """
        if not self.active:
            return Quantity(0.0, "m^3/s")

        # Calculate pressure difference
        pressure_diff = pipe_pressure.to("Pa") - ambient_pressure.to("Pa")

        # If internal pressure is lower than external, no leak occurs
        if pressure_diff.magnitude <= 0:
            return Quantity(0.0, "m^3/s")

        # Apply orifice flow equation
        # Q = Cd * A * sqrt(2 * ΔP / ρ)
        density_si = fluid_density.to("kg/m^3")
        area_si = self.leak_area.to("m^2")

        flow_rate_m3_s = (
            self.discharge_coefficient
            * area_si.magnitude
            * math.sqrt(2 * pressure_diff.magnitude / density_si.magnitude)
        )
        leak_rate = Quantity(flow_rate_m3_s, "m^3/s")
        return leak_rate

    def get_severity(self, flow_rate: PlainQuantity[float]) -> str:
        """
        Get a qualitative description of leak severity based on diameter and flow rate.

        Combines leak diameter and flow rate to determine severity:
        - Larger diameter with higher flow rate = more severe
        - Smaller diameter with lower flow rate = less severe

        :param flow_rate: Flow rate through the leak in volumetric units
        :return: Severity string: "pinhole", "small", "moderate", "large", or "critical"
        """
        diameter_mm = self.diameter.to("mm").magnitude
        flow_rate_lpm = flow_rate.to("L/min").magnitude  # Liters per minute

        # Calculate a combined severity score
        # Diameter contributes 60%, flow rate contributes 40%
        # Normalize diameter (0-50mm range) and flow rate (0-1000 L/min range)
        diameter_score = min(diameter_mm / 50.0, 1.0) * 60
        flow_rate_score = min(flow_rate_lpm / 1000.0, 1.0) * 40
        combined_score = diameter_score + flow_rate_score

        # Map combined score to severity levels
        if combined_score < 10:
            return "pinhole"
        elif combined_score < 25:
            return "small"
        elif combined_score < 50:
            return "moderate"
        elif combined_score < 75:
            return "large"
        return "critical"

    @classmethod
    def from_area(
        cls, location: float, area: PlainQuantity[float], **kwargs
    ) -> "PipeLeak":
        """Create a leak from area instead of diameter."""
        area_m2 = area.to("m^2").magnitude
        diameter_m = 2 * math.sqrt(area_m2 / math.pi)
        leak_diameter = Quantity(diameter_m, "m")
        return cls(location=location, diameter=leak_diameter, **kwargs)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.name!r}, location={self.location:.2f}, "
            f"diameter={self.diameter}, discharge_coefficient={self.discharge_coefficient}, "
            f"active={self.active})"
        )


class Pipe:
    """Pipe component for flow system visualization."""

    def __init__(
        self,
        length: PlainQuantity[float],
        internal_diameter: PlainQuantity[float],
        upstream_pressure: PlainQuantity[float],
        downstream_pressure: PlainQuantity[float],
        upstream_temperature: typing.Optional[PlainQuantity[float]] = None,
        material: str = "Steel",
        roughness: PlainQuantity[float] = Quantity(0, "m"),
        efficiency: float = 1.0,
        elevation_difference: PlainQuantity[float] = Quantity(0, "m"),
        fluid: typing.Optional[Fluid] = None,
        direction: typing.Union[PipeDirection, str] = PipeDirection.EAST,
        name: typing.Optional[str] = None,
        leaks: typing.Optional[typing.Sequence[PipeLeak]] = None,
        start_valve: typing.Optional[Valve] = None,
        end_valve: typing.Optional[Valve] = None,
        scale_factor: float = 0.1,
        max_flow_rate: PlainQuantity[float] = Quantity(10.0, "ft^3/s"),
        ambient_pressure: PlainQuantity[float] = Quantity(14.7, "psi"),
        flow_type: FlowType = FlowType.COMPRESSIBLE,
        alert_errors: bool = True,
    ) -> None:
        """
        Initialize a Pipe component.

        :param length: Length of the pipe
        :param internal_diameter: Internal diameter of the pipe
        :param upstream_pressure: Upstream pressure of the pipe
        :param downstream_pressure: Downstream pressure of the pipe
        :param material: Material of the pipe
        :param roughness: Absolute roughness of the pipe in meters
        :param efficiency: Efficiency of the pipe (0 to 1)
        :param elevation_difference: Elevation difference between upstream and downstream outlets of the pipe
        :param fluid: Optional Fluid instance with fluid properties
        :param direction: PipeDirection enum indicating flow direction
        :param name: Optional name for the pipe
        :param leaks: Optional sequence of PipeLeak instances representing leaks in the pipe
        :param start_valve: Optional valve at the start of the pipe
        :param end_valve: Optional valve at the end of the pipe
        :param scale_factor: Display scale factor for converting physical units to pixels (pixels per millimeter).
            Example: A scale_factor of 0.1 means 1 pixel represents 10 mm (1 cm).
        :param max_flow_rate: Maximum expected flow rate for intensity normalization
        :param reynolds_number: Reynolds number of the flow in the pipe
        :param ambient_pressure: Ambient pressure outside the pipe (usually atmospheric)
        :param flow_type: Type of flow (incompressible or compressible)
        :param alert_errors: Whether to show alerts on errors
        """
        self.name = name or f"Pipe-{id(self)}"
        self.direction = PipeDirection(direction)
        self.length = length
        if self.length.magnitude <= 0:
            raise ValueError("Pipe length must be greater than zero.")

        self.internal_diameter = internal_diameter
        if self.internal_diameter.magnitude <= 0:
            raise ValueError("Pipe internal diameter must be greater than zero.")

        self.upstream_pressure = upstream_pressure
        self.downstream_pressure = downstream_pressure
        self._upstream_temperature = upstream_temperature
        self.material = material
        self.roughness = roughness
        self.efficiency = efficiency
        self.elevation_difference = elevation_difference
        self._flow_type = flow_type
        self.ambient_pressure = ambient_pressure
        self.alert_errors = alert_errors

        self._fluid = fluid if fluid else None
        self.scale_factor = scale_factor
        self._flow_rate = Quantity(0.0, "ft^3/s")
        self.max_flow_rate = max_flow_rate
        self._leaks: typing.List[PipeLeak] = []
        self._ignore_leaks = False
        self._pipeline: typing.Optional[Pipeline] = (
            None  # Refrences the pipeline it belongs to
        )
        if leaks:
            for leak in leaks:
                self.add_leak(leak, sync=False)

        self._start_valve: typing.Optional[Valve] = start_valve
        self._end_valve: typing.Optional[Valve] = end_valve

        self.pipe_viz = None  # Placeholder for pipe visualization element
        self.sync()

    @property
    def fluid(self) -> typing.Optional[Fluid]:
        """Fluid properties at pipe's upstream pressure and temperature."""
        if (fluid := self._fluid) is None:
            return None

        upstream_pressure = self.upstream_pressure
        if upstream_pressure.magnitude == 0:
            return self._fluid

        return fluid.for_pressure_temperature(
            pressure=upstream_pressure,
            temperature=self.upstream_temperature,
        )

    @property
    def upstream_fluid(self) -> typing.Optional[Fluid]:
        """Fluid properties at the pipe inlet."""
        return self.fluid

    inlet_fluid = upstream_fluid  # Alias for clarity

    @property
    def downstream_fluid(self) -> typing.Optional[Fluid]:
        """Fluid properties at the pipe outlet."""
        if self.fluid is None or self.downstream_pressure.magnitude == 0:
            return None

        outlet_temp = self.downstream_temperature
        if outlet_temp is None:
            return None

        return self.fluid.for_pressure_temperature(
            pressure=self.downstream_pressure,
            temperature=outlet_temp,
        )

    outlet_fluid = downstream_fluid  # Alias for clarity

    @property
    def upstream_temperature(self) -> PlainQuantity[float]:
        """Temperature of the pipe fluid at the pipe inlet."""
        if self._upstream_temperature is None and self._fluid is not None:
            self._upstream_temperature = self._fluid.temperature
        return typing.cast(PlainQuantity[float], self._upstream_temperature)

    @property
    def downstream_temperature(self) -> typing.Optional[PlainQuantity[float]]:
        """Temperature of the pipe fluid at the pipe outlet."""
        if self.flow_rate.magnitude == 0:
            return Quantity(0, "degF")

        inlet_fluid = self.inlet_fluid
        if inlet_fluid is None:
            return None

        inlet_temp = inlet_fluid.temperature
        if inlet_fluid.phase == "gas" and self.flow_type == FlowType.COMPRESSIBLE:
            try:
                jt_coefficient = (
                    inlet_fluid.get_joule_thomson_coefficient(
                        pressure=self.upstream_pressure
                    )
                    .to("degF/psi")
                    .magnitude
                )
            except ValueError:
                ui.notify(
                    f"Could not compute Joule-Thomson coefficient for fluid in pipe - {self.name!r}."
                    " Ensure fluid is a gas and has valid properties at the given pressure.",
                    type="negative",
                    multi_line=True,
                )
                jt_coefficient = 0.0
        else:
            jt_coefficient = 0.0

        pressure_drop = self.pressure_drop.to("psi").magnitude
        # T2 = T1 + μ(JT) * ΔP
        outlet_temp_value = inlet_temp.to("degF").magnitude + (
            jt_coefficient * pressure_drop
        )
        return Quantity(outlet_temp_value, "degF")

    @property
    def pressure_drop(self) -> PlainQuantity[float]:
        """
        The pressure drop across the pipe in psi.
        """
        upstream = self.upstream_pressure.to("psi").magnitude
        downstream = self.downstream_pressure.to("psi").magnitude
        return Quantity(upstream - downstream, "psi")

    @property
    def relative_roughness(self) -> float:
        """
        The relative roughness of the pipe.
        """
        try:
            return (
                self.roughness.to("m").magnitude
                / self.internal_diameter.to("m").magnitude
            )
        except ZeroDivisionError:
            if self.alert_errors:
                show_alert(
                    f"Error calculating relative roughness of pipe - {self.name!r}: Internal diameter is zero.",
                    severity="error",
                )
            return 0.0

    @property
    def cross_sectional_area(self) -> PlainQuantity[float]:
        """
        The cross-sectional area of the pipe in ft².
        """
        radius = self.internal_diameter.to("ft").magnitude / 2.0
        area_ft2 = math.pi * (radius**2)
        return Quantity(area_ft2 * ureg.ft**2, "ft^2")

    @property
    def volume(self) -> PlainQuantity[float]:
        """
        The volume of the pipe in ft³.
        """
        area = self.cross_sectional_area.to("ft^2").magnitude
        length_ft = self.length.to("ft").magnitude
        volume_ft3 = area * length_ft
        return Quantity(volume_ft3 * ureg.ft**3, "ft^3")

    @property
    def flow_rate(self) -> PlainQuantity[float]:
        """
        Current effective volumetric flow rate IN the pipe in (ft³/s).

        If start valve is closed, no flow enters the pipe.
        Considers leaks if present and not ignored.
        """
        # If start valve is closed, no flow enters pipe
        if self._start_valve is not None and self._start_valve.is_closed():
            return Quantity(0.0, "ft^3/s")

        if self._ignore_leaks or not self.fluid:
            return self._flow_rate
        return self._flow_rate - self.leak_rate

    @property
    def leaks(self) -> typing.Iterator[PipeLeak]:
        """Iterable of active leaks in the pipe."""
        return (leak for leak in self._leaks if leak.active)

    @property
    def leak_rate(self) -> PlainQuantity[float]:
        """
        Total volumetric leak rate from all active leaks in the pipe in (ft³/s).

        Note: Computation in here should not use the `flow_rate` and `mass_rate`
        or any other methods or attribute that uses these properties to avoid circular dependency.
        Use `_flow_rate` directly for internal calculations.
        """
        if self._ignore_leaks or not self.fluid:
            return Quantity(0.0, "ft^3/s")

        total_leak_rate = sum(
            leak.compute_rate(
                # Use the estimated pressure at the leak location
                pipe_pressure=self.estimate_pressure_at_location(leak.location),
                ambient_pressure=self.ambient_pressure,
                fluid_density=self.fluid.density,
            )
            .to("ft^3/s")
            .magnitude
            for leak in self.leaks
        )
        return Quantity(total_leak_rate, "ft^3/s")

    def estimate_pressure_at_location(self, location: float) -> PlainQuantity[float]:
        """
        Estimate the pressure at a specific location along the pipe length.

        :param location: Fractional location along the pipe (0.0 = start, 1.0 = end)
        :return: Estimated pressure at the specified location
        """
        if not (0.0 <= location <= 1.0):
            raise ValueError("Location fraction must be between 0.0 and 1.0")

        solver = None
        if self._pipeline is not None:
            solver = self._pipeline._solver

        pipe_copy = self.copy(include_leaks=True, include_valves=False)
        if solver is not None or (solver := getattr(self, "_solver", None)) is not None:
            local_pressure = solver.estimate_pressure_at_location(pipe_copy, location)
            return local_pressure

        # Create a dummy pipeline for the pipe and capture its solver
        dummy_pipeline = self.get_pipeline_type()(
            pipes=[pipe_copy],
            fluid=self.fluid,
            flow_type=self.flow_type,
            ignore_leaks=self._ignore_leaks,
            alert_errors=False,
        )
        # Cache solver instance for future use
        self._solver = dummy_pipeline._solver
        local_pressure = self._solver.estimate_pressure_at_location(pipe_copy, location)
        return local_pressure

    @property
    def flow_type(self) -> FlowType:
        """Flow type."""
        return self._flow_type

    @property
    def flow_equation(self) -> typing.Optional[FlowEquation]:
        """Appropriate pipe flow equation based on pipe and fluid properties."""
        if (fluid := self.fluid) is None:
            return None

        try:
            flow_equation = determine_pipe_flow_equation(
                pressure_drop=self.pressure_drop,
                upstream_pressure=self.upstream_pressure,
                internal_diameter=self.internal_diameter,
                length=self.length,
                fluid_phase=fluid.phase,
                flow_type=self._flow_type,
            )
        except Exception:
            if self.alert_errors:
                show_alert(
                    f"Error determining flow equation for pipe - {self.name!r}.",
                    severity="error",
                )
            logger.error(
                f"Error determining flow equation for pipe - {self.name!r}.",
                exc_info=True,
            )
            return None
        return flow_equation

    @property
    def mass_rate(self) -> PlainQuantity[float]:
        """Mass flow rate in pipe in (lb/s) based on current flow rate and fluid density."""
        if self.fluid is None:
            return Quantity(0.0, "lb/s")
        density = self.fluid.density.to("lb/ft^3").magnitude
        volumetric_rate = self.flow_rate.to("ft^3/s").magnitude
        mass_rate = Quantity(density * volumetric_rate, "lb/s")
        return mass_rate

    @property
    def flow_velocity(self) -> PlainQuantity[float]:
        """Flow velocity of the fluid in the pipe in (ft/s) based on current flow rate and pipe cross-sectional area."""
        area = self.cross_sectional_area.to("ft^2").magnitude
        if area <= 0:
            if self.alert_errors:
                show_alert(
                    f"Error calculating flow velocity in pipe - {self.name!r}: Cross-sectional area is zero.",
                    severity="error",
                )
            return Quantity(0.0, "ft/s")
        volumetric_rate = self.flow_rate.to("ft^3/s").magnitude
        return Quantity(volumetric_rate / area, "ft/s")

    @property
    def reynolds_number(self) -> typing.Optional[float]:
        """Reynolds number of the flow in the pipe."""
        fluid = self.fluid
        if fluid is None:
            return None

        flow_rate = self.flow_rate
        if flow_rate.magnitude <= 0:
            return 0.0
        return compute_reynolds_number(
            current_flow_rate=flow_rate,
            pipe_internal_diameter=self.internal_diameter,
            fluid_density=fluid.density,
            fluid_dynamic_viscosity=fluid.viscosity,
        )

    @property
    def is_leaking(self) -> bool:
        """Whether the pipe has any active leaks."""
        if self._ignore_leaks or self.fluid is None or self.flow_rate.magnitude <= 0:
            return False
        return any(leak.active for leak in self._leaks)

    @property
    def effective_outlet_flow_rate(self) -> PlainQuantity[float]:
        """
        Effective flow rate OUT of the pipe (ft³/s).

        If end valve is closed, flow occurs in pipe but doesn't exit to next pipe.
        """
        # If end valve is closed, no flow exits pipe
        if self._end_valve is not None and self._end_valve.is_closed():
            return Quantity(0.0, "ft^3/s")
        return self.flow_rate

    @property
    def valve(self) -> typing.Optional[Valve]:
        """Get the first valve attached to this pipe (start valve if exists, else end valve)."""
        return self._start_valve or self._end_valve

    @property
    def has_valve(self) -> bool:
        """Check if pipe has any valve."""
        return self._start_valve is not None or self._end_valve is not None

    def get_valve(
        self, position: typing.Literal["start", "end"]
    ) -> typing.Optional[Valve]:
        """Get valve at specified position."""
        return self._start_valve if position == "start" else self._end_valve

    def add_valve(
        self,
        valve: typing.Optional[Valve] = None,
        position: typing.Literal["start", "end"] = "start",
        *,
        sync: bool = True,
    ) -> Self:
        """
        Add a valve to the pipe at specified position.

        :param valve: Valve instance to add (creates default if None)
        :param position: Position for valve or for new valve if valve is None
        :param sync: Whether to synchronize pipe properties after adding valve
        :return: self for method chaining
        """
        if valve is None:
            valve = Valve(position=position)

        if valve.position == "start":
            if self._start_valve is not None:
                raise ValueError(f"Pipe {self.name!r} already has a start valve.")
            self._start_valve = valve
        else:  # "end"
            if self._end_valve is not None:
                raise ValueError(f"Pipe {self.name!r} already has an end valve.")
            self._end_valve = valve

        if sync:
            self.sync()
        return self

    def remove_valve(
        self, position: typing.Literal["start", "end"], *, sync: bool = True
    ) -> typing.Optional[Valve]:
        """
        Remove valve at specified position.

        :param position: Position of valve to remove
        :param sync: Whether to synchronize pipe properties after removing valve
        :return: The removed Valve instance, or None if no valve existed
        """
        if position == "start":
            removed_valve = self._start_valve
            self._start_valve = None
        else:
            removed_valve = self._end_valve
            self._end_valve = None

        if sync:
            self.sync()
        return removed_valve

    def open_valve(
        self, position: typing.Literal["start", "end"], *, sync: bool = True
    ) -> Self:
        """
        Open valve at specified position.

        :param position: Position of valve to open
        :param sync: Whether to synchronize pipe properties after opening valve
        :return: self for method chaining
        """
        valve = self.get_valve(position)
        if valve is None:
            raise ValueError(f"Pipe {self.name!r} has no {position} valve.")

        valve.open()
        if sync:
            self.sync()
        return self

    def close_valve(
        self, position: typing.Literal["start", "end"], *, sync: bool = True
    ) -> Self:
        """
        Close valve at specified position.

        :param position: Position of valve to close
        :param sync: Whether to synchronize pipe properties after closing valve
        :return: self for method chaining
        """
        valve = self.get_valve(position)
        if valve is None:
            raise ValueError(f"Pipe {self.name!r} has no {position} valve.")

        valve.close()
        if sync:
            self.sync()
        return self

    def toggle_valve(
        self, position: typing.Literal["start", "end"], *, sync: bool = True
    ) -> Self:
        """
        Toggle valve state at specified position.

        :param position: Position of valve to toggle
        :param sync: Whether to synchronize pipe properties after toggling valve
        :return: self for method chaining
        """
        valve = self.get_valve(position)
        if valve is None:
            raise ValueError(f"Pipe {self.name!r} has no {position} valve.")

        valve.toggle()
        if sync:
            self.sync()
        return self

    def has_closed_valve(self) -> bool:
        """Check if pipe has any closed valve."""
        if self._start_valve and self._start_valve.is_closed():
            return True
        if self._end_valve and self._end_valve.is_closed():
            return True
        return False

    def has_flow(self) -> bool:
        """Check if there is flow in the pipe."""
        return self.flow_rate.magnitude > 0

    def add_leak(self, leak: PipeLeak, *, sync: bool = False) -> Self:
        """
        Add a leak to the pipe and optionally recalculate flow rate.

        :param leak: PipeLeak instance to add
        :param sync: Whether to synchronize pipe properties after adding leak
        :return: self or updated Pipe instance
        """
        # Check leak area is less than pipe cross-sectional area
        if leak.leak_area.magnitude >= self.cross_sectional_area.magnitude:
            raise ValueError(
                "LeakInfo area must be less than the pipe's cross-sectional area"
            )

        self._leaks.append(leak)
        if sync:
            self.sync()

        if (
            self._flow_rate.magnitude > 0
            and self.leak_rate.magnitude >= self._flow_rate.magnitude
        ):
            if self.alert_errors:
                show_alert(
                    f"Warning: Unphysical condition! Total leak rate in pipe - {self.name!r} exceeds or equals flow rate.",
                    severity="warning",
                )
            logger.warning(
                f"Total leak rate in pipe - {self.name!r} exceeds or equals flow rate."
            )
        return self

    def remove_leak(self, index: int, *, sync: bool = False) -> PipeLeak:
        """
        Remove a leak from the pipe by index and optionally recalculate flow rate.

        :param index: Index of the leak to remove
        :param sync: Whether to synchronize pipe properties after removing leak
        :return: The removed `PipeLeak` object
        """
        if index < 0 or index >= len(self._leaks):
            raise IndexError("LeakInfo index out of range")

        removed_leak = self._leaks.pop(index)
        if sync:
            self.sync()
        return removed_leak

    def clear_leaks(self, *, sync: bool = False) -> Self:
        """
        Remove all leaks from the pipe and optionally recalculate flow rate.

        :param sync: Whether to synchronize pipe properties after clearing leaks
        :return: self or updated Pipe instance
        """
        self._leaks.clear()
        if sync:
            self.sync()
        return self

    def set_ignore_leaks(self, ignore: bool = True, *, sync: bool = False) -> Self:
        """
        Set whether to ignore leaks in flow calculations and optionally recalculate flow rate.

        :param ignore: Whether to ignore leaks
        :param sync: Whether to synchronize pipe properties after changing ignore setting
        :return: self or updated Pipe instance
        """
        self._ignore_leaks = ignore
        if sync:
            self.sync()
        return self

    def set_fluid(self, fluid: Fluid, *, sync: bool = True) -> Self:
        """
        Update pipe fluid and optionally recalculate flow rate.

        :param fluid: New `Fluid` instance to set
        :param sync: Whether to synchronize pipe properties after changing fluid
        :return: self or updated Pipe instance
        """
        self._fluid = fluid
        if sync:
            self.sync()
        return self

    def set_flow_type(self, flow_type: FlowType, *, sync: bool = True) -> Self:
        """
        Update flow type and optionally recalculate flow rate.

        :param flow_type: New FlowType to set
        :param sync: Whether to synchronize pipe properties after changing flow type
        :return: self or updated Pipe instance
        """
        self._flow_type = flow_type
        if sync:
            self.sync()
        return self

    def set_max_flow_rate(
        self, max_flow_rate: PlainQuantity[float], *, update_viz: bool = True
    ) -> Self:
        """
        Update maximum expected flow rate and optionally update visualization.

        :param max_flow_rate: New maximum flow rate to set
        :param update_viz: Whether to update visualization after changing max flow rate
        :return: self or updated Pipe instance
        """
        self.max_flow_rate = max_flow_rate
        if update_viz:
            self.update_viz()
        return self

    def set_scale_factor(self, scale_factor: float, *, update_viz: bool = True) -> Self:
        """
        Update display scale factor and optionally update visualization.

        :param scale_factor: New scale factor to set
        :param update_viz: Whether to update visualization after changing scale factor
        :return: self or updated Pipe instance
        """
        self.scale_factor = scale_factor
        if update_viz:
            self.update_viz()
        return self

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
            ui.html(sanitize=False)
            .classes("flex flex-col items-center justify-center")
            .style(f"width: {width}; height: {height};")
        )

        with container:
            if show_label and label:
                ui.label(label).classes("text-lg font-semibold mb-2 text-center")

            # Create the SVG visualization
            self.pipe_viz = ui.html(str(self.get_svg()), sanitize=False).classes(
                "w-full h-full"
            )
        return container

    def update_viz(self) -> Self:
        """
        Update the pipe visualization with current properties and flow rate.

        This method regenerates the SVG content based on the current state.
        """
        if self.pipe_viz is not None:
            self.pipe_viz.content = self.get_svg()
        return self

    def get_svg(self) -> SVGComponent:
        """
        Generate the SVG content for the pipe based on its direction.

        :return: A `SVGComponent` representing the pipe
        """
        modular_components = []

        # Create pipe component first
        if not self._ignore_leaks:
            leaks = []
            for leak in self.leaks:
                # Calculate actual leak flow rate for severity assessment
                # If the pipe has fluid and flow, compute leak rate
                if self.fluid and self.flow_rate.magnitude > 0:
                    leak_flow_rate = leak.compute_rate(
                        pipe_pressure=self.estimate_pressure_at_location(leak.location),
                        ambient_pressure=self.ambient_pressure,
                        fluid_density=self.fluid.density,
                    )
                else:
                    # No fluid, assume zero flow rate
                    leak_flow_rate = Quantity(0.0, "ft^3/s")

                leaks.append(
                    LeakInfo(
                        location=leak.location,
                        severity=leak.get_severity(leak_flow_rate),
                    )
                )
        else:
            leaks = None

        if self.direction in [PipeDirection.NORTH, PipeDirection.SOUTH]:
            pipe_component = build_vertical_pipe_component(
                direction=self.direction,
                internal_diameter=self.internal_diameter,
                length=self.length,
                flow_rate=self.flow_rate,
                max_flow_rate=self.max_flow_rate,
                scale_factor=self.scale_factor,
                canvas_width=100.0,
                canvas_height=400.0,
                leaks=leaks,
            )
        else:
            pipe_component = build_horizontal_pipe_component(
                direction=self.direction,
                internal_diameter=self.internal_diameter,
                length=self.length,
                flow_rate=self.flow_rate,
                max_flow_rate=self.max_flow_rate,
                scale_factor=self.scale_factor,
                canvas_width=400.0,
                canvas_height=100.0,
                leaks=leaks,
            )

        # Add start valve if present (before pipe)
        if self._start_valve is not None:
            valve_component = build_straight_valve_component(
                component1=pipe_component,
                component2=pipe_component,  # Both same since single pipe
                state=self._start_valve.state.value,
            )
            modular_components.append(valve_component)

        # Add the pipe itself
        modular_components.append(pipe_component)

        # Add end valve if present (after pipe)
        if self._end_valve is not None:
            valve_component = build_straight_valve_component(
                component1=pipe_component,
                component2=pipe_component,  # Both same since single pipe
                state=self._end_valve.state.value,
            )
            modular_components.append(valve_component)

        # If only one component (no valves), return its SVG directly
        if len(modular_components) == 1:
            return modular_components[0].get_svg_component()

        modular_pipeline = PipelineComponents(modular_components)
        return modular_pipeline.get_svg_component()

    def set_flow_rate(
        self, flow_rate: typing.Union[PlainQuantity[float], float]
    ) -> Self:
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
        self._flow_rate = flow_rate_q
        return self

    def sync(self) -> Self:
        """Synchronize the pipe properties based on current fluid and pressures."""
        flow_equation = self.flow_equation
        fluid = self.fluid
        if flow_equation is None or fluid is None:
            return self.set_flow_rate(0.0)

        # Compute Reynolds number
        try:
            reynolds_number = self.reynolds_number
        except Exception:
            if self.alert_errors:
                show_alert(
                    f"Error calculating Reynolds number in pipe - {self.name!r}.",
                    severity="error",
                )
            logger.error(
                f"Error calculating Reynolds number in pipe - {self.name!r}.",
                exc_info=True,
            )
            raise

        try:
            # Calculate flow rate using the appropriate equation
            flow_rate = compute_pipe_flow_rate(
                length=self.length,
                internal_diameter=self.internal_diameter,
                upstream_pressure=self.upstream_pressure,
                downstream_pressure=self.downstream_pressure,
                relative_roughness=self.relative_roughness,
                efficiency=self.efficiency,
                elevation_difference=self.elevation_difference,
                specific_gravity=fluid.specific_gravity,
                temperature=fluid.temperature,
                compressibility_factor=fluid.compressibility_factor,
                reynolds_number=reynolds_number
                or 2000,  # Default to laminar if undefined
                flow_equation=flow_equation,
            )
        except Exception:
            if self.alert_errors:
                show_alert(
                    f"Error calculating flow rate in pipe - {self.name!r}.",
                    severity="error",
                )
            logger.error(
                f"Error calculating flow rate in pipe - {self.name!r}.", exc_info=True
            )
            raise
        self.set_flow_rate(flow_rate)
        return self

    def set_upstream_pressure(
        self,
        pressure: typing.Union[PlainQuantity[float], float],
        check: bool = True,
        sync: bool = False,
    ) -> Self:
        """
        Set upstream pressure and synchronize pipe properties as needed.

        :param pressure: Upstream pressure as Quantity or float (assumed psi if float)
        :param check: Whether to check pressure constraints (default is True)
        :param sync: Whether to synchronize pipe properties after setting pressure (default is False)
        :return: self for method chaining
        """
        if isinstance(pressure, Quantity):
            if pressure.magnitude < 0:
                if self.alert_errors:
                    show_alert(
                        f"Upstream pressure cannot be negative in pipe - {self.name!r}.",
                        severity="error",
                    )
                raise ValueError("Upstream pressure cannot be negative.")
            pressure_q = pressure.to("psi")
        else:
            if pressure < 0:
                if self.alert_errors:
                    show_alert(
                        f"Upstream pressure cannot be negative in pipe - {self.name!r}.",
                        severity="error",
                    )
                raise ValueError("Upstream pressure cannot be negative.")
            pressure_q = Quantity(pressure, "psi")

        if check and (self.downstream_pressure > pressure_q):
            if self.alert_errors:
                show_alert(
                    f"Upstream pressure cannot be less than downstream pressure in pipe - {self.name!r}.",
                    severity="error",
                )
            raise ValueError(
                "Upstream pressure cannot be less than downstream pressure. Flow cannot occur against the pressure gradient."
            )

        self.upstream_pressure = pressure_q
        if sync:
            self.sync()
        return self

    def set_downstream_pressure(
        self,
        pressure: typing.Union[PlainQuantity[float], float],
        check: bool = True,
        sync: bool = False,
    ) -> Self:
        """
        Set downstream pressure and synchronize pipe properties.

        :param pressure: Downstream pressure as Quantity or float (assumed psi if float)
        :param check: Whether to check pressure constraints (default is True)
        :param sync: Whether to synchronize pipe properties after setting pressure (default is False)
        :return: self for method chaining
        """
        if isinstance(pressure, Quantity):
            if pressure.magnitude < 0:
                if self.alert_errors:
                    show_alert(
                        f"Downstream pressure cannot be negative in pipe - {self.name!r}.",
                        severity="error",
                    )
                raise ValueError("Downstream pressure cannot be negative.")
            pressure_q = pressure.to("psi")
        else:
            if pressure < 0:
                if self.alert_errors:
                    show_alert(
                        f"Downstream pressure cannot be negative in pipe - {self.name!r}.",
                        severity="error",
                    )
                raise ValueError("Downstream pressure cannot be negative.")
            pressure_q = Quantity(pressure, "psi")

        if check and (self.upstream_pressure < pressure_q):
            if self.alert_errors:
                show_alert(
                    f"Downstream pressure cannot exceed upstream pressure in pipe - {self.name!r}.",
                    severity="error",
                )
            raise ValueError(
                "Downstream pressure cannot exceed upstream pressure. Flow cannot occur against the pressure gradient."
            )

        self.downstream_pressure = pressure_q
        if sync:
            self.sync()
        return self

    def set_upstream_temperature(
        self, temperature: PlainQuantity[float], *, sync: bool = True
    ) -> Self:
        """
        Update pipe (inlet) fluid temperature and optionally recalculate flow rate.

        :param temperature: New temperature to set
        :param sync: Whether to update flow rate after changing temperature
        :return: self or updated Pipe instance
        """
        self._upstream_temperature = temperature.to("degF")
        if sync:
            self.sync()
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
    ) -> "Pipeline":
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
        if not check_direction_compatibility(self.direction, other.direction):
            error_msg = (
                f"Cannot connect pipes with opposing flow directions: "
                f"{self.direction.value} to {other.direction.value}. "
                f"Pipes flowing in opposite directions cannot be connected."
            )
            if self.alert_errors:
                show_alert(error_msg, severity="error")
            raise PipelineConnectionError(error_msg)

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

    def copy(self, include_valves: bool = True, include_leaks: bool = True) -> Self:
        """
        Create a deep copy of the pipe.

        This method carefully handles:
        - Fluid objects (creates new instance at same conditions)
        - Valves (optional deep copy)
        - Leaks (optional deep copy)
        - Visualization elements (explicitly NOT copied)
        - Avoids circular reference issues

        :param include_valves: Whether to copy valves (default True)
        :param include_leaks: Whether to copy leaks (default True)
        :return: New Pipe instance with copied properties
        """
        # Copy basic Quantity properties (these are immutable-ish)
        new_pipe = self.__class__(
            length=Quantity(self.length.magnitude, self.length.units),
            internal_diameter=Quantity(
                self.internal_diameter.magnitude, self.internal_diameter.units
            ),
            upstream_pressure=Quantity(
                self.upstream_pressure.magnitude, self.upstream_pressure.units
            ),
            downstream_pressure=Quantity(
                self.downstream_pressure.magnitude, self.downstream_pressure.units
            ),
            upstream_temperature=Quantity(
                self._upstream_temperature.magnitude, self._upstream_temperature.units
            )
            if self._upstream_temperature is not None
            else None,
            material=self.material,
            roughness=Quantity(self.roughness.magnitude, self.roughness.units),
            efficiency=self.efficiency,
            elevation_difference=Quantity(
                self.elevation_difference.magnitude, self.elevation_difference.units
            ),
            # Fluid: Create new instance at same conditions (avoids shared reference)
            fluid=self._fluid.for_pressure_temperature(
                pressure=self._fluid.pressure, temperature=self._fluid.temperature
            )
            if self._fluid is not None
            else None,
            direction=self.direction,  # Enum, safe to share
            name=self.name,
            leaks=None,  # Will add later
            start_valve=None,  # Will add later
            end_valve=None,  # Will add later
            scale_factor=self.scale_factor,
            max_flow_rate=Quantity(
                self.max_flow_rate.magnitude, self.max_flow_rate.units
            ),
            ambient_pressure=Quantity(
                self.ambient_pressure.magnitude, self.ambient_pressure.units
            ),
            flow_type=self.flow_type,  # Enum, safe to share
            alert_errors=self.alert_errors,
        )

        # Copy flow rate (this is computed but should be preserved)
        new_pipe._flow_rate = Quantity(self._flow_rate.magnitude, self._flow_rate.units)
        new_pipe._ignore_leaks = self._ignore_leaks

        # Copy valves if requested
        if include_valves:
            if self._start_valve is not None:
                new_pipe._start_valve = Valve(
                    position=self._start_valve.position,  # type: ignore[arg-type]
                    state=self._start_valve.state,
                    name=self._start_valve.name,
                )

            if self._end_valve is not None:
                new_pipe._end_valve = Valve(
                    position=self._end_valve.position,  # type: ignore[arg-type]
                    state=self._end_valve.state,
                    name=self._end_valve.name,
                )

        # Copy leaks if requested
        if include_leaks:
            for leak in self._leaks:
                new_leak = PipeLeak(
                    location=leak.location,
                    diameter=Quantity(leak.diameter.magnitude, leak.diameter.units),
                    discharge_coefficient=leak.discharge_coefficient,
                    active=leak.active,
                    name=leak.name,
                )
                new_pipe._leaks.append(new_leak)

        # Explicitly DO NOT copy visualization elements
        # These should be recreated when show() is called
        new_pipe.pipe_viz = None
        return new_pipe

    def __copy__(self) -> Self:
        """
        Shallow copy support (copy.copy()).
        Creates new pipe with same parameters but no valves/leaks.
        """
        return self.copy(include_valves=False, include_leaks=False)

    def __deepcopy__(self, memo: dict) -> Self:
        """
        Deep copy support (copy.deepcopy()).

        This is called by copy.deepcopy() and must handle the memo dict
        to avoid infinite recursion with circular references.

        :param memo: Memoization dict to track already-copied objects
        :return: Deep copied Pipe instance
        """
        # Check if already copied (handles circular references)
        pipe_id = id(self)
        if pipe_id in memo:
            return memo[pipe_id]

        # Create the copy (this internally handles all the copying)
        new_pipe = self.copy(include_valves=True, include_leaks=True)

        # Register in memo BEFORE copying any nested objects
        memo[pipe_id] = new_pipe
        return new_pipe


def _invalidates_solver_cache(func: typing.Callable[P, R]) -> typing.Callable[P, R]:
    """Wrapper to invalidate the solver cache after mutating Pipeline methods."""

    def _wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        pipeline = args[0]
        if not isinstance(pipeline, Pipeline):
            raise TypeError(
                f"First argument must be Pipeline, got {type(pipeline).__name__}"
            )

        result = func(*args, **kwargs)
        # Invalidate solver cache only after initialization
        if pipeline._solver is not None and getattr(pipeline, "_initialized", False):
            pipeline._solver.clear_cache()
        return result

    return functools.update_wrapper(_wrapper, func)


class Pipeline:
    """
    Pipeline component that manages a sequence of connected Pipe components.

    Validates proper connections between pipes and aggregates their properties
    to provide comprehensive pipeline characteristics and visualization.
    """

    def __new__(cls, *args: typing.Any, **kwargs: typing.Any) -> "Pipeline":
        instance = super().__new__(cls)
        instance._initialized = False
        return instance

    def __init__(
        self,
        pipes: typing.Sequence[Pipe],
        fluid: typing.Optional[Fluid] = None,
        name: typing.Optional[str] = None,
        scale_factor: float = 0.1,
        upstream_pressure: typing.Optional[PlainQuantity[float]] = None,
        downstream_pressure: typing.Optional[PlainQuantity[float]] = None,
        upstream_temperature: typing.Optional[PlainQuantity[float]] = None,
        max_flow_rate: PlainQuantity[float] = Quantity(0.0, "ft^3/s"),
        flow_type: FlowType = FlowType.COMPRESSIBLE,
        connector_length: PlainQuantity[float] = Quantity(0.1, "m"),
        alert_errors: bool = True,
        ignore_leaks: bool = False,
    ) -> None:
        """
        Initialize a Pipeline component.

        :param pipes: Sequence of Pipe instances to include in the pipeline
        :param fluid: Optional Fluid instance representing the fluid in the pipeline
        :param name: Optional name for the pipeline
        :param scale_factor: Scaling factor for pipe visualization (applied to all pipes)
        :param upstream_pressure: Upstream pressure of the pipeline
        :param upstream_temperature: Upstream temperature of the fluid in the pipeline
        :param downstream_pressure: Downstream pressure of the pipeline
        :param max_flow_rate: Maximum expected flow rate for intensity normalization
        :param flow_type: Flow type for the pipeline (compressible or incompressible)
        :param connector_length: Physical length of connectors between pipes (e.g., mm, cm)
        :param alert_errors: Whether to alert on connection errors between pipes
        :param ignore_leaks: Whether to ignore leaks in all pipes in the pipeline
        """
        self.name = name or f"Pipeline-{id(self)}"
        self._pipes: typing.List[Pipe] = []
        self.scale_factor = scale_factor
        self.max_flow_rate = max_flow_rate
        self.pipeline_viz = None
        self._flow_type = flow_type
        self.connector_length = connector_length
        self.alert_errors = alert_errors
        self._ignore_leaks = ignore_leaks
        self._upstream_pressure = None
        self._downstream_pressure = None
        self._upstream_temperature = upstream_temperature
        self._fluid = fluid

        from src.pipeline.solver import FlowSolver

        self._solver = FlowSolver(self, cache_size=128)

        if upstream_pressure is not None:
            self.set_upstream_pressure(upstream_pressure, sync=False)
        if downstream_pressure is not None:
            self.set_downstream_pressure(downstream_pressure, sync=False)

        for pipe in pipes:
            self.add_pipe(pipe, sync=False)

        self.sync()
        self._initialized = True

    @property
    def pipes(self) -> typing.List[Pipe]:
        return self._pipes.copy()

    @property
    def fluid(self) -> typing.Optional[Fluid]:
        """The fluid in the pipeline at pipeline upstream pressure and temperature"""
        if (fluid := self._fluid) is None or self.upstream_pressure.magnitude == 0:
            return None

        upstream_temperature = self.upstream_temperature
        return fluid.for_pressure_temperature(
            pressure=self.upstream_pressure,
            temperature=upstream_temperature
            if upstream_temperature is not None
            else fluid.temperature,
        )

    @property
    def upstream_fluid(self) -> typing.Optional[Fluid]:
        """Get the fluid at the upstream end of the pipeline."""
        if self._pipes:
            return self._pipes[0].inlet_fluid
        return self._fluid

    inlet_fluid = upstream_fluid

    @property
    def downstream_fluid(self) -> typing.Optional[Fluid]:
        """Get the fluid at the downstream end of the pipeline."""
        if self._pipes:
            return self._pipes[-1].outlet_fluid
        return self._fluid

    outlet_fluid = downstream_fluid

    @property
    def upstream_pressure(self) -> PlainQuantity[float]:
        """The upstream pressure of the pipeline."""
        if self._upstream_pressure is None:
            if self._pipes:
                self._upstream_pressure = self._pipes[0].upstream_pressure
            else:
                return Quantity(0.0, "psi")
        return self._upstream_pressure.to("psi")

    @property
    def downstream_pressure(self) -> PlainQuantity[float]:
        """The downstream pressure (psi) of the pipeline."""
        if self._downstream_pressure is None:
            if self._pipes:
                self._downstream_pressure = self._pipes[-1].downstream_pressure
            else:
                return Quantity(0.0, "psi")
        return self._downstream_pressure.to("psi")

    @property
    def pressure_drop(self) -> PlainQuantity[float]:
        """The total pressure drop (psi) across the pipeline."""
        return self.upstream_pressure.to("psi") - self.downstream_pressure.to("psi")

    @property
    def upstream_temperature(self) -> typing.Optional[PlainQuantity[float]]:
        """The temperature of the fluid upstream in the pipeline"""
        if (
            self._upstream_temperature is None
            and (inlet_fluid := self.inlet_fluid) is not None
        ):
            self._upstream_temperature = inlet_fluid.temperature
        return self._upstream_temperature

    @property
    def downstream_temperature(self) -> typing.Optional[PlainQuantity[float]]:
        """The temperature of the fluid downstream in the pipeline."""
        if not self._pipes:
            return self.upstream_temperature
        return self._pipes[-1].downstream_temperature

    @property
    def inlet_flow_rate(self) -> PlainQuantity[float]:
        """The inlet/upstream flow rate (ft^3/s) of the pipeline (from the first pipe)."""
        if self._pipes:
            return self._pipes[0].flow_rate.to("ft^3/s")
        return Quantity(0, "ft^3/s")

    @property
    def outlet_flow_rate(self) -> PlainQuantity[float]:
        """The outlet/downstream flow rate of the pipeline (ft^3/s) (from the last pipe)."""
        if self._pipes:
            return self._pipes[-1].flow_rate.to("ft^3/s")
        return Quantity(0, "ft^3/s")

    @property
    def inlet_mass_rate(self) -> PlainQuantity[float]:
        """The inlet/upstream mass flow rate (lb/s) of the pipeline (from the first pipe)."""
        if self._pipes:
            return self._pipes[0].mass_rate.to("lb/s")
        return Quantity(0, "lb/s")

    @property
    def outlet_mass_rate(self) -> PlainQuantity[float]:
        """The outlet/downstream mass flow rate (lb/s) of the pipeline (from the last pipe)."""
        if self._pipes:
            return self._pipes[-1].mass_rate.to("lb/s")
        return Quantity(0, "lb/s")

    @property
    def is_leaking(self) -> bool:
        """Whether any pipe in the pipeline has active leaks."""
        if self._ignore_leaks:
            return False
        return any(pipe.is_leaking for pipe in self._pipes)

    @property
    def leaks(self) -> typing.Iterator[typing.Tuple[int, PipeLeak]]:
        """
        Iterator over all active leaks in the pipeline.

        :return: Iterator of tuples (pipe_index, leak)
        """
        for i, pipe in enumerate(self._pipes):
            for leak in pipe.leaks:
                yield i, leak

    @property
    def valves(
        self,
    ) -> typing.Iterator[
        typing.Tuple[int, typing.Optional[Valve], typing.Optional[Valve]]
    ]:
        """
        Iterator over all pipes' start and end valves.

        :return: Iterator of tuples (pipe_index, start_valve, end_valve)
        """
        for i, pipe in enumerate(self._pipes):
            yield i, pipe._start_valve, pipe._end_valve

    @property
    def leak_rate(self) -> PlainQuantity[float]:
        """Total leak rate from all pipes in the pipeline."""
        if self._ignore_leaks:
            return Quantity(0.0, "ft^3/s")

        total_leak_rate = sum(
            pipe.leak_rate.to("ft^3/s").magnitude for pipe in self._pipes
        )
        return Quantity(total_leak_rate, "ft^3/s")

    @property
    def has_valves(self) -> bool:
        """Check if any pipe in the pipeline has a valve."""
        return any(pipe.has_valve for pipe in self._pipes)

    @property
    def flow_type(self) -> FlowType:
        """The flow type for the pipeline and all pipes."""
        return self._flow_type

    @_invalidates_solver_cache
    def set_fluid(self, fluid: Fluid, *, sync: bool = True) -> Self:
        """Set the (inlet) fluid in the pipeline."""
        self._fluid = fluid
        for pipe in self._pipes:
            pipe.set_fluid(fluid, sync=False)

        if sync:
            self.sync()
        return self

    def set_ignore_leaks(self, ignore: bool = True, *, sync: bool = True) -> Self:
        """Set whether to ignore leaks in all pipes in the pipeline."""
        self._ignore_leaks = ignore
        for pipe in self._pipes:
            pipe.set_ignore_leaks(ignore, sync=False)
        if sync:
            self.sync()
        return self

    @_invalidates_solver_cache
    def set_flow_type(self, flow_type: FlowType, *, sync: bool = True) -> Self:
        """Set the flow type for the pipeline and all pipes."""
        self._flow_type = flow_type
        for pipe in self._pipes:
            pipe.set_flow_type(flow_type, sync=False)
        if sync:
            self.sync()
        return self

    def set_max_flow_rate(
        self, max_flow_rate: PlainQuantity[float], *, update_viz: bool = True
    ) -> Self:
        """Set the maximum expected flow rate for the pipeline and all pipes."""
        self.max_flow_rate = max_flow_rate
        for pipe in self._pipes:
            pipe.set_max_flow_rate(max_flow_rate, update_viz=False)
        if update_viz:
            self.update_viz()
        return self

    def set_scale_factor(self, scale_factor: float, *, update_viz: bool = True) -> Self:
        """Set the scale factor for the pipeline and all pipes."""
        self.scale_factor = scale_factor
        for pipe in self._pipes:
            pipe.scale_factor = scale_factor
        if update_viz:
            self.update_viz()
        return self

    @_invalidates_solver_cache
    def set_connector_length(
        self, length: PlainQuantity[float], sync: bool = True
    ) -> Self:
        """Set the connector length between pipes in the pipeline."""
        self.connector_length = length
        if sync:
            self.sync()
        return self

    def add_valve(
        self,
        pipe_index: int,
        valve: typing.Optional[Valve] = None,
        position: typing.Literal["start", "end"] = "start",
        *,
        sync: bool = True,
    ) -> Self:
        """
        Add valve to specific pipe in the pipeline.

        :param pipe_index: Index of pipe to add valve to
        :param valve: Valve instance to add (creates default if None)
        :param position: Position for valve ("start" or "end")
        :param sync: Whether to synchronize pipeline after adding
        :return: self for method chaining
        """
        if pipe_index < 0:
            pipe_index = len(self._pipes) + pipe_index

        if not (0 <= pipe_index < len(self._pipes)):
            raise IndexError(f"Pipe index {pipe_index} out of range")

        self._pipes[pipe_index].add_valve(valve=valve, position=position, sync=False)
        if sync:
            self.sync()
        return self

    def remove_valve(
        self,
        pipe_index: int,
        position: typing.Literal["start", "end"],
        *,
        sync: bool = True,
    ) -> typing.Optional[Valve]:
        """
        Remove valve from specific pipe in the pipeline.

        :param pipe_index: Index of pipe to remove valve from
        :param position: Position of valve to remove ("start" or "end")
        :param sync: Whether to synchronize pipeline after removing
        :return: The removed Valve instance, or None if no valve existed
        """
        if pipe_index < 0:
            pipe_index = len(self._pipes) + pipe_index

        if not (0 <= pipe_index < len(self._pipes)):
            raise IndexError(f"Pipe index {pipe_index} out of range")

        removed_valve = self._pipes[pipe_index].remove_valve(
            position=position, sync=False
        )
        if sync:
            self.sync()
        return removed_valve

    def open_valve(
        self,
        pipe_index: int,
        position: typing.Literal["start", "end"],
        *,
        sync: bool = True,
    ) -> Self:
        """
        Open valve on specific pipe.

        :param pipe_index: Index of pipe with valve to open
        :param position: Position of valve to open ("start" or "end")
        :param sync: Whether to synchronize pipeline after opening
        :return: self for method chaining
        """
        if pipe_index < 0:
            pipe_index = len(self._pipes) + pipe_index

        if not (0 <= pipe_index < len(self._pipes)):
            raise IndexError(f"Pipe index {pipe_index} out of range")

        self._pipes[pipe_index].open_valve(position=position, sync=False)
        if sync:
            self.sync()
        return self

    def close_valve(
        self,
        pipe_index: int,
        position: typing.Literal["start", "end"],
        *,
        sync: bool = True,
    ) -> Self:
        """
        Close valve on specific pipe.

        :param pipe_index: Index of pipe with valve to close
        :param position: Position of valve to close ("start" or "end")
        :param sync: Whether to synchronize pipeline after closing
        :return: self for method chaining
        """
        if pipe_index < 0:
            pipe_index = len(self._pipes) + pipe_index

        if not (0 <= pipe_index < len(self._pipes)):
            raise IndexError(f"Pipe index {pipe_index} out of range")

        self._pipes[pipe_index].close_valve(position=position, sync=False)
        if sync:
            self.sync()
        return self

    def toggle_valve(
        self,
        pipe_index: int,
        position: typing.Literal["start", "end"],
        *,
        sync: bool = True,
    ) -> Self:
        """
        Toggle valve state on specific pipe.

        :param pipe_index: Index of pipe with valve to toggle
        :param position: Position of valve to toggle ("start" or "end")
        :param sync: Whether to synchronize pipeline after toggling
        :return: self for method chaining
        """
        if pipe_index < 0:
            pipe_index = len(self._pipes) + pipe_index

        if not (0 <= pipe_index < len(self._pipes)):
            raise IndexError(f"Pipe index {pipe_index} out of range")

        self._pipes[pipe_index].toggle_valve(position=position, sync=False)
        if sync:
            self.sync()
        return self

    def open_all_valves(self, *, sync: bool = True) -> Self:
        """
        Open all valves in the pipeline.

        :param sync: Whether to synchronize pipeline after opening all valves
        :return: self for method chaining
        """
        for pipe in self._pipes:
            if pipe._start_valve is not None:
                pipe.open_valve(position="start", sync=False)
            if pipe._end_valve is not None:
                pipe.open_valve(position="end", sync=False)

        if sync:
            self.sync()
        return self

    def close_all_valves(self, *, sync: bool = True) -> Self:
        """
        Close all valves in the pipeline.

        :param sync: Whether to synchronize pipeline after closing all valves
        :return: self for method chaining
        """
        for pipe in self._pipes:
            if pipe._start_valve is not None:
                pipe.close_valve(position="start", sync=False)
            if pipe._end_valve is not None:
                pipe.close_valve(position="end", sync=False)

        if sync:
            self.sync()
        return self

    def __iter__(self) -> typing.Iterator[Pipe]:
        """Iterate over the pipes in the pipeline."""
        return iter(self._pipes)

    def __getitem__(self, index: int) -> Pipe:
        """Get a pipe by index."""
        return self._pipes[index]

    def __setitem__(self, index: int, pipe: Pipe) -> None:
        """Set a pipe at a specific index."""
        if not isinstance(pipe, Pipe):
            raise TypeError("Only Pipe instances can be assigned to the pipeline.")
        self._pipes[index] = pipe
        self.sync()

    def show(
        self,
        min_width: str = "800px",
        max_width: str = "100%",
        height: str = "800px",
        label: typing.Optional[str] = None,
        show_label: bool = True,
    ) -> Column:
        """
        Display the pipeline as a UI component.

        :param label: Title label for the pipeline visualization
        :param width: Width of the container (CSS units)
        :param height: Height of the container (CSS units)
        :param show_label: Whether to display the label above the pipeline
        :return: Html component containing the pipeline visualization
        """
        container = (
            ui.column()  # Changed to column for better flex control
            .classes("w-full p-2 bg-white border border-gray-200 rounded-lg shadow-sm")
            .style(
                f"""
                min-width: min({min_width}, 100%);
                max-width: min({max_width}, 100%);
                height: min({height}, 90dvh);
                min-height: 200px;
                overflow: hidden; 
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: 8px;
                padding: 16px;
                """,
            )
        )

        with container:
            if show_label:
                label = label or self.name
                ui.label(label).classes(
                    "text-lg sm:text-xl font-bold text-gray-800 text-center flex-shrink-0"
                )

            # Get the SVG content and check if it's valid
            svg_content = str(self.get_svg())
            self.pipeline_viz = ui.html(svg_content, sanitize=False).style(
                """
                width: 100%;
                flex: 1;  
                border: 1px solid #ccc; 
                border-radius: inherit;
                background: #f9f9f9;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
                min-height: 0; 
                """
            )
        return container

    def update_viz(self) -> Self:
        """
        Update the SVG visualization of the pipeline.
        This method should be called whenever pipe properties or flow rates change.
        """
        if self.pipeline_viz is not None:
            self.pipeline_viz.content = str(self.get_svg())
        return self

    def get_svg(self) -> SVGComponent:
        """
        Generate a unified SVG showing all pipes connected together.

        :return: `SVGComponent` representing the entire pipeline with proper connections
        """
        pipe_count = len(self._pipes)
        modular_components: typing.List[PipeComponent] = []
        pipe_component_cache = {}

        for i, pipe in enumerate(self._pipes):
            if not self._ignore_leaks:
                leaks = []
                for leak in pipe.leaks:
                    # Calculate actual leak flow rate for severity assessment
                    # If the pipe has fluid and flow, compute leak rate
                    if pipe.fluid and pipe.flow_rate.magnitude > 0:
                        leak_flow_rate = leak.compute_rate(
                            pipe_pressure=pipe.estimate_pressure_at_location(
                                leak.location
                            ),
                            ambient_pressure=pipe.ambient_pressure,
                            fluid_density=pipe.fluid.density,
                        )
                    else:
                        # No fluid, assume zero flow rate
                        leak_flow_rate = Quantity(0.0, "ft^3/s")

                    if leak_flow_rate.magnitude > 0:
                        leaks.append(
                            LeakInfo(
                                location=leak.location,
                                severity=leak.get_severity(leak_flow_rate),
                            )
                        )
            else:
                leaks = None

            # Add the pipe component
            if i in pipe_component_cache:
                pipe_component = pipe_component_cache[i]

            elif pipe.direction in [PipeDirection.EAST, PipeDirection.WEST]:
                # Horizontal pipe
                pipe_component = build_horizontal_pipe_component(
                    direction=pipe.direction,
                    internal_diameter=pipe.internal_diameter,
                    length=pipe.length,
                    flow_rate=pipe.flow_rate,
                    max_flow_rate=pipe.max_flow_rate,
                    scale_factor=pipe.scale_factor,
                    canvas_width=400.0,
                    canvas_height=100.0,
                    leaks=leaks,
                )
                pipe_component_cache[i] = pipe_component
            else:
                # Vertical pipe
                pipe_component = build_vertical_pipe_component(
                    direction=pipe.direction,
                    internal_diameter=pipe.internal_diameter,
                    length=pipe.length,
                    flow_rate=pipe.flow_rate,
                    max_flow_rate=pipe.max_flow_rate,
                    scale_factor=pipe.scale_factor,
                    canvas_width=100.0,
                    canvas_height=400.0,
                    leaks=leaks,
                )
                pipe_component_cache[i] = pipe_component

            # Add start valve if present (before the pipe)
            # Skip if previous pipe has end valve (to avoid duplication)
            prev_pipe = self._pipes[i - 1] if i > 0 else None
            prev_pipe_has_end_valve = (
                prev_pipe is not None and prev_pipe._end_valve is not None
            )
            if pipe._start_valve is not None and not prev_pipe_has_end_valve:
                # If the first pipe in the pipeline has a start valve, connect to itself
                prev_pipe = prev_pipe if prev_pipe is not None else pipe
                prev_pipe_component = pipe_component_cache.get(i - 1, pipe_component)
                if pipe.direction != prev_pipe.direction:
                    # Direction change - use elbow valve
                    valve_component = build_elbow_valve_component(
                        component1=prev_pipe_component,
                        component2=pipe_component,
                        state=pipe._start_valve.state.value,
                    )
                else:
                    # Same direction - use straight valve
                    valve_component = build_straight_valve_component(
                        component1=prev_pipe_component,
                        component2=pipe_component,
                        state=pipe._start_valve.state.value,
                    )
                modular_components.append(valve_component)

            # Add the pipe component
            modular_components.append(pipe_component)

            end_valve_component = None
            # Add end valve if present (after the pipe)
            # Need to check if next pipe changes direction to use correct valve type
            if pipe._end_valve is not None and i < (pipe_count - 1):
                next_pipe = self._pipes[i + 1]

                # Build next pipe component first if needed
                if (i + 1) not in pipe_component_cache:
                    if not self._ignore_leaks:
                        leaks = []
                        for leak in next_pipe.leaks:
                            if next_pipe.fluid and next_pipe.flow_rate.magnitude > 0:
                                leak_flow_rate = leak.compute_rate(
                                    pipe_pressure=next_pipe.estimate_pressure_at_location(
                                        leak.location
                                    ),
                                    ambient_pressure=next_pipe.ambient_pressure,
                                    fluid_density=next_pipe.fluid.density,
                                )
                            else:
                                leak_flow_rate = Quantity(0.0, "ft^3/s")

                            if leak_flow_rate.magnitude > 0:
                                leaks.append(
                                    LeakInfo(
                                        location=leak.location,
                                        severity=leak.get_severity(leak_flow_rate),
                                    )
                                )
                    else:
                        leaks = None

                    if next_pipe.direction in [PipeDirection.EAST, PipeDirection.WEST]:
                        next_pipe_component = build_horizontal_pipe_component(
                            direction=next_pipe.direction,
                            internal_diameter=next_pipe.internal_diameter,
                            length=next_pipe.length,
                            flow_rate=next_pipe.flow_rate,
                            max_flow_rate=next_pipe.max_flow_rate,
                            scale_factor=next_pipe.scale_factor,
                            canvas_width=400.0,
                            canvas_height=100.0,
                            leaks=leaks,
                        )
                    else:
                        next_pipe_component = build_vertical_pipe_component(
                            direction=next_pipe.direction,
                            internal_diameter=next_pipe.internal_diameter,
                            length=next_pipe.length,
                            flow_rate=next_pipe.flow_rate,
                            max_flow_rate=next_pipe.max_flow_rate,
                            scale_factor=next_pipe.scale_factor,
                            canvas_width=100.0,
                            canvas_height=400.0,
                            leaks=leaks,
                        )
                    pipe_component_cache[i + 1] = next_pipe_component
                else:
                    next_pipe_component = pipe_component_cache[i + 1]

                # Determine valve type based on direction change
                if pipe.direction != next_pipe.direction:
                    # Direction change - use elbow valve
                    valve_component = build_elbow_valve_component(
                        component1=pipe_component,
                        component2=next_pipe_component,
                        state=pipe._end_valve.state.value,
                    )
                else:
                    # Same direction - use straight valve
                    valve_component = build_straight_valve_component(
                        component1=pipe_component,
                        component2=next_pipe_component,
                        state=pipe._end_valve.state.value,
                    )
                end_valve_component = valve_component
                modular_components.append(valve_component)

            elif pipe._end_valve is not None:
                # Last pipe with end valve - use straight valve with same component
                valve_component = build_straight_valve_component(
                    component1=pipe_component,
                    component2=pipe_component,
                    state=pipe._end_valve.state.value,
                )
                end_valve_component = valve_component
                modular_components.append(valve_component)

            # Add connector to next pipe (if not the last pipe)
            # Skip connector if there's an end valve or if next pipe has start valve - valves already act as connectors
            if i < (pipe_count - 1) and end_valve_component is None:
                next_pipe = self._pipes[i + 1]
                # Skip connector if next pipe has a start valve
                if next_pipe._start_valve is not None:
                    continue
                if not self._ignore_leaks:
                    leaks = []
                    for leak in next_pipe.leaks:
                        # Calculate actual leak flow rate for severity assessment
                        # If the next pipe has fluid and flow, compute leak rate
                        if next_pipe.fluid and next_pipe.flow_rate.magnitude > 0:
                            leak_flow_rate = leak.compute_rate(
                                pipe_pressure=next_pipe.estimate_pressure_at_location(
                                    leak.location
                                ),
                                ambient_pressure=next_pipe.ambient_pressure,
                                fluid_density=next_pipe.fluid.density,
                            )
                        else:
                            # No fluid, assume zero flow rate
                            leak_flow_rate = Quantity(0.0, "ft^3/s")

                        if leak_flow_rate.magnitude > 0:
                            leaks.append(
                                LeakInfo(
                                    location=leak.location,
                                    severity=leak.get_severity(leak_flow_rate),
                                )
                            )
                else:
                    leaks = None

                # Build next pipe component first
                if next_pipe.direction in [PipeDirection.EAST, PipeDirection.WEST]:
                    next_pipe_component = build_horizontal_pipe_component(
                        direction=next_pipe.direction,
                        internal_diameter=next_pipe.internal_diameter,
                        length=next_pipe.length,
                        flow_rate=next_pipe.flow_rate,
                        max_flow_rate=next_pipe.max_flow_rate,
                        scale_factor=next_pipe.scale_factor,
                        canvas_width=400.0,
                        canvas_height=100.0,
                        leaks=leaks,
                    )
                else:
                    next_pipe_component = build_vertical_pipe_component(
                        direction=next_pipe.direction,
                        internal_diameter=next_pipe.internal_diameter,
                        length=next_pipe.length,
                        flow_rate=next_pipe.flow_rate,
                        max_flow_rate=next_pipe.max_flow_rate,
                        scale_factor=next_pipe.scale_factor,
                        canvas_width=100.0,
                        canvas_height=400.0,
                        leaks=leaks,
                    )
                # Cache the next pipe component for the next iteration
                # to avoid redundant reconstruction
                pipe_component_cache[i + 1] = next_pipe_component

                # Determine if we need an elbow or straight connector
                if pipe.direction != next_pipe.direction:
                    # Different directions - need elbow connector
                    connector = build_elbow_connector_component(
                        component1=pipe_component,
                        component2=next_pipe_component,
                        arm_length=self.connector_length,
                    )
                else:
                    # Same direction - need straight connector
                    connector = build_straight_connector_component(
                        component1=pipe_component,
                        component2=next_pipe_component,
                        length=self.connector_length,
                    )
                modular_components.append(connector)

        # Create modular pipeline with proper connectors
        if len(modular_components) == 1:
            # Single pipe - just return its SVG
            svg_component = modular_components[0].get_svg_component()
            return svg_component

        # Collate pipeline components
        modular_pipeline = PipelineComponents(modular_components)
        svg_component = modular_pipeline.get_svg_component()
        return svg_component

    def is_connected(self, component1_idx: int, component2_idx: int) -> bool:
        """
        Check if two consecutive pipes are properly connected.

        :param component1_idx: Index of the first pipe
        :param component2_idx: Index of the second pipe
        :return: True if pipes are connected, False otherwise
        """
        if component1_idx < 0 or component2_idx >= len(self._pipes):
            return False

        component1 = self._pipes[component1_idx]
        component2 = self._pipes[component2_idx]

        # Check direction compatibility (only check for direction compatibility now)
        direction_compatible = check_direction_compatibility(
            component1.direction, component2.direction
        )
        return direction_compatible

    def set_upstream_pressure(
        self, pressure: typing.Union[PlainQuantity[float], float], sync: bool = True
    ) -> Self:
        """
        Set the upstream pressure for the entire pipeline (applied to the first pipe section).

        :param pressure: Upstream pressure to set
        :param sync: Whether to synchronize pipes properties after setting (default is True)
        :return: self for method chaining
        """
        if isinstance(pressure, Quantity):
            pressure = pressure.to("psi")
        else:
            pressure = pressure * ureg("psi")

        if pressure.magnitude < self.downstream_pressure.magnitude:
            if self.alert_errors:
                show_alert(
                    f"Upstream pressure cannot be less than downstream pressure in pipeline - {self.name!r}.",
                    severity="error",
                )
            raise ValueError(
                "Upstream pressure cannot be less than downstream pressure. Flow cannot occur against the pressure gradient."
            )

        self._upstream_pressure = pressure
        if self._pipes:
            try:
                self._pipes[0].set_upstream_pressure(pressure, check=False, sync=False)
            except Exception as exc:
                if self.alert_errors:
                    show_alert(
                        f"Failed to set upstream pressure in first pipe - {self.name!r}: {exc}",
                        severity="error",
                    )
                raise

        if sync:
            self.sync()
        return self

    def set_downstream_pressure(
        self, pressure: typing.Union[PlainQuantity[float], float], sync: bool = True
    ) -> Self:
        """
        Set the downstream pressure for the pipeline

        :param pressure: Downstream pressure to set
        :param sync: Whether to synchronize pipes properties after setting (default is True)
        :return: self for method chaining
        """
        if isinstance(pressure, Quantity):
            pressure = pressure.to("psi")
        else:
            pressure = pressure * ureg("psi")

        if pressure.magnitude > self.upstream_pressure.magnitude:
            if self.alert_errors:
                show_alert(
                    f"Downstream pressure cannot exceed upstream pressure in pipeline - {self.name!r}.",
                    severity="error",
                )
            raise ValueError(
                "Downstream pressure cannot exceed upstream pressure. Flow cannot occur against the pressure gradient."
            )

        self._downstream_pressure = pressure
        if self._pipes:
            try:
                self._pipes[-1].set_downstream_pressure(
                    pressure, check=False, sync=False
                )
            except Exception as exc:
                if self.alert_errors:
                    show_alert(
                        f"Failed to set downstream pressure in last pipe - {self.name!r}: {exc}",
                        severity="error",
                    )
                raise

        if sync:
            self.sync()
        return self

    def set_upstream_temperature(
        self, temperature: typing.Union[PlainQuantity[float], float], sync: bool = True
    ) -> Self:
        """Set the upstream fluid temperature for the pipeline (applied to the first pipe)."""
        if self.fluid is None:
            raise ValueError(
                "Cannot set upstream temperature without defining fluid properties."
            )

        if isinstance(temperature, Quantity):
            temperature_q = temperature.to("degF")
        else:
            temperature_q = Quantity(temperature, "degF")

        self._upstream_temperature = temperature_q
        if self._pipes:
            try:
                self._pipes[0].set_upstream_temperature(temperature_q, sync=False)
            except Exception as exc:
                if self.alert_errors:
                    show_alert(
                        f"Failed to set upstream temperature in first pipe - {self.name!r}: {exc}",
                        severity="error",
                    )
                raise

        if sync:
            self.sync()
        return self

    @_invalidates_solver_cache
    def add_pipe(self, pipe: Pipe, index: int = -1, *, sync: bool = True) -> Self:
        """
        Add a new pipe to the end of the pipeline.

        :param pipe: Pipe instance to add to the pipeline
        :param index: Optional index to insert the pipe at (default is -1 for appending)
        :param sync: Whether to synchronize pipes properties after adding (default is True)
        :return: self for method chaining
        :raises `PipelineConnectionError`: If the new pipe cannot be connected
        """
        if self._pipes:
            # Validate flow direction compatibility
            last_pipe = self._pipes[-1]
            if not check_direction_compatibility(last_pipe.direction, pipe.direction):
                error_msg = (
                    f"Cannot add pipe with opposing flow direction: "
                    f"{last_pipe.direction.value} to {pipe.direction.value}. "
                    f"Pipes flowing in opposite directions cannot be connected."
                )
                if self.alert_errors:
                    show_alert(error_msg, severity="error")
                raise PipelineConnectionError(error_msg)

        pipe = pipe.copy(
            include_leaks=True, include_valves=True
        )  # Work with a copy to avoid modifying the original
        # Set pipe to not alert errors individually. Alerts will be handled by the pipeline
        pipe.alert_errors = False
        # Apply the pipeline's scale factor and max flow rate to the pipe
        pipe.set_scale_factor(self.scale_factor, update_viz=False)
        if self.max_flow_rate.magnitude > 0:
            pipe.set_max_flow_rate(self.max_flow_rate, update_viz=False)
        else:
            # If pipeline max flow rate is zero, use the pipe's own max flow rate
            # Basically the first pipe added sets the max flow rate if not defined
            self.set_max_flow_rate(pipe.max_flow_rate, update_viz=False)

        if self.fluid is not None:
            pipe.set_fluid(self.fluid, sync=False)

        # Set the pipe to ignore leaks if the pipeline is set to ignore leaks
        pipe.set_ignore_leaks(self._ignore_leaks, sync=False)
        # Ensure the pipe's flow type matches the pipeline's flow type
        pipe.set_flow_type(self._flow_type, sync=False)

        if index < 0:
            index = len(self._pipes) + index + 1  # Convert negative index to positive

        self._pipes.insert(index, pipe)
        if sync:
            try:
                self.sync()
            except Exception as exc:
                self._pipes.pop(index)  # Rollback addition
                if self.alert_errors:
                    show_alert(
                        f"Pipeline synchronization after adding pipe to {self.name!r} failed: \n{exc}",
                        severity="error",
                    )
                raise

        # Store a reference to the pipeline it belongs to for low-level usages
        pipe._pipeline = self
        return self

    @_invalidates_solver_cache
    def remove_pipe(
        self, index: int = -1, *, sync: bool = True
    ) -> typing.Optional[Pipe]:
        """
        Remove a pipe from the pipeline at the specified index.

        :param index: Index of the pipe to remove
        :param sync: Whether to synchronize pipes properties after removal (default is True)
        :return: The removed pipe, if it exists else None
        :raises PipelineConnectionError: If removing the pipe breaks pipeline continuity
        """
        if index < 0:
            index = len(self._pipes) + index  # Convert negative index to positive

        removed_pipe = None
        if 0 <= index < len(self._pipes):
            removed_pipe = self._pipes.pop(index)

            # Validate remaining connections
            if len(self._pipes) > 1:
                for i in range(len(self._pipes) - 1):
                    current_pipe = self._pipes[i]
                    next_pipe = self._pipes[i + 1]

                    if not check_direction_compatibility(
                        current_pipe.direction, next_pipe.direction
                    ):
                        error_msg = (
                            f"Removing pipe creates incompatible flow directions between segments {i} "
                            f"({current_pipe.direction.value}) and {i + 1} ({next_pipe.direction.value})"
                        )
                        if self.alert_errors:
                            show_alert(error_msg, severity="error")
                        raise PipelineConnectionError(error_msg)

        if sync:
            try:
                self.sync()
            except Exception as exc:
                if removed_pipe:
                    self._pipes.insert(index, removed_pipe)  # Rollback removal
                if self.alert_errors:
                    show_alert(
                        f"Pipeline synchronization after removing pipe from {self.name!r} failed: \n{exc}",
                        severity="error",
                    )
                raise

        # Clear reference to this pipeline
        if removed_pipe is not None:
            removed_pipe._pipeline = None
        return removed_pipe

    @_invalidates_solver_cache
    def add_leak(self, pipe_index: int, leak: PipeLeak, *, sync: bool = True) -> Self:
        """
        Add a leak to a specific pipe in the pipeline.

        :param pipe_index: Index of the pipe to add the leak to
        :param leak: `PipeLeak` instance to add
        :param sync: Whether to synchronize pipes properties after adding the leak (default is True)
        :return: self for method chaining
        """
        if pipe_index < 0:
            pipe_index = len(self._pipes) + pipe_index

        if 0 <= pipe_index < len(self._pipes):
            self._pipes[pipe_index].add_leak(leak, sync=sync)
        else:
            raise IndexError("Pipe index out of range.")

        if sync:
            self.sync()
        return self

    @_invalidates_solver_cache
    def remove_leak(
        self, pipe_index: int, leak_index: int, *, sync: bool = True
    ) -> PipeLeak:
        """
        Remove a leak from a specific pipe in the pipeline.

        :param pipe_index: Index of the pipe to remove the leak from
        :param leak_index: Index of the leak to remove
        :param sync: Whether to synchronize pipes properties after removing the leak (default is True)
        :return: The removed `PipeLeak` object.
        """
        if pipe_index < 0:
            pipe_index = len(self._pipes) + pipe_index

        if 0 <= pipe_index < len(self._pipes):
            removed_leak = self._pipes[pipe_index].remove_leak(leak_index, sync=sync)
        else:
            raise IndexError("Pipe index out of range.")

        if sync:
            self.sync()
        return removed_leak

    @_invalidates_solver_cache
    def clear_leaks(self, *, sync: bool = True) -> Self:
        """
        Clear all leaks from all pipes in the pipeline.

        :param sync: Whether to synchronize pipes properties after clearing leaks (default is True)
        :return: self for method chaining
        """
        for pipe in self._pipes:
            pipe.clear_leaks(sync=False)

        if sync:
            self.sync()
        return self

    def estimate_leak_pressure(self, pipe_index: int, leak_location: float):
        """
        Estimate local pressure at leak location in specified pipe.

        :param pipe_index: Index of the pipe containing the leak
        :param leak_location: Fractional location of the leak along the pipe (0.0 to 1.0)
        """
        pipe = self._pipes[pipe_index]
        return self._solver.estimate_pressure_at_location(pipe, leak_location)

    def sync(self) -> Self:
        """Synchronize all pipes in the pipeline, solving for flow rates and pressures."""
        success = self._solver.solve_pipeline(
            tolerance=100.0,  # 100 Pa
            max_iterations=30,
        )
        if not success:
            logger.warning(f"Pipeline {self.name!r} did not converge")
            # raise RuntimeError(
            #     f"Pipeline {self.name!r} did not converge to a solution."
            # )
        return self

    def connect(self, other: typing.Union[Pipe, "Pipeline"]) -> Self:
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

    def __and__(self, other: typing.Union[Pipe, "Pipeline"]) -> Self:
        """
        Overload the pipe connection operator.

        :param other: Pipe or Pipeline instance to connect using & operator
        :return: Connected Pipeline instance
        """
        return self.connect(other)

    __add__ = __and__

    def copy(self, deep_copy_pipes: bool = True) -> Self:
        """
        Create a copy of the pipeline.

        This method carefully handles:
        - Pipes (optional deep copy vs reference)
        - Fluid (creates new instance)
        - Solver cache (optionally preserved)
        - Visualization elements (explicitly NOT copied)
        - Avoids circular reference issues

        :param deep_copy_pipes: Whether to deep copy each pipe (True) or share references (False)
        :return: New Pipeline instance
        """
        # Copy pipes
        if deep_copy_pipes:
            # Deep copy each pipe individually
            new_pipes = [
                pipe.copy(include_valves=True, include_leaks=True)
                for pipe in self._pipes
            ]
        else:
            # Shallow copy - share pipe references
            # Useful for testing different pipeline configurations with same pipes
            new_pipes = list(self._pipes)

        # Create new pipeline instance
        new_pipeline = self.__class__(
            pipes=[],  # Will add pipes manually to avoid sync during init
            fluid=self._fluid.for_pressure_temperature(
                pressure=self._fluid.pressure, temperature=self._fluid.temperature
            )
            if self._fluid is not None
            else None,
            name=self.name,
            scale_factor=self.scale_factor,
            upstream_pressure=Quantity(
                self.upstream_pressure.magnitude, self.upstream_pressure.units
            )
            if self._upstream_pressure is not None
            else None,
            downstream_pressure=Quantity(
                self.downstream_pressure.magnitude, self.downstream_pressure.units
            )
            if self._downstream_pressure is not None
            else None,
            upstream_temperature=Quantity(
                self._upstream_temperature.magnitude, self._upstream_temperature.units
            )
            if self._upstream_temperature is not None
            else None,
            max_flow_rate=Quantity(
                self.max_flow_rate.magnitude, self.max_flow_rate.units
            ),
            flow_type=self.flow_type,  # Enum, safe to share
            connector_length=Quantity(
                self.connector_length.magnitude, self.connector_length.units
            ),
            alert_errors=self.alert_errors,
            ignore_leaks=self._ignore_leaks,
        )

        # Add pipes without triggering sync
        new_pipeline._pipes = new_pipes
        # Explicitly DO NOT copy visualization elements
        new_pipeline.pipeline_viz = None
        return new_pipeline

    def __copy__(self) -> Self:
        """
        Shallow copy support (copy.copy()).
        Creates new pipeline sharing the same pipe references.
        """
        return self.copy(deep_copy_pipes=False)

    def __deepcopy__(self, memo: dict) -> Self:
        """
        Deep copy support (copy.deepcopy()).

        Handles memoization to avoid infinite recursion.

        :param memo: Memoization dict to track already-copied objects
        :return: Deep copied Pipeline instance
        """
        # Check if already copied
        pipeline_id = id(self)
        if pipeline_id in memo:
            return memo[pipeline_id]

        # Create the copy with deep copied pipes
        new_pipeline = self.copy(deep_copy_pipes=True)
        # Register in memo
        memo[pipeline_id] = new_pipeline

        # Deep copy each pipe and update memo
        for old_pipe, new_pipe in zip(self._pipes, new_pipeline._pipes):
            memo[id(old_pipe)] = new_pipe
        return new_pipeline


class FlowStation:
    """A collection of meters and regulators to monitor and control a fluid flow system."""

    def __init__(
        self,
        meters: typing.Optional[typing.Sequence[Meter]] = None,
        regulators: typing.Optional[typing.Sequence[Regulator]] = None,
        name: str = "Flow Station",
        width: str = "100%",
        height: str = "auto",
    ) -> None:
        """
        Initialize a flow station instance.

        :param meters: Optional list of Meter instances to include in the flow station
        :param regulators: Optional list of Regulator instances to include in the flow station
        :param name: Name of the flow station
        :param width: Width of the flow station display
        :param height: Height of the flow station display
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

    def add_meter(self, meter: Meter) -> Self:
        """Add a meter to the flow station."""
        self._meters.append(meter)
        return self

    def add_regulator(self, regulator: Regulator) -> Self:
        """Add a regulator to the flow station."""
        self._regulators.append(regulator)
        return self

    def remove_meter(self, index: int) -> Self:
        """Remove a meter by index."""
        if 0 <= index < len(self._meters):
            self._meters.pop(index)
        return self

    def remove_regulator(self, index: int) -> Self:
        """Remove a regulator by index."""
        if 0 <= index < len(self._regulators):
            self._regulators.pop(index)
        return self

    def clear_meters(self) -> Self:
        """Clear all meters from the flow station."""
        self._meters.clear()
        return self

    def clear_regulators(self) -> Self:
        """Clear all regulators from the flow station."""
        self._regulators.clear()
        return self

    def get_total_count(self) -> int:
        """Get the total count of meters and regulators."""
        return len(self._meters) + len(self._regulators)

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
        Display the flow station as a UI component with proper grid layout.

        :param width: Width of the container (CSS units)
        :param height: Height of the container (CSS units)
        :param show_meters_first: Whether to show meters before regulators
        :param meters_per_row: Number of meters per row
        :param regulators_per_row: Number of regulators per row
        :param label: Title label for the flow station (uses self.name if None)
        :param show_label: Whether to display the label above the flow station
        :param section_titles: Optional tuple to customize section titles (meters, regulators)
        :param show_empty_section: Whether to show sections even if empty
        :return: ui.card component containing the flow station visualization
        """
        container = (
            ui.card()
            .classes("w-full p-3 sm:p-4 lg:p-6")
            .style(f"width: {width}; height: {height}; min-height: 200px;")
        )
        with container:
            # Header section
            if show_label:
                display_label = label or self.name
                ui.label(display_label).classes(
                    "text-lg sm:text-xl lg:text-2xl font-semibold mb-3 sm:mb-4 lg:mb-5 text-center sm:text-left"
                )

            content_container = ui.column().classes("w-full gap-3 sm:gap-4 lg:gap-6")
            with content_container:
                # Build sections list
                sections = self._build_sections_list(
                    show_meters_first,
                    section_titles,
                    meters_per_row,
                    regulators_per_row,
                )

                # Render each section
                for section_type, section_title, items, items_per_row in sections:
                    if not items and not show_empty_section:
                        continue
                    self._render_section(
                        section_type, section_title, items, items_per_row
                    )

        return container

    def _build_sections_list(
        self,
        show_meters_first: bool,
        section_titles: typing.Optional[typing.Tuple[str, str]],
        meters_per_row: int,
        regulators_per_row: int,
    ) -> typing.List[typing.Tuple[str, str, typing.List, int]]:
        """Build the sections list based on display order."""
        if show_meters_first:
            meters_title = section_titles[0] if section_titles else "Meters"
            regulators_title = section_titles[1] if section_titles else "Regulators"
            return [
                ("meters", meters_title, self._meters, meters_per_row),
                ("regulators", regulators_title, self._regulators, regulators_per_row),
            ]
        else:
            regulators_title = section_titles[0] if section_titles else "Regulators"
            meters_title = section_titles[1] if section_titles else "Meters"
            return [
                ("regulators", regulators_title, self._regulators, regulators_per_row),
                ("meters", meters_title, self._meters, meters_per_row),
            ]

    def _render_section(
        self,
        section_type: str,
        section_title: str,
        items: typing.List[typing.Union[Meter, Regulator]],
        items_per_row: int,
    ):
        """
        Render a section (meters or regulators) with proper grid layout.

        :param section_type: Type of section ("meters" or "regulators")
        :param section_title: Display title for the section
        :param items: List of items to display
        :param items_per_row: Number of items per row
        """
        section_card = ui.card().classes("w-full p-3 sm:p-4 lg:p-5")
        with section_card:
            # Section header
            self._render_section_header(section_type, section_title, items)

            # Content area
            if not items:
                self._render_empty_state(section_type)
            else:
                self._render_items_grid(items, items_per_row)

    def _render_section_header(
        self,
        section_type: str,
        section_title: str,
        items: typing.List[typing.Union[Meter, Regulator]],
    ):
        """Render section header with title and count badge."""
        header_row = ui.row().classes(
            "w-full items-center justify-between mb-3 sm:mb-4 lg:mb-5"
        )
        with header_row:
            ui.label(section_title).classes(
                "text-base sm:text-lg lg:text-xl font-semibold"
            )

            # Count badge with theme-appropriate colors
            badge_color = "blue" if section_type == "meters" else "green"
            ui.badge(str(len(items)), color=badge_color)

    def _render_empty_state(self, section_type: str):
        """
        Render empty state when no items are available.

        :param section_type: Type of section ("meters" or "regulators")
        """
        icon = "speed" if section_type == "meters" else "tune"
        message = f"No {section_type} configured"

        empty_container = ui.column().classes(
            "w-full items-center justify-center py-6 sm:py-8 lg:py-12"
        )
        with empty_container:
            ui.icon(icon, size="2rem").classes("text-gray-400 mb-2 sm:mb-3")
            ui.label(message).classes("text-gray-500 text-center text-sm sm:text-base")

    def _render_items_grid(
        self,
        items: typing.List[typing.Union[Meter, Regulator]],
        items_per_row: int,
    ):
        """
        Render items in a responsive grid layout respecting items_per_row.

        :param items: List of items to display
        :param items_per_row: Number of items per row (desktop)
        """
        grid_container = ui.row().classes(
            "w-full gap-2 sm:gap-3 flex-wrap justify-center sm:justify-start"
        )

        with grid_container:
            # Add each item with responsive sizing
            for item in items:
                # Item container with responsive flex basis and increased padding
                # On small screens: 1 item per row (100% width) centered
                # On medium screens: 2 items per row (50% width minus gap)
                # On large screens: respect items_per_row parameter
                item_container = (
                    ui.column()
                    .classes(
                        f"flex-none w-full sm:w-[calc(50%-0.375rem)] "
                        f"lg:w-[calc({100 / items_per_row}%-{(items_per_row - 1) * 0.75 / items_per_row}rem)] "
                        f"px-3 sm:px-4 lg:px-2 flex justify-center items-center"
                    )
                    .style("min-width: 280px; max-width: 400px;")
                )

                with item_container:
                    item.show()
