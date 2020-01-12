import glob
import os
import shutil
import time

from logger import logger
from perfrunner.helpers import local
from perfrunner.helpers.cbmonitor import with_stats
from perfrunner.helpers.profiler import with_profiles
from perfrunner.helpers.worker import ycsb_data_load_task, ycsb_task
from perfrunner.tests import PerfTest
from perfrunner.tests.n1ql import N1QLTest

from perfrunner.helpers import local
from perfrunner.helpers.cluster import ClusterManager
from perfrunner.helpers.memcached import MemcachedHelper
from perfrunner.helpers.metrics import MetricHelper
from perfrunner.helpers.misc import pretty_dict, read_json
from perfrunner.helpers.monitor import Monitor
from perfrunner.helpers.profiler import Profiler
from perfrunner.helpers.remote import RemoteHelper
from perfrunner.helpers.reporter import ShowFastReporter
from perfrunner.helpers.rest import RestHelper
from perfrunner.helpers.worker import  WorkerManager
from perfrunner.settings import (
    ClusterSpec,
    PhaseSettings,
    TargetIterator,
    TestConfig,
)


class MongoTest(PerfTest):

    def __init__(self,
                 cluster_spec: ClusterSpec,
                 test_config: TestConfig,
                 verbose: bool):
        print('entererd mongo test init phase')
        self.cluster_spec = cluster_spec
        self.test_config = test_config

        self.target_iterator = TargetIterator(cluster_spec, test_config)

        self.cluster = ClusterManager(cluster_spec, test_config)
        self.memcached = MemcachedHelper(test_config)
        self.monitor = Monitor(cluster_spec, test_config, verbose)
        self.rest = RestHelper(cluster_spec)
        self.remote = RemoteHelper(cluster_spec, verbose)
        self.profiler = Profiler(cluster_spec, test_config)

        self.master_node = next(cluster_spec.masters)

        self.metrics = MetricHelper(self)

        self.cbmonitor_snapshots = []
        self.cbmonitor_clusters = []

        if self.test_config.test_case.use_workers:
            self.worker_manager = WorkerManager(cluster_spec, test_config,
                                                verbose)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type == KeyboardInterrupt:
            logger.warn('The test was interrupted')
            return True

    def download_ycsb(self):
        if self.worker_manager.is_remote:
            self.remote.init_ycsb(repo=self.test_config.ycsb_settings.repo,
                                  branch=self.test_config.ycsb_settings.branch,
                                  worker_home=self.worker_manager.WORKER_HOME,
                                  sdk_version=self.test_config.ycsb_settings.sdk_version)
        else:
            local.clone_git_repo(repo=self.test_config.ycsb_settings.repo,
                                 branch=self.test_config.ycsb_settings.branch)

    def collect_export_files(self):
        if self.worker_manager.is_remote:
            shutil.rmtree("YCSB", ignore_errors=True)
            os.mkdir('YCSB')
            self.remote.get_export_files(self.worker_manager.WORKER_HOME)

    def load(self, *args, **kwargs):
        PerfTest.load(self, task=ycsb_data_load_task)

    def access(self, *args, **kwargs):
        PerfTest.access(self, task=ycsb_task)

    def access_bg(self, *args, **kwargs):
        PerfTest.access_bg(self, task=ycsb_task)

    def collect_cb(self):
        duration = self.test_config.access_settings.time
        self.cb_start = duration*0.6
        time.sleep(self.cb_start)
        start_time = time.time()
        self.remote.collect_info()
        end_time = time.time()
        self.cb_time = round(end_time - start_time)
        self.worker_manager.wait_for_workers()

    def generate_keystore(self):
        if self.worker_manager.is_remote:
            self.remote.generate_ssl_keystore(self.ROOT_CERTIFICATE,
                                              self.test_config.access_settings
                                              .ssl_keystore_file,
                                              self.test_config.access_settings
                                              .ssl_keystore_password,
                                              self.worker_manager.WORKER_HOME)
        else:
            local.generate_ssl_keystore(self.ROOT_CERTIFICATE,
                                        self.test_config.access_settings.ssl_keystore_file,
                                        self.test_config.access_settings.ssl_keystore_password)

    def _report_kpi(self):
        self.collect_export_files()

        self.reporter.post(
            *self.metrics.ycsb_throughput()
        )

    def parse_ycsb_throughput(self) -> int:
        throughput = 0
        ycsb_log_files = [filename
                          for filename in glob.glob("YCSB/ycsb_run_*.log")
                          if "stderr" not in filename]
        for filename in ycsb_log_files:
            with open(filename) as fh:
                for line in fh.readlines():
                    if line.startswith('[OVERALL], Throughput(ops/sec)'):
                        throughput += int(float(line.split()[-1]))
                        break
        return throughput

    def run(self):
        print('entered mongoTest')

        self.download_ycsb()

        self.load()

        self.access()

        self.collect_export_files()

        throughput = self.parse_ycsb_throughput()
        print(throughput)

        self.remote.flush_iptables()
        self.tear_down()
