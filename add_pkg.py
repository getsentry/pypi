from __future__ import annotations

import argparse
import configparser
import subprocess
import sys
from collections.abc import Sequence

from packaging.utils import canonicalize_name
from packaging.version import Version


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("deps", nargs="+")
    parser.add_argument("--packages-ini", default="packages.ini")
    parser.add_argument(
        "--skip-resolve",
        action="store_true",
        help="skip resolving dependencies, all deps must be specified as k==v",
    )
    args = parser.parse_args(argv)

    if args.skip_resolve:
        deps = []
        for dep in args.deps:
            name, _, version = dep.partition("==")
            if not version:
                raise SystemExit(f"dep must be name==version: {dep!r}")
            deps.append((name, version))
    else:
        print(f"resolving {' '.join(args.deps)}...")
        out = subprocess.check_output(
            (
                "uv",
                "pip",
                "compile",
                "--no-config",
                "--quiet",
                "--no-header",
                "--no-annotate",
                f"--python={sys.executable}",
                "--default-index=https://pypi.org/simple",
                "-",
            ),
            input="\n".join(args.deps).encode(),
        )

        deps = []
        for line in out.decode().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                name, _, version = line.partition("==")
                deps.append((canonicalize_name(name), str(Version(version))))

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
