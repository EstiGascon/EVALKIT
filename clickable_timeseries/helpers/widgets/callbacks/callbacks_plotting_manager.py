class PlottingManager:
    """Handles plotting operations and visualization management."""

    def __init__(self, callbacks_instance):
        """Initialize with reference to main callbacks instance."""
        self.callbacks = callbacks_instance

    @property
    def ui(self):
        """Shortcut to UI instance."""
        return self.callbacks.ui

    @property
    def plotting_manager(self):
        """Shortcut to plotting manager."""
        return self.callbacks.plotting_manager

    @property
    def multi_point_data(self):
        """Shortcut to multi point data."""
        return self.callbacks.multi_point_data

    def _show_initial_empty_plot(self):
        """Show empty plot when interface first loads."""
        try:
            fig = self.plotting_manager.create_empty_plot()

            if hasattr(self.ui, "widgets") and "plot_output" in self.ui.widgets:
                with self.ui.widgets["plot_output"]:
                    self.ui.widgets["plot_output"].clear_output(wait=True)
                    fig.show()

        except Exception as e:
            print(f"Error showing initial empty plot: {e}")

    def _create_unified_plot(self, parameter_name):
        """Create plot with time period mismatch detection."""
        selected_models = self.callbacks._get_selected_models()

        if parameter_name == "none":
            fig = self.plotting_manager.create_empty_plot()

        else:
            mismatch_detected = self.callbacks._check_for_time_period_mismatches()

            if mismatch_detected:
                self.callbacks._show_time_period_mismatch_error()
                fig = self._create_time_period_error_plot(parameter_name)
            else:
                fig = self.plotting_manager.create_multi_point_timeseries_plot(
                    multi_point_data=self.multi_point_data,
                    parameter_name=parameter_name,
                    selected_models=selected_models,
                )

        if hasattr(self.ui, "widgets") and "plot_output" in self.ui.widgets:
            print(" Found plot_output widget")
            with self.ui.widgets["plot_output"]:
                self.ui.widgets["plot_output"].clear_output(wait=True)
                if fig is not None:
                    fig.show()
                else:
                    print("Cannot display - fig is None")
        else:
            print("plot_output widget not found")

    def _create_time_period_error_plot(self, parameter_name):
        """Create a user-friendly error plot for time period mismatches."""
        try:
            fig = self.plotting_manager.create_placeholder_plot(
                len(self.multi_point_data), "Time Period Mismatch"
            )

            return fig

        except Exception as e:
            print(f"❌ Error creating time period error plot: {e}")
            return (
                self.plotting_manager.create_empty_plot()
                if self.plotting_manager
                else None
            )

    def _create_placeholder_plot(self, num_points, message):
        """Create placeholder plot with message."""
        try:
            fig = self.plotting_manager.create_placeholder_plot(num_points, message)

            if hasattr(self.ui, "widgets") and "plot_output" in self.ui.widgets:
                with self.ui.widgets["plot_output"]:
                    self.ui.widgets["plot_output"].clear_output(wait=True)
                    fig.show()

        except Exception as e:
            print(f"❌ Error creating placeholder plot: {e}")
