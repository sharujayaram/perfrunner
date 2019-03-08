import os
import shutil
import glob
import copy
import time
import re
from multiprocessing import Pool
import multiprocessing

from perfrunner.helpers.cbmonitor import with_stats, timeit
from perfrunner.tests import PerfTest
from perfrunner.helpers.worker import syncgateway_task_init_users, syncgateway_task_load_users, \
    syncgateway_task_load_docs, syncgateway_task_run_test, syncgateway_task_start_memcached, \
    syncgateway_task_grant_access

from perfrunner.helpers import local

from typing import Callable

from logger import logger

from decorator import decorator

from perfrunner.helpers.memcached import MemcachedHelper
from perfrunner.helpers.metrics import MetricHelper
from perfrunner.helpers.misc import pretty_dict
from perfrunner.helpers.remote import RemoteHelper
from perfrunner.helpers.reporter import ShowFastReporter
from perfrunner.helpers.worker import  WorkerManager
from perfrunner.helpers.profiler import Profiler, with_profiles
from perfrunner.helpers.cluster import ClusterManager
from perfrunner.helpers.rest import RestHelper
from perfrunner.helpers.monitor import Monitor

from perfrunner.settings import (
    ClusterSpec,
    PhaseSettings,
    TargetIterator,
    TestConfig,
)


@decorator
def with_timer(cblite_replicate, *args, **kwargs):
    test = args[0]

    t0 = time.time()

    cblite_replicate(*args, **kwargs)

    test.replicate_time = time.time() - t0  # Delta Sync time in seconds


class SGPerfTest(PerfTest):

    COLLECTORS = {'disk': False, 'ns_server': False, 'ns_server_overview': False, 'active_tasks': False,
                  'syncgateway_stats': True}

    ALL_HOSTNAMES = True
    LOCAL_DIR = "YCSB"

    def __init__(self,
                 cluster_spec: ClusterSpec,
                 test_config: TestConfig,
                 verbose: bool):
        self.cluster_spec = cluster_spec
        self.test_config = test_config
        self.memcached = MemcachedHelper(test_config)
        self.remote = RemoteHelper(cluster_spec, test_config, verbose)
        self.rest = RestHelper(cluster_spec)
        #self.build = os.environ.get('SGBUILD') or "0.0.0-000"
        self.master_node = next(cluster_spec.masters)
        self.build = self.rest.get_sgversion(self.master_node)
        self.metrics = MetricHelper(self)
        self.reporter = ShowFastReporter(cluster_spec, test_config, self.build)
        if self.test_config.test_case.use_workers:
            self.worker_manager = WorkerManager(cluster_spec, test_config, verbose)
        self.settings = self.test_config.access_settings
        self.settings.syncgateway_settings = self.test_config.syncgateway_settings
        self.profiler = Profiler(cluster_spec, test_config)
        self.monitor = self.monitor = Monitor(cluster_spec, test_config, verbose)
        self.cluster = ClusterManager(cluster_spec, test_config)

    def download_ycsb(self):
        if self.worker_manager.is_remote:
            self.remote.clone_ycsb(repo=self.test_config.syncgateway_settings.repo,
                                   branch=self.test_config.syncgateway_settings.branch,
                                   worker_home=self.worker_manager.WORKER_HOME,
                                   ycsb_instances=int(self.test_config.syncgateway_settings.instances_per_client))
        else:
            local.clone_ycsb(repo=self.test_config.syncgateway_settings.repo,
                             branch=self.test_config.syncgateway_settings.branch)

    def collect_execution_logs(self):
        if self.worker_manager.is_remote:
            if os.path.exists(self.LOCAL_DIR):
                shutil.rmtree(self.LOCAL_DIR, ignore_errors=True)
            os.makedirs(self.LOCAL_DIR)
            self.remote.get_syncgateway_YCSB_logs(self.worker_manager.WORKER_HOME,
                                                  self.test_config.syncgateway_settings, self.LOCAL_DIR)

    def run_sg_phase(self,
                  phase: str,
                  task: Callable, settings: PhaseSettings,
                  timer: int = None,
                  distribute: bool = False) -> None:
        logger.info('Running {}: {}'.format(phase, pretty_dict(settings)))
        self.worker_manager.run_sg_tasks(task, settings, timer, distribute, phase)
        self.worker_manager.wait_for_workers()

    def start_memcached(self):
        self.run_sg_phase("start memcached", syncgateway_task_start_memcached, self.settings, self.settings.time, False)

    def load_users(self):
        self.run_sg_phase("load users", syncgateway_task_load_users, self.settings, self.settings.time, False)

    def init_users(self):
        if self.test_config.syncgateway_settings.auth == 'true':
            self.run_sg_phase("init users", syncgateway_task_init_users, self.settings, self.settings.time, False)

    def grant_access(self):
        if self.test_config.syncgateway_settings.grant_access == 'true':
            self.run_sg_phase("grant access to  users", syncgateway_task_grant_access, self.settings,
                              self.settings.time, False)

    def load_docs(self):
        self.run_sg_phase("load docs", syncgateway_task_load_docs, self.settings, self.settings.time, False)

    @with_stats
    def run_test(self):
        self.run_sg_phase("run test", syncgateway_task_run_test, self.settings, self.settings.time, True)

    def compress_sg_logs(self):
        self.remote.compress_sg_logs()

    def get_sg_logs(self):
        initial_nodes = int(self.test_config.syncgateway_settings.nodes)
        ssh_user, ssh_pass = self.cluster_spec.ssh_credentials
        for _server in range(initial_nodes):
            server = self.cluster_spec.servers[_server]
            local.get_sg_logs(host=server, ssh_user=ssh_user, ssh_pass=ssh_pass)


    def run(self):
        self.download_ycsb()
        self.start_memcached()
        self.load_users()
        self.load_docs()
        self.init_users()
        self.grant_access()
        self.run_test()
        self.report_kpi()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.test_config.test_case.use_workers:
            self.worker_manager.download_celery_logs()
            self.worker_manager.terminate()

        if self.test_config.cluster.online_cores:
            self.remote.enable_cpu()

        if self.test_config.cluster.kernel_mem_limit:
            self.remote.reset_memory_settings()
            self.monitor.wait_for_servers()

class SGRead(SGPerfTest):
    def _report_kpi(self):
        self.collect_execution_logs()
        for f in glob.glob('{}/*runtest*.result'.format(self.LOCAL_DIR)):
            with open(f, 'r') as fout:
                logger.info(f)
                logger.info(fout.read())

        self.reporter.post(
            *self.metrics.sg_throughput("Throughput (req/sec), GET doc by id")
        )


class SGAuthThroughput(SGPerfTest):
    def _report_kpi(self):
        self.collect_execution_logs()
        for f in glob.glob('{}/*runtest*.result'.format(self.LOCAL_DIR)):
            with open(f, 'r') as fout:
                logger.info(f)
                logger.info(fout.read())

        self.reporter.post(
            *self.metrics.sg_throughput("Throughput (req/sec), POST auth")
        )


class SGAuthLatency(SGPerfTest):
    def _report_kpi(self):
        self.collect_execution_logs()
        for f in glob.glob('{}/*runtest*.result'.format(self.LOCAL_DIR)):
            with open(f, 'r') as fout:
                logger.info(f)
                logger.info(fout.read())

        self.reporter.post(
            *self.metrics.sg_latency('[SCAN], 95thPercentileLatency(us)',
                                     'Latency (ms), POST auth, 95 percentile')
        )


class SGSync(SGPerfTest):
    def _report_kpi(self):
        self.collect_execution_logs()
        for f in glob.glob('{}/*runtest*.result'.format(self.LOCAL_DIR)):
            with open(f, 'r') as fout:
                logger.info(f)
                logger.info(fout.read())

        self.reporter.post(
            *self.metrics.sg_throughput('Throughput (req/sec), GET docs via _changes')
        )

        self.reporter.post(
            *self.metrics.sg_latency('[INSERT], 95thPercentileLatency(us)',
                                     'Latency, round-trip write, 95 percentile (ms)')
        )


class SGSyncQueryThroughput(SGPerfTest):
    def _report_kpi(self):
        self.collect_execution_logs()
        for f in glob.glob('{}/*runtest*.result'.format(self.LOCAL_DIR)):
            with open(f, 'r') as fout:
                logger.info(f)
                logger.info(fout.read())

        self.reporter.post(
            *self.metrics.sg_throughput('Throughput (req/sec), GET docs via _changes')
        )


class SGSyncQueryLatency(SGPerfTest):
    def _report_kpi(self):
        self.collect_execution_logs()
        for f in glob.glob('{}/*runtest*.result'.format(self.LOCAL_DIR)):
            with open(f, 'r') as fout:
                logger.info(f)
                logger.info(fout.read())

        self.reporter.post(
            *self.metrics.sg_latency('[READ], 95thPercentileLatency(us)',
                                     'Latency (ms), GET docs via _changes, 95 percentile')
        )

class SGWrite(SGPerfTest):
    def _report_kpi(self):
        self.collect_execution_logs()
        for f in glob.glob('{}/*runtest*.result'.format(self.LOCAL_DIR)):
            with open(f, 'r') as fout:
                logger.info(f)
                logger.info(fout.read())

        self.reporter.post(
            *self.metrics.sg_throughput("Throughput (req/sec), POST doc")
        )


class SGMixQueryThroughput(SGPerfTest):
    def _report_kpi(self):
        self.collect_execution_logs()
        for f in glob.glob('{}/*runtest*.result'.format(self.LOCAL_DIR)):
            with open(f, 'r') as fout:
                logger.info(f)
                logger.info(fout.read())

        self.reporter.post(
            *self.metrics.sg_throughput("Throughput (req/sec)")
        )


class DeltaSync(SGPerfTest):

    def start_cblite(self, port: str, db_name: str):
        local.start_cblitedb(port=port, db_name=db_name)

    @with_stats
    @with_profiles
    def cblite_replicate(self, cblite_db: str):
        if self.test_config.syncgateway_settings.replication_type == 'PUSH':
            str = local.replicate_push(cblite_db=cblite_db)
        elif self.test_config.syncgateway_settings.replication_type == 'PULL':
            str = local.replicate_pull(cblite_db=cblite_db)

        if str.find('Completed'):
            print('cblite message:', str)
            replicationTime = float((re.search('docs in (.*) secs;', str)).group(1))
            docsReplicated = int((re.search('Completed (.*) docs in', str)).group(1))
            if docsReplicated == int(self.test_config.syncgateway_settings.documents):
                successCode = 'SUCCESS'
            else:
                successCode = 'FAILED'
                print("Replication failed due to partial replication . Number of docs replicated: ", docsReplicated)
        else:
            print('Replication failed with error message:', str)
            replicationTime = 0
            docsReplicated = 0
            successCode = 'FAILED'
        return replicationTime, docsReplicated, successCode

    def _report_kpi(self, replicationTime: float, throughput: int, bandwidth: float, bytes: float, field_length: str):
        self.collect_execution_logs()
        for f in glob.glob('{}/*runtest*.result'.format(self.LOCAL_DIR)):
            with open(f, 'r') as fout:
                logger.info(f)
                logger.info(fout.read())
        self.reporter.post(
            *self.metrics.deltasync_time(replicationTime=replicationTime, field_length=field_length)
        )

        self.reporter.post(
            *self.metrics.deltasync_throughput(throughput=throughput, field_length=field_length)
        )

        self.reporter.post(
            *self.metrics.deltasync_bytes(bytes=bytes, field_length=field_length)
        )

    def db_cleanup(self):
        local.cleanup_cblite_db()

    def post_deltastats(self):
        sg_server = self.cluster_spec.servers[0]
        stats = self.monitor.deltasync_stats(host=sg_server)
        print('Sync-gateway Stats:', stats)

    def calc_bandwidth_usage(self, bytes: float, timetaken: float):
        bandwidth = round((((bytes/timetaken)/1024)/1024), 2) #in Mb
        return bandwidth

    def get_bytes_transfer(self):
        sg_server = self.cluster_spec.servers[0]
        bytes_transfered = self.monitor.deltasync_bytes_transfer(host=sg_server)
        return bytes_transfered


    def run(self):
        self.download_ycsb()

        if self.test_config.syncgateway_settings.deltasync_cachehit_ratio == '100':
            self.start_cblite(port='4985', db_name='db1')
            self.start_cblite(port='4986', db_name='db2')
        else:
            self.start_cblite(port='4985', db_name='db')
        self.start_memcached()
        self.load_docs()

        if self.test_config.syncgateway_settings.deltasync_cachehit_ratio == '100':
            self.cblite_replicate(cblite_db='db1')
            self.cblite_replicate(cblite_db='db2')
        else:
            self.cblite_replicate(cblite_db='db')
        self.post_deltastats()
        self.run_test()

        if self.test_config.syncgateway_settings.deltasync_cachehit_ratio == '100':
            self.cblite_replicate(cblite_db='db1')
            bytes_transfered_1 = self.get_bytes_transfer()
            replicationTime, docsReplicated, successCode = self.cblite_replicate(cblite_db='db2')
        else:
            bytes_transfered_1 = self.get_bytes_transfer()
            replicationTime, docsReplicated, successCode = self.cblite_replicate(cblite_db='db')

        if successCode == 'SUCCESS':
            self.post_deltastats()
            bytes_transfered_2 = self.get_bytes_transfer()
            byte_transfer = bytes_transfered_2 - bytes_transfered_1
            bandwidth = self.calc_bandwidth_usage(bytes=byte_transfer, timetaken=replicationTime)
            throughput = int(docsReplicated/replicationTime)
            field_length = str(self.test_config.syncgateway_settings.fieldlength)
            self.report_kpi(replicationTime, throughput, bandwidth, byte_transfer, field_length)

            self.db_cleanup()
        else:
            self.db_cleanup()
        self.compress_sg_logs()
        self.get_sg_logs()


class DeltaSync_Parallel(DeltaSync):

    def generate_dbmap(self, num_dbs: int):
        db_map = {}
        for i in range(num_dbs):
            port = str(4985 + i)
            db_name = 'db' + str(i)
            db_map.update({port: db_name})
        return db_map

    def start_multiplecblite(self, db_map: map):
        cblite_dbs = []
        for key in db_map:
            local.start_cblitedb(port=key, db_name=db_map[key])
            cblite_dbs.append(db_map[key])
        return cblite_dbs

    @with_stats
    @with_profiles
    def multiple_replicate(self, num_agents: int, cblite_dbs: list):
        with Pool(processes=num_agents) as pool:
            print('starting cb replicate paralell with ', num_agents)
            results = pool.map(func=self.cblite_replicate, iterable=cblite_dbs)
        print('end of multiple replicate')
        return results

    def cblite_replicate(self, cblite_db: str):
        if self.test_config.syncgateway_settings.replication_type == 'PUSH':
            str = local.replicate_push(cblite_db=cblite_db)
        elif self.test_config.syncgateway_settings.replication_type == 'PULL':
            str = local.replicate_pull(cblite_db=cblite_db)

        if str.find('Completed'):
            print('cblite message:', str)
            replicationTime = float((re.search('docs in (.*) secs;', str)).group(1))
            docsReplicated = int((re.search('Completed (.*) docs in', str)).group(1))
            if docsReplicated == int(self.test_config.syncgateway_settings.documents):
                successCode = 'SUCCESS'
            else:
                successCode = 'FAILED'
                print("Replication failed due to partial replication . Number of docs replicated: ", docsReplicated)
        else:
            print('Replication failed with error message:', str)
            replicationTime = 0
            docsReplicated = 0
            successCode = 'FAILED'
        return replicationTime, docsReplicated, successCode

    def get_averagetime(self, results: list):
        sum = 0
        for result in results:
            sum = sum + result[0]
        average = sum/len(results)
        return average

    def get_docsReplicated(self, results: list):
        doc_count = 0
        for result in results:
            doc_count = doc_count + result[1]
        return doc_count

    def check_success(self, results: list):
        success_count = 0;
        for result in results:
            if result[2] == 'SUCCESS':
                success_count += 1;
        print('success_count :', success_count)
        if success_count == len(results):
            return 1
        else:
            return 0

    def run(self):
        self.download_ycsb()
        self.start_memcached()

        num_dbs = int(self.test_config.syncgateway_settings.replication_concurrency)



        db_map = self.generate_dbmap(num_dbs)
        cblite_dbs = self.start_multiplecblite(db_map)

        if self.test_config.syncgateway_settings.deltasync_cachehit_ratio == '100':
            self.start_cblite(port='4983', db_name='db')

        self.load_docs()

        if self.test_config.syncgateway_settings.deltasync_cachehit_ratio == '100':
            self.cblite_replicate(cblite_db='db')

        num_agents = len(cblite_dbs)

        self.multiple_replicate(num_agents, cblite_dbs)

        bytes_transfered_1 = self.get_bytes_transfer()
        self.post_deltastats()

        self.run_test()

        if self.test_config.syncgateway_settings.deltasync_cachehit_ratio == '100':
            self.cblite_replicate(cblite_db='db')
            bytes_transfered_1 = self.get_bytes_transfer()

        results = self.multiple_replicate(num_agents, cblite_dbs)

        if self.check_success(results) == 1:
            print('success')
            self.post_deltastats()
            bytes_transfered_2 = self.get_bytes_transfer()
            byte_transfer = bytes_transfered_2 - bytes_transfered_1
            averagetime = self.get_averagetime(results)

            docsReplicated = self.get_docsReplicated(results)

            field_length = str(self.test_config.syncgateway_settings.fieldlength)

            throughput = int(docsReplicated / averagetime)
            bandwidth = self.calc_bandwidth_usage(bytes=byte_transfer, timetaken=averagetime)

            self.report_kpi(averagetime, throughput, bandwidth, byte_transfer, field_length)

            self.db_cleanup()
        else:
            self.db_cleanup()
        self.compress_sg_logs()
        self.get_sg_logs()