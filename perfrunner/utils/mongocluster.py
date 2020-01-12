from argparse import ArgumentParser

from fabric.api import cd, run

from perfrunner.helpers.remote import RemoteHelper
from perfrunner.remote.context import all_servers, \
    mongod_master, mongod_servers, mongos_servers, mongos_master, all_clients
from perfrunner.settings import ClusterSpec, TestConfig


class MongoInstaller:

    def __init__(self, cluster_spec, test_config, options):
        self.test_config = test_config
        self.cluster_spec = cluster_spec
        self.client_settings = self.test_config.client_settings.__dict__
        self.options = options
        self.remote = RemoteHelper(self.cluster_spec, options.verbose)

    @all_servers
    def cloning_napatools(self):
        print('entered cloning')
        run('rm -rf mongotesting')
        run('mkdir mongotesting')
        with cd('mongotesting'):
            run('git clone -q -b soe2_hercules https://github.com/sharujayaram/napatools.git', shell=False)

    @all_servers
    def runSetupShell(self):
        with cd('/root/mongotesting/napatools/mongotools/mongo42-ent-2replicas'):
            print('runing setup.sh in folder :')
            run('sh setup.sh')

    @mongod_servers
    def configServerReplicaSet(self):
        print('about to run mongod config on 121 to 124 servers')
        with cd('/root/mongotesting/napatools/mongotools/mongo42-ent-2replicas'):
            run('mongod --config cfg/config_server.cfg')

    @mongod_master
    def initConfigServReplicasetMaster(self):
        print('initiating replica set on mongod master 204')
        with cd('/root/mongotesting/napatools/mongotools/mongo42-ent-2replicas'):
            run('python init_replicaset_master.py')


    @mongod_servers
    def createReplicaSet_origin(self):
        with cd('/root/mongotesting/napatools/mongotools/mongo42-ent-2replicas'):
            print('running mongod shard config on 204')

            run('sh mongod_shard_config_204.sh')

    # on all mongo servers
    @mongod_servers
    def createReplicaSet(self):
        with cd('/root/mongotesting/napatools/mongotools/mongo42-ent-2replicas'):
            print('Creating Replica Set')
            ip = run('hostname -I | awk \'{print $1}\'').split(".")[3]
            print('ip inside serevr', ip)

            if ip == '121':
                ip = 204
            if ip == '122':
                ip = 205
            if ip == '123':
                ip = 206
            if ip == '124':
                ip = 207

            shell_to_run = 'mongod_shard_config_{}'.format(ip)
            run('sh {}.sh'.format(shell_to_run))

    @mongod_servers
    def initReplicaset_origin(self):
        with cd('/root/mongotesting/napatools/mongotools/mongo42-ent-2replicas'):
            print('initiating  shard replicaset on 204')
            run('python init_shard_replicaset_204.py')

    @mongod_servers
    def initReplicaset(self):
        with cd('/root/mongotesting/napatools/mongotools/mongo42-ent-2replicas'):
            print('initiating  shard replicaset on 204')

            ip = run('hostname -I | awk \'{print $1}\'').split(".")[3]
            print('ip inside serevr', ip)

            if ip == '121':
                ip = 204
            if ip == '122':
                ip = 205
            if ip == '123':
                ip = 206
            if ip == '124':
                ip = 207

            pyTorun = 'init_shard_replicaset_{}.py'.format(ip)
            run('python {}'.format(pyTorun))

    @mongos_servers
    def run_mongos_config(self):
        with cd('/root/mongotesting/napatools/mongotools/mongo42-ent-2replicas'):
            print('about to run mongos config on 190 to 193 servers')
            run('mongos --config cfg/mongos.cfg')

    @mongos_master
    def mongos_addshard_master(self):
        with cd('/root/mongotesting/napatools/mongotools/mongo42-ent-2replicas'):
            print('adding shard on 190')
            run('python mongos_addshard_master.py')


def get_args():
    parser = ArgumentParser()

    parser.add_argument('-c', '--cluster', dest='cluster_spec_fname',
                        required=True,
                        help='path to the cluster specification file')
    parser.add_argument('-t', '--test', dest='test_config_fname',
                        required=True,
                        help='path to test test configuration file')
    parser.add_argument('--verbose', dest='verbose',
                        action='store_true',
                        help='enable verbose logging')
    parser.add_argument('override',
                        nargs='*',
                        help='custom cluster settings')

    return parser.parse_args()


def main():
    args = get_args()

    cluster_spec = ClusterSpec()
    cluster_spec.parse(args.cluster_spec_fname, override=args.override)
    test_config = TestConfig()
    test_config.parse(args.test_config_fname, override=args.override)

    mongo = MongoInstaller(cluster_spec, test_config, args)
    mongo.cloning_napatools()
    mongo.runSetupShell()
    mongo.configServerReplicaSet()
    mongo.initConfigServReplicasetMaster()

    mongo.createReplicaSet()

    mongo.initReplicaset()

    mongo.run_mongos_config()

    mongo.mongos_addshard_master()


if __name__ == '__main__':
    main()
