pypi
====

sentry pypi (public!)

this repository contains the tools to import and/or build packages from public pypi for the
platforms and achitectures required for sentry development.

## why?

this is not merely a mirror; we also build wheels for upstream dependencies that do not ship wheels.

we offer prebuilt wheels so dev machines + ci do not have to build wheels themselves; they just download.

## use the index

The index URL is `https://pypi.devinfra.sentry.io/simple`. With uv, add it to `pyproject.toml`:

```toml
[[tool.uv.index]]
url = "https://pypi.devinfra.sentry.io/simple"
```

With pip, pass `--index-url https://pypi.devinfra.sentry.io/simple`.

The index serves wheels only, and only for the versions listed in `packages.ini`.
If a version is not listed, installing it from this index fails.

Wheels are built for CPython 3.11, 3.12, 3.13, and 3.14 on linux amd64, linux arm64, and macos.

## adding packages

1. Set up the dev environment:

   ```bash
   uv sync
   direnv allow
   ```

   If you do not use direnv, prefix the commands below with `uv run`.

1. Add the package and its dependencies to `packages.ini`:

   ```bash
   python3 -m add_pkg PKGNAME
   ```

   `add_pkg` resolves `PKGNAME` with `pip wheel`, then adds a `[name==version]` section for it and for each dependency.
   A new section copies the options of the newest existing version of the same package.
   `add_pkg` accepts several packages and pinned specifiers such as `PKGNAME==1.2.3`.

1. Open a pull request. CI builds and validates the new wheels on every platform.
   After the pull request merges to `main`, CI uploads the wheels to the index.

Anyone in the getsentry Engineering team on GitHub can approve pull requests, but it's preferred to get somebody from your team with context to approve your PR.

don't worry too much about the formatting, an auto-formatter will ensure the format is correct.

most packages won't need special build instructions and the section contents can be left blank:

```ini
[botocore==1.25.12]

[simplejson==3.17.2]
[simplejson==3.17.6]
```

If a package fails to build or validate, set the options in [the `packages.ini` reference](docs/packages-ini.md).

## license

[Apache 2.0](LICENSE)
