# -*- coding: utf-8 -*-
"""
nodeenv
~~~~~~~

Node.js Virtual Environment builder.
"""
import codecs
import os
import sys

from setuptools import setup

sys.path.insert(0, '.')

from nodeenv import nodeenv_version  # noqa: E402


def read_file(file_name):
    return codecs.open(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            file_name
        ),
        encoding='utf-8',
    ).read()


ldesc = read_file('README.rst')
ldesc += "\n\n" + read_file('CHANGES')

setup(
    name='nodeenv',
    version=nodeenv_version,
    url='https://github.com/ekalinin/nodeenv',
    license='BSD',
    author='Eugene Kalinin',
    author_email='e.v.kalinin@gmail.com',
    install_requires=[],
    extras_require={'certifi': ['certifi']},
    python_requires='>=3.10',
    description="Node.js virtual environment builder",
    long_description=ldesc,
    py_modules=['nodeenv'],
    entry_points={
        'console_scripts': ['nodeenv = nodeenv:main']
    },
    zip_safe=False,
    platforms='any',
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)
