pypi
====

sentry internal pypi

this repository contains the tools to import and/or build packages from public pypi for the
platforms and achitectures required for sentry development.

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

### ignore_wheels

```ini
[grpcio==1.46.3]
ignore_wheels = grpcio-1.46.3-cp310-cp310-macosx_10_10_universal2.whl
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
