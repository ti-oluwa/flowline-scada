"""
Main Entry Point for SCADA Pipeline Management System Application.
"""

import logging
from nicegui import ui, app

from src.ui.builder import PipelineBuilderUI, PipelineBuilder

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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
        content_area = ui.column().classes("flex-1 w-full overflow-auto p-4")

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

            # Pipeline builder interface
            pipeline_builder_container = ui.column().classes("w-full")
            with pipeline_builder_container:
                builder = PipelineBuilder()
                builder_ui = PipelineBuilderUI(builder, theme_color="green")
                builder_ui.show(theme_color="green")

    return main_container


def main():
    """Main application entry point."""
    logger.info("Starting SCADA Pipeline Management System")

    # Configure NiceGUI application
    try:
        app.add_static_files("/static", "static")  # Add static file serving if needed
    except Exception:
        pass  # Static files directory might not exist, that's OK

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
