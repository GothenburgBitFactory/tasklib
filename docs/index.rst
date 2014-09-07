Welcome to tasklib's documentation!
===================================

tasklib is a Python library for interacting with taskwarrior_ databases, using
a queryset API similar to that of Django's ORM.

Supports Python 2.6, 2.7, 3.2, 3.3 and 3.4 with taskwarrior 2.1.x and 2.2.x.
Older versions of taskwarrior are untested and may not work.

Requirements
------------

* taskwarrior_ v2.1.x or v2.2.x

Installation
------------

Install via pip (recommended)::

    pip install tasklib

Or clone from github::

    git clone https://github.com/robgolding63/tasklib.git
    cd tasklib
    python setup.py install

Initialization
--------------

Optionally initialize the ``TaskWarrior`` instance with ``data_location`` (the
database directory). If it doesn't already exist, this will be created
automatically unless ``create=False``.

The default location is the same as taskwarrior's::

    >>> tw = TaskWarrior(data_location='~/.task', create=True)

Retrieving Tasks
----------------

``tw.tasks`` is a ``TaskQuerySet`` object which emulates the Django QuerySet
API. To get all tasks (including completed ones)::

    >>> tw.tasks.all()

Filtering
---------

Filter tasks using the same familiar syntax::

    >>> tw.tasks.filter(status='pending', tags__contain='work')
    ['Upgrade Ubuntu Server']

Filter arguments are passed to the ``task`` command (``__`` is replaced by
a period) so the above example is equivalent to the following command::

    $ task status:pending tags.contain=work

Tasks can also be filtered using raw commands, like so::

    >>> tw.tasks.filter('status:pending +work')
    ['Upgrade Ubuntu Server']

There are built-in functions for retrieving pending & completed tasks::

    >>> tw.tasks.pending().filter(tags__contain='work')
    ['Upgrade Ubuntu Server']
    >>> len(tw.tasks.completed())
    227

Use ``get()`` to return the only task in a ``TaskQuerySet``, or raise an
exception::

    >>> tw.tasks.filter(status='pending', tags__contain='work').get()
    'Upgrade Ubuntu Server'
    >>> tw.tasks.filter(status='pending', tags__contain='work').get(status='completed')
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "tasklib/task.py", line 224, in get
        'Lookup parameters were {0}'.format(kwargs))
    tasklib.task.DoesNotExist: Task matching query does not exist. Lookup parameters were {'status': 'completed'}
    >>> tw.tasks.filter(status='pending', tags__contain='home').get()
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "tasklib/task.py", line 227, in get
        'Lookup parameters were {1}'.format(num, kwargs))
    ValueError: get() returned more than one Task -- it returned 2! Lookup parameters were {}

Task Attributes
---------------

Attributes of task objects are accessible through indices, like so::

    >>> task = tw.tasks.pending().filter(tags__contain='work').get()
    >>> task['description']
    'Upgrade Ubuntu Server'
    >>> task['id']
    15
    >>> task['due']
    datetime.datetime(2013, 12, 5, 0, 0)
    >>> task['tags']
    ['work', 'servers']

The following fields are deserialized into Python objects:

* ``due``: deserialized to a ``datetime`` object
* ``annotations``: deserialized to a list of dictionaries, where the ``entry``
  field is a ``datetime`` object
* ``tags``: deserialized to a list

Attributes should be set using the correct Python representation, which will be
serialized into the correct format when the task is saved.

Saving Tasks
------------

After modifying one or more attributes, simple call ``save()`` to write those
changes to the database::

    >>> task = tw.tasks.pending().filter(tags__contain='work').get()
    >>> task['due'] = datetime(year=2014, month=1, day=5)
    >>> task.save()

To mark a task as complete, use ``done()``::

    >>> task = tw.tasks.pending().filter(tags__contain='work').get()
    >>> task.done()
    >>> len(tw.tasks.pending().filter(tags__contain='work'))
    0

.. _taskwarrior: http://taskwarrior.org
