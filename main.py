"""
Main Entry Point for SCADA Pipeline Management System Application.
"""

import logging
import os
import uuid
from pathlib import Path
from nicegui import ui, app, context

from src.properties import FlowType
from src.ui.manage import (
    PipelineManagerUI,
    PipelineManager,
    UpstreamStationFactory,
    DownstreamStationFactory,
    FlowStationConfig,
    MeterConfig,
    RegulatorConfig,
)
from src.ui.components import Pipeline, Fluid
from src.units import Quantity
from src.config.manage import (
    ConfigurationManager,
    ConfigurationState,
    JSONFileStorage,
    SessionStorage,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(name)s:%(funcName)s:%(lineno)d] - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@ui.page("/", title="SCADA Pipeline Management System")
def main_page():
    """Create the main SCADA Pipeline Management System application."""

    # Get unique session ID for this user
    # Option 1: Use client ID from context (if available)
    try:
        session_id = context.client.id
    except (AttributeError, RuntimeError):
        # Option 2: Generate or retrieve from storage
        if "session_id" not in app.storage.user:
            app.storage.user["session_id"] = str(uuid.uuid4())
        session_id = app.storage.user["session_id"]

    logger.info(f"User session ID: {session_id}")

    session_storage = SessionStorage(app, session_key="pipeline-scada")
    file_storage = JSONFileStorage(Path.cwd() / ".pipeline-scada")
    config_manager = ConfigurationManager(
        session_id, storages=[session_storage, file_storage]
    )
    # Get current configuration
    config = config_manager.get_config()
    theme_color = config.global_config.theme_color

    # Main layout container
    main_container = (
        ui.column()
        .classes("w-full h-screen bg-gray-50")
        .style(
            "max-width: 1440px; min-width: minmax(800px, 100%); margin: auto; scrollbar-width: thin; scrollbar-color: #cbd5e1 transparent;"
        )
    )
    with main_container:
        # Header with dynamic theme color
        header = ui.row().classes(
            f"w-full bg-{theme_color}-600 text-white p-4 shadow-lg items-center"
        )
        with header:
            ui.icon("engineering").classes("text-3xl mr-3")
            ui.label("SCADA Pipeline Management System").classes(
                "text-2xl font-bold flex-1 sm:text-lg"
            )

        def on_theme_change(config: ConfigurationState) -> None:
            """Handle theme color changes."""
            nonlocal theme_color

            new_theme = config.global_config.theme_color
            header.classes(remove=f"bg-{theme_color}-600")
            header.classes(add=f"bg-{new_theme}-600")
            theme_color = new_theme
            logger.info(f"Theme changed to: {new_theme}")

        config_manager.add_observer(on_theme_change)

        # Main content area with the pipeline builder
        content_area = ui.column().classes("flex-1 w-full overflow-auto p-1")

        with content_area:
            # Pipeline manager interface
            pipeline_manager_container = ui.column().classes("w-full")
            with pipeline_manager_container:
                pipeline_config = config.pipeline_config
                flow_station_defaults = config.flow_station_defaults

                fluid_phase = (
                    "gas" if pipeline_config.default_fluid_phase == "gas" else "liquid"
                )

                initial_fluid = Fluid.from_coolprop(
                    fluid_name=pipeline_config.default_fluid_name,
                    phase=fluid_phase,
                    temperature=Quantity(
                        pipeline_config.initial_temperature,
                        pipeline_config.initial_temperature_unit,
                    ),
                    pressure=Quantity(
                        pipeline_config.initial_pressure,
                        pipeline_config.initial_pressure_unit,
                    ),
                    molecular_weight=Quantity(
                        pipeline_config.molecular_weight,
                        pipeline_config.molecular_weight_unit,
                    ),
                )

                flow_type = FlowType(pipeline_config.flow_type)
                pipeline = Pipeline(
                    pipes=[],
                    fluid=initial_fluid,
                    name=pipeline_config.pipeline_name,
                    max_flow_rate=Quantity(
                        pipeline_config.max_flow_rate,
                        pipeline_config.max_flow_rate_unit,
                    ),
                    flow_type=flow_type,
                    scale_factor=pipeline_config.scale_factor,
                    connector_length=Quantity(pipeline_config.connector_length, "m"),
                    alert_errors=pipeline_config.alert_errors,
                )

                # Get configuration defaults
                meter_config = config.default_meter_config
                regulator_config = config.default_regulator_config

                upstream_config = FlowStationConfig(
                    station_name=flow_station_defaults.upstream_station_name,
                    station_type="upstream",
                    pressure_unit=flow_station_defaults.pressure_unit,
                    temperature_unit=flow_station_defaults.temperature_unit,
                    flow_unit=flow_station_defaults.flow_unit,
                    pressure_config=MeterConfig(
                        label="Upstream Pressure",
                        units=meter_config.pressure_units,
                        max_value=meter_config.pressure_max_value,
                        height=meter_config.pressure_height,
                        precision=meter_config.precision,
                    ),
                    temperature_config=MeterConfig(
                        label="Upstream Temperature",
                        units=meter_config.temperature_units,
                        min_value=meter_config.temperature_min_value,
                        max_value=meter_config.temperature_max_value,
                        width=meter_config.temperature_width,
                        height=meter_config.temperature_height,
                        precision=meter_config.temperature_precision,
                    ),
                    flow_config=MeterConfig(
                        label="Upstream Flow",
                        units=meter_config.flow_units,
                        max_value=meter_config.flow_max_value,
                        height=meter_config.flow_height,
                        precision=meter_config.flow_precision,
                    ),
                    pressure_regulator_config=RegulatorConfig(
                        label="Upstream Pressure Control",
                        units=regulator_config.pressure_units,
                        max_value=regulator_config.pressure_max_value,
                        precision=regulator_config.precision,
                    ),
                    temperature_regulator_config=RegulatorConfig(
                        label="Upstream Temperature Control",
                        units=regulator_config.temperature_units,
                        min_value=regulator_config.temperature_min_value,
                        max_value=regulator_config.temperature_max_value,
                        precision=regulator_config.precision,
                    ),
                )

                downstream_config = FlowStationConfig(
                    station_name=flow_station_defaults.downstream_station_name,
                    station_type="downstream",
                    pressure_unit=flow_station_defaults.pressure_unit,
                    temperature_unit=flow_station_defaults.temperature_unit,
                    flow_unit=flow_station_defaults.flow_unit,
                    pressure_config=MeterConfig(
                        label="Downstream Pressure",
                        units=meter_config.pressure_units,
                        max_value=meter_config.pressure_max_value,
                        height=meter_config.pressure_height,
                        precision=meter_config.precision,
                    ),
                    temperature_config=MeterConfig(
                        label="Downstream Temperature",
                        units=meter_config.temperature_units,
                        min_value=meter_config.temperature_min_value,
                        max_value=meter_config.temperature_max_value,
                        width=meter_config.temperature_width,
                        height=meter_config.temperature_height,
                        precision=meter_config.temperature_precision,
                    ),
                    flow_config=MeterConfig(
                        label="Downstream Flow",
                        units=meter_config.flow_units,
                        max_value=meter_config.flow_max_value,
                        height=meter_config.flow_height,
                        precision=meter_config.flow_precision,
                    ),
                    pressure_regulator_config=RegulatorConfig(
                        label="Downstream Pressure Control",
                        units=regulator_config.pressure_units,
                        max_value=regulator_config.pressure_max_value,
                        precision=regulator_config.precision,
                    ),
                )

                upstream_factory = UpstreamStationFactory(upstream_config)
                downstream_factory = DownstreamStationFactory(downstream_config)
                pipeline_manager = PipelineManager(
                    pipeline,
                    flow_station_factories=[upstream_factory, downstream_factory],
                )

                # Get the active unit system
                unit_system_name = config.global_config.unit_system_name
                logger.info(f"Using unit system: {unit_system_name}")
                manager_ui = PipelineManagerUI(
                    manager=pipeline_manager,
                    config=config_manager,
                    theme_color=theme_color,
                    unit_system=config_manager.get_unit_system(),
                )
                manager_ui.show(ui_label="Pipeline Builder", max_width="95%")

    return main_container


def main():
    """Main application entry point."""
    logger.info("Starting SCADA Pipeline Management System")
    ui.run(
        title="SCADA Pipeline Management System",
        port=8080,
        host="0.0.0.0",
        reload=True,
        show=True,
        favicon="🔧",
        dark=False,
        storage_secret=os.getenv("NICEGUI_STORAGE_SECRET", "42d56f76g78h91j94i124u"),
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
