import sys
from pathlib import Path

current_dir = Path(__file__).parent if "__file__" in globals() else Path.cwd()
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

from helpers.data_acquisition import MarsArchiveDataRetriever  # noqa: E402
from helpers.widgets.data_widgets import DataRetrieverUI  # noqa: E402
from helpers.widgets.plotting_widgets import create_plotting_interface  # noqa: E402
from helpers.widgets.surface_widgets import create_surface_calculator  # noqa: E402
from helpers.widgets.weather_callbacks import DataRetrieverCallbacks  # noqa: E402

data_retrieval_ui = DataRetrieverUI()
data_retriever = MarsArchiveDataRetriever(source="mars")
ui_callbacks = DataRetrieverCallbacks(data_retrieval_ui, data_retriever)
data_retrieval_ui.set_callbacks(ui_callbacks)
data_retrieval_ui.display_advanced_interface()
calculator = create_surface_calculator(ui_callbacks)
plotting_widget = create_plotting_interface(ui_callbacks, calculator)
