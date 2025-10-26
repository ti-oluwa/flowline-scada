"""
Configuration management UI.
"""

import typing
import logging
from nicegui import ui

from src.config.core import Configuration
from src.units import Quantity

logger = logging.getLogger(__name__)

__all__ = ["ConfigurationUI"]


THEMES = [
    "blue",
    "green",
    "red",
    "purple",
    "indigo",
    "teal",
    "orange",
    "pink",
    "cyan",
    "amber",
    "lime",
    "emerald",
    "fuchsia",
    "rose",
    "violet",
    "sky",
    "slate",
    "gray",
    "zinc",
    "neutral",
    "stone",
]


class ConfigurationUI:
    """Multi-tab configuration interface"""

    def __init__(self, config: Configuration):
        """Initialize Configuration UI"""
        self.config = config
        self.dialog = None
        self.is_open = False

    @property
    def theme_color(self) -> str:
        """Get current theme color from configuration"""
        return self.config.state.global_.theme_color

    def show(
        self,
        label: str = "System Configuration",
        max_width: str = "95%",
        min_width: str = "800px",
        height: str = "85vh",
        **kwargs,
    ):
        """Show the configuration dialog"""
        if self.dialog:
            self.dialog.close()

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

        self.dialog = (
            ui.dialog().classes("q-pa-none").style("width: 100vw; height: 100vh;")
        )
        with self.dialog:
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
                    ui.icon("settings").classes("text-2xl text-gray-600").tooltip(
                        "System Configuration - Manage application settings and preferences"
                    )
                    ui.label(label).classes("text-xl font-bold text-gray-800")
                    ui.button(icon="close", on_click=self.close_dialog).props(
                        "flat round"
                    ).classes("text-gray-600").tooltip("Close configuration dialog")

                # Content area with tabs
                with ui.column().classes("flex-1 overflow-hidden w-full"):
                    with (
                        ui.tabs()
                        .classes("w-full bg-white")
                        .style("flex-shrink: 0;") as tabs
                    ):
                        ui.tab("global", label="Global", icon="public").classes(
                            "text-xs sm:text-sm"
                        ).tooltip(
                            "Global application settings including theme, units, and auto-save preferences"
                        )
                        ui.tab(
                            "pipeline", label="Flowline", icon="account_tree"
                        ).classes("text-xs sm:text-sm").tooltip(
                            "Default settings for flowlines, pipes, and fluid properties"
                        )
                        ui.tab(
                            "all_configs", label="All Configs", icon="view_list"
                        ).classes("text-xs sm:text-sm").tooltip(
                            "Advanced view showing all configuration parameters with their full paths"
                        )
                        ui.tab(
                            "import_export", label="I/E", icon="import_export"
                        ).classes("text-xs sm:text-sm").tooltip(
                            "Import and export configuration settings to/from JSON files"
                        )

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
                    auto_save_enabled = self.config.state.global_.auto_save
                    with ui.row().classes("gap-2 items-center"):
                        ui.icon("save" if auto_save_enabled else "save_as").classes(
                            f"text-{'green' if auto_save_enabled else 'orange'}-600"
                        ).tooltip(
                            "Auto-save is currently "
                            + ("enabled" if auto_save_enabled else "disabled")
                        )
                        ui.label(
                            "Auto-save: ON" if auto_save_enabled else "Auto-save: OFF"
                        ).classes(
                            f"text-xs text-{'green' if auto_save_enabled else 'orange'}-600 font-medium"
                        ).tooltip(
                            "Indicates whether configuration changes are automatically saved. "
                            + (
                                "Changes are saved immediately when modified."
                                if auto_save_enabled
                                else "You must manually save changes."
                            )
                        )
                        if not auto_save_enabled:
                            ui.chip("Unsaved changes", color="orange").classes(
                                "text-xs"
                            ).tooltip(
                                "You have unsaved configuration changes. Click 'Save' to persist them."
                            )

                    # Action buttons
                    with ui.row().classes("gap-2"):
                        ui.button(
                            "Reset",
                            on_click=self.reset,
                            color="red",
                        ).props("outline").classes("text-xs sm:text-sm").tooltip(
                            "Reset all configuration settings to their default values. This action cannot be undone."
                        )

                        # Show Apply button only if auto-save is disabled
                        if not auto_save_enabled:
                            ui.button(
                                "Save",
                                on_click=self.apply_changes,
                                color=self.theme_color,
                                icon="save",
                            ).classes("text-xs sm:text-sm").tooltip(
                                "Save all current configuration changes to disk. Changes will persist when the application is restarted."
                            )

                        ui.button(
                            "Close" if auto_save_enabled else "Save & Close",
                            on_click=self.apply_and_close,
                            color=self.theme_color,
                        ).classes("text-xs sm:text-sm").tooltip(
                            "Close the configuration dialog."
                            + (
                                ""
                                if auto_save_enabled
                                else " All changes will be saved before closing."
                            )
                        )

        self.dialog.open()
        self.is_open = True

    def show_global_config_panel(self):
        """Create global configuration panel"""
        config = self.config.state.global_

        with ui.column().classes("w-full gap-4 config-panel-content"):
            with ui.card().classes("w-full p-4"):
                ui.label("Global Settings").classes(
                    "text-lg font-semibold mb-3"
                ).tooltip(
                    "Application-wide settings that affect the entire system behavior and appearance."
                )

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.select(
                        label="Theme Color",
                        options=THEMES,
                        value=config.theme_color or "sky",
                        new_value_mode="add",
                        on_change=lambda e: self.config.update(
                            "global_", theme_color=e.value
                        ),
                    ).classes("w-full").tooltip(
                        "Choose the primary color theme for the user interface. This affects buttons, highlights, and accent colors throughout the application."
                    )

                    ui.select(
                        label="Unit System",
                        options=self.config.get_unit_systems(),
                        value=config.unit_system_name,
                        on_change=lambda e: self.config.update(
                            "global_", unit_system_name=e.value
                        ),
                    ).classes("w-full").tooltip(
                        "Select the measurement unit system to use throughout the application. This determines units for length, pressure, temperature, flow rate, etc."
                    )

                with ui.column().classes("w-full gap-2"):
                    with ui.row().classes("w-full gap-4 items-center"):
                        ui.label("Auto-save:").classes("w-24").tooltip(
                            "Controls whether configuration changes are saved automatically or require manual saving."
                        )
                        ui.switch(
                            value=config.auto_save,
                            on_change=lambda e: self._on_auto_save_change(e.value),
                        ).tooltip(
                            "When enabled, all configuration changes are automatically saved to disk. When disabled, you must manually click 'Save' to persist changes."
                        )
                    ui.label(
                        "When enabled, configuration changes are automatically saved. "
                        "When disabled, you must manually save changes."
                    ).classes("text-xs text-gray-600")

    def show_pipeline_config_panel(self):
        """Create pipeline configuration panel"""
        config = self.config.state.pipeline
        unit_system = self.config.get_unit_system()
        flow_unit = unit_system["flow_rate"]
        length_unit = unit_system["length"]
        temperature_unit = unit_system["temperature"]
        diameter_unit = unit_system.get("diameter", length_unit)

        with ui.column().classes("w-full gap-4 config-panel-content"):
            # Pipeline Basic Settings
            with ui.card().classes("w-full p-4"):
                ui.label("Flowline Settings").classes(
                    "text-lg font-semibold mb-3"
                ).tooltip(
                    "Default configuration for flowline systems including flow type, scale factors, and error handling."
                )

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.input(
                        label="Flowline Name",
                        value=config.name,
                        on_change=lambda e: self.config.update(
                            "pipeline", name=e.value
                        ),
                    ).classes("w-full").tooltip(
                        "Default name for new flowlines created in the system. You can override this when creating individual flowlines."
                    )

                    ui.select(
                        label="Flow Type",
                        options=["compressible", "incompressible"],
                        value=config.flow_type,
                        on_change=lambda e: self.config.update(
                            "pipeline", flow_type=e.value
                        ),
                    ).classes("w-full").tooltip(
                        "Type of fluid flow analysis to use. Compressible flow accounts for density changes with pressure (gases), while incompressible assumes constant density (liquids)."
                    )

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.number(
                        label=f"Maximum Allowable Flow Rate ({flow_unit.display})",
                        value=config.max_flow_rate.to(flow_unit.unit).magnitude,
                        format="%.2f",
                        on_change=lambda e: self.config.update(
                            "pipeline",
                            max_flow_rate=Quantity(e.value, flow_unit.unit),  # type: ignore
                        ),
                    ).classes("w-full").tooltip(
                        "Maximum flow rate for the flowline. Used for visualization, validation, and scaling."
                    )

                    ui.number(
                        label=f"Connector Length ({length_unit.display})",
                        value=config.connector_length.to(length_unit.unit).magnitude,
                        format="%.3f",
                        step=0.001,
                        on_change=lambda e: self.config.update(
                            "pipeline",
                            connector_length=Quantity(e.value, length_unit.unit),  # type: ignore
                        ),
                    ).classes("w-full").tooltip(
                        "Default length for connectors between flowline components. This willl be x2 for elbows."
                    )

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.number(
                        label="Scale Factor",
                        value=config.scale_factor,
                        format="%.3f",
                        step=0.001,
                        min=0.001,
                        max=10.0,
                        on_change=lambda e: self.config.update(
                            "pipeline", scale_factor=e.value
                        ),
                    ).classes("w-full").tooltip(
                        "Scale factor for pipeline visualization. Controls the size relationship between physical dimensions and display pixels. Higher values make pipes appear larger."
                    )

                with ui.row().classes("w-full gap-4 items-center"):
                    ui.label("Alert Errors:").classes("w-24").tooltip(
                        "Controls whether the system shows popup alerts for errors and warnings during calculations."
                    )
                    ui.switch(
                        value=config.alert_errors,
                        on_change=lambda e: self.config.update(
                            "pipeline", alert_errors=e.value
                        ),
                    ).tooltip(
                        "When enabled, error messages and warnings will be displayed as popup notifications. When disabled, errors are only logged to the console."
                    )

            # Fluid Properties
            with ui.card().classes("w-full p-4"):
                ui.label("Default Fluid Properties").classes(
                    "text-lg font-semibold mb-3"
                ).tooltip(
                    "Default properties for fluids in new flowlines. These values are used as starting points when creating new fluid configurations."
                )
                fluid_config = config.fluid

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.input(
                        label="Fluid Name",
                        value=fluid_config.name,
                        on_change=lambda e: self.config.update(
                            "pipeline.fluid", name=e.value
                        ),
                    ).classes("w-full").tooltip(
                        "Name or identifier for the fluid being transported. This is used for labeling and documentation purposes."
                    )

                    ui.select(
                        label="Fluid Phase",
                        options=["gas", "liquid"],
                        value=fluid_config.phase,
                        on_change=lambda e: self.config.update(
                            "pipeline.fluid", phase=e.value
                        ),
                    ).classes("w-full").tooltip(
                        "Physical phase of the fluid. Gas phase typically uses compressible flow equations, while liquid phase uses incompressible flow equations."
                    )

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.number(
                        label=f"Temperature ({temperature_unit.display})",
                        value=fluid_config.temperature.to(
                            temperature_unit.unit
                        ).magnitude,
                        format="%.2f",
                        on_change=lambda e: self.config.update(
                            "pipeline.fluid",
                            temperature=Quantity(e.value, temperature_unit.unit),
                        ),
                    ).classes("w-full").tooltip(
                        "Operating temperature of the fluid. This affects fluid properties like density, viscosity, and compressibility factor used in flow calculations."
                    )

            # Pipe Properties
            with ui.card().classes("w-full p-4"):
                ui.label("Default Pipe Properties").classes(
                    "text-lg font-semibold mb-3"
                ).tooltip(
                    "Default specifications for pipe sections in new flowlines. These settings provide starting values when adding pipes to a system."
                )
                pipe_config = config.pipe

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.input(
                        label="Pipe Name",
                        value=pipe_config.name,
                        on_change=lambda e: self.config.update(
                            "pipeline.pipe", name=e.value
                        ),
                    ).classes("w-full").tooltip(
                        "Default name prefix for new pipe sections. Individual pipes can have custom names when created."
                    )

                    ui.input(
                        label="Material",
                        value=pipe_config.material,
                        on_change=lambda e: self.config.update(
                            "pipeline.pipe", material=e.value
                        ),
                    ).classes("w-full").tooltip(
                        "Pipe material specification (e.g., Steel, PVC, Copper). This affects roughness values and is used for documentation and material tracking."
                    )

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.number(
                        label=f"Length ({length_unit.display})",
                        value=pipe_config.length.to(length_unit.unit).magnitude,
                        format="%.2f",
                        on_change=lambda e: self.config.update(
                            "pipeline.pipe",
                            length=Quantity(e.value, length_unit.unit),
                        ),
                    ).classes("w-full").tooltip(
                        "Default length for new pipe sections. This is used in pressure drop calculations and determines the physical scale of visualizations."
                    )

                    ui.number(
                        label=f"Internal Diameter ({diameter_unit.display})",
                        value=pipe_config.internal_diameter.to(
                            diameter_unit.unit
                        ).magnitude,
                        format="%.4f",
                        step=0.0001,
                        on_change=lambda e: self.config.update(
                            "pipeline.pipe",
                            internal_diameter=Quantity(e.value, diameter_unit.unit),
                        ),
                    ).classes("w-full").tooltip(
                        "Default internal diameter for new pipe sections. This is critical for flow calculations, pressure drop analysis, and cross-sectional area computations."
                    )

    def show_all_configs_panel(self):
        """Create a panel showing all configurations in a flat view"""
        flat_configs = self.config.state.flatten()

        with ui.column().classes("w-full gap-4 config-panel-content"):
            with ui.card().classes("w-full p-4"):
                ui.label("All Configuration Settings").classes(
                    "text-lg font-semibold mb-3"
                ).tooltip(
                    "Comprehensive view of all configuration parameters in the system."
                )
                ui.label(
                    "This is a comprehensive view of all configuration values with their hierarchical paths."
                ).classes("text-sm text-gray-600 mb-4")

                # Search functionality
                search_input = (
                    ui.input(
                        label="Search configurations",
                        placeholder="Type to filter configurations...",
                    )
                    .classes("w-full mb-4")
                    .tooltip(
                        "Filter the configuration list by typing keywords. Searches configuration names and paths."
                    )
                )

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
                            if "unit_systems" in config_path.lower():
                                continue

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
                                        path=config_path: self._update_config(
                                            path, e.value
                                        ),
                                    ).classes("flex-shrink-0")
                                elif isinstance(value, (int, float)):
                                    ui.number(
                                        value=value,
                                        format="%.6g",
                                        on_change=lambda e,
                                        path=config_path: self._update_config(
                                            path, e.value
                                        ),
                                    ).classes("w-32 flex-shrink-0")
                                elif isinstance(value, (list, tuple, set)):
                                    ui.input(
                                        value=", ".join(map(str, value)),
                                        on_change=lambda e,
                                        path=config_path: self._update_config(
                                            path, e.value.split(", ")
                                        ),
                                    ).classes("w-64 flex-shrink-0")
                                elif value is None:
                                    ui.input(
                                        value="",
                                        placeholder="None",
                                        on_change=lambda e,
                                        path=config_path: self._update_config(
                                            path, e.value or None
                                        ),
                                    ).classes("w-64 flex-shrink-0")
                                else:
                                    ui.input(
                                        value=str(value),
                                        on_change=lambda e,
                                        path=config_path: self._update_config(
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
                ).tooltip(
                    "Save your configuration settings to a file or load settings from a previously saved file."
                )

                ui.button(
                    "Export Configuration",
                    on_click=self.export,
                    color=self.theme_color,
                    icon="download",
                ).classes("w-full mb-4").tooltip(
                    "Download all current configuration settings as a JSON file. This creates a backup that can be imported later or shared with other users."
                )

                ui.upload(
                    label="Import Configuration",
                    on_upload=self.import_,
                    auto_upload=True,
                ).props(
                    f"outline color={self.theme_color} icon=file_upload accept=.json"
                ).classes("w-full").tooltip(
                    "Upload a previously exported configuration JSON file to restore settings. This will overwrite current configuration values."
                )

    def _on_auto_save_change(self, value: bool):
        """Handle auto-save setting change"""
        self.config.update("global_", auto_save=value)
        # Refresh the UI to update the footer status
        if self.is_open and self.dialog:
            ui.notify(
                f"Auto-save {'enabled' if value else 'disabled'}. "
                f"{'Changes will be saved automatically.' if value else 'You must manually save changes.'}",
                type="info",
            )
            # Refresh the dialog to update button visibility
            self.show()

    def _update_config(self, path: str, value: typing.Any):
        """Update configuration from a flat path"""
        try:
            parts = path.split(".")
            if len(parts) > 1:
                obj_path = ".".join(parts[:-1])
                attr_name = parts[-1]
                self.config.update(obj_path, **{attr_name: value})
            else:
                self.config.update(".", **{path: value})
        except Exception as exc:
            logger.error(f"Failed to update config at path {path}: {exc}")
            ui.notify(f"Failed to update {path}: {str(exc)}", type="negative")

    def export(self):
        """Export configuration to JSON file"""
        try:
            config_json = self.config.export()
            ui.download(config_json.encode(), filename="scada_config.json")
            ui.notify("Configuration exported successfully", type="positive")
        except Exception as exc:
            logger.error(f"Export failed: {exc}")
            ui.notify(f"Export failed: {exc}", type="negative")

    async def import_(self, event):
        """Import configuration from uploaded file"""
        try:
            content = await event.file.read()
            self.config.import_(content.decode("utf-8"))
            ui.notify("Configuration imported successfully", type="positive")
            self.show()
        except Exception as exc:
            logger.error(f"Import failed: {exc}")
            ui.notify(f"Import failed: {exc}", type="negative")

    def reset(self):
        """Reset all configuration to defaults"""

        def confirm_reset():
            self.config.reset()
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
        if not self.config.state.global_.auto_save:
            self.config.save()
            ui.notify("Configuration saved.", type="positive")
        else:
            ui.notify(
                "Auto-save is enabled - changes are saved automatically", type="info"
            )

    def apply_and_close(self):
        """Apply changes and close dialog"""
        if not self.config.state.global_.auto_save:
            self.config.save()
        self.close_dialog()
        ui.notify("Configuration applied", type="positive")

    def close_dialog(self):
        """Close the configuration dialog"""
        if self.dialog:
            self.dialog.close()
            self.is_open = False

    def cleanup(self):
        """Cleanup resources"""
        self.close_dialog()
