import shutil
import tempfile
import unittest
import uuid

from .task import TaskWarrior


class TasklibTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
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
