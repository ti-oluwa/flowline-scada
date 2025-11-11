"""
Main Entry Point for Flowline Simulation Application.
"""

import hashlib
import logging
import os
import typing
import redis
import fastapi
from pathlib import Path
from fastapi.staticfiles import StaticFiles

from dotenv import find_dotenv, load_dotenv
from nicegui import Client, ui

from src.config import ConfigurationState, Configuration
from src.storages import JSONFileStorage, RedisStorage
from src.flow import FlowType, Fluid
from src.pipeline.core import Pipeline
from src.pipeline.manage import (
    DownstreamStationFactory,
    PipelineManager,
    PipelineManagerUI,
    UpstreamStationFactory,
)
from src.units import Quantity

load_dotenv(
    find_dotenv(Path.cwd() / ".env", raise_error_if_not_found=False), encoding="utf-8"
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - [%(name)s:%(funcName)s:%(lineno)d] - %(levelname)s - %(message)s",
    force=True,
)

logger = logging.getLogger(__name__)


redis_available = False
if redis_url := os.getenv("REDIS_URL"):
    try:
        redis_client = redis.Redis.from_url(redis_url)
        redis_client.ping()
        config_storage = RedisStorage(redis_client, namespace="config")
        state_storage = RedisStorage(redis_client, namespace="state")
        redis_available = True
        logger.info("Using `RedisStorage` for config and state storage")
    except redis.RedisError as exc:
        logger.error(
            f"Failed to connect to Redis: {exc}, falling back to file storage",
            exc_info=True,
        )
        redis_available = False

if not redis_available:
    config_storage = JSONFileStorage(
        storage_dir=Path.cwd() / ".pipeline-scada/configs", namespace="config"
    )
    state_storage = JSONFileStorage(
        storage_dir=Path.cwd() / ".pipeline-scada/states", namespace="state"
    )
    logger.info("Using `JSONFileStorage` for config and state storage")


@ui.page("/", title="Flowline SCADA Simulation")
def root(client: Client) -> ui.element:
    """Root page handler for the Flowline SCADA Simulation System."""
    request = client.request
    assert request is not None
    logger.info("Client connected to root page")
    user_agent = request.headers.get("user-agent", "unknown")
    client_ip = request.headers.get(
        "x-forwarded-for", request.headers.get("host", "unknown")
    )
    logger.info(f"Client IP: {client_ip}, User Agent: {user_agent}")
    session_id = hashlib.sha256(f"client-{user_agent}".encode()).hexdigest()
    logger.info(f"User session ID: {session_id}")

    # Load or create configuration for the session
    config = Configuration(session_id, storages=[config_storage], save_throttle=3.0)

    # Get current configuration
    theme_color = config.state.global_.theme_color
    client_state_key = state_storage.get_key(session_id)
    saved_state = state_storage.read(client_state_key)

    # Main layout container
    main_container = (
        ui.column()
        .classes("w-full h-auto bg-gray-50")
        .style(
            "max-width: 1440px; min-width: minmax(800px, 100%); margin: auto; scrollbar-width: thin; scrollbar-color: #cbd5e1 transparent;"
        )
    )
    with main_container:
        # Header with dynamic theme color
        header = (
            ui.row()
            .classes(
                f"w-full bg-{theme_color}-600 text-white p-4 shadow-lg items-center"
            )
            .style("""
            position: sticky;
            top: 0;
            z-index: 1000;
            scrollbar-width: thin;
            scrollbar-color: #cbd5e1 transparent;
            filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
        """)
        )
        with header:
            ui.icon("engineering").classes("text-lg mr-3 sm:text-2xl")
            ui.label("Flowline SCADA Simulation System").classes(
                "text-lg font-bold flex-1 sm:text-2xl"
            )

        @config.observe
        def on_theme_change(config_state: ConfigurationState) -> None:
            """Handle theme color changes."""
            nonlocal theme_color

            if theme_color == config_state.global_.theme_color:
                return

            new_theme = config_state.global_.theme_color
            header.classes(remove=f"bg-{theme_color}-600")
            header.classes(add=f"bg-{new_theme}-600")
            theme_color = new_theme
            logger.info(f"Theme changed to: {new_theme}")

        # Pipeline manager interface
        manager_container = ui.column().classes("w-full")
        with manager_container:
            pipeline_config = config.state.pipeline
            flow_station_config = config.state.flow_station

            # Build flow station factories
            upstream_factory = UpstreamStationFactory(
                name="Upstream Station", config=flow_station_config
            )
            downstream_factory = DownstreamStationFactory(
                name="Downstream Station", config=flow_station_config
            )

            if saved_state:
                logger.info(f"Restoring last pipeline state for session {session_id!r}")
                try:
                    manager = PipelineManager.load_state(
                        saved_state,
                        config=config,
                        flow_station_factories=[upstream_factory, downstream_factory],
                    )
                except Exception as exc:
                    logger.error(f"Failed to restore last state: {exc}", exc_info=True)
                    saved_state = None

            if not saved_state:
                logger.info(f"Creating new pipeline for session {session_id!r}")
                flow_type = FlowType(pipeline_config.flow_type)
                pipeline = Pipeline(
                    pipes=[],
                    fluid=None,
                    name=pipeline_config.name,
                    max_flow_rate=pipeline_config.max_flow_rate,
                    flow_type=flow_type,
                    scale_factor=pipeline_config.scale_factor,
                    connector_length=pipeline_config.connector_length,
                    alert_errors=pipeline_config.alert_errors,
                    ignore_leaks=pipeline_config.ignore_leaks,
                )

                fluid_config = pipeline_config.fluid
                fluid = Fluid.from_coolprop(
                    fluid_name=fluid_config.name,
                    phase=fluid_config.phase,
                    temperature=fluid_config.temperature,
                    pressure=pipeline.upstream_pressure or Quantity(101.325, "kPa"),
                    molecular_weight=fluid_config.molecular_weight,
                )
                pipeline.set_fluid(fluid)

                # Build pipeline manager
                manager = PipelineManager(
                    pipeline,
                    config=config,
                    flow_station_factories=[
                        upstream_factory,
                        downstream_factory,
                    ],
                )

            has_stored_state = state_storage.read(client_state_key) is not None
            logger.info(f"Session ID {session_id!r} in storage: {has_stored_state}")

            def pipeline_state_callback(_: str, __: typing.Any) -> None:
                """Handle pipeline state changes."""
                nonlocal has_stored_state

                logger.debug(
                    f"Pipeline state changed, updating storage for session {session_id!r}"
                )
                if not manager.is_valid():
                    logger.warning("Pipeline state is invalid, skipping state save")
                    return

                state = manager.dump_state()
                if not has_stored_state:
                    state_storage.create(client_state_key, state)
                else:
                    state_storage.update(client_state_key, state, overwrite=True)
                logger.debug(
                    f"Pipeline state storage updated for session {session_id!r}"
                )

            manager.subscribe("pipeline.*", pipeline_state_callback)

            # Get the active unit system
            unit_system = config.get_unit_system()
            logger.info(f"Using unit system: {unit_system!s}")
            manager_ui = PipelineManagerUI(manager=manager)

            # Observe configuration changes to update factories and UI
            @config.observe
            def upstream_observer(config_state: ConfigurationState) -> None:
                """Handle upstream station configuration changes."""
                upstream_factory.on_config_change(config_state)
                manager_ui.refresh_flow_stations()

            @config.observe
            def downstream_observer(config_state: ConfigurationState) -> None:
                """Handle downstream station configuration changes."""
                downstream_factory.on_config_change(config_state)
                manager_ui.refresh_flow_stations()

            manager_ui.show(
                ui_label="Flowline Build Toolkit",
                pipeline_label="Piping Configuration Preview",
                flow_station_label="Flow Stations (Meters and Regulators)",
                max_width="97%",
            )

    return main_container


def main():
    """Main application entry point."""
    logger.info("Starting Pipeline Simulation System")
    ui.run(
        title="Pipeline Simulation System",
        port=8080,
        host="0.0.0.0",
        reload=os.getenv("DEBUG", "False").lower()
        in ("t", "true", "yes", "on", "1", "y"),
        show=True,
        favicon="🌐",
        dark=False,
        storage_secret=os.getenv("NICEGUI_STORAGE_SECRET", "42d56f76g78h91j94i124u"),
        native=False,
        tailwind=True,
        prod_js=True,
    )


app = fastapi.FastAPI(
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
    debug=os.getenv("DEBUG", "False").lower() in ("t", "true", "yes", "on", "1", "y"),
)

# Mount static files directory for audio and other assets
fixtures_path = Path(__file__).parent / "fixtures"
if fixtures_path.exists():
    app.mount("/fixtures", StaticFiles(directory=fixtures_path), name="fixtures")
    logger.info("Mounted fixtures directory at /fixtures")

ui.run_with(
    app,
    title="Pipeline Simulation System",
    mount_path="/",
    favicon="🌐",
    dark=False,
    language="en-US",
    storage_secret=os.getenv("NICEGUI_STORAGE_SECRET", "42d56f76g78h91j94i124u"),
    tailwind=True,
    prod_js=True,
)

if __name__ in {"__main__", "__mp_main__"}:
    main()
