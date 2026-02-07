import time
import traceback

import ipyleaflet  # type: ignore
import ipywidgets as widgets  # type: ignore


class WeatherMapHandler:
    """Interactive map handler with single-point selection and bbox validation for weather analysis."""

    def __init__(self, ui_instance):
        """Initialize the map handler."""
        self.ui = ui_instance
        self.map_widget = None
        self.draw_control = None
        self.current_bbox = None
        self.current_rectangle = None
        self.default_center = (53.0, 10.0)
        self.default_zoom = 4

        self.selected_point = None
        self.point_marker = None
        self.point_color = "#345AF3"

        self.observation_markers = {}
        self.observation_stations_gdf = None

        self.drawing_mode = False
        self.last_draw_time = 0

        self.forecast_layer_group = None
        self.observation_layer_group = None

        self.center_protection_enabled = True
        self.allowed_to_change_center = False
        self.protected_center = None
        self.protected_zoom = None
        self.view_state_locked = False

        self.last_click_time = 0
        self.last_click_coords = None
        self.click_dedupe_threshold = 0.1
        self.event_counter = 0

        self.auto_plotting_enabled = True
        self.data_loaded = False

        self.setup_map()

    def is_point_in_bbox(self, lat, lon):
        """Check if a point (lat, lon) is within the current bounding box."""
        try:
            bbox = self.get_current_bbox()
            if not bbox:
                return True

            north = bbox["north"]
            south = bbox["south"]
            east = bbox["east"]
            west = bbox["west"]

            lat_in_range = south <= lat <= north
            lon_in_range = west <= lon <= east

            return lat_in_range and lon_in_range

        except Exception as e:
            print(f"Error checking bbox constraint: {e}")
            return True

    def setup_map(self):
        """Initialize the interactive map with interaction handling."""
        self.map_widget = ipyleaflet.Map(
            center=self.default_center,
            zoom=self.default_zoom,
            scroll_wheel_zoom=True,
            double_click_zoom=True,
            box_zoom=False,
            keyboard=False,
            world_copy_jump=False,
            layout=widgets.Layout(width="100%", height="400px"),
        )

        self.forecast_layer_group = ipyleaflet.LayerGroup(name="forecast_points")
        self.observation_layer_group = ipyleaflet.LayerGroup(
            name="observation_stations"
        )

        self.map_widget.add_layer(self.forecast_layer_group)
        self.map_widget.add_layer(self.observation_layer_group)

        zoom_control = ipyleaflet.ZoomControl(position="topright")
        self.map_widget.add_control(zoom_control)

        scale_control = ipyleaflet.ScaleControl(position="bottomleft")
        self.map_widget.add_control(scale_control)

        fullscreen_control = ipyleaflet.FullScreenControl()
        self.map_widget.add_control(fullscreen_control)

        self.draw_control = ipyleaflet.DrawControl()

        self.draw_control.rectangle = {
            "shapeOptions": {
                "fillColor": "#2196F3",
                "color": "#1976D2",
                "fillOpacity": 0.1,
                "weight": 2,
                "opacity": 0.7,
                "dashArray": "5, 5",
            },
            "drawError": {"color": "#dd253b", "message": "Error drawing rectangle!"},
            "allowIntersection": False,
        }

        self.draw_control.polygon = {}
        self.draw_control.polyline = {}
        self.draw_control.circle = {}
        self.draw_control.marker = {}
        self.draw_control.circlemarker = {}

        self.map_widget.add_control(self.draw_control)

        self.draw_control.on_draw(self._on_draw_event)
        self.map_widget.on_interaction(self._on_unified_map_interaction)

        self.update_bbox_visualization()

    def _temporarily_allow_view_changes(self):
        """Context manager to temporarily allow view changes."""

        class ViewChangeContext:
            def __init__(self, handler):
                self.handler = handler

            def __enter__(self):
                self.handler.allowed_to_change_center = True
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.handler.allowed_to_change_center = False

        return ViewChangeContext(self)

    def _on_unified_map_interaction(self, **kwargs):
        """Enhanced map interaction handling with single-point selection and bbox validation."""
        if kwargs.get("type") == "click":
            coordinates = kwargs.get("coordinates")
            if coordinates:
                lat, lon = coordinates

                self.event_counter += 1
                current_time = time.time()

                if (
                    self.last_click_coords
                    and abs(lat - self.last_click_coords[0]) < 0.0001  # noqa: PLR2004
                    and abs(lon - self.last_click_coords[1]) < 0.0001  # noqa: PLR2004
                    and current_time - self.last_click_time
                    < self.click_dedupe_threshold
                ):
                    return

                if current_time - self.last_draw_time < 0.2:  # noqa: PLR2004
                    return

                self.last_click_time = current_time
                self.last_click_coords = (lat, lon)

                current_center = self.map_widget.center
                current_zoom = self.map_widget.zoom

                self._process_single_point_click(lat, lon)

                if (
                    self.map_widget.center != current_center
                    or self.map_widget.zoom != current_zoom
                ):
                    with self._temporarily_allow_view_changes():
                        self.map_widget.center = current_center
                        self.map_widget.zoom = current_zoom

    def _process_single_point_click(self, lat, lon):
        """Process map clicks with single-point selection and bbox validation."""
        try:
            if not self.is_point_in_bbox(lat, lon):
                if hasattr(self.ui, "show_alert_message"):
                    self.ui.show_alert_message(
                        f"Point ({lat:.3f}°N, {lon:.3f}°E) is outside the current geographic area. "
                        "Please select a point within the defined bounding box.",
                        "warning",
                        section="plotting",
                        permanent=True,
                    )
                return

            if not (hasattr(self.ui, "data_loaded") and self.ui.data_loaded):
                if hasattr(self.ui, "show_alert_message"):
                    self.ui.show_alert_message(
                        "Please load data first before selecting points.",
                        "warning",
                        section="plotting",
                        permanent=True,
                    )
                return

            if (
                not hasattr(self.ui, "current_plot_type")
                or not self.ui.current_plot_type
            ):
                if hasattr(self.ui, "show_alert_message"):
                    self.ui.show_alert_message(
                        "Please select a plot type first.",
                        "warning",
                        section="plotting",
                        permanent=True,
                    )
                return

            current_plot_type = self.ui.current_plot_type

            plot_config = self.ui.plot_configs.get(current_plot_type, {})
            requires_points = plot_config.get("requires_points", False)

            if not requires_points:
                if hasattr(self.ui, "show_alert_message"):
                    self.ui.show_alert_message(
                        f"{current_plot_type.title()} plots don't require point selection.",
                        "info",
                        section="plotting",
                        permanent=True,
                    )
                return

            if self.selected_point is not None:
                self._remove_current_point()
                if hasattr(self.ui, "show_alert_message"):
                    self.ui.show_alert_message(
                        "Previous analysis point removed.",
                        "info",
                        section="plotting",
                        permanent=True,
                    )

            self._add_single_point(lat, lon)
            self._update_plotting_manager_with_single_point()

            if hasattr(self.ui, "on_map_point_selected"):
                self.ui.on_map_point_selected(lat, lon)
            else:
                print("UI doesn't have on_map_point_selected method")

        except Exception as e:
            traceback.print_exc()
            if hasattr(self.ui, "show_alert_message"):
                self.ui.show_alert_message(
                    f"Error processing map click: {e}",
                    "error",
                    section="plotting",
                    permanent=True,
                )

    def _add_single_point(self, lat, lon):
        """Add a single analysis point with bbox validation."""
        try:
            if not self.is_point_in_bbox(lat, lon):
                if hasattr(self.ui, "show_alert_message"):
                    self.ui.show_alert_message(
                        "Cannot add point outside geographic area boundaries.",
                        "error",
                        section="plotting",
                        permanent=True,
                    )
                return None

            circle_marker = ipyleaflet.CircleMarker(
                location=(lat, lon),
                radius=12,
                color=self.point_color,
                fill_color=self.point_color,
                fill_opacity=0.8,
                weight=3,
                opacity=1.0,
                interactive=True,
            )

            current_plot_type = getattr(self.ui, "current_plot_type", "analysis")
            popup_html = widgets.HTML(
                value=f"""
                <div style="padding: 10px; border-left: 4px solid {self.point_color};">
                    <b style="color: {self.point_color};">📍 {current_plot_type.title()} Point</b><br>
                    Lat: {lat:.4f}°<br>
                    Lon: {lon:.4f}°<br>
                    <span style="color: {self.point_color}; font-weight: bold;">●</span> Analysis Location<br>
                    <em>Click elsewhere to move point</em><br>
                    <small>Single point mode - automatic plotting</small>
                </div>
                """
            )
            circle_marker.popup = ipyleaflet.Popup(
                child=popup_html, close_button=True, max_width=280
            )

            self.selected_point = {
                "lat": lat,
                "lon": lon,
                "marker": circle_marker,
                "color": self.point_color,
                "label": f"{current_plot_type.title()} Point",
                "type": "single_analysis",
                "plot_type": current_plot_type,
            }

            self.point_marker = circle_marker

            self.forecast_layer_group.add_layer(circle_marker)

            if hasattr(self.ui, "show_alert_message"):
                self.ui.show_alert_message(
                    f"Selected {current_plot_type} analysis point at {lat:.3f}°N, {lon:.3f}°E",
                    "success",
                    section="plotting",
                    permanent=True,
                )

            print("Successfully added single analysis point")
            return "P1"  # Always P1 for single point

        except Exception as e:
            print(f"Error adding single analysis point: {e}")
            if hasattr(self.ui, "show_alert_message"):
                self.ui.show_alert_message(
                    f"Error adding analysis point: {e}",
                    "error",
                    section="plotting",
                    permanent=True,
                )
            return None

    def _remove_current_point(self):
        """Remove the current single analysis point."""
        try:
            if self.selected_point is None:
                return

            if (
                self.point_marker
                and self.point_marker in self.forecast_layer_group.layers
            ):
                self.forecast_layer_group.remove_layer(self.point_marker)

            self.selected_point = None
            self.point_marker = None

            print("Removed current analysis point")

        except Exception as e:
            print(f"Error removing analysis point: {e}")

    def get_selected_points(self):
        """Get the currently selected point (single point only)."""
        if self.selected_point is None:
            return {}

        return {
            "P1": {
                "lat": self.selected_point["lat"],
                "lon": self.selected_point["lon"],
                "color": self.selected_point["color"],
                "label": self.selected_point["label"],
                "plot_type": self.selected_point.get("plot_type", "analysis"),
            }
        }

    def clear_all_points(self):
        """Clear the selected point."""
        try:
            print("Clearing analysis point from map")

            self._remove_current_point()

            self.last_click_time = 0
            self.last_click_coords = None
            self.event_counter = 0

            if hasattr(self.ui, "callbacks") and self.ui.callbacks:
                if hasattr(self.ui.callbacks, "plotting_manager"):
                    plotting_manager = self.ui.callbacks.plotting_manager
                    if hasattr(plotting_manager, "update_selected_points"):
                        plotting_manager.update_selected_points({})
                        print("Cleared plotting manager points")

            self._clear_drawings()

            print("Analysis point cleared successfully")

        except Exception as e:
            print(f"Error clearing analysis point: {e}")
            traceback.print_exc()

    def _clear_drawings(self):
        """Clear all drawings from the map."""
        try:
            if hasattr(self, "draw_control") and self.draw_control:
                self.draw_control.clear()
        except Exception as e:
            print(f"Could not clear drawing control: {e}")

    def _update_plotting_manager_with_single_point(self):
        """Update connected plotting manager with the single selected point."""
        try:
            if (
                hasattr(self.ui, "callbacks")
                and self.ui.callbacks
                and hasattr(self.ui.callbacks, "plotting_manager")
            ):
                plotting_manager = self.ui.callbacks.plotting_manager

                if self.selected_point:
                    plotting_points = {
                        "P1": (self.selected_point["lat"], self.selected_point["lon"])
                    }
                else:
                    plotting_points = {}

                if hasattr(plotting_manager, "update_selected_points"):
                    plotting_manager.update_selected_points(plotting_points)
                    print(
                        f"Updated plotting manager with single point: {plotting_points}"
                    )

        except Exception as e:
            print(f"Error updating plotting manager with single point: {e}")

    def get_auto_plot_points_for_plotting_manager(self):
        """Get selected point in format expected by plotting manager."""
        if self.selected_point is None:
            return {}

        return {"P1": (self.selected_point["lat"], self.selected_point["lon"])}

    def has_selected_point(self):
        """Check if a point is currently selected."""
        return self.selected_point is not None

    def get_selected_point_coordinates(self):
        """Get coordinates of the selected point."""
        if self.selected_point:
            return (self.selected_point["lat"], self.selected_point["lon"])
        return None

    def validate_point_in_current_bbox(self, lat, lon):
        """Public method to validate if coordinates are within current bbox."""
        return self.is_point_in_bbox(lat, lon)

    def _on_draw_event(self, target, action, geo_json):
        """Handle draw events and automatically update coordinates."""
        self.last_draw_time = time.time()

        if action == "created" and geo_json["geometry"]["type"] == "Polygon":
            coordinates = geo_json["geometry"]["coordinates"][0]
            lons = [coord[0] for coord in coordinates]
            lats = [coord[1] for coord in coordinates]

            min_lon = min(lons)
            max_lon = max(lons)
            min_lat = min(lats)
            max_lat = max(lats)

            self.set_current_bbox_and_update_ui(max_lat, min_lat, max_lon, min_lon)

        elif action == "deleted":
            self._clear_current_rectangle()

    def update_bbox_visualization(self, preserve_center=True):
        """Update the bounding box visualization on the map."""
        self._clear_current_rectangle()

        try:
            north = float(self.ui.widgets["north"].value)
            south = float(self.ui.widgets["south"].value)
            east = float(self.ui.widgets["east"].value)
            west = float(self.ui.widgets["west"].value)
        except (KeyError, AttributeError, ValueError, TypeError) as e:
            print(f"Error getting bbox values from UI: {e}")
            north, south, east, west = 72.0, 34.0, 45.0, -25.0

        self.current_bbox = {"north": north, "south": south, "east": east, "west": west}

        bounds = [(south, west), (north, east)]
        self.current_rectangle = ipyleaflet.Rectangle(
            bounds=bounds,
            color="#1976D2",
            fill_color="#2196F3",
            opacity=0.7,
            fill_opacity=0.05,
            weight=2,
            dash_array="5, 5",
            interactive=False,
            no_click=True,
        )

        self.map_widget.add_layer(self.current_rectangle)

        if self.selected_point:
            lat, lon = self.selected_point["lat"], self.selected_point["lon"]
            if not self.is_point_in_bbox(lat, lon):
                if hasattr(self.ui, "show_alert_message"):
                    self.ui.show_alert_message(
                        "Current analysis point is now outside the geographic area and has been removed.",
                        "warning",
                        section="plotting",
                        permanent=True,
                    )
                self.clear_all_points()

    def _clear_current_rectangle(self):
        """Clear the current rectangle from the map."""
        if self.current_rectangle and self.current_rectangle in self.map_widget.layers:
            self.map_widget.remove_layer(self.current_rectangle)
        self.current_rectangle = None

    def get_current_bbox(self):
        """Get the current bounding box coordinates."""
        if self.current_bbox is None:
            try:
                return {
                    "north": float(self.ui.widgets["north"].value),
                    "south": float(self.ui.widgets["south"].value),
                    "east": float(self.ui.widgets["east"].value),
                    "west": float(self.ui.widgets["west"].value),
                }
            except (KeyError, AttributeError, ValueError, TypeError):
                return None

        return self.current_bbox

    def set_current_bbox_and_update_ui(  # noqa: PLR0912
        self, north=None, south=None, east=None, west=None, bbox_dict=None
    ):
        """Set the current bounding box coordinates and automatically update UI."""
        if bbox_dict is not None:
            try:
                north = bbox_dict.get("north")
                south = bbox_dict.get("south")
                east = bbox_dict.get("east")
                west = bbox_dict.get("west")
            except (AttributeError, TypeError) as e:
                print(f"Error extracting bbox from dictionary: {e}")
                return

        if isinstance(north, tuple | list) and len(north) == 4:  # noqa: PLR2004
            min_lon, min_lat, max_lon, max_lat = north
            north, south, east, west = max_lat, min_lat, max_lon, min_lon

        if any(coord is None for coord in [north, south, east, west]):
            print("Error: All bbox coordinates must be provided")
            return

        try:
            north_val = float(north)
            south_val = float(south)
            east_val = float(east)
            west_val = float(west)
        except (ValueError, TypeError) as e:
            print(f"Error converting bbox coordinates to float: {e}")
            return

        if not (-90 <= north_val <= 90) or not (-90 <= south_val <= 90):  # noqa: PLR2004
            print("Error: Latitude values must be between -90 and 90")
            return

        if not (-180 <= east_val <= 180) or not (-180 <= west_val <= 180):  # noqa: PLR2004
            print("Error: Longitude values must be between -180 and 180")
            return

        if north_val <= south_val:
            print("Error: North boundary must be greater than south boundary")
            return

        self.current_bbox = {
            "north": north_val,
            "south": south_val,
            "east": east_val,
            "west": west_val,
        }

        try:
            if hasattr(self.ui, "widgets") and isinstance(self.ui.widgets, dict):
                if hasattr(self.ui, "_disable_bbox_observers"):
                    self.ui._disable_bbox_observers()

                if "north" in self.ui.widgets:
                    self.ui.widgets["north"].value = north_val
                if "south" in self.ui.widgets:
                    self.ui.widgets["south"].value = south_val
                if "east" in self.ui.widgets:
                    self.ui.widgets["east"].value = east_val
                if "west" in self.ui.widgets:
                    self.ui.widgets["west"].value = west_val

                if hasattr(self.ui, "_enable_bbox_observers"):
                    self.ui._enable_bbox_observers()

        except Exception as e:
            print(f"Error updating UI widgets: {e}")

        self._update_visualization_only()

        if (
            hasattr(self.ui, "callbacks")
            and self.ui.callbacks
            and hasattr(self.ui.callbacks, "bbox_manager")
        ):
            self.ui.callbacks.bbox_manager.set_current_bbox(
                (west_val, south_val, east_val, north_val)
            )

    def _update_visualization_only(self):
        """Update only the visualization without triggering events."""
        try:
            self._clear_current_rectangle()

            north = self.current_bbox["north"]
            south = self.current_bbox["south"]
            east = self.current_bbox["east"]
            west = self.current_bbox["west"]

            self.current_rectangle = ipyleaflet.Rectangle(
                bounds=[(south, west), (north, east)],
                color="#1976D2",
                fill_color="#2196F3",
                opacity=0.7,
                fill_opacity=0.05,
                weight=2,
                dash_array="5, 5",
                interactive=False,
                no_click=True,
            )

            self.map_widget.add_layer(self.current_rectangle)

        except Exception as e:
            print(f"Error updating visualization: {e}")

    def get_map_widget(self):
        """Get the iPyLeaflet map widget for display."""
        return self.map_widget

    def clear_drawings(self):
        """Clear all drawings from the map."""
        if self.draw_control:
            self.draw_control.clear()
        self._clear_current_rectangle()

    def disable_center_protection(self):
        """Disable center protection system temporarily."""
        self.center_protection_enabled = False

    def enable_center_protection(self):
        """Enable center protection system."""
        self.center_protection_enabled = True

    def set_center_and_zoom(self, center, zoom):
        """Manually set center and zoom with proper protection handling."""
        with self._temporarily_allow_view_changes():
            self.map_widget.center = center
            self.map_widget.zoom = zoom

    def fit_to_bbox(self):
        """Fit map view to current bounding box."""
        if self.current_bbox:
            north = self.current_bbox["north"]
            south = self.current_bbox["south"]
            east = self.current_bbox["east"]
            west = self.current_bbox["west"]

            bounds = [(south, west), (north, east)]

            with self._temporarily_allow_view_changes():
                self.map_widget.fit_bounds(bounds)
        else:
            print("No bounding box available to fit to")

    def reset_map_view(self):
        """Reset map to default view."""
        with self._temporarily_allow_view_changes():
            self.map_widget.center = self.default_center
            self.map_widget.zoom = self.default_zoom

    def add_observation_marker(self, marker_data):
        """Add observation station marker to map."""
        try:
            station_id = marker_data["station_id"]
            lat = marker_data["lat"]
            lon = marker_data["lon"]

            marker = ipyleaflet.CircleMarker(
                location=(lat, lon),
                radius=8,
                color="#949190",
                fill_color="#949190",
                fill_opacity=0.8,
                opacity=1.0,
                weight=2,
            )

            popup_html = marker_data.get(
                "popup_info", f"<div>Station {station_id}</div>"
            )
            marker.popup = ipyleaflet.Popup(
                child=widgets.HTML(popup_html),
                close_button=True,
                auto_close=True,
                max_width=300,
            )

            self.observation_markers[station_id] = marker
            self.observation_layer_group.add_layer(marker)

        except Exception as e:
            print(f"Error adding observation marker: {e}")

    def clear_observation_markers(self):
        """Clear all observation markers."""
        self.observation_layer_group.clear_layers()
        self.observation_markers.clear()

    def set_data_loaded_status(self, loaded=True):
        """Set data loaded status for auto-plotting."""
        self.data_loaded = loaded

    def enable_auto_plotting(self):
        """Enable automatic plotting on map clicks."""
        self.auto_plotting_enabled = True

    def disable_auto_plotting(self):
        """Disable automatic plotting on map clicks."""
        self.auto_plotting_enabled = False

    def update_plotting_manager_points(self):
        """Update connected plotting manager with current point."""
        self._update_plotting_manager_with_single_point()

    def add_point_for_plot_type(self, lat, lon, plot_type):
        """Add a point specifically for a given plot type with bbox validation."""
        try:
            if not self.is_point_in_bbox(lat, lon):
                if hasattr(self.ui, "show_alert_message"):
                    self.ui.show_alert_message(
                        f"Cannot add point for {plot_type}: coordinates are outside geographic area",
                        "error",
                        section="plotting",
                        permanent=True,
                    )
                return None

            if hasattr(self.ui, "current_plot_type"):
                old_plot_type = self.ui.current_plot_type
                self.ui.current_plot_type = plot_type

            if self.selected_point:
                self._remove_current_point()

            point_id = self._add_single_point(lat, lon)

            if hasattr(self.ui, "current_plot_type") and "old_plot_type" in locals():
                self.ui.current_plot_type = old_plot_type

            self._update_plotting_manager_with_single_point()

            return point_id

        except Exception as e:
            print(f"Error adding point for plot type {plot_type}: {e}")
            return None

    def clear_points_for_plot_type(self, plot_type=None):
        """Clear the selected point."""
        try:
            if self.selected_point:
                self._remove_current_point()
                self._update_plotting_manager_with_single_point()

                if hasattr(self.ui, "show_alert_message"):
                    plot_name = plot_type or self.selected_point.get(
                        "plot_type", "analysis"
                    )
                    self.ui.show_alert_message(
                        f"Cleared {plot_name} point",
                        "info",
                        section="plotting",
                        permanent=True,
                    )

        except Exception as e:
            print(f"Error clearing point for plot type: {e}")

    def get_point_count_for_plot_type(self, plot_type):
        """Get number of selected points for a specific plot type (always 0 or 1)."""
        if self.selected_point and self.selected_point.get("plot_type") == plot_type:
            return 1
        return 0

    def validate_and_warn_bbox_constraints(self, lat, lon):
        """Validate point against bbox and provide detailed warning if outside."""
        if not self.is_point_in_bbox(lat, lon):
            bbox = self.get_current_bbox()
            if bbox:
                return {
                    "valid": False,
                    "message": f"Point ({lat:.3f}°N, {lon:.3f}°E) is outside geographic area: "
                    f"N:{bbox['north']:.2f}° S:{bbox['south']:.2f}° "
                    f"E:{bbox['east']:.2f}° W:{bbox['west']:.2f}°",
                }
            else:
                return {
                    "valid": False,
                    "message": "Cannot validate point: no geographic area defined",
                }
        return {"valid": True, "message": "Point is within geographic area"}


class WeatherMapHandlerExtension:
    """SIMPLIFIED extension for single-point auto-plotting integration."""

    def __init__(self, map_handler):
        """Initialize with existing map handler."""
        self.map_handler = map_handler
        self.click_callback = None

    def set_click_callback(self, callback):
        """Set callback function for map clicks."""
        self.click_callback = callback

    def add_point_marker(self, lat, lon, point_id=None):
        """Add a visual marker for a selected point - validates bbox first."""
        try:
            if not self.map_handler.is_point_in_bbox(lat, lon):
                return None

            if hasattr(self.map_handler, "_add_single_point"):
                result = self.map_handler._add_single_point(lat, lon)

                return result
            else:
                return "P1"

        except Exception:
            return None

    def clear_point_markers(self):
        """Clear the point marker from map."""
        try:
            if hasattr(self.map_handler, "clear_all_points"):
                self.map_handler.clear_all_points()
            else:
                print("Cleared point marker")

        except Exception as e:
            print(f"Could not clear markers: {e}")

    def remove_point_marker(self, point_id):
        """Remove the point marker."""
        try:
            if hasattr(self.map_handler, "_remove_current_point"):
                self.map_handler._remove_current_point()
            else:
                print(f"Removed marker for point {point_id}")

        except Exception as e:
            print(f"Could not remove marker {point_id}: {e}")
