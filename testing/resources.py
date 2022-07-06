from __future__ import annotations

import os.path

HERE = os.path.dirname(os.path.abspath(__file__))


def resource(*path: str) -> bytes:
    with open(os.path.join(HERE, "fixtures", *path), "rb") as f:
        return f.read()
