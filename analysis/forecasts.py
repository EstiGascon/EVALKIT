"""Retrieval of HRES (IFS-single) 10 m wind components and derivation of speed.

10 m wind speed is computed from the u (param 165) and v (param 166)
components as ``sqrt(u^2 + v^2)``.  Retrieved GRIB is cached on disk so
re-runs of the study do not re-hit MARS.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

import earthkit.data as ekd
import numpy as np
from config import StudyConfig


@dataclass
class ForecastFields:
    """Derived 10 m wind-speed fields for one initialisation (date + cycle).

    Attributes:
        init_time: Forecast reference (initialisation) time, UTC.
        lats: Flattened grid latitudes (shared by all steps).
        lons: Flattened grid longitudes (shared by all steps).
        steps: List of forecast steps (hours).
        speed: Dict mapping step (h) -> flattened wind-speed array (m/s).

    """

    init_time: dt.datetime
    lats: np.ndarray
    lons: np.ndarray
    steps: list[int]
    speed: dict[int, np.ndarray]

    def valid_time(self, step: int) -> dt.datetime:
        """Return the valid time for a given forecast step."""
        return self.init_time + dt.timedelta(hours=step)


def _set_mars_tmpdir(user: str | None = None) -> str | None:
    """Point TMPDIR at local /tmp so MARS's SQLite locking works (Lustre fails)."""
    orig = os.environ.get("TMPDIR")
    tmp = f"/tmp/mars_tmp_{user or os.environ.get('USER', 'evalkit')}"
    os.makedirs(tmp, exist_ok=True)
    os.environ["TMPDIR"] = tmp
    return orig


def _restore_tmpdir(orig: str | None) -> None:
    if orig is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = orig


def _cache_path(cfg: StudyConfig, day: dt.date, cycle: str):
    return cfg.forecast_cache_dir / f"hres_10uv_{day:%Y%m%d}_{cycle}.grib"


def retrieve_forecast(cfg: StudyConfig, day: dt.date, cycle: str, force: bool = False):
    """Retrieve one HRES run's 10 m wind components, using an on-disk cache.

    Args:
        cfg: Study configuration.
        day: Initialisation date.
        cycle: Initialisation cycle, e.g. ``"0000"`` or ``"1200"``.
        force: Re-download even if a cached GRIB exists.

    Returns:
        An earthkit fieldlist, or ``None`` if the retrieval yielded no fields.

    """
    cache = _cache_path(cfg, day, cycle)
    if cache.exists() and not force:
        ds = ekd.from_source("file", str(cache))
        if len(ds) > 0:
            return ds

    request = {
        "class": cfg.mars_class,
        "stream": cfg.mars_stream,
        "expver": cfg.mars_expver,
        "type": cfg.mars_type,
        "levtype": cfg.mars_levtype,
        "param": f"{cfg.param_u}/{cfg.param_v}",
        "date": day.strftime("%Y%m%d"),
        "time": cycle,
        "step": "/".join(str(s) for s in cfg.steps),
        "grid": list(cfg.grid),
        "area": cfg.area,
        "expect": "any",
    }

    orig = _set_mars_tmpdir()
    try:
        ds = ekd.from_source("mars", **request)
    except Exception as exc:  # noqa: BLE001 - report and skip this run
        print(f"  ✗ MARS failed for {day} {cycle}: {exc}")
        _restore_tmpdir(orig)
        return None
    finally:
        _restore_tmpdir(orig)

    if len(ds) == 0:
        print(f"  ⚠ 0 fields for {day} {cycle}")
        return None

    ds.save(str(cache))
    return ds


def derive_wind_speed(ds, day: dt.date, cycle: str) -> ForecastFields | None:
    """Group u/v components by step and derive 10 m wind speed.

    Args:
        ds: earthkit fieldlist containing 10u and 10v fields.
        day: Initialisation date.
        cycle: Initialisation cycle ("HHMM").

    Returns:
        A :class:`ForecastFields` object, or ``None`` if no complete u/v pair
        was found.

    """
    init_time = dt.datetime.strptime(f"{day:%Y%m%d}{cycle}", "%Y%m%d%H%M")

    latlon = ds[0].to_latlon()
    lats = np.asarray(latlon["lat"]).flatten()
    lons = np.asarray(latlon["lon"]).flatten()

    components: dict[int, dict[str, np.ndarray]] = {}
    for field in ds:
        step = int(field.metadata("step"))
        short = field.metadata("shortName")
        components.setdefault(step, {})[short] = np.asarray(field.values).flatten()

    speed: dict[int, np.ndarray] = {}
    for step, comp in components.items():
        u = comp.get("10u")
        v = comp.get("10v")
        if u is None or v is None:
            continue
        speed[step] = np.sqrt(u**2 + v**2)

    if not speed:
        return None

    return ForecastFields(
        init_time=init_time,
        lats=lats,
        lons=lons,
        steps=sorted(speed),
        speed=speed,
    )


def load_all_forecasts(cfg: StudyConfig, force: bool = False) -> list[ForecastFields]:
    """Retrieve and derive wind speed for every init date/cycle in the window."""
    out: list[ForecastFields] = []
    for day in cfg.init_dates():
        for cycle in cfg.cycles:
            ds = retrieve_forecast(cfg, day, cycle, force=force)
            if ds is None:
                continue
            ff = derive_wind_speed(ds, day, cycle)
            if ff is None:
                print(f"  ⚠ No u/v pair for {day} {cycle}")
                continue
            out.append(ff)
            print(f"  ✓ {day} {cycle}: {len(ff.steps)} steps")
    print(f"✓ Derived wind speed for {len(out)} HRES runs")
    return out
