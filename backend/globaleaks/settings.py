# -*- coding: UTF-8
# settings: Define GLSettings, main class handling GlobaLeeaks runtime settings
# ******
from __future__ import print_function

import getpass
import glob
import grp
import logging
import os
import pwd
import re
import sys
# pylint: disable=no-name-in-module,import-error
from distutils import dir_util
from distutils.version import LooseVersion
# pylint: enable=no-name-in-module,import-error
from optparse import OptionParser

from twisted.internet.defer import inlineCallbacks
from twisted.python.threadpool import ThreadPool

from globaleaks import __version__, DATABASE_VERSION
from globaleaks.utils.agent import get_tor_agent, get_web_agent
from globaleaks.utils.objectdict import ObjectDict
from globaleaks.utils.singleton import Singleton
from globaleaks.utils.tor_exit_set import TorExitSet
from globaleaks.utils.utility import datetime_now, log

this_directory = os.path.dirname(__file__)

possible_client_paths = [
    '/var/globaleaks/client',
    '/usr/share/globaleaks/client/',
    os.path.abspath(os.path.join(this_directory, '../../client/build/')),
    os.path.abspath(os.path.join(this_directory, '../../client/app/'))
]

verbosity_dict = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

external_counted_events = {
    'new_submission': 0,
    'finalized_submission': 0,
    'anon_requests': 0,
    'file_uploaded': 0,
}


class GLSettingsClass(object):
    __metaclass__ = Singleton

    def __init__(self):
        # command line parsing utils
        self.parser = OptionParser()
        self.cmdline_options = None

        # version
        self.version_string = __version__

        # testing
        # This variable is to be able to hook/bypass code when unit-tests are run
        self.testing = False

        # daemonize the process
        self.nodaemon = False

        # thread pool size of 1
        self.orm_tp = ThreadPool(1, 1)

        self.bind_address = '0.0.0.0'
        self.bind_remote_ports = [80, 443]
        self.bind_local_ports = [8082, 8083]

        # store name
        self.store_name = 'main_store'

        self.db_type = 'sqlite'

        # debug defaults
        self.orm_debug = False

        # files and paths
        self.root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.pid_path = '/var/run/globaleaks'
        self.working_path = '/var/globaleaks'

        # TODO(bug-fix-italian-style) why is this set to the 2nd entry in the possible
        # client paths...? please fix.
        self.client_path = '/usr/share/globaleaks/client'
        for path in possible_client_paths:
            if os.path.exists(path):
                self.client_path = path
                break

        self.set_ramdisk_path()

        self.authentication_lifetime = 3600

        self.jobs = []
        self.jobs_monitor = None

        self.services = []

        self.RecentEventQ = []
        self.RecentAnomaliesQ = {}
        self.stats_collection_start_time = datetime_now()

        self.accept_submissions = True

        # statistical, referred to latest period
        # and resetted by session_management sched
        self.failed_login_attempts = 0

        # static file rules
        self.staticfile_regexp = r'(.*)'
        self.staticfile_overwrite = False

        self.local_hosts = ['127.0.0.1', 'localhost']

        self.onionservice = None

        self.receipt_regexp = u'[0-9]{16}'

        # A lot of operations performed massively by globaleaks
        # should avoid to fetch continuously variables from the DB so that
        # it is important to keep this variables in memory
        #
        # Initialization is handled by db_refresh_memory_variables
        self.memory_copy = ObjectDict({
            'maximum_namesize': 128,
            'maximum_textsize': 4096,
            'maximum_filesize': 30,
            'allow_iframes_inclusion': False,
            'accept_tor2web_access': {
                'admin': True,
                'whistleblower': False,
                'custodian': False,
                'receiver': False
            },
            'private': {
                'https_enabled': False,
            },
            'anonymize_outgoing_connections': True,
        })


        # Default request time uniform value
        self.side_channels_guard = 150

        # SOCKS default
        self.socks_host = "127.0.0.1"
        self.socks_port = 9050

        self.key_bits = 2048
        self.csr_sign_bits = 512

        self.api_token_len = 32

        self.notification_limit = 30
        self.jobs_operation_limit = 20

        self.user = getpass.getuser()
        self.group = getpass.getuser()
        self.uid = os.getuid()
        self.gid = os.getgid()
        self.devel_mode = False
        self.developer_name = ''
        self.disable_swap = False

        # Number of failed login enough to generate an alarm
        self.failed_login_alarm = 5

        # Number of minutes in which a user is prevented to login in case of triggered alarm
        self.failed_login_block_time = 5

        # Limit for log sizes and number of log files
        # https://github.com/globaleaks/GlobaLeaks/issues/1578
        self.log_size = 10000000 # 10MB
        self.log_file_size = 1000000 # 1MB
        self.num_log_files = self.log_size / self.log_file_size

        # size used while streaming files
        self.file_chunk_size = 65535 # 64kb

        self.AES_key_size = 32
        self.AES_key_id_regexp = u'[A-Za-z0-9]{16}'
        self.AES_counter_nonce = 128 / 8
        self.AES_file_regexp = r'(.*)\.aes'
        self.AES_file_regexp_comp = re.compile(self.AES_file_regexp)
        self.AES_keyfile_prefix = "aeskey-"

        self.exceptions = {}
        self.exceptions_email_count = 0
        self.exceptions_email_hourly_limit = 20

        self.disable_backend_exception_notification = False
        self.disable_client_exception_notification = False

        self.enable_input_length_checks = True

        self.submission_minimum_delay = 3 # seconds
        self.submission_maximum_ttl = 3600 # 1 hour

        self.mail_counters = {}
        self.mail_timeout = 15 # seconds
        self.mail_attempts_limit = 3 # per mail limit

        self.https_socks = []
        self.http_socks = []

        # TODO holds global state until GLSettings is inverted and this
        # state managed as an object by the application
        self.appstate = ObjectDict()
        self.appstate.process_supervisor = None
        self.appstate.tor_exit_set = TorExitSet()
        self.appstate.latest_version = LooseVersion(__version__)
        self.appstate.api_token_session = None
        self.appstate.api_token_session_suspended = False

        self.acme_directory_url = 'https://acme-v01.api.letsencrypt.org/directory'

    def reset_hourly(self):
        self.RecentEventQ[:] = []
        self.RecentAnomaliesQ.clear()
        self.exceptions.clear()
        self.exceptions_email_count = 0
        self.mail_counters.clear()
        self.stats_collection_start_time = datetime_now()

    def get_mail_counter(self, receiver_id):
        return self.mail_counters.get(receiver_id, 0)

    def increment_mail_counter(self, receiver_id):
        self.mail_counters[receiver_id] = self.mail_counters.get(receiver_id, 0) + 1

    def eval_paths(self):
        self.config_file_path = '/etc/globaleaks'
        self.pidfile_path = os.path.join(self.pid_path, 'globaleaks.pid')
        self.files_path = os.path.abspath(os.path.join(self.working_path, 'files'))

        self.db_path = os.path.abspath(os.path.join(self.working_path, 'db'))
        self.log_path = os.path.abspath(os.path.join(self.working_path, 'log'))
        self.submission_path = os.path.abspath(os.path.join(self.files_path, 'submission'))
        self.tmp_upload_path = os.path.abspath(os.path.join(self.files_path, 'tmp'))
        self.static_path = os.path.abspath(os.path.join(self.files_path, 'static'))
        self.static_db_source = os.path.abspath(os.path.join(self.root_path, 'globaleaks', 'db'))
        self.ssl_file_path = os.path.abspath(os.path.join(self.files_path, 'ssl'))

        self.db_schema = os.path.join(self.static_db_source, 'sqlite.sql')
        self.db_file_name = 'glbackend-%d.db' % DATABASE_VERSION
        self.db_file_path = os.path.join(os.path.abspath(os.path.join(self.db_path, self.db_file_name)))
        self.db_uri = self.make_db_uri(self.db_file_path)

        self.logfile = os.path.abspath(os.path.join(self.log_path, 'globaleaks.log'))
        self.httplogfile = os.path.abspath(os.path.join(self.log_path, "http.log"))

        # gnupg path is used by PGP as temporary directory with keyring and files encryption.
        self.pgproot = os.path.abspath(os.path.join(self.ramdisk_path, 'gnupg'))

        # If we see that there is a custom build of GLClient, use that one.
        custom_client_path = '/var/globaleaks/client'
        if os.path.exists(custom_client_path):
            self.client_path = custom_client_path

        self.appdata_file = os.path.join(self.client_path, 'data/appdata.json')
        self.questionnaires_path = os.path.join(self.client_path, 'data/questionnaires')
        self.questions_path = os.path.join(self.client_path, 'data/questions')
        self.field_attrs_file = os.path.join(self.client_path, 'data/field_attrs.json')

        self.torbrowser_path = os.path.join(self.working_path, 'torbrowser')

    def set_ramdisk_path(self):
        self.ramdisk_path = '/dev/shm/globaleaks'
        if not os.path.isdir('/dev/shm'):
            self.ramdisk_path = os.path.join(self.working_path, 'ramdisk')

    def set_devel_mode(self):
        self.devel_mode = True

        # is forced by -z, but unitTest has not:
        if not self.cmdline_options:
            self.developer_name = u"Random GlobaLeaks Developer"
        else:
            self.developer_name = unicode(self.cmdline_options.developer_name)

        # when running in development mode lower the key bits to 512
        self.key_bits = 512
        self.csr_sign_bits = 256

        self.acme_directory_url = 'https://acme-staging.api.letsencrypt.org/directory'

        self.pid_path = os.path.join(self.root_path, 'workingdir')
        self.working_path = os.path.join(self.root_path, 'workingdir')

        self.set_ramdisk_path()

    def set_client_path(self, glcp):
        self.client_path = os.path.abspath(os.path.join(self.root_path, glcp))

    def enable_debug_mode(self):
        import signal

        def start_pdb(signal, trace):
            import pdb

            pdb.set_trace()

        signal.signal(signal.SIGQUIT, start_pdb)

    def load_cmdline_options(self):
        self.nodaemon = self.cmdline_options.nodaemon

        if self.cmdline_options.disable_swap:
            self.disable_swap = True

        log.setloglevel(verbosity_dict[self.cmdline_options.loglevel])

        self.bind_address = self.cmdline_options.ip

        self.disable_backend_exception_notification = self.cmdline_options.disable_backend_exception_notification
        self.disable_client_exception_notification = self.cmdline_options.disable_client_exception_notification

        self.socks_host = self.cmdline_options.socks_host

        if not self.validate_port(self.cmdline_options.socks_port):
            sys.exit(1)
        self.socks_port = self.cmdline_options.socks_port

        if self.cmdline_options.ramdisk:
            self.ramdisk_path = self.cmdline_options.ramdisk

        if self.cmdline_options.user and self.cmdline_options.group:
            self.user = self.cmdline_options.user
            self.group = self.cmdline_options.group
            self.uid = pwd.getpwnam(self.cmdline_options.user).pw_uid
            self.gid = grp.getgrnam(self.cmdline_options.group).gr_gid
        elif self.cmdline_options.user:
            # user selected: get also the associated group
            self.user = self.cmdline_options.user
            self.uid = pwd.getpwnam(self.cmdline_options.user).pw_uid
            self.gid = pwd.getpwnam(self.cmdline_options.user).pw_gid
        elif self.cmdline_options.group:
            # group selected: keep the current user
            self.group = self.cmdline_options.group
            self.gid = grp.getgrnam(self.cmdline_options.group).gr_gid
            self.uid = os.getuid()

        if self.uid == 0 or self.gid == 0:
            self.print_msg("Invalid user: cannot run as root")
            sys.exit(1)

        if self.cmdline_options.working_path:
            self.working_path = self.cmdline_options.working_path

        if self.cmdline_options.developer_name:
            self.print_msg("Enabling development mode for %s" % self.cmdline_options.developer_name)
            self.developer_name = unicode(self.cmdline_options.developer_name)
            self.set_devel_mode()
            self.orm_debug = self.cmdline_options.orm_debug

        self.api_prefix = self.cmdline_options.api_prefix

        if self.cmdline_options.client_path:
            self.set_client_path(self.cmdline_options.client_path)

        self.eval_paths()

        if self.nodaemon:
            self.print_msg("Going in background; log available at %s" % GLSettings.logfile)

        # special evaluation of client directory:
        indexfile = os.path.join(self.client_path, 'index.html')
        if os.path.isfile(indexfile):
            self.print_msg("Serving the client from directory: %s" % self.client_path)
        else:
            self.print_msg("Unable to find a directory to load the client from")
            sys.exit(1)

    def validate_port(self, inquiry_port):
        if inquiry_port <= 0 or inquiry_port > 65535:
            self.print_msg("Invalid port number ( > than 65535 can't work! )")
            return False
        return True

    def create_directory(self, path):
        """
        Create the specified directory;
        Returns True on success, False if the directory was already existing
        """
        if not os.path.exists(path):
            try:
                os.mkdir(path)
            except OSError as excep:
                self.print_msg("Error in creating directory: %s (%s)" % (path, excep.strerror))
                raise excep

            return True

        return False

    def create_directories(self):
        """
        Execute some consistency checks on command provided Globaleaks paths

        if one of working_path or static path is created we copy
        here the static files (default logs, and in the future pot files for localization)
        because here stay all the files needed by the application except the python scripts
        """
        for dirpath in [self.working_path,
                        self.db_path,
                        self.files_path,
                        self.submission_path,
                        self.tmp_upload_path,
                        self.log_path,
                        self.ramdisk_path,
                        self.static_path]:
            self.create_directory(dirpath)

    def check_directories(self):
        for path in (self.working_path, self.root_path, self.client_path, self.ramdisk_path,
                     self.files_path, self.static_path, self.submission_path, self.log_path):
            if not os.path.exists(path):
                raise Exception("%s does not exist!" % path)

        # Directory with Write + Read access
        for rdwr in (self.working_path, self.ramdisk_path, self.files_path, self.static_path,
                     self.submission_path, self.log_path):
            if not os.access(rdwr, os.W_OK | os.X_OK):
                raise Exception("write capability missing in: %s" % rdwr)

        # Directory in Read access
        for rdonly in (self.root_path, self.client_path):
            if not os.access(rdonly, os.R_OK | os.X_OK):
                raise Exception("read capability missing in: %s" % rdonly)

    def fix_file_permissions(self, path=None):
        """
        Recursively updates file permissions on a given path.
        UID and GID default to -1, and mode is required
        """
        if not path:
            path = self.working_path

        try:
            if path != self.working_path:
                os.chown(path, self.uid, self.gid)
                os.chmod(path, 0o700)
        except Exception as excep:
            self.print_msg("Unable to update permissions on %s: %s" % (path, excep))
            sys.exit(1)

        for item in glob.glob(path + '/*'):
            if os.path.isdir(item):
                self.fix_file_permissions(item)
            else:
                try:
                    os.chown(item, self.uid, self.gid)
                    os.chmod(item, 0o700)
                except Exception as excep:
                    self.print_msg("Unable to update permissions on %s: %s" % (item, excep))
                    sys.exit(1)

    def remove_directories(self):
        if os.path.exists(self.working_path):
            dir_util.remove_tree(self.working_path, 0)

    def drop_privileges(self):
        if os.getgid() != self.gid:
            try:
                self.print_msg("switching group privileges since %d to %d" % (os.getgid(), self.gid))
                os.setgid(self.gid)
                os.initgroups(self.user, self.gid)
            except OSError as droperr:
                self.print_msg("unable to drop group privileges: %s" % droperr.strerror)
                sys.exit(1)

        if os.getuid() != self.uid:
            try:
                self.print_msg("switching user privileges since %d to %d" % (os.getuid(), self.uid))
                os.setuid(self.uid)
            except OSError as droperr:
                self.print_msg("unable to drop user privileges: %s" % droperr.strerror)
                sys.exit(1)

    def print_msg(self, *args):
        if not self.testing:
            print(*args)

    def cleaning_dead_files(self):
        """
        This function is called at the start of GlobaLeaks, in
        bin/globaleaks, and checks if the file is present in
        temporally_encrypted_dir
        """
        # temporary .aes files must be simply deleted
        for f in os.listdir(GLSettings.tmp_upload_path):
            path = os.path.join(GLSettings.tmp_upload_path, f)
            self.print_msg("Removing old temporary file: %s" % path)

            try:
                os.remove(path)
            except OSError as excep:
                self.print_msg("Error while evaluating removal for %s: %s" % (path, excep.strerror))

        # temporary .aes files with lost keys can be deleted
        # while temporary .aes files with valid current key
        # will be automagically handled by delivery sched.
        keypath = os.path.join(self.ramdisk_path, GLSettings.AES_keyfile_prefix)

        for f in os.listdir(GLSettings.submission_path):
            path = os.path.join(GLSettings.submission_path, f)
            try:
                result = GLSettings.AES_file_regexp_comp.match(f)
                if result is not None:
                    if not os.path.isfile("%s%s" % (keypath, result.group(1))):
                        self.print_msg("Removing old encrypted file (lost key): %s" % path)
                        os.remove(path)
            except Exception as excep:
                self.print_msg("Error while evaluating removal for %s: %s" % (path, excep))

    @staticmethod
    def make_db_uri(db_file_path):
        return 'sqlite:' + db_file_path + '?foreign_keys=ON'

    def start_jobs(self):
        from globaleaks.jobs import jobs_list, services_list
        from globaleaks.jobs.base import LoopingJobsMonitor

        for job in jobs_list:
            self.jobs.append(job().schedule())

        for service in services_list:
            self.services.append(service().schedule())

        self.jobs_monitor = LoopingJobsMonitor(self.jobs)
        self.jobs_monitor.schedule()

    @inlineCallbacks
    def stop_jobs(self):
        for job in self.jobs + self.services:
            yield job.stop()

        if self.jobs_monitor is not None:
            yield self.jobs_monitor.stop()
            self.jobs_monitor = None

    def get_agent(self):
        if self.memory_copy.anonymize_outgoing_connections:
            return get_tor_agent(self.socks_host, self.socks_port)
        else:
            return get_web_agent()

    def print_listening_interfaces(self):
        print("GlobaLeaks is now running and accessible at the following urls:")

        for port in self.bind_local_ports:
            print("- [LOCAL HTTP]\t--> http://127.0.0.1:%d%s" % (port, self.api_prefix))

        if self.memory_copy.reachable_via_web:
            hostname = self.memory_copy.hostname if self.memory_copy.hostname else '0.0.0.0'
            print("- [REMOTE HTTP]\t--> http://%s%s" % (hostname, self.api_prefix))
            if self.memory_copy.private.https_enabled:
                print("- [REMOTE HTTPS]\t--> https://%s%s" % (hostname, self.api_prefix))

        if self.memory_copy.onionservice:
            print("- [REMOTE Tor]:\t--> http://%s%s" % (self.memory_copy.onionservice, self.api_prefix))


# GLSettings is a singleton class exported once
GLSettings = GLSettingsClass()
