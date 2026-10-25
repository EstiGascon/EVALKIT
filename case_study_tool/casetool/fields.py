"""Derive evaluated fields (precipitation, wind speed, orography) from GRIB files."""

from __future__ import annotations

from dataclasses import dataclass

import earthkit.data as ekd
import numpy as np

G = 9.80665


@dataclass
class Field:
    """A derived 2-D field at the model's native grid points."""

    model_key: str
    label: str
    expver: str
    lead: int | None
    base: object  # datetime of the run
    steps: list[int]
    grid: str
    lats: np.ndarray
    lons: np.ndarray
    values: np.ndarray
    lsm: np.ndarray | None = None


def _fieldlist(path: str):
    src = ekd.from_source("file", path)
    return src.to_fieldlist() if hasattr(src, "to_fieldlist") else src


def _latlon(field) -> tuple[np.ndarray, np.ndarray]:
    if hasattr(field, "to_latlon"):
        ll = field.to_latlon(flatten=True)
        lats, lons = np.asarray(ll["lat"]).ravel(), np.asarray(ll["lon"]).ravel()
    else:
        lats = np.asarray(field.data("lat", flatten=True)).ravel()
        lons = np.asarray(field.data("lon", flatten=True)).ravel()
    return lats, (lons + 180.0) % 360.0 - 180.0


def _meta(field, key, default=None):
    try:
        value = field.metadata(key)
    except Exception:  # noqa: BLE001
        return default
    return default if value is None else value


def _by_name_step(ds) -> dict[tuple[str, int], np.ndarray]:
    out = {}
    for fld in ds:
        out[(_meta(fld, "shortName"), int(_meta(fld, "step", 0)))] = np.asarray(
            fld.to_numpy()
        ).ravel()
    return out


def _to_mm(values: np.ndarray, units: str) -> np.ndarray:
    if (units or "").strip().lower() in {"m", "metre", "meter", "metres", "meters"}:
        return values * 1000.0
    return values  # kg m-2 == mm


def precipitation(path: str, s0: int, s1: int) -> tuple[np.ndarray, ...]:
    """Return (lats, lons, accumulation in mm between steps s0 and s1, grid)."""
    ds = _fieldlist(path)
    data = {}
    units = "m"
    for fld in ds:
        data[int(_meta(fld, "step", 0))] = np.asarray(fld.to_numpy()).ravel()
        units = _meta(fld, "units", units)
    if s1 not in data:
        raise ValueError(f"step {s1} missing in {path}")
    # tp at step 0 is zero by definition and may be absent from the archive.
    acc = data[s1] - data.get(s0, 0.0)
    lats, lons = _latlon(ds[0])
    return (
        lats,
        lons,
        np.clip(_to_mm(acc, units), 0.0, None),
        _meta(ds[0], "gridName", ""),
    )


def wind_speed(path: str, steps: list[int], statistic: str) -> tuple[np.ndarray, ...]:
    """Return (lats, lons, speed statistic over ``steps``, grid, n_steps used)."""
    ds = _fieldlist(path)
    comp = _by_name_step(ds)
    speeds = [
        np.hypot(comp[("10u", s)], comp[("10v", s)])
        for s in steps
        if ("10u", s) in comp and ("10v", s) in comp
    ]
    if not speeds:
        raise ValueError(f"no 10u/10v pairs for steps {steps} in {path}")
    stack = np.vstack(speeds)
    value = {
        "instant": stack[-1],
        "max": stack.max(axis=0),
        "mean": stack.mean(axis=0),
    }[statistic]
    lats, lons = _latlon(ds[0])
    return lats, lons, value, _meta(ds[0], "gridName", ""), len(speeds)


def orography(path: str) -> tuple[np.ndarray, ...]:
    """Return (lats, lons, orography in m, land-sea mask, grid)."""
    ds = _fieldlist(path)
    comp = {name: v for (name, _step), v in _by_name_step(ds).items()}
    if "z" not in comp:
        raise ValueError(f"no surface geopotential in {path}")
    lats, lons = _latlon(ds[0])
    lsm = comp.get("lsm")
    return lats, lons, comp["z"] / G, lsm, _meta(ds[0], "gridName", "")
