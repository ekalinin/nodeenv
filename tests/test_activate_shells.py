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

# printed before the variables so run() can tell the dump apart from
# anything the activation script writes to stdout
DUMP_SENTINEL = '--8<-- nodeenv env dump --8<--'

DUMPER = """\
import os
import sys

print('__SENTINEL__')
for name in sys.argv[1:]:
    print('%s=%s' % (name, os.environ.get(name, '<unset>')))
""".replace('__SENTINEL__', DUMP_SENTINEL)

# as much of the npm CLI as `freeze` calls: a version and the listing of
# `npm ls --parseable --long`, picked by the presence of `-g`
NPM_STUB = """\
#!/bin/sh
if [ "$1" = '-v' ]; then
    echo 11.19.0
    exit 0
fi
for arg in "$@"; do
    if [ "$arg" = '-g' ]; then
        cat <<'LISTING'
__GLOBAL__
LISTING
        exit 0
    fi
done
cat <<'LISTING'
__LOCAL__
LISTING
"""

# `path:name@version[:FLAGS]`, one package per line.  The tree root is the
# only line without `/node_modules/` in its path, global or local
GLOBAL_LISTING = (
    '/env/lib:lib@:/env/lib',
    '/env/lib/node_modules/@scope/pkg:@scope/pkg@1.2.3',
    '/env/lib/node_modules/cheerio:cheerio@1.2.0',
    '/env/lib/node_modules/corepack:corepack@0.36.0',
    '/env/lib/node_modules/extra:extra@1.0.0:EXTRANEOUS',
    '/env/lib/node_modules/npm:npm@11.19.0',
    '/env/lib/node_modules/npmlog:npmlog@7.0.1',
)

# npm and corepack are installed by node.js itself: freezing them pins a
# version the user never asked for and downgrades the bundled copy on the
# next install.  Everything else is kept, including the extraneous package,
# with its `:EXTRANEOUS` flag stripped
FROZEN_GLOBAL = [
    '@scope/pkg@1.2.3',
    'cheerio@1.2.0',
    'extra@1.0.0',
    'npmlog@7.0.1',
]

LOCAL_LISTING = (
    '/project:project@0.0.0',
    '/project/node_modules/@scope/local:@scope/local@2.0.0',
    '/project/node_modules/npmlog:npmlog@7.0.1',
)

FROZEN_LOCAL = [
    '@scope/local@2.0.0',
    'npmlog@7.0.1',
]

ZSH_SOURCE_GUARD = (
    'zsh sets $0 to the sourced file, so the "do not call directly" guard '
    'added to ACTIVATE_SH in 68abdc3 fires on `source bin/activate`')

FISH_NODE_PATH_CLOBBER = (
    'activate.fish runs `deactivate_node nondestructive` before it saves '
    '_OLD_NODE_PATH, and that pass erases a pre-existing NODE_PATH, so the '
    'real deactivation has nothing left to restore. b042056 added the '
    '`if set -q NODE_VIRTUAL_ENV` guard for the npm variables only. '
    'NPM_CONFIG_PREFIX and npm_config_prefix are erased by the same pass '
    'and are equally unrestored; the test only reports NODE_PATH because '
    'it is asserted first')

FISH_CARET_REDIRECT = (
    'the PATH line in activate.fish ends with `^/dev/null`, but fish 3.0 '
    'turned on stderr-nocaret and `^` is no longer a stderr redirect, so '
    'the token lands in PATH as a literal entry')


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

# a missing shell has to be reported before the tests run: pytest turns any
# failure inside an xfail-marked test into an expected one, which would hide
# it for the shells that carry a known-failure marker.  pytestmark is only
# applied after the import, so Windows has to be excluded here as well
if REQUIRE_SHELLS and not nodeenv.is_WIN:
    _missing = [s.name for s in SHELLS
                if s.name not in OPTIONAL_SHELLS and not shutil.which(s.name)]
    if _missing:
        raise RuntimeError('missing shells: %s' % ', '.join(_missing))


def _params(xfail):
    params = []
    for shell in SHELLS:
        marks = ()
        reason = xfail.get(shell.name)
        if reason:
            marks = pytest.mark.xfail(strict=True, reason=reason)
        params.append(pytest.param(shell, marks=marks, id=shell.name))
    return params


# one decorator per set of known-broken shells: each runs the test in every
# shell, and names the shells whose nodeenv bug makes it fail there.  A test
# picks the decorator that lists the bugs it is able to trip over.
every_shell = pytest.mark.parametrize('shell', _params({}))
activating_shell = pytest.mark.parametrize(
    'shell', _params({'zsh': ZSH_SOURCE_GUARD}))
restoring_shell = pytest.mark.parametrize(
    'shell', _params({'zsh': ZSH_SOURCE_GUARD,
                      'fish': FISH_NODE_PATH_CLOBBER}))
path_shell = pytest.mark.parametrize(
    'shell', _params({'zsh': ZSH_SOURCE_GUARD,
                      'fish': FISH_CARET_REDIRECT}))


def _binary(shell):
    """Path to the shell, or skip when it is not installed."""
    path = shutil.which(shell.name)
    if path:
        return path
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

    NODE_VIRTUAL_ENV_DISABLE_PROMPT would turn off the very prompt
    test_prompt_override checks, and bash sources BASH_ENV for `bash -c`,
    so both are dropped too.
    """
    ignored = ('NODE_VIRTUAL_ENV', 'NODE_PATH', 'NPM_CONFIG_PREFIX',
               'NODE_VIRTUAL_ENV_DISABLE_PROMPT', 'BASH_ENV')
    result = dict(
        (k, v) for k, v in os.environ.items()
        if not k.startswith('_OLD_')
        and not k.startswith('npm_config_')
        and k not in ignored)
    result.update(BASE_ENV)
    result.update(HOME=env.home, XDG_CONFIG_HOME=env.home, ZDOTDIR=env.home)
    return result


def _launch(shell, env, lines):
    """
    Run `lines` in the shell and return its stdout.

    The shell runs in env.home, not in the checkout pytest was started
    from, so the result does not depend on where the tests were invoked
    and fish's stock prompt cannot append the vcs ref of the work tree.
    _real() still resolves against pytest's own cwd, so a relative value
    coming back from a shell is reported against the checkout.
    """
    out = subprocess.check_output(
        [_binary(shell), '-c', '\n'.join(lines)],
        env=_child_env(env), cwd=env.home)
    return out.decode('utf-8')


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
    out = _launch(shell, env, lines)
    _, sentinel, dump = out.partition(DUMP_SENTINEL + '\n')
    assert sentinel, 'no dump in the output of %s: %r' % (shell.name, out)
    return dict(line.split('=', 1) for line in dump.splitlines())


@every_shell
def test_syntax(shell, env):
    subprocess.check_call([_binary(shell), '-n', env.script(shell)])


@path_shell
def test_activate_sets_env(shell, env):
    dump = run(shell, env)
    baseline = run(shell, env, source=False)

    assert _real(dump['NODE_VIRTUAL_ENV']) == _real(env.path)
    # the whole PATH, not just its head: an activation script must prepend
    # the two entries and leave the rest of the search path untouched
    assert [_real(p) for p in dump['PATH'].split(os.pathsep)] == [
        _real(os.path.join(env.path, 'lib', 'node_modules', '.bin')),
        _real(os.path.join(env.path, 'bin')),
    ] + [_real(p) for p in baseline['PATH'].split(os.pathsep)]
    # only the first component: activate.fish prepends when NODE_PATH is
    # set and, while FISH_NODE_PATH_CLOBBER stands, it never sees one, so
    # fish replaces just like the POSIX script.  FISH_CARET_REDIRECT keeps
    # this test xfail under fish anyway, so the tolerance is for later
    assert _real(dump['NODE_PATH'].split(os.pathsep)[0]) == \
        _real(os.path.join(env.path, 'lib', 'node_modules'))
    assert _real(dump['NPM_CONFIG_PREFIX']) == _real(env.path)
    assert _real(dump['npm_config_prefix']) == _real(env.path)


@restoring_shell
def test_deactivate_restores_env(shell, env):
    dump = run(shell, env, ['deactivate_node'])

    assert dump['NODE_VIRTUAL_ENV'] == UNSET
    assert dump['NODE_PATH'] == BASE_ENV['NODE_PATH']
    assert dump['NPM_CONFIG_PREFIX'] == BASE_ENV['NPM_CONFIG_PREFIX']
    assert dump['npm_config_prefix'] == BASE_ENV['npm_config_prefix']


@activating_shell
def test_activate_deactivate_twice(shell, env):
    baseline = run(shell, env, source=False)
    again = shell.source_line(env.script(shell))
    dump = run(shell, env, ['deactivate_node', again, 'deactivate_node'])

    assert dump['PATH'] == baseline['PATH']


@activating_shell
def test_isolate_npm_roundtrip(shell, env):
    active = run(shell, env)
    restored = run(shell, env, ['deactivate_node'])

    for name, leaf in ISOLATED_NPM:
        if env.isolate_npm:
            assert _real(active[name]) == _real(os.path.join(env.path, leaf))
        else:
            assert active[name] == BASE_ENV[name]
        assert restored[name] == BASE_ENV[name]


def _fish_prompt_output(shell, env, steps=()):
    """
    stdout of fish's prompt function after sourcing and running `steps`.

    The override marker is set unconditionally after the fish_prompt body,
    so the marker alone cannot tell a working prompt from a broken one.
    """
    lines = [shell.source_line(env.script(shell))]
    lines.extend(steps)
    lines.append('fish_prompt')
    return _launch(shell, env, lines)


def _freeze(shell, env, args=''):
    """
    Install the stub npm and run `freeze` in the activated shell.

    The stub goes next to the stub node, which activation puts at the head
    of PATH, so it shadows any npm installed on the machine.
    """
    npm = os.path.join(env.path, 'bin', 'npm')
    with open(npm, 'w') as fd:
        fd.write(NPM_STUB
                 .replace('__GLOBAL__', '\n'.join(GLOBAL_LISTING))
                 .replace('__LOCAL__', '\n'.join(LOCAL_LISTING)))
    os.chmod(npm, 0o755)

    lines = [shell.source_line(env.script(shell)),
             ('freeze %s' % args).strip()]
    return _launch(shell, env, lines)


@activating_shell
def test_freeze_lists_packages(shell, env):
    assert _freeze(shell, env).splitlines() == FROZEN_GLOBAL


@activating_shell
def test_freeze_local(shell, env):
    assert _freeze(shell, env, '-l').splitlines() == FROZEN_LOCAL


@activating_shell
def test_freeze_writes_file(shell, env, tmpdir):
    target = tmpdir.join('node-requirements.txt')
    _freeze(shell, env, nodeenv._quote(str(target)))

    assert target.read().splitlines() == FROZEN_GLOBAL


@activating_shell
def test_prompt_override(shell, env):
    active = run(shell, env)
    restored = run(shell, env, ['deactivate_node'])
    prompt = '(%s)' % os.path.basename(env.path)

    if shell.name == 'fish':
        # fish swaps the fish_prompt function instead of setting PS1 and
        # records the override in _OLD_NODE_FISH_PROMPT_OVERRIDE
        assert _real(active['_OLD_NODE_FISH_PROMPT_OVERRIDE']) == \
            _real(env.path)
        assert restored['_OLD_NODE_FISH_PROMPT_OVERRIDE'] == UNSET
        assert prompt in _fish_prompt_output(shell, env)
        assert prompt not in _fish_prompt_output(
            shell, env, ['deactivate_node'])
    else:
        assert active['PS1'] == '%s %s' % (prompt, BASE_ENV['PS1'])
        assert restored['PS1'] == BASE_ENV['PS1']
