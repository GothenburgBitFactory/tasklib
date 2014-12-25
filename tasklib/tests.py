# coding=utf-8

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
