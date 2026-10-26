from types import SimpleNamespace

import pytest

import nodeenv


pytestmark = pytest.mark.skipif(
    nodeenv.is_WIN, reason='source builds use POSIX configure scripts')


def _script(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#!/bin/sh\n' + contents)
    path.chmod(0o755)
    return path


def _build(tmp_path, node='8.7.0'):
    source = tmp_path / 'src' / ('node-v' + node)
    _script(source / 'configure',
            'exec python configure-argument "argument with spaces"\n')
    make = _script(tmp_path / 'make', 'exit 0\n')
    args = SimpleNamespace(
        node=node, load_average=None, jobs='2', without_ssl=False,
        debug=False, profile=False, make_path=str(make), verbose=False)
    nodeenv.build_node_from_src(
        str(tmp_path / 'env'), str(source.parent), str(source), args)


@pytest.mark.parametrize('case', [
    'python2.7', 'dangling-link', 'stale-link', 'shim', 'relative-path',
])
def test_legacy_build_selects_python_without_reusing_a_link(
        tmp_path, monkeypatch, case):
    tools = tmp_path / 'selected tools'
    name = 'python2.7' if case == 'python2.7' else 'python2'
    python = _script(
        tools / name,
        '[ "${0##*/}" = "' + name + '" ] || exit 19\n'
        'printf "%s\\n" "$0" "$@" >> "$PYTHON_LOG"\n')
    log = tmp_path / 'python.log'
    monkeypatch.setenv('PYTHON_LOG', str(log))
    monkeypatch.chdir(tmp_path)
    path = str(tools) if case != 'relative-path' else tools.name
    monkeypatch.setenv('PATH', path)

    launcher = tmp_path / 'src' / 'tmpbin' / 'python'
    old = tmp_path / 'old' / 'python2'
    if case in ('stale-link', 'dangling-link'):
        launcher.parent.mkdir(parents=True)
        if case == 'stale-link':
            _script(old, 'exit 23\n')
        launcher.symlink_to(old)

    _build(tmp_path)

    assert log.read_text().splitlines() == [
        str(python), 'configure-argument', 'argument with spaces']
    if case == 'stale-link':
        assert old.read_text() == '#!/bin/sh\nexit 23\n'


def test_legacy_build_refreshes_launcher_on_retry(tmp_path, monkeypatch):
    log = tmp_path / 'python.log'
    monkeypatch.setenv('PYTHON_LOG', str(log))
    for label in ('first', 'second'):
        tools = tmp_path / label
        _script(tools / 'python2',
                'printf "%s\\n" "' + label + '" >> "$PYTHON_LOG"\n')
        monkeypatch.setenv('PATH', str(tools))
        _build(tmp_path)
    assert log.read_text().splitlines() == ['first', 'second']
