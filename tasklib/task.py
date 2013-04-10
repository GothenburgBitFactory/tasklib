import json
import os
import subprocess
import tempfile
import uuid


PENDING = 'pending'


class TaskWarriorException(Exception):
    pass


class Task(object):

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

    def _generate_command(self, command):
        args = ['task', 'rc:/']
        for item in self.config.items():
            args.append('rc.{0}={1}'.format(*item))
        args.append(command)
        return ' '.join(args)

    def _execute(self, command):
        p = subprocess.Popen(self._generate_command(command), shell=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()
        if p.returncode:
            raise TaskWarriorException(stderr.strip())
        return stdout.strip().split('\n')

    def _format_filter_kwarg(self, kwarg):
        key, val = kwarg[0], kwarg[1]
        if key in ['tag', 'tags']:
            key = 'tags.equal'
        key = key.replace('__', '.')
        return '{0}:{1}'.format(key, val)

    def get_tasks(self, **filter_kwargs):
        filters = self.DEFAULT_FILTERS
        filters.update(filter_kwargs)
        filter_commands = ' '.join(map(self._format_filter_kwarg,
                                       filters.items()))
        command = '{0} export'.format(filter_commands)
        tasks = []
        for line in self._execute(command):
            if line:
                tasks.append(Task(self, json.loads(line.strip(','))))
        return tasks

    def get_task(self, task_id):
        command = '{0} export'.format(task_id)
        return Task(self, json.loads(self._execute(command)[0]))

    def add_task(self, description, project=None):
        args = ['add', description]
        if project is not None:
            args.append('project:{0}'.format(project))
        self._execute(' '.join(args))

    def delete_task(self, task_id):
        self._execute('{0} rc.confirmation:no delete'.format(task_id))

    def complete_task(self, task_id):
        self._execute('{0} done'.format(task_id))

    def import_tasks(self, tasks):
        fd, path = tempfile.mkstemp()
        with open(path, 'w') as f:
            f.write(json.dumps(tasks))
        self._execute('import {0}'.format(path))
