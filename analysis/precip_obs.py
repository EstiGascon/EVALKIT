"""Retrieval and loading of STVL ``tp24`` gauge observations for the case study.

The 24 h accumulation ending 23 Aug 2026 06 UTC (the reported valid window) is
loaded from the STVL ``.geo`` export and restricted to the study box.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

from precip_config import PrecipConfig


def _import_retriever(cfg: PrecipConfig):
    pkg = str(cfg.helpers_pkg_dir)
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    from helpers.observations_retriever import ObservationsRetriever  # noqa: PLC0415

    return ObservationsRetriever(vino_path=cfg.vino_path)


def retrieve_observations(cfg: PrecipConfig, force: bool = False) -> Path:
    """Retrieve STVL tp24 gauges spanning the valid window (a few days)."""
    out_dir = cfg.obs_dir
    existing = sorted(out_dir.glob("tp*_obs_*.geo")) if out_dir.exists() else []
    if existing and not force:
        print(f"\u2713 tp24 observations already present ({len(existing)} files) in {out_dir}")
        return out_dir

    retriever = _import_retriever(cfg)
    start = (cfg.window_end - dt.timedelta(days=1)).date()
    end = (cfg.window_end + dt.timedelta(days=1)).date()
    print(f"Retrieving STVL tp{cfg.obs_period} observations {start} \u2192 {end} ...")
    retriever.retrieve(
        sources=cfg.obs_sources,
        parameter=cfg.obs_parameter,
        period=cfg.obs_period,
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        times=cfg.obs_time,
        output_dir=str(out_dir),
    )
    return out_dir


def _parse_geo_file(path: Path, missing: float) -> pd.DataFrame:
    """Parse one tp24 ``.geo`` file, using header date/time as the valid time."""
    header_date: str | None = None
    header_time: str | None = None
    rows: list[dict] = []
    in_data = False
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.startswith("#DATA"):
                in_data = True
                continue
            if not in_data:
                if line.startswith("date="):
                    header_date = line.split("=", 1)[1].strip()
                elif line.startswith("time="):
                    header_time = line.split("=", 1)[1].strip()
                continue
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 8:
                continue
            try:
                stnid = parts[0]
                lat = float(parts[1])
                lon = float(parts[2])
                date_s = parts[4]
                time_s = parts[5]
                value = float(parts[7])
            except (ValueError, IndexError):
                continue
            if value >= missing:
                continue
            rows.append(
                {"stnid": stnid, "lat": lat, "lon": lon,
                 "date": date_s, "time": time_s, "obs": value}
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["valid_time"] = pd.to_datetime(
        df["date"] + df["time"].str.zfill(4), format="%Y%m%d%H%M"
    )
    return df[["stnid", "lat", "lon", "valid_time", "obs"]]


def load_observations(cfg: PrecipConfig) -> pd.DataFrame:
    """Load tp24 gauges valid at the window end, restricted to the study box."""
    files = sorted(cfg.obs_dir.glob("tp*_obs_*.geo"))
    if not files:
        raise FileNotFoundError(
            f"No tp24 files in {cfg.obs_dir}. Run retrieve_observations() first."
        )
    frames = [_parse_geo_file(f, cfg.obs_missing_value) for f in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        raise ValueError("All tp24 observation files were empty after parsing.")

    obs = pd.concat(frames, ignore_index=True)
    obs = obs[obs["valid_time"] == cfg.window_end]
    mask = (
        (obs["lat"] >= cfg.south) & (obs["lat"] <= cfg.north)
        & (obs["lon"] >= cfg.west) & (obs["lon"] <= cfg.east)
    )
    obs = obs.loc[mask].copy()
    obs.drop_duplicates(subset="stnid", inplace=True)
    obs.sort_values("stnid", inplace=True)
    obs.reset_index(drop=True, inplace=True)
    print(
        f"\u2713 Loaded {len(obs)} tp{cfg.obs_period} gauges in box valid "
        f"{cfg.window_end:%Y-%m-%d %HZ}  (max {obs['obs'].max():.1f} mm)"
    )
    return obs
