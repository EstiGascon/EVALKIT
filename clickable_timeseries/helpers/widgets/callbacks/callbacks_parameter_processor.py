import traceback
from typing import Any

from helpers.derived_variables.meteorological_calculations import (
    extract_wind_speed_timeseries,
)
from helpers.derived_variables.precipitation_processor import PrecipitationDataProcessor
from helpers.derived_variables.temperature_processor import TemperatureProcessor
from helpers.derived_variables.wind_gust_processor import WindGustProcessor
from helpers.derived_variables.wind_speed_processor import WindSpeedProcessor
from helpers.widgets.status_message_handler import StatusMessageHandler


class ParameterProcessor:
    """Handles parameter processing and multi-point analysis."""

    def __init__(self, callbacks_instance):
        """Initialize with reference to main callbacks instance."""
        self.callbacks = callbacks_instance

    @property
    def ui(self):
        """Shortcut to UI instance."""
        return self.callbacks.ui

    @property
    def multi_point_data(self):
        """Shortcut to multi point data."""
        return self.callbacks.multi_point_data

    @multi_point_data.setter
    def multi_point_data(self, value):
        """Setter for multi point data."""
        self.callbacks.multi_point_data = value

    @property
    def forecast_processor(self):
        """Shortcut to forecast processor."""
        return self.callbacks.forecast_processor

    @property
    def wind_speed_processor(self):
        """Shortcut to wind speed processor."""
        return self.callbacks.wind_speed_processor

    @wind_speed_processor.setter
    def wind_speed_processor(self, value):
        """Setter for wind speed processor."""
        self.callbacks.wind_speed_processor = value

    @property
    def temperature_processor(self):
        """Shortcut to temperature processor."""
        return self.callbacks.temperature_processor

    @temperature_processor.setter
    def temperature_processor(self, value):
        """Setter for temperature processor."""
        self.callbacks.temperature_processor = value

    def setup_wind_speed_processing(self):
        """Initialize wind speed processor if needed."""
        if (
            not hasattr(self.callbacks, "wind_speed_processor")
            or self.wind_speed_processor is None
        ):
            try:
                self.wind_speed_processor = WindSpeedProcessor()
                return True
            except ImportError:
                self.wind_speed_processor = None
                return False
        return True

    def setup_temperature_processing(self):
        """Initialize temperature processor if needed."""
        if (
            not hasattr(self.callbacks, "temperature_processor")
            or self.temperature_processor is None
        ):
            try:
                self.temperature_processor = TemperatureProcessor()
                return True
            except ImportError:
                self.temperature_processor = None
                return False
        return True

    def setup_wind_gust_processing(self):
        """Initialize wind gust processor if needed."""
        if (
            not hasattr(self.callbacks, "wind_gust_processor")
            or self.callbacks.wind_gust_processor is None
        ):
            try:
                self.callbacks.wind_gust_processor = WindGustProcessor()
                return True
            except ImportError:
                self.callbacks.wind_gust_processor = None
                return False
        return True

    def setup_precipitation_processing(self):
        """Initialize precipitation processor if needed."""
        if (
            not hasattr(self.callbacks, "precipitation_processor")
            or self.callbacks.precipitation_processor is None
        ):
            try:
                self.callbacks.precipitation_processor = PrecipitationDataProcessor()
                return True
            except ImportError:
                self.callbacks.precipitation_processor = None
                return False
        return True

    def on_multi_point_update(self, selected_points):  # noqa: PLR0912, PLR0915
        """Multi-point update handler."""
        try:
            if not self.callbacks._check_validation_before_plotting():
                return
            if not selected_points:
                StatusMessageHandler.show_plot_info(
                    self.ui.widgets["mars_info_display"],
                    " Click on the map to select forecast points",
                )
                self.callbacks._show_initial_empty_plot()
                return

            selected_param = self.ui.widgets["processing_param"].value
            if selected_param == "none":
                StatusMessageHandler.show_plot_info(
                    self.ui.widgets["mars_info_display"],
                    "Please select a parameter for processing first",
                )
                self.callbacks._create_placeholder_plot(
                    len(selected_points), "Please select a parameter"
                )
                return

            all_datasets = self.callbacks.get_all_datasets()
            if not all_datasets:
                StatusMessageHandler.show_plot_info(
                    self.ui.widgets["mars_info_display"],
                    "No forecast data loaded. Please retrieve or load data first",
                )
                self.callbacks._create_placeholder_plot(
                    len(selected_points), "No forecast data loaded"
                )
                return

            if self.callbacks.plotting_manager is None:
                if self.callbacks.map_handler:
                    self.callbacks.map_handler.sync_colors_with_plotting_manager(
                        self.callbacks.plotting_manager
                    )

            if selected_param in ["tp_deaccum", "cp_deaccum", "lsp_deaccum"]:
                base_param = selected_param.replace("_deaccum", "")
                self._process_precipitation_deaccum_multi_points(
                    selected_points, all_datasets, param_type=base_param
                )
            elif selected_param in ["tp", "cp", "lsp"]:
                self._process_standard_multi_points(
                    selected_points, all_datasets, selected_param
                )
            elif selected_param == "10ff":
                self._process_wind_speed_multi_points(selected_points, all_datasets)
            elif selected_param == "10ff_daily":
                self._process_daily_wind_speed_multi_points(
                    selected_points, all_datasets
                )
            elif selected_param.startswith("10fg"):
                if selected_param == "10fg":
                    self._process_standard_multi_points(
                        selected_points, all_datasets, selected_param
                    )
                else:
                    period = selected_param.replace("10fg_", "")
                    self._process_wind_gust_multi_points(
                        selected_points, all_datasets, period
                    )
            elif selected_param in [
                "2t_24h_max",
                "2t_24h_min",
                "2d_24h_max",
                "2d_24h_min",
            ]:
                self._process_temperature_multi_points(
                    selected_points, all_datasets, selected_param
                )
            else:
                self._process_standard_multi_points(
                    selected_points, all_datasets, selected_param
                )

            for point_id, point_info in selected_points.items():
                if (
                    point_info.get("type") == "observation"
                    and "station_id" in point_info
                ):
                    station_id = point_info["station_id"]

                    if point_id in self.multi_point_data:
                        success = self.callbacks._add_observation_data(
                            self.multi_point_data[point_id], station_id
                        )
                        if success:
                            if hasattr(self.ui.widgets, "observations_checkbox"):
                                self.ui.widgets[
                                    "observations_checkbox"
                                ].disabled = False
                        else:
                            print(
                                f"⚠️ Could not add observation data for station {station_id}"
                            )

            if self.multi_point_data:
                self.callbacks._create_unified_plot(selected_param)

            else:
                self.callbacks._create_placeholder_plot(
                    len(selected_points),
                    "No data could be extracted for selected points",
                )
                StatusMessageHandler.show_plot_info(
                    self.ui.widgets["mars_info_display"],
                    "❌ No data could be extracted for selected points",
                )

        except Exception as e:
            print(f"❌ Error in multi-point update: {e}")
            traceback.print_exc()
            if selected_points:
                self.callbacks._create_placeholder_plot(
                    len(selected_points), f"Error: {str(e)}"
                )

    def _process_wind_gust_multi_points(self, selected_points, all_datasets, period):
        """Process multiple points for wind gust with rolling maximum."""
        try:
            if not self.setup_wind_gust_processing():
                print("Wind gust processor not available")
                return

            success = self.callbacks.wind_gust_processor.process_wind_gust_datasets(
                all_datasets
            )
            if not success:
                print("Failed to process wind gust datasets")
                return

            self.multi_point_data = {}

            for point_id, point_info in selected_points.items():
                lat, lon = point_info["lat"], point_info["lon"]
                point_forecast_data = {}
                point_distance_info = {}

                for model_name in all_datasets.keys():
                    try:
                        gust_df, distance_km = (
                            self.callbacks.wind_gust_processor.extract_wind_gust_timeseries(
                                model_name, lat, lon, interval=period
                            )
                        )

                        if gust_df is not None and not gust_df.empty:
                            point_forecast_data[model_name] = gust_df
                            point_distance_info[model_name] = distance_km

                    except Exception as e:
                        print(f"Error processing wind gust for {model_name}: {e}")
                        continue

                if point_forecast_data:
                    self.multi_point_data[point_id] = {
                        "forecast_data": point_forecast_data,
                        "distance_info": point_distance_info,
                        "lat": lat,
                        "lon": lon,
                        "color": point_info["color"],
                        "label": point_info["label"],
                    }

        except Exception as e:
            print(f"Error in wind gust multi-point processing: {e}")
            traceback.print_exc()

    def _process_daily_wind_speed_multi_points(self, selected_points, all_datasets):
        """Process multiple points for daily mean wind speed calculation."""
        try:
            if not self.setup_wind_speed_processing():
                print("Wind speed processor not available")
                return

            success = self.wind_speed_processor.process_wind_speed_datasets(
                all_datasets
            )
            if not success:
                print("Failed to process wind speed datasets")
                return

            self.multi_point_data = {}

            for point_id, point_info in selected_points.items():
                lat, lon = point_info["lat"], point_info["lon"]
                point_forecast_data = {}
                point_distance_info = {}

                for model_name in all_datasets.keys():
                    try:
                        wind_speed_df, distance_km = (
                            self.wind_speed_processor.extract_wind_speed_timeseries(
                                model_name, lat, lon, interval="daily_mean"
                            )
                        )

                        if wind_speed_df is not None and not wind_speed_df.empty:
                            point_forecast_data[model_name] = wind_speed_df
                            point_distance_info[model_name] = distance_km
                        else:
                            print(
                                f"No daily wind speed data extracted for {model_name}"
                            )

                    except Exception as e:
                        print(
                            f"Error processing daily wind speed for {model_name}: {e}"
                        )
                        continue

                if point_forecast_data:
                    self.multi_point_data[point_id] = {
                        "forecast_data": point_forecast_data,
                        "distance_info": point_distance_info,
                        "lat": lat,
                        "lon": lon,
                        "color": point_info["color"],
                        "label": point_info["label"],
                    }

        except Exception as e:
            print(f"Error in daily wind speed multi-point processing: {e}")
            traceback.print_exc()

    def _process_temperature_multi_points(
        self, selected_points, all_datasets, selected_param
    ):
        """Process multiple points for temperature 24h max/min calculation."""
        try:
            if not self.setup_temperature_processing():
                print("Temperature processor not available")
                return

            success = self.temperature_processor.process_temperature_datasets(
                all_datasets
            )
            if not success:
                print("Failed to process temperature datasets")
                return

            self.multi_point_data = {}

            if selected_param.startswith("2t_24h"):
                base_param = "2t"
                interval = "24h_max" if "max" in selected_param else "24h_min"
            elif selected_param.startswith("2d_24h"):
                base_param = "2d"
                interval = "24h_max" if "max" in selected_param else "24h_min"
            else:
                print(f"Unsupported temperature parameter: {selected_param}")
                return

            for point_id, point_info in selected_points.items():
                lat, lon = point_info["lat"], point_info["lon"]
                point_forecast_data = {}
                point_distance_info = {}

                for model_name in all_datasets.keys():
                    try:
                        temp_df, distance_km = (
                            self.temperature_processor.extract_temperature_timeseries(
                                model_name, lat, lon, base_param, interval
                            )
                        )

                        if temp_df is not None and not temp_df.empty:
                            point_forecast_data[model_name] = temp_df
                            point_distance_info[model_name] = distance_km

                    except Exception as e:
                        print(f"Error processing temperature for {model_name}: {e}")
                        continue

                if point_forecast_data:
                    self.multi_point_data[point_id] = {
                        "forecast_data": point_forecast_data,
                        "distance_info": point_distance_info,
                        "lat": lat,
                        "lon": lon,
                        "color": point_info["color"],
                        "label": point_info["label"],
                    }

        except Exception as e:
            print(f"Error in temperature multi-point processing: {e}")
            traceback.print_exc()

    def _process_wind_speed_multi_points(self, selected_points, all_datasets):
        """Process multiple points for wind speed calculation using meteorological calculations module."""
        self.multi_point_data = {}

        for point_id, point_info in selected_points.items():
            lat, lon = point_info["lat"], point_info["lon"]
            point_forecast_data = {}
            point_distance_info = {}

            for model_name, dataset in all_datasets.items():
                try:
                    forecast_df, distance_km = extract_wind_speed_timeseries(
                        dataset, model_name, lat, lon, self.forecast_processor
                    )

                    if forecast_df is not None and not forecast_df.empty:
                        point_forecast_data[model_name] = forecast_df
                        point_distance_info[model_name] = distance_km
                    else:
                        print(f"⚠️ No wind speed data extracted for {model_name}")

                except Exception as e:
                    print(f"❌ Error processing wind speed for {model_name}: {e}")
                    traceback.print_exc()
                    continue

            if point_forecast_data:
                self.multi_point_data[point_id] = {
                    "forecast_data": point_forecast_data,
                    "distance_info": point_distance_info,
                    "lat": lat,
                    "lon": lon,
                    "color": point_info["color"],
                    "label": point_info["label"],
                }
            else:
                print(f"❌ No wind speed data available for point {point_id}")

    def _process_standard_multi_points(
        self, selected_points, all_datasets, selected_param
    ):
        """Process multiple points for standard parameters (including original tp)."""
        success = self.forecast_processor.process_datasets(all_datasets, selected_param)
        if not success:
            return

        self.multi_point_data = {}
        for point_id, point_info in selected_points.items():
            lat, lon = point_info["lat"], point_info["lon"]

            point_forecast_data = {}
            point_distance_info = {}

            for model_name in all_datasets.keys():
                try:
                    forecast_df, distance_km = (
                        self.forecast_processor.extract_forecast_timeseries(
                            model_name, lat, lon
                        )
                    )
                    if forecast_df is not None and not forecast_df.empty:
                        point_forecast_data[model_name] = forecast_df
                        point_distance_info[model_name] = distance_km

                except Exception as e:
                    print(
                        f"⚠️ Error extracting data for {model_name} at point {point_id}: {e}"
                    )
                    continue

            if point_forecast_data:
                self.multi_point_data[point_id] = {
                    "forecast_data": point_forecast_data,
                    "distance_info": point_distance_info,
                    "lat": lat,
                    "lon": lon,
                    "color": point_info["color"],
                    "label": point_info["label"],
                }

    def _process_precipitation_deaccum_multi_points(
        self, selected_points, all_datasets, param_type="tp"
    ):
        """Process multiple points for precipitation deaccumulation - ENHANCED VERSION with user-selected intervals."""
        try:
            if not self.setup_precipitation_processing():
                print("❌ Precipitation processor not available")
                return

            selected_interval = self.ui.widgets["precipitation_interval"].value
            intervals_to_process = [selected_interval]

            success = (
                self.callbacks.precipitation_processor.process_precipitation_datasets(
                    all_datasets, intervals_to_process, param_types=[param_type]
                )
            )

            if not success:
                print("❌ Failed to process datasets for precipitation")
                return

            self.multi_point_data = {}

            for point_id, point_info in selected_points.items():
                lat, lon = point_info["lat"], point_info["lon"]
                point_forecast_data = {}
                point_distance_info = {}

                for model_name in all_datasets.keys():
                    try:
                        precip_df, distance_km = (
                            self.callbacks.precipitation_processor.extract_precipitation_timeseries(
                                model_name, lat, lon, selected_interval, param_type
                            )
                        )

                        if precip_df is not None and not precip_df.empty:
                            if "precipitation_value" in precip_df.columns:
                                precip_df_renamed = precip_df.rename(
                                    columns={"precipitation_value": "forecast_value"}
                                )
                            else:
                                precip_df_renamed = precip_df.copy()

                            point_forecast_data[model_name] = precip_df_renamed
                            point_distance_info[model_name] = distance_km
                        else:
                            print(
                                f"⚠️ No {param_type} data extracted for {model_name} at {selected_interval}h"
                            )

                    except Exception as e:
                        print(f"❌ Error processing {param_type} for {model_name}: {e}")
                        continue

                if point_forecast_data:
                    self.multi_point_data[point_id] = {
                        "forecast_data": point_forecast_data,
                        "distance_info": point_distance_info,
                        "lat": lat,
                        "lon": lon,
                        "color": point_info["color"],
                        "label": point_info["label"],
                    }
                else:
                    print(
                        f"❌ No deaccumulated {param_type} data available for point {point_id}"
                    )

        except Exception as e:
            print(
                f"❌ Error in {param_type} deaccumulation multi-point processing: {e}"
            )
            traceback.print_exc()

    def update_precipitation_interval(self, interval: int):
        """Update precipitation processing for new interval (only for tp_deaccum)."""
        selected_param = self.ui.widgets["processing_param"].value
        if selected_param != "tp_deaccum":
            print("⚠️ Not in deaccumulation mode, ignoring interval change")
            return

        if (
            not hasattr(self.callbacks, "precipitation_processor")
            or self.callbacks.precipitation_processor is None
        ):
            print("⚠️ No precipitation processor available")
            return

        all_datasets = self.callbacks.get_all_datasets()
        if not all_datasets:
            print("⚠️ No datasets available for reprocessing")
            return

    def update_precipitation_display_mode(self, show_all: bool):
        """Update precipitation display to show all intervals or just selected one (only for tp_deaccum)."""
        selected_param = self.ui.widgets["processing_param"].value
        if selected_param != "tp_deaccum":
            print("⚠️ Not in deaccumulation mode, ignoring display mode change")
            return

        if show_all:
            all_datasets = self.callbacks.get_all_datasets()
            if all_datasets and hasattr(self.callbacks, "precipitation_processor"):
                self.callbacks.precipitation_processor.process_precipitation_datasets(
                    all_datasets, [24, 12, 6]
                )

        if hasattr(self.callbacks, "multi_point_data") and self.multi_point_data:
            self.callbacks._create_unified_plot("tp_deaccum")

    def setup_callbacks_after_ui_ready(self):
        """Set up callback that includes precipitation processing."""
        try:
            self.setup_parameter_observer()
        except Exception as e:
            print(f"❌ Error setting up callbacks: {e}")

    def setup_parameter_observer(self):
        """Parameter observer setup for wind speed and precipitation."""
        try:
            if hasattr(self.ui.widgets["processing_param"], "_trait_notifiers"):
                self.ui.widgets["processing_param"]._trait_notifiers.get(
                    "value", []
                ).clear()

            self.ui.widgets["processing_param"].observe(
                self.on_parameter_selection_change, names="value"
            )

        except Exception as e:
            print(f"❌ Error setting up enhanced parameter observer: {e}")

    def get_available_precipitation_intervals(
        self, model_name: str = None
    ) -> dict[str, list[str]]:
        """Get available precipitation intervals for models."""
        if (
            not hasattr(self.callbacks, "precipitation_processor")
            or self.callbacks.precipitation_processor is None
        ):
            return {}

        return self.callbacks.precipitation_processor.get_available_intervals(
            model_name
        )

    def on_parameter_selection_change(self, change):
        """Parameter selection handler with separate TP and deaccumulation support."""
        try:
            selected_param = change["new"]

            all_datasets = self.callbacks.get_all_datasets()
            if not all_datasets:
                StatusMessageHandler.show_plot_info(
                    self.ui.widgets["mars_info_display"],
                    "No datasets loaded. Please load data first.",
                )
                return

            if selected_param in ["tp_deaccum", "cp_deaccum", "lsp_deaccum"]:
                base_param = selected_param.replace("_deaccum", "")
                self._handle_precipitation_deaccum_parameter_selection(
                    all_datasets, base_param
                )

            elif selected_param in ["tp", "cp", "lsp"]:
                self._handle_original_precipitation_parameter_selection(all_datasets)

            elif selected_param in ["10ff", "10ff_daily"]:
                self._handle_wind_speed_parameter_selection(all_datasets)
            elif selected_param.startswith("10fg"):
                self._handle_wind_gust_parameter_selection(all_datasets)
            elif selected_param in [
                "2t_24h_max",
                "2t_24h_min",
                "2d_24h_max",
                "2d_24h_min",
            ]:
                self._handle_temperature_parameter_selection(all_datasets)
            else:
                StatusMessageHandler.show_plot_info(
                    f"Parameter {selected_param} selected. Click on map points to analyze."
                )

        except Exception as e:
            print(f"❌ Error in parameter selection change: {e}")
            StatusMessageHandler.show_plot_info(
                self.ui.widgets["mars_info_display"],
                f"Error checking parameter requirements: {str(e)}",
            )

    def _handle_temperature_parameter_selection(self, all_datasets: dict[str, Any]):
        """Handle when temperature 24h max/min parameters are selected."""
        try:
            models_with_temp = []
            models_missing_temp = []

            for model_key, dataset in all_datasets.items():
                dataset_params = self.callbacks._extract_parameters_from_dataset(
                    dataset, model_key
                )

                has_2t = "2t" in dataset_params
                has_2d = "2d" in dataset_params

                if has_2t or has_2d:
                    models_with_temp.append(model_key)
                else:
                    models_missing_temp.append(model_key)

            if models_with_temp:
                self.setup_temperature_processing()
                print(f"Temperature processing available for: {models_with_temp}")

            if models_missing_temp:
                print(f"Models missing temperature data: {models_missing_temp}")

        except Exception as e:
            print(f"Error handling temperature parameter selection: {e}")

    def _handle_wind_speed_parameter_selection(self, all_datasets: dict[str, Any]):
        """Handle when wind speed parameter (10ff) is selected."""
        try:
            models_with_wind_components = []
            models_missing_wind_components = []

            for model_key, dataset in all_datasets.items():
                dataset_params = self.callbacks._extract_parameters_from_dataset(
                    dataset, model_key
                )

                has_u_component = "10u" in dataset_params
                has_v_component = "10v" in dataset_params

                if has_u_component and has_v_component:
                    models_with_wind_components.append(model_key)
                else:
                    models_missing_wind_components.append(model_key)
                    missing_components = []
                    if not has_u_component:
                        missing_components.append("10u")
                    if not has_v_component:
                        missing_components.append("10v")
                    print(
                        f"⚠️ {model_key} missing wind components: {missing_components}"
                    )

        except Exception as e:
            print(f"❌ Error handling wind speed parameter selection: {e}")

    def _handle_wind_gust_parameter_selection(self, all_datasets: dict[str, Any]):
        """Handle when wind gust parameter is selected."""
        try:
            models_with_wind_gust = []
            models_missing_wind_gust = []

            for model_key, dataset in all_datasets.items():
                dataset_params = self.callbacks._extract_parameters_from_dataset(
                    dataset, model_key
                )

                has_10fg = "10fg" in dataset_params

                if has_10fg:
                    models_with_wind_gust.append(model_key)
                else:
                    models_missing_wind_gust.append(model_key)

            if models_with_wind_gust:
                self.setup_wind_gust_processing()
                print(f"Wind gust processing available for: {models_with_wind_gust}")

            if models_missing_wind_gust:
                print(f"Models missing wind gust data: {models_missing_wind_gust}")

        except Exception as e:
            print(f"❌ Error handling wind gust parameter selection: {e}")

    def _handle_precipitation_deaccum_parameter_selection(
        self, all_datasets: dict[str, Any], base_param: str = "tp"
    ):
        """Handle when deaccumulated precipitation parameter is selected."""
        try:
            models_with_precip = []
            models_missing_precip = []

            param_names = {
                "tp": "total precipitation",
                "cp": "convective precipitation",
                "lsp": "large scale precipitation",
            }
            param_description = param_names.get(
                base_param, f"{base_param} precipitation"
            )

            for model_key, dataset in all_datasets.items():
                dataset_params = self.callbacks._extract_parameters_from_dataset(
                    dataset, model_key
                )

                if base_param in dataset_params:
                    models_with_precip.append(model_key)
                else:
                    models_missing_precip.append(model_key)

            if models_with_precip:
                print(f"Models with {param_description}: {models_with_precip}")
                self.setup_precipitation_processing()

            if models_missing_precip:
                print(f"Models missing {param_description}: {models_missing_precip}")

        except Exception as e:
            print(
                f"Error handling {base_param} deaccumulation parameter selection: {e}"
            )

    def _handle_original_precipitation_parameter_selection(
        self, all_datasets: dict[str, Any]
    ):
        """Handle when original cumulative precipitation parameters (tp, cp, lsp) are selected."""
        try:
            precipitation_params = ["tp", "cp", "lsp"]

            for param in precipitation_params:
                models_with_param = []
                models_missing_param = []

                for model_key, dataset in all_datasets.items():
                    dataset_params = self.callbacks._extract_parameters_from_dataset(
                        dataset, model_key
                    )
                    if param in dataset_params:
                        models_with_param.append(model_key)
                    else:
                        models_missing_param.append(model_key)

                if models_with_param:
                    print(f"Models with {param}: {models_with_param}")
                if models_missing_param:
                    print(f"Models missing {param}: {models_missing_param}")

        except Exception as e:
            print(f"Error handling original precipitation parameter selection: {e}")

    def _setup_precipitation_observers(self):
        """Set up observers for precipitation widgets."""

        def on_precipitation_interval_change(change):  # noqa: ARG001
            """Handle precipitation interval selection changes with immediate reprocessing."""
            selected_param = self.ui.widgets["processing_param"].value

            if (
                selected_param in ["tp_deaccum", "cp_deaccum", "lsp_deaccum"]
                and hasattr(self.callbacks, "multi_point_data")
                and self.multi_point_data
            ):
                if self.callbacks.map_handler:
                    selected_points = self.callbacks.map_handler.get_selected_points()
                    if selected_points:
                        all_datasets = self.callbacks.get_all_datasets()

                        base_param = selected_param.replace("_deaccum", "")

                        self._process_precipitation_deaccum_multi_points(
                            selected_points, all_datasets, param_type=base_param
                        )

                        self.callbacks._create_unified_plot(selected_param)
                    else:
                        print("No points selected for reprocessing")
                else:
                    print("No map handler available for reprocessing")
            else:
                print("No immediate reprocessing needed - waiting for point selection")

        if hasattr(self.ui.widgets, "precipitation_interval"):
            self.ui.widgets["precipitation_interval"].observe(
                on_precipitation_interval_change, names="value"
            )

    def on_add_manual_point_click(self, button):
        """Handle manual point addition from lat/lon inputs."""
        try:
            lat = self.ui.widgets["manual_lat_input"].value
            lon = self.ui.widgets["manual_lon_input"].value

            if not (-90 <= lat <= 90):  # noqa: PLR2004
                StatusMessageHandler.show_error(
                    self.ui.widgets["manual_coord_status"],
                    " Latitude must be between -90 and 90 degrees",
                )
                return

            if not (-180 <= lon <= 180):  # noqa: PLR2004
                StatusMessageHandler.show_error(
                    self.ui.widgets["manual_coord_status"],
                    " Longitude must be between -180 and 180 degrees",
                )
                return

            if self.callbacks.map_handler:
                bbox = self.callbacks.map_handler.get_current_bbox()
                if bbox:
                    if not (
                        bbox["south"] <= lat <= bbox["north"]
                        and bbox["west"] <= lon <= bbox["east"]
                    ):
                        return

            if self.callbacks.map_handler:
                success = self.callbacks.map_handler._add_unified_forecast_point(
                    lat, lon
                )

                if success:
                    self.callbacks.map_handler._update_unified_plot()

                    self.ui.widgets["manual_lat_input"].value = 0.0
                    self.ui.widgets["manual_lon_input"].value = 0.0
                else:
                    StatusMessageHandler.show_error(
                        self.ui.widgets["manual_coord_status"],
                        " Failed to add point to map. Point may be outside bbox.",
                    )
            else:
                StatusMessageHandler.show_error(
                    self.ui.widgets["manual_coord_status"], " Map handler not available"
                )

        except Exception as e:
            StatusMessageHandler.show_error(
                self.ui.widgets["manual_coord_status"], f" Error adding point: {str(e)}"
            )
