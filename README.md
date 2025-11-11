# Model Error Detective

Model Error Detective is an open-source toolkit designed for analyzing and visualizing meteorological model outputs. It provides dynamic map exploration, calculated variable derivation, and interactive time-series capabilities to help researchers and forecasters identify and diagnose model errors.

## Key Features  

### 📊 Calculated Variables  

The toolkit computes derived meteorological variables using raw model outputs:  

| Variable Type | Inputs | Output | Calculation Method |  
|---------------|--------|--------|---------------------|  
| **Wind Speed** | 10m U (`u10`) and V (`v10`) wind components | Instantaneous wind speed magnitude | $$ \sqrt{u10^2 + v10^2} $$ at each timestep |  
| **Accumulated Precipitation** | Total Precipitation (`tp`) | Total accumulation between first/last forecast step | Sum of `tp` across all timesteps |  
| **Max/Min Values** | Any time-varying variable (e.g., temperature, wind gust) | Grid-point extremes across timesteps | - **Maximum**: Highest value per grid point<br>- **Minimum**: Lowest value per grid point |  

### 🗺️ Map Visualization  
- **Dynamic Maps**: Interactive maps with hover, zoom, and pan functionality to explore spatial data. Values display on cursor interaction.  
- **Static Maps**: Pre-rendered spatial plots generated via `earthkit` for quick analysis.  
- **Multi-Step Maps**: Comparative visualization of model outputs across multiple forecast steps.  

### ⏱️ Clickable Timeseries  
Generate interactive time-series charts by clicking grid points on maps. Visualize temporal evolution of variables at selected locations.  

## 🛠️ Contributing  
We welcome contributions! Please review our guidelines in [CONTRIBUTING.md](CONTRIBUTING.md) for details on:  
- Setting up the development environment  
- Submitting pull requests  
- Reporting issues  
- Code style standards  
