from __future__ import annotations

import zipfile

import pytest
from packaging.specifiers import SpecifierSet
from packaging.tags import parse_tag

import validate


def test_info_nothing_supplied():
    info = validate.Info.from_dct({})
    expected = validate.Info(
        validate_extras=None,
        validate_incorrect_missing_deps=(),
        validate_skip_imports=(),
    )
    assert info == expected


def test_info_all_supplied():
    info = validate.Info.from_dct(
        {
            "validate_extras": "d",
            "validate_incorrect_missing_deps": "six",
            "validate_skip_imports": "uwsgidecorators",
        }
    )
    expected = validate.Info(
        validate_extras="d",
        validate_incorrect_missing_deps=("six",),
        validate_skip_imports=("uwsgidecorators",),
    )
    assert info == expected


def test_pythons_to_check_no_pythons_raises_error():
    with pytest.raises(AssertionError) as excinfo:
        validate._pythons_to_check(frozenset())
    (msg,) = excinfo.value.args
    assert msg == "no interpreters found for frozenset()"


def test_pythons_to_check_py2_ignored():
    ret = validate._pythons_to_check(parse_tag("py2.py3-none-any"))
    assert ret == ("python3.11", "python3.12", "python3.13")


def test_pythons_to_check_py3_gives_all():
    ret = validate._pythons_to_check(parse_tag("py3-none-any"))
    assert ret == ("python3.11", "python3.12", "python3.13")


def test_pythons_to_check_abi3():
    tag = "cp37-abi3-manylinux1_x86_64"
    ret = validate._pythons_to_check(parse_tag(tag))
    assert ret == ("python3.11", "python3.12", "python3.13")


def test_pythons_to_check_minimum_abi3():
    tag = "cp312-abi3-manylinux1_x86_64"
    ret = validate._pythons_to_check(parse_tag(tag))
    assert ret == ("python3.12", "python3.13")


def test_pythons_to_check_specific_cpython_tag():
    tag = "cp311-cp311-manylinux1_aarch64.whl"
    ret = validate._pythons_to_check(parse_tag(tag))
    assert ret == ("python3.11",)


def test_pythons_to_check_multi_platform_with_musllinux():
    """Test that wheels with both compatible and incompatible platform tags are accepted."""
    # Simulates a wheel like: py3-none-any.musllinux_1_2_x86_64
    # The py3-none-any tag is always compatible, while musllinux might not be on all systems
    tags = parse_tag("py3-none-any") | parse_tag("py3-none-musllinux_1_2_x86_64")
    ret = validate._pythons_to_check(tags)
    # Should succeed because at least one tag (py3-none-any) is compatible
    assert ret == ("python3.11", "python3.12", "python3.13")


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


def test_pythons_to_check_with_python_versions_constraint():
    tag = parse_tag("py2.py3-none-any")
    constraint = SpecifierSet(">=3.12")
    ret = validate._pythons_to_check(tag, constraint)
    assert ret == ("python3.12", "python3.13")
