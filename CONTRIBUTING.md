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

Run Ruff for linting:
```sh
ruff check
```

Run Ruff for formating:
```sh
ruff format
```

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
