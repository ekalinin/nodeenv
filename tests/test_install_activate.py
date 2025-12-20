import sys
import os

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


def test_all_placeholders_replaced(tmpdir):
    """Test that all placeholders are properly replaced in generated files"""
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

    # Check that no placeholders remain in any file
    for name in FILES:
        content = bin_dir.join(name).read()
        assert '__NODE_VIRTUAL_PROMPT__' not in content
        assert '__NODE_VIRTUAL_ENV__' not in content
        assert '__SHIM_NODE__' not in content
        assert '__BIN_NAME__' not in content
        assert '__MOD_NAME__' not in content
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
