from typing import Any

import numpy as np
import xarray as xr


class GribResolutionExtractor:
    """Extract grid resolution information from ECMWF GRIB files."""

    def __init__(self):  # noqa: D107
        pass

    def get_resolution_from_xarray(self, data: xr.DataArray) -> dict[str, Any]:
        """Extract resolution from xarray DataArray (most common method)."""
        resolution_info = {}

        if "latitude" in data.coords:
            lats = data.coords["latitude"].values
            lons = data.coords["longitude"].values
        elif "lat" in data.coords:
            lats = data.coords["lat"].values
            lons = data.coords["lon"].values
        else:
            raise ValueError("Cannot find latitude/longitude coordinates")

        lat_resolution = abs(lats[1] - lats[0]) if len(lats) > 1 else 0
        lon_resolution = abs(lons[1] - lons[0]) if len(lons) > 1 else 0

        nlats = len(lats)
        nlons = len(lons)

        lat_res_km = lat_resolution * 111.32  # 1 degree ≈ 111.32 km
        lon_res_km = lon_resolution * 111.32 * np.cos(np.radians(np.mean(lats)))

        resolution_info = {
            "lat_resolution_deg": lat_resolution,
            "lon_resolution_deg": lon_resolution,
            "lat_resolution_km": lat_res_km,
            "lon_resolution_km": lon_res_km,
            "grid_shape": (nlats, nlons),
            "total_points": nlats * nlons,
            "lat_range": (float(lats.min()), float(lats.max())),
            "lon_range": (float(lons.min()), float(lons.max())),
        }

        return resolution_info

    def get_resolution_from_earthkit(self, data) -> dict[str, Any]:
        """Extract resolution from earthkit data source."""
        resolution_info = {}

        try:
            if hasattr(data, "to_xarray"):
                xr_data = data.to_xarray()
                return self.get_resolution_from_xarray(xr_data)

            if hasattr(data, "metadata"):
                metadata = data.metadata()

                if "iDirectionIncrement" in metadata:
                    lon_resolution = metadata["iDirectionIncrement"] / 1000000.0
                if "jDirectionIncrement" in metadata:
                    lat_resolution = metadata["jDirectionIncrement"] / 1000000.0

                resolution_info.update(
                    {
                        "lat_resolution_deg": lat_resolution,
                        "lon_resolution_deg": lon_resolution,
                        "lat_resolution_km": lat_resolution * 111.32,
                        "lon_resolution_km": lon_resolution * 111.32,
                    }
                )

        except Exception as e:
            print(f"Could not extract resolution from earthkit: {e}")

        return resolution_info

    def get_resolution_from_grib_metadata(self, data) -> dict[str, Any]:
        """Extract resolution from GRIB metadata using cfgrib/earthkit."""
        resolution_info = {}

        try:
            if hasattr(data, "attrs"):
                attrs = data.attrs

                grib_keys = [
                    "GRIB_iDirectionIncrementInDegrees",
                    "GRIB_jDirectionIncrementInDegrees",
                    "GRIB_DxInMetres",
                    "GRIB_DyInMetres",
                    "GRIB_gridType",
                    "GRIB_Nx",
                    "GRIB_Ny",
                ]

                for key in grib_keys:
                    if key in attrs:
                        resolution_info[key] = attrs[key]

                if "GRIB_iDirectionIncrementInDegrees" in attrs:
                    resolution_info["lon_resolution_deg"] = attrs[
                        "GRIB_iDirectionIncrementInDegrees"
                    ]
                if "GRIB_jDirectionIncrementInDegrees" in attrs:
                    resolution_info["lat_resolution_deg"] = attrs[
                        "GRIB_jDirectionIncrementInDegrees"
                    ]

        except Exception as e:
            print(f"Could not extract GRIB metadata: {e}")

        return resolution_info

    def determine_optimal_grid_resolution(
        self, data: xr.DataArray, min_points: int = 100, max_points: int = 1000
    ) -> int:
        """Determine optimal grid resolution for interpolation based on data resolution."""
        resolution_info = self.get_resolution_from_xarray(data)

        native_nlats, native_nlons = resolution_info["grid_shape"]

        target_factor = 3

        optimal_lat_points = min(
            max(native_nlats * target_factor, min_points), max_points
        )
        optimal_lon_points = min(
            max(native_nlons * target_factor, min_points), max_points
        )

        optimal_resolution = min(optimal_lat_points, optimal_lon_points)

        print(f"Native grid: {native_nlats}x{native_nlons}")
        print(
            f"Recommended interpolation grid: {optimal_resolution}x{optimal_resolution}"
        )
        print(
            f"Native resolution: {resolution_info['lat_resolution_deg']:.3f}° x {resolution_info['lon_resolution_deg']:.3f}°"
        )
        print(
            f"Approximate resolution: {resolution_info['lat_resolution_km']:.1f}km x {resolution_info['lon_resolution_km']:.1f}km"
        )

        return optimal_resolution

    def get_comprehensive_resolution_info(self, data) -> dict[str, Any]:
        """Get comprehensive resolution information using all available methods."""
        all_info = {}

        try:
            if isinstance(data, xr.DataArray):
                xr_info = self.get_resolution_from_xarray(data)
                all_info.update(xr_info)
                all_info["source"] = "xarray"
            elif hasattr(data, "to_xarray"):
                xr_data = data.to_xarray()
                xr_info = self.get_resolution_from_xarray(xr_data)
                all_info.update(xr_info)
                all_info["source"] = "xarray_converted"
        except Exception as e:
            print(f"XArray method failed: {e}")

        try:
            ek_info = self.get_resolution_from_earthkit(data)
            if ek_info:
                all_info.update(ek_info)
                if "source" not in all_info:
                    all_info["source"] = "earthkit"
        except Exception as e:
            print(f"Earthkit method failed: {e}")

        try:
            grib_info = self.get_resolution_from_grib_metadata(data)
            if grib_info:
                all_info.update(grib_info)
                if "source" not in all_info:
                    all_info["source"] = "grib_metadata"
        except Exception as e:
            print(f"GRIB metadata method failed: {e}")

        return all_info
