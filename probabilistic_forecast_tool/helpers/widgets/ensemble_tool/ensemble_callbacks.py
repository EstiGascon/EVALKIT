"""Main callbacks orchestrator for ensemble tool."""

import json
import os
import platform
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog

from helpers.data_retrieval import BoundingBoxManager, EnsembleDataRetriever
from helpers.observations_retriever import ObservationsRetriever
from helpers.plotting.plotting_manager import PlottingManager
from helpers.widgets.map_handler import WeatherMapHandler

from .callbacks.callbacks_data_management import DataManagementCallbacks
from .callbacks.callbacks_observation_handler import ObservationHandlerCallbacks
from .callbacks.callbacks_plotting_manager import PlottingManagerCallbacks
from .callbacks.callbacks_validation_helper import ValidationHelperCallbacks


class EnsembleCallbacks:
    """Callback handler for ensemble data retrieval interface with automatic plotting."""

    def __init__(self, config_file="model_config.json"):
        """Initialize callbacks with data retrieval system.

        Args:
            config_file: Path to model configuration JSON file

        """
        self.config_file = config_file
        self.bbox_manager = BoundingBoxManager()
        self.data_retriever = EnsembleDataRetriever(
            config_file=config_file, bbox_manager=self.bbox_manager
        )

        self.plotting_manager = PlottingManager(config_file=config_file)

        self.ui = None
        self.map_handler = None

        self.current_data = {}
        self.current_config = {}

        self.selected_files = {
            "fc": None,
            "cf": None,
            "pf": None,
            "cd": None,
            "scenarios": {},
        }

        self.observations_retriever = None
        self.selected_observation_folder = None
        self.file_validation_cache = {}
        self.observation_stations_gdf = None
        self.observation_timeseries_df = None
        self.observation_folder_path = None
        self.original_observation_stations_gdf = None

        self._load_config()
        self._init_observations_retriever()
        self.data_management = DataManagementCallbacks(self)
        self.observation_handler = ObservationHandlerCallbacks(self)
        self.validation_helper = ValidationHelperCallbacks(self)
        self.plotting_callbacks = PlottingManagerCallbacks(self)

    def _load_config(self):
        """Load model configuration for parameter validation."""
        try:
            if Path(self.config_file).exists():
                with open(self.config_file) as f:
                    config_data = json.load(f)
                self.param_ids = config_data.get("parameter_mappings", {}).get(
                    "param_ids", {}
                )
                self.surface_variables = config_data.get("surface_variables", {})
                self.use_cases = config_data.get("use_cases", {})
            else:
                self.param_ids = {}
                self.surface_variables = {}
                self.use_cases = {}
        except Exception as e:
            if self.ui:
                self.ui.show_alert_message(
                    f"Error loading config for callbacks: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )
            self.param_ids = {}
            self.surface_variables = {}
            self.use_cases = {}

    def _init_observations_retriever(self):
        """Initialize observations retriever with proper VINO path."""
        try:
            if Path(self.config_file).exists():
                with open(self.config_file) as f:
                    config_data = json.load(f)
                vino_path = config_data.get("vino_path", config_data.get("stvl_path", "/home/moz/bin/vino_getgeo"))
            else:
                vino_path = "/home/moz/bin/vino_getgeo"

            self.observations_retriever = ObservationsRetriever(vino_path)

        except Exception:
            self.observations_retriever = None

    def set_ui_reference(self, ui):
        """Set reference to the UI instance.

        Args:
            ui: EnsembleUI instance

        """
        self.ui = ui
        self.plotting_manager.set_ui_reference(ui)
        self._setup_file_browse_handlers()

    def _setup_file_browse_handlers(self):
        """Set up file browsing handlers for all file input widgets."""
        if not self.ui:
            return

        file_types = ["fc", "cf", "pf", "cd"]

        for file_type in file_types:
            if file_type in self.ui.widgets.get("file_inputs", {}):
                file_row = self.ui.widgets["file_inputs"][file_type]
                if hasattr(file_row, "children") and len(file_row.children) >= 2:
                    browse_btn = file_row.children[1]

                    def make_browse_handler(ftype):
                        def on_browse_click(*_args):
                            self._browse_file(ftype)

                        return on_browse_click

                    browse_btn.on_click(make_browse_handler(file_type))

        self._setup_cdf_scenario_handlers()

    def _setup_cdf_scenario_handlers(self):
        """Set up file handlers for CDF scenario files."""
        if not self.ui:
            return

        for scenario_item in self.ui.widgets.get("cdf_scenario_files", []):
            self._setup_single_scenario_handler(scenario_item)

    def _setup_single_scenario_handler(self, scenario_item):
        """Set up handler for a single scenario file.

        Args:
            scenario_item: Scenario item dictionary

        """
        try:
            scenario_name = scenario_item["name"]
            widget_id = scenario_item["id"]
            scenario_row = scenario_item["widget"]

            if hasattr(scenario_row, "children") and len(scenario_row.children) >= 4:
                browse_btn = scenario_row.children[3]

                def make_scenario_handler(widget_id, scenario_item):
                    def on_scenario_browse_click(*_args):
                        self._browse_scenario_file(
                            scenario_name, widget_id, scenario_item
                        )

                    return on_scenario_browse_click

                browse_btn.on_click(make_scenario_handler(widget_id, scenario_item))

        except Exception as e:
            if self.ui:
                self.ui.show_alert_message(
                    f"Error setting up scenario handler for {scenario_item.get('name', 'unknown')}: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )

    def setup_map_handler(self):
        """Set up map handler for geographic area selection with auto-plotting integration."""
        if self.ui:
            self.map_handler = WeatherMapHandler(self.ui)
            self.ui.set_map_handler(self.map_handler)

            self._setup_bbox_synchronization()
            self._setup_auto_plotting_integration()

    def _setup_bbox_synchronization(self):
        """Set up bidirectional bbox synchronization between map and UI."""
        if not self.map_handler or not self.ui:
            return

        def on_bbox_widget_change(*_args):
            try:
                bbox = {
                    "north": float(self.ui.widgets["north"].value),
                    "south": float(self.ui.widgets["south"].value),
                    "east": float(self.ui.widgets["east"].value),
                    "west": float(self.ui.widgets["west"].value),
                }

                if self.validation_helper.validate_bbox(bbox):
                    self.map_handler.set_current_bbox_and_update_ui(bbox_dict=bbox)
                    self.bbox_manager.set_current_bbox(
                        (bbox["west"], bbox["south"], bbox["east"], bbox["north"])
                    )
                    if (
                        hasattr(self, "observation_stations_gdf")
                        and self.observation_stations_gdf is not None
                    ):
                        self.observation_handler.update_observation_stations_for_bbox()

            except Exception as e:
                if self.ui:
                    self.ui.show_alert_message(
                        f"Error updating bbox from UI: {e}",
                        "error",
                        section="observation",
                        permanent=True,
                    )

        for coord in ["north", "south", "east", "west"]:
            if coord in self.ui.widgets:
                self.ui.widgets[coord].observe(on_bbox_widget_change, names="value")

    def _setup_auto_plotting_integration(self):
        """Set up automatic plotting integration with map interactions."""
        if not self.map_handler or not self.ui:
            return

        if hasattr(self.map_handler, "set_data_loaded_status"):
            self.map_handler.set_data_loaded_status(False)

    def setup_map_plotting_integration(self):
        """Set up map integration for single-point auto-plotting."""
        if self.map_handler:

            def on_map_point_selected(lat, lon):
                """Handle point selection from map for single-point auto-plotting."""
                try:
                    if not self.map_handler.is_point_in_bbox(lat, lon):
                        if self.ui:
                            validation_result = (
                                self.map_handler.validate_and_warn_bbox_constraints(
                                    lat, lon
                                )
                            )
                            self.ui.show_alert_message(
                                validation_result["message"],
                                "error",
                                section="plotting",
                                permanent=True,
                            )
                        return

                    if hasattr(self.plotting_manager, "selected_points"):
                        new_points = {"P1": (lat, lon)}
                        self.plotting_manager.update_selected_points(new_points)

                        current_plot_type = getattr(self.ui, "current_plot_type", None)
                        if (
                            current_plot_type
                            and self.plotting_manager.is_point_based_plot(
                                current_plot_type
                            )
                        ):
                            self._trigger_auto_plot(current_plot_type)

                except Exception as e:
                    if self.ui:
                        self.ui.show_alert_message(
                            f"Error selecting point: {e}",
                            "error",
                            section="plotting",
                            permanent=True,
                        )

            if hasattr(self.map_handler, "set_point_selection_callback"):
                self.map_handler.set_point_selection_callback(on_map_point_selected)

    def _trigger_auto_plot(self, plot_type):
        """Trigger auto-plot for point-based plots when point is selected.

        Args:
            plot_type: Type of plot to create

        """
        try:
            if not self.plotting_manager.current_parameter:
                return

            if not self.plotting_manager.selected_points:
                return

            parameter = self.plotting_manager.current_parameter
            unit_value = getattr(self.ui, "auto_plot_unit", "default")

            if plot_type == "meteogram":
                self.create_meteogram_plot(parameter, unit_value)
            elif plot_type == "cdf":
                self.create_cdf_plot(parameter, unit_value)
            elif plot_type == "plumes":
                self.create_plumes_plot(parameter, unit_value)

        except Exception as e:
            if self.ui:
                self.ui.show_alert_message(
                    f"Error creating auto-plot: {e}",
                    "error",
                    section="plotting",
                    permanent=True,
                )

    def setup_complete_integration(self):
        """Set up complete integration between UI, callbacks, plotting manager, and map handler."""
        try:
            if self.plotting_manager and self.ui:
                self.plotting_manager.set_ui_reference(self.ui)

            if hasattr(self.ui, "set_plotting_manager"):
                self.ui.set_plotting_manager(self.plotting_manager)

            if self.map_handler:
                self.setup_map_plotting_integration()

            if self.map_handler and hasattr(
                self.map_handler, "set_point_selection_callback"
            ):
                self.map_handler.set_point_selection_callback(
                    self.ui.on_map_point_selected
                )

        except Exception:
            traceback.print_exc()

    def on_validate_click(self, config):
        """Handle validate configuration button click.

        Args:
            config: Configuration dictionary

        """
        try:
            validation_messages = []
            validation_messages.append("=== Configuration Validation ===")
            validation_messages.append(f"Plot Type: {config['plot_type']}")
            validation_messages.append(f"Data Source: {config['data_source']}")
            validation_messages.append("")

            validation_errors = self.validation_helper.validate_configuration(config)

            if validation_errors:
                validation_messages.append("Configuration Issues:")
                for error in validation_errors:
                    validation_messages.append(f"  - {error}")

                alert_content = "<br>".join(validation_messages)
                self.ui.show_alert_message(
                    alert_content, "error", section="observation"
                )

            else:
                validation_messages.append(
                    "Configuration is valid and ready for data retrieval"
                )
                validation_messages.append("")

                if config["data_source"] == "mars":
                    mars_preview = self.validation_helper.get_mars_request_preview_text(
                        config
                    )
                    validation_messages.extend(mars_preview)
                elif config["data_source"] == "local":
                    file_summary = self.validation_helper.get_file_summary_text()
                    validation_messages.extend(file_summary)

                alert_content = "<br>".join(validation_messages)
                self.ui.show_alert_message(
                    alert_content, "success", section="data", permanent=True
                )

        except Exception as e:
            self.ui.show_alert_message(
                f"Error during validation:<br>{str(e)}",
                "error",
                section="data",
                permanent=True,
            )

    def on_retrieve_click(self, config):
        """Handle retrieve data button click.

        Args:
            config: Configuration dictionary

        """
        try:
            validation_errors = self.validation_helper.validate_configuration(config)
            if validation_errors:
                if self.ui:
                    self.ui.show_alert_message(
                        "Cannot retrieve data. Configuration errors found.",
                        "error",
                        section="data",
                        permanent=True,
                    )
                return

            if (
                hasattr(self, "current_data")
                and self.current_data
                and hasattr(self, "current_config")
                and self.current_config.get("plot_type")
                and self.current_config.get("data_source")
            ):
                previous_plot_type = self.current_config.get("plot_type")
                previous_data_source = self.current_config.get("data_source")
                new_plot_type = config.get("plot_type")
                new_data_source = config.get("data_source")

                if (
                    previous_data_source == new_data_source
                    and self.are_plot_types_compatible(
                        previous_plot_type, new_plot_type
                    )
                ):
                    if self.ui:
                        self.ui.show_alert_message(
                            f"Reusing data from {previous_plot_type} for {new_plot_type}",
                            "success",
                            section="data",
                            permanent=True,
                        )

                    self.current_config = config
                    self._on_data_retrieval_complete(config)
                    return

            self.current_config = config

            if config["plot_type"] == "meteogram":
                self.data_management.retrieve_meteogram_data(config)
            elif config["plot_type"] == "stamps":
                self.data_management.retrieve_stamps_data(config)
            elif config["plot_type"] == "plumes":
                self.data_management.retrieve_plumes_data(config)
            elif config["plot_type"] == "cdf":
                self.data_management.retrieve_cdf_data(config)
            else:
                raise ValueError(f"Unknown plot type: {config['plot_type']}")

        except Exception as e:
            traceback.print_exc()
            if self.ui:
                self.ui.show_alert_message(
                    f"Error retrieving data: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )

    def on_save_click(self):
        """Handle save to file button click.

        Saves the currently loaded MARS data to GRIB files under $SCRATCH/evalkit/<plot_type>/.
        """
        import datetime

        try:
            if not self.current_data:
                if self.ui:
                    self.ui.show_alert_message(
                        "No data loaded. Please retrieve data first.",
                        "error",
                        section="data",
                        permanent=True,
                    )
                return

            plot_type = self.current_config.get("plot_type")
            if not plot_type:
                if self.ui:
                    self.ui.show_alert_message(
                        "Cannot determine plot type. Please retrieve data again.",
                        "error",
                        section="data",
                        permanent=True,
                    )
                return

            # Determine output directory based on plot type
            scratch = os.environ.get("SCRATCH", str(Path.home()))
            subdir = "meteogram" if plot_type in ("meteogram", "plumes") else plot_type
            output_dir = Path(scratch) / "evalkit" / subdir
            output_dir.mkdir(parents=True, exist_ok=True)

            # Build a timestamp prefix for filenames
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            forecast_date = (
                self.current_config.get("parameters", {}).get("forecast_date", "")
                or self.current_config.get("parameters", {}).get("analysis_date", "")
            )
            date_str = str(forecast_date).replace("-", "") if forecast_date else ts

            saved_files = []

            if plot_type in ("meteogram", "plumes"):
                # data keys: "pf", "cf"
                for key in ("pf", "cf"):
                    if key in self.current_data and isinstance(self.current_data[key], dict):
                        ds = self.current_data[key].get("dataset")
                        if ds is not None:
                            fname = output_dir / f"{date_str}_{key}.grib"
                            ds.to_target(str(fname))
                            saved_files.append(str(fname))

            elif plot_type == "stamps":
                # data keys: "fc", "cf", "pf"
                for key in ("fc", "cf", "pf"):
                    if key in self.current_data and isinstance(self.current_data[key], dict):
                        ds = self.current_data[key].get("dataset")
                        if ds is not None:
                            fname = output_dir / f"{date_str}_{key}.grib"
                            ds.to_target(str(fname))
                            saved_files.append(str(fname))

            elif plot_type == "cdf":
                # data keys: "cd" and "forecast_data.scenarios"
                if "cd" in self.current_data and isinstance(self.current_data["cd"], dict):
                    ds = self.current_data["cd"].get("dataset")
                    if ds is not None:
                        fname = output_dir / f"{date_str}_cd.grib"
                        ds.to_target(str(fname))
                        saved_files.append(str(fname))

                forecast_data = self.current_data.get("forecast_data", {})
                scenarios = forecast_data.get("scenarios", {})
                for scenario_key, scenario_data in scenarios.items():
                    if isinstance(scenario_data, dict):
                        ds = scenario_data.get("dataset")
                        if ds is not None:
                            safe_key = scenario_key.replace("/", "_").replace(" ", "_")
                            fname = output_dir / f"{date_str}_{safe_key}.grib"
                            ds.to_target(str(fname))
                            saved_files.append(str(fname))

            if saved_files:
                files_list = "<br>".join(saved_files)
                if self.ui:
                    self.ui.show_alert_message(
                        f"Saved {len(saved_files)} file(s) to {output_dir}:<br>{files_list}",
                        "success",
                        section="data",
                        permanent=True,
                    )
            else:
                if self.ui:
                    self.ui.show_alert_message(
                        "No data fields found to save.",
                        "error",
                        section="data",
                        permanent=True,
                    )

        except Exception as e:
            traceback.print_exc()
            if self.ui:
                self.ui.show_alert_message(
                    f"Error saving data: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )

    def _on_data_retrieval_complete(self, config):
        """Handle completion of data retrieval with auto-plotting integration.

        Args:
            config: Configuration dictionary

        """
        try:
            if hasattr(self, "current_data") and self.current_data:
                self.plotting_manager.set_data(self.current_data, config)

                self.plotting_callbacks.refresh_parameter_options_from_data()

                plot_type = config.get("plot_type")

                if self.plotting_manager.available_parameters:
                    first_param = self.plotting_manager.available_parameters[0]
                    self.plotting_manager.current_parameter = first_param

                    if hasattr(self.ui, "auto_plot_parameter"):
                        self.ui.auto_plot_parameter = first_param
                        if hasattr(self.ui, "_update_auto_plot_unit"):
                            self.ui._update_auto_plot_unit()

                if self.ui:
                    self.ui.update_plotting_controls(None, plot_type)

                if hasattr(self.ui, "on_data_loaded"):
                    self.ui.on_data_loaded()
                    self.ui.data_loaded = True

                if self.map_handler and hasattr(
                    self.map_handler, "set_data_loaded_status"
                ):
                    self.map_handler.set_data_loaded_status(True)

                # Enable the Save to File button now that data is available
                if self.ui and "save_btn" in self.ui.widgets:
                    self.ui.widgets["save_btn"].disabled = False
                    self.ui.widgets["save_btn"].style.button_color = "#78909C"

                if self.ui:
                    self.ui.show_alert_message(
                        "Data retrieval completed successfully! Single-point auto-plotting ready.",
                        "success",
                        section="data",
                        permanent=True,
                    )

                    available_params = self.plotting_manager.available_parameters
                    if available_params:
                        calculated_params = [
                            p
                            for p in available_params
                            if p in ["ws", "tp", "lsp", "cp"]
                        ]

                        self.ui.show_alert_message(
                            f"Available parameters ({len(available_params)}): {', '.join(available_params[:5])}",
                            "info",
                            section="data",
                        )

                        if calculated_params:
                            self.ui.show_alert_message(
                                f"Calculated parameters available: {', '.join(calculated_params)}",
                                "success",
                                section="data",
                            )
                    else:
                        self._auto_create_stamps_plot()

        except Exception as e:
            traceback.print_exc()
            if self.ui:
                self.ui.show_alert_message(
                    f"Error in data retrieval completion handler: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )

    def _auto_create_stamps_plot(self):
        """Automatically create stamps plot for non-point-based plots."""
        try:
            if not self.plotting_manager or not self.plotting_manager.current_data:
                return

            parameter = self.plotting_manager.current_parameter
            step = getattr(self.ui, "auto_plot_step", 48) if self.ui else 48

            if parameter:

                def delayed_plot():
                    time.sleep(0.5)
                    self.create_stamps_plot(
                        parameter=parameter,
                        step=step,
                        unit_value=self.ui.auto_plot_unit
                        if hasattr(self.ui, "auto_plot_unit")
                        else "default",
                        palette_value=getattr(self.ui, "auto_plot_palette", 1)
                        if self.ui
                        else 1,
                    )

                plot_thread = threading.Thread(target=delayed_plot)
                plot_thread.daemon = True
                plot_thread.start()

        except Exception as e:
            print(f"Error in auto stamps plot creation: {e}")

    def _force_show_plotting_controls(self, plot_type):
        """Force the UI to show plotting controls.

        Args:
            plot_type: Type of plot

        Returns:
            bool: True if successful

        """
        try:
            if hasattr(self.ui, "_create_simplified_plot_interface"):
                simplified_controls = self.ui._create_simplified_plot_interface(
                    plot_type
                )

                self.ui.layout_manager.plot_controls_container.children = [
                    simplified_controls
                ]

                if hasattr(self.ui.layout_manager.plot_controls_container, "layout"):
                    self.ui.layout_manager.plot_controls_container.layout.display = (
                        "block"
                    )

                return True
            else:
                return False

        except Exception as e:
            print(f"Error in _force_show_plotting_controls: {e}")
            traceback.print_exc()
            return False

    def _browse_file(self, file_type):
        """Browse and select a file with validation.

        Args:
            file_type: Type of file to browse

        """
        self.data_management.browse_file(file_type)

    def _validate_grib_file(self, file_path):
        """Validate that the file is a proper GRIB file.

        Args:
            file_path: Path to file

        Returns:
            bool: True if valid

        """
        return self.data_management.validate_grib_file(file_path)

    def _detect_file_parameters(self, file_path, file_type):
        """Detect available parameters in the GRIB file.

        Args:
            file_path: Path to file
            file_type: Type of file

        """
        self.data_management.detect_file_parameters(file_path, file_type)

    def update_bbox_from_grib_file(self, file_path):
        """Extract and update bounding box from GRIB file.

        Args:
            file_path: Path to file

        Returns:
            bool: True if successful

        """
        return self.data_management.update_bbox_from_grib_file(file_path)

    def _reset_local_file_selections(self):
        """Reset all local file selections when changing plot types."""
        self.data_management.reset_local_file_selections()

    def _browse_scenario_file(self, scenario_key, widget_id, scenario_item):
        """Enhanced scenario file browsing with widget ID tracking.

        Args:
            scenario_key: Scenario key
            widget_id: Widget ID
            scenario_item: Scenario item dictionary

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

            days_back = scenario_item.get("days_back", 0)
            forecast_time = scenario_item.get("forecast_time", 0)
            title = f"Select {scenario_key} Scenario File (D-{days_back} at {forecast_time:02d}Z)"

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

            if not file_path:
                return

            if not os.path.exists(file_path):
                if self.ui:
                    self.ui.show_alert_message(
                        f"File not found: {Path(file_path).name}",
                        "warning",
                        section="data",
                    )
                return

            if self._validate_grib_file(file_path):
                self.selected_files["scenarios"][scenario_key] = file_path
                self._update_scenario_file_display_by_id(widget_id, file_path)

                if self.ui:
                    self.ui.show_alert_message(
                        f"{scenario_key} scenario file selected: {Path(file_path).name}",
                        "success",
                        section="data",
                    )

                if (
                    self.ui
                    and self.ui.current_data_source == "local"
                    and self.ui.current_plot_type == "cdf"
                    and len(self.selected_files["scenarios"]) == 1
                ):
                    self.update_bbox_from_grib_file(file_path)
            elif self.ui:
                self.ui.show_alert_message(
                    f"Invalid GRIB file: {Path(file_path).name}",
                    "error",
                    section="data",
                    permanent=True,
                )

        except Exception as e:
            if self.ui:
                err = str(e)
                if "DISPLAY" in err or "display" in err or "Tcl" in err:
                    self.ui.show_alert_message(
                        f"File browser unavailable (no graphical display in this environment). "
                        f"Please type the full path to your {scenario_key} file directly into "
                        f"the text box next to the '{scenario_key}' row and press Enter.",
                        "warning",
                        section="data",
                        permanent=True,
                    )
                else:
                    self.ui.show_alert_message(
                        f"Error selecting {scenario_key} file: {e}",
                        "error",
                        section="data",
                        permanent=True,
                    )

    def _update_scenario_file_display_by_id(self, widget_id, file_path):
        """Update scenario file display using widget ID.

        Args:
            widget_id: Widget ID
            file_path: Path to file

        """
        try:
            for scenario_item in self.ui.widgets.get("cdf_scenario_files", []):
                if scenario_item["id"] == widget_id:
                    scenario_row = scenario_item["widget"]
                    text_field = scenario_row.children[0]
                    filename = Path(file_path).name
                    text_field.value = filename
                    text_field.placeholder = f"Selected: {filename}"
                    break

        except Exception as e:
            if self.ui:
                self.ui.show_alert_message(
                    f"Error updating scenario file display: {e}",
                    "error",
                    section="data",
                    permanent=True,
                )

    def get_cdf_scenario_mapping(self):
        """Get detailed scenario mapping for CDF analysis.

        Returns:
            dict: Scenario mapping

        """
        if not self.ui:
            return {}

        scenario_mapping = {}

        for scenario_item in self.ui.widgets.get("cdf_scenario_files", []):
            days_back = scenario_item.get("days_back", 0)
            forecast_time = scenario_item.get("forecast_time", 0)
            original_name = scenario_item.get("name", "")

            standard_key = f"D-{days_back}_{forecast_time:02d}Z"

            if standard_key in self.selected_files.get("scenarios", {}):
                file_path = self.selected_files["scenarios"][standard_key]

                scenario_mapping[standard_key] = {
                    "file_path": file_path,
                    "original_name": original_name,
                    "days_back": days_back,
                    "forecast_time": forecast_time,
                    "description": f"Forecast from {days_back} days ago at {forecast_time:02d}Z",
                }

        return scenario_mapping

    def refresh_scenario_handlers(self):
        """Refresh scenario file handlers after UI updates."""
        if not self.ui:
            return

        for scenario_item in self.ui.widgets.get("cdf_scenario_files", []):
            self._setup_single_scenario_handler(scenario_item)

    def retrieve_observations(self, config):
        """Handle observation data retrieval and loading.

        Args:
            config: Configuration dictionary

        Returns:
            dict: Result dictionary

        """
        return self.observation_handler.retrieve_observations(config)

    def update_observation_times_display(self):
        """Update observation times display."""
        self.observation_handler.update_observation_times_display()

    def _handle_browse_observation_folder(self, widget, event, data):
        """Handle observation folder browsing.

        Args:
            widget: Widget that triggered event
            event: Event data
            data: Additional data

        """
        self.observation_handler.handle_browse_observation_folder(widget, event, data)

    def _handle_browse_output_directory(self, widget, event, data):
        """Handle output directory browsing.

        Args:
            widget: Widget that triggered event
            event: Event data
            data: Additional data

        """
        self.observation_handler.handle_browse_output_directory(widget, event, data)

    def _process_selected_observation_folder(self, folder_path):
        """Process selected observation folder.

        Args:
            folder_path: Path to folder

        """
        self.observation_handler._process_selected_observation_folder(folder_path)

    def create_stamps_plot(self, parameter, step, unit_value, palette_value, precip_accumulation=None):
        """Create stamps plot.

        Args:
            parameter: Parameter to plot
            step: Forecast step
            unit_value: Unit value
            palette_value: Palette value
            precip_accumulation: Optional accumulation window in hours for
                precipitation parameters (tp/lsp/cp). If None, raw field
                values are plotted.

        Returns:
            bool: True if successful

        """
        return self.plotting_callbacks.create_stamps_plot(
            parameter, step, unit_value, palette_value,
            precip_accumulation=precip_accumulation,
        )

    def create_cdf_plot(self, parameter, unit_value):
        """Create CDF plot.

        Args:
            parameter: Parameter to plot
            unit_value: Unit value

        Returns:
            bool: True if successful

        """
        return self.plotting_callbacks.create_cdf_plot(parameter, unit_value)

    def create_meteogram_plot(self, parameter, unit_value):
        """Create meteogram plot.

        Args:
            parameter: Parameter to plot
            unit_value: Unit value

        Returns:
            bool: True if successful

        """
        return self.plotting_callbacks.create_meteogram_plot(parameter, unit_value)

    def create_plumes_plot(self, parameter, unit_value):
        """Create plumes plot.

        Args:
            parameter: Parameter to plot
            unit_value: Unit value

        Returns:
            bool: True if successful

        """
        return self.plotting_callbacks.create_plumes_plot(parameter, unit_value)

    def clear_plots(self):
        """Clear all plots."""
        self.plotting_callbacks.clear_plots()

    def clear_selected_points(self):
        """Clear selected points."""
        self.plotting_callbacks.clear_selected_points()

    def on_add_manual_point_click(self):
        """Handle manual point addition."""
        self.plotting_callbacks.on_add_manual_point_click()

    def _update_parameters_for_plot_type(self, plot_type):
        """Update parameters for plot type.

        Args:
            plot_type: Plot type

        """
        self.plotting_callbacks.update_parameters_for_plot_type(plot_type)

    def get_plotting_manager(self):
        """Get the plotting manager instance.

        Returns:
            PlottingManager: Plotting manager instance

        """
        return self.plotting_manager

    def are_plot_types_compatible(self, plot_type1, plot_type2):
        """Check if two plot types are compatible for data reuse.

        Args:
            plot_type1: First plot type
            plot_type2: Second plot type

        Returns:
            bool: True if compatible

        """
        compatible_groups = [
            {"meteogram", "plumes"},  # Both use pf, cf, em data
        ]

        for group in compatible_groups:
            if plot_type1 in group and plot_type2 in group:
                return True

        return False
