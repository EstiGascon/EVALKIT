# Contributing Guide

Follow these steps to get your development environment ready.


## 1. Clone the Repository

<!-- TODO: verify - confirm this repository URL is still current -->
```sh
git clone https://github.com/nadiasadiki/Code4Earth-2025-Challenge30_Model_Error_Detective.git

cd Code4Earth-2025-Challenge30_Model_Error_Detective
```

## 2. Set Up Poetry

Ensure Poetry is installed (see `GETTING_STARTED.md` if not).

Configure Poetry to use in-project virtual environments:
```sh
poetry config virtualenvs.in-project true
```

Install all dependencies (including dev and Jupyter):
```sh
poetry install --with dev,jupyter
```

## 3. Activate the Virtual Environment
```sh
eval $(poetry env activate)
```
## 4. Lint

CI (`.github/workflows/main.yml`) runs on every push and pull request. It uses the ruff version pinned in `poetry.lock`, so run the checks through Poetry to get the same results:
```sh
poetry run ruff format --check .   # formatting (run `poetry run ruff format .` to fix)
poetry run ruff check .            # lint rules from pyproject.toml
poetry check --lock --strict       # pyproject.toml and poetry.lock are in sync
```

Notes:
- Notebooks are linted too. Rule E402 (imports not at the top) is allowed in `*.ipynb`, because notebooks set `sys.path` before importing `helpers`.
- Public functions need a docstring, and the summary line must be in the imperative mood (e.g. "Return ...", not "Returns ...").

## 5. Workflow
<!-- TODO: verify - numbering previously jumped from 4 to 6; confirm no step (e.g. running/testing notebooks) was lost here. -->

- Create a new branch.
- Make your changes.
- Ensure code passes linting.
- Commit and push your branch.
- Open a Pull Request.

## 6. Additional Notes

- Update dependencies using `poetry add` or `poetry add --group dev package-name`.
- If you change dependencies, run `poetry lock` and commit the updated `poetry.lock` file.
- Put new one-off analysis or case-study scripts in `analysis/case_studies/`, not directly in `analysis/`. Reusable pipeline modules stay in `analysis/`. Generated data, figures and tables go to `analysis/data/`, `analysis/figures/` and `analysis/results/`.
