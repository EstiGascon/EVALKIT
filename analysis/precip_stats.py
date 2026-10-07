"""Quantitative diagnostics for the precipitation misplacement study.

Two complementary views:

* point verification of each forecast against the tp24 gauges (bias, RMSE,
  correlation) via nearest-grid-point matching, and
* a precipitation-mass-weighted mean latitude that captures *how far north* the
  heavy rain was placed, for gauges and for each forecast field.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from precip_forecasts import PrecipField


def _nearest_values(lats2d, lons2d, values2d, obs: pd.DataFrame) -> np.ndarray:
    """Sample a gridded field at station locations (nearest grid point)."""
    glat = lats2d.ravel()
    glon = lons2d.ravel()
    gval = values2d.ravel()
    out = np.empty(len(obs), dtype=float)
    olat = obs["lat"].to_numpy()
    olon = obs["lon"].to_numpy()
    for i in range(len(obs)):
        d = (glat - olat[i]) ** 2 + (glon - olon[i]) ** 2
        out[i] = gval[int(d.argmin())]
    return out


def station_scores(field: PrecipField, obs: pd.DataFrame) -> pd.DataFrame:
    """Match one forecast field to gauges; return per-station fc/obs/error."""
    fc = _nearest_values(field.lats, field.lons, field.tp24, obs)
    df = obs[["stnid", "lat", "lon", "obs"]].copy()
    df["fc"] = fc
    df["error"] = df["fc"] - df["obs"]
    return df


def score_summary(field: PrecipField, obs: pd.DataFrame) -> dict:
    """Scalar verification scores of one forecast against the gauges."""
    df = station_scores(field, obs)
    err = df["error"].to_numpy()
    corr = float(np.corrcoef(df["fc"], df["obs"])[0, 1]) if len(df) > 2 else np.nan
    return {
        "model": field.model,
        "label": field.label,
        "base": field.base,
        "lead": field.lead,
        "n": len(df),
        "bias": float(err.mean()),
        "rmse": float(np.sqrt((err**2).mean())),
        "corr": corr,
    }


def mass_weighted_lat(
    lats: np.ndarray, lons: np.ndarray, values: np.ndarray, threshold: float,
    lon_min: float, lon_max: float,
) -> float:
    """Precipitation-mass-weighted mean latitude above a rain threshold.

    Restricting to a longitude band keeps the metric focused on the corridor
    where the event occurred so a higher value literally means 'further north'.
    """
    lat = np.asarray(lats).ravel()
    lon = np.asarray(lons).ravel()
    val = np.asarray(values).ravel()
    m = (lon >= lon_min) & (lon <= lon_max)
    w = np.clip(val[m] - threshold, 0.0, None)
    lat = lat[m]
    if w.sum() <= 0:
        return np.nan
    return float((w * lat).sum() / w.sum())


def obs_mass_weighted_lat(
    obs: pd.DataFrame, threshold: float, lon_min: float, lon_max: float
) -> float:
    """Mass-weighted mean latitude of the gauge rainfall in the longitude band."""
    m = (obs["lon"] >= lon_min) & (obs["lon"] <= lon_max)
    sub = obs.loc[m]
    w = np.clip(sub["obs"].to_numpy() - threshold, 0.0, None)
    if w.sum() <= 0:
        return np.nan
    return float((w * sub["lat"].to_numpy()).sum() / w.sum())
