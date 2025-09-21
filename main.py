"""
Main Entry Point for Pipeline Management System Application.
"""

import hashlib
import logging
import os
import typing
import redis
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from nicegui import Client, ui

from src.config.core import ConfigurationState, Configuration
from src.config.storages import JSONFileStorage, RedisStorage
from src.flow import FlowType, Fluid
from src.ui.components import Pipeline
from src.ui.manage import (
    DownstreamStationFactory,
    PipelineManager,
    PipelineManagerUI,
    UpstreamStationFactory,
)

load_dotenv(find_dotenv(".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(name)s:%(funcName)s:%(lineno)d] - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


redis_available = False
if redis_url := os.getenv("REDIS_URL"):
    try:
        redis_client = redis.Redis.from_url(redis_url)
        redis_client.ping()
        config_file_storage = RedisStorage(redis_client)
        state_file_storage = RedisStorage(redis_client)
        redis_available = True
        logger.info("Using `RedisStorage` for config and state storage")
    except redis.RedisError as exc:
        logger.error(f"Failed to connect to Redis: {exc}, falling back to file storage")
        redis_available = False

if not redis_available:
    config_file_storage = JSONFileStorage(Path.cwd() / ".pipeline-scada/configs")
    state_file_storage = JSONFileStorage(Path.cwd() / ".pipeline-scada/states")
    logger.info("Using `JSONFileStorage` for config and state storage")


@ui.page("/", title="Pipeline Management System")
def root(client: Client) -> ui.element:
    """Create the main Pipeline Management System application."""
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

    config = Configuration(
        session_id,
        storages=[config_file_storage],
    )

    # Get current configuration
    theme_color = config.state.global_.theme_color
    last_state = state_file_storage.read(session_id)

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
        header = ui.row().classes(
            f"w-full bg-{theme_color}-600 text-white p-4 shadow-lg items-center"
        )
        with header:
            ui.icon("engineering").classes("text-3xl mr-3")
            ui.label("Pipeline Management System").classes(
                "text-2xl font-bold flex-1 sm:text-lg"
            )

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

        config.observe(on_theme_change)

        # Pipeline manager interface
        pipeline_manager_container = ui.column().classes("w-full")
        with pipeline_manager_container:
            pipeline_config = config.state.pipeline
            flow_station_config = config.state.flow_station

            # Build flow station factories
            upstream_factory = UpstreamStationFactory(
                name="Upstream Station", config=flow_station_config
            )
            downstream_factory = DownstreamStationFactory(
                name="Downstream Station", config=flow_station_config
            )

            if last_state:
                logger.info(f"Restoring last pipeline state for session {session_id!r}")
                try:
                    pipeline_manager = PipelineManager.from_state(
                        last_state,
                        config=config,
                        flow_station_factories=[upstream_factory, downstream_factory],
                    )
                except Exception as e:
                    logger.error(f"Failed to restore last state: {e}", exc_info=True)
                    last_state = None

            if not last_state:
                logger.info(f"Creating new pipeline for session {session_id!r}")
                fluid_config = pipeline_config.fluid
                fluid = Fluid.from_coolprop(
                    fluid_name=fluid_config.name,
                    phase=fluid_config.phase,
                    temperature=fluid_config.temperature,
                    pressure=fluid_config.pressure,
                    molecular_weight=fluid_config.molecular_weight,
                )

                flow_type = FlowType(pipeline_config.flow_type)
                pipeline = Pipeline(
                    pipes=[],
                    fluid=fluid,
                    name=pipeline_config.name,
                    max_flow_rate=pipeline_config.max_flow_rate,
                    flow_type=flow_type,
                    scale_factor=pipeline_config.scale_factor,
                    connector_length=pipeline_config.connector_length,
                    alert_errors=pipeline_config.alert_errors,
                )
                # Build pipeline manager
                pipeline_manager = PipelineManager(
                    pipeline,
                    config=config,
                    flow_station_factories=[upstream_factory, downstream_factory],
                )

            session_id_in_storage = state_file_storage.read(session_id) is not None
            logger.info(
                f"Session ID {session_id!r} in storage: {session_id_in_storage}"
            )

            def pipeline_state_observer(_: str, __: typing.Any) -> None:
                """Handle pipeline state changes."""
                nonlocal session_id_in_storage

                logger.debug(
                    f"Pipeline state changed, updating storage for session {session_id!r}"
                )
                if not pipeline_manager.is_valid():
                    logger.warning("Pipeline state is invalid, skipping state save")
                    return

                state = pipeline_manager.get_state()
                if not session_id_in_storage:
                    state_file_storage.create(session_id, state)
                else:
                    state_file_storage.update(session_id, state, overwrite=True)
                logger.debug(
                    f"Pipeline state storage updated for session {session_id!r}"
                )

            pipeline_manager.subscribe("pipeline.*", pipeline_state_observer)

            # Get the active unit system
            unit_system = config.get_unit_system()
            logger.info(f"Using unit system: {unit_system!s}")
            manager_ui = PipelineManagerUI(manager=pipeline_manager)

            # Observe configuration changes to update factories and UI
            def upstream_observer(config_state: ConfigurationState) -> None:
                """Handle upstream station configuration changes."""
                upstream_factory.on_config_change(config_state)
                manager_ui.refresh_flow_stations()

            def downstream_observer(config_state: ConfigurationState) -> None:
                """Handle downstream station configuration changes."""
                downstream_factory.on_config_change(config_state)
                manager_ui.refresh_flow_stations()

            config.observe(upstream_observer)
            config.observe(downstream_observer)
            manager_ui.show(ui_label="Pipeline Builder", max_width="95%")

    return main_container


def main():
    """Main application entry point."""
    logger.info("Starting Pipeline Management System")
    ui.run(
        title="Pipeline Management System",
        port=8080,
        host="0.0.0.0",
        reload=os.getenv("DEBUG", "False").lower() in ("t", "true", "yes", "on"),
        show=True,
        favicon="🔧",
        dark=False,
        storage_secret=os.getenv("NICEGUI_STORAGE_SECRET", "42d56f76g78h91j94i124u"),
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
