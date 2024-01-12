from __future__ import annotations

import argparse
import email
import functools
import hashlib
import itertools
import json
import os.path
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Sequence
from typing import Any


@functools.lru_cache(maxsize=1)
def _commit_info() -> tuple[str, int]:
    cmd = ("git", "show", "--no-patch", "--format=%h %ct")
    h, t = subprocess.check_output(cmd).decode().split()
    return h, int(t)


def _make_info(filename: str) -> dict[str, Any]:
    h, t = _commit_info()

    with open(filename, "rb") as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()

    with zipfile.ZipFile(filename) as zipf:
        (metadata,) = (
            name
            for name in zipf.namelist()
            if name.endswith(".dist-info/METADATA") and name.count("/") == 1
        )
        with zipf.open(metadata) as f:
            info = email.message_from_binary_file(f)

    dist_info = {
        "requires_dist": info.get_all("requires-dist"),
        "requires_python": info.get("requires-python"),
    }

    return {
        "filename": os.path.basename(filename),
        "hash": f"sha256={sha256}",
        "upload_timestamp": t,
        "uploaded_by": f"git@{h}",
        **{k: v for k, v in dist_info.items() if v},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default="dist")
    parser.add_argument("--pypi-url", required=True)
    parser.add_argument("--dest", required=True)
    args = parser.parse_args(argv)

    url = urllib.parse.urljoin(args.pypi_url, "packages.json")
    packages = [json.loads(line) for line in urllib.request.urlopen(url)]
    on_pypi = {package["filename"] for package in packages}

    shutil.rmtree(args.dest, ignore_errors=True)
    os.makedirs(args.dest, exist_ok=True)

    wheels_dir = os.path.join(args.dest, "wheels")
    os.makedirs(wheels_dir)

    new_packages = []
    # we may build purepy on different platforms / architectures
    # let the first one win
    seen = set()

    # walk is unordered, so we'll sort to ensure repeatability
    for filename in sorted(
        os.path.join(root, filename)
        for root, _, filenames in os.walk(args.dist)
        for filename in filenames
    ):
        basename = os.path.basename(filename)
        if basename in on_pypi:
            raise AssertionError(f"{basename}: already on pypi?")
        elif basename in seen:
            continue

        seen.add(basename)
        new_packages.append(_make_info(filename))
        shutil.copy(filename, wheels_dir)

    with tempfile.TemporaryDirectory() as tmpdir:
        prev_json = os.path.join(tmpdir, "previous.json")
        with open(prev_json, "w") as f:
            for package in packages:
                f.write(f"{json.dumps(package)}\n")

        packages_json = os.path.join(tmpdir, "packages.json")
        with open(packages_json, "w") as f:
            for package in itertools.chain(packages, new_packages):
                f.write(f"{json.dumps(package)}\n")

        subprocess.check_call(
            (
                sys.executable,
                "-mdumb_pypi.main",
                f"--previous-package-list-json={prev_json}",
                f"--package-list-json={packages_json}",
                f"--output-dir={args.dest}",
                f'--packages-url={urllib.parse.urljoin(args.pypi_url, "wheels")}',
                "--title=sentry pypi",
                "--logo=https://avatars.githubusercontent.com/u/1396951?s=24",
                "--logo-width=36",
            )
        )

    # for now we don't utilize the json api
    shutil.rmtree(os.path.join(args.dest, "pypi"), ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
