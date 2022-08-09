from __future__ import annotations

import argparse
import configparser
import contextlib
import functools
import itertools
import json
import os.path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from typing import Callable
from typing import ContextManager
from typing import Generator
from typing import Mapping
from typing import NamedTuple

from packaging.tags import compatible_tags
from packaging.tags import cpython_tags
from packaging.tags import platform_tags
from packaging.tags import Tag
from packaging.utils import parse_wheel_filename
from packaging.version import Version

PYTHONS = ((3, 8), (3, 9), (3, 10))

BINARY_EXTS = frozenset(
    (".c", ".cc", ".cpp", ".cxx", ".pxd", ".pxi", ".pyx", ".go", ".rs")
)


def _supported_tags(version: tuple[int, int]) -> frozenset[Tag]:
    # ignore the generic `linux_x86_64` / `linux_aarch64` tags
    platforms = [plat for plat in platform_tags() if not plat.startswith("linux_")]
    return frozenset(
        (
            *cpython_tags(version, platforms=platforms),
            *compatible_tags(version, platforms=platforms),
        )
    )


class Python(NamedTuple):
    version: tuple[int, int]
    tags: frozenset[Tag]

    @property
    def exe(self) -> str:
        return "python{}.{}".format(*self.version)


class Wheel(NamedTuple):
    filename: str


class Package(NamedTuple):
    name: str
    version: Version
    apt_requires: tuple[str, ...]
    brew_requires: tuple[str, ...]
    ignore_wheels: tuple[str, ...]

    def satisfied_by(
        self,
        wheels: tuple[Wheel, ...],
        tags: frozenset[Tag],
    ) -> Wheel | None:
        for wheel in wheels:
            pkg, version, _, wheel_tags = parse_wheel_filename(wheel.filename)
            if pkg == self.name and version == self.version and wheel_tags & tags:
                return wheel
        else:
            return None

    @classmethod
    def make(cls, key: str, val: Mapping[str, str]) -> Package:
        name, version_s = key.split("==", 1)

        dct = dict(val)
        apt_requires = tuple(dct.pop("apt_requires", "").split())
        brew_requires = tuple(dct.pop("brew_requires", "").split())
        ignore_wheels = tuple(dct.pop("ignore_wheels", "").split())
        if dct:
            raise ValueError(f"unexpected attrs for {key}: {sorted(dct)}")

        return cls(
            name=name,
            version=Version(version_s),
            apt_requires=apt_requires,
            brew_requires=brew_requires,
            ignore_wheels=ignore_wheels,
        )


def _internal_wheels(index: str) -> tuple[Wheel, ...]:
    # dumb-pypi specific `packages.json` endpoint
    resp = urllib.request.urlopen(urllib.parse.urljoin(index, "packages.json"))
    return tuple(Wheel(json.loads(line)["filename"]) for line in resp)


def _darwin_setup_deps(packages_ini: str, dest: str) -> None:
    """darwin requires no setup"""


def _darwin_installed_packages() -> frozenset[str]:
    cmd = ("brew", "info", "--json=v1", "--installed")
    contents = json.loads(subprocess.check_output(cmd))
    return frozenset(pkg["name"] for pkg in contents)


def _brew_paths(*pkgs: str) -> list[str]:
    cmd = ("brew", "--prefix", *pkgs)
    return subprocess.check_output(cmd).decode().splitlines()


@contextlib.contextmanager
def _brew_install(packages: tuple[str, ...]) -> Generator[None, None, None]:
    installed_before = _darwin_installed_packages()

    subprocess.check_call(
        ("brew", "install", *packages),
        env={**os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1"},
    )

    # add the brew installed things to environment
    pkg_paths = _brew_paths(*packages)

    def _paths(*parts: str) -> list[str]:
        return [os.path.join(path, *parts) for path in pkg_paths]

    orig = dict(os.environ)
    os.environ.update(
        CFLAGS=" ".join(f"-I{path}" for path in _paths("include")),
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
def _darwin_install(package: Package) -> Generator[None, None, None]:
    with contextlib.ExitStack() as ctx:
        if package.brew_requires:
            ctx.enter_context(_brew_install(package.brew_requires))
        yield


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


def _linux_setup_deps(packages_ini: str, dest: str) -> None:
    if os.environ.get("BUILD_IN_CONTAINER"):
        return

    print("execing into container...")
    cmd = (
        *_docker_run(),
        "--pull=always",
        "--rm",
        f"--volume={os.path.abspath(packages_ini)}:/packages.ini:ro",
        f"--volume={os.path.abspath(dest)}:/dist:rw",
        # TODO: if we target 3.9+: __file__ is an abspath
        f"--volume={os.path.abspath(__file__)}:/{os.path.basename(__file__)}:ro",
        "--workdir=/",
        IMAGE_NAME,
        "python3",
        "-um",
        "build",
        *sys.argv[1:],
    )
    os.execvp(cmd[0], cmd)


@functools.lru_cache(maxsize=1)  # only run once!
def _apt_update() -> None:
    subprocess.check_call(("apt-get", "update", "-qq"))


def _linux_installed_packages() -> frozenset[str]:
    cmd = ("dpkg-query", "--show", "--showformat", "${binary:Package}\n")
    return frozenset(subprocess.check_output(cmd).decode().splitlines())


@contextlib.contextmanager
def _apt_install(packages: tuple[str, ...]) -> Generator[None, None, None]:
    _apt_update()

    installed_before = _linux_installed_packages()

    subprocess.check_call(
        (
            "apt-get",
            "install",
            "-qqy",
            "--no-install-recommends",
            *packages,
        ),
        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )

    try:
        yield
    finally:
        newly_installed = _linux_installed_packages() - installed_before
        if newly_installed:
            purge_cmd = ("apt-get", "purge", "-qqy", *newly_installed)
            subprocess.check_call(purge_cmd, stdout=subprocess.DEVNULL)


@contextlib.contextmanager
def _linux_install(package: Package) -> Generator[None, None, None]:
    with contextlib.ExitStack() as ctx:
        if package.apt_requires:
            ctx.enter_context(_apt_install(package.apt_requires))
        yield


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
    setup_deps: Callable[[str, str], None]
    install: Callable[[Package], ContextManager[None]]
    repair_wheel: Callable[[str, str], None]


plats = {
    "darwin": Platform(
        setup_deps=_darwin_setup_deps,
        install=_darwin_install,
        repair_wheel=_darwin_repair_wheel,
    ),
    "linux": Platform(
        setup_deps=_linux_setup_deps,
        install=_linux_install,
        repair_wheel=_linux_repair_wheel,
    ),
}
plat = plats[sys.platform]


def _download(package: Package, python: Python, dest: str) -> Wheel | None:
    with tempfile.TemporaryDirectory() as tmpdir:
        pip = (python.exe, "-mpip")

        if not subprocess.call(
            (
                *pip,
                "download",
                f"--dest={tmpdir}",
                "--index-url=https://pypi.org/simple",
                "--no-deps",
                "--only-binary=:all:",
                f"{package.name}=={package.version}",
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ):
            (filename,) = os.listdir(tmpdir)
            filename_full = os.path.join(tmpdir, filename)
            if filename in package.ignore_wheels:
                os.remove(filename_full)
                print(f"-> ignoring: {filename}")
                return None
            else:
                shutil.copy(filename_full, dest)
                return Wheel(filename)
        else:
            return None


def _likely_binary_exts(sdist: str) -> set[str]:
    if sdist.endswith(".zip"):
        with zipfile.ZipFile(sdist) as zipf:
            names = zipf.namelist()
    else:
        with tarfile.open(sdist) as tarf:
            names = tarf.getnames()

    ret = set()
    for name in names:
        if "/test/" in name or "/tests/" in name:
            continue

        _, ext = os.path.splitext(name)
        if ext in BINARY_EXTS:
            ret.add(ext)
    return ret


def _produced_binary(wheel: str) -> bool:
    with zipfile.ZipFile(wheel) as zipf:
        for name in zipf.namelist():
            if name.endswith(".so"):
                return True
            # TODO: uwsgi
        else:
            return False


def _build(package: Package, python: Python, dest: str, index_url: str) -> Wheel:
    with tempfile.TemporaryDirectory() as tmpdir:
        pip = (python.exe, "-mpip")

        with plat.install(package):
            # download the sdist first such that we can build against our index
            sdist_dir = os.path.join(tmpdir, "sdist")
            subprocess.check_call(
                (
                    *pip,
                    "download",
                    f"--dest={sdist_dir}",
                    "--index-url=https://pypi.org/simple",
                    "--no-deps",
                    f"--no-binary={package.name}",
                    f"{package.name}=={package.version}",
                )
            )
            (sdist,) = os.listdir(sdist_dir)
            sdist = os.path.join(sdist_dir, sdist)

            build_dir = os.path.join(tmpdir, "build")
            subprocess.check_call(
                (
                    *pip,
                    "wheel",
                    f"--index-url={index_url}",
                    f"--wheel-dir={build_dir}",
                    "--no-deps",
                    sdist,
                ),
                # disable bulky "universal2" building
                env={**os.environ, "ARCHFLAGS": ""},
            )
            (filename,) = os.listdir(build_dir)
            filename_full = os.path.join(build_dir, filename)

            sdist_likely_exts = _likely_binary_exts(sdist)
            if sdist_likely_exts and not _produced_binary(filename_full):
                raise SystemExit(
                    f"{package.name}=={package.version} expected binary as "
                    f"sdist contains files with these extensions: "
                    f'{", ".join(sorted(sdist_likely_exts))}'
                )

            if filename.endswith("-any.whl"):  # purelib
                shutil.copy(filename_full, dest)
                return Wheel(filename)
            else:
                repair_dir = os.path.join(tmpdir, "repair")
                plat.repair_wheel(filename_full, repair_dir)
                (filename,) = os.listdir(repair_dir)
                shutil.copy(os.path.join(repair_dir, filename), dest)
                return Wheel(filename)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pypi-url", required=True)
    parser.add_argument("--packages-ini", default="packages.ini")
    parser.add_argument("--dest", default="dist")
    args = parser.parse_args()

    cfg = configparser.RawConfigParser()
    if not cfg.read(args.packages_ini):
        raise SystemExit(f"does not exist: {args.packages_ini}")

    index_url = urllib.parse.urljoin(args.pypi_url, "simple")

    os.makedirs(args.dest, exist_ok=True)

    plat.setup_deps(args.packages_ini, args.dest)

    pythons = [Python(version, _supported_tags(version)) for version in PYTHONS]

    internal_wheels = _internal_wheels(args.pypi_url)
    built: list[Wheel] = []

    all_packages = [Package.make(k, cfg[k]) for k in cfg.sections()]
    for package, python in itertools.product(all_packages, pythons):
        print(f"=== {package.name}=={package.version}@{python.version}")

        if package.satisfied_by(built, python.tags):
            print("-> just built!")
        elif package.satisfied_by(internal_wheels, python.tags):
            print("-> already built!")
        else:
            print("-> building...")
            downloaded_wheel = _download(package, python, args.dest)
            if downloaded_wheel is not None:
                built.append(downloaded_wheel)
                print(f"-> downloaded! {downloaded_wheel.filename}")
            else:
                built_wheel = _build(package, python, args.dest, index_url)
                built.append(built_wheel)
                print(f"-> built! {built_wheel.filename}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
