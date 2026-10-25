# Case Study Tool

Compare forecast models with SYNOP/HDOBS observations for a single weather
event. You describe the case in one YAML file: the variable, time window, lead
times, models, area and region. The tool then:

1. retrieves the forecasts from MARS (in parallel, cached),
2. retrieves the station observations with `vino_getgeo` (cached),
3. aggregates both to the same quantity (e.g. 24 h total, 48 h maximum wind),
4. writes panel maps, an observation map, a model-orography map, score tables
   and a score figure.

It works for any area, date and model, including research experiments that
only exist in MARS under a `class`/`expver`.

> ⚠️ HDOBS observations are for ECMWF internal use only. Do not distribute
> figures or tables that include them outside ECMWF.

## Requirements

- An ECMWF Python with `earthkit-data`, `cartopy`, `shapely`, `pyyaml`,
  `pandas`, `scipy` and `matplotlib`, e.g.
  `/usr/local/apps/python3/3.13.13-01/bin/python3`.
- MARS access.
- For observations: `vino_getgeo` (default `/home/moz/bin/vino_getgeo`) and
  `metview` on the `PATH`.

## Quick start

```bash
PY=/usr/local/apps/python3/3.13.13-01/bin/python3
$PY case_study_tool/run_case.py template -o my_case.yaml   # commented template
$PY case_study_tool/run_case.py plan my_case.yaml          # dry run, no retrieval
$PY case_study_tool/run_case.py run  my_case.yaml          # retrieve, verify, plot
$PY case_study_tool/run_case.py models                     # list model presets
```

`plan` prints the model runs and steps, the observation product, the region,
and a warning for every model/lead that cannot be retrieved (no such cycle,
step not archived, lead shorter than the window). Always run it first.

`run` options:

| Option | Effect |
|---|---|
| `--workers N` | Parallel MARS retrievals (default 6) |
| `--force` | Ignore the cache and retrieve again |
| `--no-obs` | Skip observations (maps and region statistics only) |

The script can be run from any directory. `python -m casetool` from inside
`case_study_tool/` works too.

## Example cases

| Config | Case |
|---|---|
| [`iberia_20260204_tp.yaml`](configs/iberia_20260204_tp.yaml) | Andalusia extreme rain, 24 h to 5 Feb 2026 00 UTC, with an Andalusia zoom |
| [`toscana_20241018_tp.yaml`](configs/toscana_20241018_tp.yaml) | Tuscany heavy rain, 18 Oct 2024, region = Toscana (admin-1) |
| [`valencia_dana_20241029_tp.yaml`](configs/valencia_dana_20241029_tp.yaml) | Valencia DANA, 29 Oct 2024, three leads, native grid boxes, Valencia zoom |
| [`catalonia_20261004_tp.yaml`](configs/catalonia_20261004_tp.yaml) | Catalonia MCS, 24 h to 4 Oct 2026 12 UTC, with a research experiment (`rd/j5j2`) given explicitly |
| [`california_ar_20241124_tp.yaml`](configs/california_ar_20241124_tp.yaml) | California atmospheric river, 4-day total (96 h) |
| [`california_ar_20241121_ws10max.yaml`](configs/california_ar_20241121_ws10max.yaml) | Pacific NW bomb cyclone, 48 h maximum 10 m wind |

## Configuration reference

Required keys: `name`, `window`, `leads`, `models`, `domain`. Unknown keys are
rejected, so typos are caught before anything is retrieved.

```yaml
name: my_case                 # output folder: case_study_tool/output/<name>/
title: "My case study"        # figure titles (optional)

variable: tp                  # tp (precipitation, mm) | ws10 (10 m wind speed, m/s)
window:
  end: "2026-02-05 00"        # end of the window, UTC ("YYYY-MM-DD HH")
  hours: 24                   # window length
  statistic: sum              # tp: sum | ws10: instant, max or mean

leads: [24, 48]               # hours from model run to window END

models: [ifs, aifs, destine]  # presets and/or mappings, see below

domain:
  extent: [-10.0, 4.5, 35.5, 44.5]      # main map [W, E, S, N]
  zooms:                                 # optional: extra figures per sub-area
    andalusia: [-7.6, -1.5, 35.8, 38.7]

region:                       # optional, see "Region"
  name: Iberia
  countries: [Spain, Portugal]

observations:                 # all optional
  enabled: true
  sources: [synop, hdobs]
  min_coverage: 1.0           # share of reports a station needs (multi-time windows)
  wind_interval_h: 3          # spacing of station wind reports used for max/mean
  vino_path: /home/moz/bin/vino_getgeo

thresholds: [1, 10, 25, 50, 100]   # categorical scores; default depends on variable

plot:                         # all optional
  style: contour              # contour (filled contours) | gridbox (native grid cells)
  levels: null                # null = automatic colour scale, or a list of levels
  orography: true             # orography figure (also enables the land-only region max)
  dpi: 120

model_interval_h: 3           # spacing of model outputs used for ws10 max/mean
output_dir: case_study_tool/output   # relative paths resolve from the repo root
cache_dir: case_study_tool/cache
```

### Window and lead times

A lead time always refers to the **end** of the window. For each lead the
model run is `window.end − lead`, and the steps are derived automatically:

- **`tp`:** the accumulation is `tp(lead) − tp(lead − hours)`. With
  `hours: 24` and `leads: [24, 48]` the T+48 h column uses steps 24–48 of the
  run 48 h before the window end.
- **`ws10 instant`:** the single step `lead` (`hours` is ignored).
- **`ws10 max`/`mean`:** the maximum or mean wind speed over all archived
  steps in `[lead − hours, lead]`, every `model_interval_h` hours. AIFS only
  has 6-hourly output, so it uses 6-hourly steps.

The lead must be at least the window length, and `end − lead` must be a cycle
the model runs. `plan` warns about any combination that breaks this. Those
panels are left out, and the rest of the case still runs.

### Models

Presets (`run_case.py models`):

| Preset | Label | MARS | Cycles | Output steps |
|---|---|---|---|---|
| `ifs` | IFS operational | `od/0001` | 00, 12 | hourly to 90 h, 3-hourly to 144 h, 6-hourly to 360 h |
| `aifs` | AIFS-single | `ai/0001` | 00, 06, 12, 18 | 6-hourly to 360 h |
| `destine` | DestinE | `rd/iekm`, falls back to `rd/i4ql` | 00 | hourly to 120 h |
| `pilot_dt` | Pilot DT | `rd/j5j2` | 00 | hourly to 120 h |

Other experiments:

```yaml
models:
  - ifs
  - {preset: destine, expver: abcd}        # preset settings, other expver ("DestinE abcd")
  - label: "My RD experiment"              # any MARS experiment
    class: rd
    expver: abcd
    stream: oper                           # default oper
    type: fc                               # default fc
    cycles: [0]                            # default [0, 12]
    step_rules: [[120, 1], [240, 3]]       # steps <= 120 hourly, then 3-hourly to 240
    fallback_expvers: [efgh]               # tried in order if abcd has no data
```

Every model needs a unique label. Two entries with the same label are
rejected. `class: rd` uses the GRIB-1 style parameters (`228.128`,
`165.128/166.128`). Other classes use `228` and `165/166`.

### Region

`region` limits the statistics (the region maximum and mean, and the stations
used for scores) to an outline, which is also drawn on every map. Parts are
combined:

| Key | Example | Source |
|---|---|---|
| `countries` | `[Spain, Portugal]` | Natural Earth admin-0 name |
| `admin1` | `{country: Italy, regions: [Toscana]}` | Natural Earth admin-1 `region` or `name`, e.g. a Spanish autonomous community (`Valenciana`) or a province (`Valencia`) |
| `box` | `[W, E, S, N]` | rectangle |
| `clip_to_domain` | `true` (default) | drops parts outside `domain.extent`, e.g. distant islands |
| `name` | `Comunitat Valenciana` | label in titles and CSV |

A name that matches nothing stops the run before any retrieval, and `plan`
shows it as a warning. Without `region`, the statistics use the whole main
domain, sea included. With `region` and `plot.orography: true`, the region
maximum and mean only use model land points (`lsm ≥ 0.5`).

## How observations are matched

| Case | Observations |
|---|---|
| `tp`, `hours` a multiple of 24, end hour 00/06/12/18 | daily `tp24` reports ending at the window's end hour, summed per station |
| `tp`, `hours` 6 or 12, end hour 00/06/12/18 | the `tp` report for that period |
| `ws10 instant` (end hour a multiple of 3) | `10ff` at the valid time |
| `ws10 max`/`mean` | maximum or mean of the 3-hourly `10ff` reports in the window (ends included) |

Other windows (e.g. 18 h) have no matching product. The tool then runs
without observations and says so.

- **Duplicates:** SYNOP and HDOBS often report the same gauge under different
  identifiers. Reports at the same location (to 0.001°) and time are kept
  once.
- **Coverage:** a station needs at least `min_coverage` × the number of report
  times. With 1.0 (the default) a 4-day total needs all 4 daily reports, so no
  partial sums are shown.
- **Matching:** each station is compared with the nearest model grid point.
  There is no interpolation.
- **Reporting hours:** networks report `tp24` at different hours (many
  Spanish SYNOPs only at 06 UTC). A window ending at another hour misses
  those stations, so check `observations.png` and, if needed, move
  `window.end`.

## Outputs

Everything goes to `case_study_tool/output/<name>/`:

| File | Content |
|---|---|
| `panel.png` | Rows are lead times. The columns are the observations, then one per model. Each model title shows the run, the steps, the maximum inside the region (marked × on the map) and the station bias, RMSE and correlation. |
| `observations.png` | The aggregated station values on the same colour scale |
| `orography.png` | Each model's orography (`z / g`), with sea masked by its own land–sea mask |
| `panel_<zoom>.png`, … | The same figures for each `domain.zooms` entry. Model titles still give the region maximum and the scores over all region stations, while the observation column counts the stations in the zoom |
| `scores.png` | Bias, RMSE and correlation per model and lead, plus ETS against threshold |
| `scores.csv` | One row per model and lead: run, expver, grid, region max (with location) and mean, and the station scores (n, bias, MAE, RMSE, correlation, observed maximum and forecast at that station) |
| `categorical_scores.csv` | One row per model, lead and threshold: hits, misses, false alarms, correct negatives, POD, FAR, frequency bias (FBI) and ETS |
| `observations.csv` | One row per station: the aggregated value, its elevation and the number of reports used |

The colour scale is chosen from the largest value in any field or station,
unless `plot.levels` is set.

## Caching

- **Forecasts:** GRIB files go to `cache/mars/`. Each file is named after its
  class, expver, run and a hash of the request, so changing the area, steps or
  parameters gives a new file. When a preset falls back to another expver
  (DestinE `iekm` → `i4ql`), the cached fallback is reused on later runs.
- **Observations:** `.geo` files go to `cache/observations/`.

- **MARS log:** the MARS client output of the retrieval workers goes to
  `cache/mars/mars.log`, so the console only shows one ✓/✗ line per
  retrieval. Look there when a retrieval fails.

Re-running a case therefore only redraws the figures. Use `--force` to
retrieve again. `cache/` and `output/` are ignored by git.

## Code layout

| Module | Role |
|---|---|
| `casetool/cli.py` | Command-line interface and the YAML template |
| `casetool/config.py` | `CaseConfig`: parsing, defaults, validation, run/step derivation, `check()` |
| `casetool/models.py` | `ModelSpec`, presets, output-step rules, MARS parameters |
| `casetool/mars.py` | MARS requests, cache names, parallel retrieval with expver fallback |
| `casetool/fields.py` | Precipitation, wind speed and orography from GRIB (earthkit-data < 1.0 and ≥ 1.0) |
| `casetool/observations.py` | `vino_getgeo` call, `.geo` parsing, per-station aggregation |
| `casetool/regions.py` | Natural Earth region outlines |
| `casetool/stats.py` | Region summary, nearest-point station scores, contingency scores |
| `casetool/plotting.py` | Colour scales and figures |
| `casetool/pipeline.py` | `describe()` (the plan) and `run()` (the whole case) |

To add a **model preset**, add a `ModelSpec` to `PRESETS` in `models.py`. To
add a **variable**, extend `VARIABLES` in `config.py`, the parameter tables in
`models.py`, the derivation in `fields.py`/`pipeline._derive`, the
observation plan in `observations.plan`, and the colour scale in
`plotting.choose_scale`.

You can also use the tool from Python:

```python
import sys; sys.path.insert(0, "case_study_tool")
from casetool import load_config, run
outputs = run(load_config("case_study_tool/configs/iberia_20260204_tp.yaml"))
```
