import json
from pathlib import Path


class ParameterConfigSingleton(type):
    """Metaclass that ensures only one instance of the class is created."""

    _instances: dict[type, "ParameterConfigManager"] = {}

    def __call__(cls, *args, **kwargs) -> "ParameterConfigManager":
        """Override class instantiation to return singleton instance.

        Returns:
            The single instance of the class, creating it if necessary.

        """
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class ParameterConfigManager(metaclass=ParameterConfigSingleton):
    """Manage parameter configurations from model_config.json."""

    def __init__(self, config_file: str = "model_config.json"):
        """Initialize the singleton parameter configuration manager.

        Loads configuration from JSON file and builds parameter mappings.

        Args:
            config_file: Path to model_config.json file.

        """
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.config_file = Path(config_file)
        self._load_config()

    def _load_config(self):
        """Load configuration from JSON file."""
        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file {self.config_file} not found")

        with open(self.config_file) as f:
            config_data = json.load(f)

        self.model_configs = config_data.get("model_configs", {})
        self.use_cases = config_data.get("use_cases", {})
        self.surface_variables = config_data.get("surface_variables", {})
        self.parameter_mappings = config_data.get("parameter_mappings", {})
        self.climate_param_map = self.parameter_mappings.get("climate_data", {})
        self.param_ids = self.parameter_mappings.get("param_ids", {})
        self.pressure_level_map = self.parameter_mappings.get("pressure_levels", {})

        self._build_parameter_categories()

    def _build_parameter_categories(self):
        """Build parameter categories from surface_variables configuration."""
        self.parameter_categories = {
            "temperature": [],
            "precipitation": [],
            "pressure": [],
            "wind": [],
            "geopotential": [],
            "convection": [],
            "other": [],
        }

        for param, config in self.surface_variables.items():
            name = config.get("name", "").lower()
            units = config.get("units", "").lower()

            if "temperature" in name or units == "k":
                self.parameter_categories["temperature"].append(param)
            elif (
                "precipitation" in name
                or "rain" in name
                or "snow" in name
                or param in ["tp", "cp", "lsp", "sf"]
            ):
                self.parameter_categories["precipitation"].append(param)
            elif "pressure" in name or units == "pa":
                self.parameter_categories["pressure"].append(param)
            elif (
                "wind" in name
                or "gust" in name
                or param in ["10u", "10v", "ws", "i10fg"]
            ):
                self.parameter_categories["wind"].append(param)
            elif "geopotential" in name or param in ["z", "z500"]:
                self.parameter_categories["geopotential"].append(param)
            elif "cape" in name.lower() or "convective" in name.lower():
                self.parameter_categories["convection"].append(param)
            else:
                self.parameter_categories["other"].append(param)

    def get_climate_param_map(self) -> dict[str, str]:
        """Get mapping from forecast params to climate params.

        Returns:
            Dictionary mapping parameter names to climate parameter IDs

        """
        climate_map = {}
        for param, config in self.surface_variables.items():
            if "climate_param" in config:
                climate_map[param] = config["climate_param"]

        return climate_map

    def get_parameter_category(self, parameter: str) -> str:
        """Get the category of a parameter.

        Args:
            parameter: Parameter name

        Returns:
            Category name (e.g., 'temperature', 'precipitation')

        """
        for category, params in self.parameter_categories.items():
            if parameter in params:
                return category
        return "other"

    def get_required_files_for_plot_type(self, plot_type):
        """Get required files for a specific plot type.

        Args:
            plot_type: Plot type name

        Returns:
            list: List of required file types

        """
        if plot_type not in self.use_cases:
            return []

        use_case = self.use_cases[plot_type]
        return use_case.get("required_data", [])

    def get_optional_files_for_plot_type(self, plot_type):
        """Get optional files for a specific plot type.

        Args:
            plot_type: Plot type name

        Returns:
            list: List of optional file types

        """
        if plot_type not in self.use_cases:
            return []

        use_case = self.use_cases[plot_type]
        return use_case.get("optional_data", [])

    def get_step_intervals(self, model_class="ifs"):
        """Get step intervals for a model class.

        Args:
            model_class: Model class ('ifs' or 'aifs')

        Returns:
            list: Step intervals or empty list

        """
        if model_class not in self.model_configs:
            return []

        step_config = self.model_configs[model_class].get("step_config", {})

        if step_config.get("type") == "intervals":
            return step_config.get("intervals", [])

        return []
