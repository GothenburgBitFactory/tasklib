tasklib
=======

A Python library for interacting with taskwarrior_ databases.

Requirements
------------

Before installing ``tasklib``, you'll need to install taskwarrior_.

Installation
------------

Install via pip::

    pip install tasklib

Usage
-----

.. source-code:

    >>> from tasklib.task import TaskWarrior, PENDING

    >>> tw = TaskWarrior('/home/rob/.task')
    >>> tasks = tw.get_tasks(status=PENDING)
    >>> tasks
    ['Tidy the house', 'Learn German']
    >>> type(tasks[0])
    <class 'tasklib.task.Task'>
    >>> task[0].done()


.. _taskwarrior: http://taskwarrior.org
