"""SYNOP/HDOBS observations via VINO, aggregated to match the forecast quantity."""

from __future__ import annotations

import datetime as dt
import os
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from casetool.config import CaseConfig

MISSING = 3e38


def plan(cfg: CaseConfig) -> dict | None:
    """Return how observations are obtained for this case, or None if impossible.

    Keys: vino parameter, period (h or None), list of valid times, and how the
    per-station value is aggregated.
    """
    w = cfg.window
    if cfg.variable == "tp":
        if w.hours % 24 == 0 and w.end.hour % 6 == 0:
            times = [w.end - dt.timedelta(days=d) for d in range(w.hours // 24)][::-1]
            return {"param": "tp", "period": 24, "times": times, "how": "sum"}
        if w.hours in (6, 12) and w.end.hour % 6 == 0:
            return {"param": "tp", "period": w.hours, "times": [w.end], "how": "sum"}
        return None
    step = cfg.observations.wind_interval_h
    if w.statistic == "instant":
        return (
            {"param": "10ff", "period": None, "times": [w.end], "how": "instant"}
            if w.end.hour % step == 0
            else None
        )
    t, times = w.start, []
    while t <= w.end:
        if t.hour % step == 0:
            times.append(t)
        t += dt.timedelta(hours=1)
    return {"param": "10ff", "period": None, "times": times, "how": w.statistic}


def _obs_dir(cfg: CaseConfig, p: dict) -> Path:
    tag = "_".join(cfg.observations.sources)
    name = f"{p['param']}{p['period'] or ''}_{tag}"
    return cfg.cache_dir / "observations" / name


def _file_for(directory: Path, p: dict, t: dt.datetime) -> Path:
    return directory / f"{p['param']}{p['period'] or ''}_obs_{t:%Y%m%d%H}.geo"


def retrieve(cfg: CaseConfig, force: bool = False) -> Path | None:
    """Run vino_getgeo for any missing valid times; return the observation folder."""
    p = plan(cfg)
    if p is None:
        return None
    directory = _obs_dir(cfg, p)
    missing = [
        t for t in p["times"] if force or not _file_for(directory, p, t).exists()
    ]
    if not missing:
        return directory
    directory.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    scratch = env.get("SCRATCH")
    if scratch:
        tmp = Path(scratch) / "metview_tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        env["METVIEW_TMPDIR"] = env["TMPDIR"] = str(tmp)
    metview = shutil.which("metview")
    if metview:
        env["PATH"] = os.path.dirname(metview) + os.pathsep + env.get("PATH", "")
    hours = sorted({f"{t:%H}" for t in missing})
    cmd = [cfg.observations.vino_path, "--sources", *cfg.observations.sources]
    cmd += ["--parameter", p["param"]]
    if p["period"]:
        cmd += ["--period", str(p["period"])]
    cmd += [
        "--dates",
        f"{min(missing):%Y%m%d}/to/{max(missing):%Y%m%d}",
        "--times",
        *hours,
        "--columns",
        "value_0",
        "elevation",
        "--outdir",
        str(directory),
        "--flattree",
    ]
    print(f"Retrieving observations: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"vino_getgeo failed ({proc.returncode}): {proc.stderr or proc.stdout}"
        )
    return directory


def parse_geo(path: Path) -> pd.DataFrame:
    """Parse one VINO ``.geo`` export into stnid/lat/lon/elevation/valid_time/obs."""
    rows, in_data = [], False
    with path.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if line.startswith("#DATA"):
                in_data = True
                continue
            if not in_data or not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 8:
                continue
            try:
                value = float(parts[7])
                if value >= MISSING:
                    continue
                rows.append(
                    {
                        "stnid": parts[0],
                        "lat": float(parts[1]),
                        "lon": float(parts[2]),
                        "elevation": float(parts[6]),
                        "valid_time": dt.datetime.strptime(
                            parts[4] + parts[5].zfill(4), "%Y%m%d%H%M"
                        ),
                        "obs": value,
                    }
                )
            except ValueError:
                continue
    return pd.DataFrame(rows)


def load(cfg: CaseConfig, directory: Path) -> pd.DataFrame:
    """Return one aggregated value per station location inside the domains."""
    p = plan(cfg)
    files = [_file_for(directory, p, t) for t in p["times"]]
    frames = [parse_geo(f) for f in files if f.exists()]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(
            columns=["stnid", "lat", "lon", "elevation", "obs", "n_reports"]
        )
    obs = pd.concat(frames, ignore_index=True)
    obs = obs[obs["valid_time"].isin(p["times"])]
    boxes = list(cfg.domains.values())
    inside = False
    for w, e, s, n in boxes:
        inside = inside | (obs["lat"].between(s, n) & obs["lon"].between(w, e))
    obs = obs[inside]
    # SYNOP and HDOBS may report the same gauge under different identifiers.
    obs = obs.assign(
        loc=obs["lat"].round(3).astype(str) + "_" + obs["lon"].round(3).astype(str)
    )
    obs = obs.drop_duplicates(["loc", "valid_time"])
    agg = {"sum": "sum", "max": "max", "mean": "mean", "instant": "last"}[p["how"]]
    out = obs.groupby("loc").agg(
        stnid=("stnid", "first"),
        lat=("lat", "first"),
        lon=("lon", "first"),
        elevation=("elevation", "first"),
        n_reports=("obs", "size"),
        obs=("obs", agg),
    )
    needed = max(1, int(round(cfg.observations.min_coverage * len(p["times"]))))
    return out[out["n_reports"] >= needed].reset_index(drop=True)
