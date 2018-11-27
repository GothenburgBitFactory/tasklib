tasklib
=======

.. image:: https://travis-ci.org/robgolding63/tasklib.png?branch=develop
    :target: http://travis-ci.org/robgolding63/tasklib

.. image:: https://coveralls.io/repos/robgolding63/tasklib/badge.png?branch=develop
    :target: https://coveralls.io/r/robgolding63/tasklib?branch=develop

tasklib is a Python library for interacting with taskwarrior_ databases, using
a queryset API similar to that of Django's ORM.

Supports Python 2.6, 2.7, 3.2, 3.3 and 3.4 with taskwarrior 2.1.x and above.
Older versions of taskwarrior are untested and may not work.

Requirements
------------

* taskwarrior_ v2.1.x or above.

Installation
------------

Install via pip::

    pip install tasklib

Usage
-----

tasklib has a similar API to that of Django's ORM::

    >>> from tasklib import TaskWarrior

    >>> tw = TaskWarrior('/home/rob/.task')
    >>> tasks = tw.tasks.pending()
    >>> tasks
    ['Tidy the house', 'Learn German']
    >>> tasks.filter(tags__contain='chores')
    ['Tidy the house']
    >>> type(tasks[0])
    <class 'tasklib.task.Task'>
    >>> tasks[0].done()
    >>> tasks = tw.tasks.pending()
    >>> tasks
    ['Learn German']
    >>> tasks[0]['tags'] = ['languages']
    >>> tasks[0].save()

For more advanced usage, see the documentation_.

.. _taskwarrior: http://taskwarrior.org
.. _documentation: http://tasklib.readthedocs.org/en/latest/
