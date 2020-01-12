from typing import Callable, List

from decorator import decorator
from fabric.api import execute, parallel, settings


@decorator
def all_servers(task, *args, **kwargs):
    """Execute the decorated function on all remote server nodes."""
    helper = args[0]

    hosts = helper.cluster_spec.servers

    return execute(parallel(task), *args, hosts=hosts, **kwargs)


@decorator
def master_server(task: Callable, *args, **kwargs):
    """Execute the decorated function on master node."""
    self = args[0]
    with settings(host_string=self.cluster_spec.servers[0]):
        return task(*args, **kwargs)


def servers_by_role(roles: List[str]):
    """Execute the decorated function on remote server nodes filtered by role."""
    @decorator
    def wrapper(task, *args, **kwargs):
        helper = args[0]

        hosts = []
        for role in roles:
            hosts += helper.cluster_spec.servers_by_role(role=role)

        execute(parallel(task), *args, hosts=hosts, **kwargs)

    return wrapper


@decorator
def all_clients(task: Callable, *args, **kwargs):
    """Execute the decorated function on all remote client machines."""
    helper = args[0]

    hosts = helper.cluster_spec.workers

    return execute(parallel(task), *args, hosts=hosts, **kwargs)


@decorator
def mongod_servers(task: Callable, *args, **kwargs):
    """Execute the decorated function on all remote client machines."""
    helper = args[0]

    hosts = helper.cluster_spec.mongodnodes

    return execute(parallel(task), *args, hosts=hosts, **kwargs)



@decorator
def mongod_master(task: Callable, *args, **kwargs):
    """Execute the decorated function on master node."""
    self = args[0]
    with settings(host_string=self.cluster_spec.mongodnodes[0]):
        return task(*args, **kwargs)


@decorator
def mongos_servers(task: Callable, *args, **kwargs):
    """Execute the decorated function on all remote client machines."""
    helper = args[0]

    hosts = helper.cluster_spec.mongosnodes

    return execute(parallel(task), *args, hosts=hosts, **kwargs)


@decorator
def mongos_master(task: Callable, *args, **kwargs):
    """Execute the decorated function on master node."""
    self = args[0]
    with settings(host_string=self.cluster_spec.mongosnodes[0]):
        return task(*args, **kwargs)
