import ipywidgets as widgets
from helpers.parameter_mapper import ConfigurationManager
from IPython.display import display


class UILayoutManager:
    """Handles UI layout and section organization."""

    def __init__(self, widgets_dict, map_handler):
        """Initialize layout manager."""
        self.widgets = widgets_dict
        self.map_handler = map_handler
        self.config_manager = ConfigurationManager()

    def display_interface(self):
        """Display the complete interface."""
        header = self._create_header()
        configuration_accordion = self._create_configuration_section()
        visualization_accordion = self._create_visualization_section()

        main_interface = widgets.VBox(
            [
                self.widgets["description_style"],
                header,
                configuration_accordion,
                visualization_accordion,
            ],
            layout=widgets.Layout(padding="20px"),
        )

        display(main_interface)

    def _create_header(self):
        """Create the header section."""
        return widgets.HTML(
            value="""
            <div style="display: flex; flex-direction: column; align-items: center; margin: 0; padding: 0; text-align: center;">
                <img src="../helpers/widgets/assets/evalkit_logo_v2.png" style="height: 60px; width: auto; margin-bottom: 8px; image-rendering: -webkit-optimize-contrast; image-rendering: crisp-edges;" alt="EvalKit Logo">
                <h1 style="color: #171A35; margin: 0; padding: 0; font-weight: bold; font-size: 28px; line-height: 1.2;">Interactive Weather Model Timeseries Analysis</h1>
            </div>
            """,
            layout=widgets.Layout(margin="0px", padding="0px"),
        )

    def _create_configuration_section(self):
        """Create the configuration accordion section."""
        data_retrieval_section = self._create_data_retrieval_section()
        parameter_analysis_section = self._create_parameter_analysis_section()
        observation_section = self._create_observation_section()

        top_horizontal_content = widgets.HBox(
            [data_retrieval_section, parameter_analysis_section, observation_section],
            layout=widgets.Layout(width="100%", margin="0px", overflow="visible"),
        )

        configuration_accordion = widgets.Accordion(
            children=[top_horizontal_content],
            titles=["Configuration Panel"],
        )
        configuration_accordion.selected_index = 0
        return configuration_accordion

    def _create_visualization_section(self):
        """Create the visualization accordion section."""
        # Model visibility toggle row — reuses the same checkbox widget objects
        # from the Parameter & Analysis section so state stays in sync.
        model_toggle_controls = []
        for model_key, model_info in self.config_manager.models.items():
            model_short = model_key.split("-")[0]
            checkbox_name = f"{model_short}_checkbox"
            if checkbox_name in self.widgets:
                model_toggle_controls.append(self.widgets[checkbox_name])
        if "observations_checkbox" in self.widgets:
            model_toggle_controls.append(self.widgets["observations_checkbox"])

        model_visibility_row = widgets.VBox(
            [
                widgets.HTML(
                    "<b style='color:#171A35; font-size:0.9em;'>Model Visibility:</b>"
                ),
                widgets.HBox(
                    model_toggle_controls,
                    layout=widgets.Layout(flex_wrap="wrap", margin="2px 0 6px 0"),
                ),
            ],
            layout=widgets.Layout(margin="4px 0 4px 0"),
        )

        plot_section = widgets.VBox(
            [model_visibility_row, self.widgets["plot_output"]],
            layout=widgets.Layout(width="65%", margin="0 10px 0 0"),
        )

        manual_coord_box = widgets.VBox(
            [
                widgets.HBox(
                    [
                        self.widgets["manual_lat_input"],
                        self.widgets["manual_lon_input"],
                        self.widgets["add_manual_point_btn"],
                    ]
                ),
                self.widgets["manual_coord_status"],
            ]
        )

        map_section = widgets.VBox(
            [
                widgets.HBox(
                    [
                        self.widgets["clear_points_btn"],
                        self.widgets["clear_drawings_btn"],
                    ],
                    layout=widgets.Layout(margin="5px 0px"),
                ),
                manual_coord_box,
                self.map_handler.get_map_widget(),
            ],
            layout=widgets.Layout(width="33%", margin="0 0 0 10px"),
        )

        bottom_horizontal_section = widgets.HBox(
            [plot_section, map_section],
            layout=widgets.Layout(width="100%", margin="0px 0px"),
        )

        visualization_accordion = widgets.Accordion(
            children=[bottom_horizontal_section],
            titles=["Visualization Panel"],
        )
        visualization_accordion.selected_index = 0
        return visualization_accordion

    def _create_data_retrieval_section(self):
        """Create data retrieval section."""
        source_selection = widgets.VBox(
            [
                widgets.HTML(
                    "<h2 style='color: #00BCD4; margin-bottom: 10px;'>Data Source</h2>"
                ),
                self.widgets["data_source"],
            ]
        )

        mars_section = self._create_mars_section()
        local_section = self._create_local_section()

        mars_conditional = widgets.VBox([])
        local_conditional = widgets.VBox([])

        self._mars_conditional = mars_conditional
        self._local_conditional = local_conditional
        self._mars_section = mars_section
        self._local_section = local_section

        self.update_data_section("mars")

        return widgets.VBox(
            [source_selection, mars_conditional, local_conditional],
            layout=widgets.Layout(width="32%", margin="0 10px 0 0"),
        )

    def _create_mars_section(self):
        """Create MARS configuration section."""
        return widgets.VBox(
            [
                widgets.HTML(
                    "<h3 style='color: #616161; margin-bottom: 10px;'>MARS Archive Configuration</h3>"
                ),
                # Parameters & Model
                widgets.VBox(
                    [
                        widgets.HTML(
                            "<h4 style='color: #50DEA3; margin-bottom: 5px;'>Parameters & Model</h4>"
                        ),
                        self.widgets["param"],
                        self.widgets["model"],
                        widgets.HBox([self.widgets["rd_class"], self.widgets["rd_expver"]]),
                    ]
                ),
                # Forecast Configuration
                widgets.VBox(
                    [
                        widgets.HTML(
                            "<h4 style='color: #50DEA3; margin-bottom: 5px;'>Forecast Configuration</h4>"
                        ),
                        self.widgets["start_date"],
                        self.widgets["time"],
                        self.widgets["forecast_steps"],
                    ]
                ),
                # Geographic Area
                widgets.VBox(
                    [
                        widgets.HTML(
                            "<h4 style='color: #50DEA3; margin-bottom: 5px;'>Geographic Area</h4>"
                        ),
                        widgets.HBox([self.widgets["north"], self.widgets["south"]]),
                        widgets.HBox([self.widgets["west"], self.widgets["east"]]),
                        widgets.HBox([self.widgets["reset_bbox_btn"]]),
                    ]
                ),
                # Grid Resolution
                widgets.VBox(
                    [
                        widgets.HTML(
                            "<h4 style='color: #50DEA3; margin-bottom: 5px;'>Grid Settings</h4>"
                        ),
                        self.widgets["grid_resolution"],
                    ]
                ),
                # Action Buttons
                widgets.VBox(
                    [
                        widgets.HTML(
                            "<h4 style='color: #50DEA3; margin-bottom: 5px;'>Actions</h4>"
                        ),
                        widgets.HBox(
                            [
                                self.widgets["preview_btn"],
                                self.widgets["retrieve_btn"],
                                self.widgets["reset_btn"],
                            ]
                        ),
                    ]
                ),
                self.widgets["mars_info_display"],
            ]
        )

    def _create_local_section(self):
        """Create local file selection section."""
        file_sections = []

        # Get all models from config
        models = self.config_manager.models

        for model_key, model_info in models.items():
            model_short = model_key.split("-")[0]  # e.g., "aifs" from "aifs-single"
            display_name = model_info.get("display_name", model_key)

            # Create section for this model
            model_section = widgets.VBox(
                [
                    widgets.HTML(
                        f"<h4 style='color: #50DEA3; margin-bottom: 10px;'>{display_name} File</h4>"
                    ),
                    self.widgets[f"file_path_input_{model_short}"],
                    widgets.HBox(
                        [self.widgets[f"browse_btn_{model_short}"]],
                        layout=widgets.Layout(margin="5px 0px"),
                    ),
                    self.widgets[f"selected_file_{model_short}"],
                ]
            )
            file_sections.append(model_section)

        return widgets.VBox(
            [
                widgets.HTML(
                    "<h3 style='color: #616161; margin-bottom: 10px;'>Local File Selection</h3>"
                ),
                *file_sections,  # Unpack all model sections
                # Load Button (triggers validation)
                widgets.VBox(
                    [self.widgets["load_both_btn"]],
                    layout=widgets.Layout(align_items="center", margin="10px 0px"),
                ),
                self.widgets["local_info_display"],
            ]
        )

    def _create_parameter_analysis_section(self):
        """Create parameter analysis section."""
        # Create dynamic containers
        self.widgets["units_container"] = widgets.VBox(
            [
                widgets.HTML("<b>Unit Settings:</b>"),
                widgets.HBox(
                    [
                        self.widgets["temperature_unit"],
                        self.widgets["precipitation_unit"],
                    ]
                ),
            ],
            layout=widgets.Layout(margin="10px 0px", display="none"),
        )

        self.widgets["precipitation_container"] = widgets.VBox(
            [
                widgets.HBox([self.widgets["precipitation_interval"]]),
                self.widgets["precipitation_status"],
            ],
            layout=widgets.Layout(margin="10px 0px", display="none"),
        )

        # Dynamically create model checkboxes from config
        model_checkboxes = []
        models = self.config_manager.models
        for model_key, _ in models.items():
            model_short = model_key.split("-")[0]
            checkbox_widget = self.widgets.get(f"{model_short}_checkbox")
            if checkbox_widget:
                model_checkboxes.append(checkbox_widget)

        return widgets.VBox(
            [
                widgets.HTML(
                    "<h2 style='color: #00BCD4; margin-bottom: 15px;'>Parameter & Analysis Controls</h2>"
                ),
                # Parameter Selection
                widgets.HBox(
                    [
                        self.widgets["processing_param"],
                        self.widgets["refresh_params_btn"],
                    ],
                    layout=widgets.Layout(margin="5px 0px"),
                ),
                widgets.VBox(
                    [
                        widgets.HTML("<b>Model Selection:</b>"),
                        widgets.VBox(
                            [
                                *model_checkboxes,
                                self.widgets["observations_checkbox"],
                            ]
                        ),
                    ],
                    layout=widgets.Layout(margin="10px 0px"),
                ),
                # Dynamic containers
                self.widgets["units_container"],
                self.widgets["precipitation_container"],
            ],
            layout=widgets.Layout(width="34%", margin="0 10px"),
        )

    def _create_observation_section(self):
        """Create observation section."""
        retrieval_config = self._create_observation_retrieval_config()
        browsing_config = self._create_observation_browsing_config()

        retrieval_conditional = widgets.VBox([])
        browsing_conditional = widgets.VBox([])

        self._retrieval_conditional = retrieval_conditional
        self._browsing_conditional = browsing_conditional
        self._retrieval_config = retrieval_config
        self._browsing_config = browsing_config

        self.update_observation_section("browse")

        return widgets.VBox(
            [
                widgets.HTML(
                    "<h2 style='color: #00BCD4; margin-bottom: 15px;'>Observation Data Integration</h2>"
                ),
                self.widgets["has_observations"],
                widgets.VBox(
                    [
                        widgets.HTML(
                            "<h3 style='color: #616161; margin: 15px 0 10px 0;'>Data Source</h3>"
                        ),
                        self.widgets["retrieve_observations"],
                    ]
                ),
                retrieval_conditional,
                browsing_conditional,
                self.widgets["obs_info_display"],
                self.widgets["obs_time_explorer"],
                self.widgets["obs_colorbar"],
            ],
            layout=widgets.Layout(width="32%", margin="0 0 0 10px", overflow="visible"),
        )

    def _create_observation_retrieval_config(self):
        """Create observation retrieval configuration."""
        return widgets.VBox(
            [
                widgets.HTML(
                    "<h4 style='color: #50DEA3; margin-bottom: 10px;'>Retrieve from ECMWF</h4>"
                ),
                # VINO Configuration
                widgets.VBox(
                    [
                        widgets.HTML(
                            "<p style='margin: 5px 0; color: #666; font-size: 0.9em;'><b>VINO Configuration:</b></p>"
                        ),
                        self.widgets["vino_path"],
                    ]
                ),
                self.widgets["obs_param_info"],
                self.widgets["obs_sources"],
                # Period and Times
                widgets.HBox(
                    [
                        self.widgets["obs_period"],
                        widgets.VBox(
                            [self.widgets["obs_times_display"]],
                            layout=widgets.Layout(margin="0 0 0 10px"),
                        ),
                    ]
                ),
                # Date Range
                widgets.HBox(
                    [
                        self.widgets["obs_start_date"],
                        self.widgets["obs_end_date"],
                    ],
                    layout=widgets.Layout(margin="10px 0"),
                ),
                # Output Directory
                widgets.VBox(
                    [
                        widgets.HTML(
                            "<p style='margin: 5px 0; color: #666; font-size: 0.9em;'><b>Output folder:</b></p>"
                        ),
                        self.widgets["obs_output_dir"],
                    ]
                ),
                # Retrieve Button
                widgets.HBox(
                    [self.widgets["retrieve_obs_btn"]],
                    layout=widgets.Layout(align_items="center", margin="15px 0"),
                ),
            ]
        )

    def _create_observation_browsing_config(self):
        """Create observation browsing configuration with path input."""
        return widgets.VBox(
            [
                widgets.HTML(
                    "<h4 style='color: #50DEA3; margin-bottom: 10px;'>Browse Existing Folder</h4>"
                ),
                self.widgets["obs_folder_path_input"],
                widgets.HBox(
                    [self.widgets["browse_obs_btn"]],
                    layout=widgets.Layout(align_items="center", margin="10px 0"),
                ),
                self.widgets["obs_folder_display"],
                widgets.HTML(
                    "<p style='font-size: 0.85em; color: #666; font-style: italic;'>Automatic parameter validation after folder selection</p>"
                ),
            ]
        )

    def update_data_section(self, data_source_value):
        """Update data retrieval section based on source selection."""
        if data_source_value == "mars":
            self._mars_conditional.children = [self._mars_section]
            self._local_conditional.children = []
        else:
            self._mars_conditional.children = []
            self._local_conditional.children = [self._local_section]

    def update_observation_section(self, retrieval_mode_value):
        """Update observation section based on retrieval mode."""
        if retrieval_mode_value == "retrieve":
            self._retrieval_conditional.children = [self._retrieval_config]
            self._browsing_conditional.children = []
        else:
            self._retrieval_conditional.children = []
            self._browsing_conditional.children = [self._browsing_config]
