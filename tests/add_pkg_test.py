from __future__ import annotations

import subprocess
from unittest import mock

import pytest

import add_pkg


@pytest.fixture
def pretend_uv():
    resolved: list[str] = []

    def check_output(*args, **kwargs):
        return "".join(f"{line}\n" for line in resolved).encode()

    with mock.patch.object(subprocess, "check_output", side_effect=check_output):
        yield resolved


def test_new_pkg(pretend_uv, tmp_path, capsys):
    pretend_uv.append("a==1")

    packages_ini = tmp_path.joinpath("packages.ini")
    packages_ini.write_text("[b==1]\n")

    assert add_pkg.main(("a", f"--packages-ini={packages_ini}")) == 0

    assert packages_ini.read_text() == "[a==1]\n\n[b==1]\n"

    out, _ = capsys.readouterr()
    assert out == "resolving a...\na==1: adding...\n"


def test_new_pkg_multiple_packages(pretend_uv, tmp_path, capsys):
    pretend_uv.append("a==1")
    pretend_uv.append("c==2")

    packages_ini = tmp_path.joinpath("packages.ini")
    packages_ini.write_text("[b==1]\n")

    assert add_pkg.main(("a", "c", f"--packages-ini={packages_ini}")) == 0

    assert packages_ini.read_text() == "[a==1]\n\n[b==1]\n\n[c==2]\n"

    out, _ = capsys.readouterr()
    assert out == "resolving a c...\na==1: adding...\nc==2: adding...\n"


def test_pkg_already_present(pretend_uv, tmp_path, capsys):
    pretend_uv.append("a==1")

    packages_ini = tmp_path.joinpath("packages.ini")
    packages_ini.write_text("[a==1]\n")

    assert add_pkg.main(("a", f"--packages-ini={packages_ini}")) == 0

    assert packages_ini.read_text() == "[a==1]\n"

    out, _ = capsys.readouterr()
    assert out == "resolving a...\na==1: already present!\n"


def test_pkg_copied_from_previous_version(pretend_uv, tmp_path, capsys):
    pretend_uv.append("a==2")

    packages_ini = tmp_path.joinpath("packages.ini")
    packages_ini.write_text("[a==1]\napt_packages = zlib1g-dev\n")

    assert add_pkg.main(("a", f"--packages-ini={packages_ini}")) == 0

    assert packages_ini.read_text() == (
        "[a==1]\napt_packages = zlib1g-dev\n[a==2]\napt_packages = zlib1g-dev\n"
    )

    out, _ = capsys.readouterr()
    assert out == "resolving a...\na==2: adding...\n"


def test_skip_resolve(tmp_path, capsys):
    packages_ini = tmp_path.joinpath("packages.ini")
    packages_ini.write_text("[a==1]\n")

    # an attempt to resolve should raise!
    with mock.patch.object(subprocess, "check_output", side_effect=AssertionError):
        ret = add_pkg.main(("a==2", "--skip-resolve", f"--packages-ini={packages_ini}"))
        assert ret == 0

    assert packages_ini.read_text() == "[a==1]\n[a==2]\n"


def test_error_with_skip_resolve_an_not_pinned(capsys):
    with pytest.raises(SystemExit) as excinfo:
        add_pkg.main(("wat", "--skip-resolve"))
    (msg,) = excinfo.value.args
    assert msg == "dep must be name==version: 'wat'"
