"""Surface Variable Calculator Widget Module.

This module contains interactive widgets for calculating surface meteorological variables
from downloaded weather data.
"""

import traceback

import ipywidgets as widgets
import xarray as xr
from helpers.common_calculations import WeatherDataAggregator
from helpers.meteorological_calculations import (
    calculate_accumulated_precipitation,
    calculate_wind_speed,
)
from IPython.display import clear_output, display


class SurfaceVariableCalculatorUI:
    """Interactive widget for calculating surface meteorological variables."""

    def __init__(self, weather_callbacks):
        """Initialize the calculator widget.

        Args:
            weather_callbacks: WeatherCallbacks instance containing downloaded data

        """
        self.weather_callbacks = weather_callbacks
        self.widgets = {}
        self.calculated_data = None
        self.all_calculated_data = {}
        self.aggregator = WeatherDataAggregator()
        self.setup_widgets()

    def setup_widgets(self):
        """Initialize all calculator widgets with consistent styling."""
        self.widgets["calc_type"] = widgets.Dropdown(
            options=[
                ("Select calculation type...", ""),
                ("Accumulated Precipitation", "precipitation"),
                ("Wind Speed", "wind_speed"),
                ("Extremes (Max/Min)", "extremes"),
            ],
            value="",
            description="Calculation:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

        self.widgets["info_display"] = widgets.HTML(
            value="<p>Please select a calculation type above.</p>",
            layout=widgets.Layout(width="600px"),
        )

        self.widgets["param_selection"] = widgets.Dropdown(
            options=[],
            value=None,
            description="Parameter:",
            disabled=True,
            style={"description_width": "initial"},
            layout=widgets.Layout(width="400px", display="none"),
        )

        self.widgets["operation"] = widgets.Dropdown(
            options=[("Maximum", "max"), ("Minimum", "min")],
            value="max",
            description="Operation:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px", display="none"),
        )

        self.widgets["calculate_btn"] = widgets.Button(
            description="Calculate",
            button_style="",
            tooltip="Click to perform calculation",
            disabled=True,
            layout=widgets.Layout(width="150px"),
            style={"button_color": "#00BCD4", "font_weight": "bold"},
        )

        self.widgets["download_btn"] = widgets.Button(
            description="Download",
            button_style="",
            tooltip="Click to download calculated data",
            disabled=True,
            layout=widgets.Layout(width="150px", display="none"),
            style={"button_color": "#50DEA3", "font_weight": "bold"},
        )

        self.widgets["show_calculated_btn"] = widgets.Button(
            description="Show All Calculated",
            button_style="",
            tooltip="Show all calculated parameters",
            disabled=True,
            layout=widgets.Layout(width="180px", display="none"),
            style={"button_color": "#4DD0E1", "font_weight": "bold"},
        )

        self.widgets["clear_all_btn"] = widgets.Button(
            description="Clear All",
            button_style="",
            tooltip="Clear all calculated parameters",
            disabled=True,
            layout=widgets.Layout(width="120px", display="none"),
            style={"button_color": "#5A5A5A", "font_weight": "bold"},
        )

        self.widgets["param_box_title"] = widgets.HTML(
            "<h4>Parameter Selection</h4>", layout=widgets.Layout(display="none")
        )

        self.widgets["output"] = widgets.Output()
        self.setup_observers()

    def setup_observers(self):
        """Setting-up widget observers and callbacks."""
        self.widgets["calc_type"].observe(self.on_calc_type_change, names="value")

        self.widgets["calculate_btn"].on_click(self.on_calculate_click)
        self.widgets["download_btn"].on_click(self.on_download_click)
        self.widgets["show_calculated_btn"].on_click(self.on_show_calculated_click)
        self.widgets["clear_all_btn"].on_click(self.on_clear_all_click)

    def on_calc_type_change(self, change):
        """Handle calculation type selection change ."""
        calc_type = change["new"]

        with self.widgets["output"]:
            clear_output()

        self.widgets["calculate_btn"].disabled = True
        self.widgets["download_btn"].layout.display = "none"
        self.widgets["download_btn"].disabled = True

        widgets_to_hide = ["param_selection", "operation", "param_box_title"]
        for widget_name in widgets_to_hide:
            if widget_name in self.widgets:
                self.widgets[widget_name].layout.display = "none"

        if not calc_type:
            self.widgets[
                "info_display"
            ].value = "<p>Please select a calculation type above.</p>"
            return

        if not self.weather_callbacks.get_dataset():
            self.widgets["info_display"].value = """
            <div style="background-color: #FFEBEE; padding: 10px; border-radius: 5px; border-left: 4px solid #F44336;">
                <p><b>No data available!</b><br>
                Please download data first using the data acquisition interface.</p>
            </div>
            """
            return

        dataset = self.weather_callbacks.get_dataset()

        if calc_type == "precipitation":
            self.setup_precipitation_calculation(dataset)
        elif calc_type == "wind_speed":
            self.setup_wind_speed_calculation(dataset)
        elif calc_type == "extremes":
            self.setup_extremes_calculation(dataset)

    def setup_precipitation_calculation(self, dataset):  # noqa: PLR0912, PLR0915
        """Setting-up precipitation calculation interface with auto-calculation for all available types."""
        try:
            if hasattr(dataset, "to_xarray"):
                xr_ds = dataset.to_xarray()
                available_vars = list(xr_ds.data_vars.keys())

                if "step" in xr_ds.coords:
                    steps = []
                    for step in xr_ds.step.values:
                        try:
                            if hasattr(step, "astype"):
                                hours = int(step.astype("timedelta64[h]").astype(int))
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

                    if steps:
                        steps = sorted(steps)
                        first_step = min(steps)
                        last_step = max(steps)
                    else:
                        first_step, last_step = "Unknown", "Unknown"
                else:
                    first_step, last_step = "Unknown", "Unknown"
            else:
                available_vars = []
                for field in dataset:
                    param = field.metadata("param")
                    if param not in available_vars:
                        available_vars.append(param)
                first_step, last_step = "Unknown", "Unknown"

            precip_types = []
            if "tp" in available_vars:
                precip_types.append(("Total Precipitation", "tp"))
            if "cp" in available_vars:
                precip_types.append(("Convective Precipitation", "cp"))
            if "lsp" in available_vars:
                precip_types.append(("Large-scale Precipitation", "lsp"))

            if precip_types:
                existing_info = ""
                existing_calcs = []
                for _precip_type, param_code in precip_types:
                    calc_key = f"acc_{param_code}"
                    if calc_key in self.all_calculated_data:
                        existing_calcs.append(calc_key)

                if existing_calcs:
                    existing_info = f"<p><b>Note:</b> {', '.join(existing_calcs)} already calculated. This will update existing calculations.</p>"

                precip_list = ", ".join(
                    [f"{name} ({code})" for name, code in precip_types]
                )

                self.widgets["info_display"].value = f"""
                <div style="background-color: #E8F5E8; padding: 10px; border-radius: 5px; border-left: 4px solid #50DEA3;">
                    <h4 style="color: #50DEA3; margin-top: 0;">Accumulated Precipitation Calculation</h4>
                    <p><b>Available precipitation types:</b> {precip_list}</p>
                    <p><b>Calculation Range:</b> From step {first_step}h to step {last_step}h</p>
                    <p><b>Description:</b> This will calculate accumulated precipitation for <strong>all available types</strong> automatically.</p>
                    <p><b>Result:</b> Accumulated precipitation in meters (m) for each type</p>
                    <p><b>Auto-calculation:</b> Will create acc_tp, acc_cp, and/or acc_lsp as available</p>
                    {existing_info}
                </div>
                """
                self.widgets["calculate_btn"].disabled = False
            else:
                self.widgets["info_display"].value = f"""
                <div style="background-color: #FFEBEE; padding: 10px; border-radius: 5px; border-left: 4px solid #F44336;">
                    <h4 style="color: #F44336; margin-top: 0;">Accumulated Precipitation Calculation</h4>
                    <p><b>Missing required parameters:</b> No precipitation parameters found</p>
                    <p><b>Available parameters:</b> {", ".join(available_vars)}</p>
                    <p><b>Required:</b> At least one of tp (Total), cp (Convective), or lsp (Large-scale) precipitation</p>
                    <p>Please download data that includes precipitation parameters.</p>
                </div>
                """

        except Exception as e:
            self.widgets["info_display"].value = f"""
            <div style="background-color: #FFEBEE; padding: 10px; border-radius: 5px; border-left: 4px solid #F44336;">
                <h4 style="color: #F44336; margin-top: 0;">Error</h4>
                <p><b>Unable to analyze precipitation data:</b> {str(e)}</p>
            </div>
            """

    def setup_wind_speed_calculation(self, dataset):
        """Setting-up wind speed calculation interface."""
        try:
            if hasattr(dataset, "to_xarray"):
                xr_ds = dataset.to_xarray()
                available_vars = list(xr_ds.data_vars.keys())
            else:
                available_vars = []
                for field in dataset:
                    param = field.metadata("param")
                    if param not in available_vars:
                        available_vars.append(param)

            has_u_wind = any(var in ["10u", "u10"] for var in available_vars)
            has_v_wind = any(var in ["10v", "v10"] for var in available_vars)

            if has_u_wind and has_v_wind:
                existing_info = ""
                if "10ff" in self.all_calculated_data:
                    existing_info = "<p><b>Note:</b> Wind speed already calculated. This will update the existing calculation.</p>"

                self.widgets["info_display"].value = f"""
                <div style="background-color: #E3F2FD; padding: 10px; border-radius: 5px; border-left: 4px solid #2196F3;">
                    <h4 style="color: #2196F3; margin-top: 0;">Wind Speed Calculation</h4>
                    <p><b>U and V wind components detected!</b></p>
                    <p><b>Description:</b> This will calculate wind speed from 10m U and V wind components.</p>
                    <p><b>Formula:</b> Wind Speed = √(U² + V²)</p>
                    <p><b>Result:</b> 10m wind speed in m/s</p>
                    {existing_info}
                </div>
                """
                self.widgets["calculate_btn"].disabled = False
            else:
                missing_components = []
                if not has_u_wind:
                    missing_components.append("10u (U-component)")
                if not has_v_wind:
                    missing_components.append("10v (V-component)")

                self.widgets["info_display"].value = f"""
                <div style="background-color: #FFEBEE; padding: 10px; border-radius: 5px; border-left: 4px solid #F44336;">
                    <h4 style="color: #F44336; margin-top: 0;">Wind Speed Calculation</h4>
                    <p><b>Missing required components:</b> {", ".join(missing_components)}</p>
                    <p><b>Available parameters:</b> {", ".join(available_vars)}</p>
                    <p>Please download data that includes both U and V wind components (10u and 10v).</p>
                </div>
                """

        except Exception as e:
            self.widgets["info_display"].value = f"""
            <div style="background-color: #FFEBEE; padding: 10px; border-radius: 5px; border-left: 4px solid #F44336;">
                <h4 style="color: #F44336; margin-top: 0;">Error</h4>
                <p><b>Unable to analyze wind data:</b> {str(e)}</p>
            </div>
            """

    def setup_extremes_calculation(self, dataset):
        """Setting-up extremes calculation interface."""
        try:
            allowed_params = ["mn2t", "mx2t", "10fg"]

            if hasattr(dataset, "to_xarray"):
                xr_ds = dataset.to_xarray()
                available_params = list(xr_ds.data_vars.keys())
            else:
                available_params = []
                for field in dataset:
                    param = field.metadata("param")
                    if param not in available_params:
                        available_params.append(param)

            filtered_params = [
                param for param in allowed_params if param in available_params
            ]

            if "10ff" in self.all_calculated_data:
                filtered_params.append("10ff")

            if filtered_params:
                param_options = [(param, param) for param in filtered_params]
                self.widgets["param_selection"].options = param_options
                self.widgets["param_selection"].value = filtered_params[0]
                self.widgets["param_selection"].disabled = False

                self.widgets["param_selection"].layout.display = "block"
                self.widgets["operation"].layout.display = "block"
                self.widgets["param_box_title"].layout.display = "block"

                available_text = ", ".join(filtered_params)
                note_text = ""
                if "10ff" in filtered_params:
                    note_text = "<p><b>Note:</b> Calculated wind speed (10ff) is available for extremes calculation.</p>"

                self.widgets["info_display"].value = f"""
                <div style="background-color: #FFF8E1; padding: 10px; border-radius: 5px; border-left: 4px solid #FF9800;">
                    <h4 style="color: #FF9800; margin-top: 0;">Extremes Calculation (Max/Min)</h4>
                    <p><b>Available parameters for extremes:</b> {available_text}</p>
                    <p><b>Description:</b> This will calculate the temporal maximum or minimum value at each grid point across all forecast steps.</p>
                    {note_text}
                    <p><b>Instructions:</b></p>
                    <ol>
                        <li>Select <b>one</b> parameter below</li>
                        <li>Choose operation (Maximum or Minimum)</li>
                        <li>Click Calculate</li>
                    </ol>
                </div>
                """

                self.widgets["calculate_btn"].disabled = False
            else:
                self.widgets["info_display"].value = f"""
                <div style="background-color: #FFEBEE; padding: 10px; border-radius: 5px; border-left: 4px solid #F44336;">
                    <h4 style="color: #F44336; margin-top: 0;">Extremes Calculation (Max/Min)</h4>
                    <p><b>No suitable parameters found for extremes calculation.</b></p>
                    <p><b>Required parameters:</b> mn2t, mx2t, 10fg (or calculated 10ff)</p>
                    <p><b>Available in dataset:</b> {", ".join(available_params) if available_params else "None"}</p>
                    <p>Please download data that includes one of the required parameters, or calculate wind speed (10ff) first.</p>
                </div>
                """

        except Exception as e:
            self.widgets["info_display"].value = f"""
            <div style="background-color: #FFEBEE; padding: 10px; border-radius: 5px; border-left: 4px solid #F44336;">
                <h4 style="color: #F44336; margin-top: 0;">Error</h4>
                <p><b>Unable to analyze dataset:</b> {str(e)}</p>
            </div>
            """

    def print_styled_message(self, message, message_type="info"):
        """Print a styled message with consistent color scheme.

        Args:
            message: The message text to display
            message_type: Type of message - 'info', 'success', 'warning', 'error', 'progress'

        """
        color_schemes = {
            "info": {"bg": "#E0F7FA", "border": "#00BCD4"},
            "success": {"bg": "#E8F5E8", "border": "#50DEA3"},
            "warning": {"bg": "#FFF8E1", "border": "#FF9800"},
            "error": {"bg": "#FFEBEE", "border": "#F44336"},
            "progress": {"bg": "#E3F2FD", "border": "#2196F3"},
        }

        scheme = color_schemes.get(message_type, color_schemes["info"])

        styled_html = f"""
        <div style="background-color: {scheme["bg"]}; padding: 10px; border-radius: 5px;
                    margin: 5px 0; border-left: 4px solid {scheme["border"]};
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
            {message}
        </div>
        """
        display(widgets.HTML(styled_html))

    def on_calculate_click(self, button):  # noqa: PLR0912, PLR0915
        """Handle calculate button click with auto-calculation for all precipitation types."""
        with self.widgets["output"]:
            clear_output()

            calc_type = self.widgets["calc_type"].value
            dataset = self.weather_callbacks.get_dataset()

            if not dataset:
                self.print_styled_message(
                    "No dataset available for calculation!", "error"
                )
                return

            self.print_styled_message("Calculation in progress...", "progress")

            try:
                if calc_type == "precipitation":
                    if hasattr(dataset, "to_xarray"):
                        xr_ds = dataset.to_xarray()
                        available_vars = list(xr_ds.data_vars.keys())
                    else:
                        available_vars = []
                        for field in dataset:
                            param = field.metadata("param")
                            if param not in available_vars:
                                available_vars.append(param)

                    precip_types = []
                    if "tp" in available_vars:
                        precip_types.append("tp")
                    if "cp" in available_vars:
                        precip_types.append("cp")
                    if "lsp" in available_vars:
                        precip_types.append("lsp")

                    calculated_count = 0
                    calculated_names = []

                    for precip_type in precip_types:
                        try:
                            precip_data = (
                                dataset.sel(param=precip_type)
                                if hasattr(dataset, "sel")
                                else [
                                    field
                                    for field in dataset
                                    if field.metadata("param") == precip_type
                                ]
                            )

                            calculated_result = calculate_accumulated_precipitation(
                                precip_data, param_type=precip_type
                            )
                            param_key = f"acc_{precip_type}"
                            self.all_calculated_data[param_key] = calculated_result

                            calculated_count += 1
                            precip_names = {
                                "tp": "Total",
                                "cp": "Convective",
                                "lsp": "Large-scale",
                            }
                            calculated_names.append(
                                f"acc_{precip_type} ({precip_names[precip_type]})"
                            )

                            self.calculated_data = calculated_result

                        except Exception as e:
                            print(f"Warning: Failed to calculate {precip_type}: {e}")

                    if calculated_count > 0:
                        var_name = f"Accumulated Precipitation ({calculated_count} types: {', '.join(calculated_names)})"
                    else:
                        raise RuntimeError(
                            "Failed to calculate any precipitation types"
                        )

                elif calc_type == "wind_speed":
                    u_wind = (
                        dataset.sel(param=["10u", "u10"])
                        if hasattr(dataset, "sel")
                        else [
                            field
                            for field in dataset
                            if field.metadata("param") in ["10u", "u10"]
                        ]
                    )
                    v_wind = (
                        dataset.sel(param=["10v", "v10"])
                        if hasattr(dataset, "sel")
                        else [
                            field
                            for field in dataset
                            if field.metadata("param") in ["10v", "v10"]
                        ]
                    )
                    calculated_result = calculate_wind_speed(u_wind, v_wind)
                    param_key = "10ff"
                    self.all_calculated_data[param_key] = calculated_result
                    self.calculated_data = calculated_result
                    var_name = "Wind Speed"

                elif calc_type == "extremes":
                    selected_param = self.widgets["param_selection"].value

                    if not selected_param:
                        clear_output()
                        self.print_styled_message(
                            "Please select a parameter!", "warning"
                        )
                        return

                    operation = self.widgets["operation"].value

                    if selected_param in self.all_calculated_data:
                        param_data = self.all_calculated_data[selected_param]
                    else:
                        param_data = (
                            dataset.sel(param=selected_param)
                            if hasattr(dataset, "sel")
                            else [
                                field
                                for field in dataset
                                if field.metadata("param") == selected_param
                            ]
                        )

                    calculated_result = self.aggregator.calculate_temporal_extremes(
                        param_data,
                        operation=operation,
                        param_name=selected_param,
                        output_format="xarray",
                    )

                    param_key = f"{selected_param}_{operation}"
                    self.all_calculated_data[param_key] = calculated_result
                    self.calculated_data = calculated_result
                    var_name = f"{operation.capitalize()} Value for {selected_param}"

                clear_output()

                total_calculated = len(self.all_calculated_data)

                success_message = f"""
                <b>Calculation Completed Successfully!</b><br>
                <b>{var_name}</b> has been calculated and is ready for use.<br>
                Total calculated parameters: <b>{total_calculated}</b>
                """

                self.print_styled_message(success_message, "success")

                self.widgets["download_btn"].disabled = False
                self.widgets["download_btn"].layout.display = "block"

                self.widgets["show_calculated_btn"].disabled = False
                self.widgets["show_calculated_btn"].layout.display = "block"
                self.widgets["clear_all_btn"].disabled = False
                self.widgets["clear_all_btn"].layout.display = "block"

            except Exception as e:
                clear_output()
                self.print_styled_message(f"Calculation failed: {str(e)}", "error")
                print(traceback.format_exc())

    def on_download_click(self, button):
        """Handle download button click with consistent styling."""
        with self.widgets["output"]:
            if self.calculated_data is None:
                self.print_styled_message(
                    "No calculated data available to download!", "error"
                )
                return

            try:
                calc_type = self.widgets["calc_type"].value

                if calc_type == "precipitation":
                    filename = "accumulated_precipitation.nc"
                elif calc_type == "wind_speed":
                    filename = "wind_speed.nc"
                elif calc_type == "extremes":
                    operation = self.widgets["operation"].value
                    param = self.widgets["param_selection"].value
                    filename = f"{operation}_{param}.nc"
                else:
                    filename = "calculated_data.nc"

                if isinstance(self.calculated_data, xr.Dataset):
                    self.calculated_data.to_netcdf(filename)
                elif isinstance(self.calculated_data, xr.DataArray):
                    self.calculated_data.to_netcdf(filename)
                else:
                    self.print_styled_message(
                        "Unsupported data format for download!", "error"
                    )
                    return

                self.print_styled_message(
                    f"Data downloaded successfully as '{filename}'!", "success"
                )
                self.print_styled_message("File saved in current directory", "success")
                self.print_styled_message(
                    "Data is also available as 'calculated_data' variable for further analysis!",
                    "info",
                )

                globals()["calculated_data"] = self.calculated_data

            except Exception as e:
                self.print_styled_message(f"Error during download: {str(e)}", "error")
                print(traceback.format_exc())

    def on_show_calculated_click(self, button):
        """Handle show calculated parameters button click with consistent styling."""
        with self.widgets["output"]:
            clear_output()

            if not self.all_calculated_data:
                self.print_styled_message(
                    "No calculated parameters available yet.", "info"
                )
                return

            self.print_styled_message(
                f"All Calculated Parameters ({len(self.all_calculated_data)} total):",
                "info",
            )

            for i, (param_key, data) in enumerate(self.all_calculated_data.items(), 1):
                if isinstance(data, xr.Dataset):
                    data_info = f"Dataset with variables: {list(data.data_vars.keys())}"
                elif isinstance(data, xr.DataArray):
                    data_info = f"DataArray: {data.name or 'unnamed'}"
                else:
                    data_info = f"Type: {type(data).__name__}"

                if hasattr(data, "dims"):
                    dims_info = f", Dimensions: {list(data.dims)}"
                else:
                    dims_info = ""

                styled_html = f"""
                <div style="background-color: #F5F5F5; padding: 8px; border-radius: 4px;
                            margin: 3px 0; border-left: 3px solid #4DD0E1;
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
                    {i}. <b>{param_key}</b>: {data_info}{dims_info}
                </div>
                """
                display(widgets.HTML(styled_html))

    def on_clear_all_click(self, button):
        """Handle clear all calculated parameters button click with consistent styling."""
        with self.widgets["output"]:
            clear_output()

            if not self.all_calculated_data:
                self.print_styled_message("No calculated parameters to clear.", "info")
                return

            cleared_count = len(self.all_calculated_data)
            self.all_calculated_data.clear()
            self.calculated_data = None

            self.widgets["show_calculated_btn"].disabled = True
            self.widgets["show_calculated_btn"].layout.display = "none"
            self.widgets["clear_all_btn"].disabled = True
            self.widgets["clear_all_btn"].layout.display = "none"
            self.widgets["download_btn"].disabled = True
            self.widgets["download_btn"].layout.display = "none"

            self.print_styled_message(
                f"Cleared {cleared_count} calculated parameter(s).", "warning"
            )

    def get_calculated_data(self):
        """Get the most recent calculated data.

        Returns:
            The most recent calculated xarray Dataset/DataArray or None if no calculation performed.

        """
        return self.calculated_data

    def get_all_calculated_data(self):
        """Get all calculated data.

        Returns:
            Dictionary containing all calculated parameters with their data.

        """
        return self.all_calculated_data.copy()

    def display_interface(self):
        """Display the calculator interface with consistent styling."""
        title = widgets.HTML(
            value="""
            <h2 style='color: #00BCD4; margin-bottom: 10px;'>Surface Variable Calculator</h2>
            <p style='color: #666; margin-bottom: 15px;'>Calculate derived meteorological variables from your downloaded surface variables.</p>
            """,
            layout=widgets.Layout(margin="0px 0px 10px 0px"),
        )

        calculation_section = widgets.VBox(
            [
                widgets.HTML(
                    "<h3 style='color: #50DEA3; margin-bottom: 10px;'>Calculation Type</h3>"
                ),
                self.widgets["calc_type"],
                self.widgets["info_display"],
            ],
            layout=widgets.Layout(margin="0px 0px 15px 0px", width="100%"),
        )

        param_config_left = widgets.VBox(
            [
                self.widgets["param_selection"],
            ],
            layout=widgets.Layout(width="48%", margin="0px 10px 0px 0px"),
        )

        param_config_right = widgets.VBox(
            [
                self.widgets["operation"],
            ],
            layout=widgets.Layout(width="48%", margin="0px 0px 0px 10px"),
        )
        param_config_section = widgets.VBox(
            [
                widgets.HBox(
                    [param_config_left, param_config_right],
                    layout=widgets.Layout(
                        justify_content="space-between", width="100%"
                    ),
                )
            ],
            layout=widgets.Layout(margin="0px 0px 15px 0px", width="100%"),
        )

        buttons_row1 = widgets.HBox(
            [
                self.widgets["calculate_btn"],
                self.widgets["download_btn"],
            ],
            layout=widgets.Layout(
                justify_content="center", margin="0px 0px 10px 0px", width="100%"
            ),
        )

        buttons_row2 = widgets.HBox(
            [
                self.widgets["show_calculated_btn"],
                self.widgets["clear_all_btn"],
            ],
            layout=widgets.Layout(justify_content="center", margin="0px", width="100%"),
        )

        buttons_section = widgets.VBox(
            [buttons_row1, buttons_row2],
            layout=widgets.Layout(margin="0px 0px 15px 0px", width="100%"),
        )

        interface = widgets.VBox(
            [
                title,
                calculation_section,
                param_config_section,
                buttons_section,
                self.widgets["output"],
            ],
            layout=widgets.Layout(padding="10px", width="100%"),
        )

        interface = widgets.Accordion(
            children=[interface],
            titles=["Surface Variables Calculator"],
        )
        interface.selected_index = 0

        display(interface)


def create_surface_calculator(weather_callbacks):
    """Create and display the surface variable calculator widget.

    Args:
        weather_callbacks: WeatherCallbacks instance containing downloaded data

    Returns:
        SurfaceVariableCalculatorUI instance

    """
    calculator = SurfaceVariableCalculatorUI(weather_callbacks)
    calculator.display_interface()
    return calculator
