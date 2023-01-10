pypi
====

sentry internal pypi

this repository contains the tools to import and/or build packages from public pypi for the
platforms and achitectures required for sentry development.

## setup

```
python3 -m venv .venv
source .venv
pip install packaging wheel
```

## adding packages

packages are configured in the `packages.ini` file.

the easiest way to add a package and its dependencies is to use:

```bash
python3 -m add_pkg PKGNAME
```

each section is an individual package and has some additional instructions which helps for
building.

don't worry too much about the formatting, an auto-formatter will ensure the format is correct.

most packages won't need special build instructions and the section contents can be left blank:

```ini
[botocore==1.25.12]

[simplejson==3.17.2]
[simplejson==3.17.6]
```

**Anyone in the [Engineering team](https://github.com/orgs/getsentry/teams/engineering) can approve Pull Requests**.

### apt_requires / brew_requires

some packages require special system-level build dependencies, these can be configured using
`apt_requires` (linux) and `brew_requires` (macos)

```ini
[xmlsec==1.3.12]
apt_requires =
    libxmlsec1-dev
    pkg-config
brew_requires =
    libxmlsec1
    pkg-config
```

some packages on pypi have incorrectly built wheels -- these can be ignored (forcing them to
be built rather than imported):

### custom_prebuild

sometimes the dependencies aren't packaged for apt / brew and you need a custom
script to set them up.  this script will be passed a single "prefix" directory
(which contains the standard `bin` / `lib` / `include` / etc. structure).

the script should set up whatever tools are necessary inside only that directory

```ini
[google-crc32c==1.3.0]
custom_prebuild = prebuild/crc32c 1.1.2
```

### python_versions

some packages are only intended for particular python versions (or don't
otherwise build cleanly).  the builds can be filtered using `python_versions`
(though usually you should try and upgrade the relevant package).

```ini
[backports-zoneinfo==0.2.1]
python_versions = <3.9
```

## validation

after building the packages will be checked that they can install and import

### validate_extras

sometimes you may need to hint the validation tooling of additional requirements

an example is `black` which has a `blackd` top-level but requires an optional
dependency to use (the `black[d]` extra).  you can hint at this via
`validate_extras`

```ini
[black==22.3.0]
validate_extras = d
```

### validate_incorrect_missing_deps

sometimes packages incorrectly specify their dependencies.  you can use this
option to add import-time dependencies (though you should try and send a PR to
fix those packages!)

one example is `dictpath` which depends on `six` but doesn't list it:

```ini
[dictpath==0.1.3]
validate_incorrect_missing_deps = six
```

### validate_skip_modules

this should usually not be used but sometimes you need to skip importing some
top-level modules due to side-effects or weird runtime requirements

```ini
[pyuwsgi==2.0.20]
validate_skip_imports = uwsgidecorators
```
