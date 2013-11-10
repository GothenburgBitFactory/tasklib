tasklib
=======

.. image:: https://travis-ci.org/robgolding63/tasklib.png
    :target: http://travis-ci.org/robgolding63/tasklib

A Python library for interacting with taskwarrior_ databases, using a queryset
API similar to that of Django's ORM.

Supports Python 2.6, 2.7, 3.2 and 3.3 with taskwarrior 2.2.0. Older versions of
taskwarrior are untested and probably won't work.

Requirements
------------

* taskwarrior_ v2.2.0

Installation
------------

Install via pip::

    pip install tasklib

Usage
-----

.. source-code:

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

Filtering Tasks
---------------

Tasks can be filtered using the ``TaskQuerySet`` API which emulates the
Django ORM::

    >>> tw.tasks.filter(status='pending', tags__contain='work')
    ['Upgrade Ubuntu Server']

Filter arguments are passed to the ``task`` command (``__`` is replaced by
a period); so the above example is equivalent to the following command::

    $ task status:pending tags.contain=work

.. _taskwarrior: http://taskwarrior.org

Tasks can also be filtered using raw commands, like so::

    >>> tw.tasks.filter('status:pending +work')
    ['Upgrade Ubuntu Server']
