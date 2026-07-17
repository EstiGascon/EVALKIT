from datetime import datetime

import earthkit.data as ekd  # type: ignore
import numpy as np  # type: ignore
import pandas as pd  # type: ignore
import plotly.graph_objects as go
import xarray as xr  # type: ignore
from earthkit.geo.distance import nearest_point_haversine  # type: ignore
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
        # Prefer valid_time coordinate when available — earthkit provides it
        # as datetime64 and it avoids the timedelta->datetime conversion entirely.
        for coord_name in ("valid_time", "valid_datetime"):
            if coord_name in data_array.coords:
                vt = data_array.coords[coord_name]
                if np.issubdtype(vt.dtype, np.datetime64):
                    return pd.DatetimeIndex(vt.values)

        # Fall back to computing absolute times from step + base time.
        steps = data_array.coords["step"].values

        date_str = metadata["date"]
        if "-" in date_str:
            reference_time = pd.to_datetime(date_str, format="%Y-%m-%d")
        else:
            reference_time = pd.to_datetime(date_str, format="%Y%m%d")

        if "time" in metadata:
            time_val = metadata["time"]
            hours = int(str(time_val).split(":")[0]) if ":" in str(time_val) else int(time_val)
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

    @staticmethod
    def _is_precipitation_param(parameter: str) -> bool:
        """Return True for accumulated precipitation parameters."""
        return parameter in {"tp", "lsp", "cp", "sf"}

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
        # ws is a derived parameter (sqrt(10u² + 10v²)) — it has no GRIB shortName.
        if parameter == "ws":
            return self._compute_wind_speed(data_source)

        if hasattr(data_source, "sel"):
            # Try param= first (earthkit maps this to shortName), fallback to shortName=
            selected_data = data_source.sel(param=parameter)
            if len(selected_data) == 0:
                selected_data = data_source.sel(shortName=parameter)

            if len(selected_data) > 0:
                try:
                    xr_data = selected_data.to_xarray()
                except NotImplementedError:
                    # earthkit >=0.17: sel() on some FieldList types returns a
                    # MaskFieldList whose to_xarray() is abstract. Materialize first.
                    from earthkit.data import FieldList as _EkFL
                    xr_data = _EkFL.from_fields(list(selected_data)).to_xarray()
                except Exception:
                    try:
                        from earthkit.data import FieldList as _EkFL
                        xr_data = _EkFL.from_fields(list(selected_data)).to_xarray()
                    except Exception:
                        xr_data = None
            else:
                xr_data = None

            if xr_data is None or (isinstance(xr_data, xr.Dataset) and not xr_data.data_vars):
                raise ValueError(f"Parameter '{parameter}' not found in dataset.")
        else:
            xr_data = (
                data_source
                if isinstance(data_source, xr.DataArray | xr.Dataset)
                else data_source.to_xarray()
            )

        if isinstance(xr_data, xr.Dataset):
            if not xr_data.data_vars:
                raise ValueError(f"Parameter '{parameter}' not found in dataset.")
            if parameter in xr_data.data_vars:
                return xr_data[parameter]
            return xr_data[list(xr_data.data_vars)[0]]

        return xr_data

    def _compute_wind_speed(self, data_source) -> xr.DataArray:
        """Compute 10m wind speed from U and V components.

        Parameters
        ----------
        data_source : earthkit or xarray object
            Dataset containing 10u and 10v fields

        Returns
        -------
        xr.DataArray
            Wind speed DataArray

        """
        if hasattr(data_source, "sel"):
            def _sel_to_xarray(ds, param):
                sel = ds.sel(param=param)
                if len(sel) == 0:
                    sel = ds.sel(shortName=param)
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
            # earthkit converts shortName to a data variable named after it
            u_xr = xr_full[["10u"]] if "10u" in xr_full else xr_full
            v_xr = xr_full[["10v"]] if "10v" in xr_full else xr_full

        if isinstance(u_xr, xr.Dataset):
            u_da = u_xr[list(u_xr.data_vars)[0]]
        else:
            u_da = u_xr

        if isinstance(v_xr, xr.Dataset):
            v_da = v_xr[list(v_xr.data_vars)[0]]
        else:
            v_da = v_xr

        ws = np.sqrt(u_da**2 + v_da**2)
        ws.name = "ws"
        return ws

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
            ekd.from_source("file", data_source).to("fieldlist")
            if isinstance(data_source, str)
            else data_source
        )
        return self._preprocess_data(dataset, parameter)

    def _extract_parameter_at_point(
        self, data_source, parameter: str, lat: float, lon: float
    ) -> xr.DataArray:
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
        xr.DataArray
            Time series at the nearest gridpoint with 'step' (and optionally
            'number') dimensions.

        """
        if parameter == "ws":
            u_point = self._extract_parameter_at_point(data_source, "10u", lat, lon)
            v_point = self._extract_parameter_at_point(data_source, "10v", lat, lon)
            ws = np.sqrt(u_point**2 + v_point**2)
            ws.name = "ws"
            return ws

        # Non-earthkit data: fall back to full xarray path
        if not hasattr(data_source, "sel") or isinstance(
            data_source, xr.Dataset | xr.DataArray
        ):
            xr_data = self._preprocess_data(data_source, parameter)
            return self._extract_nearest_gridpoint(xr_data, lat, lon)

        # Select parameter from FieldList
        selected = data_source.sel(param=parameter)
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

        # Find nearest gridpoint index from the first field.
        # Some fields produced by post-processing (e.g. 6-hourly precipitation
        # built via FieldList.from_array) may have inconsistent grid metadata
        # that triggers "Grid description is wrong or inconsistent" in ecCodes
        # when to_latlon() or .values is called.  Scan through fields to find
        # one that works, and fall back to the xarray slow path if none do.
        latlon = None
        first_field = None
        for candidate in selected:
            try:
                latlon = candidate.to_latlon()
                # sanity check .values access too
                _ = candidate.values
                first_field = candidate
                break
            except Exception as _ll_err:
                continue

        if latlon is None or first_field is None:
            print(
                f"[WARN _extract_parameter_at_point] earthkit fast path failed "
                f"for '{parameter}' (grid metadata issue). Falling back to xarray."
            )
            xr_data = self._preprocess_data(data_source, parameter)
            return self._extract_nearest_gridpoint(xr_data, lat, lon)

        idx, _ = nearest_point_haversine(
            [lat, lon], (latlon["lat"], latlon["lon"])
        )

        # Collect (step, number) → value for every field; skip any that fail.
        step_set = set()
        number_set = set()
        records = {}
        skipped = 0
        for field in selected:
            try:
                step = field.metadata("step")
                md = field.metadata()
                number = md.get("number", None)
                val = float(field.values[idx])
            except Exception:
                skipped += 1
                continue
            step_set.add(step)
            if number is not None:
                number_set.add(number)
            records[(step, number)] = val

        if skipped:
            print(
                f"[WARN _extract_parameter_at_point] Skipped {skipped} fields "
                f"with bad grid metadata for '{parameter}'."
            )

        if not records:
            print(
                f"[WARN _extract_parameter_at_point] No usable fields for "
                f"'{parameter}' via fast path. Falling back to xarray."
            )
            xr_data = self._preprocess_data(data_source, parameter)
            return self._extract_nearest_gridpoint(xr_data, lat, lon)

        unique_steps = sorted(step_set)
        step_coord = np.array(
            [np.timedelta64(int(s), "h") for s in unique_steps]
        )

        if number_set:
            unique_numbers = sorted(number_set)
            data = np.full((len(unique_numbers), len(unique_steps)), np.nan)
            num_map = {n: i for i, n in enumerate(unique_numbers)}
            step_map = {s: i for i, s in enumerate(unique_steps)}
            for (step, number), val in records.items():
                if number is not None:
                    data[num_map[number], step_map[step]] = val
            result = xr.DataArray(
                data,
                dims=["number", "step"],
                coords={"number": unique_numbers, "step": step_coord},
                name=parameter,
            )
        else:
            data = np.full(len(unique_steps), np.nan)
            step_map = {s: i for i, s in enumerate(unique_steps)}
            for (step, _), val in records.items():
                data[step_map[step]] = val
            result = xr.DataArray(
                data,
                dims=["step"],
                coords={"step": step_coord},
                name=parameter,
            )

        return result

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
        # Observation precipitation values come from VINO already in mm;
        # no unit conversion is needed regardless of target_unit.

        return obs_values

    def _extract_observation_timeseries(
        self,
        meteogram_data: dict,
        station_id: str,
        target_unit: str,
        parameter: str,
        time_range: tuple = None,
    ) -> xr.DataArray | None:
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

        # VINO observations are per-period amounts (e.g. 6-hourly totals) and
        # forecast precipitation is already de-accumulated into matching periods
        # by _calculate_6h_precipitation(), so no cumsum is needed here.

        return xr.DataArray(
            converted_values,
            coords={"t": obs_times},
            dims=["t"],
            name=parameter,
        )

    def _get_forecast_time_range(self, meteogram_data: dict) -> tuple:
        """Extract time range from forecast metadata.

        Computes the time range from metadata (date, time, steps) without
        loading any field data, avoiding expensive to_xarray() conversions.

        Parameters
        ----------
        meteogram_data : dict
            Meteogram data dictionary

        Returns
        -------
        tuple or None
            (start_time, end_time) or None

        """
        for data_type in ["cf", "pf", "fc"]:
            if data_type in meteogram_data:
                meta = meteogram_data[data_type].get("metadata", {})
                if "date" in meta and "steps" in meta:
                    date_str = meta["date"]
                    if "-" in date_str:
                        ref = pd.to_datetime(date_str, format="%Y-%m-%d")
                    else:
                        ref = pd.to_datetime(date_str, format="%Y%m%d")
                    if "time" in meta:
                        time_val = meta["time"]
                        hours = (
                            int(str(time_val).split(":")[0])
                            if ":" in str(time_val)
                            else int(time_val)
                        )
                        ref = ref + pd.Timedelta(hours=hours)
                    steps = [int(s) for s in meta["steps"]]
                    start = ref + pd.Timedelta(hours=min(steps))
                    end = ref + pd.Timedelta(hours=max(steps))
                    return (start, end)

        return None

    def _generate_plot_title(
        self,
        parameter: str,
        lat: float,
        lon: float,
        forecast_date: str = None,
        forecast_time: str = None,
        station_id: str = None,
        model_class: str = "",
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

        model_label = ""
        if model_class:
            model_names = {"ifs": "IFS-ENS", "aifs": "AIFS-ENS", "aifs-single": "AIFS-Single", "ifs-4km": "IFS 4.4km", "custom": "Custom"}
            model_label = model_names.get(model_class, model_class.upper())

        title_parts = []
        if model_label:
            title_parts.append(f"Meteogram ({model_label}): {param_config['title']}")
        else:
            title_parts.append(f"Meteogram: {param_config['title']}")
        title_parts.append(f"Location: {location_str} | Forecast: {datetime_info}")

        return "\n".join(title_parts)

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
        non_step_dims = [d for d in data_array.dims if d != "step"]
        if not non_step_dims:
            raise ValueError(
                f"No ensemble dimension found in data for box plot. "
                f"Dims: {data_array.dims}."
            )
        ensemble_dim = non_step_dims[0]

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
                alignmentgroup="ensemble",
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
                    alignmentgroup="ensemble",
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
        model_class: str = "",
        step_frequency: int = None,
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

        # Parameters for which observation overlay is meaningful and compatible.
        # Excluded: 10u/10v (components, not scalar speed), msl, and other
        # parameters for which no VINO observation counterpart exists.
        _OBS_SUPPORTED_PARAMS = {"2t", "tp", "cp", "lsp", "ws"}

        if plot_types is None:
            if "fc" in meteogram_data and "cf" not in meteogram_data and "pf" not in meteogram_data:
                # AIFS-single: only a deterministic fc line
                plot_types = ["fc_line"]
            else:
                plot_types = ["box", "cf_line"]
                if "fc" in meteogram_data:
                    plot_types.append("fc_line")
            if (
                not skip_observations
                and "observations" in meteogram_data
                and parameter in _OBS_SUPPORTED_PARAMS
            ):
                plot_types.append("obs_line")

        forecast_date = None
        forecast_time = None
        for data_type in ["cf", "pf", "fc"]:
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
            parameter, lat, lon, forecast_date, forecast_time, nearest_station,
            model_class=model_class,
        )

        time_range = None
        if nearest_station and "obs_line" in plot_types:
            time_range = self._get_forecast_time_range(meteogram_data)

        fig = go.Figure()

        def _filter_by_step_freq(da, freq):
            """Keep only steps whose hour value is divisible by *freq*."""
            if freq is None or "step" not in da.dims:
                return da
            steps_h = da.coords["step"].values / np.timedelta64(1, "h")
            mask = np.asarray(steps_h % freq == 0)
            kept = da.isel(step=mask)
            return kept

        if "cf" in meteogram_data and "cf_line" in plot_types:
            cf_dataset = meteogram_data["cf"]["dataset"]
            cf_metadata = meteogram_data["cf"]["metadata"]
            cf_point = self._extract_parameter_at_point(
                cf_dataset, parameter, lat, lon
            )

            # Drop any unexpected singleton non-step dimensions (e.g., stray
            # number=0).  'step' is always preserved so _get_absolute_times
            # can find it even when only a single step is present.
            _stray_dims = [
                d for d in cf_point.dims
                if d != "step" and cf_point.sizes[d] == 1
            ]
            if _stray_dims:
                cf_point = cf_point.squeeze(_stray_dims, drop=True)

            cf_point = _filter_by_step_freq(cf_point, step_frequency)

            cf_point, _ = self.styling_config.transform_data_and_levels(
                cf_point, parameter, [], target_unit,
                model_class=model_class,
            )

            time_coords = self._get_absolute_times(cf_point, cf_metadata)

            if self._is_precipitation_param(parameter):
                # 6-hourly accumulation: render as bars centred on the valid time.
                fig.add_trace(
                    go.Bar(
                        x=time_coords,
                        y=cf_point.values,
                        name="Control Forecast",
                        marker_color=self.color_palette["cf"],
                        opacity=0.7,
                    )
                )
            else:
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
            pf_point = self._extract_parameter_at_point(
                pf_dataset, parameter, lat, lon
            )

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

            pf_point = _filter_by_step_freq(pf_point, step_frequency)

            pf_point, _ = self.styling_config.transform_data_and_levels(
                pf_point, parameter, [], target_unit,
                model_class=model_class,
            )

            box_traces = self._create_box_traces(pf_point, pf_metadata)
            for trace in box_traces:
                fig.add_trace(trace)

        if "fc" in meteogram_data and "fc_line" in plot_types:
            fc_dataset = meteogram_data["fc"]["dataset"]
            fc_metadata = meteogram_data["fc"]["metadata"]
            fc_point = self._extract_parameter_at_point(
                fc_dataset, parameter, lat, lon
            )

            # Drop any unexpected singleton non-step dimensions; preserve
            # 'step' always so _get_absolute_times can find it even when only
            # a single step is present.
            _stray_dims = [
                d for d in fc_point.dims
                if d != "step" and fc_point.sizes[d] == 1
            ]
            if _stray_dims:
                fc_point = fc_point.squeeze(_stray_dims, drop=True)

            fc_point = _filter_by_step_freq(fc_point, step_frequency)

            fc_point, _ = self.styling_config.transform_data_and_levels(
                fc_point, parameter, [], target_unit,
                model_class=model_class,
            )

            time_coords = self._get_absolute_times(fc_point, fc_metadata)

            _fc_det_names = {
                "aifs-single": "AIFS-Single Forecast",
                "ifs-4km": "IFS 4.4km Forecast",
            }
            _fc_label = _fc_det_names.get(model_class, f"{model_class.upper()} Forecast")

            if self._is_precipitation_param(parameter):
                fig.add_trace(
                    go.Bar(
                        x=time_coords,
                        y=fc_point.values,
                        name=_fc_label,
                        marker_color=self.color_palette["cf"],
                        opacity=0.7,
                    )
                )
            else:
                fig.add_trace(
                    go.Scatter(
                        x=time_coords,
                        y=fc_point.values,
                        mode="lines",
                        name=_fc_label,
                        line={
                            "color": self.color_palette["cf"],
                            "width": 3,
                            "dash": "dash",
                        },
                    )
                )

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
            margin={"l": 70, "r": 40, "t": 100, "b": 120},
            barmode="overlay" if self._is_precipitation_param(parameter) else None,
            boxmode="overlay",
            xaxis={
                "type": "date",
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
                "rangemode": "tozero" if self._is_precipitation_param(parameter) else "normal",
            },
            showlegend=True,
            legend={
                "orientation": "h",
                "yanchor": "top",
                "y": -0.18,
                "xanchor": "center",
                "x": 0.5,
                "bgcolor": "rgba(255, 255, 255, 0.9)",
                "bordercolor": "#CCCCCC",
                "borderwidth": 1,
                "font": {"size": 9, "color": "#555555"},
            },
        )

        return fig
