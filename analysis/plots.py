"""Plotting for the HRES wind-speed verification study.

All figures use matplotlib only (cartopy is used for coastlines/borders when
available, otherwise the maps fall back to a plain lon/lat scatter).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from config import StudyConfig  # noqa: E402

try:  # optional geographic context
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    _HAS_CARTOPY = True
except Exception:  # noqa: BLE001
    _HAS_CARTOPY = False


def _map_ax(fig, cfg: StudyConfig, subplot=111):
    """Create a map axis with borders/coastlines if cartopy is available."""
    args = subplot if isinstance(subplot, tuple) else (subplot,)
    if _HAS_CARTOPY:
        ax = fig.add_subplot(*args, projection=ccrs.PlateCarree())
        ax.set_extent(
            [cfg.west, cfg.east, cfg.south, cfg.north], crs=ccrs.PlateCarree()
        )
        ax.add_feature(cfeature.COASTLINE, linewidth=0.6)
        ax.add_feature(cfeature.BORDERS, linewidth=0.6)
        ax.add_feature(cfeature.OCEAN, facecolor="#eef4fb")
        gl = ax.gridlines(draw_labels=True, linewidth=0.3, alpha=0.5)
        gl.top_labels = False
        gl.right_labels = False
        return ax, {"transform": ccrs.PlateCarree()}
    ax = fig.add_subplot(*args)
    ax.set_xlim(cfg.west, cfg.east)
    ax.set_ylim(cfg.south, cfg.north)
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°N)")
    ax.grid(alpha=0.3)
    return ax, {}


def plot_station_bias_map(
    cfg: StudyConfig, station_scores: pd.DataFrame, title: str, fname: str, s: int = 90
) -> Path:
    """Map of per-station mean error (fc − obs), diverging colour scale."""
    fig = plt.figure(figsize=(9, 8))
    ax, kw = _map_ax(fig, cfg)
    vmax = max(0.5, float(np.nanpercentile(np.abs(station_scores["bias"]), 95)))
    sc = ax.scatter(
        station_scores["lon"],
        station_scores["lat"],
        c=station_scores["bias"],
        cmap="RdBu_r",
        vmin=-vmax,
        vmax=vmax,
        s=s,
        edgecolor="k",
        linewidth=0.4,
        **kw,
    )
    cb = fig.colorbar(sc, ax=ax, shrink=0.8, pad=0.05)
    cb.set_label("Mean forecast error  (fc − obs)  [m/s]\nblue = under-forecast")
    ax.set_title(title)
    out = cfg.figures_dir / fname
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def plot_scores_by_lead(cfg: StudyConfig, by_lead: pd.DataFrame, fname: str) -> Path:
    """Bias and RMSE vs lead time, event vs baseline."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharex=True)
    colors = {"event": "#d1495b", "baseline": "#4a7ba6"}
    for period, grp in by_lead.groupby("period"):
        sub = grp.sort_values("lead_hours")
        axes[0].plot(
            sub["lead_hours"], sub["bias"], "-o", color=colors.get(period), label=period
        )
        axes[1].plot(
            sub["lead_hours"], sub["rmse"], "-o", color=colors.get(period), label=period
        )
    axes[0].axhline(0, color="k", lw=0.8)
    axes[0].set_title("Bias vs lead time")
    axes[0].set_xlabel("Lead time (h)")
    axes[0].set_ylabel("Bias fc − obs [m/s]")
    axes[1].set_title("RMSE vs lead time")
    axes[1].set_xlabel("Lead time (h)")
    axes[1].set_ylabel("RMSE [m/s]")
    for a in axes:
        a.grid(alpha=0.3)
        a.legend()
    out = cfg.figures_dir / fname
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def plot_daily_bias(cfg: StudyConfig, by_day: pd.DataFrame, fname: str) -> Path:
    """Daily mean bias bar chart with event days highlighted."""
    by_day = by_day.sort_values("valid_day")
    colors = ["#d1495b" if ev else "#8fb4d0" for ev in by_day["is_event"]]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar([str(d) for d in by_day["valid_day"]], by_day["bias"], color=colors)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("Daily mean bias fc − obs [m/s]\n(lead ≤ 24 h)")
    ax.set_title("Daily mean 10 m wind-speed bias (red = reported event days)")
    ax.tick_params(axis="x", rotation=90)
    ax.grid(alpha=0.3, axis="y")
    out = cfg.figures_dir / fname
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def plot_error_distribution(cfg: StudyConfig, pairs: pd.DataFrame, fname: str) -> Path:
    """Histogram of errors, event vs baseline."""
    fig, ax = plt.subplots(figsize=(9, 5))
    bins = np.linspace(-8, 8, 65)
    for label, color in (("baseline", "#4a7ba6"), ("event", "#d1495b")):
        sub = (
            pairs[pairs["is_event"]] if label == "event" else pairs[~pairs["is_event"]]
        )
        if sub.empty:
            continue
        ax.hist(
            sub["error"],
            bins=bins,
            density=True,
            alpha=0.55,
            color=color,
            label=f"{label} (bias={sub['error'].mean():.2f})",
        )
    ax.axvline(0, color="k", lw=0.8)
    ax.set_xlabel("Forecast error fc − obs [m/s]")
    ax.set_ylabel("Density")
    ax.set_title("Distribution of 10 m wind-speed errors")
    ax.legend()
    ax.grid(alpha=0.3)
    out = cfg.figures_dir / fname
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def plot_scatter(cfg: StudyConfig, pairs: pd.DataFrame, fname: str) -> Path:
    """Forecast-vs-observation scatter, event points highlighted."""
    fig, ax = plt.subplots(figsize=(7, 7))
    base = pairs[~pairs["is_event"]]
    ev = pairs[pairs["is_event"]]
    ax.scatter(
        base["obs"], base["fc"], s=6, alpha=0.15, color="#4a7ba6", label="baseline"
    )
    ax.scatter(
        ev["obs"], ev["fc"], s=14, alpha=0.6, color="#d1495b", label="event days"
    )
    lim = max(pairs["obs"].max(), pairs["fc"].max()) * 1.05
    ax.plot([0, lim], [0, lim], "k--", lw=1)
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("Observed 10 m wind speed [m/s]")
    ax.set_ylabel("Forecast 10 m wind speed [m/s]")
    ax.set_title("IFS-control forecast vs STVL observation")
    ax.legend()
    ax.grid(alpha=0.3)
    out = cfg.figures_dir / fname
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def plot_event_timeseries(
    cfg: StudyConfig, pairs: pd.DataFrame, fname: str, max_lead: int = 24
) -> Path:
    """Domain-mean forecast vs observation time series across event days."""
    sub = pairs[pairs["lead_hours"] <= max_lead].copy()
    ts = (
        sub.groupby("valid_time")
        .agg(fc=("fc", "mean"), obs=("obs", "mean"))
        .reset_index()
    )
    ts.sort_values("valid_time", inplace=True)
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(
        ts["valid_time"],
        ts["obs"],
        "-o",
        ms=3,
        color="#222",
        label="observed (domain mean)",
    )
    ax.plot(
        ts["valid_time"],
        ts["fc"],
        "-o",
        ms=3,
        color="#d1495b",
        label=f"IFS-control forecast (lead ≤ {max_lead} h)",
    )
    for d in cfg.event_days:
        ax.axvspan(
            pd.Timestamp(d),
            pd.Timestamp(d) + pd.Timedelta(days=1),
            color="#ffd5dd",
            alpha=0.5,
            zorder=0,
        )
    ax.set_ylabel("10 m wind speed [m/s]")
    ax.set_title(
        "Domain-mean 10 m wind speed: IFS-control vs observations (event days shaded)"
    )
    ax.legend()
    ax.grid(alpha=0.3)
    out = cfg.figures_dir / fname
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def plot_bias_rmse_timeseries(
    cfg: StudyConfig, pairs: pd.DataFrame, fname: str, max_lead: int = 24
) -> Path:
    """Bias and RMSE as a time series over the whole window (first-24h forecasts).

    Uses only pairs with ``lead_hours <= max_lead`` and scores every 3-hourly
    valid time; a bold daily-mean line is overlaid on the noisier 3-hourly
    series. Event days are shaded so their scores stand out against the month.
    """
    sub = pairs[pairs["lead_hours"] <= max_lead].copy()
    sub["valid_time"] = pd.to_datetime(sub["valid_time"])

    def _agg(df, key):
        g = df.groupby(key).agg(
            bias=("error", "mean"),
            rmse=("error", lambda e: float(np.sqrt((e**2).mean()))),
        )
        return g.reset_index()

    ts = _agg(sub, "valid_time").sort_values("valid_time")
    sub["valid_day"] = sub["valid_time"].dt.normalize()
    daily = _agg(sub, "valid_day").sort_values("valid_day")

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    for d in cfg.event_days:
        for a in axes:
            a.axvspan(
                pd.Timestamp(d),
                pd.Timestamp(d) + pd.Timedelta(days=1),
                color="#ffd5dd",
                alpha=0.6,
                zorder=0,
            )

    # Bias panel.
    axes[0].axhline(0, color="k", lw=0.8)
    axes[0].plot(
        ts["valid_time"],
        ts["bias"],
        "-",
        lw=0.8,
        color="#4a7ba6",
        alpha=0.6,
        label="3-hourly bias",
    )
    axes[0].plot(
        daily["valid_day"] + pd.Timedelta(hours=12),
        daily["bias"],
        "-o",
        ms=4,
        lw=2,
        color="#1f4e79",
        label="daily-mean bias",
    )
    axes[0].set_ylabel("Bias fc − obs [m/s]")
    axes[0].set_title(
        f"First-{max_lead}h IFS-control 10 m wind bias & RMSE over the window "
        "(event days shaded)"
    )
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.3)

    # RMSE panel.
    axes[1].plot(
        ts["valid_time"],
        ts["rmse"],
        "-",
        lw=0.8,
        color="#d1a15b",
        alpha=0.6,
        label="3-hourly RMSE",
    )
    axes[1].plot(
        daily["valid_day"] + pd.Timedelta(hours=12),
        daily["rmse"],
        "-o",
        ms=4,
        lw=2,
        color="#b3541e",
        label="daily-mean RMSE",
    )
    axes[1].set_ylabel("RMSE [m/s]")
    axes[1].set_xlabel("Valid time (UTC)")
    axes[1].legend(loc="upper right")
    axes[1].grid(alpha=0.3)

    out = cfg.figures_dir / fname
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def plot_event_day_bias_maps(
    cfg: StudyConfig, pairs: pd.DataFrame, fname: str, max_lead: int = 24
) -> Path:
    """Small-multiple maps of per-station mean error, one panel per event day.

    Lets the reader see whether the under-forecast is in the same place on each
    event day (systematic hotspots) or shifts around (case-by-case).
    """
    sub = pairs[(pairs["is_event"]) & (pairs["lead_hours"] <= max_lead)]
    days = list(cfg.event_days)
    per_day = {
        d: sub[sub["valid_day"] == d]
        .groupby("stnid")
        .agg(lat=("lat", "first"), lon=("lon", "first"), bias=("error", "mean"))
        for d in days
    }
    all_bias = np.concatenate(
        [g["bias"].to_numpy() for g in per_day.values() if len(g)]
    )
    vmax = max(1.0, float(np.nanpercentile(np.abs(all_bias), 95)))

    fig = plt.figure(figsize=(6 * len(days), 6))
    sc = None
    for j, d in enumerate(days, start=1):
        ax, kw = _map_ax(fig, cfg, subplot=(1, len(days), j))
        g = per_day[d]
        sc = ax.scatter(
            g["lon"],
            g["lat"],
            c=g["bias"],
            cmap="RdBu_r",
            vmin=-vmax,
            vmax=vmax,
            s=70,
            edgecolor="k",
            linewidth=0.4,
            **kw,
        )
        ax.set_title(f"{d}  (mean bias {g['bias'].mean():+.2f} m/s, n={len(g)})")
    cb = fig.colorbar(sc, ax=fig.axes, shrink=0.7, pad=0.02)
    cb.set_label("Mean forecast error  (fc − obs)  [m/s]\nblue = under-forecast")
    fig.suptitle(
        f"Per-station 10 m wind bias by event day (lead ≤ {max_lead} h)", y=1.02
    )
    out = cfg.figures_dir / fname
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_bias_event_vs_baseline(
    cfg: StudyConfig, pairs: pd.DataFrame, fname: str, max_lead: int = 24, s: int = 80
) -> Path:
    """Compare per-station usual bias, event-day bias and their difference.

    Panels 1 and 2 (usual vs event bias) share one colour scale so magnitudes
    are directly comparable; panel 3 shows event minus baseline, i.e. the extra
    under-forecast that appears only on the event days.
    """
    sub = pairs[pairs["lead_hours"] <= max_lead]
    base = (
        sub[~sub["is_event"]]
        .groupby("stnid")
        .agg(lat=("lat", "first"), lon=("lon", "first"), base=("error", "mean"))
    )
    ev = sub[sub["is_event"]].groupby("stnid").agg(ev=("error", "mean"))
    g = base.join(ev, how="inner").dropna()
    g["diff"] = g["ev"] - g["base"]

    scale = max(
        0.5, float(np.nanpercentile(np.abs(np.concatenate([g["base"], g["ev"]])), 95))
    )
    dscale = max(0.5, float(np.nanpercentile(np.abs(g["diff"]), 95)))
    edge = 0.4 if s >= 40 else 0.15

    panels = [
        ("base", "Usual bias (baseline days)", scale, "RdBu_r"),
        ("ev", "Event-day bias", scale, "RdBu_r"),
        ("diff", "Event − baseline\n(extra under-forecast)", dscale, "RdBu_r"),
    ]
    fig = plt.figure(figsize=(19, 6.5))
    for j, (col, label, vmax, cmap) in enumerate(panels, start=1):
        ax, kw = _map_ax(fig, cfg, subplot=(1, 3, j))
        sc = ax.scatter(
            g["lon"],
            g["lat"],
            c=g[col],
            cmap=cmap,
            vmin=-vmax,
            vmax=vmax,
            s=s,
            edgecolor="k",
            linewidth=edge,
            **kw,
        )
        cb = fig.colorbar(sc, ax=ax, shrink=0.75, pad=0.03)
        cb.set_label(f"{label}  [m/s]\nblue = under-forecast")
        ax.set_title(f"{label.splitlines()[0]}  (mean {g[col].mean():+.2f})")
    fig.suptitle(
        f"Per-station 10 m wind bias: usual vs event days and the difference "
        f"(lead ≤ {max_lead} h, n={len(g)} stations)",
        y=1.03,
    )
    out = cfg.figures_dir / fname
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_snapshot(
    cfg: StudyConfig, pairs: pd.DataFrame, valid_time, fname: str
) -> Path:
    """Three-panel spatial snapshot at a single valid time: obs, IFS-control, error.

    For each station the most recent forecast (smallest lead) valid at that time
    is used, so the panels show a coherent analysis-like picture of the miss.
    """
    vt = pd.Timestamp(valid_time)
    snap = pairs[pairs["valid_time"] == vt].sort_values("lead_hours")
    snap = snap.drop_duplicates("stnid", keep="first")  # smallest lead per station
    wind_max = max(
        1.0, float(np.nanpercentile(np.concatenate([snap["obs"], snap["fc"]]), 98))
    )
    emax = max(1.0, float(np.nanpercentile(np.abs(snap["error"]), 95)))

    fig = plt.figure(figsize=(19, 6))
    panels = [
        ("obs", "Observed 10 m wind [m/s]", "viridis", 0, wind_max),
        ("fc", "IFS-control 10 m wind [m/s]", "viridis", 0, wind_max),
        ("error", "Error fc − obs [m/s]\nblue = under-forecast", "RdBu_r", -emax, emax),
    ]
    for j, (col, label, cmap, vmin, vmax) in enumerate(panels, start=1):
        ax, kw = _map_ax(fig, cfg, subplot=(1, 3, j))
        sc = ax.scatter(
            snap["lon"],
            snap["lat"],
            c=snap[col],
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            s=75,
            edgecolor="k",
            linewidth=0.4,
            **kw,
        )
        cb = fig.colorbar(sc, ax=ax, shrink=0.75, pad=0.03)
        cb.set_label(label)
        ax.set_title(label.split("\n")[0])
    fig.suptitle(
        f"Spatial snapshot at {vt:%Y-%m-%d %H:%M} UTC  "
        f"(mean obs {snap['obs'].mean():.1f}, mean IFS-control {snap['fc'].mean():.1f}, "
        f"mean error {snap['error'].mean():+.2f} m/s)",
        y=1.02,
    )
    out = cfg.figures_dir / fname
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_under_forecast_frequency(
    cfg: StudyConfig, pairs: pd.DataFrame, fname: str, max_lead: int = 24
) -> Path:
    """Map of how often each station is under-forecast on the event days.

    Distinguishes stations that are almost always low (robust hotspots) from
    those that only occasionally miss (case-specific noise).
    """
    sub = pairs[(pairs["is_event"]) & (pairs["lead_hours"] <= max_lead)]
    g = sub.groupby("stnid").agg(
        lat=("lat", "first"),
        lon=("lon", "first"),
        frac_under=("error", lambda e: float((e < 0).mean())),
        n=("error", "size"),
    )
    fig = plt.figure(figsize=(9, 8))
    ax, kw = _map_ax(fig, cfg)
    sc = ax.scatter(
        g["lon"],
        g["lat"],
        c=100 * g["frac_under"],
        cmap="OrRd",
        vmin=0,
        vmax=100,
        s=90,
        edgecolor="k",
        linewidth=0.4,
        **kw,
    )
    cb = fig.colorbar(sc, ax=ax, shrink=0.8, pad=0.05)
    cb.set_label("Share of event-day times under-forecast [%]")
    ax.set_title(f"Under-forecast frequency on event days (lead ≤ {max_lead} h)")
    out = cfg.figures_dir / fname
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out
