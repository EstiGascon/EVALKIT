import json
import os
from pathlib import Path

import numpy as np
import xarray as xr


class StylingConfiguration:
    """Styling configuration for plots."""

    def __init__(self, config_path=None):
        """Initialize styling config."""
        if config_path is None:
            current_dir = Path(__file__).parent
            config_path = current_dir / "model_config.json"
        self.config_path = str(config_path)
        self._initialize_palettes()
        self._initialize_parameter_defaults()

    def _initialize_palettes(self):
        """Initialize all color palettes and their corresponding levels."""
        self.temp_colors = [
            "#8200C2",
            "#ED00FA",
            "#FF7DF5",
            "#D47AFF",
            "#0808D6",
            "#007AFF",
            "#00A6FF",
            "#00D1FF",
            "#00F7FF",
            "#CAFCFF",
            "#008233",
            "#38DB78",
            "#00FF3D",
            "#A1FF00",
            "#FAFF00",
            "#FFD600",
            "#FFA100",
            "#FF6B00",
            "#FF2600",
            "#C7030D",
        ]
        self.temp_levels = [
            -70,
            -50,
            -40,
            -35,
            -30,
            -25,
            -20,
            -15,
            -10,
            -5,
            0,
            5,
            10,
            15,
            20,
            25,
            30,
            35,
            40,
            50,
            70,
        ]
        self.precip_colors = {
            1: [
                "#BFF2ED",
                "#73EDC7",
                "#12D99C",
                "#87CC21",
                "#99E80F",
                "#E6FF66",
                "#E3E311",
                "#FFBA01",
                "#FF7D01",
                "#FF0000",
                "#D901FF",
                "#A102EB",
                "#0A0AD6",
                "#0B0B6E",
                "#737373",
            ],
            2: [
                "#99E6FF",
                "#73B3FF",
                "#4D80FF",
                "#264DFF",
                "#CCFF33",
                "#A6F200",
                "#80D900",
                "#26BF1A",
                "#008C30",
                "#FFD900",
                "#FFBD00",
                "#FF9E00",
                "#FF8000",
                "#D97300",
                "#FFBFBF",
                "#FF8080",
                "#FF0000",
                "#CC0000",
                "#990000",
                "#D999FF",
                "#BF66FF",
                "#9933FF",
                "#8000E6",
                "#590099",
                "#808080",
                "#595959",
                "#404040",
                "#262626",
                "#0D0D0D",
            ],
            3: [
                "#92F495",
                "#01FFA6",
                "#00A680",
                "#01AAFF",
                "#016FFF",
                "#5440EA",
                "#954DF9",
                "#D74DF9",
                "#E438B6",
                "#E4384F",
                "#E47738",
                "#E4B338",
                "#EEEE2C",
                "#EEF0D6",
                "#808080",
            ],
        }

        self.precip_levels = {
            1: [0.5, 2, 5, 10, 20, 30, 40, 50, 60, 80, 100, 125, 150, 200, 300, 500],
            2: [
                0.5,
                1,
                2,
                4,
                5,
                6,
                8,
                10,
                12,
                15,
                20,
                30,
                40,
                50,
                75,
                100,
                125,
                150,
                175,
                200,
                250,
                275,
                300,
                325,
                350,
                400,
                500,
                600,
                700,
                1000,
            ],
            3: [
                10,
                20,
                30,
                40,
                50,
                60,
                80,
                100,
                125,
                150,
                175,
                200,
                250,
                350,
                500,
                700,
            ],
        }
        self.wind_gust_colors = [
            "#99E6FF",
            "#73B3FF",
            "#4D80FF",
            "#264DFF",
            "#CCFF33",
            "#A6F200",
            "#80D900",
            "#26BF1A",
            "#008C30",
            "#FFD900",
            "#FFBD00",
            "#FF9E00",
            "#FF8000",
            "#D97300",
            "#FFBFBF",
            "#FF8080",
            "#FF0000",
            "#CC0000",
            "#990000",
            "#D999FF",
            "#BF66FF",
            "#9933FF",
            "#8000E6",
            "#590099",
        ]
        self.wind_gust_levels = [
            2,
            4,
            6,
            8,
            10,
            12,
            14,
            16,
            18,
            20,
            22,
            24,
            26,
            28,
            30,
            32,
            34,
            36,
            38,
            40,
            42,
            44,
            46,
            50,
        ]
        self.wind_speed_colors = [
            "#011FFF",
            "#017CFF",
            "#01C8FF",
            "#2AFCEE",
            "#01FFB7",
            "#01FD3C",
            "#05C347",
            "#7CFF01",
            "#BCFA4A",
            "#FFFF01",
            "#F8D95A",
            "#FDBE01",
            "#FE9A04",
            "#FB652F",
            "#FB5935",
            "#FE0C04",
            "#B2066D",
            "#A107A3",
            "#9001FC",
        ]
        self.wind_speed_levels = [
            0,
            2,
            4,
            6,
            8,
            10,
            12,
            14,
            16,
            18,
            20,
            22,
            24,
            26,
            28,
            30,
            32,
            34,
            36,
        ]
        self.cape_colors = [
            "#0275BA",
            "#01FAFC",
            "#01B3A6",
            "#0AF915",
            "#C5FD01",
            "#FD9401",
            "#FD1301",
            "#B30631",
            "#FF00FF",
            "#8001FD",
        ]
        self.cape_levels = [10, 200, 400, 800, 1200, 1600, 2000, 2500, 3000, 4000, 9000]
        self.msl_colors = [
            "#F200FF",
            "#A300FF",
            "#0D0D4F",
            "#05055B",
            "#0101E0",
            "#6666F7",
            "#B8B8F2",
            "#82CAF5",
            "#F25EA6",
            "#F51329",
            "#B80516",
            "#7D0A15",
        ]
        self.msl_levels = [
            970,
            980,
            984,
            988,
            992,
            996,
            1000,
            1004,
            1008,
            1012,
            1016,
            1020,
            1024,
            1040,
        ]
        self.temp_pressure_colors = [
            "#8200C2",
            "#ED00FA",
            "#FF7DF5",
            "#D47AFF",
            "#0808D6",
            "#007AFF",
            "#00A6FF",
            "#00D1FF",
            "#00F7FF",
            "#CAFCFF",
            "#008233",
            "#38DB78",
            "#00FF3D",
            "#A1FF00",
            "#FAFF00",
            "#FFD600",
            "#FFA100",
            "#FF6B00",
            "#FF2600",
            "#C7030D",
        ]

        # For 850 hPa temperature in KELVIN
        self.temp_pressure_levels = [
            233,
            243,
            248,
            253,
            258,
            263,
            268,
            273,
            276,
            278,
            281,
            283,
            286,
            288,
            291,
            293,
            296,
            298,
            301,
            303,
            308,
        ]
        self.geopotential_colors = [
            "#B8B8F2",
            "#82CAF5",
            "#F25EA6",
            "#F51329",
            "#B80516",
            "#7D0A15",
        ]
        self.geopotential_levels = [48000, 50000, 52000, 54000, 56000, 58000, 60000]

    def _load_config(self):
        """Load configuration from JSON file."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path) as f:
                    return json.load(f)
            else:
                raise FileNotFoundError(
                    f"Configuration file not found: {self.config_path}"
                )
        except Exception as e:
            print(f"Warning: Could not load config file {self.config_path}: {e}")
            return {}

    def _initialize_parameter_defaults(self):
        """Initialize parameter defaults from JSON configuration."""
        config = self._load_config()

        self.parameter_types = {
            "temperature": [],
            "precipitation": [],
            "wind_gust": [],
            "wind_speed": [],
            "wind_component": [],
            "pressure": [],
            "cape": [],
            "temperature_pressure": [],
            "geopotential": [],
            "snowfall": [],
        }

        surface_variables = config.get("surface_variables", {})

        for param_name, param_info in surface_variables.items():
            param_type = self._categorize_parameter(param_name, param_info)
            if param_type in self.parameter_types:
                self.parameter_types[param_type].append(param_name)

        self.surface_variables = surface_variables

        parameter_mappings = config.get("parameter_mappings", {})
        self.param_ids = parameter_mappings.get("param_ids", {})
        self.climate_data_mapping = parameter_mappings.get("climate_data", {})
        self.pressure_levels = parameter_mappings.get("pressure_levels", {})

    def _categorize_parameter(self, param_name: str, param_info: dict) -> str:  # noqa: PLR0911
        """Categorize parameter based on its name and properties."""
        name_lower = param_info.get("name", "").lower()
        if "temperature" in name_lower or param_name in ["2t", "2d", "mn2t6", "mx2t6"]:
            if param_info.get("pressure_level", False):
                return "temperature_pressure"
            return "temperature"
        elif "precipitation" in name_lower or param_name in ["tp", "lsp", "cp"]:
            return "precipitation"
        elif "gust" in name_lower or param_name in ["i10fg"]:
            return "wind_gust"
        elif (
            "wind speed" in name_lower
            or param_name in ["10ff", "ws"]
            or ("wind" in name_lower and "speed" in name_lower)
        ):
            return "wind_speed"
        elif (
            "wind component" in name_lower
            or param_name in ["10u", "10v"]
            or ("wind" in name_lower and "component" in name_lower)
        ):
            return "wind_component"
        elif "pressure" in name_lower or param_name == "msl":
            return "pressure"
        elif (
            "cape" in name_lower
            or "convective available potential energy" in name_lower
            or param_name in ["cape", "capes"]
        ):
            return "cape"
        elif "geopotential" in name_lower or param_name == "z":
            return "geopotential"
        elif "snowfall" in name_lower or param_name in ["sf", "ts"]:
            return "snowfall"

        return "unknown"

    def _get_parameter_type(self, parameter_name: str) -> str:
        """Get the parameter type for a given parameter name."""
        for param_type, params in self.parameter_types.items():
            if parameter_name in params:
                return param_type
        return "unknown"

    def choose_color_palette_and_levels(
        self, parameter_name: str, palette_color: int = None, unit: str = None
    ) -> dict:
        """Choose appropriate color palette and levels for a weather parameter.

        Args:
            parameter_name: Name of the weather parameter
            palette_color: Color palette option (1, 2, or 3) for precipitation parameters
            unit: Unit of the parameter

        Returns:
            Dictionary containing colors, levels, unit, title, and label information

        """
        param_type = self._get_parameter_type(parameter_name)

        config = {
            "title": f"{parameter_name}",
            "colors": ["#0000FF", "#00FF00", "#FFFF00", "#FF8000", "#FF0000"],
            "levels": [0, 25, 50, 75, 100],
            "unit": "",
            "label": parameter_name,
            "param_type": param_type,
        }

        if param_type == "temperature":
            config.update(
                {
                    "title": self._get_temperature_title(parameter_name),
                    "colors": self.temp_colors,
                    "levels": self.temp_levels,
                    "unit": "°C" if unit == "celsius" else "K",
                    "label": "Temperature",
                }
            )

        elif param_type == "precipitation":
            palette_option = palette_color if palette_color in [1, 2, 3] else 1
            config.update(
                {
                    "title": self._get_precipitation_title(parameter_name),
                    "colors": self.precip_colors[palette_option],
                    "levels": self.precip_levels[palette_option],
                    "unit": "mm" if unit == "mm" else "m",
                    "label": "Precipitation",
                }
            )

        elif param_type == "wind_gust":
            config.update(
                {
                    "title": self._get_wind_gust_title(parameter_name),
                    "colors": self.wind_gust_colors,
                    "levels": self.wind_gust_levels,
                    "unit": "m/s",
                    "label": "Wind Gust",
                }
            )

        elif param_type == "wind_speed":
            config.update(
                {
                    "title": self._get_wind_speed_title(parameter_name),
                    "colors": self.wind_speed_colors,
                    "levels": self.wind_speed_levels,
                    "unit": "m/s",
                    "label": "Wind Speed",
                }
            )

        elif param_type == "cape":
            config.update(
                {
                    "title": self._get_cape_title(parameter_name),
                    "colors": self.cape_colors,
                    "levels": self.cape_levels,
                    "unit": "J/kg" if parameter_name == "cape" else "m",
                    "label": "CAPE" if parameter_name == "cape" else "CAPE Shear",
                }
            )

        elif param_type == "wind_component":
            config.update(
                {
                    "title": self._get_wind_component_title(parameter_name),
                    "colors": self.wind_speed_colors,
                    "levels": self.wind_speed_levels,
                    "unit": "m/s",
                    "label": "Zonal component"
                    if "10u" in parameter_name
                    else "Meridional component",
                }
            )

        elif param_type == "pressure":
            config.update(
                {
                    "title": "Mean Sea Level Pressure",
                    "colors": self.msl_colors,
                    "levels": self.msl_levels,
                    "unit": "Pa",
                    "label": "Pressure",
                }
            )

        elif param_type == "temperature_pressure":
            config.update(
                {
                    "title": "Temperature",
                    "colors": self.temp_pressure_colors,
                    "levels": self.temp_pressure_levels,
                    "unit": "°C" if unit == "celsius" else "K",
                    "label": "Temperature",
                }
            )

        elif param_type == "geopotential":
            config.update(
                {
                    "title": "Geopotential",
                    "colors": self.geopotential_colors,
                    "levels": self.geopotential_levels,
                    "unit": "m**2/s**2",
                    "label": "Geopotential",
                }
            )

        elif param_type == "snowfall":
            config.update(
                {
                    "title": "Snowfall",
                    "colors": self.precip_colors[1],  # Use precipitation palette
                    "levels": self.precip_levels[1],
                    "unit": "mm" if unit == "mm" else "m",
                    "label": "Snowfall",
                }
            )

        return config

    def transform_data_and_levels(  # noqa: PLR0912
        self, data, parameter_name: str, levels: list, unit: str = None
    ):
        """Transform both data and levels based on input unit."""
        param_type = self._get_parameter_type(parameter_name)

        if param_type is None:
            return data, levels

        if isinstance(data, xr.DataArray):
            transformed_data = data.copy()
            value_name = data.name if data.name else parameter_name
        else:
            if isinstance(data, np.ndarray):
                transformed_data = data.copy()
            else:
                transformed_data = data.copy()
            value_name = parameter_name

        transformed_levels = levels.copy()

        if param_type in ["temperature", "temperature_pressure"]:
            if unit and unit.lower() == "kelvin":
                transformed_levels = [
                    lvl + 273.15 if lvl < 100 else lvl for lvl in transformed_levels
                ]
            elif unit and unit.lower() == "celsius":
                if isinstance(transformed_data, xr.DataArray):
                    transformed_data = transformed_data - 273.15
                else:
                    transformed_data = transformed_data - 273.15

                transformed_levels = [
                    lvl - 273.15 if lvl > 100 else lvl for lvl in transformed_levels
                ]

        elif param_type in ["precipitation", "snowfall"]:
            if unit and unit.lower() == "m":
                transformed_levels = [lvl / 1000 for lvl in transformed_levels]
            elif unit and unit.lower() == "mm":
                if isinstance(transformed_data, xr.DataArray):
                    transformed_data = transformed_data * 1000
                elif isinstance(transformed_data, np.ndarray):
                    transformed_data = transformed_data * 1000
                elif (
                    hasattr(transformed_data, "__getitem__")
                    and value_name in transformed_data
                ):
                    transformed_data[value_name] = transformed_data[value_name] * 1000

        elif param_type == "pressure":
            if unit and unit.lower() == "hpa":
                if isinstance(transformed_data, xr.DataArray):
                    transformed_data = transformed_data / 100
                elif isinstance(transformed_data, np.ndarray):
                    transformed_data = transformed_data / 100
                elif (
                    hasattr(transformed_data, "__getitem__")
                    and value_name in transformed_data
                ):
                    transformed_data[value_name] = transformed_data[value_name] / 100

        return transformed_data, transformed_levels

    def _get_temperature_title(self, param_name: str) -> str:
        """Get appropriate title for temperature parameters."""
        if hasattr(self, "surface_variables") and param_name in self.surface_variables:
            return self.surface_variables[param_name].get(
                "name", f"{param_name} Temperature"
            )

        titles = {
            "2t": "2m Temperature",
            "2d": "2m Dewpoint Temperature",
            "mn2t6": "Minimum 2m Temperature in the last 6 hours",
            "mx2t6": "Maximum 2m Temperature in the last 6 hours",
        }
        return titles.get(param_name, f"{param_name} Temperature")

    def _get_wind_gust_title(self, param_name: str) -> str:
        """Get appropriate title for wind gust parameters."""
        if hasattr(self, "surface_variables") and param_name in self.surface_variables:
            return self.surface_variables[param_name].get(
                "name", f"{param_name} Wind Gust"
            )

        titles = {"i10fg": "Instantaneous 10m Wind Gust"}
        return titles.get(param_name, f"{param_name} Wind Gust")

    def _get_wind_speed_title(self, param_name: str) -> str:
        """Get appropriate title for wind speed parameters."""
        if hasattr(self, "surface_variables") and param_name in self.surface_variables:
            return self.surface_variables[param_name].get(
                "name", f"{param_name} Wind Speed"
            )

        titles = {"10ff": "Wind Speed"}
        return titles.get(param_name, f"{param_name} Wind Speed")

    def _get_precipitation_title(self, param_name: str) -> str:
        """Get appropriate title for precipitation parameters."""
        if hasattr(self, "surface_variables") and param_name in self.surface_variables:
            return self.surface_variables[param_name].get(
                "name", f"{param_name} Precipitation"
            )

        titles = {
            "tp": "Total Precipitation",
            "lsp": "Large-scale Precipitation",
            "cp": "Convective Precipitation",
        }
        return titles.get(param_name, f"{param_name} Precipitation")

    def _get_wind_component_title(self, param_name: str) -> str:
        """Get appropriate title for wind component parameters."""
        if hasattr(self, "surface_variables") and param_name in self.surface_variables:
            return self.surface_variables[param_name].get(
                "name", f"{param_name} Wind Component"
            )

        titles = {"10u": "10m U-component of Wind", "10v": "10m V-component of Wind"}
        return titles.get(param_name, f"{param_name} Wind Component")

    def _get_cape_title(self, param_name: str) -> str:
        """Get appropriate title for cape parameters."""
        if hasattr(self, "surface_variables") and param_name in self.surface_variables:
            return self.surface_variables[param_name].get(
                "name", f"{param_name} Cape Component"
            )

        titles = {
            "cape": "Convective available potential energy",
            "capes": "Convective Available Potential Energy Shear",
        }
        return titles.get(param_name, f"{param_name} Cape Component")
