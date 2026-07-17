import os
import traceback
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
from helpers.observations_retriever import ObservationsRetriever
from helpers.stations_manipulating import (
    DateTimeExtractor,
    GeoDataProcessor,
    StationCreator,
)
from helpers.widgets.status_message_handler import StatusMessageHandler


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

    @property
    def observation_loaded_parameter(self):
        """Shortcut to observation loaded parameter."""
        return self.callbacks.observation_loaded_parameter

    @observation_loaded_parameter.setter
    def observation_loaded_parameter(self, value):
        """Setter for observation loaded parameter."""
        self.callbacks.observation_loaded_parameter = value

    # Mapping from forecast parameter to expected observation parameter
    FORECAST_TO_OBS_PARAM = {
        "2t": "2t",
        "2d": "2d",
        "tp": "tp",
        "tp_deaccum": "tp",
        "10ff": "10ff",
        "10fg": "10fg",
        "2t_24h_max": "mx2t",
        "2t_24h_min": "mn2t",
        "2d_24h_max": "2d",
        "2d_24h_min": "2d",
        "10ff_daily": "10ff",
        "10fg_6h": "10fg",
        "10fg_12h": "10fg",
        "10fg_24h": "10fg",
        "10fg_48h": "10fg",
    }

    # Equivalent names for the same parameter (different naming conventions)
    _OBS_PARAM_ALIASES: dict[str, str] = {
        "tmax": "mx2t",
        "tmin": "mn2t",
        "mx2t": "mx2t",
        "mn2t": "mn2t",
    }

    # Known observation parameter names for matching against GEO filenames
    KNOWN_OBS_PARAMS = ["10fg", "10ff", "mx2t", "mn2t", "tmax", "tmin", "2t", "2d", "tp"]

    @staticmethod
    def _extract_obs_parameter_from_geo_files(geo_files):
        """Extract the observation parameter from the first GEO filename.

        GEO filenames follow the pattern: {param}{period}_obs_{YYYYMMDDHH}.geo
        for period-based params (e.g. 10fg01, tp06) or {param}_obs_{YYYYMMDDHH}.geo
        for instantaneous params (e.g. 2t, 10ff).
        """
        if not geo_files:
            return None
        filename = os.path.basename(geo_files[0])
        parts = filename.split("_obs_")
        if len(parts) >= 2:
            prefix = parts[0]
            # Try to match against known param names (longest first to avoid
            # partial matches like "2t" matching before "2t" in "2t_24h")
            for param in sorted(ObservationHandler.KNOWN_OBS_PARAMS, key=len, reverse=True):
                if prefix == param or (prefix.startswith(param) and prefix[len(param):].isdigit()):
                    return param
            return prefix
        return None

    def _add_observation_data(self, point_data, station_id, selected_param=None):  # noqa: PLR0911
        """Add observation data with unit handling and parameter compatibility check."""
        try:
            if (
                self.observation_timeseries_df is None
                or station_id not in self.observation_timeseries_df.columns
            ):
                return False

            # Check parameter compatibility
            if selected_param and self.observation_loaded_parameter:
                expected_obs = self.FORECAST_TO_OBS_PARAM.get(selected_param)
                # Normalise both sides through the alias table so that
                # e.g. "tmax" and "mx2t" are treated as equivalent.
                def _normalise(p):
                    return self._OBS_PARAM_ALIASES.get(p, p)

                if expected_obs and _normalise(expected_obs) != _normalise(self.observation_loaded_parameter):
                    StatusMessageHandler.show_obs_warning(
                        self.ui.widgets["obs_info_display"],
                        f"⚠️ Parameter mismatch: loaded observations are for "
                        f"<b>{self.observation_loaded_parameter}</b>, but selected "
                        f"forecast parameter <b>{selected_param}</b> expects "
                        f"<b>{expected_obs}</b> observations.<br>"
                        f"Observation data will not be plotted.",
                    )
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

                # Apply temporal aggregation to match the forecast parameter
                obs_df = self._aggregate_observations(obs_df, selected_param)
                if obs_df is None or obs_df.empty:
                    return False

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

    # Mapping from selected forecast parameter to the aggregation that should
    # be applied to the raw observation time series so it matches the forecast.
    _OBS_AGGREGATION_RULES = {
        # cumulative precipitation (obs are per-period amounts, forecast is accumulated)
        "tp": {"method": "cumsum"},
        "cp": {"method": "cumsum"},
        "lsp": {"method": "cumsum"},
        # daily mean wind speed
        "10ff_daily": {"method": "mean", "period": "24h"},
        # N-hour rolling max wind gust
        "10fg_6h": {"method": "max", "period": "6h"},
        "10fg_12h": {"method": "max", "period": "12h"},
        "10fg_24h": {"method": "max", "period": "24h"},
        "10fg_48h": {"method": "max", "period": "48h"},
        # daily max / min temperature
        "2t_24h_max": {"method": "max", "period": "24h"},
        "2t_24h_min": {"method": "min", "period": "24h"},
        # daily max / min dewpoint
        "2d_24h_max": {"method": "max", "period": "24h"},
        "2d_24h_min": {"method": "min", "period": "24h"},
    }

    def _aggregate_observations(self, obs_df, selected_param):
        """Aggregate observation data to match the forecast parameter's temporal resolution.

        For derived parameters (daily mean, rolling max, daily extremes), the raw
        observation time series is resampled so it can be compared meaningfully
        with the already-aggregated forecast data.
        """
        if not selected_param:
            return obs_df

        rule = self._OBS_AGGREGATION_RULES.get(selected_param)
        if rule is None:
            # No aggregation needed (instantaneous or already matching)
            return obs_df

        method = rule["method"]
        period = rule.get("period")

        try:
            obs_df = obs_df.sort_index()

            # Cumulative sum: observations are per-period amounts, forecast is
            # accumulated from the start of the run.
            if method == "cumsum":
                cumulated = obs_df["forecast_value"].cumsum()
                return pd.DataFrame({"forecast_value": cumulated.values}, index=cumulated.index)

            # Resample to the target period with closed='right' and label='right'
            # so that, e.g., the 24h window ending at 00 UTC is labelled at 00 UTC,
            # matching how forecast daily values are anchored.
            resampler = obs_df["forecast_value"].resample(period, closed="right", label="right")

            if method == "mean":
                aggregated = resampler.mean()
            elif method == "max":
                aggregated = resampler.max()
            elif method == "min":
                aggregated = resampler.min()
            else:
                return obs_df

            aggregated = aggregated.dropna()
            if aggregated.empty:
                return obs_df

            return pd.DataFrame({"forecast_value": aggregated.values}, index=aggregated.index)

        except Exception as e:
            print(f"⚠️ Observation aggregation failed for {selected_param}: {e}")
            return obs_df

    def setup_observation_retrieval(self, vino_path=None):
        """Initialize the observation retrieval system with configurable path."""
        try:
            if vino_path is None:
                vino_path = self.ui.get_vino_path()

            if not vino_path:
                return False

            self.observations_retriever = ObservationsRetriever(vino_path)
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

            # Cache geo files list to avoid duplicate glob calls
            geo_files = GeoDataProcessor.get_geo_files(
                self.ui.selected_observation_folder
            )

            all_datasets_forecast = self.callbacks.get_all_datasets()
            start_obs_date, end_obs_date = self._extract_observation_time_range(
                geo_files=geo_files
            )

            forecast_time_validation = {}
            if start_obs_date and end_obs_date and all_datasets_forecast != {}:
                forecast_time_validation = (
                    self.callbacks._validate_forecast_observation_time_range(
                        all_datasets_forecast, start_obs_date, end_obs_date
                    )
                )

                if not forecast_time_validation["is_valid"]:
                    StatusMessageHandler.show_obs_info(
                        self.ui.widgets["obs_info_display"],
                        f"ℹ️ Time ranges differ — all data loaded<br><br>"
                        f"<strong>Observation:</strong> {start_obs_date.strftime('%Y-%m-%d %H:%M')} – {end_obs_date.strftime('%Y-%m-%d %H:%M')}<br>"
                        f"<strong>Forecast:</strong> {forecast_time_validation['forecast_start'].strftime('%Y-%m-%d %H:%M')} – {forecast_time_validation['forecast_end'].strftime('%Y-%m-%d %H:%M')}<br>"
                        f"Each dataset will be plotted with its own available time period.",
                    )

                # Do NOT filter geo files — load all observations regardless of
                # whether they fall inside the forecast window so that the user
                # can see each dataset over its full available period.

            all_stations = self.observation_processor.create_stations_geodataframe(
                self.ui.selected_observation_folder
            )

            if all_stations is None:
                # Provide diagnostic info
                folder = self.ui.selected_observation_folder
                geo_count = len(geo_files) if geo_files else 0
                StatusMessageHandler.show_obs_error(
                    self.ui.widgets["obs_info_display"],
                    f"Failed to load observation stations<br>"
                    f"<strong>Folder:</strong> {folder}<br>"
                    f"<strong>GEO files found:</strong> {geo_count}",
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

            self._load_observation_timeseries(geo_files=geo_files)

            # Initialise the lead-time explorer at the observation timestep that
            # is closest to the forecast start, so map colours align with what
            # the timeseries plot shows (which is filtered to the forecast range).
            # If no forecast context is available, start at the LAST (most recent)
            # timestep so stale data from previous retrievals in the same folder
            # does not appear first.
            initial_time_index = 0
            if self.observation_timeseries_df is not None and not self.observation_timeseries_df.empty:
                initial_time_index = len(self.observation_timeseries_df) - 1  # default: most recent

            if (
                self.observation_timeseries_df is not None
                and not self.observation_timeseries_df.empty
                and forecast_time_validation.get("forecast_start") is not None
            ):
                try:
                    fc_start = pd.to_datetime(forecast_time_validation["forecast_start"])
                    # Strip timezone from both sides to avoid comparison errors
                    if hasattr(fc_start, "tz") and fc_start.tz is not None:
                        fc_start = fc_start.tz_convert(None)
                    obs_timestamps = pd.to_datetime(self.observation_timeseries_df.index)
                    if obs_timestamps.tz is not None:
                        obs_timestamps = obs_timestamps.tz_convert(None)
                    mask = obs_timestamps >= fc_start
                    if mask.any():
                        initial_time_index = int(mask.values.argmax())
                except Exception:
                    initial_time_index = len(self.observation_timeseries_df) - 1

            self._create_unified_observation_markers(
                self.current_filtered_stations, time_index=initial_time_index
            )

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

    # ------------------------------------------------------------------
    # Colour-mapping helpers
    # ------------------------------------------------------------------

    # Temperature parameters whose raw geo file values are in Kelvin
    _KELVIN_PARAMS = {"2t", "2d", "tmax", "tmin", "mx2t", "mn2t"}

    def _apply_unit_conversion(self, vmin, vmax):
        """Convert raw values to display units; return (disp_vmin, disp_vmax, unit_str).

        Temperature observations in geo files are stored in Kelvin. Convert to
        Celsius for display when the loaded parameter is a temperature parameter,
        detected either by parameter name or by a Kelvin heuristic (value > 200).
        """
        param = getattr(self, "observation_loaded_parameter", None) or ""
        is_temp = param in self._KELVIN_PARAMS or (vmin > 200 and vmax > 200)
        if is_temp:
            return vmin - 273.15, vmax - 273.15, "°C"
        return vmin, vmax, ""

    @staticmethod
    def _value_to_hex(value, vmin, vmax):
        """Map a scalar value to a hex colour using a RdYlBu_r colormap."""
        try:
            from matplotlib import colormaps
            cmap = colormaps["RdYlBu_r"]
        except Exception:
            return "#949190"
        denom = vmax - vmin if vmax != vmin else 1.0
        t = max(0.0, min(1.0, (value - vmin) / denom))
        r, g, b, _ = cmap(t)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    @staticmethod
    def _build_colorbar_html(vmin, vmax, unit=""):
        """Return an HTML snippet showing a horizontal colourbar legend."""
        try:
            from matplotlib import colormaps
            import numpy as _np
            cmap = colormaps["RdYlBu_r"]
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
            f'<span style="font-weight:bold;">Station values{unit_str}</span><br>'
            f'<div style="display:flex;align-items:center;gap:4px;margin-top:3px;">'
            f'<span>{label_lo}</span>'
            f'<div style="flex:1;height:10px;border-radius:4px;'
            f'background:linear-gradient(to right,{gradient});'
            f'border:1px solid #ccc;"></div>'
            f'<span>{label_hi}</span>'
            f'</div></div>'
        )

    def _get_time_values(self, time_index=0):
        """Return a dict {station_id: value} for a given time index row."""
        if self.observation_timeseries_df is None or self.observation_timeseries_df.empty:
            return None, None
        ts = self.observation_timeseries_df
        if time_index < 0 or time_index >= len(ts):
            return None, None
        row = ts.iloc[time_index].dropna()
        return row, ts.index[time_index]

    # ------------------------------------------------------------------
    # Lead-time step
    # ------------------------------------------------------------------

    def step_observation_time(self, delta):
        """Advance or retreat the current lead-time by *delta* steps and re-colour markers."""
        current = getattr(self.callbacks, "_obs_time_index", 0)
        ts = self.observation_timeseries_df
        if ts is None or ts.empty:
            return
        n = len(ts)
        new_idx = max(0, min(n - 1, current + delta))
        self.callbacks._obs_time_index = new_idx
        self._recolor_markers_at_time(new_idx)

    def _recolor_markers_at_time(self, time_index):
        """Re-colour all unselected observation markers by their value at *time_index*."""
        try:
            import ipyleaflet

            row, ts_time = self._get_time_values(time_index)
            if row is None:
                return

            valid = row.replace([np.inf, -np.inf], np.nan).dropna()
            if valid.empty:
                return

            # Clamp colour range to stations currently visible on the map
            visible_ids = list(self.callbacks.map_handler.observation_markers.keys())
            visible = valid.reindex(visible_ids).dropna()
            scale = visible if not visible.empty else valid
            vmin, vmax = float(scale.min()), float(scale.max())

            # Update time label
            time_label = ts_time.strftime("%Y-%m-%d %H:%M UTC") if hasattr(ts_time, "strftime") else str(ts_time)
            n = len(self.observation_timeseries_df)
            if "obs_time_label" in self.ui.widgets:
                self.ui.widgets["obs_time_label"].value = (
                    f"<span style='font-size:0.82em;color:#333;'>"
                    f"<b>{time_label}</b> ({time_index + 1}/{n})</span>"
                )

            # Update colorbar
            if "obs_colorbar" in self.ui.widgets:
                disp_vmin, disp_vmax, unit = self._apply_unit_conversion(vmin, vmax)
                cb_html = self._build_colorbar_html(disp_vmin, disp_vmax, unit)
                self.ui.widgets["obs_colorbar"].value = cb_html
                self.ui.widgets["obs_colorbar"].layout.display = ""

            # Re-colour markers for non-selected stations
            selected_station_ids = {
                info["station_id"]
                for info in self.callbacks.map_handler.selected_points.values()
                if info.get("type") == "observation"
            } if self.callbacks.map_handler else set()

            for station_id, marker in self.callbacks.map_handler.observation_markers.items():
                if station_id in selected_station_ids:
                    continue  # keep the selection colour
                val = row.get(station_id, np.nan)
                if pd.isna(val):
                    new_color = "#949190"
                else:
                    new_color = self._value_to_hex(float(val), vmin, vmax)
                marker.color = new_color
                marker.fill_color = new_color

            # Update popup values for visible markers
            for station_id, marker in self.callbacks.map_handler.observation_markers.items():
                if station_id in selected_station_ids:
                    continue
                val = row.get(station_id, np.nan)
                val_str = f"{val:.2f}" if not pd.isna(val) else "N/A"
                gdf = getattr(self.callbacks, "observation_stations_gdf", None)
                if gdf is not None and station_id in gdf.index:
                    si = gdf.loc[station_id]
                    lat, lon = si["latitude"], si["longitude"]
                    import ipywidgets as widgets
                    marker.popup = ipyleaflet.Popup(
                        child=widgets.HTML(
                            f'<div style="width:260px;color:black;">'
                            f'<h4 style="margin-bottom:6px;">Station {station_id}</h4>'
                            f'<p style="margin:2px 0;"><b>Location:</b> {lat:.3f}°N, {lon:.3f}°E</p>'
                            f'<p style="margin:2px 0;"><b>Value at {time_label}:</b> {val_str}</p>'
                            f'<p style="margin:2px 0;font-size:0.9em;"><em>Click to select/deselect</em></p>'
                            f'</div>'
                        ),
                        close_button=True,
                        auto_close=True,
                        max_width=280,
                    )

        except Exception as e:
            print(f"❌ Error recolouring markers at time {time_index}: {e}")

    # ------------------------------------------------------------------
    # Marker creation
    # ------------------------------------------------------------------

    def _create_unified_observation_markers(self, filtered_stations_gdf, time_index=0):
        """Create observation markers coloured by their value at *time_index*."""
        try:
            if (
                not self.map_handler
                or filtered_stations_gdf is None
                or len(filtered_stations_gdf) == 0
            ):
                return

            self.map_handler.clear_observation_markers()

            # Pre-compute data counts
            data_counts = {}
            if self.observation_timeseries_df is not None:
                common_cols = filtered_stations_gdf.index.intersection(
                    self.observation_timeseries_df.columns
                )
                if len(common_cols) > 0:
                    data_counts = self.observation_timeseries_df[common_cols].count().to_dict()

            # Get values at the initial time step for colour mapping
            row, ts_time = self._get_time_values(time_index)
            has_values = row is not None and not row.empty
            if has_values:
                valid = row.replace([np.inf, -np.inf], np.nan).dropna()
                # Clamp colour range to visible stations only for better contrast
                visible = valid.reindex(filtered_stations_gdf.index).dropna()
                scale = visible if not visible.empty else valid
                vmin = float(scale.min()) if not scale.empty else 0.0
                vmax = float(scale.max()) if not scale.empty else 1.0
            else:
                vmin = vmax = 0.0

            import ipyleaflet
            import ipywidgets as widgets

            time_label = (
                ts_time.strftime("%Y-%m-%d %H:%M UTC")
                if ts_time is not None and hasattr(ts_time, "strftime")
                else "–"
            )
            n_times = len(self.observation_timeseries_df) if self.observation_timeseries_df is not None else 0

            markers = []
            for station_id, station_info in filtered_stations_gdf.iterrows():
                lat = station_info["latitude"]
                lon = station_info["longitude"]
                elevation = station_info.get("elevation")
                has_elev = elevation is not None and not pd.isna(elevation)
                count = data_counts.get(station_id, 0)

                # Skip stations that have no observation data at all
                if count == 0:
                    continue

                # Colour by value
                val = row.get(station_id, np.nan) if has_values else np.nan
                val_str = f"{val:.2f}" if not pd.isna(val) else "N/A"
                if has_values and not pd.isna(val):
                    marker_color = self._value_to_hex(float(val), vmin, vmax)
                else:
                    marker_color = "#949190"

                popup_html = (
                    f'<div style="width:280px;color:black;">'
                    f'<h4 style="margin-bottom:10px;">Obs Station {station_id}</h4>'
                    f'<p style="margin:2px 0;"><strong>Location:</strong> {lat:.3f}°N, {lon:.3f}°E</p>'
                    + (f'<p style="margin:2px 0;"><strong>Elevation:</strong> {elevation:.1f} m</p>' if has_elev else "")
                    + f'<p style="margin:2px 0;"><strong>Data Points:</strong> {count}</p>'
                    f'<p style="margin:2px 0;"><strong>Value at {time_label}:</strong> {val_str}</p>'
                    f'<p style="margin:2px 0;font-size:0.9em;"><em>Click to select/deselect</em></p>'
                    f'</div>'
                )

                marker = ipyleaflet.CircleMarker(
                    location=(lat, lon),
                    radius=5,
                    color=marker_color,
                    fill_color=marker_color,
                    fill_opacity=0.85,
                    opacity=1.0,
                    weight=1,
                )
                marker.popup = ipyleaflet.Popup(
                    child=widgets.HTML(popup_html),
                    close_button=True,
                    auto_close=True,
                    max_width=300,
                )

                self.map_handler.observation_markers[station_id] = marker
                markers.append(marker)

            # Update the existing layer group's layers in-place so that
            # individual marker widget comms remain properly established.
            # substitute_layer creates a new LayerGroup whose children may
            # lose comm links, preventing later marker.color updates from
            # reaching the frontend.
            self.map_handler.observation_layer_group.layers = tuple(markers)

            # Activate lead-time explorer controls
            if n_times > 0 and "obs_time_explorer" in self.ui.widgets:
                self.callbacks._obs_time_index = time_index
                self.ui.widgets["obs_time_explorer"].layout.display = ""
                self.ui.widgets["obs_time_prev_btn"].disabled = False
                self.ui.widgets["obs_time_next_btn"].disabled = False

                self.ui.widgets["obs_time_label"].value = (
                    f"<span style='font-size:0.82em;color:#333;'>"
                    f"<b>{time_label}</b> ({time_index + 1}/{n_times})</span>"
                )

            # Show colorbar if values available
            if has_values and vmin != vmax and "obs_colorbar" in self.ui.widgets:
                disp_vmin, disp_vmax, unit = self._apply_unit_conversion(vmin, vmax)
                self.ui.widgets["obs_colorbar"].value = self._build_colorbar_html(disp_vmin, disp_vmax, unit)
                self.ui.widgets["obs_colorbar"].layout.display = ""

        except Exception as e:
            print(f"❌ Error creating unified observation markers: {e}")

    @staticmethod
    def _fast_read_geo_values(filepath):
        """Fast reader that only extracts stnid and value_0 from a geo file."""
        stnid_col = None
        value_col = None
        data_started = False
        results = {}

        with open(filepath, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#COLUMNS"):
                    continue
                if stnid_col is None and not line.startswith("#"):
                    headers = line.split("\t")
                    col_map = {h.strip(): i for i, h in enumerate(headers)}
                    stnid_col = col_map.get("stnid")
                    value_col = col_map.get("value_0")
                    if stnid_col is None:
                        return results
                    continue
                if line.startswith("#DATA"):
                    data_started = True
                    continue
                if data_started and not line.startswith("#"):
                    parts = line.split("\t")
                    try:
                        sid = parts[stnid_col]
                        val = parts[value_col] if value_col is not None and value_col < len(parts) else None
                        if val is not None and val != "3e+38":
                            results[sid] = float(val)
                        else:
                            results[sid] = np.nan
                    except (IndexError, ValueError):
                        continue
        return results

    @staticmethod
    def _process_single_geo_file(file_path, station_id_set):
        """Process a single geo file — intended for parallel execution."""
        try:
            filename = os.path.basename(file_path)
            file_datetime = DateTimeExtractor.parse_filename_datetime(filename)
            values = ObservationHandler._fast_read_geo_values(file_path)
            row = {sid: val for sid, val in values.items() if sid in station_id_set}
            row["datetime"] = file_datetime
            return row
        except Exception as e:
            print(f"⚠️ Error processing file {file_path}: {e}")
            return None

    def _load_observation_timeseries(self, geo_files=None):
        """Load observation timeseries data for loaded stations."""
        try:
            if self.observation_stations_gdf is None:
                return

            if geo_files is None:
                geo_files = GeoDataProcessor.get_geo_files(
                    self.ui.selected_observation_folder
                )

            if not geo_files:
                print("⚠️ No geo files found")
                return None, None

            # Extract and store the observation parameter from filenames
            self.observation_loaded_parameter = (
                self._extract_obs_parameter_from_geo_files(geo_files)
            )

            station_id_set = set(self.observation_stations_gdf.index)

            # Parallel file reading — I/O bound, so threads are effective
            max_workers = min(8, len(geo_files))
            all_data = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(
                        self._process_single_geo_file, fp, station_id_set
                    )
                    for fp in geo_files
                ]
                for future in futures:
                    result = future.result()
                    if result is not None:
                        all_data.append(result)

            if all_data:
                self.observation_timeseries_df = (
                    pd.DataFrame(all_data).set_index("datetime").sort_index()
                )

                return (
                    self.observation_timeseries_df.index.min(),
                    self.observation_timeseries_df.index.max(),
                )

            print("⚠️ No timeseries data loaded")
            return None, None

        except Exception as e:
            print(f"❌ Error loading observation timeseries: {e}")

    def _extract_observation_time_range(self, geo_files=None):
        """Extract only start and end dates from observation folder without loading full data."""
        try:
            if not self.ui.selected_observation_folder:
                print("⚠️ No observation folder path provided")
                return None, None

            if geo_files is None:
                geo_files = GeoDataProcessor.get_geo_files(
                    self.ui.selected_observation_folder
                )

            if not geo_files:
                print("⚠️ No observation data files found in folder")
                return None, None

            file_datetimes = []

            for file_path in geo_files:
                try:
                    filename = os.path.basename(file_path)
                    file_datetime = DateTimeExtractor.parse_filename_datetime(filename)

                    if file_datetime:
                        file_datetimes.append(file_datetime)
                    else:
                        print(f"⚠️ Could not parse datetime from filename: {filename}")

                except Exception as e:
                    print(f"⚠️ Error parsing datetime from file {file_path}: {e}")
                    continue

            if file_datetimes:
                return min(file_datetimes), max(file_datetimes)
            else:
                print("❌ No valid datetimes extracted from observation files")
                return None, None

        except Exception as e:
            print(f"❌ Error extracting observation time range: {e}")
            return None, None

    def _filter_stations_by_bbox(self, stations_gdf, bbox):
        """Filter stations by bounding box coordinates using vectorized comparison."""
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

            mask = (
                (stations_gdf["longitude"] >= min_lon)
                & (stations_gdf["longitude"] <= max_lon)
                & (stations_gdf["latitude"] >= min_lat)
                & (stations_gdf["latitude"] <= max_lat)
            )
            return stations_gdf[mask]

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

            current_time_index = getattr(self.callbacks, "_obs_time_index", 0)
            self._create_unified_observation_markers(filtered_stations, time_index=current_time_index)

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
