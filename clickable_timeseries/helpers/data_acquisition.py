import datetime
import subprocess
from typing import Any

import earthkit.data as ekd
import pandas as pd
from helpers.parameter_mapper import ConfigurationManager


class BoundingBoxManager:
    """Class for managing bounding box operations and storage."""

    def __init__(self):
        """Initialize the BoundingBoxManager with empty state.

        Attributes:
            current_bbox: Current bounding box coordinates as a tuple (west, south, east, north)
            saved_bboxes: List of previously saved bounding boxes
            current_bbox_params: Dictionary containing current bounding box parameters

        """
        self.current_bbox = None
        self.saved_bboxes = []
        self.current_bbox_params = {}

    def set_current_bbox(
        self, bounds: tuple[float, float, float, float], num_stations: int = 0
    ):
        """Set the current bounding box and store additional parameters.

        Args:
            bounds: Tuple of (west, south, east, north) coordinates
            num_stations: Optional number of stations within the bounding box (default: 0)

        Updates:
            current_bbox: Stores the bounding box coordinates
            current_bbox_params: Dictionary containing bounding box info including width, height, timestamp, and station count

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
        """Get the current bounding box coordinates.

        Returns:
            Tuple of (west, south, east, north) if a bounding box is set, otherwise None

        """
        return self.current_bbox

    def get_current_bbox_params(self) -> dict | None:
        """Get all parameters of the current bounding box.

        Returns:
            Dictionary containing bounding box parameters including coordinates, width, height, timestamp, and station count, or None if no bounding box is set

        """
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
            source: Data source ("mars" for Mars Archive, "file" for local files)
            bbox_manager: Optional bounding box manager instance
            **kwargs: Additional configuration parameters

        """
        self.source = source
        self.config = kwargs
        self.loaded_datasets = {}
        self.dataset_metadata = {}
        self.bbox_manager = bbox_manager or BoundingBoxManager()
        self.config_manager = ConfigurationManager()

    def retrieve_data_by_date_range(
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
        expver: str | None = None,
        custom_class: str | None = None,
    ) -> dict[str, Any] | None:
        """Retrieve meteorological data from Mars Archive based on date range.

        Args:
            param: List of parameter short names
            start_date: Start date for forecast
            end_date: End date for forecast
            time: Forecast time (default: "00:00:00")
            model: Model name (default: "aifs-single")
            stream: Optional data stream
            type: Optional forecast type
            levtype: Optional level type
            grid: Optional grid specification
            use_bbox: Use bounding box from manager if True
            custom_area: Optional custom area coordinates [north, west, south, east]
            custom_steps: Optional list of custom forecast steps

        Returns:
            Dictionary with keys: 'dataset', 'metadata', 'model_key', or None if no valid parameters

        """
        if end_date < start_date:
            print("⚠️  End date is before start date. Returning None.")
            return None

        if custom_area:
            area = custom_area
        elif use_bbox:
            area = self._get_area_from_bbox_manager()
            if not area:
                print("⚠️  No bounding box available, returning None.")
                return None
        else:
            default_bbox = self.config_manager.get_default_bbox()
            area = [
                default_bbox["north"],
                default_bbox["west"],
                default_bbox["south"],
                default_bbox["east"],
            ]

        filtered_param = self._filter_params_for_model(param, model)
        if not filtered_param:
            print(f"⚠️  No valid parameters for model '{model}'. Returning None.")
            return None

        model_info = self.config_manager.get_model_info(model) or {}
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
            start_date.strftime("%Y-%m-%d"),
            custom_steps,
            expver=expver,
            custom_class=custom_class,
        )

    def _filter_params_for_model(self, param: list[str], model: str) -> list[str]:
        """Filter parameters based on model availability.

        Args:
            param: List of parameter names
            model: Model name

        Returns:
            List of parameter short names that are available for the model

        """
        filtered = []
        unavailable = []

        for p in param:
            info = self.config_manager.get_param_info(p)
            if info:
                available_models = info.get("available_models", [])
                if not available_models or model in available_models:
                    filtered.append(p)
                else:
                    unavailable.append(p)
            else:
                filtered.append(p)

        if unavailable:
            print(f"ℹ️  Skipping {unavailable} for {model} (not available).")
            if filtered:
                print(f"   Retrieving: {filtered}")

        return filtered

    def _retrieve_single_request(
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
        expver: str | None = None,
        custom_class: str | None = None,
    ) -> dict[str, Any] | None:
        """Handle single request to Mars Archive.

        Args:
            param: List of parameter short names
            start_date: Start date
            end_date: End date
            time: Forecast time
            model: Model name
            stream: Data stream
            type: Forecast type
            levtype: Level type
            area: Area coordinates
            grid: Optional grid
            date_str: Date string for request
            custom_steps: Optional custom steps

        Returns:
            Dictionary with keys 'dataset', 'metadata', 'model_key' or None if request fails

        """
        param_ids = self.config_manager.get_param_ids(param)
        class_model = custom_class or self.config_manager.get_model_class(model)
        # expver: use caller-supplied value first, then fall back to config
        expver = expver or (self.config_manager.get_model_info(model) or {}).get("expver")

        if custom_steps:
            if self.config_manager.supports_custom_step_expansion(model):
                steps_to_download = self._expand_custom_steps(
                    custom_steps, model, start_date
                )
            else:
                # For non-expandable models (fixed interval, e.g. ifs4km-single hourly,
                # hybrid-single 3-hourly) the multi-model step selector may show coarser
                # 6-hourly options.  Interpret the user's selection as a *range* and
                # regenerate native steps via generate_steps so that we always request
                # the model's own interval (1 h for ifs4km-single, 3 h for hybrid-single).
                # generate_steps respects max_step internally, so no manual clip is needed.
                user_min = min(custom_steps)
                user_max = max(custom_steps)
                model_max_step = self.config_manager.get_model_max_step(model)
                effective_max = (
                    min(user_max, model_max_step)
                    if model_max_step is not None
                    else user_max
                )
                if effective_max < user_min:
                    print(
                        f"⚠️  All selected steps exceed max_step={model_max_step} h "
                        f"for {model}. Skipping retrieval."
                    )
                    return {
                        "error": (
                            f"All selected steps exceed the maximum ({model_max_step} h) "
                            f"available for {model}. No data retrieved."
                        ),
                        "model": model,
                        "request_params": {},
                    }
                steps_to_download = self.config_manager.generate_steps(
                    user_min, effective_max, model, start_date
                )
                if not steps_to_download:
                    print(f"⚠️  No steps generated for {model} in range [{user_min}, {effective_max}].")
                    return {
                        "error": (
                            f"No steps could be generated for {model} "
                            f"in range [{user_min}h, {effective_max}h]."
                        ),
                        "model": model,
                        "request_params": {},
                    }
        else:
            steps_to_download = self._calculate_steps_from_date_range(
                start_date, end_date, time, model
            )

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
            "expect": "any",
        }
        if grid:
            request_params["grid"] = grid
        if expver:
            request_params["expver"] = expver

        try:
            # MARS uses SQLite internally. Both $TMPDIR and $SCRATCH are on
            # Lustre, which does not support SQLite POSIX file locking and
            # causes "unable to open database file" errors. Use /tmp (local
            # tmpfs) unconditionally so SQLite always has a working filesystem.
            import os
            _orig_tmpdir = os.environ.get("TMPDIR")
            _mars_tmp = f"/tmp/mars_tmp_{os.environ.get('USER', 'evalkit')}"
            os.makedirs(_mars_tmp, exist_ok=True)
            os.environ["TMPDIR"] = _mars_tmp

            try:
                ds = ekd.from_source("mars", **request_params).to("fieldlist")
            finally:
                if _orig_tmpdir is None:
                    os.environ.pop("TMPDIR", None)
                else:
                    os.environ["TMPDIR"] = _orig_tmpdir

            # ── 0-fields guard ────────────────────────────────────────────
            # Recent operational data (class=od) can be in FDB but not yet
            # committed to MARS tape.  earthkit caches the empty response;
            # subsequent calls return the stale 0-field result.  Try three
            # escalating fallbacks before giving up.
            if len(ds) == 0:
                print(f"⚠️  MARS returned 0 fields for {model} — retrying without earthkit cache...")
                ds = self._retry_no_cache(request_params, model)

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
            }
            if hasattr(ds, "metadata"):
                metadata["datetime_values"] = ds.metadata("valid_datetime")
            if hasattr(ds, "to_latlon"):
                metadata["grid_coordinates"] = ds.to_latlon()

            self.dataset_metadata[model_key] = metadata
            self.loaded_datasets[model_key] = ds

            return {"dataset": ds, "metadata": metadata, "model_key": model_key}
        except Exception as e:
            # Walk the exception chain to find a CalledProcessError with stderr
            error_detail = str(e)
            cause = e
            while cause is not None:
                if isinstance(cause, subprocess.CalledProcessError):
                    parts = []
                    if cause.stderr:
                        s = cause.stderr if isinstance(cause.stderr, str) else cause.stderr.decode("utf-8", errors="replace")
                        parts.append(s.strip())
                    if cause.stdout:
                        s = cause.stdout if isinstance(cause.stdout, str) else cause.stdout.decode("utf-8", errors="replace")
                        parts.append(s.strip())
                    if parts:
                        error_detail = "\n".join(parts)
                    break
                cause = getattr(cause, "__cause__", None) or getattr(cause, "__context__", None)
            print(f"❌ MARS request failed for {model}: {error_detail}")
            steps = request_params.get("step", [])
            step_summary = f"{steps[0]}/.../{steps[-1]} ({len(steps)} steps)" if len(steps) > 3 else str(steps)
            error_req = {k: v for k, v in request_params.items() if k != "step"}
            error_req["step"] = step_summary
            return {"error": error_detail, "model": model, "request_params": error_req}

    def _retry_no_cache(self, request_params: dict, model: str):
        """Bypass earthkit cache and retry MARS, then fall back to pyfdb.

        When MARS returns 0 fields the earthkit user cache stores that empty
        response.  Subsequent calls within the same session return the stale
        cached result.  This method first retries with the cache disabled; if
        that also returns 0 fields it falls back to a direct pyfdb FDB read
        (useful when data is in FDB but not yet on MARS tape).

        Returns the best non-empty FieldList found, or an empty FieldList when
        all attempts fail (the caller decides how to handle it).
        """
        import os
        import earthkit.data as _ekd

        _MARS_TMP = f"/tmp/mars_tmp_{os.environ.get('USER', 'evalkit')}"
        os.makedirs(_MARS_TMP, exist_ok=True)

        # Stage 1 — MARS without earthkit cache ──────────────────────────
        try:
            stable_path = os.path.join(
                _MARS_TMP,
                f"ts_nocache_{os.getpid()}_{abs(hash(str(sorted(request_params.items()))))}.grib",
            )
            ds_nocache = None
            with _ekd.settings.temporary("cache-policy", "off"):
                ds_nocache = _ekd.from_source("mars", **request_params).to("fieldlist")
                if len(ds_nocache) > 0:
                    ds_nocache.to_target(stable_path)
            if ds_nocache is not None and len(ds_nocache) > 0:
                ds_stable = _ekd.from_source("file", stable_path).to("fieldlist")
                print(f"✅ MARS (no-cache) retrieved {len(ds_stable)} field(s) for {model}")
                return ds_stable
            print(f"⚠️  MARS (no-cache) also returned 0 fields for {model} — trying pyfdb...")
        except Exception as e:
            print(f"[cache-bypass] MARS retry failed for {model}: {e} — trying pyfdb...")

        # Stage 2 — direct pyfdb FDB read ────────────────────────────────
        try:
            ds_fdb = self._retrieve_via_pyfdb(request_params)
            if len(ds_fdb) > 0:
                print(f"✅ FDB fallback retrieved {len(ds_fdb)} field(s) for {model} (native domain — no area filter)")
                return ds_fdb
            print(f"[pyfdb] FDB also returned 0 fields for {model}")
        except Exception as e:
            print(f"[pyfdb] FDB fallback unavailable for {model}: {e}")

        # All fallbacks exhausted — return empty dataset so caller can report
        return ekd.from_source("file", []).to("fieldlist")

    def _retrieve_via_pyfdb(self, request_params: dict):
        """Retrieve data directly from FDB using pyfdb, bypassing MARS.

        Translates the MARS-style request_params into the format pyfdb expects:
        - date: YYYYMMDD (no dashes)
        - param: plain numeric IDs without '.128' table suffix
        - no area/grid/expect/target keys (FDB post-processing not supported)
        - lists → slash-separated strings

        Returns an earthkit FieldList loaded from the written GRIB file.
        """
        import os
        try:
            import pyfdb
        except ImportError:
            raise RuntimeError("pyfdb is not installed — cannot use FDB fallback")

        _SKIP_KEYS = {"area", "grid", "expect", "target"}
        _MARS_TMP = f"/tmp/mars_tmp_{os.environ.get('USER', 'evalkit')}"
        os.makedirs(_MARS_TMP, exist_ok=True)

        fdb_request = {}
        for k, v in request_params.items():
            if k in _SKIP_KEYS:
                continue
            if k == "date":
                v = str(v).replace("-", "")
            if k == "param":
                if isinstance(v, list):
                    cleaned = [str(p).split(".")[0] for p in v]
                    v = "/".join(cleaned)
                else:
                    v = str(v).split(".")[0]
            elif k == "time":
                # FDB expects HHMM not HH:MM:SS
                v = str(v).replace(":", "")[:4]
            elif isinstance(v, list):
                # Expand MARS range shorthands like "1/to/50" to "1/2/.../50"
                def _expand(item):
                    parts = str(item).split("/")
                    if len(parts) == 3 and parts[1].lower() == "to":
                        try:
                            return list(range(int(parts[0]), int(parts[2]) + 1))
                        except ValueError:
                            pass
                    return [item]
                flat = []
                for item in v:
                    flat.extend(_expand(item))
                v = "/".join(str(x) for x in flat)
            else:
                v = str(v)
            fdb_request[k] = v

        tmp_path = os.path.join(
            _MARS_TMP,
            f"ts_pyfdb_{os.getpid()}_{abs(hash(str(sorted(fdb_request.items()))))}.grib",
        )
        try:
            fdb = pyfdb.FDB()
            result = fdb.retrieve(fdb_request)
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = result.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
            return ekd.from_source("file", tmp_path).to("fieldlist")
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise RuntimeError(f"pyfdb retrieval failed: {e}") from e

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
            model: Model name

        Returns:
            List of forecast steps in hours (empty if end < start)

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
            return []
        return self.config_manager.generate_steps(0, total_hours, model, start_date)

    def _expand_custom_steps(
        self, custom_steps: list[int], model: str, forecast_date: datetime.date
    ) -> list[int]:
        """Expand custom steps following model's step pattern.

        Args:
            custom_steps: List of user-selected steps
            model: Model name
            forecast_date: Forecast date

        Returns:
            Expanded list of steps

        """
        if not custom_steps:
            return []
        return self.config_manager.generate_steps(
            min(custom_steps), max(custom_steps), model, forecast_date
        )

    def _get_area_from_bbox_manager(self) -> list[float] | None:
        """Get area coordinates from the bounding box manager.

        Returns:
            List of coordinates [north, west, south, east] or None if no bbox is set

        """
        bbox = self.bbox_manager.get_current_bbox()
        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            return [max_lat, min_lon, min_lat, max_lon]
        return None

    def get_dataset(self, model_key: str) -> Any | None:
        """Get loaded dataset for a specific model key.

        Returns:
            Dataset object or None if not loaded

        """
        return self.loaded_datasets.get(model_key)

    def get_all_datasets(self) -> dict[str, Any]:
        """Get all loaded datasets.

        Returns:
            Copy of loaded datasets dictionary

        """
        return self.loaded_datasets.copy()

    def load_grib_file(
        self, grib_file_path: str, model: str | None = None
    ) -> Any | None:
        """Load GRIB data from file.

        Args:
            grib_file_path: Path to GRIB file
            model: Optional model name

        Returns:
            Dataset object or None if loading fails

        """
        try:
            ds = ekd.from_source("file", grib_file_path).to("fieldlist")
            return ds
        except Exception as e:
            print(f"❌ Failed to load GRIB file {grib_file_path}: {e}")
            return None
