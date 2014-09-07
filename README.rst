tasklib
=======

.. image:: https://travis-ci.org/robgolding63/tasklib.png
    :target: http://travis-ci.org/robgolding63/tasklib

tasklib is a Python library for interacting with taskwarrior_ databases, using
a queryset API similar to that of Django's ORM.

Supports Python 2.6, 2.7, 3.2, 3.3 and 3.4 with taskwarrior 2.1.x and 2.2.x.
Older versions of taskwarrior are untested and may not work.

Requirements
------------

* taskwarrior_ v2.1.x or v2.2.x

Installation
------------

Install via pip::

    pip install tasklib

Usage
-----

tasklib has a similar API to that of Django's ORM::

    >>> from tasklib.task import TaskWarrior

    >>> tw = TaskWarrior('/home/rob/.task')
    >>> tasks = tw.tasks.pending()
    >>> tasks
    ['Tidy the house', 'Learn German']
    >>> tasks.filter(tags__contain='chores')
    ['Tidy the house']
    >>> type(tasks[0])
    <class 'tasklib.task.Task'>
    >>> task[0].done()
    >>> tasks = tw.tasks.pending()
    >>> tasks
    ['Learn German']
    >>> tasks[0]['tags'] = ['languages']
    >>> tasks[0].save()

For more advanced usage, see the documentation_.

.. _taskwarrior: http://taskwarrior.org
.. _documentation: http://tasklib.readthedocs.org/en/latest/
