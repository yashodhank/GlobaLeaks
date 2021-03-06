from globaleaks import db
from globaleaks.handlers.admin import shorturl
from globaleaks.jobs.session_management_sched import SessionManagementSchedule
from globaleaks.models.config import PrivateFactory
from globaleaks.orm import transact
from globaleaks.rest import errors
from globaleaks.security import generate_api_token
from globaleaks.tests import helpers
from twisted.internet.defer import inlineCallbacks


@transact
def set_api_digest(store, s):
    PrivateFactory(store).set_val(u'admin_api_token_digest', s)


class TestAPITokenEnabled(helpers.TestHandlerWithPopulatedDB):
    _handler = shorturl.ShortURLCollection

    @inlineCallbacks
    def setUp(self):
        self.api_tok, digest = generate_api_token()
        yield helpers.TestHandlerWithPopulatedDB.setUp(self)
        yield set_api_digest(digest)
        yield db.refresh_memory_variables()

    @inlineCallbacks
    def test_accept_token(self):
        shorturl_desc = self.get_dummy_shorturl()
        handler = self.request(shorturl_desc, headers={'x-api-token': self.api_tok})
        yield handler.post()

    @inlineCallbacks
    def test_deny_token(self):
        shorturl_desc = self.get_dummy_shorturl()
        handler = self.request(shorturl_desc, headers={'x-api-token': 'a'*32})
        yield self.assertRaises(errors.NotAuthenticated, handler.post)

    @inlineCallbacks
    def test_anti_bruteforce_mechanism(self):
        # If an invalid token is submitted the application should revoke the api token
        shorturl_desc = self.get_dummy_shorturl('a')

        handler = self.request(shorturl_desc, headers={'x-api-token': self.api_tok})
        yield handler.post()

        handler = self.request(shorturl_desc, headers={'x-api-token': 'a'*32})
        yield self.assertRaises(errors.NotAuthenticated, handler.post)

        handler = self.request(shorturl_desc, headers={'x-api-token': self.api_tok})
        yield self.assertRaises(errors.NotAuthenticated, handler.post)

        # After the session management job is run the token should be restored
        yield SessionManagementSchedule().operation()

        handler = self.request(self.get_dummy_shorturl('b'), headers={'x-api-token': self.api_tok})
        yield handler.post()

    @inlineCallbacks
    def tearDown(self):
        yield set_api_digest('')
        yield helpers.TestHandlerWithPopulatedDB.tearDown(self)


class TestAPITokenDisabled(helpers.TestHandlerWithPopulatedDB):
    _handler = shorturl.ShortURLCollection

    @inlineCallbacks
    def test_deny_token(self):
        # The active component of this application is the placement of the api key
        # in the private memory copy. When that changes this test will break.
        self.api_tok, digest = generate_api_token()
        yield set_api_digest(digest)

        shorturl_desc = self.get_dummy_shorturl()
        handler = self.request(shorturl_desc, headers={'x-api-token': self.api_tok})
        yield self.assertRaises(errors.NotAuthenticated, handler.post)

    @inlineCallbacks
    def tearDown(self):
        yield set_api_digest('')
        yield helpers.TestHandlerWithPopulatedDB.tearDown(self)
