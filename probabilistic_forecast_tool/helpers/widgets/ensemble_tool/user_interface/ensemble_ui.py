"""Main UI orchestrator for ensemble tool interface."""

import json
import threading
import time
import traceback
from pathlib import Path

import ipywidgets as widgets  # type: ignore

from .ui_layout_manager import UILayoutManager
from .widget_configuration import WidgetConfiguration
from .widget_observer_manager import WidgetObserverManager


class EnsembleUI:
    """Interactive interface for weather data retrieval with automatic plotting.

    This class provides a user interface for managing weather ensemble data,
    including configuration loading, widget management, and plot generation.

    Attributes:
        config_file: Path to the JSON configuration file.
        model_configs: Dictionary containing model configuration data.
        surface_variables: Dictionary of available surface variables.
        parameter_mappings: Mapping between different parameter naming conventions.
        use_cases: Dictionary of predefined use case configurations.
        current_plot_type: Currently selected plot type.
        current_data_source: Currently active data source.
        selected_files: Dictionary of selected file paths by model.
        callbacks: Registered callback functions.
        map_handler: Handler for map-based visualizations.
        data_loaded: Boolean indicating if data has been loaded.
        auto_plot_parameter: Default parameter for automatic plotting.
        auto_plot_unit: Unit system for automatic plotting.
        auto_plot_step: Time step for automatic plotting.
        auto_plot_palette: Color palette index for automatic plotting.
        widget_config: Configuration manager for UI widgets.
        widgets: Dictionary of created UI widgets.
        layout_manager: Manager for UI layout organization.
        observer_manager: Manager for widget event observers.

    """

    def __init__(self, config_file="model_config.json"):
        """Initialize the ensemble interface.

        Args:
            config_file: Path to the JSON configuration file. Defaults to
                "model_config.json".

        """
        self.config_file = config_file
        self._load_config()

        # Initialize state variables
        self.current_plot_type = None
        self.current_data_source = None
        self.selected_files = {}
        self.callbacks = None
        self.map_handler = None
        self.data_loaded = False

        # Initialize auto-plot defaults
        self._initialize_auto_plot_defaults()

        # Initialize UI components
        self._initialize_ui_components()

        # Set up observers and plot type cards
        self.observer_manager.setup_all_observers()
        self._initialize_plot_type_cards()

    def _initialize_auto_plot_defaults(self):
        """Initialize default values for automatic plotting.

        Sets up default parameter, unit, time step, and palette for
        automatic plot generation.
        """
        self.auto_plot_parameter = "2t"
        self.auto_plot_unit = "celsius"
        self.auto_plot_step = 48
        self.auto_plot_palette = 1

    def _initialize_ui_components(self):
        """Initialize all user interface components.

        Creates widget configuration, generates widgets, sets up layout
        manager, and initializes observer manager for event handling.
        """
        self.widget_config = WidgetConfiguration(
            self.model_configs, self.surface_variables
        )
        self.widgets = self.widget_config.create_all_widgets()
        self.layout_manager = UILayoutManager(
            self.widgets,
            self.plot_configs,
            self.use_cases,
            self.map_handler,
            self.widget_config,
        )
        self.observer_manager = WidgetObserverManager(
            self.widgets, self, self.layout_manager
        )

    def _load_config(self):
        """Load model configuration from JSON file.

        Attempts to load configuration from the specified JSON file. If the
        file is not found or an error occurs, falls back to default configuration.

        Raises:
            Prints warning messages but does not raise exceptions. Falls back
            to default configuration on any error.

        """
        try:
            config_path = Path(self.config_file)
            if config_path.exists():
                self._load_config_from_file(config_path)
            else:
                print(f"Warning: Config file not found: {config_path}")
                self._load_fallback_config()
        except Exception as e:
            print(f"Error loading config: {e}")
            self._load_fallback_config()

    def _load_config_from_file(self, config_path):
        """Load and parse configuration from a JSON file.

        Args:
            config_path: Path object pointing to the configuration file.

        """
        with open(config_path) as f:
            config_data = json.load(f)

        self._extract_config_sections(config_data)
        self._build_plot_configs_from_json()

    def _extract_config_sections(self, config_data):
        """Extract configuration sections from loaded JSON data.

        Args:
            config_data: Dictionary containing the parsed JSON configuration.

        """
        self.use_cases = config_data.get("use_cases", {})
        self.surface_variables = config_data.get("surface_variables", {})
        self.parameter_mappings = config_data.get("parameter_mappings", {})
        self.model_configs = config_data.get("model_configs", {})

    def _build_plot_configs_from_json(self):
        """Build plot configurations from JSON use cases data.

        Creates plot configuration dictionary from the loaded use_cases data,
        including titles, descriptions, MARS parameters, and feature flags
        for each plot type.
        """
        self.plot_configs = {}

        for plot_type, use_case_data in self.use_cases.items():
            config = self._create_plot_config(plot_type, use_case_data)
            self._add_optional_data_to_config(config, use_case_data)
            self.plot_configs[plot_type] = config

    def _create_plot_config(self, plot_type, use_case_data):
        """Create configuration dictionary for a specific plot type.

        Args:
            plot_type: Type of plot (e.g., 'meteogram', 'plumes', 'cdf').
            use_case_data: Dictionary containing use case configuration data.

        Returns:
            Dictionary containing plot configuration with title, description,
            parameters, and feature flags.

        """
        return {
            "title": f"{plot_type.title()} Data",
            "description": use_case_data.get("description", f"{plot_type} analysis"),
            "mars_params": self._get_mars_params_for_plot_type(plot_type),
            "local_files": use_case_data.get("required_data", []),
            "specific_params": [],
            "requires_points": plot_type in ["meteogram", "plumes", "cdf"],
            "supports_time_series": plot_type in ["meteogram", "plumes"],
            "scenario_files": plot_type == "cdf",
        }

    def _add_optional_data_to_config(self, config, use_case_data):
        """Add optional data files to configuration and remove duplicates.

        Args:
            config: Plot configuration dictionary to modify in place.
            use_case_data: Dictionary containing use case configuration data.

        """
        if "optional_data" in use_case_data:
            config["local_files"].extend(use_case_data["optional_data"])
            config["local_files"] = list(dict.fromkeys(config["local_files"]))

    def _get_mars_params_for_plot_type(self, plot_type):
        """Get MARS parameters needed for each plot type.

        Args:
            plot_type: Type of plot (e.g., 'meteogram', 'plumes', 'cdf').

        Returns:
            List of MARS parameter names required for the specified plot type.

        """
        base_params = ["parameters", "area", "grid", "model_class"]

        if plot_type == "cdf":
            return base_params + ["analysis_date", "days_back", "forecast_times"]
        elif plot_type == "meteogram":
            return base_params + ["forecast_date", "time", "steps", "include_control"]
        else:
            return base_params + ["forecast_date", "time", "steps"]

    def _load_fallback_config(self):
        """Load fallback configuration if config file not available.

        Initializes all configuration dictionaries to empty state when the
        primary configuration file cannot be loaded.
        """
        self.use_cases = {}
        self.surface_variables = {}
        self.parameter_mappings = {}
        self.model_configs = {}
        self.plot_configs = {}

    def _initialize_plot_type_cards(self):
        """Initialize plot type selection cards with interactive UI elements.

        Creates visual cards for each plot type showing title, description,
        features, and selection button. Sets up click handlers for plot
        type selection.
        """
        plot_buttons = []

        for plot_type, config in self.plot_configs.items():
            card = self._create_plot_type_card(plot_type, config)
            plot_buttons.append(card)

        self.widgets["plot_type_cards"].children = plot_buttons

        self.widgets["plot_type_cards"].layout = widgets.Layout(
            display="flex",
            justify_content="center",
            align_items="center",
            flex_flow="row wrap",
            width="100%",
        )

    def _create_plot_type_card(self, plot_type, config):
        """Create a single plot type selection card.

        Args:
            plot_type: Type of plot (e.g., 'meteogram', 'plumes', 'cdf').
            config: Configuration dictionary for the plot type.

        Returns:
            VBox widget containing the card HTML and selection button.

        """
        features = self._extract_plot_features(config)
        button_html = self._create_card_html(plot_type, config, features)
        button = self._create_card_button(plot_type)

        return widgets.VBox([button_html, button])

    def _extract_plot_features(self, config):
        """Extract feature list from plot configuration.

        Args:
            config: Configuration dictionary for the plot type.

        Returns:
            List of feature strings (e.g., ['Point Selection', 'Time Series']).

        """
        features = []
        if config.get("requires_points"):
            features.append("Point Selection")
        if config.get("supports_time_series"):
            features.append("Time Series")
        if config.get("scenario_files"):
            features.append("Multi-Scenario")
        return features

    def _create_card_html(self, plot_type, config, features):
        """Create HTML widget for plot type card display.

        Args:
            plot_type: Type of plot (e.g., 'meteogram', 'plumes', 'cdf').
            config: Configuration dictionary for the plot type.
            features: List of feature strings to display.

        Returns:
            HTML widget containing the formatted card display.

        """
        features_text = ", ".join(features) if features else "Grid Analysis"

        return widgets.HTML(
            value=f"""
            <div style="text-align: center; padding: 10px; margin: 5px;
                       border: 2px solid #ddd; border-radius: 8px; cursor: pointer;
                       background-color: #f9f9f9; transition: all 0.3s;">
                <h4 style="color: #86D5E0; margin: 5px 0;">{config["title"]}</h4>
                <p style="color: #666; margin: 5px 0; font-size: 0.9em;">{config["description"]}</p>
                <small style="color: #999;">Features: {features_text}</small>
                <br><span style="background: #86D5E0; color: white; padding: 2px 6px;
                           border-radius: 3px; font-size: 0.8em;">{plot_type.upper()}</span>
            </div>
            """,
            layout=widgets.Layout(width="280px"),
        )

    def _create_card_button(self, plot_type):
        """Create selection button for plot type card.

        Args:
            plot_type: Type of plot (e.g., 'meteogram', 'plumes', 'cdf').

        Returns:
            Button widget with click handler attached.

        """
        button = widgets.Button(
            description=f"Select {plot_type.title()}",
            layout=widgets.Layout(width="280px", height="40px"),
            style={"button_color": "#E0F7FA"},
        )

        def make_click_handler(ptype):
            def on_click(*_args):
                self.on_plot_type_selected(ptype)

            return on_click

        button.on_click(make_click_handler(plot_type))
        return button

    def display_interface(self):
        """Display the complete user interface.

        Delegates to the layout manager to render the full interface
        with all configured widgets and controls.
        """
        self.layout_manager.display_interface()

    def set_callbacks(self, callbacks):
        """Set callback handler for UI actions.

        Args:
            callbacks: EnsembleCallbacks instance for handling user interactions.

        """
        self.callbacks = callbacks
        self.observer_manager.set_callbacks(callbacks)

        if hasattr(callbacks, "plotting_manager"):
            self.set_plotting_manager(callbacks.plotting_manager)

    def set_map_handler(self, map_handler):
        """Set the map handler for geographic area selection.

        Args:
            map_handler: WeatherMapHandler instance for interactive map display
                and area selection, or None to disable map functionality.

        """
        self.map_handler = map_handler
        self.layout_manager.map_handler = map_handler
        if map_handler:
            self.widgets["map_container"] = map_handler.get_map_widget()

    def set_plotting_manager(self, plotting_manager):
        """Set reference to plotting manager for plot generation.

        Args:
            plotting_manager: PlottingManager instance responsible for
                creating and managing plot visualizations.

        """
        self.plotting_manager = plotting_manager

    def on_plot_type_selected(self, plot_type):
        """Handle plot type selection and update UI state accordingly.

        Manages plot type switching, including data compatibility checks,
        data preservation or clearing, and UI updates. Updates configuration
        sections and map instructions after selection.

        Args:
            plot_type: Selected plot type (e.g., 'meteogram', 'plumes', 'cdf').

        """
        self._handle_plot_type_switch(plot_type)

        # Update UI state
        self.current_plot_type = plot_type
        self._create_file_inputs_for_plot_type(plot_type)
        self._update_plot_type_button_styling(plot_type)

        self.widgets["data_source_selection"].layout.display = "block"

        if not self.current_data_source:
            self.current_data_source = self.widgets["data_source_radio"].value

        if self.callbacks:
            self.callbacks._update_parameters_for_plot_type(plot_type)

        self._update_configuration_section()
        self._update_map_instructions(plot_type)

    def _handle_plot_type_switch(self, new_plot_type):
        """Handle data management when switching between plot types.

        Checks compatibility between current and new plot types. If incompatible,
        clears data and resets state. If compatible, preserves existing data.

        Args:
            new_plot_type: The plot type being switched to.

        """
        if not hasattr(self, "current_plot_type") or not hasattr(
            self, "current_data_source"
        ):
            return

        if self.current_plot_type == new_plot_type:
            return

        if self.current_data_source == "local":
            self._handle_local_data_switch(new_plot_type)
        elif self.current_data_source == "mars":
            self._handle_mars_data_switch(new_plot_type)

    def _handle_local_data_switch(self, new_plot_type):
        """Handle data management when switching plot types with local data.

        Args:
            new_plot_type: The plot type being switched to.

        """
        if not self._are_plot_types_compatible(self.current_plot_type, new_plot_type):
            self._clear_local_data()
        else:
            self.show_alert_message(
                f"Switching to {new_plot_type} - data preserved from {self.current_plot_type}",
                "success",
                section="data",
            )

    def _handle_mars_data_switch(self, new_plot_type):
        """Handle data management when switching plot types with MARS data.

        Args:
            new_plot_type: The plot type being switched to.

        """
        if not self._are_plot_types_compatible(self.current_plot_type, new_plot_type):
            self._clear_mars_data()
            self.show_alert_message(
                f"Switching to {new_plot_type} - previous {self.current_plot_type} data cleared (incompatible)",
                "warning",
                section="data",
            )
        else:
            self.show_alert_message(
                f"Switching to {new_plot_type} - data preserved from {self.current_plot_type}",
                "success",
                section="data",
            )

    def _clear_local_data(self):
        """Clear local file selections and reset data loaded status."""
        if self.callbacks:
            self.callbacks._reset_local_file_selections()

        self.data_loaded = False
        self._update_map_handler_status(False)

    def _clear_mars_data(self):
        """Clear MARS data, configuration, and plots."""
        if self.callbacks:
            self.callbacks.current_data = {}
            self.callbacks.current_config = {}

            if hasattr(self.callbacks, "plotting_manager"):
                self.callbacks.plotting_manager.current_data = None
                self.callbacks.plotting_manager.current_config = None
                self.callbacks.plotting_manager.clear_plots()

        self.data_loaded = False
        self._update_map_handler_status(False)

    def _update_map_handler_status(self, status):
        """Update map handler data loaded status if available.

        Args:
            status: Boolean indicating whether data is loaded.

        """
        if hasattr(self, "map_handler") and self.map_handler:
            if hasattr(self.map_handler, "set_data_loaded_status"):
                self.map_handler.set_data_loaded_status(status)

    def _create_file_inputs_for_plot_type(self, plot_type):
        """Create file input widgets based on plot type configuration.

        Generates file upload widgets for each required file type specified
        in the plot configuration. Sets up observers for file selection events.

        Args:
            plot_type: Plot type to create file inputs for.

        """
        if plot_type not in self.plot_configs:
            return

        self.widgets["file_inputs"] = {}
        required_files = self.plot_configs[plot_type].get("local_files", [])

        file_descriptions = self._get_file_type_descriptions()

        for file_type in required_files:
            self._create_single_file_input(file_type, file_descriptions)

    def _get_file_type_descriptions(self):
        """Get human-readable descriptions for file types.

        Returns:
            Dictionary mapping file type codes to descriptive labels.

        """
        return {
            "fc": "Deterministic Forecast",
            "cf": "Control Forecast",
            "pf": "Ensemble Forecast",
            "cd": "Climate Data",
        }

    def _create_single_file_input(self, file_type, file_descriptions):
        """Create a single file input widget with observer.

        Args:
            file_type: Type code for the file (e.g., 'fc', 'pf').
            file_descriptions: Dictionary mapping file types to descriptions.

        """
        description = file_descriptions.get(file_type, file_type)
        file_row = self.widget_config.create_file_input_for_type(file_type, description)

        self.widgets["file_inputs"][file_type] = file_row

        file_display = file_row.children[0]
        browse_btn = file_row.children[1]
        self.observer_manager.setup_file_input_observer(
            file_type, file_display, browse_btn
        )

    def _update_plot_type_button_styling(self, selected_plot_type):
        """Update plot type button styling to highlight selection.

        Regenerates all plot type cards with updated styling to visually
        indicate which plot type is currently selected.

        Args:
            selected_plot_type: Currently selected plot type.

        """
        plot_buttons = []

        for plot_type, config in self.plot_configs.items():
            card = self._create_styled_plot_card(plot_type, config, selected_plot_type)
            plot_buttons.append(card)

        self.widgets["plot_type_cards"].children = plot_buttons

    def _create_styled_plot_card(self, plot_type, config, selected_plot_type):
        """Create a plot type card with appropriate styling.

        Args:
            plot_type: Type of plot for this card.
            config: Configuration dictionary for the plot type.
            selected_plot_type: Currently selected plot type for styling.

        Returns:
            VBox widget containing the styled card and button.

        """
        features = self._extract_plot_features(config)
        is_selected = plot_type == selected_plot_type

        button_html = self._create_styled_card_html(
            plot_type, config, features, is_selected
        )
        button = self._create_styled_card_button(plot_type, is_selected)

        return widgets.VBox([button_html, button])

    def _create_styled_card_html(self, plot_type, config, features, is_selected):
        """Create HTML widget for styled plot type card.

        Args:
            plot_type: Type of plot for this card.
            config: Configuration dictionary for the plot type.
            features: List of feature strings to display.
            is_selected: Boolean indicating if this plot type is selected.

        Returns:
            HTML widget with appropriate styling based on selection state.

        """
        bg_color = "#86D5E0" if is_selected else "#f9f9f9"
        text_color = "white" if is_selected else "#333"
        border_color = "#86D5E0" if is_selected else "#ddd"
        badge_bg = "white" if is_selected else "#86D5E0"
        badge_text = "#86D5E0" if is_selected else "white"

        features_text = ", ".join(features) if features else "Grid Analysis"

        return widgets.HTML(
            value=f"""
            <div style="text-align: center; padding: 10px; margin: 5px;
                       border: 2px solid {border_color}; border-radius: 8px;
                       background-color: {bg_color}; color: {text_color};">
                <h4 style="margin: 5px 0;">{config["title"]}</h4>
                <p style="margin: 5px 0; font-size: 0.9em;">{config["description"]}</p>
                <small>Features: {features_text}</small>
                <br><span style="background: {badge_bg};
                           color: {badge_text};
                           padding: 2px 6px; border-radius: 3px; font-size: 0.8em;">{plot_type.upper()}</span>
            </div>
            """,
            layout=widgets.Layout(width="280px"),
        )

    def _create_styled_card_button(self, plot_type, is_selected):
        """Create selection button with appropriate styling.

        Args:
            plot_type: Type of plot for this button.
            is_selected: Boolean indicating if this plot type is selected.

        Returns:
            Button widget with click handler and appropriate styling.

        """
        button = widgets.Button(
            description=f"Select {plot_type.title()}",
            layout=widgets.Layout(width="280px", height="40px"),
            style={"button_color": "#86D5E0" if is_selected else "#E0F7FA"},
        )

        def make_click_handler(ptype):
            def on_click(*_args):
                self.on_plot_type_selected(ptype)

            return on_click

        button.on_click(make_click_handler(plot_type))
        return button

    def _update_configuration_section(self):
        """Update configuration section based on plot type and data source.

        Rebuilds the configuration UI section with appropriate widgets for
        the current plot type and data source (MARS or local files). Includes
        action buttons, alerts, and observation sections where applicable.
        """
        if not self.current_plot_type or not self.current_data_source:
            return

        config = self.plot_configs[self.current_plot_type]

        self._update_retrieve_button_text()

        config_widgets = self._build_config_widgets(config)

        self._setup_cdf_scenario_observers()

        config_widgets.append(self._create_action_section())

        if self.current_plot_type in ["meteogram", "plumes"]:
            config_widgets.append(self._create_observation_section_with_alerts())

        self.layout_manager.configuration_container.children = config_widgets

    def _update_retrieve_button_text(self):
        """Update retrieve button text based on data source.

        Sets button text to 'Load Data' for local files or 'Retrieve Data'
        for MARS data source.
        """
        if self.current_data_source == "local":
            self.widgets["retrieve_btn"].description = "Load Data"
        else:
            self.widgets["retrieve_btn"].description = "Retrieve Data"

    def _build_config_widgets(self, config):
        """Build configuration widgets based on data source.

        Args:
            config: Plot configuration dictionary.

        Returns:
            List of widget objects for the configuration section.

        """
        if self.current_data_source == "mars":
            return self.layout_manager.build_three_section_mars_layout(
                config, self.current_plot_type
            )
        else:
            return self.layout_manager.build_local_config_widgets(
                config, self.current_plot_type
            )

    def _setup_cdf_scenario_observers(self):
        """Set up observers for CDF scenario file widgets if applicable."""
        if (
            self.current_plot_type == "cdf"
            and self.current_data_source == "local"
            and "cdf_scenario_files" in self.widgets
        ):
            for scenario_item in self.widgets["cdf_scenario_files"]:
                self.observer_manager.setup_scenario_widget_observers(scenario_item)

    def _create_action_section(self):
        """Create action buttons section with alerts.

        Returns:
            VBox widget containing action buttons and data alert container.

        """
        return widgets.VBox(
            [
                self.widgets["action_buttons"],
                widgets.HTML("<div style='margin: 15px 0;'></div>"),
                self.layout_manager.data_alert_container,
            ],
            layout=widgets.Layout(width="100%"),
        )

    def _create_observation_section_with_alerts(self):
        """Create observation section with associated alert container.

        Returns:
            VBox widget containing observation section and alerts.

        """
        observation_section = self.layout_manager.create_observation_section()
        return widgets.VBox(
            [
                observation_section,
                widgets.HTML("<div style='margin: 15px 0;'></div>"),
                self.layout_manager.observation_alert_container,
            ],
            layout=widgets.Layout(width="100%"),
        )

    def _update_map_instructions(self, plot_type):
        """Update map instructions based on plot type.

        Updates the map instruction text and sets up the clear point button
        if the plot type requires point selection.

        Args:
            plot_type: Currently selected plot type.

        """
        clear_btn = self.layout_manager.update_map_instructions(
            plot_type, self.plot_configs
        )

        if clear_btn:
            self._setup_clear_point_handler(clear_btn)

    def _setup_clear_point_handler(self, clear_btn):
        """Set up click handler for clear point button.

        Args:
            clear_btn: Button widget for clearing selected points.

        """

        def on_clear_point(*_args):
            if self.callbacks:
                self.callbacks.clear_selected_points()
                self._reset_manual_coordinate_inputs()

        clear_btn.on_click(on_clear_point)

    def _reset_manual_coordinate_inputs(self):
        """Reset manual coordinate input widgets to default values."""
        self.widgets["manual_lat_input"].value = 0.0
        self.widgets["manual_lon_input"].value = 0.0
        self.widgets["manual_coord_status"].value = ""

    def get_current_configuration(self):
        """Get current configuration from all widgets.

        Collects values from all relevant widgets and assembles them into
        a configuration dictionary. Handles different parameter structures
        for MARS and local data sources.

        Returns:
            Dictionary containing current configuration with keys:
                - plot_type: Currently selected plot type
                - data_source: Current data source ('mars' or 'local')
                - parameters: Dictionary of parameter values
                - files: Dictionary of selected file paths
                - scenario_files: List of scenario file configurations (for CDF)

        """
        config = self._initialize_config_structure()

        if self.current_plot_type and self.current_data_source:
            if self.current_plot_type in self.plot_configs:
                plot_config = self.plot_configs[self.current_plot_type]

                if self.current_data_source == "mars":
                    self._collect_mars_parameters(config, plot_config)

                self._collect_specific_parameters(config, plot_config)

                self._collect_cdf_scenario_files(config)

        return config

    def _initialize_config_structure(self):
        """Initialize empty configuration structure.

        Returns:
            Dictionary with empty configuration structure.

        """
        return {
            "plot_type": self.current_plot_type,
            "data_source": self.current_data_source,
            "parameters": {},
            "files": {},
            "scenario_files": [],
        }

    def _collect_mars_parameters(self, config, plot_config):
        """Collect MARS parameters from widgets.

        Args:
            config: Configuration dictionary to populate.
            plot_config: Plot-specific configuration containing required parameters.

        """
        for param in plot_config["mars_params"]:
            if param in self.widgets:
                config["parameters"][param] = self.widgets[param].value
            elif param == "area":
                self._collect_area_parameter(config)
            elif param == "grid":
                self._collect_grid_parameter(config)
            elif param == "steps" and self.current_plot_type != "cdf":
                self._collect_steps_parameter(config)

    def _collect_area_parameter(self, config):
        """Collect area boundary parameters.

        Args:
            config: Configuration dictionary to populate.

        """
        config["parameters"]["area"] = [
            self.widgets["north"].value,
            self.widgets["west"].value,
            self.widgets["south"].value,
            self.widgets["east"].value,
        ]

    def _collect_grid_parameter(self, config):
        """Collect grid resolution parameter.

        Args:
            config: Configuration dictionary to populate.

        """
        grid_value_str = self.widgets["grid_resolution"].value.strip()
        if grid_value_str:
            try:
                grid_value = float(grid_value_str)
                config["parameters"]["grid"] = [grid_value, grid_value]
            except ValueError:
                pass

    def _collect_steps_parameter(self, config):
        """Collect forecast step parameters.

        Prioritizes selected steps from display widget, falls back to
        step range widget if no specific steps are selected.

        Args:
            config: Configuration dictionary to populate.

        """
        if (
            self.widgets["steps_display"].value
            and len(self.widgets["steps_display"].value) > 0
        ):
            config["parameters"]["selected_steps"] = list(
                self.widgets["steps_display"].value
            )
        else:
            config["parameters"]["steps"] = self.widgets["steps"].value

    def _collect_specific_parameters(self, config, plot_config):
        """Collect plot-specific parameters from widgets.

        Args:
            config: Configuration dictionary to populate.
            plot_config: Plot-specific configuration containing specific parameters.

        """
        for param in plot_config["specific_params"]:
            if param in self.widgets:
                config["parameters"][param] = self.widgets[param].value

    def _collect_cdf_scenario_files(self, config):
        """Collect CDF scenario file configurations.

        Args:
            config: Configuration dictionary to populate.

        """
        if (
            self.current_plot_type == "cdf"
            and self.current_data_source == "local"
            and "cdf_scenario_files" in self.widgets
        ):
            for scenario_item in self.widgets["cdf_scenario_files"]:
                config["scenario_files"].append(
                    {
                        "name": scenario_item["name"],
                        "path": "",
                    }
                )

    def on_data_loaded(self):
        """Handle successful data loading event.

        Sets data loaded flag and triggers automatic plotting behavior based
        on plot type. For stamps plots, automatically generates the plot.
        For point-based plots, displays instructions for map interaction.
        """
        self.data_loaded = True

        if self.current_plot_type == "stamps":
            self._auto_plot_stamps()
        else:
            self._show_point_selection_instructions()

    def _show_point_selection_instructions(self):
        """Show instructions for point-based plot types after data loads."""
        config = self.plot_configs.get(self.current_plot_type, {})
        if config.get("requires_points"):
            self.show_alert_message(
                f"Data loaded! Click on the map to automatically create {self.current_plot_type} plots.",
                "success",
                section="data",
            )

    def on_map_point_selected(self, lat, lon):
        """Handle map point selection and trigger automatic plotting.

        Validates that data is loaded and plot type is selected, checks if
        the point is within the geographic bounds, updates selected points,
        and automatically generates the appropriate plot.

        Args:
            lat: Latitude of selected point in degrees.
            lon: Longitude of selected point in degrees.

        """
        if not self._validate_point_selection_preconditions():
            return

        if not self._validate_point_in_bounds(lat, lon):
            return

        self._process_point_selection(lat, lon)

    def _validate_point_selection_preconditions(self):
        """Validate that data is loaded and plot type is selected.

        Returns:
            Boolean indicating whether preconditions are met.

        """
        if not self.data_loaded:
            self.show_alert_message(
                "Please load data first before selecting points.",
                "warning",
                section="plotting",
            )
            return False

        if not self.current_plot_type:
            self.show_alert_message(
                "Please select a plot type first.", "warning", section="plotting"
            )
            return False

        return True

    def _validate_point_in_bounds(self, lat, lon):
        """Validate that selected point is within geographic bounds.

        Args:
            lat: Latitude of selected point in degrees.
            lon: Longitude of selected point in degrees.

        Returns:
            Boolean indicating whether point is within bounds.

        """
        if self.callbacks and hasattr(self.callbacks, "map_handler"):
            map_handler = self.callbacks.map_handler
            if hasattr(map_handler, "is_point_in_bbox"):
                if not map_handler.is_point_in_bbox(lat, lon):
                    self.show_alert_message(
                        f"Point ({lat:.3f}°N, {lon:.3f}°E) is outside the current geographic area.",
                        "warning",
                        section="plotting",
                    )
                    return False
        return True

    def _process_point_selection(self, lat, lon):
        """Process valid point selection and create appropriate plot.

        Args:
            lat: Latitude of selected point in degrees.
            lon: Longitude of selected point in degrees.

        """
        if not self.callbacks:
            return

        if (
            hasattr(self.callbacks, "plotting_manager")
            and self.callbacks.plotting_manager
        ):
            new_points = {"P1": (lat, lon)}
            self.callbacks.plotting_manager.update_selected_points(new_points)

            self.show_alert_message(
                f"Selected analysis point at {lat:.3f}°N, {lon:.3f}°E",
                "success",
                section="plotting",
            )

            self._create_auto_plot_for_point()

    def _create_auto_plot_for_point(self):
        """Create automatic plot based on current plot type.

        Delegates to the appropriate plot creation method based on the
        currently selected plot type (meteogram, cdf, or plumes).
        """
        plot_creators = {
            "meteogram": self.callbacks.create_meteogram_plot,
            "cdf": self.callbacks.create_cdf_plot,
            "plumes": self.callbacks.create_plumes_plot,
        }

        creator = plot_creators.get(self.current_plot_type)
        if creator:
            creator(
                parameter=self.auto_plot_parameter,
                unit_value=self.auto_plot_unit,
            )

    def _auto_plot_stamps(self):
        """Automatically create stamps plot after data loads.

        Attempts to generate a stamps plot using the configured auto-plot
        parameters. Displays error message if plot creation fails.
        """
        try:
            if self.callbacks and hasattr(self.callbacks, "create_stamps_plot"):
                self.callbacks.create_stamps_plot(
                    parameter=self.auto_plot_parameter,
                    step=self.auto_plot_step,
                    unit_value=self.auto_plot_unit,
                    palette_value=self.auto_plot_palette,
                )
        except Exception as e:
            self.show_alert_message(
                f"Error auto-plotting stamps: {e}", "error", section="plotting"
            )

    def update_plotting_controls(self, plot_controls, plot_type):
        """Update plotting controls with simplified interface.

        Retrieves available parameters from loaded data, creates a simplified
        plot interface, and sets up observers for interactive control updates.

        Args:
            plot_controls: Plot controls object from plotting manager (unused
                in current implementation but kept for API compatibility).
            plot_type: Current plot type for which to create controls.

        """
        try:
            self._update_plot_interface(plot_type)
        except Exception as e:
            traceback.print_exc()
            print(f"Error updating plotting controls: {e}")

    def _update_plot_interface(self, plot_type):
        """Create and configure the plot interface controls.

        Args:
            plot_type: Current plot type for which to create controls.

        """
        available_parameters = self._get_available_parameters_from_data()

        simplified_controls = self.layout_manager.create_plot_interface(
            plot_type,
            available_parameters,
            self.auto_plot_parameter,
            self.auto_plot_palette,
        )

        self.layout_manager.plot_controls_container.children = [simplified_controls]

        self._setup_plot_control_observers()

    def _setup_plot_control_observers(self):
        """Set up observers for plot interface interactive controls.

        Configures observers that respond to changes in parameter selection,
        unit selection, step selection, and refresh requests.
        """
        self.observer_manager.setup_plot_interface_observers(
            self._get_parameter_category,
            self._get_unit_options_for_parameter,
            self._get_available_steps_for_parameter,
            self._refresh_current_plot,
        )

    def show_alert_message(
        self, message, alert_type="info", section="general", permanent=False
    ):
        """Show alert message in the UI with styled formatting.

        Displays a styled alert message in the specified section of the UI.
        Supports different alert types with appropriate colors and icons.
        Alerts can auto-dismiss after 5 seconds or remain permanent.

        Args:
            message: Alert message text to display.
            alert_type: Type of alert - "info", "success", "warning", or "error".
                Defaults to "info".
            section: Section to show alert in - "data", "observation", "plotting",
                or "general". Defaults to "general".
            permanent: Whether alert should stay until manually cleared. If False,
                non-error/warning alerts auto-dismiss after 5 seconds. Defaults
                to False.

        """
        try:
            alert_html = self._create_alert_html(message, alert_type)
            alert = widgets.HTML(value=alert_html)

            container = self._get_alert_container(section)
            self._add_alert_to_container(alert, container, permanent, alert_type)

        except Exception as e:
            print(f"Alert error: {e}")

    def _create_alert_html(self, message, alert_type):
        """Create HTML for alert message based on type.

        Args:
            message: Alert message text.
            alert_type: Type of alert ("info", "success", "warning", "error").

        Returns:
            HTML string with styled alert message.

        """
        alert_styles = {
            "success": {
                "bg": "#E8F5E8",
                "border": "#4CAF50",
                "icon": "✅",
                "icon_color": "#2E7D32",
                "title": "Success",
                "text_color": "#1B5E20",
            },
            "info": {
                "bg": "#E3F2FD",
                "border": "#2196F3",
                "icon": "ℹ️",
                "icon_color": "#1976D2",
                "title": "Information",
                "text_color": "#0D47A1",
            },
            "warning": {
                "bg": "#FFF8E1",
                "border": "#D1D1D1",
                "icon": "⚠️",
                "icon_color": "#F57C00",
                "title": "Warning",
                "text_color": "#E65100",
            },
            "error": {
                "bg": "#FFEBEE",
                "border": "#F44336",
                "icon": "❌",
                "icon_color": "#D32F2F",
                "title": "Error",
                "text_color": "#B71C1C",
            },
        }

        style = alert_styles.get(alert_type)

        if style:
            return self._format_styled_alert(message, style)
        else:
            return self._format_default_alert(message)

    def _format_styled_alert(self, message, style):
        """Format alert with icon and title.

        Args:
            message: Alert message text.
            style: Dictionary containing style properties.

        Returns:
            HTML string with formatted alert.

        """
        return f"""
            <div style="background-color: {style["bg"]}; padding: 15px; border-radius: 8px;
                    margin: 10px 0; border-left: 4px solid {style["border"]}; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="display: flex; align-items: center;">
                    <span style="color: {style["icon_color"]}; font-size: 18px; margin-right: 8px;">{style["icon"]}</span>
                    <h4 style="margin: 0; color: {style["icon_color"]}; font-weight: bold;">{style["title"]}</h4>
                </div>
                <div style="color: {style["text_color"]}; margin-top: 8px; line-height: 1.4;">
                    {message}
                </div>
            </div>
        """

    def _format_default_alert(self, message):
        """Format default alert without icon or title.

        Args:
            message: Alert message text.

        Returns:
            HTML string with basic formatted alert.

        """
        return f"""
            <div style="background-color: #F5F5F5; padding: 15px; border-radius: 8px;
                    margin: 10px 0; border-left: 4px solid #9E9E9E; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="color: #424242; line-height: 1.4;">
                    {message}
                </div>
            </div>
        """

    def _get_alert_container(self, section):
        """Get the appropriate alert container for the specified section.

        Args:
            section: Section identifier ("data", "observation", "plotting", "general").

        Returns:
            Widget container for displaying alerts.

        """
        containers = {
            "data": self.layout_manager.data_alert_container,
            "observation": self.layout_manager.observation_alert_container,
            "plotting": self.layout_manager.plotting_alert_container,
        }
        return containers.get(section, self.layout_manager.general_alert_container)

    def _add_alert_to_container(self, alert, container, permanent, alert_type):
        """Add alert to container with appropriate behavior.

        Args:
            alert: HTML widget containing the alert.
            container: Container widget to add alert to.
            permanent: Whether alert should remain until manually cleared.
            alert_type: Type of alert for determining auto-dismiss behavior.

        """
        current_alerts = list(container.children)

        if permanent:
            current_alerts = [alert]
        else:
            current_alerts.insert(0, alert)
            if len(current_alerts) > 2:
                current_alerts = current_alerts[:2]

        container.children = current_alerts

        if not permanent and alert_type not in ["error", "warning"]:
            self._schedule_alert_dismissal(alert, container)

    def _schedule_alert_dismissal(self, alert, container):
        """Schedule automatic dismissal of alert after 5 seconds.

        Args:
            alert: HTML widget to dismiss.
            container: Container widget containing the alert.

        """

        def dismiss_alert():
            time.sleep(5)
            if alert in container.children:
                alerts = list(container.children)
                alerts.remove(alert)
                container.children = alerts

        threading.Thread(target=dismiss_alert, daemon=True).start()

    def _add_scenario_file_input(self):
        """Add a new CDF scenario file input widget.

        Creates a new scenario file input with auto-generated name, sets up
        observers, updates metadata, and refreshes the display.
        """
        scenario_name = f"Custom_{len(self.widgets['cdf_scenario_files']) + 1}"
        scenario_widget = self.widget_config.create_scenario_file_widget(scenario_name)

        self.widgets["cdf_scenario_files"].append(scenario_widget)
        self.observer_manager.setup_scenario_widget_observers(scenario_widget)

        if self.widgets["cdf_scenario_files"]:
            latest_scenario = self.widgets["cdf_scenario_files"][-1]
            self._update_scenario_metadata(latest_scenario["id"])

        self._update_scenario_files_display()

    def _remove_scenario_file_input(self, widget_id):
        """Remove a scenario file input by widget ID.

        Args:
            widget_id: Unique identifier of the scenario widget to remove.

        """
        self.widgets["cdf_scenario_files"] = [
            item
            for item in self.widgets["cdf_scenario_files"]
            if item["id"] != widget_id
        ]
        self._update_scenario_files_display()

    def _update_scenario_files_display(self):
        """Update the scenario files display with current widgets.

        Rebuilds the scenario files container with all current scenario
        widgets plus the add scenario button.
        """
        scenario_widgets = [
            item["widget"] for item in self.widgets["cdf_scenario_files"]
        ]
        scenario_widgets.append(widgets.HBox([self.widgets["add_scenario_btn"]]))

        self.widgets["scenario_files_container"].children = scenario_widgets

    def _update_scenario_metadata(self, widget_id):
        """Update scenario metadata when dropdowns change.

        Updates the scenario name, description, and metadata based on the
        selected days back and forecast time values.

        Args:
            widget_id: Unique identifier of the scenario widget to update.

        """
        for scenario_item in self.widgets["cdf_scenario_files"]:
            if scenario_item["id"] == widget_id:
                self._update_single_scenario_metadata(scenario_item)
                break

    def _update_single_scenario_metadata(self, scenario_item):
        """Update metadata for a single scenario item.

        Args:
            scenario_item: Dictionary containing scenario widget and metadata.

        """
        scenario_row = scenario_item["widget"]

        days_back = scenario_row.children[1].value
        forecast_time = scenario_row.children[2].value

        scenario_item["days_back"] = days_back
        scenario_item["forecast_time"] = forecast_time

        new_scenario_name = f"D-{days_back}_{forecast_time:02d}Z"

        self._update_scenario_widget_labels(
            scenario_row, scenario_item, new_scenario_name, days_back, forecast_time
        )

    def _update_scenario_widget_labels(
        self, scenario_row, scenario_item, scenario_name, days_back, forecast_time
    ):
        """Update text labels on scenario widget.

        Args:
            scenario_row: Widget row containing scenario controls.
            scenario_item: Dictionary containing scenario metadata.
            scenario_name: New scenario name to display.
            days_back: Number of days back for forecast.
            forecast_time: Forecast initialization time in hours.

        """
        text_field = scenario_row.children[0]
        scenario_item["name"] = scenario_name
        text_field.description = f"{scenario_name} Scenario File:"
        text_field.placeholder = (
            f"Forecast from {days_back} days ago at {forecast_time:02d}Z"
        )

        if scenario_item.get("is_custom", False):
            scenario_item["is_custom"] = False

    def _browse_scenario_file_by_id(self, widget_id):
        """Browse for scenario file by widget ID.

        Opens file browser for selecting a scenario file based on the
        configured days back and forecast time parameters.

        Args:
            widget_id: Unique identifier of the scenario widget.

        """
        for scenario_item in self.widgets["cdf_scenario_files"]:
            if scenario_item["id"] == widget_id:
                days_back = scenario_item["days_back"]
                forecast_time = scenario_item["forecast_time"]

                scenario_key = f"D-{days_back}_{forecast_time:02d}Z"

                if self.callbacks:
                    self.callbacks._browse_scenario_file(
                        scenario_key, widget_id, scenario_item
                    )
                break

    def _update_period_widget_for_parameter(self, selected_params):
        """Update period widget based on selected observation parameter.

        Configures the observation period widget based on whether the selected
        parameter is instantaneous or period-based. Updates available period
        options and enables/disables the widget accordingly.

        Args:
            selected_params: List containing selected parameter code(s).

        """
        try:
            if not self._validate_parameter_selection(selected_params):
                self._disable_period_widget()
                return

            param = selected_params[0]
            self._configure_period_widget_for_param(param)

            if self.callbacks:
                self.callbacks.update_observation_times_display()

        except Exception as e:
            print(f"Error updating period widget: {e}")

    def _validate_parameter_selection(self, selected_params):
        """Validate that a parameter is selected.

        Args:
            selected_params: List containing selected parameter code(s).

        Returns:
            Boolean indicating if selection is valid.

        """
        return selected_params and selected_params[0]

    def _disable_period_widget(self):
        """Disable period widget when no parameter is selected."""
        self.widgets["obs_period"].disabled = True
        self.widgets["obs_period"].options = []
        self.widgets["obs_times_display"].value = ""
        self.widgets["obs_times_display"].placeholder = "Select parameter first"

    def _configure_period_widget_for_param(self, param):
        """Configure period widget based on parameter type.

        Args:
            param: Parameter code to configure period widget for.

        """
        if not (
            self.callbacks
            and hasattr(self.callbacks, "observations_retriever")
            and self.callbacks.observations_retriever
        ):
            return

        retriever = self.callbacks.observations_retriever
        param_info = retriever.get_parameter_info(param)

        if param_info["type"] == "instantaneous":
            self._set_instantaneous_period_widget()
        elif param_info["type"] == "period":
            self._set_period_based_widget(param_info)

    def _set_instantaneous_period_widget(self):
        """Configure period widget for instantaneous parameter."""
        self.widgets["obs_period"].disabled = True
        self.widgets["obs_period"].options = [("Not applicable (instantaneous)", "na")]
        self.widgets["obs_period"].value = "na"

    def _set_period_based_widget(self, param_info):
        """Configure period widget for period-based parameter.

        Args:
            param_info: Dictionary containing parameter information including
                supported periods.

        """
        self.widgets["obs_period"].disabled = False
        supported_periods = param_info["supported_periods"]
        period_items = [
            (f"{period} hours", str(period)) for period in sorted(supported_periods)
        ]
        self.widgets["obs_period"].options = period_items
        if period_items:
            self.widgets["obs_period"].value = period_items[0][1]

    def _update_auto_plot_unit(self):
        """Update auto-plot unit based on selected parameter category.

        Determines the appropriate default unit for the current auto-plot
        parameter based on its category (temperature, precipitation, etc.).
        """
        if not self.callbacks or not hasattr(self.callbacks, "plotting_manager"):
            return

        plotting_manager = self.callbacks.plotting_manager
        category = plotting_manager._get_parameter_category(self.auto_plot_parameter)

        self.auto_plot_unit = self._get_default_unit_for_category(category)

    def _get_default_unit_for_category(self, category):
        """Get default unit for a parameter category.

        Args:
            category: Parameter category (e.g., 'temperature', 'precipitation').

        Returns:
            String representing the default unit for the category.

        """
        category_units = {
            "temperature": "celsius",
            "precipitation": "mm",
            "pressure": "hpa",
            "wind": "ms",
        }
        return category_units.get(category, "default")

    def _get_parameter_category(self, parameter):
        """Get parameter category for unit selection.

        Determines the category of a parameter (temperature, precipitation,
        wind, etc.) either from the plotting manager or through fallback logic.

        Args:
            parameter: Parameter code (e.g., '2t', 'tp', 'ws').

        Returns:
            String representing the parameter category.

        """
        if self.callbacks and hasattr(self.callbacks, "plotting_manager"):
            return self.callbacks.plotting_manager._get_parameter_category(parameter)

        return self._get_fallback_parameter_category(parameter)

    def _get_fallback_parameter_category(self, parameter):
        """Get parameter category using fallback logic.

        Args:
            parameter: Parameter code (e.g., '2t', 'tp', 'ws').

        Returns:
            String representing the parameter category.

        """
        category_mapping = {
            "temperature": ["2t", "t"],
            "precipitation": ["tp", "lsp", "cp"],
            "wind": ["ws"],
            "geopotential": ["z"],
        }

        for category, params in category_mapping.items():
            if parameter in params:
                return category

        return "other"

    def _get_unit_options_for_parameter(self, parameter):
        """Get available unit options for the given parameter.

        Returns a list of tuples containing display text and unit value
        for all supported units for the parameter.

        Args:
            parameter: Parameter code (e.g., '2t', 'tp', 'ws').

        Returns:
            List of tuples in format [(display_text, unit_value), ...].

        """
        category = self._get_parameter_category(parameter)

        unit_options = {
            "temperature": [("°C", "celsius"), ("K", "kelvin")],
            "precipitation": [("mm", "mm"), ("m", "m")],
            "wind": [("m/s", "m/s")],
            "geopotential": [("m²/s²", "m2/s2")],
        }

        if category in unit_options:
            return unit_options[category]
        elif parameter in ["2t", "t"]:
            return unit_options["temperature"]
        elif parameter in ["tp", "lsp", "cp"]:
            return unit_options["precipitation"]
        elif parameter in ["ws"]:
            return unit_options["wind"]
        elif parameter in ["z"]:
            return unit_options["geopotential"]
        else:
            return []

    def _get_available_steps_for_parameter(self, parameter):
        """Get available forecast steps for parameter from plotting manager.

        Args:
            parameter: Parameter code to get available steps for.

        Returns:
            List of available forecast step values in hours.

        """
        if (
            self.callbacks
            and hasattr(self.callbacks, "plotting_manager")
            and self.callbacks.plotting_manager
        ):
            return self.callbacks.plotting_manager.get_available_steps_for_parameter(
                parameter
            )
        return [0, 6, 12, 18, 24, 48, 72]

    def _get_available_parameters_from_data(self):
        """Extract available parameters from loaded data.

        Retrieves the list of parameters available in the loaded data and
        formats them with descriptive names and units for display.

        Returns:
            List of tuples in format [(display_text, parameter_code), ...].
            Returns empty list if no data is loaded.

        """
        if not self.callbacks or not hasattr(self.callbacks, "current_data"):
            return []

        if not self._has_plotting_manager_with_parameters():
            return []

        detected_params = self.callbacks.plotting_manager.available_parameters
        return self._format_parameter_options(detected_params)

    def _has_plotting_manager_with_parameters(self):
        """Check if plotting manager exists with available parameters.

        Returns:
            Boolean indicating if plotting manager and parameters are available.

        """
        return (
            hasattr(self.callbacks, "plotting_manager")
            and self.callbacks.plotting_manager
            and hasattr(self.callbacks.plotting_manager, "available_parameters")
        )

    def _format_parameter_options(self, detected_params):
        """Format parameter codes into display options.

        Args:
            detected_params: List of parameter codes detected in data.

        Returns:
            List of tuples in format [(display_text, parameter_code), ...].

        """
        parameter_options = []

        for param in detected_params:
            text = self._get_parameter_display_text(param)
            parameter_options.append((text, param))

        return parameter_options

    def _get_parameter_display_text(self, param):
        """Get display text for a parameter code.

        Args:
            param: Parameter code (e.g., '2t', 'tp', 'ws').

        Returns:
            Formatted display text with parameter name and units.

        """
        if param in self.surface_variables:
            return self._format_from_surface_variables(param)

        common_params = {
            "ws": "Wind Speed (m/s)",
            "tp": "6h Accumulated Total Precipitation (mm)",
            "lsp": "6h Accumulated Large-scale Precipitation (mm)",
            "cp": "6h Accumulated Convective Precipitation (mm)",
        }

        return common_params.get(param, param.upper())

    def _format_from_surface_variables(self, param):
        """Format parameter display text from surface variables config.

        Args:
            param: Parameter code.

        Returns:
            Formatted string with parameter name and units.

        """
        param_info = self.surface_variables[param]
        name = param_info.get("name", param.upper())
        units = param_info.get("units", "")
        return f"{name} ({units})" if units else name

    def _refresh_current_plot(self):
        """Refresh the current plot with selected parameters.

        Validates that data is loaded and plot type is selected, then
        regenerates the current plot using the selected parameters. Handles
        both grid-based plots (stamps) and point-based plots (meteogram, etc.).
        """
        if not self._validate_refresh_preconditions():
            return

        try:
            if self.current_plot_type == "stamps":
                self._refresh_stamps_plot()
            elif self.current_plot_type in ["meteogram", "cdf", "plumes"]:
                self._refresh_point_based_plot()

        except Exception as e:
            self.show_alert_message(
                f"Error refreshing plot: {e}", "error", section="plotting"
            )

    def _validate_refresh_preconditions(self):
        """Validate preconditions for plot refresh.

        Returns:
            Boolean indicating whether refresh can proceed.

        """
        if not self.data_loaded:
            self.show_alert_message(
                "No data loaded to refresh plots.", "warning", section="plotting"
            )
            return False

        if not self.current_plot_type:
            self.show_alert_message(
                "No plot type selected.", "warning", section="plotting"
            )
            return False

        return True

    def _refresh_stamps_plot(self):
        """Refresh stamps plot with current parameters."""
        if self.callbacks:
            self.callbacks.create_stamps_plot(
                parameter=self.auto_plot_parameter,
                step=self.auto_plot_step,
                unit_value=self.auto_plot_unit,
                palette_value=self.auto_plot_palette,
            )

    def _refresh_point_based_plot(self):
        """Refresh point-based plot (meteogram, CDF, or plumes).

        Validates that a point is selected and within bounds, then
        creates the appropriate plot type.
        """
        if not self._validate_point_for_refresh():
            return

        point_coords = list(self.callbacks.plotting_manager.selected_points.values())[0]
        lat, lon = point_coords

        if not self._validate_point_in_current_area(lat, lon):
            return

        self._create_point_plot()

    def _validate_point_for_refresh(self):
        """Validate that a point is selected for point-based plots.

        Returns:
            Boolean indicating whether a valid point is selected.

        """
        if not (
            self.callbacks
            and hasattr(self.callbacks, "plotting_manager")
            and self.callbacks.plotting_manager
            and self.callbacks.plotting_manager.selected_points
        ):
            self.show_alert_message(
                "Select a point on the map first for point-based plots.",
                "info",
                section="plotting",
            )
            return False
        return True

    def _validate_point_in_current_area(self, lat, lon):
        """Validate that point is within current geographic area.

        Args:
            lat: Latitude of the point.
            lon: Longitude of the point.

        Returns:
            Boolean indicating whether point is within bounds.

        """
        if hasattr(self.callbacks, "map_handler") and hasattr(
            self.callbacks.map_handler, "is_point_in_bbox"
        ):
            if not self.callbacks.map_handler.is_point_in_bbox(lat, lon):
                self.show_alert_message(
                    f"Cannot refresh plot: analysis point ({lat:.3f}°N, {lon:.3f}°E) "
                    "is outside the current geographic area.",
                    "error",
                    section="plotting",
                )
                return False
        return True

    def _create_point_plot(self):
        """Create the appropriate point-based plot."""
        plot_creators = {
            "meteogram": self.callbacks.create_meteogram_plot,
            "cdf": self.callbacks.create_cdf_plot,
            "plumes": self.callbacks.create_plumes_plot,
        }

        creator = plot_creators.get(self.current_plot_type)
        if creator:
            creator(
                parameter=self.auto_plot_parameter,
                unit_value=self.auto_plot_unit,
            )

    def _is_step_range(self, steps_str):
        """Check if the input is a range format like '0-240'.

        Args:
            steps_str: String to check for range format.

        Returns:
            Boolean indicating whether input is a valid range format.

        """
        return (
            isinstance(steps_str, str)
            and "-" in steps_str
            and len(steps_str.split("-")) == 2
        )

    def _get_available_steps_for_range(self, steps_str):
        """Get available steps based on range and current plot type.

        Parses a step range string (e.g., '0-240') and generates available
        step values based on model configuration and plot type requirements.

        Args:
            steps_str: Step range string in format 'start-end'.

        Returns:
            Sorted list of available step values within the range. Returns
            empty list if parsing fails.

        """
        try:
            start, end = map(int, steps_str.split("-"))

            if not self.current_plot_type:
                return list(range(start, end + 1, 6))

            model_class = self._get_current_model_class()
            return self._generate_steps_for_model(model_class, start, end)

        except (ValueError, AttributeError):
            return []

    def _get_current_model_class(self):
        """Get currently selected model class.

        Returns:
            String representing model class (defaults to 'ifs').

        """
        if "model_class" in self.widgets and self.widgets["model_class"].value:
            return self.widgets["model_class"].value
        return "ifs"

    def _generate_steps_for_model(self, model_class, start, end):
        """Generate step values based on model configuration.

        Args:
            model_class: Model class identifier (e.g., 'ifs', 'aifs').
            start: Start of step range.
            end: End of step range.

        Returns:
            List of step values appropriate for the model and range.

        """
        if model_class in self.model_configs:
            return self._generate_steps_from_config(model_class, start, end)

        return self._generate_default_steps(start, end)

    def _generate_steps_from_config(self, model_class, start, end):
        """Generate steps from model configuration.

        Args:
            model_class: Model class identifier.
            start: Start of step range.
            end: End of step range.

        Returns:
            List of step values based on model configuration.

        """
        model_config = self.model_configs[model_class]
        step_config = model_config.get("step_config", {})

        if step_config.get("type") == "intervals":
            return self._generate_steps_from_intervals(step_config, start, end)
        elif step_config.get("type") == "range":
            return self._generate_steps_from_range_config(step_config, start, end)

        return self._generate_default_steps(start, end)

    def _generate_steps_from_intervals(self, step_config, start, end):
        """Generate steps from interval-based configuration.

        Args:
            step_config: Step configuration dictionary with intervals.
            start: Start of step range.
            end: End of step range.

        Returns:
            Sorted list of unique step values.

        """
        intervals = step_config["intervals"]
        steps = []

        for interval_start, interval_end, step_interval in intervals:
            current_start = max(interval_start, start)
            current_end = min(interval_end, end)
            if current_start <= current_end:
                steps.extend(range(current_start, current_end + 1, step_interval))

        return sorted(set(steps))

    def _generate_steps_from_range_config(self, step_config, start, end):
        """Generate steps from range-based configuration.

        Args:
            step_config: Step configuration dictionary with range parameters.
            start: Start of requested range.
            end: End of requested range.

        Returns:
            List of step values within the requested range.

        """
        model_start = step_config["start"]
        model_end = step_config["end"]
        model_step = step_config["step"]

        available_steps = list(range(model_start, model_end + 1, model_step))
        return [step for step in available_steps if start <= step <= end]

    def _generate_default_steps(self, start, end):
        """Generate default steps when no model config is available.

        Args:
            start: Start of step range.
            end: End of step range.

        Returns:
            List of step values with interval based on plot type.

        """
        if self.current_plot_type == "cdf":
            return list(range(start, end + 1, 24))
        else:
            return list(range(start, end + 1, 6))

    def _are_plot_types_compatible(self, plot_type1, plot_type2):
        """Check if two plot types are compatible (use same data sources).

        Args:
            plot_type1: First plot type
            plot_type2: Second plot type

        Returns:
            bool: True if plot types are compatible

        """
        compatible_groups = [
            {"meteogram", "plumes"},
        ]

        for group in compatible_groups:
            if plot_type1 in group and plot_type2 in group:
                return True

        return False
