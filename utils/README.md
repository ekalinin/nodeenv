# Utilities

## Merge an existing Node environment into a Python venv (Windows)

The goal is simply to add an existing Node installation to an existing
Python environment, so activating Python also selects the project's Node.
`integrate_nodeenv.py` does this for projects that already have a standalone
Node environment in `env` and a Python virtual environment in `.venv`.

**For a new setup, using `nodeenv -p` is strongly recommended.** Create and
activate the Python venv first, then let nodeenv install Node into it:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
nodeenv -p
```

Use the migration utility below when reusing an already installed Node/npm.

From your project's directory, run the utility from this checkout:

```powershell
.\.venv\Scripts\python.exe C:\src\nodeenv\utils\integrate_nodeenv.py --dry-run
.\.venv\Scripts\python.exe C:\src\nodeenv\utils\integrate_nodeenv.py
```

Use `--source PATH` and `--venv PATH` for different directory names. Defaults
are relative to the working directory, so the utility can stay in `utils`.

- Missing files and directories are moved without overwriting existing ones.
- Existing destination files win; their source copies remain in `env`.
- Activation and deactivation are patched for CMD, PowerShell and Git Bash.
- Repeated runs leave recognized patches unchanged. Unknown layouts stop the
  operation before any files are moved.
- After success, the utility reports that you can delete `env`; it never
  deletes the source directory itself.

Requires Windows, Python 3.10+, and source/target directories on the same
filesystem. The Python venv must already exist. Only recognized CPython
activation layouts are accepted. Editing a signed `Activate.ps1` removes
its original signature; PowerShell's execution policy is not changed.
