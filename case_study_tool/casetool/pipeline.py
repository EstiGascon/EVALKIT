"""End-to-end case evaluation: retrieve, derive, verify, plot, write tables."""

from __future__ import annotations

import numpy as np
import pandas as pd

from casetool import fields as F
from casetool import observations as O
from casetool import plotting as P
from casetool.config import VARIABLES, CaseConfig, check
from casetool.mars import build_jobs, fetch_all
from casetool.regions import build_region
from casetool.stats import field_summary, station_scores


def describe(cfg: CaseConfig) -> str:
    """Return a human-readable plan of what will be retrieved and compared."""
    lines = [
        f"Case: {cfg.name}  ({cfg.title or 'no title'})",
        f"Variable: {VARIABLES[cfg.variable]['label']} ({cfg.window.statistic}), "
        f"window {cfg.window.describe()}",
        f"Domain [W,E,S,N]: {cfg.extent}  zooms: {list(cfg.zooms) or 'none'}",
        f"MARS area [N,W,S,E]: {cfg.area()}",
        "Model runs:",
    ]
    for lead in cfg.leads:
        base = cfg.base_time(lead)
        for m in cfg.models:
            steps = cfg.steps(m, lead)
            shown = (
                steps
                if len(steps) <= 6
                else f"{steps[0]}..{steps[-1]} ({len(steps)} steps)"
            )
            lines.append(
                f"  T+{lead:>3}h  {m.label:<22} {m.mars_class}/{'|'.join(m.expvers)}  "
                f"run {base:%Y-%m-%d %HZ}  steps {shown}"
            )
    p = O.plan(cfg)
    if not cfg.observations.enabled:
        lines.append("Observations: disabled")
    elif p is None:
        lines.append("Observations: no matching SYNOP/HDOBS product for this window")
    else:
        lines.append(
            f"Observations: {p['param']}{p['period'] or ''} x {len(p['times'])} time(s), "
            f"aggregated by {p['how']} (min coverage {cfg.observations.min_coverage:.0%})"
        )
    try:
        _geom, label = build_region(cfg.region, cfg.extent)
        lines.append(f"Statistics region: {label}")
    except ValueError as exc:
        lines.append(f"WARNING: {exc}")
    problems = check(cfg)
    lines += [f"WARNING: {msg}" for _k, _l, msg in problems] or ["Checks: OK"]
    return "\n".join(lines)


def _valid_pairs(cfg: CaseConfig) -> set[tuple[str, int]]:
    bad = {(key, lead) for key, lead, _msg in check(cfg)}
    return {(m.key, ld) for m in cfg.models for ld in cfg.leads} - bad


def _derive(cfg: CaseConfig, results: dict) -> tuple[dict, dict]:
    fields, orogs = {}, {}
    for (key, lead), (job, path, expver, msg) in results.items():
        if path is None:
            print(f"  \u2717 {job.label} {lead}: {msg}")
            continue
        model = next(m for m in cfg.models if m.key == key)
        try:
            if lead == "orog":
                lats, lons, orog, lsm, grid = F.orography(path)
                orogs[key] = F.Field(
                    key,
                    model.label,
                    expver,
                    None,
                    None,
                    [0],
                    grid,
                    lats,
                    lons,
                    orog,
                    lsm,
                )
                continue
            steps = cfg.steps(model, lead)
            if cfg.variable == "tp":
                s0 = lead - cfg.window.hours
                lats, lons, vals, grid = F.precipitation(path, s0, lead)
                steps = [s0, lead]
            else:
                lats, lons, vals, grid, _n = F.wind_speed(
                    path, steps, cfg.window.statistic
                )
            fields[(key, lead)] = F.Field(
                key,
                model.label,
                expver,
                lead,
                cfg.base_time(lead),
                steps,
                grid,
                lats,
                lons,
                vals,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  \u2717 {model.label} {lead}: {exc}")
    return fields, orogs


def run(
    cfg: CaseConfig,
    force: bool = False,
    workers: int = 6,
    with_obs: bool = True,
) -> dict:
    """Run the full case; return a dict of written output paths and tables."""
    print(describe(cfg))
    # Fail on a misspelt region before spending time on retrievals.
    region, region_label = build_region(cfg.region, cfg.extent)
    valid = _valid_pairs(cfg)

    results = fetch_all(build_jobs(cfg, valid), workers=workers, force=force)
    fields, orogs = _derive(cfg, results)
    if not fields:
        raise RuntimeError("No model field could be retrieved; see messages above.")

    obs = pd.DataFrame()
    if with_obs and cfg.observations.enabled:
        try:
            directory = O.retrieve(cfg, force=force)
            if directory is None:
                print("Observations: no matching product for this window; skipped.")
            else:
                obs = O.load(cfg, directory)
                print(f"Observations: {len(obs)} station(s) after aggregation")
        except Exception as exc:  # noqa: BLE001
            print(f"Observations unavailable: {exc}")

    region_plot = region if cfg.region else None
    obs_region = obs
    if not obs.empty:
        import shapely  # noqa: PLC0415

        obs_region = obs[shapely.contains_xy(region, obs["lon"], obs["lat"])]

    scores, cont_rows, cat_rows = {}, [], []
    for (key, lead), fld in fields.items():
        if key in orogs and orogs[key].lsm is not None and cfg.region:
            fld.lsm = orogs[key].lsm if orogs[key].lsm.size == fld.values.size else None
        summ = field_summary(fld, region, region_label)
        cont, cats = station_scores(fld, obs_region, cfg.thresholds)
        scores[(key, lead)] = {**summ, **cont}
        meta = {
            "model": fld.label,
            "expver": fld.expver,
            "lead_h": lead,
            "init": f"{fld.base:%Y-%m-%d %HZ}",
            "steps": f"{fld.steps[0]}-{fld.steps[-1]}",
            "grid": fld.grid,
        }
        cont_rows.append({**meta, **summ, **cont})
        cat_rows += [{**meta, **c} for c in cats]
    order = {m.label: i for i, m in enumerate(cfg.models)}
    cont_df = pd.DataFrame(cont_rows).sort_values(
        ["lead_h", "model"], key=lambda s: s.map(order) if s.name == "model" else s
    )
    cat_df = pd.DataFrame(cat_rows)

    outputs = {"scores": cfg.output_path("scores.csv")}
    cont_df.to_csv(outputs["scores"], index=False, float_format="%.3f")
    if not cat_df.empty:
        outputs["categorical"] = cfg.output_path("categorical_scores.csv")
        cat_df.to_csv(outputs["categorical"], index=False, float_format="%.3f")
    if not obs.empty:
        outputs["observations"] = cfg.output_path("observations.csv")
        obs.to_csv(outputs["observations"], index=False, float_format="%.2f")

    peaks = [float(np.nanmax(f.values)) for f in fields.values()]
    if not obs.empty:
        peaks.append(float(obs["obs"].max()))
    scale = P.choose_scale(cfg.variable, max(peaks), cfg.plot.levels)
    head = cfg.title or cfg.name
    what = f"{P.cfg_label(cfg)} \u2014 {cfg.window.describe()}"
    for dname, extent in cfg.domains.items():
        tag = "" if dname == "domain" else f"_{dname}"
        sub = f" ({dname})" if tag else ""
        outputs[f"panel{tag}"] = P.panel_figure(
            cfg, fields, obs, scores, scale, extent, region_plot,
            f"{head}{sub}\n{what}", cfg.output_path(f"panel{tag}.png"),
        )  # fmt: skip
        if not obs.empty:
            outputs[f"obs_map{tag}"] = P.obs_figure(
                cfg, obs, scale, extent, region_plot,
                f"{head}{sub} \u2014 observations\n{what}",
                cfg.output_path(f"observations{tag}.png"),
            )  # fmt: skip
        if orogs:
            outputs[f"orography{tag}"] = P.orography_figure(
                cfg, orogs, extent, region_plot, f"{head}{sub} \u2014 model orography",
                cfg.output_path(f"orography{tag}.png"),
            )  # fmt: skip
    if not obs.empty:
        outputs["scores_plot"] = P.scores_figure(
            cfg, cont_df, cat_df, f"{head} \u2014 scores vs {len(obs_region)} stations ({region_label})",
            cfg.output_path("scores.png"),
        )  # fmt: skip

    cols = [c for c in ("model", "expver", "lead_h", "init", "region_max", "region_mean",
                        "n_obs", "bias", "rmse", "corr", "obs_max", "fc_at_obs_max")
            if c in cont_df]  # fmt: skip
    with pd.option_context("display.width", 220, "display.max_columns", None):
        print(cont_df[cols].round(2).to_string(index=False))
    print("Outputs:")
    for name, path in outputs.items():
        if path:
            print(f"  {name:<14} {path}")
    return outputs
