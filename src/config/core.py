"""
Configuration Management System
"""

from typing_extensions import Self
import attrs
import orjson
import typing
import logging
from datetime import datetime

from src.units import UnitSystem, IMPERIAL
from src.types import (
    converter,
    ConfigStorage,
    GlobalConfig,
    PipelineConfig,
    FlowStationConfig,
)

logger = logging.getLogger(__name__)


def _flatten(obj, parent_key: str = "", sep: str = "."):
    """Recursively flatten a nested dictionary or object"""
    items = []

    # Check if it's an attrs class
    if attrs.has(obj):
        # Use attrs.asdict to get field values
        for field in attrs.fields(type(obj)):
            k = field.name
            v = getattr(obj, k)
            new_key = f"{parent_key}{sep}{k}" if parent_key else k

            # Skip special attributes and functions
            if k.startswith("_") or callable(v):
                continue

            # For basic types, add directly
            if isinstance(v, (str, int, float, bool, type(None))):
                items.append((new_key, v))
            # For Quantity objects, show both magnitude and units
            elif hasattr(v, "magnitude") and hasattr(v, "units"):
                items.append((f"{new_key}.magnitude", v.magnitude))
                items.append((f"{new_key}.units", str(v.units)))
            # For Unit objects, show as string
            elif hasattr(v, "__str__") and str(type(v)).find("Unit") > -1:
                items.append((new_key, str(v)))
            # For enum values, show the value
            elif hasattr(v, "value"):
                items.append((new_key, v.value))
            # For nested attrs objects, recurse
            elif attrs.has(v):
                items.extend(_flatten(v, new_key, sep=sep).items())
            else:
                items.append((new_key, str(v)))

    elif isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(_flatten(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
    else:
        items.append((parent_key, obj))

    return dict(items)


@attrs.define(slots=True, frozen=True)
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

    def flatten(self) -> typing.Dict[str, typing.Any]:
        """Get all configurations as a flat dictionary with dot notation keys"""
        data = converter.unstructure(self)
        return _flatten(data)

    def get(self, path: str, /) -> typing.Any:
        """Get nested configuration using dot notation (e.g., 'pipeline.fluid.name')"""
        parts = path.split(".")
        obj = self

        for part in parts:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                raise ValueError(f"Invalid configuration path: {path}")

        return obj

    def update(self, path: str, /, **kwargs: typing.Any) -> Self:
        """
        Update nested configuration using dot notation (e.g., 'pipeline.fluid.name')

        Returns a new `ConfigurationState` instance with the updated values.
        """
        if path == ".":
            return attrs.evolve(self, **kwargs, last_updated=datetime.now())

        parts = path.split(".")
        obj = self

        # Navigate to the nested object
        for part in parts:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                raise ValueError(f"Invalid configuration path: {path}")

        if not attrs.has(obj):
            setattr(obj, path, kwargs)
            return self

        new_obj = attrs.evolve(obj, **kwargs)
        # Rebuild the full configuration state with the updated nested object
        for part in reversed(parts):
            parent_path = ".".join(parts[: parts.index(part)])
            if parent_path:
                parent_obj = self.get(parent_path)
                new_obj = attrs.evolve(parent_obj, **{part: new_obj})
            else:
                new_obj = attrs.evolve(self, **{part: new_obj})
        return attrs.evolve(new_obj, last_updated=datetime.now())


class Configuration:
    """Application configuration with optional persistence via storage backends."""

    def __init__(
        self,
        id: str,
        storages: typing.Optional[typing.List[ConfigStorage]] = None,
    ) -> None:
        """
        Initialize configuration.

        :param id: Unique identifier for the configuration (e.g., user id or session id)
        :param storages: List of storage backends to use (session storage, file storage, etc.).
        If multiple storages are provided, they will be tried in order for loading/saving.
        It is advisable to use only two backends to avoid complexity. First should be
        session-based (like `UserSessionStorage`) and second should be persistent
        (like `JSONFileStorage` or `InMemoryStorage`).
        """
        self.id = id
        self.storages = storages or []
        self._state = ConfigurationState()
        self.load()
        self._observers: typing.List[typing.Callable[[ConfigurationState], None]] = []

    @property
    def state(self) -> ConfigurationState:
        """Get current configuration state"""
        return self._state

    def observe(self, observer: typing.Callable[[ConfigurationState], None]):
        """Add configuration change observer"""
        if observer not in self._observers:
            self._observers.append(observer)

    def unobserve(self, observer: typing.Callable[[ConfigurationState], None]):
        """Remove configuration change observer"""
        if observer in self._observers:
            self._observers.remove(observer)

    def notify(self):
        """Notify all observers of configuration changes"""
        for observer in self._observers:
            try:
                observer(self._state)
            except Exception as exc:
                logger.error(f"Error notifying config observer: {exc}", exc_info=True)

    def get_unit_system(self) -> UnitSystem:
        """Get current unit system"""
        global_state = self._state.global_
        unit_system_name = global_state.unit_system_name
        # Merge default and custom unit systems
        unit_systems = {
            **ConfigurationState().global_.unit_systems,
            **global_state.unit_systems,
        }
        return unit_systems.get(unit_system_name, IMPERIAL)

    def add_unit_system(self, unit_system: UnitSystem):
        """Add a custom unit system"""
        self.update(
            "global_",
            unit_systems={
                **self._state.global_.unit_systems,
                unit_system.name: unit_system,
            },
        )
        self.save()
        self.notify()

    def get_unit_systems(self) -> typing.List[str]:
        """Get list of available unit system names"""
        # Merge default and custom unit systems
        return list(
            set(self._state.global_.unit_systems.keys())
            | ConfigurationState().global_.unit_systems.keys()
        )

    def get(self, path: str, /) -> typing.Any:
        """Get nested configuration using dot notation (e.g., 'pipeline.fluid.name')"""
        return self._state.get(path)

    def update(self, path: str, /, **kwargs: typing.Any) -> None:
        """Update nested configuration using dot notation (e.g., 'pipeline.fluid.name')"""
        print(f"Updating config at {path} with {kwargs}")
        self._state = self._state.update(path, **kwargs)
        if self._state.global_.auto_save:
            self.save()
        self.notify()

    def load(self, storage: typing.Optional[ConfigStorage] = None):
        """
        Load configuration from storages

        Tries each storage backend in order until a valid configuration is found.
        """
        if storage:
            storages = [storage]
        else:
            storages = self.storages

        for storage in storages:
            data = storage.read(self.id)
            if data:
                try:
                    self._state = converter.structure(data, ConfigurationState)
                    logger.debug(
                        f"Loaded configuration from storage: {type(storage).__name__}"
                    )
                    return
                except Exception as exc:
                    logger.error(
                        f"Failed to load configuration from storage: {exc}",
                        exc_info=True,
                    )
        logger.info("No existing configuration found; using defaults")

    def save(self):
        """Save current configuration to all storages"""
        data = converter.unstructure(self._state)
        for storage in self.storages:
            try:
                if storage.read(self.id):
                    storage.update(self.id, data, overwrite=True)
                else:
                    storage.create(self.id, data)
                logger.debug(
                    f"Saved configuration to storage: {type(storage).__name__}"
                )
            except Exception as exc:
                logger.error(
                    f"Failed to save configuration to storage: {exc}", exc_info=True
                )

    def reset(self):
        """Reset configuration to defaults"""
        self._state = ConfigurationState()
        self.save()
        self.notify()
        logger.info("Configuration reset to defaults")

    def export(self) -> str:
        """Export configuration as JSON string"""
        data = converter.unstructure(self._state)
        return orjson.dumps(data, option=orjson.OPT_INDENT_2).decode()

    def import_(self, json_str: str):
        """Attempt to import configuration from JSON string"""
        data = orjson.loads(json_str)
        self._state = converter.structure(data, ConfigurationState)
        self.save()
        self.notify()
