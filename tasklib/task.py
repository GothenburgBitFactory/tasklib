from __future__ import print_function
import copy
import datetime
import json
import logging
import os
import pytz
import six
import sys
import subprocess
import tzlocal

DATE_FORMAT = '%Y%m%dT%H%M%SZ'
REPR_OUTPUT_SIZE = 10
PENDING = 'pending'
COMPLETED = 'completed'

VERSION_2_1_0 = six.u('2.1.0')
VERSION_2_2_0 = six.u('2.2.0')
VERSION_2_3_0 = six.u('2.3.0')
VERSION_2_4_0 = six.u('2.4.0')

logger = logging.getLogger(__name__)
local_zone = tzlocal.get_localzone()


class TaskWarriorException(Exception):
    pass


class SerializingObject(object):
    """
    Common ancestor for TaskResource & TaskFilter, since they both
    need to serialize arguments.

    Serializing method should hold the following contract:
      - any empty value (meaning removal of the attribute)
        is deserialized into a empty string
      - None denotes a empty value for any attribute

    Deserializing method should hold the following contract:
      - None denotes a empty value for any attribute (however,
        this is here as a safeguard, TaskWarrior currently does
        not export empty-valued attributes) if the attribute
        is not iterable (e.g. list or set), in which case
        a empty iterable should be used.
    """

    def _deserialize(self, key, value):
        hydrate_func = getattr(self, 'deserialize_{0}'.format(key),
                               lambda x: x if x != '' else None)
        return hydrate_func(value)

    def _serialize(self, key, value):
        dehydrate_func = getattr(self, 'serialize_{0}'.format(key),
                                 lambda x: x if x is not None else '')
        return dehydrate_func(value)

    def _normalize(self, key, value):
        """
        Use normalize_<key> methods to normalize user input. Any user
        input will be normalized at the moment it is used as filter,
        or entered as a value of Task attribute.
        """

        normalize_func = getattr(self, 'normalize_{0}'.format(key),
                                 lambda x: x)

        return normalize_func(value)

    def timestamp_serializer(self, date):
        if not date:
            return ''

        # Any serialized timestamp should be localized, we need to
        # convert to UTC before converting to string (DATE_FORMAT uses UTC)
        date = date.astimezone(pytz.utc)

        return date.strftime(DATE_FORMAT)

    def timestamp_deserializer(self, date_str):
        if not date_str:
            return None

        # Return timestamp localized in the local zone
        naive_timestamp = datetime.datetime.strptime(date_str, DATE_FORMAT)
        localized_timestamp = pytz.utc.localize(naive_timestamp)
        return localized_timestamp.astimezone(local_zone)

    def serialize_entry(self, value):
        return self.timestamp_serializer(value)

    def deserialize_entry(self, value):
        return self.timestamp_deserializer(value)

    def normalize_entry(self, value):
        return self.datetime_normalizer(value)

    def serialize_modified(self, value):
        return self.timestamp_serializer(value)

    def deserialize_modified(self, value):
        return self.timestamp_deserializer(value)

    def normalize_modified(self, value):
        return self.datetime_normalizer(value)

    def serialize_due(self, value):
        return self.timestamp_serializer(value)

    def deserialize_due(self, value):
        return self.timestamp_deserializer(value)

    def normalize_due(self, value):
        return self.datetime_normalizer(value)

    def serialize_scheduled(self, value):
        return self.timestamp_serializer(value)

    def deserialize_scheduled(self, value):
        return self.timestamp_deserializer(value)

    def normalize_scheduled(self, value):
        return self.datetime_normalizer(value)

    def serialize_until(self, value):
        return self.timestamp_serializer(value)

    def deserialize_until(self, value):
        return self.timestamp_deserializer(value)

    def normalize_until(self, value):
        return self.datetime_normalizer(value)

    def serialize_wait(self, value):
        return self.timestamp_serializer(value)

    def deserialize_wait(self, value):
        return self.timestamp_deserializer(value)

    def normalize_wait(self, value):
        return self.datetime_normalizer(value)

    def serialize_annotations(self, value):
        value = value if value is not None else []

        # This may seem weird, but it's correct, we want to export
        # a list of dicts as serialized value
        serialized_annotations = [json.loads(annotation.export_data())
                                  for annotation in value]
        return serialized_annotations if serialized_annotations else ''

    def deserialize_annotations(self, data):
        return [TaskAnnotation(self, d) for d in data] if data else []

    def serialize_tags(self, tags):
        return ','.join(tags) if tags else ''

    def deserialize_tags(self, tags):
        if isinstance(tags, six.string_types):
            return tags.split(',') if tags else []
        return tags or []

    def serialize_depends(self, value):
        # Return the list of uuids
        value = value if value is not None else set()
        return ','.join(task['uuid'] for task in value)

    def deserialize_depends(self, raw_uuids):
        raw_uuids = raw_uuids or ''  # Convert None to empty string
        uuids = raw_uuids.split(',')
        return set(self.warrior.tasks.get(uuid=uuid) for uuid in uuids if uuid)

    def datetime_normalizer(self, value):
        """
        Normalizes date/datetime value (considered to come from user input)
        to localized datetime value. Following conversions happen:

        naive date -> localized datetime with the same date, and time=midnight
        naive datetime -> localized datetime with the same value
        localized datetime -> localized datetime (no conversion)
        """

        if (isinstance(value, datetime.date)
            and not isinstance(value, datetime.datetime)):
            # Convert to local midnight
            value_full = datetime.datetime.combine(value, datetime.time.min)
            localized = local_zone.localize(value_full)
        elif isinstance(value, datetime.datetime) and value.tzinfo is None:
            # Convert to localized datetime object
            localized = local_zone.localize(value)
        else:
            # If the value is already localized, there is no need to change
            # time zone at this point. Also None is a valid value too.
            localized = value
        
        return localized
            


class TaskResource(SerializingObject):
    read_only_fields = []

    def _load_data(self, data):
        self._data = dict((key, self._deserialize(key, value))
                          for key, value in data.items())
        # We need to use a copy for original data, so that changes
        # are not propagated.
        self._original_data = copy.deepcopy(self._data)

    def _update_data(self, data, update_original=False):
        """
        Low level update of the internal _data dict. Data which are coming as
        updates should already be serialized. If update_original is True, the
        original_data dict is updated as well.
        """
        self._data.update(dict((key, self._deserialize(key, value))
                               for key, value in data.items()))

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
        return json.dumps(data, separators=(',',':'))

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

    def __init__(self, task, data={}):
        self.task = task
        self._load_data(data)

    def remove(self):
        self.task.remove_annotation(self)

    def __unicode__(self):
        return self['description']

    def __eq__(self, other):
        # consider 2 annotations equal if they belong to the same task, and
        # their data dics are the same
        return self.task == other.task and self._data == other._data

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

    class NotSaved(Exception):
        """
        Raised when the operation cannot be performed on the task, because
        it has not been saved to TaskWarrior yet.
        """
        pass

    @classmethod
    def from_input(cls, input_file=sys.stdin, modify=None):
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

        # TaskWarrior instance is set to None
        task = cls(None)

        # Detect the hook type if not given directly
        name = os.path.basename(sys.argv[0])
        modify = name.startswith('on-modify') if modify is None else modify

        # Load the data from the input
        task._load_data(json.loads(input_file.readline().strip()))

        # If this is a on-modify event, we are provided with additional
        # line of input, which provides updated data
        if modify:
            task._update_data(json.loads(input_file.readline().strip()))

        return task

    def __init__(self, warrior, **kwargs):
        self.warrior = warrior

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

    def serialize_depends(self, cur_dependencies):
        # Check that all the tasks are saved
        for task in (cur_dependencies or set()):
            if not task.saved:
                raise Task.NotSaved('Task \'%s\' needs to be saved before '
                                    'it can be set as dependency.' % task)

        return super(Task, self).serialize_depends(cur_dependencies)

    def format_depends(self):
        # We need to generate added and removed dependencies list,
        # since Taskwarrior does not accept redefining dependencies.

        # This cannot be part of serialize_depends, since we need
        # to keep a list of all depedencies in the _data dictionary,
        # not just currently added/removed ones

        old_dependencies = self._original_data.get('depends', set())

        added = self['depends'] - old_dependencies
        removed = old_dependencies - self['depends']

        # Removed dependencies need to be prefixed with '-'
        return 'depends:' + ','.join(
                [t['uuid'] for t in added] +
                ['-' + t['uuid'] for t in removed]
            )

    def format_description(self):
        # Task version older than 2.4.0 ignores first word of the
        # task description if description: prefix is used
        if self.warrior.version < VERSION_2_4_0:
            return self._data['description']
        else:
            return "description:'{0}'".format(self._data['description'] or '')

    def delete(self):
        if not self.saved:
            raise Task.NotSaved("Task needs to be saved before it can be deleted")

        # Refresh the status, and raise exception if the task is deleted
        self.refresh(only_fields=['status'])

        if self.deleted:
            raise Task.DeletedTask("Task was already deleted")

        self.warrior.execute_command([self['uuid'], 'delete'])

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
        if self.saved and not self.modified:
            return

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

        # Refreshing is very important here, as not only modification time
        # is updated, but arbitrary attribute may have changed due hooks
        # altering the data before saving
        self.refresh()

    def add_annotation(self, annotation):
        if not self.saved:
            raise Task.NotSaved("Task needs to be saved to add annotation")

        args = [self['uuid'], 'annotate', annotation]
        self.warrior.execute_command(args)
        self.refresh(only_fields=['annotations'])

    def remove_annotation(self, annotation):
        if not self.saved:
            raise Task.NotSaved("Task needs to be saved to remove annotation")

        if isinstance(annotation, TaskAnnotation):
            annotation = annotation['description']
        args = [self['uuid'], 'denotate', annotation]
        self.warrior.execute_command(args)
        self.refresh(only_fields=['annotations'])

    def _get_modified_fields_as_args(self):
        args = []

        def add_field(field):
            # Add the output of format_field method to args list (defaults to
            # field:value)
            serialized_value = self._serialize(field, self._data[field])

            # Empty values should not be enclosed in quotation marks, see
            # TW-1510
            if serialized_value is '':
                escaped_serialized_value = ''
            else:
                escaped_serialized_value = "'{0}'".format(serialized_value)

            format_default = lambda: "{0}:{1}".format(field,
                                                      escaped_serialized_value)

            format_func = getattr(self, 'format_{0}'.format(field),
                                  format_default)

            args.append(format_func())

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
            self._update_data(to_update, update_original=True)
        else:
            self._load_data(new_data)

class TaskFilter(SerializingObject):
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
        attribute_key = key.split('.')[0]

        # Since this is user input, we need to normalize before we serialize
        value = self._normalize(key, value)
        value = self._serialize(attribute_key, value)

        # If we are filtering by uuid:, do not use uuid keyword
        # due to TW-1452 bug
        if key == 'uuid':
            self.filter_params.insert(0, value)
        else:
            # Surround value with aphostrophes unless it's a empty string
            value = "'%s'" % value if value else ''

            # We enforce equality match by using 'is' (or 'none') modifier
            # Without using this syntax, filter fails due to TW-1479
            modifier = '.is' if value else '.none'
            key = key + modifier if '.' not in key else key

            self.filter_params.append("{0}:{1}".format(key, value))

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
            'confirmation': 'no',
            'dependency.confirmation': 'no',  # See TW-1483 or taskrc man page
            'recurrence.confirmation': 'no',  # Necessary for modifying R tasks
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
                    filtered_task = Task(self)
                    filtered_task._load_data(json.loads(data))
                    tasks.append(filtered_task)
                except ValueError:
                    raise TaskWarriorException('Invalid JSON: %s' % data)
        return tasks

    def merge_with(self, path, push=False):
        path = path.rstrip('/') + '/'
        self.execute_command(['merge', path], config_override={
            'merge.autopush': 'yes' if push else 'no',
        })

    def undo(self):
        self.execute_command(['undo'])
