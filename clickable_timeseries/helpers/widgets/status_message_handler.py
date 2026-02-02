class StatusMessageHandler:
    """Centralized handler for all status and information messages."""

    @staticmethod
    def show_obs_success(widget, message):
        """Show success message for observation validation."""
        widget.value = f"""
            <div style="background-color: #E0F7FA; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #00BCD4;">
                <h4 style="margin-top: 0; color: #006064;">Success</h4>
                {message}
            </div>
        """

    @staticmethod
    def show_obs_warning(widget, message):
        """Show warning message for observation validation."""
        widget.value = f"""
            <div style="background-color: #B2EBF2; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #0097A7;">
                <h4 style="margin-top: 0; color: #006064;">Warning</h4>
                {message}
            </div>
        """

    @staticmethod
    def show_obs_error(widget, message):
        """Show error message for observation validation."""
        widget.value = f"""
            <div style="background-color: #B2DFDB; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #006064;">
                <h4 style="margin-top: 0; color: #006064;">Error</h4>
                {message}
            </div>
        """

    @staticmethod
    def show_obs_info(widget, message):
        """Show info message for observation validation."""
        widget.value = f"""
            <div style="background-color: #E0F7FA; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #4DD0E1;">
                <h4 style="margin-top: 0; color: #006064;">ℹInformation</h4>
                {message}
            </div>
        """

    @staticmethod
    def show_error(widget, message):
        """Show general error message."""
        widget.value = f"""
            <div style="background-color: #ffebee; padding: 15px; border-radius: 8px; margin: 10px 0;">
                <h4 style="margin-top: 0; color: #c62828;">Error</h4>
                <p>{message}</p>
            </div>
        """

    @staticmethod
    def show_plot_info(widget, message):
        """Show information in plot display."""
        widget.value = f"""
            <div style="background-color: #e3f2fd; padding: 10px; border-radius: 5px; margin: 5px 0;">
                {message}
            </div>
        """
