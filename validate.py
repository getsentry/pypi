from __future__ import annotations

import argparse
import os.path
import re
import subprocess
import sys
import tempfile
import zipfile

from packaging.tags import Tag
from packaging.utils import parse_wheel_filename

DIST_INFO_RE = re.compile(r"^[^/]+.dist-info/[^/]+$")


def _pythons_to_check(tags: frozenset[Tag]) -> tuple[str, ...]:
    ret = set()
    for tag in tags:
        if tag.interpreter.startswith("cp"):
            ret.add(f"python{tag.interpreter[2]}.{tag.interpreter[3:]}")
        elif tag.interpreter == "py2":
            continue
        elif tag.interpreter == "py3":
            ret.update(("python3.8", "python3.9", "python3.10"))
        else:
            raise AssertionError(f"unexpected tag: {tag}")

    if not ret:
        raise AssertionError(f"no interpreters found for {tags}")
    else:
        return tuple(sorted(ret))


def _top_import(whl: str) -> str:
    with zipfile.ZipFile(whl) as zipf:
        dist_info_names = {
            os.path.basename(name): name
            for name in zipf.namelist()
            if DIST_INFO_RE.match(name)
        }
        if "top_level.txt" in dist_info_names:
            with zipf.open(dist_info_names["top_level.txt"]) as f:
                return ",".join(f.read().decode().splitlines())
        elif "RECORD" in dist_info_names:
            with zipf.open(dist_info_names["RECORD"]) as f:
                pkgs = {}
                for line_b in f:
                    fname = line_b.decode().split(",")[0]
                    if fname.endswith("/__init__.py"):
                        pkgs[fname.split("/")[0]] = 1
                    elif "/" not in fname and fname.endswith((".so", ".py")):
                        pkgs[fname.split(".")[0]] = 1
                return ",".join(pkgs)
        else:
            raise NotImplementedError("need top_level.txt or RECORD")


def _validate(python: str, filename: str, index_url: str) -> None:
    print(f"validating {python}: {filename}")
    with tempfile.TemporaryDirectory() as tmpdir:
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
                filename,
            )
        )

        print("=> importing")
        imports = _top_import(filename)

        subprocess.check_call((py, "-c", f"import {imports}"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-url", required=True)
    parser.add_argument("--dist", default="dist")
    args = parser.parse_args()

    for filename in sorted(os.listdir(args.dist)):
        _, _, _, wheel_tags = parse_wheel_filename(filename)
        for python in _pythons_to_check(wheel_tags):
            _validate(python, os.path.join(args.dist, filename), args.index_url)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
