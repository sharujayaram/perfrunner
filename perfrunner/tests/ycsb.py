import os

from perfrunner.helpers import local
from perfrunner.helpers.cbmonitor import with_stats
from perfrunner.helpers.worker import ycsb_data_load_task, ycsb_task
from perfrunner.tests import PerfTest
from perfrunner.tests.n1ql import N1QLTest


class YCSBTest(PerfTest):

    def download_ycsb(self):
        if self.worker_manager.is_remote:
            self.remote.clone_ycsb(repo=self.test_config.ycsb_settings.repo,
                                   branch=self.test_config.ycsb_settings.branch,
                                   worker_home=self.worker_manager.WORKER_HOME)
        else:
            local.clone_ycsb(repo=self.test_config.ycsb_settings.repo,
                             branch=self.test_config.ycsb_settings.branch)

    def collect_export_files(self):
        if self.worker_manager.is_remote:
            os.mkdir('YCSB')
            self.remote.get_export_files(self.worker_manager.WORKER_HOME)

    def load(self, *args, **kwargs):
        PerfTest.load(self, task=ycsb_data_load_task)

    @with_stats
    def access(self, *args, **kwargs):
        PerfTest.access(self, task=ycsb_task)

    def run(self):
        self.download_ycsb()

        self.load()
        self.wait_for_persistence()
        self.check_num_items()

        self.access()

        self.report_kpi()


class YCSBThroughputTest(YCSBTest):

    def _report_kpi(self):
        self.collect_export_files()

        self.reporter.post(
            *self.metrics.ycsb_throughput()
        )


class YCSBSOETest(YCSBThroughputTest):

    def restore(self):
        self.remote.restore_without_index(
            self.test_config.restore_settings.backup_storage,
            self.test_config.restore_settings.backup_repo,
        )
        self.wait_for_persistence()

    def run(self):
        self.download_ycsb()
        self.restore()
        self.index.build(one_index_per_bucket=False)
        self.load()
        self.access()
        self.report_kpi()


class YCSBN1QLTest(YCSBTest, N1QLTest):

    def run(self):
        self.download_ycsb()

        self.load()
        self.wait_for_persistence()
        self.check_num_items()

        self.build_index()

        self.access()

        self.report_kpi()


class YCSBN1QLThroughputTest(YCSBN1QLTest, YCSBThroughputTest):

    pass
