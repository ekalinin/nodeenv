#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    nodeenv
    ~~~~~~~
    Node.js virtual environment

    :copyright: (c) 2011 by Eugene Kalinin
    :license: BSD, see LICENSE for more details.
"""

nodeenv_version = '0.3.0'

import sys
import os
import time
import logging
import optparse
import subprocess
import ConfigParser

join = os.path.join
abspath = os.path.abspath

# ---------------------------------------------------------
# Utils

def create_logger():
    """
    Create logger for diagnostic
    """
    # create logger
    logger = logging.getLogger("nodeenv")
    logger.setLevel(logging.DEBUG)

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

    parser.add_option('-n', '--node', dest='node', 
        metavar='NODE_VER', default=get_last_stable_node_version(),
        help='The node.js version to use, e.g., '
        '--node=0.4.3 will use the node-v0.4.3 '
        'to create the new environment. The default is last stable version.')

    parser.add_option('-j', '--jobs', dest='jobs', default=2,
        help='Sets number of parallel commands at node.js compilation. '
        'The default is 2 jobs.')

    parser.add_option('-v', '--verbose',
        action='store_true', dest='verbose', default=False,
        help="Verbose mode")

    parser.add_option('-q', '--quiet',
        action='store_true', dest='quiet', default=False,
        help="Quete mode")

    parser.add_option('-r', '--requirement',
        dest='requirements', default='',  metavar='FILENAME',
        help='Install all the packages listed in the given requirements file. '
             'Not compatible with --without-npm option.')

    parser.add_option('--prompt', dest='prompt',
        help='Provides an alternative prompt prefix for this environment')

    parser.add_option('-l', '--list', dest='list',
        action='store_true', default=False,
        help='Lists available node.js versions')

    parser.add_option( '--without-ssl', dest='without_ssl',
        action='store_true', default=False, 
        help='Build node.js without SSL support')

    parser.add_option( '--debug', dest='debug',
        action='store_true', default=False, 
        help='Build debug variant of the node.js')

    parser.add_option( '--profile', dest='profile',
        action='store_true', default=False, 
        help='Enable profiling for node.js')

    parser.add_option( '--without-npm', dest='without_npm',
        action='store_true', default=False, 
        help='Install npm in new virtual environment')

    options, args = parser.parse_args()

    if not options.list:
        if not args:
            print('You must provide a DEST_DIR')
            parser.print_help()
            sys.exit(2)

        if len(args) > 1:
            print('There must be only one argument: DEST_DIR (you gave %s)' % (
                ' '.join(args)))
            parser.print_help()
            sys.exit(2)

        if options.requirements and options.without_npm:
            print('These options are not compatible: --requirements, --without-npm')
            parser.print_help()
            sys.exit(2)


    return options, args


def mkdir(path):
    """
    Create directory
    """
    if not os.path.exists(path):
        logger.info(' * Creating: %s ... ', path, extra=dict(continued=True))
        os.makedirs(path)
        logger.info('done.')
    else:
        logger.info(' * Directory %s already exists', path)


def writefile(dest, content, overwrite=True):
    if not os.path.exists(dest):
        logger.info(' * Writing %s ... ', dest, extra=dict(continued=True))
        f = open(dest, 'wb')
        f.write(content.encode('utf-8'))
        f.close()
        logger.info('done.')
        return
    else:
        f = open(dest, 'rb')
        c = f.read()
        f.close()
        if c != content:
            if not overwrite:
                logger.notify(' * File %s exists with different content; not overwriting', dest)
                return
            logger.notify(' * Overwriting %s with new content', dest)
            f = open(dest, 'wb')
            f.write(content.encode('utf-8'))
            f.close()
        else:
            logger.info(' * Content %s already in place', dest)


def callit(cmd, show_stdout=True, in_shell=False, 
        cwd=None, extra_env=None):
    """
    Execute cmd line in sub-shell
    """
    all_output = []
    cmd_parts = []

    for part in cmd:
        if len(part) > 45:
            part = part[:20]+"..."+part[-20:]
        if ' ' in part or '\n' in part or '"' in part or "'" in part:
            part = '"%s"' % part.replace('"', '\\"')
        cmd_parts.append(part)
    cmd_desc = ' '.join(cmd_parts)
    logger.debug(" ** Running command %s" % cmd_desc)

    if in_shell:
        cmd = ' '.join(cmd)

    # output
    if show_stdout:
        stdout = None
    else:
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
        logger.fatal(" ** Error %s while executing command %s" % (e, cmd_desc))
        raise

    if show_stdout:
        stdout = proc.stdout
        while stdout:
            line = stdout.readline()
            if not line:
                break
            line = line.rstrip()
            logger.info(line)
    else:
        proc.communicate()
    proc.wait()

    # error handler
    if proc.returncode:
        raise OSError(" * Command %s failed with error code %s"
            % (cmd_desc, proc.returncode))

    return proc.returncode, all_output 


# ---------------------------------------------------------
# Virtual environment functions

def install_node(env_dir, src_dir, opt):
    """
    Download source code for node.js, unpack it
    and install it in virtual environment.
    """
    node_name = 'node-v%s'%(opt.node)
    tar_name = '%s.tar.gz'%(node_name)
    node_url = 'http://nodejs.org/dist/%s'%(tar_name)
    node_tar = join(src_dir, tar_name)
    node_src_dir = join(src_dir, node_name)
    env_dir = abspath(env_dir)
    old_chdir = os.getcwd()

    if not os.path.exists(node_src_dir):
        logger.info(' * Retrieve: %s ... ', node_url)
        cmd_progress = '-#'
        if opt.quiet:
            cmd_progress = '--silent'
        cmd = 'curl %s -L "%s" | tar xzf - -C "%s" '%\
            (cmd_progress, node_url, src_dir)
        os.system(cmd)
        logger.info(' * Retrieve: %s ... done.', node_url)
    else:
        logger.info(' * Source exists: %s'%(node_src_dir))

    env = {'JOBS': str(opt.jobs) }
    conf_cmd = []
    conf_cmd.append('./configure')
    conf_cmd.append('--prefix=%s'%(env_dir))
    if opt.without_ssl:
        conf_cmd.append('--without-ssl')
    if opt.debug:
        conf_cmd.append('--debug') 
    if opt.profile:
        conf_cmd.append('--profile')

    logger.info(' * Compile: %s ...', node_src_dir)
    callit(conf_cmd         , opt.verbose, True, node_src_dir, env)
    callit(['make']         , opt.verbose, True, node_src_dir, env)
    callit(['make install'] , opt.verbose, True, node_src_dir, env)
    logger.info(' * Compile: %s ... done' % (node_src_dir) )


def install_npm(env_dir, src_dir, opt):
    """
    Download source code for npm, unpack it
    and install it in virtual environment.
    """
    if opt.verbose:
        logger.info(' * Install node.js package manager ... ')
        os.system('. %s && curl %s|bash && deactivate'%(
                join(env_dir, 'bin', 'activate'), 
                'http://npmjs.org/install.sh'))
        logger.info(' * Install node.js package manager ... done.')
    else:
        logger.info(' * Install node.js package manager ... ', 
            extra=dict(continued=True))
        npm = subprocess.Popen('. %s && curl %s|bash && deactivate'%(
                join(env_dir, 'bin', 'activate'), 
                'http://npmjs.org/install.sh'), shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        npm.communicate()
        logger.info('done.')


def install_packages(env_dir, opt):
    logger.info(' * Install node.js packages ... ')
    packages = [ package.replace('\n', '') for package in 
                    open(opt.requirements).readlines() ]
    activate_path = join(env_dir, 'bin', 'activate')
    for package in packages:
        callit(cmd=['. '+ activate_path + 
                    ' && ' + 'npm install ' + package +
                    ' && ' + 'npm activate ' + package],
                show_stdout=opt.verbose, in_shell=True)
    logger.info(' * Install node.js packages ... done.')

def install_activate(env_dir, opt):
    """
    Install virtual environment activation script
    """
    files = {'activate': ACTIVATE_SH}
    bin_dir = join(env_dir, 'bin')
    prompt = opt.prompt or '(env-%s)'%opt.node 
    for name, content in files.items():
        file_path = join(bin_dir, name)
        content = content.replace('__VIRTUAL_PROMPT__', prompt)
        content = content.replace('__VIRTUAL_ENV__', os.path.abspath(env_dir))
        content = content.replace('__BIN_NAME__', os.path.basename(bin_dir))
        writefile(file_path, content)
        os.chmod(file_path, 0755)


def create_environment(env_dir, opt):
    """
    Creates a new environment in ``env_dir``.
    """
    if os.path.exists(env_dir):
        logger.info(' * Environment is allready exists: %s', env_dir)
        sys.exit(2)
    src_dir = abspath(join(env_dir, 'src'))
    mkdir(src_dir)
    save_env_options(env_dir, opt)

    install_node(env_dir, src_dir, opt)
    # activate script install must be
    # before npm install, npm use activate
    # for install
    install_activate(env_dir, opt)
    if not opt.without_npm:
        install_npm(env_dir, src_dir, opt)
    if opt.requirements:
        install_packages(env_dir, opt)


def print_node_versions():
    """
    Prints into stdout all available node.js versions
    """
    p = subprocess.Popen(
        "curl -s http://nodejs.org/dist/ | "
        "egrep -o '[0-9]+\.[0-9]+\.[0-9]+' | "
        "sort -u -k 1,1n -k 2,2n -k 3,3n -t . ",
        shell=True, stdout=subprocess.PIPE)
    #out, err = p.communicate()
    pos = 0
    rowx = []
    while 1:
        row = p.stdout.readline()
        pos += 1
        if not row:
            logger.info('\t'.join(rowx))
            break
        if pos%8 == 0:
            logger.info('\t'.join(rowx))
            rowx =[]
        else:
            rowx.append(row.replace('\n', ''))


def get_last_stable_node_version():
    """
    Return last stable node.js version
    """
    p = subprocess.Popen(
        "curl -s http://nodejs.org/dist/ | "
        "egrep -o '[0-9]+\.[2468]+\.[0-9]+' | "
        "sort -u -k 1,1n -k 2,2n -k 3,3n -t . | "
        "tail -n1",
        shell=True, stdout=subprocess.PIPE)
    return p.stdout.readline().replace("\n", "")


def save_env_options(env_dir, opt, file_path='install.cfg'):
    """
    Save command line options into config file
    """
    section_name = 'options'
    config = ConfigParser.RawConfigParser()
    config.add_section(section_name)
    for o, v in opt.__dict__.items():
        config.set(section_name, o, v)

    with open(join(env_dir, file_path), 'wb') as configfile:
        config.write(configfile)


def main():
    opt, args = parse_args()
    if opt.list:
        print_node_versions()
    else:
        env_dir = args[0]
        if opt.quiet:
            logger.setLevel(logging.CRITICAL)
        create_environment(env_dir, opt)


# ---------------------------------------------------------
# Shell scripts content

ACTIVATE_SH = """
# This file must be used with "source bin/activate" *from bash*
# you cannot run it directly

deactivate () {
    # reset old environment variables
    if [ -n "$_OLD_VIRTUAL_PATH" ] ; then
        PATH="$_OLD_VIRTUAL_PATH"
        export PATH
        unset _OLD_VIRTUAL_PATH
    fi

    # This should detect bash and zsh, which have a hash command that must
    # be called to get it to forget past commands.  Without forgetting
    # past commands the $PATH changes we made may not be respected
    if [ -n "$BASH" -o -n "$ZSH_VERSION" ] ; then
        hash -r
    fi

    if [ -n "$_OLD_VIRTUAL_PS1" ] ; then
        PS1="$_OLD_VIRTUAL_PS1"
        export PS1
        unset _OLD_VIRTUAL_PS1
    fi

    unset VIRTUAL_ENV
    if [ ! "$1" = "nondestructive" ] ; then
    # Self destruct!
        unset -f deactivate
    fi
}

freeze () {
    npm list installed active | cut -d ' ' -f 1 > $@
}

# unset irrelavent variables
deactivate nondestructive

VIRTUAL_ENV="__VIRTUAL_ENV__"
export VIRTUAL_ENV

_OLD_VIRTUAL_PATH="$PATH"
PATH="$VIRTUAL_ENV/__BIN_NAME__:$PATH"
export PATH

if [ -z "$VIRTUAL_ENV_DISABLE_PROMPT" ] ; then
    _OLD_VIRTUAL_PS1="$PS1"
    if [ "x__VIRTUAL_PROMPT__" != x ] ; then
    PS1="__VIRTUAL_PROMPT__$PS1"
    else
    if [ "`basename \"$VIRTUAL_ENV\"`" = "__" ] ; then
        # special case for Aspen magic directories
        # see http://www.zetadev.com/software/aspen/
        PS1="[`basename \`dirname \"$VIRTUAL_ENV\"\``] $PS1"
    else
        PS1="(`basename \"$VIRTUAL_ENV\"`)$PS1"
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

