"""Data Retriever UI Module with Integrated Map.

This module contains the UI for data retrieval with map functionality.
Map is positioned below grid resolution section for full horizontal width.
"""

import os
import platform
import tkinter as tk
import traceback
from datetime import date
from tkinter import filedialog

import ipywidgets as widgets
from helpers.parameter_mapper import ConfigurationManager
from IPython.display import clear_output, display

try:
    import ipyleaflet as L

    IPYLEAFLET_AVAILABLE = True
except ImportError:
    IPYLEAFLET_AVAILABLE = False
    print("Warning: ipyleaflet not available. Map functionality will be disabled.")


class DataRetrieverUI:
    """Interactive widgets for surface variables data retrieval parameters with map integration."""

    def __init__(self):
        """Initialize the widget interface."""
        self.widgets = {}
        self.config_manager = ConfigurationManager()
        self.selected_file_path = None
        self.callbacks = None

        self.map_widget = None
        self.draw_control = None

        self.setup_widgets()

    def setup_widgets(self):
        """Initialize all parameter widgets with consistent styling."""
        self.widgets["data_source"] = widgets.RadioButtons(
            options=[
                ("Download from MARS Archive", "mars"),
                ("Load Local File", "local"),
            ],
            value="mars",
            description="Data Source:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="400px"),
        )

        self.widgets["file_path_input"] = widgets.Text(
            value="",
            description="File Path:",
            placeholder="Enter file path (e.g., /path/to/your/data.grib) or use Browse button",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="600px"),
            tooltip="Enter the full path to your GRIB file",
        )

        self.widgets["browse_btn"] = widgets.Button(
            description="Browse Files",
            button_style="",
            tooltip="Open file browser (may not work in remote environments like JupyterHub/ATOS)",
            layout=widgets.Layout(width="120px"),
            disabled=True,
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )

        self.widgets["load_file_btn"] = widgets.Button(
            description="Load File",
            button_style="",
            tooltip="Load the selected local file",
            layout=widgets.Layout(width="150px"),
            disabled=True,
            style={"button_color": "#0097A7", "font_weight": "bold"},
        )

        self.widgets["local_info_display"] = widgets.HTML(
            value="", layout=widgets.Layout(width="100%", margin="10px 0px")
        )

        self.widgets["mars_info_display"] = widgets.HTML(
            value="", layout=widgets.Layout(width="100%", margin="10px 0px")
        )

        param_options = self.config_manager.get_parameters_for_ui()
        default_params = self.config_manager.get_default_parameters()

        self.widgets["param"] = widgets.SelectMultiple(
            options=param_options,
            value=default_params,
            description="Parameters:",
            disabled=False,
            style={"description_width": "initial"},
            layout=widgets.Layout(width="400px", height="150px"),
        )

        model_options = self.config_manager.get_models_for_ui()
        default_model = self.config_manager.get_default_model()

        self.widgets["model"] = widgets.Dropdown(
            options=model_options,
            value=default_model,
            description="Model:",
            style={"description_width": "initial"},
        )

        self.widgets["date"] = widgets.DatePicker(
            description="Date:",
            value=date.today(),
            style={"description_width": "initial"},
        )

        available_times = self.config_manager.get_available_times()
        time_options = [(time, time) for time in available_times]

        self.widgets["time"] = widgets.Dropdown(
            options=time_options,
            value=available_times[0],
            description="Time:",
            style={"description_width": "initial"},
        )

        self.widgets["start_step"] = widgets.IntText(
            value=0,
            description="Start Step:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
            tooltip="Enter starting forecast step (0-360)",
        )

        self.widgets["end_step"] = widgets.IntText(
            value=72,
            description="End Step:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
            tooltip="Enter ending forecast step (0-360)",
        )

        self.widgets["step_selection"] = widgets.SelectMultiple(
            options=[],
            value=[],
            description="Select Steps:",
            disabled=False,
            style={"description_width": "initial"},
            layout=widgets.Layout(width="400px", height="150px"),
        )

        self.widgets["select_all_steps"] = widgets.Button(
            description="Select All Steps",
            button_style="",
            tooltip="Select all available steps",
            layout=widgets.Layout(width="150px"),
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )

        self.widgets["deselect_all_steps"] = widgets.Button(
            description="Deselect All",
            button_style="",
            tooltip="Deselect all steps",
            layout=widgets.Layout(width="150px"),
            style={"button_color": "#0097A7", "font_weight": "bold"},
        )

        self.widgets["update_steps"] = widgets.Button(
            description="Update Steps",
            button_style="",
            tooltip="Update step list based on start/end values",
            layout=widgets.Layout(width="150px"),
            style={"button_color": "#50DEA3", "font_weight": "bold"},
        )

        self.widgets["grid_resolution"] = widgets.Text(
            value="0.25",
            description="Grid Resolution:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
            tooltip="Grid resolution in degrees (leave empty for default, or enter value like 0.25)",
            placeholder="Leave empty for default or enter value",
        )

        self.widgets["reset_grid"] = widgets.Button(
            description="Reset Grid",
            button_style="",
            tooltip="Reset grid to default value (0.25)",
            layout=widgets.Layout(width="120px"),
            style={"button_color": "#50DEA3", "font_weight": "bold"},
        )

        self.widgets["clear_grid"] = widgets.Button(
            description="Clear Grid",
            button_style="",
            tooltip="Clear grid value (use system default)",
            layout=widgets.Layout(width="120px"),
            style={"button_color": "#0097A7", "font_weight": "bold"},
        )

        default_bbox = self.config_manager.get_default_bbox()

        self.widgets["north"] = widgets.FloatText(
            value=default_bbox["north"],
            description="North:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
            tooltip="Northern boundary (-90 to 90)",
        )

        self.widgets["west"] = widgets.FloatText(
            value=default_bbox["west"],
            description="West:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
            tooltip="Western boundary (-180 to 180)",
        )

        self.widgets["south"] = widgets.FloatText(
            value=default_bbox["south"],
            description="South:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
            tooltip="Southern boundary (-90 to 90)",
        )

        self.widgets["east"] = widgets.FloatText(
            value=default_bbox["east"],
            description="East:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
            tooltip="Eastern boundary (-180 to 180)",
        )

        self.widgets["clear_map_btn"] = widgets.Button(
            description="Clear Map",
            button_style="",
            tooltip="Clear all drawings from map",
            layout=widgets.Layout(width="120px"),
            style={"button_color": "#50DEA3", "font_weight": "bold"},
        )

        self.widgets["reset_map_btn"] = widgets.Button(
            description="Reset View",
            button_style="",
            tooltip="Reset map to default view",
            layout=widgets.Layout(width="120px"),
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )

        self.widgets["download_btn"] = widgets.Button(
            description="Retrieve Data",
            button_style="",
            tooltip="Click to download weather data",
            style={"button_color": "#00BCD4", "font_weight": "bold"},
        )

        self.widgets["preview_btn"] = widgets.Button(
            description="Preview Settings",
            button_style="",
            tooltip="Preview download settings",
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )

        self.widgets["reset_btn"] = widgets.Button(
            description="Reset All",
            button_style="",
            tooltip="Reset all settings to defaults",
            layout=widgets.Layout(width="150px"),
            style={"button_color": "#50DEA3", "font_weight": "bold"},
        )

        self.widgets["output"] = widgets.Output()

        self.create_map_widget()

        self._setup_observers()
        self._update_step_selection()

    def create_map_widget(self):  # noqa: PLR0912, PLR0915
        """Create the map widget with comprehensive error handling."""
        if not IPYLEAFLET_AVAILABLE:
            self.widgets["map_widget"] = widgets.HTML(
                "<p>Map not available - ipyleaflet not installed</p>"
            )
            return

        try:
            required_coords = ["north", "south", "east", "west"]
            default_bbox = self.config_manager.get_default_bbox()

            for coord in required_coords:
                if coord not in self.widgets:
                    print(f"Warning: Missing coordinate widget: {coord}")
                    self.widgets["map_widget"] = widgets.HTML(
                        "<p>Map not available - missing coordinate widgets</p>"
                    )
                    return

                widget = self.widgets[coord]
                if (
                    not hasattr(widget, "value")
                    or widget.value is None
                    or not isinstance(widget.value, int | float)
                ):
                    print(
                        f"Warning: Invalid value for coordinate widget: {coord}, setting default"
                    )
                    widget.value = default_bbox.get(coord, 0.0)

            try:
                north = float(self.widgets["north"].value)
                south = float(self.widgets["south"].value)
                west = float(self.widgets["west"].value)
                east = float(self.widgets["east"].value)

                north = max(-90, min(90, north))
                south = max(-90, min(90, south))
                west = max(-180, min(180, west))
                east = max(-180, min(180, east))

                if north <= south:
                    north = south + 1.0
                if east <= west:
                    east = west + 1.0

                center_lat = (north + south) / 2
                center_lon = (west + east) / 2

                if not (-90 <= center_lat <= 90 and -180 <= center_lon <= 180):  # noqa: PLR2004
                    center_lat, center_lon = 53.0, 10.0

            except (ValueError, TypeError, AttributeError) as e:
                print(f"Error calculating center coordinates: {e}")
                center_lat, center_lon = 53.0, 10.0
                for coord, default_val in default_bbox.items():
                    if coord in self.widgets:
                        self.widgets[coord].value = default_val

            self.map_widget = L.Map(
                center=[center_lat, center_lon],
                zoom=4,
                scroll_wheel_zoom=True,
                layout=widgets.Layout(height="400px", width="100%"),
            )

            try:
                self.map_widget.add_layer(
                    L.basemap_to_tiles(L.basemaps.OpenStreetMap.Mapnik)
                )
            except Exception as e:
                print(f"Warning: Could not load map tiles: {e}")

            try:
                self.draw_control = L.DrawControl(
                    polygon={},
                    rectangle={
                        "shapeOptions": {
                            "fillColor": "#fca45d",
                            "color": "#fca45d",
                            "fillOpacity": 0.3,
                        }
                    },
                    circle={},
                    marker={},
                    circlemarker={},
                    polyline={},
                    edit=False,
                )
                self.map_widget.add_control(self.draw_control)
                self.draw_control.on_draw(self.handle_draw_event)
            except Exception as e:
                print(f"Warning: Could not add drawing controls: {e}")

            button_row = widgets.HBox(
                [self.widgets["clear_map_btn"], self.widgets["reset_map_btn"]],
                layout=widgets.Layout(justify_content="center", margin="5px 0px"),
            )

            self.widgets["map_widget"] = widgets.VBox(
                [
                    widgets.HTML(
                        "<h4 style='color: #50DEA3; margin-bottom: 5px;'>Interactive Map Selection</h4>"
                    ),
                    button_row,
                    self.map_widget,
                ],
                layout=widgets.Layout(width="100%"),
            )

        except Exception as e:
            print(f"Error creating map widget: {e}")
            traceback.print_exc()
            self.widgets["map_widget"] = widgets.HTML(
                f"<p>Map not available: {str(e)}</p>"
            )

    def handle_draw_event(self, target, action, geo_json):  # noqa: PLR0912
        """Handle drawing events on the map with comprehensive validation."""
        if action == "created" and geo_json["geometry"]["type"] == "Polygon":
            try:
                coordinates = geo_json["geometry"]["coordinates"][0]

                if not coordinates or len(coordinates) < 4:  # noqa: PLR2004
                    print("Warning: Invalid coordinate data from map drawing")
                    return

                lats = []
                lons = []

                for coord in coordinates:
                    if coord and len(coord) >= 2:  # noqa: PLR2004
                        lon, lat = coord[0], coord[1]
                        if (
                            isinstance(lat, int | float)
                            and isinstance(lon, int | float)
                            and -90 <= lat <= 90  # noqa: PLR2004
                            and -180 <= lon <= 180  # noqa: PLR2004
                        ):
                            lats.append(lat)
                            lons.append(lon)

                if not lats or not lons or len(lats) < 2 or len(lons) < 2:  # noqa: PLR2004
                    print("Warning: Insufficient valid coordinates from map")
                    return

                north = max(lats)
                south = min(lats)
                east = max(lons)
                west = min(lons)

                if any(
                    coord is None or not isinstance(coord, int | float)
                    for coord in [north, south, east, west]
                ):
                    print("Warning: Calculated bounds contain invalid values")

                    return

                if north <= south or east <= west:
                    print("Warning: Invalid bounding box dimensions")
                    return

                coordinate_updates = {
                    "north": north,
                    "south": south,
                    "west": west,
                    "east": east,
                }

                for coord_name, value in coordinate_updates.items():
                    if coord_name in self.widgets:
                        widget = self.widgets[coord_name]
                        if hasattr(widget, "value"):
                            try:
                                if (
                                    value is not None
                                    and isinstance(value, int | float)
                                    and not (value != value)  # noqa: PLR0124
                                ):  # noqa: PLR0124
                                    rounded_value = float(round(value, 2))
                                    if coord_name in ["north", "south"]:
                                        rounded_value = max(-90, min(90, rounded_value))
                                    else:
                                        rounded_value = max(
                                            -180, min(180, rounded_value)
                                        )

                                    widget.value = rounded_value
                                else:
                                    print(
                                        f"Skipping invalid value for {coord_name}: {value}"
                                    )
                            except Exception as e:
                                print(f"Error updating {coord_name}: {e}")

            except Exception as e:
                print(f"Error handling map draw event: {e}")
                traceback.print_exc()

    def _setup_observers(self):  # noqa: PLR0915
        """Setting-up widget observers for dynamic updates."""
        try:

            def on_data_source_change(change):
                """Handle data source selection changes."""
                is_local = change["new"] == "local"

                self.widgets["browse_btn"].disabled = not is_local
                self.widgets["file_path_input"].disabled = not is_local
                file_path = self.widgets["file_path_input"].value.strip()
                self.widgets["load_file_btn"].disabled = not is_local or not file_path

                mars_widgets = [
                    "param",
                    "model",
                    "date",
                    "time",
                    "start_step",
                    "end_step",
                    "step_selection",
                    "select_all_steps",
                    "deselect_all_steps",
                    "update_steps",
                    "grid_resolution",
                    "reset_grid",
                    "clear_grid",
                    "north",
                    "west",
                    "south",
                    "east",
                    "download_btn",
                    "preview_btn",
                    "reset_btn",
                ]

                for widget_name in mars_widgets:
                    if widget_name in self.widgets:
                        self.widgets[widget_name].disabled = is_local

                self.widgets["local_info_display"].value = ""
                self.widgets["mars_info_display"].value = ""

            self.widgets["data_source"].observe(on_data_source_change, names="value")

            def on_date_change(change):  # noqa: ARG001
                """Update step selection when date changes."""
                self._update_step_selection()

            self.widgets["date"].observe(on_date_change, names="value")

            def on_model_change(change):  # noqa: ARG001
                """Update step selection when model changes."""
                self._update_step_selection()

            self.widgets["model"].observe(on_model_change, names="value")

            def validate_bounds(change):
                """Validate geographic bounds."""
                coord_name = change["owner"].description.replace(":", "").lower()
                value = change["new"]

                if coord_name in ["north", "south"]:
                    if value < -90:  # noqa: PLR2004
                        change["owner"].value = -90
                    elif value > 90:  # noqa: PLR2004
                        change["owner"].value = 90
                elif coord_name in ["east", "west"]:
                    if value < -180:  # noqa: PLR2004
                        change["owner"].value = -180
                    elif value > 180:  # noqa: PLR2004
                        change["owner"].value = 180

                if self.widgets["north"].value <= self.widgets["south"].value:
                    if coord_name == "north":
                        self.widgets["south"].value = self.widgets["north"].value - 0.1
                    else:
                        self.widgets["north"].value = self.widgets["south"].value + 0.1

                if self.widgets["east"].value <= self.widgets["west"].value:
                    if coord_name == "east":
                        self.widgets["west"].value = self.widgets["east"].value - 0.1
                    else:
                        self.widgets["east"].value = self.widgets["west"].value + 0.1

            for coord in ["north", "south", "east", "west"]:
                self.widgets[coord].observe(validate_bounds, names="value")

            def validate_steps(change):
                """Validate step input values."""
                widget_name = (
                    change["owner"]
                    .description.replace(":", "")
                    .replace(" ", "_")
                    .lower()
                )
                value = change["new"]

                if value < 0:
                    change["owner"].value = 0
                elif value > 360:  # noqa: PLR2004
                    change["owner"].value = 360

                if (
                    widget_name == "start_step"
                    and value > self.widgets["end_step"].value
                ):
                    self.widgets["end_step"].value = value
                elif (
                    widget_name == "end_step"
                    and value < self.widgets["start_step"].value
                ):
                    self.widgets["start_step"].value = value

            self.widgets["start_step"].observe(validate_steps, names="value")
            self.widgets["end_step"].observe(validate_steps, names="value")

            def validate_grid(change):
                """Validate grid resolution values."""
                value = change["new"].strip()

                if not value:
                    return

                try:
                    float_value = float(value)
                    if float_value <= 0:
                        change["owner"].value = "0.25"
                except ValueError:
                    change["owner"].value = "0.25"

            self.widgets["grid_resolution"].observe(validate_grid, names="value")

            def on_file_path_change(change):
                """Handle file path input changes."""
                file_path = change["new"].strip()
                is_local = self.widgets["data_source"].value == "local"

                self.selected_file_path = file_path if file_path else None

                self.widgets["load_file_btn"].disabled = not is_local or not file_path

                if not file_path:
                    self.widgets["local_info_display"].value = ""

            def select_all_steps(button):  # noqa: ARG001
                all_values = [
                    option[1] for option in self.widgets["step_selection"].options
                ]
                self.widgets["step_selection"].value = all_values

            def deselect_all_steps(button):  # noqa: ARG001
                self.widgets["step_selection"].value = []

            def update_steps(button):  # noqa: ARG001
                self._update_step_selection()

            def reset_grid(button):  # noqa: ARG001
                self.widgets["grid_resolution"].value = "0.25"

            def clear_grid(button):  # noqa: ARG001
                self.widgets["grid_resolution"].value = ""

            def reset_all(button):  # noqa: ARG001
                self.reset_widgets()

            self.widgets["browse_btn"].on_click(self._browse_for_file)
            self.widgets["data_source"].observe(on_data_source_change, names="value")
            self.widgets["file_path_input"].observe(on_file_path_change, names="value")
            self.widgets["select_all_steps"].on_click(select_all_steps)
            self.widgets["deselect_all_steps"].on_click(deselect_all_steps)
            self.widgets["update_steps"].on_click(update_steps)
            self.widgets["reset_grid"].on_click(reset_grid)
            self.widgets["clear_grid"].on_click(clear_grid)
            self.widgets["reset_btn"].on_click(reset_all)

            def on_preview_click(button):  # noqa: ARG001
                """Handle preview button click."""
                self.preview_settings()

            self.widgets["preview_btn"].on_click(on_preview_click)

        except Exception:
            traceback.print_exc()

    def _update_step_selection(self):
        """Update the step selection widget based on current parameters."""
        try:
            start_step = self.widgets["start_step"].value
            end_step = self.widgets["end_step"].value
            model = self.widgets["model"].value
            date_value = self.widgets["date"].value

            if start_step is None or end_step is None:
                return

            if start_step > end_step:
                self.widgets["start_step"].value, self.widgets["end_step"].value = (
                    end_step,
                    start_step,
                )
                start_step, end_step = end_step, start_step

            step_list = self.config_manager.generate_steps(
                start_step,
                end_step,
                model,
                date_value,
            )

            step_options = [(f"Step {step}", step) for step in step_list]
            current_selection = list(self.widgets["step_selection"].value)
            self.widgets["step_selection"].options = step_options
            available_steps = list(step_list)
            restored_selection = [
                step for step in current_selection if step in available_steps
            ]

            if not restored_selection:
                restored_selection = available_steps

            self.widgets["step_selection"].value = restored_selection

        except Exception as e:
            print(f"Error updating step selection: {e}")
            traceback.print_exc()

    def _browse_for_file(self, button):
        """Handle browse files button click."""
        try:
            root = tk.Tk()
            root.withdraw()

            if platform.system() == "Windows":
                root.wm_attributes("-topmost", 1)
                root.lift()
                root.focus_force()
            else:
                root.lift()
                root.attributes("-topmost", True)

            file_path = filedialog.askopenfilename(
                title="Select Surface Variable Data File",
                filetypes=[("GRIB files", "*.grib"), ("All files", "*.*")],
                initialdir=os.path.expanduser("~"),
            )

            root.destroy()

            if file_path:
                self.widgets["file_path_input"].value = file_path
                self.widgets["local_info_display"].value = f"""
                    <div style="background-color: #E0F7FA; padding: 10px; border-radius: 5px; margin: 5px 0; border-left: 4px solid #00BCD4;">
                        <h4 style="margin-top: 0; color: #50DEA3;">File Selected via Browser</h4>
                        <p>File: {os.path.basename(file_path)}</p>
                        <p>Path: {file_path}</p>
                        <p><em>Ready to load. Click 'Load File' button to proceed.</em></p>
                    </div>
                """

        except Exception as e:
            self.widgets["local_info_display"].value = f"""
                <div style="background-color: #FFF3E0; padding: 10px; border-radius: 5px; margin: 5px 0; border-left: 4px solid #FF9800;">
                    <h4 style="margin-top: 0; color: #FF9800;">File Browser Not Available</h4>
                    <p><strong>Environment:</strong> File browser may not work in JupyterHub, ATOS, or remote environments.</p>
                    <p><strong>Solution:</strong> Please type or paste your file path directly in the "File Path" field above.</p>
                    <p><strong>Example:</strong> <code>/home/username/data/weather_data.grib</code></p>
                    <p><em>Error details: {str(e)}</em></p>
                </div>
            """

    def set_callbacks(self, callbacks):
        """Set the callbacks instance for handling main action button clicks.

        This method should be called AFTER creating the DataRetrieverCallbacks instance
        to properly connect the main action buttons to their callback handlers.

        Args:
            callbacks: DataRetrieverCallbacks instance with callback methods

        """
        self.callbacks = callbacks

        main_action_buttons = [
            "download_btn",
            "load_file_btn",
            "clear_map_btn",
            "reset_map_btn",
        ]
        for button_name in main_action_buttons:
            if button_name in self.widgets:
                widget = self.widgets[button_name]
                if hasattr(widget, "_click_handlers"):
                    widget._click_handlers.callbacks.clear()

                widget._click_handlers = widget._click_handlers.__class__()

        if "download_btn" in self.widgets:
            self.widgets["download_btn"].on_click(callbacks.on_download_click)
        if "load_file_btn" in self.widgets:
            self.widgets["load_file_btn"].on_click(callbacks.on_load_file_click)
        if "clear_map_btn" in self.widgets:
            self.widgets["clear_map_btn"].on_click(callbacks.on_clear_map_click)
        if "reset_map_btn" in self.widgets:
            self.widgets["reset_map_btn"].on_click(callbacks.on_reset_map_click)

    def display_interface(self):
        """Display the main interface with data source selection."""
        source_box = widgets.VBox(
            [
                widgets.HTML(
                    "<h2 style='color: #00BCD4; margin-bottom: 10px;'>Data Source Selection</h2>"
                ),
                self.widgets["data_source"],
            ],
            layout=widgets.Layout(margin="0px", padding="0px"),
        )

        file_box = widgets.VBox(
            [
                widgets.HTML(
                    "<h3 style='color: #50DEA3; margin-bottom: 10px;'>Local File Options</h3>"
                ),
                widgets.HTML(
                    "<p style='color: #666; font-size: 0.9em; margin: 5px 0;'>"
                    "Enter file path directly or use Browse button (may not work in remote environments)"
                    "</p>"
                ),
                self.widgets["file_path_input"],
                widgets.HBox(
                    [self.widgets["browse_btn"], self.widgets["load_file_btn"]],
                    layout=widgets.Layout(
                        margin="5px 0px", justify_content="flex-start"
                    ),
                ),
            ],
            layout=widgets.Layout(margin="0px", padding="0px"),
        )

        local_info_section = widgets.VBox(
            [self.widgets["local_info_display"]],
            layout=widgets.Layout(margin="0px", padding="0px"),
        )

        mars_interface = self._create_mars_interface()

        map_buttons_conditional = widgets.VBox(
            [], layout=widgets.Layout(margin="0px", padding="0px")
        )

        map_section = widgets.VBox(
            [
                widgets.HTML(
                    "<h3 style='color: #50DEA3; margin-bottom: 10px;'>Interactive Map Selection</h3>"
                ),
                map_buttons_conditional,
                self.map_widget
                if hasattr(self, "map_widget") and self.map_widget
                else widgets.HTML("<p>Map loading...</p>"),
            ],
            layout=widgets.Layout(width="100%", margin="10px 0px"),
        )

        local_file_conditional = widgets.VBox(
            [], layout=widgets.Layout(margin="0px", padding="0px")
        )
        mars_conditional = widgets.VBox(
            [], layout=widgets.Layout(margin="0px", padding="0px")
        )

        def update_interface_visibility():
            """Update interface visibility based on data source selection."""
            is_mars = self.widgets["data_source"].value == "mars"
            is_local = self.widgets["data_source"].value == "local"

            if is_local:
                local_file_conditional.children = [file_box, local_info_section]
            else:
                local_file_conditional.children = []

            if is_mars:
                mars_conditional.children = [mars_interface]
                map_buttons_conditional.children = [
                    widgets.HBox(
                        [self.widgets["clear_map_btn"], self.widgets["reset_map_btn"]],
                        layout=widgets.Layout(
                            justify_content="center", margin="5px 0px"
                        ),
                    )
                ]
            else:
                mars_conditional.children = []
                map_buttons_conditional.children = []

        def on_data_source_change_interface(change):  # noqa: ARG001
            update_interface_visibility()

        self.widgets["data_source"].observe(
            on_data_source_change_interface, names="value"
        )

        update_interface_visibility()

        header = widgets.HTML(
            value="""
            <div style="display: flex; flex-direction: column; align-items: center; margin: 0; padding: 0; text-align: center;">
                <img src="../helpers/widgets/assets/evalkit_logo_v2.png" style="height: 60px; width: auto; margin-bottom: 8px; image-rendering: -webkit-optimize-contrast; image-rendering: crisp-edges;" alt="EvalKit Logo">
                <h1 style="color: #171A35; margin: 0; padding: 0; font-weight: bold; font-size: 28px; line-height: 1.2;">Interactive Surface Variables Visualization</h1>
            </div>
            """,
            layout=widgets.Layout(margin="0px", padding="0px"),
        )

        interface_panel = widgets.VBox(
            [
                source_box,
                local_file_conditional,
                mars_conditional,
                map_section,
                self.widgets["output"],
            ],
            layout=widgets.Layout(margin="0px", padding="0px", flex="1 1 auto"),
        )

        interface_panel = widgets.Accordion(
            children=[interface_panel],
            titles=["Configuration Panel"],
            layout=widgets.Layout(width="100%", flex="1 1 auto"),
        )
        interface_panel.selected_index = 0

        interface = widgets.VBox(
            [header, interface_panel],
            layout=widgets.Layout(padding="20px"),
        )

        display(interface)

    def _create_mars_interface(self):
        """Create the MARS Archive interface without map (map is now separate)."""
        param_box = widgets.VBox(
            [
                widgets.HTML(
                    "<h3 style='color: #50DEA3; margin-bottom: 10px;'>Parameter Selection</h3>"
                ),
                self.widgets["param"],
            ],
            layout=widgets.Layout(width="48%", margin="0px 10px 0px 0px"),
        )

        model_time_box = widgets.VBox(
            [
                widgets.HTML(
                    "<h3 style='color: #50DEA3; margin-bottom: 10px;'>Model & Time</h3>"
                ),
                self.widgets["model"],
                self.widgets["date"],
                self.widgets["time"],
            ],
            layout=widgets.Layout(width="48%", margin="0px 0px 0px 10px"),
        )

        params_model_section = widgets.HBox(
            [param_box, model_time_box],
            layout=widgets.Layout(
                justify_content="space-between", width="100%", margin="0px"
            ),
        )

        steps_box = widgets.VBox(
            [
                widgets.HTML(
                    "<h3 style='color: #50DEA3; margin-bottom: 10px;'>Forecast Steps</h3>"
                ),
                widgets.HBox(
                    [
                        self.widgets["start_step"],
                        self.widgets["end_step"],
                        self.widgets["update_steps"],
                    ],
                    layout=widgets.Layout(margin="0px", justify_content="flex-start"),
                ),
                widgets.HTML(
                    "<h4 style='color: #50DEA3; margin-bottom: 5px;'>Step Selection</h4>"
                ),
                widgets.HBox(
                    [
                        self.widgets["select_all_steps"],
                        self.widgets["deselect_all_steps"],
                    ],
                    layout=widgets.Layout(margin="0px", justify_content="flex-start"),
                ),
                self.widgets["step_selection"],
            ],
            layout=widgets.Layout(width="48%", margin="0px 10px 0px 0px"),
        )

        area_grid_box = widgets.VBox(
            [
                widgets.HTML(
                    "<h3 style='color: #50DEA3; margin-bottom: 10px;'>Geographic Area</h3>"
                ),
                widgets.HBox(
                    [self.widgets["north"], self.widgets["south"]],
                    layout=widgets.Layout(margin="0px", justify_content="flex-start"),
                ),
                widgets.HBox(
                    [self.widgets["west"], self.widgets["east"]],
                    layout=widgets.Layout(margin="0px", justify_content="flex-start"),
                ),
                widgets.HTML(
                    "<h3 style='color: #50DEA3; margin-bottom: 10px; margin-top: 15px;'>Grid Resolution</h3>"
                ),
                widgets.HTML(
                    '<p style="color: #666; font-size: 0.9em; margin: 0;">Leave empty for default or enter value (e.g., 0.25)</p>'
                ),
                widgets.HBox(
                    [
                        self.widgets["grid_resolution"],
                        self.widgets["reset_grid"],
                        self.widgets["clear_grid"],
                    ],
                    layout=widgets.Layout(margin="0px", justify_content="flex-start"),
                ),
            ],
            layout=widgets.Layout(width="48%", margin="0px 0px 0px 10px"),
        )
        steps_area_section = widgets.HBox(
            [steps_box, area_grid_box],
            layout=widgets.Layout(
                justify_content="space-between", width="100%", margin="10px 0px"
            ),
        )

        buttons_section = widgets.HBox(
            [
                self.widgets["preview_btn"],
                self.widgets["download_btn"],
                self.widgets["reset_btn"],
            ],
            layout=widgets.Layout(justify_content="center", margin="10px 0px"),
        )

        mars_info_section = widgets.VBox(
            [self.widgets["mars_info_display"]],
            layout=widgets.Layout(margin="0px", padding="0px"),
        )

        mars_box = widgets.VBox(
            [
                widgets.HTML(
                    "<h2 style='color: #00BCD4; margin-bottom: 15px;'>MARS Archive Options</h2>"
                ),
                params_model_section,
                steps_area_section,
                buttons_section,
                mars_info_section,
            ],
            layout=widgets.Layout(margin="0px", padding="0px", width="100%"),
        )

        return mars_box

    def display_advanced_interface(self):
        """Display advanced parameter selection interface with geographic bounds."""
        self.display_interface()

    def get_parameters(self) -> dict:
        """Get current widget values as parameters dictionary.

        Returns:
            Dictionary of current parameter values

        """
        grid_value = self.widgets["grid_resolution"].value.strip()

        grid_param = None
        if grid_value:
            try:
                grid_resolution = float(grid_value)
                if grid_resolution > 0:
                    grid_param = [grid_resolution, grid_resolution]
            except ValueError:
                grid_param = None
        file_path = (
            self.widgets["file_path_input"].value.strip()
            if "file_path_input" in self.widgets
            else self.selected_file_path
        )

        return {
            "data_source": self.widgets["data_source"].value,
            "selected_file_path": file_path if file_path else None,
            "param": list(self.widgets["param"].value),
            "start_step": self.widgets["start_step"].value,
            "end_step": self.widgets["end_step"].value,
            "selected_steps": list(self.widgets["step_selection"].value),
            "date": self.widgets["date"].value.strftime("%Y-%m-%d"),
            "time": self.widgets["time"].value,
            "model": self.widgets["model"].value,
            "area": [
                self.widgets["north"].value,
                self.widgets["west"].value,
                self.widgets["south"].value,
                self.widgets["east"].value,
            ],
            "grid": grid_param,
        }

    def preview_settings(self):
        """Preview current settings in the mars_info_display widget with blue styling."""
        params = self.get_parameters()

        if params["data_source"] == "local":
            if params["selected_file_path"]:
                file_name = os.path.basename(params["selected_file_path"])
                self.widgets["local_info_display"].value = f"""
                    <div style="background-color: #E3F2FD; padding: 10px; border-radius: 5px; border-left: 4px solid #2196F3;">
                        <h4 style="color: #2196F3; margin-top: 0;">Data Retrieval Settings Preview</h4>
                        <p><strong>Data Source:</strong> Local File</p>
                        <p><strong>Selected File:</strong> {file_name}</p>
                        <p><strong>Full Path:</strong> {params["selected_file_path"]}</p>
                        <p><em>Ready to load the selected local file.</em></p>
                    </div>
                    """
            else:
                self.widgets["local_info_display"].value = """
                    <div style="background-color: #FFEBEE; padding: 10px; border-radius: 5px; border-left: 4px solid #F44336;">
                        <h4 style="color: #F44336; margin-top: 0;">Preview Settings</h4>
                        <p><strong>Data Source:</strong> Local File</p>
                        <p><strong>Issue:</strong> No file selected</p>
                        <p>Please select a file using the 'Browse Files' button.</p>
                    </div>
                    """
        else:
            model = params["model"]
            selected_steps = sorted(params["selected_steps"])
            step_info = ""

            try:
                model_info = self.config_manager.get_model_info(model)
                model_display_name = model_info.get("display_name", model)
                step_pattern = model_info.get("step_pattern", "unknown")
            except:  # noqa: E722
                model_display_name = model
                step_pattern = "unknown"

            if step_pattern == "six_hourly":
                step_info = f"""
                    <p><strong>Model Type:</strong> {model_display_name} - 6-hourly steps</p>
                    <p><strong>Available Steps:</strong> {selected_steps}</p>
                    """
            else:
                hourly_steps = [s for s in selected_steps if s <= 144]  # noqa: PLR2004
                sixhourly_steps = [s for s in selected_steps if s > 144]  # noqa: PLR2004
                step_info = f"""
                    <p><strong>Model Type:</strong> {model_display_name}</p>
                    """
                if hourly_steps:
                    step_info += (
                        f"<p><strong>Hourly steps (0-144h):</strong> {hourly_steps}</p>"
                    )
                if sixhourly_steps:
                    step_info += f"<p><strong>6-hourly steps (150h+):</strong> {sixhourly_steps}</p>"

            grid_info = (
                "System default"
                if params["grid"] is None
                else f"{params['grid'][0]} degrees"
            )

            total_data_points = len(params["param"]) * len(selected_steps)

            self.widgets["mars_info_display"].value = f"""
                <div style="background-color: #E3F2FD; padding: 10px; border-radius: 5px; border-left: 4px solid #2196F3;">
                    <h4 style="color: #2196F3; margin-top: 0;">MARS Archive Settings Preview</h4>

                    <p><strong>Data Source:</strong> MARS Archive</p>
                    <p><strong>Parameters:</strong> {", ".join(params["param"])} ({len(params["param"])} total)</p>
                    <p><strong>Model:</strong> {model_display_name}</p>
                    <p><strong>Date & Time:</strong> {params["date"]} at {params["time"]}</p>
                    <p><strong>Step Range:</strong> {params["start_step"]} to {params["end_step"]}</p>
                    <p><strong>Selected Steps:</strong> {len(selected_steps)} steps total</p>

                    {step_info}

                    <p><strong>Geographic Area:</strong></p>
                    <ul style="margin: 5px 0; padding-left: 20px;">
                        <li>North: {params["area"][0]}°</li>
                        <li>West: {params["area"][1]}°</li>
                        <li>South: {params["area"][2]}°</li>
                        <li>East: {params["area"][3]}°</li>
                    </ul>

                    <p><strong>Grid Resolution:</strong> {grid_info}</p>

                    <hr style="border: none; border-top: 1px solid #2196F3; margin: 10px 0;">

                    <p><strong>Summary:</strong></p>
                    <ul style="margin: 5px 0; padding-left: 20px;">
                        <li><strong>Total Selected Steps:</strong> {len(selected_steps)}</li>
                        <li><strong>Total Data Points:</strong> {len(params["param"])} parameters × {len(selected_steps)} steps = {total_data_points:,}</li>
                    </ul>

                    <p><em style="color: #2196F3;">Ready for data retrieval from MARS Archive!</em></p>
                </div>
                """

    def reset_widgets(self):
        """Reset all widgets to their default values."""
        default_params = self.config_manager.get_default_parameters()
        default_model = self.config_manager.get_default_model()
        default_bbox = self.config_manager.get_default_bbox()
        available_times = self.config_manager.get_available_times()

        self.widgets["data_source"].value = "mars"
        self.widgets["param"].value = default_params
        self.widgets["model"].value = default_model
        self.widgets["date"].value = date.today()
        self.widgets["time"].value = available_times[0]
        self.widgets["start_step"].value = 0
        self.widgets["end_step"].value = 72
        self.widgets["grid_resolution"].value = "0.25"
        self.widgets["north"].value = default_bbox["north"]
        self.widgets["west"].value = default_bbox["west"]
        self.widgets["south"].value = default_bbox["south"]
        self.widgets["east"].value = default_bbox["east"]

        self.selected_file_path = None

        self.widgets["local_info_display"].value = ""
        self.widgets["mars_info_display"].value = ""
        if "file_path_input" in self.widgets:
            self.widgets["file_path_input"].value = ""

        with self.widgets["output"]:
            clear_output()

        self._update_step_selection()

        if hasattr(self, "map_widget") and self.map_widget is not None:
            try:
                if hasattr(self, "draw_control") and self.draw_control is not None:
                    self.draw_control.clear()
                center_lat = (
                    self.widgets["north"].value + self.widgets["south"].value
                ) / 2
                center_lon = (
                    self.widgets["west"].value + self.widgets["east"].value
                ) / 2
                self.map_widget.center = [center_lat, center_lon]
                self.map_widget.zoom = 4
            except Exception as e:
                print(f"Error resetting map: {e}")
