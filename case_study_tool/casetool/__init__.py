"""Case-study evaluation tool: compare forecast models with observations.

Describe a case in a YAML file (models, area, accumulation window, lead
times, observations) and run::

    python case_study_tool/run_case.py run my_case.yaml

See ``python case_study_tool/run_case.py --help`` and ``configs/`` for examples.
"""

from casetool.config import CaseConfig, load_config
from casetool.pipeline import run

__all__ = ["CaseConfig", "load_config", "run"]
