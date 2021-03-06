# -*- encoding: utf-8 -*-

from globaleaks import models
from globaleaks.jobs.base import LoopingJob
from globaleaks.orm import transact

from globaleaks.tests import helpers

class LoopingJobX(LoopingJob):
    interval = 2
    operation_called = 0

    def run(self):
        self.operation_called += 1

class TestLoopingJob(helpers.TestGL):
    def test_base_scheduler(self):
        """
        This function asseses the functionalities of a scheduler in calling
        the run() function periodically.
        """
        job = LoopingJobX()

        job.schedule()

        self.assertEqual(job.operation_called, 0)

        self.test_reactor.advance(1)

        self.assertEqual(job.operation_called, 1)

        self.test_reactor.advance(1)

        self.assertEqual(job.operation_called, 1)

        for i in range(2, 10):
            self.test_reactor.advance(2)
            self.assertEqual(job.operation_called, i)

        job.stop()


@transact
def get_scheduled_email_count(store):
    """Returns the number of mails scheduled in db"""
    return store.find(models.Mail).count()
