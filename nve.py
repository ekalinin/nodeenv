#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    nve
    ~~~
    nve - Node.js virtual environment

    TODO:
        - install npm
        - add setup.py
        - add README

    :copyright: (c) 2011 by Eugene Kalinin
    :license: BSD, see LICENSE for more details.
"""

nodeenv_version = '0.1'

import sys
import os
import optparse
import urllib
import tarfile
import logging

join = os.path.join
abspath = os.path.abspath

# ---------------------------------------------------------
# Utils

def create_logger():
    """
    Create logger for diagnostic
    """
    # create logger
    logger = logging.getLogger("node-venv")
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
        version=nodeenv_version ,
        usage="%prog [OPTIONS] DEST_DIR")

    parser.add_option(
        '-n', '--node', dest='node', 
        metavar='NODE_VER', default="0.2.6",
        help='The node.js version to use, e.g., --version=0.4.3 will use the node-v0.4.3 '
        'to create the new environment. The default is 0.2.6')

    parser.add_option(
        '--prompt',
        dest='prompt',
        help='Provides an alternative prompt prefix for this environment')

    parser.add_option( '--without-ssl', 
        action='store_true', default=False, 
        dest='without_ssl',
        help='Build node.js without SSL support')

    options, args = parser.parse_args()

    if not args:
        print('You must provide a DEST_DIR')
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

    if not os.path.exists(node_tar):
        logger.info(' * Retrieve: %s ... ', node_url, extra=dict(continued=True))
        urllib.urlretrieve(node_url, node_tar)
        logger.info('done.')
    else:
        logger.info(' * Source for %s exists: %s'%(node_name, node_tar))

    logger.info(' * Unpack: %s ... ', node_tar, extra=dict(continued=True))
    tar = tarfile.open(node_tar)
    tar.extractall(src_dir)
    tar.close()
    logger.info('done.')

    src_dir = join(src_dir, node_name)
    env_dir = abspath(env_dir)
    old_chdir = os.getcwd()
    conf_cmd = './configure --prefix=%s'%(env_dir)
    if opt.without_ssl:
        conf_cmd += ' --without-ssl'
    try:
        logger.info(' * Compile: %s ...', src_dir)
        os.chdir(src_dir)
        os.system(conf_cmd)
        os.system('make')
        os.system('make install')
        logger.info(' * Compile: %s ... done', src_dir)
    finally:
        if os.getcwd() != old_chdir:
            os.chdir(old_chdir)


def install_npm(env_dir, src_dir):
    pass


def install_activate(env_dir, opt):
    """
    Install virtual environment activation script
    """
    files = {'activate': ACTIVATE_SH}
    bin_dir = join(env_dir, 'bin')
    prompt = opt.prompt or '(env-%s)'%opt.node 
    for name, content in files.items():
        content = content.replace('__VIRTUAL_PROMPT__', prompt)
        content = content.replace('__VIRTUAL_ENV__', os.path.abspath(env_dir))
        content = content.replace('__BIN_NAME__', os.path.basename(bin_dir))
        writefile(os.path.join(bin_dir, name), content)
 

def create_environment(env_dir, opt):
    """
    Creates a new environment in ``env_dir``.
    """
    dirs = {}
    dirs["src"] = abspath(join(env_dir, 'src'))
    for dir_name, dir_path in dirs.items():
        mkdir(dir_path)

    install_node(env_dir, dirs["src"], opt)
    #install_npm(env_dir, dirs["src"])
    install_activate(env_dir, opt)


def main():
    opt, args = parse_args()
    env_dir = args[0]
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
    if [ -n "$_OLD_VIRTUAL_PYTHONHOME" ] ; then
        PYTHONHOME="$_OLD_VIRTUAL_PYTHONHOME"
        export PYTHONHOME
        unset _OLD_VIRTUAL_PYTHONHOME
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

