import json
import sys
from argparse import Namespace

import pytest

import nodeenv


@pytest.mark.skipif(nodeenv.is_WIN, reason='source builds are POSIX only')
@pytest.mark.parametrize('make_name', ('make', 'make with spaces',
                                       "make'with;special$characters"))
@pytest.mark.parametrize('jobs,load_average', (
    ('2', '3'),
    ('', ''),
    (None, None),
    ('2; touch injected-jobs', '3; touch injected-load'),
    ('$(touch injected-jobs)', '`touch injected-load`'),
))
def test_source_build_preserves_make_arguments(tmpdir, monkeypatch, make_name,
                                               jobs, load_average):
    source = tmpdir.join('node-src').ensure(dir=True)
    configure = source.join('configure')
    configure.write('#!/bin/sh\nexit 0\n')
    configure.chmod(0o755)
    make = tmpdir.join(make_name)
    log = source.join('make-args.jsonl')
    record = ('import json, sys; '
              'open(%r, "a").write(json.dumps(sys.argv[1:]) + "\\n")'
              % str(log))
    make.write('#!/bin/sh\n%s -c %s "$@"\n' % (
        nodeenv._quote(sys.executable), nodeenv._quote(record)))
    make.chmod(0o755)
    # The separate Python 2 requirement is unrelated to shell quoting.
    monkeypatch.setattr(nodeenv.shutil, 'which', lambda name: sys.executable)
    args = Namespace(node='22.11.0', make_path=str(make),
                     jobs=jobs, load_average=load_average,
                     without_ssl=False, debug=False, profile=False,
                     verbose=False)

    nodeenv.build_node_from_src(str(tmpdir.join('env with spaces')),
                                str(tmpdir), str(source), args)

    expected = [
        '--%s=%s' % (name, value) if value else '--%s' % name
        for name, value in (('load-average', load_average), ('jobs', jobs))
        if value is not None
    ]
    assert [json.loads(line) for line in log.read().splitlines()] == [
        expected, ['install']]
    assert not source.join('injected-jobs').exists()
    assert not source.join('injected-load').exists()
