"""Retrieval and loading of STVL 10 m wind-speed observations.

Observations are pulled via the existing ``ObservationsRetriever`` helper
(which wraps ``vino_getgeo``) and parsed from the ``.geo`` text export into a
tidy :class:`pandas.DataFrame`.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

from config import StudyConfig


def _import_retriever(cfg: StudyConfig):
    """Import ObservationsRetriever from the clickable_timeseries helpers."""
    pkg = str(cfg.helpers_pkg_dir)
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    from helpers.observations_retriever import ObservationsRetriever  # noqa: PLC0415

    return ObservationsRetriever(vino_path=cfg.vino_path)


def retrieve_observations(cfg: StudyConfig, force: bool = False) -> Path:
    """Retrieve STVL 10ff observations for the full study window.

    Args:
        cfg: Study configuration.
        force: Re-run the STVL retrieval even if .geo files already exist.

    Returns:
        The directory containing the retrieved ``.geo`` files.
    """
    out_dir = cfg.obs_dir
    existing = sorted(out_dir.glob(f"{cfg.obs_parameter}_obs_*.geo")) if out_dir.exists() else []
    if existing and not force:
        print(f"✓ Observations already present ({len(existing)} files) in {out_dir}")
        return out_dir

    retriever = _import_retriever(cfg)
    # STVL retrieval covers the whole window in a single call. Cover both the
    # initialisation dates and the forecast valid times (a couple of extra days).
    start = cfg.init_start
    end = cfg.init_end + dt.timedelta(days=3)
    print(f"Retrieving STVL {cfg.obs_parameter} observations {start} → {end} ...")
    retriever.retrieve(
        sources=cfg.obs_sources,
        parameter=cfg.obs_parameter,
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        times=cfg.obs_times,
        output_dir=str(out_dir),
    )
    return out_dir


def _parse_geo_file(path: Path, missing: float) -> pd.DataFrame:
    """Parse a single STVL ``.geo`` file into a DataFrame of station values."""
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
            # Columns: stnid latitude longitude level date time elevation value_0
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
                {
                    "stnid": stnid,
                    "lat": lat,
                    "lon": lon,
                    "date": date_s,
                    "time": time_s,
                    "obs": value,
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Build a UTC valid timestamp from date (YYYYMMDD) + time (HHMM).
    df["valid_time"] = pd.to_datetime(
        df["date"] + df["time"].str.zfill(4), format="%Y%m%d%H%M", utc=False
    )
    return df[["stnid", "lat", "lon", "valid_time", "obs"]]


def load_observations(cfg: StudyConfig) -> pd.DataFrame:
    """Load and concatenate all observation ``.geo`` files inside the study box.

    Returns:
        DataFrame with columns ``stnid, lat, lon, valid_time, obs`` restricted
        to the configured bounding box.
    """
    files = sorted(cfg.obs_dir.glob(f"{cfg.obs_parameter}_obs_*.geo"))
    if not files:
        raise FileNotFoundError(
            f"No observation files in {cfg.obs_dir}. Run retrieve_observations() first."
        )

    frames = [_parse_geo_file(f, cfg.obs_missing_value) for f in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        raise ValueError("All observation files were empty after parsing.")

    obs = pd.concat(frames, ignore_index=True)
    # Restrict to the study bounding box.
    mask = (
        (obs["lat"] >= cfg.south)
        & (obs["lat"] <= cfg.north)
        & (obs["lon"] >= cfg.west)
        & (obs["lon"] <= cfg.east)
    )
    obs = obs.loc[mask].copy()
    obs.sort_values(["stnid", "valid_time"], inplace=True)
    obs.reset_index(drop=True, inplace=True)
    n_stations = obs["stnid"].nunique()
    print(
        f"✓ Loaded {len(obs)} observations from {n_stations} stations "
        f"in box, {obs['valid_time'].min()} → {obs['valid_time'].max()}"
    )
    return obs
