"""Figures: model/lead panels with observations, observation map, orography, scores."""

from __future__ import annotations

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.colors import (  # noqa: E402
    BoundaryNorm,
    LinearSegmentedColormap,
    ListedColormap,
)

PC = ccrs.PlateCarree()

# Anchor colours: light blue -> greens -> yellow/orange -> reds -> magenta -> purple.
_PRECIP_ANCHORS = [
    "#e0f3fb", "#9fd3ef", "#4f9fdc", "#a6e07a", "#4fb83a", "#1f7f2a", "#fff176",
    "#ffc93c", "#ff9a26", "#f4511e", "#d01c1c", "#9e0020", "#ff3dc8", "#a417b0",
    "#4b0a7d",
]  # fmt: skip
_WIND_ANCHORS = [
    "#f7fbff", "#c6dbef", "#6cb0dd", "#9be27e", "#4fbf3a", "#fff176", "#ffc93c",
    "#ff9a26", "#f4511e", "#d01c1c", "#9e0020", "#ff3dc8", "#7a0ea8",
]  # fmt: skip
_TP_PRESETS = [
    (30, [0.5, 1, 2, 3, 5, 7.5, 10, 12.5, 15, 20, 25, 30]),
    (80, [0.5, 1, 2, 5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70, 80]),
    (160, [0.5, 1, 2, 5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70, 80, 100, 125, 150]),
    (650, [1, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 600]),
    (np.inf, [1, 5, 10, 20, 30, 50, 75, 100, 150, 200, 250, 300, 400, 500, 600, 750, 1000]),
]  # fmt: skip
_WS_LEVELS = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32, 36, 40]
OROG_LEVELS = [1, 100, 200, 300, 400, 500, 600, 800, 1000, 1200, 1400, 1700, 2000,
               2500, 3000, 3500, 4000, 4500]  # fmt: skip


class Scale:
    """Discrete colour scale (levels, colormap, norm)."""

    def __init__(self, levels, anchors, under="#ffffff", over="#1a0030"):
        """Build the colormap by sampling ``anchors`` at len(levels)-1 colours."""
        self.levels = list(levels)
        base = LinearSegmentedColormap.from_list("casetool", anchors)
        self.cmap = ListedColormap(base(np.linspace(0, 1, len(self.levels) - 1)))
        self.cmap.set_under(under)
        self.cmap.set_over(over)
        self.norm = BoundaryNorm(self.levels, ncolors=self.cmap.N)


def choose_scale(variable: str, peak: float, levels=None) -> Scale:
    """Return a colour scale for the variable that resolves values up to ``peak``."""
    if variable == "tp":
        if levels is None:
            levels = next(lv for limit, lv in _TP_PRESETS if peak <= limit)
        return Scale(levels, _PRECIP_ANCHORS)
    if levels is None:
        top = max(20.0, peak)
        levels = [v for v in _WS_LEVELS if v <= top + 4]
    return Scale(levels, _WIND_ANCHORS, under="#ffffff", over="#2a0050")


def orography_scale(peak: float) -> Scale:
    """Return a terrain colour scale covering heights up to ``peak``."""
    levels = [v for v in OROG_LEVELS if v <= peak + 500] or OROG_LEVELS[:6]
    terrain = plt.get_cmap("terrain")
    anchors = [terrain(x) for x in np.linspace(0.25, 0.97, 8)]
    return Scale(levels, anchors, under="#cfe8f7", over="#ffffff")


# --- Map helpers ----------------------------------------------------------------
def _aspect(extent) -> float:
    w, e, s, n = extent
    return (e - w) / (n - s)


def map_ax(fig, rect, extent, region=None):
    """Add a PlateCarree map axis at ``rect`` with coastlines, borders and region outline."""
    ax = fig.add_axes(rect, projection=PC)
    ax.set_extent(extent, crs=PC)
    ax.add_feature(cfeature.COASTLINE.with_scale("10m"), linewidth=0.6, zorder=5)
    ax.add_feature(cfeature.BORDERS.with_scale("10m"), linewidth=0.7, zorder=5)
    ax.add_feature(
        cfeature.STATES.with_scale("10m"), linewidth=0.25, edgecolor="0.4", zorder=5
    )
    if region is not None:
        ax.add_geometries(
            [region], PC, facecolor="none", edgecolor="k", linewidth=1.2, zorder=6
        )
    gl = ax.gridlines(draw_labels=True, linewidth=0.25, alpha=0.4)
    gl.top_labels = gl.right_labels = False
    gl.xlabel_style = gl.ylabel_style = {"size": 10}
    return ax


class Layout:
    """Grid of map panels with fixed-size (inch) margins for titles and labels."""

    def __init__(self, nrows, ncols, extent, title_lines=3, pw=5.4, head=1.0, foot=1.3):
        """Size each map from the domain aspect ratio and reserve room around it."""
        self.pw = pw
        self.ph = min(pw / _aspect(extent), 7.5)
        self.title_h = 0.2 + 0.2 * title_lines
        self.xlab_h = 0.4
        self.ylab_w = 0.75
        self.gap_w = 0.25
        self.head, self.foot = head, foot
        self.nrows, self.ncols = nrows, ncols
        self.width = ncols * (self.ylab_w + pw + self.gap_w) + 0.2
        self.height = head + nrows * (self.title_h + self.ph + self.xlab_h) + foot

    def rect(self, row, col):
        """Return the axes rectangle (figure fraction) of panel (row, col)."""
        x = 0.1 + col * (self.ylab_w + self.pw + self.gap_w) + self.ylab_w
        y_top = self.head + row * (self.title_h + self.ph + self.xlab_h) + self.title_h
        y = self.height - y_top - self.ph
        return [
            x / self.width,
            y / self.height,
            self.pw / self.width,
            self.ph / self.height,
        ]

    def bar_rect(self):
        """Return the colour-bar rectangle near the bottom of the figure."""
        return [0.1, 0.62 / self.height, 0.8, 0.22 / self.height]

    def suptitle_y(self):
        """Return the figure-fraction y of the main title."""
        return 1 - 0.1 / self.height


def _gridbox_verts(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Rectangular cells around each point of a grid organised in latitude rows."""
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
        y0 = np.full_like(x0, lat_lo[j])
        y1 = np.full_like(x0, lat_hi[j])
        verts[idx] = np.stack(
            [
                np.column_stack([x0, y0]),
                np.column_stack([x1, y0]),
                np.column_stack([x1, y1]),
                np.column_stack([x0, y1]),
            ],
            axis=1,
        )
    return verts


def draw_field(ax, lats, lons, values, scale: Scale, style: str, extend="max"):
    """Draw a native-grid field as filled contours or per-grid-box cells."""
    if style == "gridbox":
        pc = PolyCollection(
            _gridbox_verts(lats, lons),
            array=values,
            cmap=scale.cmap,
            norm=scale.norm,
            edgecolors="face",
            linewidths=0.1,
            transform=PC,
        )
        ax.add_collection(pc)
        return pc
    return ax.tricontourf(
        lons,
        lats,
        values,
        levels=scale.levels,
        cmap=scale.cmap,
        norm=scale.norm,
        extend=extend,
        transform=PC,
    )


def draw_obs(ax, obs: pd.DataFrame, scale: Scale, size: float):
    """Scatter station values coloured on the scale (largest values on top)."""
    o = obs.sort_values("obs")
    return ax.scatter(
        o["lon"],
        o["lat"],
        c=o["obs"],
        cmap=scale.cmap,
        norm=scale.norm,
        s=size,
        edgecolor="k",
        linewidth=0.4,
        zorder=8,
        transform=PC,
    )


def colorbar(fig, mappable, scale: Scale, label: str, rect, extend="max"):
    """Add a horizontal colour bar with one tick per level."""
    cax = fig.add_axes(rect)
    cb = fig.colorbar(
        mappable, cax=cax, orientation="horizontal", ticks=scale.levels, extend=extend
    )
    cb.ax.set_xticklabels([f"{v:g}" for v in scale.levels])
    cb.set_label(label, fontsize=14)
    cb.ax.tick_params(labelsize=10)


def _in_extent(df: pd.DataFrame, extent) -> pd.DataFrame:
    w, e, s, n = extent
    return df[df["lon"].between(w, e) & df["lat"].between(s, n)]


def _obs_info(obs: pd.DataFrame, unit: str) -> str:
    if obs.empty:
        return "no stations"
    top = obs.loc[obs["obs"].idxmax()]
    ns = "N" if top["lat"] >= 0 else "S"
    ew = "E" if top["lon"] >= 0 else "W"
    return (
        f"n={len(obs)}, max {top['obs']:.0f} {unit} "
        f"({abs(top['lat']):.2f}\u00b0{ns} {abs(top['lon']):.2f}\u00b0{ew})"
    )


# --- Figures ----------------------------------------------------------------------
def panel_figure(cfg, fields, obs, scores, scale, extent, region, title, path):
    """Rows = lead times; columns = observations + models."""
    leads = cfg.leads
    has_obs = obs is not None and not obs.empty
    ncols = len(cfg.models) + (1 if has_obs else 0)
    nrows = len(leads)
    lay = Layout(nrows, ncols, extent, title_lines=3)
    fig = plt.figure(figsize=(lay.width, lay.height))
    obs_dom = _in_extent(obs, extent) if has_obs else None
    size = max(12, min(70, 9000 / max(len(obs_dom), 1))) if has_obs else 0
    mappable = None
    for r, lead in enumerate(leads):
        col = 0
        if has_obs:
            ax = map_ax(fig, lay.rect(r, 0), extent, region)
            mappable = draw_obs(ax, obs_dom, scale, size)
            ax.set_title(
                f"Observations (SYNOP+HDOBS)\n{_obs_info(obs_dom, cfg.unit)}",
                fontsize=11,
            )
            col = 1
        for c, model in enumerate(cfg.models):
            ax = map_ax(fig, lay.rect(r, col + c), extent, region)
            fld = fields.get((model.key, lead))
            if fld is None:
                ax.set_title(f"{model.label} T+{lead}h\nunavailable", fontsize=11)
                continue
            mappable = draw_field(
                ax, fld.lats, fld.lons, fld.values, scale, cfg.plot.style
            )
            st = scores.get((model.key, lead), {})
            if "region_max_lon" in st:
                ax.plot(
                    st["region_max_lon"],
                    st["region_max_lat"],
                    marker="x",
                    color="k",
                    markersize=9,
                    mew=2,
                    zorder=9,
                    transform=PC,
                )
            name = model.label + (
                f" ({fld.expver})" if fld.expver != model.expver else ""
            )
            steps = (
                f"{fld.steps[0]}\u2013{fld.steps[-1]}h"
                if len(fld.steps) > 1
                else f"step {fld.steps[-1]}h"
            )
            lines = [
                f"{name} \u2014 T+{lead}h",
                f"run {fld.base:%d %b %HZ}, {steps} | max {st.get('region_max', np.nan):.0f} {cfg.unit}",
            ]
            if st.get("n_obs"):
                lines.append(
                    f"bias {st['bias']:+.1f}  RMSE {st['rmse']:.1f}  r {st['corr']:.2f}"
                )
            ax.set_title("\n".join(lines), fontsize=11)
    if mappable is not None:
        colorbar(fig, mappable, scale, cfg_label(cfg), lay.bar_rect())
    fig.suptitle(title, fontsize=17, y=lay.suptitle_y(), va="top")
    fig.savefig(path, dpi=cfg.plot.dpi)
    plt.close(fig)
    return path


def obs_figure(cfg, obs, scale, extent, region, title, path):
    """Single map of the aggregated station observations."""
    lay = Layout(1, 1, extent, title_lines=1, pw=11 if _aspect(extent) >= 1 else 8)
    fig = plt.figure(figsize=(lay.width, lay.height))
    ax = map_ax(fig, lay.rect(0, 0), extent, region)
    o = _in_extent(obs, extent)
    sc = draw_obs(ax, o, scale, max(15, min(90, 12000 / max(len(o), 1))))
    ax.set_title(f"SYNOP + HDOBS \u2014 {_obs_info(o, cfg.unit)}", fontsize=13)
    colorbar(fig, sc, scale, cfg_label(cfg), lay.bar_rect())
    fig.suptitle(title, fontsize=16, y=lay.suptitle_y(), va="top")
    fig.savefig(path, dpi=cfg.plot.dpi)
    plt.close(fig)
    return path


def orography_figure(cfg, orogs, extent, region, title, path):
    """One row of model orography panels (sea masked with each model's lsm)."""
    models = [m for m in cfg.models if m.key in orogs]
    if not models:
        return None
    w, e, s, n = extent
    peaks = []
    for m in models:
        f = orogs[m.key]
        box = (f.lats >= s) & (f.lats <= n) & (f.lons >= w) & (f.lons <= e)
        peaks.append(float(f.values[box].max()) if box.any() else 0.0)
    scale = orography_scale(max(peaks))
    lay = Layout(1, len(models), extent, title_lines=2)
    fig = plt.figure(figsize=(lay.width, lay.height))
    mappable = None
    for c, m in enumerate(models):
        f = orogs[m.key]
        ax = map_ax(fig, lay.rect(0, c), extent, region)
        land = f.lsm >= 0.5 if f.lsm is not None else np.ones_like(f.values, bool)
        mappable = draw_field(
            ax,
            f.lats,
            f.lons,
            np.where(land, f.values, -50.0),
            scale,
            cfg.plot.style,
            "both",
        )
        ax.set_title(
            f"{m.label} \u2014 grid {f.grid or '?'}\nmax {peaks[c]:.0f} m", fontsize=11
        )
    colorbar(
        fig,
        mappable,
        scale,
        "Model orography (m); sea = model land-sea mask < 0.5",
        lay.bar_rect(),
        extend="both",
    )
    fig.suptitle(title, fontsize=16, y=lay.suptitle_y(), va="top")
    fig.savefig(path, dpi=cfg.plot.dpi)
    plt.close(fig)
    return path


def scores_figure(cfg, cont: pd.DataFrame, cat: pd.DataFrame, title, path):
    """Bar charts of bias/RMSE/correlation and ETS against threshold."""
    if cont.empty or "rmse" not in cont:
        return None
    labels = [m.label for m in cfg.models]
    leads = cfg.leads
    fig, axes = plt.subplots(1, 4, figsize=(20, 4.8))
    width = 0.8 / max(len(leads), 1)
    x = np.arange(len(labels))
    for i, lead in enumerate(leads):
        sub = cont[cont["lead_h"] == lead].set_index("model").reindex(labels)
        for ax, col in zip(axes[:3], ("bias", "rmse", "corr"), strict=True):
            ax.bar(
                x + (i - (len(leads) - 1) / 2) * width,
                sub[col],
                width,
                label=f"T+{lead}h",
            )
    for ax, name in zip(
        axes[:3],
        (f"Bias ({cfg.unit})", f"RMSE ({cfg.unit})", "Correlation"),
        strict=True,
    ):
        ax.set_xticks(x, labels, rotation=15)
        ax.set_title(name)
        ax.axhline(0, color="k", linewidth=0.6)
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend()
    ax = axes[3]
    styles = ["-", "--", ":", "-."]
    for i, lead in enumerate(leads):
        for j, label in enumerate(labels):
            sub = cat[(cat["lead_h"] == lead) & (cat["model"] == label)]
            if not sub.empty:
                ax.plot(
                    sub["threshold"],
                    sub["ets"],
                    styles[i % len(styles)],
                    marker="o",
                    color=f"C{j}",
                    label=f"{label} T+{lead}h",
                )
    ax.set_xlabel(f"Threshold ({cfg.unit})")
    ax.set_title("Equitable threat score")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.suptitle(title, fontsize=15)
    fig.tight_layout()
    fig.savefig(path, dpi=cfg.plot.dpi)
    plt.close(fig)
    return path


def cfg_label(cfg) -> str:
    """Return the colour-bar label for the case variable and window."""
    if cfg.variable == "tp":
        return f"{cfg.window.hours} h accumulated precipitation (mm)"
    stat = {"instant": "", "max": "Maximum ", "mean": "Mean "}[cfg.window.statistic]
    return f"{stat}10 m wind speed (m/s)"
