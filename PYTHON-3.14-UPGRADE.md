# Python 3.14 Upgrade — Build Failures

Date: 2026-02-24
Python version: 3.14.3
CI run: https://github.com/getsentry/pypi/actions/runs/22364364543

## Summary by category

| Category | Count | Packages |
|----------|-------|----------|
| PyO3 too old for 3.14 | 7 | jiter, orjson, pydantic-core, sentry-streams, tiktoken, vroomrs, rpds-py |
| No sdist on PyPI | 3 | backports-zstd, lief, sentry-forked-jsonnet |
| CPython 3.14 C API change | 1 | pyuwsgi |
| Missing build dependency | 1 | xmlsec |
| Build timeout | 1 | grpcio (1.73.1 on linux-amd64 only) |
| Platform-specific issues | 3 | grpcio (1.67.0 macos), pillow (linux-amd64), p4python (macos) |
| Validation failure (import) | 1 | uvloop |

Note: The last two categories (timeout + platform-specific) are NOT Python 3.14 incompatibilities.
These packages built successfully on at least one platform and were commented out (not restricted).

## Detailed failures

### PyO3 too old for Python 3.14

These packages use PyO3 versions that cap support at Python 3.13. They need upstream
releases with PyO3 0.25+ (which adds 3.14 support).

#### jiter==0.9.0
- **Platforms**: linux-amd64, macos
- **Category**: PyO3 too old
- **Error**: pyo3 0.24.0 — `the maximum Python version is 3.13, found 3.14`
- **Note**: jiter==0.10.0 builds fine on 3.14

#### orjson==3.10.10
- **Platforms**: linux-amd64, macos
- **Category**: PyO3 too old
- **Error**: pyo3 0.23.0-dev — `the maximum Python version is 3.13, found 3.14`

#### pydantic-core==2.33.2
- **Platforms**: linux-amd64, macos
- **Category**: PyO3 too old
- **Error**: pyo3 0.24.1 — `the maximum Python version is 3.13, found 3.14`
- **Skipped older versions**: 2.24.2, 2.23.4

#### sentry-streams==0.0.35
- **Platforms**: linux-amd64, macos
- **Category**: PyO3 too old
- **Error**: pyo3 0.24.0 — `the maximum Python version is 3.13, found 3.14`
- **Skipped older versions**: 0.0.17 through 0.0.34
- **Note**: Already had `python_versions = <3.14` from previous pass

#### tiktoken==0.8.0
- **Platforms**: linux-amd64, macos
- **Category**: PyO3 too old
- **Error**: pyo3 0.22.6 — `the maximum Python version is 3.13, found 3.14`

#### vroomrs==0.1.19
- **Platforms**: linux-amd64, macos
- **Category**: PyO3 too old
- **Error**: pyo3 0.24.1 — `the maximum Python version is 3.13, found 3.14`
- **Skipped older versions**: 0.1.2 through 0.1.18

#### rpds-py==0.20.0
- **Platforms**: linux-amd64, macos
- **Category**: PyO3 too old
- **Error**: pyo3 0.22.2 — `the maximum Python version is 3.13, found 3.14`
- **Note**: Already had `python_versions = <3.14` from previous pass

### No sdist on PyPI

These packages only publish binary wheels (no source distribution), and no cp314 wheel exists yet.

#### backports-zstd==1.3.0
- **Platforms**: all
- **Category**: No sdist
- **Error**: `pip download` found no matching distribution — wheel-only package with no cp314 wheel

#### lief==0.16.6
- **Platforms**: linux-amd64, macos
- **Category**: No sdist
- **Error**: `pip download` found no matching distribution — no sdist for 0.16.6

#### sentry-forked-jsonnet==0.20.0.post4
- **Platforms**: linux-amd64, macos
- **Category**: No sdist
- **Error**: `pip download` found no matching distribution
- **Note**: Already had `python_versions = <3.14` from previous pass

### CPython 3.14 C API changes

#### pyuwsgi==2.0.29
- **Platforms**: linux-amd64, macos
- **Category**: CPython 3.14 API change
- **Error**: `c_recursion_remaining` removed from `PyThreadState` in CPython 3.14
- **Skipped older versions**: 2.0.28.post1, 2.0.27.post1
- **Note**: pyuwsgi==2.0.30 builds fine on 3.14

### Missing build dependencies

#### xmlsec==1.3.14
- **Platforms**: linux-amd64, macos
- **Category**: Missing build dep
- **Error**: Build dependency `lxml` has no cp314 wheel on the internal PyPI index
- **Note**: lxml==5.3.0 itself builds fine on 3.14, but xmlsec needs it at build time from the index
- **Status**: Unblocked once lxml==5.3.0 cp314 wheel is deployed to internal index. After merging (which builds and deploys lxml's cp314 wheel), remove `python_versions = <3.14` from xmlsec==1.3.14 in a follow-up commit.

### Platform-specific issues (NOT Python 3.14 incompatibilities)

These packages were NOT marked with `python_versions = <3.14` because they can build
on Python 3.14 — they just had issues on specific platforms.

#### grpcio==1.73.1
- **Platforms**: linux-amd64 only (succeeded on linux-arm64 and macos)
- **Category**: Build timeout
- **Error**: Build timed out after 600 seconds on linux-amd64 (compiled successfully on macos in ~8.5 min)
- **Note**: grpcio==1.75.1 succeeds everywhere

#### grpcio==1.67.0
- **Platforms**: macos only (succeeded on linux-arm64)
- **Category**: C compilation error
- **Error**: Bundled zlib `fdopen` macro conflicts with macOS `_stdio.h`

#### pillow==11.2.1
- **Platforms**: linux-amd64 only (succeeded on macos)
- **Category**: Missing system library
- **Error**: Missing `libjpeg` headers in the Docker build container
- **Note**: pillow==11.3.0 succeeds everywhere
- **Fix**: Added `libjpeg-dev` to Dockerfile and re-added pillow versions to packages.ini

#### p4python==2025.1.2767466
- **Platforms**: macos only (succeeded on linux-amd64)
- **Category**: Missing build configuration
- **Error**: `setup.py` requires `--ssl` parameter and P4API on macOS; multiple env issues
- **Status**: Marked `python_versions = <3.14` — too many macOS-specific build issues (SSL detection, P4API download) to fix in this pass

### Validation failures

These packages built successfully but failed during import validation on Python 3.14.

#### uvloop==0.21.0
- **Platforms**: all
- **Category**: CPython 3.14 API removal
- **Error**: `ImportError: cannot import name 'BaseDefaultEventLoopPolicy' from 'asyncio.events'`
- **Note**: `asyncio.events.BaseDefaultEventLoopPolicy` was removed in CPython 3.14

This needs to be figured out for granian to pass validation as well.

