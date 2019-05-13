import abc
import copy
import datetime
import json
import logging
import os
import re
import six
import subprocess

from .task import Task, TaskQuerySet, ReadOnlyDictView
from .filters import TaskWarriorFilter
from .serializing import local_zone

DATE_FORMAT_CALC = '%Y-%m-%dT%H:%M:%S'

logger = logging.getLogger(__name__)


class Backend(object):

    @abc.abstractproperty
    def filter_class(self):
        """Returns the TaskFilter class used by this backend"""
        pass

    @abc.abstractmethod
    def filter_tasks(self, filter_obj):
        """Returns a list of Task objects matching the given filter"""
        pass

    @abc.abstractmethod
    def save_task(self, task):
        pass

    @abc.abstractmethod
    def delete_task(self, task):
        pass

    @abc.abstractmethod
    def start_task(self, task):
        pass

    @abc.abstractmethod
    def stop_task(self, task):
        pass

    @abc.abstractmethod
    def complete_task(self, task):
        pass

    @abc.abstractmethod
    def refresh_task(self, task, after_save=False):
        """
        Refreshes the given task. Returns new data dict with serialized
        attributes.
        """
        pass

    @abc.abstractmethod
    def annotate_task(self, task, annotation):
        pass

    @abc.abstractmethod
    def denotate_task(self, task, annotation):
        pass

    @abc.abstractmethod
    def sync(self):
        """Syncs the backend database with the taskd server"""
        pass

    def convert_datetime_string(self, value):
        """
        Converts TW syntax datetime string to a localized datetime
        object. This method is not mandatory.
        """
        raise NotImplementedError


class TaskWarriorException(Exception):
    pass


class TaskWarrior(Backend):

    VERSION_2_1_0 = six.u('2.1.0')
    VERSION_2_2_0 = six.u('2.2.0')
    VERSION_2_3_0 = six.u('2.3.0')
    VERSION_2_4_0 = six.u('2.4.0')
    VERSION_2_4_1 = six.u('2.4.1')
    VERSION_2_4_2 = six.u('2.4.2')
    VERSION_2_4_3 = six.u('2.4.3')
    VERSION_2_4_4 = six.u('2.4.4')
    VERSION_2_4_5 = six.u('2.4.5')

    def __init__(self, data_location=None, create=True,
                 taskrc_location=None, task_command='task',
                 version_override=None):
        self.taskrc_location = None
        if taskrc_location:
            self.taskrc_location = os.path.expanduser(taskrc_location)

            # If taskrc does not exist, pass / to use defaults and avoid creating
            # dummy .taskrc file by TaskWarrior
            if not os.path.exists(self.taskrc_location):
                self.taskrc_location = '/'

        self.task_command = task_command

        self._config = None
        self.version = version_override or self._get_version()
        self.overrides = {
            'confirmation': 'no',
            'dependency.confirmation': 'no',  # See TW-1483 or taskrc man page
            'recurrence.confirmation': 'no',  # Necessary for modifying R tasks

            # Defaults to on since 2.4.5, we expect off during parsing
            'json.array': 'off',

            # 2.4.3 onwards supports 0 as infite bulk, otherwise set just
            # arbitrary big number which is likely to be large enough
            'bulk': 0 if self.version >= self.VERSION_2_4_3 else 100000,
        }

        # Set data.location override if passed via kwarg
        if data_location is not None:
            data_location = os.path.expanduser(data_location)
            if create and not os.path.exists(data_location):
                os.makedirs(data_location)
            self.overrides['data.location'] = data_location

        self.tasks = TaskQuerySet(self)

    def _get_task_command(self):
        return self.task_command.split()

    def _get_command_args(self, args, config_override=None):
        command_args = self._get_task_command()
        overrides = self.overrides.copy()
        overrides.update(config_override or dict())
        for item in overrides.items():
            command_args.append('rc.{0}={1}'.format(*item))
        command_args.extend([
            x.decode('utf-8') if isinstance(x, six.binary_type)
            else six.text_type(x) for x in args
        ])
        return command_args

    def _get_version(self):
        p = subprocess.Popen(
            self._get_task_command() + ['--version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        stdout, stderr = [x.decode('utf-8') for x in p.communicate()]
        return stdout.strip('\n')

    def _get_modified_task_fields_as_args(self, task):
        args = []

        def add_field(field):
            # Add the output of format_field method to args list (defaults to
            # field:value)
            serialized_value = task._serialize(field, task._data[field])

            # Empty values should not be enclosed in quotation marks, see
            # TW-1510
            if serialized_value is '':
                escaped_serialized_value = ''
            else:
                escaped_serialized_value = six.u("'{0}'").format(
                    serialized_value)

            format_default = lambda task: six.u("{0}:{1}").format(
                field, escaped_serialized_value)

            format_func = getattr(self, 'format_{0}'.format(field),
                                  format_default)

            args.append(format_func(task))

        # If we're modifying saved task, simply pass on all modified fields
        if task.saved:
            for field in task._modified_fields:
                add_field(field)

        # For new tasks, pass all fields that make sense
        else:
            for field in task._data.keys():
                # We cannot set stuff that's read only (ID, UUID, ..)
                if field in task.read_only_fields:
                    continue
                # We do not want to do field deletion for new tasks
                if task._data[field] is None:
                    continue
                # Otherwise we're fine
                add_field(field)

        return args

    def format_depends(self, task):
        # We need to generate added and removed dependencies list,
        # since Taskwarrior does not accept redefining dependencies.

        # This cannot be part of serialize_depends, since we need
        # to keep a list of all depedencies in the _data dictionary,
        # not just currently added/removed ones

        old_dependencies = task._original_data.get('depends', set())

        added = task['depends'] - old_dependencies
        removed = old_dependencies - task['depends']

        # Removed dependencies need to be prefixed with '-'
        return 'depends:' + ','.join(
            [t['uuid'] for t in added] +
            ['-' + t['uuid'] for t in removed]
        )

    def format_description(self, task):
        # Task version older than 2.4.0 ignores first word of the
        # task description if description: prefix is used
        if self.version < self.VERSION_2_4_0:
            return task._data['description']
        else:
            return six.u("description:'{0}'").format(
                task._data['description'] or '',
            )

    def convert_datetime_string(self, value):

        if self.version >= self.VERSION_2_4_0:
            # For strings, use 'calc' to evaluate the string to datetime
            # available since TW 2.4.0
            args = value.split()
            result = self.execute_command(['calc'] + args)
            naive = datetime.datetime.strptime(result[0], DATE_FORMAT_CALC)
            localized = local_zone.localize(naive)
        else:
            raise ValueError(
                'Provided value could not be converted to '
                'datetime, its type is not supported: {}'
                .format(type(value)),
            )

        return localized

    @property
    def filter_class(self):
        return TaskWarriorFilter

    # Public interface

    @property
    def config(self):
        # First, check if memoized information is available
        if self._config:
            return self._config

        # If not, fetch the config using the 'show' command
        raw_output = self.execute_command(
            ['show'],
            config_override={'verbose': 'nothing'}
        )

        config = dict()
        config_regex = re.compile(r'^(?P<key>[^\s]+)\s+(?P<value>[^\s].*$)')

        for line in raw_output:
            match = config_regex.match(line)
            if match:
                config[match.group('key')] = match.group('value').strip()

        # Memoize the config dict
        self._config = ReadOnlyDictView(config)

        return self._config

    def execute_command(self, args, config_override=None, allow_failure=True,
                        return_all=False):
        command_args = self._get_command_args(
            args, config_override=config_override)
        logger.debug(u' '.join(command_args))

        env = os.environ.copy()
        if self.taskrc_location:
            env['TASKRC'] = self.taskrc_location
        p = subprocess.Popen(command_args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env)
        stdout, stderr = [x.decode('utf-8') for x in p.communicate()]
        if p.returncode and allow_failure:
            if stderr.strip():
                error_msg = stderr.strip()
            else:
                error_msg = stdout.strip()
            error_msg += u'\nCommand used: ' + u' '.join(command_args)
            raise TaskWarriorException(error_msg)

        # Return all whole triplet only if explicitly asked for
        if not return_all:
            return stdout.rstrip().split('\n')
        else:
            return (stdout.rstrip().split('\n'),
                    stderr.rstrip().split('\n'),
                    p.returncode)

    def enforce_recurrence(self):
        # Run arbitrary report command which will trigger generation
        # of recurrent tasks.

        # Only necessary for TW up to 2.4.1, fixed in 2.4.2.
        if self.version < self.VERSION_2_4_2:
            self.execute_command(['next'], allow_failure=False)

    def merge_with(self, path, push=False):
        path = path.rstrip('/') + '/'
        self.execute_command(['merge', path], config_override={
            'merge.autopush': 'yes' if push else 'no',
        })

    def undo(self):
        self.execute_command(['undo'])

    # Backend interface implementation

    def filter_tasks(self, filter_obj):
        self.enforce_recurrence()
        args = ['export'] + filter_obj.get_filter_params()
        tasks = []
        for line in self.execute_command(args):
            if line:
                data = line.strip(',')
                try:
                    filtered_task = Task(self)
                    filtered_task._load_data(json.loads(data))
                    tasks.append(filtered_task)
                except ValueError:
                    raise TaskWarriorException('Invalid JSON: %s' % data)
        return tasks

    def save_task(self, task):
        """Save a task into TaskWarrior database using add/modify call"""

        args = [task['uuid'], 'modify'] if task.saved else ['add']
        args.extend(self._get_modified_task_fields_as_args(task))
        output = self.execute_command(args)

        # Parse out the new ID, if the task is being added for the first time
        if not task.saved:
            id_lines = [l for l in output if l.startswith('Created task ')]

            # Complain loudly if it seems that more tasks were created
            # Should not happen.
            # Expected output: Created task 1.
            #                  Created task 1 (recurrence template).
            if len(id_lines) != 1 or len(id_lines[0].split(' ')) not in (3, 5):
                raise TaskWarriorException(
                    'Unexpected output when creating '
                    'task: %s' % '\n'.join(id_lines),
                )

            # Circumvent the ID storage, since ID is considered read-only
            identifier = id_lines[0].split(' ')[2].rstrip('.')

            # Identifier can be either ID or UUID for completed tasks
            try:
                task._data['id'] = int(identifier)
            except ValueError:
                task._data['uuid'] = identifier

        # Refreshing is very important here, as not only modification time
        # is updated, but arbitrary attribute may have changed due hooks
        # altering the data before saving
        task.refresh(after_save=True)

    def delete_task(self, task):
        self.execute_command([task['uuid'], 'delete'])

    def start_task(self, task):
        self.execute_command([task['uuid'], 'start'])

    def stop_task(self, task):
        self.execute_command([task['uuid'], 'stop'])

    def complete_task(self, task):
        # Older versions of TW do not stop active task at completion
        if self.version < self.VERSION_2_4_0 and task.active:
            task.stop()

        self.execute_command([task['uuid'], 'done'])

    def annotate_task(self, task, annotation):
        args = [task['uuid'], 'annotate', annotation]
        self.execute_command(args)

    def denotate_task(self, task, annotation):
        args = [task['uuid'], 'denotate', annotation]
        self.execute_command(args)

    def refresh_task(self, task, after_save=False):
        # We need to use ID as backup for uuid here for the refreshes
        # of newly saved tasks. Any other place in the code is fine
        # with using UUID only.
        args = [task['uuid'] or task['id'], 'export']
        output = self.execute_command(args)

        def valid(output):
            return len(output) == 1 and output[0].startswith('{')

        # For older TW versions attempt to uniquely locate the task
        # using the data we have if it has been just saved.
        # This can happen when adding a completed task on older TW versions.
        if (not valid(output) and self.version < self.VERSION_2_4_5
                and after_save):

            # Make a copy, removing ID and UUID. It's most likely invalid
            # (ID 0) if it failed to match a unique task.
            data = copy.deepcopy(task._data)
            data.pop('id', None)
            data.pop('uuid', None)

            taskfilter = self.filter_class(self)
            for key, value in data.items():
                taskfilter.add_filter_param(key, value)

            output = self.execute_command(['export'] +
                                          taskfilter.get_filter_params())

        # If more than 1 task has been matched still, raise an exception
        if not valid(output):
            raise TaskWarriorException(
                'Unique identifiers {0} with description: {1} matches '
                'multiple tasks: {2}'.format(
                    task['uuid'] or task['id'], task['description'], output)
            )

        return json.loads(output[0])

    def sync(self):
        self.execute_command(['sync'])
