import traceback
from typing import Any

import ipywidgets as widgets
import matplotlib.pyplot as plt
from helpers.parameter_config_manager import ParameterConfigManager
from helpers.plotting.cdf import CDFPlotting
from helpers.plotting.meteogram import MeteogramPlotting
from helpers.plotting.plumes import PlumesPlotting
from helpers.plotting.stamps import StampsPlotting
from helpers.styling_config import StylingConfiguration
from IPython.display import clear_output, display


class PlottingManager:
    """Central manager for all weather data plotting operations."""

    def __init__(self, config_file: str = "model_config.json"):
        """Initialize plotting manager with plot classes and styling.

        Args:
            config_file: Path to model configuration file

        """
        self.config_file = config_file
        self.styling_config = StylingConfiguration()
        self.stamps_plotter = StampsPlotting(self.styling_config)
        self.cdf_plotter = CDFPlotting(self.styling_config, self.config_file)
        self.meteogram_plotter = MeteogramPlotting(self.styling_config)
        self.plumes_plotter = PlumesPlotting(self.styling_config)

        self.current_temperature_unit = "celsius"
        self.current_precipitation_unit = "mm"
        self.current_pressure_unit = "hpa"
        self.current_wind_unit = "ms"

        self.current_data = None
        self.current_config = None
        self.selected_points = {}
        self.available_parameters = []
        self.available_steps = []

        self.ui = None

        self.param_config = ParameterConfigManager()
        self.parameter_categories = self.param_config.parameter_categories

        self.setup_minimal_widgets()

    def set_ui_reference(self, ui):
        """Set reference to UI for alert messages.

        Args:
            ui: UI instance for displaying alerts

        """
        self.ui = ui

    def setup_minimal_widgets(self):
        """Set up minimal widgets for internal plotting operations."""
        self.widgets = {}

        self.widgets["plot_type"] = widgets.Dropdown(
            options=[
                ("Ensemble Stamps", "stamps"),
                ("CDF Analysis", "cdf"),
                ("Meteogram", "meteogram"),
                ("Plumes (Time Series)", "plumes"),
            ],
            value="stamps",
            description="Plot Type:",
            layout=widgets.Layout(display="none"),
        )

        self.widgets["plot_output"] = widgets.Output()

        self.current_parameter = None
        self.current_step = 48
        self.current_palette = 1
        self.current_figsize = (14, 8)
        self.plumes_size = (1200, 600)
        self.forecast_type = "cf"

    def _get_parameter_category(self, parameter: str) -> str:
        """Get the category of a parameter.

        Args:
            parameter: Parameter name

        Returns:
            Category name (temperature, precipitation, pressure, wind, or other)

        """
        for category, params in self.parameter_categories.items():
            if parameter in params:
                return category
        return "other"

    def set_data(self, data: dict[str, Any], config: dict[str, Any]):
        """Set current data and configuration.

        Args:
            data: Dictionary containing forecast data
            config: Configuration dictionary

        """
        self.current_data = data
        self.current_config = config

        self._extract_available_parameters()
        self._extract_available_steps()

        if self.available_parameters:
            self.current_parameter = self.available_parameters[0]

    def _extract_available_parameters(self):
        """Extract available parameters from the current data."""
        self.available_parameters = []

        try:
            parameter_set = set()

            for key in ["fc", "cf", "pf"]:
                if key in self.current_data:
                    data_info = self.current_data[key]
                    if isinstance(data_info, dict) and "dataset" in data_info:
                        dataset = data_info["dataset"]
                        for field in dataset:
                            try:
                                param = field.metadata("shortName")
                                if param:
                                    parameter_set.add(param)
                            except Exception:
                                continue

            if "10u" in parameter_set and "10v" in parameter_set:
                parameter_set.add("ws")

            if parameter_set:
                self.available_parameters = sorted(parameter_set)
            else:
                config_params = self.current_config.get("parameters", {}).get(
                    "parameters", []
                )
                self.available_parameters = (
                    sorted(config_params) if config_params else ["2t"]
                )

        except Exception:
            self.available_parameters = ["2t"]

    def _extract_available_steps(self):
        """Extract available forecast steps from the current data."""
        self.available_steps = []

        try:
            precip_steps = set()
            other_steps = set()

            for key in ["fc", "cf", "pf"]:
                if key in self.current_data:
                    data_info = self.current_data[key]
                    if isinstance(data_info, dict) and "dataset" in data_info:
                        dataset = data_info["dataset"]
                        for field in dataset:
                            try:
                                param = field.metadata("shortName")
                                step = field.metadata("step")
                                step_range = field.metadata().get("stepRange", "")

                                step_val = (
                                    int(step_range.split("-")[1])
                                    if step_range and "-" in str(step_range)
                                    else (int(step) if step is not None else None)
                                )

                                if step_val is not None:
                                    if param in ["tp", "lsp", "cp"]:
                                        if step_val >= 6 and step_val % 6 == 0:
                                            precip_steps.add(step_val)
                                    else:
                                        other_steps.add(step_val)

                            except Exception:
                                continue

            if "forecast_data" in self.current_data:
                forecast_data = self.current_data["forecast_data"]
                if isinstance(forecast_data, dict) and "scenarios" in forecast_data:
                    for scenario_data in forecast_data["scenarios"].values():
                        if (
                            isinstance(scenario_data, dict)
                            and "dataset" in scenario_data
                        ):
                            for field in scenario_data["dataset"]:
                                try:
                                    param = field.metadata("shortName")
                                    step = field.metadata("step")
                                    step_range = field.metadata().get("stepRange", "")

                                    step_val = (
                                        int(step_range.split("-")[1])
                                        if step_range and "-" in str(step_range)
                                        else (int(step) if step is not None else None)
                                    )

                                    if step_val is not None:
                                        if (
                                            param in ["tp", "lsp", "cp"]
                                            and step_val >= 6
                                            and step_val % 6 == 0
                                        ):
                                            precip_steps.add(step_val)
                                        else:
                                            other_steps.add(step_val)

                                except Exception:
                                    continue

            if precip_steps:
                combined_steps = set(precip_steps)
                common_steps = [
                    0,
                    6,
                    12,
                    18,
                    24,
                    48,
                    72,
                    96,
                    120,
                    144,
                    168,
                    192,
                    216,
                    240,
                ]
                combined_steps.update(
                    step for step in common_steps if step in other_steps
                )
                self.available_steps = sorted(combined_steps)
            elif other_steps:
                self.available_steps = sorted(other_steps)

            if 48 in self.available_steps:
                self.current_step = 48
            elif 6 in self.available_steps:
                self.current_step = 6
            elif self.available_steps:
                self.current_step = self.available_steps[0]
            else:
                self.current_step = 48

        except Exception:
            pass

    def update_selected_points(self, points: dict[str, tuple[float, float]]):
        """Update selected points from map interaction.

        Args:
            points: Dictionary mapping point IDs to (lat, lon) tuples

        """
        self.selected_points = points

    def create_stamps_plot(
        self, parameter=None, step=None, unit_value=None, palette_value=None
    ):
        """Create stamps plot with step validation.

        Args:
            parameter: Parameter name to plot
            step: Forecast step in hours
            unit_value: Target unit for conversion
            palette_value: Color palette option

        Returns:
            True if successful, False otherwise

        """
        if not self.current_data:
            return False

        parameter = parameter or self.current_parameter
        step = step if step is not None else self.current_step
        palette_value = (
            palette_value if palette_value is not None else self.current_palette
        )

        if not parameter:
            return False

        if step not in self.available_steps and self.available_steps:
            step = min(self.available_steps, key=lambda x: abs(x - step))

        try:
            if unit_value:
                self._set_unit_for_parameter(parameter, unit_value)

            target_unit = self._get_target_unit_for_parameter(parameter)
            self.current_step = step

            figure = self.stamps_plotter.create_ensemble_stamp_plot(
                stamp_ds=self.current_data,
                parameter=parameter,
                step=step,
                palette_option=palette_value,
                unit=target_unit,
            )

            if figure:
                with self.widgets["plot_output"]:
                    clear_output(wait=True)
                    display(figure.fig)
                plt.close(figure.fig)
                return True
            return False

        except Exception:
            with self.widgets["plot_output"]:
                clear_output(wait=True)
            return False

    def get_available_steps_for_parameter(self, parameter):
        """Get available steps filtered by parameter type.

        Args:
            parameter: Parameter name

        Returns:
            List of available steps for the parameter

        """
        if not hasattr(self, "current_data") or not self.current_data:
            return [0, 6, 12, 18, 24, 48, 72, 96, 120, 144, 168, 192, 216, 240]

        param_steps = set()

        for key in ["fc", "cf", "pf"]:
            if key in self.current_data:
                data_info = self.current_data[key]
                if isinstance(data_info, dict) and "dataset" in data_info:
                    dataset = data_info["dataset"]
                    for field in dataset:
                        try:
                            field_param = field.metadata("shortName")
                            if field_param == parameter:
                                step = field.metadata("step")
                                step_range = field.metadata().get("stepRange", "")

                                step_val = (
                                    int(step_range.split("-")[1])
                                    if step_range and "-" in str(step_range)
                                    else (int(step) if step is not None else None)
                                )

                                if step_val is not None:
                                    param_steps.add(step_val)

                        except Exception:
                            continue

        return sorted(param_steps) if param_steps else []

    def _create_point_plot(self, plot_method, parameter, unit_value, plot_type_name):
        """Create point-based plots (meteogram, CDF, plumes).

        Args:
            plot_method: Method to call for plot creation
            parameter: Parameter name
            unit_value: Target unit
            plot_type_name: Name of plot type for messages

        Returns:
            True if successful, False otherwise

        """
        if not self.current_data or not self.selected_points:
            return False

        parameter = parameter or self.current_parameter
        if not parameter:
            return False

        try:
            with self.widgets["plot_output"]:
                clear_output(wait=True)

            if unit_value:
                self._set_unit_for_parameter(parameter, unit_value)

            target_unit = self._get_target_unit_for_parameter(parameter)

            created_plots = 0
            for _point_id, (lat, lon) in self.selected_points.items():
                try:
                    result = plot_method(parameter, lat, lon, target_unit)
                    if result:
                        created_plots += 1
                except Exception:
                    pass

            return created_plots > 0

        except Exception:
            with self.widgets["plot_output"]:
                clear_output(wait=True)
            return False

    def create_meteogram_plot(self, parameter=None, unit_value=None):
        """Create meteogram plot for selected points.

        Args:
            parameter: Parameter name
            unit_value: Target unit for conversion

        Returns:
            True if successful, False otherwise

        """

        def plot_method(param, lat, lon, unit):
            chart = self.meteogram_plotter.create_meteogram(
                meteogram_data=self.current_data,
                parameter=param,
                lat=lat,
                lon=lon,
                target_unit=unit,
            )
            if chart:
                with self.widgets["plot_output"]:
                    clear_output(wait=True)
                    chart.show()
                return True
            return False

        return self._create_point_plot(plot_method, parameter, unit_value, "meteogram")

    def create_cdf_plot(self, parameter=None, unit_value=None):
        """Create CDF plot for selected points.

        Args:
            parameter: Parameter name
            unit_value: Target unit for conversion

        Returns:
            True if successful, False otherwise

        """

        def plot_method(param, lat, lon, unit):
            fig = self.cdf_plotter.create_cdf_plot(
                cdf_data=self.current_data,
                parameter=param,
                lat=lat,
                lon=lon,
                target_unit=unit,
                figsize=self.current_figsize,
            )
            if fig:
                with self.widgets["plot_output"]:
                    display(fig)
                plt.close(fig)
                return True
            return False

        return self._create_point_plot(plot_method, parameter, unit_value, "CDF")

    def create_plumes_plot(self, parameter=None, unit_value=None):
        """Create plumes (time series) plot for selected points.

        Args:
            parameter: Parameter name
            unit_value: Target unit for conversion

        Returns:
            True if successful, False otherwise

        """

        def plot_method(param, lat, lon, unit):
            fig = self.plumes_plotter.create_plumes_plot(
                forecast_data=self.current_data,
                parameter=param,
                lat=lat,
                lon=lon,
                target_unit=unit,
                figsize=self.plumes_size,
                forecast_type=self.forecast_type,
            )
            if fig:
                with self.widgets["plot_output"]:
                    fig.show()
                return True
            return False

        try:
            return self._create_point_plot(plot_method, parameter, unit_value, "plumes")
        except Exception:
            traceback.print_exc()
            return False

    def _set_unit_for_parameter(self, parameter: str, unit_value: str):
        """Set unit for parameter based on category.

        Args:
            parameter: Parameter name
            unit_value: Unit value to set

        """
        category = self._get_parameter_category(parameter)
        unit_map = {
            "temperature": "current_temperature_unit",
            "precipitation": "current_precipitation_unit",
            "pressure": "current_pressure_unit",
            "wind": "current_wind_unit",
        }
        if category in unit_map:
            setattr(self, unit_map[category], unit_value)

    def _get_target_unit_for_parameter(self, parameter: str) -> str:
        """Get target unit for a parameter based on current unit settings.

        Args:
            parameter: Parameter name

        Returns:
            Target unit string or None

        """
        category = self._get_parameter_category(parameter)
        unit_map = {
            "temperature": self.current_temperature_unit,
            "precipitation": self.current_precipitation_unit,
            "pressure": self.current_pressure_unit,
            "wind": self.current_wind_unit,
        }
        return unit_map.get(category)

    def is_point_based_plot(self, plot_type: str) -> bool:
        """Check if plot type requires point selection.

        Args:
            plot_type: Type of plot (stamps, cdf, meteogram, plumes)

        Returns:
            True if plot type requires points

        """
        return plot_type in ["cdf", "meteogram", "plumes"]

    def get_plot_output_widget(self):
        """Get the plot output widget.

        Returns:
            IPython Output widget

        """
        return self.widgets["plot_output"]

    def clear_plots(self):
        """Clear all plots from output widget."""
        try:
            with self.widgets["plot_output"]:
                clear_output(wait=True)
        except Exception:
            pass

    def get_simplified_status(self) -> dict[str, Any]:
        """Get simplified status for auto-plotting UI.

        Returns:
            Dictionary with current status information

        """
        return {
            "available_parameters": self.available_parameters,
            "available_steps": self.available_steps,
            "selected_points_count": len(self.selected_points),
            "data_loaded": bool(self.current_data),
            "current_parameter": self.current_parameter,
        }

    def __repr__(self):
        """Return string representation for debugging.

        Returns:
            String with key status information including number of parameters,
            selected points count, and data loaded status.

        """
        status = self.get_simplified_status()
        return f"PlottingManager(params={len(status['available_parameters'])}, points={status['selected_points_count']}, data_loaded={status['data_loaded']})"
