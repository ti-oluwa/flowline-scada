"""
Main SCADA Pipeline Management System Application.

This is the primary entry point for the Dynamic Pipeline Builder system,
providing an intuitive interface for pipeline construction and management.
"""

import logging
from nicegui import ui, app
from src.builder import create_pipeline_builder_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def create_main_app():
    """Create the main SCADA Pipeline Management System application."""
    
    # Main layout container
    main_container = ui.column().classes('w-full h-screen bg-gray-50')
    
    with main_container:
        # Header
        header = ui.row().classes('w-full bg-blue-600 text-white p-4 shadow-lg')
        with header:
            ui.icon('engineering').classes('text-3xl mr-3')
            ui.label('SCADA Pipeline Management System').classes('text-2xl font-bold flex-1')
            
            # Status indicator
            status_container = ui.row().classes('gap-2 items-center')
            with status_container:
                ui.icon('circle', color='green').classes('text-sm')
                ui.label('System Online').classes('text-sm')
        
        # Main content area with the pipeline builder
        content_area = ui.column().classes('flex-1 w-full overflow-auto p-4')
        
        with content_area:
            # Welcome message
            welcome_card = ui.card().classes('w-full p-4 mb-4 bg-gradient-to-r from-blue-50 to-indigo-50 border-l-4 border-blue-500')
            with welcome_card:
                ui.label('Dynamic Pipeline Builder').classes('text-xl font-semibold text-blue-800 mb-2')
                ui.label('Design, configure, and monitor industrial pipelines with real-time validation and automatic instrumentation.').classes('text-blue-700')
            
            # Pipeline builder interface
            pipeline_builder_container = ui.column().classes('w-full')
            with pipeline_builder_container:
                create_pipeline_builder_app()
    
    return main_container


def main():
    """Main application entry point."""
    logger.info("Starting SCADA Pipeline Management System")
    
    # Configure NiceGUI application
    try:
        app.add_static_files('/static', 'static')  # Add static file serving if needed
    except Exception:
        pass  # Static files directory might not exist, that's OK
    
    # Create the main application
    create_main_app()
    
    # Start the application
    logger.info("Application initialized successfully")
    
    # Run with production-ready configuration
    ui.run(
        title='SCADA Pipeline Management System',
        port=8080,
        host='0.0.0.0',
        reload=False,  # Set to True for development
        show=True,
        favicon='🔧',
        dark=False  # Use light theme by default
    )


if __name__ == "__main__":
    main()

    container = ui.column().style(
        "max-width: 1200px; margin: auto; with: 90%; padding-block: 40px;"
    )
    with container:
        ui.label("Legacy SCADA System Demo").classes(
            "text-4xl text-center text-blue-600 mb-8"
        )

        ###################
        # Pipeline System #
        ###################

        fluid = Fluid.from_coolprop(
            fluid_name="Methane",
            phase="gas",
            pressure=Quantity(1000, "psi"),
            temperature=Quantity(20, "°C"),
        )

        # Create pipes
        pipe1 = Pipe(
            length=Quantity(10, "m"),
            internal_diameter=Quantity(0.3, "m"),
            upstream_pressure=Quantity(1200, "psi"),
            downstream_pressure=Quantity(1120, "psi"),
            material="Steel",
            roughness=Quantity(0.001, "m"),
            efficiency=0.95,
            fluid=fluid,
            direction=PipeDirection.EAST,
            name="Inlet Pipe",
        )

        pipe2 = Pipe(
            length=Quantity(75, "m"),
            internal_diameter=Quantity(0.2, "m"),
            upstream_pressure=Quantity(1111, "psi"),
            downstream_pressure=Quantity(945, "psi"),
            material="Steel",
            roughness=Quantity(0.001, "m"),
            efficiency=0.90,
            fluid=fluid,
            direction=PipeDirection.EAST,
            name="Riser Pipe",
        )

        pipe3 = Pipe(
            length=Quantity(60, "m"),
            internal_diameter=Quantity(0.2, "m"),
            upstream_pressure=Quantity(800, "psi"),
            downstream_pressure=Quantity(792, "psi"),
            material="Steel",
            roughness=Quantity(0.001, "m"),
            efficiency=0.85,
            fluid=fluid,
            direction=PipeDirection.EAST,
            name="Outlet Pipe",
        )

        pipeline = Pipeline(
            pipes=[pipe1, pipe2, pipe3],
            fluid=fluid,
            name="Main Pipeline",
            max_flow_rate=Quantity(100, "ft³/sec"),
            connector_length=Quantity(0.1, "m"),
        )
        ui.label("Pipeline Visualization").classes(
            "text-2xl text-center text-gray-700 mb-4"
        )
        pipeline.show(label="Pipeline System", width="100%", height="400px")

        #################
        # Flow Stations #
        #################
        ui.separator().classes("my-4")
        # Create meters
        upstream_flow_meter = FlowMeter(
            min_value=0,
            max_value=200,
            units="ft³/sec",
            label="Upstream Flow Rate",
            alarm_high=150,
            alarm_low=10,
            update_func=lambda: pipeline.inlet_flow_rate.magnitude,
        )
        downstream_flow_meter = FlowMeter(
            min_value=0,
            max_value=200,
            units="ft³/sec",
            label="Downstream Flow Rate",
            alarm_high=150,
            alarm_low=10,
            update_func=lambda: pipeline.outlet_flow_rate.magnitude,
        )
        upstream_pressure_gauge = PressureGauge(
            min_value=0,
            max_value=1500,
            units="PSI",
            label="Upstream Pressure",
            alarm_high=1200,
            alarm_low=20,
            update_func=lambda: pipeline.upstream_pressure.magnitude,
        )
        downstream_pressure_gauge = PressureGauge(
            min_value=0,
            max_value=1500,
            units="PSI",
            label="Downstream Pressure",
            alarm_high=1200,
            alarm_low=20,
            update_func=lambda: pipeline.downstream_pressure.magnitude,
        )
        temp_gauge = TemperatureGauge(
            min_value=0,
            max_value=150,
            units="°C",
            label="Fluid Temperature",
            alarm_high=120,
            alarm_low=5,
            update_func=lambda: pipeline.fluid.temperature.magnitude
            if pipeline.fluid
            else None,
        )

        # Control functions for regulators
        def update_initial_upstream_pressure(value):
            """Update pressure and corresponding gauge."""
            pipeline.set_initial_upstream_pressure(value).update_viz()

        def update_initial_downstream_pressure(value):
            """Update pressure and corresponding gauge."""
            pipeline.set_initial_downstream_pressure(value).update_viz()

        def update_temperature(value):
            """Update temperature and corresponding gauge."""
            pipeline.set_upstream_temperature(value).update_viz()

        # Create regulators for control
        initial_upstream_pressure_regulator = Regulator(
            value=pipeline.upstream_pressure.magnitude,
            min_value=0,
            max_value=1500,
            step=0.5,
            units="PSI",
            label="Upstream (Operating) Pressure Control",
            setter_func=update_initial_upstream_pressure,
            alarm_high=1200,
            alarm_low=20,
            precision=1,
            width="300px",
            height="240px",
        )
        initial_downstream_pressure_regulator = Regulator(
            value=pipeline.downstream_pressure.magnitude,
            min_value=0,
            max_value=1500,
            step=0.5,
            units="PSI",
            label="Initial Pipe Downstream Pressure Control",
            setter_func=update_initial_downstream_pressure,
            alarm_high=1200,
            alarm_low=20,
            precision=1,
            width="300px",
            height="240px",
        )
        upstream_temperature_regulator = Regulator(
            value=pipeline.fluid.temperature.magnitude if pipeline.fluid else 0,
            min_value=0,
            max_value=150,
            step=1.0,
            units="°C",
            label="Operating Temperature Control",
            setter_func=update_temperature,
            alarm_high=120,
            alarm_low=5,
            precision=0,
            width="300px",
            height="240px",
        )

        upstream_flow_station = FlowStation(
            meters=[
                upstream_flow_meter,
                upstream_pressure_gauge,
                temp_gauge,
            ],
            regulators=[
                initial_upstream_pressure_regulator,
                initial_downstream_pressure_regulator,
                upstream_temperature_regulator,
            ],
            name="Upstream Flow Station",
            width="100%",
            height="400px",
        )
        downstream_flow_station = FlowStation(
            meters=[downstream_flow_meter, downstream_pressure_gauge],
            regulators=[],
            name="Downstream Flow Station",
            width="100%",
            height="400px",
        )
        ui.label("Flow Control Panel").classes(
            "text-2xl text-center text-gray-700 mb-4"
        )
        upstream_flow_station.show()
        downstream_flow_station.show()


if __name__ in {"__main__", "__mp_main__"}:
    main()
    ui.run(title="Flowstation SCADA", favicon="🏭", port=8084)
