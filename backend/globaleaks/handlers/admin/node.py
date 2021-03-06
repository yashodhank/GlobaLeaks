# -*- coding: UTF-8
#
#   /admin/node
#   *****
# Implementation of the code executed on handler /admin/node
#
import os
from storm.expr import In

from globaleaks import models, utils, LANGUAGES_SUPPORTED_CODES, LANGUAGES_SUPPORTED
from globaleaks.db import db_refresh_memory_variables
from globaleaks.db.appdata import load_appdata
from globaleaks.handlers.base import BaseHandler
from globaleaks.models.config import NodeFactory, PrivateFactory
from globaleaks.models.l10n import EnabledLanguage, NodeL10NFactory
from globaleaks.orm import transact
from globaleaks.rest import errors, requests
from globaleaks.settings import GLSettings
from globaleaks.utils.utility import log


def db_admin_serialize_node(store, language):
    node_dict = NodeFactory(store).admin_export()

    # Contexts and Receivers relationship
    configured  = store.find(models.ReceiverContext).count() > 0
    custom_homepage = os.path.isfile(os.path.join(GLSettings.static_path, "custom_homepage.html"))

    misc_dict = {
        'version': PrivateFactory(store).get_val(u'version'),
        'latest_version': str(GLSettings.appstate.latest_version),
        'languages_supported': LANGUAGES_SUPPORTED,
        'languages_enabled': EnabledLanguage.list(store),
        'configured': configured,
        'custom_homepage': custom_homepage,
    }

    l10n_dict = NodeL10NFactory(store).localized_dict(language)

    return utils.sets.merge_dicts(node_dict, misc_dict, l10n_dict)


@transact
def admin_serialize_node(store, language):
    return db_admin_serialize_node(store, language)


def enable_disable_languages(store, request):
    cur_enabled_langs = EnabledLanguage.list(store)
    new_enabled_langs = [unicode(y) for y in request['languages_enabled']]

    if len(new_enabled_langs) < 1:
        raise errors.InvalidInputFormat("No languages enabled!")

    if request['default_language'] not in new_enabled_langs:
        raise errors.InvalidInputFormat("Invalid lang code for chosen default_language")

    appdata = None
    for lang_code in new_enabled_langs:
        if lang_code not in LANGUAGES_SUPPORTED_CODES:
            raise errors.InvalidInputFormat("Invalid lang code: %s" % lang_code)
        if lang_code not in cur_enabled_langs:
            if appdata is None:
                appdata = load_appdata()
            log.debug("Adding a new lang %s" % lang_code)
            EnabledLanguage.add_new_lang(store, lang_code, appdata)

    to_remove = list(set(cur_enabled_langs) - set(new_enabled_langs))

    if to_remove:
        store.find(models.User, In(models.User.language, to_remove)).set(language=request['default_language'])

        models.db_delete(store, models.l10n.EnabledLanguage, In(models.l10n.EnabledLanguage.name, to_remove))


def db_update_node(store, request, language):
    """
    Update and serialize the node infos

    :param store: the store on which perform queries.
    :param language: the language in which to localize data
    :return: a dictionary representing the serialization of the node
    """
    enable_disable_languages(store, request)

    if language in request['languages_enabled']:
        node_l10n = NodeL10NFactory(store)
        node_l10n.update(request, language)

    node = NodeFactory(store)
    node.update(request)

    if request['basic_auth'] and request['basic_auth_username'] and request['basic_auth_password']:
        node.set_val(u'basic_auth', True)
        node.set_val(u'basic_auth_username', request['basic_auth_username'])
        node.set_val(u'basic_auth_password', request['basic_auth_password'])
    else:
        node.set_val(u'basic_auth', False)

    db_refresh_memory_variables(store)

    # TODO pass instance of db_update_node into admin_serialize
    return db_admin_serialize_node(store, language)


@transact
def update_node(*args):
    return db_update_node(*args)


class NodeInstance(BaseHandler):
    check_roles = 'admin'
    cache_resource = True
    invalidate_cache = True

    def get(self):
        """
        Get the node infos.

        Parameters: None
        Response: AdminNodeDesc
        """
        return admin_serialize_node(self.request.language)

    def put(self):
        """
        Update the node infos.

        Request: AdminNodeDesc
        Response: AdminNodeDesc
        Errors: InvalidInputFormat
        """
        request = self.validate_message(self.request.content.read(),
                                        requests.AdminNodeDesc)

        return update_node(request, self.request.language)
