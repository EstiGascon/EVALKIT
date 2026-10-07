"""Retrieval of total precipitation for the three models and derivation of the
fixed 24 h accumulation over the case-study window.

For a given model and initialisation time, the 24 h total is the difference of
the accumulated ``tp`` field at the two forecast steps that bracket the fixed
valid window (``window_start`` .. ``window_end``).  Values are converted to mm
regardless of the archived units (IFS stores metres, AIFS stores kg m-2).
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

import earthkit.data as ekd
import numpy as np

from precip_config import MODELS, ModelSpec, PrecipConfig


@dataclass
class PrecipField:
    """A 24 h precipitation field (mm) at the model's native resolution."""

    model: str  # model key
    label: str  # model label
    base: dt.datetime  # initialisation time
    step_start: int
    step_end: int
    lats: np.ndarray  # 1-D point latitudes (native grid, area-cropped)
    lons: np.ndarray  # 1-D point longitudes
    tp24: np.ndarray  # 1-D 24 h accumulation (mm)

    @property
    def lead(self) -> int:
        """Lead time (h) to the *end* of the 24 h accumulation window.

        The forecast verifies at the end of the accumulation period, so this is
        the lead time reported in plot titles (e.g. the 20 Aug 12Z run of the
        42-66 h window has a lead of 66 h, not 42 h).
        """
        return self.step_end


def _as_fieldlist(ds):
    """Normalise an earthkit source to an indexable/iterable field list.

    earthkit-data >= 1.0 returns a lazy ``GribData`` wrapper from
    ``from_source`` that is neither ``len()``-able nor iterable until it is
    materialised with ``to_fieldlist()``; older versions already returned a
    field list, so fall through unchanged there.
    """
    return ds.to_fieldlist() if hasattr(ds, "to_fieldlist") else ds


def _field_latlon(field) -> tuple[np.ndarray, np.ndarray]:
    """1-D (lat, lon) point arrays for one field, across earthkit versions.

    earthkit-data < 1.0 exposed ``Field.to_latlon()``; 1.0 replaced it with
    ``Field.data("lat"/"lon")``.
    """
    if hasattr(field, "to_latlon"):
        ll = field.to_latlon(flatten=True)
        return np.asarray(ll["lat"]).ravel(), np.asarray(ll["lon"]).ravel()
    return (
        np.asarray(field.data("lat", flatten=True)).ravel(),
        np.asarray(field.data("lon", flatten=True)).ravel(),
    )


def _save_fieldlist(ds, path: str) -> None:
    """Write a field list to ``path`` as GRIB, across earthkit versions.

    earthkit-data < 1.0 provided ``FieldList.save(path)``; 1.0 replaced it with
    ``FieldList.to_target("file", path)``.
    """
    if hasattr(ds, "save"):
        ds.save(path)
    else:
        ds.to_target("file", path)


def _field_units(field, default: str) -> str:
    """GRIB ``units`` for one field, falling back to ``default`` if absent.

    earthkit-data 1.0 dropped the ``default=`` kwarg on ``Field.metadata``.
    """
    try:
        u = field.metadata("units", default=default)
    except TypeError:
        try:
            u = field.metadata("units")
        except Exception:  # noqa: BLE001
            u = default
    except Exception:  # noqa: BLE001
        u = default
    return u or default


def _set_mars_tmpdir() -> str | None:
    orig = os.environ.get("TMPDIR")
    tmp = f"/tmp/mars_tmp_{os.environ.get('USER', 'evalkit')}"
    os.makedirs(tmp, exist_ok=True)
    os.environ["TMPDIR"] = tmp
    return orig


def _restore_tmpdir(orig: str | None) -> None:
    if orig is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = orig


def _cache_path(cfg: PrecipConfig, spec: ModelSpec, base: dt.datetime, s0: int, s1: int):
    return cfg.forecast_cache_dir / f"{spec.key}_tp_{base:%Y%m%d%H}_{s0}_{s1}.grib"


def _to_mm(values: np.ndarray, units: str) -> np.ndarray:
    """Convert an accumulated-precip field to mm based on its GRIB units."""
    u = (units or "").lower().strip()
    if u in {"m", "metre", "meter", "metres", "meters"}:
        return values * 1000.0
    # kg m-2 == mm of water; already in mm otherwise.
    return values


def retrieve_tp(
    cfg: PrecipConfig, spec: ModelSpec, base: dt.datetime, force: bool = False
):
    """Retrieve the two bracketing tp steps for one model/initialisation."""
    s0, s1 = cfg.steps_for(base)
    cache = _cache_path(cfg, spec, base, s0, s1)
    if cache.exists() and not force:
        ds = _as_fieldlist(ekd.from_source("file", str(cache)))
        if len(ds) >= 2:
            return ds

    request = {
        "class": spec.mars_class,
        "stream": spec.stream,
        "type": spec.mars_type,
        "expver": spec.expver,
        "levtype": "sfc",
        "param": spec.param,
        "date": base.strftime("%Y%m%d"),
        "time": base.strftime("%H%M"),
        "step": f"{s0}/{s1}",
        "area": cfg.area,
        "expect": "any",
    }
    orig = _set_mars_tmpdir()
    try:
        ds = _as_fieldlist(ekd.from_source("mars", **request))
    except Exception as exc:  # noqa: BLE001
        print(f"  \u2717 MARS failed {spec.key} {base:%Y-%m-%d %HZ}: {exc}")
        _restore_tmpdir(orig)
        return None
    finally:
        _restore_tmpdir(orig)

    if len(ds) < 2:
        print(f"  \u26a0 {spec.key} {base:%Y-%m-%d %HZ}: {len(ds)} fields (need 2)")
        return None
    _save_fieldlist(ds, str(cache))
    return ds


def tp24_field(
    cfg: PrecipConfig, spec: ModelSpec, base: dt.datetime, force: bool = False
) -> PrecipField | None:
    """Retrieve and derive the 24 h precipitation field for one forecast."""
    ds = retrieve_tp(cfg, spec, base, force=force)
    if ds is None:
        return None
    s0, s1 = cfg.steps_for(base)

    by_step: dict[int, np.ndarray] = {}
    units = "m"
    lats, lons = _field_latlon(ds[0])
    for fdln in ds:
        step = int(fdln.metadata("step"))
        by_step[step] = np.asarray(fdln.to_numpy()).ravel()
        units = _field_units(fdln, units)

    if s0 not in by_step or s1 not in by_step:
        print(f"  \u26a0 {spec.key} {base:%Y-%m-%d %HZ}: missing step {s0} or {s1}")
        return None

    acc = _to_mm(by_step[s1] - by_step[s0], units)
    acc = np.clip(acc, 0.0, None)  # guard tiny negative round-off
    return PrecipField(
        model=spec.key, label=spec.label, base=base,
        step_start=s0, step_end=s1, lats=lats, lons=lons, tp24=acc,
    )


def load_predictability(
    cfg: PrecipConfig, spec: ModelSpec, force: bool = False
) -> list[PrecipField]:
    """All available lead-time forecasts of the fixed window for one model."""
    out: list[PrecipField] = []
    for base in cfg.base_times(spec):
        fld = tp24_field(cfg, spec, base, force=force)
        if fld is None:
            continue
        out.append(fld)
        print(f"  \u2713 {spec.label} {base:%Y-%m-%d %HZ}  lead {fld.lead:>3}h  "
              f"max {fld.tp24.max():.1f} mm")
    return out


def load_event_forecasts(
    cfg: PrecipConfig, reported_base: dt.datetime, models: tuple[ModelSpec, ...] = MODELS,
    force: bool = False,
) -> dict[str, PrecipField]:
    """One forecast per model targeting the reported window.

    Each model uses the run whose lead time (to the window start) is closest to
    the reported forecast's lead. This matters for 00 UTC-only research models
    (e.g. the hybrid j1l8 or the iekm 4.4 km run), whose archive may not cover
    every date, so their closest-lead 'event' forecast can end up at a longer
    lead than IFS-control / AIFS-single.
    """
    target_lead, _ = cfg.steps_for(reported_base)
    out: dict[str, PrecipField] = {}
    for spec in models:
        candidates = sorted(cfg.base_times(spec), key=lambda b: abs(cfg.steps_for(b)[0] - target_lead))
        for base in candidates:
            fld = tp24_field(cfg, spec, base, force=force)
            if fld is not None:
                out[spec.key] = fld
                print(f"  \u2713 {spec.label} event run {base:%Y-%m-%d %HZ}  "
                      f"lead {fld.lead}h  max {fld.tp24.max():.1f} mm")
                break
    return out


def load_fixed_lead_forecasts(
    cfg: PrecipConfig, lead_hours: int, models: tuple[ModelSpec, ...] = MODELS,
    force: bool = False,
) -> dict[str, PrecipField]:
    """One forecast per model, all initialised at the same lead time to the window.

    Unlike :func:`load_event_forecasts` (which lets each model pick its closest
    available lead), this fixes the lead time so every model is compared at
    exactly the same forecast horizon.  ``lead_hours`` is the lead to the *end*
    of the 24 h accumulation window (the forecast's valid time).
    """
    base = cfg.window_end - dt.timedelta(hours=lead_hours)
    out: dict[str, PrecipField] = {}
    for spec in models:
        if base.strftime("%H%M") not in spec.cycles:
            print(f"  \u26a0 {spec.label}: {base:%H}Z is not a valid cycle for this model")
            continue
        fld = tp24_field(cfg, spec, base, force=force)
        if fld is not None:
            out[spec.key] = fld
            print(f"  \u2713 {spec.label} fixed-lead run {base:%Y-%m-%d %HZ}  "
                  f"lead {fld.lead}h  max {fld.tp24.max():.1f} mm")
    return out
