# coding=utf-8

import datetime
import shutil
import tempfile
import unittest

from .task import TaskWarrior, Task


class TasklibTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir='.')
        self.tw = TaskWarrior(data_location=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TaskFilterTest(TasklibTest):

    def test_all_empty(self):
        self.assertEqual(len(self.tw.tasks.all()), 0)

    def test_all_non_empty(self):
        Task(self.tw, description="test task").save()
        self.assertEqual(len(self.tw.tasks.all()), 1)
        self.assertEqual(self.tw.tasks.all()[0]['description'], 'test task')
        self.assertEqual(self.tw.tasks.all()[0]['status'], 'pending')

    def test_pending_non_empty(self):
        Task(self.tw, description="test task").save()
        self.assertEqual(len(self.tw.tasks.pending()), 1)
        self.assertEqual(self.tw.tasks.pending()[0]['description'],
                         'test task')
        self.assertEqual(self.tw.tasks.pending()[0]['status'], 'pending')

    def test_completed_empty(self):
        Task(self.tw, description="test task").save()
        self.assertEqual(len(self.tw.tasks.completed()), 0)

    def test_completed_non_empty(self):
        Task(self.tw, description="test task").save()
        self.assertEqual(len(self.tw.tasks.completed()), 0)
        self.tw.tasks.all()[0].done()
        self.assertEqual(len(self.tw.tasks.completed()), 1)

    def test_filtering_by_attribute(self):
        Task(self.tw, description="no priority task").save()
        Task(self.tw, priority="H", description="high priority task").save()
        self.assertEqual(len(self.tw.tasks.all()), 2)

        # Assert that the correct number of tasks is returned
        self.assertEqual(len(self.tw.tasks.filter(priority="H")), 1)

        # Assert that the correct tasks are returned
        high_priority_task = self.tw.tasks.get(priority="H")
        self.assertEqual(high_priority_task['description'], "high priority task")

    def test_filtering_by_empty_attribute(self):
        Task(self.tw, description="no priority task").save()
        Task(self.tw, priority="H", description="high priority task").save()
        self.assertEqual(len(self.tw.tasks.all()), 2)

        # Assert that the correct number of tasks is returned
        self.assertEqual(len(self.tw.tasks.filter(priority=None)), 1)

        # Assert that the correct tasks are returned
        no_priority_task = self.tw.tasks.get(priority=None)
        self.assertEqual(no_priority_task['description'], "no priority task")

    def test_filter_for_task_with_space_in_descripition(self):
        task = Task(self.tw, description="test task")
        task.save()

        filtered_task = self.tw.tasks.get(description="test task")
        self.assertEqual(filtered_task['description'], "test task")

    def test_filter_for_task_without_space_in_descripition(self):
        task = Task(self.tw, description="test")
        task.save()

        filtered_task = self.tw.tasks.get(description="test")
        self.assertEqual(filtered_task['description'], "test")

    def test_filter_for_task_with_space_in_project(self):
        task = Task(self.tw, description="test", project="random project")
        task.save()

        filtered_task = self.tw.tasks.get(project="random project")
        self.assertEqual(filtered_task['project'], "random project")

    def test_filter_for_task_without_space_in_project(self):
        task = Task(self.tw, description="test", project="random")
        task.save()

        filtered_task = self.tw.tasks.get(project="random")
        self.assertEqual(filtered_task['project'], "random")


class TaskTest(TasklibTest):

    def test_create_unsaved_task(self):
        # Make sure a new task is not saved unless explicitly called for
        t = Task(self.tw, description="test task")
        self.assertEqual(len(self.tw.tasks.all()), 0)

    # TODO: once python 2.6 compatiblity is over, use context managers here
    #       and in all subsequent tests for assertRaises

    def test_delete_unsaved_task(self):
        t = Task(self.tw, description="test task")
        self.assertRaises(Task.NotSaved, t.delete)

    def test_complete_unsaved_task(self):
        t = Task(self.tw, description="test task")
        self.assertRaises(Task.NotSaved, t.done)

    def test_refresh_unsaved_task(self):
        t = Task(self.tw, description="test task")
        self.assertRaises(Task.NotSaved, t.refresh)

    def test_delete_deleted_task(self):
        t = Task(self.tw, description="test task")
        t.save()
        t.delete()

        self.assertRaises(Task.DeletedTask, t.delete)

    def test_complete_completed_task(self):
        t = Task(self.tw, description="test task")
        t.save()
        t.done()

        self.assertRaises(Task.CompletedTask, t.done)

    def test_complete_deleted_task(self):
        t = Task(self.tw, description="test task")
        t.save()
        t.delete()

        self.assertRaises(Task.DeletedTask, t.done)

    def test_modify_simple_attribute_without_space(self):
        t = Task(self.tw, description="test")
        t.save()

        self.assertEquals(t['description'], "test")

        t['description'] = "test-modified"
        t.save()

        self.assertEquals(t['description'], "test-modified")

    def test_modify_simple_attribute_with_space(self):
        # Space can pose problems with parsing
        t = Task(self.tw, description="test task")
        t.save()

        self.assertEquals(t['description'], "test task")

        t['description'] = "test task modified"
        t.save()

        self.assertEquals(t['description'], "test task modified")

    def test_empty_dependency_set_of_unsaved_task(self):
        t = Task(self.tw, description="test task")
        self.assertEqual(t['depends'], set())

    def test_empty_dependency_set_of_saved_task(self):
        t = Task(self.tw, description="test task")
        t.save()
        self.assertEqual(t['depends'], set())

    def test_set_unsaved_task_as_dependency(self):
        # Adds only one dependency to task with no dependencies
        t = Task(self.tw, description="test task")
        dependency = Task(self.tw, description="needs to be done first")

        # We only save the parent task, dependency task is unsaved
        t.save()

        self.assertRaises(Task.NotSaved,
                          t.__setitem__, 'depends', set([dependency]))

    def test_set_simple_dependency_set(self):
        # Adds only one dependency to task with no dependencies
        t = Task(self.tw, description="test task")
        dependency = Task(self.tw, description="needs to be done first")

        t.save()
        dependency.save()

        t['depends'] = set([dependency])

        self.assertEqual(t['depends'], set([dependency]))

    def test_set_complex_dependency_set(self):
        # Adds two dependencies to task with no dependencies
        t = Task(self.tw, description="test task")
        dependency1 = Task(self.tw, description="needs to be done first")
        dependency2 = Task(self.tw, description="needs to be done second")

        t.save()
        dependency1.save()
        dependency2.save()

        t['depends'] = set([dependency1, dependency2])

        self.assertEqual(t['depends'], set([dependency1, dependency2]))

    def test_remove_from_dependency_set(self):
        # Removes dependency from task with two dependencies
        t = Task(self.tw, description="test task")
        dependency1 = Task(self.tw, description="needs to be done first")
        dependency2 = Task(self.tw, description="needs to be done second")

        dependency1.save()
        dependency2.save()

        t['depends'] = set([dependency1, dependency2])
        t.save()

        t['depends'] = t['depends'] - set([dependency2])
        t.save()

        self.assertEqual(t['depends'], set([dependency1]))

    def test_add_to_dependency_set(self):
        # Adds dependency to task with one dependencies
        t = Task(self.tw, description="test task")
        dependency1 = Task(self.tw, description="needs to be done first")
        dependency2 = Task(self.tw, description="needs to be done second")

        dependency1.save()
        dependency2.save()

        t['depends'] = set([dependency1])
        t.save()

        t['depends'] = t['depends'] | set([dependency2])
        t.save()

        self.assertEqual(t['depends'], set([dependency1, dependency2]))

    def test_simple_dependency_set_save_repeatedly(self):
        # Adds only one dependency to task with no dependencies
        t = Task(self.tw, description="test task")
        dependency = Task(self.tw, description="needs to be done first")
        dependency.save()

        t['depends'] = set([dependency])
        t.save()

        # We taint the task, but keep depends intact
        t['description'] = "test task modified"
        t.save()

        self.assertEqual(t['depends'], set([dependency]))

        # We taint the task, but assign the same set to the depends
        t['depends'] = set([dependency])
        t['description'] = "test task modified again"
        t.save()

        self.assertEqual(t['depends'], set([dependency]))

    def test_compare_different_tasks(self):
        # Negative: compare two different tasks
        t1 = Task(self.tw, description="test task")
        t2 = Task(self.tw, description="test task")

        t1.save()
        t2.save()

        self.assertEqual(t1 == t2, False)

    def test_compare_same_task_object(self):
        # Compare Task object wit itself
        t = Task(self.tw, description="test task")
        t.save()

        self.assertEqual(t == t, True)

    def test_compare_same_task(self):
        # Compare the same task using two different objects
        t1 = Task(self.tw, description="test task")
        t1.save()

        t2 = self.tw.tasks.get(uuid=t1['uuid'])
        self.assertEqual(t1 == t2, True)

    def test_compare_unsaved_tasks(self):
        # t1 and t2 are unsaved tasks, considered to be unequal
        # despite the content of data
        t1 = Task(self.tw, description="test task")
        t2 = Task(self.tw, description="test task")

        self.assertEqual(t1 == t2, False)

    def test_hash_unsaved_tasks(self):
        # Considered equal, it's the same object
        t1 = Task(self.tw, description="test task")
        t2 = t1
        self.assertEqual(hash(t1) == hash(t2), True)

    def test_hash_same_task(self):
        # Compare the hash of the task using two different objects
        t1 = Task(self.tw, description="test task")
        t1.save()

        t2 = self.tw.tasks.get(uuid=t1['uuid'])
        self.assertEqual(t1.__hash__(), t2.__hash__())

    def test_adding_task_with_priority(self):
        t = Task(self.tw, description="test task", priority="M")
        t.save()

    def test_removing_priority_with_none(self):
        t = Task(self.tw, description="test task", priority="L")
        t.save()

        # Remove the priority mark
        t['priority'] = None
        t.save()

        # Assert that priority is not there after saving
        self.assertEqual(t['priority'], None)

    def test_adding_task_with_due_time(self):
        t = Task(self.tw, description="test task", due=datetime.datetime.now())
        t.save()

    def test_removing_due_time_with_none(self):
        t = Task(self.tw, description="test task", due=datetime.datetime.now())
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
        t['description'] = "test task"
        self.assertEqual(set(t._modified_fields), set(['description']))

        t['due'] = datetime.datetime(2014, 2, 14, 14, 14, 14)  # <3
        self.assertEqual(set(t._modified_fields), set(['description', 'due']))

        t['project'] = "test project"
        self.assertEqual(set(t._modified_fields),
                         set(['description', 'due', 'project']))

        # List of modified fields should clear out when saved
        t.save()
        self.assertEqual(set(t._modified_fields), set())

        # Reassigning the fields with the same values now should not produce
        # modified fields
        t['description'] = "test task"
        t['due'] = datetime.datetime(2014, 2, 14, 14, 14, 14)  # <3
        t['project'] = "test project"
        self.assertEqual(set(t._modified_fields), set())

    def test_modified_fields_loaded_task(self):
        t = Task(self.tw)

        # Modify the task
        t['description'] = "test task"
        t['due'] = datetime.datetime(2014, 2, 14, 14, 14, 14)  # <3
        t['project'] = "test project"

        dependency = Task(self.tw, description="dependency")
        dependency.save()
        t['depends'] = set([dependency])

        # List of modified fields should clear out when saved
        t.save()
        self.assertEqual(set(t._modified_fields), set())

        # Get the task by using a filter by UUID
        t2 = self.tw.tasks.get(uuid=t['uuid'])

        # Reassigning the fields with the same values now should not produce
        # modified fields
        t['description'] = "test task"
        t['due'] = datetime.datetime(2014, 2, 14, 14, 14, 14)  # <3
        t['project'] = "test project"
        t['depends'] = set([dependency])
        self.assertEqual(set(t._modified_fields), set())

    def test_setting_read_only_attrs_through_init(self):
        # Test that we are unable to set readonly attrs through __init__
        for readonly_key in Task.read_only_fields:
            kwargs = {'description': 'test task', readonly_key: 'value'}
            self.assertRaises(RuntimeError,
                              lambda: Task(self.tw, **kwargs))

    def test_setting_read_only_attrs_through_setitem(self):
        # Test that we are unable to set readonly attrs through __init__
        for readonly_key in Task.read_only_fields:
            t = Task(self.tw, description='test task')
            self.assertRaises(RuntimeError,
                              lambda: t.__setitem__(readonly_key, 'value'))


class AnnotationTest(TasklibTest):

    def setUp(self):
        super(AnnotationTest, self).setUp()
        Task(self.tw, description="test task").save()

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


class UnicodeTest(TasklibTest):

    def test_unicode_task(self):
        Task(self.tw, description="†åßk").save()
        self.tw.tasks.get()

    def test_non_unicode_task(self):
        Task(self.tw, description="test task").save()
        self.tw.tasks.get()
