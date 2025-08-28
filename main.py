from nicegui import ui
from src.units import Quantity
from src.components import (
    FlowMeter,
    FlowStation,
    Pipeline,
    PressureGauge,
    TemperatureGauge,
    Regulator,
    Pipe,
    PipeDirection,
)
from src.properties import Fluid, PipeProperties


def main():
    """Main function demonstrating Regulators in a SCADA context."""

    container = ui.column().style(
        "max-width: 1200px; margin: auto; with: 90%; padding-block: 40px;"
    )
    with container:
        ui.label("Flow Station SCADA System").classes(
            "text-4xl text-center text-blue-600 mb-8"
        )

        ###################
        # Pipeline System #
        ###################
        pipe1_props = PipeProperties(
            length=Quantity(50, "m"),
            internal_diameter=Quantity(0.3, "m"),
            upstream_pressure=Quantity(150, "kPa"),
            downstream_pressure=Quantity(120, "kPa"),
            material="Steel",
            roughness=Quantity(0.001, "m"),
            efficiency=0.95,
        )

        pipe2_props = PipeProperties(
            length=Quantity(75, "m"),
            internal_diameter=Quantity(0.2, "m"),
            upstream_pressure=Quantity(120, "kPa"),
            downstream_pressure=Quantity(80, "kPa"),
            material="Steel",
            roughness=Quantity(0.001, "m"),
            efficiency=0.90,
        )

        pipe3_props = PipeProperties(
            length=Quantity(60, "m"),
            internal_diameter=Quantity(0.5, "m"),
            upstream_pressure=Quantity(80, "kPa"),
            downstream_pressure=Quantity(50, "kPa"),
            material="Steel",
            roughness=Quantity(0.001, "m"),
            efficiency=0.85,
        )

        fluid = Fluid(
            density=Quantity(1000, "kg/m^3"),
            viscosity=Quantity(0.001, "Pa*s"),
            temperature=Quantity(20, "°C"),
        )

        # Create pipes
        pipe1 = Pipe(
            properties=pipe1_props,
            fluid=fluid,
            direction=PipeDirection.EAST,
            name="Inlet Pipe",
        )

        pipe2 = Pipe(
            properties=pipe2_props,
            fluid=fluid,
            direction=PipeDirection.NORTH,
            name="Riser Pipe",
        )

        pipe3 = Pipe(
            properties=pipe3_props,
            fluid=fluid,
            direction=PipeDirection.EAST,
            name="Outlet Pipe",
        )

        pipeline = Pipeline(
            pipes=[pipe1, pipe2, pipe3],
            fluid=fluid,
            name="Main Pipeline",
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
            value=45.5,
            min_value=0,
            max_value=100,
            units="ft³/sec",
            label="Upstream Flow Rate",
            alarm_high=90,
            alarm_low=10,
            update_func=lambda: pipeline.inlet_flow_rate.magnitude,
        )
        downstream_flow_meter = FlowMeter(
            value=30.2,
            min_value=0,
            max_value=100,
            units="ft³/sec",
            label="Downstream Flow Rate",
            alarm_high=90,
            alarm_low=10,
            update_func=lambda: pipeline.outlet_flow_rate.magnitude,
        )
        upstream_pressure_gauge = PressureGauge(
            value=65.2,
            min_value=0,
            max_value=120,
            units="PSI",
            label="Upstream Pressure",
            alarm_high=100,
            alarm_low=20,
            update_func=lambda: pipeline.upstream_pressure.magnitude,
        )
        downstream_pressure_gauge = PressureGauge(
            value=45.8,
            min_value=0,
            max_value=120,
            units="PSI",
            label="Downstream Pressure",
            alarm_high=100,
            alarm_low=20,
            update_func=lambda: pipeline.downstream_pressure.magnitude,
        )
        temp_gauge = TemperatureGauge(
            value=78.5,
            min_value=0,
            max_value=150,
            units="°C",
            label="Fluid Temperature",
            alarm_high=120,
            alarm_low=5,
        )

        # Control functions for regulators
        def update_pressure(value):
            """Update pressure and corresponding gauge."""
            pipeline.set_upstream_pressure(value).update_viz()

        def update_temperature(value):
            """Update temperature and corresponding gauge."""
            temp_gauge.set_value(value)

        # Create regulators for control
        upstream_pressure_regulator = Regulator(
            value=65.2,
            min_value=0,
            max_value=120,
            step=0.5,
            units="PSI",
            label="Pressure Control",
            setter_func=update_pressure,
            alarm_high=100,
            alarm_low=20,
            precision=1,
            width="300px",
            height="240px",
        )
        upstream_temperature_regulator = Regulator(
            value=78.5,
            min_value=0,
            max_value=150,
            step=1.0,
            units="°C",
            label="Temperature Control",
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
                upstream_pressure_regulator,
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
