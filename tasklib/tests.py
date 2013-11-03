import shutil
import tempfile
import unittest

from .task import TaskWarrior


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
        self.tw.execute_command(['add', 'test task'])
        self.assertEqual(len(self.tw.tasks.all()), 1)
        self.assertEqual(self.tw.tasks.all()[0]['description'], 'test task')
        self.assertEqual(self.tw.tasks.all()[0]['status'], 'pending')

    def test_pending_non_empty(self):
        self.tw.execute_command(['add', 'test task'])
        self.assertEqual(len(self.tw.tasks.pending()), 1)
        self.assertEqual(self.tw.tasks.pending()[0]['description'],
                         'test task')
        self.assertEqual(self.tw.tasks.pending()[0]['status'], 'pending')

    def test_completed_empty(self):
        self.tw.execute_command(['add', 'test task'])
        self.assertEqual(len(self.tw.tasks.completed()), 0)

    def test_completed_non_empty(self):
        self.tw.execute_command(['add', 'test task'])
        self.assertEqual(len(self.tw.tasks.completed()), 0)
        self.tw.tasks.all()[0].done()
        self.assertEqual(len(self.tw.tasks.completed()), 1)
