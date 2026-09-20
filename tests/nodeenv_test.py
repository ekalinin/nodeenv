from __future__ import absolute_import
from __future__ import unicode_literals

import sys
if sys.version_info < (3, 3):
    from pipes import quote as _quote
else:
    from shlex import quote as _quote
import io
import os.path
import pathlib
import subprocess
import sys
import sysconfig
import platform
import ssl
import zipfile

try:
    from unittest import mock
except ImportError:
    import mock
import pytest

import nodeenv
from nodeenv import IncompleteRead

HERE = os.path.abspath(os.path.dirname(__file__))

ENV_COMMANDS = ('node', 'npm', 'npx')


def _resolve_and_run(activate, command):
    """
    Source `activate`, then report where `command` resolves and what
    `command --version` prints.
    """
    script = '. {0} && command -v {1} && {1} --version'.format(
        _quote(activate), command)
    out = subprocess.check_output(['sh', '-c', script])
    lines = out.decode('utf-8').splitlines()
    assert len(lines) == 2, \
        '%s: expected a path and a version, got %r' % (command, lines)
    resolved, version = lines
    # `command -v` prints a bare name for a builtin or a shell function,
    # which os.path.realpath() would resolve against the cwd instead of
    # rejecting.  Refuse anything that is not already a path.
    assert os.path.isabs(resolved), \
        '%s resolved to %r, not an absolute path' % (command, resolved)
    return resolved, version


def _inside(path, env_dir):
    """
    Is `path` inside `env_dir`?

    Both sides are resolved first: bin/activate derives NODE_VIRTUAL_ENV
    with `cd -P`, so a tmpdir under /tmp comes back as /private/tmp on
    macOS and a plain comparison would fail.
    """
    return os.path.realpath(path).startswith(
        os.path.realpath(env_dir) + os.sep)


@pytest.mark.integration
def test_smoke(tmpdir):
    nenv_path = tmpdir.join('nenv').strpath
    subprocess.check_call([
        # Enable coverage
        'coverage', 'run', '-p',
        '-m', 'nodeenv', '--prebuilt', nenv_path,
    ])
    assert os.path.exists(nenv_path)
    if sys.platform == 'win32':
        # on Windows nodeenv installs into Scripts/ and provides
        # activate.bat/Activate.ps1, there is no posix activate script
        subprocess.check_call([
            os.path.join(nenv_path, 'Scripts', 'node.exe'), '--version',
        ])
    else:
        # `node --version` alone would pass even if activation did
        # nothing, because a system node would answer it.  Check where
        # each command resolves, not just that it runs.
        activate = os.path.join(nenv_path, 'bin', 'activate')
        for command in ENV_COMMANDS:
            resolved, version = _resolve_and_run(activate, command)
            assert _inside(resolved, nenv_path), \
                '%s resolved to %s, outside %s' % (
                    command, resolved, nenv_path)
            assert version, '%s --version printed nothing' % command


@pytest.mark.integration
@pytest.mark.skipif(sys.platform == 'win32', reason='-n system is posix only')
def test_smoke_n_system_special_chars(tmpdir):
    nenv_path = tmpdir.join('nenv (production env)').strpath
    subprocess.check_call((
        'coverage', 'run', '-p',
        '-m', 'nodeenv', '-n', 'system', nenv_path,
    ))
    assert os.path.exists(nenv_path)
    # node only: with `-n system` nodeenv writes a node shim and nothing
    # else, so npm and npx legitimately resolve outside the environment.
    # Whether `-n system` should provide them too is an open question
    # about nodeenv, so this test pins neither answer.
    activate = os.path.join(nenv_path, 'bin', 'activate')
    resolved, version = _resolve_and_run(activate, 'node')
    assert _inside(resolved, nenv_path), \
        'node resolved to %s, outside %s' % (resolved, nenv_path)
    assert version, 'node --version printed nothing'


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


@pytest.fixture
def mock_musl_platform():
    with mock.patch.object(nodeenv, 'is_x86_64_musl', return_value=True):
        with mock.patch.object(nodeenv, 'is_riscv64', return_value=False):
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

    if nodeenv.is_WIN:
        tmpdir.mkdir('Scripts')
        nodeenv.set_predeactivate_hook(tmpdir.strpath)
        # Check BAT file
        p_bat = tmpdir.join('Scripts').join('predeactivate.bat')
        assert p_bat.exists()
        content_bat = p_bat.read()
        assert 'deactivate.bat' in content_bat
        # Check PS1 file
        p_ps1 = tmpdir.join('Scripts').join('predeactivate.ps1')
        assert p_ps1.exists()
        assert 'deactivate' in p_ps1.read()
    else:
        tmpdir.mkdir('bin')
        nodeenv.set_predeactivate_hook(tmpdir.strpath)
        p = tmpdir.join('bin').join('predeactivate')
        assert 'deactivate_node' in p.read()


def test_predeactivate_hook_is_idempotent(tmpdir):
    if nodeenv.is_WIN:
        tmpdir.mkdir('Scripts')
        nodeenv.set_predeactivate_hook(tmpdir.strpath)
        nodeenv.set_predeactivate_hook(tmpdir.strpath)
        p_bat = tmpdir.join('Scripts').join('predeactivate.bat')
        assert p_bat.read() == nodeenv.PREDEACTIVATE_BAT
        p_ps1 = tmpdir.join('Scripts').join('predeactivate.ps1')
        assert p_ps1.read() == nodeenv.PREDEACTIVATE_PS1
    else:
        tmpdir.mkdir('bin')
        nodeenv.set_predeactivate_hook(tmpdir.strpath)
        nodeenv.set_predeactivate_hook(tmpdir.strpath)
        p = tmpdir.join('bin').join('predeactivate')
        assert p.read() == nodeenv.PREDEACTIVATE_SH


def _node_bin(tmpdir):
    if nodeenv.is_WIN:
        return tmpdir.mkdir('Scripts').join('node.exe')
    return tmpdir.mkdir('bin').join('node')


def test_get_installed_node_version_missing(tmpdir):
    assert nodeenv.get_installed_node_version(str(tmpdir)) is None


def test_get_installed_node_version_shim(tmpdir):
    _node_bin(tmpdir).write(nodeenv.SHIM)
    assert nodeenv.get_installed_node_version(str(tmpdir)) is None


def test_get_installed_node_version_binary(tmpdir):
    _node_bin(tmpdir).write_binary(b'\x7fELF fake node binary')
    proc = mock.Mock()
    proc.communicate.return_value = (b'v26.9.0\n', b'')
    with mock.patch.object(nodeenv.subprocess, 'Popen', return_value=proc):
        assert nodeenv.get_installed_node_version(str(tmpdir)) == (26, 9, 0)


def _make_opts(extra):
    with mock.patch.object(sys, 'argv', ['nodeenv'] + extra):
        return nodeenv.parse_args()


def _count_install_node(tmpdir, opts, installed):
    with mock.patch.object(nodeenv, 'install_node') as install_node, \
            mock.patch.object(nodeenv, 'install_activate'), \
            mock.patch.object(nodeenv, 'install_npm'), \
            mock.patch.object(nodeenv, 'install_npm_win'), \
            mock.patch.object(nodeenv, 'set_predeactivate_hook'), \
            mock.patch.object(nodeenv, 'get_installed_node_version',
                              return_value=installed):
        nodeenv.create_environment(str(tmpdir), opts)
    return install_node.call_count


def test_create_environment_skips_installed_node(tmpdir):
    opts = _make_opts(['--node', '26.9.0', '-p'])
    assert _count_install_node(tmpdir, opts, (26, 9, 0)) == 0


def test_create_environment_installs_other_version(tmpdir):
    opts = _make_opts(['--node', '26.9.0', '-p'])
    assert _count_install_node(tmpdir, opts, (24, 0, 0)) == 1


def test_create_environment_installs_when_absent(tmpdir):
    opts = _make_opts(['--node', '26.9.0', '-p'])
    assert _count_install_node(tmpdir, opts, None) == 1


def test_create_environment_force_reinstalls_node(tmpdir):
    opts = _make_opts(['--node', '26.9.0', '-p', '--force'])
    assert _count_install_node(tmpdir, opts, (26, 9, 0)) == 1


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


def test_mirror_option_local_directory(tmpdir):
    """A local directory is a valid mirror, see #193"""
    tmpdir.join('index.json').write(
        '[{"version": "v99.0.0", "date": "2026-01-01", "lts": false,'
        ' "files": ["linux-x64", "linux-x64-musl", "linux-riscv64"]}]')
    mirror = pathlib.Path(str(tmpdir)).as_uri()
    argv = [__file__, '--list', '--mirror=' + mirror]
    with mock.patch.object(sys, 'argv', argv), \
            mock.patch.object(nodeenv.logger, 'info') as mock_logger:
        nodeenv.src_base_url = None
        nodeenv.main()
        mock_logger.assert_called_with('99.0.0')


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


@pytest.mark.usefixtures('mock_index_json', 'mock_host_platform')
def test_get_last_node_version_writes_nothing_to_stdout(capsys):
    nodeenv.get_last_stable_node_version()
    assert capsys.readouterr().out == ''


def test__download_node_file():
    with mock.patch.object(nodeenv, 'urlopen') as m_urlopen:
        m_urlopen.side_effect = IncompleteRead("dummy")
        with pytest.raises(IncompleteRead):
            nodeenv._download_node_file(
                "https://dummy/nodejs.tar.gz",
                n_attempt=5
            )
        assert m_urlopen.call_count == 5


def _zip_with_node(node_version):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('node-v%s-win-x64/README.md' % node_version, 'readme')
        zf.writestr('node-v%s-win-x64/node.exe' % node_version, 'binary')
    return io.BytesIO(buf.getvalue())


def test_download_node_src_zip(tmpdir):
    """On Windows the archive is a zip, which has no extractall(filter=...)"""
    class args:
        node = '22.14.0'

    with mock.patch.object(nodeenv, 'is_WIN', True), \
            mock.patch.object(nodeenv, '_download_node_file',
                              return_value=_zip_with_node(args.node)):
        nodeenv.download_node_src('https://dummy/node.zip',
                                  tmpdir.strpath, args)

    node_dir = os.path.join(tmpdir.strpath, 'node-v22.14.0-win-x64')
    assert os.path.exists(os.path.join(node_dir, 'node.exe'))
    # docs are excluded from the extract list
    assert not os.path.exists(os.path.join(node_dir, 'README.md'))


def test_download_node_src_tar_keeps_data_filter(tmpdir):
    """The tar path must keep filter='data' (CVE-2007-4559 protection)"""
    class args:
        node = '22.14.0'

    archive = mock.MagicMock()
    archive.__enter__.return_value = archive
    archive.getmembers.return_value = []
    with mock.patch.object(nodeenv, 'is_WIN', False), \
            mock.patch.object(nodeenv, 'is_CYGWIN', False), \
            mock.patch.object(nodeenv, 'tarfile_open', return_value=archive), \
            mock.patch.object(nodeenv, '_download_node_file',
                              return_value=io.BytesIO(b'')):
        nodeenv.download_node_src('https://dummy/node.tar.gz',
                                  tmpdir.strpath, args)

    if sys.version_info >= (3, 12):
        archive.extractall.assert_called_once_with(
            tmpdir.strpath, [], filter="data")
    else:
        archive.extractall.assert_called_once_with(tmpdir.strpath, [])


def test_parse_version():
    assert nodeenv.parse_version("v21.7") == (21, 7)
    assert nodeenv.parse_version("v21.7.3") == (21, 7, 3)
    assert nodeenv.parse_version("v21.7.3+0-b20240228T18452699") == (21, 7, 3)


def test_pad_version():
    assert nodeenv._pad_version((4,)) == (4, 0, 0)
    assert nodeenv._pad_version((4, 3)) == (4, 3, 0)
    assert nodeenv._pad_version((4, 3, 1)) == (4, 3, 1)


@pytest.mark.parametrize(
    ('spec', 'expected'),
    (
        ('22', [[('>=', (22, 0, 0)), ('<', (23, 0, 0))]]),
        ('21.7', [[('>=', (21, 7, 0)), ('<', (21, 8, 0))]]),
        ('4.x', [[('>=', (4, 0, 0)), ('<', (5, 0, 0))]]),
        ('4.*', [[('>=', (4, 0, 0)), ('<', (5, 0, 0))]]),
        ('*', [[]]),
        ('^4.3.1', [[('>=', (4, 3, 1)), ('<', (5, 0, 0))]]),
        ('^0.4.3', [[('>=', (0, 4, 3)), ('<', (0, 5, 0))]]),
        ('^0.0.3', [[('>=', (0, 0, 3)), ('<', (0, 0, 4))]]),
        ('^0.x', [[('>=', (0, 0, 0)), ('<', (1, 0, 0))]]),
        ('^0.0.x', [[('>=', (0, 0, 0)), ('<', (0, 1, 0))]]),
        ('~4.3.1', [[('>=', (4, 3, 1)), ('<', (4, 4, 0))]]),
        ('~4.3', [[('>=', (4, 3, 0)), ('<', (4, 4, 0))]]),
        ('~4', [[('>=', (4, 0, 0)), ('<', (5, 0, 0))]]),
        ('>=20.0.0', [[('>=', (20, 0, 0))]]),
        ('>=20', [[('>=', (20, 0, 0))]]),
        ('<21.0.0', [[('<', (21, 0, 0))]]),
        ('>4.3', [[('>=', (4, 4, 0))]]),
        ('>4', [[('>=', (5, 0, 0))]]),
        ('<=4.3', [[('<', (4, 4, 0))]]),
        ('<=4.3.1', [[('<=', (4, 3, 1))]]),
        ('=22.11.0', [[('>=', (22, 11, 0)), ('<=', (22, 11, 0))]]),
        ('>=20 <22', [[('>=', (20, 0, 0)), ('<', (22, 0, 0))]]),
        ('4 - 6', [[('>=', (4, 0, 0)), ('<', (7, 0, 0))]]),
        ('4.3.1 - 6.2.0', [[('>=', (4, 3, 1)), ('<=', (6, 2, 0))]]),
        (
            '8 || 10',
            [
                [('>=', (8, 0, 0)), ('<', (9, 0, 0))],
                [('>=', (10, 0, 0)), ('<', (11, 0, 0))],
            ],
        ),
    ),
)
def test_parse_node_range(spec, expected):
    assert nodeenv.parse_node_range(spec) == expected


@pytest.mark.parametrize(
    'spec',
    (
        '', 'abc', 'system', 'latest', 'lts', '1.2.3.4', '>=', 'v', '4-6',
        '4 - 6 - 8', '>=20 <abc', '23.0.0-nightly20240101abcdef',
    ),
)
def test_parse_node_range_invalid(spec):
    assert nodeenv.parse_node_range(spec) is None


@pytest.mark.parametrize(
    ('spec', 'expected'),
    (
        ('22.11.0', True),
        ('v22.11.0', True),
        ('0.10.48', True),
        ('21.7.3+0-b20240228T18452699', True),
        ('22', False),
        ('22.11', False),
        ('^22.11.0', False),
        ('latest', False),
        ('system', False),
        ('23.0.0-nightly20240101abcdef', False),
    ),
)
def test_is_exact_version(spec, expected):
    assert nodeenv._is_exact_version(spec) is expected


@pytest.mark.parametrize(
    ('spec', 'version', 'expected'),
    (
        ('^4.3.1', (4, 3, 1), True),
        ('^4.3.1', (4, 9, 1), True),
        ('^4.3.1', (4, 3, 0), False),
        ('^4.3.1', (5, 0, 0), False),
        ('~4.3.1', (4, 3, 9), True),
        ('~4.3.1', (4, 4, 0), False),
        ('4.x', (4, 0, 0), True),
        ('4.x', (3, 9, 9), False),
        ('*', (0, 1, 14), True),
        ('>=20 <22', (21, 5, 0), True),
        ('>=20 <22', (22, 0, 0), False),
        ('>=20 <22', (19, 9, 9), False),
        ('8 || 10', (8, 1, 0), True),
        ('8 || 10', (10, 1, 0), True),
        ('8 || 10', (9, 1, 0), False),
        ('4 - 6', (6, 17, 1), True),
        ('4 - 6', (7, 0, 0), False),
        ('4.3.1 - 6.2.0', (6, 2, 0), True),
        ('4.3.1 - 6.2.0', (6, 2, 1), False),
        ('>4.3', (4, 4, 0), True),
        ('>4.3', (4, 3, 9), False),
        ('22', (22, 0, 0), True),
        # a two-part version tuple is padded before comparing
        ('~4.3', (4, 3), True),
    ),
)
def test_match_node_range(spec, version, expected):
    ranges = nodeenv.parse_node_range(spec)
    assert nodeenv.match_node_range(version, ranges) is expected


@pytest.mark.usefixtures('mock_index_json', 'mock_host_platform')
@pytest.mark.parametrize(
    ('spec', 'expected'),
    (
        ('4.x', '4.9.1'),
        ('^4.3.1', '4.9.1'),
        ('~4.3.1', '4.3.2'),
        ('>=10 <12', '11.15.0'),
        ('0.10', '0.10.48'),
        ('^0.4.3', '0.4.12'),
        ('8 || 10', '10.18.0'),
        ('4 - 6', '6.17.1'),
        ('>4.3', '13.5.0'),
        ('*', '13.5.0'),
    ),
)
def test_resolve_node_version(spec, expected):
    assert nodeenv.resolve_node_version(spec) == expected


@pytest.mark.usefixtures('mock_index_json', 'mock_host_platform')
def test_resolve_node_version_no_match():
    # the fixture index has no 0.0.x releases
    with pytest.raises(SystemExit) as excinfo:
        nodeenv.resolve_node_version('^0.0.3')
    assert excinfo.value.code == 1


@pytest.mark.parametrize('spec', ('abc', '23.0.0-nightly20240101abcdef'))
def test_resolve_node_version_passes_through_non_ranges(spec):
    # no index fixture: a non-range must not hit the network at all
    with mock.patch.object(nodeenv, 'urlopen') as mck:
        assert nodeenv.resolve_node_version(spec) == spec
    assert mck.call_count == 0


@pytest.mark.usefixtures('mock_index_json', 'mock_musl_platform')
def test_resolve_node_version_skips_versions_without_platform_build():
    # no release in the fixture index ships a linux-x64-musl build
    with pytest.raises(SystemExit) as excinfo:
        nodeenv.resolve_node_version('4.x')
    assert excinfo.value.code == 1


@pytest.mark.usefixtures('mock_host_platform')
def test_has_platform_build_without_special_platform():
    assert nodeenv._has_platform_build({'files': []}) is True


@pytest.mark.usefixtures('mock_musl_platform')
def test_has_platform_build_musl():
    assert nodeenv._has_platform_build({'files': []}) is False
    assert nodeenv._has_platform_build(
        {'files': ['linux-x64-musl']}) is True


@pytest.mark.usefixtures('mock_riscv64_platform')
def test_has_platform_build_riscv64():
    assert nodeenv._has_platform_build({'files': []}) is False
    assert nodeenv._has_platform_build({'files': ['linux-riscv64']}) is True


def _run_main_resolving(argv):
    """
    Run main() far enough to resolve args.node, then stop
    """
    with mock.patch.object(sys, 'argv', ['nodeenv'] + argv):
        with mock.patch.object(
                nodeenv, 'create_environment') as create_environment:
            nodeenv.main()
    assert create_environment.call_count == 1
    return create_environment.call_args[0][1].node


@pytest.mark.usefixtures('mock_index_json', 'mock_host_platform')
def test_main_resolves_range():
    assert _run_main_resolving(['--node', '4.x', 'env']) == '4.9.1'


@pytest.mark.usefixtures('mock_host_platform')
def test_main_keeps_exact_version_without_network():
    with mock.patch.object(nodeenv, 'urlopen') as mck:
        assert _run_main_resolving(['--node', '22.11.0', 'env']) == '22.11.0'
    assert mck.call_count == 0


@pytest.mark.usefixtures('mock_host_platform')
def test_main_keeps_unparseable_version_without_network():
    version = '23.0.0-nightly20240101abcdef'
    with mock.patch.object(nodeenv, 'urlopen') as mck:
        assert _run_main_resolving(['--node', version, 'env']) == version
    assert mck.call_count == 0


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
def test_main_keeps_system_without_network():
    with mock.patch.object(nodeenv, 'urlopen') as mck:
        assert _run_main_resolving(['--node', 'system', 'env']) == 'system'
    assert mck.call_count == 0


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
def test_find_system_node_prefers_nodejs():
    def fake_which(cmd, path=None):
        return {'nodejs': '/usr/bin/nodejs', 'node': '/usr/bin/node'}[cmd]

    with mock.patch('shutil.which', side_effect=fake_which):
        assert nodeenv.find_system_node('/env/bin') == '/usr/bin/nodejs'


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
def test_find_system_node_falls_back_to_node():
    def fake_which(cmd, path=None):
        return {'nodejs': None, 'node': '/usr/bin/node'}[cmd]

    with mock.patch('shutil.which', side_effect=fake_which):
        assert nodeenv.find_system_node('/env/bin') == '/usr/bin/node'


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
def test_find_system_node_not_found():
    with mock.patch('shutil.which', return_value=None):
        assert nodeenv.find_system_node('/env/bin') is None


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
def test_find_system_node_skips_env_bin_dir():
    with mock.patch.dict(os.environ, {'PATH': '/env/bin:/usr/bin'}), \
         mock.patch('shutil.which', return_value='/usr/bin/node') as m_which:
        nodeenv.find_system_node('/env/bin')

    assert m_which.call_args[1]['path'] == '/usr/bin'


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
def test_find_system_node_without_env_bin_dir_keeps_path():
    with mock.patch.dict(os.environ, {'PATH': '/env/bin:/usr/bin'}), \
         mock.patch('shutil.which', return_value='/usr/bin/node') as m_which:
        assert nodeenv.find_system_node() == '/usr/bin/node'

    assert m_which.call_args[1]['path'] == '/env/bin:/usr/bin'


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
def test_node_version_from_args_system_uses_found_executable():
    args = mock.Mock(node='system')
    with mock.patch.object(nodeenv, 'find_system_node',
                           return_value='/usr/bin/nodejs'), \
         mock.patch.object(nodeenv.subprocess, 'Popen') as m_popen:
        m_popen.return_value.communicate.return_value = (b'v22.11.0\n', b'')
        assert nodeenv.node_version_from_args(args) == (22, 11, 0)

    assert m_popen.call_args[0][0] == ['/usr/bin/nodejs', '--version']


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
def test_node_version_from_args_system_falls_back_to_node():
    args = mock.Mock(node='system')
    with mock.patch.object(nodeenv, 'find_system_node', return_value=None), \
         mock.patch.object(nodeenv.subprocess, 'Popen') as m_popen:
        m_popen.return_value.communicate.return_value = (b'v22.11.0\n', b'')
        nodeenv.node_version_from_args(args)

    assert m_popen.call_args[0][0] == ['node', '--version']


def test_prefer_system_default():
    assert nodeenv.Config._default['prefer_system'] is False


def test_prefer_system_is_configurable(tmpdir):
    rc = tmpdir.join('nodeenvrc')
    rc.write('[nodeenv]\nprefer_system = true\n')
    try:
        nodeenv.Config._load([str(rc)])
        assert nodeenv.Config.prefer_system is True
    finally:
        nodeenv.Config.prefer_system = False


def test_parse_args_prefer_system():
    with mock.patch.object(
            sys, 'argv', ['nodeenv', '--prefer-system', 'env']):
        assert nodeenv.parse_args().prefer_system is True
    with mock.patch.object(sys, 'argv', ['nodeenv', 'env']):
        assert nodeenv.parse_args().prefer_system is False


def test_parse_args_python_virtualenv():
    with mock.patch.object(sys, 'argv', ['nodeenv', '-p']):
        assert nodeenv.parse_args().python_virtualenv is True
    with mock.patch.object(sys, 'argv', ['nodeenv', '-p', 'venv']):
        assert nodeenv.parse_args().python_virtualenv == 'venv'
    with mock.patch.object(
            sys, 'argv', ['nodeenv', '--python-virtualenv=venv']):
        assert nodeenv.parse_args().python_virtualenv == 'venv'
    with mock.patch.object(sys, 'argv', ['nodeenv', 'env']):
        assert nodeenv.parse_args().python_virtualenv is False


def test_isolate_npm_default():
    assert nodeenv.Config._default['isolate_npm'] is False


def test_isolate_npm_is_configurable(tmpdir):
    rc = tmpdir.join('nodeenvrc')
    rc.write('[nodeenv]\nisolate_npm = true\n')
    try:
        nodeenv.Config._load([str(rc)])
        assert nodeenv.Config.isolate_npm is True
    finally:
        nodeenv.Config.isolate_npm = False


def test_parse_args_isolate_npm():
    with mock.patch.object(
            sys, 'argv', ['nodeenv', '--isolate-npm', 'env']):
        assert nodeenv.parse_args().isolate_npm is True
    with mock.patch.object(sys, 'argv', ['nodeenv', 'env']):
        assert nodeenv.parse_args().isolate_npm is False


def test_clean_src_default():
    assert nodeenv.Config._default['clean_src'] is True


def test_clean_src_is_configurable(tmpdir):
    rc = tmpdir.join('nodeenvrc')
    rc.write('[nodeenv]\nclean_src = false\n')
    try:
        nodeenv.Config._load([str(rc)])
        assert nodeenv.Config.clean_src is False
    finally:
        nodeenv.Config.clean_src = True


def test_parse_args_clean_src():
    with mock.patch.object(sys, 'argv', ['nodeenv', 'env']):
        assert nodeenv.parse_args().clean_src is True
    # still accepted, pre-commit passes it explicitly
    with mock.patch.object(sys, 'argv', ['nodeenv', '-c', 'env']):
        assert nodeenv.parse_args().clean_src is True
    with mock.patch.object(sys, 'argv', ['nodeenv', '--no-clean-src', 'env']):
        assert nodeenv.parse_args().clean_src is False


def _run_create_environment(tmpdir, extra):
    """
    Run create_environment() in tmpdir without installing anything
    """
    argv = ['nodeenv', '--node', '26.9.0', '-p'] + extra
    with mock.patch.object(sys, 'argv', argv):
        args = nodeenv.parse_args()
    with mock.patch.object(nodeenv, 'install_node'), \
            mock.patch.object(nodeenv, 'install_activate'), \
            mock.patch.object(nodeenv, 'set_predeactivate_hook'):
        nodeenv.create_environment(str(tmpdir), args)


def test_create_environment_cleans_src_by_default(tmpdir):
    _run_create_environment(tmpdir, [])
    assert not tmpdir.join('src').check()


def test_create_environment_keeps_src_when_asked(tmpdir):
    _run_create_environment(tmpdir, ['--no-clean-src'])
    assert tmpdir.join('src').check(dir=True)


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
@pytest.mark.usefixtures('mock_host_platform')
def test_main_prefer_system_uses_system_node(cap_logging_info):
    with mock.patch('shutil.which', return_value='/usr/bin/node'), \
         mock.patch.object(nodeenv, 'urlopen') as m_urlopen:
        assert _run_main_resolving(['--prefer-system', 'env']) == 'system'
    assert m_urlopen.call_count == 0
    cap_logging_info.assert_any_call(' * Using system node: /usr/bin/node')


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
@pytest.mark.usefixtures('mock_host_platform')
def test_main_prefer_system_installs_when_missing(cap_logging_info):
    with mock.patch('shutil.which', return_value=None), \
         mock.patch.object(nodeenv, 'urlopen') as m_urlopen:
        assert _run_main_resolving(
            ['--prefer-system', '--node', '22.11.0', 'env']) == '22.11.0'
    assert m_urlopen.call_count == 0
    cap_logging_info.assert_any_call(
        ' * System node not found, installing 22.11.0')


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
@pytest.mark.usefixtures('mock_index_json', 'mock_host_platform')
def test_main_prefer_system_resolves_range_when_missing():
    with mock.patch('shutil.which', return_value=None):
        assert _run_main_resolving(
            ['--prefer-system', '--node', '4.x', 'env']) == '4.9.1'


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
def test_main_prefer_system_keeps_explicit_system():
    with mock.patch('shutil.which', return_value=None), \
         mock.patch.object(nodeenv, 'urlopen') as m_urlopen:
        assert _run_main_resolving(
            ['--prefer-system', '--node', 'system', 'env']) == 'system'
    assert m_urlopen.call_count == 0


@pytest.mark.usefixtures('mock_host_platform')
def test_main_prefer_system_ignored_on_windows():
    with mock.patch.object(nodeenv, 'is_WIN', True), \
         mock.patch('shutil.which', return_value='/usr/bin/node'), \
         mock.patch.object(nodeenv, 'urlopen') as m_urlopen, \
         mock.patch.object(nodeenv.logger, 'warning') as m_warning:
        assert _run_main_resolving(
            ['--prefer-system', '--node', '22.11.0', 'env']) == '22.11.0'
    assert m_urlopen.call_count == 0
    assert '--prefer-system is not supported on win32' in \
        m_warning.call_args[0][0]


@pytest.mark.usefixtures('mock_host_platform')
def test_main_isolate_npm_ignored_on_windows():
    with mock.patch.object(nodeenv, 'is_WIN', True), \
         mock.patch.object(nodeenv, 'urlopen') as m_urlopen, \
         mock.patch.object(nodeenv.logger, 'warning') as m_warning:
        assert _run_main_resolving(
            ['--isolate-npm', '--node', '22.11.0', 'env']) == '22.11.0'
    assert m_urlopen.call_count == 0
    assert '--isolate-npm is not supported on win32' in \
        m_warning.call_args[0][0]


@pytest.mark.usefixtures('mock_host_platform')
def test_main_isolate_npm_silent_on_posix():
    with mock.patch.object(nodeenv, 'is_WIN', False), \
         mock.patch.object(nodeenv, 'urlopen') as m_urlopen, \
         mock.patch.object(nodeenv.logger, 'warning') as m_warning:
        assert _run_main_resolving(
            ['--isolate-npm', '--node', '22.11.0', 'env']) == '22.11.0'
    assert m_urlopen.call_count == 0
    assert not any(
        '--isolate-npm' in call[0][0]
        for call in m_warning.call_args_list)


@pytest.mark.usefixtures('mock_host_platform')
def test_main_isolate_npm_no_warning_with_list():
    with mock.patch.object(
            sys, 'argv',
            ['nodeenv', '--isolate-npm', '--node', '22.11.0', '--list']), \
         mock.patch.object(nodeenv, 'is_WIN', True), \
         mock.patch.object(nodeenv, 'print_node_versions') as m_list, \
         mock.patch.object(nodeenv.logger, 'warning') as m_warning:
        nodeenv.main()
    assert m_list.call_count == 1
    assert not any(
        '--isolate-npm' in call[0][0]
        for call in m_warning.call_args_list)


def test_main_prefer_system_ignored_with_list():
    with mock.patch.object(
            sys, 'argv',
            ['nodeenv', '--prefer-system', '--node', '22.11.0', '--list']), \
         mock.patch('shutil.which', return_value='/usr/bin/node') as m_which, \
         mock.patch.object(nodeenv, 'print_node_versions') as m_list:
        nodeenv.main()
    assert m_list.call_count == 1
    assert m_which.call_count == 0


def test_clear_output():
    assert nodeenv.clear_output(
        bytes('some \ntext', 'utf-8')) == 'some text'


@pytest.mark.parametrize(
    ('path', 'env_bin_dir', 'expected'),
    (
        ('//home://home/env/bin://home/bin', '//home/env/bin',
         '//home://home/bin'),
        ('/usr/bin:/x/env/bin', '/x/env/bin', '/usr/bin'),
        ('/x/env/bin', '/x/env/bin', ''),
    ),
)
def test_remove_env_bin_from_path(path, env_bin_dir, expected):
    assert nodeenv.remove_env_bin_from_path(path, env_bin_dir) == expected


@pytest.mark.skipif(nodeenv.is_WIN, reason='-n system is posix only')
def test_remove_env_bin_from_path_relative_env_dir():
    abs_bin_dir = os.path.join(os.getcwd(), 'env', 'bin')
    assert nodeenv.remove_env_bin_from_path(
        abs_bin_dir + ':/usr/bin', 'env/bin') == '/usr/bin'


@pytest.mark.skipif(nodeenv.is_WIN, reason='symlinks need privileges on win32')
def test_remove_env_bin_from_path_symlinked_env_dir(tmpdir):
    real_bin_dir = tmpdir.mkdir('real').mkdir('bin')
    os.symlink(str(tmpdir.join('real')), str(tmpdir.join('link')))
    assert nodeenv.remove_env_bin_from_path(
        str(tmpdir.join('link', 'bin')) + ':/usr/bin',
        str(real_bin_dir)) == '/usr/bin'


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
            ('i86pc', 'x64'),
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


class TestInstallNode:
    """Tests for install_node and install_node_wrapped functions"""

    def test_install_node_wrapped_success(self, tmpdir):
        """Test successful Node.js installation"""
        args = mock.Mock()
        args.node = '18.0.0'
        args.prebuilt = True
        args.verbose = False

        env_dir = tmpdir.join('env').strpath
        src_dir = tmpdir.join('src').strpath
        os.makedirs(src_dir)

        bin_url = (
            'https://nodejs.org/download/release/v18.0.0/'
            'node-v18.0.0-linux-x64.tar.gz'
        )
        with mock.patch.object(
                nodeenv, 'get_node_bin_url',
                return_value=bin_url
        ), \
             mock.patch.object(
                 nodeenv, 'download_node_src'
             ) as mock_download, \
             mock.patch.object(
                 nodeenv, 'copy_node_from_prebuilt'
             ) as mock_copy, \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch.object(nodeenv.logger, 'info'):
            nodeenv.install_node_wrapped(env_dir, src_dir, args)

            # Verify download was called
            mock_download.assert_called_once_with(
                bin_url,
                src_dir,
                args
            )

            # Verify copy was called
            mock_copy.assert_called_once_with(env_dir, src_dir, '18.0.0')

    def test_install_node_wrapped_from_source(self, tmpdir):
        """Test Node.js installation from source"""
        args = mock.Mock()
        args.node = '18.0.0'
        args.prebuilt = False
        args.verbose = False

        env_dir = tmpdir.join('env').strpath
        src_dir = tmpdir.join('src').strpath
        os.makedirs(src_dir)

        node_src_dir = os.path.join(src_dir, 'node-v18.0.0')

        src_url = (
            'https://nodejs.org/download/release/v18.0.0/'
            'node-v18.0.0.tar.gz'
        )
        with mock.patch.object(
                nodeenv, 'get_node_src_url',
                return_value=src_url
        ), \
             mock.patch.object(
                 nodeenv, 'download_node_src'
             ) as mock_download, \
             mock.patch.object(
                 nodeenv, 'build_node_from_src'
             ) as mock_build, \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch.object(nodeenv.logger, 'info'):
            nodeenv.install_node_wrapped(env_dir, src_dir, args)

            # Verify download was called with source URL
            mock_download.assert_called_once_with(
                src_url,
                src_dir,
                args
            )

            # Verify build was called instead of copy
            mock_build.assert_called_once_with(
                env_dir, src_dir, node_src_dir, args
            )

    def test_install_node_wrapped_arm64_fallback_to_x64(self, tmpdir):
        """Test arm64 fallback to x64 when arm64 is not available"""
        args = mock.Mock()
        args.node = '16.0.0'
        args.prebuilt = True
        args.verbose = False

        env_dir = tmpdir.join('env').strpath
        src_dir = tmpdir.join('src').strpath
        os.makedirs(src_dir)

        arm64_url = (
            'https://nodejs.org/download/release/v16.0.0/'
            'node-v16.0.0-darwin-arm64.tar.gz'
        )

        # Mock HTTPError for arm64 URL
        def download_side_effect(url, src_dir, args):
            if 'arm64' in url:
                raise nodeenv.urllib2.HTTPError(
                    url, 404, 'Not Found', {}, None
                )
            # x64 download succeeds
            return None

        with mock.patch.object(
                nodeenv, 'get_node_bin_url',
                return_value=arm64_url
        ), \
             mock.patch.object(
                 nodeenv, 'download_node_src',
                 side_effect=download_side_effect
             ) as mock_download, \
             mock.patch.object(
                 nodeenv, 'copy_node_from_prebuilt'
             ) as mock_copy, \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch.object(nodeenv.logger, 'info'), \
             mock.patch.object(nodeenv.logger, 'warning'):
            nodeenv.install_node_wrapped(env_dir, src_dir, args)

            # Verify download was called twice: first with arm64, then with x64
            assert mock_download.call_count == 2
            calls = mock_download.call_args_list
            assert 'arm64' in calls[0][0][0]
            assert 'x64' in calls[1][0][0]

            # Verify copy was called after successful x64 download
            mock_copy.assert_called_once()

    def test_install_node_wrapped_http_error_non_arm64(self, tmpdir):
        """Test that HTTPError is re-raised for non-arm64 URLs"""
        args = mock.Mock()
        args.node = '18.0.0'
        args.prebuilt = True
        args.verbose = False

        env_dir = tmpdir.join('env').strpath
        src_dir = tmpdir.join('src').strpath
        os.makedirs(src_dir)

        x64_url = (
            'https://nodejs.org/download/release/v18.0.0/'
            'node-v18.0.0-linux-x64.tar.gz'
        )

        # Mock HTTPError for x64 URL (no arm64 fallback should happen)
        def download_side_effect(url, src_dir, args):
            raise nodeenv.urllib2.HTTPError(
                url, 404, 'Not Found', {}, None
            )

        with mock.patch.object(
                nodeenv, 'get_node_bin_url',
                return_value=x64_url
        ), \
             mock.patch.object(
                 nodeenv, 'download_node_src',
                 side_effect=download_side_effect
             ) as mock_download, \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch.object(nodeenv.logger, 'info'), \
             mock.patch.object(nodeenv.logger, 'warning') as mock_warning, \
             pytest.raises(nodeenv.urllib2.HTTPError):
            nodeenv.install_node_wrapped(env_dir, src_dir, args)

            # Verify warning was logged
            mock_warning.assert_called_once()
            warning_call = mock_warning.call_args[0][0]
            assert 'Failed to download' in warning_call
            assert x64_url in warning_call

            # Verify download was called only once (no fallback for x64)
            mock_download.assert_called_once()

    def test_install_node_wrapped_skips_download_if_exists(self, tmpdir):
        """Test that download is skipped if node source dir exists"""
        args = mock.Mock()
        args.node = '18.0.0'
        args.prebuilt = True
        args.verbose = False

        env_dir = tmpdir.join('env').strpath
        src_dir = tmpdir.join('src').strpath
        os.makedirs(src_dir)

        node_src_dir = os.path.join(src_dir, 'node-v18.0.0')
        os.makedirs(node_src_dir)

        bin_url = (
            'https://nodejs.org/download/release/v18.0.0/'
            'node-v18.0.0-linux-x64.tar.gz'
        )
        with mock.patch.object(
                nodeenv, 'get_node_bin_url',
                return_value=bin_url
        ), \
             mock.patch.object(
                 nodeenv, 'download_node_src'
             ) as mock_download, \
             mock.patch.object(
                 nodeenv, 'copy_node_from_prebuilt'
             ) as mock_copy, \
             mock.patch.object(nodeenv.logger, 'info'):
            nodeenv.install_node_wrapped(env_dir, src_dir, args)

            # Verify download was NOT called
            mock_download.assert_not_called()

            # Verify copy was still called
            mock_copy.assert_called_once()

    def test_install_node_restores_newline_on_exception(self, tmpdir):
        """Test that install_node restores newline on exception"""
        args = mock.Mock()
        args.node = '18.0.0'
        args.prebuilt = True

        env_dir = tmpdir.join('env').strpath
        src_dir = tmpdir.join('src').strpath

        with mock.patch.object(
                nodeenv, 'install_node_wrapped',
                side_effect=RuntimeError('Test error')
        ), \
             mock.patch.object(nodeenv.logger, 'info') as mock_logger, \
             pytest.raises(RuntimeError):
            nodeenv.install_node(env_dir, src_dir, args)

            # Verify that empty string was logged to restore newline
            calls = [call[0][0] for call in mock_logger.call_args_list]
            assert '' in calls

    def test_install_node_wrapped_prebuilt_vs_source_urls(self, tmpdir):
        """Test that correct URL getter is used for prebuilt vs source"""
        args = mock.Mock()
        args.node = '18.0.0'
        args.verbose = False

        env_dir = tmpdir.join('env').strpath
        src_dir = tmpdir.join('src').strpath
        os.makedirs(src_dir)

        # Test prebuilt
        args.prebuilt = True
        with mock.patch.object(
                nodeenv, 'get_node_bin_url',
                return_value='bin_url'
        ) as mock_bin_url, \
             mock.patch.object(
                 nodeenv, 'get_node_src_url'
             ) as mock_src_url, \
             mock.patch.object(
                 nodeenv, 'download_node_src'
             ), \
             mock.patch.object(
                 nodeenv, 'copy_node_from_prebuilt'
             ), \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch.object(nodeenv.logger, 'info'):
            nodeenv.install_node_wrapped(env_dir, src_dir, args)
            mock_bin_url.assert_called_once()
            mock_src_url.assert_not_called()

        # Test source
        args.prebuilt = False
        with mock.patch.object(
                nodeenv, 'get_node_bin_url'
        ) as mock_bin_url, \
             mock.patch.object(
                 nodeenv, 'get_node_src_url',
                 return_value='src_url'
             ) as mock_src_url, \
             mock.patch.object(
                 nodeenv, 'download_node_src'
             ), \
             mock.patch.object(
                 nodeenv, 'build_node_from_src'
             ), \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch.object(nodeenv.logger, 'info'):
            nodeenv.install_node_wrapped(env_dir, src_dir, args)
            mock_src_url.assert_called_once()
            mock_bin_url.assert_not_called()

    def test_install_node_wrapped_arm64_fallback_both_fail(self, tmpdir):
        """Test that both arm64 and x64 failures raise exception"""
        args = mock.Mock()
        args.node = '16.0.0'
        args.prebuilt = True
        args.verbose = False

        env_dir = tmpdir.join('env').strpath
        src_dir = tmpdir.join('src').strpath
        os.makedirs(src_dir)

        arm64_url = (
            'https://nodejs.org/download/release/v16.0.0/'
            'node-v16.0.0-darwin-arm64.tar.gz'
        )

        # Both arm64 and x64 downloads fail
        def download_side_effect(url, src_dir, args):
            raise nodeenv.urllib2.HTTPError(
                url, 404, 'Not Found', {}, None
            )

        with mock.patch.object(
                nodeenv, 'get_node_bin_url',
                return_value=arm64_url
        ), \
             mock.patch.object(
                 nodeenv, 'download_node_src',
                 side_effect=download_side_effect
             ) as mock_download, \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch.object(nodeenv.logger, 'info'), \
             pytest.raises(nodeenv.urllib2.HTTPError):
            nodeenv.install_node_wrapped(env_dir, src_dir, args)

            # Both arm64 and x64 should have been tried
            assert mock_download.call_count == 2

    def test_install_node_wrapped_no_copy_after_download_failure(
        self, tmpdir
    ):
        """Test copy_node_from_prebuilt not called after failure"""
        args = mock.Mock()
        args.node = '18.0.0'
        args.prebuilt = True
        args.verbose = False

        env_dir = tmpdir.join('env').strpath
        src_dir = tmpdir.join('src').strpath
        os.makedirs(src_dir)

        x64_url = (
            'https://nodejs.org/download/release/v18.0.0/'
            'node-v18.0.0-linux-x64.tar.gz'
        )

        # Download fails
        def download_side_effect(url, src_dir, args):
            raise nodeenv.urllib2.HTTPError(
                url, 404, 'Not Found', {}, None
            )

        with mock.patch.object(
                nodeenv, 'get_node_bin_url',
                return_value=x64_url
        ), \
             mock.patch.object(
                 nodeenv, 'download_node_src',
                 side_effect=download_side_effect
             ), \
             mock.patch.object(
                 nodeenv, 'copy_node_from_prebuilt'
             ) as mock_copy, \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch.object(nodeenv.logger, 'info'), \
             mock.patch.object(nodeenv.logger, 'warning'), \
             pytest.raises(nodeenv.urllib2.HTTPError):
            nodeenv.install_node_wrapped(env_dir, src_dir, args)

            # Verify copy was NOT called after download failure
            mock_copy.assert_not_called()

    def test_install_node_wrapped_no_build_after_download_failure(
        self, tmpdir
    ):
        """Test build_node_from_src not called after failure"""
        args = mock.Mock()
        args.node = '18.0.0'
        args.prebuilt = False
        args.verbose = False

        env_dir = tmpdir.join('env').strpath
        src_dir = tmpdir.join('src').strpath
        os.makedirs(src_dir)

        src_url = (
            'https://nodejs.org/download/release/v18.0.0/'
            'node-v18.0.0.tar.gz'
        )

        # Download fails
        def download_side_effect(url, src_dir, args):
            raise nodeenv.urllib2.HTTPError(
                url, 404, 'Not Found', {}, None
            )

        with mock.patch.object(
                nodeenv, 'get_node_src_url',
                return_value=src_url
        ), \
             mock.patch.object(
                 nodeenv, 'download_node_src',
                 side_effect=download_side_effect
             ), \
             mock.patch.object(
                 nodeenv, 'build_node_from_src'
             ) as mock_build, \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch.object(nodeenv.logger, 'info'), \
             mock.patch.object(nodeenv.logger, 'warning'), \
             pytest.raises(nodeenv.urllib2.HTTPError):
            nodeenv.install_node_wrapped(env_dir, src_dir, args)

            # Verify build was NOT called after download failure
            mock_build.assert_not_called()

    def test_install_node_wrapped_no_copy_after_arm64_fallback_failure(
        self, tmpdir
    ):
        """Test copy not called when both arm64 and x64 fail"""
        args = mock.Mock()
        args.node = '16.0.0'
        args.prebuilt = True
        args.verbose = False

        env_dir = tmpdir.join('env').strpath
        src_dir = tmpdir.join('src').strpath
        os.makedirs(src_dir)

        arm64_url = (
            'https://nodejs.org/download/release/v16.0.0/'
            'node-v16.0.0-darwin-arm64.tar.gz'
        )

        # Both arm64 and x64 downloads fail
        def download_side_effect(url, src_dir, args):
            raise nodeenv.urllib2.HTTPError(
                url, 404, 'Not Found', {}, None
            )

        with mock.patch.object(
                nodeenv, 'get_node_bin_url',
                return_value=arm64_url
        ), \
             mock.patch.object(
                 nodeenv, 'download_node_src',
                 side_effect=download_side_effect
             ) as mock_download, \
             mock.patch.object(
                 nodeenv, 'copy_node_from_prebuilt'
             ) as mock_copy, \
             mock.patch('os.path.exists', return_value=False), \
             mock.patch.object(nodeenv.logger, 'info'), \
             pytest.raises(nodeenv.urllib2.HTTPError):
            nodeenv.install_node_wrapped(env_dir, src_dir, args)

            # Verify both attempts were made
            assert mock_download.call_count == 2

            # Verify copy was NOT called after both download failures
            mock_copy.assert_not_called()


class TestGetEnvDir:
    """Tests for get_env_dir function"""

    def test_with_python_virtualenv_real_prefix(self):
        """Test get_env_dir when using python virtualenv with real_prefix"""
        args = mock.Mock()
        args.python_virtualenv = True
        test_prefix = '/path/to/virtualenv'

        with mock.patch.object(sys, 'real_prefix', test_prefix, create=True), \
             mock.patch.object(sys, 'prefix', test_prefix), \
             mock.patch.dict(os.environ, {}, clear=True):
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
                     mock.patch.object(sys, 'base_prefix', test_base_prefix), \
                     mock.patch.dict(os.environ, {}, clear=True):
                    result = nodeenv.get_env_dir(args)
                    assert result == test_prefix
        else:
            with mock.patch.object(sys, 'prefix', test_prefix), \
                 mock.patch.object(sys, 'base_prefix', test_base_prefix), \
                 mock.patch.dict(os.environ, {}, clear=True):
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
                     mock.patch.dict(os.environ, env_dict, clear=True):
                    result = nodeenv.get_env_dir(args)
                    assert result == test_prefix
        else:
            env_dict = {'CONDA_PREFIX': test_prefix}
            with mock.patch.object(sys, 'prefix', test_prefix), \
                 mock.patch.object(sys, 'base_prefix', test_prefix), \
                 mock.patch.dict(os.environ, env_dict, clear=True):
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

    def test_with_python_virtualenv_dir(self, tmpdir):
        """Test get_env_dir when a virtualenv directory is given"""
        args = mock.Mock()
        args.python_virtualenv = str(tmpdir)

        env_dict = {'VIRTUAL_ENV': '/path/to/other/venv'}
        with mock.patch.dict(os.environ, env_dict, clear=True):
            result = nodeenv.get_env_dir(args)
            assert result == str(tmpdir)

    def test_with_python_virtualenv_missing_dir_exits(self, tmpdir):
        """Test get_env_dir exits when the given virtualenv doesn't exist"""
        args = mock.Mock()
        args.python_virtualenv = str(tmpdir.join('missing'))

        with pytest.raises(SystemExit) as exc_info:
            nodeenv.get_env_dir(args)
        assert exc_info.value.code == 2

    def test_with_python_virtualenv_prefers_virtual_env(self):
        """Test get_env_dir prefers VIRTUAL_ENV over nodeenv's own venv"""
        args = mock.Mock()
        args.python_virtualenv = True
        # nodeenv itself is installed into its own virtualenv
        test_prefix = '/path/to/nodeenv/venv'
        virtual_env = '/path/to/activated/venv'

        env_dict = {'VIRTUAL_ENV': virtual_env}
        with mock.patch.object(sys, 'real_prefix', test_prefix, create=True), \
             mock.patch.object(sys, 'prefix', test_prefix), \
             mock.patch.dict(os.environ, env_dict, clear=True), \
             mock.patch.object(nodeenv.logger, 'warning') as mck:
            result = nodeenv.get_env_dir(args)
            assert result == virtual_env
            # the ignored virtualenv is not silently dropped
            assert mck.call_count == 1
            assert mck.call_args[0][1:] == (virtual_env, test_prefix)

    def test_with_python_virtualenv_same_venv_is_quiet(self):
        """Test get_env_dir doesn't warn when both point to the same venv"""
        args = mock.Mock()
        args.python_virtualenv = True
        test_prefix = '/path/to/venv'

        env_dict = {'VIRTUAL_ENV': test_prefix}
        with mock.patch.object(sys, 'real_prefix', test_prefix, create=True), \
             mock.patch.object(sys, 'prefix', test_prefix), \
             mock.patch.dict(os.environ, env_dict, clear=True), \
             mock.patch.object(nodeenv.logger, 'warning') as mck:
            result = nodeenv.get_env_dir(args)
            assert result == test_prefix
            mck.assert_not_called()

    def test_with_python_virtualenv_system_python_is_quiet(self):
        """Test get_env_dir doesn't warn when nodeenv runs system-wide"""
        args = mock.Mock()
        args.python_virtualenv = True
        virtual_env = '/path/to/activated/venv'

        env_dict = {'VIRTUAL_ENV': virtual_env}
        with mock.patch.object(sys, 'prefix', '/usr'), \
             mock.patch.object(sys, 'base_prefix', '/usr'), \
             mock.patch.dict(os.environ, env_dict, clear=True), \
             mock.patch.object(nodeenv.logger, 'warning') as mck:
            result = nodeenv.get_env_dir(args)
            assert result == virtual_env
            mck.assert_not_called()

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


class TestCertifi:
    """Tests for the --with-certifi option"""

    def test_urlopen_without_certifi(self):
        """No SSL context is passed when certifi is not in use"""
        with mock.patch.object(nodeenv, 'ignore_ssl_certs', False), \
             mock.patch.object(nodeenv, 'certifi_context', None), \
             mock.patch.object(nodeenv.urllib2, 'urlopen') as m_urlopen:
            nodeenv.urlopen('https://nodejs.org/dist/index.json')

        assert m_urlopen.call_args[1] == {}

    def test_urlopen_with_certifi(self):
        """The context built by main() is reused for every download"""
        with mock.patch.object(nodeenv, 'ignore_ssl_certs', False), \
             mock.patch.object(nodeenv, 'certifi_context',
                               mock.sentinel.certifi_context), \
             mock.patch.object(nodeenv.urllib2, 'urlopen') as m_urlopen:
            nodeenv.urlopen('https://nodejs.org/dist/index.json')

        context = m_urlopen.call_args[1]['context']
        assert context is mock.sentinel.certifi_context

    def test_urlopen_ignore_ssl_certs_wins(self):
        """--ignore_ssl_certs takes precedence over --with-certifi"""
        with mock.patch.object(nodeenv, 'ignore_ssl_certs', True), \
             mock.patch.object(nodeenv, 'certifi_context',
                               mock.sentinel.certifi_context), \
             mock.patch.object(nodeenv.urllib2, 'urlopen') as m_urlopen:
            nodeenv.urlopen('https://nodejs.org/dist/index.json')

        assert m_urlopen.call_args[1]['context'].verify_mode == ssl.CERT_NONE

    def test_make_certifi_context(self):
        certifi = mock.Mock()
        certifi.where.return_value = '/path/to/cacert.pem'

        with mock.patch.dict(sys.modules, {'certifi': certifi}), \
             mock.patch.object(nodeenv.ssl,
                               'create_default_context') as m_context:
            assert nodeenv.make_certifi_context() is m_context.return_value

        m_context.assert_called_once_with(cafile='/path/to/cacert.pem')

    def test_make_certifi_context_without_certifi(self):
        """A missing certifi is reported instead of silently ignored"""
        with mock.patch.dict(sys.modules, {'certifi': None}), \
             mock.patch.object(nodeenv.logger, 'warning') as m_warning:
            assert nodeenv.make_certifi_context() is None

        assert 'certifi is not installed' in m_warning.call_args[0][0]

    def test_with_certifi_is_configurable(self):
        """with_certifi can be set from the config file, like other options"""
        assert 'with_certifi' in nodeenv.Config._default
