import glob
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point


class DateTimeExtractor:
    """Class for extracting and parsing datetime information from filenames."""

    @staticmethod
    def parse_filename_datetime(filename):
        """Extract datetime from filename.

        Args:
            filename: Name of the file containing datetime information

        Returns:
            datetime object extracted from the filename

        """
        datetime_str = filename.split("_")[-1].replace(".geo", "")

        year = int(datetime_str[:4])
        month = int(datetime_str[4:6])
        day = int(datetime_str[6:8])
        hour = int(datetime_str[8:10])

        return datetime(year, month, day, hour)

    @staticmethod
    def get_date_range_from_files(file_list):
        """Get start and end dates from a list of files.

        Args:
            file_list: List of file paths to extract datetimes from

        Returns:
            Tuple of (min_datetime, max_datetime) or (None, None) if no files

        """
        if not file_list:
            return None, None

        datetimes = []
        for filepath in file_list:
            filename = Path(filepath).name
            dt = DateTimeExtractor.parse_filename_datetime(filename)
            datetimes.append(dt)

        return min(datetimes), max(datetimes)


class GeoDataProcessor:
    """Class for processing meteorological geo data files."""

    @staticmethod
    def read_geo_file(filepath):  # noqa: PLR0912
        """Read a meteorological geo file and extract station data.

        Args:
            filepath: Path to the geo file

        Returns:
            List of dictionaries with station data including:
                - stnid: Station ID
                - latitude: Latitude of the station
                - longitude: Longitude of the station
                - elevation: Elevation of the station
                - value_0: param value (or NaN if missing)

        """
        data_lines = []
        data_started = False
        column_mapping = {}

        try:
            with open(filepath, encoding="utf-8") as file:
                for raw_line in file:
                    line = raw_line.strip()

                    if line.startswith("#COLUMNS"):
                        continue

                    if (
                        not column_mapping
                        and not line.startswith("#")
                        and line
                        and not data_started
                    ):
                        headers = line.split("\t")
                        column_mapping = {
                            header.strip(): i for i, header in enumerate(headers)
                        }
                        continue

                    if line.startswith("#DATA"):
                        data_started = True
                        continue

                    if (
                        data_started
                        and column_mapping
                        and not line.startswith("#")
                        and line
                    ):
                        parts = line.split("\t")
                        try:
                            row_data = {}

                            if "stnid" in column_mapping and column_mapping[
                                "stnid"
                            ] < len(parts):
                                row_data["stnid"] = parts[column_mapping["stnid"]]

                            if "latitude" in column_mapping and column_mapping[
                                "latitude"
                            ] < len(parts):
                                row_data["latitude"] = float(
                                    parts[column_mapping["latitude"]]
                                )

                            if "longitude" in column_mapping and column_mapping[
                                "longitude"
                            ] < len(parts):
                                row_data["longitude"] = float(
                                    parts[column_mapping["longitude"]]
                                )

                            if "elevation" in column_mapping and column_mapping[
                                "elevation"
                            ] < len(parts):
                                elevation_val = parts[column_mapping["elevation"]]
                                row_data["elevation"] = (
                                    float(elevation_val)
                                    if elevation_val != "3e+38"
                                    else np.nan
                                )
                            else:
                                row_data["elevation"] = np.nan

                            if "value_0" in column_mapping and column_mapping[
                                "value_0"
                            ] < len(parts):
                                value_0_val = parts[column_mapping["value_0"]]
                                row_data["value_0"] = (
                                    float(value_0_val)
                                    if value_0_val != "3e+38"
                                    else np.nan
                                )

                            for col_name in ["level", "date", "time"]:
                                if col_name in column_mapping and column_mapping[
                                    col_name
                                ] < len(parts):
                                    value = parts[column_mapping[col_name]]
                                    if col_name in ["level"]:
                                        row_data[col_name] = (
                                            int(value) if value != "3e+38" else np.nan
                                        )
                                    else:
                                        row_data[col_name] = value

                            if all(
                                key in row_data
                                for key in ["stnid", "latitude", "longitude", "value_0"]
                            ):
                                data_lines.append(row_data)

                        except (ValueError, IndexError, KeyError):
                            continue

            return data_lines
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            return []

    @staticmethod
    def get_geo_files(folder_path):
        """Search folder_path for files with '_obs_' in the filename and '.geo' extension, returning a sorted list of matching file paths.

        Args:
            folder_path (str or Path): Directory to search.

        Returns:
            list[str]: Sorted list of geo file paths.

        """
        geo_files = glob.glob(str(Path(folder_path) / "*_obs_*.geo"))
        geo_files.sort()
        return geo_files


class StationCreator:
    """Class for creating station metadata and GeoDataFrames."""

    def __init__(self, geo_processor=None, datetime_extractor=None):
        """Initialize with optional custom processors.

        Args:
            geo_processor: Custom GeoDataProcessor instance (optional)
            datetime_extractor: Custom DateTimeExtractor instance (optional)

        """
        self.geo_processor = geo_processor or GeoDataProcessor()
        self.datetime_extractor = datetime_extractor or DateTimeExtractor()

    def create_stations_geodataframe(self, param_folder_path, crs="EPSG:4326"):
        """Create a GeoDataFrame with station metadata from the first geo file.

        Args:
            param_folder_path: Path to folder containing a specific surface variable geo files
            crs: Coordinate reference system (default: WGS84)

        Returns:
            GeoDataFrame with columns: stnid, latitude, longitude, elevation, geometry

        """
        geo_files = self.geo_processor.get_geo_files(param_folder_path)

        if not geo_files:
            print("No geo files found!")
            return None

        first_file = geo_files[0]

        station_data = self.geo_processor.read_geo_file(first_file)

        if not station_data:
            print("No station data found!")
            return None

        df = pd.DataFrame(station_data)

        geometry = [
            Point(lon, lat)
            for lon, lat in zip(df["longitude"], df["latitude"], strict=False)
        ]

        gdf = gpd.GeoDataFrame(
            df[["stnid", "latitude", "longitude", "elevation"]],
            geometry=geometry,
            crs=crs,
        )

        gdf.set_index("stnid", inplace=True)

        return gdf
