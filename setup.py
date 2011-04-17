"""
    nodeenv
    ~~~~~~~
    Node.js virtual environment
"""

from setuptools import setup
from nodeenv import nodeenv_version

setup(
    name='nodeenv',
    version=nodeenv_version,
    url='https://github.com/ekalinin/nodeenv',
    license='BSD',
    author='Eugene Kalinin',
    author_email='e.v.kalinin@gmail.com',
    description="Node.js virtual environment builder",
    long_description=__doc__,
    py_modules=['nodeenv'],
    entry_points={
        'console_scripts': ['nodeenv = nodeenv:main']
    },
    zip_safe=False,
    platforms='any',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)
