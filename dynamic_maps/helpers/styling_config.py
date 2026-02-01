import re

import pandas as pd
import xarray as xr


class StylingConfiguration:
    """A class for dynamic plotting weather parameters with customizable color palettes and units."""

    def __init__(self):
        """Initialize the WeatherPlotter with predefined color palettes and levels."""
        self._initialize_palettes()
        self._initialize_parameter_defaults()

    def _initialize_palettes(self):
        """Initialize all color palettes and their corresponding levels."""
        # Temperature color palette
        self.temp_colors = [
            "rgb(130,0,194)",
            "rgb(237,0,250)",
            "rgb(255,125,245)",
            "rgb(212,122,255)",
            "rgb(8,8,214)",
            "rgb(0,122,255)",
            "rgb(0,166,255)",
            "rgb(0,209,255)",
            "rgb(0,247,255)",
            "rgb(202,252,255)",
            "rgb(0,130,51)",
            "rgb(56,219,120)",
            "rgb(0,255,61)",
            "rgb(161,255,0)",
            "rgb(250,255,0)",
            "rgb(255,214,0)",
            "rgb(255,161,0)",
            "rgb(255,107,0)",
            "rgb(255,38,0)",
            "rgb(199,3,13)",
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

        # Precipitation color palettes
        self.precip_colors = {
            1: [  # Basic palette (option 1)
                "rgb(191,242,237)",
                "rgb(115,237,199)",
                "rgb(18,217,156)",
                "rgb(135,204,33)",
                "rgb(153,232,15)",
                "rgb(230,255,102)",
                "rgb(227,227,17)",
                "rgb(255,186,1)",
                "rgb(255,125,1)",
                "rgb(255,0,0)",
                "rgb(217,1,255)",
                "rgb(161,2,235)",
                "rgb(10,10,214)",
                "rgb(11,11,110)",
                "rgb(115,115,115)",
            ],
            2: [  # Extended palette (option 2)
                "rgb(153,230,255)",
                "rgb(115,179,255)",
                "rgb(77,128,255)",
                "rgb(38,77,255)",
                "rgb(204,255,51)",
                "rgb(166,242,0)",
                "rgb(128,217,0)",
                "rgb(38,191,26)",
                "rgb(0,140,48)",
                "rgb(255,217,0)",
                "rgb(255,189,0)",
                "rgb(255,158,0)",
                "rgb(255,128,0)",
                "rgb(217,115,0)",
                "rgb(255,191,191)",
                "rgb(255,128,128)",
                "rgb(255,0,0)",
                "rgb(204,0,0)",
                "rgb(153,0,0)",
                "rgb(217,153,255)",
                "rgb(191,102,255)",
                "rgb(153,51,255)",
                "rgb(128,0,230)",
                "rgb(89,0,153)",
                "rgb(128,128,128)",
                "rgb(89,89,89)",
                "rgb(64,64,64)",
                "rgb(38,38,38)",
                "rgb(13,13,13)",
            ],
            3: [  # High intensity palette (option 3)
                "rgb(146,244,149)",
                "rgb(1,255,166)",
                "rgb(0,166,128)",
                "rgb(1,170,255)",
                "rgb(1,111,255)",
                "rgb(84,64,234)",
                "rgb(149,77,249)",
                "rgb(215,77,249)",
                "rgb(228,56,182)",
                "rgb(228,56,79)",
                "rgb(228,119,56)",
                "rgb(228,179,56)",
                "rgb(238,238,44)",
                "rgb(238,240,214)",
                "rgb(128,128,128)",
            ],
        }

        self.acc_precip_colors = {
            1: [  # Basic palette (option 1)
                "rgb(191,242,237)",
                "rgb(115,237,199)",
                "rgb(18,217,156)",
                "rgb(135,204,33)",
                "rgb(153,232,15)",
                "rgb(230,255,102)",
                "rgb(227,227,17)",
                "rgb(255,186,1)",
                "rgb(255,125,1)",
                "rgb(255,0,0)",
                "rgb(217,1,255)",
                "rgb(161,2,235)",
                "rgb(10,10,214)",
                "rgb(11,11,110)",
                "rgb(115,115,115)",
            ],
            2: [  # Extended palette (option 2)
                "rgb(153,230,255)",
                "rgb(115,179,255)",
                "rgb(77,128,255)",
                "rgb(38,77,255)",
                "rgb(204,255,51)",
                "rgb(166,242,0)",
                "rgb(128,217,0)",
                "rgb(38,191,26)",
                "rgb(0,140,48)",
                "rgb(255,217,0)",
                "rgb(255,189,0)",
                "rgb(255,158,0)",
                "rgb(255,128,0)",
                "rgb(217,115,0)",
                "rgb(255,191,191)",
                "rgb(255,128,128)",
                "rgb(255,0,0)",
                "rgb(204,0,0)",
                "rgb(153,0,0)",
                "rgb(217,153,255)",
                "rgb(191,102,255)",
                "rgb(153,51,255)",
                "rgb(128,0,230)",
                "rgb(89,0,153)",
                "rgb(128,128,128)",
                "rgb(89,89,89)",
                "rgb(64,64,64)",
                "rgb(38,38,38)",
                "rgb(13,13,13)",
            ],
            3: [  # High intensity palette (option 3)
                "rgb(146,244,149)",
                "rgb(1,255,166)",
                "rgb(0,166,128)",
                "rgb(1,170,255)",
                "rgb(1,111,255)",
                "rgb(84,64,234)",
                "rgb(149,77,249)",
                "rgb(215,77,249)",
                "rgb(228,56,182)",
                "rgb(228,56,79)",
                "rgb(228,119,56)",
                "rgb(228,179,56)",
                "rgb(238,238,44)",
                "rgb(238,240,214)",
                "rgb(128,128,128)",
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

        # Accumulated precipitation levels
        self.acc_precip_levels = {
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

        # Wind gust color palette
        self.wind_gust_colors = [
            "rgb(153,230,255)",
            "rgb(115,179,255)",
            "rgb(77,128,255)",
            "rgb(38,77,255)",
            "rgb(204,255,51)",
            "rgb(166,242,0)",
            "rgb(128,217,0)",
            "rgb(38,191,26)",
            "rgb(0,140,48)",
            "rgb(255,217,0)",
            "rgb(255,189,0)",
            "rgb(255,158,0)",
            "rgb(255,128,0)",
            "rgb(217,115,0)",
            "rgb(255,191,191)",
            "rgb(255,128,128)",
            "rgb(255,0,0)",
            "rgb(204,0,0)",
            "rgb(153,0,0)",
            "rgb(217,153,255)",
            "rgb(191,102,255)",
            "rgb(153,51,255)",
            "rgb(128,0,230)",
            "rgb(89,0,153)",
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

        # Wind speed color palette
        self.wind_speed_colors = [
            "rgb(1,31,255)",
            "rgb(1,124,255)",
            "rgb(1,200,255)",
            "rgb(42,252,238)",
            "rgb(1,255,183)",
            "rgb(1,253,60)",
            "rgb(5,195,71)",
            "rgb(124,255,1)",
            "rgb(188,250,74)",
            "rgb(255,255,1)",
            "rgb(248,217,90)",
            "rgb(253,190,1)",
            "rgb(254,154,4)",
            "rgb(251,101,47)",
            "rgb(251,89,53)",
            "rgb(254,12,4)",
            "rgb(178,6,109)",
            "rgb(161,7,163)",
            "rgb(144,1,252)",
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

    def _initialize_parameter_defaults(self):
        """Initialize default parameter configurations."""
        self.parameter_types = {
            # Temperature parameters
            "temperature": [
                "mx2t_max",
                "mn2t_min",
                "2t",
                "2d",
                "mn2t",
                "mx2t",
                "mx2t_min",
                "mn2t_max",
            ],
            # Precipitation parameters
            "precipitation": ["tp", "lsp", "cp"],
            "accumulated_precipitation": ["acc_tp", "acc_cp", "acc_lsp"],
            # Wind parameters
            "wind_gust": [
                "10fg",
                "10fg_max",
                "10fg_min",
            ],
            "wind_speed": ["10ff", "10ff_max", "10ff_min"],
            "wind_component": ["10u", "10v"],
        }

    def _get_parameter_type(self, parameter_name: str) -> str | None:
        """Get the parameter type for a given parameter name."""
        for param_type, params in self.parameter_types.items():
            if parameter_name in params:
                return param_type
        return None

    def choose_color_palette_and_levels(
        self, parameter_name: str, palette_color: int | None = None, unit: str = None
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
            "colors": ["blue", "green", "yellow", "orange", "red"],
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

        elif param_type == "accumulated_precipitation":
            palette_option = palette_color if palette_color in [1, 2, 3] else 1

            if parameter_name == "acc_tp":
                title = "Accumulated Total Precipitation"
            elif parameter_name == "acc_cp":
                title = "Accumulated Convective Precipitation"
            elif parameter_name == "acc_lsp":
                title = "Accumulated Large-scale Precipitation"
            else:
                title = f"Accumulated {parameter_name.replace('acc_', '').upper()} Precipitation"

            config.update(
                {
                    "title": title,
                    "colors": self.acc_precip_colors[palette_option],
                    "levels": self.acc_precip_levels[palette_option],
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

        return config

    def transform_data_and_levels(  # noqa: PLR0912
        self,
        data: xr.DataArray | pd.DataFrame,
        parameter_name: str,
        levels: list[float],
        unit: str = None,
    ) -> tuple[xr.DataArray | pd.DataFrame, list[float]]:
        """Transform both data and levels based on input unit."""
        param_type = self._get_parameter_type(parameter_name)

        if param_type is None:
            return data, levels

        if isinstance(data, xr.DataArray):
            transformed_data = data.copy()
            value_name = data.name if data.name else parameter_name
        else:
            transformed_data = data.copy()
            value_name = parameter_name

        transformed_levels = levels.copy()

        if param_type == "temperature":
            if unit and unit.lower() == "kelvin":
                if isinstance(transformed_data, xr.DataArray):
                    transformed_data = transformed_data  # noqa: PLW0127
                else:
                    transformed_data[value_name] = transformed_data[value_name]
                transformed_levels = [int(lvl + 273.15) for lvl in transformed_levels]

            elif unit and unit.lower() == "celsius":
                if isinstance(transformed_data, xr.DataArray):
                    transformed_data = transformed_data - 273.15
                else:
                    transformed_data[value_name] = transformed_data[value_name] - 273.15
                transformed_levels = transformed_levels  # noqa: PLW0127

        elif param_type in ["precipitation", "accumulated_precipitation"]:
            if unit and unit.lower() == "m":
                if isinstance(transformed_data, xr.DataArray):
                    transformed_data = transformed_data  # noqa: PLW0127
                else:
                    transformed_data[value_name] = transformed_data[value_name]

                transformed_levels = [lvl / 1000 for lvl in transformed_levels]

            elif unit and unit.lower() == "mm":
                # Convert from mm to meters (if needed)
                if isinstance(transformed_data, xr.DataArray):
                    transformed_data = transformed_data * 1000

                else:
                    transformed_data[value_name] = transformed_data[value_name] * 1000
                transformed_levels = transformed_levels  # noqa: PLW0127

        return transformed_data, transformed_levels

    def _get_temperature_title(self, param_name: str) -> str:
        """Get appropriate title for temperature parameters."""
        titles = {
            "mx2t_max": "Maximum 2m Temperature (Daily Maximum)",
            "mn2t_min": "Minimum 2m Temperature (Daily Minimum)",
            "mx2t_min": "Minimum 2m Temperature (Daily Maximum)",
            "mn2t_max": "Maximum 2m Temperature (Daily Minimum)",
            "2t": "2m Temperature",
            "2d": "2m Dewpoint Temperature",
            "mn2t": "Minimum 2m Temperature",
            "mx2t": "Maximum 2m Temperature",
        }
        return titles.get(param_name, f"{param_name} Temperature")

    def _get_wind_gust_title(self, param_name: str) -> str:
        """Get appropriate title for wind gust parameters."""
        titles = {
            "10fg": "10m Wind Gust",
            "10fg_max": "10m Maximum Wind Gust",
            "10fg_min": "10m Minimum Wind Gust",
        }
        return titles.get(param_name, f"{param_name} Wind Gust")

    def _get_wind_speed_title(self, param_name: str) -> str:
        """Get appropriate title for wind speed parameters."""
        titles = {
            "10ff": "Wind Speed",
            "10ff_max": "Maximum Wind Speed",
            "10ff_min": "Minimum Wind Speed",
        }
        return titles.get(param_name, f"{param_name} Wind Speed")

    def _get_precipitation_title(self, param_name: str) -> str:
        """Get appropriate title for wind gust parameters."""
        titles = {
            "tp": "Total Precipitation",
            "lsp": "Large-scale Precipitation",
            "cp": "Convective Precipitation",
        }
        return titles.get(param_name, f"{param_name} Wind Gust")

    def _get_wind_component_title(self, param_name: str) -> str:
        """Get appropriate title for wind component parameters."""
        titles = {"10u": "10m U-component of Wind", "10v": "10m V-component of Wind"}
        return titles.get(param_name, f"{param_name} Wind Component")

    def _rgb_to_hex_colors(self, rgb_colors):
        """Convert RGB color strings to hex format for hvplot.

        Args:
            rgb_colors: List of RGB color strings

        Returns:
            List of hex color strings

        """
        hex_colors = []

        for color in rgb_colors:
            if color.startswith("rgba"):
                rgba_match = re.match(
                    r"rgba\((\d+),(\d+),(\d+),([0-9]*\.?[0-9]+)\)", color
                )
                if rgba_match:
                    r, g, b, a = rgba_match.groups()
                    r, g, b = int(r), int(g), int(b)
                    hex_color = f"#{r:02x}{g:02x}{b:02x}"
                    hex_colors.append(hex_color)
                else:
                    hex_colors.append("#000000")
            elif color.startswith("rgb"):
                rgb_match = re.match(r"rgb\((\d+),(\d+),(\d+)\)", color)
                if rgb_match:
                    r, g, b = map(int, rgb_match.groups())
                    hex_color = f"#{r:02x}{g:02x}{b:02x}"
                    hex_colors.append(hex_color)
                else:
                    hex_colors.append("#000000")
            else:
                hex_colors.append(color)

        return hex_colors
