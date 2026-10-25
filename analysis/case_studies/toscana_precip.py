"""Tuscany heavy precipitation: 24 h accumulation on 18 Oct 2024.

Window 18 Oct 2024 00 UTC -> 19 Oct 00 UTC, verified at two lead times
(lead = end of the accumulation period):

* T+24 h: 18 Oct 00 UTC run, steps 0-24
* T+48 h: 17 Oct 00 UTC run, steps 24-48

Models: IFS operational (od/0001), AIFS-single (ai/0001) and DestinE (rd/iekm,
falling back to rd/i4ql).  Fields are drawn per native grid box and compared
with SYNOP + HDOBS tp24 gauges valid 19 Oct 00 UTC.
"""

from __future__ import annotations

import datetime as dt
import sys

import earthkit.data as ekd
import matplotlib

matplotlib.use("Agg")
import cartopy.crs as ccrs  # noqa: E402
import cartopy.feature as cfeature  # noqa: E402
import cartopy.io.shapereader as shpreader  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402
from catalonia_precip import CACHE_DIR, FIG_DIR, RESULTS_DIR  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402
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

WINDOW_END = dt.datetime(2024, 10, 19, 0)
WINDOW_START = WINDOW_END - dt.timedelta(hours=24)
LEADS = (24, 48)

EXTENT = (9.0, 15.5, 39.8, 45.0)  # W, E, S, N: Tuscany to Campania
# Padded beyond EXTENT so contours of coarse grids (AIFS ~30 km) reach the frame.
AREA = [45.6, 8.4, 39.2, 16.1]  # N, W, S, E

# 24 h scale resolving 0-150 mm; saturated reds/magentas mark the peaks.
LEVELS = [0.5, 1, 2, 5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70, 80, 100, 125, 150]
COLOURS = [
    "#e0f3fb",
    "#b3dff2",
    "#7cc2ea",
    "#3f8fd6",  # 0.5-10
    "#a6e07a",
    "#5cc23e",
    "#1f8f2a",  # 10-25
    "#fff176",
    "#ffd23f",
    "#ffa726",  # 25-40
    "#fb6a1a",
    "#e53125",
    "#b5001f",  # 40-70
    "#ff3dc8",
    "#c51bb6",
    "#7a0ea8",
    "#3d0670",  # 70-150
]
CMAP = ListedColormap(COLOURS)
CMAP.set_under("#ffffff")
CMAP.set_over("#000000")
NORM = BoundaryNorm(LEVELS, ncolors=CMAP.N)

# (key, label, class, stream, type, expver candidates, param)
MODELS = [
    ("ifs", "IFS operational", "od", "oper", "fc", ("0001",), "228"),
    ("aifs", "AIFS-single", "ai", "oper", "fc", ("0001",), "228"),
    ("destine", "DestinE", "rd", "oper", "fc", ("iekm", "i4ql"), "228.128"),
]

OBS_DIR = CACHE_DIR.parent / "observations" / "tp" / "tp_24h_toscana"
HELPERS_PKG = CACHE_DIR.parents[2] / "clickable_timeseries"
VINO_PATH = "/home/moz/bin/vino_getgeo"
MISSING = 3e38


def _retrieve(spec: tuple, expver: str, lead: int, force: bool):
    key, _label, mclass, stream, mtype, _expvers, param = spec
    base = WINDOW_END - dt.timedelta(hours=lead)
    s0, s1 = lead - 24, lead
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    area_tag = "_".join(f"{v:g}" for v in AREA)
    cache = (
        CACHE_DIR / f"tosc_{key}_{expver}_tp_{base:%Y%m%d%H}_{s0}_{s1}_{area_tag}.grib"
    )
    if cache.exists() and not force:
        return _as_fieldlist(ekd.from_source("file", str(cache)))
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
        "area": AREA,
        "expect": "any",
    }
    orig = _set_mars_tmpdir()
    try:
        ds = _as_fieldlist(ekd.from_source("mars", **request))
    except Exception as exc:  # noqa: BLE001
        print(f"  \u2717 MARS failed {key}/{expver} {base:%Y-%m-%d %HZ}: {exc}")
        return None
    finally:
        _restore_tmpdir(orig)
    if len(ds) < 1:
        return None
    _save_fieldlist(ds, str(cache))
    return ds


def retrieve_tp24(spec: tuple, lead: int, force: bool = False):
    """Return the 24 h accumulation (mm) ending WINDOW_END for one model and lead."""
    s0, s1 = lead - 24, lead
    for expver in spec[5]:
        ds = _retrieve(spec, expver, lead, force)
        if ds is None:
            continue
        by_step: dict[int, np.ndarray] = {}
        units = "m"
        lats, lons = _field_latlon(ds[0])
        lons = (lons + 180.0) % 360.0 - 180.0
        for fld in ds:
            by_step[int(fld.metadata("step"))] = np.asarray(fld.to_numpy()).ravel()
            units = _field_units(fld, units)
        if s1 not in by_step:
            print(f"  \u26a0 {spec[0]}/{expver} T+{lead}: missing step {s1}")
            continue
        # Step 0 of tp is zero by definition and may be absent from the archive.
        acc = by_step[s1] - by_step.get(s0, 0.0)
        return {
            "expver": expver,
            "base": WINDOW_END - dt.timedelta(hours=lead),
            "s0": s0,
            "s1": s1,
            "lats": lats,
            "lons": lons,
            "tp": np.clip(_to_mm(acc, units), 0.0, None),
        }
    return None


def tuscany_polygon():
    """Return the Tuscany region outline (union of its Natural Earth provinces)."""
    path = shpreader.natural_earth(
        resolution="10m", category="cultural", name="admin_1_states_provinces"
    )
    geoms = [
        rec.geometry
        for rec in shpreader.Reader(path).records()
        if rec.attributes.get("admin") == "Italy"
        and rec.attributes.get("region") == "Toscana"
    ]
    return shapely.union_all(geoms)


def retrieve_obs(force: bool = False) -> None:
    """Retrieve SYNOP + HDOBS tp24 valid at WINDOW_END."""
    if sorted(OBS_DIR.glob("tp*_obs_*.geo")) and not force:
        return
    if str(HELPERS_PKG) not in sys.path:
        sys.path.insert(0, str(HELPERS_PKG))
    from helpers.observations_retriever import ObservationsRetriever  # noqa: PLC0415

    OBS_DIR.mkdir(parents=True, exist_ok=True)
    ObservationsRetriever(vino_path=VINO_PATH).retrieve(
        sources="synop hdobs",
        parameter="tp",
        period=24,
        start_date=f"{WINDOW_END:%Y%m%d}",
        end_date=f"{WINDOW_END:%Y%m%d}",
        times=f"{WINDOW_END:%H}",
        output_dir=str(OBS_DIR),
    )


def load_obs(region) -> pd.DataFrame:
    """Return tp24 gauges valid at WINDOW_END inside the plot extent, flagged by region."""
    frames = [
        _parse_geo_file(f, MISSING) for f in sorted(OBS_DIR.glob("tp*_obs_*.geo"))
    ]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["stnid", "lat", "lon", "obs", "in_tuscany"])
    obs = pd.concat(frames, ignore_index=True)
    w, e, s, n = EXTENT
    obs = obs[
        (obs["valid_time"] == WINDOW_END)
        & obs["lat"].between(s, n)
        & obs["lon"].between(w, e)
    ].drop_duplicates(subset="stnid")
    obs = obs.assign(in_tuscany=shapely.contains_xy(region, obs["lon"], obs["lat"]))
    return obs.reset_index(drop=True)


def _nearest(lats, lons, plat, plon) -> np.ndarray:
    """Return the index of the nearest model point to each (plat, plon)."""
    coslat = np.cos(np.deg2rad(lats))
    return np.array(
        [
            np.argmin((lats - la) ** 2 + ((lons - lo) * coslat) ** 2)
            for la, lo in zip(plat, plon, strict=True)
        ],
        dtype=int,
    )


def stats(res: dict, region, obs: pd.DataFrame) -> dict:
    """Region statistics and gauge verification for one forecast."""
    lats, lons, tp = res["lats"], res["lons"], res["tp"]
    inside = shapely.contains_xy(region, lons, lats)
    i_max = np.argmax(np.where(inside, tp, -1))
    out = {
        "tuscany_max_mm": float(tp[i_max]),
        "tuscany_max_lat": float(lats[i_max]),
        "tuscany_max_lon": float(lons[i_max]),
        "tuscany_mean_mm": float(tp[inside].mean()),
        "tuscany_points": int(inside.sum()),
    }
    g = obs[obs["in_tuscany"]]
    if not g.empty:
        fc = tp[_nearest(lats, lons, g["lat"].to_numpy(), g["lon"].to_numpy())]
        err = fc - g["obs"].to_numpy()
        out.update(
            n_gauges=len(g),
            gauge_mean_mm=float(g["obs"].mean()),
            fc_at_gauges_mean_mm=float(fc.mean()),
            bias_mm=float(err.mean()),
            mae_mm=float(np.abs(err).mean()),
            rmse_mm=float(np.sqrt((err**2).mean())),
            corr=float(np.corrcoef(fc, g["obs"])[0, 1]) if len(g) > 2 else np.nan,
        )
    return out


def _map_ax(fig, nrows, ncols, idx, region):
    ax = fig.add_subplot(nrows, ncols, idx, projection=ccrs.PlateCarree())
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.COASTLINE.with_scale("10m"), linewidth=0.7, zorder=5)
    ax.add_feature(cfeature.BORDERS.with_scale("10m"), linewidth=0.5, zorder=5)
    ax.add_feature(
        cfeature.STATES.with_scale("10m"), linewidth=0.3, edgecolor="0.35", zorder=5
    )
    ax.add_geometries(
        [region],
        ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="k",
        linewidth=1.3,
        zorder=6,
    )
    gl = ax.gridlines(draw_labels=True, linewidth=0.25, alpha=0.4)
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = gl.ylabel_style = {"size": 11}
    return ax, {"transform": ccrs.PlateCarree()}


def _colorbar(fig, mappable, rect):
    cax = fig.add_axes(rect)
    cb = fig.colorbar(
        mappable, cax=cax, orientation="horizontal", ticks=LEVELS, extend="max"
    )
    cb.ax.set_xticklabels([f"{v:g}" for v in LEVELS])
    cb.set_label("24 h precipitation (mm)", fontsize=15)
    cb.ax.tick_params(labelsize=11)


def make_figure(results: dict, region) -> str:
    """Draw the leads x models precipitation figure."""
    nrows, ncols = len(LEADS), len(MODELS)
    fig = plt.figure(figsize=(7.2 * ncols, 5.8 * nrows + 1.5))
    pc = None
    for r, lead in enumerate(LEADS):
        for c, spec in enumerate(MODELS):
            ax, kw = _map_ax(fig, nrows, ncols, r * ncols + c + 1, region)
            res = results.get((spec[0], lead))
            if res is None:
                ax.set_title(f"{spec[1]} T+{lead}h \u2014 unavailable", fontsize=14)
                continue
            pc = ax.tricontourf(
                res["lons"],
                res["lats"],
                res["tp"],
                levels=LEVELS,
                cmap=CMAP,
                norm=NORM,
                extend="max",
                **kw,
            )
            st = res["stats"]
            ax.plot(
                st["tuscany_max_lon"],
                st["tuscany_max_lat"],
                marker="x",
                color="k",
                markersize=10,
                mew=2,
                zorder=7,
                **kw,
            )
            label = spec[1] if spec[0] != "destine" else f"{spec[1]} ({res['expver']})"
            ax.set_title(
                f"{label} \u2014 T+{lead}h ({res['s0']}\u2013{res['s1']}h)\n"
                f"run {res['base']:%d %b %HZ} | Tuscany max {st['tuscany_max_mm']:.0f} mm (\u00d7)",
                fontsize=13,
            )
    if pc is not None:
        _colorbar(fig, pc, [0.08, 0.06, 0.84, 0.02])
    fig.suptitle(
        f"Tuscany \u2014 24 h precipitation "
        f"{WINDOW_START:%d %b %HZ} \u2192 {WINDOW_END:%d %b %HZ} {WINDOW_END:%Y}",
        fontsize=20,
        y=0.98,
    )
    fig.subplots_adjust(
        left=0.04, right=0.98, top=0.88, bottom=0.13, hspace=0.3, wspace=0.12
    )
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / f"toscana_precip_{WINDOW_END:%Y%m%d%H}.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return str(out)


def make_obs_figure(obs: pd.DataFrame, region) -> str:
    """Draw the observed tp24 gauge map."""
    fig = plt.figure(figsize=(12, 9.5))
    ax, kw = _map_ax(fig, 1, 1, 1, region)
    o = obs.sort_values("obs")
    sc = ax.scatter(
        o["lon"],
        o["lat"],
        c=o["obs"],
        cmap=CMAP,
        norm=NORM,
        s=70,
        edgecolor="k",
        linewidth=0.5,
        zorder=8,
        **kw,
    )
    t = obs[obs["in_tuscany"]]
    info = (
        f"{len(t)} gauges in Tuscany, max {t['obs'].max():.0f} mm, mean {t['obs'].mean():.0f} mm"
        if not t.empty
        else "no gauges in Tuscany"
    )
    ax.set_title(f"SYNOP + HDOBS \u2014 {info}", fontsize=14)
    _colorbar(fig, sc, [0.06, 0.07, 0.88, 0.025])
    fig.suptitle(
        f"Tuscany \u2014 observed 24 h precipitation\n"
        f"{WINDOW_START:%d %b %HZ} \u2192 {WINDOW_END:%d %b %HZ} {WINDOW_END:%Y}",
        fontsize=18,
        y=0.98,
    )
    fig.subplots_adjust(left=0.07, right=0.96, top=0.86, bottom=0.16)
    out = FIG_DIR / f"toscana_precip_obs_{WINDOW_END:%Y%m%d%H}.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return str(out)


def main(force: bool = False) -> None:
    """Retrieve forecasts and gauges, write statistics and figures."""
    region = tuscany_polygon()
    retrieve_obs(force=force)
    obs = load_obs(region)
    print(
        f"Gauges in plot extent: {len(obs)} ({int(obs['in_tuscany'].sum())} in Tuscany)"
    )
    print(f"\u2713 Wrote {make_obs_figure(obs, region)}")

    results: dict = {}
    rows = []
    for lead in LEADS:
        for spec in MODELS:
            res = retrieve_tp24(spec, lead, force=force)
            if res is None:
                print(f"  \u2717 {spec[1]} T+{lead}: no data")
                continue
            res["stats"] = stats(res, region, obs)
            results[(spec[0], lead)] = res
            rows.append(
                {
                    "model": spec[1],
                    "expver": res["expver"],
                    "lead_h": lead,
                    "init": f"{res['base']:%Y-%m-%d %HZ}",
                    "steps": f"{res['s0']}-{res['s1']}",
                    **res["stats"],
                }
            )
    df = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv = RESULTS_DIR / f"toscana_precip_{WINDOW_END:%Y%m%d%H}.csv"
    df.to_csv(csv, index=False, float_format="%.2f")
    with pd.option_context("display.width", 250, "display.max_columns", None):
        print(df.round(1).to_string(index=False))
    print(f"\u2713 Wrote {csv}")
    print(f"\u2713 Wrote {make_figure(results, region)}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
