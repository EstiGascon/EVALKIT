"""Widget configuration for ensemble tool interface."""

from datetime import date, timedelta

import ipywidgets as widgets  # type: ignore


class WidgetConfiguration:
    """Configuration and creation of all interface widgets.

    This class manages the creation and configuration of all UI widgets
    for the ensemble weather tool interface, including plot type selection,
    data source configuration, MARS parameters, and control buttons.

    Attributes:
        model_configs: Dictionary containing model configuration data.
        surface_variables: Dictionary of available surface variables.
        widgets: Dictionary storing all created widget instances.
        cdf_scenario_counter: Counter for generating unique CDF scenario IDs.

    """

    def __init__(self, model_configs, surface_variables):
        """Initialize widget configuration.

        Args:
            model_configs: Dictionary containing model configuration data
                for different forecast models.
            surface_variables: Dictionary of available surface variables
                with their properties and units.

        """
        self.model_configs = model_configs
        self.surface_variables = surface_variables
        self.widgets = {}
        self.cdf_scenario_counter = 0

    def create_all_widgets(self):
        """Create all widgets for the interface.

        Initializes and creates all widget components including plot type
        selectors, data source options, MARS parameters, file inputs,
        observation controls, map widgets, and action buttons.

        Returns:
            Dictionary containing all created widget instances organized
            by widget type and purpose.

        """
        self._create_plot_type_widgets()
        self._create_data_source_widgets()
        self._create_mars_widgets()
        self._create_local_file_widgets()
        self._create_observation_widgets()
        self._create_map_widgets()
        self._create_manual_coordinate_widgets()
        self._create_action_buttons()
        self._create_step_selection_widgets()
        return self.widgets

    def _create_plot_type_widgets(self):
        """Create plot type selection widgets.

        Initializes container widgets for displaying plot type cards
        and handling plot type selection.
        """
        self.widgets["plot_type_cards"] = widgets.HBox([])
        self.widgets["plot_type_selection"] = widgets.VBox(
            [self.widgets["plot_type_cards"]]
        )

    def _create_data_source_widgets(self):
        """Create data source selection widgets.

        Creates radio button widget for selecting between MARS archive
        download and local file loading options. Initializes as hidden
        until plot type is selected.
        """
        self.widgets["data_source_radio"] = self._create_data_source_radio()
        self.widgets["data_source_selection"] = self._create_data_source_container()

    def _create_data_source_radio(self):
        """Create radio button widget for data source selection.

        Returns:
            RadioButtons widget configured with MARS and local file options.

        """
        return widgets.RadioButtons(
            options=[
                ("Download from MARS Archive", "mars"),
                ("Load Local Files", "local"),
            ],
            value="mars",
            description="",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

    def _create_data_source_container(self):
        """Create container for data source selection widgets.

        Returns:
            VBox widget containing header and data source radio buttons,
            initially hidden.

        """
        return widgets.VBox(
            [
                self._create_section_header("Data Source"),
                self.widgets["data_source_radio"],
            ],
            layout=widgets.Layout(display="none"),
        )

    def _create_section_header(self, title, color="#616161"):
        """Create styled section header.

        Args:
            title: Header text to display.
            color: CSS color code for header text. Defaults to "#616161".

        Returns:
            HTML widget with styled header.

        """
        return widgets.HTML(
            f"<h3 style='margin-bottom: 10px; color: {color};'>{title}</h3>"
        )

    def _create_mars_widgets(self):
        """Create MARS-specific configuration widgets.

        Initializes all widgets required for MARS data retrieval configuration
        including model selection, dates, times, parameters, geographic area,
        grid resolution, and forecast steps.
        """
        self._create_model_selection_widget()
        self._create_date_and_time_widgets()
        self._create_parameter_widgets()
        self._create_geographic_area_widgets()
        self._create_grid_and_step_widgets()

    def _create_model_selection_widget(self):
        """Create model class selection dropdown.

        Builds dropdown options from model configurations with descriptions
        and sets default to IFS model.
        """
        model_options = self._build_model_options()

        self.widgets["model_class"] = widgets.Dropdown(
            options=model_options,
            value="ifs",
            description="Model Class:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

    def _build_model_options(self):
        """Build model options list from configuration.

        Returns:
            List of tuples in format [(display_text, model_code), ...].

        """
        model_options = []
        for model_name, model_config in self.model_configs.items():
            description = model_config.get("description", model_name.upper())
            model_options.append((f"{model_name.upper()} - {description}", model_name))
        return model_options

    def _create_date_and_time_widgets(self):
        """Create date and time selection widgets for MARS retrieval.

        Creates widgets for forecast date, analysis date, forecast run times,
        and days back configuration for CDF analysis.
        """
        self.widgets["forecast_date"] = self._create_date_picker(
            "Forecast initialisation Date:"
        )
        self.widgets["analysis_date"] = self._create_date_picker(
            "Forecast Analysis Date:"
        )
        self.widgets["time"] = self._create_time_dropdown()
        self.widgets["days_back"] = self._create_days_back_slider()
        self.widgets["forecast_times"] = self._create_forecast_times_dropdown()

    def _create_date_picker(self, description):
        """Create a date picker widget with standard styling.

        Args:
            description: Label text for the date picker.

        Returns:
            DatePicker widget configured with today's date.

        """
        return widgets.DatePicker(
            value=date.today(),
            description=description,
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

    def _create_time_dropdown(self):
        """Create forecast run time dropdown.

        Returns:
            Dropdown widget with 6-hour interval time options.

        """
        return widgets.Dropdown(
            options=[
                ("00:00:00", "00:00:00"),
                ("06:00:00", "06:00:00"),
                ("12:00:00", "12:00:00"),
                ("18:00:00", "18:00:00"),
            ],
            value="00:00:00",
            description="Forecast run time:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="220px"),
        )

    def _create_days_back_slider(self):
        """Create days back slider for CDF analysis.

        Returns:
            IntSlider widget for selecting historical days range (1-10).

        """
        return widgets.IntSlider(
            value=3,
            min=1,
            max=10,
            step=1,
            description="Days Back:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

    def _create_forecast_times_dropdown(self):
        """Create forecast times dropdown for CDF scenarios.

        Returns:
            Dropdown widget with 00Z, 12Z, and both options.

        """
        return widgets.Dropdown(
            options=[("00Z", 0), ("12Z", 12), ("Both (00Z & 12Z)", "both")],
            value="both",
            description="Forecast run time:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="250px"),
        )

    def _create_parameter_widgets(self):
        """Create parameter selection widgets.

        Creates multi-select widget for MARS parameters and single-select
        dropdown for plot parameter selection.
        """
        self.widgets["parameters"] = widgets.SelectMultiple(
            options=[],
            value=[],
            description="Parameters:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="400px", height="150px"),
        )

        self.widgets["plot_parameters"] = widgets.Dropdown(
            options=[],
            value=None,
            description="Parameter:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="250px"),
        )

    def _create_geographic_area_widgets(self):
        """Create geographic bounding box input widgets.

        Creates four float text inputs for north, south, east, and west
        boundaries with default values covering Europe.
        """
        self.widgets["north"] = self._create_boundary_input("North:", 72.0)
        self.widgets["south"] = self._create_boundary_input("South:", 34.0)
        self.widgets["east"] = self._create_boundary_input("East:", 45.0)
        self.widgets["west"] = self._create_boundary_input("West:", -25.0)

    def _create_boundary_input(self, description, default_value):
        """Create a geographic boundary input widget.

        Args:
            description: Label for the boundary (e.g., "North:", "South:").
            default_value: Default latitude or longitude value.

        Returns:
            FloatText widget with degree suffix.

        """
        return widgets.FloatText(
            value=default_value,
            description=description,
            suffix="°",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="150px"),
        )

    def _create_grid_and_step_widgets(self):
        """Create grid resolution and forecast step widgets.

        Creates text input for grid resolution and forecast step range
        or specific step specification.
        """
        self.widgets["grid_resolution"] = widgets.Text(
            value="",
            description="Grid Resolution:",
            suffix="°",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
        )

        self.widgets["steps"] = widgets.Text(
            value="0-240",
            description="Forecast Steps (hours):",
            placeholder="0-240 or specific steps",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="250px"),
        )

    def _create_local_file_widgets(self):
        """Create local file selection widgets.

        Initializes containers for file input widgets, CDF scenario file
        management, and the add scenario button.
        """
        self.widgets["file_inputs"] = {}
        self.widgets["cdf_scenario_files"] = []

        self.widgets["add_scenario_btn"] = widgets.Button(
            description="Add More Scenario Files",
            button_style="",
            layout=widgets.Layout(width="200px"),
            style={"button_color": "#50DEA3", "font_weight": "bold"},
        )

        self.widgets["scenario_files_container"] = widgets.VBox([])

    def _create_observation_widgets(self):
        """Create observation data integration widgets.

        Initializes all widgets for observation data configuration including
        data source selection, parameter selection, time range configuration,
        and retrieval controls.
        """
        self._create_observation_control_widgets()
        self._create_observation_browse_widgets()
        self._create_observation_parameter_widgets()
        self._create_observation_date_range_widgets()
        self._create_observation_output_widgets()
        self._create_observation_status_widgets()

    def _create_observation_control_widgets(self):
        """Create main observation control widgets.

        Creates radio buttons for enabling observations and selecting
        between browsing existing data or retrieving new data.
        """
        self.widgets["has_observations"] = widgets.RadioButtons(
            options=[("No", "no"), ("Yes", "yes")],
            value="no",
            description="Include Observation Data?",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="250px"),
        )

        self.widgets["obs_data_source"] = widgets.RadioButtons(
            options=[
                ("Browse existing folder", "browse"),
                ("Retrieve new observations", "retrieve"),
            ],
            value="browse",
            description="Data Source:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

    def _create_observation_browse_widgets(self):
        """Create widgets for browsing observation folder.

        Creates text display for selected folder path and browse button.
        """
        self.widgets["obs_folder_display"] = widgets.Text(
            value="",
            description="Observation Folder:",
            disabled=False,
            placeholder="No folder selected",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

        self.widgets["browse_obs_btn"] = widgets.Button(
            description="Browse Folder",
            button_style="",
            layout=widgets.Layout(width="120px"),
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )

    def _create_observation_parameter_widgets(self):
        """Create observation parameter selection widgets.

        Creates dropdowns for parameter selection, data sources, and
        observation period configuration. All initially disabled.
        """
        self.widgets["obs_parameters"] = self._create_obs_parameters_dropdown()
        self.widgets["obs_sources"] = self._create_obs_sources_dropdown()
        self.widgets["obs_period"] = self._create_obs_period_dropdown()
        self.widgets["obs_times_display"] = self._create_obs_times_display()

    def _create_obs_parameters_dropdown(self):
        """Create observation parameters dropdown.

        Returns:
            Dropdown widget with common meteorological parameters.

        """
        return widgets.Dropdown(
            options=[
                ("2m Temperature", "2t"),
                ("2m Dewpoint", "2d"),
                ("Total Precipitation", "tp"),
                ("10m Wind Speed", "10ff"),
                ("10m Wind Gust", "10fg"),
                ("Maximum Temperature", "tmax"),
                ("Minimum Temperature", "tmin"),
            ],
            value="2t",
            description="Parameters to Retrieve:",
            disabled=True,
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

    def _create_obs_sources_dropdown(self):
        """Create observation data sources dropdown.

        Returns:
            Dropdown widget with SYNOP, HDOBS, and both options.

        """
        return widgets.Dropdown(
            options=[("SYNOP", "synop"), ("HDOBS", "hdobs"), ("Both", "synop hdobs")],
            value="synop hdobs",
            description="Data Sources:",
            disabled=True,
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

    def _create_obs_period_dropdown(self):
        """Create observation period dropdown.

        Returns:
            Dropdown widget with 6, 12, and 24 hour period options.

        """
        return widgets.Dropdown(
            options=[("6 hours", "6"), ("12 hours", "12"), ("24 hours", "24")],
            value="24",
            description="Period:",
            disabled=True,
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
        )

    def _create_obs_times_display(self):
        """Create observation times display widget.

        Returns:
            Text widget showing retrieval times based on parameter selection.

        """
        return widgets.Text(
            value="",
            description="Retrieval Times (UTC):",
            disabled=True,
            placeholder="Times will be shown based on parameter selection",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

    def _create_observation_date_range_widgets(self):
        """Create observation date range selection widgets.

        Creates date pickers for start and end dates, defaulting to
        2 days ago through today. Initially disabled.
        """
        self.widgets["obs_start_date"] = widgets.DatePicker(
            value=(date.today() - timedelta(days=2)),
            description="Start Date:",
            disabled=True,
            style={"description_width": "initial"},
            layout=widgets.Layout(width="500px"),
        )

        self.widgets["obs_end_date"] = widgets.DatePicker(
            value=date.today(),
            description="End Date:",
            disabled=True,
            style={"description_width": "initial"},
            layout=widgets.Layout(width="500px"),
        )

    def _create_observation_output_widgets(self):
        """Create observation output directory widgets.

        Creates text input for output directory path and browse button
        for directory selection. Initially disabled.
        """
        self.widgets["obs_output_dir"] = widgets.Text(
            value="./retrieved_observations",
            description="Output Directory:",
            disabled=True,
            style={"description_width": "initial"},
            layout=widgets.Layout(width="500px"),
        )

        self.widgets["browse_output_btn"] = widgets.Button(
            description="Browse",
            button_style="",
            layout=widgets.Layout(width="120px"),
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )

        self.widgets["retrieve_obs_btn"] = widgets.Button(
            description="Retrieve Observations",
            button_style="",
            disabled=True,
            layout=widgets.Layout(width="200px"),
            style={"button_color": "#50DEA3", "font_weight": "bold"},
        )

    def _create_observation_status_widgets(self):
        """Create observation status and info display widgets.

        Creates HTML widgets for showing retrieval status and parameter
        information. Initially hidden.
        """
        self.widgets["obs_status_display"] = widgets.HTML(
            value="", layout=widgets.Layout(width="100%", display="none")
        )

        self.widgets["obs_param_info"] = widgets.HTML(
            value=self._create_obs_info_html(),
            layout=widgets.Layout(width="100%", display="none"),
        )

    def _create_obs_info_html(self):
        """Create HTML for observation parameter info display.

        Returns:
            HTML string with styled info box prompting parameter selection.

        """
        return """
            <div style="background-color: #E0F7FA; padding: 10px; border-radius: 5px;
                    border-left: 4px solid #4DD0E1;">
                <small style="color: #006064;">Select forecast parameter first</small>
            </div>
            """

    def _create_map_widgets(self):
        """Create map section placeholder widget.

        Creates a placeholder HTML widget that will be replaced with an
        interactive map component when the map handler is initialized.
        """
        self.widgets["map_container"] = widgets.HTML(
            value=self._create_map_placeholder_html(),
            layout=widgets.Layout(width="100%", height="400px"),
        )

    def _create_map_placeholder_html(self):
        """Create HTML for map placeholder display.

        Returns:
            HTML string with centered placeholder text.

        """
        return """
            <div style="height: 400px; width: 100%; border: 1px solid #ddd;
                       border-radius: 4px; display: flex; align-items: center;
                       justify-content: center; background-color: #f5f5f5;">
                <span style="color: #666;">Map will be integrated here</span>
            </div>
            """

    def _create_manual_coordinate_widgets(self):
        """Create manual coordinate input widgets.

        Creates widgets for manually entering latitude and longitude values,
        along with an add point button and status display for feedback.
        """
        self.widgets["manual_lat_input"] = self._create_coordinate_input("Lat:")
        self.widgets["manual_lon_input"] = self._create_coordinate_input("Lon:")
        self.widgets["add_manual_point_btn"] = self._create_add_point_button()
        self.widgets["manual_coord_status"] = self._create_coordinate_status_display()

    def _create_coordinate_input(self, description):
        """Create a coordinate input widget (latitude or longitude).

        Args:
            description: Label for the input (e.g., "Lat:" or "Lon:").

        Returns:
            FloatText widget configured for coordinate input.

        """
        return widgets.FloatText(
            value=0.0,
            description=description,
            disabled=False,
            step=0.1,
            style={"description_width": "30px"},
            layout=widgets.Layout(width="120px"),
        )

    def _create_add_point_button(self):
        """Create button for adding manual coordinate points.

        Returns:
            Button widget with plus icon and styled appearance.

        """
        return widgets.Button(
            description="Add Point",
            button_style="",
            icon="plus",
            layout=widgets.Layout(width="110px"),
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )

    def _create_coordinate_status_display(self):
        """Create status display for coordinate input feedback.

        Returns:
            HTML widget for displaying coordinate validation messages.

        """
        return widgets.HTML(
            value="", layout=widgets.Layout(width="100%", margin="5px 0")
        )

    def _create_action_buttons(self):
        """Create main action buttons for data operations.

        Creates validate and retrieve buttons arranged in a horizontal
        layout for initiating configuration validation and data retrieval.
        """
        self.widgets["validate_btn"] = self._create_validate_button()
        self.widgets["retrieve_btn"] = self._create_retrieve_button()

        self.widgets["action_buttons"] = widgets.HBox(
            [self.widgets["validate_btn"], self.widgets["retrieve_btn"]],
            layout=widgets.Layout(justify_content="center"),
        )

    def _create_validate_button(self):
        """Create configuration validation button.

        Returns:
            Button widget for validating configuration before data retrieval.

        """
        return widgets.Button(
            description="Validate Configuration",
            button_style="",
            layout=widgets.Layout(width="180px"),
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )

    def _create_retrieve_button(self):
        """Create data retrieval button.

        Returns:
            Button widget for initiating data retrieval or loading.

        """
        return widgets.Button(
            description="Retrieve Data",
            button_style="",
            layout=widgets.Layout(width="150px"),
            style={"button_color": "#86D5E0", "font_weight": "bold"},
        )

    def _create_step_selection_widgets(self):
        """Create enhanced step selection widgets.

        Creates multi-select widget for choosing forecast steps along with
        select all and deselect all buttons. Initially hidden until
        steps are available.
        """
        self.widgets["steps_display"] = self._create_steps_display()
        self.widgets["select_all_steps"] = self._create_select_all_button()
        self.widgets["deselect_all_steps"] = self._create_deselect_all_button()

        self.widgets["step_buttons"] = widgets.HBox(
            [self.widgets["select_all_steps"], self.widgets["deselect_all_steps"]],
            layout=widgets.Layout(display="none"),
        )

    def _create_steps_display(self):
        """Create multi-select widget for step selection.

        Returns:
            SelectMultiple widget for choosing forecast steps, initially hidden.

        """
        return widgets.SelectMultiple(
            options=[],
            value=[],
            description="Available Steps (Select All or Specific):",
            layout=widgets.Layout(width="400px", height="150px", display="none"),
            style={"description_width": "initial"},
        )

    def _create_select_all_button(self):
        """Create select all steps button.

        Returns:
            Button widget for selecting all available forecast steps.

        """
        return widgets.Button(
            description="Select All",
            button_style="",
            layout=widgets.Layout(width="100px"),
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )

    def _create_deselect_all_button(self):
        """Create deselect all steps button.

        Returns:
            Button widget for clearing all selected forecast steps.

        """
        return widgets.Button(
            description="Deselect All",
            button_style="",
            layout=widgets.Layout(width="120px"),
            style={"button_color": "#50DEA3", "font_weight": "bold"},
        )

    def get_widgets(self):
        """Return the widgets dictionary.

        Returns:
            Dictionary containing all created widget instances organized
            by widget type and purpose.

        """
        return self.widgets

    def create_scenario_file_widget(self, scenario_name, days_back=0, forecast_time=0):
        """Create a single scenario file widget with metadata.

        Creates a complete scenario file input row including file path input,
        days back selector, forecast time selector, and browse/delete buttons.
        Generates unique ID for tracking and interaction.

        Args:
            scenario_name: Name of the scenario (e.g., "D-0_00Z" or "Custom_1").
            days_back: Days back value for the scenario (0-7). Defaults to 0.
            forecast_time: Forecast time value in hours (0 or 12). Defaults to 0.

        Returns:
            Dictionary containing scenario widget information with keys:
                - name: Scenario name
                - widget: HBox widget containing all controls
                - id: Unique integer identifier
                - days_back: Days back value
                - forecast_time: Forecast time value
                - is_custom: Boolean indicating if custom scenario

        """
        self.cdf_scenario_counter += 1

        scenario_row = self._create_scenario_widget_row(
            scenario_name, days_back, forecast_time
        )

        return self._build_scenario_widget_dict(
            scenario_name, scenario_row, days_back, forecast_time
        )

    def _create_scenario_widget_row(self, scenario_name, days_back, forecast_time):
        """Create scenario file widget row with all controls.

        Args:
            scenario_name: Name of the scenario.
            days_back: Days back value for the scenario.
            forecast_time: Forecast time value.

        Returns:
            HBox widget containing file input and all control widgets.

        """
        scenario_file = self._create_scenario_file_input(scenario_name)
        days_back_select = self._create_days_back_dropdown(days_back)
        forecast_time_select = self._create_forecast_time_dropdown(forecast_time)
        browse_btn = self._create_scenario_browse_button()
        delete_btn = self._create_scenario_delete_button()

        return widgets.HBox(
            [
                scenario_file,
                days_back_select,
                forecast_time_select,
                browse_btn,
                delete_btn,
            ]
        )

    def _create_scenario_file_input(self, scenario_name):
        """Create file path input for scenario.

        Args:
            scenario_name: Name of the scenario for the label.

        Returns:
            Text widget for file path entry.

        """
        return widgets.Text(
            value="",
            description=f"{scenario_name} Scenario File:",
            disabled=False,
            placeholder="No file selected",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="250px"),
        )

    def _create_days_back_dropdown(self, days_back):
        """Create dropdown for selecting days back.

        Args:
            days_back: Default days back value.

        Returns:
            Dropdown widget with 0-7 day options.

        """
        return widgets.Dropdown(
            options=[(str(i), i) for i in range(8)],
            value=days_back,
            description="Days Back:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="120px"),
        )

    def _create_forecast_time_dropdown(self, forecast_time):
        """Create dropdown for selecting forecast time.

        Args:
            forecast_time: Default forecast time value (0 or 12).

        Returns:
            Dropdown widget with 00Z and 12Z options.

        """
        return widgets.Dropdown(
            options=[("00Z", 0), ("12Z", 12)],
            value=forecast_time,
            description="Time:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="100px"),
        )

    def _create_scenario_browse_button(self):
        """Create browse button for scenario file selection.

        Returns:
            Button widget for opening file browser.

        """
        return widgets.Button(
            description="Browse",
            button_style="",
            layout=widgets.Layout(width="80px"),
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )

    def _create_scenario_delete_button(self):
        """Create delete button for removing scenario.

        Returns:
            Button widget with red styling for deletion.

        """
        return widgets.Button(
            description="Delete",
            button_style="",
            layout=widgets.Layout(width="80px"),
            style={"button_color": "#f44336", "font_weight": "bold"},
        )

    def _build_scenario_widget_dict(
        self, scenario_name, scenario_row, days_back, forecast_time
    ):
        """Build scenario widget dictionary with metadata.

        Args:
            scenario_name: Name of the scenario.
            scenario_row: HBox widget containing all controls.
            days_back: Days back value.
            forecast_time: Forecast time value.

        Returns:
            Dictionary with complete scenario widget information.

        """
        return {
            "name": scenario_name,
            "widget": scenario_row,
            "id": self.cdf_scenario_counter,
            "days_back": days_back,
            "forecast_time": forecast_time,
            "is_custom": scenario_name.startswith("Custom_"),
        }

    def _parse_scenario_name(self, scenario_name):
        """Parse scenario name to extract metadata.

        Attempts to extract days back and forecast time from scenario names
        in format "D-{days}_{time}Z" (e.g., "D-0_00Z", "D-3_12Z").

        Args:
            scenario_name: Scenario name string to parse.

        Returns:
            Dictionary containing:
                - days_back: Extracted or default days back value
                - forecast_time: Extracted or default forecast time
                - description: Human-readable description of the scenario

        """
        if scenario_name.startswith("D-") and "_" in scenario_name:
            parsed = self._try_parse_scenario_format(scenario_name)
            if parsed:
                return parsed

        return self._get_default_scenario_metadata()

    def _try_parse_scenario_format(self, scenario_name):
        """Attempt to parse scenario name in D-X_YZ format.

        Args:
            scenario_name: Scenario name to parse.

        Returns:
            Dictionary with parsed values or None if parsing fails.

        """
        parts = scenario_name.split("_")
        if len(parts) != 2:
            return None

        days_part = parts[0].replace("D-", "")
        time_part = parts[1].replace("Z", "")

        try:
            days_back = int(days_part)
            forecast_time = int(time_part)

            return {
                "days_back": days_back,
                "forecast_time": forecast_time,
                "description": f"Forecast from {days_back} days ago at {forecast_time:02d}Z",
            }
        except ValueError:
            return None

    def _get_default_scenario_metadata(self):
        """Get default scenario metadata for unparseable names.

        Returns:
            Dictionary with default values and custom scenario description.

        """
        return {
            "days_back": 0,
            "forecast_time": 0,
            "description": "Custom scenario - set days back and time",
        }

    def create_file_input_for_type(self, file_type, file_description):
        """Create a file input widget for a specific file type.

        Creates a row with text input for file path and browse button for
        file selection dialog.

        Args:
            file_type: Type identifier for the file (e.g., "fc", "cf", "pf").
            file_description: Human-readable description for the file type
                (e.g., "Deterministic Forecast").

        Returns:
            HBox widget containing file path text input and browse button.

        """
        file_display = self._create_file_path_input(file_description)
        browse_btn = self._create_file_browse_button()

        return widgets.HBox([file_display, browse_btn])

    def _create_file_path_input(self, file_description):
        """Create text input for file path entry.

        Args:
            file_description: Description for the file type.

        Returns:
            Text widget for file path input.

        """
        return widgets.Text(
            value="",
            description=f"{file_description} File Path:",
            disabled=False,
            placeholder="Enter file path or use Browse button",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="400px"),
        )

    def _create_file_browse_button(self):
        """Create browse button for file selection.

        Returns:
            Button widget for opening file browser dialog.

        """
        return widgets.Button(
            description="Browse",
            button_style="",
            layout=widgets.Layout(width="100px"),
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )
