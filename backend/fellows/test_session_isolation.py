"""Browser-like checks for independent Admin/portal identities and CSRF secrets."""
import re

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.test import Client, TestCase, override_settings
from django.urls import path

from .session_middleware import SCOPE_KEY


def portal_form(request):
    return HttpResponse(get_token(request))


def portal_login(request):
    user = authenticate(request, username=request.POST.get('username'), password=request.POST.get('password'))
    if user is None:
        return HttpResponse('invalid', status=401)
    login(request, user)
    return HttpResponse('signed in')


def portal_logout(request):
    logout(request)
    return HttpResponse('signed out')


def portal_identity(request):
    return HttpResponse(request.user.username if request.user.is_authenticated else 'anonymous')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('portal/form/', portal_form),
    path('portal/login/', portal_login),
    path('portal/logout/', portal_logout),
    path('portal/identity/', portal_identity),
]


@override_settings(ROOT_URLCONF=__name__)
class SessionIsolationTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_superuser('operator', 'operator@example.com', 'staff-password')
        self.fellow = get_user_model().objects.create_user('student', 'student@example.com', 'student-password')
        self.browser = Client(enforce_csrf_checks=True)

    def token(self, path):
        response = self.browser.get(path)
        self.assertEqual(response.status_code, 200)
        if path == '/portal/form/':
            return response.content.decode()
        match = re.search(r'name="csrfmiddlewaretoken" value="([a-zA-Z0-9]+)"', response.content.decode())
        self.assertIsNotNone(match)
        return match.group(1)

    def admin_login(self):
        token = self.token('/admin/login/')
        response = self.browser.post('/admin/login/', {
            'username': 'operator', 'password': 'staff-password',
            'csrfmiddlewaretoken': token, 'next': '/admin/',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.browser.get('/admin/').status_code, 200)

    def fellow_login(self):
        response = self.browser.post('/portal/login/', {
            'username': 'student', 'password': 'student-password',
            'csrfmiddlewaretoken': self.token('/portal/form/'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(self.browser.get('/portal/identity/'), 'student')

    def test_login_identities_and_cookie_paths_are_independent(self):
        self.admin_login()
        self.assertContains(self.browser.get('/portal/identity/'), 'anonymous')
        self.fellow_login()
        self.assertEqual(self.browser.get('/admin/').status_code, 200)
        self.assertEqual(self.browser.cookies[settings.ADMIN_SESSION_COOKIE_NAME]['path'], '/admin/')
        self.assertEqual(self.browser.cookies[settings.SESSION_COOKIE_NAME]['path'], '/')
        self.assertNotEqual(self.browser.cookies[settings.ADMIN_SESSION_COOKIE_NAME].value,
                            self.browser.cookies[settings.SESSION_COOKIE_NAME].value)

    def test_portal_logout_keeps_admin_signed_in(self):
        self.admin_login()
        self.fellow_login()
        self.assertEqual(self.browser.post('/portal/logout/', {
            'csrfmiddlewaretoken': self.token('/portal/form/'),
        }).status_code, 200)
        self.assertContains(self.browser.get('/portal/identity/'), 'anonymous')
        self.assertEqual(self.browser.get('/admin/').status_code, 200)

    def test_admin_logout_keeps_portal_signed_in(self):
        self.fellow_login()
        self.admin_login()
        self.assertEqual(self.browser.post('/admin/logout/', {
            'csrfmiddlewaretoken': self.token('/admin/'),
        }).status_code, 302)
        self.assertEqual(self.browser.get('/admin/').status_code, 302)
        self.assertContains(self.browser.get('/portal/identity/'), 'student')

    def test_admin_login_does_not_invalidate_open_portal_form(self):
        portal_token = self.token('/portal/form/')
        self.admin_login()
        response = self.browser.post('/portal/login/', {
            'username': 'student', 'password': 'student-password',
            'csrfmiddlewaretoken': portal_token,
        })
        self.assertEqual(response.status_code, 200)

    def test_portal_login_does_not_invalidate_open_admin_form(self):
        admin_token = self.token('/admin/login/')
        self.fellow_login()
        response = self.browser.post('/admin/login/', {
            'username': 'operator', 'password': 'staff-password',
            'csrfmiddlewaretoken': admin_token, 'next': '/admin/',
        })
        self.assertEqual(response.status_code, 302)

    def test_missing_stale_or_other_scope_csrf_tokens_remain_forbidden(self):
        stale_token = self.token('/portal/form/')
        self.fellow_login()
        self.assertEqual(self.browser.post('/portal/logout/').status_code, 403)
        self.assertEqual(self.browser.post('/portal/logout/', {'csrfmiddlewaretoken': stale_token}).status_code, 403)
        admin_token = self.token('/admin/login/')
        self.assertEqual(self.browser.post('/portal/logout/', {'csrfmiddlewaretoken': admin_token}).status_code, 403)
        self.assertEqual(self.browser.post('/portal/logout/', {'csrfmiddlewaretoken': self.token('/portal/form/')}).status_code, 200)

    def test_a_bound_session_token_cannot_be_used_in_the_other_area(self):
        self.fellow_login()
        portal_key = self.browser.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertEqual(SessionStore(portal_key).get(SCOPE_KEY), 'portal')
        self.browser.cookies[settings.ADMIN_SESSION_COOKIE_NAME] = portal_key
        self.assertEqual(self.browser.get('/admin/').status_code, 302)
        self.assertContains(self.browser.get('/portal/identity/'), 'student')

    def test_global_cookie_settings_are_not_mutated_between_requests(self):
        before = (settings.SESSION_COOKIE_NAME, settings.SESSION_COOKIE_PATH)
        self.admin_login()
        self.fellow_login()
        self.assertEqual(before, (settings.SESSION_COOKIE_NAME, settings.SESSION_COOKIE_PATH))
        self.assertNotIn('csrftoken', self.browser.cookies)
