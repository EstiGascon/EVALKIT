"""Match HRES wind-speed forecasts to STVL observations and compute scores.

For each forecast run, every (step, station) pair is matched to the nearest
grid point and joined to the observation valid at the same time, producing a
long-format table of forecast/observation pairs from which verification
statistics are computed.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from config import StudyConfig
from forecasts import ForecastFields


def _nearest_index_fn(cfg: StudyConfig):
    """Return earthkit's haversine nearest-point function."""
    pkg = str(cfg.helpers_pkg_dir)
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    from earthkit.geo.distance import nearest_point_haversine  # noqa: PLC0415

    return nearest_point_haversine


def build_matched_pairs(
    cfg: StudyConfig, forecasts: list[ForecastFields], obs: pd.DataFrame
) -> pd.DataFrame:
    """Join forecasts and observations into a long table of matched pairs.

    Returns:
        DataFrame with columns: ``stnid, lat, lon, init_time, valid_time,
        lead_hours, fc, obs, error`` where ``error = fc - obs`` (negative =
        under-forecast).
    """
    nearest = _nearest_index_fn(cfg)

    # Unique stations and their coordinates.
    stations = obs.drop_duplicates("stnid")[["stnid", "lat", "lon"]].reset_index(drop=True)

    # Fast observation lookup keyed by (stnid, valid_time).
    obs_lookup = obs.set_index(["stnid", "valid_time"])["obs"].to_dict()

    # Cache nearest grid index per station per grid signature (grid is shared
    # across runs, but guard in case a run has a different shape).
    index_cache: dict[tuple, np.ndarray] = {}

    records: list[dict] = []
    for ff in forecasts:
        grid_key = (ff.lats.shape[0], float(ff.lats[0]), float(ff.lons[0]), float(ff.lats[-1]))
        if grid_key not in index_cache:
            idxs = np.empty(len(stations), dtype=int)
            for i, row in stations.iterrows():
                idx, _dist = nearest([row["lat"], row["lon"]], (ff.lats, ff.lons))
                idxs[i] = int(idx[0])
            index_cache[grid_key] = idxs
        station_idx = index_cache[grid_key]

        for step in ff.steps:
            speed = ff.speed[step]
            valid = ff.valid_time(step)
            for i, row in stations.iterrows():
                key = (row["stnid"], pd.Timestamp(valid))
                obs_val = obs_lookup.get(key)
                if obs_val is None:
                    continue
                fc_val = float(speed[station_idx[i]])
                records.append(
                    {
                        "stnid": row["stnid"],
                        "lat": row["lat"],
                        "lon": row["lon"],
                        "init_time": ff.init_time,
                        "valid_time": valid,
                        "lead_hours": step,
                        "fc": fc_val,
                        "obs": obs_val,
                    }
                )

    pairs = pd.DataFrame.from_records(records)
    if pairs.empty:
        raise ValueError("No forecast/observation matches were produced.")
    pairs["error"] = pairs["fc"] - pairs["obs"]
    pairs["valid_day"] = pairs["valid_time"].dt.date
    pairs["is_event"] = pairs["valid_day"].apply(cfg.is_event_day)
    pairs.sort_values(["valid_time", "stnid", "lead_hours"], inplace=True)
    pairs.reset_index(drop=True, inplace=True)
    print(
        f"✓ Built {len(pairs)} matched forecast/observation pairs "
        f"({pairs['stnid'].nunique()} stations, "
        f"{pairs['is_event'].sum()} event pairs)"
    )
    return pairs


def _scores(df: pd.DataFrame) -> pd.Series:
    """Compute standard verification scores for a set of matched pairs."""
    err = df["error"]
    return pd.Series(
        {
            "n": len(df),
            "bias": err.mean(),
            "mae": err.abs().mean(),
            "rmse": np.sqrt((err**2).mean()),
            "mean_obs": df["obs"].mean(),
            "mean_fc": df["fc"].mean(),
            "corr": df[["fc", "obs"]].corr().iloc[0, 1] if len(df) > 2 else np.nan,
        }
    )


def scores_overall(pairs: pd.DataFrame) -> pd.DataFrame:
    """Overall scores split into event vs baseline periods."""
    rows = {
        "all": _scores(pairs),
        "event": _scores(pairs[pairs["is_event"]]),
        "baseline": _scores(pairs[~pairs["is_event"]]),
    }
    return pd.DataFrame(rows).T


def scores_by_lead(pairs: pd.DataFrame) -> pd.DataFrame:
    """Scores as a function of forecast lead time, event vs baseline."""
    frames = []
    for label, sub in (("event", pairs[pairs["is_event"]]), ("baseline", pairs[~pairs["is_event"]])):
        if sub.empty:
            continue
        g = sub.groupby("lead_hours").apply(_scores, include_groups=False)
        g["period"] = label
        frames.append(g.reset_index())
    return pd.concat(frames, ignore_index=True)


def scores_by_station(pairs: pd.DataFrame, event_only: bool = True) -> pd.DataFrame:
    """Per-station scores (with coordinates) for mapping."""
    sub = pairs[pairs["is_event"]] if event_only else pairs
    g = sub.groupby("stnid").apply(_scores, include_groups=False).reset_index()
    coords = sub.drop_duplicates("stnid")[["stnid", "lat", "lon"]]
    return g.merge(coords, on="stnid", how="left")


def scores_by_valid_day(pairs: pd.DataFrame, max_lead: int = 24) -> pd.DataFrame:
    """Daily scores for short lead times, to show day-to-day behaviour."""
    sub = pairs[pairs["lead_hours"] <= max_lead]
    g = sub.groupby("valid_day").apply(_scores, include_groups=False).reset_index()
    g["is_event"] = g["valid_day"].apply(lambda d: d in set(pairs.loc[pairs["is_event"], "valid_day"]))
    return g


def scores_by_hour(pairs: pd.DataFrame) -> pd.DataFrame:
    """Diurnal bias, event vs baseline (by valid hour of day, UTC)."""
    tmp = pairs.copy()
    tmp["hour"] = tmp["valid_time"].dt.hour
    frames = []
    for label, sub in (("event", tmp[tmp["is_event"]]), ("baseline", tmp[~tmp["is_event"]])):
        if sub.empty:
            continue
        g = sub.groupby("hour").apply(_scores, include_groups=False).reset_index()
        g["period"] = label
        frames.append(g)
    return pd.concat(frames, ignore_index=True)
