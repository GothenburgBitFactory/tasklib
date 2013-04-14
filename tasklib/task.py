import copy
import json
import os
import subprocess
import tempfile
import uuid


REPR_OUTPUT_SIZE = 10
PENDING = 'pending'


class TaskWarriorException(Exception):
    pass


class Task(object):

    class DoesNotExist(Exception):
        pass

    def __init__(self, warrior, data={}):
        self.warrior = warrior
        self._data = data

    def __getitem__(self, key):
        return self._data.get(key)

    def __setitem__(self, key, val):
        self._data[key] = val

    def __unicode__(self):
        return self._data.get('description')

    def regenerate_uuid(self):
        self['uuid'] = str(uuid.uuid4())

    def delete(self):
        self.warrior.delete_task(self['uuid'])

    def done(self):
        self.warrior.complete_task(self['uuid'])

    def save(self, delete_first=True):
        if self['uuid'] and delete_first:
            self.delete()
        if not self['uuid'] or delete_first:
            self.regenerate_uuid()
        self.warrior.import_tasks([self._data])

    __repr__ = __unicode__


class TaskFilter(object):
    """
    A set of parameters to filter the task list with.
    """

    def __init__(self, filter_params=()):
        self.filter_params = filter_params

    def add_filter(self, param, value):
        self.filter_params += ((param, value),)

    def get_filter_params(self):
        return self.filter_params

    def clone(self):
        c = self.__class__()
        c.filter_params = tuple(self.filter_params)
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
        for k,v in self.__dict__.items():
            if k in ('_iter','_result_cache'):
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
        return self.warrior._execute_filter(self.filter_obj)

    def all(self):
        """
        Returns a new TaskQuerySet that is a copy of the current one.
        """
        return self._clone()

    def pending(self):
        return self.filter(status=PENDING)

    def filter(self, **kwargs):
        """
        Returns a new TaskQuerySet with the given filters added.
        """
        clone = self._clone()
        for param, value in kwargs.items():
            clone.filter_obj.add_filter(param, value)
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
    DEFAULT_FILTERS = {
        'status': 'pending',
    }

    def __init__(self, data_location='~/.task', create=True):
        if not os.path.exists(data_location):
            os.makedirs(data_location)
        self.config = {
            'data.location': os.path.expanduser(data_location),
        }
        self.tasks = TaskQuerySet(self)

    def _generate_command(self, command):
        args = ['task', 'rc:/']
        for item in self.config.items():
            args.append('rc.{0}={1}'.format(*item))
        args.append(command)
        return ' '.join(args)

    def _execute_command(self, command):
        p = subprocess.Popen(self._generate_command(command), shell=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()
        if p.returncode:
            raise TaskWarriorException(stderr.strip())
        return stdout.strip().split('\n')

    def _format_filter_kwarg(self, kwarg):
        key, val = kwarg[0], kwarg[1]
        key = key.replace('__', '.')
        return '{0}:{1}'.format(key, val)

    def _execute_filter(self, filter_obj):
        filter_commands = ' '.join(map(self._format_filter_kwarg,
                                       filter_obj.get_filter_params()))
        command = '{0} export'.format(filter_commands)
        tasks = []
        for line in self._execute_command(command):
            if line:
                tasks.append(Task(self, json.loads(line.strip(','))))
        return tasks

    def add_task(self, description, project=None):
        args = ['add', description]
        if project is not None:
            args.append('project:{0}'.format(project))
        self._execute_command(' '.join(args))

    def delete_task(self, task_id):
        self._execute_command('{0} rc.confirmation:no delete'.format(task_id))

    def complete_task(self, task_id):
        self._execute_command('{0} done'.format(task_id))

    def import_tasks(self, tasks):
        fd, path = tempfile.mkstemp()
        with open(path, 'w') as f:
            f.write(json.dumps(tasks))
        self._execute_command('import {0}'.format(path))
