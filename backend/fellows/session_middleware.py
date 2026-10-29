"""Keep staff Admin and the fellow portal signed in independently.

The database/session engine is shared, but cookies, authentication state, and
session-backed CSRF secrets belong to one request scope. No global settings are
modified while handling a request.
"""
import time

from django.conf import settings
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils.cache import patch_vary_headers
from django.utils.http import http_date


SCOPE_KEY = '_unbound_session_scope'


class IsolatedSessionMiddleware(SessionMiddleware):
    @staticmethod
    def cookie_config(request):
        if request.path_info == '/admin' or request.path_info.startswith('/admin/'):
            return 'admin', settings.ADMIN_SESSION_COOKIE_NAME, '/admin/'
        return 'portal', settings.SESSION_COOKIE_NAME, settings.SESSION_COOKIE_PATH

    def process_request(self, request):
        scope, name, _ = self.cookie_config(request)
        session = self.SessionStore(request.COOKIES.get(name))
        if session.get(SCOPE_KEY) not in (None, scope):
            # A token from the other area is not an authentication token here.
            # Do not flush it: that would sign the other area out.
            session = self.SessionStore()
        request.session = session

    def process_response(self, request, response):
        """Django's session save/expiry rules, using request-local cookie details."""
        scope, name, path = self.cookie_config(request)
        try:
            if not request.session.is_empty() and request.session.get(SCOPE_KEY) != scope:
                request.session[SCOPE_KEY] = scope
            accessed = request.session.accessed
            modified = request.session.modified
            empty = request.session.is_empty()
        except AttributeError:
            return response

        if name in request.COOKIES and empty:
            response.delete_cookie(name, path=path, domain=settings.SESSION_COOKIE_DOMAIN,
                                   samesite=settings.SESSION_COOKIE_SAMESITE)
            need_vary_cookie = True
        else:
            need_vary_cookie = accessed
            if (modified or settings.SESSION_SAVE_EVERY_REQUEST) and not empty:
                if request.session.get_expire_at_browser_close():
                    max_age, expires = None, None
                else:
                    max_age = request.session.get_expiry_age()
                    expires = http_date(time.time() + max_age)
                if response.status_code < 500:
                    try:
                        request.session.save()
                    except UpdateError:
                        raise SessionInterrupted(
                            'This area was signed out while the request was being processed. '
                            'Reload the page and sign in again.'
                        )
                    response.set_cookie(
                        name, request.session.session_key, max_age=max_age, expires=expires,
                        domain=settings.SESSION_COOKIE_DOMAIN, path=path,
                        secure=settings.SESSION_COOKIE_SECURE or None,
                        httponly=settings.SESSION_COOKIE_HTTPONLY or None,
                        samesite=settings.SESSION_COOKIE_SAMESITE,
                    )
                    need_vary_cookie = True
        if need_vary_cookie:
            patch_vary_headers(response, ('Cookie',))
        return response
