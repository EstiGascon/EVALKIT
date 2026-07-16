import os
import traceback

from helpers.widgets.status_message_handler import StatusMessageHandler


class DataManagement:
    """Handles data loading, validation, and management operations."""

    def __init__(self, callbacks_instance):
        """Initialize with reference to main callbacks instance."""
        self.callbacks = callbacks_instance

    @property
    def ui(self):
        """Shortcut to UI instance."""
        return self.callbacks.ui

    @property
    def data_loader(self):
        """Shortcut to data loader."""
        return self.callbacks.data_loader

    @property
    def loaded_datasets(self):
        """Shortcut to loaded datasets."""
        return self.callbacks.loaded_datasets

    @property
    def map_handler(self):
        """Shortcut to map handler."""
        return self.callbacks.map_handler

    def _get_selected_models(self):
        """Get currently selected models from UI checkboxes."""
        selected_models = []

        if hasattr(self.ui, "widgets"):
            all_datasets = self.get_all_datasets()
            models = self.ui.config_manager.models
            for model_key in models.keys():
                model_short = model_key.split("-")[0]
                checkbox_name = f"{model_short}_checkbox"
                if (
                    checkbox_name in self.ui.widgets
                    and self.ui.widgets[checkbox_name].value
                ):
                    for dk in all_datasets.keys():
                        if dk == model_short or dk.startswith(model_key + "_"):
                            selected_models.append(dk)

            if (
                "observations_checkbox" in self.ui.widgets
                and self.ui.widgets["observations_checkbox"].value
                and not self.ui.widgets["observations_checkbox"].disabled
            ):
                selected_models.append("Observations")

        return selected_models

    def on_retrieve_click(self, button):  # noqa: PLR0915
        """Handle retrieve data button click for multiple models."""
        try:
            params = self.ui.get_parameters()

            if not self._validate_mars_params(params):
                return

            self.ui.widgets["mars_info_display"].value = ""

            selected_models = params.get("model", [])
            if not selected_models:
                StatusMessageHandler.show_error(
                    self.ui.widgets["mars_info_display"],
                    "No models selected. Please select at least one model.",
                )
                return

            if "rd-experiment" in selected_models and not params.get("rd_expver"):
                StatusMessageHandler.show_error(
                    self.ui.widgets["mars_info_display"],
                    "RD Experiment is selected but no experiment version (expver) was provided. "
                    "Please fill in the Exp. version field.",
                )
                return

            if "rd-experiment" in selected_models and not params.get("rd_class"):
                StatusMessageHandler.show_error(
                    self.ui.widgets["mars_info_display"],
                    "RD Experiment is selected but no MARS class was provided. "
                    "Please fill in the Class field.",
                )
                return

            selected_steps = params.get("selected_steps", [])

            self.ui.widgets["mars_info_display"].value = f"""
                <div style="background-color: #B2EBF2; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #0097A7;">
                    <h4 style="margin-top: 0; color: #006064;">🔄 Retrieving Data</h4>
                    <p>Retrieving data for {len(selected_models)} model(s): {", ".join(selected_models)}</p>
                    <p><em>This may take a few moments depending on the data size.</em></p>
                </div>
            """

            button.disabled = True
            button.description = "Retrieving..."
            button.icon = "hourglass"

            retrieval_results = {}
            successful_retrievals = 0
            skipped_params_info = []

            for model in selected_models:
                try:
                    print(f"\n{'=' * 60}")
                    print(f"Retrieving data for model: {model}")
                    print(f"Requested parameters: {params['param']}")
                    print(f"{'=' * 60}")

                    result = self.data_loader.retrieve_data_by_date_range(
                        params["param"],
                        start_date=params["start_date"],
                        end_date=params["end_date"],
                        time=params["time"],
                        model=model,
                        custom_area=params["area"],
                        grid=params["grid"],
                        custom_steps=selected_steps,
                        expver=params.get("rd_expver") if model == "rd-experiment" else None,
                        custom_class=params.get("rd_class") if model == "rd-experiment" else None,
                    )

                    retrieval_results[model] = result

                    if self._is_load_successful(result):
                        successful_retrievals += 1

                        # Check which parameters were actually retrieved
                        retrieved_params = result.get("metadata", {}).get("param", [])
                        requested_params = params["param"]
                        skipped = [
                            p for p in requested_params if p not in retrieved_params
                        ]

                        if skipped:
                            skipped_params_info.append(
                                f"{model}: skipped {', '.join(skipped)}"
                            )

                        print(f"✅ Successfully retrieved data for {model}")
                    else:
                        error_detail = ""
                        req_params = {}
                        if isinstance(result, dict) and "error" in result:
                            error_detail = result["error"]
                            req_params = result.get("request_params", {})
                            print(f"❌ Failed to retrieve data for {model}: {error_detail}")
                            print(f"   Request params: {req_params}")
                        else:
                            print(f"❌ Failed to retrieve data for {model}: result={result}")
                        retrieval_results[model] = {
                            "error": error_detail or "Unknown error",
                            "request_params": req_params,
                        }

                except Exception as e:
                    error_message = str(e)
                    print(f"❌ Error retrieving data for {model}: {error_message}")
                    full_traceback = traceback.format_exc()
                    print(full_traceback)
                    retrieval_results[model] = {
                        "error": error_message,
                        "traceback": full_traceback,
                    }

            self._handle_multiple_model_retrieval_results(
                retrieval_results, successful_retrievals, skipped_params_info
            )

            # Always refresh available parameters and model checkboxes so the UI
            # reflects the true state of loaded_datasets — even when 0 models
            # succeeded this run (stale checkboxes from a previous retrieval
            # would otherwise persist).
            self.callbacks.refresh_available_parameters()

            if successful_retrievals > 0:
                if self.ui.widgets["has_observations"].value == "yes":
                    self.ui.widgets["observations_checkbox"].disabled = False
                    self.ui.widgets["observations_checkbox"].value = True

        except Exception as e:
            StatusMessageHandler.show_error(
                self.ui.widgets["mars_info_display"],
                f"Retrieval error: {str(e)}",
            )
            print(f"❌ Exception in MARS retrieval: {e}")

        finally:
            button.disabled = False
            button.description = "Retrieve Data"
            button.icon = "download"

    def _handle_multiple_model_retrieval_results(
        self, retrieval_results, successful_retrievals, skipped_params_info=None
    ):
        """Handle results from multiple model retrievals."""
        total_models = len(retrieval_results)

        if successful_retrievals == total_models:
            model_list = ", ".join(retrieval_results.keys())

            skip_info = ""
            if skipped_params_info:
                skip_info = (
                    "<p style='color: #F57C00; font-size: 0.9em;'><strong>Note:</strong> "
                    + "; ".join(skipped_params_info)
                    + "</p>"
                )

            self.ui.widgets["mars_info_display"].value = f"""
                <div style="background-color: #E0F7FA; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #00BCD4;">
                    <h4 style="margin-top: 0; color: #006064;">✅ All Retrievals Successful</h4>
                    <p>Successfully retrieved data for all {total_models} model(s): {model_list}</p>
                    {skip_info}
                    <p>Data is ready for analysis.</p>
                </div>
            """
        elif successful_retrievals > 0:
            successful_models = [
                model
                for model, result in retrieval_results.items()
                if self._is_load_successful(result)
            ]
            failed_models = [
                model
                for model, result in retrieval_results.items()
                if not self._is_load_successful(result)
            ]

            skip_info = ""
            if skipped_params_info:
                skip_info = (
                    "<p style='font-size: 0.9em;'><strong>Parameter availability:</strong> "
                    + "; ".join(skipped_params_info)
                    + "</p>"
                )

            failed_details = ""
            for fm in failed_models:
                err = retrieval_results.get(fm, {})
                if isinstance(err, dict) and "error" in err:
                    failed_details += f"<p style='font-size: 0.9em; color: #D84315;'><strong>{fm}:</strong> {err['error']}</p>"
                else:
                    failed_details += f"<p style='font-size: 0.9em; color: #D84315;'><strong>{fm}:</strong> No error details available</p>"

            self.ui.widgets["mars_info_display"].value = f"""
                <div style="background-color: #FFF3E0; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #FF9800;">
                    <h4 style="margin-top: 0; color: #E65100;">⚠️ Partial Success</h4>
                    <p><strong>Successful ({successful_retrievals}/{total_models}):</strong> {', '.join(successful_models)}</p>
                    <p><strong>Failed:</strong></p>
                    {failed_details}
                    {skip_info}
                    <p>You can proceed with analysis using the successfully retrieved data.</p>
                </div>
            """
        else:
            failed_details = ""
            for model, result in retrieval_results.items():
                if isinstance(result, dict) and "error" in result:
                    req_params = result.get("request_params", {})
                    req_str = ""
                    if req_params:
                        req_items = ", ".join(f"{k}={v}" for k, v in req_params.items())
                        req_str = f"<p style='font-size: 0.85em; color: #5d4037; font-family: monospace;'>Request: {req_items}</p>"
                    failed_details += f"<p style='font-size: 0.9em; color: #D84315;'><strong>{model}:</strong> {result['error']}</p>{req_str}"
                else:
                    failed_details += f"<p style='font-size: 0.9em; color: #D84315;'><strong>{model}:</strong> No error details available</p>"
            self.ui.widgets["mars_info_display"].value = f"""
                <div style="background-color: #ffebee; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #f44336;">
                    <h4 style="margin-top: 0; color: #c62828;">❌ All Retrievals Failed</h4>
                    <p>Failed to retrieve data for any of the {total_models} selected model(s).</p>
                    {failed_details}
                </div>
            """

    def on_load_both_files_click(self, button):  # noqa: PLR0912, PLR0915
        """Handle load both files button click with validation."""
        try:
            configured_models = self.ui.config_manager.models
            selected_paths = {
                model_key.split("-")[0]: self.ui.selected_file_paths.get(model_key.split("-")[0])
                for model_key in configured_models.keys()
            }
            # Keep only models that have a file path specified
            active_paths = {ms: fp for ms, fp in selected_paths.items() if fp}

            if not active_paths:
                self.ui.widgets["local_info_display"].value = """
                    <div style="background-color: #FFEBEE; padding: 10px; border-radius: 5px; margin: 5px 0; border-left: 4px solid #F44336;">
                        <h4 style="margin-top: 0; color: #F44336;">No Files Selected</h4>
                        <p>Please enter file paths or use Browse buttons to select files.</p>
                    </div>
                """
                return

            validation_failed = False

            for model_short, file_path in active_paths.items():
                if not self.ui._validate_file_path(model_short):
                    self.ui.widgets["local_info_display"].value = f"""
                        <div style="background-color: #FFEBEE; padding: 10px; border-radius: 5px; margin: 5px 0; border-left: 4px solid #F44336;">
                            <h4 style="margin-top: 0; color: #F44336;">{model_short.upper()} File Invalid</h4>
                            <p>File not found or not accessible: {file_path}</p>
                        </div>
                    """
                    validation_failed = True

            if validation_failed:
                return

            button.disabled = True
            button.description = "Loading..."
            button.icon = "hourglass"

            results = {}

            for model_short, file_path in active_paths.items():
                if self.data_loader:
                    result = self.data_loader.load_grib_file(file_path)
                    results[model_short] = result
                    if self._is_load_successful(result):
                        self.loaded_datasets[model_short] = result

            if any(self._is_load_successful(result) for result in results.values()):
                try:
                    bbox_coords = []

                    for model_short in results:
                        if model_short in self.loaded_datasets and self._is_load_successful(results[model_short]):
                            try:
                                first_field = self.loaded_datasets[model_short][0]
                                west = first_field.metadata(
                                    "longitudeOfFirstGridPointInDegrees"
                                )
                                east = first_field.metadata(
                                    "longitudeOfLastGridPointInDegrees"
                                )
                                north = first_field.metadata(
                                    "latitudeOfFirstGridPointInDegrees"
                                )
                                south = first_field.metadata(
                                    "latitudeOfLastGridPointInDegrees"
                                )

                                bbox_coords.append(
                                    {
                                        "west": min(west, east),
                                        "east": max(west, east),
                                        "north": max(north, south),
                                        "south": min(north, south),
                                    }
                                )
                            except Exception as e:
                                print(f"⚠️ Could not extract {model_short.upper()} bbox: {e}")

                    if bbox_coords:
                        final_west = max(bbox["west"] for bbox in bbox_coords)
                        final_east = min(bbox["east"] for bbox in bbox_coords)
                        final_north = min(bbox["north"] for bbox in bbox_coords)
                        final_south = max(bbox["south"] for bbox in bbox_coords)

                        self.ui.widgets["west"].value = final_west
                        self.ui.widgets["east"].value = final_east
                        self.ui.widgets["north"].value = final_north
                        self.ui.widgets["south"].value = final_south

                        AUTO_FIT_BOUNDS_ON_LOAD = True

                        if AUTO_FIT_BOUNDS_ON_LOAD:
                            bounds = [
                                (final_south, final_west),
                                (final_north, final_east),
                            ]
                            self.map_handler.map_widget.fit_bounds(bounds)

                except Exception as e:
                    print(f"❌ Error extracting/updating bbox: {e}")

            self._update_load_summary_display(results)

            if any(self._is_load_successful(result) for result in results.values()):
                self.callbacks.refresh_available_parameters()
            if self.ui.widgets["has_observations"].value == "yes":
                self.ui.widgets["observations_checkbox"].disabled = False
                self.ui.widgets["observations_checkbox"].value = True

        except Exception as e:
            StatusMessageHandler.show_error(
                self.ui.widgets["mars_info_display"]
                if self.ui.widgets["data_source"].value == "mars"
                else self.ui.widgets["local_info_display"],
                f"Multiple file loading error: {str(e)}",
            )

        finally:
            button.disabled = False
            button.description = "Load Both Files"
            button.icon = "cloud-upload"

    def fit_map_to_bbox(self):
        """Manually fit map to current bounding box."""
        try:
            north = float(self.ui.widgets["north"].value)
            south = float(self.ui.widgets["south"].value)
            east = float(self.ui.widgets["east"].value)
            west = float(self.ui.widgets["west"].value)

            bounds = [(south, west), (north, east)]
            self.map_handler.map_widget.fit_bounds(bounds)

        except Exception as e:
            print(f"❌ Error fitting map to bbox: {e}")

    def force_refresh_unit_display(self):
        """Force refresh of unit display after parameters are loaded."""
        try:
            current_param = self.ui.widgets["processing_param"].value

            is_temperature_param = current_param in [
                "2t",
                "2d",
                "2t_24h_max",
                "2t_24h_min",
                "2d_24h_max",
                "2d_24h_min",
            ]
            is_precipitation_param = current_param in [
                "tp",
                "tp_deaccum",
                "cp",
                "cp_deaccum",
                "lsp",
                "lsp_deaccum",
            ]

            if hasattr(self.ui.widgets, "units_container"):
                display_units = (
                    "block"
                    if (is_temperature_param or is_precipitation_param)
                    else "none"
                )
                self.ui.widgets["units_container"].layout.display = display_units

                if is_temperature_param or is_precipitation_param:
                    temp_display = "block" if is_temperature_param else "none"
                    precip_display = "block" if is_precipitation_param else "none"

                    self.ui.widgets["temperature_unit"].layout.display = temp_display
                    self.ui.widgets[
                        "precipitation_unit"
                    ].layout.display = precip_display

        except Exception as e:
            print(f"❌ Error in force_refresh_unit_display: {e}")

    def refresh_available_parameters(self):  # noqa: PLR0912, PLR0915
        """Refresh parameters in the list."""
        try:
            dataset_parameters = {}

            if self.data_loader:
                loader_datasets = self.data_loader.get_all_datasets()
                for model_key, dataset in loader_datasets.items():
                    params = self._extract_parameters_from_dataset(dataset, model_key)
                    dataset_parameters[model_key] = set(params)
            for model_key, dataset in self.loaded_datasets.items():
                params = self._extract_parameters_from_dataset(dataset, model_key)
                dataset_parameters[model_key] = set(params)

            if len(dataset_parameters) == 0:
                final_parameters = set()
            else:
                final_parameters = set()
                for params in dataset_parameters.values():
                    final_parameters.update(params)

            if "10u" in final_parameters and "10v" in final_parameters:
                if "10ff" not in final_parameters:
                    final_parameters.add("10ff")
                final_parameters.add("10ff_daily")

            if "10fg" in final_parameters:
                final_parameters.add("10fg_6h")
                final_parameters.add("10fg_12h")
                final_parameters.add("10fg_24h")
                final_parameters.add("10fg_48h")

            if "2t" in final_parameters:
                final_parameters.add("2t_24h_max")
                final_parameters.add("2t_24h_min")

            if "2d" in final_parameters:
                final_parameters.add("2d_24h_max")
                final_parameters.add("2d_24h_min")

            if final_parameters:
                parameter_options = []

                param_descriptions = {
                    "2t": "2m Temperature",
                    "2d": "2m Dewpoint Temperature",
                    "2t_24h_max": "Daily Maximum 2m Temperature",
                    "2t_24h_min": "Daily Minimum 2m Temperature",
                    "2d_24h_max": "Daily Maximum 2m Dewpoint Temperature",
                    "2d_24h_min": "Daily Minimum 2m Dewpoint Temperature",
                    "10u": "U Wind component",
                    "10v": "V Wind component",
                    "10ff": "10m Wind Speed (calculated)",
                    "10ff_daily": "Daily Mean 10m Wind Speed",
                    "10fg": "Hourly 10m Wind Gust",
                    "10fg_6h": "Max 6h Wind Gust",
                    "10fg_12h": "Max 12h Wind Gust",
                    "10fg_24h": "Max 24h Wind Gust",
                    "10fg_48h": "Max 48h Wind Gust",
                    "tp": "Total Precipitation (cumulative)",
                    "cp": "Convective Precipitation",
                    "lsp": "Large Scale Precipitation",
                }

                for param in sorted(final_parameters):
                    description = param_descriptions.get(param, f"Parameter: {param}")
                    parameter_options.append((description, param))

                if "tp" in final_parameters:
                    parameter_options.append(
                        ("Precipitation (with deaccumulation)", "tp_deaccum")
                    )
                if "cp" in final_parameters:
                    parameter_options.append(
                        ("Convective Precipitation (deaccumulated)", "cp_deaccum")
                    )

                if "lsp" in final_parameters:
                    parameter_options.append(
                        ("Large Scale Precipitation (deaccumulated)", "lsp_deaccum")
                    )

                self.ui.update_parameter_dropdown(parameter_options)

            else:
                self.ui.update_parameter_dropdown([])

            all_datasets = self.get_all_datasets()

            models = self.ui.config_manager.models
            for model_key in models.keys():
                model_short = model_key.split("-")[0]
                checkbox_name = f"{model_short}_checkbox"
                has_data = any(
                    k == model_short or k.startswith(model_key + "_")
                    for k in all_datasets.keys()
                )
                if checkbox_name in self.ui.widgets:
                    # Always keep the checkbox visible so the user can see all configured
                    # models. Disable (and uncheck) it when no data has been loaded for
                    # that model instead of hiding it completely.
                    self.ui.widgets[checkbox_name].layout.display = "block"
                    self.ui.widgets[checkbox_name].disabled = not has_data
                    if has_data:
                        # Re-enable and check the box whenever data is present, so that
                        # a model retrieved after a previous failure (e.g. IFS 4.4 km on
                        # a second attempt) is automatically selected for plotting.
                        self.ui.widgets[checkbox_name].value = True
                    else:
                        self.ui.widgets[checkbox_name].value = False

            # Sync obs date pickers to the forecast valid-datetime range so that
            # VINO retrieval defaults always cover the same period as the forecast.
            self._sync_obs_dates_from_forecast(all_datasets)

            try:
                current_param = self.ui.widgets["processing_param"].value

                if current_param and current_param != "none":
                    if hasattr(self.ui.widgets, "units_container"):
                        is_temp = current_param in [
                            "2t",
                            "2d",
                            "2t_24h_max",
                            "2t_24h_min",
                            "2d_24h_max",
                            "2d_24h_min",
                        ]
                        is_precip = current_param in [
                            "tp",
                            "tp_deaccum",
                            "cp",
                            "cp_deaccum",
                            "lsp",
                            "lsp_deaccum",
                        ]

                        if is_temp or is_precip:
                            self.ui.widgets["units_container"].layout.display = "block"

                            if is_temp:
                                self.ui.widgets[
                                    "temperature_unit"
                                ].layout.display = "block"
                                self.ui.widgets[
                                    "precipitation_unit"
                                ].layout.display = "none"
                            elif is_precip:
                                self.ui.widgets[
                                    "temperature_unit"
                                ].layout.display = "none"
                                self.ui.widgets[
                                    "precipitation_unit"
                                ].layout.display = "block"
                        else:
                            self.ui.widgets["units_container"].layout.display = "none"
                    else:
                        print("Units container not found")
                elif hasattr(self.ui.widgets, "units_container"):
                    self.ui.widgets["units_container"].layout.display = "none"

            except Exception as widget_error:
                print(f"Error in force refresh unit display: {widget_error}")

        except Exception as e:
            StatusMessageHandler.show_error(
                self.ui.widgets["mars_info_display"]
                if self.ui.widgets["data_source"].value == "mars"
                else self.ui.widgets["local_info_display"],
                f"Error refreshing parameters: {str(e)}",
            )

    def _extract_parameters_from_dataset(self, dataset, model_key: str) -> list[str]:  # noqa: PLR0912
        """Parameter extraction that includes calculated parameters."""
        parameters = []

        try:
            if hasattr(dataset, "metadata"):
                try:
                    params = dataset.metadata("param")
                    if isinstance(params, list | tuple):
                        parameters.extend([str(p) for p in params])
                    elif params:
                        parameters.append(str(params))
                except Exception:
                    pass

            if hasattr(dataset, "keys"):
                try:
                    keys = list(dataset.keys())
                    coord_names = {
                        "time",
                        "lat",
                        "lon",
                        "latitude",
                        "longitude",
                        "valid_time",
                        "step",
                    }
                    param_keys = [k for k in keys if k not in coord_names]
                    parameters.extend(param_keys)
                except Exception:
                    pass

            unique_parameters = []
            seen = set()
            for param in parameters:
                if param not in seen:
                    unique_parameters.append(param)
                    seen.add(param)

            if "10u" in unique_parameters and "10v" in unique_parameters:
                if "10ff" not in unique_parameters:
                    unique_parameters.append("10ff")

            if "tp" in unique_parameters:
                print(f" Precipitation deaccumulation available for {model_key}")

            if "cp" in unique_parameters:
                print(
                    f"Convective precipitation deaccumulation available for {model_key}"
                )

            if "lsp" in unique_parameters:
                print(
                    f"Large scale precipitation deaccumulation available for {model_key}"
                )

            return unique_parameters

        except Exception as e:
            print(f"  ⚠️ Error extracting parameters from {model_key}: {str(e)}")
            return []

    def _format_preview_info(self, params):
        """Format preview information as HTML."""
        if params["data_source"] == "local":
            aifs_file = params["selected_file_paths"]["aifs"]
            ifs_file = params["selected_file_paths"]["ifs"]

            aifs_status = "✅ Selected" if aifs_file else "❌ Not selected"
            ifs_status = "✅ Selected" if ifs_file else "❌ Not selected"

            param_info = f"<p><strong>Processing Parameter:</strong> {params['processing_parameter'] if params['processing_parameter'] != 'none' else 'Not selected'}</p>"
            obs_info = f"<p><strong>Observation Data:</strong> {'✅ Yes' if params['has_observations'] else '❌ No'}</p>"
            if params["has_observations"] and params["observation_folder"]:
                obs_info += f"<p style='font-size: 0.9em; color: #666; margin-left: 20px;'>Folder: {os.path.basename(params['observation_folder'])}</p>"

            return f"""
                <div style="background-color: #E0F7FA; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #00BCD4;">
                    <h4 style="margin-top: 0; color: #006064;"> Local Files Preview</h4>
                    <p><strong>AIFS File:</strong> {aifs_status}</p>
                    {f'<p style="font-size: 0.9em; color: #666; margin-left: 20px;">{os.path.basename(aifs_file)}</p>' if aifs_file else ""}
                    <p><strong>IFS File:</strong> {ifs_status}</p>
                    {f'<p style="font-size: 0.9em; color: #666; margin-left: 20px;">{os.path.basename(ifs_file)}</p>' if ifs_file else ""}
                    <p><strong>Ready to load:</strong> {"✅ Yes" if (aifs_file or ifs_file) else "❌ No files selected"}</p>
                    <hr style="margin: 10px 0;">
                    {param_info}
                    {obs_info}
                </div>
            """
        else:
            steps_info = (
                f"{len(params['selected_steps'])} steps"
                if params["selected_steps"]
                else "No steps selected"
            )
            if params.get("grid") and params["grid"] is not None:
                grid_display = f"{params['grid'][0]}° × {params['grid'][1]}°"
            else:
                grid_display = "Native resolution"

            param_info = f"<p><strong>Processing Parameter:</strong> {params['processing_parameter'] if params['processing_parameter'] != 'none' else 'Not selected'}</p>"
            obs_info = f"<p><strong>Observation Data:</strong> {'✅ Yes' if params['has_observations'] else '❌ No'}</p>"
            if params["has_observations"] and params["observation_folder"]:
                obs_info += f"<p style='font-size: 0.9em; color: #666; margin-left: 20px;'>Folder: {os.path.basename(params['observation_folder'])}</p>"

            return f"""
                <div style="background-color: #B2EBF2; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #0097A7;">
                    <h4 style="margin-top: 0; color: #006064;"> MARS Archive Preview</h4>
                    <p><strong>Parameters:</strong> {", ".join(params["param"])}</p>
                    <p><strong>Model:</strong> {params["model"]}</p>
                    <p><strong>Date Range:</strong> {params["start_date"]} to {params["end_date"]}</p>
                    <p><strong>Time:</strong> {params["time"]}</p>
                    <p><strong>Area:</strong> N:{params["area"][0]:.3f}°, W:{params["area"][1]:.3f}°, S:{params["area"][2]:.3f}°, E:{params["area"][3]:.3f}°</p>
                    <p><strong>Grid:</strong> {grid_display}</p>
                    <p><strong>Steps:</strong> {steps_info}</p>
                    <hr style="margin: 10px 0;">
                    {param_info}
                    {obs_info}
                </div>
            """

    def _validate_mars_params(self, params):
        """Validate MARS parameters for multiple models."""
        return self.callbacks.validation_helper._validate_mars_params(params)

    def _handle_retrieval_result(self, result):
        """Handle Retrieval result."""
        is_successful = False

        if result:
            if isinstance(result, dict):
                if result.get("success", False):
                    is_successful = True
                elif not result.get("error", False) and not result.get("failed", False):
                    is_successful = True
                elif "data" in result and result["data"]:
                    is_successful = True
            elif result is not False and result is not None:
                is_successful = True

        if self.data_loader:
            loader_datasets = self.data_loader.get_all_datasets()
            if loader_datasets:
                is_successful = True

        if is_successful:
            self.ui.widgets["mars_info_display"].value = """
                <div style="background-color: #E0F7FA; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #00BCD4;">
                    <h4 style="margin-top: 0; color: #006064;">✅ Retrieval Successful</h4>
                    <p>Data has been successfully retrieved and is ready for analysis.</p>
                </div>
            """
        else:
            print("❌ MARS retrieval result: FAILED")

    def _sync_obs_dates_from_forecast(self, all_datasets):
        """Sync obs_start_date / obs_end_date widgets to the forecast valid-datetime range.

        This ensures that the VINO observation retrieval defaults cover the same
        period as the loaded forecast so the 'Explore observation lead times'
        explorer shows dates that align with the forecast.
        """
        try:
            if not all_datasets:
                return
            if "obs_start_date" not in self.ui.widgets or "obs_end_date" not in self.ui.widgets:
                return

            import pandas as pd

            all_datetimes = []
            for model_key, dataset in all_datasets.items():
                try:
                    if hasattr(dataset, "metadata"):
                        vdt = dataset.metadata("valid_datetime")
                        if vdt is not None:
                            all_datetimes.extend(pd.to_datetime(vdt).tolist())
                except Exception:
                    pass

            if not all_datetimes:
                return

            forecast_start = min(all_datetimes).date()
            forecast_end = max(all_datetimes).date()

            self.ui.widgets["obs_start_date"].value = forecast_start
            self.ui.widgets["obs_end_date"].value = forecast_end

        except Exception as e:
            print(f"⚠️ Could not sync obs dates from forecast: {e}")

    def _is_load_successful(self, result):
        """Enhanced load success checker with better detection logic."""
        if result is None or result is False:
            return False

        if isinstance(result, dict):
            # Explicit error → always fail
            if result.get("error"):
                return False

            # Avoid calling bool() on dataset objects (earthkit FieldList,
            # numpy arrays, etc.) — use identity check instead.
            has_data = (result.get("data") is not None) or (result.get("dataset") is not None)
            explicit_success = result.get("success", False)

            return has_data or explicit_success
        else:
            return True

    def _update_load_summary_display(self, results):
        """Update the local info display with loading summary."""
        summary_items = []

        for model_type, result in results.items():
            status = "✅ Success" if self._is_load_successful(result) else "❌ Failed"
            summary_items.append(
                f"<p><strong>{model_type.upper()}:</strong> {status}</p>"
            )

        summary_html = f"""
            <div style="background-color: #E0F7FA; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #00BCD4;">
                <h4 style="margin-top: 0; color: #2e7d32;">✅ Loading Summary</h4>
                {"".join(summary_items)}
                <p><em>All loaded files are ready for analysis.</em></p>
            </div>
        """
        self.ui.widgets["local_info_display"].value = summary_html

    def get_all_datasets(self):
        """Get all loaded datasets."""
        all_datasets = {}

        if self.data_loader:
            loader_datasets = self.data_loader.get_all_datasets()
            all_datasets.update(loader_datasets)

        all_datasets.update(self.loaded_datasets)

        return all_datasets

    def get_dataset(self, model_key: str = None):  # noqa: PLR0911
        """Get the loaded dataset(s)."""
        if not self.data_loader:
            print("⚠️ No data loader configured")
            return None

        if model_key and model_key in self.loaded_datasets:
            print(f" Retrieved {model_key.upper()} dataset from local storage")
            return self.loaded_datasets[model_key]

        all_datasets = self.data_loader.get_all_datasets()

        if not all_datasets and not self.loaded_datasets:
            print(" No datasets currently loaded")
            return None

        if model_key:
            dataset = self.data_loader.get_dataset(model_key)
            if dataset:
                print(f"Retrieved dataset for model: {model_key}")
                return dataset

            if model_key in self.loaded_datasets:
                print(f" Retrieved {model_key.upper()} dataset from local storage")
                return self.loaded_datasets[model_key]

            print(f"❌ No dataset found for model: {model_key}")
            available_models = list(all_datasets.keys()) + list(
                self.loaded_datasets.keys()
            )
            print(f"Available models: {available_models}")
            return None

        if all_datasets:
            latest_key = list(all_datasets.keys())[-1]
            dataset = all_datasets[latest_key]
            print(f"Retrieved latest dataset: {latest_key}")
            return dataset
        elif self.loaded_datasets:
            latest_key = list(self.loaded_datasets.keys())[-1]
            dataset = self.loaded_datasets[latest_key]
            print(f"Retrieved latest {latest_key.upper()} dataset from local storage")
            return dataset

        return None
