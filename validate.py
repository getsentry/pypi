from __future__ import annotations

import argparse
import configparser
import os.path
import re
import subprocess
import sys
import tempfile
import zipfile
from typing import Mapping
from typing import NamedTuple

from packaging.tags import Tag
from packaging.utils import parse_wheel_filename
from packaging.version import Version

PYTHONS = ((3, 8), (3, 9), (3, 10))
DIST_INFO_RE = re.compile(r"^[^/]+.dist-info/[^/]+$")
DATA_SCRIPTS = re.compile(r"^[^/]+.data/scripts/[^/]+$")


class Info(NamedTuple):
    validate_extras: str | None
    validate_incorrect_missing_deps: tuple[str, ...]

    @classmethod
    def from_dct(cls, dct: Mapping[str, str]) -> Info:
        return cls(
            validate_extras=dct.get("validate_extras") or None,
            validate_incorrect_missing_deps=tuple(
                dct.get("validate_incorrect_missing_deps", "").split()
            ),
        )


def _parse_cp_tag(s: str) -> tuple[int, int]:
    return int(s[2]), int(s[3:])


def _py_exe(major: int, minor: int) -> str:
    return f"python{major}.{minor}"


def _pythons_to_check(tags: frozenset[Tag]) -> tuple[str, ...]:
    ret: set[str] = set()
    for tag in tags:
        if tag.abi == "abi3" and tag.interpreter.startswith("cp"):
            min_py = _parse_cp_tag(tag.interpreter)
            ret.update(_py_exe(*py) for py in PYTHONS if py >= min_py)
        elif tag.interpreter.startswith("cp"):
            ret.add(_py_exe(*_parse_cp_tag(tag.interpreter)))
        elif tag.interpreter == "py2":
            continue
        elif tag.interpreter == "py3":
            ret.update(_py_exe(*py) for py in PYTHONS)
        else:
            raise AssertionError(f"unexpected tag: {tag}")

    if not ret:
        raise AssertionError(f"no interpreters found for {tags}")
    else:
        return tuple(sorted(ret))


def _top_imports(whl: str) -> list[str]:
    with zipfile.ZipFile(whl) as zipf:
        dist_info_names = {
            os.path.basename(name): name
            for name in zipf.namelist()
            if DIST_INFO_RE.match(name)
        }
        if "top_level.txt" in dist_info_names:
            with zipf.open(dist_info_names["top_level.txt"]) as f:
                return f.read().decode().splitlines()
        elif "RECORD" in dist_info_names:
            with zipf.open(dist_info_names["RECORD"]) as f:
                pkgs = {}
                for line_b in f:
                    fname = line_b.decode().split(",")[0]
                    if fname.endswith("/__init__.py"):
                        pkgs[fname.split("/")[0]] = 1
                    elif "/" not in fname and fname.endswith((".so", ".py")):
                        pkgs[fname.split(".")[0]] = 1
                return list(pkgs)
        else:
            raise NotImplementedError("need top_level.txt or RECORD")


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


def _get_archs_darwin(file: str) -> set[str]:
    out = subprocess.check_output(("otool", "-hv", "-arch", "all", file))
    lines = out.decode().splitlines()
    if len(lines) % 4 != 0:
        raise AssertionError(f"unexpected otool output:\n{lines}")

    return {
        line.split()[1].lower()
        # output is in chunks of 4, we care about the 4th in each chunk
        for line in lines[3::4]
    }


def _get_archs_linux(file: str) -> set[str]:
    # TODO: this could be more accurate
    out = subprocess.check_output(("file", file)).decode()
    if ", x86-64," in out:
        return {"x86_64"}
    elif ", ARM aarch64," in out:
        return {"aarch64"}
    else:
        raise AssertionError(f"unknown architecture {file=}")


if sys.platform == "darwin":  # pragma: darwin cover
    _get_archs = _get_archs_darwin
else:  # pragma: darwin no cover
    _get_archs = _get_archs_linux


def _validate(
    *,
    python: str,
    filename: str,
    info: Info,
    index_url: str,
) -> None:
    print(f"validating {python}: {filename}")
    with tempfile.TemporaryDirectory() as tmpdir:
        print("checking arch")
        archdir = os.path.join(tmpdir, "arch")
        with zipfile.ZipFile(filename) as zipf:
            arch_files = []
            for name in zipf.namelist():
                if name.endswith((".so", ".dylib")) or ".so." in name:
                    arch_files.append(name)
                elif DATA_SCRIPTS.match(name):
                    with zipf.open(name) as f:
                        if f.read(2) != b"#!":
                            arch_files.append(name)

            for arch_file in arch_files:
                zipf.extract(arch_file, archdir)

        archs = _expected_archs_for_wheel(filename)
        for arch_file in arch_files:
            archs_for_file = _get_archs(os.path.join(archdir, arch_file))
            if archs_for_file != archs:
                raise SystemExit(
                    f"-> {arch_file} has mismatched architectures\n"
                    f"---> you may be able to fix this with `ignore_wheels = {os.path.basename(filename)}`\n"
                    f'---> expected {", ".join(sorted(archs))}\n'
                    f'---> received {", ".join(sorted(archs_for_file))}\n'
                )

        print("creating env")
        venv = os.path.join(tmpdir, "venv")
        py = os.path.join(venv, "bin", "python")

        subprocess.check_call(
            (
                sys.executable,
                "-mvirtualenv",
                "--no-periodic-update",
                "--pip=embed",
                "--setuptools=embed",
                "--wheel=embed",
                "--quiet",
                f"--python={python}",
                venv,
            )
        )

        print("=> installing")
        if info.validate_extras is not None:
            install_target = f"{filename}[{info.validate_extras}]"
        else:
            install_target = filename

        subprocess.check_call(
            (
                py,
                "-mpip",
                "install",
                "--quiet",
                "--no-cache-dir",
                "--disable-pip-version-check",
                "--only-binary=:all:",
                f"--index-url={index_url}",
                # allow just-built wheels to count too
                f"--find-links={os.path.dirname(filename)}",
                install_target,
                *info.validate_incorrect_missing_deps,
            )
        )

        print("=> importing")
        for s in _top_imports(filename):
            subprocess.check_call((py, "-c", f"__import__({s!r})"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-url", required=True)
    parser.add_argument("--dist", default="dist")
    parser.add_argument("--packages-ini", default="packages.ini")
    args = parser.parse_args()

    cfg = configparser.ConfigParser()
    if not cfg.read(args.packages_ini):
        raise SystemExit(f"{args.packages_ini}: not found")

    packages = {}
    for k in cfg.sections():
        pkg, _, version_s = k.partition("==")
        packages[(pkg, Version(version_s))] = Info.from_dct(cfg[k])

    for filename in sorted(os.listdir(args.dist)):
        name, version, _, wheel_tags = parse_wheel_filename(filename)
        info = packages[(name, version)]
        for python in _pythons_to_check(wheel_tags):
            _validate(
                python=python,
                filename=os.path.join(args.dist, filename),
                info=info,
                index_url=args.index_url,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
