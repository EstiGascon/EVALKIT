"""Crete case: model orography with 10 m wind barbs at T+24 h.

Same four models, run and map layout as ``crete_precip.py``.  Orography is the
surface geopotential (step 0) drawn per native grid box; barbs are the 10 m wind
at T+24 h, sampled at the model point nearest to a common regular grid.
"""

from __future__ import annotations

import datetime as dt
import sys

import earthkit.data as ekd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402

from crete_precip import (  # noqa: E402
    AREA,
    BASE,
    CACHE_DIR,
    EXTENT,
    FIG_DIR,
    MODELS,
    _crete_land,
    _gridbox_verts,
    _map_ax,
)
from precip_forecasts import (  # noqa: E402
    _as_fieldlist,
    _field_latlon,
    _restore_tmpdir,
    _save_fieldlist,
    _set_mars_tmpdir,
)

import shapely  # noqa: E402

STEP = 24
VALID = BASE + dt.timedelta(hours=STEP)
G = 9.80665
MS_TO_KT = 1.943844
BARB_SPACING = 0.15  # degrees

OROG_LEVELS = [1, 50, 100, 200, 300, 400, 600, 800, 1000, 1200, 1500, 1800, 2100, 2500]
_terrain = plt.get_cmap("terrain")
OROG_CMAP = ListedColormap(_terrain(np.linspace(0.25, 0.95, len(OROG_LEVELS) - 1)))
OROG_CMAP.set_under("#cfe8f7")  # sea (model lsm < 0.5)
OROG_CMAP.set_over("#ffffff")
OROG_NORM = BoundaryNorm(OROG_LEVELS, ncolors=OROG_CMAP.N)


def retrieve(spec: tuple, force: bool = False):
    """Orography (m, step 0) and 10 m wind (m/s, step STEP) at native resolution."""
    key, _label, mclass, stream, mtype, expver, _param = spec
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"crete_{key}_z_lsm_uv_{BASE:%Y%m%d%H}_{STEP}.grib"
    if cache.exists() and not force:
        ds = _as_fieldlist(ekd.from_source("file", str(cache)))
    else:
        request = {
            "class": mclass, "stream": stream, "type": mtype, "expver": expver,
            "levtype": "sfc", "param": "129/172/165/166",
            "date": BASE.strftime("%Y%m%d"), "time": BASE.strftime("%H%M"),
            "step": f"0/{STEP}", "area": AREA, "expect": "any",
        }
        orig = _set_mars_tmpdir()
        try:
            ds = _as_fieldlist(ekd.from_source("mars", **request))
        except Exception as exc:  # noqa: BLE001
            print(f"  \u2717 MARS failed {key}: {exc}")
            return None
        finally:
            _restore_tmpdir(orig)
        _save_fieldlist(ds, str(cache))

    fields: dict[tuple[str, int], np.ndarray] = {}
    for fld in ds:
        fields[(fld.metadata("shortName"), int(fld.metadata("step")))] = (
            np.asarray(fld.to_numpy()).ravel())
    need = [("z", 0), ("lsm", 0), ("10u", STEP), ("10v", STEP)]
    if any(k not in fields for k in need):
        print(f"  \u26a0 {key}: missing {[k for k in need if k not in fields]}")
        return None
    lats, lons = _field_latlon(ds[0])
    lons = (lons + 180.0) % 360.0 - 180.0
    return {"lats": lats, "lons": lons, "orog": fields[("z", 0)] / G,
            "lsm": fields[("lsm", 0)],
            "u": fields[("10u", STEP)], "v": fields[("10v", STEP)]}


def _barb_points(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Indices of model points nearest to a common regular grid (deduplicated)."""
    w, e, s, n = EXTENT
    gx, gy = np.meshgrid(np.arange(w + BARB_SPACING / 2, e, BARB_SPACING),
                         np.arange(s + BARB_SPACING / 2, n, BARB_SPACING))
    coslat = np.cos(np.deg2rad(lats))
    idx = [np.argmin((lats - y) ** 2 + ((lons - x) * coslat) ** 2)
           for x, y in zip(gx.ravel(), gy.ravel())]
    return np.unique(idx)


def make_figure(results: dict, land) -> str:
    fig = plt.figure(figsize=(18, 10.5))
    pc = None
    for i, spec in enumerate(MODELS):
        ax, kw = _map_ax(fig, 2, 2, i + 1)
        res = results.get(spec[0])
        if res is None:
            ax.set_title(f"{spec[1]} \u2014 unavailable", fontsize=15)
            continue
        lats, lons = res["lats"], res["lons"]
        orog = np.where(res["lsm"] >= 0.5, res["orog"], -1.0)
        pc = PolyCollection(_gridbox_verts(lats, lons), array=orog,
                            cmap=OROG_CMAP, norm=OROG_NORM,
                            edgecolors="face", linewidths=0.1, **kw)
        ax.add_collection(pc)
        b = _barb_points(lats, lons)
        ax.barbs(lons[b], lats[b], res["u"][b] * MS_TO_KT, res["v"][b] * MS_TO_KT,
                 length=5.5, linewidth=0.7, color="k", zorder=8, **kw)
        on_land = shapely.contains_xy(land, lons, lats)
        speed = np.hypot(res["u"], res["v"])
        ax.set_title(
            f"{spec[1]}\nmax orography Crete {res['orog'][on_land].max():.0f} m, "
            f"max 10 m wind {speed.max() * MS_TO_KT:.0f} kt",
            fontsize=15,
        )
    if pc is not None:
        cax = fig.add_axes([0.1, 0.06, 0.8, 0.022])
        cb = fig.colorbar(pc, cax=cax, orientation="horizontal", ticks=OROG_LEVELS,
                          extend="both")
        cb.set_label("Model orography (m), sea = model lsm < 0.5  \u2014  "
                     "barbs: 10 m wind (kt)", fontsize=15)
        cb.ax.tick_params(labelsize=12)
    fig.suptitle(
        f"Crete \u2014 model orography and 10 m wind, run {BASE:%d %b %Y %H}Z\n"
        f"T+{STEP}h, valid {VALID:%d %b %Y %H}Z",
        fontsize=20, y=0.98,
    )
    fig.subplots_adjust(left=0.04, right=0.98, top=0.86, bottom=0.12,
                        hspace=0.3, wspace=0.08)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / f"crete_orog_wind_{BASE:%Y%m%d%H}_T{STEP}.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return str(out)


def main(force: bool = False) -> None:
    results = {}
    for spec in MODELS:
        res = retrieve(spec, force=force)
        if res is not None:
            results[spec[0]] = res
            print(f"  \u2713 {spec[1]}: {res['orog'].size} pts, "
                  f"orog max {res['orog'].max():.0f} m")
    print(f"\u2713 Wrote {make_figure(results, _crete_land())}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
