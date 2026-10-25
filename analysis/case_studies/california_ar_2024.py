"""Atmospheric river and bomb cyclone, Northern California / Pacific NW, Nov 2024.

CW3E AR3-4 event: a bomb cyclone deepened > 50 hPa in < 24 h off the Pacific
Northwest (peak winds 20 Nov 03-12 UTC), then the AR stalled over Northern
California (heaviest rain 21-22 Nov).  Two evaluations, each for IFS
operational (od/0001), AIFS-single (ai/0001) and DestinE (rd/iekm, falling back
to rd/i4ql), verified against SYNOP + HDOBS:

* Precipitation: 4-day total 20 Nov 00 UTC -> 24 Nov 00 UTC at T+96 (20 Nov
  00 UTC run, steps 0-96) and T+120 (19 Nov 00 UTC run, steps 24-120).
* Maximum 10 m wind speed over 19 Nov 12 UTC -> 21 Nov 12 UTC (bomb cyclone
  passage) at T+60 (19 Nov 00 UTC run) and T+84 (18 Nov 00 UTC run), from
  3-hourly output (6-hourly for AIFS) and 3-hourly station reports.
"""

from __future__ import annotations

import datetime as dt
import sys

import earthkit.data as ekd
import matplotlib

matplotlib.use("Agg")
import cartopy.crs as ccrs  # noqa: E402
import cartopy.feature as cfeature  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
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
from toscana_precip import _nearest  # noqa: E402

# --- Case definition --------------------------------------------------------
TP_START = dt.datetime(2024, 11, 20, 0)
TP_END = dt.datetime(2024, 11, 24, 0)
TP_LEADS = (96, 120)  # lead to the end of the accumulation window
WIND_START = dt.datetime(2024, 11, 19, 12)
WIND_END = dt.datetime(2024, 11, 21, 12)
WIND_LEADS = (60, 84)  # lead to the end of the window
WIND_STEP_H = {"aifs": 6}  # output interval; others use 3-hourly
WIND_MIN_REPORTS = 14  # of the 17 three-hourly station reports

EXTENT = (-128.0, -116.0, 36.5, 49.5)  # W, E, S, N
# Padded beyond EXTENT so contours of coarse grids (AIFS ~30 km) reach the frame.
AREA = [50.3, -128.8, 35.7, -115.2]  # N, W, S, E
NCAL_BOX = (37.5, -124.5, 42.0, -121.0)  # S, W, N, E: Northern California focus

# (key, label, class, expver candidates, tp param, 10u/10v params)
MODELS = [
    ("ifs", "IFS operational", "od", ("0001",), "228", "165/166"),
    ("aifs", "AIFS-single", "ai", ("0001",), "228", "165/166"),
    ("destine", "DestinE", "rd", ("iekm", "i4ql"), "228.128", "165.128/166.128"),
]

OBS_ROOT = CACHE_DIR.parent / "observations"
TP_OBS_DIR = OBS_ROOT / "tp" / "tp_24h_ar2024"
WIND_OBS_DIR = OBS_ROOT / "10ff" / "ar2024"
HELPERS_PKG = CACHE_DIR.parents[2] / "clickable_timeseries"
VINO_PATH = "/home/moz/bin/vino_getgeo"
MISSING = 3e38

# --- Colour scales ----------------------------------------------------------
# 4-day totals up to ~600 mm; saturated reds/magentas mark the AR core.
TP_LEVELS = [1, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 600]
TP_COLOURS = [
    "#e0f3fb", "#9fd3ef", "#4f9fdc",  # 1-20
    "#a6e07a", "#4fb83a", "#1f7f2a",  # 20-75
    "#fff176", "#ffc93c", "#ff9a26",  # 75-150
    "#f4511e", "#d01c1c", "#9e0020",  # 150-300
    "#ff3dc8", "#a417b0", "#4b0a7d",  # 300-600
]  # fmt: skip
TP_CMAP = ListedColormap(TP_COLOURS)
TP_CMAP.set_under("#ffffff")
TP_CMAP.set_over("#1a0030")
TP_NORM = BoundaryNorm(TP_LEVELS, ncolors=TP_CMAP.N)

WS_LEVELS = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32]
WS_COLOURS = [
    "#f7fbff", "#d6e9f6", "#a9d1ec", "#6cb0dd",  # 0-8
    "#9be27e", "#4fbf3a", "#fff176", "#ffc93c",  # 8-16
    "#ff9a26", "#f4511e", "#d01c1c", "#9e0020",  # 16-25
    "#ff3dc8", "#7a0ea8",  # 25-32
]  # fmt: skip
WS_CMAP = ListedColormap(WS_COLOURS)
WS_CMAP.set_over("#2a0050")
WS_NORM = BoundaryNorm(WS_LEVELS, ncolors=WS_CMAP.N)


# --- Retrieval --------------------------------------------------------------
def _mars(spec: tuple, expver: str, base: dt.datetime, param: str, steps: str, force):
    key, _label, mclass = spec[:3]
    tag = "_".join(f"{v:g}" for v in AREA)
    name = f"ar24_{key}_{expver}_{param.replace('/', '-')}_{base:%Y%m%d%H}_{steps.replace('/', '-')}_{tag}"
    cache = CACHE_DIR / f"{name}.grib"
    if cache.exists() and not force:
        return _as_fieldlist(ekd.from_source("file", str(cache)))
    request = {
        "class": mclass,
        "stream": "oper",
        "type": "fc",
        "expver": expver,
        "levtype": "sfc",
        "param": param,
        "date": base.strftime("%Y%m%d"),
        "time": base.strftime("%H%M"),
        "step": steps,
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
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _save_fieldlist(ds, str(cache))
    return ds


def _latlon(ds):
    lats, lons = _field_latlon(ds[0])
    return lats, (lons + 180.0) % 360.0 - 180.0


def retrieve_tp(spec: tuple, lead: int, force: bool = False):
    """Return the accumulated precipitation (mm) over TP_START-TP_END at ``lead``."""
    base = TP_END - dt.timedelta(hours=lead)
    s1 = lead
    s0 = s1 - int((TP_END - TP_START).total_seconds() // 3600)
    for expver in spec[3]:
        ds = _mars(spec, expver, base, spec[4], f"{s0}/{s1}", force)
        if ds is None:
            continue
        by_step, units = {}, "m"
        for fld in ds:
            by_step[int(fld.metadata("step"))] = np.asarray(fld.to_numpy()).ravel()
            units = _field_units(fld, units)
        if s1 not in by_step:
            continue
        # Step 0 of tp is zero by definition and may be absent from the archive.
        acc = by_step[s1] - by_step.get(s0, 0.0)
        lats, lons = _latlon(ds)
        return {
            "expver": expver,
            "base": base,
            "s0": s0,
            "s1": s1,
            "lats": lats,
            "lons": lons,
            "val": np.clip(_to_mm(acc, units), 0.0, None),
        }
    return None


def retrieve_wind(spec: tuple, lead: int, force: bool = False):
    """Return the maximum 10 m wind speed (m/s) over WIND_START-WIND_END at ``lead``."""
    base = WIND_END - dt.timedelta(hours=lead)
    s1 = lead
    s0 = s1 - int((WIND_END - WIND_START).total_seconds() // 3600)
    inc = WIND_STEP_H.get(spec[0], 3)
    steps = "/".join(str(s) for s in range(s0, s1 + 1, inc))
    for expver in spec[3]:
        ds = _mars(spec, expver, base, spec[5], steps, force)
        if ds is None:
            continue
        comp: dict[tuple[str, int], np.ndarray] = {}
        for fld in ds:
            key = (fld.metadata("shortName"), int(fld.metadata("step")))
            comp[key] = np.asarray(fld.to_numpy()).ravel()
        speeds = [
            np.hypot(comp[("10u", s)], comp[("10v", s)])
            for s in range(s0, s1 + 1, inc)
            if ("10u", s) in comp and ("10v", s) in comp
        ]
        if not speeds:
            continue
        lats, lons = _latlon(ds)
        return {
            "expver": expver,
            "base": base,
            "s0": s0,
            "s1": s1,
            "n_steps": len(speeds),
            "lats": lats,
            "lons": lons,
            "val": np.max(speeds, axis=0),
        }
    return None


def retrieve_obs(force: bool = False) -> None:
    """Retrieve daily tp24 (00 UTC) and 3-hourly 10ff from SYNOP + HDOBS."""
    if str(HELPERS_PKG) not in sys.path:
        sys.path.insert(0, str(HELPERS_PKG))
    from helpers.observations_retriever import ObservationsRetriever  # noqa: PLC0415

    retr = ObservationsRetriever(vino_path=VINO_PATH)
    if force or not sorted(TP_OBS_DIR.glob("tp*_obs_*.geo")):
        retr.retrieve(
            sources="synop hdobs",
            parameter="tp",
            period=24,
            start_date=f"{TP_START + dt.timedelta(days=1):%Y%m%d}",
            end_date=f"{TP_END:%Y%m%d}",
            times="00",
            output_dir=str(TP_OBS_DIR),
        )
    if force or not sorted(WIND_OBS_DIR.glob("10ff*_obs_*.geo")):
        retr.retrieve(
            sources="synop hdobs",
            parameter="10ff",
            period=None,
            start_date=f"{WIND_START:%Y%m%d}",
            end_date=f"{WIND_END:%Y%m%d}",
            times="00 03 06 09 12 15 18 21",
            output_dir=str(WIND_OBS_DIR),
        )


def _load_geo(directory) -> pd.DataFrame:
    frames = [_parse_geo_file(f, MISSING) for f in sorted(directory.glob("*.geo"))]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["stnid", "lat", "lon", "valid_time", "obs"])
    obs = pd.concat(frames, ignore_index=True)
    w, e, s, n = EXTENT
    return obs[obs["lat"].between(s, n) & obs["lon"].between(w, e)]


def load_tp_obs() -> pd.DataFrame:
    """Return per-station totals over TP_START-TP_END from complete daily records."""
    days = pd.date_range(TP_START + dt.timedelta(days=1), TP_END, freq="1D")
    obs = _load_geo(TP_OBS_DIR)
    obs = obs[obs["valid_time"].isin(days)].drop_duplicates(["stnid", "valid_time"])
    tot = obs.groupby("stnid").agg(
        lat=("lat", "first"),
        lon=("lon", "first"),
        n_days=("obs", "size"),
        obs=("obs", "sum"),
    )
    return tot[tot["n_days"] == len(days)].reset_index()


def load_wind_obs() -> pd.DataFrame:
    """Return per-station maximum 3-hourly 10 m wind speed over WIND_START-WIND_END."""
    obs = _load_geo(WIND_OBS_DIR)
    obs = obs[obs["valid_time"].between(WIND_START, WIND_END)]
    obs = obs.drop_duplicates(["stnid", "valid_time"])
    mx = obs.groupby("stnid").agg(
        lat=("lat", "first"),
        lon=("lon", "first"),
        n_reports=("obs", "size"),
        obs=("obs", "max"),
    )
    return mx[mx["n_reports"] >= WIND_MIN_REPORTS].reset_index()


# --- Statistics ---------------------------------------------------------------
def stats(res: dict, obs: pd.DataFrame, focus_box=None) -> dict:
    """Domain/focus maxima and station verification for one forecast."""
    lats, lons, val = res["lats"], res["lons"], res["val"]
    w, e, s, n = EXTENT
    dom = (lats >= s) & (lats <= n) & (lons >= w) & (lons <= e)
    i = np.argmax(np.where(dom, val, -1))
    out = {"max": float(val[i]), "max_lat": float(lats[i]), "max_lon": float(lons[i])}
    if focus_box is not None:
        fs, fw, fn, fe = focus_box
        foc = (lats >= fs) & (lats <= fn) & (lons >= fw) & (lons <= fe)
        out["ncal_max"] = float(val[foc].max())
        out["ncal_mean"] = float(val[foc].mean())
    if not obs.empty:
        fc = val[_nearest(lats, lons, obs["lat"].to_numpy(), obs["lon"].to_numpy())]
        ob = obs["obs"].to_numpy()
        err = fc - ob
        out.update(
            n_obs=len(ob),
            obs_mean=float(ob.mean()),
            fc_mean_at_obs=float(fc.mean()),
            bias=float(err.mean()),
            mae=float(np.abs(err).mean()),
            rmse=float(np.sqrt((err**2).mean())),
            corr=float(np.corrcoef(fc, ob)[0, 1]) if len(ob) > 2 else np.nan,
        )
    return out


# --- Plotting -----------------------------------------------------------------
def _map_ax(fig, nrows, ncols, idx):
    ax = fig.add_subplot(nrows, ncols, idx, projection=ccrs.PlateCarree())
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.COASTLINE.with_scale("10m"), linewidth=0.7, zorder=5)
    ax.add_feature(cfeature.BORDERS.with_scale("10m"), linewidth=0.6, zorder=5)
    ax.add_feature(
        cfeature.STATES.with_scale("10m"), linewidth=0.4, edgecolor="0.3", zorder=5
    )
    gl = ax.gridlines(draw_labels=True, linewidth=0.25, alpha=0.4)
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = gl.ylabel_style = {"size": 11}
    return ax, {"transform": ccrs.PlateCarree()}


def _colorbar(fig, mappable, rect, levels, label):
    cax = fig.add_axes(rect)
    cb = fig.colorbar(
        mappable, cax=cax, orientation="horizontal", ticks=levels, extend="max"
    )
    cb.ax.set_xticklabels([f"{v:g}" for v in levels])
    cb.set_label(label, fontsize=15)
    cb.ax.tick_params(labelsize=11)


def _panel_figure(kind: str, results: dict, leads, title: str, fname: str) -> str:
    cmap, norm, levels = (
        (TP_CMAP, TP_NORM, TP_LEVELS) if kind == "tp" else (WS_CMAP, WS_NORM, WS_LEVELS)
    )
    unit = "mm" if kind == "tp" else "m/s"
    nrows, ncols = len(leads), len(MODELS)
    fig = plt.figure(figsize=(6.4 * ncols, 6.4 * nrows + 1.5))
    cf = None
    for r, lead in enumerate(leads):
        for c, spec in enumerate(MODELS):
            ax, kw = _map_ax(fig, nrows, ncols, r * ncols + c + 1)
            res = results.get((spec[0], lead))
            if res is None:
                ax.set_title(f"{spec[1]} T+{lead}h \u2014 unavailable", fontsize=14)
                continue
            cf = ax.tricontourf(
                res["lons"],
                res["lats"],
                res["val"],
                levels=levels,
                cmap=cmap,
                norm=norm,
                extend="max",
                **kw,
            )
            st = res["stats"]
            ax.plot(
                st["max_lon"],
                st["max_lat"],
                marker="x",
                color="k",
                markersize=10,
                mew=2,
                zorder=8,
                **kw,
            )
            label = f"{spec[1]} ({res['expver']})" if spec[0] == "destine" else spec[1]
            steps = f"{res['s0']}\u2013{res['s1']}h"
            if kind == "wind":
                steps += f", {res['n_steps']} outputs"
            ax.set_title(
                f"{label} \u2014 T+{lead}h ({steps})\n"
                f"run {res['base']:%d %b %HZ} | max {st['max']:.0f} {unit} (\u00d7)",
                fontsize=13,
            )
    if cf is not None:
        bar_label = (
            "Accumulated precipitation (mm)"
            if kind == "tp"
            else "Maximum 10 m wind speed (m/s)"
        )
        _colorbar(fig, cf, [0.08, 0.06, 0.84, 0.02], levels, bar_label)
    fig.suptitle(title, fontsize=20, y=0.98)
    fig.subplots_adjust(
        left=0.04, right=0.98, top=0.88, bottom=0.13, hspace=0.3, wspace=0.12
    )
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / fname
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return str(out)


def _obs_figure(kind: str, obs: pd.DataFrame, title: str, fname: str) -> str:
    cmap, norm, levels = (
        (TP_CMAP, TP_NORM, TP_LEVELS) if kind == "tp" else (WS_CMAP, WS_NORM, WS_LEVELS)
    )
    unit = "mm" if kind == "tp" else "m/s"
    fig = plt.figure(figsize=(10, 11))
    ax, kw = _map_ax(fig, 1, 1, 1)
    o = obs.sort_values("obs")
    sc = ax.scatter(
        o["lon"],
        o["lat"],
        c=o["obs"],
        cmap=cmap,
        norm=norm,
        s=90,
        edgecolor="k",
        linewidth=0.6,
        zorder=8,
        **kw,
    )
    if not obs.empty:
        top = obs.loc[obs["obs"].idxmax()]
        info = f"n={len(obs)}, max {top['obs']:.0f} {unit} ({top['lat']:.1f}\u00b0N {-top['lon']:.1f}\u00b0W)"
    else:
        info = "no stations"
    ax.set_title(f"SYNOP + HDOBS \u2014 {info}", fontsize=14)
    _colorbar(
        fig,
        sc,
        [0.08, 0.07, 0.84, 0.022],
        levels,
        "Accumulated precipitation (mm)"
        if kind == "tp"
        else "Maximum 10 m wind speed (m/s)",
    )
    fig.suptitle(title, fontsize=18, y=0.98)
    fig.subplots_adjust(left=0.08, right=0.96, top=0.88, bottom=0.15)
    out = FIG_DIR / fname
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return str(out)


# --- Main -----------------------------------------------------------------------
def _run(kind, leads, retrieve, obs, focus_box):
    results, rows = {}, []
    for lead in leads:
        for spec in MODELS:
            res = retrieve(spec, lead)
            if res is None:
                print(f"  \u2717 {spec[1]} {kind} T+{lead}: no data")
                continue
            res["stats"] = stats(res, obs, focus_box)
            results[(spec[0], lead)] = res
            rows.append(
                {
                    "model": spec[1],
                    "expver": res["expver"],
                    "lead_h": lead,
                    "init": f"{res['base']:%Y-%m-%d %HZ}",
                    **res["stats"],
                }
            )
    return results, pd.DataFrame(rows)


def main(force: bool = False) -> None:
    """Build precipitation and wind panel figures, observation maps and CSVs."""
    retrieve_obs(force=force)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    period = f"{TP_START:%d %b %HZ} \u2192 {TP_END:%d %b %HZ} {TP_END:%Y}"

    tp_obs = load_tp_obs()
    print(f"Precip gauges with all days: {len(tp_obs)}")
    print(
        _obs_figure(
            "tp",
            tp_obs,
            f"N California / Pacific NW AR \u2014 observed 4-day precipitation\n{period}",
            f"ar2024_tp_obs_{TP_START:%Y%m%d%H}_{TP_END:%Y%m%d%H}.png",
        )
    )
    tp_res, tp_df = _run(
        "tp", TP_LEADS, lambda s, ld: retrieve_tp(s, ld, force), tp_obs, NCAL_BOX
    )
    tp_df.to_csv(
        RESULTS_DIR / f"ar2024_tp_{TP_START:%Y%m%d%H}_{TP_END:%Y%m%d%H}.csv",
        index=False,
        float_format="%.2f",
    )
    print(
        _panel_figure(
            "tp",
            tp_res,
            TP_LEADS,
            f"Atmospheric river, N California / Pacific NW \u2014 4-day precipitation\n{period}",
            f"ar2024_tp_{TP_START:%Y%m%d%H}_{TP_END:%Y%m%d%H}.png",
        )
    )

    ws_obs = load_wind_obs()
    print(f"Wind stations with >= {WIND_MIN_REPORTS} reports: {len(ws_obs)}")
    window = f"{WIND_START:%d %b %HZ} \u2192 {WIND_END:%d %b %HZ} {WIND_END:%Y}"
    tag = f"{WIND_START:%Y%m%d%H}_{WIND_END:%Y%m%d%H}"
    print(
        _obs_figure(
            "wind",
            ws_obs,
            f"Bomb cyclone \u2014 observed maximum 10 m wind speed\n{window} (3-hourly reports)",
            f"ar2024_ws10max_obs_{tag}.png",
        )
    )
    ws_res, ws_df = _run(
        "wind", WIND_LEADS, lambda s, ld: retrieve_wind(s, ld, force), ws_obs, None
    )
    ws_df.to_csv(
        RESULTS_DIR / f"ar2024_ws10max_{tag}.csv",
        index=False,
        float_format="%.2f",
    )
    print(
        _panel_figure(
            "wind",
            ws_res,
            WIND_LEADS,
            f"Bomb cyclone, Pacific NW \u2014 maximum 10 m wind speed\n{window}",
            f"ar2024_ws10max_{tag}.png",
        )
    )
    with pd.option_context("display.width", 250, "display.max_columns", None):
        print(tp_df.round(1).to_string(index=False))
        print(ws_df.round(1).to_string(index=False))


if __name__ == "__main__":
    main(force="--force" in sys.argv)
