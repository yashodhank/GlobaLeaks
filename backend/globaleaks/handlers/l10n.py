# -*- coding: utf-8 -*-
#
# langfiles
#  **************
#
import os

from globaleaks import models
from globaleaks.handlers.base import BaseHandler
from globaleaks.orm import transact
from globaleaks.security import directory_traversal_check
from globaleaks.settings import GLSettings
from globaleaks.utils.utility import read_json_file


def langfile_path(lang):
    return os.path.abspath(os.path.join(GLSettings.client_path, 'l10n', '%s.json' % lang))


@transact
def get_l10n(store, lang):
    path = langfile_path(lang)
    directory_traversal_check(GLSettings.client_path, path)

    texts = read_json_file(path)

    custom_texts = store.find(models.CustomTexts, models.CustomTexts.lang == lang).one()
    custom_texts = custom_texts.texts if custom_texts is not None else {}

    texts.update(custom_texts)

    return texts


class L10NHandler(BaseHandler):
    """
    This class is used to return the custom translation files;
    if the file are not present, default translations are returned
    """
    check_roles = '*'
    cache_resource = True

    def get(self, lang):
        return get_l10n(lang)
