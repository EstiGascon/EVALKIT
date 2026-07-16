import traceback
from typing import Any

from helpers.data_acquisition import ForecastDataLoader
from helpers.forecast_data_processor import ForecastDataProcessor
from helpers.plotting.plotting import PlottingManager
from helpers.widgets.callbacks.callbacks_data_management import DataManagement
from helpers.widgets.callbacks.callbacks_observation_handler import ObservationHandler
from helpers.widgets.callbacks.callbacks_parameter_processor import ParameterProcessor
from helpers.widgets.callbacks.callbacks_plotting_manager import (
    PlottingManager as CallbacksPlottingManager,
)
from helpers.widgets.status_message_handler import StatusMessageHandler

from .callbacks.callbacks_validation_helper import ValidationHelper


class TimeseriesCallbacks:
    """Callback handler for weather data UI interactions."""

    def __init__(self, ui_instance):
        """Initialize callbacks with reference to UI instance."""
        self.ui = ui_instance
        self.data_loader = ForecastDataLoader()
        self.map_handler = None
        self.loaded_datasets = {}
        self.forecast_processor = ForecastDataProcessor()
        self.plotting_manager = PlottingManager()
        self.wind_speed_processor = None
        self.temperature_processor = None
        self.multi_point_data = {}

        self.observation_processor = None
        self.observation_stations_gdf = None
        self.observation_timeseries_df = None
        self.observation_loaded_parameter = None
        self.observation_markers = {}
        self.original_observation_stations_gdf = None
        self.current_filtered_stations = None

        self.observations_retriever = None

        self._calculated_datasets = {}

        self.data_management = DataManagement(self)
        self.observation_handler = ObservationHandler(self)
        self.parameter_processor = ParameterProcessor(self)
        self.plotting_manager_callbacks = CallbacksPlottingManager(self)
        self.validation_helper = ValidationHelper(self)

        self._setup_precipitation_observers()
        self._show_initial_empty_plot()

    def _show_initial_empty_plot(self):
        """Show empty plot when interface first loads."""
        return self.plotting_manager_callbacks._show_initial_empty_plot()

    def _check_validation_before_plotting(self) -> bool:
        """Check if plotting can proceed based on parameter validation."""
        return self.validation_helper._check_validation_before_plotting()

    def _add_observation_data(self, point_data, station_id, selected_param=None):
        """Add observation data with unit handling."""
        return self.observation_handler._add_observation_data(point_data, station_id, selected_param)

    def _create_unified_plot(self, parameter_name):
        """Create plot with time period mismatch detection."""
        return self.plotting_manager_callbacks._create_unified_plot(parameter_name)

    def _check_for_time_period_mismatches(self):
        """Check if any points have forecast models with no common time period."""
        return self.validation_helper._check_for_time_period_mismatches()

    def _check_for_limited_coverage(self):
        """Return True when every model has only a single-step (zero-duration) dataset."""
        return self.validation_helper._check_for_limited_coverage()

    def setup_observation_retrieval(self, vino_path=None):
        """Initialize the observation retrieval system with configurable path."""
        return self.observation_handler.setup_observation_retrieval(vino_path)

    def _show_time_period_mismatch_error(self):
        """Show detailed error message about time period mismatch in UI."""
        return self.validation_helper._show_time_period_mismatch_error()

    def _create_time_period_error_plot(self, parameter_name):
        """Create a user-friendly error plot for time period mismatches."""
        return self.plotting_manager_callbacks._create_time_period_error_plot(
            parameter_name
        )

    def _create_placeholder_plot(self, num_points, message):
        """Create placeholder plot with message."""
        return self.plotting_manager_callbacks._create_placeholder_plot(
            num_points, message
        )

    def _get_selected_models(self):
        """Get currently selected models from UI checkboxes."""
        return self.data_management._get_selected_models()

    def setup_wind_speed_processing(self):
        """Initialize wind speed processor if needed."""
        return self.parameter_processor.setup_wind_speed_processing()

    def setup_temperature_processing(self):
        """Initialize temperature processor if needed."""
        return self.parameter_processor.setup_temperature_processing()

    def on_model_selection_change(self):
        """Handle when model selection checkboxes change."""
        selected_param = self.ui.widgets["processing_param"].value
        if selected_param != "none" and self.multi_point_data:
            self._create_unified_plot(selected_param)

    def on_multi_point_update(self, selected_points):
        """Multi-point update handler."""
        return self.parameter_processor.on_multi_point_update(selected_points)

    def on_add_manual_point_click(self, button):
        """Handle manual point addition from lat/lon inputs."""
        return self.parameter_processor.on_add_manual_point_click(button)

    def _process_wind_gust_multi_points(self, selected_points, all_datasets, period):
        """Process multiple points for wind gust with rolling maximum."""
        return self.parameter_processor._process_wind_gust_multi_points(
            selected_points, all_datasets, period
        )

    def setup_wind_gust_processing(self):
        """Initialize wind gust processor if needed."""
        return self.parameter_processor.setup_wind_gust_processing()

    def _process_daily_wind_speed_multi_points(self, selected_points, all_datasets):
        """Process multiple points for daily mean wind speed calculation."""
        return self.parameter_processor._process_daily_wind_speed_multi_points(
            selected_points, all_datasets
        )

    def _process_temperature_multi_points(
        self, selected_points, all_datasets, selected_param
    ):
        """Process multiple points for temperature 24h max/min calculation."""
        return self.parameter_processor._process_temperature_multi_points(
            selected_points, all_datasets, selected_param
        )

    def on_preview_click(self, button):
        """Handle preview button click."""
        try:
            params = self.ui.get_parameters()
            preview_html = self._format_preview_info(params)
            self.ui.widgets["mars_info_display"].value = preview_html
        except Exception as e:
            StatusMessageHandler.show_error(
                self.ui.widgets["mars_info_display"]
                if self.ui.widgets["data_source"].value == "mars"
                else self.ui.widgets["local_info_display"],
                f"Preview error: {str(e)}",
            )

    def on_retrieve_click(self, button):
        """Handle retrieve data button click for multiple models."""
        return self.data_management.on_retrieve_click(button)

    def retrieve_observations_with_parameter_logic(  # noqa: PLR0913
        self,
        parameter_name,
        start_date,
        end_date,
        sources="synop hdobs",
        period=None,
        output_dir=None,
    ):
        """Retrieve observations using parameter-specific logic."""
        return self.observation_handler.retrieve_observations_with_parameter_logic(
            parameter_name, start_date, end_date, sources, period, output_dir
        )

    def _handle_multiple_model_retrieval_results(
        self, retrieval_results, successful_retrievals
    ):
        """Handle results from multiple model retrievals."""
        return self.data_management._handle_multiple_model_retrieval_results(
            retrieval_results, successful_retrievals
        )

    def on_load_both_files_click(self, button):
        """Handle load both files button click with validation."""
        return self.data_management.on_load_both_files_click(button)

    def fit_map_to_bbox(self):
        """Manually fit map to current bounding box."""
        return self.data_management.fit_map_to_bbox()

    def force_refresh_unit_display(self):
        """Force refresh of unit display after parameters are loaded."""
        return self.data_management.force_refresh_unit_display()

    def refresh_available_parameters(self):
        """Refresh parameters in the list."""
        return self.data_management.refresh_available_parameters()

    def _setup_precipitation_observers(self):
        """Set up observers for precipitation widgets."""
        return self.parameter_processor._setup_precipitation_observers()

    def _extract_parameters_from_dataset(self, dataset, model_key: str) -> list[str]:
        """Parameter extraction that includes calculated parameters."""
        return self.data_management._extract_parameters_from_dataset(dataset, model_key)

    def load_observation_data_to_map(self):
        """Load observation data."""
        return self.observation_handler.load_observation_data_to_map()

    def _validate_forecast_observation_time_range(
        self, all_datasets, start_obs_date, end_obs_date
    ):
        """Validate that forecast time range is contained within observation time range."""
        return self.validation_helper._validate_forecast_observation_time_range(
            all_datasets, start_obs_date, end_obs_date
        )

    def _extract_time_range_from_dataset(self, dataset, model_name):
        """Extract time range from a forecast dataset."""
        return self.validation_helper._extract_time_range_from_dataset(
            dataset, model_name
        )

    def _create_unified_observation_markers(self, filtered_stations_gdf):
        """Create observation markers using unified map handler."""
        time_index = getattr(self, "_obs_time_index", 0)
        return self.observation_handler._create_unified_observation_markers(
            filtered_stations_gdf, time_index=time_index
        )

    def _create_observation_popup_info(self, station_id, station_info):
        """Create popup information for observation station."""
        return self.observation_handler._create_observation_popup_info(
            station_id, station_info
        )

    def _load_observation_timeseries(self):
        """Load observation timeseries data for loaded stations."""
        return self.observation_handler._load_observation_timeseries()

    def _extract_observation_time_range(self):
        """Extract only start and end dates from observation folder without loading full data."""
        return self.observation_handler._extract_observation_time_range()

    def _filter_stations_by_bbox(self, stations_gdf, bbox):
        """Filter stations by bounding box coordinates."""
        return self.observation_handler._filter_stations_by_bbox(stations_gdf, bbox)

    def update_observation_stations_for_bbox(self, bbox):
        """Update observation stations display based on new bbox."""
        return self.observation_handler.update_observation_stations_for_bbox(bbox)

    def on_bbox_coordinates_changed(self, change):
        """Handle automatic bounding box coordinate changes from UI widgets."""
        try:
            if not self.map_handler:
                return
            try:
                north = float(self.ui.widgets["north"].value)
                south = float(self.ui.widgets["south"].value)
                east = float(self.ui.widgets["east"].value)
                west = float(self.ui.widgets["west"].value)
            except (ValueError, TypeError, KeyError) as e:
                print(f"Error reading coordinate values: {e}")
                return

            self.map_handler.update_bbox_visualization()

            if self.observation_stations_gdf is not None:
                bbox = [west, south, east, north]
                self.update_observation_stations_for_bbox(bbox)

        except Exception as e:
            print(f"Error in on_bbox_coordinates_changed: {e}")

    def on_map_bbox_drawn(self, bbox):
        """Handle when a bounding box is drawn on the map."""
        try:
            if not bbox:
                return

            if isinstance(bbox, tuple | list) and len(bbox) == 4:  # noqa: PLR2004
                min_lon, min_lat, max_lon, max_lat = bbox
                bbox_formatted = [min_lon, min_lat, max_lon, max_lat]
            elif isinstance(bbox, dict):
                bbox_formatted = [
                    bbox.get("west", bbox.get("min_lon", 0)),
                    bbox.get("south", bbox.get("min_lat", 0)),
                    bbox.get("east", bbox.get("max_lon", 0)),
                    bbox.get("north", bbox.get("max_lat", 0)),
                ]
            else:
                print(f"❌ Unsupported bbox format: {type(bbox)}")
                return

            if self.map_handler:
                self.ui.widgets["west"].value = bbox_formatted[0]
                self.ui.widgets["south"].value = bbox_formatted[1]
                self.ui.widgets["east"].value = bbox_formatted[2]
                self.ui.widgets["north"].value = bbox_formatted[3]

        except Exception as e:
            print(f"❌ Error in on_map_bbox_drawn: {e}")
            traceback.print_exc()

    def setup_map_drawing_callback(self):
        """Set up callback for map drawing events."""
        try:
            if not self.map_handler:
                print("⚠️ No map handler available for setting up drawing callback")
                return

            if hasattr(self.map_handler, "map_widget") and hasattr(
                self.map_handler.map_widget, "on_interaction"
            ):

                def on_map_interaction(**kwargs):
                    if (
                        kwargs.get("type") == "draw"
                        and kwargs.get("action") == "created"
                    ):
                        geometry = kwargs.get("geo_json", {}).get("geometry", {})
                        if geometry.get("type") == "Polygon":
                            coordinates = geometry.get("coordinates", [[]])[0]
                            if len(coordinates) >= 4:  # noqa: PLR2004
                                lons = [coord[0] for coord in coordinates]
                                lats = [coord[1] for coord in coordinates]
                                bbox = [min(lons), min(lats), max(lons), max(lats)]
                                print(f"🎯 Bounding box drawn: {bbox}")
                                self.on_map_bbox_drawn(bbox)

                self.map_handler.map_widget.on_interaction(on_map_interaction)
            else:
                print("⚠️ Map widget doesn't support interaction callbacks")

        except Exception as e:
            print(f"❌ Error setting up map drawing callback: {e}")

    def _format_preview_info(self, params):
        """Format preview information as HTML."""
        return self.data_management._format_preview_info(params)

    def _validate_mars_params(self, params):
        """Validate MARS parameters for multiple models."""
        return self.validation_helper._validate_mars_params(params)

    def _handle_retrieval_result(self, result):
        """Handle Retrieval result."""
        return self.data_management._handle_retrieval_result(result)

    def _is_load_successful(self, result):
        """Enhanced load success checker with better detection logic."""
        return self.data_management._is_load_successful(result)

    def _update_load_summary_display(self, results):
        """Update the local info display with loading summary."""
        return self.data_management._update_load_summary_display(results)

    def get_all_datasets(self):
        """Get all loaded datasets."""
        return self.data_management.get_all_datasets()

    def get_dataset(self, model_key: str = None):
        """Get the loaded dataset(s)."""
        return self.data_management.get_dataset(model_key)

    def _process_wind_speed_multi_points(self, selected_points, all_datasets):
        """Process multiple points for wind speed calculation using meteorological calculations module."""
        return self.parameter_processor._process_wind_speed_multi_points(
            selected_points, all_datasets
        )

    def _process_standard_multi_points(
        self, selected_points, all_datasets, selected_param
    ):
        """Process multiple points for standard parameters (including original tp)."""
        return self.parameter_processor._process_standard_multi_points(
            selected_points, all_datasets, selected_param
        )

    def update_precipitation_interval(self, interval: int):
        """Update precipitation processing for new interval (only for tp_deaccum)."""
        return self.parameter_processor.update_precipitation_interval(interval)

    def update_precipitation_display_mode(self, show_all: bool):
        """Update precipitation display to show all intervals or just selected one (only for tp_deaccum)."""
        return self.parameter_processor.update_precipitation_display_mode(show_all)

    def setup_callbacks_after_ui_ready(self):
        """Set up callback that includes precipitation processing."""
        return self.parameter_processor.setup_callbacks_after_ui_ready()

    def setup_parameter_observer(self):
        """Parameter observer setup for wind speed and precipitation."""
        return self.parameter_processor.setup_parameter_observer()

    def get_available_precipitation_intervals(
        self, model_name: str = None
    ) -> dict[str, list[str]]:
        """Get available precipitation intervals for models."""
        return self.parameter_processor.get_available_precipitation_intervals(
            model_name
        )

    def setup_precipitation_processing(self):
        """Initialize precipitation processor if needed."""
        return self.parameter_processor.setup_precipitation_processing()

    def on_parameter_selection_change(self, change):
        """Parameter selection handler with separate TP and deaccumulation support."""
        return self.parameter_processor.on_parameter_selection_change(change)

    def _handle_temperature_parameter_selection(self, all_datasets: dict[str, Any]):
        """Handle when temperature 24h max/min parameters are selected."""
        return self.parameter_processor._handle_temperature_parameter_selection(
            all_datasets
        )

    def _handle_wind_speed_parameter_selection(self, all_datasets: dict[str, Any]):
        """Handle when wind speed parameter (10ff) is selected."""
        return self.parameter_processor._handle_wind_speed_parameter_selection(
            all_datasets
        )

    def _handle_precipitation_deaccum_parameter_selection(
        self, all_datasets: dict[str, Any], base_param: str = "tp"
    ):
        """Handle when deaccumulated precipitation parameter is selected."""
        return (
            self.parameter_processor._handle_precipitation_deaccum_parameter_selection(
                all_datasets, base_param
            )
        )

    def _handle_original_precipitation_parameter_selection(
        self, all_datasets: dict[str, Any]
    ):
        """Handle when original cumulative precipitation parameters (tp, cp, lsp) are selected."""
        return (
            self.parameter_processor._handle_original_precipitation_parameter_selection(
                all_datasets
            )
        )

    def _process_precipitation_deaccum_multi_points(
        self, selected_points, all_datasets, param_type="tp"
    ):
        """Process multiple points for precipitation deaccumulation - ENHANCED VERSION with user-selected intervals."""
        return self.parameter_processor._process_precipitation_deaccum_multi_points(
            selected_points, all_datasets, param_type
        )
