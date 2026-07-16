import os
import platform
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from helpers.observations_retriever import ObservationsRetriever
from helpers.parameter_mapper import ConfigurationManager
from helpers.widgets.map_handler import WeatherMapHandler
from helpers.widgets.status_message_handler import StatusMessageHandler

from .user_interface.ui_layout_manager import UILayoutManager
from .user_interface.widget_configuration import WidgetConfiguration
from .user_interface.widget_observer_manager import WidgetObserverManager


class TimeseriesUI:
    """Simplified interactive widgets for weather data retrieval and visualization."""

    def __init__(self):
        """Initialize the simplified widget interface."""
        self.config_manager = ConfigurationManager()
        self.widget_config = WidgetConfiguration()
        self.widgets = self.widget_config.get_widgets()

        # Dynamically initialize selected_file_paths from config
        self.selected_file_paths = {}
        for model_key in self.config_manager.models.keys():
            model_short = model_key.split("-")[0]
            self.selected_file_paths[model_short] = None

        self.selected_observation_folder = None
        self.observation_parameter_validated = False
        self.available_parameters = []
        self.callbacks = None
        self.current_bbox = None

        self.map_handler = WeatherMapHandler(self)

        self.layout_manager = UILayoutManager(self.widgets, self.map_handler)
        self.observer_manager = WidgetObserverManager(
            self.widgets, self, self.layout_manager
        )

        self.observer_manager.setup_all_observers()

        self._initialize_default_visibility()

    def _initialize_default_visibility(self):
        """Initialize default visibility states for conditional sections."""
        self.widgets["observations_checkbox"].disabled = True

        if "units_container" in self.widgets:
            self.widgets["units_container"].layout.display = "none"
        if "precipitation_container" in self.widgets:
            self.widgets["precipitation_container"].layout.display = "none"

    def set_callbacks(self, callbacks):
        """Set callback handler for main action buttons."""
        self.callbacks = callbacks
        callbacks.map_handler = self.map_handler

        self.observer_manager.set_callbacks(callbacks)

        if hasattr(callbacks, "setup_map_drawing_callback"):
            callbacks.setup_map_drawing_callback()

        for button_name in ["preview_btn", "retrieve_btn", "load_both_btn"]:
            if button_name in self.widgets:
                widget = self.widgets[button_name]
                if hasattr(widget, "_click_handlers"):
                    widget._click_handlers.callbacks.clear()

        self.widgets["preview_btn"].on_click(callbacks.on_preview_click)
        self.widgets["retrieve_btn"].on_click(callbacks.on_retrieve_click)
        self.widgets["load_both_btn"].on_click(callbacks.on_load_both_files_click)

        self.widgets["add_manual_point_btn"].on_click(
            callbacks.on_add_manual_point_click
        )

    def display_interface(self):
        """Display the complete interface."""
        self.layout_manager.display_interface()

    def get_parameters(self):
        """Get current widget values as parameters dictionary."""
        params = {
            "data_source": self.widgets["data_source"].value,
            "selected_file_paths": self.selected_file_paths.copy(),
            "processing_parameter": self.widgets["processing_param"].value,
            "has_observations": self.widgets["has_observations"].value == "yes",
            "observation_folder": self.selected_observation_folder,
        }

        if self.widgets["data_source"].value == "mars":
            grid_value_str = self.widgets["grid_resolution"].value.strip()
            if grid_value_str:
                try:
                    grid_value = float(grid_value_str)
                    grid = [grid_value, grid_value]
                except ValueError:
                    grid = None
            else:
                grid = None

            selected_models = list(self.widgets["model"].value)
            selected_steps = (
                list(self.widgets["forecast_steps"].value)
                if self.widgets["forecast_steps"].value
                else []
            )

            params.update(
                {
                    "param": list(self.widgets["param"].value),
                    "model": selected_models,
                    "start_date": self.widgets["start_date"].value,
                    "end_date": self.widgets["end_date"].value,
                    "time": self.widgets["time"].value,
                    "selected_steps": selected_steps,
                    "area": [
                        self.widgets["north"].value,
                        self.widgets["west"].value,
                        self.widgets["south"].value,
                        self.widgets["east"].value,
                    ],
                    "grid": grid,
                    "rd_class": self.widgets["rd_class"].value.strip(),
                    "rd_expver": self.widgets["rd_expver"].value.strip(),
                }
            )

        return params

    def update_parameter_dropdown(self, parameters):
        """Update the parameter dropdown with available parameters from loaded data."""
        if parameters:
            enhanced_parameters = []
            has_tp = has_cp = has_lsp = False

            for desc, param_code in parameters:
                enhanced_parameters.append((desc, param_code))
                if param_code == "tp":
                    has_tp = True
                elif param_code == "cp":
                    has_cp = True
                elif param_code == "lsp":
                    has_lsp = True

            existing_codes = [code for _, code in enhanced_parameters]

            if has_tp and "tp_deaccum" not in existing_codes:
                enhanced_parameters.append(
                    ("Total Precipitation (deaccumulated)", "tp_deaccum")
                )
            if has_cp and "cp_deaccum" not in existing_codes:
                enhanced_parameters.append(
                    ("Convective Precipitation (deaccumulated)", "cp_deaccum")
                )
            if has_lsp and "lsp_deaccum" not in existing_codes:
                enhanced_parameters.append(
                    ("Large Scale Precipitation (deaccumulated)", "lsp_deaccum")
                )

            self.widgets["processing_param"].options = enhanced_parameters
            self.widgets["processing_param"].disabled = False
            self.widgets["refresh_params_btn"].disabled = False
            self.widgets["processing_param"].value = enhanced_parameters[0][1]
        else:
            self.widgets["processing_param"].options = [
                ("No parameters available", "none")
            ]
            self.widgets["processing_param"].value = "none"
            self.widgets["processing_param"].disabled = True
            self.widgets["refresh_params_btn"].disabled = True

    def update_model_checkboxes_visibility(self, available_models):
        """Update model checkbox visibility based on available models.

        Args:
            available_models (dict): Dictionary of available models {model_key: dataset}

        """
        # Get all models from config
        models = self.config_manager.models

        for model_key in models.keys():
            model_short = model_key.split("-")[0]  # e.g., "aifs" from "aifs-single"
            checkbox_name = f"{model_short}_checkbox"

            if checkbox_name not in self.widgets:
                continue

            # Check if this model has data loaded
            has_data = any(
                model_short in key.lower() for key in available_models.keys()
            )

            # Always keep visible; disable (and uncheck) when no data is loaded.
            self.widgets[checkbox_name].layout.display = "block"
            self.widgets[checkbox_name].disabled = not has_data
            if not has_data:
                self.widgets[checkbox_name].value = False

    def update_bbox_from_map(self, bbox):
        """Update bounding box coordinates from map interaction."""
        try:
            if isinstance(bbox, tuple | list) and len(bbox) == 4:  # noqa: PLR2004
                min_lon, min_lat, max_lon, max_lat = bbox
                bbox_dict = {
                    "north": max_lat,
                    "south": min_lat,
                    "east": max_lon,
                    "west": min_lon,
                }
            elif isinstance(bbox, dict):
                bbox_dict = bbox
            else:
                print(f"Error: Unsupported bbox format: {type(bbox)}")
                return

            if hasattr(self, "map_handler") and self.map_handler:
                self.map_handler.set_current_bbox_and_update_ui(bbox_dict=bbox_dict)
            else:
                self._update_bbox_widgets_direct(bbox_dict)

        except Exception as e:
            print(f"Error in update_bbox_from_map: {e}")

    def trigger_observation_bbox_update(self):
        """Trigger observation station update when bbox changes."""
        try:
            if (
                self.callbacks
                and hasattr(self.callbacks, "observation_stations_gdf")
                and self.callbacks.observation_stations_gdf is not None
            ):
                bbox = [
                    self.widgets["west"].value,
                    self.widgets["south"].value,
                    self.widgets["east"].value,
                    self.widgets["north"].value,
                ]
                self.callbacks.update_observation_stations_for_bbox(bbox)
        except Exception as e:
            print(f"Error triggering observation bbox update: {e}")

    def can_proceed_with_plotting(self):
        """Check if plotting can proceed based on validation status."""
        if not self.widgets["has_observations"].value == "yes":
            return True
        if not self.selected_observation_folder:
            return True
        return self.observation_parameter_validated

    def detect_surface_variable_param(self, path):
        """Detect weather parameter from file path."""
        params = ["10ff", "10fg", "2d", "2t", "tp", "tmin", "tmax"]
        params = sorted(params, key=len, reverse=True)
        param_mapping = {"tmax": "mx2t", "tmin": "mn2t"}
        path_obj = Path(path)
        path_parts = path_obj.parts
        path_str = str(path_obj).lower()

        for param in params:
            if any(param in part.lower() for part in path_parts):
                return param_mapping.get(param, param)
            if param in path_str:
                return param_mapping.get(param, param)

        if path_obj.is_dir():
            try:
                geo_files = list(path_obj.glob("geo*"))
                if geo_files:
                    geo_file = geo_files[0]
                    geo_filename = geo_file.name.lower()
                    for param in params:
                        if param in geo_filename:
                            return param
            except (OSError, PermissionError):
                pass
        elif path_obj.is_file() and path_obj.name.lower().startswith("geo"):
            filename = path_obj.name.lower()
            for param in params:
                if param in filename:
                    return param

        return None

    def update_observation_retrieval_from_forecast_param(self, forecast_param):
        """Update observation retrieval settings when forecast parameter changes."""
        if self.widgets["retrieve_observations"].value == "retrieve":
            try:
                retriever = ObservationsRetriever()

                param_mapping = {
                    "2t": "2t",
                    "2d": "2d",
                    "tp": "tp",
                    "tp_deaccum": "tp",
                    "10ff": "10ff",
                    "10fg": "10fg",
                    "2t_24h_max": "tmax",
                    "2t_24h_min": "tmin",
                    "2d_24h_max": "2d",
                    "2d_24h_min": "2d",
                    "10ff_daily": "10ff",
                    "10fg_6h": "10fg",
                    "10fg_12h": "10fg",
                    "10fg_24h": "10fg",
                }

                obs_param = param_mapping.get(forecast_param)
                if not obs_param:
                    self._show_parameter_not_available(forecast_param)
                    return

                param_info = retriever.get_parameter_info(obs_param)

                if param_info["type"] == "instantaneous":
                    self._configure_instantaneous_parameter(obs_param, param_info)
                elif param_info["type"] == "period":
                    self._configure_period_parameter(
                        obs_param, param_info, forecast_param
                    )
                else:
                    self._show_unknown_parameter(obs_param)

            except ImportError:
                self._show_retriever_not_available()

    def update_period_dependent_settings_from_change(self, forecast_param, new_period):
        """Update period-dependent settings when user changes the period dropdown."""
        try:
            retriever = ObservationsRetriever()

            param_mapping = {
                "2t": "2t",
                "2d": "2d",
                "tp": "tp",
                "tp_deaccum": "tp",
                "10ff": "10ff",
                "10fg": "10fg",
                "2t_24h_max": "tmax",
                "2t_24h_min": "tmin",
                "2d_24h_max": "2d",
                "2d_24h_min": "2d",
                "10ff_daily": "10ff",
                "10fg_6h": "10fg",
                "10fg_12h": "10fg",
                "10fg_24h": "10fg",
            }

            obs_param = param_mapping.get(forecast_param)
            if not obs_param:
                return

            param_info = retriever.get_parameter_info(obs_param)
            self._update_period_dependent_settings(obs_param, param_info, new_period)
        except Exception as e:
            print(f"⚠️ Error updating period settings: {e}")

    def _validate_file_path(self, model_type):
        """Validate the entered file path for a specific model type."""
        file_path = self.selected_file_paths.get(model_type, "")

        if not file_path:
            return False

        try:
            if os.path.exists(file_path) and os.path.isfile(file_path):
                with open(file_path, "rb") as f:
                    f.read(1)
                return True
            else:
                return False
        except Exception:
            return False

    def _browse_for_file(self, model_type):
        """Enhanced file browsing that updates file path input widget."""
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

            file_path = filedialog.askopenfilename(
                title=f"Select {model_type.upper()} Weather Data File",
                filetypes=[
                    ("GRIB files", "*.grib *.grb *.grib2"),
                    ("All files", "*.*"),
                ],
                initialdir=os.path.expanduser("~"),
            )

            root.destroy()

            if file_path:
                self.widgets[f"file_path_input_{model_type}"].value = file_path
                self.selected_file_paths[model_type] = file_path

                file_name = os.path.basename(file_path)
                self.widgets[
                    f"selected_file_{model_type}"
                ].value = f'<p style="color: #2e7d32; font-weight: bold; margin: 2px 0;"> {file_name}</p>'

                if self.widgets["data_source"].value == "local":
                    # Check if any model file is selected
                    any_file_selected = any(
                        path is not None for path in self.selected_file_paths.values()
                    )
                    if any_file_selected:
                        self.widgets["load_both_btn"].disabled = False

                self._update_local_info_display()
            else:
                self._clear_file_selection(model_type)

        except Exception as e:
            self.widgets["local_info_display"].value = f"""
                <div style="background-color: #ffe8e8; padding: 10px; border-radius: 5px; margin: 5px 0;">
                    ❌ <strong>Error:</strong> {str(e)}<br>
                    Please try again or check file dialog support.
                </div>
            """

    def _browse_for_observation_folder(self, button):
        """Enhanced observation folder browser that updates path input widget."""
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
                self.widgets["obs_folder_path_input"].value = folder_path
                self.selected_observation_folder = folder_path

                folder_name = os.path.basename(folder_path)
                self.widgets[
                    "obs_folder_display"
                ].value = f'<p style="color: #2e7d32; font-weight: bold;">📁 {folder_name}</p>'

                self._perform_automatic_validation()

        except Exception as e:
            self.widgets["obs_info_display"].value = f"""
                <div style="background-color: #ffe8e8; padding: 10px; border-radius: 5px; margin: 5px 0;">
                    ❌ <strong>Error:</strong> {str(e)}<br>
                    Please try again or check folder dialog support.
                </div>
            """

    def _validate_observation_folder_path(self):
        """Validate the entered observation folder path."""
        folder_path = self.widgets["obs_folder_path_input"].value.strip()

        if not folder_path:
            return False

        try:
            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                try:
                    os.listdir(folder_path)
                    return True
                except PermissionError:
                    return False
            else:
                return False
        except Exception:
            return False

    def _perform_automatic_validation(self):
        """Perform automatic parameter validation when observation folder is selected."""
        try:
            if not self.selected_observation_folder:
                return

            # Check folder exists and contains GEO files
            folder_path = self.selected_observation_folder
            if not os.path.isdir(folder_path):
                StatusMessageHandler.show_obs_error(
                    self.widgets["obs_info_display"],
                    f"❌ Observation folder does not exist:<br>"
                    f"<code>{folder_path}</code>",
                )
                self.observation_parameter_validated = False
                return

            from helpers.stations_manipulating import GeoDataProcessor
            geo_files = GeoDataProcessor.get_geo_files(folder_path)
            if not geo_files:
                StatusMessageHandler.show_obs_error(
                    self.widgets["obs_info_display"],
                    f"❌ No observation data files found in folder:<br>"
                    f"<code>{folder_path}</code><br>"
                    f"Expected files matching pattern: <code>*_obs_*.geo</code>",
                )
                self.observation_parameter_validated = False
                return

            selected_param = self.widgets["processing_param"].value

            if selected_param == "none":
                StatusMessageHandler.show_obs_warning(
                    self.widgets["obs_info_display"],
                    "⚠️ Please select a forecast parameter first before browsing observations.<br>"
                    "The observation data must match the selected forecast parameter.",
                )
                self.observation_parameter_validated = False
                return

            detected_param = self.detect_surface_variable_param(
                self.selected_observation_folder
            )

            if detected_param is None:
                StatusMessageHandler.show_obs_warning(
                    self.widgets["obs_info_display"],
                    f"⚠️ Could not automatically detect parameter from observation folder.<br>"
                    f"Please verify manually that your observation data matches parameter: <strong>{selected_param}</strong>",
                )
                self.observation_parameter_validated = False
                return

            parameter_matches = False

            # Map forecast param to expected obs param for comparison
            forecast_to_obs = {
                "2t": "2t",
                "2d": "2d",
                "tp": "tp",
                "tp_deaccum": "tp",
                "10ff": "10ff",
                "10fg": "10fg",
                "2t_24h_max": "tmax",
                "2t_24h_min": "tmin",
                "2d_24h_max": "2d",
                "2d_24h_min": "2d",
                "10ff_daily": "10ff",
                "10fg_6h": "10fg",
                "10fg_12h": "10fg",
                "10fg_24h": "10fg",
                "10fg_48h": "10fg",
            }
            expected_obs = forecast_to_obs.get(selected_param, selected_param)
            if detected_param == expected_obs:
                parameter_matches = True

            if parameter_matches:
                self.observation_parameter_validated = True
                self.widgets["observations_checkbox"].disabled = False
                self.widgets["observations_checkbox"].value = True

                if self.callbacks:

                    def delayed_load():
                        time.sleep(0.1)
                        self.callbacks.load_observation_data_to_map()

                    thread = threading.Thread(target=delayed_load)
                    thread.daemon = True
                    thread.start()
            else:
                StatusMessageHandler.show_obs_error(
                    self.widgets["obs_info_display"],
                    f"❌ Parameter mismatch detected!<br>"
                    f"Selected forecast parameter: <strong>{selected_param}</strong><br>"
                    f"Detected observation parameter: <strong>{detected_param}</strong>",
                )
                self.observation_parameter_validated = False
                self.widgets["observations_checkbox"].value = False
                self.widgets["observations_checkbox"].disabled = True

        except Exception as e:
            StatusMessageHandler.show_obs_error(
                self.widgets["obs_info_display"],
                f"Error during automatic validation: {str(e)}",
            )
            self.observation_parameter_validated = False

    def _refresh_parameters(self, button):
        """Refresh parameter list from loaded datasets."""
        if self.callbacks:
            self.callbacks.refresh_available_parameters()

    def _reset_bbox(self, button):
        """Reset bounding box to default from config."""
        default_bbox = self.config_manager.get_default_bbox()
        self.widgets["north"].value = default_bbox["north"]
        self.widgets["west"].value = default_bbox["west"]
        self.widgets["south"].value = default_bbox["south"]
        self.widgets["east"].value = default_bbox["east"]

    def _clear_drawings(self, button):
        """Clear all drawings from the map."""
        if self.map_handler:
            self.map_handler.clear_drawings()

    def _reset_all(self, button):
        """Reset all widgets to default values."""
        self.widgets["data_source"].value = "mars"

        # Get defaults from config
        default_params = self.config_manager.get_default_parameters()
        model_options = self.config_manager.get_models_for_ui()

        self.widgets["param"].value = default_params
        self.widgets["model"].value = [key for _, key in model_options]

        self._clear_file_selection()

        if self.map_handler:
            self.map_handler.clear_drawings()
            self.map_handler.clear_all_points()
            self.map_handler.clear_observation_markers()

        for wkey in ("obs_time_explorer", "obs_colorbar"):
            if wkey in self.widgets:
                self.widgets[wkey].layout.display = "none"
        for wkey in ("obs_time_prev_btn", "obs_time_next_btn"):
            if wkey in self.widgets:
                self.widgets[wkey].disabled = True

    def get_vino_path(self):
        """Get the VINO executable path from the UI widget."""
        if "vino_path" in self.widgets:
            return self.widgets["vino_path"].value.strip()
        return None

    # Keep backward-compatible alias
    get_stvl_path = get_vino_path

    def _handle_retrieve_observations(self, button):
        """Handle observation retrieval button click."""
        try:
            # Validate required settings
            vino_path = self.get_vino_path()
            if not vino_path:
                StatusMessageHandler.show_obs_error(
                    self.widgets["obs_info_display"],
                    "❌ VINO executable path is not set. Please configure the path.",
                )
                return

            # Get the forecast parameter to determine obs parameter
            forecast_param = self.widgets["processing_param"].value
            if forecast_param == "none":
                StatusMessageHandler.show_obs_warning(
                    self.widgets["obs_info_display"],
                    "⚠️ Please select a forecast parameter first before retrieving observations.",
                )
                return

            # Map forecast param to obs param
            param_mapping = {
                "2t": "2t",
                "2d": "2d",
                "tp": "tp",
                "tp_deaccum": "tp",
                "10ff": "10ff",
                "10fg": "10fg",
                "2t_24h_max": "tmax",
                "2t_24h_min": "tmin",
                "2d_24h_max": "2d",
                "2d_24h_min": "2d",
                "10ff_daily": "10ff",
                "10fg_6h": "10fg",
                "10fg_12h": "10fg",
                "10fg_24h": "10fg",
            }

            obs_param = param_mapping.get(forecast_param)
            if not obs_param:
                StatusMessageHandler.show_obs_error(
                    self.widgets["obs_info_display"],
                    f"❌ No observation parameter available for forecast parameter: {forecast_param}",
                )
                return

            # Get retrieval settings from widgets
            sources_tuple = self.widgets["obs_sources"].value
            sources = " ".join(sources_tuple) if sources_tuple else "synop hdobs"

            start_date = self.widgets["obs_start_date"].value
            end_date = self.widgets["obs_end_date"].value
            output_dir = self.widgets["obs_output_dir"].value.strip()

            # Get period if applicable
            retriever = ObservationsRetriever(vino_path)
            param_info = retriever.get_parameter_info(obs_param)
            period = None
            if param_info["type"] == "period":
                period = self.widgets["obs_period"].value

            # Show progress
            StatusMessageHandler.show_obs_info(
                self.widgets["obs_info_display"],
                f"⏳ Retrieving {obs_param} observations from {sources}...",
            )

            # Setup the retriever in callbacks and execute
            if self.callbacks:
                self.callbacks.setup_observation_retrieval(vino_path)
                result = self.callbacks.retrieve_observations_with_parameter_logic(
                    parameter_name=obs_param,
                    start_date=start_date,
                    end_date=end_date,
                    sources=sources,
                    period=period,
                    output_dir=output_dir,
                )

                if result.get("success"):
                    output_path = result.get("output_dir", output_dir)
                    StatusMessageHandler.show_obs_success(
                        self.widgets["obs_info_display"],
                        f"✅ Successfully retrieved {obs_param} observations!<br>"
                        f"Output directory: <code>{output_path}</code>",
                    )

                    # Auto-set the observation folder and validate
                    self.selected_observation_folder = output_path
                    self.widgets["obs_folder_path_input"].value = output_path
                    self._perform_automatic_validation()
                else:
                    error_msg = result.get("error", "Unknown error")
                    StatusMessageHandler.show_obs_error(
                        self.widgets["obs_info_display"],
                        f"❌ Retrieval failed: {error_msg}",
                    )
            else:
                StatusMessageHandler.show_obs_error(
                    self.widgets["obs_info_display"],
                    "❌ Callbacks not initialized. Please restart the interface.",
                )

        except Exception as e:
            StatusMessageHandler.show_obs_error(
                self.widgets["obs_info_display"],
                f"❌ Error during observation retrieval: {str(e)}",
            )

    def _update_local_info_display(self):
        """Update the local info display with current file status."""
        status_lines = []

        # Get all models from config
        models = self.config_manager.models

        for model_key, model_info in models.items():
            model_short = model_key.split("-")[0]
            display_name = model_info.get("display_name", model_key)

            if self.selected_file_paths.get(model_short):
                status = "✅ Selected"
            else:
                status = "❌ Not selected"

            status_lines.append(
                f"<p><strong>{display_name} File:</strong> {status}</p>"
            )

        status_html = "\n".join(status_lines)

        self.widgets["local_info_display"].value = f"""
            <div style="background-color: #E0F7FA; padding: 10px; border-radius: 5px; margin: 5px 0; border-left: 4px solid #00BCD4;">
                <h4 style="margin-top: 0; color: #50DEA3;">📁 File Selection Status</h4>
                {status_html}
                <p><em>You can select one or more files for comparison.</em></p>
            </div>
        """

    def _clear_file_selection(self, model_type=None):
        """Clear file selection for specific model type or all."""
        if model_type:
            self.selected_file_paths[model_type] = None
            self.widgets[
                f"selected_file_{model_type}"
            ].value = f'<p style="color: #666; font-style: italic;">No {model_type.upper()} file selected</p>'
        else:
            # Clear all model files
            for model_key in self.config_manager.models.keys():
                model_short = model_key.split("-")[0]
                self.selected_file_paths[model_short] = None
                widget_name = f"selected_file_{model_short}"
                if widget_name in self.widgets:
                    self.widgets[
                        widget_name
                    ].value = f'<p style="color: #666; font-style: italic;">No {model_short.upper()} file selected</p>'

        # Check if any file is selected
        any_file_selected = any(
            path is not None for path in self.selected_file_paths.values()
        )

        self.widgets["load_both_btn"].disabled = not any_file_selected
        self._update_local_info_display()

    def _update_bbox_widgets_direct(self, bbox_dict):
        """Direct update of UI widgets with bbox coordinates."""
        try:
            self.observer_manager._disable_bbox_observers()

            widget_updates = {
                "north": float(bbox_dict.get("north", 0)),
                "south": float(bbox_dict.get("south", 0)),
                "east": float(bbox_dict.get("east", 0)),
                "west": float(bbox_dict.get("west", 0)),
            }

            for widget_name, value in widget_updates.items():
                if widget_name in self.widgets:
                    self.widgets[widget_name].value = value

        except Exception as e:
            print(f"Error in _update_bbox_widgets_direct: {e}")
        finally:
            self.observer_manager._enable_bbox_observers()

    def _configure_instantaneous_parameter(self, obs_param, param_info):
        """Configure UI for instantaneous parameters."""
        self.widgets["obs_period"].disabled = True
        self.widgets["obs_period"].description = "Period: (N/A)"

        times = param_info["default_times"]
        self.widgets[
            "obs_times_display"
        ].value = f"<p style='color: #2e7d32; font-size: 0.9em;'><b>Times:</b> {times} (3-hourly)</p>"

        base_dir = "./retrieved_observations"
        self.widgets["obs_output_dir"].value = f"{base_dir}/{obs_param}/{obs_param}_3h"

        self.widgets["obs_param_info"].value = f"""
            <div style="background-color: #E8F5E8; padding: 8px; border-radius: 4px; margin: 5px 0;">
                <p style="margin: 2px 0; color: #2E7D32;"><b>Parameter:</b> {obs_param} (instantaneous)</p>
                <p style="margin: 2px 0; color: #666; font-size: 0.9em;">Retrieved every 3 hours: 00, 03, 06, 09, 12, 15, 18, 21 UTC</p>
            </div>
        """

    def _configure_period_parameter(self, obs_param, param_info, forecast_param):
        """Configure UI for period-based parameters."""
        self.widgets["obs_period"].disabled = False
        self.widgets["obs_period"].description = "Period:"

        supported_periods = param_info["supported_periods"]
        period_options = [(f"{p} hours", str(p)) for p in supported_periods]
        self.widgets["obs_period"].options = period_options

        if obs_param in ["tmax", "tmin"]:
            default_period = "24"
        elif forecast_param in ["tp_deaccum"]:
            default_period = "24"
        else:
            default_period = str(supported_periods[0])

        self.widgets["obs_period"].value = default_period
        self._update_period_dependent_settings(obs_param, param_info, default_period)

    def _update_period_dependent_settings(self, obs_param, param_info, period):
        """Update times display and output directory based on selected period."""
        period_int = int(period)
        times = param_info["times_map"].get(period_int, "00")

        times_description = {
            1: "24 times daily (hourly)",
            6: "4 times daily: 00, 06, 12, 18 UTC",
            12: "2 times daily: 00, 12 UTC",
            24: "1 time daily: 00 UTC",
        }.get(period_int, f"Times: {times}")

        self.widgets[
            "obs_times_display"
        ].value = f"<p style='color: #2e7d32; font-size: 0.9em;'><b>Times:</b> {times} ({times_description})</p>"

        base_dir = "./retrieved_observations"
        self.widgets[
            "obs_output_dir"
        ].value = f"{base_dir}/{obs_param}/{obs_param}_{period}h"

        self.widgets["obs_param_info"].value = f"""
            <div style="background-color: #E8F5E8; padding: 8px; border-radius: 4px; margin: 5px 0;">
                <p style="margin: 2px 0; color: #2E7D32;"><b>Parameter:</b> {obs_param} ({period}h accumulated)</p>
                <p style="margin: 2px 0; color: #666; font-size: 0.9em;">{times_description}</p>
            </div>
        """

    def _show_parameter_not_available(self, forecast_param):
        """Show message when observation parameter is not available."""
        self.widgets["obs_param_info"].value = f"""
            <div style="background-color: #FFF3E0; padding: 8px; border-radius: 4px; margin: 5px 0; border-left: 4px solid #FF9800;">
                <p style="margin: 2px 0; color: #E65100;"><b>Parameter Not Available</b></p>
                <p style="margin: 2px 0; color: #666; font-size: 0.9em;">No observation data available for forecast parameter: {forecast_param}</p>
            </div>
        """

    def _show_unknown_parameter(self, obs_param):
        """Show message for unknown parameters."""
        self.widgets["obs_param_info"].value = f"""
            <div style="background-color: #FFF3E0; padding: 8px; border-radius: 4px; margin: 5px 0;">
                <p style="margin: 2px 0; color: #F57C00;"><b>Unknown Parameter</b></p>
                <p style="margin: 2px 0; color: #666; font-size: 0.9em;">Parameter {obs_param} configuration unknown</p>
            </div>
        """

    def _show_retriever_not_available(self):
        """Show message when retriever is not available."""
        self.widgets["obs_param_info"].value = """
            <div style="background-color: #ffebee; padding: 8px; border-radius: 4px; margin: 5px 0;">
                <p style="margin: 2px 0; color: #c62828;"><b>Retriever Not Available</b></p>
                <p style="margin: 2px 0; color: #666; font-size: 0.9em;">Cannot configure parameter-specific settings</p>
            </div>
        """
