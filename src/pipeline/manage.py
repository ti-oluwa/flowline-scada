"""
Pipeline Management UI
"""

import datetime
from functools import partial
import logging
import typing

import attrs
from nicegui import ui
import orjson
from typing_extensions import Self

from src.config.core import Configuration, ConfigurationState
from src.config.ui import ConfigurationUI
from src.flow import Fluid, SUPPORTED_FLUIDS
from src.pipeline.core import (
    FlowMeter,
    FlowStation,
    MassFlowMeter,
    Meter,
    Pipe,
    PipeLeak,
    Pipeline,
    PressureGauge,
    Regulator,
    TemperatureGauge,
    Valve,
    ValveState,
)
from src.pipeline.ui import PipeDirection
from src.types import (
    EventCallback,
    EventSubscription,
    FlowStationConfig,
    FlowType,
    FluidConfig,
    PipeConfig,
    PipeLeakConfig,
    ValveConfig,
    converter,
    structure_quantity,
    unstructure_quantity,
)
from src.units import Quantity, UnitSystem

logger = logging.getLogger(__name__)

__all__ = [
    "PipelineManager",
    "PipelineManagerUI",
    "UpstreamStationFactory",
    "DownstreamStationFactory",
    "validate_pipe_configs",
]


PipelineT = typing.TypeVar("PipelineT", bound=Pipeline)
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
        unit_system = manager.config.get_unit_system()
        theme_color = manager.config.state.global_.theme_color
        pressure_unit = unit_system["pressure"]
        temperature_unit = unit_system["temperature"]
        flow_unit = unit_system["flow_rate"]

        pressure_gauge = PressureGauge(
            value=pipeline.upstream_pressure.to(pressure_unit.unit).magnitude,
            min_value=cfg.pressure_guage.min_value,
            max_value=cfg.pressure_guage.max_value,
            units=pressure_unit.display,
            label=cfg.pressure_guage.label,
            width=cfg.pressure_guage.width,
            height=cfg.pressure_guage.height,
            precision=cfg.pressure_guage.precision,
            alarm_high=cfg.pressure_guage.alarm_high,
            alarm_low=cfg.pressure_guage.alarm_low,
            animation_speed=cfg.pressure_guage.animation_speed,
            animation_interval=cfg.pressure_guage.animation_interval,
            update_func=lambda: pipeline.upstream_pressure.to(
                pressure_unit.unit
            ).magnitude,
            update_interval=cfg.pressure_guage.update_interval,
            theme_color=theme_color,
            help_text="""
            The pressure at the inlet of the pipeline.
            """,
        )
        temperature_gauge = TemperatureGauge(
            value=pipeline.fluid.temperature.to(temperature_unit.unit).magnitude
            if pipeline.fluid
            else 0,
            min_value=cfg.temperature_guage.min_value,
            max_value=cfg.temperature_guage.max_value,
            units=temperature_unit.display,
            label=cfg.temperature_guage.label,
            width=cfg.temperature_guage.width,
            height=cfg.temperature_guage.height,
            precision=cfg.temperature_guage.precision,
            alarm_high=cfg.temperature_guage.alarm_high,
            alarm_low=cfg.temperature_guage.alarm_low,
            animation_speed=cfg.temperature_guage.animation_speed,
            animation_interval=cfg.temperature_guage.animation_interval,
            update_func=lambda: pipeline.fluid.temperature.to(
                temperature_unit.unit
            ).magnitude
            if pipeline.fluid
            else 0,
            update_interval=cfg.temperature_guage.update_interval,
            theme_color=theme_color,
            help_text="""
            The temperature of the fluid entering the pipeline.
            """,
        )
        flow_meter = FlowMeter(
            value=pipeline.inlet_flow_rate.to(flow_unit.unit).magnitude,
            min_value=cfg.flow_meter.min_value,
            max_value=max(
                cfg.flow_meter.max_value,
                pipeline.max_flow_rate.to(flow_unit.unit).magnitude,
            ),
            units=flow_unit.display,
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
            update_func=lambda: pipeline.inlet_flow_rate.to(flow_unit.unit).magnitude,
            update_interval=cfg.flow_meter.update_interval,
            theme_color=theme_color,
            help_text="""
            The volumetric flow rate entering the pipeline.
            """,
        )
        return [pressure_gauge, temperature_gauge, flow_meter]

    def build_regulators(
        self, manager: "PipelineManager[PipelineT]"
    ) -> typing.Iterable[Regulator]:
        """Create regulators for the upstream station."""
        cfg = self.config
        pipeline = manager.get_pipeline()
        unit_system = manager.config.get_unit_system()
        theme_color = manager.config.state.global_.theme_color
        pressure_unit = unit_system["pressure"]
        temperature_unit = unit_system["temperature"]

        def _set_pressure(value: float):
            manager.set_upstream_pressure(Quantity(value, pressure_unit.unit))

        def _set_temperature(value: float):
            manager.set_upstream_temperature(Quantity(value, temperature_unit.unit))

        pressure_regulator = Regulator(
            value=pipeline.upstream_pressure.to(pressure_unit.unit).magnitude,
            min_value=cfg.pressure_regulator.min_value,
            max_value=cfg.pressure_regulator.max_value,
            step=cfg.pressure_regulator.step,
            units=pressure_unit.display,
            label=cfg.pressure_regulator.label,
            width=cfg.pressure_regulator.width,
            height=cfg.pressure_regulator.height,
            precision=cfg.pressure_regulator.precision,
            setter_func=_set_pressure,
            alarm_high=cfg.pressure_regulator.alarm_high,
            alarm_low=cfg.pressure_regulator.alarm_low,
            alert_errors=cfg.pressure_regulator.alert_errors,
            theme_color=theme_color,
            help_text="""
            Set the upstream pressure. Note that changing the upstream pressure may affect the flow rate through the pipeline.
            """,
        )
        temperature_regulator = Regulator(
            value=pipeline.fluid.temperature.to(temperature_unit.unit).magnitude
            if pipeline.fluid
            else 0,
            min_value=cfg.temperature_regulator.min_value,
            max_value=cfg.temperature_regulator.max_value,
            step=cfg.temperature_regulator.step,
            units=temperature_unit.display,
            label=cfg.temperature_regulator.label,
            width=cfg.temperature_regulator.width,
            height=cfg.temperature_regulator.height,
            precision=cfg.temperature_regulator.precision,
            setter_func=_set_temperature,
            alarm_high=cfg.temperature_regulator.alarm_high,
            alarm_low=cfg.temperature_regulator.alarm_low,
            alert_errors=cfg.temperature_regulator.alert_errors,
            theme_color=theme_color,
            help_text="""
            Set the fluid temperature. Note that changing the temperature may affect the fluid properties and flow characteristics.
            """,
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
        if flow_station_config is self.config:
            return
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
        unit_system = manager.config.get_unit_system()
        theme_color = manager.config.state.global_.theme_color
        pressure_unit = unit_system["pressure"]
        temperature_unit = unit_system["temperature"]
        flow_unit = unit_system["flow_rate"]
        mass_flow_unit = unit_system["mass_flow_rate"]

        pressure_gauge = PressureGauge(
            value=pipeline.downstream_pressure.to(pressure_unit.unit).magnitude,
            min_value=cfg.pressure_guage.min_value,
            max_value=cfg.pressure_guage.max_value,
            units=pressure_unit.display,
            label=cfg.pressure_guage.label,
            width=cfg.pressure_guage.width,
            height=cfg.pressure_guage.height,
            precision=cfg.pressure_guage.precision,
            alarm_high=cfg.pressure_guage.alarm_high,
            alarm_low=cfg.pressure_guage.alarm_low,
            animation_speed=cfg.pressure_guage.animation_speed,
            animation_interval=cfg.pressure_guage.animation_interval,
            update_func=lambda: pipeline.downstream_pressure.to(
                pressure_unit.unit
            ).magnitude,
            update_interval=cfg.pressure_guage.update_interval,
            theme_color=theme_color,
            help_text="""
            The pressure at the outlet of the pipeline.
            """,
        )
        temperature_gauge = TemperatureGauge(
            value=pipeline.fluid.temperature.to(temperature_unit.unit).magnitude
            if pipeline.fluid
            else 0,
            min_value=cfg.temperature_guage.min_value,
            max_value=cfg.temperature_guage.max_value,
            units=temperature_unit.display,
            label=cfg.temperature_guage.label,
            width=cfg.temperature_guage.width,
            height=cfg.temperature_guage.height,
            precision=cfg.temperature_guage.precision,
            alarm_high=cfg.temperature_guage.alarm_high,
            alarm_low=cfg.temperature_guage.alarm_low,
            animation_speed=cfg.temperature_guage.animation_speed,
            animation_interval=cfg.temperature_guage.animation_interval,
            update_func=lambda: pipeline.fluid.temperature.to(
                temperature_unit.unit
            ).magnitude
            if pipeline.fluid
            else 0,
            update_interval=cfg.temperature_guage.update_interval,
            theme_color=theme_color,
            help_text="""
            The temperature of the fluid exiting the pipeline.
            """,
        )
        flow_meter = FlowMeter(
            value=pipeline.outlet_flow_rate.to(flow_unit.unit).magnitude,
            min_value=cfg.flow_meter.min_value,
            max_value=max(
                cfg.flow_meter.max_value,
                pipeline.max_flow_rate.to(flow_unit.unit).magnitude,
            ),
            units=flow_unit.display,
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
            update_func=lambda: pipeline.outlet_flow_rate.to(flow_unit.unit).magnitude,
            update_interval=cfg.flow_meter.update_interval,
            theme_color=theme_color,
            help_text="""
            The volumetric rate of the fluid exiting the pipeline.
            """,
        )
        mass_flow_meter = MassFlowMeter(
            value=pipeline.outlet_mass_rate.to(mass_flow_unit.unit).magnitude,
            min_value=cfg.mass_flow_meter.min_value,
            max_value=cfg.mass_flow_meter.max_value,
            units=mass_flow_unit.display,
            label=cfg.mass_flow_meter.label,
            width=cfg.mass_flow_meter.width,
            height=cfg.mass_flow_meter.height,
            precision=cfg.mass_flow_meter.precision,
            alarm_high=cfg.mass_flow_meter.alarm_high,
            alarm_low=cfg.mass_flow_meter.alarm_low,
            animation_speed=cfg.mass_flow_meter.animation_speed,
            animation_interval=cfg.mass_flow_meter.animation_interval,
            flow_direction=str(pipeline.pipes[0].direction)
            if pipeline.pipes
            else "east",  # type: ignore
            update_func=lambda: pipeline.outlet_mass_rate.to(
                mass_flow_unit.unit
            ).magnitude,
            update_interval=cfg.mass_flow_meter.update_interval,
            theme_color=theme_color,
            help_text="""
            The mass flow rate of the fluid exiting the pipeline.
            """,
        )
        meters = [pressure_gauge, temperature_gauge, flow_meter, mass_flow_meter]

        # If pipeline has leaks, the meters above will show the flow properties with the leak losses
        # But we also want to show the expected flow properties assuming no leaks
        if pipeline.is_leaking:
            # Make a copy of the pipeline and disable leaks on it to get the no-leak flow rates
            no_leak_pipeline = pipeline.copy()
            no_leak_pipeline.set_ignore_leaks(True, sync=True)

            leak_rate_meter = FlowMeter(
                value=pipeline.leak_rate.to(flow_unit.unit).magnitude,
                min_value=cfg.flow_meter.min_value,
                max_value=max(
                    cfg.flow_meter.max_value,
                    pipeline.max_flow_rate.to(flow_unit.unit).magnitude,
                ),
                units=flow_unit.display,
                label="Leak " + cfg.flow_meter.label,
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
                update_func=lambda: pipeline.leak_rate.to(flow_unit.unit).magnitude,
                update_interval=cfg.flow_meter.update_interval,
                theme_color=theme_color,
                help_text="""
                The total volumetric flow rate lost due to leaks in the pipeline.
                """,
            )
            no_leak_pressure_gauge = PressureGauge(
                value=no_leak_pipeline.downstream_pressure.to(
                    pressure_unit.unit
                ).magnitude,
                min_value=cfg.pressure_guage.min_value,
                max_value=cfg.pressure_guage.max_value,
                units=pressure_unit.display,
                label="Expected " + cfg.pressure_guage.label,
                width=cfg.pressure_guage.width,
                height=cfg.pressure_guage.height,
                precision=cfg.pressure_guage.precision,
                alarm_high=cfg.pressure_guage.alarm_high,
                alarm_low=cfg.pressure_guage.alarm_low,
                animation_speed=cfg.pressure_guage.animation_speed,
                animation_interval=cfg.pressure_guage.animation_interval,
                update_func=lambda: no_leak_pipeline.downstream_pressure.to(
                    pressure_unit.unit
                ).magnitude,
                update_interval=cfg.pressure_guage.update_interval,
                theme_color=theme_color,
                help_text="""
                The expected downstream pressure assuming no leaks in the pipeline.
                """,
            )
            no_leak_flow_meter = FlowMeter(
                value=no_leak_pipeline.outlet_flow_rate.to(flow_unit.unit).magnitude,
                min_value=cfg.flow_meter.min_value,
                max_value=max(
                    cfg.flow_meter.max_value,
                    pipeline.max_flow_rate.to(flow_unit.unit).magnitude,
                ),
                units=flow_unit.display,
                label="Expected " + cfg.flow_meter.label,
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
                update_func=lambda: no_leak_pipeline.outlet_flow_rate.to(
                    flow_unit.unit
                ).magnitude,
                update_interval=cfg.flow_meter.update_interval,
                theme_color=theme_color,
                help_text="""
                The expected volumetric flow rate exiting the pipeline assuming no leaks.
                """,
            )
            no_leak_mass_flow_meter = MassFlowMeter(
                value=no_leak_pipeline.outlet_mass_rate.to(
                    mass_flow_unit.unit
                ).magnitude,
                min_value=cfg.mass_flow_meter.min_value,
                max_value=cfg.mass_flow_meter.max_value,
                units=mass_flow_unit.display,
                label="Expected " + cfg.mass_flow_meter.label,
                width=cfg.mass_flow_meter.width,
                height=cfg.mass_flow_meter.height,
                precision=cfg.mass_flow_meter.precision,
                alarm_high=cfg.mass_flow_meter.alarm_high,
                alarm_low=cfg.mass_flow_meter.alarm_low,
                animation_speed=cfg.mass_flow_meter.animation_speed,
                animation_interval=cfg.mass_flow_meter.animation_interval,
                flow_direction=str(pipeline.pipes[0].direction)
                if pipeline.pipes
                else "east",  # type: ignore
                update_func=lambda: no_leak_pipeline.outlet_mass_rate.to(
                    mass_flow_unit.unit
                ).magnitude,
                update_interval=cfg.mass_flow_meter.update_interval,
                theme_color=theme_color,
                help_text="""
                The expected mass flow rate exiting the pipeline assuming no leaks.
                """,
            )
            meters.extend(
                [
                    leak_rate_meter,
                    no_leak_pressure_gauge,
                    no_leak_flow_meter,
                    no_leak_mass_flow_meter,
                ]
            )
        return meters

    def build_regulators(
        self, manager: "PipelineManager[PipelineT]"
    ) -> typing.Iterable[Regulator]:
        """Downstream stations typically just have pressure regulators."""
        cfg = self.config
        pipeline = manager.get_pipeline()
        unit_system = manager.config.get_unit_system()
        theme_color = manager.config.state.global_.theme_color
        pressure_unit = unit_system["pressure"]

        def _set_pressure(value: float):
            manager.set_downstream_pressure(Quantity(value, pressure_unit.unit))

        pressure_regulator = Regulator(
            value=pipeline.downstream_pressure.to(pressure_unit.unit).magnitude,
            min_value=cfg.pressure_regulator.min_value,
            max_value=cfg.pressure_regulator.max_value,
            units=pressure_unit.display,
            label=cfg.pressure_regulator.label,
            width=cfg.pressure_regulator.width,
            height=cfg.pressure_regulator.height,
            precision=cfg.pressure_regulator.precision,
            alarm_high=cfg.pressure_regulator.alarm_high,
            alarm_low=cfg.pressure_regulator.alarm_low,
            setter_func=_set_pressure,
            theme_color=theme_color,
            help_text="""
            Set the downstream pressure. Note that changing the downstream pressure may affect the flow rate through the pipeline.
            """,
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
        if flow_station_config is self.config:
            return
        self.set_config(flow_station_config)


# Only the manager should monitor config changes and update pipeline.
# The UI should be subscribed to manager events.
# The manager can then notify the UI to refresh as needed when properties or configs change.
# This keeps things simple and avoids circular, repeated or redundant updates.


class PipelineManager(typing.Generic[PipelineT]):
    """Manages a Pipeline instance."""

    def __init__(
        self,
        pipeline: PipelineT,
        config: Configuration,
        validators: typing.Optional[typing.Sequence[PipeConfigValidator]] = None,
        flow_station_factories: typing.Optional[
            typing.Sequence[FlowStationFactory]
        ] = None,
    ) -> None:
        """
        Initialize the pipeline manager.

        :param pipeline: The Pipeline instance to manage.
        :param config: Configuration manager for global and pipeline settings.
        :param validators: Callables to validate the pipeline configurations.
        :param flow_station_factories: Callables to create flow stations for the pipeline.
        """
        self._pipeline = pipeline
        self._pipe_configs: typing.List[PipeConfig] = []
        self._fluid_config = FluidConfig()
        self._validators = validators or [validate_pipe_configs]
        self._flow_station_factories = flow_station_factories or []
        self._subscriptions: typing.List[EventSubscription] = []
        self._errors: typing.List[str] = []
        self._config = config
        self._config.observe(self.on_config_change)
        # Synchronize initial state
        self.sync(validate=True)

    @property
    def config(self) -> Configuration:
        """The configuration manager."""
        return self._config

    @property
    def config_state(self) -> ConfigurationState:
        """The current configuration state."""
        return self._config.state

    def sync(self, *, validate: bool = True) -> Self:
        """
        Synchronize pipe and fluid configs from the current pipeline state and validate the synchronized state.
        This ensures that the internal representation matches the actual Pipeline instance.

        *Called internally after any modification to the pipeline.*

        :param validate: Whether to run validation after synchronization.
        :return: Self for method chaining.
        """
        logger.info(
            f"Synchronizing pipeline manager state with pipeline {self._pipeline.name!r}"
        )
        self._pipe_configs = []

        if self._pipeline.fluid:
            self._fluid_config = FluidConfig(
                name=self._pipeline.fluid.name,
                phase=self._pipeline.fluid.phase,
                temperature=self._pipeline.fluid.temperature,  # type: ignore
                molecular_weight=self._pipeline.fluid.molecular_weight,  # type: ignore
            )

        for i, pipe in enumerate(self._pipeline):
            # Build leak configs from pipe leaks
            leak_configs = []
            for leak in pipe._leaks:
                leak_config = PipeLeakConfig(
                    location=leak.location,
                    diameter=leak.diameter,
                    discharge_coefficient=leak.discharge_coefficient,
                    active=leak.active,
                    name=leak.name,
                )
                leak_configs.append(leak_config)

            # Build valve configs from pipe valves
            valve_configs = []
            if pipe._start_valve is not None:
                valve_config = ValveConfig(
                    position="start",
                    state=pipe._start_valve.state.value.lower(),
                )
                valve_configs.append(valve_config)
            if pipe._end_valve is not None:
                valve_config = ValveConfig(
                    position="end",
                    state=pipe._end_valve.state.value.lower(),
                )
                valve_configs.append(valve_config)

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
                leaks=leak_configs,
                valves=valve_configs,
            )
            self._pipe_configs.append(pipe_config)

        if validate:
            self.validate()
        logger.info(
            f"Synchronized {len(self._pipe_configs)} pipes and fluid '{self._fluid_config.name}'"
        )
        return self

    def subscribe(self, event: str, callback: EventCallback):
        """
        Subscribe to pipeline events matching the given pattern.

        :param event: Event pattern to match:
            - "*" for all events
            - "pipeline.*" for prefix matching
            - "pipeline.pipe.added" for exact event
            - Regex patterns are also supported

        :param callback: Function to call when event matches
        """
        subscription = EventSubscription(event, callback)
        # Remove existing subscription with same event pattern and callback
        self._subscriptions = [
            sub
            for sub in self._subscriptions
            if not (sub.event == event and sub.callback == callback)
        ]
        self._subscriptions.append(subscription)

    def unsubscribe(self, event: str, callback: EventCallback):
        """
        Remove a subscription for the given event and callback.

        :param event: The event pattern to remove.
        :param callback: The callback function to remove.
        """
        self._subscriptions = [
            sub
            for sub in self._subscriptions
            if not (sub.event == event and sub.callback == callback)
        ]

    def unsubscribe_all(self, callback: EventCallback):
        """
        Remove all subscriptions for the given callback.

        :param callback: The callback function to remove subscriptions for.
        """
        self._subscriptions = [
            sub for sub in self._subscriptions if sub.callback != callback
        ]

    def notify(self, event: str, data: typing.Optional[typing.Dict] = None):
        """
        Notify all subscribers whose event patterns match the given event
        (sequentially, as they registered).

        :param event: The event name to notify.
        :param data: Optional data to pass to the callback.
        """
        if data is not None and not isinstance(data, dict):
            raise ValueError("Data must be a dictionary or None")

        for subscription in self._subscriptions:
            if subscription.matches(event):
                try:
                    subscription.callback(event, data)
                except Exception as exc:
                    logger.error(
                        f"Error notifying observer for event '{event}': {exc}",
                        exc_info=True,
                    )

    def on_config_change(self, config_state: ConfigurationState) -> None:
        """
        Monitors configuration changes.
        Updates the pipeline based on configuration changes.

        :param config_state: The new configuration state.
        """
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
        # Synchronize the pipeline state after applying all config changes
        self._pipeline.sync()
        self.sync(validate=True)
        if self.is_valid():
            self.notify(
                "pipeline.properties.updated",
                {"pipeline": self.get_pipeline(), "refresh_flow_stations": True},
            )
        logger.info(f"Updated pipeline configuration: {pipeline_config.name}")

    def build_fluid(self, fluid_config: FluidConfig) -> Fluid:
        """
        Build a Fluid instance from the current fluid config.

        :param fluid_config: The `FluidConfig` to build from.
        :return: A new Fluid instance.
        """
        return Fluid.from_coolprop(
            fluid_name=fluid_config.name,
            phase=fluid_config.phase,
            temperature=fluid_config.temperature,
            pressure=self._pipeline.upstream_pressure,
            molecular_weight=fluid_config.molecular_weight,
        )

    def build_pipe(
        self, pipe_config: PipeConfig, fluid: typing.Optional[Fluid] = None
    ) -> Pipe:
        """
        Build a Pipe instance from a pipe config.

        :param pipe_config: The `PipeConfig` to build from.
        :param fluid: Optional Fluid instance to associate with the pipe. If None, uses the current pipeline fluid.
        :return: A new pipe instance.
        """
        # Build leaks from leak configs
        leaks = []
        for leak_config in pipe_config.leaks:
            leak = PipeLeak(
                location=leak_config.location,
                diameter=leak_config.diameter,
                discharge_coefficient=leak_config.discharge_coefficient,
                active=leak_config.active,
                name=leak_config.name,
            )
            leaks.append(leak)

        # Build valves from valve configs
        start_valve = None
        end_valve = None
        for valve_config in pipe_config.valves:
            valve = Valve(
                position=valve_config.position,
                state=ValveState(valve_config.state.lower()),
            )
            if valve_config.position == "start":
                start_valve = valve
            elif valve_config.position == "end":
                end_valve = valve

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
            leaks=leaks if leaks else None,
            start_valve=start_valve,
            end_valve=end_valve,
            ambient_pressure=pipe_config.ambient_pressure,
        )

    def add_pipe(
        self, pipe_config: PipeConfig, index: typing.Optional[int] = None
    ) -> Self:
        """
        Add a pipe at the specified index (or at the end).

        :param pipe_config: The `PipeConfig` to add.
        :param index: Optional index to insert the pipe at. If None, appends to the end.
        :return: Self for method chaining.
        """
        if index is None:
            index = len(self._pipe_configs)

        pipe = self.build_pipe(pipe_config)
        self._pipeline.add_pipe(pipe, index, sync=True)

        self.sync(validate=True)
        if self.is_valid():
            self.notify(
                "pipeline.pipe.added",
                {
                    "pipe_config": pipe_config,
                    "index": index,
                    # Refresh flow stations only if this is the first pipe added
                    "refresh_flow_stations": len(self._pipe_configs) == 1,
                },
            )
        logger.info(f"Added pipe '{pipe_config.name}' at index {index}")
        return self

    def remove_pipe(self, index: int) -> Self:
        """
        Remove a pipe at the specified index.

        :param index: Index of the pipe to remove.
        :return: Self for method chaining.
        """
        if len(self._pipe_configs) <= 1:
            raise ValueError("Pipeline must contain at least one pipe")

        if 0 <= index < len(self._pipe_configs):
            # Remove from pipeline using its remove_pipe method
            self._pipeline.remove_pipe(index, sync=True)

            self.sync(validate=True)
            if self.is_valid():
                self.notify(
                    "pipeline.pipe.removed",
                    {
                        "index": index,
                        "refresh_flow_stations": False,
                    },
                )
            logger.info(f"Removed pipe from index {index}")
        return self

    def move_pipe(self, from_index: int, to_index: int) -> Self:
        """
        Move a pipe from one position to another.

        :param from_index: Current index of the pipe to move.
        :param to_index: Target index to move the pipe to.
        :return: Self for method chaining.
        """
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

            self.sync(validate=True)
            if self.is_valid():
                self.notify(
                    "pipeline.pipe.moved",
                    {
                        "from_index": from_index,
                        "to_index": to_index,
                        "pipe_config": pipe_config,
                        "refresh_flow_stations": False,
                    },
                )
            logger.info(f"Moved pipe from index {from_index} to {to_index}")
        return self

    def update_pipe(
        self, index: int, pipe_config: PipeConfig, *, update_flow_stations: bool = False
    ) -> Self:
        """
        Update a pipe configuration at the specified index.

        :param index: Index of the pipe to update.
        :param pipe_config: New `PipeConfig` to apply.
        :param update_flow_stations: Whether to notify flow stations to refresh. Default is False.
        :return: Self for method chaining.
        """
        if 0 <= index < len(self._pipe_configs):
            # Remove old pipe and add updated one
            self._pipeline.remove_pipe(index, sync=True)

            # Create new pipe with updated config
            pipe = self.build_pipe(pipe_config)
            self._pipeline.add_pipe(pipe, index, sync=True)

            self.sync(validate=True)
            if self.is_valid():
                self.notify(
                    "pipeline.pipe.updated",
                    {
                        "pipe_config": pipe_config,
                        "index": index,
                        "refresh_flow_stations": update_flow_stations,
                    },
                )
            logger.info(f"Updated pipe at index {index}")
        return self

    def set_fluid(self, fluid_config: FluidConfig) -> Self:
        """
        Set the fluid for the pipeline using the given fluid configuration.

        :param fluid_config: The `FluidConfig` to set.
        :return: Self for method chaining.
        """
        logger.info(f"Updating fluid to {fluid_config}")
        try:
            fluid = self.build_fluid(fluid_config)
            self._pipeline.set_fluid(fluid, sync=True)
        except Exception as exc:
            ui.notify(
                f"Error updating pipeline fluid '{fluid_config.name}'. Keeping existing fluid."
                f"\n Error: {exc}",
                type="warning",
                position="top",
            )
            logger.error(f"Error updating pipeline fluid: {exc}", exc_info=True)
            return self

        # Sync to update internal fluid config state from pipeline
        self.sync(validate=True)
        if self.is_valid():
            self.notify(
                "pipeline.properties.updated",
                {"pipeline": self.get_pipeline(), "refresh_flow_stations": False},
            )
        logger.info(f"Updated fluid configuration: {fluid_config.name}")
        return self

    def set_upstream_pressure(self, pressure: Quantity) -> Self:
        """Set the upstream pressure of the pipeline."""
        self._pipeline.set_upstream_pressure(pressure, sync=True)
        self.sync(validate=True)
        if self.is_valid():
            self.notify(
                "pipeline.properties.updated",
                {"pipeline": self.get_pipeline(), "refresh_flow_stations": False},
            )
        logger.info(f"Set upstream pressure to {pressure}")
        return self

    def set_downstream_pressure(self, pressure: Quantity) -> Self:
        """Set the downstream pressure of the pipeline."""
        self._pipeline.set_downstream_pressure(pressure, sync=True)
        self.sync(validate=True)
        if self.is_valid():
            self.notify(
                "pipeline.properties.updated",
                {"pipeline": self.get_pipeline(), "refresh_flow_stations": False},
            )
        logger.info(f"Set downstream pressure to {pressure}")
        return self

    def set_upstream_temperature(self, temperature: Quantity) -> Self:
        """Set the upstream temperature of the pipeline fluid."""
        if self._pipeline.fluid is None:
            ui.notify(
                "Cannot set temperature: No fluid is set in the pipeline.",
                type="warning",
                position="top",
            )
            logger.warning("Attempted to set temperature with no fluid in pipeline")
            return self

        self._pipeline.set_upstream_temperature(temperature)
        self.sync(validate=True)
        if self.is_valid():
            self.notify(
                "pipeline.properties.updated",
                {"pipeline": self.get_pipeline(), "refresh_flow_stations": False},
            )
        logger.info(f"Set upstream temperature to {temperature}")
        return self

    def add_pipe_leak(self, pipe_index: int, leak_config: PipeLeakConfig) -> Self:
        """
        Add a leak to a specific pipe.

        :param pipe_index: Index of the pipe to add leak to.
        :param leak_config: The leak configuration to add.
        :return: Self for method chaining.
        """
        if not (0 <= pipe_index < len(self._pipe_configs)):
            raise ValueError(f"Invalid pipe index: {pipe_index}")

        # Update pipe config with new leak
        pipe_config = self._pipe_configs[pipe_index]
        leaks = [*list(pipe_config.leaks), leak_config]
        updated_pipe_config = attrs.evolve(pipe_config, leaks=leaks)

        # Update the actual pipe
        # Only update flow stations if this is the first leak being added
        update_flow_stations = len(leaks) == 1
        self.update_pipe(
            pipe_index, updated_pipe_config, update_flow_stations=update_flow_stations
        )
        logger.info(f"Added leak to pipe '{pipe_config.name}' at index {pipe_index}")
        return self

    def remove_pipe_leak(self, pipe_index: int, leak_index: int) -> Self:
        """
        Remove a leak from a specific pipe.

        :param pipe_index: Index of the pipe to remove leak from.
        :param leak_index: Index of the leak to remove.
        :return: Self for method chaining.
        """
        if not (0 <= pipe_index < len(self._pipe_configs)):
            raise ValueError(f"Invalid pipe index: {pipe_index}")

        pipe_config = self._pipe_configs[pipe_index]

        if not (0 <= leak_index < len(pipe_config.leaks)):
            raise ValueError(f"Invalid leak index: {leak_index}")

        # Remove leak from config
        leaks = list(pipe_config.leaks)
        leaks.pop(leak_index)
        updated_pipe_config = attrs.evolve(pipe_config, leaks=leaks)

        # Update the actual pipe
        # Only update flow stations if this was the last leak being removed
        update_flow_stations = len(leaks) == 0
        self.update_pipe(
            pipe_index, updated_pipe_config, update_flow_stations=update_flow_stations
        )
        logger.info(
            f"Removed leak from pipe '{pipe_config.name}' at index {pipe_index}"
        )
        return self

    def update_pipe_leak(
        self, pipe_index: int, leak_index: int, leak_config: PipeLeakConfig
    ) -> Self:
        """
        Update a specific leak in a pipe.

        :param pipe_index: Index of the pipe containing the leak.
        :param leak_index: Index of the leak to update.
        :param leak_config: New leak configuration.
        :return: Self for method chaining.
        """
        if not (0 <= pipe_index < len(self._pipe_configs)):
            raise ValueError(f"Invalid pipe index: {pipe_index}")

        pipe_config = self._pipe_configs[pipe_index]

        if not (0 <= leak_index < len(pipe_config.leaks)):
            raise ValueError(f"Invalid leak index: {leak_index}")

        # Update leak in config
        leaks = list(pipe_config.leaks)
        leaks[leak_index] = leak_config
        updated_pipe_config = attrs.evolve(pipe_config, leaks=leaks)

        # Update the actual pipe
        self.update_pipe(pipe_index, updated_pipe_config)
        logger.info(f"Updated leak in pipe '{pipe_config.name}' at index {pipe_index}")
        return self

    def clear_pipe_leaks(self, pipe_index: int) -> Self:
        """
        Remove all leaks from a specific pipe.

        :param pipe_index: Index of the pipe to clear leaks from.
        :return: Self for method chaining.
        """
        if not (0 <= pipe_index < len(self._pipe_configs)):
            raise ValueError(f"Invalid pipe index: {pipe_index}")

        pipe_config = self._pipe_configs[pipe_index]
        leak_count = len(pipe_config.leaks)

        if leak_count == 0:
            ui.notify(
                f"Pipe '{pipe_config.name}' has no leaks to clear",
                type="info",
                position="top",
            )
            return self

        # Clear all leaks
        updated_pipe_config = attrs.evolve(pipe_config, leaks=[])
        # Update the actual pipe
        self.update_pipe(pipe_index, updated_pipe_config, update_flow_stations=True)
        logger.info(f"Cleared {leak_count} leaks from pipe '{pipe_config.name}'")
        return self

    def clear_all_leaks(self) -> Self:
        """
        Remove all leaks from all pipes in the pipeline.

        :return: Self for method chaining.
        """
        leak_count = sum(len(pc.leaks) for pc in self._pipe_configs)
        if leak_count == 0:
            ui.notify("Pipeline has no leaks to clear", type="info", position="top")
            return self

        # Clear leaks from all pipes
        for i, pipe_config in enumerate(self._pipe_configs):
            if pipe_config.leaks:
                updated_pipe_config = attrs.evolve(pipe_config, leaks=[])
                pipe = self.build_pipe(updated_pipe_config)
                # Remive and re-add pipes
                self._pipeline.remove_pipe(i, sync=False)
                self._pipeline.add_pipe(pipe, i, sync=False)

        # Sync once after all changes
        self._pipeline.sync()
        self.sync(validate=True)

        if self.is_valid():
            self.notify(
                "pipeline.leaks.cleared",
                {"leak_count": leak_count, "refresh_flow_stations": True},
            )
        logger.info(f"Cleared all {leak_count} leaks from pipeline")
        return self

    def toggle_leak(self, pipe_index: int, leak_index: int) -> Self:
        """
        Toggle the active state of a specific leak.

        :param pipe_index: Index of the pipe containing the leak.
        :param leak_index: Index of the leak to toggle.
        :return: Self for method chaining.
        """
        if not (0 <= pipe_index < len(self._pipe_configs)):
            raise ValueError(f"Invalid pipe index: {pipe_index}")

        pipe_config = self._pipe_configs[pipe_index]

        if not (0 <= leak_index < len(pipe_config.leaks)):
            raise ValueError(f"Invalid leak index: {leak_index}")

        # Toggle leak active state
        leak_config = pipe_config.leaks[leak_index]
        updated_leak_config = attrs.evolve(leak_config, active=not leak_config.active)
        return self.update_pipe_leak(pipe_index, leak_index, updated_leak_config)

    def get_pipe_leaks(self, pipe_index: int) -> typing.List[PipeLeakConfig]:
        """
        Get all leaks for a specific pipe.

        :param pipe_index: Index of the pipe.
        :return: List of leak configurations for the pipe.
        """
        if not (0 <= pipe_index < len(self._pipe_configs)):
            raise ValueError(f"Invalid pipe index: {pipe_index}")
        return list(self._pipe_configs[pipe_index].leaks)

    def get_all_leaks(self) -> typing.Dict[int, typing.List[PipeLeakConfig]]:
        """
        Get all leaks in the pipeline organized by pipe index.

        :return: Dictionary mapping pipe indices to their leak configurations.
        """
        return {
            i: list(pipe_config.leaks)
            for i, pipe_config in enumerate(self._pipe_configs)
            if pipe_config.leaks
        }

    def has_leaks(self) -> bool:
        """Check if the pipeline has any leaks."""
        return any(pipe_config.leaks for pipe_config in self._pipe_configs)

    def get_leak_count(self) -> int:
        """Get the total number of leaks in the pipeline."""
        return sum(len(pipe_config.leaks) for pipe_config in self._pipe_configs)

    def get_valve_count(self) -> int:
        """Get the total number of valves in the pipeline."""
        count = 0
        if self._pipeline:
            for pipe in self._pipeline.pipes:
                if pipe._start_valve:
                    count += 1
                if pipe._end_valve:
                    count += 1
        return count

    def add_valve(
        self,
        pipe_index: int,
        position: typing.Literal["start", "end"],
        valve: typing.Optional["Valve"] = None,
    ) -> Self:
        """
        Add a valve to a specific pipe.

        :param pipe_index: Index of the pipe to add valve to.
        :param position: Position of valve ("start" or "end").
        :param valve: Optional Valve instance (creates default if None).
        :return: Self for method chaining.
        """
        if not (0 <= pipe_index < len(self._pipe_configs)):
            raise ValueError(f"Invalid pipe index: {pipe_index}")

        pipe_config = self._pipe_configs[pipe_index]

        try:
            self._pipeline.add_valve(pipe_index, valve=valve, position=position)
            self.sync(validate=True)
            logger.info(
                f"Added {position} valve to pipe '{pipe_config.name}' at index {pipe_index}"
            )
            self.notify(
                "pipeline.valve.added",
                {
                    "pipe_index": pipe_index,
                    "position": position,
                    "pipe_config": pipe_config,
                },
            )
        except Exception as exc:
            logger.error(f"Failed to add valve: {exc}", exc_info=True)
            raise

        return self

    def remove_valve(
        self, pipe_index: int, position: typing.Literal["start", "end"]
    ) -> Self:
        """
        Remove a valve from a specific pipe.

        :param pipe_index: Index of the pipe to remove valve from.
        :param position: Position of valve to remove ("start" or "end").
        :return: Self for method chaining.
        """
        if not (0 <= pipe_index < len(self._pipe_configs)):
            raise ValueError(f"Invalid pipe index: {pipe_index}")

        pipe_config = self._pipe_configs[pipe_index]

        try:
            self._pipeline.remove_valve(pipe_index, position=position)
            self.sync(validate=True)
            logger.info(
                f"Removed {position} valve from pipe '{pipe_config.name}' at index {pipe_index}"
            )
            self.notify(
                "pipeline.valve.removed",
                {
                    "pipe_index": pipe_index,
                    "position": position,
                    "pipe_config": pipe_config,
                },
            )
        except Exception as exc:
            logger.error(f"Failed to remove valve: {exc}", exc_info=True)
            raise

        return self

    def toggle_valve(
        self, pipe_index: int, position: typing.Literal["start", "end"]
    ) -> Self:
        """
        Toggle a valve's state.

        :param pipe_index: Index of the pipe containing the valve.
        :param position: Position of valve to toggle ("start" or "end").
        :return: Self for method chaining.
        """
        if not (0 <= pipe_index < len(self._pipe_configs)):
            raise ValueError(f"Invalid pipe index: {pipe_index}")

        pipe_config = self._pipe_configs[pipe_index]

        try:
            self._pipeline.toggle_valve(pipe_index, position=position)
            valve = self._pipeline.pipes[pipe_index].get_valve(position)
            status = "opened" if valve and valve.is_open() else "closed"
            self.sync(validate=True)
            logger.info(
                f"Toggled {position} valve on pipe '{pipe_config.name}' - now {status}"
            )
            self.notify(
                "pipeline.valve.toggled",
                {
                    "pipe_index": pipe_index,
                    "position": position,
                    "status": status,
                    "pipe_config": pipe_config,
                },
            )
        except Exception as exc:
            logger.error(f"Failed to toggle valve: {exc}", exc_info=True)
            raise

        return self

    def open_valve(
        self, pipe_index: int, position: typing.Literal["start", "end"]
    ) -> Self:
        """
        Open a valve.

        :param pipe_index: Index of the pipe containing the valve.
        :param position: Position of valve to open ("start" or "end").
        :return: Self for method chaining.
        """
        if not (0 <= pipe_index < len(self._pipe_configs)):
            raise ValueError(f"Invalid pipe index: {pipe_index}")

        pipe_config = self._pipe_configs[pipe_index]

        try:
            self._pipeline.open_valve(pipe_index, position=position)
            self.sync(validate=True)
            logger.info(
                f"Opened {position} valve on pipe '{pipe_config.name}' at index {pipe_index}"
            )
            self.notify(
                "pipeline.valve.opened",
                {
                    "pipe_index": pipe_index,
                    "position": position,
                    "pipe_config": pipe_config,
                },
            )
        except Exception as exc:
            logger.error(f"Failed to open valve: {exc}", exc_info=True)
            raise

        return self

    def close_valve(
        self, pipe_index: int, position: typing.Literal["start", "end"]
    ) -> Self:
        """
        Close a valve.

        :param pipe_index: Index of the pipe containing the valve.
        :param position: Position of valve to close ("start" or "end").
        :return: Self for method chaining.
        """
        if not (0 <= pipe_index < len(self._pipe_configs)):
            raise ValueError(f"Invalid pipe index: {pipe_index}")

        pipe_config = self._pipe_configs[pipe_index]

        try:
            self._pipeline.close_valve(pipe_index, position=position)
            self.sync(validate=True)
            logger.info(
                f"Closed {position} valve on pipe '{pipe_config.name}' at index {pipe_index}"
            )
            self.notify(
                "pipeline.valve.closed",
                {
                    "pipe_index": pipe_index,
                    "position": position,
                    "pipe_config": pipe_config,
                },
            )
        except Exception as exc:
            logger.error(f"Failed to close valve: {exc}", exc_info=True)
            raise

        return self

    def open_all_valves(self) -> Self:
        """
        Open all valves in the pipeline.

        :return: Self for method chaining.
        """
        try:
            self._pipeline.open_all_valves()
            self.sync(validate=True)
            logger.info("Opened all valves in pipeline")
            self.notify("pipeline.valves.all_opened", {})
        except Exception as exc:
            logger.error(f"Failed to open all valves: {exc}", exc_info=True)
            raise

        return self

    def close_all_valves(self) -> Self:
        """
        Close all valves in the pipeline.

        :return: Self for method chaining.
        """
        try:
            self._pipeline.close_all_valves()
            self.sync(validate=True)
            logger.info("Closed all valves in pipeline")
            self.notify("pipeline.valves.all_closed", {})
        except Exception as exc:
            logger.error(f"Failed to close all valves: {exc}", exc_info=True)
            raise

        return self

    def validate(self):
        """Validate the current pipeline configuration."""
        errors = []
        for validator in self._validators:
            try:
                validation_errors = validator(self._pipe_configs)
                errors.extend(validation_errors)
            except Exception as exc:
                logger.error(f"Error during validation: {exc}", exc_info=True)
        self._errors = errors
        self.notify("pipeline.validation.changed", {"errors": errors})

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

    def export_configuration(self) -> str:
        """
        Export the current pipeline configuration to JSON format.

        :return: JSON string containing pipe and fluid configurations
        """
        config_data = {
            "pipes": [converter.unstructure(pipe) for pipe in self._pipe_configs],
            "fluid": converter.unstructure(self._fluid_config),
            "pipeline": {
                "name": self._pipeline.name,
                "scale_factor": self._pipeline.scale_factor,
                "max_flow_rate": unstructure_quantity(self._pipeline.max_flow_rate),
                "connector_length": unstructure_quantity(
                    self._pipeline.connector_length
                ),
                "flow_type": self._pipeline._flow_type.value,
            },
        }
        return orjson.dumps(config_data, option=orjson.OPT_INDENT_2).decode("utf-8")

    def import_configuration(self, json_data: str) -> Self:
        """
        Import pipeline configuration from JSON format.

        :param json_data: JSON string containing pipe and fluid configurations
        :return: self for method chaining
        """
        try:
            config_data = orjson.loads(json_data)

            # Clear existing pipes
            self._pipe_configs.clear()

            # Import pipe configurations
            if "pipes" in config_data:
                for pipe_data in config_data["pipes"]:
                    pipe_config = converter.structure(pipe_data, PipeConfig)
                    self._pipe_configs.append(pipe_config)

            # Import fluid configuration
            if "fluid" in config_data:
                self._fluid_config = converter.structure(
                    config_data["fluid"], FluidConfig
                )

            # Import pipeline settings if available
            if "pipeline" in config_data:
                pipeline_data = config_data["pipeline"]
                if "name" in pipeline_data:
                    self._pipeline.name = pipeline_data["name"]
                if "scale_factor" in pipeline_data:
                    self._pipeline.set_scale_factor(
                        pipeline_data["scale_factor"], update_viz=False
                    )
                if "max_flow_rate" in pipeline_data:
                    self._pipeline.set_max_flow_rate(
                        structure_quantity(pipeline_data["max_flow_rate"], None),
                        update_viz=False,
                    )
                if "connector_length" in pipeline_data:
                    self._pipeline.set_connector_length(
                        structure_quantity(pipeline_data["connector_length"], None),
                        sync=False,
                    )
                if "flow_type" in pipeline_data:
                    self._pipeline.set_flow_type(
                        FlowType(pipeline_data["flow_type"]), sync=False
                    )

            # Rebuild pipeline from imported configs
            self.sync(validate=True)
            self.notify("pipeline.configuration.imported")

            logger.info(
                f"Imported configuration: {len(self._pipe_configs)} pipes and fluid '{self._fluid_config.name}'"
            )
            return self

        except Exception as exc:
            logger.error(f"Error importing configuration: {exc}", exc_info=True)
            raise ValueError(f"Failed to import configuration: {exc}")

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
            except Exception as exc:
                logger.error(f"Error building flow station: {exc}", exc_info=True)
        return flow_stations

    def dump_state(self) -> typing.Dict[str, typing.Any]:
        """Dump the current state of the pipeline manager for serialization."""
        return {
            "pipeline": {
                "name": self._pipeline.name,
                "max_flow_rate": unstructure_quantity(self._pipeline.max_flow_rate),
                "flow_type": self._pipeline._flow_type.value,
                "scale_factor": self._pipeline.scale_factor,
                "connector_length": unstructure_quantity(
                    self._pipeline.connector_length
                ),
                "alert_errors": self._pipeline.alert_errors,
            },
            "fluid": converter.unstructure(self._fluid_config),
            "pipes": [converter.unstructure(pc) for pc in self._pipe_configs],
        }

    @classmethod
    def load_state(
        cls,
        state: typing.Dict[str, typing.Any],
        config: Configuration,
        validators: typing.Optional[typing.Sequence[PipeConfigValidator]] = None,
        flow_station_factories: typing.Optional[
            typing.Sequence[FlowStationFactory]
        ] = None,
        pipeline_type: typing.Type[PipelineT] = Pipeline,
    ) -> Self:
        """
        Load a pipeline manager from a dumped state.

        :param state: The dumped state dictionary.
        :param config: Configuration manager for global and pipeline settings.
        :param validators: Optional list of validation functions.
        :param flow_station_factories: Optional list of flow station factories.
        :param pipeline_type: The Pipeline subclass to instantiate.
        :return: A pipeline manager with the loaded state.
        """
        pipeline_data = state.get("pipeline", {})
        fluid_data = state.get("fluid", {})
        pipes_data = state.get("pipes", [])

        # Build pipes
        pipe_configs = [
            converter.structure(pipe_data, PipeConfig) for pipe_data in pipes_data
        ]
        pipes = []
        for pc in pipe_configs:
            # Build leaks from leak configs
            leaks = []
            for leak_config in pc.leaks:
                leak = PipeLeak(
                    location=leak_config.location,
                    diameter=leak_config.diameter,
                    discharge_coefficient=leak_config.discharge_coefficient,
                    active=leak_config.active,
                    name=leak_config.name,
                )
                leaks.append(leak)

            # Build valves from valve configs
            start_valve = None
            end_valve = None
            for valve_config in pc.valves:
                valve = Valve(
                    position=valve_config.position,
                    state=ValveState(valve_config.state.lower()),
                )
                if valve_config.position == "start":
                    start_valve = valve
                elif valve_config.position == "end":
                    end_valve = valve

            pipe = Pipe(
                length=pc.length,
                internal_diameter=pc.internal_diameter,
                upstream_pressure=pc.upstream_pressure,
                downstream_pressure=pc.downstream_pressure,
                material=pc.material,
                roughness=pc.roughness,
                efficiency=pc.efficiency,
                elevation_difference=pc.elevation_difference,
                fluid=None,  # Will be set later
                direction=pc.direction,
                name=pc.name,
                scale_factor=pc.scale_factor,
                max_flow_rate=pc.max_flow_rate,
                flow_type=pc.flow_type,
                leaks=leaks if leaks else None,
                start_valve=start_valve,
                end_valve=end_valve,
            )
            pipes.append(pipe)

        # Build pipeline
        pipeline = pipeline_type(
            pipes=pipes,
            fluid=None,  # Will be set later
            name=pipeline_data.get("name", "Pipeline"),
            max_flow_rate=structure_quantity(
                pipeline_data.get("max_flow_rate", {"magnitude": 1.0, "unit": "m^3/s"}),
                Quantity,
            ),
            flow_type=FlowType(pipeline_data.get("flow_type", "incompressible")),
            scale_factor=pipeline_data.get("scale_factor", 1.0),
            connector_length=structure_quantity(
                pipeline_data.get("connector_length", {"magnitude": 0.0, "unit": "m"}),
                Quantity,
            ),
            alert_errors=pipeline_data.get("alert_errors", True),
        )

        if fluid_data:
            # Build fluid
            fluid_config = converter.structure(fluid_data, FluidConfig)
            try:
                fluid = Fluid.from_coolprop(
                    fluid_name=fluid_config.name,
                    phase=fluid_config.phase,
                    temperature=fluid_config.temperature,
                    pressure=pipeline.upstream_pressure
                    or Quantity(101325, "Pa"),  # Default to 1 atm if not specified
                    molecular_weight=fluid_config.molecular_weight,
                )
                pipeline.set_fluid(fluid, sync=True)
            except Exception as exc:
                ui.notify(
                    f"Error building fluid '{fluid_config.name}'. Proceeding with no fluid.",
                    type="warning",
                )
                logger.error(f"Error building fluid from config: {exc}", exc_info=True)

        return cls(
            pipeline=pipeline,
            config=config,
            validators=validators,
            flow_station_factories=flow_station_factories,
        )


class PipelineManagerUI(typing.Generic[PipelineT]):
    """Interactive UI for pipeline management with real-time updates."""

    def __init__(
        self,
        manager: PipelineManager[PipelineT],
    ) -> None:
        """
        Initialize the pipeline manager UI.

        :param manager: The PipelineManager instance to interface with.
        :param theme_color: The primary theme color for UI elements.
        """
        self.manager = manager
        self.config_ui = ConfigurationUI(manager.config)

        # Subscribe to specific events with targeted handlers
        self.manager.subscribe("pipeline.pipe.added", self.on_pipe_added)
        self.manager.subscribe("pipeline.pipe.removed", self.on_pipe_removed)
        self.manager.subscribe("pipeline.pipe.moved", self.on_pipe_moved)
        self.manager.subscribe("pipeline.pipe.updated", self.on_pipe_updated)
        self.manager.subscribe(
            "pipeline.properties.updated", self.on_properties_updated
        )
        self.manager.subscribe(
            "pipeline.validation.changed", self.on_validation_changed
        )
        self.manager.subscribe("pipeline.leaks.cleared", self.on_leaks_cleared)

        # Subscribe to valve events
        self.manager.subscribe("pipeline.valve.added", self.on_valve_added)
        self.manager.subscribe("pipeline.valve.removed", self.on_valve_removed)
        self.manager.subscribe("pipeline.valve.toggled", self.on_valve_toggled)
        self.manager.subscribe("pipeline.valve.opened", self.on_valve_opened)
        self.manager.subscribe("pipeline.valve.closed", self.on_valve_closed)

        # UI components
        self.add_pipe_button = None
        self.config_menu_button = None
        self.main_container = None
        self.pipes_container = None
        self.validation_container = None
        self.pipeline_preview = None
        self.flow_station_container = None
        self.properties_panel = None
        self.pipe_form_container = None
        self.fluid_form_container = None
        self.selected_pipe_index: typing.Optional[int] = None
        """Index of the currently selected pipe, or None if no selection."""
        self.current_pipeline: typing.Optional[Pipeline] = None
        """Cached current pipeline for comparison."""
        self.current_flow_stations: typing.Optional[typing.List[FlowStation]] = None
        """Cached current flow stations for comparison."""

        # Leak management UI state
        self.leak_form_container = None
        self.leak_form_dialog = None
        self.selected_leak_index: typing.Optional[int] = None
        """Index of the currently selected leak, or None if no selection."""
        self.leak_edit_mode: bool = False
        """Whether we're in leak edit mode or add mode."""

    # For easy access to configuration properties
    @property
    def config(self) -> Configuration:
        """Get the configuration manager."""
        return self.manager.config

    @property
    def theme_color(self) -> str:
        """Get the current theme color."""
        return self.config.state.global_.theme_color

    @property
    def unit_system(self) -> UnitSystem:
        """Get the current unit system."""
        return self.config.get_unit_system()

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

    def on_pipe_added(self, event: str, data: typing.Optional[typing.Dict]):
        """Handle pipe added events."""
        if data is None:
            return
        ui.notify(
            f"Pipe '{data['pipe_config'].name}' added at index {data['index']}",
            type="success",
            position="top",
        )
        self.refresh_pipes_list()
        self.refresh_pipeline_preview()
        if self.flow_station_container is None or (
            data.get("refresh_flow_stations", False)
        ):
            self.refresh_flow_stations()

    def on_pipe_removed(self, event: str, data: typing.Optional[typing.Dict]):
        """Handle pipe removed events."""
        if data is None:
            return
        ui.notify(
            f"Pipe at index {data['index']} removed.",
            type="success",
            position="top",
        )
        self.refresh_pipes_list()
        self.refresh_pipeline_preview()
        if self.flow_station_container is None or (
            data.get("refresh_flow_stations", False)
        ):
            self.refresh_flow_stations()

        if self.selected_pipe_index is not None and self.selected_pipe_index >= len(
            self.manager.get_pipe_configs()
        ):
            self.selected_pipe_index = None
            self.refresh_properties_panel()

    def on_pipe_moved(self, event: str, data: typing.Optional[typing.Dict]):
        """Handle pipe moved events."""
        if data is None:
            return
        ui.notify(
            f"Pipe '{data['pipe_config'].name}' moved.",
            type="success",
            position="top",
        )
        self.refresh_pipes_list()
        self.refresh_pipeline_preview()
        if self.flow_station_container is None or (
            data.get("refresh_flow_stations", False)
        ):
            self.refresh_flow_stations()

    def on_pipe_updated(self, event: str, data: typing.Optional[typing.Dict]):
        """Handle pipe updated events."""
        if data is None:
            return
        ui.notify(
            f"Pipe '{data['pipe_config'].name}' updated.",
            type="success",
            position="top",
        )
        self.refresh_pipes_list()
        self.refresh_pipeline_preview()
        self.refresh_properties_panel()
        if self.flow_station_container is None or (
            data.get("refresh_flow_stations", False)
        ):
            self.refresh_flow_stations()

    def on_properties_updated(self, event: str, data: typing.Optional[typing.Dict]):
        """Handle general properties updated events."""
        if data is None:
            data = {}
        self.refresh_pipes_list()
        self.refresh_properties_panel()
        self.refresh_pipeline_preview()
        if self.flow_station_container is None or (
            data.get("refresh_flow_stations", False)
        ):
            self.refresh_flow_stations()

    def on_validation_changed(self, event: str, data: typing.Optional[typing.Dict]):
        """Handle validation changed events."""
        self.refresh_validation_display()

    def on_leaks_cleared(self, event: str, data: typing.Optional[typing.Dict]):
        """Handle leaks cleared from pipe events."""
        if data is None:
            return
        ui.notify(
            f"Cleared {data['leak_count']} leak(s) from pipeline.",
            type="success",
            position="top",
        )
        self.refresh_pipes_list()
        self.refresh_pipeline_preview()
        self.refresh_properties_panel()
        if self.flow_station_container is None or (
            data.get("refresh_flow_stations", False)
        ):
            self.refresh_flow_stations()

    def on_valve_added(self, event: str, data: typing.Optional[typing.Dict]):
        """Handle valve added events."""
        if data is None:
            return
        position = data.get("position", "")
        pipe_name = data.get("pipe_config", {}).name if data.get("pipe_config") else ""
        ui.notify(
            f"Added {position} valve to {pipe_name}",
            type="success",
            position="top",
        )
        self.refresh_properties_panel()
        self.refresh_pipeline_preview()

    def on_valve_removed(self, event: str, data: typing.Optional[typing.Dict]):
        """Handle valve removed events."""
        if data is None:
            return
        position = data.get("position", "")
        pipe_name = data.get("pipe_config", {}).name if data.get("pipe_config") else ""
        ui.notify(
            f"Removed {position} valve from {pipe_name}",
            type="success",
            position="top",
        )
        self.refresh_properties_panel()
        self.refresh_pipeline_preview()

    def on_valve_toggled(self, event: str, data: typing.Optional[typing.Dict]):
        """Handle valve toggled events."""
        if data is None:
            return
        status = data.get("status", "")
        ui.notify(
            f"Valve {status}",
            type="success",
            position="top",
        )
        self.refresh_properties_panel()
        self.refresh_pipeline_preview()

    def on_valve_opened(self, event: str, data: typing.Optional[typing.Dict]):
        """Handle valve opened events."""
        if data is None:
            return
        position = data.get("position", "")
        pipe_name = data.get("pipe_config", {}).name if data.get("pipe_config") else ""
        ui.notify(
            f"Opened {position} valve on {pipe_name}",
            type="success",
            position="top",
        )
        self.refresh_properties_panel()
        self.refresh_pipeline_preview()

    def on_valve_closed(self, event: str, data: typing.Optional[typing.Dict]):
        """Handle valve closed events."""
        if data is None:
            return
        position = data.get("position", "")
        pipe_name = data.get("pipe_config", {}).name if data.get("pipe_config") else ""
        ui.notify(
            f"Closed {position} valve on {pipe_name}",
            type="success",
            position="top",
        )
        self.refresh_properties_panel()
        self.refresh_pipeline_preview()

    def cleanup(self):
        """Clean up resources and remove observers."""
        try:
            # Remove all subscriptions for this UI instance
            self.manager.unsubscribe_all(self.on_pipe_added)
            self.manager.unsubscribe_all(self.on_pipe_removed)
            self.manager.unsubscribe_all(self.on_pipe_moved)
            self.manager.unsubscribe_all(self.on_pipe_updated)
            self.manager.unsubscribe_all(self.on_properties_updated)
            self.manager.unsubscribe_all(self.on_validation_changed)
            self.manager.unsubscribe_all(self.on_leaks_cleared)
            logger.info("Pipeline Manager UI cleaned up!")
        except Exception as exc:
            logger.error(
                f"Error during Pipeline Manager UI cleanup: {exc}", exc_info=True
            )

    def update_button_themes(self):
        """Update all button colors to match current theme."""
        # Update Add Pipe button
        if self.add_pipe_button is not None:
            self.add_pipe_button.props(f'color="{self.theme_color}"')
            self.add_pipe_button.update()

        # Update Config Menu button
        if self.config_menu_button is not None:
            self.config_menu_button.props(f'color="{self.theme_color}"')
            self.config_menu_button.update()

    def show(
        self,
        min_width: str = "300px",
        max_width: str = "1200px",
        ui_label: str = "Flowline Builder",
        pipeline_label: str = "Flowline Preview",
        flow_station_label: str = "Flow Station - Meters & Regulators",
        show_label: bool = True,
    ) -> ui.column:
        """
        Render the pipeline builder UI.

        :param min_width: Minimum width of the main container.
        :param max_width: Maximum width of the main container.
        :param ui_label: Label for the UI header.
        :param pipeline_label: Label for the pipeline preview.
        :param flow_station_label: Label for the flow station panel.
        :param show_label: Whether to show the UI label header.
        :return: The main UI container.
        """
        self.main_container = (
            ui.column()
            .classes("w-full min-h-screen gap-2 p-2 sm:gap-4 sm:p-4")
            .style(
                f"""
                min-width: min({min_width}, 100%); 
                max-width: {max_width}; 
                margin-left: auto; 
                margin-right: auto; 
                border-color: #CCC;
                outline-color: #AAA;
                """
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
        """Show configuration menu button"""
        # System configuration button
        self.config_menu_button = (
            ui.button(
                icon="settings",
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
            ui.label("Flowline Builder").classes(
                "text-lg sm:text-xl font-semibold mb-2 sm:mb-3"
            )

            # Button row with Add Pipe and Config toggle
            button_row = ui.row().classes(
                "w-full gap-2 mb-2 sm:mb-4 flex-wrap sm:flex-nowrap items-center"
            )
            with button_row:
                # Add pipe button
                self.add_pipe_button = (
                    ui.button(
                        "+ Add Pipe",
                        on_click=self.show_pipe_dialog,
                        color=self.theme_color,
                    )
                    .classes(self.get_primary_button_classes("flex-1 sm:flex-none"))
                    .tooltip("Add a new pipe section to the flowline")
                )

            # Collapsible config section
            config_expansion = ui.expansion(
                "Pipe Configuration Options", icon="tune"
            ).classes("w-full")
            config_expansion.value = False  # Collapsed by default
            config_expansion.classes("mb-2")

            with config_expansion:
                config_column = ui.column().classes("w-full gap-2 p-2")
                with config_column:
                    # Export button
                    ui.button(
                        "Export Configuration",
                        icon="file_download",
                        on_click=self.export_pipe_configuration,
                        color=self.theme_color,
                    ).props("outline").classes("w-full").tooltip(
                        "Export pipe configuration to JSON file"
                    )

                    # Import button
                    ui.upload(
                        on_upload=self.import_pipe_configuration,
                        auto_upload=True,
                        max_file_size=5_000_000,  # 5MB
                        label="Import Configuration",
                    ).props(
                        f"outline color={self.theme_color} icon=file_upload accept=.json"
                    ).classes("w-full").tooltip(
                        "Import pipe configuration from JSON file"
                    )

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
            ui.label("Configure Properties").classes(
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

    def show_preview_panel(self, pipeline_label: str = "Flowline Preview"):
        """Create the pipeline preview panel."""
        preview_card = (
            ui.card()
            .classes("w-full p-2 sm:p-4")
            .style("height: fit-content; overflow-y: auto; position: relative;")
        )
        with preview_card:
            ui.label(pipeline_label).classes(
                "text-lg sm:text-xl font-semibold mb-2 sm:mb-3"
            )
            self.pipeline_preview = (
                ui.column()
                .classes("w-full overflow-x-hidden")
                .style("height: 100%; min-height: 300px; position: relative;")
            )
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

        logger.debug("Refreshing pipes list...")

        self.pipes_container.clear()
        with self.pipes_container:
            pipe_configs = self.manager.get_pipe_configs()
            pipe_count = len(pipe_configs)
            for i, pipe_config in enumerate(pipe_configs):
                pipe_row = (
                    ui.row()
                    .classes(
                        "w-full items-center gap-2 p-2 sm:p-3 border rounded-lg hover:shadow-md transition-shadow flex-wrap sm:flex-nowrap"
                    )
                    .style("border-color: #CCC;")
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

                        # Add leak indicator if pipe has leaks
                        if pipe_config.leaks:
                            active_leaks = sum(
                                1 for leak in pipe_config.leaks if leak.active
                            )
                            total_leaks = len(pipe_config.leaks)
                            leak_color = "red" if active_leaks > 0 else "gray"
                            leak_text = f"⚠ {active_leaks}/{total_leaks} leaks active"
                            ui.label(leak_text).classes(
                                f"text-xs text-{leak_color}-600 font-medium"
                            )

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
                        ).tooltip("Edit pipe properties and manage leaks")
                        ui.button(
                            "↑",
                            on_click=partial(self.move_pipe_up, i),
                            color=self.theme_color,
                        ).classes(
                            self.get_secondary_button_classes(
                                "text-xs sm:text-sm px-2 py-1"
                            )
                        ).props(
                            "disabled" if i == 0 or (pipe_count < 3) else ""
                        ).tooltip(
                            "Move pipe upstream" if i > 0 and pipe_count >= 3 else ""
                        )
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
                        ).tooltip(
                            "Move pipe downstream"
                            if i < pipe_count - 1 and pipe_count >= 3
                            else ""
                        )
                        ui.button(
                            "✕", on_click=partial(self.remove_pipe, i), color="red"
                        ).classes(
                            self.get_danger_button_classes(
                                "text-xs sm:text-sm px-2 py-1"
                            )
                        ).props("disabled" if pipe_count <= 1 else "").tooltip(
                            "Remove pipe from flowline" if pipe_count > 1 else ""
                        )

    def refresh_validation_display(self):
        """Refresh the validation display."""
        if self.validation_container is None:
            return
        logger.debug("Refreshing validation display...")

        self.validation_container.clear()
        with self.validation_container:
            errors = self.manager.get_errors()

            if errors:
                ui.label("Validation Errors:").classes("font-medium text-red-600")
                for error in errors:
                    ui.label(f"• {error}").classes("text-sm text-red-600 ml-4")
            else:
                ui.label("✓ Flowline configuration valid").classes(
                    "text-green-600 font-medium"
                )

    def refresh_properties_panel(self):
        """Refresh the properties panel."""
        if self.fluid_form_container is None:
            return

        logger.debug("Refreshing properties panel...")

        self.fluid_form_container.clear()
        # Always show fluid properties in the right container
        with self.fluid_form_container:
            self.show_fluid_form()

        if self.pipe_form_container is None:
            return

        self.pipe_form_container.clear()
        # Show pipe properties in the left container if a pipe is selected
        with self.pipe_form_container:
            if self.selected_pipe_index is not None:
                pipe_configs = self.manager.get_pipe_configs()
                if self.selected_pipe_index < len(pipe_configs):
                    self.show_pipe_form(pipe_configs[self.selected_pipe_index])
            else:
                # Show pipeline summaries when no pipe is selected
                has_leaks = self.manager.has_leaks()
                has_valves = self.manager.get_valve_count() > 0

                if has_leaks or has_valves:
                    summaries_container = ui.column().classes("w-full gap-3")
                    with summaries_container:
                        # Valves Summary
                        if has_valves:
                            self.show_pipeline_valves_summary()

                        # Leak Summary
                        if has_leaks:
                            self.show_pipeline_leak_summary()
                else:
                    # Show placeholder when no pipe is selected and no leaks/valves exist
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
        logger.debug("Refreshing pipeline preview...")

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
        logger.debug("Refreshing flow stations...")

        self.flow_station_container.clear()
        with self.flow_station_container:
            if self.manager.is_valid() and self.manager.get_pipe_configs():
                flow_stations = self.manager.build_flow_stations()
                self.current_flow_stations = flow_stations
                if flow_stations:
                    for station in flow_stations:
                        station.show(meters_per_row=4, regulators_per_row=4)
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
            ui.label("Add a New Pipe").classes("text-lg font-semibold").style(
                "margin-bottom: 4px;"
            )
            ui.html(
                "<small class='text-gray-500'>Configure the new pipe below:</small>",
                sanitize=False,
            )

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
                    config_state = self.config.state
                    pipe_config = config_state.pipeline.pipe

                    length_default = pipe_config.length.to(length_unit.unit).magnitude
                    diameter_default = pipe_config.internal_diameter.to(
                        diameter_unit.unit
                    ).magnitude

                    length_input = (
                        ui.number(
                            f"Length ({length_unit})",
                            value=length_default,
                            min=0.1,
                            step=0.1,
                        )
                        .classes("flex-1 min-w-0")
                        .tooltip(
                            "Length of the pipe segment. Affects pressure drop calculations."
                        )
                    )
                    diameter_input = (
                        ui.number(
                            f"Diameter ({diameter_unit})",
                            value=diameter_default,
                            min=0.1,
                            step=0.1,
                        )
                        .classes("flex-1 min-w-0")
                        .tooltip(
                            "Internal diameter of the pipe. Critical for flow rate and pressure drop calculations."
                        )
                    )

                # Only allow pipe pressure to be set if there are no pipes yet.
                # Pipe pressures will be managed by pipeline(flow equations) and flow stations
                pressure_unit = self.unit_system["pressure"]
                if pipe_count == 0:
                    # Pressure row
                    pressure_row = ui.row().classes(
                        "w-full gap-2 flex-wrap sm:flex-nowrap"
                    )
                    with pressure_row:
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
                            .tooltip(
                                "Inlet pressure for the first pipe. Subsequent pipe pressures are calculated automatically."
                            )
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
                            .tooltip(
                                "Outlet pressure for the last pipe. Must be less than upstream pressure."
                            )
                        )
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
                    material_input = (
                        ui.input("Material", value=pipe_config.material)
                        .classes("flex-1 min-w-0")
                        .tooltip(
                            "Pipe material (e.g., Steel, PVC). Affects roughness and documentation."
                        )
                    )
                    direction_select = (
                        ui.select(
                            options=[d.value for d in PipeDirection],
                            value=PipeDirection.EAST.value,
                            label="Flow Direction",
                        )
                        .classes("flex-1 min-w-0")
                        .tooltip(
                            "Flow direction for visualization. Opposing directions cannot be connected."
                        )
                    )

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
                position_select = (
                    ui.select(
                        options=position_options, value="End", label="Insert Position"
                    )
                    .classes("w-full")
                    .tooltip(
                        "Choose where to insert the new pipe in the flowline sequence."
                    )
                )

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
                        on_click=lambda: self.save_pipe_add_form(
                            dialog=dialog,
                            name=name_input.value,
                            length=length_input.value,
                            diameter=diameter_input.value,
                            upstream_pressure=upstream_pressure_input.value,
                            downstream_pressure=downstream_pressure_input.value,
                            direction=direction_select.value,
                            material=material_input.value,
                            roughness=roughness_input.value,
                            elevation=elevation_input.value,
                            efficiency=efficiency_input.value,
                            position=position_select.value,
                            length_unit=length_unit.unit,
                            diameter_unit=diameter_unit.unit,
                            pressure_unit=pressure_unit.unit,
                            roughness_unit=roughness_unit.unit,
                            elevation_unit=elevation_unit.unit,
                        ),
                        color=self.theme_color,
                    ).classes(
                        self.get_primary_button_classes("px-4 py-2 flex-1 sm:flex-none")
                    )
        dialog.open()

    def save_pipe_add_form(
        self,
        dialog: ui.dialog,
        name: typing.Optional[str],
        length: float,
        diameter: float,
        upstream_pressure: float,
        downstream_pressure: float,
        direction: str,
        material: str,
        roughness: float,
        elevation: float,
        efficiency: float,
        position: str,
        length_unit: str = "m",
        diameter_unit: str = "m",
        pressure_unit: str = "Pa",
        roughness_unit: str = "m",
        elevation_unit: str = "m",
    ):
        """
        Add pipe from pipe add dialog data.

        :param dialog: The dialog instance to close after adding.
        :param name: Name of the pipe.
        :param length: Length of the pipe.
        :param diameter: Internal diameter of the pipe.
        :param upstream_pressure: Upstream pressure of the pipe.
        :param downstream_pressure: Downstream pressure of the pipe.
        :param direction: Flow direction of the pipe.
        :param material: Material of the pipe.
        :param roughness: Roughness of the pipe.
        :param elevation: Elevation difference of the pipe.
        :param efficiency: Efficiency of the pipe.
        :param position: Position to insert the pipe ("End" or "Before Pipe X").
        :param length_unit: Unit for length.
        :param diameter_unit: Unit for diameter.
        :param pressure_unit: Unit for pressure.
        :param roughness_unit: Unit for roughness.
        :param elevation_unit: Unit for elevation.
        """
        try:
            pipe_config = PipeConfig(
                name=name.strip() or f"Pipe-{len(self.manager.get_pipe_configs()) + 1}",
                length=Quantity(length, length_unit),  # type: ignore
                internal_diameter=Quantity(diameter, diameter_unit),  # type: ignore
                upstream_pressure=Quantity(
                    upstream_pressure,
                    pressure_unit,  # type: ignore
                ),
                downstream_pressure=Quantity(
                    downstream_pressure,
                    pressure_unit,  # type: ignore
                ),
                direction=PipeDirection(direction),
                material=material or "Steel",
                roughness=Quantity(roughness, roughness_unit),  # type: ignore
                elevation_difference=Quantity(elevation, elevation_unit),  # type: ignore
                efficiency=efficiency,
            )

            # Determine insertion index
            index = None
            if position.lower() != "end":
                # Extract pipe number from "Before Pipe X"
                pipe_num = int(position.split()[-1]) - 1  # type: ignore
                index = pipe_num

            self.manager.add_pipe(pipe_config, index)
            dialog.close()

        except Exception as exc:
            logger.error(f"Error adding pipe: {exc}", exc_info=True)
            ui.notify(f"Error adding pipe: {str(exc)}", type="negative")

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
        except ValueError as exc:
            ui.notify(str(exc), type="warning")

    def show_pipe_form(self, pipe_config: PipeConfig):
        """Create form for editing pipe properties."""
        pipe_header = ui.card().classes(
            f"w-full mb-3 bg-gradient-to-r from-{self.theme_color}-50 to-{self.theme_color}-100 border-l-4 border-{self.theme_color}-500"
        )
        with pipe_header:
            ui.label(f"Editing: {pipe_config.name}'s Configuration").classes(
                f"font-semibold text-{self.theme_color}-800 p-2"
            )
            ui.html(
                "<small class='text-gray-500'>Modify pipe properties below.</small>",
                sanitize=False,
            )

        form_container = ui.column().classes("w-full gap-2 sm:gap-3")
        with form_container:
            length_unit = self.unit_system["length"]
            diameter_unit = self.unit_system["diameter"]
            roughness_unit = self.unit_system["roughness"]
            elevation_unit = self.unit_system["elevation"]

            # Basic properties
            name_input = ui.input("Name", value=pipe_config.name).classes("w-full")

            # Dimensions row - side by side on larger screens
            dimensions_row = ui.row().classes("w-full gap-2 flex-wrap sm:flex-nowrap")
            with dimensions_row:
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
                    on_click=lambda: self.save_pipe_form(
                        name=name_input.value,
                        length=length_input.value,
                        diameter=diameter_input.value,
                        direction=direction_select.value,
                        material=material_input.value,
                        efficiency=efficiency_input.value,
                        roughness=roughness_input.value,
                        elevation=elevation_input.value,
                        length_unit=length_unit.unit,
                        diameter_unit=diameter_unit.unit,
                        roughness_unit=roughness_unit.unit,
                        elevation_unit=elevation_unit.unit,
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

        # Show leak management section
        ui.separator().classes("my-4")
        self.show_leak_management_panel(self.selected_pipe_index)

        # Show valve management section
        ui.separator().classes("my-4")
        self.show_valve_management_panel(self.selected_pipe_index)

    def show_fluid_form(self):
        """Create form for editing fluid properties."""
        # Header with better styling
        fluid_header = ui.card().classes(
            f"w-full mb-3 bg-gradient-to-r from-{self.theme_color}-50 to-{self.theme_color}-100 border-l-4 border-{self.theme_color}-500"
        )
        with fluid_header:
            ui.label("Edit Fluid").classes(
                f"font-semibold text-{self.theme_color}-800 p-2"
            )
            ui.html(
                "<small class='text-gray-500'>Modify fluid properties below.</small>",
                sanitize=False,
            )

        fluid_config = self.manager.get_fluid_config()
        temp_unit = self.unit_system["temperature"]
        mol_weight_unit = self.unit_system["molecular_weight"]

        form_container = ui.column().classes("w-full gap-2 sm:gap-3")
        with form_container:
            # Name and phase row
            name_phase_row = ui.row().classes("w-full gap-2 flex-wrap sm:flex-nowrap")
            with name_phase_row:
                name_select = (
                    ui.select(
                        options=SUPPORTED_FLUIDS,
                        value=fluid_config.name,
                        multiple=False,
                        with_input=True,
                    )
                    .classes("flex-1 min-w-0")
                    .tooltip(
                        "Name of the fluid being transported (e.g., Water, Methane, Octane). Must be supported by `CoolProp`"
                    )
                )
                phase_select = (
                    ui.select(
                        options=["gas", "liquid"],
                        value=fluid_config.phase,
                        label="Phase",
                    )
                    .classes("flex-1 min-w-0")
                    .tooltip(
                        "Physical phase affects flow equations and property calculations"
                    )
                )

            # Temperature and pressure row
            temp_pressure_row = ui.row().classes(
                "w-full gap-2 flex-wrap sm:flex-nowrap"
            )
            with temp_pressure_row:
                temperature_input = (
                    ui.number(
                        f"Temperature ({temp_unit})",
                        value=fluid_config.temperature.to(temp_unit.unit).magnitude,
                        step=1,
                        precision=3,
                    )
                    .classes("flex-1 min-w-0")
                    .tooltip(
                        "Operating temperature of the fluid. Defaults to flowline temperature if not specified."
                    )
                )

            # Molecular weight and specific gravity row
            mol_gravity_row = ui.row().classes("w-full gap-2 flex-wrap sm:flex-nowrap")
            with mol_gravity_row:
                molecular_weight_input = (
                    ui.number(
                        f"Molecular Weight ({mol_weight_unit})",
                        value=fluid_config.molecular_weight.to(
                            mol_weight_unit.unit
                        ).magnitude,
                        min=0.1,
                        step=0.1,
                        precision=4,
                    )
                    .classes("flex-1 min-w-0")
                    .tooltip(
                        "Molecular weight of the fluid (Optional). Will be estimated if not provided."
                    )
                )

            ui.button(
                "Update Fluid",
                on_click=lambda: self.save_fluid_form(
                    name=name_select.value,
                    phase=phase_select.value,
                    temperature=temperature_input.value,
                    molecular_weight=molecular_weight_input.value,
                    temperature_unit=temp_unit.unit,
                    molecular_weight_unit=mol_weight_unit.unit,
                ),
                color=self.theme_color,
            ).classes(
                self.get_primary_button_classes("px-4 py-2 mt-3 w-full sm:w-auto")
            )

    def save_pipe_form(
        self,
        name: str,
        length: float,
        diameter: float,
        direction: str,
        material: str,
        efficiency: float,
        roughness: float,
        elevation: float,
        length_unit: str = "m",
        diameter_unit: str = "mm",
        roughness_unit: str = "mm",
        elevation_unit: str = "m",
    ):
        """
        Save pipe form data.

        :param name: Name of the pipe.
        :param length: Length of the pipe.
        :param diameter: Internal diameter of the pipe.
        :param direction: Flow direction of the pipe.
        :param material: Material of the pipe.
        :param efficiency: Efficiency of the pipe.
        :param roughness: Roughness of the pipe.
        :param elevation: Elevation difference of the pipe.
        :param length_unit: Unit for length.
        :param diameter_unit: Unit for diameter.
        :param roughness_unit: Unit for roughness.
        :param elevation_unit: Unit for elevation.
        """
        try:
            if self.selected_pipe_index is not None:
                selected_pipe_config = self.manager.get_pipe_configs()[
                    self.selected_pipe_index
                ]
                updated_config = PipeConfig(
                    name=name.strip() or selected_pipe_config.name,
                    length=Quantity(length, length_unit),  # type: ignore
                    internal_diameter=Quantity(diameter, diameter_unit),  # type: ignore
                    # Pressures remain unchanged as they manage by the pipeline and flowstations
                    upstream_pressure=selected_pipe_config.upstream_pressure,
                    downstream_pressure=selected_pipe_config.downstream_pressure,
                    direction=PipeDirection(direction),
                    material=material,
                    roughness=Quantity(roughness, roughness_unit),  # type: ignore
                    elevation_difference=Quantity(elevation, elevation_unit),  # type: ignore
                    efficiency=efficiency,
                    leaks=selected_pipe_config.leaks,
                    valves=selected_pipe_config.valves,  # Preserve valves
                    ambient_pressure=selected_pipe_config.ambient_pressure,
                )
                self.manager.update_pipe(self.selected_pipe_index, updated_config)

        except Exception as exc:
            logger.error(f"Error updating pipe: {exc}", exc_info=True)

    def save_fluid_form(
        self,
        name: str,
        phase: str,
        temperature: float,
        molecular_weight: float,
        temperature_unit: str,
        molecular_weight_unit: str,
    ):
        """
        Save fluid from form data.

        :param name: Name of the fluid.
        :param phase: Phase of the fluid ("gas" or "liquid").
        :param temperature: Temperature of the fluid.
        :param molecular_weight: Molecular weight of the fluid.
        :param temperature_unit: Unit for temperature.
        :param molecular_weight_unit: Unit for molecular weight.
        """
        try:
            updated_config = FluidConfig(
                name=name.strip() or "Methane",
                phase=phase,
                temperature=Quantity(temperature, temperature_unit),  # type: ignore
                molecular_weight=Quantity(
                    molecular_weight,
                    molecular_weight_unit,  # type: ignore
                ),
            )
            self.manager.set_fluid(updated_config)
        except Exception as exc:
            logger.error(f"Error updating fluid: {exc}", exc_info=True)

    def show_leak_management_panel(self, pipe_index: int) -> ui.column:
        """
        Show leak management panel for a specific pipe.

        :param pipe_index: Index of the pipe to manage leaks for.
        :return: The leak management panel container.
        """
        pipe_config = self.manager.get_pipe_configs()[pipe_index]

        # Main leak management container
        leak_panel = ui.column().classes("w-full gap-2 sm:gap-3")

        with leak_panel:
            # Header with pipe name and leak summary
            header_row = ui.row().classes("w-full items-center justify-between")
            with header_row:
                ui.label(f"Leaks in {pipe_config.name}").classes(
                    "text-lg font-semibold"
                )
                leak_count = len(pipe_config.leaks)
                ui.badge(
                    str(leak_count), color="red" if leak_count > 0 else "gray"
                ).classes("ml-2")

            # Action buttons
            action_row = ui.row().classes("w-full gap-2 flex-wrap sm:flex-nowrap")
            with action_row:
                ui.button(
                    "Add Leak",
                    icon="add",
                    color=self.theme_color,
                ).classes("flex-1").on(
                    "click", lambda: self.show_add_leak_dialog(pipe_index)
                ).tooltip("Add a new leak to this pipe")

                if leak_count > 0:
                    ui.button(
                        "Clear All",
                        icon="clear_all",
                        color="orange",
                    ).classes("flex-1").on(
                        "click", lambda: self.confirm_clear_all_leaks(pipe_index)
                    ).tooltip("Remove all leaks from this pipe")

            # Leak list
            if leak_count > 0:
                ui.separator()
                leak_list_container = ui.column().classes("w-full gap-2")
                with leak_list_container:
                    for leak_index, leak_config in enumerate(pipe_config.leaks):
                        self.show_leak_item(pipe_index, leak_index, leak_config)
            else:
                ui.label("No leaks in this pipe").classes(
                    "text-gray-500 text-center py-4 italic"
                )

        return leak_panel

    def show_leak_item(
        self, pipe_index: int, leak_index: int, leak_config: PipeLeakConfig
    ) -> None:
        """
        Show a single leak item with controls.

        :param pipe_index: Index of the pipe containing the leak.
        :param leak_index: Index of the leak.
        :param leak_config: The leak configuration.
        """
        leak_card = (
            ui.card()
            .classes("w-full p-2 sm:p-3 border-l-4")
            .style(
                f"border-left-color: {'#ef4444' if leak_config.active else '#6b7280'}"
            )
        )
        with leak_card:
            # Header row with leak info and status
            header_row = ui.row().classes("w-full items-center justify-between")
            with header_row:
                info_col = ui.column().classes("flex-1")
                with info_col:
                    leak_name = leak_config.name or f"Leak {leak_index + 1}"
                    ui.label(leak_name).classes("font-medium")

                    # Leak details
                    diameter_unit = self.unit_system["diameter"]
                    diameter_value = leak_config.diameter.to(
                        diameter_unit.unit
                    ).magnitude
                    location_percent = leak_config.location * 100

                    details_text = f"⌀{diameter_value:.1f}{diameter_unit.display} • {location_percent:.0f}% • Cd={leak_config.discharge_coefficient:.2f}"
                    ui.label(details_text).classes("text-xs text-gray-600")

                # Status and actions
                actions_col = ui.column().classes("items-end gap-1")
                with actions_col:
                    # Active status toggle
                    ui.chip(
                        "Active" if leak_config.active else "Inactive",
                        color="red" if leak_config.active else "gray",
                        icon="leak_add" if leak_config.active else "leak_remove",
                        on_click=lambda pipe_index=pipe_index,
                        leak_index=leak_index: self.toggle_pipe_leak(
                            pipe_index, leak_index
                        ),
                    ).classes("cursor-pointer")

                    # Action buttons
                    button_row = ui.row().classes("gap-1")
                    with button_row:
                        ui.button(
                            icon="edit",
                            color=self.theme_color,
                        ).props("size=sm").on(
                            "click",
                            lambda p=pipe_index,
                            leak_idx=leak_index,
                            cfg=leak_config: self.show_edit_leak_dialog(
                                p, leak_idx, cfg
                            ),
                        ).tooltip("Edit leak")

                        ui.button(
                            icon="delete",
                            color="red",
                        ).props("size=sm").on(
                            "click",
                            lambda p=pipe_index,
                            leak_idx=leak_index: self.confirm_leak_removal(p, leak_idx),
                        ).tooltip("Remove leak")

    def show_add_leak_dialog(self, pipe_index: int) -> None:
        """Show dialog to add a new leak to a pipe."""
        self.leak_edit_mode = False
        self.selected_pipe_index = pipe_index
        self.selected_leak_index = None

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
            pipe_name = self.manager.get_pipe_configs()[pipe_index].name
            ui.label(f"Add Leak to {pipe_name}").classes("text-lg font-semibold mb-3")
            self.show_leak_form(dialog)

    def show_edit_leak_dialog(
        self, pipe_index: int, leak_index: int, leak_config: PipeLeakConfig
    ) -> None:
        """Show dialog to edit an existing leak."""
        self.leak_edit_mode = True
        self.selected_pipe_index = pipe_index
        self.selected_leak_index = leak_index

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
            pipe_name = self.manager.get_pipe_configs()[pipe_index].name
            leak_name = leak_config.name or f"Leak {leak_index + 1}"
            ui.label(f"Edit {leak_name} in {pipe_name}").classes(
                "text-lg font-semibold mb-3"
            )
            self.show_leak_form(dialog, leak_config)

    def show_leak_form(
        self, dialog: ui.dialog, existing_leak: typing.Optional[PipeLeakConfig] = None
    ) -> None:
        """
        Show the leak form with input fields.

        :param dialog: The dialog containing the form.
        :param existing_leak: Existing leak config for editing, or None for new leak.
        """
        diameter_unit = self.unit_system["diameter"]

        # Default values
        if existing_leak:
            name_default = existing_leak.name or ""
            diameter_default = existing_leak.diameter.to(diameter_unit.unit).magnitude
            location_default = existing_leak.location
            cd_default = existing_leak.discharge_coefficient
            active_default = existing_leak.active
        else:
            name_default = ""
            diameter_default = 0.01
            location_default = 0.5  # Middle of pipe
            cd_default = 0.6  # Standard orifice coefficient
            active_default = True

        form_container = ui.column().classes("w-full gap-3")
        with form_container:
            # Leak name
            name_input = ui.input(
                "Leak Name (optional)",
                value=name_default,
                placeholder="e.g., Main Leak, Valve Leak",
            ).classes("w-full")

            # Diameter
            diameter_input = (
                ui.number(
                    f"Leak Diameter ({diameter_unit.display})",
                    value=diameter_default,
                    min=0.0,
                    max=100,
                    step=0.1,
                    format="%.6f",
                )
                .classes("w-full")
                .tooltip("Physical diameter of the leak opening")
            )

            # Location
            location_input = (
                ui.number(
                    "Location (fraction of pipe length)",
                    value=location_default,
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    format="%.2f",
                )
                .classes("w-full")
                .tooltip("0.0 = start of pipe, 1.0 = end of pipe")
            )

            # Location as percentage display
            location_percent_label = ui.label().classes("text-xs text-gray-600")

            def update_location_display():
                percent = (
                    location_input.value * 100
                    if location_input.value is not None
                    else 0
                )
                location_percent_label.text = f"({percent:.0f}% along pipe)"
                location_percent_label.update()

            location_input.on("input", lambda e: update_location_display())
            update_location_display()

            # Discharge coefficient
            cd_input = (
                ui.number(
                    "Discharge Coefficient",
                    value=cd_default,
                    min=0.001,
                    max=1.0,
                    step=0.01,
                    format="%.6f",
                )
                .classes("w-full")
                .tooltip("Flow coefficient for the orifice (0.6 is typical)")
            )

            # Active status
            active_switch = ui.switch("Active", value=active_default).classes("mb-2")

            # Action buttons
            button_row = ui.row().classes("w-full justify-end gap-2 mt-4")
            with button_row:
                ui.button("Cancel", color="gray").on("click", dialog.close)

                ui.button(
                    "Update" if existing_leak else "Add",
                    color=self.theme_color,
                ).on(
                    "click",
                    lambda: self.save_leak_form(
                        dialog=dialog,
                        name=name_input.value,
                        diameter=diameter_input.value,
                        location=location_input.value,
                        discharge_coefficient=cd_input.value,
                        active=active_switch.value,
                        diameter_unit=diameter_unit.unit,
                    ),
                )

        dialog.open()

    def save_leak_form(
        self,
        dialog: ui.dialog,
        name: str,
        diameter: float,
        location: float,
        discharge_coefficient: float,
        active: bool,
        diameter_unit: str = "mm",
    ) -> None:
        """
        Save the leak form data.

        :param dialog: The dialog instance to close after saving.
        :param name: Name of the leak.
        :param diameter: Diameter of the leak.
        :param location: Location of the leak as a fraction of pipe length (0.0 to 1.0).
        :param discharge_coefficient: Discharge coefficient of the leak (0.1 to 1.0).
        :param active: Whether the leak is active.
        :param diameter_unit: Unit for diameter.
        """
        try:
            # Validation
            if diameter <= 0:
                ui.notify("Leak diameter must be positive", type="negative")
                return

            if not (0.0 <= location <= 1.0):
                ui.notify("Location must be between 0.0 and 1.0", type="negative")
                return

            if not (0.1 <= discharge_coefficient <= 1.0):
                ui.notify(
                    "Discharge coefficient must be between 0.1 and 1.0", type="negative"
                )
                return

            leak_config = PipeLeakConfig(
                name=name if name.strip() else None,
                diameter=Quantity(diameter, diameter_unit),
                location=location,
                discharge_coefficient=discharge_coefficient,
                active=active,
            )
            # Add or update leak
            if self.leak_edit_mode and self.selected_leak_index is not None:
                self.manager.update_pipe_leak(
                    self.selected_pipe_index,
                    self.selected_leak_index,
                    leak_config,
                )
            else:
                self.manager.add_pipe_leak(self.selected_pipe_index, leak_config)
            dialog.close()

        except Exception as exc:
            ui.notify(f"Error saving leak: {str(exc)}", type="negative")
            logger.error(f"Error saving leak: {exc}", exc_info=True)

    def toggle_pipe_leak(self, pipe_index: int, leak_index: int) -> None:
        """Toggle the active status of a leak."""
        try:
            self.manager.toggle_leak(pipe_index, leak_index)
        except Exception as exc:
            ui.notify(f"Error toggling leak status: {str(exc)}", type="negative")
            logger.error(f"Error toggling leak status: {exc}", exc_info=True)

    def confirm_leak_removal(self, pipe_index: int, leak_index: int) -> None:
        """Show confirmation dialog for removing a leak."""
        pipe_config = self.manager.get_pipe_configs()[pipe_index]
        leak_config = pipe_config.leaks[leak_index]
        leak_name = leak_config.name or f"Leak {leak_index + 1}"

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-sm"):
            ui.label(f"Remove {leak_name}?").classes("text-lg font-semibold mb-3")
            ui.label(
                f"This will permanently remove the leak from {pipe_config.name}."
            ).classes("text-gray-600 mb-4")

            button_row = ui.row().classes("w-full justify-end gap-2")
            with button_row:
                ui.button("Cancel", color="gray").on("click", dialog.close)
                ui.button("Remove", color="red").on(
                    "click",
                    lambda: (
                        self.manager.remove_pipe_leak(pipe_index, leak_index),
                        dialog.close(),
                    ),
                )

        dialog.open()

    def confirm_clear_all_leaks(self, pipe_index: int) -> None:
        """Show confirmation dialog for clearing all leaks from a pipe."""
        pipe_config = self.manager.get_pipe_configs()[pipe_index]
        leak_count = len(pipe_config.leaks)

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-sm"):
            ui.label("Clear All Leaks?").classes("text-lg font-semibold mb-3")
            ui.label(
                f"This will remove all {leak_count} leaks from {pipe_config.name}."
            ).classes("text-gray-600 mb-4")

            button_row = ui.row().classes("w-full justify-end gap-2")
            with button_row:
                ui.button("Cancel", color="gray").on("click", dialog.close)
                ui.button("Clear All", color="red").on(
                    "click",
                    lambda: (self.manager.clear_pipe_leaks(pipe_index), dialog.close()),
                )
        dialog.open()

    def show_pipeline_leak_summary(self) -> ui.column:
        """Show a summary of all leaks in the pipeline."""
        summary_container = ui.column().classes("w-full gap-2")

        with summary_container:
            # Header
            header_row = ui.row().classes("w-full items-center justify-between")
            with header_row:
                ui.label("Leaks").classes("text-lg font-semibold")

                total_leaks = self.manager.get_leak_count()
                if total_leaks > 0:
                    ui.button(
                        "Clear All Leaks",
                        icon="clear_all",
                        color="red",
                    ).props("size=sm").on(
                        "click", self.confirm_clear_all_pipeline_leaks
                    ).tooltip("Remove all leaks from the entire flowline")

            # Summary cards
            if total_leaks > 0:
                all_leaks = self.manager.get_all_leaks()

                for pipe_index, leak_configs in all_leaks.items():
                    pipe_config = self.manager.get_pipe_configs()[pipe_index]
                    active_leaks = sum(1 for leak in leak_configs if leak.active)

                    leak_summary_card = (
                        ui.card()
                        .classes("w-full p-2 border-l-4")
                        .style(
                            f"border-left-color: {'#ef4444' if active_leaks > 0 else '#6b7280'}"
                        )
                    )

                    with leak_summary_card:
                        summary_row = ui.row().classes(
                            "w-full items-center justify-between"
                        )
                        with summary_row:
                            ui.label(pipe_config.name).classes("font-medium")
                            ui.label(
                                f"{active_leaks}/{len(leak_configs)} active"
                            ).classes("text-sm text-gray-600")

                        distances_row = ui.row().classes("w-full flex-wrap gap-2 mt-1")
                        with distances_row:
                            for leak_config in leak_configs:
                                location_percent = leak_config.location * 100
                                location_length = (
                                    pipe_config.length.to(
                                        self.unit_system["length"].unit
                                    ).magnitude
                                    * leak_config.location
                                )
                                diameter_value = leak_config.diameter.to(
                                    self.unit_system["diameter"].unit
                                ).magnitude
                                status_color = "red" if leak_config.active else "gray"
                                ui.chip(
                                    f"⌀ {diameter_value:.6f}{self.unit_system['diameter'].display} @ {location_length:.4f}{self.unit_system['length'].display} ({location_percent:.1f}%)",
                                    color=status_color,
                                    icon="leak_add"
                                    if leak_config.active
                                    else "leak_remove",
                                    on_click=lambda pipe_index=pipe_index,
                                    leak=leak_config: self.toggle_pipe_leak(
                                        pipe_index,
                                        pipe_config.leaks.index(leak),
                                    ),
                                )
            else:
                ui.label("No leaks in pipeline").classes(
                    "text-gray-500 text-center py-4 italic"
                )

        return summary_container

    def confirm_clear_all_pipeline_leaks(self) -> None:
        """Show confirmation dialog for clearing all leaks from the entire pipeline."""
        total_leaks = self.manager.get_leak_count()

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-sm"):
            ui.label("Clear All Pipeline Leaks?").classes("text-lg font-semibold mb-3")
            ui.label(
                f"This will remove all {total_leaks} leaks from the entire pipeline."
            ).classes("text-gray-600 mb-4")

            button_row = ui.row().classes("w-full justify-end gap-2")
            with button_row:
                ui.button("Cancel", color="gray").on("click", dialog.close)
                ui.button("Clear All", color="red").on(
                    "click",
                    lambda: (self.manager.clear_all_leaks(), dialog.close()),
                )

        dialog.open()

    def show_pipeline_valves_summary(self) -> ui.column:
        """Show a summary of all valves in the pipeline."""
        summary_container = ui.column().classes("w-full gap-2")

        with summary_container:
            # Header
            header_row = ui.row().classes("w-full items-center justify-between")
            with header_row:
                ui.label("Valves").classes("text-lg font-semibold")

                total_valves = self.manager.get_valve_count()
                ui.badge(
                    str(total_valves), color="green" if total_valves > 0 else "gray"
                ).classes("ml-2")

            # Summary cards
            if total_valves > 0:
                pipeline = self.manager.get_pipeline()
                pipe_configs = self.manager.get_pipe_configs()

                for pipe_index, pipe_config in enumerate(pipe_configs):
                    if pipeline and pipe_index < len(pipeline.pipes):
                        pipe = pipeline.pipes[pipe_index]
                        start_valve = pipe._start_valve
                        end_valve = pipe._end_valve

                        if start_valve or end_valve:
                            valve_count = (1 if start_valve else 0) + (
                                1 if end_valve else 0
                            )
                            open_count = sum(
                                [
                                    1 if start_valve and start_valve.is_open() else 0,
                                    1 if end_valve and end_valve.is_open() else 0,
                                ]
                            )

                            valve_summary_card = (
                                ui.card()
                                .classes("w-full p-2 border-l-4")
                                .style(
                                    f"border-left-color: {'#10b981' if open_count > 0 else '#6b7280'}"
                                )
                            )

                            with valve_summary_card:
                                summary_row = ui.row().classes(
                                    "w-full items-center justify-between"
                                )
                                with summary_row:
                                    ui.label(pipe_config.name).classes("font-medium")
                                    ui.label(
                                        f"{open_count}/{valve_count} open"
                                    ).classes("text-sm text-gray-600")

                                valves_row = ui.row().classes(
                                    "w-full flex-wrap gap-2 mt-1"
                                )
                                with valves_row:
                                    if start_valve:
                                        status_color = (
                                            "green" if start_valve.is_open() else "red"
                                        )
                                        status_text = (
                                            "OPEN"
                                            if start_valve.is_open()
                                            else "CLOSED"
                                        )
                                        ui.chip(
                                            f"Start Valve: {status_text}",
                                            color=status_color,
                                            icon="toggle_on"
                                            if start_valve.is_open()
                                            else "toggle_off",
                                            on_click=lambda pi=pipe_index: self.toggle_valve(
                                                pi, "start"
                                            ),
                                        ).tooltip("Click to toggle")

                                    if end_valve:
                                        status_color = (
                                            "green" if end_valve.is_open() else "red"
                                        )
                                        status_text = (
                                            "OPEN" if end_valve.is_open() else "CLOSED"
                                        )
                                        ui.chip(
                                            f"End Valve: {status_text}",
                                            color=status_color,
                                            icon="toggle_on"
                                            if end_valve.is_open()
                                            else "toggle_off",
                                            on_click=lambda pi=pipe_index: self.toggle_valve(
                                                pi, "end"
                                            ),
                                        ).tooltip("Click to toggle")
            else:
                ui.label("No valves in pipeline").classes(
                    "text-gray-500 text-center py-4 italic"
                )

        return summary_container

    def show_valve_management_panel(self, pipe_index: int) -> ui.column:
        """
        Show valve management panel for a specific pipe.

        :param pipe_index: Index of the pipe to manage valves for.
        :return: The valve management panel container.
        """
        pipe_config = self.manager.get_pipe_configs()[pipe_index]
        pipeline = self.manager.get_pipeline()

        # Get valve status from the actual pipe in the pipeline
        start_valve = None
        end_valve = None
        previous_pipe_has_end_valve = False

        if pipeline and pipe_index < len(pipeline.pipes):
            pipe = pipeline.pipes[pipe_index]
            start_valve = pipe._start_valve
            end_valve = pipe._end_valve

            # Check if previous pipe has an end valve
            if pipe_index > 0:
                previous_pipe = pipeline.pipes[pipe_index - 1]
                previous_pipe_has_end_valve = previous_pipe._end_valve is not None

        # Main valve management container
        valve_panel = ui.column().classes("w-full gap-2 sm:gap-3")

        with valve_panel:
            # Header
            header_row = ui.row().classes("w-full items-center justify-between")
            with header_row:
                ui.label(f"Valves in {pipe_config.name}").classes(
                    "text-lg font-semibold"
                )
                valve_count = (1 if start_valve else 0) + (1 if end_valve else 0)
                ui.badge(
                    str(valve_count), color="green" if valve_count > 0 else "gray"
                ).classes("ml-2")

            # Start Valve Section - Hide if previous pipe has end valve
            if not previous_pipe_has_end_valve:
                start_valve_card = (
                    ui.card()
                    .classes("w-full p-3 border-l-4")
                    .style(
                        f"border-left-color: {'#10b981' if start_valve and start_valve.is_open() else '#6b7280' if start_valve else '#d1d5db'}"
                    )
                )
                with start_valve_card:
                    valve_row = ui.row().classes("w-full items-center justify-between")
                    with valve_row:
                        info_col = ui.column().classes("flex-1")
                        with info_col:
                            ui.label("Start Valve").classes("font-medium")
                            if start_valve:
                                status_text = (
                                    "OPEN" if start_valve.is_open() else "CLOSED"
                                )
                                status_color = (
                                    "green" if start_valve.is_open() else "red"
                                )
                                ui.label(f"Status: {status_text}").classes(
                                    f"text-xs text-{status_color}-600 font-semibold"
                                )
                            else:
                                ui.label("No valve installed").classes(
                                    "text-xs text-gray-500 italic"
                                )

                        # Action buttons
                        actions_col = ui.row().classes("gap-1")
                        with actions_col:
                            if start_valve:
                                # Toggle button
                                toggle_btn = (
                                    ui.button(
                                        icon="toggle_on"
                                        if start_valve.is_open()
                                        else "toggle_off",
                                        color="green"
                                        if start_valve.is_open()
                                        else "red",
                                    )
                                    .props("size=sm")
                                    .tooltip(
                                        "Close valve"
                                        if start_valve.is_open()
                                        else "Open valve"
                                    )
                                )
                                toggle_btn.on(
                                    "click",
                                    lambda: self.toggle_valve(pipe_index, "start"),
                                )

                                # Remove button
                                ui.button(
                                    icon="delete",
                                    color="orange",
                                ).props("size=sm").on(
                                    "click",
                                    lambda: self.remove_valve(pipe_index, "start"),
                                ).tooltip("Remove valve")
                            else:
                                # Add button
                                ui.button(
                                    icon="add",
                                    color=self.theme_color,
                                ).props("size=sm").on(
                                    "click", lambda: self.add_valve(pipe_index, "start")
                                ).tooltip("Add start valve")

            # End Valve Section
            end_valve_card = (
                ui.card()
                .classes("w-full p-3 border-l-4 mt-2")
                .style(
                    f"border-left-color: {'#10b981' if end_valve and end_valve.is_open() else '#6b7280' if end_valve else '#d1d5db'}"
                )
            )
            with end_valve_card:
                valve_row = ui.row().classes("w-full items-center justify-between")
                with valve_row:
                    info_col = ui.column().classes("flex-1")
                    with info_col:
                        ui.label("End Valve").classes("font-medium")
                        if end_valve:
                            status_text = "OPEN" if end_valve.is_open() else "CLOSED"
                            status_color = "green" if end_valve.is_open() else "red"
                            ui.label(f"Status: {status_text}").classes(
                                f"text-xs text-{status_color}-600 font-semibold"
                            )
                        else:
                            ui.label("No valve installed").classes(
                                "text-xs text-gray-500 italic"
                            )

                    # Action buttons
                    actions_col = ui.row().classes("gap-1")
                    with actions_col:
                        if end_valve:
                            # Toggle button
                            toggle_btn = (
                                ui.button(
                                    icon="toggle_on"
                                    if end_valve.is_open()
                                    else "toggle_off",
                                    color="green" if end_valve.is_open() else "red",
                                )
                                .props("size=sm")
                                .tooltip(
                                    "Close valve"
                                    if end_valve.is_open()
                                    else "Open valve"
                                )
                            )
                            toggle_btn.on(
                                "click",
                                lambda: self.toggle_valve(pipe_index, "end"),
                            )

                            # Remove button
                            ui.button(
                                icon="delete",
                                color="orange",
                            ).props("size=sm").on(
                                "click", lambda: self.remove_valve(pipe_index, "end")
                            ).tooltip("Remove valve")
                        else:
                            # Add button
                            ui.button(
                                icon="add",
                                color=self.theme_color,
                            ).props("size=sm").on(
                                "click", lambda: self.add_valve(pipe_index, "end")
                            ).tooltip("Add end valve")

        return valve_panel

    def add_valve(
        self, pipe_index: int, position: typing.Literal["start", "end"]
    ) -> None:
        """Add a valve to a pipe."""
        try:
            self.manager.add_valve(pipe_index, position=position)
        except Exception as exc:
            ui.notify(
                f"Failed to add valve: {exc}",
                type="negative",
                position="top",
            )
            logger.error(f"Failed to add valve: {exc}", exc_info=True)

    def remove_valve(
        self, pipe_index: int, position: typing.Literal["start", "end"]
    ) -> None:
        """Remove a valve from a pipe."""
        try:
            self.manager.remove_valve(pipe_index, position=position)
        except Exception as exc:
            ui.notify(
                f"Failed to remove valve: {exc}",
                type="negative",
                position="top",
            )
            logger.error(f"Failed to remove valve: {exc}", exc_info=True)

    def toggle_valve(
        self, pipe_index: int, position: typing.Literal["start", "end"]
    ) -> None:
        """Toggle a valve's state."""
        try:
            self.manager.toggle_valve(pipe_index, position=position)
        except Exception as exc:
            ui.notify(
                f"Failed to toggle valve: {exc}",
                type="negative",
                position="top",
            )
            logger.error(f"Failed to toggle valve: {exc}", exc_info=True)

    def clear_pipe_selection(self):
        """Clear pipe selection and return to fluid properties."""
        self.selected_pipe_index = None
        self.refresh_properties_panel()

    def export_pipe_configuration(self):
        """Export the current pipe configuration to a JSON file."""
        try:
            config_json = self.manager.export_configuration()

            # Generate filename with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pipeline_config_{timestamp}.json"

            ui.download(config_json.encode(), filename=filename)
            ui.notify(
                f"Configuration exported to {filename}",
                type="positive",
                icon="file_download",
            )
            logger.info(f"Exported pipeline configuration to {filename}")

        except Exception as exc:
            error_msg = f"Failed to export configuration: {exc}"
            ui.notify(error_msg, type="negative", icon="error")
            logger.error(error_msg, exc_info=True)

    async def import_pipe_configuration(self, event):
        """Import pipe configuration from an uploaded JSON file."""
        try:
            # Read the uploaded file content
            # NiceGUI's upload event provides the file via event.file
            content = await event.file.read()

            # Decode if bytes
            if isinstance(content, bytes):
                content = content.decode("utf-8")

            # Import the configuration
            self.manager.import_configuration(content)

            # Refresh all UI panels
            self.refresh_pipes_list()
            self.refresh_properties_panel()
            self.refresh_pipeline_preview()
            self.refresh_flow_stations()

            ui.notify(
                "Configuration imported successfully",
                type="positive",
                icon="file_upload",
            )
            logger.info("Successfully imported pipeline configuration")

        except ValueError as exc:
            error_msg = f"Invalid configuration file: {exc}"
            ui.notify(error_msg, type="negative", icon="error")
            logger.error(error_msg, exc_info=True)

        except Exception as exc:
            error_msg = f"Failed to import configuration: {exc}"
            ui.notify(error_msg, type="negative", icon="error")
            logger.error(f"Failed to import configuration: {exc}", exc_info=True)

    def __del__(self):
        """Cleanup when the UI is destroyed."""
        self.cleanup()
