from __future__ import annotations

import zipfile

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
