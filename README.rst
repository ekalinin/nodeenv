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

    $ python nve.py env-2.6
    $ . env-2.6/bin/activate
    (env-0.2.6) $ node -v
    v0.2.6
    (env-0.2.6) $ deactivate

    $ python nve.py --node "0.4.3" --without-ssl --with-npm env-4.3
    $ . env-4.3/bin/activate
    (env-0.4.3) $ node -v
    v0.4.3
    (env-0.4.3) $ npm -v
    0.3.17
    (env-0.4.3) $ deactivate

If you install it you can also just do ``nve ENV``.

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

