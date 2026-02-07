"""Observer management for ensemble tool widgets."""

import os


class WidgetObserverManager:
    """Manage all widget observers and event handlers.

    This class centralizes event handling for all UI widgets, connecting
    user interactions to appropriate callbacks and UI updates. It manages
    observers for data source selection, parameter changes, step selection,
    observations, scenarios, and action buttons.

    Attributes:
        widgets: Dictionary containing all widget instances.
        ui: Reference to main UI instance (EnsembleUI).
        layout_manager: UILayoutManager instance for UI updates.
        callbacks: EnsembleCallbacks instance for data operations.

    """

    def __init__(self, widgets_dict, ui_instance, layout_manager):
        """Initialize observer manager.

        Args:
            widgets_dict: Dictionary of all widget instances organized by
                widget type and purpose.
            ui_instance: Reference to main UI instance for state access
                and method calls.
            layout_manager: UILayoutManager instance for managing UI
                layout updates.

        """
        self.widgets = widgets_dict
        self.ui = ui_instance
        self.layout_manager = layout_manager
        self.callbacks = None

    def set_callbacks(self, callbacks):
        """Set callbacks instance for action handlers.

        Args:
            callbacks: EnsembleCallbacks instance for handling data
                operations and plot generation.

        """
        self.callbacks = callbacks

    def setup_all_observers(self):
        """Set up all widget observers and event handlers.

        Initializes observers for all interactive widgets including data
        source selection, parameter changes, step selection, observations,
        scenarios, action buttons, and coordinate inputs.
        """
        self._setup_data_source_observer()
        self._setup_parameter_observer()
        self._setup_step_selection_observers()
        self._setup_observation_observers()
        self._setup_scenario_observers()
        self._setup_action_button_observers()
        self._setup_manual_coordinate_observer()

    def _setup_data_source_observer(self):
        """Set up observer for data source selection changes.

        Monitors changes to the data source radio button (MARS vs local)
        and triggers configuration section updates when plot type is selected.
        """

        def on_data_source_change(change):
            self.ui.current_data_source = change["new"]
            if self.ui.current_plot_type:
                self.ui._update_configuration_section()

        self.widgets["data_source_radio"].observe(on_data_source_change, names="value")

    def _setup_parameter_observer(self):
        """Set up observer for parameter selection changes.

        Monitors parameter selection widget and updates auto-plot parameter
        and unit settings when a new parameter is selected.
        """

        def on_parameter_change(change):
            if self._is_valid_parameter_selection(change["new"]):
                self.ui.auto_plot_parameter = change["new"][0]
                self.ui._update_auto_plot_unit()

        self.widgets["parameters"].observe(on_parameter_change, names="value")

    def _is_valid_parameter_selection(self, selected_params):
        """Check if parameter selection is valid.

        Args:
            selected_params: List of selected parameter values.

        Returns:
            Boolean indicating if selection contains at least one parameter.

        """
        return selected_params and len(selected_params) > 0

    def _setup_step_selection_observers(self):
        """Set up observers for step selection widgets.

        Configures observers for select all, deselect all, and step range
        input changes. Handles dynamic step list generation based on
        input range.
        """
        self.widgets["select_all_steps"].on_click(self._on_select_all_steps)
        self.widgets["deselect_all_steps"].on_click(self._on_deselect_all_steps)
        self.widgets["steps"].observe(self._on_steps_change, names="value")

    def _on_select_all_steps(self, *_args):
        """Handle select all steps button click.

        Selects all available step values in the steps display widget.
        """
        if self.widgets["steps_display"].options:
            all_values = [option[1] for option in self.widgets["steps_display"].options]
            self.widgets["steps_display"].value = all_values

    def _on_deselect_all_steps(self, *_args):
        """Handle deselect all steps button click.

        Clears all selected step values in the steps display widget.
        """
        self.widgets["steps_display"].value = []

    def _on_steps_change(self, change):
        """Handle changes to step input field.

        Processes step range input and updates step selection display
        with available steps if input is a valid range.

        Args:
            change: Change dictionary containing the new step input value.

        """
        steps_input = change["new"]

        if self.ui._is_step_range(steps_input):
            self._process_step_range(steps_input)
        else:
            self._hide_step_selection_widgets()

    def _process_step_range(self, steps_input):
        """Process step range input and update display.

        Args:
            steps_input: Step range string (e.g., '0-240').

        """
        available_steps = self.ui._get_available_steps_for_range(steps_input)

        if available_steps:
            self._show_step_selection(available_steps)
        else:
            self._hide_step_selection_widgets()

    def _show_step_selection(self, available_steps):
        """Show step selection widgets with available steps.

        Args:
            available_steps: List of available step values.

        """
        step_options = [(f"Step {step}h", step) for step in available_steps]
        self.widgets["steps_display"].options = step_options
        self.widgets["steps_display"].value = available_steps
        self.widgets["steps_display"].layout.display = "block"
        self.widgets["step_buttons"].layout.display = "block"

    def _hide_step_selection_widgets(self):
        """Hide step selection display and buttons."""
        self.widgets["steps_display"].layout.display = "none"
        self.widgets["step_buttons"].layout.display = "none"

    def _setup_observation_observers(self):
        """Set up observers for observation widgets.

        Configures observers for observation enable toggle and data source
        selection (browse vs retrieve). Manages visibility and enabled state
        of observation-related widgets.
        """
        self.widgets["has_observations"].observe(
            self._on_has_observations_change, names="value"
        )
        self.widgets["obs_data_source"].observe(
            self._on_obs_source_change, names="value"
        )

    def _on_has_observations_change(self, change):
        """Handle observation enable/disable toggle.

        Shows or hides observation sections based on whether observations
        are enabled. Resets observation widgets when disabled.

        Args:
            change: Change dictionary containing the new toggle value.

        """
        has_obs = change["new"] == "yes"

        if not hasattr(self.layout_manager, "observation_container"):
            return

        try:
            if hasattr(self.layout_manager, "data_source_row"):
                self._update_data_source_visibility(has_obs)
        except Exception as e:
            print(f"Error updating observation visibility: {e}")

    def _update_data_source_visibility(self, has_obs):
        """Update visibility of observation data source section.

        Args:
            has_obs: Boolean indicating if observations are enabled.

        """
        if has_obs:
            self.layout_manager.data_source_row.layout.display = "block"
            current_source = self.widgets["obs_data_source"].value
            self._update_observation_section_visibility(current_source)
        else:
            self._hide_all_observation_sections()

    def _hide_all_observation_sections(self):
        """Hide all observation-related sections and reset widgets."""
        self.layout_manager.data_source_row.layout.display = "none"

        if hasattr(self.layout_manager, "browse_section"):
            self.layout_manager.browse_section.layout.display = "none"

        if hasattr(self.layout_manager, "retrieve_section"):
            self.layout_manager.retrieve_section.layout.display = "none"

        self._reset_observation_widgets()

    def _on_obs_source_change(self, change):
        """Handle observation data source selection change.

        Updates button text and widget enabled states based on whether
        user selected browse or retrieve mode.

        Args:
            change: Change dictionary containing the new source value.

        """
        is_retrieve = change["new"] == "retrieve"

        # Update button text
        self._update_retrieve_button_text(change["new"])

        # Update section visibility if observations are enabled
        if self.widgets["has_observations"].value == "yes":
            self._update_observation_section_visibility(change["new"])
            self._update_observation_widget_states(is_retrieve)

    def _update_retrieve_button_text(self, source):
        """Update retrieve button text based on data source.

        Args:
            source: Data source value ('browse' or 'retrieve').

        """
        if source == "browse":
            self.widgets["retrieve_obs_btn"].description = "Load Data"
        else:
            self.widgets["retrieve_obs_btn"].description = "Retrieve Observations"

    def _update_observation_widget_states(self, is_retrieve):
        """Update enabled/disabled state of observation widgets.

        Args:
            is_retrieve: Boolean indicating if in retrieve mode.

        """
        retrieve_widgets = [
            "obs_parameters",
            "obs_sources",
            "obs_period",
            "obs_times_display",
            "obs_start_date",
            "obs_end_date",
            "obs_output_dir",
            "browse_output_btn",
            "retrieve_obs_btn",
        ]

        for widget_name in retrieve_widgets:
            if widget_name in self.widgets:
                self.widgets[widget_name].disabled = not is_retrieve

        self.widgets["browse_obs_btn"].disabled = is_retrieve

    def _setup_observation_observers(self):
        """Set up observers for observation widgets.

        Configures observers for all observation-related widgets including
        parameter selection, period changes, folder path input, and button
        clicks for browsing and retrieval.
        """
        # Main observation control observers
        self.widgets["has_observations"].observe(
            self._on_has_observations_change, names="value"
        )
        self.widgets["obs_data_source"].observe(
            self._on_obs_source_change, names="value"
        )

        # Parameter and configuration observers
        self.widgets["obs_parameters"].observe(
            self._on_obs_parameters_change, names="value"
        )
        self.widgets["obs_period"].observe(self._on_obs_period_change, names="value")
        self.widgets["obs_folder_display"].observe(
            self._on_obs_folder_path_change, names="value"
        )

        # Button click observers
        self.widgets["browse_obs_btn"].on_click(self._on_browse_obs_folder_click)
        self.widgets["browse_output_btn"].on_click(self._on_browse_output_click)
        self.widgets["retrieve_obs_btn"].on_click(self._on_retrieve_observations_click)

    def _on_obs_parameters_change(self, change):
        """Handle observation parameter selection change.

        Updates period widget options and observation times display based
        on selected parameter characteristics (instantaneous vs period-based).

        Args:
            change: Change dictionary containing the new parameter value.

        """
        selected_param = change["new"] if change["new"] else None
        selected_params = [selected_param] if selected_param else []

        self.ui._update_period_widget_for_parameter(selected_params)

        if self.callbacks:
            self.callbacks.update_observation_times_display()

    def _on_obs_period_change(self, *_args):
        """Handle observation period selection change.

        Updates observation times display when period is changed in
        retrieve mode.
        """
        if self.widgets["obs_data_source"].value == "retrieve":
            if self.callbacks:
                self.callbacks.update_observation_times_display()

    def _on_obs_folder_path_change(self, change):
        """Handle observation folder path input change.

        Validates folder path and processes folder contents if path exists.

        Args:
            change: Change dictionary containing the new folder path.

        """
        folder_path = change["new"].strip()

        if folder_path and os.path.exists(folder_path):
            if self.callbacks:
                self.callbacks._process_selected_observation_folder(folder_path)

    def _on_retrieve_observations_click(self, *_args):
        """Handle retrieve observations button click.

        Collects observation configuration from widgets and initiates
        observation data retrieval process.
        """
        if not (self.callbacks and hasattr(self.callbacks, "retrieve_observations")):
            return

        config = self._build_observation_config()
        self.callbacks.retrieve_observations(config)

    def _build_observation_config(self):
        """Build observation configuration from widget values.

        Returns:
            Dictionary containing observation retrieval configuration with
            parameters, sources, period, date range, and output directory.

        """
        return {
            "parameters": self.widgets["obs_parameters"].value,
            "sources": self.widgets["obs_sources"].value,
            "period": self.widgets["obs_period"].value,
            "start_date": self.widgets["obs_start_date"].value,
            "end_date": self.widgets["obs_end_date"].value,
            "output_dir": self.widgets["obs_output_dir"].value,
        }

    def _on_browse_obs_folder_click(self, *_args):
        """Handle browse observation folder button click.

        Opens folder browser dialog for selecting observation data directory.
        """
        if self.callbacks and hasattr(
            self.callbacks, "_handle_browse_observation_folder"
        ):
            self.callbacks._handle_browse_observation_folder(None, None, None)

    def _on_browse_output_click(self, *_args):
        """Handle browse output directory button click.

        Opens folder browser dialog for selecting observation output directory.
        """
        if self.callbacks and hasattr(
            self.callbacks, "_handle_browse_output_directory"
        ):
            self.callbacks._handle_browse_output_directory(None, None, None)

    def _setup_scenario_observers(self):
        """Set up observer for scenario file addition.

        Configures click handler for add scenario button to create new
        scenario file input widgets.
        """
        self.widgets["add_scenario_btn"].on_click(self._on_add_scenario_click)

    def _on_add_scenario_click(self, *_args):
        """Handle add scenario button click.

        Creates a new scenario file input widget and adds it to the UI.
        """
        self.ui._add_scenario_file_input()

    def _setup_action_button_observers(self):
        """Set up observers for validate and retrieve buttons.

        Configures click handlers for main action buttons that trigger
        configuration validation and data retrieval.
        """
        self.widgets["validate_btn"].on_click(self._on_validate_click)
        self.widgets["retrieve_btn"].on_click(self._on_retrieve_click)

    def _on_validate_click(self, *_args):
        """Handle validate button click.

        Collects current configuration and triggers validation callback.
        """
        if self.callbacks and hasattr(self.callbacks, "on_validate_click"):
            config = self.ui.get_current_configuration()
            self.callbacks.on_validate_click(config)

    def _on_retrieve_click(self, *_args):
        """Handle retrieve button click.

        Collects current configuration and triggers data retrieval callback.
        """
        if self.callbacks and hasattr(self.callbacks, "on_retrieve_click"):
            config = self.ui.get_current_configuration()
            self.callbacks.on_retrieve_click(config)

    def _setup_manual_coordinate_observer(self):
        """Set up observer for manual coordinate input.

        Configures click handler for add point button to process manually
        entered latitude and longitude coordinates.
        """
        self.widgets["add_manual_point_btn"].on_click(self._on_add_manual_point_click)

    def _on_add_manual_point_click(self, *_args):
        """Handle add manual point button click.

        Triggers callback to process manually entered coordinates or shows
        error if callbacks not initialized.
        """
        if self.callbacks:
            self.callbacks.on_add_manual_point_click()
        else:
            self.ui.show_alert_message(
                "Callbacks not initialized", "error", section="plotting"
            )

    def setup_scenario_widget_observers(self, scenario_widget):
        """Set up observers for a scenario widget.

        Configures all observers for a single scenario file widget including
        days back/time dropdowns, browse/delete buttons, and file path input.

        Args:
            scenario_widget: Dictionary containing scenario widget information
                with keys: id, widget, days_back, forecast_time, name.

        """
        widget_id = scenario_widget["id"]
        scenario_row = scenario_widget["widget"]

        # Extract widget components
        scenario_file = scenario_row.children[0]
        days_back_select = scenario_row.children[1]
        forecast_time_select = scenario_row.children[2]
        browse_btn = scenario_row.children[3]
        delete_btn = scenario_row.children[4]

        # Set up observers
        days_back_select.observe(
            self._make_scenario_change_handler(widget_id), names="value"
        )
        forecast_time_select.observe(
            self._make_scenario_change_handler(widget_id), names="value"
        )
        browse_btn.on_click(self._make_scenario_browse_handler(widget_id))
        delete_btn.on_click(self._make_scenario_delete_handler(widget_id))
        scenario_file.observe(
            self._make_scenario_path_observer(scenario_widget), names="value"
        )

    def _make_scenario_change_handler(self, widget_id):
        """Create change handler for scenario dropdown changes.

        Args:
            widget_id: Unique identifier for the scenario widget.

        Returns:
            Closure function that handles dropdown value changes.

        """

        def on_scenario_change(*_args):
            self.ui._update_scenario_metadata(widget_id)

        return on_scenario_change

    def _make_scenario_browse_handler(self, widget_id):
        """Create click handler for scenario browse button.

        Args:
            widget_id: Unique identifier for the scenario widget.

        Returns:
            Closure function that handles browse button clicks.

        """

        def on_browse_click(*_args):
            self.ui._browse_scenario_file_by_id(widget_id)

        return on_browse_click

    def _make_scenario_delete_handler(self, widget_id):
        """Create click handler for scenario delete button.

        Args:
            widget_id: Unique identifier for the scenario widget.

        Returns:
            Closure function that handles delete button clicks.

        """

        def on_delete_click(*_args):
            self.ui._remove_scenario_file_input(widget_id)

        return on_delete_click

    def _make_scenario_path_observer(self, scenario_item):
        """Create observer for scenario file path changes.

        Args:
            scenario_item: Dictionary containing scenario widget information.

        Returns:
            Closure function that validates and processes file path changes.

        """

        def on_scenario_path_change(change):
            file_path = change["new"].strip()

            if not file_path:
                return

            if not os.path.exists(file_path):
                self._show_scenario_file_not_found(file_path)
                return

            self._process_scenario_file(file_path, scenario_item)

        return on_scenario_path_change

    def _show_scenario_file_not_found(self, file_path):
        """Show warning message for non-existent scenario file.

        Args:
            file_path: Path to the scenario file.

        """
        self.ui.show_alert_message(
            f"Scenario file not found: {file_path}",
            "warning",
            section="data",
        )

    def _process_scenario_file(self, file_path, scenario_item):
        """Process and validate scenario file.

        Args:
            file_path: Path to the scenario file.
            scenario_item: Dictionary containing scenario metadata.

        """
        if not self.callbacks:
            return

        if self.callbacks._validate_grib_file(file_path):
            self._handle_valid_scenario_file(file_path, scenario_item)
        else:
            self._handle_invalid_scenario_file(file_path)

    def _handle_valid_scenario_file(self, file_path, scenario_item):
        """Handle valid scenario file selection.

        Args:
            file_path: Path to the valid scenario file.
            scenario_item: Dictionary containing scenario metadata.

        """
        scenario_key = (
            f"D-{scenario_item['days_back']}_{scenario_item['forecast_time']:02d}Z"
        )
        self.callbacks.selected_files["scenarios"][scenario_key] = file_path

        self.ui.show_alert_message(
            f"Scenario file loaded: {scenario_key}",
            "success",
            section="data",
        )

        # Update bbox from first scenario file
        if len(self.callbacks.selected_files["scenarios"]) == 1:
            self.callbacks.update_bbox_from_grib_file(file_path)

    def _handle_invalid_scenario_file(self, file_path):
        """Handle invalid scenario file selection.

        Args:
            file_path: Path to the invalid scenario file.

        """
        self.ui.show_alert_message(
            f"Invalid scenario file: {os.path.basename(file_path)}",
            "error",
            section="data",
        )

    def setup_file_input_observer(self, file_type, file_display, browse_btn):
        """Set up observers for file input widgets.

        Configures observers for file path input and browse button for
        a specific file type (fc, cf, pf, cd).

        Args:
            file_type: File type identifier (e.g., "fc", "cf", "pf").
            file_display: Text widget for displaying file path.
            browse_btn: Button widget for opening file browser.

        """
        file_display.observe(self._make_file_path_observer(file_type), names="value")
        browse_btn.on_click(self._make_file_browse_handler(file_type))

    def _make_file_path_observer(self, file_type):
        """Create observer for file path input changes.

        Args:
            file_type: File type identifier.

        Returns:
            Closure function that validates and processes file path changes.

        """

        def on_path_change(change):
            file_path = change["new"].strip()

            if not file_path:
                return

            if not os.path.exists(file_path):
                self._show_file_not_found(file_path)
                return

            self._process_file_selection(file_path, file_type)

        return on_path_change

    def _show_file_not_found(self, file_path):
        """Show warning message for non-existent file.

        Args:
            file_path: Path to the file.

        """
        self.ui.show_alert_message(
            f"File not found: {file_path}", "warning", section="data"
        )

    def _process_file_selection(self, file_path, file_type):
        """Process and validate selected file.

        Args:
            file_path: Path to the selected file.
            file_type: File type identifier.

        """
        if not self.callbacks:
            return

        if self.callbacks._validate_grib_file(file_path):
            self._handle_valid_file(file_path, file_type)
        else:
            self._handle_invalid_file(file_path)

    def _handle_valid_file(self, file_path, file_type):
        """Handle valid file selection.

        Args:
            file_path: Path to the valid file.
            file_type: File type identifier.

        """
        self.callbacks.selected_files[file_type] = file_path
        self.callbacks._detect_file_parameters(file_path, file_type)

        # Update bbox from first loaded file
        if self._is_first_file_loaded(file_type):
            self.callbacks.update_bbox_from_grib_file(file_path)

        self.ui.show_alert_message(
            f"{file_type.upper()} file loaded: {os.path.basename(file_path)}",
            "success",
            section="data",
        )

    def _is_first_file_loaded(self, current_file_type):
        """Check if this is the first file being loaded.

        Args:
            current_file_type: Type of file being loaded.

        Returns:
            Boolean indicating if no other files are loaded.

        """
        return not any(
            self.callbacks.selected_files[ft]
            for ft in ["fc", "cf", "pf", "cd"]
            if ft != current_file_type
        )

    def _handle_invalid_file(self, file_path):
        """Handle invalid file selection.

        Args:
            file_path: Path to the invalid file.

        """
        self.ui.show_alert_message(
            f"Invalid GRIB file: {os.path.basename(file_path)}",
            "error",
            section="data",
        )

    def _make_file_browse_handler(self, file_type):
        """Create click handler for file browse button.

        Args:
            file_type: File type identifier.

        Returns:
            Closure function that handles browse button clicks.

        """

        def on_browse_click(*_args):
            if self.callbacks:
                self.callbacks._browse_file(file_type)

        return on_browse_click

    def setup_plot_interface_observers(
        self,
        get_parameter_category_func,
        get_unit_options_func,
        get_available_steps_func,
        refresh_plot_func,
    ):
        """Set up observers for the plot interface.

        Configures all observers for the plotting interface including parameter
        selection, unit changes, step selection, palette changes, and action
        buttons. Manages dynamic widget visibility based on parameter type
        and plot type.

        Args:
            get_parameter_category_func: Function to get parameter category
                (e.g., 'temperature', 'precipitation').
            get_unit_options_func: Function to get available unit options
                for a parameter.
            get_available_steps_func: Function to get available forecast steps
                for a parameter.
            refresh_plot_func: Function to refresh the current plot with
                updated parameters.

        """
        if not hasattr(self.layout_manager, "plot_interface_widgets"):
            return

        widgets_dict = self.layout_manager.plot_interface_widgets

        # Extract widget references
        selectors = self._extract_plot_interface_widgets(widgets_dict)

        # Set up all observers
        self._setup_plot_parameter_observer(
            selectors,
            get_parameter_category_func,
            get_unit_options_func,
            get_available_steps_func,
            refresh_plot_func,
        )
        self._setup_plot_unit_observer(selectors["unit_selector"], refresh_plot_func)
        self._setup_plot_step_observer(selectors["step_selector"], refresh_plot_func)
        self._setup_plot_palette_observer(
            selectors["palette_selector"], refresh_plot_func
        )
        self._setup_plot_action_observers(
            selectors["clear_btn"], selectors["refresh_btn"], refresh_plot_func
        )

        # Initialize widget visibility
        current_param = self.ui.auto_plot_parameter
        self._update_plot_widget_visibility(
            current_param,
            selectors,
            get_parameter_category_func,
            get_unit_options_func,
            get_available_steps_func,
        )

    def _extract_plot_interface_widgets(self, widgets_dict):
        """Extract plot interface widget references.

        Args:
            widgets_dict: Dictionary containing plot interface widgets.

        Returns:
            Dictionary with extracted widget references and containers.

        """
        return {
            "parameter_selector": widgets_dict["parameter_selector"],
            "unit_selector": widgets_dict["unit_selector"],
            "step_selector": widgets_dict["step_selector"],
            "palette_selector": widgets_dict["palette_selector"],
            "unit_container": widgets_dict["unit_container"],
            "step_container": widgets_dict["step_container"],
            "palette_container": widgets_dict["palette_container"],
            "clear_btn": widgets_dict["clear_btn"],
            "refresh_btn": widgets_dict["refresh_btn"],
        }

    def _setup_plot_parameter_observer(
        self, selectors, get_category_func, get_unit_func, get_steps_func, refresh_func
    ):
        """Set up observer for parameter selection changes.

        Args:
            selectors: Dictionary of widget references.
            get_category_func: Function to get parameter category.
            get_unit_func: Function to get unit options.
            get_steps_func: Function to get available steps.
            refresh_func: Function to refresh plot.

        """

        def on_parameter_change(change):
            if change["new"]:
                self.ui.auto_plot_parameter = change["new"]
                self._update_plot_widget_visibility(
                    change["new"],
                    selectors,
                    get_category_func,
                    get_unit_func,
                    get_steps_func,
                )
                refresh_func()

        selectors["parameter_selector"].observe(on_parameter_change, names="value")

    def _setup_plot_unit_observer(self, unit_selector, refresh_func):
        """Set up observer for unit selection changes.

        Args:
            unit_selector: Unit selection widget.
            refresh_func: Function to refresh plot.

        """

        def on_unit_change(change):
            if change["new"]:
                self.ui.auto_plot_unit = change["new"]
                refresh_func()

        unit_selector.observe(on_unit_change, names="value")

    def _setup_plot_step_observer(self, step_selector, refresh_func):
        """Set up observer for step selection changes.

        Args:
            step_selector: Step selection widget.
            refresh_func: Function to refresh plot.

        """

        def on_step_change(change):
            if change["new"] is not None:
                self.ui.auto_plot_step = change["new"]
                refresh_func()

        step_selector.observe(on_step_change, names="value")

    def _setup_plot_palette_observer(self, palette_selector, refresh_func):
        """Set up observer for palette selection changes.

        Args:
            palette_selector: Palette selection widget.
            refresh_func: Function to refresh plot.

        """

        def on_palette_change(change):
            if change["new"]:
                self.ui.auto_plot_palette = change["new"]
                refresh_func()

        palette_selector.observe(on_palette_change, names="value")

    def _setup_plot_action_observers(self, clear_btn, refresh_btn, refresh_func):
        """Set up observers for plot action buttons.

        Args:
            clear_btn: Clear plots button.
            refresh_btn: Refresh plot button.
            refresh_func: Function to refresh plot.

        """

        def on_clear_click(*_args):
            if self.callbacks:
                self.callbacks.clear_plots()

        def on_refresh_click(*_args):
            refresh_func()

        clear_btn.on_click(on_clear_click)
        refresh_btn.on_click(on_refresh_click)

    def _update_plot_widget_visibility(
        self, parameter, selectors, get_category_func, get_unit_func, get_steps_func
    ):
        """Update widget visibility based on parameter and plot type.

        Args:
            parameter: Selected parameter code.
            selectors: Dictionary of widget references.
            get_category_func: Function to get parameter category.
            get_unit_func: Function to get unit options.
            get_steps_func: Function to get available steps.

        """
        category = get_category_func(parameter)

        # Update visibility
        self._update_unit_visibility(parameter, category, selectors, get_unit_func)
        self._update_step_visibility(parameter, selectors, get_steps_func)
        self._update_palette_visibility(parameter, category, selectors)

    def _update_unit_visibility(self, parameter, category, selectors, get_unit_func):
        """Update unit selector visibility and options.

        Args:
            parameter: Selected parameter code.
            category: Parameter category.
            selectors: Dictionary of widget references.
            get_unit_func: Function to get unit options.

        """
        show_unit = self._should_show_unit_selector(parameter, category)
        selectors["unit_container"].layout.display = "block" if show_unit else "none"

        if show_unit:
            self._configure_unit_selector(
                parameter, category, selectors["unit_selector"], get_unit_func
            )

    def _should_show_unit_selector(self, parameter, category):
        """Determine if unit selector should be shown.

        Args:
            parameter: Selected parameter code.
            category: Parameter category.

        Returns:
            Boolean indicating whether to show unit selector.

        """
        return category in ["temperature", "precipitation"] or parameter in [
            "tp",
            "lsp",
            "cp",
            "2t",
            "t",
        ]

    def _configure_unit_selector(
        self, parameter, category, unit_selector, get_unit_func
    ):
        """Configure unit selector options and default value.

        Args:
            parameter: Selected parameter code.
            category: Parameter category.
            unit_selector: Unit selector widget.
            get_unit_func: Function to get unit options.

        """
        unit_options = get_unit_func(parameter)
        unit_selector.options = unit_options

        if unit_options:
            default_unit = self._get_default_unit(parameter, category)
            unit_selector.value = default_unit
            self.ui.auto_plot_unit = default_unit

    def _get_default_unit(self, parameter, category):
        """Get default unit for parameter.

        Args:
            parameter: Selected parameter code.
            category: Parameter category.

        Returns:
            String representing default unit.

        """
        if parameter in ["tp", "lsp", "cp"]:
            return "mm"
        elif category == "temperature":
            return "celsius"
        else:
            # Get first available unit option
            unit_options = self.ui._get_unit_options_for_parameter(parameter)
            return unit_options[0][1] if unit_options else "default"

    def _update_step_visibility(self, parameter, selectors, get_steps_func):
        """Update step selector visibility and options.

        Args:
            parameter: Selected parameter code.
            selectors: Dictionary of widget references.
            get_steps_func: Function to get available steps.

        """
        show_step = self.ui.current_plot_type == "stamps"
        selectors["step_container"].layout.display = "block" if show_step else "none"

        if show_step:
            self._configure_step_selector(
                parameter, selectors["step_selector"], get_steps_func
            )

    def _configure_step_selector(self, parameter, step_selector, get_steps_func):
        """Configure step selector options and default value.

        Args:
            parameter: Selected parameter code.
            step_selector: Step selector widget.
            get_steps_func: Function to get available steps.

        """
        available_steps = get_steps_func(parameter)

        if parameter in ["tp", "lsp", "cp"]:
            step_options, default_step = self._get_precipitation_step_options(
                available_steps
            )
        else:
            step_options, default_step = self._get_standard_step_options(
                available_steps
            )

        step_selector.options = step_options
        if step_options:
            step_selector.value = default_step
            self.ui.auto_plot_step = default_step

    def _get_precipitation_step_options(self, available_steps):
        """Get step options for precipitation parameters.

        Args:
            available_steps: List of available step values.

        Returns:
            Tuple of (step_options, default_step).

        """
        step_options = [(f"T+{step}h", step) for step in available_steps if step >= 6]
        default_step = (
            6
            if 6 in available_steps
            else (available_steps[0] if available_steps else 6)
        )
        return step_options, default_step

    def _get_standard_step_options(self, available_steps):
        """Get step options for standard parameters.

        Args:
            available_steps: List of available step values.

        Returns:
            Tuple of (step_options, default_step).

        """
        step_options = [(f"T+{step}h", step) for step in available_steps]
        default_step = available_steps[0] if available_steps else 0
        return step_options, default_step

    def _update_palette_visibility(self, parameter, category, selectors):
        """Update palette selector visibility.

        Args:
            parameter: Selected parameter code.
            category: Parameter category.
            selectors: Dictionary of widget references.

        """
        show_palette = self.ui.current_plot_type == "stamps" and (
            category == "precipitation" or parameter in ["tp", "lsp", "cp"]
        )
        selectors["palette_container"].layout.display = (
            "block" if show_palette else "none"
        )

    def _update_observation_section_visibility(self, data_source):
        """Update visibility of browse vs retrieve sections.

        Toggles between browse existing folder and retrieve new observations
        sections based on selected data source.

        Args:
            data_source: Selected data source ("browse" or "retrieve").

        """
        if self.widgets["has_observations"].value != "yes":
            return

        if not (
            hasattr(self.layout_manager, "browse_section")
            and hasattr(self.layout_manager, "retrieve_section")
        ):
            return

        if data_source == "browse":
            self.layout_manager.browse_section.layout.display = "block"
            self.layout_manager.retrieve_section.layout.display = "none"
        else:
            self.layout_manager.browse_section.layout.display = "none"
            self.layout_manager.retrieve_section.layout.display = "block"

    def _reset_observation_widgets(self):
        """Reset observation widgets to default values.

        Clears observation folder path, times display, and hides status
        and info displays. Used when observations are disabled.
        """
        try:
            self.widgets["obs_folder_display"].value = ""
            self.widgets["obs_folder_display"].placeholder = "No folder selected"
            self.widgets["obs_times_display"].value = ""
            self.widgets["obs_times_display"].placeholder = "Select parameter first"
            self.widgets["obs_status_display"].layout.display = "none"
            self.widgets["obs_param_info"].layout.display = "none"
        except Exception as e:
            print(f"Error resetting observation widgets: {e}")
