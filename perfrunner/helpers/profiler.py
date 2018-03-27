from threading import Timer
from typing import Callable

import requests
from decorator import decorator
from sshtunnel import SSHTunnelForwarder

from logger import logger
from perfrunner.settings import ClusterSpec, TestConfig


@decorator
def with_profiles(method: Callable, *args, **kwargs):
    test = args[0]
    test.profiler.schedule()
    return method(*args, **kwargs)


class Profiler:

    DEBUG_PORTS = {
        'fts':   8094,
        'index': 9102,
        'kv':    9998,  # goxdcr
        'n1ql':  6060,
    }

    ENDPOINTS = {
        'cpu':  'http://127.0.0.1:{}/debug/pprof/profile',
        'heap': 'http://127.0.0.1:{}/debug/pprof/heap',
    }

    def __init__(self, cluster_spec: ClusterSpec, test_config: TestConfig):
        self.cluster_spec = cluster_spec
        self.test_config = test_config

        self.ssh_username, self.ssh_password = cluster_spec.ssh_credentials

    def new_tunnel(self, host: str, port: int) -> SSHTunnelForwarder:
        return SSHTunnelForwarder(
            ssh_address_or_host=host,
            ssh_username=self.ssh_username,
            ssh_password=self.ssh_password,
            remote_bind_address=('127.0.0.1', port),
        )

    def save(self, host: str, service: str, profile: str, content: bytes):
        with open('{}_{}_{}.pprof'.format(host, service, profile), 'wb') as fh:
            fh.write(content)

    def profile(self, host: str, service: str, profile: str):
        logger.info('Collecting {} profile on {}'.format(profile, host))

        endpoint = self.ENDPOINTS[profile]
        port = self.DEBUG_PORTS[service]

        with self.new_tunnel(host, port) as tunnel:
            url = endpoint.format(tunnel.local_bind_port)
            response = requests.get(url=url)
            self.save(host, service, profile, response.content)

    def timer(self, **kwargs):
        timer = Timer(function=self.profile,
                      interval=self.test_config.profiling_settings.interval,
                      kwargs=kwargs)
        timer.start()

    def schedule(self):
        for service in self.test_config.profiling_settings.services:
            logger.info('Scheduling profiling of "{}" services'.format(service))
            for server in self.cluster_spec.servers_by_role(role=service):
                for profile in self.test_config.profiling_settings.profiles:
                    self.timer(host=server, service=service, profile=profile)