from __future__ import annotations

import io
import os
import shutil
import subprocess
import tarfile
import urllib.error
import urllib.request
import zipfile
from unittest import mock

import pytest
from packaging.tags import Tag
from packaging.version import Version

import build
from build import Package
from build import Wheel


@pytest.mark.parametrize("ext", sorted(build.BINARY_EXTS))
def test_all_binary_exts_start_with_dot(ext):
    assert ext.startswith(".")


def test_supported_tags_does_not_include_generic_linux():
    tags = build._supported_tags((3, 9))
    assert Tag("cp39", "cp39", "linux_x86_64") not in tags
    assert Tag("cp39", "cp39", "linux_aarch64") not in tags


def test_supported_tags_includes_purelib_tags():
    tags = build._supported_tags((3, 9))
    assert Tag("py3", "none", "any") in tags
    assert Tag("py39", "none", "any") in tags
    assert Tag("py38", "none", "any") in tags


@pytest.mark.parametrize(
    ("s", "expected"),
    (
        ("a-1-py3-none-any.whl", True),
        ("a-1-cp36-abi3-manylinux1_x86_64.whl", False),
    ),
)
def test_is_purelib(s, expected):
    assert build._is_purelib(s) is expected


def test_package_default():
    ret = Package.make("a==1", {})
    assert ret == Package(
        name="a",
        version=Version("1"),
        apt_requires=(),
        brew_requires=(),
        ignore_wheels=(),
        require_binary=False,
    )


def test_package_unexpected_keys_raises_errors():
    with pytest.raises(ValueError) as excinfo:
        Package.make("a==1", {"some": "a", "thing": "b"})

    (msg,) = excinfo.value.args
    assert msg == "unexpected attrs for a==1: ['some', 'thing']"


def test_package_parses_split_values():
    dct = {
        "apt_requires": "\npkg-config\nlibxslt1-dev",
        "brew_requires": "\npkg-config\nlibxml",
        "ignore_wheels": "\nwheel1.whl\nwheel2.whl",
        "require_binary": "true",
    }
    ret = Package.make("a==1", dct)
    assert ret == Package(
        name="a",
        version=Version("1"),
        apt_requires=("pkg-config", "libxslt1-dev"),
        brew_requires=("pkg-config", "libxml"),
        ignore_wheels=("wheel1.whl", "wheel2.whl"),
        require_binary=True,
    )


LINUX_3_8_SUPPORTED_TAGS = frozenset(
    (
        Tag("py3", "none", "any"),
        Tag("cp36", "abi3", "manylinux1_x86_64"),
        Tag("cp38", "cp38", "manylinux1_x86_64"),
    )
)


@pytest.mark.parametrize(
    "filename",
    (
        "my_pkg-1.2.3-py3-none-any.whl",
        "my_pkg-1.2.3-py2.py3-none-any.whl",
        "my_pkg-1.2.3-cp38-cp38-manylinux1_x86_64.whl",
    ),
)
def test_package_satisfied_by_matches(filename):
    package = Package.make("my-pkg==1.2.3", {})
    wheel = Wheel(filename)
    assert package.satisfied_by((wheel,), LINUX_3_8_SUPPORTED_TAGS) is wheel


@pytest.mark.parametrize(
    "filename",
    (
        "otherpkg-1.2.3-py3-none-any.whl",
        "my_pkg-0.0.0-py3-none-any.whl",
        "my_pkg-1.2.3-py2-none-any.whl",
        "my_pkg-1.2.3-py3-none-linux_x86_64.whl",
        "my_pkg-1.2.3-cp39-cp39-manylinux1_x86_64.whl",
    ),
)
def test_package_satisfied_by_does_not_match(filename):
    package = Package.make("my-pkg==1.2.3", {})
    wheels = (Wheel(filename),)
    assert package.satisfied_by(wheels, LINUX_3_8_SUPPORTED_TAGS) is None


def test_get_internal_wheels():
    contents = b"""\
{"filename": "detect_test_pollution-1.0.0-py2.py3-none-any.whl"}
{"filename": "detect_test_pollution-1.1.0-py2.py3-none-any.whl"}
{"filename": "detect_test_pollution-1.1.1-py2.py3-none-any.whl"}
"""
    bio = io.BytesIO(contents)
    with mock.patch.object(urllib.request, "urlopen", return_value=bio):
        ret = build._internal_wheels("https://example.com")

    assert ret == (
        Wheel(filename="detect_test_pollution-1.0.0-py2.py3-none-any.whl"),
        Wheel(filename="detect_test_pollution-1.1.0-py2.py3-none-any.whl"),
        Wheel(filename="detect_test_pollution-1.1.1-py2.py3-none-any.whl"),
    )


def test_brew_paths():
    out = b"""\
/opt/homebrew/opt/openssl@1.1
/opt/homebrew/opt/xz
"""
    with mock.patch.object(subprocess, "check_output", return_value=out):
        ret = build._brew_paths("openssl@1.1", "xz")
    assert ret == ["/opt/homebrew/opt/openssl@1.1", "/opt/homebrew/opt/xz"]


def test_docker_run_podman():
    with mock.patch.object(shutil, "which", return_value="/usr/bin/podman"):
        assert build._docker_run() == ("podman", "run")


def test_docker_run_docker():
    with mock.patch.object(shutil, "which", return_value=None):
        with mock.patch.object(os, "getuid", return_value=1000):
            with mock.patch.object(os, "getgid", return_value=1000):
                ret = build._docker_run()
    assert ret == ("docker", "run", "--user", "1000:1000")


def test_likely_binary_exts_zip(tmp_path):
    filename = tmp_path.joinpath("a-1.zip")
    with zipfile.ZipFile(filename, "w") as zipf:
        zipf.open("a-1/src/ext.py", "w").close()
        zipf.open("a-1/src/_ext.c", "w").close()
        zipf.open("a-1/src/_ext.pyx", "w").close()

    assert build._likely_binary_exts(str(filename)) == {".c", ".pyx"}


def test_likely_binary_exts_tgz(tmp_path):
    filename = tmp_path.joinpath("a-1.tar.gz")
    with tarfile.open(filename, "w:gz") as tarf:
        tarf.addfile(tarfile.TarInfo("a-1/src/ext.py"))
        tarf.addfile(tarfile.TarInfo("a-1/src/_ext.c"))

    assert build._likely_binary_exts(str(filename)) == {".c"}


def test_likely_binary_exts_ignores_test_files(tmp_path):
    filename = tmp_path.joinpath("a-1.tar.gz")
    with tarfile.open(filename, "w:gz") as tarf:
        tarf.addfile(tarfile.TarInfo("a-1/test/_ext.pyd"))
        tarf.addfile(tarfile.TarInfo("a-1/tests/_ext.c"))

    assert build._likely_binary_exts(str(filename)) == set()
