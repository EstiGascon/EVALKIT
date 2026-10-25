"""Run a case study: ``python case_study_tool/run_case.py run CONFIG.yaml``."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from casetool.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
