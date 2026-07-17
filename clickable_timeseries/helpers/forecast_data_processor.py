from typing import Any

import pandas as pd
from earthkit.geo.distance import nearest_point_haversine


class ForecastDataProcessor:
    """Class for processing forecast data from earthkit-data datasets for map-clicked coordinates."""

    def __init__(self):
        """Initialize the ForecastDataProcessor."""
        self.forecast_data = {}
        self.station_dataframes = {}
        self.current_param = None
        self.grid_coordinates = {}
        self.station_distances = {}
        self.loaded_models = set()
        self.datasets = {}

    def process_datasets(
        self, datasets: dict[str, Any], param: str | None = None
    ) -> bool:
        """Process multiple datasets using earthkit-data.

        Args:
            datasets (dict): Dictionary with model names as keys and datasets as values
            param (str): Parameter name (optional, will use first available if None)

        Returns:
            bool: True if successful, False otherwise

        """
        # Reset all cached state before processing a new parameter so that
        # stale data from a previous parameter selection cannot leak through.
        # Without this, if a model's dataset does not contain the requested
        # parameter, process_single_dataset returns False without touching
        # self.datasets or self.loaded_models, leaving the old (wrong)
        # parameter data in the cache and producing incorrect plots.
        self.datasets.clear()
        self.loaded_models.clear()
        self.forecast_data.clear()
        self.station_dataframes.clear()
        self.grid_coordinates.clear()
        self.station_distances.clear()
        self.current_param = None

        success = False  # True only if at least one model succeeds

        for model, ds in datasets.items():
            if self.process_single_dataset(ds, model, param):
                success = True
            # models that fail are simply absent from self.datasets —
            # no stale data is left behind.

        return success

    def process_single_dataset(
        self, ds: Any, model: str, param: str | None = None
    ) -> bool:
        """Process a single earthkit dataset.

        Args:
            ds: earthkit dataset object
            model (str): Model name
            param (str): Parameter name (optional, will use first available if None)

        Returns:
            bool: True if successful, False otherwise

        """
        try:
            if param is None:
                available_params = ds.metadata("param")
                if available_params:
                    param = available_params[0]
                else:
                    print(f"Error: No parameters found in dataset for {model}")
                    return False

            temperature_params = ["mx2t", "mn2t"]
            is_temperature = param in temperature_params
            param_dataset = ds.sel({'parameter.variable': param})
            if is_temperature:
                try:
                    steps = param_dataset.metadata("step")
                    if steps and 0 in steps:
                        param_dataset = param_dataset.new_mask_index(where=lambda f: f.metadata('step') != 0)
                except Exception:
                    param_dataset = ds.sel({'parameter.variable': param})

            self.current_param = param
            self.datasets[model] = param_dataset
            self.loaded_models.add(model)

            if model not in self.forecast_data:
                self.forecast_data[model] = {}
            if model not in self.station_dataframes:
                self.station_dataframes[model] = {}
            if model not in self.grid_coordinates:
                self.grid_coordinates[model] = {}
            if model not in self.station_distances:
                self.station_distances[model] = {}

            self.grid_coordinates[model] = {
                "lat": param_dataset.geography.latitudes().flatten(),
                "lon": param_dataset.geography.longitudes().flatten(),
            }

            return True

        except Exception as e:
            print(f"Error processing dataset for {model}: {e}")
            return False

    def extract_forecast_timeseries(
        self, model: str, lat: float, lon: float
    ) -> tuple[pd.DataFrame, float]:
        """Extract forecast time series for a map-clicked coordinate from a specific model.

        Args:
            model (str): Model name to process(ex: IFS,AIFS ..)
            lat (float): Latitude coordinate from map click
            lon (float): Longitude coordinate from map click

        Returns:
            tuple: (DataFrame with forecast time series, distance to nearest grid point in km)

        """
        if not self.loaded_models:
            raise ValueError("No datasets processed. Call process_datasets() first.")

        if model not in self.loaded_models:
            raise ValueError(
                f"Model {model} not processed. Available models: {list(self.loaded_models)}"
            )

        print(f"\nProcessing model: {model}")
        print(f"Coordinate: {lat:.4f}°N, {lon:.4f}°E")

        ds = self.datasets[model]
        datetime_values = ds.metadata("valid_datetime")
        grid_lat = self.grid_coordinates[model]["lat"]
        grid_lon = self.grid_coordinates[model]["lon"]

        coord = [lat, lon]
        idx, distance = nearest_point_haversine(coord, (grid_lat, grid_lon))
        distance_km = distance[0] / 1000.0

        print(f"Nearest grid point distance: {distance_km:.1f}km")

        values = ds.values[:, idx].flatten()

        forecast_df = pd.DataFrame({"forecast_value": values}, index=datetime_values)
        forecast_df.index.name = "datetime"

        if not isinstance(forecast_df.index, pd.DatetimeIndex):
            try:
                forecast_df.index = pd.to_datetime(forecast_df.index)
            except:  # noqa: E722
                print(
                    f"Warning: Could not convert forecast index to datetime for {model}"
                )

        location_key = f"lat_{lat:.4f}_lon_{lon:.4f}"
        self.forecast_data[model][self.current_param] = forecast_df
        self.station_distances[model] = {location_key: distance_km}

        return forecast_df, distance_km
