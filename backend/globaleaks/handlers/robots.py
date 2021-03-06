# -*- coding: UTF-8
from globaleaks.handlers.base import BaseHandler
from globaleaks.rest import errors
from globaleaks.settings import GLSettings


class RobotstxtHandler(BaseHandler):
    check_roles = '*'

    def get(self):
        """
        Get the robots.txt
        """
        self.request.setHeader('Content-Type', 'text/plain')

        data = "User-agent: *\n"

        if GLSettings.memory_copy.allow_indexing:
            site = 'https://' + GLSettings.memory_copy.hostname
            data += "Allow: /\n"
            data += "Sitemap: %s/sitemap.xml" % site
        else:
            data += "Disallow: /"

        return data


class SitemapHandler(BaseHandler):
    check_roles = '*'

    def get(self):
        """
        Get the sitemap.xml
        """
        if not GLSettings.memory_copy.allow_indexing:
            raise errors.ResourceNotFound()

        site = 'https://' + GLSettings.memory_copy.hostname

        self.request.setHeader('Content-Type', 'text/xml')

        data = "<?xml version='1.0' encoding='UTF-8' ?>\n" + \
               "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9' xmlns:xhtml='http://www.w3.org/1999/xhtml'>\n"

        for url in ['/#/', '/#/submission']:
            data += "  <url>\n" + \
                    "    <loc>" + site + url + "</loc>\n" + \
                    "    <changefreq>weekly</changefreq>\n" + \
                    "    <priority>1.00</priority>\n"

            for lang in sorted(GLSettings.memory_copy.languages_enabled):
                if lang != GLSettings.memory_copy.default_language:
                    l = lang.lower()
                    l = l.replace('_', '-')
                    data += "<xhtml:link rel='alternate' hreflang='" + l + "' href='" + site + "/#/?lang=" + lang + "' />\n"

            data += "  </url>\n"

        data += "</urlset>"

        return data
