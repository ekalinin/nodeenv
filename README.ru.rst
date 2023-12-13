Виртуальное окружение для Node.js
=================================

``nodeenv`` (node.js virtual environment) — утилита для создания изолированных
окружений для node.js.

Результатом работы утилиты является создание изолированного окружения в
отдельной директории, которое (окружение) никак не зависит от других
установок node.js.

Так же новое окружение может быть интегрировано в уже существующее окружение,
созданное ранее с помощью virtualenv_ (python).

Если вы используете nodeenv, добавьте, пожалуйста, свой проект на wiki_.

.. _wiki: https://github.com/ekalinin/nodeenv/wiki/Who-Uses-Nodeenv

Установка
---------

Глобальная
^^^^^^^^^^

Nodeenv можно установить с помощью `easy_install`_::

    $ sudo easy_install nodeenv

или с помощью `pip`_::

    $ sudo pip install nodeenv

Локальная
^^^^^^^^^

Если же используется virtualenv_, то можно установить nodeenv
внутри виртуального окружения с помощью pip_/easy_install_::

    $ virtualenv env
    $ . env/bin/activate
    (env) $ pip install nodeenv
    (env) $ nodeenv --version
    0.6.5

Если есть желание поработать с последней версией nodeenv, то
установить его можно напрямую из репозитория::

    $ git clone https://github.com/ekalinin/nodeenv.git
    $ ./nodeenv/nodeenv.py --help


.. _pip: http://pypi.python.org/pypi/pip
.. _easy_install: http://pypi.python.org/pypi/setuptools


Зависимости
-----------

Для nodeenv
^^^^^^^^^^^

* make
* tail

Для node.js
^^^^^^^^^^^

* python
* libssl-dev

Использование
-------------

Основы
^^^^^^

Создание нового окружения::

    $ nodeenv env

Активация окружения::

    $ . env/bin/activate

Проверка версий основных пакетов::

    (env) $ node -v
    v0.4.6

    (env) $ npm -v
    0.3.18

Отключение окружения::

    (env) $ deactivate_node

Доп.возможности
^^^^^^^^^^^^^^^

Просмотр списка доступных версий node.js::

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

Установка node.js версии "0.4.3" без поддержки ssl с компиляцией в 4
параллели, а так же npm версией "0.3.17"::

    $ nodeenv --without-ssl --node=0.4.3 --npm=0.3.17 --jobs=4 env-4.3

Сохранение в файл «зависимостей» версий всех установленных пакетов::

    $ . env-4.3/bin/activate
    (env-4.3)$ npm install -g express
    (env-4.3)$ npm install -g jade
    (env-4.3)$ freeze ../prod-requirements.txt

Создание точной копии окружения из файла «зависимостей»::

    $ nodeenv --requirement=../prod-requirements.txt --jobs=4 env-copy

Файл «зависимостей» или «требований» — это простой файл, в котором перечислены
пакеты, которые необходимо установить. Такой файл дает возможность полностью
повторяемые установки. Пример содержания файла::

    $ cat ../prod-requirements.txt
    connect@1.3.0
    express@2.2.2
    jade@0.10.4
    mime@1.2.1
    npm@0.3.17
    qs@0.0.7

Если вы используете оригинальную версию утилиты virtualenv (для python'а), то 
возможно вы захотите использовать nodeenv и virtualenv вместе. В этом случае,
сперва вы должны создать (или активировать) виртуальное окружение для
python'а::

    # если вы используете утилиту virtualenv_wrapper
    $ mkvirtualenv my_env

и затем добавить node.js в это окружение::

    $ nodeenv -p

Теперь все модули node.js будут устанавливаться в созданное виртуальное
окружение::

    $ workon my_env
    $ npm install -g coffee-script
    $ command -v coffee
    /home/monty/virtualenvs/my_env/bin/coffee


Альтернативы
------------

Существует несколько альтернативных утилит, которые так же позволяют создавать
изолированные окружения:

* `nave <https://github.com/isaacs/nave>`_ - Virtual Environments for Node.
  Сохраняет все окружения в одной директории ``~/.nave``. Таким образом, не
  позволяет создавать несколько окружений для одной и той же версии node.js.
  Не позволяет передавать аргументы в конфигурацию (например, --without-ssl)
* `nvm <https://github.com/creationix/nvm/blob/master/nvm.sh>`_ - Node Version
  Manager. Требует регулярно выполнять ``nvm sync`` для кэширования доступных
  версий node.js
  Не позволяет передавать аргументы в конфигурацию (например, --without-ssl)
* `virtualenv`_ Virtual Python Environment builder. Только для python.

.. _`virtualenv`: https://github.com/pypa/virtualenv
