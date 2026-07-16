import os
import platform
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import earthkit as ek  # type: ignore


class DataManagementCallbacks:
    """Handles data retrieval and file management operations."""

    def __init__(self, parent):
        """Initialize data management callbacks.

        Args:
            parent: Parent EnsembleCallbacks instance

        """
        self.parent = parent

    def _parse_steps_from_params(self, params):
        """Parse step parameters from config into steps_to_use, start_step, end_step."""
        selected_steps = params.get("selected_steps")
        if selected_steps and len(selected_steps) > 0:
            return selected_steps, min(selected_steps), max(selected_steps)

        step_range = params.get("steps", "0-240")
        if "-" in step_range:
            start, end = map(int, step_range.split("-"))
            return None, start, end
        else:
            return [int(x.strip()) for x in step_range.split(",")], 0, 240

    def _resolve_steps_for_model(self, params, model_class):
        """Resolve step list for a specific model, respecting user's max frequency.

        The user-specified step frequency is treated as a MAXIMUM resolution.
        Each model gets its own available steps filtered so that the step
        interval is never finer than what the user requested.  If a model's
        native resolution is coarser, the coarser interval is kept.
        """
        steps_to_use, start_step, end_step = self._parse_steps_from_params(params)

        # Use the explicit step_frequency from the UI (always reliable)
        max_freq = params.get("step_frequency", 1)

        # Deterministic-only models have no probabilistic section in config.
        # For those, resolve steps from the deterministic fc instead.
        _model_cfg = self.parent.data_retriever.model_configs.get(model_class, {})
        if "probabilistic" not in _model_cfg and "deterministic" in _model_cfg:
            model_steps = self.parent.data_retriever.get_available_steps(
                model_class, "deterministic", "fc", start_step, end_step
            )
        else:
            model_steps = self.parent.data_retriever.get_available_steps(
                model_class, "probabilistic", "pf", start_step, end_step
            )
        if not model_steps:
            return params

        if max_freq and max_freq > 1:
            # Keep only steps that are multiples of the user's max frequency
            model_steps = [s for s in model_steps if s % max_freq == 0]

        # If user had explicit steps, intersect with model availability
        if steps_to_use is not None:
            user_set = set(steps_to_use)
            model_steps = [s for s in model_steps if s in user_set]

        if model_steps:
            model_params = dict(params)
            model_params["selected_steps"] = sorted(model_steps)
            return model_params
        return params

    def _retrieve_single_model_meteogram_plumes(self, params, model_class, grid):
        """Retrieve meteogram/plumes data for a single model."""
        steps_to_use, start_step, end_step = self._parse_steps_from_params(params)

        custom_class = None
        custom_expver = None
        include_cf = True
        if model_class == "custom":
            custom_class = params.get("custom_class") or None
            custom_expver = params.get("custom_expver") or None
            include_cf = params.get("custom_include_cf", True)

        return self.parent.data_retriever.retrieve_plumes_meteograms_data(
            model_class=model_class,
            forecast_date=params.get("forecast_date"),
            forecast_time=params.get("time", "00:00:00"),
            selected_steps=steps_to_use,
            start_step=start_step,
            end_step=end_step,
            parameters=params.get("parameters", ["z"]),
            area=params.get("area"),
            grid=grid,
            ensemble_members=self._parse_ensemble_members(
                params.get("ensemble_members")
            ),
            calculate_windspeed=True,
            calculate_6h_precipitation=True,
            custom_class=custom_class,
            custom_expver=custom_expver,
            include_cf=include_cf,
        )

    def retrieve_meteogram_data(self, config):  # noqa: PLR0912
        """Retrieve meteogram data based on configuration.

        Args:
            config: Configuration dictionary

        """
        try:
            params = config["parameters"]

            grid_param = params.get("grid")
            if grid_param and grid_param[0] is not None:
                grid = grid_param
            else:
                grid = None

            if config["data_source"] == "mars":
                selected_models = params.get("selected_models", [params.get("model_class", "ifs")])

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Retrieving Data ...", "info", section="data", permanent=True
                    )

                if len(selected_models) > 1:
                    # Resolve steps per model: user's frequency is treated as
                    # the maximum resolution; each model uses its own native
                    # steps filtered to that ceiling.
                    multi_data = {}
                    for model in selected_models:
                        if self.parent.ui:
                            self.parent.ui.show_alert_message(
                                f"Retrieving {model.upper()} data ...",
                                "info", section="data", permanent=True,
                            )
                        model_params = self._resolve_steps_for_model(params, model)
                        multi_data[model] = self._retrieve_single_model_meteogram_plumes(
                            model_params, model, grid
                        )
                    data = {"_multi_model": True, "models": multi_data}
                else:
                    single_params = self._resolve_steps_for_model(
                        params, selected_models[0]
                    )
                    data = self._retrieve_single_model_meteogram_plumes(
                        single_params, selected_models[0], grid
                    )

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Meteogram Data retrieved successfully!",
                        "success",
                        section="data",
                        permanent=True,
                    )
                    self._show_data_summary_alert(data)

            else:
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Loading Meteogram local Data ...",
                        "info",
                        section="data",
                        permanent=True,
                    )

                data = self._load_meteogram_local_files()

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Meteogram Data loaded successfully!",
                        "success",
                        section="data",
                        permanent=True,
                    )
                    self._show_data_summary_alert(data)

            # Preserve previously loaded observations before overwriting
            prev_obs = None
            if hasattr(self.parent, "current_data") and isinstance(self.parent.current_data, dict):
                prev_obs = self.parent.current_data.get("observations")
            self.parent.current_data = data
            if prev_obs is not None:
                self.parent.current_data["observations"] = prev_obs
            self.parent._on_data_retrieval_complete(config)

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error retrieving meteogram data: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )

    def retrieve_stamps_data(self, config):  # noqa: PLR0912
        """Retrieve stamps data based on configuration.

        Args:
            config: Configuration dictionary

        """
        try:
            params = config["parameters"]

            grid_param = params.get("grid")
            if grid_param and grid_param[0] is not None:
                grid = grid_param
            else:
                grid = None

            if config["data_source"] == "mars":
                model_class = params.get("model_class", "ifs")
                resolved_params = self._resolve_steps_for_model(params, model_class)
                steps_to_use, start_step, end_step = self._parse_steps_from_params(
                    resolved_params
                )

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Retrieving Stamps Data ...",
                        "info",
                        section="data",
                        permanent=True,
                    )

                data = self.parent.data_retriever.retrieve_stamp_data(
                    model_class=model_class,
                    forecast_date=params.get("forecast_date"),
                    forecast_time=params.get("time", "00:00:00"),
                    selected_steps=steps_to_use,
                    start_step=start_step,
                    end_step=end_step,
                    parameters=params.get("parameters", ["2t"]),
                    area=params.get("area"),
                    grid=grid,
                    ensemble_members=self._parse_ensemble_members(
                        params.get("ensemble_members")
                    ),
                    calculate_windspeed=True,
                    # Keep cumulative precipitation so stamps can compute any
                    # accumulation period (3h, 6h, 12h, 24h...) at plot time.
                    calculate_6h_precipitation=False,
                    custom_class=params.get("custom_class") or None,
                    custom_expver=params.get("custom_expver") or None,
                    include_cf=params.get("custom_include_cf", True),
                )

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Stamps Data retrieved successfully!",
                        "success",
                        section="data",
                        permanent=True,
                    )
                    self._show_data_summary_alert(data)
            else:
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Loading Stamps local Data ...",
                        "info",
                        section="data",
                        permanent=True,
                    )

                data = self._load_stamps_local_files()

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Stamps Data loaded successfully!",
                        "success",
                        section="data",
                        permanent=True,
                    )
                    self._show_data_summary_alert(data)

            # Preserve previously loaded observations before overwriting
            prev_obs = None
            if hasattr(self.parent, "current_data") and isinstance(self.parent.current_data, dict):
                prev_obs = self.parent.current_data.get("observations")
            self.parent.current_data = data
            if prev_obs is not None:
                self.parent.current_data["observations"] = prev_obs

            self.parent._on_data_retrieval_complete(config)

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error retrieving stamps data: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )

    def retrieve_plumes_data(self, config):
        """Retrieve plumes (time series ensemble) data based on configuration.

        Args:
            config: Configuration dictionary

        """
        try:
            params = config["parameters"]

            grid_param = params.get("grid")
            if grid_param and grid_param[0] is not None:
                grid = grid_param
            else:
                grid = None

            if config["data_source"] == "mars":
                selected_models = params.get("selected_models", [params.get("model_class", "ifs")])

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Retrieving Plumes Data ...",
                        "info",
                        section="data",
                        permanent=True,
                    )

                if len(selected_models) > 1:
                    multi_data = {}
                    for model in selected_models:
                        if self.parent.ui:
                            self.parent.ui.show_alert_message(
                                f"Retrieving {model.upper()} plumes data ...",
                                "info", section="data", permanent=True,
                            )
                        model_params = self._resolve_steps_for_model(params, model)
                        multi_data[model] = self._retrieve_single_model_meteogram_plumes(
                            model_params, model, grid
                        )
                    data = {"_multi_model": True, "models": multi_data}
                else:
                    single_params = self._resolve_steps_for_model(
                        params, selected_models[0]
                    )
                    data = self._retrieve_single_model_meteogram_plumes(
                        single_params, selected_models[0], grid
                    )

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Plumes Data Retrieved",
                        "success",
                        section="data",
                        permanent=True,
                    )
                    self._show_data_summary_alert(data)

            else:
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Plumes Data loading ...",
                        "info",
                        section="data",
                        permanent=True,
                    )

                data = self._load_plumes_local_files()

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Plumes data loaded successfully!",
                        "success",
                        section="data",
                        permanent=True,
                    )
                    self._show_data_summary_alert(data)

            # Preserve previously loaded observations before overwriting
            prev_obs = None
            if hasattr(self.parent, "current_data") and isinstance(self.parent.current_data, dict):
                prev_obs = self.parent.current_data.get("observations")
            self.parent.current_data = data
            if prev_obs is not None:
                self.parent.current_data["observations"] = prev_obs
            self.parent._on_data_retrieval_complete(config)

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error retrieving plumes data: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )

    def retrieve_cdf_data(self, config):
        """Retrieve CDF data based on configuration.

        Args:
            config: Configuration dictionary

        """
        try:
            params = config["parameters"]

            grid_param = params.get("grid")
            if grid_param and grid_param[0] is not None:
                grid = grid_param
            else:
                grid = None

            if config["data_source"] == "mars":
                forecast_times = params.get("forecast_times", [0, 12])
                if forecast_times == "both":
                    forecast_times = [0, 12]
                elif not isinstance(forecast_times, list):
                    forecast_times = [forecast_times]

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Retrieving CDF Data ...",
                        "info",
                        section="data",
                        permanent=True,
                    )

                days_back_val = params.get("days_back")
                if not isinstance(days_back_val, int) or days_back_val < 1:
                    days_back_val = 3

                data = self.parent.data_retriever.retrieve_cdf_data(
                    analysis_date=params.get("analysis_date"),
                    days_back=days_back_val,
                    selected_forecast_times=forecast_times,
                    parameters=params.get("parameters", ["2t"]),
                    area=params.get("area"),
                    grid=grid,
                    model_class=params.get("model_class", "ifs"),
                    calculate_windspeed=True,
                    custom_class=params.get("custom_class") or None,
                    custom_expver=params.get("custom_expver") or None,
                )

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "CDF data retrieved successfully!",
                        "success",
                        section="data",
                        permanent=True,
                    )
                    self._show_data_summary_alert(data)

            else:
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Loading CDF Data ...", "info", section="data", permanent=True
                    )
                data = self._load_cdf_local_files()

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "CDF data loaded successfully!",
                        "success",
                        section="data",
                        permanent=True,
                    )
                    self._show_data_summary_alert(data)

            self.parent.current_data = data
            self.parent._on_data_retrieval_complete(config)

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error retrieving CDF data: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )

    def _load_meteogram_local_files(self):
        """Load meteogram data from local files."""
        file_mapping = {}

        if self.parent.selected_files.get("pf"):
            file_mapping["pf"] = self.parent.selected_files["pf"]
        if self.parent.selected_files.get("cf"):
            file_mapping["cf"] = self.parent.selected_files["cf"]

        return self.parent.data_retriever.read_local_grib_data(file_mapping)

    def _load_stamps_local_files(self):
        """Load stamps data from local files."""
        file_mapping = {}

        if self.parent.selected_files.get("fc"):
            file_mapping["fc"] = self.parent.selected_files["fc"]
        if self.parent.selected_files.get("cf"):
            file_mapping["cf"] = self.parent.selected_files["cf"]
        if self.parent.selected_files.get("pf"):
            file_mapping["pf"] = self.parent.selected_files["pf"]

        return self.parent.data_retriever.read_local_grib_data(file_mapping)

    def _load_plumes_local_files(self):
        """Load plumes data from local files."""
        file_mapping = {}

        if self.parent.selected_files.get("cf"):
            file_mapping["cf"] = self.parent.selected_files["cf"]
        if self.parent.selected_files.get("pf"):
            file_mapping["pf"] = self.parent.selected_files["pf"]

        return self.parent.data_retriever.read_local_grib_data(file_mapping)

    def _load_cdf_local_files(self):
        """Load CDF data from local files with enhanced scenario handling."""
        file_mapping = {}

        if self.parent.selected_files.get("cd"):
            file_mapping["cd"] = self.parent.selected_files["cd"]

        scenario_mapping = self.parent.get_cdf_scenario_mapping()

        if scenario_mapping:
            scenario_files = {}
            scenario_metadata = {}

            for standard_key, scenario_info in scenario_mapping.items():
                scenario_files[standard_key] = scenario_info["file_path"]
                scenario_metadata[standard_key] = {
                    "days_back": scenario_info["days_back"],
                    "forecast_time": scenario_info["forecast_time"],
                    "original_name": scenario_info["original_name"],
                    "description": scenario_info["description"],
                }

            file_mapping["forecast_data"] = {
                "scenarios": scenario_files,
                "scenario_metadata": scenario_metadata,
            }

        return self.parent.data_retriever.read_local_grib_data(file_mapping)

    def _parse_ensemble_members(self, members_str):
        """Parse ensemble members string into list of integers.

        Args:
            members_str: String representation of ensemble members

        Returns:
            list: List of ensemble member integers, or None

        """
        if not members_str:
            return None

        try:
            if "-" in members_str:
                start, end = map(int, members_str.split("-"))
                return list(range(start, end + 1))
            elif "," in members_str:
                return [int(x.strip()) for x in members_str.split(",")]
            else:
                return [int(members_str)]
        except ValueError:
            return None

    def _show_data_summary_alert(self, data):
        """Show summary of retrieved data as alert.

        Args:
            data: Retrieved data dictionary

        """
        try:
            summary_parts = []

            for key, dataset_info in data.items():
                if key in ("bbox_info", "metadata"):
                    continue
                elif isinstance(dataset_info, dict) and "dataset" in dataset_info:
                    dataset = dataset_info["dataset"]
                    summary_parts.append(f"{key}: {len(dataset)} fields")
                elif isinstance(dataset_info, dict):
                    if "scenarios" in dataset_info:
                        scenarios = dataset_info["scenarios"]
                        summary_parts.append(f"{key}: {len(scenarios)} scenarios")
                        for scenario_name, scenario_data in scenarios.items():
                            if (
                                isinstance(scenario_data, dict)
                                and "dataset" in scenario_data
                            ):
                                summary_parts.append(
                                    f"  - {scenario_name}: {len(scenario_data['dataset'])} fields"
                                )
                    else:
                        summary_parts.append(f"{key}: {type(dataset_info).__name__}")
                else:
                    summary_parts.append(f"{key}: {type(dataset_info).__name__}")

            if summary_parts and self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"📊 {' | '.join(summary_parts)}",
                    "info",
                    section="data",
                    permanent=True,
                )

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error showing data summary: {e}",
                    "warning",
                    section="data",
                    permanent=True,
                )

    def browse_file(self, file_type):
        """Browse and select a file with validation.

        Args:
            file_type: Type of file to browse for

        """
        try:
            root = tk.Tk()
            root.withdraw()

            if platform.system() == "Windows":
                root.wm_attributes("-topmost", 1)
                root.lift()
                root.focus_force()
            else:
                root.lift()
                root.attributes("-topmost", True)

            file_descriptions = {
                "fc": "Deterministic Forecast",
                "cf": "Control Forecast",
                "pf": "Ensemble Forecast",
                "cd": "Climate Data",
            }

            title = f"Select {file_descriptions.get(file_type, file_type)} File"

            file_path = filedialog.askopenfilename(
                title=title,
                filetypes=[
                    ("GRIB files", "*.grib *.grb *.grib2"),
                    ("NetCDF files", "*.nc *.netcdf"),
                    ("All files", "*.*"),
                ],
                initialdir=os.path.expanduser("~"),
            )

            root.destroy()

            if file_path and os.path.exists(file_path):
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "Validating file...",
                        "info",
                        section="data",
                    )

                if self.validate_grib_file(file_path):
                    self.parent.selected_files[file_type] = file_path
                    self._update_file_display(file_type, file_path)
                    self.detect_file_parameters(file_path, file_type)

                    if self.parent.ui and self.parent.ui.current_data_source == "local":
                        if not any(
                            self.parent.selected_files[ft]
                            for ft in ["fc", "cf", "pf", "cd"]
                            if ft != file_type
                        ):
                            self.update_bbox_from_grib_file(file_path)

                    if self.parent.ui:
                        self.parent.ui.show_alert_message(
                            f"{file_type.upper()} file loaded successfully",
                            "success",
                            section="data",
                        )
                elif self.parent.ui:
                    self.parent.ui.show_alert_message(
                        f"Invalid GRIB file: {Path(file_path).name}",
                        "error",
                        section="data",
                        permanent=True,
                    )

        except Exception as e:
            if self.parent.ui:
                err = str(e)
                if "DISPLAY" in err or "display" in err or "Tcl" in err:
                    file_descriptions = {
                        "fc": "Deterministic Forecast",
                        "cf": "Control Forecast",
                        "pf": "Ensemble Forecast",
                        "cd": "Climate Data",
                    }
                    label = file_descriptions.get(file_type, file_type.upper())
                    self.parent.ui.show_alert_message(
                        f"File browser unavailable (no graphical display in this environment). "
                        f"Please type the full path to your {label} file directly into the "
                        f"'{label} File Path' text box above and press Enter.",
                        "warning",
                        section="data",
                        permanent=True,
                    )
                else:
                    self.parent.ui.show_alert_message(
                        f"Error selecting {file_type} file: {e}",
                        "error",
                        section="data",
                        permanent=True,
                    )

    def validate_grib_file(self, file_path):
        """Validate that the file is a proper GRIB file.

        Args:
            file_path: Path to file to validate

        Returns:
            bool: True if valid GRIB file

        """
        try:
            if file_path in self.parent.file_validation_cache:
                return self.parent.file_validation_cache[file_path]

            ds = ek.data.from_source("file", file_path)
            is_valid = len(ds) > 0

            self.parent.file_validation_cache[file_path] = is_valid
            return is_valid

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"File validation error: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )
            self.parent.file_validation_cache[file_path] = False
            return False

    def detect_file_parameters(self, file_path, file_type):
        """Detect available parameters in the GRIB file.

        Args:
            file_path: Path to GRIB file
            file_type: Type of file

        """
        try:
            ds = ek.data.from_source("file", file_path)

            parameters = set()
            for field in ds:
                try:
                    param = field.metadata("shortName")
                    if param:
                        parameters.add(param)
                except Exception:
                    continue

            if parameters:
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        f"Detected parameters in {file_type}: {', '.join(sorted(parameters))}",
                        "info",
                        section="data",
                    )

                self._update_parameter_options(parameters)

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Parameter detection error: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )

    def update_bbox_from_grib_file(self, file_path):
        """Extract and update bounding box from GRIB file.

        Args:
            file_path: Path to GRIB file

        Returns:
            bool: True if bbox updated successfully

        """
        try:
            ds = ek.data.from_source("file", file_path)

            if len(ds) > 0:
                first_field = ds[0]

                try:
                    lat_first = first_field.metadata(
                        "latitudeOfFirstGridPointInDegrees", default=None
                    )
                    lon_first = first_field.metadata(
                        "longitudeOfFirstGridPointInDegrees", default=None
                    )
                    lat_last = first_field.metadata(
                        "latitudeOfLastGridPointInDegrees", default=None
                    )
                    lon_last = first_field.metadata(
                        "longitudeOfLastGridPointInDegrees", default=None
                    )

                    if all(
                        coord is not None
                        for coord in [lat_first, lon_first, lat_last, lon_last]
                    ):
                        north = max(lat_first, lat_last)
                        south = min(lat_first, lat_last)
                        east = max(lon_first, lon_last)
                        west = min(lon_first, lon_last)

                        if self.parent.ui:
                            self.parent.ui.widgets["north"].value = round(north, 4)
                            self.parent.ui.widgets["south"].value = round(south, 4)
                            self.parent.ui.widgets["east"].value = round(east, 4)
                            self.parent.ui.widgets["west"].value = round(west, 4)

                            if self.parent.map_handler:
                                bbox = {
                                    "north": north,
                                    "south": south,
                                    "east": east,
                                    "west": west,
                                }
                                self.parent.map_handler.set_current_bbox_and_update_ui(
                                    bbox_dict=bbox
                                )

                            self.parent.ui.show_alert_message(
                                f"Bbox auto-detected from GRIB file: North: {north:.4f}°, "
                                f"South: {south:.4f}°, West: {west:.4f}°, East: {east:.4f}°",
                                "success",
                                section="data",
                                permanent=True,
                            )

                            return True
                    else:
                        if self.parent.ui:
                            self.parent.ui.show_alert_message(
                                "Could not extract complete bbox information from GRIB file",
                                "warning",
                                section="data",
                                permanent=True,
                            )
                        return False

                except Exception as e:
                    if self.parent.ui:
                        self.parent.ui.show_alert_message(
                            f"Error extracting bbox from GRIB file: {e}",
                            "error",
                            section="data",
                            permanent=True,
                        )
                    return False
            else:
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "GRIB file appears to be empty",
                        "warning",
                        section="data",
                        permanent=True,
                    )
                return False

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error reading GRIB file for bbox detection: {e}",
                    "error",
                    section="plotting",
                    permanent=True,
                )
            return False

    def reset_local_file_selections(self):
        """Reset all local file selections when changing plot types."""
        try:
            self.parent.selected_files = {
                "fc": None,
                "cf": None,
                "pf": None,
                "cd": None,
                "scenarios": {},
            }
            if self.parent.ui and "file_inputs" in self.parent.ui.widgets:
                for _file_type, file_widget in self.parent.ui.widgets[
                    "file_inputs"
                ].items():
                    if (
                        hasattr(file_widget, "children")
                        and len(file_widget.children) > 0
                    ):
                        text_field = file_widget.children[0]
                        text_field.value = ""
            if self.parent.ui and "cdf_scenario_files" in self.parent.ui.widgets:
                for scenario_item in self.parent.ui.widgets["cdf_scenario_files"]:
                    scenario_row = scenario_item["widget"]
                    if (
                        hasattr(scenario_row, "children")
                        and len(scenario_row.children) > 0
                    ):
                        text_field = scenario_row.children[0]
                        text_field.value = ""
            self.parent.file_validation_cache = {}

            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    "File selections cleared for new plot type", "info", section="data"
                )

        except Exception as e:
            print(f"Error resetting file selections: {e}")

    def _update_file_display(self, file_type, file_path):
        """Update the file display in the UI.

        Args:
            file_type: Type of file
            file_path: Path to file

        """
        if not self.parent.ui or file_type not in self.parent.ui.widgets.get(
            "file_inputs", {}
        ):
            return

        try:
            file_row = self.parent.ui.widgets["file_inputs"][file_type]
            text_field = file_row.children[0]

            filename = Path(file_path).name
            text_field.value = filename

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error updating file display: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )

    def _update_parameter_options(self, detected_params):
        """Update parameter selection options based on detected parameters.

        Args:
            detected_params: Set of detected parameter names

        """
        if not self.parent.ui or "parameters" not in self.parent.ui.widgets:
            return

        try:
            new_options = []
            for param in sorted(detected_params):
                if param in self.parent.surface_variables:
                    param_info = self.parent.surface_variables[param]
                    name = param_info.get("name", param.upper())
                    units = param_info.get("units", "")
                    if units:
                        text = f"{name} ({units})"
                    else:
                        text = name
                else:
                    text = param.upper()

                new_options.append({"text": text, "value": param})

            self.parent.ui.widgets["parameters"].items = new_options

            if new_options and self.parent.ui:
                first_param = new_options[0]["value"]
                self.parent.ui.auto_plot_parameter = first_param
                self.parent.ui._update_auto_plot_unit()

            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Updated parameter options with {len(new_options)} detected parameters",
                    "info",
                    section="data",
                    permanent=True,
                )

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error updating parameter options: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )
