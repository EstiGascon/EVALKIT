"""Data Acquisition Module.

This module contains classes and functions for retrieving meteorological data
from Mars Archive with intelligent handling of parameters that have different
step requirements.
"""

import datetime
from pathlib import Path
from typing import Any

import earthkit.data as ek

from helpers.parameter_mapper import ConfigurationManager


class MarsArchiveDataRetriever:
    """Main class for retrieving weather data from different sources."""

    def __init__(self, source: str = "mars", **kwargs):
        """Initialize the data retriever.

        Args:
            source: Data source ("mars" for Mars Archive, "file" for local files)
            **kwargs: Additional configuration parameters

        """
        self.source = source
        self.config = kwargs
        self.config_manager = ConfigurationManager()

    def retrieve_surface_data(  # noqa: PLR0913
        self,
        param: list[str],
        start_step: int | None = None,
        end_step: int | None = None,
        date: datetime.date | str | None = None,
        time: str = "00:00:00",
        model: str = "aifs-single",
        stream: str | None = None,
        type: str | None = None,
        levtype: str | None = None,
        area: list[float] | None = None,
        grid: list[float] | None = None,
        step_list: list[int] | None = None,
    ) -> dict:
        """Retrieve surface meteorological data from ECMWF.

        Automatically handles parameters with different step requirements by
        making separate requests and merging the results.

        Args:
            param: List of parameter short names (e.g., ['10u', '10v', 'tp'])
            start_step: Starting forecast step (optional if step_list provided)
            end_step: Ending forecast step (optional if step_list provided)
            date: Forecast date as datetime.date object or string "YYYY-MM-DD"
            time: Forecast time in format "HH:MM:SS" (default: "00:00:00")
            model: Model name (default: "aifs-single")
            stream: Data stream (optional, uses model default if None)
            type: Data type (optional, uses model default if None)
            levtype: Level type (optional, uses model default if None)
            area: Bounding box [north, west, south, east] (optional, uses config default if None)
            grid: Grid resolution [lat_res, lon_res] (optional)
            step_list: Specific list of steps to download (overrides start_step/end_step)

        Returns:
            Dictionary containing retrieved data and metadata

        Raises:
            ValueError: If invalid parameters or configuration
            RuntimeError: If data retrieval fails

        """
        if isinstance(date, str):
            date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

        filtered_param = self._filter_params_for_model(param, model)

        if not filtered_param:
            raise ValueError(
                f"No valid parameters remaining after filtering for {model} model capabilities. "
                f"Requested parameters: {param}"
            )

        try:
            model_info = self.config_manager.get_model_info(model)
        except ValueError as e:
            raise ValueError(f"Model '{model}' not found in configuration") from e

        stream = stream or model_info.get("stream", "oper")
        type = type or model_info.get("type", "fc")
        levtype = levtype or model_info.get("levtype", "sfc")

        if area is None:
            default_bbox = self.config_manager.get_default_bbox()
            area = [
                default_bbox["north"],
                default_bbox["west"],
                default_bbox["south"],
                default_bbox["east"],
            ]

        class_model = self.config_manager.get_model_class(model)

        if step_list is not None:
            steps_to_download = sorted(step for step in step_list if step != 0)

            if (
                self.config_manager.supports_custom_step_expansion(model)
                and steps_to_download
            ):
                steps_to_download = self._expand_custom_steps(
                    steps_to_download, model, date
                )
                print(
                    f" {model}: Expanded custom steps to {len(steps_to_download)} steps"
                )
            else:
                print(f" {model}: Using {len(steps_to_download)} custom steps")
        else:
            if start_step is None or end_step is None:
                raise ValueError(
                    "Either step_list or both start_step and end_step must be provided"
                )

            steps_to_download = self._generate_step_list(
                start_step, end_step, model, date
            )
            print(
                f" Generated {len(steps_to_download)} steps: {steps_to_download[:10]}{'...' if len(steps_to_download) > 10 else ''}"  # noqa: PLR2004
            )  # noqa: PLR2004

        param_groups = self._group_parameters_by_step_requirements(
            filtered_param, steps_to_download
        )

        if len(param_groups) > 1:
            print(
                f"  Parameters require {len(param_groups)} separate requests due to different step requirements"
            )
            return self._retrieve_with_multiple_requests(
                param_groups,
                date,
                time,
                model,
                stream,
                type,
                levtype,
                area,
                grid,
                class_model,
                step_list is not None,
            )
        else:
            single_group = list(param_groups.values())[0]
            return self._retrieve_single_request(
                single_group["params"],
                single_group["steps"],
                date,
                time,
                model,
                stream,
                type,
                levtype,
                area,
                grid,
                class_model,
                step_list is not None,
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
            print(f"Skipping {unavailable} for {model} (not available in this model)")
            if filtered:
                print(f"   Retrieving: {filtered}")

        return filtered

    def _group_parameters_by_step_requirements(
        self, param: list[str], steps: list[int]
    ) -> dict[str, dict]:
        """Group parameters by their step requirements.

        Args:
            param: List of parameter short names
            steps: List of forecast steps

        Returns:
            Dictionary mapping group_key to {params: [...], steps: [...], requirement: {...}}

        """
        param_groups = {}

        for p in param:
            requirement = self.config_manager.get_step_requirement(p)

            if requirement and requirement.get("type") == "multiple_of":
                required_interval = requirement.get("value")
                group_key = f"interval_{required_interval}h"

                compatible_steps = [
                    step for step in steps if step % required_interval == 0
                ]

                if not compatible_steps:
                    min_step = min(steps)
                    max_step = max(steps)
                    start_multiple = (
                        (min_step + required_interval - 1) // required_interval
                    ) * required_interval
                    compatible_steps = list(
                        range(start_multiple, max_step + 1, required_interval)
                    )

                if group_key not in param_groups:
                    param_groups[group_key] = {
                        "params": [],
                        "steps": compatible_steps,
                        "requirement": requirement,
                    }

                param_groups[group_key]["params"].append(p)
                print(
                    f" Parameter '{p}' grouped with {required_interval}h interval: {len(compatible_steps)} steps"
                )

            else:
                group_key = "standard"

                if group_key not in param_groups:
                    param_groups[group_key] = {
                        "params": [],
                        "steps": steps,
                        "requirement": None,
                    }

                param_groups[group_key]["params"].append(p)

        for group_key, group_info in param_groups.items():
            params_str = ", ".join(group_info["params"])
            steps_count = len(group_info["steps"])
            print(
                f"   • {group_key}: {len(group_info['params'])} params ({params_str}) - {steps_count} steps"
            )

        return param_groups

    def _retrieve_with_multiple_requests(  # noqa: PLR0913
        self,
        param_groups: dict[str, dict],
        date: datetime.date,
        time: str,
        model: str,
        stream: str,
        type: str,
        levtype: str,
        area: list[float],
        grid: list[float] | None,
        class_model: str,
        custom_steps_used: bool,
    ) -> dict:
        """Make multiple requests for parameters with different step requirements and merge results.

        Args:
            param_groups: Dictionary of parameter groups with their step requirements
            date: Forecast date
            time: Forecast time
            model: Model name
            stream: Data stream
            type: Data type
            levtype: Level type
            area: Geographic area
            grid: Grid resolution
            class_model: MARS class
            custom_steps_used: Whether custom steps were used

        Returns:
            Dictionary containing merged dataset and metadata

        """
        date_str = (
            date.strftime("%Y-%m-%d") if isinstance(date, datetime.date) else date
        )
        all_datasets = []
        all_metadata = []

        for group_key, group_info in param_groups.items():
            params = group_info["params"]
            steps = group_info["steps"]

            param_ids = self.config_manager.get_param_ids(params)

            request_params = {
                "param": param_ids,
                "class": class_model,
                "step": steps,
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
                # MARS uses SQLite internally. $TMPDIR and $SCRATCH are on Lustre,
                # which does not support SQLite POSIX file locking. Use /tmp (local
                # tmpfs) to avoid "unable to open database file" errors.
                import os as _os
                _orig_tmpdir = _os.environ.get("TMPDIR")
                _mars_tmp = f"/tmp/mars_tmp_{_os.environ.get('USER', 'evalkit')}"
                _os.makedirs(_mars_tmp, exist_ok=True)
                _os.environ["TMPDIR"] = _mars_tmp
                try:
                    ds = ek.from_source(self.source, **request_params)
                finally:
                    if _orig_tmpdir is None:
                        _os.environ.pop("TMPDIR", None)
                    else:
                        _os.environ["TMPDIR"] = _orig_tmpdir
                all_datasets.append(ds)

                all_metadata.append(
                    {
                        "group": group_key,
                        "params": params,
                        "param_ids": param_ids,
                        "steps": steps,
                        "step_count": len(steps),
                        "field_count": len(param_ids) * len(steps),
                    }
                )

                print("    Success!")

            except Exception as e:
                print(f"Failed: {str(e)}")
                raise RuntimeError(f"Request failed for {group_key}: {str(e)}") from e

        print(f"\n Merging {len(all_datasets)} datasets...")
        if len(all_datasets) == 1:
            combined_ds = all_datasets[0]
        else:
            try:
                combined_ds = sum(all_datasets[1:], all_datasets[0])
                print("Successfully merged datasets")
            except Exception as e:
                print(f"Warning: Could not merge datasets: {e}")
                print("   Using first dataset only")
                combined_ds = all_datasets[0]

        all_params = []
        total_expected_fields = 0
        for meta in all_metadata:
            all_params.extend(meta["params"])
            total_expected_fields += meta["field_count"]

        metadata = {
            "param": all_params,
            "param_ids": self.config_manager.get_param_ids(all_params),
            "class": class_model,
            "date": date_str,
            "time": time,
            "model": model,
            "stream": stream,
            "type": type,
            "levtype": levtype,
            "area": area,
            "grid": grid,
            "total_params": len(all_params),
            "expected_fields": total_expected_fields,
            "custom_steps_used": custom_steps_used,
            "split_requests": True,
            "request_groups": all_metadata,
            "total_requests": len(all_metadata),
            "retrieval_timestamp": datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }

        print("\n All requests completed successfully!")
        print(f"   Total parameters: {len(all_params)}")
        print(f"   Total expected fields: {total_expected_fields}")
        print(f"   Split into {len(all_metadata)} requests")

        return {
            "dataset": combined_ds,
            "metadata": metadata,
        }

    def _retrieve_single_request(  # noqa: PLR0913
        self,
        param: list[str],
        steps: list[int],
        date: datetime.date,
        time: str,
        model: str,
        stream: str,
        type: str,
        levtype: str,
        area: list[float],
        grid: list[float] | None,
        class_model: str,
        custom_steps_used: bool,
    ) -> dict:
        """Make a single MARS request.

        Args:
            param: List of parameters
            steps: List of forecast steps
            date: Forecast date
            time: Forecast time
            model: Model name
            stream: Data stream
            type: Data type
            levtype: Level type
            area: Geographic area
            grid: Grid resolution
            class_model: MARS class
            custom_steps_used: Whether custom steps were used

        Returns:
            Dictionary containing dataset and metadata

        """
        date_str = (
            date.strftime("%Y-%m-%d") if isinstance(date, datetime.date) else date
        )

        param_ids = self.config_manager.get_param_ids(param)

        request_params = {
            "param": param_ids,
            "class": class_model,
            "step": steps,
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
            print(" Making single MARS request...")
            print(f"   Parameters: {len(param_ids)} ({param_ids})")
            print(f"   Steps: {len(steps)}")
            print(f"   Expected fields: {len(param_ids) * len(steps)}")

            # MARS uses SQLite internally. $TMPDIR and $SCRATCH are on Lustre,
            # which does not support SQLite POSIX file locking. Use /tmp (local
            # tmpfs) to avoid "unable to open database file" errors.
            import os as _os
            _orig_tmpdir = _os.environ.get("TMPDIR")
            _mars_tmp = f"/tmp/mars_tmp_{_os.environ.get('USER', 'evalkit')}"
            _os.makedirs(_mars_tmp, exist_ok=True)
            _os.environ["TMPDIR"] = _mars_tmp
            try:
                ds = ek.from_source(self.source, **request_params)
            finally:
                if _orig_tmpdir is None:
                    _os.environ.pop("TMPDIR", None)
                else:
                    _os.environ["TMPDIR"] = _orig_tmpdir

            metadata = {
                "param": param,
                "param_ids": param_ids,
                "class": class_model,
                "steps": steps,
                "date": date_str,
                "time": time,
                "model": model,
                "stream": stream,
                "type": type,
                "levtype": levtype,
                "area": area,
                "grid": grid,
                "total_steps": len(steps),
                "total_params": len(param),
                "expected_fields": len(param) * len(steps),
                "custom_steps_used": custom_steps_used,
                "split_requests": False,
                "retrieval_timestamp": datetime.datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }

            print(f" Successfully retrieved {metadata['expected_fields']} fields")

            return {
                "dataset": ds,
                "metadata": metadata,
            }

        except Exception as e:
            error_msg = f"Error retrieving data from Mars Archive: {str(e)}"
            print(" MARS Request failed!")
            print(f"   Error: {error_msg}")
            print(f"   Request params: {request_params}")
            raise RuntimeError(error_msg) from e

    def _generate_step_list(
        self,
        start_step: int,
        end_step: int,
        model: str,
        date: datetime.date | None,
    ) -> list[int]:
        """Generate appropriate step list based on model and step range.

        Args:
            start_step: Starting forecast step
            end_step: Ending forecast step
            model: Model name
            date: Forecast date

        Returns:
            List of forecast steps

        """
        return self.config_manager.generate_steps(start_step, end_step, model, date)

    def _expand_custom_steps(
        self, custom_steps: list[int], model: str, forecast_date: datetime.date | None
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

    def load_source_file_data(self, file_path: str) -> Any:
        """Load meteorological data from local files from MARS Archive using earthkit-data.

        Args:
            file_path: Path to the data file

        Returns:
            earthkit-data dataset object

        Raises:
            FileNotFoundError: If the file doesn't exist
            RuntimeError: If failed to load the file

        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            ds = ek.from_source("file", file_path)
            ds = ds.sel(step=lambda x: x != 0)
            return ds

        except Exception as e:
            raise RuntimeError(f"Failed to load Source file {file_path}: {str(e)}")
