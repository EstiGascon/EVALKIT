import math
import traceback
from typing import Any

import numpy as np
import pandas as pd


class TemperatureProcessor:
    """Processor for temperature calculations with daily maximum and minimum over 24-hour periods."""

    def __init__(self):
        """Initialize the temperature processor retriever."""
        self.processed_datasets = {}
        self.available_intervals = {}

    def process_temperature_datasets(self, all_datasets: dict[str, Any]) -> bool:
        """Process datasets to calculate temperature with daily max/min."""
        try:
            self.processed_datasets = {}
            self.available_intervals = {}

            for model_name, dataset in all_datasets.items():
                temp_params = self._get_available_temperature_params(dataset)
                if not temp_params:
                    print(f"{model_name} missing temperature parameters (2t, 2d)")
                    continue

                intervals_processed = []

                for temp_param in temp_params:
                    temp_data = self._extract_temperature_data(
                        dataset, model_name, temp_param
                    )
                    if temp_data is None:
                        continue

                    hourly_key = f"{model_name}_{temp_param}_hourly"
                    self.processed_datasets[hourly_key] = temp_data
                    intervals_processed.append(f"{temp_param}_hourly")

                    try:
                        daily_max_data = self._calculate_daily_extremes(
                            temp_data, model_name, temp_param, "max"
                        )
                        if daily_max_data is not None:
                            max_key = f"{model_name}_{temp_param}_24h_max"
                            self.processed_datasets[max_key] = daily_max_data
                            intervals_processed.append(f"{temp_param}_24h_max")
                            print(f"Processed 24h max for {temp_param} in {model_name}")

                        daily_min_data = self._calculate_daily_extremes(
                            temp_data, model_name, temp_param, "min"
                        )
                        if daily_min_data is not None:
                            min_key = f"{model_name}_{temp_param}_24h_min"
                            self.processed_datasets[min_key] = daily_min_data
                            intervals_processed.append(f"{temp_param}_24h_min")
                            print(f"Processed 24h min for {temp_param} in {model_name}")

                    except Exception as e:
                        print(
                            f"Error calculating daily extremes for {temp_param} in {model_name}: {e}"
                        )
                        continue

                if intervals_processed:
                    self.available_intervals[model_name] = intervals_processed
                    print(
                        f"Processed temperature for {model_name}: {intervals_processed}"
                    )

            return len(self.processed_datasets) > 0

        except Exception as e:
            print(f"Error processing temperature datasets: {e}")
            traceback.print_exc()
            return False

    def _get_available_temperature_params(self, dataset) -> list[str]:
        """Check which temperature parameters are available in the dataset."""
        available_params = []

        for param in ["2t", "2d"]:
            try:
                temp_fields = dataset.sel(param=param)
                if len(temp_fields) > 0:
                    available_params.append(param)
            except Exception:
                continue

        return available_params

    def _extract_temperature_data(self, dataset, model_name: str, temp_param: str):
        """Extract temperature data from dataset."""
        try:
            temp_fields = dataset.sel(param=temp_param)

            if len(temp_fields) == 0:
                return None

            temp_records = []

            for temp_field in temp_fields:
                try:
                    temp_values = temp_field.values

                    time_info = self._extract_time_info(temp_field)
                    coord_info = self._extract_coordinate_info(temp_field)

                    record = {
                        "values": temp_values,
                        "time": time_info,
                        "coordinates": coord_info,
                        "metadata": {
                            "param": temp_param,
                            "shortName": temp_param,
                            "units": "K",
                            "original_param": temp_param,
                        },
                    }

                    temp_records.append(record)

                except Exception as field_error:
                    print(
                        f"Error processing temperature field in {model_name}: {field_error}"
                    )
                    continue

            if temp_records:
                return {
                    "records": temp_records,
                    "model": model_name,
                    "param": temp_param,
                }
            else:
                return None

        except Exception as e:
            print(f"Error extracting temperature data for {model_name}: {e}")
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

    def _calculate_daily_extremes(  # noqa: PLR0912, PLR0915
        self, temp_data, model_name: str, temp_param: str, extreme_type: str
    ):
        """Calculate daily maximum or minimum with proper handling of data frequency and CORRECT datetime."""
        try:
            if not temp_data or "records" not in temp_data:
                return None

            records = temp_data["records"]

            base_date, base_time = self._extract_base_datetime_from_records(records)

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
                f"Calculating daily {extreme_type} for {len(records)} records (data frequency: {data_frequency}h)"
            )

            step_record_map = {}
            for record in records:
                time_info = record.get("time", {})
                step = int(time_info.get("step", 0))
                step_record_map[step] = record

            sorted_steps = sorted(step_record_map.keys())
            daily_extreme_records = []

            daily_groups = {}
            for step in sorted_steps:
                day_group = step // 24
                if day_group not in daily_groups:
                    daily_groups[day_group] = []
                daily_groups[day_group].append(step)

            print(f"Created {len(daily_groups)} daily groups")

            for day_group, group_steps in daily_groups.items():
                if len(group_steps) == 0:
                    continue

                if len(group_steps) == 1:
                    print(
                        f"   Day {day_group}: skipping - only 1 record (step {group_steps[0]}h), need multiple records for daily {extreme_type}"
                    )
                    continue

                window_records = [step_record_map[step] for step in group_steps]

                print(
                    f"   Day {day_group}: calculating {extreme_type} over {len(window_records)} records from step {min(group_steps)}h to {max(group_steps)}h"
                )

                all_values = np.stack([r["values"] for r in window_records], axis=0)

                if extreme_type == "max":
                    extreme_values = np.max(all_values, axis=0)
                    sample_values = [float(r["values"].flat[0]) for r in window_records]
                    extreme_idx = np.argmax(sample_values)
                elif extreme_type == "min":
                    extreme_values = np.min(all_values, axis=0)
                    sample_values = [float(r["values"].flat[0]) for r in window_records]
                    extreme_idx = np.argmin(sample_values)
                else:
                    raise ValueError(f"Unknown extreme type: {extreme_type}")

                representative_record = window_records[extreme_idx]
                group_steps[extreme_idx]

                extreme_time = representative_record["time"].copy()
                extreme_time["aggregation"] = f"24h_{extreme_type}"
                extreme_time["window_start_step"] = min(group_steps)
                extreme_time["window_end_step"] = max(group_steps)
                extreme_time["source_records"] = len(window_records)

                daily_step = day_group * 24
                extreme_time["step"] = daily_step

                proper_datetime = self._create_proper_datetime_for_step(
                    daily_step, base_date, base_time
                )
                extreme_time["valid_time"] = proper_datetime.isoformat()

                extreme_record = {
                    "values": extreme_values,
                    "time": extreme_time,
                    "coordinates": representative_record["coordinates"],
                    "metadata": {
                        "param": f"{temp_param}_24h_{extreme_type}",
                        "shortName": f"{temp_param}_{extreme_type}",
                        "units": "K",
                        "aggregation": f"24h_{extreme_type}",
                    },
                }

                daily_extreme_records.append(extreme_record)

            print(f"Created {len(daily_extreme_records)} daily {extreme_type} records")

            if daily_extreme_records:
                return {
                    "records": daily_extreme_records,
                    "model": model_name,
                    "param": f"{temp_param}_24h_{extreme_type}",
                    "aggregation": f"24h_{extreme_type}",
                }
            else:
                return None

        except Exception as e:
            print(f"Error calculating 24h {extreme_type}: {e}")
            traceback.print_exc()
            return None

    def _extract_base_datetime_from_records(self, records):
        """Extract base date and time from temperature records."""
        try:
            if records and len(records) > 0:
                first_record = records[0]

                metadata = first_record.get("metadata", {})
                if "date" in metadata and "time" in metadata:
                    return metadata["date"], metadata["time"]

                time_info = first_record.get("time", {})
                if "date" in time_info and "time" in time_info:
                    return time_info["date"], time_info["time"]

                if "valid_time" in time_info:
                    try:
                        dt = pd.to_datetime(time_info["valid_time"])
                        date = int(dt.strftime("%Y%m%d"))
                        time = int(dt.strftime("%H%M"))
                        return date, time
                    except Exception:
                        pass

            now = pd.Timestamp.now()
            date = int(now.strftime("%Y%m%d"))
            time = 0
            print(
                f"Warning: Could not extract base datetime from records, using fallback: {date} {time}"
            )
            return date, time

        except Exception as e:
            print(f"Error extracting base datetime from records: {e}")
            now = pd.Timestamp.now()
            date = int(now.strftime("%Y%m%d"))
            time = 0
            return date, time

    def _create_proper_datetime_for_step(self, step_hours, base_date, base_time):
        """Create proper datetime for a given step using base date/time."""
        try:
            if base_date is None or base_time is None:
                base_datetime = pd.Timestamp.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            elif isinstance(base_date, int | str):
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

            return base_datetime + pd.Timedelta(hours=step_hours)
        except Exception as e:
            print(f"Error creating datetime for step {step_hours}: {e}")
            return pd.Timestamp.now() + pd.Timedelta(hours=step_hours)

    def extract_temperature_timeseries(
        self,
        model_name: str,
        lat: float,
        lon: float,
        base_param: str,
        interval: str = "hourly",
    ) -> tuple[pd.DataFrame, float]:
        """Extract temperature timeseries using simple approach like wind speed processor.

        Args:
            model_name: Name of the model
            lat: Latitude
            lon: Longitude
            base_param: Base parameter ('2t' or '2d')
            interval: Interval type ('hourly', '24h_max', '24h_min')

        """
        try:
            if interval == "hourly":
                dataset_key = f"{model_name}_{base_param}_hourly"
            else:
                dataset_key = f"{model_name}_{base_param}_{interval}"

            if dataset_key not in self.processed_datasets:
                print(f"No temperature data for {dataset_key}")
                return None, 0.0

            temp_data = self.processed_datasets[dataset_key]

            timeseries_data = []

            for record in temp_data["records"]:
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
            print(f"Error extracting temperature timeseries: {e}")
            return None, 0.0

    def _extract_nearest_value(self, values, coordinates, target_lat, target_lon):
        """Extract value at nearest grid point using proper spatial interpolation."""
        try:
            lat_first = coordinates.get("latitudeOfFirstGridPointInDegrees")
            lon_first = coordinates.get("longitudeOfFirstGridPointInDegrees")
            lat_last = coordinates.get("latitudeOfLastGridPointInDegrees")
            lon_last = coordinates.get("longitudeOfLastGridPointInDegrees")
            ni = coordinates.get("Ni")
            nj = coordinates.get("Nj")

            grid_available = (
                lat_first is not None
                and lon_first is not None
                and lat_last is not None
                and lon_last is not None
                and ni
                and nj
            )

            if grid_available:
                try:
                    lat_step = (lat_last - lat_first) / (nj - 1) if nj > 1 else 0
                    lon_step = (lon_last - lon_first) / (ni - 1) if ni > 1 else 0

                    lat_idx = (
                        int(round((target_lat - lat_first) / lat_step))
                        if lat_step != 0
                        else 0
                    )
                    lat_idx = max(0, min(lat_idx, nj - 1))
                    lon_idx = (
                        int(round((target_lon - lon_first) / lon_step))
                        if lon_step != 0
                        else 0
                    )
                    lon_idx = max(0, min(lon_idx, ni - 1))

                    if len(values.shape) == 1:
                        combined_idx = lat_idx * ni + lon_idx
                        combined_idx = max(0, min(combined_idx, len(values) - 1))
                        extracted_value = float(values[combined_idx])
                    else:
                        extracted_value = float(values[lat_idx, lon_idx])

                    actual_lat = lat_first + lat_idx * lat_step
                    actual_lon = lon_first + lon_idx * lon_step
                    distance_km = self._calculate_distance(
                        target_lat, target_lon, actual_lat, actual_lon
                    )
                    return extracted_value, distance_km
                except Exception as grid_error:
                    print(f"Grid interpolation failed: {grid_error}, using fallback")

            if len(values.shape) == 1:
                middle_idx = len(values) // 2
                return float(values[middle_idx]), 0.0
            else:
                middle_i = values.shape[0] // 2
                middle_j = values.shape[1] // 2
                return float(values[middle_i, middle_j]), 0.0

        except Exception as e:
            print(f"Error extracting nearest value: {e}")
            if len(values.shape) == 1:
                middle_idx = len(values) // 2
                return float(values[middle_idx]), 0.0
            else:
                middle_i = values.shape[0] // 2
                middle_j = values.shape[1] // 2
                return float(values[middle_i, middle_j]), 0.0

    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points in kilometers."""
        try:
            lat1_rad = math.radians(lat1)
            lon1_rad = math.radians(lon1)
            lat2_rad = math.radians(lat2)
            lon2_rad = math.radians(lon2)

            dlat = lat2_rad - lat1_rad
            dlon = lon2_rad - lon1_rad
            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
            )
            c = 2 * math.asin(math.sqrt(a))
            distance_km = 6371 * c

            return distance_km

        except Exception as e:
            print(f"Error calculating distance: {e}")
            return 0.0

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

    def _extract_base_datetime_from_field(self, field):
        """Extract base date and time from temperature field metadata."""
        try:
            metadata = field.metadata()

            def get_metadata_value(meta, key):
                if hasattr(meta, "get"):
                    return meta.get(key)
                try:
                    return meta(key)
                except Exception:
                    return None

            date = get_metadata_value(metadata, "date")
            time = get_metadata_value(metadata, "time")

            return date, time
        except Exception as e:
            print(f"Error extracting base datetime: {e}")
            return None, None
