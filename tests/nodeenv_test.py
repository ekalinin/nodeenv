from __future__ import absolute_import
from __future__ import unicode_literals

import sys
if sys.version_info < (3, 3):
    from pipes import quote as _quote
else:
    from shlex import quote as _quote
import os.path
import subprocess
import sys
import sysconfig
import platform

try:
    from unittest import mock
except ImportError:
    import mock
import pytest

import nodeenv
from nodeenv import IncompleteRead

HERE = os.path.abspath(os.path.dirname(__file__))


@pytest.mark.integration
def test_smoke(tmpdir):
    nenv_path = tmpdir.join('nenv').strpath
    subprocess.check_call([
        # Enable coverage
        'coverage', 'run', '-p',
        '-m', 'nodeenv', '--prebuilt', nenv_path,
    ])
    assert os.path.exists(nenv_path)
    activate = _quote(os.path.join(nenv_path, 'bin', 'activate'))
    subprocess.check_call([
        'sh', '-c', '. {} && node --version'.format(activate),
    ])


@pytest.mark.integration
@pytest.mark.skipif(sys.platform == 'win32', reason='-n system is posix only')
def test_smoke_n_system_special_chars(tmpdir):
    nenv_path = tmpdir.join('nenv (production env)').strpath
    subprocess.check_call((
        'coverage', 'run', '-p',
        '-m', 'nodeenv', '-n', 'system', nenv_path,
    ))
    assert os.path.exists(nenv_path)
    activate = _quote(os.path.join(nenv_path, 'bin', 'activate'))
    subprocess.check_call([
        'sh', '-c', '. {} && node --version'.format(activate),
    ])


@pytest.fixture
def mock_index_json():
    # retrieved 2019-12-31
    with open(os.path.join(HERE, 'nodejs_index.json'), 'rb') as f:
        with mock.patch.object(nodeenv, 'urlopen', return_value=f):
            yield


@pytest.fixture
def cap_logging_info():
    with mock.patch.object(nodeenv.logger, 'info') as mck:
        yield mck


def mck_to_out(mck):
    return '\n'.join(call[0][0] for call in mck.call_args_list)


@pytest.mark.usefixtures('mock_index_json')
def test_get_node_versions():
    versions = nodeenv.get_node_versions()
    # there are a lot of versions, just some sanity checks here
    assert len(versions) == 485
    assert versions[:3] == ['0.1.14', '0.1.15', '0.1.16']
    assert versions[-3:] == ['13.3.0', '13.4.0', '13.5.0']


@pytest.mark.usefixtures('mock_index_json')
def test_print_node_versions(cap_logging_info):
    nodeenv.print_node_versions()
    printed = mck_to_out(cap_logging_info)
    assert printed.startswith(
        '0.1.14\t0.1.15\t0.1.16\t0.1.17\t0.1.18\t0.1.19\t0.1.20\t0.1.21\n'
    )
    assert printed.endswith('\n13.1.0\t13.2.0\t13.3.0\t13.4.0\t13.5.0')
    tabs_per_line = [line.count('\t') for line in printed.splitlines()]
    # 8 items per line = 7 tabs
    # The last line contains the remaining 5 items
    assert tabs_per_line == [7] * 60 + [4]


def test_predeactivate_hook(tmpdir):
    # Throw error if the environment directory is not a string
    with pytest.raises((TypeError, AttributeError)):
        nodeenv.set_predeactivate_hook(1)
    # Throw error if environment directory has no bin path
    with pytest.raises((OSError, IOError)):
        nodeenv.set_predeactivate_hook(tmpdir.strpath)
    tmpdir.mkdir('bin')
    nodeenv.set_predeactivate_hook(tmpdir.strpath)
    p = tmpdir.join('bin').join('predeactivate')
    assert 'deactivate_node' in p.read()


def test_mirror_option():
    urls = [('https://npm.taobao.org/mirrors/node',
             'https://npm.taobao.org/mirrors/node/index.json'),
            ('npm.some-mirror.com',
             'https://npm.some-mirror.com/download/release/index.json'),
            ('',
             'https://nodejs.org/download/release/index.json')]
    sys_type = sysconfig.get_config_var('HOST_GNU_TYPE')
    musl_type = ['x86_64-pc-linux-musl', 'x86_64-unknown-linux-musl']
    # Check if running on musl system and delete last mirror if it is
    if sys_type in musl_type:
        urls.pop()
    elif platform.machine() == "riscv64":
        urls.pop()
    with open(os.path.join(HERE, 'nodejs_index.json'), 'rb') as f:
        def rewind(_):
            f.seek(0)
            return f
        argv = [__file__, '--list']
        for mirror, url in urls:
            if mirror:
                test_argv = argv + ['--mirror=' + mirror]
            else:
                test_argv = argv
            with mock.patch.object(sys, 'argv', test_argv), \
                mock.patch.object(nodeenv.logger, 'info') as mock_logger, \
                mock.patch.object(nodeenv, 'urlopen',
                                  side_effect=rewind) as mock_urlopen:
                nodeenv.src_base_url = None
                nodeenv.main()
                mock_urlopen.assert_called_with(url)
                mock_logger.assert_called()


@pytest.mark.usefixtures('mock_index_json')
def test_get_latest_node_version():
    assert nodeenv.get_last_stable_node_version() == '13.5.0'


@pytest.mark.usefixtures('mock_index_json')
def test_get_lts_node_version():
    assert nodeenv.get_last_lts_node_version() == '12.14.0'


def test__download_node_file():
    with mock.patch.object(nodeenv, 'urlopen') as m_urlopen:
        m_urlopen.side_effect = IncompleteRead("dummy")
        with pytest.raises(IncompleteRead):
            nodeenv._download_node_file(
                "https://dummy/nodejs.tar.gz",
                n_attempt=5
            )
        assert m_urlopen.call_count == 5


def test_parse_version():
    assert nodeenv.parse_version("v21.7") == (21, 7)
    assert nodeenv.parse_version("v21.7.3") == (21, 7, 3)
    assert nodeenv.parse_version("v21.7.3+0-b20240228T18452699") == (21, 7, 3)
