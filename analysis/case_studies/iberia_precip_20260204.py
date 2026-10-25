"""Iberia extreme precipitation: 24 h accumulation on 4 Feb 2026.

Window 4 Feb 2026 00 UTC -> 5 Feb 00 UTC (577 mm observed at Grazalema,
Sierra de Cadiz), verified at two lead times (lead = end of the window):

* T+24 h: 4 Feb 00 UTC run, steps 0-24
* T+48 h: 3 Feb 00 UTC run, steps 24-48

Models: IFS operational (od/0001), AIFS-single (ai/0001) and DestinE (rd/iekm,
falling back to rd/i4ql), drawn as filled contours for all of Iberia and for an
Andalusia zoom, and compared with SYNOP + HDOBS tp24 gauges.
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
from california_ar_2024 import TP_CMAP, TP_LEVELS, TP_NORM  # noqa: E402
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

WINDOW_END = dt.datetime(2026, 2, 5, 0)
WINDOW_START = WINDOW_END - dt.timedelta(hours=24)
LEADS = (24, 48)

DOMAINS = {  # name: (W, E, S, N)
    "iberia": (-10.0, 4.5, 35.5, 44.5),
    "andalusia": (-7.6, -1.5, 35.8, 38.7),
}
# Padded beyond the domains so contours of coarse grids (AIFS ~30 km) reach the frame.
AREA = [45.2, -10.7, 34.8, 5.2]  # N, W, S, E

# (key, label, class, expver candidates, param)
MODELS = [
    ("ifs", "IFS operational", "od", ("0001",), "228"),
    ("aifs", "AIFS-single", "ai", ("0001",), "228"),
    ("destine", "DestinE", "rd", ("iekm", "i4ql"), "228.128"),
]

GRAZALEMA = (36.76, -5.37, 913)  # lat, lon, station elevation (m): 577 mm gauge
G = 9.80665
OROG_LEVELS = [
    1,
    100,
    200,
    300,
    400,
    500,
    600,
    800,
    1000,
    1200,
    1400,
    1700,
    2000,
    2500,
    3000,
    3500,
]
_terrain = plt.get_cmap("terrain")
OROG_CMAP = ListedColormap(_terrain(np.linspace(0.25, 0.97, len(OROG_LEVELS) - 1)))
OROG_CMAP.set_under("#cfe8f7")  # sea (model lsm < 0.5)
OROG_CMAP.set_over("#ffffff")
OROG_NORM = BoundaryNorm(OROG_LEVELS, ncolors=OROG_CMAP.N)

OBS_DIR = CACHE_DIR.parent / "observations" / "tp" / "tp_24h_iberia202602"
HELPERS_PKG = CACHE_DIR.parents[2] / "clickable_timeseries"
VINO_PATH = "/home/moz/bin/vino_getgeo"
MISSING = 3e38


def retrieve_tp24(spec: tuple, lead: int, force: bool = False):
    """Return the 24 h accumulation (mm) ending WINDOW_END for one model and lead."""
    key, _label, mclass, expvers, param = spec
    base = WINDOW_END - dt.timedelta(hours=lead)
    s0, s1 = lead - 24, lead
    tag = "_".join(f"{v:g}" for v in AREA)
    for expver in expvers:
        cache = (
            CACHE_DIR / f"ib26_{key}_{expver}_tp_{base:%Y%m%d%H}_{s0}_{s1}_{tag}.grib"
        )
        if cache.exists() and not force:
            ds = _as_fieldlist(ekd.from_source("file", str(cache)))
        else:
            request = {
                "class": mclass,
                "stream": "oper",
                "type": "fc",
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
                continue
            finally:
                _restore_tmpdir(orig)
            if len(ds) < 1:
                continue
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _save_fieldlist(ds, str(cache))
        by_step, units = {}, "m"
        for fld in ds:
            by_step[int(fld.metadata("step"))] = np.asarray(fld.to_numpy()).ravel()
            units = _field_units(fld, units)
        if s1 not in by_step:
            continue
        # Step 0 of tp is zero by definition and may be absent from the archive.
        acc = by_step[s1] - by_step.get(s0, 0.0)
        lats, lons = _field_latlon(ds[0])
        return {
            "expver": expver,
            "base": base,
            "s0": s0,
            "s1": s1,
            "lats": lats,
            "lons": (lons + 180.0) % 360.0 - 180.0,
            "tp": np.clip(_to_mm(acc, units), 0.0, None),
        }
    return None


def retrieve_orog(spec: tuple, force: bool = False):
    """Return model orography (m) and land-sea mask from the T+24 h run (step 0)."""
    key, _label, mclass, expvers, _param = spec
    base = WINDOW_END - dt.timedelta(hours=LEADS[0])
    tag = "_".join(f"{v:g}" for v in AREA)
    for expver in expvers:
        cache = CACHE_DIR / f"ib26_{key}_{expver}_z_lsm_{base:%Y%m%d%H}_{tag}.grib"
        if cache.exists() and not force:
            ds = _as_fieldlist(ekd.from_source("file", str(cache)))
        else:
            request = {
                "class": mclass,
                "stream": "oper",
                "type": "fc",
                "expver": expver,
                "levtype": "sfc",
                "param": "129/172",
                "date": base.strftime("%Y%m%d"),
                "time": base.strftime("%H%M"),
                "step": "0",
                "area": AREA,
                "expect": "any",
            }
            orig = _set_mars_tmpdir()
            try:
                ds = _as_fieldlist(ekd.from_source("mars", **request))
            except Exception as exc:  # noqa: BLE001
                print(f"  \u2717 MARS failed {key}/{expver} orography: {exc}")
                continue
            finally:
                _restore_tmpdir(orig)
            if len(ds) < 2:
                continue
            _save_fieldlist(ds, str(cache))
        fields = {f.metadata("shortName"): np.asarray(f.to_numpy()).ravel() for f in ds}
        if "z" not in fields or "lsm" not in fields:
            continue
        lats, lons = _field_latlon(ds[0])
        return {
            "expver": expver,
            "grid": ds[0].metadata("gridName"),
            "lats": lats,
            "lons": (lons + 180.0) % 360.0 - 180.0,
            "orog": fields["z"] / G,
            "lsm": fields["lsm"],
        }
    return None


def iberia_polygon():
    """Return the land outline of Spain and Portugal (Natural Earth 10 m)."""
    path = shpreader.natural_earth(
        resolution="10m", category="cultural", name="admin_0_countries"
    )
    geoms = [
        rec.geometry
        for rec in shpreader.Reader(path).records()
        if rec.attributes.get("ADMIN") in ("Spain", "Portugal")
    ]
    w, e, s, n = DOMAINS["iberia"]
    # Clip to the peninsula so the Canary Islands are excluded.
    return shapely.union_all(geoms).intersection(shapely.box(w, s, e, n))


def retrieve_obs(force: bool = False) -> None:
    """Retrieve SYNOP + HDOBS tp24 valid at WINDOW_END."""
    if sorted(OBS_DIR.glob(f"tp*_obs_{WINDOW_END:%Y%m%d%H}.geo")) and not force:
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


def load_obs(land) -> pd.DataFrame:
    """Return tp24 gauges valid at WINDOW_END in Iberia, one per location."""
    files = sorted(OBS_DIR.glob(f"tp*_obs_{WINDOW_END:%Y%m%d%H}.geo"))
    frames = [f for f in (_parse_geo_file(p, MISSING) for p in files) if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["stnid", "lat", "lon", "obs", "on_land"])
    obs = pd.concat(frames, ignore_index=True)
    w, e, s, n = DOMAINS["iberia"]
    obs = obs[
        (obs["valid_time"] == WINDOW_END)
        & obs["lat"].between(s, n)
        & obs["lon"].between(w, e)
    ]
    # SYNOP and HDOBS can report the same gauge under different identifiers.
    obs = obs.assign(
        _k=obs["lat"].round(3).astype(str) + obs["lon"].round(3).astype(str)
    )
    obs = obs.drop_duplicates("_k").drop(columns="_k")
    obs = obs.assign(on_land=shapely.contains_xy(land, obs["lon"], obs["lat"]))
    return obs.reset_index(drop=True)


def stats(res: dict, land, obs: pd.DataFrame) -> dict:
    """Land maximum/mean and gauge verification for one forecast."""
    lats, lons, tp = res["lats"], res["lons"], res["tp"]
    inside = shapely.contains_xy(land, lons, lats)
    i_max = np.argmax(np.where(inside, tp, -1))
    out = {
        "land_max_mm": float(tp[i_max]),
        "land_max_lat": float(lats[i_max]),
        "land_max_lon": float(lons[i_max]),
        "land_mean_mm": float(tp[inside].mean()),
    }
    w, e, s, n = DOMAINS["andalusia"]
    anda = inside & (lats >= s) & (lats <= n) & (lons >= w) & (lons <= e)
    out["andalusia_max_mm"] = float(tp[anda].max())
    g = obs[obs["on_land"]]
    if not g.empty:
        fc = tp[_nearest(lats, lons, g["lat"].to_numpy(), g["lon"].to_numpy())]
        ob = g["obs"].to_numpy()
        err = fc - ob
        heavy = ob >= 50
        out.update(
            n_gauges=len(g),
            gauge_mean_mm=float(ob.mean()),
            fc_at_gauges_mean_mm=float(fc.mean()),
            bias_mm=float(err.mean()),
            mae_mm=float(np.abs(err).mean()),
            rmse_mm=float(np.sqrt((err**2).mean())),
            corr=float(np.corrcoef(fc, ob)[0, 1]),
            n_gauges_ge50=int(heavy.sum()),
            hit_rate_50mm=float((fc[heavy] >= 50).mean()) if heavy.any() else np.nan,
            fc_at_max_gauge_mm=float(fc[np.argmax(ob)]),
        )
    return out


def _map_ax(fig, nrows, ncols, idx, extent):
    ax = fig.add_subplot(nrows, ncols, idx, projection=ccrs.PlateCarree())
    ax.set_extent(extent, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.COASTLINE.with_scale("10m"), linewidth=0.7, zorder=5)
    ax.add_feature(cfeature.BORDERS.with_scale("10m"), linewidth=0.8, zorder=5)
    ax.add_feature(
        cfeature.STATES.with_scale("10m"), linewidth=0.3, edgecolor="0.35", zorder=5
    )
    gl = ax.gridlines(draw_labels=True, linewidth=0.25, alpha=0.4)
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = gl.ylabel_style = {"size": 11}
    return ax, {"transform": ccrs.PlateCarree()}


def _colorbar(fig, mappable, rect):
    cax = fig.add_axes(rect)
    cb = fig.colorbar(
        mappable, cax=cax, orientation="horizontal", ticks=TP_LEVELS, extend="max"
    )
    cb.ax.set_xticklabels([f"{v:g}" for v in TP_LEVELS])
    cb.set_label("24 h precipitation (mm)", fontsize=15)
    cb.ax.tick_params(labelsize=11)


def _title_period() -> str:
    return f"{WINDOW_START:%d %b %HZ} \u2192 {WINDOW_END:%d %b %HZ} {WINDOW_END:%Y}"


def make_figure(results: dict, domain: str) -> str:
    """Draw the leads x models precipitation figure for one domain."""
    extent = DOMAINS[domain]
    aspect = (extent[1] - extent[0]) / (extent[3] - extent[2])
    nrows, ncols = len(LEADS), len(MODELS)
    pw = 6.6
    fig = plt.figure(figsize=(pw * ncols, pw / aspect * nrows + 3.0))
    cf = None
    for r, lead in enumerate(LEADS):
        for c, spec in enumerate(MODELS):
            ax, kw = _map_ax(fig, nrows, ncols, r * ncols + c + 1, extent)
            res = results.get((spec[0], lead))
            if res is None:
                ax.set_title(f"{spec[1]} T+{lead}h \u2014 unavailable", fontsize=14)
                continue
            cf = ax.tricontourf(
                res["lons"],
                res["lats"],
                res["tp"],
                levels=TP_LEVELS,
                cmap=TP_CMAP,
                norm=TP_NORM,
                extend="max",
                **kw,
            )
            st = res["stats"]
            label = f"{spec[1]} ({res['expver']})" if spec[0] == "destine" else spec[1]
            peak = (
                st["andalusia_max_mm"] if domain == "andalusia" else st["land_max_mm"]
            )
            ax.set_title(
                f"{label} \u2014 T+{lead}h ({res['s0']}\u2013{res['s1']}h)\n"
                f"run {res['base']:%d %b %HZ} | land max {peak:.0f} mm",
                fontsize=13,
            )
    if cf is not None:
        _colorbar(fig, cf, [0.08, 0.06, 0.84, 0.02])
    name = "Iberia" if domain == "iberia" else "Andalusia (zoom)"
    fig.suptitle(
        f"{name} \u2014 24 h precipitation {_title_period()}", fontsize=20, y=0.98
    )
    fig.subplots_adjust(
        left=0.04, right=0.98, top=0.88, bottom=0.14, hspace=0.3, wspace=0.12
    )
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / f"iberia_precip_{domain}_{WINDOW_END:%Y%m%d%H}.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return str(out)


def make_obs_figure(obs: pd.DataFrame, domain: str) -> str:
    """Draw the observed tp24 gauge map for one domain."""
    extent = DOMAINS[domain]
    aspect = (extent[1] - extent[0]) / (extent[3] - extent[2])
    fig = plt.figure(figsize=(12, 12 / aspect + 3.0))
    ax, kw = _map_ax(fig, 1, 1, 1, extent)
    w, e, s, n = extent
    o = obs[obs["lon"].between(w, e) & obs["lat"].between(s, n)].sort_values("obs")
    sc = ax.scatter(
        o["lon"],
        o["lat"],
        c=o["obs"],
        cmap=TP_CMAP,
        norm=TP_NORM,
        s=55 if domain == "iberia" else 110,
        edgecolor="k",
        linewidth=0.4,
        zorder=8,
        **kw,
    )
    top = o.iloc[-1] if not o.empty else None
    info = (
        f"n={len(o)}, max {top['obs']:.0f} mm ({top['lat']:.2f}\u00b0N {-top['lon']:.2f}\u00b0W), "
        f"{int((o['obs'] >= 100).sum())} gauges \u2265 100 mm"
        if top is not None
        else "no gauges"
    )
    ax.set_title(f"SYNOP + HDOBS \u2014 {info}", fontsize=14)
    _colorbar(fig, sc, [0.08, 0.07, 0.84, 0.022])
    name = "Iberia" if domain == "iberia" else "Andalusia (zoom)"
    fig.suptitle(
        f"{name} \u2014 observed 24 h precipitation\n{_title_period()}",
        fontsize=18,
        y=0.98,
    )
    fig.subplots_adjust(left=0.07, right=0.96, top=0.86, bottom=0.16)
    out = FIG_DIR / f"iberia_precip_obs_{domain}_{WINDOW_END:%Y%m%d%H}.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return str(out)


def make_orog_figure(orogs: dict, domain: str) -> str:
    """Draw one row of model orography panels for one domain."""
    extent = DOMAINS[domain]
    aspect = (extent[1] - extent[0]) / (extent[3] - extent[2])
    ncols = len(MODELS)
    pw = 6.6
    fig = plt.figure(figsize=(pw * ncols, pw / aspect + 2.0))
    w, e, s, n = extent
    cf = None
    for c, spec in enumerate(MODELS):
        ax, kw = _map_ax(fig, 1, ncols, c + 1, extent)
        res = orogs.get(spec[0])
        if res is None:
            ax.set_title(f"{spec[1]} \u2014 unavailable", fontsize=14)
            continue
        lats, lons = res["lats"], res["lons"]
        land = res["lsm"] >= 0.5
        cf = ax.tricontourf(
            lons,
            lats,
            np.where(land, res["orog"], -50.0),
            levels=OROG_LEVELS,
            cmap=OROG_CMAP,
            norm=OROG_NORM,
            extend="both",
            **kw,
        )
        dom = land & (lats >= s) & (lats <= n) & (lons >= w) & (lons <= e)
        at_gauge = res["orog"][_nearest(lats, lons, [GRAZALEMA[0]], [GRAZALEMA[1]])[0]]
        label = f"{spec[1]} ({res['expver']})" if spec[0] == "destine" else spec[1]
        ax.set_title(
            f"{label} \u2014 grid {res['grid']}\n"
            f"max {res['orog'][dom].max():.0f} m | Grazalema {at_gauge:.0f} m "
            f"(real {GRAZALEMA[2]} m)",
            fontsize=13,
        )
    if cf is not None:
        cax = fig.add_axes([0.08, 0.14, 0.84, 0.035])
        cb = fig.colorbar(
            cf, cax=cax, orientation="horizontal", ticks=OROG_LEVELS, extend="both"
        )
        cb.ax.set_xticklabels([f"{v:g}" for v in OROG_LEVELS])
        cb.set_label("Model orography (m); sea = model lsm < 0.5", fontsize=15)
        cb.ax.tick_params(labelsize=11)
    name = "Iberia" if domain == "iberia" else "Andalusia (zoom)"
    fig.suptitle(f"{name} \u2014 model orography", fontsize=20, y=0.98)
    fig.subplots_adjust(left=0.04, right=0.98, top=0.84, bottom=0.29, wspace=0.12)
    out = FIG_DIR / f"iberia_orography_{domain}.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return str(out)


def main(force: bool = False) -> None:
    """Retrieve forecasts and gauges, write statistics and figures."""
    land = iberia_polygon()
    retrieve_obs(force=force)
    obs = load_obs(land)
    print(f"Gauges: {len(obs)} ({int(obs['on_land'].sum())} on Iberian land)")
    for domain in DOMAINS:
        print(f"\u2713 Wrote {make_obs_figure(obs, domain)}")

    results: dict = {}
    rows = []
    for lead in LEADS:
        for spec in MODELS:
            res = retrieve_tp24(spec, lead, force=force)
            if res is None:
                print(f"  \u2717 {spec[1]} T+{lead}: no data")
                continue
            res["stats"] = stats(res, land, obs)
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
    csv = RESULTS_DIR / f"iberia_precip_{WINDOW_END:%Y%m%d%H}.csv"
    df.to_csv(csv, index=False, float_format="%.2f")
    with pd.option_context("display.width", 250, "display.max_columns", None):
        print(df.round(1).to_string(index=False))
    print(f"\u2713 Wrote {csv}")
    for domain in DOMAINS:
        print(f"\u2713 Wrote {make_figure(results, domain)}")

    orogs = {spec[0]: retrieve_orog(spec, force=force) for spec in MODELS}
    for domain in DOMAINS:
        print(f"\u2713 Wrote {make_orog_figure(orogs, domain)}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
