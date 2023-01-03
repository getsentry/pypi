from __future__ import annotations

import argparse
import configparser
import os
import subprocess
import sys
import tempfile
from typing import Sequence

from packaging.utils import parse_wheel_filename


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("deps", nargs="+")
    parser.add_argument("--packages-ini", default="packages.ini")
    args = parser.parse_args(argv)

    print(f"resolving {' '.join(args.deps)}...")
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.check_call(
            (
                sys.executable,
                "-mpip",
                "wheel",
                "--quiet",
                "--no-cache-dir",
                f"--wheel-dir={tmpdir}",
                *args.deps,
            )
        )

        deps = []
        for filename in sorted(os.listdir(tmpdir)):
            name, version, _, _ = parse_wheel_filename(filename)
            deps.append((name, str(version)))

    cfg = configparser.ConfigParser()
    assert cfg.read(args.packages_ini)
    pkgs_latest = dict(k.split("==", 1) for k in cfg.sections())

    for name, version in deps:
        key = f"{name}=={version}"
        if key in cfg:
            print(f"{key}: already present!")
        else:
            print(f"{key}: adding...")

        # find the best candidate to copy config from
        if name in pkgs_latest:
            copy_from = dict(cfg[f"{name}=={pkgs_latest[name]}"])
        else:
            copy_from = {}

        cfg[key] = copy_from

    with open(args.packages_ini, "w") as f:
        cfg.write(f)

    subprocess.call((sys.executable, "-m", "format_ini", args.packages_ini))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
