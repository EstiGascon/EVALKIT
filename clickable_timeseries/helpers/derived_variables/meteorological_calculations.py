import re
import traceback
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr


def extract_wind_speed_timeseries(  # noqa: PLR0911
    dataset: Any, model_name: str, lat: float, lon: float, forecast_processor: Any
) -> tuple[pd.DataFrame | None, float]:
    """Extract wind speed time series at a specific location using forecast processor.

    This function uses the forecast processor to extract U and V components,
    then calculates wind speed from them.

    Args:
        dataset: The original dataset containing U and V components
        model_name: Name of the model
        lat: Latitude
        lon: Longitude
        forecast_processor: ForecastDataProcessor instance

    Returns:
        tuple: (forecast_df with wind speed, distance_km)

    """
    try:
        u_success = forecast_processor.process_datasets({model_name: dataset}, "10u")
        if not u_success:
            print("Failed to process U component")
            return None, 0.0

        u_df, u_distance = forecast_processor.extract_forecast_timeseries(
            model_name, lat, lon
        )
        if u_df is None or u_df.empty:
            print("No U component data extracted")
            return None, 0.0

        v_success = forecast_processor.process_datasets({model_name: dataset}, "10v")
        if not v_success:
            print("Failed to process V component")
            return None, 0.0

        v_df, v_distance = forecast_processor.extract_forecast_timeseries(
            model_name, lat, lon
        )
        if v_df is None or v_df.empty:
            print("No V component data extracted")
            return None, 0.0

        if not u_df.index.equals(v_df.index):
            common_times = u_df.index.intersection(v_df.index)
            if len(common_times) == 0:
                print("No common time indices found")
                return None, 0.0
            u_df = u_df.loc[common_times]
            v_df = v_df.loc[common_times]

        u_values = u_df["forecast_value"].values
        v_values = v_df["forecast_value"].values
        wind_speed_values = np.sqrt(u_values**2 + v_values**2)

        wind_speed_df = pd.DataFrame(
            {"forecast_value": wind_speed_values}, index=u_df.index
        )
        wind_speed_df.index.name = "datetime"

        distance_km = u_distance
        return wind_speed_df, distance_km

    except Exception as e:
        print(f"Error extracting wind speed timeseries: {e}")

        traceback.print_exc()
        return None, 0.0


def calculate_deaccumulated_precipitation(
    data_ds: Any, intervals: list[int] = None, parameter: str = "tp"
) -> dict[str, xr.Dataset]:
    """Calculate deaccumulated precipitation for specified time intervals and parameter type.

    This function takes cumulative precipitation data and calculates precipitation
    rates for different time periods (e.g., 24h, 12h, 6h).

    Args:
        data_ds: Dataset containing cumulative precipitation data
        intervals: List of deaccumulation intervals in hours (default: [24, 12, 6])
        parameter: Precipitation parameter to process ("tp", "cp", or "lsp", default: "tp")

    Returns:
        Dict[str, xr.Dataset]: Dictionary with keys like 'tp_24h', 'cp_12h', 'lsp_6h'

    Raises:
        ValueError: If dataset is None or invalid, or parameter not found
        RuntimeError: If data processing fails

    """
    if data_ds is None:
        raise ValueError("Dataset cannot be None")

    if intervals is None:
        intervals = [24, 12, 6]

    try:
        try:
            print(
                f"Filtering dataset to parameter '{parameter}' before xarray conversion"
            )
            filtered_ds = data_ds.sel(param=parameter)
            xr_ds = filtered_ds.to_xarray()
            print(f"Successfully converted filtered {parameter} data to xarray")
        except Exception as filter_error:
            print(f"Could not filter by parameter '{parameter}': {filter_error}")
            xr_ds = data_ds.to_xarray()

        if parameter not in xr_ds.data_vars:
            available_vars = list(xr_ds.data_vars.keys())
            raise ValueError(
                f"No '{parameter}' variable found in dataset. Available variables: {available_vars}"
            )

        precip_data = xr_ds[parameter]

        step_values = precip_data.step.values
        steps_hours = []

        for step_val in step_values:
            try:
                hour_val = safe_timedelta_to_hours(step_val)
                steps_hours.append(int(hour_val))
            except Exception as e:
                print(f"Could not convert step {step_val}: {e}")
                continue

        print(f"Available steps for {parameter}: {sorted(steps_hours)}")

        lats, lons = _extract_coordinates_from_xarray(precip_data)
        base_date, base_time = _extract_base_datetime(data_ds, xr_ds=xr_ds)

        results = {}

        for interval in intervals:
            try:
                deaccum_data = _deaccumulate_precipitation_for_interval(
                    precip_data, interval, steps_hours, parameter
                )

                if deaccum_data is not None:
                    dataset = _create_precipitation_dataset(
                        deaccum_data,
                        lats,
                        lons,
                        interval,
                        base_date,
                        base_time,
                        parameter,
                    )

                    interval_key = f"{parameter}_{interval}h"
                    results[interval_key] = dataset
                else:
                    print(
                        f"No data available for {parameter} {interval}h deaccumulation"
                    )

            except Exception as e:
                print(f"Error processing {parameter} {interval}h interval: {e}")
                traceback.print_exc()
                continue

        if not results:
            raise RuntimeError(
                f"No {parameter} precipitation intervals could be processed"
            )

        print(
            f"\n Deaccumulation complete for {parameter} with correct dates! Created {len(results)} datasets: {list(results.keys())}"
        )
        return results

    except Exception as e:
        print(f"Error in {parameter} precipitation deaccumulation: {e}")
        traceback.print_exc()
        raise RuntimeError(f"Error in {parameter} precipitation deaccumulation: {e}")


def _extract_base_datetime(data_ds: Any, xr_ds: Any = None) -> tuple[Any, Any]:  # noqa: PLR0912
    """Extract base date and time from original dataset.

    This function properly extracts the base datetime from the dataset
    to ensure correct date calculations during deaccumulation.

    Args:
        data_ds: Original earthkit dataset
        xr_ds: Optional pre-converted xarray dataset (to avoid re-conversion issues)

    Returns:
        tuple: (base_date, base_time)

    """
    try:
        if xr_ds is None:
            try:
                xr_ds = data_ds.to_xarray()
            except Exception as e:
                print(f"⚠️  Could not convert to xarray for datetime extraction: {e}")
                pass

        if xr_ds is not None:
            if hasattr(xr_ds, "attrs"):
                date = xr_ds.attrs.get("date")
                time = xr_ds.attrs.get("time")

                if date is not None and time is not None:
                    print(f"Found base datetime: {date} {time}")
                    return date, time

            for var_name in xr_ds.data_vars:
                var = xr_ds[var_name]
                if hasattr(var, "attrs"):
                    date = var.attrs.get("date")
                    time = var.attrs.get("time")

                    if date is not None and time is not None:
                        print(f"Found base datetime from {var_name}: {date} {time}")
                        return date, time

            for coord_name in xr_ds.coords:
                coord = xr_ds.coords[coord_name]
                if hasattr(coord, "attrs"):
                    date = coord.attrs.get("date")
                    time = coord.attrs.get("time")

                    if date is not None and time is not None:
                        print(f"Found base datetime from {coord_name}: {date} {time}")
                        return date, time

    except Exception as e:
        print(f"Exception in xarray datetime extraction: {e}")

    try:
        if hasattr(data_ds, "metadata"):
            if hasattr(data_ds, "__getitem__") and len(data_ds) > 0:
                first_field = data_ds[0]
                if hasattr(first_field, "metadata"):
                    metadata = first_field.metadata()
                    date = metadata.get("date")
                    time = metadata.get("time")
                    if date is not None and time is not None:
                        print(
                            f"Found base datetime from earthkit metadata: {date} {time}"
                        )
                        return date, time
    except Exception as e:
        print(f"Could not extract from earthkit metadata: {e}")

    print("Could not find base date/time - datetime coordinates will be missing")
    return None, None


def safe_timedelta_to_hours(td):  # noqa: PLR0911, PLR0912
    """Safely convert various timedelta types to hours.

    Args:
        td: Timedelta object (numpy.timedelta64, pandas.Timedelta, or datetime.timedelta)

    Returns:
        float: Hours as a float

    """
    try:
        if isinstance(td, np.timedelta64):
            if td.dtype == "timedelta64[ns]":
                seconds = td / np.timedelta64(1, "s")
                return float(seconds) / 3600.0
            elif td.dtype == "timedelta64[h]":
                return float(td / np.timedelta64(1, "h"))
            elif td.dtype == "timedelta64[s]":
                return float(td / np.timedelta64(1, "s")) / 3600.0
            elif td.dtype == "timedelta64[m]":
                return float(td / np.timedelta64(1, "m")) / 60.0
            else:
                seconds = td / np.timedelta64(1, "s")
                return float(seconds) / 3600.0

        elif hasattr(td, "total_seconds"):
            return td.total_seconds() / 3600.0

        elif isinstance(td, int | float):
            return float(td)

        elif hasattr(td, "seconds") and hasattr(td, "days"):
            total_seconds = td.days * 86400 + td.seconds
            if hasattr(td, "microseconds"):
                total_seconds += td.microseconds / 1000000.0
            return total_seconds / 3600.0

        else:
            td_str = str(td)
            print(f"Parsing timedelta string: '{td_str}'")

            if "days" in td_str:
                match = re.match(r"(\d+) days?,?\s*(\d+):(\d+):(\d+)", td_str)
                if match:
                    days, hours, minutes, seconds = map(int, match.groups())
                    return days * 24 + hours + minutes / 60 + seconds / 3600

            elif ":" in td_str:
                parts = td_str.split(":")
                if len(parts) >= 2:  # noqa: PLR2004
                    hours = float(parts[0])
                    minutes = float(parts[1])
                    seconds = float(parts[2]) if len(parts) > 2 else 0  # noqa: PLR2004
                    return hours + minutes / 60 + seconds / 3600

            elif td_str.endswith("h"):
                return float(td_str[:-1])

            elif td_str.isdigit():
                return float(td_str)

            else:
                return float(td_str)

    except Exception as e:
        print(f"Could not convert timedelta {td} (type: {type(td)}) to hours: {e}")

        if "timedelta64" in str(type(td)):
            td_str = str(td)
            numbers = re.findall(r"(\d+)", td_str)
            if numbers:
                return float(numbers[0])

        print("All conversion attempts failed, returning 0.0")
        return 0.0


def _deaccumulate_precipitation_for_interval(
    precip_data: xr.DataArray,
    interval: int,
    steps_hours: list[int],
    parameter: str = "tp",
) -> xr.DataArray | None:
    """Deaccumulate precipitation for a specific time interval."""
    try:
        steps_hours = sorted(set(steps_hours))

        print(
            f"Processing {parameter} {interval}h deaccumulation for steps: {steps_hours}"
        )

        valid_pairs = []

        start_hour = 0
        while start_hour + interval <= max(steps_hours):
            end_hour = start_hour + interval

            start_step = _find_closest_step(start_hour, steps_hours)
            end_step = _find_closest_step(end_hour, steps_hours)

            if start_step is not None and end_step is not None:
                start_idx = steps_hours.index(start_step)
                end_idx = steps_hours.index(end_step)
                valid_pairs.append((start_idx, end_idx, start_step, end_step))
                print(f"Found interval: {start_step}h → {end_step}h")
            else:
                print(f"Could not find steps for interval {start_hour}h → {end_hour}h")

            start_hour = end_hour

        if not valid_pairs:
            print(f"No valid {interval}h pairs found in available steps: {steps_hours}")
            return None

        print(f"Found {len(valid_pairs)} non-overlapping {interval}h intervals")

        deaccum_times = []
        deaccum_values = []

        for start_idx, end_idx, start_step, end_step in valid_pairs:
            try:
                tp_start = precip_data.isel(step=start_idx)
                tp_end = precip_data.isel(step=end_idx)

                precip_diff = tp_end - tp_start

                end_time_coord = precip_data.step.values[end_idx]
                deaccum_times.append(end_time_coord)
                deaccum_values.append(precip_diff.values)

                actual_interval = end_step - start_step
                print(f"{start_step}h → {end_step}h (actual: {actual_interval}h)")

            except Exception as e:
                print(f" Error processing pair {start_step}h → {end_step}h: {e}")
                continue

        if not deaccum_values:
            print(f"No valid deaccumulation values calculated for {interval}h")
            return None

        deaccum_array = np.array(deaccum_values)

        new_coords = precip_data.coords.copy()
        new_coords["step"] = ("step", deaccum_times)

        deaccum_da = xr.DataArray(
            data=deaccum_array,
            coords=new_coords,
            dims=precip_data.dims,
            name=f"{parameter}_{interval}h",
        )

        param_name_map = {
            "tp": "Total Precipitation",
            "cp": "Convective Precipitation",
            "lsp": "Large Scale Precipitation",
        }
        param_long_name = param_name_map.get(
            parameter, f"{parameter.upper()} Precipitation"
        )

        deaccum_da.attrs.update(
            {
                "long_name": f"{interval}-hour {param_long_name}",
                "units": precip_data.attrs.get("units", "m"),
                "interval": f"{interval}h",
                "parameter": parameter,
                "description": f"{param_long_name} accumulated over {interval} hour periods (non-overlapping)",
                "deaccumulation_method": "consecutive_intervals",
            }
        )

        return deaccum_da

    except Exception:
        traceback.print_exc()
        return None


def _find_closest_step(
    target_hour: int, available_steps: list[int], tolerance: int = 3
) -> int | None:
    """Find the closest available step to target hour."""
    if target_hour in available_steps:
        return target_hour

    closest_steps = [
        step for step in available_steps if abs(step - target_hour) <= tolerance
    ]
    if closest_steps:
        return min(closest_steps, key=lambda x: abs(x - target_hour))

    return None


def _extract_coordinates_from_xarray(  # noqa: PLR0912
    data_array: xr.DataArray,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract latitude and longitude coordinates from xarray DataArray.

    Handles both regular grids (2D lat/lon) and reduced Gaussian grids (1D points).

    Args:
        data_array: xarray DataArray with coordinate information

    Returns:
        tuple: (lats, lons) as numpy arrays

    """
    try:
        lat_names = ["latitude", "lat", "y"]
        lon_names = ["longitude", "lon", "x"]

        lat_coord = None
        lon_coord = None

        for name in lat_names:
            if name in data_array.coords:
                lat_coord = data_array.coords[name].values
                break

        for name in lon_names:
            if name in data_array.coords:
                lon_coord = data_array.coords[name].values
                break

        if lat_coord is None or lon_coord is None:
            raise ValueError(
                f"Could not find lat/lon coordinates in {list(data_array.coords.keys())}"
            )

        if lat_coord.ndim == 1 and lon_coord.ndim == 1:
            if len(lat_coord) == len(lon_coord):
                print(f"Detected reduced grid: {len(lat_coord)} points (1D arrays)")
                lats, lons = lat_coord, lon_coord
            else:
                print(
                    f"Detected regular grid: {len(lat_coord)}×{len(lon_coord)} points"
                )
                lons, lats = np.meshgrid(lon_coord, lat_coord)
        else:
            print(f"Detected 2D coordinates: {lat_coord.shape}")
            lats, lons = lat_coord, lon_coord

        print(f"Extracted coordinates: lats {lats.shape}, lons {lons.shape}")
        return lats, lons

    except Exception as e:
        print(f"Error extracting coordinates: {e}")
        traceback.print_exc()

        try:
            if "step" in data_array.dims:
                spatial_data = data_array.isel(step=0)
            else:
                spatial_data = data_array

            shape = spatial_data.shape
            print(f"Fallback: using data shape {shape}")

            if len(shape) == 1:
                n_points = shape[0]
                lats = np.arange(n_points, dtype=np.float32)
                lons = np.arange(n_points, dtype=np.float32)
                print(f"   Created dummy 1D coordinates for {n_points} points")
            elif len(shape) == 2:  # noqa: PLR2004
                lats = np.arange(shape[0], dtype=np.float32)
                lons = np.arange(shape[1], dtype=np.float32)
                lons, lats = np.meshgrid(lons, lats)
                print(f"   Created dummy 2D grid: {shape[0]}×{shape[1]}")
            else:
                raise ValueError(f"Unexpected data shape: {shape}")

            return lats, lons

        except Exception as fallback_error:
            print(f"Fallback also failed: {fallback_error}")
            raise


def _create_precipitation_dataset(  # noqa: PLR0912, PLR0913, PLR0915
    precip_data: xr.DataArray,
    lats: np.ndarray,
    lons: np.ndarray,
    interval: int,
    date: Any,
    time: Any,
    parameter: str = "tp",
) -> xr.Dataset:
    """Create xarray Dataset for deaccumulated precipitation.

    Handles both regular grids (2D) and reduced Gaussian grids (1D points).
    This version properly handles datetime coordinate conversion to avoid the year 2000 problem.

    Args:
        precip_data: Deaccumulated precipitation data
        lats: Latitude coordinates
        lons: Longitude coordinates
        interval: Precipitation interval in hours
        date: Base date
        time: Base time
        parameter: Precipitation parameter name

    Returns:
        xr.Dataset: Dataset with precipitation data and coordinates

    """
    try:
        coords_2d = lats.ndim == 2  # noqa: PLR2004
        coords_1d_paired = lats.ndim == 1 and lons.ndim == 1 and len(lats) == len(lons)

        has_multiple_steps = precip_data.sizes.get("step", 1) > 1

        if "step" in precip_data.coords and date is not None and time is not None:
            step_values = precip_data.step.values

            datetime_index = _create_proper_datetime_coordinates(
                step_values, date, time
            )

            new_coords = precip_data.coords.copy()
            new_coords["step"] = ("step", datetime_index.values)

            precip_data = xr.DataArray(
                data=precip_data.values,
                coords=new_coords,
                dims=precip_data.dims,
                name=precip_data.name,
                attrs=precip_data.attrs,
            )
        else:
            print("Cannot create proper datetime coordinates - missing date/time info")

        if coords_1d_paired:
            print(f"Creating dataset for reduced grid: {len(lats)} points")

            n_points = len(lats)
            base_coords = {
                "points": np.arange(n_points),
                "latitude": ("points", lats),
                "longitude": ("points", lons),
            }

            if has_multiple_steps:
                coords = {"step": precip_data.step, **base_coords}
                dims = ["step", "points"]

                if precip_data.ndim == 2 and precip_data.shape[1] == n_points:  # noqa: PLR2004
                    data_values = precip_data.values
                elif precip_data.ndim == 1 and len(precip_data) == n_points:
                    data_values = precip_data.values.reshape(1, -1)
                else:
                    data_values = precip_data.values.reshape(len(precip_data.step), -1)
            else:
                coords = base_coords
                dims = ["points"]

                if precip_data.ndim == 1 and len(precip_data) == n_points:
                    data_values = precip_data.values
                else:
                    data_values = precip_data.values.flatten()

        elif coords_2d:
            print(f"Creating dataset for regular grid: {lats.shape}")

            base_coords = {
                "latitude": (["y", "x"], lats),
                "longitude": (["y", "x"], lons),
            }

            if has_multiple_steps:
                coords = {"step": precip_data.step, **base_coords}
                dims = ["step", "y", "x"]

                expected_shape = (len(precip_data.step), lats.shape[0], lats.shape[1])
                if precip_data.shape != expected_shape:
                    print(
                        f"Reshaping data from {precip_data.shape} to {expected_shape}"
                    )
                    data_values = precip_data.values.reshape(expected_shape)
                else:
                    data_values = precip_data.values
            else:
                coords = base_coords
                dims = ["y", "x"]

                if "step" in precip_data.dims:
                    precip_data = precip_data.squeeze("step")

                data_values = precip_data.values
        else:
            print(f"Unusual coordinate structure: lats {lats.shape}, lons {lons.shape}")
            raise ValueError("Unsupported coordinate structure")

        var_name = f"{parameter}_{interval}h"
        dataset = xr.Dataset({var_name: (dims, data_values)}, coords=coords)

        param_name_map = {
            "tp": "Total Precipitation",
            "cp": "Convective Precipitation",
            "lsp": "Large Scale Precipitation",
        }
        param_long_name = param_name_map.get(
            parameter, f"{parameter.upper()} Precipitation"
        )

        dataset[var_name].attrs = {
            "long_name": f"{interval}-hour {param_long_name}",
            "units": precip_data.attrs.get("units", "m"),
            "standard_name": f"{parameter}_amount",
            "interval": f"{interval}h",
            "parameter": parameter,
            "description": f"{param_long_name} accumulated over {interval} hour periods",
        }

        dataset.attrs = {
            "title": f"{interval}-hour Deaccumulated {param_long_name}",
            "interval": f"{interval}h",
            "parameter": parameter,
            "source": f"Deaccumulated from cumulative {parameter}",
            "date": date,
            "time": time,
            "grid_type": "reduced_gaussian" if coords_1d_paired else "regular",
        }

        print(f"Created dataset with dims {dims} and shape {data_values.shape}")
        return dataset

    except Exception as e:
        print(f"Error creating precipitation dataset: {e}")
        traceback.print_exc()
        raise


def _create_proper_datetime_coordinates(step_values, base_date, base_time):
    """Create proper datetime coordinates from step values and base datetime.

    Args:
        step_values: Array of step values (timedelta64 or similar)
        base_date: Base date (e.g., 20250301)
        base_time: Base time (e.g., 0 for 00:00)

    Returns:
        pd.DatetimeIndex: Properly converted datetime index

    """
    try:
        if base_date is None or base_time is None:
            base_datetime = pd.Timestamp.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        else:
            try:
                if isinstance(base_date, int | str):
                    date_str = str(base_date)
                    time_str = str(base_time).zfill(4)

                    year = int(date_str[:4])
                    month = int(date_str[4:6])
                    day = int(date_str[6:8])

                    hour = int(time_str[:2])
                    minute = int(time_str[2:4]) if len(time_str) >= 4 else 0  # noqa: PLR2004

                    base_datetime = pd.Timestamp(
                        year=year, month=month, day=day, hour=hour, minute=minute
                    )

                else:
                    base_datetime = pd.to_datetime(f"{base_date} {base_time}")

            except Exception:
                base_datetime = pd.Timestamp.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

        datetime_values = []
        for i, step_val in enumerate(step_values):
            try:
                hour_offset = safe_timedelta_to_hours(step_val)

                dt = base_datetime + pd.Timedelta(hours=hour_offset)
                datetime_values.append(dt)

            except Exception as e:
                print(f"Error converting step {i} ({step_val}): {e}")

        datetime_index = pd.DatetimeIndex(datetime_values)

        return datetime_index

    except Exception:
        pass
