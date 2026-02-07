import os
import subprocess


class ObservationsRetriever:
    """Retrieve meteorological observations using STVL tool."""

    def __init__(self, stvl_path: str = "/home/moz/bin/stvl_getgeo") -> None:
        """Initialize the observations retriever.

        Args:
            stvl_path: Path to the stvl_getgeo executable.

        """
        self.stvl_path = stvl_path

        self.instantaneous_params = {
            "2t": {"times": "0 3 6 9 12 15 18 21"},
            "2d": {"times": "0 3 6 9 12 15 18 21"},
            "10ff": {"times": "0 3 6 9 12 15 18 21"},
        }

        self.period_params = {
            "tp": {
                "supported_periods": [6, 12, 24],
                "times_map": {6: "00 06 12 18", 12: "00 12", 24: "00"},
            },
            "10fg": {
                "supported_periods": [6, 12, 24],
                "times_map": {6: "00 06 12 18", 12: "00 12", 24: "00"},
            },
            "tmax": {"supported_periods": [24], "times_map": {24: "00"}},
            "tmin": {"supported_periods": [24], "times_map": {24: "00"}},
        }

    def get_parameter_info(self, parameter: str) -> dict:
        """Get information about parameter requirements.

        Args:
            parameter: Parameter code (e.g., "2t", "tp", "tmax")

        Returns:
            dict: Parameter information including type and requirements

        """
        if parameter in self.instantaneous_params:
            return {
                "type": "instantaneous",
                "default_times": self.instantaneous_params[parameter]["times"],
                "uses_period": False,
            }
        elif parameter in self.period_params:
            param_info = self.period_params[parameter]
            return {
                "type": "period",
                "supported_periods": param_info["supported_periods"],
                "default_period": param_info["supported_periods"][0],
                "times_map": param_info["times_map"],
                "uses_period": True,
            }
        else:
            return {"type": "unknown", "default_times": "00", "uses_period": False}

    def validate_parameter_config(
        self, parameter: str, period: str | int | None = None
    ) -> dict:
        """Validate parameter configuration.

        Args:
            parameter: Parameter code
            period: Period in hours (for period-based parameters)

        Returns:
            dict: Validation result with status and corrected values

        """
        param_info = self.get_parameter_info(parameter)
        result = {"is_valid": True, "warnings": [], "parameter": parameter}

        if param_info["type"] == "instantaneous":
            if period is not None:
                result["warnings"].append(
                    f"Parameter {parameter} is instantaneous - ignoring period {period}"
                )
            result["times"] = param_info["default_times"]
            result["period"] = None
            result["uses_period"] = False

        elif param_info["type"] == "period":
            period_int = (
                int(period) if period is not None else param_info["default_period"]
            )

            if period_int not in param_info["supported_periods"]:
                result["is_valid"] = False
                result["error"] = (
                    f"Period {period_int}h not supported for {parameter}. Supported: {param_info['supported_periods']}"
                )
                return result

            result["period"] = str(period_int)
            result["times"] = param_info["times_map"][period_int]
            result["uses_period"] = True

        else:
            result["warnings"].append(
                f"Unknown parameter {parameter} - using default settings"
            )
            result["times"] = param_info["default_times"]
            result["period"] = None
            result["uses_period"] = False

        return result

    def build_output_path(
        self, base_dir: str, parameter: str, period: str | None = None
    ) -> str:
        """Build appropriate output path based on parameter type.

        Args:
            base_dir: Base output directory
            parameter: Parameter code
            period: Period (if applicable)

        Returns:
            str: Complete output path

        """
        param_info = self.get_parameter_info(parameter)

        if param_info["type"] == "instantaneous":
            return os.path.join(base_dir, parameter, f"{parameter}_3h")
        elif param_info["type"] == "period" and period:
            return os.path.join(base_dir, parameter, f"{parameter}_{period}h")
        else:
            # Fallback
            return os.path.join(base_dir, parameter)

    def retrieve(  # noqa: PLR0913
        self,
        sources: str = "synop hdobs",
        parameter: str = "tp",
        period: str | int | None = None,
        start_date: str = "20250301",
        end_date: str = "20250430",
        times: str | None = None,
        output_dir: str | None = None,
    ) -> dict:
        """Retrieve meteorological observations for a single parameter.

        Args:
            sources: Data sources to retrieve from (e.g., "synop hdobs").
            parameter: Meteorological parameter code (e.g., "tp", "2t", "tmax").
            period: Accumulation period in hours (only for period-based parameters).
            start_date: Start date in YYYYMMDD format.
            end_date: End date in YYYYMMDD format.
            times: Hour(s) to retrieve (if None, uses parameter-appropriate defaults).
            output_dir: Directory path for output files (if None, auto-generated).

        Returns:
            dict: Result with success status, output directory, and any warnings.

        """
        validation = self.validate_parameter_config(parameter, period)
        if not validation["is_valid"]:
            raise ValueError(validation.get("error", "Invalid parameter configuration"))

        final_times = times if times is not None else validation["times"]
        final_period = validation.get("period")
        uses_period = validation["uses_period"]

        if output_dir is None:
            output_dir = self.build_output_path("./output", parameter, final_period)

        os.makedirs(output_dir, exist_ok=True)

        try:
            print(f"Executing STVL command for {parameter}...")

            cmd_list = [self.stvl_path, "--sources", sources, "--parameter", parameter]

            if uses_period and final_period:
                cmd_list.extend(["--period", final_period])

            cmd_list.extend(
                [
                    "--dates",
                    f"{start_date}/to/{end_date}",
                    "--times",
                    final_times,
                    "--columns",
                    "value_0 elevation",
                    "--outdir",
                    output_dir,
                    "--flattree",
                ]
            )

            subprocess.run(cmd_list, check=True)

            result = {
                "success": True,
                "parameter": parameter,
                "output_dir": output_dir,
                "times": final_times,
                "warnings": validation.get("warnings", []),
            }

            if uses_period:
                result["period"] = final_period

            print(f"Successfully retrieved {parameter}")
            for warning in validation.get("warnings", []):
                print(f"Warning: {warning}")

            return result

        except subprocess.CalledProcessError as e:
            error_msg = f"STVL command failed with return code {e.returncode}"
            print(f"Error retrieving {parameter}: {error_msg}")
            raise
        except FileNotFoundError:
            error_msg = f"STVL executable not found at {self.stvl_path}"
            print(f"Error: {error_msg}")
            raise
        except Exception as e:
            error_msg = f"Unexpected error retrieving {parameter}: {e}"
            print(f"Error: {error_msg}")
            raise
