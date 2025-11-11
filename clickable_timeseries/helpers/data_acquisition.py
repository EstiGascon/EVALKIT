import datetime
from typing import Any

import earthkit.data as ekd
import pandas as pd
from helpers.parameter_mapper import ConfigurationManager


class BoundingBoxManager:
    """Class for managing bounding box operations and storage."""

    def __init__(self):
        """Initialize the BoundingBoxManager with empty state."""
        self.current_bbox = None
        self.saved_bboxes = []
        self.current_bbox_params = {}

    def set_current_bbox(
        self, bounds: tuple[float, float, float, float], num_stations: int = 0
    ):
        """Set the current bounding box with additional parameters."""
        min_lon, min_lat, max_lon, max_lat = bounds
        self.current_bbox = bounds
        self.current_bbox_params = {
            "bbox": bounds,
            "west": min_lon,
            "south": min_lat,
            "east": max_lon,
            "north": max_lat,
            "width_deg": max_lon - min_lon,
            "height_deg": max_lat - min_lat,
            "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "num_stations": num_stations,
        }

    def get_current_bbox(self) -> tuple[float, float, float, float] | None:
        """Get the current bounding box coordinates."""
        return self.current_bbox

    def get_current_bbox_params(self) -> dict | None:
        """Get the current bounding box with all parameters."""
        return self.current_bbox_params.copy() if self.current_bbox_params else None


class ForecastDataLoader:
    """Class for loading forecast data from Mars Archive and local files."""

    def __init__(
        self,
        source: str = "mars",
        bbox_manager: BoundingBoxManager | None = None,
        **kwargs,
    ):
        """Initialize the ForecastDataLoader.

        Args:
            source (str): Data source ("mars" for Mars Archive, "file" for local files)
            bbox_manager (BoundingBoxManager): Optional bounding box manager instance
            **kwargs: Additional configuration parameters

        """
        self.source = source
        self.config = kwargs
        self.loaded_datasets = {}
        self.dataset_metadata = {}
        self.bbox_manager = bbox_manager or BoundingBoxManager()
        self.config_manager = ConfigurationManager()

    def retrieve_data_by_date_range(  # noqa: PLR0913
        self,
        param: list[str],
        start_date: datetime.date,
        end_date: datetime.date,
        time: str = "00:00:00",
        model: str = "aifs-single",
        stream: str | None = None,
        type: str | None = None,
        levtype: str | None = None,
        grid: list[float] | None = None,
        use_bbox: bool = True,
        custom_area: list[float] | None = None,
        custom_steps: list[int] | None = None,
    ) -> dict[str, Any]:
        """Retrieve meteorological data from Mars Archive based on date range."""
        if end_date < start_date:
            raise ValueError("End date must be after or equal to start date")

        # Get area
        if custom_area:
            area = custom_area
        elif use_bbox:
            area = self._get_area_from_bbox_manager()
        else:
            default_bbox = self.config_manager.get_default_bbox()
            area = [
                default_bbox["north"],
                default_bbox["west"],
                default_bbox["south"],
                default_bbox["east"],
            ]

        date_str = start_date.strftime("%Y-%m-%d")

        # Filter parameters based on model availability
        filtered_param = self._filter_params_for_model(param, model)

        if not filtered_param:
            raise ValueError(
                f"No valid parameters remaining after filtering for {model} model capabilities"
            )

        # Get model configuration from config
        try:
            model_info = self.config_manager.get_model_info(model)
        except ValueError as e:
            raise ValueError(f"Model '{model}' not found in configuration") from e

        # Use config values unless explicitly overridden
        stream = stream or model_info.get("stream", "oper")
        type = type or model_info.get("type", "fc")
        levtype = levtype or model_info.get("levtype", "sfc")

        return self._retrieve_single_request(
            filtered_param,
            start_date,
            end_date,
            time,
            model,
            stream,
            type,
            levtype,
            area,
            grid,
            date_str,
            custom_steps,
        )

    def _filter_params_for_model(self, param: list[str], model: str) -> list[str]:
        """Filter parameters based on model availability.

        Args:
            param: List of parameter names to filter
            model: Model name (e.g., 'aifs-single', 'ifs-single')

        Returns:
            Filtered list of parameters available for the model

        """
        filtered = []
        unavailable = []

        for p in param:
            try:
                param_info = self.config_manager.get_param_info(p)
                available_models = param_info.get("available_models", [])

                if not available_models or model in available_models:
                    filtered.append(p)
                else:
                    unavailable.append(p)
            except ValueError:
                filtered.append(p)

        if unavailable:
            print(
                f"ℹ️  Skipping {unavailable} for {model} (not available in this model)"
            )
            if filtered:
                print(f"   Retrieving: {filtered}")

        return filtered

    def _retrieve_single_request(  # noqa: PLR0913
        self,
        param: list[str],
        start_date: datetime.date,
        end_date: datetime.date,
        time: str,
        model: str,
        stream: str,
        type: str,
        levtype: str,
        area: list[float],
        grid: list[float] | None,
        date_str: str,
        custom_steps: list[int] | None = None,
    ) -> dict[str, Any]:
        """Handle single request."""
        param_ids = self.config_manager.get_param_ids(param)
        print(f"Converting parameters {param} to IDs {param_ids}")

        # Get class from config instead of hardcoding
        class_model = self.config_manager.get_model_class(model)
        print(f"Using MARS class '{class_model}' for model '{model}'")

        # Calculate or expand steps
        if custom_steps:
            # Check if model supports custom step expansion
            if self.config_manager.supports_custom_step_expansion(model):
                steps_to_download = self._expand_custom_steps(
                    custom_steps, model, start_date
                )
                print(
                    f"{model}: Expanded custom steps {custom_steps} to {steps_to_download}"
                )
            else:
                steps_to_download = custom_steps.copy()
                print(f"{model}: Using exact custom steps: {steps_to_download}")
        else:
            steps_to_download = self._calculate_steps_from_date_range(
                start_date, end_date, time, model
            )
            print(f"Using calculated steps: {steps_to_download}")

        request_params = {
            "param": param_ids,
            "class": class_model,
            "step": steps_to_download,
            "stream": stream,
            "date": date_str,
            "time": time,
            "type": type,
            "levtype": levtype,
            "area": area,
        }

        if grid is not None:
            request_params["grid"] = grid

        try:
            print(f"Making MARS request with param IDs: {param_ids}")
            print(f"Model config: class={class_model}, stream={stream}, type={type}")
            ds = ekd.from_source("mars", **request_params)

            model_key = f"{model}_{start_date.strftime('%Y%m%d')}"
            metadata = {
                "param": param,
                "param_ids": param_ids,
                "class": class_model,
                "steps": steps_to_download,
                "original_custom_steps": custom_steps,
                "start_date": start_date,
                "end_date": end_date,
                "time": time,
                "model": model,
                "stream": stream,
                "type": type,
                "levtype": levtype,
                "area": area,
                "grid": grid,
                "total_steps": len(steps_to_download),
                "custom_steps_used": custom_steps is not None,
                "custom_steps": custom_steps,
                "retrieval_timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "bbox_info": self.bbox_manager.get_current_bbox_params(),
                "split_requests": False,
            }

            if hasattr(ds, "metadata"):
                metadata["datetime_values"] = ds.metadata("valid_datetime")
            if hasattr(ds, "to_latlon"):
                metadata["grid_coordinates"] = ds.to_latlon()

            self.dataset_metadata[model_key] = metadata
            self.loaded_datasets[model_key] = ds

            return {"dataset": ds, "metadata": metadata, "model_key": model_key}

        except Exception as e:
            error_msg = f"Error retrieving data from Mars Archive: {str(e)}"
            print("❌ MARS Request failed!")
            print(f"   Error: {error_msg}")
            print(f"   Request params: {request_params}")
            raise RuntimeError(error_msg) from e

    def _calculate_steps_from_date_range(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        start_time: str = "00:00:00",
        model: str = "ifs-single",
    ) -> list[int]:
        """Calculate forecast steps based on start and end dates.

        Args:
            start_date: Forecast start date
            end_date: Forecast end date
            start_time: Forecast start time
            model: Model name to determine step intervals

        Returns:
            List of forecast steps in hours

        """
        start_datetime = datetime.datetime.combine(
            start_date, datetime.time.fromisoformat(start_time)
        )
        end_datetime = datetime.datetime.combine(
            end_date + datetime.timedelta(days=1),
            datetime.time.fromisoformat(start_time),
        )

        total_hours = int((end_datetime - start_datetime).total_seconds() / 3600)

        if total_hours <= 0:
            raise ValueError("End date must be after start date")

        # Use config manager to generate steps
        return self.config_manager.generate_steps(0, total_hours, model, start_date)

    def _expand_custom_steps(
        self, custom_steps: list[int], model: str, forecast_date: datetime.date
    ) -> list[int]:
        """Expand custom steps following model's step pattern.

        Args:
            custom_steps: List of user-selected steps
            model: Model name
            forecast_date: Forecast date for date-based patterns

        Returns:
            Expanded list of steps following model's pattern

        """
        if not custom_steps:
            return custom_steps

        min_step = min(custom_steps)
        max_step = max(custom_steps)

        expanded_steps = self.config_manager.generate_steps(
            min_step, max_step, model, forecast_date
        )

        return expanded_steps

    def _get_area_from_bbox_manager(self) -> list[float]:
        """Get area coordinates from the bounding box manager.

        Returns:
            List[float]: Area coordinates in Mars Archive format [north, west, south, east]

        Raises:
            ValueError: If no bounding box is set

        """
        bbox = self.bbox_manager.get_current_bbox()
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            return [max_lat, min_lon, min_lat, max_lon]
        else:
            raise ValueError(
                "No bounding box set in bbox_manager. Please set a bounding box using "
                "set_bounding_box() method or provide custom_area parameter."
            )

    def get_dataset(self, model_key: str) -> Any | None:
        """Get loaded dataset for a specific model key."""
        return self.loaded_datasets.get(model_key)

    def get_all_datasets(self) -> dict[str, Any]:
        """Get all loaded datasets."""
        return self.loaded_datasets.copy()

    def load_grib_file(
        self, grib_file_path: str, model: str | None = None
    ) -> Any | None:
        """Load GRIB data from file.

        Args:
            grib_file_path: Path to GRIB file
            model: Model name (optional, will auto-detect if None)

        Returns:
            earthkit-data dataset object or None if failed

        """
        try:
            print(f"Loading GRIB file: {grib_file_path}")
            ds = ekd.from_source("file", grib_file_path)
            return ds
        except Exception as e:
            raise RuntimeError(f"Failed to load Source file {grib_file_path}: {str(e)}")
