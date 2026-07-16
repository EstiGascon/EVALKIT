import traceback
from typing import Any

import numpy as np
import pandas as pd
from earthkit.geo import nearest_point_haversine


class WindSpeedProcessor:
    """Processor for wind speed calculations including daily means."""

    def __init__(self):
        """Initialize the wind speed processor by setting up dictionaries to store processed datasets and available intervals."""
        self.processed_datasets = {}
        self.available_intervals = {}

    def process_wind_speed_datasets(self, all_datasets: dict[str, Any]) -> bool:
        """Process all wind speed datasets to compute hourly values and daily means.

        Args:
            all_datasets (dict[str, Any]): Dictionary mapping model names to dataset objects.

        Returns:
            bool: True if at least one dataset was successfully processed, otherwise False.

        """
        try:
            self.processed_datasets = {}
            self.available_intervals = {}

            for model_name, dataset in all_datasets.items():
                if not self._has_wind_components(dataset):
                    print(f"{model_name} missing wind components (10u, 10v)")
                    continue

                wind_speed_data = self._calculate_wind_speed_arrays(dataset, model_name)
                if wind_speed_data is None:
                    continue

                hourly_key = f"{model_name}_10ff_hourly"
                self.processed_datasets[hourly_key] = wind_speed_data

                try:
                    daily_data = self._calculate_daily_means(
                        wind_speed_data, model_name
                    )
                    if daily_data is not None:
                        daily_key = f"{model_name}_10ff_daily"
                        self.processed_datasets[daily_key] = daily_data
                        print(f"Processed wind speed (hourly + daily) for {model_name}")
                        self.available_intervals[model_name] = [
                            "10ff_hourly",
                            "10ff_daily",
                        ]
                    else:
                        self.available_intervals[model_name] = ["10ff_hourly"]

                except Exception as e:
                    print(f"Error calculating daily means for {model_name}: {e}")
                    self.available_intervals[model_name] = ["10ff_hourly"]

            return len(self.processed_datasets) > 0

        except Exception as e:
            print(f"Error processing wind speed datasets: {e}")
            traceback.print_exc()
            return False

    def _has_wind_components(self, dataset) -> bool:
        """Check whether the dataset contains the required wind component parameters (10u, 10v).

        Args:
            dataset: Input dataset to inspect.

        Returns:
            bool: True if both 10u and 10v components exist, otherwise False.

        """
        try:
            u_fields = dataset.sel(param="10u")
            v_fields = dataset.sel(param="10v")
            return len(u_fields) > 0 and len(v_fields) > 0
        except Exception:
            return False

    def _calculate_wind_speed_arrays(self, dataset, model_name: str):
        """Calculate wind speed arrays from U and V wind components.

        Args:
            dataset: Dataset containing 10u and 10v fields.
            model_name (str): Name of the model for logging and metadata.

        Returns:
            dict or None: Structured dictionary containing processed wind speed records,
            or None if processing fails.

        """
        try:
            u_fields = dataset.sel(param="10u")
            v_fields = dataset.sel(param="10v")

            if len(u_fields) == 0 or len(v_fields) == 0:
                return None

            # Extract lat/lon arrays once from the first field (shared grid)
            latlon = u_fields.to_latlon()
            grid_lat = latlon["lat"]
            grid_lon = latlon["lon"]

            wind_speed_records = []

            for u_field, v_field in zip(u_fields, v_fields, strict=False):
                try:
                    u_values = u_field.values
                    v_values = v_field.values
                    speed_values = np.sqrt(u_values**2 + v_values**2)

                    time_info = self._extract_time_info(u_field)

                    record = {
                        "values": speed_values,
                        "time": time_info,
                        "metadata": {
                            "param": "10ff",
                            "shortName": "ws",
                            "units": "m s**-1",
                            "original_param": "10u",
                        },
                    }

                    wind_speed_records.append(record)

                except Exception as field_error:
                    print(f"Error processing field in {model_name}: {field_error}")
                    continue

            if wind_speed_records:
                return {
                    "records": wind_speed_records,
                    "model": model_name,
                    "param": "10ff",
                    "grid_lat": grid_lat,
                    "grid_lon": grid_lon,
                }
            else:
                return None

        except Exception as e:
            print(f"Error calculating wind speed arrays for {model_name}: {e}")
            return None

    def _extract_time_info(self, field):
        """Extract time-related metadata from a dataset field.

        Args:
            field: Dataset field containing metadata with temporal information.

        Returns:
            dict: Dictionary of extracted time metadata fields.

        """
        try:
            metadata = field.metadata()
            time_info = {}

            def get_metadata_value(meta, key):
                if hasattr(meta, "get"):
                    return meta.get(key)
                try:
                    return meta(key)
                except Exception:
                    return None

            time_keys = [
                "valid_time",
                "validityTime",
                "time",
                "dataTime",
                "step",
                "forecastTime",
            ]
            for key in time_keys:
                value = get_metadata_value(metadata, key)
                if value is not None:
                    time_info[key] = value

            return time_info

        except Exception as e:
            print(f"Error extracting time info: {e}")
            return {}

    def _calculate_daily_means(self, wind_speed_data, model_name: str):
        """Compute daily mean wind speed from hourly wind speed records.

        Args:
            wind_speed_data (dict): Dictionary containing hourly wind speed records.
            model_name (str): Name of the associated model.

        Returns:
            dict or None: Dictionary containing daily mean wind speed records,
            or None if computation fails.

        """
        try:
            if not wind_speed_data or "records" not in wind_speed_data:
                return None

            records = wind_speed_data["records"]
            print(f"Calculating daily means for {len(records)} hourly records")

            daily_groups = {}
            for i, record in enumerate(records):
                time_info = record.get("time", {})
                step = int(time_info.get("step", i))
                day_group = step // 24
                daily_groups.setdefault(day_group, []).append(record)

            print(f"Created {len(daily_groups)} daily groups")

            daily_records = []
            for day_group, day_records in daily_groups.items():
                if not day_records:
                    continue

                all_values = np.stack([r["values"] for r in day_records], axis=0)
                mean_values = np.mean(all_values, axis=0)

                first_record_time = day_records[0]["time"].copy()
                steps = [int(r["time"].get("step", 0)) for r in day_records]
                first_record_time["step"] = int(np.mean(steps))
                first_record_time["aggregation"] = "daily_mean"
                first_record_time["source_records"] = len(day_records)
                first_record_time["date_group"] = f"day_{day_group}"

                daily_record = {
                    "values": mean_values,
                    "time": first_record_time,
                    "metadata": {
                        "param": "10ff_daily",
                        "shortName": "ws_daily",
                        "units": "m s**-1",
                        "aggregation": "daily_mean",
                    },
                }
                daily_records.append(daily_record)

            print(f"Created {len(daily_records)} daily mean records")

            if daily_records:
                return {
                    "records": daily_records,
                    "model": model_name,
                    "param": "10ff_daily",
                    "aggregation": "daily_mean",
                    "grid_lat": wind_speed_data.get("grid_lat"),
                    "grid_lon": wind_speed_data.get("grid_lon"),
                }
            return None

        except Exception as e:
            print(f"Error calculating daily means: {e}")
            traceback.print_exc()
            return None

    def extract_wind_speed_timeseries(
        self, model_name: str, lat: float, lon: float, interval: str = "hourly"
    ) -> tuple[pd.DataFrame, float]:
        """Extract a wind speed time series for a specific latitude and longitude.

        Args:
            model_name (str): Name of the model.
            lat (float): Latitude of the target location.
            lon (float): Longitude of the target location.
            interval (str): Time interval to extract ("hourly" or "daily_mean").

        Returns:
            tuple[pd.DataFrame, float]: DataFrame indexed by datetime containing forecast values,
            and the average distance (km) from the target location to the nearest grid point.

        """
        try:
            if interval == "daily_mean":
                dataset_key = f"{model_name}_10ff_daily"
            else:
                dataset_key = f"{model_name}_10ff_hourly"

            if dataset_key not in self.processed_datasets:
                print(f"No wind speed data for {dataset_key}")
                return None, 0.0

            wind_speed_data = self.processed_datasets[dataset_key]
            grid_lat = wind_speed_data.get("grid_lat")
            grid_lon = wind_speed_data.get("grid_lon")

            if grid_lat is None or grid_lon is None:
                print(f"No grid coordinates for {dataset_key}")
                return None, 0.0

            # Find nearest grid point once (same grid for all records)
            coord = [lat, lon]
            idx, distance = nearest_point_haversine(coord, (grid_lat, grid_lon))
            distance_km = distance[0] / 1000.0

            timeseries_data = []

            for record in wind_speed_data["records"]:
                try:
                    values = record["values"]
                    time_info = record["time"]

                    value_at_location = float(values[idx])
                    time_index = self._create_time_index(time_info)

                    timeseries_data.append(
                        {
                            "time": time_index,
                            "forecast_value": value_at_location,
                        }
                    )

                except Exception as extract_error:
                    print(f"Error extracting from record: {extract_error}")
                    continue

            if timeseries_data:
                df = pd.DataFrame(timeseries_data)
                df.set_index("time", inplace=True)
                df.sort_index(inplace=True)

                return df[["forecast_value"]], distance_km
            else:
                return None, 0.0

        except Exception as e:
            print(f"Error extracting wind speed timeseries: {e}")
            return None, 0.0

    def _create_time_index(self, time_info):
        """Create a pandas Timestamp from available time metadata.

        Args:
            time_info (dict): Dictionary of extracted time metadata.

        Returns:
            pd.Timestamp: Parsed timestamp representing the forecast valid time.

        """
        try:
            if "valid_time" in time_info:
                return pd.to_datetime(time_info["valid_time"])
            elif "step" in time_info:
                return pd.to_datetime("2000-01-01") + pd.Timedelta(
                    hours=int(time_info["step"])
                )
            else:
                return pd.Timestamp.now()

        except Exception as e:
            print(f"Error creating time index: {e}")
            return pd.Timestamp.now()
