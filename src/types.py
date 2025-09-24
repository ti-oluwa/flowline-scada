import enum
import typing
import attrs
import cattrs
import re
from pint.facets.plain import PlainQuantity

from src.units import Quantity, Unit, UnitSystem, QuantityUnit, IMPERIAL, SI, OIL_FIELD


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


def structure_quantity_unit(
    obj: typing.Any, _: typing.Type[QuantityUnit]
) -> QuantityUnit:
    """Convert a dict to a QuantityUnit."""
    if isinstance(obj, QuantityUnit):
        return obj
    if isinstance(obj, dict) and "unit" in obj:
        return QuantityUnit(
            unit=obj["unit"],
            display=obj.get("display"),
            default=obj.get("default"),
        )
    raise ValueError(f"Cannot structure {obj} as QuantityUnit")


def unstructure_quantity_unit(obj: QuantityUnit) -> dict:
    """Convert a QuantityUnit to a dict."""
    return {
        "unit": str(obj.unit),
        "display": obj.display,
        "default": obj.default,
    }


def structure_unit_system(obj: typing.Any, _: typing.Type[UnitSystem]) -> UnitSystem:
    """Convert a dict to a UnitSystem."""
    if isinstance(obj, UnitSystem):
        return obj
    if isinstance(obj, dict):
        return UnitSystem(
            obj.get("name", "custom").lower(),
            {
                k: structure_quantity_unit(v, QuantityUnit)
                for k, v in obj.get("quantities", {}).items()
            },
        )
    raise ValueError(f"Cannot structure {obj} as UnitSystem")


def unstructure_unit_system(obj: UnitSystem) -> dict:
    """Convert a UnitSystem to a dict."""
    return {
        "name": obj.name.lower(),
        "quantities": {k: unstructure_quantity_unit(v) for k, v in obj.items()},
    }


converter = cattrs.Converter()
converter.register_structure_hook(PlainQuantity, structure_quantity)
converter.register_unstructure_hook(PlainQuantity, unstructure_quantity)
converter.register_structure_hook(Unit, structure_unit)
converter.register_unstructure_hook(Unit, unstructure_unit)
converter.register_structure_hook(QuantityUnit, structure_quantity_unit)
converter.register_unstructure_hook(QuantityUnit, unstructure_quantity_unit)
converter.register_structure_hook(UnitSystem, structure_unit_system)
converter.register_unstructure_hook(UnitSystem, unstructure_unit_system)


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
    """Compressible flow (e.g., gases). With the flow type, the voluSI rate in pipes will vary with pressure and temperature."""
    INCOMPRESSIBLE = "incompressible"
    """Incompressible flow (e.g., liquids). The voluSI rate in pipes remains constant regardless of pressure changes."""

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


@attrs.define(slots=True, frozen=True)
class PipeLeakConfig:
    """Configuration for a pipe leak."""

    location: float
    """Location of the leak as a fraction along the pipe length (0.0 to 1.0)"""
    diameter: Quantity
    """Diameter of the leak opening"""
    discharge_coefficient: float = 0.6
    """Discharge coefficient for the leak (typically 0.6 for sharp-edged orifice)"""
    active: bool = True
    """Whether the leak is currently active"""
    name: typing.Optional[str] = None
    """Optional name for the leak"""

    def __attrs_post_init__(self):
        """Validate leak configuration after initialization."""
        if self.diameter.magnitude <= 0:
            raise ValueError("Leak diameter must be positive")
        if not (0.0 <= self.location <= 1.0):
            raise ValueError("Location fraction must be between 0.0 and 1.0")
        if not (0.1 <= self.discharge_coefficient <= 1.0):
            raise ValueError("Discharge coefficient must be between 0.1 and 1.0")


@attrs.define(slots=True, frozen=True)
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
    efficiency: float = attrs.field(
        default=1.0,
        validator=attrs.validators.and_(attrs.validators.gt(0), attrs.validators.le(1)),
    )
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
    leaks: typing.List[PipeLeakConfig] = attrs.field(factory=list)
    """List of leaks in the pipe"""
    ambient_pressure: Quantity = attrs.field(factory=lambda: Quantity(14.7, "psi"))  # type: ignore
    """Ambient pressure outside the pipe (usually atmospheric)"""


@attrs.define(slots=True, frozen=True)
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


@attrs.define(slots=True, frozen=True)
class MeterConfig:
    """Configuration for all meter types (PressureGauge, TemperatureGauge, FlowMeter)"""

    min_value: float = 0.0
    """Minimum value for the meter"""
    max_value: float = 100.0
    """Maximum value for the meter"""
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


@attrs.define(slots=True, frozen=True)
class RegulatorConfig:
    """Configuration for regulator components"""

    min_value: float = 0.0
    """Minimum allowable value"""
    max_value: float = 100.0
    """Maximum allowable value"""
    step: float = 0.1
    """Increment step for adjustments"""
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


@attrs.define(slots=True, frozen=True)
class FlowStationConfig:
    """Configuration for complete flow station setup"""

    pressure_guage: MeterConfig = attrs.field(
        factory=lambda: MeterConfig(label="Pressure", max_value=5000.0, height="180px")
    )
    """Configuration for the pressure meter"""
    temperature_guage: MeterConfig = attrs.field(
        factory=lambda: MeterConfig(
            label="Temperature",
            max_value=300.0,
            width="160px",
            height="240px",
            precision=2,
        )
    )
    """Configuration for the temperature meter"""
    flow_meter: MeterConfig = attrs.field(
        factory=lambda: MeterConfig(
            label="Flow Rate",
            max_value=200.0,
            height="220px",
            precision=3,
        )
    )
    """Configuration for the flow meter"""
    mass_flow_meter: MeterConfig = attrs.field(
        factory=lambda: MeterConfig(
            label="Mass Flow Rate",
            max_value=5000.0,
            height="220px",
            precision=3,
        )
    )
    """Configuration for the mass flow meter"""
    pressure_regulator: RegulatorConfig = attrs.field(
        factory=lambda: RegulatorConfig(label="Pressure Control", max_value=5000.0)
    )
    """Configuration for the pressure regulator (mostly upstream only)"""
    temperature_regulator: RegulatorConfig = attrs.field(
        factory=lambda: RegulatorConfig(
            label="Temperature Control",
            min_value=-40.0,
            max_value=300.0,
            precision=2,
        )
    )
    """Configuration for the temperature regulator (mostly upstream only)"""


@attrs.define(slots=True, frozen=True)
class GlobalConfig:
    """Global application configuration"""

    theme_color: str = "blue"
    """Primary theme color for the application"""
    unit_system_name: str = "imperial"
    """Name of the active unit system"""
    unit_systems: typing.Dict[str, UnitSystem] = attrs.field(
        factory=lambda: dict(imperial=IMPERIAL, si=SI, oil_field=OIL_FIELD)
    )
    """Custom unit systems defined by user"""
    auto_save: bool = True
    """Whether to auto-save configurations"""


@attrs.define(slots=True, frozen=True)
class PipelineConfig:
    """Pipeline-specific configuration"""

    name: str = "Flowline"
    """Default name for new pipelines"""
    max_flow_rate: Quantity = attrs.field(factory=lambda: Quantity(100.0, "MMscf/day"))  # type: ignore
    """Default maximum flow rate"""
    flow_type: FlowType = FlowType.COMPRESSIBLE
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
            upstream_pressure=Quantity(50, "psi"),  # type: ignore
            downstream_pressure=Quantity(42, "psi"),  # type: ignore
        )
    )
    """Default pipe properties"""


class StorageBackend(typing.Protocol):
    """Protocol defining a storage backend interface"""

    def read(self, key: str) -> typing.Optional[dict]:
        """Read data by key"""
        ...

    def update(self, key: str, data: dict, overwrite: bool = ...) -> None:
        """Update data by key"""
        ...

    def create(self, key: str, data: dict) -> None:
        """Create new data"""
        ...

    def delete(self, key: str) -> None:
        """Delete data by key"""
        ...


EventCallback = typing.Callable[[str, typing.Any], None]


class EventSubscription:
    """Represents a subscription to an event or events with pattern matching."""

    def __init__(self, event: str, callback: EventCallback):
        """
        Initialize event subscription.

        :param event: Event pattern or regex to match (e.g "*" for all, "pipeline.*" for prefix, or exact event name)
        :param callback: Callback function to execute when event matches
        """
        self.event = event
        self.callback = callback
        self._is_wildcard = event == "*"
        self._is_prefix = event.endswith("*") and not self._is_wildcard
        self._prefix = event[:-1] if self._is_prefix else None
        self._is_regex = False

        # Check if event contains regex special characters (excluding * which we handle specially)
        if any(char in event for char in r"[](){}+?.^$|\\") and not event == "*":
            self._is_regex = True
            try:
                self._regex = re.compile(event)
            except re.error:
                # If regex compilation fails, treat as exact match
                self._is_regex = False

    def matches(self, event: str) -> bool:
        """Check if the event matches this subscription's event pattern."""
        if self._is_wildcard:
            return True
        if self._is_regex:
            return bool(self._regex.match(event))
        if self._is_prefix:
            return event.startswith(self._prefix)
        return event == self.pattern
