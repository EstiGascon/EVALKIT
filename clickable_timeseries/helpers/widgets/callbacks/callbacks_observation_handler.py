import os
import traceback

import numpy as np
import pandas as pd
from helpers.observations_retriever import ObservationsRetriever
from helpers.stations_manipulating import (
    DateTimeExtractor,
    GeoDataProcessor,
    StationCreator,
)
from helpers.widgets.status_message_handler import StatusMessageHandler
from shapely.geometry import Point, Polygon


class ObservationHandler:
    """Handles observation data loading, processing, and validation."""

    def __init__(self, callbacks_instance):
        """Initialize with reference to main callbacks instance."""
        self.callbacks = callbacks_instance

    @property
    def ui(self):
        """Shortcut to UI instance."""
        return self.callbacks.ui

    @property
    def observation_stations_gdf(self):
        """Shortcut to observation stations GDF."""
        return self.callbacks.observation_stations_gdf

    @observation_stations_gdf.setter
    def observation_stations_gdf(self, value):
        """Setter for observation stations GDF."""
        self.callbacks.observation_stations_gdf = value

    @property
    def observation_timeseries_df(self):
        """Shortcut to observation timeseries DF."""
        return self.callbacks.observation_timeseries_df

    @observation_timeseries_df.setter
    def observation_timeseries_df(self, value):
        """Setter for observation timeseries DF."""
        self.callbacks.observation_timeseries_df = value

    @property
    def original_observation_stations_gdf(self):
        """Shortcut to original observation stations GDF."""
        return self.callbacks.original_observation_stations_gdf

    @original_observation_stations_gdf.setter
    def original_observation_stations_gdf(self, value):
        """Setter for original observation stations GDF."""
        self.callbacks.original_observation_stations_gdf = value

    @property
    def current_filtered_stations(self):
        """Shortcut to current filtered stations."""
        return self.callbacks.current_filtered_stations

    @current_filtered_stations.setter
    def current_filtered_stations(self, value):
        """Setter for current filtered stations."""
        self.callbacks.current_filtered_stations = value

    @property
    def observation_processor(self):
        """Shortcut to observation processor."""
        return self.callbacks.observation_processor

    @observation_processor.setter
    def observation_processor(self, value):
        """Setter for observation processor."""
        self.callbacks.observation_processor = value

    @property
    def observations_retriever(self):
        """Shortcut to observations retriever."""
        return self.callbacks.observations_retriever

    @observations_retriever.setter
    def observations_retriever(self, value):
        """Setter for observations retriever."""
        self.callbacks.observations_retriever = value

    @property
    def map_handler(self):
        """Shortcut to map handler."""
        return self.callbacks.map_handler

    def _add_observation_data(self, point_data, station_id):  # noqa: PLR0911
        """Add observation data with unit handling."""
        try:
            if (
                self.observation_timeseries_df is None
                or station_id not in self.observation_timeseries_df.columns
            ):
                return False

            obs_data = self.observation_timeseries_df[station_id].dropna()
            if obs_data.empty:
                return False

            try:
                obs_values = pd.to_numeric(obs_data, errors="coerce").dropna()
                if obs_values.empty:
                    return False
            except Exception as e:
                print(
                    f"Error converting observation data to numeric for station {station_id}: {e}"
                )
                return False

            try:
                obs_df = pd.DataFrame(
                    {"forecast_value": obs_values.values},
                    index=obs_values.index,
                )

                if not isinstance(obs_df.index, pd.DatetimeIndex):
                    obs_df.index = pd.to_datetime(obs_df.index)

                point_data["forecast_data"]["Observations"] = obs_df
                point_data["distance_info"]["Observations"] = 0.0
                return True

            except Exception as e:
                print(
                    f"❌ Error creating observation DataFrame for station {station_id}: {e}"
                )
                return False

        except Exception as e:
            print(f"❌ Error adding observation data for station {station_id}: {e}")
            return False

    def setup_observation_retrieval(self, stvl_path=None):
        """Initialize the observation retrieval system with configurable path."""
        try:
            if stvl_path is None:
                stvl_path = self.ui.get_stvl_path()

            if not stvl_path:
                return False

            self.observations_retriever = ObservationsRetriever(stvl_path)
            return True

        except Exception as e:
            print(f"Error setting up observation retrieval: {e}")
            return False

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
        try:
            if not self.observations_retriever:
                if not self.setup_observation_retrieval():
                    return {
                        "success": False,
                        "error": "Could not initialize observation retriever",
                    }

            result = self.observations_retriever.retrieve(
                sources=sources,
                parameter=parameter_name,
                period=period,
                start_date=start_date.strftime("%Y%m%d")
                if hasattr(start_date, "strftime")
                else start_date,
                end_date=end_date.strftime("%Y%m%d")
                if hasattr(end_date, "strftime")
                else end_date,
                times=None,
                output_dir=output_dir,
            )

            param_info = self.observations_retriever.get_parameter_info(parameter_name)
            result["param_type"] = param_info["type"]

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "parameter": parameter_name,
                "output_dir": output_dir,
            }

    def load_observation_data_to_map(self):
        """Load observation data."""
        try:
            if not self.callbacks._check_validation_before_plotting():
                print("Observation data loading skipped due to parameter mismatch")
                return
            if not self.ui.selected_observation_folder:
                StatusMessageHandler.show_obs_error(
                    self.ui.widgets["obs_info_display"],
                    "No observation folder selected",
                )
                return

            if self.observation_processor is None:
                self.observation_processor = StationCreator()

            StatusMessageHandler.show_obs_info(
                self.ui.widgets["obs_info_display"], "Loading observation stations..."
            )

            all_datasets_forecast = self.callbacks.get_all_datasets()
            start_obs_date, end_obs_date = self._extract_observation_time_range()

            if start_obs_date and end_obs_date and all_datasets_forecast != {}:
                forecast_time_validation = (
                    self.callbacks._validate_forecast_observation_time_range(
                        all_datasets_forecast, start_obs_date, end_obs_date
                    )
                )

                if not forecast_time_validation["is_valid"]:
                    StatusMessageHandler.show_obs_error(
                        self.ui.widgets["obs_info_display"],
                        f"❌ Time Range Mismatch Detected!<br><br>"
                        f"<strong>Observation Data Time Range:</strong><br>"
                        f"&nbsp;&nbsp;Start: {start_obs_date.strftime('%Y-%m-%d %H:%M:%S')}<br>"
                        f"&nbsp;&nbsp;End: {end_obs_date.strftime('%Y-%m-%d %H:%M:%S')}<br><br>"
                        f"<strong>Forecast Data Time Range:</strong><br>"
                        f"&nbsp;&nbsp;Start: {forecast_time_validation['forecast_start'].strftime('%Y-%m-%d %H:%M:%S')}<br>"
                        f"&nbsp;&nbsp;End: {forecast_time_validation['forecast_end'].strftime('%Y-%m-%d %H:%M:%S')}<br><br>"
                        f"<strong>Issue:</strong> {forecast_time_validation['error_message']}<br><br>"
                        f"<strong>Suggestion:</strong><br>"
                        f"• Use observation data that covers the entire forecast period<br>"
                        f"• Observation range must start before {forecast_time_validation['forecast_start'].strftime('%Y-%m-%d %H:%M')}<br>"
                        f"• Observation range must end after {forecast_time_validation['forecast_end'].strftime('%Y-%m-%d %H:%M')}",
                    )
                    return

            all_stations = self.observation_processor.create_stations_geodataframe(
                self.ui.selected_observation_folder
            )

            if all_stations is None:
                StatusMessageHandler.show_obs_error(
                    self.ui.widgets["obs_info_display"],
                    "Failed to load observation stations",
                )
                return

            self.original_observation_stations_gdf = all_stations
            self.observation_stations_gdf = all_stations

            current_bbox = {
                "north": self.ui.widgets["north"].value,
                "south": self.ui.widgets["south"].value,
                "east": self.ui.widgets["east"].value,
                "west": self.ui.widgets["west"].value,
            }

            filtered_stations = self._filter_stations_by_bbox(
                all_stations, current_bbox
            )
            self.current_filtered_stations = filtered_stations

            self._load_observation_timeseries()

            self._create_unified_observation_markers(self.current_filtered_stations)

            total_count = len(all_stations)
            displayed_count = len(self.current_filtered_stations)

            if displayed_count < total_count:
                StatusMessageHandler.show_obs_success(
                    self.ui.widgets["obs_info_display"],
                    f"Loaded {total_count} observation stations<br>"
                    f"Showing {displayed_count} stations in current area<br>"
                    f"Click orange markers to select stations<br>"
                    f"Selected stations will change color to match plot<br>",
                )

        except Exception as e:
            traceback.print_exc()
            StatusMessageHandler.show_obs_warning(
                self.ui.widgets["obs_info_display"],
                f"Error loading observation data: {str(e)}",
            )

    def _create_unified_observation_markers(self, filtered_stations_gdf):
        """Create observation markers using unified map handler."""
        try:
            if (
                not self.map_handler
                or filtered_stations_gdf is None
                or len(filtered_stations_gdf) == 0
            ):
                return

            self.map_handler.clear_observation_markers()

            for station_id, station_info in filtered_stations_gdf.iterrows():
                marker_data = {
                    "station_id": station_id,
                    "lat": station_info["latitude"],
                    "lon": station_info["longitude"],
                    "type": "observation",
                    "color": "#949190",
                    "radius": 8,
                    "popup_info": self._create_observation_popup_info(
                        station_id, station_info
                    ),
                }

                self.map_handler.add_observation_marker(marker_data)

        except Exception as e:
            print(f"❌ Error creating unified observation markers: {e}")

    def _create_observation_popup_info(self, station_id, station_info):
        """Create popup information for observation station."""
        try:
            elevation = station_info.get("elevation")
            has_elevation = elevation is not None and not pd.isna(elevation)

            data_count = 0
            if (
                self.observation_timeseries_df is not None
                and station_id in self.observation_timeseries_df.columns
            ):
                data_count = self.observation_timeseries_df[station_id].count()

            popup_html = f"""
                <div style="width: 280px; color: black;">
                    <h4 style="margin-bottom: 10px;">🔬 Obs Station {station_id}</h4>
                    <p style="margin: 2px 0;"><strong>Location:</strong> {station_info["latitude"]:.3f}°N, {station_info["longitude"]:.3f}°E</p>
                    {f'<p style="margin: 2px 0;"><strong>Elevation:</strong> {elevation:.1f} m</p>' if has_elevation else ""}
                    <p style="margin: 2px 0;"><strong>Data Points:</strong> {data_count}</p>
                    <p style="margin: 2px 0; color: #FF6B35;"><strong>Type:</strong> Observation</p>
                    <p style="margin: 2px 0; font-size: 0.9em;"><em>Click to select/deselect</em></p>
                </div>
            """
            return popup_html

        except Exception as e:
            print(f"❌ Error creating popup info: {e}")
            return f"<div>Station {station_id}</div>"

    def _load_observation_timeseries(self):
        """Load observation timeseries data for loaded stations."""
        try:
            if self.observation_stations_gdf is None:
                return

            geo_processor = GeoDataProcessor()
            datetime_extractor = DateTimeExtractor()

            geo_files = geo_processor.get_geo_files(self.ui.selected_observation_folder)

            all_data = []
            station_ids = self.observation_stations_gdf.index.tolist()

            for file_path in geo_files:
                try:
                    filename = os.path.basename(file_path)
                    file_datetime = datetime_extractor.parse_filename_datetime(filename)

                    station_data = geo_processor.read_geo_file(file_path)

                    row_data = {"datetime": file_datetime}

                    for station_info in station_data:
                        station_id = station_info["stnid"]
                        if station_id in station_ids:
                            row_data[station_id] = station_info.get("value_0", np.nan)

                    all_data.append(row_data)

                except Exception as e:
                    print(f"⚠️ Error processing file {file_path}: {e}")
                    continue

            if all_data:
                self.observation_timeseries_df = pd.DataFrame(all_data)
                self.observation_timeseries_df.set_index("datetime", inplace=True)
                self.observation_timeseries_df.sort_index(inplace=True)

                start_obs_date = self.observation_timeseries_df.index.min()
                end_obs_date = self.observation_timeseries_df.index.max()

                return start_obs_date, end_obs_date

            else:
                print("⚠️ No timeseries data loaded")
                return None, None

        except Exception as e:
            print(f"❌ Error loading observation timeseries: {e}")

    def _extract_observation_time_range(self):
        """Extract only start and end dates from observation folder without loading full data."""
        try:
            if not self.ui.selected_observation_folder:
                print("⚠️ No observation folder path provided")
                return None, None

            geo_processor = GeoDataProcessor()
            datetime_extractor = DateTimeExtractor()

            geo_files = geo_processor.get_geo_files(self.ui.selected_observation_folder)

            if not geo_files:
                print("⚠️ No observation data files found in folder")
                return None, None

            file_datetimes = []

            for file_path in geo_files:
                try:
                    filename = os.path.basename(file_path)
                    file_datetime = datetime_extractor.parse_filename_datetime(filename)

                    if file_datetime:
                        file_datetimes.append(file_datetime)
                    else:
                        print(f"⚠️ Could not parse datetime from filename: {filename}")

                except Exception as e:
                    print(f"⚠️ Error parsing datetime from file {file_path}: {e}")
                    continue

            if file_datetimes:
                file_datetimes.sort()
                start_obs_date = min(file_datetimes)
                end_obs_date = max(file_datetimes)

                return start_obs_date, end_obs_date
            else:
                print("❌ No valid datetimes extracted from observation files")
                return None, None

        except Exception as e:
            print(f"❌ Error extracting observation time range: {e}")
            return None, None

    def _filter_stations_by_bbox(self, stations_gdf, bbox):
        """Filter stations by bounding box coordinates."""
        try:
            if isinstance(bbox, dict):
                min_lon = float(bbox.get("west", bbox.get("min_lon", -180)))
                min_lat = float(bbox.get("south", bbox.get("min_lat", -90)))
                max_lon = float(bbox.get("east", bbox.get("max_lon", 180)))
                max_lat = float(bbox.get("north", bbox.get("max_lat", 90)))
            elif isinstance(bbox, list | tuple) and len(bbox) == 4:  # noqa: PLR2004
                min_lon, min_lat, max_lon, max_lat = bbox
            else:
                print(f"❌ Unsupported bbox format: {type(bbox)} - {bbox}")
                return stations_gdf

            box = Polygon(
                [
                    (min_lon, min_lat),
                    (max_lon, min_lat),
                    (max_lon, max_lat),
                    (min_lon, max_lat),
                    (min_lon, min_lat),
                ]
            )

            filtered_stations = []
            for station_id, station_row in stations_gdf.iterrows():
                station_point = Point(station_row["longitude"], station_row["latitude"])
                if box.contains(station_point) or box.touches(station_point):
                    filtered_stations.append(station_id)

            filtered_gdf = stations_gdf.loc[filtered_stations]
            return filtered_gdf

        except Exception as e:
            print(f"❌ Error filtering stations by bbox: {e}")
            traceback.print_exc()
            return stations_gdf

    def update_observation_stations_for_bbox(self, bbox):
        """Update observation stations display based on new bbox."""
        try:
            if self.observation_stations_gdf is None:
                print("⚠️ No observation stations loaded")
                return

            source_stations = (
                self.original_observation_stations_gdf or self.observation_stations_gdf
            )

            filtered_stations = self._filter_stations_by_bbox(source_stations, bbox)

            if len(filtered_stations) == len(source_stations):
                print("⚠️ No filtering occurred - all stations still showing")

            self.current_filtered_stations = filtered_stations

            self._create_unified_observation_markers(filtered_stations)

            total_count = len(source_stations)
            filtered_count = len(filtered_stations)

            if filtered_count > 0:
                if filtered_count < total_count:
                    StatusMessageHandler.show_obs_success(
                        self.ui.widgets["obs_info_display"],
                        f"Filtered to {filtered_count} observation stations in selected area<br>"
                        f"Click orange markers to select stations<br>"
                        f"Modify bounding box to change station selection<br>"
                        f"Total available: {total_count} stations",
                    )
                else:
                    StatusMessageHandler.show_obs_success(
                        self.ui.widgets["obs_info_display"],
                        f"All {total_count} observation stations in selected area<br>"
                        f"Click orange markers to select stations<br>"
                        f"Draw a smaller bounding box to filter stations",
                    )
            else:
                StatusMessageHandler.show_obs_warning(
                    self.ui.widgets["obs_info_display"],
                    f"No observation stations found in selected area<br>"
                    f"Try expanding the bounding box to include more stations<br>"
                    f"Total available: {total_count} stations",
                )

        except Exception as e:
            print(f"❌ Error updating observation stations for bbox: {e}")
            traceback.print_exc()
