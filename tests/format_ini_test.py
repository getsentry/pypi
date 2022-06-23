from __future__ import annotations

import format_ini


def test_error_incorrect_sections(capsys, tmp_path):
    ini = tmp_path.joinpath("f.ini")
    ini.write_text("[a]\n[b]\n")

    assert format_ini.main((str(ini),)) == 1

    _, err = capsys.readouterr()
    assert err == (
        f"{ini}: section [a] must be `[a==...]`\n"
        f"{ini}: section [b] must be `[b==...]`\n"
    )


def test_reorders(capsys, tmp_path):
    ini = tmp_path.joinpath("f.ini")
    ini.write_text("[simplejson==3.17.2]\n[botocore==1.25.12]\n")

    assert format_ini.main((str(ini),)) == 1

    assert ini.read_text() == "[botocore==1.25.12]\n\n[simplejson==3.17.2]\n"

    _, err = capsys.readouterr()
    assert err == f"{ini}: formatted\n"


def test_normalizes_names(capsys, tmp_path):
    ini = tmp_path.joinpath("f.ini")
    ini.write_text("[Django==2.2.28]\n\n[aspy.yaml==1.3.0]\n")

    assert format_ini.main((str(ini),)) == 1

    assert ini.read_text() == "[aspy-yaml==1.3.0]\n\n[django==2.2.28]\n"

    _, err = capsys.readouterr()
    assert err == f"{ini}: formatted\n"


def test_groups_same_packages(tmp_path):
    ini_src = """\
[botocore==1.25.12]

[simplejson==3.17.2]
[simplejson==3.17.5]
"""
    ini = tmp_path.joinpath("f.ini")
    ini.write_text(ini_src)

    assert format_ini.main((str(ini),)) == 0


def test_format_list_attributes(capsys, tmp_path):
    ini_src = """\
[xmlsec==1.3.12]
apt_requires = libxmlsec1-dev pkg-config
"""
    expected = """\
[xmlsec==1.3.12]
apt_requires =
    libxmlsec1-dev
    pkg-config
"""
    ini = tmp_path.joinpath("f.ini")
    ini.write_text(ini_src)

    assert format_ini.main((str(ini),)) == 1

    assert ini.read_text() == expected

    _, err = capsys.readouterr()
    assert err == f"{ini}: formatted\n"


def test_sorts_attributes(capsys, tmp_path):
    ini_src = """\
[confluent-kafka==1.7.0]
brew_requires = librdkafka
apt_requires = librdkafka-dev
"""
    expected = """\
[confluent-kafka==1.7.0]
apt_requires = librdkafka-dev
brew_requires = librdkafka
"""
    ini = tmp_path.joinpath("f.ini")
    ini.write_text(ini_src)

    assert format_ini.main((str(ini),)) == 1

    assert ini.read_text() == expected

    _, err = capsys.readouterr()
    assert err == f"{ini}: formatted\n"
