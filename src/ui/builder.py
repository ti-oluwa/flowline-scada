"""
Dynamic Pipeline Builder UI with comprehensive property management.

This module provides an intuitive interface for constructing and managing pipelines
with real-time updates, validation, and automatic meter/regulator creation.
"""

import typing
import logging
from enum import Enum
import copy
import attrs
from functools import partial

from nicegui import ui
from pint.facets.plain import PlainQuantity
from src.ui.piping import PipeDirection
from src.ui.components import (
    Pipe,
    Pipeline,
    Meter,
    Regulator,
    FlowStation,
    PressureGauge,
    TemperatureGauge,
    FlowType,
    Fluid,
)
from src.units import Quantity

logger = logging.getLogger(__name__)

__all__ = ["PipelineBuilder", "PipelineBuilderUI", "PipeConfig", "FluidConfig"]


class PipelineEvent(Enum):
    """Events that can occur during pipeline construction."""

    PIPE_ADDED = "pipe_added"
    PIPE_REMOVED = "pipe_removed"
    PIPE_MOVED = "pipe_moved"
    PROPERTIES_UPDATED = "properties_updated"
    VALIDATION_CHANGED = "validation_changed"
    METERS_UPDATED = "meters_updated"


@attrs.define
class PipeConfig:
    """Configuration for a single pipe component."""

    name: str
    length: PlainQuantity[float]
    internal_diameter: PlainQuantity[float]
    upstream_pressure: PlainQuantity[float]
    downstream_pressure: PlainQuantity[float]
    material: str = "Steel"
    roughness: PlainQuantity[float] = attrs.field(factory=lambda: Quantity(0.0001, "m"))
    efficiency: float = 1.0
    elevation_difference: PlainQuantity[float] = attrs.field(
        factory=lambda: Quantity(0, "m")
    )
    direction: PipeDirection = PipeDirection.EAST
    scale_factor: float = 0.1
    max_flow_rate: PlainQuantity[float] = attrs.field(
        factory=lambda: Quantity(10.0, "ft^3/s")
    )
    flow_type: FlowType = FlowType.COMPRESSIBLE


@attrs.define
class FluidConfig:
    """Configuration for fluid properties."""

    name: str = "Methane"
    phase: typing.Literal["gas", "liquid"] = "gas"
    temperature: PlainQuantity[float] = attrs.field(
        factory=lambda: Quantity(60, "degF")
    )
    pressure: PlainQuantity[float] = attrs.field(factory=lambda: Quantity(100, "psi"))
    molecular_weight: PlainQuantity[float] = attrs.field(
        factory=lambda: Quantity(16.04, "g/mol")
    )
    specific_gravity: float = 0.6


PipelineT = typing.TypeVar("PipelineT", bound=Pipeline)
PipelineObserver = typing.Callable[[PipelineEvent, typing.Any], None]
PipeConfigValidator = typing.Callable[[typing.Sequence[PipeConfig]], typing.List[str]]
MeterFactory = typing.Callable[[PipeConfig, FluidConfig], typing.Iterable[Meter]]


def validate_pipeline(pipeline_config: typing.Sequence[PipeConfig]) -> typing.List[str]:
    """Default validation function with comprehensive checks."""
    errors = []

    if not pipeline_config:
        errors.append("Pipeline must contain at least one pipe")
        return errors

    for i, pipe_config in enumerate(pipeline_config):
        # Basic property validation
        if pipe_config.length.magnitude <= 0:
            errors.append(f"Pipe {i + 1}: Length must be positive")

        if pipe_config.internal_diameter.magnitude <= 0:
            errors.append(f"Pipe {i + 1}: Internal diameter must be positive")

        if pipe_config.upstream_pressure.magnitude < 0:
            errors.append(f"Pipe {i + 1}: Upstream pressure cannot be negative")

        if pipe_config.downstream_pressure.magnitude < 0:
            errors.append(f"Pipe {i + 1}: Downstream pressure cannot be negative")

        if (
            pipe_config.upstream_pressure.magnitude
            < pipe_config.downstream_pressure.magnitude
        ):
            errors.append(
                f"Pipe {i + 1}: Upstream pressure must be greater than downstream pressure"
            )

        if not (0 < pipe_config.efficiency <= 1):
            errors.append(f"Pipe {i + 1}: Efficiency must be between 0 and 1")

    # Direction compatibility validation
    for i in range(len(pipeline_config) - 1):
        current_dir = pipeline_config[i].direction
        next_dir = pipeline_config[i + 1].direction

        opposing_pairs = [
            (PipeDirection.NORTH, PipeDirection.SOUTH),
            (PipeDirection.SOUTH, PipeDirection.NORTH),
            (PipeDirection.EAST, PipeDirection.WEST),
            (PipeDirection.WEST, PipeDirection.EAST),
        ]

        if (current_dir, next_dir) in opposing_pairs:
            errors.append(
                f"Pipes {i + 1} and {i + 2}: Opposing flow directions cannot be connected"
            )

    return errors


def meter_factory(
    pipe_config: PipeConfig, fluid_config: FluidConfig
) -> typing.Iterable[Meter]:
    """Create appropriate meters for a pipe configuration."""
    meters = []

    # Pressure gauge for upstream pressure
    pressure_gauge = PressureGauge(
        value=pipe_config.upstream_pressure.to("psi").magnitude,
        min_value=0,
        max_value=pipe_config.upstream_pressure.to("psi").magnitude * 1.5,
        label=f"Pressure - {pipe_config.name}",
    )
    meters.append(pressure_gauge)

    # Temperature gauge
    temp_gauge = TemperatureGauge(
        value=fluid_config.temperature.to("degF").magnitude,
        min_value=-50,
        max_value=200,
        label=f"Temperature - {pipe_config.name}",
    )
    meters.append(temp_gauge)
    return meters


class PipelineBuilder(typing.Generic[PipelineT]):
    """Builder class for constructing pipelines with comprehensive validation."""

    def __init__(
        self,
        validator: PipeConfigValidator = validate_pipeline,
        meter_factory: MeterFactory = meter_factory,
        pipeline_class: typing.Type[PipelineT] = Pipeline,
    ) -> None:
        """
        Initialize the pipeline builder.

        :param validator: Function to validate the pipeline configuration.
        :param meter_factory: Function to create meters for each pipe.
        """
        self._pipe_configs: typing.List[PipeConfig] = []
        self._fluid_config = FluidConfig()
        self._observers: typing.List[PipelineObserver] = []
        self._validator = validator
        self._meter_factory = meter_factory
        self._errors: typing.List[str] = []
        self._pipeline_class = pipeline_class

    def add_observer(self, observer: PipelineObserver):
        """Add an observer for pipeline events."""
        self._observers.append(observer)

    def remove_observer(self, observer: PipelineObserver):
        """Remove an observer."""
        if observer in self._observers:
            self._observers.remove(observer)

    def notify_observers(self, event: PipelineEvent, data: typing.Any = None):
        """Notify all observers of an event."""
        for observer in self._observers:
            try:
                observer(event, data)
            except Exception as e:
                logger.error(f"Error notifying observer: {e}")

    def add_pipe(
        self, pipe_config: PipeConfig, index: typing.Optional[int] = None
    ) -> "PipelineBuilder":
        """Add a pipe at the specified index (or at the end)."""
        if index is None:
            index = len(self._pipe_configs)

        self._pipe_configs.insert(index, pipe_config)
        self.validate()
        self.notify_observers(
            PipelineEvent.PIPE_ADDED, {"pipe_config": pipe_config, "index": index}
        )
        logger.info(f"Added pipe '{pipe_config.name}' at index {index}")
        return self

    def remove_pipe(self, index: int) -> "PipelineBuilder":
        """Remove a pipe at the specified index."""
        if len(self._pipe_configs) <= 1:
            raise ValueError("Pipeline must contain at least one pipe")

        if 0 <= index < len(self._pipe_configs):
            removed_pipe = self._pipe_configs.pop(index)
            self.validate()
            self.notify_observers(
                PipelineEvent.PIPE_REMOVED,
                {"pipe_config": removed_pipe, "index": index},
            )
            logger.info(f"Removed pipe '{removed_pipe.name}' from index {index}")
        return self

    def move_pipe(self, from_index: int, to_index: int) -> "PipelineBuilder":
        """Move a pipe from one position to another."""
        if 0 <= from_index < len(self._pipe_configs) and 0 <= to_index < len(
            self._pipe_configs
        ):
            pipe_config = self._pipe_configs.pop(from_index)
            self._pipe_configs.insert(to_index, pipe_config)
            self.validate()
            self.notify_observers(
                PipelineEvent.PIPE_MOVED,
                {"from_index": from_index, "to_index": to_index},
            )
            logger.info(f"Moved pipe from index {from_index} to {to_index}")
        return self

    def update_pipe(self, index: int, pipe_config: PipeConfig) -> "PipelineBuilder":
        """Update a pipe configuration at the specified index."""
        if 0 <= index < len(self._pipe_configs):
            self._pipe_configs[index] = pipe_config
            self.validate()
            self.notify_observers(
                PipelineEvent.PROPERTIES_UPDATED,
                {"pipe_config": pipe_config, "index": index},
            )
            logger.info(f"Updated pipe at index {index}")
        return self

    def set_fluid_config(self, fluid_config: FluidConfig) -> "PipelineBuilder":
        """Set the fluid configuration."""
        self._fluid_config = fluid_config
        self.validate()
        self.notify_observers(
            PipelineEvent.PROPERTIES_UPDATED, {"fluid_config": fluid_config}
        )
        logger.info(f"Updated fluid configuration: {fluid_config.name}")
        return self

    def validate(self):
        """Validate the current pipeline configuration."""
        self._errors = self._validator(self._pipe_configs)
        self.notify_observers(
            PipelineEvent.VALIDATION_CHANGED, {"errors": self._errors}
        )

    def get_errors(self) -> typing.List[str]:
        """Get current validation errors."""
        return self._errors.copy()

    def is_valid(self) -> bool:
        """Check if the current pipeline configuration is valid."""
        return len(self._errors) == 0

    def get_pipe_configs(self) -> typing.List[PipeConfig]:
        """Get a copy of the current pipe configurations."""
        return self._pipe_configs.copy()

    def get_fluid_config(self) -> FluidConfig:
        """Get the current fluid configuration."""
        return copy.deepcopy(self._fluid_config)

    def build(self, **pipeline_kwargs) -> typing.Optional[PipelineT]:
        """
        Build the actual pipeline if configuration is valid.

        :param pipeline_kwargs: Additional keyword arguments for initializing the pipeline.
        :return: The constructed Pipeline object or None if invalid.
        """
        if not self.is_valid():
            logger.error("Cannot build pipeline: validation errors exist")
            return None

        try:
            # Create fluid
            fluid = Fluid.from_coolprop(
                fluid_name=self._fluid_config.name,
                phase=self._fluid_config.phase,
                temperature=self._fluid_config.temperature,
                pressure=self._fluid_config.pressure,
                molecular_weight=self._fluid_config.molecular_weight,
            )

            # Create pipes
            pipes = []
            for pipe_config in self._pipe_configs:
                pipe = Pipe(
                    length=pipe_config.length,
                    internal_diameter=pipe_config.internal_diameter,
                    upstream_pressure=pipe_config.upstream_pressure,
                    downstream_pressure=pipe_config.downstream_pressure,
                    material=pipe_config.material,
                    roughness=pipe_config.roughness,
                    efficiency=pipe_config.efficiency,
                    elevation_difference=pipe_config.elevation_difference,
                    fluid=fluid,
                    direction=pipe_config.direction,
                    name=pipe_config.name,
                    scale_factor=pipe_config.scale_factor,
                    max_flow_rate=pipe_config.max_flow_rate,
                    flow_type=pipe_config.flow_type,
                )
                pipes.append(pipe)

            pipeline_kwargs["pipes"] = pipes
            pipeline_kwargs["fluid"] = fluid
            pipeline = self._pipeline_class(**pipeline_kwargs)

            logger.info(f"Successfully built pipeline with {len(pipes)} pipes")
            return pipeline

        except Exception as e:
            logger.error(f"Error building pipeline: {e}")
            return None

    def build_flow_station(self, name: str = "Pipeline Flow Station") -> FlowStation:
        """Create appropriate meters and regulators for the current pipeline."""
        meters = []
        regulators = []

        for i, pipe_config in enumerate(self._pipe_configs):
            # Create meters for each pipe
            pipe_meters = self._meter_factory(pipe_config, self._fluid_config)
            meters.extend(pipe_meters)

            # Create regulators for pressure control (every other pipe)
            if i % 2 == 0:  # Add regulator every other pipe
                regulator = Regulator(
                    min_value=0,
                    max_value=pipe_config.upstream_pressure.to("psi").magnitude,
                    value=pipe_config.upstream_pressure.to("psi").magnitude * 0.8,
                    label=f"Pressure Control - {pipe_config.name}",
                )
                regulators.append(regulator)

        flow_station = FlowStation(
            meters=meters,
            regulators=regulators,
            name=name,
        )

        # Don't notify observers here to prevent recursion
        return flow_station


class PipelineBuilderUI:
    """Interactive UI for pipeline construction with real-time updates."""

    def __init__(
        self,
        builder: typing.Optional[PipelineBuilder] = None,
        theme_color: str = "blue",
    ) -> None:
        self.builder = builder or PipelineBuilder()
        self.builder.add_observer(self.on_pipeline_event)
        self.theme_color = theme_color

        # UI components
        self.main_container = None
        self.pipes_container = None
        self.validation_container = None
        self.pipeline_preview = None
        self.flow_station_container = None
        self.properties_panel = None

        # Current state
        self.selected_pipe_index: typing.Optional[int] = None
        self.current_pipeline: typing.Optional[Pipeline] = None
        self.current_flow_station: typing.Optional[FlowStation] = None

    def get_primary_button_classes(self, additional_classes: str = "") -> str:
        """Get primary button classes with theme color."""
        base_classes = (
            f"bg-{self.theme_color}-500 hover:bg-{self.theme_color}-600 text-white"
        )
        return f"{base_classes} {additional_classes}".strip()

    def get_secondary_button_classes(self, additional_classes: str = "") -> str:
        """Get secondary button classes with theme color."""
        base_classes = f"bg-{self.theme_color}-100 hover:bg-{self.theme_color}-200 text-{self.theme_color}-800"
        return f"{base_classes} {additional_classes}".strip()

    def get_accent_button_classes(self, additional_classes: str = "") -> str:
        """Get accent button classes with theme color."""
        base_classes = f"bg-{self.theme_color}-200 hover:bg-{self.theme_color}-300 text-{self.theme_color}-800"
        return f"{base_classes} {additional_classes}".strip()

    def get_danger_button_classes(self, additional_classes: str = "") -> str:
        """Get danger button classes (always red for safety)."""
        base_classes = "bg-red-500 hover:bg-red-600 text-white"
        return f"{base_classes} {additional_classes}".strip()

    def on_pipeline_event(self, event: PipelineEvent, data: typing.Any):
        """Handle pipeline events and update UI accordingly."""
        try:
            if event == PipelineEvent.PIPE_ADDED:
                self.refresh_pipes_list()
                self.refresh_pipeline_preview()
            elif event == PipelineEvent.PIPE_REMOVED:
                self.refresh_pipes_list()
                self.refresh_pipeline_preview()
                if (
                    self.selected_pipe_index is not None
                    and self.selected_pipe_index >= len(self.builder.get_pipe_configs())
                ):
                    self.selected_pipe_index = None
                    self.refresh_properties_panel()
            elif event == PipelineEvent.PIPE_MOVED:
                self.refresh_pipes_list()
                self.refresh_pipeline_preview()
            elif event == PipelineEvent.PROPERTIES_UPDATED:
                self.refresh_pipes_list()
                self.refresh_pipeline_preview()
                # Don't refresh flow station here to avoid recursion
            elif event == PipelineEvent.VALIDATION_CHANGED:
                self.refresh_validation_display()
                # Refresh flow station only on validation changes to avoid recursion
                self.refresh_flow_station()
            # Remove METERS_UPDATED handling to prevent recursion
        except Exception as e:
            logger.error(f"Error handling pipeline event {event}: {e}")

    def show(
        self,
        min_width: str = "300px",
        max_width: str = "1200px",
        ui_label: str = "Pipeline Builder",
        pipeline_label: str = "Pipeline",
        flow_station_label: str = "Flow Station",
        theme_color: typing.Optional[str] = None,
        show_label: bool = True,
    ) -> ui.column:
        """
        Render the pipeline builder UI.

        :param min_width: Minimum width of the main container.
        :param max_width: Maximum width of the main container.
        :param ui_label: Label for the UI header.
        :param pipeline_label: Label for the pipeline preview.
        :param flow_station_label: Label for the flow station panel.
        :param theme_color: Theme color for buttons and accents.
        :param show_label: Whether to show the UI label header.
        :return: The main UI container.
        """
        # Override theme color if provided
        if theme_color is not None:
            self.theme_color = theme_color

        self.main_container = (
            ui.column()
            .classes("w-full min-h-screen gap-2 p-2 sm:gap-4 sm:p-4")
            .style(
                f"min-width: min({min_width}, 100%); max-width: {max_width}; margin-left: auto; margin-right: auto;"
            )
        )

        with self.main_container:
            if show_label:
                ui.label(ui_label).classes(
                    "text-xl sm:text-2xl lg:text-3xl font-bold text-center mb-2 sm:mb-4"
                )

            # Top panel - Pipeline preview
            self.show_preview_panel(pipeline_label=pipeline_label)

            # Main layout
            main_layout = ui.row().classes(
                "w-full gap-2 sm:gap-4 flex-1 flex-wrap lg:flex-nowrap"
            )

            with main_layout:
                # Left panel - Pipeline construction
                left_panel = ui.column().classes(
                    "w-full lg:w-1/2 gap-2 sm:gap-4 min-w-0"
                )
                with left_panel:
                    self.show_construction_panel()

                # Right panel - Properties
                right_panel = ui.column().classes(
                    "w-full lg:w-1/2 gap-2 sm:gap-4 min-w-0"
                )
                with right_panel:
                    self.show_properties_panel()

            # Bottom panel - Flow station
            self.show_flow_station_panel(flow_station_label=flow_station_label)

        # Initialize with one default pipe
        default_pipe = PipeConfig(
            name="Pipe-1",
            length=Quantity(10, "ft"),
            internal_diameter=Quantity(6, "inch"),
            upstream_pressure=Quantity(150, "psi"),
            downstream_pressure=Quantity(145, "psi"),
        )
        self.builder.add_pipe(default_pipe)
        return self.main_container

    def show_construction_panel(self):
        """Create the pipeline construction panel."""
        construction_card = ui.card().classes("w-full p-2 sm:p-4")

        with construction_card:
            ui.label("Pipeline Construction").classes(
                "text-lg sm:text-xl font-semibold mb-2 sm:mb-3"
            )

            # Add pipe button
            ui.button(
                "+ Add Pipe", on_click=self.show_pipe_dialog, color=self.theme_color
            ).classes(self.get_primary_button_classes("mb-2 sm:mb-4 w-full sm:w-auto"))

            # Pipes list
            self.pipes_container = ui.column().classes("w-full gap-1 sm:gap-2")

            # Validation display
            self.validation_container = ui.column().classes("w-full mt-2 sm:mt-4")

        self.refresh_pipes_list()
        self.refresh_validation_display()

    def show_properties_panel(self):
        """Create the properties panel."""
        properties_card = ui.card().classes("w-full p-2 sm:p-4")

        with properties_card:
            ui.label("Properties").classes(
                "text-lg sm:text-xl font-semibold mb-2 sm:mb-3"
            )

            # Side-by-side forms container
            forms_container = ui.row().classes(
                "w-full gap-2 sm:gap-4 flex-wrap xl:flex-nowrap"
            )

            with forms_container:
                # Pipe properties form (left side on large screens)
                pipe_form_container = ui.column().classes(
                    "w-full xl:w-1/2 gap-2 sm:gap-3 min-w-0"
                )

                # Fluid properties form (right side on large screens)
                fluid_form_container = ui.column().classes(
                    "w-full xl:w-1/2 gap-2 sm:gap-3 min-w-0"
                )

            # Store references for dynamic updates
            self.pipe_form_container = pipe_form_container
            self.fluid_form_container = fluid_form_container
            self.properties_panel = forms_container

        self.refresh_properties_panel()

    def show_preview_panel(self, pipeline_label: str = "Pipeline"):
        """Create the pipeline preview panel."""
        preview_card = (
            ui.card()
            .classes("w-full p-2 sm:p-4")
            .style("max-height: 800px; overflow-y: auto;")
        )

        with preview_card:
            ui.label("Pipeline Preview").classes(
                "text-lg sm:text-xl font-semibold mb-2 sm:mb-3"
            )

            # Responsive preview container with horizontal scroll on small screens
            self.pipeline_preview = ui.column().classes("w-full overflow-x-auto")

        self.refresh_pipeline_preview(label=pipeline_label)

    def show_flow_station_panel(self, flow_station_label: str = "Flow Station"):
        """Create the flow station panel."""
        flow_station_card = ui.card().classes("w-full p-2 sm:p-4")

        with flow_station_card:
            ui.label("Flow Station - Meters & Regulators").classes(
                "text-lg sm:text-xl font-semibold mb-2 sm:mb-3"
            )

            # Responsive flow station container with horizontal scroll
            self.flow_station_container = ui.column().classes("w-full overflow-x-auto")

        self.refresh_flow_station(label=flow_station_label)

    def refresh_pipes_list(self):
        """Refresh the pipes list display."""
        if self.pipes_container:
            self.pipes_container.clear()

            with self.pipes_container:
                pipe_configs = self.builder.get_pipe_configs()

                for i, pipe_config in enumerate(pipe_configs):
                    # Responsive pipe row
                    pipe_row = ui.row().classes(
                        "w-full items-center gap-2 p-2 sm:p-3 border rounded-lg hover:shadow-md transition-shadow flex-wrap sm:flex-nowrap"
                    )

                    with pipe_row:
                        # Pipe info - responsive layout
                        pipe_info = ui.column().classes("flex-1 min-w-0")
                        with pipe_info:
                            ui.label(f"{pipe_config.name}").classes(
                                "font-medium text-sm sm:text-base truncate"
                            )
                            ui.label(
                                f"L: {pipe_config.length}, D: {pipe_config.internal_diameter}"
                            ).classes("text-xs sm:text-sm text-gray-600")

                        # Action buttons - responsive
                        actions = ui.row().classes("gap-1 flex-wrap sm:flex-nowrap")
                        with actions:
                            ui.button(
                                "Edit",
                                on_click=partial(self.select_pipe, i),
                                color=self.theme_color,
                            ).classes(
                                self.get_primary_button_classes(
                                    "text-xs sm:text-sm px-2 py-1"
                                )
                            )
                            ui.button(
                                "↑",
                                on_click=partial(self.move_pipe_up, i),
                                color=self.theme_color,
                            ).classes(
                                self.get_secondary_button_classes(
                                    "text-xs sm:text-sm px-2 py-1"
                                )
                            ).props("disabled" if i == 0 else "")
                            ui.button(
                                "↓",
                                on_click=partial(self.move_pipe_down, i),
                                color=self.theme_color,
                            ).classes(
                                self.get_secondary_button_classes(
                                    "text-xs sm:text-sm px-2 py-1"
                                )
                            ).props("disabled" if i == len(pipe_configs) - 1 else "")
                            ui.button(
                                "✕", on_click=partial(self.remove_pipe, i), color="red"
                            ).classes(
                                self.get_danger_button_classes(
                                    "text-xs sm:text-sm px-2 py-1"
                                )
                            ).props("disabled" if len(pipe_configs) <= 1 else "")

    def refresh_validation_display(self):
        """Refresh the validation display."""
        if self.validation_container:
            self.validation_container.clear()

            with self.validation_container:
                errors = self.builder.get_errors()

                if errors:
                    ui.label("Validation Errors:").classes("font-medium text-red-600")
                    for error in errors:
                        ui.label(f"• {error}").classes("text-sm text-red-600 ml-4")
                else:
                    ui.label("✓ Pipeline configuration is valid").classes(
                        "text-green-600 font-medium"
                    )

    def refresh_properties_panel(self):
        """Refresh the properties panel."""
        if hasattr(self, "pipe_form_container") and hasattr(
            self, "fluid_form_container"
        ):
            # Clear both containers
            self.pipe_form_container.clear()
            self.fluid_form_container.clear()

            # Always show fluid properties in the right container
            with self.fluid_form_container:
                self.show_fluid_properties_form()

            # Show pipe properties in the left container if a pipe is selected
            with self.pipe_form_container:
                if self.selected_pipe_index is not None:
                    pipe_configs = self.builder.get_pipe_configs()
                    if self.selected_pipe_index < len(pipe_configs):
                        self.show_pipe_properties_form(
                            pipe_configs[self.selected_pipe_index]
                        )
                else:
                    # Show placeholder when no pipe is selected
                    placeholder_card = ui.card().classes(
                        "w-full p-4 border-2 border-dashed border-gray-300"
                    )
                    with placeholder_card:
                        placeholder_column = ui.column().classes(
                            "items-center justify-center gap-2"
                        )
                        with placeholder_column:
                            ui.icon("edit", size="2rem").classes("text-gray-400")
                            ui.label("Select a pipe to edit").classes(
                                "text-gray-500 text-center"
                            )
                            ui.label("Click 'Edit' button on any pipe").classes(
                                "text-xs text-gray-400 text-center"
                            )

    def refresh_pipeline_preview(self, label: str = "Pipeline"):
        """Refresh the pipeline preview."""
        if self.pipeline_preview:
            self.pipeline_preview.clear()

            with self.pipeline_preview:
                if self.builder.is_valid():
                    pipeline = self.builder.build()
                    if pipeline:
                        self.current_pipeline = pipeline
                        pipeline.show(label=label)
                else:
                    ui.label("Fix validation errors to see preview").classes(
                        "text-gray-500 italic"
                    )

    def refresh_flow_station(self, label: str = "Flow Station"):
        """Refresh the flow station display."""
        if self.flow_station_container:
            self.flow_station_container.clear()

            with self.flow_station_container:
                if self.builder.is_valid() and self.builder.get_pipe_configs():
                    flow_station = self.builder.build_flow_station()
                    self.current_flow_station = flow_station
                    flow_station.show(label=label, meters_per_row=3)
                else:
                    ui.label(
                        "Configure valid pipeline to see meters and regulators"
                    ).classes("text-gray-500 italic")

    def show_pipe_dialog(self):
        """Show dialog to add a new pipe."""
        with (
            ui.dialog() as dialog,
            ui.card().classes("w-full max-w-md mx-2 sm:w-96 p-3 sm:p-4"),
        ):
            ui.label("Add New Pipe").classes("text-lg font-semibold mb-3")

            # Form inputs - responsive
            form_container = ui.column().classes("w-full gap-2 sm:gap-3")

            with form_container:
                name_input = ui.input(
                    "Pipe Name",
                    value=f"Pipe-{len(self.builder.get_pipe_configs()) + 1}",
                ).classes("w-full")

                # Dimensions row
                dimensions_row = ui.row().classes(
                    "w-full gap-2 flex-wrap sm:flex-nowrap"
                )
                with dimensions_row:
                    length_input = ui.number(
                        "Length (ft)", value=10, min=0.1, step=0.1
                    ).classes("flex-1 min-w-0")
                    diameter_input = ui.number(
                        "Diameter (inch)", value=6, min=0.1, step=0.1
                    ).classes("flex-1 min-w-0")

                # Pressure row
                pressure_row = ui.row().classes("w-full gap-2 flex-wrap sm:flex-nowrap")
                with pressure_row:
                    upstream_pressure_input = ui.number(
                        "Upstream Pressure (psi)", value=150, min=0, step=1
                    ).classes("flex-1 min-w-0")
                    downstream_pressure_input = ui.number(
                        "Downstream Pressure (psi)", value=145, min=0, step=1
                    ).classes("flex-1 min-w-0")

                # Material and direction row
                material_dir_row = ui.row().classes(
                    "w-full gap-2 flex-wrap sm:flex-nowrap"
                )
                with material_dir_row:
                    material_input = ui.input("Material", value="Steel").classes(
                        "flex-1 min-w-0"
                    )
                    direction_select = ui.select(
                        options=[d.value for d in PipeDirection],
                        value=PipeDirection.EAST.value,
                        label="Flow Direction",
                    ).classes("flex-1 min-w-0")

                # Position selection
                pipe_configs = self.builder.get_pipe_configs()
                position_options = ["End"] + [
                    f"Before Pipe {i + 1}" for i in range(len(pipe_configs))
                ]
                position_select = ui.select(
                    options=position_options, value="End", label="Insert Position"
                ).classes("w-full")

                # Buttons - responsive
                button_row = ui.row().classes("w-full justify-end gap-2 mt-4 flex-wrap")
                with button_row:
                    ui.button("Cancel", on_click=dialog.close, color="red").classes(
                        self.get_secondary_button_classes(
                            "px-4 py-2 flex-1 sm:flex-none"
                        )
                    )
                    ui.button(
                        "Add Pipe",
                        on_click=lambda: self._add_pipe_from_dialog(
                            dialog,
                            name_input,
                            length_input,
                            diameter_input,
                            upstream_pressure_input,
                            downstream_pressure_input,
                            direction_select,
                            material_input,
                            position_select,
                        ),
                        color=self.theme_color,
                    ).classes(
                        self.get_primary_button_classes("px-4 py-2 flex-1 sm:flex-none")
                    )

        dialog.open()

    def _add_pipe_from_dialog(
        self,
        dialog,
        name_input: ui.input,
        length_input: ui.number,
        diameter_input: ui.number,
        upstream_pressure_input: ui.number,
        downstream_pressure_input: ui.number,
        direction_select: ui.select,
        material_input: ui.input,
        position_select: ui.select,
    ):
        """
        Add pipe from dialog inputs.

        :param dialog: The dialog instance to close after adding.
        :param name_input: Input for pipe name.
        :param length_input: Input for pipe length.
        :param diameter_input: Input for pipe diameter.
        :param upstream_pressure_input: Input for upstream pressure.
        :param downstream_pressure_input: Input for downstream pressure.
        :param direction_select: Select for flow direction.
        :param material_input: Input for pipe material.

        """
        try:
            pipe_config = PipeConfig(
                name=name_input.value
                or f"Pipe-{len(self.builder.get_pipe_configs()) + 1}",
                length=Quantity(length_input.value, "ft"),
                internal_diameter=Quantity(diameter_input.value, "inch"),
                upstream_pressure=Quantity(upstream_pressure_input.value, "psi"),
                downstream_pressure=Quantity(downstream_pressure_input.value, "psi"),
                direction=PipeDirection(direction_select.value),
                material=material_input.value or "Steel",
            )

            # Determine insertion index
            index = None
            if position_select.value != "End":
                # Extract pipe number from "Before Pipe X"
                pipe_num = int(position_select.value.split()[-1]) - 1  # type: ignore
                index = pipe_num

            self.builder.add_pipe(pipe_config, index)
            dialog.close()

        except Exception as e:
            logger.error(f"Error adding pipe: {e}")
            ui.notify(f"Error adding pipe: {str(e)}", type="negative")

    def select_pipe(self, index: int):
        """Select a pipe for editing."""
        self.selected_pipe_index = index
        self.refresh_properties_panel()

    def move_pipe_up(self, index: int):
        """Move pipe up in the sequence."""
        if index > 0:
            self.builder.move_pipe(index, index - 1)
            if self.selected_pipe_index == index:
                self.selected_pipe_index = index - 1

    def move_pipe_down(self, index: int):
        """Move pipe down in the sequence."""
        pipe_configs = self.builder.get_pipe_configs()
        if index < len(pipe_configs) - 1:
            self.builder.move_pipe(index, index + 1)
            if self.selected_pipe_index == index:
                self.selected_pipe_index = index + 1

    def remove_pipe(self, index: int):
        """Remove a pipe from the pipeline."""
        try:
            self.builder.remove_pipe(index)
            if self.selected_pipe_index == index:
                self.selected_pipe_index = None
        except ValueError as e:
            ui.notify(str(e), type="warning")

    def show_pipe_properties_form(self, pipe_config: PipeConfig):
        """Create form for editing pipe properties."""
        # Header with better styling
        pipe_header = ui.card().classes(
            f"w-full mb-3 bg-gradient-to-r from-{self.theme_color}-50 to-{self.theme_color}-100 border-l-4 border-{self.theme_color}-500"
        )
        with pipe_header:
            ui.label(f"Editing: {pipe_config.name}").classes(
                f"font-semibold text-{self.theme_color}-800 p-2"
            )

        # Form container with responsive inputs
        form_container = ui.column().classes("w-full gap-2 sm:gap-3")

        with form_container:
            # Basic properties
            name_input = ui.input("Name", value=pipe_config.name).classes("w-full")

            # Dimensions row - side by side on larger screens
            dimensions_row = ui.row().classes("w-full gap-2 flex-wrap sm:flex-nowrap")
            with dimensions_row:
                length_input = ui.number(
                    "Length (ft)",
                    value=pipe_config.length.to("ft").magnitude,
                    min=0.1,
                    step=0.1,
                ).classes("flex-1 min-w-0")
                diameter_input = ui.number(
                    "Diameter (inch)",
                    value=pipe_config.internal_diameter.to("inch").magnitude,
                    min=0.1,
                    step=0.1,
                ).classes("flex-1 min-w-0")

            # Pressure row - side by side on larger screens
            pressure_row = ui.row().classes("w-full gap-2 flex-wrap sm:flex-nowrap")
            with pressure_row:
                upstream_pressure_input = ui.number(
                    "Upstream Pressure (psi)",
                    value=pipe_config.upstream_pressure.to("psi").magnitude,
                    min=0,
                    step=1,
                ).classes("flex-1 min-w-0")
                downstream_pressure_input = ui.number(
                    "Downstream Pressure (psi)",
                    value=pipe_config.downstream_pressure.to("psi").magnitude,
                    min=0,
                    step=1,
                ).classes("flex-1 min-w-0")

            # Material and direction row
            material_direction_row = ui.row().classes(
                "w-full gap-2 flex-wrap sm:flex-nowrap"
            )
            with material_direction_row:
                material_input = ui.input(
                    "Material", value=pipe_config.material
                ).classes("flex-1 min-w-0")
                direction_select = ui.select(
                    options=[d.value for d in PipeDirection],
                    value=pipe_config.direction.value,
                    label="Flow Direction",
                ).classes("flex-1 min-w-0")

            # Efficiency
            efficiency_input = ui.number(
                "Efficiency", value=pipe_config.efficiency, min=0.1, max=1.0, step=0.01
            ).classes("w-full sm:w-48")

            # Action buttons - responsive
            buttons_row = ui.row().classes("w-full gap-2 mt-3 flex-wrap")
            with buttons_row:
                ui.button(
                    "Update Pipe",
                    on_click=lambda: self._update_pipe_from_form(
                        name_input,
                        length_input,
                        diameter_input,
                        upstream_pressure_input,
                        downstream_pressure_input,
                        direction_select,
                        material_input,
                        efficiency_input,
                    ),
                    color=self.theme_color,
                ).classes(
                    self.get_primary_button_classes("px-4 py-2 flex-1 sm:flex-none")
                )

                ui.button(
                    "Clear Selection",
                    on_click=self.clear_pipe_selection,
                    color=self.theme_color,
                ).classes(
                    self.get_accent_button_classes("px-4 py-2 flex-1 sm:flex-none")
                )

    def show_fluid_properties_form(self):
        """Create form for editing fluid properties."""
        # Header with better styling
        fluid_header = ui.card().classes(
            f"w-full mb-3 bg-gradient-to-r from-{self.theme_color}-50 to-{self.theme_color}-100 border-l-4 border-{self.theme_color}-500"
        )
        with fluid_header:
            ui.label("Fluid Properties").classes(
                f"font-semibold text-{self.theme_color}-800 p-2"
            )

        fluid_config = self.builder.get_fluid_config()

        # Form container with responsive inputs
        form_container = ui.column().classes("w-full gap-2 sm:gap-3")

        with form_container:
            # Name and phase row
            name_phase_row = ui.row().classes("w-full gap-2 flex-wrap sm:flex-nowrap")
            with name_phase_row:
                name_input = ui.input("Fluid Name", value=fluid_config.name).classes(
                    "flex-1 min-w-0"
                )
                phase_select = ui.select(
                    options=["gas", "liquid"], value=fluid_config.phase, label="Phase"
                ).classes("flex-1 min-w-0")

            # Temperature and pressure row
            temp_pressure_row = ui.row().classes(
                "w-full gap-2 flex-wrap sm:flex-nowrap"
            )
            with temp_pressure_row:
                temperature_input = ui.number(
                    "Temperature (°F)",
                    value=fluid_config.temperature.to("degF").magnitude,
                    step=1,
                ).classes("flex-1 min-w-0")
                pressure_input = ui.number(
                    "Pressure (psi)",
                    value=fluid_config.pressure.to("psi").magnitude,
                    min=0,
                    step=1,
                ).classes("flex-1 min-w-0")

            # Molecular weight and specific gravity row
            mol_gravity_row = ui.row().classes("w-full gap-2 flex-wrap sm:flex-nowrap")
            with mol_gravity_row:
                molecular_weight_input = ui.number(
                    "Molecular Weight (g/mol)",
                    value=fluid_config.molecular_weight.to("g/mol").magnitude,
                    min=0.1,
                    step=0.1,
                ).classes("flex-1 min-w-0")
                specific_gravity_input = ui.number(
                    "Specific Gravity",
                    value=fluid_config.specific_gravity,
                    min=0.1,
                    step=0.01,
                ).classes("flex-1 min-w-0")

            # Update button - responsive
            ui.button(
                "Update Fluid",
                on_click=lambda: self._update_fluid_from_form(
                    name_input,
                    phase_select,
                    temperature_input,
                    pressure_input,
                    molecular_weight_input,
                    specific_gravity_input,
                ),
                color=self.theme_color,
            ).classes(
                self.get_primary_button_classes("px-4 py-2 mt-3 w-full sm:w-auto")
            )

    def _update_pipe_from_form(
        self,
        name_input,
        length_input,
        diameter_input,
        upstream_pressure_input,
        downstream_pressure_input,
        direction_select,
        material_input,
        efficiency_input,
    ):
        """Update pipe configuration from form inputs."""
        try:
            if self.selected_pipe_index is not None:
                updated_config = PipeConfig(
                    name=name_input.value,
                    length=Quantity(length_input.value, "ft"),
                    internal_diameter=Quantity(diameter_input.value, "inch"),
                    upstream_pressure=Quantity(upstream_pressure_input.value, "psi"),
                    downstream_pressure=Quantity(
                        downstream_pressure_input.value, "psi"
                    ),
                    direction=PipeDirection(direction_select.value),
                    material=material_input.value,
                    efficiency=efficiency_input.value,
                )

                self.builder.update_pipe(self.selected_pipe_index, updated_config)
                ui.notify("Pipe updated successfully", type="positive")

        except Exception as e:
            logger.error(f"Error updating pipe: {e}")
            ui.notify(f"Error updating pipe: {str(e)}", type="negative")

    def _update_fluid_from_form(
        self,
        name_input,
        phase_select,
        temperature_input,
        pressure_input,
        molecular_weight_input,
        specific_gravity_input,
    ):
        """Update fluid configuration from form inputs."""
        try:
            updated_config = FluidConfig(
                name=name_input.value,
                phase=phase_select.value,
                temperature=Quantity(temperature_input.value, "degF"),
                pressure=Quantity(pressure_input.value, "psi"),
                molecular_weight=Quantity(molecular_weight_input.value, "g/mol"),
                specific_gravity=specific_gravity_input.value,
            )

            self.builder.set_fluid_config(updated_config)
            ui.notify("Fluid properties updated successfully", type="positive")

        except Exception as e:
            logger.error(f"Error updating fluid: {e}")
            ui.notify(f"Error updating fluid: {str(e)}", type="negative")

    def clear_pipe_selection(self):
        """Clear pipe selection and return to fluid properties."""
        self.selected_pipe_index = None
        self.refresh_properties_panel()
