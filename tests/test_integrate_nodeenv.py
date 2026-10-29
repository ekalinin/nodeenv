"""Offline tests for merging a Windows Node environment into a Python venv."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest


UTILITY = (Path(__file__).resolve().parents[1] / 'utils' /
           'integrate_nodeenv.py')
SPEC = importlib.util.spec_from_file_location('integrate_nodeenv', UTILITY)
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)

WINDOWS = pytest.mark.skipif(os.name != 'nt', reason='Windows-only utility')

# Small CPython 3.12 activation excerpts, independent of nodeenv's templates.
ACTIVATION = {
    'activate.bat': (
        '@echo off\n'
        'set "VIRTUAL_ENV=C:\\project\\.venv"\n'
        'set "PATH=%VIRTUAL_ENV%\\Scripts;%PATH%"\n'
        'set "VIRTUAL_ENV_PROMPT=(.venv) "\n'
    ),
    'deactivate.bat': (
        '@echo off\n'
        'if defined _OLD_VIRTUAL_PATH (\n'
        '    set "PATH=%_OLD_VIRTUAL_PATH%"\n'
        ')\n'
        'set _OLD_VIRTUAL_PATH=\n'
    ),
    'Activate.ps1': (
        'function global:deactivate ([switch]$NonDestructive) {\n'
        '    # The prior PATH:\n'
        '    if (Test-Path -Path Env:_OLD_VIRTUAL_PATH) {\n'
        '        Copy-Item Env:_OLD_VIRTUAL_PATH Env:PATH\n'
        '    }\n'
        '}\n'
        '# Add the venv to the PATH\n'
        '$env:PATH = "$VenvExecDir$([System.IO.Path]::PathSeparator)" + '
        '$env:PATH\n'
    ),
    'activate': (
        'deactivate () {\n'
        '    # Call hash to forget past locations.\n'
        '    hash -r 2> /dev/null\n'
        '}\n'
        'deactivate nondestructive\n'
        '_OLD_VIRTUAL_PATH="$PATH"\n'
        'PATH="$VIRTUAL_ENV/bin:$PATH"\n'
        'export PATH\n'
    ),
}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def snapshot(root):
    """Include directories and mtimes to detect unwanted moves and rewrites."""
    entries = {}
    for path in root.rglob('*'):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            entries[relative] = None
        else:
            entries[relative] = (path.read_bytes(), path.stat().st_mtime_ns)
    return entries


@pytest.fixture
def environments(tmp_path):
    source = tmp_path / 'env'
    destination = tmp_path / '.venv'
    for name, content in ACTIVATION.items():
        write(destination / 'Scripts' / name, content.encode('utf-8'))
        write(source / 'Scripts' / name, b'source activation retained\n')
    write(destination / 'Scripts' / 'python.exe', b'fake Python executable')
    write(source / 'Scripts' / 'node.exe', b'fake Node executable')
    write(source / 'Scripts' / 'npm.cmd', b'fake npm command')
    return source, destination


def invoke(monkeypatch, source, destination, *options):
    monkeypatch.setattr(sys, 'argv', [
        str(UTILITY), '--source', str(source), '--venv', str(destination),
        *options,
    ])
    migration.main()


def test_moves_missing_entries_and_keeps_destination_collisions(tmp_path):
    source = tmp_path / 'env'
    destination = tmp_path / '.venv'
    write(source / 'Scripts' / 'node.exe', b'node')
    write(source / 'Scripts' / 'activate.bat', b'old activation')
    write(destination / 'Scripts' / 'activate.bat', b'Python activation')
    write(source / 'lib' / 'nested' / 'module.js', b'module')
    (source / 'empty').mkdir()

    moves, skipped = migration.plan_moves(source, destination)
    assert set(moves) == {
        (source / 'Scripts' / 'node.exe',
         destination / 'Scripts' / 'node.exe'),
        (source / 'lib', destination / 'lib'),
        (source / 'empty', destination / 'empty'),
    }
    assert skipped == 1
    for origin, target in moves:
        origin.rename(target)

    assert (destination / 'Scripts' / 'node.exe').read_bytes() == b'node'
    assert (destination / 'lib' / 'nested' / 'module.js').read_bytes() == (
        b'module'
    )
    assert (destination / 'empty').is_dir()
    assert not (source / 'lib').exists()
    assert not (source / 'empty').exists()
    assert (source / 'Scripts' / 'activate.bat').read_bytes() == (
        b'old activation'
    )
    assert (destination / 'Scripts' / 'activate.bat').read_bytes() == (
        b'Python activation'
    )


def test_missing_source_has_no_moves(tmp_path):
    destination = tmp_path / '.venv'
    destination.mkdir()
    assert migration.plan_moves(tmp_path / 'missing', destination) == ([], 0)


@pytest.mark.parametrize('relationship', [
    'same', 'source-child', 'venv-child',
])
def test_overlapping_environments_are_rejected(tmp_path, relationship):
    source = tmp_path / 'env'
    source.mkdir()
    if relationship == 'same':
        destination = source
    elif relationship == 'source-child':
        destination = tmp_path
    else:
        destination = source / '.venv'
        destination.mkdir()
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match='separate'):
        migration.plan_moves(source, destination)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('source_is_directory', [False, True])
def test_file_directory_collision_is_rejected(tmp_path, source_is_directory):
    source = tmp_path / 'env'
    destination = tmp_path / '.venv'
    source.mkdir()
    destination.mkdir()
    directory = source if source_is_directory else destination
    file_root = destination if source_is_directory else source
    (directory / 'conflict').mkdir()
    write(file_root / 'conflict', b'preserve this file')
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match='file/directory collision'):
        migration.plan_moves(source, destination)
    assert snapshot(tmp_path) == before


@WINDOWS
def test_junction_is_planned_as_an_entry_without_traversing_it(tmp_path):
    source = tmp_path / 'env'
    destination = tmp_path / '.venv'
    external = tmp_path / 'external'
    source.mkdir()
    destination.mkdir()
    write(external / 'keep.txt', b'outside environment')
    junction = source / 'linked'
    result = subprocess.run(
        ['cmd.exe', '/d', '/c', 'mklink', '/J', str(junction), str(external)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        pytest.skip('Creating a directory junction is unavailable')
    assert migration.is_link(junction)
    assert not migration.is_directory(junction)
    assert migration.plan_moves(source, destination) == (
        [(junction, destination / 'linked')], 0,
    )
    assert (external / 'keep.txt').read_bytes() == b'outside environment'


@pytest.mark.parametrize('name', ACTIVATION)
@pytest.mark.parametrize('newline', ['\n', '\r\n'])
@pytest.mark.parametrize('bom', [b'', b'\xef\xbb\xbf'])
def test_patch_preserves_encoding_line_endings_and_is_idempotent(
        name, newline, bom):
    original = bom + ACTIVATION[name].replace('\n', newline).encode('utf-8')
    path = Path(name)
    updated = migration.patch_activation(path, original)
    assert updated != original
    assert b'NODE_PATH' in updated
    assert updated.startswith(bom)
    assert updated.count(b'\xef\xbb\xbf') == bool(bom)
    if newline == '\r\n':
        assert b'\n' not in updated.replace(b'\r\n', b'')
    else:
        assert b'\r' not in updated
    assert migration.patch_activation(path, updated) == updated


@pytest.mark.parametrize('name', ACTIVATION)
def test_unfamiliar_node_path_handling_is_rejected(name):
    original = (ACTIVATION[name] + '# custom NODE_PATH handling\n').encode()
    with pytest.raises(ValueError, match='unfamiliar NODE_PATH'):
        migration.patch_activation(Path(name), original)


@pytest.mark.parametrize('name', ACTIVATION)
def test_missing_anchor_is_rejected(name):
    with pytest.raises(ValueError, match='insertion point'):
        migration.patch_activation(Path(name), b'unrecognized activation\n')


def test_mixed_line_endings_are_rejected():
    original = ACTIVATION['activate.bat'].replace('\n', '\r\n', 1)
    with pytest.raises(ValueError, match='line endings'):
        migration.patch_activation(Path('activate.bat'), original.encode())


def test_edited_powershell_signature_is_removed():
    original = ACTIVATION['Activate.ps1'] + (
        '# SIG # Begin signature block\n'
        '# signed content\n'
        '# SIG # End signature block\n'
    )
    updated = migration.patch_activation(
        Path('Activate.ps1'), original.encode())
    assert b'NODE_PATH' in updated
    assert b'# SIG #' not in updated
    assert migration.patch_activation(Path('Activate.ps1'), updated) == updated


def test_unrecognized_powershell_signature_is_rejected():
    original = ACTIVATION['Activate.ps1'] + '# SIG # unexpected signature\n'
    with pytest.raises(ValueError, match='signature block'):
        migration.patch_activation(Path('Activate.ps1'), original.encode())


def test_non_windows_cli_refuses_without_modifying_files(
        environments, monkeypatch, capsys):
    source, destination = environments
    before = snapshot(source.parent)
    monkeypatch.setattr(sys, 'platform', 'linux')
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, source, destination)
    assert error.value.code == 1
    assert snapshot(source.parent) == before
    output = capsys.readouterr()
    assert 'Windows only' in output.err
    assert 'You can now delete' not in output.out


@WINDOWS
def test_dry_run_leaves_both_environments_unchanged(
        environments, monkeypatch, capsys):
    source, destination = environments
    before = snapshot(source.parent)
    invoke(monkeypatch, source, destination, '--dry-run')
    assert snapshot(source.parent) == before
    output = capsys.readouterr().out
    assert 'Would move:' in output
    assert 'Would update:' in output
    assert 'You can now delete' not in output


@WINDOWS
def test_last_script_is_validated_before_any_moves(
        environments, monkeypatch, capsys):
    source, destination = environments
    bash = destination / 'Scripts' / 'activate'
    bash.write_bytes(bash.read_bytes() + b'# custom NODE_PATH handling\n')
    before = snapshot(source.parent)
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, source, destination)
    assert error.value.code == 1
    assert snapshot(source.parent) == before
    output = capsys.readouterr()
    assert 'unfamiliar NODE_PATH' in output.err
    assert 'Moved:' not in output.out
    assert 'You can now delete' not in output.out


@WINDOWS
def test_migration_and_repeat_preserve_collision_copies_and_mtimes(
        environments, monkeypatch, capsys):
    source, destination = environments
    invoke(monkeypatch, source, destination)
    output = capsys.readouterr().out
    assert 'completed successfully' in output
    assert 'You can now delete' in output
    assert (destination / 'Scripts' / 'node.exe').read_bytes() == (
        b'fake Node executable'
    )
    assert not (source / 'Scripts' / 'node.exe').exists()
    for name in ACTIVATION:
        assert (source / 'Scripts' / name).read_bytes() == (
            b'source activation retained\n'
        )
        assert b'NODE_PATH' in (destination / 'Scripts' / name).read_bytes()
    for path in destination.rglob('*'):
        if path.is_file():
            os.utime(path, ns=(1600000000000000000, 1600000000000000000))
    before = snapshot(source.parent)
    invoke(monkeypatch, source, destination)
    assert snapshot(source.parent) == before
    assert 'Already integrated:' in capsys.readouterr().out


@WINDOWS
def test_default_environments_are_relative_to_working_directory(
        environments, monkeypatch):
    source, destination = environments
    monkeypatch.chdir(source.parent)
    monkeypatch.setattr(sys, 'argv', [str(UTILITY)])
    migration.main()
    assert (destination / 'Scripts' / 'node.exe').is_file()
    assert not (source / 'Scripts' / 'node.exe').exists()
