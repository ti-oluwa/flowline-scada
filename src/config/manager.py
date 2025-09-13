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

from nicegui import ui, app
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
    connector_length: float = 0.1
    """Length of connectors between pipes"""
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
    flow_units: str = "MSCF/DAY"
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
class ConfigurationState:
    """Complete configuration state"""

    global_config: GlobalConfig = attrs.field(factory=GlobalConfig)
    pipeline_config: PipelineConfig = attrs.field(factory=PipelineConfig)
    default_meter_config: DefaultMeterConfig = attrs.field(factory=DefaultMeterConfig)
    default_regulator_config: DefaultRegulatorConfig = attrs.field(
        factory=DefaultRegulatorConfig
    )
    last_updated: str = attrs.field(factory=lambda: datetime.now().isoformat())
    version: str = "1.0"


class ConfigurationManager:
    """Manages application configuration with session persistence"""

    def __init__(
        self,
        id: str,
        config_dir: typing.Optional[Path] = None,
        session_key: str = "pipeline-scada-config",
    ):
        self.config_dir = config_dir or Path.home() / ".scada_pipeline"
        self.config_file = self.config_dir / f"{id}_config.json"
        self.config_dir.mkdir(exist_ok=True)

        self.session_key = session_key
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

    def update_global_config(self, **kwargs):
        """Update global configuration"""
        for key, value in kwargs.items():
            if hasattr(self._config_state.global_config, key):
                setattr(self._config_state.global_config, key, value)
        self._config_state.last_updated = datetime.now().isoformat()
        self.save_configuration()
        self.notify_observers()

    def update_pipeline_config(self, **kwargs):
        """Update pipeline configuration"""
        for key, value in kwargs.items():
            if hasattr(self._config_state.pipeline_config, key):
                setattr(self._config_state.pipeline_config, key, value)
        self._config_state.last_updated = datetime.now().isoformat()
        self.save_configuration()
        self.notify_observers()

    def update_meter_config(self, **kwargs):
        """Update default meter configuration"""
        for key, value in kwargs.items():
            if hasattr(self._config_state.default_meter_config, key):
                setattr(self._config_state.default_meter_config, key, value)
        self._config_state.last_updated = datetime.now().isoformat()
        self.save_configuration()
        self.notify_observers()

    def update_regulator_config(self, **kwargs):
        """Update default regulator configuration"""
        for key, value in kwargs.items():
            if hasattr(self._config_state.default_regulator_config, key):
                setattr(self._config_state.default_regulator_config, key, value)
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
        """Load configuration from session storage and file"""
        # Try session storage first (for current session persistence)
        try:
            if hasattr(app, "storage") and app.storage.user.get(self.session_key):
                session_data = app.storage.user.get(self.session_key)
                if not isinstance(session_data, dict):
                    raise TypeError("Invalid session data")
                self._config_state = attrs.evolve(ConfigurationState(), **session_data)
                logger.info("Loaded configuration from session storage")
                return
        except Exception as e:
            logger.warning(f"Failed to load from session storage: {e}")

        # Fallback to file storage
        try:
            if self.config_file.exists():
                with open(self.config_file, "r") as f:
                    data = json.load(f)

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
                    last_updated=data.get("last_updated", datetime.now().isoformat()),
                    version=data.get("version", "1.0"),
                )
                logger.info("Loaded configuration from file")
        except Exception as e:
            logger.warning(f"Failed to load configuration from file: {e}")
            # Use default configuration
            self._config_state = ConfigurationState()

    def save_configuration(self):
        """Save configuration to both session storage and file"""
        config_dict = attrs.asdict(self._config_state)

        # Save to session storage for immediate persistence
        try:
            if hasattr(app, "storage"):
                app.storage.user[self.session_key] = config_dict
        except Exception as e:
            logger.warning(f"Failed to save to session storage: {e}")

        # Save to file for long-term persistence
        try:
            with open(self.config_file, "w") as f:
                json.dump(config_dict, f, indent=2)
            logger.debug("Saved configuration to file")
        except Exception as e:
            logger.error(f"Failed to save configuration to file: {e}")

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

