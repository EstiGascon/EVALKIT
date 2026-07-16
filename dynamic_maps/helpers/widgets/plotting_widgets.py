"""Plotting Interface Widget Module.

This module contains interactive widgets for creating meteorological data visualizations
from downloaded weather data.
"""

import traceback
import warnings

import ipywidgets as widgets
import xarray as xr
from helpers.plotting import SurfaceVariablesMapsRender
from helpers.styling_config import StylingConfiguration
from IPython.display import clear_output, display

warnings.filterwarnings(
    "ignore", message=".*option not found for quadmesh plot with bokeh.*"
)


class PlottingWidgets:
    """Interactive widgets for creating weather data plots."""

    def __init__(self, weather_callbacks, calculator=None):
        """Initialize the plotting widget interface.

        Args:
            weather_callbacks: WeatherCallbacks instance containing downloaded data
            calculator: SurfaceVariableCalculatorUI instance containing calculated data (optional)

        """
        self.weather_callbacks = weather_callbacks
        self.calculator = calculator
        self.styling_config = StylingConfiguration()
        self.widgets = {}
        self.available_parameters = []
        self.available_steps = []
        self.calculated_parameters = []
        self.setup_widgets()

    def setup_widgets(self):
        """Initialize all plotting widgets with consistent styling."""
        self.widgets["param_selection"] = widgets.Select(
            options=[],
            value=None,
            description="Parameters:",
            disabled=False,
            rows=12,
            style={"description_width": "initial"},
            layout=widgets.Layout(width="350px", height="300px"),
        )

        self.widgets["unit"] = widgets.Dropdown(
            options=[("Auto", "auto")],
            value="auto",
            description="Unit:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
        )

        self.widgets["colorscale"] = widgets.RadioButtons(
            options=[],
            value=None,
            description="Color Palette:",
            disabled=True,
            style={"description_width": "120px"},
            layout=widgets.Layout(width="350px", display="none"),
        )

        self.widgets["opacity"] = widgets.FloatSlider(
            value=0.6,
            min=0.1,
            max=1.0,
            step=0.1,
            description="Opacity:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px", display="none"),
            readout_format=".1f",
        )

        self.widgets["plot_type"] = widgets.ToggleButtons(
            options=[
                ("Dynamic Map", "dynamic"),
                ("Static Map", "static"),
                ("Multistep Maps", "multistep"),
            ],
            value="static",
            description="",
            style={
                "description_width": "initial",
                "button_width": "100%",
                "text-align": "center",
            },
            layout=widgets.Layout(width="100%"),
        )

        self.widgets["plot_description"] = widgets.HTML(
            value="<div style='text-align: center; font-style: italic;'>Fixed map visualization for a specific time step. Perfect for presentations and reports.</div>",
            layout=widgets.Layout(width="100%", margin="5px 0px"),
        )

        self.widgets["step_selection_single"] = widgets.Dropdown(
            options=[],
            value=None,
            description="Select Step:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
        )

        self.widgets["step_selection_multi"] = widgets.SelectMultiple(
            options=[],
            value=[],
            description="Select Steps:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px", height="120px"),
        )

        self.widgets["select_all_steps"] = widgets.Button(
            description="Select All",
            button_style="",
            tooltip="Select all available steps",
            layout=widgets.Layout(width="100px"),
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )

        self.widgets["deselect_all_steps"] = widgets.Button(
            description="Clear All",
            button_style="",
            tooltip="Deselect all steps",
            layout=widgets.Layout(width="100px"),
            style={"button_color": "#0097A7", "font_weight": "bold"},
        )

        self.widgets["generate_plot"] = widgets.Button(
            description="Generate Plot",
            button_style="",
            tooltip="Generate the selected plot",
            layout=widgets.Layout(width="200px", height="40px"),
            style={"button_color": "#00BCD4", "font_weight": "bold"},
        )

        self.widgets["output"] = widgets.Output()

        self.widgets["status_display"] = widgets.HTML(
            value="", layout=widgets.Layout(width="100%", margin="10px 0px")
        )

        self.setup_observers()
        self.refresh_data_info()

    def setup_observers(self):
        """Set up widget observers for dynamic updates."""

        def on_plot_type_change(change):
            plot_type = change["new"]

            if plot_type == "dynamic":
                centered_description = "<div style='text-align: center; font-style: italic;'>Dynamic map for a specific time step. Great for analyzing weather patterns.</div>"
                self.widgets["opacity"].layout.display = "block"
            elif plot_type == "static":
                centered_description = "<div style='text-align: center; font-style: italic;'>Fixed map visualization for a specific time step. Perfect for presentations and reports.</div>"
                self.widgets["opacity"].layout.display = "none"
            elif plot_type == "multistep":
                centered_description = "<div style='text-align: center; font-style: italic;'>Multiple static maps for comparison. Ideal for analyzing temporal variation.</div>"
                self.widgets["opacity"].layout.display = "block"

            self.widgets["plot_description"].value = centered_description
            self.update_step_selection_visibility()

        self.widgets["plot_type"].observe(on_plot_type_change, names="value")

        def on_parameter_change(change):  # noqa: ARG001
            self.update_unit_and_colorscale_options()
            self.update_plot_type_availability()

        self.widgets["param_selection"].observe(on_parameter_change, names="value")

        def select_all_steps(button):  # noqa: ARG001
            all_values = [
                option[1] for option in self.widgets["step_selection_multi"].options
            ]
            self.widgets["step_selection_multi"].value = all_values

        def deselect_all_steps(button):  # noqa: ARG001
            self.widgets["step_selection_multi"].value = []

        self.widgets["select_all_steps"].on_click(select_all_steps)
        self.widgets["deselect_all_steps"].on_click(deselect_all_steps)

        self.widgets["generate_plot"].on_click(self.on_generate_plot)

    def update_unit_and_colorscale_options(self):
        """Update unit and colorscale options based on selected parameter."""
        selected_param = self.widgets["param_selection"].value
        if not selected_param:
            self.widgets["colorscale"].layout.display = "none"
            self.widgets["colorscale"].disabled = True
            return

        param_config = self.styling_config.choose_color_palette_and_levels(
            selected_param
        )
        param_type = param_config.get("param_type")

        if param_type == "temperature":
            unit_options = [("Celsius (°C)", "celsius"), ("Kelvin (K)", "kelvin")]
            self.widgets["colorscale"].layout.display = "none"
            self.widgets["colorscale"].disabled = True
        elif param_type in ["precipitation", "accumulated_precipitation"]:
            unit_options = [("Millimeters (mm)", "mm"), ("Meters (m)", "m")]
            colorscale_options = [
                ("Basic Palette (0.5mm-500mm)", 1),
                ("Extended Palette (0.5mm-1000mm)", 2),
                ("High Intensity Palette (10mm-700mm)", 3),
            ]
            self.widgets["colorscale"].options = colorscale_options
            self.widgets["colorscale"].value = 2
            self.widgets["colorscale"].disabled = False
            self.widgets["colorscale"].layout.display = "block"
        elif param_type in ["wind_gust", "wind_speed", "wind_component"]:
            unit_options = [("m/s", "m/s")]
            self.widgets["colorscale"].layout.display = "none"
            self.widgets["colorscale"].disabled = True
        else:
            unit_options = [("Default", "default")]
            self.widgets["colorscale"].layout.display = "none"
            self.widgets["colorscale"].disabled = True

        self.widgets["unit"].options = unit_options
        if unit_options:
            self.widgets["unit"].value = unit_options[0][1]

        if param_type not in ["precipitation", "accumulated_precipitation"]:
            self.widgets["colorscale"].options = [("Default", 1)]
            self.widgets["colorscale"].value = 1

    def update_plot_type_availability(self):
        """Update plot type availability based on selected parameter."""
        selected_param = self.widgets["param_selection"].value
        if not selected_param:
            return

        is_calculated = selected_param in self.calculated_parameters

        if is_calculated:
            if selected_param == "10ff":
                self.widgets["plot_type"].options = [
                    ("Dynamic Map", "dynamic"),
                    ("Multistep Maps", "multistep"),
                ]

                if self.widgets["plot_type"].value == "static":
                    self.widgets["plot_type"].value = "dynamic"

                self.widgets["step_selection_single"].disabled = False
                self.widgets["step_selection_multi"].disabled = False
                self.widgets["select_all_steps"].disabled = False
                self.widgets["deselect_all_steps"].disabled = False

            else:
                self.widgets["plot_type"].options = [
                    ("Dynamic Map", "dynamic"),
                ]

                if self.widgets["plot_type"].value != "dynamic":
                    self.widgets["plot_type"].value = "dynamic"

                self.widgets["step_selection_single"].disabled = True
                self.widgets["step_selection_multi"].disabled = True
                self.widgets["select_all_steps"].disabled = True
                self.widgets["deselect_all_steps"].disabled = True

                self.widgets[
                    "plot_description"
                ].value = "<div style='text-align: center; font-style: italic;'>Dynamic map for calculated parameter. Step selection is disabled for calculated variables.</div>"
        else:
            self.widgets["plot_type"].options = [
                ("Dynamic Map", "dynamic"),
                ("Static Map", "static"),
                ("Multistep Maps", "multistep"),
            ]

            self.widgets["step_selection_single"].disabled = False
            self.widgets["step_selection_multi"].disabled = False
            self.widgets["select_all_steps"].disabled = False
            self.widgets["deselect_all_steps"].disabled = False

        self.update_step_selection_visibility()
        self.update_opacity_visibility()

    def update_opacity_visibility(self):
        """Update opacity slider visibility based on plot type."""
        plot_type = self.widgets["plot_type"].value

        if plot_type in ["dynamic", "multistep"]:
            self.widgets["opacity"].layout.display = "block"
        else:
            self.widgets["opacity"].layout.display = "none"

    def refresh_data_info(self):  # noqa: PLR0912, PLR0915
        """Refresh available parameters and steps from the weather data and calculated data."""
        try:
            dataset = self.weather_callbacks.get_dataset()
            calculated_data = (
                self.calculator.get_calculated_data() if self.calculator else None
            )

            if not dataset and not calculated_data:
                self.widgets["status_display"].value = """
                    <div style="background-color: #ffe8e8; padding: 10px; border-radius: 5px; border-left: 4px solid #00BCD4;">
                        <b>No data available!</b><br>
                        Please download weather data first using the data acquisition interface.
                    </div>
                """
                self.widgets["param_selection"].options = []
                self.widgets["step_selection_single"].options = []
                self.widgets["step_selection_multi"].options = []
                self.widgets["generate_plot"].disabled = True
                return

            all_available_params = []
            available_steps = []

            if dataset:
                if hasattr(dataset, "to_xarray"):
                    xr_ds = dataset.to_xarray()
                    original_params = list(xr_ds.data_vars.keys())

                    if "step" in xr_ds.coords:
                        steps = []
                        for step in xr_ds.step.values:
                            try:
                                if hasattr(step, "astype"):
                                    hours = int(
                                        step.astype("timedelta64[h]").astype(int)
                                    )
                                    steps.append(hours)
                                else:
                                    step_str = (
                                        str(step)
                                        .replace("0 days ", "")
                                        .replace(":00:00", "")
                                    )
                                    if step_str.isdigit():
                                        steps.append(int(step_str))
                            except (ValueError, AttributeError):
                                continue
                        available_steps = sorted(steps) if steps else [0]
                    else:
                        available_steps = [0]
                else:
                    original_params = []
                    for field in dataset:
                        param = field.metadata("param")
                        if param not in original_params:
                            original_params.append(param)

                        step = field.metadata("step")
                        if step not in available_steps:
                            available_steps.append(step)

                    available_steps = (
                        sorted(available_steps) if available_steps else [0]
                    )

                all_available_params.extend(original_params)

            calculated_params = []
            if calculated_data is not None:
                all_calculated_data = (
                    self.calculator.get_all_calculated_data()
                    if hasattr(self.calculator, "get_all_calculated_data")
                    else {}
                )

                if all_calculated_data:
                    for param_name, data in all_calculated_data.items():
                        calculated_params.append(param_name)

                        if (
                            isinstance(data, xr.Dataset | xr.DataArray)
                            and "step" in data.coords
                        ):
                            calc_steps = []
                            for step in data.step.values:
                                try:
                                    if hasattr(step, "astype"):
                                        hours = int(
                                            step.astype("timedelta64[h]").astype(int)
                                        )
                                        calc_steps.append(hours)
                                    else:
                                        step_str = (
                                            str(step)
                                            .replace("0 days ", "")
                                            .replace(":00:00", "")
                                        )
                                        if step_str.isdigit():
                                            calc_steps.append(int(step_str))
                                except (ValueError, AttributeError):
                                    continue
                            if calc_steps:
                                available_steps.extend(calc_steps)
                                available_steps = sorted(set(available_steps))
                elif isinstance(calculated_data, xr.Dataset):
                    calculated_params = list(calculated_data.data_vars.keys())
                    if "step" in calculated_data.coords:
                        calc_steps = []
                        for step in calculated_data.step.values:
                            try:
                                if hasattr(step, "astype"):
                                    hours = int(
                                        step.astype("timedelta64[h]").astype(int)
                                    )
                                    calc_steps.append(hours)
                                else:
                                    step_str = (
                                        str(step)
                                        .replace("0 days ", "")
                                        .replace(":00:00", "")
                                    )
                                    if step_str.isdigit():
                                        calc_steps.append(int(step_str))
                            except (ValueError, AttributeError):
                                continue
                        if calc_steps:
                            available_steps.extend(calc_steps)
                            available_steps = sorted(set(available_steps))
                elif isinstance(calculated_data, xr.DataArray):
                    calculated_params = [calculated_data.name or "calculated_variable"]
                    if "step" in calculated_data.coords:
                        calc_steps = []
                        for step in calculated_data.step.values:
                            try:
                                if hasattr(step, "astype"):
                                    hours = int(
                                        step.astype("timedelta64[h]").astype(int)
                                    )
                                    calc_steps.append(hours)
                                else:
                                    step_str = (
                                        str(step)
                                        .replace("0 days ", "")
                                        .replace(":00:00", "")
                                    )
                                    if step_str.isdigit():
                                        calc_steps.append(int(step_str))
                            except (ValueError, AttributeError):
                                continue
                        if calc_steps:
                            available_steps.extend(calc_steps)
                            available_steps = sorted(set(available_steps))

                all_available_params.extend(calculated_params)

            self.calculated_parameters = calculated_params

            param_options = []
            for param in all_available_params:
                param_config = self.styling_config.choose_color_palette_and_levels(
                    param
                )
                display_name = param_config.get("title", param)

                if param in calculated_params:
                    display_name = f"{display_name} (Calculated)"
                else:
                    display_name = f"{display_name} (Original)"

                param_options.append((display_name, param))

            current_param = self.widgets["param_selection"].value
            self.widgets["param_selection"].options = param_options
            if param_options:
                if current_param and current_param in [opt[1] for opt in param_options]:
                    self.widgets["param_selection"].value = current_param
                else:
                    tp_found = False
                    for _option_text, option_value in param_options:
                        if option_value == "tp":
                            self.widgets["param_selection"].value = "tp"
                            tp_found = True
                            break
                    if not tp_found:
                        self.widgets["param_selection"].value = param_options[0][1]
                self.update_unit_and_colorscale_options()
                self.update_plot_type_availability()

            step_options = [(f"Step {step}h", step) for step in available_steps]
            self.widgets["step_selection_single"].options = step_options
            self.widgets["step_selection_multi"].options = step_options

            if step_options:
                self.widgets["step_selection_single"].value = step_options[0][1]
                self.widgets["step_selection_multi"].value = [step_options[0][1]]

            self.available_parameters = all_available_params
            self.available_steps = available_steps

            calc_info = ""
            if calculated_data is not None:
                if isinstance(calculated_data, xr.Dataset):
                    calc_info = f"<br>Calculated variables: {len(calculated_params)}"
                elif isinstance(calculated_data, xr.DataArray):
                    calc_info = "<br>Calculated variable: 1"

            self.widgets["status_display"].value = f"""
                <div style="background-color: #E0F7FA; padding: 10px; border-radius: 5px; border-left: 4px solid #00BCD4;">
                    <b>Data loaded successfully!</b><br>
                    Total parameters: {len(all_available_params)} (Original: {len(all_available_params) - len(calculated_params)}, Calculated: {len(calculated_params)}){calc_info}<br>
                    Available steps: {len(available_steps)} ({min(available_steps)}h to {max(available_steps)}h)
                </div>
            """

            self.widgets["generate_plot"].disabled = False
            self.update_step_selection_visibility()
            self.update_opacity_visibility()

        except Exception as e:
            self.widgets["status_display"].value = f"""
                <div style="background-color: #ffe8e8; padding: 10px; border-radius: 5px; border-left: 4px solid #00BCD4;">
                    <b>Error loading data:</b> {str(e)}<br>
                    Please check your data and try again.
                </div>
            """
            self.widgets["generate_plot"].disabled = True

    def update_step_selection_visibility(self):
        """Update step selection widget visibility based on plot type."""
        plot_type = self.widgets["plot_type"].value
        selected_param = self.widgets["param_selection"].value
        is_calculated = (
            selected_param in self.calculated_parameters if selected_param else False
        )

        if plot_type in ["static", "dynamic"]:
            self.widgets["step_selection_single"].layout.display = "block"
            self.widgets["step_selection_multi"].layout.display = "none"
            self.widgets["select_all_steps"].layout.display = "none"
            self.widgets["deselect_all_steps"].layout.display = "none"
        else:
            self.widgets["step_selection_single"].layout.display = "none"
            self.widgets["step_selection_multi"].layout.display = "block"
            self.widgets["select_all_steps"].layout.display = "block"
            self.widgets["deselect_all_steps"].layout.display = "block"

        if is_calculated and selected_param != "10ff":
            self.widgets["step_selection_single"].layout.display = "none"
            self.widgets["step_selection_multi"].layout.display = "none"
            self.widgets["select_all_steps"].layout.display = "none"
            self.widgets["deselect_all_steps"].layout.display = "none"

    def create_actual_plot(  # noqa: D102, PLR0913
        self, parameter, steps, plot_type, unit, palette_color, opacity=0.6
    ):
        dataset = self.weather_callbacks.get_dataset()
        calculated_data = (
            self.calculator.get_calculated_data() if self.calculator else None
        )
        plotter = SurfaceVariablesMapsRender()
        calculated_params = self.calculated_parameters

        if parameter in calculated_params:
            if hasattr(self.calculator, "get_all_calculated_data"):
                all_calculated_data = self.calculator.get_all_calculated_data()
                data_to_plot = all_calculated_data.get(parameter, calculated_data)
            else:
                all_calculated_data = (
                    {parameter: calculated_data} if calculated_data else None
                )
                data_to_plot = calculated_data
        else:
            all_calculated_data = None
            data_to_plot = dataset

        try:
            if plot_type == "static":
                fig = plotter.plot_static_map(
                    data=data_to_plot,
                    parameter_name=parameter,
                    units=unit,
                    step=steps[0] if steps else 0,
                    **(
                        {"opacity": opacity}
                        if "opacity" in plotter.plot_static_map.__code__.co_varnames
                        else {}
                    ),
                )

            elif plot_type == "dynamic":
                calc_data_to_pass = (
                    all_calculated_data if parameter in calculated_params else None
                )
                step_to_pass = None
                if parameter not in calculated_params or parameter == "10ff":
                    step_to_pass = steps[0] if steps else 0

                fig = plotter.plot_dynamic_maps(
                    data=data_to_plot,
                    parameter_name=parameter,
                    unit=unit,
                    palette_color=palette_color,
                    step=step_to_pass,
                    opacity=opacity,
                    calculated_data=calc_data_to_pass,
                )

            elif plot_type == "multistep":
                fig = plotter.plot_dynamic_multistep_maps(
                    data=data_to_plot,
                    parameter_name=parameter,
                    steps=steps,
                    unit=unit,
                    palette_color=palette_color,
                    opacity=opacity,
                )
            else:
                raise ValueError(f"Unknown plot type: {plot_type}")

            return fig

        except Exception:
            raise

    def on_generate_plot(self, button):
        """Update generate plot handler with proper error handling."""
        with self.widgets["output"]:
            clear_output()

            selected_param = self.widgets["param_selection"].value
            plot_type = self.widgets["plot_type"].value
            unit = self.widgets["unit"].value
            palette_color = self.widgets["colorscale"].value
            opacity = self.widgets["opacity"].value

            if not selected_param:
                print("Please select a parameter to plot.")
                return

            is_calculated = selected_param in self.calculated_parameters

            if is_calculated and selected_param != "10ff":
                selected_steps = []
            elif plot_type in ["static", "dynamic"]:
                selected_steps = [self.widgets["step_selection_single"].value]
            else:
                selected_steps = list(self.widgets["step_selection_multi"].value)

            if not is_calculated or selected_param == "10ff":
                if not selected_steps or (
                    len(selected_steps) == 1 and selected_steps[0] is None
                ):
                    print("Please select at least one step to plot.")
                    return

            try:
                fig = self.create_actual_plot(
                    parameter=selected_param,
                    steps=selected_steps,
                    plot_type=plot_type,
                    unit=unit,
                    palette_color=palette_color,
                    opacity=opacity,
                )

                if fig is not None:
                    display(fig)

            except Exception as e:
                print(f"Critical plotting error: {str(e)}")
                traceback.print_exc()

    def display_interface(self):
        """Display the plotting interface."""
        header = widgets.HTML(
            "<h2 style='color: #00BCD4;'>Plotting Interface</h2>"
            "<p>Create visualizations from your meteorological data</p>"
        )

        refresh_btn = widgets.Button(
            description="Refresh Data",
            button_style="",
            tooltip="Refresh available parameters and steps",
            layout=widgets.Layout(width="150px"),
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )
        refresh_btn.on_click(lambda x: self.refresh_data_info())

        param_box = widgets.VBox(
            [
                widgets.HTML("<h3 style='color: #50DEA3;'>Parameter Selection</h3>"),
                self.widgets["param_selection"],
            ],
            layout=widgets.Layout(width="35%", margin="0 10px 0 0"),
        )

        config_box = widgets.VBox(
            [
                widgets.HTML("<h3 style='color: #50DEA3;'>Plot Configuration</h3>"),
                self.widgets["unit"],
                self.widgets["colorscale"],
                self.widgets["opacity"],
            ],
            layout=widgets.Layout(width="30%", margin="0 10px"),
        )

        step_buttons = widgets.HBox(
            [self.widgets["select_all_steps"], self.widgets["deselect_all_steps"]],
            layout=widgets.Layout(justify_content="center"),
        )

        step_box = widgets.VBox(
            [
                widgets.HTML("<h3 style='color: #50DEA3;'>Step Selection</h3>"),
                self.widgets["step_selection_single"],
                self.widgets["step_selection_multi"],
                step_buttons,
            ],
            layout=widgets.Layout(width="30%", margin="0 0 0 10px"),
        )

        first_row = widgets.HBox(
            [param_box, config_box, step_box],
            layout=widgets.Layout(
                width="100%", margin="10px 0", justify_content="space-between"
            ),
        )

        plot_type_box = widgets.VBox(
            [
                widgets.HTML(
                    "<h3 style='color: #50DEA3; text-align: center;'>Plot Type Selection</h3>"
                ),
                widgets.HBox(
                    [self.widgets["plot_type"]],
                    layout=widgets.Layout(justify_content="center", width="100%"),
                ),
                self.widgets["plot_description"],
            ],
            layout=widgets.Layout(width="100%", margin="10px 0"),
        )

        generate_section = widgets.VBox(
            [
                widgets.HBox(
                    [self.widgets["generate_plot"]],
                    layout=widgets.Layout(justify_content="center"),
                ),
                self.widgets["status_display"],
            ],
            layout=widgets.Layout(width="100%", margin="10px 0"),
        )

        interface = widgets.VBox(
            [
                header,
                refresh_btn,
                first_row,
                plot_type_box,
                generate_section,
                self.widgets["output"],
            ],
            layout=widgets.Layout(width="100%"),
        )

        interface = widgets.Accordion(
            children=[interface],
            titles=["Interactive Plotting"],
        )
        interface.selected_index = 0

        display(interface)

    def set_calculator(self, calculator):
        """Set or update the calculator instance.

        Args:
            calculator: SurfaceVariableCalculatorUI instance

        """
        self.calculator = calculator
        self.refresh_data_info()


def create_plotting_interface(weather_callbacks, calculator=None):
    """Create and display the plotting interface widget.

    Args:
        weather_callbacks: WeatherCallbacks instance containing downloaded data
        calculator: SurfaceVariableCalculatorUI instance containing calculated data (optional)

    Returns:
        PlottingWidgets instance

    """
    plotting_widget = PlottingWidgets(weather_callbacks, calculator)
    plotting_widget.display_interface()
    return plotting_widget
