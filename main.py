"""
Main Entry Point for SCADA Pipeline Management System Application.
"""

import logging
from nicegui import ui, app

from src.properties import FlowType
from src.ui.manager import (
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(name)s:%(funcName)s:%(lineno)d] - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def build_application(min_width: int = 800, max_width: int = 1440):
    """Create the main SCADA Pipeline Management System application."""

    # Main layout container
    main_container = (
        ui.column()
        .classes("w-full h-screen bg-gray-50")
        .style(
            f"max-width: {max_width}px; min-width: minmax({min_width}px, 100%); margin: auto;"
        )
    )

    with main_container:
        # Header
        header = ui.row().classes(
            "w-full bg-green-600 text-white p-4 shadow-lg items-center"
        )
        with header:
            ui.icon("engineering").classes("text-3xl mr-3")
            ui.label("SCADA Pipeline Management System").classes(
                "text-2xl font-bold flex-1 sm:text-lg"
            )

        # Main content area with the pipeline builder
        content_area = ui.column().classes("flex-1 w-full overflow-auto p-1")

        with content_area:
            welcome_card = ui.card().classes(
                "w-full p-4 mb-4 bg-gradient-to-r from-blue-50 to-indigo-50 border-l-4 border-blue-500"
            )
            with welcome_card:
                ui.label("Pipeline Builder").classes(
                    "text-xl font-semibold text-blue-800 mb-2"
                )
                ui.label(
                    "Design, configure, and monitor industrial pipelines with real-time validation and automatic instrumentation."
                ).classes("text-blue-700")

            # Pipeline manager interface
            pipeline_manager_container = ui.column().classes("w-full")
            with pipeline_manager_container:
                initial_fluid = Fluid.from_coolprop(
                    fluid_name="Methane",
                    phase="gas",
                    temperature=Quantity(60, "degF"),
                    pressure=Quantity(100, "psi"),
                    molecular_weight=Quantity(16.04, "g/mol"),
                )

                pipeline = Pipeline(
                    pipes=[],
                    fluid=initial_fluid,
                    name="Main Pipeline",
                    max_flow_rate=Quantity(1e6, "MSCF/day"),
                    flow_type=FlowType.COMPRESSIBLE,
                    scale_factor=0.1,
                    connector_length=Quantity(0.1, "m"),
                    alert_errors=True,
                )

                upstream_config = FlowStationConfig(
                    station_name="Upstream Station",
                    station_type="upstream",
                    pressure_unit="psi",
                    temperature_unit="degF",
                    flow_unit="MSCF/day",
                    pressure_config=MeterConfig(
                        label="Upstream Pressure",
                        units="PSI",
                        max_value=2000.0,
                        height="180px",
                        precision=3,
                    ),
                    temperature_config=MeterConfig(
                        label="Upstream Temperature",
                        units="°F",
                        min_value=-40.0,
                        max_value=200.0,
                        width="160px",
                        height="240px",
                        precision=2,
                    ),
                    flow_config=MeterConfig(
                        label="Upstream Flow",
                        units="MSCF/DAY",
                        max_value=1e9,
                        height="220px",
                        precision=4,
                    ),
                    pressure_regulator_config=RegulatorConfig(
                        label="Upstream Pressure Control",
                        units="PSI",
                        max_value=2000.0,
                        precision=3,
                    ),
                    temperature_regulator_config=RegulatorConfig(
                        label="Upstream Temperature Control",
                        units="°F",
                        min_value=-40.0,
                        max_value=200.0,
                        precision=2,
                    ),
                )

                downstream_config = FlowStationConfig(
                    station_name="Downstream Station",
                    station_type="downstream",
                    pressure_unit="psi",
                    temperature_unit="degF",
                    flow_unit="MSCF/day",
                    pressure_config=MeterConfig(
                        label="Downstream Pressure",
                        units="PSI",
                        max_value=2000.0,
                        height="180px",
                        precision=3,
                    ),
                    temperature_config=MeterConfig(
                        label="Downstream Temperature",
                        units="°F",
                        min_value=-40.0,
                        max_value=200.0,
                        width="160px",
                        height="240px",
                        precision=2,
                    ),
                    flow_config=MeterConfig(
                        label="Downstream Flow",
                        units="MSCF/DAY",
                        max_value=1e9,
                        height="220px",
                        precision=4,
                    ),
                    pressure_regulator_config=RegulatorConfig(
                        label="Downstream Pressure Control",
                        units="PSI",
                        max_value=2000.0,
                        precision=3,
                    ),
                )

                upstream_factory = UpstreamStationFactory(upstream_config)
                downstream_factory = DownstreamStationFactory(downstream_config)
                manager = PipelineManager(
                    pipeline,
                    flow_station_factories=[upstream_factory, downstream_factory],
                )
                manager_ui = PipelineManagerUI(manager)
                manager_ui.show(theme_color="green", max_width="95%")

    return main_container


def main():
    """Main application entry point."""
    logger.info("Starting SCADA Pipeline Management System")

    try:
        app.add_static_files("/static", "static")  # Add static file serving if needed
    except Exception:
        pass  # Static files directory might not exist

    build_application()

    logger.info("Application initialized successfully")
    ui.run(
        title="SCADA Pipeline Management System",
        port=8080,
        host="0.0.0.0",
        reload=True,
        show=True,
        favicon="🔧",
        dark=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
