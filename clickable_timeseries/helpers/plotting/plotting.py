import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .styling_config import TimeseriesStylingConfiguration


class PlottingManager:
    """Main class for handling timeseries plotting and visualization functionality with unit conversions."""

    def __init__(self, temperature_unit="celsius", precipitation_unit="mm"):
        """Initialize the PlottingManager with styling configuration."""
        self.style_config = TimeseriesStylingConfiguration(
            temperature_unit, precipitation_unit
        )

    def set_temperature_unit(self, unit):
        """Set the temperature unit preference.

        Args:
            unit (str): Temperature unit ('celsius' or 'kelvin')

        """
        self.style_config.set_temperature_unit(unit)

    def set_precipitation_unit(self, unit):
        """Set the precipitation unit preference.

        Args:
            unit (str): Precipitation unit ('mm' or 'm')

        """
        self.style_config.set_precipitation_unit(unit)

    def convert_temperature(self, temp_data, from_unit="kelvin", to_unit=None):
        """Convert temperature data between units.

        Args:
            temp_data: Temperature data (pandas Series, DataFrame, or numpy array)
            from_unit (str): Source unit ('kelvin' or 'celsius')
            to_unit (str): Target unit ('kelvin' or 'celsius'). If None, uses style_config unit

        Returns:
            Converted temperature data

        """
        if to_unit is None:
            to_unit = self.style_config.temperature_unit

        if from_unit == to_unit:
            return temp_data

        if from_unit == "kelvin" and to_unit == "celsius":
            return temp_data - 273.15
        elif from_unit == "celsius" and to_unit == "kelvin":
            return temp_data + 273.15
        else:
            raise ValueError(
                f"Unsupported temperature conversion: {from_unit} to {to_unit}"
            )

    def convert_precipitation(self, precip_data, from_unit="m", to_unit="mm"):
        """Convert precipitation data between units.

        Args:
            precip_data: Precipitation data
            from_unit (str): Source unit ('m' or 'mm')
            to_unit (str): Target unit ('m' or 'mm')

        Returns:
            Converted precipitation data

        """
        if from_unit == to_unit:
            return precip_data

        if from_unit == "m" and to_unit == "mm":
            return precip_data * 1000
        elif from_unit == "mm" and to_unit == "m":
            return precip_data / 1000
        else:
            raise ValueError(
                f"Unsupported precipitation conversion: {from_unit} to {to_unit}"
            )

    def process_data_units(self, data, parameter_name, data_source="observed"):  # noqa: PLR0911, PLR0912
        """Process data to ensure correct units.

        Args:
            data: The data to process
            parameter_name (str): Name of the parameter
            data_source (str): Source of data ('observed' or 'forecast')

        Returns:
            Processed data with correct units

        """
        if data is None or len(data) == 0:
            return data

        # Temperature parameters
        if parameter_name in [
            "2t",
            "2d",
            "2t_24h_max",
            "2t_24h_min",
            "2d_24h_max",
            "2d_24h_min",
        ]:
            if data_source == "forecast":
                return self.convert_temperature(
                    data, from_unit="kelvin", to_unit=self.style_config.temperature_unit
                )
            else:
                if isinstance(data, pd.Series | pd.DataFrame):
                    sample_values = data.dropna().values.flatten()
                else:
                    sample_values = np.array(data).flatten()

                if len(sample_values) > 0:
                    mean_temp = np.mean(sample_values)
                    if mean_temp > 200:  # noqa: PLR2004
                        return self.convert_temperature(
                            data,
                            from_unit="kelvin",
                            to_unit=self.style_config.temperature_unit,
                        )
                    else:
                        return self.convert_temperature(
                            data,
                            from_unit="celsius",
                            to_unit=self.style_config.temperature_unit,
                        )
                return data

        elif parameter_name in [
            "tp",
            "tp_deaccum",
            "cp_deaccum",
            "lsp_deaccum",
            "cp",
            "lsp",
        ]:
            if isinstance(data, pd.Series | pd.DataFrame):
                sample_values = data.dropna().values.flatten()
            else:
                sample_values = np.array(data).flatten()

            if len(sample_values) == 0:
                return data

            max_val = np.max(sample_values)

            if data_source == "forecast":
                return self.convert_precipitation(
                    data, from_unit="m", to_unit=self.style_config.precipitation_unit
                )
            elif max_val > 10:  # noqa: PLR2004
                return self.convert_precipitation(
                    data, from_unit="mm", to_unit=self.style_config.precipitation_unit
                )
            elif max_val > 0.1:  # noqa: PLR2004
                return self.convert_precipitation(
                    data, from_unit="mm", to_unit=self.style_config.precipitation_unit
                )
            elif max_val <= 0.1:  # noqa: PLR2004
                return self.convert_precipitation(
                    data, from_unit="m", to_unit=self.style_config.precipitation_unit
                )
            else:
                return self.convert_precipitation(
                    data, from_unit="mm", to_unit=self.style_config.precipitation_unit
                )

        else:
            return data

    def create_timeseries_chart(  # noqa: PLR0913
        self,
        timeseries_df,
        stations_gdf,
        active_stations,
        loaded_stations,
        forecast_processor=None,
        forecast_dfs=None,
        parameter_name="tp",
        station_distances=None,
    ):
        """Create and return a Plotly timeseries chart with optional forecast data and unit conversions.

        Args:
            timeseries_df (pd.DataFrame): DataFrame with timeseries data indexed by station ID
            stations_gdf (gpd.GeoDataFrame): GeoDataFrame with station metadata
            active_stations (dict): Dictionary mapping station IDs to colors for active stations
            loaded_stations (list): List of station IDs that are currently loaded
            forecast_processor: Processor containing forecast data
            forecast_dfs (dict): Dictionary with forecast data {model_name: dataframe}
            parameter_name (str): Parameter name for configuration lookup
            station_distances (dict): Dictionary with model distances {model_name: {station_id: distance_km}}

        Returns:
            go.Figure: Plotly figure object containing the timeseries chart

        """
        config = self.style_config.get_parameter_config(parameter_name)

        forecast_data_to_plot = None
        if forecast_dfs is not None:
            forecast_data_to_plot = forecast_dfs
        elif forecast_processor and hasattr(forecast_processor, "get_forecast_data"):
            forecast_data_to_plot = forecast_processor.get_forecast_data(parameter_name)

        if (
            station_distances is None
            and forecast_processor
            and hasattr(forecast_processor, "get_station_distances")
        ):
            station_distances = forecast_processor.get_station_distances()

        if len(loaded_stations) == 0:
            return self._create_no_stations_plot(config, forecast_data_to_plot)

        if not active_stations:
            return self._create_no_active_stations_plot(
                config, loaded_stations, forecast_data_to_plot
            )

        fig = go.Figure()

        self._add_observed_data_traces(
            fig,
            timeseries_df,
            stations_gdf,
            active_stations,
            loaded_stations,
            parameter_name,
            config,
        )

        if forecast_data_to_plot:
            self._add_forecast_data_traces(
                fig,
                forecast_data_to_plot,
                stations_gdf,
                active_stations,
                loaded_stations,
                parameter_name,
                config,
                station_distances,
            )

        title_text = self._build_chart_title(
            config, active_stations, forecast_data_to_plot, parameter_name
        )
        layout_config = self.style_config.get_layout_config(
            config, title_text, len(active_stations) == 1
        )

        if len(active_stations) == 1:
            layout_config["xaxis"]["rangeslider"] = (
                self.style_config.get_rangeslider_config()
            )

        fig.update_layout(**layout_config)

        return fig

    def create_multi_point_timeseries_plot(
        self, multi_point_data, parameter_name, selected_models=None
    ):
        """Create timeseries plot for multiple selected points with unified data format.

        Args:
            multi_point_data (dict): Point data with forecast and distance information
            parameter_name (str): Parameter name for configuration
            selected_models (list): List of model names to display

        Returns:
            go.Figure: Plotly figure object

        """
        if not multi_point_data:
            return self.create_empty_plot()

        if parameter_name == "10ff":
            return self._create_wind_speed_multi_point_plot(
                multi_point_data, selected_models
            )
        else:
            return self._create_standard_multi_point_plot(
                multi_point_data, parameter_name, selected_models
            )

    def create_empty_plot(self):
        """Create an empty plot when no points are selected."""
        fig = go.Figure()

        fig.add_annotation(
            text="Click on the map to select points<br><br>",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 14, "color": "gray"},
        )

        fig.update_layout(
            title={
                "text": "Multi-Point Weather Analysis",
                "x": 0.5,
                "font": {"size": 14, "color": "#171A35", "family": "Arial Black"},
            },
            xaxis={"visible": False},
            yaxis={"visible": False},
            height=500,
            showlegend=False,
            paper_bgcolor="white",
            plot_bgcolor="white",
        )

        return fig

    def create_placeholder_plot(self, num_points, message=""):
        """Create placeholder plot showing that points are selected but data/parameter is missing."""
        fig = go.Figure()

        if message:
            plot_message = f"{num_points} point(s) selected<br><br>{message}"
        else:
            plot_message = f"{num_points} point(s) selected<br><br>Please select a parameter to analyze"

        fig.add_annotation(
            text=plot_message,
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 14, "color": "gray"},
        )

        fig.update_layout(
            title={
                "text": "Multi-Point Analysis",
                "x": 0.5,
                "font": {"size": 14, "color": "black"},
            },
            xaxis={"visible": False},
            yaxis={"visible": False},
            height=500,
            showlegend=False,
            paper_bgcolor="white",
            plot_bgcolor="white",
        )

        return fig

    # Private helper methods
    def _create_no_stations_plot(self, config, forecast_data_to_plot):
        """Create plot when no stations are loaded."""
        fig = go.Figure()

        fig.add_annotation(
            text="Draw a rectangle on the map<br>to load stations in that area",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 16, "color": "gray"},
        )

        fig.update_layout(
            title={
                "text": f"{config['parameter_name']} Viewer",
                "x": 0.5,
                "font": {"size": 18, "color": "black"},
            },
            xaxis={"visible": False},
            yaxis={"visible": False},
            height=680,
            showlegend=False,
            paper_bgcolor="white",
            plot_bgcolor="white",
        )

        return fig

    def _create_no_active_stations_plot(
        self, config, loaded_stations, forecast_data_to_plot
    ):
        """Create plot when stations are loaded but none are active."""
        fig = go.Figure()

        forecast_info = ""
        if forecast_data_to_plot:
            model_count = len(forecast_data_to_plot)
            model_names = list(forecast_data_to_plot.keys())
            forecast_info = f"<br>🔮 Forecast data available ({model_count} models: {', '.join(model_names)})"

        fig.add_annotation(
            text=f"Click on station markers to display their data<br><br>📍 {len(loaded_stations)} stations loaded in selected area{forecast_info}",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 16, "color": "black"},
        )

        fig.update_layout(
            title={
                "text": f"{config['parameter_name']} Viewer",
                "x": 0.5,
                "font": {"size": 18, "color": "black"},
            },
            xaxis={"visible": False},
            yaxis={"visible": False},
            height=680,
            showlegend=False,
            paper_bgcolor="white",
            plot_bgcolor="white",
        )

        return fig

    def _add_observed_data_traces(  # noqa: PLR0913
        self,
        fig,
        timeseries_df,
        stations_gdf,
        active_stations,
        loaded_stations,
        parameter_name,
        config,
    ):
        """Add observed data traces to the figure."""
        if timeseries_df is not None and hasattr(timeseries_df, "columns"):
            for station_id, _color in active_stations.items():
                if (
                    station_id in timeseries_df.columns
                    and station_id in loaded_stations
                ):
                    station_ts = timeseries_df[station_id].dropna()

                    if len(station_ts) > 0:
                        processed_ts = self.process_data_units(
                            station_ts, parameter_name, "observed"
                        )
                        station_info = stations_gdf.loc[station_id]
                        obs_color = self.style_config.get_data_color(
                            "obs", station_id, active_stations
                        )

                        station_name = (
                            f"{station_id} - Obs"
                            if len(active_stations) >= 1
                            else "Obs"
                        )

                        hover_text = self._build_hover_text(
                            processed_ts,
                            station_id,
                            station_info,
                            config,
                            parameter_name,
                            "Observed",
                        )

                        fig.add_trace(
                            go.Scatter(
                                x=processed_ts.index,
                                y=processed_ts.values,
                                mode="lines+markers",
                                name=station_name,
                                line={"color": obs_color, "width": 2},
                                marker={"size": 4},
                                hovertemplate="%{hovertext}<extra></extra>",
                                hovertext=hover_text,
                            )
                        )

    def _add_forecast_data_traces(  # noqa: PLR0913
        self,
        fig,
        forecast_data_to_plot,
        stations_gdf,
        active_stations,
        loaded_stations,
        parameter_name,
        config,
        station_distances,
    ):
        """Add forecast data traces to the figure."""
        for model_name, model_forecast_df in forecast_data_to_plot.items():
            if model_forecast_df is not None and hasattr(model_forecast_df, "columns"):
                style = self.style_config.get_model_style(model_name)

                for station_id, _color in active_stations.items():
                    if (
                        station_id in model_forecast_df.columns
                        and station_id in loaded_stations
                    ):
                        forecast_ts = model_forecast_df[station_id].dropna()

                        if len(forecast_ts) > 0:
                            processed_forecast_ts = self.process_data_units(
                                forecast_ts, parameter_name, "forecast"
                            )
                            station_info = stations_gdf.loc[station_id]
                            model_color = self.style_config.get_data_color(
                                model_name, station_id, active_stations
                            )

                            distance_km = None
                            if (
                                station_distances
                                and model_name in station_distances
                                and station_id in station_distances[model_name]
                            ):
                                distance_km = station_distances[model_name][station_id]

                            legend_name = self._build_legend_name(
                                station_id,
                                model_name,
                                distance_km,
                                len(active_stations),
                            )

                            hover_text = self._build_forecast_hover_text(
                                processed_forecast_ts,
                                station_id,
                                model_name,
                                station_info,
                                config,
                                parameter_name,
                                distance_km,
                            )

                            fig.add_trace(
                                go.Scatter(
                                    x=processed_forecast_ts.index,
                                    y=processed_forecast_ts.values,
                                    mode="lines+markers",
                                    name=legend_name,
                                    line={
                                        "color": model_color,
                                        "width": style["width"],
                                        "dash": style["dash"],
                                    },
                                    marker={"size": 4, "symbol": style["symbol"]},
                                    hovertemplate="%{hovertext}<extra></extra>",
                                    hovertext=hover_text,
                                )
                            )

    def _build_hover_text(  # noqa: PLR0913
        self, timeseries, station_id, station_info, config, parameter_name, data_type
    ):
        """Build hover text for observed data."""
        hover_text = []
        for date, value in zip(timeseries.index, timeseries.values, strict=False):
            hover_text.append(
                f"Station: {station_id}<br>"
                f"Location: {station_info.get('latitude', 0.0):.3f}°N, {station_info.get('longitude', 0.0):.3f}°E<br>"
                f"Elevation: {station_info.get('elevation', 0.0):.1f}m<br>"
                f"Date: {date.strftime('%Y-%m-%d %H:%M')}<br>"
                f"{config['hover_label']}: {self.style_config.format_value_for_hover(value, parameter_name)} ({data_type})"
            )
        return hover_text

    def _build_forecast_hover_text(  # noqa: PLR0913
        self,
        timeseries,
        station_id,
        model_name,
        station_info,
        config,
        parameter_name,
        distance_km,
    ):
        """Build hover text for forecast data."""
        hover_text = []
        for date, value in zip(timeseries.index, timeseries.values, strict=False):
            try:
                if hasattr(date, "strftime"):
                    date_str = date.strftime("%Y-%m-%d %H:%M")
                elif hasattr(date, "to_pydatetime"):
                    date_str = date.to_pydatetime().strftime("%Y-%m-%d %H:%M")
                else:
                    date_str = str(date)
            except:  # noqa: E722
                date_str = str(date)

            hover_parts = [
                f"Station: {station_id}",
                f"Model: {model_name}",
                f"Location: {station_info.get('latitude', 0.0):.3f}°N, {station_info.get('longitude', 0.0):.3f}°E",
                f"Elevation: {station_info.get('elevation', 0.0):.1f}m",
            ]

            if distance_km is not None:
                hover_parts.append(f"Distance: {distance_km:.1f}km")

            hover_parts.extend(
                [
                    f"Date: {date_str}",
                    f"{config['hover_label']}: {self.style_config.format_value_for_hover(value, parameter_name)} {model_name}",
                ]
            )

            hover_text.append("<br>".join(hover_parts))
        return hover_text

    def _build_legend_name(
        self, station_id, model_name, distance_km, num_active_stations
    ):
        """Build legend name for forecast data."""
        if num_active_stations >= 1:
            if distance_km is not None:
                return f"{station_id} - {model_name} (dist: {distance_km:.1f}km)"
            else:
                return f"{station_id} - {model_name}"
        elif distance_km is not None:
            return f"{model_name} (dist: {distance_km:.1f}km)"
        else:
            return f"{model_name}"

    def _build_chart_title(
        self, config, active_stations, forecast_data_to_plot, parameter_name
    ):
        """Build the chart title."""
        if len(active_stations) == 1:
            station_id = list(active_stations.keys())[0]
            title_text = f"{config['title']} - Station {station_id}"
        else:
            title_text = f"{config['title']}"

        if forecast_data_to_plot:
            if len(forecast_data_to_plot) > 1:
                model_names = [
                    name for name in forecast_data_to_plot.keys() if name != "Forecast"
                ]
                title_text += f" (Obs + {', '.join(model_names)})"
            else:
                title_text += " (Obs + Forecast)"

        if parameter_name in [
            "2t",
            "2d",
            "2t_24h_max",
            "2t_24h_min",
            "2d_24h_max",
            "2d_24h_min",
        ]:
            unit_text = "°C" if self.style_config.temperature_unit == "celsius" else "K"
            title_text += f" [{unit_text}]"

        return title_text

    def _create_wind_speed_multi_point_plot(
        self, multi_point_data, selected_models=None
    ):
        """Create wind speed calculation plot for multiple points."""
        return self._create_standard_multi_point_plot(
            multi_point_data, "10ff", selected_models
        )

    def _create_standard_multi_point_plot(  # noqa: PLR0912, PLR0915
        self, multi_point_data, parameter_name, selected_models=None
    ):
        """Create standard parameter plot for multiple points."""
        config = self.style_config.get_parameter_config(parameter_name)
        fig = go.Figure()

        if selected_models is None:
            selected_models = []

        forecast_points = len(
            [p for p in multi_point_data.values() if p.get("type") == "forecast"]
        )
        obs_points = len(
            [p for p in multi_point_data.values() if p.get("type") == "observation"]
        )
        single_point_mode = len(multi_point_data) == 1

        traces_added = 0

        for _point_id, point_data in multi_point_data.items():
            point_color = point_data["color"]
            point_label = point_data["label"]
            point_type = point_data.get("type", "forecast")
            lat, lon = point_data["lat"], point_data["lon"]

            forecast_data = point_data["forecast_data"]
            distance_info = point_data["distance_info"]

            # Align forecast models and observations
            forecast_data = self._align_forecast_models(forecast_data)
            if "Observations" in forecast_data:
                original_obs = forecast_data["Observations"]
                aligned_obs = self._align_observations_with_forecast(
                    original_obs, forecast_data
                )
                forecast_data["Observations"] = aligned_obs

            for model_name, forecast_df in forecast_data.items():
                if (
                    model_name not in selected_models
                    or forecast_df is None
                    or forecast_df.empty
                ):
                    continue

                if single_point_mode:
                    line_color = self.style_config.get_single_point_color(
                        model_name, point_color
                    )
                else:
                    line_color = point_color

                style = self.style_config.get_model_style(model_name)

                if isinstance(forecast_df, pd.DataFrame):
                    processed_data = self.process_data_units(
                        forecast_df["forecast_value"],
                        parameter_name,
                        "observed" if model_name == "Observations" else "forecast",
                    )
                else:
                    processed_data = self.process_data_units(
                        forecast_df,
                        parameter_name,
                        "observed" if model_name == "Observations" else "forecast",
                    )

                distance_km = distance_info.get(model_name, 0)

                if model_name == "Observations":
                    legend_name = f"{point_label} - Obs"
                elif distance_km > 0:
                    legend_name = f"{point_label} - {model_name} ({distance_km:.1f}km)"
                else:
                    legend_name = f"{point_label} - {model_name}"

                hover_text = self._build_multi_point_hover_text(
                    processed_data,
                    point_label,
                    point_type,
                    model_name,
                    lat,
                    lon,
                    distance_km,
                    config,
                    parameter_name,
                )

                fig.add_trace(
                    go.Scatter(
                        x=processed_data.index,
                        y=processed_data.values,
                        mode="lines+markers",
                        name=legend_name,
                        line={
                            "color": line_color,
                            "width": style["width"],
                            "dash": style["dash"],
                        },
                        marker={
                            "size": 5 if model_name == "Observations" else 4,
                            "color": line_color,
                            "symbol": style["symbol"],
                        },
                        hovertemplate="%{hovertext}<extra></extra>",
                        hovertext=hover_text,
                    )
                )
                traces_added += 1

        title_parts = []
        if forecast_points > 0:
            title_parts.append(f"{forecast_points} forecast point(s)")
        if obs_points > 0:
            title_parts.append(f"{obs_points} observation station(s)")

        title_text = f"{config['title']}"

        if parameter_name in [
            "2t",
            "2d",
            "2t_24h_max",
            "2t_24h_min",
            "2d_24h_max",
            "2d_24h_min",
        ]:
            unit_text = "°C" if self.style_config.temperature_unit == "celsius" else "K"
            title_text += f" [{unit_text}]"

        layout_config = self.style_config.get_layout_config(config, title_text, False)
        fig.update_layout(**layout_config)

        return fig

    def _build_multi_point_hover_text(  # noqa: PLR0913
        self,
        timeseries,
        point_label,
        point_type,
        model_name,
        lat,
        lon,
        distance_km,
        config,
        parameter_name,
    ):
        """Build hover text for multi-point visualization."""
        hover_text = []
        for date, value in zip(timeseries.index, timeseries.values, strict=False):
            try:
                date_str = (
                    date.strftime("%Y-%m-%d %H:%M")
                    if hasattr(date, "strftime")
                    else str(date)
                )
            except:  # noqa: E722
                date_str = str(date)

            hover_parts = [
                f"Point: {point_label}",
                f"Type: {point_type.capitalize()}",
                f"Model: {model_name}",
                f"Location: {lat:.4f}°N, {lon:.4f}°E",
            ]

            if distance_km > 0:
                hover_parts.append(f"Distance: {distance_km:.1f}km")

            hover_parts.extend(
                [
                    f"Date: {date_str}",
                    f"{config['hover_label']}: {self.style_config.format_value_for_hover(value, parameter_name)}",
                ]
            )

            hover_text.append("<br>".join(hover_parts))
        return hover_text

    def _align_observations_with_forecast(self, obs_data, forecast_data_dict):
        """Filter observation data to match the same time range as forecast timeline."""
        if obs_data is None or obs_data.empty:
            return obs_data

        longest_forecast = None
        max_length = 0

        for model_name, forecast_df in forecast_data_dict.items():
            if (
                model_name != "Observations"
                and forecast_df is not None
                and not forecast_df.empty
            ):
                current_length = len(forecast_df)
                if current_length > max_length:
                    max_length = current_length
                    longest_forecast = forecast_df

        if longest_forecast is None:
            return obs_data

        forecast_start = longest_forecast.index.min()
        forecast_end = longest_forecast.index.max()

        filtered_obs = obs_data[
            (obs_data.index >= forecast_start) & (obs_data.index <= forecast_end)
        ]

        return filtered_obs

    def _align_forecast_models(self, forecast_data_dict):
        """Align AIFS and IFS forecasts to cover the same time period."""
        forecast_models = {
            k: v
            for k, v in forecast_data_dict.items()
            if k != "Observations" and v is not None and not v.empty
        }

        if len(forecast_models) < 2:  # noqa: PLR2004
            return forecast_data_dict

        common_start = None
        common_end = None

        for _model_name, forecast_df in forecast_models.items():
            model_start = forecast_df.index.min()
            model_end = forecast_df.index.max()

            if common_start is None or model_start > common_start:
                common_start = model_start
            if common_end is None or model_end < common_end:
                common_end = model_end

        aligned_forecast_data = forecast_data_dict.copy()

        for model_name in forecast_models.keys():
            original_df = forecast_data_dict[model_name]
            aligned_df = original_df[
                (original_df.index >= common_start) & (original_df.index <= common_end)
            ]
            aligned_forecast_data[model_name] = aligned_df

        return aligned_forecast_data
