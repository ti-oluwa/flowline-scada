"""
Configuration UI Components
"""

import typing
import logging
from nicegui import ui

from src.config.manage import ConfigurationManager
from src.types import ConfigurationState
from src.units import Quantity

logger = logging.getLogger(__name__)


class ConfigurationUI:
    """Multi-tab configuration interface"""

    def __init__(self, manager: ConfigurationManager, theme_color: str = "blue"):
        self.theme_color = theme_color
        self.config_dialog = None
        self.is_open = False
        self.manager = manager
        self.manager.add_observer(self.on_config_change)
        self.current_config = manager.get_config()

    def set_theme_color(self, color: str):
        """Set the theme color for the UI"""
        self.theme_color = color

    def on_config_change(self, config_state: ConfigurationState):
        """Handle configuration changes"""
        self.current_config = config_state
        # Update any open UI elements if needed
        if self.is_open and self.config_dialog:
            # Could refresh UI here if needed
            pass

    def show(
        self,
        label: str = "System Configuration",
        max_width: str = "95%",
        min_width: str = "800px",
        height: str = "85vh",
        **kwargs,
    ):
        """Show the configuration dialog"""
        if self.config_dialog:
            self.config_dialog.close()

        # Custom CSS for styling
        ui.add_head_html("""
        <style>
        .config-scroll::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        .config-scroll::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 3px;
        }
        .config-scroll::-webkit-scrollbar-thumb {
            background: #c1c1c1;
            border-radius: 3px;
        }
        .config-scroll::-webkit-scrollbar-thumb:hover {
            background: #a8a8a8;
        }
        .config-content {
            scrollbar-width: thin;
            scrollbar-color: #c1c1c1 #f1f1f1;
        }
        
        .config-grid-responsive {
            display: grid;
            gap: 1rem;
            width: 100%;
        }
        
        @media (max-width: 640px) {
            .config-grid-responsive {
                grid-template-columns: 1fr;
            }
        }
        
        @media (min-width: 641px) and (max-width: 1024px) {
            .config-grid-responsive {
                grid-template-columns: repeat(2, 1fr);
            }
        }
        
        @media (min-width: 1025px) {
            .config-grid-responsive.grid-cols-2 {
                grid-template-columns: repeat(2, 1fr);
            }
            .config-grid-responsive.grid-cols-3 {
                grid-template-columns: repeat(3, 1fr);
            }
            .config-grid-responsive.grid-cols-4 {
                grid-template-columns: repeat(4, 1fr);
            }
        }
        
        .config-panel-content {
            width: 100% !important;
            max-width: 100% !important;
        }
        </style>
        """)

        self.config_dialog = (
            ui.dialog().classes("q-pa-none").style("width: 100vw; height: 100vh;")
        )

        with self.config_dialog:
            with (
                ui.card()
                .classes("flex flex-col w-full h-full")
                .style(
                    f"max-width: {max_width}; min-width: min({min_width}, 100%); height: {height}; margin: 0 auto;"
                )
            ):
                # Header
                with ui.row().classes(
                    "w-full items-center justify-between p-4 bg-gradient-to-r from-gray-50 to-gray-100 border-b"
                ):
                    ui.icon("settings").classes("text-2xl text-gray-600")
                    ui.label(label).classes("text-xl font-bold text-gray-800")
                    ui.button(icon="close", on_click=self.close_dialog).props(
                        "flat round"
                    ).classes("text-gray-600")

                # Content area with tabs
                with ui.column().classes("flex-1 overflow-hidden w-full"):
                    with (
                        ui.tabs()
                        .classes("w-full bg-white")
                        .style("flex-shrink: 0;") as tabs
                    ):
                        ui.tab("global", label="Global", icon="public").classes(
                            "text-xs sm:text-sm"
                        )
                        ui.tab(
                            "pipeline", label="Pipeline", icon="account_tree"
                        ).classes("text-xs sm:text-sm")
                        ui.tab(
                            "flow_station", label="Flow Station", icon="factory"
                        ).classes("text-xs sm:text-sm")
                        ui.tab(
                            "all_configs", label="All Configs", icon="view_list"
                        ).classes("text-xs sm:text-sm")
                        ui.tab(
                            "import_export", label="I/E", icon="import_export"
                        ).classes("text-xs sm:text-sm")

                    with (
                        ui.tab_panels(tabs, value="global")
                        .classes("flex-1 config-scroll config-content w-full")
                        .style("overflow-y: auto; overflow-x: hidden; width: 100%;")
                    ):
                        with (
                            ui.tab_panel("global")
                            .classes("w-full p-2 sm:p-4 lg:p-6")
                            .style("width: 100%;")
                        ):
                            self.show_global_config_panel()

                        with (
                            ui.tab_panel("pipeline")
                            .classes("w-full p-2 sm:p-4 lg:p-6")
                            .style("width: 100%;")
                        ):
                            self.show_pipeline_config_panel()

                        with (
                            ui.tab_panel("flow_station")
                            .classes("w-full p-2 sm:p-4 lg:p-6")
                            .style("width: 100%;")
                        ):
                            self.show_flow_station_config_panel()

                        with (
                            ui.tab_panel("all_configs")
                            .classes("w-full p-2 sm:p-4 lg:p-6")
                            .style("width: 100%;")
                        ):
                            self.show_all_configs_panel()

                        with (
                            ui.tab_panel("import_export")
                            .classes("w-full p-2 sm:p-4 lg:p-6")
                            .style("width: 100%;")
                        ):
                            self.show_import_export_panel()

                # Footer actions
                with ui.row().classes(
                    "w-full p-2 sm:p-4 border-t bg-gray-50 justify-between items-center gap-2 flex-wrap"
                ):
                    # Auto-save status indicator
                    auto_save_enabled = self.current_config.global_.auto_save
                    with ui.row().classes("gap-2 items-center"):
                        ui.icon("save" if auto_save_enabled else "save_as").classes(
                            f"text-{'green' if auto_save_enabled else 'orange'}-600"
                        )
                        ui.label(
                            "Auto-save: ON" if auto_save_enabled else "Auto-save: OFF"
                        ).classes(
                            f"text-xs text-{'green' if auto_save_enabled else 'orange'}-600 font-medium"
                        )
                        if not auto_save_enabled and self.manager.has_unsaved_changes():
                            ui.chip("Unsaved changes", color="orange").classes(
                                "text-xs"
                            )

                    # Action buttons
                    with ui.row().classes("gap-2"):
                        ui.button(
                            "Reset",
                            on_click=self.reset_to_defaults,
                            color="red",
                        ).props("outline").classes("text-xs sm:text-sm")

                        # Show Apply button only if auto-save is disabled
                        if not auto_save_enabled:
                            ui.button(
                                "Save",
                                on_click=self.apply_changes,
                                color=self.theme_color,
                                icon="save",
                            ).classes("text-xs sm:text-sm")

                        ui.button(
                            "Close" if auto_save_enabled else "Save & Close",
                            on_click=self.apply_and_close,
                            color=self.theme_color,
                        ).classes("text-xs sm:text-sm")

        self.config_dialog.open()
        self.is_open = True

    def show_global_config_panel(self):
        """Create global configuration panel"""
        config = self.current_config.global_

        with ui.column().classes("w-full gap-4 config-panel-content"):
            with ui.card().classes("w-full p-4"):
                ui.label("Global Settings").classes("text-lg font-semibold mb-3")

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.select(
                        label="Theme Color",
                        options=[
                            "blue",
                            "green",
                            "red",
                            "purple",
                            "indigo",
                            "teal",
                            "orange",
                        ],
                        value=config.theme_color,
                        on_change=lambda e: self.manager.update_global_config(
                            theme_color=e.value
                        ),
                    ).classes("w-full")

                    ui.select(
                        label="Unit System",
                        options=self.manager.get_available_unit_systems(),
                        value=config.unit_system_name,
                        on_change=lambda e: self.manager.update_global_config(
                            unit_system_name=e.value
                        ),
                    ).classes("w-full")

                with ui.column().classes("w-full gap-2"):
                    with ui.row().classes("w-full gap-4 items-center"):
                        ui.label("Auto-save:").classes("w-24")
                        ui.switch(
                            value=config.auto_save,
                            on_change=lambda e: self._on_auto_save_change(e.value),
                        )
                    ui.label(
                        "When enabled, configuration changes are automatically saved. "
                        "When disabled, you must manually save changes."
                    ).classes("text-xs text-gray-600")

    def show_pipeline_config_panel(self):
        """Create pipeline configuration panel"""
        config = self.current_config.pipeline

        with ui.column().classes("w-full gap-4 config-panel-content"):
            # Pipeline Basic Settings
            with ui.card().classes("w-full p-4"):
                ui.label("Pipeline Settings").classes("text-lg font-semibold mb-3")

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.input(
                        label="Pipeline Name",
                        value=config.name,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            name=e.value
                        ),
                    ).classes("w-full")

                    ui.select(
                        label="Flow Type",
                        options=["compressible", "incompressible"],
                        value=config.flow_type,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            flow_type=e.value
                        ),
                    ).classes("w-full")

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.number(
                        label=f"Max Flow Rate ({config.max_flow_rate.units})",
                        value=config.max_flow_rate.magnitude,
                        format="%.2f",
                        on_change=lambda e: self.manager.update_pipeline_config(
                            max_flow_rate=Quantity(e.value, config.max_flow_rate.units)  # type: ignore
                        ),
                    ).classes("w-full")

                    ui.number(
                        label=f"Connector Length ({config.connector_length.units})",
                        value=config.connector_length.magnitude,
                        format="%.3f",
                        step=0.001,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            connector_length=Quantity(
                                e.value, config.connector_length.units
                            )  # type: ignore
                        ),
                    ).classes("w-full")

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.number(
                        label="Scale Factor",
                        value=config.scale_factor,
                        format="%.3f",
                        step=0.001,
                        min=0.001,
                        max=10.0,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            scale_factor=e.value
                        ),
                    ).classes("w-full")

                with ui.row().classes("w-full gap-4 items-center"):
                    ui.label("Alert Errors:").classes("w-24")
                    ui.switch(
                        value=config.alert_errors,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            alert_errors=e.value
                        ),
                    )

            # Fluid Properties
            with ui.card().classes("w-full p-4"):
                ui.label("Default Fluid Properties").classes(
                    "text-lg font-semibold mb-3"
                )
                fluid_config = config.fluid

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.input(
                        label="Fluid Name",
                        value=fluid_config.name,
                        on_change=lambda e: self.manager.update_nested_config(
                            "pipeline.fluid", name=e.value
                        ),
                    ).classes("w-full")

                    ui.select(
                        label="Fluid Phase",
                        options=["gas", "liquid"],
                        value=fluid_config.phase,
                        on_change=lambda e: self.manager.update_nested_config(
                            "pipeline.fluid", phase=e.value
                        ),
                    ).classes("w-full")

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.number(
                        label=f"Temperature ({fluid_config.temperature.units})",
                        value=fluid_config.temperature.magnitude,
                        format="%.2f",
                        on_change=lambda e: self.manager.update_nested_config(
                            "pipeline.fluid",
                            temperature=Quantity(
                                e.value, fluid_config.temperature.units
                            ),
                        ),
                    ).classes("w-full")

                    ui.number(
                        label=f"Pressure ({fluid_config.pressure.units})",
                        value=fluid_config.pressure.magnitude,
                        format="%.2f",
                        on_change=lambda e: self.manager.update_nested_config(
                            "pipeline.fluid",
                            pressure=Quantity(e.value, fluid_config.pressure.units),
                        ),
                    ).classes("w-full")

            # Pipe Properties
            with ui.card().classes("w-full p-4"):
                ui.label("Default Pipe Properties").classes(
                    "text-lg font-semibold mb-3"
                )
                pipe_config = config.pipe

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.input(
                        label="Pipe Name",
                        value=pipe_config.name,
                        on_change=lambda e: self.manager.update_nested_config(
                            "pipeline.pipe", name=e.value
                        ),
                    ).classes("w-full")

                    ui.input(
                        label="Material",
                        value=pipe_config.material,
                        on_change=lambda e: self.manager.update_nested_config(
                            "pipeline.pipe", material=e.value
                        ),
                    ).classes("w-full")

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.number(
                        label=f"Length ({pipe_config.length.units})",
                        value=pipe_config.length.magnitude,
                        format="%.2f",
                        on_change=lambda e: self.manager.update_nested_config(
                            "pipeline.pipe",
                            length=Quantity(e.value, pipe_config.length.units),
                        ),
                    ).classes("w-full")

                    ui.number(
                        label=f"Internal Diameter ({pipe_config.internal_diameter.units})",
                        value=pipe_config.internal_diameter.magnitude,
                        format="%.4f",
                        step=0.0001,
                        on_change=lambda e: self.manager.update_nested_config(
                            "pipeline.pipe",
                            internal_diameter=Quantity(
                                e.value, pipe_config.internal_diameter.units
                            ),
                        ),
                    ).classes("w-full")

    def show_flow_station_config_panel(self):
        """Create flow station configuration panel"""
        config = self.current_config.flow_station

        with ui.column().classes("w-full gap-4 config-panel-content"):
            with ui.card().classes("w-full p-4"):
                ui.label("Flow Station Settings").classes("text-lg font-semibold mb-3")

                with ui.element("div").classes("config-grid-responsive grid-cols-3"):
                    ui.input(
                        label="Pressure Unit",
                        value=str(config.pressure_unit),
                        on_change=lambda e: self.manager.update_flow_station_config(
                            pressure_unit=e.value
                        ),
                    ).classes("w-full")

                    ui.input(
                        label="Temperature Unit",
                        value=str(config.temperature_unit),
                        on_change=lambda e: self.manager.update_flow_station_config(
                            temperature_unit=e.value
                        ),
                    ).classes("w-full")

                    ui.input(
                        label="Flow Unit",
                        value=str(config.flow_unit),
                        on_change=lambda e: self.manager.update_flow_station_config(
                            flow_unit=e.value
                        ),
                    ).classes("w-full")

    def show_all_configs_panel(self):
        """Create a panel showing all configurations in a flat view"""
        flat_configs = self.manager.get_all_configs_flat()

        with ui.column().classes("w-full gap-4 config-panel-content"):
            with ui.card().classes("w-full p-4"):
                ui.label("All Configuration Settings").classes(
                    "text-lg font-semibold mb-3"
                )
                ui.label(
                    "This is a comprehensive view of all configuration values with their hierarchical paths."
                ).classes("text-sm text-gray-600 mb-4")

                # Search functionality
                search_input = ui.input(
                    label="Search configurations",
                    placeholder="Type to filter configurations...",
                ).classes("w-full mb-4")

                # Configuration table
                with ui.scroll_area().classes("h-96 w-full"):
                    config_table = ui.column().classes("w-full gap-2")

                def update_table(search_term: str = ""):
                    nonlocal config_table
                    logger.info(
                        f"Updating config table with search term: '{search_term}'"
                    )
                    config_table.clear()
                    configs = (
                        {
                            k: v
                            for k, v in flat_configs.items()
                            if search_term.lower() in k.lower()
                        }
                        if search_term
                        else flat_configs
                    )
                    with config_table:
                        for config_path, value in sorted(configs.items()):
                            with ui.row().classes(
                                "w-full p-2 border-b border-gray-200 items-center gap-4"
                            ):
                                ui.label(config_path).classes(
                                    "text-sm font-mono text-blue-600 flex-1"
                                )

                                if config_path == "last_updated":
                                    ui.label(str(value)).classes(
                                        "text-sm text-gray-600"
                                    )
                                    continue

                                # Show different input types based on value type
                                if isinstance(value, bool):
                                    ui.switch(
                                        value=value,
                                        on_change=lambda e,
                                        path=config_path: self._update_from_path(
                                            path, e.value
                                        ),
                                    ).classes("flex-shrink-0")
                                elif isinstance(value, (int, float)):
                                    ui.number(
                                        value=value,
                                        format="%.6g",
                                        on_change=lambda e,
                                        path=config_path: self._update_from_path(
                                            path, e.value
                                        ),
                                    ).classes("w-32 flex-shrink-0")
                                elif isinstance(value, (list, tuple, set)):
                                    ui.input(
                                        value=", ".join(map(str, value)),
                                        on_change=lambda e,
                                        path=config_path: self._update_from_path(
                                            path, e.value.split(", ")
                                        ),
                                    ).classes("w-64 flex-shrink-0")
                                elif value is None:
                                    ui.input(
                                        value="",
                                        placeholder="None",
                                        on_change=lambda e,
                                        path=config_path: self._update_from_path(
                                            path, e.value or None
                                        ),
                                    ).classes("w-64 flex-shrink-0")
                                else:
                                    ui.input(
                                        value=str(value),
                                        on_change=lambda e,
                                        path=config_path: self._update_from_path(
                                            path, e.value
                                        ),
                                    ).classes("w-64 flex-shrink-0")
                    config_table.update()

                # Initial table load
                update_table()
                # Update table on search
                search_input.on("change", lambda e: update_table(e.args), throttle=0.05)

    def show_import_export_panel(self):
        """Create import/export panel"""
        with ui.column().classes("w-full gap-4 config-panel-content"):
            with ui.card().classes("w-full p-4"):
                ui.label("Import/Export Configuration").classes(
                    "text-lg font-semibold mb-3"
                )

                ui.button(
                    "Export Configuration",
                    on_click=self.export_configuration,
                    color=self.theme_color,
                    icon="download",
                ).classes("w-full mb-4")

                ui.upload(
                    label="Import Configuration",
                    on_upload=self.import_configuration,
                    auto_upload=True,
                ).classes("w-full")

    def _on_auto_save_change(self, value: bool):
        """Handle auto-save setting change"""
        self.manager.update_global_config(auto_save=value)
        # Refresh the UI to update the footer status
        if self.is_open and self.config_dialog:
            ui.notify(
                f"Auto-save {'enabled' if value else 'disabled'}. "
                f"{'Changes will be saved automatically.' if value else 'You must manually save changes.'}",
                type="info",
            )
            # Refresh the dialog to update button visibility
            self.show()

    def _update_from_path(self, path: str, value: typing.Any):
        """Update configuration from a flat path"""
        try:
            if "." in path:
                parts = path.split(".")
                obj_path = ".".join(parts[:-1])
                attr_name = parts[-1]
                self.manager.update_nested_config(obj_path, **{attr_name: value})
            else:
                # Handle top-level attributes
                if hasattr(self.current_config.global_, path):
                    self.manager.update_global_config(**{path: value})
                elif hasattr(self.current_config.pipeline, path):
                    self.manager.update_pipeline_config(**{path: value})
                elif hasattr(self.current_config.flow_station, path):
                    self.manager.update_flow_station_config(**{path: value})
        except Exception as e:
            logger.error(f"Failed to update config at path {path}: {e}")
            ui.notify(f"Failed to update {path}: {str(e)}", type="negative")

    def export_configuration(self):
        """Export configuration to JSON file"""
        try:
            config_json = self.manager.export_configuration()
            ui.download(config_json.encode(), filename="scada_config.json")
            ui.notify("Configuration exported successfully", type="positive")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            ui.notify(f"Export failed: {e}", type="negative")

    def import_configuration(self, event):
        """Import configuration from uploaded file"""
        try:
            content = event.content.read().decode()
            self.manager.import_configuration(content)
            ui.notify("Configuration imported successfully", type="positive")
            self.show()
        except Exception as e:
            logger.error(f"Import failed: {e}")
            ui.notify(f"Import failed: {e}", type="negative")

    def reset_to_defaults(self):
        """Reset all configuration to defaults"""

        def confirm_reset():
            self.manager.reset_to_defaults()
            ui.notify("Configuration reset to defaults", type="positive")
            self.show()

        with ui.dialog() as dialog:
            with ui.card():
                ui.label("Reset all configuration to defaults?")
                ui.label("This action cannot be undone.").classes(
                    "text-sm text-red-600"
                )
                with ui.row():
                    ui.button("Cancel", on_click=dialog.close)
                    ui.button(
                        "Reset",
                        on_click=lambda: (confirm_reset(), dialog.close()),
                        color="red",
                    )
        dialog.open()

    def apply_changes(self):
        """Apply changes (manual save when auto-save is disabled)"""
        if not self.current_config.global_.auto_save:
            self.manager.manual_save()
            ui.notify("Configuration saved manually", type="positive")
        else:
            ui.notify(
                "Auto-save is enabled - changes are saved automatically", type="info"
            )

    def apply_and_close(self):
        """Apply changes and close dialog"""
        if not self.current_config.global_.auto_save:
            self.manager.manual_save()
        self.close_dialog()
        ui.notify("Configuration applied", type="positive")

    def close_dialog(self):
        """Close the configuration dialog"""
        if self.config_dialog:
            self.config_dialog.close()
            self.is_open = False

    def cleanup(self):
        """Cleanup resources"""
        self.manager.remove_observer(self.on_config_change)
        self.close_dialog()

    def __del__(self):
        self.cleanup()
