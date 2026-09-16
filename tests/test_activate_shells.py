"""
Behavioural tests for the generated activation scripts.

tests/test_install_activate.py compares the generated text against the
templates in nodeenv.py.  These tests instead run the scripts in every shell
nodeenv supports and check the environment they produce.
"""
import os
import shutil
import subprocess
import sys

try:
    from unittest import mock
except ImportError:
    import mock  # pyright: ignore[reportMissingModuleSource]
import pytest

import nodeenv

pytestmark = pytest.mark.skipif(
    nodeenv.is_WIN, reason='the scripts under test are POSIX only')

# CI sets this so a missing shell fails the run instead of skipping it
REQUIRE_SHELLS = os.environ.get('NODEENV_REQUIRE_SHELLS') == '1'

# dash is not packaged everywhere, so it stays optional even under CI
OPTIONAL_SHELLS = ('dash',)

UNSET = '<unset>'

# the environment the scripts are expected to save and restore
BASE_ENV = {
    'NODE_PATH': '/old/node_path',
    'NPM_CONFIG_PREFIX': '/old/prefix',
    'npm_config_prefix': '/old/prefix',
    'npm_config_cache': '/old/cache',
    'npm_config_userconfig': '/old/npmrc',
    'npm_config_init_module': '/old/init.js',
    'PS1': 'base-ps1 ',
}

PROBED = tuple(BASE_ENV) + (
    'PATH', 'NODE_VIRTUAL_ENV', '_OLD_NODE_FISH_PROMPT_OVERRIDE')

ISOLATED_NPM = (
    ('npm_config_cache', '.npm'),
    ('npm_config_userconfig', '.npmrc'),
    ('npm_config_init_module', '.npm-init.js'),
)

DUMPER = """\
import os
import sys

for name in sys.argv[1:]:
    print('%s=%s' % (name, os.environ.get(name, '<unset>')))
"""

ZSH_SOURCE_GUARD = (
    'zsh sets $0 to the sourced file, so the "do not call directly" guard '
    'added to ACTIVATE_SH in 68abdc3 fires on `source bin/activate`')


class Shell(object):
    def __init__(self, name, script='activate', source='.', prelude=()):
        self.name = name
        self.script = script
        self.source = source
        self.prelude = prelude

    def source_line(self, path):
        return '%s %s' % (self.source, nodeenv._quote(path))


# bash ignores PS1 from the environment when non-interactive, so the prompt
# has to be set as a shell variable inside the shell itself
POSIX_PRELUDE = ("PS1='%s'" % BASE_ENV['PS1'], 'export PS1')

SHELLS = (
    Shell('sh', prelude=POSIX_PRELUDE),
    Shell('dash', prelude=POSIX_PRELUDE),
    Shell('bash', prelude=POSIX_PRELUDE),
    Shell('zsh', prelude=POSIX_PRELUDE),
    Shell('fish', script='activate.fish', source='source'),
)


def _params(xfail_zsh):
    params = []
    for shell in SHELLS:
        marks = ()
        if xfail_zsh and shell.name == 'zsh':
            marks = pytest.mark.xfail(strict=True, reason=ZSH_SOURCE_GUARD)
        params.append(pytest.param(shell, marks=marks, id=shell.name))
    return params


every_shell = pytest.mark.parametrize('shell', _params(False))
activating_shell = pytest.mark.parametrize('shell', _params(True))


def _binary(shell):
    """Path to the shell, or skip/fail when it is not installed."""
    path = shutil.which(shell.name)
    if path:
        return path
    if REQUIRE_SHELLS and shell.name not in OPTIONAL_SHELLS:
        pytest.fail(
            '%s is missing and NODEENV_REQUIRE_SHELLS=1' % shell.name)
    return pytest.skip('%s is not installed' % shell.name)


def _real(path):
    """
    Normalise a path for comparison.

    bash resolves NODE_VIRTUAL_ENV with `cd -P` and fish with `realpath`,
    while zsh falls back to the literal path baked into the script, so the
    three disagree about symlinks such as /tmp -> /private/tmp on macOS.
    """
    return os.path.realpath(path)


class Env(object):
    def __init__(self, path, home, dumper, isolate_npm):
        self.path = path
        self.home = home
        self.dumper = dumper
        self.isolate_npm = isolate_npm

    def script(self, shell):
        return os.path.join(self.path, 'bin', shell.script)


@pytest.fixture(params=([], ['--isolate-npm']), ids=('plain', 'isolate'))
def env(request, tmpdir):
    env_dir = tmpdir.join('env')
    bin_dir = env_dir.join('bin')
    bin_dir.ensure(dir=True)
    # the activation scripts only move environment variables around,
    # so a stub is enough and no Node.js download is needed
    node = bin_dir.join('node')
    node.write('#!/bin/sh\necho stub-node\n')
    node.chmod(0o755)

    dumper = tmpdir.join('dump.py')
    dumper.write(DUMPER)

    argv = ['nodeenv'] + request.param + [str(env_dir)]
    with mock.patch.object(sys, 'argv', argv):
        opts = nodeenv.parse_args()
        nodeenv.install_activate(str(env_dir), opts)

    return Env(str(env_dir), str(tmpdir.join('home').ensure(dir=True)),
               str(dumper), bool(request.param))


def _child_env(env):
    """
    A clean environment: no leftovers from a nodeenv active in the shell
    running the tests, and no user rc files (fish reads config.fish even
    for `fish -c`).
    """
    ignored = ('NODE_VIRTUAL_ENV', 'NODE_PATH', 'NPM_CONFIG_PREFIX')
    result = dict(
        (k, v) for k, v in os.environ.items()
        if not k.startswith('_OLD_')
        and not k.startswith('npm_config_')
        and k not in ignored)
    result.update(BASE_ENV)
    result.update(HOME=env.home, XDG_CONFIG_HOME=env.home, ZDOTDIR=env.home)
    return result


def run(shell, env, steps=(), source=True):
    """Run the shell and return the probed environment as a dict."""
    lines = list(shell.prelude)
    if source:
        lines.append(shell.source_line(env.script(shell)))
    lines.extend(steps)
    lines.append('%s %s %s' % (
        nodeenv._quote(sys.executable),
        nodeenv._quote(env.dumper),
        ' '.join(PROBED)))
    out = subprocess.check_output(
        [_binary(shell), '-c', '\n'.join(lines)], env=_child_env(env))
    return dict(
        line.split('=', 1) for line in out.decode('utf-8').splitlines())


@every_shell
def test_syntax(shell, env):
    subprocess.check_call([_binary(shell), '-n', env.script(shell)])


@activating_shell
def test_activate_sets_env(shell, env):
    dump = run(shell, env)

    assert _real(dump['NODE_VIRTUAL_ENV']) == _real(env.path)
    head = dump['PATH'].split(os.pathsep)[:2]
    assert [_real(p) for p in head] == [
        _real(os.path.join(env.path, 'lib', 'node_modules', '.bin')),
        _real(os.path.join(env.path, 'bin')),
    ]
    # fish prepends to NODE_PATH, the POSIX script replaces it
    assert _real(dump['NODE_PATH'].split(os.pathsep)[0]) == \
        _real(os.path.join(env.path, 'lib', 'node_modules'))
    assert _real(dump['NPM_CONFIG_PREFIX']) == _real(env.path)
    assert _real(dump['npm_config_prefix']) == _real(env.path)


@activating_shell
def test_deactivate_restores_env(shell, env):
    dump = run(shell, env, ['deactivate_node'])

    assert dump['NODE_VIRTUAL_ENV'] == UNSET
    assert dump['NODE_PATH'] == BASE_ENV['NODE_PATH']
    assert dump['NPM_CONFIG_PREFIX'] == BASE_ENV['NPM_CONFIG_PREFIX']
    assert dump['npm_config_prefix'] == BASE_ENV['npm_config_prefix']
