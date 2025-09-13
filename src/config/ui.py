"""
Configuration UI Components
"""

import logging
from nicegui import ui

from src.config.manage import ConfigurationManager, ConfigurationState

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
        """
        Show the configuration dialog with customizable parameters

        Args:
            label: Dialog title
            max_width: Maximum width of the dialog
            min_width: Minimum width of the dialog
            height: Height of the dialog
            **kwargs: Additional styling parameters
        """
        if self.config_dialog:
            self.config_dialog.close()

        # Custom CSS for thin scrollbars and responsive design
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
        
        /* Responsive grid layouts */
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
        
        /* Ensure full width for config panels */
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
                        ui.tab("units", label="Units", icon="straighten").classes(
                            "text-xs sm:text-sm"
                        )
                        ui.tab(
                            "pipeline", label="Pipeline", icon="account_tree"
                        ).classes("text-xs sm:text-sm")
                        ui.tab("meters", label="Meters", icon="speed").classes(
                            "text-xs sm:text-sm"
                        )
                        ui.tab("regulators", label="Regulators", icon="tune").classes(
                            "text-xs sm:text-sm"
                        )
                        ui.tab(
                            "import_export", label="I/E", icon="import_export"
                        ).classes("text-xs sm:text-sm")

                    with (
                        ui.tab_panels(tabs, value="global")
                        .classes("flex-1 config-scroll config-content w-full")
                        .style("overflow-y: auto; overflow-x: hidden; width: 100%;")
                    ):
                        # Global Configuration Tab
                        with (
                            ui.tab_panel("global")
                            .classes("w-full p-2 sm:p-4 lg:p-6")
                            .style("width: 100%;")
                        ):
                            self.show_global_config_panel()

                        # Unit Systems Tab
                        with (
                            ui.tab_panel("units")
                            .classes("w-full p-2 sm:p-4 lg:p-6")
                            .style("width: 100%;")
                        ):
                            self.show_units_config_panel()

                        # Pipeline Configuration Tab
                        with (
                            ui.tab_panel("pipeline")
                            .classes("w-full p-2 sm:p-4 lg:p-6")
                            .style("width: 100%;")
                        ):
                            self.show_pipeline_config_panel()

                        # Meters Configuration Tab
                        with (
                            ui.tab_panel("meters")
                            .classes("w-full p-2 sm:p-4 lg:p-6")
                            .style("width: 100%;")
                        ):
                            self.show_meters_config_panel()

                        # Regulators Configuration Tab
                        with (
                            ui.tab_panel("regulators")
                            .classes("w-full p-2 sm:p-4 lg:p-6")
                            .style("width: 100%;")
                        ):
                            self.show_regulators_config_panel()

                        # Import/Export Tab
                        with (
                            ui.tab_panel("import_export")
                            .classes("w-full p-2 sm:p-4 lg:p-6")
                            .style("width: 100%;")
                        ):
                            self.show_import_export_panel()

                # Footer actions
                with ui.row().classes(
                    "w-full p-2 sm:p-4 border-t bg-gray-50 justify-end gap-2 flex-wrap"
                ):
                    ui.button(
                        "Reset",
                        on_click=self.reset_to_defaults,
                        color="red",
                    ).props("outline").classes("text-xs sm:text-sm")
                    ui.button(
                        "Apply & Close",
                        on_click=self.apply_and_close,
                        color=self.theme_color,
                    ).classes("text-xs sm:text-sm")

        self.config_dialog.open()
        self.is_open = True

    def show_global_config_panel(self):
        """Create global configuration panel"""
        config = self.current_config.global_config

        with ui.column().classes("w-full gap-4 config-panel-content"):
            # Theme Configuration
            with ui.card().classes("w-full p-4"):
                ui.label("Appearance").classes("text-lg font-semibold mb-3")

                with ui.row().classes("w-full gap-4 items-center"):
                    ui.label("Theme Color:").classes("w-24")
                    ui.select(
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
                    ).classes("flex-1")

                with ui.row().classes("w-full gap-4 items-center"):
                    ui.label("Dark Mode:").classes("w-24")
                    ui.switch(
                        value=config.dark_mode,
                        on_change=lambda e: self.manager.update_global_config(
                            dark_mode=e.value
                        ),
                    )

            # UI Behavior Configuration
            with ui.card().classes("w-full p-4"):
                ui.label("User Interface").classes("text-lg font-semibold mb-3")

                with ui.row().classes("w-full gap-4 items-center"):
                    ui.label("Show Tooltips:").classes("w-24")
                    ui.switch(
                        value=config.show_tooltips,
                        on_change=lambda e: self.manager.update_global_config(
                            show_tooltips=e.value
                        ),
                    )

                with ui.row().classes("w-full gap-4 items-center"):
                    ui.label("Animations:").classes("w-24")
                    ui.switch(
                        value=config.animation_enabled,
                        on_change=lambda e: self.manager.update_global_config(
                            animation_enabled=e.value
                        ),
                    )

                with ui.row().classes("w-full gap-4 items-center"):
                    ui.label("Auto-save:").classes("w-24")
                    ui.switch(
                        value=config.auto_save,
                        on_change=lambda e: self.manager.update_global_config(
                            auto_save=e.value
                        ),
                    )

    def show_units_config_panel(self):
        """Create unit systems configuration panel"""
        config = self.current_config.global_config

        with ui.column().classes("w-full gap-4 config-panel-content"):
            # Active Unit System Selection
            with ui.card().classes("w-full p-4"):
                ui.label("Active Unit System").classes("text-lg font-semibold mb-3")

                available_systems = self.manager.get_available_unit_systems()

                with ui.row().classes("w-full gap-4 items-center"):
                    ui.label("Current System:").classes("w-32")
                    ui.select(
                        options=available_systems,
                        value=config.unit_system_name,
                        on_change=lambda e: self.manager.update_global_config(
                            unit_system_name=e.value
                        ),
                    ).classes("flex-1")

                    ui.button(
                        "Create Custom System",
                        on_click=self.show_custom_unit_system_creator,
                        color=self.theme_color,
                    ).props("outline")

            # Unit System Preview
            with ui.card().classes("w-full p-4"):
                ui.label("Current Unit System Details").classes(
                    "text-lg font-semibold mb-3"
                )

                current_unit_system = self.manager.get_unit_system()

                with ui.column().classes("w-full"):
                    # Table container with scroll
                    with (
                        ui.element("div")
                        .classes("config-scroll config-content")
                        .style(
                            "max-height: 400px; overflow-y: auto; border: 1px solid #e5e7eb; border-radius: 8px;"
                        )
                    ):
                        with ui.grid(columns=4).classes("w-full gap-2 p-2"):
                            ui.label("Quantity").classes(
                                "font-semibold p-2 bg-gray-100 border-b"
                            )
                            ui.label("Unit").classes(
                                "font-semibold p-2 bg-gray-100 border-b"
                            )
                            ui.label("Display").classes(
                                "font-semibold p-2 bg-gray-100 border-b"
                            )
                            ui.label("Default").classes(
                                "font-semibold p-2 bg-gray-100 border-b"
                            )

                            for quantity, unit_obj in current_unit_system.items():
                                ui.label(quantity.replace("_", " ").title()).classes(
                                    "p-2 border-b"
                                )
                                ui.label(str(unit_obj.unit)).classes(
                                    "p-2 border-b font-mono text-sm"
                                )
                                ui.label(
                                    unit_obj.display or str(unit_obj.unit)
                                ).classes("p-2 border-b")
                                ui.label(
                                    str(unit_obj.default)
                                    if unit_obj.default is not None
                                    else "None"
                                ).classes(
                                    "p-2 border-b font-mono text-xs text-gray-600"
                                )

            # Custom Unit Systems Management
            if config.custom_unit_systems:
                with ui.card().classes("w-full p-4"):
                    ui.label("Custom Unit Systems").classes(
                        "text-lg font-semibold mb-3"
                    )

                    for system_name in config.custom_unit_systems:
                        with ui.row().classes(
                            "w-full items-center justify-between p-2 border rounded"
                        ):
                            ui.label(system_name).classes("font-medium")
                            with ui.row().classes("gap-2"):
                                ui.button(
                                    "Edit",
                                    on_click=lambda: self.edit_custom_unit_system(
                                        system_name
                                    ),
                                    color=self.theme_color,
                                ).props("outline")
                                ui.button(
                                    "Delete",
                                    on_click=lambda: self.delete_custom_unit_system(
                                        system_name
                                    ),
                                    color="red",
                                ).props("outline")

    def show_pipeline_config_panel(self):
        """Create pipeline configuration panel"""
        config = self.current_config.pipeline_config
        flow_station_config = self.current_config.flow_station_defaults

        with ui.column().classes("w-full gap-4 config-panel-content"):
            # Pipeline Properties
            with ui.card().classes("w-full p-4"):
                ui.label("Pipeline Properties").classes("text-lg font-semibold mb-3")

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.input(
                        "Pipeline Name",
                        value=config.pipeline_name,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            pipeline_name=e.value
                        ),
                    )
                    ui.select(
                        label="Flow Type",
                        options=["compressible", "incompressible"],
                        value=config.flow_type,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            flow_type=e.value
                        ),
                    )
                    ui.number(
                        "Max Flow Rate",
                        value=config.max_flow_rate,
                        format="%.0f",
                        on_change=lambda e: self.manager.update_pipeline_config(
                            max_flow_rate=e.value
                        ),
                    )
                    ui.select(
                        label="Max Flow Rate Unit",
                        options=[
                            "MSCF/day",
                            "MMscf/day",
                            "ft3/s",
                            "m3/s",
                            "L/s",
                            "gpm",
                        ],
                        value=config.max_flow_rate_unit,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            max_flow_rate_unit=e.value
                        ),
                    )

            # Fluid Properties
            with ui.card().classes("w-full p-4"):
                ui.label("Default Fluid Properties").classes(
                    "text-lg font-semibold mb-3"
                )

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.input(
                        "Fluid Name",
                        value=config.default_fluid_name,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            default_fluid_name=e.value
                        ),
                    )
                    ui.select(
                        label="Fluid Phase",
                        options=["gas", "liquid"],
                        value=config.default_fluid_phase,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            default_fluid_phase=e.value
                        ),
                    )
                    ui.number(
                        "Initial Temperature",
                        value=config.initial_temperature,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            initial_temperature=e.value
                        ),
                    )
                    ui.select(
                        label="Temperature Unit",
                        options=["degF", "degC", "degR", "K"],
                        value=config.initial_temperature_unit,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            initial_temperature_unit=e.value
                        ),
                    )
                    ui.number(
                        "Initial Pressure",
                        value=config.initial_pressure,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            initial_pressure=e.value
                        ),
                    )
                    ui.select(
                        label="Pressure Unit",
                        options=["psi", "bar", "Pa", "kPa", "MPa"],
                        value=config.initial_pressure_unit,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            initial_pressure_unit=e.value
                        ),
                    )
                    ui.number(
                        "Molecular Weight",
                        value=config.molecular_weight,
                        precision=3,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            molecular_weight=e.value
                        ),
                    )
                    ui.select(
                        label="Molecular Weight Unit",
                        options=["g/mol", "kg/mol", "lbm/lbmol"],
                        value=config.molecular_weight_unit,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            molecular_weight_unit=e.value
                        ),
                    )

            # Flow Station Units
            with ui.card().classes("w-full p-4"):
                ui.label("Flow Station Unit Defaults").classes(
                    "text-lg font-semibold mb-3"
                )

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.select(
                        label="Pressure Unit",
                        options=["psi", "bar", "Pa", "kPa", "MPa"],
                        value=flow_station_config.pressure_unit,
                        on_change=lambda e: self.manager.update_flow_station_defaults(
                            pressure_unit=e.value
                        ),
                    )
                    ui.select(
                        label="Temperature Unit",
                        options=["degF", "degC", "degR", "K"],
                        value=flow_station_config.temperature_unit,
                        on_change=lambda e: self.manager.update_flow_station_defaults(
                            temperature_unit=e.value
                        ),
                    )
                    ui.select(
                        label="Flow Unit",
                        options=[
                            "MSCF/day",
                            "MMscf/day",
                            "ft3/s",
                            "m3/s",
                            "L/s",
                            "gpm",
                        ],
                        value=flow_station_config.flow_unit,
                        on_change=lambda e: self.manager.update_flow_station_defaults(
                            flow_unit=e.value
                        ),
                    )
                    ui.input(
                        "Upstream Station Name",
                        value=flow_station_config.upstream_station_name,
                        on_change=lambda e: self.manager.update_flow_station_defaults(
                            upstream_station_name=e.value
                        ),
                    )
                    ui.input(
                        "Downstream Station Name",
                        value=flow_station_config.downstream_station_name,
                        on_change=lambda e: self.manager.update_flow_station_defaults(
                            downstream_station_name=e.value
                        ),
                    )

            # Default Pipe Properties
            with ui.card().classes("w-full p-4"):
                ui.label("Default Pipe Properties").classes(
                    "text-lg font-semibold mb-3"
                )

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.number(
                        "Length",
                        value=config.default_pipe_length,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            default_pipe_length=e.value
                        ),
                    )
                    ui.number(
                        "Diameter",
                        value=config.default_pipe_diameter,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            default_pipe_diameter=e.value
                        ),
                    )
                    ui.number(
                        "Roughness",
                        value=config.default_pipe_roughness,
                        step=0.0001,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            default_pipe_roughness=e.value
                        ),
                    )
                    ui.number(
                        "Efficiency",
                        value=config.default_efficiency,
                        min=0.1,
                        max=1.0,
                        step=0.01,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            default_efficiency=e.value
                        ),
                    )
                    ui.number(
                        "Upstream Pressure",
                        value=config.default_upstream_pressure,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            default_upstream_pressure=e.value
                        ),
                    )
                    ui.number(
                        "Downstream Pressure",
                        value=config.default_downstream_pressure,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            default_downstream_pressure=e.value
                        ),
                    )
                    ui.input(
                        "Material",
                        value=config.default_pipe_material,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            default_pipe_material=e.value
                        ),
                    )

            # Visualization Settings
            with ui.card().classes("w-full p-4"):
                ui.label("Visualization Settings").classes("text-lg font-semibold mb-3")

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.number(
                        "Scale Factor",
                        value=config.scale_factor,
                        min=0.01,
                        step=0.01,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            scale_factor=e.value
                        ),
                    )
                    ui.number(
                        "Connector Length",
                        value=config.connector_length,
                        min=0.01,
                        step=0.01,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            connector_length=e.value
                        ),
                    )

                with ui.row().classes("w-full gap-4 items-center"):
                    ui.label("Alert Errors:").classes("w-24")
                    ui.switch(
                        value=config.alert_errors,
                        on_change=lambda e: self.manager.update_pipeline_config(
                            alert_errors=e.value
                        ),
                    )

    def show_meters_config_panel(self):
        """Create meters configuration panel"""
        config = self.current_config.default_meter_config

        with ui.column().classes("w-full gap-4 config-panel-content"):
            # General Meter Settings
            with ui.card().classes("w-full p-4"):
                ui.label("General Meter Settings").classes("text-lg font-semibold mb-3")

                with ui.element("div").classes("config-grid-responsive grid-cols-3"):
                    ui.input(
                        "Default Width",
                        value=config.width,
                        on_change=lambda e: self.manager.update_meter_config(
                            width=e.value
                        ),
                    )
                    ui.input(
                        "Default Height",
                        value=config.height,
                        on_change=lambda e: self.manager.update_meter_config(
                            height=e.value
                        ),
                    )
                    ui.number(
                        "Precision",
                        value=config.precision,
                        min=0,
                        max=10,
                        on_change=lambda e: self.manager.update_meter_config(
                            precision=e.value
                        ),
                    )
                    ui.number(
                        "Animation Speed",
                        value=config.animation_speed,
                        min=1.0,
                        max=20.0,
                        step=0.5,
                        on_change=lambda e: self.manager.update_meter_config(
                            animation_speed=e.value
                        ),
                    )
                    ui.number(
                        "Animation Interval",
                        value=config.animation_interval,
                        min=0.01,
                        max=1.0,
                        step=0.01,
                        on_change=lambda e: self.manager.update_meter_config(
                            animation_interval=e.value
                        ),
                    )
                    ui.number(
                        "Update Interval",
                        value=config.update_interval,
                        min=0.1,
                        max=10.0,
                        step=0.1,
                        on_change=lambda e: self.manager.update_meter_config(
                            update_interval=e.value
                        ),
                    )

                with ui.row().classes("w-full gap-4 items-center"):
                    ui.label("Alert Errors:").classes("w-24")
                    ui.switch(
                        value=config.alert_errors,
                        on_change=lambda e: self.manager.update_meter_config(
                            alert_errors=e.value
                        ),
                    )

            # Pressure Meter Defaults
            with ui.card().classes("w-full p-4"):
                ui.label("Pressure Meter Defaults").classes(
                    "text-lg font-semibold mb-3"
                )

                with ui.element("div").classes("config-grid-responsive grid-cols-3"):
                    ui.number(
                        "Max Value",
                        value=config.pressure_max_value,
                        on_change=lambda e: self.manager.update_meter_config(
                            pressure_max_value=e.value
                        ),
                    )
                    ui.input(
                        "Units",
                        value=config.pressure_units,
                        on_change=lambda e: self.manager.update_meter_config(
                            pressure_units=e.value
                        ),
                    )
                    ui.input(
                        "Height",
                        value=config.pressure_height,
                        on_change=lambda e: self.manager.update_meter_config(
                            pressure_height=e.value
                        ),
                    )

            # Temperature Meter Defaults
            with ui.card().classes("w-full p-4"):
                ui.label("Temperature Meter Defaults").classes(
                    "text-lg font-semibold mb-3"
                )

                with ui.element("div").classes("config-grid-responsive grid-cols-4"):
                    ui.number(
                        "Min Value",
                        value=config.temperature_min_value,
                        on_change=lambda e: self.manager.update_meter_config(
                            temperature_min_value=e.value
                        ),
                    )
                    ui.number(
                        "Max Value",
                        value=config.temperature_max_value,
                        on_change=lambda e: self.manager.update_meter_config(
                            temperature_max_value=e.value
                        ),
                    )
                    ui.input(
                        "Units",
                        value=config.temperature_units,
                        on_change=lambda e: self.manager.update_meter_config(
                            temperature_units=e.value
                        ),
                    )
                    ui.input(
                        "Width",
                        value=config.temperature_width,
                        on_change=lambda e: self.manager.update_meter_config(
                            temperature_width=e.value
                        ),
                    )
                    ui.input(
                        "Height",
                        value=config.temperature_height,
                        on_change=lambda e: self.manager.update_meter_config(
                            temperature_height=e.value
                        ),
                    )
                    ui.number(
                        "Precision",
                        value=config.temperature_precision,
                        min=0,
                        max=10,
                        on_change=lambda e: self.manager.update_meter_config(
                            temperature_precision=e.value
                        ),
                    )

            # Flow Meter Defaults
            with ui.card().classes("w-full p-4"):
                ui.label("Flow Meter Defaults").classes("text-lg font-semibold mb-3")

                with ui.element("div").classes("config-grid-responsive grid-cols-4"):
                    ui.number(
                        "Max Value",
                        value=config.flow_max_value,
                        on_change=lambda e: self.manager.update_meter_config(
                            flow_max_value=e.value
                        ),
                    )
                    ui.input(
                        "Units",
                        value=config.flow_units,
                        on_change=lambda e: self.manager.update_meter_config(
                            flow_units=e.value
                        ),
                    )
                    ui.input(
                        "Height",
                        value=config.flow_height,
                        on_change=lambda e: self.manager.update_meter_config(
                            flow_height=e.value
                        ),
                    )
                    ui.number(
                        "Precision",
                        value=config.flow_precision,
                        min=0,
                        max=10,
                        on_change=lambda e: self.manager.update_meter_config(
                            flow_precision=e.value
                        ),
                    )
                    ui.select(
                        label="Flow Direction",
                        options=["east", "west", "north", "south"],
                        value=config.flow_direction,
                        on_change=lambda e: self.manager.update_meter_config(
                            flow_direction=e.value
                        ),
                    )

    def show_regulators_config_panel(self):
        """Create regulators configuration panel"""
        config = self.current_config.default_regulator_config

        with ui.column().classes("w-full gap-4 config-panel-content"):
            # General Regulator Settings
            with ui.card().classes("w-full p-4"):
                ui.label("General Regulator Settings").classes(
                    "text-lg font-semibold mb-3"
                )

                with ui.element("div").classes("config-grid-responsive grid-cols-3"):
                    ui.input(
                        "Default Width",
                        value=config.width,
                        on_change=lambda e: self.manager.update_regulator_config(
                            width=e.value
                        ),
                    )
                    ui.input(
                        "Default Height",
                        value=config.height,
                        on_change=lambda e: self.manager.update_regulator_config(
                            height=e.value
                        ),
                    )
                    ui.number(
                        "Precision",
                        value=config.precision,
                        min=0,
                        max=10,
                        on_change=lambda e: self.manager.update_regulator_config(
                            precision=e.value
                        ),
                    )
                    ui.number(
                        "Step Size",
                        value=config.step,
                        min=0.001,
                        step=0.001,
                        on_change=lambda e: self.manager.update_regulator_config(
                            step=e.value
                        ),
                    )

                with ui.row().classes("w-full gap-4 items-center"):
                    ui.label("Alert Errors:").classes("w-24")
                    ui.switch(
                        value=config.alert_errors,
                        on_change=lambda e: self.manager.update_regulator_config(
                            alert_errors=e.value
                        ),
                    )

            # Pressure Regulator Defaults
            with ui.card().classes("w-full p-4"):
                ui.label("Pressure Regulator Defaults").classes(
                    "text-lg font-semibold mb-3"
                )

                with ui.element("div").classes("config-grid-responsive grid-cols-2"):
                    ui.number(
                        "Max Value",
                        value=config.pressure_max_value,
                        on_change=lambda e: self.manager.update_regulator_config(
                            pressure_max_value=e.value
                        ),
                    )
                    ui.input(
                        "Units",
                        value=config.pressure_units,
                        on_change=lambda e: self.manager.update_regulator_config(
                            pressure_units=e.value
                        ),
                    )

            # Temperature Regulator Defaults
            with ui.card().classes("w-full p-4"):
                ui.label("Temperature Regulator Defaults").classes(
                    "text-lg font-semibold mb-3"
                )

                with ui.element("div").classes("config-grid-responsive grid-cols-3"):
                    ui.number(
                        "Min Value",
                        value=config.temperature_min_value,
                        on_change=lambda e: self.manager.update_regulator_config(
                            temperature_min_value=e.value
                        ),
                    )
                    ui.number(
                        "Max Value",
                        value=config.temperature_max_value,
                        on_change=lambda e: self.manager.update_regulator_config(
                            temperature_max_value=e.value
                        ),
                    )
                    ui.input(
                        "Units",
                        value=config.temperature_units,
                        on_change=lambda e: self.manager.update_regulator_config(
                            temperature_units=e.value
                        ),
                    )

    def show_import_export_panel(self):
        """Create import/export configuration panel"""
        with ui.column().classes("w-full gap-4 config-panel-content"):
            # Export Configuration
            with ui.card().classes("w-full p-4"):
                ui.label("Export Configuration").classes("text-lg font-semibold mb-3")
                ui.label("Download your current configuration as a JSON file.").classes(
                    "text-sm text-gray-600 mb-3"
                )

                ui.button(
                    "Download Configuration",
                    on_click=self.export_configuration,
                    color=self.theme_color,
                    icon="download",
                ).classes("w-full")

            # Import Configuration
            with ui.card().classes("w-full p-4"):
                ui.label("Import Configuration").classes("text-lg font-semibold mb-3")
                ui.label("Upload a configuration file to restore settings.").classes(
                    "text-sm text-gray-600 mb-3"
                )

                self.import_upload = (
                    ui.upload(
                        on_upload=self.import_configuration,
                        max_file_size=1024 * 1024,  # 1MB limit
                    )
                    .props('accept=".json"')
                    .classes("w-full")
                )

            # Configuration Info
            with ui.card().classes("w-full p-4"):
                ui.label("Configuration Information").classes(
                    "text-lg font-semibold mb-3"
                )

                config = self.current_config

                with ui.column().classes("gap-2"):
                    ui.label(f"Version: {config.version}").classes("font-mono")
                    ui.label(f"Last Updated: {config.last_updated}").classes(
                        "font-mono"
                    )
                    ui.label(f"Config ID: {self.manager.id}").classes(
                        "font-mono text-xs"
                    )

    def show_custom_unit_system_creator(self):
        """Show dialog to create custom unit system"""
        # This will reuse the existing custom unit system dialog from manage.py
        # For now, just show a notification
        ui.notify(
            "Custom unit system creator - feature will be integrated", type="info"
        )

    def edit_custom_unit_system(self, system_name: str):
        """Edit existing custom unit system"""
        ui.notify(f"Editing {system_name} - feature will be integrated", type="info")

    def delete_custom_unit_system(self, system_name: str):
        """Delete custom unit system"""

        def confirm_delete():
            config = self.current_config.global_config
            if system_name in config.custom_unit_systems:
                del config.custom_unit_systems[system_name]
                self.manager.update_global_config(
                    custom_unit_systems=config.custom_unit_systems
                )
                ui.notify(f"Deleted unit system: {system_name}", type="positive")
                # Refresh the panel
                self.show()

        with ui.dialog() as dialog:
            with ui.card():
                ui.label(f'Delete unit system "{system_name}"?')
                with ui.row():
                    ui.button("Cancel", on_click=dialog.close)
                    ui.button(
                        "Delete",
                        on_click=lambda: (confirm_delete(), dialog.close()),
                        color="red",
                    )
        dialog.open()

    def export_configuration(self):
        """Export configuration to file"""
        try:
            config_json = self.manager.export_configuration()
            # Use NiceGUI's download functionality
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
            # Refresh the dialog
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

    def apply_and_close(self):
        """Apply changes and close dialog"""
        ui.notify("Configuration saved", type="positive")
        self.close_dialog()

    def close_dialog(self):
        """Close the configuration dialog"""
        if self.config_dialog:
            self.config_dialog.close()
            self.config_dialog = None
        self.is_open = False

    def cleanup(self):
        """Cleanup resources"""
        self.manager.remove_observer(self.on_config_change)
        self.close_dialog()

    def __del__(self):
        self.cleanup()


# Global configuration UI instance will be created with manager
# config_ui = ConfigurationUI(manager)
