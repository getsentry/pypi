from __future__ import annotations

import argparse
import configparser
import io
import re
import sys
from typing import Sequence

from packaging.utils import canonicalize_name
from packaging.version import Version

_PKG_RE = re.compile("^.*==.*$")
_TRAILING_WS = re.compile(" +\n")


def _section_sort_key(s: str) -> tuple[str, Version]:
    pkg_s, version = s.split("==", 1)
    return canonicalize_name(pkg_s), Version(version)


def _format_value(v: str) -> str:
    v = v.strip()
    v_split = v.split()
    if len(v_split) > 1:
        items_s = "\n".join(sorted(v_split))
        return f"\n{items_s}"
    else:
        return v


def _format_file(filename: str) -> int:
    with open(filename, encoding="UTF-8", newline="") as f:
        contents = f.read()

    orig = configparser.RawConfigParser(strict=False)
    orig.read_string(contents)

    errors = []
    # validate that each of the sections are named properly
    for section in orig.sections():
        if not _PKG_RE.fullmatch(section):
            errors.append(f"section [{section}] must be `[{section}==...]`")

    if errors:
        for error in errors:
            print(f"{filename}: {error}", file=sys.stderr)
        return 1

    cfg = configparser.RawConfigParser()
    for section in sorted(orig.sections(), key=_section_sort_key):
        pkg_s, version = _section_sort_key(section)
        newsection = f"{pkg_s}=={version}"
        cfg.add_section(newsection)

        for k, v in sorted(orig[section].items()):
            cfg[newsection][k] = _format_value(v)

    cfg_sio = io.StringIO()
    cfg.write(cfg_sio)
    cfg_sio.seek(0)

    prev_pkg = ""
    lines: list[str] = []
    for line in cfg_sio:
        line = line.replace("\t", " " * 4)
        line = _TRAILING_WS.sub("\n", line)

        if line.startswith("[") and line.endswith("]\n"):
            pkg, _ = line.lstrip("[").split("==", 1)
            # if the previous package was the same, remove the blank lines between
            if pkg == prev_pkg:
                while lines and not lines[-1].strip():
                    lines.pop()
            prev_pkg = pkg
        lines.append(line)

    # remove extra blank line that configparser adds
    while lines and not lines[-1].strip():
        lines.pop()

    newcontents = "".join(lines)
    if contents != newcontents:
        with open(filename, "w", encoding="UTF-8", newline="") as f:
            f.write(newcontents)
        print(f"{filename}: formatted", file=sys.stderr)
        return 1
    else:
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*")
    args = parser.parse_args(argv)

    ret = 0
    for filename in args.filenames:
        ret |= _format_file(filename)

    return ret


if __name__ == "__main__":
    raise SystemExit(main())
