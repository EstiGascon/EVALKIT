# Analysis — verification pipelines and case studies

Scripts for verifying ECMWF forecasts against observations and for producing
case-study figures. Unlike the notebook tools, they run from the command line
and write static figures and tables.

| Folder / entry point | What it does |
|---|---|
| [`run_analysis.py`](run_analysis.py) | HRES 10 m wind-speed verification, RTE France case |
| [`europe_map.py`](europe_map.py) | Europe-wide 10 m wind-speed bias maps, same period |
| [`drilldown.py`](drilldown.py) | Drill-down into the 15 Aug 2026 wind event |
| [`precip_run.py`](precip_run.py) | Baltic 24 h precipitation misplacement study |
| [`case_studies/`](case_studies/) | One-off case-study scripts (Alps, Catalonia, Crete) |

## Requirements

- An ECMWF Python with `earthkit-data`, `cartopy`, `shapely`, `pandas` and
  `matplotlib`, for example `/usr/local/apps/python3/3.13.13-01/bin/python3`
  or the JupyterHub environment.
- MARS access for forecasts.
- `vino_getgeo` (STVL) for observations. The default path is
  `/home/moz/bin/vino_getgeo`.

> ⚠️ **HDOBS** (high-density observations) are for ECMWF internal use only.
> Do not distribute HDOBS-derived figures or tables outside ECMWF.

## Folder layout

```
analysis/
  *.py                 reusable pipelines and shared helpers
  case_studies/        one-off case-study scripts (one file per case)
  data/                cached MARS GRIBs and STVL .geo files
    forecasts/           wind study (small box)
    forecasts_europe/    wind study (Europe)
    forecasts_precip/    all precipitation / orography case studies
    observations/        STVL exports, one sub-folder per parameter/case
  figures/             PNG output
  results/             CSV / parquet tables and conclusion.md
```

All MARS and STVL retrievals are cached under `data/`, so re-runs are fast.
Delete a cached file, or pass `--force` where supported, to re-retrieve it.

## Shared helpers

[`precip_forecasts.py`](precip_forecasts.py) contains MARS/earthkit helpers
that all precipitation scripts reuse:

- **earthkit compatibility:** works with both earthkit-data < 1.0 and ≥ 1.0
  (`to_fieldlist`, `to_latlon` vs `data("lat")`, `save` vs `to_target`).
- **Units:** `tp` is converted to mm whatever the archived units are (IFS
  stores metres, AIFS stores kg m⁻²).
- **MARS temporary files:** `TMPDIR` is redirected to
  `/tmp/mars_tmp_$USER` during retrievals.

[`precip_obs.py`](precip_obs.py) provides `_parse_geo_file`, which parses STVL
`.geo` exports and uses the header date/time as the valid time.

### Models

| Label | MARS `class` / `expver` | `tp` param | Cycles | Grid |
|---|---|---|---|---|
| IFS-control | `od` / `0001` | `228` | 00, 12 UTC | O1280 (~9 km) |
| AIFS-single | `ai` / `0001` | `228` | 00, 12 UTC | N320 (~31 km) |
| DestinE (iekm) | `rd` / `iekm` | `228.128` | 00 UTC | O2560 (~4.4 km) |
| Pilot DT (j5j2) | `rd` / `j5j2` | `228.128` | 00 UTC | O2560 (~4.4 km) |
| Hybrid (j1l8) | `rd` / `j1l8` | `228.128` | 00 UTC | — |

---

## 1. HRES 10 m wind-speed verification — RTE France case

Investigates the RTE report of large wind under-forecasts on **3, 4 and
15 August 2026** over **Hauts-de-France + Grand Est**. The aim is to decide
whether the error is **systematic** or **event-specific / outliers**.

- **Forecast:** ECMWF HRES (IFS-single) 10 m wind speed, derived from
  `10u`/`10v` (MARS `class=od, stream=oper, type=fc`).
- **Observations:** STVL SYNOP 10 m wind speed (`10ff`) via `vino_getgeo`.
- **Method:** each station is matched to the nearest forecast grid point.
  Bias and RMSE are scored by lead time, station, day and hour of day. The
  event window is compared with a late-July→15-August baseline.

Run these from inside `analysis/`:

```bash
python run_analysis.py            # full pipeline (MARS + STVL retrieval)
python run_analysis.py --skip-obs # reuse cached observations
python run_analysis.py --skip-fc  # reuse cached forecasts
python run_analysis.py --force-obs / --force-fc  # force re-retrieval
python run_analysis.py --dry-run  # print config only
python europe_map.py [--test]     # Europe-wide bias maps (0.25°, leads ≤ 24 h)
python drilldown.py               # worst stations / misses on 15 Aug 2026
```

Outputs:

- `figures/`: bias/RMSE vs lead time, daily bias, error distribution,
  forecast-vs-obs scatter, event time series, per-station bias maps,
  Europe bias maps (`map_bias_europe_*.png`), and 15 Aug drill-down maps.
- `results/`: score tables (`scores_*.csv`), matched pairs
  (`matched_pairs*.parquet`), `worst_misses_20260815.csv`,
  `worst_stations_20260815.csv`, and `conclusion.md`, which gives an
  automated systematic-vs-event verdict.

All settings (box, dates, cycles, steps, paths) live in `config.py`
(`StudyConfig`).

## 2. Baltic 24 h precipitation misplacement

A heavy-rain event over Estonia, Latvia and Lithuania was forecast too far
north. The reference is the 20 Aug 2026 12 UTC run, 42–66 h accumulation
(24 h ending 23 Aug 06 UTC). The study verifies against STVL SYNOP `tp24`
gauges.

```bash
python precip_run.py                  # IFS-control, AIFS-single, Hybrid (j1l8)
python precip_run.py --variant iekm   # IFS-control, AIFS-single, DestinE (iekm)
python precip_run.py --test           # single-model smoke test
```

Steps:

1. **Event intercomparison:** each model uses its run closest to the reported
   lead.
2. **Fixed-lead intercomparison:** all models are compared at T+54 h.
3. **Predictability sweep:** one map per initialisation, for each model.
4. **Lead-time summary:** northward displacement (rain-mass-weighted
   latitude), bias and RMSE.

Lead times always refer to the **end** of the 24 h accumulation window.
Figures are `precip_*.png`, and tables are `precip_skill_by_lead*.csv`. The
`--variant iekm` run adds the suffix `_iekm`. Configuration is in
`precip_config.py` (`PrecipConfig`, `MODELS`, `MODELS_IEKM`).

---

## 3. Case studies (`case_studies/`)

Each case study is a self-contained script that reuses the shared helpers
above. Scripts add `analysis/` to `sys.path` themselves, so you can run them
from any directory:

```bash
python analysis/case_studies/<script>.py [--force]   # --force re-retrieves from MARS/STVL
```

Fields are plotted at each model's **native resolution** without
interpolation.

| Script | Case | Models | Output |
|---|---|---|---|
| [`alps_precip.py`](case_studies/alps_precip.py) | Alps, 29 Jun – 1 Jul 2024. T+24 h (0–24 h) precipitation for 3 days, with SYNOP + HDOBS gauges | IFS deterministic, `rd/i4ql` | `figures/alps_precip_3day.png` |
| [`catalonia_precip.py`](case_studies/catalonia_precip.py) | Catalonia MCS. 24 h precipitation from 03 Oct 12 UTC to 04 Oct 12 UTC 2026, at T+60 h (02 Oct 00 UTC run, steps 36–60) and T+36 h (03 Oct 00 UTC run, steps 12–36) | IFS-control, AIFS-single, DestinE (iekm), Pilot DT (j5j2) | `figures/catalonia_precip_2026100412.png`, `results/catalonia_precip_2026100412.csv` |
| [`crete_precip.py`](case_studies/crete_precip.py) | Crete extreme precipitation. 5-day accumulation T+0–120 h of the 30 Sep 2026 00 UTC run, plus the observed 5-day totals | as above | `figures/crete_precip_2026093000_0_120.png`, `figures/crete_precip_obs_2026093000_2026100500.png`, matching CSVs in `results/` |
| [`crete_orography.py`](case_studies/crete_orography.py) | Crete: model orography with 10 m wind barbs at T+24 h, 30 Sep 2026 00 UTC run | as above | `figures/crete_orog_wind_2026093000_T24.png` |

### Catalonia (`catalonia_precip.py`)

- The 2 × 4 panel map shows lead times in rows and models in columns. Fields
  are drawn as filled contours, with Barcelona marked by ★.
- The CSV gives, for each model and lead:
  - the domain maximum;
  - the maximum, its location and the mean over the coastal strip
    (40.5–42.5°N, 0.5–3.4°E);
  - the Barcelona grid-point value;
  - the maximum and mean within 25 km of Barcelona.

### Crete (`crete_precip.py`, `crete_orography.py`)

- **Map:** a 2 × 2 panel map zoomed on the island (23.3–26.5°E,
  34.7–35.8°N). Each native grid box is drawn as a filled cell, rebuilt from
  the reduced Gaussian rows, so the fields are not smoothed.
- **Precipitation colour scale:** 30 discrete classes from 0 to 1000 mm. The
  boundaries are 0, 1, 2, 3, 4, 5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80,
  100, 125, 150, 175, 200, 225, 250, 275, 300, 350, 400, 500, 600, 750 and
  1000 mm.
- **Island statistics:** the maximum (marked ×) and the mean use only model
  points inside the Natural Earth 10 m outline of Crete. Small islets such as
  Gavdos are excluded. The CSV also lists nearest-land-point values for
  Chania, Rethymno, Heraklion and Agios Nikolaos. City names are not drawn on
  the map.
- **Observations (`crete_precip.py`):**
  - Daily SYNOP + HDOBS `tp24` totals ending 00 UTC on 1–5 Oct are retrieved
    to `data/observations/tp/tp_24h_crete/` and summed per station.
  - Only stations that report **all 5 days** are kept, so partial sums are
    not shown.
  - The station map uses the same colour scale as the model maps.
- **Orography (`crete_orography.py`):**
  - Orography comes from the surface geopotential (`z`, step 0) divided by g.
  - Sea boxes are those where the model's own land–sea mask (`lsm`) is
    below 0.5.
  - 10 m wind barbs (in knots) are valid at T+24 h. They are sampled at the
    model point nearest to a common 0.15° grid, so barb density is comparable
    across models.

### Adding a new case study

Put new one-off scripts in `case_studies/`, not directly in `analysis/`. Base
them on an existing script:

- Set `REPO_ROOT = Path(__file__).resolve().parents[2]`.
- Add `analysis/` to `sys.path` before importing `precip_forecasts` or
  `precip_obs`.
- Write outputs to `analysis/data`, `analysis/figures` and `analysis/results`.
