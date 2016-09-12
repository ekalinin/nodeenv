from __future__ import absolute_import
from __future__ import unicode_literals

import io
import os.path
import subprocess

import mock
import pytest

import nodeenv


HERE = os.path.abspath(os.path.dirname(__file__))


def test_compare_versions():
    assert nodeenv.compare_versions('1', '2') == -1
    assert nodeenv.compare_versions('1', '2') == -1
    assert nodeenv.compare_versions('0.1', '0.2') == -1
    assert nodeenv.compare_versions('0.9', '0.10') == -1
    assert nodeenv.compare_versions('0.2', '0.2.1') == -1
    assert nodeenv.compare_versions('0.2.1', '0.2.10') == -1
    assert nodeenv.compare_versions('0.2.9', '0.2.10') == -1
    assert nodeenv.compare_versions('0.2.1', '0.3') == -1


def test_gets_a_hrefs_trivial():
    parser = nodeenv.GetsAHrefs()
    parser.feed('')
    assert parser.hrefs == []


def test_gets_a_hrefs_nodejs_org():
    # Retrieved 2015-01-15
    contents = io.open(os.path.join(HERE, 'nodejs.htm')).read()
    parser = nodeenv.GetsAHrefs()
    parser.feed(contents)
    # Smoke test
    assert parser.hrefs == [
        '../', 'docs/', 'x64/', 'SHASUMS.txt', 'SHASUMS.txt.asc',
        'SHASUMS.txt.gpg', 'SHASUMS256.txt', 'SHASUMS256.txt.asc',
        'SHASUMS256.txt.gpg', 'node-v0.10.35-darwin-x64.tar.gz',
        'node-v0.10.35-darwin-x86.tar.gz', 'node-v0.10.35-linux-x64.tar.gz',
        'node-v0.10.35-linux-x86.tar.gz', 'node-v0.10.35-sunos-x64.tar.gz',
        'node-v0.10.35-sunos-x86.tar.gz', 'node-v0.10.35-x86.msi',
        'node-v0.10.35.pkg', 'node-v0.10.35.tar.gz', 'node.exe',
        'node.exp', 'node.lib', 'node.pdb', 'openssl-cli.exe',
        'openssl-cli.pdb',
    ]


def test_gets_a_hrefs_iojs_org():
    # Retrieved 2015-01-15
    contents = io.open(os.path.join(HERE, 'iojs.htm')).read()
    parser = nodeenv.GetsAHrefs()
    parser.feed(contents)
    # Smoke test
    assert parser.hrefs == [
        '../', 'doc/', 'win-x64/', 'win-x86/', 'SHASUMS256.txt',
        'SHASUMS256.txt.asc', 'SHASUMS256.txt.gpg',
        'iojs-v1.0.1-darwin-x64.tar.gz', 'iojs-v1.0.1-linux-armv7l.tar.gz',
        'iojs-v1.0.1-linux-armv7l.tar.xz', 'iojs-v1.0.1-linux-x64.tar.gz',
        'iojs-v1.0.1-linux-x64.tar.xz', 'iojs-v1.0.1-linux-x86.tar.gz',
        'iojs-v1.0.1-linux-x86.tar.xz', 'iojs-v1.0.1-x64.msi',
        'iojs-v1.0.1-x86.msi', 'iojs-v1.0.1.pkg', 'iojs-v1.0.1.tar.gz',
        'iojs-v1.0.1.tar.xz',
    ]


@pytest.mark.integration
def test_smoke(tmpdir):
    nenv_path = tmpdir.join('nenv').strpath
    subprocess.check_call([
        # Enable coverage
        'coverage', 'run', '-p',
        '-m', 'nodeenv', '--prebuilt', nenv_path,
    ])
    assert os.path.exists(nenv_path)
    subprocess.check_call([
        'sh', '-c', '. {0}/bin/activate && nodejs --version'.format(nenv_path),
    ])


@pytest.yield_fixture
def returns_iojs_dist():
    with io.open(os.path.join(HERE, 'iojs_dist.htm'), 'rb') as iojs_dist:
        with mock.patch.object(nodeenv, 'urlopen', return_value=iojs_dist):
            yield


@pytest.yield_fixture
def returns_nodejs_dist():
    with io.open(os.path.join(HERE, 'nodejs_dist.htm'), 'rb') as node_dist:
        with mock.patch.object(nodeenv, 'urlopen', return_value=node_dist):
            yield


@pytest.yield_fixture
def cap_logging_info():
    with mock.patch.object(nodeenv.logger, 'info') as mck:
        yield mck


def mck_to_out(mck):
    return '\n'.join(call[0][0] for call in mck.call_args_list)


@pytest.mark.usefixtures('returns_iojs_dist')
def test_get_node_versions_iojs():
    versions = nodeenv.get_node_versions()
    assert versions == ['1.0.0', '1.0.1', '1.0.2', '1.0.3', '1.0.4', '1.1.0']


@pytest.mark.usefixtures('returns_nodejs_dist')
def test_get_node_versions_nodejs():
    versions = nodeenv.get_node_versions()
    # There's a lot of versions here, let's just do some sanity assertions
    assert len(versions) == 227
    assert versions[0:3] == ['0.0.1', '0.0.2', '0.0.3']
    assert versions[-3:] == ['0.11.15', '0.11.16', '0.12.0']


@pytest.mark.usefixtures('returns_iojs_dist')
def test_print_node_versions_iojs(cap_logging_info):
    nodeenv.print_node_versions()
    printed = mck_to_out(cap_logging_info)
    assert printed == '1.0.0\t1.0.1\t1.0.2\t1.0.3\t1.0.4\t1.1.0'


@pytest.mark.usefixtures('returns_nodejs_dist')
def test_print_node_versions_node(cap_logging_info):
    nodeenv.print_node_versions()
    printed = mck_to_out(cap_logging_info)
    # There's a lot of output here, let's just assert a few things
    assert printed.startswith(
        '0.0.1\t0.0.2\t0.0.3\t0.0.4\t0.0.5\t0.0.6\t0.1.0\t0.1.1\n'
    )
    assert printed.endswith('\n0.11.15\t0.11.16\t0.12.0')
    tabs_per_line = [line.count('\t') for line in printed.splitlines()]
    # 8 items per line = 7 tabs
    # The last line contains the remaning 3 items
    assert tabs_per_line == [7] * 28 + [2]


def test_predeactivate_hook(tmpdir):
    # Throw error if the environment directory is not a string
    with pytest.raises((TypeError, AttributeError)):
        nodeenv.set_predeactivate_hook(tmpdir)
    # Throw error if environment directory has no bin path
    with pytest.raises((OSError, IOError)):
        nodeenv.set_predeactivate_hook(tmpdir.strpath)
    tmpdir.mkdir('bin')
    nodeenv.set_predeactivate_hook(tmpdir.strpath)
    p = tmpdir.join('bin').join('predeactivate')
    assert 'deactivate_node' in p.read()
