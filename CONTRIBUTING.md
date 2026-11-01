# Contributing to nodeenv

This guide describes how to set up nodeenv for development, which checks a
change has to pass, and how to send it.

## Development environment

nodeenv is a single module, `nodeenv.py`; the tests live in `tests/`.

On Linux and macOS:

```sh
make env-dev
. env-dev/bin/activate
```

`make env-dev` creates the `env-dev` virtual environment and installs
`requirements-dev.txt` into it, nodeenv itself included as an editable
install.

On Windows, without make:

```bat
py -m venv env-dev
env-dev\Scripts\activate.bat
pip install -r requirements-dev.txt
```

## Tests and lint

The main check is tox. It runs the unit tests with coverage and flake8, as
CI does:

```sh
tox -e py314
```

Any of `py310` to `py314` works, depending on the Python versions you have.
`tox.ini` has the exact commands; without tox they are:

```sh
coverage run -p -m pytest -m 'not integration' tests
flake8 --extend-ignore=E127 nodeenv.py tests
```

CI runs them on Python 3.10 to 3.14 on Ubuntu, macOS and Windows.

The activation script tests run the generated scripts in sh, dash, bash, zsh
and fish. A shell that is not installed is skipped. Set
`NODEENV_REQUIRE_SHELLS=1` to make a missing shell other than dash a
failure, as CI does:

```sh
NODEENV_REQUIRE_SHELLS=1 pytest tests/test_activate_shells.py
```

Tests marked `integration` create real node environments and download
node, so they are slow and need network access. tox leaves them out; run
them with:

```sh
pytest -m integration tests/
```

A bare `pytest tests/` runs everything, the integration tests included.

## Code style

- All text, comments included, is in English.
- Lines are at most 79 characters long; flake8 reports longer ones as E501.
- Every file ends with a single newline.
- Prefer early returns to nested conditions.
- Every change comes with tests that cover it.
- Keep `README.rst` accurate: update it when a change affects what it
  documents.

## Commits and pull requests

Commit messages and pull request titles use the
[Conventional Commits](https://www.conventionalcommits.org/) form
`type(scope): subject`, for example:

```text
fix(nodeenv): report a missing node archive instead of a traceback
```

The types are `feat`, `fix`, `docs`, `refactor`, `perf`, `chore` and
`test`. The scope names the part of the project the change is about:
`nodeenv` for `nodeenv.py`, `readme`, `ci`, `tox`, and so on. Changes to
the GitHub workflows use `chore(ci)`.

When a pull request is squash-merged, the commit subject comes from the pull
request title or, for a single commit, from that commit, so both need the
same form.

In the pull request description, link the issue it fixes, for example
`Fixes #NNN`, so that GitHub closes the issue on merge.

If your branch conflicts with `master`, for example in `CHANGES`, rebase it
on `master`.

## Changelog

A change in how nodeenv behaves gets an entry under `Version [unreleased]`
at the top of `CHANGES`, with a link to its issue:

```rst
- What changed for the user, in a sentence or two
  `#NNN <https://github.com/ekalinin/nodeenv/issues/NNN>`_
```

Changes to documentation, CI or tests only don't need an entry.
