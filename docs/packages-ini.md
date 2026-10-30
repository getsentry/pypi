# `packages.ini` reference

Each section of `packages.ini` is one package version, named `[name==version]`.
Most sections have no options.
The `format-packages-ini` pre-commit hook (`format_ini.py`) sorts sections and values.
The hook drops `#` comments, so put no comments in `packages.ini`.

## build options

`build.py` reads these options. An unknown option fails the build.

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

### custom_prebuild

sometimes the dependencies aren't packaged for apt / brew and you need a custom
script to set them up.  this script will be passed a single "prefix" directory
(which contains the standard `bin` / `lib` / `include` / etc. structure).

the script should set up whatever tools are necessary inside only that directory

```ini
[google-crc32c==1.3.0]
custom_prebuild = prebuild/crc32c 1.1.2
```

The scripts live in `prebuild/`.

### config_settings

`uv build` passes each whitespace-separated value as a `--config-setting`.
Use it when an sdist compiles its extensions only when asked.

```ini
[pydantic==1.10.26]
config_settings = --build-option=--cythonize
require_binary = true
```

### likely_binary_ignore

when the sdist has source files of a compiled language (see `BINARY_EXTS` in `build.py`),
we would expect compiled things (e.g. binary executables, shared objects)
in the wheel. sometimes this isn't the case, and you can ignore those
source files:


```ini
[salt==3006.6]
likely_binary_ignore =
    salt-3006.6/pkg/old/smartos/esky/sodium_grabber.c
```

### require_binary

Set `require_binary = true` when a purelib wheel of the package works but is much slower than the compiled one.
`build.py` then ignores purelib wheels, both on public PyPI and in the index, and fails when the wheel it builds has no `.so` file.
Use it with `config_settings` when the sdist only compiles when asked.
pydantic 1.x is the example: PyPI has compiled wheels for some platforms only, plus a purelib wheel.

### python_versions

some packages are only intended for particular python versions (or don't
otherwise build cleanly).  the builds can be filtered using `python_versions`
(though usually you should try and upgrade the relevant package).

```ini
[brotli==1.0.9]
python_versions = <3.12
```

`validate.py` also skips the excluded versions.

You do not need `python_versions` to repeat a package's `Requires-Python`.
`build.py` and `validate.py` already skip the Python versions that `Requires-Python` excludes.

## validation options

after building the packages will be checked that they can install and import

`validate.py` reads these options.

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

### validate_skip_imports

this should usually not be used but sometimes you need to skip importing some
top-level modules due to side-effects or weird runtime requirements

```ini
[pyuwsgi==2.0.20]
validate_skip_imports = uwsgidecorators
```
