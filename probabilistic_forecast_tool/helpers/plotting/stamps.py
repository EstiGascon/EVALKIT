import math

import earthkit.plots  # type: ignore
import numpy as np
import xarray as xr
from helpers.styling_config import StylingConfiguration
from scipy.interpolate import griddata


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

    def _regrid_to_regular(self, data, parameter_name, target_resolution=0.25):
        """Regrid reduced Gaussian grid to regular lat-lon grid using nearest neighbor.

        Args:
            data: Input data on reduced Gaussian grid
            parameter_name: Name of parameter to extract
            target_resolution: Target grid resolution in degrees

        Returns:
            xr.DataArray on regular grid, or original data if regridding fails

        """
        try:
            if hasattr(data, "to_xarray"):
                data_xr = data.to_xarray()
            else:
                data_xr = data

            if isinstance(data_xr, xr.Dataset):
                data_xr = (
                    data_xr[parameter_name]
                    if parameter_name in data_xr.data_vars
                    else data_xr[list(data_xr.data_vars.keys())[0]]
                )

            df = data_xr.to_dataframe().reset_index()
            df = df.rename(columns={"lon": "longitude", "lat": "latitude"})

            value_col = data_xr.name if data_xr.name else parameter_name
            if value_col not in df.columns:
                for col in df.columns:
                    if col not in [
                        "longitude",
                        "latitude",
                        "lon",
                        "lat",
                        "step",
                        "time",
                        "valid_time",
                        "number",
                    ]:
                        value_col = col
                        break

            df = df.dropna(subset=["longitude", "latitude", value_col])

            if len(df) == 0:
                return data

            buffer = target_resolution * 0.5
            target_lons = np.arange(
                df["longitude"].min() - buffer,
                df["longitude"].max() + buffer + target_resolution,
                target_resolution,
            )
            target_lats = np.arange(
                df["latitude"].max() + buffer,
                df["latitude"].min() - buffer - target_resolution,
                -target_resolution,
            )

            points = df[["longitude", "latitude"]].values
            values = df[value_col].values
            lon_grid, lat_grid = np.meshgrid(target_lons, target_lats)
            interpolated = griddata(
                points, values, (lon_grid, lat_grid), method="nearest"
            )

            result = xr.DataArray(
                interpolated,
                coords={"latitude": target_lats, "longitude": target_lons},
                dims=["latitude", "longitude"],
                name=parameter_name,
            )

            if hasattr(data_xr, "attrs"):
                result.attrs = data_xr.attrs.copy()

            return result

        except Exception:
            return data

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
        self, stamp_ds, parameter, step, max_ensemble_members, regrid, target_resolution
    ):
        """Load forecast data and optionally regrid to regular grid.

        Args:
            stamp_ds: Dictionary with 'fc', 'cf', 'pf' forecast data
            parameter: Parameter name to extract
            step: Forecast step/lead time
            max_ensemble_members: Maximum ensemble members to load
            regrid: Whether to regrid reduced grids
            target_resolution: Target resolution for regridding

        Returns:
            Tuple of (fc_data, cf_data, pf_data, fc_metadata, cf_metadata)

        """
        fc_data, cf_data, pf_data = [], [], []
        fc_metadata, cf_metadata = {}, {}

        if "fc" in stamp_ds:
            try:
                fc_dataset, fc_metadata = self._extract_dataset_and_metadata(
                    stamp_ds["fc"]
                )
                fc_data = [fc_dataset.sel(step=step, shortName=parameter)]
            except Exception:
                pass

        if "cf" in stamp_ds:
            try:
                cf_dataset, cf_metadata = self._extract_dataset_and_metadata(
                    stamp_ds["cf"]
                )
                cf_data = [cf_dataset.sel(step=step, shortName=parameter)]
            except Exception:
                pass

        if "pf" in stamp_ds:
            try:
                pf_dataset, _ = self._extract_dataset_and_metadata(stamp_ds["pf"])
                pf_data = pf_dataset.sel(step=step, shortName=parameter)

                if (
                    max_ensemble_members is not None
                    and len(pf_data) > max_ensemble_members
                ):
                    pf_data = pf_data[:max_ensemble_members]
            except Exception:
                pass

        if regrid:
            if fc_data and self._detect_grid_type(fc_data[0]):
                fc_data = [
                    self._regrid_to_regular(fc_data[0], parameter, target_resolution)
                ]

            if cf_data and self._detect_grid_type(cf_data[0]):
                cf_data = [
                    self._regrid_to_regular(cf_data[0], parameter, target_resolution)
                ]

            if pf_data and self._detect_grid_type(pf_data[0]):
                regridded_pf = []
                for field in enumerate(pf_data):
                    regridded_pf.append(
                        self._regrid_to_regular(field, parameter, target_resolution)
                    )
                pf_data = regridded_pf

        return fc_data, cf_data, pf_data, fc_metadata, cf_metadata

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

        Returns:
            earthkit.plots.Figure object or None if no data available

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
            )
        )

        if not fc_data and not cf_data and not pf_data:
            return None

        n_fc = 1 if fc_data else 0
        n_cf = 1 if cf_data else 0
        n_pf = len(pf_data)
        total_plots = n_fc + n_cf + n_pf
        nrows, ncols = self.calculate_optimal_grid(total_plots, max_cols)

        if size is None:
            width = min(max(ncols * 2.8 + 1.5, 15), 30)
            height = min(max(nrows * 2.4 + 2.5, 8), 20)
            size = (width, height)

        figure = earthkit.plots.Figure(size=size, rows=nrows, columns=ncols)

        try:
            if hasattr(figure, "fig") and figure.fig is not None:
                figure.fig.set_layout_engine(None)
                figure.fig.subplots_adjust(
                    top=0.85,
                    bottom=0.05,
                    left=0.02,
                    right=0.98,
                    hspace=0.25,
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

        transformed_levels = self.style_config.transform_data_and_levels(
            data=plot_data[0].to_xarray()
            if hasattr(plot_data[0], "to_xarray")
            else plot_data[0],
            parameter_name=parameter,
            levels=style_config["levels"],
            unit=unit,
        )[1]

        plot_style = earthkit.plots.styles.Style(
            colors=style_config["colors"],
            levels=transformed_levels,
            units=style_config["unit"],
        )

        for position in position_mapping.keys():
            row, col = position // ncols, position % ncols
            figure.add_map(row, col)

        try:
            figure.contourf(plot_data, style=plot_style)
        except Exception:
            return None

        figure.land(color="lightgray")
        figure.coastlines(color="white", linewidth=1)
        figure.borders(color="white", linewidth=0.5)

        try:
            base_time_str = self._extract_base_time(
                fc_data, cf_data, fc_metadata, cf_metadata
            )
            unit_str = f" ({style_config['unit']})" if style_config["unit"] else ""
            ensemble_info = f" | {n_pf} Ensemble Members" if n_pf > 0 else ""
            main_title = f"{model} Ensemble Run: {base_time_str} UTC{ensemble_info}\n{style_config['title']}{unit_str} - T+{step}h"

            if hasattr(figure, "fig") and figure.fig is not None:
                title_text = figure.fig.text(
                    0.5,
                    0.96,
                    main_title,
                    fontsize=18,
                    fontweight="bold",
                    ha="center",
                    va="top",
                )

                title_bbox = title_text.get_window_extent()
                fig_bbox = figure.fig.get_window_extent()
                colorbar_width = min(title_bbox.width / fig_bbox.width, 0.6)

                cbar_ax = figure.fig.add_axes(
                    [0.5 - colorbar_width / 2, 0.88, colorbar_width, 0.02]
                )
                figure.legend(ax=cbar_ax, orientation="horizontal")
                cbar_ax.tick_params(axis="x", labelsize=10, pad=2, rotation=45)
                cbar_ax.tick_params(
                    axis="y", which="both", left=False, right=False, labelleft=False
                )
        except Exception:
            try:
                if hasattr(figure, "fig") and figure.fig is not None:
                    figure.fig.suptitle(
                        main_title, fontsize=18, fontweight="bold", y=0.95
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
                            plot_labels[data_index], fontsize=10, pad=3
                        )
        except Exception:
            pass

        return figure
