"""
Configuration Management System
"""

import orjson
import typing
import logging
from datetime import datetime
import copy

from src.units import UnitSystem, IMPERIAL
from src.types import converter, ConfigStorage, ConfigurationState

logger = logging.getLogger(__name__)


class ConfigurationManager:
    """Manages application configuration with optional persistence via storage backends."""

    def __init__(
        self,
        id: str,
        storages: typing.Optional[typing.List[ConfigStorage]] = None,
    ) -> None:
        """
        Initialize configuration manager.

        :param id: Unique identifier for the configuration (e.g., user id or session id)
        :param storages: List of storage backends to use (session storage, file storage, etc.).
        If multiple storages are provided, they will be tried in order for loading/saving.
        It is advisable to use only two backends to avoid complexity. First should be
        session-based (like `UserSessionStorage`) and second should be persistent
        (like `JSONFileStorage` or `InMemoryStorage`).
        """
        self.id = id
        self.storages = storages or []
        self._config_state = ConfigurationState()
        self.load_configuration()
        self._observers: typing.List[typing.Callable[[ConfigurationState], None]] = []

    @property
    def state(self) -> ConfigurationState:
        """Get a copy of the current configuration state"""
        return self.get_state()

    def add_observer(self, observer: typing.Callable[[ConfigurationState], None]):
        """Add configuration change observer"""
        if observer not in self._observers:
            self._observers.append(observer)

    def remove_observer(self, observer: typing.Callable[[ConfigurationState], None]):
        """Remove configuration change observer"""
        if observer in self._observers:
            self._observers.remove(observer)

    def notify_observers(self):
        """Notify all observers of configuration changes"""
        for observer in self._observers:
            try:
                observer(self.state)
            except Exception as e:
                logger.error(f"Error notifying config observer: {e}")

    def get_state(self) -> ConfigurationState:
        """Get a copy of the current configuration state"""
        return copy.deepcopy(self._config_state)

    def update_global_config(self, **kwargs: typing.Any):
        """Update global configuration"""
        for key, value in kwargs.items():
            if hasattr(self._config_state.global_, key):
                setattr(self._config_state.global_, key, value)
        self._config_state.last_updated = datetime.now().isoformat()
        if self._config_state.global_.auto_save:
            self.save_configuration()
        self.notify_observers()

    def update_pipeline_config(self, **kwargs: typing.Any):
        """Update pipeline configuration"""
        for key, value in kwargs.items():
            if hasattr(self._config_state.pipeline, key):
                setattr(self._config_state.pipeline, key, value)
        self._config_state.last_updated = datetime.now().isoformat()
        if self._config_state.global_.auto_save:
            self.save_configuration()
        self.notify_observers()

    def update_flow_station_config(self, **kwargs: typing.Any):
        """Update flow station configuration"""
        for key, value in kwargs.items():
            if hasattr(self._config_state.flow_station, key):
                setattr(self._config_state.flow_station, key, value)
        self._config_state.last_updated = datetime.now().isoformat()
        if self._config_state.global_.auto_save:
            self.save_configuration()
        self.notify_observers()

    def update_nested_config(self, path: str, **kwargs: typing.Any):
        """
        Update nested configuration using dot notation (e.g., 'pipeline.fluid.name')

        :param path: Dot notation path to the nested configuration object
        :param kwargs: Attributes to update on the nested object
        """
        parts = path.split(".")
        obj = self._config_state

        # Navigate to the nested object
        for part in parts:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                raise ValueError(f"Invalid configuration path: {path}")

        # Update the attributes on the final object
        for key, value in kwargs.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
            else:
                raise ValueError(f"Invalid attribute {key} on object at path {path}")

        self._config_state.last_updated = datetime.now().isoformat()
        if self._config_state.global_.auto_save:
            self.save_configuration()
        self.notify_observers()

    def get_unit_system(self) -> UnitSystem:
        """Get current unit system"""
        global_state = self._config_state.global_
        unit_system_name = global_state.unit_system_name
        # Merge default and custom unit systems
        unit_systems = {
            **ConfigurationState().global_.unit_systems,
            **global_state.unit_systems,
        }
        return unit_systems.get(unit_system_name, IMPERIAL)

    def add_custom_unit_system(self, unit_system: UnitSystem):
        """Add a custom unit system"""
        self._config_state.global_.unit_systems[unit_system.name.lower()] = unit_system
        self._config_state.last_updated = datetime.now().isoformat()
        self.save_configuration()
        self.notify_observers()

    def get_available_unit_systems(self) -> typing.List[str]:
        """Get list of available unit system names"""
        # Merge default and custom unit systems
        return list(
            set(self._config_state.global_.unit_systems.keys())
            | ConfigurationState().global_.unit_systems.keys()
        )

    def get_nested_config(self, path: str) -> typing.Any:
        """Get nested configuration using dot notation (e.g., 'pipeline.fluid.name')"""
        parts = path.split(".")
        obj = self._config_state

        for part in parts:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                raise ValueError(f"Invalid configuration path: {path}")

        return obj

    def get_all_configs_flat(self) -> typing.Dict[str, typing.Any]:
        """Get all configurations as a flat dictionary with dot notation keys"""
        import attrs

        def _flatten_dict(obj, parent_key="", sep="."):
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
                        items.extend(_flatten_dict(v, new_key, sep=sep).items())
                    else:
                        items.append((new_key, str(v)))

            elif isinstance(obj, dict):
                for k, v in obj.items():
                    new_key = f"{parent_key}{sep}{k}" if parent_key else k
                    if isinstance(v, dict):
                        items.extend(_flatten_dict(v, new_key, sep=sep).items())
                    else:
                        items.append((new_key, v))
            else:
                items.append((parent_key, obj))

            return dict(items)

        return _flatten_dict(self._config_state)

    def load_configuration(self):
        """
        Load configuration from storages

        Tries each storage backend in order until a valid configuration is found.
        """
        for storage in self.storages:
            data = storage.read(self.id)
            if data:
                try:
                    self._config_state = converter.structure(data, ConfigurationState)
                    logger.debug(
                        f"Loaded configuration from storage: {type(storage).__name__}"
                    )
                    return
                except Exception as e:
                    logger.error(f"Failed to load configuration from storage: {e}")
        logger.info("No existing configuration found; using defaults")

    def save_configuration(self):
        """Save current configuration to all storages"""
        data = converter.unstructure(self._config_state)
        for storage in self.storages:
            try:
                if storage.read(self.id):
                    storage.update(self.id, data, overwrite=True)
                else:
                    storage.create(self.id, data)
                logger.debug(
                    f"Saved configuration to storage: {type(storage).__name__}"
                )
            except Exception as e:
                logger.error(f"Failed to save configuration to storage: {e}")

    def manual_save(self):
        """Manually save configuration (bypasses auto-save check)"""
        self.save_configuration()
        logger.info("Configuration manually saved")

    def has_unsaved_changes(self) -> bool:
        """Check if there are unsaved changes (only meaningful when auto-save is disabled)"""
        if self._config_state.global_.auto_save:
            return False  # Auto-save enabled, so no unsaved changes

        # Check if the current config differs from what's stored
        try:
            stored_data = None
            for storage in self.storages:
                stored_data = storage.read(self.id)
                if stored_data:
                    break

            if not stored_data:
                return True  # No saved config exists, so changes are unsaved

            current_data = converter.unstructure(self._config_state)
            return stored_data != current_data
        except Exception as e:
            logger.warning(f"Failed to check for unsaved changes: {e}")
            return False

    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        self._config_state = ConfigurationState()
        self.save_configuration()
        self.notify_observers()
        logger.info("Configuration reset to defaults")

    def export_configuration(self) -> str:
        """Export configuration as JSON string"""
        data = converter.unstructure(self._config_state)
        return orjson.dumps(data, option=orjson.OPT_INDENT_2).decode()

    def import_configuration(self, json_str: str):
        """Import configuration from JSON string"""
        try:
            data = orjson.loads(json_str)
            self._config_state = converter.structure(data, ConfigurationState)

            # Notify observers
            self.notify_observers()
            self.save_configuration()

        except Exception as e:
            raise ValueError(f"Failed to import configuration: {e}")
