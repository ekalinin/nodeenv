import os
import re

import pytest

import nodeenv


@pytest.fixture
def default_config(monkeypatch, tmpdir):
    for name, value in nodeenv.Config._default.items():
        monkeypatch.setattr(nodeenv.Config, name, value)
    monkeypatch.chdir(str(tmpdir))


def _load_defaults(text, tmpdir):
    config = tmpdir.join('nodeenvrc')
    config.write(text)
    nodeenv.Config._load([str(config)])
    assert {name: getattr(nodeenv.Config, name)
            for name in nodeenv.Config._default} == nodeenv.Config._default


def test_dumped_configuration_roundtrips(default_config, capsys, tmpdir):
    nodeenv.Config._dump()
    _load_defaults(capsys.readouterr().out, tmpdir)


def test_readme_configuration_roundtrips(default_config, tmpdir):
    readme = os.path.join(os.path.dirname(__file__), '..', 'README.rst')
    with open(readme) as stream:
        block = re.search(r'    \[nodeenv\]\n(?:    .*\n)+',
                          stream.read()).group(0)
    _load_defaults('\n'.join(line[4:] for line in block.splitlines()), tmpdir)
