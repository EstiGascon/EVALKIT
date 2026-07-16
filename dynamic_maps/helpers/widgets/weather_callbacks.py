"""Weather data download callbacks module with map integration."""

import os
import re
import traceback

import ipyleaflet as L
from IPython.display import clear_output


class DataRetrieverCallbacks:
    """Class to handle surface variable data widget callbacks including map functionality."""

    def __init__(self, weather_widgets, retriever):
        """Initialize callbacks with widget and retriever instances."""
        self.weather_widgets = weather_widgets
        self.retriever = retriever
        self.downloaded_data = None
        self.ds = None
        self._executing = {
            "preview": False,
            "download": False,
            "load_file": False,
            "clear_map": False,
            "reset_map": False,
        }

    def _clear_existing_callbacks(self):
        """Clear existing callbacks to prevent duplicates."""
        buttons = [
            "preview_btn",
            "download_btn",
            "load_file_btn",
            "clear_map_btn",
            "reset_map_btn",
        ]
        for button_name in buttons:
            if button_name in self.weather_widgets.widgets:
                widget = self.weather_widgets.widgets[button_name]
                if hasattr(widget, "_click_handlers"):
                    widget._click_handlers.callbacks.clear()

    def on_preview_click(self, b):
        """Handle preview button click with duplicate prevention."""
        if self._executing["preview"]:
            return

        try:
            self._executing["preview"] = True
            self.weather_widgets.preview_settings()
        finally:
            self._executing["preview"] = False

    def on_clear_map_click(self, b):
        """Handle clear map button click with duplicate prevention."""
        if self._executing["clear_map"]:
            return

        try:
            self._executing["clear_map"] = True

            if (
                hasattr(self.weather_widgets, "draw_control")
                and self.weather_widgets.draw_control is not None
            ):
                try:
                    self.weather_widgets.draw_control.clear()
                    self._display_message(
                        """
                        <h4>Map Cleared</h4>
                        <p>All drawings have been removed from the map.</p>
                    """,
                        "success",
                    )
                except Exception as e:
                    self._display_message(
                        f"""
                        <h4>Error Clearing Map</h4>
                        <p><strong>Error:</strong> {str(e)}</p>
                        <p>Please try again or refresh the interface.</p>
                    """,
                        "error",
                    )
            else:
                self._display_message(
                    """
                    <h4>No Map to Clear</h4>
                    <p>Map drawing controls are not available or initialized.</p>
                """,
                    "warning",
                )

        finally:
            self._executing["clear_map"] = False

    def on_reset_map_click(self, b):
        """Handle reset map view button click with duplicate prevention."""
        if self._executing["reset_map"]:
            return

        try:
            self._executing["reset_map"] = True

            if (
                hasattr(self.weather_widgets, "map_widget")
                and self.weather_widgets.map_widget is not None
            ):
                try:
                    north = self.weather_widgets.widgets["north"].value
                    south = self.weather_widgets.widgets["south"].value
                    west = self.weather_widgets.widgets["west"].value
                    east = self.weather_widgets.widgets["east"].value

                    center_lat = (north + south) / 2
                    center_lon = (west + east) / 2

                    if not (-90 <= center_lat <= 90 and -180 <= center_lon <= 180):  # noqa: PLR2004
                        center_lat, center_lon = 53.0, 10.0

                    self.weather_widgets.map_widget.center = [center_lat, center_lon]
                    self.weather_widgets.map_widget.zoom = 4

                    self._display_message(
                        f"""
                        <h4>Map View Reset</h4>
                        <p>Map centered at: {center_lat:.2f}°N, {center_lon:.2f}°E</p>
                        <p>Zoom level reset to default.</p>
                    """,
                        "success",
                    )

                except Exception as e:
                    self._display_message(
                        f"""
                        <h4>Error Resetting Map</h4>
                        <p><strong>Error:</strong> {str(e)}</p>
                        <p>Please try again or check coordinate values.</p>
                    """,
                        "error",
                    )
            else:
                self._display_message(
                    """
                    <h4>No Map to Reset</h4>
                    <p>Map widget is not available or initialized.</p>
                """,
                    "warning",
                )

        finally:
            self._executing["reset_map"] = False

    def _display_message(self, message, message_type="info"):
        """Display messages in the correct info display widget based on current data source."""
        current_source = self.weather_widgets.widgets["data_source"].value

        if current_source == "local":
            widget_name = "local_info_display"
        else:
            widget_name = "mars_info_display"

        if widget_name in self.weather_widgets.widgets:
            bg_colors = {
                "error": "#ffe8e8",
                "success": "#e8f5e8",
                "info": "#e8f4fd",
                "warning": "#fff3cd",
            }

            bg_color = bg_colors.get(message_type, "#f8f9fa")

            border_colors = {
                "error": "#d32f2f",
                "success": "#2e7d32",
                "info": "#1976d2",
                "warning": "#f57c00",
            }

            border_color = border_colors.get(message_type, "#666")

            html_message = f"""
                <div style="background-color: {bg_color}; padding: 12px; border-radius: 8px; margin: 8px 0; border-left: 4px solid {border_color};">
                    {message}
                </div>
            """
            self.weather_widgets.widgets[widget_name].value = html_message
        else:
            with self.weather_widgets.widgets["output"]:
                plain_message = re.sub("<[^<]+?>", "", message)
                print(f"[{message_type.upper()}] {plain_message}")

    def on_download_click(self, b):
        """Handle download button click for MARS Archive data with duplicate prevention."""
        if self._executing["download"]:
            return

        try:
            self._executing["download"] = True

            with self.weather_widgets.widgets["output"]:
                clear_output()

            params = self.weather_widgets.get_parameters()

            if params["data_source"] == "local":
                self._display_message(
                    """
                    <h4>Data Source Mismatch</h4>
                    <p><strong>Issue:</strong> Download button is for MARS Archive data only.</p>
                    <p><strong>Solution:</strong> Use 'Load File' button for local files or switch to MARS Archive.</p>
                """,
                    "error",
                )
                return

            if not params["param"]:
                self._display_message(
                    """
                    <h4>No Parameters Selected</h4>
                    <p><strong>Issue:</strong> At least one weather parameter must be selected.</p>
                    <p><strong>Solution:</strong> Select one or more parameters from the Parameter Selection list.</p>
                """,
                    "error",
                )
                return

            if not params["selected_steps"]:
                self._display_message(
                    """
                    <h4>No Forecast Steps Selected</h4>
                    <p><strong>Issue:</strong> At least one forecast step must be selected.</p>
                    <p><strong>Solution:</strong> Select forecast steps or click 'Select All Steps' button.</p>
                """,
                    "error",
                )
                return

            area = params["area"]
            if area[0] <= area[2]:
                self._display_message(
                    f"""
                    <h4>Invalid Geographic Bounds</h4>
                    <p><strong>Issue:</strong> North boundary must be greater than South boundary.</p>
                    <p><strong>Current:</strong> North={area[0]:.2f}, South={area[2]:.2f}</p>
                """,
                    "error",
                )
                return

            if area[3] <= area[1]:
                self._display_message(
                    f"""
                    <h4>Invalid Geographic Bounds</h4>
                    <p><strong>Issue:</strong> East boundary must be greater than West boundary.</p>
                    <p><strong>Current:</strong> East={area[3]:.2f}, West={area[1]:.2f}</p>
                """,
                    "error",
                )
                return

            self._display_message(
                f"""
                <h4>Initiating MARS Archive Download</h4>
                <p><strong>Parameters:</strong> {", ".join(params["param"])}</p>
                <p><strong>Model:</strong> {params["model"]}</p>
                <p><strong>Date/Time:</strong> {params["date"]} at {params["time"]}</p>
                <p><strong>Forecast Steps:</strong> {len(params["selected_steps"])} steps ({min(params["selected_steps"])}-{max(params["selected_steps"])})</p>
                <p><strong>Geographic Area:</strong> N={area[0]}°, S={area[2]}°, W={area[1]}°, E={area[3]}°</p>
                <p>Connecting to MARS Archive... Please wait.</p>
            """,
                "info",
            )

            try:
                data = self.retriever.retrieve_surface_data(
                    param=params["param"],
                    date=params["date"],
                    time=params["time"],
                    model=params["model"],
                    area=params["area"],
                    grid=params["grid"],
                    step_list=params["selected_steps"],
                )

                self.downloaded_data = data
                self.ds = data["dataset"]

                globals()["downloaded_data"] = data
                globals()["ds"] = data["dataset"]

                total_points = len(params["param"]) * len(params["selected_steps"])
                area_size = abs(area[0] - area[2]) * abs(area[3] - area[1])

                self._display_message(
                    f"""
                    <h4>MARS Archive Download Complete!</h4>
                    <p><strong>Success Details:</strong></p>
                    <ul>
                        <li><strong>Parameters:</strong> {", ".join(params["param"])} ({len(params["param"])} total)</li>
                        <li><strong>Forecast Steps:</strong> {len(params["selected_steps"])} steps</li>
                        <li><strong>Total Data Points:</strong> {total_points:,}</li>
                        <li><strong>Geographic Coverage:</strong> {area_size:.1f} square degrees</li>
                        <li><strong>Data Source:</strong> {params["model"].upper()}</li>
                    </ul>
                    <p><strong>Ready for analysis!</strong> Your data is now loaded and available.</p>
                """,
                    "success",
                )

            except Exception as e:
                error_msg = str(e)

                if "authentication" in error_msg.lower():
                    guidance = (
                        "Check your MARS API credentials and authentication setup."
                    )
                elif (
                    "network" in error_msg.lower() or "connection" in error_msg.lower()
                ):
                    guidance = "Check your internet connection and try again."
                elif "parameter" in error_msg.lower():
                    guidance = "Verify that all selected parameters are valid for the chosen model and date."
                else:
                    guidance = "Check the error details below and verify your request parameters."

                self._display_message(
                    f"""
                    <h4>MARS Archive Download Failed</h4>
                    <p><strong>Error:</strong> {error_msg}</p>
                    <p><strong>Guidance:</strong> {guidance}</p>
                    <details>
                        <summary><strong>Click for full error traceback</strong></summary>
                        <pre style="background-color: #f8f9fa; padding: 10px; border-radius: 3px; overflow-x: auto; font-size: 0.9em; max-height: 300px; overflow-y: auto;">{traceback.format_exc()}</pre>
                    </details>
                    <p>Tip: Try adjusting your parameters or check the MARS Archive status.</p>
                """,
                    "error",
                )
        finally:
            self._executing["download"] = False

    def on_load_file_click(self, b):  # noqa: PLR0911, PLR0912, PLR0915
        """Handle load file button click for local files with path validation."""
        if self._executing["load_file"]:
            return

        try:
            self._executing["load_file"] = True

            with self.weather_widgets.widgets["output"]:
                clear_output()

                params = self.weather_widgets.get_parameters()

                if params["data_source"] != "local":
                    self._display_message(
                        """
                        <h4>Data Source Mismatch</h4>
                        <p><strong>Issue:</strong> Load File button is for local files only.</p>
                        <p><strong>Solution:</strong> Switch to 'Load Local File' option first.</p>
                    """,
                        "error",
                    )
                    return

                file_path = params["selected_file_path"]

                if not file_path:
                    self._display_message(
                        """
                        <h4>No File Path Provided</h4>
                        <p><strong>Issue:</strong> Please enter a file path in the text field above.</p>
                        <p><strong>Example:</strong> <code>/path/to/your/data.grib</code></p>
                        <p><strong>Tip:</strong> You can type the path directly or use the Browse button if available.</p>
                    """,
                        "error",
                    )
                    return

                file_path = file_path.strip()

                if not os.path.exists(file_path):
                    dir_path = os.path.dirname(file_path)
                    if os.path.exists(dir_path):
                        self._display_message(
                            f"""
                            <h4>File Not Found</h4>
                            <p><strong>Issue:</strong> The file does not exist in the specified location.</p>
                            <p><strong>Directory exists:</strong> {dir_path}</p>
                            <p><strong>Looking for:</strong> {os.path.basename(file_path)}</p>
                            <p><strong>Full path:</strong> {file_path}</p>
                            <p><strong>Solution:</strong> Check the filename and extension, or browse the directory.</p>
                        """,
                            "error",
                        )
                    else:
                        self._display_message(
                            f"""
                            <h4>Path Not Found</h4>
                            <p><strong>Issue:</strong> The directory or file path does not exist.</p>
                            <p><strong>Path:</strong> {file_path}</p>
                            <p><strong>Solution:</strong> Check the complete path or browse to select the correct location.</p>
                        """,
                            "error",
                        )
                    return

                if not os.path.isfile(file_path):
                    self._display_message(
                        f"""
                        <h4>Not a File</h4>
                        <p><strong>Issue:</strong> The path exists but points to a directory, not a file.</p>
                        <p><strong>Path:</strong> {file_path}</p>
                        <p><strong>Solution:</strong> Include the filename in your path.</p>
                    """,
                        "error",
                    )
                    return

                try:
                    with open(file_path, "rb") as f:
                        f.read(1)
                except PermissionError:
                    self._display_message(
                        f"""
                        <h4>Permission Denied</h4>
                        <p><strong>Issue:</strong> You don't have permission to read this file.</p>
                        <p><strong>File:</strong> {os.path.basename(file_path)}</p>
                        <p><strong>Solution:</strong> Check file permissions or contact your system administrator.</p>
                    """,
                        "error",
                    )
                    return
                except Exception as e:
                    self._display_message(
                        f"""
                        <h4>File Access Error</h4>
                        <p><strong>Issue:</strong> Cannot access the file.</p>
                        <p><strong>Error:</strong> {str(e)}</p>
                        <p><strong>File:</strong> {file_path}</p>
                    """,
                        "error",
                    )
                    return

                file_name = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                file_size_mb = file_size / (1024 * 1024)

                self._display_message(
                    f"""
                    <h4>✓ File Validated - Loading Data</h4>
                    <p><strong>File:</strong> {file_name}</p>
                    <p><strong>Size:</strong> {file_size_mb:.2f} MB</p>
                    <p><strong>Path:</strong> {file_path}</p>
                    <p>Reading file data... Please wait.</p>
                """,
                    "info",
                )

                try:
                    ds = self.retriever.load_source_file_data(file_path)

                    self.ds = ds
                    self.downloaded_data = {
                        "dataset": ds,
                        "metadata": {
                            "source": "local_file",
                            "file_path": file_path,
                            "data_source": "local",
                            "filename": file_name,
                            "file_size_mb": file_size_mb,
                        },
                    }

                    globals()["ds"] = ds
                    globals()["downloaded_data"] = self.downloaded_data
                    globals()["loaded_file_data"] = ds

                    bbox_info = self._extract_and_display_study_area(ds, file_name)

                    success_message = f"""
                        <h4>✓ Local File Loaded Successfully!</h4>
                        <p><strong>File Details:</strong></p>
                        <ul>
                            <li><strong>Filename:</strong> {file_name}</li>
                            <li><strong>Size:</strong> {file_size_mb:.2f} MB</li>
                            <li><strong>Source:</strong> Local file system</li>
                        </ul>
                        {bbox_info}
                        <p><strong>Ready for analysis!</strong> Your local file data is now loaded and available.</p>
                    """

                    self._display_message(success_message, "success")

                except Exception as e:
                    error_msg = str(e)

                    if any(ext in file_name.lower() for ext in [".grib", ".grb"]):
                        if (
                            "grib" in error_msg.lower()
                            or "eccodes" in error_msg.lower()
                        ):
                            format_guidance = "GRIB file format issue. Ensure the file is a valid GRIB file and eccodes is properly installed."
                        else:
                            format_guidance = "Ensure the GRIB file is not corrupted and contains valid weather data."
                    elif any(ext in file_name.lower() for ext in [".nc", ".netcdf"]):
                        format_guidance = "NetCDF file issue. Verify the file structure and ensure netCDF4 library is available."
                    elif any(ext in file_name.lower() for ext in [".hdf", ".h5"]):
                        format_guidance = "HDF5 file issue. Check the file format and ensure h5py library is available."
                    else:
                        format_guidance = "File format may not be supported. Ensure the file is a valid GRIB, NetCDF, or HDF5 file."

                    self._display_message(
                        f"""
                        <h4>Error Loading File</h4>
                        <p><strong>File:</strong> {file_name}</p>
                        <p><strong>Path:</strong> {file_path}</p>
                        <p><strong>Error:</strong> {error_msg}</p>
                        <p><strong>Format Guidance:</strong> {format_guidance}</p>
                        <details>
                            <summary><strong>Click for full error traceback</strong></summary>
                            <pre style="background-color: #f8f9fa; padding: 10px; border-radius: 3px; overflow-x: auto; font-size: 0.9em; max-height: 300px; overflow-y: auto;">{traceback.format_exc()}</pre>
                        </details>
                        <p><strong>Tips:</strong></p>
                        <ul>
                            <li>Verify the file is not corrupted</li>
                            <li>Check that you have the required libraries installed</li>
                            <li>Try a different file or contact support if the issue persists</li>
                        </ul>
                    """,
                        "error",
                    )
        finally:
            self._executing["load_file"] = False

    def get_dataset(self):
        """Get the downloaded dataset."""
        return self.ds

    def get_data(self):
        """Get the full downloaded data dictionary."""
        return self.downloaded_data

    def get_data_source(self):
        """Get the current data source type."""
        if self.downloaded_data and "metadata" in self.downloaded_data:
            return self.downloaded_data["metadata"].get("data_source", "unknown")
        return None

    def is_data_loaded(self):
        """Check if any data is currently loaded."""
        return self.ds is not None

    def get_data_info(self):
        """Get summary information about the loaded data."""
        if not self.is_data_loaded():
            return None

        info = {
            "has_data": True,
            "data_source": self.get_data_source(),
            "dataset_type": type(self.ds).__name__,
        }

        if self.downloaded_data and "metadata" in self.downloaded_data:
            info.update(self.downloaded_data["metadata"])

        return info

    def clear_data(self):
        """Clear all loaded data and reset the callback state."""
        self.ds = None
        self.downloaded_data = None

        self._executing = {
            "preview": False,
            "download": False,
            "load_file": False,
            "clear_map": False,
            "reset_map": False,
        }

        for var_name in ["ds", "downloaded_data", "loaded_file_data"]:
            if var_name in globals():
                del globals()[var_name]

        if hasattr(self.weather_widgets, "widgets"):
            if "local_info_display" in self.weather_widgets.widgets:
                self.weather_widgets.widgets["local_info_display"].value = ""
            if "mars_info_display" in self.weather_widgets.widgets:
                self.weather_widgets.widgets["mars_info_display"].value = ""

            if "output" in self.weather_widgets.widgets:
                with self.weather_widgets.widgets["output"]:
                    clear_output()

    def reinitialize_callbacks(self):
        """Reinitialize callbacks if needed."""
        self._clear_existing_callbacks()
        self._executing = {
            "preview": False,
            "download": False,
            "load_file": False,
            "clear_map": False,
            "reset_map": False,
        }

    def get_map_widget(self):
        """Get the map widget if available."""
        if hasattr(self.weather_widgets, "map_widget"):
            return self.weather_widgets.map_widget
        return None

    def get_draw_control(self):
        """Get the draw control if available."""
        if hasattr(self.weather_widgets, "draw_control"):
            return self.weather_widgets.draw_control
        return None

    def _extract_and_display_study_area(self, ds, file_name):
        """Extract bounding box from dataset, display rectangle on map, and update coordinate widgets."""
        try:
            first_field = ds[0] if hasattr(ds, "__getitem__") and len(ds) > 0 else ds

            west = first_field.metadata("longitudeOfFirstGridPointInDegrees")
            east = first_field.metadata("longitudeOfLastGridPointInDegrees")
            north = first_field.metadata("latitudeOfFirstGridPointInDegrees")
            south = first_field.metadata("latitudeOfLastGridPointInDegrees")

            bbox = {
                "west": min(west, east),
                "east": max(west, east),
                "north": max(north, south),
                "south": min(north, south),
            }

            self.weather_widgets.widgets["north"].value = bbox["north"]
            self.weather_widgets.widgets["south"].value = bbox["south"]
            self.weather_widgets.widgets["west"].value = bbox["west"]
            self.weather_widgets.widgets["east"].value = bbox["east"]

            if (
                hasattr(self.weather_widgets, "map_widget")
                and self.weather_widgets.map_widget is not None
            ):
                try:
                    rectangle_bounds = [
                        [bbox["south"], bbox["west"]],
                        [bbox["north"], bbox["east"]],
                    ]

                    rectangle = L.Rectangle(
                        bounds=rectangle_bounds,
                        color="#6883c5",
                        fill_color="#6883c5",
                        fill_opacity=0.2,
                        weight=2,
                    )

                    self.weather_widgets.map_widget.add_layer(rectangle)

                    center_lat = (bbox["north"] + bbox["south"]) / 2
                    center_lon = (bbox["west"] + bbox["east"]) / 2
                    self.weather_widgets.map_widget.center = [center_lat, center_lon]

                    lat_range = abs(bbox["north"] - bbox["south"])
                    lon_range = abs(bbox["east"] - bbox["west"])
                    max_range = max(lat_range, lon_range)

                    if max_range > 50:  # noqa: PLR2004
                        zoom_level = 3
                    elif max_range > 20:  # noqa: PLR2004
                        zoom_level = 4
                    elif max_range > 10:  # noqa: PLR2004
                        zoom_level = 5
                    else:
                        zoom_level = 6

                    self.weather_widgets.map_widget.zoom = zoom_level

                except Exception as e:
                    print(f"Warning: Could not add study area rectangle to map: {e}")

            return f"""
                <p><strong>Study Area Extracted and Applied:</strong></p>
                <ul>
                    <li>North: {bbox["north"]:.2f}°</li>
                    <li>South: {bbox["south"]:.2f}°</li>
                    <li>West: {bbox["west"]:.2f}°</li>
                    <li>East: {bbox["east"]:.2f}°</li>
                    <li>Coverage: {abs(bbox["north"] - bbox["south"]):.2f}° × {abs(bbox["east"] - bbox["west"]):.2f}°</li>
                </ul>
                <p><em>Blue rectangle shows file coverage on map and coordinate widgets updated.</em></p>
            """

        except Exception as e:
            print(f"Warning: Could not extract study area from {file_name}: {e}")
            return """
                <p><strong>Study Area:</strong> Could not extract geographic bounds from file.</p>
                <p><em>Manual coordinate entry may be required.</em></p>
            """
