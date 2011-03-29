Node.js virtual environment
===========================

``nve`` (node.js virtual environment) is a tool to create 
isolated node.js environments.

It creates an environment that has its own installation directories, 
that doesn't share libraries with other node.js virtual environments.


Install
-------

You can install nve with ``easy_install nodeenv``, or from the `git
repository <https://github.com/ekalinin/nodeenv>`_ or from a `tarball
<https://github.com/ekalinin/nodeenv/tarball/master>`_.


Usage
-----

The basic usage is::


    $ ./nve.py --without-ssl env
     * Creating: ~/nodeenv/env/src ... done.
     * Retrieve: http://nodejs.org/dist/node-v0.4.4.tar.gz ...
    ######################################################################## 100,0%
     * Retrieve: http://nodejs.org/dist/node-v0.4.4.tar.gz ... done.
     * Compile: ~/nodeenv/env/src/node-v0.4.4 ... done.
     * Writing env/bin/activate ... done.

    $ . env/bin/activate

    (env-0.4.4) $ node -v
    v0.4.4

    (env-0.4.4) $ deactivate

    $ ./nve.py --list
    0.0.1   0.0.2   0.0.3   0.0.4   0.0.5   0.0.6   0.1.0
    0.1.2   0.1.3   0.1.4   0.1.5   0.1.6   0.1.7   0.1.8
    0.1.10  0.1.11  0.1.12  0.1.13  0.1.14  0.1.15  0.1.16
    0.1.18  0.1.19  0.1.20  0.1.21  0.1.22  0.1.23  0.1.24
    0.1.26  0.1.27  0.1.28  0.1.29  0.1.30  0.1.31  0.1.32
    0.1.90  0.1.91  0.1.92  0.1.93  0.1.94  0.1.95  0.1.96
    0.1.98  0.1.99  0.1.100 0.1.101 0.1.102 0.1.103 0.1.104
    0.2.1   0.2.2   0.2.3   0.2.4   0.2.5   0.2.6   0.3.0
    0.3.2   0.3.3   0.3.4   0.3.5   0.3.6   0.3.7   0.3.8
    0.4.1   0.4.2   0.4.3   0.4.4

    $ ./nve.py --without-ssl --node "0.4.3" --with-npm env-4.3
     * Creating: /home/shorrty/projects/my/nodeenv/env-4.3/src ... done.
     * Retrieve: http://nodejs.org/dist/node-v0.4.3.tar.gz ...
    ######################################################################## 100,0%
     * Retrieve: http://nodejs.org/dist/node-v0.4.3.tar.gz ... done.
     * Compile: /home/shorrty/projects/my/nodeenv/env-4.3/src/node-v0.4.3 ... done.
     * Writing env-4.3/bin/activate ... done.
     * Install node.js package manager ... done.

    $ . env-4.3/bin/activate

    (env-0.4.3) $ node -v
    v0.4.3

    (env-0.4.3) $ npm -v
    0.3.18

    (env-0.4.3) $ deactivate


Alternatives
------------

There are several alternatives that create isolated environments:

* `nave <https://github.com/isaacs/nave>`_ - Virtual Environments for Node.
  Nave stores all environments in one directory ``~/.nave``. Thus not possible
  to create different environments for one version of node.js.
  Can not pass additional arguments into configure (for example --without-ssl)

* `nvm <https://github.com/creationix/nvm/blob/master/nvm.sh>`_ - Node Version
  Manager. It is necessarily to do `nvm sync` for caching available node.js
  version.
  Can not pass additional arguments into configure (for example --without-ssl)

* `virtualenv <https://github.com/pypa/virtualenv>`_ Virtual Python Environment
  builder. For python only.

