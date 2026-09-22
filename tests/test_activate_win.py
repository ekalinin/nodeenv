"""
Behavioural tests for the cmd and PowerShell activation scripts.

tests/test_activate_shells.py does the same for the POSIX shells, and
tests/test_install_activate.py compares the generated text against the
templates.  These run the scripts instead, so they need a Windows host
and only run there.
"""
import os
import subprocess
import sys

try:
    from unittest import mock
except ImportError:
    import mock  # pyright: ignore[reportMissingModuleSource]
import pytest

import nodeenv

pytestmark = pytest.mark.skipif(
    not nodeenv.is_WIN, reason='cmd.exe and PowerShell need a Windows host')

UNSET = '<unset>'

PROBED = ('VIRTUAL_ENV', 'NODE_VIRTUAL_ENV', 'PATH')

# printed before the variables so the dump can be told apart from
# whatever the activation scripts write to stdout themselves
DUMP_SENTINEL = '--8<-- nodeenv env dump --8<--'

DUMPER = """\
import os
import sys

print('__SENTINEL__')
for name in sys.argv[1:]:
    print('%s=%s' % (name, os.environ.get(name, '<unset>')))
""".replace('__SENTINEL__', DUMP_SENTINEL)


def _quote(path):
    """A windows path cannot contain a double quote, so this is enough."""
    return '"%s"' % path


def _same(path, other):
    return os.path.normcase(os.path.normpath(path)) == \
        os.path.normcase(os.path.normpath(other))


class Env(object):
    def __init__(self, path, dumper, tmpdir):
        self.path = path
        self.dumper = dumper
        self.tmpdir = tmpdir

    def script(self, name):
        return os.path.join(self.path, 'Scripts', name)


@pytest.fixture
def env(tmpdir):
    """A python virtualenv with `nodeenv -p` run over it."""
    env_dir = str(tmpdir.join('.venv'))
    subprocess.check_call(
        [sys.executable, '-m', 'venv', '--without-pip', env_dir])

    dumper = tmpdir.join('dump.py')
    dumper.write(DUMPER)

    # the activation scripts only move environment variables around,
    # so no Node.js download is needed
    with mock.patch.object(sys, 'argv', ['nodeenv', '-p', env_dir]):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(env_dir, opts)

    return Env(env_dir, str(dumper), tmpdir)


def _child_env():
    """
    A clean environment: no leftovers from an environment active in the
    shell running the tests, nor from the virtualenv tox builds.
    """
    ignored = ('VIRTUAL_ENV', 'VIRTUAL_ENV_PROMPT', 'NODE_VIRTUAL_ENV',
               'NODE_PATH', 'NPM_CONFIG_PREFIX',
               'NODE_VIRTUAL_ENV_DISABLE_PROMPT')
    return dict(
        (k, v) for k, v in os.environ.items()
        if not k.startswith('_OLD_')
        and not k.startswith('npm_config_')
        and k not in ignored)


def _dump_line(dumper, call=''):
    parts = [_quote(sys.executable), _quote(dumper)] + list(PROBED)
    if call:
        parts.insert(0, call)
    return ' '.join(parts)


def _parse(out, shell):
    out = out.replace('\r\n', '\n')
    _, sentinel, dump = out.partition(DUMP_SENTINEL + '\n')
    assert sentinel, 'no dump in the output of %s: %r' % (shell, out)
    return dict(line.split('=', 1) for line in dump.splitlines() if line)


def _run(args, script, lines, shell):
    script.write('\n'.join(lines) + '\n')
    out = subprocess.check_output(
        args + [str(script)], env=_child_env(), cwd=str(script.dirname))
    return _parse(out.decode('utf-8'), shell)


def run_cmd(env, steps=()):
    """Run the steps in cmd.exe and return the probed environment."""
    lines = ['@echo off'] + list(steps) + [_dump_line(env.dumper)]
    return _run(['cmd', '/c'], env.tmpdir.join('probe.bat'), lines, 'cmd')


def run_ps1(env, steps=()):
    """Run the steps in PowerShell and return the probed environment."""
    lines = list(steps) + [_dump_line(env.dumper, call='&')]
    return _run(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File'],
        env.tmpdir.join('probe.ps1'), lines, 'powershell')


def _call_bat(env, name):
    return 'call %s' % _quote(env.script(name))


def _dot_source_ps1(env):
    return '. %s' % _quote(env.script('Activate.ps1'))


# `nodeenv -p` used to overwrite the scripts python's venv wrote, and
# VIRTUAL_ENV went away with them
# https://github.com/ekalinin/nodeenv/issues/243


def test_activate_bat_keeps_virtual_env(env):
    dump = run_cmd(env, [_call_bat(env, 'activate.bat')])

    assert _same(dump['VIRTUAL_ENV'], env.path)
    assert _same(dump['NODE_VIRTUAL_ENV'], env.path)
    assert _same(dump['PATH'].split(os.pathsep)[0],
                 os.path.join(env.path, 'Scripts'))


def test_deactivate_bat_restores_the_environment(env):
    baseline = run_cmd(env)

    dump = run_cmd(env, [_call_bat(env, 'activate.bat'),
                         _call_bat(env, 'deactivate.bat')])

    assert dump['VIRTUAL_ENV'] == UNSET
    assert dump['NODE_VIRTUAL_ENV'] == UNSET
    assert dump['PATH'] == baseline['PATH']


def test_activate_ps1_keeps_virtual_env(env):
    dump = run_ps1(env, [_dot_source_ps1(env)])

    assert _same(dump['VIRTUAL_ENV'], env.path)
    assert _same(dump['NODE_VIRTUAL_ENV'], env.path)
    assert _same(dump['PATH'].split(os.pathsep)[0],
                 os.path.join(env.path, 'Scripts'))


def test_deactivate_ps1_restores_the_environment(env):
    # the appended script defines `deactivate` too: it has to call the
    # virtualenv's own one, or VIRTUAL_ENV can never be unset again
    baseline = run_ps1(env)

    dump = run_ps1(env, [_dot_source_ps1(env), 'deactivate'])

    assert dump['VIRTUAL_ENV'] == UNSET
    assert dump['NODE_VIRTUAL_ENV'] == UNSET
    assert dump['PATH'] == baseline['PATH']
