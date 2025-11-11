import os
from datetime import datetime, timedelta

from helpers.parameter_mapper import ConfigurationManager


class WidgetObserverManager:
    """Handles all widget event observers and callbacks."""

    def __init__(self, widgets_dict, ui_instance, layout_manager):
        """Initialize observer manager."""
        self.widgets = widgets_dict
        self.ui = ui_instance
        self.layout_manager = layout_manager
        self.callbacks = None
        self._bbox_observers_enabled = True
        self.config_manager = ConfigurationManager()

    def setup_all_observers(self):
        """Set up all widget observers."""
        self._setup_data_source_observers()
        self._setup_model_date_observers()
        self._setup_bbox_observers()
        self._setup_observation_observers()
        self._setup_parameter_observers()
        self._setup_validation_observers()
        self._setup_button_observers()
        self._setup_unit_observers()

    def set_callbacks(self, callbacks):
        """Set the callback handler."""
        self.callbacks = callbacks

    def _setup_data_source_observers(self):
        """Set up data source selection observers."""

        def on_data_source_change(change):
            is_local = change["new"] == "local"

            models = self.config_manager.models
            local_widgets = ["load_both_btn"]
            for model_key in models.keys():
                model_short = model_key.split("-")[0]
                local_widgets.append(f"browse_btn_{model_short}")

            for widget_name in local_widgets:
                if widget_name not in self.widgets:
                    continue

                if widget_name == "load_both_btn":
                    any_file_selected = any(
                        self.ui.selected_file_paths.get(model_key.split("-")[0])
                        is not None
                        for model_key in models.keys()
                    )
                    self.widgets[widget_name].disabled = (
                        not is_local or not any_file_selected
                    )
                else:
                    self.widgets[widget_name].disabled = not is_local

            mars_widgets = [
                "param",
                "model",
                "start_date",
                "time",
                "grid_resolution",
                "preview_btn",
                "retrieve_btn",
                "north",
                "south",
                "east",
                "west",
                "reset_bbox_btn",
            ]
            for widget_name in mars_widgets:
                self.widgets[widget_name].disabled = is_local

            self.layout_manager.update_data_section(change["new"])

            self.widgets["local_info_display"].value = ""
            self.widgets["mars_info_display"].value = ""

        self.widgets["data_source"].observe(on_data_source_change, names="value")

    def _setup_model_date_observers(self):
        """Set up model and date selection observers."""

        def on_model_or_date_change(change=None):  # noqa: ARG001
            try:
                selected_models = list(self.widgets["model"].value)
                if not selected_models:
                    self.widgets["forecast_steps"].options = []
                    return

                start_date = self.widgets["start_date"].value

                if len(selected_models) > 1:
                    available_steps = list(range(0, 361, 6))
                else:
                    primary_model = selected_models[0]
                    try:
                        available_steps = self.config_manager.generate_steps(
                            start_step=0,
                            end_step=360,
                            model=primary_model,
                            forecast_date=start_date,
                        )
                    except Exception as e:
                        print(f"Error generating steps for {primary_model}: {e}")
                        # Fallback to 6-hourly
                        available_steps = list(range(0, 361, 6))

                step_options = [(f"{step}h", step) for step in available_steps]
                self.widgets["forecast_steps"].options = step_options
                self.widgets["forecast_steps"].value = available_steps

                if available_steps:
                    max_step = max(available_steps)
                    start_time_str = self.widgets["time"].value
                    start_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
                    start_datetime = datetime.combine(start_date, start_time)
                    calculated_datetime = start_datetime + timedelta(hours=max_step)
                    self.widgets["end_date"].value = calculated_datetime.date()

            except Exception as e:
                print(f"Error updating forecast steps: {e}")

        def on_steps_change(change):
            try:
                selected_steps = list(change["new"])
                if not selected_steps:
                    return

                start_date = self.widgets["start_date"].value
                start_time_str = self.widgets["time"].value
                max_step = max(selected_steps)

                start_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
                start_datetime = datetime.combine(start_date, start_time)
                calculated_datetime = start_datetime + timedelta(hours=max_step)

                self._disable_bbox_observers()
                try:
                    self.widgets["end_date"].value = calculated_datetime.date()
                finally:
                    self._enable_bbox_observers()

            except Exception as e:
                print(f"Error updating end date from steps: {e}")

        self.widgets["model"].observe(on_model_or_date_change, names="value")
        self.widgets["start_date"].observe(on_model_or_date_change, names="value")
        self.widgets["forecast_steps"].observe(on_steps_change, names="value")

    def _setup_bbox_observers(self):
        """Set up bounding box coordinate observers."""

        def validate_bounds_and_update_map(change):
            if not self._bbox_observers_enabled:
                return

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

            if (
                coord_name == "north"
                and self.widgets["north"].value <= self.widgets["south"].value
            ):
                self.widgets["south"].value = self.widgets["north"].value - 0.1
            elif (
                coord_name == "south"
                and self.widgets["south"].value >= self.widgets["north"].value
            ):
                self.widgets["north"].value = self.widgets["south"].value + 0.1

            if (
                coord_name == "east"
                and self.widgets["east"].value <= self.widgets["west"].value
            ):
                self.widgets["west"].value = self.widgets["east"].value - 0.1
            elif (
                coord_name == "west"
                and self.widgets["west"].value >= self.widgets["east"].value
            ):
                self.widgets["east"].value = self.widgets["west"].value + 0.1

            if self.callbacks and hasattr(
                self.callbacks, "on_bbox_coordinates_changed"
            ):
                self.callbacks.on_bbox_coordinates_changed(change)

            self.ui.trigger_observation_bbox_update()

        for coord in ["north", "south", "east", "west"]:
            self.widgets[coord].observe(validate_bounds_and_update_map, names="value")

    def _setup_observation_observers(self):  # noqa: PLR0915
        """Set up observation-related observers."""

        def on_obs_folder_path_change(change):
            folder_path = change["new"].strip()

            if folder_path:
                self.ui.selected_observation_folder = folder_path
                folder_name = os.path.basename(folder_path)
                self.widgets[
                    "obs_folder_display"
                ].value = f'<p style="color: #666; margin: 2px 0;">📁 {folder_name}</p>'

                self.ui._perform_automatic_validation()
            else:
                self.ui.selected_observation_folder = None
                self.widgets[
                    "obs_folder_display"
                ].value = '<p style="color: #666; font-style: italic;">No observation folder selected</p>'
                self.ui.observation_parameter_validated = False
                self.widgets["observations_checkbox"].disabled = True
                self.widgets["observations_checkbox"].value = False

        self.widgets["obs_folder_path_input"].observe(
            on_obs_folder_path_change, names="value"
        )

        def on_has_observations_change(change):
            """Handle when 'Do you have observation data?' changes."""
            has_obs = change["new"] == "yes"

            if has_obs:
                current_mode = self.widgets["retrieve_observations"].value

                if current_mode == "browse":
                    self.widgets["browse_obs_btn"].disabled = False
                    self.widgets["obs_folder_path_input"].disabled = False
                elif current_mode == "retrieve":
                    retrieval_widgets = [
                        "obs_sources",
                        "obs_period",
                        "obs_start_date",
                        "obs_end_date",
                        "obs_output_dir",
                        "retrieve_obs_btn",
                        "stvl_path",
                    ]
                    for widget_name in retrieval_widgets:
                        if widget_name in self.widgets:
                            self.widgets[widget_name].disabled = False

                    self.widgets["browse_obs_btn"].disabled = True
            else:
                all_obs_widgets = [
                    "browse_obs_btn",
                    "obs_sources",
                    "obs_period",
                    "obs_start_date",
                    "obs_end_date",
                    "obs_output_dir",
                    "retrieve_obs_btn",
                    "stvl_path",
                ]
                for widget_name in all_obs_widgets:
                    if widget_name in self.widgets:
                        self.widgets[widget_name].disabled = True

        def on_obs_retrieval_mode_change(change):
            """Handle when retrieval mode changes between browse/retrieve."""
            is_retrieve_mode = change["new"] == "retrieve"
            has_observations = self.widgets["has_observations"].value == "yes"

            if has_observations:
                if is_retrieve_mode:
                    retrieval_widgets = [
                        "obs_sources",
                        "obs_period",
                        "obs_start_date",
                        "obs_end_date",
                        "obs_output_dir",
                        "retrieve_obs_btn",
                        "stvl_path",
                    ]
                    for widget_name in retrieval_widgets:
                        if widget_name in self.widgets:
                            self.widgets[widget_name].disabled = False

                    self.widgets["browse_obs_btn"].disabled = True
                else:
                    retrieval_widgets = [
                        "obs_sources",
                        "obs_period",
                        "obs_start_date",
                        "obs_end_date",
                        "obs_output_dir",
                        "retrieve_obs_btn",
                        "stvl_path",
                    ]
                    for widget_name in retrieval_widgets:
                        if widget_name in self.widgets:
                            self.widgets[widget_name].disabled = True
                    self.widgets["browse_obs_btn"].disabled = False

            self.layout_manager.update_observation_section(change["new"])

        self.widgets["has_observations"].observe(
            on_has_observations_change, names="value"
        )

        self.widgets["retrieve_observations"].observe(
            on_obs_retrieval_mode_change, names="value"
        )

        def on_obs_period_change(change):  # noqa: ARG001
            if (
                self.widgets["retrieve_observations"].value == "retrieve"
                and self.widgets["processing_param"].value != "none"
            ):
                forecast_param = self.widgets["processing_param"].value
                self.ui.update_observation_retrieval_from_forecast_param(forecast_param)

        self.widgets["retrieve_observations"].observe(
            on_obs_retrieval_mode_change, names="value"
        )
        self.widgets["obs_period"].observe(on_obs_period_change, names="value")

    def _setup_parameter_observers(self):
        """Set up parameter selection observers."""

        def on_param_change(change):
            selected_param = change["new"]

            if self.ui.selected_observation_folder:
                self.ui.observation_parameter_validated = False
                self.ui._perform_automatic_validation()

            is_deaccumulation = selected_param in [
                "tp_deaccum",
                "cp_deaccum",
                "lsp_deaccum",
            ]
            is_precipitation_param = selected_param in [
                "tp",
                "tp_deaccum",
                "cp",
                "cp_deaccum",
                "lsp",
                "lsp_deaccum",
            ]
            is_temperature_param = selected_param in [
                "2t",
                "2d",
                "2t_24h_max",
                "2t_24h_min",
                "2d_24h_max",
                "2d_24h_min",
            ]

            self.widgets["precipitation_interval"].disabled = not is_deaccumulation

            if "precipitation_container" in self.widgets:
                display_precip = "block" if is_deaccumulation else "none"
                self.widgets["precipitation_container"].layout.display = display_precip

            if "units_container" in self.widgets:
                display_units = (
                    "block"
                    if (is_temperature_param or is_precipitation_param)
                    else "none"
                )
                self.widgets["units_container"].layout.display = display_units

                if is_temperature_param or is_precipitation_param:
                    temp_display = "block" if is_temperature_param else "none"
                    precip_display = "block" if is_precipitation_param else "none"

                    self.widgets["temperature_unit"].layout.display = temp_display
                    self.widgets["precipitation_unit"].layout.display = precip_display
                else:
                    self.widgets["temperature_unit"].layout.display = "none"
                    self.widgets["precipitation_unit"].layout.display = "none"

            if self.widgets["retrieve_observations"].value == "retrieve":
                self.ui.update_observation_retrieval_from_forecast_param(selected_param)

            if self.callbacks and hasattr(self.callbacks, "on_multi_point_update"):
                self.callbacks.on_multi_point_update(
                    self.ui.map_handler.get_selected_points()
                )

        self.widgets["processing_param"].observe(on_param_change, names="value")

    def _setup_validation_observers(self):
        """Set up validation observers."""

        def validate_grid(change):
            try:
                value_str = change["new"].strip()
                if value_str:
                    value = float(value_str)
                    if value <= 0:
                        change["owner"].value = ""
            except ValueError:
                change["owner"].value = ""

        self.widgets["grid_resolution"].observe(validate_grid, names="value")

    def _setup_button_observers(self):
        """Set up button click observers."""
        models = self.config_manager.models

        for model_key in models.keys():
            model_short = model_key.split("-")[0]

            def create_file_path_observer(mt):
                def on_file_path_change(change):
                    file_path = change["new"].strip()
                    self.ui.selected_file_paths[mt] = file_path if file_path else None

                    any_file_selected = any(
                        self.ui.selected_file_paths.get(m.split("-")[0]) is not None
                        for m in models.keys()
                    )

                    self.widgets["load_both_btn"].disabled = (
                        self.widgets["data_source"].value != "local"
                        or not any_file_selected
                    )

                    if file_path:
                        file_name = os.path.basename(file_path)
                        self.widgets[
                            f"selected_file_{mt}"
                        ].value = (
                            f'<p style="color: #666; margin: 2px 0;"> {file_name}</p>'
                        )
                    else:
                        self.widgets[
                            f"selected_file_{mt}"
                        ].value = f'<p style="color: #666; font-style: italic;">No {mt.upper()} file selected</p>'

                    self.ui._update_local_info_display()

                return on_file_path_change

            widget_name = f"file_path_input_{model_short}"
            if widget_name in self.widgets:
                self.widgets[widget_name].observe(
                    create_file_path_observer(model_short), names="value"
                )

        for model_key in models.keys():
            model_short = model_key.split("-")[0]
            browse_btn_name = f"browse_btn_{model_short}"
            if browse_btn_name in self.widgets:

                def create_browse_handler(ms):
                    return lambda b: self.ui._browse_for_file(ms)

                self.widgets[browse_btn_name].on_click(
                    create_browse_handler(model_short)
                )

        self.widgets["browse_obs_btn"].on_click(self.ui._browse_for_observation_folder)

        self.widgets["refresh_params_btn"].on_click(self.ui._refresh_parameters)
        self.widgets["reset_bbox_btn"].on_click(self.ui._reset_bbox)
        self.widgets["clear_drawings_btn"].on_click(self.ui._clear_drawings)
        self.widgets["reset_btn"].on_click(self.ui._reset_all)
        self.widgets["retrieve_obs_btn"].on_click(self.ui._handle_retrieve_observations)

        def on_clear_all_points(button):  # noqa: ARG001
            if self.ui.map_handler:
                self.ui.map_handler.clear_all_points()
                if self.callbacks:
                    self.callbacks.on_multi_point_update({})

        self.widgets["clear_points_btn"].on_click(on_clear_all_points)

    def _setup_unit_observers(self):
        """Set up unit selection observers (dynamically from config)."""

        def on_model_change(change):  # noqa: ARG001
            if self.callbacks:
                self.callbacks.on_model_selection_change()

        def on_temperature_unit_change(change):
            new_unit = change["new"]
            if (
                self.callbacks
                and hasattr(self.callbacks, "plotting_manager")
                and self.callbacks.plotting_manager
            ):
                self.callbacks.plotting_manager.set_temperature_unit(new_unit)

                selected_param = self.widgets["processing_param"].value
                if (
                    selected_param
                    in [
                        "2t",
                        "2d",
                        "2t_24h_max",
                        "2t_24h_min",
                        "2d_24h_max",
                        "2d_24h_min",
                    ]
                    and hasattr(self.callbacks, "multi_point_data")
                    and self.callbacks.multi_point_data
                ):
                    self.callbacks.on_model_selection_change()

        def on_precipitation_unit_change(change):
            new_unit = change["new"]
            if (
                self.callbacks
                and hasattr(self.callbacks, "plotting_manager")
                and self.callbacks.plotting_manager
            ):
                self.callbacks.plotting_manager.set_precipitation_unit(new_unit)

                selected_param = self.widgets["processing_param"].value
                if (
                    selected_param
                    in ["tp", "tp_deaccum", "cp", "cp_deaccum", "lsp", "lsp_deaccum"]
                    and hasattr(self.callbacks, "multi_point_data")
                    and self.callbacks.multi_point_data
                ):
                    self.callbacks.on_model_selection_change()

        def on_precipitation_interval_change(change):
            interval = change["new"]
            if (
                self.callbacks
                and hasattr(self.callbacks, "precipitation_processor")
                and self.widgets["processing_param"].value
                in ["tp_deaccum", "cp_deaccum", "lsp_deaccum"]
            ):
                self.callbacks.update_precipitation_interval(interval)

                if (
                    hasattr(self.callbacks, "multi_point_data")
                    and self.callbacks.multi_point_data
                ):
                    self.callbacks.on_multi_point_update(
                        self.callbacks.map_handler.get_selected_points()
                    )

        models = self.config_manager.models
        for model_key in models.keys():
            model_short = model_key.split("-")[0]
            checkbox_name = f"{model_short}_checkbox"
            if checkbox_name in self.widgets:
                self.widgets[checkbox_name].observe(on_model_change, names="value")

        self.widgets["observations_checkbox"].observe(on_model_change, names="value")

        self.widgets["temperature_unit"].observe(
            on_temperature_unit_change, names="value"
        )
        self.widgets["precipitation_unit"].observe(
            on_precipitation_unit_change, names="value"
        )
        self.widgets["precipitation_interval"].observe(
            on_precipitation_interval_change, names="value"
        )

    def _disable_bbox_observers(self):
        """Temporarily disable bbox observers."""
        self._bbox_observers_enabled = False

    def _enable_bbox_observers(self):
        """Re-enable bbox observers."""
        self._bbox_observers_enabled = True
