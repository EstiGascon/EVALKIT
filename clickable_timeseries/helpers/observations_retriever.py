import os
import subprocess


class ObservationsRetriever:
    """Retrieve meteorological observations using VINO tool (formerly STVL)."""

    def __init__(self, vino_path: str = "/home/moz/bin/vino_getgeo") -> None:
        """Initialize the observations retriever.

        Args:
            vino_path: Path to the vino_getgeo executable.

        """
        self.vino_path = vino_path

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
                "supported_periods": [1],
                "times_map": {1: "00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23"},
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

        Raises:
            ValueError: If the parameter/period configuration is invalid.
            RuntimeError: If the VINO command fails or returns an error.
            FileNotFoundError: If the VINO executable is not found at the configured path.

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
            print(f"Executing VINO command for {parameter}...")

            cmd_list = [self.vino_path]
            cmd_list.extend(["--sources"] + sources.split())
            cmd_list.extend(["--parameter", parameter])

            if uses_period and final_period:
                cmd_list.extend(["--period", final_period])

            cmd_list.extend(["--dates", f"{start_date}/to/{end_date}"])
            cmd_list.extend(["--times"] + final_times.split())
            cmd_list.extend(["--columns", "value_0", "elevation"])
            cmd_list.extend(["--outdir", output_dir, "--flattree"])

            cmd_str = " ".join(cmd_list)
            print(f"Command: {cmd_str}")

            # Redirect METVIEW tmpdir to $SCRATCH (session tmpdir is quota-limited)
            env = os.environ.copy()
            scratch = os.environ.get("SCRATCH", "")
            if scratch:
                metview_tmp = os.path.join(scratch, "metview_tmp")
                os.makedirs(metview_tmp, exist_ok=True)
                env["METVIEW_TMPDIR"] = metview_tmp
                env["TMPDIR"] = metview_tmp

            # Ensure metview is in PATH for the subprocess.  The VINO script
            # may reload ecmwf-toolbox to a different version, which can drop
            # the metview binary from PATH.  Resolve it once from the current
            # shell environment and prepend it so the subprocess always finds it.
            import shutil as _shutil
            _metview_bin = _shutil.which("metview")
            if _metview_bin:
                _metview_dir = os.path.dirname(_metview_bin)
                existing_path = env.get("PATH", "")
                if _metview_dir not in existing_path.split(os.pathsep):
                    env["PATH"] = _metview_dir + os.pathsep + existing_path

            result_proc = subprocess.run(
                cmd_list, check=True, capture_output=True, text=True, env=env
            )

            result = {
                "success": True,
                "parameter": parameter,
                "output_dir": output_dir,
                "times": final_times,
                "warnings": validation.get("warnings", []),
            }

            if uses_period:
                result["period"] = final_period

            if result_proc.stdout:
                print(result_proc.stdout)
            if result_proc.stderr:
                print(result_proc.stderr)

            print(f"Successfully retrieved {parameter}")
            for warning in validation.get("warnings", []):
                print(f"Warning: {warning}")

            return result

        except subprocess.CalledProcessError as e:
            cmd_str = " ".join(cmd_list)
            stderr_msg = e.stderr.strip() if e.stderr else ""
            stdout_msg = e.stdout.strip() if e.stdout else ""
            vino_output = stderr_msg or stdout_msg or "(no output captured)"
            error_msg = (
                f"VINO command failed with return code {e.returncode}:\n{cmd_str}"
                f"\n\nVINO output:\n{vino_output}"
            )
            print(f"Error retrieving {parameter}: {error_msg}")
            raise RuntimeError(error_msg) from e
        except FileNotFoundError:
            error_msg = f"VINO executable not found at {self.vino_path}"
            print(f"Error: {error_msg}")
            raise
        except Exception as e:
            error_msg = f"Unexpected error retrieving {parameter}: {e}"
            print(f"Error: {error_msg}")
            raise
