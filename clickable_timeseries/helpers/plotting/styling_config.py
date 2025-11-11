import colorsys
import random


class TimeseriesStylingConfiguration:
    """Configuration class for timeseries plotting styles, colors, and parameter settings."""

    def __init__(self, temperature_unit="celsius", precipitation_unit="mm"):
        """Initialize the styling configuration with unit preferences."""
        self.temperature_unit = temperature_unit
        self.precipitation_unit = precipitation_unit

        self._initialize_colors()
        self._initialize_model_styles()
        self._initialize_parameter_configs()

    def _initialize_colors(self):
        """Initialize color palettes for different visualization contexts."""
        # Colors that match map pins for active points
        self.active_point_colors = [
            "#e74c3c",  # Red
            "#3498db",  # Blue
            "#2ecc71",  # Green
            "#f39c12",  # Orange
            "#9b59b6",  # Purple
            "#1abc9c",  # Teal
        ]

        # Base colors for general use
        self.base_colors = [
            "#1f77b4",
            "#ff7f0e",
            "#2ca02c",
            "#d62728",
            "#9467bd",
            "#8c564b",
            "#e377c2",
            "#7f7f7f",
            "#bcbd22",
            "#17becf",
            "#ff6b6b",
            "#4ecdc4",
            "#45b7d1",
            "#96ceb4",
            "#ffeaa7",
            "#dda0dd",
            "#98d8c8",
            "#f7dc6f",
            "#bb8fce",
            "#85c1e9",
        ]

        # Single station colors for different data types
        self.single_station_colors = {
            "obs": "#1f77b4",  # Blue
            "aifs": "#d62728",  # Red
            "ifs": "#ff7f0e",  # Orange
            "forecast": "#2ca02c",  # Green
        }

        # Colors for different precipitation intervals
        self.precipitation_interval_colors = {
            "tp_24h": "#1f77b4",  # Blue
            "tp_12h": "#ff7f0e",  # Orange
            "tp_6h": "#2ca02c",  # Green
        }

    def _initialize_model_styles(self):
        """Initialize line styles and markers for different forecast models."""
        self.model_styles = {
            "Observations": {"dash": "dashdot", "width": 3, "symbol": "circle"},
            "AIFS": {
                "dash": "dash",
                "width": 2,
                "symbol": "diamond",
            },
            "IFS": {"dash": "solid", "width": 2, "symbol": "square"},
            "aifs": {
                "dash": "dash",
                "width": 2,
                "symbol": "diamond",
            },
            "ifs": {"dash": "solid", "width": 2, "symbol": "square"},
        }

        # Single point mode colors (when only one location is selected)
        self.single_point_colors = {
            "AIFS": "red",
            "IFS": "green",
            "aifs": "red",
            "ifs": "green",
            "Observations": "blue",
        }

    def _initialize_parameter_configs(self):
        """Initialize parameter-specific configurations for titles, units, and labels."""
        temp_unit = "°C" if self.temperature_unit == "celsius" else "K"
        temp_name = (
            "Temperature"
            if self.temperature_unit == "celsius"
            else "Temperature (Kelvin)"
        )

        precip_unit = self.precipitation_unit
        precip_name = f"Precipitation ({precip_unit})"

        self.parameter_configs = {
            # Wind parameters
            "10ff": {
                "title": "10m Wind Speed Timeseries",
                "y_axis_label": "Wind Speed (m/s)",
                "unit": "m/s",
                "parameter_name": "Wind Speed",
                "hover_label": "Wind Speed",
            },
            "10ff_daily": {
                "title": "Daily Mean 10m Wind Speed Timeseries",
                "y_axis_label": "Daily Mean Wind Speed (m/s)",
                "unit": "m/s",
                "parameter_name": "Daily Mean Wind Speed",
                "hover_label": "Daily Mean Wind Speed",
            },
            "10fg": {
                "title": "10m Wind Gust Timeseries",
                "y_axis_label": "Wind Gust (m/s)",
                "unit": "m/s",
                "parameter_name": "Wind Gust",
                "hover_label": "Wind Gust",
            },
            "10fg_6h": {
                "title": "Max 6h Wind Gust Timeseries",
                "y_axis_label": "Wind Gust (m/s)",
                "unit": "m/s",
                "parameter_name": "Max 6h Wind Gust",
                "hover_label": "Max 6h Wind Gust",
            },
            "10fg_12h": {
                "title": "Max 12h Wind Gust Timeseries",
                "y_axis_label": "Wind Gust (m/s)",
                "unit": "m/s",
                "parameter_name": "Max 12h Wind Gust",
                "hover_label": "Max 12h Wind Gust",
            },
            "10fg_24h": {
                "title": "Max 24h Wind Gust Timeseries",
                "y_axis_label": "Wind Gust (m/s)",
                "unit": "m/s",
                "parameter_name": "Max 24h Wind Gust",
                "hover_label": "Max 24h Wind Gust",
            },
            "10fg_48h": {
                "title": "Max 48h Wind Gust Timeseries",
                "y_axis_label": "Wind Gust (m/s)",
                "unit": "m/s",
                "parameter_name": "Max 48h Wind Gust",
                "hover_label": "Max 48h Wind Gust",
            },
            "10u": {
                "title": "10m U-component Wind Timeseries",
                "y_axis_label": "U-wind (m/s)",
                "unit": "m/s",
                "parameter_name": "U-component Wind",
                "hover_label": "U-wind",
            },
            "10v": {
                "title": "10m V-component Wind Timeseries",
                "y_axis_label": "V-wind (m/s)",
                "unit": "m/s",
                "parameter_name": "V-component Wind",
                "hover_label": "V-wind",
            },
            # Temperature parameters
            "2d": {
                "title": "2m Dewpoint Temperature Timeseries",
                "y_axis_label": f"Dewpoint Temperature ({temp_unit})",
                "unit": temp_unit,
                "parameter_name": f"Dewpoint {temp_name}",
                "hover_label": "Dewpoint Temperature",
            },
            "2d_24h_max": {
                "title": "Daily Maximum 2m Dewpoint Temperature Timeseries",
                "y_axis_label": f"Dewpoint Temperature ({temp_unit})",
                "unit": temp_unit,
                "parameter_name": f"Daily Maximum Dewpoint {temp_name}",
                "hover_label": "Maximum Dewpoint Temperature",
            },
            "2d_24h_min": {
                "title": "Daily Minimum 2m Dewpoint Temperature Timeseries",
                "y_axis_label": f"Dewpoint Temperature ({temp_unit})",
                "unit": temp_unit,
                "parameter_name": f"Daily Minimum Dewpoint {temp_name}",
                "hover_label": "Minimum Dewpoint Temperature",
            },
            "2t": {
                "title": "2m Temperature Timeseries",
                "y_axis_label": f"Temperature ({temp_unit})",
                "unit": temp_unit,
                "parameter_name": temp_name,
                "hover_label": "Temperature",
            },
            "2t_24h_max": {
                "title": "Daily Maximum 2m Temperature Timeseries",
                "y_axis_label": f"Temperature ({temp_unit})",
                "unit": temp_unit,
                "parameter_name": f"Daily Maximum {temp_name}",
                "hover_label": "Maximum Temperature",
            },
            "2t_24h_min": {
                "title": "Daily Minimum 2m Temperature Timeseries",
                "y_axis_label": f"Temperature ({temp_unit})",
                "unit": temp_unit,
                "parameter_name": f"Daily Minimum {temp_name}",
                "hover_label": "Minimum Temperature",
            },
            # Precipitation parameters
            "tp": {
                "title": "Total Precipitation Timeseries",
                "y_axis_label": f"Precipitation ({precip_unit})",
                "unit": precip_unit,
                "parameter_name": precip_name,
                "hover_label": "Precipitation",
            },
            "tp_deaccum": {
                "title": "Deaccumulated Precipitation Timeseries",
                "y_axis_label": f"Precipitation({precip_unit})",
                "unit": f"{precip_unit}",
                "parameter_name": f"Deaccumulated {precip_name}",
                "hover_label": "Precipitation",
            },
            "cp": {
                "title": "Convective Precipitation Timeseries",
                "y_axis_label": f"Convective Precipitation ({precip_unit})",
                "unit": precip_unit,
                "parameter_name": precip_name,
                "hover_label": "Convective Precipitation",
            },
            "lsp": {
                "title": "Large Scale Precipitation Timeseries",
                "y_axis_label": f"Large Scale Precipitation ({precip_unit})",
                "unit": precip_unit,
                "parameter_name": precip_name,
                "hover_label": "Large Scale Precipitation",
            },
            "cp_deaccum": {
                "title": "Deaccumulated Convective Precipitation Timeseries",
                "y_axis_label": f"Convective Precipitation ({precip_unit})",
                "unit": precip_unit,
                "parameter_name": f"Deaccumulated Convective {precip_name}",
                "hover_label": "Convective Precipitation",
            },
            "lsp_deaccum": {
                "title": "Deaccumulated Large Scale Precipitation Timeseries",
                "y_axis_label": f"Large Scale Precipitation ({precip_unit})",
                "unit": precip_unit,
                "parameter_name": f"Deaccumulated Large Scale {precip_name}",
                "hover_label": "Large Scale Precipitation",
            },
        }

        # Default configuration for unknown parameters
        self.default_config = {
            "title": "Parameter Timeseries",
            "y_axis_label": "Value",
            "unit": "",
            "parameter_name": "Parameter",
            "hover_label": "Value",
        }

    def set_temperature_unit(self, unit):
        """Set the temperature unit preference and reinitialize configs.

        Args:
            unit (str): Temperature unit ('celsius' or 'kelvin')

        """
        if unit.lower() in ["celsius", "kelvin"]:
            self.temperature_unit = unit.lower()
            self._initialize_parameter_configs()
        else:
            raise ValueError("Temperature unit must be 'celsius' or 'kelvin'")

    def set_precipitation_unit(self, unit):
        """Set the precipitation unit preference and reinitialize configs.

        Args:
            unit (str): Precipitation unit ('mm' or 'm')

        """
        if unit.lower() in ["mm", "m"]:
            self.precipitation_unit = unit.lower()
            self._initialize_parameter_configs()
        else:
            raise ValueError("Precipitation unit must be 'mm' or 'm'")

    def get_parameter_config(self, parameter_name):
        """Get configuration for a specific parameter.

        Args:
            parameter_name (str): Name of the parameter

        Returns:
            dict: Configuration dictionary with title, labels, units, etc.

        """
        return self.parameter_configs.get(parameter_name, self.default_config)

    def get_data_color(self, data_type, station_id, active_stations):
        """Get color for data based on whether single or multiple stations are selected.

        Args:
            data_type (str): Type of data ('obs', 'aifs', 'ifs', 'forecast')
            station_id (str): Station identifier
            active_stations (dict): Dictionary mapping station IDs to colors

        Returns:
            str: Hex color code

        """
        if len(active_stations) == 1:
            return self.single_station_colors.get(
                data_type.lower(), self.single_station_colors["obs"]
            )
        else:
            return active_stations.get(station_id, self.base_colors[0])

    def get_model_style(self, model_name):
        """Get line style configuration for a model.

        Args:
            model_name (str): Name of the model

        Returns:
            dict: Style configuration with dash, width, symbol

        """
        if model_name == "Observations":
            style_key = "Observations"
        elif "aifs" in model_name.lower():
            style_key = "AIFS"
        elif "ifs" in model_name.lower() and "aifs" not in model_name.lower():
            style_key = "IFS"
        else:
            style_key = model_name

        return self.model_styles.get(
            style_key, {"dash": "solid", "width": 2, "symbol": "circle"}
        )

    def get_single_point_color(self, model_name, point_color):
        """Get color for single point mode visualization.

        Args:
            model_name (str): Name of the model
            point_color (str): Default point color

        Returns:
            str: Color to use for the line

        """
        return self.single_point_colors.get(model_name, point_color)

    def generate_random_color(self):
        """Generate a random color in hex format.

        Returns:
            str: Random hex color code

        """
        hue = random.randint(0, 360)
        saturation = random.randint(70, 100)
        lightness = random.randint(40, 70)

        r, g, b = colorsys.hls_to_rgb(hue / 360, lightness / 100, saturation / 100)
        return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"

    def format_value_for_hover(self, value, parameter_name):
        """Format value for hover text based on parameter type.

        Args:
            value: The numeric value to format
            parameter_name (str): Name of the parameter

        Returns:
            str: Formatted value string with appropriate units

        """
        config = self.get_parameter_config(parameter_name)

        if parameter_name in [
            "2t",
            "2d",
            "2t_24h_max",
            "2t_24h_min",
            "2d_24h_max",
            "2d_24h_min",
        ]:
            return f"{float(value):.1f}{config['unit']}"
        elif parameter_name == "tp":
            return f"{float(value):.2f}{config['unit']}"
        elif parameter_name in [
            "10ff",
            "10u",
            "10v",
            "10fg",
        ]:
            return f"{float(value):.1f}{config['unit']}"
        else:
            return (
                f"{float(value):.1f}{config['unit']}"
                if config["unit"]
                else f"{float(value):.2f}"
            )

    def get_layout_config(self, config, title_text, single_station_mode=False):
        """Get standardized layout configuration for Plotly figures.

        Args:
            config (dict): Parameter configuration
            title_text (str): Chart title
            single_station_mode (bool): Whether in single station mode

        Returns:
            dict: Plotly layout configuration

        """
        return {
            "title": {
                "text": f"<b>{title_text}</b>",
                "x": 0.5,
                "font": {"size": 16 if single_station_mode else 14, "color": "black"},
            },
            "xaxis": {
                "title": {"text": "<b>Time</b>", "font": {"color": "black"}},
                "tickfont": {"color": "black"},
                "showgrid": True,
                "showline": True,
                "linecolor": "black" if single_station_mode else "gray",
                "linewidth": 2,
                "ticks": "outside",
                "tickwidth": 2,
                "tickcolor": "black",
                "gridcolor": "lightgray",
                "gridwidth": 0.5,
                "tickformat": "%d/%m/%Y %H:%M",
                "tickmode": "auto",
                "nticks": 10,
                "type": "date",
            },
            "yaxis": {
                "title": {
                    "text": f"<b>{config['y_axis_label']}</b>",
                    "font": {"color": "black"},
                },
                "tickfont": {"color": "black"},
                "showline": True,
                "linecolor": "black" if single_station_mode else "gray",
                "linewidth": 2,
                "ticks": "outside",
                "tickwidth": 2,
                "tickcolor": "black",
                "showgrid": True,
                "gridcolor": "lightgray",
                "gridwidth": 0.5,
            },
            "height": 680 if single_station_mode else 500,
            "hovermode": "closest",
            "legend": {
                "orientation": "v",
                "yanchor": "top",
                "y": 1,
                "xanchor": "left",
                "x": 1.02,
                "font": {"size": 10 if single_station_mode else 9, "color": "black"},
            },
            "showlegend": True,
            "margin": {
                "r": 150 if single_station_mode else 200,
                "t": 50 if single_station_mode else 60,
                "b": 50,
                "l": 50,
            },
            "paper_bgcolor": "white",
            "plot_bgcolor": "white",
            "font": {"color": "black"},
        }

    def get_rangeslider_config(self):
        """Get rangeslider configuration for single station mode.

        Returns:
            dict: Rangeslider configuration

        """
        return {
            "visible": True,
            "bgcolor": "rgba(248, 249, 250, 0.8)",
            "bordercolor": "#BDC3C7",
            "borderwidth": 1,
            "thickness": 0.06,
        }
