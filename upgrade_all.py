from __future__ import annotations

import argparse
import configparser
import json
import subprocess
import sys
import urllib.request
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages-ini", default="packages.ini")
    args = parser.parse_args(argv)

    cfg = configparser.ConfigParser()
    assert cfg.read(args.packages_ini)
    pkgs_latest = dict(k.split("==", 1) for k in cfg.sections())

    todo = []
    for k, v in pkgs_latest.items():
        resp = urllib.request.urlopen(f"https://pypi.org/pypi/{k}/json")
        contents = json.load(resp)
        if contents["info"]["version"] != v:
            todo.append(k)

    if todo:
        print(f"upgrading {', '.join(todo)}...")
        cmd = (sys.executable, "-m", "add_pkg", "--", "-r/dev/stdin")
        subprocess.run(cmd, input="\n".join(todo).encode()).returncode
    else:
        print("up to date!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
