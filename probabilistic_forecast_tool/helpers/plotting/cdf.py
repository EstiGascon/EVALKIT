"""CDF plotting module for weather forecast visualization.

This module provides functionality for creating Cumulative Distribution Function (CDF)
plots from weather forecast and climate data. It handles data extraction, processing,
and visualization for various meteorological parameters.
"""

from datetime import datetime

import earthkit.data as ekd
import matplotlib.pyplot as plt
import numpy as np
from earthkit.geo.distance import nearest_point_haversine
from helpers.parameter_config_manager import ParameterConfigManager
from helpers.styling_config import StylingConfiguration


class CDFPlotting:
    """Manager for creating CDF plots from weather forecast and climate data.

    This class handles the complete workflow of creating CDF plots, including:
    - Data loading and preprocessing
    - Parameter-specific aggregation
    - Grid point extraction
    - Unit conversions
    - Plot generation and styling

    Attributes:
        styling_config: Configuration for plot styling and parameter settings
        color_palette: List of colors for plotting multiple scenarios
        line_styles: Available line styles for plot differentiation
        config_file: Path to model configuration file
        param_config: Manager for parameter configuration
        climate_param_map: Mapping of parameter names for climate data

    """

    def __init__(
        self,
        styling_config: StylingConfiguration | None = None,
        config_file: str = "model_config.json",
    ) -> None:
        """Initialize plotting manager with plot classes and styling.

        Args:
            styling_config: Optional custom styling configuration. If None, uses default
            config_file: Path to model configuration JSON file

        """
        self.styling_config = styling_config or StylingConfiguration()
        self.color_palette = self._setup_color_palette()
        self.config_file = config_file
        self.param_config = ParameterConfigManager(config_file)
        self.climate_param_map = self.param_config.get_climate_param_map()

    def _setup_color_palette(self) -> list[str]:
        """Set up the color palette for plotting multiple scenarios.

        Returns:
            List of hex color codes for scenario differentiation

        """
        return [
            "#FF0000",
            "#8000FF",
            "#0033FF",
            "#004DFF",
            "#0066FF",
            "#0080FF",
            "#0099FF",
            "#00B3FF",
            "#00E6FF",
            "#00FFFF",
            "#00FF99",
            "#00FF00",
            "#00B366",
            "#008000",
        ]

    def _determine_line_style(
        self, scenario_name: str, forecast_time: int | None = None
    ) -> str:
        """Determine line style based on scenario characteristics.

        Uses solid lines for D-0 scenarios and 12Z forecasts, dashed for others.

        Args:
            scenario_name: Name of the scenario (e.g., 'D-0_12Z')
            forecast_time: Forecast initialization time in hours (0 or 12)

        Returns:
            Line style string: 'solid' or 'dashed'

        """
        if scenario_name.startswith("D-0"):
            return "solid"
        if forecast_time is not None:
            return "dashed" if forecast_time == 0 else "solid"
        if "00Z" in scenario_name:
            return "dashed"
        return "solid"

    def _ensure_xarray(self, data):
        """Convert data to xarray format if needed.

        Args:
            data: Input data (FieldList, xarray, or compatible format)

        Returns:
            xarray Dataset or DataArray

        Raises:
            ValueError: If data cannot be converted to xarray format

        """
        if hasattr(data, "coords"):
            return data
        if hasattr(data, "to_xarray"):
            try:
                return data.to_xarray()
            except NotImplementedError:
                # earthkit >=0.17: MaskFieldList.to_xarray() is abstract.
                from earthkit.data import FieldList as _EkFL
                return _EkFL.from_fields(list(data)).to_xarray()
        raise ValueError(f"Cannot convert {type(data)} to xarray format")

    def _convert_step_to_hours(self, step_val) -> int:
        """Convert various step formats to hours.

        Supports multiple input formats:
        - numpy timedelta64 objects
        - Python timedelta objects
        - String formats: "24 hours", "2 days"
        - Numeric values (assumed to be hours)
        - Numpy scalars

        Args:
            step_val: Step value in any supported format

        Returns:
            Step value converted to hours as integer

        Raises:
            ValueError: If format is not recognized or conversion fails

        """
        try:
            if hasattr(step_val, "astype") and "timedelta" in str(type(step_val)):
                seconds = step_val.astype("timedelta64[s]").astype(int)
                return int(seconds / 3600)

            if hasattr(step_val, "total_seconds"):
                return int(step_val.total_seconds() / 3600)

            if isinstance(step_val, str):
                step_lower = step_val.lower()
                digits = int("".join(filter(str.isdigit, step_val)))
                if "day" in step_lower:
                    return digits * 24
                return digits

            if isinstance(step_val, int | float):
                if step_val > 1e12:
                    return int(step_val / 3.6e12)
                return int(step_val)

            if hasattr(step_val, "item"):
                return self._convert_step_to_hours(step_val.item())

            raise ValueError(f"Unknown step format: {type(step_val)}")

        except (ValueError, TypeError, AttributeError) as e:
            raise ValueError(f"Cannot convert step value {step_val} to hours: {e}")

    def _handle_wind_components(self, data, parameter: str):
        """Calculate wind speed from U and V components if needed.

        Searches for wind components in standard names (u10, v10) or GRIB parameter
        codes (165, 166) and computes wind speed using Pythagorean theorem.

        Args:
            data: Input data containing wind components
            parameter: Parameter name ('ws' for wind speed)

        Returns:
            Data with wind speed calculated if applicable, otherwise original data

        """
        if parameter != "ws":
            return data

        try:
            xr_data = self._ensure_xarray(data)

            if "u10" in xr_data.data_vars and "v10" in xr_data.data_vars:
                u_data = xr_data["u10"]
                v_data = xr_data["v10"]
            elif "165" in xr_data.data_vars and "166" in xr_data.data_vars:
                u_data = xr_data["165"]
                v_data = xr_data["166"]
            else:
                return data

            wind_speed = np.sqrt(u_data**2 + v_data**2)
            new_data = xr_data.copy()
            new_data["ws"] = wind_speed
            return new_data

        except (ValueError, KeyError, AttributeError) as e:
            print(f"Warning: Could not calculate wind speed: {e}")
            return data

    def _get_coordinate_names(self, xr_data) -> tuple[str, str]:
        """Get the names of latitude and longitude coordinates.

        Checks for common coordinate naming conventions used in weather data.

        Args:
            xr_data: xarray Dataset or DataArray

        Returns:
            Tuple of (latitude_name, longitude_name)

        Raises:
            ValueError: If coordinates cannot be found in the data

        """
        if "latitude" in xr_data.coords:
            return "latitude", "longitude"
        elif "lat" in xr_data.coords:
            return "lat", "lon"
        else:
            raise ValueError("Could not find latitude/longitude coordinates")

    def _determine_accumulation_period_for_forecast(
        self, available_steps_hours: list[int], target_period_hours: int = 24
    ) -> tuple[int, int]:
        """Determine optimal accumulation period from available forecast steps.

        Finds the best start and end steps to create an accumulation period closest
        to the target period using available forecast steps.

        Args:
            available_steps_hours: List of available forecast steps in hours
            target_period_hours: Desired accumulation period in hours

        Returns:
            Tuple of (start_step, end_step) in hours

        """
        if not available_steps_hours:
            return 0, 24

        min_step = min(available_steps_hours)
        max_step = max(available_steps_hours)

        if max_step - min_step >= target_period_hours:
            step_end = max_step
            step_start = max_step - target_period_hours
        else:
            step_start = min_step
            step_end = max_step

        available_start_steps = [s for s in available_steps_hours if s <= step_start]
        if available_start_steps:
            step_start = max(available_start_steps)
        else:
            step_start = min_step

        available_end_steps = [s for s in available_steps_hours if s >= step_end]
        if available_end_steps:
            step_end = min(available_end_steps)
        else:
            step_end = max_step

        return step_start, step_end

    def _apply_parameter_specific_aggregation(
        self, data, parameter: str, step_start: int, step_end: int
    ):
        """Apply parameter-specific temporal aggregation.

        Different parameters require different aggregation methods:
        - Precipitation (tp, sf, ts): accumulation via difference
        - Temperature (2t, ws): temporal mean
        - Maximum parameters (2tmax, 10fg, cape, capeshear): temporal maximum
        - Minimum parameters (2tmin): temporal minimum

        Args:
            data: Input data with time dimension
            parameter: Parameter name determining aggregation method
            step_start: Start of aggregation period in hours
            step_end: End of aggregation period in hours

        Returns:
            Aggregated data or None if aggregation fails

        """
        try:
            xr_data = self._ensure_xarray(data)

            if "step" not in xr_data.coords:
                return None

            available_steps = xr_data.coords["step"].values
            steps_in_hours = [self._convert_step_to_hours(s) for s in available_steps]

            # For all parameter types, derive the actual step range from
            # the data's available steps. Each CDF scenario already contains
            # only the steps that are valid for the analysis date, so we
            # should aggregate over the full available range rather than
            # using a hardcoded 0-24h window (which would be wrong for D-1,
            # D-2, … scenarios whose steps are e.g. 24-48h, 48-72h, …).
            target_period = step_end - step_start
            step_start, step_end = self._determine_accumulation_period_for_forecast(
                steps_in_hours, target_period
            )

            # Accumulation parameters (tp, sf, ts) need step_start included as
            # the baseline for the difference calculation (end - start).
            #
            # All other parameters follow the Metview convention:
            #   fcstep = [step_start+6, "to", step_end, "by", 6]
            # i.e. step_start itself is EXCLUDED.  For 6h-since-previous-postproc
            # variables (10fg6, mn2t6, mx2t6) the value at step_start covers the
            # period [step_start-6 .. step_start], which is BEFORE the analysis
            # window.  For instantaneous variables (2t) Metview also skips it.
            if parameter in ["tp", "sf", "ts"]:
                period_steps_ns = [
                    available_steps[i]
                    for i, step_hr in enumerate(steps_in_hours)
                    if step_start <= step_hr <= step_end
                ]
            else:
                period_steps_ns = [
                    available_steps[i]
                    for i, step_hr in enumerate(steps_in_hours)
                    if step_hr > step_start and step_hr <= step_end
                ]

            if not period_steps_ns:
                if not steps_in_hours:
                    return None

                closest_end_idx = min(
                    range(len(steps_in_hours)),
                    key=lambda i: abs(steps_in_hours[i] - step_end),
                )
                period_steps_ns = [available_steps[closest_end_idx]]

                if parameter in ["tp", "sf", "ts"] and len(steps_in_hours) > 1:
                    closest_start_idx = min(
                        range(len(steps_in_hours)),
                        key=lambda i: abs(steps_in_hours[i] - step_start),
                    )
                    if closest_start_idx != closest_end_idx:
                        period_steps_ns = [
                            available_steps[closest_start_idx],
                            available_steps[closest_end_idx],
                        ]

            if parameter in ["tp", "sf", "ts"]:
                if len(period_steps_ns) >= 2:
                    accum_start = xr_data.sel(step=period_steps_ns[0])
                    accum_end = xr_data.sel(step=period_steps_ns[-1])
                    aggregated_data = accum_end - accum_start
                else:
                    aggregated_data = xr_data.sel(step=period_steps_ns[0])

            elif parameter in ["2t", "ws"]:
                period_data = xr_data.sel(step=period_steps_ns)
                aggregated_data = period_data.mean(dim="step")

            elif parameter in ["2tmax", "mx2t6", "10fg", "10fg6", "cape", "capeshear", "capes"]:
                period_data = xr_data.sel(step=period_steps_ns)
                aggregated_data = period_data.max(dim="step")

            elif parameter in ["2tmin", "mn2t6"]:
                period_data = xr_data.sel(step=period_steps_ns)
                aggregated_data = period_data.min(dim="step")

            else:
                aggregated_data = xr_data.sel(step=period_steps_ns[-1])

            return aggregated_data

        except (ValueError, KeyError, IndexError) as e:
            print(f"Warning: Aggregation failed for {parameter}: {e}")
            return None

    def _extract_nearest_gridpoint(
        self, data, lat: float, lon: float, preserve_dim: str | None = None
    ) -> np.ndarray:
        """Extract values from nearest grid point.

        Works with all grid types including reduced Gaussian grids.
        Uses haversine distance calculation to find the nearest point.

        Args:
            data: Input data (FieldList or xarray)
            lat: Target latitude in degrees
            lon: Target longitude in degrees
            preserve_dim: Optional dimension to preserve (e.g., 'quantile' for climate data)

        Returns:
            Array of values at the nearest grid point

        """
        try:
            xr_data = self._ensure_xarray(data)

            try:
                lat_name, lon_name = self._get_coordinate_names(xr_data)
            except ValueError:
                return np.array([])

            lat_coord = xr_data.coords[lat_name]
            lon_coord = xr_data.coords[lon_name]

            if lat_coord.ndim == 1 and lon_coord.ndim == 1:
                if len(lat_coord) == len(lon_coord):
                    lats = lat_coord.values
                    lons = lon_coord.values
                    grid_shape = (len(lat_coord),)
                else:
                    lon_2d, lat_2d = np.meshgrid(lon_coord.values, lat_coord.values)
                    lats = lat_2d.flatten()
                    lons = lon_2d.flatten()
                    grid_shape = lat_2d.shape
            else:
                lats = lat_coord.values.flatten()
                lons = lon_coord.values.flatten()
                grid_shape = lat_coord.values.shape

            coord = [lat, lon]
            idx, distance = nearest_point_haversine(coord, (lats, lons))

            if "values" in xr_data.dims:
                point_data = xr_data.isel(values=idx)
            elif lat_coord.ndim == 1 and lon_coord.ndim == 1:
                if len(lat_coord) == len(lon_coord):
                    spatial_dims = [
                        d
                        for d in xr_data.dims
                        if d
                        not in [
                            "time",
                            "step",
                            "number",
                            "ensemble",
                            "member",
                            "quantile",
                            "percentile",
                            "valid_time",
                        ]
                    ]
                    if spatial_dims:
                        point_data = xr_data.isel({spatial_dims[0]: idx})
                    else:
                        return np.array([])
                else:
                    lat_idx, lon_idx = np.unravel_index(idx, grid_shape)
                    point_data = xr_data.isel({lat_name: lat_idx, lon_name: lon_idx})
            else:
                lat_idx, lon_idx = np.unravel_index(idx, grid_shape)
                if lat_coord.ndim == 2:
                    lat_dims = lat_coord.dims
                    point_data = xr_data.isel(
                        {lat_dims[0]: lat_idx, lat_dims[1]: lon_idx}
                    )
                else:
                    point_data = xr_data.isel({lat_name: lat_idx, lon_name: lon_idx})

            values = []

            member_dim = None
            for dim_name in ["number", "ensemble", "member"]:
                if dim_name in point_data.dims:
                    member_dim = dim_name
                    break

            for _var_name, var_data in point_data.data_vars.items():
                if preserve_dim and preserve_dim in var_data.dims:
                    var_values = var_data.values
                    values.extend(
                        var_values.flatten() if var_values.ndim > 1 else var_values
                    )
                elif member_dim and member_dim in var_data.dims:
                    var_values = var_data.values
                    values.extend(
                        var_values.flatten() if var_values.ndim > 1 else var_values
                    )
                else:
                    var_values = var_data.values
                    if np.isscalar(var_values):
                        values.append(var_values)
                    else:
                        values.extend(var_values.flatten())

            return np.array(values)

        except (ValueError, KeyError, IndexError) as e:
            print(f"Error extracting nearest gridpoint: {e}")
            return np.array([])

    def _process_climate_quantiles(
        self,
        climate_dataset,
        parameter: str,
        lat: float,
        lon: float,
        target_unit: str = "mm",
    ) -> tuple[np.ndarray, np.ndarray]:
        """Process climate quantile data for CDF plotting.

        Loads climate data, extracts values at the specified location, performs
        unit conversions, and prepares quantile-based CDF data.

        Args:
            climate_dataset: Climate data source (file path or data object)
            parameter: Parameter name
            lat: Latitude in degrees
            lon: Longitude in degrees
            target_unit: Target unit for conversion (e.g., 'mm' for precipitation)

        Returns:
            Tuple of (sorted_values, percentiles) for CDF plotting

        """
        try:
            climate_data = self._load_data(climate_dataset, parameter, is_climate=True)
            if climate_data is None:
                return np.array([]), np.array([])

            xr_data = self._ensure_xarray(climate_data)

            quantile_dim = None
            for dim_name in ["quantile", "percentile", "number"]:
                if dim_name in xr_data.dims:
                    quantile_dim = dim_name
                    break

            if quantile_dim:
                climate_values = self._extract_nearest_gridpoint(
                    xr_data, lat, lon, preserve_dim=quantile_dim
                )
            else:
                climate_values = self._extract_nearest_gridpoint(xr_data, lat, lon)

            if len(climate_values) == 0:
                return np.array([]), np.array([])

            if parameter in ["tp", "sf", "ts"]:
                current_unit = self._detect_precipitation_unit(climate_data, parameter)
                climate_values = self._convert_precipitation_units(
                    climate_values, from_unit=current_unit, to_unit=target_unit
                )
            elif parameter in ["2t", "2tmin", "2tmax", "mn2t6", "mx2t6"]:
                if np.mean(climate_values) > 200:
                    climate_values = climate_values - 273.15

            standard_percentiles = np.array(
                [
                    0,
                    1,
                    2,
                    5,
                    10,
                    20,
                    25,
                    30,
                    40,
                    50,
                    60,
                    70,
                    75,
                    80,
                    90,
                    95,
                    98,
                    99,
                    100,
                ]
            )

            if len(climate_values) == len(standard_percentiles):
                sorted_values = np.sort(climate_values)
                percentiles = standard_percentiles
            else:
                sorted_values, percentiles = self._process_cdf_data(climate_values)

            return sorted_values, percentiles

        except (ValueError, KeyError) as e:
            print(f"Warning: Could not process climate quantiles: {e}")
            return np.array([]), np.array([])

    def _detect_precipitation_unit(self, data, parameter: str) -> str:
        """Detect the unit of precipitation data.

        Checks dataset and variable attributes for unit information and normalizes
        common variations to standard unit codes.

        Args:
            data: Input data
            parameter: Parameter name

        Returns:
            Unit string: 'm', 'mm', 'cm', or 'km'

        """
        try:
            xr_data = self._ensure_xarray(data)

            if hasattr(xr_data, "attrs") and "units" in xr_data.attrs:
                unit = xr_data.attrs["units"]
            elif parameter in xr_data.data_vars:
                var_attrs = xr_data[parameter].attrs
                unit = var_attrs.get("units", var_attrs.get("unit", "m"))
            else:
                unit = "m"

            unit = unit.lower().strip()
            if unit in ["meter", "meters"]:
                return "m"
            elif unit in ["millimeter", "millimeters", "kg m**-2", "kg/m2", "kg m-2"]:
                # kg m**-2 = 1 mm of water (AIFS native unit for tp)
                return "mm"
            elif unit in ["centimeter", "centimeters"]:
                return "cm"

            return unit

        except (ValueError, AttributeError):
            return "m"

    def _convert_precipitation_units(
        self, values: np.ndarray, from_unit: str = "m", to_unit: str = "mm"
    ) -> np.ndarray:
        """Convert precipitation values between units.

        Args:
            values: Array of precipitation values
            from_unit: Source unit ('m', 'mm', 'cm', or 'km')
            to_unit: Target unit ('m', 'mm', 'cm', or 'km')

        Returns:
            Array of converted values

        """
        if from_unit == to_unit:
            return values

        unit_factors = {"m": 1.0, "mm": 0.001, "cm": 0.01, "km": 1000.0}

        try:
            values_in_meters = values * unit_factors.get(from_unit, 1.0)
            converted_values = values_in_meters / unit_factors.get(to_unit, 1.0)
            return converted_values
        except (TypeError, ValueError):
            return values

    def _process_cdf_data(self, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Process raw values into CDF format.

        Removes NaN values, sorts the data, and calculates corresponding percentiles.

        Args:
            values: Array of raw values

        Returns:
            Tuple of (sorted_values, percentiles)

        """
        if values is None or len(values) == 0:
            return np.array([]), np.array([])

        clean_values = values[~np.isnan(values)]
        if len(clean_values) == 0:
            return np.array([]), np.array([])

        sorted_values = np.sort(clean_values)
        n = len(sorted_values)
        if n == 1:
            # A single value has no spread to compute a 0-100 range over;
            # represent it at the midpoint to avoid a division by zero.
            percentiles = np.array([50.0])
        else:
            percentiles = np.arange(0, n) / (n - 1) * 100

        return sorted_values, percentiles

    def _process_forecast_data(
        self,
        forecast_dataset,
        parameter: str,
        step_start: int,
        step_end: int,
        lat: float,
        lon: float,
        target_unit: str = "mm",
    ) -> np.ndarray:
        """Process forecast data for CDF plotting.

        Loads forecast data, handles wind components, applies temporal aggregation,
        extracts values at location, and performs unit conversions.

        Args:
            forecast_dataset: Forecast data source (file path or data object)
            parameter: Parameter name
            step_start: Start of aggregation period in hours
            step_end: End of aggregation period in hours
            lat: Latitude in degrees
            lon: Longitude in degrees
            target_unit: Target unit for conversion

        Returns:
            Array of forecast values for CDF computation

        """
        try:
            forecast_data = self._load_data(forecast_dataset, parameter)
            if forecast_data is None or (
                hasattr(forecast_data, "__len__") and len(forecast_data) == 0
            ):
                return np.array([])

            if parameter == "ws":
                forecast_data = self._handle_wind_components(forecast_data, parameter)

            aggregated_data = self._apply_parameter_specific_aggregation(
                forecast_data, parameter, step_start, step_end
            )
            if aggregated_data is None:
                return np.array([])

            forecast_values = self._extract_nearest_gridpoint(aggregated_data, lat, lon)

            if len(forecast_values) == 0:
                return np.array([])

            if parameter in ["tp", "sf", "ts"]:
                current_unit = self._detect_precipitation_unit(forecast_data, parameter)
                forecast_values = self._convert_precipitation_units(
                    forecast_values, from_unit=current_unit, to_unit=target_unit
                )
            elif parameter in ["2t", "2tmin", "2tmax", "mn2t6", "mx2t6"]:
                if np.mean(forecast_values) > 200:
                    forecast_values = forecast_values - 273.15

            return forecast_values

        except (ValueError, KeyError) as e:
            print(f"Error processing forecast data: {e}")
            return np.array([])

    def _format_date_for_display(
        self, date_str: str, time_str: str | None = None, format_style: str = "short"
    ) -> str:
        """Format date string for display in plots.

        Args:
            date_str: Date string in YYYYMMDD format
            time_str: Optional time string
            format_style: Display style - 'short' (DD/MM), 'long' (DD/MM/YY HH UTC),
                         or 'legend' (DD/MM HHZ)

        Returns:
            Formatted date string for display

        """
        try:
            if len(date_str) != 8:
                return date_str

            year = date_str[:4]
            month = date_str[4:6]
            day = date_str[6:8]
            date_obj = datetime(int(year), int(month), int(day))

            hour = "00"
            if time_str:
                hour = time_str.split(":")[0] if ":" in time_str else time_str

            if format_style == "short":
                return date_obj.strftime("%d/%m")
            elif format_style == "legend":
                return f"{date_obj.strftime('%d/%m')} {hour}Z"
            elif format_style == "long":
                return f"{date_obj.strftime('%d/%m/%y')} {hour} UTC"
            else:
                return date_str

        except (ValueError, IndexError):
            return date_str if date_str else "Unknown"

    def _sort_scenarios_for_legend(self, scenarios: dict) -> list[tuple[str, dict]]:
        """Sort scenarios for consistent legend ordering.

        Sorts by day offset (ascending) and then by forecast time (12Z before 00Z).

        Args:
            scenarios: Dictionary mapping scenario names to scenario information

        Returns:
            List of (scenario_name, scenario_info) tuples in sorted order

        """

        def sort_key(item):
            scenario_name, scenario_info = item

            if scenario_name.startswith("D-"):
                try:
                    day_offset = int(scenario_name.split("_")[0].split("-")[1])
                except (ValueError, IndexError):
                    day_offset = 999
            else:
                day_offset = 999

            # forecast_time is stored inside the "scenario_info" sub-dict added
            # by retrieve_cdf_data, NOT in the "metadata" dict from
            # _retrieve_forecast_data (which does not contain "forecast_time").
            # Fall back to parsing the scenario name if the key is missing.
            scenario_data = scenario_info.get("scenario_info", {})
            forecast_time = scenario_data.get("forecast_time")
            if forecast_time is None:
                # Parse from scenario name, e.g. "D-1_12Z" → 12
                try:
                    forecast_time = int(scenario_name.split("_")[1].replace("Z", ""))
                except (ValueError, IndexError):
                    forecast_time = 0
            # 12Z runs are fresher within the same day → sort them first
            time_priority = 0 if forecast_time == 12 else 1

            return (day_offset, time_priority)

        return sorted(scenarios.items(), key=sort_key)

    def _generate_plot_title(
        self,
        parameter: str,
        lat: float,
        lon: float,
        forecast_date: str | None = None,
        forecast_time: str | None = None,
        step_start: int | None = None,
        step_end: int | None = None,
        model_name: str | None = None,
    ) -> str:
        """Generate plot title with parameter and location information.

        Args:
            parameter: Parameter name
            lat: Latitude in degrees
            lon: Longitude in degrees
            forecast_date: Forecast date in YYYYMMDD format
            forecast_time: Forecast time string
            step_start: Start of accumulation period in hours
            step_end: End of accumulation period in hours

        Returns:
            Formatted title string for the plot

        """
        param_config = self.styling_config.choose_color_palette_and_levels(parameter)

        if forecast_date:
            try:
                formatted_date = datetime.strptime(forecast_date, "%Y%m%d").strftime(
                    "%d/%m/%Y"
                )
            except ValueError:
                formatted_date = forecast_date
        else:
            formatted_date = datetime.now().strftime("%d/%m/%Y")

        datetime_info = formatted_date
        if forecast_time:
            try:
                hour = forecast_time.split(":")[0]
                datetime_info = f"{formatted_date} {hour}:00 UTC"
            except (ValueError, IndexError):
                datetime_info = f"{formatted_date} {forecast_time}"

        period_info = ""
        if (
            parameter in ["tp", "sf", "ts"]
            and step_start is not None
            and step_end is not None
        ):
            period_hours = step_end - step_start
            period_info = f" | {period_hours}h accumulation"

        model_info = f" | Model: {model_name}" if model_name else ""

        title = (
            f"Cumulative Distribution Functions for {param_config['title']}\n"
            f"Location: {lat:.2f}°, {lon:.2f}°{period_info}{model_info} | Forecast: {datetime_info}"
        )

        return title

    def create_cdf_plot(
        self,
        cdf_data: dict,
        parameter: str,
        lat: float,
        lon: float,
        step_start: int = 0,
        step_end: int = 24,
        target_unit: str | None = None,
        figsize: tuple[int, int] = (12, 8),
        model_name: str | None = None,
    ) -> plt.Figure:
        """Create a CDF plot comparing forecast and climate data.

        Main method for generating CDF plots. Processes both climate and forecast
        data, applies styling, and creates a publication-ready figure.

        Args:
            cdf_data: Dictionary containing 'cd' (climate data) and 'forecast_data'
                     with nested 'scenarios' structure
            parameter: Parameter name (e.g., 'tp', '2t', 'ws')
            lat: Latitude in degrees
            lon: Longitude in degrees
            step_start: Start of aggregation period in hours
            step_end: End of aggregation period in hours
            target_unit: Target unit for display (auto-detected if None)
            figsize: Figure size as (width, height) in inches

        Returns:
            Matplotlib Figure object containing the CDF plot

        """
        param_config = self.styling_config.choose_color_palette_and_levels(
            parameter, unit=target_unit
        )

        if target_unit is None:
            target_unit = (
                "mm"
                if parameter in ["tp", "sf", "ts"]
                else param_config.get("unit", "")
            )

        fig, ax = plt.subplots(figsize=figsize)

        # The title should show the user's chosen Forecast Analysis Date, not
        # the M-Climate date.  The analysis date is stored at the top-level
        # metadata key by both the MARS retrieval and (when provided) local
        # file loading paths.
        top_metadata = cdf_data.get("metadata", {})
        if model_name is None:
            model_name = top_metadata.get("model_display_name") or top_metadata.get("model_class") or None
        raw_analysis_date = top_metadata.get("analysis_date")  # "YYYY-MM-DD"
        if raw_analysis_date:
            # _generate_plot_title expects "YYYYMMDD" format
            try:
                from datetime import datetime as _dt
                title_date = _dt.strptime(raw_analysis_date, "%Y-%m-%d").strftime("%Y%m%d")
            except ValueError:
                title_date = raw_analysis_date
        else:
            title_date = None
        title_time = None  # Analysis date has no single representative time

        climate_date = None

        if "cd" in cdf_data:
            try:
                climate_info = cdf_data["cd"]
                climate_dataset = climate_info["dataset"]
                climate_metadata = climate_info.get("metadata", {})

                climate_date = climate_metadata.get("date", None)
                climate_time = climate_metadata.get("time", None)

                clim_x, clim_y = self._process_climate_quantiles(
                    climate_dataset, parameter, lat, lon, target_unit
                )

                if len(clim_x) > 0:
                    climate_label = f"M-Climate ({self._format_date_for_display(climate_date, format_style='short')})"
                    ax.plot(
                        clim_x,
                        clim_y,
                        color="black",
                        linewidth=3,
                        label=climate_label,
                        zorder=10,
                    )

            except (ValueError, KeyError) as e:
                print(f"Warning: Could not plot climate data: {e}")

        if "forecast_data" in cdf_data and "scenarios" in cdf_data["forecast_data"]:
            scenarios = cdf_data["forecast_data"]["scenarios"]
            sorted_scenarios = self._sort_scenarios_for_legend(scenarios)

            for i, (scenario_name, scenario_info) in enumerate(sorted_scenarios):
                try:
                    forecast_dataset = scenario_info["dataset"]
                    forecast_metadata = scenario_info.get("metadata", {})
                    scenario_data = scenario_info.get("scenario_info", {})

                    forecast_values = self._process_forecast_data(
                        forecast_dataset,
                        parameter,
                        step_start,
                        step_end,
                        lat,
                        lon,
                        target_unit,
                    )

                    if forecast_values is not None and len(forecast_values) > 0:
                        fc_x, fc_y = self._process_cdf_data(forecast_values)

                        if len(fc_x) > 0:
                            if scenario_name.startswith("D-0"):
                                color = "#FF0000"
                            else:
                                color_index = (i % (len(self.color_palette) - 1)) + 1
                                color = self.color_palette[color_index]

                            forecast_time = scenario_data.get("forecast_time", 0)
                            line_style = self._determine_line_style(
                                scenario_name, forecast_time
                            )

                            forecast_date_obj = scenario_data.get("forecast_date")
                            if forecast_date_obj:
                                forecast_date = forecast_date_obj.strftime("%Y%m%d")
                            else:
                                forecast_date = forecast_metadata.get("date", "")
                            forecast_time_str = forecast_metadata.get("time", "")

                            formatted_datetime = self._format_date_for_display(
                                forecast_date, forecast_time_str, format_style="long"
                            )
                            lead_start = scenario_data.get("lead_start", step_start)
                            lead_end = scenario_data.get("lead_end", step_end)
                            label = f"ENS {formatted_datetime} (t+[{lead_start}-{lead_end}h])"

                            ax.plot(
                                fc_x,
                                fc_y,
                                color=color,
                                linewidth=2,
                                linestyle=line_style,
                                label=label,
                            )

                except (ValueError, KeyError) as e:
                    print(f"Warning: Could not plot scenario {scenario_name}: {e}")

        unit_label = target_unit if target_unit else param_config["unit"]
        ax.set_xlabel(f"{param_config['title']} ({unit_label})", fontsize=12)
        ax.set_ylabel("Probability not to exceed threshold (%)", fontsize=12)
        ax.set_ylim(0, 100)
        ax.grid(True, color="grey", linestyle="--", alpha=0.7)

        title = self._generate_plot_title(
            parameter, lat, lon, title_date, title_time, step_start, step_end, model_name
        )
        ax.set_title(title, fontsize=14, fontweight="bold")

        ax.legend(
            bbox_to_anchor=(1.05, 1),
            loc="upper left",
            fontsize=10,
            frameon=True,
            fancybox=True,
            shadow=True,
        )

        return fig

    def _load_data(
        self, data_source: str | object, parameter: str, is_climate: bool = False
    ):
        """Load data with parameter mapping for climate data.

        Handles various data source formats including file paths, FieldList objects,
        and pre-loaded xarray data. Applies parameter name mapping for climate data.

        Args:
            data_source: Data source (file path string or data object)
            parameter: Parameter name to load
            is_climate: If True, applies climate parameter name mapping

        Returns:
            Loaded data object or None if loading fails

        """
        if is_climate:
            mapped_param = self.climate_param_map.get(parameter, parameter)
        else:
            mapped_param = parameter

        # For forecast data the Python parameter key may differ from the actual
        # GRIB shortName in the file.  E.g. "10fg6" is requested as paramId
        # 123.128 but ECMWF may encode it with shortName "10fg" in some streams.  If the
        # primary lookup fails, try the climate-param mapping as a fallback
        # (it provides the correct GRIB shortName for such cases).
        alt_param = None
        if not is_climate:
            climate_name = self.climate_param_map.get(parameter)
            if climate_name and climate_name != parameter:
                alt_param = climate_name

        if hasattr(data_source, "to_xarray"):
            try:
                if hasattr(data_source, "sel"):
                    try:
                        return data_source.sel(shortName=mapped_param)
                    except (AttributeError, KeyError):
                        if alt_param:
                            try:
                                return data_source.sel(shortName=alt_param)
                            except (AttributeError, KeyError):
                                pass
                        return data_source
                return data_source
            except (AttributeError, KeyError):
                return data_source

        if isinstance(data_source, str):
            try:
                loaded_data = ekd.from_source("file", data_source).to("fieldlist")
                try:
                    return loaded_data.sel(shortName=mapped_param)
                except (AttributeError, KeyError):
                    if alt_param:
                        try:
                            return loaded_data.sel(shortName=alt_param)
                        except (AttributeError, KeyError):
                            pass
                    return loaded_data
            except Exception as e:
                print(f"Warning: Could not load data from {data_source}: {e}")
                return None

        return data_source
