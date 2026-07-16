"""Meteorological Calculations Module.

This module contains specific functions for calculating meteorological variables
and indices from model outputs.
"""

from typing import Any

import numpy as np
import pandas as pd
import xarray as xr


def calculate_accumulated_precipitation(
    data_ds: Any, param_type: str = "tp"
) -> xr.DataArray:
    """Calculate precipitation accumulation between first and last forecast steps.

    Args:
        data_ds: Dataset from earthkit-data (ek.data.from_source result)
        param_type: Type of precipitation - "tp", "cp", or "lsp"

    Returns:
        xarray.DataArray containing accumulated precipitation with:
        - Coordinates: latitude, longitude
        - Data: acc_{param_type} (Accumulated precipitation in m)
        - Attributes: step information and metadata

    Raises:
        ValueError: If dataset is None or invalid
        RuntimeError: If data processing fails

    """
    if data_ds is None:
        raise ValueError("Dataset cannot be None")

    valid_params = ["tp", "cp", "lsp"]
    if param_type not in valid_params:
        raise ValueError(f"param_type must be one of {valid_params}, got {param_type}")

    try:
        start_step = data_ds[0].metadata("step")
        end_step = data_ds[-1].metadata("step")

        xr_ds = data_ds.to_xarray()

        available_steps = sorted(xr_ds.step.values)

        start_step_td = pd.Timedelta(hours=start_step)
        end_step_td = pd.Timedelta(hours=end_step)

        start_precip = xr_ds.sel(step=start_step_td)[param_type]
        end_precip = xr_ds.sel(step=end_step_td)[param_type]

        if start_precip.size == 0 or end_precip.size == 0:
            raise RuntimeError(
                f"No data found for requested steps. Available: {available_steps}"
            )

        acc_precip = end_precip - start_precip

        # Create variable name based on param_type
        acc_var_name = f"acc_{param_type}"
        acc_precip_da = acc_precip.rename(acc_var_name)

        # Set appropriate long name based on param_type
        long_names = {
            "tp": "Accumulated Total Precipitation",
            "cp": "Accumulated Convective Precipitation",
            "lsp": "Accumulated Large-scale Precipitation",
        }

        acc_precip_da.attrs.update(
            {
                "long_name": long_names[param_type],
                "units": "m",
                "start_step": f"{start_step}h",
                "end_step": f"{end_step}h",
                "date": data_ds[0]["date"],
                "time": data_ds[0]["time"],
                "accumulation_period": f"{end_step - start_step}h",
                "description": f"{long_names[param_type]} from {start_step}h to {end_step}h forecast",
                "precipitation_type": param_type,
            }
        )

        return acc_precip_da

    except Exception as e:
        raise RuntimeError(f"Error processing {param_type} data: {e}")


def calculate_accumulated_convective_precipitation(data_ds: Any) -> xr.DataArray:
    """Calculate convective precipitation accumulation between first and last forecast steps."""
    return calculate_accumulated_precipitation(data_ds, param_type="cp")


def calculate_accumulated_largescale_precipitation(data_ds: Any) -> xr.DataArray:
    """Calculate large-scale precipitation accumulation between first and last forecast steps."""
    return calculate_accumulated_precipitation(data_ds, param_type="lsp")


def calculate_wind_speed(u_wind: Any, v_wind: Any) -> xr.Dataset:
    """Calculate wind speed for each step from U and V components.
    Returns an xarray Dataset with lat/lon coordinates.

    Args:
        u_wind: GRIB reader containing zonal component (U)
        v_wind: GRIB reader containing meridional component (V)

    Returns:
        xarray.Dataset containing wind speed with lat/lon coordinates

    Raises:
        ValueError: If U/V datasets are empty
        RuntimeError: If U/V steps don't match

    """  # noqa: D205
    if len(u_wind) == 0 or len(v_wind) == 0:
        raise ValueError("U/V datasets cannot be empty")

    u_steps = [f.metadata("step") for f in u_wind]
    v_steps = [f.metadata("step") for f in v_wind]

    if u_steps != v_steps:
        raise RuntimeError(f"Step mismatch: U={u_steps} vs V={v_steps}")

    wind_speeds = []
    steps = []
    lats, lons = None, None
    coordinates_extracted = False
    grid_type = None
    grid_metadata = {}

    for i, (u_field, v_field) in enumerate(zip(u_wind, v_wind, strict=False)):
        step_u, step_v = u_field.metadata("step"), v_field.metadata("step")
        if step_u != step_v:
            raise RuntimeError(f"Step inconsistency at index {i}: {step_u} vs {step_v}")

        u_data, v_data = u_field.values, v_field.values
        wind_speed = np.sqrt(u_data**2 + v_data**2)

        if not coordinates_extracted:
            lats, lons = _extract_and_process_coordinates(u_field, wind_speed.shape)
            coordinates_extracted = True

            try:
                grid_type = u_field.metadata("gridType")
                if grid_type in ["reduced_gg", "reduced_ll"]:
                    grid_metadata["grid_type"] = grid_type
                    try:
                        grid_metadata["grid_N"] = u_field.metadata("N")
                        grid_metadata["is_octahedral"] = u_field.metadata(
                            "isOctahedral", default=0
                        )
                    except Exception:
                        pass
            except Exception:
                pass

        if isinstance(lats, np.ndarray):
            if lats.ndim == 2 and wind_speed.shape != lats.shape:  # noqa: PLR2004
                wind_speed = wind_speed.reshape(lats.shape)
            elif lats.ndim == 1 and wind_speed.size != lats.size:
                wind_speed = wind_speed.flatten()

        wind_speeds.append(wind_speed)
        steps.append(step_u)

    date = u_wind[0]["date"]
    time = u_wind[0]["time"]
    wind_speeds = np.array(wind_speeds)
    ds = _create_dataset(wind_speeds, lats, lons, steps, date, time)
    ds.attrs.update(grid_metadata)
    ds["10ff"].attrs.update(grid_metadata)
    return ds


def _extract_and_process_coordinates(
    field: Any, wind_shape: tuple[int, ...]
) -> tuple[np.ndarray, np.ndarray]:
    """Extract and process coordinates from GRIB field with fallback options.

    Args:
        field: GRIB field object
        wind_shape: Shape of the wind data array

    Returns:
        Tuple of latitude and longitude arrays

    """
    try:
        grid_points = field.grid_points()
        lat_1d, lon_1d = grid_points[0], grid_points[1]

        shape = getattr(field, "shape", wind_shape)
        lats = lat_1d.reshape(shape)
        lons = lon_1d.reshape(shape)
        return lats, lons

    except (AttributeError, ValueError) as e:
        raise ValueError(
            f"Could not extract grid coordinates from field: {e}"
        ) from e


def _create_dataset(  # noqa: PLR0913
    wind_speeds: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    steps: list,
    date: int,
    time: int,
) -> xr.Dataset:
    """Create optimized xarray Dataset with specified variable names.

    Args:
        wind_speeds: Array of wind speed values
        lats: Latitude coordinates
        lons: Longitude coordinates
        steps: List of forecast steps
        date: Date of the data
        time: forecast time of the data

    Returns:
        xarray.Dataset with wind speed data and coordinates

    """
    has_multiple_steps = len(wind_speeds) > 1
    coords_2d = lats.ndim == 2  # noqa: PLR2004

    if coords_2d:
        base_coords = {"latitude": (["y", "x"], lats), "longitude": (["y", "x"], lons)}

        if has_multiple_steps:
            coords = {"step": steps, **base_coords}
            dims = ["step", "y", "x"]
        else:
            coords = base_coords
            dims = ["y", "x"]
            wind_speeds = wind_speeds[0]

    else:
        n_points = len(lats)
        base_coords = {
            "points": np.arange(n_points),
            "latitude": ("points", lats),
            "longitude": ("points", lons),
        }

        if has_multiple_steps:
            coords = {"step": steps, **base_coords}
            dims = ["step", "points"]
        else:
            coords = base_coords
            dims = ["points"]
            wind_speeds = wind_speeds[0]

    ds = xr.Dataset({"10ff": (dims, wind_speeds)}, coords=coords)

    ds["10ff"].attrs = {
        "long_name": "10 metre wind speed",
        "units": "m s**-1",
        "standard_name": "wind_speed",
        "description": "Wind speed calculated from U and V components",
    }

    ds.attrs = {
        "long_name": "Wind Speed Data",
        "units": "m s**-1",
        "date": date,
        "time": time,
    }

    return ds
