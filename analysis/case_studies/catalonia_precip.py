"""Catalonia MCS, 3-4 Oct 2026: 24 h precipitation from four models.

Accumulation window 03 Oct 12 UTC -> 04 Oct 12 UTC, verified at two lead times
(lead = end of the accumulation period):

* T+60 h: 02 Oct 00 UTC run, steps 36-60
* T+36 h: 03 Oct 00 UTC run, steps 12-36

Models: IFS-control (od/0001), AIFS-single (ai/0001), DestinE (rd/iekm) and the
Pilot DT (rd/j5j2).  Fields are kept at each model's native resolution.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import earthkit.data as ekd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import BoundaryNorm  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # analysis/ pipeline modules
from precip_forecasts import (  # noqa: E402
    _as_fieldlist,
    _field_latlon,
    _field_units,
    _restore_tmpdir,
    _save_fieldlist,
    _set_mars_tmpdir,
    _to_mm,
)

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    _HAS_CARTOPY = True
except Exception:  # noqa: BLE001
    _HAS_CARTOPY = False

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_ROOT = REPO_ROOT / "analysis"
CACHE_DIR = ANALYSIS_ROOT / "data" / "forecasts_precip"
FIG_DIR = ANALYSIS_ROOT / "figures"
RESULTS_DIR = ANALYSIS_ROOT / "results"

WINDOW_END = dt.datetime(2026, 10, 4, 12)
WINDOW_START = WINDOW_END - dt.timedelta(hours=24)
LEADS = (60, 36)

# Plot / retrieval area [N, W, S, E] covering Catalonia and the adjacent sea.
NORTH, WEST, SOUTH, EAST = 43.5, -0.5, 39.5, 4.5
# Catalonia coastal strip (Ebro delta -> Costa Brava) for regional statistics.
COAST_BOX = (40.5, 0.5, 42.5, 3.4)  # S, W, N, E
BARCELONA = (41.39, 2.17)
BCN_RADIUS_KM = 25.0

# (key, label, class, stream, type, expver, param)
MODELS = [
    ("ifs", "IFS-control", "od", "oper", "fc", "0001", "228"),
    ("aifs", "AIFS-single", "ai", "oper", "fc", "0001", "228"),
    ("iekm", "DestinE (iekm)", "rd", "oper", "fc", "iekm", "228.128"),
    ("j5j2", "Pilot DT (j5j2)", "rd", "oper", "fc", "j5j2", "228.128"),
]

LEVELS = [1, 2, 5, 10, 20, 30, 50, 75, 100, 150, 200, 250]
CMAP = plt.get_cmap("turbo").copy()
NORM = BoundaryNorm(LEVELS, ncolors=CMAP.N, extend="max")


def retrieve_tp24(spec: tuple, lead: int, force: bool = False):
    """24 h accumulation (mm) ending WINDOW_END for one model at ``lead`` hours."""
    key, _label, mclass, stream, mtype, expver, param = spec
    base = WINDOW_END - dt.timedelta(hours=lead)
    s0, s1 = lead - 24, lead
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"cat_{key}_tp_{base:%Y%m%d%H}_{s0}_{s1}.grib"
    if cache.exists() and not force:
        ds = _as_fieldlist(ekd.from_source("file", str(cache)))
    else:
        request = {
            "class": mclass,
            "stream": stream,
            "type": mtype,
            "expver": expver,
            "levtype": "sfc",
            "param": param,
            "date": base.strftime("%Y%m%d"),
            "time": base.strftime("%H%M"),
            "step": f"{s0}/{s1}",
            "area": [NORTH, WEST, SOUTH, EAST],
            "expect": "any",
        }
        orig = _set_mars_tmpdir()
        try:
            ds = _as_fieldlist(ekd.from_source("mars", **request))
        except Exception as exc:  # noqa: BLE001
            print(f"  \u2717 MARS failed {key} {base:%Y-%m-%d %HZ}: {exc}")
            return None
        finally:
            _restore_tmpdir(orig)
        if len(ds) < 2:
            print(f"  \u26a0 {key} {base:%Y-%m-%d %HZ}: {len(ds)} fields (need 2)")
            return None
        _save_fieldlist(ds, str(cache))

    by_step: dict[int, np.ndarray] = {}
    units = "m"
    lats, lons = _field_latlon(ds[0])
    lons = (lons + 180.0) % 360.0 - 180.0  # area spans 0E; avoid a 0/360 seam
    for fld in ds:
        by_step[int(fld.metadata("step"))] = np.asarray(fld.to_numpy()).ravel()
        units = _field_units(fld, units)
    if s0 not in by_step or s1 not in by_step:
        print(f"  \u26a0 {key} {base:%Y-%m-%d %HZ}: missing step {s0} or {s1}")
        return None
    acc = np.clip(_to_mm(by_step[s1] - by_step[s0], units), 0.0, None)
    return {"base": base, "s0": s0, "s1": s1, "lats": lats, "lons": lons, "tp": acc}


def _haversine_km(lat, lon, lat0, lon0):
    p = np.pi / 180.0
    a = (np.sin((lat - lat0) * p / 2) ** 2
         + np.cos(lat * p) * np.cos(lat0 * p) * np.sin((lon - lon0) * p / 2) ** 2)
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def stats(res: dict) -> dict:
    lats, lons, tp = res["lats"], res["lons"], res["tp"]
    s, w, n, e = COAST_BOX
    coast = (lats >= s) & (lats <= n) & (lons >= w) & (lons <= e)
    d = _haversine_km(lats, lons, *BARCELONA)
    near = d <= BCN_RADIUS_KM
    i_coast = np.argmax(np.where(coast, tp, -1))
    return {
        "domain_max_mm": float(tp.max()),
        "coast_max_mm": float(tp[i_coast]),
        "coast_max_lat": float(lats[i_coast]),
        "coast_max_lon": float(lons[i_coast]),
        "coast_mean_mm": float(tp[coast].mean()),
        "bcn_point_mm": float(tp[np.argmin(d)]),
        f"bcn_max_{int(BCN_RADIUS_KM)}km_mm": float(tp[near].max()),
        f"bcn_mean_{int(BCN_RADIUS_KM)}km_mm": float(tp[near].mean()),
        "n_points": int(tp.size),
    }


def _map_ax(fig, nrows, ncols, idx):
    if _HAS_CARTOPY:
        ax = fig.add_subplot(nrows, ncols, idx, projection=ccrs.PlateCarree())
        ax.set_extent([WEST, EAST, SOUTH, NORTH], crs=ccrs.PlateCarree())
        ax.add_feature(cfeature.COASTLINE, linewidth=0.6)
        ax.add_feature(cfeature.BORDERS, linewidth=0.5)
        gl = ax.gridlines(draw_labels=True, linewidth=0.25, alpha=0.4)
        gl.top_labels = False
        gl.right_labels = False
        return ax, {"transform": ccrs.PlateCarree()}
    ax = fig.add_subplot(nrows, ncols, idx)
    ax.set_xlim(WEST, EAST)
    ax.set_ylim(SOUTH, NORTH)
    ax.grid(alpha=0.3)
    return ax, {}


def make_figure(results: dict) -> Path:
    nrows, ncols = len(LEADS), len(MODELS)
    fig = plt.figure(figsize=(5 * ncols, 4.8 * nrows + 1))
    last_cf = None
    for r, lead in enumerate(LEADS):
        for c, spec in enumerate(MODELS):
            ax, kw = _map_ax(fig, nrows, ncols, r * ncols + c + 1)
            res = results.get((spec[0], lead))
            if res is None:
                ax.set_title(f"{spec[1]} T+{lead}h \u2014 unavailable", fontsize=13)
                continue
            last_cf = ax.tricontourf(res["lons"], res["lats"], res["tp"],
                                     levels=LEVELS, cmap=CMAP, norm=NORM,
                                     extend="max", **kw)
            ax.plot(BARCELONA[1], BARCELONA[0], marker="*", color="k",
                    markersize=9, zorder=6, **kw)
            st = res["stats"]
            ax.set_title(
                f"{spec[1]} \u2014 T+{lead}h ({res['s0']}\u2013{res['s1']}h)\n"
                f"run {res['base']:%d %b %HZ} | max {st['domain_max_mm']:.0f} mm, "
                f"BCN {st['bcn_point_mm']:.0f} mm",
                fontsize=13,
            )
    if last_cf is not None:
        cax = fig.add_axes([0.25, 0.05, 0.5, 0.022])
        cb = fig.colorbar(last_cf, cax=cax, orientation="horizontal", extend="max",
                          ticks=LEVELS)
        cb.set_label("24 h precipitation (mm)", fontsize=15)
        cb.ax.tick_params(labelsize=13)
    fig.suptitle(
        f"Catalonia MCS \u2014 24 h precipitation "
        f"{WINDOW_START:%d %b %H}Z \u2192 {WINDOW_END:%d %b %H}Z {WINDOW_END:%Y}",
        fontsize=20, y=0.98,
    )
    fig.subplots_adjust(left=0.03, right=0.98, top=0.88, bottom=0.12,
                        hspace=0.3, wspace=0.12)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / f"catalonia_precip_{WINDOW_END:%Y%m%d%H}.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def main(force: bool = False) -> None:
    results: dict = {}
    rows = []
    for lead in LEADS:
        for spec in MODELS:
            res = retrieve_tp24(spec, lead, force=force)
            if res is None:
                continue
            res["stats"] = stats(res)
            results[(spec[0], lead)] = res
            rows.append({"model": spec[1], "lead_h": lead,
                         "init": f"{res['base']:%Y-%m-%d %HZ}",
                         "steps": f"{res['s0']}-{res['s1']}", **res["stats"]})
    df = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv = RESULTS_DIR / f"catalonia_precip_{WINDOW_END:%Y%m%d%H}.csv"
    df.to_csv(csv, index=False, float_format="%.1f")
    with pd.option_context("display.width", 200, "display.max_columns", None):
        print(df.drop(columns=["n_points"]).round(1).to_string(index=False))
    print(f"\u2713 Wrote {csv}")
    print(f"\u2713 Wrote {make_figure(results)}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
