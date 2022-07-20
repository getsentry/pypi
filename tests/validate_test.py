from __future__ import annotations

import pytest
from packaging.tags import parse_tag

import validate


def test_pythons_to_check_no_pythons_raises_error():
    with pytest.raises(AssertionError) as excinfo:
        validate._pythons_to_check(frozenset())
    (msg,) = excinfo.value.args
    assert msg == "no interpreters found for frozenset()"


def test_pythons_to_check_py3_gives_all():
    ret = validate._pythons_to_check(parse_tag("py3-none-any"))
    assert ret == ("python3.10", "python3.8", "python3.9")


def test_pythons_to_check_specific_cpython_tag():
    tag = "cp38-cp38-manylinux1_aarch64.whl"
    ret = validate._pythons_to_check(parse_tag(tag))
    assert ret == ("python3.8",)
