"""Layout management for ensemble tool interface."""

import traceback

import ipywidgets as widgets
from IPython.display import display


class UILayoutManager:
    """Manages layout construction and display for the ensemble interface."""

    def __init__(
        self, widgets_dict, plot_configs, use_cases, map_handler, widget_config=None
    ):
        """Initialize layout manager.

        Args:
            widgets_dict: Dictionary of all widgets
            plot_configs: Plot configuration dictionary
            use_cases: Use cases from config
            map_handler: Optional map handler instance
            widget_config: Optional widget configuration instance

        """
        self.widgets = widgets_dict
        self.widget_config = widget_config
        self.data_alert_container = widgets.VBox([])
        self.observation_alert_container = widgets.VBox([])
        self.plotting_alert_container = widgets.VBox([])
        self.general_alert_container = widgets.VBox([])
        self.configuration_container = widgets.VBox([])
        self.map_instructions_container = widgets.VBox([])
        self.plot_controls_container = widgets.VBox([])
        self.map_actions_container = widgets.VBox([])
        self.plot_output_container = widgets.VBox(
            [
                widgets.HTML("""
                <div style="background-color: #f0f8ff; padding: 20px; text-align: center;
                        border-radius: 5px; border-left: 4px solid #4DD0E1;">
                    <span style="color: #006064;">Plot output area ready for automatic plotting</span>
                </div>
            """)
            ]
        )

    def display_interface(self):
        """Display the complete interface."""
        viz_section = self._create_visualization_section()
        self._extract_visualization_containers_from_section(viz_section)

        config_section = widgets.VBox(
            [
                self.widgets["data_source_selection"],
                self.configuration_container,
            ]
        )

        viz_with_alerts = widgets.VBox([viz_section])

        main_layout = widgets.VBox(
            [
                self._create_header(),
                self.widgets["plot_type_selection"],
                config_section,
                viz_with_alerts,
                self.general_alert_container,
            ],
            layout=widgets.Layout(width="100%", padding="20px"),
        )

        display(main_layout)

    def _create_header(self):
        """Create the header with logo and title."""
        return widgets.HTML(
            value="""
            <div style="display: flex; flex-direction: column; align-items: center; margin: 0; padding: 0; text-align: center;">
                <img src="../helpers/widgets/assets/evalkit_logo_v2.png" style="height: 60px; width: auto; margin-bottom: 8px; image-rendering: -webkit-optimize-contrast; image-rendering: crisp-edges;" alt="EvalKit Logo">
                <h1 style="color: #171A35; margin: 0; padding: 0; font-weight: bold; font-size: 28px; line-height: 1.2;">Probabilistic Forecast Analysis Tool</h1>
            </div>
            """,
            layout=widgets.Layout(margin="0px", padding="0px"),
        )

    def _create_visualization_section(self):
        """Create the main visualization section."""
        viz_header = widgets.Button(
            description="▼ Automatic Visualization Platform",
            button_style="",
            layout=widgets.Layout(width="100%"),
            style={"button_color": "#E0F7FA", "font_weight": "bold"},
        )

        top_row = widgets.HBox(
            [
                widgets.VBox(
                    [
                        widgets.HTML(
                            "<h4 style='color: #86D5E0; margin-bottom: 15px;'>Plotting Configuration</h4>"
                        ),
                        widgets.VBox([], layout=widgets.Layout(width="100%")),
                        widgets.VBox([], layout=widgets.Layout(width="100%")),
                    ],
                    layout=widgets.Layout(width="48%", padding="10px"),
                ),
                widgets.VBox(
                    [
                        widgets.HTML(
                            "<h4 style='color: #86D5E0; margin-bottom: 15px;'>Geographic Selection</h4>"
                        ),
                        self.widgets["map_container"],
                        widgets.VBox(
                            [], layout=widgets.Layout(width="100%")
                        ),  # map_actions_container
                    ],
                    layout=widgets.Layout(width="48%", padding="10px"),
                ),
            ],
            layout=widgets.Layout(width="100%"),
        )

        bottom_row = widgets.VBox(
            [
                self.plotting_alert_container,
                widgets.HTML(
                    "<h4 style='color: #86D5E0; margin-bottom: 15px;'>Plot Output</h4>"
                ),
                widgets.VBox(
                    [
                        widgets.HTML("""
                    <div style="background-color: #f5f5f5; padding: 40px; text-align: center;
                               border: 2px dashed #ddd; border-radius: 8px;">
                        <h3 style="color: #666; margin-bottom: 10px;">Plot Output Area</h3>
                        <p style="color: #999;">Plots will appear here automatically after data loading</p>
                    </div>
                """)
                    ],
                    layout=widgets.Layout(width="100%"),
                ),
            ],
            layout=widgets.Layout(width="100%", padding="10px"),
        )

        viz_content = widgets.VBox(
            [top_row, bottom_row],
            layout=widgets.Layout(
                display="block", padding="10px", border="1px solid #ddd"
            ),
        )

        def toggle_viz_accordion(b):
            if viz_content.layout.display == "none":
                viz_content.layout.display = "block"
                b.description = "▼ Automatic Visualization Platform"
                b.style.button_color = "#86D5E0"
            else:
                viz_content.layout.display = "none"
                b.description = "▶ Automatic Visualization Platform"
                b.style.button_color = "#E0F7FA"

        viz_header.on_click(toggle_viz_accordion)

        return widgets.VBox([viz_header, viz_content])

    def _extract_visualization_containers_from_section(self, viz_section):
        """Extract container references from the visualization section.

        Args:
            viz_section: vizualisation section

        """  # noqa: D202

        try:
            if hasattr(viz_section, "children") and len(viz_section.children) >= 2:
                viz_content = viz_section.children[1]

                if hasattr(viz_content, "children") and len(viz_content.children) >= 2:
                    top_row = viz_content.children[0]
                    bottom_row = viz_content.children[1]

                    if hasattr(top_row, "children") and len(top_row.children) >= 2:
                        left_col = top_row.children[0]
                        right_col = top_row.children[1]

                        if (
                            hasattr(left_col, "children")
                            and len(left_col.children) >= 3
                        ):
                            left_col.children = (
                                left_col.children[0],
                                self.map_instructions_container,
                                self.plot_controls_container,
                            )

                        if (
                            hasattr(right_col, "children")
                            and len(right_col.children) >= 3
                        ):
                            right_col.children = (
                                right_col.children[0],
                                right_col.children[1],
                                self.map_actions_container,
                            )

                    if (
                        hasattr(bottom_row, "children")
                        and len(bottom_row.children) >= 2
                    ):
                        bottom_row.children = (
                            bottom_row.children[0],
                            bottom_row.children[1],
                            self.plot_output_container,
                        )

        except Exception as e:
            traceback.print_exc()
            print(f"ERROR in container extraction: {e}")

    def build_three_section_mars_layout(self, config, current_plot_type):
        """Build  three-section horizontal layout for MARS configuration.

        Args:
            config: Plot configuration dictionary
            current_plot_type: Currently selected plot type

        Returns:
            list: Layout widgets

        """
        mars_config_widgets = []
        mars_config_widgets.append(
            widgets.HTML(
                "<h4 style='color: #86D5E0; margin-bottom: 10px;'>Data Source & MARS Configuration</h4>"
            )
        )
        mars_config_widgets.append(
            widgets.HTML(
                "<h5 style='color: #50DEA3; margin-bottom: 5px;'>Model Selection</h5>"
            )
        )
        mars_config_widgets.append(self.widgets["model_selection_box"])
        if "custom_experiment_box" in self.widgets:
            mars_config_widgets.append(self.widgets["custom_experiment_box"])

        mars_config_widgets.append(
            widgets.HTML(
                "<h5 style='color: #50DEA3; margin-bottom: 5px;'>Forecast Configuration</h5>"
            )
        )

        date_time_widgets = self._get_date_time_widgets(config)
        if date_time_widgets and hasattr(date_time_widgets, "children"):
            mars_config_widgets.extend(date_time_widgets.children)

        if current_plot_type == "cdf":
            cdf_widgets = self._get_cdf_specific_widgets()
            if cdf_widgets and hasattr(cdf_widgets, "children"):
                mars_config_widgets.extend(cdf_widgets.children)

        mars_config_widgets.append(
            widgets.HTML(
                "<h5 style='color: #50DEA3; margin-bottom: 5px;'>Grid Configuration</h5>"
            )
        )
        mars_config_widgets.append(self.widgets["grid_resolution"])

        if current_plot_type != "cdf":
            steps_widgets = self._get_steps_widgets()
            if steps_widgets and hasattr(steps_widgets, "children"):
                mars_config_widgets.extend(steps_widgets.children)

        mars_config_section = widgets.VBox(
            mars_config_widgets,
            layout=widgets.Layout(
                width="33%", padding="10px", border="1px solid #ddd", margin="5px"
            ),
        )
        parameter_widgets = []
        parameter_widgets.append(
            widgets.HTML(
                "<h4 style='color: #86D5E0; margin-bottom: 10px;'>Parameter & Analysis Controls</h4>"
            )
        )
        parameter_widgets.append(
            widgets.HTML(
                "<h5 style='color: #50DEA3; margin-bottom: 5px;'>Parameter Selection</h5>"
            )
        )
        parameter_widgets.append(
            widgets.HTML(
                "<small style='color: #666;'>First parameter will be used for auto-plotting</small>"
            )
        )

        if "parameters" in self.widgets:
            parameter_widgets.append(self.widgets["parameters"])

        plot_specific_params = self._get_plot_specific_params(config)
        if plot_specific_params and hasattr(plot_specific_params, "children"):
            parameter_widgets.extend(plot_specific_params.children)

        parameter_section = widgets.VBox(
            parameter_widgets,
            layout=widgets.Layout(
                width="33%", padding="10px", border="1px solid #ddd", margin="5px"
            ),
        )
        geo_widgets = []
        geo_widgets.append(
            widgets.HTML(
                "<h4 style='color: #86D5E0; margin-bottom: 10px;'>Geographic Area</h4>"
            )
        )
        geo_widgets.append(widgets.HBox([self.widgets["north"], self.widgets["south"]]))
        geo_widgets.append(widgets.HBox([self.widgets["west"], self.widgets["east"]]))
        geo_widgets.append(
            widgets.HTML("""
            <div style="background-color: #E0F7FA; padding: 10px; border-radius: 5px;
                    margin-top: 10px; border-left: 4px solid #86D5E0;">
                <small style="color: #006064;">
                    Geographic area for MARS data retrieval.
                    Plots will be created automatically after loading.
                </small>
            </div>
        """)
        )

        geographic_section = widgets.VBox(
            geo_widgets,
            layout=widgets.Layout(
                width="33%", padding="10px", border="1px solid #ddd", margin="5px"
            ),
        )

        final_layout = widgets.HBox(
            [mars_config_section, parameter_section, geographic_section]
        )

        return [final_layout]

    def build_local_config_widgets(self, config, plot_type):
        """Build configuration widgets for local file mode.

        Args:
            config: Plot configuration dictionary
            plot_type: Type of plot

        Returns:
            list: List of widget sections

        """
        config_sections = []
        if plot_type != "cdf":
            file_inputs_section = self._create_file_inputs_section(config, plot_type)
            config_sections.append(file_inputs_section)
        if plot_type == "cdf":
            climate_section = self._create_climate_data_section()
            config_sections.append(climate_section)
            scenario_section = self._create_scenario_files_section()
            config_sections.append(scenario_section)

        return config_sections

    def _create_scenario_files_section(self):
        """Create scenario files section for CDF.

        Returns:
            widgets.VBox: Scenario files section

        """
        if not self.widgets.get("cdf_scenario_files"):
            self.widgets["cdf_scenario_files"] = []
            for days_back in range(4):
                for forecast_time in [0, 12]:
                    scenario_name = f"D-{days_back}_{forecast_time:02d}Z"
                    scenario_widget = self.widget_config.create_scenario_file_widget(
                        scenario_name, days_back, forecast_time
                    )
                    self.widgets["cdf_scenario_files"].append(scenario_widget)
        scenario_rows = [item["widget"] for item in self.widgets["cdf_scenario_files"]]
        scenario_rows.append(widgets.HBox([self.widgets["add_scenario_btn"]]))

        self.widgets["scenario_files_container"].children = scenario_rows

        return widgets.VBox(
            [self.widgets["scenario_files_container"]],
            layout=widgets.Layout(width="100%", margin="10px 0"),
        )

    def _create_file_inputs_section(self, config, plot_type):
        """Create file inputs section for non-CDF plots.

        Args:
            config: Plot configuration dictionary
            plot_type: Type of plot

        Returns:
            widgets.VBox: File inputs section

        """
        file_rows = []
        if "file_inputs" in self.widgets and self.widgets["file_inputs"]:
            for _file_type, file_widget in self.widgets["file_inputs"].items():
                file_rows.append(file_widget)

        return widgets.VBox(
            [widgets.VBox(file_rows, layout=widgets.Layout(width="100%"))],
            layout=widgets.Layout(width="100%", margin="10px 0"),
        )

    def _create_climate_data_section(self):
        """Create climate data file section for CDF.

        Returns:
            widgets.VBox: Climate data section

        """
        if "cd" not in self.widgets.get("file_inputs", {}):
            cd_file_row = self.widget_config.create_file_input_for_type(
                "cd", "Climate Data"
            )
            self.widgets["file_inputs"]["cd"] = cd_file_row

        cd_file_input = self.widgets["file_inputs"]["cd"]

        return widgets.VBox(
            [cd_file_input], layout=widgets.Layout(width="100%", margin="10px 0")
        )

    def create_observation_section(self):
        """Create observation data section for meteogram and plumes plots.

        Returns:
            widgets.VBox: Observation section widget

        """
        browse_section = widgets.VBox(
            [
                widgets.HBox(
                    [self.widgets["obs_folder_display"], self.widgets["browse_obs_btn"]]
                ),
                self.widgets["obs_status_display"],
            ],
            layout=widgets.Layout(display="none"),
        )

        retrieve_section = widgets.VBox(
            [
                widgets.HTML(
                    "<h5 style='color: #50DEA3; margin-bottom: 10px;'>Retrieve Configuration</h5>"
                ),
                widgets.HBox(
                    [
                        self.widgets["obs_parameters"],
                        self.widgets["obs_sources"],
                        self.widgets["obs_period"],
                        self.widgets["obs_times_display"],
                    ]
                ),
                widgets.HTML(
                    "<h5 style='color: #50DEA3; margin-bottom: 10px;'>Date Range & Output</h5>"
                ),
                widgets.HBox(
                    [
                        self.widgets["obs_start_date"],
                        self.widgets["obs_end_date"],
                        widgets.VBox(
                            [
                                widgets.HBox(
                                    [
                                        self.widgets["obs_output_dir"],
                                        self.widgets["browse_output_btn"],
                                    ]
                                )
                            ]
                        ),
                    ]
                ),
                widgets.HBox(
                    [self.widgets["retrieve_obs_btn"]],
                    layout=widgets.Layout(justify_content="center", margin="15px 0px"),
                ),
                self.widgets["obs_param_info"],
            ],
            layout=widgets.Layout(display="none"),
        )

        data_source_row = widgets.VBox(
            [
                widgets.HTML(
                    "<h4 style='color: #50DEA3; margin-bottom: 10px;'>Data Source</h4>"
                ),
                self.widgets["obs_data_source"],
            ],
            layout=widgets.Layout(display="none"),
        )

        observation_container = widgets.VBox(
            [
                widgets.HTML(
                    "<h4 style='color: #50DEA3; margin-bottom: 10px;'>Include Observation Data?</h4>"
                ),
                self.widgets["has_observations"],
                data_source_row,
                browse_section,
                retrieve_section,
                self.widgets["obs_colorbar"],
                self.widgets["obs_time_nav"],
            ]
        )
        self.browse_section = browse_section
        self.retrieve_section = retrieve_section
        self.data_source_row = data_source_row
        self.observation_container = observation_container

        accordion_header = widgets.Button(
            description="Observation Data Integration",
            button_style="",
            layout=widgets.Layout(width="100%"),
            style={"button_color": "#E0F7FA", "font_weight": "bold"},
        )

        accordion_content = widgets.VBox(
            [observation_container], layout=widgets.Layout(display="none")
        )

        def toggle_accordion(b):
            if accordion_content.layout.display == "none":
                accordion_content.layout.display = "block"
                b.description = "▼ Observation Data Integration"
                b.style.button_color = "#86D5E0"
            else:
                accordion_content.layout.display = "none"
                b.description = "▶ Observation Data Integration"
                b.style.button_color = "#E0F7FA"

        accordion_header.on_click(toggle_accordion)

        return widgets.VBox([accordion_header, accordion_content])

    def update_map_instructions(self, plot_type, plot_configs):
        """Update map instructions based on plot type.

        Args:
            plot_type: Currently selected plot type
            plot_configs: Plot configuration dictionary

        """
        config = plot_configs[plot_type]

        if config.get("requires_points"):
            instruction_text = (
                f"Click on the map to select ONE analysis point for {plot_type} plots. "
                "Point must be within the defined geographic area. "
                "Clicking a new location will move the analysis point."
            )

            instruction_widget = widgets.HTML(
                value=f"""
                <div style="background-color: #E0F7FA; padding: 10px; border-radius: 5px;
                        border-left: 4px solid #86D5E0; margin: 10px 0;">
                    <span style="color: #006064;">{instruction_text}</span>
                </div>
                """
            )

            self.map_instructions_container.children = [instruction_widget]
            manual_input_header = widgets.HTML(
                value="""
                <div style="margin: 15px 0 8px 0;">
                    <strong style="color: #86D5E0;">Or enter coordinates manually:</strong>
                </div>
                """
            )

            manual_input_row = widgets.HBox(
                [
                    self.widgets["manual_lat_input"],
                    self.widgets["manual_lon_input"],
                    self.widgets["add_manual_point_btn"],
                ],
                layout=widgets.Layout(justify_content="flex-start", margin="5px 0"),
            )

            clear_btn = widgets.Button(
                description="Clear Point",
                button_style="",
                layout=widgets.Layout(width="100px", margin="10px 0 0 0"),
                style={"button_color": "#D1D1D1", "font_weight": "bold"},
            )

            self.map_actions_container.children = [
                manual_input_header,
                manual_input_row,
                self.widgets["manual_coord_status"],
                clear_btn,
            ]

            return clear_btn

        else:
            instruction_text = f"Geographic area for {plot_type} analysis. Plots will be created automatically when data is loaded."

            instruction_widget = widgets.HTML(
                value=f"""
                <div style="background-color: #E0F7FA; padding: 10px; border-radius: 5px;
                        border-left: 4px solid #86D5E0; margin: 10px 0;">
                    <span style="color: #006064;">{instruction_text}</span>
                </div>
                """
            )

            self.map_instructions_container.children = [instruction_widget]
            self.map_actions_container.children = []

            return None

    def create_plot_interface(
        self, plot_type, available_parameters, auto_plot_parameter, auto_plot_palette=1
    ):
        """Create plot interface with conditional visibility.

        Args:
            plot_type: Current plot type
            available_parameters: List of available parameter tuples
            auto_plot_parameter: Currently selected parameter
            auto_plot_palette: Currently selected palette value

        Returns:
            widgets.VBox: Plot interface widget

        """
        if not available_parameters:
            available_parameters = [(auto_plot_parameter.upper(), auto_plot_parameter)]
        parameter_selector = widgets.Dropdown(
            options=available_parameters,
            value=auto_plot_parameter
            if auto_plot_parameter
            else available_parameters[0][1],
            description="",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="250px"),
        )

        unit_selector = widgets.Dropdown(
            options=[],
            value=None,
            description="",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="150px"),
        )

        step_selector = widgets.Dropdown(
            options=[],
            value=None,
            description="",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
        )

        palette_selector = widgets.Dropdown(
            options=[
                ("Basic Palette (0.5mm-500mm)", 1),
                ("Extended Palette (0.5mm-100mm)", 2),
                ("High Intensity Palette (10mm-700mm)", 3),
            ],
            value=auto_plot_palette,
            description="",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="180px"),
        )
        parameter_container = widgets.VBox(
            [
                widgets.HTML("<strong>Parameter:</strong>"),
                parameter_selector,
            ],
            layout=widgets.Layout(width="60%"),
        )

        unit_container = widgets.VBox(
            [
                widgets.HTML("<strong>Unit:</strong>"),
                unit_selector,
            ],
            layout=widgets.Layout(width="35%"),
        )

        step_container = widgets.VBox(
            [
                widgets.HTML("<strong>Step:</strong>"),
                step_selector,
            ],
            layout=widgets.Layout(width="45%"),
        )

        precip_accumulation_selector = widgets.Dropdown(
            options=[
                ("3-hourly", 3),
                ("6-hourly", 6),
                ("12-hourly", 12),
                ("24-hourly", 24),
                ("48-hourly", 48),
                ("72-hourly", 72),
                ("120-hourly", 120),
            ],
            value=24,
            description="",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="160px"),
        )

        precip_accumulation_container = widgets.VBox(
            [
                widgets.HTML("<strong>Precip Accumulation:</strong>"),
                precip_accumulation_selector,
            ],
            layout=widgets.Layout(width="40%", display="none"),
        )

        palette_container = widgets.VBox(
            [
                widgets.HTML("<strong>Palette:</strong>"),
                palette_selector,
            ],
            layout=widgets.Layout(width="50%"),
        )
        first_row = widgets.HBox(
            [
                parameter_container,
                unit_container,
            ],
            layout=widgets.Layout(width="100%", justify_content="space-between"),
        )

        second_row = widgets.HBox(
            [
                step_container,
                precip_accumulation_container,
                palette_container,
            ],
            layout=widgets.Layout(width="100%", justify_content="space-between"),
        )

        controls_layout = widgets.VBox(
            [first_row, second_row],
            layout=widgets.Layout(
                width="100%",
                padding="10px",
                border="1px solid #ddd",
                border_radius="5px",
            ),
        )
        clear_btn = widgets.Button(
            description="Clear Plot",
            button_style="",
            layout=widgets.Layout(width="100px"),
            style={"button_color": "#D1D1D1", "font_weight": "bold"},
        )

        refresh_btn = widgets.Button(
            description="Refresh Plot",
            button_style="",
            layout=widgets.Layout(width="120px"),
            style={"button_color": "#86D5E0", "font_weight": "bold"},
        )

        control_buttons = widgets.HBox(
            [clear_btn, refresh_btn],
            layout=widgets.Layout(justify_content="center", margin="10px 0"),
        )
        self.plot_interface_widgets = {
            "parameter_selector": parameter_selector,
            "unit_selector": unit_selector,
            "step_selector": step_selector,
            "precip_accumulation_selector": precip_accumulation_selector,
            "palette_selector": palette_selector,
            "parameter_container": parameter_container,
            "unit_container": unit_container,
            "step_container": step_container,
            "precip_accumulation_container": precip_accumulation_container,
            "palette_container": palette_container,
            "clear_btn": clear_btn,
            "refresh_btn": refresh_btn,
        }

        return widgets.VBox([controls_layout, control_buttons])

    def _get_date_time_widgets(self, config):
        """Get date/time widgets based on plot type.

        Args:
            config: config of the forecaste/analyse datetime

        Returns:
            widgets.VBox: widgets_list

        """
        widgets_list = []

        if "forecast_date" in config["mars_params"]:
            widgets_list.append(self.widgets["forecast_date"])
        elif "analysis_date" in config["mars_params"]:
            widgets_list.append(self.widgets["analysis_date"])

        if "time" in config["mars_params"]:
            widgets_list.append(self.widgets["time"])

        return widgets.VBox(widgets_list)

    def _get_cdf_specific_widgets(self):
        """Get CDF-specific widgets."""
        return widgets.VBox(
            [
                widgets.HTML(
                    "<h5 style='color: #50DEA3; margin-bottom: 5px;'>CDF Analysis Settings</h5>"
                ),
                widgets.HBox(
                    [self.widgets["days_back"], self.widgets["forecast_times"]]
                ),
            ]
        )

    def _get_steps_widgets(self):
        """Get steps configuration widgets."""
        widgets_list = [
            widgets.HTML(
                "<h5 style='color: #50DEA3; margin-bottom: 5px;'>Forecast Steps</h5>"
            ),
            widgets.HBox(
                [self.widgets["steps"], self.widgets["step_frequency"]],
                layout=widgets.Layout(align_items="center"),
            ),
        ]

        if "steps_display" in self.widgets:
            widgets_list.extend(
                [self.widgets["steps_display"], self.widgets["step_buttons"]]
            )

        return widgets.VBox(widgets_list)

    def _get_plot_specific_params(self, config):
        """Get plot-specific parameter widgets.

        Args:
            config: config of specific parameters

        Returns:
            widgets.VBox: widgets_list

        """  # noqa: D205
        widgets_list = []

        for param in config["specific_params"]:
            if param == "include_control" and param in self.widgets:
                widgets_list.append(
                    widgets.VBox(
                        [
                            widgets.HTML(
                                "<h5 style='color: #50DEA3; margin-bottom: 5px;'>Additional Options</h5>"
                            ),
                            self.widgets[param],
                        ]
                    )
                )

        return widgets.VBox(widgets_list)

    def _get_file_instruction_text(self, plot_type):
        """Get file instruction text for different plot types.

        Args:
            plot_type: type of the plot.

        """
        instructions = {
            "meteogram": "Upload your local files here",
            "stamps": "Upload your local files here",
            "plumes": "Upload your local files here",
        }
        return instructions.get(plot_type, "")
