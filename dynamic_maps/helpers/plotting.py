import warnings  # noqa: I001
from datetime import datetime
from typing import Any

import earthkit as ek
import geoviews.feature as gf
import hvplot.xarray  # noqa: F401
import numpy as np
import xarray as xr
from matplotlib.colors import ListedColormap
from scipy.interpolate import griddata

from .styling_config import StylingConfiguration

warnings.filterwarnings(
    "ignore", message=".*option not found for quadmesh plot with bokeh.*"
)


class SurfaceVariablesMapsRender:
    """Render surface variable maps with support for reduced Gaussian grids."""

    def __init__(self):
        """Initialize the renderer."""
        self.style_config = StylingConfiguration()

    def _detect_grid_type(self, data):  # noqa: PLR0912
        """Detect if data is on a reduced Gaussian grid.

        Returns:
            tuple: (is_reduced_grid, grid_spec)

        """
        if isinstance(data, xr.DataArray | xr.Dataset):
            attrs = data.attrs if isinstance(data, xr.DataArray) else data.attrs

            if "grid_type" in attrs and attrs["grid_type"] in [
                "reduced_gg",
                "reduced_ll",
            ]:
                grid_spec = None
                if "grid_N" in attrs:
                    n_value = attrs["grid_N"]
                    is_octahedral = attrs.get("is_octahedral", 0)
                    if is_octahedral:
                        grid_spec = {"grid": f"O{n_value}"}
                    else:
                        grid_spec = {"grid": f"N{n_value}"}
                return True, grid_spec

        if hasattr(data, "metadata"):
            try:
                first_field = data[0] if hasattr(data, "__getitem__") else data
                grid_type = first_field.metadata("gridType")

                if grid_type in ["reduced_gg", "reduced_ll"]:
                    try:
                        n_value = first_field.metadata("N")
                        is_octahedral = first_field.metadata("isOctahedral", default=0)
                        if is_octahedral:
                            grid_spec = {"grid": f"O{n_value}"}
                        else:
                            grid_spec = {"grid": f"N{n_value}"}
                        return True, grid_spec
                    except:  # noqa: E722
                        return True, None

            except Exception as e:
                print(f"Could not detect grid type from GRIB: {e}")

        if isinstance(data, xr.DataArray | xr.Dataset):
            if "latitude" in data.coords and "longitude" in data.coords:
                lat_vals = data.coords["latitude"].values
                lon_vals = data.coords["longitude"].values

                if lat_vals.ndim > 1 or lon_vals.ndim > 1:
                    return True, None

                if hasattr(data, "dims") and len(data.dims) > 0:
                    if "values" in data.dims or "rgrid" in data.dims:
                        return True, None

        return False, None

    def _regrid_to_regular(self, data, parameter_name, target_resolution=0.25):  # noqa: D417
        """Regrid reduced Gaussian grid data to a regular lat-lon grid.
        Uses nearest-neighbor interpolation and preserves data bounds.

        Parameters
        ----------
            data: Input data on reduced Gaussian grid
            parameter_name: Name of the parameter to extract
            target_resolution: Target grid resolution in degrees

        Returns
        -------
            xr.DataArray on regular grid

        """  # noqa: D205
        if hasattr(data, "metadata") and hasattr(data, "to_xarray"):
            try:
                data = data.to_xarray()
            except Exception as e:
                print(f"Error converting GRIB to xarray: {e}")
                raise

        if isinstance(data, xr.Dataset):
            if parameter_name in data.data_vars:
                data = data[parameter_name]
            else:
                data = data[list(data.data_vars.keys())[0]]

        df = data.to_dataframe().reset_index()

        if "lon" in df.columns and "longitude" not in df.columns:
            df = df.rename(columns={"lon": "longitude"})
        if "lat" in df.columns and "latitude" not in df.columns:
            df = df.rename(columns={"lat": "latitude"})

        value_col = data.name if data.name else parameter_name
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
                ]:
                    value_col = col
                    break

        df = df.dropna(subset=["longitude", "latitude", value_col])

        lon_min = df["longitude"].min()
        lon_max = df["longitude"].max()
        lat_min = df["latitude"].min()
        lat_max = df["latitude"].max()

        buffer = target_resolution * 0.5
        target_lons = np.arange(
            lon_min - buffer, lon_max + buffer + target_resolution, target_resolution
        )
        target_lats = np.arange(
            lat_max + buffer, lat_min - buffer - target_resolution, -target_resolution
        )

        points = df[["longitude", "latitude"]].values
        values = df[value_col].values

        lon_grid, lat_grid = np.meshgrid(target_lons, target_lats)

        interpolated = griddata(points, values, (lon_grid, lat_grid), method="nearest")

        result = xr.DataArray(
            interpolated,
            coords={"latitude": target_lats, "longitude": target_lons},
            dims=["latitude", "longitude"],
            name=parameter_name,
        )

        if hasattr(data, "attrs"):
            result.attrs = data.attrs.copy()

        return result

    def plot_dynamic_maps(  # noqa: PLR0912, PLR0913, PLR0915
        self,
        data,
        parameter_name,
        unit=None,
        palette_color=None,
        step=None,
        opacity=0.6,
        zoom_level=5,
        height=600,
        width=None,
        calculated_data=None,
        regrid=True,
        target_resolution=0.25,
    ):
        """Create an interactive dynamic map plot for a single forecast step.

        Args:
            data: earthkit/xarray dataset or DataArray for the parameter.
            parameter_name: Short name of the parameter to plot (e.g. "2t", "tp").
            unit: Optional display unit; defaults to the parameter's native unit.
            palette_color: Optional colorscale palette option (1, 2, or 3).
            step: Optional forecast step to select if the data has a step dimension.
            opacity: Layer opacity (0-1).
            zoom_level: Initial map zoom level.
            height: Plot height in pixels.
            width: Optional plot width in pixels (auto if None).
            calculated_data: Optional dict of calculated variables (e.g. wind
                speed, accumulated precipitation) keyed by parameter name,
                used instead of `data` when `parameter_name` is present in it.
            regrid: Whether to regrid reduced Gaussian grids to a regular grid.
            target_resolution: Target resolution in degrees when regridding.

        Returns:
            hvplot/holoviews dynamic map object.

        """
        date = None
        time = None

        if calculated_data and parameter_name in calculated_data:
            calc_data = calculated_data[parameter_name]

            if isinstance(calc_data, xr.DataArray):
                data = calc_data
                date = calc_data.attrs.get("date")
                time = calc_data.attrs.get("time")

                if step is not None and hasattr(data, "dims") and "step" in data.dims:
                    available_steps = data.coords["step"].values
                    if step in available_steps:
                        data = data.sel(step=step)
                    else:
                        data = data.isel(step=0)
                is_reduced, _ = self._detect_grid_type(data)
                if is_reduced and regrid:
                    data = self._regrid_to_regular(
                        data, parameter_name, target_resolution=target_resolution
                    )

            elif isinstance(calc_data, xr.Dataset):
                if parameter_name in calc_data.data_vars:
                    data = calc_data[parameter_name]
                else:
                    first_var = list(calc_data.data_vars.keys())[0]
                    data = calc_data[first_var]

                for attr in ["grid_type", "grid_N", "is_octahedral"]:
                    if attr in calc_data.attrs:
                        data.attrs[attr] = calc_data.attrs[attr]

                date = calc_data.attrs.get("date")
                time = calc_data.attrs.get("time")

                if step is not None and hasattr(data, "dims") and "step" in data.dims:
                    available_steps = data.coords["step"].values
                    if step in available_steps:
                        data = data.sel(step=step)
                    else:
                        data = data.isel(step=0)
                is_reduced, _ = self._detect_grid_type(data)
                if is_reduced and regrid:
                    data = self._regrid_to_regular(
                        data, parameter_name, target_resolution=target_resolution
                    )
        elif isinstance(data, xr.DataArray | xr.Dataset):
            date = data.attrs.get("date")
            time = data.attrs.get("time")
            if step is not None:
                idx = np.where(data["step"].values == step)[0][0]
                data = data[parameter_name][idx]
            else:
                data = data[parameter_name]
        else:
            try:
                if step is not None:
                    field = data.sel(param=parameter_name, step=step)[0]
                else:
                    field = data.sel(param=parameter_name)[0]

                date = field.metadata("date")
                time = field.metadata("time")

                is_reduced, grid_spec = self._detect_grid_type(data)

                if is_reduced and regrid:
                    if step is not None:
                        field_data = data.sel(param=parameter_name, step=step)
                    else:
                        field_data = data.sel(param=parameter_name)

                    data = self._regrid_to_regular(
                        field_data, parameter_name, target_resolution=target_resolution
                    )
                elif step is not None:
                    data = data.sel(param=parameter_name, step=step).to_xarray()
                else:
                    data = data.sel(param=parameter_name).to_xarray()

            except Exception as e:
                print(f"Error processing data: {e}")
                try:
                    first_field = data[0]
                    date = first_field.metadata("date")
                    time = first_field.metadata("time")
                except:  # noqa: E722
                    print("DEBUG: Could not extract date/time from GRIB")

        try:
            if date is not None:
                date_str = datetime.strptime(str(date), "%Y%m%d").strftime("%Y-%m-%d")
            else:
                date_str = "Unknown"
        except (ValueError, TypeError):
            date_str = str(date) if date is not None else "Unknown"

        try:
            if time is not None:
                time_str = f"{int(time):02d}:00"
            else:
                time_str = "00:00"
        except (ValueError, TypeError):
            time_str = "00:00"

        step_str = f" (T+{step}H)" if step is not None else ""

        if hasattr(data, "to_xarray"):
            data = data.to_xarray()

        def fix_coordinates(data):
            dims = list(data.dims)
            if "lat" in dims and "latitude" not in dims:
                data = data.rename({"lat": "latitude"})
            if "lon" in dims and "longitude" not in dims:
                data = data.rename({"lon": "longitude"})
            return data

        data = fix_coordinates(data)

        if "latitude" in data.coords:
            lat_vals = data.coords["latitude"].values
            lon_vals = data.coords["longitude"].values

            if abs(lat_vals.max()) < 10:  # noqa: PLR2004
                if abs(lat_vals.max()) < 1:
                    for scale_factor in [100, 1000, 57.2958]:
                        test_lat = lat_vals * scale_factor
                        test_lon = lon_vals * scale_factor

                        if (
                            -90 <= test_lat.min()  # noqa: PLR2004
                            and test_lat.max() <= 90  # noqa: PLR2004
                            and -180 <= test_lon.min()  # noqa: PLR2004
                            and test_lon.max() <= 180  # noqa: PLR2004
                        ):
                            data = data.assign_coords(
                                {
                                    "latitude": data.coords["latitude"] * scale_factor,
                                    "longitude": data.coords["longitude"]
                                    * scale_factor,
                                }
                            )
                            break

        config = self.style_config.choose_color_palette_and_levels(
            parameter_name=parameter_name, palette_color=palette_color, unit=unit
        )

        transformed_data, transformed_levels = (
            self.style_config.transform_data_and_levels(
                data=data,
                parameter_name=parameter_name,
                levels=config["levels"],
                unit=unit,
            )
        )

        transformed_data = fix_coordinates(transformed_data)
        config["levels"] = transformed_levels

        hex_colors = self.style_config._rgb_to_hex_colors(config["colors"])

        if len(hex_colors) < len(transformed_levels) - 1:
            hex_colors = (
                hex_colors * ((len(transformed_levels) - 1) // len(hex_colors) + 1)
            )[: len(transformed_levels) - 1]
        elif len(hex_colors) > len(transformed_levels) - 1:
            hex_colors = hex_colors[: len(transformed_levels) - 1]

        if isinstance(transformed_data, xr.DataArray):
            df_plot = transformed_data.to_dataframe().reset_index().dropna()
            value_col = (
                transformed_data.name if transformed_data.name else parameter_name
            )
        else:
            df_plot = transformed_data.to_dataframe().reset_index().dropna()
            value_col = parameter_name

        if parameter_name in ["tp", "lsp", "acc_tp", "cp", "acc_cp", "acc_lsp"]:
            df_plot = df_plot[df_plot[value_col] > 0]

        grid_data = df_plot.pivot_table(
            index="latitude", columns="longitude", values=value_col, fill_value=np.nan
        )

        grid_xr = xr.DataArray(
            grid_data.values,
            coords={
                "latitude": ("latitude", grid_data.index.values),
                "longitude": ("longitude", grid_data.columns.values),
            },
            dims=["latitude", "longitude"],
            name=value_col,
        )

        grid_xr.coords["longitude"].attrs["units"] = "°"
        grid_xr.coords["latitude"].attrs["units"] = "°"
        grid_xr.attrs["units"] = config["unit"]

        rgb_colors = []
        for hex_color in hex_colors:
            hex_color = hex_color.lstrip("#")  # noqa: PLW2901
            rgb = tuple(int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
            rgb_colors.append(rgb)

        custom_cmap = ListedColormap(rgb_colors, name="custom_weather_cmap")

        geo_quadmesh_options = {
            "x": "longitude",
            "y": "latitude",
            "cmap": custom_cmap,
            "colorbar": True,
            "clabel": f"{config['label']} ({config['unit']})",
            "alpha": opacity,
            "geo": True,
            "coastline": True,
            "projection": "PlateCarree",
            "global_extent": False,
            "title": f"{config['title']}\nBase time: {time_str} on {date_str}{step_str}",
            "tools": ["hover", "pan", "wheel_zoom", "box_zoom", "reset"],
            "frame_width": width if width else 1200,
            "frame_height": height if height else 700,
            "aspect": "equal",
            "data_aspect": 1,
            "hover_cols": ["longitude", "latitude", value_col],
            "xlabel": "Longitude (°)",
            "ylabel": "Latitude (°)",
            "levels": transformed_levels,
        }

        plot = grid_xr.hvplot.quadmesh(**geo_quadmesh_options)
        borders = gf.borders.opts(line_color="black", line_width=1)
        plot.opts(active_tools=["wheel_zoom"])
        final_plot = plot * borders

        return final_plot

    def plot_dynamic_multistep_maps(  # noqa: PLR0912, PLR0913, PLR0915
        self,
        data: xr.DataArray | xr.Dataset,
        parameter_name: str,
        steps: list[int] | None = None,
        unit: str | None = None,
        palette_color: int | None = None,
        zoom_level: int = 5,
        opacity: float = 0.6,
        height: int = 600,
        width: int = None,
        regrid: bool = True,
        target_resolution: float = 0.25,
    ):
        """Create multistep hvplot maps with working animation and reduced grid support."""
        date = None
        time = None

        is_reduced, grid_spec = self._detect_grid_type(data)

        if isinstance(data, xr.DataArray | xr.Dataset):
            date = data.attrs.get("date")
            time = data.attrs.get("time")
            if steps is None:
                steps = [int(step) for step in data["step"].values]
        else:
            first_field = data.sel(param=parameter_name)[0]
            date = first_field.metadata("date")
            time = first_field.metadata("time")

            if steps is None:
                steps = set()
                for field in data.sel(param=parameter_name):
                    steps.add(field.metadata("step"))
                steps = sorted(steps)

        date_str = datetime.strptime(str(date), "%Y%m%d").strftime("%Y-%m-%d")
        time_str = f"{int(time):02d}:00"

        config = self.style_config.choose_color_palette_and_levels(
            parameter_name=parameter_name, palette_color=palette_color, unit=unit
        )

        def fix_coordinates(data_array):
            dims = list(data_array.dims)
            if "lat" in dims and "latitude" not in dims:
                data_array = data_array.rename({"lat": "latitude"})
            if "lon" in dims and "longitude" not in dims:
                data_array = data_array.rename({"lon": "longitude"})
            return data_array

        all_step_arrays = []

        for _i, step in enumerate(steps):
            if isinstance(data, xr.DataArray | xr.Dataset):
                idx = np.where(data["step"].values == step)[0][0]
                step_data = data[parameter_name][idx]

                if isinstance(data, xr.Dataset) and parameter_name in data.data_vars:
                    source_var = data[parameter_name]
                    for attr in ["grid_type", "grid_N", "is_octahedral"]:
                        if attr in source_var.attrs and attr not in step_data.attrs:
                            step_data.attrs[attr] = source_var.attrs[attr]

                is_step_reduced, _ = self._detect_grid_type(step_data)
                if is_step_reduced and regrid:
                    step_data = self._regrid_to_regular(
                        step_data,
                        parameter_name,
                        target_resolution=target_resolution,
                    )
            else:
                step_data_raw = data.sel(param=parameter_name, step=step)

                if is_reduced and regrid:
                    step_data = self._regrid_to_regular(
                        step_data_raw,
                        parameter_name,
                        target_resolution=target_resolution,
                    )
                else:
                    step_data = step_data_raw.to_xarray()

            step_data = fix_coordinates(step_data)

            if "latitude" in step_data.coords:
                lat_vals = step_data.coords["latitude"].values
                lon_vals = step_data.coords["longitude"].values
                if abs(lat_vals.max()) < 10:  # noqa: PLR2004
                    if abs(lat_vals.max()) < 1:
                        for scale_factor in [100, 1000, 57.2958]:
                            test_lat = lat_vals * scale_factor
                            test_lon = lon_vals * scale_factor
                            if (
                                -90 <= test_lat.min()  # noqa: PLR2004
                                and test_lat.max() <= 90  # noqa: PLR2004
                                and -180 <= test_lon.min()  # noqa: PLR2004
                                and test_lon.max() <= 180  # noqa: PLR2004
                            ):
                                step_data = step_data.assign_coords(
                                    {
                                        "latitude": step_data.coords["latitude"]
                                        * scale_factor,
                                        "longitude": step_data.coords["longitude"]
                                        * scale_factor,
                                    }
                                )
                                break

            transformed_data, transformed_levels = (
                self.style_config.transform_data_and_levels(
                    data=step_data,
                    parameter_name=parameter_name,
                    levels=config["levels"],
                    unit=unit,
                )
            )

            transformed_data = fix_coordinates(transformed_data)

            if isinstance(transformed_data, xr.DataArray):
                df_plot = transformed_data.to_dataframe().reset_index().dropna()
                value_col = (
                    transformed_data.name if transformed_data.name else parameter_name
                )
            else:
                df_plot = transformed_data.to_dataframe().reset_index().dropna()
                value_col = parameter_name

            if parameter_name in ["tp", "lsp", "acc_tp", "cp", "acc_cp", "acc_lsp"]:
                df_plot = df_plot[df_plot[value_col] > 0]

            if not df_plot.empty:
                grid_data = df_plot.pivot_table(
                    index="latitude",
                    columns="longitude",
                    values=value_col,
                    fill_value=np.nan,
                )

                grid_xr = xr.DataArray(
                    grid_data.values,
                    coords={
                        "latitude": ("latitude", grid_data.index.values),
                        "longitude": ("longitude", grid_data.columns.values),
                    },
                    dims=["latitude", "longitude"],
                    name=value_col,
                )
                grid_xr.coords["longitude"].attrs["units"] = "°"
                grid_xr.coords["latitude"].attrs["units"] = "°"
                grid_xr.attrs["units"] = config["unit"]

                grid_xr = grid_xr.expand_dims("time")
                grid_xr = grid_xr.assign_coords(time=[f"T+{step:02d}h"])

                all_step_arrays.append(grid_xr)

        if not all_step_arrays:
            raise ValueError("No valid data found for any steps")

        combined_data = xr.concat(all_step_arrays, dim="time")
        config["levels"] = transformed_levels

        hex_colors = self.style_config._rgb_to_hex_colors(config["colors"])
        if len(hex_colors) < len(transformed_levels) - 1:
            hex_colors = (
                hex_colors * ((len(transformed_levels) - 1) // len(hex_colors) + 1)
            )[: len(transformed_levels) - 1]
        elif len(hex_colors) > len(transformed_levels) - 1:
            hex_colors = hex_colors[: len(transformed_levels) - 1]

        rgb_colors = []
        for hex_color in hex_colors:
            hex_color = hex_color.lstrip("#")  # noqa: PLW2901
            rgb = tuple(int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
            rgb_colors.append(rgb)

        custom_cmap = ListedColormap(rgb_colors, name="custom_weather_cmap")

        hover_cols = ["longitude", "latitude"]
        data_var_name = combined_data.name or parameter_name
        if data_var_name:
            hover_cols.append(data_var_name)

        forecast_range = f"(T+{min(steps):02d}H to T+{max(steps):02d}H)"

        plot = combined_data.hvplot.quadmesh(
            x="longitude",
            y="latitude",
            groupby="time",
            cmap=custom_cmap,
            colorbar=True,
            clabel=f"{config['label']} ({config['unit']})",
            alpha=opacity,
            geo=True,
            coastline=True,
            projection="PlateCarree",
            global_extent=False,
            title=f"{parameter_name}\nBase time: {time_str} on {date_str}\nForecast range: {forecast_range}",
            tools=["hover", "pan", "wheel_zoom", "box_zoom", "reset"],
            levels=transformed_levels,
            frame_width=width if width else 1200,
            frame_height=height if height else 700,
            aspect="equal",
            data_aspect=1,
            widget_type="scrubber",
            widget_location="bottom",
            hover_cols=hover_cols,
            xlabel="Longitude (°)",
            ylabel="Latitude (°)",
        )

        return plot

    def plot_static_map(
        self,  # noqa: PLR0913
        data: Any,
        parameter_name: str,
        units: str | None = None,
        step: int | None = None,
        legend_location: str = "bottom",
    ):
        """Plot a weather parameter on a map.

        Parameters
        ----------
        data : Any
            The weather data containing the parameter to plot
        parameter_name : str
            Name of the parameter to plot (e.g., 'tp' for total precipitation)
        units : str, default None
            units for the parameter display
        step : int, default None
            Time step to select from the data
        legend_location : str, default "bottom"
            Location of the legend ("bottom", "top", "left", "right")

        """
        if step:
            data_subset = data.sel(param=parameter_name, step=step)
        else:
            data_subset = data.sel(param=parameter_name)
        chart = ek.plots.Map()
        chart.point_cloud(data_subset, units=units)
        chart.coastlines()
        chart.gridlines()
        chart.title()
        chart.legend(location=legend_location)

        chart.show()
