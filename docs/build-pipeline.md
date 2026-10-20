# How the build pipeline works

The `build` workflow (`.github/workflows/build.yml`) runs on every pull request and on every push to `main`.

## build

`build.py` reads `packages.ini` and the index's `packages.json`.
It skips a package version when the index already has a wheel for it that matches the target Python and platform.
It also skips Python versions that the section's `python_versions` excludes.
For each remaining package and Python version in `PYTHONS`, `build.py` does this:

1. Reads the release from public PyPI's JSON API, retrying for up to one hour until the release is visible.
   It skips Python versions that the release's `Requires-Python` excludes, because pip would never install the package there.
   It fails right away when `Requires-Python` excludes every build Python.
1. Downloads a wheel from public PyPI.
   It discards the wheel when a compiled file in it has the wrong architecture.
1. If no usable wheel exists, downloads the sdist from public PyPI and builds it with `pip wheel`.
   Build dependencies come from this index, not from public PyPI.
1. Fails when the sdist looks like it has compiled code but the wheel has no `.so` file.
   `likely_binary_ignore` exempts files from this check.
1. Repairs a platform-specific wheel with `auditwheel` on linux or `delocate` on macos.

On linux, `build.py` re-runs itself inside the `ghcr.io/getsentry/pypi-manylinux-amd64-ci` or `ghcr.io/getsentry/pypi-manylinux-arm64-ci` image unless `BUILD_IN_CONTAINER` is set.
The `image` workflow (`.github/workflows/image.yml`) builds that image from `docker/` and pushes it only from `main`.
So a pull request that changes `docker/` builds packages with the old `:latest` image.

The sdist download retries for up to one hour, because a new release can reach PyPI's simple index after its release PR lands.
For a release with no sdist, the wheel download retries instead, but only when public PyPI lists a wheel that matches the Python version.

## validate

`validate.py` installs each built wheel into a fresh virtualenv for every Python version the wheel supports.
It installs only binary wheels from this index plus the just-built wheels.
So every dependency of a new package must also be in `packages.ini`.
Then it imports each top-level module of the wheel.
It skips Python versions that the wheel's `Requires-Python` excludes.

## deploy

On `main` only, the `collect-and-deploy` job runs `make_index.py` and `bin/upload-artifacts`.
`make_index.py` generates the index pages with `dumb-pypi`.
It fails when a wheel filename is already in `packages.json`.
`bin/upload-artifacts` uploads wheels with no-clobber, so a published wheel is never replaced.
It uploads `packages.json` last, with `no-store` caching.
To remove a published wheel, follow [deleting packages](deleting-packages.md).

## hazards

- A failure on Python 3.14 prints `!!! WARNING (py3.14)` and does not fail `build.py` or `validate.py`.
- `build.py --upgrade-python` continues past failures and sets a 600-second timeout per build.
  The [`upgrade-python` skill](../.claude/skills/upgrade-python/SKILL.md) uses it.
