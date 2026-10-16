# AGENTS.md

Tools that build and publish Sentry's internal PyPI index at `https://pypi.devinfra.sentry.io/simple`.
`packages.ini` lists every package version the index serves.

## commands

- Set up: `uv sync`, then `direnv allow` to install the pre-commit hooks.
- Test: `uv run coverage run -m pytest tests && uv run coverage report`
- Lint and format: `pre-commit run --files <changed files>`
- Add a package: `python3 -m add_pkg PKGNAME`
- Add the newest PyPI release of every package: `python3 -m upgrade_all`
- Format `packages.ini`: `python3 -m format_ini packages.ini`

## invariants

- Put no `#` comments in `packages.ini`. `format_ini.py` drops them.
- Every dependency of a package must also be in `packages.ini`, or validation fails.
- Never overwrite a published wheel. Deletion is a manual process for security cases.
- `PYTHONS` in `build.py` and `validate.py` and `VERSIONS` in `docker/install-pythons` list the same Python versions.

## docs

| Topic | Doc |
| --- | --- |
| Use the index and add a package | [README.md](README.md) |
| `packages.ini` options | [docs/packages-ini.md](docs/packages-ini.md) |
| How CI builds, validates, and deploys | [docs/build-pipeline.md](docs/build-pipeline.md) |
| Delete a published package | [docs/deleting-packages.md](docs/deleting-packages.md) |
| Add a new Python version | [upgrade-python skill](.claude/skills/upgrade-python/SKILL.md) |
| Python 3.14 upgrade failures (dated record) | [PYTHON-3.14-UPGRADE.md](PYTHON-3.14-UPGRADE.md) |
