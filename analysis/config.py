"""Configuration for the HRES 10 m wind-speed verification study.

This study verifies ECMWF HRES (IFS-single) 10 m wind speed against STVL
surface observations over north-eastern France (Hauts-de-France + Grand Est)
to assess whether the large under-forecasts reported by RTE on 3, 4 and
15 August 2026 are systematic or event-specific.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

# Repository root (two levels up from this file: analysis/config.py -> repo root)
REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ROOT = REPO_ROOT / "analysis"


@dataclass
class StudyConfig:
    """All tunable parameters for the wind-speed verification study."""

    # --- Region of interest (Hauts-de-France + Grand Est proxy box) ---------
    # MARS "area" order is [North, West, South, East].
    north: float = 51.2
    west: float = 1.4
    south: float = 47.4
    east: float = 8.3

    # --- Forecast model -----------------------------------------------------
    # HRES == IFS-single (operational high-resolution deterministic forecast).
    mars_class: str = "od"
    mars_stream: str = "oper"
    mars_type: str = "fc"
    mars_levtype: str = "sfc"
    mars_expver: str = "0001"
    # 10 m wind components (u=165, v=166) -> wind speed = sqrt(u^2 + v^2).
    param_u: str = "165"
    param_v: str = "166"
    # Retrieval grid (regular lat/lon degrees).
    grid: tuple[float, float] = (0.1, 0.1)
    # Forecast cycles (UTC) to sample.
    cycles: tuple[str, ...] = ("0000", "1200")
    # Forecast steps (hours) to retrieve for each cycle. 3-hourly out to 72 h
    # matches the 3-hourly SYNOP observation times and spans the reported
    # forecast-issue lead times.
    steps: tuple[int, ...] = tuple(range(0, 73, 3))

    # --- Time window --------------------------------------------------------
    # Initialisation dates span a baseline period around the three event days
    # so systematic behaviour can be separated from isolated events.
    init_start: dt.date = dt.date(2026, 7, 28)
    init_end: dt.date = dt.date(2026, 8, 15)
    # Valid days flagged as the reported problem events.
    event_days: tuple[dt.date, ...] = (
        dt.date(2026, 8, 3),
        dt.date(2026, 8, 4),
        dt.date(2026, 8, 15),
    )

    # --- Observations (STVL / VINO) -----------------------------------------
    vino_path: str = "/home/moz/bin/vino_getgeo"
    obs_sources: str = "synop"
    obs_parameter: str = "10ff"
    obs_times: str = "0 3 6 9 12 15 18 21"
    # Missing-value sentinel written by the STVL .geo export.
    obs_missing_value: float = 3e38

    # --- Paths --------------------------------------------------------------
    data_dir: Path = field(default=ANALYSIS_ROOT / "data")
    figures_dir: Path = field(default=ANALYSIS_ROOT / "figures")
    results_dir: Path = field(default=ANALYSIS_ROOT / "results")

    # Import path for the clickable_timeseries helpers (ObservationsRetriever).
    helpers_pkg_dir: Path = field(default=REPO_ROOT / "clickable_timeseries")

    def __post_init__(self) -> None:
        """Create output directories."""
        for d in (self.data_dir, self.figures_dir, self.results_dir):
            d.mkdir(parents=True, exist_ok=True)

    # --- Derived helpers ----------------------------------------------------
    @property
    def obs_dir(self) -> Path:
        """Directory where STVL 10ff .geo files are stored."""
        return (
            self.data_dir
            / "observations"
            / self.obs_parameter
            / f"{self.obs_parameter}_3h"
        )

    @property
    def forecast_cache_dir(self) -> Path:
        """Directory where retrieved HRES GRIB files are cached."""
        d = self.data_dir / "forecasts"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def area(self) -> list[float]:
        """MARS area list [North, West, South, East]."""
        return [self.north, self.west, self.south, self.east]

    def init_dates(self) -> list[dt.date]:
        """All initialisation dates in the study window (inclusive)."""
        n = (self.init_end - self.init_start).days
        return [self.init_start + dt.timedelta(days=i) for i in range(n + 1)]

    def in_bbox(self, lat: float, lon: float) -> bool:
        """Return True if a station coordinate falls inside the study box."""
        return self.south <= lat <= self.north and self.west <= lon <= self.east

    def is_event_day(self, day: dt.date) -> bool:
        """Return True if the given calendar day is a reported event day."""
        return day in set(self.event_days)
