from __future__ import annotations

import argparse
import configparser
import contextlib
import functools
import hashlib
import itertools
import json
import os.path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from collections.abc import Generator
from collections.abc import Mapping
from collections.abc import MutableMapping
from typing import ContextManager
from typing import NamedTuple

from packaging.specifiers import InvalidSpecifier
from packaging.specifiers import SpecifierSet
from packaging.tags import Tag
from packaging.tags import compatible_tags
from packaging.tags import cpython_tags
from packaging.tags import platform_tags
from packaging.utils import parse_wheel_filename
from packaging.version import Version

PYTHONS = ((3, 11), (3, 12), (3, 13), (3, 14))

BINARY_EXTS = frozenset(
    (".c", ".cc", ".cpp", ".cxx", ".pxd", ".pxi", ".pyx", ".go", ".rs")
)

DATA_SCRIPTS = re.compile(r"^[^/]+.data/scripts/[^/]+(?<!\.py)$")

PUBLIC_PYPI_RETRY_TIMEOUT = 60 * 60
PUBLIC_PYPI_INITIAL_RETRY_DELAY = 1


def _ordered_supported_tags(version: tuple[int, int]) -> tuple[Tag, ...]:
    # most preferred first
    # ignore the generic `linux_x86_64` / `linux_aarch64` tags
    platforms = [plat for plat in platform_tags() if not plat.startswith("linux_")]
    return (
        *cpython_tags(version, platforms=platforms),
        *compatible_tags(version, platforms=platforms),
    )


def _supported_tags(version: tuple[int, int]) -> frozenset[Tag]:
    return frozenset(_ordered_supported_tags(version))


class Python(NamedTuple):
    version: tuple[int, int]
    tags: frozenset[Tag]

    @property
    def version_string(self) -> str:
        return "{}.{}".format(*self.version)

    @property
    def exe(self) -> str:
        return "python{}.{}".format(*self.version)

    @property
    def full_version(self) -> str:
        return _python_full_version(self.exe)


@functools.cache
def _python_full_version(exe: str) -> str:
    cmd = (exe, "-c", "import platform; print(platform.python_version())")
    return subprocess.check_output(cmd).decode().strip()


class ReleaseFile(NamedTuple):
    filename: str
    url: str
    sha256: str


class Release(NamedTuple):
    requires_python: SpecifierSet
    sdist: ReleaseFile | None
    wheels: tuple[ReleaseFile, ...]

    def supports(self, python: Python) -> bool:
        return self.requires_python.contains(python.full_version, prereleases=True)

    def wheels_for(self, python: Python) -> list[ReleaseFile]:
        """compatible wheels, most preferred first"""
        priority = {
            tag: i for i, tag in enumerate(_ordered_supported_tags(python.version))
        }
        ranked = []
        for wheel in self.wheels:
            ranks = [
                priority[tag]
                for tag in parse_wheel_filename(wheel.filename)[3]
                if tag in priority
            ]
            if ranks:
                ranked.append((min(ranks), wheel))
        return [wheel for _, wheel in sorted(ranked)]


class Package(NamedTuple):
    name: str
    version: Version
    apt_requires: tuple[str, ...]
    brew_requires: tuple[str, ...]
    custom_prebuild: tuple[str, ...]
    likely_binary_ignore: tuple[str, ...]
    python_versions: SpecifierSet
    ignore_requires_python: bool = False

    def satisfied_by(
        self,
        wheels: dict[str, list[tuple[Version, frozenset[Tag]]]],
        tags: frozenset[Tag],
    ) -> bool:
        for version, wheel_tags in wheels.get(self.name, ()):
            if version == self.version and wheel_tags & tags:
                return True
        else:
            return False

    @classmethod
    def make(cls, key: str, val: Mapping[str, str]) -> Package:
        name, version_s = key.split("==", 1)

        dct = dict(val)
        apt_requires = tuple(dct.pop("apt_requires", "").split())
        brew_requires = tuple(dct.pop("brew_requires", "").split())
        custom_prebuild = tuple(dct.pop("custom_prebuild", "").split())
        likely_binary_ignore = tuple(dct.pop("likely_binary_ignore", "").split())
        python_versions = dct.pop("python_versions", "")
        ignore_requires_python = dct.pop("ignore_requires_python", "")
        if ignore_requires_python not in ("", "true"):
            raise ValueError(f"{key}: ignore_requires_python must be `true`")
        # ignore validate-only settings
        for setting in (
            "validate_extras",
            "validate_incorrect_missing_deps",
            "validate_skip_imports",
        ):
            dct.pop(setting, None)
        if dct:
            raise ValueError(f"unexpected attrs for {key}: {sorted(dct)}")

        return cls(
            name=name,
            version=Version(version_s),
            apt_requires=apt_requires,
            brew_requires=brew_requires,
            custom_prebuild=custom_prebuild,
            likely_binary_ignore=likely_binary_ignore,
            python_versions=SpecifierSet(python_versions),
            ignore_requires_python=bool(ignore_requires_python),
        )


def _public_pypi_retry_delays() -> Generator[float]:
    # A release PR can land before public PyPI exposes the new version.
    # Yield backoff delays while the publication propagates.
    deadline = time.monotonic() + PUBLIC_PYPI_RETRY_TIMEOUT
    delay: float = PUBLIC_PYPI_INITIAL_RETRY_DELAY
    while (remaining := deadline - time.monotonic()) > 0:
        delay = min(delay, remaining)
        yield delay
        delay *= 2


def _public_release(package: Package) -> Release:
    url = f"https://pypi.org/pypi/{package.name}/{package.version}/json"
    for delay in _public_pypi_retry_delays():
        try:
            resp = urllib.request.urlopen(url)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            print(f"-> not on public PyPI yet; retrying in {delay:g}s")
            time.sleep(delay)
        else:
            break
    else:
        raise SystemExit(f"{package.name}=={package.version}: not on public PyPI")

    data = json.load(resp)
    try:
        requires_python = SpecifierSet(data["info"]["requires_python"] or "")
    except InvalidSpecifier:
        requires_python = SpecifierSet()

    sdist = None
    wheels = []
    for url_info in data["urls"]:
        release_file = ReleaseFile(
            filename=url_info["filename"],
            url=url_info["url"],
            sha256=url_info["digests"]["sha256"],
        )
        if url_info["packagetype"] == "sdist":
            sdist = release_file
        elif url_info["packagetype"] == "bdist_wheel":
            wheels.append(release_file)

    return Release(requires_python=requires_python, sdist=sdist, wheels=tuple(wheels))


def _fetch(release_file: ReleaseFile, dest: str) -> str:
    os.makedirs(dest, exist_ok=True)
    filename = os.path.join(dest, release_file.filename)
    sha256 = hashlib.sha256()
    with urllib.request.urlopen(release_file.url) as resp, open(filename, "wb") as f:
        while chunk := resp.read(64 * 1024):
            sha256.update(chunk)
            f.write(chunk)

    if sha256.hexdigest() != release_file.sha256:
        raise SystemExit(f"{release_file.filename}: sha256 mismatch")
    return filename


def _add_wheel(d: dict[str, list[tuple[Version, frozenset[Tag]]]], f: str) -> None:
    name, version, _, tags = parse_wheel_filename(f)
    d.setdefault(name, []).append((version, tags))


def _internal_wheels(index: str) -> dict[str, list[tuple[Version, frozenset[Tag]]]]:
    # dumb-pypi specific `packages.json` endpoint
    resp = urllib.request.urlopen(urllib.parse.urljoin(index, "packages.json"))
    ret: dict[str, list[tuple[Version, frozenset[Tag]]]] = {}
    for line in resp:
        _add_wheel(ret, json.loads(line)["filename"])
    return ret


def _darwin_setup_deps(packages_ini: str, dest: str, pypi_url: str) -> None:
    """darwin requires no setup"""


def _darwin_installed_packages() -> frozenset[str]:
    cmd = ("brew", "info", "--json=v1", "--installed")
    contents = json.loads(subprocess.check_output(cmd))
    return frozenset(pkg["name"] for pkg in contents)


def _brew_paths(*pkgs: str) -> list[str]:
    cmd = ("brew", "--prefix", *pkgs)
    return subprocess.check_output(cmd).decode().splitlines()


@contextlib.contextmanager
def _brew_install(packages: tuple[str, ...]) -> Generator[None]:
    installed_before = _darwin_installed_packages()

    subprocess.check_call(
        ("brew", "install", *packages, "--overwrite"),
        env={**os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1"},
    )

    # add the brew installed things to environment
    pkg_paths = _brew_paths(*packages)

    def _paths(*parts: str) -> list[str]:
        return [os.path.join(path, *parts) for path in pkg_paths]

    orig = dict(os.environ)
    os.environ.update(
        CPPFLAGS=" ".join(f"-I{path}" for path in _paths("include")),
        LDFLAGS=" ".join(f"-L{path}" for path in _paths("lib")),
        PKG_CONFIG_PATH=":".join(_paths("lib", "pkgconfig")),
    )

    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(orig)

        newly_installed = _darwin_installed_packages() - installed_before
        if newly_installed:
            purge_cmd = ("brew", "uninstall", *newly_installed)
            subprocess.check_call(purge_cmd, stdout=subprocess.DEVNULL)


@contextlib.contextmanager
def _darwin_install(package: Package) -> Generator[None]:
    with contextlib.ExitStack() as ctx:
        if package.brew_requires:
            ctx.enter_context(_brew_install(package.brew_requires))
        yield


def _darwin_get_archs(file: str) -> set[str]:
    out = subprocess.check_output(("otool", "-hv", "-arch", "all", file))
    lines = out.decode().splitlines()
    if len(lines) % 4 != 0:
        raise AssertionError(f"unexpected otool output:\n{lines}")

    return {
        line.split()[1].lower()
        # output is in chunks of 4, we care about the 4th in each chunk
        for line in lines[3::4]
    }


def _darwin_repair_wheel(filename: str, dest: str) -> None:
    subprocess.check_call(
        (sys.executable, "-mdelocate.cmd.delocate_wheel", filename, "--wheel-dir", dest)
    )


PLAT_MAP = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
IMAGE_NAME = f"ghcr.io/getsentry/pypi-manylinux-{PLAT_MAP[platform.machine()]}-ci"


def _docker_run() -> tuple[str, ...]:
    if shutil.which("podman"):
        return ("podman", "run")
    else:
        return ("docker", "run", "--user", f"{os.getuid()}:{os.getgid()}")


def _linux_setup_deps(packages_ini: str, dest: str, pypi_url: str) -> None:
    if os.environ.get("BUILD_IN_CONTAINER"):
        return

    print("execing into container...")
    cmd = (
        *_docker_run(),
        "--pull=always",
        "--rm",
        f"--volume={os.path.abspath(packages_ini)}:/packages.ini:ro",
        f"--volume={os.path.abspath(dest)}:/dist:rw",
        f"--volume={os.path.dirname(os.path.abspath(__file__))}:/src:ro",
        "--workdir=/src",
        IMAGE_NAME,
        "python3",
        "-um",
        "build",
        "--dest=/dist",
        "--packages-ini=/packages.ini",
        f"--pypi-url={pypi_url}",
    )
    os.execvp(cmd[0], cmd)


@functools.lru_cache(maxsize=1)  # only run once!
def _apt_update() -> None:
    subprocess.check_call(("apt-get", "update", "-qq"))


def _linux_installed_packages() -> frozenset[str]:
    cmd = ("dpkg-query", "--show", "--showformat", "${binary:Package}\n")
    return frozenset(subprocess.check_output(cmd).decode().splitlines())


@contextlib.contextmanager
def _apt_install(packages: tuple[str, ...]) -> Generator[None]:
    _apt_update()

    installed_before = _linux_installed_packages()

    ret = subprocess.run(
        (
            "apt-get",
            "-o",
            "Acquire::Retries=3",
            "install",
            "-qqy",
            "--no-install-recommends",
            *packages,
        ),
        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
        capture_output=True,
    )
    if ret.returncode:
        sys.stderr.buffer.write(ret.stderr)
        ret.check_returncode()

    try:
        yield
    finally:
        newly_installed = _linux_installed_packages() - installed_before
        if newly_installed:
            purge_cmd = ("apt-get", "purge", "-qqy", *newly_installed)
            subprocess.check_call(purge_cmd, stdout=subprocess.DEVNULL)


@contextlib.contextmanager
def _linux_install(package: Package) -> Generator[None]:
    with contextlib.ExitStack() as ctx:
        if package.apt_requires:
            ctx.enter_context(_apt_install(package.apt_requires))
        yield


def _linux_get_archs(file: str) -> set[str]:
    # TODO: this could be more accurate
    out = subprocess.check_output(("file", file)).decode()
    if ", x86-64," in out:
        return {"x86_64"}
    elif ", ARM aarch64," in out:
        return {"aarch64"}
    else:
        raise AssertionError(f"unknown architecture {file=}")


def _linux_repair_wheel(filename: str, dest: str) -> None:
    _, libc = platform.libc_ver()
    libc = libc.replace(".", "_")
    manylinux = f"manylinux_{libc}_{platform.machine()}"
    subprocess.check_call(
        (
            sys.executable,
            "-mauditwheel",
            "repair",
            f"--wheel-dir={dest}",
            f"--plat={manylinux}",
            filename,
        )
    )


class Platform(NamedTuple):
    setup_deps: Callable[[str, str, str], None]
    install: Callable[[Package], ContextManager[None]]
    get_archs: Callable[[str], set[str]]
    repair_wheel: Callable[[str, str], None]


plats = {
    "darwin": Platform(
        setup_deps=_darwin_setup_deps,
        install=_darwin_install,
        get_archs=_darwin_get_archs,
        repair_wheel=_darwin_repair_wheel,
    ),
    "linux": Platform(
        setup_deps=_linux_setup_deps,
        install=_linux_install,
        get_archs=_linux_get_archs,
        repair_wheel=_linux_repair_wheel,
    ),
}
plat = plats[sys.platform]


def _expected_archs_for_wheel(filename: str) -> set[str]:
    archs = set()
    parts = os.path.splitext(os.path.basename(filename))[0].split("-")
    for plat in parts[-1].split("."):
        if plat == "any":
            continue
        elif plat.endswith("_intel"):  # macos
            archs.add("x86_64")
        elif plat.endswith("_universal2"):  # macos
            archs.update(("x86_64", "arm64"))
        else:
            for arch in ("aarch64", "arm64", "x86_64"):
                if plat.endswith(f"_{arch}"):
                    archs.add(arch)
                    break
            else:
                raise AssertionError(f"unexpected {plat=}")

    return archs


def _check_arch(filename: str) -> str | None:
    with tempfile.TemporaryDirectory() as tmpdir:
        archdir = os.path.join(tmpdir, "arch")
        with zipfile.ZipFile(filename) as zipf:
            arch_files = []
            for name in zipf.namelist():
                if "/tests/" in name:
                    continue
                elif name.endswith((".so", ".dylib")) or ".so." in name:
                    arch_files.append(name)
                elif DATA_SCRIPTS.match(name):
                    with zipf.open(name) as f:
                        if f.read(2) != b"#!":
                            arch_files.append(name)

            for arch_file in arch_files:
                zipf.extract(arch_file, archdir)

        archs = _expected_archs_for_wheel(filename)
        for arch_file in arch_files:
            archs_for_file = plat.get_archs(os.path.join(archdir, arch_file))
            if (archs & archs_for_file) != archs:
                return (
                    f"-> {arch_file} has mismatched architectures\n"
                    f"---> expected {', '.join(sorted(archs))}\n"
                    f"---> received {', '.join(sorted(archs_for_file))}\n"
                )

    return None


def _download(release: Release, python: Python, dest: str) -> str | None:
    with tempfile.TemporaryDirectory() as tmpdir:
        # try the most specific wheel first
        # it may be invalidated due to being packaged for the wrong arch
        # in that case fall back to a less specific (e.g. purelib) wheel
        for wheel in release.wheels_for(python):
            filename_full = _fetch(wheel, tmpdir)

            arch_reason = _check_arch(filename_full)
            if arch_reason is not None:
                os.remove(filename_full)
                print(f"-> ignoring: {wheel.filename}\n{arch_reason}")
            else:
                shutil.copy(filename_full, dest)
                return wheel.filename
        else:
            return None


def _join_env(
    *,
    name: str,
    value: str,
    sep: str,
    env: Mapping[str, str] | None = None,
) -> str:
    if env is None:
        env = os.environ

    if name in env:
        return f"{value}{sep}{env[name]}"
    else:
        return value


@contextlib.contextmanager
def _prebuild(
    package: Package, tmpdir: str, *, env: MutableMapping[str, str] | None = None
) -> Generator[None]:
    if env is None:
        env = os.environ

    if not package.custom_prebuild:
        yield
    else:
        prefix = os.path.join(tmpdir, "prefix")
        os.makedirs(prefix, exist_ok=True)

        def _prefix_path(*parts: str) -> str:
            return os.path.join(prefix, *parts)

        subprocess.check_call((*package.custom_prebuild, prefix))
        before = {**env}
        env.update(
            PATH=_join_env(
                name="PATH",
                value=_prefix_path("bin"),
                sep=os.pathsep,
                env=env,
            ),
            CPPFLAGS=_join_env(
                name="CPPFLAGS",
                value=f"-I{_prefix_path('include')}",
                sep=" ",
                env=env,
            ),
            LDFLAGS=_join_env(
                name="LDFLAGS",
                value=f"-L{_prefix_path('lib')}",
                sep=" ",
                env=env,
            ),
            LD_LIBRARY_PATH=_join_env(
                name="LD_LIBRARY_PATH",
                value=_prefix_path("lib"),
                sep=os.pathsep,
                env=env,
            ),
            PKG_CONFIG_PATH=_join_env(
                name="PKG_CONFIG_PATH",
                value=_prefix_path("lib", "pkgconfig"),
                sep=os.pathsep,
                env=env,
            ),
        )
        try:
            yield
        finally:
            env.clear()
            env.update(before)


def _likely_binary(sdist: str, likely_binary_ignore: tuple[str, ...]) -> str | None:
    if sdist.endswith(".zip"):
        with zipfile.ZipFile(sdist) as zipf:
            names = zipf.namelist()

            setup_py_contents = b""
            for name in names:
                if name.endswith("/setup.py"):
                    with zipf.open(name) as f:
                        setup_py_contents += f.read()

    else:
        with tarfile.open(sdist) as tarf:
            names = tarf.getnames()

            setup_py_contents = b""
            for name in names:
                if name.endswith("/setup.py"):
                    opt_f = tarf.extractfile(name)
                    assert opt_f is not None
                    with opt_f as f:
                        setup_py_contents += f.read()

    ret = set()
    for name in names:
        if "/test/" in name or "/tests/" in name:
            continue

        if name in likely_binary_ignore:
            continue

        _, ext = os.path.splitext(name)
        if ext in BINARY_EXTS:
            ret.add(ext)

    if ret:
        return f"sdist contains files with these extensions: {', '.join(sorted(ret))}"
    elif b"cffi_modules" in setup_py_contents:
        return "sdist setup.py has `cffi_modules`"
    else:
        return None


def _produced_binary(wheel: str) -> bool:
    with zipfile.ZipFile(wheel) as zipf:
        for name in zipf.namelist():
            if name.endswith(".so"):
                return True
            # TODO: uwsgi
        else:
            return False


def _build(
    package: Package,
    python: Python,
    sdist_file: ReleaseFile,
    dest: str,
    index_url: str,
    timeout: int | None = None,
) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        with plat.install(package), _prebuild(package, tmpdir):
            # download the sdist first such that we can build against our index
            sdist = _fetch(sdist_file, os.path.join(tmpdir, "sdist"))

            build_dir = os.path.join(tmpdir, "build")
            subprocess.check_call(
                (
                    "uv",
                    "build",
                    "--no-config",
                    "--quiet",
                    "--wheel",
                    f"--python={python.exe}",
                    "--python-preference=only-system",
                    f"--default-index={index_url}",
                    f"--out-dir={build_dir}",
                    sdist,
                ),
                env={
                    **os.environ,
                    # disable bulky "universal2" building
                    "ARCHFLAGS": "",
                },
                timeout=timeout,
            )
            # uv also writes a `.gitignore` into the output directory
            (filename,) = (f for f in os.listdir(build_dir) if f.endswith(".whl"))
            filename_full = os.path.join(build_dir, filename)

            likely_binary_reason = _likely_binary(sdist, package.likely_binary_ignore)
            if likely_binary_reason and not _produced_binary(filename_full):
                raise SystemExit(
                    f"{package.name}=={package.version} expected binary as "
                    f"{likely_binary_reason}"
                )

            if filename.endswith("-any.whl"):  # purelib
                shutil.copy(filename_full, dest)
                return filename
            else:
                repair_dir = os.path.join(tmpdir, "repair")
                plat.repair_wheel(filename_full, repair_dir)
                (filename,) = os.listdir(repair_dir)
                shutil.copy(os.path.join(repair_dir, filename), dest)
                return filename


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pypi-url", required=True)
    parser.add_argument("--packages-ini", default="packages.ini")
    parser.add_argument("--dest", default="dist")
    parser.add_argument("--upgrade-python", action="store_true")
    args = parser.parse_args()

    cfg = configparser.RawConfigParser()
    if not cfg.read(args.packages_ini):
        raise SystemExit(f"does not exist: {args.packages_ini}")

    index_url = urllib.parse.urljoin(args.pypi_url, "simple")

    os.makedirs(args.dest, exist_ok=True)

    plat.setup_deps(args.packages_ini, args.dest, args.pypi_url)

    pythons = [Python(version, _supported_tags(version)) for version in PYTHONS]

    internal_wheels = _internal_wheels(args.pypi_url)
    built: dict[str, list[tuple[Version, frozenset[Tag]]]] = {}

    timeout = 600 if args.upgrade_python else None
    failures: list[str] = []
    failed_names: set[str] = set()

    all_packages = [Package.make(k, cfg[k]) for k in cfg.sections()]
    releases: dict[str, Release] = {}

    if args.upgrade_python:
        # sort newest versions first within each package name so we can
        # bail out early: if the newest version fails, older ones will too
        by_name: dict[str, list[Package]] = {}
        for p in all_packages:
            by_name.setdefault(p.name, []).append(p)
        all_packages = [
            p
            for pkgs in by_name.values()
            for p in sorted(pkgs, key=lambda p: p.version, reverse=True)
        ]

    for package, python in itertools.product(all_packages, pythons):
        if package.satisfied_by(internal_wheels, python.tags):
            continue
        elif python.version_string not in package.python_versions:
            continue

        pkg_id = f"{package.name}=={package.version}"

        if args.upgrade_python and package.name in failed_names:
            print(f"=== {pkg_id}@{python.version}")
            print(f"!!! SKIPPED (newer version already failed): {pkg_id}")
            failures.append(pkg_id)
            continue

        print(f"=== {package.name}=={package.version}@{python.version}")

        if package.satisfied_by(built, python.tags):
            print("-> just built!")
        else:
            try:
                if pkg_id not in releases:
                    releases[pkg_id] = _public_release(package)
                release = releases[pkg_id]
                if package.ignore_requires_python:
                    release = release._replace(requires_python=SpecifierSet())

                if not any(
                    release.supports(p)
                    for p in pythons
                    if p.version_string in package.python_versions
                ):
                    raise SystemExit(
                        f"{pkg_id}: requires-python {release.requires_python} "
                        f"matches none of the build pythons"
                    )
                elif not release.supports(python):
                    print(f"-> skipping: requires-python {release.requires_python}")
                    continue

                print("-> building...")
                downloaded_wheel = _download(release, python, args.dest)
                if downloaded_wheel is not None:
                    _add_wheel(built, downloaded_wheel)
                    print(f"-> downloaded! {downloaded_wheel}")
                elif release.sdist is None:
                    raise SystemExit(
                        f"{pkg_id}: no sdist and no usable wheel for "
                        f"python {python.version_string}"
                    )
                else:
                    built_wheel = _build(
                        package,
                        python,
                        release.sdist,
                        args.dest,
                        index_url,
                        timeout=timeout,
                    )
                    _add_wheel(built, built_wheel)
                    print(f"-> built! {built_wheel}")
            except (
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                SystemExit,
            ) as e:
                if args.upgrade_python:
                    print(f"!!! FAILED: {pkg_id}: {e}")
                    failures.append(pkg_id)
                    failed_names.add(package.name)
                elif python.version == (3, 14):
                    print(f"!!! WARNING (py3.14): {pkg_id}: {e}")
                else:
                    raise

    if failures:
        print(f"\nFAILED PACKAGES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
