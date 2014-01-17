Welcome to tasklib's documentation!
===================================

tasklib is a Python library for interacting with taskwarrior_ databases, using
a queryset API similar to that of Django's ORM.

Supports Python 2.6, 2.7, 3.2 and 3.3 with taskwarrior 2.2.0 or 2.3.0 beta2.
Older versions of taskwarrior are untested and probably won't work.

Requirements
------------

* taskwarrior_ v2.2.0 or v2.3.0 beta2

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
        clone.filter_obj.get_filter_params()
    tasklib.task.DoesNotExist: Task matching query does not exist.
    Lookup parameters were ['status:pending', 'tags.contain:work', 'status:completed']
    >>> tw.tasks.filter(status='pending', tags__contain='home').get()
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "tasklib/task.py", line 227, in get
        num, clone.filter_obj.get_filter_params()
    ValueError: get() returned more than one Task -- it returned 2!
    Lookup parameters were ['status:pending', 'tags.contain:home']

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
