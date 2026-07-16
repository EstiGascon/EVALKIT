import json
from datetime import date as date_type
from pathlib import Path


class ConfigurationManager:
    """Centralized configuration management for models, parameters, and step patterns."""

    def __init__(self, config_path: str = None):
        """Initialize the configuration manager.

        Args:
            config_path: Path to the JSON configuration file

        """
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"

        with open(config_path) as f:
            self.config = json.load(f)

        self.parameters = self.config["parameters"]
        self.models = self.config["models"]
        self.step_patterns = self.config["step_patterns"]
        self.ui_settings = self.config.get("ui_settings", {})

    def get_param_id(self, short_name: str) -> int:
        """Get parameter ID from short name."""
        if short_name in self.parameters:
            return self.parameters[short_name]["param_id"]
        raise ValueError(f"Parameter '{short_name}' not found in configuration")

    def get_param_ids(self, short_names: list[str]) -> list[int]:
        """Get list of parameter IDs from list of short names."""
        return [self.get_param_id(name) for name in short_names]

    def get_param_info(self, short_name: str) -> dict:
        """Get full parameter information."""
        if short_name in self.parameters:
            return self.parameters[short_name].copy()
        raise ValueError(f"Parameter '{short_name}' not found in configuration")

    def get_expected_units(self, short_name: str) -> str:
        """Get expected units for a parameter."""
        return self.get_param_info(short_name)["units"]

    def get_parameters_for_ui(self) -> list[tuple[str, str]]:
        """Get sorted list of parameters for UI display.

        Returns:
            List of (display_name, short_name) tuples sorted by ui_order

        """
        params = []
        for short_name, info in self.parameters.items():
            display_name = info.get("display_name", info["name"])
            ui_order = info.get("ui_order", 999)
            params.append((ui_order, display_name, short_name))

        params.sort(key=lambda x: (x[0], x[1]))

        return [(display, short) for _, display, short in params]

    def get_parameters_by_model(self, model: str) -> list[str]:
        """Get list of parameters available for a specific model."""
        available = []
        for short_name, info in self.parameters.items():
            if model in info.get("available_models", []):
                available.append(short_name)
        return available

    def get_model_info(self, model: str) -> dict:
        """Get full model configuration."""
        if model in self.models:
            return self.models[model].copy()
        raise ValueError(f"Model '{model}' not found in configuration")

    def get_models_for_ui(self) -> list[tuple[str, str]]:
        """Get sorted list of models for UI display.

        Returns:
            List of (display_name, model_key) tuples sorted by ui_order

        """
        models = []
        for model_key, info in self.models.items():
            display_name = info.get("display_name", model_key)
            ui_order = info.get("ui_order", 999)
            models.append((ui_order, display_name, model_key))

        models.sort(key=lambda x: x[0])

        return [(display, key) for _, display, key in models]

    def get_model_class(self, model: str) -> str:
        """Get MARS class for a model."""
        return self.get_model_info(model).get("class", "od")

    def get_model_stream(self, model: str) -> str:
        """Get MARS stream for a model."""
        return self.get_model_info(model).get("stream", "oper")

    def supports_custom_step_expansion(self, model: str) -> bool:
        """Check if model supports custom step expansion."""
        return self.get_model_info(model).get("supports_custom_step_expansion", False)

    def get_step_pattern(self, model: str) -> str:
        """Get step pattern name for a model."""
        return self.get_model_info(model).get("step_pattern", "ifs_variable")

    def generate_steps(
        self,
        start_step: int,
        end_step: int,
        model: str,
        forecast_date: date_type = None,
    ) -> list[int]:
        """Generate forecast steps based on model and date.

        Args:
            start_step: First step (inclusive)
            end_step: Last step (inclusive)
            model: Model name
            forecast_date: Forecast date for date-based patterns

        Returns:
            List of forecast steps in hours

        """
        pattern_name = self.get_step_pattern(model)
        pattern = self.step_patterns.get(pattern_name)

        if not pattern:
            raise ValueError(f"Step pattern '{pattern_name}' not found")

        pattern_type = pattern.get("type")

        if pattern_type == "fixed_interval":
            return self._generate_fixed_interval_steps(start_step, end_step, pattern)
        elif pattern_type == "date_based_intervals":
            return self._generate_date_based_steps(
                start_step, end_step, pattern, forecast_date
            )
        else:
            raise ValueError(f"Unknown step pattern type: {pattern_type}")

    def get_step_requirement(self, short_name: str) -> dict | None:
        """Get step requirement for a parameter if it exists.

        Args:
            short_name: Parameter short name

        Returns:
            Step requirement dict or None if no requirement exists

        """
        try:
            param_info = self.get_param_info(short_name)
            return param_info.get("step_requirement")
        except ValueError:
            return None

    def check_param_step_compatibility(self, short_name: str, steps: list[int]) -> bool:
        """Check if a parameter is compatible with requested steps.

        Args:
            short_name: Parameter short name
            steps: List of forecast steps

        Returns:
            True if compatible, False otherwise

        """
        requirement = self.get_step_requirement(short_name)

        if requirement is None:
            return True

        req_type = requirement.get("type")

        if req_type == "multiple_of":
            value = requirement.get("value")
            return all(step % value == 0 for step in steps)

        return True

    def _generate_fixed_interval_steps(
        self, start_step: int, end_step: int, pattern: dict
    ) -> list[int]:
        """Generate steps with fixed interval (e.g., 6-hourly)."""
        interval = pattern["interval"]

        # Respect max_step defined in the pattern (e.g. ifs4km-single caps at 120 h).
        # Without this cap, a date range > 5 days would request steps beyond 120
        # for ifs4km-single, causing the MARS retrieval to fail.
        max_step = pattern.get("max_step")
        if max_step is not None:
            end_step = min(end_step, max_step)

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
        """Generate steps with date-based variable intervals."""
        intervals = pattern.get("default_intervals", [[0, 240, 1]])

        if forecast_date and "date_rules" in pattern:
            for rule in pattern["date_rules"]:
                matches = True

                if "before" in rule:
                    before_date = date_type.fromisoformat(rule["before"])
                    if forecast_date >= before_date:
                        matches = False

                if "after" in rule:
                    after_date = date_type.fromisoformat(rule["after"])
                    if forecast_date <= after_date:
                        matches = False

                if matches:
                    intervals = rule["intervals"]
                    break

        step_list = []
        for interval_start, interval_end, step_interval in intervals:
            current_start = max(interval_start, start_step)
            current_end = min(interval_end, end_step)

            if current_start <= current_end:
                step_list.extend(range(current_start, current_end + 1, step_interval))

        return sorted(set(step_list))

    def get_default_model(self) -> str:
        """Get default model from UI settings."""
        return self.ui_settings.get("default_model", "ifs-single")

    def get_default_parameters(self) -> list[str]:
        """Get default parameters from UI settings."""
        return self.ui_settings.get("default_parameters", ["2t"])

    def get_default_bbox(self) -> dict:
        """Get default bounding box from UI settings."""
        return self.ui_settings.get(
            "default_bbox", {"north": 72.0, "west": -25.0, "south": 34.0, "east": 45.0}
        )

    def get_available_times(self) -> list[str]:
        """Get available forecast times."""
        return self.ui_settings.get("available_times", ["00:00:00"])
