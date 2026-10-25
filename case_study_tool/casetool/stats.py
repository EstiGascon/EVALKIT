"""Verification statistics: field summaries and station-based scores."""

from __future__ import annotations

import numpy as np
import pandas as pd
import shapely

try:
    from scipy.spatial import cKDTree
except ImportError:  # pragma: no cover
    cKDTree = None


def _xyz(lats, lons) -> np.ndarray:
    la, lo = np.deg2rad(lats), np.deg2rad(lons)
    return np.column_stack(
        [np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]
    )


def nearest(lats, lons, plats, plons) -> np.ndarray:
    """Return indices of the grid points nearest to each (plat, plon)."""
    if cKDTree is not None:
        return cKDTree(_xyz(lats, lons)).query(_xyz(plats, plons))[1]
    coslat = np.cos(np.deg2rad(lats))
    return np.array(
        [
            np.argmin((lats - a) ** 2 + ((lons - b) * coslat) ** 2)
            for a, b in zip(plats, plons, strict=True)
        ]
    )


def field_summary(field, region, region_label: str) -> dict:
    """Return max (with location) and mean of a field inside the region."""
    inside = shapely.contains_xy(region, field.lons, field.lats)
    if field.lsm is not None:
        inside &= field.lsm >= 0.5
    if not inside.any():
        return {"region": region_label, "region_points": 0}
    vals = np.where(inside, field.values, -np.inf)
    i = int(np.argmax(vals))
    return {
        "region": region_label,
        "region_points": int(inside.sum()),
        "region_max": float(field.values[i]),
        "region_max_lat": float(field.lats[i]),
        "region_max_lon": float(field.lons[i]),
        "region_mean": float(field.values[inside].mean()),
    }


def station_scores(field, obs: pd.DataFrame, thresholds) -> tuple[dict, list[dict]]:
    """Return continuous scores and per-threshold categorical scores at stations."""
    if obs.empty:
        return {"n_obs": 0}, []
    idx = nearest(field.lats, field.lons, obs["lat"].to_numpy(), obs["lon"].to_numpy())
    fc = field.values[idx]
    ob = obs["obs"].to_numpy()
    err = fc - ob
    imax = int(np.argmax(ob))
    cont = {
        "n_obs": len(ob),
        "obs_mean": float(ob.mean()),
        "fc_mean_at_obs": float(fc.mean()),
        "bias": float(err.mean()),
        "mae": float(np.abs(err).mean()),
        "rmse": float(np.sqrt((err**2).mean())),
        "corr": float(np.corrcoef(fc, ob)[0, 1])
        if len(ob) > 2 and ob.std() > 0
        else np.nan,
        "obs_max": float(ob[imax]),
        "fc_at_obs_max": float(fc[imax]),
    }
    cats = []
    n = len(ob)
    for t in thresholds:
        o, f = ob >= t, fc >= t
        hits = int((o & f).sum())
        misses = int((o & ~f).sum())
        fa = int((~o & f).sum())
        cn = n - hits - misses - fa
        rand = (hits + misses) * (hits + fa) / n
        denom_ets = hits + misses + fa - rand
        cats.append(
            {
                "threshold": t,
                "n_obs_event": hits + misses,
                "n_fc_event": hits + fa,
                "hits": hits,
                "misses": misses,
                "false_alarms": fa,
                "correct_negatives": cn,
                "pod": hits / (hits + misses) if hits + misses else np.nan,
                "far": fa / (hits + fa) if hits + fa else np.nan,
                "fbi": (hits + fa) / (hits + misses) if hits + misses else np.nan,
                "ets": (hits - rand) / denom_ets if denom_ets else np.nan,
            }
        )
    return cont, cats


def fc_at_stations(field, obs: pd.DataFrame) -> np.ndarray:
    """Return the forecast value at the nearest grid point to each station."""
    idx = nearest(field.lats, field.lons, obs["lat"].to_numpy(), obs["lon"].to_numpy())
    return field.values[idx]
