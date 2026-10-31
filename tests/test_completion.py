"""
Tests for `nodeenv --print-completion SHELL`.

The unit tests check the flag itself.  The behavioural tests load the
printed script into bash, zsh, fish and PowerShell, ask the shell for the
candidates of a command line and check what it offers.
"""
import os
import select
import shutil
import subprocess
import sys
import time
import types

from unittest import mock
import pytest

import nodeenv

shtab = pytest.importorskip('shtab')

# CI sets this so a missing shell fails the run instead of skipping it
REQUIRE_SHELLS = os.environ.get('NODEENV_REQUIRE_SHELLS') == '1'

# Require CI shells at collection time, before launching any subprocess
if REQUIRE_SHELLS:
    _required = ('bash', 'zsh', 'fish', 'pwsh')
    if nodeenv.is_WIN:
        _required = ('pwsh',)
    _missing = [name for name in _required if not shutil.which(name)]
    if _missing:
        raise RuntimeError('missing shells: %s' % ', '.join(_missing))

posix_only = pytest.mark.skipif(
    nodeenv.is_WIN, reason='the shell under test is POSIX only')

# options that take free text, there is nothing to complete for them
FREE_TEXT = ('mirror', 'jobs', 'load_average', 'prompt')

NO_OPTIONS = {'--no-clean-src', '--no-npm-clean', '--no-parallel-extract'}

# command line -> (candidates that must be offered, candidates that must
# not be); None in place of the second set means nothing else may be offered
CASES = {
    'nodeenv --no-': (NO_OPTIONS, None),
    'nodeenv --clean': ({'--clean-src'}, None),
    'nodeenv -C ': ({'requirements.txt'}, set()),
    'nodeenv -r ': ({'requirements.txt'}, set()),
    'nodeenv -p ': ({'envs'}, {'requirements.txt'}),
    'nodeenv --force ': ({'envs'}, set()),
    'nodeenv --node ': (
        {'latest', 'lts'} if nodeenv.is_WIN else {'latest', 'lts', 'system'},
        None),
    'nodeenv -n l': ({'latest', 'lts'}, None),
    'nodeenv --npm ': ({'latest'}, None),
}

every_case = pytest.mark.parametrize('line', sorted(CASES))

# the file each shell loads the script from
SCRIPT_NAMES = {
    'bash': 'nodeenv.bash',
    'zsh': '_nodeenv',
    'fish': 'nodeenv.fish',
    'powershell': 'nodeenv.ps1',
}


def _binary(name):
    """Path to the shell, or skip when it is not installed."""
    path = shutil.which(name)
    if path:
        return path
    return pytest.skip('%s is not installed' % name)


def _names(candidates):
    """Candidates without `./` or `.\\` in front and `/` or `\\` at the end."""
    result = set()
    for candidate in candidates:
        for prefix in ('./', '.\\'):
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix):]
        candidate = candidate.rstrip('/\\')
        if candidate:
            result.add(candidate)
    return result


def _check(line, candidates):
    offered, absent = CASES[line]
    got = _names(candidates)
    if absent is None:
        assert got == offered
        return
    assert offered <= got
    assert not absent & got


def _completion_action(parser):
    return [a for a in parser._actions if a.dest == 'print_completion'][0]


def _print_in_process(shell, capsys):
    """The script printed by the flag, as a string."""
    with pytest.raises(SystemExit) as excinfo:
        nodeenv.make_parser().parse_args(['--print-completion', shell])
    assert excinfo.value.code == 0
    return capsys.readouterr().out


@pytest.fixture(scope='module')
def scripts(tmp_path_factory):
    """
    Path to the script `python nodeenv.py --print-completion SHELL`
    prints, made once per shell.

    Running the file rather than the `nodeenv` command also checks that
    the script completes `nodeenv` and not `nodeenv.py`.
    """
    made = {}
    base = tmp_path_factory.mktemp('scripts')

    def get(shell):
        if shell not in made:
            out = subprocess.check_output(
                [sys.executable, nodeenv.__file__,
                 '--print-completion', shell])
            path = base / shell / SCRIPT_NAMES[shell]
            path.parent.mkdir()
            path.write_bytes(out)
            made[shell] = str(path)
        return made[shell]

    return get


@pytest.fixture
def workdir(tmpdir):
    """
    A directory with one file and one directory to complete, an empty
    home and a stub `nodeenv` on PATH.

    The fish header of shtab asks for the command on PATH, and PowerShell
    may not call a native completer for a command it cannot find.
    """
    work = tmpdir.join('work').ensure(dir=True)
    work.join('requirements.txt').write('')
    work.join('envs').ensure(dir=True)
    home = tmpdir.join('home').ensure(dir=True)
    stub_dir = tmpdir.join('bin').ensure(dir=True)
    if nodeenv.is_WIN:
        stub_dir.join('nodeenv.cmd').write('@exit /b 0\r\n')
    else:
        stub = stub_dir.join('nodeenv')
        stub.write('#!/bin/sh\nexit 0\n')
        stub.chmod(0o755)

    # no user rc files, and bash sources BASH_ENV for `bash -c`
    env = dict(os.environ)
    env.pop('BASH_ENV', None)
    env.update(
        HOME=str(home), XDG_CONFIG_HOME=str(home), ZDOTDIR=str(home),
        PATH=str(stub_dir) + os.pathsep + os.environ.get('PATH', ''))
    return types.SimpleNamespace(path=str(work), home=str(home), env=env)


def _fish(script, line, workdir):
    out = subprocess.check_output(
        [_binary('fish'), '--no-config', '-c',
         'source $argv[1]; complete -C $argv[2]', script, line],
        cwd=workdir.path, env=workdir.env)
    return [row.split('\t')[0] for row in out.decode('utf-8').splitlines()]


# Calls the function the script registers for `nodeenv` the way bash does
# on Tab: $1 is the script, the rest are the words of the command line.
BASH_DRIVER = r'''
source "$1"
shift
spec=$(complete -p nodeenv) || exit 1
fn=${spec##*-F }
fn=${fn%% *}
COMP_WORDS=("$@")
COMP_CWORD=$(( ${#COMP_WORDS[@]} - 1 ))
COMP_LINE="$*"
COMP_POINT=${#COMP_LINE}
"$fn" nodeenv "${COMP_WORDS[COMP_CWORD]}" "${COMP_WORDS[COMP_CWORD-1]}"
printf '%s\n' "${COMPREPLY[@]}"
'''


def _bash(script, line, workdir):
    out = subprocess.check_output(
        [_binary('bash'), '-c', BASH_DRIVER, 'bash', script] +
        line.split(' '),
        cwd=workdir.path, env=workdir.env)
    return out.decode('utf-8').splitlines()


PWSH_DRIVER = (
    '. $env:NODEENV_TEST_SCRIPT; '
    '$line = $env:NODEENV_TEST_LINE; '
    '(TabExpansion2 -inputScript $line -cursorColumn $line.Length)'
    '.CompletionMatches | ForEach-Object CompletionText')


def _pwsh(script, line, workdir):
    env = dict(workdir.env, NODEENV_TEST_SCRIPT=script,
               NODEENV_TEST_LINE=line)
    out = subprocess.check_output(
        [_binary('pwsh'), '-NoProfile', '-NonInteractive', '-Command',
         PWSH_DRIVER],
        cwd=workdir.path, env=env)
    return out.decode('utf-8').splitlines()


# Sourced by an interactive zsh: loads the script the way README tells
# users to, then records every match completion adds into a file.
ZSH_SETUP = '''\
bindkey -e
%(load)s
_nodeenv_capture() {
  compadd() {
    local -a matches
    builtin compadd -O matches "$@"
    print -rl -- $matches >> '%(capture)s'
    builtin compadd "$@"
  }
}
compprefuncs=(_nodeenv_capture)
print -r -- READY-$((6 * 7))
'''

ZSH_LOADERS = {
    # the script as _nodeenv in a directory on fpath
    'fpath': ("fpath=('%(dir)s' $fpath)\n"
              "autoload -Uz compinit && compinit -u -D"),
    # the script evaluated after compinit
    'eval': ("autoload -Uz compinit && compinit -u -D\n"
             "eval \"$(<'%(script)s')\""),
}

ZSH_TIMEOUT = 20

# zsh turns bracketed paste on when its line editor starts reading a line
BRACKETED_PASTE = b'\x1b[?2004h'


def _read_until(fd, marker, output, start=0):
    """
    Read the terminal until `marker` shows up in it after `start`, and
    return the position right after the marker.

    The command line zsh echoes back holds `$((6 * 7))`, so only the output
    of the command itself can contain READY-42 or DONE-42.
    """
    deadline = time.time() + ZSH_TIMEOUT
    while output.find(marker, start) < 0:
        if time.time() > deadline:
            raise AssertionError('no %r from zsh, got: %r' % (
                marker, bytes(output[-2000:])))
        ready, _, _ = select.select([fd], [], [], 0.1)
        if ready:
            try:
                output.extend(os.read(fd, 65536))
            except OSError:
                raise AssertionError('zsh exited: %r' % bytes(output))
    return output.find(marker, start) + len(marker)


def _zsh(script, line, workdir, load='fpath'):
    """
    Type `line` and Tab into an interactive zsh and return the matches.

    zsh only completes in its line editor, so it runs on a pseudo terminal.
    After Tab the test kills the line and runs a command that prints a
    marker: zsh handles keys in order, so the marker means completion has
    finished and every match is in the capture file.
    """
    import pty

    capture = os.path.join(workdir.home, 'candidates')
    setup = os.path.join(workdir.home, 'setup.zsh')
    with open(setup, 'w') as f:
        f.write(ZSH_SETUP % {
            'load': ZSH_LOADERS[load] % {
                'dir': os.path.dirname(script), 'script': script},
            'capture': capture,
        })

    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [_binary('zsh'), '-f', '-i'],
        stdin=slave, stdout=slave, stderr=slave,
        cwd=workdir.path, env=dict(workdir.env, TERM='xterm'),
        close_fds=True)
    os.close(slave)
    output = bytearray()
    try:
        os.write(master, ("source '%s'\n" % setup).encode())
        ready = _read_until(master, b'READY-42', output)
        # Keys typed before the line editor takes the terminal go through
        # the terminal driver, which keeps Ctrl+U for itself
        _read_until(master, BRACKETED_PASTE, output, ready)
        # Ctrl+U kills the line in the emacs keymap
        os.write(master, (
            line + '\t\x15print -r -- DONE-$((6 * 7))\n').encode())
        _read_until(master, b'DONE-42', output)
    finally:
        proc.kill()
        proc.wait()
        os.close(master)

    if not os.path.exists(capture):
        return []
    with open(capture) as f:
        return f.read().splitlines()


def test_help_shows_the_flag_without_shtab():
    with mock.patch.dict(sys.modules, {'shtab': None}):
        help_text = nodeenv.make_parser().format_help()
    assert '--print-completion SHELL' in help_text
    assert 'powershell' in help_text


def test_unknown_shell_is_rejected(capsys):
    with pytest.raises(SystemExit) as excinfo:
        nodeenv.make_parser().parse_args(['--print-completion', 'tcsh'])
    assert excinfo.value.code == 2
    assert 'powershell' in capsys.readouterr().err


@pytest.mark.parametrize('shell', ('bash', 'zsh', 'fish', 'powershell'))
def test_main_prints_the_script_without_dest_dir(
        shell, tmpdir, monkeypatch, capsys):
    monkeypatch.chdir(tmpdir)
    argv = ['nodeenv', '--print-completion', shell]
    with mock.patch.object(sys, 'argv', argv):
        with pytest.raises(SystemExit) as excinfo:
            nodeenv.main()
    assert excinfo.value.code == 0
    assert 'nodeenv' in capsys.readouterr().out
    assert tmpdir.listdir() == []


def test_without_shtab_names_the_extra(capsys):
    with mock.patch.dict(sys.modules, {'shtab': None}):
        with pytest.raises(SystemExit) as excinfo:
            nodeenv.make_parser().parse_args(['--print-completion', 'fish'])
    assert excinfo.value.code == 2
    out, err = capsys.readouterr()
    assert out == ''
    assert 'pip install "nodeenv[completion]"' in err


def _shtab_without_powershell(monkeypatch):
    # shtab 1.11 knows fish, but not PowerShell (1.12)
    monkeypatch.setattr(
        shtab, 'SUPPORTED_SHELLS', ['bash', 'zsh', 'tcsh', 'fish'])
    return 'powershell'


def _shtab_without_cmd(monkeypatch):
    # shtab 1.9 knows fish, but not shtab.cmd (1.10)
    monkeypatch.delattr(shtab, 'cmd')
    return 'fish'


@pytest.mark.parametrize(
    'make_old', (_shtab_without_powershell, _shtab_without_cmd),
    ids=('no-powershell', 'no-cmd'))
def test_old_shtab_asks_for_an_upgrade(make_old, monkeypatch, capsys):
    shell = make_old(monkeypatch)
    with pytest.raises(SystemExit) as excinfo:
        nodeenv.make_parser().parse_args(['--print-completion', shell])
    assert excinfo.value.code == 2
    out, err = capsys.readouterr()
    assert out == ''
    assert 'pip install -U "nodeenv[completion]"' in err


def test_every_option_with_a_value_is_classified():
    """
    A new option that takes a path has to be marked, or fish and zsh
    offer nothing after it.
    """
    parser = nodeenv.make_parser()
    action = _completion_action(parser)
    marked = set(action.file_dests + action.dir_dests + ('node', 'npm'))
    for option in parser._actions:
        if option.nargs == 0 or option.choices:
            continue
        assert option.dest in marked | set(FREE_TEXT), option.dest
    if not nodeenv.is_WIN:
        # a renamed dest would silently lose its mark
        assert marked <= set(a.dest for a in parser._actions)


@posix_only
@every_case
def test_fish(line, scripts, workdir):
    _check(line, _fish(scripts('fish'), line, workdir))


@posix_only
@every_case
def test_bash(line, scripts, workdir):
    _check(line, _bash(scripts('bash'), line, workdir))


@posix_only
@every_case
def test_zsh(line, scripts, workdir):
    _check(line, _zsh(scripts('zsh'), line, workdir))


@posix_only
def test_zsh_eval(scripts, workdir):
    line = 'nodeenv --no-'
    _check(line, _zsh(scripts('zsh'), line, workdir, load='eval'))


@every_case
def test_pwsh(line, scripts, workdir):
    _check(line, _pwsh(scripts('powershell'), line, workdir))


@posix_only
def test_module_run_completes_nodeenv(workdir, tmpdir):
    env = dict(os.environ, PYTHONPATH=os.path.dirname(nodeenv.__file__))
    out = subprocess.check_output(
        [sys.executable, '-m', 'nodeenv', '--print-completion', 'fish'],
        cwd=str(tmpdir), env=env)
    script = tmpdir.join('nodeenv.fish')
    script.write_binary(out)
    assert _names(_fish(str(script), 'nodeenv --no-', workdir)) == NO_OPTIONS


@posix_only
def test_windows_script(scripts, workdir, tmpdir, capsys):
    """
    The script follows the platform it is printed on: no `system` node and
    no Unix-only options on Windows.
    """
    with mock.patch.object(nodeenv, 'is_WIN', True):
        out = _print_in_process('fish', capsys)
    script = tmpdir.join('nodeenv.fish')
    script.write(out)

    node = _fish(str(script), 'nodeenv --node ', workdir)
    assert _names(node) == {'latest', 'lts'}
    # a prefix every option matches, so fish does not fall back to fuzzy
    # matching
    unix_only = {'--source', '--jobs', '--make'}
    windows = _names(_fish(str(script), 'nodeenv --', workdir))
    assert '--prebuilt' in windows
    assert not unix_only & windows
    unix = _names(_fish(scripts('fish'), 'nodeenv --', workdir))
    assert unix_only <= unix
