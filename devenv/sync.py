from __future__ import annotations

from devenv import constants
from devenv.lib import config
from devenv.lib import proc
from devenv.lib import uv


def main(context: dict[str, str]) -> int:
    reporoot = context["reporoot"]
    cfg = config.get_repo(reporoot)

    uv.install(
        cfg["uv"]["version"],
        cfg["uv"][constants.SYSTEM_MACHINE],
        cfg["uv"][f"{constants.SYSTEM_MACHINE}_sha256"],
        reporoot,
    )

    print("syncing .venv ...")
    proc.run(("uv", "sync", "--frozen", "--quiet"))

    print("installing pre-commit hooks ...")
    proc.run((f"{reporoot}/.venv/bin/pre-commit", "install", "--install-hooks"))

    return 0
