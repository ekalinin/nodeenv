#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    nodeenv
    ~~~~~~~
    Node.js virtual environment

    :copyright: (c) 2014 by Eugene Kalinin
    :license: BSD, see LICENSE for more details.
"""

nodeenv_version = '0.9.4'

import sys
import os
import stat
import logging
import optparse
import subprocess
import pipes

try:
    import ConfigParser
except ImportError:
    # Python 3
    from configparser import ConfigParser

from pkg_resources import parse_version

join = os.path.join
abspath = os.path.abspath

# ---------------------------------------------------------
# Utils


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


def node_version_from_opt(opt):
    """
    Parse the node version from the optparse options
    """
    if opt.node == 'system':
        out, err = subprocess.Popen(
            ["node", "--version"], stdout=subprocess.PIPE).communicate()
        return parse_version(clear_output(out).replace('v', ''))

    return parse_version(opt.node)


def create_logger():
    """
    Create logger for diagnostic
    """
    # create logger
    logger = logging.getLogger("nodeenv")
    logger.setLevel(logging.INFO)

    # monkey patch
    def emit(self, record):
        msg = self.format(record)
        fs = "%s" if getattr(record, "continued", False) else "%s\n"
        self.stream.write(fs % msg)
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
    logger.addHandler(ch)
    return logger
logger = create_logger()


def parse_args():
    """
    Parses command line arguments
    """
    parser = optparse.OptionParser(
        version=nodeenv_version,
        usage="%prog [OPTIONS] ENV_DIR")

    parser.add_option(
        '-n', '--node', dest='node',
        metavar='NODE_VER', default=get_last_stable_node_version(),
        help='The node.js version to use, e.g., '
        '--node=0.4.3 will use the node-v0.4.3 '
        'to create the new environment. The default is last stable version. '
        'Use `system` to use system-wide node.')

    parser.add_option(
        '-j', '--jobs', dest='jobs', default='2',
        help='Sets number of parallel commands at node.js compilation. '
        'The default is 2 jobs.')

    parser.add_option(
        '--load-average', dest='load_average',
        help='Sets maximum load average for executing parallel commands '
             'at node.js compilation.')

    parser.add_option(
        '-v', '--verbose',
        action='store_true', dest='verbose', default=False,
        help="Verbose mode")

    parser.add_option(
        '-q', '--quiet',
        action='store_true', dest='quiet', default=False,
        help="Quete mode")

    parser.add_option(
        '-r', '--requirements',
        dest='requirements', default='', metavar='FILENAME',
        help='Install all the packages listed in the given requirements file.')

    parser.add_option(
        '--prompt', dest='prompt',
        help='Provides an alternative prompt prefix for this environment')

    parser.add_option(
        '-l', '--list', dest='list',
        action='store_true', default=False,
        help='Lists available node.js versions')

    parser.add_option(
        '--update', dest='update',
        action='store_true', default=False,
        help='Install npm packages form file without node')

    parser.add_option(
        '--without-ssl', dest='without_ssl',
        action='store_true', default=False,
        help='Build node.js without SSL support')

    parser.add_option(
        '--debug', dest='debug',
        action='store_true', default=False,
        help='Build debug variant of the node.js')

    parser.add_option(
        '--profile', dest='profile',
        action='store_true', default=False,
        help='Enable profiling for node.js')

    parser.add_option(
        '--with-npm', dest='with_npm',
        action='store_true', default=False,
        help='Build without installing npm into the new virtual environment. '
        'Required for node.js < 0.6.3. By default, the npm included with '
        'node.js is used.')

    parser.add_option(
        '--npm', dest='npm',
        metavar='NPM_VER', default='latest',
        help='The npm version to use, e.g., '
        '--npm=0.3.18 will use the npm-0.3.18.tgz '
        'tarball to install. The default is last available version.')

    parser.add_option(
        '--no-npm-clean', dest='no_npm_clean',
        action='store_true', default=False,
        help='Skip the npm 0.x cleanup.  Cleanup is enabled by default.')

    parser.add_option(
        '--python-virtualenv', '-p', dest='python_virtualenv',
        action='store_true', default=False,
        help='Use current python virtualenv')

    parser.add_option(
        '--clean-src', '-c', dest='clean_src',
        action='store_true', default=False,
        help='Remove "src" directory after installation')

    parser.add_option(
        '--force', dest='force',
        action='store_true', default=False,
        help='Force installation in a pre-existing directory')

    parser.add_option(
        '--make', '-m', dest='make_path',
        metavar='MAKE_PATH',
        help='Path to make command',
        default='make')

    parser.add_option(
        '--prebuilt', dest='prebuilt',
        action='store_true', default=False,
        help='Install node.js from prebuilt package')

    options, args = parser.parse_args()

    if not options.list and not options.python_virtualenv:
        if not args:
            print('You must provide a DEST_DIR or '
                  'use current python virtualenv')
            parser.print_help()
            sys.exit(2)

        if len(args) > 1:
            print('There must be only one argument: DEST_DIR (you gave %s)' % (
                ' '.join(args)))
            parser.print_help()
            sys.exit(2)

    return options, args


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


def writefile(dest, content, overwrite=True, append=False):
    """
    Create file and write content in it
    """
    if not os.path.exists(dest):
        logger.debug(' * Writing %s ... ', dest, extra=dict(continued=True))
        f = open(dest, 'wb')
        f.write(content.encode('utf-8'))
        f.close()
        logger.debug('done.')
        return
    else:
        f = open(dest, 'rb')
        c = f.read()
        f.close()
        if c != content.encode('utf-8'):
            if not overwrite:
                logger.info(' * File %s exists with different content; '
                            ' not overwriting', dest)
                return
            if append:
                logger.info(' * Appending nodeenv settings to %s', dest)
                f = open(dest, 'ab')
                f.write(DISABLE_POMPT.encode('utf-8'))
                f.write(content.encode('utf-8'))
                f.write(ENABLE_PROMPT.encode('utf-8'))
                f.close()
                return
            logger.info(' * Overwriting %s with new content', dest)
            f = open(dest, 'wb')
            f.write(content.encode('utf-8'))
            f.close()
        else:
            logger.debug(' * Content %s already in place', dest)


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
        line = line.rstrip()
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


def get_node_src_url(version, postfix=''):
    node_name = 'node-v%s%s' % (version, postfix)
    tar_name = '%s.tar.gz' % (node_name)
    if parse_version(version) > parse_version("0.5.0"):
        node_url = 'http://nodejs.org/dist/v%s/%s' % (version, tar_name)
    else:
        node_url = 'http://nodejs.org/dist/%s' % (tar_name)
    return node_url


def download_node(node_url, src_dir, env_dir, opt):
    """
    Download source code
    """
    cmd = []
    cmd.append('curl')
    cmd.append('--silent')
    cmd.append('-L')
    cmd.append(node_url)
    cmd.append('|')
    cmd.append('tar')
    cmd.append('xzf')
    cmd.append('-')
    cmd.append('-C')
    cmd.append(pipes.quote(src_dir))
    cmd.extend(['--exclude', 'ChangeLog'])
    cmd.extend(['--exclude', 'LICENSE'])
    cmd.extend(['--exclude', 'README.md'])
    try:
        callit(cmd, opt.verbose, True, env_dir)
        logger.info(') ', extra=dict(continued=True))
    except OSError:
        postfix = '-RC1'
        logger.info('%s) ' % postfix, extra=dict(continued=True))
        new_node_url = get_node_src_url(opt.node, postfix)
        cmd[cmd.index(node_url)] = new_node_url
        callit(cmd, opt.verbose, True, env_dir)


def get_node_src_url_postfix(opt):
    if not opt.prebuilt:
        return ''

    import platform
    postfix_system = platform.system().lower()
    arches = {'x86_64': 'x64', 'i686': 'x86'}
    postfix_arch = arches[platform.machine()]
    return '-{0}-{1}'.format(postfix_system, postfix_arch)

# ---------------------------------------------------------
# Virtual environment functions


def copy_node_from_prebuilt(env_dir, src_dir):
    """
    Copy prebuilt binaries into environment
    """
    logger.info('.', extra=dict(continued=True))
    callit(['cp', '-a', src_dir + '/node-v*/*', env_dir], True, env_dir)
    logger.info('.', extra=dict(continued=True))


def build_node_from_src(env_dir, src_dir, node_src_dir, opt):
    env = {}
    make_param_names = ['load-average', 'jobs']
    make_param_values = map(
        lambda x: getattr(opt, x.replace('-', '_')),
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
        try:
            _, which_python2_output = callit(['which', 'python2'])
            python2_path = which_python2_output[0].decode('utf-8')
        except (OSError, IndexError):
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

    conf_cmd = []
    conf_cmd.append('./configure')
    conf_cmd.append('--prefix=%s' % pipes.quote(env_dir))
    if opt.without_ssl:
        conf_cmd.append('--without-ssl')
    if opt.debug:
        conf_cmd.append('--debug')
    if opt.profile:
        conf_cmd.append('--profile')

    make_cmd = opt.make_path

    callit(conf_cmd, opt.verbose, True, node_src_dir, env)
    logger.info('.', extra=dict(continued=True))
    callit([make_cmd] + make_opts, opt.verbose, True, node_src_dir, env)
    logger.info('.', extra=dict(continued=True))
    callit([make_cmd + ' install'], opt.verbose, True, node_src_dir, env)


def install_node(env_dir, src_dir, opt):
    """
    Download source code for node.js, unpack it
    and install it in virtual environment.
    """
    logger.info(' * Install node.js (%s' % opt.node,
                extra=dict(continued=True))

    node_url = get_node_src_url(opt.node, get_node_src_url_postfix(opt))
    node_src_dir = join(src_dir, 'node-v%s' % (opt.node))
    env_dir = abspath(env_dir)

    # get src if not downloaded yet
    if not os.path.exists(node_src_dir):
        download_node(node_url, src_dir, env_dir, opt)

    logger.info('.', extra=dict(continued=True))

    if opt.prebuilt:
        copy_node_from_prebuilt(env_dir, src_dir)
    else:
        build_node_from_src(env_dir, src_dir, node_src_dir, opt)

    logger.info(' done.')


def install_npm(env_dir, src_dir, opt):
    """
    Download source code for npm, unpack it
    and install it in virtual environment.
    """
    logger.info(' * Install npm.js (%s) ... ' % opt.npm,
                extra=dict(continued=True))
    cmd = [
        '. %s && curl --location --silent %s | '
        'clean=%s npm_install=%s bash && deactivate_node' % (
            pipes.quote(join(env_dir, 'bin', 'activate')),
            'https://www.npmjs.org/install.sh',
            'no' if opt.no_npm_clean else 'yes',
            opt.npm
        )
    ]
    callit(cmd, opt.verbose, True)
    logger.info('done.')


def install_packages(env_dir, opt):
    """
    Install node.js packages via npm
    """
    logger.info(' * Install node.js packages ... ',
                extra=dict(continued=True))
    packages = [package.strip() for package in
                open(opt.requirements).readlines()]
    activate_path = join(env_dir, 'bin', 'activate')
    real_npm_ver = opt.npm if opt.npm.count(".") == 2 else opt.npm + ".0"
    if opt.npm == "latest" or real_npm_ver >= "1.0.0":
        cmd = '. ' + pipes.quote(activate_path) + \
              ' && npm install -g %(pack)s'
    else:
        cmd = '. ' + pipes.quote(activate_path) + \
              ' && npm install %(pack)s' + \
              ' && npm activate %(pack)s'

    for package in packages:
        callit(cmd=[
            cmd % {"pack": package}], show_stdout=opt.verbose, in_shell=True)

    logger.info('done.')


def install_activate(env_dir, opt):
    """
    Install virtual environment activation script
    """
    files = {'activate': ACTIVATE_SH, 'shim': SHIM}
    if opt.node == "system":
        files["node"] = SHIM
    bin_dir = join(env_dir, 'bin')
    mod_dir = join('lib', 'node_modules')
    prompt = opt.prompt or '(%s)' % os.path.basename(os.path.abspath(env_dir))
    mode_0755 = (stat.S_IRWXU | stat.S_IXGRP |
                 stat.S_IRGRP | stat.S_IROTH | stat.S_IXOTH)

    shim_node = join(bin_dir, "node")
    if opt.node == "system":
        env = os.environ.copy()
        env.update({'PATH': remove_env_bin_from_path(env['PATH'], bin_dir)})
        which_node_output, _ = subprocess.Popen(
            ["which", "node"], stdout=subprocess.PIPE, env=env).communicate()
        shim_node = clear_output(which_node_output)

    for name, content in files.items():
        file_path = join(bin_dir, name)
        content = content.replace('__NODE_VIRTUAL_PROMPT__', prompt)
        content = content.replace('__NODE_VIRTUAL_ENV__',
                                  os.path.abspath(env_dir))
        content = content.replace('__SHIM_NODE__', shim_node)
        content = content.replace('__BIN_NAME__', os.path.basename(bin_dir))
        content = content.replace('__MOD_NAME__', mod_dir)
        # if we call in the same environment:
        #   $ nodeenv -p --prebuilt
        #   $ nodeenv -p --node=system
        # we should get `bin/node` not as binary+string.
        # `bin/activate` should be appended if we inside
        # existing python's virtual environment
        need_append = 0 if name in ('node', 'shim') else opt.python_virtualenv
        writefile(file_path, content, append=need_append)
        os.chmod(file_path, mode_0755)


def create_environment(env_dir, opt):
    """
    Creates a new environment in ``env_dir``.
    """
    if os.path.exists(env_dir) and not opt.python_virtualenv:
        logger.info(' * Environment already exists: %s', env_dir)
        if not opt.force:
            sys.exit(2)
    src_dir = abspath(join(env_dir, 'src'))
    mkdir(src_dir)

    if opt.node != "system":
        install_node(env_dir, src_dir, opt)
    else:
        mkdir(join(env_dir, 'bin'))
        mkdir(join(env_dir, 'lib'))
        mkdir(join(env_dir, 'lib', 'node_modules'))
    # activate script install must be
    # before npm install, npm use activate
    # for install
    install_activate(env_dir, opt)
    if node_version_from_opt(opt) < parse_version("0.6.3") or opt.with_npm:
        install_npm(env_dir, src_dir, opt)
    if opt.requirements:
        install_packages(env_dir, opt)
    # Cleanup
    if opt.clean_src:
        callit(['rm -rf', pipes.quote(src_dir)], opt.verbose, True, env_dir)


def print_node_versions():
    """
    Prints into stdout all available node.js versions
    """
    p = subprocess.Popen(
        "curl -s http://nodejs.org/dist/ | "
        "egrep -o '[0-9]+\.[0-9]+\.[0-9]+' | "
        "sort -u -k 1,1n -k 2,2n -k 3,3n -t . ",
        shell=True, stdout=subprocess.PIPE)
    # out, err = p.communicate()
    pos = 0
    rowx = []
    while 1:
        row = p.stdout.readline()
        pos += 1
        if not row:
            logger.info('\t'.join(rowx))
            break
        rowx.append(row.replace('\n', ''))
        if pos % 8 == 0:
            logger.info('\t'.join(rowx))
            rowx = []


def get_last_stable_node_version():
    """
    Return last stable node.js version
    """
    p = subprocess.Popen(
        "curl -s http://nodejs.org/dist/latest/ | "
        "egrep -o 'node-v[0-9]+\.[0-9]+\.[0-9]+' | "
        "sed -e 's/node-v//' | "
        "sort -u -k 1,1n -k 2,2n -k 3,3n -t . | "
        "tail -n1",
        shell=True, stdout=subprocess.PIPE)
    return p.stdout.read().decode("utf-8").replace("\n", "")


def get_env_dir(opt, args):
    if opt.python_virtualenv:
        try:
            return os.environ['VIRTUAL_ENV']
        except KeyError:
            logger.error('No python virtualenv is available')
            sys.exit(2)
    else:
        return args[0]


def main():
    """
    Entry point
    """
    opt, args = parse_args()

    if opt.list:
        print_node_versions()
    elif opt.update:
        env_dir = get_env_dir(opt, args)
        install_packages(env_dir, opt)
    else:
        env_dir = get_env_dir(opt, args)
        create_environment(env_dir, opt)


# ---------------------------------------------------------
# Shell scripts content

DISABLE_POMPT = """
# disable nodeenv's prompt
# (prompt already changed by original virtualenv's script)
# https://github.com/ekalinin/nodeenv/issues/26
NODE_VIRTUAL_ENV_DISABLE_PROMPT=1
"""

ENABLE_PROMPT = """
unset NODE_VIRTUAL_ENV_DISABLE_PROMPT
"""

SHIM = """#!/usr/bin/env bash
export NODE_PATH=__NODE_VIRTUAL_ENV__/lib/node_modules
export NPM_CONFIG_PREFIX=__NODE_VIRTUAL_ENV__
exec __SHIM_NODE__ $*
"""

ACTIVATE_SH = """

# This file must be used with "source bin/activate" *from bash*
# you cannot run it directly

deactivate_node () {
    # reset old environment variables
    if [ -n "$_OLD_NODE_VIRTUAL_PATH" ] ; then
        PATH="$_OLD_NODE_VIRTUAL_PATH"
        export PATH
        unset _OLD_NODE_VIRTUAL_PATH

        NODE_PATH="$_OLD_NODE_PATH"
        export NODE_PATH
        unset _OLD_NODE_PATH

        NPM_CONFIG_PREFIX="$_OLD_NPM_CONFIG_PREFIX"
        export NPM_CONFIG_PREFIX
        unset _OLD_NPM_CONFIG_PREFIX
    fi

    # This should detect bash and zsh, which have a hash command that must
    # be called to get it to forget past commands.  Without forgetting
    # past commands the $PATH changes we made may not be respected
    if [ -n "$BASH" -o -n "$ZSH_VERSION" ] ; then
        hash -r
    fi

    if [ -n "$_OLD_NODE_VIRTUAL_PS1" ] ; then
        PS1="$_OLD_NODE_VIRTUAL_PS1"
        export PS1
        unset _OLD_NODE_VIRTUAL_PS1
    fi

    unset NODE_VIRTUAL_ENV
    if [ ! "$1" = "nondestructive" ] ; then
    # Self destruct!
        unset -f deactivate_node
    fi
}

freeze () {
    NPM_VER=`npm -v | cut -d '.' -f 1`
    if [ "$NPM_VER" != '1' ]; then
        NPM_LIST=`npm list installed active 2>/dev/null | \
                  cut -d ' ' -f 1 | grep -v npm`
    else
        NPM_LIST=`npm ls -g | grep -E '^.{4}\w{1}' | \
                 grep -o -E '[a-zA-Z0-9\.\-]+@[0-9]+\.[0-9]+\.[0-9]+([\+\-][a-zA-Z0-9\.\-]+)*' | \
                 grep -v npm`
    fi

    if [ -z "$@" ]; then
        echo "$NPM_LIST"
    else
        echo "$NPM_LIST" > $@
    fi
}

# unset irrelavent variables
deactivate_node nondestructive

# find the directory of this script
# http://stackoverflow.com/a/246128
if [ "${BASH_SOURCE}" ] ; then
    SOURCE="${BASH_SOURCE[0]}"

    while [ -h "$SOURCE" ] ; do SOURCE="$(readlink "$SOURCE")"; done
    DIR="$( cd -P "$( dirname "$SOURCE" )" && pwd )"

    NODE_VIRTUAL_ENV="$(dirname "$DIR")"
else
    # dash not movable. fix use case:
    #   dash -c " . node-env/bin/activate && node -v"
    NODE_VIRTUAL_ENV="__NODE_VIRTUAL_ENV__"
fi

# NODE_VIRTUAL_ENV is the parent of the directory where this script is
export NODE_VIRTUAL_ENV

_OLD_NODE_VIRTUAL_PATH="$PATH"
PATH="$NODE_VIRTUAL_ENV/__BIN_NAME__:$PATH"
export PATH

_OLD_NODE_PATH="$NODE_PATH"
NODE_PATH="$NODE_VIRTUAL_ENV/__MOD_NAME__"
export NODE_PATH

_OLD_NPM_CONFIG_PREFIX="$NPM_CONFIG_PREFIX"
NPM_CONFIG_PREFIX="$NODE_VIRTUAL_ENV"
export NPM_CONFIG_PREFIX

if [ -z "$NODE_VIRTUAL_ENV_DISABLE_PROMPT" ] ; then
    _OLD_NODE_VIRTUAL_PS1="$PS1"
    if [ "x__NODE_VIRTUAL_PROMPT__" != x ] ; then
        PS1="__NODE_VIRTUAL_PROMPT__$PS1"
    else
    if [ "`basename \"$NODE_VIRTUAL_ENV\"`" = "__" ] ; then
        # special case for Aspen magic directories
        # see http://www.zetadev.com/software/aspen/
        PS1="[`basename \`dirname \"$NODE_VIRTUAL_ENV\"\``] $PS1"
    else
        PS1="(`basename \"$NODE_VIRTUAL_ENV\"`)$PS1"
    fi
    fi
    export PS1
fi

# This should detect bash and zsh, which have a hash command that must
# be called to get it to forget past commands.  Without forgetting
# past commands the $PATH changes we made may not be respected
if [ -n "$BASH" -o -n "$ZSH_VERSION" ] ; then
    hash -r
fi
"""

if __name__ == '__main__':
    main()
