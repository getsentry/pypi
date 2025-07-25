from __future__ import annotations

import io
import json
import os.path
import re
import urllib.request
import zipfile
from unittest import mock

import pytest
import re_assert

import make_index


def make_wheel(path, metadata):
    name, v, *_ = os.path.basename(path).split("-")
    with zipfile.ZipFile(path, "w") as zipf:
        with zipf.open(f"{name}-{v}.dist-info/METADATA", "w") as f:
            f.write(f"Name: {name}\n".encode())
            f.write(f"Version: {v}\n".encode())
            for k, v in metadata:
                f.write(f"{k}: {v}\n".encode())


def test_make_info_empty_wheel_metadata(tmp_path):
    filename = str(tmp_path.joinpath("a-1-py3-none-any.whl"))
    make_wheel(filename, ())

    ret = make_index._make_info(filename)
    assert ret == {
        "filename": "a-1-py3-none-any.whl",
        "hash": "sha256=64f7f4664408d711c17ad28c1d3ba7dd155501e67c8632fafc8a525ba3ebc527",
        "core_metadata": "sha256=d4528dc2d072c0e6d65addae8b5700fd29253b9eb9a9214aba539447d6f29fae",
        "upload_timestamp": mock.ANY,
        "uploaded_by": re_assert.Matches(r"^git@[a-f0-9]{7}"),
    }


def test_make_info_full_wheel_metadata(tmp_path):
    filename = str(tmp_path.joinpath("a-1-py3-none-any.whl"))
    make_wheel(
        filename,
        (
            ("Requires-Python", ">= 3.7, != 3.7.0"),
            ("Requires-Dist", "cfgv (>=1)"),
            ("Requires-Dist", "jsonschema"),
            ("Requires-Dist", "packaging (==21.3) ; extra = 'p'"),
        ),
    )

    ret = make_index._make_info(filename)
    assert ret == {
        "filename": "a-1-py3-none-any.whl",
        "hash": "sha256=4e6da08b56614db68d4139aca043731c1fed51496ef168b5be2c67737dfe9f9a",
        "requires_dist": [
            "cfgv (>=1)",
            "jsonschema",
            "packaging (==21.3) ; extra = 'p'",
        ],
        "core_metadata": "sha256=a015186125a83e6667547b156f8c6813e72fbab48c4ae635ac3c3a5f1d86aa9f",
        "requires_python": ">= 3.7, != 3.7.0",
        "upload_timestamp": mock.ANY,
        "uploaded_by": re_assert.Matches(r"^git@[a-f0-9]{7}"),
    }


def test_main_new_package(tmp_path):
    dist = tmp_path.joinpath("dist")
    dist.mkdir()
    make_wheel(dist.joinpath("a-1-py3-none-any.whl"), ())
    dest = tmp_path.joinpath("dest")

    bio = io.BytesIO(b"")
    with mock.patch.object(urllib.request, "urlopen", return_value=bio):
        assert not make_index.main(
            (
                f"--dist={dist}",
                f"--dest={dest}",
                "--pypi-url=http://example.com",
            )
        )

    # just some smoke tests about the output
    assert dest.joinpath("packages.json").exists()
    assert dest.joinpath("wheels/a-1-py3-none-any.whl").exists()


def test_main_core_metadata(tmp_path):
    dist = tmp_path.joinpath("dist")
    dist.mkdir()
    make_wheel(dist.joinpath("a-1-py3-none-any.whl"), ())
    dest = tmp_path.joinpath("dest")

    bio = io.BytesIO(b"")
    with mock.patch.object(urllib.request, "urlopen", return_value=bio):
        assert not make_index.main(
            (
                f"--dist={dist}",
                f"--dest={dest}",
                "--pypi-url=http://example.com",
            )
        )

    wheel_sha = "64f7f4664408d711c17ad28c1d3ba7dd155501e67c8632fafc8a525ba3ebc527"
    metadata_sha = "d4528dc2d072c0e6d65addae8b5700fd29253b9eb9a9214aba539447d6f29fae"

    with open(dest.joinpath("simple/a/index.html")) as f:
        index_html = re.sub(r"\s+", " ", f.read())
        assert (
            f'<a href="http://example.com/wheels/a-1-py3-none-any.whl#sha256={wheel_sha}" data-core-metadata="sha256={metadata_sha}" >a-1-py3-none-any.whl</a>'
            in index_html
        )

    with open(dest.joinpath("wheels/a-1-py3-none-any.whl.metadata")) as f:
        assert f.read() == "Name: a\nVersion: 1\n"


def test_main_multiple_provide_same_package_first_wins(tmp_path):
    dist = tmp_path.joinpath("dist")
    adir = dist.joinpath("a")
    adir.mkdir(parents=True)
    make_wheel(adir.joinpath("a-1-py3-none-any.whl"), (("Requires-Python", ">=3"),))
    bdir = dist.joinpath("b")
    bdir.mkdir(parents=True)
    make_wheel(bdir.joinpath("a-1-py3-none-any.whl"), ())
    dest = tmp_path.joinpath("dest")

    bio = io.BytesIO(b"")
    with mock.patch.object(urllib.request, "urlopen", return_value=bio):
        assert not make_index.main(
            (
                f"--dist={dist}",
                f"--dest={dest}",
                "--pypi-url=http://example.com",
            )
        )

    # make sure we used the first wheel
    with open(dest.joinpath("packages.json")) as f:
        contents = json.load(f)

    assert contents["requires_python"] == ">=3"


@pytest.mark.skip
def test_main_previous_packages_exist(tmp_path):
    dist = tmp_path.joinpath("dist")
    dist.mkdir()
    make_wheel(dist.joinpath("b-1-py3-none-any.whl"), ())
    dest = tmp_path.joinpath("dest")

    bio = io.BytesIO(b'{"filename": "a-1-py3-none-any.whl"}')
    with mock.patch.object(urllib.request, "urlopen", return_value=bio):
        assert not make_index.main(
            (
                f"--dist={dist}",
                f"--dest={dest}",
                "--pypi-url=http://example.com",
            )
        )

    # incremental: build b index but not existing a
    assert dest.joinpath("simple/b/index.html").exists()
    assert not dest.joinpath("simple/a/index.html").exists()

    # but the overall package list should have both
    with open(dest.joinpath("packages.json")) as f:
        filenames = [json.loads(line)["filename"] for line in f]

    assert filenames == ["a-1-py3-none-any.whl", "b-1-py3-none-any.whl"]
