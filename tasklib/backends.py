import abc
import os
import re
import subprocess


VERSION_2_1_0 = six.u('2.1.0')
VERSION_2_2_0 = six.u('2.2.0')
VERSION_2_3_0 = six.u('2.3.0')
VERSION_2_4_0 = six.u('2.4.0')
VERSION_2_4_1 = six.u('2.4.1')
VERSION_2_4_2 = six.u('2.4.2')
VERSION_2_4_3 = six.u('2.4.3')
VERSION_2_4_4 = six.u('2.4.4')
VERSION_2_4_5 = six.u('2.4.5')


class Backend(object):

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
    def sync(self):
        """Syncs the backend database with the taskd server"""
        pass


class TaskWarriorException(Exception):
    pass


class TaskWarrior(object):
    def __init__(self, data_location=None, create=True, taskrc_location='~/.taskrc'):
        self.taskrc_location = os.path.expanduser(taskrc_location)

        # If taskrc does not exist, pass / to use defaults and avoid creating
        # dummy .taskrc file by TaskWarrior
        if not os.path.exists(self.taskrc_location):
            self.taskrc_location = '/'

        self.version = self._get_version()
        self.config = {
            'confirmation': 'no',
            'dependency.confirmation': 'no',  # See TW-1483 or taskrc man page
            'recurrence.confirmation': 'no',  # Necessary for modifying R tasks

            # Defaults to on since 2.4.5, we expect off during parsing
            'json.array': 'off',

            # 2.4.3 onwards supports 0 as infite bulk, otherwise set just
            # arbitrary big number which is likely to be large enough
            'bulk': 0 if self.version >= VERSION_2_4_3 else 100000,
        }

        # Set data.location override if passed via kwarg
        if data_location is not None:
            data_location = os.path.expanduser(data_location)
            if create and not os.path.exists(data_location):
                os.makedirs(data_location)
            self.config['data.location'] = data_location

        self.tasks = TaskQuerySet(self)

    def _get_command_args(self, args, config_override=None):
        command_args = ['task', 'rc:{0}'.format(self.taskrc_location)]
        config = self.config.copy()
        config.update(config_override or dict())
        for item in config.items():
            command_args.append('rc.{0}={1}'.format(*item))
        command_args.extend(map(six.text_type, args))
        return command_args

    def _get_version(self):
        p = subprocess.Popen(
                ['task', '--version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        stdout, stderr = [x.decode('utf-8') for x in p.communicate()]
        return stdout.strip('\n')

    def get_config(self):
        raw_output = self.execute_command(
                ['show'],
                config_override={'verbose': 'nothing'}
            )

        config = dict()
        config_regex = re.compile(r'^(?P<key>[^\s]+)\s+(?P<value>[^\s].+$)')

        for line in raw_output:
            match = config_regex.match(line)
            if match:
                config[match.group('key')] = match.group('value').strip()

        return config

    def execute_command(self, args, config_override=None, allow_failure=True,
                        return_all=False):
        command_args = self._get_command_args(
            args, config_override=config_override)
        logger.debug(' '.join(command_args))
        p = subprocess.Popen(command_args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        stdout, stderr = [x.decode('utf-8') for x in p.communicate()]
        if p.returncode and allow_failure:
            if stderr.strip():
                error_msg = stderr.strip()
            else:
                error_msg = stdout.strip()
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
        if self.version < VERSION_2_4_2:
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
        args = ['export', '--'] + filter_obj.get_filter_params()
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
        args.extend(task._get_modified_fields_as_args())
        output = self.execute_command(args)

        # Parse out the new ID, if the task is being added for the first time
        if not task.saved:
            id_lines = [l for l in output if l.startswith('Created task ')]

            # Complain loudly if it seems that more tasks were created
            # Should not happen
            if len(id_lines) != 1 or len(id_lines[0].split(' ')) != 3:
                raise TaskWarriorException("Unexpected output when creating "
                                           "task: %s" % '\n'.join(id_lines))

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
