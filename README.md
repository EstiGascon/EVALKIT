# Model Error Detective

Model Error Detective is an open-source toolkit designed for analyzing and visualizing meteorological model outputs. It provides dynamic map exploration, calculated variable derivation, and interactive time-series capabilities to help researchers and forecasters identify and diagnose model errors.

## Key Features

### 🗺️ Dynamic Map Visualization  
- **Dynamic Maps**: Interactive maps with hover, zoom, and pan functionality to explore spatial data. Values display on cursor interaction.  
- **Static Maps**: Pre-rendered spatial plots generated via `earthkit` for quick analysis.  
- **Multi-Step Maps**: Comparative visualization of model outputs across multiple forecast steps.  

### ⏱️ Clickable Timeseries  
Generate interactive time-series charts by clicking grid points on maps. Visualize temporal evolution of variables at selected locations; it allows comparison between models.

### 📊 Probabilistic Forecasts Analysis Tool

Ensemble forecast visualization and uncertainty quantification tools:
- **Meteograms**: Comprehensive temporal evolution plots showing ensemble statistics and individual member traces
- **Plumes**: Ensemble spread visualization displaying forecast uncertainty through time with percentile ranges
- **CDFs (Cumulative Distribution Functions)**: Probability distribution analysis for specific forecast times and variables
- **Stamps**: Small-multiple displays showing spatial patterns across individual ensemble members

## 🚀 Getting Started
See [GETTING_STARTED.md](GETTING_STARTED.md) for environment setup instructions.

## � User Guide
For a complete walkthrough of all three tools (with screenshots and configuration examples), see [USER_GUIDE.md](USER_GUIDE.md).

## �🛠️ Contributing  
We welcome contributions! Please review our guidelines in [CONTRIBUTING.md](CONTRIBUTING.md) for details on:  
- Setting up the development environment  
- Submitting pull requests  
- Reporting issues  
- Code style standards  
