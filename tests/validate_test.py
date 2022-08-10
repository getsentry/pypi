from __future__ import annotations

import subprocess
import zipfile
from unittest import mock

import pytest
from packaging.tags import parse_tag

import validate


def test_info_nothing_supplied():
    info = validate.Info.from_dct({})
    expected = validate.Info(
        validate_extras=None,
        validate_incorrect_missing_deps=(),
    )
    assert info == expected


def test_info_all_supplied():
    info = validate.Info.from_dct(
        {
            "validate_extras": "d",
            "validate_incorrect_missing_deps": "six",
        }
    )
    expected = validate.Info(
        validate_extras="d",
        validate_incorrect_missing_deps=("six",),
    )
    assert info == expected


def test_pythons_to_check_no_pythons_raises_error():
    with pytest.raises(AssertionError) as excinfo:
        validate._pythons_to_check(frozenset())
    (msg,) = excinfo.value.args
    assert msg == "no interpreters found for frozenset()"


def test_pythons_to_check_py2_ignored():
    ret = validate._pythons_to_check(parse_tag("py2.py3-none-any"))
    assert ret == ("python3.10", "python3.8", "python3.9")


def test_pythons_to_check_py3_gives_all():
    ret = validate._pythons_to_check(parse_tag("py3-none-any"))
    assert ret == ("python3.10", "python3.8", "python3.9")


def test_pythons_to_check_abi3():
    tag = "cp37-abi3-manylinux1_x86_64"
    ret = validate._pythons_to_check(parse_tag(tag))
    assert ret == ("python3.10", "python3.8", "python3.9")


def test_pythons_to_check_minimum_abi3():
    tag = "cp39-abi3-manylinux1_x86_64"
    ret = validate._pythons_to_check(parse_tag(tag))
    assert ret == ("python3.10", "python3.9")


def test_pythons_to_check_specific_cpython_tag():
    tag = "cp38-cp38-manylinux1_aarch64.whl"
    ret = validate._pythons_to_check(parse_tag(tag))
    assert ret == ("python3.8",)


def test_top_imports_top_level_txt(tmp_path):
    whl = tmp_path.joinpath("cffi.whl")
    with zipfile.ZipFile(whl, "w") as zipf:
        with zipf.open("cffi-1.15.1.dist-info/top_level.txt", "w") as f:
            f.write(b"_cffi_backend\ncffi\n")

    assert validate._top_imports(str(whl)) == ["_cffi_backend", "cffi"]


def test_top_imports_record(tmp_path):
    whl = tmp_path.joinpath("distlib.whl")
    with zipfile.ZipFile(whl, "w") as zipf:
        with zipf.open("distlib-0.3.4.dist-info/RECORD", "w") as f:
            f.write(
                # simplified from the actual contents
                b"distlib-0.3.4.dist-info/RECORD,,\n"
                b"distlib/__init__.py,sha256=y-rKDBB99QJ3N1PJGAXQo89ou615aAeBjV2brBxKgM8,581\n"
                b"distlib/__pycache__/index.cpython-38.pyc,,\n"
                b"distlib/compat.py,sha256=tfoMrj6tujk7G4UC2owL6ArgDuCKabgBxuJRGZSmpko,41259\n"
                # not actually present but to demonstrate behaviour
                b"distlib/subpkg/__init__.py,,\n"
                b"_distlib_backend.cpython-38-x86_64-linux-gnu.so,,\n"
                b"distlib_top.py,,\n"
            )

    expected = ["distlib", "_distlib_backend", "distlib_top"]
    assert validate._top_imports(str(whl)) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    (
        ("a-1-py3-none-any.whl", set()),
        ("a-1-py3-none-manylinux2014_x86_64.whl", {"x86_64"}),
        ("a-1-py3-none-manylinux2014_aarch64.whl", {"aarch64"}),
        ("a-1-py3-none-macosx_11_0_intel.whl", {"x86_64"}),
        ("a-1-py3-none-macosx_11_0_arm64.whl", {"arm64"}),
        ("a-1-py3-none-macosx_11_0_universal2.whl", {"x86_64", "arm64"}),
        (
            "a-1-py3-none-macosx_11_0_x86_64.macosx_11_0_arm64.whl",
            {"x86_64", "arm64"},
        ),
    ),
)
def test_expected_archs_for_wheel(filename, expected):
    assert validate._expected_archs_for_wheel(filename) == expected


def test_get_archs_darwin_single_arch():
    out = b"""\
./simplejson/_speedups.cpython-38-darwin.so:
Mach header
      magic  cputype cpusubtype  caps    filetype ncmds sizeofcmds      flags
MH_MAGIC_64    ARM64        ALL  0x00      BUNDLE    14       1416   NOUNDEFS DYLDLINK TWOLEVEL
"""
    with mock.patch.object(subprocess, "check_output", return_value=out):
        assert validate._get_archs_darwin("somefile.so") == {"arm64"}


def test_get_archs_darwin_multi_arch():
    out = b"""\
./google_crc32c/_crc32c.cpython-38-darwin.so (architecture x86_64):
Mach header
      magic  cputype cpusubtype  caps    filetype ncmds sizeofcmds      flags
MH_MAGIC_64   X86_64        ALL  0x00      BUNDLE    14       1312   NOUNDEFS DYLDLINK TWOLEVEL
./google_crc32c/_crc32c.cpython-38-darwin.so (architecture arm64):
Mach header
      magic  cputype cpusubtype  caps    filetype ncmds sizeofcmds      flags
MH_MAGIC_64    ARM64        ALL  0x00      BUNDLE    15       1320   NOUNDEFS DYLDLINK TWOLEVEL
"""
    with mock.patch.object(subprocess, "check_output", return_value=out):
        assert validate._get_archs_darwin("somefile.so") == {"arm64", "x86_64"}


def test_get_archs_linux_x86_64():
    out = b"""\
venv/bin/uwsgi: ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, BuildID[sha1]=be830dfcdbb9a7a90cf0687ba4cecde8951db1e0, for GNU/Linux 3.2.0, with debug_info, not stripped
"""
    with mock.patch.object(subprocess, "check_output", return_value=out):
        assert validate._get_archs_linux("somefile.so") == {"x86_64"}


def test_get_archs_linux_aarch64():
    out = b"""\
simplejson/_speedups.cpython-37m-aarch64-linux-gnu.so: ELF 64-bit LSB shared object, ARM aarch64, version 1 (SYSV), dynamically linked, BuildID[sha1]=77175a0e0fc131e1ad0f84daaaaee89c5f89c5b0, with debug_info, not stripped
"""
    with mock.patch.object(subprocess, "check_output", return_value=out):
        assert validate._get_archs_linux("somefile.so") == {"aarch64"}
