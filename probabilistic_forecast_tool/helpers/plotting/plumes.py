from datetime import datetime, timedelta

import earthkit.data as ekd  # type: ignore
import numpy as np  # type: ignore
import plotly.graph_objects as go  # type: ignore
from earthkit.geo.distance import nearest_point_haversine  # type: ignore
from helpers.parameter_config_manager import ParameterConfigManager
from helpers.styling_config import StylingConfiguration


class PlumesPlotting:
    """Create plume diagrams showing ensemble forecast spread.

    Generates interactive Plotly visualizations with quantile-based shading,
    ensemble member traces, control forecasts, and observational data.
    """

    def __init__(self, styling_config=StylingConfiguration()):
        """Initialize plumes plotting class.

        Parameters
        ----------
        styling_config : StylingConfiguration, optional
            Configuration for plot styling, colors, and units

        """
        self.styling_config = styling_config

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string handling both YYYYMMDD and YYYY-MM-DD formats.

        Parameters
        ----------
        date_str : str
            Date string in either YYYYMMDD or YYYY-MM-DD format

        Returns
        -------
        datetime
            Parsed datetime object

        """
        if "-" in date_str:
            return datetime.strptime(date_str, "%Y-%m-%d")
        else:
            return datetime.strptime(date_str, "%Y%m%d")

    def _parse_datetime_with_hour(self, date_str: str, time_str: str) -> datetime:
        """Parse date and time strings handling both date formats.

        Parameters
        ----------
        date_str : str
            Date string in either YYYYMMDD or YYYY-MM-DD format
        time_str : str
            Time string in format "HH:MM:SS"

        Returns
        -------
        datetime
            Parsed datetime object with hour

        """
        date_obj = self._parse_date(date_str)
        hour = int(time_str.split(":")[0])
        return date_obj.replace(hour=hour)

    def _get_color_scheme_quantile(self) -> dict:
        """Get green color scheme for quantile shading.

        Returns
        -------
        dict
            Color scheme with keys: lightest, light, medium, dark

        """
        return {
            "lightest": "rgba(144, 238, 144, 0.2)",
            "light": "rgba(50, 205, 50, 0.3)",
            "medium": "rgba(34, 139, 34, 0.4)",
            "dark": "rgba(0, 100, 0, 0.5)",
        }

    def _calculate_quantile_shading(self, ensemble_ts: np.ndarray) -> dict:
        """Calculate quantile ranges for ensemble data.

        Parameters
        ----------
        ensemble_ts : np.ndarray
            Ensemble time series [time_steps, ensemble_members]

        Returns
        -------
        dict
            Quantile arrays for each time step

        """
        quantiles = [0.0, 0.05, 0.25, 0.50, 0.75, 0.95, 1.0]
        quantile_names = ["q0", "q05", "q25", "q50", "q75", "q95", "q100"]

        if ensemble_ts.ndim == 1:
            ensemble_ts = ensemble_ts.reshape(1, -1)

        n_time_steps = ensemble_ts.shape[0]
        quantile_data = {name: np.zeros(n_time_steps) for name in quantile_names}

        for t in range(n_time_steps):
            calculated_quantiles = np.quantile(ensemble_ts[t, :], quantiles)
            for i, q_name in enumerate(quantile_names):
                quantile_data[q_name][t] = calculated_quantiles[i]

        return quantile_data

    def _add_quantile_shading(
        self,
        fig: go.Figure,
        time_axis: list,
        ensemble_ts: np.ndarray,
        colors: dict,
        metadata: dict,
    ) -> None:
        """Add quantile shading bands to the figure.

        Creates three shaded regions (0-100%, 5-95%, 25-75%) with hover info
        and a median line.

        Parameters
        ----------
        fig : go.Figure
            Plotly figure to add traces to
        time_axis : list
            List of datetime objects for x-axis
        ensemble_ts : np.ndarray
            Ensemble time series [time_steps, members]
        colors : dict
            Color scheme dictionary
        metadata : dict
            Forecast metadata with 'date' and 'time'

        """
        quantile_data = self._calculate_quantile_shading(ensemble_ts)

        forecast_datetime = self._parse_datetime_with_hour(metadata["date"], metadata["time"])

        shading_bands = [
            {
                "lower": quantile_data["q0"],
                "upper": quantile_data["q100"],
                "color": colors["lightest"],
                "name": "0%-100% range",
                "legendgroup": "q0_100",
            },
            {
                "lower": quantile_data["q05"],
                "upper": quantile_data["q95"],
                "color": colors["light"],
                "name": "5%-95% range",
                "legendgroup": "q5_95",
            },
            {
                "lower": quantile_data["q25"],
                "upper": quantile_data["q75"],
                "color": colors["medium"],
                "name": "25%-75% range (IQR)",
                "legendgroup": "q25_75",
            },
        ]

        for band in shading_bands:
            x_coords = time_axis + time_axis[::-1]
            y_coords = np.concatenate([band["upper"], band["lower"][::-1]])

            fig.add_trace(
                go.Scatter(
                    x=x_coords,
                    y=y_coords,
                    fill="toself",
                    fillcolor=band["color"],
                    line={"color": "rgba(255,255,255,0)"},
                    name=band["name"],
                    legendgroup=band["legendgroup"],
                    showlegend=True,
                    hoverinfo="none",
                )
            )

            middle_values = (band["upper"] + band["lower"]) / 2

            hover_template = (
                f"<b>{band['name']}</b><br>"
                f"Lower: %{{customdata[0]:.2f}}<br>"
                f"Upper: %{{customdata[1]:.2f}}<br>"
                "<extra></extra>"
            )

            fig.add_trace(
                go.Scatter(
                    x=time_axis,
                    y=middle_values,
                    mode="lines",
                    line={"color": "rgba(255,255,255,0)", "width": 20},
                    name=band["name"] + " (hover)",
                    legendgroup=band["legendgroup"],
                    showlegend=False,
                    hovertemplate=hover_template,
                    customdata=list(
                        zip(band["lower"], band["upper"], strict=False)
                    ),
                )
            )

        # Add median line
        median_values = quantile_data["q50"]
        forecast_steps = [
            int((vt - forecast_datetime).total_seconds() / 3600) for vt in time_axis
        ]

        fig.add_trace(
            go.Scatter(
                x=time_axis,
                y=median_values,
                mode="lines",
                line={"color": colors["dark"], "width": 5},
                name="Median (50%)",
                legendgroup="median",
                showlegend=True,
                hovertemplate="<b>Median</b><br>Value: %{y:.2f}<br><extra></extra>",
                customdata=forecast_steps,
            )
        )

    def _extract_nearest_gridpoint(self, data, lat: float, lon: float) -> np.ndarray:
        """Extract data at nearest grid point.

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
        np.ndarray
            Extracted data

        """
        if hasattr(data, "to_xarray"):
            try:
                xr_data = data.to_xarray()
            except NotImplementedError:
                # earthkit >=0.17: MaskFieldList.to_xarray() is abstract.
                # Convert to concrete SimpleFieldList first.
                from earthkit.data import FieldList as _EkFL
                xr_data = _EkFL.from_fields(list(data)).to_xarray()
        else:
            xr_data = data

        if hasattr(data, "to_latlon"):
            latlon = data.to_latlon()
            lats = latlon["lat"]
            lons = latlon["lon"]
        else:
            lat_coord = xr_data.coords.get("latitude")
            if lat_coord is None:
                lat_coord = xr_data.coords.get("lat")

            lon_coord = xr_data.coords.get("longitude")
            if lon_coord is None:
                lon_coord = xr_data.coords.get("lon")

            if lat_coord is None or lon_coord is None:
                raise ValueError("Cannot find latitude/longitude coordinates in data")

            if lat_coord.ndim == 1 and lon_coord.ndim == 1:
                lats = lat_coord.values
                lons = lon_coord.values
            else:
                lats = lat_coord.values.flatten()
                lons = lon_coord.values.flatten()

        idx, distance = nearest_point_haversine([lat, lon], (lats, lons))

        if "values" in xr_data.dims:
            point_data = xr_data.isel(values=idx)
        else:
            spatial_dims = [
                d
                for d in xr_data.dims
                if d not in ["step", "number", "ensemble", "member"]
            ]

            if len(spatial_dims) == 1:
                point_data = xr_data.isel({spatial_dims[0]: idx})
            else:
                lat_name = "latitude" if "latitude" in xr_data.coords else "lat"
                lon_name = "longitude" if "longitude" in xr_data.coords else "lon"
                lat_coord = xr_data.coords[lat_name]

                if lat_coord.ndim == 1:
                    lat_idx, lon_idx = np.unravel_index(
                        idx, (len(lat_coord), len(xr_data.coords[lon_name]))
                    )
                    point_data = xr_data.isel({lat_name: lat_idx, lon_name: lon_idx})
                else:
                    lat_idx, lon_idx = np.unravel_index(idx, lat_coord.shape)
                    point_data = xr_data.isel(
                        {lat_coord.dims[0]: lat_idx, lat_coord.dims[1]: lon_idx}
                    )

        # point_data may be an xr.Dataset (from earthkit to_xarray) or an
        # xr.DataArray (e.g. computed ws). Handle both without AttributeError.
        if hasattr(point_data, "data_vars") and len(point_data.data_vars) > 0:
            return point_data[list(point_data.data_vars)[0]]

        return point_data

    def _find_nearest_station(
        self, forecast_data: dict, lat: float, lon: float, tolerance: float = 0.1
    ) -> str:
        """Find nearest observation station within tolerance distance.

        Parameters
        ----------
        forecast_data : dict
            Forecast data dictionary with observations
        lat : float
            Target latitude
        lon : float
            Target longitude
        tolerance : float, optional
            Maximum distance in degrees (default: 0.1)

        Returns
        -------
        str or None
            Station ID if found within tolerance, None otherwise

        """
        obs_data = forecast_data.get("observations")
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

        Supports temperature (Kelvin to Celsius) and precipitation (m to mm).

        Parameters
        ----------
        obs_values : np.ndarray
            Observation values to convert
        parameter : str
            Parameter name
        target_unit : str
            Target unit (e.g., 'celsius', 'mm')

        Returns
        -------
        np.ndarray
            Converted values

        """
        param_config = ParameterConfigManager()
        category = param_config.get_parameter_category(parameter)

        if category == "temperature" and target_unit.lower() == "celsius":
            return obs_values - 273.15
        # Observation precipitation values come from VINO already in mm;
        # no unit conversion is needed regardless of target_unit.

        return obs_values

    def _get_forecast_time_range(self, metadata: dict) -> tuple:
        """Extract forecast time range from metadata.

        Parameters
        ----------
        metadata : dict
            Forecast metadata

        Returns
        -------
        tuple
            (start_time, end_time)

        """
        init_datetime = self._parse_datetime_with_hour(metadata["date"], metadata["time"])

        forecast_steps = [int(step) for step in metadata["steps"]]
        start_time = init_datetime + timedelta(hours=forecast_steps[0])
        end_time = init_datetime + timedelta(hours=forecast_steps[-1])

        return (start_time, end_time)

    def _extract_observation_timeseries(
        self,
        forecast_data: dict,
        station_id: str,
        target_unit: str,
        parameter: str,
        time_range: tuple,
    ) -> tuple:
        """Extract and convert observation timeseries for a station.

        Filters observations to specified time range and converts units.

        Parameters
        ----------
        forecast_data : dict
            Forecast data dictionary with observations
        station_id : str
            Station identifier
        target_unit : str
            Target unit for conversion
        parameter : str
            Parameter name
        time_range : tuple
            (start_time, end_time) for filtering

        Returns
        -------
        tuple
            (obs_times, obs_values) or (None, None) if not found

        """
        obs_data = forecast_data.get("observations")
        if not obs_data or "timeseries_data" not in obs_data:
            return None, None

        station_id_str = str(station_id)
        if station_id_str not in obs_data["timeseries_data"]:
            return None, None

        station_data = obs_data["timeseries_data"][station_id_str]
        if "timeseries" not in station_data:
            return None, None

        obs_times = []
        obs_values = []

        start_time, end_time = time_range
        for entry in station_data["timeseries"]:
            if "datetime" in entry and "value" in entry:
                obs_datetime = entry["datetime"]
                if start_time <= obs_datetime <= end_time:
                    obs_times.append(obs_datetime)
                    obs_values.append(entry["value"])

        if not obs_times:
            return None, None

        converted_values = self._convert_observation_units(
            np.array(obs_values), parameter, target_unit
        )

        return obs_times, converted_values

    @staticmethod
    def _is_precipitation_param(parameter: str) -> bool:
        """Return True for accumulated precipitation parameters."""
        return parameter in {"tp", "lsp", "cp", "sf"}

    def _load_and_select_data(self, data_source, parameter: str):
        """Load and select parameter from data source.

        Parameters
        ----------
        data_source : str or earthkit object
            File path or loaded dataset
        parameter : str
            Parameter to select (e.g., 'tp', '2t')

        Returns
        -------
        earthkit dataset

        """
        data = (
            ekd.from_source("file", data_source).to("fieldlist")
            if isinstance(data_source, str)
            else data_source
        )

        # ws is a derived parameter — compute it from 10u and 10v components.
        if parameter == "ws":
            return self._compute_wind_speed_dataset(data)

        if hasattr(data, "sel"):
            try:
                return data.sel(shortName=parameter)
            except:  # noqa: E722
                try:
                    return data.sel({"parameter.variable": parameter})
                except:  # noqa: E722
                    return data

        return data

    def _compute_wind_speed_dataset(self, data_source):
        """Compute 10m wind speed xarray DataArray from U/V components.

        Parameters
        ----------
        data_source : earthkit or xarray object
            Dataset containing 10u and 10v fields

        Returns
        -------
        xr.DataArray
            Wind speed DataArray

        """
        import xarray as xr  # noqa: PLC0415

        if hasattr(data_source, "sel"):
            def _sel_to_xarray(ds, param):
                sel = ds.sel({"parameter.variable": param})
                try:
                    return sel.to_xarray()
                except NotImplementedError:
                    from earthkit.data import FieldList as _EkFL
                    return _EkFL.from_fields(list(sel)).to_xarray()
            u_xr = _sel_to_xarray(data_source, "10u")
            v_xr = _sel_to_xarray(data_source, "10v")
        else:
            xr_full = (
                data_source
                if isinstance(data_source, xr.Dataset)
                else data_source.to_xarray()
            )
            u_xr = xr_full[["10u"]] if "10u" in xr_full else xr_full
            v_xr = xr_full[["10v"]] if "10v" in xr_full else xr_full

        u_da = u_xr[list(u_xr.data_vars)[0]] if isinstance(u_xr, xr.Dataset) else u_xr
        v_da = v_xr[list(v_xr.data_vars)[0]] if isinstance(v_xr, xr.Dataset) else v_xr

        ws = np.sqrt(u_da**2 + v_da**2)
        ws.name = "ws"
        return ws

    def _extract_parameter_at_point(
        self, data_source, parameter: str, lat: float, lon: float
    ) -> np.ndarray:
        """Extract parameter time series at nearest gridpoint from earthkit data.

        For large datasets on reduced Gaussian grids, avoids creating massive
        intermediate xarray datasets by extracting gridpoint values directly
        from the earthkit FieldList.

        Parameters
        ----------
        data_source : earthkit FieldList or xarray object
            Input data
        parameter : str
            Parameter short name (e.g. '2t', 'tp')
        lat : float
            Target latitude
        lon : float
            Target longitude

        Returns
        -------
        np.ndarray
            Values at the nearest gridpoint. For ensemble data the shape is
            (steps, members); for single-member data the shape is (steps,).

        """
        if parameter == "ws":
            u_vals = self._extract_parameter_at_point(data_source, "10u", lat, lon)
            v_vals = self._extract_parameter_at_point(data_source, "10v", lat, lon)
            return np.sqrt(u_vals**2 + v_vals**2)

        # Non-earthkit data: fall back to full xarray path
        import xarray as xr  # noqa: PLC0415
        if not hasattr(data_source, "sel") or isinstance(
            data_source, xr.Dataset | xr.DataArray
        ):
            data = self._load_and_select_data(data_source, parameter)
            point = self._extract_nearest_gridpoint(data, lat, lon)
            return np.squeeze(point.values) if hasattr(point, "values") else np.squeeze(point)

        # Select parameter from FieldList
        selected = data_source.sel({"parameter.variable": parameter})
        if len(selected) == 0:
            selected = data_source.sel(shortName=parameter)
        if len(selected) == 0:
            # Manual fallback: iterate fields and match by shortName metadata
            manual_fields = []
            for f in data_source:
                try:
                    sn = f.metadata("shortName")
                    if sn == parameter:
                        manual_fields.append(f)
                except Exception:
                    pass
            if manual_fields:
                from earthkit.data import FieldList as _EkFL
                selected = _EkFL.from_fields(manual_fields)
        if len(selected) == 0:
            # Collect diagnostic info for debugging
            ds_type = type(data_source).__name__
            n_fields = len(data_source)
            found_params = set()
            for f in data_source:
                try:
                    found_params.add(f.metadata("shortName"))
                except Exception:
                    found_params.add("<unknown>")
            raise ValueError(
                f"Parameter '{parameter}' not found in dataset. "
                f"Dataset type: {ds_type}, fields: {n_fields}, "
                f"available params: {sorted(found_params)}"
            )

        # Find nearest gridpoint index from the first field
        first_field = selected[0]
        idx, _ = nearest_point_haversine(
            [lat, lon], (first_field.geography.latitudes().flatten(), first_field.geography.longitudes().flatten())
        )

        # Collect (step, number) → value for every field
        step_set = set()
        number_set = set()
        records = {}
        for field in selected:
            step = field.metadata("step")
            md = field.metadata()
            number = md.get("number", None)
            val = float(field.values[idx])
            step_set.add(step)
            if number is not None:
                number_set.add(number)
            records[(step, number)] = val

        unique_steps = sorted(step_set)

        if number_set:
            unique_numbers = sorted(number_set)
            # Shape: (steps, members) — expected by create_plumes_plot
            data = np.full((len(unique_steps), len(unique_numbers)), np.nan)
            step_map = {s: i for i, s in enumerate(unique_steps)}
            num_map = {n: i for i, n in enumerate(unique_numbers)}
            for (step, number), val in records.items():
                if number is not None:
                    data[step_map[step], num_map[number]] = val
            return data
        else:
            data = np.full(len(unique_steps), np.nan)
            step_map = {s: i for i, s in enumerate(unique_steps)}
            for (step, _), val in records.items():
                data[step_map[step]] = val
            return data

    def create_plumes_plot(
        self,
        forecast_data: dict,
        parameter: str,
        lat: float,
        lon: float,
        target_unit: str = None,
        figsize: tuple[int, int] = (1200, 600),
        forecast_type: str = "cf",
        model_class: str = "",
        step_frequency: int = None,
    ) -> go.Figure:
        """Create interactive plume diagram with ensemble spread.

        Combines quantile shading, ensemble members, control forecast,
        and observations into a comprehensive visualization.

        Parameters
        ----------
        forecast_data : dict
            Dictionary containing forecast and observation data with structure:
            {
                'cf': {'dataset': ..., 'metadata': {...}},
                'pf': {'dataset': ..., 'metadata': {...}},
                'observations': {'stations_gdf': ..., 'timeseries_data': ...}
            }
        parameter : str
            Parameter code (e.g., '2t', 'tp', 'msl', 'z')
        lat : float
            Latitude for point extraction
        lon : float
            Longitude for point extraction
        target_unit : str, optional
            Target display unit (e.g., 'celsius', 'mm', 'hPa')
            Auto-detected if None
        figsize : tuple[int, int], optional
            Figure size (width, height) in pixels (default: 1200x600)
        forecast_type : str, optional
            Forecast to use as control: "cf" (control) or "fc" (high-res)
            Default: "cf"

        Returns
        -------
        go.Figure

        """
        param_config = self.styling_config.choose_color_palette_and_levels(
            parameter, unit=target_unit
        )

        if target_unit is None:
            target_unit = param_config.get("unit", "")

        metadata = forecast_data[forecast_type]["metadata"]

        init_datetime = self._parse_datetime_with_hour(metadata["date"], metadata["time"])

        forecast_steps = [int(step) for step in metadata["steps"]]
        time_axis = [init_datetime + timedelta(hours=step) for step in forecast_steps]

        # Compute step frequency filter indices on the ORIGINAL steps
        if step_frequency and step_frequency > 1:
            keep_idx = [i for i, s in enumerate(forecast_steps) if s % step_frequency == 0]
            print(f"[DEBUG create_plumes_plot] keep_idx kept {len(keep_idx)}/{len(forecast_steps)} steps")
        else:
            keep_idx = None
        # n_orig_steps used for dimension detection before filtering
        n_orig_steps = len(time_axis)

        fig = go.Figure()

        # Process control forecast
        control_ts = None
        if forecast_type in forecast_data:
            control_dataset = forecast_data[forecast_type]["dataset"]
            control_values = self._extract_parameter_at_point(
                control_dataset, parameter, lat, lon
            )

            control_values = np.squeeze(control_values)
            if control_values.ndim > 1:
                control_values = control_values.flatten()

            # Truncate to available time steps then apply step frequency filter
            control_values = control_values[:n_orig_steps]
            if keep_idx is not None:
                valid_idx = [i for i in keep_idx if i < len(control_values)]
                control_values = control_values[valid_idx]
                time_axis_ctrl = [time_axis[i] for i in valid_idx]
            else:
                time_axis_ctrl = time_axis[:len(control_values)]
            # Use filtered time_axis going forward
            time_axis = time_axis_ctrl

            control_ts, _ = self.styling_config.transform_data_and_levels(
                control_values, parameter, [], target_unit,
                model_class=model_class,
            )

        elif keep_idx is not None:
            # No control forecast but still need to filter time_axis
            time_axis = [time_axis[i] for i in keep_idx if i < len(time_axis)]

        # Process ensemble forecast
        ensemble_ts = None
        ensemble_members_count = 0
        if "pf" in forecast_data:
            pf_dataset = forecast_data["pf"]["dataset"]
            ensemble_values = self._extract_parameter_at_point(
                pf_dataset, parameter, lat, lon
            )

            ensemble_values = np.squeeze(ensemble_values)

            # Ensure shape is [time_steps, ensemble_members]
            # Use n_orig_steps for dimension detection (pre-filter count)
            if ensemble_values.ndim == 2:
                # Check which dimension is time
                if ensemble_values.shape[0] == n_orig_steps:
                    ensemble_members_count = ensemble_values.shape[1]
                elif ensemble_values.shape[1] == n_orig_steps:
                    ensemble_values = ensemble_values.T
                    ensemble_members_count = ensemble_values.shape[1]
                else:
                    # Guess based on dimension sizes
                    if ensemble_values.shape[0] < ensemble_values.shape[1]:
                        ensemble_values = ensemble_values.T
                    ensemble_members_count = ensemble_values.shape[1]
            elif ensemble_values.ndim == 1:
                ensemble_values = ensemble_values.reshape(-1, 1)
                ensemble_members_count = 1

            # Apply step frequency filter to ensemble (first dim is time)
            if keep_idx is not None:
                valid_idx = [i for i in keep_idx if i < ensemble_values.shape[0]]
                ensemble_values = ensemble_values[valid_idx]

            ensemble_ts, _ = self.styling_config.transform_data_and_levels(
                ensemble_values, parameter, [], target_unit,
                model_class=model_class,
            )

        # Process observations
        obs_times = None
        obs_values = None
        nearest_station = None

        if "observations" in forecast_data:
            obs_data = forecast_data["observations"]
            if (
                obs_data.get("stations_gdf") is not None
                and obs_data.get("timeseries_data") is not None
            ):
                nearest_station = self._find_nearest_station(forecast_data, lat, lon)
                if nearest_station:
                    time_range = self._get_forecast_time_range(metadata)
                    obs_times, obs_values = self._extract_observation_timeseries(
                        forecast_data,
                        nearest_station,
                        target_unit,
                        parameter,
                        time_range,
                    )

        # Add quantile shading
        if ensemble_ts is not None and ensemble_ts.shape[1] > 1:
            colors = self._get_color_scheme_quantile()
            self._add_quantile_shading(fig, time_axis, ensemble_ts, colors, metadata)

        # Add individual ensemble members (lines for continuous params, skip for precip)
        if ensemble_ts is not None and not self._is_precipitation_param(parameter):
            for i in range(ensemble_members_count):
                fig.add_trace(
                    go.Scatter(
                        x=time_axis,
                        y=ensemble_ts[:, i],
                        mode="lines",
                        line={
                            "color": "rgba(100, 100, 100, 0.4)",
                            "width": 0.8,
                            "dash": "dot",
                        },
                        name="",
                        legendgroup="ensemble",
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )

        # Add control forecast
        if control_ts is not None:
            forecast_datetime = self._parse_datetime_with_hour(metadata["date"], metadata["time"])

            customdata = [
                int((time_point - forecast_datetime).total_seconds() / 3600)
                for time_point in time_axis
            ]

            if self._is_precipitation_param(parameter):
                fig.add_trace(
                    go.Bar(
                        x=time_axis,
                        y=control_ts,
                        name="Control Forecast",
                        marker_color="#FF6600",
                        opacity=0.7,
                        legendgroup="control",
                        showlegend=True,
                        legendrank=1,
                        hovertemplate=(
                            "<b>Control Forecast</b><br>"
                            "Forecast Step: +%{customdata}h<br>"
                            "Value: %{y:.2f}<extra></extra>"
                        ),
                        customdata=customdata,
                    )
                )
            else:
                fig.add_trace(
                    go.Scatter(
                        x=time_axis,
                        y=control_ts,
                        mode="lines",
                        line={"color": "#FF6600", "width": 3},
                        name="Control Forecast",
                        legendgroup="control",
                        showlegend=True,
                        legendrank=1,
                        hovertemplate=(
                            "<b>Control Forecast</b><br>"
                            "Forecast Step: +%{customdata}h<br>"
                            "Value: %{y:.2f}<extra></extra>"
                        ),
                        customdata=customdata,
                    )
                )

        # Add observations
        if obs_times is not None and obs_values is not None:
            fig.add_trace(
                go.Scatter(
                    x=obs_times,
                    y=obs_values,
                    mode="lines+markers",
                    line={"color": "black", "width": 3},
                    marker={"color": "black", "size": 6},
                    name="Observations",
                    legendgroup="observations",
                    showlegend=True,
                    legendrank=0,
                    hovertemplate=(
                        f"<b>Observations</b><br>"
                        f"Value: %{{y:.2f}}<br>"
                        f"Station: {nearest_station}<extra></extra>"
                    ),
                )
            )

        # Create title
        formatted_date = self._parse_date(metadata["date"]).strftime("%d %B %Y")

        location_str = f"{lat:.2f}°, {lon:.2f}°"
        if nearest_station:
            location_str += f" (Station: {nearest_station})"

        model_label = ""
        if model_class:
            model_names = {"ifs": "IFS-ENS", "aifs": "AIFS-ENS", "custom": "Custom"}
            model_label = model_names.get(model_class, model_class.upper())

        if model_label:
            title = (
                f"Plume diagram ({model_label})<br>"
                f"DT {metadata['time'].split(':')[0]}:00 UTC {formatted_date}<br>"
                f"Location: {location_str}<br>{param_config['title']}"
            )
        else:
            title = (
                f"Plume diagram<br>DT {metadata['time'].split(':')[0]}:00 UTC {formatted_date}<br>"
                f"Location: {location_str}<br>{param_config['title']}"
            )

        # Update layout
        fig.update_layout(
            title={"text": title, "x": 0.5, "font": {"size": 14, "family": "Arial"}},
            xaxis={
                "title": "Time",
                "tickformat": "%d-%m-%Y %H:%M",
                "dtick": 21600000,
                "gridcolor": "lightgray",
                "gridwidth": 1,
                "showgrid": True,
                "showline": True,
                "linecolor": "black",
                "linewidth": 1,
                "tickangle": -45,
            },
            yaxis={
                "title": f"{param_config['title']} ({param_config['unit']})",
                "gridcolor": "lightgray",
                "gridwidth": 0.5,
                "showgrid": True,
                "showline": True,
                "linecolor": "black",
                "linewidth": 1,
                "rangemode": "tozero" if self._is_precipitation_param(parameter) else "normal",
            },
            width=figsize[0],
            height=figsize[1],
            hovermode="x unified",
            hoverdistance=50,
            barmode="overlay" if self._is_precipitation_param(parameter) else None,
            legend={
                "orientation": "h",
                "yanchor": "top",
                "y": -0.22,
                "xanchor": "center",
                "x": 0.5,
                "font": {"size": 10, "family": "Arial"},
            },
            margin={"t": 100, "b": 120, "l": 80, "r": 50},
            plot_bgcolor="white",
            paper_bgcolor="white",
        )

        return fig
