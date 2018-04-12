import sys
import os

import mock
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
        opts = nodeenv.parse_args()[0]
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
        opts = nodeenv.parse_args()[0]
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
