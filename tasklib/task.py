import copy
import datetime
import json
import logging
import os
import subprocess

DATE_FORMAT = '%Y%m%dT%H%M%SZ'
REPR_OUTPUT_SIZE = 10
PENDING = 'pending'
COMPLETED = 'completed'

logger = logging.getLogger(__name__)


class TaskWarriorException(Exception):
    pass


class TaskResource(object):
    read_only_fields = []

    def _load_data(self, data):
        self._data = data

    def __getitem__(self, key):
        hydrate_func = getattr(self, 'deserialize_{0}'.format(key),
                               lambda x: x)
        return hydrate_func(self._data.get(key))

    def __setitem__(self, key, value):
        if key in self.read_only_fields:
            raise RuntimeError('Field \'%s\' is read-only' % key)
        dehydrate_func = getattr(self, 'serialize_{0}'.format(key),
                                 lambda x: x)
        self._data[key] = dehydrate_func(value)
        self._modified_fields.add(key)

    def __repr__(self):
        return self.__unicode__()


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
    read_only_fields = ['id', 'entry', 'urgency']

    class DoesNotExist(Exception):
        pass

    def __init__(self, warrior, data={}):
        self.warrior = warrior
        self._load_data(data)
        self._modified_fields = set()

    def __unicode__(self):
        return self['description']

    def serialize_due(self, date):
        return date.strftime(DATE_FORMAT)

    def deserialize_due(self, date_str):
        if not date_str:
            return None
        return datetime.datetime.strptime(date_str, DATE_FORMAT)

    def deserialize_annotations(self, data):
        return [TaskAnnotation(self, d) for d in data] if data else []

    def deserialize_tags(self, tags):
        if isinstance(tags, basestring):
            return tags.split(',') if tags else []
        return tags

    def serialize_tags(self, tags):
        return ','.join(tags) if tags else ''

    def delete(self):
        self.warrior.execute_command([self['id'], 'delete'], config_override={
            'confirmation': 'no',
        })

    def done(self):
        self.warrior.execute_command([self['id'], 'done'])

    def save(self):
        args = [self['id'], 'modify'] if self['id'] else ['add']
        args.extend(self._get_modified_fields_as_args())
        self.warrior.execute_command(args)
        self._modified_fields.clear()

    def add_annotation(self, annotation):
        args = [self['id'], 'annotate', annotation]
        self.warrior.execute_command(args)
        self.refresh(only_fields=['annotations'])

    def remove_annotation(self, annotation):
        if isinstance(annotation, TaskAnnotation):
            annotation = annotation['description']
        args = [self['id'], 'denotate', annotation]
        self.warrior.execute_command(args)
        self.refresh(only_fields=['annotations'])

    def _get_modified_fields_as_args(self):
        args = []
        for field in self._modified_fields:
            args.append('{}:{}'.format(field, self._data[field]))
        return args

    def refresh(self, only_fields=[]):
        args = [self['uuid'], 'export']
        new_data = json.loads(self.warrior.execute_command(args)[0])
        if only_fields:
            to_update = dict(
                [(k, new_data.get(k)) for k in only_fields])
            self._data.update(to_update)
        else:
            self._data = new_data


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

    def _get_command_args(self, args, config_override={}):
        command_args = ['task', 'rc:/']
        config = self.config.copy()
        config.update(config_override)
        for item in config.items():
            command_args.append('rc.{0}={1}'.format(*item))
        command_args.extend(map(str, args))
        return command_args

    def execute_command(self, args, config_override={}):
        command_args = self._get_command_args(
            args, config_override=config_override)
        logger.debug(' '.join(command_args))
        p = subprocess.Popen(command_args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        stdout, stderr = [x.decode() for x in p.communicate()]
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
