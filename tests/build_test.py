from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import urllib.error
import urllib.request
import zipfile
from unittest import mock

import pytest
from packaging.specifiers import SpecifierSet
from packaging.tags import Tag
from packaging.version import Version

import build
from build import Package


@pytest.mark.parametrize(
    ("s", "matched"),
    (
        ("a-1.data/scripts/uwsgi", True),
        ("a-1.data/scripts/run_thing.py", False),
        ("a-1.data/purelib/unrelated", False),
        ("scripts/unrelated", False),
    ),
)
def test_data_scripts_re(s, matched):
    assert bool(build.DATA_SCRIPTS.fullmatch(s)) is matched


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


def test_package_default():
    ret = Package.make("a==1", {})
    assert ret == Package(
        name="a",
        version=Version("1"),
        apt_requires=(),
        brew_requires=(),
        custom_prebuild=(),
        likely_binary_ignore=(),
        python_versions=SpecifierSet(),
        config_settings=(),
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
        "custom_prebuild": "prebuild/crc32c deadbeef",
    }
    ret = Package.make("a==1", dct)
    assert ret == Package(
        name="a",
        version=Version("1"),
        apt_requires=("pkg-config", "libxslt1-dev"),
        brew_requires=("pkg-config", "libxml"),
        custom_prebuild=("prebuild/crc32c", "deadbeef"),
        likely_binary_ignore=(),
        python_versions=SpecifierSet(),
        config_settings=(),
        require_binary=False,
    )


def test_package_parses_config_settings_and_require_binary():
    dct = {
        "config_settings": "--build-option=--cythonize",
        "require_binary": "true",
    }
    ret = Package.make("a==1", dct)
    assert ret.config_settings == ("--build-option=--cythonize",)
    assert ret.require_binary is True


def test_package_require_binary_must_be_a_bool():
    with pytest.raises(ValueError) as excinfo:
        Package.make("a==1", {"require_binary": "yes"})

    (msg,) = excinfo.value.args
    assert msg == "a==1: require_binary must be true or false"


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
    wheels: dict[str, list[tuple[Version, frozenset[Tag]]]] = {}
    build._add_wheel(wheels, filename)
    assert package.satisfied_by(wheels, LINUX_3_8_SUPPORTED_TAGS) is True


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
    wheels: dict[str, list[tuple[Version, frozenset[Tag]]]] = {}
    build._add_wheel(wheels, filename)
    assert package.satisfied_by(wheels, LINUX_3_8_SUPPORTED_TAGS) is False


def test_package_satisfied_by_require_binary_ignores_purelib():
    package = Package.make("my-pkg==1.2.3", {"require_binary": "true"})
    wheels: dict[str, list[tuple[Version, frozenset[Tag]]]] = {}
    build._add_wheel(wheels, "my_pkg-1.2.3-py3-none-any.whl")
    assert package.satisfied_by(wheels, LINUX_3_8_SUPPORTED_TAGS) is False
    build._add_wheel(wheels, "my_pkg-1.2.3-cp38-cp38-manylinux1_x86_64.whl")
    assert package.satisfied_by(wheels, LINUX_3_8_SUPPORTED_TAGS) is True


def test_get_internal_wheels():
    contents = b"""\
{"filename": "detect_test_pollution-1.0.0-py3-none-any.whl"}
{"filename": "detect_test_pollution-1.1.0-py3-none-any.whl"}
{"filename": "detect_test_pollution-1.1.1-py3-none-any.whl"}
"""
    bio = io.BytesIO(contents)
    with mock.patch.object(urllib.request, "urlopen", return_value=bio):
        ret = build._internal_wheels("https://example.com")

    assert ret == {
        "detect-test-pollution": [
            (Version("1.0.0"), frozenset((Tag("py3", "none", "any"),))),
            (Version("1.1.0"), frozenset((Tag("py3", "none", "any"),))),
            (Version("1.1.1"), frozenset((Tag("py3", "none", "any"),))),
        ],
    }


def _pypi_json(requires_python, filenames):
    return io.BytesIO(
        json.dumps(
            {
                "info": {"requires_python": requires_python},
                "urls": [
                    {
                        "filename": f,
                        "url": f"https://files.example.com/{f}",
                        "digests": {"sha256": "h"},
                        "packagetype": "sdist"
                        if f.endswith(".tar.gz")
                        else "bdist_wheel",
                    }
                    for f in filenames
                ],
            }
        ).encode()
    )


def test_public_release():
    resp = _pypi_json(">=3.13", ("a-1-py3-none-any.whl", "a-1.tar.gz"))
    with mock.patch.object(urllib.request, "urlopen", return_value=resp):
        release = build._public_release(Package.make("a==1", {}))

    assert release == build.Release(
        requires_python=SpecifierSet(">=3.13"),
        sdist=build.ReleaseFile(
            "a-1.tar.gz", "https://files.example.com/a-1.tar.gz", "h"
        ),
        wheels=(
            build.ReleaseFile(
                "a-1-py3-none-any.whl",
                "https://files.example.com/a-1-py3-none-any.whl",
                "h",
            ),
        ),
    )


def test_public_release_invalid_requires_python_is_ignored():
    resp = _pypi_json(">=3.6.*", ("a-1-py3-none-any.whl",))
    with mock.patch.object(urllib.request, "urlopen", return_value=resp):
        release = build._public_release(Package.make("a==1", {}))

    assert release.requires_python == SpecifierSet()
    assert release.sdist is None


def test_public_release_retries_until_visible():
    not_found = urllib.error.HTTPError("u", 404, "Not Found", {}, None)  # type: ignore[arg-type]
    resp = _pypi_json(None, ("a-1.tar.gz",))
    with (
        mock.patch.object(
            urllib.request, "urlopen", side_effect=[not_found, not_found, resp]
        ),
        mock.patch.object(build.time, "sleep") as sleep,
    ):
        release = build._public_release(Package.make("a==1", {}))

    assert sleep.call_args_list == [mock.call(1), mock.call(2)]
    assert release.requires_python == SpecifierSet()


def test_release_supports():
    python = build.Python((3, 11), frozenset())
    release = build.Release(SpecifierSet(">=3.13"), None, ())
    with mock.patch.object(build, "_python_full_version", return_value="3.11.14"):
        assert release.supports(python) is False
    with mock.patch.object(build, "_python_full_version", return_value="3.13.12"):
        assert release.supports(python._replace(version=(3, 13))) is True


def test_release_wheels_for_prefers_most_specific_tag():
    python = build.Python((3, 11), frozenset())
    purelib = build.ReleaseFile("a-1-py3-none-any.whl", "u", "h")
    cp311 = build.ReleaseFile("a-1-cp311-cp311-manylinux_2_17_x86_64.whl", "u", "h")
    cp313 = build.ReleaseFile("a-1-cp313-cp313-manylinux_2_17_x86_64.whl", "u", "h")
    release = build.Release(SpecifierSet(), None, (purelib, cp313, cp311))

    with mock.patch.object(
        build, "platform_tags", return_value=iter(("manylinux_2_17_x86_64",))
    ):
        assert release.wheels_for(python) == [cp311, purelib]


@pytest.mark.parametrize(("require_binary", "expected"), ((False, True), (True, False)))
def test_download_require_binary_skips_purelib(tmp_path, require_binary, expected):
    python = build.Python((3, 11), frozenset())
    purelib = build.ReleaseFile("a-1-py3-none-any.whl", "u", "h")
    release = build.Release(SpecifierSet(), None, (purelib,))

    def fake_fetch(release_file, dest):
        path = os.path.join(dest, release_file.filename)
        open(path, "wb").close()
        return path

    with (
        mock.patch.object(build, "_fetch", side_effect=fake_fetch),
        mock.patch.object(build, "_check_arch", return_value=None),
    ):
        ret = build._download(
            release, python, str(tmp_path), require_binary=require_binary
        )

    assert ret == ("a-1-py3-none-any.whl" if expected else None)
    assert (tmp_path / "a-1-py3-none-any.whl").exists() is expected


def test_fetch_verifies_sha256(tmp_path):
    contents = b"wheel contents"
    good = build.ReleaseFile(
        "a-1-py3-none-any.whl", "u", hashlib.sha256(contents).hexdigest()
    )
    with mock.patch.object(
        urllib.request, "urlopen", return_value=io.BytesIO(contents)
    ):
        ret = build._fetch(good, str(tmp_path))
    assert open(ret, "rb").read() == contents

    bad = good._replace(sha256="0" * 64)
    with mock.patch.object(
        urllib.request, "urlopen", return_value=io.BytesIO(contents)
    ):
        with pytest.raises(SystemExit) as excinfo:
            build._fetch(bad, str(tmp_path))
    assert excinfo.value.code == "a-1-py3-none-any.whl: sha256 mismatch"


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
    assert build._expected_archs_for_wheel(filename) == expected


def test_get_archs_darwin_single_arch():
    out = b"""\
./simplejson/_speedups.cpython-38-darwin.so:
Mach header
      magic  cputype cpusubtype  caps    filetype ncmds sizeofcmds      flags
MH_MAGIC_64    ARM64        ALL  0x00      BUNDLE    14       1416   NOUNDEFS DYLDLINK TWOLEVEL
"""
    with mock.patch.object(subprocess, "check_output", return_value=out):
        assert build._darwin_get_archs("somefile.so") == {"arm64"}


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
        assert build._darwin_get_archs("somefile.so") == {"arm64", "x86_64"}


def test_get_archs_linux_x86_64():
    out = b"""\
venv/bin/uwsgi: ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, BuildID[sha1]=be830dfcdbb9a7a90cf0687ba4cecde8951db1e0, for GNU/Linux 3.2.0, with debug_info, not stripped
"""
    with mock.patch.object(subprocess, "check_output", return_value=out):
        assert build._linux_get_archs("somefile.so") == {"x86_64"}


def test_get_archs_linux_aarch64():
    out = b"""\
simplejson/_speedups.cpython-37m-aarch64-linux-gnu.so: ELF 64-bit LSB shared object, ARM aarch64, version 1 (SYSV), dynamically linked, BuildID[sha1]=77175a0e0fc131e1ad0f84daaaaee89c5f89c5b0, with debug_info, not stripped
"""
    with mock.patch.object(subprocess, "check_output", return_value=out):
        assert build._linux_get_archs("somefile.so") == {"aarch64"}


def test_likely_binary_zip(tmp_path):
    filename = tmp_path.joinpath("a-1.zip")
    with zipfile.ZipFile(filename, "w") as zipf:
        zipf.open("a-1/src/ext.py", "w").close()
        zipf.open("a-1/src/_ext.c", "w").close()
        zipf.open("a-1/src/_ext.pyx", "w").close()

    reason = build._likely_binary(str(filename), ())
    assert reason == "sdist contains files with these extensions: .c, .pyx"


def test_likely_binary_tgz(tmp_path):
    filename = tmp_path.joinpath("a-1.tar.gz")
    with tarfile.open(filename, "w:gz") as tarf:
        tarf.addfile(tarfile.TarInfo("a-1/src/ext.py"))
        tarf.addfile(tarfile.TarInfo("a-1/src/_ext.c"))

    reason = build._likely_binary(str(filename), ())
    assert reason == "sdist contains files with these extensions: .c"


def test_likely_binary_cffi_zip(tmp_path):
    filename = tmp_path.joinpath("a-1.zip")
    with zipfile.ZipFile(filename, "w") as zipf:
        with zipf.open("a-1/setup.py", "w") as f:
            # similar to google-crc32c==1.1.2
            f.write(
                b"from setuptols import setup\n"
                b"try:\n"
                b"    setup(cffi_modules=['a_build.py:ffibuilder'])\n"
                b"except:\n"
                b"    setup()\n"
            )

    reason = build._likely_binary(str(filename), ())
    assert reason == "sdist setup.py has `cffi_modules`"


def test_likely_binary_cffi_tar(tmp_path):
    filename = tmp_path.joinpath("a-1.tar.gz")
    with tarfile.open(filename, "w:gz") as tarf:
        # similar to google-crc32c==1.1.2
        bio = io.BytesIO(
            b"from setuptols import setup\n"
            b"try:\n"
            b"    setup(cffi_modules=['a_build.py:ffibuilder'])\n"
            b"except:\n"
            b"    setup()\n"
        )
        tar_info = tarfile.TarInfo(name="a-1/setup.py")
        tar_info.size = len(bio.getvalue())
        tarf.addfile(tar_info, bio)

    reason = build._likely_binary(str(filename), ())
    assert reason == "sdist setup.py has `cffi_modules`"


def test_likely_binary_ignores_test_files(tmp_path):
    filename = tmp_path.joinpath("a-1.tar.gz")
    with tarfile.open(filename, "w:gz") as tarf:
        tarf.addfile(tarfile.TarInfo("a-1/test/_ext.pyd"))
        tarf.addfile(tarfile.TarInfo("a-1/tests/_ext.c"))

    reason = build._likely_binary(str(filename), ())
    assert reason is None


def test_likely_binary_ignore(tmp_path):
    filename = tmp_path.joinpath("a-1.tar.gz")
    with tarfile.open(filename, "w:gz") as tarf:
        tarf.addfile(tarfile.TarInfo("a-1/foo/bar.c"))

    reason = build._likely_binary(str(filename), ("a-1/foo/bar.c",))
    assert reason is None


def test_join_env_variable_not_present():
    ret = build._join_env(name="PATH", value="/some/dir", sep=":", env={})
    assert ret == "/some/dir"


def test_join_env_variable_present():
    env = {"PATH": "/bin:/usr/bin"}
    ret = build._join_env(name="PATH", value="/some/dir", sep=":", env=env)
    assert ret == "/some/dir:/bin:/usr/bin"


def test_prebuild_noop_without_command(tmp_path):
    pkg = Package.make("a==1", {})
    env = {"SOME": "VAR"}
    with build._prebuild(pkg, str(tmp_path), env=env):
        assert env == {"SOME": "VAR"}
    assert env == {"SOME": "VAR"}


def test_prebuild_runs_and_prefixes_path(tmp_path, capfd):
    pkg = Package.make("a==1", {"custom_prebuild": "echo arg"})
    env = {"SOME": "VAR"}
    with build._prebuild(pkg, str(tmp_path), env=env):
        assert env == {
            "SOME": "VAR",
            "PATH": str(tmp_path.joinpath("prefix/bin")),
            "CPPFLAGS": f"-I{tmp_path.joinpath('prefix/include')}",
            "LDFLAGS": f"-L{tmp_path.joinpath('prefix/lib')}",
            "LD_LIBRARY_PATH": str(tmp_path.joinpath("prefix/lib")),
            "PKG_CONFIG_PATH": str(tmp_path.joinpath("prefix/lib/pkgconfig")),
        }
    assert env == {"SOME": "VAR"}
    out, _ = capfd.readouterr()
    assert out == f"arg {tmp_path.joinpath('prefix')}\n"
