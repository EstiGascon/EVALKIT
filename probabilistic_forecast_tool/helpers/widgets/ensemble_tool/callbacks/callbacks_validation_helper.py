from pathlib import Path

from helpers.parameter_config_manager import ParameterConfigManager


class ValidationHelperCallbacks:
    """Handles configuration validation and checking operations."""

    def __init__(self, parent):
        """Initialize validation helper callbacks.

        Args:
            parent: Parent EnsembleCallbacks instance

        """
        self.parent = parent
        self.config_manager = ParameterConfigManager()

    def validate_configuration(self, config):
        """Validate configuration for completeness.

        Args:
            config: Configuration dictionary

        Returns:
            list: List of validation error messages (empty if valid)

        """
        errors = []

        errors.extend(self._validate_basic_config(config))

        data_source = config.get("data_source")

        if data_source == "mars":
            errors.extend(self._validate_mars_config(config))
        elif data_source == "local":
            errors.extend(self._validate_local_config(config))

        return errors

    def _validate_basic_config(self, config):
        """Validate basic configuration fields.

        Args:
            config: Configuration dictionary

        Returns:
            list: Validation errors

        """
        errors = []

        if not config.get("plot_type"):
            errors.append("Plot type not selected")

        if not config.get("data_source"):
            errors.append("Data source not selected")

        return errors

    def _validate_mars_config(self, config):
        """Validate MARS data source configuration.

        Args:
            config: Configuration dictionary

        Returns:
            list: Validation errors

        """
        errors = []
        params = config.get("parameters", {})
        plot_type = config.get("plot_type")

        errors.extend(self._validate_mars_dates(params, plot_type))

        errors.extend(self._validate_mars_parameters(params))

        errors.extend(self._validate_mars_area(params))

        errors.extend(self._validate_mars_model_class(params))

        return errors

    def _validate_mars_dates(self, params, plot_type):
        """Validate date requirements for MARS retrieval.

        Args:
            params: Parameters dictionary
            plot_type: Type of plot

        Returns:
            list: Validation errors

        """
        errors = []

        if plot_type == "cdf":
            if not params.get("analysis_date"):
                errors.append("Analysis date is required for CDF plots")
        elif not params.get("forecast_date"):
            errors.append("Forecast date or date range is required")

        return errors

    def _validate_mars_parameters(self, params):
        """Validate parameter selection for MARS retrieval.

        Args:
            params: Parameters dictionary

        Returns:
            list: Validation errors

        """
        errors = []

        if not params.get("parameters"):
            errors.append("At least one parameter must be selected")

        return errors

    def _validate_mars_area(self, params):
        """Validate geographic area for MARS retrieval.

        Args:
            params: Parameters dictionary

        Returns:
            list: Validation errors

        """
        errors = []

        if "area" not in params:
            return errors

        area = params["area"]

        if len(area) != 4:
            errors.append("Area must have 4 coordinates")
            return errors

        north, west, south, east = area

        if north <= south:
            errors.append("North boundary must be greater than south")

        return errors

    def _validate_mars_model_class(self, params):
        """Validate model class selection for MARS retrieval.

        Args:
            params: Parameters dictionary

        Returns:
            list: Validation errors

        """
        errors = []

        if not params.get("model_class"):
            errors.append("Model class must be selected")

        return errors

    def _validate_local_config(self, config):
        """Validate local file data source configuration.

        Args:
            config: Configuration dictionary

        Returns:
            list: Validation errors

        """
        errors = []
        plot_type = config.get("plot_type")

        if plot_type == "cdf":
            errors.extend(self._validate_local_cdf_files())
        else:
            errors.extend(self._validate_local_standard_files(config))

        return errors

    def _validate_local_cdf_files(self):
        """Validate local files for CDF analysis.

        Returns:
            list: Validation errors

        """
        errors = []

        if not self.parent.selected_files.get("cd"):
            errors.append("Climate data file is required for CDF analysis")

        if not self.parent.selected_files.get("scenarios"):
            errors.append("At least one scenario file is required for CDF analysis")

        return errors

    def _validate_local_standard_files(self, config):
        """Validate local files for standard plots (non-CDF).

        Args:
            config: Configuration dictionary

        Returns:
            list: Validation errors

        """
        errors = []
        plot_type = config.get("plot_type")

        required_files = self._get_required_files_for_plot_type(plot_type)
        selected_files = [
            f for f in required_files if self.parent.selected_files.get(f)
        ]

        if not selected_files:
            errors.append(
                f"At least one of these files is required: {', '.join(required_files)}"
            )

        if plot_type == "meteogram":
            errors.extend(self._validate_meteogram_control_forecast(config))

        return errors

    def _validate_meteogram_control_forecast(self, config):
        """Validate control forecast file for meteogram.

        Args:
            config: Configuration dictionary

        Returns:
            list: Validation errors

        """
        errors = []
        params = config.get("parameters", {})

        if params.get("include_cf") and not self.parent.selected_files.get("cf"):
            errors.append(
                "Control forecast file is required when 'Include Control Forecast' is checked"
            )

        return errors

    def validate_bbox(self, bbox):
        """Validate bounding box coordinates.

        Args:
            bbox: Bounding box dictionary

        Returns:
            bool: True if valid

        """
        try:
            north = float(bbox["north"])
            south = float(bbox["south"])
            east = float(bbox["east"])
            west = float(bbox["west"])

            if not (-90 <= north <= 90) or not (-90 <= south <= 90):
                return False

            if not (-180 <= east <= 180) or not (-180 <= west <= 180):
                return False

            if north <= south:
                return False

            return True

        except (ValueError, TypeError):
            return False

    def get_mars_request_preview_text(self, config):
        """Get MARS request preview as text lines.

        Args:
            config: Configuration dictionary

        Returns:
            list: Preview text lines

        """
        try:
            preview_lines = self._create_preview_header()

            params = config["parameters"]
            plot_type = config["plot_type"]

            preview_lines.extend(self._add_basic_info(params, plot_type))

            preview_lines.extend(self._add_parameter_info(params))

            if plot_type != "cdf":
                preview_lines.extend(self._add_step_info(params, plot_type))

            preview_lines.extend(self._add_area_info(params))

            preview_lines.extend(self._add_grid_info(params))

            preview_lines.extend(self._add_plot_specific_info(params, plot_type))

            preview_lines.append("=" * 50)
            return preview_lines

        except Exception as e:
            return [f"Error generating preview: {e}"]

    def _create_preview_header(self):
        """Create preview header.

        Returns:
            list: Header lines

        """
        return [
            "MARS Request Preview:",
            "=" * 50,
        ]

    def _add_basic_info(self, params, plot_type):
        """Add basic configuration information.

        Args:
            params: Parameter dictionary
            plot_type: Type of plot

        Returns:
            list: Information lines

        """
        lines = []

        lines.append(f"Model Class: {params.get('model_class', 'ifs')}")

        date_field = self._get_date_field_name(plot_type)
        lines.append(f"Date: {params.get(date_field, 'Not set')}")

        lines.append(f"Time: {params.get('time', '00:00:00')}")

        return lines

    def _get_date_field_name(self, plot_type):
        """Get the appropriate date field name for plot type.

        Args:
            plot_type: Type of plot

        Returns:
            str: Date field name

        """
        if plot_type in ["stamps", "meteogram", "plumes"]:
            return "forecast_date"
        elif plot_type == "cdf":
            return "analysis_date"
        return "date"

    def _add_parameter_info(self, params):
        """Add parameter information with ID mappings.

        Args:
            params: Parameter dictionary

        Returns:
            list: Parameter information lines

        """
        lines = []
        selected_params = params.get("parameters", [])

        lines.append(f"Parameters ({len(selected_params)} selected):")

        for param in selected_params:
            param_line = self._format_parameter_line(param)
            lines.append(param_line)

        return lines

    def _format_parameter_line(self, param):
        """Format a single parameter line with ID mapping.

        Args:
            param: Parameter name

        Returns:
            str: Formatted parameter line

        """
        if param in self.parent.param_ids:
            param_id = self.parent.param_ids[param]
            return f"  • {param} → {param_id}"
        else:
            return f"  • {param} (no ID mapping - will use original name)"

    def _add_step_info(self, params, plot_type):
        """Add forecast step information.

        Args:
            params: Parameter dictionary
            plot_type: Type of plot

        Returns:
            list: Step information lines

        """
        lines = []
        selected_steps = params.get("selected_steps")

        if selected_steps:
            lines.extend(self._format_specific_steps(selected_steps))
        else:
            lines.extend(self._format_step_range(params, plot_type))

        return lines

    def _format_specific_steps(self, selected_steps):
        """Format specific selected steps.

        Args:
            selected_steps: List of selected steps

        Returns:
            list: Formatted lines

        """
        return [
            f"Steps: {len(selected_steps)} specific steps selected",
            f"  → {selected_steps}",
        ]

    def _format_step_range(self, params, plot_type):
        """Format step range information.

        Args:
            params: Parameter dictionary
            plot_type: Type of plot

        Returns:
            list: Formatted lines

        """
        lines = []
        step_range = params.get("steps", "0-240")

        lines.append(
            f"Steps: Range '{step_range}' (will be converted to available steps)"
        )

        if self._is_step_range(step_range):
            example_line = self._generate_example_steps(step_range, plot_type)
            if example_line:
                lines.append(example_line)

        return lines

    def _generate_example_steps(self, step_range, plot_type):
        """Generate example steps for a step range.

        Args:
            step_range: Step range string (e.g., "0-240")
            plot_type: Type of plot

        Returns:
            str or None: Example steps line or None if error

        """
        try:
            start, end = map(int, step_range.split("-"))

            if plot_type == "meteogram":
                example_steps = self._calculate_meteogram_steps(start, end)
            else:
                example_steps = list(range(start, end + 1, 6))

            step_preview = example_steps[:10]
            suffix = "..." if len(example_steps) > 10 else ""

            return f"  → Example: {step_preview}{suffix} ({len(example_steps)} total)"

        except Exception:
            return "  → Could not parse step range"

    def _calculate_meteogram_steps(self, start, end):
        """Calculate meteogram steps with variable intervals from config.

        Args:
            start: Start step
            end: End step

        Returns:
            list: Calculated steps

        """
        steps = []

        model_class = getattr(self.parent, "current_model_class", "ifs")

        intervals = self.config_manager.get_step_intervals(model_class)

        if intervals:
            for interval_start, interval_end, step_interval in intervals:
                current_start = max(interval_start, start)
                current_end = min(interval_end, end)

                if current_start <= current_end:
                    steps.extend(range(current_start, current_end + 1, step_interval))
        else:
            steps = list(range(start, end + 1, 6))

        return sorted(set(steps))

    def _get_step_config_for_meteogram(self):
        """Get step configuration for meteogram plots.

        Returns:
            dict: Step configuration

        """
        if hasattr(self.parent, "model_configs"):
            model_class = getattr(self.parent, "current_model_class", "ifs")
            return self.parent.model_configs.get(model_class, {}).get("step_config", {})

        return {
            "type": "intervals",
            "intervals": [[0, 90, 1], [90, 144, 3], [144, 360, 6]],
        }

    def _add_area_info(self, params):
        """Add geographic area information.

        Args:
            params: Parameter dictionary

        Returns:
            list: Area information lines

        """
        lines = []
        area = params.get("area")

        if area:
            north, west, south, east = area
            lines.append("Geographic Area:")
            lines.append(f"  → North: {north}°, South: {south}°")
            lines.append(f"  → West: {west}°, East: {east}°")

        return lines

    def _add_grid_info(self, params):
        """Add grid resolution information.

        Args:
            params: Parameter dictionary

        Returns:
            list: Grid information lines

        """
        grid_res = params.get("grid_resolution", None)
        return [f"Grid Resolution: {grid_res}° x {grid_res}°"]

    def _add_plot_specific_info(self, params, plot_type):
        """Add plot-type-specific information.

        Args:
            params: Parameter dictionary
            plot_type: Type of plot

        Returns:
            list: Plot-specific information lines

        """
        if plot_type == "meteogram":
            return self._add_meteogram_info(params)
        elif plot_type == "cdf":
            return self._add_cdf_info(params)

        return []

    def _add_meteogram_info(self, params):
        """Add meteogram-specific information.

        Args:
            params: Parameter dictionary

        Returns:
            list: Meteogram information lines

        """
        include_cf = params.get("include_cf", True)
        return [f"Include Control Forecast: {include_cf}"]

    def _add_cdf_info(self, params):
        """Add CDF-specific information.

        Args:
            params: Parameter dictionary

        Returns:
            list: CDF information lines

        """
        lines = []

        days_back = params.get("days_back", 3)
        forecast_times = params.get("forecast_times", [0, 12])

        lines.append(f"Days Back: {days_back}")
        lines.append(f"Forecast Times: {forecast_times}")

        lines.append("Scenarios that will be requested:")
        lines.extend(self._generate_cdf_scenarios(days_back, forecast_times))

        return lines

    def _generate_cdf_scenarios(self, days_back, forecast_times):
        """Generate CDF scenario information.

        Args:
            days_back: Number of days to look back
            forecast_times: Forecast times to use

        Returns:
            list: Scenario information lines

        """
        lines = []

        times_list = [0, 12] if forecast_times == "both" else forecast_times

        for days_ago in range(days_back + 1):
            for forecast_time in times_list:
                if isinstance(forecast_time, list):
                    continue

                lead_start = days_ago * 24 if forecast_time == 0 else days_ago * 24 - 12

                if lead_start >= 0:
                    scenario_key = f"D-{days_ago}_{forecast_time:02d}Z"
                    lead_end = lead_start + 24
                    lines.append(
                        f"  • {scenario_key}: Lead time {lead_start}-{lead_end}h"
                    )

        return lines

    def get_file_summary_text(self):
        """Get file summary as text lines.

        Returns:
            list: File summary text lines

        """
        try:
            summary_lines = []
            summary_lines.append("Selected Files Summary:")

            has_files = False
            for file_type, file_path in self.parent.selected_files.items():
                if file_type == "scenarios":
                    if file_path:
                        has_files = True
                        summary_lines.append(
                            f"  Scenario files: {len(file_path)} selected"
                        )
                        for scenario, path in file_path.items():
                            summary_lines.append(f"    - {scenario}: {Path(path).name}")
                elif file_path:
                    has_files = True
                    summary_lines.append(f"  {file_type}: {Path(file_path).name}")

            if not has_files:
                summary_lines.append("  No files selected")

            return summary_lines

        except Exception as e:
            return [f"Error generating file summary: {e}"]

    def _get_required_files_for_plot_type(self, plot_type):
        """Get required files for a specific plot type from config.

        Args:
            plot_type: Plot type name

        Returns:
            list: List of required file types

        """
        required = self.config_manager.get_required_files_for_plot_type(plot_type)
        optional = self.config_manager.get_optional_files_for_plot_type(plot_type)

        return required if required else optional

    def _is_step_range(self, steps_str):
        """Check if the input is a range format like '0-240'.

        Args:
            steps_str: Steps string

        Returns:
            bool: True if range format

        """
        return (
            isinstance(steps_str, str)
            and "-" in steps_str
            and len(steps_str.split("-")) == 2
        )
