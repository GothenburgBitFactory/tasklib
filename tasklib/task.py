from __future__ import print_function
import copy
import importlib
import json
import logging
import os
import six
import sys

from .serializing import SerializingObject

DATE_FORMAT = '%Y%m%dT%H%M%SZ'
REPR_OUTPUT_SIZE = 10
PENDING = 'pending'
COMPLETED = 'completed'
DELETED = 'deleted'
WAITING = 'waiting'
RECURRING = 'recurring'

logger = logging.getLogger(__name__)


class ReadOnlyDictView(object):
    """
    Provides simplified read-only view upon dict object.
    """

    def __init__(self, viewed_dict):
        self.viewed_dict = viewed_dict

    def __getitem__(self, key):
        return copy.deepcopy(self.viewed_dict.__getitem__(key))

    def __contains__(self, k):
        return self.viewed_dict.__contains__(k)

    def __iter__(self):
        for value in self.viewed_dict:
            yield copy.deepcopy(value)

    def __len__(self):
        return len(self.viewed_dict)

    def __unicode__(self):
        return six.u('ReadOnlyDictView: {0}'.format(repr(self.viewed_dict)))

    __repr__ = __unicode__

    def get(self, key, default=None):
        return copy.deepcopy(self.viewed_dict.get(key, default))

    def items(self):
        return [copy.deepcopy(v) for v in self.viewed_dict.items()]

    def values(self):
        return [copy.deepcopy(v) for v in self.viewed_dict.values()]


class TaskResource(SerializingObject):
    read_only_fields = []

    def _load_data(self, data):
        self._data = dict((key, self._deserialize(key, value))
                          for key, value in data.items())
        # We need to use a copy for original data, so that changes
        # are not propagated.
        self._original_data = copy.deepcopy(self._data)

    def _update_data(self, data, update_original=False, remove_missing=False):
        """
        Low level update of the internal _data dict. Data which are coming as
        updates should already be serialized. If update_original is True, the
        original_data dict is updated as well.
        """
        self._data.update(dict((key, self._deserialize(key, value))
                               for key, value in data.items()))

        # In certain situations, we want to treat missing keys as removals
        if remove_missing:
            for key in set(self._data.keys()) - set(data.keys()):
                self._data[key] = None

        if update_original:
            self._original_data = copy.deepcopy(self._data)

    def __getitem__(self, key):
        # This is a workaround to make TaskResource non-iterable
        # over simple index-based iteration
        try:
            int(key)
            raise StopIteration
        except ValueError:
            pass

        if key not in self._data:
            self._data[key] = self._deserialize(key, None)

        return self._data.get(key)

    def __setitem__(self, key, value):
        if key in self.read_only_fields:
            raise RuntimeError('Field \'%s\' is read-only' % key)

        # Normalize the user input before saving it
        value = self._normalize(key, value)
        self._data[key] = value

    def __str__(self):
        s = six.text_type(self.__unicode__())
        if not six.PY3:
            s = s.encode('utf-8')
        return s

    def __repr__(self):
        return str(self)

    def export_data(self):
        """
        Exports current data contained in the Task as JSON
        """

        # We need to remove spaces for TW-1504, use custom separators
        data_tuples = ((key, self._serialize(key, value))
                       for key, value in six.iteritems(self._data))

        # Empty string denotes empty serialized value, we do not want
        # to pass that to TaskWarrior.
        data_tuples = filter(lambda t: t[1] is not '', data_tuples)
        data = dict(data_tuples)
        return json.dumps(data, separators=(',', ':'))

    @property
    def _modified_fields(self):
        writable_fields = set(self._data.keys()) - set(self.read_only_fields)
        for key in writable_fields:
            new_value = self._data.get(key)
            old_value = self._original_data.get(key)

            # Make sure not to mark data removal as modified field if the
            # field originally had some empty value
            if key in self._data and not new_value and not old_value:
                continue

            if new_value != old_value:
                yield key

    @property
    def modified(self):
        return bool(list(self._modified_fields))


class TaskAnnotation(TaskResource):
    read_only_fields = ['entry', 'description']

    def __init__(self, task, data=None):
        self.task = task
        self._load_data(data or dict())
        super(TaskAnnotation, self).__init__(task.backend)

    def remove(self):
        self.task.remove_annotation(self)

    def __unicode__(self):
        return self['description']

    def __eq__(self, other):
        # consider 2 annotations equal if they belong to the same task, and
        # their data dics are the same
        return self.task == other.task and self._data == other._data

    def __ne__(self, other):
        return not self.__eq__(other)

    __repr__ = __unicode__


class Task(TaskResource):
    read_only_fields = ['id', 'entry', 'urgency', 'uuid', 'modified']

    class DoesNotExist(Exception):
        pass

    class CompletedTask(Exception):
        """
        Raised when the operation cannot be performed on the completed task.
        """
        pass

    class DeletedTask(Exception):
        """
        Raised when the operation cannot be performed on the deleted task.
        """
        pass

    class ActiveTask(Exception):
        """
        Raised when the operation cannot be performed on the active task.
        """
        pass

    class InactiveTask(Exception):
        """
        Raised when the operation cannot be performed on an inactive task.
        """
        pass

    class NotSaved(Exception):
        """
        Raised when the operation cannot be performed on the task, because
        it has not been saved to TaskWarrior yet.
        """
        pass

    @classmethod
    def from_input(cls, input_file=sys.stdin, modify=None, backend=None):
        """
        Creates a Task object, directly from the stdin, by reading one line.
        If modify=True, two lines are used, first line interpreted as the
        original state of the Task object, and second line as its new,
        modified value. This is consistent with the TaskWarrior's hook
        system.

        Object created by this method should not be saved, deleted
        or refreshed, as t could create a infinite loop. For this
        reason, TaskWarrior instance is set to None.

        Input_file argument can be used to specify the input file,
        but defaults to sys.stdin.
        """

        # Detect the hook type if not given directly
        name = os.path.basename(sys.argv[0])
        modify = name.startswith('on-modify') if modify is None else modify

        # Create the TaskWarrior instance if none passed
        if backend is None:
            backends = importlib.import_module('tasklib.backends')
            hook_parent_dir = os.path.dirname(os.path.dirname(sys.argv[0]))
            backend = backends.TaskWarrior(data_location=hook_parent_dir)

        # TaskWarrior instance is set to None
        task = cls(backend)

        # Load the data from the input
        task._load_data(json.loads(input_file.readline().strip()))

        # If this is a on-modify event, we are provided with additional
        # line of input, which provides updated data
        if modify:
            task._update_data(json.loads(input_file.readline().strip()),
                              remove_missing=True)

        return task

    def __init__(self, backend, **kwargs):
        super(Task, self).__init__(backend)

        # Check that user is not able to set read-only value in __init__
        for key in kwargs.keys():
            if key in self.read_only_fields:
                raise RuntimeError('Field \'%s\' is read-only' % key)

        # We serialize the data in kwargs so that users of the library
        # do not have to pass different data formats via __setitem__ and
        # __init__ methods, that would be confusing

        # Rather unfortunate syntax due to python2.6 comaptiblity
        self._data = dict((key, self._normalize(key, value))
                          for (key, value) in six.iteritems(kwargs))
        self._original_data = copy.deepcopy(self._data)

        # Provide read only access to the original data
        self.original = ReadOnlyDictView(self._original_data)

    def __unicode__(self):
        return self['description']

    def __eq__(self, other):
        if self['uuid'] and other['uuid']:
            # For saved Tasks, just define equality by equality of uuids
            return self['uuid'] == other['uuid']
        else:
            # If the tasks are not saved, compare the actual instances
            return id(self) == id(other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        if self['uuid']:
            # For saved Tasks, just define equality by equality of uuids
            return self['uuid'].__hash__()
        else:
            # If the tasks are not saved, return hash of instance id
            return id(self).__hash__()

    @property
    def completed(self):
        return self['status'] == six.text_type('completed')

    @property
    def deleted(self):
        return self['status'] == six.text_type('deleted')

    @property
    def waiting(self):
        return self['status'] == six.text_type('waiting')

    @property
    def pending(self):
        return self['status'] == six.text_type('pending')

    @property
    def recurring(self):
        return self['status'] == six.text_type('recurring')

    @property
    def active(self):
        return self['start'] is not None

    @property
    def saved(self):
        return self['uuid'] is not None or self['id'] is not None

    def serialize_depends(self, cur_dependencies):
        # Check that all the tasks are saved
        for task in (cur_dependencies or set()):
            if not task.saved:
                raise Task.NotSaved(
                    'Task \'%s\' needs to be saved before '
                    'it can be set as dependency.' % task,
                )

        return super(Task, self).serialize_depends(cur_dependencies)

    def delete(self):
        if not self.saved:
            raise Task.NotSaved(
                'Task needs to be saved before it can be deleted',
            )

        # Refresh the status, and raise exception if the task is deleted
        self.refresh(only_fields=['status'])

        if self.deleted:
            raise Task.DeletedTask('Task was already deleted')

        self.backend.delete_task(self)

        # Refresh the status again, so that we have updated info stored
        self.refresh(only_fields=['status', 'start', 'end'])

    def start(self):
        if not self.saved:
            raise Task.NotSaved(
                'Task needs to be saved before it can be started',
            )

        # Refresh, and raise exception if task is already completed/deleted
        self.refresh(only_fields=['status'])

        if self.completed:
            raise Task.CompletedTask('Cannot start a completed task')
        elif self.deleted:
            raise Task.DeletedTask('Deleted task cannot be started')
        elif self.active:
            raise Task.ActiveTask('Task is already active')

        self.backend.start_task(self)

        # Refresh the status again, so that we have updated info stored
        self.refresh(only_fields=['status', 'start'])

    def stop(self):
        if not self.saved:
            raise Task.NotSaved(
                'Task needs to be saved before it can be stopped',
            )

        # Refresh, and raise exception if task is already completed/deleted
        self.refresh(only_fields=['status'])

        if not self.active:
            raise Task.InactiveTask('Cannot stop an inactive task')

        self.backend.stop_task(self)

        # Refresh the status again, so that we have updated info stored
        self.refresh(only_fields=['status', 'start'])

    def done(self):
        if not self.saved:
            raise Task.NotSaved(
                'Task needs to be saved before it can be completed',
            )

        # Refresh, and raise exception if task is already completed/deleted
        self.refresh(only_fields=['status'])

        if self.completed:
            raise Task.CompletedTask('Cannot complete a completed task')
        elif self.deleted:
            raise Task.DeletedTask('Deleted task cannot be completed')

        self.backend.complete_task(self)

        # Refresh the status again, so that we have updated info stored
        self.refresh(only_fields=['status', 'start', 'end'])

    def save(self):
        if self.saved and not self.modified:
            return

        # All the actual work is done by the backend
        self.backend.save_task(self)

    def add_annotation(self, annotation):
        if not self.saved:
            raise Task.NotSaved('Task needs to be saved to add annotation')

        self.backend.annotate_task(self, annotation)
        self.refresh(only_fields=['annotations'])

    def remove_annotation(self, annotation):
        if not self.saved:
            raise Task.NotSaved('Task needs to be saved to remove annotation')

        if isinstance(annotation, TaskAnnotation):
            annotation = annotation['description']

        self.backend.denotate_task(self, annotation)
        self.refresh(only_fields=['annotations'])

    def refresh(self, only_fields=None, after_save=False):
        # Raise error when trying to refresh a task that has not been saved
        if not self.saved:
            raise Task.NotSaved('Task needs to be saved to be refreshed')

        new_data = self.backend.refresh_task(self, after_save=after_save)

        if only_fields:
            to_update = dict(
                [(k, new_data.get(k)) for k in only_fields],
            )
            self._update_data(to_update, update_original=True)
        else:
            self._load_data(new_data)


class TaskQuerySet(object):
    """
    Represents a lazy lookup for a task objects.
    """

    def __init__(self, backend, filter_obj=None):
        self.backend = backend
        self._result_cache = None
        self.filter_obj = filter_obj or self.backend.filter_class(backend)

    def __deepcopy__(self, memo):
        """
        Deep copy of a QuerySet doesn't populate the cache
        """
        obj = self.__class__(backend=self.backend)
        for k, v in self.__dict__.items():
            if k in ('_iter', '_result_cache'):
                obj.__dict__[k] = None
            else:
                obj.__dict__[k] = copy.deepcopy(v, memo)
        return obj

    def __repr__(self):
        data = list(self[:REPR_OUTPUT_SIZE + 1])
        if len(data) > REPR_OUTPUT_SIZE:
            data[-1] = '...(remaining elements truncated)...'
        return repr(data)

    def __len__(self):
        if self._result_cache is None:
            self._result_cache = list(self)
        return len(self._result_cache)

    def __iter__(self):
        if self._result_cache is None:
            self._result_cache = self._execute()
        return iter(self._result_cache)

    def __getitem__(self, k):
        if self._result_cache is None:
            self._result_cache = list(self)
        return self._result_cache.__getitem__(k)

    def __bool__(self):
        if self._result_cache is not None:
            return bool(self._result_cache)
        try:
            next(iter(self))
        except StopIteration:
            return False
        return True

    def __nonzero__(self):
        return type(self).__bool__(self)

    def _clone(self, klass=None, **kwargs):
        if klass is None:
            klass = self.__class__
        filter_obj = self.filter_obj.clone()
        c = klass(backend=self.backend, filter_obj=filter_obj)
        c.__dict__.update(kwargs)
        return c

    def _execute(self):
        """
        Fetch the tasks which match the current filters.
        """
        return self.backend.filter_tasks(self.filter_obj)

    def all(self):
        """
        Returns a new TaskQuerySet that is a copy of the current one.
        """
        return self._clone()

    def pending(self):
        return self.filter(status=PENDING)

    def completed(self):
        return self.filter(status=COMPLETED)

    def deleted(self):
        return self.filter(status=DELETED)

    def waiting(self):
        return self.filter(status=WAITING)

    def recurring(self):
        return self.filter(status=RECURRING)

    def filter(self, *args, **kwargs):
        """
        Returns a new TaskQuerySet with the given filters added.
        """
        clone = self._clone()
        for f in args:
            clone.filter_obj.add_filter(f)
        for key, value in kwargs.items():
            clone.filter_obj.add_filter_param(key, value)
        return clone

    def get(self, **kwargs):
        """
        Performs the query and returns a single object matching the given
        keyword arguments.
        """
        clone = self.filter(**kwargs)
        num = len(clone)
        if num == 1:
            return clone._result_cache[0]
        if not num:
            raise Task.DoesNotExist(
                'Task matching query does not exist. '
                'Lookup parameters were {0}'.format(kwargs),
            )
        raise ValueError(
            'get() returned more than one Task -- it returned {0}! '
            'Lookup parameters were {1}'.format(num, kwargs),
        )
