import calendar
import datetime
import json
import traceback
from pathlib import Path
from typing import Any

import earthkit as ek  # type: ignore
import numpy as np  # type: ignore
import pandas as pd  # type: ignore
from earthkit.data import FieldList  # type: ignore


class BoundingBoxManager:
    """Class for managing bounding box operations and storage."""

    def __init__(self):
        """Initialize the BoundingBoxManager with empty state."""
        self.current_bbox = None
        self.current_bbox_params = {}

    def set_current_bbox(
        self, bounds: tuple[float, float, float, float], num_stations: int = 0
    ):
        """Set the current bounding box with additional parameters.

        Args:
            bounds (tuple): A tuple of (min_lon, min_lat, max_lon, max_lat).
            num_stations (int): Number of stations within the bounding box.

        """
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


class EnsembleDataRetriever:
    """Main class for retrieving ensemble analysis data."""

    def __init__(
        self,
        config_file: str = "model_config.json",
        source: str = "mars",
        bbox_manager: BoundingBoxManager | None = None,
        **kwargs,
    ):
        """Initialize the ensemble data retriever.

        Args:
            config_file: Path to the JSON configuration file containing model settings,
                parameter mappings, and use case definitions. Defaults to 'model_config.json'.
            source: Data source identifier ('mars' for ECMWF MARS archive, 'file' for local
                GRIB files). Defaults to 'mars'.
            bbox_manager: Optional BoundingBoxManager instance for managing geographic
                bounding boxes. If provided, enables automatic area retrieval for data requests.
                Defaults to None.
            **kwargs: Additional configuration parameters to be stored in self.config.

        """
        self.source = source
        self.config = kwargs
        self.config_file = Path(config_file)
        self.bbox_manager = bbox_manager
        self._load_config()

    def _load_config(self):
        """Load model configuration from JSON file."""
        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file {self.config_file} not found")

        with open(self.config_file) as f:
            config_data = json.load(f)

        self.model_configs = config_data.get("model_configs", {})
        self.use_cases = config_data.get("use_cases", {})
        self.surface_variables = config_data.get("surface_variables", {})
        self.pressure_levels = config_data.get("pressure_levels", {})
        self.parameter_mappings = config_data.get("parameter_mappings", {})
        self.pressure_level_map = self.parameter_mappings.get("pressure_levels", {})
        self.climate_param_map = self.parameter_mappings.get("climate_data", {})
        self.param_ids = self.parameter_mappings.get("param_ids", {})

    def _convert_params_to_ids(self, parameters: list[str]) -> list[str]:
        """Convert parameter short names to parameter IDs for MARS requests.

        Args:
            parameters: List of parameter short names

        Returns:
            List of parameter IDs (e.g., ['167.128', '228.128'])

        """
        param_ids = []
        for param in parameters:
            if param in self.param_ids:
                param_ids.append(self.param_ids[param])
            else:
                print(
                    f"Warning: No parameter ID mapping found for '{param}', using original name"
                )
                param_ids.append(param)
        return param_ids

    def _convert_climate_params_to_ids(self, parameters: list[str]) -> list[str]:
        """Convert parameter short names to climate data parameter IDs.

        Args:
            parameters: List of parameter short names

        Returns:
            List of climate data parameter IDs

        """
        climate_ids = []
        for param in parameters:
            if param in self.climate_param_map:
                climate_ids.append(self.climate_param_map[param])
            elif param in self.param_ids:
                climate_ids.append(self.param_ids[param])
            else:
                print(
                    f"Warning: No climate data parameter ID mapping found for '{param}', using original name"
                )
                climate_ids.append(param)
        return climate_ids

    def get_available_steps(  # noqa: PLR0913
        self,
        model_class: str,
        forecast_type: str,
        forecast_name: str,
        start_step: int,
        end_step: int,
    ) -> list[int]:
        """Get available forecast steps for a model between start and end step.

        Args:
            model_class: 'ifs' or 'aifs'
            forecast_type: 'deterministic' or 'probabilistic'
            forecast_name: e.g., 'fc', 'cf', 'pf', 'em'
            start_step: Starting forecast step
            end_step: Ending forecast step

        Returns:
            list of available forecast steps

        """
        if model_class not in self.model_configs:
            raise ValueError(f"Model class '{model_class}' not found")

        model_config = self.model_configs[model_class]

        if (
            forecast_type in model_config
            and forecast_name in model_config[forecast_type]
        ):
            forecast_config = model_config[forecast_type][forecast_name]
            if "step_config" in forecast_config:
                step_config = forecast_config["step_config"]
            else:
                step_config = model_config.get("step_config", {})
        else:
            step_config = model_config.get("step_config", {})

        if step_config.get("type") == "range":
            model_start = step_config["start"]
            model_end = step_config["end"]
            model_step = step_config["step"]

            available_steps = list(range(model_start, model_end + 1, model_step))
            return [step for step in available_steps if start_step <= step <= end_step]

        elif step_config.get("type") == "intervals":
            intervals = step_config["intervals"]

            step_list = []
            for interval_start, interval_end, step_interval in intervals:
                current_start = max(interval_start, start_step)
                current_end = min(interval_end, end_step)

                if current_start <= current_end:
                    step_list.extend(
                        range(current_start, current_end + 1, step_interval)
                    )

            return sorted(set(step_list))

        else:
            raise ValueError(
                f"Unknown step configuration type for {model_class}/{forecast_name}"
            )

    def _get_area_from_bbox_manager(self) -> list[float]:
        """Get area coordinates from the bounding box manager."""
        if self.bbox_manager is None:
            raise ValueError("No bounding box manager provided")

        bbox = self.bbox_manager.get_current_bbox()
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            return [max_lat, min_lon, min_lat, max_lon]
        else:
            raise ValueError(
                "No bounding box set in bbox_manager. Please set a bounding box using "
                "set_current_bbox() method or provide custom_area parameter."
            )

    def _resolve_area(
        self, area: list[float] | None = None, use_bbox: bool = True
    ) -> list[float]:
        """Resolve the area to use for data retrieval.

        Args:
            area: Custom area coordinates [north, west, south, east]
            use_bbox: Whether to use bounding box manager if area is None

        Returns:
            Area coordinates [north, west, south, east]

        """
        if area is not None:
            return area
        elif use_bbox and self.bbox_manager is not None:
            return self._get_area_from_bbox_manager()
        else:
            return [72, -25, 34, 45]

    def retrieve_stamp_data(  # noqa: PLR0913
        self,
        model_class: str,
        forecast_date: str | datetime.date,
        forecast_time: str = "00:00:00",
        selected_steps: list[int] = None,
        start_step: int = 0,
        end_step: int = 240,
        parameters: list[str] = None,
        area: list[float] | None = None,
        use_bbox: bool = True,
        grid: list[float] | None = None,
        ensemble_members: list[int] | None = None,
        calculate_windspeed: bool = True,
        calculate_6h_precipitation: bool = True,
    ) -> dict[str, Any]:
        """Retrieve data for stamp plots.

        Args:
            model_class: 'ifs' or 'aifs'
            forecast_date: Forecast initialization date
            forecast_time: Forecast initialization time
            selected_steps: Specific steps to retrieve
            start_step: Starting forecast step
            end_step: Ending forecast step
            parameters: list of parameters to retrieve
            area: Geographic area [north, west, south, east] (if None, uses bbox_manager)
            use_bbox: Whether to use bbox_manager when area is None
            grid: Grid resolution
            ensemble_members: Specific ensemble members
            calculate_windspeed: Whether to calculate wind speed
            calculate_6h_precipitation: Whether to calculate 6-hour precipitation

        Returns:
            Dictionary containing HRES, control, and ensemble data

        """
        if parameters is None:
            parameters = self.use_cases.get("stamps", {}).get("typical_params")

        resolved_area = self._resolve_area(area, use_bbox)

        if selected_steps is None:
            available_steps = self.get_available_steps(
                model_class, "probabilistic", "pf", start_step, end_step
            )
            steps_to_retrieve = available_steps
        else:
            steps_to_retrieve = selected_steps

        if isinstance(forecast_date, str):
            date_str = forecast_date
        else:
            date_str = forecast_date.strftime("%Y-%m-%d")

        results = {}

        results["fc"] = self._retrieve_forecast_data(
            model_class=model_class,
            forecast_type="deterministic",
            forecast_name="fc",
            parameters=parameters,
            date=date_str,
            time=forecast_time,
            steps=steps_to_retrieve,
            area=resolved_area,
            grid=grid,
            calculate_windspeed=calculate_windspeed,
            calculate_6h_precipitation=calculate_6h_precipitation,
        )

        results["cf"] = self._retrieve_forecast_data(
            model_class=model_class,
            forecast_type="probabilistic",
            forecast_name="cf",
            parameters=parameters,
            date=date_str,
            time=forecast_time,
            steps=steps_to_retrieve,
            area=resolved_area,
            grid=grid,
            calculate_windspeed=calculate_windspeed,
            calculate_6h_precipitation=calculate_6h_precipitation,
        )

        results["pf"] = self._retrieve_forecast_data(
            model_class=model_class,
            forecast_type="probabilistic",
            forecast_name="pf",
            parameters=parameters,
            date=date_str,
            time=forecast_time,
            steps=steps_to_retrieve,
            area=resolved_area,
            grid=grid,
            ensemble_members=ensemble_members,
            calculate_windspeed=calculate_windspeed,
            calculate_6h_precipitation=calculate_6h_precipitation,
        )

        if use_bbox and self.bbox_manager:
            results["bbox_info"] = self.bbox_manager.get_current_bbox_params()

        return results

    def retrieve_plumes_meteograms_data(  # noqa: PLR0912, PLR0913
        self,
        model_class: str,
        forecast_date: str | datetime.date,
        forecast_time: str = "00:00:00",
        selected_steps: list[int] = None,
        start_step: int = 0,
        end_step: int = 240,
        parameters: list[str] = None,
        area: list[float] | None = None,
        use_bbox: bool = True,
        grid: list[float] | None = None,
        pressure_levels: list[int] | None = None,
        ensemble_members: list[int] | None = None,
        calculate_windspeed: bool = True,
        calculate_6h_precipitation: bool = True,
    ) -> dict[str, Any]:
        """Retrieve data for plumes and meteograms.

        Args:
            model_class: 'ifs' or 'aifs'
            forecast_date: Forecast initialization date
            forecast_time: Forecast initialization time
            selected_steps: Specific steps to retrieve
            start_step: Starting forecast step
            end_step: Ending forecast step
            parameters: list of parameters to retrieve
            area: Geographic area [north, west, south, east] (if None, uses bbox_manager)
            use_bbox: Whether to use bbox_manager when area is None
            grid: Grid resolution
            pressure_levels: Pressure levels for upper-air variables
            ensemble_members: Specific ensemble members
            calculate_windspeed: Whether to calculate wind speed
            calculate_6h_precipitation: Whether to calculate 6-hour precipitation

        Returns:
            Dictionary containing control, ensemble, and mean data

        """
        if parameters is None:
            parameters = self.use_cases.get("plumes", {}).get("typical_params")

        resolved_area = self._resolve_area(area, use_bbox)

        if isinstance(forecast_date, str):
            date_str = forecast_date
        else:
            date_str = forecast_date.strftime("%Y-%m-%d")

        results = {}

        levtype = "pl" if pressure_levels else "sfc"

        if selected_steps is None:
            available_steps = self.get_available_steps(
                model_class, "probabilistic", "pf", start_step, end_step
            )
            steps_to_retrieve = available_steps
        else:
            steps_to_retrieve = selected_steps

        results["pf"] = self._retrieve_forecast_data(
            model_class=model_class,
            forecast_type="probabilistic",
            forecast_name="pf",
            parameters=parameters,
            date=date_str,
            time=forecast_time,
            steps=steps_to_retrieve,
            area=resolved_area,
            grid=grid,
            levtype=levtype,
            pressure_levels=pressure_levels,
            ensemble_members=ensemble_members,
            calculate_windspeed=calculate_windspeed,
            calculate_6h_precipitation=calculate_6h_precipitation,
        )

        results["cf"] = self._retrieve_forecast_data(
            model_class=model_class,
            forecast_type="probabilistic",
            forecast_name="cf",
            parameters=parameters,
            date=date_str,
            time=forecast_time,
            steps=steps_to_retrieve,
            area=resolved_area,
            grid=grid,
            levtype=levtype,
            pressure_levels=pressure_levels,
            calculate_windspeed=calculate_windspeed,
            calculate_6h_precipitation=calculate_6h_precipitation,
        )

        if use_bbox and self.bbox_manager:
            results["bbox_info"] = self.bbox_manager.get_current_bbox_params()

        return results

    def retrieve_cdf_data(  # noqa: D417, PLR0912, PLR0913
        self,
        analysis_date: str | datetime.date,
        days_back: int = 3,
        selected_forecast_times: list[int] = None,
        parameters: list[str] = None,
        area: list[float] | None = None,
        use_bbox: bool = True,
        grid: list[float] | None = None,
        model_class: str = "ifs",
        calculate_windspeed: bool = True,
    ) -> dict[str, Any]:
        """Retrieve data for CDF analysis following Metview logic.

        For an analysis date, retrieve forecasts from the past N days
        where each forecast has a different lead time but all point to the same analysis date.

        Example for analysis_date="2025-06-17" and days_back=3:
        - Forecast from 2025-06-17 00Z, step 0-24h  -> valid for 2025-06-17
        - Forecast from 2025-06-16 00Z, step 24-48h -> valid for 2025-06-17
        - Forecast from 2025-06-15 00Z, step 48-72h -> valid for 2025-06-17

        Args:
            analysis_date: The target analysis date (what we're forecasting FOR)
            days_back: How many days back to go for forecast initialization dates
            selected_forecast_times: Forecast times (0 for 00:00, 12 for 12:00)
            parameters: List of parameters to retrieve
            area: Geographic area [north, west, south, east] (if None, uses bbox_manager)
            use_bbox: Whether to use bbox_manager when area is None
            grid: Grid resolution
            model_class: Model class ('ifs')

        Returns:
            Dictionary containing climate data and forecast data

        """
        if selected_forecast_times is None:
            selected_forecast_times = [0, 12]
        if parameters is None:
            parameters = self.use_cases.get("cdfs", {}).get("typical_params")
        resolved_area = self._resolve_area(area, use_bbox)

        if isinstance(analysis_date, str):
            analysis_date_obj = datetime.datetime.strptime(
                analysis_date, "%Y-%m-%d"
            ).date()
        else:
            analysis_date_obj = analysis_date

        climate_date = self._get_climate_data_date(analysis_date_obj)

        results = {
            "cd": {},
            "forecast_data": {},
            "metadata": {
                "analysis_date": analysis_date_obj.strftime("%Y-%m-%d"),
                "climate_date": climate_date.strftime("%Y-%m-%d"),
                "days_back": days_back,
                "forecast_times": selected_forecast_times,
                "bbox_info": self.bbox_manager.get_current_bbox_params()
                if use_bbox and self.bbox_manager
                else None,
            },
        }
        climate_parameters = self._map_to_climate_params(parameters)
        climate_step = "24-48"
        try:
            results["cd"] = self._retrieve_forecast_data(
                model_class=model_class,
                forecast_type="probabilistic",
                forecast_name="cd",
                parameters=climate_parameters,
                date=climate_date.strftime("%Y-%m-%d"),
                time="00:00:00",
                steps=[climate_step],
                area=resolved_area,
                grid=grid,
                calculate_windspeed=False,
                calculate_6h_precipitation=False,
            )
        except Exception as e:
            print(f"Failed to retrieve climate data: {e}")

        forecast_scenarios = []

        for days_ago in range(days_back + 1):
            for forecast_time in selected_forecast_times:
                forecast_date = analysis_date_obj - datetime.timedelta(days=days_ago)

                if forecast_time == 0:  # 00Z forecast
                    lead_start = days_ago * 24
                    lead_end = lead_start + 24
                else:  # 12Z forecast
                    lead_start = days_ago * 24 - 12
                    lead_end = lead_start + 24

                    if lead_start < 0:
                        continue

                step_list = list(range(lead_start, lead_end + 1, 6))
                step = step_list

                scenario_key = f"D-{days_ago}_{forecast_time:02d}Z"
                forecast_scenarios.append(
                    {
                        "key": scenario_key,
                        "forecast_date": forecast_date,
                        "forecast_time": forecast_time,
                        "days_ago": days_ago,
                        "lead_start": lead_start,
                        "lead_end": lead_end,
                        "step": step,
                        "description": f"Forecast from {forecast_date} {forecast_time:02d}Z, lead {lead_start}-{lead_end}h",
                    }
                )

        results["forecast_data"]["scenarios"] = {}

        for scenario in forecast_scenarios:
            try:
                forecast_data = self._retrieve_forecast_data(
                    model_class=model_class,
                    forecast_type="probabilistic",
                    forecast_name="pf",
                    parameters=parameters,
                    date=scenario["forecast_date"].strftime("%Y-%m-%d"),
                    time=f"{scenario['forecast_time']:02d}:00:00",
                    steps=[scenario["step"]]
                    if isinstance(scenario["step"], str)
                    else scenario["step"],
                    area=resolved_area,
                    grid=grid,
                    calculate_windspeed=True,
                    calculate_6h_precipitation=False,
                )

                forecast_data["scenario_info"] = scenario
                results["forecast_data"]["scenarios"][scenario["key"]] = forecast_data

                print(f"Retrieved: {scenario['description']}")

            except Exception as e:
                print(f"Failed to retrieve: {scenario['description']} - {e}")
                continue

        results["metadata"]["scenarios_retrieved"] = len(
            results["forecast_data"]["scenarios"]
        )
        results["metadata"]["scenarios_total"] = len(forecast_scenarios)

        return results

    def _map_to_climate_params(self, parameters: list[str]) -> list[str]:
        """Map forecast parameters to their climate equivalents.

        Args:
            parameters: List of forecast parameter names (e.g., ['2t', 'tp'])

        Returns:
            List of climate parameter names (e.g., ['avg_2t', 'tp'])

        """
        climate_params = []

        for param in parameters:
            if param in self.surface_variables:
                climate_param = self.surface_variables[param].get("climate_param")
                if climate_param:
                    climate_params.append(climate_param)
                else:
                    print(f"No climate mapping found for {param}, skipping")
            else:
                print(f"Parameter {param} not found in surface_variables config")

        return climate_params

    def _get_climate_data_date(self, date_obj: datetime.date) -> datetime.date:
        """Get the closest available climate data date based on ECMWF availability patterns.

        Climate data availability patterns:
        - Before 2015: Only Thursdays
        - 2015-2024: Mondays and Thursdays
        - From 2025: Every 4 days starting from 1st of each month (1, 5, 9, 13, 17, 21, 25, 29)

        Args:
            date_obj: Analysis date

        Returns:
            Closest available climate data date before the analysis date

        """
        year = date_obj.year

        if year >= 2025:  # noqa: PLR2004
            return self._get_climate_date_2025_pattern(date_obj)

        elif year >= 2015:  # noqa: PLR2004
            return self._get_climate_date_monday_thursday_pattern(date_obj)

        else:
            return self._get_climate_date_thursday_only_pattern(date_obj)

    def _get_climate_date_2025_pattern(self, date_obj: datetime.date) -> datetime.date:
        """Get climate date for 2025+ pattern: every 4 days from 1st of month.

        ECMWF climate data from 2025 onwards is available on specific days of each month:
        1st, 5th, 9th, 13th, 17th, 21st, 25th, and 29th. This method finds the most
        recent available climate data date before the given analysis date.

        Args:
            date_obj: Target analysis date for which to find climate data

        Returns:
            Most recent climate data date available before date_obj, following the
            4-day pattern. If no suitable day exists in the current month, returns
            the latest available day from the previous month.

        """
        year = date_obj.year
        month = date_obj.month
        day = date_obj.day

        available_days = [1, 5, 9, 13, 17, 21, 25, 29]

        suitable_day = None
        for avail_day in reversed(available_days):
            if avail_day < day:
                suitable_day = avail_day
                break

        if suitable_day:
            return datetime.date(year, month, suitable_day)
        else:
            if month == 1:
                prev_year = year - 1
                prev_month = 12
            else:
                prev_year = year
                prev_month = month - 1

            last_day_of_prev_month = calendar.monthrange(prev_year, prev_month)[1]

            for avail_day in reversed(available_days):
                if avail_day <= last_day_of_prev_month:
                    return datetime.date(prev_year, prev_month, avail_day)

            return datetime.date(prev_year, prev_month, 1)

    def _get_climate_date_monday_thursday_pattern(
        self, date_obj: datetime.date
    ) -> datetime.date:
        """Get climate date for 2015-2024 pattern: Mondays and Thursdays.

        ECMWF climate data from 2015 to 2024 is available on Mondays (weekday 0)
        and Thursdays (weekday 3). This method searches backwards from the analysis
        date to find the most recent Monday or Thursday.

        Args:
            date_obj: Target analysis date for which to find climate data

        Returns:
            Most recent Monday or Thursday before date_obj

        """
        candidate_date = date_obj - datetime.timedelta(days=1)

        while True:
            if candidate_date.weekday() in [0, 3]:
                return candidate_date
            candidate_date = candidate_date - datetime.timedelta(days=1)

    def _get_climate_date_thursday_only_pattern(
        self, date_obj: datetime.date
    ) -> datetime.date:
        """Get climate date for pre-2015 pattern: Thursdays only.

        ECMWF climate data before 2015 is only available on Thursdays (weekday 3).
        This method searches backwards from the analysis date to find the most
        recent Thursday.

        Args:
            date_obj: Target analysis date for which to find climate data

        Returns:
            Most recent Thursday before date_obj

        """
        candidate_date = date_obj - datetime.timedelta(days=1)

        while True:
            if candidate_date.weekday() == 3:  # noqa: PLR2004
                return candidate_date
            candidate_date = candidate_date - datetime.timedelta(days=1)

    def _retrieve_forecast_data(  # noqa: D417, PLR0912, PLR0913, PLR0915
        self,
        model_class: str,
        forecast_type: str,
        forecast_name: str,
        parameters: list[str],
        date: str,
        time: str,
        steps: list[int] | list[str],
        area: list[float],
        grid: list[float] | None = None,
        levtype: str = "sfc",
        pressure_levels: list[int] | None = None,
        ensemble_members: list[int] | None = None,
        expect_any: bool = True,
        calculate_windspeed: bool = True,
        calculate_6h_precipitation: bool = True,
    ) -> dict[str, Any]:
        """Retrive forecast data.

        Args:
            model_class: 'ifs' or 'aifs'
            forecast_type: 'deterministic' or 'probabilistic'
            forecast_name: Specific forecast configuration name
            parameters: List of parameters to retrieve
            date: Forecast date string
            time: Forecast time string
            steps: List of forecast steps
            area: Geographic area
            grid: Grid resolution
            levtype: Level type ('sfc' or 'pl')
            pressure_levels: Pressure levels for upper-air data
            ensemble_members: Specific ensemble members to retrieve
            expect_any: If True, allow partial data retrieval

        Returns:
            Dictionary containing dataset and metadata

        """
        if model_class not in self.model_configs:
            raise ValueError(f"Model class '{model_class}' not found")

        model_config = self.model_configs[model_class]

        if forecast_type not in model_config:
            raise ValueError(
                f"Forecast type '{forecast_type}' not found for {model_class}"
            )

        forecast_config = model_config[forecast_type].get(forecast_name)
        if not forecast_config:
            raise ValueError(
                f"Forecast '{forecast_name}' not found in {model_class}/{forecast_type}"
            )

        surface_params = []
        pressure_params = []

        for param in parameters:
            if param in self.pressure_level_map:
                pressure_params.append(param)
            else:
                surface_params.append(param)

        results = {}

        if surface_params:
            surface_result = self._retrieve_single_level_data(
                model_config,
                forecast_config,
                surface_params,
                date,
                time,
                steps,
                area,
                grid,
                "sfc",
                None,
                ensemble_members,
                expect_any,
            )
            results.update(surface_result)

        if pressure_params:
            for param in pressure_params:
                levels = self.pressure_level_map[param]
                pressure_result = self._retrieve_single_level_data(
                    model_config,
                    forecast_config,
                    [param],
                    date,
                    time,
                    steps,
                    area,
                    grid,
                    "pl",
                    levels,
                    ensemble_members,
                    expect_any,
                )
                if "dataset" in results:
                    results["dataset"] = results["dataset"] + pressure_result["dataset"]
                else:
                    results.update(pressure_result)

        results["metadata"] = {
            "model_class": model_class,
            "forecast_type": forecast_type,
            "forecast_name": forecast_name,
            "parameters": parameters,
            "surface_params": surface_params,
            "pressure_params": pressure_params,
            "date": date,
            "time": time,
            "steps": steps,
            "area": area,
            "grid": grid,
            "levtype": "mixed"
            if (surface_params and pressure_params)
            else ("pl" if pressure_params else "sfc"),
            "pressure_levels": pressure_levels,
            "ensemble_members": ensemble_members,
        }

        if "dataset" in results and forecast_config["type"] != "cd":
            try:
                dataset_type = type(results["dataset"]).__name__
                if "Reader" in dataset_type or "Simple" in dataset_type:
                    field_list = list(results["dataset"])
                    results["dataset"] = FieldList.from_fields(field_list)
                if calculate_windspeed:
                    results["dataset"] = self._calculate_windspeed(results["dataset"])

                if calculate_6h_precipitation:
                    results["dataset"] = self._calculate_6h_precipitation(
                        results["dataset"]
                    )

                actual_params = []
                for field in results["dataset"]:
                    try:
                        param = field.metadata("shortName")
                        if param and param not in actual_params:
                            actual_params.append(param)
                    except Exception:
                        continue

                results["metadata"]["parameters"] = tuple(actual_params)
                surface_params_actual = []
                pressure_params_actual = []
                for param in actual_params:
                    if param in self.pressure_level_map:
                        pressure_params_actual.append(param)
                    else:
                        surface_params_actual.append(param)

                results["metadata"]["surface_params"] = surface_params_actual
                results["metadata"]["pressure_params"] = pressure_params_actual
                calc_params = []
                for field in results["dataset"]:
                    try:
                        param = field.metadata("shortName")
                        if param in ["ws"] or (
                            param in ["tp", "lsp", "cp"]
                            and field.metadata().get("stepType") == "accum"
                        ):
                            if param not in calc_params:
                                calc_params.append(param)
                    except Exception:
                        continue

                if calc_params:
                    results["metadata"]["calculated_parameters"] = calc_params

            except Exception:
                traceback.print_exc()

        return results

    def _retrieve_single_level_data(  # noqa: PLR0913
        self,
        model_config: dict,
        forecast_config: dict,
        parameters: list[str],
        date: str,
        time: str,
        steps: list[int] | list[str],
        area: list[float],
        grid: list[float] | None = None,
        levtype: str = "sfc",
        pressure_levels: list[int] | None = None,
        ensemble_members: list[int] | None = None,
        expect_any: bool = True,
    ) -> dict[str, Any]:
        """Retrieve data for a single level type from ECMWF MARS archive.

        Args:
            model_config: Model-level configuration dictionary containing 'class' and 'expver'
            forecast_config: Forecast-specific configuration containing 'type', 'stream',
                and optional 'expver', 'quantiles', or 'number_range'
            parameters: List of parameter short names to retrieve (e.g., ['2t', 'tp', '10u'])
            date: Forecast initialization date in format 'YYYY-MM-DD'
            time: Forecast initialization time in format 'HH:MM:SS'
            steps: List of forecast lead times (hours or step strings like '24-48')
            area: Geographic bounding box as [north, west, south, east] in degrees
            grid: Optional grid resolution as [dx, dy] in degrees. Defaults to None (native grid).
            levtype: Level type - 'sfc' for surface or 'pl' for pressure levels. Defaults to 'sfc'.
            pressure_levels: List of pressure levels in hPa (e.g., [1000, 850, 500]).
                Required when levtype='pl'. Defaults to None.
            ensemble_members: Specific ensemble member numbers to retrieve (e.g., [1, 2, 3]).
                Only applies to probabilistic forecasts (type='pf'). Defaults to None.
            expect_any: If True, allows partial data retrieval when some requested fields
                are unavailable. Defaults to True.

        Returns:
            Dictionary containing:
                - 'dataset': Earthkit FieldList with the retrieved GRIB data
                - 'request_params': Complete MARS request parameters used for retrieval

        """
        request_params = {
            "class": model_config["class"],
            "expver": forecast_config.get("expver", model_config["expver"]),
            "type": forecast_config["type"],
            "stream": forecast_config["stream"],
            "levtype": levtype,
            "date": date,
            "time": time,
            "step": steps,
        }

        if forecast_config["type"] == "cd":
            climate_params = self._convert_climate_params_to_ids(parameters)
            request_params["param"] = climate_params

            quantiles = forecast_config.get(
                "quantiles",
                [
                    0,
                    1,
                    2,
                    5,
                    10,
                    20,
                    25,
                    30,
                    40,
                    50,
                    60,
                    70,
                    75,
                    80,
                    90,
                    95,
                    98,
                    99,
                    100,
                ],
            )
            request_params["quantile"] = [f"{q}:100" for q in quantiles]
        else:
            param_ids = self._convert_params_to_ids(parameters)
            request_params["param"] = param_ids
            request_params["area"] = area

            if pressure_levels and levtype == "pl":
                request_params["levelist"] = pressure_levels

            if grid is not None:
                request_params["grid"] = grid

            if forecast_config["type"] == "pf" and ensemble_members:
                request_params["number"] = ensemble_members
            elif forecast_config["type"] == "pf" and "number_range" in forecast_config:
                request_params["number"] = forecast_config["number_range"]

        if expect_any:
            request_params["expect"] = "any"

        try:
            ds = ek.data.from_source("mars", **request_params)

            return {"dataset": ds, "request_params": request_params}

        except Exception as e:
            print(f"Error retrieving data: {str(e)}")
            print(f"Request parameters: {request_params}")
            raise

    def read_local_grib_data(
        self,
        file_mapping: dict[str, str],
        model_class: str = "ifs",
        extract_metadata: bool = True,
    ) -> dict[str, Any]:
        """Read local GRIB files and return data in the same format as retrieval functions.

        Args:
            file_mapping: Dictionary mapping data types to file paths
                Examples:
                - Stamps: {"fc": "path/to/fc.grib", "control": "path/to/cf.grib", "ensemble": "path/to/pf.grib"}
                - Meteograms: {"control": "path/to/cf.grib", "ensemble": "path/to/pf.grib"}
                - Plumes: {"control": "path/to/cf.grib", "ensemble": "path/to/pf.grib", "ensemble_mean": "path/to/em.grib"}
                - CDF: {"climate_data": "path/to/cd.grib", "forecast_data": {"scenarios": {"D-0_00Z": "path/to/pf1.grib"}, "scenario_metadata": {...}}}
            model_class: Model class for metadata ('ifs' or 'aifs'). Defaults to 'ifs'.
            extract_metadata: Whether to extract metadata from GRIB files. Defaults to True.

        Returns:
            Dictionary with same structure as retrieval functions, containing:
                - Data type keys mapping to datasets and metadata
                - 'bbox_info': Bounding box parameters (if bbox_manager exists)
                - 'metadata': Overall metadata including source, model_class, data_types, and total_datasets

        """
        results = {}

        for data_type, file_info in file_mapping.items():
            try:
                results[data_type] = self._process_file_info(
                    file_info, data_type, model_class, extract_metadata
                )
            except Exception as e:
                print(f"✗ Error reading {data_type}: {e}")
                continue

        if hasattr(self, "bbox_manager") and self.bbox_manager:
            results["bbox_info"] = self.bbox_manager.get_current_bbox_params()

        results["metadata"] = {
            "source": "local_files",
            "model_class": model_class,
            "data_types": list(results.keys()),
            "total_datasets": len(
                [k for k in results.keys() if k not in ["bbox_info", "metadata"]]
            ),
        }

        return results

    def _process_file_info(self, file_info, context_key, model_class, extract_metadata):
        """Process a file_info entry (string, dict, or list).

        Args:
            file_info: File information - can be a file path string, dictionary of files, or list of file paths
            context_key: Context identifier for the data type being processed
            model_class: Model class for metadata extraction ('ifs' or 'aifs')
            extract_metadata: Whether to extract metadata from GRIB files

        Returns:
            Processed data structure containing datasets and metadata, or None if processing fails

        """
        if isinstance(file_info, str):
            return self._load_single_file(
                file_info, context_key, model_class, extract_metadata
            )

        elif isinstance(file_info, dict):
            return self._process_dict_files(file_info, model_class, extract_metadata)

        elif isinstance(file_info, list):
            return self._load_combined_files(
                file_info, context_key, model_class, extract_metadata
            )

    def _load_single_file(self, file_path, data_type, model_class, extract_metadata):
        """Load and process a single GRIB file.

        Args:
            file_path: Path to the GRIB file
            data_type: Type identifier for the data being loaded
            model_class: Model class for metadata extraction ('ifs' or 'aifs')
            extract_metadata: Whether to extract metadata from the GRIB file

        Returns:
            Dictionary containing:
                - 'dataset': Processed dataset from the GRIB file
                - 'metadata': Extracted metadata (empty dict if extract_metadata is False)
            Returns None if file doesn't exist.

        """
        if not Path(file_path).exists():
            print(f"Warning: {data_type} file not found: {file_path}")
            return None

        ds = ek.data.from_source("file", file_path)
        ds = self._process_local_grib_calculations(ds, data_type=data_type)

        metadata = {}
        if extract_metadata:
            metadata = self._extract_grib_metadata(ds, data_type, model_class)

        return {"dataset": ds, "metadata": metadata}

    def _process_dict_files(self, file_info, model_class, extract_metadata):
        """Process nested dictionary of files.

        Args:
            file_info: Dictionary containing file paths and/or nested dictionaries
                May include special 'scenario_metadata' key with metadata for scenarios
            model_class: Model class for metadata extraction ('ifs' or 'aifs')
            extract_metadata: Whether to extract metadata from GRIB files

        Returns:
            Dictionary with same structure as input, with file paths replaced by
            loaded datasets and metadata. Preserves 'scenario_metadata' if present.

        """
        nested_results = {}

        for sub_key, sub_info in file_info.items():
            if sub_key == "scenario_metadata":
                nested_results["scenario_metadata"] = sub_info
                continue

            if isinstance(sub_info, dict):
                nested_results[sub_key] = self._process_scenarios(
                    sub_info,
                    file_info.get("scenario_metadata", {}),
                    model_class,
                    extract_metadata,
                )
            else:
                result = self._load_single_file(
                    sub_info, sub_key, model_class, extract_metadata
                )
                if result:
                    nested_results[sub_key] = result

        return nested_results

    def _process_scenarios(
        self, scenarios, scenario_metadata, model_class, extract_metadata
    ):
        """Process scenario files with optional metadata enrichment.

        Args:
            scenarios: Dictionary mapping scenario keys to file paths
            scenario_metadata: Dictionary containing additional metadata for each scenario
                Each entry should include: days_back, forecast_time, original_name, description
            model_class: Model class for metadata extraction ('ifs' or 'aifs')
            extract_metadata: Whether to extract metadata from GRIB files

        Returns:
            Dictionary mapping scenario keys to dictionaries containing:
                - 'dataset': Processed dataset
                - 'metadata': Extracted metadata enriched with scenario-specific information
                    (scenario_key, days_back, forecast_time, original_name, scenario_description)

        """
        results = {}

        for scenario_key, file_path in scenarios.items():
            result = self._load_single_file(
                file_path, scenario_key, model_class, extract_metadata
            )

            if result and scenario_key in scenario_metadata:
                scenario_meta = scenario_metadata[scenario_key]
                result["metadata"].update(
                    {
                        "scenario_key": scenario_key,
                        "days_back": scenario_meta["days_back"],
                        "forecast_time": scenario_meta["forecast_time"],
                        "original_name": scenario_meta["original_name"],
                        "scenario_description": scenario_meta["description"],
                    }
                )
                print(f"  └── {scenario_meta['description']}")
            elif result:
                result["metadata"]["scenario_key"] = scenario_key

            if result:
                results[scenario_key] = result

        return results

    def _load_combined_files(
        self, file_paths, data_type, model_class, extract_metadata
    ):
        """Load and combine multiple GRIB files.

        Args:
            file_paths: List of paths to GRIB files to be combined
            data_type: Type identifier for the data being loaded
            model_class: Model class for metadata extraction ('ifs' or 'aifs')
            extract_metadata: Whether to extract metadata from the combined dataset

        Returns:
            Dictionary containing:
                - 'dataset': Combined dataset from all valid files (uses + operator)
                - 'metadata': Extracted metadata from the combined dataset
            Returns None if no valid files were found.

        """
        combined_ds = None

        for file_path in file_paths:
            if not Path(file_path).exists():
                print(f"Warning: {data_type} file not found: {file_path}")
                continue

            ds = ek.data.from_source("file", file_path)
            ds = self._process_local_grib_calculations(ds, data_type=data_type)

            combined_ds = ds if combined_ds is None else combined_ds + ds

        if combined_ds is None:
            return None

        metadata = {}
        if extract_metadata:
            metadata = self._extract_grib_metadata(combined_ds, data_type, model_class)

        return {"dataset": combined_ds, "metadata": metadata}

    def _extract_grib_metadata(  # noqa: PLR0912, PLR0915
        self, dataset, data_type: str, model_class: str
    ) -> dict[str, Any]:
        """Extract metadata from GRIB dataset to match retrieval function format.

        Args:
            dataset: Earthkit dataset
            data_type: Type of data (e.g., "fc", "control", "ensemble", "climate_data", etc.)
            model_class: Model class

        Returns:
            Metadata dictionary similar to retrieval functions

        """
        if len(dataset) == 0:
            return {"source": "local_file", "total_fields": 0}

        try:
            first_field = dataset[0]

            try:
                date_info = first_field.metadata("date")
                date_str = str(date_info) if date_info else "unknown"
            except:  # noqa: E722
                date_str = "unknown"

            try:
                time_info = first_field.metadata("time")
                time_str = f"{time_info:04d}" if time_info else "0000"
                time_str = f"{time_str[:2]}:{time_str[2:]}:00"
            except:  # noqa: E722
                time_str = "00:00:00"

            parameters = []
            for field in dataset:
                try:
                    param = field.metadata("shortName", default="unknown")
                    if param not in parameters:
                        parameters.append(param)
                except:  # noqa: E722
                    continue

            steps = []
            for field in dataset:
                try:
                    step = field.metadata("step", default=0)
                    if step not in steps:
                        steps.append(step)
                except:  # noqa: E722
                    continue
            steps.sort()

            try:
                lat_first = first_field.metadata(
                    "latitudeOfFirstGridPointInDegrees", default=90
                )
                lon_first = first_field.metadata(
                    "longitudeOfFirstGridPointInDegrees", default=-180
                )
                lat_last = first_field.metadata(
                    "latitudeOfLastGridPointInDegrees", default=-90
                )
                lon_last = first_field.metadata(
                    "longitudeOfLastGridPointInDegrees", default=180
                )

                area = [
                    max(lat_first, lat_last),  # north
                    min(lon_first, lon_last),  # west
                    min(lat_first, lat_last),  # south
                    max(lon_first, lon_last),  # east
                ]
            except:  # noqa: E722
                area = [90, -180, -90, 180]  # Global default

            surface_params = []
            pressure_params = []

            for param in parameters:
                if (
                    hasattr(self, "pressure_level_map")
                    and param in self.pressure_level_map
                ):
                    pressure_params.append(param)
                else:
                    surface_params.append(param)

            forecast_type_mapping = {
                "fc": {"forecast_type": "deterministic", "forecast_name": "fc"},
                "cf": {
                    "forecast_type": "probabilistic",
                    "forecast_name": "cf",
                },
                "pf": {
                    "forecast_type": "probabilistic",
                    "forecast_name": "pf",
                },
                "cd": {
                    "forecast_type": "probabilistic",
                    "forecast_name": "cd",
                },
            }

            if data_type.startswith("D-"):
                forecast_info = {
                    "forecast_type": "probabilistic",
                    "forecast_name": "pf",
                }
            else:
                forecast_info = forecast_type_mapping.get(
                    data_type, {"forecast_type": "unknown", "forecast_name": data_type}
                )

            metadata = {
                "model_class": model_class,
                "forecast_type": forecast_info["forecast_type"],
                "forecast_name": forecast_info["forecast_name"],
                "parameters": parameters,
                "surface_params": surface_params,
                "pressure_params": pressure_params,
                "date": date_str,
                "time": time_str,
                "steps": steps,
                "area": area,
                "grid": None,
                "levtype": "mixed"
                if (surface_params and pressure_params)
                else ("pl" if pressure_params else "sfc"),
                "pressure_levels": None,
                "ensemble_members": None,
                "source": "local_file",
                "data_type": data_type,
                "total_fields": len(dataset),
            }

            return metadata

        except Exception as e:
            print(f"Warning: Could not extract full metadata for {data_type}: {e}")
            return {
                "model_class": model_class,
                "forecast_type": "unknown",
                "forecast_name": data_type,
                "source": "local_file",
                "total_fields": len(dataset),
                "data_type": data_type,
            }

    def _calculate_windspeed(self, ds):
        """Calculate windspeed from 10u and 10v components and add to dataset.

        Args:
            ds: Dataset containing wind component fields (10u/165.128 and 10v/166.128)

        Returns:
            Dataset with windspeed fields added. Returns original dataset unchanged
            if wind components are missing or calculation fails.

        """
        try:
            u_fields = ds.sel(param=["10u", "165.128"])
            v_fields = ds.sel(param=["10v", "166.128"])

            if len(u_fields) == 0 or len(v_fields) == 0:
                return ds

            v_map = {}
            for v_field in v_fields:
                step = v_field.metadata("step")
                number = v_field.metadata().get("number", 0)
                level = v_field.metadata().get("level", 0)
                key = (step, number, level)
                v_map[key] = v_field

            all_ws_fields = []
            for u_field in u_fields:
                step = u_field.metadata("step")
                number = u_field.metadata().get("number", 0)
                level = u_field.metadata().get("level", 0)
                key = (step, number, level)

                if key in v_map:
                    v_field = v_map[key]
                    ws_values = np.sqrt(u_field.values**2 + v_field.values**2)

                    try:
                        ws_metadata = u_field.metadata().override(shortName="ws")
                    except:  # noqa: E722
                        ws_metadata = u_field.metadata()

                    ws_field = FieldList.from_array(ws_values, ws_metadata)
                    all_ws_fields.append(ws_field)

            if not all_ws_fields:
                return ds

            combined_ds = ds

            for ws_field in all_ws_fields:
                combined_ds = combined_ds + ws_field

            if type(combined_ds).__name__ == "MultiFieldList":
                try:
                    combined_ds = FieldList.from_fields(list(combined_ds))
                except Exception as e:
                    print(f"Could not convert to FieldList: {e}")

            return combined_ds

        except Exception:
            traceback.print_exc()
            return ds

    def _calculate_6h_precipitation(self, ds):  # noqa: PLR0912
        """Calculate 6-hour accumulated precipitation and replace cumulative precipitation.

        Args:
            ds: Dataset containing precipitation fields and other meteorological data

        Returns:
            Dataset with 6-hour precipitation fields replacing cumulative precipitation.
            Returns original dataset unchanged if precipitation fields are missing or
            calculation fails.

        """
        existing_params = []
        for field in ds:
            try:
                param = field.metadata("shortName")
                if param and param not in existing_params:
                    existing_params.append(param)
            except:  # noqa: E722
                continue

        try:
            precip_params = ["tp", "lsp", "cp"]
            precip_fields = ds.sel(param=precip_params)

            if len(precip_fields) == 0:
                return ds

            non_precip_fields = []
            for field in ds:
                try:
                    param = field.metadata("shortName")
                    if param not in precip_params:
                        non_precip_fields.append(field)
                except:  # noqa: E722
                    non_precip_fields.append(field)

            all_6h_fields = []

            for param in precip_params:
                try:
                    param_fields = ds.sel(param=[param])

                    if len(param_fields) > 0:
                        result_6h = self._calculate_6h_precipitation_grib(
                            param_fields, interval_hours=6, param_name=param
                        )

                        if result_6h:
                            all_6h_fields.extend(result_6h)

                except Exception:
                    traceback.print_exc()

                    try:
                        param_fields = ds.sel(param=[param])
                        for field in param_fields:
                            all_6h_fields.append(field)
                    except:  # noqa: E722
                        continue

            if all_6h_fields:
                all_fields = []
                all_fields.extend(non_precip_fields)
                for field in all_6h_fields:
                    if isinstance(field, FieldList):
                        all_fields.extend(list(field))
                    else:
                        all_fields.append(field)

                combined_ds = FieldList.from_fields(all_fields)

                return combined_ds
            else:
                return ds

        except Exception:
            traceback.print_exc()
            return ds

    def _calculate_6h_precipitation_grib(self, ds, interval_hours=6, param_name="tp"):  # noqa: PLR0912, PLR0915
        """Calculate 6-hour precipitation from cumulative precipitation and replace original fields.

        Args:
            ds: Dataset containing cumulative precipitation fields
            interval_hours: Time interval in hours for accumulation period. Defaults to 6.
            param_name: Parameter name for the precipitation field ('tp', 'lsp', or 'cp').
                Defaults to 'tp'.

        Returns:
            List of FieldList objects containing 6-hour accumulated precipitation fields
            for all ensemble members and time steps. Returns empty list if input dataset
            is empty or calculation fails.

        """
        if len(ds) == 0:
            return []

        ensemble_step_fields = {}
        for field in ds:
            step_val = field.metadata().get("step", 0)
            number = field.metadata().get("number", 0)

            if isinstance(step_val, int | float):
                hour_val = int(step_val)
            else:
                hour_val = int(str(step_val))

            if number not in ensemble_step_fields:
                ensemble_step_fields[number] = {}
            ensemble_step_fields[number][hour_val] = field

        ensemble_members = sorted(ensemble_step_fields.keys())
        steps_hours = sorted(
            set().union(
                *[
                    member_fields.keys()
                    for member_fields in ensemble_step_fields.values()
                ]
            )
        )

        all_6h_fields = []

        for member in ensemble_members:
            member_fields = ensemble_step_fields[member]
            start_hour = 0

            while start_hour + interval_hours <= max(steps_hours):
                end_hour = start_hour + interval_hours

                start_step = self._find_closest_step(
                    start_hour, list(member_fields.keys())
                )
                end_step = self._find_closest_step(end_hour, list(member_fields.keys()))

                if start_step is not None and end_step is not None:
                    if start_step in member_fields and end_step in member_fields:
                        tp_start = member_fields[start_step]
                        tp_end = member_fields[end_step]

                        precip_6h = tp_end.values - tp_start.values

                        try:
                            md = tp_end.metadata().override(
                                shortName=param_name,
                                step=end_hour,
                                stepType="accum",
                                stepRange=f"{start_hour}-{end_hour}",
                            )

                        except Exception:
                            try:
                                md = tp_end.metadata().override(
                                    shortName=param_name, step=end_hour
                                )

                            except Exception:
                                try:
                                    md = tp_end.metadata().override(step=end_hour)
                                except:  # noqa: E722
                                    md = tp_end.metadata()

                        try:
                            precip_6h_field = FieldList.from_array(precip_6h, md)
                            all_6h_fields.append(precip_6h_field)
                        except Exception:
                            try:
                                precip_6h_field = FieldList.from_array(precip_6h, md)
                                all_6h_fields.append(precip_6h_field)
                            except Exception:
                                continue

                start_hour = end_hour

        if all_6h_fields:
            try:
                first_field = all_6h_fields[0]
                if hasattr(first_field, "__len__") and len(first_field) > 0:
                    (
                        first_field[0]
                        if hasattr(first_field, "__getitem__")
                        else first_field
                    )
                else:
                    pass

            except Exception as debug_error:
                print(f"Could not read sample metadata: {debug_error}")

        return all_6h_fields

    def _find_closest_step(self, target_hour, available_steps, tolerance=3):
        """Find the closest available step to target hour.

        Args:
            target_hour: Target hour to find in available steps
            available_steps: List of available time steps (in hours)
            tolerance: Maximum allowed difference in hours from target. Defaults to 3.

        Returns:
            Closest available step (int) within tolerance, or None if no suitable
            step is found.

        """
        if target_hour in available_steps:
            return target_hour

        closest_steps = [
            step for step in available_steps if abs(step - target_hour) <= tolerance
        ]

        if closest_steps:
            return min(closest_steps, key=lambda x: abs(x - target_hour))

        return None

    def _process_local_grib_calculations(self, ds, data_type=None):
        """Process local GRIB data to add calculated fields (windspeed and 6h precipitation).

        Args:
            ds: Dataset to process
            data_type: Type of data (e.g., 'cd', 'pf', 'fc', etc.). Defaults to None.
                'cd' (climate data) skips all calculations.

        Returns:
            Processed dataset with calculated windspeed and 6-hour precipitation fields
            added. Returns original dataset unchanged if processing fails or for climate
            data type.

        """
        try:
            if data_type == "cd":
                print(f"Skipping calculations for climate data type: {data_type}")
                return ds

            ds = self._calculate_windspeed(ds)
            ds = self._calculate_6h_precipitation(ds)
            return ds

        except Exception as e:
            print(f"Error processing local GRIB calculations: {e}")
            return ds
