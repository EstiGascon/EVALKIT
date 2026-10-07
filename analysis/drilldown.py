"""Case-level drill-down into the reported event days (focus on 15 Aug 2026).

Reads the matched forecast/observation pairs produced by ``run_analysis.py``
and answers the follow-up question: *which individual stations and times drive
the event-day under-forecast, and is it a coherent hotspot or scattered
misses?* Writes worst-case tables to ``results/`` and guidance maps to
``figures/``.

Run:
    python drilldown.py
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

import plots
from config import StudyConfig

FOCUS_DAY = dt.date(2026, 8, 15)
MAX_LEAD = 24
TOP_N = 20


def _worst_individual_misses(pairs: pd.DataFrame, day: dt.date) -> pd.DataFrame:
    """Largest single under-forecasts (most negative errors) on a given day."""
    sub = pairs[(pairs["valid_day"] == day) & (pairs["lead_hours"] <= MAX_LEAD)]
    cols = ["stnid", "lat", "lon", "valid_time", "lead_hours", "obs", "fc", "error"]
    return sub.nsmallest(TOP_N, "error")[cols].reset_index(drop=True)


def _worst_stations(pairs: pd.DataFrame, day: dt.date) -> pd.DataFrame:
    """Per-station event-day statistics ranked by mean under-forecast."""
    sub = pairs[(pairs["valid_day"] == day) & (pairs["lead_hours"] <= MAX_LEAD)]
    g = sub.groupby("stnid").agg(
        lat=("lat", "first"),
        lon=("lon", "first"),
        n=("error", "size"),
        mean_obs=("obs", "mean"),
        mean_fc=("fc", "mean"),
        bias=("error", "mean"),
        worst_error=("error", "min"),
        frac_under=("error", lambda e: float((e < 0).mean())),
    )
    return g.sort_values("bias").reset_index()


def _worst_valid_time(pairs: pd.DataFrame, day: dt.date) -> pd.Timestamp:
    """Valid time on ``day`` with the most negative domain-mean error."""
    sub = pairs[(pairs["valid_day"] == day) & (pairs["lead_hours"] <= MAX_LEAD)]
    by_time = sub.groupby("valid_time")["error"].mean()
    return by_time.idxmin()


def main() -> None:
    cfg = StudyConfig()
    pairs = pd.read_parquet(cfg.results_dir / "matched_pairs.parquet")
    pairs["valid_day"] = pd.to_datetime(pairs["valid_time"]).dt.date

    # ---- Worst individual misses on the focus day --------------------------
    misses = _worst_individual_misses(pairs, FOCUS_DAY)
    misses.to_csv(cfg.results_dir / "worst_misses_20260815.csv", index=False)
    print(f"\n=== Top {TOP_N} single under-forecasts on {FOCUS_DAY} (lead ≤ {MAX_LEAD} h) ===")
    print(misses.to_string(index=False))

    # ---- Worst stations on the focus day -----------------------------------
    stations = _worst_stations(pairs, FOCUS_DAY)
    stations.to_csv(cfg.results_dir / "worst_stations_20260815.csv", index=False)
    print(f"\n=== Worst 15 stations by mean bias on {FOCUS_DAY} ===")
    print(stations.head(15).round(2).to_string(index=False))

    # ---- Worst valid time (peak miss) --------------------------------------
    peak_time = _worst_valid_time(pairs, FOCUS_DAY)
    print(f"\nPeak domain-mean under-forecast on {FOCUS_DAY}: {peak_time} UTC")

    # ---- Guidance maps ------------------------------------------------------
    outputs = [
        plots.plot_event_day_bias_maps(cfg, pairs, "map_bias_by_event_day.png", MAX_LEAD),
        plots.plot_bias_event_vs_baseline(cfg, pairs, "map_bias_event_vs_baseline.png", MAX_LEAD),
        plots.plot_under_forecast_frequency(cfg, pairs, "map_under_forecast_frequency.png", MAX_LEAD),
        plots.plot_station_bias_map(
            cfg,
            _worst_stations(pairs, FOCUS_DAY).rename(columns={"bias": "bias"}),
            f"Per-station 10 m wind bias on {FOCUS_DAY} (lead ≤ {MAX_LEAD} h)",
            "map_bias_20260815.png",
        ),
        plots.plot_snapshot(cfg, pairs, peak_time, "map_snapshot_20260815_peak.png"),
    ]
    print("\nFigures written:")
    for p in outputs:
        print(f"  {p}")


if __name__ == "__main__":
    main()
