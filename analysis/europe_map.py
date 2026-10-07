"""Europe-wide mean 10 m wind-speed forecast-error map for the same period.

The STVL observations already cover all of Europe (they were exported globally),
so only Europe-wide IFS-control forecasts are retrieved here. Forecasts use a
coarser 0.25 deg grid and short lead times (<= 24 h) to keep the MARS volume
small; each run is cached under ``data/forecasts_europe/`` so re-runs are cheap.

Run:
    python europe_map.py            # retrieve (if needed) + build maps
    python europe_map.py --test     # retrieve a single run and stop
"""

from __future__ import annotations

import sys

import earthkit.data as ekd
import forecasts as F
import observations as O
import plots as P
import verification as V
from config import StudyConfig

# Europe domain (N, W, S, E) and coarse grid; short leads only.
EU = StudyConfig(
    north=72.0,
    west=-25.0,
    south=34.0,
    east=45.0,
    grid=(0.25, 0.25),
    steps=tuple(range(0, 25, 3)),
)
CACHE = EU.data_dir / "forecasts_europe"


def retrieve_eu(day, cycle):
    """Retrieve one Europe run, cached separately from the small-box GRIBs."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / f"eu_10uv_{day:%Y%m%d}_{cycle}.grib"
    if cache.exists():
        ds = ekd.from_source("file", str(cache))
        if len(ds) > 0:
            return ds
    request = {
        "class": EU.mars_class,
        "stream": EU.mars_stream,
        "expver": EU.mars_expver,
        "type": EU.mars_type,
        "levtype": EU.mars_levtype,
        "param": f"{EU.param_u}/{EU.param_v}",
        "date": day.strftime("%Y%m%d"),
        "time": cycle,
        "step": "/".join(str(s) for s in EU.steps),
        "grid": list(EU.grid),
        "area": EU.area,
        "expect": "any",
    }
    orig = F._set_mars_tmpdir()
    try:
        ds = ekd.from_source("mars", **request)
    finally:
        F._restore_tmpdir(orig)
    if len(ds) == 0:
        print(f"  ⚠ 0 fields for {day} {cycle}")
        return None
    ds.save(str(cache))
    return ds


def main(test: bool = False) -> None:
    """Retrieve Europe forecasts, match to observations and draw bias maps."""
    dates = EU.init_dates()
    cycles = EU.cycles
    forecasts = []
    for day in dates:
        for cycle in cycles:
            ds = retrieve_eu(day, cycle)
            if ds is None:
                continue
            ff = F.derive_wind_speed(ds, day, cycle)
            if ff is not None:
                forecasts.append(ff)
                print(f"  ✓ {day} {cycle}: {len(ff.steps)} steps, {ff.lats.size} pts")
            if test:
                print("Test run complete.")
                return

    obs = O.load_observations(EU)
    pairs = V.build_matched_pairs(EU, forecasts, obs)
    pairs.to_parquet(EU.results_dir / "matched_pairs_europe.parquet")

    station_all = V.scores_by_station(pairs, event_only=False)
    station_ev = V.scores_by_station(pairs, event_only=True)
    outs = [
        P.plot_station_bias_map(
            EU,
            station_all,
            "Mean 10 m wind error — Europe, full period (lead ≤ 24 h)",
            "map_bias_europe_all.png",
            s=10,
        ),
        P.plot_station_bias_map(
            EU,
            station_ev,
            "Mean 10 m wind error — Europe, event days (lead ≤ 24 h)",
            "map_bias_europe_event.png",
            s=10,
        ),
        P.plot_bias_event_vs_baseline(
            EU, pairs, "map_bias_europe_event_vs_baseline.png", 24, s=7
        ),
    ]
    print("\nFigures written:")
    for p in outs:
        print(f"  {p}")


if __name__ == "__main__":
    main(test="--test" in sys.argv)
