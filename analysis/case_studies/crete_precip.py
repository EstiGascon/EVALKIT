"""Crete extreme precipitation: 5-day accumulation from four models.

Single forecast: 30 Sep 2026 00 UTC run, T+0 -> T+120 h accumulation
(valid 30 Sep 00 UTC -> 05 Oct 00 UTC).  Models and native-resolution handling
are shared with ``catalonia_precip.py``.
"""

from __future__ import annotations

import datetime as dt
import sys

import earthkit.data as ekd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402

from catalonia_precip import (  # noqa: E402
    CACHE_DIR,
    FIG_DIR,
    MODELS,
    RESULTS_DIR,
    _haversine_km,
)
from precip_forecasts import (  # noqa: E402
    _as_fieldlist,
    _field_latlon,
    _field_units,
    _restore_tmpdir,
    _save_fieldlist,
    _set_mars_tmpdir,
    _to_mm,
)
from precip_obs import _parse_geo_file  # noqa: E402

import cartopy.crs as ccrs  # noqa: E402
import cartopy.feature as cfeature  # noqa: E402
import cartopy.io.shapereader as shpreader  # noqa: E402
import shapely  # noqa: E402

BASE = dt.datetime(2026, 9, 30, 0)
S0, S1 = 0, 120
VALID_END = BASE + dt.timedelta(hours=S1)

# Plot extent [W, E, S, N] tightly around Crete; retrieval area is padded so
# grid boxes fill the plot edges.
EXTENT = (23.3, 26.5, 34.7, 35.8)
AREA = [36.2, 23.0, 34.3, 26.8]  # N, W, S, E
CRETE_BOX = (34.8, 23.5, 35.7, 26.35)  # S, W, N, E

OBS_DIR = CACHE_DIR.parent / "observations" / "tp" / "tp_24h_crete"
OBS_SOURCES = "synop hdobs"
OBS_DAYS = [BASE + dt.timedelta(days=d) for d in range(1, S1 // 24 + 1)]  # 24 h ending 00Z
HELPERS_PKG = CACHE_DIR.parents[2] / "clickable_timeseries"
VINO_PATH = "/home/moz/bin/vino_getgeo"
MISSING = 3e38
CITIES = {
    "Chania": (35.51, 24.02),
    "Rethymno": (35.37, 24.47),
    "Heraklion": (35.34, 25.13),
    "Agios Nikolaos": (35.19, 25.72),
}

LEVELS = [0, 1, 2, 3, 4, 5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 100, 125, 150,
          175, 200, 225, 250, 275, 300, 350, 400, 500, 600, 750, 1000]
COLOURS = [
    "#ffffff", "#a6dcfa", "#79bcf2", "#4f8ef0", "#2741e6",  # 0-5
    "#bff200", "#99e000", "#66c800", "#33b000", "#008c1a",  # 5-30
    "#ffd800", "#ffbe00", "#ffa000", "#ff8200", "#f06000",  # 30-80
    "#ffb4b4", "#ff6e6e", "#ec1c1c", "#c80000", "#960000",  # 80-200
    "#e6b4ff", "#cc78ff", "#a846f0", "#8020d8", "#5a0a9c",  # 200-350
    "#8c8c8c", "#6e6e6e", "#505050", "#323232", "#000000",  # 350-1000
]
CMAP = ListedColormap(COLOURS)
CMAP.set_over("#000000")
NORM = BoundaryNorm(LEVELS, ncolors=CMAP.N)


def retrieve_tp(spec: tuple, force: bool = False):
    """T+0 -> T+120 h accumulation (mm) for one model at native resolution."""
    key, _label, mclass, stream, mtype, expver, param = spec
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"crete_{key}_tp_{BASE:%Y%m%d%H}_{S0}_{S1}.grib"
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
            "date": BASE.strftime("%Y%m%d"),
            "time": BASE.strftime("%H%M"),
            "step": f"{S0}/{S1}",
            "area": AREA,
            "expect": "any",
        }
        orig = _set_mars_tmpdir()
        try:
            ds = _as_fieldlist(ekd.from_source("mars", **request))
        except Exception as exc:  # noqa: BLE001
            print(f"  \u2717 MARS failed {key}: {exc}")
            return None
        finally:
            _restore_tmpdir(orig)
        if len(ds) < 1:
            print(f"  \u26a0 {key}: no fields returned")
            return None
        _save_fieldlist(ds, str(cache))

    by_step: dict[int, np.ndarray] = {}
    units = "m"
    lats, lons = _field_latlon(ds[0])
    lons = (lons + 180.0) % 360.0 - 180.0
    for fld in ds:
        by_step[int(fld.metadata("step"))] = np.asarray(fld.to_numpy()).ravel()
        units = _field_units(fld, units)
    if S1 not in by_step:
        print(f"  \u26a0 {key}: missing step {S1}")
        return None
    acc = by_step[S1] - by_step.get(S0, 0.0)
    acc = np.clip(_to_mm(acc, units), 0.0, None)
    return {"lats": lats, "lons": lons, "tp": acc}


def _crete_land():
    """Natural Earth 10 m land polygon for Crete (largest polygon in the box)."""
    s, w, n, e = CRETE_BOX
    box = shapely.box(w, s, e, n)
    path = shpreader.natural_earth(resolution="10m", category="physical", name="land")
    parts = shapely.get_parts(shapely.union_all(
        [g.intersection(box) for g in shpreader.Reader(path).geometries() if g.intersects(box)]))
    return max(parts, key=lambda p: p.area)


def stats(res: dict, land) -> dict:
    lats, lons, tp = res["lats"], res["lons"], res["tp"]
    on_land = shapely.contains_xy(land, lons, lats)
    i_max = np.argmax(np.where(on_land, tp, -1))
    out = {
        "crete_max_mm": float(tp[i_max]),
        "crete_max_lat": float(lats[i_max]),
        "crete_max_lon": float(lons[i_max]),
        "crete_land_mean_mm": float(tp[on_land].mean()),
        "n_land_points": int(on_land.sum()),
    }
    for name, (la, lo) in CITIES.items():
        d = np.where(on_land, _haversine_km(lats, lons, la, lo), np.inf)
        out[f"{name.replace(' ', '_')}_mm"] = float(tp[np.argmin(d)])
    out["n_points"] = int(tp.size)
    return out


def _gridbox_verts(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Rectangular cell (N, 4, 2) around each point of a reduced Gaussian grid."""
    rlat = np.round(lats, 6)
    rows = np.unique(rlat)
    mid = (rows[1:] + rows[:-1]) / 2
    lat_lo = np.concatenate([[rows[0] - (mid[0] - rows[0])], mid])
    lat_hi = np.concatenate([mid, [rows[-1] + (rows[-1] - mid[-1])]])
    verts = np.empty((lats.size, 4, 2))
    for j, row_lat in enumerate(rows):
        idx = np.flatnonzero(rlat == row_lat)
        idx = idx[np.argsort(lons[idx])]
        x = lons[idx]
        dx = np.median(np.diff(x)) if x.size > 1 else 0.1
        x0 = np.concatenate([[x[0] - dx / 2], (x[1:] + x[:-1]) / 2])
        x1 = np.concatenate([(x[1:] + x[:-1]) / 2, [x[-1] + dx / 2]])
        y0, y1 = lat_lo[j], lat_hi[j]
        verts[idx] = np.stack([
            np.column_stack([x0, np.full_like(x0, y0)]),
            np.column_stack([x1, np.full_like(x0, y0)]),
            np.column_stack([x1, np.full_like(x0, y1)]),
            np.column_stack([x0, np.full_like(x0, y1)]),
        ], axis=1)
    return verts


def _map_ax(fig, nrows, ncols, idx):
    ax = fig.add_subplot(nrows, ncols, idx, projection=ccrs.PlateCarree())
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.COASTLINE.with_scale("10m"), linewidth=0.8, zorder=5)
    gl = ax.gridlines(draw_labels=True, linewidth=0.25, alpha=0.4)
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = gl.ylabel_style = {"size": 11}
    return ax, {"transform": ccrs.PlateCarree()}


def make_figure(results: dict) -> str:
    nrows, ncols = 2, 2
    fig = plt.figure(figsize=(18, 10.5))
    last_cf = None
    for i, spec in enumerate(MODELS):
        ax, kw = _map_ax(fig, nrows, ncols, i + 1)
        res = results.get(spec[0])
        if res is None:
            ax.set_title(f"{spec[1]} \u2014 unavailable", fontsize=15)
            continue
        last_cf = PolyCollection(_gridbox_verts(res["lats"], res["lons"]),
                                 array=res["tp"], cmap=CMAP, norm=NORM,
                                 edgecolors="face", linewidths=0.1, **kw)
        ax.add_collection(last_cf)
        st = res["stats"]
        ax.plot(st["crete_max_lon"], st["crete_max_lat"], marker="x", color="k",
                markersize=10, mew=2, zorder=6, **kw)
        ax.set_title(
            f"{spec[1]} \u2014 T+0\u2013{S1}h\n"
            f"max over Crete {st['crete_max_mm']:.0f} mm (\u00d7), "
            f"island mean {st['crete_land_mean_mm']:.0f} mm",
            fontsize=15,
        )
    if last_cf is not None:
        cax = fig.add_axes([0.1, 0.06, 0.8, 0.022])
        cb = fig.colorbar(last_cf, cax=cax, orientation="horizontal", ticks=LEVELS)
        cb.set_label("Accumulated precipitation (mm)", fontsize=15)
        cb.ax.tick_params(labelsize=12)
    fig.suptitle(
        f"Crete \u2014 5-day precipitation, run {BASE:%d %b %Y %H}Z (T+0\u2013{S1}h)\n"
        f"{BASE:%d %b %H}Z \u2192 {VALID_END:%d %b %H}Z",
        fontsize=20, y=0.98,
    )
    fig.subplots_adjust(left=0.04, right=0.98, top=0.86, bottom=0.12,
                        hspace=0.3, wspace=0.08)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / f"crete_precip_{BASE:%Y%m%d%H}_{S0}_{S1}.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return str(out)


def retrieve_obs(force: bool = False) -> None:
    """Daily tp24 (SYNOP + HDOBS) ending 00 UTC on each day of the period."""
    if sorted(OBS_DIR.glob("tp*_obs_*.geo")) and not force:
        return
    if str(HELPERS_PKG) not in sys.path:
        sys.path.insert(0, str(HELPERS_PKG))
    from helpers.observations_retriever import ObservationsRetriever  # noqa: PLC0415

    OBS_DIR.mkdir(parents=True, exist_ok=True)
    ObservationsRetriever(vino_path=VINO_PATH).retrieve(
        sources=OBS_SOURCES, parameter="tp", period=24,
        start_date=f"{OBS_DAYS[0]:%Y%m%d}", end_date=f"{OBS_DAYS[-1]:%Y%m%d}",
        times="00", output_dir=str(OBS_DIR),
    )


def load_obs_total() -> pd.DataFrame:
    """Per-station sum of the daily tp24 over the period, complete records only."""
    frames = [_parse_geo_file(f, MISSING) for f in sorted(OBS_DIR.glob("tp*_obs_*.geo"))]
    obs = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    w, e, s, n = EXTENT
    obs = obs[obs["lat"].between(s, n) & obs["lon"].between(w, e)
              & obs["valid_time"].isin(OBS_DAYS)]
    obs = obs.drop_duplicates(subset=["stnid", "valid_time"])
    tot = obs.groupby("stnid").agg(lat=("lat", "first"), lon=("lon", "first"),
                                    n_days=("obs", "size"), total_mm=("obs", "sum"))
    tot = tot[tot["n_days"] == len(OBS_DAYS)]
    return tot.reset_index().sort_values("total_mm", ascending=False)


def make_obs_figure(obs: pd.DataFrame) -> str:
    fig = plt.figure(figsize=(14, 7))
    ax, kw = _map_ax(fig, 1, 1, 1)
    sc = ax.scatter(obs["lon"], obs["lat"], c=obs["total_mm"], cmap=CMAP, norm=NORM,
                    s=110, edgecolor="k", linewidth=0.7, zorder=7, **kw)
    ax.set_title(
        f"SYNOP + HDOBS \u2014 {len(obs)} stations with all {len(OBS_DAYS)} days\n"
        f"max {obs['total_mm'].max():.0f} mm, station mean {obs['total_mm'].mean():.0f} mm",
        fontsize=15,
    )
    cax = fig.add_axes([0.06, 0.08, 0.88, 0.03])
    cb = fig.colorbar(sc, cax=cax, orientation="horizontal", ticks=LEVELS)
    cb.set_label("Accumulated precipitation (mm)", fontsize=15)
    cb.ax.tick_params(labelsize=11)
    fig.suptitle(
        f"Crete — observed 5-day precipitation\n"
        f"{BASE:%d %b %H}Z → {VALID_END:%d %b %H}Z {VALID_END:%Y} (sum of daily 24 h totals)",
        fontsize=20, y=0.98,
    )
    fig.subplots_adjust(left=0.05, right=0.97, top=0.8, bottom=0.17)
    out = FIG_DIR / f"crete_precip_obs_{BASE:%Y%m%d%H}_{VALID_END:%Y%m%d%H}.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return str(out)


def main(force: bool = False) -> None:
    retrieve_obs(force=force)
    obs = load_obs_total()
    obs_csv = RESULTS_DIR / f"crete_precip_obs_{BASE:%Y%m%d%H}_{VALID_END:%Y%m%d%H}.csv"
    obs.to_csv(obs_csv, index=False, float_format="%.1f")
    print(obs.head(10).round(1).to_string(index=False))
    print(f"✓ Wrote {obs_csv}")
    print(f"✓ Wrote {make_obs_figure(obs)}")

    land = _crete_land()
    results: dict = {}
    rows = []
    for spec in MODELS:
        res = retrieve_tp(spec, force=force)
        if res is None:
            continue
        res["stats"] = stats(res, land)
        results[spec[0]] = res
        rows.append({"model": spec[1], "init": f"{BASE:%Y-%m-%d %HZ}",
                     "steps": f"{S0}-{S1}", **res["stats"]})
    df = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv = RESULTS_DIR / f"crete_precip_{BASE:%Y%m%d%H}_{S0}_{S1}.csv"
    df.to_csv(csv, index=False, float_format="%.1f")
    with pd.option_context("display.width", 250, "display.max_columns", None):
        print(df.drop(columns=["n_points"]).round(1).to_string(index=False))
    print(f"\u2713 Wrote {csv}")
    print(f"\u2713 Wrote {make_figure(results)}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
