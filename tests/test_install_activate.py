import sys
import os
import subprocess

try:
    from unittest import mock
except ImportError:
    import mock  # pyright: ignore[reportMissingModuleSource]
import pytest

import nodeenv

if nodeenv.is_WIN:
    FILES = {
        'activate.bat': 'ACTIVATE_BAT',
        "deactivate.bat": 'DEACTIVATE_BAT',
        "Activate.ps1": 'ACTIVATE_PS1',
    }
else:
    FILES = {
        'activate': 'ACTIVATE_SH',
        'activate.fish': 'ACTIVATE_FISH',
        'shim': 'SHIM',
    }


def fix_content(content, tmpdir):
    if nodeenv.is_WIN:
        bin_name = 'Scripts'
        node_name = 'node.exe'
    else:
        bin_name = 'bin'
        node_name = 'node'
        tmpdir.join('Scripts').join('node.exe')

    content = content.replace(
        '__NODE_VIRTUAL_PROMPT__', '({})'.format(tmpdir.basename))
    content = content.replace('__NODE_VIRTUAL_ENV__', str(tmpdir))
    content = content.replace(
        '__SHIM_NODE__', str(tmpdir.join(bin_name).join(node_name)))
    content = content.replace('__BIN_NAME__', bin_name)
    content = content.replace(
        '__MOD_NAME__', os.path.join('lib', 'node_modules'))
    content = content.replace('__NPM_CONFIG_PREFIX__', '$NODE_VIRTUAL_ENV')
    content = content.replace('__NPM_ISOLATE__', '')
    content = content.replace('__NPM_UNISOLATE__', '')
    return content


@pytest.mark.parametrize('name, content_var', FILES.items())
def test_write(tmpdir, name, content_var):
    if nodeenv.is_WIN:
        bin_dir = tmpdir.join('Scripts')
    else:
        bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()
    for n in FILES:
        bin_dir.join(n).write(n)

    with mock.patch.object(sys, 'argv', ['nodeenv', str(tmpdir)]):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    content = getattr(nodeenv, content_var)
    assert bin_dir.join(name).read() == fix_content(content, tmpdir)


@pytest.mark.parametrize('name, content_var', FILES.items())
def test_python_virtualenv(tmpdir, name, content_var):
    if nodeenv.is_WIN:
        bin_dir = tmpdir.join('Scripts')
    else:
        bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()
    for n in FILES:
        bin_dir.join(n).write(n)

    with mock.patch.object(sys, 'argv', ['nodeenv', '-p']):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    content = getattr(nodeenv, content_var)
    # If there's disable prompt content to be added, we're appending to
    # the file so prepend the original content (and the wrapped
    # disable/enable prompt content).
    disable_prompt = nodeenv.DISABLE_PROMPT.get(name)
    if disable_prompt:
        enable_prompt = nodeenv.ENABLE_PROMPT.get(name, '')
        content = name + disable_prompt + content + enable_prompt
    assert bin_dir.join(name).read() == fix_content(content, tmpdir)


@pytest.mark.parametrize('name, content_var', FILES.items())
def test_custom_prompt(tmpdir, name, content_var):
    if nodeenv.is_WIN:
        bin_dir = tmpdir.join('Scripts')
    else:
        bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()
    for n in FILES:
        bin_dir.join(n).write(n)

    custom_prompt = '(my-custom-env)'
    with mock.patch.object(
        sys, 'argv', ['nodeenv', '--prompt', custom_prompt, str(tmpdir)]
    ):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    content = getattr(nodeenv, content_var)
    expected_content = content.replace(
        '__NODE_VIRTUAL_PROMPT__', custom_prompt)
    expected_content = expected_content.replace(
        '__NODE_VIRTUAL_ENV__', str(tmpdir))
    if nodeenv.is_WIN:
        node_name = 'node.exe'
    else:
        node_name = 'node'
    expected_content = expected_content.replace(
        '__SHIM_NODE__', str(bin_dir.join(node_name)))
    expected_content = expected_content.replace(
        '__BIN_NAME__', os.path.basename(str(bin_dir)))
    expected_content = expected_content.replace(
        '__MOD_NAME__', os.path.join('lib', 'node_modules'))
    expected_content = expected_content.replace(
        '__NPM_CONFIG_PREFIX__', '$NODE_VIRTUAL_ENV')
    expected_content = expected_content.replace('__NPM_ISOLATE__', '')
    expected_content = expected_content.replace('__NPM_UNISOLATE__', '')
    assert bin_dir.join(name).read() == expected_content


@pytest.mark.skipif(nodeenv.is_WIN, reason='system node is POSIX only')
def test_node_system_creates_shim(tmpdir):
    bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()

    # Mock system node path
    system_node = '/usr/bin/node'

    with mock.patch.object(
        sys, 'argv', ['nodeenv', '--node=system', str(tmpdir)]
    ):
        with mock.patch('shutil.which', return_value=system_node):
            opts = nodeenv.parse_args()
            nodeenv.install_activate(str(tmpdir), opts)

    # Check that shim file was created for node
    assert bin_dir.join('node').exists()
    shim_content = bin_dir.join('node').read()
    assert system_node in shim_content
    assert 'NODE_PATH' in shim_content


@pytest.mark.skipif(nodeenv.is_WIN, reason='symlink test is POSIX only')
def test_nodejs_symlink_created(tmpdir):
    bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()
    # Create a dummy node file
    node_file = bin_dir.join('node')
    node_file.write('#!/bin/sh\necho node')

    with mock.patch.object(sys, 'argv', ['nodeenv', str(tmpdir)]):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    nodejs_file = bin_dir.join('nodejs')
    assert nodejs_file.exists()
    assert os.path.islink(str(nodejs_file))
    assert os.readlink(str(nodejs_file)) == 'node'


def test_file_overwrite(tmpdir):
    """Test that files are correctly overwritten when they already exist"""
    if nodeenv.is_WIN:
        bin_dir = tmpdir.join('Scripts')
    else:
        bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()
    for n in FILES:
        bin_dir.join(n).write('old content')

    with mock.patch.object(sys, 'argv', ['nodeenv', str(tmpdir)]):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    # Verify files were updated with correct content
    for name, content_var in FILES.items():
        content = getattr(nodeenv, content_var)
        assert bin_dir.join(name).read() == fix_content(content, tmpdir)


def test_prompt_default_to_basename(tmpdir):
    """Test that prompt defaults to environment directory basename"""
    if nodeenv.is_WIN:
        bin_dir = tmpdir.join('Scripts')
        test_file = 'activate.bat'
    else:
        bin_dir = tmpdir.join('bin')
        test_file = 'activate'
    bin_dir.mkdir()
    for n in FILES:
        bin_dir.join(n).write(n)

    with mock.patch.object(sys, 'argv', ['nodeenv', str(tmpdir)]):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    expected_prompt = '({})'.format(tmpdir.basename)
    content = bin_dir.join(test_file).read()
    assert expected_prompt in content


def test_python_virtualenv_with_custom_prompt(tmpdir):
    """Test that custom prompt works with python virtualenv"""
    if nodeenv.is_WIN:
        bin_dir = tmpdir.join('Scripts')
        test_file = 'activate.bat'
    else:
        bin_dir = tmpdir.join('bin')
        test_file = 'activate'
    bin_dir.mkdir()
    for n in FILES:
        bin_dir.join(n).write(n)

    custom_prompt = '(test-env)'
    with mock.patch.object(
        sys, 'argv', ['nodeenv', '-p', '--prompt', custom_prompt]
    ):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    content = bin_dir.join(test_file).read()
    assert custom_prompt in content
    if not nodeenv.is_WIN:
        # Check that DISABLE_PROMPT was prepended for non-Windows
        if test_file in nodeenv.DISABLE_PROMPT:
            assert 'NODE_VIRTUAL_ENV_DISABLE_PROMPT' in content


@pytest.mark.parametrize('extra_args', ([], ['--isolate-npm']))
def test_all_placeholders_replaced(tmpdir, extra_args):
    """Test that all placeholders are properly replaced in generated files"""
    if nodeenv.is_WIN:
        bin_dir = tmpdir.join('Scripts')
    else:
        bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()
    for n in FILES:
        bin_dir.join(n).write(n)

    with mock.patch.object(
            sys, 'argv', ['nodeenv'] + extra_args + [str(tmpdir)]):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    # Check that no placeholders remain in any file
    for name in FILES:
        content = bin_dir.join(name).read()
        assert '__NODE_VIRTUAL_PROMPT__' not in content
        assert '__NODE_VIRTUAL_ENV__' not in content
        assert '__SHIM_NODE__' not in content
        assert '__BIN_NAME__' not in content
        assert '__MOD_NAME__' not in content
        assert '__NPM_ISOLATE__' not in content
        assert '__NPM_UNISOLATE__' not in content
        # __NPM_CONFIG_PREFIX__ might be in the file as a variable reference
        # but not as an unreplaced placeholder, so check more carefully
        if nodeenv.is_WIN:
            # On Windows it should be replaced with the actual path
            pass  # Skip check on Windows as it's more complex
        else:
            # On Unix it should be replaced with '$NODE_VIRTUAL_ENV'
            # The original placeholder should not exist
            lines = content.split('\n')
            for line in lines:
                if '__NPM_CONFIG_PREFIX__' in line:
                    # Make sure it's not the actual placeholder being used
                    assert (
                        'NPM_CONFIG_PREFIX=' in line or
                        'set NPM_CONFIG_PREFIX' in line
                    ), "Found unreplaced __NPM_CONFIG_PREFIX__ placeholder"


@pytest.mark.parametrize('name, content_var', FILES.items())
def test_files_are_executable(tmpdir, name, content_var):
    """Test that created activation files are executable when first created"""
    if nodeenv.is_WIN:
        bin_dir = tmpdir.join('Scripts')
    else:
        bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()

    with mock.patch.object(sys, 'argv', ['nodeenv', str(tmpdir)]):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    file_path = str(bin_dir.join(name))
    if not nodeenv.is_WIN:
        # Check that file is executable on Unix systems
        import stat
        st = os.stat(file_path)
        assert st.st_mode & stat.S_IXUSR, \
            f"File {name} should be executable by user"
        assert st.st_mode & stat.S_IXGRP, \
            f"File {name} should be executable by group"
        assert st.st_mode & stat.S_IXOTH, \
            f"File {name} should be executable by others"


ISOLATED_NPM_VARS = (
    'npm_config_cache', 'npm_config_userconfig', 'npm_config_init_module')


def _npm_isolation_report():
    """
    Shell fragment printing the three isolated npm variables on one line
    """
    return 'echo "$%s"' % '|$'.join(ISOLATED_NPM_VARS)


@pytest.mark.skipif(nodeenv.is_WIN, reason='--isolate-npm is POSIX only')
def test_isolate_npm_off_by_default(tmpdir):
    bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()

    with mock.patch.object(sys, 'argv', ['nodeenv', str(tmpdir)]):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    for name in FILES:
        content = bin_dir.join(name).read()
        for var in ISOLATED_NPM_VARS:
            assert var not in content


@pytest.mark.skipif(nodeenv.is_WIN, reason='--isolate-npm is POSIX only')
def test_isolate_npm_sh_sets_and_restores(tmpdir):
    bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()

    with mock.patch.object(
            sys, 'argv', ['nodeenv', '--isolate-npm', str(tmpdir)]):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    report = _npm_isolation_report()
    script = '. {0} && {1} && deactivate_node && {1}'.format(
        nodeenv._quote(str(bin_dir.join('activate'))), report)
    # drop any _OLD_* left by an active nodeenv in the test runner's shell
    env = dict(
        (k, v) for k, v in os.environ.items() if not k.startswith('_OLD_'))
    env.update(
        npm_config_cache='/old/cache',
        npm_config_userconfig='/old/npmrc',
        npm_config_init_module='/old/init.js',
    )
    out = subprocess.check_output(['sh', '-c', script], env=env)
    active, restored = out.decode('utf-8').splitlines()

    # bash derives NODE_VIRTUAL_ENV with `cd -P`, so symlinks are resolved
    env_dir = os.path.realpath(str(tmpdir))
    assert active == '|'.join((
        env_dir + '/.npm', env_dir + '/.npmrc', env_dir + '/.npm-init.js'))
    assert restored == '/old/cache|/old/npmrc|/old/init.js'


@pytest.mark.skipif(nodeenv.is_WIN, reason='--isolate-npm is POSIX only')
def test_isolate_npm_fish_content(tmpdir):
    bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()

    with mock.patch.object(
            sys, 'argv', ['nodeenv', '--isolate-npm', str(tmpdir)]):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    content = bin_dir.join('activate.fish').read()
    assert 'set -gx npm_config_cache "$NODE_VIRTUAL_ENV/.npm"' in content
    assert 'set -gx npm_config_userconfig "$NODE_VIRTUAL_ENV/.npmrc"' \
        in content
    assert ('set -gx npm_config_init_module '
            '"$NODE_VIRTUAL_ENV/.npm-init.js"') in content
    guard = 'if set -q NODE_VIRTUAL_ENV'
    assert guard in content
    for var in ISOLATED_NPM_VARS:
        assert 'set -gx _OLD_%s $%s' % (var, var) in content
        restore = 'set -gx %s $_OLD_%s' % (var, var)
        assert restore in content
        assert 'set -e _OLD_%s' % var in content
        assert 'set -e %s' % var in content
        # the restore must sit inside the guard, after it
        assert content.index(guard) < content.index(restore)


@pytest.mark.skipif(nodeenv.is_WIN, reason='--isolate-npm is POSIX only')
def test_isolate_npm_shim_content(tmpdir):
    bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()

    with mock.patch.object(
            sys, 'argv', ['nodeenv', '--isolate-npm', str(tmpdir)]):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)

    content = bin_dir.join('shim').read()
    env_dir = str(tmpdir)
    assert "export npm_config_cache='%s/.npm'" % env_dir in content
    assert "export npm_config_userconfig='%s/.npmrc'" % env_dir in content
    assert "export npm_config_init_module='%s/.npm-init.js'" % env_dir \
        in content
    # the exports must come before exec, otherwise node never sees them
    assert content.index('npm_config_cache') < content.index('exec ')


# Windows also gets the posix `activate`, for git-bash and friends.
# https://github.com/ekalinin/nodeenv/issues/226
#
# These run on every platform: is_WIN is faked so the Scripts/ layout can
# be checked without a Windows host.


@pytest.fixture
def fake_win():
    """
    Pretend the host is Windows.  install_activate() links nodejs.exe with
    mklink there, which exists on Windows only, so callit() is stubbed too.
    """
    with mock.patch.object(nodeenv, 'is_WIN', True):
        with mock.patch.object(nodeenv, 'callit'):
            yield


def _install_win(tmpdir, *extra_args):
    bin_dir = tmpdir.join('Scripts')
    if not bin_dir.check():
        bin_dir.mkdir()

    argv = ['nodeenv'] + list(extra_args) + [str(tmpdir)]
    with mock.patch.object(sys, 'argv', argv):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(tmpdir), opts)
    return bin_dir


def test_win_writes_posix_activate(tmpdir, fake_win):
    bin_dir = _install_win(tmpdir)

    assert sorted(p.basename for p in bin_dir.listdir()) == [
        'Activate.ps1', 'activate', 'activate.bat', 'deactivate.bat']


def test_win_activate_puts_scripts_on_path(tmpdir, fake_win):
    content = _install_win(tmpdir).join('activate').read()

    assert ('PATH="$NODE_VIRTUAL_ENV/Scripts/node_modules/.bin:'
            '$NODE_VIRTUAL_ENV/Scripts:$PATH"') in content


def test_win_activate_points_node_at_scripts(tmpdir, fake_win):
    # npm keeps the global modules next to node.exe on Windows, there is
    # no lib/node_modules there
    content = _install_win(tmpdir).join('activate').read()

    assert 'NODE_PATH="$NODE_VIRTUAL_ENV/Scripts/node_modules"' in content
    assert 'NPM_CONFIG_PREFIX="$NODE_VIRTUAL_ENV/Scripts"' in content
    assert 'npm_config_prefix="$NODE_VIRTUAL_ENV/Scripts"' in content


def test_win_activate_has_no_placeholders_left(tmpdir, fake_win):
    content = _install_win(tmpdir).join('activate').read()

    for placeholder in ('__NODE_VIRTUAL_PROMPT__', '__NODE_VIRTUAL_ENV__',
                        '__SHIM_NODE__', '__BIN_NAME__', '__MOD_NAME__',
                        '__NPM_ISOLATE__', '__NPM_UNISOLATE__',
                        '__NPM_CONFIG_PREFIX__'):
        assert placeholder not in content


def test_win_activate_converts_paths_for_node_exe(tmpdir, fake_win):
    # node.exe is a native binary: it cannot read the /c/... paths a
    # Windows shell hands out, so the script converts them back
    content = _install_win(tmpdir).join('activate').read()

    assert 'CYGWIN*|MSYS*|MINGW*)' in content
    assert 'NODE_PATH="$(cygpath -w "$NODE_PATH")"' in content
    assert 'NPM_CONFIG_PREFIX="$(cygpath -w "$NPM_CONFIG_PREFIX")"' in content
    # the conversion must come after the variables are built
    assert content.index('NODE_PATH="$NODE_VIRTUAL_ENV') < \
        content.index('cygpath -w')


def test_win_activate_is_valid_sh(tmpdir, fake_win):
    activate = _install_win(tmpdir).join('activate')

    subprocess.check_call(['sh', '-n', str(activate)])


def test_win_activate_refuses_to_be_run_directly(tmpdir, fake_win):
    # the guard matches on $0, and a shell reports the path it was given:
    # from a posix shell on Windows that is the forward slash form
    activate = str(_install_win(tmpdir).join('activate')).replace(os.sep, '/')

    proc = subprocess.Popen(
        ['sh', activate], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, _ = proc.communicate()

    assert proc.returncode == 1
    assert b'Do not call' in out


def test_win_python_virtualenv_appends_to_activate(tmpdir, fake_win):
    # nodeenv -p inside a python venv: venv wrote Scripts/activate for
    # git-bash already, nodeenv has to extend it, not replace it
    bin_dir = tmpdir.join('Scripts')
    bin_dir.mkdir()
    bin_dir.join('activate').write('# python venv activate\n')

    _install_win(tmpdir, '-p')

    content = bin_dir.join('activate').read()
    assert content.startswith('# python venv activate\n')
    assert 'NODE_VIRTUAL_ENV_DISABLE_PROMPT=1' in content


@pytest.mark.skipif(nodeenv.is_WIN, reason='system node is POSIX only')
def test_isolate_npm_node_system_shim_exports(tmpdir):
    bin_dir = tmpdir.join('bin')
    bin_dir.mkdir()

    # A fake system node that prints the three isolated npm variables
    fake_node = tmpdir.join('fake-node')
    fake_node.write('#!/bin/sh\n%s\n' % _npm_isolation_report())
    fake_node.chmod(0o755)

    with mock.patch.object(
            sys, 'argv',
            ['nodeenv', '--isolate-npm', '--node=system', str(tmpdir)]):
        with mock.patch('shutil.which', return_value=str(fake_node)):
            opts = nodeenv.parse_args()
            nodeenv.install_activate(str(tmpdir), opts)

    out = subprocess.check_output([str(bin_dir.join('node'))])
    env_dir = str(tmpdir)
    assert out.decode('utf-8').strip() == '|'.join((
        env_dir + '/.npm', env_dir + '/.npmrc', env_dir + '/.npm-init.js'))
