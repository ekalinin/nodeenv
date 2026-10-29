r"""Move a Node environment into a Windows Python venv.

Run from the project directory:
    python path\to\nodeenv\utils\integrate_nodeenv.py --dry-run
    python path\to\nodeenv\utils\integrate_nodeenv.py

Defaults: env -> .venv, relative to the current working directory.
Use --source PATH and --venv PATH to select different directories.

This adds an existing Node installation to an existing Python environment.
For a new setup, create and activate the Python venv and use nodeenv -p.

Contents of env are merged into .venv, preserving relative paths. Missing files
and directories are moved; existing destination entries are never overwritten.
Source copies, including old activation scripts, remain in env. Source and
destination must be separate directories on the same filesystem. Directory
links are treated as entries, not followed; file/directory collisions fail.

The resulting Scripts directory must contain python.exe, node.exe and npm.cmd.
All activation patches are validated before moving anything. The script then
moves missing entries and patches activation/deactivation for CMD, PowerShell
and Git Bash. Repeated runs do not duplicate patches. --dry-run validates and
previews both steps without changing either directory.

Only after both steps succeed, the script reports that env can be deleted.
It never deletes env automatically. Existing destination files take precedence
over the source copies left there.
"""

import argparse
import os
import stat
import sys
from pathlib import Path

PATCHES = {
    'activate.bat': [
        (
            'set "PATH=%VIRTUAL_ENV%\\Scripts;%PATH%"\n',
            'if defined _OLD_VIRTUAL_NODE_PATH '
            'set "NODE_PATH=%_OLD_VIRTUAL_NODE_PATH%"\n'
            'if defined NODE_PATH set "_OLD_VIRTUAL_NODE_PATH=%NODE_PATH%"\n'
            'if defined NODE_PATH set NODE_PATH=\n\n',
        ),
    ],
    'deactivate.bat': [
        (
            'if defined _OLD_VIRTUAL_PATH (\n',
            'if defined _OLD_VIRTUAL_NODE_PATH (\n'
            '    set "NODE_PATH=%_OLD_VIRTUAL_NODE_PATH%"\n'
            '    set _OLD_VIRTUAL_NODE_PATH=\n'
            ')\n\n',
        ),
    ],
    'Activate.ps1': [
        (
            '    # The prior PATH:\n',
            '    # The prior NODE_PATH:\n'
            '    if (Test-Path -Path Env:_OLD_VIRTUAL_NODE_PATH) {\n'
            '        Copy-Item -Path Env:_OLD_VIRTUAL_NODE_PATH '
            '-Destination Env:NODE_PATH\n'
            '        Remove-Item -Path Env:_OLD_VIRTUAL_NODE_PATH\n'
            '    }\n\n',
        ),
        (
            '# Add the venv to the PATH\n',
            '# Clear NODE_PATH\n'
            'if (Test-Path -Path Env:NODE_PATH) {\n'
            '    Copy-Item -Path Env:NODE_PATH '
            '-Destination Env:_OLD_VIRTUAL_NODE_PATH\n'
            '    Remove-Item -Path Env:NODE_PATH\n'
            '}\n\n',
        ),
    ],
    'activate': [
        (
            '    # Call hash to forget past locations.',
            '    if [ "${_OLD_VIRTUAL_NODE_PATH+x}" = x ] ; then\n'
            '        NODE_PATH="$_OLD_VIRTUAL_NODE_PATH"\n'
            '        export NODE_PATH\n'
            '        unset _OLD_VIRTUAL_NODE_PATH\n'
            '    fi\n\n',
        ),
        (
            '_OLD_VIRTUAL_PATH="$PATH"\n',
            '# Clear NODE_PATH\n'
            'if [ "${NODE_PATH+x}" = x ] ; then\n'
            '    _OLD_VIRTUAL_NODE_PATH="$NODE_PATH"\n'
            '    unset NODE_PATH\n'
            'fi\n\n',
        ),
    ],
}


def patch_activation(path, original):
    text = original.decode('utf-8')
    newline = '\r\n' if '\r\n' in text else '\n'
    normalized = text.replace('\r\n', '\n')
    if '\r' in normalized or normalized.replace('\n', newline) != text:
        raise ValueError(f'{path}: unsupported or mixed line endings')

    # Remove recognized blocks first, so rerunning never duplicates them.
    clean = normalized
    for anchor, block in PATCHES[path.name]:
        if clean.count(anchor) != 1:
            raise ValueError(
                f'{path}: expected one insertion point: {anchor.strip()}')
        clean = clean.replace(block + anchor, anchor, 1)
    if 'NODE_PATH' in clean:
        raise ValueError(
            f'{path}: unfamiliar NODE_PATH handling; no files changed')

    updated = clean
    for anchor, block in PATCHES[path.name]:
        updated = updated.replace(anchor, block + anchor, 1)
    if updated == normalized:
        return original

    # An edited PowerShell script can no longer use its original signature.
    if path.name == 'Activate.ps1' and '# SIG #' in updated:
        marker = '# SIG # Begin signature block\n'
        end = '# SIG # End signature block\n'
        if updated.count(marker) != 1 or not updated.endswith(end):
            raise ValueError(
                f'{path}: unfamiliar signature block; no files changed')
        updated = updated.split(marker, 1)[0]
    return updated.replace('\n', newline).encode('utf-8')


def is_link(path):
    # Path.is_junction() is unavailable on Python 3.10 and 3.11.
    attributes = getattr(path.lstat(), 'st_file_attributes', 0)
    return path.is_symlink() or bool(
        attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def is_directory(path):
    return path.is_dir() and not is_link(path)


def plan_moves(source, destination):
    if (source == destination or source.is_relative_to(destination)
            or destination.is_relative_to(source)):
        raise ValueError(
            'Source and destination must be separate, non-nested directories')
    if not destination.is_dir():
        raise ValueError(f'Missing Python venv directory: {destination}')
    if not os.path.lexists(source):
        return [], 0
    if (not source.is_dir()
            or source.stat().st_dev != destination.stat().st_dev):
        raise ValueError(
            'Source must be a directory on the same filesystem as the venv')

    moves = []
    skipped = 0
    pending = [(source, destination)]
    while pending:
        origin, target = pending.pop()
        entries = sorted(
            origin.iterdir(), key=lambda path: path.name.casefold())
        for entry in entries:
            other = target / entry.name
            if not os.path.lexists(other):
                if (not entry.parent.resolve().is_relative_to(source)
                        or not other.parent.resolve().is_relative_to(
                            destination)):
                    raise ValueError(
                        f'Move would leave the source or destination: {entry}')
                moves.append((entry, other))
            elif is_directory(entry) and is_directory(other):
                pending.append((entry, other))
            elif is_directory(entry) != is_directory(other):
                raise ValueError(
                    'Incompatible file/directory collision: '
                    f'{entry} -> {other}')
            else:
                skipped += 1
    return moves, skipped


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--source', type=Path, default=Path('env'),
        help='source Node environment (default: env in the working directory)')
    parser.add_argument(
        '--venv', type=Path, default=Path('.venv'),
        help='target Python venv (default: .venv in the working directory)')
    parser.add_argument(
        '--dry-run', action='store_true',
        help='validate and show changes without writing')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.exit(
            1, 'Error: This migration utility supports Windows only.\n')

    try:
        source = args.source.resolve()
        destination = args.venv.resolve()
        moves, skipped = plan_moves(source, destination)
        scripts = destination / 'Scripts'

        def resulting_file(path):
            if os.path.lexists(path):
                return path
            return source / path.relative_to(destination)

        if not is_directory(resulting_file(scripts)):
            raise ValueError(
                'Scripts must be an ordinary directory, not a directory link')
        for name in ('python.exe', 'node.exe', 'npm.cmd'):
            if not resulting_file(scripts / name).is_file():
                raise ValueError(
                    f'Missing {scripts / name}; '
                    'Python/Node/npm must exist in the target or source')

        # Validate all four resulting files before moving or writing anything.
        changes = []
        for name in PATCHES:
            path = scripts / name
            existing = resulting_file(path)
            if is_link(existing):
                raise ValueError(
                    f'Activation script must not be a link: {existing}')
            original = existing.read_bytes()
            changes.append((path, original, patch_activation(path, original)))

        for origin, target in moves:
            if args.dry_run:
                print(f'Would move: {origin} -> {target}')
            else:
                # On Windows rename fails if the destination already exists.
                origin.rename(target)
                print(f'Moved: {origin} -> {target}')
        print(f'Existing destination entries kept: {skipped}')

        for path, original, updated in changes:
            if updated == original:
                print(f'Already integrated: {path}')
            elif args.dry_run:
                print(f'Would update: {path}')
            else:
                path.write_bytes(updated)
                print(f'Updated: {path}')
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(1, f'Error: {error}\n')

    if not args.dry_run:
        print('Migration and activation patch completed successfully.')
        if source.is_dir():
            print(f'You can now delete the source directory: {source}')


if __name__ == '__main__':
    main()
