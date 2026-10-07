"""Three-day Alps 24 h precipitation comparison.

For each of three days (29 Jun, 30 Jun, 1 Jul 2024) a 3-panel row shows the
24 h precipitation accumulation from:

* STVL gauges (SYNOP + HDOBS), 24 h ending 00 UTC of the following day;
* the IFS deterministic forecast (od / 0001);
* the rd experiment ``expver=i4ql``.

Each model panel is the T+24 h accumulation, i.e. total precipitation from
step 0 to step 24 of that day's 00 UTC run (valid 00 UTC -> 00 UTC next day),
so obs and models share the same 24 h window.  Fields are kept at the model's
native resolution and drawn with triangulated contouring.
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

# Reuse the earthkit / MARS / unit helpers from the Baltic pipeline.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    _HAS_CARTOPY = True
except Exception:  # noqa: BLE001
    _HAS_CARTOPY = False

# --- Paths ------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_ROOT = REPO_ROOT / "analysis"
DATA_DIR = ANALYSIS_ROOT / "data"
FIG_DIR = ANALYSIS_ROOT / "figures"
CACHE_DIR = DATA_DIR / "forecasts_precip"
OBS_DIR = DATA_DIR / "observations" / "tp" / "tp_24h_alps"
HELPERS_PKG = REPO_ROOT / "clickable_timeseries"
VINO_PATH = "/home/moz/bin/vino_getgeo"

# --- Case definition --------------------------------------------------------
# Alps bounding box [North, West, South, East].
NORTH, WEST, SOUTH, EAST = 48.5, 5.5, 43.5, 15.5
DAYS = [dt.date(2024, 6, 29), dt.date(2024, 6, 30), dt.date(2024, 7, 1)]
MISSING = 3e38

# Models: (key, label, class, stream, type, expver, param).
MODELS = [
    ("ifs", "IFS deterministic", "od", "oper", "fc", "0001", "228"),
    ("i4ql", "rd i4ql", "rd", "oper", "fc", "i4ql", "228.128"),
]

# Discrete precip scale (mm / 24 h); higher than the Baltic case for Alpine totals.
LEVELS = [0.5, 1, 2, 5, 10, 20, 30, 50, 75, 100, 150]
CMAP = plt.get_cmap("turbo").copy()
NORM = BoundaryNorm(LEVELS, ncolors=CMAP.N, extend="max")


# --- Retrieval --------------------------------------------------------------
def retrieve_obs(force: bool = False) -> None:
    """Retrieve STVL tp24 (SYNOP + HDOBS) covering the three 00 UTC windows."""
    OBS_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(OBS_DIR.glob("tp*_obs_*.geo"))
    if existing and not force:
        print(
            f"\u2713 Alps tp24 obs already present ({len(existing)} files) in {OBS_DIR}"
        )
        return
    if str(HELPERS_PKG) not in sys.path:
        sys.path.insert(0, str(HELPERS_PKG))
    from helpers.observations_retriever import ObservationsRetriever  # noqa: PLC0415

    retriever = ObservationsRetriever(vino_path=VINO_PATH)
    # Windows end at 00 UTC of the day after each analysed day.
    start = (DAYS[0] + dt.timedelta(days=1)).strftime("%Y%m%d")
    end = (DAYS[-1] + dt.timedelta(days=1)).strftime("%Y%m%d")
    print(f"Retrieving STVL tp24 (synop hdobs) {start} \u2192 {end} at 00 UTC ...")
    retriever.retrieve(
        sources="synop hdobs",
        parameter="tp",
        period=24,
        start_date=start,
        end_date=end,
        times="00",
        output_dir=str(OBS_DIR),
    )


def load_obs_for_day(day: dt.date) -> pd.DataFrame:
    """Gauges for the 24 h window ending 00 UTC of ``day + 1``, in the Alps box."""
    valid = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0))
    files = sorted(OBS_DIR.glob("tp*_obs_*.geo"))
    frames = [_parse_geo_file(f, MISSING) for f in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["stnid", "lat", "lon", "valid_time", "obs"])
    obs = pd.concat(frames, ignore_index=True)
    obs = obs[obs["valid_time"] == valid]
    mask = (
        (obs["lat"] >= SOUTH)
        & (obs["lat"] <= NORTH)
        & (obs["lon"] >= WEST)
        & (obs["lon"] <= EAST)
    )
    obs = obs.loc[mask].copy()
    obs.drop_duplicates(subset="stnid", inplace=True)
    obs.reset_index(drop=True, inplace=True)
    return obs


def retrieve_model_tp24(spec: tuple, base: dt.datetime, force: bool = False):
    """0-24 h precip accumulation (mm) for one model/day at native resolution."""
    key, _label, mclass, stream, mtype, expver, param = spec
    s0, s1 = 0, 24
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"alps_{key}_tp_{base:%Y%m%d%H}_{s0}_{s1}.grib"
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
            _restore_tmpdir(orig)
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
    for fld in ds:
        step = int(fld.metadata("step"))
        by_step[step] = np.asarray(fld.to_numpy()).ravel()
        units = _field_units(fld, units)
    if s0 not in by_step or s1 not in by_step:
        print(f"  \u26a0 {key} {base:%Y-%m-%d %HZ}: missing step {s0} or {s1}")
        return None
    acc = np.clip(_to_mm(by_step[s1] - by_step[s0], units), 0.0, None)
    return lats, lons, acc


# --- Plotting ---------------------------------------------------------------
def _map_ax(fig, subplot):
    if _HAS_CARTOPY:
        ax = fig.add_subplot(*subplot, projection=ccrs.PlateCarree())
        ax.set_extent([WEST, EAST, SOUTH, NORTH], crs=ccrs.PlateCarree())
        ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        ax.add_feature(cfeature.BORDERS, linewidth=0.5)
        gl = ax.gridlines(draw_labels=True, linewidth=0.25, alpha=0.4)
        gl.top_labels = False
        gl.right_labels = False
        return ax, {"transform": ccrs.PlateCarree()}
    ax = fig.add_subplot(*subplot)
    ax.set_xlim(WEST, EAST)
    ax.set_ylim(SOUTH, NORTH)
    ax.grid(alpha=0.3)
    return ax, {}


def _draw_field(ax, lats, lons, values, kw):
    return ax.tricontourf(
        lons,
        lats,
        values,
        levels=LEVELS,
        cmap=CMAP,
        norm=NORM,
        extend="max",
        **kw,
    )


def _draw_obs(ax, obs, kw, s=45):
    return ax.scatter(
        obs["lon"],
        obs["lat"],
        c=obs["obs"],
        cmap=CMAP,
        norm=NORM,
        s=s,
        edgecolor="k",
        linewidth=0.5,
        zorder=5,
        **kw,
    )


def make_figure(obs_by_day: dict, models_by_day: dict, fname: str) -> Path:
    """3 rows (days) x 3 cols (gauges, IFS deterministic, i4ql)."""
    nrows, ncols = len(DAYS), 3
    fig = plt.figure(figsize=(15, 14))
    last_cf = None
    for r, day in enumerate(DAYS):
        window = f"{day:%d %b} 00Z \u2192 {day + dt.timedelta(days=1):%d %b} 00Z"
        # Column 0: gauges.
        ax, kw = _map_ax(fig, (nrows, ncols, r * ncols + 1))
        obs = obs_by_day.get(day)
        obs_plot = obs[obs["obs"] >= 1.0] if obs is not None else None
        if obs_plot is not None and not obs_plot.empty:
            _draw_obs(ax, obs_plot, kw, s=45)
            info = f"n={len(obs_plot)}, max {obs_plot['obs'].max():.0f} mm"
        else:
            info = "no gauges"
        ax.set_title(f"STVL gauges (SYNOP+HDOBS)\n{window}  ({info})", fontsize=10)

        # Columns 1-2: models, with gauges overlaid for reference.
        for c, spec in enumerate(MODELS, start=1):
            ax, kw = _map_ax(fig, (nrows, ncols, r * ncols + 1 + c))
            data = models_by_day.get(day, {}).get(spec[0])
            if data is None:
                ax.set_title(f"{spec[1]} \u2014 unavailable", fontsize=10)
                continue
            lats, lons, values = data
            last_cf = _draw_field(ax, lats, lons, values, kw)
            ax.set_title(
                f"{spec[1]} \u2014 T+24 h (0\u201324 h)\n{window}  "
                f"(max {values.max():.0f} mm)",
                fontsize=10,
            )

    if last_cf is not None:
        cbar_ax = fig.add_axes([0.35, 0.055, 0.32, 0.015])
        cb = fig.colorbar(last_cf, cax=cbar_ax, orientation="horizontal", extend="max")
        cb.set_label("24 h precipitation (mm)")
    fig.suptitle(
        "Alps 24 h precipitation \u2014 gauges vs IFS deterministic vs rd i4ql "
        "(T+24 h, 0\u201324 h accumulation)",
        fontsize=14,
        y=0.98,
    )
    fig.subplots_adjust(
        left=0.04, right=0.97, top=0.93, bottom=0.09, hspace=0.22, wspace=0.10
    )
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / fname
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def main(force: bool = False) -> None:
    """Retrieve gauges and forecasts, then draw the 3-day comparison figure."""
    retrieve_obs(force=force)
    obs_by_day = {day: load_obs_for_day(day) for day in DAYS}
    for day, obs in obs_by_day.items():
        n = 0 if obs is None else len(obs)
        mx = f"{obs['obs'].max():.0f} mm" if n else "-"
        print(f"  obs {day}: {n} gauges (max {mx})")
        if n:
            csv = OBS_DIR / f"alps_tp24_obs_{day:%Y%m%d}.csv"
            obs.to_csv(csv, index=False)
            print(f"    \u2192 {csv}")

    models_by_day: dict = {}
    for day in DAYS:
        base = dt.datetime.combine(day, dt.time(0))
        models_by_day[day] = {}
        for spec in MODELS:
            res = retrieve_model_tp24(spec, base, force=force)
            if res is not None:
                _lat, _lon, vals = res
                print(f"  {spec[0]} {day}: {vals.size} pts (max {vals.max():.0f} mm)")
            models_by_day[day][spec[0]] = res

    out = make_figure(obs_by_day, models_by_day, "alps_precip_3day.png")
    print(f"\u2713 Wrote {out}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
