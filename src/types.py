import enum
import typing
import attrs
import cattrs
from datetime import datetime
from pint.facets.plain import PlainQuantity

from src.units import Quantity, Unit


def structure_quantity(obj: typing.Any, _) -> PlainQuantity:
    """Convert a dict with 'magnitude' and 'units' to a Pint Quantity."""
    if isinstance(obj, PlainQuantity):
        return Quantity(obj.magnitude, obj.units)
    if isinstance(obj, dict) and "magnitude" in obj and "units" in obj:
        return Quantity(obj["magnitude"], obj["units"])
    raise ValueError(f"Cannot structure {obj} as PlainQuantity")


def unstructure_quantity(obj: PlainQuantity) -> dict:
    """Convert a Pint Quantity to a dict with 'magnitude' and 'units'."""
    return {"magnitude": obj.magnitude, "units": str(obj.units)}


def structure_unit(obj: typing.Any, _: typing.Type[Unit]) -> Unit:
    """Convert a string to a Pint Unit."""
    if isinstance(obj, Unit):
        return obj
    if isinstance(obj, str):
        return Unit(obj)
    raise ValueError(f"Cannot structure {obj} as Unit")


def unstructure_unit(obj: Unit) -> str:
    """Convert a Pint Unit to a string."""
    return str(obj)


converter = cattrs.Converter()
converter.register_structure_hook(PlainQuantity, structure_quantity)
converter.register_unstructure_hook(PlainQuantity, unstructure_quantity)
converter.register_structure_hook(Unit, structure_unit)
converter.register_unstructure_hook(Unit, unstructure_unit)


class FlowEquation(str, enum.Enum):
    """Enumeration of supported flow equations."""

    DARCY_WEISBACH = "Darcy-Weisbach"
    WEYMOUTH = "Weymouth"
    MODIFIED_PANHANDLE_A = "Modified Panhandle A"
    MODIFIED_PANHANDLE_B = "Modified Panhandle B"

    def __str__(self) -> str:
        return self.value


class FlowType(str, enum.Enum):
    """Enumeration of flow types for pipes."""

    COMPRESSIBLE = "compressible"
    """Compressible flow (e.g., gases). With the flow type, the volumetric rate in pipes will vary with pressure and temperature."""
    INCOMPRESSIBLE = "incompressible"
    """Incompressible flow (e.g., liquids). The volumetric rate in pipes remains constant regardless of pressure changes."""

    def __str__(self) -> str:
        return self.value


class PipeDirection(str, enum.Enum):
    """Enumeration for pipe flow directions."""

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"

    def __str__(self) -> str:
        return self.value


class PipelineEvent(enum.Enum):
    """Events that can occur during pipeline construction."""

    PIPE_ADDED = "pipe_added"
    """Sent when a pipe is added to the pipeline."""
    PIPE_REMOVED = "pipe_removed"
    """Sent when a pipe is removed from the pipeline."""
    PIPE_MOVED = "pipe_moved"
    """Sent when a pipe is moved within the pipeline."""
    PROPERTIES_UPDATED = "properties_updated"
    """Sent when the properties of a pipe are updated."""
    VALIDATION_CHANGED = "validation_changed"
    """Sent when the validation state of a pipe changes."""
    METERS_UPDATED = "meters_updated"
    """Sent when the meters associated with a pipe are updated."""

    def __str__(self) -> str:
        return self.value


@attrs.define(slots=True)
class PipeConfig:
    """Configuration for a single pipe component."""

    name: str
    """Name of the pipe"""
    length: Quantity
    """Length of the pipe"""
    internal_diameter: Quantity
    """Internal diameter of the pipe"""
    upstream_pressure: Quantity
    """Upstream pressure of the pipe"""
    downstream_pressure: Quantity
    """Downstream pressure of the pipe"""
    material: str = "Steel"
    """Material of the pipe"""
    roughness: Quantity = attrs.field(factory=lambda: Quantity(0.0001, "m"))  # type: ignore
    """Roughness of the pipe material"""
    efficiency: float = 1.0
    """Efficiency of the pipe (0 < efficiency <= 1)"""
    elevation_difference: Quantity = attrs.field(factory=lambda: Quantity(0, "m"))  # type: ignore
    """Elevation difference between upstream and downstream"""
    direction: PipeDirection = PipeDirection.EAST
    """Direction of flow in the pipe"""
    scale_factor: float = 0.1
    """Scale factor for visual representation"""
    max_flow_rate: Quantity = attrs.field(factory=lambda: Quantity(10.0, "ft^3/s"))  # type: ignore
    """Maximum flow rate through the pipe"""
    flow_type: FlowType = FlowType.COMPRESSIBLE
    """Type of flow in the pipe (incompressible or compressible)"""


@attrs.define(slots=True)
class FluidConfig:
    """Configuration for fluid properties."""

    name: str = "Methane"
    """Name of the fluid supported by CoolProp"""
    phase: typing.Literal["gas", "liquid"] = "gas"
    """Phase of the fluid - gas or liquid"""
    temperature: Quantity = attrs.field(factory=lambda: Quantity(60, "degF"))  # type: ignore
    """Temperature of the fluid"""
    pressure: Quantity = attrs.field(factory=lambda: Quantity(100, "psi"))  # type: ignore
    """Pressure of the fluid"""
    molecular_weight: Quantity = attrs.field(factory=lambda: Quantity(16.04, "g/mol"))  # type: ignore
    """Molecular weight of the fluid"""


@attrs.define(slots=True)
class MeterConfig:
    """Configuration for all meter types (PressureGauge, TemperatureGauge, FlowMeter)"""

    min_value: float = 0.0
    """Minimum value for the meter"""
    max_value: float = 100.0
    """Maximum value for the meter"""
    units: str = ""
    """Display units for the meter"""
    label: str = "Meter"
    """Label for the meter"""
    width: str = "200px"
    """Width of the meter"""
    height: str = "200px"
    """Height of the meter"""
    precision: int = 2
    """Precision for the meter"""
    alarm_high: typing.Optional[float] = None
    """High alarm threshold"""
    alarm_low: typing.Optional[float] = None
    """Low alarm threshold"""
    animation_speed: float = 5.0
    """Speed of the animation for value changes"""
    animation_interval: float = 0.1
    """Interval for animation updates"""
    update_interval: float = 1.0
    """Interval in seconds to call the update function"""
    alert_errors: bool = True
    """Whether to alert on errors"""

@attrs.define(slots=True)
class RegulatorConfig:
    """Configuration for regulator components"""

    min_value: float = 0.0
    """Minimum allowable value"""
    max_value: float = 100.0
    """Maximum allowable value"""
    step: float = 0.1
    """Increment step for adjustments"""
    units: str = ""
    """Display units for the regulator"""
    label: str = "Regulator"
    """Label for the regulator"""
    width: str = "280px"
    """Width of the regulator"""
    height: str = "220px"
    """Height of the regulator"""
    precision: int = 3
    """Precision for the regulator"""
    alarm_high: typing.Optional[float] = None
    """High alarm threshold"""
    alarm_low: typing.Optional[float] = None
    """Low alarm threshold"""
    alert_errors: bool = True
    """Whether to alert on errors"""


@attrs.define(slots=True)
class FlowStationConfig:
    """Configuration for complete flow station setup"""

    station_name: str = "Flow Station"
    """Name of the flow station"""
    station_type: typing.Literal["upstream", "downstream"] = "upstream"
    """Type of station - upstream (with regulators) or downstream (meters only)"""
    pressure_unit: typing.Union[str, Unit] = attrs.field(default="psi", converter=Unit)
    """Pressure unit for unit conversions (supported by Pint). Should match meter/regulator display units."""
    temperature_unit: typing.Union[str, Unit] = attrs.field(
        default="degF", converter=Unit
    )
    """Temperature unit for unit conversions (supported by Pint). Should match meter/regulator display units."""
    flow_unit: typing.Union[str, Unit] = attrs.field(default="ft^3/sec", converter=Unit)
    """Flow rate unit for unit conversions (supported by Pint). Should match meter/regulator display units."""
    pressure_config: MeterConfig = attrs.field(
        factory=lambda: MeterConfig(
            label="Pressure", units="PSI", max_value=5000.0, height="180px"
        )
    )
    """Configuration for the pressure meter"""
    temperature_config: MeterConfig = attrs.field(
        factory=lambda: MeterConfig(
            label="Temperature",
            units="°C",
            max_value=300.0,
            width="160px",
            height="240px",
            precision=2,
        )
    )
    """Configuration for the temperature meter"""
    flow_config: MeterConfig = attrs.field(
        factory=lambda: MeterConfig(
            label="Flow Rate",
            units="ft³/sec",
            max_value=200.0,
            height="220px",
            precision=3,
        )
    )
    """Configuration for the flow meter"""
    pressure_regulator_config: RegulatorConfig = attrs.field(
        factory=lambda: RegulatorConfig(
            label="Pressure Control", units="PSI", max_value=5000.0
        )
    )
    """Configuration for the pressure regulator (mostly upstream only)"""
    flow_regulator_config: RegulatorConfig = attrs.field(
        factory=lambda: RegulatorConfig(
            label="Flow Control", units="ft³/sec", max_value=200.0
        )
    )
    """Configuration for the flow regulator (mostly upstream only)"""
    temperature_regulator_config: RegulatorConfig = attrs.field(
        factory=lambda: RegulatorConfig(
            label="Temperature Control",
            units="°F",
            min_value=-40.0,
            max_value=300.0,
            precision=2,
        )
    )
    """Configuration for the temperature regulator (mostly upstream only)"""


@attrs.define(slots=True)
class GlobalConfig:
    """Global application configuration"""

    theme_color: str = "blue"
    """Primary theme color for the application"""
    unit_system_name: str = "imperial"
    """Name of the active unit system"""
    custom_unit_systems: typing.Dict[str, dict] = attrs.field(factory=dict)
    """Custom unit systems defined by user"""
    auto_save: bool = True
    """Whether to auto-save configurations"""


@attrs.define(slots=True)
class PipelineConfig:
    """Pipeline-specific configuration"""

    name: str = "Main Pipeline"
    """Default name for new pipelines"""
    max_flow_rate: Quantity = attrs.field(factory=lambda: Quantity(100.0, "MMscf/day"))  # type: ignore
    """Default maximum flow rate"""
    flow_type: str = "compressible"
    """Default flow type: 'compressible' or 'incompressible'"""
    connector_length: Quantity = attrs.field(factory=lambda: Quantity(0.1, "m"))  # type: ignore
    """Length of connectors between pipes in meters"""
    scale_factor: float = 0.1
    """Scale factor for visualization"""
    alert_errors: bool = True
    """Whether to show error alerts"""
    fluid: FluidConfig = attrs.field(factory=FluidConfig)
    """Default fluid properties"""
    pipe: PipeConfig = attrs.field(
        factory=lambda: PipeConfig(
            name="Pipe Segment",
            internal_diameter=Quantity(2, "inch"),  # type: ignore
            length=Quantity(100, "m"),  # type: ignore
            upstream_pressure=Quantity(500, "psi"),  # type: ignore
            downstream_pressure=Quantity(400, "psi"),  # type: ignore
        )
    )
    """Default pipe properties"""


@attrs.define(slots=True)
class ConfigurationState:
    """Complete configuration state"""

    global_: GlobalConfig = attrs.field(factory=GlobalConfig)
    """Global application settings"""
    pipeline: PipelineConfig = attrs.field(factory=PipelineConfig)
    """Pipeline-specific settings"""
    flow_station: FlowStationConfig = attrs.field(factory=FlowStationConfig)
    """Default flow station settings"""
    last_updated: str = attrs.field(factory=lambda: datetime.now().isoformat())
    """Timestamp of the last update"""
    version: str = "1.0"
    """Configuration schema version"""


class ConfigStorage(typing.Protocol):
    """Protocol defining a configuration storage backend interface"""

    def read(self, id: str) -> typing.Optional[dict]:
        """Read configuration data by ID"""
        ...

    def update(self, id: str, data: dict, overwrite: bool = ...) -> None:
        """Update configuration data by ID"""
        ...

    def create(self, id: str, data: dict) -> None:
        """Create new configuration data"""
        ...

    def delete(self, id: str) -> None:
        """Delete configuration data by ID"""
        ...
