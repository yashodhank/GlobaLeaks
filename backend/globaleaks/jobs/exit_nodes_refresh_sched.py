# -*- coding: UTF-8
# Implement refresh of the list of exit nodes IPs.

from globaleaks.jobs.base import ExternNetLoopingJob
from globaleaks.settings import GLSettings
from globaleaks.utils.utility import log
from twisted.internet.defer import inlineCallbacks


__all__ = ['ExitNodesRefreshSchedule']


class ExitNodesRefreshSchedule(ExternNetLoopingJob):
    name = "Exit Nodes Refresh"
    interval = 3600
    threaded = False

    @inlineCallbacks
    def operation(self):
        net_agent = GLSettings.get_agent()
        log.debug('Fetching list of Tor exit nodes')
        yield GLSettings.appstate.tor_exit_set.update(net_agent)
        log.debug('Retrieved a list of %d exit nodes', len(GLSettings.appstate.tor_exit_set))
