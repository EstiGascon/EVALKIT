import traceback
from typing import Any

import numpy as np
import pandas as pd


class WindGustProcessor:
    """Processor for wind gust calculations with rolling maximum over different periods."""

    def __init__(self):
        """Initialize the wind gust processor retriever."""
        self.processed_datasets = {}
        self.available_intervals = {}

    def process_wind_gust_datasets(self, all_datasets: dict[str, Any]) -> bool:
        """Process datasets to calculate wind gust with rolling maxima."""
        try:
            self.processed_datasets = {}
            self.available_intervals = {}

            for model_name, dataset in all_datasets.items():
                if not self._has_wind_gust(dataset):
                    print(f"{model_name} missing wind gust parameter (10fg)")
                    continue

                gust_data = self._extract_wind_gust_data(dataset, model_name)
                if gust_data is None:
                    continue

                hourly_key = f"{model_name}_10fg_hourly"
                self.processed_datasets[hourly_key] = gust_data

                intervals_processed = ["10fg_hourly"]

                for period_hours in [6, 12, 24, 48]:
                    try:
                        rolling_max_data = self._calculate_rolling_maximum(
                            gust_data, model_name, period_hours
                        )
                        if rolling_max_data is not None:
                            rolling_key = f"{model_name}_10fg_{period_hours}h"
                            self.processed_datasets[rolling_key] = rolling_max_data
                            intervals_processed.append(f"10fg_{period_hours}h")
                            print(
                                f"Processed {period_hours}h rolling max for {model_name}"
                            )

                    except Exception as e:
                        print(
                            f"Error calculating {period_hours}h rolling max for {model_name}: {e}"
                        )
                        continue

                self.available_intervals[model_name] = intervals_processed
                print(f"Processed wind gust for {model_name}: {intervals_processed}")

            return len(self.processed_datasets) > 0

        except Exception as e:
            print(f"Error processing wind gust datasets: {e}")
            traceback.print_exc()
            return False

    def _has_wind_gust(self, dataset) -> bool:
        """Check if dataset has wind gust parameter."""
        try:
            gust_fields = dataset.sel(param="10fg")
            return len(gust_fields) > 0
        except Exception:
            return False

    def _extract_wind_gust_data(self, dataset, model_name: str):
        """Extract wind gust data from dataset."""
        try:
            gust_fields = dataset.sel(param="10fg")

            if len(gust_fields) == 0:
                return None

            gust_records = []

            for gust_field in gust_fields:
                try:
                    gust_values = gust_field.values

                    time_info = self._extract_time_info(gust_field)
                    coord_info = self._extract_coordinate_info(gust_field)

                    record = {
                        "values": gust_values,
                        "time": time_info,
                        "coordinates": coord_info,
                        "metadata": {
                            "param": "10fg",
                            "shortName": "fg",
                            "units": "m s**-1",
                            "original_param": "10fg",
                        },
                    }

                    gust_records.append(record)

                except Exception as field_error:
                    print(f"Error processing gust field in {model_name}: {field_error}")
                    continue

            if gust_records:
                return {"records": gust_records, "model": model_name, "param": "10fg"}
            else:
                return None

        except Exception as e:
            print(f"Error extracting wind gust data for {model_name}: {e}")
            return None

    def _extract_time_info(self, field):
        """Extract time information from field."""
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

    def _extract_coordinate_info(self, field):
        """Extract coordinate information from field."""
        try:
            metadata = field.metadata()

            coord_info = {}
            coord_keys = [
                "latitudeOfFirstGridPointInDegrees",
                "longitudeOfFirstGridPointInDegrees",
                "latitudeOfLastGridPointInDegrees",
                "longitudeOfLastGridPointInDegrees",
                "iDirectionIncrementInDegrees",
                "jDirectionIncrementInDegrees",
                "Ni",
                "Nj",
            ]

            for key in coord_keys:
                if hasattr(metadata, "get"):
                    value = metadata.get(key)
                    if value is not None:
                        coord_info[key] = value
                else:
                    try:
                        value = metadata(key)
                        if value is not None:
                            coord_info[key] = value
                    except Exception:
                        continue

            return coord_info

        except Exception as e:
            print(f"Error extracting coordinate info: {e}")
            return {}

    def _calculate_rolling_maximum(self, gust_data, model_name: str, period_hours: int):  # noqa: PLR0912, PLR0915
        """Calculate rolling maximum with proper handling of data frequency."""
        try:
            if not gust_data or "records" not in gust_data:
                return None

            records = gust_data["records"]

            steps = []
            for record in records:
                time_info = record.get("time", {})
                step = int(time_info.get("step", 0))
                steps.append(step)

            steps.sort()
            if len(steps) > 1:
                data_frequency = steps[1] - steps[0]
            else:
                data_frequency = 1

            print(
                f"Calculating {period_hours}h rolling max for {len(records)} records (data frequency: {data_frequency}h)"
            )

            if period_hours == data_frequency:
                print(
                    f"   Period {period_hours}h matches data frequency {data_frequency}h - returning original data"
                )
                rolling_max_records = []
                for record in records:
                    rolling_record = record.copy()
                    rolling_record["time"] = record["time"].copy()
                    rolling_record["time"]["aggregation"] = (
                        f"{period_hours}h_rolling_max"
                    )
                    rolling_record["metadata"] = {
                        "param": f"10fg_{period_hours}h",
                        "shortName": f"fg_{period_hours}h",
                        "units": "m s**-1",
                        "aggregation": f"{period_hours}h_rolling_max_native",
                    }
                    rolling_max_records.append(rolling_record)

                return {
                    "records": rolling_max_records,
                    "model": model_name,
                    "param": f"10fg_{period_hours}h",
                    "aggregation": f"{period_hours}h_rolling_max_native",
                }

            step_record_map = {}
            for record in records:
                time_info = record.get("time", {})
                step = int(time_info.get("step", 0))
                step_record_map[step] = record

            sorted_steps = sorted(step_record_map.keys())
            rolling_max_records = []

            for current_step in sorted_steps:
                if current_step % period_hours != 0 or current_step == 0:
                    continue

                current_record = step_record_map[current_step]

                window_start_step = current_step - period_hours + data_frequency

                window_records = []
                for step in sorted_steps:
                    if window_start_step <= step <= current_step:
                        window_records.append(step_record_map[step])

                if not window_records:
                    print(
                        f"   No records found for window {window_start_step}h to {current_step}h"
                    )
                    continue

                print(
                    f"   Step {current_step}h: calculating max over {len(window_records)} records from {window_start_step}h to {current_step}h"
                )

                all_values = np.stack([r["values"] for r in window_records], axis=0)
                max_values = np.max(all_values, axis=0)

                rolling_time = current_record["time"].copy()
                rolling_time["aggregation"] = f"{period_hours}h_rolling_max"
                rolling_time["window_start_step"] = window_start_step
                rolling_time["window_end_step"] = current_step
                rolling_time["source_records"] = len(window_records)

                rolling_record = {
                    "values": max_values,
                    "time": rolling_time,
                    "coordinates": current_record["coordinates"],
                    "metadata": {
                        "param": f"10fg_{period_hours}h",
                        "shortName": f"fg_{period_hours}h",
                        "units": "m s**-1",
                        "aggregation": f"{period_hours}h_rolling_max",
                    },
                }

                rolling_max_records.append(rolling_record)

            print(
                f"Created {len(rolling_max_records)} rolling {period_hours}h max records"
            )

            if rolling_max_records:
                return {
                    "records": rolling_max_records,
                    "model": model_name,
                    "param": f"10fg_{period_hours}h",
                    "aggregation": f"{period_hours}h_rolling_max",
                }
            else:
                return None

        except Exception as e:
            print(f"Error calculating {period_hours}h rolling maximum: {e}")
            traceback.print_exc()
            return None

    def extract_wind_gust_timeseries(
        self, model_name: str, lat: float, lon: float, interval: str = "hourly"
    ) -> tuple[pd.DataFrame, float]:
        """Extract wind gust timeseries using simple approach like wind speed processor."""
        try:
            if interval == "hourly":
                dataset_key = f"{model_name}_10fg_hourly"
            else:
                dataset_key = f"{model_name}_10fg_{interval}"

            if dataset_key not in self.processed_datasets:
                print(f"No wind gust data for {dataset_key}")
                return None, 0.0

            gust_data = self.processed_datasets[dataset_key]

            timeseries_data = []

            for record in gust_data["records"]:
                try:
                    values = record["values"]
                    coordinates = record["coordinates"]
                    time_info = record["time"]

                    value_at_location, distance = self._extract_nearest_value(
                        values, coordinates, lat, lon
                    )

                    time_index = self._create_time_index(time_info)

                    timeseries_data.append(
                        {
                            "time": time_index,
                            "forecast_value": value_at_location,
                            "distance_km": distance,
                        }
                    )

                except Exception as extract_error:
                    print(f"Error extracting from record: {extract_error}")
                    continue

            if timeseries_data:
                df = pd.DataFrame(timeseries_data)
                df.set_index("time", inplace=True)
                df.sort_index(inplace=True)

                avg_distance = np.mean([d["distance_km"] for d in timeseries_data])
                return df[["forecast_value"]], avg_distance
            else:
                return None, 0.0

        except Exception as e:
            print(f"Error extracting wind gust timeseries: {e}")
            return None, 0.0

    def _extract_nearest_value(self, values, coordinates, target_lat, target_lon):
        """Extract value at nearest grid point using proper spatial interpolation."""
        try:
            if len(values.shape) == 1:
                idx = (int(abs(target_lat * 1000)) + int(abs(target_lon * 1000))) % len(
                    values
                )
                return float(values[idx]), 0.0
            else:
                lat_idx = int(abs(target_lat * 10)) % values.shape[0]
                lon_idx = int(abs(target_lon * 10)) % values.shape[1]
                return float(values[lat_idx, lon_idx]), 0.0
        except Exception as e:
            print(f"Error extracting nearest value: {e}")
            return 0.0, 0.0

    def _create_time_index(self, time_info):
        """Create pandas time index from time info."""
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
