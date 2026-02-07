"""Unified weather data interface - replaces WeatherDataInterface.

This module provides a simple interface for creating the complete
ensemble tool with UI and callbacks integrated.
"""

from .ensemble_tool import EnsembleCallbacks, EnsembleUI


class WeatherInterface:
    """Complete weather data interface with UI, callbacks, and plotting.

    This class provides backward compatibility while using the new
    refactored architecture.
    """

    def __init__(self, config_file="model_config.json"):
        """Initialize the weather interface.

        Args:
            config_file: Path to model configuration JSON file

        """
        self.ui = EnsembleUI(config_file=config_file)
        self.callbacks = EnsembleCallbacks(config_file=config_file)
        self.ui.set_callbacks(self.callbacks)
        self.callbacks.set_ui_reference(self.ui)
        self.callbacks.setup_map_handler()
        self.callbacks.setup_complete_integration()

    def display(self):
        """Display the complete interface."""
        self.ui.display_interface()


WeatherDataInterface = WeatherInterface


def create_weather_interface(config_file="model_config.json"):
    """Create a weather interface.

    Args:
        config_file: Path to model configuration JSON file

    Returns:
        WeatherInterface: Complete interface instance

    """
    return WeatherInterface(config_file=config_file)
