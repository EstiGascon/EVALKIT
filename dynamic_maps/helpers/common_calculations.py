"""Weather Data Aggregator Module.

This module contains functions for calculating maximum and minimum values
from gridded meteorological data over specified time periods.
"""

from typing import Any, Literal

import earthkit.data as ekd
import xarray as xr


class WeatherDataAggregator:
    """Class for aggregating weather data over time periods."""

    def calculate_temporal_extremes(  # noqa: PLR0912, PLR0915
        self,
        dataset_or_result: Any,
        operation: Literal["max", "min"] = "max",
        param_name: str | None = None,
        output_format: Literal["xarray", "earthkit"] = "xarray",
    ) -> Any:
        """Calculate temporal maximum or minimum from gridded weather data.

        This function takes a dataset with multiple time steps and calculates
        the maximum or minimum value at each grid point across all time steps.

        Args:
            dataset_or_result: Dataset from WeatherDataRetriever (can be the full result dict
                            or just the dataset), earthkit dataset, or xarray Dataset
            operation: Either 'max' or 'min' for the temporal operation
            param_name: Optional parameter name to process. If None, processes all variables
            output_format: Format for output ('xarray' or 'earthkit')

        Returns:
            Aggregated dataset with temporal extremes calculated for each grid point

        """
        if isinstance(dataset_or_result, dict) and "dataset" in dataset_or_result:
            dataset = dataset_or_result["dataset"]
            metadata = dataset_or_result.get("metadata", {})
            print(f"Processing data with metadata: {metadata}")
        else:
            dataset = dataset_or_result
            metadata = {}

        if dataset is None:
            raise ValueError(
                "Dataset is None - check if data was retrieved successfully"
            )

        if isinstance(dataset, xr.Dataset | xr.DataArray):
            if isinstance(dataset, xr.Dataset):
                ds = dataset
                date = ds.attrs.get("date", "unknown")
                time = ds.attrs.get("time", "unknown")
            else:
                ds = dataset.to_dataset()
                date = dataset.attrs.get("date", "unknown")
                time = dataset.attrs.get("time", "unknown")
        else:
            if hasattr(dataset, "to_xarray"):
                ds = dataset.to_xarray()
            else:
                raise ValueError(
                    "Dataset must be an earthkit dataset or xarray Dataset"
                )

            if hasattr(dataset, "__len__") and len(dataset) > 0:
                date = dataset[0]["date"]
                time = dataset[0]["time"]
            else:
                date = "unknown"
                time = "unknown"

        if "time" in ds.dims:
            time_steps = ds.sizes["time"]
        elif "step" in ds.dims:
            time_steps = ds.sizes["step"]
        elif "time" in ds.coords:
            time_steps = len(ds.coords["time"])
        elif "step" in ds.coords:
            time_steps = len(ds.coords["step"])
        else:
            time_steps = "unknown"

        if param_name:
            if param_name in ds.data_vars:
                ds = ds[[param_name]]
            else:
                matching_vars = [
                    var
                    for var in ds.data_vars
                    if param_name in var or var in param_name
                ]
                if matching_vars:
                    print(f"Found matching variables: {matching_vars}")
                    ds = ds[matching_vars]
                else:
                    raise ValueError(
                        f"Parameter {param_name} not found in dataset. Available: {list(ds.data_vars.keys())}"
                    )

        result_vars = {}

        for var_name in ds.data_vars:
            var_data = ds[var_name]

            time_dim = None
            if "step" in var_data.dims:
                time_dim = "step"
            elif "time" in var_data.dims:
                time_dim = "time"

            if time_dim is None:
                print(f"Warning: Variable {var_name} has no time dimension, skipping")
                print(f"Available dimensions: {var_data.dims}")
                continue

            if operation == "max":
                result_da = var_data.max(dim=time_dim)
            elif operation == "min":
                result_da = var_data.min(dim=time_dim)
            else:
                raise ValueError("Operation must be either 'max' or 'min'")

            for attr in ["grid_type", "grid_N", "is_octahedral"]:
                if attr in var_data.attrs:
                    result_da.attrs[attr] = var_data.attrs[attr]

            result_vars[f"{var_name}_{operation}"] = result_da

        if not result_vars:
            raise ValueError("No variables with time dimension found to process")

        result_ds = xr.Dataset(result_vars)

        for coord_name in ["latitude", "longitude", "lat", "lon"]:
            if coord_name in ds.coords:
                result_ds.coords[coord_name] = ds.coords[coord_name]

        result_ds.attrs.update(
            {
                "long_name": f"Temporal {operation.capitalize()} Weather Data",
                "operation": operation,
                "steps": time_steps,
                "date": date,
                "time": time,
            }
        )

        if output_format == "xarray":
            return result_ds
        elif output_format == "earthkit":
            try:
                temp_file = "/tmp/temp_aggregated.nc"
                result_ds.to_netcdf(temp_file)
                return ekd.from_source("file", temp_file)
            except ImportError:
                print("Warning: earthkit not available, returning xarray dataset")
                return result_ds
        else:
            return result_ds

    def save_aggregated_data(
        self,
        aggregated_dataset: xr.Dataset,
        output_path: str,
        format: Literal["netcdf", "grib"] = "netcdf",
    ) -> None:
        """Save aggregated dataset to file.

        Args:
            aggregated_dataset: The aggregated xarray Dataset
            output_path: Path where to save the file
            format: Output format ('netcdf' or 'grib')

        """
        try:
            if format == "netcdf":
                aggregated_dataset.to_netcdf(output_path)
                print(f"Saved aggregated data to {output_path} (NetCDF format)")
            elif format == "grib":
                try:
                    aggregated_dataset.to_netcdf(output_path.replace(".grib", ".nc"))
                    print(
                        f"Note: Saved as NetCDF to {output_path.replace('.grib', '.nc')}"
                    )
                except Exception as e:
                    print(f"Error saving as GRIB: {e}")
                    print("Falling back to NetCDF format")
                    aggregated_dataset.to_netcdf(output_path.replace(".grib", ".nc"))
            else:
                raise ValueError("Format must be 'netcdf' or 'grib'")

        except Exception as e:
            raise RuntimeError(f"Failed to save aggregated data: {str(e)}")
