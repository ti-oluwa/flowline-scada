"""
Pipeline Management UI
"""

import typing
import logging
import copy
from attrs import evolve
from functools import partial
from nicegui import ui

from src.config.manage import ConfigurationManager, ConfigurationState
from src.config.ui import ConfigurationUI
from src.ui.piping import PipeDirection
from src.ui.components import (
    Pipe,
    Pipeline,
    Meter,
    Regulator,
    FlowStation,
    PressureGauge,
    TemperatureGauge,
    FlowMeter,
)
from src.flow import Fluid
from src.units import Quantity, QuantityUnit, QuantityUnitT, UnitSystem, IMPERIAL, SI
from src.types import (
    PipelineEvent,
    PipeConfig,
    FluidConfig,
    FlowStationConfig,
    FlowType,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PipelineManager",
    "PipelineManagerUI",
    "UpstreamStationFactory",
    "DownstreamStationFactory",
    "validate_pipe_configs",
]


PipelineT = typing.TypeVar("PipelineT", bound=Pipeline)
PipelineObserver = typing.Callable[[PipelineEvent, typing.Any], None]
PipeConfigValidator = typing.Callable[[typing.Sequence[PipeConfig]], typing.List[str]]
FlowStationFactory = typing.Callable[["PipelineManager[PipelineT]"], FlowStation]


def validate_pipe_configs(
    pipeline_config: typing.Sequence[PipeConfig],
) -> typing.List[str]:
    """Default validation function with comprehensive checks."""
    errors = []

    if not pipeline_config:
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


class UpstreamStationFactory(typing.Generic[PipelineT]):
    """Factory to create an upstream flow station."""

    def __init__(self, name: str, config: FlowStationConfig) -> None:
        """
        Initialize the upstream flow station factory.

        :param name: Name of the flow station
        :param config: `FlowStationConfig` object containing all meter and regulator configurations
        """
        self.name = name
        self.config = config

    def set_config(self, config: FlowStationConfig) -> None:
        """Update the factory configuration."""
        self.config = config

    def build_meters(self, manager: "PipelineManager[PipelineT]") -> typing.List[Meter]:
        """Create meters for the upstream station."""
        cfg = self.config
        pipeline = manager.get_pipeline()
        pressure_gauge = PressureGauge(
            value=pipeline.upstream_pressure.to(cfg.pressure_unit).magnitude,
            min_value=cfg.pressure_guage.min_value,
            max_value=cfg.pressure_guage.max_value,
            units=cfg.pressure_guage.units,
            label=cfg.pressure_guage.label,
            width=cfg.pressure_guage.width,
            height=cfg.pressure_guage.height,
            precision=cfg.pressure_guage.precision,
            alarm_high=cfg.pressure_guage.alarm_high,
            alarm_low=cfg.pressure_guage.alarm_low,
            animation_speed=cfg.pressure_guage.animation_speed,
            animation_interval=cfg.pressure_guage.animation_interval,
            update_func=lambda: pipeline.upstream_pressure.to(
                cfg.pressure_unit
            ).magnitude,
            update_interval=cfg.pressure_guage.update_interval,
        )
        temperature_gauge = TemperatureGauge(
            value=pipeline.fluid.temperature.to(cfg.temperature_unit).magnitude
            if pipeline.fluid
            else 0,
            min_value=cfg.temperature_guage.min_value,
            max_value=cfg.temperature_guage.max_value,
            units=cfg.temperature_guage.units,
            label=cfg.temperature_guage.label,
            width=cfg.temperature_guage.width,
            height=cfg.temperature_guage.height,
            precision=cfg.temperature_guage.precision,
            alarm_high=cfg.temperature_guage.alarm_high,
            alarm_low=cfg.temperature_guage.alarm_low,
            animation_speed=cfg.temperature_guage.animation_speed,
            animation_interval=cfg.temperature_guage.animation_interval,
            update_func=lambda: pipeline.fluid.temperature.to(
                cfg.temperature_unit
            ).magnitude
            if pipeline.fluid
            else 0,
            update_interval=cfg.temperature_guage.update_interval,
        )
        flow_meter = FlowMeter(
            value=pipeline.inlet_flow_rate.to(cfg.flow_unit).magnitude,
            min_value=cfg.flow_meter.min_value,
            max_value=max(
                cfg.flow_meter.max_value,
                pipeline.max_flow_rate.to(cfg.flow_unit).magnitude,
            ),
            units=cfg.flow_meter.units,
            label=cfg.flow_meter.label,
            width=cfg.flow_meter.width,
            height=cfg.flow_meter.height,
            precision=cfg.flow_meter.precision,
            alarm_high=cfg.flow_meter.alarm_high,
            alarm_low=cfg.flow_meter.alarm_low,
            animation_speed=cfg.flow_meter.animation_speed,
            animation_interval=cfg.flow_meter.animation_interval,
            flow_direction=str(pipeline.pipes[0].direction)
            if pipeline.pipes
            else "east",  # type: ignore
            update_func=lambda: pipeline.inlet_flow_rate.to(cfg.flow_unit).magnitude,
            update_interval=cfg.flow_meter.update_interval,
        )
        return [pressure_gauge, temperature_gauge, flow_meter]

    def build_regulators(
        self, manager: "PipelineManager[PipelineT]"
    ) -> typing.Iterable[Regulator]:
        """Create regulators for the upstream station."""
        cfg = self.config
        pipeline = manager.get_pipeline()

        def set_pressure(value: float):
            pipeline.set_upstream_pressure(
                Quantity(value, cfg.pressure_unit), sync=True
            ).update_viz()
            manager.sync()

        def set_temperature(value: float):
            pipeline.set_upstream_temperature(
                Quantity(value, cfg.temperature_unit)
            ).update_viz()
            manager.sync()

        pressure_regulator = Regulator(
            value=pipeline.upstream_pressure.to(cfg.pressure_unit).magnitude,
            min_value=cfg.pressure_regulator.min_value,
            max_value=cfg.pressure_regulator.max_value,
            step=cfg.pressure_regulator.step,
            units=cfg.pressure_regulator.units,
            label=cfg.pressure_regulator.label,
            width=cfg.pressure_regulator.width,
            height=cfg.pressure_regulator.height,
            precision=cfg.pressure_regulator.precision,
            setter_func=set_pressure,
            alarm_high=cfg.pressure_regulator.alarm_high,
            alarm_low=cfg.pressure_regulator.alarm_low,
            alert_errors=cfg.pressure_regulator.alert_errors,
        )
        temperature_regulator = Regulator(
            value=pipeline.fluid.temperature.to(cfg.temperature_unit).magnitude
            if pipeline.fluid
            else 0,
            min_value=cfg.temperature_regulator.min_value,
            max_value=cfg.temperature_regulator.max_value,
            step=cfg.temperature_regulator.step,
            units=cfg.temperature_regulator.units,
            label=cfg.temperature_regulator.label,
            width=cfg.temperature_regulator.width,
            height=cfg.temperature_regulator.height,
            precision=cfg.temperature_regulator.precision,
            setter_func=set_temperature,
            alarm_high=cfg.temperature_regulator.alarm_high,
            alarm_low=cfg.temperature_regulator.alarm_low,
            alert_errors=cfg.temperature_regulator.alert_errors,
        )
        return [pressure_regulator, temperature_regulator]

    def __call__(self, manager: "PipelineManager[PipelineT]") -> FlowStation:
        """Build the upstream flow station."""
        meters = list(self.build_meters(manager))
        regulators = list(self.build_regulators(manager))
        return FlowStation(
            name=self.name,
            meters=meters,
            regulators=regulators,
        )

    def on_config_change(self, config_state: ConfigurationState):
        """Update internal config if the configuration state changes."""
        flow_station_config = config_state.flow_station
        self.set_config(flow_station_config)


class DownstreamStationFactory(typing.Generic[PipelineT]):
    """Factory to create a downstream flow station."""

    def __init__(self, name: str, config: FlowStationConfig) -> None:
        """
        Initialize the downstream flow station.

        :param name: Name of the flow station
        :param config: `FlowStationConfig` object containing all meter configurations
        """
        self.name = name
        self.config = config

    def set_config(self, config: FlowStationConfig) -> None:
        """Update the factory configuration."""
        self.config = config

    def build_meters(self, manager: "PipelineManager[PipelineT]") -> typing.List[Meter]:
        """Create meters for the downstream station using configured parameters."""
        cfg = self.config
        pipeline = manager.get_pipeline()
        pressure_gauge = PressureGauge(
            value=pipeline.downstream_pressure.to(cfg.pressure_unit).magnitude,
            min_value=cfg.pressure_guage.min_value,
            max_value=cfg.pressure_guage.max_value,
            units=cfg.pressure_guage.units,
            label=cfg.pressure_guage.label,
            width=cfg.pressure_guage.width,
            height=cfg.pressure_guage.height,
            precision=cfg.pressure_guage.precision,
            alarm_high=cfg.pressure_guage.alarm_high,
            alarm_low=cfg.pressure_guage.alarm_low,
            animation_speed=cfg.pressure_guage.animation_speed,
            animation_interval=cfg.pressure_guage.animation_interval,
            update_func=lambda: pipeline.downstream_pressure.to(
                cfg.pressure_unit
            ).magnitude,
            update_interval=cfg.pressure_guage.update_interval,
        )
        temperature_gauge = TemperatureGauge(
            value=pipeline.fluid.temperature.to(cfg.temperature_unit).magnitude
            if pipeline.fluid
            else 0,
            min_value=cfg.temperature_guage.min_value,
            max_value=cfg.temperature_guage.max_value,
            units=cfg.temperature_guage.units,
            label=cfg.temperature_guage.label,
            width=cfg.temperature_guage.width,
            height=cfg.temperature_guage.height,
            precision=cfg.temperature_guage.precision,
            alarm_high=cfg.temperature_guage.alarm_high,
            alarm_low=cfg.temperature_guage.alarm_low,
            animation_speed=cfg.temperature_guage.animation_speed,
            animation_interval=cfg.temperature_guage.animation_interval,
            update_func=lambda: pipeline.fluid.temperature.to(
                cfg.temperature_unit
            ).magnitude
            if pipeline.fluid
            else 0,
            update_interval=cfg.temperature_guage.update_interval,
        )
        flow_meter = FlowMeter(
            value=pipeline.outlet_flow_rate.to(cfg.flow_unit).magnitude,
            min_value=cfg.flow_meter.min_value,
            max_value=max(
                cfg.flow_meter.max_value,
                pipeline.max_flow_rate.to(cfg.flow_unit).magnitude,
            ),
            units=cfg.flow_meter.units,
            label=cfg.flow_meter.label,
            width=cfg.flow_meter.width,
            height=cfg.flow_meter.height,
            precision=cfg.flow_meter.precision,
            alarm_high=cfg.flow_meter.alarm_high,
            alarm_low=cfg.flow_meter.alarm_low,
            animation_speed=cfg.flow_meter.animation_speed,
            animation_interval=cfg.flow_meter.animation_interval,
            flow_direction=str(pipeline.pipes[-1].direction)
            if pipeline.pipes
            else "east",  # type: ignore
            update_func=lambda: pipeline.outlet_flow_rate.to(cfg.flow_unit).magnitude,
            update_interval=cfg.flow_meter.update_interval,
        )
        return [pressure_gauge, temperature_gauge, flow_meter]

    def build_regulators(
        self, manager: "PipelineManager[PipelineT]"
    ) -> typing.Iterable[Regulator]:
        """Downstream stations typically just have pressure regulators."""
        cfg = self.config
        pipeline = manager.get_pipeline()

        def set_pressure(value: float):
            pipeline.set_downstream_pressure(
                Quantity(value, cfg.pressure_unit), sync=True
            ).update_viz()
            manager.sync()

        pressure_regulator = Regulator(
            value=pipeline.downstream_pressure.to(cfg.pressure_unit).magnitude,
            min_value=cfg.pressure_regulator.min_value,
            max_value=cfg.pressure_regulator.max_value,
            units=cfg.pressure_regulator.units,
            label=cfg.pressure_regulator.label,
            width=cfg.pressure_regulator.width,
            height=cfg.pressure_regulator.height,
            precision=cfg.pressure_regulator.precision,
            alarm_high=cfg.pressure_regulator.alarm_high,
            alarm_low=cfg.pressure_regulator.alarm_low,
            setter_func=set_pressure,
        )
        return [pressure_regulator]

    def __call__(self, manager: "PipelineManager[PipelineT]") -> FlowStation:
        """Build the downstream flow station."""
        meters = list(self.build_meters(manager))
        regulators = list(self.build_regulators(manager))
        return FlowStation(
            name=self.name,
            meters=meters,
            regulators=regulators,
        )

    def on_config_change(self, config_state: ConfigurationState):
        """Update internal config if the configuration state changes."""
        flow_station_config = config_state.flow_station
        self.set_config(flow_station_config)


class PipelineManager(typing.Generic[PipelineT]):
    """Manages a Pipeline instance."""

    def __init__(
        self,
        pipeline: PipelineT,
        validators: typing.Optional[typing.Sequence[PipeConfigValidator]] = None,
        flow_station_factories: typing.Optional[
            typing.Sequence[FlowStationFactory]
        ] = None,
    ) -> None:
        """
        Initialize the pipeline manager.

        :param pipeline: The Pipeline instance to manage.
        :param validator: Function to validate the pipeline configurations.
        """
        self._pipeline = pipeline
        self._pipe_configs: typing.List[PipeConfig] = []
        self._fluid_config = FluidConfig()
        self._validators = validators or [validate_pipe_configs]
        self._flow_station_factories = flow_station_factories or []
        self._observers: typing.List[PipelineObserver] = []
        self._errors: typing.List[str] = []
        self.sync()

    def sync(self):
        """
        Synchronize pipe and fluid configs from the current pipeline state.
        This ensures that the internal representation matches the actual Pipeline instance.

        Called internally after any modification to the pipeline.
        """
        self._pipe_configs = []

        if self._pipeline.fluid:
            self._fluid_config = FluidConfig(
                name=self._pipeline.fluid.name,
                phase=self._pipeline.fluid.phase,
                temperature=self._pipeline.fluid.temperature,  # type: ignore
                pressure=self._pipeline.upstream_pressure,  # type: ignore
                molecular_weight=self._pipeline.fluid.molecular_weight,  # type: ignore
            )

        for i, pipe in enumerate(self._pipeline):
            pipe_config = PipeConfig(
                name=pipe.name or f"Pipe-{i + 1}",
                length=pipe.length,  # type: ignore
                internal_diameter=pipe.internal_diameter,  # type: ignore
                upstream_pressure=pipe.upstream_pressure,  # type: ignore
                downstream_pressure=pipe.downstream_pressure,  # type: ignore
                material=pipe.material,
                roughness=pipe.roughness,  # type: ignore
                efficiency=pipe.efficiency,
                elevation_difference=pipe.elevation_difference,  # type: ignore
                direction=pipe.direction,
                scale_factor=pipe.scale_factor,
                max_flow_rate=pipe.max_flow_rate,  # type: ignore
                flow_type=pipe.flow_type,  # type: ignore
            )
            self._pipe_configs.append(pipe_config)
        return self

    def add_observer(self, observer: PipelineObserver):
        """Add an observer for pipeline events."""
        if observer not in self._observers:
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
                logger.error(f"Error notifying pipeline observer: {e}", exc_info=True)

    def on_config_change(self, config_state: ConfigurationState) -> None:
        """Updates the pipeline based on configuration changes."""
        pipeline_config = config_state.pipeline
        self._pipeline.name = pipeline_config.name
        self._pipeline.alert_errors = pipeline_config.alert_errors
        self._pipeline.set_flow_type(FlowType(pipeline_config.flow_type), sync=False)
        self._pipeline.set_max_flow_rate(
            pipeline_config.max_flow_rate, update_viz=False
        )
        self._pipeline.set_scale_factor(pipeline_config.scale_factor, update_viz=False)
        self._pipeline.set_connector_length(
            pipeline_config.connector_length, sync=False
        )
        # Update the visualization after all changes
        self._pipeline.sync().update_viz()
        self.sync()
        self.validate()
        self.notify_observers(
            PipelineEvent.PROPERTIES_UPDATED, {"pipeline_config": pipeline_config}
        )

    def build_fluid(self, fluid_config: FluidConfig) -> Fluid:
        """Build a Fluid instance from the current fluid config."""
        return Fluid.from_coolprop(
            fluid_name=fluid_config.name,
            phase=fluid_config.phase,
            temperature=fluid_config.temperature,
            pressure=fluid_config.pressure,
            molecular_weight=fluid_config.molecular_weight,
        )

    def build_pipe(
        self, pipe_config: PipeConfig, fluid: typing.Optional[Fluid] = None
    ) -> Pipe:
        """Build a Pipe instance from a pipe config."""
        return Pipe(
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

    def add_pipe(
        self, pipe_config: PipeConfig, index: typing.Optional[int] = None
    ) -> "PipelineManager":
        """Add a pipe at the specified index (or at the end)."""
        if index is None:
            index = len(self._pipe_configs)

        pipe = self.build_pipe(pipe_config)
        self._pipeline.add_pipe(pipe, index, sync=True)

        self.sync()
        self.validate()
        self.notify_observers(
            PipelineEvent.PIPE_ADDED, {"pipe_config": pipe_config, "index": index}
        )
        logger.info(f"Added pipe '{pipe_config.name}' at index {index}")
        return self

    def remove_pipe(self, index: int) -> "PipelineManager":
        """Remove a pipe at the specified index."""
        if len(self._pipe_configs) <= 1:
            raise ValueError("Pipeline must contain at least one pipe")

        if 0 <= index < len(self._pipe_configs):
            # Remove from pipeline using its remove_pipe method
            self._pipeline.remove_pipe(index, sync=True)

            self.sync()
            self.validate()
            self.notify_observers(
                PipelineEvent.PIPE_REMOVED,
                {"index": index},
            )
            logger.info(f"Removed pipe from index {index}")
        return self

    def move_pipe(self, from_index: int, to_index: int) -> "PipelineManager[PipelineT]":
        """Move a pipe from one position to another."""
        if len(self._pipe_configs) < 3:
            # Do not move pipes when the number of pipes is less than 3, because the
            # upstream and downstream pressure will become invalid and unphysical
            raise ValueError("Cannot move pipes when number of pipes is less than 3")

        if 0 <= from_index < len(self._pipe_configs) and 0 <= to_index < len(
            self._pipe_configs
        ):
            # Remove and re-add the pipe
            pipe_config = self._pipe_configs[from_index]
            removed = False
            try:
                self._pipeline.remove_pipe(from_index, sync=True)
                removed = True
                # Build a new pipe and add it at new position
                pipe = self.build_pipe(pipe_config)
                self._pipeline.add_pipe(pipe, to_index, sync=True)
            except Exception:
                if removed:
                    pipe = self.build_pipe(pipe_config)
                    self._pipeline.add_pipe(pipe, from_index, sync=True)
                raise

            self.sync()
            self.validate()
            self.notify_observers(
                PipelineEvent.PIPE_MOVED,
                {"from_index": from_index, "to_index": to_index},
            )
            logger.info(f"Moved pipe from index {from_index} to {to_index}")
        return self

    def update_pipe(
        self, index: int, pipe_config: PipeConfig
    ) -> "PipelineManager[PipelineT]":
        """Update a pipe configuration at the specified index."""
        if 0 <= index < len(self._pipe_configs):
            # Remove old pipe and add updated one
            self._pipeline.remove_pipe(index, sync=True)

            # Create new pipe with updated config
            pipe = self.build_pipe(pipe_config)
            self._pipeline.add_pipe(pipe, index, sync=True)

            self.sync()
            self.validate()
            self.notify_observers(
                PipelineEvent.PROPERTIES_UPDATED,
                {"pipe_config": pipe_config, "index": index},
            )
            logger.info(f"Updated pipe at index {index}")
        return self

    def set_fluid_config(
        self, fluid_config: FluidConfig
    ) -> "PipelineManager[PipelineT]":
        """Set the fluid configuration."""
        try:
            fluid = self.build_fluid(self._fluid_config)
            self._pipeline.set_fluid(fluid, sync=True)
        except Exception as e:
            logger.error(f"Error updating pipeline fluid: {e}")

        # Sync to update internal fluid config state from pipeline
        self.sync()
        self.validate()
        self.notify_observers(
            PipelineEvent.PROPERTIES_UPDATED, {"fluid_config": fluid_config}
        )
        logger.info(f"Updated fluid configuration: {fluid_config.name}")
        return self

    def validate(self):
        """Validate the current pipeline configuration."""
        errors = []
        for validator in self._validators:
            try:
                validation_errors = validator(self._pipe_configs)
                errors.extend(validation_errors)
            except Exception as e:
                logger.error(f"Error during validation: {e}")
        self._errors = errors
        self.notify_observers(PipelineEvent.VALIDATION_CHANGED, {"errors": errors})

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
        return self._fluid_config

    def get_pipeline(self) -> PipelineT:
        """Get the managed pipeline instance."""
        return self._pipeline

    def build_flow_stations(self) -> typing.List[FlowStation]:
        """Build flow stations using the registered factories."""
        flow_stations = []
        for factory in self._flow_station_factories:
            try:
                station = factory(self)
                flow_stations.append(station)
            except Exception as e:
                logger.error(f"Error building flow station: {e}", exc_info=True)
        return flow_stations


class PipelineManagerUI(typing.Generic[PipelineT]):
    """Interactive UI for pipeline management with real-time updates."""

    def __init__(
        self,
        manager: PipelineManager[PipelineT],
        config: ConfigurationManager,
        theme_color: str = "blue",
        unit_system: typing.Union[
            typing.Literal["imperial", "si"], UnitSystem[QuantityUnitT]
        ] = "imperial",
    ) -> None:
        self.manager = manager
        self.manager.add_observer(self.on_pipeline_event)
        self.theme_color = theme_color
        if isinstance(unit_system, str):
            self.unit_system = IMPERIAL if unit_system == "imperial" else SI
        else:
            self.unit_system = unit_system

        self.config = config
        self.config_ui = ConfigurationUI(self.config, theme_color)
        self.config.add_observer(self.on_config_change)

        # UI components
        self.add_pipe_button = None
        self.config_menu_button = None
        self.main_container = None
        self.unit_controls_container = None
        self.pipes_container = None
        self.validation_container = None
        self.pipeline_preview = None
        self.flow_station_container = None
        self.properties_panel = None
        self.pipe_form_container = None
        self.fluid_form_container = None

        # Current state
        self.selected_pipe_index: typing.Optional[int] = None
        self.current_pipeline: typing.Optional[Pipeline] = None
        self.current_flow_stations: typing.Optional[typing.List[FlowStation]] = None

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
        if event == PipelineEvent.PIPE_ADDED:
            self.refresh_pipes_list()
            self.refresh_pipeline_preview()
            self.refresh_flow_stations()
        elif event == PipelineEvent.PIPE_REMOVED:
            self.refresh_pipes_list()
            self.refresh_pipeline_preview()
            self.refresh_flow_stations()
            if self.selected_pipe_index is not None and self.selected_pipe_index >= len(
                self.manager.get_pipe_configs()
            ):
                self.selected_pipe_index = None
                self.refresh_properties_panel()
        elif event == PipelineEvent.PIPE_MOVED:
            self.refresh_pipes_list()
            self.refresh_pipeline_preview()
            self.refresh_flow_stations()
        elif event == PipelineEvent.PROPERTIES_UPDATED:
            self.refresh_pipes_list()
            self.refresh_pipeline_preview()
            self.refresh_flow_stations()
        elif event == PipelineEvent.VALIDATION_CHANGED:
            self.refresh_validation_display()
            # Only refresh flow station if validation is now valid
            if self.manager.is_valid():
                self.refresh_flow_stations()

    def on_config_change(self, config_state: ConfigurationState):
        """Handle configuration changes and update UI accordingly."""
        # Update theme color if it changed
        new_theme_color = config_state.global_.theme_color
        if new_theme_color != self.theme_color:
            self.set_theme_color(new_theme_color)

        # Update unit system if it changed
        unit_system_name = config_state.global_.unit_system_name
        if unit_system_name == "imperial" and self.unit_system != IMPERIAL:
            self.unit_system = IMPERIAL
            logger.info("Unit system updated to Imperial")
        elif unit_system_name == "si" and self.unit_system != SI:
            self.unit_system = SI
            logger.info("Unit system updated to SI")
        elif unit_system_name not in ["imperial", "si"]:
            # Handle custom unit system
            custom_systems = config_state.global_.custom_unit_systems
            if unit_system_name in custom_systems:
                # TODO: Create custom unit system from configuration
                # This would need unit system creation logic based on custom_systems[unit_system_name]
                logger.info(f"Custom unit system '{unit_system_name}' selected")

        # Refresh UI components that depend on configuration
        self.refresh_unit_system_controls()
        self.refresh_properties_panel()
        self.refresh_pipes_list()
        self.refresh_flow_stations()

    def cleanup(self):
        """Clean up resources and remove observers."""
        try:
            # Remove observers to prevent memory leaks
            self.manager.remove_observer(self.on_pipeline_event)
            self.config.remove_observer(self.on_config_change)
            logger.info("Pipeline Manager UI cleaned up successfully")
        except Exception as e:
            logger.error(
                f"Error during Pipeline Manager UI cleanup: {e}", exc_info=True
            )

    def set_theme_color(self, color: str):
        """Set a new theme color and update UI elements."""
        self.theme_color = color
        self.config_ui.set_theme_color(color)
        self.update_button_themes()
        logger.info(f"Theme color updated to: {color}")

    def update_button_themes(self):
        """Update all button colors to match current theme."""
        # Update Add Pipe button
        if self.add_pipe_button is not None:
            self.add_pipe_button.props(f'color="{self.theme_color}"')

        # Update Config Menu button
        if self.config_menu_button is not None:
            self.config_menu_button.props(f'color="{self.theme_color}"')

    def show(
        self,
        min_width: str = "300px",
        max_width: str = "1200px",
        ui_label: str = "Pipeline Builder",
        pipeline_label: str = "Pipeline Preview",
        flow_station_label: str = "Flow Station - Meters & Regulators",
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
            header_row = ui.row().classes(
                "w-full items-center justify-between mb-2 sm:mb-4"
            )
            with header_row:
                if show_label:
                    ui.label(ui_label).classes(
                        "text-xl sm:text-2xl lg:text-3xl font-bold"
                    )
                else:
                    ui.space()  # Spacer when no label

                # Configuration menu button
                self.show_config_menu_button()

            # Unit system controls
            self.unit_controls_container = self.show_unit_system_controls()

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

        return self.main_container

    def show_config_menu_button(self):
        """Show configuration menu button with dropdown"""
        with ui.button_group():
            self.config_menu_button = (
                ui.button(
                    icon="more_vert",
                    on_click=lambda: self.config_ui.show(max_width="720px"),
                    color=self.theme_color,
                )
                .props("outline")
                .classes("text-sm p-1 sm:p-2")
                .tooltip("System Configuration")
            )

    def show_construction_panel(self):
        """Create the pipeline construction panel."""
        construction_card = ui.card().classes("w-full p-2 sm:p-4")
        with construction_card:
            ui.label("Pipeline Construction").classes(
                "text-lg sm:text-xl font-semibold mb-2 sm:mb-3"
            )

            # Add pipe button
            self.add_pipe_button = ui.button(
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
                    "w-full xl:w-1/2 gap-2 sm:gap-3 min-w-0 flex flex-col align-stretch"
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

    def show_preview_panel(self, pipeline_label: str = "Pipeline Preview"):
        """Create the pipeline preview panel."""
        preview_card = (
            ui.card()
            .classes("w-full p-2 sm:p-4")
            .style("max-height: 800px; overflow-y: auto;")
        )
        with preview_card:
            ui.label(pipeline_label).classes(
                "text-lg sm:text-xl font-semibold mb-2 sm:mb-3"
            )
            self.pipeline_preview = ui.column().classes("w-full overflow-x-auto")
        self.refresh_pipeline_preview()

    def show_flow_station_panel(
        self, flow_station_label: str = "Flow Station - Meters & Regulators"
    ):
        """Create the flow station panel."""
        flow_station_card = ui.card().classes("w-full p-2 sm:p-4")
        with flow_station_card:
            ui.label(flow_station_label).classes(
                "text-lg sm:text-xl font-semibold mb-2 sm:mb-3"
            )

            # Responsive flow station container with horizontal scroll
            self.flow_station_container = ui.column().classes("w-full overflow-x-auto")

        self.refresh_flow_stations()

    def refresh_pipes_list(self):
        """Refresh the pipes list display."""
        if self.pipes_container is None:
            return

        self.pipes_container.clear()
        with self.pipes_container:
            pipe_configs = self.manager.get_pipe_configs()
            pipe_count = len(pipe_configs)
            for i, pipe_config in enumerate(pipe_configs):
                pipe_row = ui.row().classes(
                    "w-full items-center gap-2 p-2 sm:p-3 border rounded-lg hover:shadow-md transition-shadow flex-wrap sm:flex-nowrap"
                )

                with pipe_row:
                    # Pipe info
                    pipe_info = ui.column().classes("flex-1 min-w-0")
                    with pipe_info:
                        ui.label(f"{pipe_config.name}").classes(
                            "font-medium text-sm sm:text-base truncate"
                        )

                        # Display length, diameter, pressures, and flow rates in current unit system
                        length_unit = self.unit_system["length"]
                        diameter_unit = self.unit_system["diameter"]
                        pressure_unit = self.unit_system["pressure"]
                        flow_unit = self.unit_system["flow_rate"]

                        length_val = pipe_config.length.to(length_unit.unit)
                        diameter_val = pipe_config.internal_diameter.to(
                            diameter_unit.unit
                        )
                        upstream_pressure_val = pipe_config.upstream_pressure.to(
                            pressure_unit.unit
                        )
                        downstream_pressure_val = pipe_config.downstream_pressure.to(
                            pressure_unit.unit
                        )

                        # Try to get flow rates if available (may require pipeline context)
                        flow_val = None
                        pipeline = self.manager.get_pipeline()
                        if pipeline and i < len(pipeline.pipes):
                            pipe = pipeline.pipes[i]
                            flow_val = pipe.flow_rate.to(flow_unit.unit)
                        flow_str = (
                            f"{flow_val.magnitude:.2f} {flow_unit}"
                            if flow_val is not None
                            else "N/A"
                        )

                        ui.label(
                            f"L: {length_val.magnitude:.2f} {length_unit}, "
                            f"D: {diameter_val.magnitude:.2f} {diameter_unit}, "
                            f"P₁: {upstream_pressure_val.magnitude:.2f} {pressure_unit}, "
                            f"P₂: {downstream_pressure_val.magnitude:.2f} {pressure_unit}, "
                            f"Flow: {flow_str}"
                        ).classes("text-xs sm:text-sm text-gray-600")

                    # Action buttons
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
                        ).props("disabled" if i == 0 or (pipe_count < 3) else "")
                        ui.button(
                            "↓",
                            on_click=partial(self.move_pipe_down, i),
                            color=self.theme_color,
                        ).classes(
                            self.get_secondary_button_classes(
                                "text-xs sm:text-sm px-2 py-1"
                            )
                        ).props(
                            "disabled"
                            if (i == pipe_count - 1) or (pipe_count < 3)
                            else ""
                        )
                        ui.button(
                            "✕", on_click=partial(self.remove_pipe, i), color="red"
                        ).classes(
                            self.get_danger_button_classes(
                                "text-xs sm:text-sm px-2 py-1"
                            )
                        ).props("disabled" if pipe_count <= 1 else "")

    def refresh_validation_display(self):
        """Refresh the validation display."""
        if self.validation_container is None:
            return

        self.validation_container.clear()
        with self.validation_container:
            errors = self.manager.get_errors()

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
        if self.fluid_form_container is None:
            return

        self.fluid_form_container.clear()
        # Always show fluid properties in the right container
        with self.fluid_form_container:
            self.show_fluid_properties_form()

        if self.pipe_form_container is None:
            return

        self.pipe_form_container.clear()
        # Show pipe properties in the left container if a pipe is selected
        with self.pipe_form_container:
            if self.selected_pipe_index is not None:
                pipe_configs = self.manager.get_pipe_configs()
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
                        "items-center justify-center gap-2 w-full h-24 sm:h-48"
                    )
                    with placeholder_column:
                        ui.icon("edit", size="2rem").classes("text-gray-400")
                        ui.label("Select a pipe to edit").classes(
                            "text-gray-500 text-center"
                        )
                        ui.label("Click 'Edit' button on any pipe").classes(
                            "text-xs text-gray-400 text-center"
                        )

    def refresh_pipeline_preview(self):
        """Refresh the pipeline preview."""
        if self.pipeline_preview is None:
            return

        self.pipeline_preview.clear()
        with self.pipeline_preview:
            if self.manager.is_valid():
                pipeline = self.manager.get_pipeline()
                self.current_pipeline = pipeline
                pipeline.show(height="80dvh")
            else:
                ui.label("Fix validation errors to see preview").classes(
                    "text-gray-500 italic"
                )

    def refresh_flow_stations(self):
        """Refresh the flow station display."""
        if self.flow_station_container is None:
            return

        self.flow_station_container.clear()
        with self.flow_station_container:
            if self.manager.is_valid() and self.manager.get_pipe_configs():
                flow_stations = self.manager.build_flow_stations()
                self.current_flow_stations = flow_stations
                if flow_stations:
                    for station in flow_stations:
                        station.show()
                else:
                    # Create a simple station if no factories are registered
                    ui.label("Flow stations will appear here when configured").classes(
                        "text-gray-500 italic text-center p-4"
                    )
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

            pipe_count = len(self.manager.get_pipe_configs())
            # Form inputs
            form_container = ui.column().classes("w-full gap-2 sm:gap-3")
            with form_container:
                name_input = ui.input(
                    "Pipe Name",
                    value=f"Pipe-{pipe_count + 1}",
                ).classes("w-full")

                # Dimensions row
                dimensions_row = ui.row().classes(
                    "w-full gap-2 flex-wrap sm:flex-nowrap"
                )
                with dimensions_row:
                    length_unit = self.unit_system["length"]
                    diameter_unit = self.unit_system["diameter"]

                    # Use configuration defaults if available, otherwise use unit system defaults
                    config_state = self.config.get_config()
                    pipe_config = config_state.pipeline.pipe

                    length_default = pipe_config.length.to(length_unit.unit).magnitude
                    diameter_default = pipe_config.internal_diameter.to(
                        diameter_unit.unit
                    ).magnitude

                    length_input = ui.number(
                        f"Length ({length_unit})",
                        value=length_default,
                        min=0.1,
                        step=0.1,
                    ).classes("flex-1 min-w-0")
                    diameter_input = ui.number(
                        f"Diameter ({diameter_unit})",
                        value=diameter_default,
                        min=0.1,
                        step=0.1,
                    ).classes("flex-1 min-w-0")

                # Only allow pipe pressure to be set if there are no pipes yet.
                # Pipe pressures will be managed by pipeline(flow equations) and flow stations
                pressure_unit = self.unit_system["pressure"]
                if pipe_count == 0:
                    # Pressure row
                    pressure_row = ui.row().classes(
                        "w-full gap-2 flex-wrap sm:flex-nowrap"
                    )
                    with pressure_row:
                        upstream_pressure_input = ui.number(
                            f"Upstream Pressure ({pressure_unit})",
                            value=pipe_config.upstream_pressure.to(
                                pressure_unit.unit
                            ).magnitude,
                            min=0,
                            step=1,
                        ).classes("flex-1 min-w-0")
                        downstream_pressure_input = ui.number(
                            f"Downstream Pressure ({pressure_unit})",
                            value=pipe_config.downstream_pressure.to(
                                pressure_unit.unit
                            ).magnitude,
                            min=0,
                            step=1,
                        ).classes("flex-1 min-w-0")
                else:
                    upstream_pressure_input = (
                        ui.number(
                            f"Upstream Pressure ({pressure_unit})",
                            value=pipe_config.upstream_pressure.to(
                                pressure_unit.unit
                            ).magnitude,
                            min=0,
                            step=1,
                        )
                        .classes("flex-1 min-w-0")
                        .props("hidden disabled")
                        .style("display: none;")
                    )
                    downstream_pressure_input = (
                        ui.number(
                            f"Downstream Pressure ({pressure_unit})",
                            value=pipe_config.downstream_pressure.to(
                                pressure_unit.unit
                            ).magnitude,
                            min=0,
                            step=1,
                        )
                        .classes("flex-1 min-w-0")
                        .props("hidden disabled")
                        .style("display: none;")
                    )

                # Material and direction row
                material_dir_row = ui.row().classes(
                    "w-full gap-2 flex-wrap sm:flex-nowrap"
                )
                with material_dir_row:
                    material_input = ui.input(
                        "Material", value=pipe_config.material
                    ).classes("flex-1 min-w-0")
                    direction_select = ui.select(
                        options=[d.value for d in PipeDirection],
                        value=PipeDirection.EAST.value,
                        label="Flow Direction",
                    ).classes("flex-1 min-w-0")

                # Roughness and elevation row
                roughness_elev_row = ui.row().classes(
                    "w-full gap-2 flex-wrap sm:flex-nowrap"
                )
                with roughness_elev_row:
                    roughness_unit = self.unit_system["roughness"]
                    elevation_unit = self.unit_system["elevation"]

                    roughness_input = ui.number(
                        f"Roughness ({roughness_unit})",
                        value=pipe_config.roughness.to(roughness_unit.unit).magnitude,
                        min=0.0001,
                        step=0.0001,
                    ).classes("flex-1 min-w-0")
                    elevation_input = ui.number(
                        f"Elevation Difference ({elevation_unit})",
                        value=pipe_config.elevation_difference.to(
                            elevation_unit.unit
                        ).magnitude,
                        step=0.1,
                    ).classes("flex-1 min-w-0")

                # Efficiency row
                efficiency_input = ui.number(
                    "Efficiency",
                    value=pipe_config.efficiency,
                    min=0.1,
                    max=1.0,
                    step=0.01,
                ).classes("w-full sm:w-48")

                # Position selection
                pipe_configs = self.manager.get_pipe_configs()
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
                            roughness_input,
                            elevation_input,
                            efficiency_input,
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
        roughness_input: ui.number,
        elevation_input: ui.number,
        efficiency_input: ui.number,
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
            length_unit = self.unit_system["length"].unit
            diameter_unit = self.unit_system["diameter"].unit
            pressure_unit = self.unit_system["pressure"].unit
            roughness_unit = self.unit_system["roughness"].unit
            elevation_unit = self.unit_system["elevation"].unit

            pipe_config = PipeConfig(
                name=name_input.value
                or f"Pipe-{len(self.manager.get_pipe_configs()) + 1}",
                length=Quantity(length_input.value, length_unit),  # type: ignore
                internal_diameter=Quantity(diameter_input.value, diameter_unit),  # type: ignore
                upstream_pressure=Quantity(
                    upstream_pressure_input.value,
                    pressure_unit,  # type: ignore
                ),
                downstream_pressure=Quantity(
                    downstream_pressure_input.value,
                    pressure_unit,  # type: ignore
                ),
                direction=PipeDirection(direction_select.value),
                material=material_input.value or "Steel",
                roughness=Quantity(roughness_input.value, roughness_unit),  # type: ignore
                elevation_difference=Quantity(elevation_input.value, elevation_unit),  # type: ignore
                efficiency=efficiency_input.value,
            )

            # Determine insertion index
            index = None
            if position_select.value != "End":
                # Extract pipe number from "Before Pipe X"
                pipe_num = int(position_select.value.split()[-1]) - 1  # type: ignore
                index = pipe_num

            self.manager.add_pipe(pipe_config, index)
            dialog.close()

        except Exception as e:
            logger.error(f"Error adding pipe: {e}", exc_info=True)
            ui.notify(f"Error adding pipe: {str(e)}", type="negative")

    def select_pipe(self, index: int):
        """Select a pipe for editing."""
        self.selected_pipe_index = index
        self.refresh_properties_panel()

    def move_pipe_up(self, index: int):
        """Move pipe up in the sequence."""
        if index > 0:
            self.manager.move_pipe(index, index - 1)
            if self.selected_pipe_index == index:
                self.selected_pipe_index = index - 1

    def move_pipe_down(self, index: int):
        """Move pipe down in the sequence."""
        pipe_configs = self.manager.get_pipe_configs()
        if index < len(pipe_configs) - 1:
            self.manager.move_pipe(index, index + 1)
            if self.selected_pipe_index == index:
                self.selected_pipe_index = index + 1

    def remove_pipe(self, index: int):
        """Remove a pipe from the pipeline."""
        try:
            self.manager.remove_pipe(index)
            if self.selected_pipe_index == index:
                self.selected_pipe_index = None
        except ValueError as e:
            ui.notify(str(e), type="warning")

    def show_pipe_properties_form(self, pipe_config: PipeConfig):
        """Create form for editing pipe properties."""
        pipe_header = ui.card().classes(
            f"w-full mb-3 bg-gradient-to-r from-{self.theme_color}-50 to-{self.theme_color}-100 border-l-4 border-{self.theme_color}-500"
        )
        with pipe_header:
            ui.label(f"Editing: {pipe_config.name}").classes(
                f"font-semibold text-{self.theme_color}-800 p-2"
            )

        form_container = ui.column().classes("w-full gap-2 sm:gap-3")
        with form_container:
            # Basic properties
            name_input = ui.input("Name", value=pipe_config.name).classes("w-full")

            # Dimensions row - side by side on larger screens
            dimensions_row = ui.row().classes("w-full gap-2 flex-wrap sm:flex-nowrap")
            with dimensions_row:
                length_unit = self.unit_system["length"]
                diameter_unit = self.unit_system["diameter"]

                length_input = ui.number(
                    f"Length ({length_unit})",
                    value=pipe_config.length.to(length_unit.unit).magnitude,
                    min=0.1,
                    step=0.1,
                    precision=4,
                ).classes("flex-1 min-w-0")
                diameter_input = ui.number(
                    f"Diameter ({diameter_unit})",
                    value=pipe_config.internal_diameter.to(
                        diameter_unit.unit
                    ).magnitude,
                    min=0.1,
                    step=0.1,
                    precision=4,
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

            # Roughness and elevation row
            roughness_elevation_row = ui.row().classes(
                "w-full gap-2 flex-wrap sm:flex-nowrap"
            )
            with roughness_elevation_row:
                roughness_unit = self.unit_system["roughness"]
                elevation_unit = self.unit_system["elevation"]

                roughness_input = ui.number(
                    f"Roughness ({roughness_unit})",
                    value=pipe_config.roughness.to(roughness_unit.unit).magnitude,
                    min=0,
                    step=0.0001,
                    precision=6,
                ).classes("flex-1 min-w-0")
                elevation_input = ui.number(
                    f"Elevation Difference ({elevation_unit})",
                    value=pipe_config.elevation_difference.to(
                        elevation_unit.unit
                    ).magnitude,
                    step=0.1,
                    precision=3,
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
                        direction_select,
                        material_input,
                        efficiency_input,
                        roughness_input,
                        elevation_input,
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

        fluid_config = self.manager.get_fluid_config()

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
                temp_unit = self.unit_system["temperature"]
                pressure_unit = self.unit_system["pressure"]

                temperature_input = ui.number(
                    f"Temperature ({temp_unit})",
                    value=fluid_config.temperature.to(temp_unit.unit).magnitude,
                    step=1,
                    precision=2,
                ).classes("flex-1 min-w-0")
                pressure_input = ui.number(
                    f"Pressure ({pressure_unit})",
                    value=fluid_config.pressure.to(pressure_unit.unit).magnitude,
                    min=0,
                    step=1,
                    precision=4,
                ).classes("flex-1 min-w-0")

            # Molecular weight and specific gravity row
            mol_gravity_row = ui.row().classes("w-full gap-2 flex-wrap sm:flex-nowrap")
            with mol_gravity_row:
                mol_weight_unit = self.unit_system["molecular_weight"]

                molecular_weight_input = ui.number(
                    f"Molecular Weight ({mol_weight_unit})",
                    value=fluid_config.molecular_weight.to(
                        mol_weight_unit.unit
                    ).magnitude,
                    min=0.1,
                    step=0.1,
                    precision=4,
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
        direction_select,
        material_input,
        efficiency_input,
        roughness_input,
        elevation_input,
    ):
        """Update pipe configuration from form inputs."""
        try:
            if self.selected_pipe_index is not None:
                selected_pipe_config = self.manager.get_pipe_configs()[
                    self.selected_pipe_index
                ]
                length_unit = self.unit_system["length"].unit
                diameter_unit = self.unit_system["diameter"].unit
                roughness_unit = self.unit_system["roughness"].unit
                elevation_unit = self.unit_system["elevation"].unit

                updated_config = PipeConfig(
                    name=name_input.value,
                    length=Quantity(length_input.value, length_unit),  # type: ignore
                    internal_diameter=Quantity(diameter_input.value, diameter_unit),  # type: ignore
                    # Pressures remain unchanged as they manage by the pipeline and flowstations
                    upstream_pressure=selected_pipe_config.upstream_pressure,
                    downstream_pressure=selected_pipe_config.downstream_pressure,
                    direction=PipeDirection(direction_select.value),
                    material=material_input.value,
                    roughness=Quantity(roughness_input.value, roughness_unit),  # type: ignore
                    elevation_difference=Quantity(
                        elevation_input.value, elevation_unit
                    ),  # type: ignore
                    efficiency=efficiency_input.value,
                )

                self.manager.update_pipe(self.selected_pipe_index, updated_config)
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
    ):
        """Update fluid configuration from form inputs."""
        try:
            temp_unit = self.unit_system["temperature"].unit
            pressure_unit = self.unit_system["pressure"].unit
            mol_weight_unit = self.unit_system["molecular_weight"].unit

            updated_config = FluidConfig(
                name=name_input.value,
                phase=phase_select.value,
                temperature=Quantity(temperature_input.value, temp_unit),  # type: ignore
                pressure=Quantity(pressure_input.value, pressure_unit),  # type: ignore
                molecular_weight=Quantity(
                    molecular_weight_input.value,
                    mol_weight_unit,  # type: ignore
                ),
            )
            self.manager.set_fluid_config(updated_config)
            ui.notify("Fluid properties updated successfully", type="positive")

        except Exception as e:
            logger.error(f"Error updating fluid: {e}")
            ui.notify(f"Error updating fluid: {str(e)}", type="negative")

    def clear_pipe_selection(self):
        """Clear pipe selection and return to fluid properties."""
        self.selected_pipe_index = None
        self.refresh_properties_panel()

    def show_unit_system_controls(self):
        """Create unit system selection controls."""
        unit_controls = ui.row().classes("gap-2 items-center mb-4 flex-wrap")

        with unit_controls:
            ui.label("Unit System:").classes("text-sm font-medium")

            def update_unit_system(system_name: str, custom_system=None):
                """Update the current unit system."""
                if custom_system:
                    self.unit_system = custom_system
                elif system_name == "imperial":
                    self.unit_system = IMPERIAL
                elif system_name == "si":
                    self.unit_system = SI

                # Refresh all UI components to reflect new units
                self.refresh_properties_panel()
                self.refresh_pipes_list()

                # Refresh unit system controls to update active state
                self.refresh_unit_system_controls()

                system_display_name = (
                    system_name.upper() if not custom_system else "Custom"
                )
                ui.notify(f"Switched to {system_display_name} unit system", type="info")

            # Imperial button - active styling with opacity
            imperial_is_active = self.unit_system == IMPERIAL
            imperial_button = ui.button(
                "Imperial",
                on_click=lambda: update_unit_system("imperial"),
                color=self.theme_color,
            ).classes(
                self.get_primary_button_classes("text-sm px-3 py-1")
                if imperial_is_active
                else self.get_secondary_button_classes(
                    "text-sm px-3 py-1 opacity-60 hover:opacity-100"
                )
            )

            # Add active indicator styling
            if imperial_is_active:
                imperial_button.classes("ring-2 ring-gray-300 shadow-lg")

            # SI button - active styling with opacity
            si_is_active = self.unit_system == SI
            si_button = ui.button(
                "SI", on_click=lambda: update_unit_system("si"), color=self.theme_color
            ).classes(
                self.get_primary_button_classes("text-sm px-3 py-1")
                if si_is_active
                else self.get_secondary_button_classes(
                    "text-sm px-3 py-1 opacity-60 hover:opacity-100"
                )
            )

            # Add active indicator styling
            if si_is_active:
                si_button.classes("ring-2 ring-gray-300 shadow-lg")

            # Custom button - check if current system is neither Imperial nor SI
            custom_is_active = self.unit_system not in [IMPERIAL, SI]
            custom_button = ui.button(
                "Custom",
                on_click=self.show_custom_unit_system_dialog,
                color=self.theme_color,
            ).classes(
                self.get_primary_button_classes("text-sm px-3 py-1")
                if custom_is_active
                else self.get_accent_button_classes(
                    "text-sm px-3 py-1 opacity-60 hover:opacity-100"
                )
            )

            # Add active indicator styling for custom
            if custom_is_active:
                custom_button.classes("ring-2 ring-green-300 shadow-lg")

        # Store reference for refreshing
        self.unit_controls_container = unit_controls
        return unit_controls

    def refresh_unit_system_controls(self):
        """Refresh the unit system controls to update active state."""
        if self.unit_controls_container is None:
            return

        self.unit_controls_container.clear()
        with self.unit_controls_container:
            # Recreate the controls without calling the full method to avoid recursion
            ui.label("Unit System:").classes("text-sm font-medium")

            def update_unit_system(system_name: str, custom_system=None):
                """Update the current unit system."""
                if custom_system:
                    self.unit_system = custom_system
                elif system_name == "imperial":
                    self.unit_system = IMPERIAL
                elif system_name == "si":
                    self.unit_system = SI

                # Refresh all UI components to reflect new units
                self.refresh_properties_panel()
                self.refresh_pipes_list()

                # Refresh unit system controls to update active state
                self.refresh_unit_system_controls()

                system_display_name = (
                    system_name.upper() if not custom_system else "Custom"
                )
                ui.notify(f"Switched to {system_display_name} unit system", type="info")

            # Imperial button - active styling with opacity
            imperial_is_active = self.unit_system == IMPERIAL
            imperial_button = ui.button(
                "Imperial",
                on_click=lambda: update_unit_system("imperial"),
                color=self.theme_color,
            ).classes(
                self.get_primary_button_classes("text-sm px-3 py-1")
                if imperial_is_active
                else self.get_secondary_button_classes(
                    "text-sm px-3 py-1 opacity-60 hover:opacity-100"
                )
            )

            if imperial_is_active:
                imperial_button.classes("ring-2 ring-gray-300 shadow-lg")

            # SI button - active styling with opacity
            si_is_active = self.unit_system == SI
            si_button = ui.button(
                "SI",
                on_click=lambda: update_unit_system("si"),
                color=self.theme_color,
            ).classes(
                self.get_primary_button_classes("text-sm px-3 py-1")
                if si_is_active
                else self.get_secondary_button_classes(
                    "text-sm px-3 py-1 opacity-60 hover:opacity-100"
                )
            )

            if si_is_active:
                si_button.classes("ring-2 ring-gray-300 shadow-lg")

            # Custom button
            custom_is_active = self.unit_system not in [IMPERIAL, SI]
            custom_button = ui.button(
                "Custom",
                on_click=self.show_custom_unit_system_dialog,
                color=self.theme_color,
            ).classes(
                self.get_primary_button_classes("text-sm px-3 py-1")
                if custom_is_active
                else self.get_accent_button_classes(
                    "text-sm px-3 py-1 opacity-60 hover:opacity-100"
                )
            )

            if custom_is_active:
                custom_button.classes("ring-2 ring-green-300 shadow-lg")

    def show_custom_unit_system_dialog(self):
        """Show dialog to create a custom unit system."""
        with (
            ui.dialog() as dialog,
            ui.card().classes("w-full max-w-2xl mx-2 p-4"),
        ):
            ui.label("Create Custom Unit System").classes("text-xl font-semibold mb-4")

            # Form for custom unit system
            form_container = ui.column().classes("w-full gap-4")

            with form_container:
                ui.label("Configure units for different quantities:").classes(
                    "text-sm text-gray-600 mb-2"
                )

                # Preset systems for quick selection
                ui.label("Quick Presets:").classes("font-medium text-sm mb-2")
                preset_row = ui.row().classes("w-full gap-2 mb-4 flex-wrap")

                def apply_preset(preset_name):
                    """Apply a preset unit system configuration."""
                    presets = {
                        "oil_gas": {
                            "length": ("ft", None),
                            "diameter": ("in", None),
                            "pressure": ("psi", None),
                            "temperature": ("°R", 520.0),
                            "flow_rate": ("bbl/day", None),
                            "molecular_weight": ("g/mol", 16.04),
                        },
                        "metric_industrial": {
                            "length": ("m", None),
                            "diameter": ("mm", None),
                            "pressure": ("kPa", None),
                            "temperature": ("°C", 25.0),
                            "flow_rate": ("L/min", None),
                            "molecular_weight": ("g/mol", 16.04),
                        },
                        "laboratory": {
                            "length": ("cm", None),
                            "diameter": ("mm", None),
                            "pressure": ("atm", 1.0),
                            "temperature": ("K", 298.15),
                            "flow_rate": ("mL/min", None),
                            "molecular_weight": ("g/mol", None),
                        },
                    }

                    if preset_name in presets:
                        preset = presets[preset_name]
                        for qty_key, (unit, default_val) in preset.items():
                            if qty_key in quantity_inputs:
                                quantity_inputs[qty_key]["unit"].value = unit
                                quantity_inputs[qty_key]["default"].value = default_val

                with preset_row:
                    ui.button(
                        "Oil & Gas", on_click=lambda: apply_preset("oil_gas")
                    ).classes(self.get_secondary_button_classes("text-xs px-2 py-1"))
                    ui.button(
                        "Metric Industrial",
                        on_click=lambda: apply_preset("metric_industrial"),
                    ).classes(self.get_secondary_button_classes("text-xs px-2 py-1"))
                    ui.button(
                        "Laboratory", on_click=lambda: apply_preset("laboratory")
                    ).classes(self.get_secondary_button_classes("text-xs px-2 py-1"))

                # Create inputs for common quantities
                quantity_inputs = {}
                quantities = [
                    ("length", "Length", ["ft", "m", "cm", "mm", "in"]),
                    ("diameter", "Diameter", ["in", "mm", "cm", "ft"]),
                    ("pressure", "Pressure", ["psi", "Pa", "kPa", "bar", "atm"]),
                    ("temperature", "Temperature", ["°F", "°C", "K", "°R"]),
                    (
                        "flow_rate",
                        "Flow Rate",
                        [
                            "ft³/s",
                            "m³/s",
                            "gpm",
                            "L/min",
                            "bbl/day",
                            "mL/min",
                            "scf/day",
                            "Mscf/day",
                            "MMscf/day",
                            "m³/day",
                            "m³/hr",
                        ],
                    ),
                    ("molecular_weight", "Molecular Weight", ["g/mol", "kg/mol"]),
                ]

                # Create a responsive grid for quantity inputs
                grid = ui.grid(columns=2).classes("w-full gap-4")

                with grid:
                    for qty_key, qty_label, unit_options in quantities:
                        with ui.column().classes("gap-2"):
                            ui.label(qty_label).classes("font-medium text-sm")

                            # Unit selection
                            unit_select = ui.select(
                                options=unit_options,
                                value=unit_options[0],
                                label="Unit",
                            ).classes("w-full")

                            # Default value (optional)
                            default_input = ui.number(
                                "Default Value (optional)", value=None, step=0.1
                            ).classes("w-full")

                            quantity_inputs[qty_key] = {
                                "unit": unit_select,
                                "default": default_input,
                            }

                # System name
                system_name_input = ui.input(
                    "System Name (optional)", placeholder="e.g., Oil & Gas Units"
                ).classes("w-full mt-4")

                # Buttons
                button_row = ui.row().classes("w-full justify-end gap-2 mt-6")
                with button_row:
                    ui.button("Cancel", on_click=dialog.close).classes(
                        self.get_secondary_button_classes("px-4 py-2")
                    )

                    def create_custom_system():
                        """Create and apply the custom unit system."""
                        try:
                            custom_system = UnitSystem()

                            # Convert unit display strings to actual units for Pint
                            unit_mapping = {
                                "°F": "degF",
                                "°C": "degC",
                                "K": "kelvin",
                                "°R": "degR",
                                "ft³/s": "ft^3/s",
                                "m³/s": "m^3/s",
                                "gpm": "gallon/minute",
                                "L/min": "liter/minute",
                                "bbl/day": "barrel/day",
                                "mL/min": "milliliter/minute",
                            }

                            for qty_key, inputs in quantity_inputs.items():
                                unit_display = inputs["unit"].value
                                unit_str = unit_mapping.get(unit_display, unit_display)
                                default_val = inputs["default"].value

                                # Ensure unit_str is not None
                                if unit_str is None:
                                    unit_str = "dimensionless"

                                custom_system[qty_key] = QuantityUnit(
                                    unit=unit_str,
                                    display=unit_display,
                                    default=default_val,
                                )

                            # Apply the custom system
                            self.unit_system = custom_system

                            # Refresh UI
                            self.refresh_properties_panel()
                            self.refresh_pipes_list()
                            self.refresh_unit_system_controls()

                            system_name = system_name_input.value or "Custom"
                            ui.notify(
                                f"Applied {system_name} unit system", type="positive"
                            )
                            dialog.close()

                        except Exception as e:
                            logger.error(f"Error creating custom unit system: {e}")
                            ui.notify(f"Error: {str(e)}", type="negative")

                    ui.button(
                        "Apply Custom System",
                        on_click=create_custom_system,
                        color=self.theme_color,
                    ).classes(self.get_primary_button_classes("px-4 py-2"))

        dialog.open()

    def __del__(self):
        """Cleanup when the UI is destroyed."""
        self.cleanup()
