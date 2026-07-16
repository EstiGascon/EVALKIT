import os
import platform
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog

import pandas as pd  # type: ignore

from helpers.stations_manipulating import (
    DateTimeExtractor,
    GeoDataProcessor,
    StationCreator,
)


def _get_rdylbu_colormap():
    """Return the RdYlBu_r matplotlib colormap, or None if matplotlib is unavailable."""
    try:
        from matplotlib import colormaps
        return colormaps["RdYlBu_r"]
    except Exception:
        return None


class ObservationHandlerCallbacks:
    """Handles observation data retrieval and management operations."""

    def __init__(self, parent):
        """Initialize observation handler callbacks.

        Args:
            parent: Parent EnsembleCallbacks instance

        """
        self.parent = parent
        self._obs_time_steps = []
        self._obs_time_index = 0
        self._obs_fixed_vmin = None
        self._obs_fixed_vmax = None
        self._obs_time_nav_setup = False

    def retrieve_observations(self, config):
        """Handle observation data.

        Args:
            config: Configuration dictionary

        Returns:
            dict: Result dictionary with success status

        """
        try:
            obs_mode = self.parent.ui.widgets["obs_data_source"].value

            if obs_mode == "browse":
                return self._handle_browse_mode()
            else:
                return self._handle_retrieve_mode(config)

        except Exception as e:
            return self._handle_error(str(e), "Error handling observation data")

    def _handle_browse_mode(self):
        """Load observations from local folder.

        Returns:
            dict: Result dictionary with success status

        """
        folder_path = self.parent.selected_observation_folder

        if not folder_path:
            return self._handle_error(
                "No folder selected", "No observation folder selected", "warning"
            )

        if not self._load_stations(folder_path):
            return {"success": False, "error": "Failed to load station metadata"}

        station_timeseries = self._load_timeseries(folder_path)
        if not station_timeseries:
            return self._handle_error(
                "No timeseries data found",
                "No timeseries data found in folder",
                "warning",
            )

        self._store_observation_data(folder_path, station_timeseries)

        self._sync_observations_to_plotting_manager()

        self._enable_observation_plotting()

        return self._create_success_response(station_timeseries)

    def _handle_retrieve_mode(self, config):
        """Retrieve observations using VINO.

        Args:
            config: Configuration dictionary

        Returns:
            dict: Result dictionary with success status

        """
        self._show_message(
            "Retrieving observations using VINO...", "info", section="observation"
        )

        param = self._validate_and_extract_parameter(config)
        if not param:
            return {"success": False, "error": "No valid parameter"}

        retrieval_config = self._prepare_retrieval_config(config, param)

        result = self._execute_retrieval(retrieval_config)

        if result.get("success"):
            return self._handle_successful_retrieval(retrieval_config["output_dir"])
        else:
            error_msg = result.get("error", "Unknown error")
            return self._handle_error(
                f"Retrieval failed: {error_msg}",
                f"Failed to retrieve {param.upper()}: {error_msg}",
            )

    def _load_stations(self, folder_path):
        """Load station metadata from folder.

        Args:
            folder_path: Path to observation data folder

        Returns:
            bool: True if successful, False otherwise

        """
        self._show_message(
            "Loading observation data from local folder...",
            "info",
            section="observation",
        )
        return self.load_observation_stations_from_folder(folder_path)

    def _load_timeseries(self, folder_path):
        """Load and process timeseries data.

        Args:
            folder_path: Path to observation data folder

        Returns:
            dict: Station timeseries data or None if failed

        """
        self._show_message("Processing station timeseries data...", "info")
        return self.process_station_timeseries_data(folder_path)

    def _store_observation_data(self, folder_path, station_timeseries):
        """Store observation data in parent's current_data structure.

        Args:
            folder_path: Path to observation data folder
            station_timeseries: Dictionary of station timeseries data

        """
        if not hasattr(self.parent, "current_data") or not self.parent.current_data:
            self.parent.current_data = {}

        detected_parameter = self._detect_parameter_from_folder(folder_path)

        self.parent.current_data["observations"] = {
            "stations_gdf": self.parent.observation_stations_gdf,
            "timeseries_data": station_timeseries,
            "metadata": {
                "folder_path": folder_path,
                "total_stations": len(self.parent.observation_stations_gdf),
                "stations_in_bbox": self._count_stations_in_bbox(station_timeseries),
                "parameter": detected_parameter,
                "data_type": "local_folder",
                "date_range": self._get_observation_date_range(station_timeseries),
                "source": "local_browse",
            },
        }

    def _sync_observations_to_plotting_manager(self):
        """Sync observations to the plotting manager so they are available for plots."""
        if not (
            hasattr(self.parent, "plotting_manager")
            and self.parent.plotting_manager
            and hasattr(self.parent.plotting_manager, "current_data")
            and self.parent.plotting_manager.current_data
            and "observations" in self.parent.current_data
        ):
            return

        obs = self.parent.current_data["observations"]
        self.parent.plotting_manager.current_data["observations"] = obs

    def _count_stations_in_bbox(self, station_timeseries):
        """Count how many stations are within the current bounding box.

        Args:
            station_timeseries: Dictionary of station timeseries data

        Returns:
            int: Number of stations in bounding box

        """
        return len(
            [
                s
                for s in station_timeseries.keys()
                if self._station_in_current_bbox(s, station_timeseries[s])
            ]
        )

    def _enable_observation_plotting(self):
        """Enable observation plotting checkbox in UI."""
        if not (
            hasattr(self.parent, "plotting_manager")
            and self.parent.plotting_manager
            and hasattr(self.parent.plotting_manager, "widgets")
        ):
            return

        widgets = self.parent.plotting_manager.widgets
        if "observations_checkbox" in widgets:
            widgets["observations_checkbox"].disabled = False
            widgets["observations_checkbox"].value = True

    def _create_success_response(self, station_timeseries):
        """Create success response with observation data summary.

        Args:
            station_timeseries: Dictionary of station timeseries data

        Returns:
            dict: Success response dictionary

        """
        total_observations = sum(
            len(data["timeseries"]) for data in station_timeseries.values()
        )

        detected_parameter = self.parent.current_data["observations"]["metadata"][
            "parameter"
        ]

        self._show_message(
            f"Observation data loaded successfully! "
            f"Stations: {len(station_timeseries)}, "
            f"Total observations: {total_observations}, "
            f"Parameter: {detected_parameter or 'unknown'}",
            "success",
            section="observation",
        )

        return {
            "success": True,
            "data": self.parent.current_data["observations"],
            "stations_count": len(station_timeseries),
            "observations_count": total_observations,
            "parameter": detected_parameter,
        }

    def _validate_and_extract_parameter(self, config):
        """Validate and extract parameter from config.

        Args:
            config: Configuration dictionary

        Returns:
            str: Parameter name or None if invalid

        """
        selected_param = config.get("parameters")

        if not selected_param:
            self._show_message(
                "No parameter selected for retrieval", "error", section="observation"
            )
            return None

        if isinstance(selected_param, str):
            selected_params = [selected_param]
        else:
            selected_params = (
                selected_param if isinstance(selected_param, list) else [selected_param]
            )

        if not selected_params or not selected_params[0]:
            self._show_message(
                "No valid parameter selected", "error", section="observation"
            )
            return None

        return selected_params[0]

    def _prepare_retrieval_config(self, config, param):
        """Prepare configuration dictionary for retrieval.

        Args:
            config: Original configuration dictionary
            param: Parameter name

        Returns:
            dict: Retrieval configuration

        """
        sources = config.get("sources", "synop hdobs")
        if isinstance(sources, list):
            sources = " ".join(sources)

        period = config.get("period")
        start_date = self._format_date(config.get("start_date"))
        end_date = self._format_date(config.get("end_date"))
        output_dir = config.get("output_dir", "./retrieved_observations")

        param_period = self._get_param_period(param, period)

        param_output_dir = os.path.join(output_dir, param)

        return {
            "sources": sources,
            "parameter": param,
            "period": param_period,
            "start_date": start_date,
            "end_date": end_date,
            "output_dir": param_output_dir,
        }

    def _format_date(self, date_value):
        """Format date to YYYYMMDD string.

        Args:
            date_value: Date object or string

        Returns:
            str: Formatted date string

        """
        if hasattr(date_value, "strftime"):
            return date_value.strftime("%Y%m%d")
        return date_value

    def _get_param_period(self, param, period):
        """Get parameter period if applicable.

        Args:
            param: Parameter name
            period: Period value from config

        Returns:
            int or None: Period value or None

        """
        if (
            param in ["tp", "10fg", "tmax", "tmin"]
            and period
            and period not in ["na", "mixed", "none", "unknown"]
        ):
            return int(period)
        return None

    def _execute_retrieval(self, retrieval_config):
        """Execute observation retrieval.

        Args:
            retrieval_config: Retrieval configuration dictionary

        Returns:
            dict: Result dictionary from retriever

        """
        try:
            result = self.parent.observations_retriever.retrieve(
                sources=retrieval_config["sources"],
                parameter=retrieval_config["parameter"],
                period=retrieval_config["period"],
                start_date=retrieval_config["start_date"],
                end_date=retrieval_config["end_date"],
                output_dir=retrieval_config["output_dir"],
            )
            return result

        except Exception as e:
            param = retrieval_config["parameter"]
            self._show_message(
                f"Error retrieving {param.upper()}: {e}", "error", section="observation"
            )
            return {"success": False, "error": str(e)}

    def _handle_successful_retrieval(self, output_dir):
        """Handle successful retrieval by switching to browse mode.

        Args:
            output_dir: Directory where data was retrieved

        Returns:
            dict: Result from browse mode handling

        """
        self.parent.selected_observation_folder = output_dir

        param_name = os.path.basename(output_dir)
        self._show_message(
            f"Retrieved {param_name.upper()} successfully. Loading stations...",
            "success",
            section="observation",
        )

        self.parent.ui.widgets["obs_data_source"].value = "browse"
        return self._handle_browse_mode()

    def _handle_error(self, error_msg, ui_msg=None, msg_type="error"):
        """Handle error with UI message and return error dict.

        Args:
            error_msg: Error message for return dict
            ui_msg: Optional message to show in UI (defaults to error_msg)
            msg_type: Message type (error, warning, info)

        Returns:
            dict: Error result dictionary

        """
        if self.parent.ui:
            self._show_message(ui_msg or error_msg, msg_type, section="observation")

        return {"success": False, "error": error_msg}

    def _show_message(self, message, msg_type, section="observation", permanent=True):
        """Show message in UI if available.

        Args:
            message: Message to display
            msg_type: Type of message (info, success, error, warning)
            section: UI section to show message in
            permanent: Whether message should be permanent

        """
        if self.parent.ui:
            self.parent.ui.show_alert_message(
                message, msg_type, section=section, permanent=permanent
            )

    def load_observation_stations_from_folder(self, folder_path):
        """Load observation stations from local folder, filtered by current bbox.

        Args:
            folder_path: Path to observation data folder

        Returns:
            bool: True if successful

        """
        try:
            station_creator = StationCreator()
            all_stations_gdf = station_creator.create_stations_geodataframe(folder_path)

            if all_stations_gdf is None or len(all_stations_gdf) == 0:
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "No observation stations found in folder",
                        "warning",
                        section="observation",
                        permanent=True,
                    )
                return False

            self.parent.original_observation_stations_gdf = all_stations_gdf
            self.parent.observation_folder_path = folder_path

            current_bbox = self._get_current_bbox_from_ui()

            if current_bbox:
                filtered_stations = self._filter_stations_by_bbox(
                    all_stations_gdf, current_bbox
                )
            else:
                filtered_stations = all_stations_gdf

            self.parent.observation_stations_gdf = filtered_stations

            station_ids_in_bbox = filtered_stations.index.tolist()

            station_timeseries = self.process_station_timeseries_data(
                folder_path, station_ids_in_bbox
            )

            if not station_timeseries:
                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "No timeseries data found for stations in current area",
                        "warning",
                        section="observation",
                        permanent=True,
                    )
                return False

            self._update_current_data_with_filtered_observations(
                folder_path, filtered_stations, station_timeseries
            )

            self._create_unified_observation_markers(filtered_stations)
            self._setup_obs_time_navigation()

            if self.parent.ui:
                total_observations = sum(
                    len(data["timeseries"]) for data in station_timeseries.values()
                )
                self.parent.ui.show_alert_message(
                    f"Loaded {len(filtered_stations)} stations in current area with {total_observations} observations",
                    "success",
                    section="observation",
                    permanent=True,
                )

            return True

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error loading observation stations: {e}",
                    "error",
                    section="observation",
                    permanent=True,
                )
            return False

    def process_station_timeseries_data(self, folder_path, station_ids=None):
        """Process station timeseries data into dict format.

        Args:
            folder_path: Path to observation data folder
            station_ids: Optional list of station IDs to restrict processing to.
                If None, all stations found in the geo files are processed.

        Returns:
            dict: Station timeseries data

        """
        try:
            geo_processor = GeoDataProcessor()
            geo_files = geo_processor.get_geo_files(folder_path)

            if not geo_files:
                return None

            station_timeseries = {}

            for geo_file in geo_files:
                try:
                    file_datetime = DateTimeExtractor.parse_filename_datetime(
                        Path(geo_file).name
                    )

                    station_data = geo_processor.read_geo_file(geo_file)

                    for station_record in station_data:
                        station_id = station_record["stnid"]

                        if station_ids is not None and station_id not in station_ids:
                            continue

                        if station_id not in station_timeseries:
                            station_timeseries[station_id] = {
                                "latitude": station_record["latitude"],
                                "longitude": station_record["longitude"],
                                "elevation": station_record.get("elevation"),
                                "timeseries": [],
                            }

                        station_timeseries[station_id]["timeseries"].append(
                            {
                                "datetime": file_datetime,
                                "value": station_record.get("value_0"),
                            }
                        )

                except Exception as e:
                    print(f"Error processing {geo_file}: {e}")
                    continue

            for station_id in station_timeseries:
                station_timeseries[station_id]["timeseries"].sort(
                    key=lambda x: x["datetime"]
                )

            return station_timeseries

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error processing station timeseries: {e}",
                    "error",
                    section="observation",
                    permanent=True,
                )
            return {}

    def update_observation_times_display(self):
        """Update the times display widget based on current parameter/period selection."""
        try:
            if not self.parent.ui:
                return

            selected_param = self.parent.ui.widgets["obs_parameters"].value
            selected_params = [selected_param] if selected_param else []

            current_period = self.parent.ui.widgets["obs_period"].value

            times_info = self.get_parameter_times_info(selected_params, current_period)

            self.parent.ui.widgets["obs_times_display"].value = times_info["times"]
            self.parent.ui.widgets["obs_times_display"].hint = times_info["description"]

        except Exception as e:
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error updating times display: {e}",
                    "error",
                    section="observation",
                    permanent=True,
                )

    def get_parameter_times_info(self, parameters, period=None):
        """Get time information for selected parameter.

        Args:
            parameters: List of parameters (single selection)
            period: Selected period

        Returns:
            dict: Times information with times string and description

        """
        if (
            not parameters
            or not parameters[0]
            or not self.parent.observations_retriever
        ):
            return {
                "times": "",
                "description": "No parameter selected or retriever unavailable",
            }

        try:
            param = parameters[0]
            param_info = self.parent.observations_retriever.get_parameter_info(param)

            if param_info["type"] == "instantaneous":
                return self._get_instantaneous_times_info(param, param_info)

            if param_info["type"] == "period":
                return self._get_period_times_info(param, param_info, period)

            return self._get_default_times_info(param)

        except Exception as e:
            return {"times": "", "description": f"Error determining times: {e}"}

    def _get_instantaneous_times_info(self, param, param_info):
        """Get times info for instantaneous parameters.

        Args:
            param: Parameter name
            param_info: Parameter information dictionary

        Returns:
            dict: Times information

        """
        times = param_info["default_times"]
        return {
            "times": times,
            "description": f"{param.upper()} (instantaneous): retrieved at {times} UTC",
        }

    def _get_period_times_info(self, param, param_info, period):
        """Get times info for period-based parameters.

        Args:
            param: Parameter name
            param_info: Parameter information dictionary
            period: Selected period

        Returns:
            dict: Times information

        """
        if not period or period in ["na", "mixed", "none", "unknown"]:
            return self._get_default_period_info(param, param_info)

        period_int = int(period)

        if period_int not in param_info["times_map"]:
            return {
                "times": "",
                "description": f"Period {period_int}h not supported for {param.upper()}",
            }

        times = param_info["times_map"][period_int]
        return {
            "times": times,
            "description": f"{param.upper()} ({period_int}h periods): retrieved at {times} UTC",
        }

    def _get_default_period_info(self, param, param_info):
        """Get times info using default period.

        Args:
            param: Parameter name
            param_info: Parameter information dictionary

        Returns:
            dict: Times information

        """
        default_period = param_info["default_period"]
        times = param_info["times_map"][default_period]
        return {
            "times": times,
            "description": f"{param.upper()} ({default_period}h periods): retrieved at {times} UTC",
        }

    def _get_default_times_info(self, param):
        """Get default times info for unknown parameter types.

        Args:
            param: Parameter name

        Returns:
            dict: Times information

        """
        return {
            "times": "00",
            "description": f"{param.upper()} (unknown type): default retrieval at 00 UTC",
        }

    def handle_browse_observation_folder(self, widget, event, data):
        """Handle observation folder browsing.

        Args:
            widget: Widget that triggered the event
            event: Event data
            data: Additional data

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

            folder_path = filedialog.askdirectory(
                title="Select Observation Data Folder",
                initialdir=os.path.expanduser("~"),
            )

            root.destroy()

            if folder_path:
                self._process_selected_observation_folder(folder_path)

        except Exception as e:
            if self.parent.ui:
                err = str(e)
                if "DISPLAY" in err or "display" in err or "Tcl" in err:
                    self.parent.ui.show_alert_message(
                        "Folder browser unavailable (no graphical display in this environment). "
                        "Please type the full path to your observation folder directly into "
                        "the 'Observation Folder' text box above and press Enter.",
                        "warning",
                        section="observation",
                        permanent=True,
                    )
                else:
                    self.parent.ui.show_alert_message(
                        f"Error browsing observation folder: {e}",
                        "error",
                        section="observation",
                        permanent=True,
                    )

    def handle_browse_output_directory(self, widget, event, data):
        """Handle output directory browsing.

        Args:
            widget: Widget that triggered the event
            event: Event data
            data: Additional data

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

            directory = filedialog.askdirectory(
                title="Select Output Directory for Retrieved Observations",
                initialdir=os.path.expanduser("~"),
            )

            root.destroy()

            if directory:
                self.parent.ui.widgets["obs_output_dir"].value = directory

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        f"Output directory selected: {directory}", "success"
                    )

        except Exception as e:
            if self.parent.ui:
                err = str(e)
                if "DISPLAY" in err or "display" in err or "Tcl" in err:
                    self.parent.ui.show_alert_message(
                        "Folder browser unavailable (no graphical display in this environment). "
                        "Please type the full output directory path directly into "
                        "the 'Output Directory' text box above and press Enter.",
                        "warning",
                        section="observation",
                        permanent=True,
                    )
                else:
                    self.parent.ui.show_alert_message(
                        f"Error browsing output directory: {e}",
                        "error",
                        section="observation",
                        permanent=True,
                    )

    def update_observation_stations_for_bbox(self):
        """Reload observation stations and data when bbox changes."""
        if (
            not hasattr(self.parent, "original_observation_stations_gdf")
            or self.parent.original_observation_stations_gdf is None
        ):
            return

        try:
            bbox = self._get_current_bbox_from_ui()
            if not bbox:
                return

            filtered_stations = self._filter_stations_by_bbox(
                self.parent.original_observation_stations_gdf, bbox
            )

            self.parent.observation_stations_gdf = filtered_stations

            if hasattr(self.parent.map_handler, "clear_observation_markers"):
                self.parent.map_handler.clear_observation_markers()

            if len(filtered_stations) == 0:
                if (
                    hasattr(self.parent, "current_data")
                    and "observations" in self.parent.current_data
                ):
                    del self.parent.current_data["observations"]

                if self.parent.ui:
                    self.parent.ui.show_alert_message(
                        "No observation stations in selected area",
                        "info",
                        section="observation",
                        permanent=True,
                    )
                return

            station_ids_in_bbox = filtered_stations.index.tolist()

            station_timeseries = self.process_station_timeseries_data(
                self.parent.observation_folder_path, station_ids_in_bbox
            )

            self._update_current_data_with_filtered_observations(
                self.parent.observation_folder_path,
                filtered_stations,
                station_timeseries,
            )

            self._create_unified_observation_markers(filtered_stations)
            self._setup_obs_time_navigation()

            if self.parent.ui:
                total_observations = sum(
                    len(data["timeseries"]) for data in station_timeseries.values()
                )
                self.parent.ui.show_alert_message(
                    f"Updated to {len(filtered_stations)} stations in new area with {total_observations} observations",
                    "success",
                    section="observation",
                    permanent=True,
                )

        except Exception as e:
            print(f"Error in update_observation_stations_for_bbox: {e}")
            traceback.print_exc()

            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error updating observation stations for bbox: {e}",
                    "error",
                    section="observation",
                    permanent=True,
                )

    def _process_selected_observation_folder(self, folder_path):
        """Process the selected observation folder with validation and preview.

        Args:
            folder_path: Path to selected folder

        """
        try:
            self._setup_folder_selection(folder_path)

            validation_result = self._validate_observation_folder_structure(folder_path)
            if not validation_result["valid"]:
                self._handle_invalid_folder(validation_result["error"])
                return

            detected_param = self._detect_parameter_from_folder(folder_path)
            self._show_folder_preview(folder_path, validation_result, detected_param)

            success = self._load_and_display_stations(folder_path, detected_param)

            if success:
                self._finalize_successful_load(validation_result, detected_param)

        except Exception as e:
            self._handle_folder_processing_error(e)

    def _setup_folder_selection(self, folder_path):
        """Set up basic folder selection in UI.

        Args:
            folder_path: Path to selected folder

        """
        folder_name = os.path.basename(folder_path)
        self.parent.ui.widgets["obs_folder_display"].value = folder_name
        self.parent.selected_observation_folder = folder_path

    def _handle_invalid_folder(self, error_message):
        """Handle invalid folder structure.

        Args:
            error_message: Error description

        """
        if self.parent.ui:
            self.parent.ui.show_alert_message(
                f"Invalid folder structure: {error_message}",
                "error",
                section="observation",
                permanent=True,
            )

    def _show_folder_preview(self, folder_path, validation_result, detected_param):
        """Show folder preview with validation info.

        Args:
            folder_path: Path to selected folder
            validation_result: Validation result dictionary
            detected_param: Detected parameter or None

        """
        folder_name = os.path.basename(folder_path)
        summary_info = self._build_summary_info(
            folder_name, validation_result, detected_param
        )

        preview_html = self._create_info_html(summary_info)
        self._update_status_display(preview_html)

        self._show_folder_selection_messages(folder_name, detected_param)

    def _build_summary_info(self, folder_name, validation_result, detected_param):
        """Build summary information list.

        Args:
            folder_name: Name of the folder
            validation_result: Validation result dictionary
            detected_param: Detected parameter or None

        Returns:
            list: Summary information lines

        """
        summary_info = [f"Selected: {folder_name}"]

        if detected_param:
            summary_info.append(f"Detected parameter: {detected_param}")
        else:
            summary_info.append("Could not detect parameter from folder name")

        summary_info.append(f"Found {validation_result['geo_files_count']} geo files")

        if validation_result["date_range"]:
            date_range_str = self._format_date_range(validation_result["date_range"])
            summary_info.append(f"Data period: {date_range_str}")

        return summary_info

    def _format_date_range(self, date_range):
        """Format date range for display.

        Args:
            date_range: Dictionary with 'start' and 'end' datetime objects

        Returns:
            str: Formatted date range string

        """
        start_date = date_range["start"].strftime("%Y-%m-%d %H:00")
        end_date = date_range["end"].strftime("%Y-%m-%d %H:00")
        return f"{start_date} to {end_date}"

    def _show_folder_selection_messages(self, folder_name, detected_param):
        """Show alert messages for folder selection.

        Args:
            folder_name: Name of the folder
            detected_param: Detected parameter or None

        """
        if not self.parent.ui:
            return

        self.parent.ui.show_alert_message(
            f"Observation folder selected: {folder_name}. Loading stations...",
            "info",
            section="observation",
            permanent=True,
        )

        if detected_param:
            self.parent.ui.show_alert_message(
                f"Auto-detected parameter: {detected_param}",
                "info",
                section="observation",
                permanent=True,
            )

    def _load_and_display_stations(self, folder_path, detected_param):
        """Load stations and update display.

        Args:
            folder_path: Path to folder
            detected_param: Detected parameter or None

        Returns:
            bool: True if successful, False otherwise

        """
        success = self.load_observation_stations_from_folder(folder_path)

        if not success:
            self._handle_station_load_failure(folder_path)
            return False

        station_count = self._get_station_count()
        self._show_station_load_success(folder_path, station_count, detected_param)

        return True

    def _get_station_count(self):
        """Get count of loaded observation stations.

        Returns:
            int: Number of stations

        """
        if (
            hasattr(self.parent, "observation_stations_gdf")
            and self.parent.observation_stations_gdf is not None
        ):
            return len(self.parent.observation_stations_gdf)
        return 0

    def _handle_station_load_failure(self, folder_path):
        """Handle failure to load stations.

        Args:
            folder_path: Path to folder

        """
        if self.parent.ui:
            self.parent.ui.show_alert_message(
                "Failed to load observation stations from folder",
                "error",
                section="observation",
                permanent=True,
            )

        folder_name = os.path.basename(folder_path)
        detected_param = self._detect_parameter_from_folder(folder_path)
        validation_result = self._validate_observation_folder_structure(folder_path)

        summary_info = self._build_summary_info(
            folder_name, validation_result, detected_param
        )
        summary_info.append("❌ Failed to load station data")

        error_html = self._create_error_html(summary_info)
        self._update_status_display(error_html)

    def _show_station_load_success(self, folder_path, station_count, detected_param):
        """Show success message and update display.

        Args:
            folder_path: Path to folder
            station_count: Number of loaded stations
            detected_param: Detected parameter or None

        """
        folder_name = os.path.basename(folder_path)
        validation_result = self._validate_observation_folder_structure(folder_path)

        summary_info = self._build_summary_info(
            folder_name, validation_result, detected_param
        )
        summary_info.append(f"Loaded {station_count} observation stations")

        success_html = self._create_success_html(summary_info)
        self._update_status_display(success_html)

        if self.parent.ui:
            self.parent.ui.show_alert_message(
                f"Successfully loaded {station_count} observation stations",
                "success",
                section="observation",
                permanent=True,
            )

    def _finalize_successful_load(self, validation_result, detected_param):
        """Finalize successful station load.

        Args:
            validation_result: Validation result dictionary
            detected_param: Detected parameter or None

        """
        if (
            hasattr(self.parent, "observation_stations_gdf")
            and self.parent.observation_stations_gdf is not None
        ):
            self.update_observation_stations_for_bbox()

    def _handle_folder_processing_error(self, error):
        """Handle errors during folder processing.

        Args:
            error: Exception that occurred

        """
        if self.parent.ui:
            self.parent.ui.show_alert_message(
                f"Error processing observation folder: {error}",
                "error",
                section="observation",
                permanent=True,
            )

        self.parent.ui.widgets["obs_folder_display"].value = ""
        self.parent.selected_observation_folder = None
        self.parent.observation_stations_gdf = None

        if hasattr(self.parent.map_handler, "clear_observation_markers"):
            self.parent.map_handler.clear_observation_markers()
        if self.parent.ui and "obs_colorbar" in self.parent.ui.widgets:
            self.parent.ui.widgets["obs_colorbar"].layout.display = "none"
        if self.parent.map_handler and hasattr(self.parent.map_handler, "hide_obs_legend"):
            self.parent.map_handler.hide_obs_legend()

        error_html = self._create_simple_error_html(str(error))
        self._update_status_display(error_html)

    def _create_info_html(self, summary_info):
        """Create info HTML box.

        Args:
            summary_info: List of summary lines

        Returns:
            str: HTML string

        """
        return f"""
        <div style="background-color: #E8F5E8; padding: 10px; border-radius: 5px;
                border-left: 4px solid #50DEA3; margin: 10px 0;">
            <span style="color: #2E7D32;">{"<br>".join(summary_info)}</span>
        </div>
        """

    def _create_success_html(self, summary_info):
        """Create success HTML box.

        Args:
            summary_info: List of summary lines

        Returns:
            str: HTML string

        """
        return self._create_info_html(summary_info)

    def _create_error_html(self, summary_info):
        """Create error HTML box.

        Args:
            summary_info: List of summary lines

        Returns:
            str: HTML string

        """
        return f"""
        <div style="background-color: #ffebee; padding: 10px; border-radius: 5px;
                border-left: 4px solid #f44336; margin: 10px 0;">
            <span style="color: #c62828;">{"<br>".join(summary_info)}</span>
        </div>
        """

    def _create_simple_error_html(self, error_message):
        """Create simple error HTML box.

        Args:
            error_message: Error message to display

        Returns:
            str: HTML string

        """
        return f"""
        <div style="background-color: #ffebee; padding: 10px; border-radius: 5px;
                border-left: 4px solid #f44336; margin: 10px 0;">
            <span style="color: #c62828;">Error: {error_message}</span>
        </div>
        """

    def _update_status_display(self, html_content):
        """Update status display widget.

        Args:
            html_content: HTML string to display

        """
        self.parent.ui.widgets["obs_status_display"].layout.display = "block"
        self.parent.ui.widgets["obs_status_display"].value = html_content

    def _detect_parameter_from_folder(self, folder_path):
        """Detect weather parameter from folder path/contents.

        Args:
            folder_path: Path to folder

        Returns:
            str: Detected parameter name or None

        """
        try:
            params = ["10ff", "10fg", "2d", "2t", "tp", "tmin", "tmax"]
            param_mapping = {"tmax": "mx2t", "tmin": "mn2t"}

            path_obj = Path(folder_path)
            path_str = str(path_obj).lower()

            for param in sorted(params, key=len, reverse=True):
                if param in path_str or any(
                    param in part.lower() for part in path_obj.parts
                ):
                    return param_mapping.get(param, param)

            try:
                geo_files = list(path_obj.glob("*geo*.geo"))
                if geo_files:
                    first_geo = geo_files[0].name.lower()
                    for param in sorted(params, key=len, reverse=True):
                        if param in first_geo:
                            return param_mapping.get(param, param)
            except Exception:
                pass

            return None

        except Exception as e:
            print(f"Error detecting parameter from folder: {e}")
            return None

    def _validate_observation_folder_structure(self, folder_path):
        """Validate observation folder structure and return summary info.

        Args:
            folder_path: Path to folder

        Returns:
            dict: Validation result

        """
        try:
            path_obj = Path(folder_path)

            if not path_obj.exists():
                return {"valid": False, "error": "Folder does not exist"}

            if not path_obj.is_dir():
                return {"valid": False, "error": "Path is not a directory"}

            geo_processor = GeoDataProcessor()
            geo_files = geo_processor.get_geo_files(folder_path)

            if not geo_files:
                return {"valid": False, "error": "No .geo files found in folder"}

            date_range = None
            try:
                if len(geo_files) > 0:
                    date_range = DateTimeExtractor.get_date_range_from_files(geo_files)
            except Exception as e:
                print(f"Warning: Could not determine date range: {e}")

            try:
                test_data = geo_processor.read_geo_file(geo_files[0])
                if not test_data:
                    return {"valid": False, "error": "Could not read geo file data"}
            except Exception as e:
                return {"valid": False, "error": f"Error reading geo files: {e}"}

            return {
                "valid": True,
                "geo_files_count": len(geo_files),
                "date_range": {"start": date_range[0], "end": date_range[1]}
                if date_range and date_range[0]
                else None,
                "sample_stations": len(test_data) if test_data else 0,
            }

        except Exception as e:
            return {"valid": False, "error": f"Validation error: {e}"}

    def _filter_stations_by_bbox(self, stations_gdf, bbox):
        """Filter stations GeoDataFrame by bounding box.

        Args:
            stations_gdf: GeoDataFrame of stations
            bbox: Bounding box dictionary

        Returns:
            GeoDataFrame: Filtered stations

        """
        north, south, east, west = (
            bbox["north"],
            bbox["south"],
            bbox["east"],
            bbox["west"],
        )

        mask = (
            (stations_gdf["latitude"] >= south)
            & (stations_gdf["latitude"] <= north)
            & (stations_gdf["longitude"] >= west)
            & (stations_gdf["longitude"] <= east)
        )

        return stations_gdf[mask]

    def _get_current_bbox_from_ui(self):
        """Get current bbox from UI widgets.

        Returns:
            dict: Bounding box dictionary or None

        """
        try:
            if not self.parent.ui or not hasattr(self.parent.ui, "widgets"):
                return None

            return {
                "north": float(self.parent.ui.widgets["north"].value),
                "south": float(self.parent.ui.widgets["south"].value),
                "east": float(self.parent.ui.widgets["east"].value),
                "west": float(self.parent.ui.widgets["west"].value),
            }

        except Exception:
            return None

    def _station_in_current_bbox(self, station_id, station_data):
        """Check if a station is within the current bbox.

        Args:
            station_id: Station ID
            station_data: Station data dictionary

        Returns:
            bool: True if in bbox

        """
        try:
            bbox = self._get_current_bbox_from_ui()
            if not bbox:
                return True

            lat = station_data["latitude"]
            lon = station_data["longitude"]

            return (
                bbox["south"] <= lat <= bbox["north"]
                and bbox["west"] <= lon <= bbox["east"]
            )

        except Exception:
            return True

    def _get_observation_date_range(self, station_timeseries):
        """Get the date range of observations.

        Args:
            station_timeseries: Station timeseries data

        Returns:
            dict: Date range information or None

        """
        try:
            all_dates = []
            for station_data in station_timeseries.values():
                for obs in station_data["timeseries"]:
                    all_dates.append(obs["datetime"])

            if all_dates:
                return {
                    "start": min(all_dates),
                    "end": max(all_dates),
                    "total_timesteps": len(set(all_dates)),
                }

            return None

        except Exception:
            return None

    def _update_current_data_with_filtered_observations(
        self, folder_path, filtered_stations, station_timeseries
    ):
        """Update current_data with only the filtered observation data.

        Args:
            folder_path: Path to observation folder
            filtered_stations: Filtered stations GeoDataFrame
            station_timeseries: Station timeseries data

        """
        if not hasattr(self.parent, "current_data") or not self.parent.current_data:
            self.parent.current_data = {}

        detected_parameter = self._detect_parameter_from_folder(folder_path)

        self.parent.current_data["observations"] = {
            "stations_gdf": filtered_stations,
            "timeseries_data": station_timeseries,
            "metadata": {
                "folder_path": folder_path,
                "total_stations": len(filtered_stations),
                "stations_with_data": len(station_timeseries),
                "parameter": detected_parameter,
                "data_type": "local_folder_filtered",
                "date_range": self._get_observation_date_range(station_timeseries),
                "source": "local_browse_bbox_filtered",
                "bbox_filtered": True,
            },
        }

    @staticmethod
    def _value_to_hex(value, vmin, vmax):
        """Map a scalar value to a hex colour using the RdYlBu_r colormap."""
        cmap = _get_rdylbu_colormap()
        if cmap is None:
            return "#949190"
        denom = vmax - vmin if vmax != vmin else 1.0
        t = max(0.0, min(1.0, (value - vmin) / denom))
        r, g, b, _ = cmap(t)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    @staticmethod
    def _build_colorbar_html(vmin, vmax, unit=""):
        """Return an HTML snippet showing a horizontal colourbar legend."""
        try:
            cmap = _get_rdylbu_colormap()
            if cmap is None:
                raise ValueError("RdYlBu_r colormap unavailable")
            n = 20
            stops = []
            for i in range(n + 1):
                t = i / n
                r, g, b, _ = cmap(t)
                pct = round(t * 100)
                stops.append(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x} {pct}%")
            gradient = ", ".join(stops)
        except Exception:
            gradient = "#0000ff 0%, #ff0000 100%"
        label_lo = f"{vmin:.1f}"
        label_hi = f"{vmax:.1f}"
        unit_str = f" {unit}" if unit else ""
        return (
            f'<div style="margin:4px 0;font-size:0.8em;color:#444;">'
            f'<span style="font-weight:bold;">Station mean values{unit_str}</span><br>'
            f'<div style="display:flex;align-items:center;gap:4px;margin-top:3px;">'
            f'<span>{label_lo}</span>'
            f'<div style="flex:1;height:10px;border-radius:4px;'
            f'background:linear-gradient(to right,{gradient});'
            f'border:1px solid #ccc;"></div>'
            f'<span>{label_hi}</span>'
            f'</div></div>'
        )

    def _create_unified_observation_markers(self, filtered_stations_gdf):
        """Create observation markers coloured by mean observation value.

        Args:
            filtered_stations_gdf: Filtered stations GeoDataFrame

        """
        try:
            import ipyleaflet as _ipl
            import ipywidgets as _w

            if (
                not self.parent.map_handler
                or filtered_stations_gdf is None
                or len(filtered_stations_gdf) == 0
            ):
                return

            self.parent.map_handler.clear_observation_markers()

            # Compute per-station mean observation value for colour mapping
            timeseries_data = (
                self.parent.current_data.get("observations", {}).get("timeseries_data", {})
                if hasattr(self.parent, "current_data") and self.parent.current_data
                else {}
            )
            station_means = {}
            for sid, data in timeseries_data.items():
                values = [
                    entry["value"]
                    for entry in data.get("timeseries", [])
                    if entry.get("value") is not None
                ]
                if values:
                    station_means[sid] = sum(values) / len(values)

            has_values = bool(station_means)
            if has_values:
                # Clamp colour range to visible stations only for better contrast
                visible_means = {sid: v for sid, v in station_means.items() if sid in filtered_stations_gdf.index}
                scale_source = visible_means if visible_means else station_means
                vmin = min(scale_source.values())
                vmax = max(scale_source.values())
            else:
                vmin = vmax = 0.0

            markers = []
            for station_id, station_info in filtered_stations_gdf.iterrows():
                lat = station_info["latitude"]
                lon = station_info["longitude"]
                mean_val = station_means.get(station_id)

                if mean_val is not None and has_values and vmin != vmax:
                    fill_color = self._value_to_hex(mean_val, vmin, vmax)
                    val_str = f"{mean_val:.2f}"
                else:
                    fill_color = "#949190"
                    val_str = "N/A" if mean_val is None else f"{mean_val:.2f}"

                marker_data = {
                    "station_id": station_id,
                    "lat": lat,
                    "lon": lon,
                    "type": "observation",
                    "color": fill_color,
                    "popup_info": self._create_observation_popup_info(
                        station_id, station_info, mean_val=mean_val,
                    ),
                }
                self.parent.map_handler.add_observation_marker(
                    marker_data, on_click=None
                )
                marker = self.parent.map_handler.observation_markers.get(station_id)
                if marker is not None:
                    markers.append(marker)

            # Atomically replace the observation layer group
            new_layer_group = _ipl.LayerGroup(
                layers=markers, name="observation_stations"
            )
            self.parent.map_handler.map_widget.substitute_layer(
                self.parent.map_handler.observation_layer_group, new_layer_group
            )
            self.parent.map_handler.observation_layer_group = new_layer_group

            # Show/hide colorbar legend
            if (
                self.parent.ui
                and "obs_colorbar" in self.parent.ui.widgets
            ):
                if has_values and vmin != vmax:
                    self.parent.ui.widgets["obs_colorbar"].value = self._build_colorbar_html(vmin, vmax)
                    self.parent.ui.widgets["obs_colorbar"].layout.display = ""
                else:
                    self.parent.ui.widgets["obs_colorbar"].layout.display = "none"

            # Also update map legend overlay
            if self.parent.map_handler:
                if has_values and vmin != vmax:
                    obs_meta = self.parent.current_data.get("observations", {}).get("metadata", {})
                    unit = obs_meta.get("parameter", "")
                    self.parent.map_handler.update_obs_legend(vmin, vmax, unit=unit)
                else:
                    self.parent.map_handler.hide_obs_legend()

        except Exception as e:
            print(f"Error creating unified observation markers: {e}")
            if self.parent.ui:
                self.parent.ui.show_alert_message(
                    f"Error creating station markers: {e}",
                    "error",
                    section="observation",
                    permanent=True,
                )

    def _create_observation_popup_info(self, station_id, station_info, mean_val=None):
        """Create popup information for observation station.

        Args:
            station_id: Station ID
            station_info: Station information
            mean_val: Mean observation value (optional)

        Returns:
            str: HTML popup content

        """
        try:
            elevation = station_info.get("elevation")
            has_elevation = elevation is not None and not pd.isna(elevation)
            data_count = 0

            if (
                hasattr(self.parent, "current_data")
                and self.parent.current_data
                and "observations" in self.parent.current_data
                and "timeseries_data" in self.parent.current_data["observations"]
                and station_id
                in self.parent.current_data["observations"]["timeseries_data"]
            ):
                station_data = self.parent.current_data["observations"][
                    "timeseries_data"
                ][station_id]
                data_count = len(station_data.get("timeseries", []))

            val_line = ""
            if mean_val is not None:
                val_line = f'<p style="margin: 2px 0; font-size: 1.1em;"><strong>Mean value:</strong> <span style="color:#E65100;">{mean_val:.2f}</span></p>'

            popup_html = f"""
                <div style="width: 280px; color: black;">
                    <h4 style="margin-bottom: 10px;">Obs Station {station_id}</h4>
                    {val_line}
                    <p style="margin: 2px 0;"><strong>Location:</strong> {station_info["latitude"]:.3f}°N, {station_info["longitude"]:.3f}°E</p>
                    {f'<p style="margin: 2px 0;"><strong>Elevation:</strong> {elevation:.1f} m</p>' if has_elevation else ""}
                    <p style="margin: 2px 0;"><strong>Data Points:</strong> {data_count}</p>
                </div>
            """

            return popup_html

        except Exception as e:
            print(f"Error creating popup info: {e}")
            return f"<div>Station {station_id}</div>"

    # ------------------------------------------------------------------
    # Time-step navigation for observation markers
    # ------------------------------------------------------------------

    def _setup_obs_time_navigation(self):
        """Collect unique sorted time steps from observation data and show nav buttons."""
        if not self.parent.ui:
            return

        timeseries_data = (
            self.parent.current_data.get("observations", {}).get("timeseries_data", {})
            if hasattr(self.parent, "current_data") and self.parent.current_data
            else {}
        )
        if not timeseries_data:
            return

        all_times = set()
        for data in timeseries_data.values():
            for entry in data.get("timeseries", []):
                dt = entry.get("datetime")
                if dt is not None:
                    all_times.add(dt)

        self._obs_time_steps = sorted(all_times)
        if not self._obs_time_steps:
            return

        self._obs_time_index = 0

        # Compute fixed min/max from first time step
        values_at_first = self._get_station_values_at_time(self._obs_time_steps[0])
        vals = [v for v in values_at_first.values() if v is not None]
        if vals:
            self._obs_fixed_vmin = min(vals)
            self._obs_fixed_vmax = max(vals)
        else:
            self._obs_fixed_vmin = 0
            self._obs_fixed_vmax = 1

        # Wire up buttons once
        if not self._obs_time_nav_setup:
            self.parent.ui.widgets["obs_time_prev"].on_click(self._on_obs_time_prev)
            self.parent.ui.widgets["obs_time_next"].on_click(self._on_obs_time_next)
            self._obs_time_nav_setup = True

        # Show nav widgets (HBox and all children)
        self.parent.ui.widgets["obs_time_nav"].layout.display = "flex"
        self.parent.ui.widgets["obs_time_prev"].layout.display = "inline-flex"
        self.parent.ui.widgets["obs_time_next"].layout.display = "inline-flex"
        self.parent.ui.widgets["obs_time_label"].layout.display = "inline-block"
        self._update_obs_time_label()
        self._color_markers_at_current_time()

    def _get_station_values_at_time(self, target_dt):
        """Return {station_id: value} for the given datetime."""
        timeseries_data = (
            self.parent.current_data.get("observations", {}).get("timeseries_data", {})
        )
        result = {}
        for sid, data in timeseries_data.items():
            val = None
            for entry in data.get("timeseries", []):
                if entry.get("datetime") == target_dt:
                    val = entry.get("value")
                    break
            result[sid] = val
        return result

    def _on_obs_time_prev(self, _btn):
        """Handle previous time step button click."""
        if self._obs_time_index > 0:
            self._obs_time_index -= 1
            self._update_obs_time_label()
            self._color_markers_at_current_time()

    def _on_obs_time_next(self, _btn):
        """Handle next time step button click."""
        if self._obs_time_index < len(self._obs_time_steps) - 1:
            self._obs_time_index += 1
            self._update_obs_time_label()
            self._color_markers_at_current_time()

    def _update_obs_time_label(self):
        """Update the time step label."""
        if not self._obs_time_steps:
            return
        dt = self._obs_time_steps[self._obs_time_index]
        total = len(self._obs_time_steps)
        idx = self._obs_time_index + 1
        label = dt.strftime("%Y-%m-%d %H:%M") if hasattr(dt, "strftime") else str(dt)
        self.parent.ui.widgets["obs_time_label"].value = (
            f"<span style='font-size:12px;color:#333;'><b>{label}</b> ({idx}/{total})</span>"
        )

    def _color_markers_at_current_time(self):
        """Re-color observation markers for the current time step."""
        if not self._obs_time_steps:
            return

        import ipyleaflet as _ipl
        import ipywidgets as _widgets

        target_dt = self._obs_time_steps[self._obs_time_index]
        station_values = self._get_station_values_at_time(target_dt)
        label = target_dt.strftime("%Y-%m-%d %H:%M") if hasattr(target_dt, "strftime") else str(target_dt)

        vmin = self._obs_fixed_vmin
        vmax = self._obs_fixed_vmax

        for sid, marker in self.parent.map_handler.observation_markers.items():
            val = station_values.get(sid)
            if val is not None and vmin != vmax:
                color = self._value_to_hex(val, vmin, vmax)
            else:
                color = "#949190"
            marker.color = color
            marker.fill_color = color

            # Update popup to show value at this time step
            val_str = f"{val:.2f}" if val is not None else "N/A"
            popup_html = (
                f'<div style="width:200px;color:black;">'
                f'<b>Station {sid}</b><br>'
                f'<span style="font-size:1.1em;color:#E65100;"><b>{val_str}</b></span><br>'
                f'<span style="font-size:0.85em;color:#666;">{label}</span>'
                f'</div>'
            )
            marker.popup = _ipl.Popup(
                child=_widgets.HTML(popup_html),
                close_button=False,
                auto_close=True,
                max_width=220,
            )
