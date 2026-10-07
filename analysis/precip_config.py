"""Configuration for the Baltic 24 h precipitation misplacement case study.

A heavy-rain event was forecast too far north over the Baltic states
(Estonia / Latvia / Lithuania).  The reference forecast is IFS-single run
20 Aug 2026 12 UTC, valid for the 42-66 h accumulation, i.e. the 24 h total
precipitation ending 23 Aug 2026 06 UTC.  This study compares three models
(IFS-control, AIFS-single, hybrid j1l8) at that valid window and across a
range of initialisation lead times, verified against STVL ``tp24`` gauges.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ROOT = REPO_ROOT / "analysis"

# Fixed 24 h valid window (the reported 42-66 h accumulation of the 20 Aug 12z run).
WINDOW_END = dt.datetime(2026, 8, 23, 6)  # tp24 obs valid time (24 h ending here)
WINDOW_START = WINDOW_END - dt.timedelta(hours=24)  # 2026-08-22 06 UTC


@dataclass(frozen=True)
class ModelSpec:
    """MARS identification of one forecast model."""

    key: str  # short id used in filenames
    label: str  # human-readable label for plots
    mars_class: str
    stream: str
    mars_type: str
    expver: str
    param: str
    cycles: tuple[str, ...]  # initialisation cycles available (UTC, "HHMM")


MODELS: tuple[ModelSpec, ...] = (
    ModelSpec("ifs", "IFS-control", "od", "oper", "fc", "0001", "228", ("0000", "1200")),
    ModelSpec("aifs", "AIFS-single", "ai", "oper", "fc", "0001", "228", ("0000", "1200")),
    ModelSpec("j1l8", "Hybrid (j1l8)", "rd", "oper", "fc", "j1l8", "228.128", ("0000",)),
)

# IFS at 4.4 km resolution (research experiment), used in place of the hybrid.
MODELS_IEKM: tuple[ModelSpec, ...] = (
    MODELS[0],
    MODELS[1],
    ModelSpec("iekm", "DestinE 4.4km (iekm)", "rd", "oper", "fc", "iekm", "228.128", ("0000",)),
)


@dataclass
class PrecipConfig:
    """Parameters for the Baltic precipitation case study."""

    # --- Region (Baltic states + area further north the model rained on) ----
    north: float = 63.0
    west: float = 19.0
    south: float = 53.0
    east: float = 31.0

    # --- Fixed valid window -------------------------------------------------
    window_start: dt.datetime = WINDOW_START
    window_end: dt.datetime = WINDOW_END

    # --- Predictability sweep: earliest/latest initialisation to sample -----
    lead_base_start: dt.datetime = dt.datetime(2026, 8, 17, 0)
    lead_base_end: dt.datetime = dt.datetime(2026, 8, 22, 0)

    # --- Observations (STVL / VINO tp24) ------------------------------------
    vino_path: str = "/home/moz/bin/vino_getgeo"
    obs_sources: str = "synop"
    obs_parameter: str = "tp"
    obs_period: int = 24
    obs_time: str = "06"  # 24 h accumulation valid at 06 UTC (matches the 42-66 h window)
    obs_missing_value: float = 3e38

    # --- Paths --------------------------------------------------------------
    data_dir: Path = field(default=ANALYSIS_ROOT / "data")
    figures_dir: Path = field(default=ANALYSIS_ROOT / "figures")
    results_dir: Path = field(default=ANALYSIS_ROOT / "results")
    helpers_pkg_dir: Path = field(default=REPO_ROOT / "clickable_timeseries")

    def __post_init__(self) -> None:
        for d in (self.data_dir, self.figures_dir, self.results_dir):
            d.mkdir(parents=True, exist_ok=True)

    # --- Derived helpers ----------------------------------------------------
    @property
    def area(self) -> list[float]:
        """MARS area list [North, West, South, East]."""
        return [self.north, self.west, self.south, self.east]

    @property
    def forecast_cache_dir(self) -> Path:
        d = self.data_dir / "forecasts_precip"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def obs_dir(self) -> Path:
        return self.data_dir / "observations" / "tp" / f"tp_{self.obs_period}h"

    def steps_for(self, base: dt.datetime) -> tuple[int, int]:
        """(step_start, step_end) bracketing the fixed 24 h window for a base time."""
        start = int((self.window_start - base).total_seconds() // 3600)
        return start, start + 24

    def base_times(self, spec: ModelSpec) -> list[dt.datetime]:
        """Initialisation times (for a model's cycles) that bracket the window."""
        out: list[dt.datetime] = []
        day = self.lead_base_start.date()
        end_day = self.lead_base_end.date()
        while day <= end_day:
            for cyc in spec.cycles:
                b = dt.datetime.combine(day, dt.time(int(cyc[:2])))
                s0, _ = self.steps_for(b)
                if 0 <= s0 and self.lead_base_start <= b <= self.lead_base_end:
                    out.append(b)
            day += dt.timedelta(days=1)
        return sorted(out)

    def in_bbox(self, lat: float, lon: float) -> bool:
        return self.south <= lat <= self.north and self.west <= lon <= self.east
