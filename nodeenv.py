#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    nodeenv
    ~~~~~~~
    Node.js virtual environment

    :copyright: (c) 2014 by Eugene Kalinin
    :license: BSD, see LICENSE for more details.
"""

import contextlib
import io
import json
import sys
import os
import re
import ssl
import stat
import logging
import operator
import argparse
import subprocess
import tarfile
if sys.version_info < (3, 3):
    from pipes import quote as _quote
else:
    from shlex import quote as _quote
import platform
import zipfile
import shutil
import sysconfig
import glob

try:  # pragma: no cover (py2 only)
    from ConfigParser import SafeConfigParser as ConfigParser
    # noinspection PyCompatibility
    import urllib2
    iteritems = operator.methodcaller('iteritems')
    import httplib
    IncompleteRead = httplib.IncompleteRead
except ImportError:  # pragma: no cover (py3 only)
    from configparser import ConfigParser
    # noinspection PyUnresolvedReferences
    import urllib.request as urllib2
    iteritems = operator.methodcaller('items')
    import http
    IncompleteRead = http.client.IncompleteRead

nodeenv_version = '1.9.1'

join = os.path.join
abspath = os.path.abspath
src_base_url = None

is_PY3 = sys.version_info[0] >= 3
is_WIN = platform.system() == 'Windows'
is_CYGWIN = platform.system().startswith(('CYGWIN', 'MSYS'))

ignore_ssl_certs = False

# ---------------------------------------------------------
# Utils


# https://github.com/jhermann/waif/blob/master/python/to_uft8.py
def to_utf8(text):
    """Convert given text to UTF-8 encoding (as far as possible)."""
    if not text or is_PY3:
        return text

    try:           # unicode or pure ascii
        return text.encode("utf8")
    except UnicodeDecodeError:
        try:       # successful UTF-8 decode means it's pretty sure UTF-8
            text.decode("utf8")
            return text
        except UnicodeDecodeError:
            try:   # get desperate; and yes, this has a western hemisphere bias
                return text.decode("cp1252").encode("utf8")
            except UnicodeDecodeError:
                pass

    return text    # return unchanged, hope for the best


class Config(object):
    """
    Configuration namespace.
    """

    # Defaults
    node = 'latest'
    npm = 'latest'
    with_npm = False
    jobs = '2'
    without_ssl = False
    debug = False
    profile = False
    make = 'make'
    prebuilt = True
    ignore_ssl_certs = False
    mirror = None

    @classmethod
    def _load(cls, configfiles, verbose=False):
        """
        Load configuration from the given files in reverse order,
        if they exist and have a [nodeenv] section.
        Additionally, load version from .node-version if file exists.
        """
        for configfile in reversed(configfiles):
            configfile = os.path.expanduser(configfile)
            if not os.path.exists(configfile):
                continue

            ini_file = ConfigParser()
            ini_file.read(configfile)
            section = "nodeenv"
            if not ini_file.has_section(section):
                continue

            for attr, val in iteritems(vars(cls)):
                if attr.startswith('_') or not \
                   ini_file.has_option(section, attr):
                    continue

                if isinstance(val, bool):
                    val = ini_file.getboolean(section, attr)
                else:
                    val = ini_file.get(section, attr)

                if verbose:
                    print('CONFIG {0}: {1} = {2}'.format(
                        os.path.basename(configfile), attr, val))
                setattr(cls, attr, val)

        if os.path.exists(".node-version"):
            with open(".node-version", "r") as v_file:
                setattr(cls, "node", v_file.readline().strip().lstrip("v"))

    @classmethod
    def _dump(cls):
        """
        Print defaults for the README.
        """
        print("    [nodeenv]")
        print("    " + "\n    ".join(
            "%s = %s" % (k, v) for k, v in sorted(iteritems(vars(cls)))
            if not k.startswith('_')))


Config._default = dict(
    (attr, val) for attr, val in iteritems(vars(Config))
    if not attr.startswith('_')
)


def clear_output(out):
    """
    Remove new-lines and
    """
    return out.decode('utf-8').replace('\n', '')


def remove_env_bin_from_path(env, env_bin_dir):
    """
    Remove bin directory of the current environment from PATH
    """
    return env.replace(env_bin_dir + ':', '')


def parse_version(version_str):
    """
    Parse version string to a tuple of integer parts
    """
    v = version_str.replace('v', '').split('.')[:3]
    # remove all after '+' in the PATCH part of the version
    if len(v) >= 3:
        v[2] = v[2].split('+')[0]
    return tuple(map(int, v))


def node_version_from_args(args):
    """
    Parse the node version from the argparse args
    """
    if args.node == 'system':
        out, err = subprocess.Popen(
            ["node", "--version"], stdout=subprocess.PIPE).communicate()
        return parse_version(clear_output(out))

    return parse_version(args.node)


def create_logger():
    """
    Create logger for diagnostic
    """
    # create logger
    loggr = logging.getLogger("nodeenv")
    loggr.setLevel(logging.INFO)

    # monkey patch
    def emit(self, record):
        msg = self.format(record)
        fs = "%s" if getattr(record, "continued", False) else "%s\n"
        self.stream.write(fs % to_utf8(msg))
        self.flush()
    logging.StreamHandler.emit = emit

    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # create formatter
    formatter = logging.Formatter(fmt="%(message)s")

    # add formatter to ch
    ch.setFormatter(formatter)

    # add ch to logger
    loggr.addHandler(ch)
    return loggr


logger = create_logger()


def make_parser():
    """
    Make a command line argument parser.
    """
    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTIONS] DEST_DIR")

    parser.add_argument(
        '--version', action='version', version=nodeenv_version)

    parser.add_argument(
        '-n', '--node', dest='node', metavar='NODE_VER', default=Config.node,
        help='The node.js version to use, e.g., '
        '--node=0.4.3 will use the node-v0.4.3 '
        'to create the new environment. '
        'The default is last stable version (`latest`). '
        'Use `lts` to use the latest LTS release. '
        'Use `system` to use system-wide node.')

    parser.add_argument(
        '--mirror',
        action="store", dest='mirror', default=Config.mirror,
        help='Set mirror server of nodejs.org to download from.')

    if not is_WIN:
        parser.add_argument(
            '-j', '--jobs', dest='jobs', default=Config.jobs,
            help='Sets number of parallel commands at node.js compilation. '
            'The default is 2 jobs.')

        parser.add_argument(
            '--load-average', dest='load_average',
            help='Sets maximum load average for executing parallel commands '
            'at node.js compilation.')

        parser.add_argument(
            '--without-ssl', dest='without_ssl',
            action='store_true', default=Config.without_ssl,
            help='Build node.js without SSL support')

        parser.add_argument(
            '--debug', dest='debug',
            action='store_true', default=Config.debug,
            help='Build debug variant of the node.js')

        parser.add_argument(
            '--profile', dest='profile',
            action='store_true', default=Config.profile,
            help='Enable profiling for node.js')

        parser.add_argument(
            '--make', '-m', dest='make_path',
            metavar='MAKE_PATH',
            help='Path to make command',
            default=Config.make)

        parser.add_argument(
            '--source', dest='prebuilt',
            action='store_false', default=Config.prebuilt,
            help='Install node.js from the source')

    parser.add_argument(
        '-v', '--verbose',
        action='store_true', dest='verbose', default=False,
        help="Verbose mode")

    parser.add_argument(
        '-q', '--quiet',
        action='store_true', dest='quiet', default=False,
        help="Quiet mode")

    parser.add_argument(
        '-C', '--config-file', dest='config_file', default=None,
        help="Load a different file than '~/.nodeenvrc'. "
        "Pass an empty string for no config (use built-in defaults).")

    parser.add_argument(
        '-r', '--requirements',
        dest='requirements', default='', metavar='FILENAME',
        help='Install all the packages listed in the given requirements file.')

    parser.add_argument(
        '--prompt', dest='prompt',
        help='Provides an alternative prompt prefix for this environment')

    parser.add_argument(
        '-l', '--list', dest='list',
        action='store_true', default=False,
        help='Lists available node.js versions')

    parser.add_argument(
        '--update', dest='update',
        action='store_true', default=False,
        help='Install npm packages from file without node')

    parser.add_argument(
        '--with-npm', dest='with_npm',
        action='store_true', default=Config.with_npm,
        help='Build without installing npm into the new virtual environment. '
        'Required for node.js < 0.6.3. By default, the npm included with '
        'node.js is used. Under Windows, this defaults to true.')

    parser.add_argument(
        '--npm', dest='npm',
        metavar='NPM_VER', default=Config.npm,
        help='The npm version to use, e.g., '
        '--npm=0.3.18 will use the npm-0.3.18.tgz '
        'tarball to install. '
        'The default is last available version (`latest`).')

    parser.add_argument(
        '--no-npm-clean', dest='no_npm_clean',
        action='store_true', default=False,
        help='Skip the npm 0.x cleanup.  Cleanup is enabled by default.')

    parser.add_argument(
        '--python-virtualenv', '-p', dest='python_virtualenv',
        action='store_true', default=False,
        help='Use current python virtualenv')

    parser.add_argument(
        '--clean-src', '-c', dest='clean_src',
        action='store_true', default=False,
        help='Remove "src" directory after installation')

    parser.add_argument(
        '--force', dest='force',
        action='store_true', default=False,
        help='Force installation in a pre-existing directory')

    parser.add_argument(
        '--prebuilt', dest='prebuilt',
        action='store_true', default=Config.prebuilt,
        help='Install node.js from prebuilt package (default)')

    parser.add_argument(
        '--ignore_ssl_certs', dest='ignore_ssl_certs',
        action='store_true', default=Config.ignore_ssl_certs,
        help='Ignore certificates for package downloads. - UNSAFE -')

    parser.add_argument(
        metavar='DEST_DIR', dest='env_dir', nargs='?',
        help='Destination directory')

    return parser


def parse_args(check=True):
    """
    Parses command line arguments.

    Set `check` to False to skip validation checks.
    """
    parser = make_parser()
    args = parser.parse_args()

    if args.config_file is None:
        args.config_file = ["./tox.ini", "./setup.cfg", "~/.nodeenvrc"]
    elif not args.config_file:
        args.config_file = []
    else:
        # Make sure that explicitly provided files exist
        if not os.path.exists(args.config_file):
            parser.error("Config file '{0}' doesn't exist!".format(
                args.config_file))
        args.config_file = [args.config_file]

    if not check:
        return args

    if not args.list:
        if not args.python_virtualenv and not args.env_dir:
            parser.error('You must provide a DEST_DIR or '
                         'use current python virtualenv')

    return args


def mkdir(path):
    """
    Create directory
    """
    if not os.path.exists(path):
        logger.debug(' * Creating: %s ... ', path, extra=dict(continued=True))
        os.makedirs(path)
        logger.debug('done.')
    else:
        logger.debug(' * Directory %s already exists', path)


def make_executable(filename):
    mode_0755 = (stat.S_IRWXU | stat.S_IXGRP |
                 stat.S_IRGRP | stat.S_IROTH | stat.S_IXOTH)
    os.chmod(filename, mode_0755)


# noinspection PyArgumentList
def writefile(dest, content, overwrite=True, append=False):
    """
    Create file and write content in it
    """
    content = to_utf8(content)
    if is_PY3 and not isinstance(content, bytes):
        content = bytes(content, 'utf-8')
    if not os.path.exists(dest):
        logger.debug(' * Writing %s ... ', dest, extra=dict(continued=True))
        with open(dest, 'wb') as f:
            f.write(content)
        make_executable(dest)
        logger.debug('done.')
        return
    else:
        with open(dest, 'rb') as f:
            c = f.read()
        if content in c:
            logger.debug(' * Content %s already in place', dest)
            return

        if not overwrite:
            logger.info(' * File %s exists with different content; '
                        ' not overwriting', dest)
            return

        if append:
            logger.info(' * Appending data to %s', dest)
            with open(dest, 'ab') as f:
                f.write(content)
            return

        logger.info(' * Overwriting %s with new content', dest)
        with open(dest, 'wb') as f:
            f.write(content)


def callit(cmd, show_stdout=True, in_shell=False,
           cwd=None, extra_env=None):
    """
    Execute cmd line in sub-shell
    """
    all_output = []
    cmd_parts = []

    for part in cmd:
        if len(part) > 45:
            part = part[:20] + "..." + part[-20:]
        if ' ' in part or '\n' in part or '"' in part or "'" in part:
            part = '"%s"' % part.replace('"', '\\"')
        cmd_parts.append(part)
    cmd_desc = ' '.join(cmd_parts)
    logger.debug(" ** Running command %s" % cmd_desc)

    if in_shell:
        cmd = ' '.join(cmd)

    # output
    stdout = subprocess.PIPE

    # env
    if extra_env:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
    else:
        env = None

    # execute
    try:
        proc = subprocess.Popen(
            cmd, stderr=subprocess.STDOUT, stdin=None, stdout=stdout,
            cwd=cwd, env=env, shell=in_shell)
    except Exception:
        e = sys.exc_info()[1]
        logger.error("Error %s while executing command %s" % (e, cmd_desc))
        raise

    stdout = proc.stdout
    while stdout:
        line = stdout.readline()
        if not line:
            break
        try:
            if is_WIN:
                line = line.decode('mbcs').rstrip()
            else:
                line = line.decode('utf8').rstrip()
        except UnicodeDecodeError:
            line = line.decode('cp866').rstrip()
        all_output.append(line)
        if show_stdout:
            logger.info(line)
    proc.wait()

    # error handler
    if proc.returncode:
        if show_stdout:
            for s in all_output:
                logger.critical(s)
        raise OSError("Command %s failed with error code %s"
                      % (cmd_desc, proc.returncode))

    return proc.returncode, all_output


def get_root_url(version_str):
    if parse_version(version_str) > (0, 5):
        return '%s/v%s/' % (src_base_url, version_str)
    else:
        return src_base_url


def is_x86_64_musl():
    return sysconfig.get_config_var('HOST_GNU_TYPE') == 'x86_64-pc-linux-musl'


def is_riscv64():
    return platform.machine() == 'riscv64'


def get_node_bin_url(version):
    archmap = {
        'x86':    'x86',  # Windows Vista 32
        'i686':   'x86',
        'x86_64': 'x64',  # Linux Ubuntu 64
        'amd64':  'x64',  # FreeBSD 64bits
        'AMD64':  'x64',  # Windows Server 2012 R2 (x64)
        'armv6l': 'armv6l',     # arm
        'armv7l': 'armv7l',
        'armv8l': 'armv7l',
        'aarch64': 'arm64',
        'arm64': 'arm64',
        'arm64/v8': 'arm64',
        'armv8': 'arm64',
        'armv8.4': 'arm64',
        'ppc64le': 'ppc64le',   # Power PC
        's390x': 's390x',       # IBM S390x
        'riscv64': 'riscv64',   # RISCV 64
    }
    sysinfo = {
        'system': platform.system().lower(),
        'arch': archmap[platform.machine()],
    }
    if is_WIN or is_CYGWIN:
        postfix = '-win-%(arch)s.zip' % sysinfo
    elif is_x86_64_musl():
        postfix = '-linux-x64-musl.tar.gz'
    else:
        postfix = '-%(system)s-%(arch)s.tar.gz' % sysinfo
    filename = 'node-v%s%s' % (version, postfix)
    return get_root_url(version) + filename


def get_node_src_url(version):
    tar_name = 'node-v%s.tar.gz' % version
    return get_root_url(version) + tar_name


@contextlib.contextmanager
def tarfile_open(*args, **kwargs):
    """Compatibility layer because py26."""
    tf = tarfile.open(*args, **kwargs)
    try:
        yield tf
    finally:
        tf.close()


def _download_node_file(node_url, n_attempt=3):
    """Do multiple attempts to avoid incomplete data in case
    of unstable network"""
    while n_attempt > 0:
        try:
            return io.BytesIO(urlopen(node_url).read())
        except IncompleteRead as e:
            logger.warning(
                'Incomplete read while reading '
                'from {} - {}'.format(node_url, e)
            )
            n_attempt -= 1
            if n_attempt == 0:
                raise e


def download_node_src(node_url, src_dir, args):
    """
    Download source code
    """
    logger.info('.', extra=dict(continued=True))
    dl_contents = _download_node_file(node_url)
    logger.info('.', extra=dict(continued=True))

    if is_WIN or is_CYGWIN:
        ctx = zipfile.ZipFile(dl_contents)
        members = operator.methodcaller('namelist')
        member_name = lambda s: s  # noqa: E731
    else:
        ctx = tarfile_open(fileobj=dl_contents)
        members = operator.methodcaller('getmembers')
        member_name = operator.attrgetter('name')

    with ctx as archive:
        node_ver = re.escape(args.node)
        rexp_string = r"node-v%s[^/]*/(README\.md|CHANGELOG\.md|LICENSE)"\
            % node_ver
        extract_list = [
            member
            for member in members(archive)
            if re.match(rexp_string, member_name(member)) is None
        ]
        archive.extractall(src_dir, extract_list)


def urlopen(url):
    home_url = "https://github.com/ekalinin/nodeenv/"
    headers = {'User-Agent': 'nodeenv/%s (%s)' % (nodeenv_version, home_url)}
    req = urllib2.Request(url, None, headers)
    if ignore_ssl_certs:
        # py27: protocol required, py3: optional
        # https://github.com/ekalinin/nodeenv/issues/296
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        context.verify_mode = ssl.CERT_NONE
        return urllib2.urlopen(req, context=context)
    return urllib2.urlopen(req)

# ---------------------------------------------------------
# Virtual environment functions


def copytree(src, dst, symlinks=False, ignore=None):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            try:
                shutil.copytree(s, d, symlinks, ignore)
            except OSError:
                copytree(s, d, symlinks, ignore)
        else:
            if os.path.islink(s):
                # copy link only if it not exists. #189
                if not os.path.islink(d):
                    os.symlink(os.readlink(s), d)
            else:
                shutil.copy2(s, d)


def copy_node_from_prebuilt(env_dir, src_dir, node_version):
    """
    Copy prebuilt binaries into environment
    """
    logger.info('.', extra=dict(continued=True))
    if is_WIN:
        dest = join(env_dir, 'Scripts')
        mkdir(dest)
    elif is_CYGWIN:
        dest = join(env_dir, 'bin')
        mkdir(dest)
        # write here to avoid https://bugs.python.org/issue35650
        writefile(join(env_dir, 'bin', 'node'), CYGWIN_NODE)
    else:
        dest = env_dir

    src_folder_tpl = src_dir + to_utf8('/node-v%s*' % node_version)
    src_folder, = glob.glob(src_folder_tpl)
    copytree(src_folder, dest, True)

    if is_CYGWIN:
        for filename in ('npm', 'npx', 'node.exe'):
            filename = join(env_dir, 'bin', filename)
            if os.path.exists(filename):
                make_executable(filename)

    logger.info('.', extra=dict(continued=True))


def build_node_from_src(env_dir, src_dir, node_src_dir, args):
    env = {}
    make_param_names = ['load-average', 'jobs']
    make_param_values = map(
        lambda x: getattr(args, x.replace('-', '_')),
        make_param_names)
    make_opts = [
        '--{0}={1}'.format(name, value)
        if len(value) > 0 else '--{0}'.format(name)
        for name, value in zip(make_param_names, make_param_values)
        if value is not None
    ]

    if getattr(sys.version_info, 'major', sys.version_info[0]) > 2:
        # Currently, the node.js build scripts are using python2.*,
        # therefore we need to temporarily point python exec to the
        # python 2.* version in this case.
        python2_path = shutil.which('python2')
        if not python2_path:
            raise OSError(
                'Python >=3.0 virtualenv detected, but no python2 '
                'command (required for building node.js) was found'
            )
        logger.debug(' * Temporarily pointing python to %s', python2_path)
        node_tmpbin_dir = join(src_dir, 'tmpbin')
        node_tmpbin_link = join(node_tmpbin_dir, 'python')
        mkdir(node_tmpbin_dir)
        if not os.path.exists(node_tmpbin_link):
            callit(['ln', '-s', python2_path, node_tmpbin_link])
        env['PATH'] = '{}:{}'.format(node_tmpbin_dir,
                                     os.environ.get('PATH', ''))

    conf_cmd = [
        './configure',
        '--prefix=%s' % _quote(env_dir)
    ]
    if args.without_ssl:
        conf_cmd.append('--without-ssl')
    if args.debug:
        conf_cmd.append('--debug')
    if args.profile:
        conf_cmd.append('--profile')

    make_cmd = args.make_path

    callit(conf_cmd, args.verbose, True, node_src_dir, env)
    logger.info('.', extra=dict(continued=True))
    callit([make_cmd] + make_opts, args.verbose, True, node_src_dir, env)
    logger.info('.', extra=dict(continued=True))
    callit([make_cmd + ' install'], args.verbose, True, node_src_dir, env)


def install_node(env_dir, src_dir, args):
    """
    Download source code for node.js, unpack it
    and install it in virtual environment.
    """
    try:
        install_node_wrapped(env_dir, src_dir, args)
    except BaseException:
        # this restores the newline suppressed by continued=True
        logger.info('')
        raise


def install_node_wrapped(env_dir, src_dir, args):
    env_dir = abspath(env_dir)
    node_src_dir = join(src_dir, to_utf8('node-v%s' % args.node))
    src_type = "prebuilt" if args.prebuilt else "source"

    logger.info(' * Install %s node (%s) ' % (src_type, args.node),
                extra=dict(continued=True))

    if args.prebuilt:
        node_url = get_node_bin_url(args.node)
    else:
        node_url = get_node_src_url(args.node)

    # get src if not downloaded yet
    if not os.path.exists(node_src_dir):
        try:
            download_node_src(node_url, src_dir, args)
        except urllib2.HTTPError:
            if "arm64" in node_url:
                # if arm64 not found, try x64
                download_node_src(node_url.replace('arm64', 'x64'),
                                  src_dir, args)
            else:
                logger.warning('Failed to download from %s' % node_url)

    logger.info('.', extra=dict(continued=True))

    if args.prebuilt:
        copy_node_from_prebuilt(env_dir, src_dir, args.node)
    else:
        build_node_from_src(env_dir, src_dir, node_src_dir, args)

    logger.info(' done.')


def install_npm(env_dir, _src_dir, args):
    """
    Download source code for npm, unpack it
    and install it in virtual environment.
    """
    logger.info(' * Install npm.js (%s) ... ' % args.npm,
                extra=dict(continued=True))
    env = dict(
        os.environ,
        clean='no' if args.no_npm_clean else 'yes',
        npm_install=args.npm,
    )
    proc = subprocess.Popen(
        (
            'bash', '-c',
            '. {0} && npm install -g npm@{1}'.format(
                _quote(join(env_dir, 'bin', 'activate')),
                args.npm,
            )
        ),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    out, _ = proc.communicate()
    if args.verbose:
        logger.info(out)
    logger.info('done.')


def install_npm_win(env_dir, src_dir, args):
    """
    Download source code for npm, unpack it
    and install it in virtual environment.
    """
    logger.info(' * Install npm.js (%s) ... ' % args.npm,
                extra=dict(continued=True))
    npm_url = 'https://github.com/npm/cli/archive/v%s.zip' % args.npm
    npm_contents = io.BytesIO(urlopen(npm_url).read())

    bin_path = join(env_dir, 'Scripts')
    node_modules_path = join(bin_path, 'node_modules', 'npm')

    if os.path.exists(node_modules_path):
        shutil.rmtree(node_modules_path)

    if os.path.exists(join(bin_path, 'npm.cmd')):
        os.remove(join(bin_path, 'npm.cmd'))

    if os.path.exists(join(bin_path, 'npm-cli.js')):
        os.remove(join(bin_path, 'npm-cli.js'))

    with zipfile.ZipFile(npm_contents, 'r') as zipf:
        zipf.extractall(src_dir)

    npm_ver = 'cli-%s' % args.npm
    shutil.copytree(join(src_dir, npm_ver), node_modules_path)
    shutil.copy(join(src_dir, npm_ver, 'bin', 'npm.cmd'),
                join(bin_path, 'npm.cmd'))
    shutil.copy(join(src_dir, npm_ver, 'bin', 'npm-cli.js'),
                join(bin_path, 'npm-cli.js'))

    if is_CYGWIN:
        shutil.copy(join(bin_path, 'npm-cli.js'),
                    join(env_dir, 'bin', 'npm-cli.js'))
        shutil.copytree(join(bin_path, 'node_modules'),
                        join(env_dir, 'bin', 'node_modules'))
        npm_gh_url = 'https://raw.githubusercontent.com/npm/cli'
        npm_bin_url = '{}/{}/bin/npm'.format(npm_gh_url, args.npm)
        writefile(join(env_dir, 'bin', 'npm'), urlopen(npm_bin_url).read())


def install_packages(env_dir, args):
    """
    Install node.js packages via npm
    """
    logger.info(' * Install node.js packages ... ',
                extra=dict(continued=True))
    packages = [package.strip() for package in
                open(args.requirements).readlines()]
    activate_path = join(env_dir, 'bin', 'activate')
    real_npm_ver = args.npm if args.npm.count(".") == 2 else args.npm + ".0"
    if args.npm == "latest" or real_npm_ver >= "1.0.0":
        cmd = '. ' + _quote(activate_path) + \
              ' && npm install -g %(pack)s'
    else:
        cmd = '. ' + _quote(activate_path) + \
              ' && npm install %(pack)s' + \
              ' && npm activate %(pack)s'

    for package in packages:
        if not package:
            continue
        callit(cmd=[
            cmd % {"pack": package}], show_stdout=args.verbose, in_shell=True)

    logger.info('done.')


def install_activate(env_dir, args):
    """
    Install virtual environment activation script
    """
    if is_WIN:
        files = {
            'activate.bat': ACTIVATE_BAT,
            "deactivate.bat": DEACTIVATE_BAT,
            "Activate.ps1": ACTIVATE_PS1
        }
        bin_dir = join(env_dir, 'Scripts')
        shim_node = join(bin_dir, "node.exe")
        shim_nodejs = join(bin_dir, "nodejs.exe")
    else:
        files = {
            'activate': ACTIVATE_SH,
            'activate.fish': ACTIVATE_FISH,
            'shim': SHIM
        }
        bin_dir = join(env_dir, 'bin')
        shim_node = join(bin_dir, "node")
        shim_nodejs = join(bin_dir, "nodejs")
    if is_CYGWIN:
        mkdir(bin_dir)

    if args.node == "system":
        files["node"] = SHIM

    mod_dir = join('lib', 'node_modules')
    prompt = args.prompt or '(%s)' % os.path.basename(os.path.abspath(env_dir))

    if args.node == "system":
        env = os.environ.copy()
        env.update({'PATH': remove_env_bin_from_path(env['PATH'], bin_dir)})
        for candidate in ("nodejs", "node"):
            which_node_output, _ = subprocess.Popen(
                ["which", candidate],
                stdout=subprocess.PIPE, env=env).communicate()
            shim_node = clear_output(which_node_output)
            if shim_node:
                break
        assert shim_node, "Did not find nodejs or node system executable"

    for name, content in files.items():
        file_path = join(bin_dir, name)
        content = content.replace('__NODE_VIRTUAL_PROMPT__', prompt)
        content = content.replace('__NODE_VIRTUAL_ENV__',
                                  os.path.abspath(env_dir))
        content = content.replace('__SHIM_NODE__', shim_node)
        content = content.replace('__BIN_NAME__', os.path.basename(bin_dir))
        content = content.replace('__MOD_NAME__', mod_dir)
        if is_CYGWIN:
            _, cyg_bin_dir = callit(
                ['cygpath', '-w', os.path.abspath(bin_dir)],
                show_stdout=False, in_shell=False)
            content = content.replace('__NPM_CONFIG_PREFIX__', cyg_bin_dir[0])
        else:
            content = content.replace('__NPM_CONFIG_PREFIX__',
                                      '$NODE_VIRTUAL_ENV')
        # if we call in the same environment:
        #   $ nodeenv -p --prebuilt
        #   $ nodeenv -p --node=system
        # we should get `bin/node` not as binary+string.
        # `bin/activate` should be appended if we're inside
        # existing python's virtual environment
        need_append = False
        if args.python_virtualenv:
            disable_prompt = DISABLE_PROMPT.get(name, '')
            enable_prompt = ENABLE_PROMPT.get(name, '')
            content = disable_prompt + content + enable_prompt
            need_append = bool(disable_prompt)
        writefile(file_path, content, append=need_append)

    if not os.path.exists(shim_nodejs):
        if is_WIN:
            try:
                callit(['mklink', shim_nodejs, 'node.exe'], True, True)
            except OSError:
                logger.error('Error: Failed to create nodejs.exe link')
        else:
            os.symlink("node", shim_nodejs)


def set_predeactivate_hook(env_dir):
    if not is_WIN:
        with open(join(env_dir, 'bin', 'predeactivate'), 'a') as hook:
            hook.write(PREDEACTIVATE_SH)


def create_environment(env_dir, args):
    """
    Creates a new environment in ``env_dir``.
    """
    if os.path.exists(env_dir) and not args.python_virtualenv:
        logger.info(' * Environment already exists: %s', env_dir)
        if not args.force:
            sys.exit(2)
    src_dir = to_utf8(abspath(join(env_dir, 'src')))
    mkdir(src_dir)

    if args.node != "system":
        install_node(env_dir, src_dir, args)
    else:
        mkdir(join(env_dir, 'bin'))
        mkdir(join(env_dir, 'lib'))
        mkdir(join(env_dir, 'lib', 'node_modules'))
    # activate script install must be
    # before npm install, npm use activate
    # for install
    install_activate(env_dir, args)
    if node_version_from_args(args) < (0, 6, 3) or args.with_npm:
        instfunc = install_npm_win if is_WIN or is_CYGWIN else install_npm
        instfunc(env_dir, src_dir, args)
    if args.requirements:
        install_packages(env_dir, args)
    if args.python_virtualenv:
        set_predeactivate_hook(env_dir)
    # Cleanup
    if args.clean_src:
        shutil.rmtree(src_dir)


def _get_versions_json():
    response = urlopen('%s/index.json' % src_base_url)
    return json.loads(response.read().decode('UTF-8'))


def get_node_versions():
    return [dct['version'].lstrip('v') for dct in _get_versions_json()][::-1]


def print_node_versions():
    """
    Prints into stdout all available node.js versions
    """
    versions = get_node_versions()
    chunks_of_8 = [
        versions[pos:pos + 8] for pos in range(0, len(versions), 8)
    ]
    for chunk in chunks_of_8:
        logger.info('\t'.join(chunk))


def get_last_stable_node_version():
    """
    Return last stable node.js version
    """
    return _get_versions_json()[0]['version'].lstrip('v')


def get_last_lts_node_version():
    """
    Return the last node.js version marked as LTS
    """
    return next((v['version'].lstrip('v')
                 for v in _get_versions_json() if v['lts']), None)


def get_env_dir(args):
    if args.python_virtualenv:
        if hasattr(sys, 'real_prefix'):
            res = sys.prefix
        elif hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix:
            res = sys.prefix
        elif 'CONDA_PREFIX' in os.environ:
            res = sys.prefix
        else:
            logger.error('No python virtualenv is available')
            sys.exit(2)
    else:
        res = args.env_dir
    return to_utf8(res)


# noinspection PyProtectedMember
def main():
    """
    Entry point
    """
    # quick&dirty way to help update the README
    if "--dump-config-defaults" in sys.argv:
        Config._dump()
        return

    args = parse_args(check=False)
    # noinspection PyProtectedMember
    Config._load(args.config_file, args.verbose)

    args = parse_args()

    if args.node.lower() == 'system' and is_WIN:
        logger.error('Installing system node.js on win32 is not supported!')
        exit(1)

    global src_base_url
    global ignore_ssl_certs

    ignore_ssl_certs = args.ignore_ssl_certs

    src_domain = None
    if args.mirror:
        if '://' in args.mirror:
            src_base_url = args.mirror
        else:
            src_domain = args.mirror
    # use unofficial builds only if musl and no explicitly chosen mirror
    elif is_x86_64_musl() or is_riscv64():
        src_domain = 'unofficial-builds.nodejs.org'
    else:
        src_domain = 'nodejs.org'
    if src_base_url is None:
        src_base_url = 'https://%s/download/release' % src_domain

    if not args.node or args.node.lower() == 'latest':
        args.node = get_last_stable_node_version()
    elif args.node.lower() == 'lts':
        args.node = get_last_lts_node_version()

    if args.list:
        print_node_versions()
    elif args.update:
        env_dir = get_env_dir(args)
        install_packages(env_dir, args)
    else:
        env_dir = get_env_dir(args)
        create_environment(env_dir, args)


# ---------------------------------------------------------
# Shell scripts content

DISABLE_PROMPT = {
    'activate': """
# disable nodeenv's prompt
# (prompt already changed by original virtualenv's script)
# https://github.com/ekalinin/nodeenv/issues/26
NODE_VIRTUAL_ENV_DISABLE_PROMPT=1
""",
    'activate.fish': """
# disable nodeenv's prompt
# (prompt already changed by original virtualenv's script)
# https://github.com/ekalinin/nodeenv/issues/26
set NODE_VIRTUAL_ENV_DISABLE_PROMPT 1
""",
}

ENABLE_PROMPT = {
    'activate': """
unset NODE_VIRTUAL_ENV_DISABLE_PROMPT
""",
    'activate.fish': """
set -e NODE_VIRTUAL_ENV_DISABLE_PROMPT
""",
}

SHIM = """#!/usr/bin/env bash
export NODE_PATH='__NODE_VIRTUAL_ENV__/lib/node_modules'
export NPM_CONFIG_PREFIX='__NODE_VIRTUAL_ENV__'
export npm_config_prefix='__NODE_VIRTUAL_ENV__'
exec '__SHIM_NODE__' "$@"
"""

ACTIVATE_BAT = r"""
@echo off
set "NODE_VIRTUAL_ENV=__NODE_VIRTUAL_ENV__"
if not defined PROMPT (
    set "PROMPT=$P$G"
)
if defined _OLD_VIRTUAL_PROMPT (
    set "PROMPT=%_OLD_VIRTUAL_PROMPT%"
)
if defined _OLD_VIRTUAL_NODE_PATH (
    set "NODE_PATH=%_OLD_VIRTUAL_NODE_PATH%"
)
set "_OLD_VIRTUAL_PROMPT=%PROMPT%"
set "PROMPT=__NODE_VIRTUAL_PROMPT__ %PROMPT%"
if defined NODE_PATH (
    set "_OLD_VIRTUAL_NODE_PATH=%NODE_PATH%"
    set NODE_PATH=
)
if defined _OLD_VIRTUAL_PATH (
    set "PATH=%_OLD_VIRTUAL_PATH%"
) else (
    set "_OLD_VIRTUAL_PATH=%PATH%"
)
set "PATH=%NODE_VIRTUAL_ENV%\Scripts;%PATH%"
:END

"""

DEACTIVATE_BAT = """\
@echo off
if defined _OLD_VIRTUAL_PROMPT (
    set "PROMPT=%_OLD_VIRTUAL_PROMPT%"
)
set _OLD_VIRTUAL_PROMPT=
if defined _OLD_VIRTUAL_NODE_PATH (
    set "NODE_PATH=%_OLD_VIRTUAL_NODE_PATH%"
    set _OLD_VIRTUAL_NODE_PATH=
)
if defined _OLD_VIRTUAL_PATH (
    set "PATH=%_OLD_VIRTUAL_PATH%"
)
set _OLD_VIRTUAL_PATH=
set NODE_VIRTUAL_ENV=
:END
"""

ACTIVATE_PS1 = r"""
function global:deactivate ([switch]$NonDestructive) {
    # Revert to original values
    if (Test-Path function:_OLD_VIRTUAL_PROMPT) {
        copy-item function:_OLD_VIRTUAL_PROMPT function:prompt
        remove-item function:_OLD_VIRTUAL_PROMPT
    }
    if (Test-Path env:_OLD_VIRTUAL_NODE_PATH) {
        copy-item env:_OLD_VIRTUAL_NODE_PATH env:NODE_PATH
        remove-item env:_OLD_VIRTUAL_NODE_PATH
    }
    if (Test-Path env:_OLD_VIRTUAL_PATH) {
        copy-item env:_OLD_VIRTUAL_PATH env:PATH
        remove-item env:_OLD_VIRTUAL_PATH
    }
    if (Test-Path env:NODE_VIRTUAL_ENV) {
        remove-item env:NODE_VIRTUAL_ENV
    }
    if (!$NonDestructive) {
        # Self destruct!
        remove-item function:deactivate
    }
}

deactivate -nondestructive
$env:NODE_VIRTUAL_ENV="__NODE_VIRTUAL_ENV__"

# Set the prompt to include the env name
# Make sure _OLD_VIRTUAL_PROMPT is global
function global:_OLD_VIRTUAL_PROMPT {""}
copy-item function:prompt function:_OLD_VIRTUAL_PROMPT
function global:prompt {
    Write-Host -NoNewline -ForegroundColor Green '__NODE_VIRTUAL_PROMPT__ '
    _OLD_VIRTUAL_PROMPT
}

# Clear NODE_PATH
if (Test-Path env:NODE_PATH) {
    copy-item env:NODE_PATH env:_OLD_VIRTUAL_NODE_PATH
    remove-item env:NODE_PATH
}

# Add the venv to the PATH
copy-item env:PATH env:_OLD_VIRTUAL_PATH
$env:PATH = "$env:NODE_VIRTUAL_ENV\Scripts;$env:PATH"
"""

ACTIVATE_SH = r"""

# This file must be used with "source bin/activate" *from bash*
# you cannot run it directly

deactivate_node () {
    # reset old environment variables
    if [ -n "${_OLD_NODE_VIRTUAL_PATH:-}" ] ; then
        PATH="${_OLD_NODE_VIRTUAL_PATH:-}"
        export PATH
        unset _OLD_NODE_VIRTUAL_PATH

        NODE_PATH="${_OLD_NODE_PATH:-}"
        export NODE_PATH
        unset _OLD_NODE_PATH

        NPM_CONFIG_PREFIX="${_OLD_NPM_CONFIG_PREFIX:-}"
        npm_config_prefix="${_OLD_npm_config_prefix:-}"
        export NPM_CONFIG_PREFIX
        export npm_config_prefix
        unset _OLD_NPM_CONFIG_PREFIX
        unset _OLD_npm_config_prefix
    fi

    # This should detect bash and zsh, which have a hash command that must
    # be called to get it to forget past commands.  Without forgetting
    # past commands the $PATH changes we made may not be respected
    if [ -n "${BASH:-}" -o -n "${ZSH_VERSION:-}" ] ; then
        hash -r
    fi

    if [ -n "${_OLD_NODE_VIRTUAL_PS1:-}" ] ; then
        PS1="${_OLD_NODE_VIRTUAL_PS1:-}"
        export PS1
        unset _OLD_NODE_VIRTUAL_PS1
    fi

    unset NODE_VIRTUAL_ENV
    if [ ! "${1:-}" = "nondestructive" ] ; then
    # Self destruct!
        unset -f deactivate_node
    fi
}

freeze () {
    local NPM_VER=`npm -v | cut -d '.' -f 1`
    local re="[a-zA-Z0-9\.\-]+@[0-9]+\.[0-9]+\.[0-9]+([\+\-][a-zA-Z0-9\.\-]+)*"
    if [ "$NPM_VER" = '0' ]; then
        NPM_LIST=`npm list installed active 2>/dev/null | \
                  cut -d ' ' -f 1 | grep -v npm`
    else
        local npmls="npm ls -g"
        if [ "${1:-}" = "-l" ]; then
            npmls="npm ls"
            shift
        fi
        NPM_LIST=$(eval ${npmls} | grep -E '^.{4}\w{1}'| \
                                   grep -o -E "$re"| grep -v npm)
    fi

    if [ -z "$@" ]; then
        echo "$NPM_LIST"
    else
        echo "$NPM_LIST" > $@
    fi
}

# unset irrelevant variables
deactivate_node nondestructive

# find the directory of this script
# http://stackoverflow.com/a/246128
if [ "${BASH_SOURCE:-}" ] ; then
    SOURCE="${BASH_SOURCE[0]}"

    while [ -h "$SOURCE" ] ; do SOURCE="$(readlink "$SOURCE")"; done
    DIR="$( command cd -P "$( dirname "$SOURCE" )" > /dev/null && pwd )"

    NODE_VIRTUAL_ENV="$(dirname "$DIR")"
else
    # dash not movable. fix use case:
    #   dash -c " . node-env/bin/activate && node -v"
    NODE_VIRTUAL_ENV="__NODE_VIRTUAL_ENV__"
fi

# NODE_VIRTUAL_ENV is the parent of the directory where this script is
export NODE_VIRTUAL_ENV

_OLD_NODE_VIRTUAL_PATH="$PATH"
PATH="$NODE_VIRTUAL_ENV/lib/node_modules/.bin:$NODE_VIRTUAL_ENV/__BIN_NAME__:$PATH"
export PATH

_OLD_NODE_PATH="${NODE_PATH:-}"
NODE_PATH="$NODE_VIRTUAL_ENV/__MOD_NAME__"
export NODE_PATH

_OLD_NPM_CONFIG_PREFIX="${NPM_CONFIG_PREFIX:-}"
_OLD_npm_config_prefix="${npm_config_prefix:-}"
NPM_CONFIG_PREFIX="__NPM_CONFIG_PREFIX__"
npm_config_prefix="__NPM_CONFIG_PREFIX__"
export NPM_CONFIG_PREFIX
export npm_config_prefix

if [ -z "${NODE_VIRTUAL_ENV_DISABLE_PROMPT:-}" ] ; then
    _OLD_NODE_VIRTUAL_PS1="${PS1:-}"
    if [ "x__NODE_VIRTUAL_PROMPT__" != x ] ; then
        PS1="__NODE_VIRTUAL_PROMPT__ ${PS1:-}"
    else
    if [ "`basename \"$NODE_VIRTUAL_ENV\"`" = "__" ] ; then
        # special case for Aspen magic directories
        # see http://www.zetadev.com/software/aspen/
        PS1="[`basename \`dirname \"$NODE_VIRTUAL_ENV\"\``] ${PS1:-}"
    else
        PS1="(`basename \"$NODE_VIRTUAL_ENV\"`) ${PS1:-}"
    fi
    fi
    export PS1
fi

# This should detect bash and zsh, which have a hash command that must
# be called to get it to forget past commands.  Without forgetting
# past commands the $PATH changes we made may not be respected
if [ -n "${BASH:-}" -o -n "${ZSH_VERSION:-}" ] ; then
    hash -r
fi
"""


ACTIVATE_FISH = """

# This file must be used with "source bin/activate.fish" *from fish*
# you cannot run it directly

function deactivate_node -d 'Exit nodeenv and return to normal environment.'
    # reset old environment variables
    if test -n "$_OLD_NODE_VIRTUAL_PATH"
        set -gx PATH $_OLD_NODE_VIRTUAL_PATH
        set -e _OLD_NODE_VIRTUAL_PATH
    end

    if test -n "$_OLD_NODE_PATH"
        set -gx NODE_PATH $_OLD_NODE_PATH
        set -e _OLD_NODE_PATH
    else
        set -e NODE_PATH
    end

    if test -n "$_OLD_NPM_CONFIG_PREFIX"
        set -gx NPM_CONFIG_PREFIX $_OLD_NPM_CONFIG_PREFIX
        set -e _OLD_NPM_CONFIG_PREFIX
    else
        set -e NPM_CONFIG_PREFIX
    end

    if test -n "$_OLD_npm_config_prefix"
        set -gx npm_config_prefix $_OLD_npm_config_prefix
        set -e _OLD_npm_config_prefix
    else
        set -e npm_config_prefix
    end

    if test -n "$_OLD_NODE_FISH_PROMPT_OVERRIDE"
        # Set an empty local `$fish_function_path` to allow the removal of
        # `fish_prompt` using `functions -e`.
        set -l fish_function_path

        # Prevents error when using nested fish instances
        if functions -q _node_old_fish_prompt
            # Erase virtualenv's `fish_prompt` and restore the original.
            functions -e fish_prompt
            functions -c _node_old_fish_prompt fish_prompt
            functions -e _node_old_fish_prompt
        end
        set -e _OLD_NODE_FISH_PROMPT_OVERRIDE
    end

    set -e NODE_VIRTUAL_ENV

    if test (count $argv) = 0 -o "$argv[1]" != "nondestructive"
        # Self destruct!
        functions -e deactivate_node
    end
end

function freeze -d 'Show a list of installed packages - like `pip freeze`'
    set -l NPM_VER (npm -v | cut -d '.' -f 1)
    set -l RE "[a-zA-Z0-9\\.\\-]+@[0-9]+\\.[0-9]+\\.[0-9]+([\\+\\-][a-zA-Z0-9\\.\\-]+)*"

    if test "$NPM_VER" = "0"
        set -g NPM_LIST (npm list installed active >/dev/null ^/dev/null | \
                         cut -d ' ' -f 1 | grep -v npm)
    else
        set -l NPM_LS "npm ls -g"
        if test (count $argv) -gt 0 -a "$argv[1]" = "-l"
            set NPM_LS "npm ls"
            set -e argv[1]
        end
        set -l NPM_LIST (eval $NPM_LS | grep -E '^.{4}\\w{1}' | \
                                        grep -o -E "$re" | \
                                        grep -v npm)
    end

    if test (count $argv) = 0
        echo $NPM_LIST
    else
        echo $NPM_LIST > $argv[1]
    end
end

# unset irrelevant variables
deactivate_node nondestructive

# find the directory of this script
begin
    set -l SOURCE (status filename)
    while test -L "$SOURCE"
        set SOURCE (readlink "$SOURCE")
    end
    set -l DIR (dirname (realpath "$SOURCE"))

    # NODE_VIRTUAL_ENV is the parent of the directory where this script is
    set -gx NODE_VIRTUAL_ENV (dirname "$DIR")
end

set -gx _OLD_NODE_VIRTUAL_PATH $PATH
# The node_modules/.bin path doesn't exists and it will print a warning, and
# that's why we redirect stderr to /dev/null :)
set -gx PATH "$NODE_VIRTUAL_ENV/lib/node_modules/.bin" "$NODE_VIRTUAL_ENV/__BIN_NAME__" $PATH ^/dev/null

if set -q NODE_PATH
    set -gx _OLD_NODE_PATH $NODE_PATH
    set -gx NODE_PATH "$NODE_VIRTUAL_ENV/__MOD_NAME__" $NODE_PATH
else
    set -gx NODE_PATH "$NODE_VIRTUAL_ENV/__MOD_NAME__"
end

if set -q NPM_CONFIG_PREFIX
    set -gx _OLD_NPM_CONFIG_PREFIX $NPM_CONFIG_PREFIX
end
set -gx NPM_CONFIG_PREFIX "__NPM_CONFIG_PREFIX__"

if set -q npm_config_prefix
    set -gx _OLD_npm_config_prefix $npm_config_prefix
end
set -gx npm_config_prefix "__NPM_CONFIG_PREFIX__"

if test -z "$NODE_VIRTUAL_ENV_DISABLE_PROMPT"
    # Copy the current `fish_prompt` function as `_node_old_fish_prompt`.
    functions -c fish_prompt _node_old_fish_prompt

    function fish_prompt
        # Save the current $status, for fish_prompts that display it.
        set -l old_status $status

        # Prompt override provided?
        # If not, just prepend the environment name.
        if test -n "__NODE_VIRTUAL_PROMPT__"
            printf '%s%s ' "__NODE_VIRTUAL_PROMPT__" (set_color normal)
        else
            printf '%s(%s) ' (set_color normal) (basename "$NODE_VIRTUAL_ENV")
        end

        # Restore the original $status
        echo "exit $old_status" | source
        _node_old_fish_prompt
    end

    set -gx _OLD_NODE_FISH_PROMPT_OVERRIDE "$NODE_VIRTUAL_ENV"
end
"""  # noqa: E501

PREDEACTIVATE_SH = """
if type -p deactivate_node > /dev/null; then deactivate_node;fi
"""

CYGWIN_NODE = """#!/bin/sh

if [ -r "$1" ]; then
    SCRIPT_PATH=$(cygpath -w "$1")
    shift
    set - $SCRIPT_PATH $@
    unset SCRIPT_PATH
fi

exec $(dirname "$0")/node.exe "$@"
"""

if __name__ == '__main__':
    main()
