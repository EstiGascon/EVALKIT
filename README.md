# Model Error Detective

Model Error Detective is an open-source toolkit designed for analyzing and visualizing meteorological model outputs. It provides interactive time-series and ensemble-forecast exploration, a configurable model-vs-observation case-study tool, and verification scripts to help researchers and forecasters identify and diagnose model errors.

## Key Features

### ⏱️ Clickable Timeseries  
Generate interactive time-series charts by clicking grid points on maps. Visualize temporal evolution of variables at selected locations; it allows comparison between models.

### 📊 Probabilistic Forecasts Analysis Tool

Ensemble forecast visualization and uncertainty quantification tools:
- **Meteograms**: Comprehensive temporal evolution plots showing ensemble statistics and individual member traces
- **Plumes**: Ensemble spread visualization displaying forecast uncertainty through time with percentile ranges
- **CDFs (Cumulative Distribution Functions)**: Probability distribution analysis for specific forecast times and variables
- **Stamps**: Small-multiple displays showing spatial patterns across individual ensemble members

### 🧪 Case Study Tool
One YAML file per case gives you model-vs-observation panels for any area, date and set of models, including research experiments.
- **Variables:** precipitation accumulations, or 10 m wind speed (at a time, or its maximum or mean over a window).
- **Models:** IFS, AIFS-single, DestinE and the Pilot DT as presets, or any MARS experiment by `class`/`expver`.
- **Outputs:** panel figures, observation maps, model orography, and scores (bias, RMSE, correlation, POD/FAR/ETS).

See [case_study_tool/README.md](case_study_tool/README.md) and the [User Guide](USER_GUIDE.md#-case-study-tool).

### 🔬 Verification Pipelines & Case Studies
Command-line scripts in [`analysis/`](analysis/) that verify forecasts against SYNOP/HDOBS observations and produce case-study figures. They compare IFS-control, AIFS-single, DestinE (`iekm`) and the Pilot DT (`j5j2`) at native resolution. Current scripts:
- **Wind verification:** HRES 10 m wind speed (RTE France case)
- **Precipitation misplacement:** Baltic 24 h precipitation study
- **Case studies** in [`analysis/case_studies/`](analysis/case_studies/): Alps, Catalonia, Crete, Iberia and Tuscany precipitation, the California atmospheric river (precipitation and wind), plus Crete orography with wind

See [analysis/README.md](analysis/README.md).

## 🚀 Getting Started
See [GETTING_STARTED.md](GETTING_STARTED.md) for environment setup instructions.

## 📖 User Guide
For a complete walkthrough of the two notebook tools, the Case Study Tool and the analysis scripts (with screenshots and configuration examples), see [USER_GUIDE.md](USER_GUIDE.md).

## 🛠️ Contributing  
We welcome contributions! Please review our guidelines in [CONTRIBUTING.md](CONTRIBUTING.md) for details on:  
- Setting up the development environment  
- Submitting pull requests  
- Reporting issues  
- Code style standards  
