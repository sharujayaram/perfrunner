from collections import namedtuple
from optparse import OptionParser
from typing import Iterator

import requests
import validators
from logger import logger
from requests.exceptions import ConnectionError

from perfrunner.helpers.remote import RemoteHelper
from perfrunner.settings import ClusterSpec

LOCATIONS = (
    'http://172.23.120.24/builds/latestbuilds/couchbase-server/spock/{build}/',
    'http://172.23.120.24/builds/latestbuilds/couchbase-server/watson/{build}/',
    'http://172.23.120.24/builds/releases/{release}/',
    'http://172.23.120.24/builds/releases/{release}/ce/',
)

PKG_PATTERNS = {
    'rpm': (
        'couchbase-server-{edition}-{release}-{build}-centos{os}.x86_64.rpm',
        'couchbase-server-{edition}-{release}-centos{os}.x86_64.rpm',
        'couchbase-server-{edition}-{release}-centos6.x86_64.rpm',
    ),
    'deb': (
        'couchbase-server-{edition}_{release}-{build}-ubuntu{os}_amd64.deb',
        'couchbase-server-{edition}_{release}-ubuntu{os}_amd64.deb',
    ),
    'exe': (
        'couchbase-server-{edition}_{release}-{build}-windows_amd64.exe',
        'couchbase-server-{edition}_{release}-windows_amd64.exe',
    ),
}

Build = namedtuple('Build', ['filename', 'url'])


class CouchbaseInstaller:

    def __init__(self, cluster_spec, options):
        self.remote = RemoteHelper(cluster_spec, None, options.verbose)
        self.options = options

    @property
    def url(self) -> str:
        if validators.url(self.options.version):
            return self.options.version
        else:
            return self.find_package(edition=self.options.edition)

    @property
    def release(self) -> str:
        return self.options.version.split('-')[0]

    @property
    def build(self) -> str:
        split = self.options.version.split('-')
        if len(split) > 1:
            return split[1]

    def find_package(self, edition: str) -> [str, str]:
        for url in self.url_iterator(edition):
            if self.is_exist(url):
                return url
        logger.interrupt('Target build not found')

    def url_iterator(self, edition: str) -> Iterator[str]:
        os_release = None
        if self.remote.package == 'rpm':
            os_release = self.remote.detect_centos_release()
        elif self.remote.package == 'deb':
            os_release = self.remote.detect_ubuntu_release()

        for pkg_pattern in PKG_PATTERNS[self.remote.package]:
            for loc_pattern in LOCATIONS:
                url = loc_pattern + pkg_pattern
                yield url.format(release=self.release, build=self.build,
                                 edition=edition, os=os_release)

    @staticmethod
    def is_exist(url):
        try:
            status_code = requests.head(url).status_code
        except ConnectionError:
            return False
        if status_code == 200:
            return True
        return False

    def kill_processes(self):
        self.remote.kill_processes()

    def uninstall_package(self):
        self.remote.uninstall_couchbase()

    def clean_data(self):
        self.remote.clean_data()

    def install_package(self):
        logger.info('Using this URL: {}'.format(self.url))
        self.remote.upload_iss_files(self.release)
        self.remote.install_couchbase(self.url)

    def install(self):
        self.kill_processes()
        self.uninstall_package()
        self.clean_data()
        self.install_package()


def main():
    usage = '%prog -c cluster -b build'

    parser = OptionParser(usage)

    parser.add_option('-v', '--url', dest='version',
                      help='the build version or the HTTP URL to a package')
    parser.add_option('-c', dest='cluster_spec_fname',
                      help='the path to a cluster specification file')
    parser.add_option('-e', dest='edition', default='enterprise',
                      help='the cluster edition (community or enterprise)')
    parser.add_option('--verbose', dest='verbose', action='store_true',
                      help='enable verbose logging')

    options, args = parser.parse_args()

    if not (options.cluster_spec_fname and options.version):
        parser.error('Missing mandatory parameter. Either specify both cluster '
                     'spec and version.')

    cluster_spec = ClusterSpec()
    cluster_spec.parse(fname=options.cluster_spec_fname)

    installer = CouchbaseInstaller(cluster_spec, options)
    installer.install()


if __name__ == '__main__':
    main()
