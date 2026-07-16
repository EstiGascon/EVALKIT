import math

import cartopy.crs as ccrs  # type: ignore
import earthkit.plots  # type: ignore
import numpy as np
import xarray as xr
from helpers.styling_config import StylingConfiguration
from scipy.interpolate import griddata
from scipy.spatial import cKDTree


class StampsPlotting:
    """Create ensemble stamp plots with custom layout for meteorological data."""

    def __init__(self, style_config=StylingConfiguration()):
        """Initialize with styling configuration.

        Args:
            style_config: StylingConfiguration instance for plot styling

        """
        self.style_config = style_config

    def _extract_dataset_and_metadata(self, forecast_data):
        """Extract dataset and metadata from forecast data structure.

        Args:
            forecast_data: Either a dataset or dict with 'dataset' and 'metadata' keys

        Returns:
            Tuple of (dataset, metadata dict)

        """
        if isinstance(forecast_data, dict) and "dataset" in forecast_data:
            return forecast_data["dataset"], forecast_data.get("metadata", {})
        return forecast_data, {}

    def _extract_model_name(self, stamp_ds):
        """Extract model name from stamp dataset metadata.

        Args:
            stamp_ds: Dictionary containing 'fc', 'cf', or 'pf' forecast data

        Returns:
            Model name string (e.g., 'IFS', 'GFS') or 'UNKNOWN'

        """
        for forecast_type in ["fc", "cf", "pf"]:
            if forecast_type in stamp_ds:
                _, metadata = self._extract_dataset_and_metadata(
                    stamp_ds[forecast_type]
                )
                if metadata and "model_class" in metadata:
                    return metadata["model_class"].upper()
        return "UNKNOWN"

    def _detect_grid_type(self, data):
        """Detect if data is on a reduced Gaussian grid.

        Args:
            data: GRIB field or xarray data

        Returns:
            True if data is on reduced grid, False otherwise

        """
        if hasattr(data, "metadata"):
            try:
                first_field = data[0] if hasattr(data, "__getitem__") else data
                grid_type = first_field.metadata("gridType")
                return grid_type in ["reduced_gg", "reduced_ll"]
            except Exception:
                pass

        if isinstance(data, xr.DataArray | xr.Dataset):
            if "latitude" in data.coords and "longitude" in data.coords:
                lat_vals = data.coords["latitude"].values
                lon_vals = data.coords["longitude"].values

                if lat_vals.ndim > 1 or lon_vals.ndim > 1:
                    return True

                if hasattr(data, "dims") and (
                    "values" in data.dims or "rgrid" in data.dims
                ):
                    return True

        return False

    def _derive_wind_speed_from_components(self, dataset, step, is_pf=False, max_members=None):
        """Compute 10 m wind speed (m/s) from U and V components.

        Selects ``10u`` and ``10v`` at the requested step and returns a list
        (or FieldList-equivalent list) of xr.DataArray objects whose values are
        ``sqrt(u^2 + v^2)``.  Works for both single fields (fc/cf) and
        multiple ensemble members (pf).

        Args:
            dataset: earthkit FieldList for one source (fc / cf / pf).
            step: Forecast step to select.
            is_pf: When True the dataset may contain many members; each
                matching (u, v) pair produces one wind-speed DataArray.
            max_members: Maximum number of PF members to return (ignored when
                ``is_pf=False``).

        Returns:
            List of xr.DataArray on success, or an empty list on failure.
        """
        try:
            u_fields = dataset.sel(step=step, shortName="10u")
            v_fields = dataset.sel(step=step, shortName="10v")
        except Exception as exc:
            print(f"[stamps] _derive_wind_speed: component selection failed: {exc}")
            return []

        if len(u_fields) == 0 or len(v_fields) == 0:
            print(f"[stamps] _derive_wind_speed: 10u({len(u_fields)}) or 10v({len(v_fields)}) not found")
            return []

        # Limit members for PF
        n = min(len(u_fields), len(v_fields))
        if is_pf and max_members is not None:
            n = min(n, max_members)

        result = []
        for i in range(n):
            try:
                u_field = u_fields[i]
                v_field = v_fields[i]

                # --- extract arrays ---
                if hasattr(u_field, "to_numpy"):
                    u_arr = np.asarray(u_field.to_numpy()).flatten()
                    v_arr = np.asarray(v_field.to_numpy()).flatten()
                    # Build a DataArray keeping coordinate info from one component
                    if hasattr(u_field, "to_xarray"):
                        u_xr = u_field.to_xarray()
                        if isinstance(u_xr, xr.Dataset):
                            u_xr = u_xr[list(u_xr.data_vars)[0]]
                        ws_values = np.sqrt(
                            np.asarray(u_xr.values) ** 2
                            + np.asarray(v_field.to_xarray()[list(v_field.to_xarray().data_vars)[0]].values
                                         if isinstance(v_field.to_xarray(), xr.Dataset)
                                         else v_field.to_xarray()) ** 2
                        )
                        ws_da = u_xr.copy(data=ws_values)
                        ws_da.name = "ws"
                        ws_da.attrs["units"] = "m s**-1"
                        ws_da.attrs.pop("GRIB_units", None)
                    else:
                        # No xarray available — build from lat/lon
                        ll = u_field.to_latlon()
                        lats = np.asarray(ll["lat"]).flatten()
                        lons = np.asarray(ll["lon"]).flatten()
                        ws_values = np.sqrt(u_arr ** 2 + v_arr ** 2)
                        ws_da = xr.DataArray(
                            ws_values.reshape(lats.shape),
                            coords={"latitude": lats, "longitude": lons},
                            dims=["values"],
                            name="ws",
                            attrs={"units": "m s**-1"},
                        )
                elif isinstance(u_field, xr.DataArray):
                    u_xr = u_field
                    v_xr = v_field
                    ws_values = np.sqrt(u_xr.values ** 2 + v_xr.values ** 2)
                    ws_da = u_xr.copy(data=ws_values)
                    ws_da.name = "ws"
                    ws_da.attrs["units"] = "m s**-1"
                    ws_da.attrs.pop("GRIB_units", None)
                else:
                    print(f"[stamps] _derive_wind_speed: unknown field type {type(u_field)}")
                    continue

                result.append(ws_da)
            except Exception as exc:
                print(f"[stamps] _derive_wind_speed: member {i} failed: {exc}")

        print(f"[stamps] _derive_wind_speed: derived {len(result)} wind-speed field(s) from 10u/10v")
        return result

    def _get_latlon_and_values(self, field):
        """Extract lat, lon, and values arrays from an earthkit GRIB field.

        Works for any grid type (reduced Gaussian, regular lat/lon, etc.) by
        using earthkit's native to_latlon() / to_numpy() APIs.

        Returns:
            (lats, lons, vals) as 1-D numpy arrays, or (None, None, None) on failure.
        """
        # --- earthkit path (FieldList or GribField) ---
        if hasattr(field, "to_latlon") and hasattr(field, "to_numpy"):
            try:
                ll = field.to_latlon()
                lats = np.asarray(ll["lat"]).flatten()
                lons = np.asarray(ll["lon"]).flatten()
                # Normalize to -180..180 (OPER native uses 0-360)
                lons = np.where(lons > 180, lons - 360, lons)
                vals = np.asarray(field.to_numpy()).flatten()
                # to_numpy() on a FieldList with N fields returns (N, n_pts);
                # take the first field's values so lengths match.
                n_pts = len(lats)
                if len(vals) > n_pts:
                    vals = vals[:n_pts]
                if len(vals) == n_pts:
                    return lats, lons, vals
            except Exception as e:
                print(f"[stamps] to_latlon/to_numpy failed: {e}")

        # --- xarray fallback ---
        try:
            if hasattr(field, "to_xarray"):
                data_xr = field.to_xarray()
            else:
                data_xr = field

            if isinstance(data_xr, xr.Dataset):
                data_xr = data_xr[list(data_xr.data_vars.keys())[0]]

            # Try to extract lat/lon from coords
            lat_coord = data_xr.coords.get("latitude", data_xr.coords.get("lat", None))
            lon_coord = data_xr.coords.get("longitude", data_xr.coords.get("lon", None))

            if lat_coord is not None and lon_coord is not None:
                lats = np.asarray(lat_coord).flatten()
                lons = np.asarray(lon_coord).flatten()
                # Normalize to -180..180
                lons = np.where(lons > 180, lons - 360, lons)
                vals = np.asarray(data_xr).flatten()
                n_pts = len(lats)
                if len(vals) > n_pts:
                    vals = vals[:n_pts]
                if len(lats) == len(lons) == len(vals):
                    return lats, lons, vals

            # Last resort: build meshgrid from dimension coordinates
            if "latitude" in data_xr.dims and "longitude" in data_xr.dims:
                lat_arr = data_xr.coords["latitude"].values
                lon_arr = data_xr.coords["longitude"].values
                # Normalize to -180..180
                lon_arr = np.where(lon_arr > 180, lon_arr - 360, lon_arr)
                lon_grid, lat_grid = np.meshgrid(lon_arr, lat_arr)
                lats = lat_grid.flatten()
                lons = lon_grid.flatten()
                vals = np.asarray(data_xr).flatten()
                if len(lats) == len(vals):
                    return lats, lons, vals
        except Exception as e:
            print(f"[stamps] xarray fallback failed: {e}")

        return None, None, None

    def _compute_common_bbox(self, all_fields, parameter_name):
        """Compute the intersection bounding box across all fields."""
        lon_mins, lon_maxs, lat_mins, lat_maxs = [], [], [], []
        for field in all_fields:
            # Fast path: use earthkit metadata (avoids loading all lat/lon points)
            bbox_extracted = False
            if hasattr(field, "metadata"):
                try:
                    # Try getting a single GribField (index 0 if FieldList)
                    f = field[0] if hasattr(field, "__getitem__") and not hasattr(field, "metadata") else field
                    try:
                        f = field[0]
                    except Exception:
                        f = field
                    # earthkit bounding box keys
                    lat_first = f.metadata("latitudeOfFirstGridPointInDegrees")
                    lat_last = f.metadata("latitudeOfLastGridPointInDegrees")
                    lon_first = f.metadata("longitudeOfFirstGridPointInDegrees")
                    lon_last = f.metadata("longitudeOfLastGridPointInDegrees")
                    # Normalize longitudes to -180..180
                    lon_first = lon_first - 360 if lon_first > 180 else lon_first
                    lon_last = lon_last - 360 if lon_last > 180 else lon_last
                    lat_min = min(lat_first, lat_last)
                    lat_max = max(lat_first, lat_last)
                    lon_min = min(lon_first, lon_last)
                    lon_max = max(lon_first, lon_last)
                    lat_mins.append(float(lat_min))
                    lat_maxs.append(float(lat_max))
                    lon_mins.append(float(lon_min))
                    lon_maxs.append(float(lon_max))
                    bbox_extracted = True
                except Exception:
                    pass

            if not bbox_extracted:
                lats, lons, _ = self._get_latlon_and_values(field)
                if lats is not None and len(lats) > 0:
                    lon_mins.append(float(np.nanmin(lons)))
                    lon_maxs.append(float(np.nanmax(lons)))
                    lat_mins.append(float(np.nanmin(lats)))
                    lat_maxs.append(float(np.nanmax(lats)))
        if not lon_mins:
            print("[stamps] _compute_common_bbox: could not extract coords from any field")
            return None
        # Intersection (tightest shared area)
        return (
            max(lon_mins), min(lon_maxs),
            max(lat_mins), min(lat_maxs),
        )

    def _regrid_to_common(self, field, parameter_name, target_resolution, bbox):
        """Regrid a field to a fixed regular grid defined by bbox and resolution.

        Args:
            field: earthkit GRIB field (FieldList or GribField) or xr.DataArray
            parameter_name: Parameter short name
            target_resolution: Grid spacing in degrees
            bbox: (lon_min, lon_max, lat_min, lat_max)

        Returns:
            xr.DataArray on the target grid, or original field on failure.
        """
        try:
            lats, lons, vals = self._get_latlon_and_values(field)
            if lats is None or len(lats) == 0:
                print(f"[stamps] _regrid_to_common: no coordinates for {parameter_name}, skipping")
                return field

            lon_min, lon_max, lat_min, lat_max = bbox
            target_lons = np.arange(
                lon_min, lon_max + target_resolution * 0.5, target_resolution
            )
            # Ascending latitude so earthkit.plots renders with north up
            target_lats = np.arange(
                lat_min, lat_max + target_resolution * 0.5, target_resolution
            )

            src_points = np.column_stack([lons, lats])
            lon_grid, lat_grid = np.meshgrid(target_lons, target_lats)
            interpolated = griddata(
                src_points, vals, (lon_grid, lat_grid), method="nearest"
            )

            return xr.DataArray(
                interpolated,
                coords={"latitude": target_lats, "longitude": target_lons},
                dims=["latitude", "longitude"],
                name=parameter_name,
            )
        except Exception as e:
            print(f"[stamps] _regrid_to_common failed for {parameter_name}: {e}")
            return field

    def _regrid_batch_to_common(self, fields, parameter_name, target_resolution, bbox):
        """Regrid a collection of fields that share the same source grid.

        Instead of calling griddata 50 times (once per PF member), this method
        builds a cKDTree from the first field's coordinates and reuses the
        nearest-neighbour index for every subsequent field — drastically reducing
        computation time.

        Args:
            fields: Iterable of earthkit GRIB fields (all on the same source grid)
            parameter_name: Parameter short name
            target_resolution: Grid spacing in degrees
            bbox: (lon_min, lon_max, lat_min, lat_max)

        Returns:
            List of xr.DataArray objects on the common target grid.
            Falls back to the original fields on error.
        """
        result = []
        tree = None
        target_shape = None
        target_lats = target_lons = None
        target_points = None

        try:
            lon_min, lon_max, lat_min, lat_max = bbox
            target_lons = np.arange(lon_min, lon_max + target_resolution * 0.5, target_resolution)
            target_lats = np.arange(lat_min, lat_max + target_resolution * 0.5, target_resolution)
            lon_grid, lat_grid = np.meshgrid(target_lons, target_lats)
            target_shape = lon_grid.shape
            target_points = np.column_stack([lon_grid.ravel(), lat_grid.ravel()])
        except Exception as e:
            print(f"[stamps] _regrid_batch_to_common: target grid setup failed: {e}")
            return list(fields)

        # Fast path: if fields is an earthkit FieldList, read all coords and
        # values in two bulk calls instead of one-per-field.
        if hasattr(fields, "to_latlon") and hasattr(fields, "to_numpy") and len(fields) > 1:
            try:
                ll = fields[0].to_latlon()
                lats = np.asarray(ll["lat"]).flatten()
                lons = np.asarray(ll["lon"]).flatten()
                lons = np.where(lons > 180, lons - 360, lons)
                all_vals = np.asarray(fields.to_numpy())  # shape (N, n_pts)
                if all_vals.ndim == 1:
                    all_vals = all_vals[np.newaxis, :]

                src_points = np.column_stack([lons, lats])
                tree = cKDTree(src_points)
                _dist, idx = tree.query(target_points, workers=-1)

                for row in all_vals:
                    interpolated = row[idx].reshape(target_shape)
                    result.append(xr.DataArray(
                        interpolated,
                        coords={"latitude": target_lats, "longitude": target_lons},
                        dims=["latitude", "longitude"],
                        name=parameter_name,
                    ))
                return result
            except Exception as e:
                print(f"[stamps] _regrid_batch_to_common bulk path failed ({e}), falling back to per-field")
                result = []

        for field in fields:
            try:
                lats, lons, vals = self._get_latlon_and_values(field)
                if lats is None or len(lats) == 0:
                    result.append(field)
                    continue

                # Build KDTree from the first field's source grid;
                # reuse for all subsequent fields (same source resolution).
                if tree is None:
                    src_points = np.column_stack([lons, lats])
                    tree = cKDTree(src_points)

                _dist, idx = tree.query(target_points, workers=-1)
                interpolated = vals[idx].reshape(target_shape)

                result.append(xr.DataArray(
                    interpolated,
                    coords={"latitude": target_lats, "longitude": target_lons},
                    dims=["latitude", "longitude"],
                    name=parameter_name,
                ))
            except Exception as e:
                print(f"[stamps] _regrid_batch_to_common: field failed: {e}")
                result.append(field)

        return result

    def calculate_optimal_grid(self, total_plots, max_cols=10):
        """Calculate optimal grid dimensions for stamp plots.

        Args:
            total_plots: Total number of plots to display
            max_cols: Maximum number of columns

        Returns:
            Tuple of (nrows, ncols)

        """
        if total_plots <= 0:
            return 1, max_cols
        nrows = math.ceil(total_plots / max_cols)
        return nrows, max_cols

    def _load_and_regrid_data(
        self, stamp_ds, parameter, step, max_ensemble_members, regrid, target_resolution,
        precip_accumulation=None,
    ):
        """Load forecast data and optionally regrid to regular grid.

        Args:
            stamp_ds: Dictionary with 'fc', 'cf', 'pf' forecast data
            parameter: Parameter name to extract
            step: Forecast step/lead time
            max_ensemble_members: Maximum ensemble members to load
            regrid: Whether to regrid reduced grids
            target_resolution: Target resolution for regridding
            precip_accumulation: Accumulation window in hours for precipitation
                parameters (tp/lsp/cp). The data is expected to be cumulative;
                the value at (step - precip_accumulation) is subtracted to
                obtain the period total. If None, raw field values are used.

        Returns:
            Tuple of (fc_data, cf_data, pf_data, fc_metadata, cf_metadata)

        """
        fc_data, cf_data, pf_data = [], [], []
        fc_metadata, cf_metadata = {}, {}
        _sel_errors = []

        print(f"[stamps] _load_and_regrid_data: parameter={parameter!r}, step={step!r} (type={type(step).__name__})")

        # Parameters that can be derived from U/V wind components when not
        # available as a native GRIB field (e.g. AIFS-ENS does not store 'ws').
        _DERIVED_FROM_UV = {"ws"}

        if "fc" in stamp_ds:
            try:
                fc_dataset, fc_metadata = self._extract_dataset_and_metadata(
                    stamp_ds["fc"]
                )
                selected = fc_dataset.sel(step=step, shortName=parameter)
                if len(selected) > 0:
                    fc_data = [selected]
                elif parameter in _DERIVED_FROM_UV:
                    fc_data = self._derive_wind_speed_from_components(fc_dataset, step)
                    if not fc_data:
                        _sel_errors.append(f"fc: sel(step={step}, shortName={parameter}) returned 0 fields; 10u/10v derivation also failed")
                else:
                    _sel_errors.append(f"fc: sel(step={step}, shortName={parameter}) returned 0 fields")
            except Exception as e:
                _sel_errors.append(f"fc: {e}")

        if "cf" in stamp_ds:
            try:
                cf_dataset, cf_metadata = self._extract_dataset_and_metadata(
                    stamp_ds["cf"]
                )
                selected = cf_dataset.sel(step=step, shortName=parameter)
                if len(selected) > 0:
                    cf_data = [selected]
                elif parameter in _DERIVED_FROM_UV:
                    cf_data = self._derive_wind_speed_from_components(cf_dataset, step)
                    if not cf_data:
                        _sel_errors.append(f"cf: sel(step={step}, shortName={parameter}) returned 0 fields; 10u/10v derivation also failed")
                else:
                    _sel_errors.append(f"cf: sel(step={step}, shortName={parameter}) returned 0 fields")
            except Exception as e:
                _sel_errors.append(f"cf: {e}")

        if "pf" in stamp_ds:
            try:
                pf_dataset, _ = self._extract_dataset_and_metadata(stamp_ds["pf"])
                selected = pf_dataset.sel(step=step, shortName=parameter)
                if len(selected) > 0:
                    pf_data = selected
                    if (
                        max_ensemble_members is not None
                        and len(pf_data) > max_ensemble_members
                    ):
                        pf_data = pf_data[:max_ensemble_members]
                elif parameter in _DERIVED_FROM_UV:
                    pf_data = self._derive_wind_speed_from_components(
                        pf_dataset, step, is_pf=True, max_members=max_ensemble_members
                    )
                    if not pf_data:
                        _sel_errors.append(f"pf: sel(step={step}, shortName={parameter}) returned 0 fields; 10u/10v derivation also failed")
                else:
                    _sel_errors.append(f"pf: sel(step={step}, shortName={parameter}) returned 0 fields")
            except Exception as e:
                _sel_errors.append(f"pf: {e}")

        print(f"[stamps] sel results: n_fc={len(fc_data)}, n_cf={len(cf_data)}, n_pf={len(pf_data)}, errors={_sel_errors}")

        self._last_sel_errors = _sel_errors

        # Compute the shared bounding box once so it can be reused when
        # loading start-step fields for precipitation accumulation.
        _bbox = None

        if regrid:
            # Always regrid ALL fields to a common regular grid.
            # FC (OPER) and CF/PF (ENFO) have different native resolutions
            # and earthkit contourf requires identical grid sizes.
            all_fields = []
            if fc_data:
                all_fields.append(fc_data[0])
            if cf_data:
                all_fields.append(cf_data[0])
            if pf_data:
                all_fields.append(pf_data[0])

            _bbox = self._compute_common_bbox(all_fields, parameter) if all_fields else None

            if _bbox:
                if fc_data:
                    fc_data = [self._regrid_to_common(fc_data[0], parameter, target_resolution, _bbox)]
                if cf_data:
                    cf_data = [self._regrid_to_common(cf_data[0], parameter, target_resolution, _bbox)]
                if pf_data:
                    # Batch-regrid all PF members: build the KDTree once (all PF
                    # members share the same source grid) then apply the
                    # nearest-neighbour mapping to every member in one loop —
                    # this avoids rebuilding the spatial index 50 times.
                    pf_data = self._regrid_batch_to_common(
                        pf_data, parameter, target_resolution, _bbox
                    )

        # For cumulative precipitation parameters, compute the period accumulation
        # by subtracting the start-step cumulative value from the end-step value.
        _PRECIP_PARAMS = {"tp", "lsp", "cp"}
        if parameter in _PRECIP_PARAMS and precip_accumulation and precip_accumulation > 0:
            start_step = step - precip_accumulation
            fc_data, cf_data, pf_data = self._apply_precip_accumulation(
                stamp_ds, parameter, start_step, max_ensemble_members,
                regrid, target_resolution, _bbox,
                fc_data, cf_data, pf_data,
            )

        return fc_data, cf_data, pf_data, fc_metadata, cf_metadata

    def _apply_precip_accumulation(
        self, stamp_ds, parameter, start_step, max_ensemble_members,
        regrid, target_resolution, bbox,
        fc_end, cf_end, pf_end,
    ):
        """Subtract start-step cumulative values from end-step to give period accumulation.

        The stamps retrieval keeps raw cumulative precipitation fields so that
        any accumulation window can be computed here without re-fetching data.

        Args:
            stamp_ds: Full stamps data dictionary.
            parameter: Precipitation parameter short name (tp, lsp, cp).
            start_step: Step at the beginning of the accumulation window.
            max_ensemble_members: Maximum PF members to use.
            regrid: Whether the end fields were regridded.
            target_resolution: Target resolution used for regridding.
            bbox: Bounding box (lon_min, lon_max, lat_min, lat_max) used for
                regridding, or None when regrid=False.
            fc_end, cf_end, pf_end: End-step data (already regridded if
                regrid=True).

        Returns:
            Tuple (fc_data, cf_data, pf_data) containing the period
            accumulation fields.

        Raises:
            ValueError: If the start step is not found in any required source.

        """

        def _sel_start(key, is_pf=False):
            if key not in stamp_ds:
                return None, None
            try:
                ds, _ = self._extract_dataset_and_metadata(stamp_ds[key])
                selected = ds.sel(step=start_step, shortName=parameter)
                if len(selected) == 0:
                    return None, f"T+{start_step}h not in {key}"
                if is_pf and max_ensemble_members and len(selected) > max_ensemble_members:
                    selected = selected[:max_ensemble_members]
                return selected, None
            except Exception as e:
                return None, str(e)

        fc_start_raw, fc_err = _sel_start("fc") if fc_end else (None, None)
        cf_start_raw, cf_err = _sel_start("cf") if cf_end else (None, None)
        pf_start_raw, pf_err = _sel_start("pf", is_pf=True) if pf_end else (None, None)

        errors = [e for e in [fc_err, cf_err, pf_err] if e]
        if errors:
            raise ValueError(
                f"Cannot compute precipitation accumulation: the start step "
                f"T+{start_step}h is not in the data ({'; '.join(errors)}). "
                f"Select an accumulation period compatible with the data time "
                f"resolution, or re-retrieve with a finer step frequency."
            )

        # Regrid start fields onto the same target grid as the end fields.
        if regrid and bbox:
            fc_start = (
                [self._regrid_to_common(fc_start_raw[0], parameter, target_resolution, bbox)]
                if fc_start_raw else []
            )
            cf_start = (
                [self._regrid_to_common(cf_start_raw[0], parameter, target_resolution, bbox)]
                if cf_start_raw else []
            )
            pf_start = (
                self._regrid_batch_to_common(pf_start_raw, parameter, target_resolution, bbox)
                if pf_start_raw else []
            )
        else:
            # No-regrid path: convert to DataArray so subtraction is possible.
            def _ek_to_da(field):
                lats, lons, vals = self._get_latlon_and_values(field)
                if lats is None:
                    return None
                return xr.DataArray(vals, name=parameter)

            fc_start = [_ek_to_da(fc_start_raw[0])] if fc_start_raw else []
            cf_start = [_ek_to_da(cf_start_raw[0])] if cf_start_raw else []
            pf_start = [_ek_to_da(f) for f in (pf_start_raw or [])]

            # The end-step fields passed in are still raw earthkit fields
            # (only regridded when regrid=True), so they must be converted
            # here too, otherwise `_subtract` below silently skips the
            # subtraction (type mismatch) and returns raw cumulative values.
            fc_end = [_ek_to_da(fc_end[0])] if fc_end else []
            cf_end = [_ek_to_da(cf_end[0])] if cf_end else []
            pf_end = [_ek_to_da(f) for f in (pf_end or [])]

        # Ensure pf_end is a plain list so zip works correctly.
        pf_end_list = (
            list(pf_end) if pf_end is not None and not isinstance(pf_end, list) else (pf_end or [])
        )

        def _subtract(end_list, start_list):
            if not end_list or not start_list:
                return end_list
            result = []
            for ef, sf in zip(end_list, start_list):
                if sf is None:
                    result.append(ef)
                    continue
                if isinstance(ef, xr.DataArray) and isinstance(sf, xr.DataArray):
                    diff = ef - sf
                    diff.name = parameter
                    result.append(diff)
                else:
                    result.append(ef)
            return result

        return (
            _subtract(fc_end, fc_start),
            _subtract(cf_end, cf_start),
            _subtract(pf_end_list, pf_start),
        )

    def _extract_base_time(self, fc_data, cf_data, fc_metadata, cf_metadata):
        """Extract base time from metadata or data fields.

        Args:
            fc_data: Forecast data list
            cf_data: Control forecast data list
            fc_metadata: Forecast metadata dict
            cf_metadata: Control forecast metadata dict

        Returns:
            Base time string formatted as "YYYYMMDD HH:MM"

        """
        for metadata in [fc_metadata, cf_metadata]:
            if metadata and "date" in metadata:
                date_str = metadata["date"]
                time_str = metadata.get("time", "00:00:00")
                hour = (
                    time_str.split(":")[0]
                    if ":" in time_str
                    else str(int(time_str) // 100)
                )
                minute = (
                    time_str.split(":")[1]
                    if ":" in time_str
                    else str(int(time_str) % 100).zfill(2)
                )
                return f"{date_str} {hour}:{minute}"

        for data in [fc_data, cf_data]:
            if data:
                try:
                    first_field = data[0]
                    if hasattr(first_field, "metadata"):
                        base_time_meta = first_field.metadata("date")
                        time_meta = first_field.metadata("time")
                        return f"{base_time_meta} {time_meta // 100:02d}:{time_meta % 100:02d}"
                except Exception:
                    pass

        return "Unknown"

    def create_ensemble_stamp_plot(
        self,
        stamp_ds,
        parameter,
        step,
        size=None,
        palette_option=1,
        unit=None,
        max_cols=10,
        max_ensemble_members=50,
        regrid=True,
        target_resolution=0.1,
        precip_accumulation=None,
    ):
        """Create ensemble stamp plots with custom layout.

        Layout strategy:
            - Position 0: HRES (high-resolution forecast)
            - Position (max_cols-1): Control forecast
            - Remaining positions: Ensemble members

        Args:
            stamp_ds: Dictionary with 'fc' (deterministic), 'cf' (control),
                      'pf' (ensemble) forecast data
            parameter: Parameter name (e.g., 'msl', '10fg6', 'tp', '2t')
            step: Forecast step/lead time in hours
            size: Figure size (width, height) tuple, auto-calculated if None
            palette_option: Color palette option (1, 2, or 3)
            unit: Unit for data transformation ('celsius', 'kelvin', 'mm', 'm')
            max_cols: Maximum columns in grid layout
            max_ensemble_members: Maximum ensemble members to plot
            regrid: Whether to regrid reduced Gaussian grids to regular grids
            target_resolution: Target resolution in degrees for regridding
            precip_accumulation: Accumulation window in hours for precipitation
                parameters (tp/lsp/cp). Requires cumulative TP in the data.
                If None, raw field values are plotted (backward compatible).

        Returns:
            earthkit.plots.Figure object

        Raises:
            ValueError: If no data is available for the requested parameter/step
                (either no ensemble data at all, or no data of any kind).

        """
        model = self._extract_model_name(stamp_ds)
        style_config = self.style_config.choose_color_palette_and_levels(
            parameter, palette_option, unit
        )

        fc_data, cf_data, pf_data, fc_metadata, cf_metadata = (
            self._load_and_regrid_data(
                stamp_ds,
                parameter,
                step,
                max_ensemble_members,
                regrid,
                target_resolution,
                precip_accumulation=precip_accumulation,
            )
        )

        if fc_data and not cf_data and not pf_data:
            # FC is present but no ensemble data at this step.
            # Build a diagnostic summary of what steps ARE in CF/PF for this parameter.
            ens_step_info = []
            for key in ["cf", "pf"]:
                if key in stamp_ds:
                    try:
                        ds, _ = self._extract_dataset_and_metadata(stamp_ds[key])
                        steps_with_param = set()
                        for field in ds:
                            try:
                                if field.metadata("shortName") == parameter:
                                    sv = field.metadata("step")
                                    steps_with_param.add(int(sv) if sv is not None else None)
                            except Exception:
                                pass
                        ens_step_info.append(f"{key}: steps={sorted(s for s in steps_with_param if s is not None)[:20]}")
                    except Exception:
                        pass
            ens_diag = "; ".join(ens_step_info) if ens_step_info else "no ensemble datasets present"
            raise ValueError(
                f"No ensemble data (CF/PF) found for parameter={parameter!r} at step={step}. "
                f"Only the deterministic forecast (FC) has data at this step. "
                f"Ensemble steps available for this parameter: [{ens_diag}]. "
                f"Please select a step that is present in the ensemble data."
            )

        if not fc_data and not cf_data and not pf_data:
            # Collect diagnostic info about what IS in the data
            diag_parts = []
            for key in ["fc", "cf", "pf"]:
                if key in stamp_ds:
                    try:
                        ds, _ = self._extract_dataset_and_metadata(stamp_ds[key])
                        params_in_data = set()
                        steps_in_data = set()
                        for field in ds:
                            try:
                                params_in_data.add(field.metadata("shortName"))
                                steps_in_data.add(field.metadata("step"))
                            except Exception:
                                pass
                        diag_parts.append(
                            f"{key}: params={sorted(params_in_data)}, "
                            f"steps(sample)={sorted(steps_in_data)[:15]}"
                        )
                    except Exception:
                        pass
            sel_err_msg = "; ".join(self._last_sel_errors) if self._last_sel_errors else "unknown"
            diag_msg = " | ".join(diag_parts) if diag_parts else "no datasets present"
            raise ValueError(
                f"No data found for parameter={parameter!r}, step={step!r} "
                f"(type={type(step).__name__}). "
                f"Selection errors: [{sel_err_msg}]. "
                f"Data contents: [{diag_msg}]"
            )

        n_fc = 1 if fc_data else 0
        n_cf = 1 if cf_data else 0
        n_pf = len(pf_data)
        total_plots = n_fc + n_cf + n_pf
        nrows, ncols = self.calculate_optimal_grid(total_plots, max_cols)

        if size is None:
            width = min(max(ncols * 3.2 + 2.0, 16), 36)
            height = min(max(nrows * 2.8 + 3.0, 10), 24)
            size = (width, height)

        figure = earthkit.plots.Figure(size=size, rows=nrows, columns=ncols)

        try:
            if hasattr(figure, "fig") and figure.fig is not None:
                figure.fig.set_layout_engine(None)
                figure.fig.subplots_adjust(
                    top=0.77,
                    bottom=0.05,
                    left=0.02,
                    right=0.98,
                    hspace=0.45,
                    wspace=0.05,
                )
        except Exception:
            pass

        position_mapping = {}
        plot_data = []
        plot_labels = []

        if n_fc > 0:
            position_mapping[0] = len(plot_data)
            plot_data.append(fc_data[0])
            plot_labels.append(f"{model}")

        control_position = max_cols - 1
        if n_cf > 0:
            position_mapping[control_position] = len(plot_data)
            plot_data.append(cf_data[0])
            plot_labels.append("Control")

        current_position = 1
        for i, field in enumerate(pf_data):
            if current_position == control_position:
                current_position += 1
            position_mapping[current_position] = len(plot_data)
            plot_data.append(field)
            plot_labels.append(f"MEM {i + 1:02d}")
            current_position += 1

        transformed_data_0, transformed_levels = self.style_config.transform_data_and_levels(
            data=plot_data[0].to_xarray()
            if hasattr(plot_data[0], "to_xarray")
            else plot_data[0],
            parameter_name=parameter,
            levels=style_config["levels"],
            unit=unit,
            model_class=model,
        )

        # Transform ALL fields in plot_data (not just the first one).
        # transform_data_and_levels may apply unit conversions (e.g. Pa→hPa);
        # without this the data values fall outside the level range and nothing is drawn.
        transformed_plot_data = []
        for field in plot_data:
            src = field.to_xarray() if hasattr(field, "to_xarray") else field
            transformed_field, _ = self.style_config.transform_data_and_levels(
                data=src,
                parameter_name=parameter,
                levels=style_config["levels"],
                unit=unit,
                model_class=model,
            )
            transformed_plot_data.append(transformed_field)

        # For geopotential (m²/s² → m) and pressure (Pa → hPa) the data has already
        # been converted above. Strip the units attribute AND pass units=None to the
        # Style so earthkit does not attempt a second conversion via its internal
        # parameter tables (which would use GRIB_shortName to infer native units).
        if style_config.get("param_type") in ("geopotential", "pressure"):
            cleaned = []
            for da in transformed_plot_data:
                if isinstance(da, xr.DataArray) and hasattr(da, "attrs"):
                    da = da.copy()
                    da.attrs.pop("units", None)
                    da.attrs.pop("GRIB_units", None)
                elif isinstance(da, xr.Dataset):
                    da = da.copy()
                    for var in list(da.data_vars):
                        da[var].attrs.pop("units", None)
                        da[var].attrs.pop("GRIB_units", None)
                cleaned.append(da)
            transformed_plot_data = cleaned

        # For self-converted types (pressure, geopotential), pass units=None so
        # earthkit does not attempt to re-convert data that is already in the
        # target unit. The unit label still appears in the plot title below.
        _self_converted_types = {"geopotential", "pressure"}
        style_units = (
            None
            if style_config.get("param_type") in _self_converted_types
            else style_config["unit"]
        )
        plot_style = earthkit.plots.styles.Style(
            colors=style_config["colors"],
            levels=transformed_levels,
            units=style_units,
        )

        for position in position_mapping.keys():
            row, col = position // ncols, position % ncols
            figure.add_map(row, col)

        try:
            figure.contourf(transformed_plot_data, style=plot_style)
        except Exception as e:
            raise RuntimeError(
                f"earthkit contourf failed for parameter={parameter!r}, step={step}, "
                f"unit={unit}, n_fc={n_fc}, n_cf={n_cf}, n_pf={n_pf}: {e}"
            ) from e

        figure.land(color="lightgray")
        figure.coastlines(color="black", linewidth=1.5)
        figure.borders(color="white", linewidth=0.5)

        # Thin black contour lines separating colour bands (MSLP & geopotential)
        if style_config.get("draw_contour_lines", False):
            try:
                _map_axes = [
                    ax for ax in figure.fig.get_axes() if hasattr(ax, "projection")
                ]
                for i, (_pos, data_idx) in enumerate(position_mapping.items()):
                    if i >= len(_map_axes):
                        break
                    _ax = _map_axes[i]
                    _da = transformed_plot_data[data_idx]
                    # Normalise to a plain 2-D (lat × lon) numpy array
                    if isinstance(_da, xr.Dataset):
                        _da = _da[list(_da.data_vars)[0]]
                    if isinstance(_da, xr.DataArray):
                        # Drop any extra dims (step, valid_time, …)
                        _da = _da.squeeze(drop=True)
                        _lat = _da.coords.get(
                            "latitude", _da.coords.get("lat", None)
                        )
                        _lon = _da.coords.get(
                            "longitude", _da.coords.get("lon", None)
                        )
                        if _lat is not None and _lon is not None:
                            _ax.contour(
                                np.asarray(_lon),
                                np.asarray(_lat),
                                np.asarray(_da),
                                levels=transformed_levels,
                                colors="black",
                                linewidths=0.4,
                                transform=ccrs.PlateCarree(),
                            )
            except Exception:
                pass  # contour lines are cosmetic; never block the plot

        try:
            base_time_str = self._extract_base_time(
                fc_data, cf_data, fc_metadata, cf_metadata
            )
            unit_str = f" ({style_config['unit']})" if style_config["unit"] else ""
            ensemble_info = f" | {n_pf} Ensemble Members" if n_pf > 0 else ""
            _PRECIP_PARAMS = {"tp", "lsp", "cp"}
            if parameter in _PRECIP_PARAMS and precip_accumulation and precip_accumulation > 0:
                step_label = f"{precip_accumulation}h Accum ending T+{step}h"
            else:
                step_label = f"T+{step}h"
            main_title = f"{model} Ensemble Run: {base_time_str} UTC{ensemble_info}\n{style_config['title']}{unit_str} - {step_label}"

            if hasattr(figure, "fig") and figure.fig is not None:
                title_text = figure.fig.text(
                    0.5,
                    0.97,
                    main_title,
                    fontsize=42,
                    fontweight="bold",
                    ha="center",
                    va="top",
                )

                title_bbox = title_text.get_window_extent()
                fig_bbox = figure.fig.get_window_extent()
                colorbar_width = min(title_bbox.width / fig_bbox.width, 0.7)

                cbar_ax = figure.fig.add_axes(
                    [0.5 - colorbar_width / 2, 0.86, colorbar_width, 0.045]
                )
                figure.legend(ax=cbar_ax, orientation="horizontal")
                cbar_ax.tick_params(axis="x", labelsize=26, pad=4, rotation=45)
                cbar_ax.tick_params(
                    axis="y", which="both", left=False, right=False, labelleft=False
                )
                # Make the colorbar label (title) larger if present
                if cbar_ax.get_xlabel():
                    cbar_ax.set_xlabel(cbar_ax.get_xlabel(), fontsize=26)
        except Exception:
            try:
                if hasattr(figure, "fig") and figure.fig is not None:
                    figure.fig.suptitle(
                        main_title, fontsize=42, fontweight="bold", y=0.97
                    )
                    figure.legend(orientation="horizontal", location="bottom")
            except:  # noqa: E722
                pass

        try:
            if hasattr(figure, "fig") and figure.fig is not None:
                map_axes = [
                    ax for ax in figure.fig.get_axes() if hasattr(ax, "projection")
                ]
                for i, (position, data_index) in enumerate(position_mapping.items()):  # noqa: B007
                    if i < len(map_axes):
                        map_axes[i].set_title(
                            plot_labels[data_index],
                            fontsize=24,
                            fontweight="bold",
                            color="black",
                            pad=4,
                        )
        except Exception:
            pass

        return figure
