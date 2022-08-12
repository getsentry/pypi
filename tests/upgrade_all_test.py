from __future__ import annotations

import io
import subprocess
import urllib.request
from unittest import mock

import pytest

import upgrade_all


@pytest.fixture(autouse=True)
def latest_version_2_x():
    bio = io.BytesIO(b'{"info": {"version": "2.0"}}')
    with mock.patch.object(urllib.request, "urlopen", return_value=bio):
        yield


def test_upgrade_all_up_to_date(tmp_path, capsys):
    packages_ini = tmp_path.joinpath("packages.ini")
    packages_ini.write_text("[a==2.0]\n")

    assert upgrade_all.main((f"--packages-ini={packages_ini}",)) == 0

    out, _ = capsys.readouterr()
    assert out == "up to date!\n"


def test_upgrade_needs_to_upgrade_things(tmp_path, capsys):
    packages_ini = tmp_path.joinpath("packages.ini")
    packages_ini.write_text("[a==1.0]\n")

    ret: subprocess.CompletedProcess[None]
    ret = subprocess.CompletedProcess(("add_pkg",), returncode=0)
    with mock.patch.object(subprocess, "run", return_value=ret):
        assert upgrade_all.main((f"--packages-ini={packages_ini}",)) == 0

    out, _ = capsys.readouterr()
    assert out == "upgrading a...\n"
