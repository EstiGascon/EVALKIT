from datetime import date, timedelta

import ipywidgets as widgets
from helpers.parameter_mapper import ConfigurationManager


class WidgetConfiguration:
    """Handles widget creation and initial configuration."""

    def __init__(self):
        """Initialize widget configuration."""
        self.widgets = {}
        self.config_manager = ConfigurationManager()
        self._create_all_widgets()

    def _create_all_widgets(self):
        """Create all widgets with their initial configurations."""
        self._create_data_source_widgets()
        self._create_mars_widgets()
        self._create_local_file_widgets()
        self._create_parameter_widgets()
        self._create_observation_widgets()
        self._create_bbox_widgets()
        self._create_unit_widgets()
        self._create_action_widgets()
        self._create_display_widgets()
        self._create_style_widgets()

    def _create_data_source_widgets(self):
        """Create data source selection widgets."""
        self.widgets["data_source"] = widgets.RadioButtons(
            options=[
                ("Download from MARS Archive", "mars"),
                ("Load Local File(s)", "local"),
            ],
            value="mars",
            description="",
            layout=widgets.Layout(width="400px"),
        )

    def _create_mars_widgets(self):
        """Create MARS-specific widgets."""
        # Get parameters from config
        param_options = self.config_manager.get_parameters_for_ui()
        default_params = self.config_manager.get_default_parameters()

        self.widgets["param"] = widgets.SelectMultiple(
            options=param_options,
            value=default_params,
            description="Parameters:",
            layout=widgets.Layout(width="400px", height="200px"),
        )

        # Get models from config
        model_options = self.config_manager.get_models_for_ui()

        self.widgets["model"] = widgets.SelectMultiple(
            options=model_options,
            value=[key for _, key in model_options],
            description="Models:",
            layout=widgets.Layout(width="300px", height="80px"),
        )

        self.widgets["start_date"] = widgets.DatePicker(
            description="Forecast initialisation date:",
            value=date.today(),
            layout=widgets.Layout(width="320px"),
        )

        self.widgets["end_date"] = widgets.DatePicker(
            description="End date:",
            value=date.today(),
            layout=widgets.Layout(width="320px"),
        )

        # Get available times from config
        available_times = self.config_manager.get_available_times()
        time_options = [(t, t) for t in available_times]
        default_time = self.config_manager.ui_settings.get("default_time", "00:00:00")

        self.widgets["time"] = widgets.Dropdown(
            options=time_options,
            value=default_time,
            description="Forecast run time:",
            layout=widgets.Layout(width="220px"),
        )

        self.widgets["forecast_steps"] = widgets.SelectMultiple(
            options=[],
            value=[],
            description="Forecast steps (hours):",
            layout=widgets.Layout(width="300px", height="150px"),
        )

        self.widgets["grid_resolution"] = widgets.Text(
            value="",
            description="Grid Resolution (°):",
            layout=widgets.Layout(width="200px"),
        )

        self.widgets["rd_class"] = widgets.Text(
            value="rd",
            description="Class:",
            placeholder="e.g. rd, od, ai",
            layout=widgets.Layout(width="200px", display="none"),
        )

        self.widgets["rd_expver"] = widgets.Text(
            value="",
            description="Exp. version:",
            placeholder="e.g. iekm",
            layout=widgets.Layout(width="260px", display="none"),
        )

    def _create_local_file_widgets(self):
        """Create local file selection widgets."""
        # Get all models from config to create file selection widgets
        models = self.config_manager.models.keys()

        for model_key in models:
            # Extract short name (e.g., "aifs" from "aifs-single")
            model_short = model_key.split("-")[0]

            self.widgets[f"selected_file_{model_short}"] = widgets.HTML(
                value=f'<p style="color: #666; font-style: italic;">No {model_short.upper()} file selected</p>',
                description=f"{model_short.upper()} File:",
                layout=widgets.Layout(width="400px", height="60px"),
            )

            self.widgets[f"browse_btn_{model_short}"] = widgets.Button(
                description=f"Browse {model_short.upper()}",
                icon="folder-open",
                layout=widgets.Layout(width="120px"),
                disabled=True,
            )

            self.widgets[f"file_path_input_{model_short}"] = widgets.Text(
                value="",
                description=f"{model_short.upper()} Path:",
                placeholder=f"Enter {model_short.upper()} file path or use Browse button",
                style={"description_width": "initial"},
                layout=widgets.Layout(width="400px"),
                tooltip=f"Enter the full path to your {model_short.upper()} GRIB file",
            )

        self.widgets["load_both_btn"] = widgets.Button(
            description="Load File",
            icon="cloud-upload",
            layout=widgets.Layout(width="150px"),
            disabled=True,
        )

    def _create_parameter_widgets(self):
        """Create parameter analysis widgets."""
        self.widgets["processing_param"] = widgets.Dropdown(
            options=[("No data loaded", "none")],
            value="none",
            description="Select Parameter:",
            layout=widgets.Layout(width="300px"),
            disabled=True,
        )

        self.widgets["refresh_params_btn"] = widgets.Button(
            description="Refresh Parameters",
            icon="refresh",
            layout=widgets.Layout(width="150px"),
            disabled=True,
        )

        # Create checkboxes for each model from config
        models = self.config_manager.models
        for model_key, model_info in models.items():
            model_short = model_key.split("-")[0]  # e.g., "aifs" from "aifs-single"
            display_name = model_info.get("display_name", model_key)

            self.widgets[f"{model_short}_checkbox"] = widgets.Checkbox(
                value=True,
                description=f"{display_name}",
                layout=widgets.Layout(width="150px"),
                style={"description_width": "initial"},
            )

        self.widgets["observations_checkbox"] = widgets.Checkbox(
            value=True,
            description="Observations",
            layout=widgets.Layout(width="120px"),
            style={"description_width": "initial"},
            disabled=True,
        )

    def _create_observation_widgets(self):
        """Create observation data widgets."""
        self.widgets["has_observations"] = widgets.RadioButtons(
            options=[("No", "no"), ("Yes", "yes")],
            value="no",
            description="Do you have observation data?",
            layout=widgets.Layout(width="300px"),
        )

        self.widgets["retrieve_observations"] = widgets.RadioButtons(
            options=[
                ("Browse existing folder", "browse"),
                ("Retrieve new observations", "retrieve"),
            ],
            value="browse",
            description="Observation data:",
            layout=widgets.Layout(width="300px"),
        )

        self.widgets["obs_folder_display"] = widgets.HTML(
            value='<p style="color: #666; font-style: italic;">No observation folder selected</p>',
            description="Observation Folder:",
            layout=widgets.Layout(width="400px", height="60px"),
        )

        self.widgets["browse_obs_btn"] = widgets.Button(
            description="Browse Observations",
            icon="folder-open",
            layout=widgets.Layout(width="150px"),
            disabled=True,
        )

        self.widgets["obs_folder_path_input"] = widgets.Text(
            value="",
            description="Observation Path:",
            placeholder="Enter observation folder path or use Browse button",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="400px"),
            tooltip="Enter the full path to your observation data folder",
            disabled=True,
        )

        self.widgets["obs_sources"] = widgets.SelectMultiple(
            options=[
                ("SYNOP", "synop"),
                ("HDOBS", "hdobs"),
                ("Both", "synop hdobs"),
            ],
            value=["synop hdobs"],
            description="Data sources:",
            layout=widgets.Layout(width="250px", height="80px"),
            disabled=True,
        )

        self.widgets["vino_path"] = widgets.Text(
            value="/home/moz/bin/vino_getgeo",
            description="VINO executable path:",
            layout=widgets.Layout(width="400px"),
            disabled=True,
        )

        self.widgets["obs_period"] = widgets.Dropdown(
            options=[("6 hours", "6"), ("12 hours", "12"), ("24 hours", "24")],
            value="24",
            description="Period:",
            layout=widgets.Layout(width="150px"),
            disabled=True,
        )

        for date_type in ["start", "end"]:
            default_date = (
                date.today() - timedelta(days=2)
                if date_type == "start"
                else date.today()
            )
            self.widgets[f"obs_{date_type}_date"] = widgets.DatePicker(
                description=f"{date_type.capitalize()} date:",
                value=default_date,
                layout=widgets.Layout(width="200px"),
                disabled=True,
            )

        self.widgets["obs_output_dir"] = widgets.Text(
            value="./retrieved_observations",
            description="Output folder:",
            layout=widgets.Layout(width="300px"),
            disabled=True,
        )

        self.widgets["retrieve_obs_btn"] = widgets.Button(
            description="Retrieve Observations",
            icon="download",
            layout=widgets.Layout(width="150px"),
            disabled=True,
        )

        # --- Lead-time explorer (hidden until observations are loaded) ---
        self.widgets["obs_time_prev_btn"] = widgets.Button(
            description="◀ Prev",
            layout=widgets.Layout(width="75px"),
            disabled=True,
        )
        self.widgets["obs_time_next_btn"] = widgets.Button(
            description="Next ▶",
            layout=widgets.Layout(width="75px"),
            disabled=True,
        )
        self.widgets["obs_time_label"] = widgets.HTML(
            value="<span style='font-size:0.85em;color:#555;'>–</span>",
            layout=widgets.Layout(min_width="160px", max_width="300px"),
        )
        self.widgets["obs_time_explorer"] = widgets.VBox(
            [
                widgets.HTML(
                    "<p style='margin:6px 0 2px;font-size:0.85em;color:#444;'>"
                    "<b>Explore observation lead times:</b></p>"
                ),
                widgets.HBox(
                    [
                        self.widgets["obs_time_prev_btn"],
                        self.widgets["obs_time_label"],
                        self.widgets["obs_time_next_btn"],
                    ],
                    layout=widgets.Layout(align_items="center", margin="2px 0"),
                ),
            ],
            layout=widgets.Layout(display="none", margin="6px 0 0 0"),
        )
        # Colorbar legend (an HTML widget updated dynamically)
        self.widgets["obs_colorbar"] = widgets.HTML(
            value="",
            layout=widgets.Layout(display="none", margin="4px 0 0 0"),
        )

    def _create_bbox_widgets(self):
        """Create bounding box widgets."""
        bbox_defaults = self.config_manager.get_default_bbox()

        for coord in ["north", "west", "south", "east"]:
            self.widgets[coord] = widgets.FloatText(
                value=bbox_defaults[coord],
                description=f"{coord.capitalize()}:",
                layout=widgets.Layout(width="180px"),
            )

        self.widgets["reset_bbox_btn"] = widgets.Button(
            description="Reset to Default",
            icon="refresh",
            layout=widgets.Layout(width="150px"),
        )

        self.widgets["clear_drawings_btn"] = widgets.Button(
            description="Clear Drawings",
            icon="eraser",
            layout=widgets.Layout(width="150px"),
        )

        self.widgets["manual_lat_input"] = widgets.FloatText(
            value=0.0,
            description="Lat",
            disabled=False,
            step=0.1,
            style={"description_width": "30px"},
            layout=widgets.Layout(width="90px"),
        )

        self.widgets["manual_lon_input"] = widgets.FloatText(
            value=0.0,
            description="Lon",
            disabled=False,
            step=0.1,
            style={"description_width": "30px"},
            layout=widgets.Layout(width="90px"),
        )

        self.widgets["add_manual_point_btn"] = widgets.Button(
            description="Add Point",
            button_style="",
            icon="plus",
            layout=widgets.Layout(width="130px"),
        )
        self.widgets["manual_coord_status"] = widgets.HTML(
            value="", layout=widgets.Layout(width="100%")
        )

    def _create_unit_widgets(self):
        """Create unit selection widgets."""
        self.widgets["temperature_unit"] = widgets.Dropdown(
            options=[("°C", "celsius"), ("K", "kelvin")],
            value="celsius",
            description="Temperature:",
            layout=widgets.Layout(width="170px", display="none"),
        )

        self.widgets["precipitation_unit"] = widgets.Dropdown(
            options=[("mm", "mm"), ("m", "m")],
            value="mm",
            description="Precipitation:",
            layout=widgets.Layout(width="170px", display="none"),
        )

        self.widgets["precipitation_interval"] = widgets.Dropdown(
            options=[
                ("6 hours", 6),
                ("12 hours", 12),
                ("24 hours", 24),
                ("48 hours", 48),
            ],
            value=24,
            description="Accumulated period:",
            layout=widgets.Layout(width="260px"),
            disabled=True,
        )

    def _create_action_widgets(self):
        """Create action buttons."""
        actions = [
            ("preview_btn", "Preview Settings", "eye"),
            ("retrieve_btn", "Retrieve Data", "download"),
            ("reset_btn", "Reset All", "undo"),
            ("clear_points_btn", "Clear All Points", "eraser"),
        ]

        for btn_id, description, icon in actions:
            self.widgets[btn_id] = widgets.Button(
                description=description,
                icon=icon,
                layout=widgets.Layout(width="150px"),
            )

    def _create_display_widgets(self):
        """Create information display widgets."""
        display_widgets = [
            "local_info_display",
            "mars_info_display",
            "obs_info_display",
            "obs_times_display",
            "obs_param_info",
            "precipitation_status",
        ]

        for widget_name in display_widgets:
            self.widgets[widget_name] = widgets.HTML(
                value="",
                layout=widgets.Layout(
                    width="100%" if "info" in widget_name else "300px",
                    margin="10px 0px",
                ),
            )

        self.widgets["plot_output"] = widgets.Output(
            layout=widgets.Layout(width="100%", height="500px")
        )

    def _create_style_widgets(self):
        """Create styling widgets."""
        self.widgets["description_style"] = widgets.HTML(
            value="""
            <style>
            .widget-label, .widget-label-basic {
                color: #171A35 !important;
                font-weight: bold !important;
            }
            .jp-RenderedHTMLCommon label {
                color: #171A35 !important;
                font-weight: bold !important;
            }
            </style>
            """
        )

    def get_widgets(self):
        """Return the widgets dictionary."""
        return self.widgets
