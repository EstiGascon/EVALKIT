import time
import traceback
from math import asin, cos, radians, sin, sqrt

import ipyleaflet
import ipywidgets as widgets


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in km."""
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


class WeatherMapHandler:
    """Interactive map handler for forecast points and observation stations."""

    def __init__(self, ui_instance):
        """Initialize the map handler."""
        self.ui = ui_instance
        self.map_widget = None
        self.draw_control = None
        self.current_bbox = None
        self.current_rectangle = None
        self.default_center = (53.0, 10.0)
        self.default_zoom = 4

        self.selected_points = {}
        self.point_counter = 0
        # Okabe-Ito palette (Wong 2011, Nature Methods) — safe for all major
        # forms of colour blindness. Black is excluded here (reserved for
        # Observations in the plot). The list is long enough for the maximum
        # number of selectable points by cycling through the palette.
        _cb_palette = [
            "#0072B2",  # Blue
            "#D55E00",  # Vermillion
            "#009E73",  # Bluish Green
            "#E69F00",  # Orange
            "#CC79A7",  # Reddish Purple
            "#56B4E9",  # Sky Blue
        ]
        self.active_point_colors = (_cb_palette * 20)[:100]

        self.observation_markers = {}
        self.observation_geojson_layer = None
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

        self.setup_map()

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
            layout=widgets.Layout(width="100%", height="500px"),
        )

        self.forecast_layer_group = ipyleaflet.LayerGroup(name="forecast_points")
        self.observation_layer_group = ipyleaflet.LayerGroup(
            name="observation_stations"
        )

        self.map_widget.add_layer(self.forecast_layer_group)
        self.map_widget.add_layer(self.observation_layer_group)

        scale_control = ipyleaflet.ScaleControl(position="bottomleft")
        self.map_widget.add_control(scale_control)

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
        self.draw_control.edit = False

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
        """Handle all map interactions."""
        if kwargs.get("type") == "click":
            coordinates = kwargs.get("coordinates")
            if coordinates:
                lat, lon = coordinates

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

                self._process_unified_click(lat, lon)

                if (
                    self.map_widget.center != current_center
                    or self.map_widget.zoom != current_zoom
                ):
                    with self._temporarily_allow_view_changes():
                        self.map_widget.center = current_center
                        self.map_widget.zoom = current_zoom

    def _process_unified_click(self, lat, lon):
        """Process click events with bbox constraint validation."""
        if not self._is_point_in_bbox(lat, lon):
            return

        clicked_point_id = self._find_nearby_point(lat, lon, threshold_km=1)

        if clicked_point_id:
            self._remove_unified_point(clicked_point_id)
        else:
            clicked_station_id = self._find_nearby_observation_station(
                lat, lon, threshold_km=0.5
            )

            if clicked_station_id:
                self._toggle_observation_station(clicked_station_id)
            else:
                self._add_unified_forecast_point(lat, lon)

        self._update_unified_plot()

    def _add_unified_forecast_point(self, lat, lon):
        """Add a new forecast point with unified color management (only if in bbox)."""
        if not self._is_point_in_bbox(lat, lon):
            return False

        try:
            self.point_counter += 1
            point_id = f"forecast_{self.point_counter}"

            color_index = len(self.selected_points) % len(self.active_point_colors)
            color = self.active_point_colors[color_index]

            circle_marker = ipyleaflet.CircleMarker(
                location=(lat, lon),
                radius=8,
                color=color,
                fill_color=color,
                fill_opacity=0.8,
                weight=3,
                opacity=1.0,
                interactive=True,
            )

            popup_html = widgets.HTML(
                value=f"""
                <div style="padding: 10px; border-left: 4px solid {color};">
                    <b style="color: {color};"> Forecast Point {self.point_counter}</b><br>
                    Lat: {lat:.4f}°<br>
                    Lon: {lon:.4f}°<br>
                    <span style="color: {color}; font-weight: bold;">●</span> Plot Color<br>
                    <em>Click again to remove</em>
                </div>
                """
            )
            circle_marker.popup = ipyleaflet.Popup(
                child=popup_html, close_button=True, max_width=200
            )

            self.selected_points[point_id] = {
                "lat": lat,
                "lon": lon,
                "marker": circle_marker,
                "color": color,
                "label": f"Forecast Point {self.point_counter}",
                "type": "forecast",
            }

            self.forecast_layer_group.add_layer(circle_marker)

            if hasattr(self.ui, "widgets") and "mars_info_display" in self.ui.widgets:
                self.ui.widgets["mars_info_display"].value = ""

            return True

        except Exception as e:
            print(f" Error adding forecast point: {e}")
            return False

    def _toggle_observation_station(self, station_id):
        """Toggle observation station selection (only if in bbox)."""
        try:
            if (
                hasattr(self.ui, "callbacks")
                and hasattr(self.ui.callbacks, "observation_stations_gdf")
                and self.ui.callbacks.observation_stations_gdf is not None
                and station_id in self.ui.callbacks.observation_stations_gdf.index
            ):
                station_info = self.ui.callbacks.observation_stations_gdf.loc[
                    station_id
                ]
                station_lat = station_info["latitude"]
                station_lon = station_info["longitude"]

                if not self._is_point_in_bbox(station_lat, station_lon):
                    return False

            obs_point_id = f"obs_{station_id}"

            if obs_point_id in self.selected_points:
                del self.selected_points[obs_point_id]
                self._update_observation_marker_color(
                    station_id, "#949190", selected=False
                )

            elif (
                hasattr(self.ui, "callbacks")
                and hasattr(self.ui.callbacks, "observation_stations_gdf")
                and self.ui.callbacks.observation_stations_gdf is not None
                and station_id in self.ui.callbacks.observation_stations_gdf.index
            ):
                station_info = self.ui.callbacks.observation_stations_gdf.loc[
                    station_id
                ]
                lat = station_info["latitude"]
                lon = station_info["longitude"]

                color_index = len(self.selected_points) % len(self.active_point_colors)
                color = self.active_point_colors[color_index]

                self.selected_points[obs_point_id] = {
                    "lat": lat,
                    "lon": lon,
                    "marker": self.observation_markers.get(station_id),
                    "color": color,
                    "label": f"Station {station_id}",
                    "type": "observation",
                    "station_id": station_id,
                }

                self._update_observation_marker_color(
                    station_id, color, selected=True
                )

                if (
                    hasattr(self.ui, "widgets")
                    and "mars_info_display" in self.ui.widgets
                ):
                    self.ui.widgets["mars_info_display"].value = ""

            else:
                print(f"          Station {station_id} not found in station data")
                return False

            return True

        except Exception as e:
            print(f"       Error toggling observation station: {e}")
            return False

    def _update_observation_marker_color(self, station_id, color, selected=False):
        """Update the colour of an observation station marker on the map."""
        try:
            # Remove existing marker
            if station_id in self.observation_markers:
                old = self.observation_markers.pop(station_id)
                try:
                    self.observation_layer_group.remove_layer(old)
                except Exception:
                    pass

            # Get station location (needed for both selected and deselected)
            gdf = getattr(getattr(self.ui, "callbacks", None), "observation_stations_gdf", None)
            if gdf is None or station_id not in gdf.index:
                return

            info = gdf.loc[station_id]
            lat, lon = info["latitude"], info["longitude"]

            if not selected:
                # Restore a grey unselected marker so the station stays visible
                grey_marker = ipyleaflet.CircleMarker(
                    location=(lat, lon),
                    radius=5,
                    color="#949190",
                    fill_color="#949190",
                    fill_opacity=0.85,
                    opacity=1.0,
                    weight=1,
                )
                self.observation_markers[station_id] = grey_marker
                self.observation_layer_group.add_layer(grey_marker)
                return

            # Create larger coloured marker for selected station
            new_marker = ipyleaflet.CircleMarker(
                location=(lat, lon),
                radius=10,
                color=color,
                fill_color=color,
                fill_opacity=0.9,
                opacity=1.0,
                weight=3,
            )

            self.observation_markers[station_id] = new_marker
            if f"obs_{station_id}" in self.selected_points:
                self.selected_points[f"obs_{station_id}"]["marker"] = new_marker

            self.observation_layer_group.add_layer(new_marker)

        except Exception as e:
            print(f" Error updating marker color: {e}")

    def _remove_unified_point(self, point_id):
        """Remove a point (forecast or observation) from the map."""
        try:
            if point_id not in self.selected_points:
                return

            point_info = self.selected_points[point_id]
            point_type = point_info["type"]

            if point_type == "forecast":
                if point_info["marker"] in self.forecast_layer_group.layers:
                    self.forecast_layer_group.remove_layer(point_info["marker"])

            elif point_type == "observation":
                station_id = point_info["station_id"]
                self._update_observation_marker_color(
                    station_id, "#FF6B35", selected=False
                )

            del self.selected_points[point_id]

        except Exception as e:
            print(f" Error removing point: {e}")

    def _find_nearby_point(self, lat, lon, threshold_km=8):
        """Find if there's a selected point nearby."""
        for point_id, point_info in self.selected_points.items():
            distance = haversine_distance(
                lat, lon, point_info["lat"], point_info["lon"]
            )
            if distance <= threshold_km:
                return point_id

        return None

    def _find_nearby_observation_station(self, lat, lon, threshold_km=8):
        """Find if there's an observation station nearby."""
        if (
            hasattr(self.ui, "callbacks")
            and hasattr(self.ui.callbacks, "observation_stations_gdf")
            and self.ui.callbacks.observation_stations_gdf is not None
        ):
            for (
                station_id,
                station_info,
            ) in self.ui.callbacks.observation_stations_gdf.iterrows():
                station_lat = station_info["latitude"]
                station_lon = station_info["longitude"]
                distance = haversine_distance(lat, lon, station_lat, station_lon)

                if distance <= threshold_km:
                    return station_id

        return None

    def _update_unified_plot(self):  # noqa: PLR0912
        """Update plot with unified data from all selected points."""
        try:
            unified_points = {}
            observation_count = 0
            forecast_count = 0

            for point_id, point_info in self.selected_points.items():
                point_type = point_info["type"]

                if point_type == "observation":
                    observation_count += 1
                elif point_type == "forecast":
                    forecast_count += 1

                unified_points[point_id] = {
                    "lat": point_info["lat"],
                    "lon": point_info["lon"],
                    "color": point_info["color"],
                    "label": point_info["label"],
                    "type": point_info["type"],
                }

                if point_info["type"] == "observation":
                    unified_points[point_id]["station_id"] = point_info["station_id"]
                    print(
                        f"      {point_id}: Station {point_info['station_id']} at {point_info['lat']:.4f}, {point_info['lon']:.4f} (color: {point_info['color']})"
                    )
                else:
                    print(
                        f"      {point_id}: {point_info['type']} at {point_info['lat']:.4f}, {point_info['lon']:.4f} (color: {point_info['color']})"
                    )

            if hasattr(self.ui, "callbacks"):
                if self.ui.callbacks:
                    print(f"   ✅ Callbacks object exists: {type(self.ui.callbacks)}")

                    if hasattr(self.ui.callbacks, "on_multi_point_update"):
                        for point_id, data in unified_points.items():
                            print(f"      - {point_id}: {data}")

                        try:
                            self.ui.callbacks.on_multi_point_update(unified_points)

                        except Exception as callback_error:
                            print(f"    ERROR in callback: {callback_error}")
                            print(f"      Callback error type: {type(callback_error)}")

                            print("      Full traceback:")
                            traceback.print_exc()  # noqa: F823

                    else:
                        print("    on_multi_point_update method NOT FOUND in callbacks")
                        print(
                            f"   Available methods: {[method for method in dir(self.ui.callbacks) if not method.startswith('_')]}"
                        )
                else:
                    print("    Callbacks object is None")
            else:
                print("    No callbacks attribute found in UI")

            print("    Plot update process completed")

        except Exception as e:
            print(f"    Error in _update_unified_plot: {e}")
            traceback.print_exc()

    def get_selected_points(self):
        """Get all currently selected points in format expected by callbacks."""
        result = {}
        for point_id, point_info in self.selected_points.items():
            result[point_id] = {
                "lat": point_info["lat"],
                "lon": point_info["lon"],
                "color": point_info["color"],
                "label": point_info["label"],
                "type": point_info["type"],
            }

            if point_info["type"] == "observation":
                result[point_id]["station_id"] = point_info["station_id"]

        return result

    def clear_all_points(self):
        """Clear all selected points and restart the process."""
        observation_stations_to_reset = []
        forecast_points_count = 0

        for _point_id, point_info in list(self.selected_points.items()):
            if point_info["type"] == "observation":
                observation_stations_to_reset.append(point_info["station_id"])
            elif point_info["type"] == "forecast":
                forecast_points_count += 1

        self.forecast_layer_group.clear_layers()

        for station_id in observation_stations_to_reset:
            self._update_observation_marker_color(station_id, "#949190", selected=False)

        self.selected_points.clear()

        self.point_counter = 0

        self.last_click_time = 0
        self.last_click_coords = None

        self._update_unified_plot()

        if hasattr(self, "draw_control") and self.draw_control:
            try:
                self.draw_control.clear()
            except Exception as e:
                print(f"Could not clear drawing control: {e}")

    def set_observation_geojson(self, geojson_data):
        """Set observation stations as a single GeoJSON layer (fast)."""
        if self.observation_geojson_layer is not None:
            try:
                self.observation_layer_group.remove_layer(
                    self.observation_geojson_layer
                )
            except Exception:
                pass

        self.observation_geojson_layer = ipyleaflet.GeoJSON(
            data=geojson_data,
            point_style={
                "radius": 5,
                "color": "#949190",
                "fillColor": "#949190",
                "fillOpacity": 0.8,
                "weight": 2,
            },
        )
        self.observation_layer_group.add(self.observation_geojson_layer)

    def clear_observation_markers(self):
        """Clear all observation markers and GeoJSON layer."""
        self.observation_layer_group.clear_layers()
        self.observation_markers.clear()
        self.observation_geojson_layer = None

    def sync_colors_with_plotting_manager(self, plotting_manager):
        """Synchronize colors with plotting manager."""
        if hasattr(plotting_manager, "active_point_colors"):
            self.active_point_colors = plotting_manager.active_point_colors

    def _on_draw_event(self, target, action, geo_json):
        """Handle draw events and automatically update coordinates - FIXED VERSION."""
        self.last_draw_time = time.time()

        if action == "created" and geo_json["geometry"]["type"] == "Polygon":
            coordinates = geo_json["geometry"]["coordinates"][0]
            lons = [coord[0] for coord in coordinates]
            lats = [coord[1] for coord in coordinates]

            min_lon = min(lons)
            max_lon = max(lons)
            min_lat = min(lats)
            max_lat = max(lats)

            self._clear_drawn_rectangles()

            if hasattr(self.ui, "observer_manager"):
                self.ui.observer_manager._disable_bbox_observers()

            try:
                self.ui.widgets["north"].value = max_lat
                self.ui.widgets["south"].value = min_lat
                self.ui.widgets["east"].value = max_lon
                self.ui.widgets["west"].value = min_lon

                self.current_bbox = {
                    "north": max_lat,
                    "south": min_lat,
                    "east": max_lon,
                    "west": min_lon,
                }

            finally:
                if hasattr(self.ui, "observer_manager"):
                    self.ui.observer_manager._enable_bbox_observers()

            self._update_visualization_only()

            if self.ui.widgets["has_observations"].value == "yes":
                self.clear_observation_markers()
                if hasattr(self.ui, "callbacks") and self.ui.callbacks:
                    self.ui.callbacks.load_observation_data_to_map()
                    self.ui.widgets["observations_checkbox"].disabled = False
                    self.ui.widgets["observations_checkbox"].value = True

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

    def _clear_current_rectangle(self):
        """Clear the current rectangle and its info marker from the map."""
        if self.current_rectangle and self.current_rectangle in self.map_widget.layers:
            self.map_widget.remove_layer(self.current_rectangle)

            if hasattr(self.current_rectangle, "_info_marker"):
                if self.current_rectangle._info_marker in self.map_widget.layers:
                    self.map_widget.remove_layer(self.current_rectangle._info_marker)

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

    def _update_visualization_only(self):
        """Update only the visualization without triggering events - FIXED VERSION."""
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
        """Fit map view to current bounding box (manual operation)."""
        if self.current_bbox:
            north = self.current_bbox["north"]
            south = self.current_bbox["south"]
            east = self.current_bbox["east"]
            west = self.current_bbox["west"]

            bounds = [(south, west), (north, east)]

            with self._temporarily_allow_view_changes():
                self.map_widget.fit_bounds(bounds)
        else:
            print(" No bounding box available to fit to")

    def reset_map_view(self):
        """Reset map to default view."""
        with self._temporarily_allow_view_changes():
            self.map_widget.center = self.default_center
            self.map_widget.zoom = self.default_zoom

    def _is_point_in_bbox(self, lat, lon):
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

    def _clear_drawn_rectangles(self):
        """Clear all drawn rectangles from the draw control."""
        try:
            if self.draw_control:
                self.draw_control.clear()
        except Exception as e:
            print(f"Error clearing drawn rectangles: {e}")

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
            if hasattr(self.ui, "observer_manager"):
                self.ui.observer_manager._disable_bbox_observers()

            if hasattr(self.ui, "widgets") and isinstance(self.ui.widgets, dict):
                widget_updates = {
                    "north": north_val,
                    "south": south_val,
                    "east": east_val,
                    "west": west_val,
                }

                for widget_name, value in widget_updates.items():
                    if widget_name in self.ui.widgets:
                        self.ui.widgets[widget_name].value = value

        except Exception as e:
            print(f"Error updating UI widgets: {e}")
        finally:
            if hasattr(self.ui, "observer_manager"):
                self.ui.observer_manager._enable_bbox_observers()

        self._update_visualization_only()
