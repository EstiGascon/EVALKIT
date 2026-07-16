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
        self.current_geopotential_unit = "m"

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

    def _get_live_step_frequency(self) -> int:
        """Return the step_frequency to enforce at plot time.

        Prefers the live value from the UI's Frequency dropdown so that
        changing it after retrieval immediately affects new plots. Falls
        back to the value captured in ``current_config`` and finally to 1.
        """
        # Live widget value
        try:
            if self.ui is not None and getattr(self.ui, "widgets", None):
                w = self.ui.widgets.get("step_frequency")
                if w is not None and getattr(w, "value", None) is not None:
                    val = int(w.value)
                    return val
        except Exception:
            pass
        # Fallback to config
        try:
            cfg_val = self.current_config.get("parameters", {}).get("step_frequency", 1) if self.current_config else 1
            val = int(cfg_val) if cfg_val is not None else 1
            return val
        except Exception:
            return 1

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
        self.multi_model_data = None

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
            data: Dictionary containing forecast data (single or multi-model)
            config: Configuration dictionary

        """
        self.multi_model_data = None

        if isinstance(data, dict) and data.get("_multi_model"):
            self.multi_model_data = data["models"]
            first_model = next(iter(self.multi_model_data))
            self.current_data = self.multi_model_data[first_model]
            # Preserve observations so they are available for meteogram/plumes
            if "observations" in data:
                self.current_data["observations"] = data["observations"]
        else:
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

                        # Fallback: also read from stored metadata in case synthetic
                        # calculated fields (e.g. 6-hour precipitation) do not expose
                        # their shortName through the field API.
                        metadata = data_info.get("metadata", {})
                        for meta_key in ("parameters", "calculated_parameters"):
                            for param in metadata.get(meta_key, []):
                                if param:
                                    parameter_set.add(param)

            if "10u" in parameter_set and "10v" in parameter_set:
                parameter_set.add("ws")

            # Remove 10si (scalar wind speed from GRIB) in favour of the
            # calculated ws derived from 10u and 10v components.
            parameter_set.discard("10si")

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
        self, parameter=None, step=None, unit_value=None, palette_value=None,
        precip_accumulation=None,
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
            self._last_stamps_error = None

            figure = self.stamps_plotter.create_ensemble_stamp_plot(
                stamp_ds=self.current_data,
                parameter=parameter,
                step=step,
                palette_option=palette_value,
                unit=target_unit,
                precip_accumulation=precip_accumulation,
            )

            if figure:
                with self.widgets["plot_output"]:
                    clear_output(wait=True)
                    display(figure.fig)
                plt.close(figure.fig)
                return True

            self._last_stamps_error = (
                f"No figure returned for parameter={parameter}, "
                f"step={step}, unit={target_unit}"
            )
            return False

        except Exception as e:
            import traceback

            self._last_stamps_error = str(e)
            with self.widgets["plot_output"]:
                clear_output(wait=True)
                print(f"Error creating stamps plot: {e}")
                traceback.print_exc()
            return False

    def get_available_steps_for_parameter(self, parameter):
        """Get available steps filtered by parameter type.

        For stamps plots we only expose steps where BOTH the deterministic
        forecast (FC) AND at least one ensemble source (CF or PF) have data
        for the requested parameter.  Showing FC-only steps in the widget
        would produce incomplete stamp plots with no ensemble panels.

        Args:
            parameter: Parameter name

        Returns:
            List of available steps for the parameter

        """
        if not hasattr(self, "current_data") or not self.current_data:
            return [0, 6, 12, 18, 24, 48, 72, 96, 120, 144, 168, 192, 216, 240]

        def _to_hours(step_val):
            """Convert a GRIB step value to integer hours (handles timedelta)."""
            if step_val is None:
                return None
            if isinstance(step_val, int):
                return step_val
            try:
                return int(step_val)
            except (TypeError, ValueError):
                pass
            try:  # datetime.timedelta
                return int(step_val.total_seconds() // 3600)
            except AttributeError:
                pass
            try:
                return int(str(step_val))
            except (ValueError, TypeError):
                return None

        steps_by_source = {}

        for key in ["fc", "cf", "pf"]:
            if key in self.current_data:
                data_info = self.current_data[key]
                if isinstance(data_info, dict) and "dataset" in data_info:
                    dataset = data_info["dataset"]
                    key_steps = set()
                    for field in dataset:
                        try:
                            field_param = field.metadata("shortName")
                            if field_param == parameter:
                                step = field.metadata("step")
                                step_range = field.metadata().get("stepRange", "")

                                if step_range and "-" in str(step_range):
                                    step_val = _to_hours(step_range.split("-")[1])
                                else:
                                    step_val = _to_hours(step)

                                if step_val is not None:
                                    key_steps.add(step_val)

                        except Exception:
                            continue
                    if key_steps:
                        steps_by_source[key] = key_steps

        print(f"[steps] get_available_steps_for_parameter({parameter!r}): "
              + ", ".join(f"{k}={sorted(v)[:20]}{'...' if len(v) > 20 else ''}"
                          for k, v in steps_by_source.items()))

        if not steps_by_source:
            return []

        # Ensemble steps: union of CF and PF steps
        ensemble_steps = steps_by_source.get("cf", set()) | steps_by_source.get("pf", set())
        fc_steps = steps_by_source.get("fc", set())

        if ensemble_steps and fc_steps:
            # Prefer steps present in both FC and ensemble sources
            common = fc_steps & ensemble_steps
            if common:
                return sorted(common)
            # Fall back: ensemble steps only (FC might use a different shortName)
            return sorted(ensemble_steps)

        if ensemble_steps:
            return sorted(ensemble_steps)

        # No ensemble data at all – return whatever FC has
        return sorted(fc_steps)

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
                result = plot_method(parameter, lat, lon, target_unit)
                if result:
                    created_plots += 1

            return created_plots > 0

        except Exception:
            with self.widgets["plot_output"]:
                clear_output(wait=True)
            raise

    def create_meteogram_plot(self, parameter=None, unit_value=None):
        """Create meteogram plot for selected points.

        Args:
            parameter: Parameter name
            unit_value: Target unit for conversion

        Returns:
            True if successful, False otherwise

        """
        if self.multi_model_data and len(self.multi_model_data) > 1:
            return self._create_comparison_meteogram(parameter, unit_value)

        def plot_method(param, lat, lon, unit):
            model_class = self.current_config.get("parameters", {}).get("model_class", "")
            step_freq = self._get_live_step_frequency()
            chart = self.meteogram_plotter.create_meteogram(
                meteogram_data=self.current_data,
                parameter=param,
                lat=lat,
                lon=lon,
                target_unit=unit,
                model_class=model_class,
                step_frequency=step_freq if step_freq > 1 else None,
            )
            if chart:
                with self.widgets["plot_output"]:
                    clear_output(wait=True)
                    display(chart)
                return True
            return False

        return self._create_point_plot(plot_method, parameter, unit_value, "meteogram")

    def _thin_data_by_frequency(self, model_data, step_freq):
        """Return the step frequency to be applied after point extraction.

        Instead of filtering earthkit FieldLists (which can corrupt grid
        metadata on reduced Gaussian grids), the actual step thinning is
        done later by ``_thin_xarray_by_frequency`` on the extracted xarray
        DataArrays.

        This method is kept for backward compatibility but simply returns
        the data unchanged.  The step_freq value is forwarded via the config
        to the meteogram/plumes plotters.
        """
        return model_data

    def _create_comparison_meteogram(self, parameter=None, unit_value=None):
        """Create overlaid meteogram for multiple models on the same figure."""
        if not self.multi_model_data or not self.selected_points:
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

            first_point = next(iter(self.selected_points.values()))
            lat, lon = first_point

            model_display = {"ifs": "IFS-ENS", "aifs": "AIFS-ENS", "aifs-single": "AIFS-Single", "ifs-4km": "IFS 4.4km", "custom": "Custom"}
            model_colors = {
                "ifs":         {"cf": "#D32F2F", "pf": "#1565C0", "pf_fill": "rgba(21,101,192,0.15)"},
                "aifs":        {"cf": "#2E7D32", "pf": "#F57F17", "pf_fill": "rgba(245,127,23,0.15)"},
                "aifs-single": {"cf": "#2E7D32", "pf": "#2E7D32", "pf_fill": "rgba(46,125,50,0.15)"},
                "ifs-4km":     {"cf": "#7B1FA2", "pf": "#7B1FA2", "pf_fill": "rgba(123,31,162,0.15)"},
                "custom":      {"cf": "#6A1B9A", "pf": "#00838F", "pf_fill": "rgba(0,131,143,0.15)"},
            }

            # Step frequency from UI Frequency dropdown is the single source
            # of truth for temporal resolution. Native model interval is
            # only relevant for horizontal (spatial) resolution.
            step_freq = self._get_live_step_frequency()

            # Build a single figure with overlaid traces
            import plotly.graph_objects as go
            combined = go.Figure()
            first_chart = None

            obs = self.current_data.get("observations")
            obs_added = False

            for model_name, model_data in self.multi_model_data.items():
                colors = model_colors.get(model_name, model_colors["ifs"])
                display_name = model_display.get(model_name, model_name.upper())

                # Temporarily override the plotter's color palette
                orig_palette = dict(self.meteogram_plotter.color_palette)
                self.meteogram_plotter.color_palette["cf"] = colors["cf"]
                self.meteogram_plotter.color_palette["pf"] = colors["pf"]
                self.meteogram_plotter.color_palette["pf_fill"] = colors["pf_fill"]

                # Thin data to the user's step frequency
                plot_data = dict(model_data)
                if step_freq > 1:
                    plot_data = self._thin_data_by_frequency(plot_data, step_freq)

                # Add observations only to first model; remove from others
                if obs and not obs_added:
                    plot_data["observations"] = obs
                    obs_added = True
                else:
                    plot_data.pop("observations", None)

                chart = self.meteogram_plotter.create_meteogram(
                    meteogram_data=plot_data,
                    parameter=parameter,
                    lat=lat,
                    lon=lon,
                    target_unit=target_unit,
                    model_class=model_name,
                    step_frequency=step_freq if step_freq > 1 else None,
                )
                self.meteogram_plotter.color_palette = orig_palette

                if chart:
                    if first_chart is None:
                        first_chart = chart
                    for trace in chart.data:
                        is_obs = trace.name and "Observation" in trace.name
                        if is_obs:
                            trace.legendgroup = "observations"
                            trace.meta = "_obs"
                        else:
                            if trace.name and trace.showlegend is not False:
                                trace.name = f"{display_name} – {trace.name}"
                            trace.legendgroup = model_name
                            trace.meta = model_name
                        combined.add_trace(trace)

            if first_chart is not None:
                # Offset Box and Bar traces side-by-side per model
                import numpy as np
                import pandas as pd
                model_names = list(self.multi_model_data.keys())
                n_models = len(model_names)
                if n_models > 1:
                    # Detect step interval from any Box or Bar trace
                    step_ms = None
                    for trace in combined.data:
                        trace_type = type(trace).__name__
                        if trace_type in ("Box", "Bar") and hasattr(trace, "x") and trace.x is not None and len(trace.x) >= 2:
                            try:
                                x_sorted = sorted(pd.Timestamp(t) for t in trace.x[:20])
                                for i in range(len(x_sorted) - 1):
                                    gap_ms = (x_sorted[i + 1] - x_sorted[i]).total_seconds() * 1000
                                    if gap_ms > 0 and (step_ms is None or gap_ms < step_ms):
                                        step_ms = gap_ms
                            except Exception:
                                continue

                    if step_ms and step_ms > 0:
                        # Each model gets a slot; leave 20% gap between slots
                        slot_ms = step_ms * 0.8 / n_models
                        box_width = slot_ms * 0.85  # box fills 85% of its slot

                        for trace in combined.data:
                            if trace.meta not in model_names:
                                continue
                            idx = model_names.index(trace.meta)
                            offset_ms = (idx - (n_models - 1) / 2) * slot_ms
                            offset_td = pd.Timedelta(milliseconds=offset_ms)

                            trace_type = type(trace).__name__
                            if trace_type in ("Box", "Bar"):
                                try:
                                    x_vals = trace.x
                                    if isinstance(x_vals, np.ndarray):
                                        trace.x = pd.DatetimeIndex(x_vals) + offset_td
                                    else:
                                        trace.x = [pd.Timestamp(t) + offset_td for t in x_vals]
                                except Exception:
                                    pass

                            # Set explicit box/bar width
                            if trace_type == "Box":
                                trace.width = box_width
                            elif trace_type == "Bar":
                                trace.width = box_width / 1000  # Bar width in seconds

                layout = first_chart.layout.to_plotly_json()
                layout.pop("template", None)

                # Build title listing all compared models
                all_display = ", ".join(
                    model_display.get(m, m.upper()) for m in self.multi_model_data
                )
                if "title" in layout and layout["title"].get("text"):
                    orig_title = layout["title"]["text"]
                    import re as _re
                    layout["title"]["text"] = _re.sub(
                        r"Meteogram\s*\([^)]*\)",
                        f"Meteogram Comparison ({all_display})",
                        orig_title,
                    )

                # Organised legend: one group per model, observations separate
                for mname in model_names:
                    dname = model_display.get(mname, mname.upper())
                    for trace in combined.data:
                        if trace.legendgroup == mname:
                            trace.legendgrouptitle = {"text": dname}
                            break
                # Observations group title
                for trace in combined.data:
                    if trace.legendgroup == "observations":
                        trace.legendgrouptitle = {"text": "Observations"}
                        break

                layout["legend"] = {
                    "orientation": "h",
                    "yanchor": "top",
                    "y": -0.15,
                    "xanchor": "center",
                    "x": 0.5,
                    "font": {"size": 9},
                    "groupclick": "togglegroup",
                    "tracegroupgap": 15,
                    "traceorder": "grouped",
                }
                layout["margin"] = {"l": 70, "r": 40, "t": 100, "b": 140}

                combined.update_layout(**layout)

                with self.widgets["plot_output"]:
                    display(combined)
                return True

            return False

        except Exception:
            with self.widgets["plot_output"]:
                clear_output(wait=True)
            raise

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
        if self.multi_model_data and len(self.multi_model_data) > 1:
            return self._create_comparison_plumes(parameter, unit_value)

        def plot_method(param, lat, lon, unit):
            model_class = self.current_config.get("parameters", {}).get("model_class", "")
            step_freq = self._get_live_step_frequency()
            fig = self.plumes_plotter.create_plumes_plot(
                forecast_data=self.current_data,
                parameter=param,
                lat=lat,
                lon=lon,
                target_unit=unit,
                figsize=self.plumes_size,
                forecast_type=self.forecast_type,
                model_class=model_class,
                step_frequency=step_freq if step_freq > 1 else None,
            )
            if fig:
                with self.widgets["plot_output"]:
                    fig.show()
                return True
            return False

        try:
            return self._create_point_plot(plot_method, parameter, unit_value, "plumes")
        except Exception:
            with self.widgets["plot_output"]:
                clear_output(wait=True)
            raise

    def _create_comparison_plumes(self, parameter=None, unit_value=None):
        """Create overlaid plumes plot for multiple models on the same figure."""
        if not self.multi_model_data or not self.selected_points:
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

            first_point = next(iter(self.selected_points.values()))
            lat, lon = first_point

            model_display = {"ifs": "IFS-ENS", "aifs": "AIFS-ENS", "custom": "Custom"}

            # Step frequency from UI Frequency dropdown is the single source
            # of truth for temporal resolution.
            step_freq = self._get_live_step_frequency()

            import plotly.graph_objects as go
            combined = go.Figure()
            first_fig = None

            obs = self.current_data.get("observations")
            obs_added = False

            for model_name, model_data in self.multi_model_data.items():
                display_name = model_display.get(model_name, model_name.upper())
                plot_data = dict(model_data)

                # Thin data to the user's step frequency
                if step_freq > 1:
                    plot_data = self._thin_data_by_frequency(plot_data, step_freq)

                # Add observations only to first model; remove from others
                if obs and not obs_added:
                    plot_data["observations"] = obs
                    obs_added = True
                else:
                    plot_data.pop("observations", None)

                fig = self.plumes_plotter.create_plumes_plot(
                    forecast_data=plot_data,
                    parameter=parameter,
                    lat=lat,
                    lon=lon,
                    target_unit=target_unit,
                    figsize=self.plumes_size,
                    forecast_type=self.forecast_type,
                    model_class=model_name,
                    step_frequency=step_freq if step_freq > 1 else None,
                )
                if fig:
                    if first_fig is None:
                        first_fig = fig
                    for trace in fig.data:
                        is_obs = trace.name and "Observation" in trace.name
                        if is_obs:
                            trace.legendgroup = "observations"
                            trace.meta = "_obs"
                        else:
                            if trace.name and trace.showlegend is not False:
                                trace.name = f"{display_name} – {trace.name}"
                            trace.legendgroup = model_name
                            trace.meta = model_name
                        combined.add_trace(trace)

            if first_fig is not None:
                # Offset Bar traces side-by-side per model (for precipitation)
                import numpy as np
                import pandas as pd
                model_names = list(self.multi_model_data.keys())
                n_models = len(model_names)
                if n_models > 1:
                    step_ms = None
                    for trace in combined.data:
                        trace_type = type(trace).__name__
                        if trace_type == "Bar" and hasattr(trace, "x") and trace.x is not None and len(trace.x) >= 2:
                            try:
                                x_sorted = sorted(pd.Timestamp(t) for t in trace.x[:20])
                                for i in range(len(x_sorted) - 1):
                                    gap_ms = (x_sorted[i + 1] - x_sorted[i]).total_seconds() * 1000
                                    if gap_ms > 0 and (step_ms is None or gap_ms < step_ms):
                                        step_ms = gap_ms
                            except Exception:
                                continue

                    if step_ms and step_ms > 0:
                        slot_ms = step_ms * 0.8 / n_models
                        bar_width_s = slot_ms * 0.85 / 1000  # Bar width in seconds
                        for trace in combined.data:
                            trace_type = type(trace).__name__
                            if trace_type == "Bar" and trace.meta in model_names:
                                idx = model_names.index(trace.meta)
                                offset_ms = (idx - (n_models - 1) / 2) * slot_ms
                                offset_td = pd.Timedelta(milliseconds=offset_ms)
                                try:
                                    x_vals = trace.x
                                    if isinstance(x_vals, np.ndarray):
                                        trace.x = pd.DatetimeIndex(x_vals) + offset_td
                                    else:
                                        trace.x = [pd.Timestamp(t) + offset_td for t in x_vals]
                                except Exception:
                                    pass
                                trace.width = bar_width_s

                layout = first_fig.layout.to_plotly_json()
                layout.pop("template", None)

                # Build title listing all compared models
                all_display = ", ".join(
                    model_display.get(m, m.upper()) for m in self.multi_model_data
                )
                if "title" in layout and layout["title"].get("text"):
                    import re as _re
                    layout["title"]["text"] = _re.sub(
                        r"Plumes\s*\([^)]*\)",
                        f"Plumes Comparison ({all_display})",
                        layout["title"]["text"],
                    )

                # Organised legend: one group per model, observations separate
                for mname in model_names:
                    dname = model_display.get(mname, mname.upper())
                    for trace in combined.data:
                        if trace.legendgroup == mname:
                            trace.legendgrouptitle = {"text": dname}
                            break
                for trace in combined.data:
                    if trace.legendgroup == "observations":
                        trace.legendgrouptitle = {"text": "Observations"}
                        break

                layout["legend"] = {
                    "orientation": "h",
                    "yanchor": "top",
                    "y": -0.18,
                    "xanchor": "center",
                    "x": 0.5,
                    "font": {"size": 9},
                    "groupclick": "togglegroup",
                    "tracegroupgap": 15,
                    "traceorder": "grouped",
                }
                layout["margin"] = {"t": 100, "b": 160, "l": 80, "r": 50}

                combined.update_layout(**layout)

                with self.widgets["plot_output"]:
                    combined.show()
                return True

            return False

        except Exception:
            with self.widgets["plot_output"]:
                clear_output(wait=True)
            raise

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
            "geopotential": "current_geopotential_unit",
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
            "geopotential": self.current_geopotential_unit,
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
