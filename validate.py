from __future__ import annotations

import argparse
import configparser
import os.path
import re
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Mapping
from typing import NamedTuple

from packaging.tags import Tag
from packaging.utils import parse_wheel_filename
from packaging.version import Version

PYTHONS = ((3, 9), (3, 10), (3, 11))
DIST_INFO_RE = re.compile(r"^[^/]+.dist-info/[^/]+$")


class Info(NamedTuple):
    validate_extras: str | None
    validate_incorrect_missing_deps: tuple[str, ...]
    validate_skip_imports: tuple[str, ...]

    @classmethod
    def from_dct(cls, dct: Mapping[str, str]) -> Info:
        return cls(
            validate_extras=dct.get("validate_extras") or None,
            validate_incorrect_missing_deps=tuple(
                dct.get("validate_incorrect_missing_deps", "").split()
            ),
            validate_skip_imports=tuple(dct.get("validate_skip_imports", "").split()),
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
        if "RECORD" in dist_info_names:
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
            raise NotImplementedError("need RECORD")


def _validate(
    *,
    python: str,
    filename: str,
    info: Info,
    index_url: str,
) -> None:
    print(f"validating {python}: {filename}")
    with tempfile.TemporaryDirectory() as tmpdir:
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
            if s not in info.validate_skip_imports:
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
