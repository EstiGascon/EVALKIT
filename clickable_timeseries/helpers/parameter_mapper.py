import json
from datetime import date as date_type
from pathlib import Path


class ConfigurationManager:
    """Centralized configuration management for models, parameters, and step patterns."""

    def __init__(self, config_path: str = None):
        """Initialize configuration manager and load configuration from a JSON file.

        Args:
            config_path: Path to the JSON configuration file (default: 'config.json' in current directory)

        """
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"

        with open(config_path) as f:
            self.config = json.load(f)

        self.parameters = self.config.get("parameters", {})
        self.models = self.config.get("models", {})
        self.step_patterns = self.config.get("step_patterns", {})
        self.ui_settings = self.config.get("ui_settings", {})

    def get_param_id(self, short_name: str) -> int | None:
        """Get parameter ID corresponding to a short name.

        Args:
            short_name: Short name of the parameter

        Returns:
            Integer ID of the parameter, or None if not found

        """
        return self.parameters.get(short_name, {}).get("param_id")

    def get_param_ids(self, short_names: list[str]) -> list[int]:
        """Get a list of parameter IDs corresponding to multiple short names.

        Args:
            short_names: List of parameter short names

        Returns:
            List of integer IDs of the parameters (excluding missing)

        """
        return [
            self.get_param_id(name)
            for name in short_names
            if self.get_param_id(name) is not None
        ]

    def get_param_info(self, short_name: str) -> dict | None:
        """Get full information dictionary for a parameter.

        Args:
            short_name: Short name of the parameter

        Returns:
            Dictionary containing parameter information, or None if not found

        """
        return self.parameters.get(short_name, None)

    def get_expected_units(self, short_name: str) -> str | None:
        """Get expected units for a given parameter.

        Args:
            short_name: Short name of the parameter

        Returns:
            String representing the expected units of the parameter, or None if not found

        """
        info = self.get_param_info(short_name)
        return info.get("units") if info else None

    def get_parameters_for_ui(self) -> list[tuple[str, str]]:
        """Get sorted list of parameters for UI display.

        Returns:
            List of tuples (display_name, short_name) sorted by UI order

        """
        params = []
        for short_name, info in self.parameters.items():
            display_name = info.get("display_name", info.get("name", short_name))
            ui_order = info.get("ui_order", 999)
            params.append((ui_order, display_name, short_name))

        params.sort(key=lambda x: (x[0], x[1]))
        return [(display, short) for _, display, short in params]

    def get_parameters_by_model(self, model: str) -> list[str]:
        """Get parameters that are available for a specific model.

        Args:
            model: Model name

        Returns:
            List of parameter short names available for the model

        """
        available = []
        for short_name, info in self.parameters.items():
            if model in info.get("available_models", []):
                available.append(short_name)
        return available

    def get_model_info(self, model: str) -> dict | None:
        """Get full configuration dictionary for a model.

        Args:
            model: Model name

        Returns:
            Dictionary containing model information, or None if not found

        """
        return self.models.get(model, None)

    def get_models_for_ui(self) -> list[tuple[str, str]]:
        """Get sorted list of models for UI display.

        Returns:
            List of tuples (display_name, model_key) sorted by UI order

        """
        models = []
        for model_key, info in self.models.items():
            display_name = info.get("display_name", model_key)
            ui_order = info.get("ui_order", 999)
            models.append((ui_order, display_name, model_key))

        models.sort(key=lambda x: x[0])
        return [(display, key) for _, display, key in models]

    def get_model_class(self, model: str) -> str:
        """Get MARS class associated with a model.

        Args:
            model: Model name

        Returns:
            String representing the MARS class (default: 'od')

        """
        return (
            self.get_model_info(model).get("class", "od")
            if self.get_model_info(model)
            else "od"
        )

    def get_model_stream(self, model: str) -> str:
        """Get MARS stream associated with a model.

        Args:
            model: Model name

        Returns:
            String representing the MARS stream (default: 'oper')

        """
        return (
            self.get_model_info(model).get("stream", "oper")
            if self.get_model_info(model)
            else "oper"
        )

    def supports_custom_step_expansion(self, model: str) -> bool:
        """Check if a model supports custom step expansion.

        Args:
            model: Model name

        Returns:
            Boolean indicating support for custom step expansion

        """
        return (
            self.get_model_info(model).get("supports_custom_step_expansion", False)
            if self.get_model_info(model)
            else False
        )

    def get_step_pattern(self, model: str) -> str:
        """Get step pattern name for a model.

        Args:
            model: Model name

        Returns:
            Step pattern name (default: 'ifs_variable')

        """
        return (
            self.get_model_info(model).get("step_pattern", "ifs_variable")
            if self.get_model_info(model)
            else "ifs_variable"
        )

    def generate_steps(
        self,
        start_step: int,
        end_step: int,
        model: str,
        forecast_date: date_type = None,
    ) -> list[int]:
        """Generate forecast steps based on model and forecast date.

        Args:
            start_step: First forecast step (inclusive)
            end_step: Last forecast step (inclusive)
            model: Model name
            forecast_date: Optional date for date-based patterns

        Returns:
            List of forecast steps in hours, empty list if pattern not found

        """
        pattern_name = self.get_step_pattern(model)
        pattern = self.step_patterns.get(pattern_name)
        if not pattern:
            return []

        pattern_type = pattern.get("type")
        if pattern_type == "fixed_interval":
            return self._generate_fixed_interval_steps(start_step, end_step, pattern)
        elif pattern_type == "date_based_intervals":
            return self._generate_date_based_steps(
                start_step, end_step, pattern, forecast_date
            )
        else:
            return []

    def _generate_fixed_interval_steps(
        self, start_step: int, end_step: int, pattern: dict
    ) -> list[int]:
        """Generate steps with fixed interval (e.g., 6-hourly).

        Args:
            start_step: First step (inclusive)
            end_step: Last step (inclusive)
            pattern: Step pattern dictionary containing 'interval'

        Returns:
            List of forecast steps in hours

        """
        interval = pattern.get("interval", 1)

        if start_step % interval == 0:
            adjusted_start = start_step
        else:
            lower = (start_step // interval) * interval
            upper = lower + interval
            adjusted_start = (
                lower if abs(start_step - lower) <= abs(start_step - upper) else upper
            )

        if end_step % interval == 0:
            adjusted_end = end_step
        else:
            lower = (end_step // interval) * interval
            upper = lower + interval
            adjusted_end = (
                lower if abs(end_step - lower) <= abs(end_step - upper) else upper
            )

        return list(range(adjusted_start, adjusted_end + 1, interval))

    def _generate_date_based_steps(
        self,
        start_step: int,
        end_step: int,
        pattern: dict,
        forecast_date: date_type = None,
    ) -> list[int]:
        """Generate steps using date-based variable intervals.

        Args:
            start_step: First step (inclusive)
            end_step: Last step (inclusive)
            pattern: Step pattern dictionary with default intervals and date rules
            forecast_date: Optional forecast date to apply date rules

        Returns:
            List of forecast steps in hours

        """
        intervals = pattern.get("default_intervals", [[0, 240, 1]])

        if forecast_date and "date_rules" in pattern:
            for rule in pattern["date_rules"]:
                matches = True
                if "before" in rule and forecast_date >= date_type.fromisoformat(
                    rule["before"]
                ):
                    matches = False
                if "after" in rule and forecast_date <= date_type.fromisoformat(
                    rule["after"]
                ):
                    matches = False
                if matches:
                    intervals = rule.get("intervals", intervals)
                    break

        step_list = []
        for interval_start, interval_end, step_interval in intervals:
            current_start = max(interval_start, start_step)
            current_end = min(interval_end, end_step)
            if current_start <= current_end:
                step_list.extend(range(current_start, current_end + 1, step_interval))

        return sorted(set(step_list))

    def get_default_model(self) -> str:
        """Get default model defined in UI settings.

        Returns:
            String representing the default model (default: 'ifs-single')

        """
        return self.ui_settings.get("default_model", "ifs-single")

    def get_default_parameters(self) -> list[str]:
        """Get default parameters defined in UI settings.

        Returns:
            List of default parameter short names (default: ['2t'])

        """
        return self.ui_settings.get("default_parameters", ["2t"])

    def get_default_bbox(self) -> dict:
        """Get default bounding box defined in UI settings.

        Returns:
            Dictionary with keys 'north', 'west', 'south', 'east' defining bounding box

        """
        return self.ui_settings.get(
            "default_bbox", {"north": 72.0, "west": -25.0, "south": 34.0, "east": 45.0}
        )

    def get_available_times(self) -> list[str]:
        """Get available forecast times defined in UI settings.

        Returns:
            List of time strings (default: ['00:00:00'])

        """
        return self.ui_settings.get("available_times", ["00:00:00"])
