import traceback
from typing import Any

import numpy as np
import pandas as pd
from earthkit.geo import nearest_point_haversine
from helpers.derived_variables.meteorological_calculations import (
    calculate_deaccumulated_precipitation,
)


class PrecipitationDataProcessor:
    """Class for processing precipitation data with deaccumulation capabilities."""

    def __init__(self):
        """Initialize the PrecipitationDataProcessor."""
        self.precipitation_datasets = {}
        self.precipitation_timeseries = {}
        self.grid_coordinates = {}
        self.loaded_models = set()
        self.available_intervals = {}

    def process_precipitation_datasets(
        self,
        datasets: dict[str, Any],
        intervals: list[int] = None,
        param_types: list[str] = None,
    ) -> bool:
        """Process multiple datasets for precipitation deaccumulation.

        Args:
            datasets: Dictionary with model names as keys and earthkit datasets as values
            intervals: List of deaccumulation intervals in hours (default: [24, 12, 6])
            param_types: List of precipitation parameters to process (default: ["tp", "cp", "lsp"])

        Returns:
            bool: True if successful, False otherwise

        """
        if intervals is None:
            intervals = [24, 12, 6, 48]

        if param_types is None:
            param_types = ["tp", "cp", "lsp"]

        success = True

        for model_name, dataset in datasets.items():
            try:
                model_results = {}

                for param_type in param_types:
                    deaccum_results = calculate_deaccumulated_precipitation(
                        dataset, intervals, parameter=param_type
                    )

                    if deaccum_results:
                        for interval_key, data in deaccum_results.items():
                            param_interval_key = interval_key.replace(
                                "tp_", f"{param_type}_"
                            )
                            model_results[param_interval_key] = data

                if model_results:
                    self.precipitation_datasets[model_name] = model_results
                    self.available_intervals[model_name] = list(model_results.keys())
                    self.loaded_models.add(model_name)

                    first_dataset = next(iter(model_results.values()))
                    self._extract_grid_coordinates(first_dataset, model_name)
                else:
                    success = False
            except Exception:
                success = False
                continue

        return success

    def extract_precipitation_timeseries(  # noqa: PLR0912
        self,
        model_name: str,
        lat: float,
        lon: float,
        interval: int = 24,
        parameter: str = "tp",
    ) -> tuple[pd.DataFrame, float]:
        """Extract precipitation time series at a specific location for a given interval.

        Args:
            model_name: Name of the model
            lat: Latitude coordinate
            lon: Longitude coordinate
            interval: Precipitation interval in hours (24, 12, 48 or 6)
            parameter: Precipitation parameter ("tp", "cp", or "lsp")

        Returns:
            tuple: (DataFrame with precipitation time series, distance to nearest grid point in km)

        Raises:
            ValueError: If model or interval not available

        """
        if model_name not in self.loaded_models:
            raise ValueError(
                f"Model {model_name} not processed. Available: {list(self.loaded_models)}"
            )

        interval_key = f"{parameter}_{interval}h"

        if (
            model_name not in self.available_intervals
            or interval_key not in self.available_intervals[model_name]
        ):
            available = self.available_intervals.get(model_name, [])
            raise ValueError(
                f"Interval {interval}h for {parameter} not available for {model_name}. Available: {available}"
            )

        try:
            dataset = self.precipitation_datasets[model_name][interval_key]

            if model_name not in self.grid_coordinates:
                self._extract_grid_coordinates(dataset, model_name)

            if model_name not in self.grid_coordinates:
                raise ValueError(f"Could not extract coordinates for {model_name}")

            grid_lat = self.grid_coordinates[model_name]["lat"]
            grid_lon = self.grid_coordinates[model_name]["lon"]

            coord = [lat, lon]
            idx, distance = nearest_point_haversine(coord, (grid_lat, grid_lon))
            distance_km = distance[0] / 1000.0

            precip_var = f"{parameter}_{interval}h"
            if precip_var not in dataset.data_vars:
                raise ValueError(f"Variable {precip_var} not found in dataset")

            precip_data = dataset[precip_var]

            if "points" in precip_data.dims:
                values = (
                    precip_data.values[:, idx]
                    if precip_data.ndim > 1
                    else precip_data.values[idx]
                )
            elif len(precip_data.shape) == 3:  # noqa: PLR2004
                y_idx, x_idx = np.unravel_index(idx, precip_data.shape[-2:])
                values = precip_data.values[:, y_idx, x_idx]
            elif len(precip_data.shape) == 2:  # noqa: PLR2004
                y_idx, x_idx = np.unravel_index(idx, precip_data.shape)
                values = precip_data.values[y_idx, x_idx]
            else:
                raise ValueError(f"Unexpected data shape: {precip_data.shape}")

            time_values = pd.to_datetime(precip_data.step.values)

            if np.isscalar(values):
                values = np.array([values])
            elif values.ndim > 1:
                values = values.flatten()

            precip_df = pd.DataFrame({"precipitation_value": values}, index=time_values)
            precip_df.index.name = "datetime"

            location_key = f"lat_{lat:.4f}_lon_{lon:.4f}_{interval}h"
            if model_name not in self.precipitation_timeseries:
                self.precipitation_timeseries[model_name] = {}
            self.precipitation_timeseries[model_name][location_key] = {
                "data": precip_df,
                "distance_km": distance_km,
                "interval": interval,
                "location": (lat, lon),
            }

            return precip_df, distance_km

        except Exception as e:
            print(f"Error extracting timeseries for {model_name}: {e}")
            traceback.print_exc()
            raise

    def get_available_intervals(self, model_name: str = None) -> dict[str, list[str]]:
        """Get available precipitation intervals for model(s).

        Args:
            model_name: Specific model name, or None for all models

        Returns:
            Dict mapping model names to available interval keys

        """
        if model_name:
            return {model_name: self.available_intervals.get(model_name, [])}
        else:
            return self.available_intervals.copy()

    def _extract_grid_coordinates(self, dataset: Any, model_name: str):
        """Extract grid coordinates from precipitation dataset.

        Args:
            dataset: xarray Dataset with precipitation data
            model_name: Name of the model for storage

        """
        try:
            lat_names = ["latitude", "lat", "y"]
            lon_names = ["longitude", "lon", "x"]

            lat_coord = None
            lon_coord = None

            for name in lat_names:
                if name in dataset.coords:
                    lat_coord = dataset.coords[name].values
                    break

            for name in lon_names:
                if name in dataset.coords:
                    lon_coord = dataset.coords[name].values
                    break

            if lat_coord is None or lon_coord is None:
                print(f"Could not find lat/lon coordinates for {model_name}")
                return

            if lat_coord.ndim == 1 and lon_coord.ndim == 1:
                if len(lat_coord) == len(lon_coord):
                    lats, lons = lat_coord, lon_coord
                    print(
                        f" {model_name}: Reduced Gaussian grid with {len(lat_coord)} points"
                    )
                else:
                    lons, lats = np.meshgrid(lon_coord, lat_coord)
                    print(
                        f" {model_name}: Regular grid {len(lat_coord)}×{len(lon_coord)}"
                    )
            elif lat_coord.ndim == 2 and lon_coord.ndim == 2:  # noqa: PLR2004
                lats, lons = lat_coord, lon_coord
                print(f" {model_name}: 2D grid {lat_coord.shape}")
            else:
                print(
                    f"  {model_name}: Unexpected coordinate dimensions - lat {lat_coord.ndim}D, lon {lon_coord.ndim}D"
                )
                return

            self.grid_coordinates[model_name] = {"lat": lats, "lon": lons}
            print(f"   Stored coordinates: lats {lats.shape}, lons {lons.shape}")

        except Exception as e:
            print(f"Error extracting coordinates for {model_name}: {e}")
            traceback.print_exc()

    def clear_data(self):
        """Clear all processed precipitation data."""
        self.precipitation_datasets.clear()
        self.precipitation_timeseries.clear()
        self.grid_coordinates.clear()
        self.loaded_models.clear()
        self.available_intervals.clear()

    def get_model_summary(self) -> dict[str, dict]:
        """Get summary information for all processed models.

        Returns:
            Dict with model summaries including available intervals and statistics

        """
        summary = {}

        for model_name in self.loaded_models:
            model_info = {
                "available_intervals": self.available_intervals.get(model_name, []),
                "grid_shape": None,
                "extracted_locations": 0,
            }

            if model_name in self.grid_coordinates:
                lat_shape = self.grid_coordinates[model_name]["lat"].shape
                model_info["grid_shape"] = lat_shape

            if model_name in self.precipitation_timeseries:
                model_info["extracted_locations"] = len(
                    self.precipitation_timeseries[model_name]
                )

            summary[model_name] = model_info

        return summary

    def validate_precipitation_data(
        self, model_name: str, interval: int = 24
    ) -> dict[str, Any]:
        """Validate precipitation data for a specific model and interval.

        Args:
            model_name: Name of the model to validate
            interval: Precipitation interval to validate

        Returns:
            Dict with validation results

        """
        validation = {
            "model_available": model_name in self.loaded_models,
            "interval_available": False,
            "data_statistics": None,
            "issues": [],
        }

        if not validation["model_available"]:
            validation["issues"].append(f"Model {model_name} not processed")
            return validation

        interval_key = f"tp_{interval}h"
        validation["interval_available"] = (
            model_name in self.available_intervals
            and interval_key in self.available_intervals[model_name]
        )

        if not validation["interval_available"]:
            available = self.available_intervals.get(model_name, [])
            validation["issues"].append(
                f"Interval {interval}h not available. Available: {available}"
            )
            return validation

        try:
            dataset = self.precipitation_datasets[model_name][interval_key]
            precip_var = f"tp_{interval}h"

            if precip_var in dataset.data_vars:
                data = dataset[precip_var].values
                validation["data_statistics"] = {
                    "shape": data.shape,
                    "min": float(np.nanmin(data)),
                    "max": float(np.nanmax(data)),
                    "mean": float(np.nanmean(data)),
                    "has_nan": bool(np.isnan(data).any()),
                    "all_zeros": bool(np.all(data == 0)),
                }

                if validation["data_statistics"]["all_zeros"]:
                    validation["issues"].append("All precipitation values are zero")

                if validation["data_statistics"]["has_nan"]:
                    nan_count = np.isnan(data).sum()
                    validation["issues"].append(f"{nan_count} NaN values found")

            else:
                validation["issues"].append(
                    f"Variable {precip_var} not found in dataset"
                )

        except Exception as e:
            validation["issues"].append(f"Validation error: {str(e)}")

        return validation
