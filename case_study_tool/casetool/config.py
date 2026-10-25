"""Case configuration: loading, defaults and validation."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from casetool.models import ModelSpec, model_from_config

TOOL_ROOT = Path(__file__).resolve().parents[1]

VARIABLES = {
    "tp": {"label": "Precipitation", "unit": "mm", "statistics": ("sum",)},
    "ws10": {
        "label": "10 m wind speed",
        "unit": "m/s",
        "statistics": ("instant", "max", "mean"),
    },
}
DEFAULT_THRESHOLDS = {"tp": [1, 10, 25, 50, 100], "ws10": [10, 15, 20, 25]}


@dataclass
class Window:
    """Verification window: ``hours`` long, ending at ``end`` (0 h = instantaneous)."""

    end: dt.datetime
    hours: int
    statistic: str

    @property
    def start(self) -> dt.datetime:
        """Return the start of the window."""
        return self.end - dt.timedelta(hours=self.hours)

    def describe(self) -> str:
        """Return a short human-readable description of the window."""
        if self.hours == 0:
            return f"valid {self.end:%d %b %Y %H} UTC"
        return f"{self.start:%d %b %HZ} \u2192 {self.end:%d %b %HZ} {self.end:%Y}"


@dataclass
class Observations:
    """Observation settings (SYNOP/HDOBS via VINO)."""

    enabled: bool = True
    sources: tuple[str, ...] = ("synop", "hdobs")
    min_coverage: float = 1.0
    wind_interval_h: int = 3
    vino_path: str = "/home/moz/bin/vino_getgeo"


@dataclass
class PlotOptions:
    """Plot appearance."""

    style: str = "contour"  # contour | gridbox
    levels: list[float] | None = None  # None = automatic
    orography: bool = True
    dpi: int = 120


@dataclass
class CaseConfig:
    """Everything needed to run one case study."""

    name: str
    variable: str
    window: Window
    leads: list[int]
    models: list[ModelSpec]
    extent: tuple[float, float, float, float]  # W, E, S, N
    title: str = ""
    zooms: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    region: dict | None = None
    observations: Observations = field(default_factory=Observations)
    thresholds: list[float] = field(default_factory=list)
    plot: PlotOptions = field(default_factory=PlotOptions)
    model_interval_h: int = 3  # spacing of model outputs for ws10 max/mean
    output_dir: Path = TOOL_ROOT / "output"
    cache_dir: Path = TOOL_ROOT / "cache"

    @property
    def unit(self) -> str:
        """Return the unit of the evaluated variable."""
        return VARIABLES[self.variable]["unit"]

    @property
    def domains(self) -> dict[str, tuple[float, float, float, float]]:
        """Return the main domain followed by any zoom domains."""
        return {"domain": self.extent, **self.zooms}

    def area(self, pad: float = 0.7) -> list[float]:
        """Return the padded MARS area [N, W, S, E] covering all domains."""
        boxes = list(self.domains.values())
        w = min(b[0] for b in boxes) - pad
        e = max(b[1] for b in boxes) + pad
        s = min(b[2] for b in boxes) - pad
        n = max(b[3] for b in boxes) + pad
        return [
            round(min(n, 90.0), 2),
            round(w, 2),
            round(max(s, -90.0), 2),
            round(e, 2),
        ]

    def base_time(self, lead: int) -> dt.datetime:
        """Return the initialisation time whose lead to the window end is ``lead``."""
        return self.window.end - dt.timedelta(hours=lead)

    def steps(self, model: ModelSpec, lead: int) -> list[int]:
        """Return the forecast steps needed for ``model`` at ``lead``."""
        s1 = lead
        s0 = lead - self.window.hours
        if self.variable == "tp":
            return [s0, s1] if s0 > 0 else [s1]
        if self.window.statistic == "instant":
            return [s1]
        return model.steps_between(s0, s1, self.model_interval_h)

    def output_path(self, *parts: str) -> Path:
        """Return a path inside this case's output directory (created on demand)."""
        path = self.output_dir / self.name
        path.mkdir(parents=True, exist_ok=True)
        return path.joinpath(*parts)


def _parse_time(value) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time(0))
    text = str(value).strip().replace("T", " ").rstrip("Z")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H", "%Y%m%d %H", "%Y-%m-%d", "%Y%m%d%H"):
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse time {value!r} (use e.g. '2026-02-05 00')")


def _box(value, what: str) -> tuple[float, float, float, float]:
    if len(value) != 4:
        raise ValueError(f"{what} must be [W, E, S, N], got {value!r}")
    w, e, s, n = (float(v) for v in value)
    if not (w < e and s < n):
        raise ValueError(f"{what} must satisfy W < E and S < N, got {value!r}")
    return w, e, s, n


def _options(cls, value, what: str):
    """Build dataclass ``cls`` from a mapping, rejecting unknown keys."""
    value = dict(value or {})
    unknown = sorted(set(value) - set(cls.__dataclass_fields__))
    if unknown:
        raise ValueError(
            f"Unknown {what} option(s) {unknown}; known: {sorted(cls.__dataclass_fields__)}"
        )
    return cls(**value)


def config_from_dict(raw: dict, base_dir: Path | None = None) -> CaseConfig:
    """Build and validate a CaseConfig from a parsed YAML mapping."""
    raw = dict(raw or {})
    missing = [
        k for k in ("name", "window", "leads", "models", "domain") if k not in raw
    ]
    if missing:
        raise ValueError(f"Missing required option(s) {missing}")
    variable = raw.pop("variable", "tp")
    if variable not in VARIABLES:
        raise ValueError(
            f"variable must be one of {sorted(VARIABLES)}, got {variable!r}"
        )

    win = dict(raw.pop("window"))
    statistic = win.pop("statistic", VARIABLES[variable]["statistics"][0])
    if statistic not in VARIABLES[variable]["statistics"]:
        raise ValueError(
            f"statistic {statistic!r} not valid for {variable}; "
            f"use one of {VARIABLES[variable]['statistics']}"
        )
    hours = int(win.pop("hours", 24 if variable == "tp" else 0))
    if statistic == "instant":
        hours = 0
    if variable == "tp" and hours <= 0:
        raise ValueError("Precipitation needs window.hours > 0")
    if statistic in ("max", "mean") and hours <= 0:
        raise ValueError(f"statistic {statistic!r} needs window.hours > 0")
    window = Window(_parse_time(win.pop("end")), hours, statistic)
    if win:
        raise ValueError(f"Unknown window option(s) {sorted(win)}")

    dom = dict(raw.pop("domain"))
    extent = _box(dom.pop("extent"), "domain.extent")
    zooms = {k: _box(v, f"domain.zooms.{k}") for k, v in dom.pop("zooms", {}).items()}
    if dom:
        raise ValueError(f"Unknown domain option(s) {sorted(dom)}")

    obs = _options(Observations, raw.pop("observations", None), "observations")
    obs.sources = tuple(obs.sources)
    plot = _options(PlotOptions, raw.pop("plot", None), "plot")
    if plot.style not in ("contour", "gridbox"):
        raise ValueError("plot.style must be 'contour' or 'gridbox'")

    base_dir = base_dir or Path.cwd()

    def _dir(key, default):
        value = raw.pop(key, None)
        if value is None:
            return default
        p = Path(value).expanduser()
        return p if p.is_absolute() else (base_dir / p).resolve()

    leads = sorted({int(v) for v in raw.pop("leads")})
    models = [model_from_config(m) for m in raw.pop("models")]
    for attr in ("key", "label"):
        values = [getattr(m, attr) for m in models]
        dupes = sorted({v for v in values if values.count(v) > 1})
        if dupes:
            raise ValueError(
                f"Duplicate model {attr}(s) {dupes}; give each entry its own 'label'"
            )
    cfg = CaseConfig(
        name=str(raw.pop("name")),
        title=str(raw.pop("title", "")),
        variable=variable,
        window=window,
        leads=leads,
        models=models,
        extent=extent,
        zooms=zooms,
        region=raw.pop("region", None),
        observations=obs,
        thresholds=[
            float(t) for t in raw.pop("thresholds", DEFAULT_THRESHOLDS[variable])
        ],
        plot=plot,
        model_interval_h=int(raw.pop("model_interval_h", 3)),
        output_dir=_dir("output_dir", TOOL_ROOT / "output"),
        cache_dir=_dir("cache_dir", TOOL_ROOT / "cache"),
    )
    if raw:
        raise ValueError(f"Unknown top-level option(s) {sorted(raw)}")
    return cfg


def load_config(path: str | Path) -> CaseConfig:
    """Load a case YAML file; relative paths in it are resolved from the repo root."""
    path = Path(path)
    with path.open() as fh:
        raw = yaml.safe_load(fh)
    return config_from_dict(raw, base_dir=TOOL_ROOT.parent)


def check(cfg: CaseConfig) -> list[tuple[str, int, str]]:
    """Return (model key, lead, message) for each run/step combination that cannot be retrieved."""
    problems = []
    for lead in cfg.leads:
        base = cfg.base_time(lead)
        for model in cfg.models:
            if base.hour not in model.cycles:
                msg = f"no {base:%H}Z run (cycles {model.cycles}) for T+{lead}h"
            elif lead < cfg.window.hours:
                msg = f"T+{lead}h is shorter than the window"
            else:
                steps = cfg.steps(model, lead)
                missing = [s for s in steps if s > 0 and not model.has_step(s)]
                if steps and not missing:
                    continue
                msg = f"steps {missing or 'none'} not archived for T+{lead}h"
            problems.append((model.key, lead, f"{model.label}: {msg}"))
    return problems
