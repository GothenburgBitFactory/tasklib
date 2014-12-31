from __future__ import print_function
import copy
import datetime
import json
import logging
import os
import six
import subprocess

DATE_FORMAT = '%Y%m%dT%H%M%SZ'
REPR_OUTPUT_SIZE = 10
PENDING = 'pending'
COMPLETED = 'completed'

VERSION_2_1_0 = six.u('2.1.0')
VERSION_2_2_0 = six.u('2.2.0')
VERSION_2_3_0 = six.u('2.3.0')
VERSION_2_4_0 = six.u('2.4.0')

logger = logging.getLogger(__name__)


class TaskWarriorException(Exception):
    pass


class TaskResource(object):
    read_only_fields = []

    def _load_data(self, data):
        self._data = data
        # We need to use a copy for original data, so that changes
        # are not propagated
        self._original_data = data.copy()

    def __getitem__(self, key):
        # This is a workaround to make TaskResource non-iterable
        # over simple index-based iteration
        try:
            int(key)
            raise StopIteration
        except ValueError:
            pass

        hydrate_func = getattr(self, 'deserialize_{0}'.format(key),
                               lambda x: x)
        return hydrate_func(self._data.get(key))

    def __setitem__(self, key, value):
        if key in self.read_only_fields:
            raise RuntimeError('Field \'%s\' is read-only' % key)
        dehydrate_func = getattr(self, 'serialize_{0}'.format(key),
                                 lambda x: x)
        self._data[key] = dehydrate_func(value)

    def __str__(self):
        s = six.text_type(self.__unicode__())
        if not six.PY3:
            s = s.encode('utf-8')
        return s

    def __repr__(self):
        return str(self)


class TaskAnnotation(TaskResource):
    read_only_fields = ['entry', 'description']

    def __init__(self, task, data={}):
        self.task = task
        self._load_data(data)

    def deserialize_entry(self, data):
        return datetime.datetime.strptime(data, DATE_FORMAT) if data else None

    def serialize_entry(self, date):
        return date.strftime(DATE_FORMAT) if date else ''

    def remove(self):
        self.task.remove_annotation(self)

    def __unicode__(self):
        return self['description']

    __repr__ = __unicode__


class Task(TaskResource):
    read_only_fields = ['id', 'entry', 'urgency', 'uuid']

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

    class NotSaved(Exception):
        """
        Raised when the operation cannot be performed on the task, because
        it has not been saved to TaskWarrior yet.
        """
        pass

    def __init__(self, warrior, data={}, **kwargs):
        self.warrior = warrior

        # We keep data for backwards compatibility
        kwargs.update(data)

        self._load_data(kwargs)

    def __unicode__(self):
        return self['description']

    def __eq__(self, other):
        if self['uuid'] and other['uuid']:
            # For saved Tasks, just define equality by equality of uuids
            return self['uuid'] == other['uuid']
        else:
            # If the tasks are not saved, compare the actual instances
            return id(self) == id(other)


    def __hash__(self):
        if self['uuid']:
            # For saved Tasks, just define equality by equality of uuids
            return self['uuid'].__hash__()
        else:
            # If the tasks are not saved, return hash of instance id
            return id(self).__hash__()

    @property
    def _modified_fields(self):
        for key in self._data.keys():
            if self._data.get(key) != self._original_data.get(key):
                yield key

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
    def saved(self):
        return self['uuid'] is not None or self['id'] is not None

    def serialize_due(self, date):
        return date.strftime(DATE_FORMAT)

    def deserialize_due(self, date_str):
        if not date_str:
            return None
        return datetime.datetime.strptime(date_str, DATE_FORMAT)

    def serialize_depends(self, cur_dependencies):
        # Check that all the tasks are saved
        for task in cur_dependencies:
            if not task.saved:
                raise Task.NotSaved('Task \'%s\' needs to be saved before '
                                    'it can be set as dependency.' % task)

        # Return the list of uuids
        return ','.join(task['uuid'] for task in cur_dependencies)

    def deserialize_depends(self, raw_uuids):
        raw_uuids = raw_uuids or ''  # Convert None to empty string
        uuids = raw_uuids.split(',')
        return set(self.warrior.tasks.get(uuid=uuid) for uuid in uuids if uuid)

    def format_depends(self):
        # We need to generate added and removed dependencies list,
        # since Taskwarrior does not accept redefining dependencies.

        # This cannot be part of serialize_depends, since we need
        # to keep a list of all depedencies in the _data dictionary,
        # not just currently added/removed ones

        old_dependencies_raw = self._original_data.get('depends','')
        old_dependencies = self.deserialize_depends(old_dependencies_raw)

        added = self['depends'] - old_dependencies
        removed = old_dependencies - self['depends']

        # Removed dependencies need to be prefixed with '-'
        return ','.join(
                [t['uuid'] for t in added] +
                ['-' + t['uuid'] for t in removed]
            )

    def deserialize_annotations(self, data):
        return [TaskAnnotation(self, d) for d in data] if data else []

    def deserialize_tags(self, tags):
        if isinstance(tags, basestring):
            return tags.split(',') if tags else []
        return tags

    def serialize_tags(self, tags):
        return ','.join(tags) if tags else ''

    def delete(self):
        if not self.saved:
            raise Task.NotSaved("Task needs to be saved before it can be deleted")

        # Refresh the status, and raise exception if the task is deleted
        self.refresh(only_fields=['status'])

        if self.deleted:
            raise Task.DeletedTask("Task was already deleted")

        self.warrior.execute_command([self['uuid'], 'delete'], config_override={
            'confirmation': 'no',
        })

        # Refresh the status again, so that we have updated info stored
        self.refresh(only_fields=['status'])


    def done(self):
        if not self.saved:
            raise Task.NotSaved("Task needs to be saved before it can be completed")

        # Refresh, and raise exception if task is already completed/deleted
        self.refresh(only_fields=['status'])

        if self.completed:
            raise Task.CompletedTask("Cannot complete a completed task")
        elif self.deleted:
            raise Task.DeletedTask("Deleted task cannot be completed")

        self.warrior.execute_command([self['uuid'], 'done'])

        # Refresh the status again, so that we have updated info stored
        self.refresh(only_fields=['status'])

    def save(self):
        args = [self['uuid'], 'modify'] if self.saved else ['add']
        args.extend(self._get_modified_fields_as_args())
        output = self.warrior.execute_command(args)

        # Parse out the new ID, if the task is being added for the first time
        if not self.saved:
            id_lines = [l for l in output if l.startswith('Created task ')]

            # Complain loudly if it seems that more tasks were created
            # Should not happen
            if len(id_lines) != 1 or len(id_lines[0].split(' ')) != 3:
                raise TaskWarriorException("Unexpected output when creating "
                                           "task: %s" % '\n'.join(id_lines))

            # Circumvent the ID storage, since ID is considered read-only
            self._data['id'] = int(id_lines[0].split(' ')[2].rstrip('.'))

        self.refresh()

    def add_annotation(self, annotation):
        if not self.saved:
            raise Task.NotSaved("Task needs to be saved to add annotation")

        args = [self['uuid'], 'annotate', annotation]
        self.warrior.execute_command(args)
        self.refresh(only_fields=['annotations'])

    def remove_annotation(self, annotation):
        if not self.saved:
            raise Task.NotSaved("Task needs to be saved to add annotation")

        if isinstance(annotation, TaskAnnotation):
            annotation = annotation['description']
        args = [self['uuid'], 'denotate', annotation]
        self.warrior.execute_command(args)
        self.refresh(only_fields=['annotations'])

    def _get_modified_fields_as_args(self):
        args = []

        def add_field(field):
            # Task version older than 2.4.0 ignores first word of the
            # task description if description: prefix is used
            if self.warrior.version < VERSION_2_4_0 and field == 'description':
                args.append(self._data[field])
            elif field == 'depends':
                args.append('{0}:{1}'.format(field, self.format_depends()))
            else:
                # Use empty string to substitute for None value
                args.append('{0}:{1}'.format(field, self._data[field] or ''))

        # If we're modifying saved task, simply pass on all modified fields
        if self.saved:
            for field in self._modified_fields:
                add_field(field)
        # For new tasks, pass all fields that make sense
        else:
            for field in self._data.keys():
                if field in self.read_only_fields:
                    continue
                add_field(field)

        return args

    def refresh(self, only_fields=[]):
        # Raise error when trying to refresh a task that has not been saved
        if not self.saved:
            raise Task.NotSaved("Task needs to be saved to be refreshed")

        # We need to use ID as backup for uuid here for the refreshes
        # of newly saved tasks. Any other place in the code is fine
        # with using UUID only.
        args = [self['uuid'] or self['id'], 'export']
        new_data = json.loads(self.warrior.execute_command(args)[0])
        if only_fields:
            to_update = dict(
                [(k, new_data.get(k)) for k in only_fields])
            self._data.update(to_update)
            self._original_data.update(to_update)
        else:
            self._data = new_data
            # We need to create a clone for original_data though
            # Shallow copy is alright, since data dict uses only
            # primitive data types
            self._original_data = new_data.copy()


class TaskFilter(object):
    """
    A set of parameters to filter the task list with.
    """

    def __init__(self, filter_params=[]):
        self.filter_params = filter_params

    def add_filter(self, filter_str):
        self.filter_params.append(filter_str)

    def add_filter_param(self, key, value):
        key = key.replace('__', '.')

        # Replace the value with empty string, since that is the
        # convention in TW for empty values
        value = value if value is not None else ''

        # If we are filtering by uuid:, do not use uuid keyword
        # due to TW-1452 bug
        if key == 'uuid':
            self.filter_params.insert(0, value)
        else:
            self.filter_params.append('{0}:{1}'.format(key, value))

    def get_filter_params(self):
        return [f for f in self.filter_params if f]

    def clone(self):
        c = self.__class__()
        c.filter_params = list(self.filter_params)
        return c


class TaskQuerySet(object):
    """
    Represents a lazy lookup for a task objects.
    """

    def __init__(self, warrior=None, filter_obj=None):
        self.warrior = warrior
        self._result_cache = None
        self.filter_obj = filter_obj or TaskFilter()

    def __deepcopy__(self, memo):
        """
        Deep copy of a QuerySet doesn't populate the cache
        """
        obj = self.__class__()
        for k, v in self.__dict__.items():
            if k in ('_iter', '_result_cache'):
                obj.__dict__[k] = None
            else:
                obj.__dict__[k] = copy.deepcopy(v, memo)
        return obj

    def __repr__(self):
        data = list(self[:REPR_OUTPUT_SIZE + 1])
        if len(data) > REPR_OUTPUT_SIZE:
            data[-1] = "...(remaining elements truncated)..."
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
        c = klass(warrior=self.warrior, filter_obj=filter_obj)
        c.__dict__.update(kwargs)
        return c

    def _execute(self):
        """
        Fetch the tasks which match the current filters.
        """
        return self.warrior.filter_tasks(self.filter_obj)

    def all(self):
        """
        Returns a new TaskQuerySet that is a copy of the current one.
        """
        return self._clone()

    def pending(self):
        return self.filter(status=PENDING)

    def completed(self):
        return self.filter(status=COMPLETED)

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
                'Lookup parameters were {0}'.format(kwargs))
        raise ValueError(
            'get() returned more than one Task -- it returned {0}! '
            'Lookup parameters were {1}'.format(num, kwargs))


class TaskWarrior(object):
    def __init__(self, data_location='~/.task', create=True):
        data_location = os.path.expanduser(data_location)
        if create and not os.path.exists(data_location):
            os.makedirs(data_location)
        self.config = {
            'data.location': os.path.expanduser(data_location),
        }
        self.tasks = TaskQuerySet(self)
        self.version = self._get_version()

    def _get_command_args(self, args, config_override={}):
        command_args = ['task', 'rc:/']
        config = self.config.copy()
        config.update(config_override)
        for item in config.items():
            command_args.append('rc.{0}={1}'.format(*item))
        command_args.extend(map(str, args))
        return command_args

    def _get_version(self):
        p = subprocess.Popen(
                ['task', '--version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        stdout, stderr = [x.decode('utf-8') for x in p.communicate()]
        return stdout.strip('\n')

    def execute_command(self, args, config_override={}):
        command_args = self._get_command_args(
            args, config_override=config_override)
        logger.debug(' '.join(command_args))
        p = subprocess.Popen(command_args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        stdout, stderr = [x.decode('utf-8') for x in p.communicate()]
        if p.returncode:
            if stderr.strip():
                error_msg = stderr.strip().splitlines()[-1]
            else:
                error_msg = stdout.strip()
            raise TaskWarriorException(error_msg)
        return stdout.strip().split('\n')

    def filter_tasks(self, filter_obj):
        args = ['export', '--'] + filter_obj.get_filter_params()
        tasks = []
        for line in self.execute_command(args):
            if line:
                data = line.strip(',')
                try:
                    tasks.append(Task(self, json.loads(data)))
                except ValueError:
                    raise TaskWarriorException('Invalid JSON: %s' % data)
        return tasks

    def merge_with(self, path, push=False):
        path = path.rstrip('/') + '/'
        self.execute_command(['merge', path], config_override={
            'merge.autopush': 'yes' if push else 'no',
        })

    def undo(self):
        self.execute_command(['undo'], config_override={
            'confirmation': 'no',
        })
