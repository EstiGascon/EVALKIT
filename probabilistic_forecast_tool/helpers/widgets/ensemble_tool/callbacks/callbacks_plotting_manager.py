import traceback

import ipywidgets as widgets  # type: ignore

from helpers.parameter_config_manager import ParameterConfigManager


class PlottingManagerCallbacks:
    """Handles plotting operations and plot management."""

    def __init__(self, parent):
        """Initialize plotting manager callbacks.

        Args:
            parent: Parent EnsembleCallbacks instance

        """
        self.parent = parent
        self.config_manager = ParameterConfigManager()

        self._cache_parameter_lists()

    def _cache_parameter_lists(self):
        """Cache parameter lists from config for efficient access."""
        self.calculated_params = self._get_calculated_parameters()

    def _get_calculated_parameters(self):
        """Get list of calculated parameters from config.

        Returns:
            list: Parameters with type='calculated'

        """
        calculated = []
        for param, info in self.config_manager.surface_variables.items():
            if info.get("type") == "calculated":
                calculated.append(param)
        return calculated

    def create_stamps_plot(self, parameter, step, unit_value, palette_value, precip_accumulation=None):
        """Create stamps plot using plotting manager.

        Args:
            parameter: Parameter to plot
            step: Forecast step
            unit_value: Unit for display
            palette_value: Palette selection
            precip_accumulation: Optional accumulation window in hours for
                precipitation parameters (tp/lsp/cp). If None, raw field
                values are plotted.

        Returns:
            bool: True if successful

        """
        try:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Creating stamps plot: {parameter.upper()} at T+{step}h...",
                    "info",
                    section="plotting",
                )

            if not self.parent.plotting_manager:
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Plotting system not available.",
                        "error",
                        section="plotting",
                        permanent=True,
                    )
                return False

            if (
                hasattr(self.parent.plotting_manager, "available_steps")
                and self.parent.plotting_manager.available_steps
                and step not in self.parent.plotting_manager.available_steps
            ):
                available_steps = self.parent.plotting_manager.available_steps
                closest_step = min(available_steps, key=lambda x: abs(x - step))

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        f"Step T+{step}h not available. Using closest step: T+{closest_step}h",
                        "warning",
                        section="plotting",
                        permanent=True,
                    )
                step = closest_step

            success = self.parent.plotting_manager.create_stamps_plot(
                parameter=parameter,
                step=step,
                unit_value=unit_value,
                palette_value=palette_value,
                precip_accumulation=precip_accumulation,
            )

            if success:
                self._display_plot_in_ui()

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        f"Stamps plot created! Parameter: {parameter.upper()}, Step: T+{step}h",
                        "success",
                        section="plotting",
                    )
            else:
                if self.parent.ui:
                    last_err = getattr(self.parent.plotting_manager, "_last_stamps_error", "")
                    msg = (
                        f"Could not create stamps plot for {parameter.upper()} at T+{step}h. "
                    )
                    if last_err:
                        msg += str(last_err)
                    else:
                        msg += "Check that this parameter and step exist in the retrieved data."
                    self.parent.ui.show_alert_message(
                        msg,
                        "error",
                        section="plotting",
                        permanent=True,
                    )

            return success

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error creating stamps plot: {e}",
                    "error",
                    section="plotting",
                    permanent=True,
                )
            return False

    def create_cdf_plot(self, parameter, unit_value):
        """Create CDF plot using plotting manager.

        Args:
            parameter: Parameter to plot
            unit_value: Unit for display

        Returns:
            bool: True if successful

        """
        try:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    "Creating CDF plot automatically...", "info", section="plotting"
                )

            if not self.parent.plotting_manager:
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Plotting system not available.",
                        "error",
                        section="plotting",
                        permanent=True,
                    )
                return False

            if hasattr(self.parent.map_handler, "validate_point_in_current_bbox"):
                point_coords = list(
                    self.parent.plotting_manager.selected_points.values()
                )[0]
                lat, lon = point_coords

                if not self.parent.map_handler.validate_point_in_current_bbox(lat, lon):
                    return False

            success = self.parent.plotting_manager.create_cdf_plot(
                parameter=parameter, unit_value=unit_value
            )

            if success:
                self._display_plot_in_ui()

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        f"CDF plot created! Parameter: {parameter.upper()}",
                        "success",
                        section="plotting",
                        permanent=True,
                    )

            return success

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error creating CDF plot: {e}",
                    "error",
                    section="plotting",
                    permanent=True,
                )
            return False

    def create_meteogram_plot(self, parameter, unit_value):
        """Create meteogram plot using plotting manager.

        Args:
            parameter: Parameter to plot
            unit_value: Unit for display

        Returns:
            bool: True if successful

        """
        try:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    "Creating meteogram plot automatically...",
                    "info",
                    section="plotting",
                    permanent=True,
                )

            if not self.parent.plotting_manager:
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Plotting system not available.",
                        "error",
                        section="plotting",
                        permanent=True,
                    )
                return False

            if hasattr(self.parent.map_handler, "validate_point_in_current_bbox"):
                point_coords = list(
                    self.parent.plotting_manager.selected_points.values()
                )[0]
                lat, lon = point_coords

                if not self.parent.map_handler.validate_point_in_current_bbox(lat, lon):
                    return False

            success = self.parent.plotting_manager.create_meteogram_plot(
                parameter=parameter, unit_value=unit_value
            )

            if success:
                self._display_plot_in_ui()

                if self.parent.ui:
                    param_display_name = parameter.upper()
                    if parameter in self.parent.surface_variables:
                        param_display_name = self.parent.surface_variables[
                            parameter
                        ].get("name", parameter.upper())

                    self.parent.ui.show_alert_message(
                        f"Meteogram created! Parameter: {param_display_name}",
                        "success",
                        section="plotting",
                        permanent=True,
                    )
            else:
                if self.parent.ui:
                    pm = self.parent.plotting_manager
                    if not pm.current_data:
                        msg = "No data loaded. Please retrieve or load data first."
                    elif not pm.selected_points:
                        msg = "No point selected. Please click the map or use '+ Add Point'."
                    else:
                        msg = f"Parameter '{parameter}' could not be plotted. It may not be present in the loaded data."
                    self.parent.ui.show_alert_message(
                        msg, "error", section="plotting", permanent=True
                    )

            return success

        except Exception as e:
            traceback.print_exc()
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error creating meteogram: {e}",
                    "error",
                    section="plotting",
                    permanent=True,
                )
            return False

    def create_plumes_plot(self, parameter, unit_value):
        """Create plumes plot using plotting manager.

        Args:
            parameter: Parameter to plot
            unit_value: Unit for display

        Returns:
            bool: True if successful

        """
        try:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    "Creating plumes plot automatically...",
                    "info",
                    section="plotting",
                    permanent=True,
                )

            if not self.parent.plotting_manager:
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Plotting system not available.",
                        "error",
                        section="plotting",
                        permanent=True,
                    )
                return False

            if hasattr(self.parent.map_handler, "validate_point_in_current_bbox"):
                point_coords = list(
                    self.parent.plotting_manager.selected_points.values()
                )[0]
                lat, lon = point_coords

                if not self.parent.map_handler.validate_point_in_current_bbox(lat, lon):
                    return False

            success = self.parent.plotting_manager.create_plumes_plot(
                parameter=parameter, unit_value=unit_value
            )

            if success:
                self._display_plot_in_ui()

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        f"Plumes plot created! Parameter: {parameter.upper()}",
                        "success",
                        section="plotting",
                        permanent=True,
                    )
            else:
                if self.parent.ui:
                    pm = self.parent.plotting_manager
                    if not pm.current_data:
                        msg = "No data loaded. Please retrieve or load data first."
                    elif not pm.selected_points:
                        msg = "No point selected. Please click the map or use '+ Add Point'."
                    else:
                        msg = f"Parameter '{parameter}' could not be plotted. It may not be present in the loaded data."
                    self.parent.ui.show_alert_message(
                        msg, "error", section="plotting", permanent=True
                    )

            return success

        except Exception as e:
            traceback.print_exc()
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error creating plumes plot: {e}",
                    "error",
                    section="plotting",
                    permanent=True,
                )
            return False

    def clear_plots(self):
        """Clear all plots."""
        try:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    "Clearing all plots...", "info", section="plotting", permanent=True
                )

            if self.parent.plotting_manager:
                self.parent.plotting_manager.clear_plots()

            if hasattr(self.parent.ui, "plot_output_container"):
                self.parent.ui.layout_manager.plot_output_container.children = []

            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    "All plots cleared successfully.",
                    "success",
                    section="plotting",
                    permanent=True,
                )

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error clearing plots: {e}",
                    "error",
                    section="plotting",
                    permanent=True,
                )

    def clear_selected_points(self):
        """Clear the selected point for analysis."""
        try:
            if hasattr(self.parent, "plotting_manager"):
                self.parent.plotting_manager.update_selected_points({})

            if self.parent.map_handler:
                self.parent.map_handler.clear_all_points()

        except Exception as e:
            print(f"Error clearing selected point: {e}")
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error clearing point: {e}",
                    "error",
                    section="plotting",
                    permanent=True,
                )

    def on_add_manual_point_click(self):
        """Handle manual point addition from lat/lon inputs."""
        try:
            lat = self.parent.ui.widgets["manual_lat_input"].value
            lon = self.parent.ui.widgets["manual_lon_input"].value
            if not (-90 <= lat <= 90):
                self.parent.ui.show_alert_message(
                    "Latitude must be between -90 and 90 degrees",
                    "error",
                    section="plotting",
                )
                return

            if not (-180 <= lon <= 180):
                self.parent.ui.show_alert_message(
                    "Longitude must be between -180 and 180 degrees",
                    "error",
                    section="plotting",
                )
                return
            if not (
                hasattr(self.parent.ui, "data_loaded") and self.parent.ui.data_loaded
            ):
                self.parent.ui.show_alert_message(
                    "Please load data first before adding points.",
                    "warning",
                    section="plotting",
                )
                return
            if (
                not hasattr(self.parent.ui, "current_plot_type")
                or not self.parent.ui.current_plot_type
            ):
                self.parent.ui.show_alert_message(
                    "Please select a plot type first.", "warning", section="plotting"
                )
                return
            plot_config = self.parent.ui.plot_configs.get(
                self.parent.ui.current_plot_type, {}
            )
            if not plot_config.get("requires_points", False):
                self.parent.ui.show_alert_message(
                    f"{self.parent.ui.current_plot_type.title()} plots don't require point selection.",
                    "info",
                    section="plotting",
                )
                return
            if self.parent.map_handler:
                if not self.parent.map_handler.is_point_in_bbox(lat, lon):
                    bbox = self.parent.map_handler.get_current_bbox()
                    if bbox:
                        self.parent.ui.show_alert_message(
                            f"Point ({lat:.4f}°N, {lon:.4f}°E) is outside the current bounding box.<br>"
                            f"Current bbox: N:{bbox['north']:.2f}° S:{bbox['south']:.2f}° "
                            f"E:{bbox['east']:.2f}° W:{bbox['west']:.2f}°",
                            "warning",
                            section="plotting",
                        )
                    return
                if self.parent.map_handler.has_selected_point():
                    self.parent.map_handler.clear_all_points()
                point_id = self.parent.map_handler._add_single_point(lat, lon)

                if point_id:
                    self.parent.map_handler._update_plotting_manager_with_single_point()
                    if hasattr(self.parent.ui, "on_map_point_selected"):
                        self.parent.ui.on_map_point_selected(lat, lon)

                    self.parent.ui.show_alert_message(
                        f"Point added at ({lat:.4f}°N, {lon:.4f}°E)",
                        "success",
                        section="plotting",
                    )
                    self.parent.ui.widgets["manual_lat_input"].value = 0.0
                    self.parent.ui.widgets["manual_lon_input"].value = 0.0

                else:
                    self.parent.ui.show_alert_message(
                        "Failed to add point to map.", "error", section="plotting"
                    )
            else:
                self.parent.ui.show_alert_message(
                    "Map handler not available", "error", section="plotting"
                )

        except Exception as e:
            traceback.print_exc()
            self.parent.ui.show_alert_message(
                f"Error adding point: {str(e)}", "error", section="plotting"
            )

    def refresh_parameter_options_from_data(self):
        """Refresh parameter options from loaded data."""
        if not self.parent.current_data:
            return

        try:
            detected_params = self._detect_all_parameters()

            if not detected_params:
                return

            param_options = self._build_parameter_options(detected_params)

            self._update_parameter_selector(param_options)

            self._update_plotting_manager(detected_params)

            self._log_parameter_refresh(detected_params)

        except Exception as e:
            self._handle_refresh_error(e)

    def _detect_all_parameters(self):
        """Detect all available parameters from current data.

        Returns:
            list: Sorted list of detected parameter names

        """
        detected_params = set()

        detected_params.update(self._detect_from_standard_data())

        detected_params.update(self._detect_from_forecast_scenarios())

        detected_params.update(self._add_calculated_parameters(detected_params))

        # Remove 10si (scalar wind speed from GRIB) in favour of the
        # calculated ws derived from 10u and 10v components.
        detected_params.discard("10si")

        return sorted(detected_params)

    def _detect_from_standard_data(self):
        """Detect parameters from standard data types (fc, cf, pf).

        Returns:
            set: Set of detected parameter names

        """
        detected_params = set()

        for data_type in ["fc", "cf", "pf"]:
            if data_type not in self.parent.current_data:
                continue

            params = self._extract_params_from_dataset(
                self.parent.current_data[data_type]
            )
            detected_params.update(params)

        return detected_params

    def _detect_from_forecast_scenarios(self):
        """Detect parameters from forecast scenarios.

        Returns:
            set: Set of detected parameter names

        """
        detected_params = set()

        if "forecast_data" not in self.parent.current_data:
            return detected_params

        forecast_data = self.parent.current_data["forecast_data"]

        if not isinstance(forecast_data, dict) or "scenarios" not in forecast_data:
            return detected_params

        for scenario_name, scenario_data in forecast_data["scenarios"].items():
            try:
                params = self._extract_params_from_dataset(scenario_data)
                detected_params.update(params)
            except Exception as e:
                print(f"Error processing scenario {scenario_name}: {e}")

        return detected_params

    def _extract_params_from_dataset(self, data_info):
        """Extract parameter names from a dataset.

        Args:
            data_info: Data information dictionary

        Returns:
            set: Set of parameter names

        """
        params = set()

        if not isinstance(data_info, dict) or "dataset" not in data_info:
            return params

        try:
            dataset = data_info["dataset"]
            all_fields = list(dataset)

            for field in all_fields:
                param = self._get_param_from_field(field)
                if param:
                    params.add(param)
        except Exception:
            pass

        # Fallback: read from stored metadata in case synthetic calculated fields
        # (e.g. 6-hour precipitation created by FieldList.from_array) do not
        # expose their shortName through the field API.
        metadata = data_info.get("metadata", {})
        for meta_key in ("parameters", "calculated_parameters"):
            for param in metadata.get(meta_key, []):
                if param:
                    params.add(param)

        return params

    def _get_param_from_field(self, field):
        """Get parameter name from a field.

        Args:
            field: Field object

        Returns:
            str or None: Parameter name

        """
        try:
            param = field.metadata("shortName")
            if param and param in self.calculated_params:
                print(f"Found calculated parameter: {param}")
            return param
        except Exception:
            return None

    def _add_calculated_parameters(self, detected_params):
        """Add calculated parameters based on available base parameters.

        Args:
            detected_params: Set of detected parameters

        Returns:
            set: Additional calculated parameters

        """
        calculated = set()

        for param, info in self.config_manager.surface_variables.items():
            if info.get("type") != "calculated":
                continue

            if param == "ws":
                if "10u" in detected_params and "10v" in detected_params:
                    calculated.add("ws")

        return calculated

    def _build_parameter_options(self, detected_params):
        """Build parameter options for UI selector.

        Args:
            detected_params: List of detected parameter names

        Returns:
            list: List of (display_text, value) tuples

        """
        param_options = []

        for param in detected_params:
            display_text = self._get_parameter_display_text(param)
            param_options.append((display_text, param))

        return param_options

    def _get_parameter_display_text(self, param):
        """Get display text for a parameter using config.

        Args:
            param: Parameter name

        Returns:
            str: Display text

        """
        if param in self.config_manager.surface_variables:
            param_info = self.config_manager.surface_variables[param]
            name = param_info.get("name", param.upper())
            units = param_info.get("units", "")
            return f"{name} ({units})" if units else name

        return param.upper()

    def _update_parameter_selector(self, param_options):
        """Update the parameter selector widget.

        Args:
            param_options: List of parameter options

        """
        if not self.parent.ui:
            return

        if not hasattr(self.parent.ui.layout_manager, "plot_interface_widgets"):
            return

        plot_widgets = self.parent.ui.layout_manager.plot_interface_widgets

        if "parameter_selector" not in plot_widgets:
            return

        try:
            self._set_parameter_selector_options(plot_widgets, param_options)
        except Exception as e:
            print(f"Error updating plotting parameter selector: {e}")

    def _set_parameter_selector_options(self, plot_widgets, param_options):
        """Set options for parameter selector and preserve/set value.

        Args:
            plot_widgets: Dictionary of plot interface widgets
            param_options: List of parameter options

        """
        selector = plot_widgets["parameter_selector"]

        current_value = selector.value

        selector.options = param_options

        available_values = [opt[1] for opt in param_options]

        if current_value and current_value in available_values:
            selector.value = current_value
            self.parent.ui.auto_plot_parameter = current_value
        elif param_options:
            selector.value = param_options[0][1]
            self.parent.ui.auto_plot_parameter = param_options[0][1]

        if hasattr(self.parent.ui, "_update_auto_plot_unit"):
            self.parent.ui._update_auto_plot_unit()

    def _update_plotting_manager(self, detected_params):
        """Update plotting manager with available parameters.

        Args:
            detected_params: List of detected parameters

        """
        if hasattr(self.parent, "plotting_manager"):
            self.parent.plotting_manager.available_parameters = detected_params

    def _log_parameter_refresh(self, detected_params):
        """Log parameter refresh results.

        Args:
            detected_params: List of detected parameters

        """
        calculated_params = [p for p in detected_params if p in self.calculated_params]

        if calculated_params:
            print(f"Available calculated parameters: {calculated_params}")

        print(f"Total parameters available for plotting: {len(detected_params)}")

    def _handle_refresh_error(self, error):
        """Handle error during parameter refresh.

        Args:
            error: Exception that occurred

        """
        print(f"Error refreshing parameters from data: {error}")
        traceback.print_exc()

        if self.parent.ui:
            self.parent.ui.show_alert_message(
                f"Error refreshing parameters: {error}",
                "error",
                section="plotting",
                permanent=True,
            )

    def update_parameters_for_plot_type(self, plot_type):
        """Update parameter dropdown options based on the selected plot type.

        Args:
            plot_type: Selected plot type

        """
        plot_specific_params = self._get_parameters_for_plot_type(plot_type)

        if self.parent.ui:
            self.parent.ui.widgets["parameters"].options = plot_specific_params
            if plot_specific_params:
                first_param_value = plot_specific_params[0][1]
                self.parent.ui.widgets["parameters"].value = [first_param_value]

    def _get_parameters_for_plot_type(self, plot_type):
        """Get parameters specific to the plot type from config.

        Args:
            plot_type: Plot type name

        Returns:
            list: List of parameter tuples (text, value)

        """
        if not plot_type or plot_type not in self.parent.use_cases:
            return self._get_default_parameters()

        use_case = self.parent.use_cases[plot_type]
        plot_params = use_case.get("typical_params", [])

        if not plot_params:
            return self._get_default_parameters()

        parameter_options = []
        for param_key in plot_params:
            display_text = self._get_parameter_display_text(param_key)
            parameter_options.append((display_text, param_key))

        return parameter_options

    def _get_default_parameters(self):
        """Get default parameter list from surface_variables in config.

        Returns:
            list: List of parameter tuples (text, value)

        """
        if not self.config_manager.surface_variables:
            raise ValueError(
                "Surface variables not loaded from config. "
                "Check config file path and format."
            )

        parameter_options = []

        for param_key, param_info in self.config_manager.surface_variables.items():
            if param_info.get("type") == "calculated":
                continue

            display_text = self._get_parameter_display_text(param_key)
            parameter_options.append((display_text, param_key))

        if not parameter_options:
            raise ValueError("No valid parameters found in surface_variables config.")

        return parameter_options

    def _display_plot_in_ui(self):
        """Display the plot from plotting manager in the UI container."""
        try:
            plot_widget = self.parent.plotting_manager.get_plot_output_widget()

            with plot_widget:
                pass

            plot_container = widgets.VBox(
                [plot_widget],
                layout=widgets.Layout(
                    width="100%",
                    height="auto",
                    overflow_x="auto",
                    overflow_y="auto",
                    border="1px solid #ddd",
                    padding="10px",
                ),
            )

            self.parent.ui.layout_manager.plot_output_container.children = [
                plot_container
            ]

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error displaying plot: {e}",
                    "error",
                    section="plotting",
                    permanent=True,
                )
