import typing
from pint import UnitRegistry
from collections import defaultdict
import attrs

__all__ = ["QuantityUnit", "UnitSystem", "IMPERIAL", "SI", "ureg", "Quantity", "Unit"]

ureg = UnitRegistry()
ureg.define("scf = 0.0283168 * meter**3 = SCF")  # 1 scf ≈ 0.0283168 m³
ureg.define("Mscf = 1000 * scf = MSCf")  # 1 Mscf = 1000 scf
ureg.define("MMscf = 1000 * MMscf = MMSCF")  # 1 MMscf = 1,000,000 scf
ureg.define("MMMscf = 1000 * MMscf = MMMSCF")  # 1 MMMSCF = 1,000,000,000 scf
Quantity = ureg.Quantity
Unit = ureg.Unit


@attrs.define(frozen=True, slots=True)
class QuantityUnit:
    """Unit for a specific physical quantity"""

    unit: Unit = attrs.field(converter=Unit)
    """Pint supported unit, e.g., 'psi', 'degF', 'm^3/s'."""
    display: typing.Optional[str] = attrs.field(default=None)
    """Optional display string for UI, e.g., '°F'."""
    default: typing.Optional[float] = attrs.field(default=None)
    """Default value for the quantity in the specified unit, if applicable."""

    def __str__(self) -> str:
        return self.display or str(self.unit)


QuantityUnitT = typing.TypeVar("QuantityUnitT", bound=QuantityUnit)


class UnitSystem(defaultdict[str, QuantityUnitT]):
    """
    A unit system that maps quantity names to their QuantityUnit definitions.

    Subclass of defaultdict to allow easy access to units like a dictionary.
    Users can create custom unit systems by subclassing or instantiation.

    Example:
        imperial = UnitSystem()
        imperial['pressure'] = QuantityUnit(unit='psi', default=14.7)
        imperial['temperature'] = QuantityUnit(unit='degF', default=60.0)

        # Access units
        pressure_unit = imperial['pressure'].unit  # 'psi'
        default_pressure = imperial['pressure'].default  # 14.7
    """

    def __init__(
        self,
        map: typing.Optional[typing.Mapping[str, QuantityUnitT]] = None,
        /,
        *,
        default_factory: typing.Optional[typing.Callable[[], QuantityUnitT]] = None,
    ):
        if default_factory is None:

            def _default_factory() -> QuantityUnitT:
                return typing.cast(
                    QuantityUnitT, QuantityUnit(unit="dimensionless", default=None)
                )

            default_factory = _default_factory
        super().__init__(default_factory, dict(map or {}))

    def __missing__(self, key: str) -> QuantityUnitT:
        """Return default QuantityUnit for missing keys."""
        return self.default_factory()  # type: ignore


IMPERIAL = UnitSystem()
IMPERIAL.update(
    {
        "length": QuantityUnit(unit="ft", display="ft", default=None),
        "diameter": QuantityUnit(unit="inch", display="in", default=None),
        "pressure": QuantityUnit(unit="psi", display="psi", default=None),
        "temperature": QuantityUnit(
            unit="degF", display="°F", default=60.0
        ),  # Room temperature
        "flow_rate": QuantityUnit(unit="ft^3/s", display="ft³/s", default=None),
        "flow_volume": QuantityUnit(unit="scf", display="scf", default=None),
        "molecular_weight": QuantityUnit(
            unit="g/mol", display="g/mol", default=16.04
        ),  # Methane MW
        "roughness": QuantityUnit(unit="inch", display="in", default=None),
        "elevation": QuantityUnit(unit="ft", display="ft", default=0.0),  # Sea level
        "area": QuantityUnit(unit="inch^2", display="in²", default=None),
        "velocity": QuantityUnit(unit="ft/s", display="ft/s", default=None),
        "density": QuantityUnit(unit="lb/ft^3", display="lb/ft³", default=None),
        "viscosity": QuantityUnit(unit="cP", display="cP", default=None),
    }
)

SI = UnitSystem()
SI.update(
    {
        "length": QuantityUnit(unit="m", display="m", default=None),
        "diameter": QuantityUnit(unit="mm", display="mm", default=None),
        "pressure": QuantityUnit(unit="Pa", display="Pa", default=None),
        "temperature": QuantityUnit(
            unit="degC", display="°C", default=15.6
        ),  # Room temperature
        "flow_rate": QuantityUnit(unit="m^3/s", display="m³/s", default=None),
        "flow_volume": QuantityUnit(unit="m^3", display="m³", default=None),
        "molecular_weight": QuantityUnit(
            unit="g/mol", display="g/mol", default=16.0
        ),  # Methane MW
        "roughness": QuantityUnit(unit="mm", display="mm", default=None),
        "elevation": QuantityUnit(unit="m", display="m", default=0.0),  # Sea level
        "area": QuantityUnit(unit="mm^2", display="mm²", default=None),
        "velocity": QuantityUnit(unit="m/s", display="m/s", default=None),
        "density": QuantityUnit(unit="kg/m^3", display="kg/m³", default=None),
        "viscosity": QuantityUnit(unit="Pa*s", display="Pa⋅s", default=None),
    }
)
