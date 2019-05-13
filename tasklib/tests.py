# coding=utf-8

import copy
import datetime
import itertools
import json
import os
import pytz
import six
import shutil
import sys
import tempfile
import unittest

from .backends import TaskWarrior
from .task import Task, ReadOnlyDictView
from .lazy import LazyUUIDTask, LazyUUIDTaskSet
from .serializing import DATE_FORMAT, local_zone

# http://taskwarrior.org/docs/design/task.html , Section: The Attributes
TASK_STANDARD_ATTRS = (
    'status',
    'uuid',
    'entry',
    'description',
    'start',
    'end',
    'due',
    'until',
    'wait',
    'modified',
    'scheduled',
    'recur',
    'mask',
    'imask',
    'parent',
    'project',
    'priority',
    'depends',
    'tags',
    'annotations',
)


def total_seconds_2_6(x):
    return x.microseconds / 1e6 + x.seconds + x.days * 24 * 3600


class TasklibTest(unittest.TestCase):

    def get_taskwarrior(self, **kwargs):
        tw_kwargs = dict(
            data_location=self.tmp,
            taskrc_location='/',
        )
        tw_kwargs.update(kwargs)
        return TaskWarrior(**tw_kwargs)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir='.')
        self.tw = self.get_taskwarrior()

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TaskWarriorTest(TasklibTest):

    def test_custom_command(self):
        # ensure that a custom command which contains multiple parts
        # is properly split up
        tw = self.get_taskwarrior(
            task_command='wsl task',
            # prevent `_get_version` from running as `wsl` may not exist
            version_override=os.getenv('TASK_VERSION'),
        )
        self.assertEqual(tw._get_task_command(), ['wsl', 'task'])


class TaskFilterTest(TasklibTest):

    def test_all_empty(self):
        self.assertEqual(len(self.tw.tasks.all()), 0)

    def test_all_non_empty(self):
        Task(self.tw, description='test task').save()
        self.assertEqual(len(self.tw.tasks.all()), 1)
        self.assertEqual(self.tw.tasks.all()[0]['description'], 'test task')
        self.assertEqual(self.tw.tasks.all()[0]['status'], 'pending')

    def test_pending_non_empty(self):
        Task(self.tw, description='test task').save()
        self.assertEqual(len(self.tw.tasks.pending()), 1)
        self.assertEqual(
            self.tw.tasks.pending()[0]['description'],
            'test task',
        )
        self.assertEqual(self.tw.tasks.pending()[0]['status'], 'pending')

    def test_completed_empty(self):
        Task(self.tw, description='test task').save()
        self.assertEqual(len(self.tw.tasks.completed()), 0)

    def test_completed_non_empty(self):
        Task(self.tw, description='test task').save()
        self.assertEqual(len(self.tw.tasks.completed()), 0)
        self.tw.tasks.all()[0].done()
        self.assertEqual(len(self.tw.tasks.completed()), 1)

    def test_deleted_empty(self):
        Task(self.tw, description='test task').save()
        self.assertEqual(len(self.tw.tasks.deleted()), 0)

    def test_deleted_non_empty(self):
        Task(self.tw, description='test task').save()
        self.assertEqual(len(self.tw.tasks.deleted()), 0)
        self.tw.tasks.all()[0].delete()
        self.assertEqual(len(self.tw.tasks.deleted()), 1)

    def test_waiting_empty(self):
        Task(self.tw, description='test task').save()
        self.assertEqual(len(self.tw.tasks.waiting()), 0)

    def test_waiting_non_empty(self):
        Task(self.tw, description='test task').save()
        self.assertEqual(len(self.tw.tasks.waiting()), 0)

        t = self.tw.tasks.all()[0]
        t['wait'] = datetime.datetime.now() + datetime.timedelta(days=1)
        t.save()

        self.assertEqual(len(self.tw.tasks.waiting()), 1)

    def test_recurring_empty(self):
        Task(self.tw, description='test task').save()
        self.assertEqual(len(self.tw.tasks.recurring()), 0)

    def test_recurring_non_empty(self):
        Task(
            self.tw,
            description='test task',
            recur='daily',
            due=datetime.datetime.now(),
        ).save()
        self.assertEqual(len(self.tw.tasks.recurring()), 1)

    def test_filtering_by_attribute(self):
        Task(self.tw, description='no priority task').save()
        Task(self.tw, priority='H', description='high priority task').save()
        self.assertEqual(len(self.tw.tasks.all()), 2)

        # Assert that the correct number of tasks is returned
        self.assertEqual(len(self.tw.tasks.filter(priority='H')), 1)

        # Assert that the correct tasks are returned
        high_priority_task = self.tw.tasks.get(priority='H')
        self.assertEqual(
            high_priority_task['description'],
            'high priority task',
        )

    def test_filtering_by_empty_attribute(self):
        Task(self.tw, description='no priority task').save()
        Task(self.tw, priority='H', description='high priority task').save()
        self.assertEqual(len(self.tw.tasks.all()), 2)

        # Assert that the correct number of tasks is returned
        self.assertEqual(len(self.tw.tasks.filter(priority=None)), 1)

        # Assert that the correct tasks are returned
        no_priority_task = self.tw.tasks.get(priority=None)
        self.assertEqual(no_priority_task['description'], 'no priority task')

    def test_filter_for_task_with_space_in_descripition(self):
        task = Task(self.tw, description='test task')
        task.save()

        filtered_task = self.tw.tasks.get(description='test task')
        self.assertEqual(filtered_task['description'], 'test task')

    def test_filter_for_task_without_space_in_descripition(self):
        task = Task(self.tw, description='test')
        task.save()

        filtered_task = self.tw.tasks.get(description='test')
        self.assertEqual(filtered_task['description'], 'test')

    def test_filter_for_task_with_space_in_project(self):
        task = Task(self.tw, description='test', project='random project')
        task.save()

        filtered_task = self.tw.tasks.get(project='random project')
        self.assertEqual(filtered_task['project'], 'random project')

    def test_filter_for_task_without_space_in_project(self):
        task = Task(self.tw, description='test', project='random')
        task.save()

        filtered_task = self.tw.tasks.get(project='random')
        self.assertEqual(filtered_task['project'], 'random')

    def test_filter_with_empty_uuid(self):
        self.assertRaises(ValueError, lambda: self.tw.tasks.get(uuid=''))

    def test_filter_dummy_by_status(self):
        t = Task(self.tw, description='test')
        t.save()

        tasks = self.tw.tasks.filter(status=t['status'])
        self.assertEqual(list(tasks), [t])

    def test_filter_dummy_by_uuid(self):
        t = Task(self.tw, description='test')
        t.save()

        tasks = self.tw.tasks.filter(uuid=t['uuid'])
        self.assertEqual(list(tasks), [t])

    def test_filter_dummy_by_entry(self):
        t = Task(self.tw, description='test')
        t.save()

        tasks = self.tw.tasks.filter(entry=t['entry'])
        self.assertEqual(list(tasks), [t])

    def test_filter_dummy_by_description(self):
        t = Task(self.tw, description='test')
        t.save()

        tasks = self.tw.tasks.filter(description=t['description'])
        self.assertEqual(list(tasks), [t])

    def test_filter_dummy_by_start(self):
        t = Task(self.tw, description='test')
        t.save()
        t.start()

        tasks = self.tw.tasks.filter(start=t['start'])
        self.assertEqual(list(tasks), [t])

    def test_filter_dummy_by_end(self):
        t = Task(self.tw, description='test')
        t.save()
        t.done()

        tasks = self.tw.tasks.filter(end=t['end'])
        self.assertEqual(list(tasks), [t])

    def test_filter_dummy_by_due(self):
        t = Task(self.tw, description='test', due=datetime.datetime.now())
        t.save()

        tasks = self.tw.tasks.filter(due=t['due'])
        self.assertEqual(list(tasks), [t])

    def test_filter_dummy_by_until(self):
        t = Task(self.tw, description='test')
        t.save()

        tasks = self.tw.tasks.filter(until=t['until'])
        self.assertEqual(list(tasks), [t])

    def test_filter_dummy_by_modified(self):
        # Older TW version does not support bumping modified
        # on save
        if self.tw.version < six.text_type('2.2.0'):
            # Python2.6 does not support SkipTest. As a workaround
            # mark the test as passed by exiting.
            if getattr(unittest, 'SkipTest', None) is not None:
                raise unittest.SkipTest()
            else:
                return

        t = Task(self.tw, description='test')
        t.save()

        tasks = self.tw.tasks.filter(modified=t['modified'])
        self.assertEqual(list(tasks), [t])

    def test_filter_dummy_by_scheduled(self):
        t = Task(self.tw, description='test')
        t.save()

        tasks = self.tw.tasks.filter(scheduled=t['scheduled'])
        self.assertEqual(list(tasks), [t])

    def test_filter_dummy_by_tags(self):
        t = Task(self.tw, description='test', tags=['home'])
        t.save()

        tasks = self.tw.tasks.filter(tags=t['tags'])
        self.assertEqual(list(tasks), [t])

    def test_filter_dummy_by_projects(self):
        t = Task(self.tw, description='test', project='random')
        t.save()

        tasks = self.tw.tasks.filter(project=t['project'])
        self.assertEqual(list(tasks), [t])

    def test_filter_by_priority(self):
        t = Task(self.tw, description='test', priority='H')
        t.save()

        tasks = self.tw.tasks.filter(priority=t['priority'])
        self.assertEqual(list(tasks), [t])


class TaskTest(TasklibTest):

    def test_create_unsaved_task(self):
        # Make sure a new task is not saved unless explicitly called for
        Task(self.tw, description='test task')
        self.assertEqual(len(self.tw.tasks.all()), 0)

    # TODO: once python 2.6 compatibility is over, use context managers here
    #       and in all subsequent tests for assertRaises

    def test_delete_unsaved_task(self):
        t = Task(self.tw, description='test task')
        self.assertRaises(Task.NotSaved, t.delete)

    def test_complete_unsaved_task(self):
        t = Task(self.tw, description='test task')
        self.assertRaises(Task.NotSaved, t.done)

    def test_refresh_unsaved_task(self):
        t = Task(self.tw, description='test task')
        self.assertRaises(Task.NotSaved, t.refresh)

    def test_start_unsaved_task(self):
        t = Task(self.tw, description='test task')
        self.assertRaises(Task.NotSaved, t.start)

    def test_delete_deleted_task(self):
        t = Task(self.tw, description='test task')
        t.save()
        t.delete()

        self.assertRaises(Task.DeletedTask, t.delete)

    def test_complete_completed_task(self):
        t = Task(self.tw, description='test task')
        t.save()
        t.done()

        self.assertRaises(Task.CompletedTask, t.done)

    def test_start_completed_task(self):
        t = Task(self.tw, description='test task')
        t.save()
        t.done()

        self.assertRaises(Task.CompletedTask, t.start)

    def test_add_completed_task(self):
        t = Task(
            self.tw,
            description='test',
            status='completed',
            end=datetime.datetime.now(),
        )
        t.save()

    def test_add_multiple_completed_tasks(self):
        t1 = Task(
            self.tw,
            description='test1',
            status='completed',
            end=datetime.datetime.now(),
        )
        t2 = Task(
            self.tw,
            description='test2',
            status='completed',
            end=datetime.datetime.now(),
        )
        t1.save()
        t2.save()

    def test_complete_deleted_task(self):
        t = Task(self.tw, description='test task')
        t.save()
        t.delete()

        self.assertRaises(Task.DeletedTask, t.done)

    def test_starting_task(self):
        t = Task(self.tw, description='test task')
        now = t.datetime_normalizer(datetime.datetime.now())
        t.save()
        t.start()

        self.assertTrue(now.replace(microsecond=0) <= t['start'])
        self.assertEqual(t['status'], 'pending')

    def test_completing_task(self):
        t = Task(self.tw, description='test task')
        now = t.datetime_normalizer(datetime.datetime.now())
        t.save()
        t.done()

        self.assertTrue(now.replace(microsecond=0) <= t['end'])
        self.assertEqual(t['status'], 'completed')

    def test_deleting_task(self):
        t = Task(self.tw, description='test task')
        now = t.datetime_normalizer(datetime.datetime.now())
        t.save()
        t.delete()

        self.assertTrue(now.replace(microsecond=0) <= t['end'])
        self.assertEqual(t['status'], 'deleted')

    def test_started_task_active(self):
        t = Task(self.tw, description='test task')
        t.save()
        t.start()
        self.assertTrue(t.active)

    def test_unstarted_task_inactive(self):
        t = Task(self.tw, description='test task')
        self.assertFalse(t.active)
        t.save()
        self.assertFalse(t.active)

    def test_start_active_task(self):
        t = Task(self.tw, description='test task')
        t.save()
        t.start()
        self.assertRaises(Task.ActiveTask, t.start)

    def test_stop_completed_task(self):
        t = Task(self.tw, description='test task')
        t.save()
        t.start()
        t.done()

        self.assertRaises(Task.InactiveTask, t.stop)

        t = Task(self.tw, description='test task')
        t.save()
        t.done()

        self.assertRaises(Task.InactiveTask, t.stop)

    def test_stop_deleted_task(self):
        t = Task(self.tw, description='test task')
        t.save()
        t.start()
        t.delete()
        t.stop()

    def test_stop_inactive_task(self):
        t = Task(self.tw, description='test task')
        t.save()

        self.assertRaises(Task.InactiveTask, t.stop)

        t = Task(self.tw, description='test task')
        t.save()
        t.start()
        t.stop()

        self.assertRaises(Task.InactiveTask, t.stop)

    def test_stopping_task(self):
        t = Task(self.tw, description='test task')
        t.datetime_normalizer(datetime.datetime.now())
        t.save()
        t.start()
        t.stop()

        self.assertEqual(t['end'], None)
        self.assertEqual(t['status'], 'pending')
        self.assertFalse(t.active)

    def test_modify_simple_attribute_without_space(self):
        t = Task(self.tw, description='test')
        t.save()

        self.assertEqual(t['description'], 'test')

        t['description'] = 'test-modified'
        t.save()

        self.assertEqual(t['description'], 'test-modified')

    def test_modify_simple_attribute_with_space(self):
        # Space can pose problems with parsing
        t = Task(self.tw, description='test task')
        t.save()

        self.assertEqual(t['description'], 'test task')

        t['description'] = 'test task modified'
        t.save()

        self.assertEqual(t['description'], 'test task modified')

    def test_empty_dependency_set_of_unsaved_task(self):
        t = Task(self.tw, description='test task')
        self.assertEqual(t['depends'], set())

    def test_empty_dependency_set_of_saved_task(self):
        t = Task(self.tw, description='test task')
        t.save()
        self.assertEqual(t['depends'], set())

    def test_set_unsaved_task_as_dependency(self):
        # Adds only one dependency to task with no dependencies
        t = Task(self.tw, description='test task')
        dependency = Task(self.tw, description='needs to be done first')

        # We only save the parent task, dependency task is unsaved
        t.save()
        t['depends'] = set([dependency])

        self.assertRaises(Task.NotSaved, t.save)

    def test_set_simple_dependency_set(self):
        # Adds only one dependency to task with no dependencies
        t = Task(self.tw, description='test task')
        dependency = Task(self.tw, description='needs to be done first')

        t.save()
        dependency.save()

        t['depends'] = set([dependency])

        self.assertEqual(t['depends'], set([dependency]))

    def test_set_complex_dependency_set(self):
        # Adds two dependencies to task with no dependencies
        t = Task(self.tw, description='test task')
        dependency1 = Task(self.tw, description='needs to be done first')
        dependency2 = Task(self.tw, description='needs to be done second')

        t.save()
        dependency1.save()
        dependency2.save()

        t['depends'] = set([dependency1, dependency2])

        self.assertEqual(t['depends'], set([dependency1, dependency2]))

    def test_remove_from_dependency_set(self):
        # Removes dependency from task with two dependencies
        t = Task(self.tw, description='test task')
        dependency1 = Task(self.tw, description='needs to be done first')
        dependency2 = Task(self.tw, description='needs to be done second')

        dependency1.save()
        dependency2.save()

        t['depends'] = set([dependency1, dependency2])
        t.save()

        t['depends'].remove(dependency2)
        t.save()

        self.assertEqual(t['depends'], set([dependency1]))

    def test_add_to_dependency_set(self):
        # Adds dependency to task with one dependencies
        t = Task(self.tw, description='test task')
        dependency1 = Task(self.tw, description='needs to be done first')
        dependency2 = Task(self.tw, description='needs to be done second')

        dependency1.save()
        dependency2.save()

        t['depends'] = set([dependency1])
        t.save()

        t['depends'].add(dependency2)
        t.save()

        self.assertEqual(t['depends'], set([dependency1, dependency2]))

    def test_add_to_empty_dependency_set(self):
        # Adds dependency to task with one dependencies
        t = Task(self.tw, description='test task')
        dependency = Task(self.tw, description='needs to be done first')

        dependency.save()

        t['depends'].add(dependency)
        t.save()

        self.assertEqual(t['depends'], set([dependency]))

    def test_simple_dependency_set_save_repeatedly(self):
        # Adds only one dependency to task with no dependencies
        t = Task(self.tw, description='test task')
        dependency = Task(self.tw, description='needs to be done first')
        dependency.save()

        t['depends'] = set([dependency])
        t.save()

        # We taint the task, but keep depends intact
        t['description'] = 'test task modified'
        t.save()

        self.assertEqual(t['depends'], set([dependency]))

        # We taint the task, but assign the same set to the depends
        t['depends'] = set([dependency])
        t['description'] = 'test task modified again'
        t.save()

        self.assertEqual(t['depends'], set([dependency]))

    def test_compare_different_tasks(self):
        # Negative: compare two different tasks
        t1 = Task(self.tw, description='test task')
        t2 = Task(self.tw, description='test task')

        t1.save()
        t2.save()

        self.assertEqual(t1 == t2, False)

    def test_compare_same_task_object(self):
        # Compare Task object wit itself
        t = Task(self.tw, description='test task')
        t.save()

        self.assertEqual(t == t, True)

    def test_compare_same_task(self):
        # Compare the same task using two different objects
        t1 = Task(self.tw, description='test task')
        t1.save()

        t2 = self.tw.tasks.get(uuid=t1['uuid'])
        self.assertEqual(t1 == t2, True)

    def test_compare_unsaved_tasks(self):
        # t1 and t2 are unsaved tasks, considered to be unequal
        # despite the content of data
        t1 = Task(self.tw, description='test task')
        t2 = Task(self.tw, description='test task')

        self.assertEqual(t1 == t2, False)

    def test_hash_unsaved_tasks(self):
        # Considered equal, it's the same object
        t1 = Task(self.tw, description='test task')
        t2 = t1
        self.assertEqual(hash(t1) == hash(t2), True)

    def test_hash_same_task(self):
        # Compare the hash of the task using two different objects
        t1 = Task(self.tw, description='test task')
        t1.save()

        t2 = self.tw.tasks.get(uuid=t1['uuid'])
        self.assertEqual(t1.__hash__(), t2.__hash__())

    def test_hash_unequal_unsaved_tasks(self):
        # Compare the hash of the task using two different objects
        t1 = Task(self.tw, description='test task 1')
        t2 = Task(self.tw, description='test task 2')

        self.assertNotEqual(t1.__hash__(), t2.__hash__())

    def test_hash_unequal_saved_tasks(self):
        # Compare the hash of the task using two different objects
        t1 = Task(self.tw, description='test task 1')
        t2 = Task(self.tw, description='test task 2')

        t1.save()
        t2.save()

        self.assertNotEqual(t1.__hash__(), t2.__hash__())

    def test_adding_task_with_priority(self):
        t = Task(self.tw, description='test task', priority='M')
        t.save()

    def test_removing_priority_with_none(self):
        t = Task(self.tw, description='test task', priority='L')
        t.save()

        # Remove the priority mark
        t['priority'] = None
        t.save()

        # Assert that priority is not there after saving
        self.assertEqual(t['priority'], None)

    def test_adding_task_with_due_time(self):
        t = Task(self.tw, description='test task', due=datetime.datetime.now())
        t.save()

    def test_removing_due_time_with_none(self):
        t = Task(self.tw, description='test task', due=datetime.datetime.now())
        t.save()

        # Remove the due timestamp
        t['due'] = None
        t.save()

        # Assert that due timestamp is no longer there
        self.assertEqual(t['due'], None)

    def test_modified_fields_new_task(self):
        t = Task(self.tw)

        # This should be empty with new task
        self.assertEqual(set(t._modified_fields), set())

        # Modify the task
        t['description'] = 'test task'
        self.assertEqual(set(t._modified_fields), set(['description']))

        t['due'] = datetime.datetime(2014, 2, 14, 14, 14, 14)  # <3
        self.assertEqual(set(t._modified_fields), set(['description', 'due']))

        t['project'] = 'test project'
        self.assertEqual(
            set(t._modified_fields),
            set(['description', 'due', 'project']),
        )

        # List of modified fields should clear out when saved
        t.save()
        self.assertEqual(set(t._modified_fields), set())

        # Reassigning the fields with the same values now should not produce
        # modified fields
        t['description'] = 'test task'
        t['due'] = datetime.datetime(2014, 2, 14, 14, 14, 14)  # <3
        t['project'] = 'test project'
        self.assertEqual(set(t._modified_fields), set())

    def test_modified_fields_loaded_task(self):
        t = Task(self.tw)

        # Modify the task
        t['description'] = 'test task'
        t['due'] = datetime.datetime(2014, 2, 14, 14, 14, 14)  # <3
        t['project'] = 'test project'

        dependency = Task(self.tw, description='dependency')
        dependency.save()
        t['depends'] = set([dependency])

        # List of modified fields should clear out when saved
        t.save()
        self.assertEqual(set(t._modified_fields), set())

        # Get the task by using a filter by UUID
        self.tw.tasks.get(uuid=t['uuid'])

        # Reassigning the fields with the same values now should not produce
        # modified fields
        t['description'] = 'test task'
        t['due'] = datetime.datetime(2014, 2, 14, 14, 14, 14)  # <3
        t['project'] = 'test project'
        t['depends'] = set([dependency])
        self.assertEqual(set(t._modified_fields), set())

    def test_modified_fields_not_affected_by_reading(self):
        t = Task(self.tw)

        for field in TASK_STANDARD_ATTRS:
            t[field]

        self.assertEqual(set(t._modified_fields), set())

    def test_setting_read_only_attrs_through_init(self):
        # Test that we are unable to set readonly attrs through __init__
        for readonly_key in Task.read_only_fields:
            kwargs = {'description': 'test task', readonly_key: 'value'}
            self.assertRaises(
                RuntimeError,
                lambda: Task(self.tw, **kwargs),
            )

    def test_setting_read_only_attrs_through_setitem(self):
        # Test that we are unable to set readonly attrs through __init__
        for readonly_key in Task.read_only_fields:
            t = Task(self.tw, description='test task')
            self.assertRaises(
                RuntimeError,
                lambda: t.__setitem__(readonly_key, 'value'),
            )

    def test_saving_unmodified_task(self):
        t = Task(self.tw, description='test task')
        t.save()
        t.save()

    def test_adding_tag_by_appending(self):
        t = Task(self.tw, description='test task', tags=['test1'])
        t.save()
        t['tags'].add('test2')
        t.save()
        self.assertEqual(t['tags'], set(['test1', 'test2']))

    def test_adding_tag_twice(self):
        t = Task(self.tw, description='test task', tags=['test1'])
        t.save()
        t['tags'].add('test2')
        t['tags'].add('test2')
        t.save()
        self.assertEqual(t['tags'], set(['test1', 'test2']))

    def test_adding_tag_by_appending_empty(self):
        t = Task(self.tw, description='test task')
        t.save()
        t['tags'].add('test')
        t.save()
        self.assertEqual(t['tags'], set(['test']))

    def test_serializers_returning_empty_string_for_none(self):
        # Test that any serializer returns '' when passed None
        t = Task(self.tw)
        serializers = [
            getattr(t, serializer_name)
            for serializer_name in filter(
                lambda x: x.startswith('serialize_'),
                dir(t),
            )
        ]
        for serializer in serializers:
            self.assertEqual(serializer(None), '')

    def test_deserializer_returning_empty_value_for_empty_string(self):
        # Test that any deserializer returns empty value when passed ''
        t = Task(self.tw)
        deserializers = [
            getattr(t, deserializer_name)
            for deserializer_name in filter(
                lambda x: x.startswith('deserialize_'),
                dir(t),
            )
        ]
        for deserializer in deserializers:
            self.assertTrue(deserializer('') in (None, [], set()))

    def test_normalizers_handling_none(self):
        # Test that any normalizer can handle None as a valid value
        t = Task(self.tw)

        for key in TASK_STANDARD_ATTRS:
            t._normalize(key, None)

    def test_recurrent_task_generation(self):
        today = datetime.date.today()
        t = Task(
            self.tw,
            description='brush teeth',
            due=today,
            recur='daily',
        )
        t.save()
        self.assertEqual(len(self.tw.tasks.pending()), 2)

    def test_spawned_task_parent(self):
        today = datetime.date.today()
        t = Task(
            self.tw,
            description='brush teeth',
            due=today,
            recur='daily',
        )
        t.save()

        spawned = self.tw.tasks.pending().get(due=today)
        assert spawned['parent'] == t

    def test_modify_number_of_tasks_at_once(self):
        for i in range(1, 100):
            Task(self.tw, description='test task %d' % i, tags=['test']).save()

        self.tw.execute_command(['+test', 'mod', 'unified', 'description'])

    def test_return_all_from_executed_command(self):
        Task(self.tw, description='test task', tags=['test']).save()
        out, err, rc = self.tw.execute_command(['count'], return_all=True)
        self.assertEqual(rc, 0)

    def test_return_all_from_failed_executed_command(self):
        Task(self.tw, description='test task', tags=['test']).save()
        out, err, rc = self.tw.execute_command(
            ['countinvalid'],
            return_all=True,
            allow_failure=False,
        )
        self.assertNotEqual(rc, 0)


class TaskFromHookTest(TasklibTest):

    input_add_data = six.StringIO(
        '{"description":"Buy some milk",'
        '"entry":"20141118T050231Z",'
        '"status":"pending",'
        '"start":"20141119T152233Z",'
        '"uuid":"a360fc44-315c-4366-b70c-ea7e7520b749"}',
    )

    input_add_data_recurring = six.StringIO(
        '{"description":"Mow the lawn",'
        '"entry":"20160210T224304Z",'
        '"parent":"62da6227-519c-42c2-915d-dccada926ad7",'
        '"recur":"weekly",'
        '"status":"pending",'
        '"uuid":"81305335-0237-49ff-8e87-b3cdc2369cec"}',
    )

    input_modify_data = six.StringIO(
        '\n'.join([
            input_add_data.getvalue(),
            (
                '{"description":"Buy some milk finally",'
                '"entry":"20141118T050231Z",'
                '"status":"completed",'
                '"uuid":"a360fc44-315c-4366-b70c-ea7e7520b749"}'
            ),
        ]),
    )

    exported_raw_data = (
        '{"project":"Home",'
        '"due":"20150101T232323Z",'
        '"description":"test task"}'
    )

    def test_setting_up_from_add_hook_input(self):
        t = Task.from_input(input_file=self.input_add_data, backend=self.tw)
        self.assertEqual(t['description'], 'Buy some milk')
        self.assertEqual(t.pending, True)

    def test_setting_up_from_add_hook_input_recurring(self):
        t = Task.from_input(
            input_file=self.input_add_data_recurring,
            backend=self.tw,
        )
        self.assertEqual(t['description'], 'Mow the lawn')
        self.assertEqual(t.pending, True)

    def test_setting_up_from_modified_hook_input(self):
        t = Task.from_input(
            input_file=self.input_modify_data,
            modify=True,
            backend=self.tw,
        )
        self.assertEqual(t['description'], 'Buy some milk finally')
        self.assertEqual(t.pending, False)
        self.assertEqual(t.completed, True)

        self.assertEqual(t._original_data['status'], 'pending')
        self.assertEqual(t._original_data['description'], 'Buy some milk')
        self.assertEqual(
            set(t._modified_fields),
            set(['status', 'description', 'start']),
        )

    def test_export_data(self):
        t = Task(
            self.tw,
            description='test task',
            project='Home',
            due=pytz.utc.localize(
                datetime.datetime(2015, 1, 1, 23, 23, 23)),
        )

        # Check that the output is a permutation of:
        # {"project":"Home","description":"test task","due":"20150101232323Z"}
        allowed_segments = self.exported_raw_data[1:-1].split(',')
        allowed_output = [
            '{' + ','.join(segments) + '}'
            for segments in itertools.permutations(allowed_segments)
        ]

        self.assertTrue(
            any(t.export_data() == expected
                for expected in allowed_output),
        )


class TimezoneAwareDatetimeTest(TasklibTest):

    def setUp(self):
        super(TimezoneAwareDatetimeTest, self).setUp()
        self.zone = local_zone
        self.localdate_naive = datetime.datetime(2015, 2, 2)
        self.localtime_naive = datetime.datetime(2015, 2, 2, 0, 0, 0)
        self.localtime_aware = self.zone.localize(self.localtime_naive)
        self.utctime_aware = self.localtime_aware.astimezone(pytz.utc)

    def test_timezone_naive_datetime_setitem(self):
        t = Task(self.tw, description='test task')
        t['due'] = self.localtime_naive
        self.assertEqual(t['due'], self.localtime_aware)

    def test_timezone_naive_datetime_using_init(self):
        t = Task(self.tw, description='test task', due=self.localtime_naive)
        self.assertEqual(t['due'], self.localtime_aware)

    def test_filter_by_naive_datetime(self):
        t = Task(self.tw, description='task1', due=self.localtime_naive)
        t.save()
        matching_tasks = self.tw.tasks.filter(due=self.localtime_naive)
        self.assertEqual(len(matching_tasks), 1)

    def test_serialize_naive_datetime(self):
        t = Task(self.tw, description='task1', due=self.localtime_naive)
        self.assertEqual(
            json.loads(t.export_data())['due'],
            self.utctime_aware.strftime(DATE_FORMAT),
        )

    def test_timezone_naive_date_setitem(self):
        t = Task(self.tw, description='test task')
        t['due'] = self.localdate_naive
        self.assertEqual(t['due'], self.localtime_aware)

    def test_timezone_naive_date_using_init(self):
        t = Task(self.tw, description='test task', due=self.localdate_naive)
        self.assertEqual(t['due'], self.localtime_aware)

    def test_filter_by_naive_date(self):
        t = Task(self.tw, description='task1', due=self.localdate_naive)
        t.save()
        matching_tasks = self.tw.tasks.filter(due=self.localdate_naive)
        self.assertEqual(len(matching_tasks), 1)

    def test_serialize_naive_date(self):
        t = Task(self.tw, description='task1', due=self.localdate_naive)
        self.assertEqual(
            json.loads(t.export_data())['due'],
            self.utctime_aware.strftime(DATE_FORMAT),
        )

    def test_timezone_aware_datetime_setitem(self):
        t = Task(self.tw, description='test task')
        t['due'] = self.localtime_aware
        self.assertEqual(t['due'], self.localtime_aware)

    def test_timezone_aware_datetime_using_init(self):
        t = Task(self.tw, description='test task', due=self.localtime_aware)
        self.assertEqual(t['due'], self.localtime_aware)

    def test_filter_by_aware_datetime(self):
        t = Task(self.tw, description='task1', due=self.localtime_aware)
        t.save()
        matching_tasks = self.tw.tasks.filter(due=self.localtime_aware)
        self.assertEqual(len(matching_tasks), 1)

    def test_serialize_aware_datetime(self):
        t = Task(self.tw, description='task1', due=self.localtime_aware)
        self.assertEqual(
            json.loads(t.export_data())['due'],
            self.utctime_aware.strftime(DATE_FORMAT),
        )


class DatetimeStringTest(TasklibTest):

    def test_simple_now_conversion(self):
        if self.tw.version < six.text_type('2.4.0'):
            # Python2.6 does not support SkipTest. As a workaround
            # mark the test as passed by exiting.
            if getattr(unittest, 'SkipTest', None) is not None:
                raise unittest.SkipTest()
            else:
                return

        t = Task(self.tw, description='test task', due='now')
        now = local_zone.localize(datetime.datetime.now())

        # Assert that both times are not more than 5 seconds apart
        if sys.version_info < (2, 7):
            self.assertTrue(total_seconds_2_6(now - t['due']) < 5)
            self.assertTrue(total_seconds_2_6(t['due'] - now) < 5)
        else:
            self.assertTrue((now - t['due']).total_seconds() < 5)
            self.assertTrue((t['due'] - now).total_seconds() < 5)

    def test_simple_eoy_conversion(self):
        if self.tw.version < six.text_type('2.4.0'):
            # Python2.6 does not support SkipTest. As a workaround
            # mark the test as passed by exiting.
            if getattr(unittest, 'SkipTest', None) is not None:
                raise unittest.SkipTest()
            else:
                return

        t = Task(self.tw, description='test task', due='eoy')
        now = local_zone.localize(datetime.datetime.now())
        eoy = local_zone.localize(datetime.datetime(
            year=now.year,
            month=12,
            day=31,
            hour=23,
            minute=59,
            second=59,
            ))
        self.assertEqual(eoy, t['due'])

    def test_complex_eoy_conversion(self):
        if self.tw.version < six.text_type('2.4.0'):
            # Python2.6 does not support SkipTest. As a workaround
            # mark the test as passed by exiting.
            if getattr(unittest, 'SkipTest', None) is not None:
                raise unittest.SkipTest()
            else:
                return

        t = Task(self.tw, description='test task', due='eoy - 4 months')
        now = local_zone.localize(datetime.datetime.now())
        due_date = local_zone.localize(
            datetime.datetime(
                year=now.year,
                month=12,
                day=31,
                hour=23,
                minute=59,
                second=59,
            )
        ) - datetime.timedelta(0, 4 * 30 * 86400)
        self.assertEqual(due_date, t['due'])

    def test_filtering_with_string_datetime(self):
        if self.tw.version < six.text_type('2.4.0'):
            # Python2.6 does not support SkipTest. As a workaround
            # mark the test as passed by exiting.
            if getattr(unittest, 'SkipTest', None) is not None:
                raise unittest.SkipTest()
            else:
                return

        t = Task(
            self.tw,
            description='test task',
            due=datetime.datetime.now() - datetime.timedelta(0, 2),
        )
        t.save()
        self.assertEqual(len(self.tw.tasks.filter(due__before='now')), 1)


class AnnotationTest(TasklibTest):

    def setUp(self):
        super(AnnotationTest, self).setUp()
        Task(self.tw, description='test task').save()

    def test_adding_annotation(self):
        task = self.tw.tasks.get()
        task.add_annotation('test annotation')
        self.assertEqual(len(task['annotations']), 1)
        ann = task['annotations'][0]
        self.assertEqual(ann['description'], 'test annotation')

    def test_removing_annotation(self):
        task = self.tw.tasks.get()
        task.add_annotation('test annotation')
        ann = task['annotations'][0]
        ann.remove()
        self.assertEqual(len(task['annotations']), 0)

    def test_removing_annotation_by_description(self):
        task = self.tw.tasks.get()
        task.add_annotation('test annotation')
        task.remove_annotation('test annotation')
        self.assertEqual(len(task['annotations']), 0)

    def test_removing_annotation_by_obj(self):
        task = self.tw.tasks.get()
        task.add_annotation('test annotation')
        ann = task['annotations'][0]
        task.remove_annotation(ann)
        self.assertEqual(len(task['annotations']), 0)

    def test_annotation_after_modification(self):
        task = self.tw.tasks.get()
        task['project'] = 'test'
        task.add_annotation('I should really do this task')
        self.assertEqual(task['project'], 'test')
        task.save()
        self.assertEqual(task['project'], 'test')

    def test_serialize_annotations(self):
        # Test that serializing annotations is possible
        t = Task(self.tw, description='test')
        t.save()

        t.add_annotation('annotation1')
        t.add_annotation('annotation2')

        data = t._serialize('annotations', t._data['annotations'])

        self.assertEqual(len(data), 2)
        self.assertEqual(type(data[0]), dict)
        self.assertEqual(type(data[1]), dict)

        self.assertEqual(data[0]['description'], 'annotation1')
        self.assertEqual(data[1]['description'], 'annotation2')


class UnicodeTest(TasklibTest):

    def test_unicode_task(self):
        Task(self.tw, description=six.u('†åßk')).save()
        self.tw.tasks.get()

    def test_filter_by_unicode_task(self):
        Task(self.tw, description=six.u('†åßk')).save()
        tasks = self.tw.tasks.filter(description=six.u('†åßk'))
        self.assertEqual(len(tasks), 1)

    def test_non_unicode_task(self):
        Task(self.tw, description='test task').save()
        self.tw.tasks.get()


class ReadOnlyDictViewTest(unittest.TestCase):

    def setUp(self):
        self.sample = dict(sample_list=[1, 2, 3], sample_dict={'key': 'value'})
        self.original_sample = copy.deepcopy(self.sample)
        self.view = ReadOnlyDictView(self.sample)

    def test_readonlydictview_getitem(self):
        sample_list = self.view['sample_list']
        self.assertEqual(sample_list, self.sample['sample_list'])

        # Assert that modification changed only copied value
        sample_list.append(4)
        self.assertNotEqual(sample_list, self.sample['sample_list'])

        # Assert that viewed dict is not changed
        self.assertEqual(self.sample, self.original_sample)

    def test_readonlydictview_contains(self):
        self.assertEqual('sample_list' in self.view,
                         'sample_list' in self.sample)
        self.assertEqual('sample_dict' in self.view,
                         'sample_dict' in self.sample)
        self.assertEqual('key' in self.view, 'key' in self.sample)

        # Assert that viewed dict is not changed
        self.assertEqual(self.sample, self.original_sample)

    def test_readonlydictview_iter(self):
        self.assertEqual(
            list(key for key in self.view),
            list(key for key in self.sample),
        )

        # Assert the view is correct after modification
        self.sample['new'] = 'value'
        self.assertEqual(
            list(key for key in self.view),
            list(key for key in self.sample),
        )

    def test_readonlydictview_len(self):
        self.assertEqual(len(self.view), len(self.sample))

        # Assert the view is correct after modification
        self.sample['new'] = 'value'
        self.assertEqual(len(self.view), len(self.sample))

    def test_readonlydictview_get(self):
        sample_list = self.view.get('sample_list')
        self.assertEqual(sample_list, self.sample.get('sample_list'))

        # Assert that modification changed only copied value
        sample_list.append(4)
        self.assertNotEqual(sample_list, self.sample.get('sample_list'))

        # Assert that viewed dict is not changed
        self.assertEqual(self.sample, self.original_sample)

    def test_readonlydict_items(self):
        view_items = self.view.items()
        sample_items = list(self.sample.items())
        self.assertEqual(view_items, sample_items)

        view_items.append('newkey')
        self.assertNotEqual(view_items, sample_items)
        self.assertEqual(self.sample, self.original_sample)

    def test_readonlydict_values(self):
        view_values = self.view.values()
        sample_values = list(self.sample.values())
        self.assertEqual(view_values, sample_values)

        view_list_item = list(filter(lambda x: type(x) is list,
                                     view_values))[0]
        view_list_item.append(4)
        self.assertNotEqual(view_values, sample_values)
        self.assertEqual(self.sample, self.original_sample)


class LazyUUIDTaskTest(TasklibTest):

    def setUp(self):
        super(LazyUUIDTaskTest, self).setUp()

        self.stored = Task(self.tw, description='this is test task')
        self.stored.save()

        self.lazy = LazyUUIDTask(self.tw, self.stored['uuid'])

    def test_uuid_non_conversion(self):
        assert self.stored['uuid'] == self.lazy['uuid']
        assert type(self.lazy) is LazyUUIDTask

    def test_lazy_explicit_conversion(self):
        assert type(self.lazy) is LazyUUIDTask
        self.lazy.replace()
        assert type(self.lazy) is Task

    def test_conversion_key(self):
        assert self.stored['description'] == self.lazy['description']
        assert type(self.lazy) is Task

    def test_conversion_attribute(self):
        assert type(self.lazy) is LazyUUIDTask
        assert self.lazy.completed is False
        assert type(self.lazy) is Task

    def test_normal_to_lazy_equality(self):
        assert self.stored == self.lazy
        assert not self.stored != self.lazy
        assert type(self.lazy) is LazyUUIDTask

    def test_lazy_to_lazy_equality(self):
        lazy1 = LazyUUIDTask(self.tw, self.stored['uuid'])
        lazy2 = LazyUUIDTask(self.tw, self.stored['uuid'])

        assert lazy1 == lazy2
        assert not lazy1 != lazy2
        assert type(lazy1) is LazyUUIDTask
        assert type(lazy2) is LazyUUIDTask

    def test_normal_to_lazy_inequality(self):
        # Create a different UUID by changing the last letter
        wrong_uuid = self.stored['uuid']
        wrong_uuid = wrong_uuid[:-1] + ('a' if wrong_uuid[-1] != 'a' else 'b')

        wrong_lazy = LazyUUIDTask(self.tw, wrong_uuid)

        assert not self.stored == wrong_lazy
        assert self.stored != wrong_lazy
        assert type(wrong_lazy) is LazyUUIDTask

    def test_lazy_to_lazy_inequality(self):
        # Create a different UUID by changing the last letter
        wrong_uuid = self.stored['uuid']
        wrong_uuid = wrong_uuid[:-1] + ('a' if wrong_uuid[-1] != 'a' else 'b')

        lazy1 = LazyUUIDTask(self.tw, self.stored['uuid'])
        lazy2 = LazyUUIDTask(self.tw, wrong_uuid)

        assert not lazy1 == lazy2
        assert lazy1 != lazy2
        assert type(lazy1) is LazyUUIDTask
        assert type(lazy2) is LazyUUIDTask

    def test_lazy_in_queryset(self):
        tasks = self.tw.tasks.filter(uuid=self.stored['uuid'])

        assert self.lazy in tasks
        assert type(self.lazy) is LazyUUIDTask

    def test_lazy_saved(self):
        assert self.lazy.saved is True

    def test_lazy_modified(self):
        assert self.lazy.modified is False

    def test_lazy_modified_fields(self):
        assert self.lazy._modified_fields == set()


class LazyUUIDTaskSetTest(TasklibTest):

    def setUp(self):
        super(LazyUUIDTaskSetTest, self).setUp()

        self.task1 = Task(self.tw, description='task 1')
        self.task2 = Task(self.tw, description='task 2')
        self.task3 = Task(self.tw, description='task 3')

        self.task1.save()
        self.task2.save()
        self.task3.save()

        self.uuids = (
            self.task1['uuid'],
            self.task2['uuid'],
            self.task3['uuid'],
        )

        self.lazy = LazyUUIDTaskSet(self.tw, self.uuids)

    def test_length(self):
        assert len(self.lazy) == 3
        assert type(self.lazy) is LazyUUIDTaskSet

    def test_contains(self):
        assert self.task1 in self.lazy
        assert self.task2 in self.lazy
        assert self.task3 in self.lazy
        assert type(self.lazy) is LazyUUIDTaskSet

    def test_eq_lazy(self):
        new_lazy = LazyUUIDTaskSet(self.tw, self.uuids)
        assert self.lazy == new_lazy
        assert not self.lazy != new_lazy
        assert type(self.lazy) is LazyUUIDTaskSet

    def test_eq_real(self):
        assert self.lazy == self.tw.tasks.all()
        assert self.tw.tasks.all() == self.lazy
        assert not self.lazy != self.tw.tasks.all()

        assert type(self.lazy) is LazyUUIDTaskSet

    def test_union(self):
        taskset = set([self.task1])
        lazyset = LazyUUIDTaskSet(
            self.tw,
            (self.task2['uuid'], self.task3['uuid']),
        )

        assert taskset | lazyset == self.lazy
        assert lazyset | taskset == self.lazy
        assert taskset.union(lazyset) == self.lazy
        assert lazyset.union(taskset) == self.lazy

        lazyset |= taskset
        assert lazyset == self.lazy

    def test_difference(self):
        taskset = set([self.task1, self.task2])
        lazyset = LazyUUIDTaskSet(
            self.tw,
            (self.task2['uuid'], self.task3['uuid']),
        )

        assert taskset - lazyset == set([self.task1])
        assert lazyset - taskset == set([self.task3])
        assert taskset.difference(lazyset) == set([self.task1])
        assert lazyset.difference(taskset) == set([self.task3])

        lazyset -= taskset
        assert lazyset == set([self.task3])

    def test_symmetric_difference(self):
        taskset = set([self.task1, self.task2])
        lazyset = LazyUUIDTaskSet(
            self.tw,
            (self.task2['uuid'], self.task3['uuid']),
        )

        assert taskset ^ lazyset == set([self.task1, self.task3])
        assert lazyset ^ taskset == set([self.task1, self.task3])
        self.assertEqual(
            taskset.symmetric_difference(lazyset),
            set([self.task1, self.task3]),
        )
        self.assertEqual(
            lazyset.symmetric_difference(taskset),
            set([self.task1, self.task3]),
        )

        lazyset ^= taskset
        assert lazyset == set([self.task1, self.task3])

    def test_intersection(self):
        taskset = set([self.task1, self.task2])
        lazyset = LazyUUIDTaskSet(
            self.tw,
            (self.task2['uuid'], self.task3['uuid']),
        )

        assert taskset & lazyset == set([self.task2])
        assert lazyset & taskset == set([self.task2])
        assert taskset.intersection(lazyset) == set([self.task2])
        assert lazyset.intersection(taskset) == set([self.task2])

        lazyset &= taskset
        assert lazyset == set([self.task2])


class TaskWarriorBackendTest(TasklibTest):

    def test_config(self):
        assert self.tw.config['nag'] == 'You have more urgent tasks.'
        assert self.tw.config['default.command'] == 'next'
        assert self.tw.config['dependency.indicator'] == 'D'
