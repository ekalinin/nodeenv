Node.js virtual environment
===========================

``nodeenv`` (node.js virtual environment) is a tool to create 
isolated node.js environments.

It creates an environment that has its own installation directories, 
that doesn't share libraries with other node.js virtual environments.


Install
-------

You can install nodeenv with `easy_install`_::

    $ sudo easy_install nodeenv

or `pip`_::

    $ sudo pip install nodeenv

If you want to work with the latest version of the nodeenv you can 
install it from the github `repository`_::

    $ git clone https://github.com/ekalinin/nodeenv.git
    $ ./nodeenv/nodeenv.py --help

Or you can just download raw nodeenv.py and use it::

    $ wget https://raw.github.com/ekalinin/nodeenv/master/nodeenv.py
    $ python nodeenv.py --version
    0.4.0

.. _repository: https://github.com/ekalinin/nodeenv
.. _pip: http://pypi.python.org/pypi/pip
.. _easy_install: http://pypi.python.org/pypi/setuptools


Dependency
----------

For nodeenv
^^^^^^^^^^^

* make
* curl
* egrep
* sort
* tail
* tar

For node.js
^^^^^^^^^^^

* python
* libssl-dev

Usage
-----

Basic
^^^^^

Install new environment::

    $ nodeenv env

Activate new environment::

    $ . env/bin/activate

Chek versions of main packages::

    (env) $ node -v
    v0.4.6

    (env) $ npm -v
    0.3.18

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

    $ nodeenv --without-ssl --node=0.4.3 --npm=0.3.17 --jobs=4 env-4.3

Saving into the file versions of all installed packages::

    $ . env-4.3/bin/activate
    (env-4.3)$ npm install express
    (env-4.3)$ npm install jade
    (env-4.3)$ freeze ../prod-requirements.txt

Create environment copy from requirement file::

    $ nodeenv --requirement=../prod-requirements.txt --jobs=4 env-copy

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


Alternatives
------------

There are several alternatives that create isolated environments:

* `nave <https://github.com/isaacs/nave>`_ - Virtual Environments for Node.
  Nave stores all environments in one directory ``~/.nave``. Thus it is not 
  possible to create different environments for one version of node.js.
  Can not pass additional arguments into configure (for example --without-ssl)

* `nvm <https://github.com/creationix/nvm/blob/master/nvm.sh>`_ - Node Version
  Manager. It is necessarily to do `nvm sync` for caching available node.js
  version.
  Can not pass additional arguments into configure (for example --without-ssl)

* `virtualenv <https://github.com/pypa/virtualenv>`_ Virtual Python Environment
  builder. For python only.

