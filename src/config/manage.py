"""
Configuration Management System with Session Persistence
"""

import json
import typing
import logging
from pathlib import Path
import attrs
from datetime import datetime
import copy

from nicegui import App
from src.units import UnitSystem, IMPERIAL, SI, QuantityUnit

logger = logging.getLogger(__name__)


@attrs.define
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
    show_tooltips: bool = True
    """Whether to show tooltips in UI"""
    animation_enabled: bool = True
    """Whether animations are enabled"""
    dark_mode: bool = False
    """Dark mode preference"""


@attrs.define
class PipelineConfig:
    """Pipeline-specific configuration"""

    # Pipeline properties
    pipeline_name: str = "Main Pipeline"
    """Default name for new pipelines"""
    max_flow_rate: float = 1e6
    """Default maximum flow rate"""
    max_flow_rate_unit: str = "MMscf/day"
    """Unit for maximum flow rate"""
    flow_type: str = "compressible"
    """Default flow type: 'compressible' or 'incompressible'"""
    
    # Fluid properties
    default_fluid_name: str = "Methane"
    """Default fluid name"""
    default_fluid_phase: str = "gas"
    """Default fluid phase: 'liquid' or 'gas'"""
    initial_temperature: float = 60.0
    """Default initial temperature"""
    initial_temperature_unit: str = "degF"
    """Unit for initial temperature"""
    initial_pressure: float = 100.0
    """Default initial pressure"""
    initial_pressure_unit: str = "psi"
    """Unit for initial pressure"""
    molecular_weight: float = 16.04
    """Default molecular weight"""
    molecular_weight_unit: str = "g/mol"
    """Unit for molecular weight"""

    # Pipe defaults
    default_pipe_material: str = "Steel"
    """Default material for new pipes"""
    default_pipe_length: float = 100.0
    """Default length for new pipes"""
    default_pipe_diameter: float = 12.0
    """Default diameter for new pipes"""
    default_pipe_roughness: float = 0.0018
    """Default roughness for new pipes"""
    default_upstream_pressure: float = 1000.0
    """Default upstream pressure"""
    default_downstream_pressure: float = 500.0
    """Default downstream pressure"""
    default_efficiency: float = 0.85
    """Default pipe efficiency"""
    
    # Pipeline visualization
    connector_length: float = 0.1
    """Length of connectors between pipes in meters"""
    scale_factor: float = 0.1
    """Scale factor for visualization"""
    alert_errors: bool = True
    """Whether to show error alerts"""


@attrs.define
class DefaultMeterConfig:
    """Default meter configuration template"""

    width: str = "200px"
    height: str = "200px"
    precision: int = 2
    animation_speed: float = 5.0
    animation_interval: float = 0.1
    update_interval: float = 1.0
    alert_errors: bool = True

    # Pressure meter defaults
    pressure_max_value: float = 2000.0
    pressure_units: str = "PSI"
    pressure_height: str = "180px"

    # Temperature meter defaults
    temperature_min_value: float = -40.0
    temperature_max_value: float = 200.0
    temperature_units: str = "°F"
    temperature_width: str = "160px"
    temperature_height: str = "240px"
    temperature_precision: int = 1

    # Flow meter defaults
    flow_max_value: float = 1e9
    flow_units: str = "MMscf/DAY"
    flow_height: str = "220px"
    flow_precision: int = 4
    flow_direction: typing.Literal["east", "west", "north", "south"] = "east"


@attrs.define
class DefaultRegulatorConfig:
    """Default regulator configuration template"""

    width: str = "280px"
    height: str = "220px"
    precision: int = 3
    step: float = 0.1
    alert_errors: bool = True

    # Pressure regulator defaults
    pressure_max_value: float = 2000.0
    pressure_units: str = "PSI"

    # Temperature regulator defaults
    temperature_min_value: float = -40.0
    temperature_max_value: float = 200.0
    temperature_units: str = "°F"


@attrs.define
class FlowStationDefaults:
    """Default flow station configuration"""

    # Station units
    pressure_unit: str = "psi"
    """Default pressure unit for flow stations"""
    temperature_unit: str = "degF"
    """Default temperature unit for flow stations"""
    flow_unit: str = "MMscf/day"
    """Default flow unit for flow stations"""
    
    # Station naming
    upstream_station_name: str = "Upstream Station"
    """Default name for upstream stations"""
    downstream_station_name: str = "Downstream Station"
    """Default name for downstream stations"""


@attrs.define
class ConfigurationState:
    """Complete configuration state"""

    global_config: GlobalConfig = attrs.field(factory=GlobalConfig)
    pipeline_config: PipelineConfig = attrs.field(factory=PipelineConfig)
    default_meter_config: DefaultMeterConfig = attrs.field(factory=DefaultMeterConfig)
    default_regulator_config: DefaultRegulatorConfig = attrs.field(
        factory=DefaultRegulatorConfig
    )
    flow_station_defaults: FlowStationDefaults = attrs.field(
        factory=FlowStationDefaults
    )
    last_updated: str = attrs.field(factory=lambda: datetime.now().isoformat())
    version: str = "1.0"


class ConfigStorage(typing.Protocol):
    """Protocol for configuration storage backend"""

    def read(self, id: str) -> typing.Optional[dict]: ...

    def update(self, id: str, data: dict, overwrite: bool = ...) -> None: ...

    def create(self, id: str, data: dict) -> None: ...

    def delete(self, id: str) -> None: ...


class InMemoryStorage:
    """In-memory storage backend for configurations"""

    def __init__(self, defaults: typing.Optional[dict] = None):
        self._store: typing.Dict[str, dict] = defaults or {}

    def read(self, id: str) -> typing.Optional[dict]:
        """Read configuration by id"""
        return self._store.get(id)

    def update(self, id: str, data: dict, overwrite: bool = False) -> None:
        if id not in self._store:
            raise KeyError(f"Configuration with id '{id}' does not exist.")
        if overwrite:
            self._store[id] = data
        else:
            self._store[id].update(data)

    def create(self, id: str, data: dict) -> None:
        if id in self._store:
            raise KeyError(f"Configuration with id '{id}' already exists.")
        self._store[id] = data

    def delete(self, id: str) -> None:
        if id in self._store:
            del self._store[id]
        else:
            raise KeyError(f"Configuration with id '{id}' does not exist.")


class SessionStorage:
    def __init__(self, app: App, session_key: str = "pipeline-scada"):
        self.app = app
        self.session_key = session_key
        if not hasattr(app, "storage"):
            raise ValueError("App does not support storage backend.")
        self.app.storage.user[self.session_key] = {}

    def read(self, id: str) -> typing.Optional[dict]:
        try:
            return self.app.storage.user[self.session_key].get(id)
        except Exception as e:
            logger.error(f"Failed to read session storage for id '{id}': {e}")
            return None

    def update(self, id: str, data: dict, overwrite: bool = False) -> None:
        try:
            if id not in self.app.storage.user[self.session_key]:
                raise KeyError(f"Configuration with id '{id}' does not exist.")
            if overwrite:
                self.app.storage.user[self.session_key][id] = data
            else:
                self.app.storage.user[self.session_key][id].update(data)
        except Exception as e:
            logger.error(f"Failed to update session storage for id '{id}': {e}")
            raise

    def create(self, id: str, data: dict) -> None:
        try:
            if id in self.app.storage.user[self.session_key]:
                raise KeyError(f"Configuration with id '{id}' already exists.")
            self.app.storage.user[self.session_key][id] = data
        except Exception as e:
            logger.error(f"Failed to create session storage for id '{id}': {e}")
            raise

    def delete(self, id: str) -> None:
        try:
            if id in self.app.storage.user[self.session_key]:
                del self.app.storage.user[self.session_key][id]
            else:
                raise KeyError(f"Configuration with id '{id}' does not exist.")
        except Exception as e:
            logger.error(f"Failed to delete session storage for id '{id}': {e}")
            raise


class JSONFileStorage:
    """JSON file storage backend for configurations"""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, id: str) -> Path:
        return self.config_dir / f"{id}_config.json"

    def read(self, id: str) -> typing.Optional[dict]:
        file_path = self._get_file_path(id)
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read configuration file '{file_path}': {e}")
            return None

    def update(self, id: str, data: dict, overwrite: bool = False) -> None:
        file_path = self._get_file_path(id)
        if not file_path.exists():
            raise KeyError(f"Configuration with id '{id}' does not exist.")
        try:
            if overwrite:
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=2)
            else:
                existing_data = self.read(id) or {}
                existing_data.update(data)
                with open(file_path, "w") as f:
                    json.dump(existing_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to update configuration file '{file_path}': {e}")
            raise

    def create(self, id: str, data: dict) -> None:
        file_path = self._get_file_path(id)
        if file_path.exists():
            raise KeyError(f"Configuration with id '{id}' already exists.")
        try:
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to create configuration file '{file_path}': {e}")
            raise

    def delete(self, id: str) -> None:
        file_path = self._get_file_path(id)
        if not file_path.exists():
            raise KeyError(f"Configuration with id '{id}' does not exist.")
        try:
            file_path.unlink()
        except Exception as e:
            logger.error(f"Failed to delete configuration file '{file_path}': {e}")
            raise


class ConfigurationManager:
    """Manages application configuration with session persistence"""

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
        session-based (like `SessionStorage`) and second should be persistent
        (like `JSONFileStorage` or `InMemoryStorage`).
        """
        self.id = id
        self.storages = storages or []
        self._config_state = ConfigurationState()
        self.load_configuration()
        self._observers: typing.List[typing.Callable[[ConfigurationState], None]] = []

    def add_observer(self, observer: typing.Callable[[ConfigurationState], None]):
        """Add configuration change observer"""
        self._observers.append(observer)

    def remove_observer(self, observer: typing.Callable[[ConfigurationState], None]):
        """Remove configuration change observer"""
        if observer in self._observers:
            self._observers.remove(observer)

    def notify_observers(self):
        """Notify all observers of configuration changes"""
        for observer in self._observers:
            try:
                observer(self._config_state)
            except Exception as e:
                logger.error(f"Error notifying config observer: {e}")

    def get_config(self) -> ConfigurationState:
        """Get current configuration state"""
        return copy.deepcopy(self._config_state)

    def update_global_config(self, **kwargs: typing.Any):
        """Update global configuration"""
        for key, value in kwargs.items():
            if hasattr(self._config_state.global_config, key):
                setattr(self._config_state.global_config, key, value)
        self._config_state.last_updated = datetime.now().isoformat()
        self.save_configuration()
        self.notify_observers()

    def update_pipeline_config(self, **kwargs: typing.Any):
        """Update pipeline configuration"""
        for key, value in kwargs.items():
            if hasattr(self._config_state.pipeline_config, key):
                setattr(self._config_state.pipeline_config, key, value)
        self._config_state.last_updated = datetime.now().isoformat()
        self.save_configuration()
        self.notify_observers()

    def update_meter_config(self, **kwargs: typing.Any):
        """Update default meter configuration"""
        for key, value in kwargs.items():
            if hasattr(self._config_state.default_meter_config, key):
                setattr(self._config_state.default_meter_config, key, value)
        self._config_state.last_updated = datetime.now().isoformat()
        self.save_configuration()
        self.notify_observers()

    def update_regulator_config(self, **kwargs: typing.Any):
        """Update default regulator configuration"""
        for key, value in kwargs.items():
            if hasattr(self._config_state.default_regulator_config, key):
                setattr(self._config_state.default_regulator_config, key, value)
        self._config_state.last_updated = datetime.now().isoformat()
        self.save_configuration()
        self.notify_observers()

    def update_flow_station_defaults(self, **kwargs: typing.Any):
        """Update flow station defaults configuration"""
        for key, value in kwargs.items():
            if hasattr(self._config_state.flow_station_defaults, key):
                setattr(self._config_state.flow_station_defaults, key, value)
        self._config_state.last_updated = datetime.now().isoformat()
        self.save_configuration()
        self.notify_observers()

    def get_unit_system(self) -> UnitSystem:
        """Get current unit system"""
        config = self._config_state.global_config

        # Check if it's a custom unit system
        if config.unit_system_name in config.custom_unit_systems:
            unit_data = config.custom_unit_systems[config.unit_system_name]
            unit_system = UnitSystem()
            for quantity, unit_info in unit_data.items():
                unit_system[quantity] = QuantityUnit(
                    unit=unit_info["unit"],
                    display=unit_info.get("display", unit_info["unit"]),
                    default=unit_info.get("default"),
                )
            return unit_system

        # Return predefined unit systems
        return IMPERIAL if config.unit_system_name == "imperial" else SI

    def add_custom_unit_system(self, name: str, unit_system: UnitSystem):
        """Add a custom unit system"""
        unit_data = {}
        for quantity, unit_obj in unit_system.items():
            unit_data[quantity] = {
                "unit": unit_obj.unit,
                "display": unit_obj.display,
                "default": unit_obj.default,
            }

        self._config_state.global_config.custom_unit_systems[name] = unit_data
        self._config_state.last_updated = datetime.now().isoformat()
        self.save_configuration()
        self.notify_observers()

    def get_available_unit_systems(self) -> typing.List[str]:
        """Get list of available unit system names"""
        systems = ["imperial", "si"]
        systems.extend(self._config_state.global_config.custom_unit_systems.keys())
        return systems

    def load_configuration(self):
        """
        Load configuration from storages

        Tries each storage backend in order until a valid configuration is found.
        """
        for storage in self.storages:
            data = storage.read(self.id)
            if data:
                try:
                    # Convert dict data back to attrs classes
                    global_config = GlobalConfig(**data.get("global_config", {}))
                    pipeline_config = PipelineConfig(**data.get("pipeline_config", {}))
                    meter_config = DefaultMeterConfig(
                        **data.get("default_meter_config", {})
                    )
                    regulator_config = DefaultRegulatorConfig(
                        **data.get("default_regulator_config", {})
                    )

                    self._config_state = ConfigurationState(
                        global_config=global_config,
                        pipeline_config=pipeline_config,
                        default_meter_config=meter_config,
                        default_regulator_config=regulator_config,
                        last_updated=data.get(
                            "last_updated", datetime.now().isoformat()
                        ),
                        version=data.get("version", "1.0"),
                    )
                    logger.debug(
                        f"Loaded configuration from storage: {type(storage).__name__}"
                    )
                    return
                except Exception as e:
                    logger.error(f"Failed to load configuration from storage: {e}")
        logger.info("No existing configuration found; using defaults")

    def save_configuration(self):
        """Save current configuration to all storages"""
        data = attrs.asdict(self._config_state)
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

    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        self._config_state = ConfigurationState()
        self.save_configuration()
        self.notify_observers()
        logger.info("Configuration reset to defaults")

    def export_configuration(self) -> str:
        """Export configuration as JSON string"""
        return json.dumps(attrs.asdict(self._config_state), indent=2)

    def import_configuration(self, json_str: str):
        """Import configuration from JSON string"""
        try:
            data = json.loads(json_str)

            # Convert dict data back to attrs classes
            global_config = GlobalConfig(**data.get("global_config", {}))
            pipeline_config = PipelineConfig(**data.get("pipeline_config", {}))
            meter_config = DefaultMeterConfig(**data.get("default_meter_config", {}))
            regulator_config = DefaultRegulatorConfig(
                **data.get("default_regulator_config", {})
            )

            self._config_state = ConfigurationState(
                global_config=global_config,
                pipeline_config=pipeline_config,
                default_meter_config=meter_config,
                default_regulator_config=regulator_config,
                last_updated=datetime.now().isoformat(),
                version=data.get("version", "1.0"),
            )

            self.save_configuration()
            self.notify_observers()
            logger.info("Configuration imported successfully")
        except Exception as e:
            logger.error(f"Failed to import configuration: {e}")
            raise ValueError(f"Invalid configuration format: {e}")
