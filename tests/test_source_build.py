import json
import sys
from argparse import Namespace

import pytest

import nodeenv


pytestmark = pytest.mark.skipif(
    nodeenv.is_WIN, reason='source builds are POSIX only')


def _record_script(path, log):
    record = ('import json, sys; '
              'open(%r, "a").write(json.dumps(sys.argv[1:]) + "\\n")'
              % str(log))
    path.write('#!/bin/sh\n%s -c %s "$@"\n' % (
        nodeenv._quote(sys.executable), nodeenv._quote(record)))
    path.chmod(0o755)


@pytest.fixture
def source_build(tmpdir):
    source = tmpdir.join('node-src').ensure(dir=True)
    _record_script(source.join('configure'),
                   source.join('configure-args.jsonl'))
    make = tmpdir.join('make')
    _record_script(make, source.join('make-args.jsonl'))
    args = Namespace(node='22.11.0', make_path=str(make), jobs='2',
                     load_average=None, without_ssl=False, debug=False,
                     profile=False, verbose=False)
    return source, make, args


@pytest.mark.parametrize('jobs,load_average,expected', (
    ('2', None, ['--jobs=2']),
    ('2', '3', ['--load-average=3', '--jobs=2']),
    ('', '', ['--load-average', '--jobs']),
    (None, None, []),
    ('2; touch injected-jobs', '3; touch injected-load',
     ['--load-average=3; touch injected-load',
      '--jobs=2; touch injected-jobs']),
    ('$(touch injected-jobs)', '`touch injected-load`',
     ['--load-average=`touch injected-load`',
      '--jobs=$(touch injected-jobs)']),
))
def test_source_build_preserves_make_arguments(tmpdir, source_build,
                                               jobs, load_average, expected):
    source, make, args = source_build
    args.jobs = jobs
    args.load_average = load_average
    env_dir = str(tmpdir.join('env with spaces'))

    nodeenv.build_node_from_src(env_dir, str(tmpdir), str(source), args)

    assert [json.loads(line) for line in source.join(
        'make-args.jsonl').read().splitlines()] == [expected, ['install']]
    configure_args = source.join('configure-args.jsonl').read().splitlines()
    assert [json.loads(line) for line in configure_args] == [
        ['--prefix=' + env_dir]]
    assert not source.join('injected-jobs').exists()
    assert not source.join('injected-load').exists()


@pytest.mark.parametrize('command', ('arguments', 'wrapper', 'tilde',
                                     'variable', 'quoted-path'))
def test_source_build_make_is_a_command_line(tmpdir, monkeypatch, source_build,
                                              command):
    source, make, args = source_build
    expected = [['--jobs=2'], ['install']]
    if command == 'arguments':
        args.make_path = str(make) + ' -s'
        expected = [['-s', '--jobs=2'], ['-s', 'install']]
    elif command == 'wrapper':
        args.make_path = 'env ' + nodeenv._quote(str(make))
    elif command == 'tilde':
        monkeypatch.setenv('HOME', str(tmpdir))
        args.make_path = '~/make'
    elif command == 'variable':
        monkeypatch.setenv('NODEENV_TEST_MAKE', str(make))
        args.make_path = '$NODEENV_TEST_MAKE'
    else:
        make = tmpdir.join('make with spaces')
        _record_script(make, source.join('make-args.jsonl'))
        args.make_path = nodeenv._quote(str(make))

    nodeenv.build_node_from_src(str(tmpdir.join('env')), str(tmpdir),
                                str(source), args)

    assert [json.loads(line) for line in source.join(
        'make-args.jsonl').read().splitlines()] == expected
