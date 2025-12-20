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


class TestInstallNpm:
    """Tests for install_npm function"""

    def test_install_npm_basic(self):
        """Test basic npm installation with default settings"""
        args = mock.Mock()
        args.npm = '8.19.2'
        args.no_npm_clean = False
        args.verbose = False

        env_dir = '/path/to/env'
        src_dir = '/path/to/src'

        mock_proc = mock.Mock()
        mock_proc.communicate.return_value = (b'npm installed', None)

        with mock.patch.object(
                subprocess, 'Popen', return_value=mock_proc
        ) as mock_popen, \
             mock.patch.object(nodeenv.logger, 'info') as mock_logger:
            nodeenv.install_npm(env_dir, src_dir, args)

            # Verify subprocess was called correctly
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args

            # Check command
            assert call_args[0][0][0] == 'sh'
            assert call_args[0][0][1] == '-c'
            expected_cmd = '. {0} && npm install -g npm@{1}'.format(
                _quote(os.path.join(env_dir, 'bin', 'activate')),
                '8.19.2'
            )
            assert call_args[0][0][2] == expected_cmd

            # Check environment variables
            env = call_args[1]['env']
            assert env['clean'] == 'yes'
            assert env['npm_install'] == '8.19.2'

            # Check other subprocess parameters
            assert call_args[1]['stdin'] == subprocess.PIPE
            assert call_args[1]['stdout'] == subprocess.PIPE
            assert call_args[1]['stderr'] == subprocess.STDOUT

            # Verify communicate was called
            mock_proc.communicate.assert_called_once()

            # Verify logging
            assert mock_logger.call_count >= 2
            log_calls = [call[0][0] for call in mock_logger.call_args_list]
            assert any('8.19.2' in str(call) for call in log_calls)
            assert any('done' in str(call) for call in log_calls)

    def test_install_npm_with_no_npm_clean(self):
        """Test npm installation with no_npm_clean flag"""
        args = mock.Mock()
        args.npm = 'latest'
        args.no_npm_clean = True
        args.verbose = False

        env_dir = '/test/env'
        src_dir = '/test/src'

        mock_proc = mock.Mock()
        mock_proc.communicate.return_value = (b'', None)

        with mock.patch.object(
                subprocess, 'Popen', return_value=mock_proc
        ) as mock_popen, \
             mock.patch.object(nodeenv.logger, 'info'):
            nodeenv.install_npm(env_dir, src_dir, args)

            # Check that clean='no' when no_npm_clean is True
            call_args = mock_popen.call_args
            env = call_args[1]['env']
            assert env['clean'] == 'no'
            assert env['npm_install'] == 'latest'

    def test_install_npm_verbose_output(self):
        """Test npm installation with verbose output enabled"""
        args = mock.Mock()
        args.npm = '9.0.0'
        args.no_npm_clean = False
        args.verbose = True

        env_dir = '/verbose/env'
        src_dir = '/verbose/src'

        test_output = b'Installing npm 9.0.0...\nDone!'
        mock_proc = mock.Mock()
        mock_proc.communicate.return_value = (test_output, None)

        with mock.patch.object(subprocess, 'Popen', return_value=mock_proc), \
             mock.patch.object(nodeenv.logger, 'info') as mock_logger:
            nodeenv.install_npm(env_dir, src_dir, args)

            # Verify that output was logged when verbose=True
            log_calls = [call[0][0] for call in mock_logger.call_args_list]
            assert test_output in log_calls

    def test_install_npm_latest_version(self):
        """Test npm installation with 'latest' version"""
        args = mock.Mock()
        args.npm = 'latest'
        args.no_npm_clean = False
        args.verbose = False

        env_dir = '/latest/env'
        src_dir = '/latest/src'

        mock_proc = mock.Mock()
        mock_proc.communicate.return_value = (b'', None)

        with mock.patch.object(
                subprocess, 'Popen', return_value=mock_proc
        ) as mock_popen, \
             mock.patch.object(nodeenv.logger, 'info'):
            nodeenv.install_npm(env_dir, src_dir, args)

            # Verify the command uses 'latest'
            call_args = mock_popen.call_args
            command = call_args[0][0][2]
            assert 'npm install -g npm@latest' in command

    def test_install_npm_with_special_chars_in_path(self):
        """Test npm installation with special characters in path"""
        args = mock.Mock()
        args.npm = '8.0.0'
        args.no_npm_clean = False
        args.verbose = False

        env_dir = '/path/with spaces/and (parens)/env'
        src_dir = '/path/src'

        mock_proc = mock.Mock()
        mock_proc.communicate.return_value = (b'', None)

        with mock.patch.object(
                subprocess, 'Popen', return_value=mock_proc
        ) as mock_popen, \
             mock.patch.object(nodeenv.logger, 'info'):
            nodeenv.install_npm(env_dir, src_dir, args)

            # Verify the path is properly quoted
            call_args = mock_popen.call_args
            command = call_args[0][0][2]
            # The path should be quoted to handle special characters
            activate_path = os.path.join(env_dir, 'bin', 'activate')
            quoted_path = _quote(activate_path)
            assert quoted_path in command

    def test_install_npm_environment_inheritance(self):
        """Test that install_npm inherits current environment variables"""
        args = mock.Mock()
        args.npm = '7.0.0'
        args.no_npm_clean = False
        args.verbose = False

        env_dir = '/env'
        src_dir = '/src'

        mock_proc = mock.Mock()
        mock_proc.communicate.return_value = (b'', None)

        test_env = {'TEST_VAR': 'test_value', 'PATH': '/usr/bin'}
        with mock.patch.object(
                subprocess, 'Popen', return_value=mock_proc
        ) as mock_popen, \
             mock.patch.object(nodeenv.logger, 'info'), \
             mock.patch.dict(os.environ, test_env, clear=True):
            nodeenv.install_npm(env_dir, src_dir, args)

            # Check that environment variables are inherited
            call_args = mock_popen.call_args
            env = call_args[1]['env']
            assert env['TEST_VAR'] == 'test_value'
            assert env['PATH'] == '/usr/bin'
            assert env['clean'] == 'yes'
            assert env['npm_install'] == '7.0.0'

    def test_install_npm_specific_version_formats(self):
        """Test npm installation with different version formats"""
        test_versions = ['8.19.2', '10.0.0', '6.14.18', 'latest']

        for version in test_versions:
            args = mock.Mock()
            args.npm = version
            args.no_npm_clean = False
            args.verbose = False

            env_dir = '/env'
            src_dir = '/src'

            mock_proc = mock.Mock()
            mock_proc.communicate.return_value = (b'', None)

            with mock.patch.object(
                    subprocess, 'Popen', return_value=mock_proc
            ) as mock_popen, \
                 mock.patch.object(nodeenv.logger, 'info'):
                nodeenv.install_npm(env_dir, src_dir, args)

                # Verify the version is correctly used in the command
                call_args = mock_popen.call_args
                command = call_args[0][0][2]
                assert f'npm install -g npm@{version}' in command

                # Verify version is in environment
                env = call_args[1]['env']
                assert env['npm_install'] == version


class TestInstallNpmWin:
    """Tests for install_npm_win function"""

    def test_install_npm_win_basic(self):
        """Test basic Windows npm installation"""
        args = mock.Mock()
        args.npm = '8.19.2'

        env_dir = 'C:\\path\\to\\env'
        src_dir = 'C:\\path\\to\\src'

        # Mock the zip file content
        mock_zip_content = b'PK\x03\x04...'  # Simplified zip header
        mock_response = mock.Mock()
        mock_response.read.return_value = mock_zip_content

        mock_zip = mock.Mock()
        mock_zip.__enter__ = mock.Mock(return_value=mock_zip)
        mock_zip.__exit__ = mock.Mock(return_value=False)

        with mock.patch.object(
                nodeenv, 'urlopen', return_value=mock_response
        ), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch('zipfile.ZipFile', return_value=mock_zip), \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch('shutil.copytree') as mock_copytree, \
             mock.patch('shutil.copy') as mock_copy, \
             mock.patch.object(nodeenv.logger, 'info') as mock_logger:
            nodeenv.install_npm_win(env_dir, src_dir, args)

            # Verify URL was constructed correctly
            expected_url = 'https://github.com/npm/cli/archive/v8.19.2.zip'
            nodeenv.urlopen.assert_called_once_with(expected_url)

            # Verify extraction happened
            mock_zip.extractall.assert_called_once_with(src_dir)

            # Verify copytree and copy were called
            assert mock_copytree.called
            assert mock_copy.call_count == 2

            # Verify logging
            log_calls = [call[0][0] for call in mock_logger.call_args_list]
            assert any('8.19.2' in str(call) for call in log_calls)

    def test_install_npm_win_removes_existing_files(self):
        """Test that existing npm files are removed before installation"""
        args = mock.Mock()
        args.npm = '9.0.0'

        env_dir = 'C:\\env'
        src_dir = 'C:\\src'

        mock_zip_content = b'PK\x03\x04...'
        mock_response = mock.Mock()
        mock_response.read.return_value = mock_zip_content

        mock_zip = mock.Mock()
        mock_zip.__enter__ = mock.Mock(return_value=mock_zip)
        mock_zip.__exit__ = mock.Mock(return_value=False)

        # Simulate existing files
        def exists_side_effect(path):
            if ('node_modules' in path or 'npm.cmd' in path or
                    'npm-cli.js' in path):
                return True
            return False

        with mock.patch.object(
                nodeenv, 'urlopen', return_value=mock_response
        ), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch('zipfile.ZipFile', return_value=mock_zip), \
             mock.patch('os.path.exists', side_effect=exists_side_effect), \
             mock.patch('shutil.rmtree') as mock_rmtree, \
             mock.patch('os.remove') as mock_remove, \
             mock.patch('shutil.copytree'), \
             mock.patch('shutil.copy'), \
             mock.patch.object(nodeenv.logger, 'info'):
            nodeenv.install_npm_win(env_dir, src_dir, args)

            # Verify cleanup happened
            mock_rmtree.assert_called_once()
            assert mock_remove.call_count == 2

    def test_install_npm_win_cygwin(self):
        """Test Windows npm installation on CYGWIN"""
        args = mock.Mock()
        args.npm = '7.24.2'

        env_dir = '/cygdrive/c/env'
        src_dir = '/cygdrive/c/src'

        mock_zip_content = b'PK\x03\x04...'
        mock_response = mock.Mock()
        mock_response.read.return_value = mock_zip_content

        mock_npm_script = b'#!/bin/sh\n# npm script'
        mock_npm_response = mock.Mock()
        mock_npm_response.read.return_value = mock_npm_script

        mock_zip = mock.Mock()
        mock_zip.__enter__ = mock.Mock(return_value=mock_zip)
        mock_zip.__exit__ = mock.Mock(return_value=False)

        with mock.patch.object(nodeenv, 'urlopen') as mock_urlopen, \
             mock.patch.object(nodeenv, 'is_CYGWIN', True), \
             mock.patch.object(nodeenv, 'writefile') as mock_writefile, \
             mock.patch('zipfile.ZipFile', return_value=mock_zip), \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch('shutil.copytree'), \
             mock.patch('shutil.copy'), \
             mock.patch.object(nodeenv.logger, 'info'):
            mock_urlopen.side_effect = [mock_response, mock_npm_response]

            nodeenv.install_npm_win(env_dir, src_dir, args)

            # Verify that CYGWIN-specific operations happened
            assert mock_urlopen.call_count == 2
            assert mock_writefile.called

            # Verify the raw GitHub URL was called
            calls = [str(call) for call in mock_urlopen.call_args_list]
            assert any(
                'raw.githubusercontent.com' in str(call) for call in calls
            )

    def test_install_npm_win_different_versions(self):
        """Test Windows npm installation with different version formats"""
        test_versions = ['8.0.0', '9.5.1', '10.0.0']

        for version in test_versions:
            args = mock.Mock()
            args.npm = version

            env_dir = 'C:\\env'
            src_dir = 'C:\\src'

            mock_zip_content = b'PK\x03\x04...'
            mock_response = mock.Mock()
            mock_response.read.return_value = mock_zip_content

            mock_zip = mock.Mock()
            mock_zip.__enter__ = mock.Mock(return_value=mock_zip)
            mock_zip.__exit__ = mock.Mock(return_value=False)

            with mock.patch.object(
                    nodeenv, 'urlopen', return_value=mock_response
            ) as mock_urlopen, \
                 mock.patch.object(nodeenv, 'is_CYGWIN', False), \
                 mock.patch('zipfile.ZipFile', return_value=mock_zip), \
                 mock.patch('os.path.exists', return_value=False), \
                 mock.patch('shutil.copytree'), \
                 mock.patch('shutil.copy'), \
                 mock.patch.object(nodeenv.logger, 'info'):
                nodeenv.install_npm_win(env_dir, src_dir, args)

                # Verify correct URL for each version
                expected_url = (
                    f'https://github.com/npm/cli/archive/v{version}.zip'
                )
                mock_urlopen.assert_called_with(expected_url)

    def test_install_npm_win_paths(self):
        """Test that Windows npm installation uses correct paths"""
        args = mock.Mock()
        args.npm = '8.5.0'

        env_dir = 'C:\\Users\\test\\env'
        src_dir = 'C:\\Users\\test\\src'

        mock_zip_content = b'PK\x03\x04...'
        mock_response = mock.Mock()
        mock_response.read.return_value = mock_zip_content

        mock_zip = mock.Mock()
        mock_zip.__enter__ = mock.Mock(return_value=mock_zip)
        mock_zip.__exit__ = mock.Mock(return_value=False)

        with mock.patch.object(
                nodeenv, 'urlopen', return_value=mock_response
        ), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch('zipfile.ZipFile', return_value=mock_zip), \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch('shutil.copytree') as mock_copytree, \
             mock.patch('shutil.copy') as mock_copy, \
             mock.patch.object(nodeenv.logger, 'info'):
            nodeenv.install_npm_win(env_dir, src_dir, args)

            # Verify paths
            copytree_call = mock_copytree.call_args[0]
            src_path = copytree_call[0]
            dst_path = copytree_call[1]

            assert 'cli-8.5.0' in src_path
            expected_path = os.path.join(
                env_dir, 'Scripts', 'node_modules', 'npm'
            )
            assert expected_path == dst_path

            # Verify copy calls use correct paths
            copy_calls = mock_copy.call_args_list
            assert len(copy_calls) == 2
            assert any('npm.cmd' in str(call) for call in copy_calls)
            assert any('npm-cli.js' in str(call) for call in copy_calls)

    def test_install_npm_win_zip_extraction(self):
        """Test that zip file is properly extracted"""
        args = mock.Mock()
        args.npm = '9.1.0'

        env_dir = 'C:\\test'
        src_dir = 'C:\\test\\src'

        mock_zip_content = b'PK\x03\x04...'
        mock_response = mock.Mock()
        mock_response.read.return_value = mock_zip_content

        mock_zip = mock.Mock()
        mock_zip.__enter__ = mock.Mock(return_value=mock_zip)
        mock_zip.__exit__ = mock.Mock(return_value=False)
        mock_zip.extractall = mock.Mock()

        with mock.patch.object(
                nodeenv, 'urlopen', return_value=mock_response
        ), \
             mock.patch.object(nodeenv, 'is_CYGWIN', False), \
             mock.patch(
                 'zipfile.ZipFile', return_value=mock_zip
             ) as mock_zipfile, \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch('shutil.copytree'), \
             mock.patch('shutil.copy'), \
             mock.patch.object(nodeenv.logger, 'info'):
            nodeenv.install_npm_win(env_dir, src_dir, args)

            # Verify ZipFile was created with the BytesIO content
            mock_zipfile.assert_called_once()
            zip_args = mock_zipfile.call_args[0]
            assert hasattr(zip_args[0], 'read')  # Should be BytesIO object

            # Verify extraction
            mock_zip.extractall.assert_called_once_with(src_dir)
