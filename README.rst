Node.js virtual environment
===========================

``nodeenv`` (node.js virtual environment) is a tool to create
isolated node.js environments.

It creates an environment that has its own installation directories,
that doesn't share libraries with other node.js virtual environments.

Also the new environment can be integrated with the environment which was built
by virtualenv_ (python).

If you use nodeenv feel free to add your project on wiki: `Who-Uses-Nodeenv`_.

.. _Who-Uses-Nodeenv: https://github.com/ekalinin/nodeenv/wiki/Who-Uses-Nodeenv

.. image:: https://github.com/ekalinin/nodeenv/actions/workflows/main.yml/badge.svg?branch=master
    :target: https://github.com/ekalinin/nodeenv/actions/workflows/main.yml
    :alt: CI

.. contents:: :local:


Install
-------

Global installation
^^^^^^^^^^^^^^^^^^^

You can install nodeenv globally with `easy_install`_::

    $ sudo easy_install nodeenv

or with `pip`_::

    $ sudo pip install nodeenv

or on Debian using `dpkg`_::

    $ ln -s debian-upstream debian
    $ dpkg-buildpackage -uc -us -b
    $ sudo dpkg -i $(ls -1rt ../nodeenv_*.deb | tail -n1)

.. _dpkg: https://www.debian.org/doc/manuals/debian-faq/ch-pkgtools.en.html

Local installation
^^^^^^^^^^^^^^^^^^

If you're using virtualenv_ then you can install nodeenv via
pip_/easy_install_ inside any virtual environment built with virtualenv::

    $ virtualenv env
    $ . env/bin/activate
    (env) $ pip install nodeenv
    (env) $ nodeenv --version
    0.6.5

If you want to work with the latest version of the nodeenv you can
install it from the github `repository`_::

    $ git clone https://github.com/ekalinin/nodeenv.git
    $ ./nodeenv/nodeenv.py --help

or with `pip`_::

    $ pip install -e git+https://github.com/ekalinin/nodeenv.git#egg=nodeenv

.. _repository: https://github.com/ekalinin/nodeenv
.. _pip: http://pypi.python.org/pypi/pip
.. _easy_install: http://pypi.python.org/pypi/setuptools


Dependency
----------

For nodeenv
^^^^^^^^^^^

* python (2.6+, 3.5+, or pypy)
* make
* tail

For node.js
^^^^^^^^^^^

* libssl-dev

Usage
-----

Basic
^^^^^

Create new environment::

    $ nodeenv env

Activate new environment::

    $ . env/bin/activate

Check versions of main packages::

    (env) $ node -v
    v0.10.26

    (env) $ npm -v
    1.4.3

Deactivate environment::

    (env) $ deactivate_node

Advanced
^^^^^^^^

Get available node.js versions::

    $ nodeenv --list
    0.0.1   0.0.2   0.0.3   0.0.4   0.0.5   0.0.6   0.1.0
    0.1.2   0.1.3   0.1.4   0.1.5   0.1.6   0.1.7   0.1.8
    0.1.10  0.1.11  0.1.12  0.1.13  0.1.14  0.1.15  0.1.16
    0.1.18  0.1.19  0.1.20  0.1.21  0.1.22  0.1.23  0.1.24
    0.1.26  0.1.27  0.1.28  0.1.29  0.1.30  0.1.31  0.1.32
    0.1.90  0.1.91  0.1.92  0.1.93  0.1.94  0.1.95  0.1.96
    0.1.98  0.1.99  0.1.100 0.1.101 0.1.102 0.1.103 0.1.104
    0.2.1   0.2.2   0.2.3   0.2.4   0.2.5   0.2.6   0.3.0
    0.3.2   0.3.3   0.3.4   0.3.5   0.3.6   0.3.7   0.3.8
    0.4.1   0.4.2   0.4.3   0.4.4   0.4.5   0.4.6

Install node.js "0.4.3" without ssl support with 4 parallel commands
for compilation and npm.js "0.3.17"::

    $ nodeenv --without-ssl --node=0.4.3 --npm=0.3.17 --with-npm --jobs=4 env-4.3

Install node.js from the source::

    $ nodeenv --node=0.10.25 --source env-0.10.25

Install node.js from a mirror::

    $ nodeenv --node=10.19.0 --mirror=https://npm.taobao.org/mirrors/node

It's much faster to install from the prebuilt package than Install & compile
node.js from source::

    $ time nodeenv --node=0.10.25 --prebuilt env-0.10.25-prebuilt
     + Install node.js (0.10.25) ... done.

    real    0m6.928s
    user    0m0.408s
    sys     0m1.144s

    $ time nodeenv --node=0.10.25 --source env-0.10.25-src
     + Install node.js (0.10.25) ... done.

    real    4m12.602s
    user    6m34.112s
    sys     0m30.524s

Create a new environment with the system-wide node.js::

    $ nodeenv --node=system

Saving the versions of all installed packages to a file::

    $ . env-4.3/bin/activate
    (env-4.3)$ npm install -g express
    (env-4.3)$ npm install -g jade
    (env-4.3)$ freeze ../prod-requirements.txt

If you want to list locally installed packages use ``-l`` option::

    (env-4.3)$ freeze -l ../prod-requirements.txt

Create an environment from a requirements file::

    $ nodeenv --requirements=../prod-requirements.txt --jobs=4 env-copy

Requirements files are plain text files that contain a list of packages
to be installed. These text files allow you to create repeatable installations.
Requirements file example::

    $ cat ../prod-requirements.txt
    connect@1.3.0
    express@2.2.2
    jade@0.10.4
    mime@1.2.1
    npm@0.3.17
    qs@0.0.7

If you already have the python virtualenv tool, and want to use nodeenv and
virtualenv in conjunction, then you should create (or activate) the python
virtual environment::

    # in case of using virtualenv_wrapper
    $ mkvirtualenv my_env

    # in case of using virtualenv
    $ . my_env/bin/activate

and add a node virtual environment to this existing new_venv::

    $ nodeenv -p

If you need to set the path to make used to build node::

	$ nodeenv -m /usr/local/bin/gmake ENV

That's all. Now, all your node.js modules will be installed into your virtual
environment::

    $ workon my_env
    $ npm install -g coffee-script
    $ command -v coffee
    /home/monty/virtualenvs/my_env/bin/coffee

Creating a virtual environment with a custom prompt:

    $ nodeenv --node=12.18.2 --prompt="(myenv)" nodeenv

If environment's directory already exists then you can use ``--force`` option::

    $ nodeenv --requirements=requirements.txt --jobs=4 --force env

If you already have an environment and want to update packages from requirements
file you can use ``--update`` option::

    $ . env-4.3/bin/activate
    (env-4.3)$ nodeenv --requirements=requirements.txt --update env-4.3

If you want to call node from environment without activation then you should
use `shim` script::

    $ ./env-4.3/bin/shim --version
    v0.4.3

Command Line Options
--------------------

Basic options
^^^^^^^^^^^^^

``-n NODE_VER, --node=NODE_VER``
    The node.js version to use, e.g., ``--node=22.11.0``. The default is the
    last stable version (``latest``). Use ``lts`` for the latest LTS release.
    Use ``system`` to use system-wide node.

``-l, --list``
    Lists available node.js versions.

``-p, --python-virtualenv``
    Use current python virtualenv.

``-r FILENAME, --requirements=FILENAME``
    Install all the packages listed in the given requirements file.

``--prompt=PROMPT``
    Provides an alternative prompt prefix for this environment.

``--force``
    Force installation in a pre-existing directory.

``--update``
    Install npm packages from file without reinstalling node.

Installation options
^^^^^^^^^^^^^^^^^^^^

``--prebuilt``
    Install node.js from prebuilt package (default).

``--source``
    Install node.js from the source (Unix only).

``--mirror=URL``
    Set mirror server of nodejs.org to download from.

``-c, --clean-src``
    Remove "src" directory after installation.

NPM options
^^^^^^^^^^^

``--npm=NPM_VER``
    The npm version to use, e.g., ``--npm=10.0.0``.
    The default is the last available version (``latest``).

``--with-npm``
    Install npm into the new virtual environment. Required for node.js < 0.6.3.
    By default, the npm included with node.js is used.

``--no-npm-clean``
    Skip the npm 0.x cleanup. Cleanup is enabled by default.

Compilation options (Unix only)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``-j JOBS, --jobs=JOBS``
    Sets number of parallel commands at node.js compilation. The default is 2 jobs.

``--load-average=LOAD``
    Sets maximum load average for executing parallel commands at node.js compilation.

``-m MAKE_PATH, --make=MAKE_PATH``
    Path to make command.

``--without-ssl``
    Build node.js without SSL support.

``--debug``
    Build debug variant of the node.js.

``--profile``
    Enable profiling for node.js.

Other options
^^^^^^^^^^^^^

``-v, --verbose``
    Verbose mode.

``-q, --quiet``
    Quiet mode.

``-C CONFIG_FILE, --config-file=CONFIG_FILE``
    Load a different config file than ``~/.nodeenvrc``.
    Pass an empty string for no config (use built-in defaults).

``--ignore_ssl_certs``
    Ignore SSL certificates for package downloads. **UNSAFE - use at your own risk**.

``--version``
    Show program version and exit.

Configuration
-------------
You can use the INI-style file ``~/.nodeenvrc`` to set default values for many options,
the keys in that file are the long command-line option names.

These are the available options and their defaults::

    [nodeenv]
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

Alternatives
------------

There are several alternatives that create isolated environments:

* `nave <https://github.com/isaacs/nave>`_ - Virtual Environments for Node.
  Nave stores all environments in one directory ``~/.nave``. Can create
  per node version environments using `nave use envname versionname`.
  Can not pass additional arguments into configure (for example --without-ssl)
  Can't run on windows because it relies on a POSIX shell.

* `nvm <https://github.com/creationix/nvm/blob/master/nvm.sh>`_ - Node Version
  Manager. It is necessarily to do `nvm sync` for caching available node.js
  version.
  Can not pass additional arguments into configure (for example --without-ssl)

* virtualenv_ - Virtual Python Environment builder. For python only.

.. _`virtualenv`: https://github.com/pypa/virtualenv

LICENSE
=======

BSD / `LICENSE <https://github.com/ekalinin/nodeenv/blob/master/LICENSE>`_
