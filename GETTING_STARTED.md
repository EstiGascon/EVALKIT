# Getting Started

This guide will help you set up your environment and replicate the project setup from scratch.

# Prerequisites

Before starting development, make sure the following programs are installed:

- **Visual Studio Code (VSCode)**
- **Windows Subsystem for Linux (WSL)**

## 1. Installing WSL

To install WSL, open PowerShell as Administrator and follow the official Microsoft procedure:

```sh
wsl --install -d ubuntu
```
Set WSL 2 as the default version:
```sh
wsl --set-default-version 2
```
During installation, you'll be prompted to create a username and password.  
**Be sure to remember these credentials,** as you'll need them each time you start a WSL2 Ubuntu terminal.

Restart your PC to ensure all changes take effect.

---
<!-- TODO: verify - section 2 appears to be missing from this guide (numbering jumps from 1 to 3); confirm no setup step (e.g. Python/VS Code extensions) was lost. -->
## 2. Installing Poetry

Run the following in your WSL terminal:
```sh
curl -sSL https://install.python-poetry.org | python3 -
```
Add Poetry to your PATH:
```sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```
Verify installation:
```sh
poetry --version
```

## 3. Initialize Your Project with Poetry
Initialize Poetry (creates `pyproject.toml`):
```sh
poetry init
```
Follow the prompts to configure your project.

## 4. Poetry Environment Setup
Configure Poetry to place virtual environments inside your project:
```sh

poetry config virtualenvs.in-project true
```
Install dependencies (if you have a `pyproject.toml`):
```sh
poetry install
```
Synchronize your environment (if you have a `poetry.lock`):
```sh
poetry sync
```
Activate the virtual environment:
```sh
eval $(poetry env activate)
```

## 5. Running the Notebooks

With the environment activated, launch Jupyter and open one of the tool notebooks:
```sh
jupyter lab
```
- `clickable_timeseries/notebooks/timeseries_analysis.ipynb`
- `dynamic_maps/notebooks/dynamic_map.ipynb`
- `probabilistic_forecast_tool/notebooks/probabilistic_forecast_tool.ipynb`

## 6. Running the Analysis Scripts (ECMWF systems)

The scripts in `analysis/` need MARS access and, for observations, the STVL `vino_getgeo` executable. Run them with an ECMWF Python that provides `earthkit-data`, `cartopy` and `shapely`:
```sh
PY=/usr/local/apps/python3/3.13.13-01/bin/python3
$PY analysis/case_studies/crete_precip.py     # case studies run from any directory
cd analysis && $PY run_analysis.py --dry-run  # pipelines run from inside analysis/
```
See [analysis/README.md](analysis/README.md) for all scripts and options.
- `probabilistic_forecast_tool/notebooks/probabilistic_forecast_tool.ipynb`