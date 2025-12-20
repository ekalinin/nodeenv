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


@pytest.fixture
def mock_host_platform():
    with mock.patch.object(nodeenv, 'is_x86_64_musl', return_value=False):
        with mock.patch.object(nodeenv, 'is_riscv64', return_value=False):
            yield


@pytest.fixture
def mock_riscv64_platform():
    with mock.patch.object(nodeenv, 'is_x86_64_musl', return_value=False):
        with mock.patch.object(nodeenv, 'is_riscv64', return_value=True):
            yield


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


@pytest.mark.usefixtures('mock_index_json', 'mock_host_platform')
def test_get_latest_node_version():
    assert nodeenv.get_last_stable_node_version() == '13.5.0'


@pytest.mark.usefixtures('mock_index_json', 'mock_host_platform')
def test_get_lts_node_version():
    assert nodeenv.get_last_lts_node_version() == '12.14.0'


@pytest.mark.usefixtures('mock_index_json', 'mock_riscv64_platform')
def test_get_latest_node_version_riscv64():
    assert nodeenv.get_last_stable_node_version() == '13.4.0'


@pytest.mark.usefixtures('mock_index_json', 'mock_riscv64_platform')
def test_get_lts_node_version_riscv64():
    assert nodeenv.get_last_lts_node_version() == '12.13.1'


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


def test_clear_output():
    assert nodeenv.clear_output(
        bytes('some \ntext', 'utf-8')) == 'some text'


def test_remove_env_bin_from_path():
    assert (nodeenv.remove_env_bin_from_path(
        '//home://home/env/bin://home/bin', '//home/env/bin')
            == '//home://home/bin')


@pytest.mark.parametrize(
    "node_version_file_content, expected_node_version",
    [
        ("v22.14.0", "22.14.0"),
        ("22.14.0", "22.14.0"),
        ("v22.14.0\n", "22.14.0"),
        ("v22.14.0\r\n", "22.14.0"),
    ],
)
def test_node_version_file(node_version_file_content, expected_node_version):
    def custom_exists(path):
        if path == ".node-version":
            return True
        else:
            return os.path.exists(path)

    def custom_open(file_path, *args, **kwargs):
        if file_path == ".node-version":
            return mock.mock_open(read_data=node_version_file_content)()
        else:
            return open(file_path, *args, **kwargs)

    with mock.patch("os.path.exists", new=custom_exists), mock.patch(
        "builtins.open", new=custom_open
    ):
        nodeenv.Config._load([])
        assert nodeenv.Config.node == expected_node_version


class TestGetNodeBinUrl:
    """Tests for get_node_bin_url function"""

    @pytest.mark.parametrize(
        "machine,expected_arch",
        [
            ('x86', 'x86'),
            ('i686', 'x86'),
            ('x86_64', 'x64'),
            ('amd64', 'x64'),
            ('AMD64', 'x64'),
            ('armv6l', 'armv6l'),
            ('armv7l', 'armv7l'),
            ('armv8l', 'armv7l'),
            ('aarch64', 'arm64'),
            ('arm64', 'arm64'),
            ('arm64/v8', 'arm64'),
            ('armv8', 'arm64'),
            ('armv8.4', 'arm64'),
            ('ppc64le', 'ppc64le'),
            ('s390x', 's390x'),
            ('riscv64', 'riscv64'),
        ],
    )
    def test_linux_architectures(self, machine, expected_arch):
        """Test URL generation for various Linux architectures"""
        root_url = 'https://nodejs.org/download/release/v18.0.0/'
        with mock.patch.object(platform, 'system', return_value='Linux'), \
             mock.patch.object(
                 platform, 'machine', return_value=machine), \
             mock.patch.object(nodeenv, 'is_WIN', False), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch.object(
                 nodeenv, 'is_x86_64_musl', return_value=False), \
             mock.patch.object(
                 nodeenv, 'get_root_url', return_value=root_url):
            url = nodeenv.get_node_bin_url('18.0.0')
            expected = (
                'https://nodejs.org/download/release/v18.0.0/'
                'node-v18.0.0-linux-{}.tar.gz'.format(expected_arch)
            )
            assert url == expected

    @pytest.mark.parametrize(
        "machine,expected_arch",
        [
            ('x86', 'x86'),
            ('x86_64', 'x64'),
            ('AMD64', 'x64'),
        ],
    )
    def test_windows_architectures(self, machine, expected_arch):
        """Test URL generation for Windows platforms"""
        root_url = 'https://nodejs.org/download/release/v18.0.0/'
        with mock.patch.object(
                platform, 'system', return_value='Windows'), \
             mock.patch.object(
                 platform, 'machine', return_value=machine), \
             mock.patch.object(nodeenv, 'is_WIN', True), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch.object(
                 nodeenv, 'is_x86_64_musl', return_value=False), \
             mock.patch.object(
                 nodeenv, 'get_root_url', return_value=root_url):
            url = nodeenv.get_node_bin_url('18.0.0')
            expected = (
                'https://nodejs.org/download/release/v18.0.0/'
                'node-v18.0.0-win-{}.zip'.format(expected_arch)
            )
            assert url == expected

    def test_darwin_x64(self):
        """Test URL generation for macOS x64"""
        root_url = 'https://nodejs.org/download/release/v18.0.0/'
        with mock.patch.object(platform, 'system', return_value='Darwin'), \
             mock.patch.object(
                 platform, 'machine', return_value='x86_64'), \
             mock.patch.object(nodeenv, 'is_WIN', False), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch.object(
                 nodeenv, 'is_x86_64_musl', return_value=False), \
             mock.patch.object(
                 nodeenv, 'get_root_url', return_value=root_url):
            url = nodeenv.get_node_bin_url('18.0.0')
            expected = (
                'https://nodejs.org/download/release/v18.0.0/'
                'node-v18.0.0-darwin-x64.tar.gz'
            )
            assert url == expected

    def test_darwin_arm64(self):
        """Test URL generation for macOS ARM64 (Apple Silicon)"""
        root_url = 'https://nodejs.org/download/release/v18.0.0/'
        with mock.patch.object(platform, 'system', return_value='Darwin'), \
             mock.patch.object(platform, 'machine', return_value='arm64'), \
             mock.patch.object(nodeenv, 'is_WIN', False), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch.object(
                 nodeenv, 'is_x86_64_musl', return_value=False), \
             mock.patch.object(
                 nodeenv, 'get_root_url', return_value=root_url):
            url = nodeenv.get_node_bin_url('18.0.0')
            expected = (
                'https://nodejs.org/download/release/v18.0.0/'
                'node-v18.0.0-darwin-arm64.tar.gz'
            )
            assert url == expected

    def test_x86_64_musl(self):
        """Test URL generation for x86_64 musl (Alpine Linux)"""
        root_url = 'https://nodejs.org/download/release/v18.0.0/'
        with mock.patch.object(platform, 'system', return_value='Linux'), \
             mock.patch.object(
                 platform, 'machine', return_value='x86_64'), \
             mock.patch.object(nodeenv, 'is_WIN', False), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch.object(
                 nodeenv, 'is_x86_64_musl', return_value=True), \
             mock.patch.object(
                 nodeenv, 'get_root_url', return_value=root_url):
            url = nodeenv.get_node_bin_url('18.0.0')
            expected = (
                'https://nodejs.org/download/release/v18.0.0/'
                'node-v18.0.0-linux-x64-musl.tar.gz'
            )
            assert url == expected

    def test_cygwin(self):
        """Test URL generation for CYGWIN platforms"""
        root_url = 'https://nodejs.org/download/release/v18.0.0/'
        with mock.patch.object(
                platform, 'system', return_value='CYGWIN_NT-10.0'), \
             mock.patch.object(
                 platform, 'machine', return_value='x86_64'), \
             mock.patch.object(nodeenv, 'is_WIN', False), \
             mock.patch.object(nodeenv, 'is_CYGWIN', True), \
             mock.patch.object(
                 nodeenv, 'is_x86_64_musl', return_value=False), \
             mock.patch.object(
                 nodeenv, 'get_root_url', return_value=root_url):
            url = nodeenv.get_node_bin_url('18.0.0')
            expected = (
                'https://nodejs.org/download/release/v18.0.0/'
                'node-v18.0.0-win-x64.zip'
            )
            assert url == expected

    def test_old_node_version(self):
        """Test URL generation for old Node.js version (< 0.5)"""
        root_url = 'https://nodejs.org/download/release/'
        with mock.patch.object(platform, 'system', return_value='Linux'), \
             mock.patch.object(
                 platform, 'machine', return_value='x86_64'), \
             mock.patch.object(nodeenv, 'is_WIN', False), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch.object(
                 nodeenv, 'is_x86_64_musl', return_value=False), \
             mock.patch.object(
                 nodeenv, 'get_root_url', return_value=root_url):
            url = nodeenv.get_node_bin_url('0.4.12')
            expected = (
                'https://nodejs.org/download/release/'
                'node-v0.4.12-linux-x64.tar.gz'
            )
            assert url == expected

    def test_freebsd(self):
        """Test URL generation for FreeBSD"""
        root_url = 'https://nodejs.org/download/release/v18.0.0/'
        with mock.patch.object(
                platform, 'system', return_value='FreeBSD'), \
             mock.patch.object(platform, 'machine', return_value='amd64'), \
             mock.patch.object(nodeenv, 'is_WIN', False), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch.object(
                 nodeenv, 'is_x86_64_musl', return_value=False), \
             mock.patch.object(
                 nodeenv, 'get_root_url', return_value=root_url):
            url = nodeenv.get_node_bin_url('18.0.0')
            expected = (
                'https://nodejs.org/download/release/v18.0.0/'
                'node-v18.0.0-freebsd-x64.tar.gz'
            )
            assert url == expected

    def test_uppercase_machine_x86_64(self):
        """Test that uppercase X86_64 is handled correctly"""
        root_url = 'https://nodejs.org/download/release/v18.0.0/'
        with mock.patch.object(platform, 'system', return_value='Linux'), \
             mock.patch.object(
                 platform, 'machine', return_value='X86_64'), \
             mock.patch.object(nodeenv, 'is_WIN', False), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch.object(
                 nodeenv, 'is_x86_64_musl', return_value=False), \
             mock.patch.object(
                 nodeenv, 'get_root_url', return_value=root_url):
            url = nodeenv.get_node_bin_url('18.0.0')
            expected = (
                'https://nodejs.org/download/release/v18.0.0/'
                'node-v18.0.0-linux-x64.tar.gz'
            )
            assert url == expected

    def test_uppercase_machine_aarch64(self):
        """Test that uppercase AARCH64 is handled correctly"""
        root_url = 'https://nodejs.org/download/release/v18.0.0/'
        with mock.patch.object(platform, 'system', return_value='Linux'), \
             mock.patch.object(
                 platform, 'machine', return_value='AARCH64'), \
             mock.patch.object(nodeenv, 'is_WIN', False), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch.object(
                 nodeenv, 'is_x86_64_musl', return_value=False), \
             mock.patch.object(
                 nodeenv, 'get_root_url', return_value=root_url):
            url = nodeenv.get_node_bin_url('18.0.0')
            expected = (
                'https://nodejs.org/download/release/v18.0.0/'
                'node-v18.0.0-linux-arm64.tar.gz'
            )
            assert url == expected

    def test_mixed_case_machine(self):
        """Test that mixed case Aarch64 is handled correctly"""
        root_url = 'https://nodejs.org/download/release/v18.0.0/'
        with mock.patch.object(platform, 'system', return_value='Linux'), \
             mock.patch.object(
                 platform, 'machine', return_value='Aarch64'), \
             mock.patch.object(nodeenv, 'is_WIN', False), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch.object(
                 nodeenv, 'is_x86_64_musl', return_value=False), \
             mock.patch.object(
                 nodeenv, 'get_root_url', return_value=root_url):
            url = nodeenv.get_node_bin_url('18.0.0')
            expected = (
                'https://nodejs.org/download/release/v18.0.0/'
                'node-v18.0.0-linux-arm64.tar.gz'
            )
            assert url == expected

    def test_uppercase_machine_amd64(self):
        """Test that uppercase AMD64 (Windows style) is handled correctly"""
        root_url = 'https://nodejs.org/download/release/v18.0.0/'
        with mock.patch.object(
                platform, 'system', return_value='Windows'), \
             mock.patch.object(platform, 'machine', return_value='AMD64'), \
             mock.patch.object(nodeenv, 'is_WIN', True), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch.object(
                 nodeenv, 'is_x86_64_musl', return_value=False), \
             mock.patch.object(
                 nodeenv, 'get_root_url', return_value=root_url):
            url = nodeenv.get_node_bin_url('18.0.0')
            expected = (
                'https://nodejs.org/download/release/v18.0.0/'
                'node-v18.0.0-win-x64.zip'
            )
            assert url == expected


class TestGetEnvDir:
    """Tests for get_env_dir function"""

    def test_with_python_virtualenv_real_prefix(self):
        """Test get_env_dir when using python virtualenv with real_prefix"""
        args = mock.Mock()
        args.python_virtualenv = True
        test_prefix = '/path/to/virtualenv'

        with mock.patch.object(sys, 'real_prefix', test_prefix, create=True), \
             mock.patch.object(sys, 'prefix', test_prefix):
            result = nodeenv.get_env_dir(args)
            assert result == test_prefix

    def test_with_python_virtualenv_base_prefix(self):
        """Test get_env_dir when using python virtualenv with base_prefix"""
        args = mock.Mock()
        args.python_virtualenv = True
        test_prefix = '/path/to/virtualenv'
        test_base_prefix = '/usr'

        # Remove real_prefix if it exists
        if hasattr(sys, 'real_prefix'):
            with mock.patch.object(sys, 'real_prefix', create=False):
                with mock.patch.object(sys, 'prefix', test_prefix), \
                     mock.patch.object(sys, 'base_prefix', test_base_prefix):
                    result = nodeenv.get_env_dir(args)
                    assert result == test_prefix
        else:
            with mock.patch.object(sys, 'prefix', test_prefix), \
                 mock.patch.object(sys, 'base_prefix', test_base_prefix):
                result = nodeenv.get_env_dir(args)
                assert result == test_prefix

    def test_with_python_virtualenv_conda_prefix(self):
        """Test get_env_dir when using conda environment"""
        args = mock.Mock()
        args.python_virtualenv = True
        test_prefix = '/path/to/conda/env'

        # Remove real_prefix if it exists
        if hasattr(sys, 'real_prefix'):
            with mock.patch.object(sys, 'real_prefix', create=False):
                env_dict = {'CONDA_PREFIX': test_prefix}
                with mock.patch.object(sys, 'prefix', test_prefix), \
                     mock.patch.object(sys, 'base_prefix', test_prefix), \
                     mock.patch.dict(os.environ, env_dict):
                    result = nodeenv.get_env_dir(args)
                    assert result == test_prefix
        else:
            env_dict = {'CONDA_PREFIX': test_prefix}
            with mock.patch.object(sys, 'prefix', test_prefix), \
                 mock.patch.object(sys, 'base_prefix', test_prefix), \
                 mock.patch.dict(os.environ, env_dict):
                result = nodeenv.get_env_dir(args)
                assert result == test_prefix

    def test_with_python_virtualenv_virtual_env(self):
        """Test get_env_dir when using VIRTUAL_ENV variable"""
        args = mock.Mock()
        args.python_virtualenv = True
        test_prefix = '/path/to/venv'
        virtual_env = '/path/to/virtual/env'

        # Remove real_prefix if it exists
        if hasattr(sys, 'real_prefix'):
            with mock.patch.object(sys, 'real_prefix', create=False):
                env_dict = {'VIRTUAL_ENV': virtual_env}
                with mock.patch.object(sys, 'prefix', test_prefix), \
                     mock.patch.object(sys, 'base_prefix', test_prefix), \
                     mock.patch.dict(os.environ, env_dict, clear=True):
                    result = nodeenv.get_env_dir(args)
                    assert result == virtual_env
        else:
            env_dict = {'VIRTUAL_ENV': virtual_env}
            with mock.patch.object(sys, 'prefix', test_prefix), \
                 mock.patch.object(sys, 'base_prefix', test_prefix), \
                 mock.patch.dict(os.environ, env_dict, clear=True):
                result = nodeenv.get_env_dir(args)
                assert result == virtual_env

    def test_with_python_virtualenv_no_virtualenv_exits(self):
        """Test get_env_dir exits when no virtualenv is available"""
        args = mock.Mock()
        args.python_virtualenv = True
        test_prefix = '/usr'

        # Remove real_prefix if it exists
        if hasattr(sys, 'real_prefix'):
            with mock.patch.object(sys, 'real_prefix', create=False):
                with mock.patch.object(sys, 'prefix', test_prefix), \
                     mock.patch.object(sys, 'base_prefix', test_prefix), \
                     mock.patch.dict(os.environ, {}, clear=True), \
                     pytest.raises(SystemExit) as exc_info:
                    nodeenv.get_env_dir(args)
                assert exc_info.value.code == 2
        else:
            with mock.patch.object(sys, 'prefix', test_prefix), \
                 mock.patch.object(sys, 'base_prefix', test_prefix), \
                 mock.patch.dict(os.environ, {}, clear=True), \
                 pytest.raises(SystemExit) as exc_info:
                nodeenv.get_env_dir(args)
            assert exc_info.value.code == 2

    def test_without_python_virtualenv(self):
        """Test get_env_dir when not using python virtualenv"""
        args = mock.Mock()
        args.python_virtualenv = False
        args.env_dir = '/path/to/node/env'

        result = nodeenv.get_env_dir(args)
        assert result == '/path/to/node/env'

    def test_returns_utf8_encoded_string(self):
        """Test that get_env_dir returns UTF-8 encoded string"""
        args = mock.Mock()
        args.python_virtualenv = False
        args.env_dir = '/path/to/env'

        result = nodeenv.get_env_dir(args)
        # The to_utf8 function is applied,
        # but in Python 3 it returns the same string
        assert result == '/path/to/env'
