from __future__ import absolute_import
from __future__ import unicode_literals

import io
import os.path
import subprocess

import pytest

from nodeenv import GetsAHrefs


HERE = os.path.abspath(os.path.dirname(__file__))


def test_gets_a_hrefs_trivial():
    parser = GetsAHrefs()
    parser.feed('')
    assert parser.hrefs == []


def test_gets_a_hrefs_nodejs_org():
    # Retrieved 2015-01-15
    contents = io.open(os.path.join(HERE, 'nodejs.htm')).read()
    parser = GetsAHrefs()
    parser.feed(contents)
    # Smoke test
    assert parser.hrefs == [
        '../', 'docs/', 'x64/', 'SHASUMS.txt', 'SHASUMS.txt.asc',
        'SHASUMS.txt.gpg', 'SHASUMS256.txt', 'SHASUMS256.txt.asc',
        'SHASUMS256.txt.gpg', 'node-v0.10.35-darwin-x64.tar.gz',
        'node-v0.10.35-darwin-x86.tar.gz', 'node-v0.10.35-linux-x64.tar.gz',
        'node-v0.10.35-linux-x86.tar.gz', 'node-v0.10.35-sunos-x64.tar.gz',
        'node-v0.10.35-sunos-x86.tar.gz', 'node-v0.10.35-x86.msi',
        'node-v0.10.35.pkg', 'node-v0.10.35.tar.gz', 'node.exe',
        'node.exp', 'node.lib', 'node.pdb', 'openssl-cli.exe',
        'openssl-cli.pdb',
    ]


def test_gets_a_hrefs_iojs_org():
    # Retrieved 2015-01-15
    contents = io.open(os.path.join(HERE, 'iojs.htm')).read()
    parser = GetsAHrefs()
    parser.feed(contents)
    # Smoke test
    assert parser.hrefs == [
        '../', 'doc/', 'win-x64/', 'win-x86/', 'SHASUMS256.txt',
        'SHASUMS256.txt.asc', 'SHASUMS256.txt.gpg',
        'iojs-v1.0.1-darwin-x64.tar.gz', 'iojs-v1.0.1-linux-armv7l.tar.gz',
        'iojs-v1.0.1-linux-armv7l.tar.xz', 'iojs-v1.0.1-linux-x64.tar.gz',
        'iojs-v1.0.1-linux-x64.tar.xz', 'iojs-v1.0.1-linux-x86.tar.gz',
        'iojs-v1.0.1-linux-x86.tar.xz', 'iojs-v1.0.1-x64.msi',
        'iojs-v1.0.1-x86.msi', 'iojs-v1.0.1.pkg', 'iojs-v1.0.1.tar.gz',
        'iojs-v1.0.1.tar.xz',
    ]


@pytest.mark.integration
def test_smoke(tmpdir):
    nenv_path = tmpdir.join('nenv').strpath
    subprocess.check_call([
        # Enable coverage
        'coverage', 'run', '-p',
        '-m', 'nodeenv', '--prebuilt', nenv_path,
    ])
    assert os.path.exists(nenv_path)
    subprocess.check_call([
        'sh', '-c', '. {0}/bin/activate && nodejs --version'.format(nenv_path),
    ])
