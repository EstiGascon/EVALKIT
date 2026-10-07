"""Maps and diagnostic graphs for the Baltic precipitation misplacement study."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import BoundaryNorm  # noqa: E402

from precip_config import PrecipConfig  # noqa: E402
from precip_forecasts import PrecipField  # noqa: E402

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    _HAS_CARTOPY = True
except Exception:  # noqa: BLE001
    _HAS_CARTOPY = False

# Discrete precipitation scale (mm / 24 h) shared by every panel.
LEVELS = [0.5, 1, 2, 5, 10, 15, 20, 30, 40, 60, 80]
CMAP = plt.get_cmap("turbo").copy()
NORM = BoundaryNorm(LEVELS, ncolors=CMAP.N, extend="max")

MODEL_COLORS = {"ifs": "#1f77b4", "aifs": "#d62728", "j1l8": "#2ca02c"}


def _map_ax(fig, cfg: PrecipConfig, subplot=111):
    args = subplot if isinstance(subplot, tuple) else (subplot,)
    if _HAS_CARTOPY:
        ax = fig.add_subplot(*args, projection=ccrs.PlateCarree())
        ax.set_extent([cfg.west, cfg.east, cfg.south, cfg.north], crs=ccrs.PlateCarree())
        ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        ax.add_feature(cfeature.BORDERS, linewidth=0.5)
        gl = ax.gridlines(draw_labels=True, linewidth=0.25, alpha=0.4)
        gl.top_labels = False
        gl.right_labels = False
        return ax, {"transform": ccrs.PlateCarree()}
    ax = fig.add_subplot(*args)
    ax.set_xlim(cfg.west, cfg.east)
    ax.set_ylim(cfg.south, cfg.north)
    ax.grid(alpha=0.3)
    return ax, {}


def _draw_field(ax, field: PrecipField, kw: dict):
    """Filled 24 h precip field at the model's native resolution.

    Uses triangulated contouring so it works for both regular lat/lon grids
    (AIFS) and reduced-Gaussian grids (IFS), which are 1-D point sets.
    """
    return ax.tricontourf(
        field.lons, field.lats, field.tp24,
        levels=LEVELS, cmap=CMAP, norm=NORM, extend="max", **kw,
    )


def _draw_obs(ax, obs: pd.DataFrame, kw: dict, s: int = 45):
    """Overlay gauge tp24 as ringed points on the shared precip scale."""
    return ax.scatter(
        obs["lon"], obs["lat"], c=obs["obs"], cmap=CMAP, norm=NORM,
        s=s, edgecolor="k", linewidth=0.6, zorder=5, **kw,
    )


def plot_event_intercomparison(
    cfg: PrecipConfig, obs: pd.DataFrame, fields: dict[str, PrecipField], fname: str,
    subtitle: str | None = None, order: tuple[str, ...] = ("ifs", "aifs", "j1l8"),
) -> Path:
    """Gauges + the three models' 24 h forecast of the reported valid window."""
    fig = plt.figure(figsize=(15, 11))

    ax, kw = _map_ax(fig, cfg, (2, 2, 1))
    sc = _draw_obs(ax, obs, kw, s=70)
    ax.set_title(f"STVL gauges — 24 h to {cfg.window_end:%d %b %HZ}\n"
                 f"(n={len(obs)}, max {obs['obs'].max():.0f} mm)", fontsize=11)

    for i, key in enumerate(order, start=2):
        fld = fields.get(key)
        ax, kw = _map_ax(fig, cfg, (2, 2, i))
        if fld is None:
            ax.set_title(f"{key}: unavailable")
            continue
        cf = _draw_field(ax, fld, kw)
        _draw_obs(ax, obs, kw, s=32)
        ax.set_title(
            f"{fld.label} — init {fld.base:%d %b %HZ}  (lead {fld.lead} h)\n"
            f"+{fld.step_start}\u2013{fld.step_end} h acc. \u00b7 max {fld.tp24.max():.0f} mm",
            fontsize=11,
        )
    cbar_ax = fig.add_axes([0.35, 0.06, 0.32, 0.018])
    cb = fig.colorbar(cf, cax=cbar_ax, orientation="horizontal", extend="max")
    cb.set_label("24 h precipitation (mm)")
    title = (
        "Baltic heavy-rain event — model forecasts vs gauges "
        f"(valid {cfg.window_start:%d %b %HZ} \u2192 {cfg.window_end:%d %b %HZ})"
    )
    if subtitle:
        title += f"\n{subtitle}"
    fig.suptitle(title, fontsize=14, y=0.98)
    fig.subplots_adjust(left=0.04, right=0.97, top=0.90, bottom=0.11, hspace=0.16, wspace=0.10)
    out = cfg.figures_dir / fname
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def plot_lead_time_comparison(
    cfg: PrecipConfig, obs: pd.DataFrame, fields_by_model: dict[str, list[PrecipField]], fname: str,
    order: tuple[str, ...] = ("ifs", "aifs", "j1l8"),
) -> Path:
    """Forecasts of the same valid window from up to three models, one row
    per lead time (i.e. per initialisation), so earlier lead times can be checked
    for the same misplacement seen in the reported run.
    """
    order = [k for k in order if k in fields_by_model]
    leads = sorted({f.lead for k in order for f in fields_by_model[k]})
    nrows, ncols = len(leads), len(order)
    fig = plt.figure(figsize=(5.2 * ncols, 3.6 * nrows))
    cf = None
    for r, lead in enumerate(leads):
        for c, key in enumerate(order):
            fld = next((f for f in fields_by_model[key] if f.lead == lead), None)
            ax, kw = _map_ax(fig, cfg, (nrows, ncols, r * ncols + c + 1))
            if fld is None:
                ax.set_title(f"{key}: unavailable")
                continue
            cf = _draw_field(ax, fld, kw)
            _draw_obs(ax, obs, kw, s=18)
            ax.set_title(
                f"{fld.label} — init {fld.base:%d %b %HZ}  (lead {fld.lead} h)\n"
                f"+{fld.step_start}–{fld.step_end} h acc. · max {fld.tp24.max():.0f} mm",
                fontsize=10,
            )
    if cf is not None:
        cbar_ax = fig.add_axes([0.35, 0.02, 0.32, 0.008])
        cb = fig.colorbar(cf, cax=cbar_ax, orientation="horizontal", extend="max")
        cb.set_label("24 h precipitation (mm)")
    labels = [fields_by_model[k][0].label for k in order]
    fig.suptitle(
        f"{' vs '.join(labels)} — same valid window at successive lead times\n"
        "(rings = gauges; checks whether the misplacement recurs at earlier lead times)",
        fontsize=14, y=0.995,
    )
    fig.subplots_adjust(left=0.03, right=0.98, top=0.93, bottom=0.04, hspace=0.28, wspace=0.10)
    out = cfg.figures_dir / fname
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def plot_predictability_grid(
    cfg: PrecipConfig, obs: pd.DataFrame, fields: list[PrecipField], fname: str, label: str
) -> Path:
    """Small-multiples of one model's forecast of the fixed window by lead time."""
    fields = sorted(fields, key=lambda f: f.lead)
    n = len(fields)
    ncols = 4
    nrows = int(np.ceil(n / ncols))
    fig = plt.figure(figsize=(4.2 * ncols, 3.9 * nrows))
    cf = None
    for i, fld in enumerate(fields, start=1):
        ax, kw = _map_ax(fig, cfg, (nrows, ncols, i))
        cf = _draw_field(ax, fld, kw)
        _draw_obs(ax, obs, kw, s=16)
        ax.set_title(f"init {fld.base:%d %b %HZ}  (lead {fld.lead} h)\n"
                     f"+{fld.step_start}–{fld.step_end} h acc. · "
                     f"max {fld.tp24.max():.0f} mm", fontsize=10)
    if cf is not None:
        cbar_ax = fig.add_axes([0.35, 0.045, 0.32, 0.014])
        cb = fig.colorbar(cf, cax=cbar_ax, orientation="horizontal", extend="max")
        cb.set_label("24 h precipitation (mm)")
    fig.suptitle(
        f"{label} — predictability of the {cfg.window_end:%d %b} Baltic rain "
        "across initialisation lead times (rings = gauges)",
        fontsize=14, y=0.99,
    )
    fig.subplots_adjust(left=0.03, right=0.98, top=0.93, bottom=0.09, hspace=0.22, wspace=0.08)
    out = cfg.figures_dir / fname
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def plot_displacement_summary(
    cfg: PrecipConfig, summary: pd.DataFrame, obs_lat: float, fname: str
) -> Path:
    """Northward displacement, bias and RMSE vs lead time for all models."""
    fig, axes = plt.subplots(1, 3, figsize=(17, 5))

    for key, sub in summary.groupby("model"):
        sub = sub.sort_values("lead")
        c = MODEL_COLORS.get(key, "k")
        lbl = sub["label"].iloc[0]
        axes[0].plot(sub["lead"], sub["cm_lat"], "-o", color=c, label=lbl)
        axes[1].plot(sub["lead"], sub["bias"], "-o", color=c, label=lbl)
        axes[2].plot(sub["lead"], sub["rmse"], "-o", color=c, label=lbl)

    axes[0].axhline(obs_lat, color="k", ls="--", lw=1.2, label="gauges")
    axes[0].set_title("Rain-mass mean latitude\n(higher = further north)")
    axes[0].set_ylabel("Mass-weighted latitude (°N)")
    axes[1].axhline(0, color="k", lw=0.8)
    axes[1].set_title("Bias vs gauges")
    axes[1].set_ylabel("Bias (mm)")
    axes[2].set_title("RMSE vs gauges")
    axes[2].set_ylabel("RMSE (mm)")
    for ax in axes:
        ax.set_xlabel("Lead time to end of 24 h window (h)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=9)
    fig.suptitle(
        "Predictability & skill of the Baltic 24 h rain event by model and lead time",
        fontsize=14,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = cfg.figures_dir / fname
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out
