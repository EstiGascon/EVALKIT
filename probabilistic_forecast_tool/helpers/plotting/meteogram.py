from datetime import datetime

import earthkit.data as ekd  # type: ignore
import numpy as np  # type: ignore
import pandas as pd  # type: ignore
import plotly.graph_objects as go
import xarray as xr  # type: ignore
from earthkit.geo import nearest_point_haversine  # type: ignore
from helpers.parameter_config_manager import ParameterConfigManager
from helpers.styling_config import StylingConfiguration


class MeteogramPlotting:
    """Create meteogram plots from ensemble forecast and observation data.

    Generates interactive Plotly visualizations combining control forecasts,
    ensemble forecasts (as box plots), and observational data when available.
    """

    def __init__(self, styling_config=StylingConfiguration()):
        """Initialize meteogram plotter.

        Parameters
        ----------
        styling_config : StylingConfiguration, optional
            Configuration for plot styling, colors, and units

        """
        self.styling_config = styling_config
        self.color_palette = self._setup_color_palette()

    def _setup_color_palette(self) -> dict[str, str]:
        """Define color palette for plot elements."""
        return {
            "cf": "#FF0000",
            "pf": "#6E78FA",
            "pf_fill": "#B1B6FC",
            "obs": "#000000",
        }

    def _get_absolute_times(
        self, data_array: xr.DataArray, metadata: dict
    ) -> np.ndarray:
        """Convert step coordinate to absolute datetime values for plotting.

        Parameters
        ----------
        data_array : xr.DataArray
            Data with 'step' coordinate
        metadata : dict
            Metadata dict containing 'date' and 'time'

        Returns
        -------
        np.ndarray
            Array of datetime objects

        """
        steps = data_array.coords["step"].values

        date_str = metadata["date"]
        if "-" in date_str:
            reference_time = pd.to_datetime(date_str, format="%Y-%m-%d")
        else:
            reference_time = pd.to_datetime(date_str, format="%Y%m%d")

        if "time" in metadata:
            hours = int(metadata["time"].split(":")[0])
            reference_time = reference_time + pd.Timedelta(hours=hours)

        step_deltas = pd.to_timedelta(steps)
        return reference_time + step_deltas

    def _extract_nearest_gridpoint(self, data, lat: float, lon: float) -> xr.DataArray:
        """Extract data at nearest grid point to specified coordinates.

        Parameters
        ----------
        data : earthkit dataset or xarray object
            Input data
        lat : float
            Target latitude
        lon : float
            Target longitude

        Returns
        -------
        xr.DataArray
            Data at nearest point

        """
        xr_data = data.to_xarray() if hasattr(data, "to_xarray") else data

        if isinstance(xr_data, xr.Dataset):
            xr_data = xr_data[list(xr_data.data_vars)[0]]

        if "values" in xr_data.dims:
            if hasattr(data, "to_latlon"):
                latlon = data.to_latlon()
                lats = latlon["lat"]
                lons = latlon["lon"]
            else:
                lat_coord = xr_data.coords.get("latitude", xr_data.coords.get("lat"))
                lon_coord = xr_data.coords.get("longitude", xr_data.coords.get("lon"))

                if lat_coord is not None and lon_coord is not None:
                    lats = lat_coord.values
                    lons = lon_coord.values
                else:
                    raise ValueError("Cannot find latitude/longitude coordinates")

            idx, distance = nearest_point_haversine([lat, lon], (lats, lons))
            point_data = xr_data.isel(values=idx)

        else:
            lat_coord = xr_data.coords.get("latitude", xr_data.coords.get("lat"))
            lon_coord = xr_data.coords.get("longitude", xr_data.coords.get("lon"))

            if lat_coord is None or lon_coord is None:
                raise ValueError("Cannot find latitude/longitude coordinates")

            lat_name = "latitude" if "latitude" in xr_data.coords else "lat"
            lon_name = "longitude" if "longitude" in xr_data.coords else "lon"

            if lat_coord.ndim == 1 and lon_coord.ndim == 1:
                lon_grid, lat_grid = np.meshgrid(lon_coord.values, lat_coord.values)
                lats = lat_grid.flatten()
                lons = lon_grid.flatten()

                idx, distance = nearest_point_haversine([lat, lon], (lats, lons))

                lat_idx, lon_idx = np.unravel_index(
                    idx, (len(lat_coord), len(lon_coord))
                )

                point_data = xr_data.isel({lat_name: lat_idx, lon_name: lon_idx})

            elif lat_coord.ndim == 2 and lon_coord.ndim == 2:
                lats = lat_coord.values.flatten()
                lons = lon_coord.values.flatten()

                idx, distance = nearest_point_haversine([lat, lon], (lats, lons))

                lat_idx, lon_idx = np.unravel_index(idx, lat_coord.shape)

                dim0, dim1 = lat_coord.dims
                point_data = xr_data.isel({dim0: lat_idx, dim1: lon_idx})

            else:
                raise ValueError(
                    f"Unexpected coordinate dimensions: lat={lat_coord.ndim}D, lon={lon_coord.ndim}D"
                )

        if isinstance(point_data, xr.Dataset):
            point_data = point_data[list(point_data.data_vars)[0]]

        if point_data.name is None:
            point_data.name = "data"

        return point_data

    def _preprocess_data(self, data_source, parameter: str):
            """Extract parameter as DataArray from data source.

            Parameters
            ----------
            data_source : earthkit or xarray object
                Input data
            parameter : str
                Parameter name to extract

            Returns
            -------
            xr.DataArray
                Extracted parameter data

            """
            if hasattr(data_source, 'sel'):
                selected_data = data_source.sel(param=parameter)
                xr_data = selected_data.to_xarray()
            else:
                xr_data = data_source if isinstance(data_source, xr.DataArray | xr.Dataset) else data_source.to_xarray()

            if isinstance(xr_data, xr.Dataset):
                return xr_data[list(xr_data.data_vars)[0]]

            return xr_data

    def _load_and_select_data(self, data_source, parameter: str) -> xr.DataArray:
        """Load and extract parameter from data source.

        Parameters
        ----------
        data_source : str or earthkit object
            File path or loaded dataset
        parameter : str
            Parameter to extract

        Returns
        -------
        xr.DataArray

        """
        dataset = (
            ekd.from_source("file", data_source)
            if isinstance(data_source, str)
            else data_source
        )
        return self._preprocess_data(dataset, parameter)

    def _find_nearest_station(
        self, meteogram_data: dict, lat: float, lon: float, tolerance: float = 0.1
    ) -> str:
        """Find nearest observation station within tolerance distance.

        Parameters
        ----------
        meteogram_data : dict
            Meteogram data dictionary
        lat : float
            Target latitude
        lon : float
            Target longitude
        tolerance : float, optional
            Maximum distance in degrees (default: 0.1)

        Returns
        -------
        str or None
            Station ID if found, None otherwise

        """
        obs_data = meteogram_data.get("observations")
        if not obs_data or "stations_gdf" not in obs_data:
            return None

        stations_gdf = obs_data["stations_gdf"]
        distances = np.sqrt(
            (stations_gdf["latitude"] - lat) ** 2
            + (stations_gdf["longitude"] - lon) ** 2
        )

        min_distance = distances.min()
        if min_distance <= tolerance:
            nearest_station_idx = distances.idxmin()
            return (
                stations_gdf.index[nearest_station_idx]
                if isinstance(nearest_station_idx, int | np.integer)
                else nearest_station_idx
            )

        return None

    def _convert_observation_units(
        self, obs_values: np.ndarray, parameter: str, target_unit: str
    ) -> np.ndarray:
        """Convert observation values to target unit.

        Parameters
        ----------
        obs_values : np.ndarray
            Values to convert
        parameter : str
            Parameter name
        target_unit : str
            Target unit

        Returns
        -------
        np.ndarray
            Converted values

        """
        param_config = ParameterConfigManager()
        category = param_config.get_parameter_category(parameter)

        if category == "temperature" and target_unit.lower() == "celsius":
            return obs_values - 273.15
        elif category == "precipitation" and target_unit.lower() == "mm":
            return obs_values * 1000

        return obs_values

    def _extract_observation_timeseries(
        self,
        meteogram_data: dict,
        station_id: str,
        target_unit: str,
        parameter: str,
        time_range: tuple = None,
    ) -> xr.DataArray:
        """Extract observation timeseries for a station.

        Parameters
        ----------
        meteogram_data : dict
            Meteogram data dictionary
        station_id : str
            Station identifier
        target_unit : str
            Target unit for conversion
        parameter : str
            Parameter name
        time_range : tuple, optional
            (start_time, end_time) to filter observations

        Returns
        -------
        xr.DataArray or None
            Observation timeseries

        """
        obs_data = meteogram_data.get("observations")
        if not obs_data or "timeseries_data" not in obs_data:
            return None

        station_id_str = str(station_id)
        if station_id_str not in obs_data["timeseries_data"]:
            return None

        station_data = obs_data["timeseries_data"][station_id_str]
        if "timeseries" not in station_data:
            return None

        obs_times = []
        obs_values = []

        for entry in station_data["timeseries"]:
            if "datetime" in entry and "value" in entry:
                obs_datetime = entry["datetime"]

                if time_range:
                    start_time, end_time = time_range
                    if not (start_time <= obs_datetime <= end_time):
                        continue

                obs_times.append(obs_datetime)
                obs_values.append(entry["value"])

        if not obs_times:
            return None

        converted_values = self._convert_observation_units(
            np.array(obs_values), parameter, target_unit
        )

        return xr.DataArray(
            converted_values,
            coords={"t": obs_times},
            dims=["t"],
            name=parameter,
        )

    def _get_forecast_time_range(self, meteogram_data: dict) -> tuple:
        """Extract time range from forecast data.

        Parameters
        ----------
        meteogram_data : dict
            Meteogram data dictionary

        Returns
        -------
        tuple or None
            (start_time, end_time) or None

        """
        for data_type in ["cf", "pf"]:
            if data_type in meteogram_data:
                dataset = meteogram_data[data_type]["dataset"]
                data = self._load_and_select_data(dataset, "2t")
                if data is not None:
                    xr_data = data.to_xarray() if hasattr(data, "to_xarray") else data
                    times = xr_data.coords["step"].values
                    return (pd.to_datetime(times[0]), pd.to_datetime(times[-1]))

        return None

    def _generate_plot_title(
        self,
        parameter: str,
        lat: float,
        lon: float,
        forecast_date: str = None,
        forecast_time: str = None,
        station_id: str = None,
    ) -> str:
        """Generate formatted plot title.

        Parameters
        ----------
        parameter : str
            Parameter name
        lat : float
            Latitude
        lon : float
            Longitude
        forecast_date : str, optional
            Forecast date (YYYYMMDD)
        forecast_time : str, optional
            Forecast time
        station_id : str, optional
            Observation station ID

        Returns
        -------
        str
            Formatted title

        """
        param_config = self.styling_config.choose_color_palette_and_levels(parameter)

        if forecast_date:
            try:
                formatted_date = datetime.strptime(forecast_date, "%Y-%m-%d").strftime(
                    "%d/%m/%Y"
                )
            except ValueError:
                try:
                    formatted_date = datetime.strptime(
                        forecast_date, "%Y%m%d"
                    ).strftime("%d/%m/%Y")
                except ValueError:
                    formatted_date = forecast_date
        else:
            formatted_date = datetime.now().strftime("%d/%m/%Y")

        datetime_info = formatted_date
        if forecast_time:
            hour = (
                forecast_time.split(":")[0] if ":" in forecast_time else forecast_time
            )
            datetime_info = f"{formatted_date} {hour}:00 UTC"

        location_str = f"{lat:.2f}°, {lon:.2f}°"
        if station_id:
            location_str += f" (Station: {station_id})"

        return (
            f"Meteogram: {param_config['title']}\n"
            f"Location: {location_str} | Forecast: {datetime_info}"
        )

    def _create_box_traces(
        self, data_array: xr.DataArray, metadata: dict, quantiles: list = None
    ) -> list:
        """Create box plot traces for ensemble data.

        Parameters
        ----------
        data_array : xr.DataArray
            Ensemble data with 'step' and ensemble dimensions
        metadata : dict
            Metadata dict containing 'date' and 'time'
        quantiles : list, optional
            Quantile levels (default: [0.05, 0.25, 0.5, 0.75, 0.95])

        Returns
        -------
        list
            Plotly trace objects

        """
        if quantiles is None:
            quantiles = [0.05, 0.25, 0.5, 0.75, 0.95]

        time_coords = self._get_absolute_times(data_array, metadata)
        ensemble_dim = [d for d in data_array.dims if d != "step"][0]

        ensemble_axis = data_array.dims.index(ensemble_dim)
        quantile_values = np.quantile(data_array.values, quantiles, axis=ensemble_axis)

        time_diff = time_coords[1] - time_coords[0]
        width = time_diff.total_seconds() * 1000 * 0.6

        traces = []

        traces.append(
            go.Box(
                x=time_coords,
                lowerfence=quantile_values[0],
                upperfence=quantile_values[-1],
                q1=quantile_values[1],
                q3=quantile_values[-2],
                median=quantile_values[2],
                width=width * 0.6,
                line_color=self.color_palette["pf"],
                fillcolor=self.color_palette["pf_fill"],
                name="Ensemble Members",
                hoverinfo="skip",
            )
        )

        extra_boxes = (len(quantiles) - 5) // 2
        for j in range(extra_boxes):
            traces.append(
                go.Box(
                    x=time_coords,
                    lowerfence=quantile_values[0],
                    upperfence=quantile_values[-1],
                    showwhiskers=False,
                    q1=quantile_values[1 + (j + 1)],
                    q3=quantile_values[-2 - (j + 1)],
                    median=quantile_values[2],
                    width=width,
                    line_color=self.color_palette["pf"],
                    fillcolor=self.color_palette["pf_fill"],
                    name="Ensemble Members",
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

        for y, p in zip(quantile_values, quantiles, strict=False):
            traces.append(
                go.Scatter(
                    x=time_coords,
                    y=y,
                    mode="markers",
                    marker={"size": 0.00001, "color": self.color_palette["pf"]},
                    hovertemplate=f"%{{y:.2f}}<extra>P<sub>{p * 100:g}%</sub></extra>",
                    showlegend=False,
                )
            )

        return traces

    def create_meteogram(
        self,
        meteogram_data: dict,
        parameter: str,
        lat: float,
        lon: float,
        target_unit: str = None,
        plot_types: list[str] = None,
        skip_observations: bool = False,
        width: int = 1200,
        height: int = 600,
    ) -> go.Figure:
        """Create interactive meteogram plot.

        Combines control forecast, ensemble forecast (as box plots), and
        observations into a single Plotly figure.

        Parameters
        ----------
        meteogram_data : dict
            Dictionary containing forecast and observation data
        parameter : str
            Parameter code (e.g., '2t', 'tp', 'msl')
        lat : float
            Latitude for extraction
        lon : float
            Longitude for extraction
        target_unit : str, optional
            Target display unit
        plot_types : list[str], optional
            Plot components: ['box', 'em_line', 'cf_line', 'obs_line']
        skip_observations : bool, optional
            Skip observation processing (default: False)
        width : int, optional
            Plot width in pixels (default: 1200)
        height : int, optional
            Plot height in pixels (default: 600)

        Returns
        -------
        go.Figure
            Interactive Plotly figure

        """
        param_config = self.styling_config.choose_color_palette_and_levels(
            parameter, unit=target_unit
        )

        if target_unit is None:
            target_unit = param_config.get("unit", "")

        if plot_types is None:
            plot_types = ["box", "cf_line"]
            if not skip_observations and "observations" in meteogram_data:
                plot_types.append("obs_line")

        forecast_date = None
        forecast_time = None
        for data_type in ["cf", "pf"]:
            if data_type in meteogram_data:
                metadata = meteogram_data[data_type].get("metadata", {})
                forecast_date = forecast_date or metadata.get("date")
                forecast_time = forecast_time or metadata.get("time")
                if forecast_date and forecast_time:
                    break

        nearest_station = None
        if "obs_line" in plot_types and not skip_observations:
            nearest_station = self._find_nearest_station(meteogram_data, lat, lon)

        title = self._generate_plot_title(
            parameter, lat, lon, forecast_date, forecast_time, nearest_station
        )

        time_range = None
        if nearest_station and "obs_line" in plot_types:
            time_range = self._get_forecast_time_range(meteogram_data)

        fig = go.Figure()

        if "cf" in meteogram_data and "cf_line" in plot_types:
            cf_dataset = meteogram_data["cf"]["dataset"]
            cf_metadata = meteogram_data["cf"]["metadata"]
            cf_data = self._load_and_select_data(cf_dataset, parameter)
            cf_xr = cf_data.to_xarray() if hasattr(cf_data, "to_xarray") else cf_data
            cf_point = self._extract_nearest_gridpoint(cf_xr, lat, lon)

            cf_values = np.squeeze(cf_point.values)
            non_singleton_dims = [d for d in cf_point.dims if cf_point.sizes[d] > 1]
            non_singleton_coords = {
                d: cf_point.coords[d]
                for d in non_singleton_dims
                if d in cf_point.coords
            }

            cf_point = xr.DataArray(
                cf_values,
                dims=non_singleton_dims,
                coords=non_singleton_coords,
                name=parameter,
            )

            cf_point, _ = self.styling_config.transform_data_and_levels(
                cf_point, parameter, [], target_unit
            )

            time_coords = self._get_absolute_times(cf_point, cf_metadata)

            fig.add_trace(
                go.Scatter(
                    x=time_coords,
                    y=cf_point.values,
                    mode="lines",
                    name="Control Forecast",
                    line={"color": self.color_palette["cf"], "width": 3},
                )
            )

        if "pf" in meteogram_data and "box" in plot_types:
            pf_dataset = meteogram_data["pf"]["dataset"]
            pf_metadata = meteogram_data["pf"]["metadata"]
            pf_data = self._load_and_select_data(pf_dataset, parameter)
            pf_xr = pf_data.to_xarray() if hasattr(pf_data, "to_xarray") else pf_data
            pf_point = self._extract_nearest_gridpoint(pf_xr, lat, lon)

            pf_values = np.squeeze(pf_point.values)
            non_singleton_dims = [d for d in pf_point.dims if pf_point.sizes[d] > 1]
            non_singleton_coords = {
                d: pf_point.coords[d]
                for d in non_singleton_dims
                if d in pf_point.coords
            }

            pf_point = xr.DataArray(
                pf_values,
                dims=non_singleton_dims,
                coords=non_singleton_coords,
                name=parameter,
            )

            pf_point, _ = self.styling_config.transform_data_and_levels(
                pf_point, parameter, [], target_unit
            )

            box_traces = self._create_box_traces(pf_point, pf_metadata)
            for trace in box_traces:
                fig.add_trace(trace)

        if nearest_station and "obs_line" in plot_types:
            obs_data = self._extract_observation_timeseries(
                meteogram_data, nearest_station, target_unit, parameter, time_range
            )
            if obs_data is not None:
                fig.add_trace(
                    go.Scatter(
                        x=obs_data.coords["t"].values,
                        y=obs_data.values,
                        mode="lines+markers",
                        name="Observations",
                        line={"color": self.color_palette["obs"], "width": 3},
                        marker={"size": 6},
                    )
                )

        fig.update_layout(
            title={
                "text": title,
                "x": 0.5,
                "xanchor": "center",
                "yanchor": "top",
                "font": {"size": 14, "color": "#000000", "family": "Arial, sans-serif"},
                "pad": {"t": 5, "b": 15},
            },
            xaxis_title={
                "text": "Time",
                "font": {"size": 12, "color": "#000000"},
                "standoff": 15,
            },
            yaxis_title={
                "text": f"{param_config['title']} ({param_config['unit']})",
                "font": {"size": 12, "color": "#000000"},
                "standoff": 15,
            },
            width=width,
            height=height,
            hovermode="x",
            plot_bgcolor="white",
            paper_bgcolor="white",
            margin={"l": 70, "r": 140, "t": 100, "b": 70},
            xaxis={
                "gridwidth": 0.5,
                "showgrid": True,
                "gridcolor": "#E0E0E0",
                "showline": True,
                "linewidth": 1.5,
                "linecolor": "#000000",
                "zeroline": False,
                "tickfont": {"size": 10, "color": "#000000"},
                "tickformat": "%d %b\n%H:%M",
                "mirror": True,
                "ticks": "outside",
                "ticklen": 5,
                "tickcolor": "#AAAAAA",
            },
            yaxis={
                "linewidth": 1.5,
                "linecolor": "#000000",
                "gridcolor": "#E0E0E0",
                "gridwidth": 0.5,
                "showgrid": True,
                "showline": True,
                "zeroline": False,
                "tickfont": {"size": 9, "color": "#000000"},
                "mirror": True,
                "ticks": "outside",
                "ticklen": 5,
                "tickcolor": "#000000",
            },
            showlegend=True,
            legend={
                "orientation": "v",
                "yanchor": "top",
                "y": 0.98,
                "xanchor": "left",
                "x": 1.01,
                "bgcolor": "rgba(255, 255, 255, 0.9)",
                "bordercolor": "#CCCCCC",
                "borderwidth": 1,
                "font": {"size": 9, "color": "#555555"},
            },
        )

        return fig
