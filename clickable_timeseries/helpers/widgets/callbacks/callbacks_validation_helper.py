import traceback

import pandas as pd
from helpers.widgets.status_message_handler import StatusMessageHandler


class ValidationHelper:
    """Handles validation operations for forecast and observation data."""

    def __init__(self, callbacks_instance):
        """Initialize with reference to main callbacks instance."""
        self.callbacks = callbacks_instance

    @property
    def ui(self):
        """Shortcut to UI instance."""
        return self.callbacks.ui

    @property
    def multi_point_data(self):
        """Shortcut to multi point data."""
        return self.callbacks.multi_point_data

    def _check_validation_before_plotting(self) -> bool:
        """Check if plotting can proceed based on parameter validation."""
        try:
            if not self.ui.can_proceed_with_plotting():
                StatusMessageHandler.show_plot_info(
                    self.ui.widgets["mars_info_display"],
                    "Plotting disabled due to parameter mismatch<br>"
                    "Your observation data parameter doesn't match the selected forecast parameter<br>"
                    "Please select the correct forecast parameter or choose a different observation folder<br>"
                    "The parameter validation message above shows the required parameter",
                )
                self.callbacks.plotting_manager_callbacks._create_placeholder_plot(
                    0, "Parameter validation required"
                )
                return False

            return True

        except Exception as e:
            print(f"Error checking validation status: {e}")
            return True

    def _check_for_time_period_mismatches(self):
        """Check if any points have forecast models with no common time period."""
        try:
            for _point_id, point_data in self.multi_point_data.items():
                forecast_data = point_data.get("forecast_data", {})

                forecast_models = {
                    k: v
                    for k, v in forecast_data.items()
                    if k != "Observations" and v is not None and not v.empty
                }

                if len(forecast_models) < 2:  # noqa: PLR2004
                    continue

                common_start = None
                common_end = None

                for _model_name, forecast_df in forecast_models.items():
                    if isinstance(forecast_df, pd.DataFrame):
                        model_start = forecast_df.index.min()
                        model_end = forecast_df.index.max()
                    else:
                        model_start = forecast_df.index.min()
                        model_end = forecast_df.index.max()

                    if common_start is None or model_start > common_start:
                        common_start = model_start
                    if common_end is None or model_end < common_end:
                        common_end = model_end

                if common_start >= common_end:
                    return True

            return False

        except Exception as e:
            print(f"❌ Error checking for time period mismatches: {e}")
            return False

    def _show_time_period_mismatch_error(self):
        """Show detailed error message about time period mismatch in UI."""
        try:
            mismatch_details = []

            for point_id, point_data in self.multi_point_data.items():
                forecast_data = point_data.get("forecast_data", {})
                forecast_models = {
                    k: v
                    for k, v in forecast_data.items()
                    if k != "Observations" and v is not None and not v.empty
                }

                if len(forecast_models) >= 2:  # noqa: PLR2004
                    point_details = [
                        f"<strong>Point {point_data.get('label', point_id)}:</strong>"
                    ]

                    for model_name, forecast_df in forecast_models.items():
                        start_time = forecast_df.index.min()
                        end_time = forecast_df.index.max()
                        duration = end_time - start_time

                        point_details.append(
                            f"&nbsp;&nbsp;• {model_name}: {start_time.strftime('%Y-%m-%d %H:%M')} "
                            f"to {end_time.strftime('%Y-%m-%d %H:%M')} "
                            f"({duration})"
                        )

                    mismatch_details.append("<br>".join(point_details))

            error_message = f"""
                ⚠️ <strong>Forecast Time Period Mismatch Detected</strong><br><br>

                The forecast models have no overlapping time periods, making comparison impossible.<br><br>

                <strong>📅 Detected Time Periods:</strong><br>
                {"<br><br>".join(mismatch_details)}<br><br>

                <strong> How to fix this:</strong><br>
                • Load forecast data with matching time ranges<br>
                • Verify that start/end dates are compatible
            """

            StatusMessageHandler.show_plot_info(
                self.ui.widgets["mars_info_display"], error_message
            )

        except Exception as e:
            print(f"❌ Error showing time period mismatch error: {e}")

    def _validate_forecast_observation_time_range(
        self, all_datasets, start_obs_date, end_obs_date
    ):
        """Validate that forecast time range is contained within observation time range."""
        try:
            if not all_datasets:
                return {
                    "is_valid": False,
                    "error_message": "No forecast datasets loaded for comparison",
                    "forecast_start": None,
                    "forecast_end": None,
                }

            forecast_time_ranges = {}

            for model_name, dataset in all_datasets.items():
                try:
                    time_range = self._extract_time_range_from_dataset(
                        dataset, model_name
                    )
                    if time_range and time_range.get("start") and time_range.get("end"):
                        forecast_time_ranges[model_name] = time_range
                except Exception as e:
                    print(f"⚠️ Error extracting time range from {model_name}: {e}")
                    continue

            if not forecast_time_ranges:
                return {
                    "is_valid": False,
                    "error_message": "Could not extract time ranges from any forecast datasets",
                    "forecast_start": None,
                    "forecast_end": None,
                }

            forecast_starts = [tr["start"] for tr in forecast_time_ranges.values()]
            forecast_ends = [tr["end"] for tr in forecast_time_ranges.values()]

            earliest_forecast_start = min(forecast_starts)
            latest_forecast_end = max(forecast_ends)

            forecast_start_in_range = (
                start_obs_date <= earliest_forecast_start <= end_obs_date
            )
            forecast_end_in_range = (
                start_obs_date <= latest_forecast_end <= end_obs_date
            )

            if not forecast_start_in_range or not forecast_end_in_range:
                if earliest_forecast_start < start_obs_date:
                    error_msg = f"Forecast starts before observation data begins ({earliest_forecast_start} < {start_obs_date})"
                elif latest_forecast_end > end_obs_date:
                    error_msg = f"Forecast ends after observation data ends ({latest_forecast_end} > {end_obs_date})"
                else:
                    error_msg = "Forecast time range is not fully contained within observation time range"

                return {
                    "is_valid": False,
                    "error_message": error_msg,
                    "forecast_start": earliest_forecast_start,
                    "forecast_end": latest_forecast_end,
                }

            return {
                "is_valid": True,
                "error_message": None,
                "forecast_start": earliest_forecast_start,
                "forecast_end": latest_forecast_end,
            }

        except Exception as e:
            print(f"❌ Error in time range validation: {e}")
            traceback.print_exc()
            return {
                "is_valid": False,
                "error_message": f"Validation error: {str(e)}",
                "forecast_start": None,
                "forecast_end": None,
            }

    def _extract_time_range_from_dataset(self, dataset, model_name):  # noqa: PLR0912
        """Extract time range from a forecast dataset."""
        try:
            if hasattr(dataset, "metadata"):
                try:
                    valid_datetimes = dataset.metadata("valid_datetime")
                    if valid_datetimes is not None:
                        datetime_series = pd.to_datetime(valid_datetimes)
                        start_time = datetime_series.min()
                        end_time = datetime_series.max()

                        return {"start": start_time, "end": end_time}
                except Exception as e:
                    print(f"⚠️ {model_name}: Error getting valid_datetime metadata: {e}")

            if hasattr(dataset, "__iter__"):
                times = []
                for i, field in enumerate(dataset):
                    if i > 50:  # noqa: PLR2004
                        break
                    try:
                        if hasattr(field, "metadata"):
                            valid_time = field.metadata("valid_time")
                            if valid_time:
                                times.append(pd.to_datetime(valid_time))
                            else:
                                base_time = field.metadata("base_time")
                                step = field.metadata("step")
                                if base_time and step is not None:
                                    base_dt = pd.to_datetime(base_time)
                                    step_td = pd.Timedelta(hours=float(step))
                                    times.append(base_dt + step_td)
                    except Exception:
                        continue

                if times:
                    start_time = min(times)
                    end_time = max(times)
                    return {"start": start_time, "end": end_time}

            return None

        except Exception as e:
            print(f"❌ Error extracting time range from {model_name}: {e}")

    def _validate_mars_params(self, params):
        """Validate MARS parameters for multiple models."""
        if params["data_source"] != "mars":
            return True

        errors = []
        warnings = []

        selected_models = params.get("model", [])
        if not selected_models:
            errors.append("No models selected")

        if not params.get("param"):
            errors.append("No parameters selected")

        if not params.get("selected_steps"):
            errors.append("No forecast steps selected")

        if params["start_date"] > params["end_date"]:
            errors.append("Start date must be before end date")

        area = params["area"]
        if area[0] <= area[2]:
            errors.append("North boundary must be greater than South boundary")

        if area[3] <= area[1]:
            errors.append("East boundary must be greater than West boundary")

        if errors or warnings:
            messages = []

            if errors:
                error_msg = "<br>".join([f"• {error}" for error in errors])
                messages.append(f"""
                    <h4 style="margin-top: 0; color: #c62828;">❌ Validation Errors</h4>
                    {error_msg}
                """)

            if warnings:
                warning_msg = "<br>".join([f"• {warning}" for warning in warnings])
                messages.append(f"""
                    <h4 style="margin-top: 0; color: #f57c00;">⚠️ Warnings</h4>
                    {warning_msg}
                """)

            self.ui.widgets["mars_info_display"].value = f"""
                <div style="background-color: #ffebee; padding: 15px; border-radius: 8px; margin: 10px 0;">
                    {"".join(messages)}
                </div>
            """

            return len(errors) == 0

        return True
