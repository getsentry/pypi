from __future__ import annotations

import subprocess
import tempfile
from unittest import mock

import pytest

import add_pkg


@pytest.fixture
def pretend_pip(tmp_path):
    tmp = tmp_path.joinpath("tmp_path")
    tmp.mkdir()

    with mock.patch.object(tempfile, "TemporaryDirectory") as tmpdir_mck:
        tmpdir_mck.return_value.__enter__.return_value = tmp
        with mock.patch.object(subprocess, "check_call"):
            yield tmp


def test_new_pkg(pretend_pip, tmp_path, capsys):
    pretend_pip.joinpath("a-1-py3-none-any.whl").touch()

    packages_ini = tmp_path.joinpath("packages.ini")
    packages_ini.write_text("[b==1]\n")

    assert add_pkg.main(("a", f"--packages-ini={packages_ini}")) == 0

    assert packages_ini.read_text() == "[a==1]\n\n[b==1]\n"

    out, _ = capsys.readouterr()
    assert out == "resolving a...\na==1: adding...\n"


def test_pkg_already_present(pretend_pip, tmp_path, capsys):
    pretend_pip.joinpath("a-1-py3-none-any.whl").touch()

    packages_ini = tmp_path.joinpath("packages.ini")
    packages_ini.write_text("[a==1]\n")

    assert add_pkg.main(("a", f"--packages-ini={packages_ini}")) == 0

    assert packages_ini.read_text() == "[a==1]\n"

    out, _ = capsys.readouterr()
    assert out == "resolving a...\na==1: already present!\n"


def test_pkg_copied_from_previous_version(pretend_pip, tmp_path, capsys):
    pretend_pip.joinpath("a-2-py3-none-any.whl").touch()

    packages_ini = tmp_path.joinpath("packages.ini")
    packages_ini.write_text("[a==1]\napt_packages = zlib1g-dev\n")

    assert add_pkg.main(("a", f"--packages-ini={packages_ini}")) == 0

    assert packages_ini.read_text() == (
        "[a==1]\n"
        "apt_packages = zlib1g-dev\n"
        "[a==2]\n"
        "apt_packages = zlib1g-dev\n"
    )

    out, _ = capsys.readouterr()
    assert out == "resolving a...\na==2: adding...\n"
