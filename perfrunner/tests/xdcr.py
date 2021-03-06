from perfrunner.helpers.cbmonitor import timeit, with_stats
from perfrunner.helpers.misc import target_hash
from perfrunner.settings import TargetSettings
from perfrunner.tests import PerfTest, TargetIterator


class XdcrTest(PerfTest):

    """Implement bi-directional XDCR cases.

    As a base class it implements several methods for XDCR management and WAN
    configuration.

    "run" workflow is common for both uni-directional and bi-directional cases.
    """

    COLLECTORS = {'xdcr_lag': True, 'xdcr_stats': True}

    ALL_BUCKETS = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = self.test_config.xdcr_settings

    def _start_replication(self, m1, m2):
        name = target_hash(m1, m2)
        certificate = self.settings.use_ssl and self.rest.get_certificate(m2)
        self.rest.add_remote_cluster(m1, m2, name, certificate)

        for bucket in self.test_config.buckets:
            params = {
                'replicationType': 'continuous',
                'toBucket': bucket,
                'fromBucket': bucket,
                'toCluster': name
            }
            if self.settings.filter_expression:
                params['filterExpression'] = self.settings.filter_expression
            self.rest.start_replication(m1, params)

    def enable_xdcr(self):
        m1, m2 = self.cluster_spec.masters
        self._start_replication(m1, m2)
        self._start_replication(m2, m1)

    def monitor_replication(self):
        for target in self.target_iterator:
            if self.rest.get_remote_clusters(target.node):
                self.monitor.monitor_xdcr_queues(target.node, target.bucket)

    @with_stats
    def access(self, *args):
        super().sleep()

    def configure_wan(self):
        if self.settings.wan_delay:
            hostnames = self.cluster_spec.servers
            src_list = [
                hostname for hostname in hostnames[len(hostnames) // 2:]
            ]
            dest_list = [
                hostname for hostname in hostnames[:len(hostnames) // 2]
            ]
            self.remote.enable_wan(self.settings.wan_delay)
            self.remote.filter_wan(src_list, dest_list)

    def _report_kpi(self, *args):
        self.reporter.post(
            *self.metrics.xdcr_lag()
        )

        if self.test_config.stats_settings.post_cpu:
            self.reporter.post(
                *self.metrics.cpu_utilization()
            )

    def run(self):
        self.load()
        self.wait_for_persistence()

        self.enable_xdcr()
        self.monitor_replication()
        self.wait_for_persistence()

        self.hot_load()

        self.configure_wan()

        self.access_bg()
        self.access()

        self.report_kpi()


class SrcTargetIterator(TargetIterator):

    def __iter__(self):
        password = self.test_config.bucket.password
        prefix = self.prefix
        src_master = next(self.cluster_spec.masters)
        for bucket in self.test_config.buckets:
            if self.prefix is None:
                prefix = target_hash(src_master, bucket)
            yield TargetSettings(src_master, bucket, password, prefix)


class DestTargetIterator(TargetIterator):

    def __iter__(self):
        password = self.test_config.bucket.password
        prefix = self.prefix
        masters = self.cluster_spec.masters
        src_master = next(masters)
        dest_master = next(masters)
        for bucket in self.test_config.buckets:
            if self.prefix is None:
                prefix = target_hash(src_master, bucket)
            yield TargetSettings(dest_master, bucket, password, prefix)


class UniDirXdcrTest(XdcrTest):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_iterator = TargetIterator(self.cluster_spec,
                                              self.test_config,
                                              prefix='symmetric')

    def load(self, *args):
        src_target_iterator = SrcTargetIterator(self.cluster_spec,
                                                self.test_config,
                                                prefix='symmetric')
        super().load(target_iterator=src_target_iterator)

    def enable_xdcr(self):
        m1, m2 = self.cluster_spec.masters
        self._start_replication(m1, m2)


class XdcrInitTest(XdcrTest):

    """Run initial XDCR.

    There is no ongoing workload and compaction is usually disabled.
    """

    COLLECTORS = {'xdcr_stats': True}

    @with_stats
    @timeit
    def init_xdcr(self):
        self.enable_xdcr()
        self.monitor_replication()

    def _report_kpi(self, time_elapsed):
        self.reporter.post(
            *self.metrics.avg_replication_rate(time_elapsed)
        )

    def run(self):
        self.load()
        self.wait_for_persistence()

        self.configure_wan()

        time_elapsed = self.init_xdcr()
        self.report_kpi(time_elapsed)


class UniDirXdcrInitTest(XdcrInitTest):

    def enable_xdcr(self):
        m1, m2 = self.cluster_spec.masters
        self._start_replication(m1, m2)

    def load(self, *args):
        src_target_iterator = SrcTargetIterator(self.cluster_spec,
                                                self.test_config)
        super(XdcrInitTest, self).load(target_iterator=src_target_iterator)
